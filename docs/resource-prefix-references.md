# Live resource ARRAY rows and planes

Pythonic BYNAME can borrow an existing FILE, PATH or QUEUE_TYPE ARRAY row/plane
for a typed user routine. This is an authored offline reference extension.
The capture retains original resource cells and creates no replacement resource
objects. Source compiler, native ABI, hardware and controller equivalence remain
separate; strict mode is future work.

```karel
VAR streams:ARRAY[2,2]OF FILE entry:INTEGER
ROUTINE write_row(row:ARRAY OF FILE)
BEGIN
  OPEN FILE row[1] ('WO','out')
  WRITE row[1] (17)
  CLOSE FILE row[1]
END write_row
-- Inside BEGIN, with an explicit files backend:
write_row(BYNAME('','STREAMS[2]',entry))
```

## Selection, types and ownership

A final incomplete flat coordinate selection captures the concrete remaining
row/plane dimensions. Adjacent numeric brackets and comma coordinates use the
same static-path lookup. The suffix has anonymous outer identity; any named
inner ARRAY components and FILE/PATH/queue schemas remain exact. Generic formals
inherit actual sizes. No cast, resize or inferred backend is introduced.

Lookup retains explicit binding precedence, attached-program roots, dynamic
variables and calling-root defaults for a blank program name. Routine-local
and system discovery remain excluded. Ordinary bare resource-prefix values,
grouped copies, whole resource ARRAY assignments, results, READ/WRITE/UNINIT and
generic data transfers remain unavailable. Explicit [logical collection ARRAY
transfers](collection-array-transfers.md) now copy PATH/queue banks and selected
rows/planes under a separate value contract. Complete named-component borrowing
keeps its existing separate identity rules.

Before publishing the BYNAME entry/cache output, validate the entire containing
resource ARRAY's schema, physical shape, original storage and logical contents.
Distinct cells must own distinct resource objects. Selected coordinates capture
original contiguous cells once. Later argument effects, dynamic rename and
cooperative pause do not repeat lookup. Replacing a host root storage list does
not redirect the capture. Resizing its retained list fails on later view access.

The view uses an exact ARRAY carrier over checked original cells. Borrowing
allocates no FILE, PATH or QUEUE_TYPE descriptors. Forwarding the formal, or an
individual resource cell, retains ordinary reference semantics. PATH cell copies
still use the existing individual-PATH copy/detached-alias rules; borrowing itself
copies no collection state.

## FILE and collection operations

Selected FILEs keep their descriptor, backend, cursor, attributes and pending
operation. An already open descriptor can be borrowed. Text/binary I/O, explicit
CLOSE and CANCEL FILE reuse their existing transport and output rules. A waiting
read survives pause/resume; cancellation preserves unpublished input/output and
releases the pending read. Stop does not implicitly close every open descriptor.

PATH nodes and headers remain accessible through the borrowed row/plane, with
one node index after complete remaining ARRAY coordinates. Existing nodes are
required for indexed access. APPEND_NODE and ordinary collection operations
mutate original cells; capture allocates no nodes. Partial node/header data
retains its known/missing contents.

QUEUE_TYPE keeps its initialized state, ordered entries, sequence and original
backing INTEGER ARRAY. INIT/APPEND/GET and other existing queue operations use
that same resource. Borrowing neither rebinds nor serializes the buffer link.

BYNAME entry outputs must be disjoint from borrowed storage. This includes PATH
header/node descendants and backing cells of selected queues. The queue-buffer
guard also applies to other BYNAME references to those queues; ordinary queue
procedures still accept their explicit backing buffer. A disjoint unselected
row/buffer remains eligible as an entry output. Failure publishes no cache ID or
entry value. Existing FOR/resource-root and exact linked-interface guards remain.

## Bounds, persistence and verification

Logical ARRAY rank remains one through three. The containing resource schema
must fit 32,767 descriptor/header reservation units. Its combined current
contents must fit 32,767 units: descriptors, PATH header/node scalar leaves and
two units per queue entry. Data component schemas retain the existing 64-level
bound. These are portable prototype units, not native bytes or heap estimates.

Save the original roots using existing policies: static FILE arrays are omitted,
created FILE arrays require closed descriptors and retain allocation markers,
and collection arrays retain logical values. Fresh restores own new independent
resources. Views, suspended frames, open FILE state and queue backing links are
not serialized. Generic resource-array codecs do not accept the live view.

The [authored tests](../tests/test_resource_prefix_references.py) cover rows,
planes, named components, forwarding, live FILE input/cancellation, PATH nodes,
queue buffers, dynamic allocation/rename, linked calls, malformed storage,
entry overlap, quota checks and JSON behavior. Four runnable examples and two
linked projects have independent snapshots, saved-variable rows and optional
service-state expectations.

The FILE examples reopen their selected streams on replay so fresh static
descriptors reproduce their observations. Collection examples use DONE guards
to retain completed logical data without repeating mutations.

```console
python -m karel2py examples/resource_file_row.kl -o streams.py
python streams.py --context examples/resource_file_row.services.initial.json --state-out state.json
python streams.py --context state.json
```

No native controller or strict-mode validation is claimed.
