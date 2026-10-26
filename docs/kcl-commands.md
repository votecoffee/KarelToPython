# Scripted KCL command results

KCL, KCL_NO_WAIT and KCL_STATUS use an explicit KclCommands service. The service
records command requests and returns configured replies. It does not interpret
commands or execute them through a shell, host application or controller. For
example, a configured CLEAR ALL reply changes no variables or files.

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

## Failure and persistence

Once accepted, a pending request remains observable if its caller pauses, stops,
aborts or its wait fails. It is not cancelled or retried implicitly. This retains
the distinction between acceptance and collection. A later KCL_STATUS can collect
the same request without increasing the submission sequence.

`KclCommands.snapshot()` returns detached reply/history data and a pending
descriptor when present. Context save rejects pending work; collect it first.
Terminal configuration saves replies, bounded history, sequence and last status.
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
```

Use `rt.KclCommands(replies, ...)` with `ExecutionContext(kcl=...)` for host
scenarios. The standalone example uses zero delay for deterministic fixtures;
the linked project exercises virtual delayed completion and logical stack queries.

The report's `kcl_policy` and [semantics ledger](semantics/kcl_semantics.json)
record boundaries and evidence. There is no native KCL parser, command queue,
program/file/variable mutation, live transport or controller-runtime claim.
Native command execution and strict mode remain outside this milestone.
