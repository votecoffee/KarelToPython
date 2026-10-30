# API and command-line guide

## Translation

[Record GET_VAR/SET_VAR transfers](record-variable-transfers.md) add
`record_variable_transfer_policy` reports. Source service calls opt into compatible
context-free record schemas while preserving the existing prefix/status/cache
contract. The internal `extended.variable_transfer(..., records=False)` helper
retains its exact-record default; explicit `records=True` is Pythonic-only and
stages independent receiver data without publishing it.

[Model-backed record conversion](kinematic-records.md) adds
`State.kinematic_record(target_spec, value, line=None, *, kind="ASSIGNMENT", source_spec=None)`.
Generated source supplies its declared source schema and selects ASSIGNMENT,
ARGUMENT or RETURN. The execution context preflights the entire compatible
record tree before sequential scalar model calls, then returns independent
receiver data. Reports expose `kinematic_record_conversions` and
`kinematic_record_policy`; value-free service observations use KINEMATIC_RECORD
boundary names. Context-free helpers and exact typed-reference contracts remain.

[Source STRUCTURE schemas](record-schema-conversions.md) add
`runtime.convert_record_schema(target_spec, value, line=None, *, source_spec=None)`
for independent context-free user record and record ARRAY conversions. Generated
calls supply the declared source schema; bare generic ARRAY receiver assignments
use `State.array_assignment_value(..., source_spec=...)` with their actual target
schema. Reports expose `record_schema_conversions` and `record_schema_policy`.
Exact generic helpers, BYNAME, declared links and raw callback results retain
their existing contracts.

[Source ARRAY schemas](array-schema-conversions.md) add
`runtime.convert_array_schema(target_spec, value, line=None)` for independent
data copies across ARRAY names, STRING capacities and logical-shape-preserving
layouts. Generated bare-generic receiver assignments use
`State.array_assignment_value(value, target_spec, line=None)` with the actual
borrowed target schema. Reports add `array_schema_conversions` and
`array_schema_policy`. Compatible generic arguments and exact runtime helpers
retain their existing contracts.

[Numeric ARRAY conversions](numeric-arrays.md) add
`runtime.convert_numeric_array(target_spec, value, line=None)` at numeric source
assignment, argument and RETURN boundaries. Reports expose
`numeric_array_conversions` and `numeric_array_policy`; converted arguments
retain source specs and private writable ownership without copy-back.
[Named/component ARRAY conversions](named-array-conversions.md) add
`named_array_conversions`, component-name provenance and `named_array_policy`
across numeric, positional and explicit-model conversions. Receiver schemas
retain their own names. Generic checked/value/result helpers remain exact.

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

`translate(source, *, filename="<input>", array_shapes=None, mode="pythonic", cooperative=False, includes=None)` accepts a KAREL
source string. `filename` labels diagnostics and source locations. Translation
does not run the program. The returned object exposes generated `python_source`
and a JSON-serializable `report` with program/version information, source maps,
hashes, features, effect analysis and feature-specific policies.

[Nested label transfers](nested-jumps.md) expose `nested_jump_policy` and per-body
`control_flow.jumps`: target label, source/target expanded line/column/block paths,
and same-block, ancestor, nested or sibling classification. The existing source
map resolves physical include origins. FOR and USING capture barriers remain.

`includes` accepts captured source text by filename or an explicit
`karel2py.includes.IncludeLibrary`. [Source includes](includes.md) describe
nested lookup, selected directories/device mappings, limits and source-file
protection. Expanded reports add dependency hashes, physical-source spans and
original-file diagnostics. The text API does not infer filesystem access from
`filename`; the CLI explicitly selects the source directory and extra roots.

Pythonic [POS construction](pos-construction.md) supplies checked XYZWPR values,
independent CONFIG data and source-located `pos_constructors` report entries.
[CONFIG text conversions](config-text.md) expose `config_text_conversions` and
`config_text_policy`, including portable grammar, output guards and status behavior.

[Group CONFIG formatting](group-config-text.md) adds `CNV_CNF_STRG`, supplied
`runtime.ConfigTextFormats` profiles, the `ExecutionContext.config_text` service
and `group_config_text_policy`. The service's profiles persist in context JSON.

