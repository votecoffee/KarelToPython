# Motion-local clauses and scripted progress

Pythonic MOVE requests accept local `WHEN ... DO ...` and
`UNTIL ... [THEN ...]` clauses, terminated by `ENDMOVE`. An explicit scripted
response may also supply a finite `delay_ms`. These features use the existing
[offline request service](motion-requests.md) and logical ownership. They do not
calculate trajectories, infer node arrivals or update robot feedback.

## Local source forms

```karel
MOVE AWAY 1,
  WHEN ready DO CLOSE HAND 1
  UNTIL finished THEN count=count+1
ENDMOVE
```

The comma introduces 1..32 local clauses. WHEN requires an action list; UNTIL
may omit THEN and its actions. Conditions use the existing Pythonic BOOLEAN
expression model, including explicit ports, events, errors, connected timers,
EVAL captures and source functions. Local function predicates are a Pythonic
extension; this is not native compiler acceptance evidence.

Each WHEN or UNTIL is independent and one-shot. Clauses scan in source order;
a satisfied clause disables itself before running its actions. Earlier actions
can affect a later predicate in the same scan. A WHEN action list finishes even
when it cancels the current request; later clauses then stop scanning.

UNTIL first cancels the current group, then executes optional THEN actions.
The source continues after ENDMOVE unless an action pauses, stops, aborts or
fails. Cancellation is recorded as `cancelled`; an action failure is recorded as
`failed`, including a failure in THEN after cancellation.

Local callbacks retain their routine parameters, local storage and captured
USING references. EVAL uses the existing condition-definition capture policy,
after WITH values and MOVE operands have been captured. Active FOR counter
protections still apply to predicates and actions.

Direct MOVE, nested handler definitions, GOTO/labels and RETURN remain forbidden
inside action lists. A routine cannot start another scoped move from a handler.
Ordinary routine calls and cooperative actions retain their normal checked
interfaces. Motion-local handlers do not use or overwrite CONDITION numbers.

## Explicit delayed responses

```json
{
  "motion": {
    "groups": {"1": 2},
    "responses": [
      {"operation": "MOVE AWAY", "completed": true, "delay_ms": 25}
    ]
  },
  "group_locks": {"groups": [1]}
}
```

`delay_ms` is an optional INTEGER in 0..86400000. Missing or zero delay preserves
the immediate-response contract. A false completion response rejects immediately
without sleeping or executing local actions. A missing/mismatched response,
invalid operand or failed ownership check consumes no response and starts no scope.
Completed source-expression effects remain; normal task failure cleanup still
applies.

A positive accepted delay, or any local clauses, creates a synchronous request
scope. It temporarily marks the owned group executing. Global handlers scan
first, then local clauses at entry and after supplied progress steps of at most
10 ms. A zero-duration capture with local clauses scans at its request boundary.
Every progress/poll cycle uses the existing execution budget and task scheduler.

The supplied delay is model input. `elapsed_ms` counts progress steps, excluding
handler action time, pause intervals and hold polling; it is not measured robot
time. An injected sleeper or the deterministic scheduler can exercise progress
without real waiting. The normal standalone sleeper waits for supplied durations.

Local port/event/error consumers are isolated from global handler consumers and
purged with the scope. A global cancellation ends the active request before the
next local scan. No callback or frame survives successful completion or terminal
cleanup.

## Controls, holds and task lifetime

Within a local predicate/action, unqualified HOLD, UNHOLD and CANCEL target that
request's group, including through linked routines. Explicit GROUP selections
retain their existing atomic ownership checks. Outside local callbacks, omitted
GROUP still selects the calling root's owned groups at action time.

An active hold suspends local scans and progress. Global scans and budgeted
10 ms hold polls continue, allowing a global handler to unhold or cancel the
request. Pending task pause/abort requests are honored before the scope can
report completion. A MOVE encountered while already held retains its existing
start rejection; no move is queued.

Source PAUSE and supported task pause requests retain the generator, local frames,
one-shot state, ownership grant and remaining supplied progress. Resume continues them. Stop/abort cancel the scope;
runtime or budget failures mark it failed. Cleanup releases the active request
and its transient executing label while preserving hold flags. Normal terminal
task cleanup releases ownership.

Scopes retain opaque ownership-grant identities. If ownership changes, they fail
without changing another task's motion label. An externally changed work label
also fails the scope; a supplied stopped label is preserved. Native stopped-motion
resume and trajectory recovery are not inferred.

## History, saving and compatibility

Scoped MOVE history adds `execution` containing planned delay, progress, local
kind/line metadata and triggered one-based clause indexes. The request is pending
while active, then becomes completed/captured, cancelled or failed. Its row stays
in normal submission order while action requests append to the existing history
ring. Ring eviction does not end a live scope.

Saving an active motion service is rejected, independently of the existing live
ownership guard. Finish or stop before saving. Persisted data contains no task
frames, callbacks or resumable in-flight scopes. Loading validates metadata,
progress bounds, trigger indexes and outcome consistency; pending history is not
accepted. Unused response scripts retain their optional delays.

Reports extend `motion_request_policy` with local/progress rules and attach local
kind, line and column to affected `motion_requests`. Existing source maps retain
include origins. Old immediate generated output remains usable. Retranslate to
use delayed responses: older direct-invoke output rejects them instead of
silently skipping the delay.

NOWAIT with local clauses is rejected at translation. NOWAIT with a positive
scripted delay is rejected before response consumption. Immediate NOWAIT requests
retain their original capture behavior. Queued motion, native scan timing,
inferred arrivals, trajectory interpolation and native multi-group synchronization
remain unsupported. [Local AT NODE/TIME predicates](motion-timeline.md) now use
complete supplied schedules and exact progress breakpoints.

See the authored [local clauses](../examples/local_motion_handlers.kl),
[delayed progress](../examples/scripted_motion_progress.kl),
[early cancellation](../examples/motion_until_progress.kl) and
[linked routine](../examples/motion_handler_project/main.kl).
