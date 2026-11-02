# Source storage clauses and portable predicates

Pythonic mode accepts explicit VAR storage intent, Boolean unary `+`, Boolean
port-simulation outputs and both position families in range predicates. These are
practical offline equivalents; strict/native equivalence remains future work.

## Declaration storage intent

```karel
PROGRAM SAMPLE
VAR saved IN CMOS:INTEGER
    work,spare IN DRAM:ARRAY[2]OF INTEGER
ROUTINE collect
VAR local_value IN DRAM:INTEGER
BEGIN local_value=7 saved=local_value END collect
BEGIN collect END SAMPLE
```

A comma-separated list may have one `IN CMOS` or `IN DRAM` clause before its
colon, in a global or routine VAR section. Keywords are case insensitive;
comments and physical newlines may separate IN, the pool and the colon. The
ordinary declared type, aliases, capacities and positional `IN GROUP[n]` clauses
continue to apply. Placement on FROM imports, formal parameters, fields and TYPE
aliases is rejected. SHADOW and other pool spellings are not added by this form.

The clause records intent. Globals keep their existing initialization and run
lifetime, and routine locals remain fresh on each call. The runtime does not
allocate native CMOS/DRAM, persist locals or restore values after a reboot.
Context JSON and portable archives remain explicit persistence mechanisms.
Existing `%CMOSVARS`, `%CMOS2SHADOW` and `%SHADOWVARS` defaults are recorded
separately in `Program.source_settings`.

`report['storage_declarations']` lists qualified names in source order, with
`owner` (program or routine), `name`, `pool`, `line` and `column`. Included source
also has physical `source_file`, `source_line`, `source_column` and `include_stack`
fields. The ordinary line/column remains in the expanded source coordinate space.
Generated modules expose an independent immutable tuple:

```python
Program.source_storage_declarations
# ((owner, name, pool, expanded_line, column), ...)
```

There are no live references in this metadata, and changing a report does not
change it. Unqualified variables do not create entries.

## Boolean identity

Unary `+` accepts BOOLEAN and returns the same checked Boolean category. This
supports `ready=+TRUE`, selected Boolean fields/elements, expressions and routine
arguments/results. The operand is evaluated once. Missing values still fail;
Boolean unary minus, Boolean arithmetic and implicit Boolean-number assignments
remain rejected. This policy does not reinterpret Python's `bool` as INTEGER.

## Port simulation flags

`GET_PORT_SIM(port_type,port_no,simulated,status)` accepts an exact writable
BOOLEAN or INTEGER flag output. A BOOLEAN receives TRUE/FALSE; an INTEGER
continues to receive 1/0. Status is an exact INTEGER. Queries share the existing
PortBank simulation state with SET_PORT_SIM and CLR_PORT_SIM, independently of
whether a logical port value has been supplied.

Type IDs still require explicit `type_codes`; no native enum or hardware is
discovered. Invalid type/address requests write status only. Output references
must remain ordinary, writable and disjoint; literals, grouped outputs and
BYTE/SHORT/REAL/STRING flags are rejected. Remote `RGET_PORTSIM` retains its
BOOLEAN signature.

## Range predicates

Both `IN_RANGE(value)` and `J_IN_RANGE(value)` accept POSITION, XYZWPR,
XYZWPREXT and JOINTPOS values. They use the calling root task's selected explicit
robot group. Their shared portable policy depends on the supplied representation:

| Input | Offline check |
| --- | --- |
| JOINTPOS | Every active axis lies within its explicit inclusive joint limit. |
| POSITION / XYZWPR / XYZWPREXT | Call the supplied Cartesian reachability adapter or configured DH model. |

Joint checks require all active axes and exact width, or nine-slot input with
checked zero padding. Nonzero padding, missing/nonfinite axes and width mismatch
are errors, not a false answer. They require no forward conversion, current-state
seed, frame or tool. Cartesian checks receive a checked independent pose,
including external axes. They require an adapter even when joint limits exist.
Adapters must return a synchronous BOOLEAN; exceptions and malformed results
preserve the assignment destination. Coroutine/generator results are closed and
rejected. Input expressions are evaluated once; source locations and ordinary
service outcome records remain available.

This deliberately shares one representation-based predicate policy. It does not
reproduce a native distinction between the two function names, infer a robot,
find all IK branches or certify reachability. A bounded DH solver can return
false when it finds no solution within its configured search budget.

## Executable evidence

The authored examples are [source_storage](../examples/source_storage.kl),
[predicate_boolean](../examples/predicate_boolean.kl),
[predicate_range](../examples/predicate_range.kl) and
[predicate_ports](../examples/predicate_ports.kl). Complete state and service
fixtures accompany them. The linked [storage project](../examples/source_forms_project)
and [predicate project](../examples/predicate_project) exercise external routines,
borrowed variables and explicit shared context. CLI acceptance includes saved JSON
replay and runtime-only generated execution with compiler imports blocked.

The [semantic contract](semantics/source_form_semantics.json) records these
boundaries. No native compiler or controller execution is claimed.
