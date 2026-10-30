# Connected timers in private USING records

Pythonic CONNECT/DISCONNECT TIMER accepts ordinary INTEGER fields and ARRAY
leaves in a captured computed USING record. These values are independent checked
copies; timer writes never copy back to the record returned by the selector.
Existing declared global timer forms remain supported.

```karel
USING make_record() DO
  CONNECT TIMER TO elapsed
  CONDITION[1]:
    WHEN elapsed>=5 DO
      ready=TRUE
      DISCONNECT TIMER elapsed
  ENDCONDITION
ENDUSING
ENABLE CONDITION[1]
WHILE NOT ready DO
ENDWHILE
```

Initialize ready explicitly. Supply a nonnegative monotonic microsecond clock
through Program(clock_us=...) for controlled host execution, or use the existing
deterministic scheduler. Default standalone execution reads the host monotonic
clock. This is an offline Pythonic extension without native controller timing.

## Capture and identity

CONNECT evaluates its scalar selector once. Changing an index variable later
does not retarget that connection. DISCONNECT evaluates its own selector once
and must identify the same scalar storage. Nested reference USING scopes inherit
the private capture; independent computed captures and fresh entries allocate
different values. Connecting the same scalar twice fails; distinct sibling leaves
can be connected independently. Disconnecting a different leaf fails without
removing the original connection.

Unknown INTEGER storage initializes to zero after a valid clock is acquired.
An initialized checked INTEGER, including a negative value, retains its starting
value. Malformed initial values fail before acquiring a clock or registering the
timer. Clock failures do not initialize unknown storage. No native timer status
codes or automatic variable lookup are supplied.

## Progress and failure

Existing checkpoint updates carry fractional milliseconds, reject backward
clocks and stage all timer values before publishing any update. Overflow in one
connected timer preserves every timer value and its previous clock/remainder
record for that attempted update. Explicit source assignments retain their usual
checked behavior and can change a connected scalar's base value.

Timers poll only at execution checkpoints, including loop tests. There is no
background thread. Pause retains the connection and capture; elapsed clock time
during a pause is applied at the next checkpoint after resume. With a virtual
scheduler this is virtual elapsed time, with no inference of physical duration.

## Lifetime and cleanup

A private connection can outlive its lexical USING block or an ordinary source
routine return within the same Program invocation. Retained condition handlers
freeze the enclosing capture and can read or disconnect it later. Separate
entries keep separate captured values. Losing lexical access does not implicitly
disconnect a timer or invent a public variable name.

Explicit DISCONNECT removes a connection. Task completion, stop, abort and failure
release all remaining timer registrations, including declared global timers,
after ordinary frame unwinding. Pause retains them. A linked FROM routine has an
independent invocation state; its connections end when that invocation returns,
fails or closes. They do not become persistent timers of the caller or prototype.
Caller connections retain their independent lifetime.

Context JSON can store declared values and logical services. It omits private
captures, connections, clock callables, callbacks and suspended execution. Loading
that data does not resume a private timer. Private values are not added to the
public variable store; a saved run begins again under the existing run contract.

## Counter and type boundaries

The existing conservative whole-root counter proof applies. Any lexical CONNECT
site for one private record blocks FOR counters anywhere in that same private
root, including sibling fields, nested aliases and code before a DISCONNECT.
An independent computed copy or original source record is a different root.
Existing direct, handler, transitive-call and retained writable-alias guards stay
in force; this feature does not prove path-sensitive disjointness.

Only exact ordinary INTEGER leaves qualify. BYTE, SHORT, REAL, CONFIG turn
fields, read-only POSITION columns, resources, direct uncaptured function-result
selectors retain their existing restrictions. [Declared local timers](routine-local-timers.md)
now use a separate routine-frame lifetime. [Formal timers](formal-timers.md) borrow
ordinary INTEGER leaves under the live callee frame and shared-context ownership.
No physical timer, native alias lifetime, controller interrupt ordering or strict
mode behavior is implied.

## Reports and examples

connected_timers records operation, body, source line/column, selector, source
root, provenance, internal protection root and one-time evaluation. Private rows
retain root=null; internal identities are not source variable names or runtime
persistence keys. connected_timer_policy describes storage, lifetime, update,
counter and persistence choices and sets controller_validated=false.

See the authored [retained handler](../examples/private_using_timers.kl),
[routine RETURN](../examples/private_timer_returns.kl),
[linked progress](../examples/private_timer_project/main.kl),
[linked retained handler](../examples/private_timer_handler_project/main.kl), and
[regression tests](../tests/test_private_using_timers.py).
