# Language support

This is the supported prototype subset as of 0.99.0. Acceptance is specific to
source form, type and context. A supported feature can still reject uncertain
inputs at runtime. The [semantic notes](semantics/README.md) separate documented
rules, implemented restrictions and unresolved native behavior.

Public translation uses [Pythonic numeric equivalents](numeric-modes.md).
Strict mode is a future milestone; older exactness contracts are preserved
internally and in the historical semantic notes.

| Area | Supported subset | Limits |
| --- | --- | --- |
| Source | Case-insensitive ASCII identifiers, comments, ENVIRONMENT/COMMENT/ALPHABETIZE/NOLOCKGROUP metadata, bounded complete-token continuations, doubled apostrophes | Environment requirements do not load definitions or grant extra calls. No arbitrary/runtime directives, token fusion, backslash escapes or multiline string literals. |
| Control flow | Assignment, IF/ELSE, WHILE, REPEAT, inclusive FOR/DOWNTO, SELECT, RETURN | FOR calls must protect active counters through transitive write checks; read-only counter references allowed; initialized counters clear on all scope exits. Formal/nonlocal counters in parameterized routines require fresh locals. SELECT uses first matching case and errors without a match/ELSE. |
| Labels | Restricted labels and unconditional GOTO | Jumps within the same block or to an ancestor; no arbitrary entry into nested control blocks. |
| Routines | Internal procedures/functions, bare zero-argument function calls, fresh local frames, local constants, reference/value arguments, recursion | Depth limit 64; chosen Pythonic left-to-right evaluation; existing FOR rules; typed FROM project/callback linkage; no native external ABI or local TYPE sections. |
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
| Positional data | CONFIG, VECTOR, XYZWPR, XYZWPREXT, POSITION data and exact value/result copies; POS constructs XYZWPR from six numbers and explicit CONFIG | POS retains coordinate/angle bounds and complete CONFIG checks without robot-specific validity. POSITION orientation starts unknown; explicit XYZWPR assignment can initialize it while retaining recursive read-only protection. No robot defaults. |
| Initialization queries | UNINIT on supported scalar/joint storage and whole builtin records, including nested fields and individual ARRAY elements | Any missing builtin-record leaf means TRUE; read-only schema/type checks. Whole ARRAY, PATH, user STRUCTURE, FILE, QUEUE_TYPE and BYTE queries remain blocked. |
| Variable inspection | VAR_INFO metadata and VAR_LIST filtered/paged global names | Current/attached declarations and explicit bindings; canonical types, bounded dimensions/formats, portable initialization flags and statuses; no local/controller discovery. |
| Program listing | PROG_LIST with optional cursor | Attached Programs and explicit immutable metadata; type filters, sorted pages, checked formats and persisted catalogs; no program discovery or loading. |
| Collection persistence | PATH and QUEUE_TYPE context variables | Typed partial PATH data, queue FIFO/sequence state and explicit buffer rebinding; portable logical snapshots without native layouts or task checkpoints. |
| POSITION conversion | Whole assignments among XYZWPR, XYZWPREXT and POSITION; independent location/configuration and checked orientation matrices | Finite complete values; proper unit/orthogonal matrix checks with explicit 1e-9 tolerance; exact interfaces and whole-array types; context-free Cartesian conversion only; model-backed joint assignments are listed below. Widening zeros external metadata; narrowing drops it. |
| Output pulses | PULSE DOUT with blocking/NOWAIT statements and blocking handler actions | Explicit bank, rounded duration, host polling or scheduler virtual time; portable override/lifecycle rules. |
| Kinematic assignment | Whole JOINTPOS to/from POSITION/XYZWPR/XYZWPREXT using supplied robot adapters/models | Selected frame/tool and root group; inverse needs current joints as seed; exact routine/RETURN/whole-array interfaces remain. |
| Joint data | Opaque JOINTPOS1..9, exact-width copies, restricted explicit-context REAL-array conversions | No source field/index access or implicit group discovery. RobotContext supplies explicit kinematics. |
| VECTOR | VEC construction, unary signs, checked float arithmetic, scaling, left-associated cross/dot products, equality and routine values | Initialized finite components; parentheses override association; explicit internal VEC routines retain precedence. Zero/parallel cross products allowed. No frame transforms or kinematics. |
| Conversion | Python INTEGER/REAL text parsing, signed bases 2..16, rounded fixed/scientific REAL output, UNPOS pose-value and model-backed joint extraction | Bounded width/precision, caller capacities and disjoint outputs; source snapshots and chosen Pythonic formatting/pose conventions. |
| CONFIG text | CNV_STR_CONF and CNV_CONF_STR with complete checked CONFIG data, portable flags/turn grammar and canonical text | Omitted values are explicit portable choices; parse failure status 1 preserves CONFIG. No robot/group masks, native error mapping or CNV_CNF_STRG. |
| Time text | CNV_STR_TIME and CNV_TIME_STR on supplied packed date/time values | Gregorian 1980..2107, fixed English text, two-second precision and signed bit patterns; complete STRING capacity required; no clock/timezone access or native equivalence. |
| Microsecond timers | GET_USEC_TIM host monotonic sampling and GET_USEC_SUB elapsed subtraction, with optional clock injection | Portable two-minute ring, one clock and intervals shorter than two minutes; no native encoding/tick precision or calendar clock access. |
| Offline numeric registers | GET_REG, SET_INT_REG and SET_REAL_REG on an explicit in-memory NumericRegisters bank | Explicit count/initial values, exact checked outputs and portable missing/range statuses; typed JSON save/load; no controller backend or native status/count/persistence claim. |
| Frame transforms | POSITION/XYZWPR/XYZWPREXT and model-backed JOINTPOS colon composition, INV inversion and three/four-point FRAME construction | JOINTPOS first becomes XYZWPREXT through supplied forward context; other types retain representation precedence. Proper matrices or portable Euler choices, existing external metadata and 10 mm FRAME bounds; no VECTOR frames or context discovery. |
| Pose axis queries | APPROACH and ORIENT on POSITION/XYZWPR/XYZWPREXT return independent writable VECTOR values for positive Z/Y | Complete finite poses, checked CONFIG and proper POSITION matrices; no normalization, defaults, other positional operands or controller acquisition. |
| Position comparison | Approximate >=< on POSITION/XYZWPR/XYZWPREXT, including mixed operands, returns BOOLEAN | Explicit per-instance distance/angle/external-axis tolerances and CONFIG choice; complete proper poses; Euclidean distance and shortest rotation angle; no native defaults, exact/ordered relations or other operand types. |
| DELAY | Checked 0..86400000 ms through a host callback | Host timing is not controller timing; step budget is not a time budget. |
| WAIT FOR | Repeated checks of supported BOOLEAN expressions, including internal functions | Ordinary step budget, short-circuit rules and sleep(0.0) after false checks; cooperative handlers are separate; no hardware acquisition or native event/timing equivalence. |
| WRITE | Mixed scalar lists, signed integers, finite REALs, dynamic INTEGER formats, quoted STRING escaping/truncation, narrow integers and CR newlines | One complete recorder/callback request per statement, <=254 characters. Bounded formats; explicit FILE output uses MemoryFiles or a caller-rooted DirectoryFiles; no live devices or aggregate output. |
| READ | Scalar variables, fields/elements and narrow aggregate leaves through typed callbacks, JSON batches or TextInput; CR, widths, bases and quoted STRINGs | Capture each target then its formats once; complete-response validation. Chosen text rules; MemoryFiles/DirectoryFiles add explicit text/binary FILE transfers; no live devices, native parser claim, aggregate targets, CONFIG subfields or POSITION orientation writes. |
| ABORT | Bare statement with sticky termination and frame cleanup | Also available in cooperative actions and explicitly registered ABORT_TASK; no motion cancellation or controller restart behavior. |


