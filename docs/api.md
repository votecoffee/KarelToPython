# API and command-line guide

## Translation

```python
from karel2py import translate
from karel2py.lexer import TranslationError

try:
    result = translate(
        "PROGRAM DEMO VAR answer: INTEGER BEGIN answer=42 END DEMO",
        filename="demo.kl",
    )
except TranslationError as error:
    print(error.as_dict())
else:
    python_source = result.python_source
    report = result.report
```

`translate(source, *, filename="<input>", array_shapes=None, mode="pythonic", cooperative=False)` accepts a KAREL
source string. `filename` labels diagnostics and source locations. Translation
does not run the program. The returned object exposes generated `python_source`
and a JSON-serializable `report` with program/version information, source maps,
hashes, features, effect analysis and feature-specific policies.

Pythonic [POS construction](pos-construction.md) supplies checked XYZWPR values,
independent CONFIG data and source-located `pos_constructors` report entries.
[CONFIG text conversions](config-text.md) expose `config_text_conversions` and
`config_text_policy`, including portable grammar, output guards and status behavior.

[Group CONFIG formatting](group-config-text.md) adds `CNV_CNF_STRG`, supplied
`runtime.ConfigTextFormats` profiles, the `ExecutionContext.config_text` service
and `group_config_text_policy`. The service's profiles persist in context JSON.

[Source directives](source-directives.md) retain raw `directives`, decoded
`directive_metadata` and a `directive_policy` with `required_environments`.
These are recorded requirements and attributes; they do not load definitions or
enable additional source symbols or calls.

[Frame transforms](frame-transforms.md) expose `frame_operations` for explicit
POSITION/XYZWPR composition/inversion and `frame_policy` for matrix/Euler conventions,
configuration handling, capture order and retained controller boundaries.
FRAME construction also records one-based `origin_argument` and three/four operand
types in those entries. See [frame construction](frame-construction.md).
[POSITION conversions](position-conversions.md) add `position_conversions` entries
and `position_conversion_policy` for whole assignments, matrix tolerance and
read-only orientation protection. Routine interfaces retain exact types.
Since 0.72.0, [POSITION geometry](position-geometry.md) records actual operand
and result types: INV preserves its representation; colon and FRAME return
POSITION when any input is POSITION. XYZWPR-only results retain their layout.
[Pose axis queries](position-axes.md) add source-located `position_axis_queries`
and `position_axis_policy` for APPROACH/ORIENT mapping, complete-pose checks and
independent writable VECTOR results. Internal routines keep their own signatures.
[Position comparisons](position-comparisons.md) add `position_comparisons` and
`position_comparison_policy` for `>=<`. Execution requires explicit
`Program(pose_tolerance=(location_mm, orientation_deg, check_config))` context.
[Boolean waits](boolean-waits.md) add `waits` and `wait_policy` for repeated
BOOLEAN checks, zero-second host yields and the normal execution step budget.
[Time text](time-text.md) adds `time_text_conversions` and `time_text_policy` for
supplied packed dates, exact output types, complete formatting and capture order.
[Microsecond timers](microsecond-timers.md) add `microsecond_timers`,
`microsecond_timer_policy` and transitive `potential_host_clock_reads` routine effects.
[Numeric registers](numeric-registers.md) add `register_operations`,
`register_policy` and transitive `potential_register_reads` / `potential_register_writes`.

`mode="pythonic"` is the default and currently the only released mode. It uses
ordinary Python floats, rounded math and ties-to-even `ROUND`. The selected mode
is embedded in `Program.translation_mode`, the report translation context and
its hash. `mode="strict"` returns `E_MODE`: strict is a future milestone, with
the prior exactness implementation retained internally. See the
[numeric equivalence matrix](numeric-modes.md) for the complete chosen conventions.

`TranslationError.as_dict()` contains `code`, `message`, `file`, `line` and
`column`. Unsupported source is an error, rather than a partial best-effort module.

For supported global variable-sized declarations, explicitly supply every outer
dimension through `array_shapes`, for example `{"READINGS": [3]}`. Names are
case-insensitive; fixed dimensions must agree. Shapes are embedded during
translation. They do not query or resize controller storage.

## Projects and persistent services

`translate_project({filename: source_text})` and `load_project(directory)` return
a Project with `translations`, `classes` and `instantiate(context=None,
options=None)`. Its instance exposes `programs`, `context`, `scheduler`,
`run(entry,max_cycles=100000)` and `snapshot()`. FROM routines/imported globals
link among explicitly supplied sources. `python -m karel2py.project directory`
checks them; `--entry NAME` explicitly executes.

