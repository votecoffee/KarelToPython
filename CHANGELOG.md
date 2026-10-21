# Changelog

## 0.78.0 - 2026-10-21

- Add Pythonic GET_REG, SET_INT_REG and SET_REAL_REG on an explicit in-memory
  NumericRegisters bank. Preserve INTEGER/REAL kinds, selected-output behavior,
  unused output state, shared bank ownership and portable missing/range statuses.
- Add generated-script JSON context, defensive value-free operation records,
  transitive read/write effects and source-located reports. Check all output types
  and aliases before bank access, retain source order, prior effects, FOR guards
  and cleanup, and preserve user routines. Add an authored example, guide and
  bank/ownership/CLI regressions. Real controller access and native status/count
  equivalence remain unsupported; strict is future work.

## 0.77.0 - 2026-10-21

- Add Pythonic GET_USEC_TIM and GET_USEC_SUB for host elapsed time, with a
  documented two-minute counter ring and optional synchronous clock injection.
  Accept unshadowed bare clock syntax and preserve user routines/declarations.
- Add defensive clock observations, transitive routine effects and source-located
  timer reports. Preserve short circuiting, source order, pending assignments,
  step/FOR guards, sticky ABORT and frame cleanup on clock failures. Include
  rollover, adapter and ownership checks, an authored example and a guide.
  Native timing/encoding and calendar clock access remain unsupported; strict
  remains future work.

## 0.76.0 - 2026-10-21

- Add Pythonic CNV_STR_TIME and CNV_TIME_STR for supplied packed date/time data,
  using documented bit fields, Gregorian calendar checks, two-second precision
  and signed 32-bit patterns. Parse optional seconds and write zero for invalid
  text; emit complete fixed English text with checked output capacity.
- Preserve argument order, prior effects, output state on errors, internal routine
  precedence, transitive FOR protections and frame cleanup. Add independent bit
  pattern checks, an authored example, a guide and explicit report policies.
  Clock access and native equivalence remain unsupported; strict is future work.

## 0.75.0 - 2026-10-21

- Add Pythonic WAIT FOR on supported BOOLEAN expressions, including internal
  function results and ordinary short-circuit operators. Recheck until true,
  yield through the existing sleeper with zero seconds after false checks and
  apply the normal step budget even to a constant-false wait.
- Preserve condition/callback effects, transitive host-delay reports, source
  diagnostics, FOR protections, sticky ABORT and frame cleanup. Add polling,
  typed-input, error and ownership regressions, an authored example and a guide.
  Native event/handler syntax and controller scheduling remain unsupported;
  strict remains future work.

## 0.74.0 - 2026-10-21

- Add Pythonic approximate POSITION/XYZWPR comparison (`>=<`) with explicit
  per-instance location/angle tolerances and CONFIG checking. Use Euclidean
  distance and shortest rotation angle with stable behavior near zero/180 degrees.
- Add required context flags to generated scripts and a read-only defensive
  tolerance tuple. Capture complete operands before later effects, retain existing
  failure/FOR protections and keep exact/ordered pose relations blocked.
- Add independent quaternion, context, effect and CLI checks, an authored example,
  documentation and report policies. Strict remains future work; native tolerance
  metrics and controller acceptance remain unverified.

## 0.73.0 - 2026-10-21

- Add Pythonic APPROACH and ORIENT axis queries on POSITION and XYZWPR, returning
  independent writable VECTOR copies of positive Z and Y. Use POSITION columns
  directly and the existing portable rotation convention for XYZWPR.
- Require complete checked poses, retain protected source orientation, capture
  once before later effects and preserve user routines with the same names. Add
  source-located query reports, independent quaternion and ownership checks, an
  authored offset example, a guide and semantic notes. Strict remains future work;
  these checks establish offline behavior, without native/controller acceptance.

## 0.72.0 - 2026-10-21

