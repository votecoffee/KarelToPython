# Pythonic frame transforms

Version 0.79.0 extends the base contract below with XYZWPREXT operands and
explicit external-axis metadata. The [offline service guide](offline-services.md)
defines the added conversions, propagation rules and remaining boundaries.

Since 0.69.0, Pythonic mode supports explicit `XYZWPR : XYZWPR` composition and
`INV(XYZWPR)` inversion. These are offline rigid transforms using Python floats.
Since 0.70.0, [FRAME construction](frame-construction.md) also builds an explicit
XYZWPR frame from three or four point locations. Since 0.72.0,
[POSITION geometry](position-geometry.md) extends all three operations to POSITION
and mixed operands, preserving matrix columns when POSITION is involved.

```karel
PROGRAM FRAMES
VAR cfg: CONFIG code: INTEGER frame,local,world,recovered: XYZWPR
BEGIN
  CNV_STR_CONF('N R U T, 0, 0, 0',cfg,code)
  frame=POS(10,20,30,0,0,90,cfg)
  local=POS(2,3,4,0,0,0,cfg)
  world=frame:local
  recovered=INV(frame):world
  WRITE('recovered=',recovered.x::0::1,CR)
END FRAMES
```

The local translation `(2,3,4)` becomes `(7,22,34)` in the parent frame: rotate it
90 degrees about Z, then add `(10,20,30)`. Applying the inverse frame recovers
`(2,3,4)`, and the example writes `recovered= 2.0` followed by a newline.
The [authored example](../examples/pythonic_frames.kl) includes environment
metadata and complete independent [snapshot](../examples/pythonic_frames.expected.json)
and [output](../examples/pythonic_frames.write.expected.json) fixtures.

## Equivalent operations

Each pose supplies a rotation `R` and translation `t`. Column vectors follow the
explicit portable convention `R = Rz(r) Ry(p) Rx(w)`, with W/P/R in degrees.
Angles are reduced modulo 360 before trigonometry. No controller frame is queried.

| KAREL expression | Pythonic calculation | Result configuration |
| --- | --- | --- |
| `a:b` | `R = Ra Rb`, `t = ta + Ra tb` | Independent copy of `b.CONFIG_DATA`. |
| `INV(a)` | `R = transpose(Ra)`, `t = -transpose(Ra) ta` | Independent copy of `a.CONFIG_DATA`. |

The left pose describes the local frame in its parent; the right pose is expressed
in that local frame. Operand order matters. Colon has the same precedence as
`@` and `#`, above multiplication, and chains associate left to right. Parentheses
override grouping. Rounding can make differently grouped chains differ slightly.
In READ/WRITE items and formats, group a geometric subexpression, as in
`WRITE((a:b).x::0::1,CR)`, to keep the relative operator distinct from invalid
single-colon format syntax.

For pose composition, both operands must be complete, initialized POSITION or XYZWPR values, including
their CONFIG records. INV preserves representation; colon returns POSITION if
either input is POSITION, otherwise XYZWPR. POSITION input/output matrices follow
the [proper-matrix checks](position-geometry.md#validation-evaluation-and-ownership).
Type aliases, variables, record/array fields and internal results work. Fields
of a grouped result, such as `(a:b).x` for XYZWPR, can be read or passed as
private value storage. INV is a fallback: an explicitly declared internal INV
routine keeps its own signature and effects; ordinary declarations named INV
remain usable.

## Output angles and bounds

For XYZWPR results, the rotation is converted to a canonical Euler representation:
P is in -90..90 degrees, with W and R in `[-180,180)`. Equivalent input angles can
therefore produce different W/P/R numbers representing the same orientation.
When `hypot(R00,R10) <= 1e-12`, the chosen gimbal-lock convention sets W to zero
and places the remaining rotation in R. Near that threshold, orientation is an
approximation at floating-point precision.

Exact quarter-turn trigonometric values are retained. Other arithmetic uses
rounded Python floats. Input components and resulting translations must be finite.
The transform does not impose POS constructor bounds on its result: composing two
valid translations can exceed +/-10000000 while remaining valid offline data.
Existing CONFIG field types and turn bounds still apply.

Composition preserves the right configuration as data. Inversion preserves its
input configuration. Neither operation computes robot-specific turn numbers,
joint solutions, reachability or configuration validity.

## Evaluation, ownership and reports

Operands evaluate once from left to right. Each complete value is validated and
copied before the next operand runs, so a right-side function cannot alter the
captured left pose. A failure stops later operand evaluation. Results own their
storage and CONFIG data; existing captured destination references survive whole
record replacement.

Ordinary assignment, parameter, RETURN, active-FOR-counter and cleanup rules
apply. A transform error leaves the assignment destination unchanged while
retaining earlier expression effects. Reports expose source-located
`frame_operations` and the chosen `frame_policy`. Type inspection of result fields
does not duplicate operation entries.

## Evidence boundary

The reviewed [reference edition](references.md), one-based PDF pages 81 and 83-84,
describes precedence and frame-relative composition/inversion. Page 446 describes
INV with POSITION input/output and configuration preservation. The implementation
now supports POSITION and also supplies XYZWPR and mixed-type Pythonic equivalents.
The Z-Y-X convention, canonical/singular Euler choices and composition's CONFIG
copy rule are explicit offline policies. Tests compare the geometry against
independent quaternion calculations; they do not establish native equivalence.

XYZWPREXT uses the [extended metadata rules](portable-projects.md#robot-models-and-extended-poses).
JOINTPOS uses supplied forward context under [joint geometry](joint-geometry.md).
A right VECTOR now selects [affine point transformation](vector-frames.md),
returning VECTOR after rotation and translation. [VECTOR translation frames](vector-translation-frames.md)
add left offsets, VECTOR inversion and FRAME points with an explicit pose origin.
Routine/RETURN/whole-array types remain exact;
controller context discovery and native configuration validity remain unverified.
Strict mode remains a future milestone and retains its earlier internal guards.
