# Portable projects, state, files and robot models

Version 0.80.0 extended all four offline service areas; 0.81.0 adds
[semaphores and error/lifecycle notifications](control-notifications.md). Version
0.82.0 adds [scoped errors, task requests and field reads](task-and-file-extensions.md). These are executable
Pythonic conventions; 0.83.0 adds [indirect I/O, comments and CALL arguments](io-and-call-parameters.md).
They have authored tests and do not assert native controller
timing, file layout, task ABI or robot calibration. Strict mode remains a future
milestone. The [service matrix](offline-services.md) describes the underlying
procedures and the [semantic ledger](semantics/extended_service_semantics.json)
retains source provenance and unresolved behavior.
Version 0.84.0 adds [current robot snapshots and program queries](current-robot-state.md),
including state-only contexts and current data alongside the existing models.
Version 0.85.0 adds [joint interoperability](joint-interoperability.md), limits-only
persistence and consistent updates to loaded-model frame/tool context.
Version 0.86.0 adds [register inspection/clearing and logical port unsimulation](register-lifecycle.md).
Version 0.87.0 adds [calendar clocks](calendar-clock.md), shared GET_TIME/SET_TIME
and full datetime snapshots with frozen restore.
Version 0.88.0 adds [task inspection](task-inspection.md) over explicitly bound
tasks, live execution context and supplied informational attributes.
Version 0.89.0 adds [file comparison and printing](file-comparison.md), using
closed named inputs, bounded report FILE output and synchronous WRITE callbacks.
Version 0.90.0 adds [model-backed joint/Cartesian assignments](kinematic-assignments.md)
with selected frame/tool, current-joint inverse seed and retained interface types.
Version 0.91.0 adds [digital output pulses](pulses.md) with blocking/NOWAIT,
explicit host polling and scheduler deadlines that survive normal completion/pause.
Version 0.92.0 adds [builtin-record initialization queries](initialization-queries.md).
Version 0.93.0 adds [global variable inspection](variable-inspection.md), with
canonical metadata, filtered name lists, pagination and checked formats.
Version 0.94.0 adds [joint operands in geometry](joint-geometry.md), using supplied
forward context for Cartesian frame operations, reflection, axes and comparisons.
Version 0.95.0 adds [program listing](program-listing.md), with attached Program
identities, persisted explicit catalogs, filtered pages and an optional cursor.
Version 0.96.0 adds [pose decomposition](pose-decomposition.md): UNPOS values,
model-backed joints, captured-source aliases and default-mask current queries.
Version 0.97.0 adds [collection persistence](collection-persistence.md), preserving
typed partial PATH data and logical queue entries/sequences with explicit buffer rebinding.

| Area | Working Pythonic implementation | Remaining boundary |
| --- | --- | --- |
| Registers and I/O | Numeric/string/position banks and ports persist to typed JSON; timed DOUT pulses; position type/axes, grouped clearing and simulation lifecycle; attached program globals and explicitly supplied system roots resolve through GET_VAR/SET_VAR | Live I/O acquisition and automatic controller-system-variable discovery |
| Files and collections | Explicit directory backend, copy/delete/rename/list/compare/print, ASCII/binary transfers, attributes, typed PATH/header and QUEUE_TYPE operations | Native devices, proprietary binary layouts, association records and native alarms |
| Control and linkage | Deterministic task scheduler, virtual time, event broadcasts, port edges, EVAL capture, scan intervals, optional local handler lifetime, typed source-project linkage | Native interrupts/priorities, motion UNTIL handlers, native alarm dictionaries and external ABI |
| Geometry | Explicit standard-DH model, forward/numerical inverse conversion, limits/reachability, external kinematic joints, groups/frames/tools, joint/Cartesian assignments and extended-pose comparisons | Robot-specific calibration/configuration branch selection, collisions and certified reachability |

## Shared and persistent state

```python
from karel2py import runtime as rt

context = rt.ExecutionContext(
    numeric=rt.NumericRegisters(10, {1: 42}),
    strings=rt.StringRegisters(5, {1: "ready"}),
    ports=rt.PortBank({"DIN": 2, "DOUT": 2}, {("DIN", 1): True}),
)
context.variables.define("SYSTEM", "$LIMIT", ("INTEGER",), 100)
context.save("state.json")
restored = rt.ExecutionContext.load("state.json")
assert restored.numeric.read(1) == (0, 42)
```

Pass the context to `Program(context=context)`. The separate `registers=` argument
still takes precedence over its numeric bank. No bank size or missing value is
inferred. `save` atomically replaces the explicitly named file; its parent must
exist. `to_config` and `from_config` offer the same representation without disk
access. Save only between execution steps; this API does not lock a concurrently
modified context.

