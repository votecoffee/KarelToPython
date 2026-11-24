"""Classify child statements that can be followed to a task boundary."""

from dataclasses import dataclass

from .compiler_language import CONSTANT_BUILTINS, INTEGRAL_TYPES, RECORD_TYPES
from .extended import PREDEFINED_FILE_NAMES
from .input_robot_values import POSE_CONSTRUCTORS
from .input_teach_discovery import TEACH_POSITION_GETTERS
from .input_value_conversions import SCALARS, Value, array_dimensions
from .queue_operations import QUEUE_EDIT_INPUTS
from .teach import TPE_NAMES


SHARED_TEACH_CALLS = TPE_NAMES | {'GET_ATTR_PRG', 'SET_ATTR_PRG', 'LOAD_STATUS'}
STRUCTURED_LOOPS = frozenset(('for', 'while', 'repeat'))
SCALAR_BINARY_OPERATORS = frozenset(('+', '-', '*', '/', 'DIV', 'MOD', '=', '<>', '<', '<=', '>', '>=', 'AND', 'OR'))
TASK_DATA_AGGREGATES = frozenset(('ARRAY', 'JOINTPOS', *RECORD_TYPES))
TASK_ROUTINE_VALUES = frozenset(SCALARS) | TASK_DATA_AGGREGATES
PATH_TASK_EDITS = frozenset(('APPEND_NODE', 'INSERT_NODE', 'DELETE_NODE'))
QUEUE_TASK_EDITS = frozenset(QUEUE_EDIT_INPUTS) | {'INIT_QUEUE', 'COPY_QUEUE'}
FILE_TASK_QUERIES = frozenset(('GET_FILE_POS', 'BYTES_LEFT', 'IO_STATUS'))
FILE_TASK_PROCEDURES = frozenset(('SET_FILE_ATR', 'SET_FILE_POS', 'BYTES_AHEAD', 'CLR_IO_STAT'))
_REPEAT_SAMPLE = object()


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


def _direct_routine_call(plan, operand, *, procedure=False, results=TASK_ROUTINE_VALUES):
    call = _ungroup(operand)
    routine = plan['routines'].get(call['value']) if call is not None and call['kind'] == 'call' else None
    if routine is None:
        return None
    result = routine['result']
    valid = result is None if procedure else result and result[0] in results
    return call if valid else None


def scalar_task_operator(node):
    kind, operator = node['kind'], node['value']
    return (kind == 'group' or kind == 'unary' and operator in ('+', '-', 'NOT')
            or kind == 'binary' and operator in SCALAR_BINARY_OPERATORS)


def select_case_labels(node):
    for index, (_, labels, _) in enumerate(node['args'][1]):
        for label in labels:
            yield index, label


def aggregate_task_write(node):
    return node['kind'] == 'write_items' and any(
        item.get('write_type') in TASK_DATA_AGGREGATES or 'write_collection' in item for item in node['args'])


def repeat_capture_parts(predicate, tick):
    """Split captures in evaluation order, including captures nested in others."""
    captures = []

    def split(node):
        if not isinstance(node, dict):
            return node
        tick()
        operands = [split(operand) for operand in node['args']]
        if node['kind'] == 'repeat_eval':
            slot = len(captures)
            captures.append(dict(node, args=operands))
            return dict(node, kind=_REPEAT_SAMPLE, value=slot, args=[])
        if any(before is not after for before, after in zip(node['args'], operands)):
            return dict(node, args=operands)
        return node

    live = split(predicate)
    return tuple(captures), live


def bind_repeat_samples(node, samples, tick):
    """Make a test or capture operand refer to its already sampled values."""
    if not isinstance(node, dict):
        return node
    tick()
    if node['kind'] is _REPEAT_SAMPLE:
        return dict(node, kind='wait_sample', value=samples[node['value']])
    operands = [bind_repeat_samples(operand, samples, tick) for operand in node['args']]
    if any(before is not after for before, after in zip(node['args'], operands)):
        return dict(node, args=operands)
    return node


def task_resource_storage(spec):
    _, terminal = array_dimensions(spec)
    return bool(terminal and terminal[0] in ('FILE', 'QUEUE_TYPE', 'PATH'))


def queue_task_storage(spec):
    return array_dimensions(spec)[1] == ['QUEUE_TYPE']


def path_task_storage(spec):
    _, terminal = array_dimensions(spec)
    return bool(terminal and terminal[0] == 'PATH')


