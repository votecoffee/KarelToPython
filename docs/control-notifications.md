# Semaphores, lifecycle recovery and error handlers

Version 0.81.0 implements the remaining basic Pythonic condition notifications:
SEMAPHORE, ERROR and POWERUP, plus NOPAUSE, NOABORT and NOMESSAGE actions.
Execution uses the existing cooperative checkpoints and explicit service context.
The [semantic ledger](semantics/control_notification_semantics.json) records
manual references and the portable choices below. Strict mode remains deferred.

| Source | Pythonic behavior |
| --- | --- |
| `POST_SEMA(n)` / `SIGNAL SEMAPHORE[n]` | Grant the oldest pending waiter or increment the available count. |
| `CLEAR_SEMA(n)` | Clear available tokens; preserve outstanding waits and granted reservations. |
| `SEMA_COUNT(n)` | Available tokens, or negative number of queued waiters when none are available. |
| `PEND_SEMA(n,max_time,time_out)` | Consume one token, wait cooperatively, or write timeout TRUE on expiration. |
| `SEMAPHORE[n]` | True when the semaphore has an available token; checking does not consume it. |
| `ERROR[n]` / `ERROR[*]` | Observe a new matching error notification for the running task. |
| `POWERUP` | Observe an explicit host recovery continuation of a paused instance. |
| `NOPAUSE` / `NOABORT` | Cancel a pending pause/abort request before it becomes terminal. |
| `NOMESSAGE` | Mark the matched error record suppressed while preserving it in history. |

## Counting semaphores

Select the bank size explicitly. Unspecified counters in that bank start at zero;
no controller count is discovered. The count is 1..32767 and each nonnegative
available value is bounded by the normal stored INTEGER range.

```python
from karel2py import translate, runtime as rt

context = rt.ExecutionContext(semaphores=rt.SemaphoreBank(2, {1: 1}))
namespace = {"__name__": "semaphore_demo"}
source = "PROGRAM DEMO VAR timeout: BOOLEAN BEGIN PEND_SEMA(1,0,timeout) END DEMO"
exec(translate(source).python_source, namespace)
Program = namespace["Program"]
program = Program(context=context)
assert program.run()["TIMEOUT"] is False
assert context.semaphores.value(1) == 0
```

JSON configuration is `{"semaphores":{"count":2,"values":{"1":1}}}`.
ExecutionContext save/load preserves quiescent counters. Saving with outstanding
wait tickets raises, because a value snapshot cannot restore suspended execution.
`snapshot()` reports touched counters, including negative queued-wait counts.

`max_time` is milliseconds: -1 waits until a token arrives, zero tests immediately,
and positive values are bounded at one day. The output must be a writable BOOLEAN.
Available/granted tokens are checked before timeout, so an already granted token
wins at the deadline. Waiters use FIFO order. A granted waiter reserves its token
until it writes the output; cancellation returns that reservation to the next
waiter or the bank. Stopping, aborting or failing a waiting task removes its ticket.
Clearing a bank does not cancel waits or revoke granted tickets.

With TaskScheduler, waits use virtual time and yield at checkpoints with at most
one quantum between polls. A standalone Program uses a 1 ms sleeper callback and
the connected-timer clock. Budgets remain active for indefinite waits. An injected
clock used for a timed standalone wait must advance. Semaphore methods and source
operations are atomic between cooperative yields; they are not thread locks.

SIGNAL EVENT and SIGNAL SEMAPHORE perform a checkpoint after signaling, including
when the signal is the program's final statement. SIGNAL SEMAPHORE is a posting
operation; an ordinary SEMAPHORE condition is a non-consuming observation.
See the [authored semaphore example](../examples/offline_semaphores.kl).

## Error notifications

`POST_ERR(error_code,parameter,cause_code,severity)` retains the manual's argument
order. Error/cause codes are nonnegative INTEGERs; the parameter is bounded ASCII.
The portable severities match its documented three choices:

| Severity | Effect within the shared offline context |
| --- | --- |
| 0 | Record a warning and scan handlers. |
| 1 | Request pause of the caller and registered active/paused tasks. |
| 2 | Request abort of those tasks. |

No native motion, alarm dictionary, task outside the context or controller is
affected. Requests take effect at cooperative checkpoints. A scheduler abort
raises at the first aborted task; other pending requests remain for the next
drive. Paused standalone targets require continuation to process a pending abort.
Inspect or explicitly stop them when ending a drive after an error.