The JSON preserves type specs, numeric kind, partial ARRAY/record initialization,
unknown BYTE leaves, joint widths, position-register group keys, file bytes,
event generations and configured robot models. Attached programs contribute
global values. Restoring them requires a fresh Program with matching declarations.
FILE handles, queue-buffer references, active call stacks, timers, handler closures,
callbacks and scheduler continuation state are not serialized. This is a value
snapshot, not a suspended-program checkpoint. A directory backend is restored as
memory bytes; reselect its root explicitly to use disk again.

GET_VAR/SET_VAR resolves attached global namespaces without manually binding
each name. Static dotted fields and numeric subscripts are supported. System
names such as `$LIMIT` resolve only when explicitly supplied through VariableStore;
they do not expose Python objects or inspect a controller. A foreign program
must be attached to the same context. Private globals and register values belong
in local state files outside public source control.

## Directory-backed files

```python
from karel2py import runtime as rt

# The selected directory and any device subdirectories must already exist.
files = rt.DirectoryFiles("data", devices={"MD": ""})
context = rt.ExecutionContext(files=files)
```

Names are relative paths, optionally beginning with a mapped device, such as
`MD:result.txt`. Absolute names, `..`, unmapped devices and symlink components
are rejected. File parents are not created. The default per-file limit is 16 MiB,
configurable up to 64 MiB. Each backend permits one open handle per file.
These checks are for controlled offline directories; they do not provide a
security boundary against another process racing filesystem changes.

Writes buffer until CLOSE FILE, then replace the file atomically. `ATR_IA`
enables interactive flush after each WRITE. `ATR_UF` selects unformatted/binary
fields; `ATR_REVERSE` selects big-endian fields instead of the default little
endian. `ATR_EOL` supplies the ASCII record terminator emitted by CR and used on
input. `ATR_FIELD` makes unformatted STRING reads consume the declared capacity;
explicit widths override it. Numeric defaults remain token based. These attribute identifiers
are package constants, not native numeric encodings. **0.80 corrects the earlier
ATR_IA binary interpretation; use ATR_UF for binary data.**

COPY_FILE, DELETE_FILE and RENAME_FILE are synchronous even when `nowait` is true.
Portable statuses are 0 success, 1 missing, 2 destination exists and 3 open/busy.
COPY_FILE overwrites only when its explicit overwrite Boolean is true. FILE_LIST
accepts format 0, nonnegative skip and shell-style `*`/`?` name patterns; it writes
sorted names up to the output array capacity and preserves unused elements.
Parent-directory creation, native listing formats and native alarm codes remain
outside this contract. See [file management](../examples/file_management.kl).

Generated service scripts accept `--filesystem-root data`, `--context state.json`
and `--state-out updated.json`. A state output file is written after successful
completion. Choose a separate output path if you want to preserve the input.

## Linked source projects

```python
from karel2py import load_project

project = load_project("examples/linked_project")
instance = project.instantiate()
result = instance.run("MAIN")
assert result["MAIN"]["values"]["TOTAL"] == 13
```

`translate_project({filename: source_text, ...})` is the in-memory equivalent.
`load_project` reads regular `.kl` files directly in one directory, at most 4 MiB
each. It does not recurse or import arbitrary Python files. Both compile supplied
KAREL into cooperative Programs; translation and linking execute no KAREL bodies.

```sh
python -m karel2py.project examples/linked_project
python -m karel2py.project examples/linked_project --entry MAIN
```

The first checks translation/linkage. `--entry` explicitly starts execution.
`--context`, `--filesystem-root`, `--state-out` and `--max-cycles` are available.
The Python API additionally accepts `instantiate(options={...})` for ordinary
Program options such as `joint_axes` and pose tolerances.

`ROUTINE add(amount: INTEGER): INTEGER FROM LIBRARY` automatically links to the
matching internal routine of the supplied LIBRARY program. Interfaces must agree
on canonical types, capacities, dimensions, result type and joint width. Explicit
host callback bindings take precedence. Missing or incompatible interfaces fail
during linkage. Cyclic calls have a shared 64-frame depth limit and charge work
to the caller's step budget.

`value FROM LIBRARY: INTEGER` imports a global by shared reference. Aggregate
imports share their underlying fields/elements too. Missing globals, mismatched
types and cyclic imports fail during linkage. Each routine invocation gets a
separate local stack; simultaneous tasks can call a library without sharing
locals. Module globals remain shared and can interleave at checkpoints. Library
main bodies are not run implicitly; call `instance.run("LIBRARY")` first when
initialization is needed. Contexts used for a project must have no already
attached Programs; restore a saved value context to create another instance.

## Scheduling and handlers

TaskScheduler uses round-robin generator checkpoints and a virtual clock with
a default 1 ms quantum. DELAY parks a task; other ready tasks continue. Connected
timers use the virtual clock unless the caller explicitly supplies another clock.
RUN_TASK queues a registered Program; PAUSE_TASK and PAUSE PROGRAM[n] request
pause at a checkpoint. CONT_TASK and CONTINUE PROGRAM[n] continue it. STOP and
ABORT terminate and unwind the affected stack. Numeric task IDs follow binding
order. The source-project loader binds in sorted filename order.

