# Selected ARRAY variable transfers

Pythonic GET_VAR and SET_VAR can transfer rows and planes selected inside flat
multidimensional ARRAYs. Named variable paths, SET_VAR source expressions and
GET_VAR data outputs use explicit data-transfer rules. This is an authored
extension, without native source/layout/controller claims. Strict mode remains
future work.

```karel
VAR matrix:ARRAY[2,3]OF INTEGER row:ARRAY[3]OF INTEGER entry,status:INTEGER
-- Inside BEGIN:
GET_VAR(entry,'','MATRIX[1]',row,status)
SET_VAR(entry,'','MATRIX[2]',row,status)
GET_VAR(entry,'','ROW',matrix[1],status)
SET_VAR(entry,'','ROW',matrix[2],status)
```

| Transfer form | Behavior |
| --- | --- |
| Named source `MATRIX[1]` | Snapshot the selected original row after GET output selectors |
| Named destination `CUBE[2]` | Prepare data for the selected original plane |
| GET_VAR data output `matrix[index()]` | Capture that row once at the output argument position |
| SET_VAR data input `matrix[index()]` | Capture an independent typed source value before later selectors |

See [named paths](../examples/prefix_variable_paths.kl),
[source/output capture](../examples/prefix_variable_values.kl),
[record conversion](../examples/prefix_variable_records.kl) and
[explicit model conversion](../examples/prefix_variable_models.kl).

## Named paths and namespaces

A final incomplete flat ARRAY selection resolves to existing suffix cells.
Prefixes inside separately named components and checked record fields work too.
Current/attached programs and explicit root/system/full-path binding precedence
retain their existing rules. No routine-local discovery or binding is created.

For these two transfers, adjacent numeric bracket groups combine before lookup:
`CUBE[2][1]` selects the same row as `CUBE[2,1]`, and `MATRIX[2][3]` selects a
complete scalar element. Complete joint-axis paths can similarly combine their
ARRAY indexes and final axis. A field access still requires a complete record;
a partial row followed by `.FIELD` is invalid.

Indexes in quoted paths are checked one-based decimal integers. Expressions,
variables, calls and arbitrary Python access are not evaluated. Source indexes
retain ordinary one-time expression evaluation. General resolver and BYNAME
calls keep their complete-reference grammar; this extension exposes data
transfers without introducing a live view or general prefix reference.

The [linked project](../examples/prefix_variable_project/main.kl) transfers across
attached owners. The [dynamic-bank project](../examples/prefix_variable_dynamic_project/main.kl)
uses a created GRID root, then transfers its selected row across modules.

## Types, data and conversion

Each selected suffix retains its actual dimensions, terminal capacities and
named child layouts. Existing variable transfer rules apply: equal logical rank,
copy the smaller row-major terminal count and preserve every unused receiver
cell. Numeric, STRING, compatible record, context-free positional and explicitly
model-backed conversions use their existing domains. No equal-count reshape or
inferred robot geometry is introduced.

Missing scalar leaves retain status 12311 when copied. Unknown BYTE data stays
unknown and does not become an invented number or missing-data query result.
A prefix destination must retain shaped containers. A whole missing ARRAY or
nested record/ARRAY container cannot replace that selected range. Such a failure
preserves its data, entry, status and cache; ordinary whole-reference missing
container transfers retain their established behavior.

Prefix capture validates the entire containing ARRAY's schema, storage and known
leaves, including unselected data. It therefore cannot hide malformed data in
another row. Missing source containers in a named prefix fail lookup with status
1. Incompatible type/rank retains status 3. Configured model/data failures raise
without publishing an outer transfer.

## Capture, aliases and atomic publication

SET_VAR snapshots its typed input at its argument position. GET_VAR captures its
named source after all output selectors. Captured output rows and named targets
keep their original cells through later adapter effects, pauses and root
replacement. Existing element/record/joint aliases remain attached after data
replacement. Ordinary routine prefix arguments remain independent source copies.

Check output overlap before lookup, including every selected descendant of a
GET_VAR row output. A SET_VAR named target also checks its selected addresses
against entry/status. Recheck prefix destination overlap after model effects:
an adapter cannot introduce a new alias to metadata and have it overwritten.
Metadata outside the selected range may be used when otherwise disjoint.

Validate complete converted data and selected destination storage before
publication. Publish data before allocating a cache ID or writing entry/status.
A rejected prefix write allocates no ID and changes no outer outputs; completed
source, selector and adapter effects remain visible. Missing-container and late
narrowing/model failures follow the same rule.

Successful lookups retain context-local cache IDs. Case variants reuse the
existing uppercase key; comma and chained bracket spellings keep separate keys.
Traversal normalization does not rewrite supplied full-path bindings or merge
cache identities. Cache IDs and private captures are omitted from saved JSON.

## Boundaries and reports

Data-only schemas remain bounded to three logical ARRAY dimensions, 32767
containing ARRAY scalar leaves and 64 data-schema levels. Active FOR roots,
constants, CONFIG/POSITION field protection, resource exclusions and explicit
model/owner checks remain in force. Other service output parameters, general
BYNAME aliases and VariableStore bindings do not accept prefix capture objects.
No live references, callbacks or suspended stacks are persisted.

`prefix_variable_transfer_policy` describes this extension. Source-located
`array_prefix_targets` also records GET_VAR data-output selections. See the
[regressions](../tests/test_prefix_variable_transfers.py) and
[semantic ledger](semantics/prefix_variable_transfer_semantics.json).
