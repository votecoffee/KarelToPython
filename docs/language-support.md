# Language support

This is the supported prototype subset as of 0.52.0. Acceptance is specific to
source form, type and context. A supported feature can still reject uncertain
inputs at runtime. The [semantic notes](semantics/README.md) separate documented
rules, implemented restrictions and unresolved native behavior.

Public translation uses [Pythonic numeric equivalents](numeric-modes.md).
Strict mode is a future milestone; older exactness contracts are preserved
internally and in the historical semantic notes.

| Area | Supported subset | Limits |
| --- | --- | --- |
| Source | Case-insensitive ASCII identifiers, comments, supported metadata directives, bounded complete-token continuations, doubled apostrophes | No arbitrary directives, token fusion, backslash escapes or multiline string literals. |
| Control flow | Assignment, IF/ELSE, WHILE, REPEAT, inclusive FOR/DOWNTO, SELECT, RETURN | Fresh local counters are required for calls/early returns within FOR; SELECT uses first matching case and errors without a match/ELSE. |
| Labels | Restricted labels and unconditional GOTO | Jumps within the same block or to an ancestor; no arbitrary entry into nested control blocks. |
| Routines | Internal procedures/functions, bare zero-argument function calls, fresh local frames, local constants, reference/value arguments, recursion | Depth limit 64, conservative effects/order guards, no external routine linkage or local TYPE sections. |
| INTEGER | Checked signed 32-bit expressions, bit operators, DIV and signed MOD | MAXINT excluded from normal storage; DIV truncates toward zero; MOD follows Python remainder. |
| BOOLEAN | Strict Boolean storage, operators and comparisons | Numeric values are not implicitly Booleans. |
| REAL | Python float, rounded arithmetic, promotion, ROUND/TRUNC, SQRT, EXP and LN | Finite values required; existing checked INTEGER results. ROUND uses ties to even. |
| Trig | General degree SIN/COS/TAN/ASIN/ACOS and ATAN2 | Inverse/domain checks remain. ATAN2 uses KAREL `(x,y)` order, all quadrants and Python -180..180 degree output. |
| STRING | Bounded ASCII storage, right truncation, concatenation/comparison, STR_LEN, restricted SUB_STR/INDEX/CHR/ORD | Direct STRING function results and unresolved substring/search boundaries remain blocked. Read-only value inputs have restricted temporary handling. |
| BYTE/SHORT | Aggregate storage, range checks and numeric value promotion | Initial BYTE data is unknown; BYTE initialization queries are blocked. SHORT 32767 means uninitialized. |
| Arrays | One-based fixed/named arrays up to logical rank three, exact whole copies, reference formals and named subarrays | Prototype bound of 32767 scalar leaves; whole-array value arguments prohibited; nominal identity and exact shape are retained. |
| Variable arrays | Explicit translation-time shapes for direct global wildcard declarations | No inference, controller/VR access, resize or persistence. |
| ARRAY results | Unsized anonymous outer ARRAY with scalar, explicitly bounded STRING, prior named STRUCTURE, built-in record, exact-width JOINTPOS or prior named ARRAY elements; logical rank up to three | Every scalar leaf known/initialized; call only as complete direct-assignment RHS. One outer dimension; exact inner component names/shapes and STRING capacities. Named outer results, flat multidimensional sources and unspecified STRING result capacities remain blocked. |
| Structures | Prior named structures, nested fields/arrays, checked copies and internal results/value temporaries | Nominal type identity, complete known initialization and capacity checks; no type aliases or ABI claim. |
| USING | Restricted bare structure selectors and field priority | Lexical scope; no complex selector expressions or dynamic caller scope. |
| Positional data | CONFIG, VECTOR, XYZWPR, XYZWPREXT, POSITION data and exact value/result copies | POSITION orientation starts unknown and remains recursively read-only. No invented orientation, geometry or robot defaults. |
| Joint data | Opaque JOINTPOS1..9, exact-width copies, restricted explicit-context REAL-array conversions | No source field/index access, implicit group discovery, positional conversion or kinematics. |
| VECTOR | Checked float arithmetic, scaling, cross/dot products, equality and routine values | Group ambiguous products and initialize finite components. Zero/parallel cross products allowed. |
| Conversion | Python INTEGER/REAL text parsing, signed bases 2..16, rounded fixed-decimal REAL output, checked XYZWPR extraction via UNPOS | Bounded width/precision, caller capacities and disjoint outputs; chosen Pythonic formatting conventions. |
| DELAY | Checked 0..86400000 ms through a host callback | Host timing is not controller timing; step budget is not a time budget. |
| WRITE | Mixed scalar lists, signed integers, finite REALs, numeric formatting, narrow integers and CR newlines | One complete recorder/callback request per statement, <=254 characters. Literal formats; existing STRING quote guards; no explicit FILE/device destinations, aggregate output or READ. |
| ABORT | Bare statement with sticky termination and frame cleanup | No task qualifiers, condition/action semantics, motion cancellation or controller restart behavior. |

