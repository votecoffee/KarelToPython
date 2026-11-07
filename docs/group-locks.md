# Logical motion-group ownership

Pythonic `LOCK_GROUP(mask,status)` and `UNLOCK_GROUP(mask,status)` use an
explicit offline `GroupLocks` bank. They model task ownership labels and
contention, without commanding motion or acquiring controller locks.

Configure the groups explicitly:

```python
from karel2py.runtime import ExecutionContext, GroupLocks

context = ExecutionContext(group_locks=GroupLocks([1, 2, 3]))
```

The equivalent context JSON field is:

```json
{
  "group_locks": {
    "groups": [1, 2, 3],
    "motion": {"3": "stopped"}
  }
}
```

Groups are distinct integers in 1..31. Bit n-1 selects group n: mask 1 selects
group 1, mask 4 selects group 3, and mask 5 selects both. A zero mask is a
successful no-op. A negative mask or any bit outside the configured groups
returns status 1 before changing ownership. An absent bank raises; source
directives, robot axes and hardware do not supply one implicitly.

## Ownership and partial results

The default calls complete immediately and may change part of the selected mask.
Ownership belongs to the stable calling task root. Nested program calls and
linked routines use the same owner; task renaming preserves it. Re-locking an
owned group is idempotent. A lock request acquires each available selected group
even if another selected group belongs to another task, matching the manual's
partial acquisition rule.

Unlock releases the calling task's idle groups. Foreign ownership and supplied
busy labels retain their respective groups, while eligible groups release. The
status reports the first blocked group in ascending group order. This partial
unlock ordering is a chosen offline policy.

| Status | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Invalid or unconfigured mask |
| 2 | Selected group belongs to another task |
| 17039 | Owned group has executing work or an idle hold flag |
| 17040 | Owned group has a stopped motion label |

Executing/stopped codes retain their documented conditions; applying 17039 to
an idle held group is an explicit offline extension. The motion
labels are caller-supplied evidence, not simulated or observed robot movement.
The host can change a label with `bank.set_motion(group,'idle')`, `'executing'`
or `'stopped'`. An unspecified label is idle. A separate [hold flag](motion-controls.md)
can block new requests without changing that label. The separate
[controller service](controller-services.md)
now lets CNCL_STP_MTN clear only the caller-owned stopped labels, and MOTION_CTL
query explicit/default group selection. These have no physical motion effects.

## Bounded acquisition and release

Set either wait limit in the explicit bank configuration.

~~~json
{
  "group_locks": {
    "groups": [1, 2, 3],
    "lock_wait_ms": 100,
    "unlock_wait_ms": 50
  }
}
~~~

Each limit accepts an INTEGER in 0 through 86400000 milliseconds. Zero is the
default immediate policy described above. A positive limit applies to newly
translated source calls and checks the whole mask before any acquisition or
release. Invalid and empty masks return their usual status without waiting.

- `LOCK_GROUP` waits for foreign owners of the selected groups to release them.
  Groups already owned by the caller remain eligible. It grants the entire mask
  once ready and acquires no additional groups if time expires.
- `UNLOCK_GROUP` waits for the caller's selected executing/stopped labels and
  hold flags to clear. The original owners and grant identities must still match
  on each retry. Unlocking and reacquiring a group during the wait invalidates
  that request. A foreign selected grant returns immediately with no release.

The first blocked group in ascending order supplies the status on timeout or
immediate rejection. A ready mask on the final retry succeeds. Each retry
follows a delay of at most 10 logical milliseconds and a task checkpoint.
Eligible timed conditions in scheduled tasks can run between retries.
Mask and status selectors are captured once. Status is published only when the
operation returns, so pause retains its previous value and the wait budget.

A blocked standalone call requires an explicitly injected sleeper. A scheduled
task uses its virtual clock. A blocked handler action returns the current
blocking status immediately, while a ready handler action can complete.
Requests reserve no groups while waiting. Stop, abort and failure discard the
pending operation and follow ordinary terminal cleanup.

These options apply to manual source calls. Automatic root and callee directive
entry keeps its own immediate preflight. Direct bank updates and older generated
calls keep the original immediate behavior. Retranslate to use the new path.

See the [ready example](../examples/group_wait_ready.kl), the [acquisition
project](../examples/group_wait_acquire/main.kl) with a competing owner, and the
[release project](../examples/group_wait_release/main.kl) with timer-driven
clearance of a stopped label.

## Lifecycle and saved context

Pause retains ownership. Returning from a called program or linked routine also
retains it. Root completion, stop, abort or runtime failure releases all of that
root's groups, including groups with busy labels. Finishing one task preserves
other owners. By default `%LOCKGROUP` and `%NOLOCKGROUP` remain source policy
metadata. `GroupLocks(..., apply_directives=True)` opts into atomic root startup
acquisition; see [directive group locks](directive-group-locks.md) for default
selection, lifecycle and contention. A second opt-in, `callee_scopes=True`, adds
[scoped acquisitions](scoped-group-locks.md) for called programs and routines.
Separately, `pendant_enabled=True` allows [RUN_TASK handoff](task-and-file-extensions.md#pendant-launch-and-logical-group-handoff)
of idle parent grants to a fresh child in the shared context.

`bank.snapshot()` returns detached configured groups, motion labels and owner
source names for inspection. Nonempty hold sets appear as `held`; empty sets
remain omitted. JSON persists configured groups, motion labels, hold flags and
the true `apply_directives`, `callee_scopes` and `pendant_enabled` flags. It also retains nonzero
wait limits. Saving while ownership or a wait is live raises. Finish the
operation and release ownership before saving. Saved configuration recreates
only the group bank, labels and policy.

The [authored example](../examples/group_locks.kl) exercises a stopped-group
status, invalid mask and terminal cleanup. Run it with the supplied context:

```sh
python -m karel2py examples/group_locks.kl --check
python -m karel2py examples/group_locks.kl -o .local/group_locks.py
python .local/group_locks.py --context examples/group_locks.services.initial.json
```

Create `.local` before using the output path. The
[linked program example](../examples/program_calls_project/main.kl) also shows
a caller and its callee retaining the same logical owner.

The report's `group_lock_policy` and
[semantic ledger](semantics/group_lock_semantics.json) record the contract.
Native group availability, servo ownership, physical motion, scheduling, lock
waits and controller status equivalence remain unverified. Strict mode remains
future work.
