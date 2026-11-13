# Explicit robot system variable transfers

Pythonic GET_VAR and SET_VAR now accept bounded literal frame/tool paths when an
explicit RobotContext is supplied. These are checked offline data transfers.
They share the existing tables and active selections without creating live aliases.

```karel
VAR point:XYZWPREXT entry,status:INTEGER
BEGIN
  GET_VAR(entry,'*SYSTEM*','$MNUFRAME[1,2]',point,status)
  point.ext2=42
  SET_VAR(entry,'*SYSTEM*','$MNUTOOL[1,7]',point,status)
  SET_VAR(entry,'*SYSTEM*','$MNUTOOLNUM[1]',7,status)
```

## Paths and values

The program argument must be empty, SYSTEM or *SYSTEM* for automatic robot-path
lookup. Case is ignored. Existing explicit full-path and root bindings retain
precedence, including their existing schemas and protection. Other namespaces,
BYNAME and the default resolver do not discover these endpoints.

[VAR_INFO](variable-inspection.md) can inspect these same readable paths for
type and initialization metadata. It preserves the table, active selection
and transfer cache.

| Quoted path | GET_VAR | SET_VAR |
| --- | --- | --- |
| `$MNUFRAME[g,n]`, `$MNUTOOL[g,n]` | Complete detached configured Cartesian representation | Complete Cartesian replacement; may populate a numbered row |
| `$GROUP[g].$UFRAME`, `$GROUP[g].$UTOOL` | Complete detached selected row | Complete replacement of an existing selected row |
| `.LOCATION`, `.LOCATION.X/Y/Z` | VECTOR or REAL value | Staged location edit |
| `.CONFIG_DATA` and its declared fields | CONFIG, INTEGER or BOOLEAN value | Checked staged configuration edit |
| `.NORMAL`, `.ORIENT`, `.APPROACH` and X/Y/Z descendants | Independent orientation value | Rejected |
| `.EXT1`, `.EXT2`, `.EXT3` | REAL from a configured XYZWPREXT row | Staged edit of that existing extended row |
| `$MNUFRAMENUM[g]`, `$MNUTOOLNUM[g]` | Selected INTEGER ID | Validate the supplied row before selecting it |

Indexes are literal decimal integers, with groups checked by RobotContext and
row numbers in 0..32767. Quoted expressions, calls, negative/chained/extra indexes,
unknown fields and arbitrary dollar roots are rejected. No quoted text is evaluated.

Whole GET retains the row's actual POSITION, XYZWPR or XYZWPREXT representation
before ordinary context-free transfer conversions. Whole SET retains its complete
supplied Cartesian representation, including external axes. Field edits preserve
the existing representation and every unselected value. EXT fields require an
existing XYZWPREXT row. Direct source axis fields use the same table, and whole
direct reads return POSITION. See [source assignments](system-pose-writes.md).

The existing numeric narrowing, CONFIG-word and Cartesian data rules apply.
Whole [model-backed system transfers](system-variable-models.md) now convert
rows to JOINTPOS GET outputs and JOINTPOS SET inputs to XYZWPREXT using the
calling root group's explicit model. Field and selection paths keep their
ordinary data rules. Modeled SET requires an absent numbered or complete old
row; use an explicit Cartesian SET to repair malformed existing storage.
Partial or invalid data cannot be published into a
robot table. Whole numbered writes can repair a malformed old row; field edits
require a complete valid old row. A selection setter can repair a missing old
selected row, but its new row must be complete and configured.

## Capture, errors and publication

SET_VAR snapshots its typed input before later argument selector effects.
GET_VAR reads the named row after output selectors. Existing ordinary expression
effects remain if a subsequent lookup or validation fails. An active target uses
the selected row at lookup. Final validation and publication introduce no
callback or pause. Model-backed calls run their synchronous model
during preparation and retain the selected endpoint and output participants
through budgeted capture and final publication; conflicting edits reject.

Lookup and configured-row validation failures return status 1; incompatible data
returns status 3. These change only status, preserving data, entry and cache.
Invalid transferred values, geometry, CONFIG domains or new selection targets
raise a source-line runtime error before publication.
They preserve the previous table/selection, entry, status and cache. Previously
completed source effects remain visible. Successful operations publish data before
allocating the usual context-local cache ID and writing entry/status.

Metadata and GET outputs cannot alias any cell in the selected configured row.
Active-row transfers protect the selection used for lookup; selection setters
also protect the new selected row. Overlap checks precede row validation, so
failure status cannot mutate an invalid row. This includes explicitly supplied host references. No writable endpoint is
returned, bound or retained. Direct READ/service outputs and routine arguments
keep their existing reference and private-value rules. FOR/timer protections and
ordinary explicit VariableStore transfers retain their existing checks.

## Saved state and evidence

Existing RobotContext JSON retains published representations, external axes and
IDs. Cache IDs, endpoint snapshots, callbacks and suspended execution are not
serialized. Saving or loading connects to no controller. No native table layout,
physical motion, source-compiler acceptance or strict equivalence is claimed.

`system_variable_transfer_policy` records the scope and boundaries. GET_VAR and
SET_VAR observations retain operation, source line and outcome without payloads.
See the [regressions](../tests/test_system_variable_transfers.py),
[semantic ledger](semantics/system_variable_transfer_semantics.json),
[whole-row example](../examples/system_variable_rows.kl),
[field example](../examples/system_variable_fields.kl),
[extended-axis example](../examples/system_variable_axes.kl),
[selection example](../examples/system_variable_ids.kl),
[linked project](../examples/system_variable_linked/main.kl) and
[handler project](../examples/system_variable_handler/main.kl).
