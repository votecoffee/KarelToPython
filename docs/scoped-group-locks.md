# Opt-in scoped logical group locks

Pythonic mode can apply source group requirements to same-task called programs
and routines, in addition to [root entry](directive-group-locks.md):

```python
from karel2py.runtime import ExecutionContext, GroupLocks

context = ExecutionContext(group_locks=GroupLocks(
    [1, 2, 3], apply_directives=True, callee_scopes=True,
))
```

The JSON equivalent is:

```json
{
  "group_locks": {
    "groups": [1, 2, 3],
    "apply_directives": true,
    "callee_scopes": true
  }
}
```

Both flags require actual Booleans. callee_scopes defaults to false and requires
apply_directives=true when enabled. The existing root-only opt-in therefore
retains its behavior. False flags remain omitted from canonical configuration.
No absent bank, source directive, robot model or library discovers hardware or
creates implicit groups.

## Entry and return

Each source-defined program/routine uses its module's policy: LOCKGROUP selects
the listed configured groups, NOLOCKGROUP selects none, and neither directive
selects all explicitly configured bank groups. Entry checks the entire request
before making any additional acquisition. Unknown groups, foreign owners and
unowned executing/stopped labels or [hold flags](motion-controls.md) raise before the callee body runs. Existing
caller ownership remains intact. Native pause/readiness waits are not modeled.

Ownership always belongs to the stable calling task root. A scope records only
groups newly acquired at that entry. Groups already owned by the caller are
retained on return; a NOLOCKGROUP callee does not unlock them. New scope groups
are released on ordinary return, error, abort propagation or generator closure,
provided that the original automatic grant is still present. Nested and recursive
calls retain outer grants until their owning scope exits.

For example, a root holding group 1 calls a module requiring group 2. The callee
observes groups 1 and 2 under the same owner. On return, group 2 releases and group
1 remains with the caller. A further callee requiring group 3 temporarily adds
group 3 and releases it before returning to the intermediate module.

CALL_PROG and CALL_PROGLIN acquire the called module's additional groups before
publishing their program index and before an optional pause on entry. Linked
FROM routines acquire the defining module's groups. Their source declaration
forwarders do not apply the declaring module's policy again. Explicit Python
callbacks have no inferred source-module group policy.

Internal routines also use their defining module's policy. If code manually
unlocked a required group before an internal call, that routine can acquire it
for its own scope and release it again on return. No caller group is silently
restored merely because it appeared in an earlier source directive.

## Manual ownership and grant identity

The existing manual LOCK_GROUP/UNLOCK_GROUP procedures retain their partial
result/status behavior. Scoped cleanup distinguishes an acquisition from later
ownership of the same group:

| Operation inside a callee | Effect when its scope exits |
| --- | --- |
| Leave its automatic grant untouched | Release that added group |
| Re-lock an already owned automatic group | Still release it; re-lock is idempotent |
| Unlock its group without reacquiring | Keep it unlocked |
| Unlock then manually lock again | Retain the new manual acquisition |
| Unlock then another task acquires it | Preserve the foreign owner |
| Manually acquire an unrelated extra group | Retain the manual acquisition |

Opaque in-memory grant tokens enforce those boundaries. Names, task renaming,
mask values or a reused group number do not establish grant identity. Tokens are
not part of saved configuration or public snapshots. Existing manually held
caller groups are never adopted as a callee's new automatic grants.

Automatic scope exit is a logical owner release even if a supplied motion label
became busy after acquisition. The label itself remains unchanged. Native
return-time holds pending executing/stopped motion are outside this model;
manual UNLOCK_GROUP retains its existing busy-label checks. No scope cleanup
commands motion, clears a motion label or waits for a physical controller.

## Suspension, failure and persistence

Pause, cooperative waits and POWERUP continuation retain active scope grants.
Resume continues the existing scope without another entry acquisition. Task
renaming preserves the root owner and grant tokens. Stop and execution-budget
failure close nested generators and release their surviving automatic grants;
ordinary root cleanup then releases that root's remaining groups. Foreign owners
survive. Routine frame-entry/exit failures also unwind scoped grants and local
stack bookkeeping.

Acquisition is atomic within a single entry. Source effects completed before a
failed call remain, while the callee body and CALL_PROG index are untouched by
that failed entry. Normal task termination/error cleanup still applies to the
caller after an unhandled error. No transaction rolls back previously executed
source statements or independent manual ownership changes.

Context JSON retains configured groups, motion labels and true opt-in flags.
Live ownership prevents serialization. After cleanup, restoring the configuration
creates no owners, grant tokens, routine scopes, task frames or suspended calls.
A value snapshot is not an execution checkpoint.

MARRC75KR07091E Rev N sections 17.3, A.12.5 and A.14.5 describe additional
program/routine requirements and return-time release. This implementation adds
an explicit portable scope/grant convention. Native readiness conditions, lock
waits, parent/control transfer, physical group limits, servo ownership, exact
controller status/timing and public strict mode remain unverified or deferred.
See the authored regressions in `tests/test_scoped_group_locks.py` and the
[manual logical lock guide](group-locks.md).
