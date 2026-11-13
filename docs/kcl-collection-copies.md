# KCL logical collection copies

Pythonic KCL variable commands now copy exact logical PATH and QUEUE_TYPE values
to independent explicit storage. Enable `kcl.variable_commands` in the execution
context. Supplied scripted replies still take precedence. These are offline data
operations; they do not invoke a controller command interpreter.

```text
SET VAR [CACHE]ROUTE = [MAIN]SOURCE
SET VARIABLE [CACHE]QUEUES = [MAIN]QUEUES
SET VAR [CACHE]ROUTES[2,1] = [CACHE]ROUTES[1][2]
```

## Values and selection

Both sides must have identical concrete schemas, including node/header layouts,
ARRAY names, dimensions and named components. Supported values are scalar PATHs,
queues, whole banks, complete indexed collection cells and complete named ARRAY
components. Adjacent static index groups normalize as usual. Unqualified source
names use the destination namespace; explicit `[program]` names can read supplied
compiled modules or other explicit namespaces. The receiver must be detached
storage, including a valid dynamically created root.

PATH partial scalar data, missing nodes/header data and unknown BYTE markers use
the existing [logical collection policy](scalar-collection-values.md). An empty
headerless PATH is valid; a missing whole PATH object is invalid storage. A queue
can be initialized or uninitialized. Queue entries and the sequence counter copy,
while backing buffer links never copy. Ordinary data ARRAY/record KCL copies
continue to require complete initialized leaves.

## Admission and publication

Count each selection before encoding or copying payloads. Each source and
receiver fits 32,767 units: one per collection descriptor, one per PATH header/node
scalar, and two per queue entry (sequence and value). Data schemas retain the
64-level bound and ARRAY rank remains at most three.

Charge one execution step per unit in both selections, then recheck the original
receiver reference location, variable store, selected parent/cell, whole-root
ownership, program protection, aliases and connected timers. Re-resolve the source
after the last charge. Its current value can change, including a replacement
binding, provided its exact schema and admitted unit count still match. A changed
source or receiver count rejects before snapshot allocation. Earlier host or
checkpoint effects remain visible.

Validate the complete current source and receiver before publication, with no
further checkpoints. Malformed known data, nonfinite numbers, overlong STRINGs,
invalid queue IDs, overlapping owned collection cells or invalid containers fail
without partial writes. Valid PATH data may still contain explicit missing markers.

Publication retains receiver ARRAY containers and collection objects. Compatible
PATH header storage stays live; new independent nodes replace the old list.
Previously captured old node references remain detached. Copied queues retain
their receiver objects and lose their old buffer link. Source and unselected
receiver buffer links/data remain unchanged. Self-copy follows the same rules.

| Status | Portable result |
| --- | --- |
| 0 | Logical value copied, including valid partial PATH or uninitialized queue state |
| 204 | Receiver changed or became protected during preparation |
| 205 | Missing/incompatible source, invalid data/layout, changed admitted count, or excessive logical size |
| 4 | Execution budget or command execution failed |

Existing missing-target and syntax statuses remain in force. `KCL_NO_WAIT` still
separates acceptance from the final `KCL_STATUS` result. No variable-cache entry
is allocated by a copy.

## Boundaries and replay

Incomplete flat collection rows/planes, paused-local collection roots, FILE
values/banks, resource STRUCTURE fields, aggregate literals, conversions and
reshaping remain outside this command contract. Complete named ARRAY components
are supported. [Ordinary data prefixes](kcl-data-prefixes.md) and paused-local
data edits keep their separate ownership and initialization rules.

Closed context JSON retains the copied values, creation metadata, queue sequence
and command history. It omits queue buffers, live aliases and suspended execution.
The [standalone example](../examples/kcl_logical_copy.kl) copies a path, queue and
bank, changes the originals and reads back independent values. The
[linked example](../examples/kcl_logical_copy_project/main.kl) issues a library
command against a compiled source and dynamically created detached destination.
Both use DONE guards for exact saved-context replay.

Translation reports expose `kcl_collection_copy_policy`. The
[semantic ledger](semantics/kcl_collection_copy_semantics.json) and
[authored regressions](../tests/test_kcl_collection_copies.py) record the offline
contract. Native KCL statuses, controller behavior and strict mode remain unverified.