| Registers and ports | String/position/joint banks, digital/group/analog ports, static GET_VAR/SET_VAR paths | Explicit context, disjoint outputs and bounded same-rank ARRAY/missing-data transfers; attached foreign globals and explicit system roots; no live acquisition. |
| FILE | OPEN/CLOSE, text/binary READ/WRITE, byte cursors, byte counts and status | MemoryFiles or explicit DirectoryFiles root; copy/delete/rename/list, ATR_UF binary, reverse byte order, EOL and interactive flush; no native device routing. |
| PATH / QUEUE_TYPE | Typed nodes/header, append/insert/delete/copy/length; initialized FIFO queues and GET_VAR/SET_VAR logical queue transfers | One-based nodes, explicit buffer capacity/rebinding, portable status/sequence conventions and no native layout claim. |
| Cooperative control | Multiple WHEN handlers/actions, controls, connected global timers, task pause/resume/stop, TaskRegistry and external callbacks | Deterministic scheduler, event/semaphore/error/lifecycle conditions, EVAL predicates/actions, scan intervals, local lifetimes, suppression actions and typed project linkage; no native interrupts or motion behavior. |
| Robot model | MIRROR, extended pose metadata, JOINT2POS/POS2JOINT, IN_RANGE/J_IN_RANGE | Explicit right-handed reflection convention, supplied callbacks/limits or standard-DH models with bounded IK, explicit groups/frames/tools and external joints; no inferred robot context or native reachability claim. |

