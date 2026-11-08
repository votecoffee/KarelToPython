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


class TextInputIncomplete(KarelRuntimeError):
    """An explicitly unfinished text stream needs more bytes, not a retry of bad data."""


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
ASSOCIATION_TYPES = ('COMMON_ASSOC','GROUP_ASSOC')
DATA_RECORD_TYPES = ('XYZWPR', 'CONFIG', 'VECTOR', 'POSITION', 'XYZWPREXT', *ASSOCIATION_TYPES)
POSITIONAL_VALUE_TYPES = tuple(name for name in DATA_RECORD_TYPES if name != 'VECTOR') + ('JOINTPOS',)
POSITION_READ_ONLY_FIELDS = ('NORMAL', 'ORIENT', 'APPROACH')
POSITION_AXIS_FUNCTIONS = {'APPROACH': 2, 'ORIENT': 1}
RECORD_TYPES = ('STRUCTURE', *DATA_RECORD_TYPES)
DATA_RECORD_FIELDS = {
    'COMMON_ASSOC': tuple((name,INTEGER) for name in ('SEGTERMTYPE','SEGDECELTOL','SEGRELACCEL','SEGTIMESHFT')),
    'GROUP_ASSOC': tuple((name,INTEGER) for name in ('SEGRELSPEED','SEGMOTYPE','SEGORIENTYPE')) + (('SEGBREAK',BOOLEAN),),
    'VECTOR': tuple((name, REAL) for name in ('X', 'Y', 'Z')),
    'CONFIG': tuple((name, INTEGER) for name in ('CFG_TURN_NO1', 'CFG_TURN_NO2', 'CFG_TURN_NO3'))
              + tuple((name, BOOLEAN) for name in ('CFG_FLIP', 'CFG_LEFT', 'CFG_UP', 'CFG_FRONT')),
    'XYZWPR': tuple((name, REAL) for name in ('X', 'Y', 'Z', 'W', 'P', 'R')) + (('CONFIG_DATA', ('CONFIG',)),),
    'XYZWPREXT': tuple((name, REAL) for name in ('X', 'Y', 'Z', 'W', 'P', 'R'))
                + (('CONFIG_DATA', ('CONFIG',)),) + tuple((name, REAL) for name in ('EXT1', 'EXT2', 'EXT3')),
    'POSITION': tuple((name, ('VECTOR',)) for name in (*POSITION_READ_ONLY_FIELDS, 'LOCATION'))
                + (('CONFIG_DATA', ('CONFIG',)),),
}


