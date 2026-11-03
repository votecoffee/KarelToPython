# Dynamic typed data arrays

Pythonic CREATE_VAR accepts `ARRAY OF` followed by a supported data type or a
resolved type alias. A named ARRAY type may also receive extra outer dimensions.
These are authored allocation/layout extensions with ordinary offline data
storage. Native allocation, binary environments and controller equivalence remain
unverified. Strict mode remains a future milestone.

```karel
TYPE row_t=ARRAY[3]OF INTEGER
-- Inside BEGIN:
CREATE_VAR('CACHE','ITEM','','ROW_T',0,2,0,0,status)
-- ITEM is now ARRAY[2] OF row_t, with logical dimensions (2,3).
```

`ARRAY OF ROW_T` with the same dimension arguments creates that same layout.
The [named-array example](../examples/dynamic_array_named.kl) fills it through an
exact BYNAME formal and transfers its second row using GET_VAR.

## Type forms and dimensions

| Requested type | Dimension arguments | Result |
| --- | --- | --- |
| `ARRAY OF INTEGER` | inner=3, middle=2, outer=0 | Anonymous ARRAY[2,3] OF INTEGER |
| `ARRAY OF STRING[4]` | inner=2, other slots zero | ARRAY[2] OF STRING[4] |
| `ARRAY OF item_t` | inner=2, other slots zero | ARRAY[2] of the supplied named data record |
| Named `row_t=ARRAY[3]OF INTEGER` | inner=2, other slots zero | ARRAY[2] OF row_t |
| Named `matrix_t=ARRAY[2,3]OF INTEGER` | inner=2, other slots zero | ARRAY[2] OF matrix_t; logical dimensions (2,2,3) |
| Named ARRAY with all slots zero | No new dimensions | Existing exact named ARRAY type |

Dimension slots describe the new outer storage, in the existing inner-to-outer
argument order. Named inner ARRAY components retain their identities and physical
boundaries. Logical rank includes every component and remains at most three.
No flattening, reshaping, anonymous nested components or runtime wildcard sizes
are introduced. Used slots remain contiguous positive INTEGER values in 1..32767.

`ARRAY OF` requires a positive inner slot. It accepts existing scalar data,
bounded STRING, VECTOR/CONFIG/Cartesian/joint and resolved data-record/ARRAY
aliases. STRING defaults to capacity 12; explicit capacities stay within 1..254.
Case and surrounding/repeated separating spaces are normalized. Inline recursive
syntax such as `ARRAY OF ARRAY OF INTEGER` is not parsed: supply a named inner
type. [FILE arrays](dynamic-file-arrays.md) use separate descriptor-allocation
rules. [PATH/QUEUE arrays](collection-arrays.md) now use separate reference-only
contracts; resource fields remain excluded.

The type program still selects explicitly attached source layouts. A blank type
program uses the executing source module; no controller or caller-local layout
is discovered. The [linked owner example](../examples/dynamic_array_project/main.kl)
uses the library's row definition even when the caller has another local shape.

## Initial data, references and operations

Each created component owns fresh ordinary storage. Scalar missing markers,
unknown BYTE contents, SHORT sentinels and STRING capacities retain their existing
rules. Builtin data records and nested arrays are independent objects. Direct
positional/joint element types retain their required group metadata; that value
does not select a robot or supply frames, tools or an axis model.

Exact BYNAME formals borrow the created data. Chained element access, source
copies, scalar and aggregate READ/WRITE, ARRAY_LEN, GET_VAR/SET_VAR and selected
row transfers use existing typed storage rules. The
[record example](../examples/dynamic_array_records.kl) reads a created record
ARRAY through a routine. The [pose example](../examples/dynamic_array_pose.kl)
uses a separately supplied robot model for later joint/Cartesian conversion.
Creation alone performs no geometry or motion.

Renaming the root or its unattached namespace preserves captured references,
child identities, creation metadata and entry hints. Pause/resume retains the
same borrowed root. The [linked rename example](../examples/dynamic_array_lifetime_project/main.kl)
continues editing a captured array after its root name changes.

## Preflight, reservation and failure

All data creation schemas now use bounded validation before recursive collection
checks: at most 64 schema levels and 32767 scalar leaves per root. Reject malformed
or cyclic schemas, empty data records, nonconcrete dimensions and anonymous inner
ARRAY components before allocation. Shared immutable schemas retain ordinary
per-pass accounting; schema validation does not allocate data objects.

The combined created-variable reservation remains 32767 units. Data arrays cost
all scalar leaves across new outer dimensions and named children. FILE and
collection descriptors keep their separate existing accounting. Existing statuses
remain: 5 for invalid type/dimensions/group or per-root schema bounds, 6 for total
reservation overflow, and the established collision/name/pool statuses otherwise.

The budget checkpoint still follows initial preflight. Recheck owner lifetime,
bank identity, root collisions and fresh reserved capacity before publication.
A callback cannot replace the bank, claim the root or consume remaining capacity
and have its completed changes overwritten. The resolved immutable type schema
is captured before that checkpoint; changing a supplied type map cannot retarget
an in-progress creation.

## Saved contexts, archives and reports

JSON records the concrete outer/inner schemas, values and creation policy. Restore
validates each schema and the combined reservation before decoding its data.
Fresh source declarations do not retype an already restored root. Existing VR
SAVE/CLEAR/LOAD and explicit DRAM restoration retain named children, partial data
and compatible aliases. See the [archive example](../examples/dynamic_array_archive.kl).
No live bindings, suspended stacks or native power-cycle behavior are serialized.

`dynamic_array_creation_policy` describes accepted forms and boundaries. See the
[regressions](../tests/test_dynamic_data_arrays.py) and
[semantic ledger](semantics/dynamic_array_creation_semantics.json). General
[dynamic variable rules](dynamic-variables.md) continue to govern names, pools,
metadata, statuses and collision protection.
