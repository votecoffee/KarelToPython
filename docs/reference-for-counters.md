# Captured INTEGER FOR counters

[Computed USING records](computed-using.md) can now supply isolated private
INTEGER counters under the [private counter contract](private-using-counters.md).
They use internal whole-root protection identities without inventing declared
storage or copying back. Named record fields retain the contract below.

Pythonic mode accepts exact INTEGER scalar storage as a FOR counter: a declared
variable, STRUCTURE field, ARRAY element, indexed record field or bare field
resolved through USING. The converter captures one writable reference before
evaluating the initial value. Iteration and cleanup keep that reference even if
index variables change.

```karel
counters[2]=99
slot=1
total=0
FOR counters[slot]=1 TO 3 DO
  slot=2
  total=total+counters[1]
ENDFOR
```

The loop totals six. It clears `counters[1]`, while `counters[2]` remains 99.
Changing `slot` does not move the loop counter or clear a different element.

This is a portable Pythonic extension. The reference FOR syntax restricts native
counters to INTEGER variables and specifically excludes system variables and
ARRAY elements. Field/element behavior here follows the explicit capture and
write-proof policy below, without claiming native compiler/controller support.
The historical strict parser retains its previous bare-variable restrictions;
public strict mode remains future work.

## Selectors, order and storage

Headers support dotted fields and ordinary comma-separated ARRAY indexes,
including up to the existing three logical dimensions. Index expressions may
call typed source functions and run once, in ordinary left-to-right reference
evaluation order. Whole aggregate, grouped/computed root and function-result
counters are unavailable. The selected leaf must be exact INTEGER; BYTE, SHORT,
REAL and BOOLEAN do not become INTEGER counters through promotion.

On normal entry:

1. Capture the selector's ordinary scalar reference once.
2. Evaluate the initial expression and assign its checked value to that reference.
3. Evaluate the final expression once, then capture the resulting counter/start
   and inclusive stop for the ordinary TO/DOWNTO iterator.
4. Write each iterator value through the captured reference.
5. Clear only that scalar on loop completion or scope unwinding.

The initial/final expression can observe or change index variables without
retargeting the reference. Existing Pythonic header rules still permit the final
expression to observe or update the newly initialized counter before the start
is captured. Bounds are not re-evaluated by same-loop GOTO transfers.

USING resolves a bare counter field to its captured record storage. A global
variable with the same spelling remains a separate cell. Nested/rightmost USING
priority and existing selector capture rules remain unchanged. Record siblings
may remain uninitialized: only the counter's ordinary INTEGER leaf needs storage.
PATH/FILE/QUEUE roots, CONFIG-domain subfields, readonly POSITION orientation
descendants and acquired controller/port storage remain invalid counter targets.

## Conservative write proof

While a counter is active, its entire declared storage root is protected. This
keeps aliases safe without pretending every dynamic index is disjoint:

```karel
FOR item.count=1 TO 3 DO
  item.other=9       -- rejected: same protected root ITEM
ENDFOR
```

The same guard applies to other ARRAY elements, whole-root assignments, READ and
service outputs, conversion outputs, indirect variable writes and potentially
writable routine arguments. Nested counters cannot share a root, even if their
fields or constant indexes differ. Counters on independent roots may nest.

Routine analysis tracks direct and transitive writes, including FOR initialization
through fields/elements. Bare references into an active root are allowed only
when the formal is proved readonly. Grouped value copies are detached and may
be edited privately under the existing aggregate rules. Ordinary readonly
observations, expressions and writes to independent roots remain usable.

Global aggregate counter roots additionally reject direct or transitive external
routine calls whose global writes are unknown at translation time. Fresh local
roots are isolated from no-argument external globals; passing them as writable
references remains blocked. Parameterized routines require a fresh local counter
root, so formal roots and nonlocal/global roots are excluded there. Existing
bare scalar counter policies retain their previous contracts.

Condition actions and connected timers that can write any part of the root also
block the counter. These are conservative source proofs, without a claim that
arbitrary host callbacks or other independently driven programs cannot change
supplied storage. Explicit source calls must still satisfy the transitive and
reference checks.

## Jumps, failures and cooperative lifetime

Both ordinary structured Python and the [FOR label dispatcher](for-jumps.md) use
the same captured references. Same-active-loop jumps retain the selected cell,
current value and iterator. Exiting loops clears their captured scalars from
inner to outer before the target executes. Direct entry into new FOR or USING
scopes remains rejected.

Selector failure makes no initial assignment. Initial-expression/assignment
failure preserves the selected leaf's previous storage and earlier effects.
After initial assignment succeeds, final-bound failure, RETURN, ABORT, body or
callback errors, budget/call-depth exhaustion and stop clear that scalar. Other
record fields and ARRAY elements are retained. RETURN values and aggregate
snapshots are captured before cleanup, so a returned independent record can
retain the final observed counter value.

Pause/resume keeps the live reference and iterator. If a selected ARRAY index
changes before a pause, resume and stop still use the original selected cell.
A pause during the initial expression has not registered cleanup; a pause during
the final expression has. These rules also apply in typed source routines.

Context JSON retains ordinary scalar/aggregate values, including a currently
initialized leaf. It does not serialize the captured Python reference, iterator,
routine stack or paused dispatcher as an executable checkpoint.

## Reports and evidence

`reference_for_counters` records each counter's selector text, declared root,
source line/column, selector kind and capture/cleanup/root-protection policy.
Dispatcher `for_scopes.counter` retains the full selector description rather than
only its final field name. Pure type inspection does not duplicate selector calls.
`reference_for_counter_policy` describes the accepted domains and remaining
proof boundaries; the current FOR/USING policies identify the same behavior.

The [authored regressions](../tests/test_reference_for_counters.py) cover both
execution engines, selector/bound order, USING, readonly/writable aliases,
transitive/handler/timer guards, partial records, RETURN snapshots, GOTO,
pause/resume/stop and JSON values. These establish the documented offline
Pythonic interpretation, separately from native compiler and controller evidence.
