# Dynamic logical collections

Pythonic `CREATE_VAR` accepts root `PATH` and `QUEUE_TYPE` storage, plus resolved
transparent aliases supplied by translated source. This extends the existing
[dynamic variable contract](dynamic-variables.md) with ordinary offline collection
objects. It is an authored Pythonic extension; native resource allocation and
compiler/controller acceptance remain unverified.

```karel
VAR entry,status:INTEGER
ROUTINE prepare(queue:QUEUE_TYPE)
BEGIN
  INIT_QUEUE(queue)
END prepare
-- Inside the main BEGIN:
CREATE_VAR('CACHE','JOBS','','QUEUE_TYPE',0,0,0,0,status)
prepare(BYNAME('CACHE','JOBS',entry))
```

## Types and initial state

| Requested type | Initial storage |
| --- | --- |
| `PATH` | Empty nodes, portable STD_PTH_NODE schema, no header. |
| Supplied alias of PATH | Empty nodes, resolved NODEDATA/PATHHEADER layouts and a fresh, partially uninitialized header when declared. |
| `QUEUE_TYPE` or supplied alias | Uninitialized logical queue with zero sequence, no entries and no backing buffer. |

Custom PATH components must be named data STRUCTURE layouts with concrete shapes,
bounded STRING capacities and at most 64 data-schema levels. Each node/header
prototype retains the 32767-leaf bound. Embedded resources and additional
ARRAY dimensions around collection roots are rejected with existing
unsupported-type status 5. Type declarations are supplied explicitly; a custom
source declaration string or binary environment is not parsed from `type_name`.
[Root FILE descriptors](dynamic-files.md) use a separate closed-descriptor contract.

Group 0..32 and DRAM/CMOS intent remain metadata. A collection's group value does
not select a robot, pose frame, tool, axis model or physical mechanism. The same
name, collision, pool and namespace guards apply to data and collections.

## Reserved storage and publication

The combined creation budget remains 32767 reserved units across created roots.
Ordinary data costs its existing scalar-leaf count. A queue or root FILE costs one descriptor;
a PATH costs one descriptor plus its immediately allocated header leaves. Its
node prototype is checked separately before creation. Nodes and queue entries
grow only through the existing collection operations, with their existing limits;
they are not charged as preallocated nodes during CREATE_VAR. This is creation
accounting rather than a total Python-heap or native controller memory estimate.

Validate the complete requested schema and budget before allocation. After the
execution-budget checkpoint, reject a terminal ABORT or stopped owner, check that
the variable bank is still the same and
recheck root collisions and reserved capacity. A callback's completed writes stay
visible; the new root cannot overwrite its competing claim or overrun the updated
budget. A replaced bank raises before publication. Quota rejection retains status
6; other existing status rules remain. Account shared immutable schemas once per
pass, with a fresh accounting pass after a checkpoint and for each restored row.

## References, operations and lifetime

Pass the root through exact `BYNAME` routine formals to use ordinary PATH/QUEUE
procedures, including explicitly linked routines. PATH header/node data fields
also use existing GET_VAR/SET_VAR/static BYNAME paths, with ordinary type, missing,
read-only POSITION/CONFIG and joint-axis checks. Whole-PATH variable transfers
now use the [exact Pythonic copy extension](path-transfers.md). Logical queue
GET_VAR/SET_VAR transfers keep their existing
independent-copy rules and clear buffer links on publication.

Renaming a root or unattached namespace preserves live references, creation
policy and lookup entry hints. A captured resource remains usable through a
rename and pause/resume. ABORT/error cleanup retains completed collection edits.
The existing indirect FOR, overlap and alias checks remain in force.

VAR_INFO uses PATH code 31 and its existing missing-data policy. No QUEUE_TYPE
inspection code is invented: VAR_INFO retains unavailable-type status 4, while
unfiltered VAR_LIST still includes that root. A PATH code filter includes only
PATH roots.

## Saved state and archives

Context JSON keeps the existing typed `variables` rows, logical collection state
and `creation` metadata. Validate schemas and reserved capacity before decoding a
created row. Partial node/header data and exact nominal layouts survive replay.
A restored queue has no backing-buffer reference; its next ordinary operation
must supply a compatible explicit INTEGER buffer. Live buffer/field aliases,
callbacks, suspended stacks and executable type declarations are not saved.

Portable variable archives already support logical queues. Created queue policy
now follows their existing save/clear/load and restore guards. PATH roots retain
the archive's explicit exclusion; use context JSON to retain their contents.
Reattach source layouts for later custom-type creation or linked calls.

Reports add `dynamic_collection_policy`, and `dynamic_variable_policy` links the
extension. See the [queue example](../examples/dynamic_queue_values.kl),
[custom path](../examples/dynamic_path_values.kl),
[rename example](../examples/dynamic_collection_rename.kl),
[queue archive](../examples/dynamic_queue_archive.kl),
[linked path](../examples/dynamic_path_project/main.kl),
[linked queue](../examples/dynamic_queue_project/main.kl),
[regressions](../tests/test_dynamic_collections.py) and
[semantic ledger](semantics/dynamic_collection_semantics.json).
Public strict mode remains future work.