ExecutionContext supports typed `to_config`, `from_config`, `save` and `load`.
DirectoryFiles, TaskScheduler and SerialRobotModel provide optional explicit
backends. See [portable projects](portable-projects.md) for complete examples,
JSON formats, scheduling semantics and remaining boundaries.

RobotContext accepts `check_position(position,frame,tool)` as a synchronous
Boolean callback for CHECK_EPOS. Its `check_pose(position,frame,tool)` host API
validates and detaches operands; loaded DH models provide this service on restore.
See [position checks](position-checks.md) for explicit frames, groups and statuses.

`PositionRegisters.describe(number,group=1)` returns `(status,kind,axes)`;
`clear(number,group=1)` returns status, with group zero clearing all configured
groups for that number. Source POS_REG_TYPE can omit its second group operand
and uses the root task's default; the host methods default explicitly to 1.
CLR_PORT_SIM removes an existing logical simulation flag. The translation report's
`register_lifecycle_policy` describes these choices. See
[register lifecycle](register-lifecycle.md) for representation codes and failure behavior.

CalendarClock supplies GET_TIME/SET_TIME through `ExecutionContext(calendar=...)`.
Its `now`, `read`, `set`, `to_config` and `from_config` methods use an explicit
datetime or packed value, optional elapsed-microsecond adapter and frozen restore.
The report's `calendar_clock_policy` records the contract. See
[calendar time](calendar-clock.md) for setup, JSON and source examples.

ErrorHistory supplies `read_after(sequence)` for defensive record queries and
optional `post(..., error_string=..., cause_string=..., time_int=...)` metadata.
Translated ERR_DATA reads the same history; see [error history](error-history.md).

TaskRegistry and TaskScheduler accept `bind(name,program,attributes=None)` with
optional named INTEGER metadata. GET_TSK_INFO uses registered identity, live
caller-rooted execution data or that explicit metadata. `rt.TASK_CONSTANTS` and
the report's `task_inspection_policy` record the portable mappings. See
[task inspection](task-inspection.md) for lookup/output rules and all attributes.
Both task containers expose `rename(old_name,new_name)`, returning a portable
status. Translated SET_TSK_NAME also supports empty-name caller-root lookup.
The report's `task_rename_policy` describes retained state and ownership; see
[task renaming](task-renaming.md).

COMPARE_FILE and PRINT_FILE require the explicit files service. Both backends
expose `read_named(name)` returning `(status, detached_bytes_or_None)`. The
report's `file_comparison_policy` covers ASCII records, binary offsets, bounded
JSON reports and synchronous WRITE callbacks. See
[file comparison and printing](file-comparison.md) for the complete contract.

Whole JOINTPOS/Cartesian assignments call the supplied robot adapters with the
selected frame/tool and root task group. The report records `kinematic_assignments`
and `kinematic_assignment_policy`; service observations use KINEMATIC_ASSIGNMENT.
See [kinematic assignments](kinematic-assignments.md) for seed, type and failure rules.

PULSE uses explicit PortBank DOUT values, captured host clocks or scheduler virtual
time. `PortBank.poll_pulses()` services expirations and returns their count;
`pending_pulses` reports retained records. The report includes `pulses` and
`pulse_policy`. See [output pulses](pulses.md) for blocking/NOWAIT and lifecycle rules.

## CLI

```sh
python -m karel2py input.kl --check
python -m karel2py input.kl -o converted.py --report translation.json
python -m karel2py input.kl -o converted.py --array-shape READINGS=3
python -m karel2py input.kl --mode pythonic --check
python -m karel2py --version
```

The installed `karel2py` command is equivalent. Inputs are UTF-8, with an optional
BOM. Use `--force` to replace an explicitly named output/report. Source, output
and report paths must differ. Their parent directories must already exist.
`--check` cannot be combined with `--output`.

| Exit code | Meaning |
| --- | --- |
| `0` | Translation or validation succeeded. |
| `1` | File or text-decoding error. |
| `2` | Rejected source or invalid CLI arguments. |

## Semaphores and notifications

