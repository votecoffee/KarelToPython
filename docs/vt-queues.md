# Offline VT line queues

Twelve legacy VT calls use explicit `vision.tracking.vt` state. Together with
[core vision results](vision-results.md) and [legacy tracking](vision-tracking.md),
they provide a Pythonic workpiece queue model. The host supplies ordered areas,
geometry estimates and poses. No camera, encoder or conveyor is connected.

```sh
python -m karel2py examples/vt_flow.kl -o vt_flow.py
python vt_flow.py --context examples/vt_flow.services.initial.json --state-out vt-state.json
```

See the authored [allocation example](../examples/vt_flow.kl),
[PATH/routing example](../examples/vt_path.kl) and
[linked project](../examples/vt_project/main.kl). Generated translations remain
outputs. All forms use an INTEGER status output.

## Calls

| Source form | Offline behavior |
| --- | --- |
| `VT_PUT_QUEUE(line,work_id,tray,encoder,model,offset,positions,measurements,status)` | Insert supplied workpiece into the shared line pool. |
| `VT_PUT_QUE2(...,duplicate,status)` | Same inputs, plus BOOLEAN duplicate output; requires tray zero. |
| `VT_GET_QUEUE(area,vr,timeout,consecutive,model,work_id,status)` | Select eligible workpiece, copy into vision register and retain allocation receipt. |
| `VT_ACK_QUEUE(area,vr,ack,status)` | 1 handled or 3 failed discards; 2 not handled forwards the current adjusted register downstream. |
| `VT_CLR_QUEUE(area,status)` | Clear visibility/allocations for that area; retain parts still eligible elsewhere. |
| `VT_GET_TIME(area,consecutive,model,work_id,time,status)` | Signed INTEGER milliseconds until first eligible arrival; negative if already available. Does not consume. |
| `VT_GET_PFRT(area,consecutive,num_consct,model,rate,status)` | Approximate INTEGER parts/minute from explicit speed/span and grouped eligible count. |
| `VT_READ_PQ(area,path,status)` | Fill existing PATH node prefix in downstream encoder order, set header count, preserve unused nodes. |
| `VT_WRITE_PQ(area,internal_index,model,encoder,offset,found_pos,measurements,status)` | Replace only supplied fields of a pooled part. |
| `VT_DELETE_PQ(area,internal_index,status)` | Remove that area's visibility, forwarding its target when another area remains. |
| `VT_SET_FLAG(line,enable,disable,area_enable,area_disable,status)` | Atomically update checked line/area flag masks. |
| `VT_SET_LDBAL(line,model,pick_rates,pass_rate,status)` | Set deterministic weighted routing profile and reset its cursor. |

The reference syntax and parameter table for WRITE_PQ put **model before encoder**;
its example reverses them. This implementation follows the syntax/table. The
[semantic ledger](semantics/vt_queue_semantics.json) records that discrepancy.
These are legacy source forms; their native availability varies by release.

## Explicit configuration

A minimal configuration is:

```json
{
  "vision": {
    "tracking": {
      "ids": {"areas": {"PICK": 1, "NEXT": 2}, "lines": {"LINE": 1}},
      "vt": {
        "lines": {"1": {"areas": [1, 2], "capacity": 8, "speed": 100}},
        "areas": {
          "1": {"line": 1, "travel_ms": 15, "span": 1000, "frame": 2},
          "2": {"line": 1, "span": 1000, "frame": 3}
        }
      }
    }
  }
}
```

Name-to-ID lookups remain explicit in `tracking.ids`; configuring a line does
not invent names. Every area belongs to one configured line, whose `areas` list
is its upstream-to-downstream order. Parts occupy one shared pool, with per-area
arrival times, passed-area markers and a routing target. Capacity includes
outstanding allocations. Caller work ID zero is allowed; distinct nonzero caller
IDs cannot coexist on one line. Each accepted insertion has a separate increasing
internal index, which READ_PQ reports in WORK_ID and WRITE/DELETE use. GET uses
the original caller work ID. IDs never wrap.

Defaults are line flags zero, direction +1, no speed, no tray editing, area flags
zero, clocks/travel zero, frame zero and no span. `direction` +1/-1 controls
encoder sort order. `speed` is nonnegative and `span` positive, in matching supplied
distance units. Frames are labels; results are never transformed automatically.

Duplicate detection compares a nonzero caller ID or the exact encoder/model/
six-coordinate offset tuple against held parts. QUE2 returns duplicate TRUE with
status zero and leaves the queue unchanged. This is a practical deterministic
rule; native calibrated duplicate tolerances are not reproduced. A configured
nonzero tray ID is a tag on one part, without tray-cell expansion or sequence.

## Nullable typed inputs

Unknown INTEGER `model`/`work_id` inputs in GET/TIME/PFRT mean unspecified.
Initialized zero selects the real value zero. Source lvalues, including indexed
ones, are captured once as typed readonly snapshots; expressions must still be
valid initialized expressions. Ordinary source reads and routine interfaces keep
their initialization guards.

