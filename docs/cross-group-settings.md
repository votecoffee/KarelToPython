# Cross-group WITH metadata

Pythonic MOVE requests can capture temporary WITH values for other configured
groups through an explicit service option. These values are detached request
metadata. Only the MOVE's selected group executes or joins a queue.

## Enable and translate

~~~python
from karel2py.runtime import MotionRequests, GroupLocks, ExecutionContext

context = ExecutionContext(
    group_locks=GroupLocks([1, 2]),
    motion=MotionRequests({1: 6, 2: 2}, capture_only=True,
                          cross_group_settings=True),
)
~~~

~~~karel
ATTACH
WITH $SPEED=25, $GROUP[2].$SPEED=50, $TERMTYPE[2]=FINE
MOVE AWAY 10
RELEASE
~~~

The MOVE uses its source-selected group. An unqualified setting resolves to that
group; `$NAME[group]` and `$GROUP[group].$NAME` select a setting's group explicitly.
The option requires an exact BOOLEAN, defaults to false and is omitted when
false. Saved execution-context JSON accepts `"cross_group_settings": true` inside
`motion`. The same context works through the API, CLI `--context` and linked
project execution. Retranslate existing generated code to use the expanded
source row limit.

## Capture and admission

All [21 supported settings](motion-controls.md) may occur once per configured
group, up to 651 rows across groups 1..31. A name may repeat on different groups;
the same canonical name/group pair cannot repeat, including aliases discovered
after dynamic group expressions run. With the option disabled, all rows must
still match the selected MOVE group and the runtime limit remains 21.

Capture each group expression, then its value, once in source order before MOVE
operands and local-condition captures. Frame/tool values detach immediately.
Complete values, configured groups, duplicate pairs, attached calling-root
ownership, response scripts and existing bounds validate before MOVE publication
or reply consumption. Earlier expression effects remain visible on failure.

The calling task must own every referenced group at admission. Foreign and
unowned references reject. Referenced groups may be held or logically busy
because they are metadata only. The selected MOVE group retains all existing
hold, ownership, stopped-state, queue-capacity and response checks. Existing
MOTYPE/VIA consistency applies to every setting row, including other groups.
The compact canonical request limit remains 64 KiB.

## Execution and lifetime

All seven MOVE forms and VIA retain these values in ordinary capture, supplied
finite delays, NOWAIT, queued blocking/NOWAIT work and local WHEN/UNTIL or supplied
temporal scopes. The queue/scope owns only the selected MOVE group's exact grant.
Later release, hold or ownership changes on a metadata-only group do not mutate
or invalidate admitted jobs. A later MOVE must independently validate ownership.
Linked routines use the calling root's grants and their own selected source group.

No other group gains execution, a hold, feedback, changed frame/tool tables,
trajectory planning, synchronized timing or a physical motion from these values.
Pause/resume, cancellation, frame expiry and task cleanup retain existing rules.
This is an authored offline extension; native/compiler/controller behavior and
strict equivalence remain unverified.

## History and examples

Terminal JSON history retains canonical names, group numbers and checked values.
The true opt-in persists; loading cross-group rows without it rejects. Completed
histories round trip without callbacks, clocks or aliases. Active/waiting scopes
remain unsavable, and pending history cannot reload.

Reports expose `motion_cross_group_setting_policy`. The existing
`motion_setting_policy.maximum` remains 21 per group; `maximum_total` is 651.
Runtime row capacity also depends on the number of configured groups.

See [choices](../examples/cross_group_choices.kl),
[all settings](../examples/cross_group_all.kl),
[queued clauses](../examples/cross_group_queue.kl),
[supplied timing](../examples/cross_group_temporal.kl),
[linked group selection](../examples/cross_group_linked/main.kl),
[borrowed parameters](../examples/cross_group_borrowed/main.kl),
[regressions](../tests/test_cross_group_settings.py) and the
[semantic ledger](semantics/cross_group_setting_semantics.json).
