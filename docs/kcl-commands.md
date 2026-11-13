# Offline KCL commands

KCL, KCL_NO_WAIT and KCL_STATUS use an explicit KclCommands service. The service
records command requests and returns configured replies. Separate opt-ins
enable registered task controls and offline file, variable, volume, dictionary,
program, environment, procedure and source debugging operations.
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

Scheduled scripted waits use virtual time and allow eligible timed conditions to
run before the configured reply is due. Standalone waits use the captured clock
and existing sleeper callback; callback completion is the
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
Names use an ASCII identifier starting with a letter or underscore. Tasks must already
be bound through the host registry or supplied as linked project modules.

| Form | Offline effect |
| --- | --- |
| `RUN name` | Start a fresh task at main entry or continue its existing pause. A fresh launch is independent of the caller. |
| `CONTINUE name` or `CONT name` | Resume the selected paused task and its eligible RUN_TASK descendants. |
| `CONTINUE ALL` or `CONT ALL` | Resume registered paused tasks once, coalescing aliases and paused parent/child paths. |
| `PAUSE name` or `PAUSE ALL` | Request pause on eligible running or waiting tasks at their checkpoints. |
| `ABORT name` or `ABORT ALL` | Request abort on eligible running, waiting or paused tasks. |
| `HOLD name` or `HOLD ALL` | Hold owned logical motion and request a cooperative task pause. |
| `UNHOLD name` or `UNHOLD ALL` | Release logical holds for live tasks. Use CONTINUE to resume source execution. |
| `RESET` | Wait for one supplied logical controller reset response. |

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

### Logical hold and release

HOLD and its HO alias use the same driver, eligibility and command masks
as PAUSE. HOLD validates the full target batch against shared MotionRequests
and GroupLocks before applying logical holds or requesting pauses. Only groups
owned by eligible unmasked tasks are affected. A live target with no owned
groups can pause without adding a motion history row. Missing services or an
invalid group, grant or history capacity returns 4 before any target is changed.

