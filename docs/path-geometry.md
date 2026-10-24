# PATH sizing and line/plane geometry

`NODE_SIZE` and `INTSCT_VL_PL` have Pythonic offline implementations. Both work
with supplied typed PATH data and require no controller or vision service.

## Portable node size

`NODE_SIZE(path)` returns the packed size of its node schema, including node
data fields and excluding the PATH header. Values need not be initialized and
the result does not depend on the number of nodes.

| Leaf | Portable bytes |
| --- | --- |
| BYTE / BOOLEAN | 1 |
| SHORT | 2 |
| INTEGER / REAL | 4 |
| STRING | Declared capacity |
| JOINTPOS | Four per declared axis |
| ARRAY | Element size times its concrete dimensions |
| Record | Sum of its field sizes |

There is no alignment, string prefix, resource descriptor or native PATH control
data in this calculation. VECTOR is 12 bytes, CONFIG 16, XYZWPR 40, XYZWPREXT 52
and POSITION 64. The default node containing NODE_POS: POSITION is therefore 64.
Named nested arrays count each dimension once. The widths match the portable
default binary scalar fields, with explicit capacity-sized strings.

This is a schema-size convention, not a native FANUC memory layout. Aggregate
PATH file serialization is still unavailable. Use the existing checked scalar
FILE operations for authored portable formats; native binary offsets cannot be
inferred from this result. Unknown capacities and embedded resources fail.

## Explicit line/plane intersection

`INTSCT_VL_PL(lines, plane, points, status)` accepts these structural field schemas.
User type names and field declaration order may differ; field names/types must
match, without additional fields.

| Record | Fields |
| --- | --- |
| Input NODEDATA | DIR: VECTOR, POL: VECTOR, MODEL_ID: INTEGER |
| Input PATHHEADER | GRP_NUM: INTEGER, UFRM_NUM: INTEGER, FOCAL_POINT: VECTOR |
| Output NODEDATA | POS: VECTOR, POL: VECTOR, MODEL_ID: INTEGER |
| Output PATHHEADER | GRP_NUM: INTEGER, UFRM_NUM: INTEGER |

Each input defines an infinite line through FOCAL_POINT along DIR. The supplied
complete POSITION/XYZWPR/XYZWPREXT defines the plane's XY surface, using the
existing proper-matrix and Euler conventions. All values must already use the
same application frame; no calibration or robot frame conversion is inferred.

For plane point O, unit normal N, focal point F and normalized direction D, the
intersection is `F + t*D`, with `t = N dot (O-F) / (N dot D)`. Polarity is projected
onto the plane along D and normalized, retaining the direction implied by the
signed distance. Negative distances are valid for this infinite-line model.
Coincident focal/plane data or a zero projected polarity is degenerate.

Successful results append to the output PATH, retain model IDs and copy group/
frame identifiers. Existing nodes remain intact. A nonempty output must already
use the same identifiers. Groups are 1..32 and user-frame IDs 0..32767; these
are supplied metadata rather than discovered controller settings.

The complete batch is staged before changing output nodes or header. Each input
node consumes an ordinary execution step. Invalid/uninitialized values, improper
matrices and exhausted step budgets raise while retaining output data. Existing
disjoint-output and transitive FOR-counter checks apply, including aliases into
the output header. No handlers run inside this synchronous calculation.

| Status | Meaning |
| --- | --- |
| 0 | Results appended, or empty input accepted with its header |
| 1 | Parallel line: absolute unit-direction denominator at most 1e-12 |
| 2 | Degenerate direction, projected polarity or zero focal-plane distance |
| 3 | Existing output uses different group/frame identifiers |
| 4 | Appending would exceed 32767 nodes |

Nonzero statuses retain the complete output. These are portable codes, not
native vision alarms. The [authored example](../examples/path_geometry.kl)
constructs two view lines and intersects them with an explicit plane, producing
points at (0,0,0) and (10,0,0). It clears previous fixture nodes so JSON replay
is deterministic; the built-in itself appends.

```sh
python -m karel2py examples/path_geometry.kl -o geometry.py --report geometry-report.json
python geometry.py --state-out geometry-state.json
```

The report includes `path_geometry_policy`; the
[semantic ledger](semantics/path_geometry_semantics.json) records provenance and
portable choices. This does not acquire camera images, run V_FIND_VLINE, wait
for asynchronous vision data, reconstruct calibration or certify native geometry.
`QUEUE_ATTACH` remains a separate unimplemented message-attachment facility,
independent of the implemented INTEGER-buffer QUEUE_TYPE operations.
