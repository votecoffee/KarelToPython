# Checked REAL-to-integral conversions

Pythonic conversion now accepts finite REAL data for INTEGER, BYTE and SHORT
receivers at explicit source/value boundaries. It uses Python math.trunc:
discard the fractional part toward zero, then validate the receiver's existing
storage domain. This is an authored offline policy, without native KAREL rounding,
compiler acceptance, binary ABI, status-code or controller-equivalence claims.
Public strict mode remains future work.

| Source | Receiver | Result |
| --- | --- | --- |
| 7.9 | INTEGER | 7 |
| -7.9 | INTEGER or SHORT | -7 |
| -0.9 | BYTE | 0 |
| 255.99 | BYTE | 255 |
| 256.0 | BYTE | Range error |
| 32767.9 | SHORT storage | Existing uninitialized marker |
| 2147483647.0 | INTEGER | MAXINT storage error |

The receiver domain is checked after truncation. INTEGER retains
-2147483648..2147483646; BYTE retains 0..255; SHORT retains -32768..32766 plus
32767 as its missing-state convention. There is no wrapping, saturation, nearest
rounding, numeric truthiness or string parsing. NaN, infinity, malformed known
source values and missing scalar reads still fail. No default zero is invented.

## Source and ownership

```karel
VAR source:REAL result:INTEGER
ROUTINE bump(value:INTEGER):INTEGER
BEGIN value=value+1 RETURN value END bump
BEGIN
  source=7.9
  result=bump(source)
END
```

result becomes 8 and source remains 7.9. Ordinary assignments, aliases, nested
fields, ARRAY elements and source function results use the same conversion.
Compatible user/builtin records and matching logical ARRAY layouts recurse over
numeric leaves, retaining receiver schemas, names, dimensions and capacities.
Supplied system-frame/tool CONFIG turn-field writes also apply the conversion
before the existing -8..7 field and complete table-publication checks.

Converted bare routine arguments own private writable cells or containers.
Grouped/computed arguments remain private. Matching bare integral arguments keep
their existing reference behavior. Forwarded exact aliases, retained handlers,
pause/resume, stop and failures refer to the private converted storage; it never
copies back into the REAL caller. Linked calls retain exact declaration/definition
signatures while converting actual source values at the caller boundary.

Capture/conversion finishes before assignment target selectors or later routine
arguments. Complete ARRAY/record data is validated and staged before destination
publication, including late overflow and invalid geometry checks. Earlier completed
source effects remain visible on failure. Scalar SHORT results must be initialized:
returning a value that truncates to 32767 raises before caller assignment, while
assigning it to SHORT storage or passing it privately retains the missing state.

Missing aggregate leaves propagate through conversions under the existing partial
copy rules. Unknown BYTE contents remain distinct. Schema bounds stay at three
logical ARRAY dimensions, 32,767 scalar leaves and 64 data-schema levels; shape
changes, resource-bearing values and inferred robot context remain unavailable.

## GET_VAR and SET_VAR

Both directions support numeric scalars, selected same-rank ARRAY prefixes and
compatible recursive records, including explicit supplied system/foreign bindings.
Only the copied row-major prefix is converted; the receiver tail is retained.
Existing receiver cells and reference identities survive successful publication.

Prepare all selected values before changing data, cache entry or status. Overflow
and malformed known data raise and preserve all three. Incompatible categories
keep status 3. Copied missing source data, including a SHORT result truncated to
32767, produces missing data and status 12311. Missing data outside the copied
prefix does not affect the result. SET captures its input before later status
selectors; GET retains its post-selector named-source snapshot convention.

## Exact interfaces and persistence

Generic checked/integer/value helpers and parameter/reference compatibility are
unchanged. Explicit BYNAME borrowing, linked declared signatures and raw callback
return values remain exact. INTEGER service inputs, indices, device/register
addresses, statuses, FOR bounds/counters and READ parsing do not gain implicit
REAL coercion. JSON/VR schema loading retains its existing typed validation.

Context JSON and portable archives store ordinary numeric values and missing
markers. They do not store conversion plans, retained aliases or suspended frames.
The [authored regressions](../tests/test_real_integral_conversions.py) cover domains,
source order, failures, partial data, private ownership, linked calls, handlers,
pause/stop, explicit frame turns and exact-reference guards.

- [Scalar and private argument](../examples/real_narrow_scalars.kl)
- [ARRAY argument and result](../examples/real_narrow_arrays.kl)
- [Record conversion](../examples/real_narrow_records.kl)
- [Variable prefix and missing state](../examples/real_narrow_variables.kl)
- [Linked ARRAY interface](../examples/real_narrow_project/main.kl)
- [Linked variable transfer](../examples/real_narrow_transfer_project/main.kl)

Reports expose real_integral_policy alongside the existing numeric/record policies.
The [semantic ledger](semantics/real_integral_semantics.json) records these explicit
boundaries. Evidence remains offline.
