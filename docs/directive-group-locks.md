# Opt-in directive group locks

Pythonic Programs can apply their root `%LOCKGROUP` / `%NOLOCKGROUP` policy to
an explicitly supplied logical GroupLocks bank:

```python
from karel2py.runtime import ExecutionContext, GroupLocks

context = ExecutionContext(
    group_locks=GroupLocks([1, 2, 3], apply_directives=True),
)
```

The equivalent context JSON is:

```json
{
  "group_locks": {
    "groups": [1, 2, 3],
    "apply_directives": true
  }
}
```

The flag defaults to false. Without the flag, existing directives remain source
metadata and manual LOCK_GROUP/UNLOCK_GROUP behavior is unchanged. Without a
bank, directives never create groups or discover hardware, robot models or
controller configuration. This feature acquires logical owner labels only.

## Root entry and selection

At each new root Program run or TaskScheduler start, after ordinary task setup
and before its body, the opted-in bank applies this selection:

| Source policy | Groups requested |
| --- | --- |
| `%LOCKGROUP=1,3` | Exactly the listed groups |
| `%NOLOCKGROUP` | None |
| Neither directive | Every explicitly configured bank group |

DEFGROUP selects ordinary source robot context and does not narrow the default
lock selection. Configured groups remain distinct integers in 1 through 31.
Each requested group must be configured, free or already owned by this stable
task root. A free group with an executing/stopped label is unavailable. A group
already owned by this root remains eligible, including with a busy label.

The bank checks the entire request before acquiring any group. Unknown groups,
foreign owners, unowned busy labels or malformed requirements raise
KarelRuntimeError before body effects. They preserve all preexisting ownership,
including the requesting root's manually held groups. A failed scheduler start
keeps the task ready without creating an execution generator; it can retry after
the conflict is resolved. No partially acquired automatic batch is retained.

This atomic startup policy is separate from the existing manual LOCK_GROUP
procedure, which still acquires eligible selected groups even when another
selected group is unavailable. The manual procedure's documented partial-result
and status conventions remain unchanged.

## Lifetime and nested execution

Pause retains ownership. Resume and POWERUP continuation do not start a new root
run or reacquire a group explicitly unlocked while paused. A later fresh run
applies the policy again. Root completion, stop, abort or runtime failure releases
that root's groups under the existing cleanup rules; foreign owners and supplied
motion labels survive. Explicit manual unlock rules continue to apply.

Task renaming changes registry identity without changing the root owner object.
Same-task CALL_PROG/CALL_PROGLIN, recursion and linked FROM routines share that
owner. Returning from a called program or routine does not release caller locks.
Manual lock/unlock calls made inside them still operate on the calling root.

**Automatic directive acquisition in this implementation is root-only.** A called
program or linked library's own directive does not acquire additional groups or
release caller groups. For example, a root with NOLOCKGROUP calling a program
with LOCKGROUP=1 remains unlocked unless code explicitly calls LOCK_GROUP.
Likewise, a root holding group 1 can call a module declaring group 2 even when
only group 1 is configured; the callee's deferred directive is not applied.

MARRC75KR07091E Rev N sections 17.3, A.12.4, A.12.5 and A.14.5 describe native
program/routine acquisition, additional callee scopes, native pause/readiness
conditions and return-time release. This root-only portable choice does not
implement those additional callee acquisitions, native lock waits, servo/e-stop
readiness, parent group transfer or physical motion. An unavailable automatic
request raises instead of entering a native pause or wait.

## Configuration and observations

`apply_directives` requires an actual Boolean in the Python API and JSON; numeric
0/1, null and strings are rejected. A true value persists in to_config and
snapshot results. False remains the canonical default and is omitted, preserving
the existing configuration shape. Explicit JSON false also canonicalizes to that
omitted default.

Snapshots retain the existing configured groups, supplied motion labels and
owner source-program names. They are detached inspection values. Saving context
with live ownership still raises. After ordinary terminal cleanup or explicit
unlocking, JSON retains the opt-in flag, configured groups and labels; it does
not restore ownership, task identity, held execution or suspended stacks.

See [logical group ownership](group-locks.md) for manual procedure masks/statuses
and [source directives](source-directives.md) for metadata parsing. The authored
regressions in `tests/test_directive_group_locks.py` cover startup atomicity,
legacy opt-out behavior, nested calls, scheduler contention, renaming, terminal
cleanup and configuration persistence. Native/controller acceptance and public
strict mode remain future work.
