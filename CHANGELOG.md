# Changelog

## 26.1023.140206 - 2026-10-23

- Use the supplied transparent icon artwork in the workbench header and window
  icon, with eight original sizes from 16 to 256 pixels and Windows taskbar identity.
- Package the PNG assets unchanged in wheels and source distributions; retain
  image references and apply the default icon to future application windows.
- Add headless resource/window-wiring checks and a narrowly hashed binary-artwork
  exception to repository validation; routine checks continue to open no windows.

## 26.1023.134348 - 2026-10-23

- Add numeric and position register receive/send between explicit local/peer
  banks, with value/comment options, explicit groups and RPREG/RPOSREG aliases.
- Preserve numeric kinds, Cartesian/joint representations and external axes;
  snapshot and preflight selected values/comments before publishing transfers.
- Add authored CLI execution, persistence, copy isolation, malformed-source,
  destination-preflight and counter-protection regressions.
- Make native GUI/editor tests opt-in and move desktop CI to a manual workflow.
  Routine conversion tests and package acceptance open no windows.

## 26.1023.132259 - 2026-10-23

- Add 17 RGET/RSET procedures over explicit PeerBanks for numeric/string
  registers, register/port comments, port values and BOOLEAN simulation queries.
- Preserve numeric kinds, selected outputs, bank capacities, ordinary port rules
  and argument/counter protections; require each peer's own banks/type codes.
- Persist detached peer snapshots and completed updates without networking,
  controller discovery or local-bank fallback. Document manual signature conflicts.
- Add an authored example covering all remote procedures, fresh CLI execution,
  linked-source sharing, isolation, failure guards and runtime-only delivery checks.

## 26.1023.130323 - 2026-10-23

- Add LOAD_STATUS for attached Programs and explicit load snapshots, counting
  any known global content including partial aggregates and imported references.
- Add GET_ATTR_PRG with selected outputs, portable AT/PT constants, derived
  identity/type/comment and explicit metadata for sizes/times/task settings.
- Add SET_ATTR_PRG for owner, comment, source name and source version; persist
  checked metadata and block writes to active/paused Programs and linked frames.
- Track plain run activity through failure cleanup and reject recursive driving.
  Add authored CLI execution, runtime-only packaging and metadata regressions.

## 26.1023.123045 - 2026-10-23

- Add CNV_CNF_STRG with status output and optional caller-rooted group selection.
  Explicit ConfigTextFormats profiles select flags and turns; persist them in
  ExecutionContext JSON without inferring native robot masks.
- Preserve complete CONFIG capture, source-order evaluation, output capacity and
  counter protections; add an authored example and CLI execution checks.
- Protect CLI source/output/report hard-link aliases and reject symbolic-link
  outputs. Share source protection and complete-file replacement with the GUI;
  failed forced replacement retains the previous output.
- Add subprocess CLI regressions for translation, generated-script execution,
  report hashes, exit codes, source preservation and operation without GUI imports.

## 26.1023.115555 - 2026-10-23

- Add line numbers, bounded KAREL/Python syntax coloring, cursor position,
  Go to Line and font zoom to the desktop workbench.
- Add literal Find/Replace with case selection, forward/backward wrapping and
  search across source, Python and report views. Source replacements support
  grouped Undo/Redo and check the UTF-8 size limit before editing.
- Navigate both ways between source statements and generated Python using exact
  compiler source-map entries; leave unmapped generated scaffolding explicit.
- Preserve Unicode match boundaries and prioritize application shortcuts over
  native text navigation bindings. Add native editor and headless helper checks.
- Match literal queries in Python to avoid native multi-line Unicode search
  crashes on Linux Tk builds; keep Find and Replace All case rules consistent.

## 26.1023.110723 - 2026-10-23

- Add a Tkinter desktop workbench and karel2py-gui windowed launcher, with the
  timestamp version in the title bar, header and About dialog.
- Open/edit/save KAREL sources, validate or translate in a background worker,
  review generated Python and located diagnostics, and export Python/JSON.
- Check linked-project construction without running source bodies; share the
  existing translator, linkage and literal ARRAY-shape parsing behavior.
- Invalidate results after edits/options changes, protect source aliases during
  export, confirm unsaved/overwrite choices and detect external source edits.
- Add headless document/export tests and native Tk workflow tests, with explicit
  display requirements and virtual-display coverage on Linux CI.

## 26.1022.232239 - 2026-10-22

