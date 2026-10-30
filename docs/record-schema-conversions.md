# Source STRUCTURE and record ARRAY conversions

Pythonic source assignments, ordinary routine arguments and RETURN values can
convert user STRUCTURE schemas that contain compatible context-free data.
[Model-backed record conversion](kinematic-records.md) separately extends these
source boundaries through joint/Cartesian fields under explicit robot context.
Records must have exactly the same field-name set. Fields match by name, in the
receiver's declared order; record names and field order may differ. Matching
record ARRAY terminals follow these rules recursively across named components.

~~~karel
TYPE input_t=STRUCTURE count:INTEGER label:STRING[8] ENDSTRUCTURE
     output_t=STRUCTURE label:STRING[3] count:REAL ENDSTRUCTURE
VAR original:input_t result:output_t
BEGIN
  original.count=7 original.label='abcdefgh'
  result=original
END
~~~

result owns LABEL='abc' and COUNT=7.0. original retains its own schema and data.
This is an offline Pythonic extension with no native structure layout, external
ABI or controller-equivalence claim. Public strict mode remains future work.

## Compatible fields

| Field pair | Conversion |
| --- | --- |
| Identical supported data schemas | Independent copy, preserving missing scalar leaves |
| Different user STRUCTURE names/order | Recursively map the identical field-name set |
| INTEGER/BYTE/SHORT family | Check source domain and receiver range |
| Integral family to REAL | Practical Python float promotion |
| Bounded STRING capacities | Validate source ASCII/capacity, then right-truncate or widen |
| ARRAY schemas | Match every logical dimension; rebuild receiver names and flat/nested components |
| POSITION/XYZWPR/XYZWPREXT | Existing complete context-free Cartesian representation rules |
| JOINTPOS widths | Complete values; zero-pad or discard only zero trailing axes |

Nested records and arrays retain their declared receiver schemas. ARRAY rank is
one through three. The existing 32767-scalar-leaf and 64-schema-level limits
apply to the entire captured value and converted output before allocation.
Different record ARRAY terminal schemas may also convert at a whole-ARRAY source
boundary. No equal-count reshape, resize, axis reorder or ragged storage is added.

## Validation and publication

The generated call validates the declared source schema and original data before
conversion. A malformed known leaf cannot be hidden by truncation or promotion.
The RHS evaluates once and captures an independent value before resolving an
assignment target or evaluating the next argument. Conversion validates all
output leaves before publication; failure keeps the destination intact while
retaining any earlier independent source effects.

Missing scalar leaves remain missing. Exact BYTE copies preserve unknown BYTE
contents; numeric extraction still rejects them. SHORT sentinel normalization
follows ordinary partial-data copy rules. Representation-changing pose/joint
fields must be complete; same-type partial pose/joint copies need no model.
POSITION orientation columns remain recursively read-only.

Assignment preserves existing receiver and child storage so captured references
remain attached. Bare generic ARRAY assignments use the actual borrowed receiver
schema; no dynamic caller-scope lookup or extra selector evaluation is introduced.

## Arguments, results and linkage

An already compatible ordinary reference argument keeps its existing alias.
A schema-changing argument receives private writable data without copy-back.
Exact forwarding and retained handlers may alias that private data; pause/resume,
stop, abort, failures and timer cleanup do not publish it back to its source.
Converted data cannot bypass protections on an exact borrowed FOR counter.

RETURN prepares its independent declared schema before frame, counter and timer
cleanup. Matching source-linked routines and explicit callbacks can receive
converted actual arguments. Linked declarations/definitions themselves, raw
callback results, BYNAME and generic checked/value/result helpers still require
their existing exact schemas. A raw callback cannot claim to return one record
and supply another nominal record for automatic coercion.

Typed JSON stores the resulting schemas and data. It does not serialize private
cells, live handlers, timers, callbacks or suspended execution. The DONE guards
in the authored examples allow deterministic data replay.

## Variable storage transfers

[GET_VAR/SET_VAR record transfers](record-variable-transfers.md) separately apply
compatible context-free field schemas to explicit variable storage and record
ARRAY prefixes. They retain their own missing-container, cache and status rules.

## Remaining exclusions

Field additions, removal and renaming, builtin-record/user-STRUCTURE interchange,
resource fields, BOOLEAN/numeric changes and implicit REAL-to-integral conversion
remain excluded. Model-backed JOINT/Cartesian changes inside records and nested
arrays now use the separate [explicit-model source policy](kinematic-records.md).
The context-free convert_record_schema helper still never invokes robot services.

Reports expose record_schema_conversions with boundary, location, original and
target schemas and ownership evidence, plus record_schema_policy. See the
[semantic ledger](semantics/record_schema_conversion_semantics.json),
[regressions](../tests/test_record_schema_conversions.py),
[field example](../examples/record_schema_fields.kl),
[nested example](../examples/record_schema_nested.kl),
[geometry example](../examples/record_schema_geometry.kl),
[lifetime example](../examples/record_schema_lifetime.kl),
[linked routine](../examples/record_schema_project/main.kl) and
[generic record ARRAY receiver](../examples/record_array_receiver_project/main.kl).
