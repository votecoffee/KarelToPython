# Pythonic evaluation order

Pythonic mode lets functions compose in operators, argument lists, array
subscripts, conversion procedures and FOR bounds. The rules below choose a
deterministic offline behavior. They do not claim native KAREL evaluation order.

```karel
PROGRAM order_demo
VAR count,result: INTEGER flag: BOOLEAN
ROUTINE next_value: INTEGER
BEGIN
  count=count+1
  RETURN count
END next_value
ROUTINE stop_now: BOOLEAN
BEGIN
  ABORT
  RETURN TRUE
END stop_now
BEGIN
  count=0
  result=next_value*10+next_value
  flag=TRUE OR stop_now()
END order_demo
```

This finishes with `COUNT=2`, `RESULT=12` and `FLAG=TRUE`. The second operand of
OR is skipped. The [complete authored example](../examples/pythonic_order.kl)
also exercises STRING composition, target indexes and callable FOR bounds, with
[expected values](../examples/pythonic_order.expected.json) and
[expected output](../examples/pythonic_order.write.expected.json).

## Operands and arguments

Evaluate ordinary operands and actual arguments once, from left to right.
Each scalar read captures its value at that point. VECTOR operands are checked
and copied before evaluating the next operand, so a later call cannot change
an earlier operand through shared storage.

BOOLEAN `AND` and `OR` use Python short circuiting: false AND skips the right
operand, and true OR skips it. INTEGER `AND` and `OR` are eager bitwise operations.
All branches still undergo translation-time syntax and type checks. Constant
declarations retain their existing compile-time expression validation.

Bare variable, field and array-element actuals capture live references. If a
later argument changes that storage, the callee sees the changed value. Grouping
an actual captures an independent value before the next argument:

| Call, starting with `n=1` | If `change()` sets `n=9` before returning |
| --- | --- |
| `use(n,change())` | First parameter refers to `n` and reads 9 in the callee. |
| `use((n),change())` | First parameter owns a copy containing 1. |

An indexed reference keeps the selected cell even if a later actual changes the
index variable. Existing aggregate copy, nominal type, initialization and STRING
capacity rules remain. Whole ARRAY value arguments remain unsupported.

## Assignments and subscripts

For `values[index()]=compute()`, evaluate `compute()` first and capture its result.
Then evaluate the target base and indexes, and assign. Aggregate right sides
are captured by checked independent copies before any target effects. An
incomplete aggregate fails before target calls run. Destination type, shape,
capacity and write-protection checks still apply when storing the result.

For a read, reference or assignment target, evaluate the array base first, then
its comma-separated subscripts once from left to right. Bounds checks happen
after the subscript expressions have run. Consequently, a later subscript can
have effects even when an earlier numeric subscript is out of range.

## Conversions and loops

Conversion procedures evaluate inputs and output-reference expressions in source
order before entering the procedure. Bare aggregate inputs remain live storage,
so later reference-index functions can change their contents before conversion.
UNPOS overlap checks, exact output types and explicit joint-axis context still
apply before output writes. An index function's earlier effects are retained if
the subsequent procedure fails.

FOR evaluates the initial expression once, stores it in the counter, then
evaluates the final expression once. The final expression can read the initialized
counter. The resulting counter value and inclusive stop are captured for Python
iteration; changes to the counter during final-expression evaluation therefore
affect the first iteration. Normal exit clears the counter. Existing fresh-local
counter requirements for routine calls in a FOR body remain in place.

## Failures and compatibility

A runtime error or ABORT stops the current evaluation. Later operands, arguments,
target indexes and outer calls do not run. Earlier writes, mutations and delays
remain visible, and routine frames unwind. A nested WRITE request can occur
before a containing WRITE finishes rendering.

Retranslating with 0.54.0 can change behavior: Boolean expressions previously
evaluated eagerly, and assignment target references previously resolved before
their values. The generated report's `evaluation_policy` records the new rules.
The older ordering rejections remain tested through the internal conservative
compiler as preparation for the future strict milestone. Public strict mode
remains unavailable while Pythonic coverage takes priority.

See the [semantic contract](semantics/pythonic_order_semantics.json) and
[mode roadmap](numeric-modes.md).
