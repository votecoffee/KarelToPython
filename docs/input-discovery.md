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

## Linked project discovery

Start with the JSON from `runner create-project` or the desktop **New linked**
workflow. Use the following command for a read-only report.

```console
python -m karel2py.runner discover-project .local/linked.run.json
```

The report identifies the saved run revision and ordered module pins. Discovery
starts at the entry and follows synchronous calls with matching linked
signatures. It tracks reference arguments and resolves imported globals to the
program that owns their storage. A candidate's `program` gives that owner.
Each source location's `program` identifies the module containing the read.

A known `RUN_TASK` target with a checked pinned body contributes conditional
candidates. Discovery follows nested launches within its analysis budget. A
known first launch with the pause flag set can leave the child at entry if
its generated Python has a checkpoint before the first source action. In
that case, discovery examines the body when a known `CONT_TASK`, later
`RUN_TASK`, or numbered `CONTINUE`, `RESUME`, or `UNPAUSE` can release it.
Task numbers refer to the saved module order. A task parked at entry
contributes no body reads until a possible continuation. Potential reads remain
visible if discovery cannot verify a leading checkpoint, including entries
that use a label dispatcher.

Discovery can also stop at an explicit top-level `PAUSE` in a child body
limited to private scalar assignments, simple IF blocks, WRITE and event
signals. A known continuation resumes at the next statement and keeps
initialization and scalar value facts from earlier statements in that child.
Several such pauses can be tracked. Shared storage, external calls, nested
pauses, and ambiguous suspended positions use conservative analysis.

Discovery evaluates signal and wait selectors and can track known pauses
across a delay or simple event wait. A signal or delay alone does not
continue a paused task. Delivery, admission, and timing remain unresolved.
Dynamic or missing targets, recursion, and unmodeled effects from concurrent
tasks remain explicit gaps. A potentially runnable child with uncertain
ordering still contributes conditional reads. A child's writes do not
establish that a parent read is initialized.

Discovery evaluates condition numbers, options and captured `EVAL` operands
when it reaches a definition. In modeled structured linked flow, a known
`ENABLE CONDITION[n]` selects the possible definitions in its invocation. A
`PURGE` removes the matching definition. `DISABLE` preserves its definition for
a later enable. Branches can contribute different definitions under the same
number. Local routines share the current registry, and each external routine
call gets a separate registry. A dormant definition contributes its eager
reads at registration.

Predicates follow source order, and possible predicate and action reads stay
conditional. A handler write cannot establish a definite write in the caller
because the checkpoint may run later. If dynamic numbers, callback rearming,
unbounded loops, or other unmodeled effects prevent tracking activation, the
report includes possible reads from reachable definitions and flags the gap.

Linked motion discovery reads group-qualified `WITH` settings, movement
operands and PATH bounds before callback capture. Each local clause evaluates
its `EVAL` operands and then its `AT NODE` or `TIME` selector operands before
submission. Predicate and action reads for blocking and `NOWAIT` moves are
conditional. Multiple `WHEN` actions can run. A proven true `UNTIL` ends the scan,
so later clauses contribute no action reads. Timing, motion admission, PATH
contents, and effects across callbacks remain unresolved.

Earlier generated plans can lack original `EVAL` or temporal selector operands
and report a capture gap. Re-translate those modules to include the operands.

Missing or invalid analysis contracts, mismatched routine interfaces and
unmodeled effects remain visible in the report. Changed pinned Python bytes
prevent discovery. The report leaves saved inputs and results intact. Enter
values in `inputs.context` using the reported owner and root schema. Add
`--output` to save the report to a new private JSON file.

