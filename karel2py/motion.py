"""Explicit offline motion requests, detached data and logical hand state.

Nothing in this module computes a trajectory or changes robot feedback. A host
must opt into capture-only execution or supply finite scripted completion responses.
"""
from copy import deepcopy
import json
import re


MOVES = ('MOVE TO', 'MOVE NEAR', 'MOVE AWAY', 'MOVE ABOUT', 'MOVE AXIS',
         'MOVE RELATIVE', 'MOVE ALONG')
CONTROLS = ('HOLD', 'UNHOLD', 'CANCEL')
OPERATIONS = (*MOVES, *CONTROLS, 'OPEN HAND', 'CLOSE HAND', 'RELAX HAND', 'ATTACH', 'RELEASE')
POSES = ('POSITION', 'XYZWPR', 'XYZWPREXT', 'JOINTPOS')
MAX_SEQUENCE = 2147483646
SETTINGS = {'$SPEED':'REAL', '$ROTSPEED':'REAL', '$MOTYPE':'INTEGER',
            '$UFRAME':'POSE', '$UTOOL':'POSE', '$USE_CONFIG':'BOOLEAN',
            '$TERMTYPE':'INTEGER', '$SEGTERMTYPE':'INTEGER', '$ORIENT_TYPE':'INTEGER',
            '$DECELTOL':'INTEGER', '$USEMAXACCEL':'BOOLEAN',
            '$ACCEL_OVRD':'INTEGER', '$ACCU_NUM':'INTEGER', '$SEG_TIME':'INTEGER',
            '$TIME_SHIFT':'INTEGER', '$CONTAXISVEL':'REAL', '$CNSTNT_PATH':'BOOLEAN',
            '$DYN_I_COMP':'BOOLEAN', '$USE_CARTACC':'BOOLEAN', '$USERELACCEL':'BOOLEAN',
            '$USETIMESHFT':'BOOLEAN'}
INTEGER_LIMITS = {'$DECELTOL':(0,99), '$ACCEL_OVRD':(0,500), '$ACCU_NUM':(0,10),
                  '$SEG_TIME':(0,100000), '$TIME_SHIFT':(0,10000)}
REAL_LIMITS = {'$SPEED':(0,None), '$ROTSPEED':(0,None), '$CONTAXISVEL':(-100,100)}
KINDS = {6:'JOINT', 7:'LINEAR', 8:'CIRCULAR'}
TERMINATIONS = {1:'FINE', 2:'COARSE', 3:'NOSETTLE', 4:'NODECEL', 5:'VARDECEL'}
ORIENTATIONS = {1:'RSWORLD', 2:'AESWORLD', 3:'WRISTJOINT'}
ENUM_SETTINGS = {'$MOTYPE':KINDS, '$TERMTYPE':TERMINATIONS,
                 '$SEGTERMTYPE':TERMINATIONS, '$ORIENT_TYPE':ORIENTATIONS}
SETTING_CONSTANTS = {key:{name:number for number,name in values.items()}
                     for key,values in ENUM_SETTINGS.items()}
SETTING_CONSTANTS['$MOTYPE']['STRAIGHT']=7


def rt():
    from . import runtime
    return runtime


def bounded(value, low, high, message):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(message)
    return value


def selector(kind, offset_ms, node, line=None):
    """Freeze one local temporal selector, independently of any motion service."""
    try:
        if type(kind) is not str or kind not in ('AT', 'BEFORE', 'AFTER'):
            raise ValueError('Unknown motion temporal condition')
        bounded(offset_ms, 0, 86400000, 'Motion time offset must be in 0..86400000 ms')
        if kind == 'AT' and offset_ms != 0:
            raise ValueError('AT NODE cannot contain a time offset')
        if type(node) is not str or node != '*':
            bounded(node, 0, 32767, 'Motion condition node must be in 0..32767 or *')
    except ValueError as error:
        raise rt().KarelRuntimeError(str(error), line) from error
    return dict(kind=kind, node=node, offset_ms=offset_ms)


def node_times(values, duration):
    """Validate caller-supplied arrivals; no path geometry or feedback inference."""
    if type(values) is not dict or not 2 <= len(values) <= 257:
        raise ValueError('Motion node_times requires start and 1..256 destination arrivals')
    result = {}
    for key, value in values.items():
        if type(key) is not str or not re.fullmatch(r'0|[1-9][0-9]{0,4}', key):
            raise ValueError('Motion node keys require canonical nonnegative integers')
        bounded(int(key), 0, 32767, 'Motion node number exceeds 32767')
        result[int(key)] = bounded(value, 0, duration, 'Motion arrival must be within the supplied delay')
    if result.get(0) != 0:
        raise ValueError('Motion node_times must explicitly place NODE[0] at zero')
    ordered = sorted(result)
    if any(result[left] > result[right] for left, right in zip(ordered, ordered[1:])):
        raise ValueError('Motion arrivals must be nondecreasing in node order')
    if result[ordered[-1]] != duration:
        raise ValueError('Last motion arrival must equal the supplied delay')
    return result


def temporal_events(data, execution, operation):
    """Precompute finite exact progress breakpoints and constant-time predicates."""
    conditions = execution.get('conditions', [])
    if 'node_times' not in execution:
        if conditions:
            raise ValueError('AT NODE/TIME conditions require explicit scripted node_times')
        return {}, ()
    times = node_times(execution['node_times'], execution['delay_ms'])
    expected = [0, *range(data['start'], data['end'] + 1)] if operation == 'MOVE ALONG' else [0, 1]
    if sorted(times) != expected:
        raise ValueError('Motion node_times must match the complete selected move range')
    last = expected[-1]
    previous = {node: expected[index-1] for index, node in enumerate(expected) if index}
    events, breakpoints = {}, set(times.values())
    for condition in conditions:
        if type(condition) is not dict or set(condition) != {'kind', 'node', 'offset_ms'}:
            raise ValueError('Malformed motion temporal selector')
        try:
            normalized = selector(condition['kind'], condition['offset_ms'], condition['node'])
        except rt().KarelRuntimeError as error:
            raise ValueError(str(error)) from error
        if normalized != condition:
            raise ValueError('Motion temporal selector is not canonical')
        kind, node, offset = condition['kind'], condition['node'], condition['offset_ms']
        targets = expected[1:] if node == '*' else [node]
        if any(target not in times for target in targets):
            raise ValueError('Temporal condition references a node outside the selected move')
        due = set()
        for target in targets:
            if kind == 'AT':
                due.add(times[target])
            elif kind == 'BEFORE' and target != 0:
                due.add(max(times[previous[target]], times[target] - offset))
            elif kind == 'AFTER' and target != last:
                when = times[target] + offset
                if when <= execution['delay_ms']:
                    due.add(when)
        events[kind, node, offset] = frozenset(due)
        breakpoints.update(due)
    return events, tuple(sorted(breakpoints))


