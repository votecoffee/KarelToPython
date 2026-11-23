"""Discovery for TP handle allocation, ownership and closure."""

from dataclasses import dataclass

from .input_value_conversions import UNKNOWN, Value
from .teach import checked_open_request, teach_open_conflict


@dataclass(frozen=True)
class TeachHandle:
    program: str
    owner: str
    mode: int
    reject: int


class TeachHandleDiscovery:
    def teach_handle_access(self, flow):
        return self.teach_stable(flow) and flow.teach.handles is not None

    def teach_handle_program(self, number, flow, *, write=False):
        if not self.teach_handle_access(flow) or type(number) is not int:
            return UNKNOWN
        programs = set()
        owner = self.task_roots[-1]
        for handle in flow.teach.handle_choices(number):
            allowed = handle is not None and handle.owner == owner and handle.mode in ((2,) if write else (1, 2))
            programs.add(handle.program if allowed else None)
        return next(iter(programs)) if len(programs) == 1 else UNKNOWN

    def teach_handle_call(self, node, flow, conditional):
        opening = node['value'] == 'OPEN_TPE'
        operands = self.teach_operands(node, 3 if opening else 1, flow, conditional)
        if operands is None:
            return Value(complete=False)
        inputs, outputs = operands
        self.address_service_cases(
            inputs, range(len(inputs)), flow, conditional,
            lambda values, branch, _: self.teach_handle_transfer(values, outputs, node, branch),
        )
        return Value()

    def teach_handle_transfer(self, inputs, outputs, node, flow):
        operation = node['value']
        known = [item.constant for item in inputs]
        bank = getattr(self.saved_bindings, 'teach_programs', None)
        state = flow.teach
        if bank is None or not self.teach_handle_access(flow):
            state.forget_handles(self.task_roots[-1] if self.teach_stable(flow) else None)
            self.teach_unknown_access(operation, outputs, node, flow, 'teach-handle')
        elif operation == 'CLOSE_TPE':
            self.teach_close(known[0], outputs[0], node, flow)
        elif any(item is UNKNOWN for item in known):
            state.forget_handles(self.task_roots[-1])
            self.teach_unknown_access(operation, outputs, node, flow, 'teach-handle')
        else:
            self.teach_open(bank, known, outputs, node, flow)

    def teach_close(self, number, status, node, flow):
        state = flow.teach
        owner = self.task_roots[-1]
        if type(number) is int:
            options = state.handle_choices(number)
            codes = tuple(dict.fromkeys(0 if handle is not None and handle.owner == owner else 3 for handle in options))
            state.set_handle_choices(number, (None if handle is not None and handle.owner == owner else handle
                                              for handle in options))
        else:
            self.tick(len(state.handles))
            codes = (3,)
            for index, options in state.handles.items():
                if any(handle is not None and handle.owner == owner for handle in options):
                    # Unknown CLOSE can remove any own handle. Foreign handles
                    # and the next allocation sequence are unaffected.
                    state.handles[index] = tuple(dict.fromkeys((*options, None)))
                    codes = (0, 3)
            if len(codes) > 1:
                self.unresolved_at('teach-handle', 'CLOSE_TPE may close any handle owned by this task', node)
        value = Value(codes[0] if len(codes) == 1 else UNKNOWN, spec=['INTEGER'],
                      scalar_choices=codes if len(codes) > 1 else ())
        self.write(status, value, flow, node)

    def teach_open(self, bank, values, outputs, node, flow):
        name, mode, reject = values
        _, status = outputs
        code, program = checked_open_request(name, mode, reject, node.get('line'))
        if code:
            self.bank_status(status, code, flow, node)
            return
        state = flow.teach
        entry = state.catalog.entry(bank, program)
        owner = self.task_roots[-1]
        if entry is UNKNOWN:
            state.forget_handles(owner)
            self.teach_unknown_access(node['value'], outputs, node, flow, 'teach-handle')
            return
        if entry is None:
            self.bank_status(status, 1, flow, node)
            return
        self.tick(len(state.handles))
        conflict = state.matching_handle(
            lambda handle: handle.owner != owner and handle.program == program
            and teach_open_conflict(mode, reject, handle.mode, handle.reject),
        )
        if conflict is True:
            self.bank_status(status, 4, flow, node)
            return
        if state.sequence is None:
            state.forget_handles(owner)
            self.teach_unknown_access(node['value'], outputs, node, flow, 'teach-handle')
            return
        codes = [4] if conflict is UNKNOWN else []
        if state.sequence >= 2147483646 or sum(None not in options for options in state.handles.values()) >= 1024:
            codes.append(6)
        else:
            if len(state.handles) >= 1024:
                codes.append(6)
            codes.append(0)
        handle = TeachHandle(program, owner, mode, reject)
        if len(codes) > 1:
            self.apply_service_cases(
                flow, codes, lambda code, branch: self.teach_open_result(code, handle, outputs, node, branch),
            )
        else:
            self.teach_open_result(codes[0], handle, outputs, node, flow)

    def teach_open_result(self, code, handle, outputs, node, flow):
        receiver, status = outputs
        if not code:
            state = flow.teach
            state.sequence += 1
            state.handles[state.sequence] = (handle,)
            self.write(receiver, Value(state.sequence, spec=['INTEGER']), flow, node)
        self.bank_status(status, code, flow, node)