```karel
PROGRAM ERROR_DEMO
VAR marker: INTEGER
BEGIN
  marker=0
  CONDITION[1]:
    WHEN ERROR[15018] DO NOMESSAGE,NOABORT,marker=7
  ENDCONDITION
  ENABLE CONDITION[1]
  POST_ERR(15018,'authored',0,2)
END ERROR_DEMO
```

This completes with MARKER=7 and a retained suppressed error record. It does not
assert that native MOTN-018 can be recovered this way. A posted code is data in
this runtime; native alarm side effects and severity encodings outside POST_ERR's
0/1/2 form are not inferred. POST_ERR_L remains unsupported.

ErrorHistory is created lazily, or supplied with `ExecutionContext(errors=...)`.
`ErrorHistory(limit=1000)` retains the newest records with increasing IDs.
`snapshot()` returns defensive copies. Each record includes code, parameter,
cause, severity, program scope, source line, origin and suppression state.
ExecutionContext JSON save/load preserves the bounded history. Example context:
`{"errors":{"limit":1000,"records":[]}}`.

For host notifications, `context.errors.post(17,program="MAIN")` records an event
for that task. Omit program for a context-wide event. Its severity field records
data; host insertion does not itself drive or control a task. Source POST_ERR
does apply the pending control requests described above.

ERROR conditions consume matching record IDs independently per expression and
handler. Multiple matches between scans coalesce to the newest retained record.
Records posted before a new run can satisfy its first scan, because consumer
cursors reset at run start. This is the same portable latched convention as EVENT;
native scan-time-only notification is not modeled. A very small history limit can
evict an error before an unscanned consumer sees it.

## Runtime failures stay failures

Cooperative Programs notify handlers of KarelRuntimeError using portable code 1,
origin `runtime`, and the current task's program scope. This code does not map
the exception to a native alarm. Notifications occur at the generated execution
boundary after failed routine/FOR frames unwind. Earlier effects remain; a failed
assignment and later statements are not retried or silently continued.

ERROR handlers may observe the failure and perform their ordinary checked actions.
NOMESSAGE marks the record, and NOABORT can clear a pending control request, but
neither suppresses the original runtime exception. If a handler itself fails,
the original exception is retained with a diagnostic note. Exhausted step budgets
record the error without executing additional handler actions. Explicit ABORT or
STOP in a handler still takes precedence as an intentional termination.

This notification path applies to cooperative Programs; ordinary Programs without
handlers/cooperative generation retain direct runtime exceptions. Arbitrary Python
exceptions, KeyboardInterrupt and process failures are not converted into native
or resumable errors.

## Recovery and handler actions

NOPAUSE and NOABORT operate on pending requests, including requests from linked
library routines. A sticky terminal KarelAbort cannot be undone by NOABORT.
NOMESSAGE keeps the audit record and marks it suppressed; this runtime has no
native alarm UI to clear. These three forms are accepted only inside handler
action lists. EVAL in an action captures an independent value at handler definition,
just as it does in a predicate. Pythonic operand/callback ordering still applies.

POWERUP requires an explicit host recovery call:

```python
from karel2py import translate, runtime as rt

namespace = {"__name__": "powerup_demo"}
source = """PROGRAM DEMO VAR n: INTEGER BEGIN
n=0
CONDITION[1]: WHEN POWERUP DO n=7 ENDCONDITION
ENABLE CONDITION[1]
PAUSE
END DEMO"""
exec(translate(source).python_source, namespace)
program = namespace["Program"]()
try:
    program.run()
except rt.KarelPause:
    pass
assert program.powerup()["N"] == 7
```

For scheduled tasks use `scheduler.powerup(name)` or
`continue_task(name,powerup=True)`, followed by `run`. Ordinary resume signals
CONTINUE without POWERUP. Explicit powerup signals both. Recovery requires a
paused, still-live instance; it does not restore a process lost to actual power
failure or reconstruct a call stack from JSON.

Native interrupt priorities, motion UNTIL handlers, physical stop/resume,
POST_ERR_L severity constants, alarm dictionaries and suspended-process recovery
remain separate work. See [portable projects](portable-projects.md) for scheduling,
linkage and persistence, and the
[error-handler example](../examples/offline_error_handlers.kl) for expected state.
