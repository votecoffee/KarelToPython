# Wildcard copy and deletion

Pythonic COPY_FILE and DELETE_FILE accept bounded star/question source batches on explicit
MemoryFiles, DirectoryFiles and DeviceFiles backends. Exact calls retain their
existing behavior. Source files and targets stay within the supplied logical
bank, mapped devices or rooted directory; no controller or host drive discovery
is performed.

```karel
COPY_FILE('src/part*.KL','dst/backup_*.PY',FALSE,FALSE,status)
DELETE_FILE('src/old*.DAT',FALSE,status)
```

The manual explicitly permits star specifications for COPY_FILE and DELETE_FILE.
It does not define a complete destination expansion algorithm. The following
mapping is a documented portable choice, without a native DOS/controller
wildcard-equivalence claim. [Wildcard RENAME_FILE](wildcard-rename.md) is a
separate Pythonic extension with no overwrite and same-bank preflight, including
[complete virtual-volume capacity checks](cross-volume-rename.md).

## Patterns and destination templates

Star/question source matchers are allowed only in the final filename. Literal parent paths and optional
device prefixes remain fixed. No recursive directory search, directory wildcard,
bracket pattern, absolute host path or traversal is accepted.
Paths use forward slashes and stay relative to their explicit backend/root.
Unmapped devices, symlinks, control characters, trailing-dot/space components and
reserved device basenames fail closed.

A wildcard COPY specification must include a nonempty name and type, such as
`part*.KL` or `*.*`. DELETE also accepts `*` to select extensionless names in the
chosen parent. `*.*` matches names containing a dot; it is not a special native
alias for every filename. Literal brackets in already stored matched filenames
are copied/deleted as characters, rather than interpreted as another pattern.

For a destination containing a dot, its final filename is split at the last dot.
Each of its stem and extension permits at most one star. That star substitutes
the complete source stem or extension, rather than only a source-pattern capture:

| Source match | Destination template | Result |
| --- | --- | --- |
| `partOne.KL` from `part*.KL` | `backup_*.PY` | `backup_partOne.PY` |
| `part.rev1.KL` | `new_*.copy*` | `new_part.rev1.copyKL` |
| `partOne.KL` | `*.*` | `partOne.KL` |
| `partOne.KL` | `*` | `partOne.KL` |

A standalone destination `*` preserves the complete filename. A literal
destination is allowed when the resulting batch has only one target. A star
stem without an extension, such as `prefix_*`, is rejected as ambiguous.
Generated targets must satisfy the same backend path and size checks.

Final basename matching and collision checks use case-insensitive comparisons,
while source spelling is preserved in substitutions. Parent paths use the
backend's explicit resolution rules. DirectoryFiles requires the selected source
and destination parent directories to exist; it never creates them implicitly.
Matching is nonrecursive even when deeper filenames would match the basename.

## Preflight and publication

Names are collected in deterministic sorted order. Before changing files, the
entire plan validates source/target paths, output collisions, case aliases,
source-target overlap, open handles, source sizes, copied-byte limits and budget.
A later conflicting or busy file prevents earlier files from changing. Wildcard
in-place copies are rejected even when overwrite is true. Directory hardlink
aliases and overlap are rejected when physical identities are available.

Overwrite false rejects any existing destination. Overwrite true reuses one
unambiguous existing destination spelling; multiple case aliases are rejected.
Directory cache aliases are refreshed/removed with the physical target rather
than retained as stale saved bytes. Predictable source/destination changes found
during preflight fail without publishing the helper's plan; fresh externally
changed data is preserved.

MemoryFiles and DeviceFiles prepare their file dictionary changes before a single
publication phase, preserving that dictionary's identity. DeviceFiles additionally
preflights every affected volume's mounted/read-only state, complete destination
quota, final file count and retained obsolete bytes. Overwriting on a retaining
volume charges old target bytes as garbage; deletion retains obsolete bytes
under the existing volume policy. Source files remain unchanged by copying.

DirectoryFiles snapshots every bounded source before the first copy. Each target
uses atomic byte replacement. DELETE does not read source bytes or impose an
input-size limit on an already existing regular file. It deletes only the matched
files in order, leaving subdirectories untouched.

**A DirectoryFiles batch is not a filesystem transaction.** Host I/O failures or
external changes during publication can leave earlier targets copied or earlier
matches deleted. No rollback or native abort-completion guarantee is claimed.
Authored tests preserve this partial-publication outcome explicitly. All budget
charges and predictable checks occur before publication, so budget failure during
preflight leaves the entire helper plan unapplied.

## Bounds, statuses and scope

At most 32767 entries may be scanned in a scope/backend and at most 32767 matches
may be selected. Copy snapshots total at most 64 MiB, with each file also bounded
by the existing backend limit. Virtual volume file-count and capacity limits
still apply. These guards run before any planned file mutation.

| Portable status | Meaning |
| --- | --- |
| 0 | Complete batch succeeded |
| 1 | No source matches |
| 2 | Target exists, aliases/targets overlap or unsupported template |
| 3 | A selected source or target is open/busy |

Unsafe paths, service-route violations, byte/count limits, quota failures,
preflight changes and host I/O errors raise under the existing FILE error
contract. These outcomes do not assert native alarm-code equivalence.
The nowait flag remains accepted intent; both values execute synchronously in
this offline model.

Configured plain PIP operands now use the separate
[pipe wildcard contract](pipe-wildcard-files.md), with complete capacity checks
and no automatic pipe creation. Socket and DAQ wildcard operands remain rejected
and never fall through to ordinary literal filenames. Existing finite exact
[pipe file operations](pipe-file-management.md) retain their separate contract.
Native binary program translation, physical device management, native
scheduling and strict behavior remain outside this feature.

Source forms are grounded in MARRC75KR07091E Rev N A.3.46 COPY_FILE, A.4.12
DELETE_FILE and A.18.10 RENAME_FILE. See the
[authored cross-backend regressions](../tests/test_wildcard_file_operations.py)
for translation and offline behavior evidence.

[Single-character question matchers](question-file-wildcards.md) now select exactly
one character in a source basename, alone or alongside stars. Destination question
substitution remains unavailable. The same preflight, limits and failure boundaries apply.
