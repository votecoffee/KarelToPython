# Feature guide

For setup and a first conversion, see the [README](../README.md).
Current limitations are in the [remaining support inventory](unsupported.md).

## Translation mode

**Pythonic mode is the default.** Ordinary decimals, rounded arithmetic and
Python math functions work without the former exact binary32 restriction.
For an explicit choice, use `translate(source, mode="pythonic")` or:

```sh
python -m karel2py examples/pythonic_numeric.kl --mode pythonic --check
```

`ROUND` uses Python's ties-to-even rule, so `ROUND(2.5)` returns 2. REAL values
use Python `float`; structural and initialization checks remain. **Strict mode
is a future milestone**; its previous exactness work is preserved internally.
See the [equivalence matrix and mode roadmap](numeric-modes.md).

`CNV_CNF_STRG` formats CONFIG values using explicitly supplied per-group field
profiles. `CNV_STR_CONF` with an explicit group reads the selected fields and
fills omitted fields with FALSE or zero. Profiles persist in service-context
JSON and work with generated-script `--context` input. See
[group CONFIG text](group-config-text.md).

Pythonic `WRITE` supports mixed text, signed numbers, REAL formatting and `CR`
newlines, for example `WRITE('value=',value::0::3,CR)`. Requests are recorded or
sent to a supplied callback. See the [text output guide](pythonic-output.md).

STRING functions and writable value arguments are supported too. `STRING`
results default to 254 characters; `STRING[n]` results truncate at the declared
capacity. Parenthesized STRING arguments use private storage. See the
[STRING guide](pythonic-strings.md).

Functions compose in operators, argument lists, array subscripts, conversions
and FOR bounds. Pythonic mode evaluates ordinary operands and arguments left
to right, short circuits BOOLEAN `AND`/`OR`, and captures assignment values before
resolving targets. See the [evaluation order guide](evaluation-order.md)
for reference aliasing and compatibility changes.

Whole ARRAY value arguments use private checked copies. ARRAY results can be
passed onward, forwarded by RETURN, or read directly with `make()[1]`.
See the [ARRAY values guide](pythonic-arrays.md) for ownership and limits.
[Numeric ARRAY conversions](numeric-arrays.md) add checked integral narrowing
and REAL promotion across assignment, private arguments and RETURN, preserving
missing data and shape. [Named and component ARRAY conversions](named-array-conversions.md)
now extend numeric, Cartesian, joint-width and explicit-model changes to named
outer types and nested components, retaining private arguments and receiver
schemas. [Source ARRAY schema conversions](array-schema-conversions.md)
also support same-element named copies, bounded STRING capacities and flat/nested
layouts with matching logical dimensions; compatible generic arguments still
borrow caller storage. [Source STRUCTURE conversions](record-schema-conversions.md)
also map matching field names across record types, including nested records and
record ARRAYs, checked numeric/STRING fields and context-free geometry. Receiver
schemas remain intact and converted arguments stay private.
[Model-backed record conversions](kinematic-records.md) now extend explicit
joint/Cartesian models through nested fields and record ARRAYs, with complete
data preflight and staged output before publication.
Resource-free aggregate copies now preserve missing scalar fields across
assignments, private arguments and returns. Reads and geometry still reject
unavailable components; see [partial aggregate values](partial-aggregate-values.md).
Results also support named types and fixed or wildcard matrix/cube dimensions.
`ARRAY_LEN(array)` returns the first dimension, like Python `len`.
`ARRAY_LEN(array, dimension)` selects a one-based dimension. Both forms accept
selected FILE rows and planes without copying descriptors. See
[ARRAY result shapes](array-result-shapes.md).

WRITE formats accept INTEGER expressions, including function calls. Quoted
STRING fields handle apostrophes and truncation; REAL-to-text conversion supports
fixed and scientific notation. See [Pythonic text formats](text-formats.md)
for the chosen conventions, evaluation order and bounds.

SUB_STR clips at the source end and permits zero counts; INDEX accepts empty
searches. See [STRING operations](string-operations.md) for bounded slicing,
one-based positions and character checks.

Global-counter FOR loops can call helpers when transitive write checks protect
the counters. Read-only counter references are supported, and initialized
counters clear on RETURN, ABORT and errors. See [Pythonic FOR](pythonic-for.md)
for cleanup, argument passing and remaining restrictions.

USING supports nested lexical scopes and dotted, indexed or grouped record
storage, including built-in records. Selectors capture references once per entry;
index changes preserve the selected fields. Inner fields take precedence and
handler callbacks retain their enclosing references. See [Pythonic USING](pythonic-using.md)
and [captured selectors](using-selectors.md) for lookup and retained guards.

TYPE aliases provide alternate names for supported types and keep original
aggregate identities and capacities. Bounded STRING alias parameters accept
checked references or private value copies. See [TYPE aliases](type-aliases.md).
External types retain their complete `TYPE name FROM owner = definition` layout.
Linked projects check owner sources, exact schemas and reexport chains before
allocating globals. Shared variables and external routines use those checked
types. See [external types](external-types.md) for standalone behavior and
source-located linkage errors.

VEC constructs independent VECTOR values from numeric components. Unary signs
and left-associated cross/dot chains support composed calculations such as
`SQRT(v@v)`. See [Pythonic vector expressions](pythonic-vectors.md).

`POS(x,y,z,w,p,r,c)` constructs an independent XYZWPR with explicit CONFIG data
and checked coordinate and angle bounds. Three trailing axis values produce
XYZWPREXT. See [POS construction](pos-construction.md).
CONFIG text parsing and complete formatting use an explicit offline grammar and
portable failure status. See [CONFIG text](config-text.md).
Explicit XYZWPR poses also support `a:b` composition and `INV(a)` inversion
with a documented offline angle convention. See [frame transforms](frame-transforms.md).
`FRAME` builds a right-handed frame from three or four explicit points.
See [frame construction](frame-construction.md) for spacing and origin rules.
Whole assignments convert between XYZWPR and POSITION, initializing protected
orientation vectors from explicit poses. See [POSITION conversions](position-conversions.md).
Composition, INV and FRAME also accept POSITION and mixed POSITION/XYZWPR
operands, with direct matrix results whenever POSITION is involved.
See [POSITION geometry](position-geometry.md).
`pose:vector` transforms a local VECTOR point with rotation and translation,
returning an independent VECTOR. Cartesian and model-backed joint frames use the
same rule; see [VECTOR frame transforms](vector-frames.md).
APPROACH and ORIENT return independent VECTOR copies of a pose's positive Z and
Y axes. See [pose axis queries](position-axes.md).
`UNINIT` queries whole builtin records, including partially initialized poses
and vectors, without changing storage. See [initialization queries](initialization-queries.md)
for the portable leaf rule and retained container exclusions.
Approximate position comparison (`>=<`) uses explicit host-supplied distance,
angle and CONFIG tolerances. See [position comparisons](position-comparisons.md).
Boolean `WAIT FOR` rechecks its condition with host yields and the ordinary
execution step budget. See [Boolean waits](boolean-waits.md).

CNV_STR_TIME and CNV_TIME_STR convert supplied packed date/time values and
complete English text, with checked calendars and two-second precision.
See [time text](time-text.md) for the format and signed bit representation.

GET_USEC_TIM and GET_USEC_SUB measure short elapsed intervals using a host
monotonic clock or an injected test clock. See [microsecond timers](microsecond-timers.md)
for the portable rollover model and repeatable execution.

GET_REG, SET_INT_REG and SET_REAL_REG operate on an explicit in-memory numeric
register bank. See [offline numeric registers](numeric-registers.md) for
initial state, portable statuses and the generated script's JSON context.