- Add Pythonic POSITION and mixed POSITION/XYZWPR operands to colon, INV and
  FRAME. INV preserves its operand representation; colon and FRAME return
  POSITION when any input is POSITION, retaining XYZWPR-only results.
- Calculate POSITION results directly as checked matrices with protected
  orientation columns and independent location/CONFIG data. Capture and validate
  each operand before later effects; retain exact routine interfaces and guards.
- Add independent quaternion, evaluation-order and ownership checks, a complete
  authored example, a geometry guide and explicit report policies. These establish
  offline behavior; strict mode and native/controller acceptance remain future work.

## 0.71.0 - 2026-10-21

- Add Pythonic whole-value POSITION/XYZWPR assignment conversion, initializing
  protected matrix columns from explicit XYZWPR and extracting canonical Euler
  values from complete proper POSITION matrices. Copy location/CONFIG data and
  retain read-only orientation, independent values and stable target storage.
- Validate finite complete shapes, unit/orthogonal columns and determinant +1
  with an explicit 1e-9 tolerance. Convert before destination evaluation; retain
  prior effects, skip target effects on failure and preserve FOR/frame cleanup.
  Add source-located conversion entries and a current conversion policy.
- Add 47 regressions, independent quaternion checks, an authored conversion/copy
  example, runtime-only portability and a representation guide. Routine interfaces,
  whole arrays, geometry operands and other positional types retain their checks.
  Strict remains future work; no native/controller or kinematic equivalence claim.

## 0.70.0 - 2026-10-21

- Add Pythonic FRAME with three or four complete XYZWPR points, right-handed
  orthogonal axes, checked 10 mm spacing and optional fourth origin/CONFIG.
  Use stable norms and the existing portable Euler convention; reject degenerate
  or non-finite geometry with source-located offline errors.
- Capture each complete argument before later effects and copy result CONFIG.
  Preserve internal FRAME routines, ordinary names, private result fields,
  arrays/structures, RETURN, stable references and FOR/cleanup protections.
  Extend frame reports with constructor arity and selected origin.
- Add 45 regressions, independent quaternion basis checks, an authored
  construction/transform example, runtime-only portability and a construction
  guide. Other positional/VECTOR inputs and native/controller behavior remain
  unsupported; strict remains future work.

## 0.69.0 - 2026-10-21

- Add Pythonic XYZWPR colon composition and INV inversion using explicit portable
  Z-Y-X rigid transforms, canonical Euler angles and a bounded gimbal-lock policy.
  Copy right CONFIG on composition and input CONFIG on inversion without solving
  robot configuration. Retain internal INV routines and ordinary declarations.
- Capture complete operands once in source order; preserve independent results,
  stable destination storage, field/array/value/RETURN composition, FOR effect
  checks, failure preservation and cleanup. Add source-located frame reports.
- Add 53 regressions, independent quaternion checks, an authored round-trip example,
  runtime-only portability and a transform guide. Other positional/VECTOR operands,
  external axes, implicit frame discovery and kinematics remain blocked. Strict
  remains future work; no native Euler/configuration or controller claim.

## 0.68.0 - 2026-10-21

- Accept Pythonic ENVIRONMENT, COMMENT and ALPHABETIZE as syntax-checked metadata,
  retaining NOLOCKGROUP. Preserve raw/source-located and decoded report entries,
  environment requirements and generated Program.source_directives tuple pairs.
- Scan directive quotes before recognizing trailing comments or continuations.
  Preserve literal ampersands, comment markers and doubled apostrophes; enforce
  COMMENT's length/header rules and explicit duplicate/name/form guards.
- Add 49 regressions, an authored helper/output example, runtime-only portability
  and a directive guide. No implicit environment definitions, extra calls,
  controller attributes or offline storage reordering. Runtime directives remain
  blocked; strict remains future work.

## 0.67.0 - 2026-10-21

- Add Pythonic CNV_STR_CONF/CNV_CONF_STR fallbacks with portable CONFIG flag/turn
  grammar and complete canonical text. Preserve explicit user routines, source
  order, concrete capacities, stable aggregate storage and both output effects.
