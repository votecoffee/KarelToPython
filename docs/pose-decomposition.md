# Pose decomposition

Pythonic `UNPOS` accepts XYZWPR, POSITION and XYZWPREXT values, including grouped
expressions, POS/geometry results and typed routine or service results. JOINTPOS
inputs use the existing explicit forward-model context. It returns six REAL
components and a separate CONFIG copy through writable references:

```karel
PROGRAM parts
VAR
  cfg,result_cfg: CONFIG
  point: POSITION
  x,y,z,w,p,r: REAL
  status: INTEGER
BEGIN
  CNV_STR_CONF('N',cfg,status)
  point=POS(10,20,30,0,0,90,cfg)
  UNPOS(point,x,y,z,w,p,r,result_cfg)
END parts
```

This returns X=10, Y=20, Z=30 and the equivalent canonical rotation W=0, P=0,
R=90. `UNPOS` remains a procedure and has no expression result. Outputs require
six exact REAL references and one CONFIG reference; scalar promotion, output
expressions, grouped output references and protected POSITION/CONFIG fields
retain their ordinary guards.

## Representation choices

| Input | Extraction |
| --- | --- |
| XYZWPR | Preserve its six supplied components and copy CONFIG. |
| XYZWPREXT | Preserve its six supplied components and copy CONFIG; validate but omit external-axis fields. |
| POSITION | Validate its complete proper rotation matrix, convert using the existing Z-Y-X and canonical Euler policy, and copy CONFIG. |
| JOINTPOS | Convert once to XYZWPREXT through supplied forward kinematics, then extract the Cartesian components and CONFIG. |

XYZWPR and XYZWPREXT extraction does not normalize already supplied angle
components or impose POS constructor coordinate/angle bounds. POSITION angles
can differ from a previous Euler representation of the same rotation. The
existing unit-column, orthogonality and right-handed checks use tolerance `1e-9`;
the [POSITION conversion guide](position-conversions.md) describes that policy.

All source fields must be initialized, structurally exact and finite. CONFIG
fields retain their existing Boolean and turn-number checks. Extended fields
must also be valid even though UNPOS has no external-axis outputs. Query those
fields directly when needed. The output CONFIG is independent of the source.

## Source capture and output effects

The complete source expression is evaluated, copied, validated and converted
before output selectors run. Each selector then evaluates once from left to
right. A failed source skips every selector and output write. A later selector
or output guard failure retains prior source/selector effects, with no partial
UNPOS output batch.

All seven outputs must have disjoint storage footprints. The captured source
may also supply output storage. For example, this swaps the source X/Y fields
using the independently captured values:

```karel
UNPOS(pose,pose.y,pose.x,z,w,p,r,pose.config_data)
```

Duplicate outputs, including dynamic indices that select the same cell, remain
errors. Ordinary type, active FOR counter, CONFIG subfield and read-only POSITION
guards apply. CONFIG writes preserve captured destination field aliases. All
seven outputs participate in the existing direct and transitive effect analysis.

## Current state and joint inputs

Unshadowed bare `CURPOS` and `CURJPOS` names, or explicit `CURPOS()` and
`CURJPOS()` calls, now mean the existing queries with both masks discarded:
`CURPOS(0,0)` and `CURJPOS(0,0)`. They use the calling root task's selected group.
Existing two- or three-argument forms retain their mask outputs and explicit
group selection. A single argument remains invalid. Variables, constants and
internal routines retain precedence over the bare built-in names.

`UNPOS(CURPOS,x,y,z,w,p,r,cfg)` reads supplied offline current state. A supplied
Cartesian snapshot requires no model. Otherwise CURPOS needs supplied current
joints and a configured DH model. CURJPOS always requires supplied joints and
does not infer them from a pose. These shorthands work in other value expressions
too; see [current robot state](current-robot-state.md).

JOINTPOS decomposition requires explicit forward kinematics, selected frame/tool,
root group and the existing width, finite-value, padding and limit checks. It
needs no current-joint seed when the input joints are supplied directly:

```python
from karel2py import translate, runtime as rt

context = rt.ExecutionContext.from_config({"robot": {
    "dh": [{"a": 100}, {"a": 100}],
    "current": {"joints": {"type": ["JOINTPOS", 2], "value": [0.0, 90.0]}}
}})
source = """PROGRAM parts
VAR x,y,z,w,p,r: REAL cfg: CONFIG
BEGIN UNPOS(CURJPOS(),x,y,z,w,p,r,cfg) END parts"""
namespace = {"__name__": "pose_decomposition_example"}
exec(translate(source).python_source, namespace)
Program = namespace["Program"]
snapshot = Program(context=context).run()
assert abs(snapshot["X"] - 100.0) < 1e-9
assert abs(snapshot["Y"] - 100.0) < 1e-9
assert abs(snapshot["R"] - 90.0) < 1e-9
assert context.robot.current.joints.values == [0.0, 90.0]
```

Decomposition leaves the robot snapshot unchanged. Forward callbacks receive
independent input values, and the existing sticky-abort behavior applies. See
[joint geometry](joint-geometry.md) for the shared conversion rules and external
kinematic-axis boundaries.

## Reports and evidence

`unpos_calls` records source type/kind, source snapshot policy, output positions
and physical location. `unpos_policy` describes capture, representations and
alias rules. Joint inputs also create `joint_geometry` entries with operation
`UNPOS` and value-free runtime `JOINT_GEOMETRY` records. Cartesian-only UNPOS
creates no service requests. Current queries create their ordinary CURPOS or
CURJPOS records; bare query sites appear in `bare_function_calls`.

The manual documents XYZWPR input and illustrates a current-position expression.
Broader representation inputs, default-mask shorthand and the source snapshot
rules are explicit Pythonic choices. Native reference/write order, controller
acquisition, robot-specific CONFIG validity, status/alarm mapping and strict mode
remain outside this implementation. Preserved internal strict compilation keeps
its previous XYZWPR-storage and disjoint-source/output guards.

See the authored [Cartesian example](../examples/pose_decomposition.kl),
[joint example](../examples/joint_decomposition.kl) and
[semantic ledger](semantics/pose_decomposition_semantics.json).
