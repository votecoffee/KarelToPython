# Roadmap

Functional Pythonic conversion remains the implementation priority. The
compiler now separates parsing, schema validation, control-flow analysis, and
Python generation. Remaining Pythonic source forms and offline overloads take
priority. See the [coverage backlog](unsupported.md) for gaps by feature.
Strict compatibility follows functional coverage.
Current behavior and restrictions are documented in the [support guide](language-support.md)
and [desktop guide](desktop.md).

## Compiler decomposition

The first extraction separates parsing, AST data, declaration analysis, type
queries, control-flow validation and lowering, Python generation, and reports.
Unary and binary operator rules return schemas independently of emission.
SELECT checking returns typed CASE rows before dispatch generation. Call
analysis checks routine binding plans, BYNAME operands, collection capture,
and service operand schemas. Scoped type queries identify borrowable FILE
prefixes and check service storage. Routine and service generation have dedicated
modules. Routine argument and result plans share conversion selection while
keeping their distinct ARRAY and collection checks. Assignment analysis and
generation now cover ordinary writes, ARRAY prefixes, collection copies, and
routine result receivers. Robot system access and staged READ and WRITE have
dedicated analysis and generation modules. Motion and task-control lowering
now have their own modules. Condition handlers and connected timers share
dedicated compiler modules for capture, storage checks, and lowering. Both
control-flow engines share FOR counter checks, bound emission, and USING
entry capture. Dedicated control-flow and SELECT generators handle label
dispatch, CASE emission, and FOR scope unwinding. Routine effect propagation
and retained-alias analysis run after source normalization. ARRAY subscript,
bare routine call, and USING reference normalization have dedicated modules.
Constant evaluation and dependency ordering have their own compiler module.
Named TYPE resolution checks expanded schema size and depth and shares the
dependency walk with CONST. ARRAY storage, parameter, and result schemas
have a dedicated resolver. Routine interface and local scope validation run
after module declarations. Program initialization, execution entry points,
and standalone CLI bindings have dedicated generators. Procedure dispatch,
FILE operations, and timing statements are owned by their generators.
Built-in function and typed output procedure generation are also separate.
Storage references, subscript checks, and ARRAY prefix lowering have a
dedicated generator, as do unary, binary, and relative pose operators.
Function-call dispatch and shared schema conversions have dedicated modules.
`file_io.py` now owns FILE descriptors, portable field formats, PATH
record selection and finite READ execution. Continue extracting service
families from `runtime.py` and
`extended.py` behind their existing runtime interfaces with focused
regressions. See
[compiler architecture](compiler-architecture.md).

## Python runner and parameter editor

