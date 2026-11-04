# Timer control from helper routines

Pythonic DISCONNECT TIMER can release an existing connection through an exact
reference borrowed by a helper in the same calling task. This includes active
caller/ancestor frames, global or private invocation timers, linked source calls,
INTEGER fields/elements, named USING aliases and explicit BYNAME rows/planes.
It is an authored offline extension; native timer/alias behavior, controller ABI
and strict equivalence have not been established.

```karel
VAR elapsed:INTEGER
ROUTINE stop_timer(value:INTEGER)
BEGIN
  DISCONNECT TIMER value
END stop_timer
BEGIN
  CONNECT TIMER TO elapsed
  DELAY 5
  stop_timer(elapsed)
  DELAY 9
END
```

Checkpoints update elapsed time through the call to `stop_timer`. The later wait
cannot update that disconnected cell. A helper can also stop a caller's declared
local timer while its defining frame is still active. In linked calls, the actual
calling task identity is used even when program states and local frames differ.

## Ownership proof

Control follows the captured physical cell, not variable names, source program
names or equal numeric values. Validate the original owner state, record object,
storage object, member identity and member type against the shared
ExecutionContext claim. A frame-owned connection also needs its exact live frame
binding. Remove only that original registration and its matching claim.

The owner and helper must share one ExecutionContext and task-root identity.
Another concurrent task cannot cancel a connection merely by borrowing the same
cell or having the same program/task name. Independent contexts remain separate
model domains. Missing records, replaced endpoints/bindings, inactive defining
frames and uncertain reserved claims reject without freeing a foreign slot.

The helper's own scoped access still requires its current live routine frame.
A retained handler cannot present a dead defining frame as live. A fresh explicit
helper call can borrow retained writable data under its new frame and control an
otherwise valid connection owned by that same task.

## Lifetimes and values remain unchanged

DISCONNECT does not move the timer, clock, frame binding or cleanup owner into
the helper. It adds no clock read, time increment, initialization or copy-back.
Selectors evaluate once through the existing source/reference rules. Other
connections keep their own values, remainders and clocks.

Bare exact arguments and BYNAME aliases borrow the original scalar. Grouped,
computed, converted and ordinary copied-prefix arguments have independent cells;
they cannot control a caller timer on a different cell. Different formal names
that identify one actual cell refer to the same registration.

New connections through formal parameters retain their existing callee-frame
lifetime and end when that frame returns. Persistent borrowed connections after
return are not added by this feature. Duplicate CONNECT remains an error; after
an explicit disconnect, a later explicit connection can establish its own normal
ownership and lifetime.

Pause/resume retains ordinary connections and references until explicit control
or defining-scope cleanup. Stop, abort, failure and unwind retain their existing
owned cleanup. Source effects already completed before a later failure remain
visible. Direct/transitive timer writes and retained aliases keep whole-root FOR
counter protections; this feature adds no path-sensitive counter proof.

## Reports, saved state and examples

Reports add `timer_control_policy`; DISCONNECT rows add
`control_scope: "same_task_existing_claim"`. Existing provenance and connection
lifetime fields remain. Context JSON/VR/DRAM stores data only, omitting connections,
clocks, frame bindings, retained callbacks and suspended execution. Loading data
does not resume a timer or repair a reserved claim.

Authored examples compare Boolean progress checks and normalize elapsed values
before saving, so injected test clocks and normal generated CLI clocks can share
exact final expectations. The example runner's explicit clock fixtures remain
test inputs; no clock adapter is embedded in a saved context.

See the [semantics ledger](semantics/timer_control_semantics.json),
[regressions](../tests/test_timer_control.py), [scalar](../examples/timer_control_scalar.kl),
[row alias](../examples/timer_control_array.kl), [ancestor local](../examples/timer_control_local.kl),
[private capture](../examples/timer_control_private.kl),
[linked caller](../examples/timer_control_linked_caller/main.kl) and
[linked local](../examples/timer_control_linked_local/main.kl).
