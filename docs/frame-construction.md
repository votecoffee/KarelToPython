# Pythonic FRAME construction

Version 0.79.0 extends the base contract below with XYZWPREXT operands and
explicit external-axis metadata. The [offline service guide](offline-services.md)
defines the added conversions, propagation rules and remaining boundaries.

[VECTOR point inputs](vector-translation-frames.md) now supply point locations
while the first or explicit fourth pose origin supplies CONFIG. An all-VECTOR
FRAME has no configured origin and remains rejected.

Since 0.70.0, `FRAME(a,b,c)` and `FRAME(a,b,c,origin)` construct independent
XYZWPR frames from explicit XYZWPR points. The result can be composed or inverted
with the existing [frame operators](frame-transforms.md). Since 0.72.0,
[POSITION geometry](position-geometry.md) also accepts POSITION and mixed points,
returning POSITION whenever any argument, including the fourth, is POSITION.

```karel
PROGRAM FRAME_POINTS
VAR cfg: CONFIG code: INTEGER a,b,c,built,relocated,world: XYZWPR
BEGIN
  CNV_STR_CONF('N R U T, 0, 0, 0',cfg,code)
  a=POS(10,20,30,0,0,0,cfg)
  b=POS(10,40,30,0,0,0,cfg)
  c=POS(-10,20,30,0,0,0,cfg)
  built=FRAME(a,b,c)
  cfg.cfg_left=TRUE
  relocated=FRAME(a,b,c,POS(100,200,300,0,0,0,cfg))
  world=relocated:POS(2,3,4,0,0,0,cfg)
  WRITE('world=',world.x::0::1,',',world.y::0::1,',',world.z::0::1,CR)
END FRAME_POINTS
```

`built` has origin `(10,20,30)` and orientation `(0,0,90)`. `relocated` keeps
that orientation with origin `(100,200,300)` and the fourth argument's CONFIG.
The local point `(2,3,4)` becomes `(97,202,304)`; the output is
`world= 97.0, 202.0, 304.0` followed by a newline.

The [authored example](../examples/pythonic_frame_constructor.kl) includes
environment metadata and independent complete
[snapshot](../examples/pythonic_frame_constructor.expected.json) and
[output](../examples/pythonic_frame_constructor.write.expected.json) fixtures.

## Constructing the basis

The first three locations define the orientation:

| Component | Pythonic equivalent |
| --- | --- |
| X axis | Normalize `b.xyz - a.xyz`. |
| Z axis | Normalize the cross product of X and `c.xyz - a.xyz`. |
| Y axis | Normalize `Z cross X`; reconstruct normalized Z as `X cross Y`. |
| Origin | Copy `a.xyz`, or the optional fourth location. |
| CONFIG | Copy the first CONFIG, or the optional fourth CONFIG. |

The third point selects the positive half of the XY plane. Its projection along
X does not affect the perpendicular Y direction. The basis is right-handed.
The optional fourth point changes origin and CONFIG without changing the
orientation defined by the first three points. Input orientation values do not define
the basis.

The first and second locations must be at least **10 mm apart**. The third
location must be at least **10 mm from their infinite line**, rather than merely
far from the first point or from the finite line segment. Both bounds are
inclusive and use rounded Python floating-point distances. Coincident,
collinear or undersized geometry raises `KarelRuntimeError`.

Norms use `math.hypot`, avoiding unnecessary overflow from squaring large spans.
Input values, derived differences, cross products and distances must remain
finite. XYZWPR-only results use the same canonical Z-Y-X Euler and gimbal-lock
policy as [composition and inversion](frame-transforms.md#output-angles-and-bounds).
POSITION results retain matrix columns directly.
The constructor does not impose POS coordinate bounds on a copied origin.

## Types, evaluation and ownership

Every Cartesian argument must be a complete, initialized POSITION, XYZWPR or XYZWPREXT value, including
finite orientation and valid CONFIG fields even when those values do not determine
the result. POSITION matrices must pass the [proper-matrix checks](position-geometry.md).
This complete-value guard is an explicit offline choice. JOINTPOS arguments use
supplied forward context under [joint geometry](joint-geometry.md); their presence
makes the result XYZWPREXT. VECTOR points remain blocked.

Arguments evaluate once from left to right. Each pose is validated and copied
before the next expression runs, so later functions cannot change earlier
captured locations or configurations. Geometry checks run after the argument
values have been captured. A geometry failure leaves the assignment destination
unchanged and retains earlier argument effects.

The result owns independent pose and CONFIG storage. Type aliases, record/array
points, function results, private value arguments, RETURN and temporary fields
work with the ordinary copy, reference, FOR-counter and cleanup protections.
Explicit internal routines named FRAME keep their own signatures and effects;
ordinary variables named FRAME remain usable.

Reports include FRAME entries in `frame_operations`, with source line/column,
operand types and one-based `origin_argument` (1 or 4). `frame_policy` records
the chosen construction, capture and configuration behavior. Looking up a
result field does not duplicate the operation entry.

## Evidence boundary

The reviewed [reference edition](references.md), one-based PDF page 398,
describes the point-defined axes, optional origin/configuration and 10 mm
spacing rules. Its signature uses POSITION. The Pythonic implementation
deliberately uses exact XYZWPR input/output and the existing portable Euler
representation. Native pause/error behavior becomes a source-located offline
exception; native error numbers and controller task behavior are not inferred.

Independent quaternion-based tests check rotated bases, including both Euler
singularities. These are offline mathematical checks, with no native compiler,
controller acceptance, frame discovery, external axes, kinematics, reachability
or robot configuration claim. Strict mode remains future work.
