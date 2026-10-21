# Pythonic ARRAY values and results

Pythonic mode supports writable private ARRAY arguments and composable ARRAY
results. Bare arrays still pass caller storage by reference; grouping the whole
actual argument selects a checked deep copy.

```karel
PROGRAM array_values
VAR original,edited: ARRAY[2] OF INTEGER
    first,count: INTEGER
ROUTINE edit(values: ARRAY OF INTEGER): ARRAY OF INTEGER
BEGIN
  values[1]=99
  RETURN values
END edit
BEGIN
  original[1]=1
  original[2]=2
  edited=edit((original))
  first=edit((original))[1]
  count=ARRAY_LEN(edit((original)))
END array_values
```

The final arrays are `ORIGINAL=[1,2]` and `EDITED=[99,2]`, with `FIRST=99` and
`COUNT=2`. Each call owns a separate copy. See the
[complete authored example](../examples/pythonic_arrays.kl),
[expected values](../examples/pythonic_arrays.expected.json) and
[expected output](../examples/pythonic_arrays.write.expected.json).

## Argument ownership

| Actual argument | Callee storage |
| --- | --- |
| `use(values)` | Live reference to the caller's array. |
| `use((values))` | Independent writable copy of the complete array. |
| `use((record.values))` | Independent copy of that array field. |
| `use((plane[1]))` | Independent copy of the selected named subarray. |
| `use(make())` or `use(make)` | Independent writable copy of the returned array. |

Value copies retain concrete dimensions, nominal array and record identities,
STRING capacities, narrow integer element types and joint widths. Flat and named
multidimensional arrays are supported up to logical rank three. Copies require
every scalar leaf to be known, initialized and valid; they do not resize arrays,
coerce element types or truncate corrupt STRING contents. The existing prototype
limit of 32767 scalar leaves applies.

A copy is made once at its argument position in left-to-right evaluation. A
later actual can change caller storage without changing an earlier private
copy. Bare references remain live. An uninitialized array is still a legal bare
output argument; its grouped value copy fails before entering the callee.

Forwarding a private parameter bare shares the private storage. Grouping it again
makes another copy. Changes never copy back to the original, including after
errors or ABORT. Whole-array assignment inside the callee retains captured
element aliases within that private array.

## Result composition and access

ARRAY results support grouping, compatible user-routine arguments, direct RETURN
forwarding, and `ARRAY_LEN` returning the first dimension. For example,
`RETURN transform(make())` can forward a fully checked result without staging it
in a local array. Each function RETURN still captures an independent result
before removing the routine frame.

Use `make()[2]` or `(make)[2]` to read a returned element. Subscripts and fields
also follow grouped aggregate expressions and record function results, such as
`make_records()[1].id` and `make_record().id`. The aggregate is evaluated once
before its subscripts. Nested array selection uses comma-separated subscripts,
such as `make_rows()[1,2]`; chained `make_rows()[1][2]` remains unsupported.

A bare function name used directly as a receiver root remains a storage name:
`make[1]` does not call a function. Use an explicit call or a group. Grouping only
the receiver in `use((values)[1])` keeps a reference to that element; grouping the
whole actual in `use(((values)[1]))` selects a scalar value copy.

References into returned temporary aggregates retain only that detached storage.
A callee may change its temporary element, but it cannot change the source from
which the function created its result. Existing POSITION read-only descendants,
CONFIG field passing rules and conversion argument restrictions remain.

## Remaining boundaries and reports

ARRAY function declarations support prior named types and anonymous fixed,
wildcard or mixed dimensions up to logical rank three. Named results require
exact nominal types; anonymous declarations require anonymous outer storage.
Named inner components retain exact identity and shape. Passing a named array
through a generic parameter preserves its identity; it does not turn it into
anonymous outer storage. See [ARRAY result shapes](array-result-shapes.md).

Arrays are not scalar arithmetic operands, Booleans, SELECT selectors or WRITE
items. `ARRAY_LEN` returns the first dimension of matrices and nested arrays. Motion,
controller storage and native call ABI behavior are outside this offline policy.

The report's `array_value_arguments` records each private copy site;
`array_function_uses` records ARRAY-valued calls in expressions. Existing
`array_returns` and `array_result_assignments` retain their checked-copy metadata.
`array_value_policy` and `aggregate_access_policy` describe the chosen behavior,
and ARRAY formal `passing_modes` includes reference and value.
`array_result_declarations` records result shapes and nominal identities;
`array_length_policy` records the Pythonic first-dimension convention.

The [semantic contract](semantics/pythonic_array_semantics.json) records the
boundaries and regression tests. Older assignment-only and value-rejection tests
are retained internally for the future strict milestone. Public strict mode
remains unavailable while Pythonic coverage takes priority.
