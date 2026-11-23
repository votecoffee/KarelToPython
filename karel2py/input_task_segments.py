"""Classify child bodies that can be followed to a top-level task boundary."""

from dataclasses import dataclass

from .input_robot_values import POSE_CONSTRUCTORS
from .input_value_conversions import SCALARS
from .teach import TPE_NAMES


SHARED_TEACH_CALLS = TPE_NAMES | {'GET_ATTR_PRG', 'SET_ATTR_PRG', 'LOAD_STATUS'}


@dataclass
class TaskHandoff:
    request: dict
    waiter: dict | None = None
    assignments: tuple = ()
    selector: dict | None = None
    reached: bool = False


def task_scalar_operand(node):
    """Unwrap expressions that read one scalar or contain a literal."""
    while node['kind'] == 'group' and len(node['args']) == 1:
        node = node['args'][0]
    return node if node['kind'] in ('name', 'literal', 'real_literal', 'predefined') else None


def task_handoff_window(body, index, *, terminal_entry, tick):
    """Find a pause wait reached through straight-line scalar assignments."""
    node = body[index]
    args = node['args']
    if node['kind'] == 'call' and args[0]['kind'] == 'call' and args[0]['value'] in ('RUN_TASK', 'CONT_TASK'):
        request = args[0]
    elif node['kind'] == 'task_control' and len(args) == 2 and args[0] in ('CONTINUE', 'RESUME', 'UNPAUSE'):
        request = node
    else:
        return None

    if index == len(body) - 1:
        return TaskHandoff(request) if terminal_entry else None
    assignments = []
    for position in range(index + 1, len(body)):
        tick()
        step = body[position]
        if step['kind'] == 'wait' and len(step['args']) == 1:
            condition = step['args'][0]
            if condition['kind'] != 'wait_pause' or condition['args'][0] is None:
                return None
            selector = task_scalar_operand(condition['args'][0])
            return TaskHandoff(request, step, tuple(assignments), selector) if selector is not None else None
        if step['kind'] != 'assign' or step.get('geometry_assignment') or step.get('path_assignment_type'):
            return None
        target, source = step['args']
        operand = task_scalar_operand(source)
        if target['kind'] != 'name' or operand is None:
            return None
        assignments.append((target, operand))
    return None


def bounded_child(plan, linked_plans, tick, *, segment=None):
    """Check an isolated child body or its requested execution segment."""
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

    body = plan['body'] if segment is None else plan['body'][slice(*segment)]
    if not all(safe(node, top=True) for node in body):
        return None
    if uses_teach:
        return 'teach'
    if not uses_pose and (segment is not None or any(node['kind'] == 'task_control' for node in body)):
        return 'scalar'
    return None
