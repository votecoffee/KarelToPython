# Pythonic text formats

Since 0.57.0, WRITE widths, alignments, bases and precision can be KAREL INTEGER
expressions. CNV_REAL_STR also supports negative precision for scientific output.
These are practical Pythonic conventions, without a claim of controller equivalence.

```karel
PROGRAM formats
VAR width: INTEGER
    text: STRING[32]
BEGIN
  width=12
  CNV_REAL_STR(123.456,width,-3,text)
  WRITE(text,CR,'O''Brien'::width::3,CR)
END formats
```

The snapshot contains `WIDTH=12` and `TEXT="   1.235E+02"`. One output request
contains `   1.235E+02\n  'O''Brien'\n`, with each `\n` denoting an LF character.
The [complete example](../examples/pythonic_text_formats.kl) also shows dynamic
base selection, a format function and quoted truncation, checked against
[expected values](../examples/pythonic_text_formats.expected.json) and
[expected output](../examples/pythonic_text_formats.write.expected.json).

## Format expressions

| KAREL form | Pythonic equivalent | Limits |
| --- | --- | --- |
| `WRITE(value::width)` | Evaluate `value`, then `width`, then render | Numeric/BOOLEAN width 0..254; STRING width 0..2147483647 with bounded fallback. |
| `WRITE(number::width::base)` | Checked INTEGER base formatting | Base 0 selects decimal; otherwise 2..16, uppercase A..F, no prefix. |
| `WRITE(real::width::precision)` | Python `format(real, '.nf')` or `'.nE'` | Precision -254..254; negative selects scientific with its absolute value. |
| `WRITE(text::width::alignment)` | Checked truncation, padding and quoting | Alignment 0/1 unquoted left/right, 2/3 quoted left/right. |
| `CNV_REAL_STR(real,width,precision,text)` | Leading blank plus Python fixed/scientific formatting and left padding | Width 1..254; precision -254..254; retain caller capacity and blank/asterisk overflow marker. |

Variables, constants, fields, array elements, arithmetic, built-ins and INTEGER
functions can provide formats. BYTE/SHORT values are promoted to INTEGER.
BOOLEAN, REAL, STRING and aggregate format values are rejected during translation.
BOOLEAN data accepts only one format; CR accepts none. Static signed/grouped
literal range errors are reported during translation. Other range errors are
reported during execution, before sending the outer output request.

Each item evaluates **value, width, then second format**, once each. It validates
and renders before the next item starts. A value is captured before a format
function can change its source storage. All formats for an item are evaluated
before its range checks; an error while evaluating an expression skips later
expressions. Earlier changes and nested output remain visible on failure or
ABORT, and routine frames unwind. The complete statement is sent once, after
all items render and the combined ASCII length is checked. See
[evaluation order](evaluation-order.md) and [output callbacks](pythonic-output.md).

## Quoted STRING fields

Quoted modes retain a leading blank and enclosing apostrophes. An apostrophe in
the contents becomes two apostrophes. Padding is outside the quotes; contents
are truncated from the right to fit the field. A doubled apostrophe is indivisible:
if it will not fit, truncation stops there, including all following contents.

- `'O''Brien'::11::2` renders ` 'O''Brien'`.
- `'ABCDE'::6::2` renders ` 'ABC'`.
- `CHR(39)::4::2` renders ` '' `; the two-character escape will not fit.
- Widths 1 or 2 promote to 3, preserving the wrapper ` ''`.
- Width 0 or greater than 254 selects the natural **rendered** length, including
  the blank, quotes and doubled apostrophes. No huge padding is allocated.

Unquoted modes retain their previous rules: widths 1..254 truncate/pad contents;
width 0 or greater than 254 uses the contents' length. STRING input must be
initialized ASCII of at most 254 characters before truncation. Quoting can expand
the result; the combined 254-character output limit still applies and produces
no outer request on overflow. No implicit truncation is applied to the combined
statement. The 1024-item, step, call-depth and ownership checks remain.

## Compatibility and evidence

Earlier public versions rejected dynamic formats, negative CNV_REAL_STR precision
and quoted contents needing escaping, truncation or width fallback. These now
use the conventions above; positive fixed formatting and fitting quote-free
fields retain their results. Widths below three and doubled-apostrophe truncation
are chosen implementation policies, not inferred native behavior.

Reports preserve numeric literal `format_specifiers`. A dynamic specifier is an
object with `expression=true` and its physical `line` and `column`; dynamic width
or alignment metadata is marked explicitly. `write_policy` and `conversion_policy`
describe the runtime rules. See the
[semantic ledger](semantics/pythonic_text_format_semantics.json) and
[execution tests](../tests/test_pythonic_text_formats.py).
Conservative formatting tests remain internal for the future strict milestone.
Files/devices, READ, binary output, aggregate WRITE and IO_STATUS remain outside
this offline implementation.
