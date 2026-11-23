"""Detached catalog and instruction facts for teach-program discovery."""

from dataclasses import dataclass, field, replace

from .extended import PROGRAM_KINDS
from .input_position_values import POSITION_MODIFIED
from .input_value_conversions import UNKNOWN, Value
from .teach import KIND_NAMES, TEACH_COMMENT_CAPACITY, checked_teach_kind, name_key


TEACH_CATALOG_SERVICES = {'CREATE_TPE', 'COPY_TPE', 'SELECT_TPE'}
TEACH_EDIT_SERVICES = {'GET_TPE_CMT', 'SET_TPE_CMT', 'DEL_INST_TPE'}
TEACH_COMMENT_KIND = 'teach_position_comment'


@dataclass(frozen=True)
class TeachProgramEntry:
    origin: str | None
    kind: str
    protected: bool
    instructions: object


def shared(values):
    first = values[0]
    return first if all(value == first for value in values[1:]) else UNKNOWN


def merged_entry(entries):
    entry = shared(entries)
    if entry is UNKNOWN and all(isinstance(item, TeachProgramEntry) for item in entries):
        base = replace(entries[0], instructions=UNKNOWN)
        if all(replace(item, instructions=UNKNOWN) == base for item in entries[1:]):
            return base
    return entry


@dataclass
class TeachCatalogFacts:
    # Unmentioned names resolve against the original saved bank.
    entries: dict = field(default_factory=dict)
    selection: object = None
    call_counts: object = None
    all_uncertain: bool = False
    saved_instruction_count_unknown: bool = False

    def copy(self):
        # The dependency counts are replaced atomically after a copy.
        return TeachCatalogFacts(self.entries.copy(), self.selection, self.call_counts,
                                 self.all_uncertain, self.saved_instruction_count_unknown)

    @classmethod
    def merge(cls, flows):
        names = set().union(*(flow.entries for flow in flows))
        return cls({name: merged_entry([flow.entries.get(name) for flow in flows]) for name in names},
                   shared([flow.selection for flow in flows]), shared([flow.call_counts for flow in flows]),
                   any(flow.all_uncertain for flow in flows),
                   any(flow.saved_instruction_count_unknown for flow in flows))

    def entry(self, bank, name):
        if self.all_uncertain:
            return UNKNOWN
        if name in self.entries:
            return self.entries[name]
        row = bank.saved_program_definition(name)
        if row is None:
            return None
        kind, protected, count = row
        return TeachProgramEntry(name, kind, protected, UNKNOWN if self.saved_instruction_count_unknown else count)

    def invalidate_instruction_counts(self, tick):
        tick(len(self.entries))
        self.entries = {
            name: replace(entry, instructions=UNKNOWN) if entry is not UNKNOWN else UNKNOWN
            for name, entry in self.entries.items()
        }
        self.saved_instruction_count_unknown = True

    def selected(self, bank):
        return bank.selected if self.selection is None else self.selection

    def is_full(self, bank):
        count = bank.program_count
        for name, entry in self.entries.items():
            if entry is UNKNOWN:
                return UNKNOWN
            count += bank.saved_program_definition(name) is None
        return count >= bank.program_limit

    def replace_dependency_counts(self, bank, source, target, tick):
        counts = self.call_counts
        if counts is UNKNOWN:
            return UNKNOWN
        if counts is None:
            counts = bank.saved_dependency_counts()
        tick(len(counts))
        updated = counts.copy()
        if source in counts:
            updated[target] = counts[source]
        else:
            updated.pop(target, None)
        if len(updated) > bank.program_limit or sum(updated.values()) > 32767:
            return 6
        self.call_counts = updated
        return 0


