# Acyclic forward constant references

Pythonic mode resolves complete module CONST sections before types, global
variables and routine interfaces. Each routine resolves its own CONST sections
before local VAR declarations, including declarations earlier in the source.

```karel
CONST count=later later=2
TYPE row_t=ARRAY[count]OF INTEGER
VAR values:row_t
ROUTINE work
VAR word:STRING[width]
CONST width=length length=3
BEGIN word='abcdef' values[2]=7 END work
BEGIN work END
```

This is an authored offline extension. Source acceptance, controller compilation,
native storage and runtime equivalence require separate evidence. Public strict
mode remains a future milestone; internal legacy ordering is preserved.

## Dependency resolution

An iterative dependency walk evaluates each prerequisite before its users. Long
finite global and local alias chains do not consume Python recursion. Shared or
repeated dependencies are evaluated once per declaration, rather than treated as
cycles. Source-order values remain immutable scalar constants without runtime cells.

Every definition is checked, including unused routines and declarations. Unknown
or nonconstant names produce E_CONSTANT at the reference. Self/mutual cycles
produce E_CONSTANT with a bounded dependency path. A false Boolean operand does
not hide an invalid dependency; constant operators retain their eager policy.

Expressions retain the existing checked scalar evaluator: literals, predefined
constants, grouping, unary and binary operators. [Pure scalar built-in calls](constant-builtins.md)
now use an explicit 17-function whitelist, with checked arity and bounded nested
evaluation. Their argument references participate in the same dependency graph.
User/external calls, storage selectors, system reads, Python evaluation and
callbacks remain excluded. INTEGER ranges, MININT spelling, finite REAL values, ASCII
STRING bounds and Boolean domains retain their existing diagnostics. MAXINT may
remain a constant but cannot become ordinary initialized INTEGER storage.

## Lexical scopes and schemas

Local constants see module constants and their own declaring routine's constants.
They never inherit a caller or sibling routine's names. Namespace, label, USING,
immutability and output-reference checks remain unchanged. Parameters resolve
before local constants; duplicate parameter/constant/variable names still fail.

Global and named ARRAY dimensions, STRING capacities, group annotations and
routine result schemas may use resolved module chains. Local VAR schemas may use
resolved local chains across repeated CONST/VAR sections. Global types and routine
interfaces cannot use local constants. ARRAY ranks, capacities, type identities,
resource rules and the [forward-type policy](forward-types.md) remain separate.
Constants used by SELECT, FOR bounds, formatting or source services follow their
ordinary runtime contracts after compile-time resolution.

## Reports, linking and saved data

Reports expose forward_constant_policy. global_constants and local_constants
retain declaration order, resolved values and physical source origins.
constant_dependencies records declaring scope, routine, referenced constant,
dependency scope, source position and whether the declaration occurs later in
source. constant_resolution_order records actual dependency-first evaluation.
Included fragments retain original file/line/column and include-stack metadata.

Each supplied source module resolves its own graph before normal exact linked
interface checks. No external constant discovery or binary environment is added.
Generated modules contain resolved values; saved JSON contains ordinary variable
data without expression graphs, pending evaluators or writable constant slots.

See the [semantics ledger](semantics/forward_constant_semantics.json),
[regressions](../tests/test_forward_constants.py), and authored examples for
[values](../examples/forward_constant_values.kl),
[shapes](../examples/forward_constant_shapes.kl),
[local declarations](../examples/forward_constant_locals.kl),
[control flow](../examples/forward_constant_control.kl),
[linked routines](../examples/forward_constants_linked/main.kl) and
[linked ARRAY results](../examples/forward_constants_result/main.kl).
