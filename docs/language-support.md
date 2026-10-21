# Language support

This is the supported prototype subset as of 0.47.0. Acceptance is specific to
source form, type and context. A supported feature can still reject uncertain
inputs at runtime. The [semantic notes](semantics/README.md) separate documented
rules, implemented restrictions and unresolved native behavior.

| Area | Supported subset | Limits |
| --- | --- | --- |
| Source | Case-insensitive ASCII identifiers, comments, supported metadata directives, bounded complete-token continuations, doubled apostrophes | No arbitrary directives, token fusion, backslash escapes or multiline string literals. |
| Control flow | Assignment, IF/ELSE, WHILE, REPEAT, inclusive FOR/DOWNTO, SELECT, RETURN | Fresh local counters are required for calls/early returns within FOR; SELECT uses first matching case and errors without a match/ELSE. |
| Labels | Restricted labels and unconditional GOTO | Jumps within the same block or to an ancestor; no arbitrary entry into nested control blocks. |
| Routines | Internal procedures/functions, bare zero-argument function calls, fresh local frames, local constants, reference/value arguments, recursion | Depth limit 64, conservative effects/order guards, no external routine linkage or local TYPE sections. |
| INTEGER | Checked signed 32-bit expressions, bit operators, DIV, restricted MOD | MAXINT excluded from normal storage; division truncates toward zero; signed MOD cases remain restricted. |
| BOOLEAN | Strict Boolean storage, operators and comparisons | Numeric values are not implicitly Booleans. |
| REAL | Exact normal-or-zero binary32 subset, checked promotion, ROUND/TRUNC and exact SQRT | No general controller rounding model; inexact operations can fail. |
| Trig | Exact degree cases for SIN/COS/TAN/ASIN/ACOS; restricted ATAN2 | Finite tables only. ATAN2 uses KAREL `(x,y)` order and nonnegative axes/positive equal diagonal; general bearings, EXP and LN are blocked. |
| STRING | Bounded ASCII storage, right truncation, concatenation/comparison, STR_LEN, restricted SUB_STR/INDEX/CHR/ORD | Direct STRING function results and unresolved substring/search boundaries remain blocked. Read-only value inputs have restricted temporary handling. |
| BYTE/SHORT | Aggregate storage, range checks and numeric value promotion | Initial BYTE data is unknown; BYTE initialization queries are blocked. SHORT 32767 means uninitialized. |
| Arrays | One-based fixed/named arrays up to logical rank three, exact whole copies, reference formals and named subarrays | Prototype bound of 32767 scalar leaves; whole-array value arguments prohibited; nominal identity and exact shape are retained. |
| Variable arrays | Explicit translation-time shapes for direct global wildcard declarations | No inference, controller/VR access, resize or persistence. |
| ARRAY results | Unsized anonymous outer ARRAY with scalar, prior named STRUCTURE, built-in record, exact-width JOINTPOS or prior named ARRAY elements; logical rank up to three | Every scalar leaf known/initialized; call only as complete direct-assignment RHS. One outer dimension; exact inner component names/shapes. Named outer results, flat multidimensional sources and terminal STRING arrays remain blocked. |
| Structures | Prior named structures, nested fields/arrays, checked copies and internal results/value temporaries | Nominal type identity, complete known initialization and capacity checks; no type aliases or ABI claim. |
| USING | Restricted bare structure selectors and field priority | Lexical scope; no complex selector expressions or dynamic caller scope. |
| Positional data | CONFIG, VECTOR, XYZWPR, XYZWPREXT, POSITION data and exact value/result copies | POSITION orientation starts unknown and remains recursively read-only. No invented orientation, geometry or robot defaults. |
| Joint data | Opaque JOINTPOS1..9, exact-width copies, restricted explicit-context REAL-array conversions | No source field/index access, implicit group discovery, positional conversion or kinematics. |
| VECTOR | Checked exact arithmetic, scaling, cross/dot products, equality and routine values | Group ambiguous products, initialize components, preserve exact intermediates; degenerate cases remain restricted. |
| Conversion | Selected INTEGER/REAL text conversions and fixed-decimal formatting, exact XYZWPR extraction via UNPOS | Canonical formats, exactness and disjoint output requirements; no inferred native status/rounding behavior. |
| DELAY | Checked 0..86400000 ms through a host callback | Host timing is not controller timing; step budget is not a time budget. |
| WRITE | Restricted single STRING, BOOLEAN or nonnegative INTEGER request | Recorder/callback only; restricted literal STRING formats; no FILE destinations, multi-item, general REAL/negative INTEGER output or READ. |
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

Internal functions may return arrays of INTEGER/BOOLEAN/REAL/BYTE/SHORT, prior
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
terminal STRING arrays remain blocked. A named subarray cannot be returned as an
anonymous outer array. Named STRUCTURE elements may contain supported STRING
fields and named arrays under the existing recursive copy rules.

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
