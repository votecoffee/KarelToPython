"""Classify child statements that can be followed to a task boundary."""

from dataclasses import dataclass

from .compiler_language import INTEGRAL_TYPES
from .input_robot_values import POSE_CONSTRUCTORS
from .input_value_conversions import SCALARS, array_dimensions
from .teach import TPE_NAMES


SHARED_TEACH_CALLS = TPE_NAMES | {'GET_ATTR_PRG', 'SET_ATTR_PRG', 'LOAD_STATUS'}
STRUCTURED_LOOPS = frozenset(('for', 'while', 'repeat'))
SCALAR_BINARY_OPERATORS = frozenset(('+', '-', '*', '/', 'DIV', 'MOD', '=', '<>', '<', '<=', '>', '>=', 'AND', 'OR'))


@dataclass
class TaskHandoff:
    request: dict
    waiter: dict | None = None
    assignments: tuple = ()
    selector: dict | None = None
    reached: bool = False


def _ungroup(node):
    while node is not None and node['kind'] == 'group' and len(node['args']) == 1:
        node = node['args'][0]
    return node


def task_scalar_operand(node):
    """Unwrap expressions that read one scalar or contain a literal."""
    node = _ungroup(node)
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


def explicit_pause(node):
    return node['kind'] == 'task_control' and node['args'] == ['PAUSE']


def _isolated(plan, linked_plans, tick):
    name = plan['program']
    if plan.get('imports') != []:
        return False
    for other in linked_plans.values():
        tick()
        imports, routines = other.get('imports'), other.get('routines')
        if (other.get('status') != 'available' or type(imports) is not list or type(routines) is not dict
                or any(owner.upper() == name for _, owner, _ in imports)
                or any((routine['external'] or '').upper() == name for routine in routines.values())):
            return False
    return True


def resolve_routine(plan, linked_plans, name, interface):
    """Resolve only an implementation with the pinned caller signature."""
    owner = interface['external']
    if not owner:
        return plan, interface
    target = (linked_plans or {}).get(owner.upper(), {})
    routine = target.get('routines', {}).get(name)
    if (target.get('status') != 'available' or routine is None or routine['external'] or
            routine['result'] != interface['result'] or
            [spec for _, spec in routine['parameters']] != [spec for _, spec in interface['parameters']]):
        return None, None
    return target, routine


def _direct_routine_call(plan, operand, *, procedure=False):
    call = _ungroup(operand)
    routine = plan['routines'].get(call['value']) if call is not None and call['kind'] == 'call' else None
    if routine is None:
        return None
    result = routine['result']
    valid = result is None if procedure else result and result[0] in SCALARS
    return call if valid else None


def scalar_task_operator(node):
    kind, operator = node['kind'], node['value']
    return (kind == 'group' or kind == 'unary' and operator in ('+', '-', 'NOT')
            or kind == 'binary' and operator in SCALAR_BINARY_OPERATORS)


def select_case_labels(node):
    for index, (_, labels, _) in enumerate(node['args'][1]):
        for label in labels:
            yield index, label


def _expression_routines(plan, expression, tick, *, procedure=False):
    if expression is None:
        return
    tick()
    if scalar_task_operator(expression) or expression['kind'] in ('field', 'index'):
        for operand in expression['args']:
            yield from _expression_routines(plan, operand, tick, procedure=procedure)
    else:
        call = _direct_routine_call(plan, expression, procedure=procedure)
        if call is not None:
            yield call
            for mode, operand in zip(call.get('passing', ()), call['args']):
                if mode in ('value', 'reference'):
                    yield from _expression_routines(plan, operand, tick)


def _routine_calls(plan, node, tick):
    kind, args = node['kind'], node['args']
    if kind == 'call':
        yield from _expression_routines(plan, args[0], tick, procedure=True)
    elif kind == 'select':
        yield from _expression_routines(plan, args[0], tick)
        for _, label in select_case_labels(node):
            yield from _expression_routines(plan, label, tick)
    elif kind in ('assign', 'for'):
        for operand in args[:3] if kind == 'for' else args:
            yield from _expression_routines(plan, operand, tick)
    elif kind in ('if', 'return', 'while', 'repeat') and args:
        yield from _expression_routines(plan, args[0], tick)


def _branches(node):
    if node['kind'] == 'if':
        return (node['body'], node['alternate'])
    if node['kind'] == 'select':
        return (*(body for _, _, body in node['args'][1]), node['alternate'])
    if node['kind'] in STRUCTURED_LOOPS:
        return (node['body'],)
    return ()


def structured_child(plan, linked_plans, tick):
    """Find an isolated child with a pause within or alongside structured flow."""
    pending = [(plan, iter(plan['body']), False)]
    found_control = found_pause = False
    visited_routines = set()
    while pending:
        owner, statements, nested = pending[-1]
        node = next(statements, None)
        if node is None:
            pending.pop()
            continue
        tick()
        pause = explicit_pause(node)
        found_pause = found_pause or pause
        found_control = found_control or node['kind'] in STRUCTURED_LOOPS
        pending.extend((owner, iter(body), True) for body in _branches(node) if body)
        for call in _routine_calls(owner, node, tick):
            name = call['value']
            target, routine = resolve_routine(owner, linked_plans, name, owner['routines'][name])
            if routine is not None:
                found_control = True
                key = target['program'], name
                if key not in visited_routines:
                    visited_routines.add(key)
                    pending.append((target, iter(routine['body']), True))
        if (nested and pause) or (found_control and found_pause):
            return _SegmentRules(plan, tick, structured=True) if _isolated(plan, linked_plans, tick) else None
    return None


