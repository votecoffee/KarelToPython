"""Bounded, read-only evaluation of offline robot data and geometry."""

from . import runtime as rt
from .extended import mirror
from .input_value_conversions import UNKNOWN, Value, detached_facts, materialized_value
from .kinematics import SerialRobotModel
from .storage import tuple_spec


ROBOT_SNAPSHOTS = {'CURPOS': ('XYZWPREXT',), 'CURJPOS': ('JOINTPOS', 9)}
ROBOT_RANGE_QUERIES = {'IN_RANGE', 'J_IN_RANGE', 'CHECK_EPOS'}
ROBOT_CONVERSIONS = {'JOINT2POS': 4, 'POS2JOINT': 7}
CONFIG_TEXT_CONVERSIONS = {'CNV_STR_CONF', 'CNV_CONF_STR', 'CNV_CNF_STRG'}
POSE_CONSTRUCTORS = {'POS', 'VEC', 'MIRROR'}
MODEL_SAMPLE_LIMIT = 1024


class RobotFactsUnavailable(ValueError):
    """The saved state or known operands are insufficient for evaluation."""


def constructor_schema(name, arity):
    if name == 'VEC':
        return ['VECTOR']
    return ['XYZWPREXT' if name == 'MIRROR' or arity == 10 else 'XYZWPR']


def construct_pose(name, arguments, line):
    if name == 'MIRROR' and any(value.spec and value.spec[0] == 'JOINTPOS' for value in arguments[:2]):
        raise RobotFactsUnavailable('MIRROR joint operands require a robot-model conversion')
    values = [materialized_value(value) for value in arguments]
    if any(value is UNKNOWN for value in values):
        return None
    with rt._numeric_scope('pythonic'):
        if name == 'MIRROR':
            result = mirror(*values, line=line)
        else:
            result = rt.builtin(name, values, line)
    return detached_facts(result)


def current_robot_facts(robot, operation, line, *, select):
    if operation == 'CURPOS' and robot.current is not None and robot.current.position is None:
        if type(robot.model) is not SerialRobotModel:
            raise RobotFactsUnavailable('CURPOS requires a saved pose or the portable DH model')
        robot = select()
    with rt._numeric_scope('pythonic'):
        return detached_facts(robot.current_value(operation, line))


def check_robot_range(robot, operation, arguments, line, *, select, tick):
    values = [materialized_value(value) for value in arguments]
    if any(value is UNKNOWN for value in values):
        raise RobotFactsUnavailable(operation+' needs the source position at run time')
    point = values[0]
    with rt._numeric_scope('pythonic'):
        if operation != 'CHECK_EPOS' and isinstance(point, rt.JointPosition):
            return robot.in_range(point, operation, line)
        model = robot.model
        if type(model) is not SerialRobotModel:
            raise RobotFactsUnavailable(operation+' requires a saved portable DH model')
        if operation == 'CHECK_EPOS':
            frame, tool = (rt.frame_value(value, line) for value in values[1:])
            if isinstance(point, rt.JointPosition):
                # Use the same bounded forward conversion as the runtime. The
                # temporary context publishes only to local conversion outputs.
                point = rt.ExecutionContext(robot=robot)._forward_pose(point, frame, tool, None, line)
        else:
            robot = select()
            frame, tool = robot.frame(robot.active_frame), robot.tool(robot.active_tool)
        point = rt.frame_value(point, line)
        checked = 0

        def checkpoint():
            nonlocal checked
            checked += 1
            if checked > MODEL_SAMPLE_LIMIT:
                raise RobotFactsUnavailable(operation+' exceeded the discovery model-sample limit')
            tick(1 + model.axes)

        reference = robot.current.joints if robot.current is not None else None
        return model.reachable(point, frame, tool, reference=reference, check=checkpoint)


def _run_portable_model(robot, operation, evaluate, tick, sample_limit=None):
    if sample_limit is None:
        sample_limit = MODEL_SAMPLE_LIMIT
    if type(robot.model) is not SerialRobotModel:
        raise RobotFactsUnavailable(operation+' requires the portable DH model')
    samples = 0
    interrupted = None

    def checkpoint():
        nonlocal samples, interrupted
        samples += 1
        try:
            if samples > sample_limit:
                raise RobotFactsUnavailable(operation+' exceeded the discovery model-sample limit')
            tick(1 + robot.model.axes)
        except Exception as error:
            interrupted = error
            raise

    checkpoint()
    try:
        with rt._numeric_scope('pythonic'):
            return evaluate(rt.ExecutionContext(robot=robot), checkpoint)
    except rt.KarelRuntimeError as error:
        if interrupted is not None and error.__cause__ is interrupted:
            raise interrupted from None
        raise


