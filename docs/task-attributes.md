# Task attributes, policies and traces

Version 26.1024.141821 adds SET_TSK_ATTR, seven task directives, applied task
settings and bounded checkpoint traces. The source signature is
`SET_TSK_ATTR(name,attribute,value,status)`. The host equivalent,
`tasks.set_attribute(name,attribute,value)`, returns status and accepts a named
attribute or its package INTEGER identifier on TaskRegistry and TaskScheduler.

Source operands require STRING, INTEGER, INTEGER and an exact writable INTEGER
status. Each operand/selector evaluates once in source order. Initialization,
type, FOR-counter and output-reference guards apply before a setting changes.

## Settings and selection

| Attribute | Accepted value | Offline effect |
| --- | --- | --- |
| TSK_PRIORITY | 1..99 | Lower numbers run earlier in the next scheduler round; ties retain binding order. |
| TSK_TIMESLIC | 1..1000 ms | Bounded checkpoint budget for each scheduled turn. |
| TSK_NOABORT | Mask 0..3 | Suppress new error/command abort requests by origin. |
| TSK_NOPAUSE | Combination of bits 1, 4 and 8 | Suppress new error, command and explicit TP-enable pause notifications. |
| TSK_TRACE | 0 or 1 | Disable/enable checkpoint records in the calling root's buffer. |
| TSK_TRACELEN | 1..10000 | Retain this many newest records, trimming immediately on shrink. |
| TSK_PAUSESFT | 0 or 1 | Ignore/accept explicit shift-release pause notifications. |
| TSK_NOBUSY | 0 or 1 | Readable busy-lamp capability metadata; no physical output. |
| TSK_TPMOTION | 0 or 1 | Readable pendant-motion capability metadata; no motion execution. |

Other known attributes are read-only to this setter. Applied settings override
matching GET_TSK_INFO reads without rewriting informational bind metadata.

| Status | Meaning |
| --- | --- |
| 0 | Setting applied |
| 1 | Explicit task name was not found |
| 2 | Unknown attribute or invalid value |
| 3 | Read-only attribute, unavailable/ambiguous self, or foreign active scheduler |

Names follow [task renaming](task-renaming.md): case-insensitive bindings, with
only the empty string selecting the uniquely registered calling root. Linked
routines use their caller; aliases share the Program's policy. Active tasks must
be changed through their owning scheduler. Ready, paused, waiting and terminal
bindings can be configured without driving them.

## Source directives

These directives precede declarations, cannot repeat and enable cooperative
generation automatically:

```karel
PROGRAM POLICY_EXAMPLE
%PRIORITY=20
%TIMESLICE=3
%NOABORT=ERROR+COMMAND
%NOPAUSE=ERROR+COMMAND+TPENABLE
%NOBUSYLAMP
%NOPAUSESHFT
%TPMOTION
VAR count: INTEGER
BEGIN
  count=1
END POLICY_EXAMPLE
```

Numeric directives use unsigned literals within the ranges above. Masks accept
unique named flags joined by `+`. The three flag directives take no arguments;
NOPAUSESHFT sets TSK_PAUSESFT to zero. No expression evaluation or native enum
lookup occurs. Immutable Program.source_directives retains normalized pairs;
Program.task_settings returns a defensive copy of applied values. Later setters
override initial policy. Library directives configure the library's own task
without overwriting callers during FROM linkage.

## Scheduling

The default remains one checkpoint per binding per round, in binding order,
with a 1 ms virtual quantum. Priority changes the next round's order; every
runnable binding still receives a turn. Task numbers retain binding order.

A time slice gives `ceil(value_ms / quantum_ms)` checkpoint advances per turn,
at most 1000. The budget is captured at turn start. Sleeping, pausing, completion
or failure ends the turn immediately. Time advances once by the quantum after
the round; extra checkpoint work does not advance the clock within a turn.
DELAY, connected timers, pulse deadlines and step/cycle limits retain that
virtual-time model. Unconfigured tasks retain one-checkpoint turns. Synchronous
execution stores slice settings for a later scheduler without CPU timing control.

This is a Pythonic approximation. Native preemption, wall-clock CPU duration,
priority starvation and controller interrupt ordering remain outside the model.

## Pause and abort masks

Use package constants rather than native numeric encodings:

| Constant | Bit | Use |
| --- | --- | --- |
| PG_NP_ERROR | 1 | Error requests, either attribute |
| PG_NP_CMD | 2 | Abort commands, TSK_NOABORT |
| PG_NP_END | 4 | Pause commands, TSK_NOPAUSE |
| PG_NP_TPENB | 8 | Explicit TP-enable pause, TSK_NOPAUSE |

Named/numeric task control and Program.pause() issue command requests.
POST_ERR/POST_ERR_L issue error requests. Suppression affects new requests only;
it does not clear pending requests, remove error records, suppress ERROR
notification or resume paused tasks. A suppressed command returns success.
Handler actions retain their existing pending-request suppression rules.

Bare PAUSE/ABORT, runtime failures and explicit host stop retain their behavior.
No mask turns a runtime exception into success. Hosts can supply explicit
notifications with `rt.request_task_control(program._state,'PAUSE',origin='shift')`
or `origin='tpenable'`; no keyboard/pendant state is discovered. Native lock-group
eligibility and motion restrictions are not inferred for offline policies.

## Trace inspection and CLI export

Enable TSK_TRACE explicitly; this supplies default TSK_TRACELEN 1000 unless a
limit was already applied. Program.task_trace returns independent dictionaries
containing sequence, source program, routine and line. Sequences increase as
checkpoints are recorded; trimming keeps newest entries. Linked routines write
into the caller's buffer with library source identity. Values and arguments are
not recorded. Disabling trace retains history; a new run clears records and
sequence while keeping settings. Pause/resume, rename and completion retain it.

```sh
python -m karel2py.project examples/task_policies_project --entry MAIN --trace-out task-trace.json
```

The CLI atomically writes separate `karel2py.task-trace.v1` JSON containing app
version and per-binding source identity, state, settings and records. It requires
execution and a path distinct from source, context and state output. Execution
failure saves available partial traces then reports the original failure. If
export also fails, the original failure remains primary with an explanatory note.
ProjectInstance.trace_snapshot() returns the same detached document for embedding.

Settings, traces, bindings and continuations remain live host state, omitted from
ExecutionContext value JSON. Trace export is separate from the future runner
input/result JSON milestone. The [authored project](../examples/task_policies_project/main.kl)
exercises directives, settings and error/command masks. The
[semantic ledger](semantics/task_attribute_semantics.json) records manual pages
and portable choices. Reports include task_attribute_policy, directive_policy
and named masks in task_inspection_policy.constants.
