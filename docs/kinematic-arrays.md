# Model-backed joint and Cartesian ARRAY conversion

Pythonic source can convert whole ARRAY values between JOINTPOS and
POSITION, XYZWPR or XYZWPREXT at assignments, ordinary routine arguments and
RETURN. Every element uses the existing scalar model/adaptor engine and its
explicit caller-group, selected-frame/tool and current-seed rules. The feature
performs numerical conversion; it does not move a robot or update its supplied
current state.

```karel
VAR joints:ARRAY[2]OF JOINTPOS2 points:ARRAY[2]OF POSITION
ROUTINE roundtrip(value:ARRAY OF POSITION):ARRAY OF JOINTPOS9
BEGIN
  RETURN value
END roundtrip
BEGIN
  -- Supply complete joints and explicit robot model/context before conversion.
  points=joints
  joints=roundtrip(joints)
END
```

The second assignment can also perform the separate zero-only joint-width
narrowing after its returned nine-slot ARRAY has been captured. See the runnable
[forward](../examples/kinematic_array_forward.kl),
[round-trip](../examples/kinematic_array_roundtrip.kl),
[interface](../examples/kinematic_array_interfaces.kl) and
[linked-group](../examples/kinematic_array_project/main.kl) examples for complete
explicit contexts and initialization.

## Capture, preflight and publication

The source expression is evaluated once. The runtime captures independent,
complete, finite ARRAY storage, validates all source POSITION rotation matrices,
and checks target allocation before calling any model adapter. Missing fields,
axes, malformed storage and improper source matrices fail without adapter calls.
Existing rank, shape, CONFIG, external-axis and 32767-scalar-leaf bounds remain.

Elements convert in row-major storage order. Model-specific width, padding,
limits, solution and adapter-output checks apply at each scalar call. The entire
converted ARRAY is staged privately. A failure in any element preserves the
receiver and skips later arguments or assignment-target selectors, as applicable.
Earlier explicit source or host-adapter effects remain; they are neither retried
nor rolled back. A model's failure to solve a point is not proof of geometric
impossibility.

Supported source declarations have one through three logical dimensions and
terminal joint/Cartesian values. Dimensions and declared component boundaries
must match; anonymous formal/result wildcards inherit concrete input dimensions.
[Named ARRAY types and matching nested components](named-array-conversions.md)
now convert into independent receiver schemas. No reshape, component flattening
or inferred allocation is added. Whole STRUCTURE schemas, BYNAME, linked
declaration/definition signatures and raw callback results retain exact contracts.

## Explicit context at each element

Forward conversion requires a supplied forward adapter or model. Loaded models
accept their native joint width or nine slots with zero unused axes. Custom
adapters retain their explicit input/result rules. POSITION and XYZWPR narrow
away forward external metadata; XYZWPREXT retains all three returned values.

Inverse conversion requires supplied current joints as its reference seed.
Neither the receiver's old values nor a previous converted element becomes an
implicit seed. Loaded models accept their native output width or nine slots;
custom adapters must return the declared width exactly. CONFIG, config_ref zero
and source external values follow the scalar policy, with zero external values
for plain POSITION/XYZWPR. Missing group/frame/tool or required seed fails.

All elements use the root caller's group, including inside linked libraries.
Each scalar call reads that group's currently supplied frame/tool/current state.
Adapter inputs are detached; mutating a passed seed or pose cannot change source
or robot storage. An explicit host adapter can replace context state; later
elements observe that replacement under the sequential scalar contract. Such host
effects remain on failure. The engine does not silently update robot state,
selections, calibration or seeds.

## Interfaces, scheduling and observations

A representation-changing argument receives an independent writable converted
ARRAY, including for a bare actual. Changes to a converted formal do not copy
back. Same-type bare arguments retain their existing aliases. RETURN conversion
finishes before active-counter and routine-frame cleanup. Final concrete receiver
shape checks retain their ordinary reference behavior for wildcard declarations.

The conversion is synchronous, with no intermediate handler scan or cooperative
yield inside the ARRAY/model computation. A callee can pause after argument
capture; resume keeps that private value without repeating model calls. Stop or
failure unwinds its frames. Sticky ABORT stops further element conversions and
prevents result publication, including when an adapter catches it or raises a
later error. Existing source FOR/effect guards remain in force.

One value-free service observation describes each requested ARRAY conversion:
KINEMATIC_ARRAY_ASSIGNMENT, KINEMATIC_ARRAY_ARGUMENT or KINEMATIC_ARRAY_RETURN,
with source line and completed/failed outcome. A failed ARRAY observation may
follow earlier completed adapter effects; it is not a per-element/native motion
receipt. Reports add `kinematic_array_conversions` source/target sites and a
`kinematic_array_policy`, with single-evaluation/private-value metadata.

JSON preserves concrete source/result arrays and serializable supplied model
state using existing codecs. It does not save temporary frames, adapters,
callbacks, executable links or physical robot state. The [49 authored regression
cases](../tests/test_kinematic_arrays.py) cover modeled and callback conversions,
preflight, ordering, ownership, contexts, aborts, pause, linkage and persistence.

GET_VAR/SET_VAR remain storage operations: their Cartesian/joint-width prefixes
never infer joint/Cartesian kinematics. Context-free [positional ARRAY changes](positional-arrays.md)
remain separate and need no robot model. Named source-interface coercion,
physical/controller motion, native ABI equivalence and strict mode remain future
or excluded work under the existing support contract.
