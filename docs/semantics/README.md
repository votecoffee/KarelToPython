# Semantic notes

The [routine-local timer ledger](routine_local_timer_semantics.json) supersedes
older declared-local timer exclusions. The [formal timer ledger](formal_timer_semantics.json)
supersedes older borrowed-formal exclusions under a callee-frame ownership policy.

The [numeric ARRAY ledger](numeric_array_semantics.json) supersedes older blanket
numeric element-conversion exclusions at anonymous source ARRAY boundaries.
The [named/component ARRAY ledger](named_array_conversion_semantics.json) supersedes older
blanket named-interface conversion exclusions for supported terminal changes.
The [source ARRAY schema ledger](array_schema_conversion_semantics.json) supersedes
older nominal ARRAY, STRING-capacity and component-layout source exclusions.
Receiver schemas and generic checked/value/result exactness remain.
The [source STRUCTURE schema ledger](record_schema_conversion_semantics.json)
supersedes older whole-record and different-record-terminal source exclusions
for identical field-name sets with recursively compatible context-free data.
Declared links, BYNAME, raw callback results and generic helpers remain exact.

The [private timer ledger](private_using_timer_semantics.json) supersedes older
private connected-timer exclusions in the computed-capture/private-counter notes.

Current POSITION geometry follows the [POSITION guide](../position-geometry.md);
older blanket POSITION geometry exclusions retain the conservative contract.

The [register transfer ledger](register_transfer_semantics.json) supersedes the
remote-position-transfer exclusion in the historical remote-bank ledger.

These JSON notes describe manual rules, conservative prototype contracts, test
locations and unresolved behavior. They are implementation documentation, not
native compiler or controller acceptance evidence. See [references](../references.md)
for the manual edition and page numbering.

Since 0.51.0, public translation uses [Pythonic numeric behavior](../numeric-modes.md).
Exact REAL, trig, conversion and VECTOR restrictions in the older ledgers describe
the preserved conservative research contract. They do not limit the current
Pythonic mode. Earlier ordering rejections also belong to that conservative
contract; see the [current evaluation rules](../evaluation-order.md). A public
strict mode remains a future milestone. Older ARRAY assignment-only and value
rejections also belong to the conservative contract; see the
[Pythonic ARRAY rules](../pythonic-arrays.md). Result-form and length rejections
are also qualified by the [Pythonic result shapes](../array-result-shapes.md).
Earlier literal-only, quoted-content and scientific-format rejections are
qualified by the [current text format rules](../text-formats.md).
Earlier substring-overrun and empty-search rejections are qualified by the
[Pythonic STRING operations](../string-operations.md).
Earlier fresh-local-only FOR calls, counter-reference rejections and exceptional
counter observations are qualified by [Pythonic FOR](../pythonic-for.md).
Earlier USING nesting, dotted-selector and namespace rejections are qualified
by [Pythonic USING](../pythonic-using.md).
Earlier scalar/STRING/type-to-type alias rejections are qualified by
[Pythonic TYPE aliases](../type-aliases.md).
Earlier VEC, unary VECTOR sign and same-level product-chain rejections are
qualified by [Pythonic vector expressions](../pythonic-vectors.md).

Each ledger is relative to this directory. Test paths inside its text are relative
to the repository root. Private corpus reports and machine-specific provenance
are kept outside public documentation.

