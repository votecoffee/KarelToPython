# Statement-only ARRAY row and plane targets

Explicit live BYNAME row/plane arguments follow the separate
[live-reference policy](array-prefix-references.md). Ordinary values and
statement captures retain the ownership described here.

Pythonic assignment and READ can now select an existing row or plane inside a
flat multidimensional ARRAY. This is an authored extension with explicit capture
and publication rules. It does not establish native source-form, storage-layout
or controller equivalence. Strict mode remains a future milestone.

```karel
VAR matrix:ARRAY[2,2]OF INTEGER row:ARRAY[2]OF INTEGER
-- Inside BEGIN:
row[1]=7 row[2]=9
matrix[1]=row
READ(matrix[2]::2::16,CR)
```

The assignment copies into the original first-row cells. The READ expands the
second row into ordinary scalar input destinations; text `0A0F` followed by LF
produces values 10 and 15. The source row remains independent of both rows.
See the [assignment example](../examples/array_prefix_target_values.kl) and
[typed callback example](../examples/array_prefix_target_input.kl).

## Captured storage, without a live view

| Selection | Statement target |
| --- | --- |
| `matrix[i]` | Its original one-dimensional row cells |
| `cube[i]` | Its original two-dimensional plane cells |
| `cube[i,j]` or `cube[i][j]` | Its original row cells |
| Prefix inside a named flat component | Its original remaining component cells |
| Flat generic formal over named caller rows | The caller's actual suffix schema and original cells |

Complete adjacent chains still normalize before typing. Complete elements and
prefixes ending exactly before a named component retain their existing reference
behavior. Ordinary prefix arguments remain independent [source values](array-prefix-values.md),
even when passed to a routine that writes its parameter.

The runtime captures a private statement target rather than exposing a generic
Reference or ARRAY view. Runtime indexed-reference helpers and general service
output parameters keep their complete-reference contracts. Explicit BYNAME data
prefixes use the separate live-reference interface.
Separate [GET_VAR/SET_VAR prefix transfers](prefix-variable-transfers.md) now
accept named data selections, SET input copies and GET data-output captures. No view
or selection is stored in context JSON.

## Assignment order and publication

Prefix assignment has this explicit receiver-schema policy:

1. Evaluate and validate an independent copy of the right-hand data.
2. Evaluate the target base, then all target indexes once from left to right.
3. Validate the concrete receiver and capture its original suffix cells.
4. Convert the saved source against the captured actual receiver schema.
5. Validate every selected destination and publish without intervening callbacks
   or checkpoints.

Conversion follows target capture so generic formals can honor their actual
caller layout, names and STRING capacities. This ordering is specific to prefix
assignment; complete assignment receivers retain their existing conversion order.
An explicit model adapter therefore runs after prefix index effects. An invalid
right-hand value skips target effects. A conversion failure leaves selected
outputs unchanged while retaining completed index/adapter effects.

Existing numeric, bounded STRING, record, positional and explicit-model ARRAY
conversions apply. No reshape, implicit REAL-to-integral conversion or inferred
robot context is added. Compatible missing scalar leaves and unknown BYTE data
retain their existing copy rules. Missing containers and malformed known data
reject. Capture validates the entire receiver ARRAY, including unselected data.

Publication preserves ordinary selected scalar references and nested ARRAY,
record and joint identities. A previously captured alias observes the new value.
The target does not retarget itself if a later adapter changes an index or
replaces the declared root; captured old cells retain ordinary alias lifetime.
Malformed captured storage rejects before prefix publication.

## READ and cooperative transports

READ captures all selected original scalar references before evaluating that
item's formats. Later index/format functions cannot redirect them. Existing
whole-data flattening handles record declaration order, row-major ARRAY order,
joint axes and source CR offsets. Uniform controls retain each scalar's format
domain; typed callback/JSON responses remain flat decoded values.

Validate the complete response before publishing scalar outputs. Repeated cells
retain source order with the last validated value winning. Callback errors,
CONFIG turn errors, cancellation and late malformed input preserve ordinary
atomic output rules. Cursor/buffer consumption follows the existing transport
contract; this extension adds no universal rewind of external input effects.

Text/binary FILEs, explicitly rooted files, supplied serial streams, waiting
serial/pipe input and injected keyboard FILE input reuse their scalar transports.
Waiting reads retain the selected row through host feeds, pauses and cancellation.
See the [binary example](../examples/array_prefix_target_binary.kl),
[serial example](../examples/array_prefix_target_serial.kl),
[linked transfer](../examples/array_prefix_target_project/main.kl) and
[linked cancellation](../examples/array_prefix_target_cancel_project/main.kl).

## Guards, reports and persistence

Whole-root active FOR checks still cover prefix writes and READ. POSITION
orientation protection, CONFIG domains, constants, exact resource exclusions and
existing cooperative cleanup remain unchanged. POSITION data can be copied by
assignment; [whole POSITION input](position-input.md) now validates complete
position cohorts inside prefix READ targets. Computed/function
READ roots and general service prefix outputs remain unavailable. Explicit BYNAME
borrowing uses the live-reference policy. GET_VAR
data-output prefixes follow the separate variable-transfer contract above.

Existing bounds remain three logical dimensions, 32767 source/receiver scalar
leaves, 64 schema levels and 1024 expanded READ destinations plus CR. Saved JSON
contains ordinary data and logical services, without captured targets or paused
execution. Authored examples have a completion flag for exact saved-state replay.

`array_prefix_target_policy` describes this contract. Source-located
`array_prefix_targets` lists suffix schemas, supplied index counts and
`independent_value=false`; source prefix values keep their separate observations.
See the [regressions](../tests/test_array_prefix_targets.py) and
[semantic ledger](semantics/array_prefix_target_semantics.json).
