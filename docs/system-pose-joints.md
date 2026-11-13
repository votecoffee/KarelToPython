# Joint source values for frame and tool tables

Whole source assignments to the four offline frame/tool table forms now accept
complete JOINTPOS values as well as Cartesian poses:

```karel
$MNUFRAME[1,7]=joints
$MNUTOOL[1,8]=joints
$GROUP[1].$UFRAME=joints
$GROUP[1].$UTOOL=joints
```

The translator uses the existing [model-backed assignment](kinematic-assignments.md)
conversion to prepare an independent XYZWPREXT value before evaluating the
destination group and row expressions. Its CONFIG and all three supplied
external-axis values are retained in the published row. Numbered rows may be
populated or repaired; active forms still require an existing selected row.

Conversion uses the **calling root task's group**, its explicit forward model or
adapter, and its selected frame/tool values. The destination group chooses table
storage. It does not select a different conversion model. Linked library code
uses its caller's group, following ordinary joint/Cartesian source assignments.
No current joint snapshot is required for forward conversion of a complete value.

Joint inputs, routine results and array elements are evaluated once. Model inputs
and results are detached. Conversion finishes before destination selectors run;
those selectors still run once from left to right. A failed conversion prevents
selector effects and table publication. A failed selector retains earlier
completed callback effects. Sticky abort prevents publication even when an adapter
catches the abort exception and returns a result.

Active-row lookup occurs after conversion and selector effects. An adapter may
change the active selection through its explicit host context; the table write
then uses that selection. After writing an active frame or tool, later conversions
use its new data. This is ordinary shared-context behavior; the write does not
change selection IDs or supplied current robot state.

The existing complete geometry, CONFIG, width, zero-padding, joint-limit and
table guards apply. A joint value cannot replace a LOCATION, CONFIG_DATA or EXT
field. READ/service outputs and BYNAME gain no live table aliases.
Whole [GET_VAR/SET_VAR system model transfers](system-variable-models.md) now
have their own retained endpoint/output contract. The context's direct
`system_pose_write` host API still requires Cartesian input.

`system_pose_writes` retains the original JOINTPOS source type and adds
`kinematic_conversion` and `stored_type`. `kinematic_assignments` records the
`system_pose` target kind. Runtime observations remain value-free
KINEMATIC_ASSIGNMENT followed by SYSTEM_POSE_WRITE when publication succeeds.
Rows and explicit models use ordinary robot context JSON; callbacks and suspended
execution do not persist.

The [linked example](../examples/system_pose_joint_project/main.kl) converts in
group 2 and stores all four forms in group 1, preserving a supplied external axis.
It checks complete program values and independent robot-table expectations:

```sh
python -m karel2py.project examples/system_pose_joint_project --entry MAIN --context examples/system_pose_joint_project/services.initial.json --state-out joint-tables.json
```

The [semantic ledger](semantics/system_pose_joint_semantics.json) records these
authored Pythonic choices. This feature supplies no native frame/tool calibration,
controller writes, motion, native CONFIG branch selection or strict equivalence.
