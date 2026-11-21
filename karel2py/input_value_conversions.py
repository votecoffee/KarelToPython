"""Bounded storage and record conversion facts for generated input discovery."""

from dataclasses import dataclass
from itertools import product
import math

from . import runtime as rt
from .extended import _variable_compatible
from .storage import tuple_spec


UNKNOWN = object()
SCALARS = {'INTEGER', 'BYTE', 'SHORT', 'REAL', 'BOOLEAN', 'STRING', 'NUMERIC'}


@dataclass
class Value:
    constant: object = UNKNOWN
    complete: bool = True
    spec: object = None
    facts: object = None
    path_records: tuple | None = None
    uninitialized: bool = False  # Positive proof, separate from incomplete knowledge.


def array_dimensions(spec):
    dimensions = []
    while spec and spec[0] == 'ARRAY':
        dimensions.extend(spec[1] if type(spec[1]) is list else [spec[1]])
        spec = spec[2]
    return dimensions, spec


def stored_value(spec, value):
    """Availability and schema facts after storage."""
    constant, complete = value.constant, value.complete
    uninitialized = value.uninitialized and spec == value.spec
    if spec == ['REAL'] and type(constant) is int:
        constant = float(constant) if constant.bit_length() <= 64 else UNKNOWN
    if spec and spec[0] == 'STRING' and type(constant) is str:
        capacity = spec[1] if len(spec) > 1 else None
        if type(capacity) is not int or len(constant) > capacity:
            constant = UNKNOWN
    elif spec and spec[0] in ('INTEGER', 'BYTE', 'SHORT') and type(constant) is float:
        if spec == ['SHORT'] and math.isfinite(constant) and math.trunc(constant) == 32767:
            complete, uninitialized = False, True
        constant = UNKNOWN
    if spec == ['SHORT'] and constant == 32767:
        complete, uninitialized = False, True
    if spec == ['SHORT'] and value.constant is UNKNOWN and value.spec not in (['SHORT'], ['BYTE']):
        complete = False
    if spec and spec[0] == 'ARRAY' and value.spec and value.spec[0] == 'ARRAY':
        _, target = array_dimensions(spec)
        _, source = array_dimensions(value.spec)
        if target == ['SHORT'] and source != target:
            complete = False
    return Value(constant, complete, spec, uninitialized=uninitialized)


def _indices(shape):
    for coordinates in product(*(range(1, size + 1) for size in shape)):
        yield tuple(('index', index) for index in coordinates)


def _children(spec):
    """Yield relative logical addresses and runtime slots of a concrete value."""
    if spec[0] in rt.RECORD_TYPES:
        for name, field in rt.record_fields(spec):
            yield (('field', name),), name, field
    elif spec[0] == 'JOINTPOS':
        for index in range(spec[1]):
            yield (('index', index + 1),), index, ('REAL',)
    elif spec[0] == 'ARRAY':
        for index, address in enumerate(_indices(rt.array_shape(spec))):
            yield address, index, spec[2]


def _leaf_specs(spec, path):
    if spec[0] in SCALARS:
        yield path, spec
        return
    for parts, _, child in _children(spec):
        yield from _leaf_specs(child, path + parts)


def _materialize(spec, path, fact_at):
    if spec[0] in SCALARS:
        fact = fact_at(path, spec)
        if fact.uninitialized:
            return rt.UNINITIALIZED
        return fact.constant if fact.complete else UNKNOWN
    values = []
    for parts, slot, child in _children(spec):
        member = _materialize(child, path + parts, fact_at)
        if member is UNKNOWN:
            return UNKNOWN
        values.append((slot, member))
    result = rt.initial_value(spec)
    for slot, member in values:
        result.values[slot] = member
    return result


def _const_facts(spec, path, value, output):
    if spec[0] in SCALARS:
        missing = value is rt.UNINITIALIZED
        exact = not missing and value is not rt.UNKNOWN_BYTE
        output[path] = Value(value if exact else UNKNOWN, exact, list(spec), uninitialized=missing)
        return
    for parts, slot, child in _children(spec):
        _const_facts(child, path + parts, value.values[slot], output)


def _cast_scalar(expected, actual, source):
    schema = list(expected)
    if source.uninitialized:
        return Value(complete=False, spec=schema, uninitialized=True)
    if not source.complete or source.constant is UNKNOWN:
        return stored_value(schema, Value(complete=source.complete, spec=list(actual)))
    value = rt.checked(actual, source.constant)
    if expected != actual:
        if rt.real_integral_kind(expected, actual):
            value = rt.real_integral_value(expected, value)
        value = rt.checked(expected, value)
    if value is rt.UNINITIALIZED:
        return Value(complete=False, spec=schema, uninitialized=True)
    return Value(value, spec=schema)


