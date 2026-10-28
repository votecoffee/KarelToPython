# Offline dynamic displays

Twelve INI_DYN_DIS*/CNC_DYN_DIS* procedures watch static variables or supplied
ports and paint fields in existing logical windows. Configure both services:

```json
{"pendant":{"rows":24,"cols":80},"dynamic_display":{"quantum_ms":1}}
```

Host code can construct `rt.ExecutionContext(pendant=rt.PendantDisplay(...),
dynamic_display=rt.DynamicDisplays(...))`. No native display task, thread,
desktop window or controller connection is started. See
[pendant displays](pendant-display.md) for window definitions and attachments.

## Calls and binding identity

| Family | Initiation arguments before status | Value |
| --- | --- | --- |
| INI_DYN_DISB | variable, window, width, attributes, size, row, col, interval, labels | BOOLEAN selects labels[1] or labels[2]. |
| INI_DYN_DISE | variable, window, width, attributes, size, row, col, interval, labels | INTEGER n selects labels[n+1]. |
| INI_DYN_DISI | variable, window, width, attributes, size, row, col, interval, buffer_size, format | INTEGER numeric format. |
| INI_DYN_DISR | variable, window, width, attributes, size, row, col, interval, buffer_size, format | REAL numeric format. |
| INI_DYN_DISS | variable, window, width, attributes, size, row, col, interval, buffer_size, format | STRING format. |
| INI_DYN_DISP | port_type, port_no, window, width, attributes, size, row, col, interval, labels | Supplied BOOLEAN/INTEGER port selects labels. |

Every initiation ends with an ordinary writable INTEGER status. CNC_DYN_DISB,
CNC_DYN_DISE, CNC_DYN_DISI, CNC_DYN_DISR and CNC_DYN_DISS take variable, window,
status. CNC_DYN_DISP takes port_type, port_no, window, status.

Variables and label arrays must be static global storage. Supported selectors
include fields, indexed/grouped selections and captured USING fields. Array
indexes run once when a call captures the reference; later index changes do not
retarget an active watch. FROM globals retain their linked storage identity.
Routine locals/formals, constants, temporary values and computed scalar
expressions are rejected with E_STATIC_ARGUMENT. Scalar types must match the
family exactly; INTEGER references are not promoted to REAL references.

Read-only references permit uninitialized variables and observation of active
FOR counters. They do not create writes to those variables. Existing status
output, overlap, POSITION/CONFIG and active-counter protections remain. Protected
POSITION orientation fields may be observed as REAL inputs. The service never
writes a watched scalar or label ARRAY.

Cancellation matches family, captured storage identity and logical window,
including every location registered for that combination. Equal scalar values
in different variables do not match. Port cancellation also matches the bank and
resolved port kind/number. An explicit supplied port type_codes mapping is
required; it is not a native I/O type-code catalog.

## Text and fields

```karel
DEF_WINDOW('INFO',2,20,WD_COM_CURSR,status)
ATT_WINDOW_S('INFO','SYS',1,1,status)
count=7
INI_DYN_DISI(count,'INFO',6,0,0,1,1,1,0,'%d',status)
count=42
-- A subsequent source checkpoint samples the changed value.
CNC_DYN_DISI(count,'INFO',status)
```

Each field stays on one window row. Positive width truncates long text and pads
short text with spaces. Width zero clips to the available columns and writes
only current text, so shrinking text leaves old trailing cells. Cancellation
clears positive-width fields and retains width-zero text. Surviving overlapping
fields are restored in registration order from their last sampled text, without
bypassing their update intervals. Due fields paint in registration order.

BOOLEAN labels need at least two one-dimensional STRING cells. Enum labels use
zero-based values. Missing scalar/port/selected-label data displays stars; an
out-of-range enum displays question marks. Placeholder length is width or one
character for width zero. Other invalid data, including embedded control
characters, displays question marks rather than moving a cursor.

