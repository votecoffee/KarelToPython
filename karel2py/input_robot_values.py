"""Bounded, read-only evaluation of offline robot data and geometry."""

from . import runtime as rt
from .extended import mirror
from .input_value_conversions import UNKNOWN, detached_facts, materialized_value
from .kinematics import SerialRobotModel


ROBOT_SNAPSHOTS = {'CURPOS': ('XYZWPREXT',), 'CURJPOS': ('JOINTPOS', 9)}
ROBOT_RANGE_QUERIES = {'IN_RANGE', 'J_IN_RANGE', 'CHECK_EPOS'}
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


def current_robot_facts(robot, operation, line, *, tables_known):
    if operation == 'CURPOS' and robot.current is not None and robot.current.position is None:
        if not tables_known:
            raise RobotFactsUnavailable('CURPOS depends on the current frame and tool selection')
        if type(robot.model) is not SerialRobotModel:
            raise RobotFactsUnavailable('CURPOS requires a saved pose or the portable DH model')
    with rt._numeric_scope('pythonic'):
        return detached_facts(robot.current_value(operation, line))


def check_robot_range(robot, operation, arguments, line, *, tables_known, tick):
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
            if not tables_known:
                raise RobotFactsUnavailable(operation+' depends on the current frame and tool selection')
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
