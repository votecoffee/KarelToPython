# Explicit-frame position checks

Pythonic mode supports `CHECK_EPOS(position,uframe,utool,status[,group])` with
an explicitly supplied robot model or position-check callback. It checks a
candidate pose using the supplied frame and tool values, without changing
current robot state or starting motion.

The manual declares an XYZWPREXT target and POSITION frame/tool operands.
Pythonic mode accepts complete POSITION, XYZWPR and XYZWPREXT values for all
three operands. Positions, CONFIG data and orientation matrices retain their
existing validation. JOINTPOS and VECTOR operands are not accepted.

```karel
CHECK_EPOS(target,frame,tool,status)
CHECK_EPOS(target,frame,tool,status,2)
```

The optional group overrides the calling root task's group. Without it, source
`IN GROUP[n]` qualifiers or the supplied context's active group determine the
selection. A linked library uses its calling task's group. Group selection
does not discover hardware or change the active group.

| Portable status | Meaning |
| --- | --- |
| 0 | The supplied model or callback accepts the target. |
| 1 | The supplied model or callback rejects the target. |

Missing context, an unconfigured group, invalid pose data, callback exceptions
or invalid callback results raise a source-located error and preserve the
previous status. Status must be ordinary writable INTEGER storage, including
record fields and ARRAY elements. Active FOR counters remain protected through
routine calls. These values do not map to native controller alarm codes.

## Standard-DH models

Models loaded through `ExecutionContext.from_config` provide this service
automatically. A current pose/joint snapshot is not required:

```json
{"robot":{"dh":[{"a":100,"min":0,"max":0}]}}
```

This authored model has a single joint fixed at zero degrees and a 100 mm link.
With identity frame/tool poses, a target at X=100 mm with identity orientation
passes. X=250 mm fails. The [complete example](../examples/check_positions.kl)
also checks frame/tool offsets and a second group with a prismatic external axis.

The model uses its base transform and the explicit frame and tool operands.
It does not use active frame/tool selections or require corresponding entries
in the frame/tool maps. For example, frame X=10 mm, target X=95 mm and tool
X=5 mm produce a flange target at X=100 mm.

Reachability uses the existing bounded multi-seed numerical search, joint limits
and configured external joints. Only the configured trailing external axes are
constrained by EXT1..EXT3; unmodeled external metadata is not validated. CONFIG
fields are checked as data but do not select calibrated configuration branches.
A failed search does not prove geometric impossibility. JSON save/load preserves
the model and recreates the check adapter.

## Host adapters

`RobotContext(check_position=callback)` accepts a synchronous callback taking
`(position,uframe,utool)` and returning an exact Python `bool`. For example,
an explicitly constructed model can supply the callback directly:

```python
from karel2py import runtime as rt
from karel2py.kinematics import SerialRobotModel, pose

model = SerialRobotModel([{"a": 100, "min": 0, "max": 0}])
robot = rt.RobotContext(check_position=model.reachable)
context = rt.ExecutionContext(robot=robot)
assert robot.check_pose(pose(model.chain([0.])), pose(), pose()) is True
```

`check_pose` is the equivalent host API and returns a Boolean. All three inputs
are validated and detached before the callback, so modifying them cannot alter
the source program's operands. Source arguments and reference selectors are
captured once in left-to-right order; earlier completed effects remain if a
later operation fails.

Integer truth values, awaitables and generators are rejected. Async callbacks
are rejected at construction; accidentally returned coroutine objects are closed
without execution. The existing single-argument `reachable` callback used by
IN_RANGE is independent and is not reinterpreted for this service. Custom Python
callbacks are not serialized; rebind them after restoring context values.

This is an offline model check. It does not guarantee that a controller move
will be free of errors, validate collisions or account for measured robot
calibration. See the [semantic ledger](semantics/position_check_semantics.json)
for source locators and the [joint interoperability guide](joint-interoperability.md)
for related model and group conventions.
