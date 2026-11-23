"""Source-ordered frame and tool facts for offline input discovery."""

from copy import copy
from dataclasses import dataclass, field

from . import runtime as rt
from .extended import SYSTEM_POSE_AXES, _SystemVariableTarget
from .input_robot_values import RobotFactsUnavailable
from .input_value_conversions import UNKNOWN, Value, detached_facts, materialized_value


_ATTRIBUTES = {'FRAME': ('frames', 'active_frame'), 'TOOL': ('tools', 'active_tool')}
_UNCHANGED = object()


@dataclass
class RobotTableFacts:
    # None in the number slot denotes the selection, UNKNOWN denotes all rows.
    # A None group in invalidated denotes all groups.
    values: dict = field(default_factory=dict)
    invalidated: set = field(default_factory=set)

    def copy(self):
        return RobotTableFacts(self.values.copy(), self.invalidated.copy())

    @classmethod
    def merge(cls, branches):
        if len(branches) == 1:
            return branches[0].copy()
        values = {}
        for key in set().union(*(branch.values for branch in branches)):
            value = branches[0].values.get(key, _UNCHANGED)
            values[key] = value if all(branch.values.get(key, _UNCHANGED) == value
                                       for branch in branches[1:]) else UNKNOWN
        return cls(values, set().union(*(branch.invalidated for branch in branches)))

    def invalidate(self, group, kind, number):
        if group is not None and number is not UNKNOWN:
            self.values[group, kind, number] = UNKNOWN
            return
        self.invalidated.add((group, kind, number is None))
        for key in tuple(self.values):
            owner, family, row = key
            if family == kind and (group is None or group == owner) and (row is None) == (number is None):
                del self.values[key]

    def invalidate_all(self):
        self.values.clear()
        self.invalidated.update((None, kind, selection) for kind in _ATTRIBUTES for selection in (False, True))

    def value(self, robot, group, kind, number):
        key = group, kind, number
        if key in self.values:
            value = self.values[key]
            return materialized_value(value) if isinstance(value, Value) else value
        if (group, kind, number is None) in self.invalidated or (None, kind, number is None) in self.invalidated:
            return UNKNOWN
        table, selection = _ATTRIBUTES[kind]
        return getattr(robot, selection) if number is None else getattr(robot, table).get(number)

    def selected_robot(self, robot, group):
        """Use only the two rows that a model query can observe."""
        if not self.values and not self.invalidated:
            return robot
        result = copy(robot)
        for kind, (table, selection) in _ATTRIBUTES.items():
            number = self.value(robot, group, kind, None)
            if number is UNKNOWN:
                raise RobotFactsUnavailable('Active frame or tool selection needs run-time evaluation')
            row = self.value(robot, group, kind, number)
            if row is UNKNOWN:
                raise RobotFactsUnavailable('Selected frame or tool row needs run-time evaluation')
            setattr(result, selection, number)
            setattr(result, table, {} if row is None else {number: row})
        return result

    def _endpoint(self, robot, group, operation, number):
        kind = operation.removeprefix('ACTIVE_')
        table, selection = _ATTRIBUTES[kind]
        result = copy(robot)
        result.active_group = group
        result.groups = {}
        setattr(result, table, {})
        if operation.startswith('ACTIVE_'):
            number = self.value(robot, group, kind, None)
            setattr(result, selection, number)
        return rt.ExecutionContext(robot=result), kind, table, number

    def named_endpoint(self, robot, address, *, writing, line):
        operation, group, number, path = address
        selection = operation.endswith('_ID')
        kind = operation.removeprefix('ACTIVE_').removesuffix('_ID')
        endpoint_kind = kind if selection else operation
        context, _, table, resolved = self._endpoint(robot, group, endpoint_kind, number)
        if selection:
            resolved = self.value(robot, group, kind, None)
            setattr(context.robot, _ATTRIBUTES[kind][1], resolved)
        if resolved is UNKNOWN:
            raise RobotFactsUnavailable('Frame or tool selection needs run-time evaluation')
        # A numbered Cartesian replacement can publish even without a previous
        # row. Capture a known row when available for metadata and model checks.
        if not (selection and writing):
            row = self.value(robot, group, kind, resolved)
            requires_row = not writing or bool(path) or operation.startswith('ACTIVE_')
            if row is UNKNOWN and requires_row:
                raise RobotFactsUnavailable('Frame or tool row needs run-time evaluation')
            if row is not None and row is not UNKNOWN:
                getattr(context.robot, table)[resolved] = row
        return _SystemVariableTarget(context, *address, writing, line)

    def publish_named(self, robot, endpoint, value, line):
        group = endpoint.group
        kind = endpoint.kind.removeprefix('ACTIVE_').removesuffix('_ID')
        if endpoint.selection:
            number = rt.integer(value, line)
            row = self.value(robot, group, kind, number)
            if row is UNKNOWN:
                raise RobotFactsUnavailable('Newly selected frame or tool row needs run-time evaluation')
            if row is not None:
                endpoint.table[number] = row
        endpoint.guard((), line)
        endpoint.publish(value, line)
        key = group, kind, None if endpoint.selection else endpoint.number
        self.values[key] = value if endpoint.selection else detached_facts(endpoint.table[endpoint.number])

    def invalidate_named(self, robot, address):
        operation, group, number, _ = address
        kind = operation.removeprefix('ACTIVE_').removesuffix('_ID')
        if operation.startswith('ACTIVE_'):
            if robot is None:
                number = UNKNOWN
            else:
                number = self.value(robot, group, kind, None)
        self.invalidate(group, kind, number)

    def read(self, robot, group, operation, number, path, *, selection, line):
        kind = operation.removeprefix('ACTIVE_')
        if selection:
            number = self.value(robot, group, kind, None)
        context, kind, table, resolved = self._endpoint(robot, group, operation, number)
        if resolved is UNKNOWN:
            raise RobotFactsUnavailable('Frame or tool selection needs run-time evaluation')
        row = self.value(robot, group, kind, resolved)
        if row is UNKNOWN:
            raise RobotFactsUnavailable('Frame or tool row needs run-time evaluation')
        if row is not None:
            getattr(context.robot, table)[resolved] = row
        with rt._numeric_scope('pythonic'):
            if selection:
                setattr(context.robot, _ATTRIBUTES[kind][1], resolved)
                return Value(context.system_selection(kind, group, line), spec=['INTEGER'])
            external_axis = len(path) == 1 and path[0] in SYSTEM_POSE_AXES
            result = context.system_pose(operation, group, number, line, axis=path[0] if external_axis else None)
            if external_axis:
                return Value(result, spec=['REAL'])
            for field_name in path:
                reference = rt.field_reference(result, field_name, line)
                result = rt.require(reference.raw(), line)
            return (detached_facts(result) if isinstance(result, rt.Structure) else
                    Value(result, spec=list(reference.spec)))

    def write(self, robot, group, operation, number, path, source, *, selection, line):
        kind = operation.removeprefix('ACTIVE_')
        target = None if selection else number
        if robot is None:
            self.invalidate(group, kind, target if target is not None or selection else UNKNOWN)
            raise RobotFactsUnavailable('Frame or tool write depends on the group or execution order')
        context, kind, table, resolved = self._endpoint(robot, group, operation, number)
        target = None if selection else resolved
        needed = source if selection else resolved
        row = self.value(robot, group, kind, needed) if needed is not UNKNOWN else UNKNOWN
        # A numbered whole-row replacement does not depend on the old row.
        needs_prior_row = selection or bool(path) or operation.startswith('ACTIVE_')
        if source is UNKNOWN or resolved is UNKNOWN or needs_prior_row and row is UNKNOWN:
            self.invalidate(group, kind, target)
            raise RobotFactsUnavailable('Frame or tool write depends on source data at run time')
        if row is not None and row is not UNKNOWN:
            getattr(context.robot, table)[needed] = row
        with rt._numeric_scope('pythonic'):
            if selection:
                context.system_selection_write(kind, group, source, line)
                self.values[group, kind, None] = source
            else:
                if type(source) is float and len(path) == 2 and path[0] == 'CONFIG_DATA':
                    expected = dict(rt.record_fields(('CONFIG',)))[path[1]]
                    if rt.real_integral_kind(expected, ('REAL',)):
                        source = rt.real_integral_value(expected, source, line)
                context.system_pose_write(operation, group, number, source, path, line)
                self.values[group, kind, resolved] = detached_facts(getattr(context.robot, table)[resolved])
