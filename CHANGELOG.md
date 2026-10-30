# Changelog

## 26.1030.180659 - 2026-10-30

- Accept explicit CONFIG turn and BOOLEAN fields in Pythonic READ, including
  nested records/ARRAYs, POSITION.CONFIG_DATA, exact routine formals and captured
  USING values. Validate canonical parent schemas and retain turn bounds -8..7.
- Preflight every typed response before any destination or committed FILE cursor
  changes, preserving ordinary scalar formats and BYTE/SHORT normalization.
  Apply the policy across callbacks/JSON/TextInput, memory/rooted/virtual/shared
  FILEs, serial streams, pipes and injected keyboard line input.
- Preserve captured selectors/formats through waiting reads and pause/resume;
  retain cancellation, stop/abort, budget cleanup, readonly/counter guards and
  existing portable failure/status rules. Whole CONFIG READ and generic output
  aliases remain protected; native CONFIG binary layout is unverified.
- Add config_field_reads and config_field_read_policy reports, 72 regressions,
  four examples, two linked projects and compiler-free runtime coverage. Update
  README, API, semantic ledger and remaining-support inventory; defer strict mode.

## 26.1030.154410 - 2026-10-30

- Extend GET_VAR/SET_VAR to compatible context-free user STRUCTURE schemas and
  same-rank record ARRAY prefixes. Match identical field-name sets in receiver
  order; support nested record/ARRAY layouts, bounded STRING, checked numeric
  domains and context-free Cartesian/joint-width fields while retaining receiver tails.
- Validate copied original data before conversion and stage the complete selected
  result before data, entry, cache or status publication. Preserve missing record/
  ARRAY containers, partial data, distinct BYTE unknown values, SHORT sentinels,
  stable known child storage and existing capture/overlap/protected-field/FOR guards.
- Keep model-backed record variable transfers incompatible with status 3; supplied
  robot models are never inferred. Generic transfer helpers retain their exact
  record default unless explicitly opted into this Pythonic policy.
- Add record_variable_transfer_policy reports, 72 authored regressions, four
  examples, two linked projects and compiler-free runtime coverage. Update README,
  API and remaining-support inventory; preserve native cache/status/ABI boundaries
  and defer strict mode.

## 26.1030.151821 - 2026-10-30

- Extend explicit joint/Cartesian model conversion through compatible user
  STRUCTURE trees, nested records/ARRAY fields and whole record ARRAYs at source
  assignment, private ordinary arguments and RETURN boundaries.
- Preflight declared source schemas, all known data, context-free conversions,
  complete model operands and proper POSITION matrices before adapter calls.
  Retain receiver schemas, logical layouts, partial ordinary data and allocation
  bounds; stage the entire converted output before publication.
- Run models in receiver field order and row-major ARRAY order using current
  root-caller group/frame/tool/seed context at each scalar call. Preserve prior
  explicit host effects on failure, private lifetimes, RETURN cleanup ordering,
  stable receiver children and sticky ABORT without replay or implicit state updates.
- Add kinematic_record_policy/provenance reports, 72 authored regressions, four
  examples, two linked projects and compiler-free runtime coverage. Refresh README,
  API and remaining-support inventory. Context-free helpers, BYNAME, declared
  links, raw callback results and GET_VAR/SET_VAR remain exact; native motion,
  inferred robot context, controller ABI equivalence and strict mode stay excluded.

## 26.1030.145630 - 2026-10-30

- Convert compatible user STRUCTURE schemas and record ARRAY terminals at
  Pythonic source assignment, ordinary argument and RETURN boundaries. Match
  identical field-name sets in receiver order, including nested records, ARRAY
  names/layouts, integral/REAL fields, STRING capacities and context-free geometry.
- Keep receiver schemas and stable child storage. Validate declared source specs,
  original data and complete independent output before publication; preserve
  partial data and existing domain, schema-depth and allocation guards.
- Give schema-changing arguments private writable values without copy-back;
  retain compatible references, actual generic ARRAY receiver schemas and RETURN
  capture before frame/counter/timer cleanup. Keep exact BYNAME, generic helpers,
  linked signatures and raw callback results.
- Add record_schema_policy/provenance reports, 72 authored regressions, four
  examples and two linked projects. Replace obsolete source exclusions with
  execution and source-isolation checks; refresh README, API and remaining-support
  inventory. Model-backed record-field conversion, field-set changes, native ABI
  or controller equivalence and public strict mode remain outside this change.

## 26.1030.141231 - 2026-10-30

- Support same-terminal ARRAY names, bounded STRING capacities and flat/nested
  layouts with matching logical dimensions at source assignment, ordinary
  argument and RETURN boundaries. Preserve receiver schemas and source data.
- Keep compatible generic arguments borrowed; otherwise converted named/bounded
  interfaces receive private writable values without copy-back. Generic source
  assignments use the actual borrowed receiver schema after RHS capture.
- Validate source domains and ASCII capacity before output truncation/widening;
  preserve missing/unknown markers, child identities, existing effect ordering
  and exact BYNAME/helper/callback/linkage contracts. Numeric, positional and
  explicit-model ARRAY changes also support matching logical layouts.
- Add array_schema_policy/provenance reports, 72 authored regressions, four
  examples and two linked projects. Update existing source exclusions with
  positive execution checks and preserve legacy/native boundaries. Refresh
  README, API, support backlog and semantic notes. No native ARRAY ABI,
  inferred robot context, physical motion or public strict-mode claim is added.

## 26.1030.131923 - 2026-10-30

- Extend numeric, Cartesian, joint-width and explicit-model ARRAY source
  conversions to named outer types and matching separately named nested
  components at assignment, ordinary argument and RETURN boundaries.
- Preserve receiver schemas, component names and existing child identities.
  Converted bare arguments remain private without copy-back; shape boundaries,
  numeric domains, missing data, positional completeness and allocation checks
  still run before publication. Model adapters retain explicit caller context.
- Keep exact-type aliases, same-terminal nominal checks, BYNAME, raw callback
  results, generic helpers and linked declaration signatures intact. Add named
  conversion provenance/policy reports and transitive private-alias classification.
- Add 60 authored regressions, four standalone examples and two typed linked
  projects, including nested counters and caller-group model conversions.
  Update README, API, support backlog and semantic notes. Strict mode,
  native ARRAY ABI/controller equivalence and physical motion remain future work.

## 26.1030.124630 - 2026-10-30

- Support CONNECT/DISCONNECT TIMER on exact INTEGER routine parameters,
  record fields, ARRAY leaves and named USING aliases. Bare exact arguments
  borrow caller storage; grouped/computed and ordinary numeric conversions
  retain private value cells. Connections belong to the live callee frame.
- Coordinate timer cell claims across linked/concurrent states in a shared
  ExecutionContext. Validate original endpoints, records and frame ownership,
  recheck after clock callbacks, release exact claims and retain uncertain ones.
  Protect claimed cells from variable-archive restores, including transient owners.
