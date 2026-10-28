# Finite offline serial streams

Pythonic FILE operations can use explicitly supplied serial endpoints through
`ExecutionContext.serial_streams`. The backend exchanges finite byte buffers;
it never opens a COM port, cable, device, socket or background reader.
An explicit per-port `wait=True` opts into [cooperative host-fed reads](serial-waiting.md)
with a `final` flag and `finish_input(port)`. The default remains finite input.

```python
from karel2py.runtime import ExecutionContext, SerialStreams

context = ExecutionContext(serial_streams=SerialStreams({
    2: {"capacity": 1024, "input": "21\n", "output": "pre:"},
}, limit=4096))
```

The equivalent context JSON uses canonical port-number strings:

```json
{
  "serial_streams": {
    "limit": 4096,
    "ports": {
      "2": {"capacity": 1024, "input": "21\n", "output": "pre:"}
    }
  }
}
```

The Python API accepts actual INTEGER port keys 1 through 5, excluding Booleans.
JSON accepts exactly string keys "1" through "5". A FILE name must be exactly
P1: through P5:, without a suffix, path or leading zero; case is folded. Numeric
P-device prefixes are reserved before ordinary file routing, so P02: or
P2:filename cannot silently open a literal MemoryFiles/DirectoryFiles entry.
Missing streams and unconfigured endpoints fail before opening.

MARRC75KR07091E Rev N sections 7.2.2, 7.2.3 and 16.3 describe serial FILE names
and communication ports. That edition describes P1 through P4 and controller-
specific connector restrictions. P5 is an explicit portable endpoint consistent
with this package's existing serial metadata constants. None of these offline
labels assert physical connector availability or repurpose a teach-pendant port.

## FILE behavior

```karel
OPEN FILE channel('RW','P2:')
READ channel(value,CR)
WRITE channel('answer=',value*2,CR)
CLOSE FILE channel
```

Each endpoint permits one live FILE, including across linked programs and tasks.
Different configured endpoints remain independent. OPEN preserves existing RX
and TX data. READ inspects RX bytes; WRITE appends to a separate retained TX
outbox and never echoes into RX, truncates old output or advances the RX cursor.

| Modes | Portable meaning |
| --- | --- |
| R, RO | Read only |
| W, WO | Write only, retaining old RX/TX |
| RW, UD | Independent input and appended output |
| A, AP, AO | Output-only append aliases |

An optional trailing B or ATR_UF selects existing binary FILE field handling.
AO is a portable append-output alias; the cited manual describes AP instead.
This backend does not implement AP's native first-operation/read-write rules or
UD's equal-length file replacement behavior. It always treats TX as an outbox.

Text/binary scalar widths, numeric validation, byte order, bounded STRING rules,
ATR_FIELD and explicit FILE ATR_EOL use the existing checked FILE parser.
ATR_REVERSE selects the existing binary byte order. Binary BYTE/SHORT/INTEGER/
REAL/BOOLEAN fields can carry raw bytes; binary STRING decoding still requires
ASCII. XML, PASSALL and pipe-specific FILE attributes are rejected. No parser,
native character encoding or implicit line editing is added.

The separate SerialPorts service retains baud/parity/data-bit/stop-bit/XON/OFF
and other metadata. It does not configure these byte streams. In particular,
GET_PORT_ATR/SET_PORT_ATR ATR_EOL does not silently change a FILE's terminator;
use SET_FILE_ATR explicitly. Streams perform no automatic echo, including when
ATR_NOECHO is absent.

## Atomic reads and close-time consumption

Successful READ operations advance the FILE's receive cursor. A complete READ
validates all outputs before publication. An incomplete or invalid later field
preserves that READ's outputs and starting cursor. Failed binary decoding also
rolls back its tentative byte progress. Input exhaustion fails immediately;
there is no producer wait, retry, timeout, host sleep or automatic acquisition.

RX bytes remain physically retained until explicit CLOSE. CLOSE consumes only
the prefix covered by the successful cursor and resets that closed handle's
cursor to zero. Remaining input survives for the next OPEN. CR bytes are consumed
only when the ordinary parser consumes them; no extra terminator is stripped.
A failed later READ therefore cannot discard its partial fields on close.

GET_FILE_POS reports the current relative RX cursor. BYTES_AHEAD/BYTES_LEFT
report currently unread RX bytes, independently of TX. SET_FILE_POS returns
portable status 2 without moving the cursor; serial seeking is unsupported.
Handles and byte operations validate endpoint identity, original registration,
mode, attributes and cursor bounds. Closed, copied, foreign or redirected
handles fail before changing either queue.

Pause, completion, abort, stop and runtime failure retain ordinary explicit FILE
lifetime. They do not automatically close the stream or consume pending RX.
Close the actual live handle before saving its context. No live FILE state or
suspended input operation is restored from JSON.

## Host queues and bounds

`bank.feed(port,data)` appends explicit input to a configured endpoint, including
while its FILE is open. `bank.take_output(port,count=None)` removes and returns
TX bytes; count must be an actual nonnegative INTEGER within the retained output.
These host calls never drive another task or create a connection. snapshot()
returns detached byte data keyed by actual integer port numbers.

The bank limit defaults to 4 MiB and accepts 1 byte through 64 MiB. Each endpoint
has a capacity from 1 through the bank limit, defaulting to that limit. A port's
combined retained RX+TX must fit its capacity, and actual bytes across all ports
must fit the bank limit. Capacities do not reserve memory in advance. RX that has
been read but not closed still counts toward capacity. Appends check both budgets
before adding any bytes. TX remains bounded until explicitly drained.

Constructor/configuration data accepts ASCII text, Python bytes, or an exact
hex object such as `{"hex":"00ff"}`. Saved configuration emits lowercase hex for
both queues and concrete capacities. Unknown fields, malformed data, noncanonical
JSON keys, invalid capacities and over-limit initial queues are rejected.

Live handles prevent to_config/context save. After close, JSON preserves the
remaining RX and retained TX outboxes; reopening starts a fresh cursor. It stores
no handles, baud/timing effects, native alarms, port-init state, task ownership,
callbacks or execution stacks. Physical serial I/O, native waiting/flow control,
controller timing/encoding and public strict mode remain outside this model.

See the authored cases in `tests/test_serial_streams.py`, the runnable
[serial-stream example](../examples/serial_streams.kl), and the separate
[serial metadata guide](serial-attributes.md).
