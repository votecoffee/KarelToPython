# Offline motion and hand requests

Pythonic output translates the seven basic `MOVE` forms into an explicit
`ExecutionContext.motion` service. `MotionRequests` validates and snapshots
operands, checks logical ownership and records what the source requested. It
does not calculate trajectories, drive a robot, change `RobotState` feedback,
perform reachability checks or map hands to physical signals.

| Source form | Captured data |
| --- | --- |
| `MOVE TO point [VIA point] [NOWAIT]` | Complete POSITION, XYZWPR, XYZWPREXT or exact configured-width JOINTPOS destination; optional Cartesian via point. A direct `path[index]` destination extracts NODE_POS. |
| `MOVE NEAR point BY distance [NOWAIT]` | Complete Cartesian point and finite numeric distance. |
| `MOVE AWAY distance [NOWAIT]` | Finite numeric distance. |
| `MOVE ABOUT vector BY angle [NOWAIT]` | Complete VECTOR and finite numeric angle. |
| `MOVE AXIS axis BY distance [NOWAIT]` | One-based INTEGER axis within the explicit group width and finite distance. |
| `MOVE RELATIVE offset [NOWAIT]` | Complete VECTOR or Cartesian pose offset; no implicit kinematics. |
| `MOVE ALONG path [NOWAIT]` | Complete positional NODE_POS values for all selected nodes. |
| `MOVE ALONG path[start]` / `path[start..end]` | Inclusive forward range, ending at the final node when end is omitted. NOWAIT is also accepted. |
| `OPEN HAND number`, `CLOSE HAND number`, `RELAX HAND number` | Update an explicitly configured logical hand, numbered 1 or 2. These are also accepted global handler actions. |
| `ATTACH`, `RELEASE` | Acquire or release checked logical group ownership. |
| `HOLD`, `UNHOLD`, `CANCEL` with optional GROUP selectors | Update owned logical labels/hold flags; see [motion controls](motion-controls.md). |
| `WITH` before MOVE | Capture six supported local settings, without applying a native environment; see [local settings](motion-controls.md#temporary-with-settings). |

Source operands are evaluated once from left to right and detached before the
next operand is evaluated. PATH storage is captured before its range expressions;
only selected NODE_POS values must be initialized. Other node/header data does
not participate. Distances and angles remain request data: the service does not
derive destinations, infer units for unknown axes or apply native interpolation
and motion-environment settings.

## Configure execution explicitly

This authored capture-only context uses a six-axis group and two logical hands:

```json
{
  "motion": {
    "groups": {"1": 6},
    "hands": {"1": "relaxed", "2": "open"},
    "capture_only": true
  },
  "group_locks": {"groups": [1]}
}
```

```karel
PROGRAM REQUEST_DEMO
BEGIN
  ATTACH
  OPEN HAND 1
  MOVE AXIS 2 BY 15 NOWAIT
  CLOSE HAND 1
  RELEASE
END REQUEST_DEMO
```

Use the existing CLI and generated script options:

```console
python -m karel2py request_demo.kl -o request_demo.py --report request_demo.report.json
python request_demo.py --context context.json --state-out results.json
```

Missing services, unowned groups and unknown hands fail at the source statement.
Alternatively, acquire groups with LOCK_GROUP or opt into GroupLocks directive
application. A MOVE requires ownership of the selected source group, an idle
logical motion label and no hold flag. Group and axis configuration is supplied, never discovered.

ATTACH selects the module's explicit LOCKGROUP list, or all configured motion
groups when no list exists. After RELEASE, ATTACH reacquires the exact previous
selection. RELEASE checks every owned group before changing any ownership;
another task's grant is never removed. Busy or conflicting groups fail atomically.
Root completion, stop, abort and failure clear released-task bindings, including
nested calls. Ownership remains with the calling task across linked routines and
CALL_PROG. The history records both task owner and source module.

## Captures and scripted completions

`capture_only: true` records moves with outcome `captured`, allowing the Python
source to continue without claiming completion. Logical ownership and hand
operations record `completed` for their offline state changes.

With `capture_only: false` (the default), supply a finite ordered response list:

```json
{
  "groups": {"1": 6},
  "responses": [
    {"operation": "MOVE AXIS", "completed": true},
    {"operation": "MOVE AWAY", "completed": false}
  ]
}
```

Each MOVE must match the next response. Missing or mismatched responses fail
without consuming it. A valid false response is consumed, records `rejected`
and raises a source-located runtime error. A true response records `completed`
for that explicitly supplied offline result. Operand, ownership and capacity
validation precede response consumption and history publication.

Responses have zero modeled duration by default. An explicit finite `delay_ms`
adds [cooperative progress and optional local clauses](motion-handlers.md).
NOWAIT remains limited to immediate requests; there is no background motion
queue or interpolation model. Scripted results are supplied offline data.

## Persistence, reports and bounds

Context JSON retains group widths, hand values, capture mode, unused responses
and a bounded history of detached request data. Live released-task bindings
cannot be serialized: reattach, finish or stop the task first. GroupLocks also
retains its existing live-owner save guard. Persisted history is validated when
restored; no execution or host callbacks run during loading.

The translation report provides `motion_requests` and `motion_request_policy`,
including source locations, one-time capture, ownership rules and the explicit
controller-validation boundary. Normal source maps retain include origins.

- Groups 1..31, explicit widths 1..9, configured hands 1..2.
- At most 4096 scripted responses and 128 retained history entries.
- MOVE ALONG requires a named PATH, 1..256 selected nodes and forward in-range
  indexes. Its nodes need a positional NODE_POS field; no associations are inferred.
- Each request payload is limited to 64 KiB of canonical compact JSON, independently
  of the node bound. Sequence numbers stop at 2147483646.
- NOWAIT/local-clause combinations, unsupplied arrival times, remaining WITH settings and cross-group options,
  native group synchronization, hand-signal routing and controller timing remain
  unsupported. Supported [logical controls and six WITH values](motion-controls.md)
  retain the offline contract. [Boolean local clauses and scripted progress](motion-handlers.md)
  add synchronous request scopes. Unsupported source forms reject before execution.

See the authored [motion requests](../examples/motion_requests.kl),
[scripted motion](../examples/scripted_motion.kl),
[hand lifecycle](../examples/hand_requests.kl) and
[linked project](../examples/motion_request_project/main.kl).
