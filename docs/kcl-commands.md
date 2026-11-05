# Offline KCL commands

KCL, KCL_NO_WAIT and KCL_STATUS use an explicit KclCommands service. The service
records command requests and returns configured replies. Separate opt-ins
enable registered task controls and offline file, variable, volume, dictionary,
program, environment and procedure operations.
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
Names use an ASCII identifier starting with a letter or underscore. Tasks must already
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
target itself. Acceptance, channel busy status and saved-history rules
match other KCL jobs.

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
| `SHOW CONDITION [name] [number]` | Write enabled state, priority and scan interval as JSON Lines in condition-number order. |

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
744. Native breakpoints, statement text lookup and debugging execution
remain outside this scope.

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
atomically within its configured root.

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
| `SET VAR [program]path = literal` | Assign a checked scalar literal to an independent root or field/element. VAR and VARIABLE are accepted. |
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
within the portable 32767-leaf limit. The detached PATH can be inspected with
GET_VAR and saved through the existing typed context.

SET accepts decimal INTEGER, BYTE and SHORT literals, finite decimal REAL
literals with optional exponents, TRUE and FALSE, and ASCII text in single or
double quotes. Double the delimiting quote to include it in the text. STRING
case is retained, and text beyond the declared capacity fails. The command
updates one ordinary scalar cell. It does not emit an implicit console display.
Variable-to-variable assignments, aggregate literals and system variables
remain outside these forms.

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

The forms follow MARRC75KR07091E Rev N, PDF pages 706, 709, 711–713, 717,
722, 726–727, 731 and 736. Native default programs and controller variable
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
leaves and 1 MiB of output before the first write. Status 201 indicates an
unavailable selector, 202 an invalid radix request, and 205 a value or
listing that cannot be represented within the portable limits. The forms
follow MARRC75KR07091E Rev N, PDF pages 744–745.

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

`SET LOCAL VAR name [IN routine] [FROM module] [task] = literal` also
accepts the full VARIABLE spelling. It assigns one checked scalar literal
to a paused routine's owned local variable. The same routine, module and
task selectors apply. Supported targets are INTEGER, SHORT, BYTE, REAL,
BOOLEAN and STRING roots. Reads still support paths and borrowed formals.

The compiler records FOR roots per routine. The whole routine's listed
roots, retained aliases, borrowed formals and connected timers are
protected. Running tasks and code without the required compiler metadata
also reject writes with 204. Missing targets use 201 and invalid literals
or a scan over 32,767 storage cells use 205. This subset follows
MARRC75KR07091E Rev N, PDF pages 734–735 and 740–741.

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
| `LOAD DICT source name [language]` | Parse an explicit decoded catalog entry and load a snapshot under the first four characters of the dictionary name. |
| `CLEAR DICT name [language]` | Remove a loaded snapshot. ALL clears matching snapshots across languages. |

An omitted language selects DEFAULT. A missing source suffix becomes `.TX`
under the existing catalog rules. CLEAR preserves supplied source text. Loaded
snapshots are available to CHECK_DICT, READ_DICT and WRITE_DICT. Small nonzero
dictionary results are offset by 400, including 401 for malformed text or
selectors, 402 for an existing snapshot, 403 for a missing source or snapshot,
and 405 for capacity. The configured-language error 33003 is preserved.
KCL_NO_WAIT and KCL_STATUS separate acceptance from inline completion.

The forms follow MARRC75KR07091E Rev N, PDF pages 708–709 and 718.
Native compressed TX decoding, COMPRESS DICT and LOAD FORM remain outside
these forms. The [combined example](../examples/kcl_offline_services.kl)
exercises a virtual volume, a decoded catalog and a plain pipe.

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
listings succeed without output. Rows are captured before the first write,
with a limit of 32,767 rows per listing.

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
| `SET GROUP number` | Set the KCL group for later SHOW CURPOS calls. |
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
The complete input graph is captured before executing commands. Limits
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

## Failure and persistence

Once accepted, a scripted reply or task wait remains observable if its caller
pauses, stops, aborts or its wait fails. This retains
the distinction between acceptance and collection. A later KCL_STATUS can collect
the same request without increasing the submission sequence.

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
python -m karel2py.project examples/kcl_file_commands --entry MAIN --context examples/kcl_file_commands/services.initial.json
python -m karel2py examples/kcl_variable_commands.kl -o kcl_variable_commands.py
python kcl_variable_commands.py --context examples/kcl_variable_commands.services.initial.json --state-out variable-state.json
python -m karel2py examples/kcl_variable_archives.kl -o kcl_variable_archives.py
python kcl_variable_archives.py --context examples/kcl_variable_archives.services.initial.json --state-out archive-state.json
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
