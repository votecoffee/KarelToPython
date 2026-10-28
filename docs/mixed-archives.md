# Mixed recursive TP and variable archives

Pythonic mode combines portable TP records and ordinary KAREL variable snapshots
for `PROG_BACKUP(...,PBR_ALLTYPE,...)`, `PROG_CLEAR(...,PBR_ALLTYPE,...)` and
manifest-based `PROG_RESTORE`. Supply the existing `VariableArchives` service;
`TeachPrograms` is optional for a variable-only graph. These operations use
[TP archive](program-archives.md) and [VR archive](variable-archives.md) formats.
They restore logical data without loading native code or controller binaries.

```sh
python -m karel2py examples/mixed_archives.kl -o mixed_archives.py
python mixed_archives.py --context examples/mixed_archives.services.initial.json --state-out mixed-state.json
python mixed_archives.py --context mixed-state.json --state-out mixed-state.json
```

The authored [mixed example](../examples/mixed_archives.kl),
[variable-only example](../examples/mixed_variables.kl) and
[linked project](../examples/mixed_archive_project/main.kl) preserve completion
flags for repeat runs. Those flags do not provide crash recovery.

## Select the mixed branch

| Source form | Behavior |
| --- | --- |
| `PROG_BACKUP(file,PBR_ALLTYPE,hint,include_protected,status)` | With VariableArchives, capture both known stores and a root manifest. Without it, retain the TP-only branch. |
| `PROG_CLEAR(root,PBR_ALLTYPE,status)` | With VariableArchives, preflight removal of TP records and reset of owned VR values together. Without it, retain TP-only clear. |
| `PROG_RESTORE(file,status)` | With VariableArchives, a matching root `.PB` manifest selects mixed restore. A missing manifest falls back to ordinary TP restore, except an explicit `.PB` request returns missing. |
| Explicit `.VR` restore | Always use the existing variable-only branch. |
| Other PBR selectors | Retain their existing TP-only or VR-only meaning. |

The ordinary filename rules apply: bounded ASCII, optional device and relative
subdirectory, no host absolute paths/traversal/socket devices. Backup/restore
ignore the supplied final extension in favor of the root identity. Clear accepts
a plain name or `.TP`/`.VR`, without a directory/device. SAVE/LOAD/CLEAR do not gain
mixed extensionless native code operations.

Only exact MemoryFiles and DeviceFiles backends are accepted. DirectoryFiles and
custom subclasses remain unsupported. All output stays in the supplied file
bank; these calls do not read or write the host filesystem.

## Combined graph

Traversal unions `TeachPrograms.calls` and `VariableArchives.calls`, preserving
first occurrence order and visiting each identity once. It handles cycles and
shared dependencies. Known macro children are excluded; an explicit macro root
can be selected. No instruction strings or native linkage are parsed.

A namespace is known when it has a TP record, owned attached globals, or ordinary
explicit variable roots. Call metadata alone does not create a namespace. A
missing dependency fails backup before any write. Clear skips missing children,
while a missing root remains an error. Protection skips selected identities after
traversal, so unprotected descendants can still be processed.

A TP record can share an identity with its explicit VR namespace. Each is saved
in its own `.TP` or `.VR` member. TP-local register banks remain part of the TP
record; ordinary KAREL variables remain in VR. FILE/PATH roots stay excluded from
VR snapshots and retain live storage on clear/restore.

## Portable manifest

A mixed backup writes `directory/ROOT.PB` using format
`karel2py-program-batch-v1`. It contains the root and an ordered list of entries,
each with canonical program name, combined calls and a map of TP/VR SHA-256
hashes. Members keep the existing portable JSON formats. No private source,
manuals, native code, suspended task stacks or executable bindings are embedded.

The manifest defines the captured batch. Restore reads only its listed members;
it does not scan the directory or guess which unlisted sidecars belong to it.
It rejects malformed graphs, duplicate identities/JSON keys, unreachable entries,
invalid hashes and member identity/schema/dependency mismatches. A corrupt or busy
manifest never falls back to TP restore. Separate replacement of a member makes
an old manifest stale; back up the complete mixed batch again before restoring.

If protection excludes an identity, its manifest entry has no members. Backup
can succeed, but restoring that incomplete batch returns missing and leaves both
stores unchanged. This makes the exclusion explicit rather than inventing data.
Hashes identify exact bytes; they are not signatures or proof of origin.

## Atomic preflight and restoration

Backup prepares every TP record, VR snapshot and manifest before checking the
complete file batch. Busy/open/read-only/unmounted targets, file/count limits,
combined device growth and retained-deletion garbage all participate. Identical
files remain untouched. The existing 0..65536 KiB free-space hint is a reservation
check; it does not cap actual output bytes.

Restore validates every listed file and hash, even when a TP record already
exists. Existing TP records and their current graphs are retained. Absent TP
records are created; compatible VR values are overwritten, retaining unlisted
roots and ordinary aggregate/field aliases. All destinations are prepared before
either store changes. Extra cross-store edges supplied for a namespace without
that store's record are retained in VariableArchives.calls, so fresh restore does
not lose reachable dependencies. Graph capacities are checked before commit.

Clear preflights both stores before removing selected TP records and resetting
owned VR values to missing/empty storage. It preserves source code, declarations,
namespace identities, dynamic creation metadata, ordinary aliases, FILE/PATH
resources and executable links. It does not unload KAREL source programs.

Selected/open/bound TP records, protected or explicitly active identities,
foreign running/paused variable owners, connected timers and output/status aliases
retain their existing guards. TP header protection also protects its associated
VR data. ALLTYPE clear and every PROG_RESTORE are possible variable writes for
static analysis, including a `.TP` restore literal; direct, transitive routine and
condition-action FOR counters are protected. Proven TP LOAD/CLEAR literals and
TP-only PBR selectors keep their prior loop behavior.

## Limits and status

The total bytes of a mixed batch, including its manifest, must fit the minimum
configured TP `archive_limit` and VR `limit`; if only the variable service exists,
its limit applies. Distinct visited identities are bounded by the maximum
configured program count. Per-store graph/namespace/record capacities still
apply, and combined edges cannot exceed 32767. JSON retains the existing depth-32,
ASCII, duplicate-key and finite-number checks.

Statuses follow the portable archive table: 0 complete, 1 missing member/namespace
or deliberately omitted identity, 2 invalid specification/hint, 4 busy/protected/
unsupported service or backend, 5 capacity, and 6 malformed/incompatible/stale
archive. Missing explicit file services raise before writing a status. Ordinary
source type, initialization, overlap and FOR checks remain in force.

Context JSON retains both stores, graphs and file bytes for explicit replay.
This is an in-memory preflight contract, without concurrent mutation guarantees,
crash journals, native partial-progress/retry semantics, controller storage or
strict/runtime equivalence. The [ledger](semantics/mixed_archive_semantics.json)
records the source basis and these chosen portable behaviors.
