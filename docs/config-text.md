# Pythonic CONFIG text

Since 0.67.0, Pythonic mode supports `CNV_STR_CONF(source,target,status)` and
`CNV_CONF_STR(source,target)` as portable CONFIG text conversions. They let
programs construct complete CONFIG values for [POS](pos-construction.md).

`CNV_CNF_STRG` adds status-bearing formatting using supplied per-group field
profiles. See [group CONFIG text](group-config-text.md) for its context, group
selection and failure contract.

```karel
PROGRAM CONFIG_TEXT
VAR cfg: CONFIG pose: XYZWPR code: INTEGER text: STRING[40]
BEGIN
  CNV_STR_CONF('N U T, 0, 0, 0',cfg,code)
  IF code=0 THEN
    pose=POS(.1,2,3,10,-20,30,cfg)
    CNV_CONF_STR(cfg,text)
    WRITE(text,CR)
  ENDIF
END CONFIG_TEXT
```

This sets `code=0`, creates an independent pose and writes
`N R U T, 0, 0, 0` followed by a newline.
The [authored example](../examples/pythonic_config_text.kl) also exercises
reference formals and invalid-input preservation. Its
[snapshot](../examples/pythonic_config_text.expected.json) and
[output](../examples/pythonic_config_text.write.expected.json) are independent fixtures.

## Portable grammar

Input is ASCII, case-insensitive and limited to 254 characters. A nonempty flag
section can use any order, with optional whitespace between letters:

| Pair | False | True | CONFIG field |
| --- | --- | --- | --- |
| Wrist | N | F | CFG_FLIP |
| Shoulder | R | L | CFG_LEFT |
| Elbow | D | U | CFG_UP |
| Front/back | B | T | CFG_FRONT |

Use at most one letter from each pair. Unknown letters, duplicates and conflicting
pairs are invalid. Compact `FLUT` and spaced `F L U T` both work. Omitted flags
become false as an explicit portable data choice; this does not infer robot defaults.

The flag section may be followed by exactly three comma-separated decimal turn
numbers, each in -8..7. Signs, leading zeros, surrounding whitespace and Python
decimal underscores are accepted. Without the comma section, all turns become
zero. For example, `N U T` supplies false FLIP/LEFT, true UP/FRONT and zero turns.
`F L U T, -8, 0, 7` explicitly supplies all fields.

`CNV_CONF_STR` emits every field in a chosen fixed order: wrist, shoulder, elbow,
front/back, then the three turns. It separates flags with spaces and turns with
comma-space. Thus parsing and formatting `tulf,-8,7,-1` yields
`F L U T, -8, 7, -1`. This preserves all seven fields without a robot-specific mask.
Formatted text can be parsed back into an equivalent independent CONFIG.

## Status and output handling

`CNV_STR_CONF` writes status 0 on success. Invalid grammar or turn ranges write
the portable status 1 (`runtime.CONFIG_TEXT_INVALID`) and leave the target CONFIG
unchanged, including its initialization state. This value is a project convention,
not an authenticated native controller error code.

The target can be a CONFIG variable, field, ARRAY element or reference formal.
A successful conversion initializes all seven leaves while preserving captured
references to its storage. CONFIG and status outputs must be ordinary writable
references and must not overlap. Status requires exact INTEGER storage; CONFIG
scalar subfields remain blocked as output aliases.

Formatting requires a fully initialized CONFIG with the exact field layout,
strict BOOLEAN flags and turns in -8..7. The output requires concrete STRING
capacity sufficient for the complete text. A capacity failure raises
`KarelRuntimeError` without truncating or changing the output. STRING reference
formals use their caller's capacity; value formals retain their private capacity.

Type, storage-shape, ASCII and 254-character input guard failures also raise
without conversion output writes. They do not become status 1. The two procedures
do not clear unrelated state or invent a partial CONFIG on failure.

## Evaluation and reports

Arguments evaluate once in source order: source, target, then status when present.
Formatting snapshots and validates its CONFIG source before evaluating the target,
so later target-index functions cannot change the captured source value. Output
types, shapes and overlap are checked before writes. Earlier argument effects
remain on error; ordinary local-frame and FOR cleanup applies.

Both parsing outputs participate in direct and transitive write analysis. Calls
that could write an active FOR counter are rejected. The procedures are fallbacks:
explicit internal routines with the same names retain their own signatures,
results and effects. Strict mode retains the earlier unsupported-call behavior.

Reports expose source-located `config_text_conversions` and the chosen
`config_text_policy`. User routines with these names are not conversion sites.

## Evidence boundary

The reviewed [reference edition](references.md), PDF pages 145-146, 338, 341 and
347, describes the flag categories, CONFIG fields and conversion signatures.
Robot configuration validity depends on controller-specific context. Accepted
grammar, omitted values, canonical order, portable failure status and guarded
failure behavior here are explicit offline choices. There is no robot/group mask,
native status/alarm mapping, controller acceptance or reachability claim.
Group-specific `CNV_CNF_STRG` uses the separate explicit-profile contract above.
Strict mode remains future work.