- Propagate direct/transitive timer writes through routine aliases and reject
  unsafe active or handler-retained FOR counters while allowing detached values.
  Preserve checkpoint timing, caller timers, pause/resume and exact unwind cleanup.
- Add formal_timer_policy reports, 64 authored regressions, four standalone
  examples and two linked projects. Update README, API, support backlog and
  semantic notes. Context JSON retains data without live timer ownership;
  strict mode and native/controller timing remain future work.

## 26.1030.120651 - 2026-10-30

- Support CONNECT/DISCONNECT TIMER for fresh routine-local INTEGER scalars,
  record fields, ARRAY leaves and captured named/grouped USING aliases.
  Bind connections to actual live defining frames; retain them across pause/nested
  calls and release exact owned registrations on RETURN and terminal unwind.
- Keep retained handler data readable after return while rejecting timer control
  through inactive frames. Preserve caller/global/private connections, recursive
  and concurrent invocation ownership, and changed-registration evidence.
- Distinguish local timer roots in other routines and globals with the same name
  for counter interference; retain conservative whole-root and handler/call guards.
- Add routine_local_timer_policy and frame-lifetime/provenance reports, 49 authored
  regressions, four standalone examples and two linked projects. Update README,
  API, support backlog and semantic notes. Formal timer roots and strict remain
  separate work; no native timer/controller equivalence is implied.

## 26.1030.114424 - 2026-10-30

- Support anonymous numeric ARRAY assignment, ordinary routine arguments and
  RETURN: checked INTEGER/BYTE/SHORT family changes and integral-to-REAL promotion
  retain matching rank/dimensions and concrete wildcard shapes.
- Stage all elements before destination publication, target selectors or later
  arguments. Preserve missing data, SHORT sentinels and unknown-BYTE restrictions;
  reject malformed source domains and narrowing overflow without partial writes.
- Give converted arguments private writable storage without copy-back, including
  retained handlers, forwarding, pause/resume and failure. Preserve exact aliases,
  named ARRAY identity, counter effects, linked signatures and raw callback results.
- Add numeric_array_conversions reports and numeric_array_policy, 54 regressions,
  four standalone examples and two linked projects. Refresh README, API, support
  and semantic guides; legacy and generic runtime ARRAY guards remain exact.

## 26.1030.111646 - 2026-10-30

- Support CONNECT/DISCONNECT TIMER on ordinary INTEGER leaves in computed USING
  captures, including nested reference aliases, indexed leaves, retained handlers,
  ordinary routine returns and pause/resume. Preserve independent copies and the
  existing whole-root counter protections without source copy-back.
- Validate initial timer data before clock acquisition; keep unknown initialization
  and multi-timer updates atomic on errors. Release timer registrations at terminal
  task cleanup and linked invocation exit, preserving pause and caller lifetimes.
- Add connected_timers source/provenance reports and connected_timer_policy,
  42 authored regressions, two standalone examples and two linked projects.
  Refresh README, API, support backlog and semantic notes. Declared routine-local
  and formal timer roots, native timing and public strict mode remain separate.

## 26.1030.031942 - 2026-10-30

- Extend explicit CANCEL FILE to pending READ_KB editors. Return procedure/IO
  status 6 without publishing text/count/key outputs or adding completed history.
  Preserve consumed events and queued suffixes for explicit retry.
- Give blocking reads per-key checkpoints and inclusive positive deadlines;
  keep cancellation precedence and atomic zero-time polling. Preserve echo/noecho,
  pane selection, explicit window output, pause/resume and suspension-frame rules.
- Retain independent FILE/binding/editor identities, validate metadata and preserve
  foreign registration replacements during owned cleanup. Stop/abort and budget
  failures keep their precedence; live handles/frames still prevent context save.
- Add 45 regressions, two standalone examples and three linked timer/window/
  suspension projects. Verify installed execution and saved-context replay.
- Refresh README, API and support/semantic guidance. Fileless menus, direct typed
  backend reads, default aliases, native keyboard/status/timing and strict remain separate.

## 26.1030.023712 - 2026-10-30

- Convert anonymous whole joint/Cartesian ARRAYs in assignments, private source
  arguments and RETURN with explicit scalar robot models/adapters and root groups.
- Preflight complete source geometry and output allocation before adapters, then
  stage row-major results before publication. Preserve current seed/frame/tool
  rules, external axes, model limits, independent values and zero-copyback behavior.
- Keep prior explicit host effects without retry or rollback; sticky abort stops
  further elements and prevents output. Preserve pause, stop and frame/counter
  cleanup. Record one value-free outcome per requested ARRAY conversion.
- Add 49 regressions, three standalone examples and a linked caller-group project;
  verify model JSON round trips, generated execution, installed CLI and saved replay.
- Update README, API and support/semantic guidance. Named source interfaces,
  storage-only GET_VAR/SET_VAR, raw callbacks and legacy guards retain their contracts;
  physical motion, native ABI and strict mode remain separate.

## 26.1030.020945 - 2026-10-30

- Convert anonymous positional ARRAY values across Cartesian representations or
  checked JOINTPOS widths in assignments, private source arguments and RETURN.
  Capture complete data once before later arguments, targets and frame cleanup.
- Extend GET_VAR/SET_VAR same-rank prefixes to these checked leaf conversions,
  including named ARRAY components, while preserving receiver schema, aliases,
  untouched tails and atomic data/cache/status publication.
- Keep exact bare aliases, partial same-type copies, named source interfaces,
  BYNAME, linked signatures and raw callback results under existing contracts.
  Preserve complete geometry, zero-only joint narrowing and allocation guards.
- Add 44 regressions, three standalone examples and a linked project, including
  independent ownership, failure ordering, pause, persistence and installed replay.
- Refresh README, API and support/semantic guidance. Whole-array joint/Cartesian
  kinematics, inferred robot context, native ABI and strict mode remain separate.

## 26.1030.014130 - 2026-10-30

- Translate explicit CANCEL FILE selectors in Pythonic source, handler actions
  and typed linked routines. Interrupt cooperative serial, plain-pipe and keyboard
  line/PASSALL typed reads without publishing partial destinations or cursor progress.
- Return portable IO_STATUS 6 and continue after a canceled READ. Preserve unread
  input and committed writes; idle registered FILEs succeed without discarding data.
- Validate captured handle identity and backend registrations before cancellation;
  retain pause/resume, sticky abort, stop/failure precedence and owned cleanup.
  Keep direct host/READ_KB jobs, default FILE aliases and native writes separate.
- Add 44 regressions, an idle read/write example and three timer-driven linked
  serial/pipe/keyboard projects. Verify installed CLI execution and saved replay.
- Refresh README, API, support boundaries and semantic guidance. Physical I/O,
  native status/timing and strict mode remain outside this offline model.

## 26.1030.011911 - 2026-10-30

- Translate local AT NODE and TIME BEFORE/AFTER NODE conditions, including
  wildcard destinations and one-time integer selector capture, using complete
  explicit node_times response schedules. Preserve original selected path indexes.
- Scan exact declared/event progress breakpoints; clamp BEFORE to segment starts,
  exclude start from wildcard destinations and preserve final-node AFTER rules.
  Keep holds, pause/resume, cancellation and caller ownership in existing scopes.