# Documented data layouts, represented with the existing nominal STRUCTURE
# schema. The obsolete association fields of STD_PTH_NODE are not modeled.
PREDEFINED_STRUCTURES = {
    'STD_PTH_NODE': ('STRUCTURE','STD_PTH_NODE',(('NODE_POS',('POSITION',)),)),
    'XWORK_T': ('STRUCTURE','XWORK_T',(('SESSION',INTEGER),)),
    'COL_DESC_T': ('STRUCTURE','COL_DESC_T',tuple((name,spec) for name,spec in (
        ('ITEM_TYPE',INTEGER),('START_COL',INTEGER),('FIELD_WIDTH',INTEGER),('ENUM_ELE',INTEGER),
        ('ENUM_DICT',('STRING',4)),('FORMAT_SPEC',('STRING',80)),
        ('MIN_INTEGER',INTEGER),('MAX_INTEGER',INTEGER),('MIN_REAL',REAL),('MAX_REAL',REAL),
        ('CLEAR_FLAG',INTEGER),('LOWER_CASE',INTEGER)))),
    'DISP_DAT_T': ('STRUCTURE','DISP_DAT_T',(
        ('WIN_START',('ARRAY',4,SHORT)),('WIN_END',('ARRAY',4,SHORT)),
        ('CURR_WIN',SHORT),('CURSOR_ROW',SHORT),('LINS_PER_PG',SHORT),
        ('CURS_ST_COL',('ARRAY',10,SHORT)),('CURS_EN_COL',('ARRAY',10,SHORT)),
        ('CURR_FIELD',SHORT),('LAST_FIELD',SHORT),('CURR_IT_NUM',SHORT),
        ('SOB_IT_NUM',SHORT),('EOB_IT_NUM',SHORT),('LAST_IT_NUM',SHORT),('MENU_ID',SHORT))),
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


def real_integral_kind(target,source):
    """Describe the source/value conversion without relaxing typed references."""
    return target in (('INTEGER',),('BYTE',),('SHORT',)) and source==('REAL',)


def real_integral_value(target,value,line=None):
    """Pythonic truncation toward zero, followed by ordinary storage checks."""
    if not _pythonic() or not real_integral_kind(target,('REAL',)):
        raise KarelRuntimeError('REAL narrowing requires a Pythonic integral receiver',line)
    require(value,line)
    if type(value) is not float or not math.isfinite(value):
        raise KarelRuntimeError('REAL narrowing requires finite REAL data',line)
    result=math.trunc(value)
    checked(target,result,line)
    return result


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


def array_prefix_type(spec,count):
    """Describe a value-only prefix ending inside a flat ARRAY component."""
    if type(count) is not int or count<1 or _array_conversion_layout(spec) is None:return None
    while spec[0]=='ARRAY':
        shape=array_shape(spec);width=len(shape)
        if count<width:
            remaining=shape[count:]
            return ('ARRAY',remaining[0] if len(remaining)==1 else remaining,spec[2])
        count-=width;spec=spec[2]
        if count==0:return None
    return None


def array_prefix_value(array,index,expected,line=None):
    """Copy a row/plane value without introducing a writable storage view."""
    if not _pythonic():raise KarelRuntimeError('ARRAY prefix values require Pythonic mode',line)
    indexes=index if type(index) is tuple else (index,)
    if array_prefix_type(expected,len(indexes)) is None:
        raise KarelRuntimeError('ARRAY prefix requires an incomplete flat data selection',line)
    if type(array) is not Array:raise KarelRuntimeError('ARRAY prefix requires exact ARRAY storage',line)
    _validate_data_schema(array.spec,line)
    if not parameter_accepts(expected,array.spec):
        raise KarelRuntimeError('ARRAY prefix storage does not match its declared schema',line)
    # Validate every known source leaf and detach before exposing any selected data.
    current=_aggregate_value(array.spec,array,line)
    declared=array_prefix_type(expected,len(indexes))
    def finish(selected):
        concrete=_array_conversion_spec(declared,selected.spec)
        return selected if selected.spec==concrete else convert_array_schema(concrete,selected,line)
    while True:
        width=len(current.shape)
        if len(indexes)<width:
            supplied=len(indexes);suffix=current.shape[supplied:];offset=0
            for number,(subscript,dimension) in enumerate(zip(indexes,current.shape),1):
                integer(subscript,line)
                if not 1<=subscript<=dimension:
                    raise KarelRuntimeError(f'Array index {subscript} outside 1..{dimension} in dimension {number}',line)
                offset=offset*dimension+subscript-1
            size=math.prod(suffix)
            result=Array(('ARRAY',suffix[0] if len(suffix)==1 else suffix,current.spec[2]))
            result.values[:]=current.values[offset*size:(offset+1)*size]
            return finish(result)
        offset=current.offset(indexes[:width],line)
        current=current.values[offset];indexes=indexes[width:]
        if not indexes:
            if type(current) is not Array:raise KarelRuntimeError('ARRAY prefix requires remaining ARRAY data',line)
            return finish(current)
        if type(current) is not Array:raise KarelRuntimeError('ARRAY prefix requires nested ARRAY storage',line)


def array_prefix_target(array,index,expected,line=None):
    """Capture an existing row/plane for statement-only assignment or input."""
    if not _pythonic():raise KarelRuntimeError('ARRAY prefix targets require Pythonic mode',line)
    indexes=index if type(index) is tuple else (index,)
    if array_prefix_type(expected,len(indexes)) is None:
        raise KarelRuntimeError('ARRAY prefix target requires an incomplete flat selection',line)
    if type(array) is not Array:raise KarelRuntimeError('ARRAY prefix target requires exact ARRAY storage',line)
    _validate_data_schema(array.spec,line)
    if not parameter_accepts(expected,array.spec):
        raise KarelRuntimeError('ARRAY prefix target storage does not match its declaration',line)
    _aggregate_value(array.spec,array,line)
    current=array
    while True:
        width=len(current.shape)
        if len(indexes)<width:
            suffix=current.shape[len(indexes):];offset=0
            for number,(subscript,dimension) in enumerate(zip(indexes,current.shape),1):
                integer(subscript,line)
                if not 1<=subscript<=dimension:
                    raise KarelRuntimeError(f'Array index {subscript} outside 1..{dimension} in dimension {number}',line)
                offset=offset*dimension+subscript-1
            size=math.prod(suffix);spec=('ARRAY',suffix[0] if len(suffix)==1 else suffix,current.spec[2])
            return _ArrayPrefixTarget(spec,current.values,range(offset*size,(offset+1)*size),line)
        offset=current.offset(indexes[:width],line)
        current=current.values[offset];indexes=indexes[width:]
        if type(current) is not Array:raise KarelRuntimeError('ARRAY prefix target requires existing nested ARRAY storage',line)
        if not indexes:return _ArrayPrefixTarget(current.spec,current.values,range(len(current.values)),line)


def joint_axis_access(spec,count):
    """Recognize a single terminal joint axis after complete ARRAY components."""
    if type(count) is not int or not 1<=count<=4:return False
    rank=0
    try:
        for _ in range(4):
            if type(spec) is not tuple or not spec:return False
            if spec[0]=='JOINTPOS':return bool(joint_width(spec)) and count==rank+1
            if spec[0]!='ARRAY' or len(spec) not in (3,4):return False
            shape=array_shape(spec)
            if not 1<=len(shape)<=3 or rank+len(shape)>3:return False
            if any(size is not None and (type(size) is not int or not 1<=size<=32767) for size in shape):return False
            rank+=len(shape);spec=spec[2]
    except (KarelRuntimeError,TypeError,IndexError):pass
    return False


def positional_conversion_kind(target,source):
    """Describe supported context-free positional changes, without coercing data."""
    if type(target) is not tuple or type(source) is not tuple or not target or not source or target==source:return None
    cartesians=(('POSITION',),('XYZWPR',),('XYZWPREXT',))
    if target in cartesians and source in cartesians:return 'cartesian'
    if target[0]==source[0]=='JOINTPOS':
        try:joint_width(target);joint_width(source)
        except (KarelRuntimeError,TypeError,IndexError):return None
        return 'joint_width'
    return None


def _array_conversion_layout(spec):
    """Validate ARRAY boundaries while retaining their logical axes and names."""
    parts=[];rank=0
    try:
        while True:
            if type(spec) is not tuple or len(spec) not in (3,4) or spec[0]!='ARRAY':return None
            shape=array_shape(spec);name=array_identity(spec)
            if (not shape or any(size is not None and (type(size) is not int or not 1<=size<=32767) for size in shape)
                    or name is not None and any(size is None for size in shape)
                    or parts and name is None):return None
            rank+=len(shape)
            if rank>3:return None
            parts.append((shape,name));spec=spec[2]
            if type(spec) is not tuple or not spec:return None
            if spec[0]!='ARRAY':return tuple(parts)
    except (KarelRuntimeError,TypeError,IndexError):return None


def _source_array_pair(target,source):
    """Require matching logical dimensions across explicit ARRAY layouts."""
    layouts=[_array_conversion_layout(spec) for spec in (target,source)]
    if any(parts is None for parts in layouts):return False
    shapes=[tuple(size for shape,name in parts for size in shape) for parts in layouts]
    return len(shapes[0])==len(shapes[1]) and all(a is None or b is None or a==b for a,b in zip(*shapes))


def array_schema_compatible(target,source):
    """Source-only data ARRAY copies; generic typed-reference contracts stay exact."""
    if not _source_array_pair(target,source):return False
    first,second=array_leaf_spec(target),array_leaf_spec(source)
    if first[0]==second[0]=='STRING':
        if any(len(spec)!=2 or spec[1] is not None and (type(spec[1]) is not int or not 1<=spec[1]<=254) for spec in (first,second)):return False
        return all(spec[1] is not None or not any(name is not None for shape,name in _array_conversion_layout(array)) for spec,array in ((first,target),(second,source)))
    return first==second and first[0] in ('INTEGER','BOOLEAN','REAL','BYTE','SHORT','JOINTPOS',*RECORD_TYPES)


def array_schema_kind(target,source):
    if not array_schema_compatible(target,source):return None
    first,second=array_leaf_spec(target),array_leaf_spec(source)
    if first[0]=='STRING' and first[1] is not None and first[1]!=second[1]:return 'string_capacity'
    layouts=[_array_conversion_layout(spec) for spec in (target,source)]
    if tuple(len(shape) for shape,name in layouts[0])!=tuple(len(shape) for shape,name in layouts[1]):return 'component_layout'
    if tuple(name for shape,name in layouts[0])!=tuple(name for shape,name in layouts[1]):return 'nominal_identity'
    return None


def convert_array_schema(target,value,line=None):
    """Capture a data ARRAY into an independent declared receiver schema."""
    if not _pythonic():raise KarelRuntimeError('ARRAY schema conversion requires Pythonic mode',line)
    if type(value) is not Array or not array_schema_compatible(target,value.spec):
        raise KarelRuntimeError('ARRAY schema conversion requires matching logical dimensions and compatible data terminals',line)
    source=_aggregate_value(value.spec,value,line);result=_array_conversion_storage(target,source,line)
    leaf=array_leaf_spec(result.spec)
    for (output,index),(storage,key) in zip(_array_conversion_cells(result),_array_conversion_cells(source)):
        item=storage[key]
        output[index]=checked(leaf,item,line) if leaf[0]=='STRING' and item is not UNINITIALIZED else item
    return result


def _array_conversion_cells(value):
    """Visit only ARRAY terminal cells in checked row-major component order."""
    if value.spec[2][0]=='ARRAY':
        for child in value.values:yield from _array_conversion_cells(child)
    else:
        for index in range(len(value.values)):yield value.values,index


def _array_conversion_spec(target,source_spec):
    axes=iter(array_dimensions(source_spec));source_leaf=array_leaf_spec(source_spec)
    def concrete(expected):
        dimensions=tuple(next(axes) for _ in array_shape(expected))
        shape=dimensions if type(expected[1]) is tuple else dimensions[0]
        element=concrete(expected[2]) if expected[2][0]=='ARRAY' else source_leaf if expected[2]==('STRING',None) else expected[2]
        return ('ARRAY',shape,element,*expected[3:])
    return concrete(target)


def _array_conversion_storage(target,source,line=None):
    spec=_array_conversion_spec(target,source.spec)
    if scalar_leaf_count(spec)>32767:raise KarelRuntimeError('ARRAY conversion exceeds 32767 scalar leaves',line)
    return Array(spec)


def positional_array_kind(target,source):
    """Positional ARRAY values retain matching component dimensions."""
    return positional_conversion_kind(array_leaf_spec(target),array_leaf_spec(source)) if _source_array_pair(target,source) else None


def numeric_array_kind(target,source):
    """Numeric ARRAY values use scalar domains and independent receiver schemas."""
    try:
        if not _source_array_pair(target,source):return None
        first,second=array_leaf_spec(target),array_leaf_spec(source)
        if any(type(spec) is not tuple or len(spec)!=1 or type(spec[0]) is not str for spec in (first,second)):return None
        integral=(('INTEGER',),('BYTE',),('SHORT',))
        if first==second:return None
        if config_word_kind(first,second):return 'config_word'
        if first==('REAL',) and second in integral:return 'promote_real'
        if first in integral and second in integral:return 'checked_integral'
        if real_integral_kind(first,second):return 'truncate_real'
    except (KarelRuntimeError,TypeError,IndexError):return None
    return None


def convert_numeric_array(target,value,line=None):
    """Stage checked numeric leaves and missing data before receiver publication."""
    if not _pythonic():raise KarelRuntimeError('Numeric ARRAY conversion requires Pythonic mode',line)
    if type(value) is not Array or numeric_array_kind(target,value.spec) is None:
        raise KarelRuntimeError('Numeric ARRAY conversion requires matching component shapes and convertible numeric terminals',line)
    source=_aggregate_value(value.spec,value,line)
    result=_array_conversion_storage(target,source,line);leaf=array_leaf_spec(result.spec)
    source_leaf=array_leaf_spec(source.spec);word=config_word_kind(leaf,source_leaf)
    for (output,index),(storage,key) in zip(_array_conversion_cells(result),_array_conversion_cells(source)):
        item=storage[key]
        output[index]=(_config_word_data(leaf,source_leaf,item,line) if word
                       else UNINITIALIZED if item is UNINITIALIZED else checked(leaf,real_integral_value(leaf,item,line),line) if real_integral_kind(leaf,source_leaf) else checked(leaf,require(item,line),line))
    return result


def kinematic_array_kind(target,source):
    """Describe explicit-model ARRAY conversions without consulting a robot."""
    if not _source_array_pair(target,source):return None
    first,second=array_leaf_spec(target),array_leaf_spec(source)
    if type(first) is not tuple or not first or type(second) is not tuple or not second:return None
    poses=(('POSITION',),('XYZWPR',),('XYZWPREXT',))
    joint=first if first[0]=='JOINTPOS' and second in poses else second if second[0]=='JOINTPOS' and first in poses else None
    if joint is None:return None
    try:joint_width(joint)
    except (KarelRuntimeError,TypeError,IndexError):return None
    return 'inverse' if first[0]=='JOINTPOS' else 'forward'


def prepare_kinematic_array(target,value,line=None):
    """Preflight complete geometry and allocate private output before adapters."""
    if not _pythonic():raise KarelRuntimeError('Kinematic ARRAY conversion requires Pythonic mode',line)
    if type(value) is not Array or kinematic_array_kind(target,value.spec) is None:
        raise KarelRuntimeError('Kinematic ARRAY conversion requires matching component shapes and joint/Cartesian terminals',line)
    source=_aggregate_value(value.spec,value,line,allow_partial=False)
    if array_leaf_spec(source.spec)[0]!='JOINTPOS':
        for storage,key in _array_conversion_cells(source):storage[key]=frame_value(storage[key],line)
    return source,_array_conversion_storage(target,source,line)


def convert_positional_array(target,value,line=None):
    """Prepare an independent complete ARRAY before publishing any destination."""
    if not _pythonic():raise KarelRuntimeError('Positional ARRAY conversion requires Pythonic mode',line)
    if type(value) is not Array or positional_array_kind(target,value.spec) is None:
        raise KarelRuntimeError('Positional ARRAY conversion requires matching component shapes and convertible terminal types',line)
    source=_aggregate_value(value.spec,value,line,allow_partial=False)
    result=_array_conversion_storage(target,source,line);leaf=array_leaf_spec(result.spec)
    convert=convert_joint_width if leaf[0]=='JOINTPOS' else convert_position
    for (output,index),(storage,key) in zip(_array_conversion_cells(result),_array_conversion_cells(source)):
        output[index]=convert(leaf,storage[key],line)
    return result


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
    if _pythonic() and (type(spec) is not tuple or not spec or type(spec[0]) is not str):
        raise KarelRuntimeError('Malformed concrete value type specification', line)
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
        if _pythonic():
            if not isinstance(value, JointPosition) or value.spec != spec:
                raise KarelRuntimeError('Joint copy requires identical declared axis count', line)
            return _aggregate_value(spec, value, line)
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
        if _pythonic(): return _aggregate_value(spec, value, line)
        if array_leaf_spec(spec)[0] in (*RECORD_TYPES, 'JOINTPOS') and not fully_initialized(value):
            raise KarelRuntimeError('Whole-array copying with uninitialized or unknown STRUCTURE fields needs KAREL validation', line)
        validate_config_contents(value, line)
        return value.clone()
    if spec[0] in RECORD_TYPES:
        if not isinstance(value, Structure) or value.spec != spec:
            raise KarelRuntimeError('Whole-structure assignment requires identical named type', line)
        if _pythonic(): return _aggregate_value(spec, value, line)
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


def service_value(value, line=None):
    """Capture ordinary service inputs with their existing complete-value checks."""
    if _pythonic() and isinstance(value,(Array,Structure,JointPosition)):
        if isinstance(value,Array) and array_leaf_spec(value.spec)[0] not in (*RECORD_TYPES,'JOINTPOS'):
            return _partial_aggregate_value(value.spec,value,line)
        return _aggregate_value(value.spec,value,line,allow_partial=False)
    return assignment_value(value,line)


def path_node_seed(state,spec,value,line=None):
    """Charge the source capture before copying a complete PATH node seed."""
    if type(value) is not Structure or value.spec!=spec:
        raise KarelRuntimeError('PATH node seed requires matching declared STRUCTURE storage',line)
    for _ in range(_validate_data_schema(spec,line)):
        state.tick(line)
    return _aggregate_value(spec,value,line,allow_partial=False)


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
        if file_storage_type(spec) and not _pythonic():
            raise KarelRuntimeError('FILE ARRAY storage requires Pythonic mode')
        if collection_array_type(spec) and not _pythonic():
            raise KarelRuntimeError('Collection ARRAY storage requires Pythonic mode')
        if spec[2][0] == 'ARRAY' and array_identity(spec[2]) is None:
            raise KarelRuntimeError('Nested ARRAY elements require a separately named type')
        if collection_array_type(spec):
            from .storage import collection_array_cost
            try:collection_array_cost(spec)
            except (ValueError,KarelRuntimeError) as exc:raise KarelRuntimeError(str(exc)) from exc
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
        if file_storage_type(self.spec):
            raise KarelRuntimeError('FILE ARRAY storage cannot be copied; pass its reference')
        if collection_array_type(self.spec):
            raise KarelRuntimeError('Collection ARRAY storage cannot be copied; pass its reference')
        result = Array(self.spec)
        result.values = [value.clone() if isinstance(value, (Array, Structure, JointPosition)) else value
                         for value in self.values]
        return result


def file_storage_type(spec):
    """FILE descriptors, including reference-only ARRAY roots; never data values."""
    return spec[0] == 'FILE' or spec[0] == 'ARRAY' and array_leaf_spec(spec)[0] == 'FILE'


def collection_type(spec):
    return type(spec) is tuple and bool(spec) and (spec==('QUEUE_TYPE',) or spec[0]=='PATH' and len(spec)==3)


def collection_source_value(spec,value,line=None,*,source_spec=None):
    """Snapshot exact scalar logical data; never copy queue buffer ownership."""
    from .extended import path_variable_value,queue_variable_value
    if not _pythonic() or not collection_type(spec):
        raise KarelRuntimeError('Logical collection source values require Pythonic scalar schemas',line)
    if source_spec is not None and source_spec!=spec:
        raise KarelRuntimeError('Logical collection value differs from its declared source schema',line)
    expected=PathValue if spec[0]=='PATH' else QueueValue
    if type(value) is not expected or value.spec!=spec:
        raise KarelRuntimeError('Logical collection source requires matching owned storage',line)
    # The checked logical codec validates all data before any destination is touched.
    copied=path_variable_value(spec,value,line) if spec[0]=='PATH' else queue_variable_value(value,line)
    if spec[0]=='PATH':
        pending=[value];seen=set()
        while pending:
            item=pending.pop()
            if type(item) is PathValue:
                owned=(item,item.nodes);children=[item.data,*item.nodes]
            elif type(item) is Structure:
                owned=(item,item.values);children=list(item.values.values())
            elif type(item) in (Array,JointPosition):
                owned=(item,item.values);children=item.values
            else:continue
            for storage in owned:
                if id(storage) in seen:raise KarelRuntimeError('Logical PATH source storage overlaps',line)
                seen.add(id(storage))
            pending.extend(children)
    return copied


def collection_argument(spec,value,line=None,*,source_spec=None):
    copied=collection_source_value(spec,value,line,source_spec=source_spec)
    return Reference(spec,{'value':copied},'value')


def collection_assign(reference,value,line=None):
    """Publish only after both selections validate, retaining root/header aliases."""
    from .variable_archives import ordinary,replace_collections
    if not ordinary(reference):raise KarelRuntimeError('Logical collection assignment requires ordinary writable storage',line)
    copied=collection_source_value(reference.spec,value,line)
    collection_source_value(reference.spec,reference.raw(),line,source_spec=reference.spec)
    reference.storage[reference.key]=replace_collections(reference.raw(),copied)


def using_path_header(spec,value,line=None,*,reference=False):
    """Select a checked existing header, or detach a computed PATH header value."""
    from .variable_archives import ordinary
    if not collection_type(spec) or spec[0]!='PATH' or spec[2] is None:
        raise KarelRuntimeError('USING PATH requires an explicit PATHHEADER',line)
    if reference:
        if not ordinary(value) or value.spec!=spec:
            raise KarelRuntimeError('USING PATH requires an ordinary matching storage reference',line)
        source=value.raw()
    else:source=value
    copied=collection_source_value(spec,source,line,source_spec=spec)
    header=(source if reference else copied).data
    if type(header) is not Structure or header.spec!=spec[2]:
        raise KarelRuntimeError('USING PATH requires an existing shaped header',line)
    # Freeze the selected header object: later root/cell replacement cannot retarget it.
    return Reference(spec[2],{'value':header},'value')


def collection_array_type(spec):
    """ARRAY roots whose terminal cells are owned logical collections."""
    return spec[0]=='ARRAY' and array_leaf_spec(spec)[0] in ('PATH','QUEUE_TYPE')


def collection_array_source_accepts(target,source):
    """Source logical copies retain exact components and concrete dimensions."""
    try:
        if not collection_array_type(target) or not collection_array_type(source):return False
        if target[2]!=source[2]:return False
        if array_identity(target) is not None:return target==source
        expected,actual=array_shape(target),array_shape(source)
        return len(expected)==len(actual) and all(a is None or b is None or a==b for a,b in zip(expected,actual))
    except (KarelRuntimeError,TypeError,IndexError):return False


def path_array_conversion_layout(target,source):
    """Keep each ARRAY component rank while converting compatible PATH cells."""
    from .extended import path_conversion_layout
    if not _source_array_pair(target,source):return None
    ranks=lambda spec:tuple(len(shape) for shape,_ in _array_conversion_layout(spec))
    if ranks(target)!=ranks(source):return None
    first,second=array_leaf_spec(target),array_leaf_spec(source)
    return path_conversion_layout(first,second,model=True) if first!=second else None


def collection_array_source_value(target,value,line=None,*,source_spec=None):
    """Detach bounded logical data without relaxing generic ARRAY codecs."""
    from .extended import collection_array_variable_value
    if not _pythonic() or type(value) is not Array:
        raise KarelRuntimeError('Collection ARRAY source values require Pythonic owned storage',line)
    if source_spec is not None:
        matches=collection_array_source_accepts(source_spec,value.spec) if None in array_dimensions(source_spec) else source_spec==value.spec
        if not matches:raise KarelRuntimeError('Collection ARRAY value differs from its declared source schema',line)
    if not collection_array_source_accepts(target,value.spec):
        raise KarelRuntimeError('Collection ARRAY source copies require matching schemas and dimensions',line)
    copied=collection_array_variable_value(value.spec,value,line)
    return copied


def collection_array_result(spec,value,line=None,*,source_spec=None):
    copied=collection_array_source_value(spec,value,line,source_spec=source_spec)
    shape=copied.shape[0] if len(copied.shape)==1 else copied.shape
    copied.spec=('ARRAY',shape,spec[2])+((spec[3],) if len(spec)==4 else ())
    return copied


def external_collection_result(spec,value,line=None,*,check=None):
    """Detach an explicitly linked callback's exact logical value or typed JSON."""
    if not _pythonic():raise KarelRuntimeError('External collection results require Pythonic mode',line)
    from .storage import tuple_spec,decode_typed,collection_array_cost
    try:
        if not (collection_type(spec) or collection_array_type(spec)):
            raise ValueError('External collection results require collection schemas')
        if type(value) is dict:
            if set(value)!={'type','value'} or type(value['type']) is not list:
                raise ValueError('Typed collection result requires exactly type and value, with a type list')
            actual=tuple_spec(value['type'])
            matches=actual==spec if collection_type(spec) else collection_array_source_accepts(spec,actual)
            if not matches:raise ValueError('Typed collection result differs from its declared schema')
            if spec[0]=='PATH':
                # Check total scalar storage before the codec allocates any nodes.
                payload=value['value'];node=spec[1] or PREDEFINED_STRUCTURES['STD_PTH_NODE']
                if (type(payload) is not dict or set(payload)!={'nodes','data'} or type(payload['nodes']) is not list
                        or len(payload['nodes'])>32767):raise ValueError('PATH result requires bounded nodes and data')
                width=_validate_data_schema(node,line);header=_validate_data_schema(spec[2],line) if spec[2] else 0
                if header+len(payload['nodes'])*width>32767:raise ValueError('PATH result exceeds 32767 scalar leaves')
            _charge_external_result(actual,value,line,check)
            _,value=decode_typed(value)
        elif check is not None:
            if not collection_type(spec) and (type(value) is not Array or not collection_array_source_accepts(spec,value.spec)):
                raise ValueError('Logical collection ARRAY result differs from its declared schema')
            actual=spec if collection_type(spec) else value.spec
            _charge_external_result(actual,value,line,check)
        if not collection_type(spec) and type(value) is Array:collection_array_cost(value.spec)
        return collection_source_value(spec,value,line) if collection_type(spec) else collection_array_result(spec,value,line)
    except (ValueError,KarelRuntimeError,TypeError,KeyError,IndexError,AttributeError,RecursionError,OverflowError) as error:
        raise KarelRuntimeError('External collection result: '+str(error),line) from error


def _external_data_payload(spec,payload,line=None):
    """Check canonical data shapes before the general state codec can normalize them."""
    kind=spec[0]
    if type(payload) is dict and ('uninitialized' in payload or 'unknown_byte' in payload):
        if (set(payload) not in ({'uninitialized'},{'unknown_byte'}) or next(iter(payload.values())) is not True
                or kind in ('ARRAY','JOINTPOS',*RECORD_TYPES)
                or 'unknown_byte' in payload and kind!='BYTE'):
            raise ValueError('External data requires exact scalar missing markers and shaped containers')
        return
    if kind=='ARRAY':
        def dimensions(shape,value):
            if type(value) is not list or len(value)!=shape[0]:raise ValueError('External data ARRAY payload must match its canonical shape')
            for item in value:
                if len(shape)>1:dimensions(shape[1:],item)
                else:_external_data_payload(spec[2],item,line)
        dimensions(array_shape(spec),payload)
    elif kind in RECORD_TYPES:
        fields=dict(record_fields(spec))
        if type(payload) is not dict or set(payload)!=set(fields):raise ValueError('External data record payload requires exact declared field names')
        for name,field in fields.items():_external_data_payload(field,payload[name],line)
    elif kind=='JOINTPOS':
        if type(payload) is not dict or set(payload)!={'axes'} or type(payload['axes']) is not list or len(payload['axes'])!=joint_width(spec):
            raise ValueError('External joint payload requires exactly its declared axes')
        for item in payload['axes']:_external_data_payload(REAL,item,line)
    elif kind=='STRING' and len(ascii_string(payload,line))>spec[1]:
        raise ValueError('External STRING payload exceeds its declared capacity')


def _external_data_decode(row,line=None,*,selector=False,check=None):
    from .storage import tuple_spec,decode_typed
    if type(row) is not dict or set(row)!={'type','value'} or type(row['type']) is not list:
        raise ValueError('Typed external data requires exactly type and value, with a type list')
    spec=tuple_spec(row['type']);_validate_data_schema(spec,line)
    _charge_external_result(spec,row,line,check)
    _external_data_payload(spec,row['value'],line)
    _,value=decode_typed(row);value=_aggregate_value(spec,value,line)
    if not selector and spec[0] not in ('ARRAY','JOINTPOS',*RECORD_TYPES):value=require(checked(spec,value,line),line)
    return spec,value


def external_data_result(spec,value,line=None,*,check=None):
    """Decode only explicitly typed callback data; preserve exact result interfaces."""
    if not _pythonic():raise KarelRuntimeError('Typed external data results require Pythonic mode',line)
    try:
        actual,copied=_external_data_decode(value,line,check=check)
        if spec[0]=='ARRAY':return array_result(spec,copied,line)
        if not parameter_accepts(spec,actual):raise ValueError('Typed external data differs from its declared schema')
        return checked(spec,copied,line)
    except (ValueError,KarelRuntimeError,TypeError,KeyError,IndexError,AttributeError,RecursionError,OverflowError) as error:
        raise KarelRuntimeError('External data result: '+str(error),line) from error


def _external_value_units(spec,value,line=None):
    """Preflight explicit data or logical snapshots before decoding/copying contents."""
    from .storage import collection_array_cost,_collection_array_units
    from .variable_archives import schema
    if type(spec) is not tuple or not spec or type(spec[0]) is not str:
        return _validate_data_schema(spec,line)
    if spec[0] in ('PATH','QUEUE_TYPE'):return schema(spec,value)
    if spec[0]=='ARRAY' and collection_array_cost(spec) is not None:
        if type(value) is not Array:return schema(spec,value)
        units=0
        def visit(expected,item):
            nonlocal units
            if expected[0]!='ARRAY':
                units+=_collection_array_units(expected,item,False)
                if units>32767:raise ValueError('External collection ARRAY exceeds 32767 units including contents')
                return
            shape=array_shape(expected)
            if (type(item) is not Array or item.spec!=expected or item.shape!=shape
                    or not _array_storage(item.values,line) or len(item.values)!=math.prod(shape)):
                raise ValueError('External collection ARRAY storage does not match its schema')
            for child in item.values:visit(expected[2],child)
        visit(spec,value)
        return units
    return _validate_data_schema(spec,line)


def _charge_external_result(spec,value,line,check):
    if check is None:return
    from .storage import tuple_spec,_collection_array_units

    encoded=type(value) is dict
    payload=value['value'] if encoded else value

    def footprint():
        if collection_type(spec):
            # Plain scalar collection results keep their existing separate limits.
            units=_collection_array_units(spec,payload,encoded)
            if spec[0]=='PATH' and units>32768:raise ValueError('PATH result exceeds 32767 scalar leaves')
            return units
        return _external_value_units(spec,payload,line)

    units=footprint()
    for _ in range(units):check()
    if encoded and (set(value)!={'type','value'} or type(value['type']) is not list
                    or tuple_spec(value['type'])!=spec or value['value'] is not payload):
        raise ValueError('External result changed during preparation')
    if footprint()!=units:raise ValueError('External result size changed during preparation')


def _external_value_snapshot(spec,value,line=None):
    if collection_type(spec):return collection_source_value(spec,value,line,source_spec=spec)
    if collection_array_type(spec):return collection_array_source_value(spec,value,line,source_spec=spec)
    return _aggregate_value(spec,value,line)


def _external_value_decode(row,line=None,*,selector=False):
    from .storage import tuple_spec
    if type(row) is not dict or set(row)!={'type','value'} or type(row['type']) is not list:
        raise ValueError('Typed external value requires exactly type and value, with a type list')
    spec=tuple_spec(row['type']);_external_value_units(spec,row['value'],line)
    if collection_type(spec) or collection_array_type(spec):return spec,external_collection_result(spec,row,line)
    return _external_data_decode(row,line,selector=selector)


def _external_reply_outputs(outputs,arity=None):
    """Validate explicit one-based output ordinals without touching argument storage."""
    if type(outputs) is not list or len(outputs)>64:raise ValueError('External reply outputs require a list of at most 64 entries')
    seen=set();rows=[]
    for row in outputs:
        if type(row) is not dict or set(row)!={'argument','value'}:raise ValueError('External reply output requires exactly argument and value')
        number=row['argument']
        if type(number) is not int or not 1<=number<=64 or arity is not None and number>arity:
            raise ValueError('External reply output argument must be in 1..64 and present in the call')
        if number in seen:raise ValueError('Duplicate external reply output argument')
        seen.add(number);rows.append(row)
    return sorted(rows,key=lambda row:row['argument'])


def external_reply_result(spec,reply,arguments,line=None,*,check=None):
    """Stage a declared result and disjoint data/logical outputs before publication."""
    if not _pythonic():raise KarelRuntimeError('External reply outputs require Pythonic mode',line)
    from .storage import tuple_spec
    from .variable_archives import ordinary,cells,replace_collections
    try:
        def plan():
            if type(reply) is not dict or set(reply)!={'result','outputs'}:raise ValueError('External reply requires exactly result and outputs')
            if type(arguments) not in (list,tuple) or len(arguments)>64:raise ValueError('External reply requires at most 64 source arguments')
            rows=_external_reply_outputs(reply['outputs'],len(arguments))
            result_input=reply['result']
            # Bound supplied data before allocating any detached snapshot.
            units=1 if result_input is None else 0
            encoded=([result_input] if result_input is not None else [])+[row['value'] for row in rows]
            for value in encoded:
                if type(value) is not dict or set(value)!={'type','value'} or type(value['type']) is not list:
                    raise ValueError('External reply data requires exactly type and value')
                units+=_external_value_units(tuple_spec(value['type']),value['value'],line)
                if units>32767:raise ValueError('External reply exceeds 32767 snapshot units including result and outputs')
            targets=[]
            for row in rows:
                target=arguments[row['argument']-1]
                if not ordinary(target):raise ValueError('External reply output requires an ordinary writable data reference')
                value=row['value']
                actual=tuple_spec(value['type']);current=target.raw()
                units+=_external_value_units(target.spec,current,line)
                if target.spec!=actual:raise ValueError('External reply output differs from its captured argument schema')
                if type(current) is Structure and current.read_only:raise ValueError('External reply cannot write a read-only record value')
                targets.append((target,current,value))
            return result_input,targets,units

        result_input,targets,units=plan()
        if check is not None:
            for _ in range(units):check()
            result_input,targets,current_units=plan()
            if current_units!=units:raise ValueError('External reply size changed during preparation')
        if spec is None:
            if result_input is not None:raise ValueError('External procedure must return None')
            result=None
        else:
            if result_input is None:raise ValueError('External function requires its declared data result')
            result=(external_collection_result(spec,result_input,line) if collection_type(spec) or collection_array_type(spec)
                    else external_data_result(spec,result_input,line))
        staged=[];occupied=set()
        for target,current,value in targets:
            _external_value_snapshot(target.spec,current,line)
            # PATH headers are retained and updated; old nodes are detached instead.
            pending=[current]
            while pending:
                item=pending.pop()
                if type(item) is Array and collection_array_type(item.spec):pending.extend(item.values)
                elif type(item) is PathValue and type(item.data) is Structure and item.data.read_only:
                    raise ValueError('External reply cannot write a read-only PATH header')
            _,prepared=_external_value_decode(value,line,selector=True)
            addresses=cells(target)
            if occupied&addresses:raise ValueError('External reply output arguments overlap')
            occupied.update(addresses);staged.append((target,current,prepared))
        # Exact ordinary containers and disjoint cells have been checked completely.
        # No callback, clock read or checkpoint runs during these replacements.
        for target,current,prepared in staged:target.storage[target.key]=replace_collections(current,prepared)
        return result
    except (ValueError,KarelRuntimeError,TypeError,KeyError,IndexError,AttributeError,RecursionError,OverflowError) as error:
        raise KarelRuntimeError('External reply: '+str(error),line) from error


class _ExternalValueCase:
    def __init__(self,select):
        self.select=select

    def __call__(self,*arguments):
        return self.select(arguments)


def external_value_callbacks(config):
    """Prepare fixed replies or exact argument cases with an optional default."""
    import json
    from .storage import tuple_spec,typed_value
    if type(config) is not dict or not config or len(config)>128:
        raise ValueError('External values require a nonempty program/routine object within 128 bindings')
    prepared={};units=0;rows=0;unmatched=object()
    def capture(row,*,selector=False):
        nonlocal units
        if row is None and not selector:
            units+=1
            if units>32767:raise ValueError('External values exceed 32767 stored scalar leaves')
            return None
        if type(row) is not dict or set(row)!={'type','value'} or type(row['type']) is not list:
            raise ValueError('External value data requires exactly type and value')
        spec=tuple_spec(row['type']);units+=_external_value_units(spec,row['value'])
        if units>32767:raise ValueError('External values exceed 32767 stored scalar leaves')
        spec,copied=_external_value_decode(row,selector=selector)
        return typed_value(copied,spec)
    def response(result,outputs,arity=None):
        rows=_external_reply_outputs(outputs,arity)
        return dict(result=capture(result),outputs=[dict(argument=row['argument'],value=capture(row['value'],selector=True)) for row in rows])
    def fixed_response(row,arity=None):
        if type(row) is dict and set(row)=={'result','outputs'}:
            return response(row['result'],row['outputs'],arity)
        return capture(row)
    def key(arguments):
        def normalize(value):
            if type(value) is dict:return {name:normalize(item) for name,item in value.items()}
            if type(value) is list:return [normalize(item) for item in value]
            return 0.0 if type(value) is float and value==0.0 else value
        return json.dumps(normalize(arguments),sort_keys=True,separators=(',',':'),allow_nan=False)
    def cases_callback(table,arity,default):
        @_with_numeric_mode('pythonic')
        def select(arguments,*,check=None):
            from .variable_archives import ordinary
            if len(arguments)!=arity:raise KarelRuntimeError('External value case argument count differs')
            def plan():
                values=[];units=0
                for reference in arguments:
                    if not ordinary(reference):raise KarelRuntimeError('External value cases require ordinary typed data arguments')
                    spec,value=reference.spec,reference.raw()
                    units+=_external_value_units(spec,value)
                    if units>32767:raise KarelRuntimeError('External value arguments exceed 32767 scalar leaves')
                    values.append((spec,value))
                return values,units

            values,units=plan()
            if check is not None:
                for _ in range(units):check()
                values,current_units=plan()
                if current_units!=units:raise KarelRuntimeError('External value argument size changed during preparation')
            snapshots=[typed_value(_external_value_snapshot(spec,value),spec) for spec,value in values]
            selected=table.get(key(snapshots),default)
            if selected is unmatched:raise KarelRuntimeError('No external value case matches the captured arguments')
            return deepcopy(selected)
        return _ExternalValueCase(select)
    with _numeric_scope('pythonic'):
        try:
            for program,routines in config.items():
                if type(program) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,253}',program):
                    raise ValueError('External value program requires an ASCII identifier within 254 characters')
                if type(routines) is not dict or not routines:raise ValueError('External value routines require a nonempty object')
                for name,row in routines.items():
                    if type(name) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,253}',name):
                        raise ValueError('External value routine requires an ASCII identifier within 254 characters')
                    pair=program.upper(),name.upper()
                    if pair in prepared or len(prepared)>=128:raise ValueError('External value bindings must be distinct and limited to 128')
                    if type(row) is dict and set(row) in ({'cases'},{'cases','default'}):
                        cases=row['cases']
                        if type(cases) is not list or not cases:raise ValueError('External value cases require a nonempty list')
                        rows+=len(cases)+('default' in row)
                        if rows>128:raise ValueError('External values are limited to 128 fixed/case rows')
                        table={};arity=None
                        for case in cases:
                            if (type(case) is not dict or set(case) not in ({'arguments','result'},{'arguments','result','outputs'}) or type(case['arguments']) is not list
                                    or len(case['arguments'])>64):raise ValueError('External value case requires arguments (up to 64), result and optional outputs')
                            if arity is None:arity=len(case['arguments'])
                            if len(case['arguments'])!=arity:raise ValueError('External value cases require one argument count per binding')
                            selected=key([capture(argument,selector=True) for argument in case['arguments']])
                            if selected in table:raise ValueError('Duplicate normalized external value case arguments')
                            table[selected]=response(case['result'],case['outputs'],arity) if 'outputs' in case else capture(case['result'])
                        default=fixed_response(row['default'],arity) if 'default' in row else unmatched
                        prepared[pair]=cases_callback(table,arity,default)
                    else:
                        rows+=1
                        if rows>128:raise ValueError('External values are limited to 128 fixed/case rows')
                        saved=fixed_response(row)
                        prepared[pair]=lambda *arguments,_saved=saved:deepcopy(_saved)
        except (KarelRuntimeError,TypeError,KeyError,IndexError,AttributeError,RecursionError,OverflowError) as error:
            raise ValueError('Invalid external value data: '+str(error)) from error
    return prepared


