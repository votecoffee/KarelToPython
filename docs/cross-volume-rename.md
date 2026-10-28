# Virtual cross-volume wildcard rename

Pythonic wildcard RENAME_FILE can move a complete selected batch between volumes
within one explicitly supplied DeviceFiles bank. It uses the existing
[wildcard rename](wildcard-rename.md) pattern, template, busy and no-overwrite
rules. Exact-name calls retain their previous behavior.

```karel
RENAME_FILE('FR:src/*.KL','RD:archive/*.PY',FALSE,status)
```

Both volumes must be configured, mounted and writable. Names remain relative to
their selected virtual volumes; device labels are canonicalized while source
filename spelling follows the existing template rules. A standalone destination
`*` preserves complete names, including extensionless sources. Parent paths are
logical DeviceFiles paths and need no host directory creation.

This is an offline extension to the portable wildcard algorithm. It opens,
mounts, discovers or copies no host drive or controller device and establishes no
DirectoryFiles host cross-volume behavior. PIP-to-ordinary, ordinary-to-PIP and
renames between separate backend banks remain unsupported.

## Quota and retention planning

Every selected source and generated destination is validated before publication.
The plan rejects busy handles, case aliases, duplicate targets, source-target
overlap, invalid paths, unsupported templates and existing targets. Source names,
bytes, identity and destination entries are rechecked after the initial plan;
both source and target mounted/writable states are checked again before commit.
Execution-budget charges occur during preflight, including bounded source-byte
fingerprinting.

The helper then prepares the complete final file mapping and garbage counts:

| Change | Used-byte effect |
| --- | --- |
| Target volume receives a file | Add its full retained byte length |
| Source with `retain_deleted=True` loses a file | Replace its live bytes with the same amount of garbage |
| Source with `retain_deleted=False` loses a file | Remove its live bytes without adding garbage |
| Same-volume rename | Preserve live bytes and garbage |

Existing target garbage and files in every target parent count toward the target
volume's capacity. The complete batch must fit; space available on the source or
an unrelated volume cannot subsidize the target. A later file that would exceed
capacity prevents earlier files from moving or creating source garbage. Empty
files add no bytes or garbage. A retaining source already at capacity can still
move files because their live bytes become garbage without increasing its used
total.

For example, moving 5 live bytes from a retaining source that has 4 other live
bytes and 3 garbage bytes leaves its used total at 12, with 8 garbage bytes. A
target that already has 1 live byte and 2 garbage bytes needs capacity for all 8
bytes after the move. Its own `retain_deleted` setting creates no extra garbage
because rename never overwrites a target.

Rename preserves the final global file count. A bank containing 32,767 files can
move them without needing a temporary slot. No per-file reservation, payload copy
or COPY_FILE copied-byte budget is used. The final global count and each volume's
final live-plus-garbage usage are checked before any bank mutation.

## Publication and errors

Successful publication updates the existing file dictionary and volume garbage
fields from prepared state in one phase, without a callback, budget check or
scheduler yield between updates. Original payload objects, the file dictionary,
volume dictionary and individual volume rows retain their identities. Unrelated
open handles retain their buffers, ownership and cursors. Predictable preflight
failures leave the helper's complete plan unapplied. No host-thread transaction
or controller atomicity guarantee is implied.

Existing portable statuses remain: 0 means success, 1 means no selected source,
2 means collision/overlap/unsupported template or cross-bank rename, and 3 means
a selected source or destination is busy. Unknown/unmounted/read-only volumes,
invalid paths, changed source data, quota failures and budget exhaustion raise
KarelRuntimeError; these errors preserve the status output until a result can be
returned. A capacity failure uses the complete-wildcard-rename diagnostic. These
statuses are portable choices rather than native controller error numbers.

Same-volume wildcard rename still consumes no additional capacity and creates no
garbage. Ordinary MemoryFiles, plain FilePipes, DirectoryFiles and exact-name
rename behavior retain their existing contracts. Closed DeviceFiles context JSON
preserves renamed names, bytes, garbage and volume metadata; normal live-handle
serialization restrictions remain. Authored coverage is in
`tests/test_cross_volume_rename.py` alongside the existing wildcard and exact
rename regression suites.
