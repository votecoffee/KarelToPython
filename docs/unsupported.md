# Remaining Pythonic support

Audited on 2026-11-04 against the 465-heading, multi-edition KAREL feature
inventory, the programmer reference and the implemented parser/runtime. This is
a product backlog, not a controller compatibility certificate. The inventory
contains statements, actions, clauses, types and directives as well as calls;
one heading does not equal one executable feature or one percentage of coverage.

The inventory has 334 distinct built-in names after merging repeated headings.
Currently, all 334 have a registered Pythonic translation form.
Registration means a supported form exists; it does not mean every overload,
option, type, controller release or native behavior is implemented. Calls outside
this reference set can also be rejected. There are no unregistered names in this
audited set. The [support guide](language-support.md) describes accepted forms.
Some exclusions, such as whole-array UNINIT, retain documented language rules;
they are boundaries rather than promises to accept every such source form later.

Scalar PATH/QUEUE_TYPE assignment, private arguments and internal/compiled linked
results now follow the [scalar collection policy](scalar-collection-values.md).
[Queue entry I/O](queue-io.md) now adds initialized scalar/bank READ/WRITE with
existing counts and IDs, detached input buffers and ordinary scalar transports.
Exact schemas and logical bounds remain required; FILE copying, generic queue
value helpers, resource fields and native collection layouts remain unavailable.
[External collection results](external-collection-results.md) now add checked
callback values and typed JSON, with optional fixed results from an explicit CLI
file. They supply no executable libraries, inferred function logic or native ABI.

[Explicit external data](external-values.md) now adds typed ordinary callback
results plus CLI fixed values, explicit no-op procedures and exact typed argument
cases. [Explicit response outputs](external-outputs.md) now update selected
ordinary data arguments after whole-response validation.
[Logical responses](external-logical-values.md) now also cover PATH/QUEUE_TYPE
results, argument cases and scalar/bank outputs. Algorithmic behavior and FILE
effects still require supplied source or Python callbacks; bindings are
not inferred or persisted.

[Forward constants](forward-constants.md) now resolve acyclic chains across module
CONST sections and each routine's own CONST sections before dependent schemas.
Unknown names, cycles, calls and runtime reads remain errors. Local constants do
not enter global type declarations, routine interfaces or caller/sibling scopes.

## Language and source forms

