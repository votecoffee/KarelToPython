# KCL paused-local PATH data edits

Pythonic KCL variable commands now edit existing header/node data in owned PATH
locals and PATH banks of eligible paused routines. The
[local logical-copy policy](kcl-local-collections.md) still supplies frame,
context, ownership, timer and FOR protection. These operations use retained
offline Python frames, without native symbol or controller lookup.

```text
SET LOCAL VAR route.count WORKER = 7
SET LOCAL VAR route[1].value IN stage FROM LIB WORKER = scalar
SET LOCAL VAR bank[2,2][1].numbers[2] WORKER = row
SET LOCAL VAR route[1].pose WORKER = 1,2,3,0,0,0
SET LOCAL VAR route[1].pose.location.x WORKER = 12.5
```

## Values and selection

Static fields and comma/chained indexes select existing header/node storage,
including ordinary data ARRAY rows, user records, poses and joint axes. Named
copies require identical selected schemas and complete selected data. Scalar
STRING sources may have different capacities if their current value fits.
Unselected source fields can remain unknown under the existing partial-data rules.
Sources prefer the selected frame, including readable formals, then module globals;
explicit `[program]` names use global lookup. No conversions or reshaping occur.

Literals use the [existing KCL data formats](kcl-commands.md#pose-recording-and-value-assignment):
checked scalar values and VECTOR/CONFIG/JOINTPOS/Cartesian component lists.
STRINGs must fit without truncation; compact CONFIG flags/turns keep their domains.
SHORT 32767 retains the existing explicit clear convention. Arbitrary ARRAY/user
record literals, expressions, resource fields and FILE copying remain excluded.

POSITION orientation columns and their descendants remain read-only. Complete
pose values, writable location fields, XYZWPREXT external axes and joint axes
use their existing Pythonic data rules, without automatic robot context or
kinematic conversion. Fields require existing containers and nodes. No node is
allocated or nested container inferred by a field edit.

## Admission and private validation

Locate the original selection through bounded metadata. For PATH-bank nodes,
defer NODEDATA copying until admission; other callers retain their earlier checks.
Charge the complete receiver local root and each named source scope before payload
copies. Literals have no source-data charge. Existing 32,767-unit/64-level bounds
and retained task/run/continuation/frame/context/store/metadata checks still apply.
Whole-owner aliases, timers and compiler FOR roots protect unselected siblings too.

After the final charge, resolve current source data and validate the admitted
schemas/counts. Clone the containing logical receiver and stage the edit privately.
Validate all known data in that prepared owner, including unselected siblings,
and check the geometry of every complete POSITION. Partial unselected data remains
explicit. Invalid data, overlong strings, out-of-domain compact fields or bad
complete POSITION geometry reject before live writes.

Only after preparation succeeds, apply the checked value/literal to the original
selected cell or container. Preserve PATH objects, compatible headers, node lists,
node objects and unselected fields. Named values remain independent of their source.
Earlier independent host/checkpoint changes remain visible. This operation does
not replace the entire live PATH just to edit one field.

The existing portable statuses apply: 201 missing task/frame/root, 204 protected
or changed storage, 205 invalid data/schema/literal, and 4 execution budget failure.
KCL_NO_WAIT continues to separate acceptance from completion.

## Inspection, continuation and evidence

Existing SHOW LOCAL VAR paths inspect edited data without changing the owner.
Continuing the paused task reads the same edited cells. Closed JSON can preserve
independent ordinary global results and command history, without saving local
frames, aliases or suspended execution.

The [linked example](../examples/kcl_local_path_data/main.kl) pauses in a library
routine, edits header/node/ARRAY/POSITION data, continues, and observes a mixed-case
label, numeric total, location and independent copied row. Its MAIN DONE guard
supports saved ordinary-data replay; fresh tasks still have fresh execution states.

Reports expose `kcl_local_path_data_policy`. The
[semantic ledger](semantics/kcl_local_path_data_semantics.json) and
[authored regressions](../tests/test_kcl_local_path_data.py) record offline behavior.
Formal/borrowed receivers, readonly orientation fields, implicit discovery,
native/controller equivalence and strict mode remain outside this contract.