class _SegmentRules:
    def __init__(self, plan, tick, *, structured=False, routine=None):
        self.plan = plan
        self.tick = tick
        self.structured = structured
        self.types = plan['types'] if routine is None else plan['types'] | routine['types']
        self.constants = plan['constants'] if routine is None else plan['constants'] | routine['constants']
        self.routine_scopes = {}
        self.uses_teach = False
        self.uses_pose = False

    def routine_scope(self, plan, name):
        key = plan['program'], name
        if key not in self.routine_scopes:
            self.routine_scopes[key] = _SegmentRules(plan, self.tick, structured=True,
                                                     routine=plan['routines'][name])
        return self.routine_scopes[key]

    def reference_schema(self, node, *, staged=False):
        self.tick()
        kind = node['kind']
        if kind == 'name':
            return self.types.get(node['value'])
        if staged and kind == 'group':
            return self.reference_schema(node['args'][0], staged=True)
        if not self.structured or kind not in ('field', 'index'):
            return None
        receiver, *indices = node['args']
        schema = self.reference_schema(receiver, staged=staged)
        if schema is None:
            return None
        if kind == 'field':
            return dict(schema[2]).get(node['value']) if schema[0] == 'STRUCTURE' else None
        if schema[0] != 'ARRAY':
            return None
        dimensions, element = array_dimensions(schema)
        if not 0 < len(indices) <= len(dimensions):
            return None
        if not staged and not all(self.operand(index) for index in indices):
            return None
        remaining = dimensions[len(indices):]
        return ['ARRAY', remaining, element] if remaining else element

    def operand(self, node):
        self.tick()
        kind = node['kind']
        if kind == 'name':
            variable = node['value']
            schema = self.types.get(variable)
            if schema is None:
                return variable in self.constants
            if schema[0] in ('CONFIG', 'POSITION', 'XYZWPR', 'XYZWPREXT', 'JOINTPOS'):
                self.uses_pose = True
                return True
            return schema[0] in SCALARS
        if kind in ('literal', 'real_literal', 'predefined', 'write_cr'):
            return True
        if kind == 'call':
            return self.call(node)
        if kind in ('field', 'index'):
            schema = self.reference_schema(node)
            if schema and schema[0] in SCALARS:
                return True
            self.uses_pose = True
        return kind in ('group', 'unary', 'binary', 'write_item', 'field', 'index', 'repeat_eval') and all(
            self.operand(arg) for arg in node['args'])

    def call(self, node):
        routine = node['value']
        if routine in self.plan['routines']:
            return False
        if routine in SHARED_TEACH_CALLS:
            self.uses_teach = True
        elif routine in POSE_CONSTRUCTORS or routine == 'CNV_STR_CONF':
            self.uses_pose = True
        elif routine != 'UNINIT':
            return False
        return all(self.operand(arg) for arg in node['args'])

    def procedure_call(self, node):
        return self.checked_routine_call(_direct_routine_call(self.plan, node, procedure=True))

    def scalar_routine_call(self, operand):
        return self.checked_routine_call(_direct_routine_call(self.plan, operand))

    def checked_routine_call(self, call):
        if call is None:
            return None
        actuals = call['args']
        modes = call.get('passing', ())
        formals = self.plan['routines'][call['value']]['parameters']
        if len(actuals) != len(modes) or len(modes) != len(formals):
            return None
        return call if all(mode in ('value', 'reference') and spec[0] in SCALARS
                           for mode, (_, spec) in zip(modes, formals)) else None

    def branch(self, node):
        args = node['args']
        return self.operand(args[0]) and (
            node['kind'] == 'if' or all(self.operand(label) for _, label in select_case_labels(node)))

    def loop(self, node):
        if node['kind'] != 'for':
            return True
        schema = self.reference_schema(node['args'][0], staged=True)
        return bool(schema and schema[0] in INTEGRAL_TYPES)

    def statement(self, node):
        self.tick()
        kind, args = node['kind'], node['args']
        if kind == 'assign':
            target, value = args
            if target['kind'] == 'name':
                return self.operand(target) and self.operand(value)
            schema = self.reference_schema(target)
            return bool(schema and schema[0] in SCALARS and self.operand(value))
        if kind == 'call':
            return args[0]['kind'] == 'call' and self.call(args[0])
        if kind in ('if', 'select'):
            return self.branch(node) and all(self.statement(row) for body in _branches(node) for row in body)
        return kind in ('write_items', 'signal_event') and all(self.operand(arg) for arg in args)


def bounded_child(plan, linked_plans, tick, *, segment=None):
    """Check an isolated child body or its requested execution segment."""
    if not _isolated(plan, linked_plans, tick):
        return None
    rules = _SegmentRules(plan, tick)
    body = plan['body'] if segment is None else plan['body'][slice(*segment)]
    if not all(rules.statement(node) or explicit_pause(node) for node in body):
        return None
    if rules.uses_teach:
        return 'teach'
    if not rules.uses_pose and (segment is not None or any(explicit_pause(node) for node in body)):
        return 'scalar'
    return None