[Source directives](source-directives.md) retain raw `directives`, decoded
`directive_metadata` and a `directive_policy` with `required_environments`.
`Program.source_settings` exposes detached source policy metadata, including
DEFGROUP and CRTDEVICE behavior. [PATH geometry](path-geometry.md) adds
NODE_SIZE and INTSCT_VL_PL with `path_geometry_policy` in the report.
[XML input](xml-input.md) adds `xml_input_policy` and five checked FILE calls.
`SerialPorts`, supplied as `ExecutionContext(serial_ports=bank)`, adds persisted
[serial attributes](serial-attributes.md) and `serial_attribute_policy`.
`DeviceFiles` supplies six [virtual device/storage calls](virtual-devices.md)
through the ordinary files service, with `virtual_device_policy`. Context JSON
uses `device_files` to preserve volumes, quotas and obsolete-storage counters.
These are recorded requirements and attributes; they do not load definitions or
enable additional source symbols or calls.

`runtime.SourceTranslations`, supplied as `ExecutionContext(source_translations=...)`,
enables [stored-source TRANSLATE](source-translations.md), with JSON configuration,
bounded artifact history and `stored_source_translation_policy` in reports.
It uses the ordinary `files` backend, produces `.py` plus optional `.LS` and
never loads or executes its products. Compiler imports are lazy for runtime-only
deployments. [Wildcard COPY/DELETE](wildcard-file-operations.md) use that same
backend and expose `wildcard_file_policy`.
`GroupLocks(..., apply_directives=True)` enables [root directive acquisition](directive-group-locks.md);
`group_lock_policy` records the opt-in, root entry and startup failure rules.
Adding `callee_scopes=True` enables [nested module scopes](scoped-group-locks.md)
with additional-grant cleanup on return; the default retains root-only behavior.
[Plain pipe wildcard batches](pipe-wildcard-files.md) extend `wildcard_file_policy`
without creating missing pipe configurations or truncating snapshots.
The [FOR jump contract](for-jumps.md) adds active-loop transfers and exited-counter
cleanup to the dispatcher, with explicit rejection of entry into new FOR scopes.

`runtime.SerialStreams`, supplied as `ExecutionContext(serial_streams=...)`, adds
[finite serial FILE endpoints](serial-streams.md). The JSON field `serial_streams`
retains remaining RX and accumulated TX data after explicit FILE close; it opens
no host devices. `SerialPorts` attribute metadata remains independent.
[Reference FOR counters](reference-for-counters.md) capture selected INTEGER
storage once and protect the aggregate root. [VECTOR translation frames](vector-translation-frames.md)
add offset colon operands, VECTOR inversion and FRAME point arguments with an
explicit pose origin; ordinary exact routine interfaces remain unchanged.