| Topic | Ledger |
| --- | --- |
| Explicit-frame position checks | [position_check_semantics.json](position_check_semantics.json) |
| Task binding renaming | [task_rename_semantics.json](task_rename_semantics.json) |
| Applied task attributes, directives and traces | [task_attribute_semantics.json](task_attribute_semantics.json) |
| Offline TP program data | [teach_program_semantics.json](teach_program_semantics.json) |
| TP caller-local registers | [teach_register_semantics.json](teach_register_semantics.json) |
| Additional source policies | [source_policy_semantics.json](source_policy_semantics.json) |
| PATH sizing and intersections | [path_geometry_semantics.json](path_geometry_semantics.json) |
| XML input | [xml_input_semantics.json](xml_input_semantics.json) |
| Serial attributes | [serial_attribute_semantics.json](serial_attribute_semantics.json) |
| Virtual devices and storage | [virtual_device_semantics.json](virtual_device_semantics.json) |
| Error history queries | [error_history_semantics.json](error_history_semantics.json) |
| Collection persistence | [collection_persistence_semantics.json](collection_persistence_semantics.json) |
| Pose decomposition | [pose_decomposition_semantics.json](pose_decomposition_semantics.json) |
| Program listing | [program_listing_semantics.json](program_listing_semantics.json) |
| Program metadata | [program_metadata_semantics.json](program_metadata_semantics.json) |
| Remote banks | [remote_bank_semantics.json](remote_bank_semantics.json) |
| Register transfers | [register_transfer_semantics.json](register_transfer_semantics.json) |
| Pythonic CONFIG text | [config_text_semantics.json](config_text_semantics.json) |
| Pythonic POS construction | [pos_constructor_semantics.json](pos_constructor_semantics.json) |
| Pythonic READ formats | [read_format_semantics.json](read_format_semantics.json) |
| Abort | [abort_semantics.json](abort_semantics.json) |
| Array routine | [array_routine_semantics.json](array_routine_semantics.json) |
| Array | [array_semantics.json](array_semantics.json) |
| Atan2 | [atan2_semantics.json](atan2_semantics.json) |
| Branch | [branch_semantics.json](branch_semantics.json) |
| Conversion | [conversion_semantics.json](conversion_semantics.json) |
| Data record | [data_record_semantics.json](data_record_semantics.json) |
| Delay | [delay_semantics.json](delay_semantics.json) |
| For routine | [for_routine_semantics.json](for_routine_semantics.json) |
| Function call | [function_call_semantics.json](function_call_semantics.json) |
| Joint | [joint_semantics.json](joint_semantics.json) |
| Literal | [literal_semantics.json](literal_semantics.json) |
| Local constant | [local_constant_semantics.json](local_constant_semantics.json) |
| Named array | [named_array_semantics.json](named_array_semantics.json) |
| Narrow integer | [narrow_integer_semantics.json](narrow_integer_semantics.json) |
| Numeric | [numeric_semantics.json](numeric_semantics.json) |
| Position | [position_semantics.json](position_semantics.json) |
| Pythonic WRITE | [pythonic_write_semantics.json](pythonic_write_semantics.json) |
| Pythonic STRING | [pythonic_string_semantics.json](pythonic_string_semantics.json) |
| Pythonic evaluation order | [pythonic_order_semantics.json](pythonic_order_semantics.json) |
| Pythonic ARRAY | [pythonic_array_semantics.json](pythonic_array_semantics.json) |
| Pythonic ARRAY result shapes | [pythonic_array_shape_semantics.json](pythonic_array_shape_semantics.json) |
| Pythonic text formats | [pythonic_text_format_semantics.json](pythonic_text_format_semantics.json) |
| Pythonic STRING operations | [pythonic_string_operation_semantics.json](pythonic_string_operation_semantics.json) |
| Pythonic FOR | [pythonic_for_semantics.json](pythonic_for_semantics.json) |
| Pythonic USING | [pythonic_using_semantics.json](pythonic_using_semantics.json) |
| Pythonic TYPE aliases | [type_alias_semantics.json](type_alias_semantics.json) |
| Pythonic VECTOR expressions | [pythonic_vector_expression_semantics.json](pythonic_vector_expression_semantics.json) |
| Pythonic typed READ | [pythonic_read_semantics.json](pythonic_read_semantics.json) |
| Pythonic text input | [text_input_semantics.json](text_input_semantics.json) |
| Positional routine | [positional_routine_semantics.json](positional_routine_semantics.json) |
| Predefined | [predefined_semantics.json](predefined_semantics.json) |
| Select | [select_semantics.json](select_semantics.json) |
| Source | [source_semantics.json](source_semantics.json) |
| Source directive metadata | [directive_semantics.json](directive_semantics.json) |
| XYZWPR frame transforms | [frame_transform_semantics.json](frame_transform_semantics.json) |
| Point-defined FRAME | [frame_constructor_semantics.json](frame_constructor_semantics.json) |
| POSITION/XYZWPR conversion | [position_conversion_semantics.json](position_conversion_semantics.json) |
| POSITION and mixed geometry | [position_geometry_semantics.json](position_geometry_semantics.json) |
| APPROACH/ORIENT axis queries | [position_axis_semantics.json](position_axis_semantics.json) |
| Approximate position comparison | [position_comparison_semantics.json](position_comparison_semantics.json) |
| Boolean WAIT FOR | [wait_semantics.json](wait_semantics.json) |
| Packed date/time text | [time_text_semantics.json](time_text_semantics.json) |
| Host microsecond timers | [microsecond_timer_semantics.json](microsecond_timer_semantics.json) |
| Offline numeric registers | [numeric_register_semantics.json](numeric_register_semantics.json) |
| String | [string_semantics.json](string_semantics.json) |
| String value | [string_value_semantics.json](string_value_semantics.json) |
| Structure routine | [structure_routine_semantics.json](structure_routine_semantics.json) |
| Structure | [structure_semantics.json](structure_semantics.json) |
| Subarray | [subarray_semantics.json](subarray_semantics.json) |
| Trig | [trig_semantics.json](trig_semantics.json) |
| Unpos | [unpos_semantics.json](unpos_semantics.json) |
| Using | [using_semantics.json](using_semantics.json) |
| Variable array | [variable_array_semantics.json](variable_array_semantics.json) |
| Vector routine | [vector_routine_semantics.json](vector_routine_semantics.json) |
| Vector | [vector_semantics.json](vector_semantics.json) |
| Write | [write_semantics.json](write_semantics.json) |

