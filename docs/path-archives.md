# Logical PATH variable archives

Pythonic variable archives now include owned PATH roots in SAVE, LOAD, CLEAR,
variable-only and mixed recursive PBR batches, SAVE_DRAM and explicit host DRAM
restore. These are logical JSON snapshots, using the existing
`karel2py-variables-v1` format. Native controller VR binaries, PATH association
records, byte layout and controller restore behavior remain unverified.

Use an explicit `VariableArchives` service. File operations require an exact
MemoryFiles or DeviceFiles backend, with the existing archive device, protection,
quota and busy-file checks. No backend is needed for CLEAR or SAVE_DRAM.

```python
from karel2py.runtime import ExecutionContext, MemoryFiles, VariableArchives
context = ExecutionContext(variable_archives=VariableArchives(), files=MemoryFiles())
```

```karel
PROGRAM path_archive
TYPE node_t=STRUCTURE value:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t
VAR route:route_t
ROUTINE transact
VAR status:INTEGER
BEGIN
  APPEND_NODE(route,status)
  route[1].value=7
  SAVE('PATH_ARCHIVE','route.VR',status)
  route[1].value=99
  LOAD('route.VR',0,status)
END transact
BEGIN
  transact
END path_archive
```

A routine-local status avoids overlapping a restored global. See the
[complete copy](../examples/path_archive_values.kl),
[partial data](../examples/path_archive_partial.kl),
[dynamic root](../examples/path_dynamic_archive.kl),
[DRAM save point](../examples/path_dram_archive.kl) and
[linked project](../examples/path_archive_project/main.kl) examples.

## Values, identity and clearing

Each PATH row retains exact NODEDATA/PATHHEADER schemas, nominal names, all nodes
and header data, including partial fields, missing whole node/header containers
and unknown BYTE markers. Known values remain checked, including finite REALs,
CONFIG turn bounds, STRING capacities and SHORT/BYTE domains. Empty default PATH
values are valid. A whole missing root or malformed storage is rejected.

LOAD requires an exact destination schema. Existing PathValue roots and compatible
header containers retain their identity, including nested ARRAY/joint data.
Publication installs an independent nodes list. Captured old node/list/field
aliases stay on detached old storage. No aliases are serialized. New roots publish
the validated decoded value directly, without allocating a throwaway PATH.

CLEAR retains the root and compatible header aliases, resets header data to its
ordinary missing/unknown initial state, and replaces nodes with an empty list.
It retains declarations, bindings and dynamic creation metadata. Explicit host
`bank.restore_dram(program._state, name)` uses the same load guards and identity
rules; SAVE_DRAM never installs an automatic power-up restore hook.

## Bounds and atomic publication

A snapshot has at most 32767 total units across ordinary data and PATH contents.
A PATH costs one descriptor plus its header's declared scalar leaves plus every
node's declared scalar leaves. Missing containers still count their full declared
width. This snapshot accounting is independent of dynamic creation reservation,
which continues to reserve only the descriptor and header at creation time.

Each component retains the 64-level data-schema bound. All archive records' schemas,
node counts, aggregate units and creation policies are checked before typed decode.
The existing 32-level JSON nesting, byte, namespace, graph and backend limits still
apply; a valid data schema can exceed the separate archive JSON depth limit.

The entire selected batch is prepared before variable/metadata/graph publication.
Exact root/header/node/index and nested joint aliases participate in overlap checks,
including shared empty PATH roots or node lists. Disjoint status outputs, foreign
active/paused execution, connected timer claims, program protection and existing
FOR write guards remain in force. Sparse node/field bindings must identify the
exact storage selected under their archived root.

A malformed later member, incompatible nominal schema, creation-policy conflict,
protected alias or quota failure leaves every planned namespace unchanged, apart
from the operation's status output and already completed source effects. Mixed
TP/VR batches also retain TP data on failed PATH preflight. The
[variable archive status contract](variable-archives.md) is unchanged.

## Compatibility and exclusions

Older v1 archives that list a PATH under `excluded` remain readable and leave that
root untouched. New PATH rows use the existing typed collection codec; older
application versions may reject them. Unlisted destination roots remain unchanged.
Created PATH policy survives fresh-namespace load and context replay. Reattach
source layouts for later alias-based creation or linked code; archives contain data.

FILE roots, resource fields/ARRAYs, imported FROM globals and inferred system
schemas remain excluded. Live handles, queue buffers, suspended stacks, callbacks,
native allocation and proprietary PATH association/VR records are not restored.
Strict mode remains a future milestone. The compiler's `path_archive_policy` and
[semantic ledger](semantics/path_archive_semantics.json) describe this portable
extension and its authored verification separately from native evidence.
