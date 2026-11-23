"""Checked quoted robot transfers on isolated discovery storage."""

from . import runtime as rt
from .extended import variable_transfer, variable_value
from .input_robot_values import MODEL_SAMPLE_LIMIT, RobotFactsUnavailable
from .input_value_conversions import UNKNOWN, Value, detached_facts, materialized_value, variable_transfer_policy
from .inspection import describe, missing
from .kinematics import SerialRobotModel
from .storage import tuple_spec


def _facts(spec, value):
    if value is rt.UNINITIALIZED:
        return Value(complete=False, spec=list(spec), uninitialized=True)
    if isinstance(value, (rt.Structure, rt.JointPosition)):
        return detached_facts(value)
    return Value(value, spec=list(spec))


def _model_value(target, value, model_robot, line, tick):
    robot = model_robot()
    if type(robot.model) is not SerialRobotModel:
        raise RobotFactsUnavailable('Quoted joint transfers need the portable DH model')
    samples = 0
    interrupted = None

    def checkpoint():
        nonlocal samples, interrupted
        samples += 1
        try:
            if samples > MODEL_SAMPLE_LIMIT:
                raise RobotFactsUnavailable('Quoted joint transfer exceeded the discovery model-sample limit')
            tick(1 + robot.model.axes)
        except Exception as error:
            interrupted = error
            raise

    checkpoint()
    try:
        return rt.ExecutionContext(robot=robot).kinematic_assignment(
            None, target, value, line, group=robot.active_group, check=checkpoint,
        )
    except rt.KarelRuntimeError as error:
        if interrupted is not None and error.__cause__ is interrupted:
            raise interrupted from None
        raise


def transfer_robot_variable(tables, robot, address, *, getting, target_spec, source, model_robot, line, tick):
    """Return the status and detached GET value. Only a successful SET changes facts."""
    with rt._numeric_scope('pythonic'):
        try:
            endpoint = tables.named_endpoint(robot, address, writing=not getting, line=line)
            reference = endpoint.capture(line)
        except rt.KarelRuntimeError:
            return 1, None

        def check():
            tick()

        whole_pose = not endpoint.selection and not endpoint.path
        if getting:
            expected = tuple_spec(target_spec)
            actual = reference.spec
            raw = reference.raw()
            modeled = whole_pose and expected[0] == 'JOINTPOS'
            policy = variable_transfer_policy(expected, actual)
            if policy is None:
                raise RobotFactsUnavailable('Quoted frame or tool read requires supported receiver storage')
            if not modeled and policy != 'data':
                return 3, None
            if modeled:
                result = _model_value(expected, raw, model_robot, line, tick)
                return 0, _facts(expected, result)
            destination = rt.Reference(expected, {'value': rt.initial_value(expected)}, 'value')
        else:
            if source.spec is None:
                raise RobotFactsUnavailable('Quoted frame or tool write requires known source data and type')
            actual = tuple_spec(source.spec)
            modeled = whole_pose and actual[0] == 'JOINTPOS'
            if not endpoint.prepare(actual, line, model=modeled):
                return 3, None
            destination = endpoint.reference
            expected = destination.spec
            policy = variable_transfer_policy(expected, actual)
            if policy is None:
                raise RobotFactsUnavailable('Quoted frame or tool write requires a supported source type')
            if not modeled and policy != 'data':
                return 3, None
            raw = rt.UNINITIALIZED if source.uninitialized else materialized_value(source)
            if raw is UNKNOWN:
                raise RobotFactsUnavailable('Quoted frame or tool write requires known source data')
            if modeled:
                result = _model_value(expected, raw, model_robot, line, tick)
                tables.publish_named(robot, endpoint, result, line)
                return 0, None

        prepared = variable_transfer(destination, variable_value(actual, raw, line, check=check),
                                     numeric=True, representations=True, records=True, paths=True,
                                     line=line, check=check)
        if prepared is None:
            return 3, None
        result, uninitialized = prepared
        if getting:
            return 12311 if uninitialized else 0, _facts(expected, result)
        tables.publish_named(robot, endpoint, result, line)
        return 12311 if uninitialized else 0, None


def inspect_robot_variable(tables, robot, address, line, tick):
    """Use the stored row's representation for VAR_INFO, including external axes."""
    with rt._numeric_scope('pythonic'):
        try:
            endpoint = tables.named_endpoint(robot, address, writing=False, line=line)
            reference = endpoint.capture(line)
        except rt.KarelRuntimeError:
            return 1, None
        try:
            name, code, shape, length = describe(reference.spec)
        except NotImplementedError:
            return 4, None
        uninitialized = missing(reference.raw(), reference.spec, line, check=tick)
        return 0, (name, code, shape, length, uninitialized)
