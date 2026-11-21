"""Resolve editable scalar inputs in a prepared execution context."""
from dataclasses import dataclass
import json
from math import prod

from . import runtime as rt
from .input_template import InputTemplateError, _path_record_slot
from .storage import array_state_values, restore_value, tuple_spec


SCALAR_TYPES = {'BOOLEAN', 'BYTE', 'SHORT', 'INTEGER', 'REAL', 'STRING'}
EDITABLE_KINDS = {'variable', 'numeric_register', 'string_register', 'port'}


def input_key(row):
    """Identify a variable input by its saved root as well as its display path."""
    key = row.get('kind'), row.get('program'), row.get('path')
    root = row.get('root_path')
    return (*key, root) if key[0] == 'variable' and isinstance(root, str) else key


def scalar_options(candidate):
    """Return the input's supported scalar type names, in display order."""
    if candidate.get('kind') not in EDITABLE_KINDS:
        return ()
    specs = candidate.get('type_options') or [candidate.get('type')]
    if not isinstance(specs, list):
        return ()
    return tuple(spec[0] for spec in specs if isinstance(spec, list) and spec
                 and isinstance(spec[0], str) and spec[0] in SCALAR_TYPES)


@dataclass(frozen=True)
class ScalarSlot:
    container: dict | list
    key: str | int
    options: tuple
    capacity: int | None = None
    config_field: bool = False

    @property
    def value(self):
        value = self.container.get(self.key) if isinstance(self.container, dict) else self.container[self.key]
        return None if isinstance(value, dict) else value

    def set_text(self, kind, text):
        if kind not in self.options:
            raise InputTemplateError('Choose a supported type for this input.')
        if kind == 'STRING':
            if len(text) > self.capacity:
                raise InputTemplateError(f'STRING input must fit in {self.capacity} ASCII characters.')
            value, spec = text, ('STRING', self.capacity)
        else:
            try:
                value = json.loads(text)
            except (ValueError, RecursionError) as error:
                raise InputTemplateError(f'Enter a {kind} value.') from error
            spec = (kind,)
        try:
            with rt._numeric_scope('pythonic'):
                checked = rt.checked(spec, value)
                if self.config_field:
                    rt.ConfigFieldReference(spec, self.container, self.key).validate(value)
        except rt.KarelRuntimeError as error:
            raise InputTemplateError(str(error)) from error
        if checked is rt.UNINITIALIZED:
            raise InputTemplateError(f'{value} is the {kind} uninitialized marker. Enter an initialized value.')
        self.container[self.key] = checked


def _field_key(payload, name):
    matches = [key for key in payload if key.upper() == name] if isinstance(payload, dict) else []
    if len(matches) != 1:
        raise InputTemplateError('The record field is unavailable or ambiguous. Review Edit context.')
    return matches[0]


def _array_slot(payload, spec, indices):
    """Resolve an element or a nested row inside saved ARRAY storage."""
    shape = rt.array_shape(spec)
    if not 1 <= len(indices) <= len(shape) or any(type(index) is not int or not 1 <= index <= size
                                                 for index, size in zip(indices, shape)):
        raise InputTemplateError('The input ARRAY index is outside its saved shape.')
    if len(shape) > 1 and isinstance(payload, list) and len(payload) == prod(shape):
        try:
            # With singleton dimensions, a flat list of record/axis values may
            # also look like nested rows. Use the state decoder's same fallback.
            with rt._numeric_scope('pythonic'):
                for item in array_state_values(shape, payload):
                    restore_value(spec[2], item)
        except (ValueError, rt.KarelRuntimeError):
            if len(indices) < len(shape):
                raise InputTemplateError('A row in legacy flat storage requires Edit context.')
            offset = 0
            for index, size in zip(indices, shape):
                offset = offset * size + index - 1
            return payload, offset
    for index in indices[:-1]:
        payload = payload[index - 1]
    return payload, indices[-1] - 1