- Validate schedule shape, range, temporal references and saved history before
  admission. Preserve old response behavior and reject unsupplied/inferred arrivals
  or unsupported NOWAIT schedules without consuming responses.
- Keep MOVE clause/condition report metadata on its request when handler actions
  append their own uses. Add 40 regressions, three standalone examples and a linked
  project, with fresh installed CLI and saved-context replay checks.
- Refresh current README/API/backlog. Native timing, trajectory inference,
  asynchronous queues, multi-group synchronization and strict remain outside this model.

## 26.1030.004838 - 2026-10-30

- Translate motion-local Boolean WHEN/DO and UNTIL/optional THEN clauses with
  independent one-shot state, private EVAL captures, routine/USING storage and
  scoped unqualified controls. Preserve global condition numbers and consumers.
- Add explicit finite delay_ms responses and cooperative progress, active hold
  polling, pause/resume and current-group cancellation. Retain immediate output
  behavior and reject unsupported NOWAIT combinations before response consumption.
- Track root-owned active scopes with opaque grant identities; honor deferred
  abort/pause requests before completion and clean up stop/failure paths without
  overwriting foreign or externally stopped work labels.
- Persist validated progress, local trigger metadata and terminal outcomes; block
  active saves and pending reloads. Add 51 regressions, three standalone examples
  and a linked project, with fresh package and saved-context replay checks.
- Refresh current README/API/backlog. Queued/native motion, node/time conditions,
  trajectory calculation and strict mode remain outside the released model.

## 26.1030.001439 - 2026-10-30

- Add logical HOLD/UNHOLD/CANCEL statements and global handler actions with
  atomic explicit group selection, source-order capture and caller-owned state.
  Preserve stopped work and keep hold flags independent from work labels.
- Retain hold flags across canceled work and task termination, block new moves
  and automatic acquisition while held, and allow logical hand actions during
  held/active work. Keep stopped cancellation in CNCL_STP_MTN distinct.
- Capture six local WITH settings before MOVE operands, including checked
  interpolation types, finite speed values, Boolean configuration and detached
  Cartesian frame/tool data. Preserve global environments and robot feedback.
- Persist validated control transitions and typed settings, retaining old empty
  hold output. Add 41 regressions, three standalone examples and a linked project;
  update current README, API, backlog and legacy-only HOLD rejection coverage.
  Queued motion, remaining WITH variables, local handlers and strict remain future work.

## 26.1029.234813 - 2026-10-29

- Translate all seven basic MOVE forms, VIA, direct PATH-node destinations and
  inclusive PATH ranges into an explicit offline MotionRequests service.
  Capture validated detached operands or consume immediate scripted completions;
  retain NOWAIT intent without simulating queued motion, trajectories or feedback.
- Add logical OPEN/CLOSE/RELAX HAND and atomic ATTACH/RELEASE ownership over
  explicit banks. Preserve caller ownership across linked source calls and clear
  released-task bindings on completion, stop, abort and failure.
- Persist bounded typed request history, logical hands and remaining responses;
  validate restored data and retain source-located rejection evidence.
- Add 47 regressions, three standalone examples and a linked project; update
  isolated runtime distributions, current README, API and remaining-support notes.
  Motion-local clauses and strict mode remain future work.

## 26.1029.231800 - 2026-10-29

- Convert complete individual Cartesian representations and checked joint widths
  in GET_VAR/SET_VAR before atomic data/cache/status publication, preserving exact
  partial copies, ARRAY boundaries and destination storage identities.
- Add private synchronous bodies to ordinary Pythonic output and support nested
  CALL_PROG/CALL_PROGLIN execution under caller-owned budgets, state and resources.
  Preserve standalone run behavior, failure cleanup and sticky ABORT handling.
- Retain explicit 16-bit grayscale/GA/RGB/RGBA samples through supplied vision
  images and PNG export, with big-endian bytes, matching headers, byte-aware quotas
  and unsupported 16-bit BMP status. Preserve existing 8-bit artifact bytes.
- Add 66 regressions, three standalone examples and one linked project, refresh
  public support notes and correct variable-transfer formatting. Strict stays future work.

## 26.1029.224626 - 2026-10-29

- Add typed dynamic SELECT case expressions with selector-first capture, eager
  once-only label evaluation in source order and first-match dispatch after
  complete validation. Retain category, effect, counter and cleanup checks.
- Add checked integral-family and integral-to-REAL scalar/ARRAY prefix transfers
  in GET_VAR and SET_VAR, preserving source domains, receiver bounds, missing
  markers, atomic outputs, concrete types and stable storage identities.
- Allow explicit VECTOR/CONFIG/XYZWPR/XYZWPREXT/POSITION XML_SETVAR roots while
  retaining staged updates, readonly POSITION roots/descendants and CONFIG bounds.
- Add 73 regressions, three standalone examples and one linked project, with
  refreshed support notes, reports and semantic guides. Strict stays future work.

## 26.1029.222104 - 2026-10-29

- Add complete joint-width changes for whole assignments, private source routine
  arguments and RETURN values, with zero padding and zero-only narrowing. Retain
  exact same-type aliases and exact whole-array/BYNAME/linkage contracts.
- Apply XML attributes atomically through nested record and complete ARRAY paths,
  including BYTE/SHORT leaves. Preserve canonical duplicate checks, missing
  values, POSITION protection, CONFIG limits and retained storage identities.
- Accept single-character question matching in COPY/DELETE/RENAME/MOVE source
  basenames across existing explicit file backends, preserving star destination
  substitution, complete preflight and ordinary publication failure boundaries.
- Add 63 regressions, three standalone examples and one linked project, with
  updated reports, guides and remaining-support notes. Strict stays future work.

## 26.1029.000454 - 2026-10-29

- Add complete chained ARRAY subscripts across storage and returned values,
  normalizing to existing comma access while preserving evaluation/capture order,
  named boundaries, concrete shape/capacity and counter/alias protection.
- Add private model-backed joint/Cartesian source routine arguments and RETURN
  conversions with explicit robot, root group, frame/tool and inverse-seed context.
  Preserve exact linkage/BYNAME/width contracts, failure effects and current state.
- Add supplied RGBA palettes on indexed vision rasters, palette-inclusive quota
  preflight, indexed PNG and alpha-preserving BMP export. Keep existing grayscale,
  RGB and alpha artifacts unchanged without native acquisition or processing.
- Add 170 regressions, three standalone examples and two linked projects,
  current reports, public guides and semantic notes. Strict remains future work.

## 26.1028.234706 - 2026-10-28

- Add checked BYTE/SHORT FOR counters across supported storage and execution
  forms, with initialized-domain bounds, stable captures, whole-root protection
  and type-specific cleanup. Keep ordinary references and legacy guards intact.
- Convert differing POSITION/XYZWPR/XYZWPREXT source routine arguments into
  checked private values, and convert source RETURN expressions before cleanup.
  Preserve exact bare aliases, linkage/BYNAME/callback contracts and complete-input
  orientation/configuration checks without acquiring robot context.
