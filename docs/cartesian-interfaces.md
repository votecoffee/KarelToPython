# Pythonic Cartesian routine interfaces

Pythonic routines accept representation conversions among `POSITION`, `XYZWPR`
and `XYZWPREXT` at ordinary argument and RETURN boundaries. The conversion uses
the existing [position conversion](position-conversions.md) geometry. It adds no
robot model, physical motion, frame discovery or native routine ABI claim.
Public strict mode remains future work; internal legacy cross-type interface
guards are preserved.

## Arguments and ownership

| Actual and formal types | Bare ordinary storage | Grouped/computed value |
| --- | --- | --- |
| Same Cartesian type | Existing writable reference | Existing independent value copy |
| Differing Cartesian types | Checked independent converted value | Checked independent converted value |

All six directed pairs among the three Cartesian types are supported. A
converted argument has a private writable cell of the formal's type. Changes to
that cell, its location or CONFIG do not copy back to the caller, including on
failure, pause/resume or stop. An exact bare reference still changes the caller.
Forwarding a converted formal as an exact reference shares only that private
cell. Repeated conversions of the same source create independent cells.

```karel
PROGRAM CARTESIAN_INTERFACE
VAR
  cfg: CONFIG
  status: INTEGER
  original: XYZWPR
  result: XYZWPREXT
ROUTINE shifted(value: POSITION): XYZWPREXT
BEGIN
  value.location.x = value.location.x + 10
  RETURN value
END shifted
BEGIN
  CNV_STR_CONF('N',cfg,status)
  original = POS(1,2,3,0,0,90,cfg)
  result = shifted(original)
  -- original.x remains 1; result.x is 11, result.ext1..ext3 are zero
END CARTESIAN_INTERFACE
```

The source expression is evaluated once. A cross-type argument is converted and
captured before later arguments run. Later changes to the original pose do not
change the captured cell. Invalid conversion prevents later argument effects and
callee entry. Earlier explicit effects retain their normal behavior.

## RETURN and geometry checks

A RETURN expression of a differing Cartesian type is converted into the
declared result type before routine frames unwind. The returned record is
independent of globals, locals and formal storage. Forwarded or recursive returns
can convert at each declared boundary. Assignment target selectors run after the
result has been evaluated and captured; a failed conversion skips those selectors
and preserves the assignment destination.

Cross-type conversion requires a complete source, including valid CONFIG and all
three external-axis fields of a source XYZWPREXT. Finite known numeric fields and
the existing proper POSITION rotation checks remain required. POSITION columns
must form a unit, orthogonal, right-handed matrix under the existing tolerance.
There are no guessed orientation or CONFIG defaults. These checks apply even
when a target representation will omit some source fields.

Conversions use the existing portable `Rz(r) Ry(p) Rx(w)` convention and canonical
Euler extraction. Cartesian location and CONFIG are copied. Narrowing from
XYZWPREXT discards external-axis fields; widening to XYZWPREXT initializes its
three added axis fields to zero, as existing Cartesian assignment conversion
does. No external-axis units, frame calibration, robot group or joint solution
is inferred. Values must already describe the intended common coordinate frame.

Exact-type value arguments and returns retain their existing data-copy behavior,
including permitted partial data. The full geometry guard applies to a
representation change; this feature does not tighten every exact-type copy.
Same-type XYZWPREXT copies retain their external-axis values. Converted POSITION
results retain read-only orientation descendants; location/CONFIG access and
existing output protections keep their current rules.

## Linked routines, callbacks and exact boundaries

Ordinary source calls to explicitly linked routines convert actual arguments to
their declared Cartesian formal types. Linked declarations and definitions must
still agree exactly. Explicit Python callbacks receive the declared reference
type, with the same private-versus-alias ownership rules at the source call site.
Their raw result must still match their declared result type. A correctly declared
Cartesian callback result can be converted by an enclosing source RETURN or
assignment; returning a different raw record type from the callback is rejected.

`BYNAME` remains an exact typed reference operation. It does not turn a mismatched
Cartesian variable into a private converted value. INTEGER/scalar output
references, protected POSITION orientation arguments, CONFIG fields and ordinary
FOR-effect guards are unchanged. Whole ARRAY element types, same-kind JOINTPOS
widths and named aggregate interfaces remain exact.
[Joint/Cartesian source routine conversions](kinematic-interfaces.md) now use
explicitly supplied models/adapters and the existing seed/frame/tool rules.
Plain Cartesian representation conversion still needs no robot context.

Context JSON stores the converted destination's concrete type, values and
orientation protection through the existing codec. It does not save temporary
routine cells or add frame/group provenance. Reports retain the declared target
in `type_spec` and record `source_type_spec` plus `converted` in Pythonic
`positional_value_arguments` and `positional_returns`. Exact copies have
`converted: false`; cross-type conversions have `converted: true`.

The authored [Cartesian interface tests](../tests/test_cartesian_interfaces.py)
cover all six directions, independent quaternion geometry, capture/failure order,
internal/linked/callback calls, saved-state behavior and retained legacy guards.
See [partial aggregate values](partial-aggregate-values.md) for the separate
same-type data-copy policy.
