# Pythonic text output

Pythonic mode supports comma-separated STRING, BOOLEAN, INTEGER, BYTE, SHORT and
REAL expressions in omitted-file `WRITE` statements. `CR` emits an LF newline.
No newline or separator is added automatically between data items.

```karel
PROGRAM output_demo
VAR value: REAL
BEGIN
  value=1.0/3.0
  WRITE('value=',value::0::3,', enabled=',ON,CR)
END output_demo
```

This creates one request containing `value= 0.333, enabled= TRUE\n`, where `\n`
denotes one actual newline. Numerical items retain one leading blank before any
extra width padding. See the complete [authored example](../examples/pythonic_output.kl)
and its [expected output](../examples/pythonic_output.write.expected.json).

## Formatting equivalents

Specifiers are KAREL INTEGER expressions separated by `::`. Their meaning depends
on the data type. See [dynamic formats and quoted fields](text-formats.md).

| Data type | No format | `::width` | Second specifier |
| --- | --- | --- | --- |
| STRING | Contents unchanged | Truncation, padding and bounded natural-width fallback | 0/1: unquoted left/right; 2/3: quoted left/right with doubled apostrophes. |
| INTEGER, BYTE, SHORT | Signed decimal with a leading blank | Minimum right-aligned field, expanding to fit | Base 2..16; 0 selects decimal. Uppercase A..F; nondecimal fields zero-fill after an optional minus. |
| REAL | Leading blank plus Python `.5E` scientific formatting | Minimum right-aligned field, expanding to fit | Nonnegative precision selects fixed-point `.nf`; negative precision selects scientific `.nE` using its absolute value. |
| BOOLEAN | Leading blank plus TRUE/FALSE | Minimum right-aligned field, expanding to fit | Unsupported. |
| CR | One LF newline | Unsupported | Unsupported. |

For example, `WRITE(5::6::2)` yields ` 00101`; `WRITE(-42::0::16)` yields
` -2A`; `WRITE(123.456::9::2)` yields `   123.46`; and
`WRITE(123.0::12::-3)` yields `   1.230E+02`.

Numeric and BOOLEAN widths are bounded to 0..254, with 0 selecting natural width.
REAL precision is bounded to -254..254. Decimal formatting uses Python rounding;
negative nondecimal integers use a minus sign rather than controller bit-pattern
formatting. These are chosen Pythonic conventions. STRING quoting preserves
paired quotes and complete escapes when truncating. Aggregate output,
explicit devices/files, binary transfer, READ and IO_STATUS remain unsupported.

## Evaluation and output callbacks

Items are evaluated and formatted **once, from left to right**. This permits
multiple routine calls in one `WRITE` list. An item's value is captured before a
later item can change its source storage. For each item, evaluate the value,
width and second format in that order, then validate and render. Expressions
follow the chosen [evaluation order](evaluation-order.md), including function
effects and Boolean short circuiting.

After all items render, the combined ASCII output is checked against the
254-character statement limit. The prototype also bounds a statement to 1024
items, including empty strings and CR. One complete request is then recorded or
sent to the callback. Rendering or total-length failure produces no outer
request; earlier expression changes and nested output requests remain visible.
Routine frames unwind on errors. Failed/interrupted callbacks are recorded and
are not retried; external callback effects can remain.

`Program().run()` records text in `write_requests`. To display text on the host
console without extra newlines, supply a callback when executing the generated
module:

```python
from converted import Program

program = Program(write=lambda text: print(text, end=""))
snapshot = program.run()
```

The callback receives one complete string per statement and must return `None`
synchronously. `Program.write_requests` retains defensive text/line/outcome
observations with or without a callback. Generated modules do not open files,
select a controller device or connect to a robot.

## Evidence

The reference manual's WRITE syntax supplies item lists and CR, and its text I/O
tables supply numeric formatting forms. Python rounding, LF newline mapping,
nondecimal minus signs, precision/width bounds and complete-request callback
delivery are explicit implementation choices. The
[semantic contract](semantics/pythonic_write_semantics.json) records source pages
and tests. The older [WRITE ledger](semantics/write_semantics.json) preserves
the conservative research subset; a released strict mode remains a future
milestone.
