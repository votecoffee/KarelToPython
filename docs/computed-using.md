# Computed USING selectors

Pythonic translation accepts computed record values in `USING`, alongside the
existing [captured storage selectors](using-selectors.md). Supported selected
types are named `STRUCTURE`, `VECTOR`, `CONFIG`, `XYZWPR`, `XYZWPREXT` and
`POSITION`.

```karel
USING VEC(1,2,3) + VEC(4,5,6) DO
  x = x + 10
  result = x + y + z
ENDUSING

USING make_record().child, make_rows()[slot] DO
  value = value + 1
ENDUSING
```

Functions, constructors, supported record operators, grouping and nested record
field/ARRAY element selection can provide the selected value. An unshadowed
zero-parameter function name can omit its parentheses. All expressions still
use their ordinary type, argument, effect and geometry checks; a computed
selector does not make an otherwise unsupported expression valid.

## Storage and value capture

Each selector is captured exactly once, from left to right, before the body
starts. Capture also occurs for an empty body. Each selector in a list resolves
against the enclosing lexical aliases; fields introduced earlier in that same
list do not change the meaning of later selectors.

The receiver's root determines ownership:

| Root | Capture | Writes through unqualified fields |
| --- | --- | --- |
| Declared storage, including grouped/dotted/indexed paths | Existing reference | Change the selected original storage |
| An existing captured USING reference | Existing reference | Change that capture's storage |
| A function, constructor or computed expression | Independent checked record copy | Change only the private temporary |

For example, `USING (record)` retains the original storage, while
`USING copy_record(record)` captures a separate value. Computed copies never
copy back to the routine's source, its reference arguments, a register bank or
the original record. A nested `USING child` inside a computed capture refers to
that same temporary's child; it does not allocate another copy. A directly
selected `USING make_record().child` copies the selected child independently.

Direct fields become mutable lexical aliases. Inner fields override outer
fields, and the rightmost matching record wins within a list. Ending or jumping
out of the scope restores the surrounding name resolution. Only direct fields
are exposed; nested fields require qualification or another `USING`.

## Validation and effects

The temporary uses the ordinary checked aggregate value-copy boundary. Nominal
types, concrete schema, field names, dimensions, bounded strings, known scalar
values and CONFIG turn ranges remain checked. Partial scalar `UNINITIALIZED`
leaves and BYTE-only unknown markers survive a valid copy. Reading an unknown
leaf retains its usual error; capture does not synthesize defaults. Copies are
limited to 32767 scalar leaves and 64 nested schema levels.

POSITION orientation columns remain read-only even when selected from a
computed pose or reached through a nested private alias. CONFIG subfields keep
their bounded assignment and value-only routine-argument rules; they cannot
become unchecked conversion output aliases.

Selector functions, constructor arguments and indexes use ordinary transitive
call checks before capture. They cannot modify an active FOR counter or bypass
the conservative whole-aggregate-root write guard. Direct writes to a private
temporary do not claim a write to the original source or an invented global.
Effects performed while obtaining a value, including routine/global writes or
service requests, remain ordinary effects.

## Control flow and lifetime

Each fresh block entry allocates new computed temporaries. Jumps within a USING
scope and cooperative pause/resume retain its captures. Entry from outside or a
sibling USING scope remains rejected because it would skip capture. A captured
selector function can itself pause; the USING body starts after it returns and
its value passes validation.

Condition handlers freeze the enclosing captured references at definition.
They may retain, read and mutate a computed temporary after lexical scope exit.
Handlers created on separate entries retain separate temporaries. A handler's
own inner USING captures are allocated when that action runs. These are
in-process references, not serialized suspended stacks or native alias-lifetime
claims.

RETURN, STOP, ABORT, errors and budget exhaustion retain their ordinary task and
frame cleanup. Completed outside effects remain on failure; private field edits
are never copied back. In a selector list, failure of a later capture leaves
earlier completed effects intact and prevents entry to the body.

## Explicit boundaries

- Whole ARRAY, FILE, PATH, QUEUE_TYPE and JOINTPOS selectors are rejected. An
  individual record element returned in an ARRAY is supported.
- Computed selected records must contain data without FILE/PATH/QUEUE resources.
  Existing reference selectors keep their original behavior, including PATH
  node record references.
- Exact INTEGER fields in isolated private captures can now serve as
  [FOR counters](private-using-counters.md), with internal whole-root protection
  identities and conservative retained-alias checks. The public source root
  remains null and counter edits never copy back to the source.
- [Private connected timers](private-using-timers.md) accept ordinary INTEGER
  leaves under the existing whole-root counter protections. They can retain a
  capture after lexical exit and end with explicit disconnect or terminal cleanup.
  [Declared local timers](routine-local-timers.md) use their defining routine
  frame lifetime. Formal timer roots and other service scope restrictions remain.
- The preserved legacy translator retains its prior selector restrictions.
  These additions describe Pythonic offline execution, with no native or
  controller acceptance claim.

## Reports

`using_scopes` retains lexical ids, parents, source selectors, resolved uses and
selector types. Each `selector_captures` row adds:

| Field | Meaning |
| --- | --- |
| `source_kind` | `storage_reference` or `computed_value` |
| `provenance` | `declared_storage` or `private_temporary` |
| `source_root` | Original declared name, or JSON null for private storage |
| `expression_kind` | Selector AST kind after lexical and bare-function resolution |
| `independent_copy` | Whether this entry creates a new checked value copy |
| `copy_back` | Always false; named references write directly, private values do not copy back |

A nested reference into an outer private capture reports `storage_reference`,
`private_temporary`, null `source_root` and `independent_copy=false`.
`computed_using_policy` describes value validation, effects, lifetime and
remaining boundaries. `controller_validated` is false.
