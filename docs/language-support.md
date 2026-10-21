# Language support

This is the supported prototype subset as of 0.61.0. Acceptance is specific to
source form, type and context. A supported feature can still reject uncertain
inputs at runtime. The [semantic notes](semantics/README.md) separate documented
rules, implemented restrictions and unresolved native behavior.

Public translation uses [Pythonic numeric equivalents](numeric-modes.md).
Strict mode is a future milestone; older exactness contracts are preserved
internally and in the historical semantic notes.

| Area | Supported subset | Limits |
| --- | --- | --- |
| Source | Case-insensitive ASCII identifiers, comments, supported metadata directives, bounded complete-token continuations, doubled apostrophes | No arbitrary directives, token fusion, backslash escapes or multiline string literals. |
| Control flow | Assignment, IF/ELSE, WHILE, REPEAT, inclusive FOR/DOWNTO, SELECT, RETURN | FOR calls must protect active counters through transitive write checks; read-only counter references allowed; initialized counters clear on all scope exits. Formal/nonlocal counters in parameterized routines require fresh locals. SELECT uses first matching case and errors without a match/ELSE. |
| Labels | Restricted labels and unconditional GOTO | Jumps within the same block or to an ancestor; no arbitrary entry into nested control blocks. |
| Routines | Internal procedures/functions, bare zero-argument function calls, fresh local frames, local constants, reference/value arguments, recursion | Depth limit 64; chosen Pythonic left-to-right evaluation; existing FOR rules; no external routine linkage or local TYPE sections. |
| INTEGER | Checked signed 32-bit expressions, bit operators, DIV and signed MOD | MAXINT excluded from normal storage; DIV truncates toward zero; MOD follows Python remainder. |
| BOOLEAN | Strict Boolean storage, operators and comparisons | Numeric values are not implicitly Booleans. |
| REAL | Python float, rounded arithmetic, promotion, ROUND/TRUNC, SQRT, EXP and LN | Finite values required; existing checked INTEGER results. ROUND uses ties to even. |
| Trig | General degree SIN/COS/TAN/ASIN/ACOS and ATAN2 | Inverse/domain checks remain. ATAN2 uses KAREL `(x,y)` order, all quadrants and Python -180..180 degree output. |
| STRING | Bounded ASCII storage, right truncation, internal STRING/STRING[n] function results, writable value arguments, concatenation/comparison, clipped SUB_STR and INDEX including empty searches | Default result/value capacity 254; explicit result capacity 1..254. Bare arguments keep caller references. SUB_STR returns at most 254; positive start and nonnegative count. |
| BYTE/SHORT | Aggregate storage, range checks and numeric value promotion | Initial BYTE data is unknown; BYTE initialization queries are blocked. SHORT 32767 means uninitialized. |
| Arrays | One-based fixed/named arrays up to logical rank three, exact whole copies, reference/value arguments and named subarrays | Prototype bound of 32767 scalar leaves; value arguments require known initialized leaves; nominal identity and exact shape are retained. |
| Variable arrays | Explicit translation-time shapes for direct global wildcard declarations | No inference, controller/VR access, resize or persistence. |
| ARRAY results | Named types or anonymous fixed/wildcard/mixed dimensions; scalar, bounded STRING, record, joint or named ARRAY elements; grouping, argument/RETURN composition and aggregate access | Every scalar leaf known/initialized; exact nominal/component identities and STRING capacities; logical rank up to three. Anonymous declarations require anonymous outer storage. No unspecified STRING capacities, resize or flattening. |
| Structures | Prior named structures, nested fields/arrays, checked copies and internal results/value temporaries | Nominal type identity, complete known initialization and capacity checks; no ABI claim. |
| TYPE aliases | Transparent supported scalar, bounded STRING, record, joint and prior named type aliases; chains and routine interfaces | Preserve original aggregate identity and capacities; bounded STRING formal references require matching capacity, values truncate to private alias capacity. No forward/self/cyclic aliases, local TYPE or external FROM types. BYTE/SHORT remain element/field-only. |
| USING | Nested lexical scopes, named STRUCTURE variables and dotted selectors; inner/right-most field priority | Fields shadow constants; calls use call context. No indexed/call/grouped selectors, builtin record selectors, field FOR counters or dynamic caller scope. |
| Positional data | CONFIG, VECTOR, XYZWPR, XYZWPREXT, POSITION data and exact value/result copies | POSITION orientation starts unknown and remains recursively read-only. No invented orientation, geometry or robot defaults. |
| Joint data | Opaque JOINTPOS1..9, exact-width copies, restricted explicit-context REAL-array conversions | No source field/index access, implicit group discovery, positional conversion or kinematics. |
| VECTOR | Checked float arithmetic, scaling, cross/dot products, equality and routine values | Group ambiguous products and initialize finite components. Zero/parallel cross products allowed. |
| Conversion | Python INTEGER/REAL text parsing, signed bases 2..16, rounded fixed/scientific REAL output, checked XYZWPR extraction via UNPOS | Bounded width/precision, caller capacities and disjoint outputs; chosen Pythonic formatting conventions. |
| DELAY | Checked 0..86400000 ms through a host callback | Host timing is not controller timing; step budget is not a time budget. |
| WRITE | Mixed scalar lists, signed integers, finite REALs, dynamic INTEGER formats, quoted STRING escaping/truncation, narrow integers and CR newlines | One complete recorder/callback request per statement, <=254 characters. Bounded formats; no explicit FILE/device destinations, aggregate output or READ. |
| ABORT | Bare statement with sticky termination and frame cleanup | No task qualifiers, condition/action semantics, motion cancellation or controller restart behavior. |