- Parse success writes status zero; portable invalid-text status one preserves
  CONFIG. Guard failures raise before conversion writes. Formatting snapshots
  initialized CONFIG before target effects and rejects insufficient capacity
  without truncation. Retain overlap, FOR, type, field and cleanup protections.
- Add 60 regressions, an authored CONFIG/POS example, runtime-only portability,
  reports and a grammar/status guide. Omitted values and nonzero status are
  explicit offline choices; no robot/group mask, native error or controller
  validity is inferred. Strict and group-specific CNV_CNF_STRG remain future work.

## 0.66.0 - 2026-10-21

- Add Pythonic POS(x,y,z,w,p,r,c) construction of fresh XYZWPR values with six
  finite numeric components and a copied complete CONFIG. Retain documented
  coordinate/angle bounds, existing CONFIG checks and explicit robot-validity
  limits. Preserve internal POS routines and ordinary declarations of that name.
- Support routine results/value arguments, arrays, structures and constructor
  fields with chosen left-to-right evaluation, checked copies and failure
  cleanup. Extend constructor receiver type lookup without duplicate call reports;
  preserve POSITION protections and UNPOS's source/output constraints.
- Add source-located constructor reports, current policies, 54 regressions, an
  authored POS/UNPOS example, runtime-only portability and a construction guide.
  Strict remains future work; no implicit geometry, group/frame context or
  robot configuration validity is inferred.

## 0.65.0 - 2026-10-21

- Add Pythonic READ widths, integral bases and quoted STRING input, with up to
  two ordered dynamic INTEGER format expressions per scalar. Capture each target
  once before its formats, validate before later captures and retain concrete
  storage/capacities, nested requests, transitive effects and FOR protections.
- Extend TextInput with exact single-line fields, Python numeric whitespace and
  base grammar, documented BOOLEAN abbreviations and doubled-apostrophe decoding.
  Keep short/malformed fields consumed without later input or response stores;
  preserve metadata preflight, complete-response checks and ordinary cleanup.
- Add optional per-target format metadata without changing plain scalar requests.
  Typed host/JSON responses remain already decoded. Fix multiline CR list items,
  add 59 format regressions, an authored example and a format guide; remove the
  stale example count from the root README. Strict remains future work.

## 0.64.0 - 2026-10-21

- Add runtime.TextInput for explicit ASCII input with persistent line/column/EOF
  observations. Parse checked Python decimal integers/floats, documented BOOLEAN
  tokens and STRING line remainders; preserve storage ranges and capacity limits.
- Support leading/repeated/CR-only READ markers, with optional line_breaks
  metadata and no extra response values. Keep scalar metadata compatible and
  bound the combined scalar/marker count to 1024. Retain target capture, complete
  response validation, prior effects and FOR/frame cleanup.
- Add mutually exclusive generated-script --read-text/--read-values adapters,
  explicit UTF-8 paths with optional BOM and joint-axis context composition.
  Add 62 text/CR regressions, an authored text example with independent fixtures,
  runtime-only portability and a text-input guide. Native parser/status/device
  semantics remain outside this Pythonic contract; strict is future work.

## 0.63.0 - 2026-10-21

- Support Pythonic omitted-file scalar READ through an explicit synchronous
  typed host callback. Capture writable targets once in source order, validate
  the complete response, then assign in destination order; preserve ordinary
  scalar/STRING/narrow checks, captured storage, prior effects and cleanup.
- Add defensive input metadata/outcome observations, source-located input sites
  and transitive input-request/global/formal-write effects. Keep active FOR
  counters, constants, temporary/aggregate targets, CONFIG subfields and
  POSITION orientation writes protected. No implicit stdin or callback retry.
- Add JSON response batches through generated-script --read-values, composing
  with explicit joint-axis context. Add 77 input/CLI regressions, runtime-only
  portability coverage, an authored example with input/trace/output fixtures and
  an input guide. Native file/device parsing, CR, formats, status/error clearing
  and controller input remain outside this offline contract; strict is future work.

