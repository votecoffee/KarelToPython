# Pythonic BYTE and SHORT scalars

Pythonic translation accepts `BYTE` and `SHORT` global variables, fresh routine
locals, transparent type aliases, scalar parameters and scalar function results.
They use the existing checked narrow storage domains used by array elements and
structure fields.

These standalone and routine interface forms are deliberate Pythonic extensions.
The KAREL Reference Manual MARRC75KR07091E Rev N, A.2.3 (`BYTE`) and A.19.40
(`SHORT`), describes these types for array and structure members. This feature
does not establish native compiler acceptance, native ABI compatibility or
controller execution. The internal legacy translator keeps its aggregate-only
declaration and interface restrictions; public strict mode remains a future
milestone.

## Storage and expressions

| Type | Initialized values | Initial state | Special behavior |
| --- | --- | --- | --- |
| `BYTE` | 0 through 255 | Unknown BYTE contents | Assign before reading; `UNINIT` remains prohibited |
| `SHORT` | -32768 through 32766 | Uninitialized | Assigning 32767 clears the value; `UNINIT` can inspect storage |

Assignments from integral expressions check the destination range. Arithmetic
promotes narrow operands to ordinary Pythonic numeric values: adding one to 255
produces 256, which an `INTEGER` can hold and a `BYTE` cannot. Narrow values can
promote to `INTEGER` and `REAL`. There is no wrapping, REAL-to-narrow conversion,
or Boolean/string coercion. Out-of-range assignments preserve the previous
destination.

Unknown BYTE contents are distinct from uninitialized SHORT storage. Scalar
reads of either fail; no zero value is invented. Snapshots and typed JSON retain
`{"unknown_byte": true}` and `{"uninitialized": true}` respectively.

## Routine arguments and results

Matching bare storage arguments keep ordinary reference behavior. A `BYTE`
variable passed directly to a `BYTE` formal can be initialized or changed by the
callee, including when its initial contents are unknown. Matching SHORT storage
can similarly be queried, initialized or cleared by the callee.

Grouped/computed arguments have private mutable value cells. An `INTEGER`,
`BYTE` or `SHORT` passed to a different integral narrow formal also gets a
checked private cell, even for a bare variable. The callee cannot change the
caller's variable through that conversion. A conversion checks its range before
later arguments are evaluated; there is no copyback on success or failure.

```karel
PROGRAM NARROW
VAR
  octet: BYTE
  wide: INTEGER
  signed: SHORT
ROUTINE touch(value: BYTE)
BEGIN
  value = 99
END touch
ROUTINE negative: SHORT
BEGIN
  RETURN -11
END negative
BEGIN
  octet = 255
  wide = 7
  touch(wide)       -- wide stays 7: INTEGER-to-BYTE private conversion
  touch(octet)      -- octet becomes 99: matching BYTE reference
  signed = negative()
END NARROW
```

INTEGER 32767 converted to a SHORT formal creates a private uninitialized cell.
That formal can use `UNINIT` and assign a new value; reading it first fails. A
missing SHORT argument already stored in matching bare SHORT storage also stays
a reference. Reading or grouping missing storage still fails before entry.

Scalar BYTE/SHORT function results must be initialized, checked values.
`RETURN 32767` from a SHORT function fails at RETURN, preserving the caller's
assignment destination and unwinding routine frames. Use an exact matching
SHORT output reference when the operation needs to clear caller storage. Earlier
explicit side effects retain the usual failure behavior.

[Narrow FOR counters](narrow-for.md) support BYTE and SHORT alongside INTEGER.
Both bounds must fit the selected counter's initialized domain; BYTE exit restores
unknown contents and SHORT exit restores missing state. Passing an active INTEGER
counter through a private narrow conversion
does not expose that counter to writes by the converted formal, including
transitive calls. Explicit global counter writes and exact reference writes
remain protected.

## FILE, variable services and persistence

Typed text FILE input uses the existing scalar parser and range checks. Binary
FILE input/output uses one unsigned byte for BYTE and two signed bytes for SHORT,
with existing byte-order attributes. SHORT binary 32767 is normalized once when
published to storage. All fields validate before READ publishes destinations or
advances the logical cursor, including when a later field fails.

Finite plain pipes and configured serial streams use the same narrow fields.
Their opt-in cooperative waits retain pending bytes and the original outputs
until a complete READ is available; no host device or live controller is used.

`GET_VAR` supports matching narrow scalar destinations, including unknown BYTE
and missing SHORT state. Its output reference does not silently widen to an
INTEGER. `SET_VAR` keeps existing checked integral conversions and missing-state
status behavior. Context JSON records the scalar type and marker explicitly;
restoring it does not turn unknown or missing contents into initialized values.
[Dynamic narrow CREATE_VAR](dynamic-narrow.md) now creates direct BYTE/SHORT or
supplied transparent aliases with existing initialization and allocation checks.
Builtins that require INTEGER output references still require INTEGER storage,
and whole array interfaces do
not convert their element types.

The translation report records `scalar_narrow_policy`. Authored regression
coverage is in [test_scalar_narrow.py](../tests/test_scalar_narrow.py), with legacy
aggregate and alias regressions retained in the existing test modules. See also
[type aliases](type-aliases.md) and [variable transfers](variable-transfers.md).