def load_external_values(path,*,outputs=()):
    """Strict explicit JSON data bindings; no executable code or persisted callbacks."""
    import json
    from pathlib import Path
    from .fileio import same_file
    source=Path(path)
    if any(output is not None and same_file(source,output) for output in outputs):
        raise ValueError('External value input must differ from state/trace outputs, including aliases')
    limit=4*1024*1024
    if not source.is_file() or source.stat().st_size>limit:
        raise ValueError('External value input requires a regular file of at most 4 MiB')
    with source.open('rb') as stream:data=stream.read(limit+1)
    if len(data)>limit:raise ValueError('External value input exceeds 4 MiB')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate external value JSON key: '+key)
            result[key]=value
        return result
    def finite(value):raise ValueError('Nonfinite external value JSON number: '+value)
    try:config=json.loads(data.decode('utf-8-sig'),object_pairs_hook=unique,parse_constant=finite)
    except (UnicodeError,RecursionError) as error:raise ValueError('Invalid external value JSON: '+str(error)) from error
    return external_value_callbacks(config)


def load_external_bindings(*,values=None,collections=None,outputs=()):
    """Validate both explicit files before returning one disjoint callback bank."""
    prepared=load_external_collections(collections,outputs=outputs) if collections is not None else {}
    data=load_external_values(values,outputs=outputs) if values is not None else {}
    if set(prepared)&set(data):raise ValueError('External data and collection files contain duplicate program/routine bindings')
    prepared.update(data);return prepared


def external_collection_callbacks(config):
    """Prepare fixed logical function values; never load executable host code."""
    from .storage import tuple_spec,typed_value
    if type(config) is not dict or not config or len(config)>128:
        raise ValueError('External collections require a nonempty program/routine object within 128 bindings')
    prepared={}
    with _numeric_scope('pythonic'):
        for program,routines in config.items():
            if type(program) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,253}',program):
                raise ValueError('External collection program requires an ASCII identifier within 254 characters')
            if type(routines) is not dict or not routines:raise ValueError('External collection routines require a nonempty object')
            for name,row in routines.items():
                if type(name) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,253}',name):
                    raise ValueError('External collection routine requires an ASCII identifier within 254 characters')
                key=program.upper(),name.upper()
                if key in prepared or len(prepared)>=128:raise ValueError('External collection bindings must be distinct and limited to 128')
                if type(row) is not dict or set(row)!={'type','value'} or type(row['type']) is not list:
                    raise ValueError('External collection binding requires exactly type and value')
                try:
                    spec=tuple_spec(row['type']);captured=external_collection_result(spec,row)
                    saved=typed_value(captured,spec)
                except (ValueError,KarelRuntimeError,TypeError,IndexError,KeyError,RecursionError) as error:
                    raise ValueError('Invalid external collection '+'.'.join(key)+': '+str(error)) from error
                prepared[key]=lambda *arguments,_saved=saved:deepcopy(_saved)
    return prepared


def load_external_collections(path,*,outputs=()):
    """Load explicit fixed function results, protecting the input from output aliases."""
    import json
    from pathlib import Path
    from .fileio import same_file
    source=Path(path)
    if any(output is not None and same_file(source,output) for output in outputs):
        raise ValueError('External collection input must differ from state/trace outputs, including aliases')
    if not source.is_file() or source.stat().st_size>4*1024*1024:
        raise ValueError('External collection input requires a regular file of at most 4 MiB')
    data=source.read_bytes()
    if len(data)>4*1024*1024:raise ValueError('External collection input exceeds 4 MiB')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate external collection JSON key: '+key)
            result[key]=value
        return result
    def finite(value):raise ValueError('Nonfinite external collection JSON number: '+value)
    try:config=json.loads(data.decode('utf-8-sig'),object_pairs_hook=unique,parse_constant=finite)
    except (UnicodeError,RecursionError) as error:raise ValueError('Invalid external collection JSON: '+str(error)) from error
    return external_collection_callbacks(config)


def collection_array_argument(spec,value,line=None,*,source_spec=None):
    copied=collection_array_source_value(spec,value,line,source_spec=source_spec)
    return Reference(copied.spec,{'value':copied},'value')


def collection_array_assign(reference,value,line=None):
    """Preflight both owned selections, then preserve receiver collection cells."""
    from .variable_archives import replace_collections
    if not isinstance(reference,Reference):raise KarelRuntimeError('Collection ARRAY assignment requires writable storage',line)
    copied=collection_array_source_value(reference.spec,value,line)
    collection_array_source_value(reference.spec,reference.raw(),line,source_spec=reference.spec)
    if type(reference) is _ArrayPrefixTarget:reference.set(copied,line)
    elif type(reference) is Reference:reference.storage[reference.key]=replace_collections(reference.raw(),copied)
    else:raise KarelRuntimeError('Collection ARRAY source assignment requires an ordinary writable reference',line)


def collection_array_prefix_value(array,index,expected,line=None):
    reference=resource_array_prefix_reference(array,index,expected,line)
    return collection_array_source_value(reference.spec,reference.raw(),line)


def collection_array_node_type(spec,count):
    if collection_array_type(spec) and array_leaf_spec(spec)[0]=='PATH' and count==len(array_dimensions(spec))+1:
        return array_leaf_spec(spec)[1] or PREDEFINED_STRUCTURES['STD_PTH_NODE']
    return None


def _collection_path_slot(array,index,expected,line=None):
    """Resolve checked ARRAY coordinates and the following one-based node index."""
    indexes=index if type(index) is tuple else (index,)
    if (not _pythonic() or collection_array_node_type(expected,len(indexes)) is None
            or type(array) is not Array or not parameter_accepts(expected,array.spec)):
        raise KarelRuntimeError('Collection ARRAY node access requires matching declared PATH storage',line)
    current=array;schema=array.spec;remaining=indexes[:-1]
    while schema[0]=='ARRAY':
        shape=array_shape(schema)
        if (type(current) is not Array or current.spec!=schema or current.shape!=shape
                or not _array_storage(current.values,line) or len(current.values)!=math.prod(shape)):
            raise KarelRuntimeError('Malformed collection ARRAY container',line)
        width=len(shape);offset=current.offset(remaining[:width],line)
        current=current.values[offset];schema=schema[2];remaining=remaining[width:]
    if type(current) is not PathValue or current.spec!=schema or type(current.nodes) is not list:
        raise KarelRuntimeError('Collection ARRAY cell requires matching PATH storage',line)
    return current,integer(indexes[-1],line)


def collection_path_reference(array,index,expected,line=None):
    """Capture and validate the complete node for ordinary data access."""
    current,node=_collection_path_slot(array,index,expected,line)
    value=current.node(node,line)
    _aggregate_value(current.node_spec,value,line,allow_partial=True)
    return Reference(current.node_spec,current.nodes,node-1)


def resource_array_type(spec):
    return spec[0]=='ARRAY' and array_leaf_spec(spec)[0] in ('FILE','PATH','QUEUE_TYPE')


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
    """Explicit offline joint storage; Pythonic axis indexes use checked helpers."""
    def __init__(self, spec):
        self.spec = spec
        self.values = [UNINITIALIZED] * joint_width(spec)

    def clone(self):
        result = JointPosition(self.spec)
        result.values[:] = self.values
        return result


def joint_values(value, axes, line=None, *, pythonic_padding=False):
    """Read complete joints with zero-only padding for an explicit axis context."""
    if type(axes) is not int or not 1<=axes<=9:
        raise KarelRuntimeError('Joint context requires an axis count in 1..9',line)
    if not isinstance(value,JointPosition) or len(value.values)!=joint_width(value.spec):
        raise KarelRuntimeError('Malformed joint data',line)
    width=joint_width(value.spec)
    if width not in (axes,9) and not (pythonic_padding and _pythonic() and width>axes):
        raise KarelRuntimeError('Joint width does not fit the explicit axis context',line)
    with _numeric_scope('pythonic'): values=[real(axis,line) for axis in value.values]
    if any(axis!=0. for axis in values[axes:]):
        raise KarelRuntimeError('Unused JOINTPOS slots must be zero for the explicit axis context',line)
    return values[:axes]


def convert_joint_width(target, value, line=None):
    """Checked private joint padding/narrowing; no robot or axis inference."""
    if not _pythonic(): raise KarelRuntimeError('Joint width conversions require Pythonic mode',line)
    if not isinstance(value,JointPosition): raise KarelRuntimeError('Expected joint data',line)
    try:
        if type(target) is not tuple or target[0]!='JOINTPOS': raise ValueError('Expected JOINTPOS target')
        width=joint_width(target)
        source_width=joint_width(value.spec)
    except (ValueError,TypeError,IndexError,KarelRuntimeError) as exc:
        raise KarelRuntimeError('Malformed joint width conversion type',line) from exc
    axes=joint_values(value,source_width,line)
    if any(axis!=0. for axis in axes[width:]):
        raise KarelRuntimeError('Joint width narrowing requires zero discarded axes',line)
    result=JointPosition(target)
    result.values[:]=axes[:width]+[0.] * max(0,width-source_width)
    return result


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
    if value.spec[0] in ASSOCIATION_TYPES:return AssociationFieldReference(value.types[name],value.values,name,value.spec)
    reference_type = ConfigFieldReference if value.spec[0] == 'CONFIG' else Reference
    return reference_type(value.types[name], value.values, name)


def raw_field(value, name, line=None):
    return field_reference(value, name, line).raw()


def load_field(value, name, line=None):
    return require(raw_field(value, name, line), line)


def raw_index(array, index, line=None):
    if _pythonic() and isinstance(array,JointPosition):return index_reference(array,index,line).raw()
    if not isinstance(array, Array):
        raise KarelRuntimeError('Expected ARRAY', line)
    return array.raw(index, line)


def load_index(array, index, line=None):
    value=raw_index(array,index,line)
    count=len(index) if type(index) is tuple else 1
    if _pythonic() and isinstance(array,(Array,JointPosition)) and joint_axis_access(array.spec,count):return real(value,line)
    return require(value,line)


def store_index(array, index, value, line=None):
    if _pythonic() and isinstance(array,JointPosition):return index_reference(array,index,line).set(value,line)
    if not isinstance(array, Array):
        raise KarelRuntimeError('Expected ARRAY', line)
    array.set(index, value, line)


class Reference:
    """A captured storage location; not a copy-in/copy-out parameter."""
    def __init__(self, spec, storage, key):
        if type(storage) is _ArrayWindow:storage,key=storage.location(key)
        self.spec, self.storage, self.key = spec, storage, key

    def raw(self):
        return self.storage[self.key]

    def set(self, value, line=None):
        updated = checked(self.spec, value, line)
        self.storage[self.key] = replace_value(self.raw(), updated)

    def clear(self):
        self.storage[self.key] = UNINITIALIZED


class _ArrayWindow:
    """Fixed-size live data cells captured from an exact ARRAY storage list."""
    __slots__=('storage','start','size','length')

    def __init__(self,target):
        self.storage=target.storage;self.start=target.indices[0];self.size=len(target.indices);self.length=target.length
        if target.indices!=tuple(range(self.start,self.start+self.size)):
            raise KarelRuntimeError('Live ARRAY prefix requires contiguous captured cells')
        self.validate()

    @property
    def indices(self):
        self.validate();return range(self.start,self.start+self.size)

    def validate(self,line=None):
        if (not _pythonic() or type(self.storage) is not list
                or any(type(value) is not int for value in (self.start,self.size,self.length))
                or not 1<=self.length<=32767 or len(self.storage)!=self.length
                or self.start<0 or self.size<1 or self.start+self.size>self.length):
            raise KarelRuntimeError('Malformed live ARRAY prefix storage',line)
        return True

    def __len__(self):
        self.validate();return len(self.indices)

    def location(self,index):
        self.validate()
        return self.storage,self.indices[index]

    def __getitem__(self,index):
        self.validate()
        if type(index) is slice:return [self.storage[key] for key in self.indices[index]]
        storage,key=self.location(index);return storage[key]

    def __setitem__(self,index,value):
        self.validate()
        if type(index) is slice:
            keys=self.indices[index];values=list(value)
            if len(keys)!=len(values):raise KarelRuntimeError('Live ARRAY prefix cannot change its shape')
            for key,item in zip(keys,values):self.storage[key]=item
        else:
            storage,key=self.location(index);storage[key]=value

    def __iter__(self):
        self.validate()
        for index in range(len(self.indices)):yield self[index]


def _array_storage(values,line=None):
    """Accept exact lists and only our checked Pythonic live data windows."""
    return type(values) is list or type(values) is _ArrayWindow and values.validate(line)


def _service_array_layout(array, expected, line):
    if type(array) is not Array or not parameter_accepts(expected, array.spec):
        raise KarelRuntimeError('Service ARRAY input does not match its declared type', line)
    shape = array_shape(array.spec)
    storage = array.values
    if (array.shape != shape or not _array_storage(storage, line)
            or len(storage) != math.prod(shape)):
        raise KarelRuntimeError('Malformed service ARRAY input storage', line)
    return shape, storage


def service_array_view(array, index, expected, line=None):
    """Locate a selected service row without copying the containing ARRAY."""
    indexes = index if type(index) is tuple else (index,)
    if array_prefix_type(expected, len(indexes)) is None:
        raise KarelRuntimeError('Service ARRAY prefix requires an incomplete selection', line)
    current = array
    while indexes:
        shape, storage = _service_array_layout(current, expected, line)
        width = len(shape)
        if len(indexes) < width:
            suffix = shape[len(indexes):]
            start = current.offset(indexes + (1,) * len(suffix), line)
            if type(storage) is _ArrayWindow:
                start += storage.start
                storage = storage.storage
            window = object.__new__(_ArrayWindow)
            window.storage, window.start, window.size, window.length = storage, start, math.prod(suffix), len(storage)
            window.validate(line)
            view = object.__new__(Array)
            view.spec = ('ARRAY', suffix[0] if len(suffix) == 1 else suffix, current.spec[2])
            view.shape, view.values = suffix, window
            return view
        expected = current.spec[2]
        current = storage[current.offset(indexes[:width], line)]
        indexes = indexes[width:]
    _service_array_layout(current, expected, line)
    return current


def bounded_service_array(spec, array, limit, line=None, *, check=None):
    """Capture only admissible scalar cells before later argument selectors."""
    from .extended import VariableValue

    if array is UNINITIALIZED:
        return VariableValue(spec, ())
    shape, storage = _service_array_layout(array, spec, line)
    actual = array.spec
    if len(shape) != 1 or actual[2][0] not in ('BYTE', 'STRING'):
        raise KarelRuntimeError('Service ARRAY requires one dimension of BYTE or STRING', line)
    size = shape[0]
    if not 1 <= size <= limit:
        return VariableValue(actual, ())
    if check is not None:
        check()
    current_shape, current_storage = _service_array_layout(array, actual, line)
    if current_shape != shape or current_storage is not storage:
        raise KarelRuntimeError('Service ARRAY storage changed during capture', line)
    values = tuple(storage)
    if actual[2][0] == 'STRING':
        for item in values:
            if item is not UNINITIALIZED and len(ascii_string(item, line)) > actual[2][1]:
                raise KarelRuntimeError('Service ARRAY STRING exceeds its declared capacity', line)
    return VariableValue(actual, values)


def same_array_storage(first,second):
    """Backing identity for repeated captures of the same live ARRAY cells."""
    if first is second:return True
    if (type(first) is not Array or type(second) is not Array
            or first.spec!=second.spec or first.shape!=second.shape):return False
    def capture(values):
        if type(values) is _ArrayWindow:
            values.validate();return values.storage,values.indices
        if type(values) is list:return values,range(len(values))
        raise KarelRuntimeError('Malformed ARRAY backing storage')
    left,li=capture(first.values);right,ri=capture(second.values)
    return left is right and li==ri


def resource_array_prefix_reference(array,index,expected,line=None,*,check=None):
    """Borrow original resource cells; no descriptor/collection allocation or copy."""
    if not _pythonic():raise KarelRuntimeError('Resource ARRAY prefixes require Pythonic mode',line)
    indexes=index if type(index) is tuple else (index,)
    if (type(array) is not Array or array_prefix_type(expected,len(indexes)) is None
            or not resource_array_type(expected)):
        raise KarelRuntimeError('Resource ARRAY prefix requires matching incomplete ARRAY storage',line)
    from .dynamic import creation_cost
    from .storage import _collection_array_units,collection_payload
    try:
        creation_cost(array.spec)
        if not resource_array_type(array.spec) or not parameter_accepts(expected,array.spec):
            raise ValueError('Resource ARRAY prefix storage does not match its declared schema')
    except (ValueError,KarelRuntimeError) as exc:raise KarelRuntimeError('Resource ARRAY prefix schema: '+str(exc),line) from exc
    if check is not None and collection_array_type(array.spec):
        _collection_bank_io_preflight(array,line,check)
    units=0;seen=set();pending=[(array.spec,array)]
    while pending:
        schema,current=pending.pop()
        if schema[0]=='ARRAY':
            shape=array_shape(schema);identity=array_identity(schema)
            if identity is not None and re.fullmatch(r'[A-Z_][A-Z_0-9]*',identity) is None:
                raise KarelRuntimeError('Resource ARRAY prefix requires canonical named components',line)
            if (type(current) is not Array or current.spec!=schema or current.shape!=shape
                    or not _array_storage(current.values,line) or len(current.values)!=math.prod(shape)):
                raise KarelRuntimeError('Resource ARRAY prefix found malformed container storage',line)
            pending.extend((schema[2],item) for item in current.values)
            continue
        if id(current) in seen:raise KarelRuntimeError('Resource ARRAY cells must own distinct resources',line)
        seen.add(id(current))
        if schema==('FILE',):
            if type(current) is not FileHandle:raise KarelRuntimeError('Resource ARRAY prefix requires exact FILE descriptors',line)
            units+=1
        else:
            try:
                units+=_collection_array_units(schema,current,False)
                if units>32767:raise ValueError('Resource ARRAY prefix exceeds 32767 content units')
                collection_payload(schema,current)
            except (ValueError,KarelRuntimeError) as exc:raise KarelRuntimeError('Resource ARRAY prefix contents: '+str(exc),line) from exc
        if units>32767:raise KarelRuntimeError('Resource ARRAY prefix exceeds 32767 content units',line)
    current=array
    while True:
        width=len(current.shape)
        if len(indexes)<width:
            suffix=current.shape[len(indexes):];offset=0
            for number,(subscript,dimension) in enumerate(zip(indexes,current.shape),1):
                integer(subscript,line)
                if not 1<=subscript<=dimension:raise KarelRuntimeError(f'Array index {subscript} outside 1..{dimension} in dimension {number}',line)
                offset=offset*dimension+subscript-1
            size=math.prod(suffix);start=offset*size;storage=current.values
            spec=('ARRAY',suffix[0] if len(suffix)==1 else suffix,current.spec[2])
            if type(storage) is _ArrayWindow:
                storage.validate(line);start+=storage.start;storage=storage.storage
            window=object.__new__(_ArrayWindow)
            window.storage=storage;window.start=start;window.size=size;window.length=len(storage);window.validate(line)
            view=object.__new__(Array);view.spec=spec;view.shape=suffix;view.values=window
            return Reference(spec,{'value':view},'value')
        offset=current.offset(indexes[:width],line)
        current=current.values[offset];indexes=indexes[width:]


