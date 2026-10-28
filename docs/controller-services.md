# Logical controller services

Pythonic translation supports `MOTION_CTL`, `CNCL_STP_MTN`, `SET_PERCH`, `RESET`,
`MIXBG_RUN` and `MIXBG_STOP` through an explicit `ControllerServices` model.
It stores logical data and controls attached cooperative Python tasks. It opens
no controller connection, commands no physical motion and performs no hardware
reset. Native motion statements remain unsupported.

```json
{
  "controller": {
    "perch_counts": {"1": 4},
    "resets": [{"completed": false, "fault": true, "delay_ms": 25}],
    "background": {"1": "WORKER"}
  },
  "group_locks": {"groups": [1], "motion": {"1": "stopped"}},
  "ports": {"counts": {"OPOUT": 3}, "values": {"OPOUT": {"3": true}}}
}
```

All banks, responses and task-slot bindings must be supplied. None is discovered
from hardware or native program configuration. Direct Python construction uses
integer keys, for example `ControllerServices(perch_counts={1:4})`; JSON bank
keys use canonical positive decimal strings.

## Ownership and cancellation

`MOTION_CTL(mask)` checks the existing [GroupLocks bank](group-locks.md). It
returns TRUE only if every selected group belongs to the stable calling task
root. A zero mask returns FALSE. Negative, unrepresentable or unconfigured masks
raise errors. The bank supports groups 1..31, with bit n-1 selecting group n.

`MOTION_CTL()` and bare `MOTION_CTL` use `%LOCKGROUP` as their default selection,
an empty selection for `%NOLOCKGROUP`, or the calling root's selected/default
group otherwise. These directives choose query defaults; they still acquire no
locks automatically. `LOCK_GROUP` remains the explicit acquisition operation.
Nested program/routine calls retain their calling root's ownership.

`CNCL_STP_MTN` or `CNCL_STP_MTN()` changes the caller's owned `stopped` group
labels to `idle`. It retains ownership, executing labels and foreign groups.
Calling it with no owned stopped labels is a no-op. It does not resume motion
statements or imply that physical movement stopped; no motion statements run in
this model. A later logical unlock can succeed after a stopped label is cleared.

## Stored reference positions

`SET_PERCH(joints,tolerance,index)` stores a detached six-axis reference and six
nonnegative finite tolerances. The target group is the calling root's selected
group, using existing `%DEFGROUP`, unique group-declaration or supplied context
selection. Configure that group's capacity in `perch_counts`. Indices are
one-based and must fit that capacity.

JOINTPOS6 or zero-padded JOINTPOS9 values are accepted. Other widths, missing
axes/tolerances, nonzero unused JOINTPOS9 slots, incorrect tolerance-array shape
and negative tolerances fail before changing the bank. The tolerance parameter
requires one-dimensional ARRAY[6] OF REAL. Standard explicit joint conversion
context remains necessary for `CNV_REL_JPOS` used to construct source joints.

The Pythonic bank preserves supplied units. It does not infer native radian/
degree conversion, prismatic-axis units, per-value group annotations or controller
reference-position behavior. It does not change current robot joints, pose or
model frames. Inspect `bank.perches[(group,index)]` or the detached snapshot.
Saved keys have the portable `group:index` form.

## Scripted reset requests

`RESET(successful)` consumes the next configured reset response once accepted.
Each response requires `completed: BOOLEAN`, optional `delay_ms` in 0..86400000,
and an optional `fault: BOOLEAN`. Missing responses fail explicitly.

The documented Boolean output acknowledges the request even when conditions
prevent a controller reset. The model likewise sets it TRUE when the scripted
request finishes, including `completed:false` responses. That output must not
be interpreted as proof that faults cleared. Completion data remains in request
history; a supplied `fault` response updates the explicit `OPOUT[3]` bank value.
That bank/address must exist before the request is accepted. Without a fault
response, no port values change.

