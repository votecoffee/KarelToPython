# Joint values across robot services

Version 0.85.0 connects the existing current-state, register and robot-model
interfaces. Bare JOINTPOS values have nine slots in this translator; a supplied
model or limit context can have fewer active axes. These are explicit offline
conventions, without a native unused-axis or controller-equivalence claim.

Version 0.90.0 adds [whole joint/Cartesian assignments](kinematic-assignments.md)
using these same model checks and explicitly supplied context.

## Joint widths and unused slots

Pythonic JOINT2POS, POS2JOINT and J_IN_RANGE accept complete JOINTPOS inputs with
at least as many slots as the configured model or explicit limits require.
Every unused slot must contain zero. Nonzero, uninitialized, Boolean and
nonfinite padding are rejected. Current-joint snapshots use the same rules for
model-derived CURPOS, source inverse conversions and reachability seeds.

CURJPOS and GET_JPOS_REG return independent nine-slot values. A narrow register
value is padded on read without changing its stored type, width or contents.
[Model-backed register getters](position-register-models.md) now also bridge
stored joint/Cartesian representations using the selected register group's
explicit model and selected frame/tool, with supplied current joints for inverse
conversion. These reads keep the original bank value and guard source/status
publication. Matching forms keep their existing paths.
[Mixed register setters](position-register-model-writes.md) now convert joint
inputs for Cartesian setters and Cartesian inputs for SET_JPOS_REG, using
the same explicit register group with staged destination/status publication.

Model POS2JOINT can write any JOINTPOS width from the configured axis count
through nine. It pads unused result slots with zeros and rejects an output that
would omit a modeled axis. Model-backed source conversions use the same rule.
Callbacks without a configured model retain their exact output type contract.
Ordinary source assignments, arguments and RETURN can also use
[checked joint-width conversion](joint-width-conversions.md): complete finite
values widen with zeros, and narrowing requires every discarded axis zero.

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

With those limits, both a two-axis value [5,15] and a padded four-slot value
[5,15,0,0] pass J_IN_RANGE. A modeled active value outside its limit returns FALSE.
Invalid nonzero padding raises rather than being interpreted as an active-axis
range result. See the [limits-only example](../examples/joint_limits.kl).

## External-axis output arrays

DH-backed JOINT2POS accepts a one-dimensional REAL array with one to three
slots, provided it fits every configured external axis. For a single external
axis, ARRAY[1] receives EXT1. For two axes, ARRAY[2] receives EXT1 and EXT2.
Any unused slots receive zero. The XYZWPREXT pose still receives all three
metadata fields. A shorter array can omit only padding. Custom forward
callbacks still return exactly as many values as the output array contains.

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
file. Host edits remain available between cooperative execution steps;
[dedicated source table writes](system-pose-writes.md) and
[active selection assignments](frame-tool-selection.md) now share that context.
These changes do not add a native frame-discovery service.

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
