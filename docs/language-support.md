# Language support

This is the supported prototype subset as of 26.1030.192713. Acceptance is specific to
source form, type and context. A supported feature can still reject uncertain
inputs at runtime. The [semantic notes](semantics/README.md) separate documented
rules, implemented restrictions and unresolved native behavior.
The [remaining-support inventory](unsupported.md) lists unimplemented built-ins,
language forms, partial-service boundaries and future application milestones.

Public translation uses [Pythonic numeric equivalents](numeric-modes.md).
Strict mode is a future milestone; older exactness contracts are preserved
internally and in the historical semantic notes.

| Area | Supported subset | Limits |
| --- | --- | --- |
| Source | Case-insensitive ASCII identifiers, comments, four metadata directives, seven task policies and nine additional source policies, explicit nested %INCLUDE expansion, bounded complete-token continuations, doubled apostrophes | DEFGROUP selects offline defaults, CRTDEVICE labels requests; opt-in root and callee group scopes use an explicit bank, while storage/stack/periodic-delay intent remains metadata. Unknown directives, token fusion and multiline literals remain blocked; include sources require explicit mappings or selected roots. |
| Motion requests | Seven basic MOVE forms, Cartesian VIA, direct PATH-node destinations and inclusive PATH ranges, hand statements and ATTACH/RELEASE | Explicit [MotionRequests](motion-requests.md) capture-only or immediate scripted responses; detached operands, logical group ownership, independent HOLD/UNHOLD/CANCEL, nine [local WITH settings](motion-controls.md), including [termination/orientation choices](extended-motion-settings.md), [local WHEN/UNTIL and supplied delays](motion-handlers.md), [scheduled node/time predicates](motion-timeline.md), and bounded JSON history. No trajectories, inferred arrival timing, remaining native motion environment, queued completion or robot feedback updates. |
| Control flow | Assignment, IF/ELSE, WHILE, REPEAT, inclusive FOR/DOWNTO, SELECT, RETURN | FOR can capture INTEGER/BYTE/SHORT fields/elements/USING fields with checked counter domains; conservative aggregate-root write/reuse guards and exact cleanup apply. Formal/nonlocal roots in parameterized routines require fresh locals; unproven external calls over global aggregate counters remain blocked. [Scalar SELECT](scalar-select.md) accepts finite numeric, BOOLEAN and ASCII STRING categories, evaluates compatible constant/dynamic labels once in source order before choosing the first matching case and errors without a match/ELSE. |
| Labels | Body-scoped labels and GOTO, nested/sibling IF/WHILE/REPEAT/SELECT targets and active FOR-body transfers | Ordinary continuation, retained active FOR bounds and exited-counter cleanup; no entry into new FOR or USING scopes or cross-routine transfers. See [nested jumps](nested-jumps.md) and [FOR jumps](for-jumps.md). |
| Routines | Internal procedures/functions, bare zero-argument function calls, fresh local frames, local constants, reference/value arguments, recursion | Depth limit 64; chosen Pythonic left-to-right evaluation; existing FOR rules; typed FROM project/callback linkage; no native external ABI or local TYPE sections. |
| INTEGER | Checked signed 32-bit expressions, bit operators, DIV and signed MOD | MAXINT excluded from normal storage; DIV truncates toward zero; MOD follows Python remainder. |
| BOOLEAN | Strict Boolean storage, operators and comparisons | Numeric values are not implicitly Booleans. |
| REAL | Python float, rounded arithmetic, promotion, ROUND/TRUNC, SQRT, EXP and LN | Finite values required; existing checked INTEGER results. ROUND uses ties to even. |
| Trig | General degree SIN/COS/TAN/ASIN/ACOS and ATAN2 | Inverse/domain checks remain. ATAN2 uses KAREL `(x,y)` order, all quadrants and Python -180..180 degree output. |
| STRING | Bounded ASCII storage, right truncation, internal STRING/STRING[n] function results, writable value arguments, concatenation/comparison, clipped SUB_STR and INDEX including empty searches | Default result/value capacity 254; explicit result capacity 1..254. Bare arguments keep caller references. SUB_STR returns at most 254; positive start and nonnegative count. |
| BYTE/SHORT | Aggregate and standalone storage, TYPE aliases, exact references, checked private numeric arguments and initialized routine results | BYTE 0..255, SHORT -32768..32766; initial BYTE is unknown and its UNINIT is blocked. SHORT 32767 means uninitialized; [narrow counters](narrow-for.md) restore BYTE unknown and SHORT missing state on exit. [Dynamic narrow creation](dynamic-narrow.md) retains exact types and initialization markers. See [scalar narrow integers](scalar-narrow.md). |
| Arrays | One-based fixed/named arrays up to logical rank three, complete [chained subscripts](chained-array-indexes.md), exact whole copies, reference/value arguments and named subarrays | Copies preserve missing markers with 32767 scalar leaves and 64 schema levels; receiver schema, logical shape and known scalar validation remain. [Numeric conversions](numeric-arrays.md) add checked integral narrowing and REAL promotion; [named/component conversions](named-array-conversions.md) preserve receiver schemas at source assignment/argument/RETURN boundaries. [Schema conversions](array-schema-conversions.md) add same-terminal names, STRING capacities and compatible flat/nested layouts. |
| Variable arrays | Explicit translation-time shapes for direct global wildcard declarations | No inference, controller/VR access, resize or persistence. |
| ARRAY results | Named types or anonymous fixed/wildcard/mixed dimensions; scalar, bounded or inherited-capacity STRING, record, joint or named ARRAY elements; grouping, argument/RETURN composition and aggregate access | Missing markers preserved and known leaves validated; declared output names/layout and bounded/inherited STRING capacities; logical rank up to three. Source RETURN prepares its independent output schema. Omitted STRING result capacity inherits concrete returned storage; no resize or flattening. |
| Structures | Prior named structures, nested fields/arrays, checked copies and internal results/value temporaries; [source schema conversions](record-schema-conversions.md) | Matching field-name sets convert recursively into receiver schemas, including record ARRAY terminals; checked numeric/STRING and context-free pose/joint changes; [explicit-model geometry fields](kinematic-records.md). Private converted arguments, partial-data preservation and exact generic/BYNAME/link/callback contracts; no ABI claim. |
| Predefined structures | DISP_DAT_T SHORT fields/fixed arrays, portable COL_DESC_T/XWORK_T and STD_PTH_NODE NODE_POS; aliases, arrays, fields, routine interfaces and CREATE_VAR | Existing nominal STRUCTURE schemas and initialization/copy/output guards; no obsolete association fields, native UI execution or ABI claim. |
| TYPE aliases | Transparent supported scalar, bounded STRING, record, joint and prior named type aliases; chains and routine interfaces | Preserve original aggregate identity and capacities; bounded STRING formal references require matching capacity, values truncate to private alias capacity. No forward/self/cyclic aliases or local TYPE; aliases preserve scalar/aggregate storage domains. |
| External types | Full TYPE name FROM owner definitions; supported aliases, structures, arrays and resource schemas | Standalone layout and owner metadata; source projects validate exact resolved schemas, self owners and acyclic reexports before allocation. No binary environments or native owner-qualified ABI. |
| USING | Nested scopes; named/grouped record storage references and independent computed record captures | One-time left-to-right capture, inner/right-most field priority and handler lifetime. No copy-back for computed values; isolated private integral counters use whole-root/retained-alias proofs. [Private timers](private-using-timers.md) accept ordinary INTEGER leaves with terminal cleanup; whole ARRAY/resource/joint selectors remain blocked. See [computed USING](computed-using.md). |
| Positional data | CONFIG, VECTOR, XYZWPR, XYZWPREXT, POSITION data and exact value/result copies; POS constructs XYZWPR from six numbers and explicit CONFIG | POS retains coordinate/angle bounds and complete CONFIG checks without robot-specific validity. POSITION orientation starts unknown; explicit XYZWPR assignment can initialize it while retaining recursive read-only protection. No robot defaults. |
| Initialization queries | UNINIT on supported scalar/joint storage and whole builtin records, including nested fields and individual ARRAY elements | Any missing builtin-record leaf means TRUE; read-only schema/type checks. Whole ARRAY, PATH, user STRUCTURE, FILE, QUEUE_TYPE and BYTE queries remain blocked. |
| Variable inspection | VAR_INFO metadata and VAR_LIST filtered/paged global names | Current/attached declarations and explicit bindings; canonical types, bounded dimensions/formats, portable initialization flags and statuses; no local/controller discovery. |
| Program listing | PROG_LIST with optional cursor | Attached Programs and explicit immutable metadata; type filters, sorted pages, checked formats and persisted catalogs; no program discovery or loading. |
| Program metadata | LOAD_STATUS, GET_ATTR_PRG, SET_ATTR_PRG | Attached load/partial global initialization, explicit snapshots and typed attributes; four metadata writes with active-task guards, portable constants/statuses and persistence; no native loading or task-policy writes. |
| Diagnostics | CHECK_STACK, SET_DEBUG, SET_DB_EVENT; eight portable source/call/lifecycle event labels | Explicit DiagnosticLog, bounded value-free records and configured frame-cost stack estimates; no native p-code, stack layout or diagnostic option equivalence. |
| Forms | DISCTRL_FORM with supplied FTX source; typed scalar/port edits, selections, enums, help, paging, sequential trees and concatenated .tree fragments | Explicit FormControls and USER2; literal forward single-window layout, root-owned attributes; no native compression/VR association ABI. See [forms](forms.md). |
| Lists and tables | DISCTRL_LIST, INIT_TBL, ACT_TBL and DISCTRL_TBL; COL_DESC_T and opaque XWORK_T | Explicit resident rows and static array/port cells, typed edits, change grids, injected keys and session cleanup; portable layouts/codes, no form grammar or native widgets. See [table controls](table-controls.md). |
| Keyboard and menus | Typed FILE READ, READ_KB, PUSH_KEY_RD/POP_KEY_RD, DISCTRL_ALPH, DISCTRL_SBMN and DISCTRL_PLMN; KB and combined WD/TPKB endpoints | Explicit injected events, cooperative editing/waits, pane capture, suspension tokens, dictionary choices and terminal-state persistence; no host keyboard capture or native soft-key rendering. |
| Dynamic displays | Twelve INI_DYN_DIS*/CNC_DYN_DIS* calls for BOOLEAN, enum, INTEGER, REAL, STRING and supplied ports | Explicit read-only static bindings, checkpoint intervals, one-line fields and identity-based cancellation; cancel bindings before context save. No native display task, fonts or form managers. |
| Text dictionaries | Seven ADD/CHECK/READ/REMOVE/WRITE dictionary calls, plain and formatted, with nested text elements and static variable paths | Explicit supplied text catalogs, language snapshots, bounded formatting, ARRAY truncation and atomic logical window controls; no compressed TX decoding or form compilation. |
| Pendant display | FORCE_LINK, FORCE_SPMENU, SET_LANG, screen/window definitions, activation, attachments, detachment and SET_CURSOR; WD:name text output | Explicit headless PendantDisplay, portable IDs/statuses, character grids, common/per-handle cursors, scrolling and closed-handle persistence; no native UI, keyboard or dictionaries. |
| Vision services | 53 calls for supplied runs/images including [explicit palettes](vision-palette-images.md), registers, result arrays, view-line PATHs, reader/file output, parameter editing and logical devices | Explicit inputs, PNG/BMP export, checked outputs and persistent queues/cursors/state; no image processing or hardware I/O. See [vision results](vision-results.md) and [image/device services](vision-image-services.md); [legacy tracking](vision-tracking.md) adds timed queues, allocation receipts, VT result/lookup forms, supplied maps and a local outbox. [VT queues](vt-queues.md) add put/get/acknowledge, partial PATH editing, flags, routing and time/flow estimates. |
| Controller services | MOTION_CTL, CNCL_STP_MTN, SET_PERCH, RESET and MIXBG_RUN/STOP | Explicit ownership/perch banks, scripted reset results and attached background tasks; portable units/statuses, no motion statements or hardware reset. See [controller services](controller-services.md). |
| KCL | KCL, KCL_NO_WAIT and bare/called KCL_STATUS over explicit scripted replies | One shared accepted command, configured delays/statuses, bounded history and terminal-state persistence; no host/controller command execution or implicit replay of pending work. |
| Remote banks | 17 RGET/RSET numeric/string/comment/port procedures and numeric/position receive/send | Explicit persisted PeerBanks, per-peer banks/type codes, selected outputs, simulation and checked register copies; explicit position groups and comment options; no networking or robot conversion. |
| Collection persistence | PATH and QUEUE_TYPE context variables | Typed partial PATH data, queue FIFO/sequence state and explicit buffer rebinding; portable logical snapshots without native layouts or task checkpoints. |
| POSITION conversion | Whole assignments among XYZWPR, XYZWPREXT and POSITION; independent location/configuration and checked orientation matrices | Finite complete values; proper unit/orthogonal matrix checks with explicit 1e-9 tolerance; [Cartesian source routine conversions](cartesian-interfaces.md) use private differing representations; whole-array/BYNAME/linked declared types remain exact; context-free Cartesian conversion only; model-backed joint assignments are listed below. Widening zeros external metadata; narrowing drops it. |
| Output pulses | PULSE DOUT with blocking/NOWAIT statements and blocking handler actions | Explicit bank, rounded duration, host polling or scheduler virtual time; portable override/lifecycle rules. |
| Kinematic assignment | Whole JOINTPOS to/from POSITION/XYZWPR/XYZWPREXT assignments and [source routine conversions](kinematic-interfaces.md) using supplied robot adapters/models | Selected frame/tool and root group; inverse needs current joints as seed; same-kind source widths use checked zero-padding/zero-only narrowing; [positional ARRAYs](positional-arrays.md) use context-free changes and [model-backed arrays](kinematic-arrays.md) and [nested record conversions](kinematic-records.md) require explicit models and stage complete receiver data; [named/component source conversions](named-array-conversions.md) preserve schemas; BYNAME and declared linkage remain exact. |
| Joint data | JOINTPOS1..9, [checked Pythonic axis subscripts](joint-axis-access.md), exact-width copies, restricted explicit-context REAL-array conversions | One-based finite REAL cells, declared schemas and captured aliases; partial axes allowed. No direct joint fields or implicit group/unit discovery. RobotContext supplies explicit kinematics. |
| VECTOR | VEC construction, arithmetic, cross/dot products, equality, routine values and translation-frame equivalents | Complete finite components; [pose:VECTOR points](vector-frames.md) and [VECTOR translation offsets](vector-translation-frames.md), INV negation and FRAME points with an explicit pose origin. No inferred CONFIG or implicit routine coercion. |
| Conversion | Python INTEGER/REAL text parsing, signed bases 2..16, rounded fixed/scientific REAL output, UNPOS pose-value and model-backed joint extraction | Bounded width/precision, caller capacities and disjoint outputs; source snapshots and chosen Pythonic formatting/pose conventions. |
| CONFIG text | CNV_STR_CONF, CNV_CONF_STR and CNV_CNF_STRG with complete checked CONFIG data and portable flag/turn text | CNV_CNF_STRG uses explicit persisted per-group profiles; missing group status 1 preserves text. No native mask discovery or error mapping. |
| Time text | CNV_STR_TIME and CNV_TIME_STR on supplied packed date/time values | Gregorian 1980..2107, fixed English text, two-second precision and signed bit patterns; complete STRING capacity required; no clock/timezone access or native equivalence. |
| Microsecond timers | GET_USEC_TIM host monotonic sampling and GET_USEC_SUB elapsed subtraction, with optional clock injection | Portable two-minute ring, one clock and intervals shorter than two minutes; no native encoding/tick precision or calendar clock access. |
| Offline numeric registers | GET_REG, SET_INT_REG and SET_REAL_REG on an explicit in-memory NumericRegisters bank | Explicit count/initial values, exact checked outputs and portable missing/range statuses; typed JSON save/load; no controller backend or native status/count/persistence claim. |
| Frame transforms | POSITION/XYZWPR/XYZWPREXT and model-backed JOINTPOS composition, VECTOR offsets/points and INV, three/four-point FRAME construction | JOINTPOS uses explicit forward context; right pose representation is preserved for VECTOR-left translation. Complete poses, origin CONFIG, proper matrices, external metadata and 10 mm FRAME bounds remain; no all-VECTOR FRAME origin or context discovery. |
| Pose axis queries | APPROACH and ORIENT on POSITION/XYZWPR/XYZWPREXT return independent writable VECTOR values for positive Z/Y | Complete finite poses, checked CONFIG and proper POSITION matrices; no normalization, defaults, other positional operands or controller acquisition. |
| Position comparison | Approximate >=< on POSITION/XYZWPR/XYZWPREXT, including mixed operands, returns BOOLEAN | Explicit per-instance distance/angle/external-axis tolerances and CONFIG choice; complete proper poses; Euclidean distance and shortest rotation angle; no native defaults, exact/ordered relations or other operand types. |
| DELAY | Checked 0..86400000 ms through a host callback | Host timing is not controller timing; step budget is not a time budget. |
| WAIT FOR | Repeated checks of supported BOOLEAN expressions, including internal functions | Ordinary step budget, short-circuit rules and sleep(0.0) after false checks; cooperative handlers are separate; no hardware acquisition or native event/timing equivalence. |
| WRITE | Mixed scalar lists, signed integers, finite REALs, dynamic INTEGER formats, quoted STRING escaping/truncation, narrow integers and CR newlines | One complete recorder/callback request per statement, <=254 characters. Bounded formats; explicit FILE output uses MemoryFiles, a caller-rooted DirectoryFiles or configured WD windows; no live devices or aggregate output. |
| READ | Scalar variables, fields/elements and narrow scalar storage through typed callbacks, JSON batches or TextInput; CR, widths, bases and quoted STRINGs | Capture each target then its formats once; complete-response validation. Chosen text rules; MemoryFiles/DirectoryFiles add explicit text/binary FILE transfers; injected keyboard text and opted-in waiting pipe reads use cooperative generators; no live devices, native parser claim, aggregate targets or POSITION orientation writes. [CONFIG field input](config-field-input.md) validates turn bounds and BOOLEAN flags before any output/cursor publication. |
| ABORT | Bare statement with sticky termination and frame cleanup | Also available in cooperative actions and explicitly registered ABORT_TASK; no motion cancellation or controller restart behavior. |


