# Inline ARRAY source spellings

Pythonic mode accepts directly written `ARRAY OF ARRAY` layers and combines
their dimensions before resolving types or allocating storage. This is a source
spelling extension using existing checked ARRAY schemas and runtime operations.

```karel
VAR grid:ARRAY[2] OF ARRAY[3] OF INTEGER
ROUTINE edit(data:ARRAY OF ARRAY OF INTEGER)
BEGIN
  data[2][3]=9
END edit
```

`grid` has exactly the same schema as `ARRAY[2,3] OF INTEGER`. The parameter
has the same schema as `ARRAY[*,*] OF INTEGER`. Both comma and complete chained
indexes select ordinary cells. See the [runnable example](../examples/inline_arrays.kl).

## Declarations and interfaces

| Source | Normalized declaration |
| --- | --- |
| `ARRAY[2] OF ARRAY[3] OF INTEGER` | `ARRAY[2,3] OF INTEGER` |
| `ARRAY[2,1] OF ARRAY[3] OF STRING[4]` | `ARRAY[2,1,3] OF STRING[4]` |
| `ARRAY[*] OF ARRAY[3] OF INTEGER` global | `ARRAY[*,3] OF INTEGER`; explicit complete shape required. |
| `ARRAY OF ARRAY OF INTEGER` parameter | `ARRAY[*,*] OF INTEGER`; caller supplies both dimensions. |
| `ARRAY[2] OF ARRAY[*] OF INTEGER` parameter | `ARRAY[2,*] OF INTEGER`; first dimension must match and the second comes from the caller. |
| `ARRAY OF ARRAY[3] OF INTEGER` result | `ARRAY[*,3] OF INTEGER`; RETURN supplies the first dimension. |
| `ARRAY[2] OF ARRAY[*] OF STRING` result | `ARRAY[2,*] OF STRING`; returned storage supplies wildcard size and element capacity. |

Global and local variables, TYPE definitions, record fields and routine
interfaces share this normalization. Dimension expressions retain their existing
constant scopes and checked values. [Formal dimensions](array-formal-shapes.md)
may now be fixed, wildcard or mixed; omitted STRING formal capacities still
inherit, while [explicit bounds](bounded-string-formals.md) use existing checked storage.
Result dimensions may be omitted, fixed,
wildcard or mixed under the [existing result rules](array-result-shapes.md).

Normalization stops at a named component. If `row_t=ARRAY[3] OF INTEGER`,
`ARRAY[2] OF ARRAY[1] OF row_t` becomes `ARRAY[2,1] OF row_t`, retaining the
`row_t` identity and component storage. Named outer TYPEs retain their own
identity after normalization. A source-linked declaration can use a nested
spelling while its supplied implementation uses the equivalent comma spelling;
their resolved interfaces must still match exactly.

## Execution and saved data

The normalized declaration uses ordinary ARRAY operations: row-major READ/WRITE,
prefix selection, ARRAY_LEN, assignments, private copies and borrowed arguments.
Partial data retains missing scalar leaves. Bounds, scalar domains, POSITION
protection, FOR roots, timer claims and retained-alias checks still apply.

FILE, PATH and QUEUE_TYPE terminals follow their existing storage and ownership
rules. FILE bank rows borrow original descriptors and cannot become values.
Logical PATH/queue values and I/O use their separate supported collection policies.
No new backend, node/entry allocation or implicit robot context is introduced.

Wildcard global dimensions supplied through `array_shapes` or `--array-shape`
describe the complete normalized outer shape. Saved JSON ARRAY schemas supplied
through `array_context` or `--array-context` use that same normalized shape;
loading values still requires a separate execution context. Existing codecs and
archives see ordinary schemas. No new anonymous nested runtime schema is accepted,
and no live descriptors, aliases or suspended call stacks are restored.

## Bounds and reports

The complete logical rank, including named components, remains at most three.
Each fixed dimension is positive; the existing 32767-leaf/resource and 64-level
schema bounds remain. A fourth directly written ARRAY layer is rejected during
parsing, before arbitrarily deep source nesting can recurse. Ragged dimensions,
equal-count reshaping and wildcard TYPE/field/local storage remain rejected.
[Fixed CREATE_VAR type strings](dynamic-fixed-arrays.md) now use a separate
bounded literal grammar, with existing dimension slots for extra outer storage.

Reports include `inline_array_syntax_policy` and `inline_array_syntaxes`.
Each normalization records its rank, terminal source category, physical source
location and include stack. These rows describe translation, not execution or
native compiler acceptance. Policies for earlier versions retain their historical
scope; current source syntax follows this guide.

The [semantic ledger](semantics/inline_array_syntax_semantics.json) and
[authored regressions](../tests/test_inline_arrays.py) cover data, resources,
interfaces, includes and saved-state replay. Public strict mode, native KAREL
syntax/compiler acceptance, controller layouts and hardware remain separate.
