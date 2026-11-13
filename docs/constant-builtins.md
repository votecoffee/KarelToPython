# Pure scalar compile-time built-ins

Pythonic translation accepts 17 pure scalar built-ins in CONST expressions and
static ARRAY dimensions, STRING capacities and group annotations. This is an
authored offline source extension. It does not establish native CONST-call
acceptance or exact controller math; public strict mode remains future work.
Internal strict translation retains its previous constant-call rejection.

```karel
CONST count=ROUND(SQRT(square)) square=9 width=STR_LEN('ready')
TYPE row_t=ARRAY[count]OF INTEGER
VAR row:row_t text:STRING[width]
BEGIN row[3]=7 text='abcdef' END
```

COUNT resolves to 3, WIDTH to 5, and TEXT becomes `abcde` on execution. Calls
resolve before dependent schemas. The generated module stores scalar values;
it does not call these functions again to initialize constants.

## Accepted functions

| Functions | Checked Pythonic behavior |
| --- | --- |
| ABS | INTEGER or REAL magnitude, with the existing result range. |
| ROUND, TRUNC | Finite numeric input; ties-to-even rounding or truncation toward zero into initialized INTEGER. |
| SQRT, EXP, LN | Existing finite math domains; negative root, nonpositive logarithm and overflow fail translation. |
| SIN, COS, TAN, ASIN, ACOS | Existing degree-based math and domain/pole checks. |
| ATAN2 | Existing KAREL `(x,y)` order; the origin is invalid. |
| STR_LEN, SUB_STR, INDEX | Bounded ASCII text; one-based substring/search results, existing clipped slices and empty-search behavior. |
| CHR, ORD | ASCII codes 0..127 and one-based indexes within supplied contents. |

Arity and argument domains follow the existing runtime helpers. INTEGER inputs
to numeric REAL functions use the same promotion. BOOLEAN is not numeric
truthiness; text is not implicitly parsed. Known invalid arguments, nonfinite
math, overflow and wrong arity produce E_CONSTANT during translation. Existing
MININT spelling, MAXINT storage restrictions and schema size/capacity checks remain.

## Dependencies, scope and bounds

Calls may nest and reference later constants. Their argument references enter
the [forward dependency graph](forward-constants.md), including cycle detection
and validation of unused declarations. After dependencies resolve, arguments
evaluate eagerly from left to right; a false Boolean operand does not suppress
an invalid call. Module constants and each routine's local constants retain
lexical scope. Interfaces still use module constants, and sibling/caller local
names remain invisible.

The same rules apply to direct static schema expressions, such as
`ARRAY[ABS(-2)] OF INTEGER` and `STRING[STR_LEN('abc')]`. Local VAR declarations
may precede the local constants that determine their shapes. Linked modules
resolve independently before normal exact interface checks; no external constant
discovery or inferred type conversion is added.

Evaluation permits at most 4096 distinct cached call evaluations per translation
and 64 nested pure calls. Cache keys retain lexical routine/source position and
typed scalar arguments. Limits produce source-located E_CONSTANT diagnostics;
they do not defer execution or invent a value. Ordinary dependency chains retain
their separate iterative resolution behavior.

User or external routines, callbacks, time/system/port/register/FILE reads,
ARRAY_LEN, UNINIT and geometry/resource constructors remain unavailable in
constant expressions. Translation never runs the selected KAREL body, creates
a Program execution state or uses Python eval to compute a constant. These
restrictions apply even if a rejected call would appear in an unused definition.

## Reports and authored checks

`constant_builtin_policy` lists the functions, bounds and offline boundary.
`constant_builtin_uses` records function, module/routine scope, declaring constant
when applicable, argument/result types and original include-file positions.
Calls in direct schema expressions have no declaring constant. Dependency and
source-order constant metadata retain their existing contracts.

Resolved values travel through normal generated-module, source-translation and
saved-run interfaces; there are no writable constant slots or deferred call
graphs. [Input discovery](input-discovery.md) treats them as constants.

Authored examples cover [all functions](../examples/constant_builtin_values.kl),
[schemas and results](../examples/constant_builtin_shapes.kl),
[local declarations](../examples/constant_builtin_locals.kl) and
[linked interfaces](../examples/constant_builtins_linked/main.kl).
The [regressions](../tests/test_constant_builtins.py) and
[semantic ledger](semantics/constant_builtin_semantics.json) separate these
offline checks from native compiler/controller acceptance.
