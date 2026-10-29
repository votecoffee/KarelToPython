# Model-backed joint and Cartesian assignments

Version 0.90.0 supports whole-value assignments between JOINTPOS and POSITION,
XYZWPR or XYZWPREXT. Conversion uses the explicitly supplied robot model or
adapters, selected frame/tool maps and calling task's group. It does not move a
robot or change the supplied current robot state.

```karel
point=joints
joints=point
```

These statements use the existing JOINT2POS/POS2JOINT implementation. Plain
Cartesian representation changes still use [position conversions](position-conversions.md)
without a robot model. A same-width JOINTPOS copy also needs no model.

## Forward and inverse context

Forward conversion requires a complete finite joint value and a configured
forward adapter. The model validates joint width, unused padding and limits.
It returns independent location/orientation, CONFIG and external-axis values.
XYZWPREXT retains all three external values; POSITION and XYZWPR drop them under
the usual narrowing convention.

Inverse conversion requires a complete source pose and explicitly supplied
current joints as its reference seed. Previous destination contents are not a
seed. The selected adapter receives the source CONFIG, source external axes
(zero for plain POSITION/XYZWPR) and config_ref=0. The bounded numerical model
can fail to find a solution; that does not establish geometric impossibility.

```python
from karel2py import translate, runtime as rt

context = rt.ExecutionContext.from_config({"robot": {
    "dh": [{"a": 100}, {"a": 100}],
    "current": {"joints": {"type": ["JOINTPOS", 2], "value": [0.0, 0.0]}}
}})
source = """PROGRAM DEMO
VAR j,restored: JOINTPOS point: XYZWPR
BEGIN
  j=CURJPOS(0,0)
  point=j
  restored=point
END DEMO"""
namespace = {"__name__": "joint_assignment_demo"}
translation = translate(source)
exec(translation.python_source, namespace)
Program = namespace["Program"]
program = Program(context=context)
result = program.run()
assert result["POINT"]["X"] == 200.0
assert result["RESTORED"]["axes"] == [0.0] * 9
assert context.robot.current.joints.values == [0.0, 0.0]
assert len(translation.report["kinematic_assignments"]) == 2
```

Loaded standard-DH models configure identity frame/tool entries at zero. For
custom adapters, explicitly supply valid frame/tool maps too. Their return
formats match the existing explicit conversion procedures. Forward CONFIG and
three external outputs are authoritative. Callback joint outputs must match
the destination's declared width exactly. Inputs and results are detached.

For a loaded model, joint inputs accept its exact width or JOINTPOS9 with zero
unused slots. Inverse output accepts its exact width or nine slots, padding
unused slots with zero. Other widths and discarded nonzero inputs raise errors.
See [joint interoperability](joint-interoperability.md) for the shared rules.

```python
from karel2py import translate, runtime as rt

context = rt.ExecutionContext.from_config({"robot": {
    "dh": [{"a": 100}, {"type": "prismatic"}], "external_axes": 1,
    "current": {"joints": {"type": ["JOINTPOS", 2], "value": [0.0, 25.0]}}
}})
namespace = {"__name__": "external_assignment_demo"}
exec(translate("PROGRAM DEMO VAR point: XYZWPREXT restored: JOINTPOS BEGIN point=CURJPOS(0,0) restored=point END DEMO").python_source, namespace)
Program = namespace["Program"]
result = Program(context=context).run()
assert (result["POINT"]["Z"], result["POINT"]["EXT1"]) == (25.0, 25.0)
assert result["RESTORED"]["axes"] == [0.0, 25.0] + [0.0] * 7
```

An external kinematic joint is part of the supplied DH model. No external
geometry is inferred from an EXT field alone. Plain-pose inverse conversion
supplies zero external values, so use XYZWPREXT when those values matter.

## Ownership, errors and interfaces

Conversion completes before an assignment's target selector is evaluated.
The RHS is captured once, and array-element/structure-field destinations work
individually. Missing context, invalid values, model failures and invalid results
preserve the destination. Earlier source evaluation and completed host callback
effects remain. Host callback effects are not rolled back or retried.
A sticky ABORT prevents a converted result from being committed.

Each conversion records a value-free KINEMATIC_ASSIGNMENT service observation
with source line and outcome. The report includes source/target types, location,
target kind and the kinematic_assignment_policy. Execution charges the ordinary
assignment checkpoint; numerical solving keeps the model's iteration bound.
No intermediate handler scan or cooperative yield occurs inside the model call.

[Source routine arguments and RETURN values](kinematic-interfaces.md) now use
private joint/Cartesian conversions with the same explicit model and context.
Same-type bare references retain aliases; same-kind joint widths, whole ARRAY
transfers, GET_VAR/SET_VAR, BYNAME, linked declared signatures and raw callback
results retain their exact-type rules.
JOINTPOS still has no source field/index access. Supported geometry expressions
use the explicit [joint geometry](joint-geometry.md) conversion policy since
0.94.0. POSITION orientation destinations remain protected.

Source group declarations select the same root-task context as explicit robot
queries. Linked library conversions use the caller's group, even when the
library declares another group. An absent group/frame/tool raises an error.
Callback and current-state bindings remain explicit host configuration.

The authored [joint roundtrip](../examples/joint_assignment.kl) and
[external-axis roundtrip](../examples/joint_external_assignment.kl) have portable
model inputs and independent expected snapshots. The
[semantic ledger](semantics/kinematic_assignment_semantics.json) records manual
locators and the chosen context/seed rules. Native configuration-branch selection,
calibration, collision checking, physical acceptance and strict mode remain
separate work.