The older WRITE ledger preserves the conservative output contract. Current
Pythonic item lists and formatting are described in the Pythonic WRITE ledger
and [output guide](../pythonic-output.md).
The older STRING ledgers preserve the conservative result/value restrictions;
current behavior follows the Pythonic STRING ledger and
[STRING guide](../pythonic-strings.md).

The [extended service ledger](extended_service_semantics.json) records the 0.79.0
register/port, FILE/collection, cooperative control and robot-model contracts.
Its [guide](../offline-services.md) extends the earlier geometry ledgers with
XYZWPREXT metadata and MIRROR; historical native-behavior questions remain open.

See [control notifications](../control-notifications.md) and the
[semaphore/error/lifecycle ledger](control_notification_semantics.json) for
the 0.81.0 manual forms, portable choices and remaining native gaps.
The 0.82.0 [task and file guide](../task-and-file-extensions.md) extends those
ledgers with scoped POST_ERR_L, queued task control and field/record reads.
The 0.83.0 [I/O and argument ledger](io_parameter_semantics.json) adds explicit
indirect port mappings, simulation, independent comments and per-task arguments.
The 0.84.0 [current-state ledger](current_robot_semantics.json) records supplied
robot snapshots, model-derived Cartesian queries, mask/group choices and CURR_PROG.
The 0.85.0 [joint interoperability ledger](joint_interoperability_semantics.json)
records padded model/limit boundaries, register reads and current frame/tool persistence.
The 0.86.0 [register lifecycle ledger](register_lifecycle_semantics.json) records
representation codes, stored widths, grouped clearing and logical unsimulation.
The 0.87.0 [calendar ledger](calendar_clock_semantics.json) records explicit
GET_TIME/SET_TIME, elapsed adapters, packing and frozen snapshot restoration.
The 0.88.0 [task inspection ledger](task_inspection_semantics.json) records
directional lookup, live/caller-rooted state, supplied attributes and portable enums.
The 0.89.0 [file comparison ledger](file_comparison_semantics.json) records
closed named reads, portable comparison/report choices and synchronous printing.
The 0.90.0 [kinematic assignment ledger](kinematic_assignment_semantics.json) records
model-backed whole assignments, selected context, seed requirements and exact interfaces.
The 0.91.0 [pulse ledger](pulse_semantics.json) records rounded output timing,
clock/scheduler servicing, root ownership, overrides and terminal freeze choices.
The 0.92.0 [initialization ledger](initialization_query_semantics.json) records
whole builtin-record queries, partial leaves, read-only validation and retained
whole-container exclusions. It supersedes earlier whole builtin-record UNINIT
restrictions; historical ledgers retain their version-bound scope.
The 0.93.0 [variable inspection ledger](variable_inspection_semantics.json) records
static metadata, type codes, aggregate/resource flag choices, sorted listings,
pagination and output-format capacity checks.
The 0.94.0 [joint geometry ledger](joint_geometry_semantics.json) records supplied
forward conversion in geometry expressions, Cartesian results, ordered capture,
metadata and comparison context. It supersedes older blanket JOINTPOS geometry
exclusions; historical ledgers retain their version-bound scope.
The 0.101.0 [I/O configuration ledger](port_configuration_semantics.json) records
explicit topology and module metadata, staged assignments/modes, host application,
portable status/range choices and independence from logical signal values.

The [group CONFIG text ledger](group_config_text_semantics.json) records
CNV_CNF_STRG, explicit per-group field profiles, status/capacity handling and
calling-root selection. It supersedes that procedure's exclusion in the older
context-free CONFIG ledger while retaining native-mask and controller boundaries.

The [list/table ledger](table_control_semantics.json) adds resident DISP_DAT_T
list navigation and portable COL_DESC_T/XWORK_T table editing over injected keys.
It supersedes older blanket list/table exclusions; native layouts remain
outside the implementation. The [FTX form ledger](form_semantics.json) adds
DISCTRL_FORM source parsing, typed editing, help/choices and nonnested tree groups,
superseding older blanket form exclusions while retaining native binary/ABI limits.

