# Offline vision tracking

Twelve legacy vision/tracking calls run through the explicit `VisionServices`
model. Configure its `tracking` object for queues, process flags, lookup IDs,
supplied area maps and the iRConnect outbox. `VT_GET_FOUND` uses the ordinary
supplied vision-result stream and does not require a tracking object.

```sh
python -m karel2py examples/tracking_queues.kl -o tracking_queues.py
python tracking_queues.py --context examples/tracking_queues.services.initial.json --state-out tracking-state.json
```

The manual inventory spans older controller releases and options. Some VT forms
are explicitly unavailable on V8.20 and later. Their offline acceptance here
preserves legacy source conversion; it does not establish availability or
runtime behavior on a particular controller.

| Source form | Pythonic behavior |
| --- | --- |
| `V_INIT_QUEUE(queue,status)` | Clear stored queued parts and allocation receipts for that queue. |
| `V_GET_QUEUE(queue,vision_register,timeout,status)` | Wait for an explicitly supplied part, then copy its result into the vision register. |
| `V_RALC_QUEUE(queue,vision_register,status)` | Reallocate a received part to the selected downstream queue once. |
| `V_START_VTRK(process,status)` / `V_STOP_VTRK(process,status)` | Set an explicitly configured logical tracking-process flag. |
| `VT_GET_AREID(name)` / `VT_GET_LINID(name)` / `VT_GET_TRYID(name)` | Return configured area/line/tray IDs. |
| `VT_GET_FOUND(process,model,encoder,offset,positions,measurements,status)` | Read the next supplied workpiece with exact ARRAY[4] OF XYZWPR and ARRAY[10] OF REAL outputs. |
| `V_ACQ_VAMAP(sensor,FALSE,zero_vector,status)` | Consume a supplied area-map reply and retain its point data on success. |
| `V_CLR_VAMAP(sensor,status)` | Clear that sensor's current supplied map. |
| `V_IRCONNECT(description,priority,0,status)` | Stage a copy of the most recent supplied completion in a bounded local outbox. |

## Queue input and allocation lifetime

Queues have canonical positive string keys, an explicit `capacity` in 1..4096,
optional `parts` and ordered future `arrivals`. Parts have a positive `work_id`
and a `result` using the [core vision result schema](vision-results.md).
The complete authored [queue fixture](../examples/tracking_queues.services.initial.json)
shows typed XYZWPR values. Queue configuration looks like:

```json
{
  "queues": {
    "1": {"capacity": 3, "parts": [], "arrivals": [], "elapsed_ms": 0},
    "2": {"capacity": 3}
  },
  "processes": {"SCAN": {"running": false}},
  "ids": {
    "areas": {"PICK": 2},
    "lines": {"LINE": 1},
    "trays": {"TRAY": 3}
  }
}
```

An arrival is `{ "at_ms": 15, "part": { "work_id": 101, "result": ... } }`.
Names are case-insensitive; each ID bank requires distinct positive IDs. Unknown
names raise an explicit error without inventing zero or changing an assignment.
The name maps describe supplied setup metadata; they do not discover native
line, area or tray configuration.

Each queue has an independent logical millisecond clock. GET advances it in
cooperative steps of at most 10 ms while waiting. Arrival times use that queue's
clock; passage of unrelated host time does not advance it. Timeout zero polls,
a positive timeout waits up to that many milliseconds, and a negative timeout
waits until input arrives or normal execution limits/control interrupt it.
An arrival exactly on the deadline is eligible. Timeout returns 117249, the
chosen portable equivalent of the documented VT timeout value; the older
V_GET_QUEUE reference does not specify its units or nonzero timeout encoding.

Future arrivals become queued parts as space permits. GET copies the first
available part, records its work ID and supplied encoder as a logical trigger,
and retains an allocation receipt keyed by the destination vision register.
It neither starts conveyor motion nor configures a hardware trigger. Parts are
independent copies. Work IDs are distinct within a queue's queued, future and
allocated records. Queues and work IDs are portable model identities.

RALC requires a receipt from an earlier queue GET and a populated matching
register. It can reallocate to a different configured queue, copying the current
result. An X/Y adjustment therefore retains the original work ID while changing
the reallocated offset. Full or duplicate destinations preserve the receipt;
a successful reallocation consumes it and clears the logical trigger. Repeating
it cannot silently duplicate a part.

