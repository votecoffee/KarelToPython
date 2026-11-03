# Explicit live ARRAY row and plane references

Pythonic `BYNAME` arguments can borrow an existing flat ARRAY row or plane for a
user routine. This is an authored offline extension. Ordinary bare or grouped
prefix arguments still produce independent values; strict mode remains future.

```karel
VAR matrix:ARRAY[2,3]OF INTEGER entry:INTEGER
ROUTINE fill(row:ARRAY OF INTEGER)
BEGIN row[1]=7 row[3]=9 END fill
-- Inside BEGIN:
fill(BYNAME('','MATRIX[2]',entry))  -- edits matrix[2,1] and matrix[2,3]
fill(matrix[1])                    -- edits a private row
```

## Selection and interfaces

A final incomplete flat selection borrows its concrete remaining dimensions and
terminal capacities. Static paths accept comma or adjacent numeric bracket groups,
including `CUBE[2][1]`. Lookup retains explicit binding precedence, attached-program
roots, dynamic variables and the calling-root default for a blank program name.
Routine-local discovery and system paths remain excluded. Default `resolve`
continues to require complete references; GET_VAR/SET_VAR keep their existing
separate snapshot/publication policies.

A suffix has anonymous outer identity. Named inner components and record schemas
remain exact. Wildcard formals inherit actual sizes and STRING capacities; fixed
ARRAY formal dimensions remain unsupported. BYNAME does not perform numeric,
nominal or positional casts, flattening, reshaping or copyback.

[Row](../examples/live_array_row.kl), [plane](../examples/live_array_plane.kl),
[record](../examples/live_array_records.kl) and
[dynamic allocation](../examples/live_array_dynamic.kl) examples have independent
expected snapshots and saved-variable fixtures. Linked examples cover
[ordinary storage](../examples/live_array_reference_project/main.kl) and
[dynamic rename](../examples/live_array_dynamic_project/main.kl).

## Capture and shared storage

Evaluate the BYNAME arguments once in normal order. Validate the entire containing
data schema, physical storage and known leaves before exposing selected cells.
Capture the original storage and coordinates once; later arguments, rename,
linked calls and cooperative pauses do not retarget the reference. Malformed or
resized backing storage fails. Replacing a host ARRAY's storage list does not
redirect an existing capture to the new list.

Indexing and forwarding a borrowed formal use the original cells. A grouped
formal, RETURN or ordinary partial selection makes an independent checked value.
Whole-row/plane assignments retain existing element, nested-record and joint-axis
aliases. Prefix assignments/READ within a borrowed plane capture original cells.
Existing source conversions apply at assignment boundaries; they do not change
the borrowed schema.

ARRAY_LEN, scalar UNINIT queries, whole-data READ/WRITE, text/binary FILE I/O and
GET_VAR/SET_VAR reuse existing transports, limits and validation. Invalid input
batches leave selected data unchanged. Missing scalar leaves, unknown BYTE and
SHORT sentinels keep their ordinary meanings, including missing-data status 12311
for variable transfers.

## Ownership and protections

Overlap checks compare original storage cells, including nested descendants.
BYNAME rejects an entry output inside the selected row before allocating a cache
ID or writing it. An output in a disjoint row is allowed. Connected timers retain
underlying scalar identity and frame cleanup. Active FOR guards and the existing
restriction on parameter-root FOR counters remain in effect. Direct POSITION
orientation writes and CONFIG field domains remain protected.

QUEUE_TYPE may use an INTEGER row as its backing buffer. Repeated captures of the
same concrete schema and original cells retain backing identity; a different row
or independently allocated array remains a different buffer. A queue can retain
its captured buffer after a routine returns. Logical saved queues still restore
without a live backing link.

FILE/PATH/QUEUE_TYPE prefixes now follow the separate
[resource reference contract](resource-prefix-references.md): explicit BYNAME
borrowing only, preserving original resource cells and their existing lifetimes.
Ordinary data values retain the rules above. Existing one-to-three logical
dimensions, 32767 scalar-leaf and 64 schema-level bounds remain. Generic service
output syntax does not gain bare prefix targets.

## Saved state and evidence

JSON stores ordinary typed values, not view objects, routine aliases or suspended
frames. Fresh restored ARRAYs own plain independent storage. Dynamic creation
metadata, namespace renames and entry-cache behavior retain their existing rules.
No native storage layout, ABI, compiler source-form equivalence, physical robot or
controller timing claim follows from these offline tests.

This guide supersedes the former BYNAME exclusion in the
[value](array-prefix-values.md), [target](array-prefix-targets.md) and
[variable-transfer](prefix-variable-transfers.md) guides. Ordinary prefix values
and statement captures retain their documented ownership.
