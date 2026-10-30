# Routine-local connected timers

Pythonic CONNECT/DISCONNECT TIMER accepts fresh declared routine-local INTEGER
scalars, record fields and ARRAY elements. Named or grouped USING references into
those locals keep the same frame lifetime. This is an explicit offline Pythonic
extension; native timer scope, interrupts and controller timing are unverified.

```karel
ROUTINE elapsed_at_return:INTEGER
VAR elapsed:INTEGER
BEGIN
  CONNECT TIMER TO elapsed
  DELAY 5
  RETURN elapsed
END elapsed_at_return
```

The connection ends when this routine unwinds, including an early RETURN.
Default standalone execution uses host monotonic elapsed time. Supply clock_us
for controlled tests, or use the deterministic scheduler for virtual time.
An initialized local keeps its starting value; an unknown INTEGER becomes zero
only after a valid clock. Existing source and receiver INTEGER checks apply.

## Capture and lifetime

CONNECT captures its scalar selector once. Changing an index later does not
retarget the connection. DISCONNECT evaluates its own selector and must identify
the same connected leaf. Separate leaves, fresh calls and recursive invocations
retain independent references and clock/remainder state. Connecting the same
leaf twice fails before another registration is created.

Local connections belong to the actual defining routine frame. They survive
lexical USING exit, nested routine calls and pause/resume while that frame is
active. Explicit DISCONNECT removes one connection. Normal/early RETURN,
failures, stop, sticky abort, budget exhaustion and generator close release the
remaining connections owned by that exact frame. RETURN captures its value before
cleanup. Caller and sibling-frame timers remain independent.

Scope cleanup removes only the retained owned registration. A replaced record
is not removed by an older frame's cleanup. Checkpoint updates reject a changed
or lost local registration before acquiring a clock or updating values. A scoped
DISCONNECT cannot use another frame's registration or a retained dead frame.
The existing terminal task/invocation bank cleanup remains separate.

Updates use the existing checkpoint model: monotonic milliseconds, fractional
carry, backward-clock checks, bounded source budgets and staged numeric updates.
There is no background timer thread. Elapsed clock time during a pause is applied
at the next checkpoint after resume, before the frame can return.

## Retained handlers and different timer roots

A condition handler freezes the references and local frames captured at its
definition. It can use a local timer while the defining frame is still active,
even if the task is inside a nested call. After that frame returns, a retained
handler can still read or explicitly edit its retained data. The timer is
already disconnected, so later elapsed time does not update that value.

A handler cannot reconnect or disconnect a local timer after its defining frame
returns. Merely retaining a local frame is not proof that it remains active.
The optional local_handlers policy can purge handlers at return; local timer
cleanup runs independently of that option.

Global and [computed private USING timers](private-using-timers.md) retain their
existing invocation lifetimes. An independently computed copy of a local record
is private storage, rather than a declared local alias. Its connection can outlive
the source routine within that invocation. A named USING reference into the local
record retains the routine-frame lifetime. Neither case copies timer writes back
to a function's original record.

Linked FROM calls own separate invocation frames. Their local connections end
with the actual defining frame, including failure or suspended-generator close.
A caller's active global/local timers survive the callee's cleanup. Concurrent
linked invocations allocate different local storage and ownership records.

## Counter, type and persistence boundaries

The conservative whole-root timer/counter proof applies within the defining
routine. A local timer on one field blocks a FOR counter on a sibling of that
same root. This is a lexical proof, including connections after the loop or before
an explicit DISCONNECT. Fresh locals in another routine and declared global
storage with the same spelling remain distinct roots for timer interference.
Other direct/transitive/handler counter checks retain their existing rules.

Only ordinary exact INTEGER leaves qualify. BYTE, SHORT, REAL, CONFIG turn fields
and read-only POSITION columns retain their type/protection guards. [Borrowed
formal timers](formal-timers.md) now use a separate callee-frame contract and
shared-context duplicate checks. Dynamic caller scope, inferred native alias
ownership and public strict mode remain outside this feature.

Context JSON stores declared globals and logical service data. It omits local
values, frame ownership, live connections, clock callbacks, handlers and suspended
execution. Loading saved data does not restore or resume a local timer.

## Reports and examples

connected_timers rows use provenance=routine_local and lifetime=routine_frame,
with the source local root and one-time captured selector. Global/private rows
retain their source provenance and invocation lifetime. routine_local_timer_policy
adds frame ownership, cleanup, counter and persistence choices, with
controller_validated=false. The existing connected_timer_policy includes the
expanded storage choices.

See the authored [scalar/record example](../examples/routine_local_timers.kl),
[retained handler](../examples/routine_local_timer_handlers.kl),
[recursion](../examples/routine_local_timer_recursion.kl),
[independent counter](../examples/routine_local_timer_counter.kl),
[linked local timer](../examples/routine_local_timer_project/main.kl),
[caller preservation](../examples/routine_local_timer_caller_project/main.kl), and
[regression tests](../tests/test_routine_local_timers.py).
