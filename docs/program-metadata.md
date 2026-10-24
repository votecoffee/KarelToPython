# Program load state and attributes

Pythonic mode supports `LOAD_STATUS`, `GET_ATTR_PRG` and `SET_ATTR_PRG` for
attached Python Programs and explicitly supplied `ProgramAttributes` records.
These queries do not discover controller programs, import Python modules or load
files. `ProgramCatalog` remains an independent, immutable listing service.
The explicit [TeachPrograms store](teach-programs.md) also supplies logical TP
load/position-initialization state, program type, instruction count and four
writable headers. Open/selected record guards apply; this does not load native TP
files or execute their instructions.

```karel
LOAD_STATUS('WORKER',loaded,initialized)
GET_ATTR_PRG('WORKER',AT_COMMENT,number,text,status)
SET_ATTR_PRG('WORKER',AT_COMMENT,0,'converted',status)
```

## Load state

Names are case-insensitive ASCII program identifiers, 1..36 characters. A path,
extension, task alias, routine name or unknown program returns FALSE/FALSE.
Attached source Programs count as loaded, including libraries whose main bodies
have not run and completed/stopped Programs that remain attached. Task-registry
Programs are queried under their source program names.

`initialized` means **any known global content**, including a single initialized
ARRAY element, STRUCTURE field or joint axis. Zero, FALSE and the empty STRING
count as initialized. Constants and routine locals do not count. Unknown BYTE
contents and the SHORT uninitialized sentinel do not count. Every global branch
is checked before either output changes, so valid data cannot hide malformed
storage. Imported global references are followed with cycle/depth guards.

The portable resource convention counts an open FILE, a PATH containing a node
or known header content, and an initialized QUEUE_TYPE. It does not infer queue
initialization from its backing ARRAY. These conventions describe this runtime's
storage model, without claiming native resource initialization behavior.

For duplicate source program names, any known global content across attached
instances counts. Attached data takes precedence over snapshot load flags. The
two LOAD_STATUS output variables are evaluated before the query and written
after it; a first self-query can therefore report FALSE for initialization while
the next query sees those outputs as initialized globals.

## Explicit host metadata

Supply metadata through the generated Program's `context` argument or JSON:

```python
from karel2py import runtime as rt

metadata = rt.ProgramAttributes({
    "WORKER": {
        "loaded": True,
        "initialized": False,
        "attributes": {
            "AT_COMMENT": "ready",
            "AT_PROG_SIZE": 400,
            "AT_SRC_VRSN": 2,
        },
    },
})
context = rt.ExecutionContext(program_attributes=metadata)
context.save("context.json")
```

The JSON field is `program_attributes`, using the same name-to-record mapping.
Optional `loaded`, `initialized` and `active` fields require exact BOOLEANs;
omitted flags default to FALSE. Data can be initialized without loaded code, but
an explicit active snapshot requires `loaded: true`. Metadata alone does not
imply loaded code. Snapshot flags apply only when no matching Program is attached;
an explicit `active: true` still blocks writes. Hosts supply fresh snapshots when
external state changes.

`attributes` accepts the named `AT_*` selectors below, except `AT_PROG_NAME`:
identity comes from the record's key. Names/keys normalize to uppercase;
duplicates, unknown fields and invalid values are rejected. Constructor input,
`record(name)` results and `to_config()` results are detached copies. Context
save/load persists metadata and completed writes, without executable/task state.

## Attribute reads

GET_ATTR_PRG writes only the selected INTEGER or STRING output and then status.
The unused output can remain uninitialized. The attached program type is
`PT_KRLPRG`; its identity is the first 12 characters of the normalized name. An
explicit comment overrides the attached source's `%COMMENT` metadata. Without a
comment in either source, the value is unsupplied, rather than an invented empty
STRING. All other values require explicit metadata:

