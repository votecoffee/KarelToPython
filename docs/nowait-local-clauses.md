# NOWAIT local motion clauses

Pythonic NOWAIT accepts local WHEN and UNTIL/THEN clauses on all seven MOVE forms
and VIA. Source continues while the job owns its group. Clauses scan at admission
and at the owning task's cooperative checkpoints after global handlers. Clock
polling, host sleeps and foreign tasks do not execute local callbacks.

```karel
ATTACH
MOVE AWAY 1 NOWAIT,
  WHEN ready DO count=count+1
  UNTIL finished THEN count=count+10
ENDMOVE
ready=TRUE
DELAY 40
RELEASE
```

Supply the existing explicit offline MotionRequests response and GroupLocks
configuration. This extension supplies no trajectories, physical hand movement,
robot feedback, native interrupts or compiler/controller equivalence. Strict
mode remains future work.

## Observation and temporal windows

Each clause is one-shot and source ordered. Actions of an earlier satisfied
clause can affect a later predicate in that scan. UNTIL cancels the current group
before THEN. Explicit CANCEL finishes its current action list and stops later
clauses. Unqualified local controls keep targeting that request's group.

AT NODE and TIME BEFORE/AFTER require complete supplied node_times, using the
existing selected-node, start-node-zero and wildcard rules. A temporal selector
is eligible if a supplied event lies after the previous scan and at or before
the current observed elapsed time. The entry window includes time zero. Events
crossed during one delay are eligible together in source order, even when their
supplied times differ. A false Boolean gate does not replay a past event on a
later scan; a later wildcard event can still qualify.

This is checkpoint observation. A delay or cooperative wait is not interrupted
to execute a clause at an inferred physical instant. History records observed
elapsed time, capped at the supplied duration. Synchronous moves keep their
existing exact supplied breakpoints. Explicit motion.poll updates progress but
never executes callbacks; a completed supplied timeline with local clauses
remains active until an owner checkpoint observes it.

There is no implicit final callback scan after a last DELAY, automatic return or
task completion. Use a following source checkpoint, such as RELEASE or an
assignment, when completion must be observed before leaving the scope. Scheduler
deadlines do not spin at a fully elapsed job waiting for owner observation.

## Captures, lifetime and controls

Operands, WITH values, EVAL and temporal selectors retain their one-time capture
rules. Local callbacks use the exact saved defining frames and USING references;
an inner routine with the same variable names cannot redirect them. Bare exact
formals borrow caller cells; grouped/private values keep independent cells.

Unfinished jobs with local callbacks cancel before their defining routine or
program invocation exits, including early return, failure and linked call exit.
Captured private USING data can survive lexical ENDUSING within that invocation.
Callbacks cannot extend a finished routine's lifetime. Jobs without callbacks
retain their existing root-task lifetime across linked routine return.

Each job excludes its own callback action time, holds and task pauses from
background progress. Other jobs retain their separate clocks and progress.
Pause/resume retains action generators and one-shot state. Stop/abort cancels;
action/budget failures mark the job failed, including THEN failures after UNTIL.
Pending pause/abort requests are honored before a job can report completion.

Only matching ownership grants and registrations can release an executing label.
Task/frame identity is checked before admission and after injected clock calls;
stale cleanup cannot relabel a replacement request. Global cancellation precedes
local scanning. Direct/nested MOVE, nested handlers, GOTO and RETURN stay forbidden
in local action lists.

## Effects, reports and saved data

Pending local predicate/action writes also protect later FOR counters on the
complete root. Direct, transitive, service-output, timer and retained-reference
guards keep their existing rules. This is a source proof, not a controller lock
against independent host mutation.

Reports add motion_nowait_clause_policy and per-request callback_observation and
callback_lifetime. Terminal history stores checked local metadata and triggered
indexes. Active jobs cannot be saved. JSON reload reconstructs data only, without
callbacks, frames, clocks, ownership grants or suspended actions.

See the [semantics ledger](semantics/nowait_clauses_semantics.json),
[regressions](../tests/test_nowait_clauses.py), [Boolean clauses](../examples/nowait_clauses_boolean.kl),
[temporal observation](../examples/nowait_clauses_temporal.kl),
[private captures](../examples/nowait_clauses_private.kl), [axis motion](../examples/nowait_clauses_axis.kl),
[live linked routine](../examples/nowait_clauses_linked/main.kl) and
[linked UNTIL](../examples/nowait_clauses_until/main.kl).