- Allow anonymous STRING-array results to inherit concrete returned element
  capacity, preserving checked copies, missing markers, nominal identity and
  exact downstream capacity checks without defaulting or truncation.
- Add 165 regressions, three standalone examples and two linked projects,
  current reports, public guides and semantic notes. Strict remains future work.

## 26.1028.232505 - 2026-10-28

- Extend Pythonic SELECT to BOOLEAN, bounded ASCII STRING and finite numeric
  categories, with checked constant cases, single selector evaluation and first
  match across structured, labelled and cooperative execution. Keep BOOLEAN
  distinct from numbers and preserve legacy INTEGER-only behavior.
- Add direct BYTE/SHORT CREATE_VAR forms and supplied transparent narrow aliases,
  preserving exact BYNAME references, unknown/missing markers, allocation guards,
  rename metadata and saved context/archive behavior.
- Add wildcard renames between configured virtual volumes in one DeviceFiles
  bank, with complete destination capacity and source garbage preflight before
  publishing file keys and accounting; retain no-overwrite and alias guards.
- Add 158 regressions, three standalone examples and two linked projects,
  current support reports, public guides and semantic notes. Strict remains future work.

## 26.1028.231128 - 2026-10-28

- Add isolated private computed-USING INTEGER counters with whole-root protection,
  retained-alias checks and cleanup across structured, labelled and cooperative
  execution, without source copy-back or invented public variables.
- Add Pythonic BYTE/SHORT variables, aliases and typed routine interfaces, with
  exact references, checked private numeric conversions and initialized results.
  Preserve unknown/missing markers and legacy aggregate-only restrictions.
- Add preflighted wildcard renames within ordinary banks/volumes and plain pipe
  banks, preserving bytes/configuration and rejecting overwrite or alias overlap.
  Retain the explicit partial-publication boundary for late directory failures.
- Fix atomic binary SHORT sentinel publication in ordinary, pipe and serial FILE
  readers. Validate every decoded field before publishing the original raw values.
- Add 175 regressions, three standalone examples and two linked projects,
  current support reports, public guides and semantic notes. Strict remains future work.

## 26.1028.223057 - 2026-10-28

- Add computed USING selectors with independent checked record temporaries,
  left-to-right capture, nested selections and no copy-back. Named storage stays
  live; private-counter/timer and ordinary schema/readonly guards remain explicit.
- Add opt-in cooperative serial READ waits, host feed and explicit EOF, atomic
  typed publication, pending guards and cancellation cleanup. Preserve finite
  defaults and explicit FILE close semantics.
- Preserve supplied grayscale/RGB alpha in PNG and 32-bit V4 BMP exports,
  without premultiplication. Keep legacy image bytes unchanged and strengthen
  raw/combined quota preflight and encoder validation.
- Add 147 regressions, three standalone examples and two linked projects,
  current reports, support guides and semantic notes; strict remains future work.

## 26.1028.215956 - 2026-10-28

- Add captured writable INTEGER fields, ARRAY elements and USING fields as
  Pythonic FOR counters, with stable selection, aggregate-root protection and
  cleanup in both structured and labelled/cooperative execution.
- Add VECTOR translation-left operands, independent VECTOR inversion and FRAME
  point inputs with explicit pose origins. Preserve complete-value checks and
  right-pose representation, CONFIG and external metadata.
- Add finite serial FILE streams with supplied RX/TX data, text/binary transfer,
  close-time input consumption, bounded persistence and exclusive handles.
  No host device is opened and SerialPorts metadata remains independent.
- Add 169 regressions, three standalone examples and two linked projects,
  current support guides and semantic notes; preserve historical strict behavior.

## 26.1028.213122 - 2026-10-28

- Add Pythonic labels/GOTO within active FOR loops, retained captured bounds,
  nested-loop exits and counter cleanup across return, suspension, stop and
  errors. Reject entry into new FOR or uncaptured USING scopes.
- Add opt-in callee group scopes for called programs and defining routines,
  preserving caller ownership, recursive grants and manual unlock/reacquisition.
  Keep root-only directive behavior as the default.
- Extend wildcard COPY_FILE/DELETE_FILE to configured plain PIP endpoints with
  finite snapshots, complete preflight and no implicit configuration or circular
  truncation. Keep socket/DAQ and wildcard rename boundaries explicit.
- Add 168 regressions, two standalone examples and two linked projects, current
  reports, support guides and semantic notes; retain historical strict restrictions.

## 26.1028.211044 - 2026-10-28

- Add opt-in stored-source TRANSLATE over explicit file backends, producing
  sibling Python and optional listings with source protection, overwrite/quota/
  alias guards and bounded artifact history. Never load or execute products;
  runtime-only imports remain independent of the compiler.
- Add nonrecursive star COPY_FILE/DELETE_FILE batches, portable destination
  templates, complete snapshot/preflight and backend-specific publication.
  Retain wildcard RENAME, PIP/socket/DAQ and native file boundaries.
- Add opt-in atomic root LOCKGROUP/NOLOCKGROUP acquisition, scheduler contention
  checks, retained pause ownership and terminal cleanup; callee directive scopes
  and native waits remain deferred.
- Add 149 regressions, three standalone examples and a linked directive-lock
  project. Update reports, public guides and remaining-support inventory:
  all 334 audited built-in names now have a registered Pythonic form, with
  overload and native behavior restrictions still explicit.

## 26.1028.202845 - 2026-10-28

- Preserve missing scalar leaves in Pythonic resource-free ARRAY, STRUCTURE,
  built-in record and JOINTPOS copies, private arguments and function results.
  Validate complete storage/schema and known contents before publishing outputs;
  retain scalar-read, geometry/kinematics/vision and internal strict guards.
- Add bounded PASSALL ASCII STRING fields and printable keyboard record
  delimiters, with explicit control-byte mappings, atomic output, retained pending
  prefixes, shared-pane arbitration and ordinary cooperative cleanup.
- Route COPY_FILE/DELETE_FILE/RENAME_FILE/FILE_LIST for explicit plain PIP names.
  Cross-backend copies use finite closed-file snapshots, configured capacities,
  ordinary quota/path checks and atomic destination replacement without ring loss.
- Add 160 regressions, three standalone examples and a linked partial-value
  project. Preserve historical strict cases and per-feature ledger versions;
  update current reports, README, support guides and semantic notes.

## 26.1028.200539 - 2026-10-28

- Enable cooperative FILE READ with captured destinations/formats. Add typed
  injected-keyboard line reads, editing/echo, buffered suffixes, multirecord
  transactions and cleanup; READ_KB keeps its existing masked-key contract.
- Add opted-in plain-pipe wait/snapshot and overflow attributes, staged text and
  binary reads, snapshot-aware cursor queries and explicit host feeding. Retain
  legacy behavior without attributes and require explicit standalone wait callbacks.
- Distinguish unfinished streaming text from complete invalid fields, including
  tokens, fixed widths, quoted strings and CR. Keep ordinary final-input defaults.
