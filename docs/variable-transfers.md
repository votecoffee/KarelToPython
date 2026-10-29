# Variable transfers

Pythonic `GET_VAR(entry,program,path,value,status)` reads explicit global data;
`SET_VAR(entry,program,path,value,status)` writes it. Both use the same five
arguments and the [offline execution context](offline-services.md). Since
0.98.0, ARRAY sizes can differ and missing reference data can be transferred.

```karel
PROGRAM transfer_demo
VAR entry,status: INTEGER
    source: ARRAY[2] OF INTEGER
    destination: ARRAY[3] OF INTEGER
BEGIN
  source[1]=10
  source[2]=20
  destination[3]=30
  GET_VAR(entry,'','SOURCE',destination,status)
END transfer_demo
```

This returns `DESTINATION=[10,20,30]`, `ENTRY=1`, `STATUS=0`. The receiver's
third element survives. The [prefix example](../examples/variable_prefix.kl)
also demonstrates different matrix dimensions and STRING element capacities.

## Lookup and outputs

An empty program string selects the executing module's globals, including from
inside a routine with shadowing locals. Other program names select attached
modules or explicit `VariableStore` roots. Names are case-insensitive. Static
paths allow fields, numeric ARRAY subscripts and PATH nodes, such as
`PARTS[2].LABEL` and `ROUTE[1].POINT`. These paths do not evaluate Python or
source expressions. Routine locals and controller discovery are excluded.

`entry` and `status` require ordinary writable exact INTEGER references. A GET
receiver requires ordinary writable data storage. Output references must be
disjoint, including aggregate descendants. A dynamic SET target cannot overlap
entry/status. Protected CONFIG subfields and POSITION orientation aliases remain
excluded as destinations. Reading a protected field as the SET source is allowed.

Completed transfers publish a positive context-local cache ID for the normalized
program/path pair. Repeated successful calls reuse it. Caller entry contents do
not replace path resolution. Failed lookups and type mismatches retain entry and
data, write status only, and do not allocate IDs. Cache IDs are not persisted.

## ARRAY and type rules

ARRAY transfers use these bounded rules:

- Source and receiver must have the same logical rank, from one through three.
  Named ARRAY components contribute their dimensions to that rank.
- Outer ARRAY names and extents may differ. Terminal element types must match;
  named STRUCTURE types and JOINTPOS widths retain exact identity. Numeric
  leaves also permit [checked integral-family/integral-to-REAL conversion](numeric-variable-transfers.md).
- STRING elements may have different capacities. Copied strings truncate to the
  receiver's capacity. Numeric receiver bounds and declared source domains remain checked.
- Copy the smaller **total terminal element count** in row-major order. This is
  a sequential prefix, including across differently shaped matrices. Preserve
  the receiver's remaining cells. A record or joint is one terminal element.

For example, a `[2,2]` source holding `[[1,2],[3,4]]` copied into a `[2,3]`
receiver becomes `[[1,2,3],[4,old5,old6]]`. Rank changes do not flatten implicitly.
Ordinary whole ARRAY assignment, routine parameters and RETURN keep their
existing nominal type and shape rules.

Non-ARRAY GET and SET permit identical data types, receiver-capacity STRING
truncation, checked integral-family conversion and integral-to-REAL promotion.
The same numeric choices now apply to ARRAY prefixes. REAL-to-integer conversion
remains explicit; BOOLEAN does not enter the numeric category. Individual
Cartesian/joint-width values can use [checked positional conversion](positional-variable-transfers.md).
Representation changes require complete source data, while exact copies retain
their missing-data contract. Known value/range/config checks remain.
Since 0.99.0, whole QUEUE_TYPE values support independent
[logical queue transfers](queue-transfers.md). Whole FILE/PATH and embedded
resources remain excluded; static data fields and nodes can be addressed
individually.

## Missing values

An uninitialized SET source reference is data that can be transferred. It need
not be evaluated as an initialized scalar first. Grouping such a reference also
works. An expression such as `missing+1` still fails when it reads missing data.

```karel
PROGRAM missing_demo
VAR entry,status,missing,value: INTEGER
    cleared: BOOLEAN
BEGIN
  value=99
  SET_VAR(entry,'','VALUE',missing,status)
  cleared=UNINIT(value)
END missing_demo
```

This clears VALUE, returns `STATUS=12311`, and sets CLEARED to TRUE. See the
[missing-data example](../examples/variable_missing.kl) for partial ARRAY data
and unknown BYTE contents.

Partial records, joints and ARRAY elements retain both known and missing leaves.
Only missing data inside the transferred prefix contributes to status 12311.
Missing source cells beyond a shorter receiver are not copied, and an untouched
missing receiver tail does not change status. A whole missing source container
clears the entire compatible receiver. An initialized ARRAY copied into a whole
missing receiver materializes its container; the unfilled tail remains missing.

BYTE unknown-content markers are preserved as unknown BYTE data, distinct from
initialization-tracked missing values. They do not cause status 12311. They
cannot be read numerically or promoted to INTEGER/REAL as invented values.
Type/rank compatibility is checked before missing propagation: a missing INTEGER
cannot clear a BOOLEAN receiver.

## Ordering, validation and status

Arguments and selector expressions run once, from left to right. SET captures
an independent typed source at its fourth argument, before the status selector.
Generic STRING/ARRAY parameters inherit the actual source capacity/shape. GET
resolves and snapshots the named global after output selectors have run.

For data transfers, source container/schema checks occur at capture. Known values in selected
transfer cells are checked after lookup. Untransferred numeric source tail cells
are not read as values; structural checks still cover the source containers and
declared STRING capacities. Destination structure is checked, then the complete
replacement is prepared before publishing data, entry and status. Existing
aggregate cells retain their identity when updated, preserving captured aliases.
Whole [queue transfers](queue-transfers.md) validate their complete logical source
at capture and retain the receiver object while releasing its buffer binding.

Malformed storage, invalid known values, invalid output aliases and forbidden
resources raise runtime errors. They preserve transfer outputs and storage;
earlier completed source statements and argument/selector effects remain visible.
These rules also apply to partial CONFIG data, including known turn-number
limits. General assignment checks remain unchanged.

| Status | Portable meaning |
| --- | --- |
| 0 | Transfer completed without copied initialization-tracked missing data |
| 1 | Program/path could not be resolved; status only |
| 3 | Incompatible data type or ARRAY rank; status only |
| 12311 | Transfer completed and copied missing data |

The generated report's `variable_transfer_policy` describes these choices.
`service_operations` records source sites; runtime `service_requests` records
operation, line and outcome without data values. Partial results and unknown
BYTE markers survive [typed context save/load](collection-persistence.md).
Multidimensional ARRAY state reloads the nested lists emitted by snapshots;
earlier flat physical-storage configurations remain readable. Malformed/ragged
shapes fail. Restored POSITION data retains protected orientation children.

The [semantics ledger](semantics/variable_transfer_semantics.json) separates
reviewed manual contracts from portable choices. These are offline transfers;
native ARRAY layout, exact status/cache encoding, remote variables and controller
execution remain unvalidated. Strict mode is a future milestone.