[Computed USING](computed-using.md) adds checked private record captures for
function/constructor/operator results. `using_scopes[].selector_captures` records
storage/computed provenance, ownership and copy-back policy; `computed_using_policy`
describes capture lifetime. [Private connected timers](private-using-timers.md) add
`connected_timers` source sites and `connected_timer_policy`, retaining null public
roots for private captures, whole-root counter protection and terminal cleanup.
[Routine-local timers](routine-local-timers.md) add `routine_local_timer_policy`
and rows with `provenance=routine_local`, `lifetime=routine_frame`. Generated local
operations use `runtime.connect_timer`/`disconnect_timer` with `scoped=True`;
actual live-frame ownership controls pause and exact-frame cleanup.
[Formal timers](formal-timers.md) add `formal_timer_policy` and
`provenance=borrowed_formal` rows with the same frame lifetime. ExecutionContext
keeps private shared-cell claims, and archive preflight protects their retained
original endpoints. Claims are absent from saved context JSON.
[Private INTEGER counters](private-using-counters.md) add internal protection
identities, retained-alias checks and `private_using_counter_policy` without
publishing synthetic source variables. [Scalar BYTE/SHORT](scalar-narrow.md)
add narrow globals, locals, TYPE aliases and typed routine interfaces, with exact
bare references or checked private numeric conversions. [Wildcard renames](wildcard-rename.md)
extend `wildcard_file_policy` with no overwrite and same-bank preflight.
[Scalar SELECT](scalar-select.md) adds `scalar_select_policy`, per-site selector
types and comparison categories; BOOLEAN remains distinct from numeric cases.
[Dynamic narrow creation](dynamic-narrow.md) extends `dynamic_variable_policy`
with direct BYTE/SHORT and supplied transparent aliases. [Cross-volume renames](cross-volume-rename.md)
extend the wildcard policy with complete DeviceFiles capacity and garbage preflight.
[Narrow FOR counters](narrow-for.md) add BYTE/SHORT domains and type-specific cleanup,
recorded by `narrow_for_policy`. [Inherited STRING-array capacities](inherited-string-array-results.md)
add capacity inference from concrete returned storage, recorded by
`inherited_string_array_result_policy`; `cartesian_interface_policy` describes
the routine representation conversions.
[Chained indexes](chained-array-indexes.md) add `array_index_chains` and
`chained_array_index_policy`; complete adjacent brackets use the existing comma
access contract. [Model-backed routine conversions](kinematic-interfaces.md)
add `kinematic_interfaces`, `kinematic_interface_policy` and value-free
KINEMATIC_ARGUMENT/KINEMATIC_RETURN observations. [Palette images](vision-palette-images.md)
add optional explicit RGBA tables and `vision_palette_policy`, retaining the
existing image queues, storage limits and output preflight.
[Waiting serial reads](serial-waiting.md) use per-port `wait`/`final` flags and
`SerialStreams.finish_input(port)`, retaining finite defaults and explicit FILE
lifetime. [Alpha images](vision-alpha-images.md) add packed GA/RGBA data and
PNG/BMP exports without image processing or native acquisition.

[Frame transforms](frame-transforms.md) expose `frame_operations` for explicit
POSITION/XYZWPR composition/inversion and `frame_policy` for matrix/Euler conventions,
configuration handling, capture order and retained controller boundaries.
FRAME construction also records one-based `origin_argument` and three/four operand
types in those entries. See [frame construction](frame-construction.md).
[POSITION conversions](position-conversions.md) add `position_conversions` entries
and `position_conversion_policy` for whole assignments, matrix tolerance and
read-only orientation protection. [Cartesian routine conversions](cartesian-interfaces.md)
extend source argument and RETURN boundaries with independent checked values;
BYNAME, linked declarations, callback raw results and whole arrays retain their
exact interface contracts.
Since 0.72.0, [POSITION geometry](position-geometry.md) records actual operand
and result types: INV preserves its representation; colon and FRAME return
POSITION for pose-only inputs when any input is POSITION. Extended/joint rules
are documented in their feature guides. A [right VECTOR point](vector-frames.md)
now returns VECTOR; XYZWPR-only pose operations retain their layout.
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

`translate_project(sources, *, array_shapes=None, includes=None)` and
`load_project(directory, *, array_shapes=None, include_dirs=(), include_devices=None)`
return a Project with `translations`, `classes`, captured filesystem `source_files`
and `instantiate(context=None,
options=None)`. Its instance exposes `programs`, `context`, `scheduler`,
`run(entry,max_cycles=100000)` and `snapshot()`. FROM routines/imported globals
link among explicitly supplied sources. `python -m karel2py.project directory`
checks them; `--entry NAME` explicitly executes. Both CLIs accept repeated
`-I`/`--include-dir` and `--include-device DEVICE=DIRECTORY`. Directory projects
exclude referenced top-level include fragments from standalone program entries.

Project `array_shapes` accepts common `NAME` keys or program-qualified
`PROGRAM.NAME` keys, for example `{"MAIN.VALUES": [3, 2], "LIB.VALUES": [2]}`.
Common keys apply only to matching direct global wildcard declarations; other
programs receive no unused shape. Unknown/duplicate/overlapping keys reject.
The project CLI accepts repeated `--array-shape [PROGRAM.]NAME=DIM[,DIM]`.
`Project.array_shapes` exposes normalized maps per program; translation reports
retain local concrete contexts and hashes. See
[project ARRAY specialization](project-array-shapes.md).

