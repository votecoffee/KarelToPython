# Indirect I/O, register comments and CALL arguments

Version 0.83.0 extends the explicit offline service context with thirteen
procedures. The implementations share existing banks and use ordinary Pythonic
checks. They do not acquire controller values or change hardware configuration.

| KAREL | Pythonic implementation |
| --- | --- |
| GET_PORT_VAL / SET_PORT_VAL | Read/write the same PortBank storage used by DIN/DOUT and other port expressions. |
| GET_PORT_SIM / SET_PORT_SIM | Inspect a simulation flag or initialize a simulated logical port. |
| GET_PORT_CMT / SET_PORT_CMT | Read/write a bounded comment for a configured logical port. |
| GET_REG_CMT / SET_REG_CMT | Numeric-register comments, independent of numeric values. |
| GET_PREG_CMT / SET_PREG_CMT | Position-register comments, independent of group values. |
| GET_SREG_CMT / SET_SREG_CMT | String-register comments, independent of string values. |
| GET_TPE_PRM | Retrieve an explicitly supplied argument for the calling task. |

## Indirect port access

Indirect procedures take an INTEGER port type and one-based port number. Supply
the code-to-kind mapping explicitly; the manual delegates these codes to an
external include file. The package does not assume a native enum or load that
file. Codes below are authored example choices, not controller constants.

```python
from karel2py import translate, runtime as rt

bank = rt.PortBank(
    {"DIN": 1, "DOUT": 1},
    type_codes={10: "DIN", 20: "DOUT"},
)
context = rt.ExecutionContext(ports=bank)
namespace = {"__name__": "indirect_demo"}
source = """PROGRAM DEMO VAR value,status: INTEGER BEGIN
SET_PORT_SIM(10,1,1,status)
GET_PORT_VAL(10,1,value,status)
SET_PORT_VAL(20,1,value,status)
END DEMO"""
exec(translate(source).python_source, namespace)
Program = namespace["Program"]
assert Program(context=context).run()["VALUE"] == 1
assert bank.read("DOUT", 1) is True
```

SET_PORT_SIM sets an initial value and marks that address simulated. It is not
an enable/disable Boolean: passing zero initializes a simulated port to zero.
GET_PORT_SIM returns INTEGER 0 or 1. SET_PORT_VAL permits output ports and
simulated input ports. Direct source assignment to an input, such as DIN[1],
remains rejected; use SET_PORT_VAL for simulated input updates. Host `update`
can still supply any configured port's value.

The chosen GET_PORT_VAL output contract accepts INTEGER, REAL, BOOLEAN or STRING
references. The manual's parameter line lists STRING while its Boolean details
describe 0/1. This implementation supports both forms, plus natural typed output.
SET_PORT_VAL and SET_PORT_SIM accept those four scalar types too. Boolean ports
use 0/1 or ON/OFF/TRUE/FALSE text. Group ports require nonnegative whole INTEGERs.
Analog ports use finite REALs; converting a fractional value to INTEGER fails
instead of silently dropping its fraction. STRING output uses decimal text and
the normal destination-capacity truncation. These are portable conversions.

| Port status | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Configured port has no supplied value |
| 2 | Unmapped type, unconfigured kind or out-of-range port number |
| 3 | Value cannot be represented by the requested port/output type |
| 4 | Attempt to write an input that is not simulated |

Failures with these statuses preserve other outputs and bank values. Missing
services or a missing type-code mapping raise a source-located context error.
Overlapping output references fail before accessing the bank. As with other
services, earlier completed source statements remain effective on later failure.

