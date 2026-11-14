# Input discovery

The CLI identifies initial values read before a definite source write in newly
generated Pythonic modules. Discovery reads a checked literal analysis contract;
it never imports or executes the selected Python. It produces candidates and
explicit gaps without inventing values. `runner create --discover` can also
prepare an editable input template in a new run document.

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
The optional input-template preparation below constructs those whole-root
shapes with missing markers. A graphical parameter editor remains planned.

Port and register candidates retain known indexes and position groups. Numeric
register reads list INTEGER/REAL alternatives without guessing the stored kind.
Unspecified position groups retain a caller-default marker. Position getter
schemas describe the logical read shape, rather than authenticated stored data.
`context_requirements` separately identifies services/addresses used even when
the source writes before reading. Bank sizes, routes, initial values, robot
models and successful runtime service statuses are never inferred from that list.

## Prepare an editable run document

```console
python -m karel2py.runner create .local/discovery.py .local/editable.run.json --discover
```

This saves the usual `inputs.context` and `results`, plus `inputs.template` with
the discovery report, input bindings and requirements. Variable bindings point
to whole-root values through `context_pointer` (a JSON Pointer relative to
`inputs.context`) and retain logical `selectors` for the required fields or
one-based KAREL indexes. Fill those values in `inputs.context`, then run the
document normally. For the authored example set SELECTOR to true and SOURCE.B
to 41; SOURCE.A may retain its missing marker because the program writes it.

Preparation builds concrete scalar, ARRAY, STRUCTURE, built-in record and
JOINTPOS shapes. Missing scalars use `{"uninitialized": true}`; BYTE uses
`{"unknown_byte": true}`. Fields and cells remain independent. Whole roots are
deduplicated across selected inputs. No numeric zeros, Boolean choices, strings,
poses, register capacities or port configuration are invented.

Combine `--discover --context existing-context.json` to retain supplied values,
partial data, comments and unrelated services. Compatible root bindings keep
their original spelling and representation; conflicting root types reject
preparation before publication. Bank/port bindings point to existing or proposed
value locations, while absent services/counts, out-of-range addresses and
caller-default position groups require explicit review. Bank values remain
omitted until supplied. Physical-input adapters can supply port values without
an explicit logical `values` entry; such a pointer identifies the logical value
to edit if overriding it, rather than the physical sample row.

Binding status is `supplied`, `missing` or `unmapped` at preparation time.
Requirements and statuses are snapshots and do not refresh after JSON edits;
they never authorize execution or assert that a program is ready. Conditional
inputs may remain missing when their branch is not taken. Unsupported discovery
effects remain in `inputs.template.discovery.unresolved`. Actual runtime reads
and services keep their existing checks and failure behavior.

Preparation adds at most 32767 scalar leaves across new roots. Unsupported or
oversized roots stay unmapped with explicit requirements. Source bytes are
checked against the run document's pin during preparation; stale annotation
envelopes are rejected before running. Inputs and annotations survive failures
and replay unchanged. Preparation still never imports or executes the target.

## Refresh edited inputs

```console
python -m karel2py.runner refresh .local/editable.run.json .local/refreshed.run.json
python -m karel2py.runner refresh .local/editable.run.json .local/refreshed-v2.run.json --target .local/converted-v2.py
```

Refresh always creates a new run document. It reads `inputs.context`, preserves
the execution limits, pins the selected Python and starts with `results: null`.
It never uses final results as new inputs or imports/executes the target. The
original document, edited values and results remain intact. By default it reads
the saved target path, even if that Python has been regenerated. `--target`
selects a different module and can be used when the old Python is unavailable.

The refreshed `inputs.template` recomputes binding status and requirements from
the edited context. Its `refresh` section lists added, removed, changed and
retained source inputs. Source locations and binding status alone do not count
as an input-schema change. A changed type, root schema or certainty does.
Old context-only documents are supported, with `baseline_known: false` because
their prior source input catalog is unavailable.

`comparison_complete` requires complete catalogs on both sides. An entry missing
from incomplete current discovery is an unresolved comparison, rather than a
proven removal. An entry absent from an unknown/incomplete prior catalog is
similarly unproven as an addition. These appear in `refresh.changes.unresolved`,
separately from current discovery gaps. Retained context is preserved in either case.

