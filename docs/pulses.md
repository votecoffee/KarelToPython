# Offline digital output pulses

Version 0.91.0 adds PULSE statements and condition-handler actions over an
explicit PortBank. No background thread or physical output adapter is created.

```karel
PULSE DOUT[port_no] FOR milliseconds
PULSE DOUT[port_no] FOR milliseconds NOWAIT
```

Both operands are INTEGER expressions, evaluated once from left to right.
The output must belong to the supplied DOUT bank. A declared variable named
DOUT cannot stand in for that bank. Handler actions support the blocking form;
NOWAIT in an action is rejected during translation.

## Duration and waiting

Duration must be 0..86,400,000 milliseconds. Zero preserves the current value
and any existing pulse, without starting a timer or waiting. Existing pulses
can still expire through ordinary checkpoint polling. A positive duration
rounds upward to a multiple of eight milliseconds. The modeled pulse turns the
output on, then off at completion, including when it was already on beforehand.
The model uses the rounded duration deterministically; native scan jitter is
outside this implementation.

Without NOWAIT, PULSE waits through the existing DELAY driver. A standalone
Program calls its sleep callback with rounded seconds. Successful callback
completion finishes the logical pulse even when the callback only records the
delay. In a TaskScheduler, the task parks while other tasks can execute.

```python
from karel2py import translate, runtime as rt

ports = rt.PortBank({"DOUT": 1}, {("DOUT", 1): False})
context = rt.ExecutionContext(ports=ports)
namespace = {"__name__": "pulse_wait_demo"}
exec(translate("PROGRAM DEMO VAR after: BOOLEAN BEGIN PULSE DOUT[1] FOR 9 after=DOUT[1] END DEMO").python_source, namespace)
Program = namespace["Program"]
delays = []
program = Program(context=context, sleep=delays.append)
assert program.run()["AFTER"] is False
assert delays == [0.016]
assert ports.pending_pulses == 0
```

## NOWAIT and polling

NOWAIT starts a pulse and continues source execution immediately. A standalone
Program captures its supplied clock_us callback, or monotonic microseconds when
none is supplied. Clock values must be nonnegative INTEGER microseconds and
must not move backward for an active pulse.

Execution checkpoints, port reads, port snapshots and `ports.poll_pulses()`
service pending expirations. poll_pulses returns the number of outputs turned
off by normal expiration. pending_pulses reports the retained pending-record
count without advancing time. Direct access to the host's values dictionary
does not poll. There is no automatic expiry while the host is idle.

```python
from karel2py import translate, runtime as rt

clock = {"us": 0}
ports = rt.PortBank({"DOUT": 1}, {("DOUT", 1): False})
namespace = {"__name__": "pulse_nowait_demo"}
exec(translate("PROGRAM DEMO BEGIN PULSE DOUT[1] FOR 9 NOWAIT END DEMO").python_source, namespace)
Program = namespace["Program"]
program = Program(context=rt.ExecutionContext(ports=ports), clock_us=lambda: clock["us"])
program.run()
assert ports.read("DOUT", 1) is True
clock["us"] = 16000
assert ports.poll_pulses() == 1
assert ports.read("DOUT", 1) is False
```

Scheduled pulses always use scheduler virtual time, including when a Program
also has an injected clock for other features. Their captured clock remains
valid after the owner finishes. The scheduler polls shared banks and drains
its pending pulses when all tasks complete or pause. Idle steps can jump to
the next pulse/wait deadline. Use step() when intermediate states matter;
run() drains the scheduled work within its usual cycle budget.

The [linked example](../examples/pulse_project/main.kl) starts a pulse from a
library routine, observes the output on and then off, and shares one port bank:

```sh
python -m karel2py.project examples/pulse_project --entry MAIN --context examples/pulse_project/services.initial.json
```

## Ownership and failure behavior

| Event | Pythonic result |
| --- | --- |
| Normal owner completion | Pending NOWAIT pulse remains until polled or drained |
| Pause | Pulse can expire while the owner remains paused |
| Abort, terminal STOP or runtime failure | Preserve last modeled output value; discard the owner's pending record on polling |
| Successful direct/indirect/host write | Cancel that output's pending expiration and keep the new supplied value |
| Failed write | Preserve the existing value and pending pulse |
| Another pulse on a busy output | Reject before replacing the existing pulse |
| Context JSON save/load | Save observed values and existing metadata; pending clocks/owners/deadlines are omitted |

A linked routine's pulse belongs to its calling root task. An unrelated task's
failure does not cancel the owner's pulse. A blocking callback failure retains
completed host effects and the last output value; it is not retried. A sticky
ABORT prevents a new pulse from starting or completing after termination.

Clock errors, backward samples and recursive polling raise runtime errors.
Polling validates the batch of active clock samples before applying any normal
expirations. Arbitrary side effects inside a supplied clock/sleep callback are
outside rollback. Expiry records are removed by successful writes only after
the new address/value validates.

PULSE enables cooperative generation automatically. Existing step/cycle limits,
routine counter-write guards and handler ordering remain. Operands can read
active FOR counters. Blocking PULSE contributes to transitive routine delay
effects. Each start/wait operation records only operation, source line and
outcome in service_requests. A completed NOWAIT record means the pulse started;
it does not mean its deadline has passed.

The report exposes source-located pulses and pulse_policy. The authored
[blocking](../examples/pulse_wait.kl), [override](../examples/pulse_override.kl)
and linked examples have independent expected snapshots. The
[semantic ledger](semantics/pulse_semantics.json) records source locators and
the portable clock, override and lifecycle choices. Native polarity/complement
modes, scan jitter, physical timing, controller acceptance and strict mode
remain separate work.