| Registers and ports | String/position/joint banks, digital/group/analog ports, static GET_VAR/SET_VAR paths, assignment/mode settings and module lookup | Explicit context, disjoint outputs and bounded same-rank ARRAY/missing-data transfers; [compatible record schemas and record prefixes](record-variable-transfers.md) and [explicit-model geometry](kinematic-variable-transfers.md); attached foreign globals and explicit system roots; staged I/O configuration requires host apply; no live acquisition. |
| FILE | OPEN/CLOSE, [CANCEL FILE](file-cancellation.md), text/binary READ/WRITE, byte cursors/counts/status, CHECK_NAME and MOVE_FILE | MemoryFiles or explicit DirectoryFiles root; copy/delete/rename including [wildcard renames](wildcard-rename.md), FILE_LIST formats 0 through 4 with atomic pages and blank timestamps, preflighted RD/FR movement, ATR_UF binary, byte order, EOL and interactive flush; explicit routing without native device behavior. |
| PATH / QUEUE_TYPE | Typed nodes/header, PATHHEADER/PATHDATA spellings, reflowed clauses, append/insert/delete/copy/length; initialized FIFO queues and GET_VAR/SET_VAR logical queue transfers | Default/explicit STD_PTH_NODE schemas canonicalize identically; one-based nodes, explicit queue capacity/rebinding and no native layout claim. |
| Cooperative control | Multiple WHEN handlers/actions, controls, connected global/private USING, [routine-local](routine-local-timers.md) and [borrowed formal timers](formal-timers.md), task pause/resume/stop, TaskRegistry and external callbacks | Deterministic scheduler, event/semaphore/error/lifecycle conditions, EVAL predicates/actions, scan intervals, local lifetimes, suppression actions and typed project linkage; no native interrupts or motion behavior. |
| Task policies and traces | SET_TSK_ATTR, seven source directives, priority-ordered weighted turns, request-origin masks and bounded source checkpoint tracing | Nine checked settings, stable numeric IDs, explicit shift/TP-enable notifications and atomic CLI trace export; capability-only lamp/motion flags; no native CPU timing or preemption. |
| TP program data | 17 management, position, frame/type and comment calls over explicit TeachPrograms, plus listing/load/header metadata integration | Logical records, grouped poses/joints, opaque one-based instruction deletion, access/reject handles and terminal cleanup; no native TP files, execution or motion linkage. |
| TP local registers | 12 numeric/string/grouped position calls with explicit caller bindings in TeachPrograms | Calling KAREL root scope through linked routines and scheduler rename, separate local banks, stored frame/tool metadata and typed JSON; no native caller-stack discovery. |
| XML input | XML_ADDTAG, XML_REMTAG, XML_SCAN, XML_GETDATA, XML_SETVAR over explicit text RO FILEs | Bounded ASCII documents, registered events, text continuation and checked nested scalar leaf updates on user/built-in records; [nested scalar/ARRAY paths](xml-aggregate-paths.md) and BYTE/SHORT leaves; no DTD/entities, XML writing or native parser/status equivalence. |
| Serial attributes | GET_PORT_ATR/SET_PORT_ATR over explicit SerialPorts | Seven checked attributes, canonical context JSON and portable constants; configuration metadata without serial/device effects. |
| Serial FILE streams | Explicit finite/default or opted-in host-fed waiting P1:..P5: RX queues and TX outboxes | Atomic text/binary reads, explicit EOF, close-time RX consumption, appended TX, bounded JSON and exclusive handles. No hardware access, implicit attribute application or native serial timing. See [serial streams](serial-streams.md) and [serial waiting](serial-waiting.md). |
| Virtual devices | MOUNT_DEV, DISMOUNT_DEV, FORMAT_DEV, PURGE_DEV, VOL_SPACE, DOSFILE_INF over DeviceFiles | Explicit memory-backed volumes, mount/closed-file guards, byte quotas/reclamation and supplied metadata; no host drive or native device operations. |
| Robot model | MIRROR, extended pose metadata, JOINT2POS/POS2JOINT, IN_RANGE/J_IN_RANGE and CHECK_EPOS | Explicit right-handed reflection convention, supplied callbacks/limits or standard-DH models with bounded IK, explicit groups/frames/tools and external joints; no inferred robot context or native reachability claim. |