- Expand configured VT trays into supplied cell transforms with independent
  internal IDs, per-cell models/routing/allocation, portable sequence order and
  checked context persistence. Unconfigured trays retain their single-part tags.
- Add 177 regressions, three standalone CLI examples and an input pipeline
  project combining keyboard input, a delayed producer and a waiting pipe reader.
  Refresh README, reports and semantic notes; no native timing, motion or strict
  mode equivalence is claimed.

## 26.1028.194447 - 2026-10-28

- Add FILE_LIST formats 1 through 4 while retaining format 0 backend keys.
  Return stems, extensions, basenames or portable 40-column size records with
  blank timestamps. Validate complete pages before changing names/counts;
  capacity errors now preserve outputs instead of truncating format 0 names.
- Compose complete FTX form fragments through dictionary references, including
  explicit .tree inheritance, shared data/selection indices and root-owned
  attributes. A new tree now remains selectable when its predecessor is collapsed;
  nested groups retain the documented language prohibition.
- Route common and program-qualified wildcard ARRAY shapes in linked projects.
  Add project CLI --array-shape and normalized per-program metadata; preserve
  compiler rank/fixed-size/linkage checks and reject ambiguous/unused shapes.
- Add 101 regressions, two authored CLI examples and a linked ARRAY project.
  Refresh reports, README, support guides and semantic notes. All behavior is
  offline; strict mode, native widgets and controller acceptance remain future work.

## 26.1028.191850 - 2026-10-28

- Add nested and sibling GOTO entry into IF, WHILE, REPEAT and SELECT bodies.
  Direct transfers skip intervening statements and header dispatch, then follow
  the target suffix and normal loop back edges without fabricated initialization.
- Validate entry scope explicitly: retain FOR-body and routine boundaries,
  condition-action restrictions and a USING capture-prefix proof. Entering a
  new capture remains rejected even for identical selected storage.
- Add source/target block paths and entry classification to control-flow reports;
  retain ordinary type checks, budgets, errors, cleanup and pause/resume state.
- Add 54 regressions, two replayable CLI examples and a linked source project;
  refresh README, API/support guides and semantic ledger. Historical strict
  entry restrictions remain unchanged; no native/controller equivalence claim.

## 26.1028.184931 - 2026-10-28

- Enable the existing --help/--context/--state-out argument handling for every
  generated Pythonic script, including pure arithmetic and Cartesian geometry.
  Previously those programs ran a minimal entrypoint that ignored arguments.
- Restore explicit global inputs, preserve supplied banks and save successful
  state consistently; reject unknown flags and invalid context before execution.
- Add nine runtime-only CLI regressions, including saved-state replay, and update
  README and the VECTOR example commands. Legacy strict entrypoints are unchanged.

## 26.1028.183029 - 2026-10-28

- Add pose:VECTOR affine point transforms for POSITION, XYZWPR, XYZWPREXT and
  model-backed JOINTPOS frames, with exact VECTOR results and independent storage.
- Support result fields, routine arguments/returns, named types and array elements;
  retain one-time left-to-right capture, joint conversion records, failure/target
  ordering, ordinary aliases, protected orientations and FOR-effect checks.
- Preserve complete finite pose/vector inputs, proper matrix/CONFIG/external
  metadata validation and existing frame math. Document the explicit point
  interpretation and direction-only subtraction form; VECTOR left frames and
  INV/FRAME vector arguments remain rejected.
- Add 53 regressions, two CLI examples and a linked source project. Refresh README,
  support guides and report policies; native/controller equivalence remains unverified.

## 26.1028.181511 - 2026-10-28

- Add mixed PBR_ALLTYPE backup/clear and manifest-based restore over explicit
  TP and KAREL variable stores, including variable-only ALLTYPE batches.
- Traverse combined supplied dependency graphs with cycles/shared nodes, macro
  exclusions and bounded bridge-edge persistence into fresh contexts.
- Write a versioned .PB manifest with member SHA-256 hashes; preflight complete
  TP/VR/file/quota batches and reject stale, missing or incompatible members
  before committing. Retain existing TP records and overwrite compatible VR data.
- Preserve ordinary aliases, unlisted roots and resources, active-task/timer/
  output guards, protection overlays and direct/transitive/handler FOR checks.
- Add 50 regressions, two replayable CLI examples and a linked source project;
  update README, support guides and semantic policies. Native binaries, physical
  storage, code unloading and strict equivalence remain outside this model.

## 26.1028.175803 - 2026-10-28

- Add twelve VT queue calls over explicit ordered lines/areas: put, duplicate
  detection, get/acknowledge, clear, time/flow estimates, PATH read/write/delete,
  flags and deterministic weighted routing with per-model profiles and bypass.
- Preserve distinct caller work IDs and internal PATH indexes; copy adjusted
  results downstream, reserve allocated registers, support cooperative waits
  and release pending ownership on stop/abort/budget failure.
- Capture typed nullable selectors and sparse input arrays only for declared
  optional parameters. Preserve unknown fields and preallocated PATH tails;
  retain generic initialization, alias and active-FOR guards.
- Persist checked clocks, profiles, nullable results and receipts; reject active
  saves. Document portable statuses, tray/geometry/flow limits and the manual's
  conflicting WRITE_PQ example argument order.
- Add 60 regressions, two CLI examples and a linked VT project. Refresh README
  and support audit: 333 registered inventory names, one unregistered native
  TRANSLATE call; registration does not imply every native form or behavior.

## 26.1028.172050 - 2026-10-28

- Add twelve legacy vision/tracking calls: cooperative queue get/init/reallocate,
  process start/stop flags, explicit area/line/tray IDs and VT_GET_FOUND.
- Preserve allocation receipts and logical encoder triggers, timed arrivals,
  per-queue clocks and pending-register ownership; pause/resume retains the
  request and stop/abort/budget failures release reservations without replay.
- Add supplied point-cloud map acquisition/clearing and a bounded portable
  iRConnect outbox with optional supplied images; no hardware/network effects.
- Keep VT_GET_FOUND's exact 4/10-element outputs and shared result cursor;
  retain native library-wrapper lowering only for the three documented IRVU calls.
- Add 51 regressions, two CLI examples and a linked tracking project. Update
  README/support guides: 321 registered built-in names, 13 remaining.

## 26.1028.165003 - 2026-10-28

- Add ten vision calls for explicit captures/image registers, image-bound finds,
  reader output, view-line PATHs, camera queries, calibration replies and
  headless display/LED state. All 27 modern inventory vision names now have
  registered offline forms; undocumented overloads and native effects stay open.
- Encode supplied grayscale/RGB pixels as PNG/BMP through bounded file backends,
  with busy/quota/path checks and atomic rooted-file replacement.
- Retain once-consumed capture/calibration replies, image ownership/coverage,
  reader/line batches and logical state in context JSON; stage outputs before
  consumption and preserve files/lengths/PATHs on failure.
- Document the three-argument Pythonic V_SAVE_IMREG form and reject unexplained
  compression/iPC overloads. Keep image processing and physical I/O separate.
