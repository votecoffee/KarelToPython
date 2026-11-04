# Acyclic forward type references

Pythonic mode resolves references to later module TYPE definitions before global
allocation or source execution. This covers transparent aliases, named ARRAY
elements, STRUCTURE fields, PATH NODEDATA/PATHHEADER and routine interfaces.

```karel
TYPE row_t=ARRAY[2]OF item_t
     item_t=STRUCTURE count:number_t ENDSTRUCTURE
     number_t=INTEGER
VAR items:row_t
BEGIN
  items[1].count=7
END
```

All TYPE sections in the module contribute complete definitions. A routine may
precede the types used by its parameters, locals or named/anonymous ARRAY result.
The existing constant-expression rules still govern STRING capacities, ARRAY
dimensions and group annotations. No source routine or callback is executed
to discover a type, dimension, owner or storage value.

## Dependency and identity rules

An iterative dependency walk resolves each required definition before its users.
It does not consume Python recursion for transparent alias chains. All definitions
are checked, including unused branches. Unknown names produce E_TYPE at the
reference; cycles produce E_TYPE with a bounded dependency path. Self-reference
does not create recursive storage. Missing declarations are never synthesized.

Aliases preserve the original ARRAY/STRUCTURE identity, STRING capacity, joint
width and field layout. A fresh ARRAY or STRUCTURE definition retains its own
nominal name. Source field order remains unchanged. Exact arguments still borrow
references, grouped values still copy, and ordinary compatible source conversions
keep their separate receiver-schema rules.

Resolved user_types dictionaries and type_aliases report rows retain source
declaration order. type_resolution_order records actual dependency order;
type_dependencies records each named reference, its position, physical include
origin and whether it points to a later declaration. Repeated references to one
completed definition are shared dependencies, rather than cycles.

## Bounds and existing restrictions

Shared data-schema costs are memoized before generated Python literals expand.
Resolved TYPE data is limited to 32767 scalar leaves and 64 schema levels;
E_TYPE_CAPACITY and E_TYPE_DEPTH identify excess record/schema expansion. ARRAY
rank, dimension and capacity checks retain their existing diagnostics and bounds.
Transparent aliases add no schema depth and long finite chains remain usable.

Resource fields in STRUCTURE remain prohibited. Supported root FILE/PATH/queue
aliases and collection ARRAYs keep their existing ownership, initialization and
interface rules. Wildcard TYPE dimensions, routine-local TYPE declarations,
forward constant chains, implicit model discovery and unsupported result domains
remain unavailable. Public strict mode remains a future milestone; internal
legacy translation retains its prior-definition rules.

## Linking, dynamic creation and saved data

TYPE FROM still supplies a complete local layout. Forward dependencies resolve
before the existing exact source-project owner/schema checks. A local dependency
cycle and an external ownership cycle remain separate errors. No binary type
environment, missing owner program or native ABI is inferred.

Generated Program.variable_types exposes complete resolved schemas. CREATE_VAR,
GET_VAR/SET_VAR and ordinary context JSON use those same schemas and data rules.
Saved state contains no unresolved NAMED placeholders, dependency walkers or
suspended resolution. Partial ordinary data still retains its missing markers.

This is an authored offline Pythonic extension. The tests establish translation
and runtime data behavior, without native source/compiler/controller equivalence.
Reports expose forward_type_policy; see the
[semantics ledger](semantics/forward_type_semantics.json) and
[regressions](../tests/test_forward_types.py).

Authored examples cover [alias chains](../examples/forward_alias_chain.kl),
[record arrays](../examples/forward_record_array.kl), [PATH layouts](../examples/forward_path_layout.kl),
[later routine types](../examples/forward_routine_types.kl),
[linked ownership](../examples/forward_types_linked/main.kl) and
[linked record results](../examples/forward_types_result/main.kl).
