"""Read-before-write analysis for the saved teach-pendant banks."""

from dataclasses import dataclass, field

from . import runtime as rt
from .input_position_values import (
    POSITION_MODIFIED, merge_positions, position_register_result, teach_position_store_facts,
)
from .input_teach_catalog import TEACH_COMMENT_KIND, TEACH_HEADER_KIND, TeachCatalogDiscovery, TeachCatalogFacts
from .input_teach_handles import TeachHandle, TeachHandleDiscovery
from .input_value_conversions import MAX_SCALAR_CHOICES, UNKNOWN, Value
from .position_register_models import register_description
from .storage import tuple_spec
from .teach import teach_rejects


LOCAL_POSITION_KIND = 'teach_position_register'
PROGRAM_POSITION_KIND = 'teach_program_position'
TEACH_POSITION_SECTIONS = {LOCAL_POSITION_KIND: 'position_registers', PROGRAM_POSITION_KIND: 'positions'}
TEACH_SCALAR_SECTIONS = {
    'teach_numeric_register': 'numeric_registers', 'teach_string_register': 'string_registers',
    TEACH_COMMENT_KIND: 'comments', TEACH_HEADER_KIND: 'attributes',
}
TEACH_SCALAR_GETTERS = {'GET_TPE_REG': 'numeric', 'GET_TPE_STR_REG': 'string'}
TEACH_SCALAR_SETTERS = {'SET_INT_TPE_REG': 'INTEGER', 'SET_REAL_TPE_REG': 'REAL', 'SET_TPE_STR_REG': 'STRING'}
TEACH_POSITION_GETTERS = {
    'GET_TPE_POS_REG': ('XYZWPREXT',), 'GET_TPE_JPOS_REG': ('JOINTPOS', 9),
    'GET_POS_TPE': ('XYZWPREXT',), 'GET_JPOS_TPE': ('JOINTPOS', 9),
}
TEACH_POSITION_SETTERS = {
    'SET_TPE_POS_REG': 'XYZWPR', 'SET_TPE_EPOS_REG': 'XYZWPREXT', 'SET_TPE_JPOS_REG': 'JOINTPOS',
    'SET_POS_TPE': 'XYZWPR', 'SET_EPOS_TPE': 'XYZWPREXT', 'SET_JPOS_TPE': 'JOINTPOS',
    'SET_TRNS_TPE': 'POSITION',
}
TEACH_FRAME_QUERIES = {'TPE_POS_REG_FRM', 'GET_POS_FRM'}
TEACH_POSITION_QUERIES = TEACH_FRAME_QUERIES | {'TPE_POS_REG_TYPE', 'GET_POS_TYP'}
TEACH_POSITION_SERVICES = TEACH_POSITION_GETTERS.keys() | TEACH_POSITION_SETTERS.keys() | TEACH_POSITION_QUERIES
TEACH_HANDLE_POSITIONS = {
    'GET_POS_TPE', 'GET_JPOS_TPE', 'GET_POS_FRM', 'GET_POS_TYP',
    'SET_POS_TPE', 'SET_EPOS_TPE', 'SET_JPOS_TPE', 'SET_TRNS_TPE',
}
TEACH_HANDLE_SERVICES = {'OPEN_TPE', 'CLOSE_TPE'}


def teach_program_config_key(config, program):
    programs = config.get('teach_programs', {}).get('programs', {})
    return next((name for name in programs if name.upper() == program), None)


def teach_position_config_address(config, program, group, number, kind):
    """Locate the original JSON spelling and ordered row for a TP position."""
    name = teach_program_config_key(config, program)
    if name is None:
        return None
    rows = config['teach_programs']['programs'][name].get(TEACH_POSITION_SECTIONS[kind], [])
    for index, row in enumerate(rows):
        if (row['group'], row['number']) == (group, number):
            return name, index, row
    return name, len(rows), None


