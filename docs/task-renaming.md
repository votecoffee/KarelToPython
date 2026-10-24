# Task renaming

Version 26.1024.135943 adds `SET_TSK_NAME(old_name,new_name,status)` and the
host `TaskRegistry.rename(old_name,new_name)` / `TaskScheduler.rename(...)` APIs.
They rename an explicitly registered binding while retaining the Program object
and execution state. Host calls return the same portable status INTEGER.

Names are case-insensitive ASCII strings, stored uppercase, with new names of
1..254 characters. An empty old_name in source selects the uniquely registered
calling root task. A linked library routine uses its caller's root, rather than
the library module. An empty name in the host API has no implicit caller.
Names containing spaces are literal names; only the empty string selects self.

| Status | Meaning |
| --- | --- |
| 0 | Renamed successfully, including an unchanged case-insensitive name |
| 1 | Explicit old name is not registered |
| 2 | Empty/oversized new name, existing binding or conflicting scheduler metadata |
| 3 | Self is unregistered/ambiguous, or another registry owns the active task |

Invalid types, uninitialized source operands and invalid output references raise
ordinary source-located errors. Source status must be an exact writable INTEGER.
Inputs and the output selector evaluate once, left to right; completed argument
effects survive a later failure. FOR counter writes are protected directly,
through routines and through handlers. Only status changes on a nonzero result;
no registry or scheduler keys are changed.

## Retained identity and execution

Renaming preserves insertion order and therefore the task number used by
GET_TSK_INFO and numeric task control. It retains attributes, generator frames,
local values, task state and outstanding delay deadlines. Scheduler waiting and
error records move to the new key. Self-renaming and renaming a later task during
the current round do not skip or duplicate that task's turn.

Subsequent named queries, CONT_TASK, PAUSE_TASK, ABORT_TASK, RUN_TASK and scheduler
host operations use the new binding. The old name stops resolving. Separate
aliases of one Program remain separate bindings; explicit rename changes only
the selected alias, while empty self lookup rejects ambiguity. An active task
registered through a second registry cannot be renamed through that second
registry: use its owning TaskScheduler.

The source PROGRAM/module name, CURR_PROG, TSK_PROGNAME, imported globals,
GET_VAR/SET_VAR namespaces, external routine linkage and `ProjectInstance.programs`
keys retain source module identity. Task names and module names serve different
lookups. For a renamed project entry, subsequent scheduler starts use the new
binding; source linkage continues using the original module name.

```python
from karel2py import runtime as rt, translate

namespace = {"__name__": "rename_example"}
exec(translate("PROGRAM WORKER VAR n: INTEGER BEGIN n=1 PAUSE n=2 END WORKER").python_source, namespace)
context = rt.ExecutionContext(tasks=rt.TaskScheduler())
Worker = namespace["Program"]
worker = Worker(context=context)
context.tasks.bind("worker", worker)
context.tasks.start("worker")
context.tasks.run()
assert worker.task_state == "paused"
assert context.tasks.rename("worker", "renamed") == 0
context.tasks.continue_task("renamed")
assert context.tasks.run()["RENAMED"]["values"]["N"] == 2
```

The [authored project](../examples/task_rename_project/main.kl) renames the calling
task and a paused worker, then resumes the worker and inspects its retained task
number and source name:

```sh
python -m karel2py.project examples/task_rename_project --entry MAIN
```

Bindings and metadata remain live host configuration, omitted from ExecutionContext
JSON snapshots. Renaming does not persist suspended execution, rename a host
process or affect native task priorities, locks or controller task identifiers.
See [task inspection](task-inspection.md), the
[semantic ledger](semantics/task_rename_semantics.json) and the
[remaining-support inventory](unsupported.md).
