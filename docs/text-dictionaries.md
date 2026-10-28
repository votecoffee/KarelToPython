# Offline text dictionaries

ADD_DICT, CHECK_DICT, READ_DICT, READ_DICT_V, REMOVE_DICT, WRITE_DICT and
WRITE_DICT_V use an explicit TextDictionaries service. It parses supplied ASCII
text and keeps independent loaded snapshots for each language/name pair.
Native compressed TX files and dictionary/form compilers are not invoked.

```json
{"dictionaries":{"sources":{"labels":"$1, Greeting \"Hello\" &new_line"}}}
```

Pass a context JSON file to generated Python with --context, or construct
`rt.ExecutionContext(dictionaries=rt.TextDictionaries(sources={...}))` in Python.
Source labels are opaque, case insensitive catalog keys; slash directions are
canonicalized and a missing extension becomes .TX. ADD_DICT never opens the
host filesystem or searches controller devices. A label ending in .TX still
refers to supplied decoded text, rather than native compressed bytes.

## Loading and languages

```karel
ADD_DICT('labels','USER',DP_DEFAULT,DP_DRAM,status)
CHECK_DICT('USER',1,status)
READ_DICT('USER',1,lines,1,last_line,status)
REMOVE_DICT('USER',DP_DEFAULT,status)
```

Names use the first four ASCII identifier characters, case insensitively.
DP_DRAM=1 is the portable supported load option; it selects a logical snapshot,
without modeling native DRAM placement or startup retention. Loading an existing
language/name pair returns duplicate status and preserves the original text.
Source changes affect later loads after removal, rather than existing snapshots.

The service has explicit languages, default_language and language fields.
They default to ENGLISH. If a PendantDisplay is supplied, its current/default
language selects dictionary operations. Otherwise the dictionary service's own
configuration is used. ADD_DICT/REMOVE_DICT accept the DP_* STRING constants;
DP_DEFAULT resolves to the configured default. Reads use the exact current
language without implicit fallback. REMOVE_DICT(name,'',status) removes that
name from every loaded language. No language dictionaries or translations are
downloaded or generated.

CHECK_DICT accepts an INTEGER element ID, a decimal STRING or a case sensitive
element name STRING. The reference's signature labels this argument STRING;
the supplied historical compiler inventory records an accepted INTEGER case.
These two explicit lookup forms are a Pythonic compatibility choice. CHECK_DICT
checks presence without expanding a potentially large element.

## Supplied text syntax

```text
* Authored text catalog
$0, Heading "Summary" &new_line
$1, Detail "Count: %04d" &new_line
$- "Done" &new_line
$3 +Heading +Detail
```

Elements start with $number; IDs are 0..32767 and may be sparse. $- assigns the
previous ID plus one. Optional comma-separated element names are case sensitive
ASCII identifiers up to 250 characters. Names and IDs must be unique. Comments
start with * outside quoted text and continue to the physical line end.

Quoted text is printable ASCII and stays on one physical line. Backslash escapes
are limited to double quote and backslash: \" and \\. Multiple strings and tokens
may appear in an element. +number or +Name includes a preceding or following
element. Missing references, cycles and nesting beyond five total levels fail
loading. Unknown syntax fails explicitly.

@row,column positions a window cursor. &new_line ends a read-output row and
advances window output. Recognized controls include &clear_win, &clear_2_eol,
&clear_2_eow, &home, &cr, &lf, &rev_lf and &bs. Printable #ASCII codes and the
supported control/style codes are accepted. READ ignores cursor/control/style
tokens except new_line; WRITE applies cursor/clear/control tokens atomically.

Known foreground/background colors and blink, reverse, bold, under_line,
double_wide, standard, graphics_on, ascii_on, double_high, normal_size and
multi_on attributes are recognized and ignored by the character-grid model.
This is text output without native font, color, glyph or graphic behavior.
Unsupported character codes, Unicode, native forms and unknown attributes fail
loading rather than disappearing silently.

## Plain and formatted reads

