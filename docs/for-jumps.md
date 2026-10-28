# Pythonic jumps in FOR loops

Pythonic mode accepts labels and GOTO/GO TO inside FOR bodies, including their
nested IF, WHILE, REPEAT and SELECT branches. A jump can stay within an already
initialized loop or leave active loops. Entry directly into a new FOR body
remains rejected because it would bypass counter initialization and captured
iteration bounds.

This is a deliberate Pythonic extension. MARRC75KR07091E Rev N A.6.3 warns against
labels and GOTO inside native FOR loops because of controller stack effects.
A.7.28 requires targets in the same program/routine body. The implementation
preserves that body boundary and uses explicit Python lifetime scopes; it does
not claim native compiler/controller acceptance for the extended forms. Public
strict mode remains a future milestone, and the internal historical FOR guard
is retained.

```karel
total=0
FOR i=1 TO 3 DO
  IF i=3 THEN GOTO finished ENDIF
  total=total+i
ENDFOR
finished:: counter_cleared=UNINIT(i)
```

The result is `total=3` and `counter_cleared=TRUE`. The counter is cleared before
the target executes. See the [authored example](../examples/for_jumps.kl) and
[linked routine example](../examples/for_jumps_project/main.kl).

## Entry, jumps and continuation

| Transfer | Pythonic behavior |
| --- | --- |
| Label or jump within the same active FOR | Retain the current counter and captured iterator; skip intervening statements. |
| Body end reached after a jump | Advance the existing iterator and begin the next ordinary iteration. |
| Exit an inner FOR while staying in an outer FOR | Clear the inner counter before the target; retain the outer counter/iterator. |
| Exit several FOR scopes | Clear exited counters from inner to outer before the target. |
| Jump to a label before a FOR statement | First clean exited scopes, then execute the target suffix and normal FOR initialization when reached. |
| Jump over an entire FOR | Leave its previous counter storage untouched; no loop scope was initialized. |
| Enter a FOR body from outside or a sibling FOR | Reject with E_GOTO_FOR, including entry through nested branches. |

Forward and backward same-loop jumps do not re-evaluate the initial/final bounds.
Normal entry retains the existing Pythonic order: evaluate the initial expression,
assign the counter, evaluate the final expression once, then capture the resulting
counter/start and inclusive final bound. The final expression can observe or
change the initialized counter under the existing header expression rules.
TO/DOWNTO, empty ranges and checked INTEGER assignment retain their existing
behavior.

A label at the end of a FOR body continues through the ordinary iteration step.
Reaching a previously skipped loop header initializes that loop normally; a
stale earlier execution never permits direct entry into its body. Nested/sibling
[structured label entry](nested-jumps.md) can skip IF/WHILE/REPEAT/SELECT header
tests only when the required active FOR scopes are already present.

## Capture and counter proofs

A target's FOR scope chain must be a prefix of the source's FOR chain. Scope
identity is lexical, rather than the counter variable's spelling. Two sibling
loops using the same counter are distinct scopes. Cross-program/routine labels,
missing/duplicate labels and identifier conflicts retain their normal errors.

The target USING capture chain must also prefix the source chain. Existing
captures survive same-scope jumps, and exiting a USING restores the target's
lexical field bindings. A jump cannot capture a new selector, even if it names
the same record storage as an earlier USING.

Every source statement remains type/effect checked, including unreachable or
skipped statements. FOR counters remain direct INTEGER globals in permitted
parameter-free contexts or fresh routine-local INTEGER variables. Formal counters,
nonlocal counters in parameterized routines, shared nested counters and shadowing
USING fields remain rejected. Direct/indirect output writes, potentially writable
reference arguments, transitive global writes and handler/timer counter writes
retain the same protections as structured FORs. Readonly counter observations
remain usable.

## Cleanup and cooperative lifetime

Cleanup is registered only after the initial counter assignment succeeds. If the
initial expression or checked assignment fails, the old counter and prior effects
remain. Once registered, final-bound failure, RETURN, ABORT, body/callback errors,
budget/call-depth exhaustion and stop unwind that counter. Nested scopes unwind
from inner to outer. RETURN values are evaluated and checked before cleanup and
routine-frame removal.

Cooperative pause/resume retains the dispatcher location, current counter and
iterator. It does not replay skipped source or re-evaluate bounds. A pause during
the final-bound call retains a registered cleanup scope even before its iterator
exists; stopping there clears the counter. A pause inside the initial expression
has not yet registered that loop, so stopping preserves its earlier counter value.
Caller and linked routine loops retain independent frames and counters.

Jumps and iterations charge ordinary execution steps; a same-iteration GOTO cycle
remains bounded. The internal iterator/frame stack is live Python execution
state, not context JSON or a persisted instruction pointer. Saving values does
not reconstruct a suspended loop or routine. Native preemption, stack layouts,
motion and controller scheduling remain unavailable.

## Reports and evidence

Programs without labels keep structured Python output. Labelled Pythonic bodies
lower FORs to `for_enter`, `for_next` and `for_exit` dispatcher nodes. Their
`control_flow` reports contain:

- Per-body `for_scopes`: enter-node ID, counter, source line/column and parent IDs.
- Per-node `for_scopes`: the active lexical scope IDs required by that node.
- Per-jump `retained_for_scopes` and `exited_for_scopes`, with exits in cleanup order.

`control_flow.jump_policy` is `body_labels_no_new_for_or_using`.
`for_jump_policy` describes capture, continuation, cleanup and retained barriers;
`for_policy` identifies the same supported jump forms. Existing source-map include
origins resolve expanded graph locations to physical source files.

The [authored regressions](../tests/test_for_jumps.py) cover same-loop/backward
transfers, nested exits, captured bounds, initial/final failures, recursion,
counter/capture proofs, callbacks, pause/resume/stop, includes and linked calls.
These establish translation and offline execution only, with the documented
Pythonic interpretation of native FOR/GOTO warnings.
