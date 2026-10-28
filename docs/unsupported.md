# Remaining Pythonic support

Audited on 2026-10-28 against the 465-heading, multi-edition KAREL feature
inventory, the programmer reference and the implemented parser/runtime. This is
a product backlog, not a controller compatibility certificate. The inventory
contains statements, actions, clauses, types and directives as well as calls;
one heading does not equal one executable feature or one percentage of coverage.

The inventory has 334 distinct built-in names after merging repeated headings.
Currently, 333 have a registered translation and one does not.
Registration means a supported form exists; it does not mean every overload,
option, type, controller release or native behavior is implemented. Calls outside
this reference set can also be rejected. The complete remaining name list is
below. The [support guide](language-support.md) describes accepted forms.
Some exclusions, such as whole-array UNINIT, retain documented language rules;
they are boundaries rather than promises to accept every such source form later.

## Language and source forms

- Unknown directives and binary environments. %INCLUDE now expands
  [explicitly supplied source fragments](includes.md), with three nested files,
  selected directory/device lookup and original-file diagnostics. The four original metadata directives,
  seven [task policies](task-attributes.md) and nine additional
  [source policies](source-directives.md#additional-source-policies) are accepted.
  DEFGROUP selects offline defaults and CRTDEVICE labels I/O requests; native
  storage, group locks, periodic delay, stack allocation and real device routing
  are not applied. Include search does not discover native support installations.
- Native motion statements: `MOVE TO`, `MOVE NEAR`, `MOVE AWAY`, `MOVE ABOUT`,
  `MOVE ALONG`, `MOVE AXIS`, `MOVE RELATIVE`; their `VIA`, motion `WITH`, `WHEN`
  and `UNTIL` clauses; motion ownership and hand control. `ATTACH`, `RELEASE`,
  `OPEN HAND`, `CLOSE HAND`, `RELAX HAND`, `HOLD`, `UNHOLD`, `CANCEL`,
  `CANCEL FILE` and standalone `PURGE` are not translated. `PURGE CONDITION`
  is supported. `IN GROUP[n]` does not add motion or other native `IN` clauses;
  `IN DRAM` storage placement is unavailable.
- Handler actions involving native motion, hold/unhold or file cancellation;
  path-node arrival (`A TNODE`) conditions. Checkpoint predicates, events, port
  edges, semaphores, errors and lifecycle notifications have offline models.
  TIME-style behavior uses connected timers and comparisons; motion timing,
  asynchronous native interrupts and motion-local handlers are unavailable.
- Labels/jumps inside FOR bodies, transfers across program/routine bodies, and
  entry into an uncaptured USING scope. [Nested/sibling label transfers](nested-jumps.md)
  now support IF/WHILE/REPEAT/SELECT targets with normal loop continuations.
  Forward/self/cyclic type aliases remain blocked. Full [external FROM type declarations](external-types.md)
  now use supplied source layouts and checked project ownership chains; missing
  definitions, cyclic ownership and native binary type environments remain blocked.
  Routine-local TYPE declarations
  remain prohibited by the KAREL language, rather than a planned extension.
- `USING` function-result/computed selectors, whole ARRAY/resource/joint selectors,
  field FOR counters and dynamic caller scope. [Captured USING selectors](using-selectors.md)
  now accept indexed/grouped record storage and built-in records; calls inside
  indexes use the one-time entry capture policy. SELECT is INTEGER-only; a miss
  without ELSE fails. Recursion is bounded at 64 calls.
- Unicode/multilingual source, native graphic characters, multiline literals,
  backslash string escapes, token-splicing continuations and arbitrary native
  preprocessor/compiler extensions.

## Types, expressions and interfaces

- `COMMON_ASSOC`, `GROUP_ASSOC` and the obsolete `STD_PTH_NODE.GROUP_DATA` /
  `COMMON_DATA` association layouts. [Predefined structures](path-declarations.md)
  now expose DISP_DAT_T data and the portable STD_PTH_NODE NODE_POS field; PATH
  accepts authored NODEDATA and PATHHEADER/PATHDATA structures. Native group
  associations and native display/recording behavior remain outside those records.
  The separate [headless display model](pendant-display.md) supports character
  windows and screen composition. [List/table controls](table-controls.md) now use
  DISP_DAT_T resident-list metadata and portable COL_DESC_T/XWORK_T records; native
  memory layouts and widget rendering remain unverified.
- Dynamically resized/ragged arrays, unknown runtime wildcard dimensions, ranks
  above three and aggregates exceeding the 32767-leaf prototype bound. Global
  wildcard declarations require translation-time shapes; no VR auto-discovery.
  Linked projects now route common or [program-qualified shapes](project-array-shapes.md)
  to the declared wildcard storage, including differing module-local dimensions.
- Standalone BYTE/SHORT variables and routine interfaces; they remain aggregate
  field/element and file forms. BYTE unknown contents cannot be queried with
  UNINIT. SHORT 32767 is the retained uninitialized sentinel.
- Whole ARRAY, PATH, user STRUCTURE, FILE and QUEUE_TYPE UNINIT queries; flattening,
  nominal-type coercion, unspecified STRING result-element capacities and resource
  fields in structures. [Partial data copies](partial-aggregate-values.md) now
  preserve missing scalar leaves across assignments, private arguments and results;
  malformed known data, resource-bearing values and schemas above64 levels remain blocked.
- VECTOR left frames and VECTOR inputs to INV/FRAME; direct joint field/index access; implicit
  pose/joint conversions in exact routine, RETURN and whole-array interfaces.
  POSITION orientation columns remain recursively read-only source storage.
- Unbounded/Unicode strings, lengths above 254, implicit numeric-to-BOOLEAN
  truthiness, arbitrary-size INTEGERs, MAXINT as ordinary initialized storage,
  NaN/Infinity and exact native numeric/storage/rounding equivalence. Public
  Pythonic mode uses finite Python float and practical numeric equivalents.
- Native external routine ABI, PC binary execution and automatically discovered
  libraries. FROM linkage uses supplied typed source modules or explicit callbacks.

## Registers, variables and I/O

- Live controller banks, physical I/O reads/writes, rack/slot discovery, hardware
  routing, automatic polling and native alarm/status mappings. Numeric, string,
  position and port services use explicit offline banks.
- Automatic system-variable schemas, arbitrary host/Python attribute access,
  dynamic routine-local lookup, native cached variable table IDs and runtime
  variable creation/rename. GET_VAR/SET_VAR support declared/explicit roots,
  checked static paths and documented aggregate/queue transfers.
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

- Physical device mounting/formatting/purging, sockets, serial devices, pipes,
  device discovery and unrestricted absolute-path file access. Six device/storage
  calls now operate on [explicit virtual DeviceFiles volumes](virtual-devices.md),
  with byte accounting and reclamation. MemoryFiles and explicitly rooted
  DirectoryFiles retain their existing FILE behavior; management calls cannot
  target those backends or host drives.
  GET_PORT_ATR/SET_PORT_ATR now retain [explicit serial configuration](serial-attributes.md)
  with seven checked attributes; they do not open ports or exchange serial data.
- Proprietary PC/VR/native binary layouts, arbitrary FILE attributes/listing
  formats, device-specific parsing and controller file alarms. Text and binary
  scalar operations use the documented portable formats and bounded sizes;
  FILE_LIST supports [formats 0 through 4](file-listing.md), with portable
  40-column size records and blank timestamps; native metadata formats remain open.
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
  now support bounded ASCII FILE scanning and checked flat structure updates;
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
  now have explicit offline forms; renaming compiled globals or attached program
  namespaces, dynamic resource creation and native allocation remain unsupported.
  Program catalogs and load status describe attached programs or supplied metadata.
- CALL_PROG/CALL_PROGLIN now support [attached cooperative KAREL programs](program-calls.md)
  in the calling task. Noncooperative targets, TP/native instruction execution,
  persisted executable links and implicit program loading remain unsupported.
- LOCK_GROUP/UNLOCK_GROUP now have [logical ownership banks](group-locks.md).
  Automatic directive acquisition, native locks, lock waits and motion effects
  remain unavailable; the configured bank requires explicit groups and busy labels.
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
  image processing and undocumented save overloads remain open. Twelve
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

This list is exhaustive for distinct built-in names in the audited inventory.
An explicit user routine can use one of these names, but that does not implement
the corresponding controller built-in. Names are grouped by purpose; grouping
does not assert a particular installed option or environment.

### Native program translation (1)

- `TRANSLATE`
