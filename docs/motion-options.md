# Acceleration, accuracy and timing options

Pythonic MOVE accepts 21 request-local WITH settings. Ten additions retain
acceleration, accuracy, continuous-axis, path and timing intent as checked offline
request data. See [the complete setting table](motion-controls.md) for the other
settings and [termination/orientation choices](extended-motion-settings.md).

```karel
WITH $ACCEL_OVRD=125,$ACCU_NUM=3,$CONTAXISVEL=-25.5,
     $SEG_TIME=40,$TIME_SHIFT=10,$USETIMESHFT=TRUE,
     $CNSTNT_PATH=TRUE,$DYN_I_COMP=FALSE,$USE_CARTACC=TRUE,$USERELACCEL=TRUE
MOVE AWAY 1
```

## Values

| Setting | Accepted Pythonic expression | Retained intent |
| --- | --- | --- |
| `$ACCEL_OVRD` | INTEGER, BYTE or SHORT in 0..500 | Acceleration/deceleration override value; zero stays zero. |
| `$ACCU_NUM` | INTEGER, BYTE or SHORT in 0..10 | Accuracy-area selection; no area is discovered or evaluated. |
| `$SEG_TIME` | INTEGER, BYTE or SHORT in 0..100000 | Segment time in milliseconds, including zero. |
| `$TIME_SHIFT` | INTEGER, BYTE or SHORT in 0..10000 | Local-condition time-shift value in milliseconds. |
| `$CONTAXISVEL` | Finite REAL or integer in -100..100 | Signed continuous-axis speed percentage, saved as a Python float. |
| `$CNSTNT_PATH` | Exact BOOLEAN | Constant-path intent. |
| `$DYN_I_COMP` | Exact BOOLEAN | Dynamic-compensation intent. |
| `$USE_CARTACC` | Exact BOOLEAN | Cartesian acceleration policy intent. |
| `$USERELACCEL` | Exact BOOLEAN | Relative acceleration policy intent. |
| `$USETIMESHFT` | Exact BOOLEAN | Whether the requested time-shift option is enabled. |

These are portable input domains. Numeric truthiness, strings, uninitialized
values, nonfinite numbers and values outside the listed bounds fail explicitly.
The integer bounds are deliberate Pythonic admission choices. No native default,
clamping, installed-option behavior or accuracy-area configuration is inferred.

The FANUC [KAREL reference, MARAIKLRF06031E Rev A, table 12-2](https://www.vicpas.com/file/Fanuc-Teach-Pendant_7066287.pdf)
lists the program-accessible names. The FANUC [software reference,
MARACSSRF03061E Rev G, section 2.7.3](https://studylib.net/doc/27616999/variables-fanuc)
identifies the scalar categories, signed continuous-axis percentage and millisecond
time fields. This implementation uses those categories for authored offline
metadata; it does not establish native compiler/controller behavior.

`$REF_POS` remains unavailable: its name occurs in the KAREL list, but a concrete
motion-setting type/contract has not been established. The similarly named
mastering field is not used to infer one. Other system-variable names remain
outside this local WITH interface.

## Capture and execution

All seven MOVE forms accept the new options. Each setting permits `$NAME`,
`$NAME[group]` or `$GROUP[group].$NAME`. Capture the group expression, then the
value, once in source order before the MOVE operands and local condition captures.
Every explicit group matches the selected MOVE group by default. An explicit
[cross-group opt-in](cross-group-settings.md) allows checked owned metadata on
other groups. All 21 distinct settings may appear per group. Duplicate name/group
pairs, bad domains, ownership, VIA constraints and
script/history limits are checked before publishing a request or consuming a
completion response. Earlier source-expression effects remain visible if a later
check fails.

The options belong to the request. They do not calculate trajectories, apply
acceleration/speed, select accuracy areas, update feedback or mutate RobotContext.
In particular, SEG_TIME and TIME_SHIFT do not change supplied completion delays,
node arrival times or local-handler trigger times. USETIMESHFT remains an intent
flag; an offline timeline continues to use its explicit script.

Immediate NOWAIT, synchronous delayed completion and existing local WHEN/UNTIL
and node/time scopes retain these values. Pause/resume keeps the captured values;
cancellation and terminal cleanup retain their existing ownership rules.
[Delayed NOWAIT](nowait-motion.md) retains these settings, and [NOWAIT local
clauses](nowait-local-clauses.md) add owner-checkpoint observation. Cross-group
execution remains unavailable. A later MOVE starts with its own settings.

## History and reports

Existing JSON history stores ordinary integer, Boolean and floating values with
canonical setting names and selected groups. Loading validates categories,
bounds, duplicate names and group consistency. Older histories remain valid;
request size, history/sequence limits and active-scope save restrictions remain.

`motion_setting_policy` reports the 21-setting maximum, new categories/domains,
metadata-only timing and unresolved REF_POS. Motion requests and their setting
rows retain expanded line/column plus physical source origins and include stacks.
The generated runtime uses the same validation without importing the compiler.

See the [domain example](../examples/motion_option_domains.kl),
[signed speed](../examples/motion_continuous_axis.kl),
[explicit timing](../examples/motion_time_options.kl),
[21-setting example](../examples/motion_twenty_one_settings.kl),
[linked routine](../examples/motion_options_project/lib.kl),
[local temporal handler](../examples/motion_option_handler_project/lib.kl),
[regressions](../tests/test_motion_options.py) and
[semantic ledger](semantics/motion_option_semantics.json). Strict mode remains a
future milestone.
