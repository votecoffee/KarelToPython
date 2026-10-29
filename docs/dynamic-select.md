# Dynamic SELECT case expressions

Pythonic SELECT accepts typed scalar expressions in CASE lists. Variables,
fields, ARRAY elements, ordinary operators and typed functions can provide case
values alongside existing constants. Numeric, BOOLEAN and ASCII STRING
comparison categories retain their [scalar SELECT rules](scalar-select.md).

```karel
key=7
label=7
SELECT key OF
  CASE(label, calculate_label()): result=42
  CASE(other_label): result=99
  ELSE: result=0
ENDSELECT
```

This is an explicit Pythonic extension. The manual and preserved legacy
translator require INTEGER selectors and constant INTEGER cases.

## Evaluation contract

1. Evaluate and validate the selector once, capturing its scalar value.
2. Evaluate and validate every case expression once, in source order: clauses
   from top to bottom, then values from left to right within each CASE list.
3. Choose the first matching clause after the complete table succeeds. Otherwise
   run ELSE, or raise the existing no-match error when ELSE is absent.

Later case expressions still run when an earlier case would match. This eager
policy extends the existing complete-table validation contract. Case functions
can change globals, but cannot change the already captured selector. Normal
short-circuit evaluation still applies inside each individual expression.

Unknown or invalid selector data fails before any case effects. A case failure
prevents all case bodies and ELSE from running. Earlier selector/case effects
remain visible; later case expressions are skipped after a failure. A later
invalid category is rejected at translation even after an earlier constant match.
BOOLEAN never becomes a numeric value, strings retain exact case-sensitive
comparison, and REAL matching uses finite ordinary Python equality.

## Effects, lifetime and state

Existing routine, alias, active FOR-counter and service-effect checks apply to
case expressions. Dynamic labels cannot write protected counters indirectly or
bypass readonly POSITION fields. Aggregate and resource labels remain blocked.
Local constants remain constant labels; lexical USING fields are dynamic labels.

Structured code, label dispatch and cooperative tasks use the same order. A
pause in a case function retains the captured selector and earlier case values.
Resuming a body does not reevaluate dispatch. Stop, ABORT, errors and RETURN
retain ordinary frame and counter cleanup. A permitted GOTO directly into a
case body bypasses selector/case evaluation under the existing label-entry rules.
Saved context retains values, with suspended execution still excluded.

## Reports and examples

Each `selects` row retains `case_values` for constants. A dynamic slot is `null`;
`case_expressions` distinguishes it using `dynamic`, source location, expression
kind and declared type. `case_types`, `dynamic_cases` and `case_evaluation` record
the comparison and eager policy. Generated code retains explicit categories and
checked primitive equality. `dynamic_select_policy` describes the extension.

The [standalone example](../examples/dynamic_select.kl) records selector/case
order. The [linked project](../examples/select_numeric_xml_project/main.kl)
combines dynamic case functions, XML record input and numeric variable transfers.
Public strict mode remains future work; no native SELECT equivalence is claimed.
