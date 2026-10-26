# External type declarations

Pythonic mode accepts the complete KAREL declaration form:

```karel
PROGRAM MAIN
TYPE point_t FROM GEOMLIB = STRUCTURE
       x: REAL
       y: REAL
     ENDSTRUCTURE
     row_t FROM GEOMLIB = ARRAY[2] OF point_t
VAR points: row_t
BEGIN
  points[1].x=20
  points[1].y=5
  points[2].x=22
  points[2].y=7
END MAIN
```

`FROM` appears between the type name and `=`. It names the declaring owner
program; that program may be the current program. A complete definition is still
required. The manual's FROM clause and external PATH examples retain the full
STRUCTURE and PATH definitions. This feature does not load an unknown type from
a binary environment or infer a missing definition.

## Supported layouts and execution

Use the existing supported TYPE definitions: transparent scalar, bounded STRING,
record and joint aliases; fixed named ARRAY and STRUCTURE definitions; and
supported FILE, PATH and QUEUE_TYPE aliases. Referenced component types must
already be defined. Existing resource-field, array-capacity, initialization,
BYTE/SHORT and routine-interface restrictions continue to apply.

A standalone translation can run using its complete local layout. It records
external ownership as **unverified** and neither discovers nor executes the
owner program. Self-owned declarations are marked `self-declared`. Run the
authored standalone fixture with the CLI:

```sh
python -m karel2py examples/external_types.kl --check
python -m karel2py examples/external_types.kl -o external_types.py --report external_types.report.json
python external_types.py
```

A source project verifies each external declaration during `translate_project`
or `load_project`, before any Program instance allocates globals or runs KAREL
statements. It requires a supplied owner program with the same type name and an
exactly equal resolved schema, including field order, nested nominal names,
array dimensions, joint width and STRING capacity. Aliases resolve before this
comparison. There is no numeric promotion, field reordering or identity erasure
at a link boundary.

Source reexports can form a chain. Every edge must have a matching schema, and
the chain must end at a local definition or a declaration owned by its own
program. Cycles and missing intermediate owners are errors. Resolution uses an
iterative walk and does not depend on source ordering. This chain policy is an
offline Pythonic linking choice, not a native loader acceptance claim.

```sh
python -m karel2py.project examples/external_types_project
python -m karel2py.project examples/external_types_project --entry MAIN
```

That project combines an included type fragment, self-owned definitions, a
reexporting library, shared FROM variables, a named array argument and an
external function returning a structure. Ordinary variable aliases and routine
signatures retain their existing exact checks.

## Metadata and errors

Generated `Program.imported_types` contains immutable `(name, declared_owner)`
pairs. `Program.type_owners` maps each local type name to its declared owner;
a local alias belongs to its declaring module while preserving the aliased
aggregate schema. `Program.variable_types` remains the resolved layout table.

Translation reports add `imported_types` rows containing the name, declared
owner, expanded line/column, original source file/line/column, include stack
and linkage disposition. Successful source projects mark rows `source-validated`
and add `resolved_owner`. `Project.type_owners[program][type_name]` provides
terminal owners; class metadata continues to show the originally declared owner.
The `external_type_policy` report and
[semantics ledger](semantics/external_type_semantics.json) describe the contract.

| Diagnostic | Meaning |
| --- | --- |
| E_TYPE_LINK | Owner program or same-named owner type is missing. |
| E_TYPE_LINK_TYPE | Importer and owner resolved schemas differ. |
| E_TYPE_LINK_CYCLE | Ownership chain has no terminal definition. |

Link diagnostics point at the importing type declaration, including its original
physical location inside an included file. Syntax/type-definition errors retain
the ordinary parser diagnostics.

## Boundaries

Ownership is explicit metadata alongside existing nominal names and layouts.
It does not create a universal owner-qualified type identity or a native ABI.
Existing `IN GROUP` annotations remain source context metadata, outside resolved
type identity, and do not make otherwise equal schemas different. Existing
persisted variable/archive schemas do not change.

No automatic library discovery, native binary environments, incomplete imports,
renamed imported type names, forward/self/cyclic type aliases or routine-local
TYPE sections are added. The KAREL language prohibits routine-local TYPE;
a self-owned FROM clause on a complete definition is a different construct.
Strict mode remains a future milestone. Tests establish source acceptance and
offline behavior; no native compiler or controller equivalence is claimed.
