# Typed service ARRAY rows and planes

Pythonic typed service arguments can now select a data ARRAY row or plane and
update its original cells. The service must declare an explicit supported ARRAY
kind. Existing whole-ARRAY calls retain their behavior. This is an authored
offline extension; strict mode and native source/ABI equivalence remain separate.

```karel
VAR names:ARRAY[2,3]OF STRING[20] count,status:INTEGER
-- Inside BEGIN, with an explicit files backend:
FILE_LIST('*',0,0,names[2],count,status)
```

## Supported interfaces

| Interfaces | Selected storage |
| --- | --- |
| APPEND/GET/INSERT/MODIFY/DELETE/COPY_QUEUE | INTEGER buffer or copy-output rows |
| FILE_LIST, PROG_LIST, VAR_LIST, VAR_INFO | STRING output rows; INTEGER dimension rows |
| READ_DICT/READ_DICT_V, XML_GETDATA | Typed STRING input/output rows |
| ADD_INTPC/ADD_REALPC/ADD_STRINGPC/ADD_BYNAMEPC, SEND_DATAPC | BYTE builder rows and detached typed/raw send snapshots |
| Forms and table controls | STRING values, COL_DESC_T columns, BOOLEAN flags and change planes, INTEGER pointer planes |
| INI_DYN_DISB | Static global STRING label row, retained for later refresh |
| JOINT2POS and related geometry inputs | REAL output rows and ordinary private input rows |
| Supplied vision/tracking results | Exact XYZWPR/REAL/INTEGER rows required by each signature |

The shared kinds are BYTE_ARRAY, PC_BUFFER, VT_INT32, INT_ARRAY, REAL_ARRAY,
STRING_ARRAY, BOOL_ARRAY, COL_ARRAY, BOOL_GRID, INT_GRID, TRACKING_POSITIONS,
TRACKING_MEASURES and XYZWPR_ARRAY. Existing signature-specific rank, element,
capacity and fixed-size checks still apply. A kind name does not relax a service's
input validation or make every ARRAY accepted by that service.

## Capture and ownership

Writable output/mutable arguments require direct ungrouped variable storage.
A final incomplete flat selection captures the remaining concrete dimensions;
named inner components keep their schemas and STRING capacities. Generic formals
inherit their actual storage dimensions. Chained numeric indexes use the same
normalization as comma indexes.

Evaluate the receiver and each index once, left to right in ordinary argument
order. Validate the entire containing data schema, physical storage and known
leaves before capturing original cells. A later selector or callback cannot
redirect the capture by replacing a root's storage list. Resizing the retained
list fails on later window access. There is no reference cast, reshape or copyback.

Repeated queue captures of the same cells retain backing identity. A queue can
retain a local buffer after the routine returns. Static display labels retain
selected global cells and observe subsequent edits; local/formal label roots
remain rejected. Pause/resume retains live in-memory captures.

Readonly nullable/value inputs, including SEND_DATAPC, detach typed snapshots
before later argument effects. Existing unknown BYTE/unused packet-tail rules
remain specific to typed versus raw send mode. Ordinary user-routine prefix
arguments still copy private data; explicit BYNAME borrowing follows its own
[data](array-prefix-references.md) and [resource](resource-prefix-references.md)
contracts.

## Validation, effects and saved state

Original-cell and descendant overlap checks remain active for outputs. Existing
FOR, CONFIG/association-field, POSITION orientation and exact linked-interface
checks still apply. Data schemas remain bounded to 32,767 scalar leaves, 64 levels
and at most three logical ARRAY dimensions. Invalid containing data fails before
later output selectors and service publication.

Each service retains its existing status, capacity, pagination, consumption and
partial-publication behavior. FILE_LIST preflights its page, while READ_DICT can
publish a bounded page with a nonzero continuation/status result. Selecting a row
does not introduce a blanket transaction guarantee for all service effects.

Save the original roots as ordinary typed data. JSON replay restores independent
plain storage and logical queue data, without live windows, new variable bindings,
queue backing links or suspended stacks. The examples use DONE guards to avoid
repeating completed mutations or outgoing messages on replay.

Generic ANY/scalar service outputs do not gain prefix references. Resource ARRAY
prefixes remain explicit BYNAME arguments; this change does not enable resource
value copying, implicit devices, discovery or native controller behavior.

## Examples and evidence

The [authored tests](../tests/test_service_array_prefixes.py) cover service families,
overlap, capture order, lifetime, malformed storage, private inputs, linked calls
and report metadata. Four examples and two linked projects have independent
snapshots and complete selected typed saved-variable expectations:

- [Queue buffers and copy outputs](../examples/service_queue_row.kl)
- [File listing row](../examples/service_file_row.kl)
- [Variable dimensions row](../examples/service_metadata_row.kl)
- [PC packet row](../examples/service_pc_row.kl)
- [Linked file listing](../examples/service_file_project/main.kl)
- [Linked queue buffer](../examples/service_queue_project/main.kl)

```console
python -m karel2py examples/service_file_row.kl -o listing.py
python listing.py --context examples/service_file_row.services.initial.json --state-out state.json
python listing.py --context state.json
```

Translation reports expose typed_service_array_prefix_policy. The
[semantic ledger](semantics/service_array_prefix_semantics.json) records the same
portable scope. Offline tests do not establish native compiler or controller
acceptance.
