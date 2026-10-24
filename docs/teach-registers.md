# TP caller-local registers

Version 26.1024.151618 adds twelve register calls using an explicit caller association in `TeachPrograms`.
These model the local registers of a TP program that calls a KAREL root. They
retain separate numeric, string and grouped position banks in each logical TP
record. The association is supplied by the host or context JSON; no TP execution,
pendant, controller discovery or native call-stack inference occurs.

## Source calls

| Call | Supported signature |
| --- | --- |
| GET_TPE_REG | `(number, real_flag, int_value, real_value, status)` |
| SET_INT_TPE_REG / SET_REAL_TPE_REG | `(number, value, status)` |
| GET_TPE_STR_REG / SET_TPE_STR_REG | `(number, text, status)` |
| GET_TPE_POS_REG / GET_TPE_JPOS_REG | `(number, status [, group])` functions |
| SET_TPE_POS_REG / SET_TPE_EPOS_REG / SET_TPE_JPOS_REG | `(number, position, status [, group])` |
| TPE_POS_REG_FRM | `(number [, group], uframe, utool, status)` |
| TPE_POS_REG_TYPE | `(number [, group], representation, axes, status)` |

The two functions return independent XYZWPREXT or padded JOINTPOS9 values.
Metadata queries also accept omission of the middle group, following the
manual's default-group description. Omitted groups use the calling KAREL root's
group, or portable group 1. Explicit groups must belong to the supplied store.
Each position write changes only its addressed group.

## Explicit callers and banks

```python
from karel2py import runtime as rt

bank = rt.TeachPrograms(
    {"TP_CALLER": {
        "numeric_registers": {"1": 42, "2": 1.25},
        "string_registers": {"1": "authored"},
    }},
    callers={"MAIN": "TP_CALLER"},
    groups=(1, 2),
    register_limit=100,
    string_register_limit=10,
    position_register_limit=50,
    string_capacity=80,
)
context = rt.ExecutionContext(teach_programs=bank)
assert bank.read_register("main", 1) == (0, 42)
assert bank.write_register("MAIN", 2, 2.5) == 0
```

Caller and TP names use the [TP store's identifier rules](teach-programs.md).
`callers` maps stable KAREL root program names to existing TP records. Linked
FROM routines use their calling root, even if the library has its own binding.
Renaming a scheduler binding leaves that root program identity intact. Multiple
roots can explicitly share one TP record or address separate records. The
selected program, OPEN_TPE handles, GET_TPE_PRM arguments and ordinary global
register banks do not select a caller implicitly.

`bind_caller(karel_name, tp_name)` updates a binding after validating both names
and the target. It returns 0 on success, 1 for an absent target and 2 for an
invalid identifier; failure keeps the old binding. The `callers` property is a
detached mapping. Bindings are offline configuration, not native call frames.

Each record can contain `numeric_registers` and `string_registers` mappings with
canonical positive decimal string keys. Numeric values are finite initialized
INTEGERs or Pythonic REALs; booleans, NaN and infinities are rejected. String
initializers must be ASCII and fit the configured capacity. Source string writes
truncate to that capacity, matching the ordinary offline string-bank convention.
String reads require the complete result to fit the destination; a small
destination receives status 8 and retains its prior value.

The three register limits default to 32767 and accept 1..32767. String capacity
defaults to 254 and accepts 1..254. These are portable limits rather than a claim
about a controller's configured bank sizes. Empty slots are uninitialized,
including after CREATE_TPE. GET_TPE_REG changes the flag and only the matching
numeric output; the other numeric output retains its previous value.

## Local positions

`position_registers` is a separate list of `group`, `number`, checked runtime
`value` and optional `uframe`/`utool` rows, with the same typed JSON encoding as
the program's `positions`. These two lists are independent: local registers do
not affect program point comments, AVL_POS_NUM or instruction deletion.

Cartesian setters accept complete POSITION/XYZWPR/XYZWPREXT and normalize to
XYZWPR or XYZWPREXT. Extended writes and reads preserve external slots; narrowing
drops them and widening plain data initializes them to zero. Joint writes retain
their exact width. There is no implicit pose/joint kinematics. Joint getters pad
to nine axes; stored width remains available through TPE_POS_REG_TYPE.

Type queries return 1 for POSITION, 2 for XYZWPR, 6 for XYZWPREXT or 9 for JOINTPOS.
Axis count is zero for plain/matrix data, three external metadata slots for
XYZWPREXT, or the stored joint width. Frame/tool queries return supplied IDs.
Source replacement preserves existing IDs; new records start at 0/0. Host
`write_register(..., kind="position", group=..., uframe=..., utool=...)` can
supply explicit IDs in 0..32767. No active robot frames/tools are inferred.

Host `read_register(caller, number, kind="numeric", group=1, owner=None)` returns
`(status, value)`. Kind is `numeric`, `string` or `position`. A position value is
a detached row containing checked `value`, `uframe` and `utool`. The matching
`write_register(caller, number, value, ...)` returns status and checks complete
values before replacing data. The host group default is always 1.

## Access, persistence and failures

Local register calls do not require an OPEN_TPE handle. Foreign handles on the
target TP record still apply their explicit reject masks: read uses read access,
write uses read/write access. A calling root's own handles do not block it. Host
calls accept an owner token; omitted owner means the shared host owner described
in the TP store guide. Selection alone does not prevent local data access.

Completed updates survive pause, completion, failure and stop. JSON retains
bindings, limits and all bank values, while live handles/owners remain omitted.
COPY_TPE deep-copies the three banks along with program data; it keeps caller
bindings unchanged. Overwriting an eligible destination changes the values seen
by its existing bindings. Local values contribute to offline LOAD_STATUS
initialization. No local register operation creates a task or program.

| Status | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Numeric/string slot absent |
| 2 | Invalid register/group address or incompatible position representation |
| 4 | Foreign TP handle rejects access |
| 8 | String destination too small; output preserved |
| 9 / TPE_NO_CALLER | No explicit calling-root binding |
| 17038 / TPE_UNINITIALIZED | Local position absent |

These are portable statuses; 17038 follows the manual's uninitialized TP position
sentinel. Procedure failures preserve data outputs. Failed position functions
publish status then raise without replacing the assignment target, matching
existing offline position getters. Missing services, invalid types, incomplete
values or bad numeric/matrix contents raise rather than fabricate values.
Inputs/selectors evaluate once in source order; exact disjoint output checks and
transitive FOR-counter protection remain in effect.

```sh
python -m karel2py examples/teach_registers.kl -o registers.py --report registers-report.json
python registers.py --context examples/teach_registers.services.initial.json --state-out registers-state.json
```

The report's `teach_register_policy` describes selection and retained boundaries.
The [semantic ledger](semantics/teach_register_semantics.json) records source
provenance and portable choices. Authored tests, the all-call fixture, saved JSON
replay and runtime-only CLI checks establish offline behavior. Native TP register
allocation, call nesting, alarm encodings and controller equivalence remain
unverified; strict mode remains a future milestone.