See the [offline service matrix and guide](offline-services.md) for the complete
contracts and remaining gaps; [portable projects](portable-projects.md) covers
the project implementation and setup.
The [initialization query guide](initialization-queries.md) covers whole builtin
records, partial leaves, grouped storage and retained container exclusions.
[Control notifications](control-notifications.md) covers 0.81.0 semaphores, error
records, runtime-failure observation and explicit powerup recovery.
The [error history guide](error-history.md) adds ERR_DATA traversal, latest lookup,
checked outputs and persisted message/timestamp metadata.
The [position check guide](position-checks.md) adds CHECK_EPOS with explicit
frame/tool operands, caller-rooted groups and model/adapter reachability.
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
The [task attribute guide](task-attributes.md) covers applied settings, directives,
cooperative scheduling, mask effects and CLI trace export.
The [TP program guide](teach-programs.md) covers the shared logical store,
all 17 calls, permissions, JSON and retained native boundaries.
The [TP local register guide](teach-registers.md) covers twelve additional calls,
explicit caller bindings, independent banks and copy/replay behavior.
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
See [Pythonic USING](pythonic-using.md) and [captured selectors](using-selectors.md)
for lexical lookup, indexed record storage, built-in fields and handler references.
See [PATH declarations](path-declarations.md) for clause spellings, predefined
record layouts, interfaces, dynamic creation and persistence.
See [TYPE aliases](type-aliases.md) for transparent names, identity and bounded
STRING routine interfaces.
See [external types](external-types.md) for full FROM definitions, owner-source
validation, reexports and physical linkage diagnostics.
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
bounded or [inherited-capacity STRING elements](inherited-string-array-results.md), prior
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
aliases, retain the declared output identity after checked source conversion.
Inline `ARRAY OF ARRAY` remains blocked. Selected named subarrays may return as
independent anonymous values under [source schema rules](array-schema-conversions.md).
Omitted direct anonymous STRING result capacities inherit concrete source data.
Named STRUCTURE elements may
contain supported STRING fields and named arrays under the existing recursive
copy rules.

