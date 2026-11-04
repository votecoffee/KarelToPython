# PATH and QUEUE_TYPE arrays

[Owned PATH counters](path-for-counters.md) now support integral header/node/bank
leaves under complete-root and retained-alias proof. PATH node USING captures
retain the selected node object across later deletion or replacement.

[PATH-bank I/O](path-array-io.md) extends these scalar transports to whole PATH
arrays and selected rows/planes, retaining existing supplied headers/nodes and
normal capture, format and operation bounds. [Queue I/O](queue-io.md) now adds
initialized entry-value streams; FILE banks remain excluded.

Pythonic mode supports owned logical ARRAYs of PATH and QUEUE_TYPE. Each cell
owns an independent logical collection. Use existing PATH/queue operations on a
selected cell, or borrow the complete ARRAY through a routine or BYNAME argument.
This is an authored Pythonic extension, with no native source/layout claim.

```karel
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t
VAR routes:ARRAY[2]OF route_t status:INTEGER
BEGIN
  APPEND_NODE(routes[2],status)
  routes[2][1].amount=17
END
```

## Types and references

Global and local declarations, transparent collection aliases, named ARRAY types,
named nested components and supplied global wildcard shapes use the existing
ARRAY contracts. Logical ARRAY rank stays at one through three. Custom PATH
nodes/headers remain named resource-free data STRUCTUREs with concrete shapes.
A fresh PATH has empty nodes and its own declared header; a fresh queue is
uninitialized, with no entries, sequence or backing buffer.

Complete ARRAY coordinates may be followed by one PATH node selector. For example,
`routes[row][node].amount` and `routes[row,node].amount` select the same cell and
node for a one-dimensional ARRAY. The node index is separate from ARRAY rank;
a three-dimensional ARRAY can therefore have four coordinates including its node.
Capture all selector expressions once, left-to-right, then validate the declared
containers, coordinates and selected node. Missing nodes are not allocated by a
selector. Earlier selector effects remain if a later check fails.

Exact and generic borrowed ARRAY formals retain live storage. A complete named
subarray boundary can also be borrowed. Individual collection cells and PATH
node records/fields retain their existing interfaces, including checked static
BYNAME paths and scalar GET_VAR/SET_VAR transfers. Borrowed references survive
ordinary calls, rename and pause/resume. Linked source declarations still require
matching types and identities.

[Explicit BYNAME resource prefixes](resource-prefix-references.md) now borrow flat
rows/planes with original collection identities, including PATH node/header
access and queue backing buffers. Entry-output overlap checks include selected
PATH descendants and borrowed queue backing cells.

[Logical source values](collection-source-values.md) now support whole ARRAY
assignment, private grouped/computed arguments, function results and independent
row/plane values. [PATH-bank I/O](path-array-io.md) and [queue I/O](queue-io.md)
provide whole-bank and selected row/plane scalar transports. Whole collection
ARRAY UNINIT remains unavailable.
[Explicit logical GET_VAR/SET_VAR copies](collection-array-transfers.md) now support
whole banks and selected rows/planes with exact schemas. Source resource fields in
STRUCTUREs remain blocked. Individual PATH copies retain their existing logical
copy rules; [scalar queue source values](scalar-collection-values.md) now copy
logical entries and detach buffer links. Direct POSITION orientation and
resource-root FOR protection retain their documented rules.

## Dynamic creation and allocation

CREATE_VAR accepts `ARRAY OF PATH`, `ARRAY OF QUEUE_TYPE`, supplied collection
aliases with dimensions, and named ARRAY types with optional outer dimensions.
The existing inner/middle/outer dimension order applies. ARRAY OF spelling needs
positive dimensions; a named ARRAY type can supply its own shape. Explicit type
owners, name/collision rules, pool/group metadata and creation statuses remain.

The shared creation budget is 32767 reserved units. Each collection cell costs
one descriptor; a PATH also reserves its immediately allocated header leaves.
Validate node prototypes separately; nodes and queue entries grow later through
ordinary operations. Validate schema and quota before allocation, then recheck
the bank, collisions, capacity and terminal lifetime after the creation checkpoint.
These are portable allocation units, not native bytes or a Python heap estimate.

## Context JSON

Saved-variable rows use the resolved ARRAY schema and canonical nested lists.
PATH cells retain nodes, headers and partial/missing data. Queue cells retain
initialized state, ordered sequence/value pairs and the last sequence counter.
Queue backing buffers and live aliases are not saved. Restore creates independent
collection objects; an initialized restored queue binds a compatible explicit
INTEGER buffer when its next operation requires one.

Before allocating a restored root ARRAY, validate schema, hierarchy and combined
contents. The snapshot limit is 32767 units: descriptors, PATH header/node scalar
leaves and two scalar units per queue entry. This differs from the creation budget,
which reserves no future nodes/entries. Oversized snapshots fail before expanding
payloads or allocating restored root arrays. Existing creation metadata/quota checks
also apply before decoding creation-tagged rows. There is no inferred legacy flat
multidimensional collection representation.

[Logical VR archives](collection-array-archives.md) now include owned static and
created collection ARRAY roots in save/load/clear, recursive/mixed batches and
explicit DRAM snapshots. Exact existing array/cell/header identities survive;
node lists detach and queue links reset. JSON/VR are value replay and do not
persist callbacks, queue buffer links, captured aliases or task stacks.

Reports add `collection_array_policy`. See the [PATH](../examples/collection_path_arrays.kl),
[queue](../examples/collection_queue_arrays.kl),
[created PATH](../examples/dynamic_path_array_values.kl),
[created queue](../examples/dynamic_queue_array_values.kl),
[borrowed project](../examples/collection_array_project/main.kl),
[foreign type owner](../examples/dynamic_collection_array_project/main.kl),
[static/reference/codec tests](../tests/test_collection_arrays.py),
[dynamic tests](../tests/test_dynamic_collection_arrays.py) and
[semantic ledger](semantics/collection_array_semantics.json).

The example runner accepts optional `*.variables.expected.json` and project
`variables.expected.json` fixtures. Each is a nonempty list of selected complete
saved-variable rows, uniquely keyed by program/path. It compares each row exactly,
including type, logical value and any creation metadata, independently of the
ordinary Program snapshot. Strict mode remains future work.
