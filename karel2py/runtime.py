"""Offline compatibility runtime for the implemented source subset.

Robot models, storage backends and other services require explicit caller data.
Generated modules use this package's standard-library-only runtime modules.
"""
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from copy import deepcopy
from datetime import datetime
import inspect
import math
import re
import struct
import time


# Keep the previous conservative contracts available for regression tests. Public
# translation selects Pythonic behavior explicitly; strict mode is not released.
_numeric_mode = ContextVar('karel2py_numeric_mode', default='strict')


@contextmanager
def _numeric_scope(mode):
    if mode not in ('pythonic', 'strict'):
        raise ValueError('Unknown numeric mode')
    token = _numeric_mode.set(mode)
    try:
        yield
    finally:
        _numeric_mode.reset(token)


def _with_numeric_mode(mode):
    def decorate(function):
        @wraps(function)
        def call(*args, **kwargs):
            with _numeric_scope(mode):
                return function(*args, **kwargs)
        return call
    return decorate


def _pythonic():
    return _numeric_mode.get() == 'pythonic'


class KarelRuntimeError(Exception):
    def __init__(self, message, line=None):
        self.line = line
        super().__init__((f"KAREL line {line}: " if line else '') + message)


class KarelAbort(Exception):
    """Intentional offline termination, distinct from an invalid runtime value."""
    def __init__(self, line=None):
        self.line = line
        super().__init__((f'KAREL line {line}: ' if line else '') +
                         'ABORT terminated this offline instance; create a new Program to restart')


class _Uninitialized:
    def __deepcopy__(self, memo): return self
    def __repr__(self):
        return 'UNINITIALIZED'


UNINITIALIZED = _Uninitialized()


class _UnknownByte:
    def __deepcopy__(self, memo): return self
    def __repr__(self): return 'UNKNOWN_BYTE'


UNKNOWN_BYTE = _UnknownByte()
INTEGER = ('INTEGER',)
BOOLEAN = ('BOOLEAN',)
REAL = ('REAL',)
UNARY_TRIG_FUNCTIONS = ('SIN', 'COS', 'TAN', 'ASIN', 'ACOS')
BYTE = ('BYTE',)
SHORT = ('SHORT',)
JOINT_TYPE_NAMES = ('JOINTPOS',) + tuple('JOINTPOS' + str(n) for n in range(1, 10))


def joint_width(spec):
    if (not isinstance(spec, tuple) or len(spec) != 2 or spec[0] != 'JOINTPOS'
            or type(spec[1]) is not int or not 1 <= spec[1] <= 9):
        raise KarelRuntimeError('JOINTPOS type requires an axis count in 1..9')
    return spec[1]


def joint_spec(name):
    if name not in JOINT_TYPE_NAMES: raise KarelRuntimeError('Unsupported JOINTPOS type name')
    return ('JOINTPOS', 9 if name == 'JOINTPOS' else int(name[-1]))
DATA_RECORD_TYPES = ('XYZWPR', 'CONFIG', 'VECTOR', 'POSITION', 'XYZWPREXT')
POSITIONAL_VALUE_TYPES = tuple(name for name in DATA_RECORD_TYPES if name != 'VECTOR') + ('JOINTPOS',)
POSITION_READ_ONLY_FIELDS = ('NORMAL', 'ORIENT', 'APPROACH')
POSITION_AXIS_FUNCTIONS = {'APPROACH': 2, 'ORIENT': 1}
RECORD_TYPES = ('STRUCTURE', *DATA_RECORD_TYPES)
DATA_RECORD_FIELDS = {
    'VECTOR': tuple((name, REAL) for name in ('X', 'Y', 'Z')),
    'CONFIG': tuple((name, INTEGER) for name in ('CFG_TURN_NO1', 'CFG_TURN_NO2', 'CFG_TURN_NO3'))
              + tuple((name, BOOLEAN) for name in ('CFG_FLIP', 'CFG_LEFT', 'CFG_UP', 'CFG_FRONT')),
    'XYZWPR': tuple((name, REAL) for name in ('X', 'Y', 'Z', 'W', 'P', 'R')) + (('CONFIG_DATA', ('CONFIG',)),),
    'XYZWPREXT': tuple((name, REAL) for name in ('X', 'Y', 'Z', 'W', 'P', 'R'))
                + (('CONFIG_DATA', ('CONFIG',)),) + tuple((name, REAL) for name in ('EXT1', 'EXT2', 'EXT3')),
    'POSITION': tuple((name, ('VECTOR',)) for name in (*POSITION_READ_ONLY_FIELDS, 'LOCATION'))
                + (('CONFIG_DATA', ('CONFIG',)),),
}


def record_fields(spec):
    if spec[0] in DATA_RECORD_TYPES:
        if len(spec) != 1: raise KarelRuntimeError('Data records do not accept group/frame metadata')
        return DATA_RECORD_FIELDS[spec[0]]
    if spec[0] == 'STRUCTURE': return spec[2]
    raise KarelRuntimeError('Expected a supported record type')


def validate_config_contents(value, line=None):
    """Keep the conservative turn-number range even across aggregate copies."""
    if isinstance(value, Structure):
        if value.spec[0] == 'CONFIG':
            for name, spec in record_fields(value.spec):
                field = value.values[name]
                if spec == INTEGER:
                    if not -8 <= integer(field, line) <= 7:
                        raise KarelRuntimeError('CONFIG turn numbers are limited to -8..7 by the prototype', line)
                else: boolean(field, line)
        else:
            for field in value.values.values(): validate_config_contents(field, line)
    elif isinstance(value, Array):
        for item in value.values: validate_config_contents(item, line)
    elif isinstance(value, JointPosition):
        if len(value.values) != joint_width(value.spec): raise KarelRuntimeError('Malformed joint axis values', line)
        for axis in value.values: real(axis, line)
_REAL_MANUAL_MIN = Fraction(Decimal('1.175494E-38'))
_REAL_MANUAL_MAX = Fraction(Decimal('3.4028236E+38'))
_REAL_BINARY32_MIN_NORMAL = Fraction(1, 2 ** 126)


def require(value, line=None):
    if value is UNINITIALIZED:
        raise KarelRuntimeError('Read of an uninitialized value', line)
    if value is UNKNOWN_BYTE:
        raise KarelRuntimeError('Initial BYTE contents are unknown; assign before reading', line)
    return value


def integer(value, line=None):
    require(value, line)
    if type(value) is not int:
        raise KarelRuntimeError('Expected INTEGER', line)
    if not -2147483648 <= value <= 2147483647:
        raise KarelRuntimeError('INTEGER overflow', line)
    return value


def boolean(value, line=None):
    require(value, line)
    if type(value) is not bool:
        raise KarelRuntimeError('Expected BOOLEAN', line)
    return value


def _real_fraction(value, line=None):
    """Convert a rational result under the active generated-program policy."""
    if _pythonic():
        try:
            return real(float(value), line)
        except OverflowError:
            raise KarelRuntimeError('REAL overflow', line) from None
    magnitude = abs(value)
    if magnitude > _REAL_MANUAL_MAX:
        raise KarelRuntimeError('REAL overflow', line)
    if magnitude < _REAL_MANUAL_MIN:
        return 0.0  # The manual describes values below this threshold as zero.
    if magnitude < _REAL_BINARY32_MIN_NORMAL:
        raise KarelRuntimeError('REAL subnormal boundary needs controller validation', line)
    try:
        candidate = struct.unpack('>f', struct.pack('>f', float(value)))[0]
    except (OverflowError, struct.error):
        raise KarelRuntimeError('REAL binary32 boundary needs controller validation', line) from None
    if not math.isfinite(candidate) or Fraction(candidate) != value:
        raise KarelRuntimeError('REAL rounding is not validated; exact binary32 values only', line)
    return candidate


def real(value, line=None):
    require(value, line)
    if type(value) is int:
        value = integer(value, line)
    elif type(value) is not float or not math.isfinite(value):
        raise KarelRuntimeError('Expected finite REAL or INTEGER', line)
    if _pythonic(): return float(value)
    return _real_fraction(Fraction(value), line)


def real_literal(text, line=None):
    if _pythonic():
        try:
            value = float(text)
        except (ValueError, OverflowError):
            raise KarelRuntimeError('Invalid REAL literal', line) from None
        if not math.isfinite(value): raise KarelRuntimeError('REAL overflow', line)
        return value
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise KarelRuntimeError('Invalid REAL literal', line) from None
    if not value.is_finite():
        raise KarelRuntimeError('Non-finite REAL literal', line)
    # Compare before constructing potentially huge powers in an exact fraction.
    magnitude = value.copy_abs()
    if magnitude > Decimal('3.4028236E+38'):
        raise KarelRuntimeError('REAL overflow', line)
    if magnitude < Decimal('1.175494E-38'): return 0.0
    return _real_fraction(Fraction(value), line)


def ascii_string(value, line=None):
    require(value, line)
    if type(value) is not str or not value.isascii():
        raise KarelRuntimeError('Only ASCII STRING values are supported', line)
    return value


def array_shape(spec):
    """Preserve the original one-dimensional type format; tuples hold higher ranks."""
    return spec[1] if isinstance(spec[1], tuple) else (spec[1],)


def array_identity(spec):
    """An optional fourth component identifies a declared named ARRAY type."""
    if len(spec) == 3: return None
    if len(spec) != 4 or type(spec[3]) is not str or not spec[3] or not spec[3].isascii():
        raise KarelRuntimeError('Invalid named ARRAY type specification')
    return spec[3]


def array_dimensions(spec):
    """Logical dimensions across separately named ARRAY components."""
    dimensions = []
    while spec[0] == 'ARRAY':
        dimensions.extend(array_shape(spec))
        spec = spec[2]
    return tuple(dimensions)


def array_leaf_spec(spec):
    while spec[0] == 'ARRAY': spec = spec[2]
    return spec


def indexed_type(spec, count):
    """Full elements or a prefix ending at a separately named ARRAY boundary."""
    if type(count) is not int or count < 1:
        raise KarelRuntimeError('ARRAY requires at least one subscript')
    while spec[0] == 'ARRAY':
        width = len(array_shape(spec))
        if count < width:
            raise KarelRuntimeError('ARRAY requires all subscripts through a declared type boundary')
        count -= width
        spec = spec[2]
        if count == 0:
            if spec[0] == 'ARRAY' and array_identity(spec) is None:
                raise KarelRuntimeError('A subarray requires a separately named ARRAY type')
            return spec
    raise KarelRuntimeError('Too many ARRAY subscripts')


def parameter_accepts(formal, actual):
    """Compare formal types; None capacity is inherited from caller storage."""
    if formal[0] != actual[0]: return False
    if formal[0] == 'STRING':
        return formal[1] is None or formal[1] == actual[1]
    if formal[0] == 'ARRAY':
        formal_name, actual_name = array_identity(formal), array_identity(actual)
        if formal_name is not None: return formal_name == actual_name and formal == actual
        # An explicit named component must retain its identity. A flat generic
        # interface instead checks logical rank and the terminal element type.
        if formal[2][0] == 'ARRAY':
            formal_shape, actual_shape = array_shape(formal), array_shape(actual)
            elements_match = parameter_accepts(formal[2], actual[2])
        else:
            formal_shape, actual_shape = array_dimensions(formal), array_dimensions(actual)
            elements_match = parameter_accepts(formal[2], array_leaf_spec(actual))
        return (elements_match and len(formal_shape) == len(actual_shape) and
                all(a is None or a == b for a, b in zip(formal_shape, actual_shape)))
    return formal == actual


def checked(spec, value, line=None):
    if spec[0] in ('FILE','PATH','QUEUE_TYPE'):
        if spec[0]=='FILE' and isinstance(value,FileHandle): return value
        if not hasattr(value,'spec') or value.spec!=spec: raise KarelRuntimeError('Resource type mismatch',line)
        if spec[0]=='PATH': return value.clone()
        raise KarelRuntimeError('QUEUE_TYPE cannot be copied; pass its reference',line)
    if spec[0] == 'INTEGER':
        value = integer(value, line)
        if value == 2147483647:
            raise KarelRuntimeError('INTEGER storage excludes MAXINT (2147483647); special-state behavior needs validation', line)
        return value
    if spec[0] == 'BYTE':
        value = integer(value, line)
        if not 0 <= value <= 255:
            raise KarelRuntimeError('BYTE value outside 0..255', line)
        return value
    if spec[0] == 'SHORT':
        value = integer(value, line)
        if not -32768 <= value <= 32767:
            raise KarelRuntimeError('SHORT value outside -32768..32767 (32767 is uninitialized)', line)
        return UNINITIALIZED if value == 32767 else value
    if spec[0] == 'BOOLEAN':
        return boolean(value, line)
    if spec[0] == 'REAL':
        return real(value, line)
    if spec[0] == 'STRING':
        return ascii_string(value, line)[:spec[1]]
    if spec[0] == 'JOINTPOS':
        count = joint_width(spec)
        if not isinstance(value, JointPosition) or value.spec != spec or len(value.values) != count:
            raise KarelRuntimeError('Joint copy requires identical declared axis count', line)
        if not fully_initialized(value):
            raise KarelRuntimeError('Joint copy requires initialized axes', line)
        result = JointPosition(spec)
        result.values[:] = [real(axis, line) for axis in value.values]
        return result
    if spec[0] == 'ARRAY':
        if not isinstance(value, Array) or value.spec != spec:
            raise KarelRuntimeError('Whole-array assignment requires identical type and size', line)
        if array_leaf_spec(spec)[0] in (*RECORD_TYPES, 'JOINTPOS') and not fully_initialized(value):
            raise KarelRuntimeError('Whole-array copying with uninitialized or unknown STRUCTURE fields needs KAREL validation', line)
        validate_config_contents(value, line)
        return value.clone()
    if spec[0] in RECORD_TYPES:
        if not isinstance(value, Structure) or value.spec != spec:
            raise KarelRuntimeError('Whole-structure assignment requires identical named type', line)
        if not fully_initialized(value):
            raise KarelRuntimeError('Whole-structure copying with uninitialized fields needs KAREL validation', line)
        validate_config_contents(value, line)
        return value.clone()
    raise KarelRuntimeError(f'Unsupported type {spec[0]}', line)