For STRING elements, `ROUTINE make: ARRAY OF STRING[4]` prepares capacity4
after validating the actual source capacity and ASCII contents. Explicit source
conversion may widen or right-truncate values into bounded capacities in 1..254.
Prior named rows/planes remain supported. An `ARRAY OF STRING` reference formal
retains caller capacity; assignment through that generic receiver uses its
actual schema. An omitted anonymous result capacity inherits concrete source
capacity before any separate downstream conversion.

Empty initialized elements are valid; missing markers are preserved. Known
non-ASCII or malformed oversized host values fail before result assignment. See the authored
[STRING ARRAY example](../examples/string_array_functions.kl). Direct STRING
results follow the [Pythonic STRING contract](pythonic-strings.md); this ARRAY subset is an offline
composition of the documented array and bounded-string rules, without native
compiler or controller validation.

Return copies complete before local frames unwind and retain record names,
nested array identities/shapes, STRING field capacities and joint widths. All
known scalar leaves are validated, while missing markers remain missing; see
[partial aggregate values](partial-aggregate-values.md). Copies are bounded to
32767 scalar leaves and 64 schema levels, including nested fields/joint axes.
Failure leaves the destination intact while retaining earlier independent effects.

Use a bare zero-argument function name or an explicit call. Results compose in
grouping, compatible user-routine arguments, direct RETURN forwarding and
ARRAY_LEN returning the first dimension. Explicit calls or groups support returned aggregate
subscripts and fields. Destination type and length must
match under the generic copy contract. Separate [numeric ARRAY conversions](numeric-arrays.md)
add checked integral narrowing and REAL promotion; resizing and nominal identity
erasure remain unavailable.
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
root to translate and check them. The intentionally unsupported motion-local-handler source
must be rejected and is not executed.

