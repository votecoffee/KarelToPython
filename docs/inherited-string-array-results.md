# Inherited STRING capacities in ARRAY results

Pythonic anonymous ARRAY function results may omit the capacity of their direct
STRING element type. The result inherits its concrete capacity from the returned
array storage. It does not use a default capacity of 254 or convert the array's
strings to the assignment destination's capacity.

```karel
ROUTINE words: ARRAY OF STRING
VAR
  data: ARRAY[2] OF STRING[6]
BEGIN
  data[1] = 'hello'
  RETURN data
END words

ROUTINE copy_words(data: ARRAY[*,*] OF STRING): ARRAY[2,*] OF STRING
BEGIN
  RETURN data
END copy_words
```

The first result owns a detached anonymous `ARRAY[2] OF STRING[6]`. Its second
element remains uninitialized. The matrix routine retains the actual second
dimension and STRING capacity of its argument while enforcing two rows. Fixed,
wildcard and mixed dimensions keep the existing one-through-three-dimensional
result rules. Omitted ARRAY dimensions still mean a one-dimensional wildcard.

## Concrete storage and copies

Only the declared result's direct anonymous STRING element capacity may be
inherited. Returned storage must be a checked concrete ARRAY with one actual
STRING capacity from 1 through 254, excluding Boolean and noninteger sizes.
The runtime validates its exact shape, flat storage length, all known ASCII
STRING leaves and missing markers before detaching an independent copy. A known
value exceeding the actual source capacity fails instead of being truncated.
Ragged host lists, embedded arrays, mixed representations and non-STRING leaves
are rejected. The 32,767 scalar-leaf and 64-level schema guards remain in force.

Known empty strings remain initialized. Existing uninitialized STRING markers
survive the copy, while reading one as a scalar still fails. BYTE unknown markers
are invalid STRING values. Results returned from globals, ordinary array fields,
generic formals, other ARRAY functions and recursive functions retain their
concrete capacity and independent storage.

[Source ARRAY schema conversion](array-schema-conversions.md) can now capture
named or nested storage into an owned anonymous result with the same logical
dimensions. It preserves the original source and does not add omitted STRING
capacities to named declarations. Generic runtime array_result remains exact;
generated source RETURN prepares the declared output schema first.

## Using a result

Calls, RETURN forwarding, whole-array assignment, array arguments and result
subscripts understand the declaration's unknown capacity. After evaluation,
source boundaries validate concrete source data before applying the receiver's
capacity under [ARRAY schema rules](array-schema-conversions.md). A STRING[6]
result may be copied into STRING[8], or right-truncated into STRING[4], without
changing the source or receiver schema. A failed conversion preserves the prior
destination and already completed effects.

Explicit `ARRAY OF STRING[6]` source RETURN declarations now prepare capacity6
using checked source text and scalar truncation/widening. The inherited result
itself still keeps its concrete source capacity; downstream conversion is a
separate source boundary. Generic runtime result/value helpers remain exact.
Result subscripts support ordinary STRING operations, including STR_LEN, ORD and
SUB_STR. Writable result arguments refer to private result storage and preserve
the original source.

Typed FROM linkage keeps exact declared interface matching. A caller and source
routine can both declare an inherited-capacity ARRAY result, whose returned
concrete storage is validated and copied normally. An inherited declaration and
an explicitly bounded declaration are distinct project interfaces; this feature
does not weaken external callback or native ABI contracts.

## Lifecycle and persistence

Pause retains an unfinished factory's ordinary local storage; the caller's
destination changes only after a successful checked return. Resume completes
that return. Stop, abort and budget failures unwind routine frames and preserve
an unassigned destination. Completed copies in global storage serialize their
actual concrete STRING capacity and partial values through existing context JSON.
The unbound declaration is an interface constraint, not a saved wildcard-sized
storage allocation.

The internal legacy compiler and runtime retain their explicit-capacity
requirement. Public strict mode remains a future milestone. This behavior is an
offline Pythonic convention and carries no native/controller storage or ABI
equivalence claim. See `tests/test_inherited_string_array_results.py` and the
existing bounded STRING, shaped ARRAY and project linkage regression suites.