def array_prefix_reference(target,line=None):
    """Borrow captured row/plane cells without changing ordinary prefix values."""
    if not _pythonic() or type(target) is not _ArrayPrefixTarget:
        raise KarelRuntimeError('Live ARRAY prefixes require a Pythonic data capture',line)
    current=target._current(line)
    _aggregate_value(target.spec,current,line)
    current.values=_ArrayWindow(target)
    return Reference(target.spec,{'value':current},'value')


class _ArrayPrefixTarget:
    """A statement capture; never a generic Reference or a live ARRAY view."""
    __slots__=('spec','storage','indices','length')
    def __init__(self,spec,storage,indices,line=None):
        indices=tuple(indices)
        if type(storage) is _ArrayWindow:
            storage.validate(line);indices=tuple(storage.indices[index] for index in indices);storage=storage.storage
        self.spec=spec;self.storage=storage;self.indices=indices;self.length=len(storage)
        self._current(line)

    def _current(self,line=None):
        if (not _pythonic() or type(self.storage) is not list or len(self.storage)!=self.length
                or type(self.indices) is not tuple or not self.indices
                or any(type(index) is not int or not 0<=index<self.length for index in self.indices)
                or len(set(self.indices))!=len(self.indices)):
            raise KarelRuntimeError('Malformed captured ARRAY prefix storage',line)
        result=Array(self.spec)
        if len(result.values)!=len(self.indices):raise KarelRuntimeError('Captured ARRAY prefix shape changed',line)
        result.values[:]=[self.storage[index] for index in self.indices]
        return result

    def raw(self):
        return _aggregate_value(self.spec,self._current())

    def references(self,line=None):
        _aggregate_value(self.spec,self._current(line),line)
        return [Reference(self.spec[2],self.storage,index) for index in self.indices]

    def set(self,value,line=None):
        # No callbacks/checkpoints occur between this preflight and publication.
        updated=_aggregate_value(self.spec,value,line)
        self.references(line)
        for index,item in zip(self.indices,updated.values):
            self.storage[index]=replace_value(self.storage[index],item)


def using_path_node_reference(spec,reference,line=None):
    """Retain the selected node object when its PATH list changes later."""
    from .variable_archives import ordinary
    if not _pythonic() or not ordinary(reference) or reference.spec!=spec or spec[0]!='STRUCTURE':
        raise KarelRuntimeError('USING PATH node requires an ordinary exact record reference',line)
    value=reference.raw()
    if type(value) is not Structure or value.spec!=spec:
        raise KarelRuntimeError('USING PATH node requires existing shaped node data',line)
    _aggregate_value(spec,value,line,allow_partial=True)
    return Reference(spec,{'value':value},'value')


def path_counter_root(spec):
    """Explicit PATH storage only; FILE and queue descriptors remain resources."""
    return collection_type(spec) and spec[0]=='PATH' or path_array_io_type(spec)


def path_for_reference(root,spec,target,line=None):
    """Preflight bounded owned logical storage before initial-bound effects."""
    from .variable_archives import ordinary
    if (not _pythonic() or not path_counter_root(spec) or not ordinary(root) or root.spec!=spec
            or not ordinary(target) or target.spec not in (('INTEGER',),('BYTE',),('SHORT',))):
        raise KarelRuntimeError('PATH FOR requires owned storage and an ordinary integral leaf',line)
    if spec[0]=='PATH':collection_source_value(spec,root.raw(),line,source_spec=spec)
    else:collection_array_source_value(spec,root.raw(),line,source_spec=spec)
    found=False
    def visit(schema,value,storage=None,key=None):
        nonlocal found
        if schema in (('INTEGER',),('BYTE',),('SHORT',)):
            found=found or storage is target.storage and key==target.key and schema==target.spec
        elif value is UNINITIALIZED or value is UNKNOWN_BYTE:return
        elif schema[0]=='PATH':
            if schema[2] is not None:visit(schema[2],value.data,vars(value),'data')
            for index,node in enumerate(value.nodes):visit(value.node_spec,node,value.nodes,index)
        elif schema[0]=='ARRAY':
            for index,child in enumerate(value.values):visit(schema[2],child,value.values,index)
        elif schema[0] in RECORD_TYPES and schema[0] not in ('CONFIG',*ASSOCIATION_TYPES):
            for name,field in record_fields(schema):visit(field,value.values[name],value.values,name)
    visit(spec,root.raw())
    if not found:raise KarelRuntimeError('PATH FOR requires a matching integral cell in its current owned root',line)
    return target


def for_bound(spec,value,line=None):
    """Require an initialized integral loop bound in its counter's domain."""
    if type(spec) is not tuple or len(spec)!=1 or type(spec[0]) is not str or spec[0] not in ('INTEGER','BYTE','SHORT'):
        raise KarelRuntimeError('FOR counter requires INTEGER, BYTE or SHORT storage',line)
    value=integer(value,line)
    if spec==('BYTE',) and not 0<=value<=255:
        raise KarelRuntimeError('BYTE FOR bounds require initialized values in 0..255',line)
    if spec==('SHORT',) and not -32768<=value<=32766:
        raise KarelRuntimeError('SHORT FOR bounds require initialized values in -32768..32766',line)
    return value


class NarrowForCounter:
    """One captured narrow leaf, with checked writes and type-specific cleanup."""
    def __init__(self,reference,line=None):
        if (not _pythonic() or type(reference) is not Reference or type(reference.spec) is not tuple
                or len(reference.spec)!=1 or type(reference.spec[0]) is not str or reference.spec not in (('BYTE',),('SHORT',))):
            raise KarelRuntimeError('Narrow FOR requires ordinary Pythonic BYTE/SHORT storage',line)
        self.reference=reference
        self.spec=reference.spec

    def raw(self):return self.reference.raw()

    def set(self,value,line=None):
        # In particular, SHORT 32767 must fail before Reference.set turns it
        # into an uninitialized marker or a loop registers its cleanup frame.
        self.reference.set(for_bound(self.spec,value,line),line)

    def clear(self):
        self.reference.storage[self.reference.key]=UNKNOWN_BYTE if self.spec==('BYTE',) else UNINITIALIZED


class ReadOnlyFieldReference(Reference):
    """Protect POSITION orientation fields and their descendants at runtime."""
    def __init__(self, spec, storage, key, line=None):
        super().__init__(spec, storage, key)
        self.line = line

    def set(self, value, line=None):
        raise KarelRuntimeError('POSITION orientation fields are read-only', self.line if line is None else line)

    def clear(self):
        raise KarelRuntimeError('POSITION orientation fields are read-only', self.line)


class AssociationFieldReference(Reference):
    """Writable data field; user-routine passing is value-only, never an alias."""
    def __init__(self,spec,storage,key,record_spec):
        super().__init__(spec,storage,key);self.record_spec=record_spec

    def validate_storage(self,line=None):
        if self.record_spec not in tuple((name,) for name in ASSOCIATION_TYPES):
            raise KarelRuntimeError('Association field requires a declared record type',line)
        fields=dict(record_fields(self.record_spec))
        if (type(self.storage) is not dict or set(self.storage)!=set(fields)
                or type(self.key) is not str or self.key not in fields or self.spec!=fields[self.key]):
            raise KarelRuntimeError('Malformed association scalar field storage',line)

    def set(self,value,line=None):
        self.validate_storage(line);super().set(value,line)


class ConfigFieldReference(Reference):
    """Compact CONFIG fields have a bounded turn-number storage policy."""
    def validate_storage(self,line=None):
        fields=dict(record_fields(('CONFIG',)))
        if (type(self.storage) is not dict or set(self.storage)!=set(fields)
                or type(self.key) is not str or self.key not in fields or self.spec!=fields[self.key]):
            raise KarelRuntimeError('Expected declared CONFIG scalar field storage',line)

    def validate(self, value, line=None):
        if self.spec == INTEGER and not -8 <= integer(value, line) <= 7:
            raise KarelRuntimeError('CONFIG turn numbers are limited to -8..7 by the prototype', line)
        checked(self.spec,value,line)

    def set(self, value, line=None):
        self.validate(value,line)
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


def _reference_cells(reference,*,queue_buffers=False):
    """Storage identity, including aggregate descendants; values are not aliases."""
    cells, seen = {(id(reference.storage), reference.key)}, set()

    def visit(value):
        if queue_buffers and isinstance(value,QueueValue):
            if id(value) in seen:return
            seen.add(id(value));visit(value.buffer);return
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
            storage,member=(value.values.location(key) if type(value.values) is _ArrayWindow else (value.values,key))
            cells.add((id(storage), member))
            visit(child)
    visit(reference.raw())
    return cells


def unpos_source(value, expected, line=None, *, with_axes=False):
    """Snapshot and normalize a Pythonic pose before output selectors run."""
    value=frame_value(value,line,expected=expected)
    if with_axes:
        from .extended import pose_extended
        return pose_extended(value,line)
    if value.spec==('POSITION',): return convert_position(('XYZWPR',),value,line)
    result=Structure(('XYZWPR',))
    result.values.update({name:value.values[name] for name in ('X','Y','Z','W','P','R')})
    result.values['CONFIG_DATA']=positional_value(('CONFIG',),value.values['CONFIG_DATA'],line)
    return result


def unpos_value(source, outputs, line=None):
    """Extract an independent prepared pose with the existing output guards."""
    if not _pythonic(): raise KarelRuntimeError('UNPOS values require Pythonic mode',line)
    spec=('XYZWPREXT',) if isinstance(outputs,(list,tuple)) and len(outputs)==10 else ('XYZWPR',)
    source=positional_value(spec,source,line)
    unpos(Reference(spec,{'source':source},'source'),outputs,line)


def unpos(source, outputs, line=None):
    """Extract checked Cartesian data without relying on alias write order."""
    if not isinstance(outputs,(list,tuple)) or len(outputs) not in ((7,10) if _pythonic() else (7,)):
        raise KarelRuntimeError('UNPOS has an invalid output reference count',line)
    with_axes=len(outputs)==10
    source_type=('XYZWPREXT',) if with_axes else ('XYZWPR',)
    references = [source, *outputs]
    expected=[source_type]+[('REAL',)]*6+[('CONFIG',)]
    if with_axes:
        expected.extend([('REAL',)]*3)
    for reference, spec in zip(references, expected):
        if type(reference) is not Reference or reference.spec != spec:
            raise KarelRuntimeError(f'UNPOS requires ordinary exact-type writable output references and {source_type[0]} source',line)
    pose = require(source.raw(), line)
    if (not isinstance(pose,Structure) or pose.spec!=source_type
            or set(pose.values)!=set(dict(record_fields(source_type)))):
        raise KarelRuntimeError(f'UNPOS requires a complete {source_type[0]} record',line)
    config = pose.values['CONFIG_DATA']
    if (not isinstance(config, Structure) or config.spec != ('CONFIG',)
            or set(config.values) != set(dict(record_fields(('CONFIG',))))):
        raise KarelRuntimeError('UNPOS requires a complete CONFIG record', line)
    values = [real(pose.values[name], line) for name in ('X', 'Y', 'Z', 'W', 'P', 'R')]
    values.append(checked(('CONFIG',), config, line))
    if with_axes:
        values.extend(real(pose.values[name],line) for name in ('EXT1','EXT2','EXT3'))
    current_config = outputs[6].raw()
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


def joint_index_reference(value,index,expected,line=None):
    """Capture one source-declared joint axis without materializing partial rows."""
    if not _pythonic():raise KarelRuntimeError('Joint axis access requires Pythonic mode',line)
    indexes=index if type(index) is tuple else (index,)
    try:
        if not joint_axis_access(expected,len(indexes)):
            raise KarelRuntimeError('Joint axis access requires one axis after complete ARRAY indexes',line)
        if (type(value) not in (Array,JointPosition) or not joint_axis_access(value.spec,len(indexes))
                or not parameter_accepts(expected,value.spec)):
            raise KarelRuntimeError('Joint axis source storage does not match its declared schema',line)
        current=value;declared=value.spec
        while declared[0]=='ARRAY':
            shape=array_shape(declared)
            if (type(current) is not Array or current.spec!=declared or current.shape!=shape
                    or not _array_storage(current.values,line) or len(current.values)!=math.prod(shape)):
                raise KarelRuntimeError('Malformed ARRAY storage before joint axis',line)
            width=len(shape);offset=current.offset(indexes[:width],line)
            current=current.values[offset];indexes=indexes[width:];declared=declared[2]
        width=joint_width(declared)
        if (type(current) is not JointPosition or current.spec!=declared
                or type(current.values) is not list or len(current.values)!=width):
            raise KarelRuntimeError('Malformed joint axis storage',line)
        axis=integer(indexes[0],line)
        if not 1<=axis<=width:raise KarelRuntimeError(f'Joint axis {axis} outside 1..{width}',line)
        return Reference(REAL,current.values,axis-1)
    except KarelRuntimeError as exc:
        if exc.line is None:raise KarelRuntimeError(str(exc),line) from exc
        raise
    except (TypeError,IndexError,KeyError,AttributeError) as exc:
        raise KarelRuntimeError('Malformed joint axis storage: '+str(exc),line) from exc


def index_reference(array, index, line=None):
    if _pythonic() and isinstance(array,(Array,JointPosition)):
        count=len(index) if type(index) is tuple else 1
        if joint_axis_access(array.spec,count):return joint_index_reference(array,index,array.spec,line)
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
        try:compatible=isinstance(value,Array) and parameter_accepts(spec,value.spec)
        except (KarelRuntimeError,TypeError,IndexError,RecursionError):compatible=False
        if not compatible:
            raise KarelRuntimeError('ARRAY value argument requires a matching concrete type and shape', line)
        copied = _aggregate_value(value.spec, value, line)
        return Reference(copied.spec, {'value': copied}, 'value')
    if spec == ('VECTOR',):
        return Reference(spec, {'value': checked(spec, value, line) if _pythonic() else vector_value(value, line)}, 'value')
    if spec[0] == 'STRUCTURE':
        return Reference(spec, {'value': structure_value(spec, value, line)}, 'value')
    if spec[0] in POSITIONAL_VALUE_TYPES:
        if (_pythonic() and spec[0] in ('POSITION','XYZWPR','XYZWPREXT') and isinstance(value,Structure)
                and value.spec[0] in ('POSITION','XYZWPR','XYZWPREXT') and value.spec!=spec):
            value=convert_position(spec,value,line)
        return Reference(spec, {'value': checked(spec, value, line) if _pythonic() else positional_value(spec, value, line)}, 'value')
    supported = ('INTEGER', 'BOOLEAN', 'REAL') + (('BYTE','SHORT') if _pythonic() else ())
    if spec[0] not in supported:
        raise KarelRuntimeError('Unsupported value-parameter type', line)
    return Reference(spec, {'value': checked(spec, value, line)}, 'value')


def select_scalar(value,category,line=None):
    """Validate one SELECT primitive without bool/numeric coercion or rounding."""
    if type(category) is not str or category not in ('BOOLEAN','STRING','NUMERIC'):
        raise KarelRuntimeError('Invalid generated SELECT comparison category',line)
    if category=='BOOLEAN':return boolean(value,line)
    if category=='STRING':
        value=ascii_string(value,line)
        if len(value)>254:raise KarelRuntimeError('SELECT STRING is limited to 254 ASCII characters',line)
        return value
    # Keep INTEGER operands as integers: converting them to float before equality
    # could collapse otherwise distinct numeric values. bool is never a number.
    if type(value) is int:return integer(value,line)
    if type(value) is float:return real(value,line)
    require(value,line)
    raise KarelRuntimeError('SELECT numeric values require finite REAL or INTEGER',line)


def select_case(value,cases,has_else,line=None,*,category=None):
    """Return the first matching clause index; missing ELSE is an execution error."""
    pythonic=_pythonic()
    if pythonic:
        if category is None:
            category='BOOLEAN' if type(value) is bool else 'STRING' if type(value) is str else 'NUMERIC'
        value=select_scalar(value,category,line)
    else:
        if category is not None:raise KarelRuntimeError('Scalar SELECT categories require Pythonic mode',line)
        value=integer(value,line)
    if type(has_else) is not bool or type(cases) not in (list,tuple) or not 1<=len(cases)<=1000:
        raise KarelRuntimeError('Invalid generated SELECT case table or ELSE flag',line)
    # Validate every clause before comparison, including clauses after an earlier
    # match. Tables never execute arbitrary equality on supplied objects.
    for values in cases:
        if type(values) not in (list,tuple) or not values:
            raise KarelRuntimeError('Invalid generated SELECT value list',line)
        for candidate in values:
            if pythonic:select_scalar(candidate,category,line)
            else:integer(candidate,line)
    for index,values in enumerate(cases):
        if value in values:return index
    if has_else:return len(cases)
    raise KarelRuntimeError('No match in CASE',line)


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


def _parse_config_text(source, line=None, *, profile=None):
    text = ascii_string(source, line)
    if len(text) > 254: raise KarelRuntimeError('CONFIG text input is limited to 254 characters', line)
    parts = text.upper().split(',')
    expected=None
    if profile is None:
        if len(parts) not in (1,4):return None
        positions=(1,2,3) if len(parts)==4 else ()
        flag_text=parts.pop(0)
    else:
        selected,positions=profile
        expected={f'CFG_{flag.upper()}' for flag in selected}
        flag_text=parts.pop(0) if selected else ''
        if not selected and not positions and not text.strip():
            parts=[]
        if len(parts)!=len(positions):return None
    flags=re.sub(r'\s+','',flag_text)
    if expected is None and not flags:return None
    values = {field: False for field, _, _ in CONFIG_TEXT_FLAGS}
    choices = {letter: (field, enabled) for field, off, on in CONFIG_TEXT_FLAGS
               for letter, enabled in ((off, False), (on, True))}
    seen = set()
    for letter in flags:
        if letter not in choices: return None
        field, value = choices[letter]
        if field in seen: return None
        seen.add(field); values[field] = value
    if expected is not None and seen!=expected:return None
    try: turns = [int(part, 10) for part in parts]
    except ValueError: return None
    if any(not -8 <= value <= 7 for value in turns): return None
    values.update(CFG_TURN_NO1=0,CFG_TURN_NO2=0,CFG_TURN_NO3=0)
    values.update((f'CFG_TURN_NO{position}',turn) for position,turn in zip(positions,turns))
    result = Structure(('CONFIG',)); result.values.update(values)
    return positional_value(('CONFIG',), result, line)


def config_word_kind(target,source):
    """Source-only portable CONFIG words, separate from reference/ABI contracts."""
    integral=(('INTEGER',),('BYTE',),('SHORT',))
    if target==('CONFIG',) and source in integral:return 'decode'
    if source==('CONFIG',) and target in integral:return 'encode'
    return None


def config_word_value(target,value,line=None):
    """An explicit Pythonic 16-bit value codec; never native CONFIG memory."""
    if not _pythonic():raise KarelRuntimeError('CONFIG word conversion requires Pythonic mode',line)
    fields=record_fields(('CONFIG',));turns=fields[:3];flags=fields[3:]
    if target==('CONFIG',):
        word=integer(value,line)
        if not 0<=word<=65535:raise KarelRuntimeError('CONFIG word requires INTEGER in 0..65535',line)
        result=Structure(('CONFIG',))
        for index,(name,_) in enumerate(turns):
            nibble=(word>>(4*index))&15;result.values[name]=nibble-16 if nibble>=8 else nibble
        for index,(name,_) in enumerate(flags):result.values[name]=bool(word&(1<<(12+index)))
        return result
    if target not in (('INTEGER',),('BYTE',),('SHORT',)):
        raise KarelRuntimeError('CONFIG word output requires INTEGER, BYTE or SHORT',line)
    captured=positional_value(('CONFIG',),value,line)
    if not fully_initialized(captured):raise KarelRuntimeError('CONFIG word encoding requires complete initialized CONFIG data',line)
    word=sum((captured.values[name]&15)<<(4*index) for index,(name,_) in enumerate(turns))
    word|=sum(int(captured.values[name])<<(12+index) for index,(name,_) in enumerate(flags))
    checked(target,word,line)
    # Keep the expression value until receiving SHORT storage applies its sentinel.
    return word


def _config_word_data(target,source,value,line=None):
    """Partial data copies preserve missing leaves without inventing CONFIG bits."""
    if not _pythonic() or config_word_kind(target,source) is None:
        raise KarelRuntimeError('CONFIG word data requires compatible Pythonic types',line)
    if value is UNINITIALIZED:return Structure(target) if target==('CONFIG',) else UNINITIALIZED
    if source==('CONFIG',):
        value=_partial_aggregate_value(source,value,line)
        if not fully_initialized(value):return UNINITIALIZED
    else:
        value=checked(source,value,line)
        if value is UNINITIALIZED:return Structure(target)
    converted=config_word_value(target,value,line)
    return converted if target==('CONFIG',) else checked(target,converted,line)


