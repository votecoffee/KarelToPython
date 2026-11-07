# PATH-bank READ and WRITE

Pythonic READ and WRITE accept whole ARRAYs ending in PATH, named components and
selected rows/planes. This extends [scalar PATH I/O](path-io-and-file-initialization.md)
using supplied storage and ordinary scalar transports. It is an authored offline
extension without native compiler, controller, packed-layout or strict equivalence.

```karel
TYPE node_t=STRUCTURE value:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t
VAR routes:ARRAY[2]OF route_t status:INTEGER
BEGIN
  APPEND_NODE(routes[2],status)
  routes[2][1].value=17
  WRITE(routes::4,CR)
  READ(routes)
END
```

Output contains the supplied value 17 in a four-character field followed by LF.
The empty first PATH contributes no fields. Input expects one INTEGER for the
existing second node; it neither appends nodes nor infers a PATH shape from input.

## Order, capture and bounds

Expand ARRAY cells in row-major order. For each PATH, expand its optional header
then existing nodes; component fields use declaration, row-major ARRAY and joint
axis order. No type tags, lengths, separators or node counts are inserted. Changing
a user header count never changes the number of nodes.

Validate the entire selected bank, concrete schemas, ordinary owned cells and
known logical contents before format expressions or transport. WRITE captures
complete immutable scalar values. READ captures original writable leaf cells;
missing scalar values are permitted, but missing shaped containers are rejected.
The execution budget charges one step per PATH cell and scalar field before
payload validation. The bank checks that the selected cells, headers and node
lists stayed in place during that charge. Later selectors or format routines
may delete or replace nodes or bank cells without
retargeting captured input. Earlier explicit source/format effects remain visible
when a later validation fails.

Banks retain one through three logical dimensions, 32,767 collection snapshot
units and the existing 64-level data-schema bound. Each operation admits at most
1,024 expanded scalar fields including CR markers. Combined source items also
share ordinary output size/backend limits. A flat row or plane selection also charges and validates the containing bank
before selecting cells. WRITE uses the checked row or plane view for its
immediate scalar snapshot. Ordinary PATH array prefix values remain independent.

Header-only PATHs contribute their header fields. Empty headerless cells contribute
none. All-empty unformatted WRITE produces one empty item and still checks FILE
open state; formatted all-empty WRITE and all-empty READ reject. Mixed banks can
use uniform formats on their nonempty cells. See [aggregate formats](aggregate-formats.md)
for the scalar domains; each format expression is evaluated once per source item.

## Transports and interfaces

Default callback/JSON/TextInput input, explicit text and binary FILEs, selected
byte order, STRING widths and existing cooperative transports use their normal
rules. Invalid/truncated input preserves staged destination data and follows the
transport's cursor/status/rollback contract. Complete POSITION cohorts retain
geometry checks; direct orientation references remain protected. Cooperative
cancellation, pause/resume and stop retain or release the normal captured request.

Bare matching and explicit BYNAME formals borrow live banks. Grouped arguments,
computed results and ordinary output prefixes retain independent logical values.
READ prefixes capture original cells rather than a copied row. Static, explicitly
created and compiled linked storage share these contracts; linked signatures stay
exact. Input does not create nodes, resize banks or discover robot context.

[Queue entry I/O](queue-io.md) now adds initialized scalar queues and banks.
FILE banks, embedded resource fields, whole ARRAY/PATH UNINIT and
generic collection copy codecs retain their guards. Existing resource-root FOR
protection also remains. Typed JSON and logical VR/DRAM storage retain ordinary
collection data; input captures, live FILE handles and pending/suspended operations
are not persisted.

## Evidence

The report exposes `path_array_io_policy`, and READ/WRITE rows identify the ARRAY
and PATH scalar order. Authored fixtures cover output, supplied binary input,
binary roundtrip and selected-row I/O, plus compiled linked input and result output.
The [semantics ledger](semantics/path_array_io_semantics.json) records the offline
boundary separately from native acceptance.
