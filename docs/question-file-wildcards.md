# Single-character FILE wildcards

Pythonic COPY_FILE, DELETE_FILE, RENAME_FILE and MOVE_FILE accept `?` in their
source's final filename. It matches exactly one ASCII character. Existing `*`
matches zero or more characters; they can be combined.

```karel
COPY_FILE('src/part?.dat','stage/*.bak',FALSE,FALSE,status)
RENAME_FILE('stage/part?.bak','done/*.dat',FALSE,status)
DELETE_FILE('src/part?.dat',FALSE,status)
MOVE_FILE('RD:job?.kl',status)
```

`part?.dat` matches `part1.dat` and `partA.dat`, and excludes `part.dat` and
`part12.dat`. Matching remains case-insensitive. Question matching is an explicit
portable Pythonic extension; native DOS/controller matching is unverified.

Destination templates retain their existing whole-source stem/extension star
substitution. Question marks cannot be destination substitutions: a destination
template containing one returns invalid-template status 2 without mutation.
For example, `backup_*.py` uses the full matched stem, rather than a single
character captured by the source question mark.

Both source matchers are confined to the final basename. Bracket classes,
wildcard directories, recursive search, traversal, implicit devices, socket/DAQ
endpoints and unrestricted host paths remain blocked. Paths and selected files
retain their ordinary backend checks.

## Existing batch guarantees

MemoryFiles, rooted DirectoryFiles, DeviceFiles and explicitly configured plain
FilePipes use the existing [wildcard batch engine](wildcard-file-operations.md).
Source collection is sorted and bounded, with complete predictable collision,
busy-handle, alias, capacity and execution-budget checks before publication.
Pipe COPY targets must already be configured. RENAME retains the existing
same-bank and cross-volume rules without overwrite.

MOVE_FILE retains its RD-to-FR or FR-to-RD contract and complete batch preflight;
it does not acquire a destination-template argument. No-match, busy, capacity and
other statuses follow the corresponding existing operation.

Memory/device publication uses staged state. A rooted directory batch still
consists of ordered per-file operations; host failure during publication can
leave earlier files changed. No new rollback or filesystem transaction is claimed.

The [standalone example](../examples/question_file_wildcards.kl) copies, renames
and deletes selected names while retaining `part12.dat`. The
[linked example](../examples/xml_joint_files_project/main.kl) combines supplied
XML updates, private joint widths and a selected file batch across source modules.
