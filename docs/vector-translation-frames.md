# VECTOR translation frames

Pythonic mode accepts VECTOR values as translation-only left frames and as point
inputs to FRAME when an explicit pose supplies the origin and CONFIG. These are
portable extensions. The existing [pose-to-VECTOR point transform](vector-frames.md)
continues to include rotation and translation.

| Form | Result | Portable meaning |
| --- | --- | --- |
| `v1 : v2` | VECTOR | Componentwise translation sum |
| `vector : pose` | Right pose representation | Add VECTOR to location; retain right orientation, CONFIG and external axes |
| `pose : vector` | VECTOR | Existing affine point transform, `t + R @ vector` |
| `INV(vector)` | VECTOR | Independent componentwise negative translation |
| `FRAME(pose,vector,vector)` | Cartesian frame | Pose is origin and CONFIG source; points define the axes |
| `FRAME(vector,vector,vector,pose)` | Cartesian frame | Fourth pose supplies origin and CONFIG; first three points define the axes |

A VECTOR has exactly three finite initialized components. Treating it as a
translation frame means identity rotation by definition; no POSITION, CONFIG or
robot context is synthesized for the vector itself.

```karel
CNV_STR_CONF('N',cfg,status)
pose=POS(10,20,30,0,0,90,cfg)
point=VEC(2,3,4)
translated=point:pose             -- location (12,23,34), R remains 90
world_point=pose:point            -- VECTOR (7,22,34)
recovered=INV(point):translated   -- original pose location and orientation
```

## Translation and inversion

For VECTOR components `v` and right Cartesian location `t`, the location is
`t + v`. Right XYZWPR Euler values are copied exactly rather than decomposed and
canonicalized. POSITION orientation columns remain unchanged and must already
form a proper basis. XYZWPREXT retains all three right external metadata values.
CONFIG is copied as supplied data; no robot turns or reachability are inferred.

VECTOR:VECTOR returns a fresh VECTOR with no pose fields. INV(VECTOR) returns a
fresh negative VECTOR, so `INV(v):(v:point)` recovers a point and
`INV(v):(v:pose)` recovers the pose, subject to ordinary float rounding. Translation
operations do not create implicit VECTOR-to-pose assignment or routine coercions.

A model-backed JOINTPOS on the right uses the existing explicit forward-geometry
context first, then returns translated XYZWPREXT. No inverse solve, controller
state discovery or physical motion occurs. Missing context and joint width/group
errors retain their existing failures.

## FRAME point inputs and metadata

FRAME still constructs the right-handed basis defined by its first three points:
X points from the first to second point, and the third chooses the positive XY
half-plane. Existing minimum separations remain 10 mm for the first/second pair
and 10 mm from the third point to that line.

The origin is the first argument in a three-point call or the fourth argument
when supplied. **That origin must be a complete POSITION, XYZWPR, XYZWPREXT or
model-backed joint pose.** A VECTOR origin cannot borrow CONFIG from another
point. All-VECTOR calls are rejected; supply an explicit fourth pose instead:

```karel
basis=FRAME(VEC(0,0,0),VEC(20,0,0),VEC(0,20,0),pose)
```

This basis has the supplied pose's location and CONFIG, with orientation computed
from the three VECTOR points. The input pose's orientation remains fully checked
even though FRAME derives a new basis. Non-VECTOR axis points retain their full
pose validation too.

Result representation keeps the existing precedence: XYZWPREXT, then POSITION,
then XYZWPR, considering supplied pose operands after any explicit joint forward
conversion. CONFIG and external metadata retain the existing
[frame construction](frame-construction.md) and
[extended geometry](portable-projects.md#robot-models-and-extended-poses) origin rules. VECTOR points contribute
coordinates only; they provide no orientation, CONFIG or external-axis values.

## Evaluation, ownership and evidence

Source operands evaluate once from left to right, and each is checked and copied
before the next operand runs. Invalid earlier vectors/poses skip later effects.
A later routine cannot alter a captured point or translation. Geometry failure
retains earlier effects, skips assignment-target index evaluation and preserves
the old destination.

Every result has independent writable storage. Whole destination replacement
preserves existing component aliases under the ordinary runtime rules. Exact
routine arguments, results, RETURN, arrays, active FOR counters and protected
POSITION orientation storage retain their existing constraints. APPROACH, ORIENT,
pose comparisons and generic frame-value validation remain pose-only.

Reports retain source-located frame operations, exact operand/result types and
joint geometry records. The
[authored translation-frame tests](../tests/test_vector_translation_frames.py)
cover math, metadata, capture order, failure preservation, source projects and
explicit joint adapters; existing frame/vector suites cover unchanged forms.

MARRC75KR07091E Rev N A.6.7 and A.9.17 define pose FRAME and INV. Their reviewed
signatures do not establish these VECTOR overloads. The translation-only and
configured-point choices above are explicit Pythonic conventions. Native type,
Euler, ABI, controller execution and strict-mode equivalence remain unverified;
public strict mode remains a future milestone.