@dataclass
class TeachBankFacts:
    cells: dict = field(default_factory=dict)
    uncertain_programs: set = field(default_factory=set)
    all_uncertain: bool = False

    def copy(self):
        return TeachBankFacts(self.cells.copy(), self.uncertain_programs.copy(), self.all_uncertain)

    @classmethod
    def merge(cls, flows, merge_values):
        return cls(merge_positions([flow.cells for flow in flows], merge_values),
                   set().union(*(flow.uncertain_programs for flow in flows)),
                   any(flow.all_uncertain for flow in flows))

    def lookup(self, key):
        uncertain = self.all_uncertain or key[0] in self.uncertain_programs
        return self.cells.get(key, UNKNOWN if uncertain else None)

    def invalidate(self, program):
        if program is None:
            self.all_uncertain = True
            self.cells.clear()
        else:
            self.uncertain_programs.add(program)
            self.cells = {key: value for key, value in self.cells.items() if key[0] != program}

    def copy_program(self, source, target, tick):
        tick(len(self.cells))
        snapshot = {}
        for key, value in self.cells.items():
            if key[0] == source:
                snapshot[(target,) + key[1:]] = value
            elif key[0] != target:
                snapshot[key] = value
        self.cells = snapshot
        self.uncertain_programs.discard(target)
        if source in self.uncertain_programs:
            self.uncertain_programs.add(target)


@dataclass
class TeachFacts:
    numeric: TeachBankFacts = field(default_factory=TeachBankFacts)
    strings: TeachBankFacts = field(default_factory=TeachBankFacts)
    local_positions: TeachBankFacts = field(default_factory=TeachBankFacts)
    program_positions: TeachBankFacts = field(default_factory=TeachBankFacts)
    # None for the table or sequence records a loss of precision. When all
    # possible unknown handles have the same owner, local access can still
    # be checked for that owner.
    handles: dict[int, tuple[TeachHandle | None, ...]] | None = field(default_factory=dict)
    sequence: int | None = 0
    unknown_handle_owner: str | None = None
    comments: TeachBankFacts = field(default_factory=TeachBankFacts)
    catalog: TeachCatalogFacts = field(default_factory=TeachCatalogFacts)

    def data_banks(self):
        return self.numeric, self.strings, self.local_positions, self.program_positions

    def banks(self):
        return (*self.data_banks(), self.comments)

    def copy(self):
        return TeachFacts(self.numeric.copy(), self.strings.copy(), self.local_positions.copy(),
                          self.program_positions.copy(), None if self.handles is None else self.handles.copy(),
                          self.sequence, self.unknown_handle_owner, self.comments.copy(), self.catalog.copy())

    def forget_handles(self, owner):
        owners = self.handle_owners()
        self.unknown_handle_owner = owner if owners <= {owner} else None
        self.handles = None
        self.sequence = None

    def handle_owners(self):
        if self.handles is None:
            return {self.unknown_handle_owner}
        return {handle.owner for options in self.handles.values() for handle in options if handle is not None}

    def handle_choices(self, number):
        return self.handles.get(number, (None,)) if self.handles is not None else ()

    def set_handle_choices(self, number, options):
        choices = tuple(dict.fromkeys(options))
        if choices == (None,):
            self.handles.pop(number, None)
        else:
            self.handles[number] = choices

    def matching_handle(self, predicate):
        if self.handles is None:
            return UNKNOWN
        possible = False
        for options in self.handles.values():
            checks = [handle is not None and predicate(handle) for handle in options]
            if all(checks):
                return True
            possible |= any(checks)
        return UNKNOWN if possible else False

    def definitely_open_programs(self):
        programs = set()
        for options in (self.handles or {}).values():
            first = options[0]
            if first is not None and all(handle is not None and handle.program == first.program for handle in options):
                programs.add(first.program)
        return programs

    def release_owner(self, owner):
        if self.handles is not None:
            for number, options in list(self.handles.items()):
                self.set_handle_choices(number, (None if handle is not None and handle.owner == owner else handle
                                                 for handle in options))
        elif self.unknown_handle_owner == owner:
            self.handles = {}
            self.unknown_handle_owner = None

    @staticmethod
    def merge_handles(flows):
        if any(flow.handles is None for flow in flows):
            return None
        first = flows[0].handles
        if all(flow.handles == first for flow in flows[1:]):
            return first.copy()
        handles = {}
        numbers = dict.fromkeys(number for flow in flows for number in flow.handles)
        for number in numbers:
            options = tuple(dict.fromkeys(option for flow in flows for option in flow.handle_choices(number)))
            if len(options) > MAX_SCALAR_CHOICES:
                return None
            if options != (None,):
                handles[number] = options
        return handles

    @classmethod
    def merge(cls, flows, merge_values):
        first = flows[0]
        sequence = first.sequence if all(flow.sequence == first.sequence for flow in flows[1:]) else None
        handles = cls.merge_handles(flows)
        owner = None
        if handles is None:
            owners = set().union(*(flow.handle_owners() for flow in flows))
            if len(owners) == 1:
                owner = next(iter(owners))
        return cls(*(TeachBankFacts.merge([getattr(flow, name) for flow in flows], merge_values)
                     for name in ('numeric', 'strings', 'local_positions', 'program_positions')),
                   handles, sequence, owner, TeachBankFacts.merge([flow.comments for flow in flows], merge_values),
                   TeachCatalogFacts.merge([flow.catalog for flow in flows]))


