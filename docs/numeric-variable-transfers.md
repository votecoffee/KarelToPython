# Numeric GET_VAR and SET_VAR transfers

Pythonic GET_VAR and SET_VAR support checked numeric conversions for individual
scalars and terminal elements of same-rank ARRAY prefix transfers:

| Source | Receiver | Behavior |
| --- | --- | --- |
| INTEGER, BYTE or SHORT | INTEGER, BYTE or SHORT | Validate source domain, then check receiver domain |
| INTEGER, BYTE or SHORT | REAL | Validate source domain and promote to finite Python float |
| REAL | REAL | Existing finite REAL copy |
| REAL | INTEGER, BYTE or SHORT | Incompatible type status 3; use an explicit source conversion |
| BOOLEAN | Numeric, or numeric to BOOLEAN | Incompatible type status 3 |

The [existing variable transfer contract](variable-transfers.md) defines lookup,
reference capture, aliases, missing data, cache IDs and statuses. Both directions
now use the same numeric rules. For example:

```karel
VAR source:ARRAY[2] OF SHORT target:ARRAY[3] OF REAL entry,status:INTEGER
BEGIN
  source[1]=7
  source[2]=8
  target[3]=9
  GET_VAR(entry,'','SOURCE',target,status)
END
```

The resulting target is `[7.0, 8.0, 9.0]`. Outer ARRAY dimensions and names can
differ while logical ranks match. Transfer the smaller row-major terminal
element count, preserving every receiver tail cell. Named nested ARRAY boundaries
contribute to the rank. Whole record identities and joint widths remain exact;
this does not add whole-array positional representation conversion.

## Missing values, domains and atomicity

Missing integral data can clear a compatible REAL receiver and produces status
12311. Partial missing ARRAY leaves propagate through the transferred prefix.
Only copied missing data contributes to that status. SHORT keeps 32767 as its
uninitialized sentinel, including when a valid INTEGER 32767 is narrowed into it.
BYTE unknown contents remain distinct and cannot be promoted into invented
numeric values. An unknown BYTE outside the copied prefix is not read numerically.

Every copied known source value is validated against its declared source type
before conversion. A malformed BYTE 256 cannot become valid REAL data merely
because REAL can represent the number. Receiver bounds and INTEGER MAXINT storage
exclusion remain checked. No rounding, saturation or wrapping is introduced.

Prepare the complete replacement before publishing data, cache entry or status.
A late overflow, invalid source value or unknown-BYTE promotion raises without
publishing any part of the transfer. Type/rank mismatches retain the existing
status-only failure. Successful updates preserve receiver ARRAY and retained
element-reference identities. Earlier argument/selector effects remain visible.

SET input capture still precedes later status selectors. GET still resolves and
snapshots named data after output selectors. Explicit system/foreign bindings,
attached source programs and saved typed context use the same numeric policy.

`numeric_variable_transfer_policy` records these choices. The
[standalone example](../examples/numeric_variable_transfers.kl) demonstrates
promotion, checked narrowing and preserved tails. No controller schema discovery,
native cache/status mapping or strict-mode equivalence is implied.
