# Model-backed routine argument and RETURN conversions

Pythonic source routines can convert between `JOINTPOS` and `POSITION`, `XYZWPR`
or `XYZWPREXT` at ordinary argument and RETURN boundaries. They use the existing
[kinematic assignment](kinematic-assignments.md) engine with an explicitly
supplied robot model or adapters, selected frame/tool and caller task group.
No robot model, joint seed, calibration or physical motion is inferred.

This is a portable Pythonic interface convention. It does not establish native
KAREL routine ABI, configuration-branch selection, controller or physical
acceptance. Public strict mode remains future work; internal legacy source and
runtime guards are retained.

## Private converted arguments and results

```karel
ROUTINE inspect(point: POSITION)
BEGIN
  point.location.x = point.location.x + 10
END inspect

ROUTINE forward_value: XYZWPREXT
BEGIN
  RETURN joints
END forward_value

ROUTINE inverse_value: JOINTPOS
BEGIN
  RETURN point
END inverse_value
```

With declared globals and explicit context, `inspect(joints)` solves forward
kinematics into a private POSITION argument. Changes to that formal do not
change the caller's joint value. An ordinary Cartesian actual supplied to a
JOINTPOS formal similarly creates an independent joint value using inverse
kinematics. Grouping and computed arguments keep the same private ownership.
Each conversion runs once at that expression position, before later arguments
are evaluated. Repeated converted actuals get independent writable cells.

An exact same-type bare variable/field/element remains a reference. Grouped exact
values keep the existing independent data-copy behavior. Forwarding a converted
formal as an exact reference shares only its private cell, without copyback to
the original actual on success, failure, pause/resume or stop.

A differing joint/Cartesian RETURN expression converts into the declared result
type before routine frames unwind. Its result is independent of globals, locals
and formals. Forwarded or recursive returns convert only where the declared
types differ. A failure preserves the caller's assignment destination and skips
its target selectors; earlier source effects retain their usual behavior.

## Explicit model context

Forward conversion requires complete finite joints and a configured forward
adapter. A loaded model accepts its native joint width or JOINTPOS9 with zero
unused slots, and checks its existing joint limits. No nonzero padding is silently
discarded. Custom adapters retain their explicit input and exact result rules.

Inverse conversion requires complete valid Cartesian data and supplied current
joints as its reference seed. Previous destination contents and a current pose
without joints are not seeds. It passes the source CONFIG, config_ref=0 and three
external-axis values to the adapter. A loaded model accepts its native output
width or JOINTPOS9 with zero padding; a custom adapter must return the declared
joint output width exactly. Solver failure is an offline failure to find a
solution, rather than proof of geometric impossibility.

Both directions use the calling root task's group and that group's selected
frame/tool maps, including conversions inside linked library routines. An absent
group, selected frame/tool or required adapter raises. The conversion does not
modify supplied current joints, frames, tools or active selections. Adapter
inputs are detached. Explicit adapter effects outside those input copies remain
the caller's responsibility and are not rolled back or retried.

Forward adapter CONFIG and external-axis outputs are authoritative. XYZWPREXT
keeps all three external values; POSITION/XYZWPR narrow them away under the
existing assignment convention. Inverse conversion supplies zero external
values for plain POSITION/XYZWPR and supplied EXT1..EXT3 for XYZWPREXT. Missing
external fields, nonfinite values, malformed CONFIG and improper POSITION
orientation matrices still fail. No external geometry is inferred from an EXT
field alone. See [joint interoperability](joint-interoperability.md) for model
width, frame/tool and padding details.

## Execution, observations and exact boundaries

Model/adaptor execution is synchronous and retains its existing numerical
iteration bounds. No intermediate handler scan or cooperative yield is inserted
inside a conversion. Completed argument conversions are not repeated when the
callee pauses and resumes. A sticky ABORT prevents result publication, including
when an adapter catches that abort or subsequently raises another error.
Routine frames unwind on failure and stop; earlier completed host effects remain.

Source reports record `kinematic_interfaces` with operation, body/routine,
source/target specs, line/column and single-evaluation/independent-value flags.
RETURN sites also record `before_cleanup`. Existing Pythonic positional argument
and return rows retain `source_type_spec`, declared `type_spec`, `converted` and
`conversion_kind` (`kinematic`, `cartesian`, `joint_width` or `none`). Model-backed interface
service effects propagate through routine calls.

Runtime `service_requests` distinguish `KINEMATIC_ARGUMENT` from
`KINEMATIC_RETURN`. These value-free observations contain only operation, source
line and completed/failed outcome. Ordinary assignment and geometry operations
retain their separate observation names. Context JSON uses the existing supplied
model and concrete variable codecs; it does not serialize temporary routine
cells, executable callbacks or native robot state.

Same-kind JOINTPOS source widths use [checked width conversion](joint-width-conversions.md),
independent of model inverse padding. [Context-free positional ARRAY changes](positional-arrays.md)
now use a separate policy; [model-backed ARRAY source conversions](kinematic-arrays.md)
now apply explicit scalar model rules to [named and matching nested ARRAYs](named-array-conversions.md)
as well as anonymous arrays. Compatible whole STRUCTURE interfaces now follow
[model-backed record conversion](kinematic-records.md). BYNAME references,
linked declaration/definition signatures and raw callback results remain exact. A correctly
declared external result can be converted by an enclosing source expression or
RETURN. POSITION orientation destinations, scalar output references and existing
FOR/effect guards retain their protection. Pure Cartesian interfaces follow the
separate [Cartesian interface](cartesian-interfaces.md) convention.

The authored [kinematic interface tests](../tests/test_kinematic_interfaces.py)
cover all Cartesian representations, model widths/padding, external axes,
ownership, selected frames/tools/groups, copied callbacks, capture order,
failure/abort cleanup, cooperative and linked calls, saved replay and report
evidence. No test requires a controller or opens the GUI.

Source JOINTPOS width differences now follow [joint-width conversions](joint-width-conversions.md)
without a model: pad zeros or discard only zero axes from complete finite data.
This supersedes earlier source width-mismatch exclusions. Linked declarations,
BYNAME and raw adapter results retain their exact contracts.