`scheduler.start(name)`, `step()`, `run(max_cycles=...)`, `continue_task(name)` and
`stop(name)` support embedding. `run` returns when tasks have completed, stopped
or paused; a paused task needs an explicit continuation. Cycle and per-task step
budgets bound WAIT loops. Errors stop the current drive and preserve prior writes;
other active tasks remain available for the caller to inspect or stop. No host
thread or process is launched. Caller handlers and pause requests are checked
at checkpoints inside linked routines, retaining their independent local stacks.

`SIGNAL EVENT[n]` increments a shared generation. EVENT[n] conditions and WAIT
consume generations independently per handler/expression. Multiple signals
between scans coalesce. Generations survive in the context, so an event signaled
before a new run can satisfy its first scan. This is a deliberate portable
broadcast convention, unlike native scan-time-only event delivery.

Boolean port `+`/`-` conditions detect rising/falling edges, starting from false.
EVAL captures and detaches its operand when defining the handler. For example:

```karel
PROGRAM EVENTS
VAR count: INTEGER
BEGIN
  count=1
  CONDITION[1]:
    WITH $SCAN_TIME=10
    WHEN EVENT[1] AND EVAL(count=1) DO count=7
  ENDCONDITION
  ENABLE CONDITION[1]
  SIGNAL EVENT[1]
END EVENTS
```

WITH $SCAN_TIME supplies a nonnegative millisecond scan interval. Zero scans
at every checkpoint; ENABLE permits an immediate first scan. PAUSE/ABORT
conditions observe explicit source requests; CONTINUE observes continuation.
Handlers remain one-shot until explicitly enabled again. By default they keep
their captured lexical frames. `ExecutionContext(local_handlers=True)` instead
purges handlers defined in a routine when its frame exits. `rt.condition_scope`
offers host-controlled lifetime. These facilities do not implement native motion
UNTIL handlers or interrupt priorities. Version 0.81.0 adds Pythonic
ERROR/POWERUP/SEMAPHORE conditions and NOABORT/NOPAUSE/NOMESSAGE actions; see
[control notifications](control-notifications.md).

## Robot models and extended poses

```python
from karel2py import runtime as rt

context = rt.ExecutionContext.from_config({
    "robot": {"dh": [
        {"a": 100, "min": -170, "max": 170},
        {"a": 100, "min": -170, "max": 170},
    ]}
})
assert context.robot.model.chain([0, 90])[0][3] == 100.0
```

Supply standard DH rows with `a`, `alpha`, `d`, `theta`, `offset`, `type`, `min`
and `max`. Lengths use mm; angles use degrees. Types are revolute or prismatic.
Omitted geometry/offset fields are zero; default limits are -180..180 degrees
or -1000..1000 mm. There are 1..9 joints and up to three external joints, which
occupy the tail of the serial chain. `external_axes` leaves at least one main
joint. This is a generic model; no robot's dimensions are bundled or inferred.

The model provides real forward transformations and damped numerical inverse
kinematics, seeded by the supplied reference joints. Limits and iteration budgets
are enforced. JOINT2POS returns three external values, padding unused fields
with zero. POS2JOINT fixes external joints at its explicit external-array values.
IN_RANGE fixes them at the pose's external values (zero for a plain pose), then
tries a bounded set of seeds. Failure means no solution was found within this
algorithm's budget, not proof of geometric impossibility. No collision checking
or robot-specific configuration-branch selection is implemented; config_ref=0
is the portable supported choice.

Optional typed `base`, `frames`, `tools`, active `frame` and `tool` entries provide
explicit model context. Identity frame/tool index zero is supplied by default.
Reachability uses the active entries; JOINT2POS/POS2JOINT use their explicit frame
and tool operands. `context.robot.frame(index)` and `.tool(index)` return copies.
Grouped configuration uses `{"groups":{"1":{...},"2":{...}},"active_group":2}`.
An `IN GROUP[n]` qualifier on a positional/joint declaration or interface is
retained in reports and `Program.source_groups`. A unique source group selects
that model; otherwise the explicit active group applies. Qualifiers are source
metadata; they do not change aggregate layouts or create a native grouped ABI.

Extended-pose `>=<` requires both ordinary `pose_tolerance` and an explicit
`external_tolerance` scalar or three-value tuple. Each external axis uses its
own inclusive absolute difference limit, in the caller's model units. Missing
external fields in a plain pose count as zero. Generated comparison scripts
accept `--external-axis-tolerances e1 e2 e3`. See the authored
[model example](../examples/robot_dh.kl) and
[extended comparison](../examples/extended_comparison.kl).
