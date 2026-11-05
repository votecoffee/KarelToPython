# Task requests, scoped errors and field reads

Version 0.82.0 completes these Pythonic gaps using the existing offline context.
The examples are authored fixtures. Manual syntax informs the implementation;
native enum values, task timing and device behavior remain unverified.

## Task requests

Named `PAUSE_TASK`/`ABORT_TASK` and numeric `PAUSE PROGRAM[n]`/`ABORT PROGRAM[n]`
use the same pending-request mechanism. Self requests also work inside linked
library routines: the caller owns the task identity. Status is written before
a named self request is delivered, so its handlers can read that status.

Remote requests run at the target's next checkpoint. ABORT wakes a paused
scheduled task to scan its ABORT handlers before termination. NOPAUSE/NOABORT
can suppress pending requests; a terminal abort remains sticky. A paused
standalone target needs `resume()` or CONT_TASK to process the request. An
inactive target with no live frames becomes aborted immediately. Stopping,
aborting or failing a task unwinds frames and removes its semaphore wait tickets.

For TaskRegistry, RUN_TASK and CONT_TASK drive the child synchronously until
completion, pause or intentional ABORT/STOP. Child ABORT/STOP returns control to
the caller with status 0; a child runtime failure still propagates. With
TaskScheduler, a terminal ABORT/STOP raises at the affected task's step. Inspect
the task states and drive again to process remaining work or pending requests.