def config_text_conversion(name, source, target, status=None, *, line=None, group=None, formats=None):
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
    if group is None:
        value=_parse_config_text(source,line)
        code=CONFIG_TEXT_INVALID if value is None else 0
    else:
        if formats is None:raise KarelRuntimeError('Grouped CONFIG parsing requires ConfigTextFormats',line)
        code,value=formats.parse(source,group,line)
    if code==0:target.set(value,line)
    status.set(code,line)


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


def _record_uninitialized(value,spec,line=None,*,check=None):
    if not isinstance(value,Structure) or value.spec!=spec or spec!=(spec[0],) or spec[0] not in DATA_RECORD_TYPES:
        raise KarelRuntimeError('Initialization query requires matching builtin record storage',line)
    fields=dict(record_fields(spec))
    if set(value.values)!=set(fields): raise KarelRuntimeError('Initialization query found malformed record fields',line)
    missing=False
    for name,field_spec in fields.items():
        if check is not None:check()
        member=value.values[name]
        if member is UNINITIALIZED: missing=True
        elif member is UNKNOWN_BYTE: raise KarelRuntimeError('BYTE initialization queries are not implemented',line)
        elif field_spec[0] in DATA_RECORD_TYPES: missing|=_record_uninitialized(member,field_spec,line,check=check)
        else:
            checked(field_spec,member,line)
            if spec[0]=='CONFIG' and field_spec==INTEGER and not -8<=member<=7:
                raise KarelRuntimeError('CONFIG turn numbers are limited to -8..7 by the prototype',line)
    return missing


def file_uninit(value,line=None):
    if not _pythonic() or type(value) is not FileHandle:
        raise KarelRuntimeError('FILE initialization queries require ordinary Pythonic descriptors',line)
    return value.owner is None


def queue_uninit(value,line=None):
    if (not _pythonic() or type(value) is not QueueValue or getattr(value,'spec',None)!=('QUEUE_TYPE',)
            or type(getattr(value,'initialized',None)) is not bool):
        raise KarelRuntimeError('QUEUE_TYPE initialization queries require ordinary Pythonic queue storage',line)
    return not value.initialized


def uninit(value,line=None):
    if isinstance(value,FileHandle):return file_uninit(value,line)
    if isinstance(value,QueueValue):return queue_uninit(value,line)
    if isinstance(value, JointPosition): return not fully_initialized(value)
    if isinstance(value,Structure) and value.spec[0] in DATA_RECORD_TYPES:
        if not _pythonic(): raise KarelRuntimeError('Whole record initialization queries require Pythonic mode',line)
        return _record_uninitialized(value,(value.spec[0],),line)
    # Whole arrays deliberately rejected by the compiler; no guessed aggregate rule.
    if value is UNKNOWN_BYTE:
        raise KarelRuntimeError('BYTE initialization queries are not implemented',line)
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
        if _pythonic() and type(value) is bool:return boolean(value,line)
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
    """Copy a named record tree without exporting its source storage."""
    if spec[0] != 'STRUCTURE':
        raise KarelRuntimeError('Named STRUCTURE value requires a declared STRUCTURE type', line)
    return _aggregate_value(spec, value, line)


def positional_value(spec, value, line=None):
    """Copy initialized exact-type positional data without conversion or context."""
    if spec[0] not in POSITIONAL_VALUE_TYPES:
        raise KarelRuntimeError('Expected a supported exact positional value type', line)
    return _aggregate_value(spec, value, line, allow_partial=False)


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
    inherited_string=pythonic and identity is None and spec[2]==('STRING',None)
    if inherited_string:
        if (type(value) is Array and type(value.spec) is tuple and len(value.spec) in (3,4)
                and array_identity(value.spec) is not None):
            raise KarelRuntimeError('ARRAY result requires matching anonymous outer storage and exact element type',line)
        if (type(value) is not Array or type(value.spec) is not tuple or len(value.spec)!=3
                or type(value.spec[2]) is not tuple or len(value.spec[2])!=2 or value.spec[2][0]!='STRING'
                or type(value.spec[2][1]) is not int or not 1<=value.spec[2][1]<=254):
            raise KarelRuntimeError('Inherited STRING ARRAY result requires concrete capacity in 1..254',line)
        spec=('ARRAY',spec[1],value.spec[2])
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


def _validate_data_schema(spec,line=None):
    """Validate a bounded data-only schema before allocation or value capture."""
    schema_cache={}
    def schema(expected,trail=()):
        if type(expected) is not tuple or not expected or type(expected[0]) is not str:
            raise KarelRuntimeError('Aggregate value requires a concrete data type',line)
        if id(expected) in trail or len(trail)>=64:
            raise KarelRuntimeError('Aggregate value schema exceeds 64 levels or is cyclic',line)
        if id(expected) in schema_cache:
            count,height=schema_cache[id(expected)]
            if len(trail)+height>64:raise KarelRuntimeError('Aggregate value schema exceeds 64 levels',line)
            return count
        trail=trail+(id(expected),);kind=expected[0];height=1
        if kind in ('INTEGER','REAL','BOOLEAN','BYTE','SHORT'):
            if expected!=(kind,):raise KarelRuntimeError('Aggregate scalar type is malformed',line)
            count=1
        elif kind=='STRING':
            if len(expected)!=2 or type(expected[1]) is not int or not 1<=expected[1]<=254:
                raise KarelRuntimeError('Aggregate value STRING needs concrete capacity in 1..254',line)
            count=1
        elif kind=='JOINTPOS':count=joint_width(expected)
        elif kind=='ARRAY':
            if len(expected) not in (3,4):raise KarelRuntimeError('Aggregate value ARRAY type is malformed',line)
            array_identity(expected);shape=array_shape(expected)
            if not 1<=len(shape)<=3 or any(type(size) is not int or not 1<=size<=32767 for size in shape):
                raise KarelRuntimeError('Aggregate value ARRAY requires concrete shape in 1..32767',line)
            count=schema(expected[2],trail)*math.prod(shape)
            height=1+schema_cache[id(expected[2])][1]
            if expected[2][0]=='ARRAY' and array_identity(expected[2]) is None:
                raise KarelRuntimeError('Aggregate value nested ARRAY needs a named component type',line)
            if len(array_dimensions(expected))>3:
                raise KarelRuntimeError('Aggregate value ARRAY supports at most three logical dimensions',line)
        elif kind in RECORD_TYPES:
            if kind=='STRUCTURE':
                if (len(expected)!=3 or type(expected[1]) is not str or not re.fullmatch(r'[A-Z_][A-Z_0-9]*',expected[1])
                        or type(expected[2]) is not tuple or not expected[2]):
                    raise KarelRuntimeError('Aggregate value STRUCTURE needs a nominal name and nonempty fields',line)
                names=set()
                for field in expected[2]:
                    if (type(field) is not tuple or len(field)!=2 or type(field[0]) is not str
                            or not re.fullmatch(r'[A-Z_][A-Z_0-9]*',field[0]) or field[0] in names):
                        raise KarelRuntimeError('Aggregate value STRUCTURE has malformed or duplicate fields',line)
                    names.add(field[0])
            elif expected!=(kind,):raise KarelRuntimeError('Aggregate builtin record type is malformed',line)
            fields=record_fields(expected);count=0
            for name,field in fields:
                count+=schema(field,trail);height=max(height,1+schema_cache[id(field)][1])
                if count>32767:break
        else:raise KarelRuntimeError('Aggregate values require data types without FILE/PATH/QUEUE resources',line)
        if count>32767:raise KarelRuntimeError('Aggregate values are limited to 32767 scalar leaves by the prototype',line)
        schema_cache[id(expected)]=(count,height);return count

    try:return schema(spec)
    except KarelRuntimeError as exc:
        if exc.line is None and line is not None:raise KarelRuntimeError(str(exc),line) from None
        raise


def _partial_aggregate_value(spec, value, line=None):
    """Validate every declared field before detaching partial data-only values."""
    _validate_data_schema(spec,line)
    def copy_value(expected,item,trail=()):
        kind=expected[0]
        if kind in ('ARRAY','JOINTPOS',*RECORD_TYPES):
            if id(item) in trail:raise KarelRuntimeError('Aggregate value storage is cyclic',line)
            trail=trail+(id(item),)
        if kind=='ARRAY':
            shape=array_shape(expected)
            if (type(item) is not Array or item.spec!=expected or item.shape!=shape
                    or not _array_storage(item.values,line) or len(item.values)!=math.prod(shape)):
                raise KarelRuntimeError('Aggregate value ARRAY requires identical concrete type, shape and storage',line)
            result=Array(expected)
            result.values[:]=[copy_value(expected[2],child,trail) for child in item.values]
            return result
        if kind in RECORD_TYPES:
            fields=dict(record_fields(expected))
            if (type(item) is not Structure or item.spec!=expected or type(item.types) is not dict or item.types!=fields
                    or type(item.values) is not dict or set(item.values)!=set(fields)):
                raise KarelRuntimeError('Aggregate value record requires identical nominal type and fields',line)
            result=Structure(expected)
            for name,field in fields.items():
                updated=copy_value(field,item.values[name],trail)
                if kind=='CONFIG' and field==INTEGER and updated is not UNINITIALIZED and not -8<=updated<=7:
                    raise KarelRuntimeError('CONFIG turn numbers are limited to -8..7 by the prototype',line)
                result.values[name]=replace_value(result.values[name],updated)
            return result
        if kind=='JOINTPOS':
            if type(item) is not JointPosition or item.spec!=expected or type(item.values) is not list or len(item.values)!=expected[1]:
                raise KarelRuntimeError('Aggregate value joint requires identical declared axis count and storage',line)
            result=JointPosition(expected)
            result.values[:]=[copy_value(REAL,axis,trail) for axis in item.values]
            return result
        if item is UNINITIALIZED:return UNINITIALIZED
        if item is UNKNOWN_BYTE:
            if expected!=BYTE:raise KarelRuntimeError('Unknown BYTE marker requires BYTE aggregate storage',line)
            return UNKNOWN_BYTE
        if kind=='STRING' and len(ascii_string(item,line))>expected[1]:
            raise KarelRuntimeError('Aggregate value STRING exceeds its declared capacity',line)
        return checked(expected,item,line)
    return copy_value(spec,value)


def _aggregate_value(spec, value, line=None, *, allow_partial=None):
    """Shared checked copy; Pythonic transfers retain validated missing leaves."""
    if allow_partial is None:allow_partial=_pythonic()
    if allow_partial:return _partial_aggregate_value(spec,value,line)
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
        if kind == 'JOINTPOS' and not fully_initialized(item):
            raise KarelRuntimeError('Joint copy requires initialized axes',line)
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
    """Construct a frame from complete points with supplied origin CONFIG."""
    if not _pythonic(): raise KarelRuntimeError('FRAME requires Pythonic mode', line)
    if type(arguments) not in (list, tuple) or len(arguments) not in (3,4,5):
        raise KarelRuntimeError('FRAME requires three points and optional origin and CONFIG', line)
    explicit_config=(len(arguments)>3 and isinstance(arguments[-1],Structure)
                     and arguments[-1].spec==('CONFIG',))
    if len(arguments)==5 and not explicit_config:
        raise KarelRuntimeError('Five-argument FRAME requires CONFIG as the fifth argument',line)
    point_args=arguments[:-1] if explicit_config else arguments
    points = [vector_value(value, line) if isinstance(value, Structure) and value.spec == ('VECTOR',)
              else frame_value(value, line) for value in point_args]
    origin = points[3] if len(points) == 4 else points[0]
    if explicit_config:
        if origin.spec!=('VECTOR',):
            raise KarelRuntimeError('FRAME with explicit CONFIG requires a VECTOR origin',line)
        config=positional_value(('CONFIG',),arguments[-1],line)
    else:
        if origin.spec == ('VECTOR',):
            raise KarelRuntimeError('FRAME VECTOR origin requires explicit CONFIG', line)
        config=origin.values['CONFIG_DATA']
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
    result=_frame_result(rotation, locations[3] if len(points) == 4 else locations[0], config, line, result_type=result_type)
    if result_type==('XYZWPREXT',) and origin.spec==result_type:
        for key in ('EXT1','EXT2','EXT3'): result.values[key]=origin.values[key]
    return result


def frame_inverse(value, line=None):
    """Invert a pose or negate a translation VECTOR without inventing CONFIG."""
    if not _pythonic(): raise KarelRuntimeError('Frame transforms require Pythonic mode', line)
    if isinstance(value, Structure) and value.spec == ('VECTOR',):
        result = vector_value(value, line)
        result.values.update((axis, real(-result.values[axis], line)) for axis in ('X','Y','Z'))
        return result
    rotation, translation, config = _frame_parts(value, line)
    inverse = tuple(zip(*rotation))
    location = tuple(real(-sum(row[j]*translation[j] for j in range(3)), line) for row in inverse)
    result=_frame_result(inverse, location, config, line, result_type=value.spec)
    if value.spec==('XYZWPREXT',):
        for key in ('EXT1','EXT2','EXT3'): result.values[key]=value.values[key]
    return result


def frame_transform(left, right, line=None):
    """Compose poses, affine points or explicit translation-only VECTOR frames."""
    if not _pythonic(): raise KarelRuntimeError('Frame transforms require Pythonic mode', line)
    if isinstance(left, Structure) and left.spec == ('VECTOR',):
        translation = vector_value(left, line)
        result = (vector_value(right, line) if isinstance(right, Structure) and right.spec == ('VECTOR',)
                  else frame_value(right, line))
        location = result.values['LOCATION'].values if result.spec == ('POSITION',) else result.values
        location.update((axis, real(translation.values[axis] + location[axis], line)) for axis in ('X','Y','Z'))
        return result
    rotation, translation, _ = _frame_parts(left, line)
    if isinstance(right,Structure) and right.spec==('VECTOR',):
        point=vector_value(right,line)
        local=tuple(point.values[axis] for axis in ('X','Y','Z'))
        result=Structure(('VECTOR',))
        result.values.update(zip(('X','Y','Z'),
            (real(translation[i]+sum(rotation[i][j]*local[j] for j in range(3)),line) for i in range(3))))
        return result
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
        if len(arguments) not in (7,10):
            raise KarelRuntimeError('POS requires seven arguments and optionally three external axes',line)
        components = [real(value, line) for value in arguments[:6]]
        for field, value, limit in zip(('X','Y','Z','W','P','R'), components, (10000000,)*3 + (180,)*3):
            if not -limit <= value <= limit:
                raise KarelRuntimeError(f'POS {field} must be in {-limit}..{limit}', line)
        config = positional_value(('CONFIG',), arguments[6], line)
        axes = [real(value,line) for value in arguments[7:]]
        result = Structure(('XYZWPREXT',) if axes else ('XYZWPR',))
        result.values.update(zip(('X','Y','Z','W','P','R'), components))
        result.values['CONFIG_DATA'] = config
        result.values.update(zip(('EXT1','EXT2','EXT3'),axes))
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
        if len(arguments) not in ((1,2) if _pythonic() else (1,)):
            raise KarelRuntimeError('ARRAY_LEN has an invalid argument count',line)
        array = arguments[0]
        if not isinstance(array, Array): raise KarelRuntimeError('Expected ARRAY', line)
        if not _pythonic() and len(array_dimensions(array.spec)) != 1:
            raise KarelRuntimeError('ARRAY_LEN on multidimensional arrays needs dimension-count validation', line)
        if (type(array.shape) is not tuple or not 1 <= len(array.shape) <= 3 or array.shape != array_shape(array.spec)
                or any(type(size) is not int or not 1 <= size <= 32767 for size in array.shape)):
            raise KarelRuntimeError('ARRAY_LEN requires a concrete valid shape', line)
        if len(arguments)==1:
            return array.shape[0]
        dimensions=array_dimensions(array.spec)
        dimension=integer(arguments[1],line)
        if not 1<=len(dimensions)<=3 or any(type(size) is not int or not 1<=size<=32767 for size in dimensions):
            raise KarelRuntimeError('ARRAY_LEN requires concrete valid logical dimensions',line)
        if not 1<=dimension<=len(dimensions):
            raise KarelRuntimeError(f'ARRAY_LEN dimension {dimension} outside 1..{len(dimensions)}',line)
        return dimensions[dimension-1]
    if name == 'UNINIT': return uninit(arguments[0],line)
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
    if isinstance(value,FileHandle): return dict(file=value.logical_name or value.name,open=value.owner is not None,position=value.position,binary=value.binary,status=value.status)
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


def config_read_reference(value,name,line=None):
    """Capture a declared CONFIG field without accepting substituted record schemas."""
    fields=dict(record_fields(('CONFIG',)))
    if (not _pythonic() or type(value) is not Structure or value.spec!=('CONFIG',)
            or value.types!=fields or type(value.values) is not dict or set(value.values)!=set(fields)
            or type(name) is not str or name not in fields):
        raise KarelRuntimeError('READ requires declared CONFIG storage and scalar fields',line)
    result=field_reference(value,name,line)
    _validate_read_target(result,line)
    return result


def _validate_read_target(target,line=None):
    """Accept ordinary scalar cells and explicit bounded Pythonic CONFIG fields."""
    if type(target) is ConfigFieldReference and _pythonic():
        target.validate_storage(line)
    elif type(target) is AssociationFieldReference and _pythonic():
        target.validate_storage(line)
    elif type(target) is _QueueReadField and _pythonic():
        _validate_queue_field(target,line)
    elif type(target) is _PositionReadField and _pythonic():
        _validate_position_read_field(target,line)
    elif type(target) is not Reference:
        raise KarelRuntimeError('READ requires ordinary scalar references, bounded CONFIG fields or complete POSITION captures',line)
    _read_scalar_spec(target.spec,line)


def _validate_read_value(target,value,line=None):
    """Preflight without storing or normalizing raw SHORT sentinel data twice."""
    _validate_read_target(target,line)
    if type(target) is _PositionReadField:target=target.base
    if type(target) is ConfigFieldReference:target.validate(value,line)
    else:checked(target.spec,value,line)


def capture_read_target(target, formats, line=None):
    _validate_read_target(target,line)
    return target, read_formats(target.spec, formats, line)


def path_io_components(spec,line=None):
    """Concrete data schemas for scalar PATHs and explicit PATH-bank I/O."""
    if type(spec) is not tuple or len(spec)!=3 or spec[0]!='PATH':
        raise KarelRuntimeError('PATH I/O requires an exact PATH schema',line)
    node=PREDEFINED_STRUCTURES['STD_PTH_NODE'] if spec[1] is None else spec[1];header=spec[2]
    if (type(node) is not tuple or not node or node[0]!='STRUCTURE'
            or header is not None and (type(header) is not tuple or not header or header[0]!='STRUCTURE')):
        raise KarelRuntimeError('PATH I/O requires STRUCTURE node/header schemas',line)
    for component in (node,header):
        if component is not None:_validate_data_schema(component,line)
    return node,header


def _path_io_values(spec,value,line=None,*,check=None):
    node,header=path_io_components(spec,line)
    if type(value) is not PathValue or value.spec!=spec or type(value.nodes) is not list or len(value.nodes)>32767:
        raise KarelRuntimeError('PATH I/O requires matching ordinary PATH storage',line)
    if header is None and value.data is not None:
        raise KarelRuntimeError('PATH I/O found unexpected header storage',line)
    nodes,data=value.nodes,value.data
    length=len(nodes)
    count=(scalar_leaf_count(header) if header is not None else 0)+length*scalar_leaf_count(node)
    if count>1024:raise KarelRuntimeError('PATH I/O is limited to 1024 scalar fields including CR',line)
    if check is not None:
        for _ in range(count):check(line)
        if value.spec!=spec or value.nodes is not nodes or len(nodes)!=length or value.data is not data:
            raise KarelRuntimeError('PATH I/O storage changed during preparation',line)
    values=([(header,data)] if header is not None else [])+[(node,item) for item in nodes]
    for expected,item in values:_aggregate_value(expected,item,line,allow_partial=True)
    return values


def path_array_io_type(spec):
    """Only ARRAY chains ending in PATH; embedded resource fields remain excluded."""
    if type(spec) is not tuple or not spec or spec[0]!='ARRAY':return False
    for _ in range(64):
        if type(spec) is not tuple or not spec:return False
        if spec[0]!='ARRAY':return spec[0]=='PATH' and len(spec)==3
        if len(spec) not in (3,4):return False
        spec=spec[2]
    return False


def _collection_io_stamp(value):
    if type(value) is QueueValue:
        buffer=getattr(value,'buffer',None)
        mapping=getattr(buffer,'values',None) if type(buffer) is Array else None
        return (value,value.entries,buffer,mapping),(len(value.entries),getattr(value,'sequence',None),
                                                     getattr(value,'initialized',None))
    return (value,value.nodes,getattr(value,'data',None)),(len(value.nodes),)


def _collection_io_unchanged(value,stamp):
    storage,metadata=_collection_io_stamp(value)
    original,expected=stamp
    return metadata==expected and all(item is prior for item,prior in zip(storage,original))


