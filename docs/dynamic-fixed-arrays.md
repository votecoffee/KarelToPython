# Fixed ARRAY type strings in CREATE_VAR

Pythonic CREATE_VAR accepts fixed ARRAY type strings, including directly written
layers. It normalizes those dimensions before allocation, using the same schemas
as ordinary [inline declarations](inline-arrays.md).

```karel
CREATE_VAR('CACHE','ITEM','','ARRAY[2] OF ARRAY[3] OF INTEGER',0,0,0,0,status)
```

This creates a fresh `ARRAY[2,3] OF INTEGER` in the explicit logical namespace.
The three zero dimension slots add no outer storage. The type string supplies
its shape completely. See the [runnable example](../examples/dynamic_fixed_arrays.kl).

## Shape and type rules

| Type text | Inner, middle, outer slots | Result |
| --- | --- | --- |
| `ARRAY[2,3] OF INTEGER` | `0,0,0` | Anonymous ARRAY[2,3] OF INTEGER. |
| `ARRAY[2] OF ARRAY[3] OF INTEGER` | `0,0,0` | The same normalized schema. |
| `ARRAY[3] OF INTEGER` | `2,4,0` | ARRAY[4,2,3] OF INTEGER. |
| `ARRAY OF ARRAY[3] OF INTEGER` | `2,0,0` | ARRAY[2,3] OF INTEGER. |
| `ARRAY[2] OF row_t` | `0,0,0` | ARRAY[2] OF the supplied named row type. |
| `ARRAY[2,3] OF FILE` | `0,0,0` | Six fresh closed FILE descriptors. |
| `ARRAY[2,3] OF PATH` | `0,0,0` | Six independent empty default PATHs. |
| `ARRAY[2,3] OF QUEUE_TYPE` | `0,0,0` | Six independent uninitialized queues. |

Literal dimensions are outer-to-inner. Existing dimension slots add outer
dimensions in their existing inner-to-outer argument order. Used slots must be
contiguous from the inner slot. One optional leading `ARRAY OF` retains its
positive-inner-slot requirement. Bare layers inside fixed layers and repeated
bare `ARRAY OF ARRAY OF` forms remain rejected.

Dimensions contain one through five decimal digits and must resolve to 1..32767.
There are no signs, expressions, constants or wildcards in runtime type text.
Case, surrounding spaces and spaces around ARRAY brackets/commas normalize.
The existing bounded ASCII STRING input and terminal-type spellings still apply;
the parser does not evaluate source code.

Terminal scalars, bounded/default STRING, builtin records, joints, named data,
FILE and logical collections follow their current creation rules. STRING defaults
to capacity 12. Named components resolve through the explicit type program and
retain their existing identities. A named ARRAY alias is not flattened, and an
anonymous host-provided ARRAY cannot masquerade as a named component.

## Allocation, execution and persistence

Validate the full normalized shape and terminal schema before allocation. Logical
rank includes named components and remains at most three; existing 64-level
schemas and 32767 scalar/resource and shared-reservation limits remain. PATH
headers reserve their declared leaves; nodes and queue entries grow later through
their existing operations. Positional terminals still require an explicit group;
creation does not infer geometry or robot context.

Name, collision, group/pool and owner rules are unchanged. Invalid text, dimensions
or types return portable status 5. Shared-reservation overflow returns 6. The
existing creation checkpoint still precedes allocation and rechecks bank identity,
root collisions, terminal lifetime and fresh reservation totals. Budget failures
propagate without publishing a root or overwriting the source status target.

Created arrays use ordinary BYNAME, typed routines, variable transfers, inspection,
I/O and supported archive operations. Rename and pause retain captured storage.
Saved JSON uses existing normalized ARRAY schemas and creation metadata. FILE
banks retain closed allocation markers; logical queues omit buffer links. No live
descriptors, callbacks or suspended execution are restored.

Reports expose `dynamic_fixed_array_policy`, with existing data, FILE and
collection policies retaining their own ownership boundaries. The
[semantic ledger](semantics/dynamic_fixed_array_semantics.json) and
[authored regressions](../tests/test_dynamic_fixed_arrays.py) cover allocation,
data/resource operations, linkage, replay and failed publication. This is an
offline Pythonic extension; native syntax/allocation, controller and strict
equivalence remain separate.
