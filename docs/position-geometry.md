# Pythonic POSITION geometry

Version 0.79.0 extends the base contract below with XYZWPREXT operands and
explicit external-axis metadata. The [offline service guide](offline-services.md)
defines the added conversions, propagation rules and remaining boundaries.

Since 0.72.0, `:`, `INV` and `FRAME` accept complete POSITION values as well as
XYZWPR. Mixed operands are supported. POSITION results use rotation matrices
directly, retaining protected NORMAL, ORIENT and APPROACH columns.

```karel
PROGRAM POSITION_GEOMETRY
VAR cfg: CONFIG code: INTEGER p1,p2,p3,frame,world,recovered: POSITION local,pose: XYZWPR
BEGIN
  CNV_STR_CONF('N R U T, 0, 0, 0',cfg,code)
  p1=POS(10,20,30,0,0,0,cfg)
  p2=POS(10,40,30,0,0,0,cfg)
  p3=POS(-10,20,30,0,0,0,cfg)
  frame=FRAME(p1,p2,p3)
  local=POS(2,3,4,0,0,0,cfg)
  world=frame:local
  recovered=INV(frame):world
  pose=recovered
  WRITE('recovered=',pose.x::0::1,',',pose.y::0::1,',',pose.z::0::1,CR)
END POSITION_GEOMETRY
```

The three points define a frame at `(10,20,30)` rotated 90 degrees about Z.
Its columns are NORMAL `(0,1,0)`, ORIENT `(-1,0,0)` and APPROACH `(0,0,1)`.
The mixed `frame:local` expression returns POSITION at `(7,22,34)`. Applying
the inverse recovers `(2,3,4)`. The final assignment converts to XYZWPR for
scalar output: `recovered= 2.0, 3.0, 4.0` followed by a newline.

The [authored example](../examples/pythonic_position_geometry.kl) adds environment
metadata and has complete independent
[snapshot](../examples/pythonic_position_geometry.expected.json) and
[output](../examples/pythonic_position_geometry.write.expected.json) fixtures.

## Equivalent operations and result types

| Expression | Calculation | Result type |
| --- | --- | --- |
| `a:b` | `R = Ra Rb`, `t = ta + Ra tb`; copy right CONFIG. | POSITION if either operand is POSITION; otherwise XYZWPR. |
| `INV(a)` | `R = transpose(Ra)`, `t = -transpose(Ra) ta`; copy input CONFIG. | Same representation as `a`. |
| `FRAME(a,b,c[,origin])` | Normalize point differences and cross products; copy first or optional fourth origin/CONFIG. | POSITION if any argument, including optional origin, is POSITION; otherwise XYZWPR. |

Each argument must be exactly POSITION or XYZWPR after transparent type aliases
are resolved. POSITION supplies rotation columns NORMAL/ORIENT/APPROACH and
translation LOCATION. XYZWPR uses the existing
[Z-Y-X convention](frame-transforms.md#equivalent-operations). POSITION results
keep matrix columns without intermediate Euler extraction. XYZWPR-only operations
retain their previous canonical angle and gimbal-lock policy.

FRAME retains the [10 mm spacing and origin rules](frame-construction.md).
Input orientations do not determine its axes, but must still be complete and
valid. A fourth POSITION origin selects a POSITION result even if all three
axis-defining points are XYZWPR. Result selection is a Pythonic policy; it does
not establish native mixed-type overload behavior.

## Validation, evaluation and ownership

Operands must be complete, initialized, structurally exact and finite, including
CONFIG fields and existing turn bounds. POSITION columns must have unit norms,
pairwise dot products zero and determinant +1, each within absolute `1e-9`
tolerance. POSITION results receive the same checks. Arithmetic can therefore
reject a result whose accumulated deviation exceeds that tolerance even when
each input passed. No columns are inferred or repaired. Exact-type data copies
retain their existing data-only checks.

Each operand evaluates once from left to right and is validated and detached
before later operands run. Invalid matrices stop subsequent operand effects.
FRAME's distance checks run after all arguments are captured. Failure retains
earlier effects, skips assignment target expressions and leaves the destination
unchanged. Ordinary FOR-counter protections and routine-frame cleanup apply.

Results own independent location, CONFIG and orientation data. POSITION orientation
remains recursively read-only. LOCATION and CONFIG retain their writable fields.
Whole replacement preserves existing destination field references. Reading
`INV(p).LOCATION.X` or `(p:a).NORMAL` uses the inferred result layout. Passing a
bare protected orientation as a reference remains blocked; grouping it as a
value, `take((INV(p).NORMAL))`, creates private writable VECTOR storage.

Parameters and RETURN retain exact types. Whole assignments can still use the
[explicit POSITION/XYZWPR conversion policy](position-conversions.md). Internal
routines named INV or FRAME keep their own signatures and effects.

Reports retain `frame_operations`, now with actual operand and result types,
and `frame_policy` with result selection and matrix checks. FRAME still reports
one-based `origin_argument`. Inspecting result fields does not duplicate entries.

## Evidence boundary

The reviewed [reference edition](references.md), one-based PDF pages 81, 83-84,
398, 446 and 481, describes relative transforms, POSITION frame operations,
point-defined FRAME axes, inversion and POSITION field protection. Independent
quaternion calculations, synthetic invalid matrices and authored fixtures check
the portable implementation. Mixed-type result selection, matrix tolerance,
Euler convention and CONFIG copy choices are explicit offline policies.

XYZWPREXT follows the [extended metadata rules](portable-projects.md#robot-models-and-extended-poses).
JOINTPOS follows the explicit forward-model policy in [joint geometry](joint-geometry.md).
A right VECTOR now selects [affine point transformation](vector-frames.md),
with a VECTOR result. VECTOR left frames and INV/FRAME vector inputs remain
rejected. Controller context discovery and native
compiler/runtime acceptance remain unverified. Strict mode remains a future milestone.
