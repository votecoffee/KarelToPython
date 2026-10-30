# Source ARRAY schemas, STRING capacities and layouts

Pythonic source can copy compatible data ARRAYs into a receiver's declared names,
bounded STRING capacity and flat/nested storage layout. Logical rank and every
dimension must match. These are explicit source conversions at assignment,
ordinary argument and RETURN boundaries; generic runtime typed-reference helpers
keep their exact contracts.

| Source boundary | Result |
| --- | --- |
| Same terminal type, different ARRAY/component names | Independent value with receiver names |
| STRING elements with different bounded capacities | Validate source, then right-truncate or widen each known string |
| Flat matrix/cube and named-row/plane layout | Rebuild receiver components without changing logical coordinates |
| Assignment through a bare generic ARRAY formal | Use its actual borrowed receiver schema |
| RETURN from named storage or generic formals | Independent value with the declared result's schema |

Numeric, Cartesian, joint-width and explicit-model ARRAY conversions also use
matching logical dimensions across storage layouts. Their scalar rules remain
in the [numeric](numeric-arrays.md), [positional](positional-arrays.md) and
[model-backed](kinematic-arrays.md) guides.

~~~karel
TYPE row_t=ARRAY[2]OF INTEGER rows_t=ARRAY[2]OF row_t
     matrix_t=ARRAY[2,2]OF INTEGER
VAR original:matrix_t result:rows_t
BEGIN
  -- Initialize any desired source leaves; permitted missing leaves stay missing.
  result=original
END
~~~

Both values have logical dimensions (2,2). result owns two row_t children.
Changing result[2,2] does not change original[2,2]. A (1,4) or one-dimensional
four-element receiver is rejected even though its total element count is four.

## Names, layout and partial data

Named outer ARRAYs and separately named components retain their own receiver
identities. Conversions do not rename source objects or expose subarray views.
Rank remains one through three and allocation remains bounded at 32767 scalar
leaves and 64 schema levels. Anonymous formal/result wildcards inherit concrete
dimensions; named storage remains concrete.

Identical scalar/data-record/joint terminal types may be copied across ARRAY
names and layouts. Record terminal schemas retain exact nominal identity; this
does not coerce different STRUCTURE types or the surrounding record schema.
FILE/PATH/QUEUE values do not become copyable data ARRAY elements.

Existing missing scalar markers remain missing. Same-type BYTE copies retain
unknown BYTE contents without allowing numeric extraction or UNINIT queries.
Known source domains, SHORT sentinels, CONFIG bounds, finite numeric values and
POSITION orientation protection retain their ordinary checks. Same-type partial
pose/joint copies do not infer geometry or require a robot model.

## STRING capacities

Concrete capacities remain 1 through 254 ASCII characters. Every known source
value must first fit its own declared capacity. Malformed overlong or non-ASCII
source contents fail instead of being hidden by truncation. After validation,
each known value uses the receiver capacity under ordinary scalar right-truncation;
widening preserves its text. Empty strings remain initialized and missing values
remain missing.

An omitted anonymous ARRAY-result STRING capacity inherits concrete returned
storage, including named source storage. The function result retains that
capacity. A later assignment or source routine boundary may independently convert
it to another capacity. Named declarations never gain an inferred STRING size.

## References, private arguments and generic receivers

An ordinary argument already accepted by its declared formal keeps existing
reference/value behavior. In particular, a compatible generic formal can still
borrow named or nested caller storage. It is not silently detached.

A conversion into an otherwise incompatible named/bounded interface creates
private writable storage. Exact forwarding inside that private value may alias
it, but retained handlers, timers, pause/resume, failures, stop and return never
copy it back. Passing a generic formal onward to an explicit named interface uses
a private checked conversion when static names are unknown, even if its current
runtime name happens to match.

Whole assignment through a bare generic ARRAY formal uses the actual receiver
schema supplied by its caller. The receiver retains its names, component children
and STRING capacity. RHS capture finishes before receiver metadata lookup; this
adds no source selector call or guessed dynamic caller scope.

## Capture, publication and exact interfaces

Capture and conversion run once before later arguments or assignment selectors.
RETURN prepares its declared schema before frame/counter cleanup. Existing
exact-copy destination checks retain their prior timing; a shape error at the
final write can retain target-selector effects. All copied
source data and every output conversion are staged before publication. A late
invalid leaf, overflow, dimension mismatch or adapter failure preserves the
receiver. Earlier explicit source/adapter effects remain without rollback/retry.

Model-backed changes still preflight complete geometry before the first adapter
and use explicit caller group/frame/tool/current inverse seed. Layout rebuilding
does not acquire robot state, update current state, introduce checkpoints or move
hardware.

BYNAME, linked declaration/definition signatures, raw callback results and generic
runtime checked/value_argument/array_result helpers remain exact. The explicit
runtime.convert_array_schema(target_spec, value, line=None) helper implements
data schema conversion; generated generic assignments use
State.array_assignment_value(value, target_spec, line=None). Public strict mode
remains future work. No native ARRAY layout/ABI or controller equivalence is implied.

## Reports, examples and persistence

array_schema_conversions records source/target specs, operation, location,
one-time independent capture and a primary schema_change_kind: nominal_identity,
string_capacity, component_layout, dynamic_receiver or declared_result.
The argument tag can be null when only a previously unknown concrete dimension
requires runtime checking. actual_receiver_schema marks generic target resolution.
Named rows also appear
in named_array_conversions; array_schema_policy describes these offline rules
with controller_validated=false.

Context JSON preserves concrete receiver schemas, names, capacities, values and
missing markers. It omits private routine cells, handlers, live timer claims and
suspended stacks; saved data does not resume an operation.

See [nominal copies](../examples/array_schema_identity.kl),
[STRING capacities](../examples/array_string_capacities.kl),
[logical layouts](../examples/array_logical_layouts.kl),
[model layouts](../examples/array_schema_model.kl),
[typed linked copies](../examples/array_schema_project/main.kl),
[linked generic receivers](../examples/array_schema_receiver_project/main.kl),
and [regressions](../tests/test_array_schema_conversions.py).
