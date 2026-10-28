# Plain PIP file management

Pythonic mode routes explicit `PIP:` names in `COPY_FILE`, `DELETE_FILE`,
`RENAME_FILE` and `FILE_LIST` to the configured
[plain file-pipe service](communications.md). The reference manual describes
ordinary file I/O on the PIP device, excluding directory-changing/creation/removal
operations. This implementation uses finite retained-byte snapshots and explicit
configuration, without a native pipe device or operating-system connection.

```karel
PROGRAM pipe_copy
VAR source_file:FILE status:INTEGER
BEGIN
  PIPE_CONFIG('PIP:LOG.DAT',FALSE,1,0,'',0,status)
  PIPE_CONFIG('PIP:COPY.DAT',FALSE,1,0,'',0,status)
  OPEN FILE source_file('WO','PIP:LOG.DAT')
  WRITE source_file('sample',CR)
  CLOSE FILE source_file
  COPY_FILE('PIP:LOG.DAT','PIP:COPY.DAT',TRUE,FALSE,status)
  RENAME_FILE('PIP:COPY.DAT','PIP:SAVED.DAT',FALSE,status)
  DELETE_FILE('PIP:LOG.DAT',FALSE,status)
END pipe_copy
```

Supply `ExecutionContext(file_pipes=FilePipes())` or JSON
`{"file_pipes": {}}`. No ordinary `files` backend is needed when every endpoint
and listing pattern is an explicit PIP name.

## Copy finite retained data

`COPY_FILE(source,destination,overwrite,nowait,status)` can copy between two
configured pipes or between a configured pipe and an explicit ordinary
MemoryFiles, DirectoryFiles or DeviceFiles backend. Each endpoint is selected
independently by its explicit PIP prefix. Names without that prefix use the
ordinary backend, including its existing device mappings and confined paths.

The operation snapshots the source's current retained bytes. It does not consume
history, wait for future writes, follow producers, format dictionary records or
convert text/binary data. After circular overflow, only the still-retained suffix
is copied. Both values of `nowait` perform the same synchronous offline copy.

The source and destination must be closed. A pipe destination must already be
configured. Because that name already exists, its copy requires `overwrite=TRUE`,
even when it contains no bytes. No missing pipe or configuration is created by a
copy. Replacement preserves all destination configuration fields, including
sector count, CMOS intent, record size and dictionary metadata.

Every copied byte must fit the destination. A pipe replacement rejects excess
data rather than applying circular truncation. Ordinary backend byte limits,
virtual volume quotas, mounted/read-only flags and obsolete-byte accounting
remain active. DirectoryFiles publishes through its atomic replacement helper;
failed publication retains the previous file and cache. Supplied filesystem
roots, device aliases and path/symlink checks remain in force.

Each 4096-byte block charges the execution budget before destination publication.
An error during snapshot validation, capacity checks, budgeting or publication
retains the previous destination. No source bytes or configuration are removed.

## Rename and delete

`RENAME_FILE` supports a closed source and a new destination name within PIP.
Both names must carry an explicit PIP prefix. The complete configuration and
retained data move together; no additional pipe slot or reserved sectors are
required. An already configured destination rejects the rename. Cross-backend
renaming returns portable invalid status 2; copy explicitly to transfer bytes.

`DELETE_FILE` removes both the closed pipe's bytes and configuration. Its reserved
capacity becomes available for later PIPE_CONFIG calls. Open pipes, including a
pipe with a retained waiting READ, remain busy. `nowait` remains synchronous for
rename/delete as well.

## Listings

`FILE_LIST('PIP:pattern',skip,format,names,count,status)` lists configured plain
pipes in canonical uppercase name order. Names accept the same plain basenames
and optional single leading slash as ordinary PIP opens. Patterns support `*`
and `?`, with case-insensitive matching. Directory paths, traversal, additional
device prefixes and character-class patterns are rejected.

All [FILE_LIST formats](file-listing.md) are reused: 0 full canonical PIP keys,
1 stems, 2 extensions, 3 basenames with extensions, and 4 portable size metadata
with blank date/time columns. Format 4 keeps its existing 8.3-name/five-digit-size
limits. Listing can inspect an open pipe's current retained size and does not
advance FILE cursors. Filtering and pagination precede formatting; the complete
page must fit before names/count change. Unused destination slots are retained.

## Status, scope and persistence

For pipe copy/rename/delete, portable status 0 means success, 1 missing source or
configured destination, 2 existing destination or unsupported cross-backend
rename, 3 busy endpoint and 4 excessive pipe replacement size. FILE_LIST retains
its separate documented invalid/capacity statuses. Source output/reference
guards, malformed names, missing services, host access failures and ordinary
backend capacity/protection failures raise their existing runtime errors.

Explicit PIP routing takes precedence over similarly named ordinary memory-file
keys. DAQ pipes and socket tags are not generic file-management endpoints. Plain
listings exclude DAQ registrations, and ambiguous plain/DAQ names fail closed.
Unconfigured names do not fall through to ordinary files. Calls with no PIP
operand retain their previous ordinary-backend dispatch. MOVE_FILE keeps its
existing RD/FR-only contract; it does not move PIP configurations or data.

[Wildcard COPY/DELETE](pipe-wildcard-files.md) additionally select bounded batches
from explicitly configured plain pipes. Every pipe target must already exist,
and all snapshots must fit without circular truncation. RENAME remains exact.

FilePipes JSON retains renamed configurations and complete replacement bytes,
and omits deleted entries. Live handles and pending READs must still close/finish
before saving. Context restoration does not recreate tasks, producers or native
CMOS lifetime. The [authored regressions](../tests/test_pipe_file_management.py)
cover cross-backend snapshots, busy/configuration guards, output atomicity,
quota/path failures, scope separation and JSON replay. These are offline results;
native file alarms, device scheduling and strict equivalence remain unverified.
