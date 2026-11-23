"""Discovery for TP handle allocation, ownership and closure."""

from dataclasses import dataclass, field, replace

from .input_value_conversions import MAX_SCALAR_CHOICES, MAX_SERVICE_CASES, UNKNOWN, Value
from .teach import checked_open_request, teach_open_conflict, teach_rejects


OPEN_MODES = (0, 1, 2)
REJECT_MODES = (0, 1, 2, 3, 4)
HANDLE_LIMIT = 1024
SEQUENCE_LIMIT = 2147483646
MAX_GUARD_COPIES = 4
MAX_GUARD_FACTS = 32767


def guard_reference(node):
    """Identify a source reference with selectors that need no evaluation."""
    kind, args = node['kind'], node['args']
    if kind == 'name':
        return ('name', node['value'])
    if kind == 'group' and len(args) == 1:
        return guard_reference(args[0])
    if kind in ('field', 'index'):
        base = guard_reference(args[0])
        if base is not None:
            if kind == 'field':
                return ('field', base, node['value'])
            if all(item['kind'] == 'literal' and type(item['value']) is int for item in args[1:]):
                return ('index', base, tuple(item['value'] for item in args[1:]))
    return None


@dataclass
class OpenGuard:
    call: dict
    end: int
    reads_handle: bool
    cases: list = field(default_factory=list)
    facts: int = 0
    abandoned: bool = False

    def abandon(self):
        self.abandoned = True
        self.cases.clear()

    @property
    def projects(self):
        return len(self.cases) > 1 and (self.reads_handle or len({code for code, _ in self.cases}) > 1)



@dataclass(frozen=True)
class TeachHandle:
    # None denotes an unrestricted program name or legal request option.
    program: str | None
    owner: str
    mode: int | None
    reject: int | None

    def targets(self, program):
        return UNKNOWN if self.program is None else self.program == program

    def rejects(self, program, access):
        target = self.targets(program)
        if target is False or self.reject is not None and not teach_rejects(self.reject, access):
            return False
        return UNKNOWN if self.reject is None else target

    @staticmethod
    def direction_conflict(reject, mode):
        rejects = REJECT_MODES if reject is None else (reject,)
        modes = OPEN_MODES if mode is None else (mode,)
        access = (0, 1, 3)
        matches = {teach_rejects(mask, access[choice]) for mask in rejects for choice in modes}
        return matches.pop() if len(matches) == 1 else UNKNOWN

    def conflicts(self, other):
        if self.owner == other.owner:
            return False
        exact_name = self.program is not None and other.program is not None
        if exact_name and self.program != other.program:
            return False
        if None not in (self.mode, self.reject, other.mode, other.reject):
            outcome = teach_open_conflict(self.mode, self.reject, other.mode, other.reject)
        else:
            first = self.direction_conflict(other.reject, self.mode)
            second = self.direction_conflict(self.reject, other.mode)
            if first is True or second is True:
                outcome = True
            else:
                outcome = UNKNOWN if first is UNKNOWN or second is UNKNOWN else False
        return outcome if exact_name or outcome is False else UNKNOWN

    @classmethod
    def compact(cls, options):
        """Retain each owner, widening fields that differ for the same slot."""
        groups = {}
        for handle in options:
            if handle is not None:
                groups.setdefault(handle.owner, []).append(handle)
        result = [None] if None in options else []
        for owner, handles in groups.items():
            fields = []
            for field in ('program', 'mode', 'reject'):
                candidates = {getattr(handle, field) for handle in handles}
                fields.append(candidates.pop() if len(candidates) == 1 else None)
            program, mode, reject = fields
            result.append(cls(program, owner, mode, reject))
        return tuple(result)


