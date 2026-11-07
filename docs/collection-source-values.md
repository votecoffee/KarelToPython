# Logical PATH and queue ARRAY source values

Pythonic source now copies owned logical PATH/QUEUE_TYPE ARRAY data at assignment,
private argument and function-result boundaries. Incomplete rows/planes evaluate
to independent values. Bare matching arguments and explicit BYNAME still borrow
live storage. This authored offline extension does not establish native source,
compiler, controller, ABI or strict-mode equivalence.

```karel
TYPE node_t=STRUCTURE value:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t
VAR source,target:ARRAY[2]OF route_t status:INTEGER
BEGIN
  APPEND_NODE(source[2],status)
  source[2][1].value=17
  target=source
  source[2][1].value=99
END
```

target retains 17 independently. The existing destination ARRAY containers,
collection cells and compatible PATH headers stay live. New independent PATH
nodes replace old node lists; aliases to old nodes stay detached. Queue initialized
state, entries and last sequence copy, but receiver buffer links reset. Unselected
rows keep their original cells, data and buffer links. Self-copy follows the same
rules.

## Schemas, captures and bounds

Exact collection copies retain their nominal and component schema checks.
Compatible PATH cells can also convert on assignment, private argument and
RETURN boundaries using the [scalar PATH layout rules](scalar-collection-values.md).
Both arrays must have matching dimensions and component ranks. The converted
value uses the declared receiver layout and its names. Generic formals and
results inherit concrete dimensions. Ordinary declared source storage is still
checked against its original type.

Capture and validate the complete source before evaluating destination selectors
or later arguments. Source and receiver preflight rejects malformed containers,
shared owned cells/headers/nodes, invalid queue sequence/entries and oversized
snapshots before publication. Earlier selector/source effects remain visible on
failure. A later invalid receiver does not undo those explicit earlier effects.

Logical rank remains one through three and data schemas at most 64 levels. Each
snapshot fits 32,767 collection descriptor, PATH header/node scalar and queue-entry
units. Prefix capture additionally validates the containing bank and retains the
selected original destination cells. No schema, node or queue allocation is
inferred from external files or devices.

Known and partial PATH data, missing headers/nodes and unknown BYTE markers follow
the existing logical codecs. An uninitialized queue is valid copyable state.
Missing ARRAY containers remain invalid. Converting PATH arrays charges both
snapshots, including each cell's descriptor and header/node leaves, and prepares
every cell before invoking the first robot model adapter. Joint and Cartesian
fields that use the model require complete data and explicit robot context.

## Routine interfaces and lifetime

| Source argument | Behavior |
| --- | --- |
| Bare whole ARRAY or complete named component | Existing exact borrowed reference |
| Explicit BYNAME, including a row/plane | Existing captured live reference |
| Grouped ARRAY or computed result | Private independent logical value |
| Ordinary incomplete row/plane | Private independent logical value, with compatible PATH conversion when required |

Private arrays can be mutated, forwarded by exact reference and retained by an
in-process condition handler. Pause/resume retains them; stop/failure unwinds normal
frames without copying back. Separate entries allocate separate copies. Typed
source arguments validate before later argument expressions run.

Internal and compiled linked function results capture independent concrete data
before local frame cleanup. Results can feed assignments, further private calls,
selected prefixes and ordinary value reads. Linked declarations remain exact.
[Explicit callback collection results](external-collection-results.md) now use a
separate bounded runtime-value/typed-JSON adapter and make independent copies.
Generic result helpers remain closed; there is no native external ABI.

## Boundaries and persistence

FILE descriptors/arrays, resource STRUCTURE fields and generic checked/clone/value/
result helpers keep their guards. Whole ARRAY/PATH UNINIT and FILE-bank I/O
remain unavailable; [PATH-bank I/O](path-array-io.md) and [queue entry I/O](queue-io.md)
have explicit scalar transport contracts. Scalar assignments, private arguments and results now follow the
[scalar collection policy](scalar-collection-values.md). Existing resource-root FOR and POSITION
orientation protection also remain. Live queue-buffer ownership is never copied:
a later queue operation binds a compatible explicitly supplied INTEGER buffer.

Context JSON and portable VR/DRAM archives retain ordinary logical values and
creation metadata through their existing contracts. They omit buffer links, row
views, private/retained references, callbacks and suspended frames. DONE guards
make these examples safe for exact saved-value replay.

- [Independent PATH assignment](../examples/collection_value_paths.kl)
- [Private queue argument and result](../examples/collection_value_queues.kl)
- [Captured row assignment](../examples/collection_value_rows.kl)
- [Fresh local results](../examples/collection_value_results.kl)
- [Linked PATH result](../examples/collection_value_path_project/main.kl)
- [Linked queue result](../examples/collection_value_queue_project/main.kl)

[Authored regressions](../tests/test_collection_source_values.py) exercise copies,
identity, partial data, malformed/over-budget data, private lifetimes, dynamic
storage, linked results, exact helper guards and persistence. Reports expose
collection_array_source_policy; the [semantic ledger](semantics/collection_source_value_semantics.json)
records the same offline scope. Strict mode remains future work.
