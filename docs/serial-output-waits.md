# Cooperative serial output and FILE cancellation

SerialStreams can retain a complete rendered WRITE while an explicit host driver
drains its TX outbox. The exact-BOOLEAN per-port `wait_output` option defaults to
false and is omitted from JSON/snapshots when disabled. It is independent from
the receive `wait`/`final` policy. No COM port, cable, socket, worker thread or
physical flow control is opened or inferred.

~~~python
from karel2py.runtime import ExecutionContext, SerialStreams

bank = SerialStreams({
    2: {"capacity": 4, "output": b"old", "wait_output": True},
}, limit=32)
context = ExecutionContext(serial_streams=bank)

drained = []
def driver(seconds):
    drained.append(bank.take_output(2))
    # Return None. This explicit offline driver drains bytes without device I/O.

# Construct the translated Program with context=context and sleep=driver.
~~~

~~~karel
OPEN FILE channel('WO','P2:')
WRITE channel('XY')
status=IO_STATUS(channel)
CLOSE FILE channel
~~~

The first WRITE cannot fit beside `old`. After the supplied driver drains it,
the outbox becomes `XY` in one append. A scheduler can instead wait at cooperative
checkpoints while explicit host actions drain bytes or source handlers cancel.
The standalone CLI examples have available capacity; the linked CLI projects
exercise actual waiting and timer-driven cancellation under the scheduler.

## Source capture and publication

Retranslate source to use the generated cooperative WRITE path. Pythonic scalar,
aggregate, binary and bound-default output now uses that path. Capture FILE
selection, source values and format expressions once, then render independent
immutable bytes and apply the configured text EOL once before waiting. Changes
to a value, ARRAY, selector or format variable during the wait cannot retarget or
rerender that payload. Other backends retain their existing immediate writes.
Legacy direct State.write_items calls remain synchronous and cannot secretly
start a wait.

A complete payload must fit beside the port's retained RX within its port/bank
limits even after TX is drained. Impossible payloads fail before waiting. Consumed
RX still counts until ordinary CLOSE; no new input reclamation is added. Port
and whole-bank availability are checked before one complete append, with no
partial write, ring truncation, extra output observation or RX cursor advance.

Blocked writes yield logical 10 ms delays and checkpoints. Standalone execution
requires an explicitly injected sleeper; the default host sleeper is rejected
before waiting indefinitely. Ordinary execution budgets remain active. A handler
may perform an immediately ready write but cannot enter a blocked TX wait.
Linked routines and same-task calls retain their calling-root driver rules.

## Cancellation and control

CANCEL FILE on the exact pending handle marks its captured WRITE. At the next
checked unwind, source continues after WRITE with portable IO_STATUS 6 and none
of its captured bytes appended. Prior TX and completed source effects remain.
Cancellation wins when a driver both drains TX and cancels in the same step.
Repeated cancellation is idempotent. Idle cancellation still affects no future
operation, and a later successful WRITE restores status zero.

One cooperative typed operation may be pending per FILE. Pending WRITE blocks
another typed READ/WRITE, direct writes, CLOSE, seek and flush until it unwinds.
Byte-count/status inspection remains available. Marking cancellation does not
make CLOSE safe inside the same handler; put CLOSE after the pending WRITE.
Existing immediate output during a waiting read retains its established rules
when output waiting is disabled. Direct backend generators have separate
lifetimes and cannot be canceled through the source-operation token.

Pause retains the captured bytes and registration. Canceling a paused writer
leaves it paused; resume performs the cancellation. Stop, sticky abort, execution
budget failure, sleeper errors and generator close release only exact owned
registrations. They do not automatically close FILEs or drain outboxes. Close
remaining live handles explicitly after source unwind where appropriate.

## Identity, persistence and boundaries

Before retry/publication/cancellation, validate the original handle, attributes,
RX cursor, calling-root identity, registration, port/bank mappings, retained RX/TX
objects and unchanged limits. Replaced operation tokens or registrations remain
reserved where their ownership is uncertain; no foreign slot is silently freed.
This is cooperative ownership checking, without concurrent host isolation.

The enabled flag and ordinary RX/TX data round trip through closed context JSON.
Live FILEs still prevent saving, including after cancellation has been requested.
No pending payload, token, callback, frame, clock, generator or source continuation
is saved or reconstructed. This is an authored offline model; native pending-WRITE
interrupts, hardware timing/status codes, baud/flow control and strict equivalence
remain unverified.

Reports expose `serial_output_wait_policy` and extend FILE cancellation metadata.
See [text output](../examples/serial_tx_text.kl),
[binary aggregates](../examples/serial_tx_binary.kl),
[bound output](../examples/serial_tx_default.kl),
[sequential writes](../examples/serial_tx_sequence.kl),
[linked cancellation](../examples/serial_tx_linked_cancel/main.kl),
[default cancellation](../examples/serial_tx_default_cancel/main.kl),
[regressions](../tests/test_serial_output_waits.py) and the
[semantic ledger](semantics/serial_output_wait_semantics.json).
