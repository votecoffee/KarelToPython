# Portable KAREL variable archives

Pythonic mode supports `.VR` forms of SAVE, LOAD and CLEAR; variable-only
PROG_BACKUP/PROG_CLEAR; explicit `.VR` PROG_RESTORE; and SAVE_DRAM. They use an
explicit `VariableArchives` service and checked ordinary variable storage.
Files contain portable JSON, independently of native controller VR binaries.

```python
from karel2py.runtime import ExecutionContext, MemoryFiles, VariableArchives

context = ExecutionContext(
    variable_archives=VariableArchives(calls={'CACHE': []}),
    files=MemoryFiles(),
)
context.variables.define('CACHE', 'VALUE', ('INTEGER',), 17)
```

Context JSON uses `variable_archives`, with optional `limit`, `program_limit`,
`calls` and saved `flash` snapshots. No file bank is needed for SAVE_DRAM or
variable clear. File operations require exact MemoryFiles or DeviceFiles;
DirectoryFiles and custom backends reject. The existing
[program archive file rules](program-archives.md) supply relative names, device
state, quota checks and retained-garbage accounting.

## Source calls

| Call | Supported variable form |
| --- | --- |
| SAVE | program, `.VR` filename, INTEGER status output |
| LOAD | `.VR` filename, INTEGER option, status; the option is ignored |
| CLEAR | program with explicit `.VR` suffix, status |
| PROG_BACKUP | file/root, PBR_VRTYPE or PBR_PCTYPE, free-space hint, include-protected flag, status |
| PROG_CLEAR | root, PBR_VRTYPE or PBR_PCTYPE, status |
| PROG_RESTORE | explicit `.VR` file/root, status |
| SAVE_DRAM | program, status |

SAVE refuses existing files. Program `'*'` saves all known ordinary namespaces
and attached source modules into individually named `.VR` files. Single-file
LOAD follows the archive's internal program identity, so a filename alias does
not rename its namespace. LOAD overwrites matching roots and retains unlisted
roots. It can create ordinary explicit roots in a fresh namespace; it never
adds source declarations or executable code.

Names are case-insensitive ASCII identifiers of 1..36 characters, including a
leading underscore. Filenames retain the existing archive naming rules. CLEAR
requires a name without device/directory. Explicit `.VR` spelling distinguishes
these operations from the [TP archive branch](program-archives.md). Native
PC/IO binaries and extensionless mixed SAVE/LOAD/CLEAR code operations remain
unsupported. [Mixed PBR_ALLTYPE batches](mixed-archives.md) now support
backup/clear and manifest-based recursive restore across TP and VR data.
PBR_PCTYPE selects variable records,
consistent with the manual's VR-only description; it does not archive PC code.

## Snapshot contents

Snapshots contain owned declared globals and ordinary explicit root bindings.
Constants, routine locals, imported FROM globals, system paths and external
namespaces are not inferred as owned data. FILE and PATH roots are recorded as
excluded names and retain their current runtime storage. Embedded resources and
sparse standalone field/index bindings reject instead of producing an incomplete
archive. Ordinary references must use exact dictionary or list storage.

Supported data includes INTEGER, REAL, BOOLEAN, bounded STRING, aggregate
BYTE/SHORT data, concrete arrays, structures, CONFIG, Cartesian data records,
exact-width joints and logical queues. Types and nominal identities are stored
alongside values. Missing leaves and unknown BYTE contents retain explicit true
markers; uninitialized integers are not replaced with guessed defaults.
Known values must satisfy the existing finite numeric and capacity checks.

LOAD requires exact destination schemas. It preserves array, structure, joint
and queue object identities so captured aliases continue to refer to the live
storage. A whole missing aggregate is restored as an existing-shaped tree of
missing/unknown initial leaves. Logical queue initialization, sequence and entries
are restored; its runtime backing-buffer association is dropped. A subsequent
queue operation can bind an explicit compatible buffer again.

Validated dynamic creation group/memory-pool metadata is retained for new roots.
A conflicting existing creation policy rejects the entire load. This preserves
offline intent and does not relocate native memory. Explicit ProgramAttributes
initialization flags refresh from the planned values; loaded-code flags and
overlay attributes remain unchanged.

CLEAR resets owned roots to their ordinary initial missing/empty values. It
preserves source declarations, explicit bindings, creation metadata and aggregate
aliases. It does not unload code, delete a variable namespace or release native
allocation. This reset policy is a practical Pythonic equivalent.

