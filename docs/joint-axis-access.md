# Checked Pythonic joint-axis access

Pythonic conversion accepts one-based JOINTPOS axis subscripts as an explicit
input extension. The selected cell is ordinary finite REAL storage, using the
existing portable joint-value conventions. No native KAREL field/index syntax,
compiler acceptance, controller behavior or physical axis units are inferred.

~~~karel
VAR joints:JOINTPOS3 value:REAL
BEGIN
  joints[1]=1.25 joints[2]=-2.5
  value=joints[2]
END
~~~

The third axis remains missing. Reading an initialized axis does not require a
complete joint pose. An ordinary UNINIT query can inspect a selected REAL cell;
reading a missing axis raises instead of inventing zero. Complete geometry,
model conversion and joint-width changes retain their existing full-input checks.

## Types and bounds

JOINTPOS1 through JOINTPOS9 retain their declared width; bare JOINTPOS is nine
slots. Each final axis index must be INTEGER-compatible and within 1..width.
BOOLEAN truthiness, REAL indexes, implicit axis-to-INTEGER conversion and native
joint field names such as J1 are not added. A REAL axis cannot become a FOR counter
or an INTEGER/status output alias. No robot service or joint_axes constructor
context is needed for this data-only operation.

Complete ARRAY prefixes may precede the axis, across flat, separately named and
chained components, including nested record fields and exact routine formals.
For example items[1,2][3] and items[1][2][3] select the third axis of a two-dimensional
ARRAY's joint element. A three-dimensional ARRAY may have a fourth subscript
for its joint axis; this does not add four-dimensional ARRAY declarations.
Incomplete flat ARRAY rows remain unavailable.

## Capture and protection

Evaluate the base once, then all indexes once from left to right before checking
bounds, matching complete ARRAY access. Assignment captures the RHS before target
selectors. A function-result base remains an independent value if an index call
changes the original source.

Capture validates the declared source schema, selected ARRAY containers, exact
joint width and list storage before returning an ordinary REAL reference. A
substituted joint/ARRAY schema cannot silently widen the source declaration.
Unselected numeric axes may remain missing; an axis read does not certify those
other values as valid geometry. Missing whole containers cannot be indexed.

Exact REAL formals retain writable axis aliases. Grouped actuals use private
values without copy-back. Ordinary whole-joint replacement retains the axis list,
so captured aliases stay attached. Pause/resume retains those references without
repeating selectors. Existing whole-root FOR, readonly POSITION/CONFIG, service
overlap and task-lifetime guards remain in force. The legacy translator and
generic indexed_type helper retain their ARRAY-only contracts.

## Input, paths and persistence

READ, text/binary FILE input, scalar conversion outputs and cooperative serial
reads accept these REAL cells. Existing complete-response preflight, cursor
rollback, cancellation and pending-read cleanup apply. No new device opens.

Explicit GET_VAR/SET_VAR and BYNAME paths accept joint axes, including nested
fields, ARRAY terminals and foreign bindings. Paths use declared joint schemas;
failed path resolution retains status 1, copied missing axis data retains 12311,
and normalized lookups retain existing cache rules. No system-variable or robot
schema is discovered. BYNAME remains exact-type reference binding.

Context JSON preserves ordinary joint axes and partial markers. It does not save
captured references, source selectors or paused execution. Reports expose
joint_axis_accesses with source location, joint width, selected REAL type and
one-time/schema-check metadata, plus joint_axis_policy. Both normal and label-
dispatched source use the same captured access.

See [authored tests](../tests/test_joint_axis_access.py),
[values](../examples/joint_axis_values.kl), [aliases](../examples/joint_axis_aliases.kl),
[binary input](../examples/joint_axis_file.kl), [explicit paths](../examples/joint_axis_paths.kl),
[linked aliases](../examples/joint_axis_project/main.kl),
[generic linked arrays](../examples/joint_axis_array_project/main.kl) and the
[semantic ledger](semantics/joint_axis_semantics.json).
