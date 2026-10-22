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

The `no_wait` Boolean is accepted, but both values queue the same cooperative
request. There is no native acknowledgment wait. Motion flags are rejected.
For TaskRegistry, RUN_TASK and CONT_TASK drive the child synchronously until
completion, pause or intentional ABORT/STOP. Child ABORT/STOP returns control to
the caller with status 0; a child runtime failure still propagates. With
TaskScheduler, a terminal ABORT/STOP raises at the affected task's step. Inspect
the task states and drive again to process remaining work or pending requests.

Self CONTINUE, bare or numeric, scans handlers after incrementing its lifecycle generation,
including when it is the final source statement. POWERUP and ordinary resume
retain their [existing contracts](control-notifications.md#recovery-and-handler-actions).

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