def assignment_value(value, line=None):
    """Capture a Pythonic RHS before evaluating a possibly effectful target."""
    if isinstance(value, (Array, Structure, JointPosition, PathValue)):
        return checked(value.spec, value, line)
    return require(value, line)


def scalar_leaf_count(spec, limit=32767):
    """Bound allocation accounting, including nested structure/array contents."""
    if spec[0] == 'JOINTPOS': return joint_width(spec)
    if spec[0] in RECORD_TYPES:
        count = 0
        for _, field_spec in record_fields(spec):
            count += scalar_leaf_count(field_spec, limit)
            if count > limit: return limit + 1
        return count
    if spec[0] == 'ARRAY':
        count = scalar_leaf_count(spec[2], limit)
        for dimension in array_shape(spec):
            if type(dimension) is not int or not 1 <= dimension <= 32767:
                raise KarelRuntimeError('ARRAY dimensions must be INTEGER in 1..32767')
            count *= dimension
            if count > limit: return limit + 1
        return count
    return 1


class Array:
    def __init__(self, spec):
        array_identity(spec)
        if spec[2][0] == 'ARRAY' and array_identity(spec[2]) is None:
            raise KarelRuntimeError('Nested ARRAY elements require a separately named type')
        self.spec = spec
        self.shape = array_shape(spec)
        size = 1
        if not 1 <= len(self.shape) <= 3 or not 1 <= len(array_dimensions(spec)) <= 3:
            raise KarelRuntimeError('Arrays support one through three dimensions')
        for dimension in self.shape:
            if type(dimension) is not int or not 1 <= dimension <= 32767:
                raise KarelRuntimeError('ARRAY dimensions must be INTEGER in 1..32767')
            size *= dimension
        if size > 32767:
            raise KarelRuntimeError('Prototype arrays are limited to 32767 scalar elements in total')
        if scalar_leaf_count(spec) > 32767:
            raise KarelRuntimeError('Prototype arrays are limited to 32767 scalar leaves including STRUCTURE fields')
        self.values = [initial_value(spec[2]) for _ in range(size)]

    def offset(self, index, line=None):
        indexes = index if isinstance(index, tuple) else (index,)
        if len(indexes) != len(self.shape):
            raise KarelRuntimeError(f'ARRAY requires {len(self.shape)} subscripts', line)
        offset = 0
        for number, (subscript, dimension) in enumerate(zip(indexes, self.shape), 1):
            integer(subscript, line)
            if not 1 <= subscript <= dimension:
                suffix = f' in dimension {number}' if len(self.shape) > 1 else ''
                raise KarelRuntimeError(f'Array index {subscript} outside 1..{dimension}{suffix}', line)
            offset = offset * dimension + subscript - 1
        return offset

    def snapshot(self):
        # Nested lists are an offline presentation, not a controller storage layout.
        values = [snapshot_value(value) for value in self.values]
        for dimension in reversed(self.shape[1:]):
            values = [values[start:start + dimension] for start in range(0, len(values), dimension)]
        return values

    def raw(self, index, line=None):
        return index_reference(self, index, line).raw()

    def get(self, index, line=None):
        return require(self.raw(index, line), line)

    def set(self, index, value, line=None):
        index_reference(self, index, line).set(value, line)

    def clone(self):
        result = Array(self.spec)
        result.values = [value.clone() if isinstance(value, (Array, Structure, JointPosition)) else value
                         for value in self.values]
        return result


def initial_value(spec):
    if spec[0]=='FILE': return FileHandle()
    if spec[0]=='PATH': return PathValue(spec)
    if spec[0]=='QUEUE_TYPE': return QueueValue()
    if spec[0] == 'JOINTPOS': return JointPosition(spec)
    if spec[0] == 'ARRAY': return Array(spec)
    if spec[0] in RECORD_TYPES: return Structure(spec)
    if spec[0] == 'BYTE': return UNKNOWN_BYTE
    return UNINITIALIZED


class JointPosition:
    """Opaque offline joint values; no KAREL field/index syntax is invented."""
    def __init__(self, spec):
        self.spec = spec
        self.values = [UNINITIALIZED] * joint_width(spec)

    def clone(self):
        result = JointPosition(self.spec)
        result.values[:] = self.values
        return result


def joint_values(value, axes, line=None):
    """Read explicit axes or JOINTPOS9 with zero-only unused slots."""
    if type(axes) is not int or not 1<=axes<=9:
        raise KarelRuntimeError('Joint context requires an axis count in 1..9',line)
    if not isinstance(value,JointPosition) or len(value.values)!=joint_width(value.spec):
        raise KarelRuntimeError('Malformed joint data',line)
    width=joint_width(value.spec)
    if width not in (axes,9): raise KarelRuntimeError('Joint width must match the explicit axes or use JOINTPOS9 padding',line)
    with _numeric_scope('pythonic'): values=[real(axis,line) for axis in value.values]
    if any(axis!=0. for axis in values[axes:]):
        raise KarelRuntimeError('Unused JOINTPOS9 slots must be zero for the explicit axis context',line)
    return values[:axes]


def padded_joints(value, line=None):
    """Return a complete independent nine-slot joint value."""
    if not isinstance(value,JointPosition): raise KarelRuntimeError('Expected joint data',line)
    values=joint_values(value,joint_width(value.spec),line)
    result=JointPosition(('JOINTPOS',9)); result.values[:]=values+[0.]*(9-len(values))
    return result


class Structure:
    """A named aggregate with stable storage for its individual fields."""
    def __init__(self, spec):
        self.spec = spec
        self.read_only = False
        self.types = dict(record_fields(spec))
        self.values = {name: initial_value(field_spec) for name, field_spec in self.types.items()}
        if spec[0] == 'POSITION':
            for name in POSITION_READ_ONLY_FIELDS: self.values[name].read_only = True

    def clone(self):
        result = Structure(self.spec)
        # Protection belongs to the destination's context: detached VECTOR copies
        # are writable, while POSITION's orientation children stay read-only.
        for name, value in self.values.items():
            updated = value.clone() if isinstance(value, (Array, Structure, JointPosition)) else value
            result.values[name] = replace_value(result.values[name], updated)
        return result


def fully_initialized(value):
    if value is UNINITIALIZED or value is UNKNOWN_BYTE: return False
    if isinstance(value, JointPosition): return all(fully_initialized(x) for x in value.values)
    if isinstance(value, Array): return all(fully_initialized(x) for x in value.values)
    if isinstance(value, Structure): return all(fully_initialized(x) for x in value.values.values())
    return True


def replace_value(current, updated):
    """Copy into existing aggregate storage so captured field/element aliases survive."""
    if isinstance(current, JointPosition) and isinstance(updated, JointPosition):
        current.values[:] = updated.values
        return current
    if isinstance(current, Array) and isinstance(updated, Array):
        current.values[:] = [replace_value(old, new) for old, new in zip(current.values, updated.values)]
        return current
    if isinstance(current, Structure) and isinstance(updated, Structure):
        for name, value in updated.values.items():
            current.values[name] = replace_value(current.values[name], value)
        return current
    return updated


def field_reference(value, name, line=None):
    if isinstance(value,PathValue):
        if not value.spec[2]: raise KarelRuntimeError('PATH has no PATHHEADER',line)
        return field_reference(value.data,name,line)
    if not isinstance(value, Structure):
        raise KarelRuntimeError('Expected STRUCTURE for field access', line)
    if name not in value.types:
        raise KarelRuntimeError(f'Unknown STRUCTURE field {name}', line)
    if value.read_only or value.spec[0] == 'POSITION' and name in POSITION_READ_ONLY_FIELDS:
        return ReadOnlyFieldReference(value.types[name], value.values, name, line)
    reference_type = ConfigFieldReference if value.spec[0] == 'CONFIG' else Reference
    return reference_type(value.types[name], value.values, name)


def raw_field(value, name, line=None):
    return field_reference(value, name, line).raw()


def load_field(value, name, line=None):
    return require(raw_field(value, name, line), line)


def raw_index(array, index, line=None):
    if not isinstance(array, Array):
        raise KarelRuntimeError('Expected ARRAY', line)
    return array.raw(index, line)


def load_index(array, index, line=None):
    return require(raw_index(array, index, line), line)


def store_index(array, index, value, line=None):
    if not isinstance(array, Array):
        raise KarelRuntimeError('Expected ARRAY', line)
    array.set(index, value, line)


class Reference:
    """A captured storage location; not a copy-in/copy-out parameter."""
    def __init__(self, spec, storage, key):
        self.spec, self.storage, self.key = spec, storage, key

    def raw(self):
        return self.storage[self.key]

    def set(self, value, line=None):
        updated = checked(self.spec, value, line)
        self.storage[self.key] = replace_value(self.raw(), updated)

    def clear(self):
        self.storage[self.key] = UNINITIALIZED


class ReadOnlyFieldReference(Reference):
    """Protect POSITION orientation fields and their descendants at runtime."""
    def __init__(self, spec, storage, key, line=None):
        super().__init__(spec, storage, key)
        self.line = line

    def set(self, value, line=None):
        raise KarelRuntimeError('POSITION orientation fields are read-only', self.line if line is None else line)

    def clear(self):
        raise KarelRuntimeError('POSITION orientation fields are read-only', self.line)


class ConfigFieldReference(Reference):
    """Compact CONFIG fields have a bounded turn-number storage policy."""
    def set(self, value, line=None):
        if self.spec == INTEGER and not -8 <= integer(value, line) <= 7:
            raise KarelRuntimeError('CONFIG turn numbers are limited to -8..7 by the prototype', line)
        super().set(value, line)


class StringValueReference(Reference):
    """Read-only value copy; deliberately makes no physical-capacity claim."""
    def __init__(self, value, line=None):
        value = ascii_string(value, line)
        if len(value) > 254:
            raise KarelRuntimeError('STRING value arguments are limited to 254 characters', line)
        super().__init__(('STRING', None), {'value': value}, 'value')

    def set(self, value, line=None):
        raise KarelRuntimeError('Read-only STRING value temporary cannot be written; physical capacity is unverified', line)

    def clear(self):
        raise KarelRuntimeError('Read-only STRING value temporary cannot be cleared')


def string_value_argument(value, line=None):
    if _pythonic():
        value = ascii_string(value, line)
        if len(value) > 254:
            raise KarelRuntimeError('STRING value arguments are limited to 254 characters', line)
        return Reference(('STRING', 254), {'value': value}, 'value')
    return StringValueReference(value, line)


def _reference_cells(reference):
    """Storage identity, including aggregate descendants; values are not aliases."""
    cells, seen = {(id(reference.storage), reference.key)}, set()

    def visit(value):
        if isinstance(value, PathValue):
            if id(value) in seen: return
            seen.add(id(value))
            visit(value.data)
            for node in value.nodes: visit(node)
            return
        if not isinstance(value, (Structure, Array)) or id(value) in seen: return
        seen.add(id(value))
        entries = value.values.items() if isinstance(value, Structure) else enumerate(value.values)
        for key, child in entries:
            cells.add((id(value.values), key))
            visit(child)
    visit(reference.raw())
    return cells


def unpos(source, outputs, line=None):
    """Extract offline XYZWPR data; no inferred conversion or alias write order."""
    if not isinstance(outputs, (list, tuple)) or len(outputs) != 7:
        raise KarelRuntimeError('UNPOS requires seven output references', line)
    references = [source, *outputs]
    expected = [('XYZWPR',), *(('REAL',) for _ in range(6)), ('CONFIG',)]
    for reference, spec in zip(references, expected):
        if type(reference) is not Reference or reference.spec != spec:
            raise KarelRuntimeError('UNPOS requires ordinary exact-type writable output references and XYZWPR source', line)
    pose = require(source.raw(), line)
    if (not isinstance(pose, Structure) or pose.spec != ('XYZWPR',)
            or set(pose.values) != set(dict(record_fields(('XYZWPR',))))):
        raise KarelRuntimeError('UNPOS requires a complete XYZWPR record', line)
    config = pose.values['CONFIG_DATA']
    if (not isinstance(config, Structure) or config.spec != ('CONFIG',)
            or set(config.values) != set(dict(record_fields(('CONFIG',))))):
        raise KarelRuntimeError('UNPOS requires a complete CONFIG record', line)
    values = [real(pose.values[name], line) for name in ('X', 'Y', 'Z', 'W', 'P', 'R')]
    values.append(checked(('CONFIG',), config, line))
    current_config = outputs[-1].raw()
    if (isinstance(current_config, Structure) and
            (current_config.spec != ('CONFIG',) or set(current_config.values) != set(config.values))):
        raise KarelRuntimeError('UNPOS CONFIG destination has malformed storage', line)
    occupied = set()
    for reference in references:
        cells = _reference_cells(reference)
        if occupied & cells:
            raise KarelRuntimeError('UNPOS overlapping source/output references need native write-order validation', line)
        occupied.update(cells)
    # Every input, type, protection and overlap check completed before any write.
    for reference, value in zip(outputs, values): reference.set(value, line)


def index_reference(array, index, line=None):
    if isinstance(array,PathValue):
        array.node(index,line)
        return Reference(array.node_spec,array.nodes,index-1)
    if not isinstance(array, Array):
        raise KarelRuntimeError('Expected ARRAY for indexed reference argument', line)
    indexes = index if isinstance(index, tuple) else (index,)
    try: indexed_type(array.spec, len(indexes))
    except KarelRuntimeError as exc: raise KarelRuntimeError(str(exc), line) from None
    current = array
    while True:
        width = len(current.shape)
        offset = current.offset(indexes[:width], line)
        reference = Reference(current.spec[2], current.values, offset)
        indexes = indexes[width:]
        if not indexes: return reference
        current = reference.raw()
        if not isinstance(current, Array):
            raise KarelRuntimeError('Expected nested ARRAY storage', line)


