# Pythonic FOR calls and cleanup

Since 0.59.0, Pythonic FOR loops using global counters can call helpers whose
transitive write effects exclude those counters. Bare counter arguments can
bind to proven read-only formals. Initialized counters clear on all scope exits.
These are chosen offline policies, with no native counter-state or timing claim.

```karel
PROGRAM loops
VAR i,total: INTEGER
ROUTINE add(value: INTEGER)
BEGIN
  total=total+value
END add
BEGIN
  total=0
  FOR i=1 TO 3 DO add(i) ENDFOR
  WRITE(total,CR)
END loops
```

This produces `TOTAL=6`, an uninitialized `I`, and one output request ` 6\n`.
The [complete example](../examples/pythonic_for.kl) also returns a value from a
global-counter loop and checks cleanup, with independent
[expected values](../examples/pythonic_for.expected.json) and
[expected output](../examples/pythonic_for.write.expected.json).

## Calls and counter arguments

The analysis follows direct assignments, FOR initialization and built-in output
arguments, then propagates potential global and formal writes through recursive
calls until they stop changing. Writable actuals are mapped back to caller
globals or formals. The proof is conservative: a potential write in a dead branch
still counts. A local declaration shadowing a global name has separate storage;
it does not count as a write to that global.

| Form inside a FOR body | Pythonic behavior |
| --- | --- |
| Helper writing unrelated globals | Allowed; ordinary effects remain visible. |
| Helper potentially writing an active global counter | Translation error, including transitive writes through parameters or nested loops. |
| `inspect(i)` with a transitively read-only INTEGER formal | Pass the existing counter reference; reads observe the current iteration. |
| `change(i)` with a potentially writable INTEGER formal | Translation error. |
| `change((i))` or `change(i+0)` | Independent writable value; no copy-back. |
| INTEGER counter passed to a REAL formal | Independent promoted value, including through forwarding routines. |
| Global counter in the program or a parameter-free routine | Supported with the write proof above. |
| Formal counter, or nonlocal counter in a parameterized routine | Still rejected; use a fresh local counter. |

Fresh local counters remain usable in any internal routine. The existing
direct-counter-assignment and nested-counter-reuse guards remain.
[Labels and jumps](for-jumps.md) now retain active loop bounds and clear counters
when leaving their scope; entering an unstarted FOR remains blocked.
[Reference counters](reference-for-counters.md) additionally support captured
INTEGER fields, ARRAY elements and USING fields, with conservative aggregate-root
write/reuse guards. Formal/nonlocal roots in parameterized routines and unproven
external calls over global aggregate counters remain rejected.
Conversion outputs cannot write active counters. The analysis covers
translated KAREL calls; host callbacks retain their ordinary external side effects.

## Bounds and cleanup

Bounds retain the chosen [evaluation order](evaluation-order.md): evaluate the
counter selector first for reference counters under their capture contract, then the
initial expression once, store it in the counter, then evaluate the final
expression once. Capture the resulting counter/start and inclusive stop for
Python range iteration. A final-bound function may read or change the newly
initialized counter; this affects the captured start. Nested bounds may not
write an already active outer counter.

After the initial assignment succeeds, generated `try/finally` clears the counter
on normal or empty completion, RETURN, ABORT, final-bound failure, body errors,
callback failure/interruption and step/call-depth exhaustion. Nested scopes unwind
from inner to outer. If the initial expression or checked initial assignment
fails, that loop has not entered its cleanup scope: previous counter storage and
earlier expression effects remain.

RETURN evaluates, validates and captures its result before cleanup. Scalar,
STRING and independent aggregate results survive counter clearing and routine
frame destruction. A failing RETURN expression still unwinds the loop scopes.
Non-counter changes, nested output and callback effects are retained; there is
no rollback. ABORT remains sticky for the instance.

## Reports and compatibility

`routine_effects[].potential_global_writes` lists potential global roots and
`potential_parameter_writes` lists formals. Root-level aggregate effects can be
conservative; grouping/value copies prevent caller mutation. `for_policy`
describes write proof, read-only references, bound order and cleanup.

Earlier versions rejected all global-counter calls and all bare counter
references. Errors could leave an observable initialized global counter behind.
Retranslation now accepts the cases above and clears initialized counters during
unwinding. The preserved conservative tests remain internal for the future strict
milestone. See the [semantic ledger](semantics/pythonic_for_semantics.json) and
[execution tests](../tests/test_pythonic_for.py).
