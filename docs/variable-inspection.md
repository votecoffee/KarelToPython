# Variable inspection

Pythonic `VAR_INFO` and `VAR_LIST` inspect the same explicit global namespaces
used by [GET_VAR/SET_VAR](offline-services.md). The current program, attached
project modules and caller-supplied VariableStore roots are available. Routine
locals, Python attributes and controller discovery are outside this interface.
Queries do not initialize or copy source values, allocate cache entries, or
require a register bank or robot model.

## VAR_INFO

```karel
PROGRAM DEMO
VAR items: ARRAY[2] OF STRING[4]
    missing: BOOLEAN
    label: STRING[12]
    code,capacity,status: INTEGER
    dims: ARRAY[3] OF INTEGER
BEGIN
  items[1]='one'
  VAR_INFO('','items',missing,label,code,dims,capacity,status)
END DEMO
```

The result is `missing=TRUE`, `label='STRING'`, `code=209`, `dims=[2,0,0]`,
`capacity=4`, `status=0`. The second element remains uninitialized. The dimensions
buffer must be a writable one-dimensional ARRAY of exactly three INTEGERs.

An empty program string selects current globals even when a routine has a local
with the same name. Lookup is case-insensitive. Static fields, numeric subscripts
and PATH nodes are supported, for example `PARTS[2].LABEL`, `ROUTE[1].POINT` and
a PATH header field `ROUTE.ID`. Explicit system roots such as `$LIMIT` must be
supplied by the host. Read-only POSITION orientation fields can be inspected.

Metadata uses canonical resolved types: transparent aliases report their base
type, named structures report their name, and JOINTPOS reports its explicit width
(`JOINTPOS9` for the ordinary alias). Arrays report the terminal element type and
all logical dimensions, including named ARRAY components. STRING arrays report
the element capacity. Non-STRING capacity and unused dimensions are zero. The
type-name output follows ordinary bounded STRING truncation.

| Type | Code |
| --- | --- |
| POSITION / XYZWPR / XYZWPREXT | 1 / 2 / 6 |
| INTEGER / REAL / BOOLEAN / VECTOR | 16 / 17 / 18 / 19 |
| SHORT / BYTE / CONFIG | 23 / 24 / 28 |
| FILE / PATH | 29 / 31 |
| JOINTPOS1 through JOINTPOS9 | 25 + 16 times (width minus 1) |
| STRING / named STRUCTURE | 209 / 210 |

The initialization flag uses these portable choices:

- Scalars and data aggregates are missing if any leaf or nested aggregate is
  uninitialized. Known leaves retain schema/type/domain checks, including CONFIG
  turns. This extends metadata inspection to whole ARRAY and user STRUCTURE;
  their direct `UNINIT` exclusions remain.
- BYTE is not initialization-tracked. Its flag is FALSE even for unknown bytes;
  this permits metadata inspection without making unknown contents readable.
- FILE is missing while closed. PATH checks supplied header and node contents;
  an empty PATH without a header is initialized. These are resource-model choices,
  not native allocation flags.
- QUEUE_TYPE has no reviewed type code and returns status 4 without changing
  metadata outputs. Existing queue operations remain available.

Initialized metadata does not establish valid rotation matrices, robot
configuration or reachability. Those operations retain their own checks.

## VAR_LIST

`VAR_LIST(program,pattern,type_code,skip,format,names,count,status)` lists static
root names into a one-dimensional ARRAY of STRING. Empty program means current
globals; `*` can appear in program/name patterns. Matching is case-insensitive.
Bracket patterns and `?` are rejected. Type code 0 includes all declarations;
other codes filter by canonical terminal type, including ARRAY elements.

Results sort by program and variable name. `skip` is a nonnegative zero-based
offset into that ordered result. A call returns at most the names ARRAY capacity;
add the returned `count` to the offset for the next page. No matches returns count
zero. Successful calls clear unused slots to empty STRINGs. The list can include
its own output globals; names are captured before any output changes.

| Format | Stored text |
| --- | --- |
| 1 | Program name, repeated for each matching variable |
| 2 | Variable name |
| 3 | `[PROGRAM]VARIABLE` |
| 4 | Exactly 27 characters: program in columns 1-15, variable in columns 16-27, padded with blanks |

Format 4 rejects identifiers that do not fit those fields. Every returned text
must fit its STRING element capacity; listing does not silently truncate names.
Explicit full-path bindings such as `VALUE[1]` do not become root declarations.

## Failures, observations and embedding

| Portable status | Meaning |
| --- | --- |
| 0 | Success, including an empty list |
| 1 | Variable/path lookup failed, or an exact program is unavailable |
| 2 | Invalid listing type code, skip, format or pattern |
| 3 | Listing text exceeds the caller capacity or fixed-format fields |
| 4 | Metadata type has no supported reviewed code |

Status failures change only status. Invalid types, references, dimensions or
malformed supplied storage raise runtime errors before operation outputs change.
Arguments and selectors evaluate once from left to right; their earlier effects
remain after a later failure. Outputs must be ordinary writable references and
disjoint, including aggregate descendants. An inspected variable can itself be
an output: its metadata is captured before writing.

```python
from karel2py import translate

source = """PROGRAM DEMO
VAR point: VECTOR missing: BOOLEAN label: STRING[12]
    code,capacity,status: INTEGER dims: ARRAY[3] OF INTEGER
BEGIN
  point.x=1
  VAR_INFO('','point',missing,label,code,dims,capacity,status)
END DEMO"""
result = translate(source)
namespace = {"__name__": "inspection_example"}
exec(result.python_source, namespace)
Program = namespace["Program"]
program = Program()
state = program.run()
assert (state["MISSING"], state["LABEL"], state["CODE"]) == (True, "VECTOR", 19)
assert state["DIMS"] == [0, 0, 0]
assert state["POINT"]["Y"] == {"uninitialized": True}
assert program._state.execution.entries == {}
```

`service_operations` reports source locations and `variable_inspection_policy`
records these rules and type codes. Runtime `service_requests` retain only the
operation, source line and completion/error outcome, without variable names or
values. No listing cursor or native entry cache is persisted.

The authored [metadata example](../examples/variable_metadata.kl) and
[paged catalog](../examples/variable_catalog.kl) have independent expected
snapshots. The [semantic ledger](semantics/variable_inspection_semantics.json)
records manual locators and portable choices. Native table order, allocation
flags, status/alarm mappings and controller acceptance remain unverified.
Strict mode remains a future milestone.
