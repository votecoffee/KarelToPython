# Blocking MOVE after queued work

With an explicitly enabled MotionRequests queue_limit, a newly generated,
blocking MOVE, including [local clauses](blocking-motion-clauses.md), can join its selected group's active FIFO. Source
execution waits for that exact request's supplied terminal result. All seven
MOVE forms and Cartesian VIA use the same policy.

```karel
ATTACH
MOVE AWAY 1 NOWAIT
MOVE AXIS 2 BY 90
RELEASE
```

Given explicit successful responses with delay_ms 10 and 20, the second MOVE
waits for the first ten milliseconds, then its own twenty milliseconds. RELEASE
can follow without an extra source DELAY. A zero-duration second response still
waits for its predecessors. Its history row retains nowait false and ordinary
execution metadata, without creating a new serialized wait type.

```sh
python -m karel2py examples/sync_motion_fifo.kl -o sync_motion_fifo.py
python sync_motion_fifo.py --context examples/sync_motion_fifo.services.initial.json
```

This is an authored offline extension. Supplied replies and root task clocks
define progress; no physical movement, feedback, inferred arrival, controller
queue timing or strict equivalence is claimed.

## Admission and source capture

queue_limit remains an exact INTEGER 0..127 and bounds waiting slots across the
service. Zero keeps busy-group rejection. A blocking waiter consumes a normal
waiting slot; a full queue rejects instead of implicitly waiting for capacity.
Held groups, foreign owners and invalid/lost grants also reject before admission.

Evaluate operands and WITH settings once, in the existing source order, before
waiting. Poses and selected PATH nodes detach before handlers can alter source
storage. Validate data, complete supplied node schedule, response, stable clock,
capacity and ownership before publication or consumption. Reserve the reply at
admission. A false reply rejects immediately, and an invalid admission leaves its
reply untouched. Already completed argument effects remain visible.

The blocking waiter must be generated and belong to the same calling root and
exact logical group grant as the head. [Queued NOWAIT handlers](queued-motion-clauses.md)
may precede it and scan at owner checkpoints during the wait. [Blocking local
WHEN/UNTIL and temporal clauses](blocking-motion-clauses.md) now use the same live
frame boundary, with supplied-breakpoint targeting for blocking handler heads.
Old direct-invoke generated output must be retranslated for blocking waits.

## Waiting, controls and lifetime

Waiting progress remains zero until FIFO promotion. The source cooperates at
checkpoints and sleeps at most ten milliseconds or the remaining head interval,
rounding up fractional milliseconds. Eligible timed conditions can wake the
waiting task earlier. Observe global handlers and task control while waiting. Supplied root-clock
progress, sub-millisecond remainders and scheduler completion deadlines retain
the [queue policy](queued-motion.md).

HOLD and pending/active task pause freeze the active head and its waiters.
UNHOLD/resume exclude frozen intervals. Global handler time counts as ordinary
background progress unless held/paused; standalone synchronous local-handler
progress keeps its existing separate policy. CANCEL cancels the selected batch,
and a canceled blocking MOVE returns so source may continue. Completed
predecessors remain completed.

Stop, abort, step-budget and host failures retain owned cleanup. A failed terminal
result raises; an idle label, missing admitted scope or replaced ownership grant
cannot satisfy the wait. Grant/clock failures preserve foreign owners and stopped
labels. RELEASE still requires idle, unheld groups.

The caller remains inside the defining routine/program until its own waiter ends.
Local parameters, captured references and connected timers stay live through
ordinary pause/resume. Linked calls retain calling-root ownership and their
originating source names. Other groups keep progressing independently; waiting
for one group does not become a global completion barrier.

## Defaults and saved state

An idle synchronous MOVE retains its existing immediate or supplied-step
execution, including local clauses. This extension applies when the selected
group has an active scope at admission capture and queue_limit is positive.
Capture-only endpoints remain immediate. No new context option is required.

Saving active/waiting scopes still rejects. Only checked terminal history,
unused replies and queue_limit persist. Wait generators, clocks, owners, live
routine frames and source continuations cannot be saved or restored. Generated
scripts and linked projects can replay completed, guarded examples from JSON.

See the [semantics ledger](semantics/synchronous_motion_queue_semantics.json).