## 0.62.0 - 2026-10-21

- Interpret VEC(x,y,z) as a Pythonic expression constructor for fresh checked
  VECTOR values. Support numeric components, function/value composition and
  explicit component access. Preserve existing internal VEC routines and
  ordinary declaration names; explicit internal routines keep precedence.
- Support unary VECTOR plus/minus as independent checked values and same-level
  cross/dot chains with chosen left association and existing precedence.
  Preserve rounded arithmetic, captured operands, initialized finite components,
  intermediate type checks, storage ownership and POSITION protections.
- Add constructor report metadata, current vector policies, 71 execution/runtime
  regressions, an authored example with independent fixtures and a vector guide.
  Preserve conservative constructor/sign/chain guards internally for the future
  strict milestone; no frame transforms, kinematics or native constructor ABI claim.

## 0.61.0 - 2026-10-21

- Support Pythonic transparent TYPE aliases for supported scalars, bounded STRINGs,
  records, joints and prior named types, including chains and routine interfaces.
  Preserve original aggregate identities, component types, dimensions, capacities
  and joint widths; new ARRAY/STRUCTURE definitions remain distinct nominal types.
- Support bounded STRING alias formals with matching-capacity references or
  private writable value copies. Validate initialized ASCII input <=254 characters,
  then truncate to the alias capacity before the routine body; preserve that
  capacity on later writes and report the actual temporary capacity.
- Retain source-located forward/self/cyclic/duplicate checks, storage and ownership
  rules, leaf completeness for aggregate values/results, and BYTE/SHORT element
  and field restrictions. Keep conservative alias rejections internally for the
  future strict milestone. Add an alias guide, 76 execution/runtime regressions and an
  authored example with independent fixtures; no native type ABI/runtime claim.

## 0.60.0 - 2026-10-21

- Support Pythonic nested USING scopes and dotted named STRUCTURE selectors.
  Inner/right-most fields take precedence; unmatched outer fields remain
  available and enclosing bindings are restored after the block. Resolve selector
  lists against enclosing aliases only, without chaining aliases within one list.
- Define field priority over constants in expressions/targets, explicit function
  calls and procedure call context over field names, and bare field priority over
  zero-argument function names. Keep CASE labels compile-time constants.
- Expand aliases to independent absolute paths before type, effect and control-flow
  checks; preserve original storage roots, reference/value behavior and callee
  lexical isolation. Keep indexed/call/grouped selectors, field FOR counters,
  builtin record selectors and unsupported jumps blocked.
- Add parent/depth/selector metadata, 52 execution regressions, an authored example
  with independent fixtures and a USING guide. Preserve conservative checks
  internally for the future strict milestone; no native namespace/lifetime claim.

## 0.59.0 - 2026-10-21

- Permit Pythonic global-counter FOR bodies to call helpers when transitive
  potential global writes exclude active counters. Track global roots through
  recursive calls, writable formal actuals, assignments, FOR initialization and
  built-in outputs; preserve local shadowing and conservative dead-branch checks.
- Permit bare active-counter references to transitively read-only formals.
  Keep writable references blocked; grouped/expression actuals and INTEGER-to-REAL
  forwarding remain independent values. Formal/nonlocal counters in parameterized
  routines still require fresh locals; direct writes and loop jumps remain blocked.
- Clear initialized FOR counters with finally on normal/empty completion,
  RETURN, ABORT, final-bound/body errors, callback failure/interruption and resource
  exhaustion. Capture checked return values first; keep prior non-counter effects.
  Initial-expression/initial-store failures retain prior counter state/effects.
- Add global-write report metadata, current FOR policies, 72 execution/runtime
  regressions, an authored example with independent fixtures and a FOR guide.
  Preserve conservative rejection/error-state tests internally for the future
  strict milestone; no native counter-state, scheduling or runtime-equivalence claim.