class TeachHandleDiscovery:
    def find_open_guard(self, body, index, flow):
        """Find a guard after at most a few side-effect-free assignments."""
        statement = body[index]
        if statement['kind'] != 'call' or index + 1 >= len(body):
            return None
        call = statement['args'][0]
        if (call['kind'] != 'call' or call['value'] != 'OPEN_TPE' or len(call['args']) != 5
                or 'OPEN_TPE' in self.plan['routines'] or not self.teach_stable(flow) or flow.handlers):
            return None
        status, receiver = guard_reference(call['args'][4]), guard_reference(call['args'][3])
        active_status = {status} if status is not None else set()
        active_handle = {receiver} if receiver is not None else set()
        end = min(len(body), index + MAX_GUARD_COPIES + 2)
        for following in range(index + 1, end):
            node = body[following]
            if node['kind'] in ('if', 'select'):
                references = self.open_guard_references(node['args'][0])
                reads_handle = bool(references & active_handle)
                return OpenGuard(call, following, reads_handle) if reads_handle or references & active_status else None
            if node['kind'] != 'assign' or node.get('geometry_assignment') or node.get('path_assignment_type'):
                return None
            target_node, source_node = node['args']
            target, source = guard_reference(target_node), guard_reference(source_node)
            if target is None or (source is None and source_node['kind'] not in ('literal', 'real_literal', 'predefined')):
                return None
            for tracked in (active_status, active_handle):
                if source in tracked:
                    tracked.add(target)
                else:
                    tracked.discard(target)
        return None

    def open_guard_references(self, expression):
        pending = [expression]
        references = set()
        while pending:
            self.tick()
            node = pending.pop()
            if not isinstance(node, dict):
                continue
            reference = guard_reference(node)
            if reference is not None:
                references.add(reference)
            pending.extend(node.get('args', ()))
        return references

    def teach_open_status(self, status, code, flow, node):
        self.bank_status(status, code, flow, node)
        guard = self.open_guard
        if guard is None or guard.call is not node or guard.abandoned:
            return
        facts = sum(len(value) for value in vars(flow).values() if isinstance(value, (dict, set, tuple)))
        facts += len(flow.teach.handles or ()) + sum(len(bank.cells) for bank in flow.teach.banks())
        guard.facts += facts
        if len(guard.cases) >= MAX_SERVICE_CASES or guard.facts > MAX_GUARD_FACTS:
            guard.abandon()
        else:
            guard.cases.append((code, flow.copy()))

    def teach_handle_access(self, flow):
        return self.teach_stable(flow) and flow.teach.handles is not None

    def teach_handle_program(self, number, flow, *, write=False):
        if not self.teach_handle_access(flow) or type(number) is not int:
            return UNKNOWN
        state = flow.teach
        owner = self.task_roots[-1]
        if state.may_have_untracked(number, owner=owner):
            return UNKNOWN
        programs = set()
        for handle in state.handle_choices(number):
            if handle is None or handle.owner != owner:
                programs.add(None)
            elif handle.mode is None:
                programs.add(UNKNOWN)
            elif handle.mode not in ((2,) if write else (1, 2)):
                programs.add(None)
            else:
                programs.add(handle.program if handle.program is not None else UNKNOWN)
        return next(iter(programs)) if len(programs) == 1 else UNKNOWN

    def teach_resolved_handle_choices(self, number, flow):
        state = flow.teach
        owner = self.task_roots[-1]
        if state.may_have_untracked(number, owner=owner):
            return ()
        options = []
        for handle in state.handle_choices(number):
            if handle is not None and handle.owner == owner and handle.mode is None:
                options.extend(replace(handle, mode=mode) for mode in OPEN_MODES)
            else:
                options.append(handle)
        return tuple(dict.fromkeys(options))

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
            if self.open_guard is not None and self.open_guard.call is node:
                self.open_guard.abandon()
            state.forget_handles(self.task_roots[-1] if self.teach_stable(flow) else None)
            self.teach_unknown_access(operation, outputs, node, flow, 'teach-handle')
        elif operation == 'CLOSE_TPE':
            self.teach_close(known[0], outputs[0], node, flow)
        else:
            self.teach_open(bank, inputs, outputs, node, flow)

    def teach_close(self, number, status, node, flow):
        state = flow.teach
        owner = self.task_roots[-1]
        if type(number) is int:
            options = state.handle_choices(number)
            codes = tuple(dict.fromkeys(0 if handle is not None and handle.owner == owner else 3 for handle in options))
            if state.may_have_untracked(number, owner=owner) and 0 not in codes:
                codes = (*codes, 0)
            state.set_handle_choices(number, (None if handle is not None and handle.owner == owner else handle
                                              for handle in options))
        else:
            self.tick(len(state.handles))
            codes = (0, 3) if any(handle.owner == owner for handle in state.untracked_handles) else (3,)
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

    def teach_open(self, bank, inputs, outputs, node, flow):
        name, mode, reject = (value.constant for value in inputs)
        _, status = outputs
        # Validate all concrete request fields before considering possible opens.
        code, program = checked_open_request(
            'A' if name is UNKNOWN else name,
            1 if mode is UNKNOWN else mode, 0 if reject is UNKNOWN else reject, node.get('line'),
        )
        if code:
            self.teach_open_status(status, code, flow, node)
            return
        state = flow.teach
        codes = {2} if any(value is UNKNOWN for value in (name, mode, reject)) else set()
        if name is UNKNOWN:
            codes.add(1)
            programs = self.teach_open_programs(bank, flow, inputs[0].spec)
        else:
            entry = state.catalog.entry(bank, program)
            if entry is UNKNOWN or entry is None:
                codes.add(1)
            programs = () if entry is None else (program,)

        owner = self.task_roots[-1]
        concrete_mode = None if mode is UNKNOWN else mode
        concrete_reject = None if reject is UNKNOWN else reject
        sequences = state.sequences if state.sequences is not None else (None,)
        if len(programs) * len(sequences) + len(codes) > MAX_SERVICE_CASES:
            programs = (None,)
        requests = [TeachHandle(program, owner, concrete_mode, concrete_reject) for program in programs]
        cases = [(code, None, None) for code in sorted(codes)]
        for handle in requests:
            cases.extend((0, handle, sequence) for sequence in sequences)
        if len(cases) == 1:
            self.teach_open_case(cases[0], outputs, node, flow)
        else:
            self.apply_service_cases(flow, cases, lambda case, branch: self.teach_open_case(case, outputs, node, branch))

    def teach_open_programs(self, bank, flow, spec):
        entries = self.teach_listing_entries(bank, flow, '*', 2)
        if entries is None:
            return (None,)
        width = spec[1] if spec and spec[0] == 'STRING' else None
        names = tuple(name for name, _ in entries if type(width) is not int or len(name) <= width)
        return names if len(names) < MAX_SCALAR_CHOICES else (None,)

    def teach_open_case(self, case, outputs, node, flow):
        code, handle, sequence = case
        if code:
            self.teach_open_status(outputs[-1], code, flow, node)
            return
        state = flow.teach
        if sequence is not None:
            state.restrict_sequence(sequence)
        self.tick(len(state.handles) + len(state.untracked_handles))
        conflict = state.matching_handle(handle.conflicts)
        if conflict is True:
            self.teach_open_status(outputs[-1], 4, flow, node)
            return
        codes = [4] if conflict is UNKNOWN else []
        definite_count = sum(None not in options for options in state.handles.values())
        if (sequence is not None and sequence >= SEQUENCE_LIMIT) or definite_count >= HANDLE_LIMIT:
            codes.append(6)
        else:
            if sequence is None or len(state.handles) >= HANDLE_LIMIT or state.untracked_handles:
                codes.append(6)
            codes.append(0)
        if len(codes) > 1:
            self.apply_service_cases(
                flow, codes, lambda code, branch: self.teach_open_result(code, handle, sequence, outputs, node, branch),
            )
        else:
            self.teach_open_result(codes[0], handle, sequence, outputs, node, flow)

    def teach_open_result(self, code, handle, sequence, outputs, node, flow):
        receiver, status = outputs
        if not code:
            state = flow.teach
            if sequence is None:
                state.add_untracked_handle(handle)
                self.unresolved_at('teach-handle', 'OPEN_TPE allocation number is unresolved', node)
                self.write(receiver, Value(spec=['INTEGER']), flow, node)
            else:
                state.sequences = (sequence + 1,)
                state.handles[sequence + 1] = (handle,)
                self.write(receiver, Value(sequence + 1, spec=['INTEGER']), flow, node)
            if handle.program is None:
                self.unresolved_at('teach-handle', 'OPEN_TPE program is unresolved', node)
        self.teach_open_status(status, code, flow, node)
