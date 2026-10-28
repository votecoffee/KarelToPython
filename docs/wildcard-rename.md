# Wildcard rename

Pythonic RENAME_FILE supports bounded, nonrecursive star batches over explicit
MemoryFiles, DirectoryFiles, DeviceFiles and plain FilePipes. Calls without a star
retain their existing exact-name behavior.

```karel
RENAME_FILE('src/part*.KL','dst/backup_*.PY',FALSE,status)
RENAME_FILE('PIP:*.DAT','PIP:*.OLD',TRUE,status)
```

The signature remains `(source,destination,nowait,status)`. NOWAIT must be a
BOOLEAN; both values execute this finite offline operation synchronously. There
is no overwrite option. The native RENAME_FILE manual does not establish this
star-expansion algorithm: wildcard rename is an explicit Pythonic extension,
without a native filesystem or controller equivalence claim.

## Patterns and templates

The existing [wildcard FILE pattern rules](wildcard-file-operations.md) apply.
Stars occur only in the final filename. Parent paths and optional device labels
are literal and remain within the supplied bank or directory root. Selection is
case-insensitive, sorted and nonrecursive. Question marks, bracket patterns,
directory stars, traversal, absolute paths, symlinks, control characters and
reserved device basenames fail closed. Literal brackets already present in a
matched filename remain characters.

Destination templates use complete source components rather than the portion
captured by a source-pattern star. Split the final filename at its last dot;
each nonempty destination stem and extension permits at most one star.

| Source match | Destination template | Result |
| --- | --- | --- |
| `partOne.KL` from `part*.KL` | `backup_*.PY` | `backup_partOne.PY` |
| `part.rev1.KL` | `new_*.copy*` | `new_part.rev1.copyKL` |
| `LOG` | `saved/*` | `saved/LOG` |

A standalone destination `*` preserves the complete filename and permits
extensionless sources. Other wildcard substitutions require a nonempty source
stem and extension. A literal destination can accept a single selected source;
multiple sources mapping to that name are rejected. Ambiguous templates such as
`prefix_*` or `**.DAT` are rejected. `*.*` selects names containing a dot, without
special native DOS matching behavior.

MemoryFiles and DeviceFiles have logical parent paths. DirectoryFiles requires
existing physical parents and uses its explicit device mappings. Plain PIP
names have one flat scope, are normalized to uppercase and may use the optional
root slash. A preserving `PIP:*` destination overlaps its source and is rejected.

## Whole-batch preflight

Before any rename, the complete plan validates paths, selected sources, target
names, parent directories, source/target handle activity and execution budget.
Case aliases, physical source aliases when available, duplicate generated
targets, source-target overlap, self-renames, cycles and existing targets are
rejected. An open later source or target prevents earlier names from moving.
Open unflushed DirectoryFiles entries are included in busy checks. The helper
rechecks selected names, destination entries, source identity and metadata before
publication. In-memory retained bytes are fingerprinted in bounded chunks and
checked again without publishing intermediate state.

PIP-to-ordinary and ordinary-to-PIP renames are rejected. DeviceFiles wildcard
renames stay within one explicitly configured volume, whose mounted and writable
state is checked. Exact cross-volume calls retain their previous behavior. This
operation does not discover another backend, route socket names or treat DAQ
PIP names as ordinary pipe data.

| Portable status | Meaning |
| --- | --- |
| 0 | Complete batch renamed |
| 1 | No selected source |
| 2 | Existing target, collision, overlap, unsupported template or cross-bank/volume rename |
| 3 | Selected source or target is open/busy |

Invalid paths, missing required services, device state, inconsistent backend
registrations, source changes and budget failures raise KarelRuntimeError with
the ordinary runtime diagnostics. They preserve the status output until a status
is returned. These are portable statuses, without native numeric status claims.

## Publication and retained state

MemoryFiles and DeviceFiles prepare every key move before updating their existing
file dictionary. Payload byte objects are moved, without a copy allocation or
copied-byte quota. Same-volume rename consumes no extra volume capacity, reserves
no file slot and adds no garbage, including on a full retaining volume.

Plain FilePipes move each source's configuration and retained byte object together
to its previously unconfigured destination. The file and configuration dictionary
identities remain stable; capacity reservations, CMOS flags, record sizes and
formatting metadata follow their source. A full 32-pipe bank can rename without
allocating another pipe. The operation does not apply COPY_FILE's configured
destination replacement rules. A selected pending READ is busy; unrelated live
pipe handles and pending reads retain their original buffers and registrations.

DirectoryFiles performs all predictable checks and budget charges first, then
uses its existing per-file rename operation in sorted order. It does not read or
rewrite source bytes, so already existing regular files need not fit the copy
input-size limit. Cache entries follow successful moves and stale case aliases
are removed. **A directory batch is not a filesystem transaction:** a late host
I/O failure or external change can leave earlier files renamed. No batch rollback
or concurrent-host isolation guarantee is claimed.

Closed memory/device/pipe banks serialize their renamed names, retained bytes
and unchanged service metadata through the existing context JSON format. Live
handles retain their existing serialization restrictions. Authored tests are in
`tests/test_wildcard_rename.py`; existing COPY, DELETE and exact RENAME regression
cases remain in the FILE management and wildcard test modules.