## Preflight and active execution

Each load, clear or recursive operation prepares its entire batch before
publishing variable values, metadata or graph changes. Failure retains prior
state, apart from the operation's status output and earlier argument effects.
Preflight rejects:

- Overlapping archive roots or destinations overlapping the status reference.
- Imported/resource replacements and incompatible schemas or creation policies.
- Another running, waiting or paused task's storage, including aliased roots.
- Connected or reserved timer cells, including shared-context claims held by
  transient/unattached states, plus explicit protected/active program metadata.
- Byte, leaf, namespace, graph or backend quota limits.

Restoring the executing module is supported with a disjoint status variable,
usually a routine-local status. A status global included in that module's archive
would overlap a destination and returns status 4. Scalar and aggregate aliases
used by the current routine retain their storage identity.

Possible VR writes retain direct, transitive-routine and condition-action
FOR-counter protection. Dynamic filenames are conservatively treated as possible
VR writes. ALLTYPE clear and every PROG_RESTORE now count as possible variable
writes, including `.TP` restore spelling because it can select a mixed manifest.
Proven TP LOAD/CLEAR filename literals and TP-only PBR selectors retain their
existing loop behavior. Read-only SAVE and SAVE_DRAM do not implicitly write
source globals.

## Recursive VR operations

`calls` supplies a bounded graph of variable namespaces. Backup visits each
known namespace once, including cycles and shared children, and archives its
dependency list with its values. Missing backup dependencies reject the complete
batch. Recursive clear ignores missing children and skips protected namespaces.

PROG_RESTORE requires explicit `.VR` spelling and follows the archived graph,
so a fresh bank does not need the original `calls` configuration. Every selected
file, schema and destination is checked before any namespace changes. Archive
identities must match recursive target names. Existing variable values are
overwritten; this differs from retaining existing TP program records.

Backup replaces changed files, skips identical bytes and respects the
include-protected flag. Free-space hints follow the TP archive policy. A skipped
protected dependency can leave no file for a future restore. Mixed TP/VR graph
selection uses the separate [mixed batch contract](mixed-archives.md); native
partial-progress behavior remains outside both models.

## DRAM save points and persistence

SAVE_DRAM captures a detached typed snapshot in `bank.flash`. It needs no file
backend and shares the configured total flash byte/count budget. A failed save
preserves the previous snapshot. All owned supported data is captured; native
DRAM/CMOS allocation and flash wear/lifetime are not modeled.

Host code explicitly restores a save point with
`bank.restore_dram(program._state, 'CACHE')`, returning a portable status. The
same schema, alias, task, timer and protection preflight applies. There is no
automatic POWERUP hook or native power-cycle claim. Context JSON preserves the
snapshots for an explicit later restore; it does not resume execution stacks.

Each `.VR` file uses format `karel2py-variables-v1`, with program identity,
typed variables, excluded root names and calls. Compact sorted JSON ends in one
LF. Loading rejects duplicate keys, native bytes, noncanonical typed payloads,
invalid true markers and excessive JSON nesting beyond 32 containers.
The shared byte budget defaults to 16 MiB and accepts 1..64 MiB. Program limits
are 1..4096, default 256. Each namespace has at most 32767 scalar leaves; call
graphs have at most the configured program count of keys/targets per row and
32767 total edges. Recursive batches and saved flash also honor their combined
byte/count limits.

| Status | Portable meaning |
| --- | --- |
| 0 | Complete operation succeeded |
| 1 | Missing namespace, dependency, file or DRAM snapshot |
| 2 | Invalid name/specification or free-space hint |
| 3 | Existing SAVE destination |
| 4 | Busy/protected/overlapping or unsupported storage/backend |
| 5 | Byte, leaf, namespace, graph or backend capacity limit |
| 6 | Invalid archive, incompatible schema/creation policy or malformed data |

Missing explicit services and ordinary source argument/protection errors can
raise before a status is written. Atomic preflight is an offline in-memory
contract, without a crash journal or concurrent mutation guarantee.

The [single-namespace example](../examples/variable_archives.kl) covers
SAVE/CLEAR/LOAD/SAVE_DRAM, and the
[recursive example](../examples/recursive_variables.kl) covers variable-only
backup/clear/restore. Both have independent fixtures and support saved-state CLI
replay. See `variable_archive_policy` in translation reports and the
[semantic ledger](semantics/variable_archive_semantics.json).
