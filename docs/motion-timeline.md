# Explicit node and time conditions

Pythonic [motion-local handlers](motion-handlers.md) support `AT NODE` and
`TIME ... BEFORE/AFTER NODE` using an explicitly supplied arrival schedule.
Schedule values are offline model inputs. They are not measured robot arrivals,
trajectory estimates or controller timing evidence.

## Source forms and capture

```karel
MOVE ALONG track,
  WHEN AT NODE[0] DO count=0
  WHEN TIME 3 BEFORE NODE[1] DO CLOSE HAND 1
  WHEN AT NODE[*] DO count=count+1
  UNTIL TIME 2 AFTER NODE[1] THEN finished=TRUE
ENDMOVE
```

| Form | Modeled event |
| --- | --- |
| `AT NODE[n]` | Supplied arrival time for node n |
| `TIME t BEFORE NODE[n]` | Arrival minus t, clamped to the preceding segment's start |
| `TIME t AFTER NODE[n]` | Arrival plus t, if still within the move and n is not the final node |
| `NODE[*]` in any form | Events for selected destination nodes; the wildcard excludes start node zero |

NODE[0] is the explicit start boundary. For non-path moves, NODE[1] is the
destination. A selected MOVE ALONG range retains its original path indexes:
`track[2..3]` uses nodes 0, 2 and 3. The first selected segment starts at node zero.
TIME BEFORE node zero never fires. TIME AFTER the final node never fires,
including a zero offset. An AFTER event for an earlier node may occur at the
completion boundary; events beyond completion do not fire.

Offsets and node selectors must be INTEGER-compatible values. Offset t is in
0..86400000 ms; named nodes are in 0..32767. Their expressions are evaluated once
at clause definition, offset before node, after the existing EVAL captures.
Changing variables later cannot retime a condition. Pythonic source functions
may supply these values; active FOR counter protections remain in force.

Temporal forms are local predicates only. Ordinary variables named `time`, `at`
or `node` remain usable outside these contextual forms. Boolean composition
retains the existing KAREL precedence rules; parenthesize relational expressions
when combining them with AND/OR. At most 64 temporal selectors are captured per
MOVE, independently of the 32-clause limit.

## Supply the complete schedule

```json
{
  "motion": {
    "groups": {"1": 2},
    "responses": [
      {
        "operation": "MOVE ALONG",
        "completed": true,
        "delay_ms": 23,
        "node_times": {"0": 0, "1": 7, "2": 23}
      }
    ]
  },
  "group_locks": {"groups": [1]}
}
```

`node_times` maps canonical decimal node strings to integer progress milliseconds.
It requires an explicit `delay_ms`, start node `"0": 0`, and 1..256 destination
entries. Times must be nonnegative, nondecreasing by node number and within the
delay. The final arrival must equal delay_ms. Equal times and an explicitly
zero-duration schedule are accepted.

Admission checks the complete selected range: non-path moves require exactly
nodes 0 and 1; path moves require zero plus every selected destination. Extra,
missing or out-of-range nodes reject before consuming the response or creating
an active request. Every named temporal reference must occur in that schedule.

Capture-only mode and a delay without node_times cannot supply arrivals, even
for NODE[0] or an unreachable Boolean branch. No schedule is inferred from
coordinates, path length, speed, frames or duration alone. A false completion
response still validates its data, then rejects without progress or actions.

## Exact progress events

The runtime adds supplied arrivals and temporal event times to its existing
bounded progress steps. A 7 ms arrival is scanned at 7 ms rather than being
rounded to the next 10 ms poll. Global handlers scan first, then local one-shot
clauses in source order. Multiple clauses due at the same instant can all fire;
the existing cancellation/hold rules stop or suspend subsequent scans.

A temporal test is true at its due progress boundary. If a Boolean gate is false
at that boundary, the event is missed; it is not latched into later progress.
A wildcard can offer another event at a later selected node. Each clause still
fires at most once. Wildcards deliberately exclude NODE[0]; write it explicitly
when start timing is needed. This is a documented offline wildcard policy.

Pause and holds freeze the progress clock. Resume/unhold continues the same
boundary and remaining schedule; local scans remain disabled while held. Handler
action time is not motion progress. Stop/abort, UNTIL cancellation, ownership
loss and failures retain the existing checked scope cleanup. A canceled request
keeps its declared future schedule while its elapsed progress records where it
ended; future arrivals are not reported as reached.

The model precomputes bounded event sets and advances a progress cursor. It does
not create a background queue or native asynchronous motion environment.

## History, reports and compatibility

Scoped execution history adds optional `node_times` and captured `conditions`
records (`kind`, `node`, `offset_ms`). Loading validates schedules, references,
selector bounds and existing progress/outcome rules. Node zero, wildcard and
before/after boundary rules are checked without executing callbacks. Active
scope saves and pending-history reloads remain rejected.

Translation reports add `motion_request_policy.temporal_conditions` and per-MOVE
condition locations, wildcard flags and one-time capture metadata. Clause and
condition metadata stays attached to the MOVE even when actions add their own
hand/control request report entries. Source maps retain physical include origins.

Old response JSON without node_times retains its behavior. Old direct-invoke
generated output rejects supplied schedules instead of silently ignoring them;
retranslate for current support. NOWAIT with local clauses or a supplied schedule
remains rejected. Global temporal predicates, inferred arrivals, trajectory
calculation, physical timing and native multi-group synchronization remain outside
this model.

See the authored [node boundaries](../examples/motion_node_events.kl),
[path timeline](../examples/path_timeline_events.kl),
[selected-range cancellation](../examples/motion_timeline_until.kl) and
[linked selectors](../examples/motion_timeline_project/main.kl).