See [STRING operations](string-operations.md) for substring, search, length and
character equivalents, evaluation order and retained input checks.
See [Pythonic FOR](pythonic-for.md) for global-counter calls, read-only counter
arguments, bounds and cleanup on early exits/errors.
See [Pythonic USING](pythonic-using.md) for nested field paths and namespace choices.
See [TYPE aliases](type-aliases.md) for transparent names, identity and bounded
STRING routine interfaces.

## Zero-argument function calls

Pythonic mode supports function composition with a chosen deterministic
[evaluation order](evaluation-order.md): ordinary operands and arguments run
left to right, BOOLEAN AND/OR short circuit, and assignments capture their values
before resolving targets. Function calls are accepted in multiple arguments,
subscripts, conversion arguments and FOR bounds. Existing type, initialization,
copy/alias, domain, output-overlap and FOR-body counter checks remain.

An unshadowed internal function with no parameters can be invoked by its name:
`IF ready THEN ... ENDIF`, `value=answer`, or `values=build`. Existing explicit
`answer()` spelling remains accepted for compatibility. Functions with parameters
require their argument list; procedure calls remain standalone statements.

Name resolution runs after `USING` field resolution and before effect analysis.
Routine-local variables and parameters keep their storage bindings. Local CONST
collisions retain the existing rejection. Assignment targets and field/array
receiver roots remain storage expressions: `build[1]` does not implicitly invoke
a function. Use an explicit call or a group to access returned fields or elements,
such as `build()[1]` or `(build)[1]`.

Bare calls use the same type, ownership, argument-order, effect, FOR, recursion
and cleanup rules as explicit calls. ARRAY results support grouping, compatible
user-routine arguments, direct RETURN forwarding and ARRAY_LEN returning the first dimension.
See the [ARRAY values guide](pythonic-arrays.md), the authored
[bare-call example](../examples/bare_function_calls.kl) and
[function-call contract](semantics/function_call_semantics.json).

## ARRAY function results

Internal functions may return arrays of INTEGER/BOOLEAN/REAL/BYTE/SHORT,
explicitly bounded STRING elements, prior
named STRUCTURE types, CONFIG/VECTOR/XYZWPR/XYZWPREXT/POSITION, or JOINTPOS1..9.
Unsuffixed JOINTPOS means nine axes. Elements may also be prior named fixed ARRAY
types, with at most three logical dimensions across the result. Named outer results
and anonymous fixed, wildcard or mixed outer dimensions are supported. Fixed sizes
are global constant expressions; wildcard sizes come from returned concrete storage.
See [ARRAY result shapes](array-result-shapes.md).

```karel
PROGRAM ARRAY_RECORDS
TYPE entry_t=STRUCTURE id: INTEGER label: STRING[4] ENDSTRUCTURE
VAR entries: ARRAY[1] OF entry_t
ROUTINE make: ARRAY OF entry_t
VAR values: ARRAY[1] OF entry_t
BEGIN
  values[1].id=42
  values[1].label='ready'
  RETURN values
END make
BEGIN
  entries=make()
END ARRAY_RECORDS
```

For a matrix built from named rows, declare `TYPE row_t=ARRAY[2] OF INTEGER`, then use
`ROUTINE make: ARRAY OF row_t` and return local storage declared
`values: ARRAY[2] OF row_t`. A prior named plane type can supply the inner two
dimensions of a three-dimensional result. Each ARRAY component retains its exact
declared type and fixed shape. See the complete authored
[named-component example](../examples/named_component_array_functions.kl).

