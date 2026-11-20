"""Check operand types and PATH selectors for offline motion requests."""
from . import runtime as rt
from .schema_conversion import CARTESIAN_TYPES
from .syntax import Expr


MOTION_OPERANDS = {
    'MOVE TO': ('target', 'via'),
    'MOVE NEAR': ('target', 'distance'),
    'MOVE AWAY': ('distance',),
    'MOVE ABOUT': ('vector', 'angle'),
    'MOVE AXIS': ('axis', 'distance'),
    'MOVE RELATIVE': ('offset',),
    'MOVE ALONG': ('path', 'start', 'end'),
}


def split_motion_path(operand, *, access_type, error):
    """Separate a PATH receiver from its optional node bounds."""
    if operand.kind not in ('index', 'motion_range'):
        return operand, None, None
    base, *indexes = operand.args
    end = indexes.pop() if operand.kind == 'motion_range' else None
    spec = access_type(base)
    if rt.collection_array_node_type(spec, len(indexes)) is not None:
        path = Expr('index', operand.token, args=[base, *indexes[:-1]])
        return path, indexes[-1], end
    if spec[0] == 'PATH' and len(indexes) == 1:
        return base, indexes[0], end
    if end is not None:
        error('E_MOTION_TYPE', 'MOVE ALONG range requires a PATH and one starting node', operand.token)
    return operand, None, None


def check_motion_pose_setting(schema, token, *, error):
    if schema[0] not in CARTESIAN_TYPES:
        error('E_MOTION_SETTING', 'Motion WITH frame/tool requires a Cartesian pose', token)


def check_motion_operand(operation, name, schema, token, *, error):
    if name == 'path':
        allowed = ('PATH',)
    elif name == 'vector':
        allowed = ('VECTOR',)
    elif name == 'offset':
        allowed = ('VECTOR', *CARTESIAN_TYPES)
    elif operation == 'MOVE NEAR' or name == 'via':
        allowed = CARTESIAN_TYPES
    else:
        allowed = (*CARTESIAN_TYPES, 'JOINTPOS')
    if schema[0] not in allowed:
        error('E_MOTION_TYPE', f'Unsupported {operation} {name} type: {schema[0]}', token)
