# Whole data aggregate WRITE

Pythonic WRITE accepts complete ARRAY, user STRUCTURE, VECTOR, CONFIG,
Cartesian/POSITION and JOINTPOS values. This is an authored source extension
through existing scalar output transports, without native aggregate WRITE,
packed record, geometry or controller-runtime acceptance claims. Strict mode
remains a future milestone.

```karel
PROGRAM aggregate_output
TYPE packet_t=STRUCTURE values:ARRAY[2]OF INTEGER label:STRING[4] ENDSTRUCTURE
VAR packet:packet_t
BEGIN
  packet.values[1]=7 packet.values[2]=9 packet.label='text'
  WRITE('packet=',packet,CR)
END aggregate_output
```

The statement produces one text request containing `packet= 7 9text` followed by
LF. No separator is added between expanded fields. Scalar defaults supply the
ordinary leading blank for numbers and BOOLEANs; STRING contents remain raw.
See the [record example](../examples/aggregate_write_values.kl).

## Capture, order and limits

ARRAY cells expand in physical row-major order, recursively through named
components. Records expand in declared field order; joints expand in axis order.
A POSITION's record order is NORMAL, ORIENT, APPROACH, LOCATION and CONFIG_DATA.
These are readable data components: no position conversion, matrix correction,
robot-model call or native association layout is inferred. Input orientation
write restrictions remain unchanged.

Each source expression is evaluated once, checked, detached and rendered before
later values or format expressions run. A later source routine can change the
original value without changing already rendered fields. Function results,
computed values, generic ARRAY formals and linked reference formals use the same
rules. The source and its captured aliases are not modified by rendering.

An aggregate item uses defaults or [uniform scalar formats](aggregate-formats.md).
Detach complete source values before evaluating format functions once, then apply
the controls to every scalar kind. Select individual fields for different
formats. Mixed scalar/aggregate/CR statements retain scalar format order and
existing source effects. After all rendering,
one complete recorder/callback request or FILE write is published. A late invalid
item or combined-limit failure publishes no outer output; earlier source effects
and nested WRITE requests remain visible. Failed callbacks are recorded once and
are not retried. Pause in a later expression retains earlier rendered fields.

Each source schema is bounded to 64 levels and 1024 scalar leaves. The complete
statement is bounded to 1024 expanded scalar items including empty STRINGs and
CR. Omitted-file output retains its 254-character limit. FILE output uses its
existing backend capacity, so a bounded aggregate can produce longer FILE text.

## Complete values and boundaries

All source leaves must be initialized and known, including BYTE contents, CONFIG
flags/turns, joint axes and nested fields. No missing/unknown placeholder is
printed. SHORT's uninitialized marker is not output as 32767. Known values,
nominal schemas, dimensions, ASCII STRING capacity, numeric finiteness and CONFIG
turn ranges are checked before output. A missing container or malformed data
rejects before publication. Resource roots and embedded resources remain excluded.

POSITION is supported as readable output data, including its orientation columns;
this does not make those columns writable or certify a proper geometric frame.
Native record formats, compact CONFIGs, inferred groups and physical axes remain
unavailable. Generic service outputs and public strict mode are unchanged.

## FILE and binary behavior

Existing memory/rooted/device files, configured serial/pipe outputs and headless
window sinks receive the same rendered batch. No device or GUI is opened. Text
output retains existing EOL mapping and scalar defaults. See the
[text FILE](../examples/aggregate_write_text.kl) and
[serial outbox](../examples/aggregate_write_serial.kl) examples.

Binary output consists of existing separate scalar fields in declaration/row-major
order, with ordinary BYTE/SHORT/INTEGER/REAL/BOOLEAN widths and selected byte order.
A STRING leaf defaults to its declared capacity, padded with NUL bytes when shorter.
An explicit width overrides that capacity under ordinary scalar binary rules.
Ordinary binary READ retains that padding in the returned STRING; it is not
silently trimmed. Fully occupied STRING fields and numeric data can roundtrip
through [whole-data READ](aggregate-input.md). See the
[binary roundtrip](../examples/aggregate_write_binary.kl).

No alignment, native ABI, portable-value archive envelope or packed controller
record is synthesized. Validation/rendering failures leave the FILE data/cursor
and previous status untouched before backend invocation. Backend failures retain
the backend's existing rules; arbitrary external callback effects have no rollback.
These writes are atomic modeled operations, not pending native WRITE cancellation.

## Reports and compatibility

The compiler's `aggregate_write_policy` records capture, defaults, bounds and
evidence boundaries. Aggregate `writes[].items[]` include type metadata and the
scalar order; `data_items` counts source items. Existing runtime output records
remain defensive text/line/outcome copies, without aggregate objects or callbacks.
Completed source data and backend state use existing context JSON.

Scalar-only generation remains on its existing path. The
[linked FILE](../examples/aggregate_write_project/main.kl) and
[linked serial](../examples/aggregate_write_serial_project/main.kl) projects
exercise shared context and generic formals. See the
[semantic ledger](semantics/aggregate_write_semantics.json) for authored verification.
