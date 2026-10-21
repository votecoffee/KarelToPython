# Pythonic text input and CR

Since 0.64.0, `runtime.TextInput` adapts explicit ASCII text to the checked
[READ callback contract](pythonic-read.md). READ also accepts CR markers for
line control, including leading, repeated and CR-only forms.

```karel
PROGRAM TEXT_INPUT
VAR count: INTEGER label: STRING[8] enabled: BOOLEAN
BEGIN
  READ(count,enabled,CR)
  READ(label,CR)
  count=count+1
  WRITE(label,':',count::0,CR)
END TEXT_INPUT
```

For a generated `converted.py`, supply a persistent reader:

```python
from converted import Program
from karel2py.runtime import TextInput

reader = TextInput("7 ON ignored\nwidget\n")
program = Program(read=reader)
assert program.run() == {"COUNT": 8, "LABEL": "widget", "ENABLED": True}
assert program.write_requests[0]["text"] == "widget: 8\n"
assert reader.position == {"line": 3, "column": 1, "eof": True}
```

The complete [authored example](../examples/pythonic_text_input.kl) reads fields
and function-local values in a FOR loop. Its [text](../examples/pythonic_text_input.input.txt),
[snapshot](../examples/pythonic_text_input.expected.json),
[READ observations](../examples/pythonic_text_input.read.expected.json),
[cursor](../examples/pythonic_text_input.input.expected.json) and
[output](../examples/pythonic_text_input.write.expected.json) are independent fixtures.

## Parsing rules

`TextInput(text)` accepts an ASCII `str` held in memory. It opens no device or
file and selects no implicit stdin. LF, CRLF and CR delimit physical lines;
CRLF counts as one line ending. Numeric and BOOLEAN fields skip ASCII whitespace
and blank lines, then consume one whitespace-delimited token.

| Destination | Chosen interpretation |
| --- | --- |
| INTEGER, BYTE, SHORT | Python `int(token,10)`, including signs and underscores; prefixes such as `0x10` are rejected |
| REAL | Python `float(token)`, including decimal, exponent and underscore forms; finite values required |
| BOOLEAN | Case-insensitive TRUE/FALSE, ON/OFF, T/F and 1/0 |
| STRING | Unformatted: remaining characters on the current line, including separating/leading blanks; no token splitting |

Since 0.65.0, [READ formats](read-formats.md) add positive fixed widths, nondecimal
bases and quoted STRINGs with apostrophe escaping. BOOLEAN input also accepts
TRU/TR and FALS/FAL/FA/OF abbreviations. The table describes unformatted defaults.

Existing storage checks apply to each parsed value before reading the next
field: INTEGER ranges/MAXINT, narrow ranges/SHORT sentinel, finite REALs and
the 254-character STRING input bound before destination truncation. The adapter
returns raw typed values; the READ runtime performs complete-response validation
and ordered assignment through the captured references.

After a field ends exactly at a line boundary, a subsequent STRING advances to
the next line. A fresh empty line supplies an initialized empty STRING. This
avoids manufacturing empty fields between ordinary successive line reads.
If characters remain after a numeric token, STRING preserves them, including
blanks. For example, input `7 label` for `READ(number,text)` gives `text=' label'`
before capacity truncation. These are explicit Pythonic boundary choices.

## CR and position

CR discards the rest of the current line and advances to the next one.
`READ(x,CR,y)` parses x, discards its line remainder, then parses y.
`READ(CR)` consumes one current line without a value. Repeated CRs consume
successive lines. A STRING leaves its line boundary available to a following CR,
so `READ(text,CR)` finishes that line without discarding the next line.
CR can finish an unterminated final record; a further CR at EOF raises an error.

The READ limit is 1024 total scalar destinations plus CR markers.
Optional `line_breaks` metadata records each CR as the number of scalar
destinations preceding it: `[1]` for `READ(x,CR,y)`, `[0,0]` for `READ(CR,CR)`.
Positions are ordered and may repeat. Plain scalar requests retain their former
metadata shape. CR consumes no callback response values; a JSON CR-only batch
is `[]`. Typed batch adapters have no text cursor to discard.

`reader.position` returns a new dictionary with one-based input `line` and
`column`, plus `eof`. EOF means no text characters/line endings remain; a CR may
still finish the current unterminated record. The cursor persists across calls
and explicit warm runs. Construct a new reader to start the same input again.

## Failures and execution

Malformed metadata is rejected before consumption. A bad token is consumed,
then parsing stops before later fields or CRs. Errors identify the destination
type and starting input line/column. EOF supplies no invented values or lines.
Consumed input is never rewound. If parsing fails partway through a READ,
the callback fails and no response values are assigned; prior target/callback
effects remain. Ordinary frame and FOR cleanup still applies.

The adapter uses Pythonic numeric validation even when invoked directly from a
host; it restores the surrounding numeric context after each validation.
Large integer tokens remain subject to the host Python integer parsing limit.

Generated scripts offer mutually exclusive explicit input adapters:

```sh
python -m karel2py examples/pythonic_text_input.kl -o converted.py
python converted.py --read-text examples/pythonic_text_input.input.txt
```

`--read-values` remains available for JSON batches. Both input-file loaders use
UTF-8 with an optional BOM. `--read-text` requires ASCII content after decoding.
Programs using joint conversions also retain `--joint-axes`.

## Evidence boundary

The reviewed [reference edition](references.md), PDF pages 127 and 496-497,
describes CR line skipping and READ input. This adapter chooses explicit Python
token grammars, STRING boundary behavior and complete-response assignment for
offline use. It establishes no native parser, file/window re-prompt, error
clearing, EOF/status/alarm or controller-input equivalence. Binary
transfer and controller FILE/device access remain outside this subset. Strict
mode remains a future milestone with its internal READ rejection retained.
