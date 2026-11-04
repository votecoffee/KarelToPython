# Pending NOWAIT motion

Pythonic NOWAIT accepts supplied finite response delays and complete node_times
schedules for all seven MOVE forms and VIA. Source execution continues while one
pending request occupies its logical group. This is an authored offline model;
it creates no trajectories, robot feedback updates, physical arrivals, background
threads, native motion queue or controller/compiler equivalence. Strict mode
remains a future milestone.

```karel
ATTACH
MOVE AWAY 1 NOWAIT
count=7
DELAY 30
RELEASE
```

Supply an explicit MotionRequests response with `operation: "MOVE AWAY"`,
`completed: true` and `delay_ms: 25`, plus the ordinary configured GroupLocks bank.
The assignment does not wait for completion. The later delay allows completion
before release. Source without NOWAIT retains its synchronous progress policy.

## Admission and progress

Validate operands, local WITH values, group ownership, response data and the task
clock before publishing the pending request. Values detach before source code can
change them. A second move to a busy group rejects without consuming its response.
Different owned groups can progress independently; this is not a queued batch of
moves or synchronized multi-group interpolation.

The calling root task owns the job, including a MOVE launched in a linked routine
that subsequently returns when the job has no local clauses. [NOWAIT local
WHEN/UNTIL and temporal selectors](nowait-local-clauses.md) now use owner-checkpoint
observation, retaining exact live frames and USING references. Those callback
jobs cancel before their defining routine/invocation ends. Supplied schedules
still require the complete selected range; no node time is inferred from geometry.

Progress observes the root's captured `clock_us` adapter, the scheduler's virtual
clock, or monotonic microseconds when no adapter was supplied. Poll at source
checkpoints, after a successful standalone DELAY and at scheduler boundaries.
Keep sub-millisecond remainders and cap recorded `elapsed_ms` at `delay_ms`.
Completion becomes observable at a poll; it does not run in an operating-system
background thread. Explicit `context.motion.poll()` offers the same observation.

The scheduler observes jobs even while their owner sleeps. Its own clock adapters
provide virtual completion deadlines for fast-forwarding. A custom injected clock
must be advanced explicitly; no relation to scheduler time is inferred. Invalid,
backwards or replaced adapters fail the job. A scheduler poll failure also fails
and cleans the owning task, rather than leaving its wait or grant live.

## Holds, pause and lifetime

HOLD freezes that group's progress. Pending or active task pause freezes all jobs
owned by that task; resume and UNHOLD reanchor the observation so frozen intervals
are excluded. Ordinary source and global handler execution otherwise consume
background clock time. This differs from synchronous local-handler scopes,
whose handler action time is excluded from supplied progress steps. A NOWAIT
job with local clauses also excludes its own callback action time; its supplied
events are observed at owner checkpoints rather than exact synchronous steps.

CANCEL ends an unfinished job immediately and keeps the existing hold/stopped
label protections. A completion already observed at the control boundary remains
completed. RELEASE requires idle groups. Clock or grant failure releases only the
matching active scope; another owner's grant or an externally stopped label is
preserved. Task renaming keeps the same task and ownership identities.

Normal task completion, stop, abort or later runtime failure cancels unfinished
jobs at their last observed progress. A move cannot continue after its owning
program finishes in this offline model. Use source waiting/delays or an explicit
host clock/poll before completion when the job must finish. No native end-of-task
motion, recovery trajectory or stopped-motion resume behavior is inferred.

## History and replay

Terminal history uses the existing `nowait` flag and `data.execution` fields:
planned delay, observed progress and optional supplied schedule. Callback-free
jobs keep empty handlers/triggered indexes; local jobs add the ordinary checked
clause metadata, triggered indexes and captured temporal descriptors. Completed jobs require full supplied progress; canceled
or failed jobs may retain partial progress. False completion responses retain the
existing rejection and consumption policy. Zero-duration scheduled jobs validate
and complete immediately. Immediate NOWAIT calls without a delay/schedule retain
their previous record shape.

Saving any active motion job remains forbidden. Checked terminal local metadata
can load as data; pending history and inconsistent terminal progress remain forbidden.
No clock adapter, active scope or suspended execution is persisted. Retained
history may evict an old row without ending its still-active job.

Old generated direct-invoke output continues to reject delayed responses;
retranslate for this behavior. Existing group/axis, 256-node request, 64 KiB
payload, finite response-script and history-ring limits remain in force.

Authored standalone fixtures may provide `*.clock.initial.json` with a nonnegative
`microseconds` value. The example runner advances that explicit test clock through
its captured DELAY calls; ordinary generated CLI runs retain their default clock
and sleeper. Both paths compare the same final logical data and history.

Reports expose `motion_nowait_policy`. See the [semantics ledger](semantics/nowait_motion_semantics.json),
[regressions](../tests/test_nowait_motion.py), [completion](../examples/nowait_completion.kl),
[axis request](../examples/nowait_axis.kl), [supplied schedule](../examples/nowait_schedule.kl),
[settings](../examples/nowait_settings.kl), [linked launch](../examples/nowait_linked_launch/main.kl)
and [independent groups](../examples/nowait_linked_groups/main.kl).
