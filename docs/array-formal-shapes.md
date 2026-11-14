# ARRAY parameter shapes

Pythonic source accepts fixed, wildcard and mixed ARRAY formal dimensions.
This is an authored source extension over existing checked storage. Native
source/compiler acceptance is not claimed; internal strict parsing retains its
wildcard-only syntax and public strict mode remains future work.

```karel
VAR grid:ARRAY[2,3]OF INTEGER
ROUTINE edit(data:ARRAY[2,*]OF INTEGER)
BEGIN data[2,3]=7 END edit
BEGIN edit(grid) END
```

The first dimension must be two. The second dimension comes from concrete caller
storage. The routine edits the original `grid[2,3]`; no wildcard size is guessed.

## Source and scope

| Formal | Constraint |
| --- | --- |
| `ARRAY OF INTEGER`, `ARRAY[*] OF INTEGER` | One caller-supplied dimension. |
| `ARRAY[2] OF INTEGER` | Exactly two elements. |
| `ARRAY[2,*] OF INTEGER` | Two rows and a caller-supplied second dimension. |
| `ARRAY[*,3] OF INTEGER` | Caller-supplied rows and exactly three columns. |
| `ARRAY[2] OF ARRAY[*] OF INTEGER` | Normalizes to `ARRAY[2,*] OF INTEGER`. |
| `ARRAY[count,*] OF item_t` | Module-scope constant size with existing exact element types. |

Sizes may use module constants, forward dependencies and supported
[pure compile-time calls](constant-builtins.md). Parameters, routine-local or
caller/sibling constants cannot determine interfaces. Ordinary local declaration
rules remain separate. Comma-separated dimensions may span physical lines.

Keep the existing limit of three logical dimensions, including named components.
Fixed sizes must be INTEGER in 1..32767. Fully fixed or minimum possible mixed
storage must fit the 32767-leaf/descriptor guard, including known element layouts.
The minimum uses one only for a capacity check; it never allocates or supplies
wildcard dimensions. Named component identities and direct STRING-capacity
inheritance remain unchanged. `ARRAY[2] OF STRING[3]` is still rejected; use
existing named aliases when a declared element capacity is needed.

## Borrowing and private values

Matching bare ARRAY storage keeps its existing reference and concrete schema.
Writes and whole assignments preserve caller identity; a formal cannot resize
borrowed storage or turn an equal element count into another shape. Grouped
values, ordinary data prefixes and computed results remain independent writable
copies. Existing numeric, STRING, nominal and geometric source conversions keep
their private-value rules. No new reference cast is introduced.

An outer wildcard formal can forward a bare reference to an anonymous fixed or
mixed interface when known sizes and element/component types do not conflict:

```karel
ROUTINE inner(data:ARRAY[2]OF INTEGER)
BEGIN data[1]=7 END inner
ROUTINE outer(data:ARRAY OF INTEGER)
BEGIN inner(data) END outer
```

The reference remains shared. The unchanged routine-entry check requires a
matching concrete reference before allocating the callee frame or running its
body. A three-element actual fails; the inner body does not edit it. Arguments
and earlier caller effects follow existing evaluation order and are not rolled
back. Named formal types keep their existing exact contracts. The generic
`parameter_accepts` runtime helper remains strict about unknown or wrong sizes.

Writes through forwarded references still participate in direct/transitive
effects, active FOR-counter protection, handler/timer guards and retained alias
proofs. Pause/resume keeps the original references; stopping unwinds frames and
retains completed ordinary writes.

## Resources and linked sources

FILE, PATH and QUEUE_TYPE formals retain their existing ownership rules.
Direct FILE prefixes borrow descriptors and FILE values still cannot be copied.
Logical PATH/queue banks use their existing checked references or independent
value policies; no nodes, entries, buffers or services are invented.
[BYNAME data rows/planes](array-prefix-references.md) must match fixed constraints
before binding; a mismatch preserves the entry output and original storage.

Source-linked declarations and supplied definitions must match exactly after
normalization. `ARRAY[2] OF ARRAY[*]` and `ARRAY[2,*]` normalize identically.
A fixed declaration does not silently match a wildcard definition. Callback
and explicit context validation retain their existing exact interfaces.

## Reports and evidence

`array_formal_policy` describes the constraints and offline boundary.
`array_formal_uses` records direct fixed/mixed interfaces, logical dimensions,
one-based constrained/wildcard dimensions, declaring routine/parameter and
physical include-file origins. `array_forward_uses` identifies retained aliases
whose unknown sizes defer to concrete routine-entry checks.

Static input discovery keeps uncast scalar values conservative when STRING
truncation or integral coercion can change a branch. A converted SHORT missing
sentinel remains an explicit derived-value gap rather than a seedable input.
Discovery still retains its documented partial-analysis boundaries.

The [mask](../examples/array_formal_masks.kl),
[forwarding](../examples/array_formal_forwarding.kl),
[value](../examples/array_formal_values.kl) and
[linked](../examples/array_formal_shapes_linked/main.kl) examples have independent
expected snapshots. [Regressions](../tests/test_array_formal_shapes.py) and the
[semantic ledger](semantics/array_formal_semantics.json) record software checks
separately from native/compiler/controller proof. Generated modules retain
resolved shape constraints; saved JSON stores ordinary values rather than live
parameter frames or resumable references.
