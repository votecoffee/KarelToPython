# Directory-pattern moves and listings

Pythonic MOVE_FILE and FILE_LIST accept star/question matchers in ordinary
source-directory components and a whole-directory ** matcher for zero or more
components. This authored offline extension uses explicitly supplied MemoryFiles,
DeviceFiles or rooted DirectoryFiles. It does not discover controller devices,
host roots, native filesystem metadata, socket/DAQ endpoints or pipe subdirectories.

```karel
MOVE_FILE('RD:jobs/**/part?.KL',status)
FILE_LIST('RD:jobs/cell?/part*.KL',0,3,names,count,status)
FILE_LIST('RD:jobs/**/*.KL',2,4,names,count,status)
```

## Pattern scope

Directory * consumes zero or more characters within one component; ? consumes
one character. A whole directory ** consumes zero or more directory components.
A final basename ** remains a filename matcher. Repeated globstars do not create
exponential backtracking. The literal prefix before the first directory matcher
fixes the scan root/device. Matching below that backend-resolved prefix is
case-insensitive; literal-prefix lookup retains the backend's rules.

Without a directory matcher, each call retains its existing selection contract:
MOVE_FILE does not recurse, while FILE_LIST uses its backend's prior wildcard
rules, including whole-key matching. This avoids changing existing flat listing
patterns such as *.KL. Explicit directory patterns do not infer device namespaces
from an unqualified logical root. Plain PIP listing remains flat.

Explicit patterns require bounded relative ASCII names and reject traversal,
empty/dot components, bracket classes and unsafe device syntax. MOVE_FILE retains
its single optional device-root separator and slash/backslash normalization.
FILE_LIST directory patterns use forward slashes. Selected paths are bounded to
254 characters, and scans to 32,767 entries. Rooted scans count files and
directories; in-memory scans retain a whole-bank bound. Scanning and matcher work
charge the ordinary execution budget. Encountered links/junctions under a
resolved scan root are rejected. No file payload is read during selection.

## MOVE_FILE

Only the explicit RD/FR pair is supported. Each selected source keeps its entire
relative path under the peer device: RD:jobs/cell/a.KL becomes
FR:jobs/cell/a.KL. Files with equal basenames in distinct directories remain
distinct. All destination parents must already exist for DirectoryFiles; no
directory is created or moved. Missing mappings, identical roots and overlapping
rooted scan mappings retain unsupported-pair status 4.

The complete plan checks sorted names, busy source/target handles, case/duplicate
collisions, selected rooted physical aliases, source sizes and virtual-device
capacity before the first move. Retained source bytes use the existing device
accounting convention. Busy files return status 3; collisions return 2; an empty
selection returns 1. Invalid paths and backend/budget failures raise ordinary
runtime errors and preserve the status output. Earlier expression effects stay
visible if later preparation fails.

Publication retains ordered per-file backend renames. A late OS, status or budget
failure may leave earlier moves completed. The runtime does not retry or roll
back completed moves, create a filesystem transaction or promise isolation from
external host edits. These rules apply to old and newly extended forms.

## FILE_LIST

Selection sorts complete backend keys before skip, page length and formatting.
Formats 0 through 4 retain their [existing definitions](file-listing.md), including
blank timestamp fields. Format 0 preserves full keys; formatted results remove
device/directory prefixes. Duplicate stems stay separate; no formatting reorder
occurs. Unused slots retain initialized or unknown contents, and exhausted pages
return zero count without clearing names.

Busy descriptors remain listable. Metadata inspection uses buffered length while
open and regular-file length while closed; it does not read payloads, flush,
advance cursors or close handles. The complete page is validated before names and
count change. Capacity errors preserve both; path/backend/budget errors preserve
all outputs. Listing has no serialized cursor or concurrent-filesystem snapshot.

## Linked calls, persistence and examples

Generated Python and linked source routines use the same runtime implementation.
Context JSON stores resulting ordinary file bytes and virtual-device accounting;
it does not store glob objects, pending scans, live descriptors or suspended calls.
DirectoryFiles roots/mappings remain host-supplied, and saved file snapshots load
through the existing MemoryFiles convention. Example DONE guards support exact
saved-state replay.

- [Recursive move](../examples/directory_move.kl)
- [Virtual-device move/accounting](../examples/directory_move_devices.kl)
- [Component listing](../examples/directory_listing.kl)
- [Paginated metadata](../examples/directory_listing_formats.kl)
- [Linked move](../examples/directory_move_project/main.kl)
- [Linked listing](../examples/directory_listing_project/main.kl)

```console
python -m karel2py examples/directory_move.kl -o move.py
python move.py --context examples/directory_move.services.initial.json --state-out state.json
python move.py --context state.json
```

The [regressions](../tests/test_directory_file_queries.py) and independent saved
state fixtures establish offline behavior. Reports expose directory_file_query_policy;
the [semantic ledger](semantics/directory_file_query_semantics.json) records scope.
Native source/compiler/controller behavior remains unverified. Strict mode remains
future work.
