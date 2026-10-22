# Pythonic POSITION conversions

Version 0.79.0 extends the base contract below with XYZWPREXT operands and
explicit external-axis metadata. The [offline service guide](offline-services.md)
defines the added conversions, propagation rules and remaining boundaries.

Since 0.71.0, whole-value assignments can convert between XYZWPR and POSITION.
This gives POSITION explicit orientation data while retaining its protected
orientation fields.

```karel
PROGRAM POSITION_VALUES
VAR cfg: CONFIG code: INTEGER pose,restored: XYZWPR p: POSITION normal: VECTOR
BEGIN
  CNV_STR_CONF('N R U T, 0, 0, 0',cfg,code)
  pose=POS(10,20,30,0,0,90,cfg)
  p=pose
  p.location.x=12
  p.config_data.cfg_left=TRUE
  normal=p.normal
  restored=p
  WRITE('normal=',normal.x::0::1,',',normal.y::0::1,CR)
  WRITE('restored=',restored.x::0::1,CR)
END POSITION_VALUES
```

The pose supplies a 90-degree Z rotation, so `p.NORMAL` becomes `(0,1,0)`,
`p.ORIENT` becomes `(-1,0,0)` and `p.APPROACH` becomes `(0,0,1)`.
The original pose retains X=10 and its original CONFIG. After the location and
configuration edits, `restored` has X=12 and CFG_LEFT=true with the same rotation.
The output is `normal= 0.0, 1.0` and `restored= 12.0`, each followed by a newline.

The [authored example](../examples/pythonic_position_conversions.kl) includes
environment metadata and independent complete
[snapshot](../examples/pythonic_position_conversions.expected.json) and
[output](../examples/pythonic_position_conversions.write.expected.json) fixtures.

## Mapping the representations

The conversion uses the existing portable
[Z-Y-X frame convention](frame-transforms.md#equivalent-operations):
`R = Rz(r) Ry(p) Rx(w)`, with column vectors and degree angles.

| XYZWPR data | POSITION data |
| --- | --- |
| First rotation column | NORMAL vector. |
| Second rotation column | ORIENT vector. |
| Third rotation column | APPROACH vector. |
| X, Y, Z | LOCATION vector. |
| CONFIG_DATA | Independent CONFIG copy. |

The reverse conversion reconstructs the matrix from these columns and extracts
canonical W/P/R using the existing [angle and gimbal-lock policy](frame-transforms.md#output-angles-and-bounds).
Equivalent rotations can therefore return different Euler numbers. No robot
turn numbers, joint solutions, controller frames or physical configuration
validity are computed.

POSITION starts with unknown orientation until an explicit complete value is
assigned. Conversion from XYZWPR initializes all orientation columns. NORMAL,
ORIENT and APPROACH remain recursively read-only afterward. LOCATION and CONFIG
retain their existing writable fields. A detached VECTOR copy such as
`normal=p.normal` owns writable storage without changing the source POSITION.

## Checked input and matrix policy

Both source representations must be complete, initialized and structurally exact,
with finite REAL leaves and the existing CONFIG field/turn bounds. Unknown axes,
partial records, malformed shapes and non-finite components raise before assignment.

For POSITION-to-XYZWPR conversion, the three orientation columns must have unit
norm, be pairwise orthogonal and have determinant +1. Each check permits an
absolute deviation of at most `1e-9`, an explicit offline tolerance. Scaled,
skewed or left-handed matrices outside that tolerance are rejected. The converter
does not infer missing columns or repair a matrix. This guard applies to the
representation conversion; existing exact-type POSITION copies remain data copies.

Finite locations are retained without imposing POS constructor coordinate bounds.
The result owns independent location, orientation and CONFIG data. Floating-point
rounding and signed zero follow the portable numeric policy.

## Assignment scope and effects

Conversions apply only to whole-value assignments between exact POSITION and
XYZWPR types. Variables, nested record fields, array elements, transparent type
aliases and explicitly typed function/geometry results are supported. Whole
ARRAY assignments retain exact component identities.

Routine parameters and RETURN expressions retain their exact type requirements.
Use a local assignment to convert before passing or returning a value. Since
0.72.0, [FRAME, INV and colon geometry](position-geometry.md) accept both exact
representations, including mixed operands. UNPOS still requires XYZWPR; assign a
POSITION to XYZWPR storage before extraction. There is no POSITION or XYZWPR
cast-call syntax.

The complete source is evaluated and converted once before destination
expressions run. An invalid conversion skips target-index functions and leaves
the assignment destination unchanged. Earlier source effects remain. Whole
replacement preserves captured destination field/CONFIG references and POSITION
orientation protection. Ordinary FOR-counter checks and local-frame cleanup apply.

Reports expose `position_conversions` with body, physical source line/column,
source/target types and target kind. `position_conversion_policy` records the
matrix tolerance, mapping, scope and ownership choices. Exact-type copies do not
create conversion entries.

## Evidence boundary

The reviewed [reference edition](references.md), one-based PDF pages 79 and 481,
permits positional assignment across representations and describes POSITION's
matrix fields and read/write access. This implementation covers only the
POSITION/XYZWPR pair. The column mapping, Euler representation, proper-matrix
guard and tolerance are explicit portable choices checked against independent
quaternion geometry.

There is no implicit conversion for XYZWPREXT, JOINTPOS, VECTOR or CONFIG, no
external-axis handling or kinematics, and no native compiler/controller or
configuration-validity claim. Strict mode remains future work and retains its
previous internal assignment guards.