def value_argument(spec, value, line=None):
    # Each expression argument owns independent temporary storage.
    if spec[0] == 'STRING' and _pythonic():
        # Bounded alias formals retain their declared capacity for value copies.
        if len(spec) != 2 or type(spec[1]) is not int or not 1 <= spec[1] <= 254:
            raise KarelRuntimeError('STRING value capacity must be INTEGER in 1..254', line)
        value = ascii_string(value, line)
        if len(value) > 254:
            raise KarelRuntimeError('STRING value arguments are limited to 254 characters', line)
        return Reference(spec, {'value': checked(spec, value, line)}, 'value')
    if spec[0] == 'ARRAY' and _pythonic():
        if not isinstance(value, Array) or not parameter_accepts(spec, value.spec):
            raise KarelRuntimeError('ARRAY value argument requires a matching concrete type and shape', line)
        copied = _aggregate_value(value.spec, value, line)
        return Reference(copied.spec, {'value': copied}, 'value')
    if spec == ('VECTOR',):
        return Reference(spec, {'value': vector_value(value, line)}, 'value')
    if spec[0] == 'STRUCTURE':
        return Reference(spec, {'value': structure_value(spec, value, line)}, 'value')
    if spec[0] in POSITIONAL_VALUE_TYPES:
        return Reference(spec, {'value': positional_value(spec, value, line)}, 'value')
    if spec[0] not in ('INTEGER', 'BOOLEAN', 'REAL'):
        raise KarelRuntimeError('Unsupported value-parameter type', line)
    return Reference(spec, {'value': checked(spec, value, line)}, 'value')


def select_case(value, cases, has_else, line=None):
    """Return the first matching clause index; missing ELSE is an execution error."""
    value = integer(value, line)
    if type(has_else) is not bool or type(cases) not in (list, tuple) or not 1 <= len(cases) <= 1000:
        raise KarelRuntimeError('Invalid generated SELECT case table or ELSE flag', line)
    for values in cases:
        if type(values) not in (list, tuple) or not values:
            raise KarelRuntimeError('Invalid generated SELECT value list', line)
        for candidate in values: integer(candidate, line)
    for index, values in enumerate(cases):
        if value in values: return index
    if has_else: return len(cases)
    raise KarelRuntimeError('No match in CASE', line)


def _store_conversion_text(name, target, text, line):
    capacity = target.spec[1]
    if type(capacity) is not int or not 1 <= capacity <= 254:
        raise KarelRuntimeError(f'{name} requires a concrete caller STRING capacity in 1..254', line)
    if len(text) > capacity:
        text = ' ' + '*' * (capacity - 1)
    target.set(text, line)


CONFIG_TEXT_FLAGS = (('CFG_FLIP', 'N', 'F'), ('CFG_LEFT', 'R', 'L'),
                     ('CFG_UP', 'D', 'U'), ('CFG_FRONT', 'B', 'T'))
CONFIG_TEXT_INVALID = 1  # Portable parse failure, not a native controller code.


def _parse_config_text(source, line=None):
    text = ascii_string(source, line)
    if len(text) > 254: raise KarelRuntimeError('CONFIG text input is limited to 254 characters', line)
    parts = text.upper().split(',')
    if len(parts) not in (1, 4): return None
    flags = re.sub(r'\s+', '', parts[0])
    if not flags: return None
    values = {field: False for field, _, _ in CONFIG_TEXT_FLAGS}
    choices = {letter: (field, enabled) for field, off, on in CONFIG_TEXT_FLAGS
               for letter, enabled in ((off, False), (on, True))}
    seen = set()
    for letter in flags:
        if letter not in choices: return None
        field, value = choices[letter]
        if field in seen: return None
        seen.add(field); values[field] = value
    try: turns = [int(part, 10) for part in parts[1:]] if len(parts) == 4 else [0, 0, 0]
    except ValueError: return None
    if any(not -8 <= value <= 7 for value in turns): return None
    values.update(zip(('CFG_TURN_NO1','CFG_TURN_NO2','CFG_TURN_NO3'), turns))
    result = Structure(('CONFIG',)); result.values.update(values)
    return positional_value(('CONFIG',), result, line)


def config_text_conversion(name, source, target, status=None, *, line=None):
    """Portable CONFIG text conversions; no robot mask or native error mapping."""
    if not _pythonic() or name not in ('CNV_CONF_STR', 'CNV_STR_CONF'):
        raise KarelRuntimeError('Unsupported CONFIG text conversion', line)
    if type(target) is not Reference: raise KarelRuntimeError('CONFIG conversion requires ordinary writable output storage', line)
    if name == 'CNV_CONF_STR':
        spec = target.spec
        if (status is not None or type(spec) is not tuple or len(spec) != 2 or spec[0] != 'STRING'
                or type(spec[1]) is not int or not 1 <= spec[1] <= 254):
            raise KarelRuntimeError('CNV_CONF_STR requires a concrete STRING output and no status', line)
        config = positional_value(('CONFIG',), source, line)
        text = ' '.join(on if config.values[field] else off for field, off, on in CONFIG_TEXT_FLAGS)
        text += ', ' + ', '.join(str(config.values[field]) for field in ('CFG_TURN_NO1','CFG_TURN_NO2','CFG_TURN_NO3'))
        if len(text) > spec[1]: raise KarelRuntimeError('CNV_CONF_STR output capacity is too small for complete CONFIG text', line)
        target.set(text, line)
        return
    if target.spec != ('CONFIG',) or type(status) is not Reference or status.spec != INTEGER:
        raise KarelRuntimeError('CNV_STR_CONF requires CONFIG and INTEGER output references', line)
    current = target.raw(); fields = dict(record_fields(('CONFIG',)))
    if current is not UNINITIALIZED and (not isinstance(current, Structure) or current.spec != ('CONFIG',)
            or current.types != fields or type(current.values) is not dict or set(current.values) != set(fields)):
        raise KarelRuntimeError('CNV_STR_CONF CONFIG destination has malformed storage', line)
    if _reference_cells(target) & _reference_cells(status):
        raise KarelRuntimeError('CNV_STR_CONF outputs must not overlap', line)
    value = _parse_config_text(source, line)
    if value is None:
        status.set(CONFIG_TEXT_INVALID, line)
        return
    target.set(value, line)
    status.set(0, line)


TIME_MONTHS = ('JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC')
USEC_PERIOD = 120_000_000


def usec_sub(later, earlier, line=None):
    """Portable elapsed microseconds on the explicit two-minute counter ring."""
    if not _pythonic(): raise KarelRuntimeError('Microsecond timers require Pythonic mode',line)
    later, earlier = integer(later,line), integer(earlier,line)
    if not (0 <= later < USEC_PERIOD and 0 <= earlier < USEC_PERIOD):
        raise KarelRuntimeError('Microsecond counter values must be in 0..119999999',line)
    return (later-earlier) % USEC_PERIOD


def _parse_time_text(source, line=None):
    text = ascii_string(source, line)
    if len(text) > 254: raise KarelRuntimeError('Time input exceeds 254 characters', line)
    match = re.fullmatch(r'([0-9]{2})-([A-Za-z]{3})-([0-9]{4}) ([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?',text.strip())
    if not match: return 0
    day, month, year, hour, minute, second = match.groups()
    if month.upper() not in TIME_MONTHS: return 0
    year, month = int(year),TIME_MONTHS.index(month.upper())+1
    if not 1980 <= year <= 2107: return 0
    try: stamp = datetime(year,month,int(day),int(hour),int(minute),int(second or 0))
    except ValueError: return 0
    return _pack_time(stamp,line)


