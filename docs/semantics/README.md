# Semantic notes

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
