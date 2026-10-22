# Initialization queries

Pythonic `UNINIT(storage)` returns BOOLEAN for scalar and JOINTPOS storage and
for whole CONFIG, VECTOR, POSITION, XYZWPR and XYZWPREXT records. Builtin records
can be variables, fields of user structures or individual ARRAY elements.

```karel
PROGRAM DEMO
VAR point: VECTOR
    fresh,partial,complete: BOOLEAN
BEGIN
  fresh=UNINIT(point)
  point.x=1
  partial=UNINIT((point))
  IF UNINIT(point) THEN
    point=VEC(1,2,3)
  ENDIF
  complete=NOT UNINIT(point)
END DEMO
```

`FRESH`, `PARTIAL` and `COMPLETE` are TRUE. A whole builtin record is uninitialized
when any scalar leaf or complete nested record is uninitialized. POSITION includes
its location, three orientation vectors and CONFIG data; XYZWPREXT includes its
three external-axis leaves. A complete explicit assignment supplies those values
under the existing [Cartesian conversion rules](position-conversions.md).

The query reads storage without initializing, copying or replacing it. It works
on read-only orientation fields and routine parameters. Pythonic parentheses
preserve the storage query; computed subscripts evaluate once. Earlier subscript
effects persist if a later check fails, as in ordinary expression evaluation.
Builtin records nested in larger containers remain individually queryable.

Every known leaf must still have its ordinary valid scalar type and domain.
The query checks all fields, even if an earlier field was uninitialized. Malformed
host-supplied records raise an error without changing the source or assigning the
query result. Initialized records need not describe a proper rotation, reachable
pose or valid robot configuration: geometry operations perform their own checks.

Whole ARRAY, PATH and user STRUCTURE queries remain rejected, following the
manual's explicit exclusions. Whole FILE and QUEUE_TYPE queries also remain
blocked. Constants, literals, constructors and function results do not identify
queryable storage. BYTE remains distinct: unknown BYTE contents are not an
uninitialized value, and BYTE queries remain rejected even after a write.

Existing scalar and JOINTPOS behavior is retained. Whole copies still require
complete values. Internal strict-mode record queries remain blocked; public strict
mode is a future milestone.

## Python embedding and observations

No service bank, robot context or callback is required:

```python
from karel2py import translate

source = """PROGRAM DEMO
VAR point: VECTOR missing: BOOLEAN
BEGIN point.x=1 missing=UNINIT(point) END DEMO"""
result = translate(source)
namespace = {"__name__": "initialization_example"}
exec(result.python_source, namespace)
Program = namespace["Program"]
program = Program()
state = program.run()
assert state["MISSING"] is True
assert state["POINT"]["Y"] == {"uninitialized": True}
assert program.service_requests == ()
assert result.report["initialization_queries"][0]["operand_type"] == ("VECTOR",)
```

The translation report records `initialization_queries` with body, line, column,
operand type, selector kind, grouping and single-evaluation facts. These are
source observations and contain no storage values. `initialization_query_policy`
describes the portable rule. Queries generate no service request.

The authored [vector example](../examples/record_initialization.kl) and
[pose example](../examples/pose_initialization.kl) have independent expected
snapshots. The [semantic ledger](semantics/initialization_query_semantics.json)
records the manual locator and implementation boundaries. The recursive
partial-record rule is a portable choice, with no claim about native allocation
flags or controller runtime behavior.
