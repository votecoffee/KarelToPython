# Direct FILE ARRAY prefix arguments

Pythonic typed user routines now borrow an incomplete FILE ARRAY row or plane
through an ordinary ungrouped selector. The selected cells retain their exact
original descriptors. Borrowing creates no FILE objects or replacement resource
storage and requires no BYNAME namespace lookup.

```karel
VAR streams:ARRAY[2,2]OF FILE
ROUTINE write_row(row:ARRAY OF FILE)
BEGIN
  OPEN FILE row[1] ('WO','out')
  WRITE row[1] (17)
  CLOSE FILE row[1]
END write_row
-- Inside BEGIN, with an explicit files backend:
write_row(streams[2])
```

## Selection and interface rules

One or more incomplete flat coordinates select a concrete remaining row/plane.
Comma and adjacent bracket spellings share the existing normalized index path.
Indexes are checked INTEGER expressions and are evaluated once in ordinary
left-to-right argument order. Capture precedes later argument effects.

Generic rank-matched FILE ARRAY formals inherit actual dimensions. The suffix
has anonymous outer identity; exact named inner components remain. A suffix does
not acquire a named row type merely because sizes match. Fixed ARRAY formal
sizes, rank changes and incompatible terminal/resource types remain rejected.

Global and routine-local banks, named outer arrays and borrowed formals use the
same source form. A borrowed plane can pass one of its rows onward. Supplied
source linkage and explicit typed callbacks retain the same exact interfaces;
no binary ABI or automatic library discovery is inferred.

The existing resource-prefix helper validates the whole containing bank, physical
shape, component schemas and distinct descriptor ownership before exposing a
view. Unselected malformed cells also fail. The existing rank-three and
32767-descriptor bounds remain.

## Original resources and lifetimes

Opening, closing, reading, writing, status/cursor queries and attributes operate
on original cells. Repeated captures of the same row share descriptors; disjoint
rows keep distinct handles. Source scalar FILE arguments can borrow individual
cells from the view.

The capture retains its original list. Replacing a host ARRAY's storage does not
redirect a retained view. Resizing that original list fails on later view access.
Pause retains descriptors and pending input; cancellation preserves unpublished
input and releases only the pending READ. Stop retains the ordinary explicit-close
contract. Borrowing itself neither opens a backend nor creates a resource.

Direct selectors do not publish BYNAME cache IDs or entry outputs. BYNAME keeps
its own explicit lookup and overlap rules, including support for dynamic roots.
A BYNAME whole/plane formal can forward a direct row using its retained storage.
Existing call effects, active FOR checks, frame cleanup and backend guards remain.

## Value boundaries and saved data

| Source form | Ownership |
| --- | --- |
| work(files[2]) | Borrowed FILE row; edits/I/O affect original descriptors. |
| work((files[2])) | Rejected FILE value copy. |
| work(BYNAME('', 'FILES[2]', entry)) | Existing explicit live resource lookup. |
| work(data[2]) | Existing independent data row value. |
| work(paths[2]) / work(queues[2]) | Existing private collection row values. |
| ARRAY_LEN(files[2],dimension) | Reads the selected shape through a checked view. Dimension is optional and one-based. |

ARRAY_LEN uses the same index, schema and descriptor checks as borrowing a
routine argument. The selected shape is captured before the dimension
expression runs. The query can run with no FILE backend configured.

Whole FILE bank assignment, RETURN values, READ/WRITE/UNINIT, resource fields and
generic typed codecs remain excluded. This change does not introduce generic
service/scalar output-prefix syntax or FILE data transfers.

Save original roots under their existing policies: static FILE banks are omitted
from variable data, and created FILE banks require closed descriptors and save
allocation intent. Views, borrowed frames, live handles and pending operations
are not serialized. Restored banks own fresh resources; no live alias is restored.

Reports expose file_prefix_call_policy and file_prefix_arguments. Each capture
records body/routine/formal, source selector, container/suffix schemas, supplied
index count and physical source/include origin. These are translation records,
not evidence that a particular call executed.

This is an authored offline Pythonic extension. Native source acceptance, FILE
layout/ABI, hardware/controller timing and strict equivalence remain separate.
See the [ledger](semantics/direct_file_prefix_semantics.json),
[regressions](../tests/test_direct_file_prefixes.py), and authored
[row](../examples/direct_file_row.kl), [plane](../examples/direct_file_plane.kl),
[named-component](../examples/direct_file_components.kl),
[local-bank](../examples/direct_file_locals.kl),
[linked](../examples/direct_file_prefix_linked/main.kl) and
[forwarding](../examples/direct_file_prefix_forwarded/main.kl) examples.