def evaluate_robot_assignment(robot, target, value, line, tick, *, operation='Kinematic assignment', sample_limit=None):
    return _run_portable_model(
        robot, operation,
        lambda context, check: context.kinematic_assignment(
            None, target, value, line, group=robot.active_group, check=check,
        ),
        tick, MODEL_SAMPLE_LIMIT if sample_limit is None else sample_limit,
    )


def _convert_model_leaf(context, expected, value, line, check):
    check()
    return context.kinematic_assignment(None, expected, value, line, group=context.robot.active_group, check=check)


def evaluate_robot_aggregate(robot, conversion, target, value, line, tick, *, operation):
    """Preflight the whole ARRAY or STRUCTURE and meter one private conversion."""
    def evaluate(context, check):
        if conversion == 'kinematic_array':
            source, result = rt.prepare_kinematic_array(target, value, line)
            leaf = rt.array_leaf_spec(result.spec)
            source_cells = rt._array_conversion_cells(source)
            result_cells = rt._array_conversion_cells(result)
            pending = ((output, index, leaf, storage[key])
                       for (storage, key), (output, index) in zip(source_cells, result_cells, strict=True))
        else:
            result, pending = rt.prepare_kinematic_record(target, value, line)
        for storage, key, expected, item in pending:
            storage[key] = _convert_model_leaf(context, expected, item, line, check)
        if conversion == 'kinematic_record':
            return rt._partial_aggregate_value(result.spec, result, line)
        return result

    return _run_portable_model(robot, operation, evaluate, tick, MODEL_SAMPLE_LIMIT)


def _reference(spec):
    expected = tuple_spec(spec)
    return rt.Reference(expected, {'value': rt.initial_value(expected)}, 'value')


def _output_facts(reference):
    raw = reference.raw()
    if isinstance(raw, (rt.Structure, rt.JointPosition, rt.Array)):
        return detached_facts(raw)
    return Value(raw, spec=list(reference.spec))


def convert_robot_coordinates(robot, operation, inputs, outputs, line, tick):
    def evaluate(context, check):
        values = []
        for index, value in enumerate(inputs):
            if operation == 'POS2JOINT' and index == 6 and robot.model.external_axes == 0:
                if not value.spec or value.spec[0] != 'ARRAY':
                    raise RobotFactsUnavailable('POS2JOINT needs a known external-axis ARRAY shape')
                # The portable model ignores the contents in this case.
                values.append(rt.Array(('ARRAY', 1, ('REAL',))))
                continue
            captured = materialized_value(value)
            if captured is UNKNOWN:
                raise RobotFactsUnavailable(operation+' needs its input data at run time')
            values.append(rt.service_value(captured, line))
        if operation == 'JOINT2POS':
            sizes = rt.array_dimensions(tuple_spec(outputs[2]))
            if len(sizes) != 1 or type(sizes[0]) is not int:
                raise RobotFactsUnavailable('JOINT2POS needs a known external-axis output width')
            if not 1 <= sizes[0] <= 3:
                raise rt.KarelRuntimeError('Portable DH forward output requires 1..3 external-axis slots', line)
        references = [_reference(spec) for spec in outputs]
        context.kinematics(operation, values + references, line, check=check)
        return [_output_facts(reference) for reference in references]

    return _run_portable_model(robot, operation, evaluate, tick, MODEL_SAMPLE_LIMIT)


def convert_config_text(operation, source, outputs, line, *, group=None, formats=None):
    value = materialized_value(source)
    if value is UNKNOWN:
        raise RobotFactsUnavailable(operation+' needs its input data at run time')
    with rt._numeric_scope('pythonic'):
        refs = [_reference(spec) for spec in outputs]
        if operation == 'CNV_CNF_STRG':
            # Supply the caller group explicitly, so invocation needs no program state.
            rt.ExecutionContext(config_text=formats).invoke(None, operation, [value, *refs, group], line)
        else:
            rt.config_text_conversion(operation, value, *refs, line=line, group=group, formats=formats)
        result = [_output_facts(reference) for reference in refs]
    if len(result) == 2 and result[-1].constant != 0:
        result[0] = None
    return result