- Unknown directives and binary environments. %INCLUDE now expands
  [explicitly supplied source fragments](includes.md), with three nested files,
  selected directory/device lookup and original-file diagnostics. The four original metadata directives,
  seven [task policies](task-attributes.md) and nine additional
  [source policies](source-directives.md#additional-source-policies) are accepted.
  DEFGROUP selects offline defaults and CRTDEVICE labels I/O requests; native
  storage, periodic delay, stack allocation and real device routing are not applied.
  An opted-in GroupLocks bank applies root LOCKGROUP/NOLOCKGROUP policies;
  a second opt-in enables [callee scopes](scoped-group-locks.md), while native
  waits remain unavailable. Include search does not discover native support installations.
- Native motion execution, trajectories, feedback updates and controller queues. [Offline motion requests](motion-requests.md) now translate all
  seven basic MOVE forms, VIA, direct PATH-node destinations, forward PATH ranges,
  hand state and logical ATTACH/RELEASE. They require explicit capture-only opt-in
  or immediate scripted responses plus logical ownership. [Logical controls](motion-controls.md)
  now support HOLD/UNHOLD/CANCEL, global handler actions and 21 per-group WITH
  settings, including [termination/orientation choices](extended-motion-settings.md)
  and [deceleration/acceleration intent](motion-deceleration-settings.md). [Local Boolean WHEN/UNTIL clauses and finite supplied response delays](motion-handlers.md)
  now use synchronous scopes with pause/resume and cleanup. [Pending NOWAIT jobs](nowait-motion.md)
  now use supplied delays/schedules and task clocks, including scheduler progress
  while the owner waits. [NOWAIT local clauses](nowait-local-clauses.md) now scan
  at owner checkpoints with exact live defining-frame captures and supplied
  temporal observation windows. [Bounded NOWAIT FIFOs](queued-motion.md)
  now use explicit queue_limit and supplied response durations; [blocking MOVE
  waiters](synchronous-motion-queues.md) now wait on their own admitted FIFO result.
  [Queued NOWAIT handlers](queued-motion-clauses.md) now retain exact live captures
  until promotion and cancel expired defining frames. [Blocking local clauses](blocking-motion-clauses.md)
  now retain the calling continuation and target supplied temporal breakpoints. Callbacks after
  defining-frame return, old direct-invoke queueing, inferred
  node arrivals, unresolved `$REF_POS`,
  cross-group execution, interpolation execution and native synchronization remain unsupported.
  [Cross-group WITH metadata](cross-group-settings.md) now has an explicit opt-in
  for configured groups owned by the calling root, without changing other groups.
  [Ten additional WITH options](motion-options.md) now retain acceleration, accuracy,
  signed continuous-axis speed, timing and Boolean policy intent as checked metadata.
  They do not apply those options to a trajectory or the supplied offline timeline.
  [AT NODE and TIME BEFORE/AFTER](motion-timeline.md) now require a complete supplied
  arrival schedule; global temporal predicates and physical arrival discovery remain unavailable.
  [CANCEL FILE](file-cancellation.md) now interrupts explicit cooperative typed reads
  and [READ_KB editors](read-kb-cancellation.md);
  [predefined/default FILE bindings](predefined-files.md) now use supplied offline
  endpoints; callback cancellation and native pending writes remain unavailable.
  `PURGE CONDITION` is supported; bare PURGE remains rejected. `IN GROUP[n]` does not add arbitrary native `IN` clauses.
  [VAR IN CMOS/DRAM](source-forms-and-predicates.md) now records per-declaration
  intent; native storage allocation and automatic retention remain unavailable.
- Handler actions involving native motion execution or native pending WRITE cancellation;
  native path-node arrival discovery. Checkpoint predicates, events, port
  edges, semaphores, errors and lifecycle notifications have offline models.
  TIME-style behavior uses connected timers and comparisons; motion timing,
  asynchronous native interrupts and physical node-arrival scans are unavailable.
- Transfers across program/routine bodies and entry into an uncaptured USING or
  unstarted FOR scope. [FOR jumps](for-jumps.md) now support same-loop labels,
  nested active-loop transfers and exits with counter cleanup under an explicit
  Pythonic extension. [Nested/sibling label transfers](nested-jumps.md)
  now support IF/WHILE/REPEAT/SELECT targets with normal loop continuations.
  [Acyclic forward types](forward-types.md) now resolve across aliases, aggregate
  components, PATH layouts and routine interfaces; self/cyclic layouts and unknown
  dependencies remain blocked. Full [external FROM type declarations](external-types.md)
  now use supplied source layouts and checked project ownership chains; missing
  definitions, cyclic ownership and native binary type environments remain blocked.
  Routine-local TYPE declarations
  remain prohibited by the KAREL language, rather than a planned extension.
- Whole ARRAY/FILE/QUEUE_TYPE/JOINTPOS and headerless PATH USING selectors, plus
  dynamic caller scope. [Explicit PATH headers](path-header-using.md) now support
  captured named/indexed storage and private computed results, with existing
  lexical, retained-handler, counter and timer checks.
  [Computed record selectors](computed-using.md) now capture checked private values;
  [private INTEGER counters](private-using-counters.md) now use internal lexical
  whole-root identities, including [checked narrow counters](narrow-for.md).
  Retained writable aliases remain blocked for counters. [Private connected
  timers](private-using-timers.md) now retain ordinary INTEGER leaves across
  lexical exit and pause, with whole-root counter guards and terminal cleanup.
  [Routine-local timers](routine-local-timers.md) now accept fresh declared
  INTEGER leaves with exact-frame cleanup and pause retention. [Borrowed formal
  timers](formal-timers.md) now use callee-frame ownership and shared-context
  duplicate/alias checks. [Helper timer control](timer-control.md) now releases
  exact existing claims owned by the same task across active frames and linked
  states. Persistent borrowed connections after return, cross-task control and
  inferred native alias ownership remain unavailable. [Reference FOR counters](reference-for-counters.md)
  now capture writable INTEGER fields/elements once. Aggregate-root writes/reuse,
  CONFIG/FILE/queue roots, imported or borrowed PATH roots, nonlocal parameterized
  roots and unproven external calls over global aggregate counters remain blocked.
  [Owned PATH counters](path-for-counters.md) now cover header/node fields and
  bank elements with complete-root write and retained-alias checks. [Captured USING selectors](using-selectors.md)
  now accept indexed/grouped record storage and built-in records; calls inside
  indexes use the one-time entry capture policy. [Scalar SELECT](scalar-select.md)
  now accepts finite numeric, BOOLEAN and ASCII STRING categories, with
  [dynamic scalar CASE expressions](dynamic-select.md) evaluated eagerly once
  after selector capture; mixed categories and aggregate/resource selectors remain blocked. A miss without
  ELSE fails. Recursion is bounded at 64 calls.
- Unicode/multilingual source, native graphic characters, multiline literals,
  backslash string escapes, token-splicing continuations and arbitrary native
  preprocessor/compiler extensions.

## Types, expressions and interfaces

[Explicit robot system transfers](system-variable-transfers.md) now add bounded
GET_VAR/SET_VAR row, location/CONFIG, extended-axis and selection operations.
They preserve existing binding precedence and publish checked offline values;
live system aliases and native discovery remain excluded.

[Offline frame/tool writes](system-pose-writes.md) now accept whole Cartesian
poses and staged location/configuration edits, including retained external axes.
[Active selection IDs](frame-tool-selection.md) now support checked source reads
and assignments using supplied rows. Writable aliases, direct orientation-column
writes, automatic joint conversion, native special-ID interpretation and
native/controller writes remain excluded.

[Root PATH READ/WRITE](path-io-and-file-initialization.md) now expands supplied
header/node data through scalar transports. Automatic node allocation, native
PATH framing, empty headerless input and formatted empty output remain excluded.
[Whole POSITION input](position-input.md) now spans data containers and PATH
components with complete-batch pose validation and bounded rounding normalization. FILE UNINIT uses the explicit descriptor open-state convention.

- Native compact association layouts, automatic motion-environment recording,
  and the obsolete `STD_PTH_NODE.GROUP_DATA` / `COMMON_DATA` fields.
  [COMMON_ASSOC/GROUP_ASSOC data](association-records.md) now support checked
  fields, ordinary containers/interfaces, I/O, inspection and logical persistence.
  Custom NODEDATA/PATHHEADER structures can embed those records; default and
  explicit STD_PTH_NODE retain the compatible NODE_POS-only schema.
  [Predefined structures](path-declarations.md) also expose DISP_DAT_T data.
  Native motion-option application and display/recording behavior remain outside
  those data records.
  The separate [headless display model](pendant-display.md) supports character
  windows and screen composition. [List/table controls](table-controls.md) now use
  DISP_DAT_T resident-list metadata and portable COL_DESC_T/XWORK_T records; native
  memory layouts and widget rendering remain unverified.
- Dynamically resized/ragged arrays, unknown runtime wildcard dimensions, ranks
  above three and aggregates exceeding the 32767-leaf prototype bound. Global
  wildcard declarations require translation-time shapes; no native VR auto-discovery.
  [Explicit saved JSON schemas](array-context.md) now supply dimensions through
  API/CLI opt-in, with exact source types and separate execution-state loading.
  Linked projects now route common or [program-qualified shapes](project-array-shapes.md)
  to the declared wildcard storage, including differing module-local dimensions.
  [Complete chained indexes](chained-array-indexes.md) now use the existing comma
  access contract. [Prefix values](array-prefix-values.md) now copy incomplete
  flat rows/planes independently. [Statement prefix targets](array-prefix-targets.md)
  now assign and READ original cells with retained aliases. Explicit
  [live BYNAME prefixes](array-prefix-references.md) now borrow data rows/planes
  across routines, linked calls, rename and pause. [Resource prefixes](resource-prefix-references.md)
  now borrow FILE/PATH/QUEUE_TYPE rows and planes explicitly through BYNAME.
  [Typed data service prefixes](service-array-prefixes.md) now capture writable
  rows/planes for explicit ARRAY interfaces. Generic ANY/scalar output prefixes,
  ordinary resource-prefix values and routine-local/system discovery remain excluded.
  [GET_VAR/SET_VAR prefix data transfers](prefix-variable-transfers.md) now support
  selected named paths, SET source values and captured GET data outputs.
  [Logical collection ARRAY transfers](collection-array-transfers.md) now extend
  GET_VAR/SET_VAR to exact whole PATH/queue banks and selected rows/planes; FILE
  storage remains excluded; ordinary logical collection ARRAY values use the
  separate [source-copy policy](collection-source-values.md).
- BYTE unknown contents cannot be queried with UNINIT; SHORT 32767 remains the
  uninitialized sentinel. [Scalar BYTE/SHORT](scalar-narrow.md) now support
  variables, aliases and typed interfaces; numeric narrowing makes checked private
  values. [Narrow FOR counters](narrow-for.md) now enforce initialized BYTE/SHORT
  domains and type-specific cleanup; [dynamic narrow creation](dynamic-narrow.md)
  now supports direct BYTE/SHORT and supplied aliases with existing allocation guards.
- FILE resource output, incomplete/unknown aggregate output, per-field aggregate-format
  mapping syntax and native packed layouts remain unavailable.
  [Uniform aggregate formats](aggregate-formats.md) now apply scalar format lists
  to every expanded member of whole-data READ/WRITE, with capture before formats.
  [Whole-data WRITE](aggregate-output.md) now supports complete data, including
  readable POSITION columns, without changing orientation-write restrictions.
- FILE resource READ, uninitialized or all-empty queue input, missing whole/nested
  data containers, direct readonly POSITION
  orientation destinations and generic CONFIG conversion/status aliases remain blocked.
  [Portable CONFIG words](config-words.md) now support source and explicit
  variable-transfer value conversions, with a documented 16-bit Pythonic layout;
  native packed memory, generic reference casts and negative/high-bit words remain excluded.
  [Whole-data READ](aggregate-input.md) now supports shaped ARRAY/record/CONFIG/
  Cartesian/joint data through flat scalar callbacks and existing FILE transports;
  uniform formats follow the scalar domains; native packed layouts remain
  unavailable. [CONFIG scalar-field READ](config-field-input.md) now supports
  bounded turn integers and BOOLEAN flags through callbacks and
  explicit FILE transports; no compact native CONFIG binary layout is inferred.
- Whole ARRAY, PATH, user STRUCTURE and QUEUE_TYPE UNINIT queries;
  dimension flattening, field-set changes/renaming and resource fields. Context-free
  [STRUCTURE source conversion](record-schema-conversions.md) now maps identical
  field-name sets recursively, including record ARRAY terminals.
  [Model-backed record conversion](kinematic-records.md) now extends supplied
  joint/Cartesian models through nested fields and record ARRAYs, with complete
  data/geometry preflight and staged publication. [Model-backed variable transfers](kinematic-variable-transfers.md)
  now extend explicit context through GET_VAR/SET_VAR scalar, ARRAY-prefix and record
  data; implicit context remains unavailable. Omitted STRING ARRAY
  result capacities now [inherit concrete returned storage](inherited-string-array-results.md);
  malformed/mixed capacities remain blocked. [Partial data copies](partial-aggregate-values.md) now
  preserve missing scalar leaves across assignments, private arguments and results;
  malformed known data, resource-bearing values and schemas above64 levels remain blocked.
- Direct joint field access, nonzero-axis-discarding joint-width conversions,
  and implicit robot-context discovery. [Checked Pythonic axis subscripts](joint-axis-access.md)
  now support REAL data cells, nested/ARRAY joint elements, captured aliases, input
  and explicit variable paths; native source acceptance and axis units remain unverified.
  [Source joint-width conversions](joint-width-conversions.md) now pad zeros or
  narrow zero-only trailing axes into complete private values without robot inference.
  [Joint/Cartesian source routine conversions](kinematic-interfaces.md) now require
  explicit models/adapters and current inverse seeds, using private values.
  [Model-backed ARRAY source conversions](kinematic-arrays.md) now apply these
  scalar rules to complete named/anonymous arrays with atomic receiver publication.
  [Cartesian source argument/RETURN conversions](cartesian-interfaces.md) now
  use private values across POSITION/XYZWPR/XYZWPREXT; BYNAME, linked declarations,
  callback raw return types remain exact.
  [Positional ARRAYs](positional-arrays.md) now change Cartesian representation
  or checked joint width, including same-rank GET_VAR/SET_VAR prefixes. Individual
  [GET_VAR/SET_VAR positional values](positional-variable-transfers.md) now change
  Cartesian representation or checked joint width without inferring kinematics.
  POSITION orientation columns remain recursively read-only source storage.
  [VECTOR translation frames](vector-translation-frames.md) now support left
  offsets, independent INV negation and FRAME points. A VECTOR-only origin cannot
  supply CONFIG; complete pose/model context remains mandatory for that role.
- [Numeric ARRAY source conversions](numeric-arrays.md) now support checked
  INTEGER/BYTE/SHORT changes and REAL promotion. [Named/component ARRAY conversions](named-array-conversions.md)
  extend numeric, Cartesian, joint-width and explicit-model source assignments,
  arguments and RETURN values while preserving receiver schemas.
  [Source schema conversion](array-schema-conversions.md) now adds same-terminal
  ARRAY names, bounded STRING capacities and flat/nested layouts with matching
  logical dimensions, including actual generic receiver schemas.
  [Checked REAL narrowing](real-integral-conversions.md) now truncates toward zero
  at source and explicit variable-transfer data boundaries, including nested
  records/ARRAYs; generic references and typed service inputs remain exact.
  Incompatible record fields, rank/dimension changes, equal-count reshape and generic runtime compatibility changes remain blocked.
- Unbounded/Unicode strings, lengths above 254, implicit numeric-to-BOOLEAN
  truthiness, arbitrary-size INTEGERs, MAXINT as ordinary initialized storage,
  NaN/Infinity and exact native numeric/storage/rounding equivalence. Public
  Pythonic mode uses finite Python float and practical numeric equivalents.
- Native external routine ABI, PC binary execution and automatically discovered
  libraries. FROM linkage uses supplied typed source modules or explicit callbacks.
  [Logical collection results](external-collection-results.md) add exact owned
  values/typed JSON and explicit fixed-value CLI bindings; algorithmic
  behavior and resource effects require a callback or supplied source implementation.
  [Explicit data outputs](external-outputs.md) now publish disjoint typed argument
  batches with the declared result after complete validation.
  [Explicit data case bindings](external-values.md) now cover supplied fixed or
  exact argument-dependent data responses and no-op procedures from CLI JSON.

## Registers, variables and I/O

- Live controller banks, physical I/O reads/writes, rack/slot discovery, hardware
  routing, automatic polling and native alarm/status mappings. Numeric, string,
  position and port services use explicit offline banks.
- [Four source frame/tool reads](handler-priority-and-system-poses.md) now use
  supplied frame/tool tables and active selections, with independent POSITION
  values and model-free JSON persistence. [Active selection numbers](frame-tool-selection.md)
  add private INTEGER reads and checked assignments; writable source aliases remain excluded.
- Automatic system-variable schemas, arbitrary host/Python attribute access,
  dynamic routine-local lookup, native cached variable table IDs and native
  allocation/layout behavior. GET_VAR/SET_VAR support declared/explicit roots,
  checked static paths, [checked numeric scalar/ARRAY transfers](numeric-variable-transfers.md)
  and [compatible context-free record schemas/record ARRAY prefixes](record-variable-transfers.md)
  with atomic data/cache/status publication. [Built-in record bridges](record-bridges.md)
  also map matching user structures and builtin fields, preserving CONFIG bounds
  and requiring complete proper POSITION geometry on construction. [Explicit model-backed transfers](kinematic-variable-transfers.md)
  now cover joint/Cartesian scalar, prefix and record data. Schema discovery and
  field renaming remain unavailable. Logical queue transfers, CREATE_VAR and
  variable renaming operate on explicit logical storage. Whole PATH now has an
  [exact Pythonic copy extension](path-transfers.md) with bounded partial data
  and documented detached-node aliases; the reviewed manual excludes the native
  whole-PATH call form. [Logical PATH archives](path-archives.md) now cover portable
  VR, recursive/mixed batches and explicit DRAM restore. Whole FILE transfer,
  resource embedding and native PATH/VR layout/association records remain unavailable.
- Automatic application of staged I/O assignments/modes. The host must explicitly
  apply the supplied offline configuration. Remote bank calls model named peers;
  they do not establish network sessions, discover peers or convert robot poses.
- Native TP caller-stack discovery and local register allocation remain unavailable.
  Twelve [TP local register calls](teach-registers.md) now use explicit caller
  bindings and per-program banks, distinct from ordinary registers, TP program
  positions and GET_TPE_PRM parameters. Seventeen [TP program data calls](teach-programs.md)
  model logical programs, grouped positions, comments and metadata; native TP
  files, execution and physical controller data remain unavailable.

## Files and collections

[FILE arrays](file-arrays.md) now support indexed streams and borrowed
routine/source-linked storage. [Direct FILE prefix arguments](direct-file-prefixes.md)
now borrow rows/planes from globals, locals and formal banks without BYNAME lookup.
Grouped FILE values, copies and generic FILE bank data I/O remain excluded. [Dynamic creation](dynamic-file-arrays.md) adds
checked allocations and closed creation-tagged JSON markers. Whole FILE ARRAY
copies/results, resource STRUCTURE fields, generic FILE codecs and live descriptor
restoration remain excluded. Whole ARRAY READ/WRITE follows the separate data, PATH-bank and initialized
queue-entry policies; FILE banks remain excluded.

- Physical device mounting/formatting/purging, sockets, serial devices, pipes,
  device discovery and unrestricted absolute-path file access. Six device/storage
  calls now operate on [explicit virtual DeviceFiles volumes](virtual-devices.md),
  with byte accounting and reclamation. MemoryFiles and explicitly rooted
  DirectoryFiles retain their existing FILE behavior; management calls cannot
  target those backends or host drives.
  GET_PORT_ATR/SET_PORT_ATR now retain [explicit serial configuration](serial-attributes.md)
  with seven checked attributes; they do not open ports or exchange serial data.
  Separate [finite serial streams](serial-streams.md) now expose supplied RX/TX
  through P1:..P5: FILEs. Hardware ports, automatic attribute application,
  physical/native producer waiting and serial timing remain unavailable.
  [Cooperative serial waiting](serial-waiting.md) now accepts explicit host feeds
  and EOF, with atomic outputs and pending-read cleanup; it creates no connection.
- Proprietary PC/VR/native binary layouts, arbitrary FILE attributes/listing
  formats, device-specific parsing and controller file alarms. Text and binary
  scalar operations use the documented portable formats and bounded sizes;
  FILE_LIST supports [formats 0 through 4](file-listing.md), with portable
  40-column size records and blank timestamps; native metadata formats remain open.
  [Wildcard COPY/DELETE](wildcard-file-operations.md) now support bounded final-name
  star/question source patterns and full-stem star templates.
  [Single-character FILE wildcards](question-file-wildcards.md) also apply to MOVE_FILE. [Wildcard RENAME](wildcard-rename.md)
  now moves same-bank closed files or plain PIP configurations without
  overwrite. [Cross-volume virtual renames](cross-volume-rename.md) now preflight
  complete destination capacity and retained source bytes within one DeviceFiles
  bank. [Cross-bank renames](cross-bank-rename.md) now move exact files and bounded
  batches between explicit plain PIP and ordinary file banks, using empty reserved
  pipe targets and no ordinary overwrite. [Ordinary source directory patterns](directory-globs.md)
  now add component star/question and directory globstar selection to COPY/DELETE/RENAME.
  [Directory-pattern moves/listings](directory-file-queries.md) also extend MOVE_FILE
  with preserved RD/FR subdirectories and FILE_LIST with bounded component matching;
  their legacy flat selection and publication contracts remain separate.
  [Directory-preserving destinations](directory-destinations.md) now insert
  source-relative components with one whole-directory ** placeholder in COPY/RENAME.
  [Directory component stars](directory-components.md) now add full relative-name
  substitution with literal prefix/suffix tags and one optional globstar.
  Question/bracket/multiple-star directory templates, PIP directory sources, separate
  ordinary-bank discovery, socket/DAQ batches and cross-file atomic host
  transactions remain unsupported.
  [Plain PIP batches](pipe-wildcard-files.md) now copy/delete finite snapshots with
  explicit configured destinations; automatic pipe creation and ring truncation
  during copying remain unavailable.
- Physical PATH node byte sizes, native association records and native message
  attachments. NODE_SIZE uses [portable packed schema widths](path-geometry.md).
  QUEUE_ATTACH has a separate [offline message-attachment model](remote-messages.md);
  QUEUE_TYPE uses a fixed INTEGER buffer, FIFO entries and portable
  sequence/status conventions.
- Persisting live file handles, callbacks, connected clocks, queue buffer
  references, Python closures, generator/call stacks or suspended task execution.
  JSON stores values and logical collection state; it is not a task checkpoint.
- XML writing, DTD/entity processing, Unicode, namespace interpretation and
  native streaming/error equivalence. All five [XML input calls](xml-input.md)
  now support bounded ASCII FILE scanning and [checked nested scalar/ARRAY leaf updates](xml-aggregate-paths.md),
  including BYTE/SHORT and [explicit built-in record roots](xml-record-roots.md),
  with atomic publication;
  live scanners and registrations are omitted from saved JSON.

## Tasks, handlers and programs

- Native preemption, priorities, CPU time slices, group locks, interrupt ordering,
  instruction pointers, allocated stack-byte reporting and native parent/child
  relationships. The scheduler runs deterministic cooperative checkpoints.
- Native STOP/RESUME motion behavior. Offline STOP is terminal; resume/continue
  acts on retained cooperative generators. Arbitrary start lines, motion flags
  and lock masks in task procedures remain outside their supported forms. Six
  [logical controller calls](controller-services.md) now cover group ownership
  queries, cancellation of owned stopped labels, stored six-axis perches, scripted
  RESET and cooperative background slots. Native motion, hardware reset, per-value
  joint group/unit conventions and TP background scan scheduling remain unavailable.
- Native task policy effects remain unavailable. SET_TSK_ATTR now has nine
  [offline settings](task-attributes.md), including cooperative priority/slice
  policies, request masks and bounded tracing. Other attributes remain read-only
  or require explicit informational metadata. SET_ATTR_PRG retains its four
  metadata writes and activity guards.
- SET_TSK_NAME now has an [offline implementation](task-renaming.md), including
  stable task numbers and retained scheduler state. Native task naming rules and
  controller task identifiers remain unverified.
- Native program load/save/translate/backup/clear/restore, task discovery and
  implicit external linkage. [Dynamic variables and BYNAME](dynamic-variables.md)
  now have explicit offline forms. [Typed data arrays](dynamic-data-arrays.md)
  now add ARRAY OF data aliases and named-array outer dimensions, with bounded
  schema/reservation checks and ordinary saved/archive layouts; renaming compiled globals or attached program
  namespaces, embedded resources, restored open FILE handles and native allocation
  remain unsupported. [Dynamic FILE descriptors](dynamic-files.md) now create root
  FILE/aliases for explicit typed I/O and cancellation; JSON retains closed
  allocation intent and resets handle state on restore. [Dynamic logical collections](dynamic-collections.md) now create root
  PATH/QUEUE_TYPE and supplied aliases with checked header/descriptor reservations;
  QUEUE_TYPE native inspection codes remain unavailable. [Collection arrays](collection-arrays.md)
  now support static/dynamic owned logical PATH/QUEUE_TYPE storage and typed JSON.
  [Logical collection source values](collection-source-values.md) now add owned
  ARRAY assignments, private interfaces/results and independent selected prefixes;
  FILE-bank READ/WRITE, generic codecs and whole collection UNINIT retain
  guards. [PATH-bank I/O](path-array-io.md) and [queue entry I/O](queue-io.md)
  add whole-bank and selected row/plane scalar streams. Queue input replaces
  existing values and detaches buffer links without writing the old ARRAY cells;
  initialized empty output is allowed, but input does not infer or append entries.
  [Owned collection ARRAY VR archives](collection-array-archives.md) now support
  save/load/clear, recursive/mixed batches and explicit DRAM snapshots with
  exact identities, bounded validation and ordinary lifetime guards.
  Program catalogs and load status describe attached programs or supplied metadata.
  [TRANSLATE](source-translations.md) now generates sibling Python and optional
  listings from explicit stored source, with [mapped include FILEs and saved ARRAY
  schemas](stored-translation-inputs.md); native PC output, implicit include discovery,
  program attachment/execution and asynchronous native timing remain unsupported.
- CALL_PROG/CALL_PROGLIN now support [attached cooperative KAREL programs](program-calls.md)
  in the calling task. Newly generated [synchronous targets](synchronous-program-calls.md)
  now use a private caller-owned entry; old outputs without that entry still
  require retranslation. TP/native instruction execution,
  persisted executable links and implicit program loading remain unsupported.
- LOCK_GROUP/UNLOCK_GROUP now have [logical ownership banks](group-locks.md).
  [Opt-in root directive acquisition](directive-group-locks.md) is available;
  a second opt-in adds [callee acquisition/release scopes](scoped-group-locks.md).
  Native locks, lock waits and motion effects remain unavailable. The configured
  bank requires explicit groups and busy labels.
- Native alarm dictionaries, severity encodings, asynchronous history timing,
  power-cycle restoration and controller error recovery. POST_ERR, POST_ERR_L,
  ERR_DATA, semaphores and lifecycle conditions have explicit offline contracts.

## Geometry and robot context

- Physical motion, controller/servo/safety integration and live robot state.
  No geometry, current pose, frame, tool, axis limits or tolerance is discovered
  from hardware; supply it explicitly.
- Calibrated robot-specific geometry, native CONFIG branch selection, collision
  checks and certified/native reachability. Standard-DH models use bounded
  numerical IK; failure to find a solution is not proof of impossibility.
- Unconfigured groups/axes, coupled mechanisms and external axes beyond the
  supplied model's supported width and trailing-axis mapping. Three XYZWPREXT
  metadata slots do not model arbitrary physical external-axis behavior.
- Native reflection/Euler singularity/configuration/default conventions and all
  robot-specific type conversions. MIRROR, framed conversions, range checks and
  CHECK_EPOS are implemented under documented portable conventions.

## Option-specific systems and application milestones

- Native TP parsing/generation/execution, motion instruction linkage and embedded
  register APIs. The explicit TeachPrograms store supports logical position/comment
  editing and opaque line deletion without those native behaviors. Six
  [program archive calls](program-archives.md) now support portable TP records,
  recursive explicit graphs and guarded in-memory batches. Native TP/PC/VR/IO
  binaries and KAREL code unloading remain unavailable. [Portable variable
  archives](variable-archives.md) now support VR data, variable-only recursive
  batches and explicit SAVE_DRAM points. [Mixed TP/VR batches](mixed-archives.md)
  now support PBR_ALLTYPE backup/clear and manifest-based restore across both
  stores. Native binary batches and automatic DRAM/flash restoration remain unavailable.
- Native controller rendering, host/controller keyboard capture, form/list/table
  managers, compressed dictionary files and language packs. Ten [pendant display calls](pendant-display.md)
  now have headless request/surface models, including WD:name output, cursor
  movement and scrolling. No native keyboard acquisition, glyphs, abort-time screen
  restoration or font/style rendering is supplied. Seven [text dictionary calls](text-dictionaries.md)
  now load explicitly supplied ASCII text, expand nested elements, format static
  variables, read ARRAY rows and write atomic logical window controls. Native
  compressed TX/UTX compiler workflows, native VR form associations and glyph
  encodings remain blocked.
  Twelve [dynamic display calls](dynamic-displays.md) now watch static globals and
  explicit ports, with bounded logical checkpoint intervals, atomic field updates
  and typed cancellation. Native background timing, implicit task cleanup, live
  binding persistence and native form widgets remain unsupported. Six
  [keyboard/menu calls](keyboard-input.md) now use injected key events, editable
  buffers, masks, pane capture, cooperative waits and PUSH/POP suspension; combined
  WD/TPKB echo and dictionary-backed entry/subwindow/pull-up controls are modeled.
  Native key codes, soft-key editing widgets, raw binary transfer and native form
  widgets remain outside that contract. [Typed keyboard FILE READ](keyboard-file-read.md)
  now parses submitted ASCII lines with buffered suffixes and atomic outputs;
  [bounded PASSALL ASCII fields and printable EOL](keyboard-raw-read.md) are now
  supported. Numeric/raw binary transfer, nonprintable custom delimiters and native
  key encodings remain unsupported. Four
  [list/table controls](table-controls.md) now support resident lists and typed
  array-backed editors with injected keys, port cells and explicit session guards.
  [DISCTRL_FORM](forms.md) now accepts supplied FTX forms with typed scalar/port
  editing, numeric/variable/program enums, help, function labels and sequential tree
  groups, including concatenated complete fragments with explicit .tree inheritance.
  Native binary form/VR associations, Data ID discovery, native table header syntax
  and exact widget/layout semantics remain unsupported. Nested tree groups retain
  the documented language prohibition.
- Native DAQ sampling, timing and monitor integration. The six calls now have
  an [offline pipe model](data-acquisition.md), with chosen record/view layouts
  and explicit file streaming. No physical acquisition or native format is implied.
- Native PC/GEMM transport and delivery. Six [PC data/event calls](pc-exchange.md)
  now support typed buffer construction and explicit offline event outboxes;
  custom payloads require raw mode and fully initialized bytes.
- Native socket connections, DNS/ping, native pipe timing and formatted dictionaries.
  MSG_CONNECT/MSG_DISCO/MSG_PING and PIPE_CONFIG now have
  [offline FILE models](communications.md); plain and DAQ pipe names stay distinct.
  Explicit [plain-pipe attributes](pipe-attributes.md) add cooperative waiting
  reads, captured snapshot boundaries and checked overflow recovery.
  [Pipe file management](pipe-file-management.md) now covers finite COPY/DELETE/
  RENAME/LIST operations with explicit configurations and ordinary backend guards;
  generic DAQ/socket routing and native formatted dictionary output remain open.
- Native mobile/ZDT delivery, message schemas and automatic SET_VAR triggers.
  RMCN_ALERT/RMCN_SEND and QUEUE_ATTACH now have [offline outboxes and deferred
  attachments](remote-messages.md), with explicit host publication/collection.
- Native KCL execution, unmodeled diagnostic events/native stack-word layouts,
  controller XML services, image processing and conveyor/vision tracking. KCL calls now use
  an [explicit scripted channel](kcl-commands.md), and three diagnostic calls use
  an [offline event/stack model](diagnostics.md). Neither executes native commands.
  Fifty-three [vision calls](vision-results.md) now consume supplied completed
  runs and retain registers/parameters. [Image/device services](vision-image-services.md)
  add supplied rasters, PNG/BMP export, reader/view-line output and logical
  camera/calibration/display/LED data. Live acquisition, calibration computation,
  image processing and undocumented save overloads remain open.
  [Alpha image formats](vision-alpha-images.md) now preserve GA/RGBA channels and
  PNG/32-bit BMP transparency. [Explicit palette images](vision-palette-images.md)
  now retain 8-bit indices and supplied RGBA colors with indexed PNG/BMP export.
  Explicit [16-bit samples](vision-16bit-images.md) now retain grayscale/GA/RGB/RGBA
  PNG data; [BMP export](vision-bmp-samples.md) now rounds those components to
  eight bits while preserving exact source samples. Packed 16-bit BMP pixels,
  physical depth maps, proprietary image
  layouts and color/calibration transforms remain unavailable. Twelve
  [legacy tracking calls](vision-tracking.md) now add timed queues, receipts,
  VT result/lookup forms, supplied point maps and a portable local outbox.
  Twelve [VT queue calls](vt-queues.md) add allocation/acknowledgement, partial
  PATH editing, flags, weighted routing and explicit time/flow estimates. Native
  tracking/motion, native calibrated tray/Seq algorithms, historical flow regions,
  native duplicate tolerances, automatic encoder/frame transformations and
  mobile delivery remain unavailable. [Supplied VT tray cells](vt-trays.md) now
  expand into independent queue entries, with explicit geometry, sequence choices,
  per-cell model/routing and allocation/forwarding state.
- The workbench currently validates/translates/reviews/exports. The planned Python
  runner, input-parameter editor, read-before-write discovery and combined
  input/result JSON are still [future work](roadmap.md).
- Public strict mode remains a future milestone. `--mode strict` is rejected;
  preserved historical exactness work is not an available public execution mode.

## Evidence still needed

The manual inventory combines editions and options. Some headings lack a complete
signature, installed environment definitions or an accepted compiler probe.
The reference campaign spans 20 releases; its accepted cases establish acceptance
of particular source forms, not all overloads or runtime behavior. Rejection can
also reflect probe syntax, missing environment/support files or an option.

Runtime equivalence on FANUC controllers, native ABI/binary formats, native status
enums and option-specific commissioning remain unverified. Authored public tests
establish translation and offline behavior only. Manuals and private compiler
campaign reports remain outside this public repository. See
[reference provenance](references.md) and the current per-feature semantic notes;
older conservative ledgers can contain restrictions superseded by Pythonic guides.

## Built-ins with no registered translation

None in the audited 334-name inventory. This is registration coverage, not full
source-form coverage or native/controller equivalence. The sections above retain
the remaining restrictions, partial services and future milestones.
