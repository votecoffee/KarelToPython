# ARRAY row and plane values

Pythonic mode accepts incomplete flat ARRAY selections as independent row or
plane values. This is an authored extension, without native source-form or
controller acceptance claims. Strict mode remains a future milestone.

```karel
VAR matrix:ARRAY[2,3]OF INTEGER row:ARRAY[3]OF INTEGER
-- Inside BEGIN:
matrix[1,1]=7 matrix[1,2]=9 matrix[1,3]=11
row=matrix[1]
row[2]=42                 -- matrix[1,2] stays 9
```

| Selection | Value |
| --- | --- |
| `matrix[i]` for a flat matrix | Independent one-dimensional row |
| `cube[i]` for a flat cube | Independent two-dimensional plane |
| `cube[i,j]` or `cube[i][j]` | Independent one-dimensional row |
| Prefix within a separately named flat component | Independent remaining component dimensions |
| Prefix ending exactly before a named component | Existing named component reference; grouping still makes a private value |

Complete adjacent chains still normalize before typing. `(matrix[i])[j]` is
therefore a complete element reference, just like `matrix[i,j]`; it does not copy
an intermediate row. Only a selection ending inside a flat component uses this
value extension. See [chained subscripts](chained-array-indexes.md).

## Shapes, schemas and ownership

Remaining dimensions retain their order, with no reshape or equal-count rank
conversion. A suffix cut from a flat component has an anonymous outer ARRAY type.
Declared named child components, record layouts and bounded STRING capacities
remain intact. A flat generic formal copies into its declared suffix layout,
using actual dimensions and STRING capacity; this may rebuild named caller rows
into anonymous flat storage under existing source schema-conversion rules.

Rows and planes contain ordinary ARRAY data. Assignment, RETURN and ordinary
source routine arguments use existing numeric, record, positional and explicit
model-backed conversions. A bare prefix argument is a private writable value:
a callee can edit it without writing back to the original array. This applies to
linked routines too. Complete named-component arguments retain their established
reference behavior.

The [generic STRING example](../examples/array_prefix_generic.kl) inherits the
actual suffix capacity before assigning into smaller declared STRING storage.
The [linked argument](../examples/array_prefix_project/main.kl) and
[linked result](../examples/array_prefix_return_project/main.kl) show private
ownership across source modules.

## Evaluation and validation

Evaluate the receiver once, then every supplied subscript once from left to
right. Capture the selected value after those index effects finish. All supplied
index functions run before a bounds failure, as with complete comma indexing.
The receiver's entire concrete schema, storage and known data are validated
before publishing a prefix, including unselected elements. Malformed known
values cannot be hidden by selecting another row.

Preserve permitted missing scalar leaves, unknown BYTE contents and SHORT
sentinels. Missing record/ARRAY containers remain invalid. Selected records,
nested arrays, CONFIGs, positions and joint data are independently owned; no
geometry is inferred for partial poses or joints. Existing POSITION orientation
write guards and CONFIG domains still apply.

Later routine arguments or WRITE format functions cannot change an already
copied prefix. Assignment captures the source before evaluating destination
indexes. Cooperative pauses retain index calls and private arguments without
replaying them. FOR analysis treats private prefix arguments as values, while
retaining direct global effects and ordinary complete-reference guards.

## Output, persistence and limits

ARRAY_LEN returns the first remaining dimension. Complete prefixes can use
[whole-data WRITE](aggregate-output.md), including uniform scalar formats and
binary FILE fields. Missing/unknown output still fails before publication.
See [formatted output](../examples/array_prefix_output.kl) and the
[binary FILE example](../examples/array_prefix_binary.kl).

Saved JSON contains ordinary typed ARRAY values. There is no view, capture,
callback or suspended stack to restore. The authored examples use an explicit
completion flag so saved output state can be replayed without repeating effects.

Existing limits remain three logical dimensions, 32767 source scalar leaves and
64 data-schema levels. Resources, ragged dimensions and writable partial views
remain excluded. Separate [statement targets](array-prefix-targets.md) now allow
assignment and READ into original rows/planes. Service outputs and BYNAME
variable-path aliases remain complete. Generic runtime
`indexed_type` and `index_reference` retain their full-rank/reference contracts.

Reports add source-located `array_prefix_values` and `array_prefix_policy`, with
source/suffix schemas, supplied subscript count and independent-value metadata.
The [regressions](../tests/test_array_prefix_values.py) and
[semantic ledger](semantics/array_prefix_semantics.json) record offline evidence.
