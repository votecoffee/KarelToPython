# PC data buffers and event outbox

Pythonic mode implements `ADD_INTPC`, `ADD_REALPC`, `ADD_STRINGPC`,
`ADD_BYNAMEPC`, `SEND_DATAPC` and `SEND_EVENTPC`. Buffer construction uses the
manual's common typed format. Sending publishes a bounded offline event to an
explicit `PcExchange` outbox; it does not transmit to a PC or robot.

```python
from karel2py.runtime import ExecutionContext, PcExchange

context = ExecutionContext(pc_exchange=PcExchange(capacity=1024))
```

The JSON equivalent is `{"pc_exchange": {"capacity": 1024}}`. Builders do not
require an outbox. Send calls require one and raise if it was not supplied.

## Source calls

| Call | Supported arguments |
| --- | --- |
| ADD_INTPC | buffer, index, INTEGER value, status |
| ADD_REALPC | buffer, index, REAL value, status |
| ADD_STRINGPC | buffer, index, STRING value, status |
| ADD_BYNAMEPC | buffer, index, program, variable path, status |
| SEND_DATAPC | event number, buffer, status |
| SEND_EVENTPC | event number, status |

Buffers are one-dimensional ARRAYs of BYTE, with 1..244 elements. Named arrays,
fields and matching generic routine references retain their storage identity.
Builder buffers, index and status must be ordinary disjoint writable references.
The index is a 1-based INTEGER and must already be initialized. Each successful
builder writes one complete item and a two-byte zero end marker. It advances
the index to the marker's first byte, allowing the next builder to overwrite
that marker. Untouched prefix and tail bytes are retained, including unknown
unused BYTE values.

The complete item, marker and updated index are prepared before publishing
writes. Invalid index, insufficient remaining capacity and unrepresentable data
preserve the buffer and index. A builder can initialize portable missing whole
ARRAY storage; unrelated source reads still retain their initialization checks.
Direct source argument errors, protection/type violations and overlapping
references can raise before the operation's status is written.

## Wire format

Type tags are unsigned big-endian 16-bit values. Numeric payloads are also
big-endian, which differs from the runtime's default binary FILE/DAQ layout.

| Item | Tag | Payload |
| --- | --- | --- |
| INTEGER | 16, hex 0010 | Signed 32-bit value |
| REAL | 17, hex 0011 | Finite IEEE binary32 value |
| STRING | 209, hex 00d1 | One-byte text length, ASCII text, one NUL byte |
| End marker | 0, hex 0000 | No payload |

REAL values use practical float32 rounding; overflow and nonfinite data reject.
INTEGER storage retains the existing runtime bounds and MAXINT exclusion.
STRING length excludes its NUL terminator. Empty strings and embedded NUL
characters retain their explicit lengths. The available buffer space is checked
before writing; the largest string in a fresh 244-byte buffer is 238 characters.

For example, appending INTEGER 5 at index 1 writes `00 10 00 00 00 05 00 00`
and returns index 7. No native allocation, status or transport equivalence is
claimed by this representation.

## Named data

`ADD_BYNAMEPC` reads the selected INTEGER, REAL or STRING once before updating
the buffer and index. Program and path matching are case-insensitive. Blank
program uses the executing source module, including inside an explicitly linked
routine. Current/attached declared globals and explicit variable-store roots
support ordinary static fields and array indices whose selected leaf is one of
those three types.

Whole arrays, whole structures, BOOLEAN, BYTE and SHORT leaves are excluded
from named insertion. Use a direct builder with an explicit compatible scalar
expression when appropriate. System-variable paths are excluded, and no names
are discovered from a controller. Missing paths return status 1; incompatible
or uninitialized named data returns status 4 without changing the index/buffer.

## Typed and raw send modes

The default `PcExchange(packet_format='typed')` validates the common ADD_*
envelope, starting at the buffer's first byte. It publishes the used prefix
through the checked end marker. Unknown unused tail bytes after that marker
are ignored; unknown payload bytes, malformed strings, missing markers and
unsupported type tags reject the send. This is a chosen Pythonic policy: the
native SEND_DATAPC API does not validate arbitrary PC data formats.

For a custom byte protocol, use `PcExchange(packet_format='raw')`, or JSON
`{"pc_exchange": {"format": "raw"}}`. Raw mode requires every byte to be
initialized and publishes the entire buffer, including any embedded zero
markers. It does not infer lengths, trim tails or decode custom content.

SEND_DATAPC captures an independent buffer snapshot once, before evaluating
later output selectors. It is read-only in routine effect analysis. Builder
reference selectors and value arguments also evaluate once in source order;
the referenced in/out index is read when the builder operation begins. Active
FOR-counter, alias and ordinary source-protection rules remain in place.

## Outbox, statuses and consumption

Event numbers are integers in 0..255. A successful send adds a row with a
monotonic local sequence, event number and payload hex. Event-only sends use
`data: null`, distinct from a data message containing an empty typed packet
`data: "0000"`. Success means queued in this offline bank. There are no network
calls, delivery callbacks, GEMM sessions, retries or controller notifications.

The outbox capacity is 1..32767 events; the default is 1024. A full queue rejects
the new event without dropping old events or advancing the sequence. Host code
can inspect `bank.snapshot()` or consume detached rows with `bank.drain(count)`;
omitting count drains all rows. Draining preserves sequence history, so later
events continue numbering. Sequences are limited to 2147483646.

| Status | Portable meaning |
| --- | --- |
| 0 | Buffer item added or event queued |
| 1 | Named variable missing or excluded system path |
| 2 | Invalid/uninitialized index or event number |
| 3 | Insufficient buffer capacity for the item and marker |
| 4 | Unsupported, unknown or unrepresentable data/packet |
| 5 | Outbox full or publication sequence exhausted |

Failed sends retain the outbox and source buffer. Source type/protection checks
can raise instead of returning a status, including an invalid mutable buffer
passed through a generic formal. No native status-number mapping is inferred.

## Saved context and CLI examples

Context JSON preserves capacity, packet format, sequence history, ordered
messages and bounded payload hex, along with ordinary global variable values.
Loading checks event bounds, capacities, increasing sequences and packet format
before accepting messages. Saved typed messages contain exactly their used
prefix. Raw messages retain their complete bytes. No executable consumer or
external connection is restored.

The [typed example](../examples/pc_exchange.kl) exercises all six calls. The
[raw example](../examples/pc_custom_payload.kl) preserves a custom payload whose
first two bytes look like a typed end marker. Their completion flags prevent
additional events when replaying a successfully saved run; they do not model
crash recovery or transport acknowledgement.

```sh
python -m karel2py examples/pc_exchange.kl --check
python -m karel2py examples/pc_exchange.kl -o .local/pc_exchange.py
python .local/pc_exchange.py --context examples/pc_exchange.services.initial.json --state-out .local/pc_state.json
python .local/pc_exchange.py --context .local/pc_state.json --state-out .local/pc_state.json
```

Create `.local` before using the output paths. The report's `pc_exchange_policy`
and [semantic ledger](semantics/pc_exchange_semantics.json) record the contract.
Native transport, PC application behavior, controller scheduling and strict
equivalence remain future work.
