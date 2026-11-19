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


def check_routine_call(expr, routine, *, mode, has_routine_call, error):
    """Check call shape and return source arguments paired with their formals."""
    expected, supplied = len(routine.parameters), len(expr.args)
    if supplied != expected:
        error('E_ARGUMENTS', f'{expr.value} expects {expected} arguments, received {supplied}', expr.token)
    if mode == 'strict' and supplied > 1 and any(has_routine_call(arg) for arg in expr.args):
        error('E_EVALUATION_ORDER', 'Multiple arguments containing routine calls need evaluation-order validation', expr.token)
    return zip(expr.args, routine.parameters)


@dataclass(frozen=True)
class RoutineArgumentPlan:
    expected_schema: tuple
    bound_schema: tuple
    conversion: str | None
    by_reference: bool
    guarded_array: bool
    guarded_string: bool

    @property
    def bounded_string_value(self):
        return (not self.by_reference and self.expected_schema[0] == self.bound_schema[0] == 'STRING'
                and self.expected_schema[1] is not None)


def plan_routine_argument(expected, actual, *, mode, reference):
    """Resolve the passing mode, bound schema and any runtime forwarding guards."""
    guarded_array = mode == 'pythonic' and reference and array_formal_forward_match(expected, actual)
    guarded_string = (mode == 'pythonic' and reference and expected[0] == actual[0] == 'STRING'
                      and expected[1] is not None and actual[1] is None)
    conversion = routine_argument_conversion(expected, actual, mode=mode, guarded_array=guarded_array)
    return RoutineArgumentPlan(
        expected_schema=expected,
        bound_schema=expected if conversion else actual,
        conversion=conversion,
        by_reference=reference and conversion is None,
        guarded_array=guarded_array,
        guarded_string=guarded_string,
    )


def validate_routine_argument(plan, routine_name, token, *, mode, active_counter, writable_formal, error):
    """Check parameter compatibility and scoped restrictions in source diagnostic order."""
    expected, actual = plan.expected_schema, plan.bound_schema
    if (not rt.parameter_accepts(expected, actual)
            and not (plan.bounded_string_value or plan.guarded_array or plan.guarded_string)):
        error('E_TYPE', f'{routine_name} parameter expects {expected[0]}, found {actual[0]}', token)
    if plan.by_reference:
        if active_counter and (mode == 'strict' or writable_formal):
            error('E_FOR_COUNTER', 'An active FOR counter cannot be passed to a potentially writable formal; '
                  'use parentheses for a value argument', token)
    elif expected[0] == 'ARRAY' and mode == 'strict':
        error('E_ARRAY_VALUE', 'Whole ARRAY arguments cannot be passed by value', token)
    elif expected[0] == 'STRING' and mode != 'pythonic' and writable_formal:
        error('E_STRING_VALUE', 'STRING value arguments require a read-only formal; '
              'this parameter may be written through assignments or nested calls', token)


@dataclass(frozen=True)
class CheckedServiceSignature:
    name: str
    parameters: tuple
    explicit_node_flag: bool

    def check_operand(self, index, spec, token, *, node_schema, error):
        """Validate a typed operand and carry the first PATH's NODEDATA schema."""
        _, kind = self.parameters[index]
        if not ex.matches(spec, kind):
            error('E_TYPE', f'{self.name} expects {kind}, found {spec[0]}', token)
        if index == 0 and self.name in ex.OPTIONAL_PATH_NODE:
            node_schema = spec[1] or rt.PREDEFINED_STRUCTURES['STD_PTH_NODE']
        if kind == 'PATH_NODE' and spec != node_schema and not self.explicit_node_flag:
            error('E_TYPE', f'{self.name} node input must match the declared NODEDATA', token)
        return node_schema


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
    return CheckedServiceSignature(name, signature, node_flag and count == maximum)
