# Formatted empty collection output

Pythonic WRITE accepts uniform formats on empty headerless PATHs, initialized
QUEUE_TYPE values, all-empty banks and selected rows/planes. The same source
operation works before and after collections acquire data. This is an authored
offline extension, without a native PATH/queue framing or controller claim.

```karel
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
VAR route:PATH NODEDATA=node_t q:QUEUE_TYPE
BEGIN
 INIT_QUEUE(q)
 WRITE('empty',route::4,q::4,CR)
END
```

The output is `empty` followed by LF. Each collection contributes one empty item,
with no width padding, quoted STRING wrapper, numeric field or record marker.
Other scalar items and CR retain their ordinary output. Empty groups still count
against the existing operation-item bound and still create a normal WRITE request.

## Format domains and capture

Validate every declared node scalar category even when no nodes exist. Queues use
the INTEGER category. Text width, base, precision and STRING mode rules are the
same as for nonempty scalar output. A mixed INTEGER/STRING node can use second
format 2, but 16 rejects because it is not a STRING mode. BOOLEAN still accepts
only a width. Invalid literal formats reject during translation; dynamic formats
reject before outer output publication.

Binary FILEs retain scalar byte-width-only rules. An empty INTEGER collection
with width 4 emits no bytes; width 3 and a second format reject. An empty STRING
node with width 8 emits no NUL padding. No collection value, node, queue entry or
buffer is allocated or initialized to validate a format. The existing pure, bounded scalar formatters and
binary format planner supply the same domain checks without transport output.

Capture and validate the source before evaluating width then second format once.
A format function may append data to the original collection, but it cannot change
the current empty snapshot; a later WRITE sees those completed effects. Invalid
source data, uninitialized queues and capture-budget failure prevent later format
functions. Failed formatting retains earlier explicit effects but publishes no
part of the outer WRITE.

## Transports, bounds and input

The normal omitted-file recorder/callback and supplied text, binary and
cooperative FILE transports apply. Empty output still requires an open writable
FILE. Other byte payloads and CR retain their normal encoding. No backend,
directory, connection or endpoint is discovered or opened implicitly.

Existing collection snapshot/schema limits, 1024 scalar/CR items, 254-character
omitted-file text limit, FILE quotas and execution budgets remain. Headers and
nonempty nodes/entries still need complete valid scalar values. Missing shapes,
resource fields, unavailable data and read-only destinations retain their guards.
Empty headerless/all-empty READ remains rejected and does not infer or allocate
nodes or queue entries.

Saved context retains logical data, not captures, callbacks, pending operations
or live FILE handles. Reports expose `empty_collection_write_policy` and update
the existing PATH/queue/aggregate format policies. Versioned older ledgers retain
their historical exclusions with an explicit pointer to this current extension.

See the [empty/populated example](../examples/empty_collection_output.kl),
[regressions](../tests/test_empty_collection_formats.py) and
[semantic ledger](semantics/empty_collection_write_semantics.json).
