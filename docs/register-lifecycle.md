# Register inspection, clearing and port unsimulation

Version 0.86.0 adds POS_REG_TYPE, CLR_POS_REG and CLR_PORT_SIM to the explicit
offline banks. These operations make register and logical-port lifecycles usable
from translated source. No controller connection is required.

## Inspecting a position register

`POS_REG_TYPE(number,group,kind,axes,status)` inspects the stored value without
converting or modifying it. The last three arguments require independent writable
INTEGER storage. On failure, only status changes.

| Stored representation | kind | axes |
| --- | --- | --- |
| POSITION | 1 | 0 |
| XYZWPR | 2 | 0 |
| XYZWPREXT | 6 | 3 |
| JOINTPOS | 9 | Stored width, 1..9 |

The kind codes follow the supplied KAREL manual. Plain Cartesian axes=0 is an
explicit Pythonic choice where the manual defines the count only for joint and
extended representations. XYZWPREXT always stores three extended slots in this
translator, so its count is three; it does not infer physical external axes.
Joint introspection reports the stored width even when GET_JPOS_REG pads its
result to nine slots. A zero axis value still belongs to the stored representation.

Omit the second argument to use `POS_REG_TYPE(number,kind,axes,status)`. The group
then follows the calling root task, including linked library calls. A single source
IN GROUP declaration selects that group; otherwise the supplied robot context's
active group applies, falling back to group 1 when neither is available. An explicit
group overrides the default. Query group zero is invalid.

```python
from karel2py import translate, runtime as rt

joint = rt.JointPosition(("JOINTPOS", 2))
joint.values[:] = [10.0, 20.0]
bank = rt.PositionRegisters(2, {1: joint})
context = rt.ExecutionContext(positions=bank)
namespace = {"__name__": "register_demo"}
exec(translate("""PROGRAM DEMO VAR kind,axes,status: INTEGER BEGIN
POS_REG_TYPE(1,kind,axes,status)
END DEMO""").python_source, namespace)
Program = namespace["Program"]
assert Program(context=context).run() == {
    "KIND": 9, "AXES": 2, "STATUS": 0
}
assert bank.describe(1) == (0, 9, 2)
```

The host method `PositionRegisters.describe(number,group=1)` returns
`(status,kind,axes)`, with None for both data items on failure. Its default group
is explicitly 1 because a bank alone has no calling-task context.

## Clearing position values

`CLR_POS_REG(number,group,status)` removes that group's value. Group zero removes
the selected register from every configured bank group. Other register numbers
and independent register comments remain. Valid absent entries clear successfully,
so repeated clears are harmless. The host equivalent is
`PositionRegisters.clear(number,group=1)`, which returns the status directly.

Portable status codes are 0 success, 1 absent value for inspection, and 2 invalid
register/group. Inspecting an absent register preserves kind and axes outputs.
Clearing an invalid address preserves the entire bank. A later GET of a cleared
register follows its existing missing-value error behavior; no pose is fabricated.
Existing copies of values remain independent and usable.

```python
assert bank.clear(1, 0) == 0
assert bank.describe(1) == (1, None, None)
assert bank.comments.read(1) == (0, "")
restored = rt.ExecutionContext.from_config(context.to_config())
assert restored.positions.read(1) == (1, None)
```

The second block continues the first. Context save/load preserves cleared entries
as absent, retaining other groups and comments. See the
[grouped register example](../examples/register_lifecycle.kl).

## Removing logical port simulation

`CLR_PORT_SIM(type_code,number,status)` uses the same explicit PortBank type-code
mapping as GET_PORT_SIM and SET_PORT_SIM. It removes only the selected simulation
flag. Clearing an already unsimulated valid address succeeds. The last supplied
value and comment remain; clearing a flag neither acquires a hardware value nor
initializes a missing one.

After clearing, SET_PORT_VAL on an input returns portable direction status 4 and
preserves its value. Host updates can still supply input values. Outputs remain
writable. SET_PORT_SIM can enable simulation again with a new initial value.
GET_PORT_SIM reports zero after clearing, and JSON persistence preserves this
state. Invalid addresses return 2; missing context or type-code mapping raises
before status changes. See the [port example](../examples/port_unsimulation.kl)
and [indirect I/O guide](io-and-call-parameters.md).

All three operations retain source-order input/output selection, disjoint outputs,
exact INTEGER output types and ordinary FOR-counter protections. Service request
records contain operation, source line and outcome without bank values. Native
alarms, hardware modes and strict-mode behavior remain outside this contract.
The [semantic ledger](semantics/register_lifecycle_semantics.json) records the
manual locators, authored choices and tests.
