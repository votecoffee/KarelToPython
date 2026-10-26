# Offline XML input

The five XML calls operate on an explicitly supplied MemoryFiles or DirectoryFiles
backend. Set ATR_XML (AR_XML is an alias) before opening the FILE as text RO.
The input is prevalidated as bounded ASCII XML before delivering any tag events.
DTD/entity declarations, external entities and non-ASCII data are rejected.

| Call | Supported form |
| --- | --- |
| XML_ADDTAG | `(file, name, numchar, caseflag, ident, status)` |
| XML_REMTAG | `(file, name, status)` |
| XML_SCAN | `(file, tag_name, tag_ident, function_code, status)` |
| XML_GETDATA | `(file, numattr, attrnames, attrvalues, text, textdone, status)` |
| XML_SETVAR | `(file, program_name, variable_path, status)` |

These forms follow the manual's worked example and accepted compiler cases. The
appendix syntax lines omit the GETDATA status and SCAN identifier, and add an
unused REMTAG identifier; the parameter descriptions and example clarify them.
Compiler acceptance establishes source forms, not native execution equivalence.

## Register and scan tags

XML_ADDTAG registers a name and unique positive INTEGER identifier. Identifiers
zero, XML_ERROR, XML_FUNCTION and XML_SCANLIM are reserved. Up to 128 registrations
are retained per open FILE. Duplicate names, ignoring case, and duplicate IDs
return XML_INVALID without replacing a registration. The character count is
1..254; it compares that many characters of each name. A count at least as large
as the complete name implements an exact name match. Caseflag TRUE preserves
case and FALSE folds it. If prefixes overlap, the first registration wins.

XML_SCAN ignores unregistered tags. A matching opening tag returns XML_START;
an ordinary closing tag returns XML_END without attributes. A self-closing tag
returns one XML_END event with its attributes. XML_STEND is retained as a constant
but is not emitted, following the manual's example. Names retain original case.

**SCAN status XML_FUNCTION means a tag or text-continuation delivery; zero means
EOF.** At EOF, the name is empty, identifier zero and function XML_END. After
50 skipped physical lines, SCAN can return XML_SCANLIM as status and identifier;
call it again to continue. These package constants are portable identifiers.

XML_GETDATA returns original attribute names/values in supplied one-dimensional
STRING arrays. Both arrays must fit every attribute, and each element must fit
the complete name/value. Unused array elements retain their previous values;
use numattr to determine valid entries. A capacity failure returns XML_CAPACITY
and preserves all data outputs and the text offset for retry.

Text means immediate text following the current tag, up to the next element
boundary. Comments and processing instructions are ignored; CDATA and predefined
XML entities are decoded. Each GETDATA reads up to the destination STRING's
concrete capacity and sets textdone when exhausted. Repeated GETDATA calls can
finish the text directly. If a read left more text, a subsequent SCAN reports
XML_TXCONT for the same tag. Scanning without reading a tag's text skips it and
advances to the next registered event.

## Apply attributes to variables

XML_SETVAR resolves attached globals or explicit VariableStore bindings through
the existing static variable-path rules, including supported PATH node fields.
An empty program name selects the current program. The target must be a user
STRUCTURE with flat INTEGER, REAL, BOOLEAN or bounded STRING fields.

Attribute names match KAREL field names without case sensitivity. INTEGER values
use signed decimal text; REAL values use finite Python float equivalents.
BOOLEAN accepts 0/1, TRUE/FALSE or ON/OFF, without case sensitivity. STRING values
must fit their destination. Unknown fields, duplicate names after case folding,
unsupported field types and invalid values reject the entire update. All values
are prepared before any field changes. Unmentioned fields retain their values,
including uninitialized markers. No variables or types are created implicitly.

The call needs an attribute-bearing start or self-closing event; an ordinary end
event is not eligible. Output overlap checks include the target and status cell.
Direct, transitive and condition-handler FOR-counter protections also apply to
these indirect writes. No arbitrary Python attributes or callback code is loaded.

## Limits, status and lifetime

Inputs are limited to 1 MiB, 64 nesting levels, 65536 events, 32 attributes per
tag and 254 characters per name/value. Parsing charges each 4096-byte block and
each element event to the ordinary execution budget; scanning charges visited
events. A malformed later element prevents earlier event delivery because the
complete document is validated first.

| Status | Meaning |
| --- | --- |
| 0 | Success for registration/data/update; EOF for SCAN |
| XML_FUNCTION (1001) | SCAN delivered a registered event or text continuation |
| XML_SCANLIM (1002) | Resume SCAN after a 50-line boundary |
| XML_STATE (1) | No eligible current event, unresolved target or active-tag removal |
| XML_INVALID (2) | Invalid registration, field mapping or converted value |
| XML_CAPACITY (3) | Output destination too small; data/offset preserved |
| XML_PARSE (4) | Invalid/unsupported XML; SCAN publishes XML_ERROR (-1) and function zero |
| XML_LIMIT (5) | Input size or registration limit exceeded |

All statuses and XML function codes are package choices, not native alarm/enum
claims. Parse failures remain sticky until reopen. Missing/incorrect FILE state,
changed backend bytes, invalid ordinary values and step exhaustion raise.

Pause retains registrations and pending text. CLOSE releases the scanner; reopen
starts at byte zero with no registrations. A current tag cannot be removed until
SCAN advances beyond it. Ordinary READ and SET_FILE_POS are blocked for XML FILEs;
reopen to restart. The exposed cursor advances on scanned tags/line limits/EOF,
not as an exact native streaming-position model. No source bytes are modified.

Context JSON retains file contents and ordinary variable/serial values. It omits
FILE handles, registrations and live parser state. The
[authored all-call example](../examples/xml_input.kl) includes attribute updates,
text continuation and complete cleanup, and can be replayed with saved JSON.

```sh
python -m karel2py examples/xml_input.kl -o xml_reader.py --report xml-report.json
python xml_reader.py --context examples/xml_input.services.initial.json --state-out xml-state.json
```

See `xml_input_policy` in the report and the
[semantic ledger](semantics/xml_input_semantics.json). XML writing, Unicode,
namespace interpretation, native parser behavior and suspended parser checkpoint
restoration remain outside this implementation. Strict mode remains future work.
