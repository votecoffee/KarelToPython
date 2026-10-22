# Pythonic position comparisons

Since 0.74.0, `a >=< b` compares complete POSITION or XYZWPR values, including
mixed operands, and returns BOOLEAN. Supply explicit comparison tolerances when
creating the generated Program. No controller defaults are inferred.

```karel
PROGRAM POSITION_COMPARISONS
VAR cfg: CONFIG code: INTEGER p: POSITION origin,nearby,far: XYZWPR near,far_ok,same_rotation,config_ok: BOOLEAN
BEGIN
  CNV_STR_CONF('N R U T, 0, 0, 0',cfg,code)
  origin=POS(10,20,30,0,0,0,cfg)
  p=origin
  nearby=POS(10.03,20.04,30,0,0,0.25,cfg)
  near=p>=<nearby
  far=POS(10.2,20,30,0,0,0,cfg)
  far_ok=origin>=<far
  far=origin
  far.r=360
  same_rotation=origin>=<far
  far.config_data.cfg_left=TRUE
  config_ok=origin>=<far
  WRITE('near=',near,', far=',far_ok,CR)
  WRITE('rotation=',same_rotation,', config=',config_ok,CR)
END POSITION_COMPARISONS
```

With `Program(pose_tolerance=(0.1, 0.5, True))`, the first comparison accepts
0.05 mm and 0.25 degrees of separation. The 0.2 mm location difference fails.
A full 360-degree turn is the same rotation; changing CONFIG then fails the
last comparison. Recorded text is `near= TRUE, far= FALSE` and
`rotation= TRUE, config= FALSE`, each followed by a newline.

The [authored example](../examples/pythonic_position_comparisons.kl) adds environment
metadata and includes independent complete
[snapshot](../examples/pythonic_position_comparisons.expected.json),
[text](../examples/pythonic_position_comparisons.write.expected.json) and
[host context](../examples/pythonic_position_comparisons.context.expected.json) fixtures.

## Host context and generated scripts

`pose_tolerance=(location_mm, orientation_deg, check_config)` is runtime context:

| Component | Meaning | Accepted values |
| --- | --- | --- |
| `location_mm` | Maximum Euclidean distance between locations. | Finite nonnegative INTEGER/float. |
| `orientation_deg` | Maximum shortest angle between rotations. | Finite INTEGER/float in 0..180 degrees. |
| `check_config` | Require every CONFIG field to match when true. | Exact Python `bool`. |

A list or tuple with exactly three components is copied to an immutable tuple.
`Program.pose_tolerance` exposes that tuple through a read-only property. Contexts
belong to individual instances; nested programs do not replace each other's values.
Invalid supplied context raises `ValueError` during construction. Omitted context
raises a source-located `KarelRuntimeError` when a comparison executes. A skipped
short-circuit expression does not need context.

Translate normally, then pass all three choices to the generated script:

```sh
python -m karel2py examples/pythonic_position_comparisons.kl -o converted.py
python converted.py --location-tolerance-mm 0.1 --orientation-tolerance-deg 0.5 --check-config
```

Use `--ignore-config` instead of `--check-config` to ignore CONFIG differences.
The two flags are mutually exclusive and one is required. Bounds and configuration
choice are required whenever a generated script contains this operator, including
inside a routine. READ and joint-axis context options can be combined with these
options. Invalid bounds are usage errors. Runtime tolerance values do not alter
the translation-context hash, like the existing runtime `joint_axes` context.

## Metrics, validation and effects

Both limits are inclusive, with no relative tolerance. Location uses
`math.dist`. Orientation uses `D = transpose(Ra) Rb`, where the rotations follow
the existing [POSITION/XYZWPR conventions](position-geometry.md). The shortest
angle is `degrees(atan2(s, c))`, where `s` is half the norm of the three skew
differences of D and `c` is `(trace(D)-1)/2` clamped to -1..1. This retains small
angles near both zero and 180 degrees. Equivalent Euler representations compare
as rotations; this is not a per-component W/P/R comparison.

All arithmetic uses rounded Python floats. Complete initialized, finite and exact
pose shapes and valid CONFIG fields are required even when CONFIG differences
are ignored. POSITION matrices retain the proper-matrix checks and `1e-9` absolute
tolerance from frame geometry. Non-finite derived distances raise an error.
Exact pose equality and ordered pose relations remain unsupported.

Operands evaluate once from left to right. Each is validated and copied before
later effects. Both complete poses are checked before comparing, so a large
location difference cannot hide invalid orientation or configuration. Context
is checked after the operands. Failure preserves earlier effects and the existing
assignment destination, while skipping target expressions. Ordinary routine,
FOR-counter, cleanup and Boolean short-circuit rules apply.

Reports expose source-located `position_comparisons` with body, operand types,
BOOLEAN result and capture flags. `position_comparison_policy` records the context,
metrics, CONFIG choice and limits.

## Evidence boundary

The reviewed [reference edition](references.md), one-based PDF pages 82-83,
describes approximate POSITION comparison and its relationship to `$LOCTOL`,
`$ORIENTTOL` and `$CHECKCONFIG`. The explicit host tuple, XYZWPR acceptance,
distance/rotation metrics, field-by-field CONFIG check and numeric bounds are
portable Pythonic choices. Source system-variable access is still unsupported.

Since 0.80.0, XYZWPREXT comparisons use explicit `external_tolerance` values
(scalar or three axes), with inclusive absolute difference limits. Plain poses
supply zero external values in mixed comparisons. See
[extended pose setup](portable-projects.md#robot-models-and-extended-poses).
JOINTPOS uses supplied forward context under [joint geometry](joint-geometry.md)
and the same explicit Cartesian/external tolerances. VECTOR and scalar operands
remain blocked. Controller context and native metric equivalence remain
unverified. Strict mode remains a future milestone.