- Switch release versions to fixed UTC build timestamps in YY.MMDD.HHmmss format.
  Preserve historical feature/release versions in their original documentation.
- Display the version in translator and linked-project command banners and help;
  add --version to the linked-project command. Keep banners on stderr so stdout
  summaries and JSON remain parseable.
- Read package version metadata from karel2py.__version__ as the single source.

## 0.101.0 - 2026-10-22

- Add GET_PORT_ASG, SET_PORT_ASG, GET_PORT_MOD, SET_PORT_MOD and IO_MOD_TYPE
  over explicit PortBank topology, physical capacities and module metadata.
- Validate complete assignment spans before staging: direction-compatible
  BOOLEAN batches of 1..8 points, group widths of 1..32 and analog single points.
  Bound mode masks and require valid odd BOOLEAN output pairs for complementary mode.
- Keep active and pending settings separate. SET stages and GET reads active
  settings; the host's apply_configuration applies all pending rows. Task POWERUP
  notifications do not apply shared I/O settings.
- Persist active/pending configuration with detached snapshots. Preserve logical
  values, simulation/comments and pulse ownership/deadlines independently;
  configuration does not simulate physical wiring, inversion or complementary signals.
- Add 55 tests, two runnable examples, documented configuration/status policies,
  runtime-only and installed-package checks. Native enums/alarms, physical signal
  adapters, controller acceptance and strict mode remain future work.

## 0.100.0 - 2026-10-22

- Add CHECK_NAME with a documented portable base-name grammar and status 0/2;
  no file backend or existence lookup is required.
- Add MOVE_FILE for closed RD/FR files over explicit MemoryFiles namespaces or
  mapped DirectoryFiles roots. Support case-insensitive star filename/type
  patterns, device-root separators and literal nonrecursive subdirectories.
- Preflight complete batches for rooted paths, busy handles, destination/case/
  alias collisions, duplicate targets, size and 32767-file limits. Preserve
  exact bytes and filename case, and refresh moved directory cache data.
- Move synchronously in sorted order with normal budget checks. Late OS, status
  or budget failures retain completed per-file moves without automatic retry or
  rollback; directory roots/mappings remain explicit host configuration.
- Add 45 tests, two runnable examples, installed/runtime-only checks and public
  selection/status/failure policies. Native name/flash behavior and strict mode
  remain future work.

## 0.99.0 - 2026-10-22

- Allow whole QUEUE_TYPE logical values through GET_VAR/SET_VAR. Copy FIFO
  order, sequence gaps/counter and initialization state using the checked
  collection codec; retain receiver object identity with independent entries.
- Release the receiver's old buffer binding without synchronizing any ARRAY.
  Its next queue operation binds an adequate explicit INTEGER ARRAY; normal
  capacity/identity guards then apply. Self-copy also releases binding.
- Snapshot SET queues before later selectors and GET queues after selectors.
  Copy an uninitialized queue with portable status 12311; type mismatch writes
  status 3 only. Validate both sides before publishing state or cache outputs.
- Accept detached queue snapshots in VariableStore.define and retain typed
  save/load continuation. Reject malformed queue/buffer state, embedded resources
  and whole FILE/PATH transfers; ordinary resource value interfaces stay guarded.
- Add 44 tests, two runnable examples and documented source/ownership/status
  policies. Native copy semantics and strict mode remain future work.

## 0.98.0 - 2026-10-22

- Extend GET_VAR/SET_VAR to same-rank ARRAY prefix transfers across different
  extents and outer identities. Preserve receiver tails, retain terminal type
  checks and truncate STRING elements to receiver capacity.
- Capture typed SET sources once before later selectors, including missing
  references. Propagate partial record/joint/ARRAY data with status 12311;
  preserve unknown BYTE contents distinctly and check types before clearing.
- Prepare complete replacements before writes; retain exact/disjoint/protected
  output guards, earlier argument effects and stable cache IDs on success.
  Incompatible GET/SET types or ARRAY ranks return status 3 without data changes.
- Fix nested multidimensional ARRAY state reloads while retaining existing flat
  configurations. Preserve protected POSITION orientation children on restore.
- Add 70 tests, two runnable examples, portable/installed-package checks and
  public transfer policies. Ordinary assignment/routine type rules remain;
  strict mode and native/controller equivalence remain future work.

## 0.97.0 - 2026-10-22

- Include PATH and QUEUE_TYPE globals and explicit bindings in typed context
  snapshots. Preserve nominal PATH schemas, headers, node order, partial data
  and unknown BYTE markers; preserve queue FIFO order, sequence IDs and counter.