The [desktop runner](desktop.md#discover-inputs-and-run-python) and CLI share
standalone run documents. The desktop lists discovered input paths and source
locations, validates scalar and structured edits, and runs the selected Python
with cancellation and saved results. The field editor covers shaped data and
explicitly grouped position registers. Both entry points can carry compatible
inputs to a new document on refresh.

The desktop and CLI create pinned linked runs with an explicit entry and module
order. Both prepare owner-qualified input templates, and the desktop edits
discovered scalar and structured inputs and shows each saved program snapshot.
Input saves check the document revision and module pins and keep prior results.
Discovery follows synchronous linked calls, known child task bodies, and
global and motion-local condition callbacks. Child and scan-time reads are
conditional. Linked discovery follows known paused entries and explicit
top-level child pauses through continuation. It tracks numbered handler
activation within each invocation and follows emitted motion capture order.
Refreshing a module set carries compatible owner-qualified values into a new
document and reports changed, omitted and unresolved inputs.
[Linked input discovery](input-discovery.md#linked-project-discovery)

### Remaining linked-run work

1. **Expand linked discovery.** Model suspension in routine frames and nested
   control flow, synchronization between tasks, and handler rearming where
   order and targets can be determined. Track effects between motion
   callbacks and keep dynamic selections and external effects visible. Extend
   TP discovery to unsynchronized task interleavings, external pause and abort
   requests, dynamic overwrites, and dynamic header selectors. Known child
   pause handoffs carry TP handle ownership, reject masks, shared bank writes,
   and header edits across continuations.
2. **Export linked sources from the desktop.** Reuse linked-project validation
   and cooperative Python export so the desktop workflow can begin with KAREL
   source files. Keep the existing output and source-file protections.

### Discover inputs from Python

The first CLI/API discovery slice now reports supported source-flow candidates,
typed selectors, known routine aliases and explicit unresolved dependencies.
`runner create --discover` now prepares whole-root shapes and annotations in the
run document; users still supply initial values and explicit service configuration.
It does not claim to analyze every source form.
The requirements below describe the complete milestone.

Analyze the generated Python without importing or running it. An input is a
register, variable or other state value that a reachable execution path reads
before that value has been written or initialized on that path. Use Python AST
analysis plus translation metadata where available to recover KAREL names,
types and source locations; ignore compiler temporaries and runtime plumbing.

Discovery must follow control flow and known routine calls. A write in only one
branch, a loop that may run zero times, or a write after the first read must not
hide an input. Distinguish required inputs from conditional inputs and explain
unresolved requirements instead of inventing initial values.

| State | Planned discovery behavior |
| --- | --- |
| Variables, parameters and globals | Include values read before initialization; exclude constants and values definitely initialized first. |
| Arrays, records and positions | Track elements and fields so a partial write does not initialize unrelated content. Preserve type, shape and group information. |
| Numeric, string and position registers | Identify the bank, index and group read before a matching write. |
| Digital, group and analog ports; system/external variables | Identify port addresses and variable paths, with the offline context needed to supply them. |
| Linked routines and reference arguments | Propagate known read/write effects, including aliases. Flag unknown callback effects for explicit configuration. |
| Dynamic addresses, file reads and other external inputs | Use known address ranges and declared input contracts where possible; request explicit mappings or context for unresolved dependencies. |

The editor should show each input's name/address, type, discovery reason and
source location, with validated editable values. Preserve saved values when
rediscovering compatible inputs and flag removed, changed or unresolved inputs.

### Save inputs and results together

The CLI foundation now uses one versioned JSON run document containing separate `inputs` and `results`
sections. Record the selected Python target and source hash so stale saved
parameters can be identified when the code changes. Keep this format distinct
from the existing [ExecutionContext JSON](offline-services.md#register-port-and-variable-context)
through the explicit `inputs.context` and `results.context` adapter.

- Save edited inputs before starting a run and allow the document to be reopened
  for repeat runs. Do not overwrite input values with final output values.
- Write final variables, registers, I/O and other observable state into `results`,
  together with captured text output and completion, failure or cancellation
  status. Report unavailable or uninitialized results explicitly.
- Preserve the original inputs and any valid partial results on failure. Replace
  the JSON file only after a complete temporary write succeeds.
- Keep run documents and generated output local, outside tracked public source;
  the ignored `.local/` directory is available for checkout-local runs.

### Execution and acceptance

Run only after an explicit user action, in a worker that keeps the GUI responsive
and supports cancellation and execution limits. Use the existing offline runtime
and explicit context providers. Discovery must never execute the selected code.

The milestone is complete when:

- CLI and GUI discover and edit the same inputs and produce the same JSON result
  contract for authored examples.
- Tests cover read-before-write ordering, branches, zero-iteration loops, routine
  calls, aliases, partial aggregates and register/port reads and writes.
- Dynamic or unsupported dependencies remain visible with actionable diagnostics.
- A saved document can be edited and replayed, and success, failure and
  cancellation all retain the inputs and write results to that document.
- Changed source is detected, malformed inputs are rejected before execution,
  and a failed JSON save preserves the previous file.

## Strict mode

Strict mode remains a later milestone, after functional Pythonic coverage. Keep
the earlier exactness work and regression evidence available as a starting point.
The [numeric mode roadmap](numeric-modes.md#compatibility-and-the-strict-milestone)
describes its current status and compatibility boundaries.
