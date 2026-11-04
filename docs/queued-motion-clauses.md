# Queued NOWAIT local handlers

With an explicit positive MotionRequests queue_limit, NOWAIT moves with local
WHEN and UNTIL/THEN clauses can join the selected group's FIFO. All seven MOVE
forms and VIA retain the existing Boolean, EVAL and supplied temporal selectors.
A callback-free blocking MOVE may follow and wait for those handler jobs.

```karel
ATTACH
MOVE AWAY 1 NOWAIT
MOVE AWAY 2 NOWAIT,
  WHEN TRUE DO count=count+1
ENDMOVE
MOVE AWAY 3
RELEASE
```

The second job's handler becomes eligible after promotion. The third MOVE keeps
the calling source active until its own result ends. Supply explicit successful
responses and durations, plus the usual GroupLocks bank. Run an authored example:

```sh
python -m karel2py examples/queued_clauses_boolean.kl -o queued_clauses_boolean.py
python queued_clauses_boolean.py --context examples/queued_clauses_boolean.services.initial.json
```

This is an authored offline model. No trajectories, physical arrivals, native
controller queue timing, binary ABI or strict equivalence are inferred.

## Capture and owner observation

Keep ordinary one-time operand, WITH, EVAL and selector capture at admission.
Retain exact live defining frames and named/borrowed/private USING references.
Waiting handlers do not scan or earn elapsed progress. Complete supplied
node_times remain required for AT NODE and TIME BEFORE/AFTER.

After promotion, only the active local head selected at the beginning of each
owning-task checkpoint is scanned, after global handlers. A newly promoted local
successor waits for the next checkpoint. Entry windows include time zero; later
windows include crossed supplied events in source order. False gates do not
replay past events. Event/edge consumers remain separate for each job.

Clock-only motion.poll and foreign task checkpoints never run source callbacks.
A sleeping owner does not execute a local handler at an inferred arrival instant.
No final scan is added at a last DELAY, routine return or root completion. A
blocking barrier supplies owner checkpoints while waiting.

## Progress, controls and bounds

Existing exact INTEGER queue_limit 0..127 still bounds all waiting jobs, shared
across groups. Zero keeps busy-group rejection. Hold, capacity, response,
complete schedule, descriptor and ownership checks precede publication and
reply consumption. Invalid admissions leave the unaccepted reply untouched.

Callback-free predecessor overshoot can advance a promoted handler's supplied
timeline. A handler head itself completes only when the owner observes it, after
excluding its own callback action time. Its successor starts at that observed
boundary; no unobserved callback completion is backdated. Blocking barriers
observe newly promoted entries and zero-duration successors without adding
artificial host sleeps. Scheduler checkpoint time retains its ordinary policy.

WHEN/UNTIL remain one-shot and source ordered. Local unqualified controls target
that job's group. UNTIL cancels before THEN; explicit CANCEL finishes the current
action list and skips later clauses. Canceling the head cancels its unfinished
waiters, while an action/clock/grant failure fails the affected batch. Already
completed predecessors keep their outcomes. Holds and task pauses freeze work;
pause/resume retain suspended actions. Other groups remain independent.

## Defining-frame lifetime and write protection

A queued callback's defining routine or program invocation must remain live.
Leaving it before promotion cancels just that unstarted job and frees its slot;
its live predecessor and other waiters remain. Leaving an active callback's
defining frame cancels that active group's remaining batch. Root completion,
stop or abort cancels unfinished owned work. Private USING values may survive
lexical ENDUSING within a still-live defining invocation.

Check active and queued task/frame/grant/clock identities before and after clock
observations, including injected clock side effects. Failures cannot relabel a
foreign grant or externally stopped work. Nested frame names cannot redirect a
capture. Borrowed formals retain caller cells; grouped values remain private.

Existing direct, transitive, predicate, service-output and retained-reference
proofs still protect complete FOR-counter roots against pending NOWAIT writes.
Queueing does not weaken those checks. Direct/nested MOVE, nested handlers, GOTO
and RETURN remain forbidden in local action lists. Blocking MOVE local clauses
still cannot join busy queues; callbacks cannot outlive their defining frames.

## Reports and saved data

Reports add motion_queue_clause_policy. Terminal history retains ordinary local
metadata, supplied timelines, triggered indexes and outcomes. Unstarted expired
jobs retain zero progress and no triggers. Active/waiting saves and pending reload
remain forbidden. No callback, frame, clock, queue scope or action/wait generator
is persisted or reconstructed during JSON loading.

See [NOWAIT clauses](nowait-local-clauses.md), [queues](queued-motion.md),
[blocking waits](synchronous-motion-queues.md) and the
[semantics ledger](semantics/queued_motion_clause_semantics.json).
