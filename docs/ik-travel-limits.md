# Inverse-kinematics travel limits

The Pythonic standard-DH solver bounds each proposed joint update in that row's
units. Revolute rows default to 10 degrees per update; prismatic rows default to
100 millimetres. Earlier versions used 10 for both types, which could exhaust
the iteration budget on a long linear move within the supplied joint limits.

Each DH row can override its update cap with `ik_step_limit`, a positive finite
number in degrees or millimetres. For example, this supplied offline linear
model can solve a 5000 mm target from zero within eight iterations:

```json
{
  "robot": {
    "dh": [{"type": "prismatic", "min": -10000, "max": 10000,
            "ik_step_limit": 1000}],
    "iterations": 8,
    "current": {"joints": {"type": ["JOINTPOS", 1], "value": [0.0]}}
  }
}
```

The solver applies one common scale to the proposed update, chosen so every
free joint fits its own cap. Line-search reductions can make that update smaller.
This retains the proposed direction for mixed revolute/prismatic chains. Fixed
external joints and rows with equal minimum/maximum limits do not restrict the
scale. Joint limits still clamp each trial. The cap is a numerical search
setting, rather than speed, acceleration or a physical motion command.

Set `ik_step_limit` to 10 on prismatic rows to retain the earlier search cap.
Changing a cap may change convergence and the first solution found. A larger
cap is not a guarantee of convergence. Invalid values, including zero,
negative numbers, BOOLEANs, strings, NaN and infinity, reject model loading.

The same solver serves POS2JOINT, model-backed source/routine/ARRAY/record
conversions, GET_VAR/SET_VAR, IN_RANGE and CHECK_EPOS. Every model evaluation
still charges the source execution budget. Per-seed iteration bounds, supplied
fallback order, fixed external values and failure-preserving publication remain
active. Forward geometry, current joints and frame/tool selections are unchanged
by this setting. Explicit settings survive ordinary context JSON round trips.

The [authored example](../examples/ik_long_travel.kl) checks source assignment,
explicit inverse conversion, variable transfers and reachability against a
supplied linear model. It stores rounded distances for stable expected output;
the solver itself returns finite floating-point joint values.

```sh
python -m karel2py examples/ik_long_travel.kl -o linear.py --report linear-report.json
python linear.py --context examples/ik_long_travel.services.initial.json --state-out linear-state.json
```

Reports expose `kinematic_assignment_policy.inverse_steps`. The
[semantic ledger](semantics/ik_travel_limit_semantics.json) records these authored
numerical choices. They provide no robot calibration, native CONFIG branch
selection, collision checking or controller reachability certification. Failure
to find a solution remains inconclusive. Strict mode is a future milestone.
