# Portable program archives

Pythonic mode supports TP forms of `SAVE`, `LOAD`, `CLEAR`, `PROG_BACKUP`,
`PROG_RESTORE` and `PROG_CLEAR`. They operate on the explicit `TeachPrograms`
store and ordinary in-memory file banks. Archives contain versioned JSON,
including positions, comments, header metadata and all three TP-local register
banks. Instructions remain opaque text and are never executed.

These are portable logical records. The `.TP` suffix identifies this chosen
container for TP, JB, PR and MR kinds; the internal type is preserved. Native
TP/PC/VR/IO binaries, KAREL source unloading, ordinary variable snapshots and
controller storage formats remain unsupported.

```python
from karel2py.runtime import ExecutionContext, MemoryFiles, TeachPrograms

context = ExecutionContext(
    teach_programs=TeachPrograms(
        {'MAIN': {'instructions': ['Authored root']},
         'WORKER': {'type': 'PR', 'instructions': ['Authored child']}},
        calls={'MAIN': ['WORKER'], 'WORKER': []},
        archive_limit=16 * 1024 * 1024,
    ),
    files=MemoryFiles(),
)
```

Context JSON adds optional `calls` and `archive_limit` fields inside
`teach_programs`. Existing configurations need no changes. The default byte
budget is 16 MiB; accepted budgets are 1 byte through 64 MiB.

## Source forms

| Call | Arguments and supported behavior |
| --- | --- |
| SAVE | program name, target `.TP` file, INTEGER status output |
| LOAD | source `.TP` file, INTEGER option, status |
| CLEAR | program name with optional `.TP` extension, status |
| PROG_BACKUP | device/path/root, PBR selector, free-space hint in KiB, include-protected Boolean, status |
| PROG_RESTORE | device/path/root, status |
| PROG_CLEAR | root program, PBR selector, status |

SAVE refuses an existing file. A source program of `'*'` saves every logical TP
program to a separate named file in the target directory; `FR:batch/*.TP` is an
explicit example. A single-program filename may differ from its source name:
LOAD uses the canonical identity in the archive header. It does not rename a
program to match that filename.

LOAD accepts overwrite only when option equals 1. Other integer options refuse
an existing program. CLEAR removes the logical record and its dependency list;
it accepts a bare program name or `.TP`, without a device or directory.
Associated TP-local register data is part of the record. `.PC`, `.VR` and `.IO`
forms return unsupported status and preserve state.

Program names are case-insensitive ASCII identifiers, 1..36 characters, starting
with a letter. File specifications have optional ordinary device prefixes and
relative directories. Program basenames and extensions normalize to uppercase;
directory spelling is retained. Slash and native backslash separators are
accepted, including a single leading separator after a device. Traversal,
absolute host paths, control characters and socket/PIP/MF devices reject.
Specifications are at most 254 ASCII characters.

## Recursive operations and selection

The explicit `calls` mapping is the dependency graph. Keys and targets normalize
to uppercase; duplicates reject. The graph has at most `program_limit` keys,
at most that many targets per key and at most 32767 total edges. Targets can be
unloaded; this allows restore preparation without pretending code is loaded.
Missing and empty dependency lists both mean no children. Loading can retain an
explicit empty list. COPY_TPE copies dependency metadata into detached storage.

Recursive traversal is iterative and visits each identity once, including
cycles and shared dependencies. It never parses instruction strings or infers
CALL/RUN/MONITOR targets. Known references to MR macros are excluded from
recursive traversal and saved dependency lists. An explicitly named macro root
can still be processed. Supply the relevant non-macro references in `calls`.

The nine PBR names use portable numeric constants in
`runtime.ARCHIVE_CONSTANTS`; their integers are not native enum evidence.

| Selector | Logical records selected |
| --- | --- |
| PBR_MNTYPE, PBR_ALLTYPE, PBR_NVRTYPE | TP, JB, PR and explicit MR roots |
| PBR_JBTYPE | JB |
| PBR_PRTYPE | PR |
| PBR_MRTYPE | Explicit MR root |
| PBR_NMRTYPE | TP, JB and PR |
| PBR_VRTYPE, PBR_PCTYPE | Unsupported variable-only forms |

Filters apply after traversal, so a JB child can be selected through a TP root.
PBR_ALLTYPE covers the logical TP records and their embedded register banks;
it does not add ordinary KAREL `.VR` snapshots. PROG_BACKUP's final extension is
ignored. Each selected record is saved as `directory/PROGRAM.TP`.

