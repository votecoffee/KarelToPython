# Handler priority and robot system pose values

Pythonic mode adds priority ordering within existing cooperative condition scans,
explicit frame/tool source expressions and model-free frame/tool context JSON.
These facilities operate on supplied offline data. Strict and native interrupt,
robot/controller and system-variable equivalence remain future work.

## Handler options

```karel
CONDITION[7]: WITH $PRIORITY=20, $SCAN_TIME=10
  WHEN ready DO count=count+1
ENDCONDITION
ENABLE CONDITION[7]
```

A handler may have one `$PRIORITY` and one `$SCAN_TIME` option, in either order.
Separate options with a comma or a repeated WITH; case, physical newlines and
ordinary comments are accepted. Duplicate and unknown options fail translation.
Each expression must have INTEGER-compatible type. The condition number and
options are captured once, left to right in source order, before registration.
Ordinary effects from completed source expressions remain if a later value fails.

The existing condition-number range is 1..1000. Priority is a portable integer
1..99, with lower numbers scanning first and default 50. Scan time remains
0..86400000 milliseconds; zero scans at each checkpoint. All values are validated
before a new handler is installed. Existing handlers require PURGE before a new
definition can replace them.

At checkpoint entry, each handler namespace takes a stable priority ordering.
Equal priorities retain definition order, including handlers with no explicit
priority. Disabled and not-yet-due handlers are skipped; a high-priority false
predicate does not block other eligible handlers. Actions may disable/purge later
handlers before their turn. Within a handler, WHEN clauses keep source order and
one-shot behavior. ENABLE rearms a handler and allows an immediate first scan.

Priority does not add preemption or merge namespaces/tasks. Linked caller
handlers still scan before the callee namespace. Pause/resume keeps an in-progress
scan, and local-handler lifetime remains controlled by `local_handlers`. A source
abort requested inside an action retains existing deferred delivery after the
current scan, including other eligible actions. There is no new terminal scan:
a final ordinary assignment alone does not create another checkpoint.

`handler_definitions` records source locations, option order, clause count and
once-only capture. `handler_priority_policy` records the portable scheduling
rules. Handler records and suspended scans are not serialized in context JSON.

## Explicit frame/tool expressions

| Source expression | Supplied robot context lookup |
| --- | --- |
| `$MNUFRAME[group,number]` | Numbered frame in that group. |
| `$MNUTOOL[group,number]` | Numbered tool in that group. |
| `$GROUP[group].$UFRAME` | That group's active frame. |
| `$GROUP[group].$UTOOL` | That group's active tool. |

Selectors are INTEGER-compatible expressions, evaluated once left to right before
lookup. Groups must be explicitly configured; frame/tool IDs are 0..32767 and must
have supplied entries. No missing identity, active selection or robot model is
inferred by these source expressions.

Each read returns a complete, independent POSITION value. Supplied POSITION,
XYZWPR and XYZWPREXT table entries use existing checked Cartesian conversions;
external-axis frame metadata is not part of the POSITION result. Location,
configuration and orientation fields can be read normally. Existing assignments,
geometry and private routine argument/result conversions continue to apply.
Bare fields of these computed values are private routine arguments. Computed
USING also captures a private copy, so editing it leaves the configured table
unchanged.

[Dedicated table assignments](system-pose-writes.md) now accept whole poses and
staged LOCATION/CONFIG_DATA edits. Writable READ/service references remain rejected,
and these expressions create no live system alias. Generic GET_VAR/SET_VAR/BYNAME discovery is unchanged;
explicit VariableStore bindings remain separate. Other dollar roots and members,
whole `$GROUP` objects, bare `$UFRAME`/`$UTOOL` values and chained table index
syntax remain unsupported.

`system_pose_values` records operation, body, source location and copy/evaluation
policy. Runtime `service_requests` adds value-free SYSTEM_POSE outcomes, and lookup
failures retain source-located diagnostics and ordinary destination preservation.

## Frame/tool-only JSON contexts

Explicit tables and selections can now load and save without DH parameters,
current joints or reachability callbacks. For example, the ordinary typed pose
format is used in the supplied context:

```json
{
  "robot": {
    "frames": {
      "2": {
        "type": ["XYZWPR"],
        "value": {
          "X": 12.0, "Y": 0.0, "Z": 0.0,
          "W": 0.0, "P": 0.0, "R": 0.0,
          "CONFIG_DATA": {
            "CFG_TURN_NO1": 0, "CFG_TURN_NO2": 0, "CFG_TURN_NO3": 0,
            "CFG_FLIP": false, "CFG_LEFT": false,
            "CFG_UP": false, "CFG_FRONT": false
          }
        }
      }
    },
    "frame": 2
  }
}
```

A standalone table uses canonical ASCII decimal keys 0..32767 and complete typed
Cartesian poses. Explicit active selections must name supplied rows. An omitted
selection keeps the existing default zero; this does not create an absent row.
The example supplies no tool table, so tool reads fail explicitly. Empty tables
alone do not define a robot context. Current-state snapshots and explicit joint
limits may coexist with tables; DH-specific settings still require DH parameters.
Grouped contexts follow the same rules per group.

Save/load retains table values, removals, selections and explicit identity entries.
It does not serialize callbacks or make a table-only context capable of forward,
inverse or reachability math. Existing DH contexts keep their model-specific
identity defaults and serialization behavior.

## Authored execution coverage

The [priority](../examples/handler_priority.kl) and
[combined options](../examples/handler_scan_options.kl) examples exercise ordered
scans and definition-time effects. [Table reads](../examples/system_pose_tables.kl)
and [private routine values](../examples/system_pose_linkage.kl) use model-free
JSON fixtures. The linked [priority project](../examples/handler_priority_project)
and [grouped table project](../examples/system_pose_project) cover external source
routines and namespace/group boundaries.

Complete state fixtures, saved-JSON replay and compiler-free generated execution
accompany these examples. The [semantic contract](semantics/handler_pose_semantics.json)
records the implementation boundaries; native compilation/execution is not claimed.