def variable_location(context, candidate):
    """Resolve the actual JSON receiver and its concrete schema."""
    row = next((row for row in context.get('variables', ())
                if row['program'].upper() == candidate['program'] and row['path'].upper() == candidate['root_path']), None)
    if row is None:
        raise InputTemplateError('The discovered variable has no saved receiver. Rediscover or review Edit context.')
    container, key = row, 'value'
    spec = tuple_spec(candidate['root_type'])
    config_field = False
    remaining = list(candidate.get('selectors', ()))
    while remaining:
        payload = container[key]
        kind, value = remaining.pop(0)
        if kind == 'field':
            container, key = payload, _field_key(payload, value)
            config_field = spec[0] == 'CONFIG'
            spec = dict(rt.record_fields(spec))[value]
        elif kind == 'index' and spec[0] == 'ARRAY':
            shape = rt.array_shape(spec)
            tail = remaining[:len(shape) - 1]
            if any(selector != 'index' for selector, _ in tail):
                raise InputTemplateError('The array selector needs its complete index.')
            indices = [value, *(index for _, index in tail)]
            container, key = _array_slot(payload, spec, indices)
            del remaining[:len(shape) - 1]
            spec = spec[2] if len(indices) == len(shape) else ('ARRAY', shape[len(indices):], spec[2])
        elif kind == 'index' and spec[0] == 'JOINTPOS':
            if type(value) is not int or not 1 <= value <= rt.joint_width(spec):
                raise InputTemplateError('The joint axis is outside its saved width.')
            axes = next((payload[name] for name in ('axes', 'joints', 'values') if name in payload), None) if isinstance(payload, dict) else payload
            container, key, spec = axes, value - 1, ('REAL',)
        elif kind == 'index' and spec[0] == 'PATH':
            container, key, spec = _path_record_slot(payload, spec, value)
        else:
            raise InputTemplateError('This selector requires Edit context.')
    if (type(key) is int and not isinstance(container, list)) or (type(key) is str and not isinstance(container, dict)):
        raise InputTemplateError('The saved receiver has no initialized shape. Review Edit context.')
    return container, key, spec, config_field


def _bank_slot(context, candidate, binding, options):
    # Preparation computes the address using the existing key spellings.
    service, section, *address = binding['context_pointer'][1:].split('/')
    expected = {'numeric_register': 'numeric', 'string_register': 'strings', 'port': 'ports'}[candidate['kind']]
    if service != expected or section != 'values' or len(address) != (2 if service == 'ports' else 1):
        raise InputTemplateError('This input needs a current service binding. Rediscover the inputs.')
    bank = context[service]
    if service == 'ports' and bank.get('physical_inputs'):
        raise InputTemplateError('Edit the port configuration or physical samples in Edit context.')
    values = bank.setdefault('values', {})
    if service == 'ports':
        values = values.setdefault(address[0], {})
    return ScalarSlot(values, address[-1], options, bank.get('capacity', 254) if service == 'strings' else None)


def scalar_slot(context, candidate, binding):
    """Locate a single persisted scalar without replacing its enclosing value."""
    options = scalar_options(candidate)
    if not options or not binding.get('context_pointer') or binding.get('status') == 'unmapped':
        raise InputTemplateError('This input needs a scalar binding. Review Requirements or Edit context.')
    try:
        if candidate['kind'] == 'variable':
            container, key, spec, config_field = variable_location(context, candidate)
            if (spec[0],) != options:
                raise InputTemplateError('The selected scalar does not match its discovered type.')
            return ScalarSlot(container, key, options, spec[1] if spec[0] == 'STRING' else None, config_field)
        return _bank_slot(context, candidate, binding, options)
    except (IndexError, KeyError, TypeError, ValueError, rt.KarelRuntimeError) as error:
        if isinstance(error, InputTemplateError):
            raise
        raise InputTemplateError('The saved receiver cannot be edited as a scalar. Review Edit context.') from error
