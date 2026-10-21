"""Offline compatibility runtime for the implemented source subset.

No robot APIs or device I/O. All value reads and assignments are explicit.
Only the generated module needs this file on a target interpreter.
"""
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import math
import re
import struct
import time


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
    def __repr__(self):
        return 'UNINITIALIZED'


UNINITIALIZED = _Uninitialized()


class _UnknownByte:
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
    """Check the exact result; never silently adopt host floating-point rounding."""
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
    return _real_fraction(Fraction(value), line)


def real_literal(text, line=None):
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
    return StringValueReference(value, line)


def _reference_cells(reference):
    """Storage identity, including aggregate descendants; values are not aliases."""
    cells, seen = {(id(reference.storage), reference.key)}, set()

    def visit(value):
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
        if not 0 <= num_digits <= 254:
            raise KarelRuntimeError('CNV_REAL_STR supports fixed fractional digits in 0..254; scientific/out-of-bound precision rules need validation', line)
        scaled = Fraction(value) * 10 ** num_digits
        if scaled.denominator != 1:
            raise KarelRuntimeError('CNV_REAL_STR decimal rounding is not validated; exact formatting only', line)
        digits = str(abs(scaled.numerator)).rjust(num_digits + 1, '0')
        body = digits if num_digits == 0 else digits[:-num_digits] + '.' + digits[-num_digits:]
        text = ' ' + ('-' if value < 0 else '') + body
        if not 1 <= length <= len(text):
            raise KarelRuntimeError('CNV_REAL_STR requires a positive minimum length no greater than the natural result; padding/invalid-length rules need validation', line)
        _store_conversion_text(name, target, text, line)
        return
    value = integer(source, line)
    length, base = (integer(argument, line) for argument in arguments[:-1])
    if length != 1:
        raise KarelRuntimeError('CNV_INT_STR currently requires length 1; other width/validity rules need validation', line)
    if base != 0 and not 2 <= base <= 16:
        target.clear()
        return
    if base not in (0, 10):
        raise KarelRuntimeError('CNV_INT_STR currently supports decimal bases 0 and 10 only', line)
    text = ' ' + str(value)
    _store_conversion_text(name, target, text, line)


def uninit(value):
    if isinstance(value, JointPosition): return not fully_initialized(value)
    # Whole arrays deliberately rejected by the compiler; no guessed aggregate rule.
    if value is UNKNOWN_BYTE:
        raise KarelRuntimeError('BYTE initialization queries are not implemented')
    return value is UNINITIALIZED


def unary(op, value, line=None):
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
    """Detach one anonymous outer dimension, retaining named inner components."""
    if (not isinstance(spec, tuple) or len(spec) != 3 or spec[:2] != ('ARRAY', None)
            or not isinstance(spec[2], tuple) or not spec[2]):
        raise KarelRuntimeError('ARRAY results require an unsized 1D supported element declaration', line)
    element = spec[2]
    rank = 1
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
    if (not isinstance(value, Array) or not isinstance(value.spec, tuple) or len(value.spec) != 3
            or value.spec[0] != 'ARRAY' or value.spec[2] != spec[2]):
        raise KarelRuntimeError('ARRAY result requires matching anonymous outer storage and exact element type', line)
    shape = array_shape(value.spec)
    if len(shape) != 1 or type(shape[0]) is not int or not 1 <= shape[0] <= 32767:
        raise KarelRuntimeError('ARRAY result requires a concrete 1D size in 1..32767', line)
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
    """Manual vector algebra restricted to exact, initialized binary32 values."""
    left_vector = isinstance(left, Structure) and left.spec == ('VECTOR',)
    right_vector = isinstance(right, Structure) and right.spec == ('VECTOR',)
    both = left_vector and right_vector
    if not (both and op in ('+', '-', '#', '@', '=', '<>')
            or left_vector != right_vector and op in ('*', '/')):
        raise KarelRuntimeError('Unsupported VECTOR operand types/operator', line)
    a = vector_components(left, line) if left_vector else Fraction(real(left, line))
    b = vector_components(right, line) if right_vector else Fraction(real(right, line))

    def intermediate(value):
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
        for i, j in ((0, 1), (0, 2), (1, 2)): intermediate(products[i] + products[j])
        return _real_fraction(sum(products), line)
    if op == '#':
        values = [intermediate(a[j] * b[k]) - intermediate(a[k] * b[j])
                  for j, k in ((1, 2), (2, 0), (0, 1))]
        if not any(values):
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
        values = [a * intermediate(1 / y) for y in b]
    components = [_real_fraction(value, line) for value in values]
    if op == '#' and any(value != 0 and component == 0 for value, component in zip(values, components)):
        raise KarelRuntimeError('VECTOR cross-product underflow needs controller validation', line)
    result = Structure(('VECTOR',))
    result.values.update(zip(('X', 'Y', 'Z'), components))
    return result


