# Queue entry READ and WRITE

Pythonic mode accepts initialized scalar QUEUE_TYPE and ARRAYs ending in queues
for READ and WRITE, including selected rows/planes, named components, created
storage, borrowed interfaces and compiled linked routines. This is an authored
offline extension; native queue I/O, packed layouts and controller equivalence
have not been established. Strict mode remains a future milestone.

```karel
VAR values:QUEUE_TYPE buffer,received:ARRAY[3]OF INTEGER seq,status,first:INTEGER
BEGIN
  INIT_QUEUE(values)
  APPEND_QUEUE(17,values,buffer,seq,status)
  APPEND_QUEUE(9,values,buffer,seq,status)
  WRITE(values::4,CR)
  READ(values)
  GET_QUEUE(values,received,first,seq,status)
END
```

WRITE emits the two INTEGER values 17 and 9, each in a four-character field,
followed by LF. READ expects two INTEGER values, for example `[42, 43]` from a
callback. It retains IDs 1 and 2, their order and the last sequence counter 2.
The subsequent GET_QUEUE returns value 42 and ID 1, and explicitly binds
`received`, synchronizing its cells to `[43, 0, 0]`.

## Logical values and buffers

Queue READ replaces existing entry values together and retains the original
queue object, entry-list object, initialization flag, IDs, FIFO order and sequence
counter. It detaches the previous backing-buffer link. Its ARRAY cells keep their
old contents: `buffer` above stays `[17, 9, 0]`. No implicit ARRAY write occurs,
including when a former backing cell is an active FOR counter.

A later queue operation supplies and binds an explicit compatible INTEGER ARRAY
and synchronizes it using the existing queue service rules. This matches the
logical-copy policy used by GET_VAR/SET_VAR and source assignments. Input neither
infers entry counts nor appends, deletes or allocates entries/buffers.

ARRAY cells expand in row-major order, followed by each queue's current entry
order. The stream contains INTEGER values only, without IDs, counters, lengths,
initialization flags or automatic separators. Binary FILEs encode ordinary scalar
INTEGERs in the selected byte order; they are not native queue descriptors.

All selected queues must have passed INIT_QUEUE, including empty bank cells.
Empty initialized cells contribute no fields. All-empty WRITE emits
one empty item and still requires an open FILE. Formats now validate the
[declared INTEGER domain](empty-collection-output.md) without producing padding
or entry bytes. All-empty READ still rejects before invoking an input adapter. Nonempty items support
the normal uniform scalar width/base formats, evaluated once per source item.

## Capture and publication

Queue I/O charges one step per queue descriptor and one each for every entry
ID and value before validating the payload. It verifies the queue and entry
containers, entry count, sequence and backing storage after charging.
WRITE then detaches complete values before format expressions. READ
captures original queue/entry storage and backing-buffer mappings before formats
or waiting. Each entry must remain present and unchanged until publication.
Reinitialization, queue replacement, entry-list replacement, changed IDs/order/
counter or changed buffer mappings reject. Explicit earlier callback/format
side effects are retained on failure; input never retargets replacement storage.

Every queue's complete, contiguous, ordered capture must participate. Duplicate
queues, shared entry lists, partial/reordered cohorts and entry/scalar destination
overlaps reject before input. Former backing ARRAY cells can appear separately
in the same READ because queue input does not write them. Their explicit scalar
inputs follow normal alias and active-counter rules.

All scalar values and complete POSITION geometry validate before any destination
publication. READ stages every replacement pair with its original entry ID,
then publishes the prepared entries without re-encoding the queue. It checks
the original destination reference and entry contents against the capture.
Invalid values, a stale later queue or invalid geometry leave the other
staged inputs unchanged. TextInput and FILEs retain their existing cursor,
status and rollback contracts. Cancellation and stop discard pending queue
publication; pause/resume retains its captured request. Earlier completed reads
remain visible.

## Interfaces, bounds and saved state

Bare matching queue/bank formals and explicit BYNAME borrow live storage. Grouped
or computed arguments and ordinary prefix arguments make private logical copies;
READ directly on a selected row or plane captures its original cells. A flat
selection also charges and validates the containing bank. WRITE snapshots
selected scalars from the checked view. Computed values can be written, while
input requires ordinary writable references.

Existing limits apply: one through three logical ARRAY dimensions, 32,767 logical
entry/collection snapshot units and at most 1,024 expanded scalar fields including
CR per operation. Combined items share the operation limit and output/backend
limits. Malformed queues and buffer mappings reject without publishing input.

Callback/JSON/TextInput, explicit text/binary FILE, serial, keyboard and pipe
transports share the staged input contract. Typed JSON and logical archives retain
queue initialization, entries and last sequence, omitting buffer links, input
captures, pending operations and suspended frames. Reopened streams and supplied
inputs make the authored examples replay with identical saved contexts.

Use [UNINIT](initialization-queries.md#queue-initialization) to check whether
an individual queue has been initialized. FILE values/banks, resource fields
in STRUCTUREs and generic queue checked/value/result helpers keep their guards.
[Explicit callback collection results](external-collection-results.md) now detach bounded values or
typed JSON. Linked signatures and ordinary source-root FOR proofs stay exact.

Reports expose `queue_io_policy` and each queue item's scalar order. See the
[semantics ledger](semantics/queue_io_semantics.json), [regressions](../tests/test_queue_io.py),
[scalar example](../examples/queue_io_values.kl), [bank example](../examples/queue_io_bank.kl),
[binary example](../examples/queue_io_binary.kl), [rebinding example](../examples/queue_io_rebind.kl),
[borrowed project](../examples/queue_io_linked_borrowed/main.kl) and
[private-result project](../examples/queue_io_linked_private/main.kl).