**New linked** and `runner create-project --discover` save an editable template
as part of the run document. Use **Prepare inputs** or `runner prepare-project`
to prepare inputs in an existing document. The saved template identifies the
entry and ordered module pins, so its identity remains stable as you edit
inputs and replay the run. Same-named variables are separate inputs when their
owners differ. Bank capacities and values still come from explicit context.
[Linked project runs](run-documents.md#linked-project-runs)

## Report and values

The `karel2py.inputs.v1` report contains target byte identity, `inputs`,
`context_requirements`, `unresolved` and `complete`. Each input identifies its
logical kind, owner, selected path, type when known, certainty and source
locations. Include locations retain their physical file/line; `python_lines`
points into the generated module. When a FILE transfer, `PATH_LEN`, or
bounded node edit depends on existing PATH storage, `path_storage` lists the
exact owner, root path and type of each saved root used. A shape dependency
can exist without a field input.

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
shapes with missing markers. The [desktop runner](desktop.md#discover-inputs-and-run-python)
lists the candidates and provides scalar and structured field editors alongside
the JSON context editor.

Linked motion reports include the `motion` and `group_locks` offline services.
Preparation lists each absent service as a requirement. Configure execution
groups and motion responses explicitly in the context. The presence of these
services alone cannot establish that any request will succeed.
[Offline motion services](offline-services.md)

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

### Refresh a linked run

Use `runner refresh-project` or desktop **Revise linked** with an explicitly
ordered set of replacement Python modules. The linked refresh reads the original
run's context and prior annotations, so it can work even if the old modules are
unavailable. The new module pins are checked before publication.
[Refresh a linked module set](run-documents.md#refresh-a-linked-module-set)

Linked refresh uses the same schema compatibility rules and keys storage by
the owning program and root path. Exact saved PATH roots needed by a whole or
selected FILE transfer, `PATH_LEN`, or a proved node edit carry forward,
including READ destinations with no initial fields to edit. A context variable without a matching discovered root
or PATH storage dependency is omitted from the new context. The `refresh.variables` row
points to its original value and marks it `not-discovered` if discovery finished,
or `unresolved` if discovery was incomplete. Even an omitted variable may be
needed by a path that analysis cannot model. Use the discovery report and
`refresh.changes` to review those gaps and supply values explicitly.

Shared offline service configuration, including saved bank values and file
fixtures, carries forward as explicit starting context. Newly discovered
requirements still need review. The refresh receipt records the prior entry and
ordered module pins, whose paths are relative to the prior document when possible,
plus the path and SHA-256 of that document. Editing or preparing the new run's
inputs preserves the receipt.

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
keep unproven leaves incomplete. Known-safe conversions and available BYTE/SHORT
sources retain their leaf availability. Scalar storage/result conversions also
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

### FILE operands

Explicit FILE statements expose the inputs used to select a FILE, evaluate
OPEN mode and endpoint strings, select PATH bounds and READ destinations, and
format or supply WRITE values. Discovery follows those operands in source order.
It finishes capturing a READ's destinations and formats before recording
possible writes from that READ.

An explicit predefined name such as `READ INPUT(n)` or `WRITE OUTPUT(n)`
reports the matching alias under `predefined_files`. Context preparation checks
whether that alias is bound. A declared FILE with the same name uses its normal
scope. FILE transfers can invalidate prior value facts. Linked analysis also
retains uncertainty about task and handler effects across FILE lifecycle
operations. Configure the endpoint and supply any PATH storage and input
stream data through the run context.

### PATH records

Discovery supports statically located PATH headers, nodes and their fields,
including PATH ARRAY cells. `ROUTE.COUNT` and `ROUTE[0].COUNT` share the
same input address, `ROUTE[0].COUNT`. READ and WRITE can also use a computed
selector when analysis proves its value. An inclusive range with known bounds
visits its selected records in source order. Unknown selectors remain explicit
in the discovery report. Retranslate older output to add the header-selector
and default-node metadata.

Provide the exact typed PATH root in `inputs.context.variables` to edit its
selected scalar or structure. The template can bind to a supplied header,
node or field, keeping the remaining PATH values and node count intact.
A missing root or unavailable node is reported as a `path-storage` requirement.
During standalone preparation or refresh and linked discovery, preparation,
or refresh, a matching saved root lets discovery expand a whole PATH, a
selected whole PATH ARRAY cell, or a whole bank into existing header and node
records. Linked references use the storage owner, including when a pinned
routine reads an imported PATH passed by reference. READ uses the shape to
identify its destinations and still requires explicit input-stream data.
WRITE adds editable records when their fields are read before a definite
source write. Each whole transfer item is limited to 1,024 scalar fields.
A conditionally reached transfer, a possible topology change, a missing
saved shape, or analysis without a saved context leaves the whole transfer
unresolved. Linked discovery also leaves it unresolved when task or handler
ordering requires a conservative second pass.

`PATH_LEN` uses the node count of a matching saved PATH when that shape still
applies. This can resolve branch decisions, node selectors and FILE range
bounds without treating any record field as an input. An unknown shape or
unmodeled intervening node edit produces a `path-topology` gap. `NODE_SIZE`
uses the translator's portable NODEDATA schema size, independently of node
count or values. Subscript expressions still contribute their own inputs
and effects. Retranslate older Python to attach the schema when an unresolved
subscript prevents finding it through the selected location.

For a matching saved shape, discovery follows unseeded `APPEND_NODE`,
`INSERT_NODE` and `DELETE_NODE` with known indexes in definite program-body
flow. Known invalid indexes report status 2 and preserve the shape.
Successful edits set status 0 and update later `PATH_LEN`, named data selectors
and FILE transfers. Earlier write facts stay with the records as they move.
If a source statement reads `ROUTE[1]` after deleting the first node, its
candidate can be `ROUTE[2]`, the location to edit in the saved context.

New records begin with missing data owned by the source, so their fields
must be written or read from a stream before use. A deleted record's
values do not become facts for the record now at that index. A range
outside the edited shape reports a gap for the transfer.

Seeded inserts, aliases into the edited PATH, edits inside routine frames,
and uncertain or potentially repeated edits leave the topology unresolved.
When discovery loses the order of a tracked PATH, it reports unknown
saved origins for its node selectors.

### Boolean and INTEGER operators

WAIT FOR entry captures are read before the live predicate. Their inputs can
be required even when a Boolean branch of the predicate is skipped. Port
edge subscripts are then read at the polling stage. REPEAT UNTIL captures
read after the first reachable execution of the body and before the Boolean
test. A body that returns before UNTIL contributes no capture inputs.

Discovery follows the translator's existing Pythonic Boolean short-circuit
execution. `FALSE AND right` and `TRUE OR right` skip right-hand reads, routines
and service requirements. `TRUE AND right` and `FALSE OR right` require them.
With an unknown Boolean left operand, right-hand inputs are conditional and
write facts merge with the skipped path. Optional writes cannot initialize a
later input definitively. The left operand and each reachable right operand are
analyzed once in source order, including nested operations and routine aliases.

Decisive right-side constants may prove the Boolean result, but their optional
side effects remain conditional. Nonreturning right-hand paths retain only live
continuation facts. INTEGER AND/OR are eager bitwise operations, including when
the left operand is zero; they do not use Boolean truthiness. Static translation
still checks skipped source for valid names/types. Execution rules are unchanged.

Generated contracts record each checked AND/OR evaluation category. Existing
payload and module fingerprints protect those annotations from stale edits.
Older contracts without the category use proven Boolean/INTEGER operand facts;
otherwise discovery reports `operator-mode` and treats right-hand effects
conservatively. Retranslation supplies the checked category. No target import,
execution, callback or runtime coercion is used during analysis.

The [Boolean](../examples/discovery_boolean_short_circuit.kl) example identifies
SOURCE as an initial input, supplied as 11 by its context fixture. Its skipped
routine leaves CALLS at zero. The [INTEGER](../examples/discovery_integer_eager.kl)
example calls the right-hand routine twice and needs no initial SOURCE value.
[Linked calls](../examples/boolean_short_circuit_linked/main.kl) keep the same
execution order. Independent snapshots, discovery expectations,
[regressions](../tests/test_input_short_circuit.py) and the
[semantic ledger](semantics/input_short_circuit_semantics.json) record offline evidence.

### Partial data copies

The analyzer retains independent availability facts for each scalar field/cell
in legal ARRAY, STRUCTURE, built-in record and joint data copies. Assignments,
private arguments and internal function results preserve known leaves even when
unrelated leaves remain missing. Matching return schemas merge only facts proved
on every live return path. Exact-schema constants survive; schema conversions
discard uncast constant facts and apply conservative leaf availability rules.

Fresh local partial data may be copied or returned without becoming a seedable
input. Reading an unproven copied scalar still produces a derived-value gap.
Scalar reads and complete-value consumers keep their initialization checks;
computed partial results, geometric conversions and CONFIG-word packing also
retain explicit complete-data preconditions. Unknown numeric SHORT conversions
may produce its missing sentinel; known-safe leaves and available BYTE/SHORT
sources are treated separately.

Snapshots precede later target selectors and arguments. Private writes do not
initialize caller storage, and return facts survive normal frame cleanup without
retaining live references. Facts obey the existing storage/step/schema budgets
and stay internal to analysis; JSON plans, reports and saved-run formats do not
gain value snapshots, callbacks or frame objects. No target execution is used.

Whole global aggregate reads remain input candidates when they access leaves
before source writes. A candidate describes the source access; it does not mean
every missing field must be filled. Legal partial copies can execute with unused
markers unchanged. In the [ARRAY example](../examples/discovery_partial_arrays.kl),
SOURCE is such a candidate, SOURCE[1] is set by code, and the second cells remain
missing while RESULT becomes 7. The [local result/private-call example](../examples/discovery_partial_values.kl)
needs no initial inputs and preserves DATA.UNUSED as a missing marker.
[Linked results](../examples/partial_discovery_values_linked/main.kl),
[regressions](../tests/test_input_partial_facts.py) and the
[semantic ledger](semantics/input_partial_fact_semantics.json) provide independent
offline execution and analysis evidence. Complete discovery retains its usual
source-access boundary; it does not certify runtime success or controller behavior.

### Captured FOR starts

Discovery follows the existing [captured-counter execution order](reference-for-counters.md#selectors-order-and-storage).
The counter reference is selected once before the initializer; the final bound
is evaluated once after initialization. The start is then read from that same
counter, including effects from an internal routine or a matching reference
argument. Grouped/private values do not write back into the counter.

Known starts and stops use the existing bounded inclusive TO/DOWNTO analysis.
A changed start may reveal an input on an additional iteration or prove the
body unreachable. Unknown but initialized starts retain conditional body reads.
An unproven initialized start reports `for-start`; it does not invent a seedable
counter input or reuse the original initializer. SHORT missing-state writes,
unproven external effects and paused routines retain explicit analysis gaps.
Existing loop budgets, unwinding and captured scalar cleanup still apply.

The [changed-start example](../examples/discovery_for_start.kl) requires SOURCE
on counter zero even though its initializer is one; supplied SOURCE=11 produces
TOTAL=11 over two iterations. The [empty-range example](../examples/discovery_for_empty.kl)
changes the start to four with stop three, leaves SOURCE missing and returns
TOTAL=7 without reading it. [Linked reference-bound execution](../examples/for_start_capture_linked/main.kl)
checks runtime order; linked static effect discovery remains incomplete.
[Regressions](../tests/test_input_for_capture.py) and the
[semantic ledger](semantics/input_for_capture_semantics.json) record offline evidence.
Discovery never executes the selected target or certifies runtime readiness.

### Checked scalar calls

Discovery retains known results from the same 17 [pure scalar builtins](constant-builtins.md#accepted-functions)
accepted by compile-time evaluation: ABS, ROUND, TRUNC, SQRT, EXP, LN, SIN, COS,
TAN, ASIN, ACOS, ATAN2, STR_LEN, SUB_STR, INDEX, CHR and ORD. STR_LEN no longer
invalidates prior writes as an unknown service. Nested known calls can resolve
branches, bounded FOR ranges, ARRAY/register addresses and own-program variable
paths. For example, `samples[ROUND(SQRT(4))]` identifies `SAMPLES[2]`.

Arguments are analyzed once, left to right. Earlier values are captured before
later argument effects; internal routine writes still affect following source.
A nonreturning argument skips the remaining arguments and continuation. Unknown
arguments contribute their ordinary input reads without invented values; their
results remain unknown. Known INTEGER-to-REAL storage promotion retains the
floating category, including through internal results and arithmetic. Existing
STRING clipping and narrow storage conversions can discard constant facts.
Unavailable scalar storage never supplies a stale
known value, including the SHORT missing sentinel.

Only known bounded primitive scalars enter the fixed whitelist of trusted pure
runtime helpers, under a temporary Pythonic numeric scope that restores the
caller's mode on success or failure. Existing finite math domains, ties-to-even
rounding, degree-based trig and bounded ASCII rules apply. Known domain failures
produce explicit `scalar-call` gaps; discovery does not publish a successful
result or invent an initial value for the destination. Existing step, contract
and storage budgets remain. Geometry constructors, services, external callbacks
and target Python code are never executed by scalar folding.

The [scalar-call example](../examples/discovery_scalar_calls.kl) identifies SOURCE
and produces TOTAL=14 with SOURCE=11, preserving an unused missing ARRAY cell.
The [address example](../examples/discovery_scalar_addresses.kl) identifies only
SAMPLES[2] and computes its own GET_VAR path; the supplied whole-root context
leaves the other cells missing. The [linked call example](../examples/scalar_discovery_calls_linked/main.kl)
provides offline runtime evidence. [Regressions](../tests/test_input_scalar_calls.py) and the
[semantic ledger](semantics/input_scalar_call_semantics.json) record the offline
contract. This is source-access analysis, without runtime-readiness or native
compiler/controller equivalence claims.

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
records its contract. `karel2py.project_input_discovery.discover_project_document(path)`
returns a linked report. `karel2py.runner.prepare_project_document(path)` saves
the linked template and returns the updated document and its exact JSON bytes.
It uses the existing context unless a caller supplies a replacement `context`.
Both functions accept `expected` with the saved JSON bytes to check the caller's
open revision. The scalar and structured save APIs use the same
`(kind, program, path)` key for linked and standalone inputs.

`karel2py.input_refresh.refresh_inputs(source, inputs, filename=...)` returns fresh
context and template objects without changing the supplied inputs. Invalid
previous metadata/context raises `InputTemplateError`; invalid target contracts
retain discovery errors. The [refresh ledger](semantics/input_refresh_semantics.json)
records the compatible migration and preservation boundaries.