- Restore queues without their former buffer reference/capacity; the first
  explicitly supplied queue-operation ARRAY binds when it can hold the saved
  entries. Retain within-run buffer identity and deliberate INIT_QUEUE reset.
- Validate schemas, host shapes, known values, capacities, CONFIG domains and
  canonical markers before state-file writes. Keep FILE handles, native layouts
  and task checkpoints outside snapshots.
- Add 54 tests, two runnable examples, installed/runtime-only verification and
  documented portable state/rebinding policies. Strict mode remains future work.

## 0.96.0 - 2026-10-22

- Extend Pythonic UNPOS to pose values, POSITION/XYZWPREXT, constructors, geometry
  and typed routine/service results; decompose JOINTPOS through existing supplied
  forward kinematics and selected root group/frame/tool.
- Capture and validate the source before output selectors, permit source/output
  aliases through an independent snapshot and retain exact, protected, disjoint
  output guards. Preserve direct XYZWPR/XYZWPREXT components; POSITION uses the
  established matrix/Euler convention. Validate external fields without adding
  external-axis outputs or changing robot snapshots.
- Support bare and zero-argument CURPOS/CURJPOS with both masks discarded,
  preserving declared-name priorities and explicit mask/group forms.
- Add 54 tests, two examples, policies and runtime-only coverage. Preserve the
  conservative strict compiler/runtime contract and document Pythonic choices.

## 0.95.0 - 2026-10-22

- Add PROG_LIST over attached KAREL Programs and explicit ProgramCatalog metadata
  with all six program types, type filters, star patterns, sorted bounded pages,
  checked name/type formats and optional Pythonic cursor pagination.
- Preserve complete output batches on capacity/option failures, clear unused
  slots on success and persist explicit catalog metadata without loading code
  or inferring program identities from files, variable bindings or callbacks.
- Add 48 tests, two examples, report policies and runtime-only coverage. Document
  the manual syntax/table discrepancy and portable directory/index choices;
  retain older minimal runtime bundles. Strict mode remains future work.

## 0.94.0 - 2026-10-22

- Accept JOINTPOS operands in colon, INV, FRAME, MIRROR, APPROACH, ORIENT and
  approximate comparison through supplied forward kinematics and selected
  root-task group/frame/tool. Joint frame results use Cartesian XYZWPREXT.
- Snapshot and convert each joint once before later operands/arguments or target
  selectors; retain exact interfaces, limits/padding, external metadata rules,
  explicit tolerances and sticky abort without changing current robot state.
- Add source/report policies, transitive service-effect reporting, 50 tests,
  two modeled examples and runtime-only coverage. Document portable result/context
  choices and retained native/strict boundaries.

## 0.93.0 - 2026-10-22

- Add VAR_INFO over explicit static globals, fields, ARRAY elements and PATH
  nodes/headers: canonical types/codes, logical dimensions, STRING capacity and
  read-only initialization metadata with documented aggregate/resource choices.
- Add VAR_LIST with case-insensitive star filters, canonical type selection,
  sorted pagination, four formats and capacity checks. Keep output batches atomic
  on portable status failures and preserve source initialization and protection.
- Add source/report policies, 63 tests, two examples, runtime-only coverage and
  documented native-evidence boundaries. Strict mode remains future work.

## 0.92.0 - 2026-10-22

- Add read-only whole CONFIG, VECTOR, POSITION, XYZWPR and XYZWPREXT UNINIT
  queries. Any missing leaf or complete nested record returns TRUE, with checked
  schemas and known scalar values; geometry validity remains a separate check.
- Support record fields, individual ARRAY elements and parenthesized storage;
  evaluate computed selectors once. Retain scalar/joint behavior, copy guards,
  BYTE distinction and whole ARRAY/PATH/user STRUCTURE/resource exclusions.
- Add source-located report facts, 36 tests, two examples, runtime-only coverage
  and documentation of the portable partial-record choice. Strict remains future.

## 0.91.0 - 2026-10-22

- Add PULSE DOUT statements and handler actions with checked INTEGER operands,
  eight-millisecond duration rounding, blocking waits and NOWAIT deadlines.
- Integrate host polling, port reads/snapshots and scheduler virtual time; drain
  pending pulses after task completion/pause. Linked pulses belong to the caller.
- Preserve terminal output state, reject overlapping pulses and cancel deadlines
  on successful writes. Keep pending work out of serialized context values.