PUT positions require exact `ARRAY[4] OF XYZWPR`; measurements require exact
`ARRAY[10] OF REAL`. Entirely unknown poses are absent, partially initialized
poses fail, and unknown measurements remain absent. WRITE allows an entirely
unknown model, encoder or pose to preserve it; unknown measurement elements
preserve their old values. It updates camera view 1 only. Partial records are
never turned into invented zero poses. A source may pass the same readonly input
more than once; outputs and mutable resources keep their overlap checks.

## Allocation and waiting

GET uses encoder order, or offset Y when Y-sort is enabled, filtered by area,
model and caller work ID. `consecutive` must be positive; greater than one ignores
a load-balancing target, but still respects passed/skip/model/work filters. It
does not infer a native tray-cell sequence. Allocated workpieces leave the pool
until acknowledged; register replacement by core or legacy queue gets is blocked.
V_ADJ_2D can adjust the register before ACK 2 forwards it downstream. A receipt
can be consumed only once. ACK 1/3 removes the workpiece but retains the register's
last value. Upstream areas cannot reacquire a part returned downstream.

PUT sets each arrival to that area's current clock plus `travel_ms`. Each area
has an independent logical millisecond clock; only its GET waits advance it.
GET polls at most every 10 ms, with zero-time poll, inclusive positive timeout,
or negative indefinite wait. Pause/resume retains the pending request. Stop,
abort and budget failure release reservations; no history ID is required for
cleanup. A pending request blocks relevant edits/register reuse and saving.
This is a cooperative logical-clock model, without native scheduler timing.

TIME returns positive until arrival and at most -1 once available. PFRT computes
`floor((eligible_count + num_consct - consecutive) / num_consct)` groups, clipped
to zero, times `speed * 60 / span`, rounded with Python. It includes eligible
future arrivals; it does not reconstruct a historical conveyor region, tray
occupancy, calibrated Y area or native load-balancing flow algorithm. Missing
speed/span returns unavailable and preserves the output; overflow is invalid.

## Queue PATH

The structural schema is exact; authored type names can differ:

```karel
TYPE
  coord_t=STRUCTURE x:REAL y:REAL z:REAL w:REAL p:REAL r:REAL ENDSTRUCTURE
  part_t=STRUCTURE
    work_id:INTEGER model_id:INTEGER tray_id:INTEGER enc_count:INTEGER
    offset:coord_t found_pos:coord_t meas_value:ARRAY[10] OF REAL
  ENDSTRUCTURE
  header_t=STRUCTURE area_id:INTEGER num_parts:INTEGER ENDSTRUCTURE
  queue_t=PATH NODEDATA=part_t,PATHHEADER=header_t
```

Preallocate nodes with APPEND_NODE before READ_PQ. It copies at most the existing
node count, sets AREA_ID/NUM_PARTS to the copied count, and leaves the unused tail
and storage identities intact. Missing tray/view/measurement fields remain
uninitialized in copied nodes. READ includes future eligible pooled parts,
without waiting. READ/WRITE/DELETE require disabled load balancing. Tray-tagged
entries also require explicit line `tray_edit: true`; this grants data editing,
not native tray semantics. Editing an allocated internal index returns busy.

## Flags and routing

All flag/rate arrays are exact `ARRAY[32] OF INTEGER`, initialized in full.
Only the prefix matching the ordered areas is used; unused slots must be zero.
Enable and disable cannot both be nonzero for one line or one area.

| Scope | Mask | Behavior |
| --- | --- | --- |
| Line | 1 | Weighted routing enabled. |
| Line | 2 | Downstream-first weight-cycle ordering. |
| Area | 1 | Skip area; retarget queued parts that selected it. |
| Area | 2 | Sort by supplied offset Y. |
| Area | 4 | Descending Y when sorting is enabled. |
| Area | 8, 16 | Retained conveyor/DO intent metadata only. |

Profiles use model zero as default fallback, per-area nonnegative `pick` weights
and a nonnegative `pass` weight. At least one rate must be positive. Each insertion
advances that profile's deterministic weighted round-robin cursor. Bypass drops
the insertion; skipped areas are excluded. No enabled destination also drops it.
Without load balancing the first enabled area is selected. SET_LDBAL does not
automatically enable load balancing or retroactively redistribute existing parts.

## Persistence, bounds and statuses

Context JSON retains checked pool data, partial result values, per-area clocks,
line sequence, profiles/cursors and allocation receipts. Active GET requests
must finish or stop before saving. Restored data does not restore executable
links, suspended tasks or input producers. The [linked fixture](../examples/vt_project/services.initial.json)
uses the same services across supplied source modules.

Limits are 32 lines, 256 areas, 1..32 ordered areas per line, 4096 held parts
in total, 256 model profiles per line, 24-hour positive timeout/travel windows
and nonwrapping INTEGER counters/clocks. Malformed topology/state is rejected.

Portable statuses: 0 completed, 1 unavailable/not found, 2 invalid/unconfigured,
3 busy, 4 capacity, 6 missing allocation, 7 incompatible load-balance/tray-edit
mode, and 117249 timeout. Other result services retain their documented codes.
History status 8 records interrupted waits and 9 other failed waits; they are not
invented successful source outputs. Supplied values, portable codes and passing
offline checks do not establish native ABI/status, controller or strict equivalence.
