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
| 17039 | Owned group has an executing motion label |
| 17040 | Owned group has a stopped motion label |

The two busy codes follow the documented UNLOCK_GROUP conditions. The motion
labels are caller-supplied evidence, not simulated or observed robot movement.
The host can change a label with `bank.set_motion(group,'idle')`, `'executing'`
or `'stopped'`. An unspecified label is idle. There are no automatic lock waits,
motion-driven acquisitions. The separate [controller service](controller-services.md)
now lets CNCL_STP_MTN clear only the caller-owned stopped labels, and MOTION_CTL
query explicit/default group selection. These have no physical motion effects.

## Lifecycle and saved context

Pause retains ownership. Returning from a called program or linked routine also
retains it. Root completion, stop, abort or runtime failure releases all of that
root's groups, including groups with busy labels. Finishing one task preserves
other owners. `%LOCKGROUP` and `%NOLOCKGROUP` remain source policy metadata;
they do not acquire or release this bank automatically.

`bank.snapshot()` returns detached configured groups, motion labels and owner
source names for inspection. JSON persists only groups and motion labels.
Saving context while ownership is live raises rather than writing a state that
could appear to restore task ownership. Finish or explicitly unlock before
saving; source and task frames are never restored by this configuration.

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
