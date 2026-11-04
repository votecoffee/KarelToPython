# Directory-pattern file batches

Pythonic COPY_FILE, DELETE_FILE and RENAME_FILE now accept ordinary source
patterns in directory components. Supply MemoryFiles, DeviceFiles or rooted
DirectoryFiles explicitly. This is an authored offline extension, without native
compiler/controller wildcard equivalence or host/device discovery.

```karel
COPY_FILE('src/*/part?.KL','dst/backup_*.PY',FALSE,FALSE,status)
RENAME_FILE('src/**/part*.KL','done/*.DAT',FALSE,status)
DELETE_FILE('src/**/old?.DAT',FALSE,status)
```

## Component matching and scope

| Source component | Meaning |
| --- | --- |
| `cell*` | Zero or more characters within one directory name |
| `cell?` | Exactly one character within one directory name |
| Whole directory `**` | Zero or more directory components |
| Final basename `*`/`?` | Existing filename matching, without consuming a slash |

For example, src/*/a.KL matches src/cell/a.KL and excludes src/a.KL or
src/cell/deep/a.KL. src/**/a.KL includes all three. Repeated globstar components
remain bounded component matching, without exponential backtracking. A final
filename ** retains ordinary star semantics rather than creating recursion.

The literal prefix before the first directory matcher fixes the scan root.
Optional device labels stay literal. Matching below that backend-resolved root
is case-insensitive; literal root resolution keeps the backend's rules. A source
without directory matchers keeps its existing nonrecursive parent selection.
Unqualified logical roots do not discover other device namespaces.

Literal destination parents retain the existing flattening behavior. One optional
whole-directory ** [destination placeholder](directory-destinations.md) now inserts
source directories relative to the captured literal scan root. Every expanded
parent must already exist for DirectoryFiles; no directory is created implicitly.
Existing full-source basename/stem/extension templates keep their rules. Two
sources mapping to one destination still reject the complete batch before mutation.
RENAME never overwrites; COPY retains its explicit overwrite flag.

## Validation and bounds

Names remain relative bounded ASCII paths, at most 254 characters. Traversal,
empty/dot components, bracket patterns, absolute host paths, unsafe device names
and reserved basenames remain rejected. Rooted recursive scans reject encountered
links and junctions and recheck containment as they traverse. They never remove
directories; DELETE removes matched regular files only.

At most 32,767 entries are scanned/matched under existing backend limits. Rooted
scans count directory and file entries; explicit in-memory banks retain their
existing whole-bank count bounds. Scans and matcher-component work charge the
execution budget. COPY retains the 64 MiB total payload snapshot limit and
per-backend byte/capacity rules. DELETE does not decode or read file payloads.

The existing engine validates sorted selection, duplicate/case/physical aliases,
source-target overlap, busy handles, target templates, source bytes and complete
quotas before publication. It rescans names before publishing to detect new,
removed or changed nested sources. Earlier argument/checkpoint effects remain
visible when a later preflight fails.

Memory/device changes publish prepared dictionaries and device accounting.
DirectoryFiles still publishes per file: a late OS error or external race can
leave earlier files changed. There is no new filesystem transaction, rollback or
concurrent-host isolation claim.

## Pipes, other calls and saved state

Plain PIP sources remain flat configured names. An ordinary directory pattern may
copy/rename to preconfigured pipe targets using the existing capacity, overwrite,
empty-reservation and ownership rules. Socket/DAQ routing, pipe discovery and
implicit configuration remain excluded. Both NOWAIT values retain synchronous
finite batch execution.

MOVE_FILE and FILE_LIST retain their separate existing pattern contracts. This
change does not reinterpret their sources. Context JSON stores ordinary resulting
bytes, device accounting and closed pipe configurations; it does not store glob
objects, open handles or suspended plans. Examples use DONE guards for replay.

## Examples and evidence

- [Globstar copy and listing](../examples/directory_glob_copy.kl)
- [Single-level rename](../examples/directory_glob_rename.kl)
- [Recursive deletion](../examples/directory_glob_delete.kl)
- [Virtual cross-volume rename](../examples/directory_glob_devices.kl)
- [Linked file batch](../examples/directory_glob_project/main.kl)
- [Linked reserved-pipe batch](../examples/directory_glob_pipe_project/main.kl)

```console
python -m karel2py examples/directory_glob_copy.kl -o batch.py
python batch.py --context examples/directory_glob_copy.services.initial.json --state-out state.json
python batch.py --context state.json
```

The [authored tests](../tests/test_directory_globs.py) cover component/globstar
matching, devices, rooted files, link/junction guards, hardlink aliases, capacity,
budget, preflight races, pipes, linked calls and persistence. Independent examples
verify state, typed saved-variable rows and resulting backend bytes/accounting.
Reports expose directory_glob_policy; the
[semantic ledger](semantics/directory_glob_semantics.json) records the same scope.
Offline tests do not establish native compiler or controller acceptance.