ExecutionContext accepts explicit `semaphores=SemaphoreBank(count,initial)` and
`errors=ErrorHistory(limit=1000)` services, including typed JSON save/load.
PEND_SEMA, POST_ERR and POST_ERR_L enable cooperative generation automatically. ERROR
conditions observe posted/host notifications or portable runtime-failure code 1.
NOABORT/NOPAUSE clear pending requests; they cannot suppress an invalid runtime
value. `Program.powerup()` and `scheduler.powerup(name)` explicitly continue a
live paused instance. See [control notifications](control-notifications.md) for
FIFO ordering, timeouts, error scope, suppression and recovery boundaries.
`control_notification_policy.severity_constants` maps the portable ERSEV names
to IDs, normalized effects and local scope. See
[task and file extensions](task-and-file-extensions.md) for queued requests,
POST_ERR_L metadata and TextInput terminator/field options with exact byte offsets.

## Generated Program

A generated module defines `Program(*, sleep=None, write=None, read=None, joint_axes=None, pose_tolerance=None, external_tolerance=None, clock_us=None, registers=None, context=None)`.
Call `Program().run(max_steps=100_000)` to execute explicitly and receive a
snapshot of global variables. Only the generated module's entry point runs it
automatically; importing a module defines its class.

`Program.source_directives` contains immutable normalized `(name, argument)` pairs
in source order, with `None` for directives without arguments. It is empty when
no supported directives occur. It is available without the compiler installed.

`snapshot()` returns the current global state. Names are normalized to uppercase.
Uninitialized scalar values are represented as `{"uninitialized": true}` and
unknown initial BYTE contents as `{"unknown_byte": true}`. Routine locals are
excluded. Aggregate snapshots are detached from mutable runtime storage.

The step limit counts instrumented execution, not wall-clock time. Errors raise
`karel2py.runtime.KarelRuntimeError`. Bare KAREL `ABORT` raises
`karel2py.runtime.KarelAbort`, records `abort_info` and terminates the instance.
Use a new `Program` for a cold restart. Earlier writes and callback effects are
not rolled back by failures or ABORT.

## Host callbacks and context

- `registers=NumericRegisters(count, initial=None)` supplies explicit in-memory
  INTEGER/REAL register state. GET_REG and numeric setters require this context.
  `Program.register_requests` returns copied value-free records, reset at run
  start; the bank retains writes. Generated scripts use `--registers` with JSON.
  See [numeric registers](numeric-registers.md) for types and portable statuses.
- `clock_us()` optionally supplies nonnegative Python integer microseconds for
  GET_USEC_TIM. The default uses host monotonic nanoseconds floored to microseconds;
  counter values wrap at 120,000,000 in the portable model. `Program.clock_reads`
  exposes copied line/adapter/outcome records and successful counters, reset at
  run start. See [microsecond timers](microsecond-timers.md).
- `sleep(seconds)` handles supported `DELAY`. The default is the host sleeper.
  Tests can inject a recorder. Zero delay makes no callback. Boolean WAIT FOR
  calls the same sleeper with `0.0` after a false condition check; true checks do
  not yield. See [Boolean waits](boolean-waits.md).
- `write(text)` handles supported text `WRITE` requests. Without it, requests
  are recorded in `write_requests`; this is not controller output. A callback
  receives one complete statement and must return `None` synchronously.
- `read(request)` supplies typed scalar `READ` values as a list/tuple matching
  defensive line/type metadata. An explicit callback is required when READ
  executes. `read_requests` records defensive metadata and outcomes; generated
  scripts can load JSON response batches with `--read-values`. See
  [Pythonic input](pythonic-read.md).
  `runtime.TextInput(text)` supplies explicit ASCII text with a persistent cursor
  and CR line control; generated scripts can choose `--read-text` instead.
  Optional `line_breaks` metadata describes CR positions. See [text input](text-input.md).
  [READ formats](read-formats.md) add optional per-target `format_specifiers`
  metadata and ordered dynamic expressions for widths, bases and STRING quoting.
- `joint_axes=n` supplies an explicit offline axis count for the restricted
  degree-valued joint conversion subset. It is not robot discovery or group
  configuration. Copying exact joint values does not infer a controller context.
- `pose_tolerance=(location_mm, orientation_deg, check_config)` supplies explicit
  approximate-position comparison limits and CONFIG checking. The copied immutable
  tuple is exposed as `Program.pose_tolerance`. See [position comparisons](position-comparisons.md)
  for bounds, missing-context behavior and generated-script flags.