def operand(value, spec, line=None):
    """Validate and freeze each source operand before evaluating the next one."""
    runtime = rt()
    if spec[0] == 'PATH':
        if type(value) is not runtime.PathValue or value.spec != spec:
            raise runtime.KarelRuntimeError('MOVE ALONG requires exact PATH storage', line)
        return value.clone()
    if spec[0] == 'VECTOR':
        runtime.vector_components(value, line)
        value = value.clone()
    elif spec[0] in POSES:
        value = runtime.positional_value(spec, value, line)
        if spec[0] != 'JOINTPOS':
            runtime._frame_parts(value, line)
    elif spec[0] == 'INTEGER':
        return runtime.integer(value, line)
    elif spec[0] == 'REAL':
        return runtime.real(value, line)
    else:
        raise runtime.KarelRuntimeError('Unsupported motion operand', line)
    from .storage import typed_value
    return typed_value(value, spec)


def typed(row, allowed, axes=None):
    """Validate bounded history data without accepting arbitrary type schemas."""
    if type(row) is not dict or set(row) != {'type', 'value'}:
        raise ValueError('Motion position requires typed data')
    spec = row['type']
    if (type(spec) is not list or not spec or type(spec[0]) is not str
            or spec[0] not in allowed):
        raise ValueError('Unsupported motion position type')
    if spec[0] == 'JOINTPOS':
        if len(spec) != 2:
            raise ValueError('Motion joints require a concrete width')
        bounded(spec[1], 1, 9, 'Invalid motion joint width')
        if axes is not None and spec[1] != axes:
            raise ValueError('Motion joint width must match the configured group')
    elif len(spec) != 1:
        raise ValueError('Malformed motion position type')
    from .storage import decode_typed
    runtime = rt()
    with runtime._numeric_scope('pythonic'):
        decoded_spec, value = decode_typed(row)
        canonical = operand(value, decoded_spec)
    if canonical != row:
        raise ValueError('Motion position requires canonical complete data')


def setting(name, value, spec, line=None):
    """Capture one temporary WITH value, without applying an environment."""
    runtime = rt()
    if name in ENUM_SETTINGS:
        value = runtime.integer(value, line);values=ENUM_SETTINGS[name]
        if value not in values:
            raise runtime.KarelRuntimeError('Motion '+name+' requires '+
                '/'.join(values.values())+' ('+'/'.join(map(str,values))+')',line)
        return values[value]
    if name in INTEGER_LIMITS:
        value = runtime.integer(value, line)
        low, high = INTEGER_LIMITS[name]
        if not low <= value <= high:
            raise runtime.KarelRuntimeError('Motion '+name+' requires INTEGER '+str(low)+'..'+str(high), line)
        return value
    if name in REAL_LIMITS:
        value = runtime.real(value, line)
        low, high = REAL_LIMITS[name]
        if value < low or high is not None and value > high:
            raise runtime.KarelRuntimeError('Motion '+name+' outside its supported numeric range', line)
        return value
    if name in SETTINGS and SETTINGS[name] == 'BOOLEAN':
        return runtime.boolean(value, line)
    if name in ('$UFRAME', '$UTOOL') and spec[0] in POSES[:-1]:
        return operand(value, spec, line)
    raise runtime.KarelRuntimeError('Unsupported motion WITH setting', line)


def transition(operation, before):
    """Hold is orthogonal to stopped/active work; cancellation retains the hold."""
    after = dict(before)
    if operation == 'HOLD':
        after['held'] = True
    elif operation == 'UNHOLD':
        after['held'] = False
    elif operation == 'CANCEL' and before['motion'] == 'executing':
        after['motion'] = 'idle'
    return after


