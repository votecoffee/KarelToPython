# Input discovery

The CLI identifies initial values read before a definite source write in newly
generated Pythonic modules. Discovery reads a checked literal analysis contract;
it never imports or executes the selected Python. It produces candidates and
explicit gaps, without inventing values or editing a run document.

## CLI workflow

Create an ignored `.local/` directory, then run from the repository root:

```console
python -m karel2py examples/discovery_inputs.kl -o .local/discovery.py
python -m karel2py.runner discover .local/discovery.py --output .local/inputs.report.json
python -m karel2py.runner create .local/discovery.py .local/session.run.json --context examples/discovery_inputs.services.initial.json
python -m karel2py.runner run .local/session.run.json
```

The authored example reads `SELECTOR` and conditionally reads `SOURCE.B`.
It writes `SOURCE.A` before reading it. Its supplied context selects the branch
that returns 41. Review the report, then supply your own values in the context
format described in [saved runs](run-documents.md). Execution uses the explicit
context, independently of the discovery report.

Without `--output`, discovery prints the full JSON report. With `--output`, it
creates a new report and prints counts. Existing files and the selected Python
are protected from replacement. Exit code 0 includes partial reports; inspect
`complete` and `unresolved`. Invalid, stale or unmarked targets and publication
errors return 2. Reports belong in ignored `.local/` or outside public source.
The repository check also rejects full report instances under other JSON names.

## Report and values

The `karel2py.inputs.v1` report contains target byte identity, `inputs`,
`context_requirements`, `unresolved` and `complete`. Each input identifies its
logical kind, owner, selected path, type when known, certainty and source
locations. Include locations retain their physical file/line; `python_lines`
points into the generated module.

- `required`: a modeled unconditional read has no proven prior source write.
- `conditional`: the read depends on a branch, a potentially empty loop, a
  possible prior write or an uncertain effect.

These labels describe source accesses. They do not assert that every missing
runtime marker fails immediately: aggregate copies can preserve missing leaves.
An overwritten destination whose complete value remains unproven is reported
as an unresolved derived value, rather than an initial value to seed.

Variable candidates include `root_path`, `root_type` and `selectors`. A selected
path such as `SOURCE.B` explains the needed part of the value. The existing
context adapter restores whole declared globals: supply a `SOURCE` row with its
root schema and shaped value, retaining uninitialized markers where appropriate.
Do not copy selected field/element rows directly into `context.variables`.
Automatic root-value construction and a parameter editor remain planned.

Port and register candidates retain known indexes and position groups. Numeric
register reads list INTEGER/REAL alternatives without guessing the stored kind.
Unspecified position groups retain a caller-default marker. Position getter
schemas describe the logical read shape, rather than authenticated stored data.
`context_requirements` separately identifies services/addresses used even when
the source writes before reading. Bank sizes, routes, initial values, robot
models and successful runtime service statuses are never inferred from that list.

## Supported analysis

The analyzer follows source evaluation order for assignments, scalar/aggregate
reads, fields and bounded array/joint indexes, WRITE items, IF, WHILE, REPEAT,
FOR, SELECT and routine returns. It intersects definite writes across branches,
allows zero loop iterations where needed and tracks partial aggregate writes.
Small constant FOR ranges are expanded; uncertain loops widen address facts.
Internal calls preserve reference aliases and private value arguments, while
uncalled routines do not contribute inputs. UNINIT and ARRAY_LEN are metadata
probes. Literal/propagated addresses support direct ports, numeric/string/position
registers and own-program GET_VAR/SET_VAR data paths.

Dynamic addresses, unsupported schemas/resources/services, host or linked
routine effects, handlers, nonstructured jumps, recursion, fresh uninitialized
routine locals and analysis limits produce explicit `unresolved` entries.
Unsupported effects invalidate strong write facts so later writes cannot hide
potential initial reads. Reports can remain useful when partial; review the
listed gaps before deciding which context values to supply.

`complete: true` means the bounded supported source-access analysis found no
unresolved forms. It does not prove successful execution, termination, arbitrary
Python coverage, complete host callback dependencies or native controller
equivalence. READ requires an explicit input provider and remains a reported gap.

Limits are 16 MiB of Python, 100000 analysis steps, 32767 storage facts, 2048
catalog entries, 32 routine frames and 32 iterations for constant FOR expansion.
Contract construction has a separate 50000-node/100-depth budget; an oversized
contract is marked unavailable without rejecting an otherwise valid translation.
Limit exhaustion returns an explicit partial report.

## Contract identity and Python API

The compiler attaches inert literal source-flow metadata to Pythonic output.
Discovery checks its payload SHA-256 and a fingerprint of the entire Python AST
that excludes only that payload. Executable syntax or metadata edits require
retranslation. Comments/formatting preserve the semantic fingerprint, while the
report's raw SHA-256 and saved-run byte pin still reflect those edits. Older
generated modules must be retranslated. Strict-mode discovery is a future task.

The fingerprints detect stale metadata; they provide no authenticity or security
boundary. Deliberately regenerated contracts are not authenticated. Running a
module still executes trusted Python with ordinary process permissions.

`karel2py.input_discovery.discover_inputs(source, filename=...)` accepts text or
bytes. `discover_file(path)` performs a bounded file read. Both return a report;
invalid inputs raise `InputDiscoveryError`. Neither API imports the target.
The [semantic ledger](semantics/input_discovery_semantics.json) records this
contract. Complete discovery, automatic value editing, linked runs and the GUI
parameter tab remain [future work](roadmap.md).
