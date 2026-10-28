# Nested and sibling label transfers

Pythonic `GOTO label` and `GO TO label` can enter nested or sibling IF, WHILE,
REPEAT and SELECT bodies within the same program or routine. Labels still have
one body-wide namespace. This extends the existing checked control-flow dispatcher;
programs without labels keep ordinary structured Python output.

```karel
GOTO selected_branch
IF uninitialized_flag THEN
  skipped=99
  selected_branch:: result=7
ENDIF
```

The transfer reaches the label directly. It does not read the IF condition or
execute `skipped=99`. Code after ENDIF runs normally. The source is still parsed
and type-checked in full, including statements that this transfer skips.

See the authored [structured-entry example](../examples/nested_jumps.kl),
[captured-scope example](../examples/scoped_jumps.kl) and
[linked routine project](../examples/nested_jump_project/main.kl).

## Entry and continuation

| Target | Direct-entry behavior |
| --- | --- |
| IF then/else body | Skip the condition and earlier body statements; run the target suffix and continue after ENDIF. |
| WHILE body | Skip its initial condition and earlier body statements; at body end, evaluate the ordinary WHILE condition and restart from the body beginning when true. |
| REPEAT body | Skip earlier body statements; evaluate UNTIL at body end and restart from the full body beginning when false. |
| SELECT case/else body | Skip selector evaluation and case dispatch; run the target suffix and continue after ENDSELECT, without implicit case fall-through. |
| Nested combination | Enter the deepest target label directly; subsequent successors unwind through ordinary enclosing continuations/back edges. |

The same rules apply to a transfer from another branch, case or loop body.
Transfers back to a loop-body label skip the prefix again. Transfers to a label
before a structured statement execute that statement's ordinary entry behavior.
Labels at the end of an empty block lead directly to its normal continuation.

Direct entry does not synthesize initialization, handler definitions, connected
timers, open files or other skipped effects. If later code uses state that was
never initialized/prepared, the normal runtime error remains. SELECT no-match
errors still apply when SELECT executes normally; direct case entry does not
execute SELECT dispatch.

## USING capture proof

A USING body depends on references captured by its USING statement. A jump's
target USING scope chain must be a prefix of its source USING chain. This permits
same-scope transfers and exit to outer captures, while rejecting entry to any
new USING body. The guard is based on lexical scope identity, not equal storage
names or a stale capture from an earlier execution.

```karel
USING items[pick()] DO
  IF TRUE THEN
    GOTO other_branch
  ELSE
    other_branch:: value=7
  ENDIF
ENDUSING
```

Here `pick()` executes once at USING entry. The sibling transfer retains that
capture. By contrast, a jump from outside directly to `other_branch` is rejected.
A label before the USING statement is a valid target and runs its capture
normally. Exiting an inner USING restores the target's outer lexical bindings.
Right-most field priority, protected POSITION columns, ordinary aliases and
handler capture rules remain unchanged.

Only IF, WHILE, REPEAT and SELECT are admitted as newly entered block kinds.
An already active FOR can contain labels and transfers under the
[FOR jump contract](for-jumps.md); a transfer cannot enter a new FOR scope.
Other future block kinds require an explicit entry contract before acceptance.

## Retained checks and execution

- Labels and jumps within active FOR bodies preserve their captured bounds and
  iteration state; exits clear the counters of exited loops. Entry into any new
  FOR scope remains rejected. Jumping over an entire FOR leaves its counter untouched.
- A target must exist in the same program/routine body. Duplicate labels and
  conflicts with declared identifiers still reject. Calls use the callee's labels.
- Condition actions cannot contain labels, GOTO or RETURN. A normal body can jump
  past a handler definition, but no handler is created by skipping it.
- Unreachable source still receives ordinary syntax/type/effect validation.
  Transitive FOR-counter protection and exact routine interfaces remain in force.
- Jumps consume the ordinary execution step budget. Cycles remain bounded.
  Runtime errors and RETURN/ABORT keep their normal routine-frame cleanup.
- Cooperative pause/resume retains the dispatcher location and existing captures;
  it does not replay the skipped prefix. Stop uses ordinary task cleanup.

This does not introduce instruction-pointer persistence. Context JSON stores
values, while a live paused generator retains its own continuation. Native task
preemption, controller addresses and binary execution are outside the model.
Historical strict-mode implementation retains the previous same-block/ancestor
entry rule; public strict mode remains a future milestone.

## CLI, reports and evidence

```sh
python -m karel2py examples/nested_jumps.kl -o nested_jumps.py --report jumps.json
python nested_jumps.py --state-out jump-state.json
python nested_jumps.py --context jump-state.json --state-out jump-state.json
python -m karel2py examples/scoped_jumps.kl --check
python -m karel2py.project examples/nested_jump_project --entry MAIN
```

`control_flow` retains the generated dispatcher graph and per-body labels. Each
body now adds `jumps`, in source order, with target label, expanded source/target
line/column/block paths and `entry_kind` (`same_block`, `ancestor`, `nested` or
`sibling`). Graph edges remain the executed transfer targets. Programs without
labels report an empty transfer list and retain the structured engine.

`nested_jump_policy` records supported block kinds, capture proof and boundaries.
For included source, use the existing source-map include origins to resolve
physical files and lines. These reports are metadata, not native addresses.

The manual basis is MARRC75KR07091E Rev N sections 2.1.5 (labels), A.7.28 (GO TO)
and the FOR restrictions. The [ledger](semantics/nested_jump_semantics.json)
records the accepted Pythonic interpretation and verification. Authored tests
check skipped effects, continuation/back edges, aliases, routines, includes and
cooperative lifetime. Passing translation/offline execution does not establish
native compiler acceptance for every target or controller/runtime equivalence.