## Evidence boundaries

The public tests use authored source and synthetic fixtures. They check parser,
emitter, execution, ownership, effects, diagnostics and failure paths offline.
They do not authenticate native compiler acceptance, original source recovery,
binary equality, controller ABI or robot behavior.

Manual PDFs, private corpora, local audit results and controller files are not
distributed here. Use the [reference descriptions](references.md) and the
documents available for your controller release when evaluating source semantics.

Dynamic creation, renaming and typed BYNAME routine aliases follow the
[dynamic variable contract](dynamic-variables.md), including saved creation policy
and explicit namespace guards. Compiled names and native memory pools stay fixed.

See [diagnostics](diagnostics.md) for event selection and logical stack queries,
and [KCL commands](kcl-commands.md) for explicit scripted acceptance/completion.

CALL_PROG/CALL_PROGLIN support attached cooperative KAREL programs through
[program calls](program-calls.md). [Logical group ownership](group-locks.md) adds
explicit LOCK_GROUP/UNLOCK_GROUP banks, partial acquisition and terminal cleanup.
An opted-in bank also applies [root source directive locks](directive-group-locks.md)
atomically before body execution. A separate `callee_scopes=True` option adds
[scoped module grants](scoped-group-locks.md) with return/stop/error cleanup;
root-only behavior remains the default.
[Stored source translation](source-translations.md) adds TRANSLATE over explicit
ordinary file stores, producing Python and optional listings without execution.
[Wildcard files](wildcard-file-operations.md) add nonrecursive star COPY/DELETE
batches, portable full-stem templates and backend-specific publication guarantees.
[Pipe wildcard batches](pipe-wildcard-files.md) additionally route configured
plain pipe names without implicit configuration or circular truncation.

