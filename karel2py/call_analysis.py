"""Routine argument and service signature checks without Python emission."""
from dataclasses import dataclass

from . import extended as ex
from . import runtime as rt
from .compiler_language import INTEGRAL_TYPES, NARROW_TYPES


CARTESIAN_TYPES = ('POSITION', 'XYZWPR', 'XYZWPREXT')
PYTHONIC_CONVERSIONS = (
    ('real_integral', rt.real_integral_kind),
    ('config_word', rt.config_word_kind),
    ('numeric_array', rt.numeric_array_kind),
    ('positional_array', rt.positional_array_kind),
    ('kinematic_array', rt.kinematic_array_kind),
    ('kinematic_record', rt.kinematic_record_kind),
    ('record_schema', rt.record_schema_kind),
)


def array_formal_forward_match(expected, actual):
    """Defer unknown ARRAY sizes while retaining the routine entry check."""
    if expected[0] != 'ARRAY' or actual[0] != 'ARRAY' or rt.array_identity(expected) is not None:
        return False
    if expected[2][0] == 'ARRAY':
        first, second = rt.array_shape(expected), rt.array_shape(actual)
        elements = rt.parameter_accepts(expected[2], actual[2])
    else:
        first, second = rt.array_dimensions(expected), rt.array_dimensions(actual)
        elements = rt.parameter_accepts(expected[2], rt.array_leaf_spec(actual))
    return (
        elements and len(first) == len(second)
        and any(wanted is not None and supplied is None for wanted, supplied in zip(first, second))
        and all(wanted is None or supplied is None or wanted == supplied for wanted, supplied in zip(first, second))
    )


def routine_argument_conversion(expected, actual, *, mode, guarded_array=False):
    """Return the selected value conversion, or None if no conversion applies."""
    target_kind, source_kind = expected[0], actual[0]
    if mode == 'pythonic':
        for conversion, matches in PYTHONIC_CONVERSIONS:
            if matches(expected, actual):
                return conversion
        if (not guarded_array and rt.array_schema_compatible(expected, actual)
                and not rt.parameter_accepts(expected, actual)):
            return 'array_schema'
        if target_kind == source_kind == 'JOINTPOS' and expected != actual:
            return 'joint_width'
        if (target_kind == 'JOINTPOS' and source_kind in CARTESIAN_TYPES
                or source_kind == 'JOINTPOS' and target_kind in CARTESIAN_TYPES):
            return 'kinematic'
        if expected != actual and target_kind in CARTESIAN_TYPES and source_kind in CARTESIAN_TYPES:
            return 'cartesian'
        if target_kind in NARROW_TYPES and source_kind in INTEGRAL_TYPES and actual != expected:
            return 'integral_narrow'
    if target_kind in ('INTEGER', 'REAL') and source_kind in NARROW_TYPES:
        return 'narrow_promotion'
    if target_kind == 'REAL' and source_kind == 'INTEGER':
        return 'integer_to_real'
    return None


@dataclass(frozen=True)
class CheckedServiceSignature:
    parameters: tuple
    explicit_node_flag: bool


def check_service_signature(name, count, token, *, mode, error):
    """Resolve arity, optional operands, and argument roles before lowering."""
    if name == 'BYNAME':
        error('E_BYNAME_CONTEXT', 'BYNAME is permitted only as a direct user routine argument', token)
    declared = ex.PROCEDURES.get(name, ex.FUNCTIONS.get(name, ((), None))[0])
    minimum = len(declared) - (name in ex.OPTIONAL_LAST or name in ex.OPTIONAL_GROUP or name in ex.OPTIONAL_PATH_NODE)
    default_masks = mode == 'pythonic' and name in ('CURPOS', 'CURJPOS') and count == 0
    node_flag = mode == 'pythonic' and name in ex.OPTIONAL_PATH_NODE
    maximum = len(declared) + node_flag
    if not default_masks and not minimum <= count <= maximum:
        error('E_ARGUMENTS', f'{name} requires {minimum}..{maximum} arguments', token)
    signature = ex.signature_for(name, count)
    if mode == 'pythonic' and name in ('SET_POS_REG', 'SET_EPOS_REG', 'SET_JPOS_REG'):
        # Register selection determines the model conversion after value capture.
        signature = tuple((passing, 'RANGE_POSITION') if index == 1 else (passing, kind)
                          for index, (passing, kind) in enumerate(signature))
    return CheckedServiceSignature(signature, node_flag and count == maximum)
