# Blocking local clauses in motion queues

With a positive MotionRequests queue_limit, a generated blocking MOVE with local
WHEN/UNTIL/THEN clauses can join its selected group's active FIFO. All seven
MOVE forms and VIA support existing Boolean, EVAL and supplied temporal selectors.
The calling source remains inside that MOVE until its own result ends.

```karel
ATTACH
MOVE AWAY 1 NOWAIT
MOVE AWAY 2,
  WHEN AT NODE[0] DO count=1
  WHEN TIME 5 BEFORE NODE[1] DO count=count*10+2
  WHEN AT NODE[1] DO count=count*10+3
ENDMOVE
RELEASE
```

Provide explicit completion responses, durations, a complete node_times schedule
for the second job, and the ordinary GroupLocks bank. With successful delays of
10 and 20 ms, its entry event becomes eligible after the predecessor's ten ms;
the later events use its own twenty-ms supplied timeline.

```sh
python -m karel2py examples/blocking_clauses_temporal.kl -o blocking_clauses_temporal.py
python blocking_clauses_temporal.py --context examples/blocking_clauses_temporal.services.initial.json
```

This is an authored offline model. No robot movement, feedback, inferred arrival,
native queue timing, controller ABI or strict equivalence is claimed.

## Admission, capture and defaults

queue_limit stays an exact INTEGER 0..127. Positive values bound waiting slots
across the service; zero retains busy-group rejection. Full, held or foreign
groups reject instead of implicitly waiting for capacity or ownership.

Capture operands, WITH settings, EVAL and temporal selectors once in source
order. Detach mutable poses and PATH-node operands before waiting. Validate
response/schedule, descriptors, original calling root, exact grant and live
defining frames before publication or reply consumption. A false reply rejects
immediately. Invalid admission leaves its reply untouched; completed argument
effects remain visible.

The extension applies when the selected group is active at admission capture.
An operand routine may complete or cancel its predecessor at a checkpoint before
that capture; the new MOVE then uses existing idle synchronous execution. Idle,
disabled-queue and capture-only behavior remain unchanged. Retranslate old
direct-invoke generated code for queued blocking scopes.

## Waiting and supplied breakpoints

Waiting clauses do not scan or earn progress until FIFO promotion. Observe
promoted clauses only at owning task checkpoints after global handlers. Entry
windows include time zero. One-shot/source-order, false-gate and crossed-event
rules follow the [queued handler policy](queued-motion-clauses.md).

When the active head is a blocking handler job, its wait targets the next future
supplied temporal breakpoint as well as completion, capped at ten milliseconds
and rounded up to whole milliseconds. With an injected exact clock, the example's
BEFORE event can be observed at its supplied 15 ms. NOWAIT predecessors retain
their existing checkpoint observation. Clock-only polling never runs callbacks.
Late host/scheduler samples still use crossed-event windows; this is not a
physical interrupt or an exact native timing promise.

Exclude the job's own action time, holds and task pauses. Retain ordinary
background progress for other groups. A callback-free predecessor may carry
overshoot, while a handler predecessor completes at its owner-observed boundary.
No artificial sleep is added just to scan a promoted zero-duration job.

## Controls, frames and source writes

UNTIL cancels before THEN. Explicit CANCEL finishes its current action list and
skips later clauses. A canceled blocking MOVE returns so source can continue.
Pause/resume retain one-shot state, the action generator and calling frame;
stop/abort, step-budget or host failures retain owned cleanup and completed
predecessor outcomes. Foreign grants and externally stopped labels stay protected.

The defining routine/program remains live while blocked. Borrowed formals retain
caller cells; grouped/private and computed USING values retain independent
storage. Local variables, connected timers and linked calling-root ownership stay
live through pause/resume. A callback cannot outlive the defining frame, and
recursive MOVE actions remain forbidden.

Existing active FOR-counter and transitive predicate/action write checks remain.
After a blocking MOVE ends, its clauses do not remain pending writers against a
later counter. NOWAIT retained-writer protections remain unchanged.

## History and replay

Keep nowait false and the ordinary execution/handler/trigger metadata. Only
checked terminal data, unused responses and queue_limit persist. Saving active
or waiting scopes and loading pending history reject. No callback, wait/action
generator, frame, clock or source continuation is saved or reconstructed.

Reports add motion_blocking_clause_policy. See [blocking waits](synchronous-motion-queues.md),
[queues](queued-motion.md), [local clauses](nowait-local-clauses.md) and the
[semantics ledger](semantics/blocking_motion_clause_semantics.json).
