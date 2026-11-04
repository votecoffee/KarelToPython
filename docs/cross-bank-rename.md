# Cross-bank rename

Pythonic `RENAME_FILE(source,destination,nowait,status)` moves exact files or
bounded final-name `*`/`?` batches between plain FilePipes and one explicit
MemoryFiles, DeviceFiles or rooted DirectoryFiles bank. Supply both banks through
ExecutionContext or saved context JSON. There is no backend discovery.

```karel
RENAME_FILE('src/*.KL','PIP:*.NEW',FALSE,status)
RENAME_FILE('PIP:*.NEW','archive/*.DAT',TRUE,status)
RENAME_FILE('extensionless','PIP:BRIDGE',FALSE,status)
```

Before the first call, configure an empty destination pipe for every generated
name using PIPE_CONFIG or explicit context configuration. This is an offline
Pythonic extension; it makes no native RENAME_FILE/controller equivalence claim.
Both BOOLEAN nowait values complete synchronously without background work.

## Endpoints and ownership

| Move | Destination requirement | Successful source change |
| --- | --- | --- |
| Ordinary file to PIP | Already configured, empty and closed | Remove ordinary source |
| PIP to ordinary file | Unused name, existing host parent if applicable, closed | Remove source bytes and pipe configuration |

An empty configured pipe is a reserved endpoint for this operation. It retains
its configuration object, sectors, CMOS intent, record size and formatting
metadata. Its empty buffer is replaced. Nonempty pipes are collisions, even when
their bytes happen to equal the source. No pipe is implicitly configured and
bytes are never truncated to fit. Exporting a pipe releases its reserved sectors.

Mutable in-memory source bytearrays retain their identity at the destination;
immutable bytes are converted to mutable storage. The banks' dictionary objects
stay stable. Unrelated live handles keep their buffers, cursors and ownership.
Selected sources and destinations must be closed, including pending pipe READs.
Closed banks save their resulting bytes, pipe metadata and device accounting in
the existing context JSON format; live handles still prevent serialization.

Same-bank [wildcard rename](wildcard-rename.md) and [virtual cross-volume rename](cross-volume-rename.md)
retain their separate contracts. Same-bank PIP rename moves configuration to an
unused name, whereas cross-bank import retains a configured empty destination.
COPY_FILE continues to require its own explicit overwrite permission.

## Planning and publication

The complete sorted batch validates names, aliases, duplicate targets, paths,
existing destination entries, busy handles, configured pipe capacities and
execution budgets before moving data. Source identities/bytes, configuration
identities/fields, selected names, busy state and final quotas are rechecked
before publication. Predictable later failures leave the whole plan unapplied;
host callbacks' own external changes are not rolled back.

MemoryFiles and DeviceFiles stage final mappings before updating the existing
dictionaries without intermediate callbacks, execution checks or scheduler
yields. DeviceFiles imports count all final live bytes plus existing garbage
against each volume's capacity. Exports from retaining volumes add removed bytes
to garbage; nonretaining exports release them. Mounted/writable requirements and
the final global file count apply to the whole batch. No temporary extra file
slot or pipe reservation is required.

DirectoryFiles confines names to its explicit root/device mappings and existing
parents. All selected bytes and predictable checks are prepared first. Moves
then publish in sorted per-file order: a source host file is deleted before its
reserved destination pipe receives bytes; a destination host file is atomically
written before its source pipe is removed. A failing current host delete/write
leaves that current source and reservation available, but earlier moves can
already be complete. This is not a multi-file host transaction and offers no
rollback or isolation from concurrent external filesystem changes.

## Limits and failures

Existing pattern/template rules apply: flat PIP source names and optional
[ordinary source directory patterns](directory-globs.md), case-insensitive matching
and uppercase PIP names, full-stem/extension star
substitution, and standalone `*` to preserve a complete filename. Exact calls
also support extensionless literal names. Destination question substitution,
unsafe paths, symlinks, socket endpoints and DAQ-owned names remain excluded.

The shared engine bounds scanned/matched/final ordinary entries to 32,767 and
selected retained payloads to 64 MiB. Existing per-file limits, 32-pipe maximum,
sector reservations, device quotas and execution budgets remain active.

| Portable status | Meaning |
| --- | --- |
| 0 | Complete move succeeded |
| 1 | No source match or destination pipe is not configured |
| 2 | Existing ordinary/nonempty pipe target, collision or unsupported template |
| 3 | A selected source or destination is busy |
| 4 | Destination pipe cannot hold the complete payload |

Missing services, malformed configuration, path/device/quota failures, changed
preflight state, budget exhaustion and host I/O errors raise KarelRuntimeError.
An exception preserves the source status variable until a result is returned.
These portable statuses do not claim native alarm-number equivalence.

[Authored tests](../tests/test_cross_bank_rename.py) cover memory, virtual devices,
rooted directories, binary bytes, metadata/identity retention, budget and quota
failures, changed preflight state, late host errors, linked routines and JSON
replay. Four runnable examples and two linked projects have independent expected
file/pipe state fixtures. No native controller or strict-mode validation is claimed.