Port comments default to empty strings for configured addresses, even before a
value is supplied. SET_PORT_CMT truncates to 16 ASCII characters; GET truncates
to destination capacity. The setter truncation is a Pythonic choice where the
manual requires a comment no longer than 16 characters. Physical assignment,
reverse/complementary modes and hardware effects remain outside this implementation.
Version 0.86.0 adds [CLR_PORT_SIM](register-lifecycle.md#removing-logical-port-simulation)
to remove a logical simulation flag while preserving the last supplied value.

Port JSON configuration adds optional `type_codes`, `comments` and `simulated`:

```json
{"ports":{"counts":{"DIN":1,"DOUT":1},"type_codes":{"10":"DIN","20":"DOUT"},"comments":{"DIN":{"1":"sensor"}},"simulated":{"DIN":[1]},"values":{"DIN":{"1":true}}}}
```

Simulation alone does not invent an initial value when restoring a configuration;
include it in `values` if needed. JSON persistence retains the mapping, comments,
simulation flags and values. See the [indirect I/O example](../examples/indirect_io.kl).

## Register comments

Each bank exposes `.comments.read(number)`, `.write(number,text)` and
`.snapshot()`. NumericRegisters and PositionRegisters use 16 characters;
StringRegisters uses 254. The position-comment capacity is a portable choice.
The source GET/SET procedures use the matching bank. Numeric comments honor
the existing explicit `Program(registers=...)` bank before `context.numeric`.
Comments use register numbers without a group selector; a position comment is
shared across that bank's groups.

Valid registers default to an empty comment regardless of whether their values
are initialized. Comment writes never initialize or replace register values.
Out-of-range reads/writes return status 2 and preserve the other outputs.
Setters truncate to comment capacity; getters truncate to destination capacity.

Bank constructors accept `comments={1: "ready"}`. JSON bank configuration uses
`"comments":{"1":"ready"}`. Empty metadata is omitted when saving, retaining
the older configuration shape. NumericRegisters now exposes `to_config()` for
its count, values and optional comments; `from_config()` accepts that result.
See the [register-comment example](../examples/register_comments.kl).

## Teach-pendant CALL parameters

Supply arguments explicitly with `CallParameters`. No TP program is opened or
executed. The mapping identifies the root program/task and numbers 1 through 10.
INTEGER, REAL and bounded ASCII STRING values retain their types; Boolean values
are rejected.

```python
from karel2py import translate, runtime as rt

context = rt.ExecutionContext(parameters=rt.CallParameters({"DEMO": {1: 42}}))
namespace = {"__name__": "argument_demo"}
source = """PROGRAM DEMO
VAR kind,value,status: INTEGER unused_real: REAL unused_text: STRING[8]
BEGIN GET_TPE_PRM(1,kind,value,unused_real,unused_text,status) END DEMO"""
exec(translate(source).python_source, namespace)
Program = namespace["Program"]
snapshot = Program(context=context).run()
assert (snapshot["KIND"], snapshot["VALUE"], snapshot["STATUS"]) == (1, 42, 0)
assert snapshot["UNUSED_REAL"] == {"uninitialized": True}
```

`GET_TPE_PRM(number,data_type,int_value,real_value,str_value,status)` writes
data_type 1 for INTEGER, 2 for REAL or 3 for STRING, the selected value output
and status zero. Other value outputs stay untouched. An absent or out-of-range
argument writes only status 17042; an explicit empty argument bank supports
that optional-argument pattern. A missing service raises instead of fabricating
arguments. All output references must remain writable, exact and disjoint,
including unused outputs. STRING destinations use normal Pythonic truncation.

Linked routines use their calling task's arguments. Concurrent tasks use their
own root program's mapping. Arguments persist across repeated runs until the
host replaces the service. Source RUN_TASK does not forward a new argument list.
The JSON form is `{"parameters":{"DEMO":{"1":42,"2":1.25,"3":"ready"}}}`.
Context save/load preserves it; `CallParameters.to_config()` returns an
independent JSON-shaped copy. See [CALL arguments](../examples/call_parameters.kl).

The [semantic ledger](semantics/io_parameter_semantics.json) records manual
provenance, the type discrepancy and portable choices. Strict mode, controller
acceptance and native I/O/TP acquisition remain future work.