Results can use omitted, fixed, wildcard or mixed outer dimensions and matching
flat comma-dimension storage. Named outer result types, including transparent
aliases, require the original nominal identity. Inline `ARRAY OF ARRAY` and
unspecified STRING result-element capacities remain blocked. A named subarray
cannot be returned as an anonymous outer array. Named STRUCTURE elements may
contain supported STRING fields and named arrays under the existing recursive
copy rules.

For STRING elements, use `ROUTINE make: ARRAY OF STRING[4]` and return an anonymous
array whose elements have that same physical capacity. The capacity is a constant
in 1..254. Prior named rows or planes containing bounded STRING elements also
work. An `ARRAY OF STRING` reference formal retains its caller's capacity; RETURN
checks that concrete capacity against the declared result. The result never
infers a capacity or truncates elements to reconcile a mismatch. Ordinary writes
to source storage still apply the existing right-truncation rule.

Empty initialized elements are valid. Uninitialized, non-ASCII or malformed
oversized host values fail before result assignment. See the authored
[STRING ARRAY example](../examples/string_array_functions.kl). Direct STRING
results follow the [Pythonic STRING contract](pythonic-strings.md); this ARRAY subset is an offline
composition of the documented array and bounded-string rules, without native
compiler or controller validation.

Return copies complete before local frames unwind and retain record names,
nested array identities/shapes, STRING field capacities and joint widths. All
scalar leaves must be initialized and known; this is a conservative prototype
guard. The 32767 scalar-leaf limit includes nested fields and joint axes.
Failure leaves the destination intact while retaining earlier independent effects.

Use a bare zero-argument function name or an explicit call. Results compose in
grouping, compatible user-routine arguments, direct RETURN forwarding and
ARRAY_LEN returning the first dimension. Explicit calls or groups support returned aggregate
subscripts and fields. Destination type and length must
match exactly; no element coercion, resizing or nominal identity erasure occurs.
POSITION orientation remains protected, with no source acquisition or default
values. Exact joint copying needs no axis context; conversion procedures retain
their existing explicit-context requirements. The full contract and unresolved
native behavior are separated in the [Pythonic ARRAY contract](pythonic-arrays.md)
and retained [conservative ledger](semantics/array_routine_semantics.json).

## INTEGER base formatting

For statement output rather than conversion to STRING storage, see
[Pythonic WRITE](pythonic-output.md), including mixed items and REAL formatting.

`CNV_INT_STR(source,length,base,target)` formats signed INTEGER values in bases
2..16. Base 0 selects decimal; alphabetic digits are uppercase A..F. For example,
source -42 produces ` -101010` in base 2 and ` -2A` in base 16. Natural output
has one leading blank, no prefix and minimal digits; zero produces ` 0`.

Minimum lengths in 1..254 are supported, adding left padding when needed.
An invalid base outside 0 or 2..16 clears output after input and length checks.
Capacity overflow produces one blank
followed by asterisks filling the caller's declared capacity. Guard failures keep
the destination intact. These are bounded offline formatting rules, without
native compiler or controller validation. See the authored
[base-formatting example](../examples/integer_base_formatting.kl).

## Decimal formatting

`CNV_REAL_STR(source,length,num_digits,target)` supports precision in -254..254.
Negative precision selects uppercase scientific notation using its absolute
value; nonnegative precision selects fixed output.
For example, `CNV_REAL_STR(1.125,1,3,text)` produces ` 1.125`, including
its leading blank. Requested trailing zeros are retained; zero fractional digits
suppress the decimal point. Python fixed-point formatting supplies decimal
rounding; ordinary decimal inputs and rounded results are accepted.

`length` is a minimum width in 1..254; extra width adds left padding.
If the result exceeds the caller's declared STRING
capacity, output is one blank followed by asterisks filling that capacity. This
also applies when supported precision produces more than 254 characters. The
-254..254 precision bound limits prototype work; it is not a claimed controller
format-parameter range. Invalid formats raise errors. See
[Pythonic text formats](text-formats.md), the authored
[precision example](../examples/fixed_decimal_precision.kl) and the older
[conservative conversion contract](semantics/conversion_semantics.json).

## Examples

All runnable examples have authored KAREL sources and complete expected snapshots
under [examples](../examples). Run `python tools/run_examples.py` from the repository
root to translate and check them. The intentionally unsupported-motion source
must be rejected and is not executed.

## Evidence boundaries

The public tests use authored source and synthetic fixtures. They check parser,
emitter, execution, ownership, effects, diagnostics and failure paths offline.
They do not authenticate native compiler acceptance, original source recovery,
binary equality, controller ABI or robot behavior.

Manual PDFs, private corpora, local audit results and controller files are not
distributed here. Use the [reference descriptions](references.md) and the
documents available for your controller release when evaluating source semantics.