For example, a generated program using supported WRITE requests can be exercised
with `Program(write=messages.append)`, where `messages` is a list. The
`write_requests` and `abort_info` properties return defensive observations.
Mixed STRING/BOOLEAN/INTEGER/BYTE/SHORT/REAL items and CR newlines are supported.
Numeric width/base/precision specifiers follow the chosen
[Pythonic output contract](pythonic-output.md). Items render left to right once;
the combined ASCII output is limited to 254 characters. Rendering/length failure
creates no outer request while preserving earlier effects and nested requests.

`string_operation_policy` describes SUB_STR clipping, its 254-character result
bound before consumption, zero counts, one-based starts and INDEX empty-search
results. It also records STR_LEN/CHR/ORD domains, argument evaluation order and
retained checks. See [STRING operations](string-operations.md).

`routine_effects[].potential_global_writes` reports transitive global roots.
Together with `potential_parameter_writes`, it supports checked global-counter
FOR calls and read-only counter references. `for_policy` records cleanup after
successful initial assignment, including early exits and failures. See
[Pythonic FOR](pythonic-for.md) for proof boundaries and compatibility changes.

`using_scopes` records lexical `id`, `parent` and zero-based `depth`, original
`source_selectors`, resolved paths in `variables`, inherited `field_bindings` and
source-located `resolved_uses`. `using_policy` describes nested precedence and
constant/routine-name lookup. See [Pythonic USING](pythonic-using.md).

## Limits

`conversion_policy.format` includes signed `CNV_INT_STR` bases 2..16, with base 0
selecting decimal. Digits use uppercase A..F and no prefix; minimum widths in
1..254 add left padding. These are chosen Pythonic conventions.

`conversion_policy` reports rounded Python `CNV_REAL_STR` precision in -254..254:
negative selects uppercase scientific with absolute digits, nonnegative selects
fixed output. Minimum widths are in 1..254. Those bounds limit formatting work;
caller-capacity blank/asterisk overflow and checked output references remain.
Input conversions use Python int/float
text grammar, bounded ASCII text and finite/range checks.

WRITE accepts INTEGER format expressions. Report `format_specifiers` entries
are integers for signed/grouped literals, or objects containing `expression=true`
and physical `line`/`column` for dynamic values. `items[].dynamic_formats` identifies
dynamic sites; `format_width` retains the integer or expression object, while
`alignment`, `quoted` and `width_policy` explicitly mark dynamic cases.
`write_policy.string` describes paired quotes, doubled apostrophes and bounded
truncation/fallback. See [text formats](text-formats.md).

`bare_function_calls` records each resolved zero-parameter function-name use with
its body, original source line/column and exact `result_spec`.
`bare_function_policy` describes the resolution and effect boundaries. These sites
use the ordinary checked call path; they do not represent first-class functions
or native external ABI. Explicit Python callback linkage is supported.