## 0.58.0 - 2026-10-21

- Define Pythonic SUB_STR with positive one-based starts, nonnegative counts,
  clipping at the source end and a 254-character result cap before consumption.
  Accept zero counts as initialized empty strings; bound slicing before allocation
  even for MAXINT counts. Smaller destination/result capacities still truncate.
- Define INDEX empty search as position 1, including an empty source, using
  Python find plus the existing one-based offset. Preserve exact case-sensitive
  first matches, zero for absence, ASCII, initialization and character-domain checks.
- Add STRING operation policy metadata and remove superseded public limitations.
  Preserve one-time argument order, earlier effects and assignment destinations
  on failures, and routine cleanup. Retain conservative guards internally for
  the future strict milestone; no native substring/search edge-behavior claim.
- Add 56 execution/runtime regressions, an authored example with independent
  fixtures, runtime portability coverage and a STRING operation guide.

## 0.57.0 - 2026-10-21

- Accept bounded KAREL INTEGER expressions for WRITE widths, alignment, base and
  precision. Evaluate each value, width and second format once in source order;
  validate/render each item before the next, preserving prior effects on failure.
  Include format calls in routine-effect analysis and retain existing FOR guards.
- Add Pythonic quoted STRING escaping and truncation, preserving paired quotes
  and complete doubled-apostrophe escapes. Tiny widths preserve the wrapper;
  zero/large widths use bounded natural length. Keep combined output <=254.
- Support negative CNV_REAL_STR precision for uppercase scientific output with
  Python rounding, preserving caller capacity and blank/asterisk overflow markers.
- Add dynamic format metadata, a public guide, 65 execution/runtime regressions
  and an authored example with independent fixtures. Keep conservative tests
  internally for the future strict milestone; no native formatting equivalence
  claim. Bound oversized INTEGER tokens before Python integer parsing.

## 0.56.0 - 2026-10-21

- Add Pythonic named ARRAY results and anonymous fixed, wildcard or mixed result
  dimensions, including flat matrices and cubes. Resolve fixed sizes from global
  constants and check wildcard sizes against concrete returned storage.
- Preserve exact nominal identity, outer representation, component types,
  initialized leaves and independent RETURN copies. Enforce three logical
  dimensions and the 32767-leaf bound; fail known mismatches during translation
  and generic runtime mismatches before destination assignment.
- Define Pythonic ARRAY_LEN on matrices and nested arrays as the first concrete
  dimension, like Python len, without requiring initialized scalar leaves.
- Add result declaration/RETURN metadata, 89 execution/runtime regressions,
  a complete authored example and a result-shape guide. Retain earlier result-form
  and multidimensional-length rejections internally for the future strict milestone;
  no native compiler, call ABI or controller-runtime equivalence claim.

## 0.55.0 - 2026-10-21

- Add Pythonic ARRAY value arguments as checked independent writable copies.
  Grouped whole arrays, array fields, named subarrays and ARRAY function results
  retain concrete shape, nominal identity, element capacities and protection.
  Require every scalar leaf known/initialized; preserve the 32767-leaf bound.
  Bare actuals remain references, with no copy-back from value temporaries.
- Compose ARRAY results in grouping, compatible user-routine arguments, direct
  RETURN forwarding, logical-rank-one ARRAY_LEN and aggregate access. Accept
  subscripts/fields after explicit calls or grouped aggregate expressions.
  Preserve one-time left-to-right evaluation and detached result ownership.
- Add copy/call-site metadata and report policies, 88 execution/runtime
  regressions and an authored example with independent fixtures. Preserve
  conservative rejection tests internally for the future strict milestone.
  ARRAY declaration forms, nominal identity, initialization, POSITION protection,
  conversion argument and FOR-counter boundaries remain; no native ABI claim.

## 0.54.0 - 2026-10-21

- Enable Pythonic function composition in operators, multi-argument calls,
  comma-separated subscripts, assignment targets, conversions and FOR bounds.
  Evaluate ordinary operands and actuals once from left to right; bare actuals
  keep live references while value actuals capture independent copies.