def variable_transfer_policy(target, source):
    """Classify checked ordinary transfers without querying contextual services."""
    expected, actual = tuple_spec(target), tuple_spec(source)
    try:
        rt._validate_data_schema(expected)
        rt._validate_data_schema(actual)
    except rt.KarelRuntimeError:
        return None
    arrays = expected[0] == actual[0] == 'ARRAY'
    if arrays and rt.array_dimensions(expected) != rt.array_dimensions(actual):
        return None
    first, second = (rt.array_leaf_spec(expected), rt.array_leaf_spec(actual)) if arrays else (expected, actual)
    with rt._numeric_scope('pythonic'):
        if (_variable_compatible(first, second, numeric=True) or rt.config_word_kind(first, second)
                or rt.positional_conversion_kind(first, second) or rt.record_schema_kind(first, second)):
            return 'data'
        if (rt.kinematic_record_kind(first, second)
                or rt.kinematic_array_kind(('ARRAY', 1, first), ('ARRAY', 1, second))):
            return 'model'
    return 'rejected'


def convert_value_facts(target, value, *, tick):
    """Convert detached data, retaining proof for independent fields."""
    if target == value.spec:
        return value, False
    output = {}
    source_facts = {(): value} if value.spec[0] in SCALARS else value.facts or {}
    unproven = False

    def fact_at(path, schema):
        return source_facts.get(path, Value(complete=value.complete, spec=list(schema)))

    def project(expected, actual, path):
        nonlocal unproven
        tick()
        if expected == actual:
            for address, schema in _leaf_specs(expected, path):
                tick()
                output[address] = _cast_scalar(schema, schema, fact_at(address, schema))
        elif expected[0] == actual[0] == 'STRUCTURE':
            fields = dict(rt.record_fields(actual))
            for name, field in rt.record_fields(expected):
                project(field, fields[name], path + (('field', name),))
        elif expected[0] == actual[0] == 'ARRAY':
            target_leaf, source_leaf = rt.array_leaf_spec(expected), rt.array_leaf_spec(actual)
            for address in _indices(rt.array_dimensions(expected)):
                project(target_leaf, source_leaf, path + address)
        elif expected[0] in SCALARS and actual[0] in SCALARS:
            output[path] = _cast_scalar(expected, actual, fact_at(path, actual))
        else:
            convert_component(expected, actual, path)

    def convert_component(expected, actual, path):
        nonlocal unproven
        positional = rt.positional_conversion_kind(expected, actual)
        word = rt.config_word_kind(expected, actual)
        leaves = [fact_at(address, schema) for address, schema in _leaf_specs(actual, path)]
        available = all(fact.complete for fact in leaves)
        missing = any(fact.uninitialized for fact in leaves)
        if positional == 'joint_width':
            known = _materialize(actual, path, fact_at)
            if known is not UNKNOWN:
                _const_facts(expected, path, rt.convert_joint_width(expected, known), output)
                return
            for fact in leaves:
                if fact.uninitialized:
                    rt.require(rt.UNINITIALIZED)
            if any(fact.complete and fact.constant is not UNKNOWN and fact.constant != 0.
                   for fact in leaves[expected[1]:]):
                raise rt.KarelRuntimeError('Joint width narrowing requires zero discarded axes')
            unproven |= not available
            for axis in range(expected[1]):
                fact = leaves[axis] if axis < len(leaves) else Value(
                    0. if available else UNKNOWN, available, ['REAL'],
                )
                output[path + (('index', axis + 1),)] = fact
            return

        known = _materialize(actual, path, fact_at)
        if known is not UNKNOWN:
            if word:
                converted = rt._config_word_data(expected, actual, known)
            elif positional == 'cartesian':
                converted = rt.convert_position(expected, known)
            else:
                converted = rt.convert_record_schema(expected, known, source_spec=actual)
            _const_facts(expected, path, converted, output)
            return

        # Unknown data can still prove compatible fields elsewhere in the record.
        requires_complete = positional == 'cartesian' or expected == ('POSITION',)
        unproven |= requires_complete and not available
        for address, schema in _leaf_specs(expected, path):
            # CONFIG data casts preserve missing input, and an encoded SHORT
            # can introduce the missing sentinel even with complete input.
            complete = available and not (word and expected == ('SHORT',))
            output[address] = Value(complete=complete, spec=list(schema), uninitialized=bool(word and missing))

    with rt._numeric_scope('pythonic'):
        project(tuple_spec(target), tuple_spec(value.spec), ())
    if target[0] in SCALARS:
        return output[()], unproven
    return Value(complete=all(fact.complete for fact in output.values()), spec=target, facts=output), unproven