ExecutionContext supports typed `to_config`, `from_config`, `save` and `load`.
Its optional `variable_archives=runtime.VariableArchives(...)` service supplies
[portable VR files and SAVE_DRAM points](variable-archives.md). Host
`bank.restore_dram(program._state, name)` explicitly restores a guarded snapshot;
loading context does not automatically apply it or resume execution.
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
`tasks.set_attribute(name,attribute,value)` applies one of nine checked policies;
attribute can be a named TSK key or package INTEGER ID. Program.task_settings and
Program.task_trace return detached copies. `ProjectInstance.trace_snapshot()`
provides the document exported by the project CLI's `--trace-out`. See
[task attributes and tracing](task-attributes.md).
`TeachPrograms` supplies logical TP records through
`ExecutionContext(teach_programs=bank)`. Host APIs cover create/copy/select,
root-token open/close, read/write positions, owner cleanup and detached JSON.
Its records also participate in program listing/load/header metadata queries.
See [TP program data](teach-programs.md) for all 17 source calls and access rules.
`TeachPrograms(..., callers={"MAIN": "TP_CALLER"})` additionally supplies the
12 [TP local register calls](teach-registers.md). `bind_caller`, `read_register`
and `write_register` expose explicit host access; `callers` returns a detached
mapping. Local limits/values/bindings persist in context JSON. Translation reports
include `teach_register_policy`, and local banks remain separate from global
registers, program points and call parameters.

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
  `TextInput(...,final=False)` distinguishes incomplete input with
  `TextInputIncomplete` from malformed completed fields; the default `final=True`
  retains ordinary EOF behavior. Explicit waiting pipes use this parser without
  publishing partial responses. FILE READ automatically enables cooperative source
  generation for injected [keyboard input](keyboard-file-read.md) and opted-in
  [plain pipes](pipe-attributes.md).
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
`aggregate_copy_policy` describes validated partial data transfers, complete-only
geometry/service boundaries and the retained strict restrictions. See
[partial aggregate values](partial-aggregate-values.md).
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

FILE READ, task-control syntax, handlers, connected timers and external declarations enable
cooperative generation automatically. `translate(...,cooperative=True)` and CLI
`--cooperative` enable host control for other source and enter the context hash.
Generated cooperative Programs add `pause()`, `resume()`, `powerup()`, `stop()` and
`task_state`. `run()`/`resume()` raise `KarelPause` when suspended; `resume()`
retains the stack, budget and current instruction. `stop()` closes suspended
frames. Runtime errors, sticky KarelAbort and terminal KarelStop are distinct.
`service_requests` returns copied operation/line/outcome records and resets on a
new run. Services retain their explicit shared state.

Install the complete `karel2py` package alongside generated modules. Runtime
services share support modules; project translation additionally uses
`project.py`, `compiler.py`, `lexer.py`, `includes.py` and `fileio.py`. Installing
the package supplies those dependencies.

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

[Joint width conversion](joint-width-conversions.md) adds complete-value source
assignment/argument/RETURN padding and zero-only narrowing. `joint_width_conversions`
and `joint_width_policy` describe sites and contracts in translation reports.
[XML aggregate paths](xml-aggregate-paths.md) add staged scalar-leaf updates through
record/ARRAY paths, including BYTE/SHORT. [Question FILE patterns](question-file-wildcards.md)
extend final source basenames for COPY/DELETE/RENAME/MOVE while retaining checked
batch publication and explicit ordinary/plain-PIP services.

[Dynamic SELECT](dynamic-select.md) accepts compatible runtime scalar case labels
and captures all labels eagerly before matching. Reports expose dynamic slots
through `case_expressions`, `dynamic_cases` and `case_evaluation`.
`numeric_variable_transfer_policy` describes [checked GET_VAR/SET_VAR numeric
conversions](numeric-variable-transfers.md), including bounded ARRAY prefixes.
`xml_record_root_policy` describes [XML built-in record roots](xml-record-roots.md),
their explicit schemas, staged publication and protected descendants.

