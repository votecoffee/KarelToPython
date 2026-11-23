"""Classify child bodies that can be followed to a top-level task boundary."""

from .input_robot_values import POSE_CONSTRUCTORS
from .input_value_conversions import SCALARS
from .teach import TPE_NAMES


SHARED_TEACH_CALLS = TPE_NAMES | {'GET_ATTR_PRG', 'SET_ATTR_PRG', 'LOAD_STATUS'}


def bounded_child(plan, linked_plans, tick):
    """Return the kind of operations in an isolated, bounded child body."""
    name = plan['program']
    if plan.get('imports') != []:
        return None
    for other in linked_plans.values():
        tick()
        imports, routines = other.get('imports'), other.get('routines')
        if (other.get('status') != 'available' or type(imports) is not list or type(routines) is not dict
                or any(owner.upper() == name for _, owner, _ in imports)
                or any((routine['external'] or '').upper() == name for routine in routines.values())):
            return None

    uses_teach = False
    uses_pose = False

    def operand(node):
        nonlocal uses_pose
        tick()
        kind = node['kind']
        if kind == 'name':
            variable = node['value']
            schema = plan['types'].get(variable)
            if schema is None:
                return variable in plan['constants']
            if schema[0] in ('CONFIG', 'POSITION', 'XYZWPR', 'XYZWPREXT', 'JOINTPOS'):
                uses_pose = True
                return True
            return schema[0] in SCALARS
        if kind in ('literal', 'real_literal', 'predefined', 'write_cr'):
            return True
        if kind == 'call':
            return call(node)
        if kind in ('field', 'index'):
            uses_pose = True
        return kind in ('group', 'unary', 'binary', 'write_item', 'field', 'index') and all(
            operand(arg) for arg in node['args'])

    def call(node):
        nonlocal uses_teach, uses_pose
        routine = node['value']
        if routine in plan['routines']:
            return False
        if routine in SHARED_TEACH_CALLS:
            uses_teach = True
        elif routine in POSE_CONSTRUCTORS or routine == 'CNV_STR_CONF':
            uses_pose = True
        else:
            return False
        return all(operand(arg) for arg in node['args'])

    def safe(node, *, top=False):
        tick()
        kind, args = node['kind'], node['args']
        if kind == 'task_control':
            return top and args == ['PAUSE']
        if kind == 'assign':
            target, value = args
            return target['kind'] == 'name' and operand(target) and operand(value)
        if kind == 'call':
            return args[0]['kind'] == 'call' and call(args[0])
        if kind == 'if':
            return operand(args[0]) and all(safe(row) for row in (*node['body'], *node['alternate']))
        return kind in ('write_items', 'signal_event') and all(operand(arg) for arg in args)

    if not all(safe(node, top=True) for node in plan['body']):
        return None
    if uses_teach:
        return 'teach'
    if not uses_pose and any(node['kind'] == 'task_control' for node in plan['body']):
        return 'scalar'
    return None