Waits use cooperative steps of at most 10 ms, with ordinary task/handler checks.
They create no artificial PAUSE notification. Their accumulated scripted delay
is retained as `elapsed_ms`; this is not controller elapsed time. Only one reset
may be pending. A competing request fails without cancelling or borrowing the
accepted response. Pause/resume retains the same pending request; stop, abort or
budget failure releases it and records cancellation/failure. A consumed response
is never silently returned to the queue or replayed. Unfinished requests do not
publish their optional fault result or Boolean acknowledgement.

## Background task slots

`MIXBG_RUN(slot,status)` and `MIXBG_STOP(slot,status)` require an explicit
`TaskScheduler` and a configured slot-to-task-name mapping. Linked projects
already use that scheduler; standalone host applications must bind cooperative
programs themselves. Target programs must share the execution context.

RUN starts a ready/completed task, resumes a paused task, or acknowledges an
already running task. STOP requests a cooperative pause, retaining its generator,
globals and resources for a later RUN. A RUN can withdraw a still-pending pause.
An idle STOP does not execute the target. Stop requests honor command-pause masks.
Bindings follow the retained task object through renaming, including a completed
task renamed before its next RUN. Foreign contexts, self targets, foreign schedulers,
pending aborts and terminal stopped/aborted/failed tasks are not adopted or revived.

This is the chosen Pythonic equivalent for attached KAREL work. Native TP
background scan scheduling, scan restart semantics, implicit TP loading and
native background-screen state are not implemented. Permanent STOP/ABORT retains
the existing requirement for a fresh execution instance. A caller controls when
and how the attached KAREL body loops; the service does not invent scan loops.

| Portable status | Meaning |
| --- | --- |
| 0 | Accepted request or idempotent no-op |
| 1 | Slot or named task is not configured |
| 2 | Self target or execution-context/scheduler conflict |
| 3 | Terminal task or pending abort requires explicit recovery |
| 4 | Command-pause policy suppresses the stop request |

Indirect background effects conservatively block these two calls in active FOR
scopes, including through routine effects. Masks and statuses are portable,
not asserted native controller encodings.

## Panel I/O and saved state

`OPIN`, `OPOUT`, `TPIN` and `TPOUT` are explicit BOOLEAN port banks. Their
configured count is the maximum address, with indices 0..maximum available.
Other existing port kinds retain addresses 1..maximum. Values, comments,
simulation metadata and explicit modes/assignments round-trip through context
JSON, including panel address zero. Type codes remain caller-supplied.

Missing values remain unknown. Direct input assignments remain rejected by the
compiler. Indirect/form/table writes to inputs require explicit simulation;
logical output writes are allowed. Native channel privileges, key acquisition,
signal routing and panel/system side effects are not inferred. This includes
zero-address form/table port fields and scripted reset fault observations.

Context save retains perch data/capacities, slot names, unconsumed reset responses,
bounded history, finite request IDs and logical delay. It rejects pending reset
requests and live background frames, including paused tasks. Finish or explicitly
stop those tasks before saving; generators, ownership and execution links are
never serialized. History records request order, and pending entries become
terminal in place. Ring eviction can remove an older request's retained row.

Limits are 256 distinct background slots, 4096 stored perches and reset responses,
32 perch groups, six perch axes and a configurable history of 1..4096 rows
(default 500). Perch group capacity is 1..32767. Request and logical-delay counters
are finite. History exhaustion blocks new requests while pending cleanup remains
possible. Constructor/configuration errors are rejected before use.

```sh
python -m karel2py examples/controller_services.kl -o controller_services.py
python controller_services.py --context examples/controller_services.services.initial.json
python -m karel2py examples/perch_storage.kl -o perch_storage.py
python perch_storage.py --joint-axes 6 --context examples/perch_storage.services.initial.json
python -m karel2py.project examples/background_project --entry MAIN --context examples/background_project/services.initial.json
```

Translation reports expose `controller_policy`; the
[semantic ledger](semantics/controller_service_semantics.json) records primary
manual provenance and authored verification. Native controller/servo acceptance,
binary ABI, physical reset and strict equivalence remain future work.