Backup replaces changed target files and leaves identical files untouched.
The include-protected flag controls whether protected records are saved.
Recursive clear skips protected records and ignores missing child programs;
a missing root remains an error. Skipping a protected or filtered root can leave
no root archive for a later restore.

PROG_RESTORE also ignores the supplied extension. It restores absent records
and follows their archived graph. Existing records are retained, and traversal
uses their current graph without reading their archive file. Archive identities
must match the requested recursive names. Every new record is validated before
the store changes; missing dependencies preserve the entire store.

## Guards, files and atomic preflight

Clear and overwrite refuse selected programs, open TP handles, mapped TP-local
register callers, protected targets and identities attached as KAREL source.
Explicit active ProgramAttributes records also prevent archive operations.
Read-only SAVE/backup may inspect a selected program, but open TP handles still
prevent snapshots. No source task, import, routine binding or continuation is
unloaded. Ordinary source type, initialization, status-reference and FOR-counter
checks remain active.

Host TP headers can supply `AT_PROTECT` as 1 (off) or 2 (on); source
SET_ATTR_PRG still treats that attribute as read-only. Explicit ProgramAttributes
overlays retain their existing metadata precedence. Archive load/clear refresh
their loaded/initialized/active flags while preserving overlay attributes.
Native editor permissions are not inferred from this archive guard.

Only exact `MemoryFiles` and `DeviceFiles` backends are accepted. Open target or
source FILEs, unmounted devices and read-only write destinations reject.
DirectoryFiles and custom subclasses return unsupported status, so archive
calls perform no host filesystem reads or writes.

SAVE, recursive backup, clear and restore preflight their complete batch before
committing. A bad dependency, existing SAVE target, invalid archive, count or
quota limit preserves all earlier state and files. This is a chosen Pythonic
policy; native routines can complete only part of a batch.

Device preflight combines the entire batch's quota changes. Replacement respects
retained-deletion garbage accounting, and identical files add no garbage.
Each file must fit the file bank's limit; the complete archive batch must fit
the TP store's archive budget. A backup free-space hint accepts 0..65536 KiB:
DeviceFiles checks that much free space as well as actual batch growth, while
MemoryFiles checks the hint against its configured file limit. Zero adds no
reservation. The hint does not cap actual output size.

## Format, status and persistence

Each file is compact ASCII JSON with format `karel2py-teach-program-v1`, an
internal program `name`, a typed logical `program` record and a `calls` list.
It ends with one LF. Loading rejects native binary content, duplicate JSON keys,
unknown fields, nonfinite numbers, excessive nesting beyond 32 containers and
records incompatible with the destination's groups/capacities. Position payloads
use the ordinary checked typed-state representation.

| Status | Portable meaning |
| --- | --- |
| 0 | Complete operation succeeded |
| 1 | Missing program, dependency or archive file |
| 2 | Invalid specification or free-space hint |
| 3 | Existing SAVE destination or LOAD target without overwrite |
| 4 | Busy/protected/active/bound target, inaccessible backend or unsupported form |
| 5 | Byte, quota, program, graph or count limit |
| 6 | Invalid or incompatible portable archive |

Context JSON preserves logical records, explicit graph, optional budget and file
bytes. Live TP handles and executable tasks retain their existing persistence
limitations. Archives restore data rather than native code, selected programs,
caller bindings or TP handles. There is no crash journal, concurrent mutation
contract, retry or controller-runtime equivalence.

The [single-program example](../examples/program_archives.kl) covers
SAVE/CLEAR/LOAD. The [recursive example](../examples/recursive_backup.kl) covers
backup/clear/restore of a root and worker. Both support saved-state CLI replay.

```sh
python -m karel2py examples/recursive_backup.kl --check
python -m karel2py examples/recursive_backup.kl -o .local/recursive_backup.py
python .local/recursive_backup.py --context examples/recursive_backup.services.initial.json --state-out .local/backup_state.json
python .local/recursive_backup.py --context .local/backup_state.json --state-out .local/backup_state.json
```

Create `.local` first. Completion flags avoid repeating successfully saved
example operations; they do not model crash recovery. The report exposes
`program_archive_policy`; the [semantic ledger](semantics/program_archive_semantics.json)
records the source basis, accepted forms and remaining boundaries.