def _collection_bank_io_preflight(value,line,check,*,field_limit=None):
    from .storage import _collection_array_rows

    spec=value.spec
    queue_bank=queue_io_type(spec)
    label='Queue ARRAY I/O' if queue_bank else 'PATH ARRAY I/O'
    units_per_field=2 if queue_bank else 1
    try:
        rows,units=_collection_array_rows(spec,value,False,allow_windows=True)
    except (ValueError,KarelRuntimeError,TypeError,IndexError,AttributeError,RecursionError) as error:
        raise KarelRuntimeError(label+': '+str(error),line) from error
    if field_limit is not None and units-len(rows)>field_limit*units_per_field:
        raise KarelRuntimeError(f'{label} is limited to {field_limit} scalar fields including CR',line)
    if check is None:return
    cells=[_collection_io_stamp(item) for _,item in rows]
    for _ in range(units):check(line)
    try:
        current,current_units=_collection_array_rows(spec,value,False,allow_windows=True)
    except (ValueError,KarelRuntimeError,TypeError,IndexError,AttributeError,RecursionError) as error:
        raise KarelRuntimeError(label+' storage changed during preparation',line) from error
    if (current_units!=units or len(current)!=len(cells)
            or any(not _collection_io_unchanged(item,stamp) for (_,item),stamp in zip(current,cells))):
        raise KarelRuntimeError(label+' storage changed during preparation',line)


def path_array_io_values(spec,value,line=None,*,check=None):
    """Preflight an entire selected bank and retain original PATH cell identities."""
    from .extended import collection_array_storage
    matches=False
    if _pythonic() and path_array_io_type(spec) and type(value) is Array:
        try:matches=parameter_accepts(spec,value.spec)
        except (KarelRuntimeError,TypeError,IndexError,RecursionError):pass
    if not matches:raise KarelRuntimeError('PATH ARRAY I/O requires matching Pythonic storage',line)
    _collection_bank_io_preflight(value,line,check,field_limit=1024)
    captured=collection_array_storage(value.spec,value,line);result=[]
    def visit(item):
        if type(item) is Array:
            for child in item.values:visit(child)
        else:result.append(item)
    visit(captured)
    return result


def queue_io_type(spec):
    """Only scalar queues or ARRAY chains ending in queues, never record fields."""
    for _ in range(64):
        if type(spec) is not tuple or not spec:return False
        if spec[0]!='ARRAY':return spec==('QUEUE_TYPE',)
        if len(spec) not in (3,4):return False
        spec=spec[2]
    return False


def _queue_io_payload(value,line=None):
    from .storage import collection_payload
    try:payload=collection_payload(('QUEUE_TYPE',),value)
    except (ValueError,KarelRuntimeError,TypeError,IndexError,AttributeError,RecursionError) as error:raise KarelRuntimeError('Queue I/O: '+str(error),line) from error
    if not payload['initialized']:raise KarelRuntimeError('Queue I/O requires INIT_QUEUE before use',line)
    return payload


def queue_io_values(spec,value,line=None,*,check=None):
    from .extended import collection_array_storage
    from .storage import _collection_array_units

    if not _pythonic() or not queue_io_type(spec):raise KarelRuntimeError('Queue I/O requires a Pythonic queue schema',line)
    if spec==('QUEUE_TYPE',):
        try:units=_collection_array_units(spec,value,False)
        except (ValueError,KarelRuntimeError,TypeError,IndexError,AttributeError,RecursionError) as error:
            raise KarelRuntimeError('Queue I/O: '+str(error),line) from error
        if len(value.entries)>1024:raise KarelRuntimeError('Queue I/O is limited to 1024 entry values including CR',line)
        if check is not None:
            stamp=_collection_io_stamp(value)
            for _ in range(units):check(line)
            if value.spec!=spec or type(getattr(value,'entries',None)) is not list or not _collection_io_unchanged(value,stamp):
                raise KarelRuntimeError('Queue I/O storage changed during preparation',line)
        _queue_io_payload(value,line)
        return [value]
    matches=False
    if type(value) is Array:
        try:matches=parameter_accepts(spec,value.spec)
        except (KarelRuntimeError,TypeError,IndexError,RecursionError):pass
    if not matches:raise KarelRuntimeError('Queue ARRAY I/O requires matching concrete storage',line)
    _collection_bank_io_preflight(value,line,check,field_limit=1024)
    try:captured=collection_array_storage(value.spec,value,line)
    except (ValueError,KarelRuntimeError,TypeError,IndexError,AttributeError,RecursionError) as error:
        raise KarelRuntimeError('Queue ARRAY I/O: '+str(error),line) from error
    values=[]
    def visit(item):
        if type(item) is Array:
            for child in item.values:visit(child)
        else:values.append(item)
    visit(captured)
    if any(item.initialized is not True for item in values):
        raise KarelRuntimeError('Queue I/O requires INIT_QUEUE before use',line)
    return values


def _queue_buffer_witness(buffer,line=None):
    try:
        if buffer is None:return None
        if (type(buffer) is not Array or len(array_dimensions(buffer.spec))!=1 or buffer.spec[2]!=INTEGER
                or buffer.shape!=array_shape(buffer.spec) or not _array_storage(buffer.values,line)
                or len(buffer.values)!=math.prod(buffer.shape)):
            raise KarelRuntimeError('Queue READ requires a matching INTEGER backing ARRAY',line)
        _validate_data_schema(buffer.spec,line)
        values=buffer.values
        if type(values) is _ArrayWindow:
            return buffer.spec,buffer.shape,id(values.storage),values.start,values.size,values.length
        return buffer.spec,buffer.shape,id(values),0,len(values),len(values)
    except (KarelRuntimeError,TypeError,IndexError,AttributeError,RecursionError) as error:
        raise KarelRuntimeError('Queue READ buffer: '+str(error),line) from error


class _QueueReadField:
    __slots__=('cohort','index')
    spec=INTEGER
    def __init__(self,cohort,index):self.cohort,self.index=cohort,index
    def raw(self):return self.cohort.queue.entries[self.index][1]
    def set(self,value,line=None):
        _validate_queue_field(self,line);cohort=self.cohort
        if (type(cohort.plan) is not tuple or len(cohort.plan)!=len(cohort.members)
                or self.index!=cohort.cursor or type(value) is not int or value!=cohort.plan[self.index][1]):
            raise KarelRuntimeError('Queue READ requires a complete prepared input cohort',line)
        if self.index==0:
            cohort.entries[:]=cohort.plan
            cohort.queue.buffer=None;cohort.buffer=None;cohort.witness=None
            cohort.snapshot=cohort.plan
        cohort.cursor+=1


class _QueueReadCohort:
    __slots__=('queue','source','location','entries','snapshot','sequence','buffer','witness','members','plan','cursor')
    def __init__(self,source,line=None):
        self.source=source;self.queue=source.raw();self.entries=self.queue.entries
        self.location=(source.storage,source.key)
        self.snapshot=tuple(tuple(pair) for pair in self.entries)
        self.sequence=self.queue.sequence;self.buffer=self.queue.buffer
        self.witness=_queue_buffer_witness(self.buffer,line)
        self.members=tuple(_QueueReadField(self,index) for index in range(len(self.entries)))
        self.plan=None;self.cursor=0
    def validate(self,line=None):
        from .variable_archives import ordinary
        if (not _pythonic() or not ordinary(self.source) or self.source.spec!=('QUEUE_TYPE',)
                or self.source.storage is not self.location[0] or self.source.key!=self.location[1]
                or self.source.raw() is not self.queue or type(self.queue) is not QueueValue
                or self.queue.spec!=('QUEUE_TYPE',) or self.queue.entries is not self.entries
                or type(self.entries) is not list or self.queue.initialized is not True
                or type(self.queue.sequence) is not int or self.queue.sequence!=self.sequence
                or type(self.members) is not tuple or type(self.snapshot) is not tuple
                or len(self.entries)!=len(self.members) or len(self.entries)!=len(self.snapshot)
                or _queue_buffer_witness(self.queue.buffer,line)!=self.witness
                or _queue_buffer_witness(self.buffer,line)!=self.witness):
            raise KarelRuntimeError('Queue READ capture changed before input publication',line)


def _validate_queue_field(field,line=None):
    cohort=field.cohort;index=field.index
    if (type(cohort) is not _QueueReadCohort or type(cohort.members) is not tuple or type(index) is not int or not 0<=index<len(cohort.members)
            or cohort.members[index] is not field):raise KarelRuntimeError('Malformed queue READ capture',line)
    cohort.validate(line)
    pair=cohort.entries[index]
    if (type(pair) not in (tuple,list) or len(pair)!=2 or type(pair[0]) is not int
            or type(pair[1]) is not int or (pair[0],pair[1])!=cohort.snapshot[index]):
        raise KarelRuntimeError('Queue READ entry changed before input publication',line)


def _capture_queue_read(target,line=None,*,check=None):
    from .variable_archives import ordinary
    if not ordinary(target):raise KarelRuntimeError('Queue READ requires ordinary writable queue storage',line)
    value=target.raw()
    queue_io_values(target.spec,value,line,check=check)
    if not ordinary(target) or target.raw() is not value:
        raise KarelRuntimeError('Queue READ destination changed during preparation',line)
    references=[]
    def visit(item,reference):
        if type(item) is Array:
            for index,child in enumerate(item.values):visit(child,Reference(item.spec[2],item.values,index))
        elif item.entries:references.append(reference)
    visit(value,target)
    fields=[(field,()) for reference in references for field in _QueueReadCohort(reference,line).members]
    if not fields:raise KarelRuntimeError('Queue READ requires existing initialized entry values',line)
    return fields


def _queue_read_cohorts(targets,line=None):
    cohorts={}
    for offset,target in enumerate(targets):
        if type(target) is _QueueReadField:cohorts.setdefault(target.cohort,[]).append((offset,target.index))
    if not cohorts:return cohorts
    occupied=set()
    for cohort,entries in cohorts.items():
        if (len(entries)!=len(cohort.members) or [index for _,index in entries]!=list(range(len(entries)))
                or entries[-1][0]-entries[0][0]!=len(entries)-1):
            raise KarelRuntimeError('Queue READ requires every unchanged entry field in order',line)
        cells={(id(cohort.queue),'queue'),(id(cohort.entries),'entries'),(id(cohort.source.storage),cohort.source.key)}
        cells.update((id(cohort.entries),index) for index in range(len(cohort.entries)))
        for pair in cohort.entries:
            if type(pair) is list:cells.update(((id(pair),0),(id(pair),1)))
        if occupied&cells:raise KarelRuntimeError('Queue READ entry storage must be disjoint',line)
        occupied.update(cells)
    for target in targets:
        if type(target) is _QueueReadField:continue
        base=target.base if type(target) is _PositionReadField else target
        if _reference_cells(base)&occupied:raise KarelRuntimeError('Queue READ entry storage overlaps another destination',line)
    return cohorts


def _validate_read_targets(targets,line=None):
    cohorts=_validate_position_read_targets(targets,line)
    cohorts.update(_queue_read_cohorts(targets,line))
    return cohorts


def _prepare_read_values(targets,values,line=None):
    cohorts=_validate_read_targets(targets,line)
    positions={cohort:entries for cohort,entries in cohorts.items() if type(cohort) is not _QueueReadCohort}
    result=_prepare_position_read_values(targets,values,line,cohorts=positions)
    plans=[]
    for cohort,entries in cohorts.items():
        if type(cohort) is _QueueReadCohort:
            plan=tuple((entry_id,checked(INTEGER,result[offset],line))
                       for (entry_id,_),(offset,_) in zip(cohort.snapshot,entries))
            plans.append((cohort,plan))
    for cohort,plan in plans:
        cohort.plan=plan;cohort.cursor=0
    return result


def aggregate_write_type(spec,trail=()):
    """Type-only output eligibility; POSITION is readable data, resources are not."""
    if type(spec) is not tuple or not spec or id(spec) in trail or len(trail)>=64:return False
    kind=spec[0];trail=trail+(id(spec),)
    if len(trail)==1 and queue_io_type(spec):return True
    if len(trail)==1 and path_array_io_type(spec):return aggregate_write_type(array_leaf_spec(spec))
    if kind=='PATH' and len(trail)==1:
        try:components=path_io_components(spec)
        except (KarelRuntimeError,TypeError,IndexError):return False
        return all(aggregate_write_type(item,trail) for item in components if item is not None)
    if kind in ('INTEGER','REAL','BOOLEAN','BYTE','SHORT','STRING','JOINTPOS'):return True
    if kind=='ARRAY':return aggregate_write_type(spec[2],trail)
    if kind in RECORD_TYPES:return all(aggregate_write_type(member,trail) for _,member in record_fields(spec))
    return False


def aggregate_format_kinds(spec,trail=()):
    """Scalar format categories without expanding ARRAY dimensions or storage."""
    if type(spec) is not tuple or not spec or id(spec) in trail or len(trail)>=64:
        raise KarelRuntimeError('Aggregate format schema is malformed or exceeds 64 levels')
    kind=spec[0];trail=trail+(id(spec),)
    if len(trail)==1 and queue_io_type(spec):return {'INTEGER'}
    if len(trail)==1 and path_array_io_type(spec):return aggregate_format_kinds(array_leaf_spec(spec))
    if kind=='PATH' and len(trail)==1:
        kinds=set()
        for item in path_io_components(spec):
            if item is not None:kinds.update(aggregate_format_kinds(item,trail))
        return kinds
    if kind=='ARRAY':return aggregate_format_kinds(spec[2],trail)
    if kind=='JOINTPOS':return {'REAL'}
    if kind in RECORD_TYPES:
        kinds=set()
        for _,member in record_fields(spec):kinds.update(aggregate_format_kinds(member,trail))
        return kinds
    if kind in ('INTEGER','REAL','BOOLEAN','BYTE','SHORT','STRING'):return {kind}
    raise KarelRuntimeError('Aggregate formats require data-only scalar leaves')


class _AggregateWriteValue:
    __slots__=('spec','fields')
    def __init__(self,spec,fields):self.spec=spec;self.fields=tuple(fields)


def capture_aggregate_write(spec,value,line=None,*,check=None):
    """Validate and detach complete immutable scalar leaves before format calls."""
    if not _pythonic():raise KarelRuntimeError('Aggregate WRITE requires Pythonic mode',line)
    if queue_io_type(spec):
        fields=[(INTEGER,pair[1]) for item in queue_io_values(spec,value,line,check=check) for pair in item.entries]
        return _AggregateWriteValue(spec,fields)
    if path_array_io_type(spec):
        fields=[]
        for item in path_array_io_values(spec,value,line,check=check):
            fields.extend(capture_aggregate_write(item.spec,item,line).fields)
        return _AggregateWriteValue(spec,fields)
    if spec[0]=='PATH':
        fields=[]
        for expected,item in _path_io_values(spec,value,line,check=check):
            fields.extend(capture_aggregate_write(expected,item,line).fields)
        return _AggregateWriteValue(spec,fields)
    actual=getattr(value,'spec',None)
    if spec[0]=='ARRAY' and actual is not None and parameter_accepts(spec,actual):spec=actual
    count=_validate_data_schema(spec,line)
    if count>1024:raise KarelRuntimeError('Aggregate WRITE is limited to 1024 scalar items including CR',line)
    source=_aggregate_value(spec,value,line);fields=[]
    def capture(expected,item):
        item=require(item,line);kind=expected[0]
        if kind=='ARRAY':
            for child in item.values:capture(expected[2],child)
        elif kind=='JOINTPOS':
            for axis in item.values:capture(REAL,axis)
        elif kind in RECORD_TYPES:
            for name,member in record_fields(expected):capture(member,item.values[name])
        else:fields.append((expected,item))
    capture(spec,source)
    return _AggregateWriteValue(spec,fields)


def format_aggregate_write(captured,formats=(),line=None,*,file=None):
    """Interpret one captured format list separately for every scalar kind."""
    if not _pythonic() or type(captured) is not _AggregateWriteValue or type(captured.fields) is not tuple or not 0<=len(captured.fields)<=1024:
        raise KarelRuntimeError('Aggregate WRITE requires checked captured data',line)
    if type(formats) not in (list,tuple) or len(formats)>2 or any(type(value) is not int for value in formats):
        raise KarelRuntimeError('WRITE requires at most two INTEGER format specifiers',line)
    if not captured.fields:
        if not aggregate_write_type(captured.spec) or not (captured.spec[0]=='PATH' or path_array_io_type(captured.spec) or queue_io_type(captured.spec)):
            raise KarelRuntimeError('Only an empty PATH may omit captured output fields',line)
        if formats:raise KarelRuntimeError('Empty PATH/queue output requires unformatted WRITE',line)
        return [b''] if file is not None and file.binary else ['']
    result=[]
    for expected,item in captured.fields:
        kind=expected[0];controls=formats
        if not controls and kind=='STRING' and file is not None and file.binary:controls=[expected[1]]
        result.append(file_piece(file,kind,item,controls,line) if file is not None else format_write_item(kind,item,controls,line))
    return result


def aggregate_write_pieces(spec,value,line=None,*,file=None,check=None):
    """Preserve the original unformatted generated-code entry point."""
    return format_aggregate_write(capture_aggregate_write(spec,value,line,check=check),(),line,file=file)


def aggregate_read_type(spec,trail=()):
    """Type-only eligibility, including generic source ARRAY/STRING formals."""
    if type(spec) is not tuple or not spec or id(spec) in trail or len(trail)>=64:return False
    kind=spec[0];trail=trail+(id(spec),)
    if len(trail)==1 and queue_io_type(spec):return True
    if len(trail)==1 and path_array_io_type(spec):return aggregate_read_type(array_leaf_spec(spec))
    if kind=='PATH' and len(trail)==1:
        try:components=path_io_components(spec)
        except (KarelRuntimeError,TypeError,IndexError):return False
        return all(aggregate_read_type(item,trail) for item in components if item is not None)
    if kind in ('INTEGER','REAL','BOOLEAN','BYTE','SHORT','STRING','JOINTPOS'):return True
    if kind=='ARRAY':return aggregate_read_type(spec[2],trail)
    if kind in RECORD_TYPES:return all(aggregate_read_type(member,trail) for _,member in record_fields(spec))
    return False


def capture_aggregate_read_target(target,formats,line=None,*,check=None):
    """Capture shaped data leaves once; keep ordinary scalar input transports."""
    if _pythonic() and type(target) is _ArrayPrefixTarget:
        return capture_prefix_read_target(target,formats,line)
    if not _pythonic() or type(target) is not Reference or not aggregate_read_type(target.spec):
        raise KarelRuntimeError('Aggregate READ requires writable resource-free data',line)
    if type(formats) not in (list,tuple) or formats:
        raise KarelRuntimeError('Aggregate READ formats require selecting scalar fields',line)
    if queue_io_type(target.spec):return _capture_queue_read(target,line,check=check)
    if path_array_io_type(target.spec):
        result=[]
        for item in path_array_io_values(target.spec,target.raw(),line,check=check):
            if item.data is not None or item.nodes:
                result.extend(capture_aggregate_read_target(Reference(item.spec,{'value':item},'value'),[],line))
        if not result:raise KarelRuntimeError('PATH ARRAY READ requires existing header or node data',line)
        return result
    if target.spec[0]=='PATH':
        value=target.raw();components=_path_io_values(target.spec,value,line,check=check)
        if not components:raise KarelRuntimeError('PATH READ requires an existing header or node',line)
        result=[]
        if target.spec[2] is not None:
            result.extend(capture_aggregate_read_target(Reference(target.spec[2],vars(value),'data'),[],line))
        for index in range(len(value.nodes)):
            result.extend(capture_aggregate_read_target(Reference(value.node_spec,value.nodes,index),[],line))
        return result
    count=_validate_data_schema(target.spec,line)
    if count>1024:raise KarelRuntimeError('Aggregate READ is limited to 1024 scalar destinations including CR',line)
    # Check exact host schemas and all known values; no source data is consumed.
    _aggregate_value(target.spec,target.raw(),line)
    result=[]
    def descend(reference):
        spec=reference.spec;kind=spec[0]
        if kind in ('INTEGER','REAL','BOOLEAN','BYTE','SHORT','STRING'):
            result.append(capture_read_target(reference,[],line));return
        value=reference.raw()
        if value is UNINITIALIZED:raise KarelRuntimeError('Aggregate READ requires existing shaped containers; missing scalar leaves are allowed',line)
        if kind=='ARRAY':
            for index in range(len(value.values)):descend(Reference(spec[2],value.values,index))
        elif kind=='JOINTPOS':
            for index in range(len(value.values)):descend(Reference(REAL,value.values,index))
        elif kind=='POSITION':result.extend(_capture_position_read(value,line))
        elif kind in ASSOCIATION_TYPES:
            for name,_ in record_fields(spec):descend(field_reference(value,name,line))
        else:
            for name,member in record_fields(spec):
                descend(config_read_reference(value,name,line) if kind=='CONFIG' else Reference(member,value.values,name))
    descend(target)
    return result


def capture_prefix_read_target(target,formats,line=None):
    """Expand captured original cells, without reading into a temporary row."""
    if not _pythonic() or type(target) is not _ArrayPrefixTarget or not aggregate_read_type(target.spec):
        raise KarelRuntimeError('Prefix READ requires captured writable data',line)
    if type(formats) not in (list,tuple) or formats:
        raise KarelRuntimeError('Prefix READ capture requires default scalar controls',line)
    if _validate_data_schema(target.spec,line)>1024:
        raise KarelRuntimeError('Prefix READ is limited to 1024 scalar destinations including CR',line)
    result=[]
    for reference in target.references(line):
        if reference.spec[0] in ('INTEGER','REAL','BOOLEAN','BYTE','SHORT','STRING'):result.append(capture_read_target(reference,[],line))
        else:result.extend(capture_aggregate_read_target(reference,[],line))
    return result


