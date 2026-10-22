# Collection persistence

Pythonic context snapshots now include declared PATH and QUEUE_TYPE globals and
explicit VariableStore bindings. Saving and loading preserve logical collection
contents. FILE handles, call stacks and suspended execution remain separate.

Use the existing `ExecutionContext.to_config()`, `from_config()`, `save()` and
`load()` APIs, or generated script `--context` and `--state-out` options. Context
JSON stores each collection in the existing typed `variables` list with its
program and path. Attach the same declarations to restore the saved globals.

```python
import json
from karel2py import translate, runtime as rt

source = """PROGRAM STORE
TYPE node_t=STRUCTURE id: INTEGER ENDSTRUCTURE
VAR p: PATH NODEDATA=node_t q: QUEUE_TYPE
    data: ARRAY[3] OF INTEGER seq,status,seen: INTEGER seeded: BOOLEAN
BEGIN
  IF UNINIT(seeded) THEN
    APPEND_NODE(p,status)
    p[1].id=42
    INIT_QUEUE(q)
    APPEND_QUEUE(7,q,data,seq,status)
    seeded=TRUE
  ENDIF
  seen=p[1].id
END STORE"""
namespace = {"__name__": "collection_persistence_example"}
exec(translate(source).python_source, namespace)
Program = namespace["Program"]
context = rt.ExecutionContext()
first = Program(context=context)
assert first.run()["SEEN"] == 42
saved = json.loads(json.dumps(context.to_config()))
restored = rt.ExecutionContext.from_config(saved)
second = Program(context=restored)
assert second.snapshot() == first.snapshot()
assert second._state.values["Q"].buffer is None
assert second.run() == first.snapshot()
assert second._state.values["Q"].sequence == 1
```

A new Program starts its source from the beginning. The example's saved `seeded`
flag explicitly controls whether initialization runs again. Loading state does
not resume a task at a previous statement. Ordinary source initialization,
including INIT_QUEUE, still executes when reached.

## PATH values

A PATH row retains the complete resolved NODEDATA/PATHHEADER type schema and a
value object with exactly `nodes` and `data`. Nodes remain in their stored order.
A headerless path uses `data: null`. Omitted NODEDATA keeps the portable
STD_PTH_NODE definition with a POSITION `NODE_POS` field.

Snapshots preserve partially initialized nodes, headers, records, joint axes and
ARRAY elements. `{"uninitialized": true}` and `{"unknown_byte": true}` remain
distinct; unknown BYTE markers are valid only for BYTE storage. Whole missing
nodes are also preserved. Concrete named ARRAY identities, all dimensions and
nominal STRUCTURE types survive round trips.

The codec checks exact storage shapes, field names, finite known numeric values,
STRING capacities, CONFIG Boolean/turn domains and the existing 32767-node
limit. Schemas require concrete resource-free data types, at most three logical
ARRAY dimensions and at most 32767 scalar leaves per component. Embedded FILE,
PATH and QUEUE resources are rejected. Unknown fields, malformed markers and
over-capacity strings are rejected rather than normalized by truncation.

These are data snapshots. POSITION orientation columns are preserved as data;
geometry operations retain their separate proper-matrix checks. Restored PATH
nodes and headers support the ordinary field, node, copy and inspection APIs.
Whole PATH remains excluded from GET_VAR/SET_VAR, as in the reviewed manual;
node/header data paths can select supported data values.

## Queue values and buffer binding

A QUEUE_TYPE value object contains exactly:

| Field | Saved meaning |
| --- | --- |
| `initialized` | Boolean initialization flag. |
| `sequence` | Last issued sequence ID, including IDs whose entries were removed. |
| `entries` | Ordered `[sequence_id, integer_value]` pairs. |

Entry order is FIFO order, including INSERT_QUEUE placement; it is not sorted by
sequence ID. IDs must be distinct, positive and no greater than the saved
counter. At most 32767 entries are accepted. An uninitialized queue has no
entries, a zero counter and no buffer. Numeric values use the existing checked
INTEGER domain.

The ordinary Program snapshot retains its existing queue summary. The typed
context value additionally carries the sequence counter needed for continuation.

The backing ARRAY reference and its former capacity are not serialized. A loaded
queue has no bound buffer. Its first explicit queue operation supplies an ARRAY
large enough to hold the restored entries. That operation binds the ARRAY and
uses the existing synchronization rules, including zeroing unused backing slots.
The caller can supply a larger capacity after reload. A buffer too small for
existing entries raises before binding or consuming any entry.

After binding, the existing same-buffer identity rule applies for that run.
Ordinary status failures can still bind/synchronize the supplied buffer, as for
a newly initialized queue. INIT_QUEUE deliberately clears saved entries, resets
the sequence counter and releases the current binding. Queue values remain
reference-only in ordinary assignments and value interfaces. Since 0.99.0,
[GET_VAR/SET_VAR queue transfers](queue-transfers.md) explicitly copy logical
state and release the receiver binding using the same portable snapshot rules.

## Validation and boundaries

Encoding validates collection data before the atomic state-file write. Invalid
data leaves an existing destination file unchanged. Decoding validates a fresh
context without changing the source file. JSON objects, restored data and attached
Program values are independent copies. Explicitly supplied collection bindings
use the same codec as attached globals.

`collection_state_policy` records the schemas, guard and rebinding choices.
Saving/loading uses host context APIs and adds no KAREL service requests. Existing
collection statements keep their ordinary value-free operation records.

This is portable logical state, with no native VR/PATH/queue binary layout,
restored Python alias graph, old queue-buffer identity/capacity, native task
checkpoint or controller acceptance claim. Strict mode remains a future
milestone. Older context files without collection rows still load normally.

See the authored [seed-once example](../examples/collection_state.kl),
[restored-data example](../examples/restored_collections.kl),
[semantic ledger](semantics/collection_persistence_semantics.json) and
[offline services](offline-services.md).
