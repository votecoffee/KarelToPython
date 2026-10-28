# Joint operands in geometry

Pythonic geometry accepts JOINTPOS operands through the explicit robot model
or forward adapter already used by [kinematic assignments](kinematic-assignments.md).
Each joint operand becomes a complete independent XYZWPREXT in the selected
user frame and tool, then participates in the existing Cartesian operation.

| Operation | Joint operand behavior | Result |
| --- | --- | --- |
| `left:right` | Convert either or both operands, then compose frames | XYZWPREXT when a joint participates |
| `INV(value)` | Forward conversion, then rigid-frame inversion | XYZWPREXT for joint input |
| `FRAME(a,b,c[,origin])` | Convert joint point arguments, then apply the existing axes/origin rules | XYZWPREXT when a joint participates |
| `MIRROR(value,frame,orientation)` | Convert joint value and/or mirror frame, then reflect across the frame's XZ plane | XYZWPREXT |
| `APPROACH(value)` / `ORIENT(value)` | Return positive Z / positive Y from the converted pose | Independent writable VECTOR |
| `left >=< right` | Compare the converted Cartesian poses | BOOLEAN |

The source remains opaque joint storage. Complete values, exact declared width,
model axis count, padded-nine-slot rules, finite components and configured limits
still apply. Unsupported widths, absent models or invalid adapter results raise
errors before assigning the expression result. Ordinary JOINTPOS copies retain
their existing context-free behavior.

## Context and evaluation

Conversion selects the calling root task's group and that group's active
configured frame and tool. A linked library follows its caller's group. Loaded
standard-DH models define identity frame/tool entries at zero; custom adapters
need explicit maps. Cartesian operands must describe coordinates in compatible
frames; no controller frame tags are discovered or inferred.

Forward conversion receives config_ref zero and supplies CONFIG plus three
external-axis values. It needs no inverse seed when the source joints are already
available. `CURJPOS` still requires supplied current state when used to obtain
those source joints. Geometry leaves the supplied current state unchanged.

```python
from karel2py import translate, runtime as rt

context = rt.ExecutionContext.from_config({"robot": {
    "dh": [{"a": 100}, {"a": 100}],
    "current": {"joints": {"type": ["JOINTPOS", 2], "value": [0.0, 0.0]}}
}})
source = """PROGRAM DEMO
VAR joints: JOINTPOS point: XYZWPREXT axis: VECTOR
BEGIN
  joints=CURJPOS(0,0)
  point=INV(joints)
  axis=APPROACH(joints)
END DEMO"""
result = translate(source)
namespace = {"__name__": "joint_geometry_example"}
exec(result.python_source, namespace)
Program = namespace["Program"]
program = Program(context=context)
state = program.run()
assert state["POINT"]["X"] == -200.0
assert state["AXIS"] == {"X": 0.0, "Y": 0.0, "Z": 1.0}
assert context.robot.current.joints.values == [0.0, 0.0]
assert len(result.report["joint_geometry"]) == 2
```

Each joint operand is evaluated, copied and converted once before later operands
or arguments run. A failed conversion skips those later evaluations and the
assignment target selector. Earlier source or callback effects remain. The
existing sticky-abort guard also applies when an adapter catches an abort before
returning. Cartesian-only evaluation rules are retained.

The resulting type is Cartesian. `INV(joints)` performs forward kinematics and
frame inversion; a whole assignment back to JOINTPOS subsequently uses the
ordinary inverse-assignment rules and requires an explicit current-joint seed.
Routine arguments, RETURN types, whole ARRAY transfers and register interfaces
keep their existing exact-type rules. Since 0.96.0, [UNPOS](pose-decomposition.md)
also accepts joint inputs through this forward conversion. POSITION orientation fields remain
protected. A [right VECTOR point](vector-frames.md) now produces a VECTOR after
forward conversion and affine transformation. [VECTOR translation frames](vector-translation-frames.md)
also accept left offsets and FRAME point locations, using the existing explicit
joint conversion for pose origins. Scalar frames and VECTOR-only FRAME origins
remain rejected.

## External axes and comparisons

Joint conversion supplies XYZWPREXT, even when all external values are zero.
The [existing metadata rules](portable-projects.md#robot-models-and-extended-poses)
then apply: INV and MIRROR preserve source external values; colon prefers the
right extended operand, otherwise the left; FRAME uses its selected origin's
external values. A right-hand plain pose widened to XYZWPREXT contributes its
explicit zeros. These are metadata choices, not joint-coordinate algebra.

`>=<` compares Cartesian distance, rotation, CONFIG and external values after
conversion. Supply `pose_tolerance=(distance_mm,angle_deg,check_config)` and
`external_tolerance` (a nonnegative scalar or three-axis tuple) to Program.
Neither tolerance is inferred, including for models with zero external values.
Exact/ordered joint relations and raw joint-distance comparisons remain outside
this interface.

## Reports and evidence

`joint_geometry` records each converted source operand's operation, body, physical
line/column, original type/width and XYZWPREXT result type. Runtime records use
`operation='JOINT_GEOMETRY'` with only source line and completion/failure outcome.
Completed earlier conversions remain recorded if a later operation fails. Requests
reset on a new run and survive pause/resume without replaying finished operands.
`routine_effects.potential_service_requests` propagates through helper calls;
`joint_geometry_policy` describes context, ownership and result conventions.

The authored [geometry example](../examples/joint_geometry.kl) and
[mirror example](../examples/joint_mirror.kl) include independent snapshots and
explicit model inputs. The [semantic ledger](semantics/joint_geometry_semantics.json)
records reference locators and the portable extension. Native overload/result
selection, configuration branches, calibration, collision checking and physical
acceptance remain unverified. Strict mode remains a future milestone.
