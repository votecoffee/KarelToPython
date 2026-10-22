# Current robot state and program queries

Version 0.84.0 adds CURPOS, CURJPOS and CURR_PROG to Pythonic mode. Pose/joint
queries use explicitly supplied offline state. They do not read encoders, move
a robot or establish that a snapshot matches a controller.

| KAREL | Pythonic behavior |
| --- | --- |
| CURPOS(limit_mask,travel_mask[,group]) | Independent XYZWPREXT from a supplied pose or a configured DH model's current joints. |
| CURJPOS(limit_mask,travel_mask[,group]) | Independent JOINTPOS9 from supplied joints, with zero padding for unused slots. |
| CURR_PROG / CURR_PROG() | Executing module name as STRING[12], including the library name inside a linked call. |

## Supplied state

`RobotState(position=...,joints=...,axis_limit_mask=0,overtravel_mask=0)` accepts
a complete POSITION/XYZWPR/XYZWPREXT pose, complete JointPosition, or a list/tuple
of one to nine numeric joint values. At least a pose or joints must be supplied.
Inputs and returned properties are copied; incomplete or nonfinite values fail.

Pass it as `RobotContext(current=...)`, or load it through context JSON. A
state-only RobotContext needs no model. CURJPOS requires supplied joints and does
not run inverse kinematics to invent them from a pose. CURPOS requires a supplied
pose, or supplied joints plus a loadable standard-DH model. An arbitrary forward
callback alone does not supply the current frame/tool needed for this query.

```python
from karel2py import translate, runtime as rt

context = rt.ExecutionContext.from_config({"robot": {
    "dh": [{"a": 100}, {"a": 100}],
    "current": {"joints": {"type": ["JOINTPOS", 2], "value": [0.0, 90.0]}}
}})
namespace = {"__name__": "current_demo"}
source = """PROGRAM DEMO VAR result: REAL
ROUTINE sample_x: REAL VAR point: XYZWPREXT
BEGIN point=CURPOS(0,0) RETURN point.x END sample_x
BEGIN result=sample_x() END DEMO"""
exec(translate(source).python_source, namespace)
Program = namespace["Program"]
assert abs(Program(context=context).run()["RESULT"] - 100.0) < 1e-9
```

CURPOS prefers a supplied Cartesian pose even if joints/model data also exist.
That pose is interpreted in the caller-supplied current coordinate context. The
runtime does not reconcile inconsistent pose and joint inputs. Model-derived
poses apply the configured base, active frame and active tool. External model
joints retain their existing kinematic role and populate extended fields.

Current-state forward math accepts joints outside configured limits, allowing
inspection of an outside-limit snapshot. Ordinary JOINT2POS/model.forward calls
still enforce limits by default. No limit or overtravel condition is inferred
from this choice; masks are separate supplied metadata. Mathematical forward
evaluation does not authorize motion to those joints.

CURJPOS's declared result has nine slots, matching bare JOINTPOS in this
translator. Supplied values occupy the first slots; unused slots are zero.
The stored snapshot retains its original width. Padding is a portable convention,
not a claim that additional physical axes exist. Assignment to a narrower
JOINTPOS declaration still requires an explicit supported conversion.
Since 0.85.0, model conversions and explicit range contexts accept this padded
form when unused slots are zero. GET_JPOS_REG uses the same padding convention.
See [joint interoperability](joint-interoperability.md).

## Mask outputs and groups

Each mask argument is an ordinary writable exact INTEGER reference, or literal
zero to discard the output. Parenthesized literal zero is accepted too. The
manual lists output masks but its worked example passes zero while noting that
mask support is release dependent. This implementation supports both forms
without allowing other literal/Boolean expressions as writable outputs.

Masks are supplied integers 0..511, defaulting to zero; they describe at most nine
logical slots. They are not authenticated limit/overtravel measurements. Both
outputs are checked for aliasing before querying state. Missing data, unknown
groups and failed model evaluation leave them untouched. Existing source-order,
FOR-counter and protected-reference guards apply to the mask writes.

An explicit group selects that configured group. Otherwise queries use the
calling root task's group, selected by its single source IN GROUP qualifier or
the context's active group. Linked calls follow that caller group. A flat context
rejects a different explicit group rather than returning the same data for it.
Grouped contexts hold an independent model/current state for each group.

## Updates and persistence

`current.update(position=...,joints=...,axis_limit_mask=...,overtravel_mask=...)`
validates the entire update before replacing any fields. Omitted fields retain
their values. Passing None clears a pose or joint snapshot; clearing both fails.
Updating joints leaves a previously supplied pose intact, so clear that pose
explicitly when switching to model-derived CURPOS behavior.

```python
from karel2py import runtime as rt

current = rt.RobotState(joints=[10.0, 20.0], axis_limit_mask=1)
context = rt.ExecutionContext(robot=rt.RobotContext(current=current))
current.update(joints=[30.0, 40.0], overtravel_mask=2)
restored = rt.ExecutionContext.from_config(context.to_config())
assert restored.robot.current.joints.values == [30.0, 40.0]
assert restored.robot.current.overtravel_mask == 2
```

JSON uses the existing typed pose/joint representation inside `robot.current`:

```json
{"robot":{"current":{"joints":{"type":["JOINTPOS",2],"value":[10.0,20.0]},"axis_limit_mask":1,"overtravel_mask":0}}}
```

Context save/load and RobotState.to_config/from_config preserve the latest state,
including host updates after model loading. Grouped contexts preserve each
snapshot and the active group. Callback closures, call stacks, elapsed motion and
live acquisition are not serialized. Model-only legacy contexts keep their
existing configuration shape. This is value persistence, not program suspension
or robot simulation over time.
Setting `robot.current=None` removes its saved snapshot. Callback-only groups
have no serializable model/state; a mix of serializable and callback-only groups
raises rather than silently dropping a group.

## Program name

CURR_PROG reports the executing program/library module. It differs from the root
task identity used for CALL parameters, error scope and default query group.
Both bare and explicit zero-argument forms work. Internal functions and ordinary
global/local variables or constants keep their usual precedence. Result strings
truncate at 12 characters; assignment can further truncate to destination capacity.

Run the [current-state example](../examples/current_robot.kl) or
[group example](../examples/current_groups.kl) with their supplied context:

```sh
python -m karel2py examples/current_robot.kl -o current.py
python current.py --context examples/current_robot.services.initial.json
```

The [semantic ledger](semantics/current_robot_semantics.json) records manual
references and portable choices. Strict mode, native mask behavior, calibrated
geometry, encoder acquisition and controller/runtime acceptance remain future work.
