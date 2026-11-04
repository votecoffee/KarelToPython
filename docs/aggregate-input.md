# Whole data aggregate READ

[PATH-bank I/O](path-array-io.md) extends these scalar transports to whole PATH
arrays and selected rows/planes, retaining existing supplied headers/nodes and
normal capture, format and operation bounds. FILE/queue banks remain excluded.

Pythonic READ accepts whole ARRAYs, user STRUCTUREs, VECTORs, CONFIGs,
POSITION/XYZWPR/XYZWPREXT records and JOINTPOS values. This is an authored Pythonic
extension using the existing scalar input transports, without native aggregate
READ acceptance, packed record layouts or controller input claims. Strict mode
remains a future milestone.

```karel
PROGRAM aggregate_input
TYPE packet_t=STRUCTURE values:ARRAY[2]OF INTEGER label:STRING[4] ENDSTRUCTURE
VAR packet:packet_t
BEGIN
  READ(packet)
END aggregate_input
```

Supply `[7, 9, "hello"]` as the typed response batch. The ARRAY becomes `[7, 9]`
and LABEL becomes `hell` under its ordinary bounded STRING rule. Generated CLI
scripts use a JSON list of flat response batches with `--read-values`, or explicit
ASCII text with `--read-text`. See the [callback example](../examples/aggregate_read_values.kl).

## Ordering and source capture

Fields expand in declared field order. ARRAY physical cells expand in row-major
order, recursively through named ARRAY components and record elements. Joint
axes expand in axis order. CONFIG expands to its three INTEGER turns followed by
its four BOOLEAN flags, retaining the existing -8..7 turn bounds. Cartesian
records include their declared CONFIG and external-axis fields; no robot model,
pose conversion or axis units are inferred.

Each destination is captured once before the next destination and its format
expressions. Captured leaves keep their storage aliases through later selector
calls, source pause/resume and cooperative waits. Root and child containers are
retained. If a host callback replaces a root, the captured old fields remain the
selected destinations, like existing scalar field references.

Mix whole data with scalar destinations and CR. CR applies after the entire
preceding source item, and the runtime remaps it to the expanded scalar offset.
Repeated/overlapping aliases retain ordinary READ ordering: validate every
response first, then publish scalar values in expanded source order, with the
last value winning for a repeated cell. Aggregate items use defaults or
[uniform scalar formats](aggregate-formats.md). Capture all selected leaves before
format functions; evaluate each format once and validate it for every member.
Select individual fields when different controls are needed.

[Statement prefix targets](array-prefix-targets.md) also expand captured original
row/plane cells, retaining formats, source CR mapping and scalar input transports.
They do not read into temporary source-row copies.

## Shapes, bounds and validation

Destination schemas must be exact concrete resource-free data, with at most
64 schema levels and at most 1024 expanded scalar destinations plus CR markers
in the complete request. Generic source ARRAY formals inherit the caller's actual
shape. The ordinary scalar STRING, finite numeric and narrow-type rules apply.

Declared shaped containers with missing scalar leaves are accepted. A missing
whole container, including a missing nested ARRAY/record, is rejected before
input. Malformed schemas/shapes and invalid known existing aggregate values are
also rejected before the callback or FILE read. No container or robot defaults
are invented. Existing constants, FOR counters and readonly guards remain.
[Whole POSITION input](position-input.md) uses checked complete 19-field captures,
with geometry validation and bounded transport-roundoff normalization. Direct
orientation descendants remain readonly. [Root PATH input](path-io-and-file-initialization.md) now expands
its supplied header/nodes under an explicit in-place extension. FILE, QUEUE_TYPE
and embedded resources remain excluded.

The complete typed response is validated before any scalar destination is written,
including late CONFIG turn bounds. An invalid late value leaves earlier ordinary
and aggregate destinations unchanged. Earlier selector and explicit callback
effects remain visible. A callback/TextInput may have consumed its own input;
there is no arbitrary callback rewind.

## FILE transports and cancellation

Ordinary text/binary MemoryFiles, rooted DirectoryFiles, DeviceFiles, existing
finite transports and cooperative serial, pipe and injected keyboard FILE reads
receive the same flat scalar target list. Text parsing and CR use the existing
rules. Binary input uses separate scalar widths, STRING capacities and selected
byte order; it is not a native packed aggregate layout. See the
[text example](../examples/aggregate_read_text.kl),
[binary example](../examples/aggregate_read_binary.kl) and
[serial example](../examples/aggregate_read_serial.kl).

Successful FILE reads commit their existing cursor/status changes. A validation
failure retains the uncommitted cursor and destinations under the transport's
ordinary failure rules. Waiting reads retain captured leaves; CANCEL FILE leaves
uncompleted data/output untouched and returns status 6. Pause, stop, abort and
step-budget cleanup retain their existing precedence and operation ownership.
No keyboard/device connection or GUI is opened. See the
[linked read](../examples/aggregate_read_project/main.kl) and
[linked cancellation](../examples/aggregate_read_cancel_project/main.kl) examples.

## Metadata and compatibility

[Whole-data WRITE](aggregate-output.md) supplies the output counterpart through
default scalar fields. Binary STRING leaves occupy declared capacity; existing
binary READ retains their NUL padding. Native record layouts are not inferred.

The compiler's `aggregate_read_policy` describes ordering, limits and native
boundaries. Each aggregate destination in `reads` is marked with its scalar order.
Runtime READ observations and callback metadata remain ordinary flat type/format/CR
records, without supplied values. Whole CONFIG reads reuse bounded scalar field
references; generic service aliases and conversion outputs retain their restrictions.

Existing scalar-only generation and callback contracts remain unchanged. Completed
data uses ordinary context JSON; aliases, callbacks and pending READ stacks are
not saved. The [semantic ledger](semantics/aggregate_read_semantics.json) links the
authored verification separately from native evidence.