- Add 58 regressions, two CLI examples and a linked vision-I/O project; update
  README/support guides: 309 registered built-in names, 25 remaining.

## 26.1028.163240 - 2026-10-28

- Let generated CLI numeric-register calls use the explicit numeric bank in
  --context. Keep --registers as an override and share the chosen bank with
  vision/extended services and saved state; absent banks still fail explicitly.
- Add six isolated CLI regressions for combined contexts, READ, overrides,
  shared vision results and saved numeric state.

## 26.1028.162050 - 2026-10-28

- Add 19 offline iRVision calls for supplied completed runs, vision-register
  reads/transfers, result cursors, inspection flags, counts and reference data.
- Add checked sparse XYZWPR/REAL array outputs, detached register values,
  finite X/Y adjustments and calling-root position-register group selection.
- Add CSAPI editing/reset/save, captured test parameters and explicit one-shot
  override bindings; persist unconsumed batches, cursors, edits and history.
- Recognize exact IRVUTILVR wrapper declarations without native library loading;
  retain output/alias/FOR guards and document the NUMSET direction discrepancy.
- Add 55 regressions, two CLI examples and a linked vision project. Update
  README/support guides: 299 registered built-in names, 35 remaining.

## 26.1028.154448 - 2026-10-28

- Add MOTION_CTL and CNCL_STP_MTN over explicit calling-root group ownership,
  plus SET_PERCH with detached checked six-axis references/tolerances.
- Add cooperative scripted RESET with independent acknowledgement/fault results,
  pending-state guards, once-only response consumption and interruption cleanup.
- Add configured MIXBG_RUN/MIXBG_STOP slots for attached cooperative tasks,
  preserving renamed identities and honoring pause masks and terminal states.
- Add explicit OPIN/OPOUT/TPIN/TPOUT Boolean banks, including address zero in
  indirect I/O, metadata, form/table fields and reset fault observations.
- Add 55 regressions, two CLI examples and a linked background project; update
  README/support guides: 280 registered built-in names, 54 remaining.

## 26.1028.151355 - 2026-10-28

- Add DISCTRL_FORM over supplied .form/.endform FTX source, typed scalar/global
  paths and explicit port banks, with USER2 selection and headless windows.
- Add editable/display/selectable items, numeric bounds/retry, strings, program
  names, Boolean/port/simulation and function/subwindow/variable enum choices.
- Add help/function metadata, choice overlays, paging, continuous default items,
  nonnested tree groups, live repainting and robust session/interruption cleanup.
- Accept native enum bell terminators; keep ordinary dictionary rendering guarded
  against form metadata. Add 50 regressions, two CLI examples and a linked project.
- Update README/support guides: 274 registered inventory names, 60 remaining;
  all screen/window/keyboard/dictionary inventory names now have registered forms.

## 26.1028.144536 - 2026-10-28

- Add DISCTRL_LIST resident paging and all three table calls: INIT_TBL, ACT_TBL
  and DISCTRL_TBL, with explicit headless windows and injected key events.
- Add portable COL_DESC_T/XWORK_T records, static array and typed port cells,
  numeric/string/enum/Boolean editing, range/format checks and change grids.
- Add session ownership, cancellation, save guards, cursor preservation and
  conservative indirect-write checks through active FOR scopes.
- Add 56 focused regressions, two CLI examples and a linked project; refresh
  the README and audit 273 registered built-in names with 61 remaining.

## 26.1028.140226 - 2026-10-28

- Add READ_KB, PUSH_KEY_RD and POP_KEY_RD with explicit key events, pane capture,
  masked input, bounded editing/history, cooperative timeouts and suspension tokens.
- Add KB:TPKB and combined WD:name/TPKB text FILEs, echo/no-echo, PASSALL intent,
  ordinary window output, cursor forwarding and explicit lifetime/save guards.
- Add DISCTRL_ALPH plus dictionary-backed DISCTRL_SBMN/DISCTRL_PLMN navigation;
  preserve typed output/counter guards and persist only unconsumed input/history.
- Add 67 regressions, two CLI examples and a linked project; update README and
  audit 269 registered built-in names with 65 remaining.

## 26.1028.133057 - 2026-10-28

- Add all twelve dynamic display initiation/cancellation calls for static scalar
  variables, enum labels and supplied BOOLEAN/INTEGER ports.
- Capture typed read-only storage once; support unknown-value markers, live labels,
  bounded formatting, field padding/clipping and deterministic checkpoint intervals.
- Paint fields atomically without moving FILE cursors; cancel by storage identity,
  restore overlapping survivors and retain cleanup at exhausted display limits.
- Reject active-binding context saves; retain closed logical clock/settings and
  visual state. Add 62 regressions, two CLI examples and a linked project.
- Refresh README/support inventory: 263 registered built-in names, 71 remaining.

## 26.1026.195318 - 2026-10-26

- Add all seven dictionary calls over supplied ASCII text catalogs and persisted
  per-language loaded snapshots, with explicit CHECK_DICT signature compatibility.
- Parse numbered/named elements, automatic numbering, comments, escapes and bounded
  nesting; format static scalar variable paths with widths, precision and reordering.
- Add ARRAY reads with last-row/truncation statuses and atomic window writes with
  cursor positioning, clearing and control tokens; preserve failed-request state.
- Add 63 regressions, two CLI examples and a linked project; refresh README and
  audit 251 registered built-in names with 83 remaining.

## 26.1026.193506 - 2026-10-26

- Add ten offline pendant calls for links, menus, language labels, screens,
  windows, attachments, activation and cursor positioning.
- Add WD:name text FILE output with common/per-handle cursors, wrapping, scrolling,
  screen composition and explicit closed-handle context persistence.
- Support STRING-valued predefined language constants while retaining typed
  argument/output guards and portable status/ID boundaries.
- Add 61 regressions, two CLI examples and a linked project; audit 244 registered
  built-in names with 90 remaining. No GUI or live-controller operations are added.

## 26.1026.185812 - 2026-10-26

- Add CHECK_STACK, SET_DEBUG and SET_DB_EVENT with explicit logical stack costs,
  low-water tracking, per-task enable flags and bounded portable event records.
- Add scripted KCL/KCL_NO_WAIT/KCL_STATUS acceptance and completion, shared busy
  handling, scheduler/standalone waits and terminal-only context persistence.
- Retain accepted commands after caller stop/failure without resubmission; keep
  pending state reviewable and require collection before saving context.
- Add 58 regressions, two CLI examples and one linked project; refresh runtime-only
  distribution checks and audit 234 registered built-in names with 100 remaining.

## 26.1026.182837 - 2026-10-26

- Add PATHDATA as a PATHHEADER compatibility spelling, clause order/whitespace
  flexibility and physical newline reflow with duplicate and dangling-comma guards.
- Add documented DISP_DAT_T data and explicit portable STD_PTH_NODE aliases across
  declarations, arrays, structures, routine interfaces and dynamic CREATE_VAR.
