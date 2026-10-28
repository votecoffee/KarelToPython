# Cooperative serial input

Explicit offline serial streams can wait cooperatively for input. This is an
opt-in extension to [finite serial FILE I/O](serial-streams.md); existing ports
continue to fail immediately on incomplete input.

```python
from karel2py.runtime import ExecutionContext, SerialStreams

bank = SerialStreams({
    2: {"capacity": 1024, "input": b"", "wait": True},
}, limit=4096)
context = ExecutionContext(serial_streams=bank)

# A host driver or another explicitly scheduled callback supplies bytes.
bank.feed(2, b"21")
bank.feed(2, b"\n")
bank.finish_input(2)
```

Each configured port accepts actual BOOLEAN `wait` and `final` fields. `wait`
defaults to `False`; `final` defaults to `not wait`. A finite port requires
`final=True` and retains its existing feed behavior. A waiting port defaults to
`final=False` and accepts more input until `finish_input(port)` marks its input
complete. That operation requires `wait=True` and is idempotent. Subsequent feed
calls to a finalized waiting port fail, including empty feeds.

Context JSON uses the same fields under canonical port-number strings:

```json
{
  "serial_streams": {
    "limit": 4096,
    "ports": {
      "2": {
        "capacity": 1024,
        "input": "",
        "output": "",
        "wait": true,
        "final": false
      }
    }
  }
}
```

## Completion and publication

A waiting READ captures its writable scalar targets and format expressions once.
It probes the currently supplied RX bytes without publishing partial values,
advancing the receive cursor or recording successful input requests. When every
field is complete and valid, the ordinary checked READ publisher commits all
destinations and one input observation together, then advances the cursor once.

Nonfinal text uses the shared streaming FILE parser. An unformatted trailing
token or STRING needs its delimiter before publication. Short fixed-width fields,
unfinished quoted strings and requested but incomplete CR boundaries wait.
Malformed complete fields and non-ASCII text fail immediately. Explicit widths
and binary fields can complete as soon as their required bytes are available;
binary CR fields remain invalid. FILE ATR_EOL, ATR_FIELD, ATR_REVERSE and existing
scalar formats retain their checked parsing rules.

Once input is final, READ uses ordinary finite-file end-of-input rules. For
example, a final input of `"17"` can complete an INTEGER READ without a newline.
Missing later fields, unfinished quoted strings and short binary input fail and
preserve that READ's original destinations and cursor. Finalization does not
invent a line terminator or discard the incomplete prefix.

A fixed-width or binary READ that cannot fit within the port's retained RX
capacity fails before waiting. This check includes the successfully read prefix
that remains retained until CLOSE. Variable-length input remains subject to the
ordinary combined RX/TX capacity and bank byte budget; feed and WRITE reject
over-limit appends atomically.

## Scheduling and cancellation

An incomplete waiting READ uses 10 ms logical delay intervals and normal runtime
checkpoints. Scheduled tasks yield so an explicitly driven producer can feed
input or finalize the stream. Standalone execution requires an explicitly
injected sleeper callback before it may wait indefinitely. Merely using the
runtime's default host sleeper does not authorize an indefinite standalone wait.
The callback provenance follows same-task CALL_PROG and linked FROM routines.

Pause retains the pending READ, its captured references and its receive cursor.
Resume continues that operation. Stop, abort, budget failure, parser failure or
generator close removes the owned pending registration. These operations retain
ordinary explicit FILE lifetime: the actual handle remains open until CLOSE.
Closing it then consumes only previously successful input, preserving any
uncompleted READ prefix.

Each live handle permits one pending READ. Another READ, direct typed FILE READ,
raw byte read or CLOSE on that handle fails while it is pending. Byte-count
queries remain available, and an RW handle can append independent TX output.
SET_FILE_POS remains unsupported with portable status 2. Handle ownership,
registration identity, attributes, wait policy and unchanged starting cursor are
validated before each retry. No automatic reopening or cursor repair occurs.

## Persistence and boundaries

Live serial handles prevent context serialization, including after a stopped
pending READ. Close them explicitly before saving. Closed waiting streams save
their `wait` and `final` flags, remaining RX and retained TX. Finite streams keep
their original JSON and snapshot shape without added flags. Saved byte queues
use the existing lowercase hex representation. Pending registrations, references,
callbacks and execution stacks are never serialized.

This feature models explicit offline byte delivery. It opens no COM port,
device, socket, thread or background reader and does not implement baud rate,
flow control, native serial waiting or controller timing. SerialPorts metadata
does not silently configure this backend or its FILE terminator. See the
authored cases in `tests/test_serial_waits.py` and the finite compatibility cases
in `tests/test_serial_streams.py`.