The logical hold survives task continuation. Use the Pythonic UNHOLD command
or the source UNHOLD statement to release held motion. To resume a task paused
inside a blocking MOVE, issue UNHOLD before CONTINUE. UNHOLD accepts paused,
running or waiting registered targets and changes their owned groups. Task
scheduling and source execution continue to use their existing checkpoints.
Both operations use the [logical motion policy](task-and-file-extensions.md#logical-motion-flags).

### Scripted reset

Blocking `KCL('RESET', status)` uses the next response in the explicit
[ControllerServices](controller-services.md) reset queue. A response with
`completed: true` returns 0. A response with `completed: false`, a missing
plan, or an unavailable service returns 4. If the response supplies a
fault value, it is applied to logical OPOUT[3] at completion. The existing
source RESET built-in continues to report request acknowledgment.

The channel stays busy during the captured delay. Only the invoking
activation drives the response, including when RESET is a line in RUNCF.
Stopping or aborting that activation releases the channel and retires the
consumed response without publishing its fault value. KCL_NO_WAIT returns
3 before consuming a response. Exact scripted KCL replies retain precedence.
The command form follows MARRC75KR07091E Rev N, PDF page 728.

The modeled forms follow MARRC75KR07091E Rev N, PDF pages 283–284, 450–452,
705–706, 710, 717, 724 and 728. The offline task bank keeps explicit binding,
continuation and terminal-state rules. Native default selectors, abbreviated
verbs beyond the documented aliases, TP execution and physical motion remain
outside this model.

### Task waits

`WAIT name DONE` observes the selected task run until it completes, aborts
or stops. `WAIT name PAUSE` also completes when that run pauses. A failed
run completes the command with status 4. The name is an explicit registry
binding. A missing, idle, foreign-owned or self target returns 3.

An unfinished wait needs an active TaskScheduler-owned target. KCL and
unfinished KCL_STATUS wait from another task on that scheduler. KCL_NO_WAIT
can submit the request from a standalone observer with the same task
registry. Terminal results and a matching paused state can complete inline.
The command captures the bound task and its current run, including through
a registry rename. It observes scheduler transitions without advancing the
target itself. Eligible timed conditions on a scheduled caller can run while
the wait is pending, including when the caller is collecting it with KCL_STATUS.
Acceptance, channel busy status and saved-history rules match other KCL jobs.

An unresolved DONE wait can remain pending when its target is paused and
the scheduler has no runnable or timed work. Continue or stop the target
through the scheduler or another source control path. The channel stays busy
until the captured condition is reached. The forms follow MARRC75KR07091E
Rev N, PDF page 749. The [linked example](../examples/kcl_task_waits/main.kl)
waits for a pause, continues the worker and collects its completion.

With a saved [program default](#program-defaults), the name may be omitted
from RUN, CONTINUE, CONT, PAUSE, ABORT and WAIT. Explicit selectors still
select their named task. The abbreviated forms require a configured default.

### Task settings, traces and conditions

The same `task_commands` opt-in enables these forms.

| Form | Offline effect |
| --- | --- |
| `SET TASK [[name]] PRIORITY = value` | Apply the scheduler priority in 1..99. |
| `SET TASK [[name]] TRACELEN = value` | Set the trace capacity in 1..10,000 and retain the newest rows. |
| `SET TRACE ON\|OFF [[name]]` | Enable or disable future source checkpoint records. |
| `SHOW TRACE [name]` | Write retained source trace rows in sequence order as JSON Lines. |
| `SHOW HISTORY [name]` | Write the current source call stack as JSON Lines, from the root through the innermost frame. |
| `ENABLE CONDITION [name] number` | Enable a live global handler and reset its scan deadline. |
| `DISABLE CONDITION [name] number` | Disable a live global handler. |
| `SHOW CONDITION [name] [number]` | Write enabled state, priority and scan interval as JSON Lines in condition-number order. With debug commands enabled, include the live `breakpoint` flag. |

For SET TASK and SET TRACE, an explicit name goes inside literal brackets,
as in `SET TASK [WORKER] PRIORITY = 9`. SHOW TRACE and condition commands
take a bare name. Names select explicit registry bindings. Without a name,
settings and traces require a unique caller binding. Condition commands
default to the calling root task and also accept the COND abbreviation.

Settings and traces share [SET_TSK_ATTR and Program.task_trace](task-attributes.md).
Trace rows describe source checkpoints and include the sequence, program,
routine and line. SHOW TRACE takes a snapshot before writing. Condition
commands select condition numbers 1..1,000 in a running, waiting or paused
root task. They scope inspection and changes to the root's global handlers.
Handlers in linked modules and frame-local handlers have separate lifetimes.
Enabling a handler makes it eligible for the target task's next normal scan.
It does not drive the selected task. Use a host output callback to consume
listing text, or inspect the program's recorded output requests.

Status 3 indicates an unavailable task, handler or selector. Status 4
includes invalid settings, out-of-range condition numbers and output errors.
These forms follow MARRC75KR07091E Rev N, PDF pages 714–716, 735–736, 738 and
744. [Source debugging](#source-debugging) uses generated statement
checkpoints and explicit task state.

SHOW HISTORY also accepts SHOW HIST. It selects an explicit registry
binding, the configured default, or the calling root in that order.
Each row includes depth, source module and routine. The innermost row
also has the last observed source line. The form follows MARRC75KR07091E
Rev N, PDF page 740.

## File commands

Set `"file_commands": true` in the `kcl` context section or pass
`file_commands=True` to KclCommands. File commands use the existing explicit
memory, virtual device, rooted directory and plain PIP backends where supported.
Exact scripted replies retain precedence. Verbs and keywords are case-insensitive.
Path tokens preserve filename spelling and use relative paths or configured
device prefixes. A backslash is a directory separator, and a single leading
separator after a device prefix selects the root of that configured device.

| Form | Offline effect |
| --- | --- |
| `COPY [FILE] source TO destination [OVERWRITE]` | Use COPY_FILE with the requested overwrite policy. A device-only destination uses the source filename. |
| `RENAME FILE source TO destination` | Use RENAME_FILE with its existing wildcard, collision and backend rules. |
| `MOVE [FILE] source` | Use MOVE_FILE to move selected files between explicit RD and FR volumes. |
| `DELETE FILE source [YES]` | Use DELETE_FILE over the selected file or batch. YES is optional in this noninteractive service. |
| `APPEND FILE source TO destination` | Append one complete byte snapshot to an existing closed file. |
| `PRINT file` | Send the complete ASCII contents of a closed ordinary file or unformatted plain pipe to the current output sink. |
| `DIRECTORY pattern` | Send sorted matching filenames, one per line, to the current output sink. A device-only pattern selects that device's files. |

APPEND uses exact, distinct source and destination names. The destination
keeps its existing prefix. An open file, alias of the source, or insufficient
capacity prevents publication. Virtual volumes charge only the additional bytes.
A configured plain pipe retains its configuration and rejects data that would
discard part of the existing history. A rooted append replaces the destination
atomically within its configured root. APPEND charges one execution step per
started 4096 bytes of the combined result, including the existing prefix.
APPEND checks virtual volume capacity and the execution budget before reading.
It reads each payload once, checking the source first and then the planned
prefix immediately before publication. An execution budget
failure during the command returns KCL status 4 and leaves the destination intact.

DIRECTORY uses bounded component matching on ordinary backends and plain
basename patterns on PIP. An empty match succeeds with no output. PRINT validates
the full payload as ASCII before sending any text. A PIP target must have zero
record size and no format dictionary. Output uses the existing
WRITE observation or callback, so an output callback failure can follow earlier
successful chunks.

Inline file commands complete on the caller's turn. KCL returns the final
result. KCL_NO_WAIT returns acceptance and KCL_STATUS exposes completion.
Successful completion is 0. Returned FILE statuses are offset by 100, including
101 for missing data, 102 for conflicts, 103 for busy files and 104 for
operation-specific capacity or scope limits. A backend, path or output error
returns 4. Unsupported command syntax and a busy channel retain statuses 1 and 2.

The forms follow MARRC75KR07091E Rev N, PDF pages 706, 711–714 and 724–726.
Quoted paths, implicit directory defaults, formatted pipe printing, native
device discovery and socket/DAQ file dispatch remain outside this model.
The [linked file example](../examples/kcl_file_commands/main.kl) copies and
appends file data before a worker reads it from a plain pipe.

### Rooted directory commands

TYPE accepts the same ASCII file or plain pipe inputs as PRINT.
`CHDIR path` or `CD path` selects a directory within an explicitly
supplied DirectoryFiles root. `CD` writes the current root-relative
directory, `CD ..` selects its parent, and `CD /` selects the configured
root. A mapped device prefix selects its configured directory. Paths use
slash or backslash separators. The host process directory and ordinary
KAREL FILE operands keep their own resolution rules.

`MKDIR path` creates one directory under an existing parent. `RMDIR path`
removes one empty directory. The root, the active directory and its
ancestors are protected. An open FILE under the target also prevents
removal. The backend rejects traversal and symlink paths. Nonempty or
active directories and open files return 103. A missing path returns 101,
and a collision or invalid root operation returns 102. Invalid path or
backend errors use 4.

Unqualified KCL file commands resolve from the current directory.
Explicit device operands resolve from their device mappings. Context JSON
saves a nonroot `working_directory` within `kcl`. Supply the rooted backend
again when restoring it, for example with the generated CLI's
`--filesystem-root` option. The forms follow MARRC75KR07091E Rev N, PDF
pages 707, 723, 728 and 748.

## Variable and PATH commands

Set `"variable_commands": true` in the `kcl` context section or pass
`variable_commands=True` to KclCommands. Commands use the explicit variable
store and case-insensitive names. An omitted `[program]` qualifier selects the
currently executing source module. Exact scripted replies retain precedence.

| Form | Offline effect |
| --- | --- |
| `CREATE VAR [program]name : type` | Allocate a new typed root. VAR and VARIABLE are accepted. |
| `CREATE VAR [program]name IN CMOS : ARRAY[2,3] OF type` | Allocate with outer-to-inner dimensions and CMOS intent. DRAM is the default. |
| `RENAME VAR [program]old new` | Rename an explicit root and its related bindings. VAR and VARIABLE are accepted. |
| `RENAME VARS old new` | Move an unattached variable namespace to an unused name. |
| `SET VAR [program]path = value` | Assign a checked literal or named value to an independent root or field/element. VAR and VARIABLE are accepted. |
| `RECORD [program]path` | Capture current Cartesian or joint data into independent pose storage. |
| `DELETE VAR [program]name` | Remove an independent explicit root and its lookup entries. VAR and VARIABLE are accepted. |
| `CLEAR VARS program [YES]` | Remove the complete ordinary variable namespace when it is unattached. Y is also accepted. |
| `SAVE VARS file [= program]` | Write one portable VR archive to an unused file. The filename stem supplies the program name when omitted. |
| `LOAD VARS file` | Restore the namespace recorded in a portable VR archive into detached storage. |
| `APPEND NODE [program]path` | Add an uninitialized node after the last existing node. |
| `INSERT NODE [program]path[index]` | Insert an uninitialized node before an existing one-based index. |
| `DELETE NODE [program]path[index]` | Remove the node at an existing one-based index. |

Creation follows the [dynamic variable rules](dynamic-variables.md), including
one to three explicit ARRAY dimensions, bounded STRING capacities, supported
built-in types and supplied user types. A user type resolves in the selected
program. Creation records the calling task's default group and the requested
memory intent. Renames preserve storage identity, lookup entries and allocation
metadata. If bindings change during the rename checkpoint, the command fails
without overwriting the competing changes.

PATH edits apply to explicit detached root bindings. Compiled storage, known
borrowed frames, overlapping bindings and connected timers prevent an edit.
Valid edits preserve header and surviving node identities and keep the PATH
within the portable 32767-leaf limit. The command charges one step per existing
header or node leaf and per new node leaf before validating the payload or
allocating a node. It verifies the binding, header, node list and selected
index again after charging. Budget exhaustion or a target change completes
with status 4 and leaves the command's edit unapplied. The detached PATH can
be inspected with GET_VAR and saved through the existing typed context.

SET accepts decimal INTEGER, BYTE and SHORT literals, finite decimal REAL
literals with optional exponents, TRUE and FALSE, and ASCII text in single or
double quotes. Double the delimiting quote to include it in the text. STRING
case is retained, and text beyond the declared capacity fails.

Assignment and removal reject compiled roots, known borrowed frames, overlapping
bindings and connected timers. Removal also rejects open FILE descriptors.
CLEAR checks the whole namespace before deleting any binding. Surviving
references and lookup IDs retain their identities.

SAVE and LOAD require the explicit variable archive and file services. File
specifications accept an omitted `.VR` suffix and use the existing archive
device rules. SAVE writes the portable JSON envelope over the existing memory or
virtual-device archive backends. LOAD uses the envelope's namespace even if
the file has a different name. It checks the entire archive and rejects attached
namespaces or aliased destinations before publishing. Existing independent
references with matching schemas receive the restored values. Native VR data,
implicit filenames and LOAD VARS CONVERT remain outside these forms.

These commands complete inline. KCL_NO_WAIT returns acceptance, and KCL_STATUS
reports completion. Success is 0. Dynamic variable statuses are offset by 200.
The portable results include 201 for missing names, 202 for invalid selectors,
203 for collisions, 204 for protected storage, 205 for type or shape failures,
and 206 for allocation limits. An execution error returns 4.

### Pose recording and value assignment

SET can copy one initialized value from a static ordinary source path. With
no qualifier on the right, the destination namespace supplies the lookup
scope. Use an explicit `[program]` prefix to read from another namespace.
Supported values are scalars, VECTOR, CONFIG, JOINTPOS and Cartesian poses.
Types must match and a copied STRING must fit. A source pose or vector is
detached before publication. Updates retain the existing destination ownership,
read-only field and connected-timer checks.

Named ARRAYs and user STRUCTURE records also copy with exactly matching concrete
schemas, including nested data, named ARRAY components and fully selected fields
or elements. Final ordinary ARRAY rows/planes also copy as exact remaining
ARRAY schemas, with comma or chained static indexes; see [KCL data selections](kcl-data-prefixes.md).
Every source leaf must be initialized and valid. STRING capacities,
nominal record/ARRAY names, dimensions and terminal types remain exact. A source
may be compiled storage; the destination must remain independent explicit storage.
The copy retains existing destination containers and never aliases source data.

For these ARRAY/record copies, charge one execution step per declared scalar leaf
before validating or copying contents. Retain the selected destination through
those checkpoints, then recheck its binding, selected parent, storage identity,
ownership, aliases and timer protection. Read the source's current value after
the last copy checkpoint. Validate the destination shape and the complete source
before publication, with no further checkpoints. Budget exhaustion returns 4;
changed or protected targets return 204; invalid/incomplete/mismatched data returns
205. Existing 32767-leaf and 64-level data limits apply. FILE data, aggregate
literals and implicit reshaping remain excluded. Separate
[logical collection copies](kcl-collection-copies.md) now support exact scalar
PATH/QUEUE_TYPE values, whole banks and complete indexed/named components to
detached storage, including valid partial PATH and uninitialized queue data.
[Collection rows/planes](kcl-collection-prefixes.md) additionally use complete
containing-bank charges, retained original target cells and typed SHOW output. The
[ARRAY example](../examples/kcl_data_copy.kl) verifies that later source edits
leave the copied values unchanged; [regressions](../tests/test_kcl_data_edits.py)
cover records, ownership and failures.

Comma-separated literals follow the destination type. VECTOR takes three
components. JOINTPOS takes the declared axis count. POSITION and XYZWPR
take X, Y, Z, W, P and R. XYZWPREXT adds EXT1, EXT2 and EXT3. Supply an
optional quoted CONFIG after the last numeric component, using the existing
[portable CONFIG text](config-text.md) syntax. Omitted CONFIG uses `N R D B`
with zero turns. The same quoted text can initialize a detached CONFIG field.
Lists validate all components before publication. Generic ARRAY literals,
user-record literals and system-variable writes remain outside these forms.

RECORD uses the KCL group selection or the calling task's group with the
supplied [current robot state](current-robot-state.md). It accepts detached
POSITION, XYZWPR, XYZWPREXT and JOINTPOS destinations, including compatible
selected cells. Cartesian conversion follows the source pose rules and
XYZWPREXT retains the supplied external axes. Joint width changes use the
existing zero-padding and zero-only narrowing checks. Missing current data
returns 4 and a value incompatible with the destination returns 205.
The [CLI example](../examples/kcl_pose_record.kl) records the supplied
Cartesian pose and reads back a modeled external axis.

The forms follow MARRC75KR07091E Rev N, PDF pages 706, 709, 711–713, 717,
722, 726–727, 731 and 736–737. Native default programs and controller variable
allocation remain outside this model.
The [PATH example](../examples/kcl_variable_commands.kl) shows creation,
node edits and a root rename with saved-context replay.
The [VR example](../examples/kcl_variable_archives.kl) saves a value, removes
its root, then loads and reads it back.

### Variable inspection

`SHOW VAR [program]path` or `SHOW VARIABLE [program]path` uses the same
static variable resolution as VAR_INFO. The optional program selector uses
literal brackets, as in `SHOW VAR [WORKER]route[2].part`. The caller's
module is the default. Fields and complete ARRAY, JOINTPOS and PATH indices
are supported. An optional HEX, HEXADECIMAL or BINARY suffix adds signed
Python-style formatting for an initialized integer scalar.

`SHOW VARS [program] [VALUES]` writes canonical root names and types from
the named module or detached namespace. The optional program name is bare.
VALUES includes typed snapshots. Output is compact JSON Lines with array
dimensions and string capacity when applicable. Uninitialized markers and
portable PATH and QUEUE_TYPE data use the existing saved-state shapes.
FILE storage contributes metadata with `value_available` set to false
when values are requested. System-variable paths require their separate
source services.

The command preflights the complete listing against 32,767 rows and data
leaves and 1 MiB of output before the first write. `SHOW VARS` also charges each
inspected program owner, global and binding to the step budget, with a scan
limit of 32,767 entries before filtering. Status 201 indicates an
unavailable selector, 202 an invalid radix request, and 205 a value or
listing that cannot be represented within the portable limits. The forms
follow MARRC75KR07091E Rev N, PDF pages 744–745.

### System and memory inspection

`SHOW SYSTEM [type] [VALUES]` lists explicit `$` bindings from the
`SYSTEM`, `*SYSTEM*` and empty namespaces, with that precedence for
duplicate paths. It sorts the paths and uses the same bounded JSON Lines
and optional type filter as ordinary variable inspection. Without VALUES
the output describes each binding's type. Robot context tables require
explicit bindings to appear in this view.
The scan counts every explicit binding, including those outside the system
namespaces. A scan that exceeds the limit returns 205 before writing rows.

`SHOW MEMORY` writes one JSON row with used and available reservations
under the shared 32,767-unit CREATE_VAR limit. It counts created storage
across both declared memory intents. Explicit host bindings and compiled
globals are outside that budget. Units follow the portable allocation
rules and do not estimate controller bytes.

Both commands use the variable opt-in. The forms follow MARRC75KR07091E
Rev N, PDF pages 742–743.

### Local variable inspection

`SHOW LOCAL VAR path [HEX|HEXADECIMAL|BINARY] [IN routine] [FROM module] [task]`
reads one local variable or parameter. `SHOW LOCAL VARS [VALUES] [IN routine]
[FROM module] [task]` lists the frame's locals and formals. The optional
task is a registry binding. Without one, the command uses the configured
program default or the calling root. IN and FROM select the innermost
matching live frame, including frames in linked source modules. With
neither filter the command selects the top frame.

The output includes the task, module and routine. Paths, type information,
value encoding and capacity limits match the global variable views.
Missing frames, tasks or local paths return 201. These forms use retained
Python frames and follow MARRC75KR07091E Rev N, PDF pages 740–741.

`SET LOCAL VAR path [IN routine] [FROM module] [task] = value` also
accepts the full VARIABLE spelling. It edits owned data in a paused routine,
using the same routine, module and task selectors. Static fields and complete
one-based ARRAY/JOINTPOS indices select original storage. Indices are integer
literals, with optional spaces; adjacent numeric bracket groups normalize.
Final ordinary ARRAY rows/planes can be named data sources or destinations.
Expressions, aggregate literals and incompatible remaining shapes still reject.

Scalar and positional literals use the SET VAR formats above. VECTOR, CONFIG,
POSITION, XYZWPR, XYZWPREXT and JOINTPOS roots or selected cells use complete typed
component lists. CONFIG scalar fields retain their flag/turn bounds. POSITION
orientation columns and their descendants remain read-only; location edits work.
All components validate before any field changes, and destination objects retain
their identity.

Named source values can copy scalars, poses and complete data ARRAYs/records.
An unqualified source path first checks the selected frame, including readable
borrowed parameters, then that frame's source-module globals. A declared local
that is missing or uninitialized never falls back to a global. An explicit
`[program]` qualifier uses ordinary global lookup. ARRAY/record schemas must match
exactly and every source leaf must be initialized. Scalar STRING copies may use
different capacities if the value fits. Copies create no aliases to source data.
Separate [local logical copies](kcl-local-collections.md) now support owned
PATH/queue locals, banks, complete components and final rows/planes. They accept
valid partial PATH and uninitialized queue data, and readable borrowed sources,
while formal destinations remain protected. SHOW LOCAL VAR supports logical rows.

```text
SET LOCAL VAR target IN stage WORKER = source
SET LOCAL VAR target[2].count IN stage WORKER = 42
SET LOCAL VAR point.location.x WORKER = 12.5
SET LOCAL VAR target WORKER = [INPUTS]source
```

The compiler records FOR roots per routine. The whole routine's listed
roots, retained aliases into any field or joint axis, borrowed formals and
connected timers protect the entire containing local root, including unselected
siblings. Running tasks and code without the required compiler metadata also
reject writes with 204. Reads still support borrowed formals.

Path, named-value and ARRAY/record edits charge one step per declared scalar leaf
in the containing local root before validating/copying contents. Retain the task
binding, run and continuation, live frame, declaration, root container and selected
target through those checkpoints. A changed binding/frame/root/target or newly
protected storage rejects before publication. Read named source data after the
last preparation checkpoint, then validate and publish with no further checkpoints.
Existing scalar and positional root literals retain their original admission.

Missing task/frame/root uses 201; protected or changed storage uses 204; invalid
paths, incomplete/mismatched data or a scan over 32,767 storage cells use 205.
Budget exhaustion uses 4. Data schemas retain the 32767-leaf and 64-level limits.
This subset follows
MARRC75KR07091E Rev N, PDF pages 734–735 and 740–741.
FILE storage, local PATH data-field/literal edits, aggregate literal syntax, reshaping, computed
selectors and implicit routine discovery outside these explicit frame commands
remain excluded. Extended data/positional edits are a portable Pythonic model,
without a native/controller equivalence claim. See the
[linked example](../examples/kcl_local_data/main.kl) and
[regressions](../tests/test_kcl_local_data_paths.py).

### Declared types and typed variable filters

`SHOW TYPES [program] [FIELDS]` lists declared types from an attached
source module. The optional program can name a registered task binding
when it does not name an attached module. Rows show declared names and
owners, resolved kinds and known dimensions or string capacities. FIELDS
includes immediate record fields. The view uses metadata in the generated
module and a 1 MiB output limit.

`SHOW data_type [program] [VALUES]` filters the existing variable listing
by root type. For example, SHOW INTEGER VALUES selects INTEGER scalar
roots, SHOW ARRAY selects array roots, and SHOW JOINTPOS2 selects
two-axis joint positions. SHOW JOINTPOS includes every joint width.
The filter supports ARRAY, STRUCTURE, the modeled primitive, position and
association types, FILE, PATH and QUEUE_TYPE. The forms follow
MARRC75KR07091E Rev N, PDF pages 744–746. The
[linked example](../examples/kcl_local_types/main.kl) lists types and
integer variables, then edits a paused worker's local before continuing it.

## Virtual device commands

Set `"device_commands": true` in the `kcl` context section or pass
`device_commands=True` to KclCommands. These forms use
[DeviceFiles](virtual-devices.md) and its explicitly configured virtual volumes.
Exact scripted replies retain precedence. Device names are case-insensitive
and accept an optional trailing colon.

| Form | Offline effect |
| --- | --- |
| `MOUNT device` | Mark the selected volume mounted. |
| `DISMOUNT device` | Mark the selected volume unavailable while retaining its bytes. |
| `FORMAT device [label] [YES]` | Clear the selected mounted writable volume after its busy checks. The optional label is one token and is truncated to 11 characters. YES and Y are accepted. |
| `PURGE device` | Reclaim obsolete bytes while retaining live files. MF selects both RD and FR and checks both before reclamation. |

These commands complete inline. KCL_NO_WAIT returns acceptance and KCL_STATUS
reports completion. Small nonzero device results are offset by 300. This
includes 302 for invalid device selection, 303 for unmounted media, 304 for an
open FILE, and 305 for a read-only volume. DEV_NOTHING_TO_PURGE (85023) is
preserved. An absent or incompatible backend returns 4. Physical volumes and
socket endpoint changes use their separate service boundaries.

The forms follow MARRC75KR07091E Rev N, PDF pages 715–716 and 723–725.

`SHOW DEVICE device:` reports a configured volume as JSON with its name,
label, mounted and read-only flags, and total capacity. File-backed volumes
also report free and reclaimable bytes. Unmounted volumes can be inspected.
Unknown volumes return 302. The form follows MARRC75KR07091E Rev N, PDF
page 739.

## Dictionary commands

Set `"dictionary_commands": true` in the `kcl` context section or pass
`dictionary_commands=True` to KclCommands. The commands use a supplied
[TextDictionaries catalog](text-dictionaries.md). Exact scripted replies
retain precedence.

| Form | Offline effect |
| --- | --- |
| `LOAD DICT source name [language]` | Load a decoded catalog entry or explicit offline file under the first four characters of the dictionary name. |
| `CLEAR DICT name [language]` | Remove a loaded snapshot. ALL clears matching snapshots across languages. |
| `COMPRESS DICT source` | Validate an ASCII UTX file and publish a new sibling portable TX file. |
| `COMPRESS FORM [file]` | Compile an FTX dictionary and publish its portable TX and form companion as one prepared batch. |
| `LOAD FORM [file]` | Validate both members of a portable form package and install the decoded dictionary. |

An omitted language selects DEFAULT. A missing source suffix becomes `.TX`
under the existing catalog rules. CLEAR preserves supplied source text. Loaded
snapshots are available to CHECK_DICT, READ_DICT and WRITE_DICT. Small nonzero
dictionary results are offset by 400, including 401 for malformed text or
selectors, 402 for an existing snapshot, 403 for a missing source or snapshot,
and 405 for capacity. The configured-language error 33003 is preserved.
KCL_NO_WAIT and KCL_STATUS separate acceptance from inline completion.

An explicit catalog source takes precedence. If the label is missing,
File-backed dictionary and form commands charge one execution step per
started 4096 bytes before reading each input, including a form companion.
Portable TX expansion also charges the decoded text before parsing.

LOAD can read ASCII TX, UTX and FTX files or a portable TX stream from
MemoryFiles, DeviceFiles or an explicit DirectoryFiles root. File operands
respect the KCL directory and preserve spelling for case-sensitive banks.
Loaded text is saved as a detached decoded snapshot.

COMPRESS defaults to `.UTX`, accepts up to 64 KiB of checked dictionary
text and writes the new `.TX` sibling without overwrite. Its portable
format is the ASCII marker `K2PY-TX1`, one zero byte and one complete
zlib stream. LOAD bounds expansion to 64 KiB and rejects incomplete or
trailing compressed data. A busy file or unavailable backend returns 404.
An optional [`.kl` directive](text-dictionaries.md#generated-karel-constants)
adds a generated CONST include to the batch.
Native TX binaries remain outside these forms.
The forms follow MARRC75KR07091E Rev N, PDF pages 708–710 and 718.
The [file replay example](../examples/kcl_portable_batch.kl) compiles and loads
a portable TX. The [catalog example](../examples/kcl_offline_services.kl)
uses a supplied decoded entry.

`SET LANGUAGE name` or `SET LANG name` selects a configured language.
DEFAULT selects the authority's default. With a pendant, it is the active
language authority and the change records a SET_LANG event. Without a
pendant, the dictionary catalog supplies the current and default language.
When both services exist, SET accepts their shared language labels. An
unavailable selection returns 33003 before changing either service.

`SHOW LANG` reports the current and default labels. `SHOW LANGS` lists
selectable labels in sorted order. `SHOW DICTS` lists loaded dictionary
names and source labels for the effective current language. It uses the
same selection rule as READ_DICT. These forms write JSON Lines through
the offline output callback or recorded WRITE requests. The forms follow
MARRC75KR07091E Rev N, PDF pages 734 and 739–740.

### Portable form packages

With the dictionary opt-in, COMPRESS FORM defaults to `FORM.FTX` and LOAD
FORM defaults to `FORM.TX`. Supply a four-character dictionary name, or
prefix it with two application characters and optionally append a two-letter
language suffix. EG, JP, FR, GR and SP select English, Japanese, French,
German and Spanish. With no suffix, loading selects the configured default.
File operands use the KCL directory and the exact spelling required by the
backend.

COMPRESS FORM requires at least one complete form in the checked FTX text.
It writes a sibling portable TX stream and a companion named for the
four-character dictionary, such as `BTNS.VR` for `ABBTNSEG.TX`.
The companion contains canonical JSON with the source name, dictionary,
language, element identities and SHA-256 of the TX bytes. Both files must
be new. The command preflights both files, their combined capacity and
busy handles before publishing in MemoryFiles or DeviceFiles.
An optional `.kl` directive adds the validated include to the same batch.

LOAD FORM accepts those banks or an explicit DirectoryFiles root.
It requires the portable TX marker and the matching canonical companion
before installing the decoded snapshot. A missing member returns 403,
a malformed or stale pair returns 401, an existing dictionary returns
402, and a busy member or unsupported backend returns 404. The loaded
snapshot can be saved in context JSON and used by
[DISCTRL_FORM](forms.md) with the caller's explicit value paths.

The companion describes the portable form package. Native VR records and
inferred Data IDs remain outside
this contract. The forms follow MARRC75KR07091E Rev N, PDF pages
212–214, 710 and 719. The [CLI example](../examples/kcl_form_package.kl)
compiles a named package with a CONST include, loads it, and checks its form element by name.

## Program and task inspection commands

Set `"program_commands": true` in the `kcl` context section or pass
`program_commands=True` to KclCommands. Exact scripted replies retain
precedence. File operands are explicit, unquoted relative specifications
with optional logical device names.

| Form | Offline effect |
| --- | --- |
| `SAVE TP file [= program]` | Save one logical TP record to a new portable archive. The filename stem selects the program when omitted. |
| `LOAD TP file [OVERWRITE]` | Load the program named inside the portable archive, with optional replacement subject to the existing guards. |
| `CLEAR PROGRAM name [YES]` | Clear one logical TP record. `CLEAR PROG` and `Y` are accepted aliases. |
| `SAVE ALL [file]` | Save a new portable TP/VR manifest and its members. |
| `LOAD ALL [file]` | Restore a portable manifest into logical TP and detached variable storage. |
| `CLEAR ALL YES` | Remove logical TP records and independent detached variable namespaces after complete preflight. |
| `TRANSLATE file [LIST]` | Translate stored KAREL source to a sibling Python artifact and optionally a listing. |
| `SHOW PROGRAMS` | Write a sorted, deduplicated snapshot of offline program names and types. |
| `SHOW PROGRAM [name]` | Write matching rows for one name, with source task state and active routine when available. |
| `SHOW TASKS` | Write a sorted snapshot of registered task names and status labels. |
| `SHOW TASK name` | Write one registered task row selected by an ASCII identifier starting with a letter. |

The TP commands accept optional `.TP` suffixes on file operands and use the
explicit [logical program and FILE services](program-archives.md). Selection,
protection and attached-program guards remain in effect. Clearing removes
logical program data only. TRANSLATE uses the explicit
[stored-source service](source-translations.md) and its source, input and
publication rules. The artifacts require a separate execution step.

Listings use the ordinary offline output path with compact JSON per line.
Program rows carry `name` and `type`, including `PC` for attached Python
programs, explicit catalog and teach-program types, and `VR` for named
variable namespaces. Task rows carry `name` and `status` using the same PG
labels as GET_TSK_INFO. Registered aliases have separate rows. Empty task
listings succeed without output. Rows are captured before the first write.
Each scan inspects up to 32,767 catalog entries or task registrations and
charges each entry to the step budget, including entries filtered out or
deduplicated. `SET DEFAULT` uses the bounded program scan when looking up a
catalog name. Exceeding the catalog limit returns 505 before any rows are
written or the default selection changes.

`SHOW BUILTINS` writes the offline service registry in name order. Each
JSON row contains the service name and FUNCTION or PROCEDURE. The
registry describes callable translations. Availability of a particular
call can require a supplied backend or option. This view follows the
intent of MARRC75KR07091E Rev N, PDF page 738.

Nonzero program archive and listing results use offset 500. Results include
501 for a missing record, 502 for an invalid archive specification, 503 for
a conflict, 504 for a protected or active record, 505 for capacity and 506
for malformed archive data. Missing required backends and KAREL output
errors use 4. TRANSLATE preserves its stored-source status codes. These
commands use the existing KCL_NO_WAIT acceptance and KCL_STATUS completion
split, with inline offline dispatch.

The forms follow MARRC75KR07091E Rev N, PDF pages 709, 721, 730–731,
742–743 and 748. Native TP and p-code loading, native display and teach-mode
translation switches, and controller listing formats remain outside this scope.
The [archive example](../examples/kcl_program_commands.kl) saves to an alias,
clears and restores the original program name, then lists the records.

### Mixed archive batches

SAVE ALL and LOAD ALL use the existing
[portable mixed manifest](mixed-archives.md) with explicit VariableArchives
and MemoryFiles or DeviceFiles. They accept a plain root file specification
with an optional `.PB` suffix. With no operand, the saved KCL program
default supplies the root. SAVE ALL is a Pythonic extension and refuses
any collision among the manifest and its members.

LOAD ALL requires the manifest and validates every listed hash and
destination before publishing. It retains existing TP records, restores
compatible detached VR values, and rejects writes into attached source
namespaces or the SYSTEM namespace. It does not fall back to native PC,
standalone TP or standalone VR files. LOAD ALL CONVERT is unsupported.

CLEAR ALL requires YES or Y and returns 502 without it. It selects the
logical teach-program store and ordinary unattached variable namespaces,
excluding source-owned and system data. An open FILE, overlapping
binding, selected TP record or other protected destination prevents
the entire clear. Stored archive files and executable links remain
available. These commands use the 500-series program statuses.
The source forms for CLEAR ALL and LOAD ALL follow MARRC75KR07091E Rev N,
PDF pages 707 and 718. The [CLI example](../examples/kcl_portable_batch.kl)
round-trips a variable batch before loading a dictionary and running RESET.

### Program defaults

`SET DEFAULT name` or `SET DEF name` selects a known program, task binding,
or detached variable namespace. `SHOW DEFAULT` writes the selected name
or the caller's source module. An unavailable name returns 501. ALL is
reserved and returns 502.

The default applies to omitted task selectors, ordinary variable selectors,
and SHOW PROGRAM. Each command still checks the appropriate registry or
namespace. File operands and archive naming retain their own rules.
Context JSON persists `default_program` within `kcl`. Rebind tasks when
restoring a standalone context. The forms follow MARRC75KR07091E Rev N,
PDF pages 733–734, 739 and 742. The [linked example](../examples/kcl_session_defaults/main.kl)
uses one default for running, waiting, inspecting and continuing a worker.

## Environment commands

Set `"environment_commands": true` in the `kcl` context or pass
`environment_commands=True` to KclCommands. Exact scripted replies take
precedence.

| Form | Offline effect |
| --- | --- |
| `SET PORT kind[index] = value` | Assign a configured output or simulated input using the logical port bank's checked types. |
| `SIMULATE kind[index] [= value]` | Mark a port simulated. Use the supplied value or the current logical value. |
| `UNSIMULATE kind[index]` or `UNSIMULATE ALL` | Remove the selected simulation flags and retain the last logical values. |
| `SET CLOCK 'dd-mmm-yy hh:mm'` | Replace the supplied calendar anchor. |
| `SHOW CLOCK` | Write the supplied calendar in `dd-MMM-yyyy hh:mm:ss` form. |
| `SHOW CURPOS` | Write a JSON row with the active task group and the supplied or modeled current XYZWPREXT pose. |
| `SET GROUP number` | Set the KCL group for later SHOW CURPOS and RECORD calls. |
| `SHOW GROUP` | Write the effective KCL group as a JSON row. |

SET PORT accepts DIN, DOUT, RDO, OPOUT, TPOUT, GIN, GOUT, AIN and AOUT.
Individual simulation forms accept DIN, DOUT, GIN, GOUT, AIN and AOUT, and
the SIM and UNSIM aliases. Addresses use the existing configured index
ranges. Values use Boolean ON/OFF, TRUE/FALSE or 0/1, nonnegative decimal
group integers, or finite decimal analog numbers. The named commands
share the [PortBank](io-and-call-parameters.md) with KAREL port access.
UNSIMULATE ALL clears all simulation flags in that bank. The offline
bank holds one logical value per address.

SET CLOCK uses English month abbreviations and maps years 80..99 to
1980..1999 and 00..79 to 2000..2079. Double the inner quotes when
embedding the command in a KAREL STRING. SHOW CLOCK uses the same
packed value and two-second resolution as [GET_TIME](calendar-clock.md).
Calendar changes stay within the supplied offline clock.

SHOW CURPOS shares [CURPOS](current-robot-state.md) group selection and frame/tool
rules. The pose includes the modeled external axes and structured CONFIG
fields. Missing current state uses status 4. This form follows
MARRC75KR07091E Rev N, PDF page 739.

SET GROUP requires a configured group in 1..32 and returns 602 for an
invalid selection. The group is saved as `default_group` within `kcl`.
Without a KCL override, SHOW CURPOS uses the caller's group. Source CURPOS
retains its own task selection. The group forms follow MARRC75KR07091E
Rev N, PDF pages 734 and 740.

Completion statuses are 601 for an unavailable current port value, 602
for an invalid configured address or calendar value, 603 for an invalid
port literal or value, and 604 for writing an unsimulated input. Status 4
covers missing backends or inline runtime errors. KCL_NO_WAIT returns
acceptance and KCL_STATUS returns completion. The forms follow
MARRC75KR07091E Rev N, PDF pages 733, 735, 738, 746 and 748–749.

The [environment example](../examples/kcl_environment_commands.kl) changes
a simulated input, observes a handler fire and updates the calendar.

## Command procedures

Set `"procedure_commands": true` in the KCL context. Use
`KCL('RUNCF input [listing]',status)` with a concrete input name and an
optional listing name. Omitted extensions become `.CF` and `.LS`.
Names resolve through the explicit ordinary FILE backend and the current
KCL directory. Supply exact filename spelling for case-sensitive backends.
Exact scripted replies retain precedence. Built-in RUNCF uses blocking KCL.
KCL_NO_WAIT returns 3 for this form.

The procedure accepts ASCII command lines, optional leading `>`, and
`--` comments outside quoted values. `%INCLUDE file` expands an ordinary
file relative to the containing procedure or to its explicit mapped device.
The complete input graph is captured before executing commands. Each input
costs one execution step per started 4096 bytes before reading. Rooted files
are checked against their planned identity, size and modification time. Limits
are 64 KiB of input, four file levels including the entry file, 32 file
reads, and 256 expanded commands. Includes with cycles, nested RUNCF,
unknown directives and unsafe paths fail during preflight.

Each line uses the same enabled command families and exact replies.
The procedure stops at the first nonzero completion code and reports it.
Effects of earlier commands remain applied. Task WAIT commands use the
calling task's scheduler. The channel stays busy until the procedure
finishes. The invoking activation owns the procedure and its private
waits. Stopping it releases those waits while already launched tasks keep
their own lifetimes. The channel history records one RUNCF request.

`SET VERIFY ON` and `SET VERIFY OFF` control command echoes. ON is the
default and OFF persists as `"verify": false`. Echoes and command output
share a 64 KiB budget. Without a listing, text goes to the caller's output
path as it is emitted. With a listing, output is buffered and published to
a new file only on success. A preexisting or concurrently created file
keeps its contents.

Procedure statuses include 701 for missing input, 702 for invalid syntax
or paths, 703 for a listing collision, 704 for a busy or unavailable file,
705 for size or count limits, and 706 for cycles or nested RUNCF. Runtime
service failures can return 4. Child command statuses are preserved.
The forms follow MARRC75KR07091E Rev N, PDF pages 729 and 737.
The [linked example](../examples/kcl_command_procedure/main.kl) expands an
include, runs and waits for a worker, and saves a listing.

## Source debugging

Set `"debug_commands": true` in the KCL context. Program breakpoints
use the same channel as the compiled source. Retranslate cooperative
modules to obtain checkpoint metadata. The CLI report lists eligible
expanded-source line numbers under `kcl_policy.source_checkpoints`.
These lines identify generated statement checkpoints, including statements
in linked modules. Several checkpoints may share a physical source line.

| Form | Offline effect |
| --- | --- |
| `SET BREAK PROGRAM [program] slot line [action]` | Create or replace a numbered program breakpoint. Actions are PAUSE, DISPLAY, TRACE ON and TRACE OFF. PAUSE is the default. |
| `ENABLE BREAK PROGRAM [program] slot` | Enable the selected definition. |
| `DISABLE BREAK PROGRAM [program] slot` | Keep the definition and suppress its effect. |
| `CLEAR BREAK PROGRAM [program] slot` or `CLEAR BREAK PROGRAM [program] ALL` | Remove the selected definitions. |
| `SET BREAK CONDITION [task] number` | Arm a one-shot break on an existing live root-task global condition. |
| `CLEAR BREAK CONDITION [task] number` or `CLEAR BREAK CONDITION [task] ALL` | Remove the selected condition break marks. |
| `SHOW BREAK [name]` | Write JSON Lines for program definitions and armed root conditions. |
| `STEP ON [task]` or `STEP OFF` | Select one task for source-checkpoint pauses, or clear the active step selection. |
| `SHOW CHECKPOINT [task]` | Report the live skippable statement's source module, line and skip flag. |
| `SKIP [task]` | Mark that exact paused statement to be bypassed when the task continues. |

PROGRAM and CONDITION accept PROG and COND. An omitted selector uses the
configured program default or the caller. Program names select source
modules. Registered task aliases can select their root modules. Program
breakpoint slots and line numbers use 1..32,767, with at most 256 saved
definitions. Condition numbers use 1..1,000.

PAUSE stops before the matched statement. Continuing resumes that captured
checkpoint, and later visits can pause again. DISPLAY writes a JSON event
to the offline output path. TRACE actions change the root task's source
trace setting at that checkpoint. Actions on the same line run in slot
order, with a single resulting pause. A condition break is consumed when
its predicate succeeds and pauses before the action. Continuing executes
the action if the same handler is still enabled. STEP pauses before each
eligible checkpoint for the selected root and works through linked calls.

SKIP applies to a breakpoint or step pause immediately before an eligible
statement. It skips operands, implicit FILE selection and the complete
statement body. Assignments, calls, ordinary READ/WRITE and FILE commands,
DELAY, WAIT FOR, PULSE and whole motion requests are eligible. FOR, USING
and other structural checkpoints, RETURN, condition breaks and already
started operations reject SKIP with 802. The report lists candidate lines
under `kcl_policy.skippable_checkpoints`. A line can contain more than one
statement, and the exact retained checkpoint determines eligibility.

Repeated SKIP commands mark the same statement. CONTINUE resumes the
task and bypasses that statement once, with ordinary handler and scheduler
checks still in force. Abort or stop discards the mark. Retranslate existing
modules to enable this form. The live mark is transient.

Context JSON saves program definitions under `program_breakpoints`.
Condition break marks and step selection belong to live runtime state.
Status 801 means an unavailable program, condition or slot. Status 802
means an invalid number, unavailable checkpoint or ineligible source.
Status 805 means the definition limit has been reached. The forms follow
MARRC75KR07091E Rev N, PDF pages 708, 714–715, 732, 737–738 and 746–747.
The [linked example](../examples/kcl_source_debug/main.kl) uses RUNCF
to set a worker breakpoint, wait for the pause and skip the selected assignment.

## Failure and persistence

Once accepted, a scripted reply or task wait remains observable if its caller
pauses, stops, aborts or its wait fails. This retains
the distinction between acceptance and collection. A later KCL_STATUS can collect
the same request without increasing the submission sequence.

Built-in blocking RUNCF and RESET belong to the invoking activation.
KCL_STATUS cannot drive either command while it is pending.

`KclCommands.snapshot()` returns detached reply/history data and a pending
descriptor when present. Context save rejects pending work; collect it first.
Terminal configuration saves replies, bounded history, sequence and last status.
It also retains enabled command opt-ins.
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
python -m karel2py.project examples/kcl_task_waits --entry MAIN --context examples/kcl_task_waits/services.initial.json
python -m karel2py.project examples/kcl_session_defaults --entry MAIN --context examples/kcl_session_defaults/services.initial.json
python -m karel2py.project examples/kcl_command_procedure --entry MAIN --context examples/kcl_command_procedure/services.initial.json --state-out procedure-state.json
python -m karel2py.project examples/kcl_local_types --entry MAIN --context examples/kcl_local_types/services.initial.json
python -m karel2py.project examples/kcl_local_data --entry MAIN --context examples/kcl_local_data/services.initial.json
python -m karel2py.project examples/kcl_source_debug --entry MAIN --context examples/kcl_source_debug/services.initial.json
python -m karel2py.project examples/kcl_file_commands --entry MAIN --context examples/kcl_file_commands/services.initial.json
python -m karel2py examples/kcl_variable_commands.kl -o kcl_variable_commands.py
python kcl_variable_commands.py --context examples/kcl_variable_commands.services.initial.json --state-out variable-state.json
python -m karel2py examples/kcl_variable_archives.kl -o kcl_variable_archives.py
python kcl_variable_archives.py --context examples/kcl_variable_archives.services.initial.json --state-out archive-state.json
python -m karel2py examples/kcl_pose_record.kl -o kcl_pose_record.py
python kcl_pose_record.py --context examples/kcl_pose_record.services.initial.json
python -m karel2py examples/kcl_portable_batch.kl -o kcl_portable_batch.py
python kcl_portable_batch.py --context examples/kcl_portable_batch.services.initial.json
python -m karel2py examples/kcl_form_package.kl -o kcl_form_package.py
python kcl_form_package.py --context examples/kcl_form_package.services.initial.json
python -m karel2py examples/kcl_offline_services.kl -o kcl_offline_services.py
python kcl_offline_services.py --context examples/kcl_offline_services.services.initial.json --state-out service-state.json
python -m karel2py examples/kcl_program_commands.kl -o kcl_program_commands.py
python kcl_program_commands.py --context examples/kcl_program_commands.services.initial.json --state-out program-state.json
python -m karel2py examples/kcl_environment_commands.kl -o kcl_environment_commands.py
python kcl_environment_commands.py --context examples/kcl_environment_commands.services.initial.json --state-out environment-state.json
python -m karel2py examples/kcl_inspection_commands.kl -o kcl_inspection_commands.py
python kcl_inspection_commands.py --context examples/kcl_inspection_commands.services.initial.json --state-out inspection-state.json
```

Use `rt.KclCommands(replies, ...)` with `ExecutionContext(kcl=...)` for host
scenarios. The standalone example uses zero delay for deterministic fixtures;
the linked project exercises virtual delayed completion and logical stack queries.
The task commands example starts a worker independently, inspects its parent
number and continues its pause through KCL.

The report's `kcl_policy` and [semantics ledger](semantics/kcl_semantics.json)
record the accepted command forms and evidence. Native KCL, shell execution,
live transport and strict mode remain outside this milestone.
