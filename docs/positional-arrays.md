# Positional ARRAY conversions

Pythonic source can convert whole ARRAY values between POSITION, XYZWPR and
XYZWPREXT, or between JOINTPOS widths 1..9. This extends the existing scalar
Cartesian and joint-width conventions. It uses no robot model or implicit frame,
tool, group, current state or physical motion.

| Boundary | Behavior |
| --- | --- |
| Matching-component ARRAY assignment | Matching rank/dimensions; convert every complete element before destination publication |
| Ordinary source argument | Differing terminal representation creates a private writable converted ARRAY; no copy-back |
| Source RETURN | Convert before frame/counter cleanup, then return an independent concrete result |
| GET_VAR/SET_VAR ARRAY | Same-rank row-major prefix conversion; receiver schema, storage identities and unused tail survive |
| Named/component source ARRAY interface | Private conversion preserves receiver schemas; component dimensions and boundaries must match |
| BYNAME, raw callback result | Existing exact contracts remain |

## Source assignments and routines

```karel
VAR original:ARRAY[2]OF XYZWPR result:ARRAY[2]OF XYZWPREXT
ROUTINE shifted(points:ARRAY OF POSITION):ARRAY OF XYZWPREXT
BEGIN
  points[1].location.x=points[1].location.x+10
  RETURN points
END shifted
BEGIN
  -- Initialize both original elements before this conversion.
  result=shifted(original)
END
```

The actual expression is evaluated once and its complete conversion finishes at
that argument position, before later arguments execute. Converted arguments own
independent writable cells, even when the actual is bare storage. Mutations and
forwarding affect that private value; success, failure, pause/resume and stop do
not copy it back. Exact-type bare actuals retain their existing writable aliases;
exact grouped values remain private copies and can retain permitted missing data.

Assignments convert and capture the right side before target selectors run.
Failure in any copied element preserves the receiver and skips those selectors.
Routine RETURN converts before frame and active-counter cleanup. Final concrete
destination-size checks still belong to the destination reference when its
compile-time declaration contains wildcard dimensions.

Supported source arrays have one through three logical dimensions and terminal
Cartesian or JOINTPOS elements. Known dimensions and per-component boundaries
must match. Anonymous formal/result wildcards inherit checked concrete dimensions;
there is no reshape, resize, ragged data or unknown runtime allocation inference.
[Named outer arrays and nested components](named-array-conversions.md) convert
privately into the receiver's schema when their terminal representation changes.
ARRAY fields in named structures can convert separately; whole STRUCTURE schemas
and same-terminal nominal retagging retain their existing restrictions.

## Geometry, completeness and bounds

Every element of a representation-changing source array must be complete, finite
and valid under the existing scalar conversion. POSITION requires a proper unit,
orthogonal, right-handed rotation matrix; CONFIG and source external fields must
be initialized. Cartesian conversion preserves location and CONFIG, uses existing
Euler conventions, zero-fills added EXT1..EXT3 fields and drops those metadata
slots when narrowing. This is a portable representation convention, without
physical external-axis or frame-equivalence inference.

JOINTPOS widening pads zero axes. Narrowing requires all discarded axes to be
zero; no nonzero joint data is silently removed. All source axes must be complete.
The existing 32767-scalar-leaf allocation limit applies to source and converted
storage. Conversion stages independent values before publishing any element.
Same-type partial copies keep their earlier missing-marker behavior.

## Named variable transfers

GET_VAR/SET_VAR keep their existing same-rank prefix policy. Only the copied
prefix changes representation; receiver shape, nominal ARRAY components,
existing element/child identities and its unused tail remain. Named/nested ARRAY
components are visited in row-major order under this explicit bulk-transfer
contract. Every copied positional element must be complete, including fields or
axes omitted by its result. Uncopied source tail contents need not be initialized.
A wholly missing representation-changing source fails rather than clearing the
receiver. Exact-type missing transfers retain status 12311.

SET captures typed source data before later status-selector effects. GET resolves
and captures its named source after output selectors. An invalid copied element
fails before receiver, cache entry or status publication. Incompatible rank or
joint/Cartesian pairs retain status 3. These calls never infer kinematics, even
when an explicit robot model exists. Existing overlap, protected orientation,
CONFIG-subfield and FOR-effect guards remain.

## Linkage, persistence and evidence

Linked declarations and definitions still agree exactly. A matching linked
routine or explicit callback can receive privately converted actual arguments.
Raw callback ARRAY results must match their declared terminal type; source RETURN
or assignment can subsequently convert a correctly declared result. Generic
runtime checked/value/result helpers do not gain implicit array coercion.

Context JSON preserves concrete receiver types, values and POSITION protection
through existing codecs, without storing temporary routine cells or provenance.
Reports add `positional_array_conversions` source/target sites and a
`positional_array_policy`; converted ARRAY argument rows retain the original
source type and mark the conversion. No service request or robot state update
is generated for this context-free operation.

[Explicit-model joint/Cartesian ARRAY conversions](kinematic-arrays.md) now follow
a separate policy. [Numeric ARRAY source conversions](numeric-arrays.md) now use
checked integral narrowing and REAL promotion. [Named/component source conversions](named-array-conversions.md)
preserve receiver schemas; native ABI/controller equivalence remains unverified.
Public strict mode remains a future milestone; legacy guards remain.
See the authored [Cartesian interfaces](../examples/positional_array_interfaces.kl),
[joint widths](../examples/joint_array_widths.kl),
[variable prefixes](../examples/positional_array_variables.kl), and
[linked project](../examples/positional_array_project/main.kl).
