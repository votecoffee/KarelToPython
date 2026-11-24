"""Shared schema conversion order for source-language value interfaces."""
from . import runtime as rt


CARTESIAN_TYPES = ('POSITION', 'XYZWPR', 'XYZWPREXT')
MODEL_CONVERSIONS = {'kinematic', 'kinematic_array', 'kinematic_record'}
DATA_AGGREGATE_CONVERTERS = {
    'array_schema': rt.convert_array_schema,
    'numeric_array': rt.convert_numeric_array,
    'positional_array': rt.convert_positional_array,
    'record_schema': rt.convert_record_schema,
    'joint_width': rt.convert_joint_width,
    'cartesian': rt.convert_position,
}
PYTHONIC_CONVERSIONS = (
    ('real_integral', rt.real_integral_kind),
    ('config_word', rt.config_word_kind),
    ('numeric_array', rt.numeric_array_kind),
    ('positional_array', rt.positional_array_kind),
    ('kinematic_array', rt.kinematic_array_kind),
    ('kinematic_record', rt.kinematic_record_kind),
    ('record_schema', rt.record_schema_kind),
)


def pythonic_schema_conversion(expected, actual, *, array_conversion):
    """Select an interface conversion using the caller's ARRAY policy."""
    for conversion, matches in PYTHONIC_CONVERSIONS:
        if matches(expected, actual):
            return conversion
    if array_conversion(expected, actual):
        return 'array_schema'
    target_kind, source_kind = expected[0], actual[0]
    if target_kind == source_kind == 'JOINTPOS' and expected != actual:
        return 'joint_width'
    if (target_kind == 'JOINTPOS' and source_kind in CARTESIAN_TYPES
            or source_kind == 'JOINTPOS' and target_kind in CARTESIAN_TYPES):
        return 'kinematic'
    if expected != actual and target_kind in CARTESIAN_TYPES and source_kind in CARTESIAN_TYPES:
        return 'cartesian'
    return None