Exact-schema roots retain their original values, spelling and representation.
Changed roots receive a checked new shape, then copy compatible data:

| Changed storage | Values retained |
| --- | --- |
| Same nominal STRUCTURE | Matching field names, recursively checked by type. |
| ARRAY | Overlapping logical coordinates when physical rank and ARRAY identity match; nested named components follow the same rule. |
| JOINTPOS | Common axis indexes; additional axes remain missing. |
| STRING capacity | An existing string that fits the new capacity; no truncation during migration. |
| Other scalar/kind/name changes | Missing markers, with the old value retained in the original document. |

New fields/cells remain missing. Removed inputs and unrelated context bindings,
services, bank capacities, values and comments are retained. A changed root's new
row carries its new schema; prior creation metadata remains in the original
document. No variable-owner rename, numeric conversion, bank allocation or robot
model is inferred. Unsupported schemas and storage limits remain explicit.

Root migration rows report preserved/missing leaf counts, the old source value
pointer and the new context pointer. Source pointers address the original whole
run document; context pointers are relative to the refreshed `inputs.context`.
Immediate previous-target identity and source-document path/hash provide
provenance without nesting older refresh histories. These checks do not
authenticate code or prove runtime readiness.

Existing outputs and source/target aliases are refused. Refresh detects source
document edits and target changes during preparation before publication. A prior
`running` marker must be resolved explicitly before refresh, as for replay.
Failed preparation or publication preserves the original; no execution is retried.
Review missing values and unresolved discovery effects before running the new
document. Conditional inputs can still remain missing on untaken paths.

## Supported analysis

The analyzer follows source evaluation order for assignments, scalar/aggregate
reads, fields and bounded array/joint indexes, WRITE items, IF, WHILE, REPEAT,
FOR, SELECT and routine returns. It intersects definite writes across branches,
allows zero loop iterations where needed and tracks partial aggregate writes.
Small constant FOR ranges are expanded; uncertain loops widen address facts.
Internal calls preserve reference aliases and private value arguments, while
uncalled routines do not contribute inputs. UNINIT and ARRAY_LEN are metadata
probes. ARRAY_LEN returns a static fact when the selected logical dimension is
known, including private wildcard ARRAY parameters and internal ARRAY results.
This can bound the existing small FOR expansion without reading missing cells.
Computed metadata receivers retain their modeled call effects exactly once.

Private ARRAY calls retain known source dimensions and inherited STRING element
capacities while using the declared receiver's component layout and converted
terminal types. Reference calls keep their original locations. Private writes
never initialize caller storage. Matching concrete result shapes survive return
merges; disagreeing shapes retain only their declared constraints. No wildcard
size is invented. Conflicting known argument/result constraints remain explicit
shape gaps rather than publishing callee write facts.

Partial aggregate copies remain conservative: a later read of an unproven
private leaf is a derived-value gap, not a seedable local input. Conversions to
SHORT from another terminal type may create its missing sentinel and therefore
do not establish complete copied leaves. Scalar storage/result conversions also
invalidate uncast constants when truncation can change branch truth. Direct
private STRING arguments use their existing 254-character temporary capacity.

The [private ARRAY](../examples/discovery_private_arrays.kl) and
[ARRAY result](../examples/discovery_array_shape_results.kl) examples have
independent execution and discovery expectations; their
[regressions](../tests/test_input_discovery_arrays.py) require discovery without
target execution. These facts use the existing contract and report schemas.

Literal/propagated addresses support direct ports, numeric/string/position
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
contract. `karel2py.input_template.prepare_inputs(source, context=...)` returns
independent `context` and `template` objects for CLI/host reuse; invalid contexts
raise `InputTemplateError`. The [template ledger](semantics/input_template_semantics.json)
records its contract. Complete discovery, automatic value editing, linked runs
and the GUI parameter tab remain [future work](roadmap.md).

`karel2py.input_refresh.refresh_inputs(source, inputs, filename=...)` returns fresh
context and template objects without changing the supplied inputs. Invalid
previous metadata/context raises `InputTemplateError`; invalid target contracts
retain discovery errors. The [refresh ledger](semantics/input_refresh_semantics.json)
records the compatible migration and preservation boundaries.
