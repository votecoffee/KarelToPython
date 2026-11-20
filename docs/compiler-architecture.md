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
| Call analysis | `call_analysis.py` | Plans routine arguments and results, including conversion, storage, and collection rules. Validates bindings and protected counter use, resolves service signatures, and checks PATH node compatibility. |
| SELECT | `select_analysis.py`, `select_codegen.py` | `check_select()` returns a checked selector and typed CASE rows in source order. The shared generator emits the match and uses the control-flow engine to emit each branch. |
| Control flow | `control_flow.py`, `flow_codegen.py` | `validate_labels()` checks scope entry and `FlowGraph` builds dispatch nodes. `ControlFlowLowering.emit_body()` emits the validated body, its source checkpoints, and FOR scope cleanup. |
| Loop and USING generation | `loop_analysis.py`, `loop_codegen.py`, `using_codegen.py` | Checks FOR counter ownership and schema. Both control-flow engines share counter initialization, inclusive range generation, and USING entry capture. |
| Generation | `expression_codegen.py`, `python_codegen.py` | `ExpressionLowering` lowers expressions and access paths. `Emitter.emit()` drives validation and emits Python. |
| Routine generation | `routine_codegen.py` | Captures arguments in source order and emits calls and checked RETURN values. |
| Assignment | `assignment_analysis.py`, `assignment_codegen.py`, `schema_conversion.py` | Checks declared or concrete receiver schemas and emits scalar, ARRAY prefix, and collection writes. Assignments and routines share conversion selection with distinct ARRAY policies. |
| Robot system access | `robot_system_analysis.py`, `robot_system_codegen.py` | Checks writable pose paths and source schemas. Emits system reads and captures write values before frame/tool selectors. |
| Statement I/O | `statement_io_analysis.py`, `statement_io_codegen.py` | Checks READ and WRITE source formats. Stages targets, rendered values, and explicit or default FILE bindings before runtime publication. |
| Motion | `motion_analysis.py`, `motion_codegen.py` | Checks motion operand types and PATH selectors. Captures settings, operands, and local callbacks for the offline runtime. |
| Task control | `task_codegen.py` | Lowers local and addressed task transitions, ABORT, and event/semaphore signals with the existing scheduler checkpoints. |
| Conditions and timers | `handler_analysis.py`, `handler_codegen.py` | Validates handler actions and timer storage, checks asynchronous FOR counter writes, and emits EVAL and USING captures for condition and motion callbacks. |
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
guards, and source locations. `RoutineResultPlan` carries the declared
result, operand schema, and conversion. RETURN analysis checks ARRAY source
shape and identity before generation emits an independent result.
`AssignmentPlan` records the source and destination schemas and the conversion
to emit. Anonymous ARRAY formals and prefixes can check against the concrete
receiver at runtime. Pythonic assignment lowering captures the source value
before evaluating destination selectors, including when an ARRAY result is
assigned through a routine formal. System pose writes use the same ordering
with separately checked frame/tool selectors. READ and WRITE retain separate
capture and publication steps for scalar and aggregate data.
FOR lowering initializes the captured counter before evaluating the final
bound. Structured loops clear it on exit, and labelled bodies track it in the
dispatcher scope stack. USING entry generation consumes the capture kinds
recorded by declaration analysis and uses the shared PATH node type query.
Keep label validation independent of Python emission. The report modules are
applied in order because later policies extend earlier entries.

For behavior-preserving moves, compare generated Python, diagnostics, source
maps, and report content at a fixed version. Run the tests for the affected
passes and the authored examples that exercise their interfaces. Runtime and
extended service decomposition can follow their existing ownership boundaries
in separate changes.
