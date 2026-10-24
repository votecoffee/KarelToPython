# Joint values across robot services

Version 0.85.0 connects the existing current-state, register and robot-model
interfaces. Bare JOINTPOS values have nine slots in this translator; a supplied
model or limit context can have fewer active axes. These are explicit offline
conventions, without a native unused-axis or controller-equivalence claim.

Version 0.90.0 adds [whole joint/Cartesian assignments](kinematic-assignments.md)
using these same model checks and explicitly supplied context.

## Joint widths and unused slots

Model JOINT2POS/POS2JOINT inputs and J_IN_RANGE accept either the exact configured
axis width or a complete JOINTPOS9 with zero in every unused slot. The number of
active axes comes from the model or explicit limits. Other widths are rejected.
Nonzero, uninitialized, Boolean or nonfinite unused values are rejected too;
the runtime does not silently drop additional axis data.

CURJPOS and GET_JPOS_REG return independent nine-slot values. A narrow register
value is padded on read without changing its stored type, width or contents.
Model POS2JOINT can write either its exact model width or JOINTPOS9; unused result
slots are zero. Callbacks without a configured model retain their exact output
type contract. Ordinary whole-value assignment between different JOINTPOS widths
still requires an explicit supported conversion.

This makes paths such as `J_IN_RANGE(CURJPOS(0,0))` and
`GET_JPOS_REG -> JOINT2POS -> POS2JOINT -> SET_JPOS_REG` usable with a narrower
configured model. The [authored conversion example](../examples/joint_interoperability.kl)
uses a two-axis model, a narrow stored register and nine-slot source variables.
All modeled joint values remain finite and normal model limits still apply.

```python
from karel2py import translate, runtime as rt

context = rt.ExecutionContext.from_config({"robot": {
    "dh": [{"a": 100}, {"a": 100}],
    "current": {"joints": {"type": ["JOINTPOS", 2], "value": [0.0, 90.0]}}
}})
namespace = {"__name__": "joint_demo"}
source = "PROGRAM DEMO VAR ready: BOOLEAN BEGIN ready=J_IN_RANGE(CURJPOS(0,0)) END DEMO"
exec(translate(source).python_source, namespace)
Program = namespace["Program"]
assert Program(context=context).run()["READY"] is True
```

Conversions validate padding and results before writing conversion outputs or
status. Existing output alias, FOR-counter, initialization and budget guards
remain. Earlier source effects are retained on a later failure. Padding does not
create physical axes or authorize motion.

## Explicit limits without a model

`RobotContext(joint_limits=[(minimum,maximum),...])` supports one through nine
finite ordered pairs. JSON can now supply this context with or without a current
snapshot, and save/load preserves the limits. DH models keep their limits in
the DH rows; mixing DH rows and a separate joint_limits field is rejected.

```json
{"robot":{"joint_limits":[[-10,10],[-20,20]]}}
```

With those limits, a two-axis value [5,15] or a nine-slot value [5,15,0,0,0,0,0,0,0]
passes J_IN_RANGE. A modeled active value outside its limit returns FALSE.
Invalid nonzero padding raises rather than being interpreted as an active-axis
range result. See the [limits-only example](../examples/joint_limits.kl).

## Frames, tools and linked groups

For loaded DH models, host updates to `frames`, `tools`, `active_frame` and
`active_tool` now affect CURPOS and IN_RANGE consistently. Reachability reads the
current selection each time. JOINT2POS/POS2JOINT continue to use their explicit
frame and tool operands. Frame/tool identifiers are portable INTEGERs 0..32767;
poses must be complete and valid.

```python
from karel2py import runtime as rt
from karel2py.kinematics import pose

context = rt.ExecutionContext.from_config({"robot": {
    "dh": [{"a": 100, "min": 0, "max": 0}],
    "current": {"joints": {"type": ["JOINTPOS", 1], "value": [0.0]}}
}})
# An authored frame translated 50 mm along X; no controller data is inferred.
context.robot.frames[2] = pose(((1,0,0,50),(0,1,0,0),(0,0,1,0),(0,0,0,1)))
context.robot.active_frame = 2
restored = rt.ExecutionContext.from_config(context.to_config())
assert restored.robot.active_frame == 2
assert restored.robot.frame(2).values["LOCATION"].values["X"] == 50.0
```

Saving preserves latest frame/tool values, removals and selections. Unchanged
typed input representations and omitted default identity entries retain their
legacy shape. Invalid maps or active selections fail before replacing a saved
file. Frame/tool edits are host-owned operations; update between cooperative
execution steps. These changes do not add a native frame-discovery service.

Current-state queries, conversions, IN_RANGE and J_IN_RANGE all select the
calling root task's group across linked routines. This prevents a library from
querying one group's current state and converting it with another group's model.
CHECK_EPOS uses this group too unless an explicit group is supplied; its
[position check guide](position-checks.md) covers explicit frame/tool operands.
Source declaration qualifiers retain their existing representation; there is no
native grouped ABI or implicit model discovery.

The [semantic ledger](semantics/joint_interoperability_semantics.json) records
the Pythonic choices and verification. Numerical IK/reachability remains bounded,
and failure is not proof of geometric impossibility. Strict mode, measured robot
state, calibrated geometry, collision checks and controller acceptance remain
separate work.