ENVIRONMENT, COMMENT and ALPHABETIZE directives are retained as checked metadata
alongside NOLOCKGROUP. Environment requirements are recorded without loading
definitions or enabling extra facilities. Pythonic COMMENT preserves up to 254
decoded ASCII characters; reports identify comments exceeding the reference's
16-character native attribute limit. See [source directives](source-directives.md).
Seven task directives also initialize portable priority, time-slice and request
policies; see [task attributes and traces](task-attributes.md).
Nine additional source policies cover an applied DEFGROUP default, CRTDEVICE
request labels, uninitialized defaults and retained storage/lock/stack/delay
intent. An explicitly configured GroupLocks bank can opt into atomic root
directive acquisition; nested callee directives are deferred by default. See
[directive group locks](directive-group-locks.md). Policies are exposed
through `Program.source_settings`; see
[source directive policies](source-directives.md#additional-source-policies).
An additional `callee_scopes=True` setting acquires module-required groups for
called programs and routines, then releases that scope's additional grants on
return. Caller ownership survives; see [scoped group locks](scoped-group-locks.md).
%INCLUDE expands supplied declaration/routine/body fragments, with nested
lookup, explicit include directories/device mappings, physical-source diagnostics
and input-file protection across CLI and linked projects. See
[source includes](includes.md).
Stored-source `TRANSLATE` can generate sibling Python and optional listings over
an explicitly supplied file backend. It preserves source and never loads or runs
the products; see [source translations](source-translations.md).
COPY_FILE and DELETE_FILE accept bounded, nonrecursive star batches with checked
destination templates and preflight; see [wildcard files](wildcard-file-operations.md).
The same operations support configured plain pipes with finite snapshots and
complete destination-capacity checks; see [pipe wildcard files](pipe-wildcard-files.md).
Labels and GOTO can remain inside an active FOR loop or exit it with counter
cleanup. Direct entry into a new FOR scope stays blocked; see [FOR jumps](for-jumps.md).
FOR counters can also capture writable INTEGER record fields, ARRAY elements or
USING fields once per entry, with conservative aggregate-write protection; see
[reference counters](reference-for-counters.md).
VECTOR values can act as translation offsets, with negation through INV and
checked FRAME point inputs with a pose origin or explicit CONFIG. See
[VECTOR translation frames](vector-translation-frames.md).
Finite `P1:` through `P5:` FILE endpoints use explicitly supplied RX/TX data,
including text and binary transfers; see [serial streams](serial-streams.md).
Computed USING selectors capture independent record temporaries once, with no
copy-back; see [computed USING](computed-using.md). Isolated integral fields
in those captures can serve as [private FOR counters](private-using-counters.md),
with whole-root alias protection and cleanup. [Private connected timers](private-using-timers.md)
retain captured INTEGER leaves across lexical exit and pause, with explicit
disconnect and terminal/invocation cleanup. [Routine-local timers](routine-local-timers.md)
accept fresh local INTEGER leaves, retain them across pause and release each
connection when its defining routine frame unwinds. [Borrowed parameter timers](formal-timers.md)
use callee frame ownership, shared-context duplicate checks and transitive counter
write guards; exact bare actuals update caller data while value actuals stay private.
[Scalar BYTE/SHORT](scalar-narrow.md)
add typed variables, aliases and routine interfaces with checked private numeric
conversions. [Wildcard renames](wildcard-rename.md) move closed files or plain
pipe configurations after batch preflight, without overwrite.
[Scalar SELECT](scalar-select.md) now branches on finite numbers, BOOLEANs
and ASCII strings, with one selector evaluation and first-match behavior.
[Dynamic narrow variables](dynamic-narrow.md) add BYTE/SHORT creation and
exact named routine references. [Virtual-volume renames](cross-volume-rename.md)
preflight complete destination capacity and retained source bytes within one
configured DeviceFiles bank.
[BYTE/SHORT counters](narrow-for.md) now retain checked narrow domains and
type-specific cleanup. [Cartesian routine conversions](cartesian-interfaces.md)
use independent values when POSITION, XYZWPR and XYZWPREXT representations differ.
[STRING-array results](inherited-string-array-results.md) can inherit the
returned storage's concrete element capacity without truncation or invented defaults.
[Chained ARRAY indexes](chained-array-indexes.md) support complete forms such as
`items[i][j]` and `make()[i][j]` under the existing comma-index capture rules.
[Joint routine conversions](kinematic-interfaces.md) use explicitly supplied
models/adapters and private values at source argument/RETURN boundaries.
[Palette images](vision-palette-images.md) retain supplied indices and RGBA
colors, exporting indexed PNG and alpha-preserving BMP without image acquisition.
Serial streams can opt
into cooperative reads fed by the host, with explicit EOF and cancellation;
see [serial waiting](serial-waiting.md). Supplied vision images now retain
grayscale/RGB alpha in PNG and 32-bit BMP exports; see [alpha images](vision-alpha-images.md).
Linked projects accept program-qualified ARRAY shapes, so modules can specialize
the same variable name independently. See [project ARRAY shapes](project-array-shapes.md)
for API and CLI examples, including validation without executing source.
PATH helpers include portable NODE_SIZE and budgeted view-line/plane intersections
with staged append behavior; see [PATH geometry](path-geometry.md).
Five XML input calls provide registered-tag scanning, chunked text and attributes,
and checked structure updates over explicit FILE backends. Dotted attributes can
update individual JOINTPOS axes, including inside arrays. XML FILE calls charge
for snapshot capture and later comparisons with the original buffer. XML_SETVAR
also charges for the full target record before staging. [Publication checks](xml-publication.md)
preserve callback edits and reject changed target/status bindings before a staged
update is published. A `{uri}local` tag registration
enables matching by namespace URI. See
[XML input](xml-input.md). GET_PORT_ATR/SET_PORT_ATR use a separate persisted
offline serial-attribute bank; see [serial attributes](serial-attributes.md).
Six device/storage calls share explicit virtual DeviceFiles volumes, including
mount state, byte quotas, obsolete-storage reclamation, labels and supplied device
information. These operations affect memory-backed data only; see
[virtual devices](virtual-devices.md).
Rooted and virtual FILE backends accept controller-style paths such as
`RD:\jobs\part.dat` through their explicit device mappings. Exact rooted
access rejects symlink and junction components. Hard links to an open rooted
file share its busy status. Generated scripts and linked projects accept repeatable `--filesystem-device RD=ram` mappings under
`--filesystem-root`.
`FILE_LIST` supports name, extension, complete-name and portable 40-column size
formats, with whole-page validation before outputs change. Pair
`--filesystem-timestamps` with `--filesystem-root` to include UTC modification
times for closed files. See
[file listings](file-listing.md).
CREATE_VAR, RENAME_VAR and RENAME_VARS manage explicit variable namespaces;
BYNAME passes checked named aliases into typed routines, including linked calls
and cooperative pause/resume. [Dynamic collections](dynamic-collections.md)
now add root PATH/QUEUE_TYPE creation and [collection arrays](collection-arrays.md), checked header/descriptor reservations,
renaming and saved-state replay. [Dynamic FILE descriptors](dynamic-files.md)
now add typed file I/O/cancellation aliases and explicit closed-descriptor JSON;
loading creates a fresh closed handle while backend data uses existing snapshots.
See [dynamic variables](dynamic-variables.md).
CHECK_STACK, SET_DEBUG and SET_DB_EVENT use explicit offline diagnostics with
bounded event history and configurable logical stack estimates. KCL,
KCL_NO_WAIT and KCL_STATUS use a command channel with scripted replies, optional
task, file, variable, device, dictionary, program and environment dispatch, completion waits
and saved results. Scheduled scripted delays and task-state waits honor timed
condition scans.
See [diagnostics](diagnostics.md)
and [KCL commands](kcl-commands.md) for setup and execution boundaries.

Ten pendant calls now use an explicit headless display model: opaque link/menu
requests, configured language selection, screen/window definitions, attachments,
activation and cursor positioning. WD:name FILE output updates character grids
with scrolling and common or per-handle cursors. Closed-window state persists
through context JSON. See [pendant display](pendant-display.md).

```sh
python -m karel2py examples/window_display.kl -o window_display.py
python window_display.py --context examples/window_display.services.initial.json --state-out window-state.json
```

Generated programs accept numeric banks from `--context` or a separate
`--registers` file; an explicit register file overrides the context bank for all
numeric services.

Fifty-three [vision calls](vision-results.md) consume supplied completed
runs, transfer registers, edit parameters and retain cursors in context JSON.
[Image/device services](vision-image-services.md) add supplied captures,
PNG/BMP export, reader output, view-line PATHs and logical camera/calibration/
display/LED state. [Legacy tracking](vision-tracking.md) adds timed queues,
allocation receipts, VT results/lookups, supplied point maps and a local
notification outbox. [VT line queues](vt-queues.md) add put/get/acknowledge,
partial PATH reads/edits, flags, weighted routing and explicit time/flow estimates.
Scheduled waits in both queue models honor timed condition scans between polls.
An optional [VT tray-cell bank](vt-trays.md) expands supplied local poses into
independent workpieces, with per-cell models, routing and allocation receipts.
These services perform no image processing, hardware I/O or network delivery.

```sh
python -m karel2py examples/vision_results.kl -o vision_results.py
python vision_results.py --context examples/vision_results.services.initial.json --state-out vision-state.json
```

Six [logical controller services](controller-services.md) add group-control
queries, stopped-label cancellation, stored perches, scripted reset results and
background slots for attached cooperative KAREL tasks. Explicit panel I/O banks
include OPIN/OPOUT and TPIN/TPOUT, including address zero.

The [FTX form service](forms.md) adds DISCTRL_FORM with typed editing,
enumerations, help/choice overlays, sequential tree groups and injected navigation.
Complete form fragments can be concatenated through dictionary references;
`.tree` explicitly inherits the preceding group. Layout uses headless windows.

Four [list/table controls](table-controls.md) add resident-list paging and
array-backed typed table edits, including port cells, range checks and explicit
session cancellation. They use injected keys and headless windows; no GUI opens.

Keyboard input now uses explicitly supplied key events through READ_KB, with
editing, masks, timeouts, per-file history and PUSH/POP read suspension. Combined
window/keyboard FILEs support echo and ordinary output. Alphanumeric entry and
dictionary-backed subwindow/pull-up menus share that headless event model. See
[keyboard input](keyboard-input.md) for context JSON and runnable CLI examples.
Interrupted tasks release their own keyboard suspension tokens.
Ordinary typed FILE READ now uses the same injected keyboard service, with
submitted lines, numeric/quoted formats, buffered suffixes and atomic outputs;
see [keyboard FILE reads](keyboard-file-read.md).
[Raw keyboard fields](keyboard-raw-read.md) add bounded PASSALL STRINGs,
fixed-width numeric/BOOLEAN text and printable delimiters, using the same
injected events and lifetime guards.

Twelve dynamic-display calls watch static scalar/enum variables and supplied
ports, updating logical window fields at deterministic checkpoint intervals.
Cancellation matches storage identity and clears fixed-width fields while
preserving ordinary FILE cursors. Set `cancel_on_interrupt` to release a task's
watches when it stops, aborts or fails. Cancel retained bindings before saving context.
Polls validate captured data and all due windows before painting. Missing labels
show stars; malformed source data shows question marks and can recover when repaired.
See [dynamic displays](dynamic-displays.md).

Seven dictionary calls now load supplied text catalogs, read numbered/named
elements, format static variable values and write to logical windows. Nested
elements, language selection, truncation statuses and atomic cursor/clear
controls have offline models. See [text dictionaries](text-dictionaries.md)
for the supported source grammar and CLI examples.

CALL_PROG/CALL_PROGLIN run attached KAREL main bodies in the calling task with
separate cursors and shared module data. See [program calls](program-calls.md).
RUN_TASK starts a registered task or resumes its paused continuation.
See [task requests](task-and-file-extensions.md#run_task-entry-and-continuation).
LOCK_GROUP/UNLOCK_GROUP use configured logical ownership with immediate partial
results or opt-in bounded waits for a complete mask. See [group locks](group-locks.md).
All six DAQ calls use explicit typed acquisition pipes with binary FILE readers,
budgeted snapshot views, overflow tracking and batch output to supplied file
backends. Writes charge for record preparation and pending batch bytes before
encoding. Named DAQ registration/writes also accept selected PATH-node/header
data and ordinary ARRAY rows/planes, with original-cell capture and source/status
binding checks through record preparation and file flushing. See
[data acquisition](data-acquisition.md).
Four ADD_*PC builders create checked typed BYTE buffers; SEND_DATAPC and
SEND_EVENTPC publish to an explicit bounded offline outbox, with typed and raw
payload modes. Packet and attachment inputs check their limits before capturing
the selected ARRAY cells. See [PC data and events](pc-exchange.md).
[Named PC data batches](pc-named-data.md) now append complete ARRAY/record/
joint values and BYTE/SHORT/BOOLEAN scalars through ADD_BYNAMEPC, retaining
existing tags, a single final marker and atomic buffer/index publication.
Selected PATH nodes, node fields and headers use the same ordinary data rules;
whole PATH resources remain excluded. Captured builder/index/status bindings
are checked before publication, including SEND_DATAPC status at preparation.
Named ARRAY rows and planes now use the same packet items, with static comma
or chained indexes and selected-data copying after capacity/budget admission.
[Display value paths](display-named-rows.md) now share chained static indexes
for dictionary formatting and form fields, plus live ARRAY rows for form choices,
function labels and table backing columns. Original-cell overlap and retained-row
length checks protect those headless editing sessions.
[KCL data selections](kcl-data-prefixes.md) now copy exact ordinary ARRAY
rows/planes into detached variables or owned paused locals, with chained indexes,
selected-row listings and rechecked original-cell ownership before publication.
[KCL logical copies](kcl-collection-copies.md) also support exact detached
PATH/queue values, whole banks and complete indexed/named components. They charge
both logical snapshots, preserve independent data and reset copied queue buffer links.
[Collection rows and planes](kcl-collection-prefixes.md) now copy and display
through static comma/chained selections, with complete containing-bank checks and
original receiver-cell protection across preparation checkpoints.
[Paused local collection copies](kcl-local-collections.md) now edit owned
PATH/queue locals, banks and rows from exact local, global or borrowed sources,
with retained frame checks, whole-root protection and local SHOW inspection.
[Local PATH data edits](kcl-local-path-data.md) now add header/node literals,
named record/row copies, pose values and joint/CONFIG fields. A private containing
PATH validates before publication into the original selected live cells.
MSG_CONNECT/MSG_DISCO/MSG_PING use configured offline socket buffers and host
results; PIPE_CONFIG provides circular PIP FILE histories. Both support ordinary
FILE I/O and saved state. Socket FILEs can opt in to cooperative input and output
waits. See [communications](communications.md).
Plain pipes also support explicit wait/snapshot and overflow attributes.
Waiting reads follow configured cursor adjustments from circular overwrites
between polls, and byte capture checks for history changes. See
[pipe attributes](pipe-attributes.md).
[Pipe file management](pipe-file-management.md) adds finite snapshot copies,
configuration-preserving rename, deletion and listing over explicit PIP names.
RMCN_ALERT/RMCN_SEND and QUEUE_ATTACH provide bounded offline mobile-message
outboxes and deferred ZDT attachment selection, with validated XML publication,
controller-style FILE names, MD retention and explicit host collection. XML
publication budgets capture, validation and hex expansion, then checks that the
source still matches before deletion. See
[mobile messages and attachments](remote-messages.md).
SAVE/LOAD/CLEAR and recursive PROG_BACKUP/PROG_RESTORE/PROG_CLEAR support
portable TP data archives, explicit dependency graphs, guarded batch operations
and saved-state replay. TP transfers charge the execution budget before copying
input bytes or publishing staged files. See [program archives](program-archives.md).
Portable VR forms also save/load/reset owned KAREL globals and explicit variable
namespaces, including recursive variable-only batches. SAVE_DRAM records guarded
offline save points; see [variable archives](variable-archives.md).
[Mixed ALLTYPE batches](mixed-archives.md) combine TP and VR dependencies,
validate hashed member manifests, and preflight backup/restore/clear across both
stores before committing changes. VR and mixed transfers charge the execution
budget before copying input files or publishing a staged batch.

[Model-backed variable transfers](kinematic-variable-transfers.md) now apply
explicit joint/Cartesian models across GET_VAR/SET_VAR values, same-rank ARRAY
prefixes and nested record fields. The full batch is charged against the step
budget before invoking adapters. Private results preserve data, entry and cache
outputs on failure.

[Bounded CONFIG input](config-field-input.md) now reads turn integers and
BOOLEAN flags through callbacks and text/binary FILEs, including captured nested
fields, routine formals and private USING values. The complete response is checked
before destination or FILE cursor publication.

READ accepts typed scalar input through an explicit host callback. Generated
scripts can use JSON response batches with `--read-values` or ASCII text with
`--read-text`, field widths/bases/quotes and explicit CR line control. The text
parser locates records as the cursor visits them. See
[READ formats](read-formats.md), [text input](text-input.md) and
[Pythonic input](pythonic-read.md) for capture order, validation and failure behavior.

## Offline services and task control

Registers, ports and program globals share an explicit context with typed JSON
save/load. FILE operations can use memory or a caller-selected directory. Finite
and cooperative socket, serial and pipe READs charge input bytes before capture.
Binary READ plans all widths up front and copies only the requested fields.
FILE WRITE budgets payload bytes before assembly and retains one payload across
serial and socket waits. Rooted OPEN and flush charge for the full file image.
An interactive write publishes the disk image before updating its buffer.
Typed PATH and QUEUE_TYPE collections work offline. APPEND_NODE and INSERT_NODE can
take complete node values, with a final `TRUE` argument to convert compatible
NODEDATA layouts. Node edits charge seed capture and node allocation before
copying or allocating the corresponding data. Insertions and deletions also
charge the shifted nodes and verify the receiver. `COPY_PATH` charges the header
and selected nodes before capturing them and checks that the source and
destination storage still match before publication. Its final `TRUE` argument also enables
conversion between compatible PATH schemas. These opted-in edits and copies can
convert joint and Cartesian fields using the calling task's supplied robot model.
[Scalar PATH values](scalar-collection-values.md) also convert compatible
layouts at assignments, private arguments and returns.
[PATH arrays](collection-source-values.md) apply these conversions to whole
banks and selected rows or planes with matching component dimensions.
[GET_VAR and SET_VAR](path-transfers.md) also convert compatible PATH
layouts while retaining their checked status and cache behavior.
Queue operations charge the FIFO snapshot and backing slots before staging.
COPY_QUEUE also charges the output array when it returns a page. PATH declarations accept PATHHEADER
and its PATHDATA compatibility spelling. Predefined DISP_DAT_T and portable
STD_PTH_NODE records work in declarations, routine interfaces, CREATE_VAR and
saved state. See [PATH declarations](path-declarations.md). A deterministic scheduler handles
events, timers, delays and task pause/continue/stop. A scheduled source DELAY can
wake for explicit positive [condition scan intervals](handler-priority-and-system-poses.md#handler-options).
KCL can change the next wake of a parked delay by enabling or disabling a timed
condition. Source projects link typed external routines and imported globals.
A configurable standard-DH
robot model provides forward/inverse math, external joints and bounded
reachability checks. Source inverse and reachability searches charge the
execution budget per model evaluation. Extended-pose comparisons use explicit
axis tolerances.

```sh
python -m karel2py examples/offline_services.kl -o services.py
python services.py --context examples/offline_services.services.initial.json
```

Counting semaphores, ERROR/POWERUP conditions and NOPAUSE/NOABORT/NOMESSAGE
actions are also supported. Runtime failures notify handlers while preserving
the exception. POST_ERR_L adds named portable severities and task-local scope.
Task pause/abort requests honor handlers across linked calls. Scheduled semaphore
waits can park until a grant, timeout or timed condition scan. FILE reads support
capacity-sized ATR_FIELD strings and custom record terminators. See
[control notifications](control-notifications.md) and
[task and file extensions](task-and-file-extensions.md).

Indirect port values, simulated inputs, port/register comments and supplied
teach-pendant CALL arguments share that context too. See
[I/O and CALL parameters](io-and-call-parameters.md) for explicit port-type
mapping, conversions, persistence and linked-task argument scope.

CURPOS/CURJPOS read supplied current robot snapshots or model-derived Cartesian
state, with explicit groups and mask outputs. CURR_PROG reports the executing
module. See [current robot state](current-robot-state.md) for host updates,
frame/tool handling, joint padding and persistence.

Padded joint values now compose across current queries, registers, model
conversions and range checks. Limits-only contexts can persist, and loaded-model
frame/tool updates remain consistent across queries and save/load. See
[joint interoperability](joint-interoperability.md).

POS_REG_TYPE reports stored representation and axis width. CLR_POS_REG clears
the caller's group by default, or takes an explicit group with zero selecting
all groups. Register comments are retained. CLR_PORT_SIM removes a logical
simulation flag while retaining the last supplied value. See
[register lifecycle](register-lifecycle.md) for examples and statuses.

GET_TIME and SET_TIME use an explicit offline CalendarClock, frozen or advanced
by a supplied elapsed-time adapter. Complete calendar snapshots persist through
context JSON. See [calendar time](calendar-clock.md).

GET_TSK_INFO inspects explicitly registered tasks by name or number, including
live state, active linked routines, checkpoints and supplied attributes. See
[task inspection](task-inspection.md) and its runnable two-task project.
SET_TSK_NAME and host task rename APIs retain numeric task order, paused/waiting
execution and scheduler metadata; see [task renaming](task-renaming.md).
SET_TSK_ATTR updates nine checked settings, with cooperative scheduling, request
masks and bounded checkpoint traces. The project CLI supports `--trace-out` for
atomic trace JSON export, including partial traces on failure; see
[task attributes](task-attributes.md).
Seventeen TP program calls share an explicit logical TeachPrograms store for
program management, grouped positions, frame/tool metadata, comments and opaque
instruction deletion. Values and selection persist in context JSON; native TP
parsing/execution remains outside this store. See [TP program data](teach-programs.md).
Twelve TP caller-local register calls add separate numeric, string and grouped
position banks through explicit KAREL-root to TP-program bindings. Linked calls,
copying, pause/resume and JSON replay retain that scope; see
[TP local registers](teach-registers.md).

LOAD_STATUS checks attached code and any known global initialization.
GET_ATTR_PRG/SET_ATTR_PRG read explicit program metadata and update owner, comment
and source metadata with activity guards. See [program metadata](program-metadata.md)
for supplied snapshots, portable identifiers/statuses and the CLI example.

Seventeen remote register/comment/port procedures use explicit offline PeerBanks,
including numeric/string values, independent comments and simulation flags.
Peer banks persist in context JSON and remain independent of local banks. See
[remote banks](remote-banks.md) for setup and the CLI example.

RNUMREG/RPOSREG receive/send calls copy values and selected comments between
local and peer banks, preserving numeric kind and positional representation.
See [register transfers](register-transfers.md) for direction, options,
explicit groups, checked copies and RPREG spelling aliases.

COMPARE_FILE compares ASCII records or binary bytes and writes a bounded JSON
report to an open ordinary FILE. Both comparison modes charge for the full
captured inputs and recheck the report FILE before writing. PRINT_FILE charges
for the input and sends validated ASCII to the existing output recorder or callback.
Rooted COPY_FILE, PRINT_FILE, COMPARE_FILE and KCL APPEND charge before disk
reads and verify source metadata. Comparison and printing accept closed
ordinary and plain PIP inputs from the supplied context. See
[file comparison and printing](file-comparison.md).

Whole JOINTPOS/Cartesian assignments use supplied robot models, selected frames
and tools. Inverse assignments require supplied current joints as a seed. See
[kinematic assignments](kinematic-assignments.md) for the context and type rules.
JOINT2POS writes directly to POSITION, XYZWPR or XYZWPREXT. With a supplied DH
model, the separate REAL array can be sized to fit the configured external axes.
A JOINTPOS value wide enough for all modeled axes can round-trip through
forward and inverse conversions. Inputs require zeros in unused slots, and
inverse conversion fills those slots with zeros. See [joint interoperability](joint-interoperability.md).

JOINTPOS operands also work in frame composition, INV, FRAME, MIRROR, axis queries
and approximate comparisons through the supplied forward model. See
[joint geometry](joint-geometry.md) for Cartesian result types, ordered
conversion, selected context and external-axis rules.

UNPOS extracts pose expressions, POSITION/XYZWPREXT values and model-backed
joint values with source capture and checked outputs. Three optional REAL outputs
receive the external axes. Bare CURPOS/CURJPOS queries use supplied offline state.
See [pose decomposition](pose-decomposition.md).

PULSE supports blocking and NOWAIT digital outputs with checked durations,
explicit host polling and scheduler deadlines. Blocking pulses permit timed
condition scans in scheduled tasks. A pending pulse stays on its
original scheduler clock when a completed task's binding is replaced.
Interruptions discard only the owning run's pending deadlines. See [output pulses](pulses.md).

VAR_INFO inspects types, dimensions, capacities and initialization, including
selected ARRAY rows and planes and supplied robot frame/tool paths.
VAR_LIST filters and pages explicit global names with checked output formats.
See [variable inspection](variable-inspection.md) for static paths, supplied
namespaces and portable resource/initialization choices.

[Record variable transfers](record-variable-transfers.md) now map compatible
user STRUCTURE fields in GET_VAR/SET_VAR, including nested records, geometry and
same-rank record ARRAY prefixes with preserved receiver tails.

GET_VAR/SET_VAR copy bounded ARRAY prefixes across different sizes and preserve
the receiver tail. Aggregate source capture and receiver preparation count
against the step budget. Typed SET sources and partial aggregates can transfer
missing data. GET_VAR reads named POSITION orientation and CONFIG fields by value.
SET_VAR writes named CONFIG turns and flags through their field checks. See
[variable transfers](variable-transfers.md) for type, ordering and status rules.

Whole QUEUE_TYPE values also transfer logical contents and sequence counters
through GET_VAR/SET_VAR. Receivers bind an explicit buffer on their next queue
operation. Whole-queue transfers charge the step budget for source and receiver
entries. See [queue transfers](queue-transfers.md).

[Dynamic typed data arrays](dynamic-data-arrays.md) accept ARRAY OF data
types/aliases and extra outer dimensions around named arrays. [Fixed CREATE_VAR
type strings](dynamic-fixed-arrays.md) now also supply literal ARRAY shapes
for data, FILE, PATH and queue banks. Created layouts retain checked ownership
through BYNAME, transfers, JSON and supported portable archives.

[Selected ARRAY variable transfers](prefix-variable-transfers.md) now let
GET_VAR/SET_VAR copy named rows/planes, capture SET source prefixes and write GET
data-output prefixes, with existing conversions and metadata/overlap guards.

[ARRAY prefix targets](array-prefix-targets.md) now assign and READ original
rows/planes, with captured actual receiver schemas, retained element aliases and
existing callback/FILE/waiting-input guards.

[ARRAY prefix values](array-prefix-values.md) now copy rows and planes from
flat multidimensional arrays into independent values for assignments, routine
arguments/results and text/binary WRITE. Complete element references stay intact.

[Uniform aggregate formats](aggregate-formats.md) now apply READ/WRITE widths,
bases, precision and quote modes to every expanded scalar field. Values and
references are captured before format functions, including across pause/resume.

[Whole-data WRITE](aggregate-output.md) now renders complete ARRAYs, records,
CONFIGs, positions and joints in defined scalar order through text and FILE
outputs, including binary fields, supplied serial/pipe banks and linked routines.

[Whole-data READ](aggregate-input.md) now expands ARRAYs, records, CONFIGs and
joint values into checked scalar input through existing callback, text and FILE
transports, including cooperative waits and cancellation. POSITION orientation
and resource input remain excluded.

[Logical PATH archives](path-archives.md) now include partial node/header data
in SAVE/LOAD/CLEAR, recursive and mixed batches, and explicit DRAM restore. They
retain exact schemas and root/header aliases, with detached old node storage.

Whole PATH values now support an exact Pythonic GET_VAR/SET_VAR copy extension,
including partial nodes/header, created roots and linked references. Copies keep
the root and compatible header aliases, and detach the old nodes. This extends
beyond the reviewed manual, which excludes whole PATH for these calls. Named
node paths such as `ROUTE[1].VALUE` use the ordinary typed transfer rules. Whole
PATH transfers charge the step budget for source and receiver leaves. See
[PATH transfers](path-transfers.md) for limits and native evidence boundaries.

CHECK_NAME validates portable base names. MOVE_FILE swaps selected RD/FR files
through explicit memory or mapped directory backends. Source and destination scans
are bounded. Preparation charges the full batch before moving, including the
byte count for rooted files. Exact ordinary COPY_FILE and KCL APPEND also charge
by byte count before publishing.
See [file management](file-management.md).

I/O assignment/mode procedures stage settings against explicit physical-capacity
metadata; module lookup uses a supplied catalog. The host applies pending settings
at an explicit configuration boundary. Logical port values remain independent.
See [I/O configuration](port-configuration.md).

`PROG_LIST` filters and pages attached programs and explicit catalog metadata
with an optional cursor. `VAR_LIST` pages declared globals and supplied root
bindings. Both accept `?` for single-character matching in Pythonic mode and
count catalog scans and output preparation against the execution step budget.
See [program listing](program-listing.md) and
[variable inspection](variable-inspection.md) for setup and formats.

PATH and QUEUE_TYPE globals now survive typed context save/load, including partial
PATH data and queue sequence IDs. Restored queues bind to the next explicitly
supplied buffer. See [collection persistence](collection-persistence.md).

Run a complete authored project with `python -m karel2py.project examples/linked_project --entry MAIN`.
See [portable projects and model setup](portable-projects.md) and the
[service equivalence matrix and embedding guide](offline-services.md)
for supported operations, context setup, pause/resume examples and remaining
native-behavior gaps. Use `--cooperative` to add host task control to ordinary
source. Strict mode remains a future milestone.

## Supported Features

- Assignment, `IF`, `SELECT`, `FOR`/`DOWNTO`, `WHILE`, `REPEAT`, body-scoped labels
  and `GOTO`, internal routines, `RETURN`, bare `ABORT` and host-backed `DELAY`.
  [Nested label transfers](nested-jumps.md) support IF/WHILE/REPEAT/SELECT
  entry while preserving FOR restrictions and USING capture barriers.
- Checked `INTEGER`, `BOOLEAN`, Python-float `REAL`, bounded ASCII `STRING`,
  `BYTE`/`SHORT` storage, fixed and named arrays, named structures, transparent
  TYPE aliases and `USING`.
- Reference/value parameters, bare zero-argument function calls, checked aggregate
  copies, restricted scalar, bounded STRING, record, joint and named-component
  ARRAY functions, selected built-ins, general degree trig, SQRT, EXP and LN.
- Positional data records, POS construction of XYZWPR and XYZWPREXT, checked [joint-axis data access](joint-axis-access.md),
  VECTOR construction/signs/products and explicit-context offline conversion subsets.
- CONFIG text parsing/formatting, with checked complete outputs and portable status.
- Explicit XYZWPR frame composition and inversion, with independent CONFIG copies.
- FRAME construction with three checked points and an optional separate origin.
  A VECTOR origin requires explicit CONFIG. See [VECTOR point frames](vector-translation-frames.md#frame-point-inputs-and-metadata).
- POSITION/XYZWPR assignment conversion with checked orientation matrices.
- POSITION and mixed POSITION/XYZWPR geometry, preserving protected matrix columns.
- Read-only UNINIT queries for whole builtin records and individual queues.
- APPROACH/ORIENT axis queries on POSITION and XYZWPR, with writable VECTOR results.
- Approximate POSITION/XYZWPR/XYZWPREXT comparison with explicit per-instance tolerances.
- CHECK_EPOS with Cartesian or joint targets, explicit frame/tool poses and a
  selected robot group. Joint targets use the supplied forward model before the
  position check. See [position checks](position-checks.md).
- DH reachability tries compatible supplied current joints before its standard
  seeds. Inverse conversion and reachability both accept optional ordered
  fallback seeds. See [position checks](position-checks.md).
- Boolean WAIT FOR with repeated checks, host yields and bounded execution.
- Error-history queries through `ERR_DATA`, with sequential/latest lookup,
  checked message outputs and optional persisted text/timestamps; see
  [error history](error-history.md).
- Packed date/time text conversion with checked calendars and complete outputs.
- Calendar GET_TIME/SET_TIME on an explicit frozen or advancing offline clock.
- Host microsecond sampling and elapsed-time subtraction with an injectable clock.
- Numeric register reads/writes on an explicit in-memory bank with checked outputs.
- Source directive metadata for environment requirements, comments and display order.
- Rounded fixed/scientific REAL text formatting with precision -254..254,
  minimum-width padding and caller-capacity overflow markers.
- Signed INTEGER text formatting in bases 2..16, with checked output references
  and capacities.
- Mixed scalar `WRITE` lists, CR newlines, dynamic formats and quoted STRING
  truncation/escaping through a recorder or supplied callback.
- Scalar `READ` destinations through a typed callback, JSON batches or text/CR input,
  with complete-response checks and input-request observations.

Each item has type and context restrictions. Physical motion, live controller
access and native task behavior remain unsupported. External routines can link
to supplied KAREL modules or explicit Python callbacks.
Explicit offline services now model files/registers/I/O and cooperative tasks.
Read the [support table and limitations](language-support.md) before using a feature.

Pythonic mode also supports [checked joint width changes](joint-width-conversions.md)
with zero padding and zero-only narrowing, [nested XML attribute updates](xml-aggregate-paths.md)
including BYTE/SHORT leaves, and [single-character FILE wildcards](question-file-wildcards.md).
These retain explicit input context, private converted values and checked batch publication.

[Dynamic SELECT cases](dynamic-select.md) evaluate typed labels once in source
order before first-match dispatch. [Numeric variable transfers](numeric-variable-transfers.md)
add checked integral-family and integral-to-REAL scalar/ARRAY conversion to GET_VAR
and SET_VAR. [XML record roots](xml-record-roots.md) accept explicit built-in
records while preserving POSITION protection and CONFIG bounds.

[Positional variable transfers](positional-variable-transfers.md) now convert
individual Cartesian representations and checked joint widths in GET_VAR/SET_VAR.
[Attached synchronous programs](synchronous-program-calls.md) can run through
CALL_PROG without resetting caller-owned state. Supplied [16-bit PNG rasters](vision-16bit-images.md)
retain explicit sample depth, byte order and alpha through saved context.
[BMP export](vision-bmp-samples.md) rounds these samples into ordinary 8-bit
components while retaining exact source data and lossless PNG output.
[Packed RGB555/RGB565 BMP export](vision-packed-bmp.md) now accepts an
explicit preference on supplied grayscale/RGB rasters while preserving original
samples and lossless PNG output.

[Offline motion requests](motion-requests.md) now cover all seven basic MOVE
forms, VIA, PATH ranges, hand statements and logical ATTACH/RELEASE ownership.
MOVE ALONG accepts scalar PATH values, array cells and PATH-valued routine
results, including chained array subscripts with ranges. It budgets NODE_POS
snapshots before evaluating node bounds. MOVE TO, MOVE NEAR and VIA read
only NODE_POS from direct PATH node operands.
An explicit service captures detached requests or consumes supplied
completion responses, immediate by default or with an explicit finite delay. It does not calculate trajectories or update robot feedback.

[Motion controls and local settings](motion-controls.md) now add independent
HOLD/UNHOLD flags, grouped STOP/RESUME of pending scripted motion, global handler
actions and 21 request-local WITH values per group, including checked termination/orientation
choices, [deceleration/acceleration intent](motion-deceleration-settings.md)
[additional scalar options](motion-options.md) and explicit group-qualified inputs; see [extended settings](extended-motion-settings.md). Ownership and JSON history remain
explicit; controls do not create trajectories or change robot feedback.

[Motion-local clauses and scripted progress](motion-handlers.md) now support
one-shot WHEN actions, UNTIL/THEN cancellation and finite supplied response delays.
An [inline MOVE](motion-statement-boundaries.md) preserves its enclosing
REPEAT's UNTIL and a following independent WITH MOVE, keeping settings scoped
to their own request.
They retain caller-owned local frames across pause/resume, validate completion
history and clean up on cancellation or failure. [Pending NOWAIT jobs](nowait-motion.md)
progress from task clocks while owners sleep or wait for another task. Opt-in
[FIFO batches](queued-motion.md) retain supplied durations and
[queued NOWAIT handlers](queued-motion-clauses.md).
Blocking local clauses now follow the [queued blocking policy](blocking-motion-clauses.md);
inferred arrivals remain unavailable.

[Explicit motion timelines](motion-timeline.md) support ascending and
descending PATH ranges. Local AT NODE and TIME BEFORE/AFTER predicates,
including wildcard destinations, use complete supplied node schedules.
Captured selectors and exact progress breakpoints persist
in validated history; no arrival times are inferred from robot geometry.

[Cooperative FILE cancellation](file-cancellation.md) now interrupts modeled
serial, pipe and keyboard typed reads through explicit FILE handles. Canceled
reads retain outputs and unread input, then continue with a portable status.

[Positional ARRAY conversions](positional-arrays.md) now carry Cartesian
representations and checked joint widths through whole assignments, private
routine arguments/results and GET_VAR/SET_VAR prefixes, without robot inference.

[Model-backed ARRAY conversions](kinematic-arrays.md) now carry whole
joint/Cartesian arrays through assignments and routine interfaces using explicit
models/adapters. Complete preflight and private staging preserve atomic output.

[READ_KB cancellation](read-kb-cancellation.md) now preserves edited-output
variables while returning portable cancellation status. Blocking reads yield
between keys; retained FILE identities protect cancellation and cleanup.

## Implementation highlights

[Inline ARRAY declarations](inline-arrays.md) now accept nested source
spellings in storage, parameters and results. Direct anonymous layers combine
into existing dimensions; named components retain their identities.

[ARRAY parameter shapes](array-formal-shapes.md) now accept fixed and mixed
dimensions, such as `ARRAY[2,*] OF INTEGER`. Matching borrowed storage keeps its
aliases; unknown forwarded sizes are checked against concrete caller storage
before the callee body. Existing private-copy and exact linked-interface rules remain.

[Bounded STRING parameters](bounded-string-formals.md) now accept direct
`STRING[capacity]` and ARRAY element spellings. Matching storage stays shared;
value arguments use the existing checked private-copy rules. Borrowed generic
scalar STRING forwarding checks the concrete capacity before the callee body.

[Input discovery](input-discovery.md#supported-analysis) now retains concrete
private ARRAY shapes through wildcard calls and function returns. Known
`ARRAY_LEN` dimensions support bounded loop analysis without reading missing
cells or executing the generated Python. Conflicting shapes and incomplete
derived values retain explicit analysis gaps.

[Boolean input discovery](input-discovery.md#boolean-and-integer-operators)
now follows short-circuit `AND`/`OR` execution. A skipped routine cannot falsely
initialize later inputs, and optional right-hand writes remain conditional.
INTEGER bitwise operators retain eager evaluation.

[Partial-copy input discovery](input-discovery.md#partial-data-copies) now
retains known fields/cells across assignments, private calls and function results.
Unused missing leaves can remain missing; reads of unproven leaves and conversions
that require complete data still report explicit gaps.

[FOR-loop input discovery](input-discovery.md#captured-for-starts) now uses
the captured counter after final-bound side effects, matching emitted execution.
Changed starts reveal newly reached inputs and omit reads from proven empty ranges.

[Scalar-call input discovery](input-discovery.md#checked-scalar-calls) now
retains known results from 17 checked math/text builtins, including `STR_LEN`.
Nested calls can resolve branches, loop bounds, array/register addresses and
own-program variable paths without executing the generated target.

[PASSALL keyboard reads](keyboard-raw-read.md#explicit-cr-record-discards)
now combine fixed STRING/numeric/BOOLEAN fields with explicit CR record discards.
Quoted STRINGs retain doubled-apostrophe escapes. Fixed fields finish without
ENTER unless a CR marker requests a terminator.

[Waiting serial reads](serial-waiting.md#scheduling-and-cancellation) and
[keyboard FILE reads](keyboard-file-read.md#pending-file-binding-checks)
retain their original bindings and registrations across waits and pauses.
Replaced keyboard bindings reject input publication and stale cancellation;
uncertain owner slots remain reserved during cleanup.

[Persistent serial readers](serial-streams.md#reclaiming-consumed-input)
can opt into reclaiming consumed input after each successful READ, allowing
repeated host feeds within a bounded receive buffer without reopening the FILE.

[Text FILE reads](communications.md#fragmented-text-records) preserve CRLF
record boundaries across separate host feeds on pipes, sockets and serial
streams. Cancellation and failed reads retain the complete unread prefix.

[Table editors](table-controls.md#enumeration-keys) now support
function-key choices and scrollable submenus. Dictionary formatting and
headless editors also accept [explicit system paths](text-dictionaries.md#plain-and-formatted-reads).

[Dictionary includes](text-dictionaries.md#generated-karel-constants)
generate checked KAREL constants from named elements. [Table headers](table-controls.md#header-controls)
support positioned text, function keys and help. [Forms](forms.md#source-syntax-and-fields)
can edit explicitly supplied system bindings.

[KCL statement skipping](kcl-commands.md#source-debugging) marks a
paused statement to bypass its operands and execution on continuation.
[Portable form packages](kcl-commands.md#portable-form-packages)
compile and load checked TX and VR companion pairs for headless forms.

[KCL source debugging](kcl-commands.md#source-debugging) adds cooperative
program breakpoints, one-shot condition breaks, and per-task source stepping.

[KCL portable batches](kcl-commands.md#mixed-archive-batches) save and
restore logical TP and variable data through checked manifests.
[Dictionary files](kcl-commands.md#dictionary-commands) support explicit
ASCII inputs and portable TX streams. File reads and expanded TX text count
against the execution step budget. [KCL RESET](kcl-commands.md#scripted-reset)
uses the supplied logical controller response.

[KCL pose recording and assignment](kcl-commands.md#pose-recording-and-value-assignment)
use supplied robot state and checked detached values. Named ARRAYs and user
records now copy into independent storage with exact schemas and complete
validation. The command channel also
supports [logical holds](kcl-commands.md#logical-hold-and-release) and
[offline storage listings](kcl-commands.md#system-and-memory-inspection).

[KCL local edits and type views](kcl-commands.md#local-variable-inspection)
add checked field/element edits and named data copies in paused source routines,
including ARRAYs, records, VECTOR, CONFIG, Cartesian poses and JOINTPOS. Type
listings and filters use the declared source metadata.

[KCL command procedures](kcl-commands.md#command-procedures) add blocking
RUNCF, bounded relative includes, SET VERIFY, and optional success-only
listing files. Procedure inputs count against the step budget before reading.
Procedures can launch and wait for registered offline tasks.

[KCL session defaults](kcl-commands.md#program-defaults) add saved program
and robot-group selectors. Live local variables, source call frames, and
individual programs can be inspected through the offline command channel.

[KCL task waits and directories](kcl-commands.md#task-waits)
add scheduler-driven WAIT DONE and WAIT PAUSE, ASCII TYPE, and directory
navigation and management within an explicitly supplied filesystem root.

[KCL inspection commands](kcl-commands.md#variable-inspection)
add bounded variable value listings, virtual volume and dictionary views,
language selection, and current-pose output from the supplied robot context.

[KCL environment and task commands](kcl-commands.md#environment-commands)
add offline port simulation and clock controls, registered task settings,
and inspection of source traces and live condition handlers.

[KCL program commands](kcl-commands.md#program-and-task-inspection-commands)
add portable TP save, load and clear, stored-source translation to Python,
and JSON-line program and task listings.
Program, task, variable and system listings bound catalog scans and charge
inspected entries to the execution budget.

[KCL volume and dictionary commands](kcl-commands.md#virtual-device-commands)
add opt-in mount, dismount, format, purge, and catalog load/clear. KCL PRINT
also accepts closed plain ASCII pipes through the existing output path.

[KCL assignment and VR commands](kcl-commands.md#variable-and-path-commands)
add typed scalar SET, detached variable removal, and portable SAVE VARS and
LOAD VARS. Restores use the archived namespace and validate the complete batch
before changing detached storage.

[KCL variable commands](kcl-commands.md#variable-and-path-commands)
add opt-in typed creation, root and namespace renaming, and bounded edits to
detached PATH nodes. KCL charges detached edits before validating or allocating
node data and verifies that the target is still current. The offline store
preserves names, values and allocation
metadata through the existing saved-context format.

[KCL file commands](kcl-commands.md#file-commands) add opt-in COPY, RENAME,
MOVE, DELETE, APPEND, PRINT and DIRECTORY over explicit offline file backends.
Append preserves complete byte prefixes and checks capacity before publication.

[Registered KCL task commands](kcl-commands.md#registered-task-commands)
add opt-in independent RUN, continuation, pause and abort through the offline
task drivers. Exact scripted replies retain precedence.

[Pendant launch and group handoff](task-and-file-extensions.md#pendant-launch-and-logical-group-handoff)
lets RUN_TASK transfer idle parent grants to a child in an explicitly enabled
offline group bank. The child's automatic group requirements are checked at the
same time, and GET_TSK_INFO reports its live pendant-motion setting.

[Parent continuation](task-and-file-extensions.md#continuing-a-parent-task)
resumes paused RUN_TASK descendants through their live launch relationships.
Both task drivers preserve existing execution frames and deliver one CONTINUE
notification per resumed task.

[Live task inspection](task-inspection.md) now reports RUN_TASK parents
and direct children. TSK_LOCKGRP and TSK_MCTL expose the selected task's current
logical group mask when its GroupLocks bank is supplied.

[Task motion flags](task-and-file-extensions.md#logical-motion-flags) now
apply HOLD or CANCEL to the owned groups of eligible live tasks. The offline
services check every target and the complete history capacity before committing
a named request or broadcast.

[Forced and broadcast task requests](task-and-file-extensions.md#forced-and-broadcast-requests)
add named force switches and `*ALL*` selection for PAUSE_TASK and ABORT_TASK.
Scheduler aliases share one execution turn and one wait deadline per Program.

[RUN_TASK continuation](task-and-file-extensions.md#run_task-entry-and-continuation)
resumes a paused KAREL task with its existing frames, timers and ownership.
Nonnegative line hints select the main entry on a fresh KAREL start.

[Bounded group lock waits](group-locks.md#bounded-acquisition-and-release)
let LOCK_GROUP wait for foreign owners and UNLOCK_GROUP wait for owned busy
groups. Both opt-in operations apply the complete mask together, with ordinary
task checkpoints, timed condition scans and exact grant checks before release.

[Cooperative socket FILE operations](communications.md#cooperative-input-and-output)
can wait for explicit input or shared TX space. Complete typed READs consume
only their RX prefix. WRITE captures its payload once and appends it atomically.
CANCEL FILE can unwind either pending operation with status 6. Scheduled
socket, serial and pipe FILE waits honor timed condition deadlines between polls.

[Cooperative serial output](serial-output-waits.md) now waits for explicitly
drained TX space under an opt-in port policy. Scalar, aggregate, binary and
bound-default WRITE capture their bytes once; CANCEL FILE can interrupt a pending
write without appending them. Pause/resume and owned cleanup retain that operation.

[Extensionless and hidden filenames](filename-substitutions.md) now work
with COPY_FILE/RENAME_FILE batches and stem-only templates. Optional-extension
substitution, mixed-name batches, virtual devices and configured plain pipes
retain complete collision, path, quota and publication checks.

[Repeated destination substitutions](repeated-destinations.md) now let
COPY_FILE and RENAME_FILE reuse complete source directory names, filename stems
and extensions at adjacent or separated stars. A whole-directory `**` keeps its
depth-preserving role; `pre_**` and `***` each repeat one directory name. Ordinary
file banks, virtual volumes, rooted folders and configured plain pipes retain
complete batch preflight.

[Directory question captures](directory-question-captures.md) now reuse
fixed-width source-directory characters in COPY_FILE/RENAME_FILE targets, alongside
repeated stars and globstars. Ambiguous source alignments reject the complete batch.

[Cross-group WITH settings](cross-group-settings.md) now capture separate
values for owned configured groups through an explicit offline opt-in. All 21
settings may appear once per group, up to 651 rows, across ordinary, queued and
local-handler MOVE requests. Only the selected MOVE group executes.

[Blocking local clauses in queues](blocking-motion-clauses.md) now support
WHEN/UNTIL and supplied temporal selectors on all seven MOVE forms and VIA.
Queued blocking scopes retain live callers, pause/resume, cancellation and checked
terminal history; their waits target supplied temporal breakpoints.

[Queued NOWAIT handlers](queued-motion-clauses.md) now retain WHEN/UNTIL,
supplied temporal selectors and live defining-frame captures until promotion.
Blocking moves can wait behind these jobs. Frame expiry, batch cancellation,
clock/grant checks and existing counter-write proofs retain explicit boundaries.

[Blocking moves after queued work](synchronous-motion-queues.md) now join an
enabled FIFO and wait for their own supplied result. All seven
MOVE forms retain captured operands/settings, holds, pause/resume, cancellation
and linked-task lifetime rules. Timed conditions can wake scheduled blocking
moves between progress polls. Queueing is an explicit offline opt-in.

[Queued NOWAIT moves](queued-motion.md) now provide an opt-in, bounded FIFO
for motion requests, including checked NOWAIT handlers. Supplied delays progress in group order with
hold/pause handling, task cleanup, complete-batch cancellation and terminal replay.
The default remains one pending move per group; physical trajectories are outside
the offline runtime.

[Directory component substitutions](directory-components.md) now let COPY_FILE
and RENAME_FILE add literal tags around source-relative directory names, including
mixed star/globstar layouts. Complete path/depth, collision and recursive namespace
checks retain existing file publication and device-accounting rules.

[Stored translation inputs](stored-translation-inputs.md) now add explicit
FILE-backed include bindings and saved ARRAY schemas to TRANSLATE. Primary/include
snapshots, protected input paths and final byte checks guard product publication;
runtime-only configuration retains lazy compiler availability.

[Saved ARRAY schemas](array-context.md) now supply wildcard global dimensions
through explicit API and CLI options, including linked owner/reexport chains.
Source types and allocation bounds remain checked; saved values and services
load separately through the existing execution context.

[External logical responses](external-logical-values.md) now carry PATH/QUEUE_TYPE
values and collection ARRAYs through fixed results, argument cases and atomic
output batches. Retained roots/headers, detached nodes and omitted queue buffer
links follow the existing logical-copy rules. Plain logical callback results
charge for descriptors and contents before copying.

[Explicit external outputs](external-outputs.md) now let JSON responses update selected
ordinary data arguments as well as returning data. Results, values and disjoint
captured destinations count against the step budget before decoding. The
complete batch validates before any response write, with the existing borrowed
and private argument rules.

[Explicit external data](external-values.md) accepts budgeted typed callback results and
CLI JSON bindings for fixed data, no-op procedures and exact argument cases
with optional explicit fallback responses. Case argument snapshots count
against the execution budget before copying.
Scalars, records, ARRAYs and pose/joint data retain checked independent values;
legacy collection bindings can be supplied alongside disjoint data bindings.

[Explicit robot system transfers](system-variable-transfers.md) now extend GET_VAR/SET_VAR to
configured frame/tool rows, location/CONFIG fields, external axes and active IDs.
Transfers stage complete checked values; direct source reads remain private and
BYNAME system aliases remain excluded.

[Direct FILE row/plane arguments](direct-file-prefixes.md) now borrow original
descriptor cells in typed user routines, including locals, nested forwarding and
linked calls. Selection is evaluated once; FILE copies remain excluded and
ordinary data/PATH/QUEUE prefixes retain their private-value behavior.

[Predefined FILE bindings](predefined-files.md) now route explicit names and
omitted READ/WRITE through configured offline endpoints. CRTDEVICE selects
INPUT/OUTPUT, bare CANCEL FILE targets the bound default input, and existing
callbacks remain the fallback for unbound defaults.

[Forward CONST references](forward-constants.md) now resolve acyclic module
and routine chains before dependent schemas. Local VAR declarations may precede
their local size/capacity constants; lexical scope, checked values and module-only
routine interfaces remain enforced.

[Pure compile-time calls](constant-builtins.md) now resolve 17 scalar math
and string built-ins in CONST expressions and static schemas. Nested calls and
forward/local dependencies use checked Pythonic values; user routines, services
and runtime storage remain excluded from constant evaluation.

[Forward type references](forward-types.md) now resolve acyclic aliases,
ARRAY/STRUCTURE components, PATH layouts and routine interfaces before allocation.
Original nominal identities and source-order metadata remain; cycles, unknown
names and excessive schema expansion produce source-located diagnostics.

[Directory-preserving destinations](directory-destinations.md) now let COPY_FILE
and RENAME_FILE insert source-relative directories with one whole `**` placeholder.
Existing collision, busy-file, overwrite and capacity checks cover the complete
expanded batch; rooted destination directories must already exist.

[NOWAIT local clauses](nowait-local-clauses.md) now support one-shot WHEN/UNTIL
and supplied temporal events at owner checkpoints across all MOVE forms. Captured
values stay live within their defining routine/invocation; pause, hold, cancellation
and checked terminal history use the existing offline motion services.

[Timer control through helpers](timer-control.md) now lets DISCONNECT TIMER
release an exact existing connection owned by the calling task, including linked
frames and borrowed ARRAY/record/BYNAME aliases. Clocks and connection lifetimes
keep their defining owners; cross-task and uncertain claims remain protected.

[Delayed NOWAIT motion](nowait-motion.md) by default keeps one pending move per
owned group while source code continues. Task clocks drive supplied completion,
with hold/pause freezing, cancellation, linked launches and scheduler observation.

[External collection results](external-collection-results.md) now accept
checked callback PATH/QUEUE_TYPE values, banks and typed JSON. Generated programs
and the project CLI can bind fixed logical results with `--external-collections`;
copies remain independent and queue buffers detach.

[Queue entry I/O](queue-io.md) now expands initialized scalar queues and
queue banks through READ/WRITE, including selected rows/planes and linked routines.
Queue I/O charges before payload validation and captures WRITE values before formats.
READ prepares every replacement pair before publishing to the original queues.
Input retains existing entry IDs/order, detaches the old buffer link and leaves
its ARRAY cells unchanged until an explicit queue operation rebinds a buffer.

[Source storage clauses and predicates](source-forms-and-predicates.md) retain
`IN CMOS`/`IN DRAM` declaration intent, accept Boolean unary `+`, and support
Boolean/integer port-simulation flags. Both range predicates accept Cartesian or
joint values using explicit reachability adapters or axis limits.

[Handler priority and frame/tool values](handler-priority-and-system-poses.md)
add stable checkpoint ordering, explicit `$MNUFRAME`/`$MNUTOOL` and active group
frame/tool reads. Supplied frame/tool tables now save/load without a robot model.

[Whole-PATH I/O and FILE queries](path-io-and-file-initialization.md) expand
supplied headers/nodes through ordinary READ/WRITE scalar transports and expose
FILE open-state initialization queries. PATH input keeps its existing node count.
PATH I/O charges the execution budget before validating or capturing fields.

[FILE arrays](file-arrays.md) now provide independent indexed streams,
borrowed routine arguments, named rows and linked imports. Existing text/binary
I/O, cancellation and pause/resume retain the selected descriptor. Static arrays
are excluded from saved variable data; a new Program creates closed descriptors.

[Dynamic FILE arrays](dynamic-file-arrays.md) now allocate checked descriptor
banks through CREATE_VAR and borrowed BYNAME interfaces. Creation-tagged JSON
retains the ARRAY schema and a closed-allocation marker; restored cells are fresh
closed descriptors. Text/binary I/O, renaming and timed cancellation use the same
explicit backends.

[Offline frame/tool writes](system-pose-writes.md) now accept whole Cartesian
rows and staged location/configuration edits. Direct EXT1 through EXT3 reads
and assignments use the configured XYZWPREXT row. Whole reads return independent
POSITION snapshots.
Linked routines, handlers and saved-context replay share the same table policy.

[Active frame/tool selection](frame-tool-selection.md) now translates
`$MNUFRAMENUM[group]` and `$MNUTOOLNUM[group]` reads and assignments. Supplied rows
are validated before selection changes; active pose views, model-backed conversions,
linked routines, handlers and JSON replay use the same offline context.

[Additional motion options](motion-options.md) expand local WITH requests to
21 checked settings: acceleration override, accuracy-area selection, signed
continuous-axis speed, segment/shift times and five policy flags. Values survive
saved-history replay; supplied timing remains explicit. `$REF_POS` is still unresolved.

[Whole POSITION input](position-input.md) now spans ARRAYs, records, prefix
rows, borrowed routines and PATH data. Complete-batch geometry checks accept
bounded transport roundoff and preserve source orientation protection across
callback, text/binary FILE and cooperative input.

[PATH and queue arrays](collection-arrays.md) now provide independent
collection cells, borrowed routine/BYNAME access and dynamic creation. Logical
JSON retains PATH contents and queue sequence state, with bounded allocation and
restore checks. Saved-variable fixtures verify the new examples independently.

[Explicit live ARRAY references](array-prefix-references.md) now borrow rows
and planes through BYNAME, including linked routines and dynamic variables.
Writes, input, timers and queue buffers share the captured original cells;
ordinary prefix arguments still use independent values. JSON retains data
without persisting aliases or suspended calls.

[Portable CONFIG words](config-words.md) now convert between CONFIG and
integral values across source assignments, private routine interfaces, ARRAYs,
records and GET_VAR/SET_VAR. The documented 16-bit Pythonic encoding preserves
missing data and staged publication without claiming native packed memory.

[Association records](association-records.md) now support COMMON_ASSOC and
GROUP_ASSOC data across declarations, routines, ARRAYs, custom PATH structures,
I/O, dynamic variables and persistence. Whole records retain normal reference
behavior; scalar-field routine arguments are private values. Group annotations
remain metadata, and the default PATH schema stays compatible.

[Cross-bank renames](cross-bank-rename.md) now move exact files and bounded
wildcard batches between explicit plain pipes and ordinary file backends. Empty
configured destination pipes retain their settings; exported source pipes release
their configuration. Complete quota and busy checks precede publication.

[Built-in record bridges](record-bridges.md) now convert matching user
structures and VECTOR, CONFIG, Cartesian, POSITION and association records.
Assignments, private routine interfaces, arrays and variable transfers preserve
typed receiver storage; constructing POSITION requires complete valid geometry.

[Resource ARRAY references](resource-prefix-references.md) now let BYNAME
borrow FILE, PATH and QUEUE_TYPE rows/planes across routines, linked calls,
dynamic rename and pause. Original descriptors, collection cells and queue
buffer links stay live; ordinary resource-array copies remain guarded.

[Typed service ARRAY rows and planes](service-array-prefixes.md) now accept
selected data storage for queue buffers, listings, XML, PC packets, forms/tables,
geometry and supplied vision results. Captures retain original cells; static
labels and typed input snapshots keep their existing ownership rules.

[Collection ARRAY archives](collection-array-archives.md) now save and
restore owned PATH/QUEUE_TYPE banks through VR files, recursive/mixed batches and
explicit DRAM snapshots. Existing array/cell/header identities survive restore;
node lists detach and queue buffer links reset after bounded batch validation.

[Collection ARRAY transfers](collection-array-transfers.md) now copy logical
PATH/QUEUE_TYPE banks through GET_VAR/SET_VAR, including rows/planes, created
storage and linked routines. Independent snapshots retain destination cells and
headers, detach old nodes, and reset copied queue buffer links. Source and
receiver snapshots count against the execution step budget.

[PATH integral counters](path-for-counters.md) add FOR over owned header,
node and bank cells, with checked capture, selected-leaf cleanup and whole-root
write/alias protection. USING node captures now retain deleted/replaced nodes.

[PATH-header USING](path-header-using.md) exposes supplied header fields
through lexical aliases. Storage selectors retain their selected header; computed
PATH results use independent private headers with counter and timer checks.

[PATH-bank I/O](path-array-io.md) adds whole-bank and selected row/plane
READ/WRITE over existing headers/nodes, with uniform formats and ordinary text,
binary and cooperative transports. Input retains original captured cells.
Output snapshots the selected fields before formats, including for rows and planes.

[Scalar collection values](scalar-collection-values.md) add PATH/QUEUE_TYPE
assignment, private routine arguments and internal/linked results with independent
logical data. Destination roots/headers stay live; copied queue buffers detach.

[Logical collection ARRAY values](collection-source-values.md) now support
PATH/queue bank assignments, private arguments, results and selected row/plane
copies. Existing destination cells stay live; copied nodes are independent and
queue buffer links reset. Bare arguments and explicit BYNAME still borrow.

[Checked REAL narrowing](real-integral-conversions.md) now truncates finite
REAL values toward zero at source assignments, private routine interfaces,
ARRAY/record conversions and GET_VAR/SET_VAR. Integral storage bounds, SHORT
missing markers, atomic data publication and exact reference contracts remain.

[Directory-pattern moves and listings](directory-file-queries.md) now extend
MOVE_FILE and FILE_LIST with bounded directory star/question and globstar matching.
RD/FR moves preserve subdirectories; sorted listings retain all five formats,
pagination, busy descriptor inspection and staged output checks.

[Directory-pattern file batches](directory-globs.md) now let COPY_FILE,
DELETE_FILE and RENAME_FILE match ordinary source directories with `*`, `?` and
whole-component `**`. Selection stays inside an explicit root/device, and the
existing collision, busy-file, quota and publication checks remain active.
[Fixed-width filename captures](question-file-wildcards.md) let COPY_FILE
and RENAME_FILE reuse matched characters in their destination filenames.

[Inverse-kinematics travel limits](ik-travel-limits.md) now distinguish
revolute degrees from prismatic millimetres. Explicit per-joint caps support
long linear travel across source conversions, variable transfers and
reachability checks while retaining supplied limits and execution budgets.

[Joint frame/tool assignments](system-pose-joints.md) now convert whole
JOINTPOS source values through the calling root group's explicit model and
selected frame/tool before destination selectors. All four table forms retain
CONFIG and external axes, including linked routines and handlers.

[Model-backed system transfers](system-variable-models.md) now convert
whole frame/tool GET_VAR rows to JOINTPOS and JOINTPOS SET_VAR inputs to
XYZWPREXT. Retained endpoint/output checks reject conflicting callback edits
before publishing data, cache IDs or status.

[Position-register model getters](position-register-models.md) now bridge
stored joint and Cartesian representations using the selected register group's
explicit model. Reads retain original bank types and guard source/status
publication through callbacks and numerical inverse-model execution budgets.

[Position-register model setters](position-register-model-writes.md) now
accept joint inputs for SET_POS_REG/SET_EPOS_REG and Cartesian inputs for
SET_JPOS_REG. They capture inputs before later selectors and stage converted
values under destination/status guards in the selected register group.

[Formatted empty collection output](empty-collection-output.md) lets the same
WRITE handle empty and populated PATHs or initialized queues. Empty collections
validate their declared formats and emit no field bytes or padding.

[Translation reports](translation-reports.md) summarize the active Pythonic
mode and link stable limitation categories to detailed policies. Supported forward
types, nested jumps, partial copies and source conversions are described consistently.
