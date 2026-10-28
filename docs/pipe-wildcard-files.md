# Wildcard operations on plain pipes

Pythonic COPY_FILE and DELETE_FILE extend the
[bounded wildcard file contract](wildcard-file-operations.md) to explicitly
configured plain FilePipes. Copies support pipe-to-pipe, ordinary-to-pipe and
pipe-to-ordinary endpoints, including rooted DirectoryFiles and virtual
DeviceFiles. No real IPC connection, input wait or background operation is created.
Exact pipe operations keep their existing finite snapshot contract.

```karel
COPY_FILE('seed*.DAT','PIP:work_*.BAK',TRUE,FALSE,status)
COPY_FILE('PIP:WORK_*.BAK','saved_*.DAT',FALSE,FALSE,status)
DELETE_FILE('PIP:WORK_*.BAK',FALSE,status)
```

Configure `PIP:WORK_SEEDA.BAK` and `PIP:WORK_SEEDB.BAK` before the first copy when
source files are `seedA.DAT` and `seedB.DAT`. The exported ordinary names are
`saved_WORK_SEEDA.DAT` and `saved_WORK_SEEDB.DAT`: pipe names normalize to uppercase.
A pipe-only batch does not require an ordinary files service; crossing between
services requires both to be supplied explicitly.

## Names, configuration and snapshots

Pipe patterns are plain basenames with star wildcards. Case is ignored, and one
optional slash immediately after `PIP:` is accepted. Paths, traversal, recursive
search, question/bracket patterns and generated names beyond the pipe name limit
are rejected. Existing whole-stem/extension substitution applies: `work_*`
within a complete `work_*.BAK` template uses the complete matched source stem.

A standalone destination `*` preserves the complete source filename, including
extensionless names when a pipe endpoint participates. Stem/extension templates
still require both source components. Ordinary-to-ordinary wildcard restrictions
remain unchanged.

Every destination pipe must already be configured. An empty configured pipe is
still an existing target, so replacement requires overwrite TRUE. The copy keeps
all destination configuration, including sectors, CMOS intent, record size and
dictionary metadata. It replaces the complete bytes rather than appending or
formatting them. No configuration, quota reservation or extra pipe slot is created.

Source pipes contribute their complete retained byte history, including any
circular overflow that occurred before the request. Existing live cursors are not
used as snapshot offsets. Source and target pipes must be closed; active readers
and unresolved pending-read identities block the batch. Unrelated pending readers
retain their buffers and identities across a successful prepared commit.

A snapshot larger than any configured destination returns capacity status 4.
It is never ring-truncated. All matched files are checked before any target is
published, so a later missing, busy, conflicting or undersized target preserves
earlier targets. Source/destination configuration and bytes changed during
preflight are detected and preserved. Deletion removes both matching plain
configuration and bytes, leaving unmatched records unchanged.

## Bounds, publication and routing

The shared 32767-entry/match and 64 MiB copy-snapshot limits apply, alongside the
pipe bank's 32 configured records, sector capacities and combined reservation
limit. Budget charges and predictable checks precede publication. Memory, virtual
device and pipe destinations use prepared dictionary changes; virtual device
quotas and obsolete-byte accounting are preflighted for the complete batch.
Rooted directory exports retain per-file atomic replacement and the documented
possibility of partial publication on later host I/O failure. Pipe sources remain
unchanged in that case. Both nowait values execute synchronously.

| Portable status | Meaning |
| --- | --- |
| 0 | Complete batch succeeded |
| 1 | No source match or a destination pipe is not configured |
| 2 | Overwrite disabled, collision/overlap or unsupported template |
| 3 | Selected file/pipe is open or has a pending read |
| 4 | A destination pipe cannot hold its complete snapshot |

Unsafe paths, limits, quota failures, preflight changes and unresolved read
identities raise. These outcomes are portable and do not assert native alarm IDs.
[Wildcard RENAME](wildcard-rename.md) is now a separate Pythonic extension for
ordinary same-volume files or a single plain PIP bank. It moves original bytes
and pipe metadata to previously unused names; it never replaces an existing pipe.
COPY still requires configured destinations under the contract above.

Socket wildcard operands are rejected before routing. A pipe source pattern that
also matches a DAQ PIP name rejects the entire request, including a DAQ-only
match; it does not silently create or read a plain shadow. Actual generated DAQ
target names are also rejected, even if a plain configuration has the same name.
Unmatched DAQ names are not selected by a destination template. Native formatted
pipe dictionaries, DAQ transport and binary controller formats remain separate.

Saved context retains completed replacement bytes and remaining configuration;
deleted pipes are not recreated. Live handles/read generators still prevent
serialization under their existing lifecycle rules. Verification is in the
[authored pipe wildcard tests](../tests/test_pipe_wildcard_files.py), alongside
ordinary wildcard and exact pipe regressions. Evidence is translation/offline
execution only.
