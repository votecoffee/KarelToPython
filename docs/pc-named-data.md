# Named PC data batches

Pythonic `ADD_BYNAMEPC` accepts complete ordinary data in addition to the existing
INTEGER, REAL and STRING scalar forms. It appends an ordered sequence of existing
typed items to the BYTE buffer and updates the index only after preparing the
complete batch. Sending still requires an explicitly configured offline outbox.

```karel
TYPE item_t=STRUCTURE ready:BOOLEAN code:BYTE amount:REAL ENDSTRUCTURE
VAR item:item_t buffer:ARRAY[20]OF BYTE cursor,status:INTEGER
BEGIN
  item.ready=TRUE item.code=255 item.amount=1.5
  cursor=1
  ADD_BYNAMEPC(buffer,cursor,'','item',status)
END
```

The buffer contains INTEGER 1, INTEGER 255, REAL32 1.5 and one final end marker.
The index becomes 19. See the [complete runnable example](../examples/pc_named_data.kl).

## Source values and item order

| Source data | Packet items |
| --- | --- |
| BYTE or SHORT | One existing INTEGER item after source-domain/initialization checks. |
| BOOLEAN | One INTEGER item: false is 0 and true is 1. |
| ARRAY | Expand terminal data in row-major order, preserving named component boundaries during validation. |
| User or builtin record | Expand fields recursively in declaration order. |
| JOINTPOS | One REAL32 item per declared axis. |
| INTEGER, REAL, STRING | Existing scalar tags and encoding, unchanged. |

Nested ARRAYs/records, VECTOR, CONFIG, Cartesian data and joints use the existing
complete data capture rules. Read-only POSITION columns can be read. Unknown
BYTEs, SHORT sentinels, missing leaves, malformed containers, invalid strings and
unrepresentable REAL32 values reject the complete admitted batch. No field is
silently omitted or defaulted.

Names follow current/attached globals and explicit variable roots, with existing
case-insensitive static paths. Blank program uses the executing source module,
including a supplied linked routine. Fully selected named ARRAY components can
be serialized; incomplete flat row/plane selectors remain excluded. Routine-local
discovery, system paths and whole FILE/PATH/QUEUE resources remain outside this
contract.

### Selected PATH data

`route[1]`, `route[1].field` and ordinary PATH header fields select data
without serializing the PATH descriptor or unselected nodes. PATH banks
accept static `routes[2,1]` and `routes[2][1]` node paths. The complete selected
record, nested data, Cartesian columns or joints follow the same table above.
Incomplete selected data returns status 4; absent or invalid node paths return
status 1. Unselected partial nodes do not prevent a complete selected capture.

Only selected data is captured after scalar budget admission; lookup does not
clone the whole PATH. See the [runnable PATH example](../examples/pc_path_node.kl)
and [PATH data contract](semantics/pc_path_node_semantics.json).

## Wire format and bounds

The [existing scalar envelope](pc-exchange.md#wire-format) is unchanged: big-endian
type tags 16, 17 and 209, INTEGER32, finite REAL32 and explicit-length ASCII STRING.
There are no ARRAY dimension markers, nominal type names or field-name headers.
The receiver must know the application schema; decoding typed items alone does
not reconstruct the original aggregate type.

The ordinary buffer bound remains 1..244 bytes. Before expanding source storage,
reject a batch if even four bytes per scalar plus the final two-byte marker
cannot fit. This schema-based status 3 can precede content validation. The bound
also limits admitted batches to at most 60 leaves. Complete data validation and
exact item lengths then determine whether the batch fits. A batch of 60 empty
STRINGs uses 242 bytes; INTEGER/REAL items require six bytes each.

## Capture and publication

Retain the existing initial builder checkpoint and index/buffer selection. For
new data forms, charge one step per scalar before creating detached source
copies or item bytes. Source edits completed during those checkpoints are read
by the subsequent capture. A changed source schema or captured source location,
buffer root, backing list, contents or index raises before publication and
preserves those completed edits.
Buffer, index and status must also retain their captured reference type, schema,
storage and key across the initial checkpoint and expanded scalar charges.
Deleting a selected node or retargeting a captured reference raises before writes;
changing the ordinary index value at the initial checkpoint remains allowed.
Existing INTEGER/REAL/STRING scalar calls retain their earlier behavior.

Prepare all items and one end marker before replacing buffer bytes and advancing
the index. Status 3 reports capacity and 4 reports incompatible, unknown or
unrepresentable data. Neither publishes a partial batch. Budget/lifecycle failures
propagate and preserve the prior status target, buffer and index. Existing alias,
active FOR, source protection and linked-interface checks remain in force.

Untouched prefix/tail bytes and unknown unused BYTEs remain intact. Named data
can append after ordinary builders or before more builders. No outbox is needed
until SEND_DATAPC/SEND_EVENTPC. Saved context retains ordinary source data and
the existing checked packet/outbox layout; no live lookup or callback is saved.

`pc_named_data_policy`, the [semantic ledger](semantics/pc_named_data_semantics.json)
and [authored regressions](../tests/test_pc_named_data.py) describe this extension.
Native aggregate envelopes, GEMM/PC delivery, controller and public strict-mode
equivalence remain separate.