class MotionRequests:
    """Finite capture/scripted endpoint. No hardware adapter or implicit replies."""
    def __init__(self, groups, *, hands=None, capture_only=False, responses=None,
                 limit=128, sequence=0, history=None, queue_limit=0, cross_group_settings=False):
        if type(groups) is not dict or not groups or len(groups) > 31:
            raise ValueError('Motion groups require an explicit group:axis-count map')
        self.groups = {}
        for group, axes in groups.items():
            bounded(group, 1, 31, 'Motion group must be in 1..31')
            self.groups[group] = bounded(axes, 1, 9, 'Motion group axis count must be in 1..9')
        if type(capture_only) is not bool:
            raise ValueError('capture_only requires BOOLEAN')
        self.queue_limit = bounded(queue_limit, 0, 127, "Motion queue limit must be in 0..127")
        if type(cross_group_settings) is not bool:
            raise ValueError("cross_group_settings requires BOOLEAN")
        self.cross_group_settings = cross_group_settings
        self.capture_only = capture_only
        self.limit = bounded(limit, 1, 128, 'Motion history limit must be in 1..128')
        self.sequence = bounded(sequence, 0, MAX_SEQUENCE, 'Invalid motion sequence')
        self.hands = {}
        if hands is not None and type(hands) is not dict:
            raise ValueError('Motion hands require an object')
        for hand, value in (hands or {}).items():
            bounded(hand, 1, 2, 'Hand number must be in 1..2')
            if type(value) is not str or value not in ('open', 'closed', 'relaxed'):
                raise ValueError('Invalid logical hand state')
            self.hands[hand] = value
        if responses is None:
            responses = []
        if type(responses) is not list or len(responses) > 4096:
            raise ValueError('Motion responses exceed the finite script limit')
        for row in responses:
            if (type(row) is not dict or not {'operation', 'completed'} <= set(row)
                    or set(row) - {'operation', 'completed', 'delay_ms', 'node_times'}
                    or type(row['operation']) is not str or row['operation'] not in MOVES
                    or type(row['completed']) is not bool):
                raise ValueError('Motion response requires operation and BOOLEAN completed')
            if 'delay_ms' in row:
                bounded(row['delay_ms'], 0, 86400000, 'Motion delay must be in 0..86400000 ms')
            if 'node_times' in row:
                if 'delay_ms' not in row:
                    raise ValueError('Motion node_times requires an explicit delay_ms')
                node_times(row['node_times'], row['delay_ms'])
        if capture_only and responses:
            raise ValueError('Choose capture-only or scripted motion responses')
        self.responses = deepcopy(responses)
        self._released = {}
        self._active = {}
        self._queued = {}
        self._local_actions = {}
        if history is None:
            history = []
        if type(history) is not list or len(history) > self.limit:
            raise ValueError('Motion history exceeds its ring limit')
        previous = 0
        for row in history:
            if (type(row) is not dict or set(row) != {'sequence', 'program', 'source_program',
                    'operation', 'group', 'line', 'nowait', 'outcome', 'data'}):
                raise ValueError('Malformed motion history')
            previous = bounded(row['sequence'], previous + 1, sequence, 'Motion history IDs must increase')
            for key in ('program', 'source_program'):
                if type(row[key]) is not str or not re.fullmatch(r'[A-Z_][A-Z_0-9]{0,253}', row[key]):
                    raise ValueError('Invalid motion request owner')
            bounded(row['line'], 1, MAX_SEQUENCE, 'Invalid motion source line')
            if type(row['operation']) is not str or row['operation'] not in OPERATIONS:
                raise ValueError('Invalid motion operation')
            if type(row['nowait']) is not bool or row['nowait'] and row['operation'] not in MOVES:
                raise ValueError('Invalid motion NOWAIT flag')
            if type(row['outcome']) is not str or row['outcome'] not in ('captured', 'completed', 'rejected', 'cancelled', 'failed'):
                raise ValueError('Invalid motion outcome')
            if row['operation'] not in MOVES and row['outcome'] != 'completed':
                raise ValueError('Logical motion actions require completed history')
            if row['outcome'] in ('cancelled', 'failed') and (type(row['data']) is not dict or 'execution' not in row['data']):
                raise ValueError('Cancelled/failed motion history requires an execution scope')
            try:
                self.validate(row['operation'], row['group'], row['data'])
            except rt().KarelRuntimeError as error:
                raise ValueError(str(error)) from error
            execution = row['data'].get('execution')
            if execution is not None:
                if row['outcome'] in ('captured', 'completed') and execution['elapsed_ms'] != execution['delay_ms']:
                    raise ValueError('Completed motion history requires its full supplied progress')
                if row['outcome'] == 'captured' and execution['delay_ms']:
                    raise ValueError('Capture-only motion cannot claim a delayed completion')
                if row['outcome'] == 'captured' and 'node_times' in execution:
                    raise ValueError('Capture-only motion cannot claim scripted node arrivals')
                if row['outcome'] == 'rejected' and (execution['elapsed_ms'] or execution['triggered']):
                    raise ValueError('Rejected motion cannot contain executed handlers or progress')
                if (any(execution['handlers'][index-1]['kind'] == 'UNTIL' for index in execution['triggered'])
                        and row['outcome'] not in ('cancelled', 'failed')):
                    raise ValueError('A triggered UNTIL must cancel or fail the motion')
        self.history = deepcopy(history)

    def validate(self, operation, group, data):
        if type(group) is not int or group not in self.groups:
            raise ValueError('Motion group is not configured')
        if type(data) is not dict or len(data) > 5:
            raise ValueError('Malformed motion request data')
        expected = {
            'MOVE TO': {'target'}, 'MOVE NEAR': {'target', 'distance'},
            'MOVE AWAY': {'distance'}, 'MOVE ABOUT': {'vector', 'angle'},
            'MOVE AXIS': {'axis', 'distance'}, 'MOVE RELATIVE': {'offset'},
            'MOVE ALONG': {'nodes', 'start', 'end'}, 'ATTACH': {'groups'},
            'RELEASE': {'groups'}, 'OPEN HAND': {'hand'}, 'CLOSE HAND': {'hand'},
            'RELAX HAND': {'hand'},
            **{name:{'groups', 'states'} for name in CONTROLS},
        }[operation]
        optional = ({'settings', 'execution'} if operation in MOVES else set()) | ({'via'} if operation == 'MOVE TO' else set())
        if set(data) - optional != expected:
            raise ValueError('Unexpected motion request fields')
        if 'execution' in data:
            execution = data['execution']
            required = {'delay_ms', 'elapsed_ms', 'handlers', 'triggered'}
            if (type(execution) is not dict or not required <= set(execution)
                    or set(execution) - required - {'node_times', 'conditions'}):
                raise ValueError('Malformed motion execution metadata')
            duration = bounded(execution['delay_ms'], 0, 86400000, 'Invalid motion execution delay')
            bounded(execution['elapsed_ms'], 0, duration, 'Motion progress exceeds its supplied delay')
            handlers, triggered = execution['handlers'], execution['triggered']
            if type(handlers) is not list or len(handlers) > 32:
                raise ValueError('Motion execution supports at most 32 local clauses')
            for handler in handlers:
                if (type(handler) is not dict or set(handler) != {'kind', 'line'}
                        or type(handler['kind']) is not str or handler['kind'] not in ('WHEN', 'UNTIL')):
                    raise ValueError('Malformed local motion clause metadata')
                bounded(handler['line'], 1, MAX_SEQUENCE, 'Invalid local motion clause line')
            if (type(triggered) is not list or len(triggered) > len(handlers)
                    or any(type(index) is not int or not 1 <= index <= len(handlers) for index in triggered)
                    or len(set(triggered)) != len(triggered)):
                raise ValueError('Invalid local motion trigger sequence')
            if 'conditions' in execution and (type(execution['conditions']) is not list
                    or not 1 <= len(execution['conditions']) <= 64):
                raise ValueError('Motion execution supports 1..64 temporal selectors')
        if 'settings' in data:
            rows = data['settings']
            maximum = len(SETTINGS) * (len(self.groups) if self.cross_group_settings else 1)
            if type(rows) is not list or not 1 <= len(rows) <= maximum:
                raise ValueError('Motion WITH requires 1..'+str(maximum)+' supported settings')
            names = set()
            for row in rows:
                if type(row) is not dict or set(row) != {'name', 'group', 'value'}:
                    raise ValueError('Malformed motion WITH setting')
                name = row['name']
                selected_group = row['group']
                if type(selected_group) is not int or selected_group not in self.groups:
                    raise ValueError('Motion WITH group must be configured')
                if not self.cross_group_settings and selected_group != group:
                    raise ValueError('Motion WITH group must match the selected request group')
                if type(name) is not str or name not in SETTINGS or (selected_group, name) in names:
                    raise ValueError('Unknown or duplicate motion WITH setting for its group')
                names.add((selected_group, name))
                value = row['value']
                if name in ENUM_SETTINGS:
                    if type(value) is not str or value not in ENUM_SETTINGS[name].values():
                        raise ValueError('Invalid motion WITH '+name+' choice')
                    if name=='$MOTYPE':
                        if value == 'CIRCULAR' and (operation != 'MOVE TO' or 'via' not in data):
                            raise ValueError('CIRCULAR motion requires MOVE TO with VIA')
                        if value != 'CIRCULAR' and 'via' in data:
                            raise ValueError('VIA conflicts with the explicit motion type')
                elif name in ('$UFRAME', '$UTOOL'):
                    typed(value, POSES[:-1])
                elif name in INTEGER_LIMITS:
                    low, high = INTEGER_LIMITS[name]
                    bounded(value, low, high, name+' requires INTEGER '+str(low)+'..'+str(high))
                elif SETTINGS[name] == 'BOOLEAN':
                    if type(value) is not bool:
                        raise ValueError(name+' requires BOOLEAN')
                else:
                    runtime = rt()
                    with runtime._numeric_scope('pythonic'):
                        number = runtime.real(value)
                        low, high = REAL_LIMITS[name]
                        if number < low or high is not None and number > high:
                            raise ValueError(name+' outside its supported numeric range')
        for key in ('target', 'via', 'offset', 'vector'):
            if key in data:
                allowed = ('VECTOR',) if key == 'vector' else ('VECTOR', *POSES[:-1]) if key == 'offset' else POSES[:-1] if operation == 'MOVE NEAR' or key == 'via' else POSES
                typed(data[key], allowed, self.groups[group])
        for key in ('distance', 'angle'):
            if key in data:
                runtime = rt()
                with runtime._numeric_scope('pythonic'):
                    runtime.real(data[key])
        if 'axis' in data:
            bounded(data['axis'], 1, self.groups[group], 'Motion axis outside the configured group')
        if 'hand' in data:
            if type(data['hand']) is not int or data['hand'] not in self.hands:
                raise ValueError('Motion hand is not explicitly configured')
        if 'groups' in data:
            groups = data['groups']
            if (type(groups) is not list or len(groups) > 31
                    or any(type(g) is not int or g not in self.groups for g in groups)
                    or groups != sorted(set(groups))):
                raise ValueError('Invalid motion ownership selection')
        if 'states' in data:
            states = data['states']
            if type(states) is not list or len(states) != len(data['groups']):
                raise ValueError('Motion control state count disagrees with groups')
            for group_number, row in zip(data['groups'], states):
                if (type(row) is not dict or set(row) != {'group', 'before', 'after'}
                        or type(row['group']) is not int or row['group'] != group_number):
                    raise ValueError('Malformed motion control state')
                for state in (row['before'], row['after']):
                    if (type(state) is not dict or set(state) != {'motion', 'held'}
                            or type(state['motion']) is not str or state['motion'] not in ('idle', 'executing', 'stopped')
                            or type(state['held']) is not bool):
                        raise ValueError('Invalid motion control label or hold flag')
                if row['after'] != transition(operation, row['before']):
                    raise ValueError('Motion control history contains an invalid transition')
        if 'nodes' in data:
            nodes = data['nodes']
            if type(nodes) is not list or not 1 <= len(nodes) <= 256:
                raise ValueError('MOVE ALONG requires 1..256 selected nodes')
            start = bounded(data['start'], 1, 32767, 'Invalid PATH start')
            end = bounded(data['end'], start, 32767, 'Invalid PATH end')
            if end - start + 1 != len(nodes):
                raise ValueError('Motion PATH range disagrees with nodes')
            for node in nodes:
                typed(node, POSES, self.groups[group])
        events, breakpoints = temporal_events(data, data['execution'], operation) if 'execution' in data else ({}, ())
        if len(json.dumps(data, allow_nan=False, separators=(',', ':')).encode('ascii')) > 65536:
            raise ValueError('Motion request exceeds 64 KiB')
        return events, breakpoints

    @staticmethod
    def clause_metadata(clauses,line=None):
        if (type(clauses) not in (tuple,list) or len(clauses)>32
                or any(type(row) not in (tuple,list) or len(row)!=4
                       or row[0] not in ('WHEN','UNTIL') or not callable(row[1]) or not callable(row[2])
                       or type(row[3]) is not int or not 1<=row[3]<=MAX_SEQUENCE for row in clauses)):
            raise rt().KarelRuntimeError('Motion local clauses require bounded callable WHEN/UNTIL descriptors',line)
        return [dict(kind=kind,line=location) for kind,_,_,location in clauses]

    @staticmethod
    def _validate_owner_names(root, source):
        for name in (root.program_name, source.program_name):
            if type(name) is not str or not re.fullmatch(r'[A-Z_][A-Z_0-9]{0,253}', name):
                raise ValueError('Motion request owner requires an ASCII source identifier within 254 characters')

    def _control_data(self, locks, operation, groups):
        if (type(groups) is not list or len(groups) > 31
                or any(type(group) is not int or group not in self.groups for group in groups)
                or len(set(groups)) != len(groups)):
            raise ValueError('Motion control requires distinct configured group numbers')
        groups = sorted(groups)
        states = []
        for group in groups:
            before = dict(motion=locks.motion.get(group, 'idle'), held=group in locks.held)
            states.append(dict(group=group, before=before, after=transition(operation, before)))
        return dict(groups=groups, states=states)

    def _record_request(self, root, source, operation, group, line, nowait, outcome, data):
        self.sequence += 1
        request = dict(sequence=self.sequence, program=root.program_name,
                       source_program=source.program_name, operation=operation, group=group,
                       line=line, nowait=nowait, outcome=outcome, data=deepcopy(data))
        self.history.append(request)
        del self.history[:-self.limit]
        return request

    def _apply_control(self, locks, operation, data):
        for row in data['states']:
            group = row['group']
            scope = self._active.get(group)
            if operation == 'CANCEL' and scope is not None and row['before']['motion'] != 'stopped':
                scope['cancelled'] = True
            locks.set_motion(group, row['after']['motion'])
            if row['after']['held']:
                locks.held.add(group)
            else:
                locks.held.discard(group)
            if scope is not None and scope.get('background'):
                if scope['cancelled'] and not scope.get('scanning'):
                    self.finish_scope(scope, 'cancelled')
                else:
                    scope['blocked'] = self.background_blocked(scope)

    def prepare_task_controls(self, source, roots, operation, line):
        """Check every live task's owned motion before accepting the command batch."""
        runtime = rt()
        locks = source.execution.group_locks
        rows = []
        try:
            if any(group not in locks.groups for group in self.groups):
                raise ValueError('Motion groups must exist in the logical GroupLocks bank')
            for root in roots:
                if root.execution.motion is not self or root.execution.group_locks is not locks:
                    raise ValueError('Task motion control requires shared MotionRequests and GroupLocks')
                groups = [group for group, owner in locks.owners.items() if owner is root]
                if not groups:
                    continue
                if root in self._released:
                    raise ValueError('Task motion control requires attached logical group ownership')
                self._validate_owner_names(root, source)
                bounded(line, 1, MAX_SEQUENCE, 'Invalid task motion source line')
                data = self._control_data(locks, operation, groups)
                self.validate(operation, data['groups'][0], data)
                for group in data['groups']:
                    scope = self._active.get(group)
                    if scope is not None:
                        if scope['root'] is not root or scope['locks'] is not locks:
                            raise ValueError('Task motion control found a foreign active scope')
                        self._verify_batch(scope, line)
                    elif self._queued.get(group):
                        raise ValueError('Task motion control found a queue without an active scope')
                rows.append((root, data))
            if self.sequence + len(rows) > MAX_SEQUENCE:
                raise ValueError('Motion request sequence exhausted')
        except ValueError as error:
            raise runtime.KarelRuntimeError(str(error), line) from error
        return locks, rows

    def apply_task_controls(self, source, operation, line, plan):
        """Commit the prepared transitions without polling clocks or driving tasks."""
        locks, rows = plan
        for root, data in rows:
            self._record_request(root, source, operation, data['groups'][0], line, False, 'completed', data)
            self._apply_control(locks, operation, data)

    def invoke(self, state, operation, data, nowait=False, line=None, *, settings=None, _execution=None, _background=False, _clauses=(), _callback_context=None, _clock_sample=None, _queue_wait=False):
        runtime = rt()
        if _clock_sample is not None and not _background:
            raise runtime.KarelRuntimeError('Admission clock samples require generated NOWAIT scopes', line)
        self.poll(state,line,_sample=_clock_sample)
        group = state.robot_group or 1
        root = runtime.task_root(state)
        locks = state.execution.require('group_locks', line)
        try:
            self._validate_owner_names(root, state)
            if settings and operation not in MOVES:
                raise ValueError('WITH settings require a MOVE request')
            queued = operation in MOVES and group in self._active
            if queued:
                head = self._active[group]
                if (not self.queue_limit or not _background or not head.get('background')
                        or head.get('scanning') or head['cancelled']):
                    raise ValueError('Motion group already has an active request scope; queueing requires generated NOWAIT moves or checked blocking scopes')
                if head['root'] is not root or not self.owns_scope(head):
                    raise ValueError('Queued motion requires the same task and logical ownership grant')
                if sum(map(len, self._queued.values())) >= self.queue_limit:
                    raise ValueError('Motion waiting queue capacity exceeded')
            if (type(_queue_wait) is not bool or _queue_wait and (not self.queue_limit or nowait
                    or not _background or _execution is None)):
                raise ValueError('Queued synchronous motion requires a generated scope and enabled queue')
            if type(_background) is not bool or _background and (not (nowait or _queue_wait) or _execution is None):
                raise ValueError('Background motion requires a generated NOWAIT execution scope')
            if _execution is not None and (operation not in MOVES or nowait and not _background or state._in_handler or root._in_handler):
                raise ValueError('Scoped motion requires supported generated output outside handler actions')
            if _background and (type(_execution) is not dict or _execution.get('handlers')!=self.clause_metadata(_clauses,line)
                    or 'conditions' in _execution and not _clauses):
                raise ValueError('NOWAIT local handlers require matching generated callable descriptors')
            if _background and _clauses:
                if (type(_callback_context) is not tuple or len(_callback_context)!=2 or _callback_context[0] is not root
                        or type(_callback_context[1]) is not tuple or len(_callback_context[1])!=len(state.local_frames)
                        or any(saved is not current for saved,current in zip(_callback_context[1],state.local_frames))
                        or any(not any(frame is live for live in state._timer_frames) for frame in _callback_context[1])):
                    raise ValueError('NOWAIT local callback task or defining frames changed before admission')
            if operation == 'MOVE ALONG':
                path, start, end = data.pop('path'), data['start'], data['end']
                start = 1 if start is None else start
                end = len(path.nodes) if end is None else end
                bounded(start, 1, len(path.nodes), 'PATH start outside available nodes')
                bounded(end, start, len(path.nodes), 'PATH end outside available nodes')
                if end - start + 1 > 256:
                    raise ValueError('MOVE ALONG exceeds 256 selected nodes')
                fields = dict(runtime.record_fields(path.node_spec))
                spec = fields.get('NODE_POS')
                if spec is None or spec[0] not in POSES:
                    raise ValueError('MOVE ALONG nodes require positional NODE_POS')
                data = dict(start=start, end=end, nodes=[operand(node.values['NODE_POS'], spec, line)
                            for node in path.nodes[start - 1:end]])
            if settings:
                data = dict(data, settings=[dict(row, group=group if row['group'] is None else row['group']) for row in settings])
            if operation in CONTROLS:
                groups = data['groups']
                if groups is None:
                    local = self._local_actions.get(root)
                    groups = [local['group']] if local is not None else [g for g, owner in locks.owners.items() if owner is root]
                data = self._control_data(locks, operation, groups)
            if operation == 'RELEASE':
                data = dict(groups=sorted(g for g, owner in locks.owners.items() if owner is root))
            elif operation == 'ATTACH':
                groups = self._released.get(root)
                if groups is None:
                    groups = state._source_settings.get('lock_groups')
                    if groups is None:
                        groups = self.groups
                data = dict(groups=sorted(groups))
            if _execution is not None:
                data = dict(data, execution=_execution)
            events, breakpoints = self.validate(operation, group, data)
            if any(g not in locks.groups for g in self.groups):
                raise ValueError('Motion groups must exist in the logical GroupLocks bank')
            selected = data['groups'] if operation in (*CONTROLS, 'ATTACH', 'RELEASE') else [group]
            for selected_group in selected:
                owner = locks.owners.get(selected_group)
                if owner is not None and owner is not root:
                    raise ValueError('Motion group is owned by another task')
                if operation not in ('ATTACH', 'RELEASE') and (owner is not root or root in self._released):
                    raise ValueError('Motion requires attached logical group ownership')
                if operation in (*MOVES, 'ATTACH', 'RELEASE') and (locks.motion.get(selected_group, 'idle') != ('executing' if queued else 'idle') or selected_group in locks.held):
                    raise ValueError('Motion request requires an idle logical group without a hold')
            # Other WITH groups are owned metadata references, not execution scopes.
            for row in data.get('settings', ()):
                owner = locks.owners.get(row['group'])
                if owner is not None and owner is not root:
                    raise ValueError('Motion WITH group is owned by another task')
                if owner is not root or root in self._released:
                    raise ValueError('Motion WITH requires attached logical group ownership')
            if self.sequence >= MAX_SEQUENCE:
                raise ValueError('Motion request sequence exhausted')
            outcome = 'completed'
            if operation in MOVES:
                if self.capture_only:
                    outcome = 'captured'
                else:
                    if not self.responses or self.responses[0]['operation'] != operation:
                        raise ValueError('Motion requires the next explicit matching completion response')
                    if (self.responses[0].get('delay_ms', 0) or 'node_times' in self.responses[0]) and _execution is None:
                        raise ValueError('Delayed motion requires newly generated cooperative output')
                    outcome = 'completed' if self.responses[0]['completed'] else 'rejected'
        except (ValueError, runtime.KarelRuntimeError) as error:
            raise runtime.KarelRuntimeError(str(error), line) from error
        # All data, ownership, capacity and scripted response checks precede publication.
        request = self._record_request(root, state, operation, group, line, nowait, outcome, data)
        if operation in MOVES and not self.capture_only:
            self.responses.pop(0)
        elif operation == 'ATTACH':
            for selected_group in selected:
                locks._grant(selected_group, root)
            self._released.pop(root, None)
        elif operation == 'RELEASE':
            if root not in self._released:
                self._released[root] = tuple(selected)
            for selected_group in selected:
                locks.owners.pop(selected_group, None)
                locks._ownership_tokens.pop(selected_group, None)
        elif operation in CONTROLS:
            self._apply_control(locks, operation, data)
        elif operation.endswith(' HAND'):
            self.hands[data['hand']] = {'OPEN HAND': 'open', 'CLOSE HAND': 'closed', 'RELAX HAND': 'relaxed'}[operation]
        if outcome == 'rejected':
            raise runtime.KarelRuntimeError('Scripted motion completion rejected: ' + operation, line)
        if _execution is not None:
            scope = dict(group=group, root=root, state=state, locks=locks,
                grant=locks._ownership_tokens.get(group), request=request,
                outcome=outcome, cancelled=False, consumer=object(), events=events, breakpoints=breakpoints)
            request['outcome'] = 'pending'
            if queued:
                self._queued.setdefault(group, []).append(scope)
            else:
                self._active[group] = scope
                locks.set_motion(group, 'executing')
            return scope

    @staticmethod
    def background_blocked(scope):
        root=scope['root']
        return (scope.get('scanning',False) or scope['group'] in scope['locks'].held or root._pause_requested or root._abort_requested
                or root.task_state not in ('running','waiting'))

    def poll(self,state=None,line=None,*,scheduler=None,_sample=None):
        """Observe task clocks and bounded FIFO progress without source callbacks."""
        runtime=rt();root=runtime.task_root(state) if state is not None else None
        if _sample is not None and (root is None or type(_sample) is not tuple or len(_sample)!=2
                or root._clock_us is not _sample[0] or type(_sample[1]) is not int or _sample[1]<0):
            raise runtime.KarelRuntimeError('NOWAIT admission clock sample or adapter changed',line)
        selected=[scope for scope in self._active.values() if scope.get('background')
                  and (root is None or scope['root'] is root)
                  and (scheduler is None or scope['root']._scheduler is scheduler)]
        roots=[]
        for scope in selected:
            if not any(scope['root'] is item for item in roots):roots.append(scope['root'])
        for owner in roots:
            scopes=[scope for scope in selected if scope['root'] is owner]
            for scope in scopes:
                try:
                    self._verify_batch(scope,line)
                    if owner._clock_us is not scope['clock']:raise runtime.KarelRuntimeError('NOWAIT motion clock adapter changed',line)
                except BaseException:
                    self.finish_scope(scope,'failed');raise
            try:
                now=runtime.timer_clock(owner,line) if _sample is None else _sample[1]
                if any(owner._clock_us is not scope['clock'] for scope in scopes):raise runtime.KarelRuntimeError('NOWAIT motion clock adapter changed during poll',line)
                if any(now<scope['last_us'] for scope in scopes):raise runtime.KarelRuntimeError('NOWAIT motion clock moved backwards',line)
                for scope in scopes:self._verify_batch(scope,line)
            except BaseException:
                for scope in scopes:self.finish_scope(scope,'failed')
                raise
            for initial in scopes:
                scope=initial
                while scope is not None:
                    blocked=self.background_blocked(scope)
                    progress=scope['request']['data']['execution']
                    if not scope['blocked'] and not blocked:scope['active_us']+=now-scope['last_us']
                    scope['last_us']=now;scope['blocked']=blocked
                    progress['elapsed_ms']=min(progress['delay_ms'],scope['active_us']//1000)
                    if scope.get('scanning'):break
                    if scope['cancelled']:
                        self.finish_scope(scope,'cancelled');break
                    if progress['elapsed_ms']!=progress['delay_ms'] or scope.get('clauses'):break
                    # A delayed poll can cross multiple supplied completions. Carry
                    # only observed active time; held/paused intervals never enter it.
                    completed_us=now-max(0,scope['active_us']-progress['delay_ms']*1000)
                    self.finish_scope(scope,scope['outcome'],completed_us=completed_us)
                    scope=self._active.get(scope['group'])

    def deadlines(self,scheduler):
        """Virtual deadlines apply only to the scheduler's own clock adapters."""
        return [scope['last_us']+max(0,scope['request']['data']['execution']['delay_ms']*1000-scope['active_us'])
                for scope in self._active.values() if scope.get('background') and scope['root']._scheduler is scheduler
                and scope['root']._scheduler_clock and not scope['blocked'] and not self.background_blocked(scope)
                and scope['active_us']<scope['request']['data']['execution']['delay_ms']*1000]

    def owns_scope(self, scope):
        locks, group = scope['locks'], scope['group']
        return locks.owners.get(group) is scope['root'] and locks._ownership_tokens.get(group) is scope['grant']

    def finish_scope(self, scope, outcome, *, completed_us=None):
        scope['request']['outcome'] = outcome
        group = scope['group']
        if self._active.get(group) is scope:
            waiting = self._queued.pop(group, [])
            self._active.pop(group)
            if outcome == 'completed' and waiting and self.owns_scope(scope):
                next_scope = waiting.pop(0)
                next_scope['last_us'] = scope['last_us'] if completed_us is None else completed_us
                next_scope['blocked'] = self.background_blocked(next_scope)
                self._active[group] = next_scope
                if waiting:self._queued[group] = waiting
            else:
                for queued in waiting:
                    queued['request']['outcome'] = 'failed' if outcome == 'failed' else 'cancelled'
                if self.owns_scope(scope) and scope['locks'].motion.get(group) == 'executing':
                    scope['locks'].set_motion(group, 'idle')
        else:
            waiting = self._queued.get(group, [])
            waiting[:] = [queued for queued in waiting if queued is not scope]
            if not waiting:self._queued.pop(group, None)
        consumer=scope['consumer']
        for cache in (scope['state']._event_seen,scope['state']._edge_history):
            for key in list(cache):
                identity=key[0]
                if type(identity) is tuple and len(identity)==2 and identity[0] is consumer:cache.pop(key)

    def verify_scope(self, scope, line):
        if not self.owns_scope(scope) or self._active.get(scope['group']) is not scope:
            raise rt().KarelRuntimeError('Active motion lost its logical ownership grant', line)
        self._verify_callback_frames(scope,line)
        if not scope['cancelled'] and scope['locks'].motion.get(scope['group'], 'idle') != 'executing':
            raise rt().KarelRuntimeError('Active motion work label was changed externally', line)

    @staticmethod
    def _verify_callback_frames(scope,line):
        if scope.get('clauses') and rt().task_root(scope['state']) is not scope['root']:
            raise rt().KarelRuntimeError('NOWAIT local callback defining task changed',line)
        if scope.get('clauses') and any(not any(frame is live for live in scope['state']._timer_frames) for frame in scope['frames']):
            raise rt().KarelRuntimeError('NOWAIT local callback defining frame is inactive',line)

    def _verify_batch(self,head,line):
        self.verify_scope(head,line)
        for scope in self._queued.get(head['group'], ()):
            if (scope['root'] is not head['root'] or scope['grant'] is not head['grant']
                    or not self.owns_scope(scope) or scope['request']['outcome'] != 'pending'):
                raise rt().KarelRuntimeError('Queued motion lost its task, pending scope or ownership grant',line)
            self._verify_callback_frames(scope,line)
            if scope['clock'] is not head['clock']:
                raise rt().KarelRuntimeError('Queued motion clock adapter changed',line)

    def _scopes(self):
        return [*self._active.values(), *(scope for queue in self._queued.values() for scope in queue)]

    def release_frame(self,state,frame):
        """Local NOWAIT callbacks cannot outlive their actual defining frame."""
        for scope in self._scopes():
            if scope.get('clauses') and scope['state'] is state and scope['frame'] is frame:
                self.finish_scope(scope,'cancelled')

    def finish_callbacks(self,state):
        for scope in self._scopes():
            if scope.get('clauses') and scope['state'] is state:self.finish_scope(scope,'cancelled')

    def scan_background(self,state,line=None):
        """Run local callbacks only at an owning task's cooperative checkpoints."""
        runtime=rt();root=runtime.task_root(state)
        if state._in_handler or root._in_handler:return
        selected=[scope for scope in self._active.values()
                  if scope.get('background') and scope.get('clauses') and scope['root'] is root]
        for scope in selected:
            if self._active.get(scope['group']) is not scope or scope.get('scanning'):continue
            self.poll(state,line)
            self.verify_scope(scope,line)
            if self.background_blocked(scope):continue
            owner=scope['state'];original,depth=owner.local_frames,owner.call_depth
            progress=scope['request']['data']['execution']
            scope['window']=(scope['last_scan'],progress['elapsed_ms'])
            scope['scanning']=True;scope['blocked']=True
            owner.local_frames=list(scope['frames']);owner.call_depth=len(owner.local_frames)
            try:
                yield from self.scan_local(scope,scope['clauses'],line)
                scope['last_scan']=progress['elapsed_ms']
                if owner._abort_requested or owner._pause_requested:
                    yield from runtime.checkpoint(owner,line)
                self.verify_scope(scope,line)
            except (GeneratorExit,runtime.KarelStop,runtime.KarelAbort):
                self.finish_scope(scope,'cancelled');raise
            except BaseException:
                self.finish_scope(scope,'failed');raise
            finally:
                owner.local_frames,owner.call_depth=original,depth
                try:
                    if self._active.get(scope['group']) is scope:self.poll(state,line)
                except BaseException:
                    self.finish_scope(scope,'failed');raise
                finally:
                    scope['scanning']=False;scope['blocked']=self.background_blocked(scope)
            if self._active.get(scope['group']) is not scope:continue
            if scope['cancelled']:self.finish_scope(scope,'cancelled')
            elif not self.background_blocked(scope) and progress['elapsed_ms']==progress['delay_ms']:
                self.finish_scope(scope,scope['outcome'])

    def condition(self, state, descriptor, line=None):
        scope = self._local_actions.get(rt().task_root(state))
        if scope is None:
            raise rt().KarelRuntimeError('AT NODE/TIME requires an active local motion predicate', line)
        key = descriptor['kind'], descriptor['node'], descriptor['offset_ms']
        if key not in scope['events']:
            raise rt().KarelRuntimeError('Motion temporal selector was not captured for this scope', line)
        if scope.get('background'):
            lower,upper=scope['window'];return any(lower<point<=upper for point in scope['events'][key])
        return scope['request']['data']['execution']['elapsed_ms'] in scope['events'][key]

    def scan_local(self, scope, clauses, line):
        """One-shot clauses in source order, isolated from global event cursors."""
        runtime, state = rt(), scope['state']
        execution = scope['request']['data']['execution']
        for index, (kind, predicate, action, location) in enumerate(clauses, 1):
            if scope['cancelled'] or scope['group'] in scope['locks'].held:
                return
            if index in execution['triggered']:
                continue
            chain, current = [], state
            while current is not None:
                chain.append((current, current._in_handler))
                current._in_handler = True
                current = current._budget_parent
            previous_scan, previous_error = state._scanning_condition, state._current_error
            original, depth = state.local_frames, state.call_depth
            previous_action = self._local_actions.get(scope['root'])
            self._local_actions[scope['root']] = scope
            state._scanning_condition = (scope['consumer'], index)
            try:
                result = predicate()
                if runtime.inspect.isgenerator(result):
                    result = yield from result
                if scope['cancelled']:
                    return
                if runtime.boolean(result, location):
                    execution['triggered'].append(index)
                    if kind == 'UNTIL':
                        self.invoke(state, 'CANCEL', {'groups':[scope['group']]}, False, location)
                    result = action()
                    if runtime.inspect.isgenerator(result):
                        yield from result
            finally:
                state.local_frames, state.call_depth = original, depth
                state._scanning_condition, state._current_error = previous_scan, previous_error
                if previous_action is None:
                    self._local_actions.pop(scope['root'], None)
                else:
                    self._local_actions[scope['root']] = previous_action
                for current, previous in chain:
                    current._in_handler = previous

    def execute(self, state, operation, data, nowait=False, line=None, *, settings=None, clauses=(), conditions=()):
        """Explicit progress, with NOWAIT callbacks observed by owner checkpoints."""
        runtime = rt()
        self.clause_metadata(clauses,line)
        delay, plan = 0, None
        if not self.capture_only and self.responses and self.responses[0]['operation'] == operation:
            delay = self.responses[0].get('delay_ms', 0)
            plan = self.responses[0].get('node_times')
        queue_wait = bool(self.queue_limit and not nowait
                          and (state.robot_group or 1) in self._active)
        scoped = bool(clauses) or bool(delay) or plan is not None or bool(conditions) or bool(nowait and self.queue_limit) or queue_wait
        if not scoped:
            self.invoke(state, operation, data, nowait, line, settings=settings)
            return
        execution = dict(delay_ms=delay, elapsed_ms=0,
            handlers=[dict(kind=kind, line=location) for kind, _, _, location in clauses], triggered=[])
        if plan is not None:
            execution['node_times'] = {str(key): value for key, value in sorted(node_times(plan, delay).items())}
        if conditions:
            execution['conditions'] = list(conditions)
        if nowait or queue_wait:
            frames=list(state.local_frames)
            if clauses and any(not any(frame is live for live in state._timer_frames) for frame in frames):
                raise runtime.KarelRuntimeError('NOWAIT local callback requires live defining frames',line)
            root=runtime.task_root(state);clock=root._clock_us;now=runtime.timer_clock(root,line)
            if (runtime.task_root(state) is not root or clauses and (len(frames)!=len(state.local_frames)
                    or any(saved is not current for saved,current in zip(frames,state.local_frames))
                    or any(not any(frame is live for live in state._timer_frames) for frame in frames))):
                raise runtime.KarelRuntimeError('NOWAIT local callback defining frames or task changed during capture',line)
            if root._clock_us is not clock:raise runtime.KarelRuntimeError('NOWAIT motion clock adapter changed during capture',line)
            scope=self.invoke(state,operation,data,nowait,line,settings=settings,_execution=execution,_background=True,_clauses=clauses,_callback_context=(root,tuple(frames)),_clock_sample=(clock,now) if self.queue_limit else None,_queue_wait=queue_wait)
            scope.update(background=True,clock=clock,last_us=now,active_us=0,blocked=self.background_blocked(scope),
                clauses=tuple(clauses),frames=frames,frame=frames[-1] if frames else None,
                scanning=False,last_scan=-1)
            if clauses:yield from self.scan_background(state,line)
            elif delay==0 and self._active.get(scope['group']) is scope:self.finish_scope(scope,scope['outcome'])
            if queue_wait:yield from self._wait_for_scope(scope,line)
            return
        scope = self.invoke(state, operation, data, nowait, line, settings=settings, _execution=execution)
        outcome = 'failed'
        try:
            progress = scope['request']['data']['execution']
            event_cursor = 0
            while True:
                yield from runtime.checkpoint(state, line)
                self.verify_scope(scope, line)
                if scope['cancelled']:
                    outcome = 'cancelled'
                    break
                yield from self.scan_local(scope, clauses, line)
                if state._abort_requested or state._pause_requested:
                    yield from runtime.checkpoint(state, line)
                self.verify_scope(scope, line)
                if scope['cancelled']:
                    outcome = 'cancelled'
                    break
                held = scope['group'] in scope['locks'].held
                if not held and progress['elapsed_ms'] >= delay:
                    outcome = scope['outcome']
                    break
                step = 10 if held else min(10, delay - progress['elapsed_ms'])
                while event_cursor < len(scope['breakpoints']) and scope['breakpoints'][event_cursor] <= progress['elapsed_ms']:
                    event_cursor += 1
                if not held and event_cursor < len(scope['breakpoints']):
                    step = min(step, scope['breakpoints'][event_cursor] - progress['elapsed_ms'])
                yield from runtime.delay_execution(state, step, line)
                if not held:
                    progress['elapsed_ms'] += step
        except (GeneratorExit, runtime.KarelStop, runtime.KarelAbort):
            outcome = 'cancelled'
            raise
        finally:
            consumer = scope['consumer']
            for cache in (state._event_seen, state._edge_history):
                for key in list(cache):
                    identity = key[0]
                    if type(identity) is tuple and len(identity) == 2 and identity[0] is consumer:
                        cache.pop(key)
            self.finish_scope(scope, outcome)

    def _wait_for_scope(self, scope, line=None):
        """Block one source MOVE on its own admitted FIFO result."""
        runtime = rt()
        state = scope['state']
        outcome = 'failed'
        try:
            while scope['request']['outcome'] == 'pending':
                yield from runtime.checkpoint(state, line)
                if scope['request']['outcome'] != 'pending':break
                head = self._active.get(scope['group'])
                if (not self.owns_scope(scope) or head is None or head['root'] is not scope['root']
                        or head is not scope and not any(scope is item for item in self._queued.get(scope['group'], ()))):
                    raise runtime.KarelRuntimeError('Queued synchronous motion lost its admitted scope or ownership grant', line)
                self.verify_scope(head, line)
                progress = head['request']['data']['execution']
                # A promoted callback job needs its entry scan before sleeping;
                # a fully elapsed callback head needs an owner observation.
                if (not self.background_blocked(head)
                        and (head.get('clauses') and head['last_scan'] < 0
                             or progress['elapsed_ms'] == progress['delay_ms'])):
                    continue
                remaining_us = progress['delay_ms'] * 1000 - head['active_us']
                if head.get('clauses') and not head['request']['nowait']:
                    for point in head['breakpoints']:
                        distance = point * 1000 - head['active_us']
                        if distance > 0:
                            remaining_us = min(remaining_us, distance)
                            break
                step = 10 if self.background_blocked(head) else min(10, max(1, (remaining_us + 999) // 1000))
                yield from runtime.delay_execution(state, step, line)
            if scope['request']['outcome'] not in ('completed', 'cancelled'):
                raise runtime.KarelRuntimeError('Queued synchronous motion did not complete successfully', line)
        except (GeneratorExit, runtime.KarelStop, runtime.KarelAbort):
            outcome = 'cancelled'
            raise
        finally:
            if scope['request']['outcome'] == 'pending':self.finish_scope(scope, outcome)

    def has_pending_group(self, group):
        return group in self._active or bool(self._queued.get(group))

    def finish(self, state):
        root = rt().task_root(state)
        for scope in list(self._active.values()):
            if scope['root'] is root:
                self.finish_scope(scope, 'cancelled')
        self._released.pop(root, None)

    def to_config(self):
        if self._active or self._queued:
            raise ValueError('Finish or stop active motion scopes before saving context')
        if self._released:
            raise ValueError('Finish or reattach released motion tasks before saving context')
        config = dict(groups={str(k):v for k,v in sorted(self.groups.items())},
            hands={str(k):v for k,v in sorted(self.hands.items())}, capture_only=self.capture_only,
            responses=deepcopy(self.responses), limit=self.limit, sequence=self.sequence,
            history=deepcopy(self.history))
        if self.queue_limit:config['queue_limit'] = self.queue_limit
        if self.cross_group_settings:config['cross_group_settings'] = True
        return config

    snapshot = to_config

    @classmethod
    def from_config(cls, config):
        if type(config) is not dict or set(config) - {'groups', 'hands', 'capture_only', 'responses', 'limit', 'sequence', 'history', 'queue_limit', 'cross_group_settings'}:
            raise ValueError('Unknown motion request configuration fields')
        config = dict(config)
        if 'groups' not in config:
            raise ValueError('Motion requests require explicit groups')
        for field in ('groups', 'hands'):
            values = config.get(field, {})
            if type(values) is not dict or any(type(k) is not str or not re.fullmatch(r'[1-9][0-9]*', k) for k in values):
                raise ValueError('Motion bank keys require canonical positive integers')
            config[field] = {int(k):v for k,v in values.items()}
        return cls(**config)