`positional_variable_transfer_policy` describes complete individual Cartesian
and checked joint-width GET_VAR/SET_VAR conversions. ARRAY representations stay exact.
`synchronous_program_call_policy` describes newly generated `_execute_sync` bodies
used by nested program calls; standalone `run()` retains its ordinary begin/cleanup.
`vision_sample_depth_policy` describes explicit `sample_bits=16`, lossless PNG,
raw byte quotas and unsupported 16-bit BMP status. See [positional transfers](positional-variable-transfers.md),
[synchronous calls](synchronous-program-calls.md) and [16-bit images](vision-16bit-images.md).

[Motion requests](motion-requests.md) use `runtime.MotionRequests(groups, *, hands=None,
capture_only=False, responses=None, limit=128, sequence=0, history=None)` through
`ExecutionContext.motion`. Groups map integer group numbers to explicit axis counts.
Reports add `motion_requests` and `motion_request_policy`; context JSON retains
canonical group/hand keys, detached typed history and remaining immediate replies.
Ownership is supplied through GroupLocks. Capture-only outcomes are explicit;
scripted results do not calculate motion or change robot feedback.

[Logical motion controls and local WITH settings](motion-controls.md) add the
optional `GroupLocks(..., held=[group,...])` configuration. Empty hold sets remain
omitted from saved JSON. MotionRequests validates before/after control history
and per-request `settings` records; the translation policy documents action-time
ownership selection, source capture order and the absence of environment mutation.

[Motion-local handlers and scripted progress](motion-handlers.md) accept an optional
`delay_ms` on each MotionRequests response. Generated cooperative MOVE output
retains private callbacks and routine frames for synchronous scopes; save guards
reject active scopes and loaded history validates progress, triggers and outcomes.
Reports add local clause locations and scope rules. Older direct-invoke output
must be retranslated for delayed responses. No queued/native motion is inferred.

[Explicit temporal predicates](motion-timeline.md) use optional response
`node_times` with an explicit delay_ms. Complete selected-range schedules and
concrete selector metadata persist in execution history. Reports add
`motion_request_policy.temporal_conditions` and per-MOVE condition locations;
handler action reports cannot take ownership of their enclosing MOVE metadata.

[FILE cancellation](file-cancellation.md) adds `runtime.cancel_file(state, handle,
line=None)` for the exact generated cooperative typed READ. Cancellation marks
the captured operation, validates live backend identity, and returns portable
IO_STATUS 6 after unwind. Idle registered FILEs return status zero without data
changes. Direct host generators and READ_KB jobs remain separate. Reports expose
`file_cancel_policy`; operation tokens are private and never serialized.

[Positional ARRAY conversion](positional-arrays.md) adds explicit
`runtime.convert_positional_array(target_spec, value, line=None)` for anonymous
matching-shape Cartesian/joint-width source values. It prepares complete private
data without changing generic checked/parameter/result compatibility. Reports
add `positional_array_conversions` and `positional_array_policy`; GET_VAR/SET_VAR
reuse checked leaf conversions inside their existing atomic prefix preparation.

[Model-backed ARRAY conversion](kinematic-arrays.md) adds
`State.kinematic_array(target_spec, value, line=None, kind="ASSIGNMENT")`; kind
also accepts ARGUMENT or RETURN. It preflights complete source geometry and output
allocation, then stages existing scalar model conversions in row-major order.
Reports add `kinematic_array_conversions`/`kinematic_array_policy`; one value-free
service record describes the whole request. Generic ARRAY checked/value/result
helpers and storage-only GET_VAR/SET_VAR keep their separate contracts.

[READ_KB cancellation](read-kb-cancellation.md) extends `runtime.cancel_file` to
the exact keyboard editor, using retained FILE/binding/request identities. Source
status and IO_STATUS become 6 without text/count/key publication; private tokens
are omitted from JSON. Reports add `read_kb_cancellation_policy` and keyboard
blocking-checkpoint/poll rules. Direct typed backend generators remain separate.