def format_aggregate_read_group(group,formats,line=None):
    """Apply formats after complete leaf/reference capture, before input."""
    if not _pythonic() or type(group) not in (list,tuple) or not 1<=len(group)<=1024:
        raise KarelRuntimeError('Aggregate READ requires captured scalar fields',line)
    result=[]
    for item in group:
        if type(item) is not tuple or len(item)!=2:raise KarelRuntimeError('Malformed aggregate READ capture',line)
        target,_=item;_validate_read_target(target,line)
        result.append((target,read_formats(target.spec,formats,line)))
    return result


def flatten_read_groups(groups,line_breaks=(),line=None):
    """Translate source item CR offsets to the expanded scalar request offsets."""
    if type(groups) not in (list,tuple):raise KarelRuntimeError('READ requires captured target groups',line)
    positions=_read_line_breaks(len(groups),line_breaks,line);targets=[];formats=[];offsets=[0]
    for group in groups:
        if type(group) not in (list,tuple) or not group:raise KarelRuntimeError('READ target groups require scalar fields',line)
        for item in group:
            if type(item) is not tuple or len(item)!=2:raise KarelRuntimeError('Malformed READ target group',line)
            target,controls=item;_validate_read_target(target,line)
            targets.append(target);formats.append(read_formats(target.spec,controls,line))
        offsets.append(len(targets))
    breaks=tuple(offsets[position] for position in positions)
    _read_line_breaks(len(targets),breaks,line)
    return targets,formats,breaks


class TextInput:
    """Explicit ASCII text adapter for Pythonic READ, with a persistent cursor."""
    def __init__(self, text, *, terminator=None, field_mode=False, final=True):
        if type(text) is not str or not text.isascii():
            raise ValueError('TextInput requires an ASCII string')
        if terminator is not None and (type(terminator) is not int or not 0<=terminator<=127):
            raise ValueError('TextInput terminator must be an ASCII code or None')
        if type(field_mode) is not bool: raise ValueError('TextInput field_mode must be BOOLEAN')
        if type(final) is not bool: raise ValueError('TextInput final must be BOOLEAN')
        self.final = final
        self.field_mode = field_mode
        self._text = text
        self._separator = re.compile(r'\r\n|\r|\n' if terminator in (None,10,13) else re.escape(chr(terminator)))
        self._record_start, self._bounds, self._eof_column = 0, None, 1
        self._row, self._column, self._after_field = 0, 0, False

    def _checkpoint(self):
        return (self._record_start, self._bounds, self._eof_column,
                self._row, self._column, self._after_field)

    def _restore(self, checkpoint):
        (self._record_start, self._bounds, self._eof_column,
         self._row, self._column, self._after_field) = checkpoint

    def _line_bounds(self):
        if self._bounds is None:
            separator = self._separator.search(self._text, self._record_start)
            self._bounds = ((len(self._text), None) if separator is None
                            else (separator.start(), separator.end()))
        return self._bounds

    @property
    def offset(self):
        """Exact ASCII byte offset, including consumed record separators."""
        return self._record_start + self._column

    @property
    def position(self):
        if self._record_start == len(self._text):
            return dict(line=self._row + 1, column=self._eof_column, eof=True)
        end, following = self._line_bounds()
        return dict(line=self._row + 1, column=self._column + 1,
                    eof=following is None and self.offset == end)

    def _next_line(self):
        end, following = self._line_bounds()
        if following is None:
            self._eof_column = end - self._record_start + 1
            self._record_start = end
        else:
            self._record_start = following
            self._row += 1
        self._bounds = None
        self._column, self._after_field = 0, False

    def _require_line(self):
        if self._record_start == len(self._text):
            position = self.position
            error = KarelRuntimeError if self.final else TextInputIncomplete
            raise error(f'TextInput reached end of input at input line {position["line"]}, column {position["column"]}')

    def _unfinished_line(self):
        return not self.final and self._line_bounds()[1] is None

    def _token(self):
        text = self._text
        while True:
            self._require_line()
            end, _ = self._line_bounds()
            cursor = self.offset
            while cursor < end and text[cursor].isspace():
                cursor += 1
            if cursor < end:
                break
            self._next_line()
        start = cursor
        while cursor < end and not text[cursor].isspace():
            cursor += 1
        self._column, self._after_field = cursor - self._record_start, True
        column = start - self._record_start + 1
        if cursor == end and self._unfinished_line():
            raise TextInputIncomplete(f'TextInput unfinished token at input line {self._row+1}, column {column}')
        return text[start:cursor], self._row + 1, column

    def _field_end(self):
        self._require_line()
        end, _ = self._line_bounds()
        if self._after_field and self.offset == end:
            self._next_line()
            self._require_line()
            end, _ = self._line_bounds()
        return end

    def _string(self, width=0):
        end = self._field_end()
        start = self.offset
        row, column = self._row + 1, self._column + 1
        stop = min(end, start + width) if width else end
        length = stop - start
        self._column, self._after_field = self._column + length, True
        if width and length != width:
            error = TextInputIncomplete if self._unfinished_line() else KarelRuntimeError
            raise error(f'TextInput incomplete field at input line {row}, column {column}; expected {width} characters')
        if not width and self._unfinished_line():
            raise TextInputIncomplete(f'TextInput unfinished STRING at input line {row}, column {column}')
        if length > 254:
            raise KarelRuntimeError(f'TextInput invalid STRING at input line {row}, column {column}')
        return self._text[start:stop], row, column

    def _quoted(self, width):
        if width:
            text, row, column = self._string(width)
            start, end = 0, len(text)
        else:
            end = self._field_end()
            text, start = self._text, self.offset
            row, column = self._row + 1, self._column + 1
        offset = start
        while offset < end and text[offset].isspace():
            offset += 1
        quoted = offset < end and text[offset] == "'"
        waiting_for_quote = offset == end
        contents = []
        if quoted:
            offset += 1
            while offset < end:
                char = text[offset]
                offset += 1
                if char == "'":
                    if offset < end and text[offset] == "'":
                        offset += 1
                    else:
                        if not width:
                            self._column += offset - start
                            self._after_field = True
                        if not width or not text[offset:end].strip():
                            return ''.join(contents), row, column
                        break
                if len(contents) <= 254:
                    contents.append(char)
        if not width:
            self._column += end - start
            self._after_field = True
            if self._unfinished_line() and (quoted or waiting_for_quote):
                raise TextInputIncomplete(f'TextInput unfinished quoted STRING at input line {row}, column {column}')
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
                if self._unfinished_line():
                    raise TextInputIncomplete(f'TextInput unfinished record at input line {self._row+1}')
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
        self._debug_statement=None
        self._task_run = None
        self._last_task_run = None
        self._task_run_services = {}
        self._task_launch = None
        self._task_parent = None
        self._task_pendant_motion = False
        self._task_settings={};self._task_trace=[];self._task_trace_sequence=0
        self._source_settings={}
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
        self._sleep_injected = sleep is not None
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
        self._group_scope_frames = []
        self._timer_frames=[];self._frame_timers={}
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
                or isinstance(status, (ReadOnlyFieldReference, ConfigFieldReference, AssociationFieldReference))):
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

    def tick(self, line=None, *, _diagnostic=True):
        if line is not None: task_root(self)._task_line=line
        if self._budget_parent is not None: self._budget_parent.tick(line,_diagnostic=False)
        if self._aborted: raise KarelAbort(self._abort_line)
        if self.task_state=='stopped': raise KarelStop('Task is stopped')
        update_timers(self,line)
        if self._budget_parent is None and self.execution.motion is not None:self.execution.motion.poll(self,line)
        if self.execution.ports is not None: self.execution.ports.poll_pulses(line)
        self.steps += 1
        if self.steps > self.max_steps:
            raise KarelRuntimeError(f'Execution step budget exceeded ({self.max_steps})', line)
        if _diagnostic and self.execution.diagnostics is not None:self.execution.diagnostics.checkpoint(self,line)
        if _diagnostic and self.execution.dynamic_display is not None:self.execution.dynamic_display.checkpoint(self,line)

    def begin(self, max_steps):
        if self._driving: raise KarelRuntimeError('A Program cannot be driven recursively')
        if self._aborted: raise KarelAbort(self._abort_line)
        if type(max_steps) is not int or max_steps < 1:
            raise ValueError('max_steps must be a positive integer')
        lineage, transferred, launch_line = self._task_launch or (None, None, None)
        if _pythonic() and self.execution.group_locks is not None:
            handoff = None if transferred is None else (lineage[1], transferred)
            self.execution.group_locks.begin(self, launch_line, handoff=handoff)
        self.max_steps, self.steps = max_steps, 0
        self._task_frames.clear();self._task_line=0;self._has_run=True
        self._task_trace.clear();self._task_trace_sequence=0
        self.write_requests.clear()
        self.read_requests.clear()
        self.clock_reads.clear()
        self.register_requests.clear()
        self.service_requests.clear()
        self._handlers.clear(); self.finish_timers()
        self._event_seen.clear(); self._edge_history.clear(); self._abort_requested=False; self._abort_request_line=None; self._current_error=None; self._lifecycle={'CONTINUE':0,'POWERUP':0}
        if self.execution.diagnostics is not None:self.execution.diagnostics.begin(self)
        self._task_run = self._last_task_run = object()
        self._task_parent = lineage
        self._task_pendant_motion = transferred is not None
        self._task_launch = None

    def finish_timers(self):
        finish_timers(self)

    def finish_teach_programs(self,*,interrupted=False):
        if self._budget_parent is None:
            if self._task_run is not None and (interrupted or self.task_state in ('stopped','aborted','failed')):
                for service in self._task_run_services:service.finish(self,self._task_run)
            self._task_run_services.clear()
            self._task_run = None
            self._task_parent = None
            self._task_pendant_motion = False
        if self.execution.motion is not None:self.execution.motion.finish_callbacks(self)
        self.finish_timers()
        if self._budget_parent is None and self.execution.motion is not None:self.execution.motion.finish(self)
        if self._budget_parent is None and self.execution.diagnostics is not None:self.execution.diagnostics.finish(self)
        bank=self.execution.teach_programs
        if bank is not None: bank.release_owner(task_root(self))
        if self.execution.group_locks is not None: self.execution.group_locks.release_owner(task_root(self))

    def extended_call(self,name,arguments,line=None):
        if not _pythonic(): raise KarelRuntimeError('Extended services require Pythonic mode',line)
        row=dict(operation=name,line=line,outcome='requested'); self.service_requests.append(row)
        try: result=self.execution.invoke(self,name,arguments,line)
        except Exception as exc:
            row['outcome']='failed'
            if isinstance(exc,KarelRuntimeError) and exc.line is None: raise KarelRuntimeError(str(exc),line) from exc
            raise
        row['outcome']='completed'; return result

    def system_pose(self,kind,group,number=None,line=None,*,axis=None):
        if not _pythonic():raise KarelRuntimeError('Robot system poses require Pythonic mode',line)
        row=dict(operation='SYSTEM_POSE',line=line,outcome='requested');self.service_requests.append(row)
        try:
            if axis is None:result=self.execution.system_pose(kind,group,number,line)
            else:result=self.execution.system_pose(kind,group,number,line,axis=axis)
        except Exception as exc:
            row['outcome']='failed'
            if isinstance(exc,KarelRuntimeError) and exc.line is None:raise KarelRuntimeError(str(exc),line) from exc
            raise
        row['outcome']='completed';return result

    def system_selection(self,kind,group,line=None):
        if not _pythonic():raise KarelRuntimeError('Frame/tool selections require Pythonic mode',line)
        row=dict(operation='SYSTEM_SELECTION_READ',line=line,outcome='requested');self.service_requests.append(row)
        try:result=self.execution.system_selection(kind,group,line)
        except Exception as exc:
            row['outcome']='failed'
            if isinstance(exc,KarelRuntimeError) and exc.line is None:raise KarelRuntimeError(str(exc),line) from exc
            raise
        row['outcome']='completed';return result

    def system_selection_write(self,kind,group,value,line=None):
        if not _pythonic():raise KarelRuntimeError('Frame/tool selections require Pythonic mode',line)
        row=dict(operation='SYSTEM_SELECTION_WRITE',line=line,outcome='requested');self.service_requests.append(row)
        try:self.execution.system_selection_write(kind,group,value,line)
        except Exception as exc:
            row['outcome']='failed'
            if isinstance(exc,KarelRuntimeError) and exc.line is None:raise KarelRuntimeError(str(exc),line) from exc
            raise
        row['outcome']='completed'

    def system_pose_write(self,kind,group,number,value,path=(),line=None):
        if not _pythonic():raise KarelRuntimeError('Robot system pose writes require Pythonic mode',line)
        row=dict(operation='SYSTEM_POSE_WRITE',line=line,outcome='requested');self.service_requests.append(row)
        try:self.execution.system_pose_write(kind,group,number,value,path,line)
        except Exception as exc:
            row['outcome']='failed'
            if isinstance(exc,KarelRuntimeError) and exc.line is None:raise KarelRuntimeError(str(exc),line) from exc
            raise
        row['outcome']='completed'

    def byname_argument(self,expected,program,path,entry,line=None):
        from .dynamic import byname
        return byname(self,expected,program,path,entry,line)

    def kinematic_assignment(self,target,value,line=None):
        if not _pythonic(): raise KarelRuntimeError('Kinematic assignments require Pythonic mode',line)
        return self._kinematic_conversion(target,value,line,'KINEMATIC_ASSIGNMENT')

    def kinematic_interface(self,target,value,line=None,*,result=False):
        """Convert an explicit joint/Cartesian interface value through its context."""
        if not _pythonic():raise KarelRuntimeError('Kinematic interfaces require Pythonic mode',line)
        if type(result) is not bool:raise KarelRuntimeError('Kinematic interface result flag must be BOOLEAN',line)
        source=getattr(value,'spec',())
        if (type(target) is not tuple or not target or type(source) is not tuple or not source
                or not ((target[0]=='JOINTPOS' and source[0] in ('POSITION','XYZWPR','XYZWPREXT'))
                        or (source[0]=='JOINTPOS' and target[0] in ('POSITION','XYZWPR','XYZWPREXT')))):
            raise KarelRuntimeError('Kinematic interfaces require one joint and one Cartesian type',line)
        return self._kinematic_conversion(target,value,line,'KINEMATIC_RETURN' if result else 'KINEMATIC_ARGUMENT')

    def array_assignment_value(self,value,target,line=None,*,source_spec=None):
        """Honor the actual schema of a borrowed generic ARRAY receiver."""
        if not _pythonic():raise KarelRuntimeError('Source ARRAY assignment requires Pythonic mode',line)
        if type(value) is not Array:raise KarelRuntimeError('Source ARRAY assignment requires ARRAY data',line)
        if source_spec is not None:
            _validate_data_schema(value.spec,line)
            if not parameter_accepts(source_spec,value.spec):
                raise KarelRuntimeError('STRUCTURE conversion source storage does not match its declared schema',line)
        if numeric_array_kind(target,value.spec):return convert_numeric_array(target,value,line)
        if positional_array_kind(target,value.spec):return convert_positional_array(target,value,line)
        if kinematic_array_kind(target,value.spec):return self.kinematic_array(target,value,line)
        if kinematic_record_kind(target,value.spec):return self.kinematic_record(target,value,line,source_spec=source_spec)
        if record_schema_kind(target,value.spec):return convert_record_schema(target,value,line,source_spec=source_spec)
        return convert_array_schema(target,value,line)

    def path_source_value(self,target,value,line=None,*,source_spec):
        return self.execution.path_source_value(self,target,value,source_spec,line)

    def path_array_source_value(self,target,value,line=None,*,source_spec):
        return self.execution.path_array_source_value(self,target,value,source_spec,line)

    def kinematic_array(self,target,value,line=None,*,kind='ASSIGNMENT'):
        """Convert one whole ARRAY under explicit scalar model/adaptor contracts."""
        if not _pythonic():raise KarelRuntimeError('Kinematic ARRAY conversion requires Pythonic mode',line)
        if type(kind) is not str or kind not in ('ASSIGNMENT','ARGUMENT','RETURN'):
            raise KarelRuntimeError('Invalid kinematic ARRAY conversion boundary',line)
        return self._kinematic_conversion(target,value,line,'KINEMATIC_ARRAY_'+kind)

    def kinematic_record(self,target,value,line=None,*,kind='ASSIGNMENT',source_spec=None):
        """Convert a user record tree using explicitly supplied model context."""
        if not _pythonic():raise KarelRuntimeError('Kinematic STRUCTURE conversion requires Pythonic mode',line)
        if type(kind) is not str or kind not in ('ASSIGNMENT','ARGUMENT','RETURN'):
            raise KarelRuntimeError('Invalid kinematic STRUCTURE conversion boundary',line)
        return self._kinematic_conversion(target,value,line,'KINEMATIC_RECORD_'+kind,source_spec=source_spec)

    def geometry_value(self,value,expected,line=None):
        if not _pythonic(): raise KarelRuntimeError('Joint geometry requires Pythonic mode',line)
        if expected[0]!='JOINTPOS': return frame_value(value,line,expected=expected)
        captured=checked(expected,value,line)
        return self._kinematic_conversion(('XYZWPREXT',),captured,line,'JOINT_GEOMETRY')

    def _kinematic_conversion(self,target,value,line,operation,*,source_spec=None):
        row=dict(operation=operation,line=line,outcome='requested');self.service_requests.append(row)
        try:
            convert=self.execution.kinematic_array if operation.startswith('KINEMATIC_ARRAY_') else self.execution.kinematic_assignment
            result=self.execution.kinematic_record(self,target,value,line,source_spec=source_spec) if operation.startswith('KINEMATIC_RECORD_') else convert(self,target,value,line)
            root=task_root(self)
            if root._aborted: raise KarelAbort(root._abort_line)
            if self._aborted: raise KarelAbort(self._abort_line)
        except Exception as exc:
            row['outcome']='failed'
            root=task_root(self)
            if root._aborted: raise KarelAbort(root._abort_line)
            if self._aborted: raise KarelAbort(self._abort_line)
            if isinstance(exc,KarelRuntimeError) and exc.line is None: raise KarelRuntimeError(str(exc),line) from exc
            if isinstance(exc,(ValueError,TypeError,KeyError,IndexError)):
                label='Joint geometry' if operation=='JOINT_GEOMETRY' else 'Kinematic ARRAY' if operation.startswith('KINEMATIC_ARRAY_') else 'Kinematic STRUCTURE' if operation.startswith('KINEMATIC_RECORD_') else 'Kinematic interface' if operation in ('KINEMATIC_ARGUMENT','KINEMATIC_RETURN') else 'Kinematic assignment'
                raise KarelRuntimeError(label+' failed: '+str(exc),line) from exc
            raise
        row['outcome']='completed';return result

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
        input_cohorts=_validate_read_targets(targets,line)
        if formats is None: formats = [()] * len(targets)
        if type(formats) not in (list, tuple) or len(formats) != len(targets):
            raise KarelRuntimeError('READ requires one format list per scalar destination', line)
        formats = [read_formats(target.spec, item, line) for target, item in zip(targets, formats)]
        metadata = dict(line=line, targets=[dict(type=ref.spec[0], type_spec=ref.spec) for ref in targets])
        if self._source_settings.get('default_io_device')=='CRT/KB': metadata['device']='CRT/KB'
        for target, item in zip(metadata['targets'], formats):
            if item: target['format_specifiers'] = item
        if line_breaks: metadata['line_breaks'] = list(line_breaks)
        request = dict(deepcopy(metadata), adapter_outcome='missing_adapter')
        self.read_requests.append(request)
        if self._read is None:
            raise KarelRuntimeError('READ requires an explicit Program(read=...) input callback', line)
        request['adapter_outcome'] = 'callback_started'
        adapter=self._read
        text_checkpoint=adapter._checkpoint() if input_cohorts and type(adapter) is TextInput else None
        try:
            response = adapter(deepcopy(metadata))
        except Exception as exc:
            if text_checkpoint is not None:adapter._restore(text_checkpoint)
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
                _validate_read_value(target,value,line)
            values=_prepare_read_values(targets,values,line)
        except Exception:
            if text_checkpoint is not None:adapter._restore(text_checkpoint)
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
        if self._source_settings.get('default_io_device')=='CRT/KB': request['device']='CRT/KB'
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
            return _write_file_now(self, file, pieces, line)
        total = 0
        for piece in pieces:
            total += len(ascii_string(piece, line))
            if total > 254:
                raise KarelRuntimeError('WRITE combined output is limited to 254 characters', line)
        self.write_string(''.join(pieces), line)

    def write_groups(self,groups,line=None,*,file=None):
        """Publish one rendered scalar batch with aggregate items expanded."""
        return self.write_items(_write_group_pieces(groups,line),line,file=file)

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
        if self.execution.motion is not None:self.execution.motion.poll(self,line)

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
        bank=self.execution.group_locks;scope=None
        if _pythonic() and bank is not None:
            # FROM declarations create forwarding frames. The defining source
            # routine applies its own module policy when that frame is entered.
            interfaces=getattr(getattr(self,'program',None),'routine_interfaces',{})
            external=interfaces.get(routine,{}).get('external') if routine else None
            if not external:scope=bank.enter_scope(self,line)
        self.call_depth += 1
        self.local_frames.append((declarations, values))
        self._timer_frames.append(self.local_frames[-1])
        self._group_scope_frames.append((bank,scope))
        task_root(self)._task_frames.append((self,routine))
        try:
            if self.execution.diagnostics is not None:
                self.execution.diagnostics.observe(self);self.execution.diagnostics.record(self,'CALL',line)
        except BaseException:
            release_frame_timers(self,self.local_frames[-1])
            self.call_depth-=1;self.local_frames.pop();self._timer_frames.pop();self._group_scope_frames.pop()
            task_root(self)._task_frames.pop()
            if bank is not None:bank.leave_scope(scope)
            raise

    def leave_routine(self):
        frame=self.local_frames[-1];bank,scope=self._group_scope_frames[-1]
        try:
            if self.execution.diagnostics is not None:self.execution.diagnostics.record(self,'RTN_FRM_RTN',task_root(self)._task_line or None)
        finally:
            if self.execution.motion is not None:self.execution.motion.release_frame(self,frame)
            release_frame_timers(self,frame)
            for number,handler in list(self._handlers.items()):
                if handler.get('local_frame') is frame: self._handlers.pop(number,None)
            self.call_depth -= 1
            self.local_frames.pop();self._timer_frames.pop();self._group_scope_frames.pop()
            task_root(self)._task_frames.pop()
            if bank is not None:bank.leave_scope(scope)

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

    def predefined_file(self,name,line=None):
        return self.execution.predefined_file(self,name,line)

    def predefined_file_reference(self,name,line=None):
        handle=self.predefined_file(name,line)
        return Reference(('FILE',),{'value':handle},'value')

    def default_file(self,direction,line=None,*,required=False):
        if direction not in ('READ','WRITE'):raise KarelRuntimeError('Default FILE direction must be READ or WRITE',line)
        name=('INPUT' if direction=='READ' else 'OUTPUT') if self._source_settings.get('default_io_device')=='CRT/KB' else 'TPDISPLAY'
        return self.execution.predefined_file(self,name,line,required=required)

    def optional_file_read(self,handle,targets,line=None,**options):
        return self.read_items(targets,line,**options) if handle is None else self.file_read(handle,targets,line,**options)

    def file_read(self,handle,targets,line=None,**options):
        from .extended import file_read
        return file_read(self,handle,targets,line,**options)

    def file_open(self,handle,mode,name,line=None):
        if any(handle is item for item in self.execution._predefined_values.values()):raise KarelRuntimeError('Predefined FILE bindings cannot be reopened; reset with close_predefined_files',line)
        name=ascii_string(name,line)
        pipe_attributes=handle.pipe_wait is not None or handle.pipe_overflow is not None
        if pipe_attributes and not name.upper().startswith('PIP:'):
            raise KarelRuntimeError('Pipe FILE attributes require an explicitly configured plain FilePipes endpoint',line)
        from .serial_io import serial_address
        if serial_address(name):return self.execution.require('serial_streams',line).open_for(self,handle,mode,name,line)
        if name.upper().startswith('KB:') or name.upper().startswith('WD:') and '/' in name:return self.execution.require('keyboard',line).open_for(self,handle,mode,name,line)
        if name.upper().startswith('WD:'):return self.execution.require('pendant',line).open_for(self,handle,mode,name,line)
        if message_address(name):return self.execution.require('messaging',line).open_for(self,handle,mode,name,line)
        if name.upper().startswith('PIP:'):
            try:key=communication_pipe_name(name)
            except ValueError as exc:raise KarelRuntimeError(str(exc),line) from exc
            banks=[bank for bank in (self.execution.acquisition,self.execution.file_pipes) if bank is not None and key in bank.files]
            if len(banks)!=1:raise KarelRuntimeError('PIP FILE requires one explicitly configured acquisition or file_pipes entry',line)
            if pipe_attributes and type(banks[0]) is not FilePipes:
                raise KarelRuntimeError('Pipe FILE attributes require plain FilePipes, not acquisition pipes',line)
            bank=banks[0]
            if type(bank) is Acquisition and _pythonic():
                def check():
                    self.tick(line)
                    if self.execution.acquisition is not bank:
                        raise KarelRuntimeError('DAQ service changed during snapshot preparation',line)
                return bank.open_for(self,handle,mode,key,line,check=check)
            return bank.open_for(self,handle,mode,key,line)
        files = self.execution.require('files', line)
        if type(files) is DirectoryFiles and _pythonic():
            return files.open(handle, mode, name, line, check=lambda: self.tick(line))
        files.open(handle, mode, name, line)

    def file_close(self,handle,line=None):
        handle.require_open(line)
        owner = handle.owner
        if type(owner) is DirectoryFiles and _pythonic():
            return owner.close(handle, line, check=lambda: self.tick(line))
        owner.close(handle, line)

    def external_call(self,program,name,arguments,result_spec,line=None):
        callback=self.execution.externals.get((program.upper(),name.upper()))
        if callback is None: raise KarelRuntimeError('External routine is not explicitly linked: '+program+'.'+name,line)
        try:
            linked=getattr(callback,'_karel_link',False)
            if linked:result=callback.invoke(self,arguments,line)
            elif type(callback) is _ExternalValueCase and _pythonic():
                result=callback.select(arguments,check=lambda:self.tick(line))
            else:result=callback(*arguments)
            if inspect.isgenerator(result): result=yield from result
        except KarelAbort as exc:
            self._aborted=True; self._abort_line=exc.line; raise
        except (KarelPause,KarelStop): raise
        except Exception as exc: raise KarelRuntimeError('External routine failed: '+str(exc),line) from exc
        if self._aborted: raise KarelAbort(self._abort_line)
        check=None if linked else lambda:self.tick(line)
        if _pythonic() and type(result) is dict and set(result)=={'result','outputs'}:
            return external_reply_result(result_spec,result,arguments,line,check=check)
        if result_spec is None:
            if result is not None: raise KarelRuntimeError('External procedure must return None',line)
            return
        if _pythonic() and (collection_type(result_spec) or collection_array_type(result_spec)):
            return external_collection_result(result_spec,result,line,check=check)
        if _pythonic() and type(result) is dict:return external_data_result(result_spec,result,line,check=check)
        return array_result(result_spec,result,line) if result_spec[0]=='ARRAY' else checked(result_spec,result,line)


