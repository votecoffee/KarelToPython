# Program listing

Pythonic `PROG_LIST` lists the current program, attached KAREL programs, registered
task Programs and optional explicit program metadata. It supports type filters,
star patterns, bounded result arrays and pagination. Listing needs no controller
or filesystem adapter.

Load flags and mutable attributes use the separate
[program metadata service](program-metadata.md). Catalog entries alone do not
count as loaded programs or provide attribute/readiness records.

```karel
PROGRAM browse
VAR
  names: ARRAY[4] OF STRING[39]
  count,status,cursor_no: INTEGER
BEGIN
  cursor_no=0
  PROG_LIST('*',7,0,2,names,count,status,cursor_no)
END browse
```

## Program context

Current and attached Programs appear as `PC` entries, including libraries that
have not run. Programs explicitly bound in a task registry also appear under
their source program name; task aliases do not become program names. A stopped
or completed Program stays attached. Identical name/type pairs collapse.

`ProgramCatalog` supplies immutable listing metadata for other programs:

```python
from karel2py import translate, runtime as rt

catalog = rt.ProgramCatalog([
    {"name": "WELD", "type": "TP"},
    {"name": "SETTINGS", "type": "VR"},
])
context = rt.ExecutionContext(programs=catalog)
source = """PROGRAM browse
VAR names: ARRAY[4] OF STRING[39] count,status,cursor_no: INTEGER
BEGIN
  cursor_no=0
  PROG_LIST('*',7,0,1,names,count,status,cursor_no)
END browse"""
namespace = {"__name__": "program_listing_example"}
exec(translate(source).python_source, namespace)
Program = namespace["Program"]
snapshot = Program(context=context).run()
assert snapshot["NAMES"] == ["BROWSE", "SETTINGS", "WELD", ""]
assert snapshot["CURSOR_NO"] == 3
assert context.programs.to_config() == [
    {"name": "SETTINGS", "type": "VR"},
    {"name": "WELD", "type": "TP"},
]
```

Catalog names are ASCII identifiers of 1 through 36 characters. Names and types
normalize to uppercase. Supported types are `VR`, `JB`, `PR`, `MR`, `TP` and `PC`.
Duplicate name/type pairs in a supplied catalog are rejected; one name may have
multiple types. Supplied dictionaries and exported JSON are detached copies.

Catalog entries provide listing metadata only. They do not create variables,
load code, link routines or create runnable tasks. Variable bindings, external
callbacks and filenames are not interpreted as loaded programs. A supplied
`VR` entry does not require a variable namespace.

Context JSON accepts the same list under `programs`. `to_config()`, `save()` and
`load()` preserve that explicit metadata. Attached Programs and tasks must be
attached again after loading saved service state. An omitted catalog preserves
the previous context JSON shape; an explicitly empty catalog saves `programs: []`.

## Signature and filters

`PROG_LIST(pattern,type,skip,format,names,count,status[,cursor])` takes seven
required arguments and an optional eighth cursor. `names` is a writable
one-dimensional `ARRAY OF STRING`; count, status and cursor require exact writable
`INTEGER` storage. Pattern, type, skip and format are inputs.

The reviewed manual's syntax line omits status, while its parameter table lists
both output status and an optional input/output index. This implementation uses
the table's seven-plus-optional-eighth contract. This is a documented Pythonic
choice, without a native acceptance claim for that optional form.

| Type | Entries |
| --- | --- |
| 1 | VR |
| 2 | JB, PR, MR, TP |
| 3 | JB |
| 4 | PR |
| 5 | MR |
| 6 | PC |
| 7 | All six types |
| 8 | All except VR |

Patterns match names case-insensitively. `*` matches zero or more characters;
`?` and bracket patterns are rejected. Empty patterns are invalid. A pattern
with no matches succeeds with count zero.

Results are distinct name/type pairs sorted by name and then type. Format 1
returns just the name. Format 2 pads names of up to 12 characters to 12 columns,
then appends a space and the two-letter type, for 15 characters total. Longer
names use 36 columns and 39 total characters. The width is chosen per row.
Names and formatted rows must fit their STRING element capacity without
truncation. Successful calls clear all unused ARRAY slots.

## Paging and failures

The ARRAY length bounds each page. `skip` must be nonnegative and may be nonzero
only for pattern `*` with type 7. It skips that many matching sorted entries.
Without a cursor, callers can add count to skip for another page of that query.

An optional cursor must already contain a nonnegative integer. Start it at zero.
It indexes the filtered entries remaining after skip, and increases by the
number returned. An exhausted call returns zero, clears the result ARRAY and
leaves the cursor unchanged. Reset the cursor when changing the query or catalog;
Pythonic mode uses an explicit row offset rather than a native opaque index.
Names with different types occupy separate rows even under format 1.

| Status | Meaning |
| --- | --- |
| 0 | Success, including no matches or an exhausted page |
| 2 | Invalid filter type, pattern, format, skip or negative cursor |
| 3 | A selected row exceeds the destination capacity or format width |

These are portable statuses. A status failure writes only status and preserves
the result ARRAY, count and optional cursor. Uninitialized cursor values,
incorrect types, overlapping outputs and invalid references raise checked
errors. All inputs and output selectors capture once in source order; ordinary
active FOR counter and protected storage rules apply. The complete successful
output batch is validated before writes.

`program_listing_policy` records the contract. `service_operations` and
`Program.service_requests` record operation, source location and outcome without
catalog contents. Native ordering, index encoding, discovery, program lifecycle,
native statuses and strict mode remain outside this implementation.

The authored examples are [program_catalog.kl](../examples/program_catalog.kl)
and [program_pages.kl](../examples/program_pages.kl). See the
[semantic ledger](semantics/program_listing_semantics.json) and
[offline services](offline-services.md) for related context operations.
