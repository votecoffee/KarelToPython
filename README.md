# KarelToPython

![KarelToPython icon](karel2py/assets/icons/karel_to_python_icon_64x64.png)

KAREL source to Python translator with a checked offline runtime

Translate a supported subset of FANUC KAREL into Python modules with a checked
offline runtime and practical Python numeric equivalents. Unsupported syntax produces explicit
diagnostics or runtime errors. The translator does not connect to a robot.

The repository is named **KarelToPython**; its Python package and command-line
tool are named **karel2py**. The current implementation is **26.1028.175803**. It is a
development prototype, with no claim of controller runtime equivalence.

## Table of Contents

- [Background](#background)
- [Install](#install)
- [Usage](#usage)
- [Supported Features](#supported-features)
- [Roadmap](#roadmap)
- [Development](#development)
- [Repository Layout](#repository-layout)
- [API](#api)
- [Maintainers](#maintainers)
- [Contributing](#contributing)
- [License](#license)

## Background

KAREL and Python differ in storage, parameter passing, numeric behavior and
control flow. This project makes those differences explicit in a parser, code
generator and runtime. It supports inspecting and exercising small source
programs offline while preserving type, initialization and ownership checks.

Translation acceptance, successful offline execution and controller behavior
are separate results. Physical motion, live controller I/O and robot commissioning are outside
the current implementation. See the [language support guide](docs/language-support.md)
for specific restrictions, the [remaining-support inventory](docs/unsupported.md)
for the complete audited gap list, and [reference notes](docs/references.md) for provenance.

## Install

Requires **Python 3.11 or later**. The runtime uses only the Python standard library.
From a local checkout:

```sh
git clone https://github.com/votecoffee/KarelToPython.git
cd KarelToPython
python -m pip install .
```

An editable development install is also supported:

```sh
python -m pip install -e .
```

Use a virtual environment when installing. No manual PDFs, compiler installation,
private corpus or robot connection is needed to run the public tests and examples.

## Usage

### Desktop GUI

Launch the desktop workbench:

```sh
python -m karel2py.gui
```

The installed `karel2py-gui` launcher opens the same window. An optional source
path, such as `python -m karel2py.gui examples/control_flow.kl`, opens a file at startup.
The timestamp version is visible in the title bar and header.

The supplied application icon appears in the header and window/taskbar where
supported. All eight original PNG sizes are included in installed packages.

Open or paste KAREL source, select **Validate** or **Translate to Python**, and
review the Python, Diagnostics and Report tabs. Save generated Python or JSON
with the export buttons. **Check project** validates source linkage for a folder
without running the programs. See the [desktop guide](docs/desktop.md).

The editors include line numbers, syntax coloring, Find/Replace, Go to Line and
font zoom. After translation, navigate between a KAREL statement and its mapped
Python lines using the arrow buttons or Alt+Right / Alt+Left.

The GUI uses Tkinter, included with most Python installations. If unavailable,
install Python's Tcl/Tk component or your distribution's Tkinter package.

### CLI

The version uses a fixed UTC build timestamp in `YY.MMDD.HHmmss` format. It is
displayed in normal command banners and `--help`; both command-line entry points
also support `--version`:

```sh
python -m karel2py --version
python -m karel2py.project --version
```

CLI version banners go to stderr so translation summaries and linked-project
JSON remain usable on stdout. The desktop GUI also displays the build version.

Validate a KAREL source without generating or executing a module:

```sh
python -m karel2py examples/control_flow.kl --check
```

Generate a Python module and a JSON translation report, then run the module:

```sh
python -m karel2py examples/control_flow.kl -o converted.py --report translation.json
python converted.py
```

The installed `karel2py` command accepts the same arguments. Output files must be
new unless `--force` is specified. Exit codes are `0` for successful translation
or validation, `2` for rejected source or invalid CLI arguments, and `1` for file
or encoding errors. Translation does not execute the input program.

Output/report paths must differ from the source and each other, including hard
links and resolved aliases. Symbolic-link outputs are rejected. With `--force`,
each file is replaced after a complete temporary write; a failed replacement
retains that file's previous contents. Python and report publication are separate
operations, so a later report failure can leave an already-written Python file.

Generated modules print a snapshot of global values when run directly. For
example, the control-flow example finishes with `TOTAL` equal to `200`.

### Python

```python
from karel2py import translate

source = "PROGRAM DEMO VAR result: INTEGER BEGIN result=6*7 END DEMO"
translation = translate(source, filename="demo.kl")
print(translation.report["program"])  # DEMO
print(translation.python_source)
```

The generated module defines a `Program` class. For a module saved as
`converted.py`, execute it explicitly:

```python
from converted import Program

snapshot = Program().run(max_steps=100_000)
assert snapshot["TOTAL"] == 200
```

Generated Python needs `karel2py` on its import path. See the [API guide](docs/api.md)
for translation options, runtime callbacks, diagnostics and execution limits.

### Translation mode

**Pythonic mode is the default.** Ordinary decimals, rounded arithmetic and
Python math functions work without the former exact binary32 restriction.
For an explicit choice, use `translate(source, mode="pythonic")` or:

```sh
python -m karel2py examples/pythonic_numeric.kl --mode pythonic --check
```

`ROUND` uses Python's ties-to-even rule, so `ROUND(2.5)` returns 2. REAL values
use Python `float`; structural and initialization checks remain. **Strict mode
is a future milestone**; its previous exactness work is preserved internally.
See the [equivalence matrix and mode roadmap](docs/numeric-modes.md).

`CNV_CNF_STRG` formats CONFIG values using explicitly supplied per-group field
profiles, with a status output and optional group argument. Profiles persist in
service-context JSON and work with generated-script `--context` input. See
[group CONFIG formatting](docs/group-config-text.md).

Pythonic `WRITE` supports mixed text, signed numbers, REAL formatting and `CR`
newlines, for example `WRITE('value=',value::0::3,CR)`. Requests are recorded or
sent to a supplied callback. See the [text output guide](docs/pythonic-output.md).

STRING functions and writable value arguments are supported too. `STRING`
results default to 254 characters; `STRING[n]` results truncate at the declared
capacity. Parenthesized STRING arguments use private storage. See the
[STRING guide](docs/pythonic-strings.md).

Functions compose in operators, argument lists, array subscripts, conversions
and FOR bounds. Pythonic mode evaluates ordinary operands and arguments left
to right, short circuits BOOLEAN `AND`/`OR`, and captures assignment values before
resolving targets. See the [evaluation order guide](docs/evaluation-order.md)
for reference aliasing and compatibility changes.

Whole ARRAY value arguments use private checked copies. ARRAY results can be
passed onward, forwarded by RETURN, or read directly with `make()[1]`.
See the [ARRAY values guide](docs/pythonic-arrays.md) for ownership and limits.
Results also support named types and fixed or wildcard matrix/cube dimensions.
`ARRAY_LEN` returns the first dimension, like Python `len`. See
[ARRAY result shapes](docs/array-result-shapes.md).

WRITE formats accept INTEGER expressions, including function calls. Quoted
STRING fields handle apostrophes and truncation; REAL-to-text conversion supports
fixed and scientific notation. See [Pythonic text formats](docs/text-formats.md)
for the chosen conventions, evaluation order and bounds.

SUB_STR clips at the source end and permits zero counts; INDEX accepts empty
searches. See [STRING operations](docs/string-operations.md) for bounded slicing,
one-based positions and character checks.

Global-counter FOR loops can call helpers when transitive write checks protect
the counters. Read-only counter references are supported, and initialized
counters clear on RETURN, ABORT and errors. See [Pythonic FOR](docs/pythonic-for.md)
for cleanup, argument passing and remaining restrictions.

USING supports nested lexical scopes and dotted, indexed or grouped record
storage, including built-in records. Selectors capture references once per entry;
index changes preserve the selected fields. Inner fields take precedence and
handler callbacks retain their enclosing references. See [Pythonic USING](docs/pythonic-using.md)
and [captured selectors](docs/using-selectors.md) for lookup and retained guards.

TYPE aliases provide alternate names for supported types and keep original
aggregate identities and capacities. Bounded STRING alias parameters accept
checked references or private value copies. See [TYPE aliases](docs/type-aliases.md).
External types retain their complete `TYPE name FROM owner = definition` layout.
Linked projects check owner sources, exact schemas and reexport chains before
allocating globals. Shared variables and external routines use those checked
types. See [external types](docs/external-types.md) for standalone behavior and
source-located linkage errors.

VEC constructs independent VECTOR values from numeric components. Unary signs
and left-associated cross/dot chains support composed calculations such as
`SQRT(v@v)`. See [Pythonic vector expressions](docs/pythonic-vectors.md).

`POS(x,y,z,w,p,r,c)` constructs an independent XYZWPR with explicit CONFIG data
and checked coordinate/angle bounds. See [POS construction](docs/pos-construction.md).
CONFIG text parsing and complete formatting use an explicit offline grammar and
portable failure status. See [CONFIG text](docs/config-text.md).
Explicit XYZWPR poses also support `a:b` composition and `INV(a)` inversion
with a documented offline angle convention. See [frame transforms](docs/frame-transforms.md).
`FRAME` builds a right-handed frame from three or four explicit points.
See [frame construction](docs/frame-construction.md) for spacing and origin rules.
Whole assignments convert between XYZWPR and POSITION, initializing protected
orientation vectors from explicit poses. See [POSITION conversions](docs/position-conversions.md).
Composition, INV and FRAME also accept POSITION and mixed POSITION/XYZWPR
operands, with direct matrix results whenever POSITION is involved.
See [POSITION geometry](docs/position-geometry.md).
APPROACH and ORIENT return independent VECTOR copies of a pose's positive Z and
Y axes. See [pose axis queries](docs/position-axes.md).
`UNINIT` queries whole builtin records, including partially initialized poses
and vectors, without changing storage. See [initialization queries](docs/initialization-queries.md)
for the portable leaf rule and retained container exclusions.
Approximate position comparison (`>=<`) uses explicit host-supplied distance,
angle and CONFIG tolerances. See [position comparisons](docs/position-comparisons.md).
Boolean `WAIT FOR` rechecks its condition with host yields and the ordinary
execution step budget. See [Boolean waits](docs/boolean-waits.md).

CNV_STR_TIME and CNV_TIME_STR convert supplied packed date/time values and
complete English text, with checked calendars and two-second precision.
See [time text](docs/time-text.md) for the format and signed bit representation.

GET_USEC_TIM and GET_USEC_SUB measure short elapsed intervals using a host
monotonic clock or an injected test clock. See [microsecond timers](docs/microsecond-timers.md)
for the portable rollover model and repeatable execution.

GET_REG, SET_INT_REG and SET_REAL_REG operate on an explicit in-memory numeric
register bank. See [offline numeric registers](docs/numeric-registers.md) for
initial state, portable statuses and the generated script's JSON context.

ENVIRONMENT, COMMENT and ALPHABETIZE directives are retained as checked metadata
alongside NOLOCKGROUP. Environment requirements are recorded without loading
definitions or enabling extra facilities. See [source directives](docs/source-directives.md).
Seven task directives also initialize portable priority, time-slice and request
policies; see [task attributes and traces](docs/task-attributes.md).
Nine additional source policies cover an applied DEFGROUP default, CRTDEVICE
request labels, uninitialized defaults and retained storage/lock/stack/delay
intent. They are exposed through `Program.source_settings`; see
[source directive policies](docs/source-directives.md#additional-source-policies).
%INCLUDE expands supplied declaration/routine/body fragments, with nested
lookup, explicit include directories/device mappings, physical-source diagnostics
and input-file protection across CLI and linked projects. See
[source includes](docs/includes.md).
PATH helpers include portable NODE_SIZE and supplied view-line/plane intersections
with staged append behavior; see [PATH geometry](docs/path-geometry.md).
Five XML input calls provide registered-tag scanning, chunked text/attributes
and checked structure updates over explicit FILE backends; see
[XML input](docs/xml-input.md). GET_PORT_ATR/SET_PORT_ATR use a separate persisted
offline serial-attribute bank; see [serial attributes](docs/serial-attributes.md).
Six device/storage calls share explicit virtual DeviceFiles volumes, including
mount state, byte quotas, obsolete-storage reclamation, labels and supplied device
information. These operations affect memory-backed data only; see
[virtual devices](docs/virtual-devices.md).
CREATE_VAR, RENAME_VAR and RENAME_VARS manage explicit variable namespaces;
BYNAME passes checked named aliases into typed routines, including linked calls
and cooperative pause/resume. See [dynamic variables](docs/dynamic-variables.md).
CHECK_STACK, SET_DEBUG and SET_DB_EVENT use explicit offline diagnostics with
bounded event history and configurable logical stack estimates. KCL,
KCL_NO_WAIT and KCL_STATUS use a scripted command channel with acceptance,
completion waits and saved completed results. See [diagnostics](docs/diagnostics.md)
and [KCL commands](docs/kcl-commands.md) for setup and execution boundaries.

Ten pendant calls now use an explicit headless display model: opaque link/menu
requests, configured language selection, screen/window definitions, attachments,
activation and cursor positioning. WD:name FILE output updates character grids
with scrolling and common or per-handle cursors. Closed-window state persists
through context JSON. See [pendant display](docs/pendant-display.md).

```sh
python -m karel2py examples/window_display.kl -o window_display.py
python window_display.py --context examples/window_display.services.initial.json --state-out window-state.json
```

Generated programs accept numeric banks from `--context` or a separate
`--registers` file; an explicit register file overrides the context bank for all
numeric services.

Fifty-three [vision calls](docs/vision-results.md) consume supplied completed
runs, transfer registers, edit parameters and retain cursors in context JSON.
[Image/device services](docs/vision-image-services.md) add supplied captures,
PNG/BMP export, reader output, view-line PATHs and logical camera/calibration/
display/LED state. [Legacy tracking](docs/vision-tracking.md) adds timed queues,
allocation receipts, VT results/lookups, supplied point maps and a local
notification outbox. [VT line queues](docs/vt-queues.md) add put/get/acknowledge,
partial PATH reads/edits, flags, weighted routing and explicit time/flow estimates.
These services perform no image processing, hardware I/O or network delivery.

```sh
python -m karel2py examples/vision_results.kl -o vision_results.py
python vision_results.py --context examples/vision_results.services.initial.json --state-out vision-state.json
```

Six [logical controller services](docs/controller-services.md) add group-control
queries, stopped-label cancellation, stored perches, scripted reset results and
background slots for attached cooperative KAREL tasks. Explicit panel I/O banks
include OPIN/OPOUT and TPIN/TPOUT, including address zero.

The [FTX form service](docs/forms.md) adds DISCTRL_FORM with typed editing,
enumerations, help/choice overlays, tree groups and injected navigation.

Four [list/table controls](docs/table-controls.md) add resident-list paging and
array-backed typed table edits, including port cells, range checks and explicit
session cancellation. They use injected keys and headless windows; no GUI opens.

Keyboard input now uses explicitly supplied key events through READ_KB, with
editing, masks, timeouts, per-file history and PUSH/POP read suspension. Combined
window/keyboard FILEs support echo and ordinary output. Alphanumeric entry and
dictionary-backed subwindow/pull-up menus share that headless event model. See
[keyboard input](docs/keyboard-input.md) for context JSON and runnable CLI examples.

Twelve dynamic-display calls watch static scalar/enum variables and supplied
ports, updating logical window fields at deterministic checkpoint intervals.
Cancellation matches storage identity and clears fixed-width fields while
preserving ordinary FILE cursors. Cancel active bindings before saving context.
See [dynamic displays](docs/dynamic-displays.md).

Seven dictionary calls now load supplied text catalogs, read numbered/named
elements, format static variable values and write to logical windows. Nested
elements, language selection, truncation statuses and atomic cursor/clear
controls have offline models. See [text dictionaries](docs/text-dictionaries.md)
for the supported source grammar and CLI examples.

CALL_PROG/CALL_PROGLIN run attached KAREL main bodies in the calling task with
separate cursors and shared module data; see [program calls](docs/program-calls.md).
LOCK_GROUP/UNLOCK_GROUP use configured logical ownership with contention and
terminal cleanup; see [group locks](docs/group-locks.md).
All six DAQ calls use explicit typed acquisition pipes with binary FILE readers,
snapshot views, overflow tracking and batch output to supplied file backends.
See [data acquisition](docs/data-acquisition.md).
Four ADD_*PC builders create checked typed BYTE buffers; SEND_DATAPC and
SEND_EVENTPC publish to an explicit bounded offline outbox, with typed and raw
payload modes. See [PC data and events](docs/pc-exchange.md).
MSG_CONNECT/MSG_DISCO/MSG_PING use configured offline socket buffers and host
results; PIPE_CONFIG provides circular PIP FILE histories. Both support ordinary
FILE I/O and saved state; see [communications](docs/communications.md).
RMCN_ALERT/RMCN_SEND and QUEUE_ATTACH provide bounded offline mobile-message
outboxes and deferred ZDT attachment selection, with validated XML publication,
MD retention, explicit host collection and saved-state replay. See
[mobile messages and attachments](docs/remote-messages.md).
SAVE/LOAD/CLEAR and recursive PROG_BACKUP/PROG_RESTORE/PROG_CLEAR support
portable TP data archives, explicit dependency graphs, guarded batch operations
and saved-state replay; see [program archives](docs/program-archives.md).
Portable VR forms also save/load/reset owned KAREL globals and explicit variable
namespaces, including recursive variable-only batches. SAVE_DRAM records guarded
offline save points; see [variable archives](docs/variable-archives.md).

READ accepts typed scalar input through an explicit host callback. Generated
scripts can use JSON response batches with `--read-values` or ASCII text with
`--read-text`, field widths/bases/quotes and explicit CR line control. See
[READ formats](docs/read-formats.md), [text input](docs/text-input.md) and
[Pythonic input](docs/pythonic-read.md) for capture order, validation and failure behavior.

### Offline services and task control

Registers, ports and program globals share an explicit context with typed JSON
save/load. FILE operations can use memory or a caller-selected directory. Typed
PATH and QUEUE_TYPE collections work offline. PATH declarations accept PATHHEADER
and its PATHDATA compatibility spelling. Predefined DISP_DAT_T and portable
STD_PTH_NODE records work in declarations, routine interfaces, CREATE_VAR and
saved state. See [PATH declarations](docs/path-declarations.md). A deterministic scheduler handles
events, timers, delays and task pause/continue/stop. Source projects automatically
link typed external routines and imported globals. A configurable standard-DH
robot model provides forward/inverse math, external joints and bounded
reachability checks; extended-pose comparisons use explicit axis tolerances.

```sh
python -m karel2py examples/offline_services.kl -o services.py
python services.py --context examples/offline_services.services.initial.json
```

Counting semaphores, ERROR/POWERUP conditions and NOPAUSE/NOABORT/NOMESSAGE
actions are also supported. Runtime failures notify handlers while preserving
the exception. POST_ERR_L adds named portable severities and task-local scope.
Task pause/abort requests honor handlers across linked calls. FILE reads support
capacity-sized ATR_FIELD strings and custom record terminators. See
[control notifications](docs/control-notifications.md) and
[task and file extensions](docs/task-and-file-extensions.md).

Indirect port values, simulated inputs, port/register comments and supplied
teach-pendant CALL arguments share that context too. See
[I/O and CALL parameters](docs/io-and-call-parameters.md) for explicit port-type
mapping, conversions, persistence and linked-task argument scope.

CURPOS/CURJPOS read supplied current robot snapshots or model-derived Cartesian
state, with explicit groups and mask outputs. CURR_PROG reports the executing
module. See [current robot state](docs/current-robot-state.md) for host updates,
frame/tool handling, joint padding and persistence.

Padded joint values now compose across current queries, registers, model
conversions and range checks. Limits-only contexts can persist, and loaded-model
frame/tool updates remain consistent across queries and save/load. See
[joint interoperability](docs/joint-interoperability.md).

POS_REG_TYPE reports stored representation and axis width; CLR_POS_REG clears
one or all groups without removing comments. CLR_PORT_SIM removes a logical
simulation flag while retaining the last supplied value. See
[register lifecycle](docs/register-lifecycle.md) for examples and statuses.

GET_TIME and SET_TIME use an explicit offline CalendarClock, frozen or advanced
by a supplied elapsed-time adapter. Complete calendar snapshots persist through
context JSON. See [calendar time](docs/calendar-clock.md).

GET_TSK_INFO inspects explicitly registered tasks by name or number, including
live state, active linked routines, checkpoints and supplied attributes. See
[task inspection](docs/task-inspection.md) and its runnable two-task project.
SET_TSK_NAME and host task rename APIs retain numeric task order, paused/waiting
execution and scheduler metadata; see [task renaming](docs/task-renaming.md).
SET_TSK_ATTR updates nine checked settings, with cooperative scheduling, request
masks and bounded checkpoint traces. The project CLI supports `--trace-out` for
atomic trace JSON export, including partial traces on failure; see
[task attributes](docs/task-attributes.md).
Seventeen TP program calls share an explicit logical TeachPrograms store for
program management, grouped positions, frame/tool metadata, comments and opaque
instruction deletion. Values and selection persist in context JSON; native TP
parsing/execution remains outside this store. See [TP program data](docs/teach-programs.md).
Twelve TP caller-local register calls add separate numeric, string and grouped
position banks through explicit KAREL-root to TP-program bindings. Linked calls,
copying, pause/resume and JSON replay retain that scope; see
[TP local registers](docs/teach-registers.md).

LOAD_STATUS checks attached code and any known global initialization.
GET_ATTR_PRG/SET_ATTR_PRG read explicit program metadata and update owner, comment
and source metadata with activity guards. See [program metadata](docs/program-metadata.md)
for supplied snapshots, portable identifiers/statuses and the CLI example.

Seventeen remote register/comment/port procedures use explicit offline PeerBanks,
including numeric/string values, independent comments and simulation flags.
Peer banks persist in context JSON and remain independent of local banks. See
[remote banks](docs/remote-banks.md) for setup and the CLI example.

RNUMREG/RPOSREG receive/send calls copy values and selected comments between
local and peer banks, preserving numeric kind and positional representation.
See [register transfers](docs/register-transfers.md) for direction, options,
explicit groups, checked copies and RPREG spelling aliases.

COMPARE_FILE compares ASCII records or binary bytes and writes a bounded JSON
report to an open FILE. PRINT_FILE sends validated ASCII to the existing output
recorder or callback. Both use explicit memory or directory file context. See
[file comparison and printing](docs/file-comparison.md).

Whole JOINTPOS/Cartesian assignments use supplied robot models, selected frames
and tools. Inverse assignments require supplied current joints as a seed. See
[kinematic assignments](docs/kinematic-assignments.md) for the context and type rules.

JOINTPOS operands also work in frame composition, INV, FRAME, MIRROR, axis queries
and approximate comparisons through the supplied forward model. See
[joint geometry](docs/joint-geometry.md) for Cartesian result types, ordered
conversion, selected context and external-axis rules.

UNPOS extracts pose expressions, POSITION/XYZWPREXT values and model-backed
joint values with source capture and checked outputs. Bare CURPOS/CURJPOS queries
use supplied offline state. See [pose decomposition](docs/pose-decomposition.md).

PULSE supports blocking and NOWAIT digital outputs with checked durations,
explicit host polling and scheduler deadlines. Pause, terminal state and later
writes have documented ownership rules. See [output pulses](docs/pulses.md).

VAR_INFO inspects canonical types, dimensions, capacities and initialization.
VAR_LIST filters and pages explicit global names with checked output formats.
See [variable inspection](docs/variable-inspection.md) for static paths, supplied
namespaces and portable resource/initialization choices.

GET_VAR/SET_VAR copy bounded ARRAY prefixes across different sizes and preserve
the receiver tail. Typed SET sources and partial aggregates can transfer missing
data. See [variable transfers](docs/variable-transfers.md) for type, ordering,
unknown BYTE and status rules.

Whole QUEUE_TYPE values also transfer logical contents and sequence counters
through GET_VAR/SET_VAR. Receivers bind an explicit buffer on their next queue
operation. See [queue transfers](docs/queue-transfers.md).

CHECK_NAME validates portable base names. MOVE_FILE swaps selected RD/FR files
through explicit memory or mapped directory backends, with batch preflight and
documented late-failure behavior. See [file management](docs/file-management.md).

I/O assignment/mode procedures stage settings against explicit physical-capacity
metadata; module lookup uses a supplied catalog. The host applies pending settings
at an explicit configuration boundary. Logical port values remain independent.
See [I/O configuration](docs/port-configuration.md).

PROG_LIST filters and pages attached programs and explicit catalog metadata,
including program types, checked names and optional cursor pagination. See
[program listing](docs/program-listing.md) for context setup and portable formats.

PATH and QUEUE_TYPE globals now survive typed context save/load, including partial
PATH data and queue sequence IDs. Restored queues bind to the next explicitly
supplied buffer. See [collection persistence](docs/collection-persistence.md).

Run a complete authored project with `python -m karel2py.project examples/linked_project --entry MAIN`.
See [portable projects and model setup](docs/portable-projects.md) and the
[service equivalence matrix and embedding guide](docs/offline-services.md)
for supported operations, context setup, pause/resume examples and remaining
native-behavior gaps. Use `--cooperative` to add host task control to ordinary
source. Strict mode remains a future milestone.

## Supported Features

- Assignment, `IF`, `SELECT`, `FOR`/`DOWNTO`, `WHILE`, `REPEAT`, restricted labels
  and `GOTO`, internal routines, `RETURN`, bare `ABORT` and host-backed `DELAY`.
- Checked `INTEGER`, `BOOLEAN`, Python-float `REAL`, bounded ASCII `STRING`,
  `BYTE`/`SHORT` storage, fixed and named arrays, named structures, transparent
  TYPE aliases and `USING`.
- Reference/value parameters, bare zero-argument function calls, checked aggregate
  copies, restricted scalar, bounded STRING, record, joint and named-component
  ARRAY functions, selected built-ins, general degree trig, SQRT, EXP and LN.
- Positional data records, POS/XYZWPR construction, opaque joint values,
  VECTOR construction/signs/products and explicit-context offline conversion subsets.
- CONFIG text parsing/formatting, with checked complete outputs and portable status.
- Explicit XYZWPR frame composition and inversion, with independent CONFIG copies.
- Three/four-point FRAME construction with checked geometry and an optional origin.
- POSITION/XYZWPR assignment conversion with checked orientation matrices.
- POSITION and mixed POSITION/XYZWPR geometry, preserving protected matrix columns.
- Read-only whole builtin-record UNINIT queries, including nested and partial values.
- APPROACH/ORIENT axis queries on POSITION and XYZWPR, with writable VECTOR results.
- Approximate POSITION/XYZWPR/XYZWPREXT comparison with explicit per-instance tolerances.
- CHECK_EPOS with explicit frame/tool poses, selected robot group and a supplied
  DH model or synchronous callback; see [position checks](docs/position-checks.md).
- Boolean WAIT FOR with repeated checks, host yields and bounded execution.
- Error-history queries through `ERR_DATA`, with sequential/latest lookup,
  checked message outputs and optional persisted text/timestamps; see
  [error history](docs/error-history.md).
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
Read the [support table and limitations](docs/language-support.md) before using a feature.

## Roadmap

Continue expanding functional Pythonic conversion coverage. A planned
[Python runner and parameter editor](docs/roadmap.md#python-runner-and-parameter-editor)
will extract registers, variables and other values read before they are written
from generated Python, provide a tab or popup for editing those inputs, and
save both inputs and execution results in one JSON file. This runner is a
future milestone; the current workbench translates and reviews code.

[Strict mode](docs/numeric-modes.md#compatibility-and-the-strict-milestone)
remains a later milestone. See the [roadmap](docs/roadmap.md) for planned scope
and acceptance criteria.

## Development

Run from the repository root:

```sh
python -m unittest discover -s tests
python tools/run_examples.py
python tools/check_repository.py
```

Routine checks open no GUI windows. Native GUI tests are opt-in via
`KAREL2PY_GUI_TESTS=1`; see [developer tools](tools/README.md#public-checks) for
focused commands.

GitHub Actions tests are **manual-only**. Pushes and pull requests do not start
workflows. To run hosted checks, open the repository's **Actions** tab, select
**Tests (manual)** or **GUI checks (manual)**, then choose **Run workflow**.
Routine development validation uses the local CLI commands above.

The example runner translates all authored runnable examples, checks complete
expected snapshots and validates their output, delay, context and termination
fixtures, plus five complete linked projects. It also checks that the unsupported-motion example is rejected.
It uses an injected sleeper, so the delay fixture does not wait in real time.

The aggregate ARRAY example covers named records with nested arrays and STRING
fields, VECTOR arrays, exact-width joint arrays and stable captured references.
Its joint conversion uses the explicit offline axis context in its fixture.
See the [changelog](CHANGELOG.md) for implementation milestones.

Public tests create any corpus fixtures they need in temporary directories.
Optional [corpus audit tools](tools/README.md) accept an explicitly supplied corpus;
their inputs and generated reports are not part of this repository.

## Repository Layout

```text
karel2py/          Parser, lexer, code generator, CLI and checked runtime
tests/            Unit tests and synthetic corpus audit fixtures
examples/         Authored KAREL examples and expected results
docs/             API, language support, roadmap, references and semantic notes
tools/            Example runner, repository checks and optional corpus scanners
.github/workflows/  Manually dispatched CLI and GUI test workflows
```

Keep machine-specific notes, original robot files, private corpora, manual PDFs,
generated translation reports and release artifacts outside the repository or
under the git-ignored `.local/` directory. Generated Python and reports are not
maintained alongside example sources.

## API

The main entry point is
`translate(source, *, filename="<input>", array_shapes=None, mode="pythonic", cooperative=False, includes=None)`.
`translate_project(sources, *, array_shapes=None, includes=None)` adds typed project
linkage. `load_project(directory, *, array_shapes=None, include_dirs=(),
include_devices=None)` loads linked files with selected include roots/device maps.
See [include configuration](docs/includes.md). Translation returns a
translation containing `python_source` and `report`, or raises
`karel2py.lexer.TranslationError`. See [docs/api.md](docs/api.md).

## Maintainers

[@votecoffee](https://github.com/votecoffee).

## Contributing

Questions and bug reports are welcome in
[GitHub issues](https://github.com/votecoffee/KarelToPython/issues).
Pull requests are welcome. Include a small authored reproducer and meaningful
tests for changed behavior; keep unresolved semantics explicit and exclude
private or proprietary inputs. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 votecoffee.
