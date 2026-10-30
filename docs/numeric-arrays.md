# Numeric ARRAY source conversions

Pythonic source supports checked numeric changes for whole ARRAY values
at assignment, ordinary routine argument and RETURN boundaries. Arrays retain
matching rank and dimensions. This extends the existing scalar numeric rules;
generic runtime type compatibility remains exact. [Named/component conversions](named-array-conversions.md)
preserve receiver schemas across named types and matching nested components.

| Source element | Receiver element | Behavior |
| --- | --- | --- |
| INTEGER, BYTE, SHORT | Different INTEGER, BYTE, SHORT | Check the source domain and then the receiver domain |
| INTEGER, BYTE, SHORT | REAL | Promote checked values to finite Python floats |
| Same numeric type | Same numeric type | Existing checked copy or bare-reference contract |
| REAL | INTEGER, BYTE, SHORT | Rejected; use explicit ROUND/TRUNC per element |
| BOOLEAN, STRING, resource or record | Numeric | Rejected |

```karel
VAR original:ARRAY[2]OF INTEGER result:ARRAY[2]OF REAL
ROUTINE shifted(values:ARRAY OF SHORT):ARRAY OF REAL
BEGIN
  values[1]=-7
  RETURN values
END shifted
BEGIN
  original[1]=1
  original[2]=2
  result=shifted(original)
END
```

The result is [-7.0, 2.0]; original remains [1, 2]. Argument conversion creates
private writable SHORT storage. RETURN promotes that storage to an independent
concrete REAL array before the routine frame unwinds.

## Shapes, capture and ownership

Supported arrays have one through three logical dimensions and ordinary numeric
terminal elements, with matching logical dimensions across flat/nested layouts.
Formal/result wildcards inherit concrete dimensions. Known
rank or dimension mismatches fail during translation; concrete destination shape
checks still run when wildcard declarations defer that information. There is no
reshape, resize, flattening or inferred allocation. The 32767-leaf bound applies.

The source expression is evaluated once. All source data and receiver conversions
finish before any destination publication. Assignment captures this converted
value before target selector functions run. A conversion failure skips those
selectors and preserves every destination element. Completed earlier effects
remain visible.

At an argument position, conversion finishes before later arguments are
evaluated. Even a bare actual gets private writable storage when its terminal
type changes. Edits, forwarding, retained handlers, pause/resume, failures and
stop cannot copy it back. A nested exact bare argument can alias the private
copy. Exact-type bare actuals retain their existing caller references; exact
grouped actuals retain their independent-copy behavior.

RETURN conversion occurs before routine and active-counter cleanup. Its result
captures the current values; clearing a source counter later does not erase the
returned value. Explicit global writes and exact reference arguments still obey
ordinary counter checks. Proven converted arguments do not supply a writable
alias to the source, including when a handler retains the private formal.

## Missing values and numeric domains

Missing scalar leaves remain missing. They are never filled with zeros, even
when changing INTEGER/SHORT to REAL or BYTE. The existing ARRAY missing marker
can inhabit a BYTE destination; this does not enable BYTE UNINIT queries or
invent an initialized byte. Matching BYTE copies also retain unknown-byte state.
Unknown BYTE contents cannot be promoted or narrowed into another numeric type.

Every known source value is validated against its own declared domain before
conversion. Malformed BYTE 256 does not become valid REAL data. INTEGER MAXINT
storage exclusion, strict Boolean separation and checked BYTE/SHORT ranges remain.
SHORT 32767 normalizes to missing data during source copying, and narrowing a
valid INTEGER 32767 to SHORT also creates its existing missing sentinel. There is
no wrapping, saturation, Boolean coercion or implicit REAL rounding.

A late invalid source leaf or receiver overflow fails the complete conversion.
No partially converted destination, argument or RETURN result is published.
Source storage remains independent from normalization in the copied value.

## Identity, linkage and persistence

[Named outer ARRAY types and nested components](named-array-conversions.md) now
convert into independent receiver schemas when their numeric terminal type changes.
Logical dimensions must match. [Schema conversions](array-schema-conversions.md)
also copy same-terminal ARRAY names and rebuild compatible component layouts.
Transparent scalar aliases work as numeric terminal types.
An ARRAY field inside a named STRUCTURE can convert separately; this does not
coerce the whole STRUCTURE schema.

Linked routine declarations/definitions must agree exactly. A matching source
or callback interface can receive privately converted actuals. Raw callback
ARRAY results must match the declared type before an ordinary source boundary
can subsequently convert them. BYNAME, generic checked/value/result helpers and
ordinary formal compatibility retain their exact checks.

GET_VAR/SET_VAR keep their separate [same-rank numeric prefix contract](numeric-variable-transfers.md).
This feature changes complete source ARRAY boundaries, with no new prefix copy or
status convention. Typed context JSON preserves receiver schemas, values and
missing markers. It omits private routine cells, handlers and suspended stacks.
Loading saved data does not resume a conversion.

## Reports and examples

numeric_array_conversions records assignment/argument/RETURN sites, original and
receiver specs, source location and one-time independent capture. Argument rows
also identify the routine and formal; RETURN rows record capture before cleanup.
numeric_array_policy describes numeric domains, ownership and remaining limits,
with controller_validated=false. Converted ARRAY argument rows retain the
original source spec and conversion_kind=numeric_array.

See the authored [interfaces](../examples/numeric_array_interfaces.kl),
[partial data](../examples/numeric_array_partial.kl),
[counter copies](../examples/numeric_array_counter_copy.kl),
[retained handlers](../examples/numeric_array_handler_copy.kl),
[linked interfaces](../examples/numeric_array_project/main.kl),
[linked source return](../examples/numeric_array_assignment_project/main.kl), and
[regression tests](../tests/test_numeric_arrays.py).

These are offline Pythonic conventions without native ARRAY ABI or controller
acceptance claims. Public strict mode remains a future milestone; legacy numeric
ARRAY guards and generic runtime compatibility remain preserved.
