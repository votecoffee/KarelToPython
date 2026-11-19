"""Select an assignment conversion and its destination schema before emission."""
from dataclasses import dataclass

from . import runtime as rt
from .schema_conversion import pythonic_schema_conversion


@dataclass(frozen=True)
class ArrayReceiverPlan:
    record_schema: bool
    kinematic_record: bool
    kinematic_array: bool

    @property
    def needs_source_schema(self):
        return self.record_schema or self.kinematic_record

    @property
    def needs_geometry(self):
        return self.kinematic_array or self.kinematic_record


@dataclass(frozen=True)
class AssignmentPlan:
    target_schema: tuple
    source_schema: tuple
    conversion: str | None = None
    array_receiver: ArrayReceiverPlan | None = None


def _array_receiver(expected, actual, *, compatible):
    record = bool(rt.record_schema_kind(expected, actual))
    kinematic_record = bool(rt.kinematic_record_kind(expected, actual))
    kinematic_array = bool(rt.kinematic_array_kind(expected, actual))
    if (compatible(expected, actual) or rt.array_schema_compatible(expected, actual)
            or rt.numeric_array_kind(expected, actual) or rt.positional_array_kind(expected, actual)
            or record or kinematic_record or kinematic_array):
        return ArrayReceiverPlan(record, kinematic_record, kinematic_array)
    return None


def check_assignment(expected, actual, token, *, mode, formal_receiver, compatible, error):
    """Check the source and select a declared or concrete receiver conversion."""
    if mode == 'pythonic':
        if formal_receiver and expected[0] == 'ARRAY' and rt.array_identity(expected) is None:
            receiver = _array_receiver(expected, actual, compatible=compatible)
            if receiver is not None:
                return AssignmentPlan(expected, actual, array_receiver=receiver)
        conversion = pythonic_schema_conversion(expected, actual, array_conversion=rt.array_schema_kind)
        if conversion is not None:
            return AssignmentPlan(expected, actual, conversion=conversion)
    if not compatible(expected, actual):
        error('E_TYPE', f'Cannot assign {actual} to {expected}', token)
    return AssignmentPlan(expected, actual)


def check_prefix_assignment(expected, actual, token, *, compatible, error):
    receiver = _array_receiver(expected, actual, compatible=compatible) if actual[0] == 'ARRAY' else None
    if receiver is None:
        error('E_TYPE', f'Cannot assign {actual} to ARRAY prefix {expected}', token)
    return receiver


def collection_array_capture(expected, actual, *, formal_receiver):
    if rt.collection_array_source_accepts(expected, actual):
        return 'copy'
    if formal_receiver and None in rt.array_shape(expected):
        return 'receiver_conversion'
    return 'schema_conversion'


def array_result_routine(expr, schema, *, mode):
    if mode == 'pythonic':
        while expr.kind == 'group':
            expr = expr.args[0]
    return expr.value if expr.kind == 'call' and schema[0] == 'ARRAY' else None