The six DAQ calls follow the [data-acquisition contract](data-acquisition.md):
bounded typed pipes, binary PIP readers, reference-counted activation, snapshot
views, ring overflow, synchronous file batches and validated saved state.

The six [PC data/event calls](pc-exchange.md) support big-endian typed BYTE
buffers, named scalar insertion, captured read-only sends and bounded persisted
outboxes. Custom payloads use the explicit raw packet mode; no transport is opened.

[Offline communications](communications.md) covers MSG_CONNECT/MSG_DISCO/MSG_PING,
socket-tag mount forms and PIPE_CONFIG, with scripted duplex FILE buffers,
circular plain PIP histories, distinct DAQ names and bounded saved state.

[Mobile-message calls](remote-messages.md) cover RMCN_ALERT/RMCN_SEND and
QUEUE_ATTACH with explicit alert defaults, bounded XML outboxes, deferred
attachment collection, MD retention and supplied ZDT types. SET_VAR has no
implicit send trigger; no native delivery or host-filesystem deletion occurs.

[Portable TP archives](program-archives.md) support SAVE/LOAD/CLEAR and
PROG_BACKUP/PROG_RESTORE/PROG_CLEAR, with typed program data, explicit bounded
dependency graphs, selection/protection/binding guards and complete batch
preflight. [Variable archives](variable-archives.md) add portable VR forms,
variable-only recursive batches and SAVE_DRAM save points, preserving typed
partial data and ordinary aliases. [Mixed ALLTYPE batches](mixed-archives.md)
combine TP/VR graphs and preflight both stores using hashed manifests. Native
PC/VR/IO binaries, code unloading and
automatic native flash/power-up behavior remain unavailable.