def _expression_routines(plan, expression, tick, *, procedure=False):
    if expression is None:
        return
    tick()
    kind = expression['kind']
    builtin = (not procedure and kind == 'call' and expression['value'] not in plan['routines']
               and (expression['value'] in ('ARRAY_LEN', 'PATH_LEN', 'UNINIT')
                    or expression['value'] in CONSTANT_BUILTINS or expression['value'] in FILE_TASK_QUERIES))
    if builtin or scalar_task_operator(expression) or kind in ('field', 'index', 'path_io_range', 'repeat_eval'):
        for operand in expression['args']:
            yield from _expression_routines(plan, operand, tick, procedure=procedure)
    else:
        call = _direct_routine_call(plan, expression, procedure=procedure)
        if call is not None:
            yield call
            for mode, operand in zip(call.get('passing', ()), call['args']):
                if mode in ('value', 'reference'):
                    yield from _expression_routines(plan, operand, tick)


def queue_task_call(plan, node):
    if node['kind'] != 'call' or node['value'] not in QUEUE_TASK_EDITS or node['value'] in plan['routines']:
        return False
    signature = node.get('signature', ())
    return len(signature) == len(node['args']) and all(spec[0] in ('i', 'r', 'o') for spec in signature)


def path_copy_task_call(plan, node):
    return (node['kind'] == 'call' and node['value'] == 'COPY_PATH'
            and 'COPY_PATH' not in plan['routines'] and len(node['args']) in (5, 6))


def file_task_procedure(plan, node):
    if node['kind'] != 'call' or node['value'] not in FILE_TASK_PROCEDURES or node['value'] in plan['routines']:
        return False
    arity, signature = len(node['args']), node.get('signature', ())
    # The compiler retains the full signature when SET_FILE_ATR omits its value.
    return len(signature) == arity or node['value'] == 'SET_FILE_ATR' and arity == 2 and len(signature) == 3


def _routine_calls(plan, node, tick):
    kind, args = node['kind'], node['args']
    if kind == 'call':
        call = args[0]
        if queue_task_call(plan, call) or file_task_procedure(plan, call) or path_copy_task_call(plan, call):
            for operand in call['args']:
                yield from _expression_routines(plan, operand, tick)
        else:
            yield from _expression_routines(plan, call, tick, procedure=True)
    elif kind in ('file_read', 'file_write'):
        yield from _expression_routines(plan, args[0], tick)
        yield from _routine_calls(plan, args[1], tick)
    elif kind in ('file_open', 'file_close'):
        for operand in args:
            yield from _expression_routines(plan, operand, tick)
    elif kind == 'write_items':
        for item in args:
            for operand in item['args']:
                yield from _expression_routines(plan, operand, tick)
    elif kind == 'read':
        for item in args:
            operands = item['args'] if item['kind'] == 'read_item' else (item,)
            for operand in operands:
                yield from _expression_routines(plan, operand, tick)
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


def _path_storage(types, node):
    while node['kind'] in ('group', 'field', 'index'):
        node = node['args'][0]
    return node['kind'] == 'name' and path_task_storage(types.get(node['value']))


def structured_child(plan, linked_plans, tick, *, predefined_files=()):
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
        found_control = (found_control or node['kind'] in STRUCTURED_LOOPS
                         or aggregate_task_write(node) or node.get('data_assignment') is True
                         or node['kind'] == 'assign' and _path_storage(owner['types'], node['args'][0])
                         or node['kind'] == 'call' and (
                             queue_task_call(owner, node['args'][0]) or file_task_procedure(owner, node['args'][0])
                             or path_copy_task_call(owner, node['args'][0]))
                         or node['kind'] in ('file_open', 'file_read', 'file_write', 'file_close', 'read')
                         or node['kind'] == 'write_items' and owner.get('default_write_file') in predefined_files)
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
            return (_SegmentRules(plan, tick, structured=True, predefined_files=predefined_files)
                    if _isolated(plan, linked_plans, tick) else None)
    return None