- Change BOOLEAN AND/OR to Python short circuiting. Capture assignment values
  before resolving targets, including checked independent aggregate copies.
  Capture VECTOR operands before later calls can mutate their source storage.
  These chosen rules can change behavior when retranslating older programs.
- Preserve earlier effects and frame cleanup on errors/ABORT, along with type,
  initialization, shape, ownership, output-overlap and FOR-body counter checks.
  Document conversion input/reference evaluation and one-time FOR bounds.
- Add the evaluation policy report, 80 execution regressions, an authored example
  and compatibility guide. Retain conservative ordering tests internally for
  the future strict milestone; no native evaluation-order equivalence claim.

## 0.53.0 - 2026-10-21

- Add Pythonic internal STRING function results: plain `STRING` chooses capacity
  254, while `STRING[n]` accepts a global constant capacity in 1..254. RETURN
  validates initialized ASCII and right-truncates before routine-frame cleanup.
  Results compose as ordinary string values under existing type/effect guards.
- Allow writable STRING value arguments using independent capacity-254
  temporaries. Bare ordinary storage retains caller identity and capacity;
  grouping, literals, constants, expressions and function results use private
  copies. Preserve input bounds, normal assignment truncation and conversion
  output behavior, with no copy-back after completion or failure.
- Add result/copy metadata, 59 regression tests and a complete authored example.
  Document the chosen policy and conflicting manual statements. Preserve the
  previous conservative STRING tests for the future strict milestone; no native
  controller acceptance or STRING ABI claim.

## 0.52.0 - 2026-10-21

- Extend Pythonic `WRITE` to mixed STRING, BOOLEAN, signed INTEGER, BYTE, SHORT
  and finite REAL items, plus CR mapped to LF. Evaluate and format items once,
  left to right; send one complete request to the recorder or callback.
- Add numeric minimum widths, integer bases 2..16 and REAL fixed/scientific
  precision using Python rounding. Preserve scalar initialization/type guards,
  STRING formatting, output observations and callback/error cleanup behavior.
- Bound combined output to 254 ASCII characters and statements to 1024 items.
  Rendering or length failure emits no outer request; prior expression effects
  and nested requests remain visible. Keep files/devices, READ and dynamic format
  expressions unsupported. Strict mode remains a future milestone.
- Add 52 regression tests, a runnable mixed-output example, a public output guide
  and source-page semantic notes. Preserve earlier conservative WRITE tests
  internally; validation remains offline.

## 0.51.0 - 2026-10-21

- Make Pythonic numeric behavior the public default, selectable through
  `translate(..., mode="pythonic")` and `--mode pythonic`. Embed the selected mode
  in generated programs and hashed report context. Strict mode is reserved for a
  future milestone; preserve the previous exactness runtime and regression tests.
- Accept ordinary finite floats, rounded arithmetic, general SQRT and degree
  trigonometry, all ATAN2 quadrants, EXP and LN. ROUND now uses Python ties to even;
  signed MOD follows Python remainder. Retain checked INTEGER storage and domain,
  initialization, shape, ownership and effect guards.
- Use Python numeric text parsing, rounded fixed-decimal output, signed integer
  bases 2..16 and bounded minimum-width padding. Preserve output capacities,
  overflow markers and failure-before-assignment checks.
- Add public numeric mode documentation, a runnable Pythonic example and API/CLI,
  storage, math-domain and nested/threaded-policy tests. Update existing example
  fixtures for changed ROUND and underflow results. Validation remains offline.

## 0.50.0 - 2026-10-21

- Extend `CNV_INT_STR` length-1 output to nonnegative values in bases 2..9, using
  minimal positional numeric digits and exactly one leading blank. Signed decimal
  bases 0/10 and the existing INTEGER expression range remain supported.
