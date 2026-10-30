# Timers on borrowed routine parameters

Pythonic CONNECT/DISCONNECT TIMER accepts exact INTEGER references rooted in
routine parameters, including record fields, ARRAY elements and captured named
USING aliases. The callee owns the connection; the referenced data follows the
ordinary argument-passing contract. This is an offline Pythonic extension.

```karel
ROUTINE elapsed_after_wait(value:INTEGER):INTEGER
BEGIN
  CONNECT TIMER TO value
  DELAY 5
  RETURN value
END elapsed_after_wait
```

A bare exact INTEGER actual borrows caller storage. If it is missing, CONNECT
initializes that storage to zero after a valid clock is acquired. Checkpoints
update the actual caller value while the callee frame is active. RETURN captures
its result, then frame cleanup disconnects the timer. The final caller value
remains; cleanup neither clears the value nor copies a temporary result back.

## Actual arguments and capture

| Actual | Data changed by timer writes |
| --- | --- |
| Exact bare INTEGER or exact aggregate reference | The captured caller scalar leaf |
| Grouped/computed scalar or aggregate value | Its independent private argument cell |
| Ordinary checked numeric promotion/conversion | Its private converted argument cell |
| Forwarded exact bare formal | The same original reference |

Existing read, type, initialization, shape and numeric-conversion rules run
before entry. Grouping a missing scalar still fails as an ordinary read; bare
missing references and permitted partial aggregate copies can supply storage.
Formal terminal storage must be ordinary exact INTEGER. SHORT/REAL/BYTE formals,
CONFIG turn fields and readonly POSITION columns retain their existing guards.

Each CONNECT selector is evaluated once. Changing an index later does not
retarget the connection. Matching DISCONNECT evaluates its own selector once.
Different formal names that identify the same physical cell are aliases, rather
than independent timer slots.

## Frame ownership and progress

Borrowed connections use the actual live callee frame. They retain references,
clock/remainder data and completed writes across nested calls and pause/resume.
Normal/early return, errors, stop, sticky abort, budget exhaustion and generator
close release the callee's exact owned registrations. Connections do not persist
as borrowed timers after that frame returns.

DISCONNECT through a formal removes only that frame's own scoped connection.
It cannot take over a caller/ancestor timer or cancel another frame's timer.
Use the owning scope to disconnect that connection. Ordinary global/private
invocation timers and fresh local timers retain their separate lifetimes.

The model samples elapsed time at execution checkpoints. RETURN and explicit
DISCONNECT provide source checkpoints after a wait. Automatic implicit return
and cleanup do not add a clock sample or execution step. For example, a helper
ending immediately after DELAY can retain its last pre-wait observed value;
add an explicit RETURN or DISCONNECT when the post-wait value is needed.
There is no background thread, native interrupt scan or implicit final tick.

Handlers retain their ordinary data references. A retained formal alias can
observe later caller writes after the callee returns; it is not a frozen copy
unless the actual was private. A handler cannot restart a scoped timer through
its dead defining frame. A new explicit routine call may borrow retained writable
data under its own new frame without reviving the old frame.

## Shared registrations and validation

An ExecutionContext coordinates connected-cell claims across program states,
linked invocations and concurrent tasks. Each claim retains actual state, record,
original storage object and member identities. A second connection to an already
connected/reserved cell fails before another clock read or initialization. Sharing
one context coordinates these aliases; independent contexts remain separate
explicit model domains.

Updates and DISCONNECT validate record ownership and the captured reference
endpoint before modifying data. Updates revalidate the bank and claims after clock
capture. Registration rechecks endpoint/claims, live frame and current value,
including host callbacks that claim a cell reentrantly or retire its frame.
Each bank still stages its normal numeric updates; the shared registry does not
introduce synchronized multi-bank time or cross-bank transactions.

Cleanup releases exact proven claims. Replaced records/claims or changed reference
endpoints leave uncertain claims reserved for host inspection rather than silently
freeing another owner's slot. Retained original storage prevents identity reuse
from making that claim refer to a different cell. Source code has no API to forge
or retarget these private ownership records.

[Variable archive](variable-archives.md) preflight protects claimed cells across
the context, including transient/unattached states and retained uncertain claims.
A failed restore retains existing data and returns its usual protected/busy status.
It does not repair a live registration or restore execution stacks.

## Counter effects and retained aliases

CONNECT/DISCONNECT count as potential formal/global writes. Direct and transitive
calls and handler actions preserve whole-root FOR counter protections. Passing
an active counter bare to a potentially timer-writing formal is rejected. A
proved detached value argument does not expose that counter to writes.

Source handlers that can retain timer-writing aliases conservatively block
later counters on those declared roots, including transitive forwarding and
local/global storage. This is a lexical proof across the source, not an ordering
or path-sensitive release proof. Existing private USING retained-alias rules
remain. A synchronous scoped helper without a retained handler does not itself
create a continuing timer after return.

## Persistence, reports and examples

Context JSON stores declared data and ordinary logical services. It omits live
claims, frame ownership, private argument cells, callbacks and suspended stacks.
Loading saved data starts a new model context and does not resume a borrowed timer
or certify the state of a still-live context.

connected_timers rows use provenance=borrowed_formal and lifetime=routine_frame.
formal_timer_policy describes argument ownership, cleanup, shared claims,
effects and persistence, with controller_validated=false. Linked signatures,
native ABI/controller timing and public strict mode keep their existing boundaries.

See authored [bare references](../examples/formal_timers.kl),
[private actuals](../examples/formal_timer_values.kl),
[counter values](../examples/formal_timer_counter.kl),
[retained reads](../examples/formal_timer_retained.kl),
[linked borrowing](../examples/formal_timer_project/main.kl),
[caller preservation](../examples/formal_timer_caller_project/main.kl), and
[regression tests](../tests/test_formal_timers.py).
