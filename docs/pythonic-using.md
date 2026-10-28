# Pythonic USING scopes

Pythonic USING supports lexical nesting and dotted, indexed or grouped selectors
for named STRUCTURE and supported built-in record storage. Selectors capture
references once on each entry. Inner fields override matching outer fields;
unmatched outer fields remain available. Leaving a block restores the enclosing
bindings. These are chosen offline namespace and selection rules, without a
native timing or alias-lifetime claim. See [captured selectors](using-selectors.md)
for index effects, callbacks and executable CLI examples.

```karel
PROGRAM fields
TYPE child_t=STRUCTURE value: INTEGER ENDSTRUCTURE
     packet_t=STRUCTURE child: child_t value: INTEGER ENDSTRUCTURE
VAR packet: packet_t
    outer_seen: INTEGER
BEGIN
  USING packet DO
    value=1
    USING child DO value=7 ENDUSING
    outer_seen=value
  ENDUSING
  WRITE(outer_seen,packet.child.value,CR)
END fields
```

This finishes with `PACKET.VALUE=1`, `PACKET.CHILD.VALUE=7`, `OUTER_SEEN=1`, and
one output request ` 1 7\n`. The [complete example](../examples/pythonic_using.kl)
also uses qualified selectors and a function whose name matches a field, with
independent [expected values](../examples/pythonic_using.expected.json) and
[expected output](../examples/pythonic_using.write.expected.json).

## Lookup and selectors

| Source form | Pythonic behavior |
| --- | --- |
| `USING packet.child DO ... ENDUSING` | Expose direct fields of the existing record at that dotted path. |
| `USING packet DO USING child DO ... ENDUSING ENDUSING` | Resolve the inner selector `child` through the enclosing scope, then expose its fields. |
| `USING left,right DO ... ENDUSING` | Right-most matching selector wins. Resolve all selectors against enclosing bindings only; earlier selectors in this same list do not affect later selector lookup. |
| Unmatched inner field name | Fall back to an enclosing field alias, then ordinary lexical lookup. An uninitialized matching inner field does not fall back. |
| Field matching a global/local constant | The field wins inside the scope. Constants retain their original value outside it. |
| Field matching a function name | A bare expression reads the field; an explicit `name(...)` expression invokes the function. Procedure call statements use their call context. |

Selectors must designate existing named STRUCTURE or supported built-in record
storage. Dotted paths, subscripts (including calls inside indexes) and grouping
are accepted. Each selector reference is evaluated once, left-to-right, before
the body; changing an index later does not retarget the selected fields.
Function-result and computed aggregate selectors remain unsupported. Only direct fields of selected structures are exposed; nested fields
need a dotted path or another USING. A field cannot act as a FOR counter. CASE
labels still require compile-time constants: a name shadowed by a field cannot
become a runtime CASE label; use a noncolliding constant name.

## Storage, calls and control flow

Aliases resolve lexically before type, function-call, effect and control-flow
analysis. Inserted roots are not resolved through aliases again. Captured
references retain the original global/formal root for mutation checks; selector
calls contribute their ordinary effects once at entry. Fields refer to existing
storage without a structure copy. Existing whole-record/array assignment
preserves descendant aliases when copying into stable aggregate storage.
Handler predicates/actions freeze references from their enclosing USING at
handler definition, including when the same block is entered again.

Bare field arguments keep ordinary references; grouping and expressions use the
existing checked value rules. Transitive global/formal writes retain the original
structure root, so aliases cannot hide writes from [FOR checks](pythonic-for.md).
A callee has its own lexical scope and does not inherit its caller's USING aliases.
Type, initialization, ASCII, capacity, ownership and POSITION protection checks
remain in place.

RETURN, errors and ABORT use ordinary routine cleanup and retain earlier writes.
Jumps out to ancestors restore the outer lexical bindings. [Nested/sibling
structured transfers](nested-jumps.md) can enter IF/WHILE/REPEAT/SELECT bodies
while retaining existing captures. Entering a new USING scope without its capture
and labels/jumps inside FOR bodies remain blocked. See
[evaluation order](evaluation-order.md) and [STRING values](pythonic-strings.md).

## Reports and compatibility

`using_scopes` records a scope `id`, `parent` id (or null), and `depth` (outermost
is zero). `source_selectors` retains normalized source spelling; `variables`
contains resolved absolute paths. `field_bindings` lists all active bindings,
including inherited fields, while `resolved_uses` records each source-located
alias use. Each binding value and `resolved_uses.variable` is the containing
STRUCTURE's path; combine it with the field name for the full field path.
`capture_once` and `selector_types` describe entry evaluation and resolved layouts.
`using_policy` describes these choices.

Older versions rejected nesting, dotted selectors and namespace collisions. Those
cases now follow the rules above; scalar/non-record selectors and unsupported
control flow still fail explicitly. Conservative tests remain internal for the
future strict milestone. See the [semantic ledger](semantics/pythonic_using_semantics.json)
and [execution tests](../tests/test_pythonic_using.py).