READ_DICT(name,id,output,first_line,last_line,status) writes a one-dimensional
STRING ARRAY beginning at the requested one-based row. It preserves the prefix
and unused tail, returns the last row used and right-truncates strings to their
cell capacities. Insufficient rows or cell widths return 33008 while retaining
the successfully copied prefix. A trailing new_line does not create an extra
empty output row; consecutive newlines preserve intervening blank rows.
An empty element returns one empty string. Plain reads leave percent text literal.

READ_DICT_V(name,id,value_paths,output,status) starts at output row 1. value_paths
is a one-dimensional STRING ARRAY containing static global variable paths:

```karel
values[1]='COUNT'
values[2]='[LIB]LABEL'
READ_DICT_V('USER',2,values,lines,status)
```

Paths resolve through the existing checked variable service. They can contain
fields, fixed subscripts and PATH node fields. [PROGRAM] selects an explicitly
attached owner; omission selects the executing module's globals. Routine-local
names, arbitrary Python attributes and expressions are unavailable. Only used
argument slots need initialized paths. Values are fully rendered before output
mutation, including when the input and output ARRAY share storage.

Formats use `%[-][+][0][width][.precision]conversion[^argument]`. Width and
precision are bounded at 254. Supported conversions are d/o/x/X/u for integral
scalars, s for STRING and f/e/E/g/G for REAL. BOOLEAN displays 0/1. Unsigned
integer formats use the low 32 bits. Python percent formatting supplies the
chosen padding, precision, scientific notation and rounding behavior. Numeric
flags on strings and mismatched variable types fail explicitly. %% emits a
literal percent without consuming an argument.

^argument selects a one-based value_paths entry. Each non-percent specifier also
advances the ordinary sequential slot, even when an explicit slot is selected.
Nested elements share that sequence. The model safely reads SHORT/BYTE fields
for reordered formats; it does not reproduce native argument ABI restrictions.
Missing/uninitialized variables and invalid formats preserve every output row.

## Window writes

WRITE_DICT(file,name,id,status) and WRITE_DICT_V(file,name,id,value_paths,status)
require an open WD:name FILE owned by the supplied PendantDisplay. Ordinary
memory/directory files are rejected. See [pendant displays](pendant-display.md)
for window setup, cursors, scrolling and source FILE syntax.

Each request validates and stages the entire grid/cursor update before mutation.
A late invalid cursor, format, byte-position overflow or exhausted display
sequence leaves the prior surface, cursor, position and accepted history intact.
A successful write adds one WINDOW_WRITE row. Logical position counts emitted
ASCII/control bytes; cursor, style, home, reverse-line-feed and clear-to-end
commands have no emitted byte count. clear_win emits one form-feed byte.

## Limits, statuses and persistence

There are at most 64 source labels and 64 loaded language/name pairs. Source and
loaded text each have a separate 1 MiB budget, with at most 64 KiB per text.
A file has at most 4096 elements and 16384 tokens. Expansion is limited to 16384
tokens and rendered text/control output to 65536 bytes per call.

Portable statuses are 0 success, 1 invalid input/source, 2 duplicate load,
3 missing source/dictionary/element, 4 variable/format/window failure and
5 capacity/expansion limit. Unavailable language returns 33003; truncated ARRAY
output returns 33008. The latter two retain the documented language/truncation
cases. Other codes and DP_DRAM's numeric value are package conventions.
Source argument types, disjoint output storage, POSITION/CONFIG protection and
active FOR-counter guards remain in force before backend execution.

Context JSON retains source text, language configuration and independent loaded
text snapshots. Reload reparses these logical snapshots without ADD replay or
native startup restoration. The usual pendant rule still requires every window
FILE to be closed before saving context. Model snapshots are detached copies.

```sh
python -m karel2py examples/dictionary_text.kl -o dictionary_text.py
python dictionary_text.py --context examples/dictionary_text.services.initial.json
python -m karel2py examples/dictionary_window.kl -o dictionary_window.py
python dictionary_window.py --context examples/dictionary_window.services.initial.json --state-out dictionary-state.json
python -m karel2py.project examples/dictionary_project --entry MAIN --context examples/dictionary_project/services.initial.json
```

Reports expose dictionary_policy and a [semantics ledger](semantics/text_dictionary_semantics.json).
Native compressed formats, dictionary/form compilation, glyph rendering,
interactive form/list/table controls, keyboard input, strict mode and controller acceptance remain
future work.
