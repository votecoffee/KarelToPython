"""Prepare offline model conversions for captured PATH and named data values."""

from . import runtime as rt
from .extended import variable_value
from .input_robot_values import RobotFactsUnavailable, _convert_model_leaf, _run_portable_model
from .input_value_conversions import UNKNOWN, Value, detached_facts, materialized_value
from .storage import list_spec, tuple_spec
from .variable_kinematics import transfer


def _known_data(value, operation, tick):
    tick(1 + len(value.facts or ()))
    if value.whole_record_missing:
        return rt.UNINITIALIZED
    raw = materialized_value(value, allow_missing=True)
    if raw is UNKNOWN:
        raise RobotFactsUnavailable(operation+' needs known source records at run time')
    return raw


def _record_facts(spec, value):
    if value is rt.UNINITIALIZED:
        return Value(spec=list_spec(spec), complete=False, uninitialized=True, whole_record_missing=True)
    return detached_facts(value)


def evaluate_model_paths(robot, target, captures, layout, line, tick, *, operation, allow_missing):
    """Prepare every PATH before publishing any converted header or node."""
    target_spec = tuple_spec(target)

    def prepare(context, value):
        source = rt.PathValue(tuple_spec(value.spec))
        records = [_known_data(record, operation, tick) for record in value.path_records]
        has_header = source.spec[2] is not None
        source.nodes = records[int(has_header):]
        if has_header:
            source.data = records[0]
        return context._prepare_path_data(target_spec, source, source.nodes, source.data, layout, line,
                                          allow_missing=allow_missing)

    def evaluate(context, check):
        captured = [prepare(context, value) for value in captures]
        node_type = target_spec[1] or rt.PREDEFINED_STRUCTURES['STD_PTH_NODE']
        header = target_spec[2]

        def finish(spec, row):
            value, pending = row
            for storage, key, expected, source in pending:
                storage[key] = _convert_model_leaf(context, expected, source, line, check)
            if pending:
                value = rt._partial_aggregate_value(spec, value, line)
            return _record_facts(spec, value)

        paths = []
        for nodes, data in captured:
            values = tuple(finish(node_type, row) for row in nodes)
            if header is not None:
                values = (finish(header, data), *values)
            paths.append(Value(spec=target, complete=all(row.complete for row in values), path_records=values))
        return paths

    return _run_portable_model(robot, operation, evaluate, tick)


class _TransferState(rt.State):
    """Isolated storage and metering for the regular variable transfer engine."""

    def __init__(self, context, tick, check):
        super().__init__({}, {}, context=context)
        self._work_tick = tick
        self._model_checkpoint = check

    def tick(self, line=None, *, _diagnostic=True):
        self._work_tick()

    def kinematic_assignment(self, target, value, line=None):
        return _convert_model_leaf(self.execution, target, value, line, self._model_checkpoint)


def evaluate_model_variables(robot, pairs, line, tick, *, prefix, operation):
    """Evaluate one named transfer, packing only selected row-major cells."""
    def evaluate(context, check):
        state = _TransferState(context, tick, check)
        expected = tuple_spec(pairs[0][0])
        actual = tuple_spec(pairs[0][1].spec)
        captured = [_known_data(value, operation, tick) for _, value in pairs]
        if prefix:
            shape = len(captured)
            expected = ('ARRAY', shape, expected)
            actual = ('ARRAY', shape, actual)
            raw = rt.Array(actual)
            raw.values[:] = captured
        else:
            raw = captured[0]
        destination = rt.Reference(expected, {'value': rt.initial_value(expected)}, 'value')
        prepared = transfer(state, destination, variable_value(actual, raw, line), line)
        if prepared is None:
            return [], 3
        copied, missing = prepared
        values = ([_record_facts(expected[2], value) for value in copied.values] if prefix
                  else [_record_facts(expected, copied)])
        return values, 12311 if missing else 0

    return _run_portable_model(robot, operation, evaluate, tick)
