# Compiler architecture

`karel2py.translate` delegates to `compiler.py`, which expands includes,
coordinates the compiler passes, and attaches source origins and the checked
input-discovery contract to the result.

| Stage | Modules | Interface |
| --- | --- | --- |
| Syntax | `lexer.py`, `parser.py`, `syntax.py` | `Parser.parse()` returns a source AST. The linked-project loader uses the same parser for declaration discovery. |
| Declaration analysis | `declarations.py`, `compiler_language.py` | `DeclarationPasses` resolves declarations, constants, and types. It normalizes source references and records routine effects in the emitter's current scope. |
| Type queries | `type_checking.py` | `TypeQueries` inspects schemas, resolves scoped references and FILE prefixes, and checks storage for BYNAME and service operands. Declaration analysis and lowering share these queries. |
| Operator rules | `operator_types.py` | Unary and binary rules check operand schemas and return a result schema. Python generation applies evaluation order, source diagnostics, and reporting. |
| Call analysis | `call_analysis.py` | Plans passing mode, schema conversions, BYNAME operands and collection capture. Validates bindings and protected counter use, resolves service signatures, and checks PATH node compatibility. |
| SELECT checking | `select_analysis.py` | `check_select()` returns a checked selector and typed CASE rows in source order. The emitter assembles the dispatch call and report from those rows. |
| Control flow | `control_flow.py` | `validate_labels()` checks scope entry with the declared names and source mode. `FlowGraph` lowers a validated body to dispatch nodes. |
| Generation | `expression_codegen.py`, `python_codegen.py` | `ExpressionLowering` checks expression types and lowers access and routine calls. `Emitter.emit()` drives validation and emits Python. |
| Service generation | `service_codegen.py` | Lowers storage references, bounded ARRAY operands, and captured values in source order. Checks each typed operand against its service signature. |
| Reports | `call_reporting.py`, `report_base.py`, `report_services.py`, `report_language.py`, `report_interfaces.py`, `reporting.py` | Call reporting records argument binding and conversions as the call is lowered. Report builders collect this evidence and describe the policies applied to the translation. |

Relative geometry checks still use scoped frame rules. For routine arguments,
`RoutineArgumentPlan` carries the bound schema, passing mode, conversion, and
deferred ARRAY and STRING forwarding checks. The emitter supplies the operand
schema and whether the selected reference touches an active FOR counter.
BYNAME validation preserves source order across the program, path, and entry
operands. FILE prefix emission uses the selected schema from type queries.
Collection capture plans indicate whether to convert a PATH layout or copy
the existing logical value. Lowering emits the runtime calls in source order.
The reporting module records the chosen bindings, conversions, forwarding
guards, and source locations.
Keep label validation independent of Python emission. The report modules are
applied in order because later policies extend earlier entries.

For behavior-preserving moves, compare generated Python, diagnostics, source
maps, and report content at a fixed version. Run the tests for the affected
passes and the authored examples that exercise their interfaces. Runtime and
extended service decomposition can follow their existing ownership boundaries
in separate changes.