def binary(op, left, right, line=None):
    require(left, line)
    require(right, line)
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
        left, right = Fraction(real(left, line)), Fraction(real(right, line))
        if op == '+': result = left + right
        elif op == '-': result = left - right
        elif op == '*': result = left * right
        else:
            if right == 0: raise KarelRuntimeError('Division by zero', line)
            result = left / right
        return _real_fraction(result, line)
    integer(left, line)
    integer(right, line)
    if op == '+': return integer(left + right, line)
    if op == '-': return integer(left - right, line)
    if op == '*': return integer(left * right, line)
    if op in ('DIV', 'MOD'):
        if right == 0:
            raise KarelRuntimeError('Division by zero', line)
        if op == 'MOD':
            if left < 0 or right < 0:
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
        if value not in inverse:
            raise KarelRuntimeError(f'{name} rounding is not validated; inputs limited to -1, -0.5, 0, 0.5, 1', line)
        return float(inverse[value])
    if name not in ('SIN', 'COS', 'TAN'):
        raise KarelRuntimeError('Unsupported exact trigonometric function', line)
    # Check the documented input range before reducing periods; a large angle
    # cannot become valid just because its reduced value is small or zero.
    if not -18000 <= value <= 18000:
        raise KarelRuntimeError(f'{name} angle must be in -18000..18000 degrees', line)
    reduced = value % (180 if name == 'TAN' else 360)
    if name == 'TAN' and reduced == 90:
        raise KarelRuntimeError('TAN is undefined at odd multiples of 90 degrees', line)
    exact = ({0: 0., 30: .5, 90: 1., 150: .5, 180: 0., 210: -.5, 270: -1., 330: -.5}
             if name == 'SIN' else
             {0: 1., 60: .5, 90: 0., 120: -.5, 180: -1., 240: -.5, 270: 0., 300: .5}
             if name == 'COS' else {0: 0., 45: 1., 135: -1.})
    if reduced not in exact:
        raise KarelRuntimeError(f'{name} rounding is not validated; angle outside the exact degree subset', line)
    return exact[reduced]


def exact_atan2(x, y, line=None):
    """Unambiguous exact bearings with KAREL coordinate order, not host atan2."""
    x, y = real(x, line), real(y, line)
    if x == 0 and y == 0:
        raise KarelRuntimeError('ATAN2 is undefined at the origin', line)
    if x < 0 or y < 0:
        raise KarelRuntimeError('ATAN2 negative-coordinate return range needs validation; nonnegative coordinates only', line)
    # No division, squares or host trig: axis and positive diagonal identities
    # remain exact even when intermediate ratios/products would overflow.
    if y == 0: return 0.
    if x == 0: return 90.
    if x == y: return 45.
    raise KarelRuntimeError('ATAN2 rounding is not validated; exact axes and positive diagonal only', line)


def builtin(name, arguments, line=None):
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
        value = Fraction(real(arguments[0], line))
        if value < 0:
            raise KarelRuntimeError('SQRT argument must not be negative', line)
        numerator = math.isqrt(value.numerator)
        denominator = math.isqrt(value.denominator)
        # A reduced rational has a rational square root exactly when both
        # numerator and denominator are squares. Never adopt a rounded host root.
        if numerator * numerator != value.numerator or denominator * denominator != value.denominator:
            raise KarelRuntimeError('SQRT rounding is not validated; exact rational roots only', line)
        return _real_fraction(Fraction(numerator, denominator), line)
    if name in ('ROUND', 'TRUNC'):
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
        if len(array_dimensions(array.spec)) != 1:
            raise KarelRuntimeError('ARRAY_LEN on multidimensional arrays needs dimension-count validation', line)
        return array.shape[0]
    if name == 'UNINIT': return uninit(arguments[0])
    if name == 'SUB_STR':
        source = ascii_string(arguments[0], line)
        start, count = (integer(x, line) for x in arguments[1:])
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
        if search == '':
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
    if isinstance(value, JointPosition): return {'axes': [snapshot_value(x) for x in value.values]}
    if value is UNINITIALIZED:
        return {'uninitialized': True}
    if value is UNKNOWN_BYTE: return {'unknown_byte': True}
    if isinstance(value, Array):
        return value.snapshot()
    if isinstance(value, Structure):
        return {name: snapshot_value(x) for name, x in value.values.items()}
    return value


class State:
    def __init__(self, declarations, constants, *, sleep=None, write=None, joint_axes=None):
        if joint_axes is not None and (type(joint_axes) is not int or not 1 <= joint_axes <= 9):
            raise ValueError('joint_axes must be None or an INTEGER in 1..9')
        if sleep is not None and not callable(sleep):
            raise TypeError('sleep must be a synchronous callable accepting seconds, or None')
        if write is not None and not callable(write):
            raise TypeError('write must be a synchronous callable accepting text, or None')
        self._sleep = time.sleep if sleep is None else sleep
        self._write = write
        self.joint_axes = joint_axes
        self.write_requests = []
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

    def tick(self, line=None):
        if self._aborted: raise KarelAbort(self._abort_line)
        self.steps += 1
        if self.steps > self.max_steps:
            raise KarelRuntimeError(f'Execution step budget exceeded ({self.max_steps})', line)

    def begin(self, max_steps):
        if self._aborted: raise KarelAbort(self._abort_line)
        if type(max_steps) is not int or max_steps < 1:
            raise ValueError('max_steps must be a positive integer')
        self.max_steps, self.steps = max_steps, 0
        self.write_requests.clear()

    def write_string(self, text, line=None, *, width=None, alignment=0):
        """Record an offline request or call a supplied text sink; not device I/O."""
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

    def enter_routine(self, declarations, line=None, arguments=None):
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

    def leave_routine(self):
        self.call_depth -= 1
        self.local_frames.pop()

    def raw(self, name):
        if self.local_frames and name in self.local_frames[-1][0]:
            value = self.local_frames[-1][1][name]
            return value.raw() if isinstance(value, Reference) else value
        return self.constants[name] if name in self.constants else self.values[name]

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
        return {name: snapshot_value(value) for name, value in self.values.items()}