- Canonicalize explicit default nodes to the existing implicit PATH schema; retain
  typed storage, SHORT limits, POSITION protection and context/VR persistence.
- Record clause/type-use provenance and add 51 regressions, two standalone CLI
  examples and a linked project with typed PATH and predefined-record interfaces.

## 26.1026.180251 - 2026-10-26

- Add indexed and grouped USING storage selectors, including index calls and
  supported built-in VECTOR, CONFIG, XYZWPR, XYZWPREXT and POSITION records.
- Capture references once left-to-right at block entry; retain selections across
  index changes, internal jumps and pause/resume, with fresh captures on reentry.
- Freeze enclosing references in condition callbacks; retain source-root effects,
  exact output interfaces and POSITION/CONFIG/active-counter protection.
- Add 51 focused regressions, two standalone CLI examples and one linked project
  combining external types, shared variables and indexed routine parameters.

## 26.1026.174213 - 2026-10-26

- Add complete TYPE name FROM owner definitions for supported aliases, structures,
  arrays and resource schemas; preserve declared owner and physical source metadata.
- Validate linked-project type layouts before global allocation; support self-owned
  declarations and transitive source reexports with missing-owner/schema/cycle errors.
- Retain exact STRING capacities, array identities, nested field order and existing
  variable/routine interface checks without changing persisted storage schemas.
- Add 40 regressions, one standalone CLI example and one linked source project;
  update the README, support guide and remaining-feature inventory.

## 26.1026.170848 - 2026-10-26

- Add portable VR SAVE/LOAD/CLEAR for owned KAREL globals and explicit roots,
  retaining partial/unknown typed data, aggregate aliases and creation metadata.
- Add variable-only recursive backup/clear/restore using archived dependency
  graphs, complete batch preflight and the existing memory/device file policies.
- Add SAVE_DRAM snapshots with persisted offline flash state and explicit guarded
  host restoration; keep native power-up behavior and mixed TP/VR batches deferred.
- Guard status/root overlaps, sparse bindings, callback storage, foreign active
  tasks, timers and metadata; preserve FOR write proof for known TP forms.
- Add 52 regressions and two authored CLI examples; update guides and audit
  228 registered built-in names with 106 still unregistered.

## 26.1026.162834 - 2026-10-26

- Add %INCLUDE expansion for declaration, routine, executable and whole-program
  fragments, with explicit text libraries, ordered directories and device maps.
- Support three nested files, case-insensitive relative lookup, cycle detection,
  bounded snapshots/expansions and source-preserving UTF-8/BOM file reads.
- Record original/expanded/dependency hashes, compact physical source spans and
  enriched source maps; remap compiler/lexer errors to included source locations.
- Protect CLI outputs and project state/trace files from replacing any input or
  hard-link alias; exclude referenced fragments from linked program entries.
- Add 41 regressions, one CLI example and one linked project. Keep routine-local
  TYPE prohibited under documented KAREL rules; built-in counts stay 227/107.

## 26.1026.155345 - 2026-10-26

- Add TP forms of SAVE/LOAD/CLEAR and PROG_BACKUP/PROG_RESTORE/PROG_CLEAR
  using versioned portable archives with positions, headers and TP-local registers.
- Add explicit bounded dependency graphs with cycle-safe recursive traversal,
  kind filters, macro exclusion and detached COPY_TPE graph metadata.
- Preflight full batches over memory/virtual-device files, including shared quota,
  retained garbage, unchanged backups and free-space hints; retain failed batches.
- Guard selected/open/bound/protected/source targets, preserve existing restore
  records and refresh explicit load flags; native PC/VR/IO forms stay unsupported.
- Add 43 regressions and two CLI examples; update guides and audit 227 registered
  built-in names with 107 still unregistered.

## 26.1026.153257 - 2026-10-26

- Add RMCN_ALERT/RMCN_SEND and QUEUE_ATTACH over a bounded offline message
  outbox with explicit defaults, type catalog, priorities and deferred files.
- Validate XML and publication limits before deleting the source XML; preflight
  whole attachment collections, retain current MD files and preserve failures.
- Support exact in-memory/device file backends with busy/access/quota accounting;
  provide detached host collection and explicit opaque ZDT publication.
- Persist checked alerts, XML/opaque bytes, pending selections and monotonic
  sequences; keep SET_VAR behavior and source/counter/reference checks explicit.
- Add 40 regressions and two authored CLI examples; update guides and audit
  221 registered built-in names with 113 still unregistered.

## 26.1026.151124 - 2026-10-26

- Add MSG_CONNECT/MSG_DISCO/MSG_PING over configured offline endpoints, with
  distinct RX/TX buffers, scripted ping results and socket-tag mount forms.
- Route ordinary text/binary FILE I/O to connected endpoints; preserve input
  on failed reads, enforce limits and support explicit host feed/output draining.
- Add PIPE_CONFIG and circular PIP histories with concurrent readers/writers,
  sector bounds, truncation/append modes and retained formatting/CMOS metadata.
- Persist checked socket/pipe state while refusing live FILE saves; protect
  separate plain/DAQ namespaces and preserve existing source/counter guards.
- Add 40 focused regressions and two authored CLI examples; update guides and
  audit 218 registered built-in names with 116 still unregistered.

## 26.1026.143509 - 2026-10-26

- Add ADD_INTPC/ADD_REALPC/ADD_STRINGPC/ADD_BYNAMEPC with documented big-endian
  typed BYTE buffers, explicit string/end markers and atomic cursor updates.
- Add SEND_DATAPC/SEND_EVENTPC over a bounded offline PcExchange outbox, with
  checked typed-prefix sends, fully initialized raw payloads and event bounds.
- Capture send buffers before later output-selector effects; preserve read-only
  effect analysis, reference/counter guards, unknown unused tails and named types.
- Persist checked outbox messages and sequence history; expose detached snapshots
  and host draining without network access, callbacks or automatic delivery.
- Add 40 focused regressions and two authored CLI examples; update guides and
  audit 214 registered built-in names with 120 still unregistered.

## 26.1026.140703 - 2026-10-26

- Add all six DAQ calls over explicit bounded typed acquisition pipes, with
  reference-counted start/stop, forced shutdown, status flags and ring overflow.
- Add binary read-only PIP FILEs, independent consuming stream cursors, frozen
  snapshot views and complete-record reclamation when lagging readers close.
- Stream whole batches through explicit memory, virtual-device or rooted disk
  backends; preserve pipe state on failure and flush partial batches at final stop.
- Persist validated pipe schemas, lifecycle and pending bytes; reject live-reader
  saves, retain current module scope and expose logical FILE names in snapshots.
- Add 40 focused regressions and two authored CLI examples; update guides and
  audit 208 registered built-in names with 126 still unregistered.

## 26.1026.133752 - 2026-10-26

- Add CALL_PROG/CALL_PROGLIN for attached cooperative KAREL main bodies, with
  isolated cursors/stacks, shared globals and caller-root budgets and lifecycle.
- Preserve nested pauses, runtime-selected targets, combined depth guards,
  entry hints, task inspection and linked-routine/caller-parameter scope.