- Add 42 tests, two root examples, a linked pulse project, runtime-only coverage
  and documented portable timing/lifecycle choices. Strict/native work remains future.

## 0.90.0 - 2026-10-22

- Add JOINTPOS to/from POSITION, XYZWPR and XYZWPREXT whole assignments through
  supplied robot adapters/models, selected frame/tool and calling task group.
- Reuse explicit kinematic checks, padding and limits. Inverse assignments require
  supplied current joints as seed; source CONFIG/external metadata flows through.
- Preserve destinations on failure, detach values before target selectors, retain
  sticky abort and exact routine/RETURN/whole-array interfaces. Add source-located
  service/report records, 37 tests, two examples and runtime-only coverage.
- Document portable context/seed choices; strict/native behavior remains future.

## 0.89.0 - 2026-10-22

- Add COMPARE_FILE over memory and rooted directory backends: ASCII differing
  records or binary first-difference offsets, with bounded JSON reports written
  through existing FILE cursor, append, terminator and flush semantics.
- Add PRINT_FILE through the WRITE recorder/callback, preserving ASCII bytes
  in bounded synchronous chunks. Validate before output; retain completed effects
  on callback failure, budget exhaustion or abort.
- Add closed named-file reads, fresh directory input, busy-file alias checks,
  40 authored tests, two runnable examples and runtime-only portability checks.
- Document portable statuses, comparison/report choices and native boundaries;
  strict mode remains a future milestone.

## 0.88.0 - 2026-10-22

- Add GET_TSK_INFO over explicit task registries and schedulers, including
  directional name/number lookup and selected INTEGER/STRING output preservation.
- Expose live task/program states, active module/routine, latest checkpoint,
  logical frame count and scheduler quantum. Keep linked callers and concurrent
  library stacks separate; clean inspection frames on return, stop and failure.
- Accept explicit informational metadata for the other documented attributes.
  Publish portable TSK_/PG_ identifiers and additional existing-runtime states.
- Add 40 integration tests, a runtime-only check, a two-task example project,
  report policy and manual-backed semantic notes. Strict/native behavior remains future.

## 0.87.0 - 2026-10-22

- Add GET_TIME and SET_TIME on an explicit CalendarClock, frozen or advanced by a
  supplied elapsed-microsecond callback. Reuse packed calendar conversion helpers;
  zero sets are no-ops and no operating-system clock is changed.
- Preserve complete datetime microseconds in snapshots and restore frozen clocks.
  Validate samples, backward observations and calendar bounds before output/anchor
  changes; retain shared linked context and ordinary output/counter protections.
- Add two authored examples, 45 integration tests, runtime-only portability checks,
  report policy and manual-backed semantic notes. Strict mode remains future work.

## 0.86.0 - 2026-10-22

- Add POS_REG_TYPE with stored representation/axis reporting and optional group
  selection rooted in the caller, including linked routines. Share optional-middle
  argument mapping with routine and handler write analysis.
- Add CLR_POS_REG for one group or all groups, retaining other register values,
  comments and independent copies; valid absent clearing is idempotent.
- Add CLR_PORT_SIM for logical flags, retaining last supplied values/comments
  while restoring ordinary input-write restrictions. Existing JSON persists results.
- Add two authored examples, 37 integration tests, report policy and source-backed
  semantic notes. Native hardware modes, alarms and strict remain future work.

## 0.85.0 - 2026-10-22

- Accept exact model/limit width or JOINTPOS9 with zero-only unused slots across
  forward/inverse conversion and joint range checks. Reject discarded nonzero,
  partial or invalid axes. Model inverse outputs support model width or nine slots.
- Pad narrow joint-register reads without changing stored representation, so
  current queries, registers, conversion and range checks work together.
- Persist explicit limits-only contexts and latest valid model frame/tool maps,
  removals and selections. Reachability follows current selections, and linked
  conversions/range checks use the caller's group consistently.
- Add two authored examples, 33 integration tests, report policy and semantic
  notes. Native unused-axis encoding, physical motion and strict remain future.

## 0.84.0 - 2026-10-22

- Add RobotState with complete supplied pose/joints, defensive copies, atomic host
  updates and persistence for current snapshots in state-only or modeled groups.
- Add CURPOS and CURJPOS with optional groups, checked mask outputs or literal
  zero discard. CURPOS can use configured DH/frame/tool math; CURJPOS pads unused
  result slots to JOINTPOS9. Current-state math can observe outside-limit joints.
