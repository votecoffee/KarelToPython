# Offline frame and tool table writes

Pythonic mode now accepts dedicated assignments to the four existing system pose
forms: `$MNUFRAME[group,number]`, `$MNUTOOL[group,number]`,
`$GROUP[group].$UFRAME` and `$GROUP[group].$UTOOL`. They edit supplied offline
RobotContext tables. Source reads still return independent POSITION snapshots;
READ, service outputs and routine arguments do not gain writable table aliases.

```karel
VAR a:XYZWPR
BEGIN
  a=$MNUFRAME[1,2]
  a.x=30
  $MNUFRAME[1,7]=a
  $GROUP[1].$UTOOL.location.x=40
  $MNUFRAME[1,7].config_data.cfg_turn_no1=7
```

[Explicit robot system transfers](system-variable-transfers.md) now add bounded
GET_VAR/SET_VAR paths, including retained whole-row external axes and checked
extended-axis fields. Direct source values and writable-alias boundaries below
retain their existing contracts.

## Targets and values

Whole assignments accept complete POSITION, XYZWPR or XYZWPREXT records. The
stored row keeps the supplied representation and external-axis values. The source
value is detached: changing it after assignment leaves the table unchanged.
POSITION basis, finite numeric and CONFIG domain checks apply before publication.
Joint values require an explicit Cartesian conversion first.

Field writes support LOCATION as a VECTOR, LOCATION.X/Y/Z as REAL cells,
CONFIG_DATA as a CONFIG record, and its individual turn/Boolean fields. They stage
an independent copy of the existing complete row, apply the checked edit, validate
the complete result and replace one table entry. Representation, orientation and
external-axis values not selected by the edit are preserved. POSITION NORMAL,
ORIENT and APPROACH remain read-only source fields; whole proper-pose replacement
is available when orientation must change.

## Capture and publication

The right-hand value is captured before group and number expressions. Selectors
then run once, left to right. Earlier ordinary source effects remain if a later
selector or value check fails. Active-row selection occurs after selector effects,
using the supplied group's current active frame/tool number. No callback, pause or
writable reference is introduced during final table validation and publication.

An explicit RobotContext and group are required. Numbered whole writes may
populate a row in its ordinary frame/tool dictionary; numbers are 0..32767. Active
writes require an existing selected row. Field writes require an existing complete
row. A failed edit leaves the previous table entry unchanged. Whole replacement
can repair an invalid existing row when a complete valid source pose is supplied.
Active selection IDs and the robot's current pose/joints are not changed by a table
write. Cartesian table updates do not invoke kinematic or reachability callbacks.

## Persistence and boundaries

Existing RobotContext JSON stores published rows, representations, external axes
and selections, including explicit overrides of a model's default identity row.
It still stores no callbacks, suspended execution or controller connection. Model
and frame/tool-only contexts use the same serialization rules as before.

This extension creates no live system-variable aliases. Generic GET_VAR/SET_VAR
and BYNAME discovery is unchanged. READ/service outputs, direct orientation-column
writes, unknown dollar roots and automatic joint conversion remain unavailable.
[Active ID assignments](frame-tool-selection.md) use a separate checked selection
operation. The existing POSITION read view does not expose external-axis
metadata; supplied XYZWPREXT whole values and the saved table retain those axes.
Native table storage, controller writes, physical robot behavior and strict-mode
equivalence are outside this offline contract.

`system_pose_writes` records target paths, source type, source locations and capture
policy. `system_pose_write_policy` states publication and persistence boundaries.
Runtime SYSTEM_POSE_WRITE observations contain operation, source line and outcome,
without pose payloads. Existing source-line error handling applies.

The four authored examples cover [whole rows](../examples/system_pose_write_frame.kl),
[fields](../examples/system_pose_write_fields.kl),
[external axes](../examples/system_pose_write_extended.kl) and
[active rows](../examples/system_pose_write_active.kl). Linked routine and handler
projects include complete expected program state and independent robot-table
fixtures. The example runner checks optional `robot.expected.json` fixtures;
CLI acceptance also verifies saved-context replay without GUI or network imports.
See the [semantic ledger](semantics/system_pose_write_semantics.json).
