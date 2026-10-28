# Offline I/O configuration

Since 0.101.0, Pythonic programs can inspect and stage logical I/O assignments
and modes, and query an explicit module catalog. These operations use the same
PortBank as [indirect I/O](io-and-call-parameters.md).

| KAREL | Pythonic equivalent |
| --- | --- |
| `GET_PORT_ASG(type,number,rack,slot,physical_type,start,count,status)` | Read an active assignment tuple from the bank's configuration. |
| `SET_PORT_ASG(type,number,rack,slot,physical_type,start,count,status)` | Validate a complete mapping and stage its assignment rows. |
| `GET_PORT_MOD(type,number,mask,status)` | Read the active mode mask, defaulting to zero for a configured logical port. |
| `SET_PORT_MOD(type,number,mask,status)` | Validate and stage a mode mask. |
| `IO_MOD_TYPE(rack,slot,module_type,status)` | Look up supplied module metadata. |

## Explicit topology

Pass a configuration object to `PortBank(configuration=...)`, or include
`configuration` inside the JSON context's `ports` object. Omitting it leaves
these operations unavailable. An explicit empty object permits mode settings
but supplies no physical ports, assignments or module types.

The optional fields are lists; rows accept exactly these fields:

| Field | Row fields |
| --- | --- |
| `physical` | `rack`, `slot`, `type_code`, `kind`, `count` |
| `modules` | `rack`, `slot`, `type` |
| `assignments`, `pending_assignments` | `kind`, `number`, `rack`, `slot`, `type_code`, `start`, `count` |
| `modes`, `pending_modes` | `kind`, `number`, `mask` |

`physical` declares available capacity for a rack/slot/type-code tuple; its kind
is DIN, DOUT, AIN or AOUT. Logical type codes still come from the bank's explicit
`type_codes` mapping. Physical codes may differ, including authored dummy or
memory-image identifiers. Reusing a code with conflicting direction/kind fails
configuration validation. The package does not load native enum/include files.

Rack and slot coordinates are in 0..32767. Type codes and module types are exact
INTEGERs in 0..2147483646. Capacities and ordinary port numbers are in 1..32767.
Explicit OPIN/OPOUT/TPIN/TPOUT panel addresses additionally allow zero and use
the input/output digital family for supplied mappings; no native panel assignment
or channel privilege is inferred. See [controller services](controller-services.md).
Booleans, duplicate rows, unknown fields and incompatible settings are rejected.
Constructor input, `bank.configuration` and saved context snapshots are detached.

Module rows are independent from physical capacities: a capacity does not invent
a board type. Values such as module types 6/7/8 are returned only when explicitly
supplied. IO_MOD_TYPE needs no logical type-code map.

## Deferred changes

SET calls stage pending settings. GET calls read active settings. The host calls
`bank.apply_configuration()` to apply all pending assignments and modes and clear
the pending lists; the return value is the number of assignment/mode rows applied.
Repeated staging replaces only the selected pending rows. Reapplying an empty
pending set returns zero.

This explicit lifecycle follows the manuals' deferred-setting intent. Reading
active values before host application is a portable choice, without a native
GET-before-power-up equivalence claim. A task's `Program.powerup()` or scheduler
POWERUP notification does not apply shared I/O settings. The host application
decides when to apply configuration; there is no operating-system/controller reboot.

```python
from karel2py import translate, runtime as rt

bank = rt.PortBank(
    {"DOUT": 8}, {("DOUT", 1): True}, type_codes={20: "DOUT"},
    configuration={
        "physical": [{"rack": 0, "slot": 1, "type_code": 20,
                      "kind": "DOUT", "count": 64}],
        "modules": [{"rack": 0, "slot": 1, "type": 7}],
    },
)
namespace = {"__name__": "configure_demo"}
exec(translate("""PROGRAM DEMO VAR mask,status: INTEGER BEGIN
SET_PORT_ASG(20,1,0,1,20,17,8,status)
SET_PORT_MOD(20,1,3,status)
GET_PORT_MOD(20,1,mask,status)
END DEMO""").python_source, namespace)
Program = namespace["Program"]
context = rt.ExecutionContext(ports=bank)
assert Program(context=context).run()["MASK"] == 0
assert len(bank.configuration["pending_assignments"]) == 8

# Persist both active and pending settings, then apply independently.
restored = rt.ExecutionContext.from_config(context.to_config())
assert restored.ports.apply_configuration() == 9
assert restored.ports.configuration["modes"][0]["mask"] == 3
assert restored.ports.configuration["assignments"][7]["start"] == 24
assert "modes" not in bank.configuration
assert restored.ports.read("DOUT", 1) is True
```

## Assignment and mode rules

DIN/RDI/RDIN and GIN map to physical DIN; DOUT/RDO/RDOUT and GOUT map to
physical DOUT. Analog ports map to their matching analog direction. Explicit
capacities bound both ends of every assignment. Cross-direction mappings fail.

BOOLEAN SET_PORT_ASG batches contain 1..8 consecutive points. Each becomes a
separate assignment with count 1, so GET on any selected point returns that
point's physical start. A group mapping uses one logical group and 1..32 physical
bits; GET retains its bit width. Analog assignments contain exactly one point.
These are bounded portable conventions. The whole batch is validated before any
pending rows change. Seeded configuration batches use the same normalization.
Mappings may share physical spans; no physical ownership arbitration is inferred.

Mode mask bit 1 records reverse mode, and bit 2 records complementary mode.
Masks are in 0..3. Complementary mode requires an odd BOOLEAN output with a
following configured logical point. Group/analog/input complementary modes fail.
Setting zero clears the active mask on the next host apply.

Configuration is metadata. It does not acquire physical inputs, drive outputs,
copy group bits, invert logical values, complement a neighbor or rescale analog
values. It does not initialize missing values or modify comments, simulation
flags or pulse ownership/deadlines. Existing logical values remain the inputs
and outputs supplied by the host/program. `PortBank.snapshot()` keeps its existing
logical-values-only format; `bank.configuration` exposes configuration separately.

## Status and failure behavior

| Status | Portable meaning |
| --- | --- |
| 0 | Success |
| 1 | No active assignment, or no supplied module at a valid coordinate |
| 2 | Unmapped/out-of-range logical address, or module coordinate outside 0..32767 |
| 3 | Invalid mapping span/direction/capacity, or invalid mode mask/pair |

A nonzero status preserves other outputs and configuration. Missing bank,
configuration or required logical type map raises a source-located context error.
Outputs require ordinary exact writable INTEGER references and cannot overlap.
Inputs and selectors evaluate once in source order. Completed earlier calls and
argument effects remain if a later selector, task or execution budget fails.

The translation report includes `port_configuration_policy`; runtime service
records contain operation, source line and outcome without configuration values.
Saved contexts preserve active and pending settings independently of program
completion. Native code/status tables, physical signal behavior, hardware
discovery, controller acceptance and strict mode remain future work.

See the authored [staging example](../examples/port_configuration.kl),
[failure example](../examples/port_configuration_guards.kl), and
[semantics ledger](semantics/port_configuration_semantics.json).