ARRAY return reports include the exact resolved `element_spec` and `logical_rank`
(one through three). Anonymous outer results may contain prior named
fixed ARRAY components. Bounded STRING elements carry their exact physical
capacity in `element_spec`; generic source-formal capacities are checked at
runtime, and result copying never truncates to match a different capacity.
Results also support grouping, compatible user-routine value arguments,
direct RETURN forwarding, ARRAY_LEN returning the first dimension and aggregate access.
Copies retain exact types/shapes and known initialized leaves. The
[ARRAY result contract](language-support.md#array-function-results) describes the
supported forms and remaining restrictions.

Internal STRING functions support `STRING` (default capacity 254) and
`STRING[n]` (global constant capacity 1..254). RETURN validates initialized ASCII
and right-truncates before frame cleanup. Literals, expressions, function results
and grouped STRING actuals receive independent writable capacity-254 storage;
bare storage keeps caller identity and capacity. Input values remain bounded to
254 characters, and private mutations are never copied back. See the
[STRING contract](pythonic-strings.md) and report fields
`string_routine_declarations`, `string_returns`, and `string_value_arguments`.

The runtime uses Pythonic numeric equivalents and checked range, shape, initialization and alias
checks. Successful translation does not guarantee successful execution for all
inputs. The [language support guide](language-support.md) and [semantic notes](semantics/README.md)
describe the supported input domains and unresolved behavior.

`evaluation_policy` records the chosen Pythonic order, Boolean short circuiting,
assignment value capture, live reference actuals, conversions, FOR bounds and
failure behavior. See the [evaluation order guide](evaluation-order.md) for
examples and the compatibility changes introduced in 0.54.0.

`array_value_arguments` records private ARRAY copy sites with formal and source
type specs. `array_function_uses` records ARRAY-valued expression calls.
`array_value_policy` describes checked ownership and `aggregate_access_policy`
describes subscripts/fields on explicit calls and groups. ARRAY formal
`passing_modes` includes reference and value; see the
[ARRAY values guide](pythonic-arrays.md).

`array_result_declarations` and `array_returns` record the complete result type,
declared dimension mask and nominal identity. Named types and anonymous fixed,
wildcard or mixed dimensions follow the [result shape contract](array-result-shapes.md).
`array_length_policy` defines Pythonic ARRAY_LEN as the first concrete dimension;
it also supports matrices and nested arrays without reading scalar leaves.

`type_aliases` records transparent TYPE declarations with name, immediate target,
resolved spec and physical source location. `user_types` and `named_array_types`
retain original aggregate identities. `type_alias_policy` describes resolution
and boundaries; bounded STRING alias value arguments report the declared alias
capacity in `string_value_arguments[].temporary_capacity`. See [TYPE aliases](type-aliases.md).

`vector_constructors` records fallback VEC construction sites with body,
physical line/column, X/Y/Z argument order, one-time evaluation and independent
value flags. `vector_policy` records constructor/internal-routine name priority,
unary VECTOR signs, product association and numeric boundaries. See
[Pythonic vector expressions](pythonic-vectors.md).

## Offline service context and cooperative execution

`io_parameter_policy` describes indirect port mapping, scalar conversions,
simulation, comments, argument scope and portable status codes. See
[I/O and CALL parameters](io-and-call-parameters.md) for CallParameters and the
optional constructor/JSON fields for register and port metadata.

`current_robot_policy` describes CURPOS, CURJPOS and CURR_PROG. RobotContext
accepts `current=RobotState(...)`; typed context JSON can contain `robot.current`
with or without a DH model. See [current robot state](current-robot-state.md) for
mask discard arguments, group selection, host updates and persisted snapshots.

`joint_interoperability_policy` describes exact/padded joint inputs, model output
widths, serialized explicit limits and latest model frame/tool state. See
[joint interoperability](joint-interoperability.md) for conversions, validation
and the distinction between configured active axes and unused result slots.

`context=ExecutionContext(...)` adds strings, positions, ports, variables, files,
robot adapters, external callback bindings and a task registry. Generated scripts
accept `--context` JSON for serializable service state. See the
[complete service guide](offline-services.md) for signatures and examples.
`service_operations`, `service_policy`, `cooperative_policy` and
`extended_geometry_policy` describe source sites and current portable choices.

Task-control syntax, handlers, connected timers and external declarations enable
cooperative generation automatically. `translate(...,cooperative=True)` and CLI
`--cooperative` enable host control for other source and enter the context hash.
Generated cooperative Programs add `pause()`, `resume()`, `powerup()`, `stop()` and
`task_state`. `run()`/`resume()` raise `KarelPause` when suspended; `resume()`
retains the stack, budget and current instruction. `stop()` closes suspended
frames. Runtime errors, sticky KarelAbort and terminal KarelStop are distinct.
`service_requests` returns copied operation/line/outcome records and resets on a
new run. Services retain their explicit shared state.

A minimal runtime-only distribution needs `karel2py/__init__.py`, `runtime.py`,
`extended.py`, `storage.py`, `kinematics.py`, `scheduling.py`, `control.py`, `clocks.py`, `fileops.py`, `pulses.py` and `inspection.py`. Project loading
also needs `project.py`, the compiler and lexer. Installing the package includes
all of them.

`UNINIT` supports whole CONFIG, VECTOR, POSITION, XYZWPR and XYZWPREXT storage
in Pythonic mode. Any missing nested leaf yields TRUE, with no storage mutation.
`initialization_queries` records each source site and operand type;
`initialization_query_policy` describes the portable rule and exclusions. These
queries require no service adapter and add no `service_requests`. See
[initialization queries](initialization-queries.md) for examples and validation.

`VAR_INFO` and `VAR_LIST` inspect global declarations in the explicit execution
context. They reuse ordinary output/reference checks and source-located
`service_operations`/`service_requests`. `variable_inspection_policy` records type
codes, canonical ARRAY/alias metadata, portable flags, filters and pagination.
See [variable inspection](variable-inspection.md) for complete signatures and statuses.

`GET_VAR`/`SET_VAR` support bounded same-rank ARRAY prefix copies and typed
missing/partial data. `variable_transfer_policy` records capture timing, compatible
types, preserved tails, status codes and validation boundaries. SET snapshots
source references before later output selectors; GET snapshots the resolved
global after selectors. See [variable transfers](variable-transfers.md).

`queue_transfer_policy` describes whole QUEUE_TYPE logical copies, checked
initialization/order/counter state and receiver buffer release. Explicit
`VariableStore.define` queue values detach using the same codec. See
[queue transfers](queue-transfers.md) for ordering, ownership and initialization
choices; ordinary resource assignments remain excluded.

`file_management_policy` describes CHECK_NAME's portable grammar and MOVE_FILE's
explicit RD/FR context, wildcard selection, batch preflight, status codes and
retained effects on late failure. MemoryFiles and DirectoryFiles expose
`move(specification, check=None)` with a keyword-only optional budget callback.
See [file management](file-management.md).

`port_configuration_policy` describes GET/SET_PORT_ASG, GET/SET_PORT_MOD and
IO_MOD_TYPE: explicit topology, bounded spans/modes, portable statuses, deferred
settings and logical-value independence. `PortBank(configuration=...)` accepts
the same object as JSON `ports.configuration`; `bank.configuration` returns a
detached snapshot and `bank.apply_configuration()` applies all pending settings.
Task POWERUP events do not apply configuration. See [I/O configuration](port-configuration.md).

`PROG_LIST` lists attached Programs and optional immutable
`ExecutionContext(programs=ProgramCatalog(...))` metadata. Context JSON preserves
explicit entries under `programs`. `program_listing_policy` records type filters,
formats, atomic outputs and optional Pythonic cursor pagination; see
[program listing](program-listing.md).

`LOAD_STATUS` queries attached Programs or explicit load snapshots;
`GET_ATTR_PRG`/`SET_ATTR_PRG` select typed attributes with portable identifiers
from `runtime.PROGRAM_CONSTANTS`. `ExecutionContext(program_attributes=ProgramAttributes(...))`
accepts detached named records, persisted under JSON `program_attributes`.
`record(name)` and `to_config()` return defensive copies; `set_value(name,key,value)`
validates a host metadata update. `program_metadata_policy` describes initialization,
selected outputs, the four writable fields and activity guards. See
[program metadata](program-metadata.md).

`ExecutionContext(peers=PeerBanks(...))` supplies explicit offline bank bindings
for the 17 remote register and port procedures. `PeerBanks.lookup(host)` returns
a copied mapping of shared bank objects; `to_config()` exports detached snapshots
and `from_config()` restores bank-only JSON. Context JSON stores these under
`peers`; `runtime.PEER_UNAVAILABLE` is portable status 5. Reports include
`remote_bank_policy`. See [remote banks](remote-banks.md) for signatures, selected
outputs, per-peer port mappings and retained network boundaries.

`remote_transfer_policy` describes RNUMREG/RPOSREG receive/send, also accepting
RPREG position spellings. Transfers use the caller's numeric bank or
`ExecutionContext.positions` and the selected peer bank, with explicit groups,
selected value/comment copies and complete destination preflight. Existing
context JSON retains completed updates. See [register transfers](register-transfers.md).

`joint_geometry` records model-backed JOINTPOS operands in supported geometry
expressions; `joint_geometry_policy` describes explicit context and Cartesian
results. Runtime `JOINT_GEOMETRY` records contain operation/line/outcome only.
`routine_effects.potential_service_requests` includes implicit conversions and
propagates through calls. See [joint geometry](joint-geometry.md).

Pythonic `UNPOS` accepts pose values and model-backed joint inputs, capturing
the complete source before output selectors. `unpos_calls` includes source type,
kind and snapshot policy; `unpos_policy` records representations and alias rules.
Bare or zero-argument CURPOS/CURJPOS discard both masks using the existing explicit
context; their source sites appear in `bare_function_calls` and `service_operations`.
See [pose decomposition](pose-decomposition.md).

`collection_state_policy` describes PATH/QUEUE_TYPE typed context snapshots,
partial data validation and queue buffer rebinding. `storage.typed_value()` and
`decode_typed()` support both collections; context save/load includes their
attached globals and explicit bindings. See [collection persistence](collection-persistence.md).
