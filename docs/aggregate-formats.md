# Uniform aggregate READ and WRITE formats

Pythonic whole-data READ and WRITE now accept the scalar `::width` and second
format expressions on aggregate items. Evaluate each format expression once,
then interpret that list separately for every expanded scalar field. This is an
authored extension, without native whole-aggregate formatting or packed-layout
acceptance claims. Strict mode remains a future milestone.

```karel
PROGRAM aggregate_formats
VAR values:ARRAY[2]OF INTEGER
BEGIN
  values[1]=10 values[2]=15
  WRITE(values::3::16,CR)
END aggregate_formats
```

This produces one request containing ` 0A 0F` followed by LF. A matching text
`READ(values::3::16,CR)` reads those fixed-width fields. Use default formats when
no specifiers are supplied. See [formatted output](../examples/aggregate_format_output.kl)
and [formatted input](../examples/aggregate_format_input.kl).

## Per-field interpretation

The existing [scalar READ](read-formats.md) and [scalar WRITE](text-formats.md)
format domains still apply. Record fields expand in declaration order, ARRAY
components in row-major order and joints in axis order. There is no new separator,
rank conversion or field-name inference.

| Scalar kind | READ | WRITE |
| --- | --- | --- |
| INTEGER/BYTE/SHORT | Width and base 0 or 2..16 | Minimum width and base 0 or 2..16 |
| REAL | Width; second expression evaluated and ignored | Minimum width; signed fixed/scientific precision |
| STRING | Width and quote mode 0/2 | Width and alignment/quote mode 0..3 |
| BOOLEAN | Width; second expression evaluated and ignored | Minimum width only |

A list must be valid for every member of a mixed aggregate. A record containing
BOOLEAN cannot use a second WRITE format. A mixed INTEGER/STRING record can use
second format 2: binary integer text and quoted STRING text follow their own
scalar meanings. A base of 16 on that same record rejects because it is not a
STRING mode. Static incompatibilities reject during translation; dynamic values
are checked before input or output publication.

READ and WRITE retain independent scalar domains. For example, an all-STRING
WRITE can use the large-width natural-size fallback; READ widths remain 0..254.
Numeric/BOOLEAN output widths are minimums, whereas positive READ widths select
exact input fields. Choose adequate widths rather than assuming every format
pair roundtrips. Individual fields can still have distinct formats in a list;
there is no separate field-to-format mapping syntax.

## Capture before format functions

WRITE first validates and detaches all complete scalar source values. It then
evaluates width and second format once, in that order, and renders using the
captured values. A format function that changes the original ARRAY or record
cannot change the current output. Missing/unknown/malformed source data rejects
before format functions run. Later expression and nested WRITE effects retain
the existing publication rules.

READ captures every selected leaf reference before evaluating formats. A format
function that changes an index or replaces the source root cannot retarget those
references. The normal captured-storage semantics still apply: old fields can
remain selected after a root is replaced. Formats are validated for each captured
scalar before input. Callback/JSON response batches remain flat, already decoded
values; formats are metadata rather than instructions to parse typed strings.

Pause/resume retains the captured fields/values and already evaluated formats.
Neither branch repeats selectors or format functions. Source effects completed
before a later failure remain visible. The compiler marks `capture_before_formats`
on aggregate READ destinations and WRITE items, with dynamic source locations.
Aggregate WRITE reports do not assign a single scalar alignment to mixed fields.

## FILEs and cooperative transports

Text, typed callbacks, TextInput and existing ordinary/cooperative FILE transports
use the same expanded scalar controls. CR is still remapped after whole source
items. Waiting serial, pipe and injected keyboard input retain captures through
waits and cancellation. The [linked text project](../examples/aggregate_format_project/main.kl)
and [linked cancellation project](../examples/aggregate_format_cancel_project/main.kl)
exercise those contracts.

Binary formats retain their scalar width-only restrictions; a second format
rejects rather than becoming a base/precision. Explicit uniform widths override
default binary STRING capacities and integral field widths. Truncation, NUL
padding and existing read padding retention remain unchanged. See the
[binary width example](../examples/aggregate_format_binary.kl). No native record
packing, alignment or ABI is inferred. A rejected binary READ retains all outputs
and the cursor; a rejected rendered WRITE publishes no file bytes before backend
invocation. Backend-specific failures retain existing rules.

## Limits and exclusions

The existing 64-level schemas, 1024 expanded scalar/CR items, omitted-file output
limit of 254 characters and FILE/backend bounds are unchanged. Missing input
containers, POSITION input/orientation writes, partial/unknown output and resource
input/output remain excluded. Formatting does not relax CONFIG turn domains,
exact schemas, protected outputs, active FOR guards or native/controller boundaries.

Unformatted generated code keeps its existing runtime entry points. Saved context
JSON remains data-only: no format captures, callbacks or paused stacks are stored.
`aggregate_format_policy` and the [semantic ledger](semantics/aggregate_format_semantics.json)
describe this extension and its authored verification.
