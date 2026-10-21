# Semantic notes

These JSON notes describe manual rules, conservative prototype contracts, test
locations and unresolved behavior. They are implementation documentation, not
native compiler or controller acceptance evidence. See [references](../references.md)
for the manual edition and page numbering.

Since 0.51.0, public translation uses [Pythonic numeric behavior](../numeric-modes.md).
Exact REAL, trig, conversion and VECTOR restrictions in the older ledgers describe
the preserved conservative research contract. They do not limit the current
Pythonic mode. Earlier ordering rejections also belong to that conservative
contract; see the [current evaluation rules](../evaluation-order.md). A public
strict mode remains a future milestone.

Each ledger is relative to this directory. Test paths inside its text are relative
to the repository root. Private corpus reports and machine-specific provenance
are kept outside public documentation.

| Topic | Ledger |
| --- | --- |
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
| Positional routine | [positional_routine_semantics.json](positional_routine_semantics.json) |
| Predefined | [predefined_semantics.json](predefined_semantics.json) |
| Select | [select_semantics.json](select_semantics.json) |
| Source | [source_semantics.json](source_semantics.json) |
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