def optional_file_piece(handle,kind,value,formats,line=None):
    return format_write_item(kind,value,formats,line) if handle is None else file_piece(handle,kind,value,formats,line)


def _write_group_pieces(groups,line=None):
    if not _pythonic() or type(groups) not in (list,tuple):raise KarelRuntimeError('WRITE requires captured item groups',line)
    pieces=[]
    for group in groups:
        if type(group) not in (list,tuple) or not group:raise KarelRuntimeError('WRITE groups require rendered scalar items',line)
        if len(pieces)+len(group)>1024:raise KarelRuntimeError('WRITE requires 1..1024 expanded scalar items including CR',line)
        pieces.extend(group)
    return pieces


class _FileWritePayload:
    """Rendered scalar fields whose byte count is known before assembly."""

    def __init__(self, pieces, line=None):
        if type(pieces) not in (list, tuple) or not 1 <= len(pieces) <= 1024:
            raise KarelRuntimeError('WRITE requires 1..1024 rendered items', line)
        self.pieces = []
        self.size = 0
        for piece in pieces:
            if type(piece) is str:
                if not piece.isascii():
                    raise KarelRuntimeError('FILE WRITE text requires ASCII', line)
                self.size += len(piece)
            elif type(piece) is bytes:
                self.size += len(piece)
            else:
                # Direct State callers may supply a contiguous bytes-like field.
                try:
                    piece = memoryview(piece)
                except (TypeError, ValueError) as exc:
                    raise KarelRuntimeError('FILE WRITE requires rendered text or bytes', line) from exc
                if not piece.c_contiguous:
                    raise KarelRuntimeError('FILE WRITE byte fields must be contiguous', line)
                self.size += piece.nbytes
            self.pieces.append(piece)

    def render(self, state, handle, line, verify):
        from .fileops import charge_file_bytes

        def charge():
            state.tick(line)
            verify()

        charge_file_bytes(self.size, charge)
        verify()
        data = b''.join(piece.encode('ascii') if type(piece) is str else piece for piece in self.pieces)
        return data if handle.binary else data.replace(b'\n', bytes((handle.eol,)))


def _file_write_binding(handle, line):
    owner = handle.owner
    if type(owner) in (KeyboardInput, PendantDisplay):
        return (owner._handles.get(handle),)
    files = getattr(owner, 'files', None)
    binding = (files, files.get(handle.name) if files is not None else None)
    if type(owner) is SerialStreams:
        row = owner._active(handle, line)
        return (*binding, owner._open.get(id(handle)), row, row['output'])
    if type(owner) is Messaging:
        row = owner.connected(handle, line)
        return (*binding, row, row['output'], row['_connection'])
    return binding


def _write_file_now(state, handle, pieces, line):
    handle.require_open(line)
    payload = _FileWritePayload(pieces, line)
    owner, position = handle.owner, handle.position
    identity = _file_identity(handle)
    operations = (handle._read_operation, handle._write_operation)
    binding = _file_write_binding(handle, line)

    def verify():
        if (_file_identity(handle) != identity or handle.position != position
                or handle._read_operation is not operations[0]
                or handle._write_operation is not operations[1]
                or any(current is not original for current, original
                       in zip(_file_write_binding(handle, line), binding))):
            raise KarelRuntimeError('FILE WRITE destination or cursor changed during preparation', line)

    data = payload.render(state, handle, line, verify)
    if type(owner) is DirectoryFiles and _pythonic():
        return owner.write(handle, data, line, check=lambda: state.tick(line))
    owner.write(handle, data, line)


class _FileWriteCancelled(GeneratorExit):
    """Internal unwind of one WRITE without publishing its captured bytes."""


def check_file_write(handle,line=None):
    operation=handle._write_operation
    if operation is None:return
    if (type(operation) is not dict or set(operation)!={'identity','position','cancelled','state','root'}
            or type(operation['state']) is not State or task_root(operation['state']) is not operation['root']
            or type(operation['cancelled']) is not bool or _file_identity(handle)!=operation['identity']
            or handle.position!=operation['position'] or type(handle.owner) not in (SerialStreams,Messaging)):
        raise KarelRuntimeError('Pending FILE WRITE identity or cursor changed',line)
    owner = handle.owner
    if type(owner) is Messaging:
        owner.validate_pending(handle, operation['state'], 'WRITE', line)
    else:
        record = owner._writes.get(id(handle))
        if (type(record) is not tuple or len(record) != 9 or type(record[8]) is not tuple
                or len(record[8]) != 5 or record[0] is not operation['state']
                or record[2] != operation['position'] or record[8][2] is not operation['root']):
            raise KarelRuntimeError('Serial pending WRITE registration changed', line)
        owner.validate_write(handle, record, line)
    if operation['cancelled']:raise _FileWriteCancelled()


def cooperative_write_items(state,pieces,line=None,*,file=None):
    """Retain rendered bytes across an explicitly enabled TX wait."""
    if file is None:
        return state.write_items(pieces, line)
    file.require_open(line)
    owner = file.owner
    if type(owner) is SerialStreams:
        waiting = owner._active(file, line)['wait_output']
    elif type(owner) is Messaging:
        waiting = owner.connected(file, line)['wait_output']
    else:
        waiting = False
    if not waiting:
        return state.write_items(pieces, line, file=file)
    if file._read_operation is not None or file._write_operation is not None:
        raise KarelRuntimeError('FILE already has pending I/O',line)
    payload = _FileWritePayload(pieces, line)
    operation=dict(identity=_file_identity(file),position=file.position,cancelled=False,state=state,root=task_root(state))
    file._write_operation=operation
    try:
        return (yield from owner.write_items(state, file, payload, line))
    except _FileWriteCancelled:
        file.status=6
    finally:
        if file._write_operation is operation:file._write_operation=None


def cooperative_write_groups(state,groups,line=None,*,file=None):
    return (yield from cooperative_write_items(state,_write_group_pieces(groups,line),line,file=file))


def cooperative_optional_file_read(state,handle,targets,line=None,**options):
    if handle is None:return state.read_items(targets,line,**options)
    return (yield from cooperative_file_read(state,handle,targets,line,**options))


def _dispatch_file_read(state,handle,targets,line=None,*,line_breaks=(),formats=None):
    """Retain captured FILE targets while an explicit input service waits."""
    handle.require_open(line)
    if type(handle.owner) is KeyboardInput:
        return (yield from handle.owner.file_read(state,handle,targets,line,line_breaks=line_breaks,formats=formats))
    if type(handle.owner) is FilePipes and (handle.pipe_wait is not None or handle.pipe_overflow is not None):
        return (yield from handle.owner.pipe_read(state,handle,targets,line,line_breaks=line_breaks,formats=formats))
    if type(handle.owner) in (SerialStreams, Messaging):
        return (yield from handle.owner.read_items(state,handle,targets,line,line_breaks=line_breaks,formats=formats))
    return state.file_read(handle,targets,line,line_breaks=line_breaks,formats=formats)


class _FileReadCancelled(GeneratorExit):
    """Internal unwind of one READ, without stopping its source task."""


def _file_identity(handle):
    return (handle.owner,handle.name,handle.logical_name,handle.mode,handle.binary,
        handle.reverse,handle.field,handle.eol,handle.xml,handle.passall,
        handle.noecho,handle.interactive,handle.pipe_wait,handle.pipe_overflow)


def _validate_file_read(handle,operation,line=None):
    if (type(operation) is not dict or set(operation)!={'identity','position','cancelled','state'}
            or type(operation['cancelled']) is not bool
            or _file_identity(handle)!=operation['identity'] or handle.position!=operation['position']):
        raise KarelRuntimeError('Pending FILE READ identity or cursor changed',line)
    owner=handle.owner;state=operation['state']
    if type(owner) is SerialStreams:
        pending=owner._pending.get(id(handle));registration=owner._open.get(id(handle))
        if (type(pending) is not tuple or len(pending)!=3 or pending[0] is not state
                or pending[1] is not registration or pending[2]!=operation['position']):
            raise KarelRuntimeError('Serial pending READ registration changed',line)
    if type(owner) is Messaging:
        owner.validate_pending(handle, state, 'READ', line)
    if type(owner) is FilePipes and (handle.pipe_wait is not None or handle.pipe_overflow is not None):
        owner.validate_pending_read(handle,state,line)
    if type(owner) is KeyboardInput and not any(job.get('handle') is handle and job['state'] is state for job in owner._active.values()):
        raise KarelRuntimeError('Keyboard pending READ registration changed',line)


def check_file_read(handle,line=None):
    """Check cancellation only after validating the captured operation identity."""
    operation=handle._read_operation
    if operation is None:return
    _validate_file_read(handle,operation,line)
    if operation['cancelled']:raise _FileReadCancelled()


def cancel_file(state,handle,line=None):
    """Mark one explicit cooperative READ or WRITE for checked cancellation."""
    if type(handle) is not FileHandle:raise KarelRuntimeError('CANCEL FILE requires an ordinary FILE handle',line)
    handle.require_open(line);owner=handle.owner
    if type(owner) is KeyboardInput:
        registered=handle in owner._handles
    else:registered=any(item is handle for item in getattr(owner,'handles',()))
    if not registered:raise KarelRuntimeError('CANCEL FILE requires its original live FILE registration',line)
    if handle._read_operation is not None and handle._write_operation is not None:
        raise KarelRuntimeError('FILE has overlapping pending operations',line)
    if handle._write_operation is not None:
        try:check_file_write(handle,line)
        except _FileWriteCancelled:pass
        handle._write_operation['cancelled']=True;handle.status=6;return
    operation=handle._read_operation
    if operation is not None:
        # A repeated request is idempotent, including before a paused reader resumes.
        _validate_file_read(handle,operation,line)
        operation['cancelled']=True;handle.status=6;return
    if type(owner) is KeyboardInput:return owner.cancel_read_kb(handle,line)
    direct=(type(owner) is SerialStreams and id(handle) in owner._pending
        or type(owner) is FilePipes and id(handle) in owner._reads
        or type(owner) is Messaging and id(handle) in owner._pending
        or type(owner) is SerialStreams and id(handle) in owner._writes)
    if direct:raise KarelRuntimeError('CANCEL FILE requires a cooperative typed READ/WRITE, not a direct host operation',line)
    handle.status=0


def cooperative_file_read(state,handle,targets,line=None,*,line_breaks=(),formats=None):
    """Register a captured FILE READ and unwind cancellation without publication."""
    handle.require_open(line)
    if handle._read_operation is not None:raise KarelRuntimeError('FILE already has a pending READ',line)
    if handle._write_operation is not None:raise KarelRuntimeError('FILE already has a pending WRITE',line)
    operation=dict(identity=_file_identity(handle),position=handle.position,cancelled=False,state=state)
    handle._read_operation=operation
    try:
        return (yield from _dispatch_file_read(state,handle,targets,line,line_breaks=line_breaks,formats=formats))
    except _FileReadCancelled:
        handle.status=6
    finally:
        if handle._read_operation is operation:handle._read_operation=None


from .extended import (ExecutionContext, StringRegisters, PositionRegisters, PortBank, RegisterComments, CallParameters, ProgramCatalog, ProgramAttributes, PROGRAM_CONSTANTS, PeerBanks, PEER_UNAVAILABLE,
                       SerialPorts,SERIAL_CONSTANTS,XML_CONSTANTS,
                       VariableStore, variable_value, variable_reference, MemoryFiles, FileHandle, PathValue, QueueValue, RobotContext, RobotState, file_piece,
                        TaskRegistry, KarelPause, KarelStop, update_timers, timer_clock, connect_timer, disconnect_timer, release_frame_timers, finish_timers,
                        define_condition, condition_control, checkpoint, cooperative_test, pause_execution,abort_execution,
                       run_cooperative, resume_cooperative, stop_cooperative)
from .storage import DirectoryFiles,directory_files_options,directory_files_from_args
from .devices import DeviceFiles,DEVICE_CONSTANTS,DEVICE_INFO
from .programs import GroupLocks
from .acquisition import Acquisition,DAQ_CONSTANTS
from .variable_archives import VariableArchives
from .archives import ARCHIVE_CONSTANTS
from .remote_messages import RemoteMessages
from .pc_exchange import PcExchange
from .communications import Messaging,FilePipes,message_address,pipe_name as communication_pipe_name,COMMUNICATION_CONSTANTS
from .teach import TeachPrograms,TPE_CONSTANTS
from .clocks import CalendarClock
from .configtext import ConfigTextFormats, CONFIG_TEXT_GROUP_MISSING
from .pulses import pulse_execution
from .kinematics import SerialRobotModel
from .scheduling import (TaskScheduler,EventBank,event_condition,edge_condition,lifecycle_condition,
                         signal_event,delay_execution,control_task,condition_scope,TASK_CONSTANTS,
                         configure_task,TASK_DIRECTIVES,TASK_FLAG_DIRECTIVES,TASK_MASKS,
                         SOURCE_DIRECTIVES,SOURCE_FLAG_DIRECTIVES,SOURCE_DIRECTIVE_RANGES,
                         TASK_SETTING_RANGES,valid_task_setting)
from .control import (SemaphoreBank,ErrorHistory,error_condition,handler_action,cooperative_service,
                      runtime_failure,powerup_cooperative,task_root,request_task_control,ERROR_SEVERITIES)
from .diagnostics import DiagnosticLog,DIAGNOSTIC_CONSTANTS
from .kcl import KclCommands
from .pendant import PendantDisplay,PENDANT_CONSTANTS
from .dictionaries import TextDictionaries,DICTIONARY_CONSTANTS
from .dynamic_display import DynamicDisplays,DYNAMIC_DISPLAY_CALLS
from .keyboard import KeyboardInput,KEYBOARD_CONSTANTS,KEYBOARD_CALLS
from .table_controls import TableControls,TABLE_CONSTANTS,TABLE_CALLS
from .forms import FormControls,FORM_CALLS
from .controller import ControllerServices,CONTROLLER_CALLS
from .vision import VisionServices,VISION_CALLS
from .source_translations import SourceTranslations
from .record_schemas import record_schema_kind,convert_record_schema,kinematic_record_kind,prepare_kinematic_record
from .serial_io import SerialStreams
from .position_input import (PositionReadField as _PositionReadField,capture as _capture_position_read,
                             validate_field as _validate_position_read_field,
                             validate_targets as _validate_position_read_targets,prepare_values as _prepare_position_read_values)
from .motion import (MotionRequests,operand as motion_operand,path_operand as motion_path_operand,
                     path_node_operand as motion_path_node_operand,setting as motion_setting,selector as motion_selector,
                     SETTINGS as MOTION_SETTINGS,KINDS as MOTION_KINDS,
                     SETTING_CONSTANTS as MOTION_SETTING_CONSTANTS)
