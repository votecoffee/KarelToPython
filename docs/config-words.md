# Portable CONFIG word values

Pythonic source can assign between CONFIG and INTEGER, BYTE or SHORT and pass
these conversions as private ordinary routine arguments/results. ARRAY and
user-STRUCTURE data conversions and GET_VAR/SET_VAR use the same checked codec.
This is an authored value representation. The reference manual defines the
seven CONFIG fields but does not establish this encoding as native memory.
Strict mode remains a future milestone.

```karel
VAR cfg:CONFIG word:INTEGER
-- Inside BEGIN:
cfg=22415
word=cfg                         -- 22415
-- Turns (-1,-8,7), FLIP and UP true; LEFT and FRONT false.
```

## Encoding and domains

A word is an INTEGER in **0..65535**. No byte order is implied by the value.
The codec uses three signed four-bit turn counts and four BOOLEAN flags:

| Field | Word bits | Value |
| --- | --- | --- |
| CFG_TURN_NO1 | 0..3 | Signed nibble, -8..7 |
| CFG_TURN_NO2 | 4..7 | Signed nibble, -8..7 |
| CFG_TURN_NO3 | 8..11 | Signed nibble, -8..7 |
| CFG_FLIP | 12 | BOOLEAN |
| CFG_LEFT | 13 | BOOLEAN |
| CFG_UP | 14 | BOOLEAN |
| CFG_FRONT | 15 | BOOLEAN |

Zero means all turns zero and all flags false. Word 65535 means every turn -1
and every flag true. Negative words, extra high bits, REAL and BOOLEAN values
are rejected. Encoding requires complete CONFIG fields, exact BOOLEAN flags
and the existing turn range. This does not validate a physical robot branch.

BYTE and SHORT destinations retain their existing checked ranges. SHORT 32767
is still its missing sentinel when stored; a source SHORT with that sentinel
cannot supply an initialized scalar word. No truncation, masking of extra high
bits or invented contents for unknown BYTE values occurs.

## Source values and ownership

Assignment evaluates and converts the source before receiver selectors.
Ordinary typed argument conversion occurs once at that argument position,
before later arguments. Converted formals own independent writable values;
changes do not copy back. RETURN finishes conversion before normal frame/counter
cleanup. Bare same-type references retain their established alias behavior.

Named and anonymous ARRAYs retain existing matching logical dimensions and
receiver component schemas. User records retain the same field-name set,
receiver order and staged nested conversion rules. A failed batch leaves the
receiver unchanged. Existing element and CONFIG aggregate aliases survive a
successful whole-record replacement; CONFIG subfield arguments remain values.

Rows/planes use their existing source-prefix policies, including
[explicit live BYNAME storage](array-prefix-references.md) whose *assignment*
can receive converted data. BYNAME lookup itself still requires exact formal
compatibility. Active FOR protections, protected POSITION orientation fields,
linked declared signatures and raw external callback results remain exact.
Builtin typed inputs and dedicated robot-context table writers do not acquire
implicit word conversion; convert into ordinary CONFIG storage first.

## Partial data and variable transfers

Missing integral members in data ARRAYs/records become shaped CONFIG records
whose seven fields are missing. A partially initialized CONFIG becomes a missing
integral member. Validate every known source field before using missingness;
malformed known turns/flags cannot be hidden by another missing field. Scalar
source reads/encodes still require initialized values.

GET_VAR/SET_VAR support scalar, ARRAY-prefix and record word conversions through
ordinary explicit variable paths. They preserve receiver tails, metadata overlap
guards, lookup/cache rules and staged publication. Copied missing data retains
status 12311. Invalid words fail before data, entry/status or cache publication.
Uninitialized CONFIG-to-BYTE transfers remain missing data rather than reporting
an invented initialized byte. Dynamic CONFIG bindings retain ordinary creation
metadata, rename behavior and saved values.

## Files, saving and evidence

READ/WRITE keep their existing scalar transport layouts. A decoded word can be
read/written as an INTEGER using the normal text or binary INTEGER format;
`CONFIG=word` performs the separate value conversion. CONFIG aggregate I/O still
expands its seven fields. This codec does not introduce a packed two-byte CONFIG
FILE representation or a native ABI.

Context JSON and VR archives retain ordinary CONFIG/integral schemas and values.
There is no codec session, live alias, robot context or executable state to save.
The tests cover every 16-bit word, independent field/flag anchors, malformed data,
private/linked interfaces, missing values, file input and atomic transfers.
They establish offline behavior without native compiler/controller equivalence.

Authored examples cover [scalar/text values](../examples/config_word_values.kl),
[arrays](../examples/config_word_arrays.kl),
[records](../examples/config_word_records.kl) and
[dynamic variables](../examples/config_word_variables.kl). Linked projects cover
[scalar interfaces](../examples/config_word_interface_project/main.kl) and
[record interfaces](../examples/config_word_record_project/main.kl), with
independent expected snapshots and saved-variable fixtures.
