"""Check writable robot frame, tool, and pose operands without emitting Python."""
from dataclasses import dataclass

from . import extended as ex
from . import runtime as rt
from .schema_conversion import CARTESIAN_TYPES
from .syntax import Expr


_ALLOWED_POSE_PATHS = {
    (), ('LOCATION',), *(('LOCATION', axis) for axis in ('X', 'Y', 'Z')),
    ('CONFIG_DATA',), *(('CONFIG_DATA', name) for name, _ in rt.record_fields(('CONFIG',))),
    *((axis,) for axis in ex.SYSTEM_POSE_AXES),
}


@dataclass(frozen=True)
class SystemPoseTarget:
    pose: Expr
    path: tuple


def check_system_selection_target(target, *, error):
    if target.kind != 'system_selection':
        error('E_SYSTEM_SELECTION_TARGET', 'Active frame/tool assignment requires one group selector and no descendant fields',
              target.token)


def check_system_pose_target(target, *, error):
    root = target
    fields = []
    while root.kind in ('field', 'group'):
        if root.kind == 'field':
            fields.append(root.value)
        root = root.args[0]
    path = tuple(reversed(fields))
    if root.kind != 'system_pose' or path not in _ALLOWED_POSE_PATHS:
        error('E_SYSTEM_POSE_TARGET', 'System pose writes require a whole pose or a LOCATION, CONFIG_DATA or external-axis field',
              target.token)
    return SystemPoseTarget(root, path)


def check_system_pose_value(target, expected, actual, token, *, mode, compatible, error):
    if not target.path:
        if mode == 'pythonic' and actual[0] == 'JOINTPOS':
            return 'kinematic'
        if actual[0] not in CARTESIAN_TYPES:
            error('E_TYPE', 'System pose assignment requires a Cartesian pose or Pythonic JOINTPOS value', token)
    elif mode == 'pythonic' and rt.real_integral_kind(expected, actual):
        return 'real_integral'
    elif not compatible(expected, actual):
        error('E_TYPE', f'System pose field requires {expected}', token)
    return None