[Joint width conversions](joint-width-conversions.md) accept complete same-kind
joint values across source assignments, arguments and RETURN with zero padding or
zero-only narrowing. Exact bare aliases, linked declarations and whole arrays
retain their existing contracts. [Question FILE wildcards](question-file-wildcards.md)
extend final-basename source matching across COPY/DELETE/RENAME/MOVE without
changing destination star substitution, backend isolation or preflight guarantees.

[Dynamic SELECT labels](dynamic-select.md) capture the selector first, evaluate
all typed case expressions once in source order, and dispatch after complete
validation. [Numeric GET_VAR/SET_VAR](numeric-variable-transfers.md) adds checked
integral-family/integral-to-REAL scalars and same-rank ARRAY prefixes. [XML built-in
record roots](xml-record-roots.md) retain atomic leaf updates, readonly POSITION
orientation, CONFIG bounds and explicit context without geometry inference.

[Non-ARRAY positional GET_VAR/SET_VAR](positional-variable-transfers.md) reuses
checked Cartesian and zero-only joint-width conversions with complete inputs.
[Synchronous source program calls](synchronous-program-calls.md) use private bodies
with caller-owned state; project/cooperative behavior and legacy guards remain.
[Explicit 16-bit rasters](vision-16bit-images.md) preserve supplied direct-color
samples in PNG, with unchanged byte quotas and eight-bit palette behavior.
