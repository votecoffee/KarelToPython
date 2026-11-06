# Whole-PATH I/O and FILE initialization queries

[PATH-bank I/O](path-array-io.md) extends these scalar transports to whole PATH
arrays and selected rows/planes, retaining existing supplied headers/nodes and
normal capture, format and operation bounds. [Queue I/O](queue-io.md) now adds
initialized entry-value streams; FILE banks remain excluded.

Pythonic mode supports whole-PATH WRITE, in-place whole-PATH READ and UNINIT on
ordinary FILE descriptors. PATH I/O is an authored portable extension built on
existing scalar transports. It does not encode or infer a native PATH record.
FILE queries use the existing offline open-state convention.

## PATH scalar order and capture

```karel
TYPE node_t=STRUCTURE value:INTEGER ENDSTRUCTURE
     header_t=STRUCTURE count:INTEGER ENDSTRUCTURE
VAR route:PATH NODEDATA=node_t PATHHEADER=header_t
    status:INTEGER
BEGIN
  INSERT_NODE(route,1,status) INSERT_NODE(route,2,status)
  route.count=2 route[1].value=7 route[2].value=9
  WRITE(route,CR)
  READ(route)
```

The WRITE records ` 2 7 9` and a newline. READ expects three scalar values:
header COUNT, node 1 VALUE and node 2 VALUE. It keeps the existing two nodes.
Header fields are ordinary user data; changing COUNT does not change PATH length.

Whole-PATH I/O expands the optional header first, followed by existing nodes in
node order. Components use declaration order, ARRAY row-major order and joint
axis order. Default STD_PTH_NODE data and explicit NODEDATA/PATHHEADER schemas
retain their existing concrete types. [Whole POSITION input](position-input.md)
now validates complete position cohorts, including default NODE_POS fields.
Explicit XYZWPR,
XYZWPREXT, CONFIG, VECTOR and joint data can follow their normal scalar input
rules.

The complete PATH schema, ordinary container identities and known component data
are checked before format expressions or transport. Components retain the
existing 64-level data-schema bound. The combined operation allows at most 1024
expanded scalar fields including CR; PATH's existing node bound still applies.
Nested resources, malformed schemas, substitute PATH subclasses and wrong
header/node storage are rejected.

WRITE captures independent complete scalar values before format expressions.
Missing or unknown data prevents outer output, while earlier completed source
effects remain. READ captures original leaf cells before formats and later
selectors. Missing scalar leaves are allowed, but shaped header/node/ARRAY/record
containers must exist. Deleting or replacing PATH nodes after capture does not
retarget those original cells. Existing scalar response validation and publication
rules continue to apply.

## Formats, empty paths and FILEs

One uniform format list is evaluated once and interpreted for each scalar kind.
Literal controls must fit every represented kind. Dynamic controls are checked
before input or output publication. This reuses the
[aggregate format rules](aggregate-formats.md).

A header-only PATH can be read or written. READ requires at least an existing
header or node and never allocates nodes from input. An empty headerless PATH has
no input fields and is rejected before consuming input. Unformatted WRITE of an
empty PATH produces one empty item, like an empty STRING. It still participates
in ordinary WRITE recording, FILE-open checks and item limits. Formatted empty
PATH output is rejected.

Omitted-file READ uses the existing typed callback, JSON values or TextInput
adapter. Explicit FILE operations use the existing text, binary and cooperative
transport paths, including cursor/status, rollback, pause and cancellation rules.
No length, type tag, node count or new separator is inserted into the payload.
Use explicit widths/separators when textual fields would otherwise be ambiguous.

Binary fields retain their separate scalar encodings, selected byte order and
STRING capacities. A writer and reader need matching supplied schemas and node
counts; this is not a self-describing or native PATH file format. The
[binary example](../examples/whole_path_binary.kl) writes a header INTEGER and two
node INTEGERs as twelve portable bytes, then reads them into an existing PATH.
The [input example](../examples/whole_path_read.kl) demonstrates that a header
COUNT value of three leaves the supplied two-node PATH unchanged.

Linked source routines keep their existing exact PATH/FILE parameter contracts.
A borrowed PATH READ updates caller cells; output uses a private value capture.
Context JSON continues to save ordinary PATH data through the existing typed
collection codec. Capture objects, live input operations and FILE handles are
not added to that codec.

## FILE initialization queries

```karel
before=UNINIT(stream)
OPEN FILE stream('WO','output')
during=UNINIT(stream)
CLOSE FILE stream
after=UNINIT(stream)
```

With an initially closed descriptor, BEFORE and AFTER are TRUE and DURING is
FALSE. The query returns TRUE when the ordinary descriptor has no owner, matching
the offline FILE state used by VAR_INFO. It performs no backend I/O and leaves
name, cursor, status and attributes unchanged. CANCEL FILE retains the existing
ownership rules; canceling an operation without closing its descriptor leaves
that descriptor initialized.

FILE aliases and borrowed routine parameters observe the same descriptor.
Parenthesized queries remain storage queries. Exact descriptor type and Pythonic
mode are required; malformed host substitutions and subclasses are rejected.
The native initialization-bit representation is not claimed. Whole ARRAY, PATH,
and user STRUCTURE UNINIT exclusions remain, and BYTE queries remain
excluded even after a write.

## Reports and executable coverage

`path_io_policy` describes field order, capture, limits, formats, empty-path rules,
FILE query semantics and the offline boundaries. Existing writes/reads reports
identify PATH items and their header/node scalar ordering. Initialization-query
records identify FILE operands. Runtime observations stay in ordinary scalar
read/write records; no data-bearing native receipt is invented.

The authored examples are [output](../examples/whole_path_write.kl),
[input](../examples/whole_path_read.kl), [binary](../examples/whole_path_binary.kl)
and [FILE queries](../examples/file_uninit.kl). Linked
[PATH input](../examples/whole_path_project) and
[FILE query](../examples/file_uninit_project) projects include complete state and
service fixtures. CLI acceptance verifies saved-context replay and generated
execution without compiler imports. The FILE examples reopen and close their
descriptors on each run; their JSON snapshots do not restore live handles.

The [semantic contract](semantics/path_io_semantics.json) distinguishes these
Pythonic policies from native acceptance. Strict mode remains a future milestone.