See the [offline service matrix and guide](offline-services.md) for the complete
contracts and remaining gaps; [portable projects](portable-projects.md) covers
the project implementation and setup.
The [initialization query guide](initialization-queries.md) covers whole builtin
records, partial leaves, grouped storage and retained container exclusions.
[Control notifications](control-notifications.md) covers 0.81.0 semaphores, error
records, runtime-failure observation and explicit powerup recovery.
[Task and file extensions](task-and-file-extensions.md) adds scoped POST_ERR_L,
handler-aware task requests, ATR_FIELD reads and custom record terminators.
[I/O and CALL parameters](io-and-call-parameters.md) adds indirect port access,
simulation, register/port comments and supplied per-task GET_TPE_PRM arguments.
[Current robot state](current-robot-state.md) adds supplied/model-derived CURPOS,
CURJPOS, group snapshots, mask outputs and executing-module CURR_PROG queries.
[Joint interoperability](joint-interoperability.md) connects padded queries and
register values with model conversions, range checks and persisted frame/tool context.
The [register lifecycle guide](register-lifecycle.md) covers position representation
inspection, one/all-group clearing and removing logical port simulation.
The [calendar clock guide](calendar-clock.md) covers explicit GET_TIME/SET_TIME,
elapsed-time adapters and frozen datetime snapshots.
The [task inspection guide](task-inspection.md) covers GET_TSK_INFO lookup,
live execution data, portable constants and supplied attributes.
The [file comparison and printing guide](file-comparison.md) covers COMPARE_FILE
and PRINT_FILE with explicit backends, bounded reports and recorded/callback output.
The [kinematic assignment guide](kinematic-assignments.md) covers model-backed
whole-value joint/Cartesian changes and retained exact interfaces.
The [output pulse guide](pulses.md) covers timed DOUT values, blocking/NOWAIT,
explicit polling and scheduler integration.

See [STRING operations](string-operations.md) for substring, search, length and
character equivalents, evaluation order and retained input checks.
See [Pythonic FOR](pythonic-for.md) for global-counter calls, read-only counter
arguments, bounds and cleanup on early exits/errors.
See [Pythonic USING](pythonic-using.md) for nested field paths and namespace choices.
See [TYPE aliases](type-aliases.md) for transparent names, identity and bounded
STRING routine interfaces.
See [Pythonic vector expressions](pythonic-vectors.md) for construction, signs,
product association and composed length calculations.
See [Pythonic input](pythonic-read.md) for typed READ callbacks, input batches,
observations and error behavior.
See [text input](text-input.md) for ASCII parsing, CR, cursor and --read-text.
See [READ formats](read-formats.md) for widths, bases, quoting and dynamic expressions.
See [POS construction](pos-construction.md) for Cartesian values, CONFIG copies and bounds.
See [CONFIG text](config-text.md) for portable parsing, formatting, status and capacity rules.
See [source directives](source-directives.md) for metadata syntax, placement and environment boundaries.
See [frame transforms](frame-transforms.md) for composition, inversion and portable angle/configuration policies.
See [frame construction](frame-construction.md) for point-defined axes, spacing and optional origin.
See [POSITION conversions](position-conversions.md) for whole assignments, matrix checks and orientation protection.
See [POSITION geometry](position-geometry.md) for mixed operands, result types and direct matrix operations.
See [pose axis queries](position-axes.md) for APPROACH/ORIENT mapping and writable VECTOR results.
See [position comparisons](position-comparisons.md) for >=< metrics and explicit execution context.
See [Boolean waits](boolean-waits.md) for repeated condition checks, host yields and budget limits.
See [time text](time-text.md) for calendar validation, packed bits and complete formatting.
See [microsecond timers](microsecond-timers.md) for host clocks, rollover and deterministic adapters.
See [numeric registers](numeric-registers.md) for explicit banks, output checks and script context.

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
