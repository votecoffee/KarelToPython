# FOR counters in private USING values

Pythonic mode accepts INTEGER, BYTE and SHORT counter fields and ARRAY elements inside
[computed USING record captures](computed-using.md). The counter owns a single
captured scalar reference, and protects the complete private record while it is
active. Its fields never copy back to the function's source.

```karel
total=0
USING make_record() DO
  FOR count=1 TO 3 DO
    total=total+count
  ENDFOR
  finished=UNINIT(count)
ENDUSING
```

This totals six, clears the selected private `count` field and leaves the source
record unchanged. [Narrow counters](narrow-for.md) additionally support BYTE/SHORT
with initialized bounds and type-specific cleanup. REAL, BOOLEAN, CONFIG-domain
fields, readonly POSITION columns and resources retain
their existing counter restrictions. Direct function-result counter syntax
outside a captured USING scope remains unavailable.

## Private identity and aliases

Each independent computed capture receives a distinct internal lexical
protection identity. It has no public variable name: report `source_root` stays
null. Nested reference selectors, such as `USING child`, inherit the enclosing
capture's identity. Grouping a reference does not make a new record copy.

Consequently, counters and writes to different fields or indexes of the same
private root are conservatively treated as aliases:

```karel
USING make_record() DO
  FOR child.count=1 TO 3 DO
    child.other=9       -- rejected: same protected private root
  ENDFOR
ENDUSING
```

A nested computed selector creates a separate checked copy and a separate root;
its counter can run independently. Declared global/local roots also remain
independent from the private copy, even when the computed value originated in
that same declared record.

The protection covers direct assignments, READ, scalar/time/config conversions,
register/joint/UNPOS outputs, ordinary service outputs and potentially writable
routine arguments. Nested counters cannot share one private root. Proven
readonly formals can observe an active counter; grouped value arguments and
checked numeric value conversions use detached cells and can be edited there.

## Calls, handlers and escaped references

A computed capture is fresh storage inside a parameterized routine. It may own
a counter even where the routine's formal or nonlocal declared roots remain
restricted. Unknown external calls without writable private actuals cannot name
these captures. Declared global/formal counter rules remain unchanged.

Private storage can escape through a routine argument. A source routine that
installs a handler can retain its call frame or captured references after it
returns; an unknown external routine could retain an explicitly passed writable
reference. Before accepting a private counter, the translator rejects its root
if the source passes any part of it through a potentially writable bare formal
to an external or direct/transitive handler/timer-retaining routine.

This is a conservative lexical proof across the source, including calls after
the loop and different runtime entries at the same capture site. It does not
attempt path-sensitive ordering, dynamic-index disjointness or callback release
analysis. An ordinary synchronous writable call before the loop does not itself
escape a reference. A grouped argument is a separate value, and a formal proved
readonly does not supply a write alias.

Condition actions that may write any part of the same private root block its
counter, whether through assignment, nested FOR, READ, conversion/service output
or a transitive writable routine argument. Readonly handlers can retain the
capture and observe its counter or subsequent cleanup. Handlers bound to
independent computed captures do not alias the counter. Connected timers still
require declared global storage and reject private captures with `E_TIMER_SCOPE`.

Indirect variable-name operations cannot resolve an unnamed private root. They
remain subject to their own output-reference checks and to ordinary protection
when a declared counter is also active.

## Execution and cleanup

The [captured reference FOR contract](reference-for-counters.md) applies to both
structured code and the label dispatcher:

1. Capture the scalar reference once, before evaluating its initial expression.
2. Assign the checked initial value, evaluate the final expression once and
   capture the start/stop iterator state.
3. Retain the selected leaf and bounds across same-loop jumps and pause/resume.
4. Clear only that scalar when the loop ends or its scope unwinds.

Changing index variables does not retarget iteration or cleanup. Initial-value
failure leaves previous private storage intact. After initial assignment,
final-bound failure, body/callback errors, RETURN, ABORT, stop or budget
exhaustion clear the selected leaf. Other private fields and completed outside
effects remain intact. A RETURN value or aggregate snapshot is captured before
counter cleanup.

Exiting nested loops clears their selected leaves from inner to outer. Direct
entry to a new FOR or USING scope remains rejected. Re-entering the USING block
creates a fresh private value. Context JSON retains declared values and service
state; it does not publish private temporary variables, captured references,
iterators or suspended stacks.

## Reports and evidence

Private `reference_for_counters` rows retain `root=null` and add
`protection_root` plus `provenance="private_temporary"`. Reference aliases share
the same protection identity; independent copies differ. Named counter rows
and USING source/capture provenance keep their previous contracts.
`private_using_counter_policy` describes these rules and the conservative escape
boundary. It reports `controller_validated=false`.

The [authored tests](../tests/test_private_using_counters.py) exercise both
execution engines, nested references/copies, aliases, retained handlers,
transitive calls, initialization order, jumps, failures, RETURN snapshots,
cooperative cleanup, linked routines and JSON boundaries. This is an offline
Pythonic extension. The legacy translator retains its selector/counter
restrictions; no native or controller behavior is claimed.
