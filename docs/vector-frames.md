# VECTOR points in explicit frames

Pythonic mode accepts `pose : vector` when the left operand is POSITION,
XYZWPR, XYZWPREXT or model-backed JOINTPOS and the right operand is VECTOR.
It returns an exact independent VECTOR. This extends
[pose frame composition](frame-transforms.md) without adding VECTOR frames or
implicit conversions between VECTOR and positional types.

```karel
CNV_STR_CONF('N',cfg,status)
pose=POS(10,20,30,0,0,90,cfg)
local_point=VEC(2,3,4)
world_point=pose:local_point       -- (7,22,34)
recovered=INV(pose):world_point   -- (2,3,4)
```

See the authored [Cartesian example](../examples/vector_frames.kl),
[joint example](../examples/joint_vector_frames.kl) and
[linked project](../examples/vector_frame_project/main.kl).

## Python equivalent and chosen interpretation

Given the frame's rotation `R`, translation `t` and local VECTOR components `v`,
the calculation is `world = t + R @ v`. Matrix columns and the portable
[Z-Y-X Euler convention](frame-transforms.md#equivalent-operations) match existing
pose composition. The zero local vector returns the frame origin.

The reviewed manual permits the mixed POSITION/VECTOR relative operator and
states that the left pose supplies the reference frame. This implementation
explicitly treats the VECTOR as a local **point** and includes translation.
That arithmetic choice is not a claim of native behavior for every use of VECTOR.

For a direction that should rotate without translation, subtract the transformed
origin:

```karel
world_direction=(pose:local_direction)-(pose:VEC(0,0,0))
```

Both colon expressions are ordinary evaluations. If the frame is computed by a
function or model whose state can change, capture it once in an explicit pose
variable before using this direction form. No automatic direction/point inference
or units/frame metadata is attached to VECTOR storage.

## Types and composition

| Expression | Result |
| --- | --- |
| POSITION/XYZWPR/XYZWPREXT `: VECTOR` | VECTOR after affine point transform. |
| JOINTPOS1..9 `: VECTOR` | VECTOR after explicit forward conversion and affine transform. |
| `(a:b):v` or `a:(b:v)` | VECTOR, using ordinary colon precedence and rounding. |
| `(a:v).x` | REAL component of the temporary VECTOR result. |
| VECTOR `: pose` or VECTOR `: VECTOR` | Rejected: VECTOR is not a frame. |
| `INV(vector)` or `FRAME(...vector...)` | Rejected; those operations keep their pose inputs. |

VECTOR results contain only X/Y/Z. They do not acquire CONFIG, external axes,
robot group, frame or tool fields. Extended pose metadata is still validated on
the left, but is not carried into the VECTOR result. Joint frames require the
existing [forward model/context](joint-geometry.md); no inverse solve or current
joint seed is introduced, and supplied current state remains unchanged.

Named aliases, record/array elements, internal and linked routine results,
exact VECTOR parameters/RETURN and whole VECTOR arrays retain their ordinary
rules. Result components can be read or passed as value temporaries. Complete
POSITION orientation columns can supply VECTOR values while their source storage
remains protected. There is no automatic VECTOR-to-pose assignment or routine/
RETURN/whole-array coercion.

## Validation, order and ownership

Every operand is evaluated once, left to right. The left frame is validated,
copied and, for joints, forward-converted before the right operand runs. A right
function cannot change the captured frame. Invalid left inputs skip right-side
effects. Invalid right inputs or nonfinite arithmetic retain earlier effects,
skip target-index evaluation and leave the assignment destination unchanged.

The complete frame must pass existing shape, finite-value, CONFIG, turn, proper
POSITION-matrix and external metadata checks even though VECTOR has no CONFIG.
The right VECTOR must have three initialized finite components. No zero pose,
orientation, missing component or external-axis value is fabricated. Existing
Python float rounding, finite result checks and strict-mode internal guards remain.

Results have independent writable storage; ordinary whole replacement preserves
existing destination field aliases. Exact routine types, active-FOR effects,
protected source orientation rules, sticky aborts and routine-frame cleanup are
unchanged. Source projects use the same checked operations across linked modules.

## CLI, reports and evidence

```sh
python -m karel2py examples/vector_frames.kl -o vector_frames.py
python vector_frames.py
python -m karel2py examples/joint_vector_frames.kl -o joint_vector_frames.py
python joint_vector_frames.py --context examples/joint_vector_frames.services.initial.json --state-out joint-state.json
python -m karel2py.project examples/vector_frame_project --entry MAIN
```

Reports include `vector_frame_policy` and source-located `frame_operations` with
exact operand/result types. Result-field type inspection adds no duplicate site.
Joint operands retain `joint_geometry` and value-free JOINT_GEOMETRY service
records, including failures and transitive routine effects.

The source basis is MARRC75KR07091E Rev N sections 3.1.1-3.1.2 and 3.2.4,
one-based PDF pages 78 and 83-84. The
[ledger](semantics/vector_frame_semantics.json) records accepted forms, portable
choices and verification. Tests use independent quaternion calculations, authored
source and supplied models/adapters. No calibration, collision/reachability,
controller runtime or strict equivalence is established.
