# Deceleration and acceleration intent

Pythonic MOVE accepts eleven request-local WITH settings. `$DECELTOL` and
`$USEMAXACCEL` add checked deceleration/acceleration intent to the
[existing settings](extended-motion-settings.md).

```karel
WITH $GROUP[1].$DECELTOL=50, $USEMAXACCEL=TRUE
MOVE AWAY 10
```

| Setting | Pythonic value | Meaning retained in history |
| --- | --- | --- |
| `$DECELTOL` | INTEGER, BYTE or SHORT expression in 0..99 | 1..99 retains percentage intent; zero records unspecified configured-default intent. |
| `$USEMAXACCEL` | Exact BOOLEAN expression | Request to use the fast-acceleration policy. |

The reviewed R-J3iB KAREL Reference Manual, Rev A, PDF pages 220 and 324,
describes the deceleration percentages and lists both settings for program use.
The SYSTEM R-J2 KAREL Reference Manual, Version 4.30/4.31, PDF pages 177 and
456, describes TRUE for fast acceleration and a zero deceleration default.
The bounded INTEGER domain and treatment of zero here are explicit Pythonic
choices. Native fallback for out-of-range percentages is unresolved; such values
fail before request publication. Zero remains metadata because no configured
native default is discovered.

Capture each explicit group expression and value once, left-to-right, before
MOVE operands and local condition captures. Accept `$NAME`, `$NAME[group]` and
`$GROUP[group].$NAME`; every explicit group must match the selected MOVE group.
Duplicate names, wrong categories and invalid values fail before MOVE publication
or script consumption. Earlier completed source-expression effects remain.

Remaining WITH names from the reviewed table are `$ACCEL_OVRD`, `$ACCU_NUM`,
`$CNSTNT_PATH`, `$CONTAXISVEL`, `$DYN_I_COMP`, `$REF_POS`, `$SEG_TIME`,
`$TIME_SHIFT`, `$USE_CARTACC`, `$USERELACCEL` and `$USETIMESHFT`. Their typed
offline contracts remain unimplemented.

All seven MOVE forms accept these settings alongside the other nine. Immediate
NOWAIT, local WHEN/UNTIL, supplied finite delays and node/time schedules keep the
same checked metadata. Pause/resume retains captured values. Cancellation,
ABORT, errors and budget exhaustion keep the existing scope/ownership cleanup.
Delayed NOWAIT and cross-group settings remain outside the model.

The values affect request history only. They neither calculate a trajectory nor
change a supplied completion delay, arrival schedule, robot feedback, frame/tool
context or acceleration profile. A later MOVE has its own settings. JSON stores
ordinary INTEGER/BOOLEAN values and validates their exact domains on restore;
older histories remain valid. Reports add `deceleration` and `acceleration` to
`motion_setting_policy`, with an eleven-setting maximum.

See the [intent example](../examples/motion_deceleration_intents.kl),
[eleven-setting example](../examples/motion_eleven_settings.kl),
[linked routine](../examples/motion_deceleration_project/lib.kl),
[regressions](../tests/test_motion_deceleration_settings.py) and
[ledger](semantics/motion_deceleration_semantics.json). Evidence is authored
translation and offline execution; native compiler/controller acceptance remains
unverified. Strict mode remains a future milestone.
