# Logical collection ARRAY archives

Pythonic VR archives now include owned PATH and QUEUE_TYPE ARRAY roots. SAVE,
LOAD, CLEAR, variable-only or mixed recursive batches, SAVE_DRAM and explicit
host restore_dram use the existing karel2py-variables-v1 typed JSON format.
These are portable logical snapshots, without native VR binary or controller
restore claims. Strict mode remains future work.

```karel
VAR jobs:ARRAY[2]OF QUEUE_TYPE buffers:ARRAY[2,3]OF INTEGER
-- Inside a routine, with local status/sequence and explicit archive/files banks:
INIT_QUEUE(jobs[2])
APPEND_QUEUE(17,jobs[2],buffers[2],sequence,status)
SAVE('JOB','JOB.VR',status)
LOAD('JOB.VR',0,status)
```

## Included roots and data

Owned static or dynamically created collection arrays retain exact resolved
schemas, named components, concrete dimensions and creation metadata. Logical
rank remains at most three. Imported globals remain excluded from the importing
module; archive their defining owner. Whole FILE storage and borrowed live row
carriers remain excluded. Ordinary collection-array value copying, results and
generic GET_VAR/SET_VAR interfaces retain their existing restrictions.

PATH cells retain complete or partial node/header data, missing markers and
unknown BYTE values under their exact declared schemas. Queue cells retain
initialized state, ordered sequence/value entries and last sequence counters.
Queue backing buffer links are omitted. Old archives that list collection roots
as excluded keep those roots unchanged when loaded.

## Identity and clearing

Loading existing storage preserves the original ARRAY containers, owned PATH or
queue objects, and compatible PATH header containers. Captured cell/header
aliases continue to refer to that storage. New node lists detach old node/list
aliases, matching scalar PATH archive behavior. Queue loads and clears remove
runtime buffer links; later queue operations require an explicit compatible
INTEGER buffer. Buffer contents change only if their own saved roots are loaded.

CLEAR retains declarations, metadata, array cells and compatible headers. PATH
nodes become empty and headers regain ordinary missing/unknown initial values;
queues regain their uninitialized empty state. Newly loaded namespaces own
independent decoded arrays and cells. Decoded ARRAY carriers allocate only those
restored cells, with no discarded constructor-created collections or placeholder
root resource bank.

## Preflight and publication

Validate concrete hierarchy and combined contents before typed decode. The
snapshot bound is 32,767 units across roots: one descriptor per collection cell,
PATH header/node scalar leaves, and two scalar units per queue entry. Missing
containers retain their declared width. Creation reservation remains a separate
quota. Existing 64-level data-schema and 32-level JSON nesting, byte, namespace,
graph and backend limits still apply.

Owned cells must be distinct. Shared ARRAY containers, collection objects,
headers or node storage across cells fail before publication. Status/descendant
overlap, connected timers, foreign active/paused aliases, protection and creation
metadata guards retain their existing batch semantics. Every selected namespace
is prepared before any variable, graph or metadata update. Backend capacity and
busy/protection checks precede file publication; host files are not discovered.

DRAM is an explicit logical snapshot service. SAVE_DRAM and serialized flash
snapshots do not install an automatic power-up hook. A host calls
bank.restore_dram(program._state, name) explicitly. JSON/VR never persist live
views, aliases, queue buffers, callbacks, open descriptors or suspended execution.

## Examples and verification

- [PATH array save/clear/load](../examples/collection_archive_paths.kl)
- [Queue bank and buffer restore](../examples/collection_archive_queues.kl)
- [Named nested PATH arrays](../examples/collection_archive_nested.kl)
- [Queue bank DRAM snapshot](../examples/collection_archive_dram.kl)
- [Linked PATH archive](../examples/collection_archive_path_project/main.kl)
- [Linked queue archive](../examples/collection_archive_queue_project/main.kl)

Each example has independent state, full selected typed-variable expectations
and archive/file service fixtures. DONE guards preserve completed state during
CLI JSON replay. Routine-local status outputs avoid overlapping restored globals.

```console
python -m karel2py examples/collection_archive_paths.kl -o archive.py
python archive.py --context examples/collection_archive_paths.services.initial.json --state-out state.json
python archive.py --context state.json
```

The [authored tests](../tests/test_collection_array_archives.py) cover identity,
aliases, partial data, malformed payloads, resource allocation, quota preflight,
dynamic metadata, timers, paused owners, recursive/mixed batches and CLI-compatible
saved data. Reports expose collection_array_archive_policy; the
[semantic ledger](semantics/collection_array_archive_semantics.json) records the
same offline scope. No native compiler, robot or controller acceptance is claimed.
