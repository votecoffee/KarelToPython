# Compiler architecture

`karel2py.translate` delegates to `compiler.py`, which expands includes,
coordinates the compiler passes, and attaches source origins and the checked
input-discovery contract to the result.

| Stage | Modules | Interface |
| --- | --- | --- |
| Syntax | `lexer.py`, `parser.py`, `syntax.py` | `Parser.parse()` returns a source AST. The linked-project loader uses the same parser for declaration discovery. |
| Declaration analysis | `declarations.py`, `compiler_language.py` | `DeclarationPasses` resolves declarations, constants, and types. It normalizes source references and records routine effects in the emitter's current scope. |
| Type queries | `type_checking.py` | `TypeQueries` inspects schemas, resolves reference paths and checks scalar, array, and geometry compatibility in the current scope. |
| Operator rules | `operator_types.py` | Unary and binary rules check operand schemas and return a result schema. Python generation applies evaluation order, source diagnostics, and reporting. |
| Call analysis | `call_analysis.py` | Classifies routine argument conversions, checks fixed ARRAY forwarding and resolves service arity and operand roles. Routine emission and reference-effect analysis share the conversion rules. |
| SELECT checking | `select_analysis.py` | `check_select()` returns a checked selector and typed CASE rows in source order. The emitter assembles the dispatch call and report from those rows. |
| Control flow | `control_flow.py` | `validate_labels()` checks scope entry with the declared names and source mode. `FlowGraph` lowers a validated body to dispatch nodes. |
| Generation | `expression_codegen.py`, `python_codegen.py` | `ExpressionLowering` checks expression types and lowers access and call forms. `Emitter.emit()` drives validation and emits Python. |
| Reports | `report_base.py`, `report_services.py`, `report_language.py`, `report_interfaces.py`, `reporting.py` | Report builders collect pass results and describe the policies applied to the translation. |

Relative geometry checks still use scoped frame rules. Call arguments also
depend on the current scope for writable references, active FOR counters, and
service storage checks. Lowering owns those operations, argument evaluation
order and report metadata. A follow-up can move one expression family at a
time into a typed result that carries its schema, evaluation order, and source
span.
Keep label validation independent of Python emission. The report modules are
applied in order because later policies extend earlier entries.

For behavior-preserving moves, compare generated Python, diagnostics, source
maps, and report content at a fixed version. Run the tests for the affected
passes and the authored examples that exercise their interfaces. Runtime and
extended service decomposition can follow their existing ownership boundaries
in separate changes.
