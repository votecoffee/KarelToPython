# Named and component ARRAY conversions

Pythonic source conversions now accept named outer ARRAY types and matching
separately named nested ARRAY components at assignment, ordinary argument and
RETURN boundaries. Each converted value uses the receiver's schema and nominal
component names. The source retains its own type and storage.

| Terminal change | Existing conversion contract |
| --- | --- |
| INTEGER/BYTE/SHORT between integral domains, or to REAL | Checked domains and permitted missing scalar leaves |
| POSITION, XYZWPR, XYZWPREXT between representations | Complete finite poses, CONFIG and valid POSITION matrices |
| JOINTPOS width changes | Complete axes, zero padding and zero-only discarded axes |
| JOINTPOS to/from Cartesian representations | Explicit model/adapters, selected frame/tool/group and supplied inverse seed |

These changes extend the [numeric](numeric-arrays.md),
[positional](positional-arrays.md) and [model-backed](kinematic-arrays.md)
ARRAY policies. They retain those policies' scalar conversion rules.

~~~karel
TYPE input_row=ARRAY[2]OF INTEGER input_grid=ARRAY[2]OF input_row
     output_row=ARRAY[2]OF REAL output_grid=ARRAY[2]OF output_row
VAR source:input_grid result:output_grid
ROUTINE changed(values:output_grid):output_grid
BEGIN
  values[1,1]=99
  RETURN values
END changed
BEGIN
  -- Initialize source leaves, or leave permitted numeric leaves missing.
  result=changed(source)
END
~~~

The call captures a private output_grid value before entering changed. Assigning
values[1,1] cannot write source. The returned result retains output_grid and
output_row identities. Successful whole assignments update the receiver's
existing ARRAY/record children under the ordinary stable-reference contract.

## Shapes and named components

Shapes now match by every logical dimension through one to three axes.
Anonymous outer formal/result wildcards inherit concrete dimensions; named
components remain concrete. The existing 32767-leaf bound remains.

[Source schema conversion](array-schema-conversions.md) also supports same-terminal
ARRAY names, bounded STRING capacities and rebuilding a flat ARRAY[2,2] as two
named rows of length two. It preserves logical coordinates and receiver schemas;
equal element counts alone do not permit reshape or dimension changes.
Compatible whole STRUCTURE and record-terminal changes follow
[source record conversions](record-schema-conversions.md), with identical field-name sets.

A numeric ARRAY field within a STRUCTURE can also convert separately. Neither
operation grants writes to POSITION orientation fields.
Complete chained selectors and selected named subarrays use their existing
capture rules.

## Capture, publication and lifetime

Source expressions run once. Conversion completes before assignment target
selectors, later arguments or the routine body, as applicable. RETURN conversion
finishes before frame and active-counter cleanup.

Converted bare actuals own independent writable cells. Nested exact forwarding,
retained handlers and connected formal timers refer to that private data.
Pause/resume, failure, stop and return never copy it back. Ordinary exact-type
bare arguments still borrow their caller storage; grouping keeps its ordinary
private-value behavior.

Numeric conversion validates every known source leaf and the receiver's domain,
retaining permitted missing markers. Unknown BYTE contents cannot become numbers.
An invalid late source or narrowing overflow preserves the whole destination and
skips later argument or target-selector effects. Earlier explicit effects remain.

Positional changes require complete valid elements. Model-backed conversions
preflight all source geometry and target allocation before invoking an adapter.
Adapters visit terminal elements in row-major component order. Outputs remain
private until every element succeeds; completed host-adapter effects remain on
failure without rollback or retry. No implicit checkpoint or current-state update
is introduced, and sticky abort prevents later element calls.

## Exact interfaces and persistence

Linked declarations and definitions still agree exactly. Ordinary callers may
convert actual data privately into that declared interface. Raw external callback
results must first match their declared result schema. BYNAME and generic runtime
checked/value/result helpers retain their exact contracts; this feature does not
add automatic conversions to those APIs or to GET_VAR/SET_VAR. Generic source
assignments and owned result schemas follow [ARRAY schema conversion](array-schema-conversions.md).

Context JSON preserves concrete receiver types, component names, values and
missing markers. It omits temporary routine cells, handlers, timer claims and
suspended execution. Restoring data does not resume a conversion or a task.

## Reports, examples and evidence

named_array_conversions identifies numeric_array, positional_array or
kinematic_array sites, with original source/target specs and ordered
source_component_names/target_component_names. Rows retain location, one-time
capture and independent-value metadata from the underlying policy.
named_array_policy describes schemas, ownership and boundaries with
controller_validated=false.

See authored [numeric interfaces](../examples/named_numeric_arrays.kl),
[nested counter copies](../examples/component_array_counters.kl),
[Cartesian interfaces](../examples/named_positional_arrays.kl),
[model-backed arrays](../examples/named_model_arrays.kl),
[typed linked routines](../examples/named_array_project/main.kl),
[linked caller-group models](../examples/named_model_array_project/main.kl),
and the [regression suite](../tests/test_named_array_conversions.py).

These are offline Pythonic source conventions. Native ARRAY ABI/layout, native
controller behavior, inferred robot context, physical motion and certified
reachability remain outside this policy. Public strict mode remains future work.
