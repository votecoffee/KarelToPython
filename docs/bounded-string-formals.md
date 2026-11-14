# Bounded STRING parameters

Pythonic source accepts direct `STRING[capacity]` scalar parameters and ARRAY
elements. This is an authored syntax extension over the existing
[bounded alias contracts](type-aliases.md#arguments-and-copies); native source,
compiler and controller equivalence are not claimed. Internal strict parsing
retains its existing exclusions, and public strict mode remains future work.

```karel
CONST width=3
ROUTINE edit(text:STRING[width])
BEGIN text='abcdef' END edit
ROUTINE edit_rows(rows:ARRAY[2,*]OF STRING[width])
BEGIN rows[1,1]='abcdef' END edit_rows
```

Capacities require module-scope INTEGER constants in 1..254. Forward constants,
supported pure compile-time calls and newlines inside brackets follow the
existing constant rules. Parameter, caller and routine-local values cannot
define an interface. Omitted capacities retain their existing behavior; no
wildcard bracket capacity or dynamic allocation is introduced.

## Scalar parameters

| Actual | Behavior |
| --- | --- |
| Bare STRING with the same known capacity | Borrow the original cell. |
| Bare STRING with a different known capacity | Reject; use grouping for a private value. |
| Literal, constant, expression, function result or grouped STRING | Validate initialized ASCII input of at most 254 characters, then copy and right-truncate into the declared private capacity. |
| Borrowed generic scalar STRING with an unknown declared capacity | Retain its reference and require matching concrete capacity at routine entry. |

The 254-character input guard precedes truncation. Later assignment and clear
operations keep the temporary's declared capacity. Ordinary plain `STRING`
value arguments still use capacity 254; borrowed plain STRING formals still
inherit caller capacity. No value argument writes back into caller storage.

```karel
ROUTINE inner(text:STRING[3])
BEGIN text='abcdef' END inner
ROUTINE outer(text:STRING)
BEGIN inner(text) END outer
```

An actual STRING[3] remains shared and becomes `'abc'`. An actual STRING[4]
fails the unchanged concrete reference check before the inner frame/body.
Earlier caller and argument effects are retained; they are not rolled back.
`inner((text))` instead creates a private bounded value, with no writeback.
These forwarding rules also apply to transparent bounded STRING aliases.

Pause/resume keeps the original cell; stop unwinds frames and retains ordinary
completed writes. Active aggregate FOR-counter roots retain their existing
direct/transitive write protection. BYNAME uses exact concrete capacity checks
and preserves the entry output and original target on a binding failure.

## ARRAY elements and linkage

Direct bounded elements use the existing checked ARRAY rules. Matching bare
storage retains references. Different capacities use independent source schema
conversion values, with no copyback. Grouped arrays remain private and preserve
missing scalar markers. Fixed/wildcard/mixed dimensions and inline layers follow
[ARRAY formal constraints](array-formal-shapes.md).

An unknown generic STRING element capacity retains the existing private ARRAY
conversion policy; it does not acquire the scalar forwarding reference rule.
Named component identities, logical rank, storage limits and receiver shape
checks remain unchanged.

Linked declarations/definitions and explicit callbacks keep exact resolved
interfaces. Direct and alias spellings may match after resolution. Different
capacities do not become interchangeable signatures. Persistence keeps ordinary
typed STRING values and ARRAY schemas; no live frame or reference is serialized.

## Reports and checks

`string_formal_policy` describes these source and runtime boundaries.
`string_formal_uses` records direct bounded scalar/ARRAY declarations, resolved
capacity/schema, routine/parameter and physical include origins.
`string_forward_uses` records borrowed generic scalar capacity checks.
The generic `parameter_accepts` helper remains unchanged.

Input discovery follows existing bounded private values, ARRAY shape facts and
borrowed aliases. Conflicting known borrowed capacities produce explicit
`parameter-capacity` gaps without publishing callee write facts. Partial data,
dynamic paths, services and other existing analysis limits remain explicit.

The [scalar](../examples/bounded_string_parameters.kl),
[ARRAY](../examples/bounded_string_array_parameters.kl) and
[linked](../examples/bounded_string_formals_linked/main.kl) examples have
independent expected snapshots. [Regressions](../tests/test_bounded_string_formals.py)
and the [semantic ledger](semantics/bounded_string_formal_semantics.json) record
software evidence separately from native/controller acceptance.
