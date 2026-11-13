# Roadmap

These milestones describe released foundations and remaining work, without dated commitments.
Functional Pythonic conversion remains the implementation priority. Current
behavior and restrictions are documented in the [support guide](language-support.md)
and [desktop guide](desktop.md).

## Python runner and parameter editor

**Status: in progress.** The standalone [run-document service and CLI](run-documents.md)
now run pinned Pythonic generated modules with explicitly supplied context,
separate inputs/results and partial failure capture. [Bounded input discovery](input-discovery.md)
now follows generated source contracts without target execution. Complete
discovery, automatic value population, the parameter editor, linked-project runs
and GUI execution remain future work.
Expose the shared execution behavior through a workbench tab or popup after
those input and worker interfaces are ready.

### Discover inputs from Python

The first CLI/API discovery slice now reports supported source-flow candidates,
typed selectors, known routine aliases and explicit unresolved dependencies.
It does not populate run-document values or claim to analyze every source form.
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
