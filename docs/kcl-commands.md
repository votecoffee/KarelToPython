# Offline KCL commands

KCL, KCL_NO_WAIT and KCL_STATUS use an explicit KclCommands service. The service
records command requests and returns configured replies. Separate opt-ins
enable registered task controls and offline file, variable, volume, dictionary
and program operations.
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

## Failure and persistence

Once accepted, a pending request remains observable if its caller pauses, stops,
aborts or its wait fails. It is not cancelled or retried implicitly. This retains
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
python -m karel2py.project examples/kcl_file_commands --entry MAIN --context examples/kcl_file_commands/services.initial.json
python -m karel2py examples/kcl_variable_commands.kl -o kcl_variable_commands.py
python kcl_variable_commands.py --context examples/kcl_variable_commands.services.initial.json --state-out variable-state.json
python -m karel2py examples/kcl_variable_archives.kl -o kcl_variable_archives.py
python kcl_variable_archives.py --context examples/kcl_variable_archives.services.initial.json --state-out archive-state.json
python -m karel2py examples/kcl_offline_services.kl -o kcl_offline_services.py
python kcl_offline_services.py --context examples/kcl_offline_services.services.initial.json --state-out service-state.json
python -m karel2py examples/kcl_program_commands.kl -o kcl_program_commands.py
python kcl_program_commands.py --context examples/kcl_program_commands.services.initial.json --state-out program-state.json
```

Use `rt.KclCommands(replies, ...)` with `ExecutionContext(kcl=...)` for host
scenarios. The standalone example uses zero delay for deterministic fixtures;
the linked project exercises virtual delayed completion and logical stack queries.
The task commands example starts a worker independently, inspects its parent
number and continues its pause through KCL.

The report's `kcl_policy` and [semantics ledger](semantics/kcl_semantics.json)
record the accepted command forms and evidence. Native KCL, shell execution,
live transport and strict mode remain outside this milestone.