- Preserve caller capacities, blank/asterisk overflow markers, output references,
  invalid-base clearing and existing effect/cleanup checks. Negative nondecimal
  values, alphabetic-digit bases 11..16 and other widths remain blocked.
- Add 30 regression checks for base/value/capacity boundaries, independent binary
  and octal oracles, numeric roundtrips, aliasing, failure preservation and effect
  guards, plus a runnable authored example. Validation remains offline.

## 0.49.0 - 2026-10-21

- Extend exact `CNV_REAL_STR` fixed formatting from 0/1/2 to 0..254 fractional
  digits, with a bounded rational calculation and no host decimal rounding.
- Preserve strict REAL/INTEGER inputs, positive minimum widths requiring no extra
  padding, caller STRING capacities and blank/asterisk overflow markers. Rounding,
  scientific notation and precision outside the explicit prototype bound remain
  blocked before output mutation; no native validity range is inferred.
- Add 30 regression checks using independent Decimal formatting oracles, range
  endpoints, long expansions, capacity thresholds and existing effect/reference
  guards, plus a runnable authored example. Validation remains offline.

## 0.48.0 - 2026-10-21

- Add `ARRAY OF STRING[capacity]` function results with constant capacities 1..254,
  plus named ARRAY rows/planes whose terminal elements are bounded STRINGs.
- Keep exact capacity/type/shape checks and independent initialized ASCII copies.
  Reference formals retain caller capacity, which is checked at RETURN; no result
  truncation or inferred temporary capacity. Existing context/effect/cleanup
  checks and direct STRING result rejection remain.
- Add 45 regression checks and a runnable authored STRING ARRAY example. The
  combined result forms are an offline interpretation of the documented ARRAY
  and STRING rules, without native compiler or controller validation.

## 0.47.0 - 2026-10-21

- Resolve unshadowed zero-parameter internal function names as calls in value
  expressions, including scalar conditions and direct ARRAY result assignments.
- Resolve after USING fields and before effect analysis. Keep local storage
  bindings, storage receiver roots and all existing call, argument-order, effect,
  ARRAY-context, recursion and frame-cleanup checks. Explicit calls remain accepted.
- Report bare-call source locations and exact result specifications. Add 54
  regression checks, a runnable authored example and a manual-backed semantic
  contract. Validation remains offline, without native compiler/controller claims.

## 0.46.0 - 2026-10-21

- Add prior named fixed ARRAY elements to unsized anonymous ARRAY function
  results, supporting two or three logical dimensions with one outer dimension.
- Preserve each component's declared identity, shape and terminal element type
  through recursive checked copies and stable destination references. Return
  reports include logical rank and the exact resolved element specification.
- Keep direct-assignment-only use, full known initialization, scalar-leaf limits
  and existing effect/cleanup guards. Named outer results, flat multidimensional
  sources, terminal STRING arrays and whole ARRAY value arguments remain blocked.
- Add 40 regression checks and an authored named-component ARRAY example.
  Validation remains offline, without native compiler or controller claims.

## 0.45.0 - 2026-10-21

- Add unsized anonymous one-dimensional ARRAY function results with prior named
  STRUCTURE, CONFIG/VECTOR/XYZWPR/XYZWPREXT/POSITION and exact-width JOINTPOS elements.
- Reuse recursive checked copies that retain nominal types, nested shapes, STRING
  field capacities, joint widths and POSITION orientation protection. Every scalar
  leaf must be known and initialized; the 32767 scalar-leaf limit still applies.
- Retain direct-assignment-only use, exact destination type/length and existing
  effect, alias and frame-cleanup guards. Broader result forms remain blocked.
- Add 46 regression checks and an authored aggregate ARRAY example. Evidence is
  offline; no controller defaults, native ABI or runtime equivalence is inferred.

## 0.44.0

- Support checked BYTE/SHORT ARRAY function results alongside the earlier scalar
  ARRAY result subset.
- Establish the public package layout, portable tests/examples, semantic notes,
  repository hygiene checks and wheel/source distribution metadata.