- Add explicit GroupLocks for LOCK_GROUP/UNLOCK_GROUP, including partial
  acquisition, contention, busy labels, task identity and terminal cleanup.
- Persist configured groups/motion labels while refusing live-ownership saves;
  keep compiled/TP execution, native locks and automatic source locks excluded.
- Add 40 focused regressions, two CLI examples and a linked project; update
  documentation and audit 202 registered built-ins with 132 still unregistered.

## 26.1026.131437 - 2026-10-26

- Add CREATE_VAR over bounded portable data and attached user types, with typed
  context persistence and retained group/DRAM/CMOS intent metadata.
- Add RENAME_VAR and RENAME_VARS for explicit variable roots/namespaces; preserve
  references and caches while protecting compiled identities and system bindings.
- Add BYNAME as a typed routine alias, including linked calls and pause/resume;
  retain exact named types, disjoint entry outputs and indirect FOR/effect guards.
- Normalize current-program variable cache keys, reject duplicate saved bindings,
  add 42 focused regressions and two authored CLI examples; update support docs
  and audit 198 registered built-in names with 136 still unregistered.

## 26.1026.124620 - 2026-10-26

- Add all six device/storage calls over an explicit virtual DeviceFiles backend,
  with mount state, closed-file guards, labels and supplied device information.
- Share ordinary FILE operations with per-volume byte quotas and retained obsolete
  storage; purge reclaims garbage without deleting live files, including MF batches.
- Preflight writes/copies/moves and complete MOVE_FILE batch growth before mutation;
  preserve all format targets on budget failure or newly opened FILE guards.
- Persist virtual contents, mount/read-only flags, labels and reclamation counters
  in device_files JSON; management never targets host drives or DirectoryFiles.
- Add 30 focused regressions and two authored CLI examples; refresh guides and
  audit 194 registered built-in names with 140 still unregistered.

## 26.1026.121648 - 2026-10-26

- Add all five XML input calls with checked registered-tag events, attribute and
  text chunks, continuations, scan limits and atomic flat structure field updates.
- Bound ASCII XML parsing over explicit text RO FILE backends; reject DTD/entity
  declarations, malformed data, output aliases and indirect FOR-counter writes.
- Preserve live scanning across pause, release it on close/reopen and retain
  complete output/cursor state for capacity retries; omit scanners from JSON.
- Add GET_PORT_ATR/SET_PORT_ATR with an explicit persisted SerialPorts bank,
  seven checked attributes and portable constants, independent of physical I/O.
- Add 39 focused regressions, two authored examples and runtime-only dependency
  coverage; refresh guides and audit 188 registered built-in names, 146 remaining.

## 26.1024.153206 - 2026-10-24

- Accept nine additional checked source directives; apply DEFGROUP to caller-root
  defaults and CRTDEVICE labels to omitted-file READ/WRITE requests.
- Expose detached source settings for storage, locks, periodic-delay and stack
  intent without adding native side effects or clearing restored values.
- Make ordinary position-register calls honor the calling root's default group
  when omitted, consistently with TP register and robot-context operations.
- Add portable NODE_SIZE and staged INTSCT_VL_PL over documented structural PATH
  data, preserving model IDs, projected polarity and explicit frame/group metadata.
- Add 35 regressions and two authored CLI examples; refresh guides and the gap
  inventory to 181 registered built-in names with 153 still unregistered.

## 26.1024.151618 - 2026-10-24

- Add all twelve TP caller-local numeric, string, grouped position, frame and
  representation APIs with explicit KAREL-root to TP-program bindings.
- Keep local banks independent from global registers, program points and call
  parameters; preserve linked-root scope, external axes and exact joint widths.
- Persist limits, bindings and typed values; deep-copy local banks with programs
  while retaining caller associations and values across task lifecycle changes.
- Apply foreign TP handle rejection, selected numeric outputs, complete string
  destination checks, optional groups and retained failure/counter protections.
- Add an all-call CLI example and 32 regressions, refresh public guides and audit
  the inventory to 179 registered built-in names with 155 still unregistered.

## 26.1024.144946 - 2026-10-24

- Add 17 TP program management, position, frame/type and comment calls over an
  explicit shared TeachPrograms logical store, with bounded typed JSON data.
- Apply root-owned access/reject handles, independent copies, selected/open
  guards, retained pause state and automatic cleanup on terminal execution.
- Preserve grouped Cartesian/joint data, external axes, frame/tool identifiers,
  comment capacity rules and one-based opaque instruction deletion.
- Integrate program listing, load status and four writable header fields; retain
  native TP formats, execution, embedded registers and motion as explicit gaps.
- Add an authored all-call CLI example, saved-context replay, runtime-only
  dependency checks and access/lifecycle/metadata/serialization regressions.

## 26.1024.141821 - 2026-10-24

- Add SET_TSK_ATTR with nine checked task settings and seven source directives
  for priority, slices, request masks and readable capability flags.
- Apply stable priority ordering and bounded checkpoint budgets in cooperative
  rounds while retaining virtual time, task IDs, rename state and step limits.
- Distinguish command/error/explicit pendant and shift requests; retain bare
  PAUSE/ABORT, runtime failures, pending-request and error-history behavior.
- Add bounded caller-rooted source tracing, detached host observations and atomic
  project CLI --trace-out export, including partial traces on failures.
- Add a linked policy example and scheduling, mask, source, tracing and CLI
  regressions; refresh the remaining-support inventory and current guides.

## 26.1024.135943 - 2026-10-24

- Publish a comprehensive remaining-support inventory, including every audited
  unimplemented built-in and partial language/service boundaries.
- Add SET_TSK_NAME and host rename APIs with stable task numbers, caller-rooted
  self lookup, collision preflight and preserved module/linkage identity.
- Retain paused/waiting execution, deadlines, metadata and failure records across
  scheduler renames, including changes during the current cooperative round.
- Add an authored CLI project and registry, linked-call, scheduler, argument-order
  and counter-protection regressions.

## 26.1024.133929 - 2026-10-24

- Add CHECK_EPOS with complete Cartesian operands, explicit frame/tool values,
  optional groups and portable success/failure statuses over supplied models.
- Provide a synchronous check_position callback and check_pose host API; loaded
  DH contexts restore framed reachability with limits and external-axis checks.
- Preserve source operands, current robot state, group selection, status outputs
  and active FOR counters; reject asynchronous or non-Boolean adapter results.
- Add an authored grouped/external-axis CLI example and focused mathematical,
  callback, persistence, source-order and linked-root regressions.

## 26.1023.152301 - 2026-10-23

- Add ERR_DATA queries over shared offline error history: oldest/next traversal,
  latest-record MAXINT selector, output preflight and retained notification cursors.
- Preserve optional error/cause text and packed timestamps in JSON history;
  source error posting samples an explicitly supplied calendar when available.
- Keep ordinary MAXINT storage guarded, reject sequence exhaustion before append,
  and document missing messages, unknown time and native log-timing boundaries.
- Add authored CLI execution, handler, persistence and output-protection checks.

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