INTEGER formats support d/o/x/X/u; REAL supports f/e/E/g/G; STRING supports s.
Formats are exactly one percent conversion, optionally with bounded flags,
width and precision, without dictionary argument reordering or literal prefixes.
%% displays a percent. Width and precision are at most 254. Formatting uses the
[Pythonic dictionary numeric conventions](text-dictionaries.md), including low
32-bit unsigned integers. Host polling uses the same Pythonic numeric context.
The buffer_size argument is retained as metadata and allocates no buffer,
matching the documented unimplemented parameter.

Attribute masks 0..15 and character sizes 0/2 are accepted intent. The grid keeps
normal one-cell ASCII characters; native bold, colors, underline, reverse video
and double-size glyph rendering are not applied.

A paint batch validates all field locations/text before replacing any grid data.
It does not move ordinary FILE cursors, change FILE positions or open a hidden
FILE handle. Accepted batches add DYNAMIC_WRITE pendant history rows with field
and character counts. History names the task triggering the paint; binding
metadata separately retains the registering module and root owner.

## Clock, inspection and lifetime

The clock is deterministic logical milliseconds. While bindings are active,
each leaf source/call-entry checkpoint advances quantum_ms (default 1). Parent
budget/handler scans do not duplicate updates. A binding paints immediately at
registration and samples again no sooner than its interval, which must be
1..86400000 ms. Missed intervals produce one current sample without a catch-up
burst. With no bindings, source checkpoints leave the display clock unchanged.

```python
context.dynamic_display.advance(10)                 # logical milliseconds
context.dynamic_display.advance(0, force=True)      # sample now
metadata = context.dynamic_display.snapshot()      # detached, JSON-safe
context.dynamic_display.close_all()                 # explicit cleanup
```

Host values/ports can change between polls. There is no automatic wall-clock
polling. Registrations remain live through pause and program termination until
explicit cancellation or host cleanup; this is not an implicit native lifecycle
policy. Linked routines and scheduled programs can observe shared globals.
Snapshots include IDs, type/window/layout, owner, source key, next due time,
last text and last_status; they contain no executable references.

Per-watch last_status is 0 valid, 1 unknown data, 2 invalid enum index, 4 invalid
data/format and 5 background repaint failure. Background failures retain the
surface and allow source cancellation to proceed. An explicit host advance
raises on exhausted paint capacity before any window in that poll changes.
The bounded logical clock saturates at 2147483646; host advances beyond that
limit reject. Forced polling and cancellation remain possible. Cleanup can clear
fields even after pendant history sequence exhaustion, without adding a row.

## Limits, persistence and CLI

The binding limit defaults to 256 and may be configured from 1..256. Registration
IDs are monotonic and finite. At most 512 field changes are accepted in one
paint/cleanup batch. Ordinary window dimensions and cell budgets still apply.
Portable initiation/cancellation statuses are 0 success, 1 invalid layout/format/
port, 3 missing window/matching binding and 5 binding capacity exhausted.
Missing required services and immediate display-sequence exhaustion raise an
explicit runtime error. None of these codes establish native controller behavior.

Active bindings prevent context save. Cancel them first: live references,
registration state and task execution are not serialized or automatically
rebound. Closed context JSON retains clock settings, elapsed time and ID sequence;
pendant JSON retains the resulting grids/history. Reload performs no subscriptions.

```sh
python -m karel2py examples/dynamic_values.kl -o dynamic_values.py
python dynamic_values.py --context examples/dynamic_values.services.initial.json --state-out dynamic-state.json
python -m karel2py examples/dynamic_ports.kl -o dynamic_ports.py
python dynamic_ports.py --context examples/dynamic_ports.services.initial.json
python -m karel2py.project examples/dynamic_display_project --entry MAIN --context examples/dynamic_display_project/services.initial.json
```

The report's dynamic_display_policy and the
[semantics ledger](semantics/dynamic_display_semantics.json) record this contract.
Native timing, glyph rendering, form/list/table managers, keyboard input, live
binding persistence, controller acceptance and strict mode remain future work.
