# Virtual devices and storage

Six device/storage calls now work with `DeviceFiles`, an explicit virtual
MemoryFiles backend. They operate on supplied byte arrays and metadata. They
never mount or format host drives, query OS disks, or act on a DirectoryFiles
root. Plain MemoryFiles is also excluded from device-management calls.

Socket-tag MOUNT_DEV/DISMOUNT_DEV forms use the separate explicit
[Messaging service](communications.md). They change logical endpoint flags;
the virtual-volume forms below continue to use DeviceFiles.

| Call | Supported form |
| --- | --- |
| MOUNT_DEV / DISMOUNT_DEV | `(device, status)` |
| FORMAT_DEV | `(device, label, nowait, status)` |
| PURGE_DEV | `(device, status)` |
| VOL_SPACE | `(device, total, free, volume)` |
| DOSFILE_INF | `(device, item, value, status)` |

## Explicit backend and JSON

```python
from karel2py import runtime as rt

files = rt.DeviceFiles(
    {"RD:": {"capacity": 4096},
     "FR:": {"capacity": 8192, "garbage": 128},
     "UD1:": {"capacity": 4096, "info": {"DF_MANUFNAME": "Example"}}},
    {"RD:note.txt": "authored input"},
)
context = rt.ExecutionContext(files=files)
assert files.mount("RD:", False) == 0
```

Device names are case-insensitive letter-starting ASCII identifiers of up to
eight characters with a final colon. MF: is reserved as the combined RD:/FR:
purge selector. Source FILE names require a configured device prefix; only that
prefix is folded to uppercase. Paths remain case-sensitive relative POSIX names.
Empty components, traversal, absolute paths, extra colons, backslashes and control
characters are rejected. No physical path is derived from a virtual filename.

The required volume field is `capacity`. Optional fields are `mounted` (default
true), `label` (empty), `read_only` (false), `retain_deleted` (true for FR:, false
otherwise), `garbage` (zero) and `info` (empty). Labels must fit 11 printable ASCII
characters on load. DOS information maps DF_MANUFNAME, DF_PRODNAME, DF_SERIALNO,
DF_PRODID and DF_VENDID to supplied ASCII strings of at most 254 characters.
No manufacturer, identifiers or capacities are discovered automatically.

There must be 1..32 volumes. Individual and combined capacities are limited to
64 MiB, with at most 32767 files. The inherited per-file limit defaults to 16 MiB
and accepts 1..64 MiB. Initial live bytes plus garbage must fit every volume.
FROM:, DRAM: and CMOS: are total-only metadata entries and cannot contain files.

`to_config()` returns detached records. `from_config()` accepts the same records
with ASCII file strings or explicit `{"hex": "..."}` values. ExecutionContext
JSON stores this under `device_files`, including `volumes`, `files` and `limit`.
The ordinary `files` key cannot coexist with `device_files`. Saving retains
unmounted contents, labels, flags and garbage, while omitting live FILE handles.
Source filenames and device settings in this document are all virtual.

## Mounting, capacity and reclamation

MOUNT_DEV and DISMOUNT_DEV change only the configured mounted flag. Repeating a
mount-state request is allowed. Unmounted media keep their data, but file access
and device queries fail. Aggregate listings show mounted media only.
Dismounting a device with an open FILE returns busy without changing its state.

Used capacity is the sum of live file bytes and retained obsolete bytes. No
directory overhead, block alignment or fragmentation is inferred. A volume with
`retain_deleted` retains deleted/truncated bytes and bytes replaced by writes or
overwriting copies. Deleting an FR: file therefore need not increase free space
until purge. RD: normally releases replaced/deleted bytes immediately, while an
explicit initial garbage count can model retained obsolete storage.

Ordinary OPEN/WRITE/COPY_FILE/DELETE_FILE/RENAME_FILE, XML input and other FILE
operations share this backend. Quota/access failures preserve data and cursors
before raising. Same-volume renaming needs no copy space; cross-volume moves
reserve the destination and account for obsolete source data. MOVE_FILE checks
combined capacity for its complete batch before moving the first file. Ordinary
file missing/exists/busy statuses retain their existing conventions.

FORMAT_DEV requires mounted, writable file media without open handles. It clears
only the selected virtual volume's live files and garbage and stores the supplied
label, truncating it to 11 characters. Both nowait values complete synchronously
in this offline model. Its preflight consumes one execution step per selected
file, with no deletion if the budget fails or a FILE becomes busy before commit.

PURGE_DEV reclaims garbage and preserves every live file. MF: requires both RD:
and FR: to be configured, mounted, writable and closed; the complete request is
checked before either garbage count changes. No garbage returns the documented
DEV_NOTHING_TO_PURGE (85023), rather than deleting files or inventing reclaimed
blocks. No handlers run inside these synchronous operations.

## Queries and statuses

VOL_SPACE returns configured capacity, currently free bytes and label. RD:/FR:
return empty labels, following the reference. FROM:/DRAM:/CMOS: change only the
total output; free and volume retain their previous values. Missing/unmounted
devices and insufficient label capacity raise before any output changes.

DOSFILE_INF accepts the five DF_* constants and returns only the matching
supplied metadata. Missing information, invalid selectors, unmounted media and
small output destinations preserve the value output. Package IDs do not claim
native USB identifier or status encoding equality.

| Management status | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Requested DOS metadata absent |
| 2 | Invalid/unknown device, item, label or unsupported total-only mutation |
| 3 | Device unmounted |
| 4 | Open FILE prevents dismount/format/purge |
| 5 | Read-only volume rejects mutation |
| 7 | DOS information output too small |
| 85023 / DEV_NOTHING_TO_PURGE | Purge found no obsolete bytes |

VOL_SPACE has no status output, so it raises on failure. FILE quota/access
failures also raise; their source status destinations remain unchanged. Ordinary
argument typing, disjoint outputs, once-only selector capture and FOR-counter
protection remain in effect.

The [all-call example](../examples/virtual_devices.kl) demonstrates mounting,
capacity, deletion/reclamation, metadata, format and total-only queries. The
[capacity example](../examples/device_capacity.kl) shows an open-file purge guard
and overwrite reclamation. Both support saved-context replay. See
`virtual_device_policy` in translation reports and the
[semantic ledger](semantics/virtual_device_semantics.json).
