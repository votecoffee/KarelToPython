# Pythonic typed input

Since 0.63.0, Pythonic mode supports scalar READ through an explicit synchronous
host callback. The callback supplies typed Python values for offline execution.
Since 0.64.0, [TextInput and CR](text-input.md) also support explicit text and
line control through the same callback interface.
Since 0.65.0, [READ formats](read-formats.md) add widths, bases and STRING quoting,
including ordered dynamic expressions.

```karel
PROGRAM INPUTS
VAR count: INTEGER label: STRING[4] enabled: BOOLEAN
BEGIN
  READ(count,label,enabled)
  IF enabled THEN count=count+1 ENDIF
  WRITE(label,':',count::0,CR)
END INPUTS
```

After generating `converted.py`, supply one value per destination:

```python
from converted import Program

messages = []
program = Program(read=lambda request: [7, "widget", True], write=messages.append)
assert program.run() == {"COUNT": 8, "LABEL": "widg", "ENABLED": True}
assert messages == ["widg: 8\n"]
```

The complete [authored example](../examples/pythonic_read.kl) uses three input
batches, including two function-local reads in a FOR loop. Its
[input values](../examples/pythonic_read.read.values.json),
[request observations](../examples/pythonic_read.read.expected.json),
[snapshot](../examples/pythonic_read.expected.json) and
[output](../examples/pythonic_read.write.expected.json) are independent fixtures.

## Destinations and values

Use `READ(destination,...)` with 1..1024 total scalar destinations and CR markers.
CR-only requests are allowed. Scalar destinations are rooted in ordinary
variable storage: INTEGER, BOOLEAN, REAL, bounded STRING and BYTE/SHORT aggregate
leaves, including TYPE aliases. Each destination may be a variable, field or
ARRAY element. Aggregates, grouped/computed targets, fields of returned
temporaries, constants, active FOR counters, CONFIG subfields and POSITION
orientation writes remain blocked.

The callback returns an exact list or tuple with one typed value per destination:

| Destination | Python value and checks |
| --- | --- |
| INTEGER | `int`, excluding `bool`; existing signed-32-bit storage range and MAXINT restriction |
| REAL | Finite `float` or checked INTEGER promoted to `float` |
| BOOLEAN | `bool`; numeric and textual values are not converted |
| STRING | ASCII `str`, at most 254 characters before right-truncation to destination capacity; whitespace and empty contents preserved |
| BYTE/SHORT leaf | Checked narrow `int`; SHORT 32767 retains its uninitialized-marker meaning |

STRING reference formals keep the actual caller capacity. Private value
parameters retain their temporary capacity and receive no copy-back.

## Capture, validation and failures

Resolve all destination references once, left to right, before invoking the
callback once. Subscript functions may have ordinary effects and nested READs.
A target/capture failure creates no outer request; earlier effects remain.
With `x=1`, `READ(x,a[x])` still targets `a[1]` when the new `x` is 2.

Check the complete response before assigning values in destination order.
Repeated aliases use the last value, with every supplied value still validated.
Callback exceptions, wrong response shapes or invalid values perform no response
assignment. Earlier target/callback mutations remain. Input consumption and host
effects are never rolled back or automatically retried. If host code disrupts
captured storage and a later assignment fails, earlier completed stores remain.

Ordinary callback exceptions become source-located `KarelRuntimeError`s with
their original cause; interruptions propagate. Routine frames unwind, and
initialized FOR counters follow existing cleanup rules. Step exhaustion before
READ prevents its callback. Step limits do not bound time in host callbacks.

No adapter is selected by default. Reaching READ without `Program(read=...)`
raises an explicit error. Exhausted batches follow the callback failure path.
Coroutines, generators and arbitrary response objects are rejected; the callback
is synchronous. Native text parsing and input-error clearing are not inferred.

## Requests and reports

The callback receives a defensive dictionary with `line` and `targets`. Each
target gives `type` and its concrete `type_spec`, including STRING capacity.
It receives no live reference, storage address or previous target contents.
`Program.read_requests` returns defensive metadata/outcome copies; these
observations retain no response values and reset at each run start.

| `adapter_outcome` | Meaning |
| --- | --- |
| `missing_adapter` | READ reached without a callback |
| `callback_started` | Callback invoked |
| `callback_failed` / `callback_interrupted` | Callback raised an exception / interruption |
| `callback_result_rejected` | Response shape or value failed validation |
| `response_validated` | Complete response checked; assignment is next |
| `assignment_failed` | Assignment failed after validation |
| `callback_completed` | All response values assigned |

Nested requests keep their actual request order. The translation report's
`reads` records destination roots, types and physical source locations;
`read_policy` states this contract. `routine_effects[].potential_input_requests`
propagates through internal calls. READ also contributes global/formal writes
to the existing FOR-counter proof.

## Generated scripts

Scripts containing READ require `--read-values` with a UTF-8 JSON list of
response batches, one per executed READ, including routine reads:

```sh
python -m karel2py examples/pythonic_read.kl -o converted.py
python converted.py --read-values examples/pythonic_read.read.values.json
```

Programs also using joint conversions retain their required `--joint-axes`.
Alternatively, choose `--read-text` for explicit ASCII text; the options are
mutually exclusive. CR adds no batch values, and a CR-only batch is `[]`.
Unused batches are allowed by the script adapter; the example runner checks that
each fixture consumes all its batches. Translation with `--check` requires no
adapter and executes no READ.

## Reference boundary

The reviewed [reference edition](references.md), PDF pages 127 and 496-497,
describes READ destinations and native file/device, format, CR and error rules.
Typed host values, text/CR adapter rules and complete-response validation are
chosen Pythonic behavior. Native text/binary tokenization, buffering, EOF, file/window
error clearing or re-prompting, IO_STATUS and default TPDISPLAY/INPUT behavior
remain outside this contract. The conservative READ rejection is retained for
the future strict milestone. No controller input or native runtime acceptance
is established.