Self CONTINUE, bare or numeric, scans handlers after incrementing its lifecycle generation,
including when it is the final source statement. POWERUP and ordinary resume
retain their [existing contracts](control-notifications.md#recovery-and-handler-actions).

### Forced and broadcast requests

`PAUSE_TASK(name,force_sw,stop_mtn_sw,status)` and
`ABORT_TASK(name,force_sw,cancel_mtn_sw,status)` queue task requests. For a
named target, `force_sw=TRUE` bypasses its command ignore mask. Delivery still
uses the task's checkpoint and its NOPAUSE or NOABORT action can clear the
pending request. A false force switch applies the ordinary command mask.

Use the case-insensitive name `*ALL*` to select each eligible live root once
in binding order. PAUSE selects running and waiting tasks. ABORT also selects
paused tasks and wakes a paused scheduled target to scan its handlers.
A TaskScheduler selects the live executions it owns. A TaskRegistry selects
its registered live standalone executions. The broadcast honors each command
mask regardless of the force argument. An included caller scans its own
request after the whole batch is queued.

Status 0 acknowledges an accepted request, including a suppressed request or
empty broadcast. Status 1 reports a missing named binding. MARRC75KR07091E Rev N,
PDF pages 302 and 474, describes the force switches and wildcard selection.

See the linked [pause and force example](../examples/task_broadcast_pause/main.kl)
and the [abort handler example](../examples/task_broadcast_abort/main.kl).

### Logical motion flags

`PAUSE_TASK(...,TRUE,status)` in the motion-switch position applies the
portable HOLD transition. `ABORT_TASK(...,TRUE,status)` in that position
applies the portable CANCEL transition. These effects require the caller's
explicit MotionRequests and GroupLocks. Each affected live target must share
those banks and belong to the registered task driver.

The command selects every group owned by each eligible target. A masked
request has no motion effect. A live target with no owned groups adds no
motion history row. For broadcasts, the full batch must pass group
configuration, exact active-grant and history-capacity checks before any status,
motion transition or task request is published. The check uses the most recently
observed logical state and runs without advancing motion clocks.

HOLD freezes queued progress and stays set through task continuation until
explicit UNHOLD. CANCEL clears executing labels and cancels their active and
queued work using the existing motion-control rules. Stopped labels and hold
flags retain their existing CANCEL treatment. A synchronous or scanning scope
unwinds at its own checked continuation.

The motion action commits when the command is accepted. A later NOPAUSE or
NOABORT handler can clear the task request while the motion transition remains
committed. History records the target task as owner, the requester's source
module and line, and the complete selected group list. The first selected group
labels that row.

See the linked [hold example](../examples/task_motion_pause/main.kl) and
[cancel example](../examples/task_motion_abort/main.kl). The
[motion control guide](motion-controls.md) describes the offline state model.

### RUN_TASK entry and continuation

`RUN_TASK(task_name,line_number,pause_on_sft,tp_motion,lock_mask,status)`
uses the explicit task registry. A fresh KAREL task begins at its main entry for
any nonnegative line hint. The existing portable pause flag suspends a fresh task
before its first statement. A rejected standalone start restores the prior pause
request, so retrying can use its own launch policy.

Calling RUN_TASK again on a paused target resumes the existing execution. Its
frames, pending delays, group ownership and budget stay with that execution.
The start-pause flag applies only to fresh entry. Both RUN_TASK continuation
and CONT_TASK advance the CONTINUE notification once. A scheduler can continue
only the live paused tasks it owns. A fresh RUN_TASK inside the same driver
also records a live parent for [GET_TSK_INFO](task-inspection.md#live-lineage-and-group-masks).
That relationship follows the exact calling and child runs.

An unknown binding returns status 1. An accepted start or continuation returns
status 0 under the driver rules above. A negative line hint raises. The offline
form requires `tp_motion=FALSE` and `lock_mask=0`. The caller and child keep their
separate task identities.

MARRC75KR07091E Rev N, PDF pages 529–530, describes continuation of an already
paused task and reserves the line selector for teach pendant programs. The
Pythonic mapping uses main entry for KAREL. See the linked
[continuation example](../examples/run_task_resume/main.kl) and
[pause-on-entry example](../examples/run_task_entry_pause/main.kl).

### Continuing a parent task

Continuing a paused parent also continues its paused RUN_TASK descendants.
The request follows paused child links in the same driver. Each link belongs
to the exact live runs that established it. Aliases share a continuation and
a new parent run cannot resume children left over from an earlier run.

Host resume, remote numeric CONTINUE, CONT_TASK, and RUN_TASK on a paused
target use this behavior. POWERUP recovery sends POWERUP to the selected task
and ordinary CONTINUE to its paused descendants. Each selected task keeps
its existing frames, pending waits and resource ownership.

The scheduler makes the selected tasks runnable together and uses its regular
priority and round ordering. The synchronous registry captures the paused
descendants at request time, advances the parent, then visits the captured
tasks in breadth-first registry order. A child already advanced by the parent
keeps its new continuation. A runtime failure stops the synchronous drive and
propagates after any effects already committed. Bare or self CONTINUE remains
a local lifecycle action.

See MARRC75KR07091E Rev N, PDF page 283, section 17.5.2, and the authored
[parent continuation example](../examples/task_family_continue/main.kl).
Native STEP propagation is outside this model.

## POST_ERR_L

`POST_ERR_L(code,parameter,cause,severity)` accepts predefined ERSEV names. Codes
are nonnegative INTEGERs and the parameter is bounded ASCII, as for POST_ERR.
The numeric IDs below are **portable package constants**, independent of native
controller encodings. Use the names in source instead of imported numeric values.

| Constant | Portable ID | Offline effect | Scope |
| --- | --- | --- | --- |
| ERSEV_NONE | 0 | Record/notify | Shared context |
| ERSEV_WARN | 1 | Record/notify | Shared context |
| ERSEV_PAUSE | 2 | Pause request | Shared context |
| ERSEV_PAUSEL | 3 | Pause request | Calling task |
| ERSEV_STOP | 4 | Pause request | Shared context |
| ERSEV_STOPL | 5 | Pause request | Calling task |
| ERSEV_SERVO | 6 | Pause request | Shared context |
| ERSEV_SERVOL | 7 | Pause request | Calling task |
| ERSEV_ABORT | 8 | Abort request | Shared context |
| ERSEV_ABORTL | 9 | Abort request | Calling task |
| ERSEV_SYSTEM | 10 | Abort request | Shared context |

Shared control requests target the caller and registered active/paused tasks.
Global records are visible to other consumers in that context. Local records
are scoped to the caller's root program, including when posted from a library.
ERROR handlers may suppress the pending effects using NOPAUSE/NOABORT and mark
the retained record with NOMESSAGE. STOP/SERVO variants use offline pause;
SYSTEM uses global abort. Physical motion, servo power and controller lockout
are outside this runtime.

History stores normalized severity 0/1/2, plus `operation="POST_ERR_L"`,
`severity_name` and `source_program`. A local record's `program` identifies the
calling task; `source_program` identifies the posting library/program. These
fields survive context JSON save/load. Existing POST_ERR records retain their
schema and its 0/1/2 input convention. See the
[scoped error example](../examples/scoped_error.kl).

## Field and record reads

Set attributes before OPEN FILE. `ATR_FIELD` makes an unformatted ASCII STRING
read exactly its declared capacity; `::width` overrides that capacity. A zero
width uses the capacity in field mode, including quoted `::0::2` fields. A short
field raises; it does not read across a record separator. INTEGER, REAL and
BOOLEAN defaults remain token based. This keeps Pythonic parsing practical
without inventing fixed numeric field widths.

Without ATR_FIELD, an unformatted STRING consumes the rest of the record before
destination truncation. Explicit widths and CR keep their existing meanings.
ATR_FIELD affects reads only. Binary mode retains its existing byte widths and
ignores text EOL handling.

ATR_EOL selects the ASCII byte written by CR and recognized by text READ.
Codes 10 and 13 accept CR, LF or CRLF on input for newline compatibility. Other
codes select exactly that byte, including NUL; embedded CR/LF can then be STRING
data. READ CR consumes the selected record boundary. File positions count
actual bytes, including both bytes of CRLF. Separate reads start at the last
committed byte position. A failed text transfer preserves all destination
values and the file cursor and sets portable I/O status 1.

MemoryFiles and DirectoryFiles share the same parser. The
[field example](../examples/file_fields.kl) writes `abcdef;ghijkl;`, then reads
four three-character fields with record-end positions 7 and 14.

For direct embedding, `TextInput(text,terminator=None,field_mode=False)` exposes
the same parser options. `offset` is its exact consumed ASCII byte count;
`position` retains line/column/EOF information. Direct adapter failures can
consume adapter input; FILE commits its cursor only after successful validation.

See the [service ledger](semantics/extended_service_semantics.json) and
[notification ledger](semantics/control_notification_semantics.json) for source
references and remaining native boundaries. Strict mode remains deferred.
