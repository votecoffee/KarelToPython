# Pythonic READ formats

Since 0.65.0, omitted-file READ accepts up to two INTEGER format expressions per
scalar destination. Formats extend the [typed input contract](pythonic-read.md)
and [TextInput adapter](text-input.md).

```karel
PROGRAM FIELD_INPUT
VAR value: INTEGER label: STRING[12]
BEGIN
  READ(value::2::16,label::0::2,CR)
  WRITE(label,':',value::0,CR)
END FIELD_INPUT
```

Use `Program(read=TextInput("2A 'O''Brien'\n"))` with the generated module.
The result is `{"VALUE":42,"LABEL":"O'Brien"}`, with output `O'Brien: 42\n`.
Generated scripts use the same formats with `--read-text`.

The [authored example](../examples/pythonic_read_formats.kl) includes a function
width, a dynamic base, adjacent REAL/BOOLEAN fields and quoted STRING input.
Its [text](../examples/pythonic_read_formats.input.txt),
[snapshot](../examples/pythonic_read_formats.expected.json),
[input observations](../examples/pythonic_read_formats.read.expected.json),
[cursor](../examples/pythonic_read_formats.input.expected.json) and
[output](../examples/pythonic_read_formats.write.expected.json) are independent fixtures.

## Format expressions

| Destination | First format | Second format |
| --- | --- | --- |
| INTEGER, BYTE, SHORT | Width 0..254 | Base 0 or 2..16; 0 selects decimal |
| REAL, BOOLEAN | Width 0..254 | Any checked INTEGER; evaluated and ignored |
| STRING | Width 0..254 | 0 unquoted, 2 quoted |

Omitted formats keep the previous behavior. A zero width selects the default
token/remainder behavior, or scans through a quoted field when STRING mode is 2.
A positive width consumes exactly that many characters from the current physical
line, including padding. Fields may be adjacent. A completed previous line
advances using the existing TextInput boundary rule; a field never spans lines.
If too few characters remain, the available remainder is consumed and the READ
fails without consuming the next line. CR remains separate and accepts no format.

INTEGER fields use Python `int(field, base)`; REAL fields use `float(field)`.
Signs, underscores and matching base prefixes follow Python's grammar. Numeric
and BOOLEAN fields accept surrounding whitespace, a chosen Pythonic convenience.
BOOLEAN input accepts TRUE/TRU/TR/T/ON/1 and FALSE/FALS/FAL/FA/F/OFF/OF/0,
case-insensitively. Ambiguous `O` is rejected. Existing storage ranges, SHORT's
sentinel, finite REAL checks and STRING capacities still apply.

## Quoted STRING input

STRING mode 2 skips leading whitespace on its current line, requires an opening
apostrophe and scans to a closing apostrophe. Doubled apostrophes decode to one:
`'O''Brien'` yields `O'Brien`. An empty quoted field initializes an empty STRING.
With width zero, the cursor stops immediately after the closing quote, leaving
adjacent data available. With a positive width, the complete width is consumed;
characters after the closing quote must be whitespace. A missing quote or
unexpected suffix fails the field. A malformed zero-width quoted field consumes
the remaining current line. It never scans the next line for a quote.

The 254-character bound applies to decoded contents before destination
truncation. Quotes, padding and apostrophe escapes do not count toward this bound.
This supports round trips from the existing quoted WRITE formatter, subject to
WRITE's total request bound and destination capacity.

## Evaluation, metadata and failures

Each item captures its destination once, then evaluates width and second format
left to right, once each. Formats are validated before evaluating the next
destination. All destinations and formats finish before the outer input callback.
Calls made by a format expression can themselves read input; those requests
appear before the outer request. Captured references keep their concrete storage
and STRING capacities even if a later expression changes a source binding.

Literal range/type errors are diagnosed during translation when possible;
dynamic errors fail before the outer request or text consumption. Prior target
and function effects remain. Function writes participate in the ordinary
transitive FOR-counter checks. Formatted READ targets remain writable outputs.

Formatted callback targets add a `format_specifiers` tuple containing the
evaluated integers. Unformatted targets retain their previous metadata shape.
Translation reports record literal formats or source positions for dynamic
expressions. CR offsets still count scalar destinations alone.

`TextInput` validates all target metadata before consuming input, then validates
each decoded field before reading the next. A failed field keeps consumed input
consumed and stops before later fields/CRs. The complete response must validate
before any response assignment. Earlier effects remain; ordinary frame and FOR
cleanup applies. Input observations retain metadata/outcomes, not response values.

Typed callbacks and `--read-values` already supply decoded values. They receive
validated format metadata but do not reparse, truncate to field width, unquote
or apply an integer base. Storage validation and destination truncation still apply.

[CONFIG scalar fields](config-field-input.md) now use these widths/bases and
BOOLEAN formats, with turn-domain validation before publishing any READ output.

## Evidence boundary

The reviewed [reference edition](references.md), PDF pages 129-135, documents
input widths, bases, ignored second formats and STRING quote mode. Dynamic format
expressions, width-zero defaults, whitespace tolerance, Python number grammar,
apostrophe escaping and complete-response stores are explicit offline choices.
The manual's quoted-STRING example and prose leave quote retention unclear; this
adapter returns decoded contents without wrappers. Native file/window errors,
buffering, status codes and controller behavior are outside this contract.
Binary formats and explicit FILE/device input remain unsupported. Strict mode
remains future work with its internal READ rejection preserved.
