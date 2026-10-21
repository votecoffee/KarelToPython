# Pythonic ARRAY result declarations

Pythonic functions can return named ARRAY types or anonymous arrays with fixed,
wildcard or mixed dimensions. Each RETURN validates the concrete data and creates
an independent copy before removing the routine frame.

```karel
PROGRAM shape_demo
TYPE matrix_t=ARRAY[2,2] OF INTEGER
VAR matrix: matrix_t
    rows,last: INTEGER
ROUTINE build: matrix_t
VAR data: matrix_t
BEGIN
  data[1,1]=1 data[1,2]=2
  data[2,1]=3 data[2,2]=4
  RETURN data
END build
BEGIN
  matrix=build()
  rows=ARRAY_LEN(matrix)
  last=build()[2,2]
END shape_demo
```

The result is `MATRIX=[[1,2],[3,4]]`, `ROWS=2` and `LAST=4`. The
[complete example](../examples/pythonic_array_shapes.kl) also demonstrates fixed
and mixed result shapes, with [expected values](../examples/pythonic_array_shapes.expected.json)
and [expected output](../examples/pythonic_array_shapes.write.expected.json).

## Declaration forms

| Result declaration | Contract |
| --- | --- |
| `ARRAY OF INTEGER` | One anonymous outer dimension; length comes from returned storage. |
| `ARRAY[*] OF INTEGER` | Explicit spelling of that one-dimensional wildcard. |
| `ARRAY[2,3] OF INTEGER` | Anonymous matrix with exactly two rows and three columns. |
| `ARRAY[*,3] OF INTEGER` | Anonymous matrix with a returned row count and exactly three columns. |
| `ARRAY[*,*,*] OF INTEGER` | Anonymous cube with three returned dimensions. |
| `row_t` | Exact previously declared named ARRAY type, including its concrete shape and identity. |

Fixed dimensions are INTEGER constant expressions in 1..32767, resolved from the
global interface scope. Routine-local constants and runtime expressions cannot
set them. Wildcards inherit actual dimensions at RETURN; they allocate no local
storage and need no `array_shapes` translation option. Wildcard global variables
still require that explicit context, and wildcard local variables remain blocked.

Results support up to three logical dimensions across the outer declaration and
any separately named inner ARRAY components. Supported terminal elements remain
INTEGER, BOOLEAN, REAL, BYTE, SHORT, explicitly bounded STRING, named records,
built-in data records and exact-width JOINTPOS. The prototype limit is 32767
scalar leaves, including nested record fields and joint axes. Declarations whose
minimum possible size already exceeds that limit fail during translation.

## Identity and validation

Named result declarations require the exact named type. Another type with the
same shape is not interchangeable. Anonymous result declarations require
anonymous outer storage, matching outer rank and exact element/component types.
Flat matrices and matrices built from named rows remain distinct representations.
RETURN never flattens, reshapes, resizes or erases nominal identity.

A generic parameter can supply a result when its concrete runtime storage matches
the declared interface. Known mismatches fail during translation; unknown sizes,
capacities or identities are checked at RETURN before destination assignment.
For example, a named result may accept a generic parameter bound to that exact
named type, while anonymous storage passed through the same parameter fails.

Every scalar leaf must be known, initialized and valid. Copies retain STRING
capacities, narrow numeric element types, record identities, joint widths and
POSITION protection. An error or ABORT keeps earlier effects and unwinds frames;
an unsuccessful result does not replace its caller's destination.

## ARRAY_LEN

Pythonic `ARRAY_LEN(array)` returns the first concrete dimension, like Python
`len`. A flat `ARRAY[2,3]` returns 2, and an `ARRAY[3] OF row_t` returns 3. It does
not return a total element count or an inner dimension. The array expression runs
once. Reading this dimension does not require initialized scalar leaves, although
a function must still produce a fully validated result before ARRAY_LEN consumes it.

This extends the earlier rank-one-only policy. Existing one-dimensional values
keep the same answer. The internal conservative implementation retains the older
multidimensional rejection for the future strict milestone.

## Reports and boundaries

`array_result_declarations` records each routine's complete result type, declared
dimension mask, nominal identity and logical rank. `array_returns` includes the
same interface information at each RETURN site. `array_routine_policy` and
`array_length_policy` describe the chosen rules.

Composition, argument ownership and aggregate access follow the
[ARRAY values guide](pythonic-arrays.md). Unspecified STRING element capacities,
anonymous nested ARRAY component syntax, unsupported ranks and implicit element
coercion remain blocked. Public strict mode is still a future milestone.

These are chosen Pythonic declaration and length policies. Passing authored
offline tests does not establish native compiler, call ABI or controller behavior.
See the [semantic contract](semantics/pythonic_array_shape_semantics.json).