The [logical controller ledger](controller_service_semantics.json) adds six
controller-related calls over explicit ownership/perch/reset/background banks.
It also records zero-address panel I/O, while retaining physical motion, hardware
reset and native TP scan boundaries.

The [vision result ledger](vision_result_semantics.json) adds 19 calls over
completed supplied runs, vision registers and parameter banks. It records sparse
outputs, shared cursor persistence and the NUMSET direction discrepancy, while
retaining image-processing, camera and tracking boundaries.

Generated CLI programs can select their explicit numeric bank from --context or
--registers. An explicit register file overrides the context bank consistently
for numeric and extended services and saved state; see
[numeric-register usage](../numeric-registers.md#generated-scripts).

The [vision I/O ledger](vision_io_semantics.json) adds ten calls for supplied
rasters, image export, reader/view-line results and logical camera/calibration/
display/LED data. It supersedes older blanket image/reader exclusions while
retaining native acquisition, image processing and undocumented save overloads.

The [vision tracking ledger](vision_tracking_semantics.json) adds twelve legacy
queue, lookup/result, supplied-map and outbox calls. It supersedes older blanket
legacy-queue/map exclusions while retaining native motion, delivery and remaining
native/strict behavior boundaries recorded at that milestone.

The [VT queue ledger](vt_queue_semantics.json) adds twelve line-pool, allocation,
acknowledgement, PATH editing, time/flow and weighted-routing calls. It supersedes
older blanket exclusions of these calls. Nullable typed inputs are scoped to
these documented forms; ordinary initialization guards remain. Tray tags,
configured logical arrival times and approximate flow rates do not establish
native tray-cell expansion, calibrated conveyor geometry or physical effects.

The [mixed archive ledger](mixed_archive_semantics.json) adds combined TP/VR
ALLTYPE backup/clear and manifest-based restore. It supersedes older mixed-batch
exclusions while retaining native binary/code-unload boundaries. Hashes bind each
member to one captured batch; cross-store preflight preserves both stores on
failure, and possible variable writes retain FOR-counter guards.

The [VECTOR frame ledger](vector_frame_semantics.json) adds right-VECTOR point
transforms for Cartesian and model-backed joint frames. It supersedes older
blanket VECTOR-transform exclusions, preserving VECTOR left-frame rejection and
exact interfaces. Full affine point semantics, direction subtraction, finite
geometry and detached ordered evaluation are explicit Pythonic choices.

The [nested label ledger](nested_jump_semantics.json) adds nested/sibling
IF/WHILE/REPEAT/SELECT target entry. It supersedes older blanket structured-entry
exclusions while retaining FOR-body, routine/handler and USING capture barriers.
Per-body transfer reports describe source/target paths; direct entry skips header
dispatch and follows the ordinary target continuation and loop back edges.

The [portable expansion ledger](portable_expansion_semantics.json) adds atomic
FILE_LIST formats 0 through 4, concatenated FTX tree fragments and linked-project
ARRAY shape routing. It supersedes the corresponding older exclusions while
preserving historical versions, explicit dimensions, nonnested trees, portable
metadata/status choices and controller evidence boundaries.

The [cooperative input ledger](cooperative_input_semantics.json) adds typed
keyboard FILE READ, explicit plain-pipe wait/snapshot/overflow attributes and
unfinished-stream parsing. It supersedes older blanket exclusions while retaining
explicit input, atomic publication and suspended-state boundaries. The
[VT tray ledger](vt_tray_semantics.json) adds supplied cell geometry, independent
allocation/routing and portable ordering without claiming native calibration.

The [data copy expansion ledger](data_copy_expansion_semantics.json) adds
validated partial aggregate transfers, bounded raw keyboard fields/printable
delimiters and explicit PIP file management. It supersedes the older exclusions
while retaining missing-value reads, complete geometry/service inputs, ownership,
native evidence boundaries and internal strict rejection coverage.

The [source services ledger](source_services_semantics.json) adds opt-in stored
source to Python translation, bounded wildcard COPY/DELETE and root directive
group acquisition. It supersedes those older exclusions while retaining native
PC, physical motion, callee lock scopes and host batch failure boundaries.

The [control and file scope ledger](control_file_scope_semantics.json) adds
active FOR transfers, opt-in callee lock scopes and configured plain pipe
wildcard batches. It supersedes those earlier exclusions while preserving
scope-entry proofs, caller ownership and explicit offline service boundaries.

The [reference, geometry and serial ledger](reference_geometry_serial_semantics.json)
adds captured INTEGER storage counters, VECTOR translation-frame equivalents and
finite P-device streams. It retains aggregate-write protection, explicit origin
CONFIG, bounded byte buffers and separate native/controller evidence boundaries.

The [computed, serial and alpha ledger](computed_serial_alpha_semantics.json)
adds checked private USING records, opt-in host-fed serial waits and supplied
alpha-channel image exports. It preserves storage identity, atomic typed input,
explicit FILE lifetime and independent image-format evidence.

The [private counter, narrow scalar and rename ledger](private_narrow_rename_semantics.json)
adds isolated computed-record counters, checked BYTE/SHORT scalar interfaces and
preflighted same-bank wildcard renames. It supersedes their earlier exclusions
while preserving missing markers, source ownership and partial host-failure evidence.

The [scalar, dynamic and volume ledger](scalar_dynamic_volume_semantics.json)
adds typed scalar SELECT branches, direct narrow variable creation and prepared
virtual cross-volume rename batches. It preserves category separation, exact
named references, missing markers and complete capacity/garbage accounting.

The [counter, Cartesian and STRING-array ledger](counter_cartesian_string_semantics.json)
adds checked narrow counters, private Cartesian routine conversions and inherited
STRING result capacities. It preserves whole-root alias protection, initialized
conversion inputs, concrete array capacity and exact declared linkage contracts.

The [chain, kinematic and palette ledger](chain_kinematic_palette_semantics.json)
adds complete chained ARRAY access, private model-backed routine conversions and
supplied palette images. It preserves rank/alias proofs, explicit robot context,
legacy raster bytes and checked PNG/BMP output publication.

The [joint, XML and question-wildcard ledger](joint_xml_question_semantics.json)
adds complete joint width conversions, atomic aggregate XML leaf updates and
single-character final-basename source matching. Exact linkage, missing markers,
protected fields, explicit services and bounded batch publication remain checked.

The [SELECT, numeric transfer and XML-root ledger](select_numeric_xml_semantics.json)
adds eager typed dynamic CASE labels, checked numeric scalar/ARRAY transfers and
built-in XML record targets. Captured values, source effects, atomic publication,
explicit schemas, protected fields and legacy SELECT guards remain checked.

The [pose, synchronous-call and 16-bit PNG ledger](pose_sync_png16_semantics.json)
adds checked individual positional variable transfers, private synchronous source
entries and supplied two-byte image samples. It preserves complete conversion
inputs, caller ownership, root cleanup, artifact hashes and byte quotas.

The [motion request ledger](motion_request_semantics.json) supersedes blanket
MOVE/hand/ATTACH/RELEASE translation exclusions in older contracts. The explicit
request model remains separate from native motion, trajectories and feedback.

The [motion control ledger](motion_control_semantics.json) supersedes the first
request ledger's HOLD/UNHOLD/CANCEL and blanket WITH exclusions. Native motion,
pending execution, other WITH variables and synchronization remain separate.

The [local motion ledger](motion_handler_semantics.json) supersedes prior blanket
local-handler and delayed-response exclusions for Boolean clauses and finite
synchronous scopes. Native timing, node conditions and NOWAIT queues remain outside it.

The [motion timeline ledger](motion_timeline_semantics.json) supersedes blanket
AT NODE/TIME exclusions for local predicates with complete explicit schedules.
Native timing, inferred arrivals and queued motion remain separate.

The [FILE cancellation ledger](file_cancel_semantics.json) supersedes blanket
CANCEL FILE translation exclusions for explicit cooperative typed reads. Native
pending writes, default aliases and controller status/timing remain separate.

The [positional ARRAY ledger](positional_array_semantics.json) supersedes blanket
whole-array Cartesian/joint-width exclusions for anonymous source values and
explicit same-rank variable prefixes. Named source interfaces and joint/Cartesian
ARRAY kinematics retain their separate boundaries.

The [kinematic ARRAY ledger](kinematic_array_semantics.json) supersedes blanket
joint/Cartesian whole-array source exclusions for anonymous values with explicit
models/adapters. Named interfaces, storage-only variable transfers and physical
robot/native ABI acceptance remain separate.

The [READ_KB cancellation ledger](read_kb_cancel_semantics.json) supersedes its
blanket exclusion from explicit FILE cancellation. Blocking per-key checkpoints,
zero-time polling, output preservation and retained editor ownership are explicit
offline policies; native keyboard/status acceptance remains separate.
