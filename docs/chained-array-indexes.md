# Chained ARRAY subscripts

Pythonic translation accepts complete chained ARRAY subscripts as another
spelling of the existing comma-separated access:

```karel
values[1][2]=42
result=values[1,2]

cube[1,2][3]=7
result=cube[1][2][3]

result=make_values()[1][2]
```

This is a source-level normalization. It uses the existing typed ARRAY storage,
bounds checks and captured references; it does not create Python list views or
new partial rows. The preserved legacy translator retains its comma-only
restrictions.

## Complete accesses and named boundaries

Adjacent bracket groups combine into one ordered subscript list, including
groups separated by parentheses around an intermediate value receiver.
`((values[1]))[2]` therefore completes the same access as `values[1,2]`.
Mixed forms such as `[i,j][k]` and `[i][j,k]` are supported when the resulting
access is valid.

A flat `ARRAY[2,3] OF INTEGER` requires both subscripts. Standalone `values[1]`,
including `(values[1])`, remains invalid. Likewise, two subscripts into a flat
three-dimensional ARRAY remain incomplete. A complete surrounding chain can
supply those missing subscripts; an intervening STRUCTURE field access cannot
invent a row that the ARRAY type does not expose.

Separately named ARRAY components keep their established boundaries:

```karel
TYPE row_t=ARRAY[3] OF INTEGER
     plane_t=ARRAY[2] OF row_t
VAR plane:plane_t row:row_t
BEGIN
  plane[1][2]=42
  row=plane[1]
END
```

Here `plane[1]` is an existing named `row_t` component. A chain can cross that
boundary, and a selection ending at a valid named ARRAY boundary can still be
passed or copied as that exact type. A partial access inside a flat named
component remains invalid until its required subscripts are supplied.

At most three logical dimensions remain supported. Extra subscripts, scalar or
resource reindexing, invalid index types and ARRAY representation/nominal type
mismatches retain their normal errors. STRING capacities, dimensions, named
identities and partial scalar contents are preserved without reshaping or
coercion. Whole-array copies remain independent values where ordinary copying
applies.

## Evaluation and capture

Each normalized access evaluates its base once, then each index once from left
to right. All index expressions are captured before the combined bounds check,
matching existing comma indexing. For example, a later index function still
runs before an earlier out-of-range index is reported. No intermediate row is
loaded or checked independently merely because a bracket group ends there.

A function-result base is captured before its index functions run. Its existing
independent result ownership remains intact if a later index function changes
the original source. Pure type checks and source normalization do not execute
functions or create duplicate call sites.

Assignment keeps its established order: capture the right-hand value before
evaluating the target base and indexes. A writable reference actual, READ target,
conversion/service output or FOR counter captures the selected leaf once.
Changing index variables later does not retarget that reference. Parentheses
around an entire routine actual retain their ordinary value-passing meaning;
parentheses used within a larger access do not copy a row implicitly.

Chained selectors work with STRUCTURE fields, lexical USING, computed record
captures, typed aggregate function results and linked routine formals. BYNAME
entry-output storage can use complete source chains. A quoted BYNAME variable
path remains a dynamic path string with its own grammar; source normalization
does not rewrite that string.

## Protection and lifetime

Original declared roots and private USING protection identities are retained.
Whole-root active-counter write/reuse guards cover chained reads, writes,
argument aliases, handlers and service outputs just as they cover comma access.
POSITION orientation descendants remain readonly, CONFIG subfields retain their
bounded/output rules, and BYTE unknown contents do not become initialized data.

[Checked joint-axis access](joint-axis-access.md) can now terminate a complete
ARRAY chain at one additional one-based REAL axis. It preserves ARRAY boundaries
and does not create partial flat rows.

Both structured code and the label dispatcher use the same normalization.
Existing FOR bounds, RETURN snapshots, GOTO entry restrictions, errors and
cleanup apply. INTEGER, BYTE and SHORT chained counters retain their respective
cleanup markers. Cooperative pauses retain captured bases, indexes and
references; resume does not replay an index function, and stop clears the
original selected counter leaf.

Context JSON preserves concrete ARRAY types, shapes and ordinary values or
missing markers. It does not serialize expression captures, iterators or a
suspended Python stack.

## Reports and verification

`array_index_chains` records each normalized chain with its body, source
line/column, `source_selector`, `normalized_selector`, ordered `segment_lengths`
and total `subscript_count`. Existing counter/USING selector descriptions refer
to the normalized typed access. The ordinary source map retains include-file
origins. Normal comma access creates no chain row.

The [authored tests](../tests/test_chained_array_indexes.py) cover flat/named
components, grouping, aggregate results, partial data, capacities, effects,
references, READ/BYNAME/USING/counters, errors, both engines, suspension, linked
programs and JSON state. These establish offline Pythonic behavior without a
native compiler or controller acceptance claim.
