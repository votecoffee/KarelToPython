# Logical collection ARRAY variable transfers

Pythonic GET_VAR and SET_VAR now copy whole logical PATH/QUEUE_TYPE banks and
selected ARRAY rows/planes. This is an authored offline value extension. Native
compiler source acceptance, native ABI/status equivalence and controller behavior
remain unverified; strict mode remains future work.

```karel
VAR source,target:ARRAY[2,2]OF QUEUE_TYPE entry,status:INTEGER
-- Inside BEGIN, after preparing source[2,1] and source[2,2]:
GET_VAR(entry,'','SOURCE[2]',target[2],status)
SET_VAR(entry,'','TARGET[2]',source[2],status)
```

## Selection and exact types

Declared globals, created variables, explicit context bindings, borrowed formals,
linked owners and selected named components use the same contract. Blank program
names select the current module. Quoted paths remain checked static paths; no
routine-local discovery, expressions in quoted indexes or host attributes are
introduced. Adjacent numeric brackets normalize like comma indexes.

Selected schemas must match exactly: concrete dimensions, ARRAY identities and
named children, terminal PATH/queue types, PATH node/header field layouts,
capacities and positional widths. Generic formals inherit actual storage types.
There is no short-bank/tail copy, nominal erasure, reshape, numeric promotion or
robot-model conversion inside a collection. Whole banks and anonymous suffixes
can copy when their resolved schemas match.

[Logical source values](collection-source-values.md) now add ARRAY assignments,
private arguments/results and independent prefixes under a separate ownership
contract. READ/WRITE/UNINIT, FILE transfers and resource STRUCTURE fields retain
their existing guards. Grouped SET sources may snapshot; GET outputs require direct
writable storage. Generic resource codecs still reject live borrowed windows.

## Capture, identity and partial data

SET snapshots its fourth argument once before later status selectors. GET resolves
and snapshots the named source after output selectors finish. An output/source
prefix evaluates receiver and indexes once, validates the containing resource
bank, and retains original cells. Replacing a root list later cannot retarget the
capture; resizing retained storage fails before publication. Pause/resume retains
an already captured private source snapshot.

Copying preserves destination ARRAY containers, owned collection objects and
compatible PATH header containers. It installs independent PATH nodes and drops
copied queue buffer links. Old node/list/field aliases remain on detached storage;
source aliases remain independent. Unselected rows retain their original nodes,
objects and queue buffer links. A self-copy uses the same rules.

Known and partial PATH fields, missing node/header containers and unknown BYTE
markers follow existing logical codecs. Queue initialized state, ordered entries
and last sequence counters are copied. Restored queues bind explicit compatible
INTEGER buffers when a later queue operation needs one.

| Status | Portable result |
| --- | --- |
| 0 | Copied without tracked missing data |
| 1 | Named lookup failed; data/cache/entry unchanged |
| 3 | Exact selected schemas differ; data/cache/entry unchanged |
| 12311 | Copied tracked missing PATH data or an uninitialized queue |

Unknown BYTE markers alone do not imply tracked missing data. Malformed known
values, missing ARRAY containers, invalid collection states or exceeded bounds
raise a source-located runtime error before data/cache/entry/status publication.
Earlier completed argument effects remain visible. Named prefix lookup failures
retain the existing status-1 resolver boundary.

## Bounds, aliases and saved state

Each selected source/receiver snapshot is bounded to 32,767 units: collection
descriptors, PATH header/node scalar leaves and two scalar units per queue entry.
Logical rank remains at most three; data components retain their 64-level bound.
Prefix capture additionally validates the containing bank. Ordinary later
collection growth, further captures and JSON/VR snapshots keep their separate
bank-wide limits.

Shared owned collection cells, headers or node storage fail validation. Outputs
must be disjoint from entry/status storage; SET checks its resolved named target
as well. Existing FOR, positional-field, resource-field and exact linkage guards
remain active. No lookup publishes a new variable root or live view binding.

JSON and [VR/DRAM archives](collection-array-archives.md) retain ordinary logical
values and creation metadata. They omit live windows, queue buffers, aliases,
callbacks and suspended execution. The runnable examples use DONE guards to
retain completed data during saved-context replay.

## Examples and evidence

- [Whole PATH bank and source independence](../examples/collection_transfer_paths.kl)
- [Queue rows, independent buffers and later dequeue](../examples/collection_transfer_queue_rows.kl)
- [Partial data status](../examples/collection_transfer_partial.kl)
- [Created matrix row](../examples/collection_transfer_dynamic.kl)
- [Linked PATH owners](../examples/collection_transfer_path_project/main.kl)
- [Linked generic queue rows](../examples/collection_transfer_queue_project/main.kl)

```console
python -m karel2py examples/collection_transfer_paths.kl -o copy.py
python copy.py --state-out state.json
python copy.py --context state.json
```

The [authored tests](../tests/test_collection_array_transfers.py) cover whole and
selected storage, evaluation order, aliases, protected outputs, partial data,
quotas, dynamic banks, linked calls and JSON/VR integration. Translation reports
expose collection_array_transfer_policy; the
[semantic ledger](semantics/collection_array_transfer_semantics.json) records the
same offline scope. Runtime equivalence on robots is not claimed.