- Add bare/explicit CURR_PROG reporting the executing module as STRING[12], with
  ordinary declaration precedence and linked caller group behavior for queries.
- Reject unconfigured groups in flat contexts and preserve latest state/active
  group during serialization. Keep normal model conversion limit checks.
- Add two authored examples, 41 integration tests, report policy and source-backed
  semantic notes. Strict mode and physical acquisition/motion remain future.

## 0.83.0 - 2026-10-22

- Add indirect port value/comment/simulation procedures with explicit port-type
  mappings, checked scalar conversions and shared direct-port storage. Simulated
  input values can be updated through SET_PORT_VAL; physical modes stay outside.
- Add independent numeric, position and string register comments, constructor
  metadata and JSON persistence without initializing absent register values.
- Add per-task CallParameters and GET_TPE_PRM, selected output preservation,
  missing argument status 17042 and linked caller identity.
- Add three authored examples, 39 integration tests, public API/report policy
  and source-backed semantic notes. Strict and native I/O/TP execution remain future.

## 0.82.0 - 2026-10-22

- Add POST_ERR_L with eleven named portable ERSEV constants, explicit local/global
  task scope, normalized offline effects and persistent source/severity metadata.
- Deliver named/numeric pause and abort requests through target checkpoints,
  including paused ABORT handlers and linked caller identity. Intentional child
  ABORT/STOP in synchronous TaskRegistry calls returns control to the caller;
  runtime failures still propagate. Final CONTINUE notifies handlers.
- Implement ATR_FIELD capacity-sized STRING reads, custom ASCII EOL input and
  exact byte cursors across mixed newlines. Failed text transfers preserve all
  targets and the cursor; binary and write field conventions remain unchanged.
- Add two authored examples, 43 integration tests and public semantic boundaries.
  Native severity encodings, physical motion/servo effects and strict remain future.

## 0.81.0 - 2026-10-22

- Add explicit FIFO counting semaphores, POST/CLEAR/COUNT/PEND procedures,
  semaphore conditions and SIGNAL, timed/indefinite waits and cancellation cleanup.
- Add POST_ERR, scoped bounded error history, ERROR/wildcard conditions and
  NOMESSAGE/NOPAUSE/NOABORT handler actions. Invalid runtime values still fail
  after notifying handlers with a documented portable error category.
- Add explicit POWERUP continuation for live paused Programs/scheduled tasks,
  shared pending control requests across library calls and EVAL action capture.
- Scan after final signal statements, wake delayed tasks for pending aborts,
  preserve semaphore reservations and reject persistence of active waits.
- Add authored notification examples, integration regressions and source-backed
  semantic notes. Native priorities, motion, POST_ERR_L and strict remain future.

## 0.80.0 - 2026-10-22

- Add typed JSON save/load for service banks and attached program globals, with
  partial initialization and explicit system/foreign variable namespaces.
- Add caller-rooted DirectoryFiles, atomic close/flush, file management/listing,
  reverse byte order and ASCII EOL. Correct ATR_IA to interactive flushing;
  use ATR_UF for binary fields. Existing RB/WB modes continue to work.
- Add deterministic cooperative scheduling with virtual time, parked delays,
  EVENT signals, port edges, EVAL capture, scan intervals and local lifetimes.
- Add typed source-project linkage, shared FROM globals and independent stacks
  for concurrent library calls, with caller budgets and sticky abort cleanup.
- Add configurable standard-DH kinematics, bounded numerical IK/reachability,
  external kinematic joints, groups/frames/tools and extended-pose tolerances.
- Add authored programs, a three-module project, public setup/mapping guide and
  integration regressions. Keep strict mode and native behavior gaps explicit.

## 0.79.0 - 2026-10-22

- Add explicit offline string/position registers, digital/group/analog ports,
  GET_VAR/SET_VAR and shared checked service context.
- Add in-memory text/binary FILE transfers, cursor/status procedures, typed PATH
  nodes/headers and copies, and initialized FIFO QUEUE_TYPE operations.
- Add cooperative handlers with multiple WHEN clauses, connected timers, retained
  pause/resume frames, terminal task stop, explicit task registry and external
  Python routine bindings. `--cooperative` also enables host control.
- Add MIRROR, XYZWPREXT frame/conversion metadata and explicit robot-model
  conversion/reachability adapters. No robot model or native behavior is inferred.
- Add authored examples, service equivalence matrix, semantic evidence, portable
  distribution checks and integration regressions. Preserve the strict milestone.

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