class _SegmentRules:
    def __init__(self, plan, tick, *, structured=False, routine=None, predefined_files=()):
        self.plan = plan
        self.tick = tick
        self.structured = structured
        self.predefined_files = predefined_files
        self.types = plan['types'] if routine is None else plan['types'] | routine['types']
        self.constants = plan['constants'] if routine is None else plan['constants'] | routine['constants']
        self.routine_scopes = {}
        self.uses_teach = False
        self.uses_pose = False

    def routine_scope(self, plan, name):
        key = plan['program'], name
        if key not in self.routine_scopes:
            self.routine_scopes[key] = _SegmentRules(plan, self.tick, structured=True,
                                                     routine=plan['routines'][name],
                                                     predefined_files=self.predefined_files)
        return self.routine_scopes[key]

    def predefined_file_alias(self, node):
        node = _ungroup(node)
        if node['kind'] != 'name':
            return None
        name = node['value']
        if (name in PREDEFINED_FILE_NAMES and name not in self.types and name not in self.constants
                and name not in self.plan['routines']):
            return name
        return None

    def reference_schema(self, node, *, staged=False):
        self.tick()
        kind = node['kind']
        if kind == 'name':
            if staged and self.predefined_file_alias(node) is not None:
                return ['FILE']
            return self.types.get(node['value'])
        if staged and kind == 'group':
            return self.reference_schema(node['args'][0], staged=True)
        if not self.structured or kind not in ('field', 'index'):
            return None
        receiver, *indices = node['args']
        schema = self.reference_schema(receiver, staged=staged)
        if schema is None:
            return None
        if schema[0] == 'PATH':
            if kind == 'field':
                return dict(schema[2][2]).get(node['value']) if schema[2] else None
            if len(indices) != 1 or not (staged or self.operand(indices[0])):
                return None
            return schema[2] if node.get('static_zero_subscript') else schema[1] or self.plan.get('default_path_node')
        if kind == 'field':
            return dict(schema[2]).get(node['value']) if schema[0] == 'STRUCTURE' else None
        if schema[0] != 'ARRAY':
            return None
        dimensions, element = array_dimensions(schema)
        if not indices or not staged and not all(self.operand(index) for index in indices):
            return None
        if len(indices) > len(dimensions):
            if element[0] == 'PATH' and len(indices) == len(dimensions) + 1:
                return element[2] if node.get('static_zero_subscript') else element[1] or self.plan.get('default_path_node')
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
        if kind == 'wait_sample':
            return isinstance(node['value'], Value)
        if kind == 'call':
            return self.call(node)
        if kind in ('field', 'index'):
            if self.path_storage(node):
                return False
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

    def storage_operand(self, node):
        kind, args = node['kind'], node['args']
        if kind == 'name':
            return node['value'] in self.types
        return (kind in ('group', 'field', 'index') and self.storage_operand(args[0])
                and all(self.operand(arg) for arg in args[1:]))

    def path_storage(self, node):
        return _path_storage(self.types, node)

    def path_edit_call(self, node):
        name = node['value']
        if name in self.plan['routines'] or name not in PATH_TASK_EDITS:
            return False
        args, signature = node['args'], node.get('signature', ())
        return len(args) == len(signature) and all(
            self.storage_operand(arg) or spec[0] == 'i' and self.operand(arg)
            for arg, spec in zip(args, signature)
        )

    def scalar_routine_call(self, operand):
        return self.checked_routine_call(_direct_routine_call(self.plan, operand, results=SCALARS))

    def data_routine_call(self, operand):
        return self.checked_routine_call(_direct_routine_call(self.plan, operand, results=TASK_DATA_AGGREGATES))

    def checked_routine_call(self, call):
        if call is None:
            return None
        actuals = call['args']
        modes = call.get('passing', ())
        formals = self.plan['routines'][call['value']]['parameters']
        if len(actuals) != len(modes) or len(modes) != len(formals):
            return None
        for mode, (_, spec) in zip(modes, formals):
            _, terminal = array_dimensions(spec)
            if (mode not in ('value', 'reference')
                    or terminal == ['FILE'] and mode != 'reference'
                    or spec[0] not in TASK_ROUTINE_VALUES and not task_resource_storage(spec)):
                return None
        return call

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
            if node.get('data_assignment') is True:
                # A direct TP getter can record its input without materializing the pose.
                call = _ungroup(value)
                result = TEACH_POSITION_GETTERS.get(call['value']) if call['kind'] == 'call' else None
                return (target['kind'] == 'name' and result is not None
                        and self.types.get(target['value']) == list(result)
                        and 'data_assignment_conversion' not in node and self.call(call))
            if self.path_storage(target):
                return False
            if target['kind'] == 'name':
                return self.operand(target) and self.operand(value)
            schema = self.reference_schema(target)
            return bool(schema and schema[0] in SCALARS and self.operand(value))
        if kind == 'call':
            return args[0]['kind'] == 'call' and self.call(args[0])
        if kind in ('if', 'select'):
            return self.branch(node) and all(self.statement(row) for body in _branches(node) for row in body)
        if (aggregate_task_write(node)
                or kind == 'write_items' and self.plan.get('default_write_file') in self.predefined_files):
            return False
        return kind in ('write_items', 'signal_event') and all(self.operand(arg) for arg in args)


def bounded_child(plan, linked_plans, tick, *, segment=None, predefined_files=()):
    """Check an isolated child body or its requested execution segment."""
    if not _isolated(plan, linked_plans, tick):
        return None
    rules = _SegmentRules(plan, tick, predefined_files=predefined_files)
    body = plan['body'] if segment is None else plan['body'][slice(*segment)]
    if not all(rules.statement(node) or explicit_pause(node) for node in body):
        return None
    if rules.uses_teach:
        return 'teach'
    if not rules.uses_pose and (segment is not None or any(explicit_pause(node) for node in body)):
        return 'scalar'
    return None
