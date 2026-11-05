# Offline KCL commands

KCL, KCL_NO_WAIT and KCL_STATUS use an explicit KclCommands service. The service
records command requests and returns configured replies. With a separate opt-in
it can also dispatch a small set of task controls to the offline registry.
A configured CLEAR ALL reply changes no variables or files.

```json
{
  "kcl": {
    "replies": {
      "SHOW PROGRAMS": {"accept_status":0,"status":17,"delay_ms":5}
    }
  }
}
```

```karel
KCL_NO_WAIT('SHOW PROGRAMS',accepted)
result=KCL_STATUS
```

KCL(command, status) waits for its configured completion result. KCL_NO_WAIT
returns the acceptance result; a later bare KCL_STATUS or KCL_STATUS() collects
completion. A status query captures the accepted request current when it begins;
it does not resubmit that command. KCL_STATUS without a prior or explicitly
configured result raises an error instead of inventing success.

## Requests and completion

Commands require 1..126 printable ASCII characters. Outer spaces are trimmed;
case and internal spacing match configured replies exactly. At most 256 reply
entries are configured. Replies require an ordinary INTEGER status and optionally
accept_status (default zero) and delay_ms (0..86400000, default zero).

One accepted command can be pending on the shared context channel. Zero delay
completes immediately. Configured nonzero acceptance rejects the request without
starting a job. Unconfigured commands return portable status 1; submissions while
an earlier command is pending return portable busy status 2. These portable codes
are not native alarm numbers. Configured completion/acceptance values are supplied
scenario data, not measured controller outcomes.

Scheduled waits use the existing virtual clock and sleep events. Standalone waits
use the captured clock and existing sleeper callback; callback completion is the
logical wait-completion signal, consistent with other offline waits. A pending
reply whose clock has elapsed can be collected by a later request/status call or
explicit host `poll()`. There is no background thread or automatic host action.

A blocking caller receives its own accepted reply even when another task later
submits a new command. The channel's last completed status is context-wide. Busy
submissions do not replace an accepted pending result. Ordinary output capture,
type, alias, overlap and active-counter guards continue to apply.

## Registered task commands

Set `"task_commands": true` in the `kcl` context section or pass
`task_commands=True` to KclCommands. Exact scripted replies take precedence.
The task forms accept case-insensitive verbs and names separated by spaces.
Names use one ASCII identifier with an initial letter. Tasks must already
be bound through the host registry or supplied as linked project modules.

| Form | Offline effect |
| --- | --- |
| `RUN name` | Start a fresh task at main entry or continue its existing pause. A fresh launch is independent of the caller. |
| `CONTINUE name` or `CONT name` | Resume the selected paused task and its eligible RUN_TASK descendants. |
| `CONTINUE ALL` or `CONT ALL` | Resume registered paused tasks once, coalescing aliases and paused parent/child paths. |
| `PAUSE name` or `PAUSE ALL` | Request pause on eligible running or waiting tasks at their checkpoints. |
| `ABORT name` or `ABORT ALL` | Request abort on eligible running, waiting or paused tasks. |

`FORCE` can follow a named or ALL PAUSE/ABORT selector to override the
corresponding command mask. A masked request still completes successfully.
Self pause and abort publish their result before delivering the request at
the caller checkpoint. An ALL command with no eligible targets succeeds.
An aborted or stopped task requires a new Program instance.

With a TaskScheduler, RUN and CONTINUE complete at admission and execution
continues on the scheduler. Standalone KCL drives a selected task synchronously
to completion, pause or intentional termination. Standalone KCL_NO_WAIT can
submit PAUSE and ABORT. Its RUN and CONTINUE forms require a TaskScheduler.
Pending scripted commands and synchronous task dispatches share the busy channel.
A task cannot collect the result of a KCL command that is currently driving it.

For these forms, 0 means accepted or completed successfully. Status 3 means
the target or driver is unavailable or ineligible. Status 4 means a supported
command encountered an admission or synchronous execution error. KCL_NO_WAIT
returns acceptance and KCL_STATUS returns completion. A later scheduled task
failure belongs to that task's scheduler. Unsupported text and busy submissions
retain statuses 1 and 2.

The modeled forms follow MARRC75KR07091E Rev N, PDF pages 283–284, 450–452,
705–706, 710, 724 and 728. The offline task bank keeps explicit binding,
continuation and terminal-state rules. Native default selectors, abbreviated
verbs beyond CONT, command files, TP execution and physical motion remain
outside this model.

## Failure and persistence

Once accepted, a pending request remains observable if its caller pauses, stops,
aborts or its wait fails. It is not cancelled or retried implicitly. This retains
the distinction between acceptance and collection. A later KCL_STATUS can collect
the same request without increasing the submission sequence.

`KclCommands.snapshot()` returns detached reply/history data and a pending
descriptor when present. Context save rejects pending work; collect it first.
Terminal configuration saves replies, bounded history, sequence and last status.
It also retains the task command opt-in when enabled.
Reloading that terminal state starts no jobs and replays no commands. Calling the
source again is a new explicit source execution, not automatic replay.

History retains the latest limit rows (default 500, maximum 4096), each with
sequence, owner task program, operation, normalized command, phase and status.
Phases are pending, completed, rejected, unsupported or busy; saved history must
contain terminal phases. Sequence exhaustion fails before a new submission.

## CLI and reports

```sh
python -m karel2py examples/kcl_commands.kl -o kcl_commands.py
python kcl_commands.py --context examples/kcl_commands.services.initial.json --state-out kcl-state.json
python -m karel2py.project examples/diagnostics_commands_project --entry MAIN --context examples/diagnostics_commands_project/services.initial.json --state-out project-state.json
python -m karel2py.project examples/kcl_task_commands --entry MAIN --context examples/kcl_task_commands/services.initial.json
```

Use `rt.KclCommands(replies, ...)` with `ExecutionContext(kcl=...)` for host
scenarios. The standalone example uses zero delay for deterministic fixtures;
the linked project exercises virtual delayed completion and logical stack queries.
The task commands example starts a worker independently, inspects its parent
number and continues its pause through KCL.

The report's `kcl_policy` and [semantics ledger](semantics/kcl_semantics.json)
record the accepted command forms and evidence. Native KCL, shell execution,
file and variable commands, live transport and strict mode remain outside this
milestone.
