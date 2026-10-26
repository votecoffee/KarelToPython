# Same-task KAREL program calls

Pythonic mode implements `CALL_PROG(name,index)` and
`CALL_PROGLIN(name,line,index,pause_entry)` for explicitly attached cooperative
KAREL programs. A program call runs the target's main body in the calling task.
It can select a program at runtime and returns to the statement after the call.

Use the [authored linked example](../examples/program_calls_project/main.kl)
through the project CLI:

```sh
python -m karel2py.project examples/program_calls_project
python -m karel2py.project examples/program_calls_project --entry MAIN --context examples/program_calls_project/services.initial.json
```

Project inputs are translated cooperatively and explicitly attached in one
context. With the Python API, translate targets using `cooperative=True`, create
them with the same `ExecutionContext`, and retain the resulting Program objects.
Constructing them attaches their source namespaces; it executes no statements.
Calls themselves enable cooperative generation in the caller automatically.

## Execution and scope

The target name is a case-insensitive ASCII program identifier, up to 36
characters. The target must be an attached cooperative Program, rather than an
internal/external routine, an opaque teach program, a supplied catalog entry or
a native compiled file. No code is loaded from JSON, the filesystem or a robot.

Each call has its own execution cursor and routine frames. The called module's
globals, including imported aliases, remain shared. Repeated and concurrent
calls therefore retain global data while keeping their suspended stacks
separate. Calls do not start, reset, resume or replace the target's independently
registered task. Self-calls are supported with separate cursors and shared data;
combined program/routine depth is limited to 64.

Calls share the caller's task budget, lifecycle notifications, scheduler,
callbacks and root observation lists. `BYNAME` with an empty owner, TP call
parameters, default group selection and logical group ownership continue to use
the calling root. `CURR_PROG` identifies the currently executing source module;
task program/stack inspection and checkpoint traces include the nested frame.
Indirect writes retain FOR-counter, routine-effect and handler checks.

`index` is an exact writable INTEGER reference and need not be initialized.
Successful target validation writes a stable context-local program hint before
entry. Missing or invalid targets, negative line values and unsupported target
forms raise without writing it. Hints are separate from variable lookup entries,
and their supplied previous values are ignored. Later callee failures retain
the already written hint and earlier source effects.

## Lines, pause and termination

For KAREL, every nonnegative line hint starts at the beginning, matching the
manual's KAREL rule. It does not jump to a source line. `pause_entry=TRUE`
pauses after publishing the index and creating the frame, before the body runs.
Body pauses also retain the complete nested generator. Continue through
`Program.resume()` for standalone execution or the `TaskScheduler` for a project.

The root owns stop, abort and failure outcomes. Closing a stopped invocation
unwinds its frames; abort and runtime failures propagate to the calling task.
Returning from a called program retains task-owned resources, including TP
handles and [logical group locks](group-locks.md). Root completion, stop, abort
or failure performs terminal cleanup. FILE variables keep their ordinary
explicit-close contract.

## Persistence and limits

Context JSON retains global data through the existing typed variable format.
Program cache hints, executable links, frames and suspended cursors are omitted.
Attach or instantiate source again after loading saved values. The
[recursive CLI example](../examples/program_recursion.kl) also demonstrates a
self-call that can replay from saved context.

Native program tables, controller task-stack layout, compiled PC/TP execution,
TP start-line execution, motion, implicit program discovery and strict behavior
remain outside this implementation. Noncooperative Program targets are rejected
with an explicit diagnostic; use cooperative generation or the project loader.

The report's `program_call_policy` and the
[semantic ledger](semantics/program_call_semantics.json) record the contract.
