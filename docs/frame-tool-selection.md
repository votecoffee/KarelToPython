# Active frame and tool selection

Pythonic mode supports INTEGER reads and dedicated assignments for
`$MNUFRAMENUM[group]` and `$MNUTOOLNUM[group]`. They use the existing explicit
RobotContext active frame/tool selections. The source names are documented in the
[FANUC KAREL reference](https://www.mroelectric.com/static/app/product/pdfs/A05B-2518-C204-EMH.pdf).
The behavior below is this application's portable offline contract.

```karel
VAR frame_id,tool_id:INTEGER
BEGIN
  frame_id=$MNUFRAMENUM[1]
  tool_id=$MNUTOOLNUM[1]
  $MNUFRAMENUM[1]=2
  $MNUTOOLNUM[1]=3
```

[Explicit robot system transfers](system-variable-transfers.md) now also read
and set these IDs through bounded GET_VAR/SET_VAR paths in an explicit system
namespace. They return values and create no writable system aliases.

## Validation and capture

Both reads and assignments require an explicit robot context/group, an ordinary
frame/tool dictionary and a complete valid Cartesian row for the selected number.
IDs use the existing portable range 0..32767. Missing groups/rows, uninitialized
values, invalid geometry and noninteger IDs fail before selection changes. Zero
is usable only when its row is configured, including an existing model's identity
row. No missing row, frame, tool or model is inferred.

A read evaluates its group once and returns an independent INTEGER value. Routine
arguments use private value storage. Assignments capture the RHS before evaluating
the group, evaluate each expression once and publish one active ID after complete
validation. Earlier ordinary expression effects remain on a later failure. Failed
selection leaves active IDs and table entries unchanged.

These values cannot supply writable READ/service references, FOR counters,
connected timer storage or generic system-variable discovery. Unknown dollar roots,
extra indexes and descendant selection fields remain rejected. Setting one group's
frame or tool leaves other groups, the other selection and table data unchanged.

## Integration and saved state

Selection uses the same active rows as the existing `$GROUP[g].$UFRAME/$UTOOL`
value views and [dedicated table writes](system-pose-writes.md). This completes the
offline workflow: supply or edit a row, select it, then read/use that selected row.
Source-linked routines and handler predicates/actions share these context values.

Existing model-backed CURPOS, joint/Cartesian assignments and reachability checks
use the changed selection. Explicit frame/tool operands on other conversion calls
retain their own behavior. No physical motion or current joint/Cartesian feedback
snapshot is changed by selecting a frame or tool. Explicit fixed Cartesian current
snapshots keep their existing supplied-snapshot interpretation.

RobotContext JSON already stores the latest selections alongside its tables and
model settings. Saved-context replay retains them without restoring callbacks or
suspended execution. The examples reset their intended selections explicitly, so
replaying a saved result produces the same program and robot-table expectations.

## Boundaries and observations

This implementation reuses the existing offline selection coupling. It does not
implement native special meanings for frame/tool numbers, implicit KAREL/TP frame
copying, system-variable discovery, controller writes or hardware feedback. A
number such as 62 or 30 is an ordinary row ID only if that row is supplied; it does
not select an inferred alternate environment. Strict equivalence remains future
work.

`system_selections` report rows identify reads/writes, locations, private values
and capture order. `frame_selection_policy` states the validation, integration and
persistence rules. Runtime SYSTEM_SELECTION_READ/WRITE observations contain only
operation, source line and outcome. Errors retain normal source-line handling.

Authored examples cover [number values](../examples/frame_tool_selection.kl),
[frame row editing](../examples/frame_selection_pose.kl),
[tool row editing](../examples/tool_selection_pose.kl) and
[explicit-model transforms](../examples/frame_selection_model.kl). Two linked
projects cover routine and handler use. Complete robot-table fixtures and CLI
JSON replay checks accompany them. See the
[semantic ledger](semantics/frame_selection_semantics.json).
