# Bounded NOWAIT motion queues

Pythonic motion can retain a finite FIFO of callback-free NOWAIT requests for
each owned group. Enable this explicitly with MotionRequests queue_limit; zero
is the default. This authored offline model consumes supplied completion replies
and durations. It does not compute trajectories, infer node arrivals, update
robot feedback or reproduce controller queue timing. Strict mode remains future.

```python
from karel2py.runtime import ExecutionContext, GroupLocks, MotionRequests

context = ExecutionContext(
    group_locks=GroupLocks([1]),
    motion=MotionRequests({1: 2}, queue_limit=8, responses=[
        {"operation": "MOVE AWAY", "completed": True, "delay_ms": 10},
        {"operation": "MOVE AXIS", "completed": True, "delay_ms": 20},
    ]),
)
```

The corresponding service JSON uses "queue_limit": 8 inside "motion". All
seven MOVE forms and Cartesian VIA can join callback-free queues:

```karel
ATTACH
MOVE AWAY 1 NOWAIT
MOVE AXIS 2 BY 90 NOWAIT
DELAY 100
RELEASE
```

Source execution continues after both admissions. The second request starts
after the first supplied ten milliseconds complete. Its own twenty milliseconds
start at promotion, rather than admission. The final delay permits the whole
batch to complete before RELEASE. Run an authored example through the CLI:

```sh
python -m karel2py examples/queued_motion_fifo.kl -o queued_motion_fifo.py
python queued_motion_fifo.py --context examples/queued_motion_fifo.services.initial.json
```

## Admission and bounds

queue_limit must be an exact INTEGER in 0..127. It bounds all waiting requests
in the MotionRequests service, shared across groups; active heads are excluded.
Each group has one active head and a separate FIFO. Different groups progress
independently, without synchronized interpolation. Completing a head frees one
waiting slot when the next request starts. The existing history ring may evict
a live request's row without dropping its scope or waiting slot.

Both the active head and the new waiter must be newly generated, callback-free
NOWAIT scopes, owned by the same calling root task and exact logical ownership
grant. Synchronous moves, old direct-invoke output and local WHEN/UNTIL callbacks
cannot join a busy group. Local callback heads remain usable on their own under
the existing defining-frame rules. Retranslate old generated code for queueing.

Capture operands and WITH settings once at admission, detaching mutable poses
and PATH nodes. Validate data, group/hold/grant, capacity, response, complete node
schedule and clock before publishing history or consuming the next reply. Queue-enabled
admission shares one captured clock sample with head polling, preventing a second
read from crediting a new job with time before its predecessor completed.
Waiting requests reserve and consume their replies at admission. A false reply
rejects immediately under the existing scripted rejection policy; it is not a
deferred failure at promotion. Invalid/full admissions leave the unaccepted
reply untouched. Source expression effects already completed remain visible.

## Progress and controls

Only the head earns observed active clock time. Waiting requests keep zero
elapsed_ms until promotion. A late poll can complete several requests using the
same captured clock sample, carrying observed overshoot through supplied
boundaries. Sub-millisecond remainders survive promotion; zero-duration waiters
still keep FIFO order. No extra sleeps or background threads are created.

HOLD and task pause freeze the head, and therefore its FIFO. UNHOLD/resume
exclude frozen intervals. New moves reject while held. Scheduler-owned clocks
retain head completion deadlines and can progress the queue while its owner
waits; custom clocks still require explicit advancement. Stable adapter and
monotonic sample checks retain the existing failure behavior.

CANCEL ends the active head and every waiter for each selected group. Already
completed requests stay completed; hold flags and stopped-label protections
remain. RELEASE requires the complete selected batch to be idle and unheld.
Normal root completion, stop, abort or failure cancels unfinished owned batches.
Linked callback-free launches retain root lifetime after the routine returns.
Clock/grant failures fail the head and its waiters, preserving another owner's
grant or an externally stopped work label.

## History and saved state

Admitted requests use existing pending history and execution fields; enabled
queues give even immediate NOWAIT moves explicit execution metadata. Terminal
rows retain supplied delays/schedules and observed elapsed progress. Unstarted
canceled/failed waiters retain zero progress. No callback or trajectory executes
during load.

Positive queue_limit persists with unused replies and checked terminal history.
Disabled limits are omitted, preserving old default configurations. Saving any
active or waiting request rejects. Pending history cannot reload. Queue scopes,
clocks, owners, frames and suspended execution are never persisted.

See [pending motion](nowait-motion.md), [local clauses](nowait-local-clauses.md)
and the [semantics ledger](semantics/queued_motion_semantics.json).
