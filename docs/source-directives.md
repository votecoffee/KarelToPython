# Pythonic source directives

Since 0.68.0, Pythonic mode accepts a small set of top-level directives as
syntax-checked metadata. This lets otherwise supported code retain its environment
requirements and program attributes when translated.

```karel
PROGRAM DIRECTIVES
%COMMENT = 'Can''t -- &sort' -- real trailing comment
%ENVIRONMENT STRNG
%ENVIRONMENT SYSTEM
%ALPHABETIZE
%NOLOCKGROUP
VAR z,a,total: INTEGER
BEGIN
  CNV_STR_INT('7',z)
  a=3
  total=z+a
  WRITE('total=',total::0,CR)
END DIRECTIVES
```

This finishes with `Z=7`, `A=3`, `TOTAL=10`, in declaration order, and records
`total= 10` followed by a newline. The generated `Program.source_directives` is:

```python
(
    ('%COMMENT', "Can't -- &sort"),
    ('%ENVIRONMENT', 'STRNG'),
    ('%ENVIRONMENT', 'SYSTEM'),
    ('%ALPHABETIZE', None),
    ('%NOLOCKGROUP', None),
)
```

The [authored example](../examples/pythonic_directives.kl) also calls a helper
routine. Its [snapshot](../examples/pythonic_directives.expected.json) and
[output](../examples/pythonic_directives.write.expected.json) are independent fixtures.

## Accepted forms

Directives are case-insensitive, run through the end of their physical line,
and are accepted after `PROGRAM` and before the program body. Real trailing `--`
comments are accepted.
An ampersand outside a quoted payload and before a trailing comment remains an
unsupported directive continuation.

| Directive | Pythonic behavior |
| --- | --- |
| `%ENVIRONMENT name` | Record a required facility name, normalized to uppercase. |
| `%COMMENT = 'text'` | Record the decoded program comment without changing runtime state. |
| `%ALPHABETIZE` | Record the request to display static variables alphabetically. Offline storage and snapshots keep declaration order. |
| `%NOLOCKGROUP` | Retain the existing offline metadata behavior without acquiring task/group ownership. |

An environment name must start with an ASCII letter, then contain only ASCII
letters, digits or underscores, with at most 36 characters. Custom names and
repeated declarations are preserved. This is an explicit portable identifier
subset: quoted filenames, extensions, paths, assignments and lists are rejected.

COMMENT accepts one single-quoted ASCII literal of at most 16 decoded characters,
including an empty literal. Doubled apostrophes decode to one apostrophe; `--`
and `&` inside the literal remain data. COMMENT must precede CONST, TYPE, VAR and
routine declarations. Duplicate COMMENT attributes are rejected because this
translator does not choose a native precedence rule. ALPHABETIZE and NOLOCKGROUP
accept no arguments. ENVIRONMENT and ALPHABETIZE may appear between top-level
declaration sections; directives inside routines or executable blocks remain blocked.

## Environment requirements and reports

Native ENVIRONMENT declarations select translator definition files. Here they
record requirements only. Translation does not load files or modules, import
definitions, grant extra built-ins, or infer controller facilities. Every source
symbol, type and call still has to satisfy the implemented language subset. A
supported built-in works with or without an ENVIRONMENT declaration; this offline
policy does not reproduce native environment visibility or default-file rules.

The report retains raw directive text, physical lines and dispositions in
`directives`. `directive_metadata` adds normalized names, decoded arguments,
physical line/column and dispositions in source order. `directive_policy` describes
the chosen behavior and lists unique `required_environments` in first-use order.
Generated modules retain immutable `(name, argument)` pairs in
`Program.source_directives`, available with the small standalone runtime too.
Changing report dictionaries does not change generated metadata.

Malformed supported forms produce `E_DIRECTIVE_SYNTAX` or `E_DIRECTIVE_VALUE`;
late or duplicate COMMENT attributes produce `E_DIRECTIVE_POSITION` or
`E_DIRECTIVE_DUPLICATE`. Unknown and unimplemented directives retain `E_DIRECTIVE`.

## Evidence boundary

The reviewed [reference edition](references.md), one-based PDF pages 310,
343-344 and 387-388, describes alphabetical static-variable display, COMMENT's
length/header placement and ENVIRONMENT definition loading. Metadata preservation,
the portable name subset, duplicate policy and unchanged offline storage order
are explicit implementation choices.

Persistence, scheduling, task/group behavior, device defaults and INCLUDE still
need runtime mappings. Their directives remain blocked. There is no native
environment loading, controller attribute write or controller validation.
Strict mode remains a future milestone and retains its previous internal directive
restrictions.