def _pack_time(stamp, line=None):
    if type(stamp) is not datetime or stamp.tzinfo is not None or not 1980<=stamp.year<=2107:
        raise KarelRuntimeError('Calendar time requires a naive datetime in 1980..2107',line)
    packed = ((stamp.year-1980)<<25 | stamp.month<<21 | stamp.day<<16 |
              stamp.hour<<11 | stamp.minute<<5 | stamp.second//2)
    return packed if packed < 2**31 else packed-2**32


def _unpack_time(source, line=None):
    packed = integer(source,line) & 0xffffffff
    year, month, day = 1980+(packed>>25), (packed>>21)&15, (packed>>16)&31
    hour, minute, second = (packed>>11)&31, (packed>>5)&63, (packed&31)*2
    try: return datetime(year,month,day,hour,minute,second)
    except ValueError: raise KarelRuntimeError('Packed time contains an invalid calendar date or clock field',line) from None


def _format_time_text(source, line=None):
    stamp=_unpack_time(source,line)
    year,month,day,hour,minute,second=stamp.year,stamp.month,stamp.day,stamp.hour,stamp.minute,stamp.second
    return f'{day:02d}-{TIME_MONTHS[month-1]}-{year:04d} {hour:02d}:{minute:02d}:{second:02d}'


def time_text_conversion(name, source, target, line=None):
    """Convert explicit packed time data without acquiring or setting any clock."""
    if not _pythonic(): raise KarelRuntimeError('Time text conversion requires Pythonic mode',line)
    if name not in ('CNV_STR_TIME','CNV_TIME_STR') or type(target) is not Reference:
        raise KarelRuntimeError('Time conversion requires a supported procedure and ordinary writable output',line)
    if name == 'CNV_STR_TIME':
        if target.spec != INTEGER: raise KarelRuntimeError('CNV_STR_TIME requires INTEGER output',line)
        target.set(_parse_time_text(source,line),line)
    else:
        spec = target.spec
        if (type(spec) is not tuple or len(spec) != 2 or spec[0] != 'STRING'
                or type(spec[1]) is not int or not 20 <= spec[1] <= 254):
            raise KarelRuntimeError('CNV_TIME_STR requires STRING output capacity in 20..254 for complete text',line)
        target.set(_format_time_text(source,line),line)


def conversion_procedure(name, source, *arguments, line=None):
    """Bounded pure-data conversions with one checked caller output reference."""
    output_types = {'CNV_STR_INT': 'INTEGER', 'CNV_INT_STR': 'STRING', 'CNV_STR_REAL': 'REAL',
                    'CNV_REAL_STR': 'STRING'}
    count = 3 if name in ('CNV_INT_STR', 'CNV_REAL_STR') else 1
    if name not in output_types or len(arguments) != count:
        raise KarelRuntimeError('Unsupported conversion procedure or argument count', line)
    expected = output_types[name]
    target = arguments[-1]
    if not isinstance(target, Reference) or target.spec[0] != expected:
        raise KarelRuntimeError(f'{name} requires a writable {expected} output reference', line)
    if name in ('CNV_STR_INT', 'CNV_STR_REAL'):
        text = ascii_string(source, line)
        if len(text) > 254:
            raise KarelRuntimeError(f'{name} input longer than the supported 254 characters', line)
        if _pythonic():
            try:
                value = int(text, 10) if name == 'CNV_STR_INT' else float(text)
            except ValueError:
                target.clear()
                return
            target.set(value, line)
            return
        pattern = r'[+-]?[0-9]+' if name == 'CNV_STR_INT' else r'[+-]?[0-9]+\.[0-9]+(?:E[+-][0-9]+)?'
        if re.fullmatch(pattern, text):
            # Check an explicit grammar before exact decimal parsing or integer conversion.
            value = int(text, 10) if name == 'CNV_STR_INT' else real_literal(text, line)
            target.set(value, line)
        elif re.fullmatch(r'[A-Za-z]+', text):
            target.clear()  # The documented invalid representation result.
        else:
            raise KarelRuntimeError(f'{name} text format needs validation; use the documented canonical decimal subset', line)
        return
    if name == 'CNV_REAL_STR':
        value = real(source, line)
        length, num_digits = (integer(argument, line) for argument in arguments[:-1])
        if _pythonic():
            if not 1 <= length <= 254:
                raise KarelRuntimeError('CNV_REAL_STR minimum length must be in 1..254', line)
            if not -254 <= num_digits <= 254:
                raise KarelRuntimeError('CNV_REAL_STR precision must be in -254..254', line)
            style = 'E' if num_digits < 0 else 'f'
            text = ' ' + format(value, f'.{abs(num_digits)}{style}')
            text = text.rjust(length)
        else:
            if not 0 <= num_digits <= 254:
                raise KarelRuntimeError('CNV_REAL_STR supports fixed fractional digits in 0..254; scientific/out-of-bound precision rules need validation', line)
            scaled = Fraction(value) * 10 ** num_digits
            if scaled.denominator != 1:
                raise KarelRuntimeError('CNV_REAL_STR decimal rounding is not validated; exact formatting only', line)
            digits = str(abs(scaled.numerator)).rjust(num_digits + 1, '0')
            body = digits if num_digits == 0 else digits[:-num_digits] + '.' + digits[-num_digits:]
            text = ' ' + ('-' if value < 0 else '') + body
        if not _pythonic() and not 1 <= length <= len(text):
            raise KarelRuntimeError('CNV_REAL_STR requires a positive minimum length no greater than the natural result; padding/invalid-length rules need validation', line)
        _store_conversion_text(name, target, text, line)
        return
    value = integer(source, line)
    length, base = (integer(argument, line) for argument in arguments[:-1])
    if _pythonic() and not 1 <= length <= 254:
        raise KarelRuntimeError('CNV_INT_STR minimum length must be in 1..254', line)
    if not _pythonic() and length != 1:
        raise KarelRuntimeError('CNV_INT_STR currently requires length 1; other width/validity rules need validation', line)
    if base != 0 and not 2 <= base <= 16:
        target.clear()
        return
    if base in (0, 10):
        text = ' ' + str(value)
    else:
        if not _pythonic() and base > 10:
            raise KarelRuntimeError('CNV_INT_STR bases 11..16 need validated alphabetic digit case', line)
        if not _pythonic() and value < 0:
            raise KarelRuntimeError('CNV_INT_STR negative nondecimal representation needs validation', line)
        # Nonnegative signed-32-bit values need at most 31 divisions in base 2.
        digits, remaining = [], abs(value)
        while remaining:
            remaining, digit = divmod(remaining, base)
            digits.append('0123456789ABCDEF'[digit])
        text = ' ' + ('-' if value < 0 else '') + (''.join(reversed(digits)) or '0')
    if _pythonic(): text = text.rjust(length)
    _store_conversion_text(name, target, text, line)


def uninit(value):
    if isinstance(value, JointPosition): return not fully_initialized(value)
    # Whole arrays deliberately rejected by the compiler; no guessed aggregate rule.
    if value is UNKNOWN_BYTE:
        raise KarelRuntimeError('BYTE initialization queries are not implemented')
    return value is UNINITIALIZED


def unary(op, value, line=None):
    if _pythonic() and op in ('+', '-') and isinstance(value, Structure) and value.spec == ('VECTOR',):
        result = vector_value(value, line)
        if op == '-':
            result.values = {name: real(-component, line) for name, component in result.values.items()}
        return result
    if op == 'NOT':
        if type(value) is bool:
            return not value
        return integer(~integer(value, line), line)
    if op == '-':
        if type(value) is float: return real(-real(value, line), line)
        return integer(-integer(value, line), line)
    if op == '+':
        if type(value) is float: return real(value, line)
        return integer(value, line)
    raise KarelRuntimeError(f'Unsupported unary operator {op}', line)


def vector_components(value, line=None):
    if (not isinstance(value, Structure) or value.spec != ('VECTOR',)
            or set(value.values) != {'X', 'Y', 'Z'}):
        raise KarelRuntimeError('Expected three-component VECTOR', line)
    # Read every component, including for equality; a mismatch must not hide UNINIT.
    return tuple(Fraction(real(value.values[name], line)) for name in ('X', 'Y', 'Z'))


def vector_value(value, line=None):
    """Detach a fully validated VECTOR value at argument and RETURN boundaries."""
    components = vector_components(value, line)
    result = Structure(('VECTOR',))
    result.values.update(zip(('X', 'Y', 'Z'), (float(component) for component in components)))
    return result


def structure_value(spec, value, line=None):
    """Copy a named record tree without exporting its source storage or markers."""
    if spec[0] != 'STRUCTURE':
        raise KarelRuntimeError('Named STRUCTURE value requires a declared STRUCTURE type', line)
    return _aggregate_value(spec, value, line)


def positional_value(spec, value, line=None):
    """Copy initialized exact-type positional data without conversion or context."""
    if spec[0] not in POSITIONAL_VALUE_TYPES:
        raise KarelRuntimeError('Expected a supported exact positional value type', line)
    return _aggregate_value(spec, value, line)


def array_result(spec, value, line=None):
    """Detach checked ARRAY results, retaining concrete shape and nominal types."""
    pythonic = _pythonic()
    if (not isinstance(spec, tuple) or len(spec) not in ((3, 4) if pythonic else (3,)) or spec[0] != 'ARRAY'
            or not isinstance(spec[2], tuple) or not spec[2]):
        raise KarelRuntimeError('ARRAY results require a supported ARRAY declaration', line)
    declared = array_shape(spec)
    try: identity = array_identity(spec)
    except KarelRuntimeError as exc: raise KarelRuntimeError(str(exc), line) from None
    if not pythonic and spec[:2] != ('ARRAY', None):
        raise KarelRuntimeError('ARRAY results require an unsized 1D supported element declaration', line)
    if (not 1 <= len(declared) <= 3 or
            any(size is not None and (type(size) is not int or not 1 <= size <= 32767) for size in declared) or
            identity is not None and any(size is None for size in declared)):
        raise KarelRuntimeError('ARRAY result dimensions require fixed sizes in 1..32767 or anonymous wildcards', line)
    element = spec[2]
    rank = len(declared)
    while element[0] == 'ARRAY':
        if (len(element) != 4 or type(element[3]) is not str or not element[3]
                or not element[3].isascii()):
            raise KarelRuntimeError('ARRAY result inner components require named concrete ARRAY types', line)
        shape = array_shape(element)
        rank += len(shape)
        if (not shape or rank > 3 or any(type(size) is not int or not 1 <= size <= 32767 for size in shape)
                or not isinstance(element[2], tuple) or not element[2]):
            raise KarelRuntimeError('ARRAY results require concrete named components and at most three logical dimensions', line)
        element = element[2]
    if element[0] == 'STRING':
        valid = len(element) == 2 and type(element[1]) is int and 1 <= element[1] <= 254
    elif element[0] == 'STRUCTURE':
        valid = len(element) == 3 and type(element[1]) is str and type(element[2]) is tuple
    elif element[0] == 'JOINTPOS':
        valid = len(element) == 2 and type(element[1]) is int and 1 <= element[1] <= 9
    else:
        valid = element in (INTEGER, BOOLEAN, REAL, BYTE, SHORT, *((kind,) for kind in DATA_RECORD_TYPES))
    if not valid:
        raise KarelRuntimeError('ARRAY results require supported scalar, bounded STRING, record or exact-width joint terminal elements', line)
    if (not isinstance(value, Array) or not isinstance(value.spec, tuple) or len(value.spec) not in (3, 4)
            or value.spec[0] != 'ARRAY' or value.spec[2] != spec[2]):
        raise KarelRuntimeError('ARRAY result requires matching outer storage and exact element type', line)
    try: actual_identity = array_identity(value.spec)
    except KarelRuntimeError as exc: raise KarelRuntimeError(str(exc), line) from None
    if identity is None and actual_identity is not None:
        raise KarelRuntimeError('ARRAY result requires matching anonymous outer storage and exact element type', line)
    if identity is not None and value.spec != spec:
        raise KarelRuntimeError('ARRAY result requires identical named ARRAY type and shape', line)
    shape = array_shape(value.spec)
    if (len(shape) != len(declared) or any(type(size) is not int or not 1 <= size <= 32767 for size in shape)
            or any(expected is not None and expected != actual for expected, actual in zip(declared, shape))):
        raise KarelRuntimeError('ARRAY result requires a matching concrete shape in 1..32767', line)
    return _aggregate_value(value.spec, value, line)


def _aggregate_value(spec, value, line=None):
    """Shared checked copy of a generated concrete aggregate type."""
    if scalar_leaf_count(spec) > 32767:
        raise KarelRuntimeError('Aggregate values are limited to 32767 scalar leaves by the prototype', line)

    def copy_value(expected, item):
        require(item, line)
        kind = expected[0]
        if kind == 'ARRAY':
            shape = array_shape(expected)
            count = math.prod(shape)
            if (not isinstance(item, Array) or item.spec != expected or item.shape != shape
                    or type(item.values) is not list or len(item.values) != count):
                raise KarelRuntimeError('Aggregate value ARRAY requires identical concrete type, shape and storage', line)
            result = Array(expected)
            result.values[:] = [copy_value(expected[2], child) for child in item.values]
            return result
        if kind in RECORD_TYPES:
            fields = dict(record_fields(expected))
            if (not isinstance(item, Structure) or item.spec != expected or item.types != fields
                    or type(item.values) is not dict or set(item.values) != set(fields)):
                raise KarelRuntimeError('Aggregate value record requires identical nominal type and fields', line)
            result = Structure(expected)
            for name, field_spec in fields.items():
                updated = copy_value(field_spec, item.values[name])
                result.values[name] = replace_value(result.values[name], updated)
            if kind == 'CONFIG': validate_config_contents(result, line)
            return result
        if kind == 'STRING' and len(ascii_string(item, line)) > expected[1]:
            raise KarelRuntimeError('Aggregate value STRING exceeds its declared capacity', line)
        updated = checked(expected, item, line)
        require(updated, line)
        return updated

    return copy_value(spec, value)


def vector_binary(op, left, right, line=None):
    """Checked vector algebra using the active numeric policy."""
    left_vector = isinstance(left, Structure) and left.spec == ('VECTOR',)
    right_vector = isinstance(right, Structure) and right.spec == ('VECTOR',)
    both = left_vector and right_vector
    if not (both and op in ('+', '-', '#', '@', '=', '<>')
            or left_vector != right_vector and op in ('*', '/')):
        raise KarelRuntimeError('Unsupported VECTOR operand types/operator', line)
    a = vector_components(left, line) if left_vector else Fraction(real(left, line))
    b = vector_components(right, line) if right_vector else Fraction(real(right, line))
    if _pythonic():
        a = tuple(map(float, a)) if left_vector else float(a)
        b = tuple(map(float, b)) if right_vector else float(b)

    def intermediate(value):
        if _pythonic(): return real(value, line)
        checked_value = _real_fraction(value, line)
        if Fraction(checked_value) != value:
            raise KarelRuntimeError('VECTOR intermediate underflow needs controller validation', line)
        return value

    if op in ('=', '<>'):
        return (a == b) if op == '=' else (a != b)
    if op == '@':
        products = [intermediate(x * y) for x, y in zip(a, b)]
        # The manual does not specify sum association. Validate all three possible
        # first pairs, rejecting cancellation that could hide rounding/overflow.
        if not _pythonic():
            for i, j in ((0, 1), (0, 2), (1, 2)): intermediate(products[i] + products[j])
        return real(sum(products), line) if _pythonic() else _real_fraction(sum(products), line)
    if op == '#':
        values = [intermediate(a[j] * b[k]) - intermediate(a[k] * b[j])
                  for j, k in ((1, 2), (2, 0), (0, 1))]
        if not _pythonic() and not any(values):
            raise KarelRuntimeError('VECTOR cross product requires nonzero, nonparallel operands', line)
    elif op == '+': values = [x + y for x, y in zip(a, b)]
    elif op == '-': values = [x - y for x, y in zip(a, b)]
    elif op == '*': values = [x * b for x in a] if left_vector else [a * y for y in b]
    elif left_vector:
        if b == 0: raise KarelRuntimeError('Division by zero', line)
        values = [x / b for x in a]
    else:
        if any(y == 0 for y in b): raise KarelRuntimeError('Division by zero', line)
        # Also guard the manual's reciprocal-then-multiply description, rather
        # than silently choosing a more permissive host division implementation.
        values = [a / y for y in b] if _pythonic() else [a * intermediate(1 / y) for y in b]
    components = [real(value, line) if _pythonic() else _real_fraction(value, line) for value in values]
    if not _pythonic() and op == '#' and any(value != 0 and component == 0 for value, component in zip(values, components)):
        raise KarelRuntimeError('VECTOR cross-product underflow needs controller validation', line)
    result = Structure(('VECTOR',))
    result.values.update(zip(('X', 'Y', 'Z'), components))
    return result


def _frame_parts(value, line=None):
    """Detach a proper pose; XYZWPR uses the portable Z-Y-X convention."""
    pose = frame_value(value, line)
    if pose.spec == ('POSITION',):
        return (_position_rotation(pose, line), tuple(pose.values['LOCATION'].values[axis] for axis in ('X','Y','Z')),
                pose.values['CONFIG_DATA'])

    def sin_cos(degrees):
        reduced = degrees % 360.0
        exact = {0.0: (0.0, 1.0), 90.0: (1.0, 0.0),
                 180.0: (0.0, -1.0), 270.0: (-1.0, 0.0)}
        if reduced in exact: return exact[reduced]
        angle = math.radians(reduced)
        return math.sin(angle), math.cos(angle)

    sw, cw = sin_cos(pose.values['W'])
    sp, cp = sin_cos(pose.values['P'])
    sr, cr = sin_cos(pose.values['R'])
    # Column vectors: Rz(r) Ry(p) Rx(w), then translation in the parent frame.
    rotation = ((cr*cp, cr*sp*sw-sr*cw, cr*sp*cw+sr*sw),
                (sr*cp, sr*sp*sw+cr*cw, sr*sp*cw-cr*sw),
                (-sp, cp*sw, cp*cw))
    return rotation, tuple(pose.values[field] for field in ('X','Y','Z')), pose.values['CONFIG_DATA']


def _frame_result(rotation, translation, config, line=None, *, result_type=('XYZWPR',)):
    if result_type==('XYZWPREXT',):
        source=_frame_result(rotation,translation,config,line)
        result=Structure(result_type); result.values.update(source.values); result.values.update(EXT1=0.,EXT2=0.,EXT3=0.)
        return result
    if result_type == ('POSITION',):
        result = Structure(result_type)
        for column, name in enumerate(POSITION_READ_ONLY_FIELDS):
            result.values[name].values.update(zip(('X','Y','Z'), (real(rotation[row][column], line) for row in range(3))))
        result.values['LOCATION'].values.update(zip(('X','Y','Z'), (real(value, line) for value in translation)))
        result.values['CONFIG_DATA'] = positional_value(('CONFIG',), config, line)
        return frame_value(result, line)
    if result_type != ('XYZWPR',): raise KarelRuntimeError('Unsupported frame result type', line)
    horizontal = math.hypot(rotation[0][0], rotation[1][0])
    pitch = math.atan2(-rotation[2][0], horizontal)
    if horizontal <= 1e-12:
        # Choose W=0 at either gimbal lock; the remaining rotation goes into R.
        roll, yaw = 0.0, math.atan2(-rotation[0][1], rotation[1][1])
    else:
        roll = math.atan2(rotation[2][1], rotation[2][2])
        yaw = math.atan2(rotation[1][0], rotation[0][0])

    def canonical(angle):
        degrees = math.degrees(angle)
        if degrees >= 180.0: degrees -= 360.0
        return 0.0 if degrees == 0.0 else degrees

    components = [real(component, line) for component in (*translation, canonical(roll), math.degrees(pitch), canonical(yaw))]
    result = Structure(('XYZWPR',))
    result.values.update(zip(('X','Y','Z','W','P','R'), components))
    result.values['CONFIG_DATA'] = positional_value(('CONFIG',), config, line)
    return result


def _position_rotation(position, line=None):
    """Validate the rotation of an already shape-checked POSITION."""
    columns = [tuple(position.values[name].values[axis] for axis in ('X','Y','Z')) for name in POSITION_READ_ONLY_FIELDS]
    tolerance = 1e-9
    if any(abs(math.hypot(*column)-1.0) > tolerance for column in columns):
        raise KarelRuntimeError('POSITION orientation requires unit columns', line)
    if any(abs(sum(a*b for a,b in zip(columns[i],columns[j]))) > tolerance for i,j in ((0,1),(0,2),(1,2))):
        raise KarelRuntimeError('POSITION orientation requires orthogonal columns', line)
    a,b,c = columns
    determinant = sum(a[i]*(b[j]*c[k]-b[k]*c[j]) for i,j,k in ((0,1,2),(1,2,0),(2,0,1)))
    if abs(determinant-1.0) > tolerance:
        raise KarelRuntimeError('POSITION orientation requires a right-handed basis', line)
    return tuple(zip(*columns))


def frame_value(value, line=None, *, expected=None):
    """Snapshot a complete pose and validate POSITION before later operands run."""
    if not _pythonic(): raise KarelRuntimeError('Frame values require Pythonic mode', line)
    if not isinstance(value, Structure) or value.spec not in (('XYZWPR',), ('POSITION',), ('XYZWPREXT',)):
        raise KarelRuntimeError('Frame values require POSITION or XYZWPR', line)
    if expected is not None and value.spec != expected:
        raise KarelRuntimeError('Frame value does not match its declared pose type', line)
    result = positional_value(value.spec, value, line)
    if result.spec == ('POSITION',): _position_rotation(result, line)
    return result


def convert_position(target, value, line=None):
    """Convert explicit POSITION/XYZWPR assignment values without robot context."""
    if not _pythonic(): raise KarelRuntimeError('Positional conversions require Pythonic mode', line)
    if (not isinstance(value, Structure) or target not in (('POSITION',),('XYZWPR',),('XYZWPREXT',)) or value.spec not in (('POSITION',),('XYZWPR',),('XYZWPREXT',))):
        raise KarelRuntimeError('Only POSITION/XYZWPR assignment conversions are supported', line)
    rotation, location, config = _frame_parts(value, line)
    return _frame_result(rotation, location, config, line, result_type=target)


def position_axis(name, value, line=None):
    """Detach a pose's positive Y/Z axis without granting orientation writes."""
    if not _pythonic(): raise KarelRuntimeError('Position axis queries require Pythonic mode', line)
    if name not in POSITION_AXIS_FUNCTIONS: raise KarelRuntimeError('Unsupported position axis query', line)
    rotation, _, _ = _frame_parts(value, line)
    result = Structure(('VECTOR',))
    column = POSITION_AXIS_FUNCTIONS[name]
    result.values.update(zip(('X','Y','Z'), (real(rotation[row][column], line) for row in range(3))))
    return result


def frame_from_points(arguments, line=None):
    """Construct a right-handed frame from three/four complete poses."""
    if not _pythonic(): raise KarelRuntimeError('FRAME requires Pythonic mode', line)
    if type(arguments) not in (list, tuple) or len(arguments) not in (3, 4):
        raise KarelRuntimeError('FRAME requires three or four POSITION/XYZWPR points', line)
    points = [frame_value(value, line) for value in arguments]
    origin = points[3] if len(points) == 4 else points[0]
    locations = [tuple((point.values['LOCATION'].values if point.spec == ('POSITION',) else point.values)[field]
                       for field in ('X','Y','Z')) for point in points]

    def difference(point):
        return tuple(real(a-b, line) for a,b in zip(point, locations[0]))

    def cross(a, b):
        return tuple(real(a[j]*b[k]-a[k]*b[j], line) for j,k in ((1,2),(2,0),(0,1)))

    def unit(values, minimum, description):
        length = real(math.hypot(*values), line)
        if length == 0 or length < minimum:
            raise KarelRuntimeError('FRAME '+description, line)
        return tuple(real(value/length, line) for value in values)

    x_axis = unit(difference(locations[1]), 10.0, 'first and second points must be at least 10 mm apart')
    z_axis = unit(cross(x_axis, difference(locations[2])), 10.0, 'third point must be at least 10 mm from the first/second line')
    y_axis = unit(cross(z_axis, x_axis), 0.0, 'could not form a finite orthogonal Y axis')
    z_axis = unit(cross(x_axis, y_axis), 0.0, 'could not form a finite orthogonal Z axis')
    rotation = tuple(zip(x_axis, y_axis, z_axis))
    result_type = ('XYZWPREXT',) if any(point.spec==('XYZWPREXT',) for point in points) else ('POSITION',) if any(point.spec == ('POSITION',) for point in points) else ('XYZWPR',)
    result=_frame_result(rotation, locations[3] if len(points) == 4 else locations[0], origin.values['CONFIG_DATA'], line, result_type=result_type)
    if result_type==('XYZWPREXT',) and origin.spec==result_type:
        for key in ('EXT1','EXT2','EXT3'): result.values[key]=origin.values[key]
    return result


def frame_inverse(value, line=None):
    """Invert an explicit pose; no controller/frame discovery."""
    if not _pythonic(): raise KarelRuntimeError('Frame transforms require Pythonic mode', line)
    rotation, translation, config = _frame_parts(value, line)
    inverse = tuple(zip(*rotation))
    location = tuple(real(-sum(row[j]*translation[j] for j in range(3)), line) for row in inverse)
    result=_frame_result(inverse, location, config, line, result_type=value.spec)
    if value.spec==('XYZWPREXT',):
        for key in ('EXT1','EXT2','EXT3'): result.values[key]=value.values[key]
    return result


def frame_transform(left, right, line=None):
    """Compose two explicit poses without controller/frame discovery."""
    if not _pythonic(): raise KarelRuntimeError('Frame transforms require Pythonic mode', line)
    rotation, translation, _ = _frame_parts(left, line)
    other_rotation, other_translation, other_config = _frame_parts(right, line)
    composed = tuple(tuple(sum(rotation[i][k]*other_rotation[k][j] for k in range(3))
                           for j in range(3)) for i in range(3))
    location = tuple(real(translation[i] + sum(rotation[i][j]*other_translation[j] for j in range(3)), line)
                     for i in range(3))
    result_type = ('XYZWPREXT',) if ('XYZWPREXT',) in (left.spec,right.spec) else ('POSITION',) if ('POSITION',) in (left.spec, right.spec) else ('XYZWPR',)
    result=_frame_result(composed, location, other_config, line, result_type=result_type)
    if result_type==('XYZWPREXT',):
        source=right if right.spec==result_type else left
        for key in ('EXT1','EXT2','EXT3'): result.values[key]=source.values[key]
    return result


def checked_pose_tolerance(value):
    """Copy explicit host comparison context without inferring controller settings."""
    if value is None: return None
    message = 'pose_tolerance requires (finite location_mm >= 0, orientation_deg in 0..180, BOOLEAN check_config)'
    if type(value) not in (tuple,list) or len(value) != 3 or type(value[2]) is not bool:
        raise ValueError(message)
    if any(type(component) not in (int,float) for component in value[:2]): raise ValueError(message)
    try: location, orientation = map(float,value[:2])
    except (OverflowError,ValueError): raise ValueError(message) from None
    if not math.isfinite(location) or location < 0 or not math.isfinite(orientation) or not 0 <= orientation <= 180:
        raise ValueError(message)
    return location,orientation,value[2]


def checked_external_tolerance(value):
    if value is None: return None
    if type(value) in (int,float): value=(value,)*3
    if type(value) not in (list,tuple) or len(value)!=3 or any(type(x) not in (int,float) for x in value):
        raise ValueError('external_tolerance requires one or three finite nonnegative axis tolerances')
    result=tuple(float(x) for x in value)
    if not all(math.isfinite(x) and x>=0 for x in result): raise ValueError('External-axis tolerances must be finite and nonnegative')
    return result


def positions_close(left, right, tolerance, line=None, *, external_tolerance=None):
    """Compare explicit poses with supplied distance, rotation and CONFIG rules."""
    if not _pythonic(): raise KarelRuntimeError('Position comparison requires Pythonic mode', line)
    rotation, location, config = _frame_parts(left, line)
    other_rotation, other_location, other_config = _frame_parts(right, line)
    try: context = checked_pose_tolerance(tolerance)
    except ValueError as exc: raise KarelRuntimeError(str(exc),line) from None
    if context is None: raise KarelRuntimeError('Position comparison requires explicit Program(pose_tolerance=(location_mm, orientation_deg, check_config)) context',line)
    if any(value.spec==('XYZWPREXT',) for value in (left,right)):
        try: axes=checked_external_tolerance(external_tolerance)
        except ValueError as exc: raise KarelRuntimeError(str(exc),line) from None
        if axes is None: raise KarelRuntimeError('Extended-pose comparison requires explicit external_tolerance',line)
        if any(abs(left.values.get(key,0.)-right.values.get(key,0.))>limit for key,limit in zip(('EXT1','EXT2','EXT3'),axes)): return False
    distance = real(math.dist(location,other_location),line)
    relative = tuple(tuple(sum(rotation[k][i]*other_rotation[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    sine = math.hypot(*(relative[j][i]-relative[i][j] for i,j in ((1,2),(2,0),(0,1))))/2
    cosine = max(-1.0,min(1.0,(sum(relative[i][i] for i in range(3))-1)/2))
    # atan2 retains small deviations near both zero and 180 degrees.
    angle = real(math.degrees(math.atan2(sine,cosine)),line)
    return distance <= context[0] and angle <= context[1] and (not context[2] or config.values == other_config.values)


def binary(op, left, right, line=None):
    require(left, line)
    require(right, line)
    if op == ':': return frame_transform(left, right, line)
    if op in ('#', '@') or any(isinstance(value, Structure) and value.spec == ('VECTOR',) for value in (left, right)):
        return vector_binary(op, left, right, line)
    if op in ('=', '<>', '<', '<=', '>', '>='):
        if type(left) in (int, float) and type(right) in (int, float) and float in (type(left), type(right)):
            left, right = real(left, line), real(right, line)
        elif type(left) is not type(right) or type(left) not in (int, bool, str):
            raise KarelRuntimeError('Incompatible comparison operands', line)
        if op == '=': return left == right
        if op == '<>': return left != right
        if op == '<': return left < right
        if op == '<=': return left <= right
        if op == '>': return left > right
        return left >= right
    if op in ('AND', 'OR'):
        if type(left) is bool and type(right) is bool:
            # Both operands already evaluated by generated Python calls.
            return (left and right) if op == 'AND' else (left or right)
        integer(left, line)
        integer(right, line)
        return integer((left & right) if op == 'AND' else (left | right), line)
    if op == '+' and type(left) is str and type(right) is str:
        return ascii_string(left, line) + ascii_string(right, line)
    if op in ('+', '-', '*', '/') and (op == '/' or float in (type(left), type(right))):
        left, right = real(left, line), real(right, line)
        if not _pythonic(): left, right = Fraction(left), Fraction(right)
        if op == '+': result = left + right
        elif op == '-': result = left - right
        elif op == '*': result = left * right
        else:
            if right == 0: raise KarelRuntimeError('Division by zero', line)
            result = left / right
        return real(result, line) if _pythonic() else _real_fraction(result, line)
    integer(left, line)
    integer(right, line)
    if op == '+': return integer(left + right, line)
    if op == '-': return integer(left - right, line)
    if op == '*': return integer(left * right, line)
    if op in ('DIV', 'MOD'):
        if right == 0:
            raise KarelRuntimeError('Division by zero', line)
        if op == 'MOD':
            if not _pythonic() and (left < 0 or right < 0):
                raise KarelRuntimeError('Signed MOD is not yet validated; negative operands are blocked', line)
            return left % right
        quotient = abs(left) // abs(right)
        return integer(-quotient if (left < 0) != (right < 0) else quotient, line)
    raise KarelRuntimeError(f'Unsupported binary operator {op}', line)


def exact_trig(name, value, line=None):
    """Degree trigonometry on explicit exact subsets, without host libm rounding."""
    value = Fraction(real(value, line))
    if name in ('ASIN', 'ACOS'):
        if not -1 <= value <= 1:
            raise KarelRuntimeError(f'{name} argument must be in -1..1', line)
        inverse = ({-1: -90, Fraction(-1, 2): -30, 0: 0, Fraction(1, 2): 30, 1: 90}
                   if name == 'ASIN' else
                   {-1: 180, Fraction(-1, 2): 120, 0: 90, Fraction(1, 2): 60, 1: 0})
        if value not in inverse and _pythonic():
            function = math.asin if name == 'ASIN' else math.acos
            return real(math.degrees(function(float(value))), line)
        if value not in inverse:
            raise KarelRuntimeError(f'{name} rounding is not validated; inputs limited to -1, -0.5, 0, 0.5, 1', line)
        return float(inverse[value])
    if name not in ('SIN', 'COS', 'TAN'):
        raise KarelRuntimeError('Unsupported exact trigonometric function', line)
    # Check the documented input range before reducing periods; a large angle
    # cannot become valid just because its reduced value is small or zero.
    if not _pythonic() and not -18000 <= value <= 18000:
        raise KarelRuntimeError(f'{name} angle must be in -18000..18000 degrees', line)
    reduced = value % (180 if name == 'TAN' else 360)
    if name == 'TAN' and reduced == 90:
        raise KarelRuntimeError('TAN is undefined at odd multiples of 90 degrees', line)
    exact = ({0: 0., 30: .5, 90: 1., 150: .5, 180: 0., 210: -.5, 270: -1., 330: -.5}
             if name == 'SIN' else
             {0: 1., 60: .5, 90: 0., 120: -.5, 180: -1., 240: -.5, 270: 0., 300: .5}
             if name == 'COS' else {0: 0., 45: 1., 135: -1.})
    if reduced not in exact and _pythonic():
        function = {'SIN': math.sin, 'COS': math.cos, 'TAN': math.tan}[name]
        return real(function(math.radians(float(reduced))), line)
    if reduced not in exact:
        raise KarelRuntimeError(f'{name} rounding is not validated; angle outside the exact degree subset', line)
    return exact[reduced]


def exact_atan2(x, y, line=None):
    """Unambiguous exact bearings with KAREL coordinate order, not host atan2."""
    x, y = real(x, line), real(y, line)
    if x == 0 and y == 0:
        raise KarelRuntimeError('ATAN2 is undefined at the origin', line)
    if _pythonic(): return real(math.degrees(math.atan2(y, x)), line)
    if x < 0 or y < 0:
        raise KarelRuntimeError('ATAN2 negative-coordinate return range needs validation; nonnegative coordinates only', line)
    # No division, squares or host trig: axis and positive diagonal identities
    # remain exact even when intermediate ratios/products would overflow.
    if y == 0: return 0.
    if x == 0: return 90.
    if x == y: return 45.
    raise KarelRuntimeError('ATAN2 rounding is not validated; exact axes and positive diagonal only', line)


def builtin(name, arguments, line=None):
    if name in POSITION_AXIS_FUNCTIONS:
        if len(arguments) != 1: raise KarelRuntimeError(name+' requires one pose', line)
        return position_axis(name, arguments[0], line)
    if name == 'FRAME': return frame_from_points(arguments, line)
    if name == 'INV':
        if len(arguments) != 1: raise KarelRuntimeError('INV requires exactly one argument', line)
        return frame_inverse(arguments[0], line)
    if name == 'POS' and _pythonic():
        if len(arguments) != 7: raise KarelRuntimeError('POS requires exactly seven arguments', line)
        components = [real(value, line) for value in arguments[:6]]
        for field, value, limit in zip(('X','Y','Z','W','P','R'), components, (10000000,)*3 + (180,)*3):
            if not -limit <= value <= limit:
                raise KarelRuntimeError(f'POS {field} must be in {-limit}..{limit}', line)
        config = positional_value(('CONFIG',), arguments[6], line)
        result = Structure(('XYZWPR',))
        result.values.update(zip(('X','Y','Z','W','P','R'), components))
        result.values['CONFIG_DATA'] = config
        return result
    if name == 'VEC' and _pythonic():
        if len(arguments) != 3: raise KarelRuntimeError('VEC requires exactly three arguments', line)
        components = [real(value, line) for value in arguments]
        result = Structure(('VECTOR',))
        result.values.update(zip(('X', 'Y', 'Z'), components))
        return result
    if name == 'ATAN2':
        if len(arguments) != 2: raise KarelRuntimeError('ATAN2 requires exactly two arguments', line)
        return exact_atan2(arguments[0], arguments[1], line)
    if name in UNARY_TRIG_FUNCTIONS:
        if len(arguments) != 1: raise KarelRuntimeError(f'{name} requires exactly one argument', line)
        return exact_trig(name, arguments[0], line)
    if name == 'ABS':
        value = arguments[0]
        return real(abs(real(value, line)), line) if type(value) is float else integer(abs(integer(value, line)), line)
    if name == 'SQRT':
        value = real(arguments[0], line)
        if value < 0:
            raise KarelRuntimeError('SQRT argument must not be negative', line)
        if _pythonic(): return real(math.sqrt(value), line)
        value = Fraction(value)
        numerator = math.isqrt(value.numerator)
        denominator = math.isqrt(value.denominator)
        # A reduced rational has a rational square root exactly when both
        # numerator and denominator are squares. Never adopt a rounded host root.
        if numerator * numerator != value.numerator or denominator * denominator != value.denominator:
            raise KarelRuntimeError('SQRT rounding is not validated; exact rational roots only', line)
        return _real_fraction(Fraction(numerator, denominator), line)
    if name in ('EXP', 'LN'):
        if not _pythonic():
            raise KarelRuntimeError(f'{name} is available only in Pythonic mode', line)
        value = real(arguments[0], line)
        if name == 'LN' and value <= 0:
            raise KarelRuntimeError('LN argument must be positive', line)
        try:
            return real(math.exp(value) if name == 'EXP' else math.log(value), line)
        except OverflowError:
            raise KarelRuntimeError(f'{name} REAL overflow', line) from None
    if name in ('ROUND', 'TRUNC'):
        if _pythonic():
            value = real(arguments[0], line)
            converted = round(value) if name == 'ROUND' else math.trunc(value)
            return checked(INTEGER, converted, line)
        value = Fraction(real(arguments[0], line))
        maximum = 2147483646 if name == 'ROUND' else 2147483583
        if not -2147483648 <= value <= maximum:
            raise KarelRuntimeError(f'{name} argument outside documented INTEGER conversion range', line)
        if name == 'TRUNC': return integer(int(value), line)
        magnitude = abs(value) + Fraction(1, 2)
        rounded = magnitude.numerator // magnitude.denominator
        return integer(-rounded if value < 0 else rounded, line)
    if name == 'STR_LEN': return len(ascii_string(arguments[0], line))
    if name == 'ARRAY_LEN':
        array = arguments[0]
        if not isinstance(array, Array): raise KarelRuntimeError('Expected ARRAY', line)
        if not _pythonic() and len(array_dimensions(array.spec)) != 1:
            raise KarelRuntimeError('ARRAY_LEN on multidimensional arrays needs dimension-count validation', line)
        if (type(array.shape) is not tuple or not 1 <= len(array.shape) <= 3 or array.shape != array_shape(array.spec)
                or any(type(size) is not int or not 1 <= size <= 32767 for size in array.shape)):
            raise KarelRuntimeError('ARRAY_LEN requires a concrete valid shape', line)
        return array.shape[0]
    if name == 'UNINIT': return uninit(arguments[0])
    if name == 'SUB_STR':
        source = ascii_string(arguments[0], line)
        start, count = (integer(x, line) for x in arguments[1:])
        if _pythonic():
            if start < 1 or count < 0:
                raise KarelRuntimeError('SUB_STR start must be positive and length nonnegative', line)
            # Bound the slice before allocating it, including a MAXINT count.
            return source[start - 1:start - 1 + min(count, 254)]
        if start < 1 or count < 1:
            raise KarelRuntimeError('SUB_STR start and length must be positive', line)
        if start > len(source): return ''
        if count > len(source) - start + 1:
            raise KarelRuntimeError('SUB_STR length extending beyond source needs runtime validation', line)
        if count > 254:
            raise KarelRuntimeError('SUB_STR results longer than 254 need return-capacity validation', line)
        return source[start - 1:start - 1 + count]
    if name == 'INDEX':
        source, search = (ascii_string(x, line) for x in arguments)
        if search == '' and not _pythonic():
            raise KarelRuntimeError('INDEX empty search string needs runtime validation', line)
        return source.find(search) + 1
    if name == 'CHR':
        code = integer(arguments[0], line)
        if not 0 <= code <= 127:
            raise KarelRuntimeError('CHR supports only ASCII codes 0..127', line)
        return chr(code)
    if name == 'ORD':
        source = ascii_string(arguments[0], line)
        index = integer(arguments[1], line)
        if not 1 <= index <= len(source):
            raise KarelRuntimeError(f'ORD index {index} outside 1..{len(source)}', line)
        return ord(source[index - 1])
    raise KarelRuntimeError(f'Unsupported built-in {name}', line)


def snapshot_value(value):
    if isinstance(value,FileHandle): return dict(file=value.name,open=value.owner is not None,position=value.position,binary=value.binary,status=value.status)
    if isinstance(value,PathValue): return dict(nodes=[snapshot_value(node) for node in value.nodes],data=snapshot_value(value.data))
    if isinstance(value,QueueValue): return dict(initialized=value.initialized,entries=[list(pair) for pair in value.entries])
    if isinstance(value, JointPosition): return {'axes': [snapshot_value(x) for x in value.values]}
    if value is UNINITIALIZED:
        return {'uninitialized': True}
    if value is UNKNOWN_BYTE: return {'unknown_byte': True}
    if isinstance(value, Array):
        return value.snapshot()
    if isinstance(value, Structure):
        return {name: snapshot_value(x) for name, x in value.values.items()}
    return value


def _format_write_string(text, line=None, *, width=None, alignment=0):
    text = ascii_string(text, line)
    if len(text) > 254:
        raise KarelRuntimeError('WRITE STRING input is limited to 254 characters', line)
    if type(alignment) is not int or alignment not in (0, 1, 2, 3):
        raise KarelRuntimeError('WRITE STRING alignment must be INTEGER 0, 1, 2 or 3', line)
    if width is None:
        if alignment != 0:
            raise KarelRuntimeError('WRITE STRING alignment requires a width', line)
    else:
        if type(width) is not int or not 0 <= width <= 2147483647:
            raise KarelRuntimeError('WRITE STRING width must be nonnegative INTEGER in 0..2147483647', line)
        if alignment in (2, 3):
            if _pythonic():
                # Keep paired quotes and complete doubled-apostrophe escapes,
                # even when the requested field is shorter than the wrapper.
                escaped = ["''" if char == "'" else char for char in text]
                natural = sum(map(len, escaped)) + 3
                width = max(3, width) if 1 <= width <= 254 else natural
                contents, remaining = [], width - 3
                for char in escaped:
                    if len(char) > remaining: break
                    contents.append(char)
                    remaining -= len(char)
                text = " '" + ''.join(contents) + "'"
                return text.rjust(width) if alignment == 3 else text.ljust(width)
            if not 1 <= width <= 254:
                raise KarelRuntimeError('Quoted WRITE width fallback is not implemented', line)
            if "'" in text:
                raise KarelRuntimeError('Quoted WRITE with embedded apostrophes is not implemented', line)
            if len(text) + 3 > width:
                raise KarelRuntimeError('Quoted WRITE truncation is not implemented; width must fit a leading blank, contents and both quotes', line)
            text = " '" + text + "'"
        else:
            if not 1 <= width <= 254:
                width = len(text)
            text = text[:width]
        blanks = ' ' * (width - len(text))
        text = blanks + text if alignment in (1, 3) else text + blanks
    return text


def format_write_item(kind, value, formats=(), line=None):
    """Render one Pythonic scalar without emitting an output request."""
    if not _pythonic(): raise KarelRuntimeError('Scalar item rendering requires Pythonic mode', line)
    if type(formats) not in (tuple, list) or len(formats) > 2 or any(type(item) is not int for item in formats):
        raise KarelRuntimeError('WRITE requires at most two INTEGER format specifiers', line)
    width = formats[0] if formats else None
    second = formats[1] if len(formats) == 2 else None
    if kind == 'STRING':
        return _format_write_string(value, line, width=width, alignment=second if second is not None else 0)
    if width is not None and not 0 <= width <= 254:
        raise KarelRuntimeError('Numeric/BOOLEAN WRITE width must be in 0..254', line)
    if kind == 'REAL':
        value = real(value, line)
        precision = second if second is not None else -5
        if not -254 <= precision <= 254:
            raise KarelRuntimeError('REAL WRITE precision must be in -254..254', line)
        style = 'E' if precision < 0 else 'f'
        text = ' ' + format(value, f'.{abs(precision)}{style}')
    elif kind == 'BOOLEAN':
        if second is not None: raise KarelRuntimeError('BOOLEAN WRITE accepts only a width', line)
        text = ' TRUE' if boolean(value, line) else ' FALSE'
    elif kind in ('INTEGER', 'BYTE', 'SHORT'):
        value = integer(value, line) if kind == 'INTEGER' else integer(checked((kind,), value, line), line)
        base = 10 if second in (None, 0) else second
        if not 2 <= base <= 16:
            raise KarelRuntimeError('INTEGER WRITE base must be 0 or 2..16', line)
        digits, remaining = [], abs(value)
        while remaining:
            remaining, digit = divmod(remaining, base)
            digits.append('0123456789ABCDEF'[digit])
        body = ('-' if value < 0 else '') + (''.join(reversed(digits)) or '0')
        # Retain the manual's zero-filled nondecimal fields, with a Pythonic
        # minus sign instead of inferring controller two's-complement output.
        if base != 10 and width: body = body.zfill(width - 1)
        text = ' ' + body
    else:
        raise KarelRuntimeError('WRITE requires a supported scalar type', line)
    return text.rjust(width or 0)


def _read_scalar_spec(spec, line=None):
    scalar = spec in (INTEGER, REAL, ('BOOLEAN',), ('BYTE',), ('SHORT',))
    string = (type(spec) is tuple and len(spec) == 2 and spec[0] == 'STRING'
              and type(spec[1]) is int and 1 <= spec[1] <= 254)
    if not scalar and not string:
        raise KarelRuntimeError('READ requires supported concrete scalar types and STRING capacities', line)
    return spec


def _read_line_breaks(count, positions, line=None):
    if type(positions) not in (list, tuple) or not 1 <= count + len(positions) <= 1024:
        raise KarelRuntimeError('READ requires 1..1024 scalar destinations or CR markers', line)
    previous = 0
    for position in positions:
        if type(position) is not int or not previous <= position <= count:
            raise KarelRuntimeError('READ CR positions must be ordered destination offsets', line)
        previous = position
    return tuple(positions)


def read_formats(spec, formats, line=None):
    """Check concrete Pythonic input formats without consuming input."""
    _read_scalar_spec(spec, line)
    if type(formats) not in (list, tuple) or len(formats) > 2:
        raise KarelRuntimeError('READ requires at most two INTEGER format specifiers', line)
    formats = tuple(integer(value, line) for value in formats)
    if formats and not 0 <= formats[0] <= 254:
        raise KarelRuntimeError('READ width must be in 0..254', line)
    if len(formats) == 2:
        second = formats[1]
        valid = (spec[0] in ('REAL', 'BOOLEAN') or spec[0] == 'STRING' and second in (0, 2)
                 or spec[0] in ('INTEGER', 'BYTE', 'SHORT') and second in (0, *range(2, 17)))
        if not valid: raise KarelRuntimeError(f'Invalid {spec[0]} READ second format specifier', line)
    return formats


def capture_read_target(target, formats, line=None):
    if type(target) is not Reference:
        raise KarelRuntimeError('READ requires ordinary writable scalar references', line)
    return target, read_formats(target.spec, formats, line)


class TextInput:
    """Explicit ASCII text adapter for Pythonic READ, with a persistent cursor."""
    def __init__(self, text, *, terminator=None, field_mode=False):
        if type(text) is not str or not text.isascii():
            raise ValueError('TextInput requires an ASCII string')
        if terminator is not None and (type(terminator) is not int or not 0<=terminator<=127):
            raise ValueError('TextInput terminator must be an ASCII code or None')
        if type(field_mode) is not bool: raise ValueError('TextInput field_mode must be BOOLEAN')
        self.field_mode = field_mode
        separators = list(re.finditer(r'\r\n|\r|\n' if terminator in (None,10,13) else re.escape(chr(terminator)), text))
        self._starts = [0] + [match.end() for match in separators]
        self._lines = [text[start:match.start()] for start,match in zip(self._starts,separators)] + [text[self._starts[-1]:]]
        self._length = len(text)
        self._terminated = bool(separators) and separators[-1].end() == len(text)
        if not text or self._terminated: self._lines.pop()
        self._row, self._column, self._after_field = 0, 0, False

    @property
    def offset(self):
        """Exact ASCII byte offset, including consumed record separators."""
        return self._length if self._row >= len(self._lines) else self._starts[self._row] + self._column

    @property
    def position(self):
        if self._row >= len(self._lines):
            row = len(self._lines) if self._lines and not self._terminated else len(self._lines) + 1
            column = len(self._lines[-1]) + 1 if self._lines and not self._terminated else 1
            return dict(line=row, column=column, eof=True)
        eof = (self._row == len(self._lines) - 1 and not self._terminated
               and self._column == len(self._lines[self._row]))
        return dict(line=self._row + 1, column=self._column + 1, eof=eof)

    def _next_line(self):
        self._row += 1
        self._column, self._after_field = 0, False

    def _require_line(self):
        if self._row >= len(self._lines):
            position = self.position
            raise KarelRuntimeError(f'TextInput reached end of input at input line {position["line"]}, column {position["column"]}')

    def _token(self):
        while True:
            self._require_line()
            line = self._lines[self._row]
            while self._column < len(line) and line[self._column].isspace(): self._column += 1
            if self._column < len(line): break
            self._next_line()
        start = self._column
        while self._column < len(line) and not line[self._column].isspace(): self._column += 1
        self._after_field = True
        return line[start:self._column], self._row + 1, start + 1

    def _field_line(self):
        self._require_line()
        if self._after_field and self._column == len(self._lines[self._row]):
            self._next_line()
            self._require_line()
        return self._lines[self._row]

    def _string(self, width=0):
        line = self._field_line()
        row, column = self._row + 1, self._column + 1
        value = line[self._column:self._column + width] if width else line[self._column:]
        self._column, self._after_field = self._column + len(value), True
        if width and len(value) != width:
            raise KarelRuntimeError(f'TextInput incomplete field at input line {row}, column {column}; expected {width} characters')
        return value, row, column

    def _quoted(self, width):
        if width:
            field, row, column = self._string(width)
        else:
            line = self._field_line()
            row, column = self._row + 1, self._column + 1
            field = line[self._column:]
        offset = 0
        while offset < len(field) and field[offset].isspace(): offset += 1
        contents = []
        if offset < len(field) and field[offset] == "'":
            offset += 1
            while offset < len(field):
                char = field[offset]; offset += 1
                if char == "'":
                    if offset < len(field) and field[offset] == "'":
                        contents.append("'"); offset += 1
                        continue
                    if not width:
                        self._column += offset
                        self._after_field = True
                    if not width or not field[offset:].strip():
                        return ''.join(contents), row, column
                    break
                contents.append(char)
        if not width:
            self._column += len(field)
            self._after_field = True
        raise KarelRuntimeError(f'TextInput invalid quoted STRING at input line {row}, column {column}')

    def __call__(self, request):
        if type(request) is not dict or type(request.get('targets')) not in (list, tuple):
            raise KarelRuntimeError('TextInput requires READ target metadata')
        targets = request['targets']
        breaks = _read_line_breaks(len(targets), request.get('line_breaks', ()))
        specs, formats = [], []
        for target in targets:
            if type(target) is not dict or type(target.get('type_spec')) not in (list, tuple):
                raise KarelRuntimeError('TextInput requires concrete READ target type specs')
            spec = _read_scalar_spec(tuple(target['type_spec']))
            if target.get('type') != spec[0]: raise KarelRuntimeError('TextInput target type metadata disagrees')
            specs.append(spec)
            formats.append(read_formats(spec, target.get('format_specifiers', ())))
        values, marker = [], 0
        for index in range(len(specs) + 1):
            while marker < len(breaks) and breaks[marker] == index:
                self._require_line()
                self._next_line()
                marker += 1
            if index == len(specs): break
            spec = specs[index]
            controls = formats[index]
            width = controls[0] if controls else 0
            second = controls[1] if len(controls) == 2 else 0
            if self.field_mode and spec[0] == 'STRING' and not width: width = spec[1]
            if spec[0] == 'STRING' and second == 2: token, row, column = self._quoted(width)
            elif width or spec[0] == 'STRING': token, row, column = self._string(width)
            else: token, row, column = self._token()
            try:
                if spec[0] == 'STRING':
                    value = token
                    if len(value) > 254: raise ValueError('STRING input exceeds 254 characters before truncation')
                elif spec[0] == 'REAL': value = float(token)
                elif spec[0] == 'BOOLEAN':
                    name = token.upper()
                    name = name.strip()
                    if name not in ('TRUE','TRU','TR','T','ON','1','FALSE','FALS','FAL','FA','F','OFF','OF','0'): raise ValueError('Invalid BOOLEAN token')
                    value = name in ('TRUE','TRU','TR','T','ON','1')
                else: value = int(token, second or 10)
                with _numeric_scope('pythonic'): checked(spec, value)
            except (ValueError, OverflowError, KarelRuntimeError) as exc:
                raise KarelRuntimeError(f'TextInput invalid {spec[0]} at input line {row}, column {column}') from exc
            values.append(value)
        return values


REGISTER_UNINITIALIZED = 1
REGISTER_OUT_OF_RANGE = 2


class NumericRegisters:
    """Explicit bounded in-memory numeric registers; no controller access."""
    def __init__(self, count, initial=None, *, comments=None):
        if type(count) is not int or not 1 <= count <= 32767:
            raise ValueError('NumericRegisters count must be an integer in 1..32767')
        if initial is not None and type(initial) is not dict:
            raise TypeError('NumericRegisters initial values must be a dict of integer register numbers to int/float values')
        self._count, self._values = count, {}
        self.comments=RegisterComments(count,comments)
        for number, value in (initial or {}).items():
            if self.write(number,value) != 0: raise ValueError('Initial register number is outside the explicit register count')

    @property
    def count(self): return self._count

    def snapshot(self): return self._values.copy()

    def to_config(self):
        result={'count':self.count,'values':{str(k):v for k,v in self.snapshot().items()}}
        if self.comments.values: result['comments']={str(k):v for k,v in self.comments.snapshot().items()}
        return result

    @classmethod
    def from_config(cls, config):
        if type(config) is not dict or not {'count','values'}<=set(config) or set(config)-{'count','values','comments'} or type(config['values']) is not dict:
            raise ValueError('Register configuration requires count and values, with optional comments')
        values = {}
        for number, value in config['values'].items():
            if type(number) is not str or not re.fullmatch(r'[1-9][0-9]{0,4}',number):
                raise ValueError('Register configuration keys must be canonical positive decimal numbers up to 32767')
            values[int(number)] = value
        return cls(config['count'],values,comments=RegisterComments.decode(config.get('comments',{})))

    def read(self, number, line=None):
        number = integer(number,line)
        if not 1 <= number <= self.count: return REGISTER_OUT_OF_RANGE, None
        if number not in self._values: return REGISTER_UNINITIALIZED, None
        return 0, self._values[number]

    def write(self, number, value, line=None):
        number = integer(number,line)
        if type(value) not in (int,float): raise KarelRuntimeError('Numeric register values require int or float',line)
        with _numeric_scope('pythonic'):
            value = checked(INTEGER if type(value) is int else REAL,value,line)
        if not 1 <= number <= self.count: return REGISTER_OUT_OF_RANGE
        self._values[number] = value
        return 0


class State:
    @property
    def _pause_requested(self): return self._budget_parent._pause_requested if self._budget_parent is not None else self._pause_flag
    @_pause_requested.setter
    def _pause_requested(self,value):
        if self._budget_parent is not None: self._budget_parent._pause_requested=value
        else: self._pause_flag=value
    @property
    def _abort_requested(self): return self._budget_parent._abort_requested if self._budget_parent is not None else self._abort_flag
    @_abort_requested.setter
    def _abort_requested(self,value):
        if self._budget_parent is not None: self._budget_parent._abort_requested=value
        else: self._abort_flag=value
    @property
    def _abort_request_line(self): return self._budget_parent._abort_request_line if self._budget_parent is not None else self._pending_abort_line
    @_abort_request_line.setter
    def _abort_request_line(self,value):
        if self._budget_parent is not None: self._budget_parent._abort_request_line=value
        else: self._pending_abort_line=value

    def __init__(self, declarations, constants, *, sleep=None, write=None, read=None, joint_axes=None, pose_tolerance=None, external_tolerance=None, clock_us=None, registers=None, context=None):
        if context is not None and type(context) is not ExecutionContext: raise TypeError('context must be ExecutionContext or None')
        self.execution=context if context is not None else ExecutionContext()
        if registers is None: registers=self.execution.numeric
        self.robot_group=self.execution.robot.active_group if self.execution.robot is not None else None
        self.program_name=''
        self._task_frames=[];self._task_line=0;self._has_run=False
        self.service_requests=[]
        self._handlers={}; self._in_handler=False; self._timers={}
        self._scheduler=None; self._scheduler_clock=False; self._budget_parent=None
        self._event_seen={}; self._edge_history={}; self._scanning_condition=None
        self._abort_requested=False; self._abort_request_line=None; self._lifecycle={'CONTINUE':0,'POWERUP':0}
        self._current_error=None
        self.task_state='ready'; self._pause_requested=False; self._driving=False
        if joint_axes is not None and (type(joint_axes) is not int or not 1 <= joint_axes <= 9):
            raise ValueError('joint_axes must be None or an INTEGER in 1..9')
        if sleep is not None and not callable(sleep):
            raise TypeError('sleep must be a synchronous callable accepting seconds, or None')
        if write is not None and not callable(write):
            raise TypeError('write must be a synchronous callable accepting text, or None')
        if read is not None and not callable(read):
            raise TypeError('read must be a synchronous callable accepting a request, or None')
        if clock_us is not None and not callable(clock_us):
            raise TypeError('clock_us must be a synchronous callable returning nonnegative integer microseconds, or None')
        if registers is not None and type(registers) is not NumericRegisters:
            raise TypeError('registers must be an explicit NumericRegisters instance, or None')
        self._sleep = time.sleep if sleep is None else sleep
        self._write = write
        self._read = read
        self._clock_us = clock_us
        self.registers = registers
        self.joint_axes = joint_axes
        self.pose_tolerance = checked_pose_tolerance(pose_tolerance)
        self.external_tolerance = checked_external_tolerance(external_tolerance)
        self.write_requests = []
        self.read_requests = []
        self.clock_reads = []
        self.register_requests = []
        self.types = declarations
        self.constants = constants
        self.values = {name: initial_value(spec) for name, spec in declarations.items()}
        self.steps = 0
        self.max_steps = 100000
        self.call_depth = 0
        self.local_frames = []
        self._aborted = False
        self._abort_line = None

    @property
    def abort_info(self):
        return dict(kind='ABORT', line=self._abort_line, scope='current offline execution') if self._aborted else None

    def abort(self, line=None):
        if not self._aborted:
            self._aborted, self._abort_line = True, line
        raise KarelAbort(self._abort_line)

    def joint_conversion(self, name, source, target, status, line=None):
        """Offline degree-valued array/joint conversion with explicit axis context."""
        if name not in ('CNV_REL_JPOS', 'CNV_JPOS_REL'):
            raise KarelRuntimeError('Unknown joint conversion', line)
        if self.joint_axes is None:
            raise KarelRuntimeError('Joint conversion requires explicit Program(joint_axes=1..9) context', line)
        if (not isinstance(status, Reference) or status.spec != INTEGER
                or isinstance(status, (ReadOnlyFieldReference, ConfigFieldReference))):
            raise KarelRuntimeError('Joint conversion status requires ordinary writable INTEGER storage', line)
        count = self.joint_axes
        if name == 'CNV_REL_JPOS':
            if not isinstance(target, Reference) or target.spec[0] != 'JOINTPOS':
                raise KarelRuntimeError('Joint output requires a writable JOINTPOS reference', line)
            if joint_width(target.spec) != count:
                raise KarelRuntimeError('Joint declared width must match explicit joint_axes context', line)
            array = source
        else:
            if not isinstance(source, JointPosition) or joint_width(source.spec) != count:
                raise KarelRuntimeError('Joint declared width must match explicit joint_axes context', line)
            if not fully_initialized(source): raise KarelRuntimeError('Joint conversion requires initialized axes', line)
            array = target
        if (not isinstance(array, Array) or len(array_dimensions(array.spec)) != 1
                or array_leaf_spec(array.spec) != REAL):
            raise KarelRuntimeError('Joint conversion requires a one-dimensional ARRAY OF REAL', line)
        length = array_dimensions(array.spec)[0]
        if name == 'CNV_REL_JPOS':
            if length < count: raise KarelRuntimeError('Joint input ARRAY is smaller than explicit joint_axes', line)
            axes = [real(array.raw(i + 1, line), line) for i in range(count)]
            converted = JointPosition(target.spec)
            converted.values[:] = axes
            target.set(converted, line)
        else:
            # Validate the entire opaque joint before touching any output.
            axes = [real(axis, line) for axis in source.values]
            if len(axes) != count: raise KarelRuntimeError('Malformed joint axis values', line)
            for i in range(min(length, count)): array.set(i + 1, axes[i], line)
        status.set(0, line)  # Offline success only; no controller status/alarm mapping.

    def numeric_register(self, name, number, *arguments, line=None):
        """Checked GET/SET operations on the explicitly supplied memory bank."""
        if not _pythonic(): raise KarelRuntimeError('Numeric registers require Pythonic mode',line)
        if type(self.registers) is not NumericRegisters:
            raise KarelRuntimeError('Numeric register operations require explicit Program(registers=NumericRegisters(...)) context',line)
        reading = name == 'GET_REG'
        if name not in ('GET_REG','SET_INT_REG','SET_REAL_REG') or len(arguments) != (4 if reading else 2):
            raise KarelRuntimeError('Unsupported numeric register procedure or argument count',line)
        number = integer(number,line)
        outputs = arguments if reading else arguments[1:]
        specs = (BOOLEAN,INTEGER,REAL,INTEGER) if reading else (INTEGER,)
        occupied = set()
        for output, spec in zip(outputs,specs):
            if type(output) is not Reference or output.spec != spec:
                raise KarelRuntimeError('Numeric register outputs require ordinary exact-type writable references',line)
            cells = _reference_cells(output)
            if occupied & cells: raise KarelRuntimeError('Numeric register outputs must not overlap',line)
            occupied.update(cells)
        if reading:
            code, value = self.registers.read(number,line)
            if code == 0:
                flag, int_value, real_value, _ = outputs
                is_real = type(value) is float
                # Check the selected value before changing any program output.
                value = checked(REAL if is_real else INTEGER,value,line)
                (real_value if is_real else int_value).set(value,line)
                flag.set(is_real,line)
        else:
            value = integer(arguments[0],line) if name == 'SET_INT_REG' else real(arguments[0],line)
            code = self.registers.write(number,value,line)
        outputs[-1].set(code,line)
        self.register_requests.append(dict(procedure=name,register_no=number,line=line,operation='read' if reading else 'write',
                                           status=code,adapter_outcome='completed' if code == 0 else 'uninitialized' if code == REGISTER_UNINITIALIZED else 'out_of_range'))

    def tick(self, line=None):
        if line is not None: task_root(self)._task_line=line
        if self._budget_parent is not None: self._budget_parent.tick(line)
        if self._aborted: raise KarelAbort(self._abort_line)
        if self.task_state=='stopped': raise KarelStop('Task is stopped')
        update_timers(self,line)
        self.steps += 1
        if self.steps > self.max_steps:
            raise KarelRuntimeError(f'Execution step budget exceeded ({self.max_steps})', line)

    def begin(self, max_steps):
        if self._aborted: raise KarelAbort(self._abort_line)
        if type(max_steps) is not int or max_steps < 1:
            raise ValueError('max_steps must be a positive integer')
        self.max_steps, self.steps = max_steps, 0
        self._task_frames.clear();self._task_line=0;self._has_run=True
        self.write_requests.clear()
        self.read_requests.clear()
        self.clock_reads.clear()
        self.register_requests.clear()
        self.service_requests.clear()
        self._handlers.clear(); self._timers.clear()
        self._event_seen.clear(); self._edge_history.clear(); self._abort_requested=False; self._abort_request_line=None; self._current_error=None; self._lifecycle={'CONTINUE':0,'POWERUP':0}

    def extended_call(self,name,arguments,line=None):
        if not _pythonic(): raise KarelRuntimeError('Extended services require Pythonic mode',line)
        row=dict(operation=name,line=line,outcome='requested'); self.service_requests.append(row)
        try: result=self.execution.invoke(self,name,arguments,line)
        except Exception as exc:
            row['outcome']='failed'
            if isinstance(exc,KarelRuntimeError) and exc.line is None: raise KarelRuntimeError(str(exc),line) from exc
            raise
        row['outcome']='completed'; return result

    def port_read(self,kind,number,line=None): return self.execution.require('ports',line).read(kind,number,line)

    def port_write(self,kind,number,value,line=None):
        try: return self.execution.require('ports',line).write(kind,number,value,line)
        except KarelRuntimeError as exc:
            if exc.line is None: raise KarelRuntimeError(str(exc),line) from exc
            raise

    def read_observations(self):
        return tuple(deepcopy(self.read_requests))

    def read_items(self, targets, line=None, *, line_breaks=(), formats=None):
        """Receive typed offline input; validate the complete response before writes."""
        if type(targets) not in (list, tuple):
            raise KarelRuntimeError('READ requires scalar destination references', line)
        line_breaks = _read_line_breaks(len(targets), line_breaks, line)
        for target in targets:
            if type(target) is not Reference:
                raise KarelRuntimeError('READ requires ordinary writable scalar references', line)
            _read_scalar_spec(target.spec, line)
        if formats is None: formats = [()] * len(targets)
        if type(formats) not in (list, tuple) or len(formats) != len(targets):
            raise KarelRuntimeError('READ requires one format list per scalar destination', line)
        formats = [read_formats(target.spec, item, line) for target, item in zip(targets, formats)]
        metadata = dict(line=line, targets=[dict(type=ref.spec[0], type_spec=ref.spec) for ref in targets])
        for target, item in zip(metadata['targets'], formats):
            if item: target['format_specifiers'] = item
        if line_breaks: metadata['line_breaks'] = list(line_breaks)
        request = dict(deepcopy(metadata), adapter_outcome='missing_adapter')
        self.read_requests.append(request)
        if self._read is None:
            raise KarelRuntimeError('READ requires an explicit Program(read=...) input callback', line)
        request['adapter_outcome'] = 'callback_started'
        try:
            response = self._read(deepcopy(metadata))
        except Exception as exc:
            request['adapter_outcome'] = 'callback_failed'
            raise KarelRuntimeError(f'READ input callback failed: {exc}', line) from exc
        except BaseException:
            request['adapter_outcome'] = 'callback_interrupted'
            raise
        try:
            if type(response) not in (list, tuple) or len(response) != len(targets):
                if inspect.iscoroutine(response): response.close()
                raise KarelRuntimeError('READ input callback must return a list/tuple with one typed value per destination', line)
            values = list(response)
            for target, value in zip(targets, values):
                if target.spec[0] == 'STRING':
                    if len(ascii_string(value, line)) > 254:
                        raise KarelRuntimeError('READ STRING input is limited to 254 characters before truncation', line)
                checked(target.spec, value, line)
        except Exception:
            request['adapter_outcome'] = 'callback_result_rejected'
            raise
        request['adapter_outcome'] = 'response_validated'
        try:
            for target, value in zip(targets, values): target.set(value, line)
        except BaseException:
            request['adapter_outcome'] = 'assignment_failed'
            raise
        request['adapter_outcome'] = 'callback_completed'

    def write_string(self, text, line=None, *, width=None, alignment=0):
        """Record an offline request or call a supplied text sink; not device I/O."""
        text = _format_write_string(text, line, width=width, alignment=alignment)
        request = dict(text=text, line=line, adapter_outcome='recorded')
        self.write_requests.append(request)
        if self._write is None:
            return
        request['adapter_outcome'] = 'callback_started'
        try:
            result = self._write(text)
        except Exception as exc:
            request['adapter_outcome'] = 'callback_failed'
            raise KarelRuntimeError(f'WRITE output callback failed: {exc}', line) from exc
        except BaseException:
            request['adapter_outcome'] = 'callback_interrupted'
            raise
        if result is not None:
            request['adapter_outcome'] = 'callback_result_rejected'
            raise KarelRuntimeError('WRITE output callback must return None', line)
        request['adapter_outcome'] = 'callback_completed'

    def write_items(self, pieces, line=None, *, file=None):
        """Commit one fully rendered WRITE; earlier expression effects remain."""
        if type(pieces) not in (list, tuple) or not 1 <= len(pieces) <= 1024:
            raise KarelRuntimeError('WRITE requires 1..1024 rendered items', line)
        if file is not None:
            file.require_open(line)
            data=b''.join(piece.encode('ascii') if type(piece) is str else piece for piece in pieces)
            if not file.binary: data=data.replace(b'\n',bytes((file.eol,)))
            file.owner.write(file,data,line); return
        total = 0
        for piece in pieces:
            total += len(ascii_string(piece, line))
            if total > 254:
                raise KarelRuntimeError('WRITE combined output is limited to 254 characters', line)
        self.write_string(''.join(pieces), line)

    def write_boolean(self, value, line=None):
        """Default BOOLEAN text; same offline request/callback contract as STRING."""
        value = boolean(value, line)
        self.write_string(' TRUE' if value else ' FALSE', line)

    def write_integer(self, value, line=None):
        """Default nonnegative decimal text; negative/format spacing is unresolved."""
        value = integer(value, line)
        if value < 0:
            raise KarelRuntimeError('Negative INTEGER WRITE spacing is not established; output is limited to nonnegative values', line)
        self.write_string(' ' + str(value), line)

    def delay(self, milliseconds, line=None):
        """Checked host delay; controller scheduling and pause semantics are not modeled."""
        milliseconds = integer(milliseconds, line)
        if not 0 <= milliseconds <= 86400000:
            raise KarelRuntimeError('DELAY requires milliseconds in 0..86400000 (one day)', line)
        # KAREL zero has no effect. time.sleep(0) may yield the host thread.
        if milliseconds == 0:
            return
        try:
            result = self._sleep(milliseconds / 1000.0)
        except Exception as exc:
            raise KarelRuntimeError(f'Host DELAY sleeper failed: {exc}', line) from exc
        if result is not None:
            raise KarelRuntimeError('Host DELAY sleeper must return None', line)

    def microsecond_time(self, line=None):
        """Sample host monotonic microseconds or an explicit synchronous test clock."""
        if not _pythonic(): raise KarelRuntimeError('Microsecond timers require Pythonic mode',line)
        if self._aborted: raise KarelAbort(self._abort_line)
        observation = dict(line=line,adapter='monotonic' if self._clock_us is None else 'injected',adapter_outcome='requested')
        self.clock_reads.append(observation)
        try:
            sample = time.monotonic_ns()//1000 if self._clock_us is None else self._clock_us()
        except Exception as exc:
            observation['adapter_outcome'] = 'aborted' if self._aborted else 'clock_failed'
            if self._aborted: raise KarelAbort(self._abort_line) from exc
            raise KarelRuntimeError(f'Host microsecond clock failed: {exc}',line) from exc
        if inspect.iscoroutine(sample): sample.close()
        if self._aborted:
            observation['adapter_outcome'] = 'aborted'
            raise KarelAbort(self._abort_line)
        if type(sample) is not int or sample < 0:
            observation['adapter_outcome'] = 'invalid_response'
            raise KarelRuntimeError('Host microsecond clock must return nonnegative integer microseconds synchronously',line)
        counter = sample % USEC_PERIOD
        observation.update(counter=counter,adapter_outcome='completed')
        return counter

    def wait_poll(self, line=None):
        """Yield after a false budgeted WAIT check; do not infer controller timing."""
        if not _pythonic(): raise KarelRuntimeError('WAIT requires Pythonic mode', line)
        if self._aborted: raise KarelAbort(self._abort_line)
        try:
            result = self._sleep(0.0)
        except Exception as exc:
            if self._aborted: raise KarelAbort(self._abort_line) from exc
            raise KarelRuntimeError(f'Host WAIT sleeper failed: {exc}', line) from exc
        if self._aborted: raise KarelAbort(self._abort_line)
        if result is not None: raise KarelRuntimeError('Host WAIT sleeper must return None', line)

    def enter_routine(self, declarations, line=None, arguments=None, *, routine=''):
        if self.call_depth >= 64:
            raise KarelRuntimeError('Prototype routine call-depth limit exceeded (64)', line)
        arguments = arguments or {}
        for name, argument in arguments.items():
            if (name not in declarations or not isinstance(argument, Reference)
                    or not parameter_accepts(declarations[name], argument.spec)):
                raise KarelRuntimeError('Parameter binding type mismatch', line)
        values = {name: initial_value(spec) for name, spec in declarations.items() if name not in arguments}
        values.update(arguments)
        self.call_depth += 1
        self.local_frames.append((declarations, values))
        task_root(self)._task_frames.append((self,routine))

    def leave_routine(self):
        frame=self.local_frames[-1]
        for number,handler in list(self._handlers.items()):
            if handler.get('local_frame') is frame: self._handlers.pop(number,None)
        self.call_depth -= 1
        self.local_frames.pop()
        task_root(self)._task_frames.pop()

    def raw(self, name):
        if self.local_frames and name in self.local_frames[-1][0]:
            value = self.local_frames[-1][1][name]
            return value.raw() if isinstance(value, Reference) else value
        value=self.constants[name] if name in self.constants else self.values[name]
        return value.raw() if isinstance(value,Reference) else value

    def reference(self, name, line=None):
        if name in self.constants:
            raise KarelRuntimeError('CONST cannot be bound by reference', line)
        declarations, values = self.local_frames[-1] if self.local_frames and name in self.local_frames[-1][0] else (self.types, self.values)
        if name not in declarations:
            raise KarelRuntimeError('Unknown reference variable', line)
        value = values[name]
        return value if isinstance(value, Reference) else Reference(declarations[name], values, name)

    def get(self, name, line=None):
        return require(self.raw(name), line)

    def set(self, name, value, line=None):
        if name in self.constants:
            raise KarelRuntimeError('Cannot assign to CONST', line)
        if self.local_frames and name in self.local_frames[-1][0]:
            declarations, values = self.local_frames[-1]
        else:
            declarations, values = self.types, self.values
        current = values[name]
        if isinstance(current, Reference):
            current.set(value, line)
        else:
            updated = checked(declarations[name], value, line)
            values[name] = replace_value(current, updated)

    def clear(self, name):
        values = self.local_frames[-1][1] if self.local_frames and name in self.local_frames[-1][0] else self.values
        if isinstance(values[name], Reference): values[name].clear()
        else: values[name] = UNINITIALIZED

    def test(self, value, line=None):
        self.tick(line)
        return boolean(value, line)

    def snapshot(self):
        return {name: snapshot_value(value.raw() if isinstance(value,Reference) else value) for name, value in self.values.items()}

    def file_read(self,handle,targets,line=None,**options):
        from .extended import file_read
        return file_read(self,handle,targets,line,**options)

    def file_open(self,handle,mode,name,line=None):
        self.execution.require('files',line).open(handle,mode,name,line)

    def file_close(self,handle,line=None):
        handle.require_open(line); handle.owner.close(handle,line)

    def external_call(self,program,name,arguments,result_spec,line=None):
        callback=self.execution.externals.get((program.upper(),name.upper()))
        if callback is None: raise KarelRuntimeError('External routine is not explicitly linked: '+program+'.'+name,line)
        try:
            result=callback.invoke(self,arguments,line) if getattr(callback,'_karel_link',False) else callback(*arguments)
            if inspect.isgenerator(result): result=yield from result
        except KarelAbort as exc:
            self._aborted=True; self._abort_line=exc.line; raise
        except (KarelPause,KarelStop): raise
        except Exception as exc: raise KarelRuntimeError('External routine failed: '+str(exc),line) from exc
        if self._aborted: raise KarelAbort(self._abort_line)
        if result_spec is None:
            if result is not None: raise KarelRuntimeError('External procedure must return None',line)
            return
        return array_result(result_spec,result,line) if result_spec[0]=='ARRAY' else checked(result_spec,result,line)


from .extended import (ExecutionContext, StringRegisters, PositionRegisters, PortBank, RegisterComments, CallParameters,
                       VariableStore, MemoryFiles, FileHandle, PathValue, QueueValue, RobotContext, RobotState, file_piece,
                        TaskRegistry, KarelPause, KarelStop, update_timers, timer_clock, connect_timer, disconnect_timer,
                        define_condition, condition_control, checkpoint, cooperative_test, pause_execution,abort_execution,
                       run_cooperative, resume_cooperative, stop_cooperative)
from .storage import DirectoryFiles
from .clocks import CalendarClock
from .kinematics import SerialRobotModel
from .scheduling import (TaskScheduler,EventBank,event_condition,edge_condition,lifecycle_condition,
                         signal_event,delay_execution,control_task,condition_scope,TASK_CONSTANTS)
from .control import (SemaphoreBank,ErrorHistory,error_condition,handler_action,cooperative_service,
                      runtime_failure,powerup_cooperative,task_root,request_task_control,ERROR_SEVERITIES)