A later successful GET into the same register replaces its old receipt, treating
the previous allocation as handled. Core V_GET_OFFSET likewise invalidates an
old receipt when it replaces that register. Register values remain independent
of queue storage. INIT clears queued parts and receipts for its queue, retaining
register values, clock position and explicitly supplied future input plans.
Those plans represent external future inputs rather than data already held in
the queue. Initializing one robot's bank does not clear another bank.

Host integrations can call `tracking.enqueue(queue,work_id,result)` to supply a
new part explicitly. Capacity and duplicate IDs remain checked. START/STOP record
logical process state only: they do not execute vision algorithms, create parts,
infer conveyor travel or suppress already supplied future arrivals.

## Waiting, interruption and saved state

Only one GET may wait on a queue or reserve a particular vision register.
A competing GET returns busy status. INIT cannot clear a queue with a pending
read. Core offset replacement, X/Y adjustment and reallocation also reject
writes involving a reserved register. Reallocation from another register can
feed a waiting queue.

Pause/resume retains the same request, deadline and input plans. Waits create no
artificial PAUSE notification. Stop, abort and budget failure release the pending
reservation in `finally`; cancellation does not require another history ID.
The ordinary status output remains unchanged on interruption. Request history
records 8 for cancellation or 9 for failure in these cases. A future arrival that
has not been consumed remains available for a later request.

Context saves reject pending GET operations. Completed state preserves queue
contents, future inputs, clocks, register allocation receipts and logical trigger
metadata. Receipts restore as checked data, without live task/frame pointers.
A new run must explicitly supply new work IDs/input plans when replaying a
producer; already consumed arrivals are not recreated automatically. See the
[linked project](../examples/tracking_project/main.kl) for queue calls across
routine boundaries using the same context and calling-root history identity.

There are at most 256 queues and 4096 cumulative queued/future/allocated
workpieces. Queue clocks and request IDs do not wrap. A clock/sequence failure
preserves inputs and outputs, and a stop can still release a request after
sequence exhaustion.

## Result extraction, maps and outbox

VT_GET_FOUND shares the core GET_FOUND/GET_OFFSET cursor. It writes only populated
camera views and the supplied measurement prefix; unknown tails remain unknown.
Every scalar/pose and exact 4/10-element array output passes the shared type,
alias and active-FOR guards before the cursor moves. Exhaustion is 117151.
It returns no frame-number output, matching its documented legacy form.

Area sensors contain explicit `responses` and an optional current `map`. A
successful reply requires `{ "frame": 3, "points": [[1,2,3]] }`; a nonzero
reply contains no map. These finite point triples are a portable point-cloud
representation, without native grid decoding, camera calibration or inferred
units. FALSE and a complete zero VECTOR are the documented internal-parameter
values; other values are rejected without consuming the reply. Success replaces
the map, failure retains it, and CLEAR is idempotent. Clearing keeps future
responses. JSON deliberately retains supplied map data; this is not a physical
controller power-cycle model. Each map has at most 4096 points; cumulative
current/queued maps have at most 32767 points and 4096 replies.

IRCONNECT requires priority 0..3 and unused vision-register argument zero.
The most recent accepted RUN_FIND, TESTRUN, FIND_VIEW or FIND_VLINE completion
becomes the source, including supplied failures. Source START/STOP and queue
reads do not invent a new vision completion. Packets copy available result data,
process and program names, description and priority. Optional `include_images`
adds available supplied image registers for that process, without asserting
freshness or native runtime-image association.

This is a portable local outbox, not the native iRConnect wire schema. It sends
nothing to mobile devices, opens no network connection and invents no missing
fit-error/timing fields. Packets remain until explicitly collected by the host;
a full outbox returns status 4 and never discards old packets. Defaults are 500
packets and a 1 MiB per-packet `payload_limit`, configurable to 4096 packets and
16 MiB per packet, with a 16 MiB aggregate byte limit. Saved packets validate
typed result/image data and increasing request IDs, independently of live links.

Portable statuses are 0 completed, 1 unavailable, 2 invalid/unconfigured,
3 busy, 4 capacity, 5 duplicate work ID and 6 missing/stale allocation. Supplied
map/completion failure codes pass through. None of these choices establishes
native alarms, scheduling, calibrated conveyor geometry, motion or strict
controller equivalence. Twelve additional [VT line queue calls](vt-queues.md)
now model allocation/acknowledgement, partial PATH editing, time/flow estimates
and weighted routing. Tray-cell expansion, calibrated conveyor geometry and
native duplicate/flow algorithms remain unavailable.