class TeachCatalogDiscovery:
    def teach_listing_entries(self, bank, flow):
        catalog = flow.teach.catalog
        if catalog.all_uncertain or any(entry is UNKNOWN for entry in catalog.entries.values()):
            return None
        saved = dict(bank.entries)
        saved.update((name, entry.kind) for name, entry in catalog.entries.items())
        return tuple(saved.items())

    def teach_inspection_metadata(self, bank, name, entry, flow):
        record = bank.metadata(entry.origin) if entry.origin is not None else None
        initialized = record['initialized'] if record is not None else False
        if not initialized:
            for facts in flow.teach.data_banks():
                self.tick(len(facts.cells))
                if any(key[0] == name and (isinstance(value, Value) or value is POSITION_MODIFIED)
                       for key, value in facts.cells.items()):
                    initialized = True
                    break
                if (facts.all_uncertain or name in facts.uncertain_programs
                        or any(key[0] == name for key in facts.cells)):
                    initialized = UNKNOWN
        attributes = dict(record['attributes']) if record is not None else {
            'AT_OWNER': '', 'AT_COMMENT': '', 'AT_SRC_NAME': '', 'AT_SRC_VRSN': 0,
        }
        attributes.update(AT_PROG_TYPE=PROGRAM_KINDS[KIND_NAMES[entry.kind]], AT_NUM_LINE=entry.instructions)
        selected = flow.teach.catalog.selected(bank)
        if flow.teach.handles is None or selected is UNKNOWN:
            active = UNKNOWN
        else:
            active = selected == name or self.teach_program_busy(name, flow)
        return {'loaded': True, 'initialized': initialized, 'active': active, 'attributes': attributes}

    def teach_catalog_call(self, node, flow, conditional):
        operation = node['value']
        count = {'CREATE_TPE': 2, 'COPY_TPE': 3, 'SELECT_TPE': 1}[operation]
        operands = self.teach_operands(node, count, flow, conditional)
        if operands is None:
            return Value(complete=False)
        inputs, (status,) = operands
        bank = getattr(self.saved_bindings, 'teach_programs', None)
        state = flow.teach
        values = [value.constant for value in inputs]
        code = UNKNOWN
        if bank is not None and self.teach_stable(flow) and len(self.task_roots) == 1:
            if all(value is not UNKNOWN for value in values) and not state.catalog.all_uncertain:
                code = self.teach_catalog_operation(operation, bank, values, node, flow)
        if code is UNKNOWN:
            if operation == 'SELECT_TPE':
                state.catalog.selection = UNKNOWN
            else:
                state.catalog.all_uncertain = True
            self.teach_unknown_access(operation, (status,), node, flow, 'teach-catalog')
        else:
            self.bank_status(status, code, flow, node)
        return Value()

    def teach_catalog_operation(self, operation, bank, values, node, flow):
        catalog = flow.teach.catalog
        line = node.get('line')
        name = name_key(values[0], line)
        if name is None:
            return 2
        entry = catalog.entry(bank, name)
        if entry is UNKNOWN:
            return UNKNOWN
        if operation == 'CREATE_TPE':
            kind = checked_teach_kind(values[1])
            if kind is None:
                return 2
            if entry is not None:
                return 5
            self.tick(len(catalog.entries))
            full = catalog.is_full(bank)
            if full is UNKNOWN or full:
                return UNKNOWN if full is UNKNOWN else 6
            catalog.entries[name] = TeachProgramEntry(None, kind, False, 0)
            return 0
        if operation == 'COPY_TPE':
            target = name_key(values[1], line)
            if target is None or target == name:
                return 2
            return self.teach_copy_program(bank, name, entry, target, values[2], flow)
        if entry is None:
            return 1
        if flow.teach.handles is None:
            return UNKNOWN
        if self.teach_program_busy(name, flow):
            return 4
        catalog.selection = name
        return 0

    def teach_program_busy(self, name, flow):
        handles = flow.teach.handles
        return handles is None or any(name == program for program, mode in handles.values())

    def teach_copy_program(self, bank, source, entry, target, overwrite, flow):
        state = flow.teach
        catalog = state.catalog
        if entry is None:
            return 1
        target_entry = catalog.entry(bank, target)
        selected = catalog.selected(bank)
        if target_entry is UNKNOWN or selected is UNKNOWN or state.handles is None:
            return UNKNOWN
        if self.teach_program_busy(source, flow) or self.teach_program_busy(target, flow) or selected == target:
            return 4
        if target_entry is not None:
            if target_entry.protected:
                return 4
            if not overwrite:
                return 5
        else:
            self.tick(len(catalog.entries))
            full = catalog.is_full(bank)
            if full is UNKNOWN or full:
                return UNKNOWN if full is UNKNOWN else 6
        status = catalog.replace_dependency_counts(bank, source, target, self.tick)
        if status is UNKNOWN or status:
            return status
        for cells in state.banks():
            cells.copy_program(source, target, self.tick)
        catalog.entries[target] = entry
        return 0

    def teach_edit_call(self, node, flow, conditional):
        operation = node['value']
        comment_write = operation == 'SET_TPE_CMT'
        operands = self.teach_operands(node, 3 if comment_write else 2, flow, conditional)
        if operands is None:
            return Value(complete=False)
        inputs, outputs = operands
        handle, number = (value.constant for value in inputs[:2])
        bank = getattr(self.saved_bindings, 'teach_programs', None)
        write = operation != 'GET_TPE_CMT'
        program = self.teach_handle_program(handle, flow, write=write)
        if bank is None or program is UNKNOWN:
            if comment_write:
                flow.teach.comments.invalidate(None)
            elif write:
                flow.teach.catalog.invalidate_instruction_counts(self.tick)
            self.teach_unknown_access(operation, outputs, node, flow, 'teach-edit')
        elif program is None:
            self.bank_status(outputs[-1], 3, flow, node)
        else:
            entry = flow.teach.catalog.entry(bank, program)
            if operation == 'DEL_INST_TPE':
                self.teach_delete_instruction(program, entry, number, outputs[-1], node, flow)
            else:
                self.teach_comment(bank, program, entry, number, inputs, outputs, node, flow, conditional)
        return Value()

    def teach_delete_instruction(self, program, entry, number, status, node, flow):
        if entry is UNKNOWN:
            self.teach_unknown_access(node['value'], (status,), node, flow, 'teach-edit')
            return
        count = entry.instructions
        if type(number) is not int or count is UNKNOWN:
            flow.teach.catalog.entries[program] = replace(entry, instructions=UNKNOWN)
            self.teach_unknown_access(node['value'], (status,), node, flow, 'teach-edit')
        elif not 1 <= number <= count:
            self.bank_status(status, 2, flow, node)
        else:
            flow.teach.catalog.entries[program] = replace(entry, instructions=count - 1)
            self.bank_status(status, 0, flow, node)

    def teach_comment(self, bank, program, entry, number, inputs, outputs, node, flow, conditional):
        status = outputs[-1]
        writing = node['value'] == 'SET_TPE_CMT'
        comments = flow.teach.comments
        if entry is UNKNOWN or type(number) is not int:
            if writing:
                self.tick(len(comments.cells))
                comments.invalidate(program)
            self.teach_unknown_access(node['value'], outputs, node, flow, 'teach-edit')
            return
        if not 1 <= number <= bank.position_limit:
            self.bank_status(status, 2, flow, node)
            return
        origin = entry.origin
        initial_position = origin is not None and bank.has_saved_position(origin, number)
        present = self.teach_position_recorded(bank, program, number, initial_position, flow)
        if present is UNKNOWN:
            if writing:
                comments.cells[program, number] = UNKNOWN
            self.teach_unknown_access(node['value'], outputs, node, flow, 'teach-edit')
        elif not present:
            self.bank_status(status, 17038, flow, node)
        elif writing:
            text = inputs[2].constant
            payload = text[:TEACH_COMMENT_CAPACITY] if type(text) is str else UNKNOWN
            comments.cells[program, number] = Value(payload, spec=['STRING', TEACH_COMMENT_CAPACITY])
            code = (7 if len(text) > TEACH_COMMENT_CAPACITY else 0) if type(text) is str else UNKNOWN
            self.bank_status(status, code, flow, node)
        else:
            self.teach_comment_read(bank, origin if initial_position else None, number,
                                    comments.lookup((program, number)), outputs, node, flow, conditional)

    def teach_comment_read(self, bank, origin, number, stored, outputs, node, flow, conditional):
        receiver, status = outputs
        initial = ''
        if origin is not None and not isinstance(stored, Value):
            initial = bank.saved_position_comment(origin, number)
            self.teach_input(TEACH_COMMENT_KIND, origin, number, ['STRING', TEACH_COMMENT_CAPACITY],
                             node, flow, conditional or stored is UNKNOWN)
        text = stored.constant if isinstance(stored, Value) else initial if stored is None else UNKNOWN
        capacity = receiver.spec[1]
        if type(capacity) is not int:
            self.teach_unknown_access(node['value'], outputs, node, flow, 'teach-edit')
        elif type(text) is str and len(text) > capacity:
            self.bank_status(status, 8, flow, node)
        elif type(text) is str or capacity >= TEACH_COMMENT_CAPACITY:
            constant = UNKNOWN if origin is not None and stored is None else text
            self.write(receiver, Value(constant, spec=receiver.spec), flow, node)
            self.bank_status(status, 0, flow, node)
        else:
            self.uncertain_bank_read((receiver,), status, flow, node)