class TeachDiscovery(TeachCatalogDiscovery, TeachHandleDiscovery):
    """Teach services evaluated against detached bank facts and saved configuration."""

    def teach_operands(self, node, inputs, flow, conditional, **options):
        operands = self.service_operands(node, inputs, flow, conditional, **options)
        if operands is not None and self.checked_robot_service_outputs(operands[1], node, flow):
            self.context('teach_programs', None)
            return operands
        return None

    def teach_stable(self, flow):
        return not (flow.opaque or flow.task_order_unknown or self.callback_depth or self.repeat_depth)

    def teach_local_status(self, program, flow, *, write=False):
        if not self.teach_stable(flow):
            return UNKNOWN
        if program is None:
            return 9
        owner = self.task_roots[-1]
        state = flow.teach
        if state.handles is None:
            return 0 if state.unknown_handle_owner == owner else UNKNOWN
        access = 3 if write else 1
        self.tick(len(state.handles))
        conflict = state.matching_handle(
            lambda handle: handle.owner != owner and handle.program == program and teach_rejects(handle.reject, access),
        )
        if conflict is UNKNOWN:
            return UNKNOWN
        return 4 if conflict else 0

    def teach_unknown_access(self, operation, outputs, node, flow, code):
        *receivers, status = outputs
        self.unresolved_at(code, operation+' requires a known TP bank, address and execution order', node)
        self.uncertain_bank_read(receivers, status, flow, node)

    def teach_scalar_call(self, node, flow, conditional):
        reading = node['value'] in TEACH_SCALAR_GETTERS
        operands = self.teach_operands(node, 1 if reading else 2, flow, conditional)
        if operands is None:
            return Value(complete=False)
        inputs, outputs = operands
        self.address_service_cases(
            inputs, (0,), flow, conditional,
            lambda values, branch, possible: self.teach_scalar_transfer(values, outputs, node, branch, possible),
        )
        return Value()

    def teach_scalar_transfer(self, inputs, outputs, node, flow, conditional, *, access=None):
        operation = node['value']
        reading = operation in TEACH_SCALAR_GETTERS
        kind = TEACH_SCALAR_SETTERS.get(operation)
        numeric = TEACH_SCALAR_GETTERS.get(operation) == 'numeric' if reading else kind != 'STRING'
        *receivers, status = outputs
        bank = getattr(self.saved_bindings, 'teach_programs', None)
        owner = self.task_roots[-1]
        program = bank.callers.get(owner) if bank is not None else None
        number = inputs[0].constant
        cells = flow.teach.numeric if numeric else flow.teach.strings
        entry = flow.teach.catalog.entry(bank, program) if program is not None else None
        code = self.teach_local_status(program, flow, write=not reading) if access is None else access
        if bank is not None and type(code) is int and code:
            self.bank_status(status, code, flow, node)
            return
        if bank is not None and entry is not UNKNOWN and type(number) is int and code is UNKNOWN and self.teach_handle_access(flow):
            self.apply_service_cases(
                flow, (0, 4), lambda code, branch: self.teach_scalar_transfer(inputs, outputs, node, branch, True, access=code),
            )
            return
        if bank is None or entry is UNKNOWN or code is UNKNOWN or type(number) is not int:
            if not reading and program is not None:
                self.tick(len(cells.cells))
                cells.invalidate(program)
            self.teach_unknown_access(operation, outputs, node, flow, 'teach-register')
            return
        limit = bank.register_limit if numeric else bank.string_register_limit
        if not 1 <= number <= limit:
            self.bank_status(status, 2, flow, node)
            return
        key = program, number
        if reading:
            self.teach_scalar_read(bank, entry.origin, number, cells.lookup(key), numeric, receivers,
                                   status, node, flow, conditional)
        else:
            self.teach_scalar_write(bank, key, cells, kind, inputs[1], status, node, flow)

    def teach_scalar_write(self, bank, key, cells, kind, source, status, node, flow):
        spec = ['STRING', bank.string_capacity] if kind == 'STRING' else [kind]
        value = source.constant
        if value is not UNKNOWN:
            try:
                with rt._numeric_scope('pythonic'):
                    value = rt.checked(tuple_spec(spec), value, node.get('line'))
            except rt.KarelRuntimeError as error:
                self.unresolved_at('teach-register', str(error), node)
                flow.stopped = True
                return
        cells.cells[key] = Value(value, spec=spec)
        self.bank_status(status, 0, flow, node)

    def teach_scalar_read(self, bank, origin, number, stored, numeric, receivers, status, node, flow, conditional):
        initial = UNKNOWN
        if not isinstance(stored, Value):
            if origin is None:
                if stored is UNKNOWN:
                    self.uncertain_bank_read(receivers, status, flow, node)
                else:
                    self.bank_status(status, 1, flow, node)
                return
            kind, spec = ('teach_numeric_register', ['NUMERIC']) if numeric else (
                'teach_string_register', ['STRING', bank.string_capacity])
            self.teach_input(kind, origin, number, spec, node, flow, conditional or stored is UNKNOWN)
            code, initial = bank.saved_register(origin, 'numeric' if numeric else 'string', number)
            if stored is UNKNOWN or code:
                self.uncertain_bank_read(receivers, status, flow, node)
                return

        constant = stored.constant if isinstance(stored, Value) else UNKNOWN
        if numeric:
            flag, integer, real = receivers
            kind = stored.spec[0] if isinstance(stored, Value) and stored.spec else None
            is_real = (kind == 'REAL' if kind is not None else
                       type(initial) is float if initial is not UNKNOWN else UNKNOWN)
            self.write(flag, Value(is_real, spec=['BOOLEAN']), flow, node)
            if is_real is UNKNOWN:
                self.uncertain_bank_read((integer, real), status, flow, node, code=0)
            else:
                target = real if is_real else integer
                self.write(target, Value(constant, spec=target.spec), flow, node)
                self.bank_status(status, 0, flow, node)
            return

        target = receivers[0]
        capacity = target.spec[1]
        text = constant if type(constant) is str else initial
        if type(capacity) is not int:
            self.teach_unknown_access(node['value'], (*receivers, status), node, flow, 'teach-register')
        elif type(text) is str and len(text) > capacity:
            self.bank_status(status, 8, flow, node)
        elif type(text) is str or bank.string_capacity <= capacity:
            self.write(target, Value(constant, spec=target.spec), flow, node)
            self.bank_status(status, 0, flow, node)
        else:
            self.uncertain_bank_read(receivers, status, flow, node)

    def teach_position_call(self, node, flow, conditional):
        operation = node['value']
        schema = TEACH_POSITION_GETTERS.get(operation)
        setter = TEACH_POSITION_SETTERS.get(operation)
        handled = operation in TEACH_HANDLE_POSITIONS
        address_count = 2 if handled else 1
        count = address_count + bool(setter) if schema or setter else len(node['args']) - 3
        trailing = int(bool(schema or setter) and len(node['args']) > count + 1)
        operands = self.teach_operands(node, count, flow, conditional, trailing=trailing,
                                      complete_input=address_count if setter else None)
        result = Value(spec=list(schema)) if schema else Value()
        if operands is None:
            return result
        inputs, outputs = operands
        explicit = bool(trailing or (not (schema or setter) and count > address_count))
        indices = (*range(address_count), len(inputs) - 1) if explicit else tuple(range(address_count))
        value = self.address_service_cases(
            inputs, indices, flow, conditional,
            lambda values, branch, possible: self.teach_position_transfer(
                values, outputs, node, branch, possible, explicit=explicit,
            ),
            handle=handled, result=bool(schema),
        )
        return value if schema else result

    def teach_position_transfer(self, inputs, outputs, node, flow, conditional, *, explicit, access=None):
        operation = node['value']
        schema = TEACH_POSITION_GETTERS.get(operation)
        setter = TEACH_POSITION_SETTERS.get(operation)
        handled = operation in TEACH_HANDLE_POSITIONS
        address_count = 2 if handled else 1
        result = Value(spec=list(schema)) if schema else Value()
        *receivers, status = outputs
        bank = getattr(self.saved_bindings, 'teach_programs', None)
        owner = self.task_roots[-1]
        cells = flow.teach.program_positions if handled else flow.teach.local_positions
        if handled:
            target = self.teach_handle_program(inputs[0].constant, flow, write=bool(setter))
            stable = target is not UNKNOWN
            program = target if stable else None
            access_error = (3, 'TP handle is closed or does not permit access') if target is None else None
        else:
            program = bank.callers.get(owner) if bank is not None else None
            code = self.teach_local_status(program, flow, write=bool(setter)) if access is None else access
            if (bank is not None and code is UNKNOWN and self.teach_handle_access(flow)
                    and flow.teach.catalog.entry(bank, program) is not UNKNOWN):
                if type(inputs[0].constant) is int and (not explicit or type(inputs[-1].constant) is int):
                    return self.apply_service_cases(
                        flow, (0, 4), lambda code, branch: self.teach_position_transfer(
                            inputs, outputs, node, branch, True, explicit=explicit, access=code,
                        ), merge_results=bool(schema),
                    )
            stable = code is not UNKNOWN
            access_error = ({9: (9, 'calling task has no saved TP bank'),
                             4: (4, 'TP bank is held by another task')}.get(code) if stable else None)
        number = inputs[address_count - 1].constant
        group = inputs[-1].constant if explicit else self.default_position_group(bank)
        entry = flow.teach.catalog.entry(bank, program) if bank is not None and program is not None else None
        if bank is None or entry is UNKNOWN or not stable:
            if setter and (handled or program is not None):
                self.tick(len(cells.cells))
                cells.invalidate(program)
            self.teach_unknown_access(operation, outputs, node, flow, 'teach-position')
            return result
        if setter:
            try:
                stored = teach_position_store_facts(setter, inputs[address_count], node.get('line'), self.tick)
            except (rt.KarelRuntimeError, TypeError, ValueError, ArithmeticError) as error:
                self.unresolved_at('teach-position', str(error), node)
                flow.stopped = True
                return result
        if access_error is not None:
            code, reason = access_error
        elif type(number) is not int or type(group) is not int:
            if setter:
                self.tick(len(cells.cells))
                cells.invalidate(program)
            self.teach_unknown_access(operation, outputs, node, flow, 'teach-position')
            return result
        elif not bank.address(group, number, bank.position_limit if handled else bank.position_register_limit):
            code, reason = 2, 'address is outside the TP bank'
        else:
            code = 0

        if code:
            if schema:
                self.position_read_failed(operation, status, code, node, flow, reason)
            else:
                self.bank_status(status, code, flow, node)
            return result
        key = program, group, number
        if setter:
            cells.cells[key] = stored
            self.bank_status(status, 0, flow, node)
            return result

        kind = PROGRAM_POSITION_KIND if handled else LOCAL_POSITION_KIND
        origin = entry.origin
        initial = bank.saved_position_metadata(origin, number, group, local=not handled) if origin is not None else None
        stored = cells.lookup(key)
        spec = tuple_spec(stored.spec) if isinstance(stored, Value) and stored.spec else (
            initial[0] if initial is not None and stored is None else None
        )
        if schema:
            if origin is None and stored is None:
                self.position_read_failed(operation, status, 17038, node, flow, 'source-created TP row is missing')
                return result
            return self.teach_position_read(kind, (origin, group, number), result, stored, spec,
                                            status, node, flow, conditional)
        self.teach_position_metadata(operation, initial, stored, spec, receivers, status, node, flow)
        return result

    def teach_position_metadata(self, operation, initial, stored, spec, receivers, status, node, flow):
        if stored is None and initial is None:
            self.bank_status(status, 17038, flow, node)
        elif stored is UNKNOWN:
            self.uncertain_bank_read(receivers, status, flow, node)
        else:
            if operation in TEACH_FRAME_QUERIES:
                values = initial[1:] if initial is not None else (0, 0)
            else:
                values = register_description(spec) if spec is not None else (UNKNOWN, UNKNOWN)
            for loc, value in zip(receivers, values):
                self.write(loc, Value(value, spec=['INTEGER']), flow, node)
            self.bank_status(status, 0, flow, node)

    def teach_position_read(self, kind, key, result, stored, spec, status, node, flow, conditional):
        origin, group, number = key
        if origin is not None and not isinstance(stored, Value) and stored is not POSITION_MODIFIED:
            self.teach_input(kind, origin, number, result.spec, node, flow,
                             conditional or stored is UNKNOWN, group=group)
        operation = node['value']
        if spec is not None and (spec[0] == 'JOINTPOS') != (result.spec[0] == 'JOINTPOS'):
            self.position_read_failed(operation, status, 2, node, flow, 'TP position uses a different representation')
            return result
        if isinstance(stored, Value) and stored.spec is not None:
            try:
                result = position_register_result(result.spec, stored, tick=self.tick)
            except (rt.KarelRuntimeError, TypeError, ValueError, ArithmeticError) as error:
                self.unresolved_at('teach-position', str(error), node)
                flow.stopped = True
                return result
        # Follow the successful path for a matching or newly supplied input row.
        # An untracked source write keeps subsequent status analysis conservative.
        self.bank_status(status, UNKNOWN if stored is UNKNOWN else 0, flow, node)
        return result

    def teach_position_recorded(self, bank, program, number, initial, flow):
        if initial:
            return True
        cells = flow.teach.program_positions
        self.tick(len(bank.groups))
        values = [cells.lookup((program, group, number)) for group in bank.groups]
        if any(isinstance(value, Value) or value is POSITION_MODIFIED for value in values):
            return True
        return UNKNOWN if any(value is UNKNOWN for value in values) else False

    def teach_available_position(self, node, flow, conditional):
        operands = self.teach_operands(node, 1, flow, conditional)
        if operands is None:
            return Value(complete=False)
        inputs, outputs = operands
        self.address_service_cases(
            inputs, (0,), flow, conditional,
            lambda values, branch, _: self.teach_available_transfer(values[0], outputs, node, branch),
            handle=True,
        )
        return Value()

    def teach_available_transfer(self, handle, outputs, node, flow):
        receiver, status = outputs
        bank = getattr(self.saved_bindings, 'teach_programs', None)
        program = self.teach_handle_program(handle.constant, flow)
        if bank is None or program is UNKNOWN:
            self.teach_unknown_access(node['value'], outputs, node, flow, 'teach-position')
            return Value()
        if program is None:
            self.bank_status(status, 3, flow, node)
            return Value()
        entry = flow.teach.catalog.entry(bank, program)
        if entry is UNKNOWN:
            self.teach_unknown_access(node['value'], outputs, node, flow, 'teach-position')
            return Value()

        cells = flow.teach.program_positions
        occupied = set()
        if entry.origin is not None:
            for number in bank.saved_position_numbers(entry.origin):
                self.tick()
                occupied.add(number)
        possible = set()
        for (owner, _, number), stored in cells.cells.items():
            self.tick()
            if owner == program:
                (possible if stored is UNKNOWN else occupied).add(number)

        for number in range(1, bank.position_limit + 1):
            self.tick()
            if number not in occupied:
                if number in possible or cells.all_uncertain or program in cells.uncertain_programs:
                    self.teach_unknown_access(node['value'], outputs, node, flow, 'teach-position')
                else:
                    self.write(receiver, Value(number, spec=['INTEGER']), flow, node)
                    self.bank_status(status, 0, flow, node)
                break
        else:
            self.bank_status(status, 6, flow, node)
        return Value()
