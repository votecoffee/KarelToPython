"""Explicit offline motion requests, detached data and logical hand state.

Nothing in this module computes a trajectory or changes robot feedback. A host
must opt into capture-only execution or supply immediate completion responses.
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
            '$UFRAME':'POSE', '$UTOOL':'POSE', '$USE_CONFIG':'BOOLEAN'}
KINDS = {6:'JOINT', 7:'LINEAR', 8:'CIRCULAR'}


def rt():
    from . import runtime
    return runtime


def bounded(value, low, high, message):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(message)
    return value


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
    if name == '$MOTYPE':
        value = runtime.integer(value, line)
        if value not in KINDS:
            raise runtime.KarelRuntimeError('Motion type requires JOINT/LINEAR/CIRCULAR (6/7/8)', line)
        return KINDS[value]
    if name in ('$SPEED', '$ROTSPEED'):
        value = runtime.real(value, line)
        if value < 0:
            raise runtime.KarelRuntimeError('Motion speed settings require nonnegative finite values', line)
        return value
    if name == '$USE_CONFIG':
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
                 limit=128, sequence=0, history=None):
        if type(groups) is not dict or not groups or len(groups) > 31:
            raise ValueError('Motion groups require an explicit group:axis-count map')
        self.groups = {}
        for group, axes in groups.items():
            bounded(group, 1, 31, 'Motion group must be in 1..31')
            self.groups[group] = bounded(axes, 1, 9, 'Motion group axis count must be in 1..9')
        if type(capture_only) is not bool:
            raise ValueError('capture_only requires BOOLEAN')
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
            if (type(row) is not dict or set(row) != {'operation', 'completed'}
                    or type(row['operation']) is not str or row['operation'] not in MOVES
                    or type(row['completed']) is not bool):
                raise ValueError('Motion response requires operation and BOOLEAN completed')
        if capture_only and responses:
            raise ValueError('Choose capture-only or scripted motion responses')
        self.responses = deepcopy(responses)
        self._released = {}
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
            if type(row['outcome']) is not str or row['outcome'] not in ('captured', 'completed', 'rejected'):
                raise ValueError('Invalid motion outcome')
            if row['operation'] not in MOVES and row['outcome'] != 'completed':
                raise ValueError('Logical motion actions require completed history')
            try:
                self.validate(row['operation'], row['group'], row['data'])
            except rt().KarelRuntimeError as error:
                raise ValueError(str(error)) from error
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
        optional = ({'settings'} if operation in MOVES else set()) | ({'via'} if operation == 'MOVE TO' else set())
        if set(data) - optional != expected:
            raise ValueError('Unexpected motion request fields')
        if 'settings' in data:
            rows = data['settings']
            if type(rows) is not list or not 1 <= len(rows) <= len(SETTINGS):
                raise ValueError('Motion WITH requires 1..6 supported settings')
            names = set()
            for row in rows:
                if type(row) is not dict or set(row) != {'name', 'group', 'value'}:
                    raise ValueError('Malformed motion WITH setting')
                name = row['name']
                if type(name) is not str or name not in SETTINGS or name in names:
                    raise ValueError('Unknown or duplicate motion WITH setting')
                names.add(name)
                if type(row['group']) is not int or row['group'] != group:
                    raise ValueError('Motion WITH group must match the selected request group')
                value = row['value']
                if name == '$MOTYPE':
                    if type(value) is not str or value not in KINDS.values():
                        raise ValueError('Invalid motion WITH interpolation type')
                    if value == 'CIRCULAR' and (operation != 'MOVE TO' or 'via' not in data):
                        raise ValueError('CIRCULAR motion requires MOVE TO with VIA')
                    if value != 'CIRCULAR' and 'via' in data:
                        raise ValueError('VIA conflicts with the explicit motion type')
                elif name in ('$UFRAME', '$UTOOL'):
                    typed(value, POSES[:-1])
                elif name == '$USE_CONFIG':
                    if type(value) is not bool:
                        raise ValueError('USE_CONFIG requires BOOLEAN')
                else:
                    runtime = rt()
                    with runtime._numeric_scope('pythonic'):
                        if runtime.real(value) < 0:
                            raise ValueError('Motion speed settings must be nonnegative')
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
        if len(json.dumps(data, allow_nan=False, separators=(',', ':')).encode('ascii')) > 65536:
            raise ValueError('Motion request exceeds 64 KiB')

    def invoke(self, state, operation, data, nowait=False, line=None, *, settings=None):
        runtime = rt()
        group = state.robot_group or 1
        root = runtime.task_root(state)
        locks = state.execution.require('group_locks', line)
        try:
            for name in (root.program_name, state.program_name):
                if type(name) is not str or not re.fullmatch(r'[A-Z_][A-Z_0-9]{0,253}', name):
                    raise ValueError('Motion request owner requires an ASCII source identifier within 254 characters')
            if settings and operation not in MOVES:
                raise ValueError('WITH settings require a MOVE request')
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
                    groups = [g for g, owner in locks.owners.items() if owner is root]
                if (type(groups) is not list or len(groups) > 31
                        or any(type(g) is not int or g not in self.groups for g in groups)
                        or len(set(groups)) != len(groups)):
                    raise ValueError('Motion control requires distinct configured group numbers')
                groups = sorted(groups)
                states = []
                for selected_group in groups:
                    before = dict(motion=locks.motion.get(selected_group, 'idle'), held=selected_group in locks.held)
                    states.append(dict(group=selected_group, before=before, after=transition(operation, before)))
                data = dict(groups=groups, states=states)
            if operation == 'RELEASE':
                data = dict(groups=sorted(g for g, owner in locks.owners.items() if owner is root))
            elif operation == 'ATTACH':
                groups = self._released.get(root)
                if groups is None:
                    groups = state._source_settings.get('lock_groups')
                    if groups is None:
                        groups = self.groups
                data = dict(groups=sorted(groups))
            self.validate(operation, group, data)
            if any(g not in locks.groups for g in self.groups):
                raise ValueError('Motion groups must exist in the logical GroupLocks bank')
            selected = data['groups'] if operation in (*CONTROLS, 'ATTACH', 'RELEASE') else [group]
            for selected_group in selected:
                owner = locks.owners.get(selected_group)
                if owner is not None and owner is not root:
                    raise ValueError('Motion group is owned by another task')
                if operation not in ('ATTACH', 'RELEASE') and (owner is not root or root in self._released):
                    raise ValueError('Motion requires attached logical group ownership')
                if operation in (*MOVES, 'ATTACH', 'RELEASE') and (locks.motion.get(selected_group, 'idle') != 'idle' or selected_group in locks.held):
                    raise ValueError('Motion request requires an idle logical group without a hold')
            if self.sequence >= MAX_SEQUENCE:
                raise ValueError('Motion request sequence exhausted')
            outcome = 'completed'
            if operation in MOVES:
                if self.capture_only:
                    outcome = 'captured'
                else:
                    if not self.responses or self.responses[0]['operation'] != operation:
                        raise ValueError('Motion requires the next explicit matching completion response')
                    outcome = 'completed' if self.responses[0]['completed'] else 'rejected'
        except (ValueError, runtime.KarelRuntimeError) as error:
            raise runtime.KarelRuntimeError(str(error), line) from error
        # All data, ownership, capacity and scripted response checks precede publication.
        self.sequence += 1
        self.history.append(dict(sequence=self.sequence, program=root.program_name,
            source_program=state.program_name, operation=operation, group=group,
            line=line, nowait=nowait, outcome=outcome, data=deepcopy(data)))
        del self.history[:-self.limit]
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
            for row in data['states']:
                selected_group = row['group']
                locks.set_motion(selected_group, row['after']['motion'])
                if row['after']['held']:
                    locks.held.add(selected_group)
                else:
                    locks.held.discard(selected_group)
        elif operation.endswith(' HAND'):
            self.hands[data['hand']] = {'OPEN HAND': 'open', 'CLOSE HAND': 'closed', 'RELAX HAND': 'relaxed'}[operation]
        if outcome == 'rejected':
            raise runtime.KarelRuntimeError('Scripted motion completion rejected: ' + operation, line)

    def finish(self, state):
        self._released.pop(rt().task_root(state), None)

    def to_config(self):
        if self._released:
            raise ValueError('Finish or reattach released motion tasks before saving context')
        return dict(groups={str(k):v for k,v in sorted(self.groups.items())},
            hands={str(k):v for k,v in sorted(self.hands.items())}, capture_only=self.capture_only,
            responses=deepcopy(self.responses), limit=self.limit, sequence=self.sequence,
            history=deepcopy(self.history))

    snapshot = to_config

    @classmethod
    def from_config(cls, config):
        if type(config) is not dict or set(config) - {'groups', 'hands', 'capture_only', 'responses', 'limit', 'sequence', 'history'}:
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