| Selectors | Value |
| --- | --- |
| `AT_PROG_NAME`, `AT_OWNER`, `AT_COMMENT`, `AT_SRC_NAME` | STRING, native documented capacities 12, 8, 16 and 128 respectively |
| `AT_PROG_TYPE` | `PT_KRLPRG`, `PT_MNE_UNDEF`, `PT_MNE_JOB`, `PT_MNE_PROC` or `PT_MNE_MACRO` |
| `AT_PROG_SIZE`, `AT_ALLC_SIZE`, `AT_NUM_LINE`, `AT_STK_SIZE` | Nonnegative INTEGER |
| `AT_PROTECT` | INTEGER 1 (off) or 2 (on) |
| `AT_BUSY_OFF`, `AT_IGNR_ABRT`, `AT_IGNR_PAUS` | INTEGER 0 or 1 |
| `AT_CRE_TIME`, `AT_MDFY_TIME`, `AT_SRC_VRSN`, `AT_DEF_GROUP`, `AT_STORAGE`, `AT_TASK_PRI`, `AT_DURATION`, `AT_CONTROL` | Supplied INTEGER; no time, size, group, storage or task-policy inference |

The translator provides portable numeric `AT_*` and `PT_*` constants, also
available in `runtime.PROGRAM_CONSTANTS`. Use their names in KAREL source; these
identifiers do not authenticate native enum numbers. Host type values must use
the same portable constants. Host STRING values must fit their documented field
capacity; GET follows ordinary truncation to a smaller destination capacity.

## Attribute writes and failures

SET_ATTR_PRG supports four metadata fields: `AT_OWNER`, `AT_COMMENT`,
`AT_SRC_NAME` and `AT_SRC_VRSN`. STRING writes truncate to the field's capacity.
Writing an inactive attached Program requires an explicit `ProgramAttributes`
service, even an empty one. A missing service raises before metadata/status
mutation. A host-only record can be updated without loading code.

Executing, waiting and paused Programs reject writes. This includes plain
synchronous runs observed inside a host callback, the current program and linked
routine frames. Completed/stopped Programs can be updated. Identity, sizes,
timestamps and unmodeled task-policy writes return status 2; they do not rename
Python namespaces, change priorities or change pause/abort behavior.

| Status | Portable meaning |
| --- | --- |
| 0 | Successful read/write |
| 1 | Unknown program |
| 2 | Unknown selector, or read-only/unmodeled write |
| 3 | Known program, requested read metadata unsupplied |
| 4 | Active program cannot be changed |

An invalid selector takes precedence over program lookup. Error statuses preserve
value outputs and metadata. Missing context, uninitialized input and malformed
typed storage raise `KarelRuntimeError`. Outputs require exact, disjoint writable
references; read-only, CONFIG-subfield and active FOR-counter protections apply,
including transitive routine effects. Alias checks include unused GET outputs.

All arguments evaluate once in source order. Both SET value expressions are
captured and checked even though only the selected value is stored. This is an
explicit Pythonic choice; an unused uninitialized input still raises. Earlier
completed argument effects remain on failure. Updates validate before publishing
metadata and success status. `Program.service_requests` records operation, line
and outcome without attribute values; reports include `program_metadata_policy`.

## CLI example and evidence

```sh
python -c "from pathlib import Path; Path('.local').mkdir(exist_ok=True)"
python -m karel2py examples/program_metadata.kl -o .local/program_metadata.py
python .local/program_metadata.py --context examples/program_metadata.services.initial.json --state-out .local/program_metadata_state.json
```

The runtime package must be installed or on the Python import path. The example
checks supplied readiness, selected outputs, comment/version updates and saved
metadata. It exercises no external controller or source-body discovery.

MARRC75KR07091E Rev N, PDF pages 399–400, 454 and 535–536, documents these
signatures, any-variable initialization, attribute capacities, selected outputs
and native running/readonly errors. This package uses portable status/enum
numbers and supports fewer writes than the controller API. The
[semantic ledger](semantics/program_metadata_semantics.json) records these
choices. Native loading, task-policy writes and controller equivalence remain
outside this offline implementation; strict mode remains a future milestone.
