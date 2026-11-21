"""Checked drafts for shaped variable inputs and explicit position registers."""
from dataclasses import dataclass

from . import runtime as rt
from .input_template import InputTemplateError, _missing
from .runner_values import ScalarSlot, variable_location
from .storage import decode_typed, restore_value, tuple_spec


STRUCTURED_TYPES = ('ARRAY', 'JOINTPOS', *rt.RECORD_TYPES)
POSITION_TYPES = ('XYZWPR', 'XYZWPREXT', 'POSITION', 'JOINTPOS')


def supports_structure(candidate):
    spec = candidate.get('type')
    return (isinstance(spec, list) and bool(spec) and
            (candidate.get('kind') == 'variable' and spec[0] in STRUCTURED_TYPES or
             candidate.get('kind') == 'position_register' and spec[0] in POSITION_TYPES))


def _fields(container, key, spec, path, *, config_field=False):
    kind = spec[0]
    value = container[key]
    if kind in STRUCTURED_TYPES and value == {'uninitialized': True}:
        value = container[key] = _missing(spec)
    if kind == 'ARRAY':
        shape = rt.array_shape(spec)
        member = ('ARRAY', shape[1:], spec[2]) if len(shape) > 1 else spec[2]
        for index in range(shape[0]):
            yield from _fields(value, index, member, f'{path}[{index + 1}]')
    elif kind == 'JOINTPOS':
        for index in range(rt.joint_width(spec)):
            yield from _fields(value['axes'], index, ('REAL',), f'{path}[{index + 1}]')
    elif kind in rt.RECORD_TYPES:
        for name, member in rt.record_fields(spec):
            yield from _fields(value, name, member, f'{path}.{name}', config_field=kind == 'CONFIG')
    else:
        capacity = spec[1] if kind == 'STRING' else None
        yield path, ScalarSlot(container, key, (kind,), capacity, config_field)


@dataclass
class StructuredDraft:
    spec: tuple
    payload: object
    fields: list
    position_register: bool

    def checked_payload(self):
        if self.position_register:
            missing = next((path for path, slot in self.fields if slot.value is None), None)
            if missing is not None:
                raise InputTemplateError(f'Enter a value for {missing}. Position registers require complete data.')
        return _checked_payload(self.spec, self.payload, self.position_register)


def _checked_payload(spec, payload, position_register):
    try:
        with rt._numeric_scope('pythonic'):
            rt._validate_data_schema(spec)
            value = restore_value(spec, payload)
            if position_register:
                value = rt.positional_value(spec, value)
            else:
                value = rt._partial_aggregate_value(spec, value)
            return rt.snapshot_value(value)
    except (ValueError, TypeError, rt.KarelRuntimeError) as error:
        raise InputTemplateError(str(error)) from error


@dataclass(frozen=True)
class StructuredSlot:
    container: dict | list
    key: int | str
    spec: tuple
    position_register: bool = False

    def draft(self, label):
        try:
            with rt._numeric_scope('pythonic'):
                rt._validate_data_schema(self.spec)
                if self.position_register:
                    row = self.container.get(self.key)
                    payload = _missing(self.spec) if row is None else rt.snapshot_value(decode_typed(row)[1])
                else:
                    payload = rt.snapshot_value(restore_value(self.spec, self.container[self.key]))
        except (ValueError, TypeError, rt.KarelRuntimeError) as error:
            raise InputTemplateError(str(error)) from error
        root = [payload]
        fields = list(_fields(root, 0, self.spec, label))
        return StructuredDraft(self.spec, root[0], fields, self.position_register)

    def replace(self, payload):
        value = _checked_payload(self.spec, payload, self.position_register)
        if self.position_register:
            row = self.container.get(self.key)
            schema = row['type'] if row is not None else list(self.spec)
            value = {'type': schema, 'value': value}
        self.container[self.key] = value


def structured_slot(context, candidate, binding):
    """Resolve one discovered aggregate or an explicitly grouped bank entry."""
    if not supports_structure(candidate) or not binding.get('context_pointer') or binding.get('status') == 'unmapped':
        raise InputTemplateError('This input needs a shaped binding. Review Requirements or Edit context.')
    try:
        spec = tuple_spec(candidate['type'])
        if candidate['kind'] == 'variable':
            container, key, actual, _ = variable_location(context, candidate)
            same_array = (spec[0] == actual[0] == 'ARRAY'
                          and rt.array_shape(spec) == rt.array_shape(actual)
                          and spec[2:] == actual[2:])
            if spec != actual and not same_array:
                raise InputTemplateError('The saved aggregate differs from the discovered type.')
            return StructuredSlot(container, key, actual)

        service, section, key = binding['context_pointer'][1:].split('/')
        if service != 'positions' or section != 'values' or candidate.get('group') is None:
            raise InputTemplateError('Choose an explicitly grouped position register binding.')
        values = context['positions'].setdefault('values', {})
        if key in values:
            spec, _ = decode_typed(values[key])
        if spec[0] not in POSITION_TYPES:
            raise InputTemplateError('This register does not have a supported pose or joint schema.')
        return StructuredSlot(values, key, spec, position_register=True)
    except (IndexError, KeyError, TypeError, ValueError, rt.KarelRuntimeError) as error:
        if isinstance(error, InputTemplateError):
            raise
        raise InputTemplateError('The saved receiver cannot be edited as structured data. Review Edit context.') from error