## Zero-argument function calls

An unshadowed internal function with no parameters can be invoked by its name:
`IF ready THEN ... ENDIF`, `value=answer`, or `values=build`. Existing explicit
`answer()` spelling remains accepted for compatibility. Functions with parameters
require their argument list; procedure calls remain standalone statements.

Name resolution runs after `USING` field resolution and before effect analysis.
Routine-local variables and parameters keep their storage bindings. Local CONST
collisions retain the existing rejection. Assignment targets and field/array
receiver roots remain storage expressions: `build[1]` does not implicitly invoke
a function. Stage aggregate results before selecting their fields or elements.

Bare calls use the same type, ownership, argument-order, effect, FOR, recursion
and cleanup rules as explicit calls. ARRAY results still require a complete
direct-assignment right side; `(build)`, `use(build)` and `RETURN build` cannot
consume or forward an ARRAY function result. See the authored
[bare-call example](../examples/bare_function_calls.kl) and
[function-call contract](semantics/function_call_semantics.json).

## ARRAY function results

Internal functions may return arrays of INTEGER/BOOLEAN/REAL/BYTE/SHORT,
explicitly bounded STRING elements, prior
named STRUCTURE types, CONFIG/VECTOR/XYZWPR/XYZWPREXT/POSITION, or JOINTPOS1..9.
Unsuffixed JOINTPOS means nine axes. Elements may also be prior named fixed ARRAY
types, with at most three logical dimensions across the result. The outer result
is anonymous and unsized; its single outer length comes from the returned storage.

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

For a matrix, declare `TYPE row_t=ARRAY[2] OF INTEGER`, then use
`ROUTINE make: ARRAY OF row_t` and return local storage declared
`values: ARRAY[2] OF row_t`. A prior named plane type can supply the inner two
dimensions of a three-dimensional result. Each ARRAY component retains its exact
declared type and fixed shape. See the complete authored
[named-component example](../examples/named_component_array_functions.kl).

The result declaration still omits brackets and sizes. Flat comma-dimension
return storage, named outer result types/storage, inline `ARRAY OF ARRAY`, and
unspecified STRING result-element capacities remain blocked. A named subarray cannot be returned as an
anonymous outer array. Named STRUCTURE elements may contain supported STRING
fields and named arrays under the existing recursive copy rules.

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
function results retain their existing rejection; this ARRAY subset is an offline
composition of the documented array and bounded-string rules, without native
compiler or controller validation.

Return copies complete before local frames unwind and retain record names,
nested array identities/shapes, STRING field capacities and joint widths. All
scalar leaves must be initialized and known; this is a conservative prototype
guard. The 32767 scalar-leaf limit includes nested fields and joint axes.
Failure leaves the destination intact while retaining earlier independent effects.

Use the result only as the complete right side of a direct assignment, with a bare
zero-argument function name or an explicit call. Stage it
in a concrete array before passing it onward. Destination type and length must
match exactly; no element coercion, resizing or nominal identity erasure occurs.
POSITION orientation remains protected, with no source acquisition or default
values. Exact joint copying needs no axis context; conversion procedures retain
their existing explicit-context requirements. The full contract and unresolved
native behavior are in [array_routine_semantics.json](semantics/array_routine_semantics.json).

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

`CNV_REAL_STR(source,length,num_digits,target)` supports fixed precision in
0..254. For example, `CNV_REAL_STR(1.125,1,3,text)` produces ` 1.125`, including
its leading blank. Requested trailing zeros are retained; zero fractional digits
suppress the decimal point. Python fixed-point formatting supplies decimal
rounding; ordinary decimal inputs and rounded results are accepted.

`length` is a minimum width in 1..254; extra width adds left padding.
If the result exceeds the caller's declared STRING
capacity, output is one blank followed by asterisks filling that capacity. This
also applies when supported precision produces more than 254 characters. The
0..254 precision bound limits prototype work; it is not a claimed controller
format-parameter range. Scientific notation and invalid-format outcome inference
remain blocked. See the authored [precision example](../examples/fixed_decimal_precision.kl)
and [conversion contract](semantics/conversion_semantics.json).

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
