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
Several such pauses can be tracked. For supported TP operations,
`WAIT FOR PAUSE PROGRAM[n]` can establish the child boundary after a launch
or continuation, including inside a synchronous routine. Simple assignments
to parent-owned scalar storage may precede the wait, and the task number can
come from a constant or a known scalar. The wait can follow a pause inside
a statically chosen `IF` or `SELECT` branch. A continuation resumes within
the same arm without reevaluating its condition or selector and rejoins the
surrounding body when that arm ends. The wait can also follow pauses in
`FOR`, `WHILE`, and `REPEAT` loops. Discovery follows `INTEGER`,
`BYTE`, and `SHORT` counters in child-owned variables, ordinary ARRAY cells,
and STRUCTURE fields. The captured reference and inclusive bounds survive
continuation even if the source index changes. Loop exit clears the same
cell, using the unknown BYTE marker for `BYTE` and the uninitialized marker
for `INTEGER` and `SHORT`.
`WHILE` reevaluates its predicate before the next iteration. `REPEAT`
evaluates its predicate after the body and keeps its first `EVAL` sample
until that loop exits. Discovery follows up to 32 iterations per loop
activation and examines only the reached segment through each pause.
A child can also pause within a call in its own module or a pinned
linked module. This includes procedure statements and scalar calls in
assignments, `RETURN`, `IF` conditions, `SELECT` selectors, `CASE` labels,
`FOR` bounds, and `WHILE` and `REPEAT` tests. Grouped, unary, and binary
scalar expressions keep evaluated operands across a pause and evaluate the
rest left to right. A known Boolean `AND` or `OR` can skip its right-hand
operand. Integer `AND` and `OR` evaluate both operands.
For checked scalar and ordinary aggregate arguments, discovery evaluates
arguments once, left to right. Grouped data values and ARRAY prefixes keep
private copies, including their concrete shape, STRING capacities, and
missing fields. Bare references keep the originally selected storage.
The callee starts after all arguments finish, and reference shape constraints
are checked on entry. The tracker preserves each live invocation, including
its locals, the defining module's source scope, and the child task's TP
ownership. Ordinary aggregate returns preserve their fields before frame
cleanup. They can feed a supported routine, console `WRITE`, an assignment,
or a field or array selection. Pure scalar math and string built-ins also keep
earlier arguments while later arguments pause. `ARRAY_LEN` saves the selected
array's shape before evaluating an optional dimension expression. A shape
query on ordinary storage adds no array cell reads. Calls in ordinary ARRAY
subscripts can pause during scalar reads, assignments, reference arguments,
and `FOR` counter selection. Discovery saves
the receiver and earlier subscripts while later ones evaluate, including
subscripts on a detached aggregate result. A flat subscript list checks bounds
after all its indices finish. An aggregate assignment captures its right-hand
value before selecting the target and retains partial field facts. Supported
data conversions include numeric arrays, STRING capacities, array layouts,
compatible records, and context-free pose and joint conversions. Declared
conversions run before a destination selector or later argument. An ARRAY
prefix or generic ARRAY assignment uses the concrete receiver schema after
selection. A converted return is checked before frame cleanup. Discovery uses
the generated conversion metadata and the same checked helpers as execution
for known values and proven missing fields. Re-translate older modules to add
that metadata. Console `WRITE` retains each scalar value while width, base, precision,
or alignment expressions run. For ordinary arrays, data records, and joint
positions, discovery captures known scalar leaves after any supported
subscripts finish and before evaluating formats. This also covers checked
values from pure constructors such as `VEC`. Items format left to right. The
expanded piece count and combined length are checked after the last item.
Console `WRITE` also captures known PATH and queue contents before formats
run. PATH and queue ARRAY selectors can pause while choosing a cell or subarray.
A PATH range keeps its selected receiver while the two bounds run left to right.
Discovery validates the bounds after both have finished and captures the records
from the receiver's current topology. A dynamic single index can select the
header by returning zero. Whole PATHs follow record order, and ranges follow
their requested direction. Discovery follows supported `APPEND_NODE`,
`INSERT_NODE`, and `DELETE_NODE` operations and reads the captured records
before any later edit. Queue writes preserve entry order for queues and queue
arrays initialized in the child source with `INIT_QUEUE`. Discovery follows
`APPEND_QUEUE`, `INSERT_QUEUE`, `MODIFY_QUEUE`, `DELETE_QUEUE`, `GET_QUEUE`, and
`COPY_QUEUE` with known inputs and checked storage. It retains evaluated scalar
arguments and selected references while later operands pause. Queue entry IDs,
the backing ARRAY, and status outputs carry across pauses. An empty get
preserves its value and ID outputs, and a copy writes just the copied prefix
and its count and status. The same capture order applies when a checked
`WRITE` targets a predefined memory FILE. Saved queue contents and queue
transfers through FILE `READ` still use conservative discovery.
Discovery uses the emitted item types and does not produce output. Re-translate
older modules to add any missing item types or collection schemas for
paused `WRITE` discovery.
A `SELECT` keeps its captured selector across pauses and evaluates every
label once, left to right. The
first matching arm begins only after the last label finishes. A `FOR` captures
its counter before the initial-bound call, initializes that cell before the
final-bound call, and reads the start from the same cell after that call
returns. The captured counter can be an integral field in a known PATH
header or node, including one selected through a PATH ARRAY. Normal loop
cleanup clears the originally selected field.
In a checked child, `USING` evaluates selectors once, from left to right.
Borrowed ordinary data records retain their selected storage. Computed
records occupy private writable storage, including partially initialized
results from pinned routines. Nested scopes retain their lexical bindings
through pauses, and an integral field may serve as a `FOR` counter. A return
clears active counters before releasing private bindings. Re-translate
existing modules to include the selector capture modes.

`USING` also binds known PATH headers and nodes, including PATH ARRAY cells.
A captured node retains its identity when a later selector, a routine, or the
body shifts or deletes that node. A PATH assignment updates a captured header
in place. `COPY_PATH` publishes a replacement header and keeps earlier aliases
on the original record. A computed PATH from a pinned routine supplies a
private header. When `USING` receives a bare whole-record formal, it keeps
that formal's slot, including a vacant node slot. Each field access uses the
record then in that slot. A nested `USING` can bind a record field from the
current node and keep that field's storage when the outer slot moves to
another record. Starting a `FOR` on a borrowed PATH field requires that the
selected field still belong to the live owned PATH.

Scalar `UNINIT` can evaluate pausing subscripts on a borrowed record, a
`USING` field, or ordinary storage. It keeps the receiver selected before
the subscript ran and checks initialization without loading the field's
value. An unresolved initialization state keeps the test conservative.

A pausing test runs before each `WHILE` body or after each `REPEAT` body.
At the first `REPEAT` test, scalar, ordinary aggregate, PATH, and queue `EVAL`
operands run in source order, with nested captures evaluated before their
enclosing capture. Captures include PATH and queue banks, selected rows,
and checked routine results. They finish before the live test, including captures on a
side of a Boolean expression the live test later skips. Captured records and
arrays retain their fields, shape, and missing values across pauses and
subsequent iterations. Field, subscript, and shape queries see the captured
value. A PATH can come from storage or a pinned routine. Its `PATH_LEN`, header,
and node selections use the captured records even when the live PATH changes
while a later operand pauses. Queue snapshots retain initialization state,
entry IDs, and sequence numbers. Queue ARRAY shape and cell initialization
queries use the capture, and a pinned value call can bind a new backing ARRAY
to its own copy. A fresh loop activation takes fresh samples.
Re-translate earlier modules to add collection capture schemas. Calls can nest within the
ordinary routine-depth limit.

The analysis carries TP handles and bank effects across that wait and uses
the current shared bank when the child resumes. An eligible final launch or
continuation can also reach natural completion when cleanup of the entry task's
handles cannot race with the child. Shared operations between the request
and wait, unresolved branches and loop tests, unsupported or unresolved
`FOR` targets or bounds, and ambiguous suspended positions still use
conservative analysis. Checked handoffs also leave recursive calls,
other resource arguments and selectors, model-backed or unproven
data conversions, other FILE transports and selectors, and pausing FILE
`EVAL` captures unresolved.
Unproven PATH topology or descriptor history, and untracked queue
contents, use conservative analysis. Shared globals in called
library modules and retained `USING` aliases in deferred callbacks still
require review.

Discovery evaluates signal and wait selectors and can track known pauses
across a delay or simple event wait. A signal or delay alone does not
continue a paused task. Delivery, admission, and timing remain unresolved.
Dynamic or missing targets, recursion, and unmodeled effects from concurrent
tasks remain explicit gaps. A potentially runnable child with uncertain
ordering still contributes conditional reads. Without an established handoff,
a child's writes do not establish that a parent read is initialized.

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
can exist without a field input. The `binding_storage` list identifies saved
rows used for named lookup, renaming, variable catalogs, collision checks and
reserved creation capacity. Refresh retains these rows even when the program
never reads their values.

- `required`: a modeled unconditional read has no proven prior source write.
- `conditional`: the read depends on a branch, a potentially empty loop, a
  possible prior write or an uncertain effect.

These labels describe source accesses. They do not assert that every missing
runtime marker fails immediately: aggregate copies can preserve missing leaves.
An overwritten destination whose complete value remains unproven is reported
as an unresolved derived value, rather than an initial value to seed.

Variable candidates include `root_path`, `root_type` and `selectors`. A selected
path such as `SOURCE.B` explains the needed part of the value. For a declared
global, supply a `SOURCE` row with its root schema and shaped value, retaining
uninitialized markers where appropriate. Input-template preparation can build
that root shape with missing markers. For a named lookup resolved to an
existing saved binding, the input points to the actual saved row, even when
that row has a field or subscript in its name. Supplied leaves can establish
that a copy initializes its receiver. Their values remain editable inputs. The [desktop runner](desktop.md#discover-inputs-and-run-python)
lists the candidates and provides scalar and structured field editors alongside
the JSON context editor.

Linked motion reports include the `motion` and `group_locks` offline services.
Preparation lists each absent service as a requirement. Configure execution
groups and motion responses explicitly in the context. The presence of these
services alone cannot establish that any request will succeed.
[Offline motion services](offline-services.md)

Port and register candidates retain known indexes and position groups. An
initial numeric register read still offers INTEGER and REAL as editable
alternatives. With a configured bank, discovery follows source writes into
`GET_REG` and `GET_STR_REG`, including the selected numeric receiver and
string truncation. A known range failure updates only status.

`GET_PORT_VAL`, `SET_PORT_VAL` and the simulation calls use the saved
`ports.type_codes` mapping. Direct and indirect accesses share one address in
the input template. Discovery follows known value conversions and simulation
changes. A supplied bank value can establish that a compatible getter
initializes its receiver while the value itself remains editable. Saving the
first value for a bank input refreshes the reachable inputs. Comment, routing,
and live port effects still require review.

With a configured position bank, discovery resolves an omitted group from the
calling task's source group, the active robot group, or the runtime default of
group 1. An unresolved caller group retains a marker.
`POS_REG_TYPE` uses the stored schema and reports the joint width or
external-axis count without requiring a value input. `CLR_POS_REG` follows
single-group clears and group 0 clears across the configured groups.

Discovery follows compatible source writes into `GET_POS_REG` and
`GET_JPOS_REG`, including direct result selectors and joint padding. A
getter after a proven clear reports the failed read without adding a value to
seed. For a read from the initial context, the getter schema describes the
logical result and the editor uses the actual saved representation. Supplying
a missing register refreshes type-dependent inputs. With known source-written
values, discovery follows both pose-to-joint and joint-to-pose conversions
using the register's group and its selected frame and tool. A model-backed
write records the converted representation for later reads and `POS_REG_TYPE`.
Editable saved values and conversions that exceed the solver budget remain
open during discovery.

### Teach-pendant data

Caller-local TP numeric, string and position registers use the calling task's
explicit `teach_programs.callers` binding. Discovery follows the active numeric
output of `GET_TPE_REG`, the saved string capacity and the destination capacity,
and the TP position getters, setters and metadata queries. An early read points
to the physical TP program and register in the context editor. Editing a scalar
TP register refreshes discovery because the numeric kind or string length can
change which outputs the getter writes.

Discovery follows `OPEN_TPE` and `CLOSE_TPE` in the entry task and synchronous
linked routines. When a read through a handle can reach several saved programs,
the input template lists the possible positions or comments under their owning
programs. Positions addressed through a handle have separate edit locations
from caller-local position registers. Position getters require the matching
Cartesian or joint representation. Source writes preserve saved frame and
tool identifiers, and `AVL_POS_NUM` considers all configured groups. Adding a missing position refreshes discovery.

Discovery follows known `CREATE_TPE`, `COPY_TPE` and `SELECT_TPE` calls,
including catalog membership and the instruction count after
`DEL_INST_TPE`. Copying captures the source values and prior writes at the
time of the call. An early read of a copied position, register, comment or
writable header points back to its original saved program. A program created by
the source starts empty, and its positions must be written before they can be
read.

`GET_ATTR_PRG` and `SET_ATTR_PRG` follow the TP owner, comment, source name
and source version through edits, copies and known linked pause handoffs.
Copies carry the TP header values present at the time of copying. Explicit
`program_attributes` records remain attached to their own program names and
take precedence for those fields when configured. Editing a discovered TP header
refreshes discovery because its value can select a different branch.

Discovery follows small sets of literal alternatives for catalog operands and
header lookups, including choices assigned in branches or returned by routines.
With a known program and an unrestricted attribute selector, it considers the
supported attributes and the invalid-selector status. The inactive output of
a header getter stays intact when all possible selectors use the other output.

A copy with an unresolved source and a known destination leaves unrelated TP
programs available for discovery. An unrestricted overwrite destination
preserves the known source, selected programs, protected programs, and
programs with known open handles. Other eligible destinations may change.
Unrestricted creates and copies with overwriting disabled can make listing
results uncertain while preserving reads and exact-name listings for existing
programs.

`GET_TPE_CMT` and `SET_TPE_CMT` follow the addressed position across groups,
the comment's 16-character capacity and the receiver's capacity. A saved
position comment can be added or edited as a scalar. Edits refresh discovery
when the new length can change the getter's status. In a linked pause handoff,
the owning task keeps its handles while paused. The analysis follows reject
masks, rejects foreign handle operations, and releases the child's handles
at natural completion when the boundary is known. Discovery follows bounded
choices of handle, register number and position group. It also follows bounded
addresses for ordinary numeric, string and position registers and indirect
ports. A close using an unrestricted handle number can obscure which of the
task's handles closed, while keeping foreign handles and the allocation
sequence. With a runtime-selected open, discovery considers the valid access
modes and reject flags. It considers each saved target when the catalog is
small and known. A large or incomplete catalog can leave the new target
unresolved while preserving earlier handles. If possible allocation numbers
exceed the analysis budget, the new number remains unresolved. A nearby
`IF` or `SELECT` on the open status or handle keeps the new allocation on
successful paths and the previous handle on failure paths. A short sequence
of plain copies or literal assignments may precede the check. Later
correlations and unsynchronized access still use conservative analysis.

### Robot snapshots and range checks

`CURPOS` and `CURJPOS` can use the saved position or joint snapshot for the
calling group or an explicit group. Discovery follows supplied mask outputs,
joint padding and pose fields. With the portable DH model, `CURPOS` can also
derive a pose from saved joints and the selected frame and tool.

`IN_RANGE`, `J_IN_RANGE` and `CHECK_EPOS` use known source data, explicit
joint limits, or the saved DH model. Discovery bounds the solver work and
considers both branches when a result depends on run-time inputs or exceeds
that budget. Known `VEC`, `POS` and `MIRROR` values can feed these checks.
Discovery also follows `INV`, `FRAME`, frame composition with `:`,
`ORIENT`, `APPROACH` and `UNPOS`. A joint operand uses the portable DH
model and the frame and tool selected when that operand is evaluated.
`UNPOS` captures the converted pose before evaluating its output
selectors. For `>=<`, discovery and execution use the saved
`pose_tolerance` and any required `external_tolerance`. Missing
tolerances or unknown operands leave both branches open.

`JOINT2POS` and `POS2JOINT` use known operands and the calling task's
saved portable DH model. Discovery follows the pose, CONFIG, external-axis
array, joint and status outputs, including selected ARRAY rows and padded
joint widths. `POS2JOINT` can use an unset external-axis array when the
model has zero external axes. CONFIG text parsing and formatting supply
known values using the default format or an explicit saved group profile.

Direct Cartesian and model-backed conversions preserve known results in
assignments, routine value arguments and returns. This includes ARRAY and
STRUCTURE conversions, concrete shapes behind wildcard parameters, and known
missing non-geometry fields. Discovery uses the frame and tool selected at
each conversion. A direct assignment converts before selecting its
destination. A borrowed ARRAY receiver or ARRAY row uses its captured
destination shape. Converted routine arguments are private values, and
discovery follows their conversion before evaluating later arguments.

Retranslate existing generated Python to include the conversion metadata.
Discovery shares a solver budget across the elements of each aggregate.
Unknown operands and conversions that exceed the budget remain visible.

Discovery follows direct `$MNUFRAMENUM` and `$MNUTOOLNUM` assignments,
numbered and active frame/tool pose assignments, and subsequent reads in the
same group. It tracks whole rows, writable pose fields and JOINTPOS writes
with a saved portable DH model. Later `CURPOS` and Cartesian `IN_RANGE`
queries use the updated selection and rows. Where branches disagree or
selectors depend on unknown inputs, discovery reports affected reads and
keeps both possible branches. Independent groups and rows can still supply
known values. The editor retains the original saved robot configuration.

`GET_VAR`, `SET_VAR` and `VAR_INFO` can also use literal frame, tool
and selection paths in the empty, `SYSTEM` and `*SYSTEM*` namespaces.
They follow the same rows and selections as direct source assignments. Saved
variable bindings take precedence. Discovery follows transfer status and cache
entries, and `VAR_INFO` reports the stored pose representation without
allocating a transfer entry. Whole-pose JOINTPOS transfers use the calling
task's portable DH model and a bounded inverse solve. Dynamic paths, uncertain
bindings and conversions that exceed the solver budget remain review items.

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
`inputs.context`) and retain `root_path` and logical `selectors` for the
required fields or one-based KAREL indexes. An exact saved row and a field or
element selected through a different root can share a displayed path. The
editor labels their backing roots and applies each edit to its selected row.
Fill the values in `inputs.context`, then run the document normally. For the authored example set SELECTOR to true and SOURCE.B
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

PATH refresh can carry saved nodes through an added header or added fields
in the same nominal header. The node schema and existing header field types
must match. PATH ARRAY resizing also preserves overlapping coordinates when
the array ranks and identities match. New cells have empty node lists, and
new header fields use missing markers. Discovery uses the migrated shape
when evaluating node counts and transfers. Incompatible layouts can receive
fresh empty header templates for discovered header inputs. The earlier
document retains the old header and nodes.

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
the owning program and root path. Saved PATH roots with an exact or compatible
layout carry forward when needed by a whole or selected FILE transfer,
`PATH_LEN`, or a proved node edit. This includes READ destinations with no
initial fields to edit. A context variable without a matching discovered root
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
uncalled routines do not contribute inputs. `ARRAY_LEN` returns a static fact
when the selected logical dimension is known, including private wildcard ARRAY
parameters, returned arrays and array fields selected from routine results. This
can bound the existing small FOR expansion without reading missing cells.
`UNINIT` can resolve a branch when the selected fields are known initialized or
a leaf is known missing, including an unwritten routine local, a source-created
PATH record or a known SHORT sentinel. Initial values that can come from saved
context and conditional writes can leave the result unknown. A computed receiver
runs once before any dimension expression. Selectors are evaluated in source order.

Selections on detached array, joint and record results preserve known selected
fields in standalone and linked analysis. Selecting a known field can drive a
branch even when other fields in the result lack values. Consuming an unproven
scalar result is reported as a derived-value gap.

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

Literal and propagated addresses support direct ports, numeric, string and
position registers, and statically named GET_VAR/SET_VAR data paths in the current or a
pinned linked program. For whole PATHs, PATH arrays and bounded row or plane
selections, discovery follows the captured source data and retains the
receiver's updated topology. SET_VAR captures its value before resolving the
status destination, so those reads can appear even if the named target is
unknown. GET_VAR reads the named source after its arguments have run.
Exact and compatible context-free layouts preserve known fields and missing
markers. Discovery can resolve status 0 for complete data, 12311 for
proved missing data and 3 for rejected layouts. For a fresh offline context,
discovery follows entry allocation and reuse across successful named transfers
and synchronous linked calls. The requested owner and path are case-insensitive.
Equivalent subscript spellings can have separate entry numbers. A transfer with
status 1 or 3 leaves the entry and allocation order intact. Branches can retain
the next number when they allocated the same number of entries, and retain a
specific entry when its number agrees across all continuing branches. New entry
numbers remain unknown when earlier operations could have changed the cache.
Discovery reports unproved topology and model dependencies and stops at a
proven output overlap. It checks the `GET_VAR` receiver before
looking up the named source and checks the `SET_VAR` destination after the name
resolves. A declared root with an invalid field or subscript yields status 1
without a transfer. An invalid `SET_VAR` destination still yields status 1
after source capture. Discovery can resolve typed bindings in the supplied
context. Declared globals take precedence. For an undeclared name, an exact
saved path takes precedence over traversal of a saved root. Missing external
bindings and unproved container shapes remain open for review. A field in a
retained old record or rebuilt retired slot can receive
status when its storage is disjoint from the live destination.

For fields of PATH headers and nodes, including PATH ARRAY cells, discovery
follows `GET_VAR` and `SET_VAR` through proven nested records, joint axes and
bounded array selections. It follows aggregate-field transfers when the
selected containers are present. After a node edit, a read-before-write
dependency retains the node's original saved address. A missing intermediate
container, invalid named PATH subscript or undeclared header yields status 1
and leaves the entry and destination untouched. A PATH ARRAY node lookup also
requires the node's other aggregate fields to be present. A missing scalar can
transfer with status 12311. Discovery follows whole selected headers and nodes
when their aggregate containers are present, preserving known fields and
missing scalar markers. Whole-node outputs follow captured list slots through
modeled edits. A wholly uninitialized record in a scalar PATH, or a wholly
uninitialized PATH header, can transfer with status 12311. Its whole-record
address also accepts a compatible replacement. A missing node record in a PATH
ARRAY rejects named lookup with status 1. When a whole-record transfer clears a
PATH slot, borrowed fields keep their original storage and whole-record
references follow the slot. Earlier reference arguments keep their captured
storage during evaluation of later arguments, including a named transfer's
status selector. Discovery follows checked PATH edits in direct routines
used for the owner, variable path, and scalar-array status subscript of
`GET_VAR` and `SET_VAR` when the starting topology and affected references
are known. A captured node slot follows the current list position.
A borrowed field keeps its original storage even when its node is removed.
A checked `COPY_PATH` in the same argument positions can replace the descriptor.
Previously captured slots and fields retain the old descriptor's storage.
Discovery also follows the already evaluated raw source of `COPY_PATH` and
the separately evaluated PATH base of a node subscript through a checked
replacement. The retained descriptor sees edits made before replacement and
writes through its borrowed slots afterward. A flattened ARRAY and node
subscript resolves the cell after evaluating both subscripts. A selected
aggregate READ with a PATHHEADER follows its writable PATH reference when
resolving the node. Initializing an uninitialized PATH record in the saved-run
editor refreshes the reachable inputs. Discovery reports unresolved compound
selectors, ambiguous edits, and unproved record storage.

Discovery also tracks statically named scalar, record, and ordinary array
transfers. Equal-rank arrays copy the leading elements in row-major order,
up to the smaller element count. Discovery reports reads from only those
elements for a statically located source. A computed source can also read
inputs while constructing its result. The destination tail is preserved, and
only selected elements determine the missing-data status. A proved rank or
layout mismatch produces status 3. Discovery checks the source topology for a
rejected `GET_VAR` on a PATH or PATH bank and omits unused payload inputs. An
earlier `SET_VAR` source capture stays visible. A proved conversion failure
stops discovery before any receiver, entry, or status update. Destination fields
with special write guards remain conservative. A saved portable DH model
allows named joint and Cartesian transfers, including compatible records and
the selected ARRAY prefix. Discovery retains the cache entry and missing-data
status from the prepared transfer. A saved context with no robot returns
status 3 for a transfer that requires a model.

### Named routine arguments

Discovery follows direct `BYNAME` arguments with a known owner and path to
declared, saved or source-created data and PATH storage. The called routine
borrows scalar fields,
whole records, and proven ARRAY rows or planes. A whole PATH node or header
keeps its captured slot across later argument evaluation. A selected field
keeps its captured record storage. A blank owner selects the calling task
root, including inside a synchronous linked routine.

A successful `BYNAME` writes the lookup entry before evaluating later
arguments, using the same offline cache as `GET_VAR` and `SET_VAR`. Proven
invalid selections, type mismatches, and entry overlap stop discovery at
the argument. Targets with unsupplied external bindings, unsupported resource
storage, or unproved addresses retain an explicit discovery gap.

When an input template is prepared against a validated context, discovery
can follow `CREATE_VAR` with known names, schema, dimensions and pool.
Declared types are available from the executing module and pinned linked
modules. A successful creation makes the new data available to `GET_VAR`,
`SET_VAR` and direct `BYNAME` calls. Discovery follows known creation status
codes and carries matching storage through branch joins. Freshly created
values follow their runtime initialization rules and stay out of the input
template. Analysis reports a gap when creation depends on unresolved values,
repeat or callback order, or unknown capacity. Resource use continues to
require review.

With a validated context, discovery can follow `RENAME_VAR` and
`RENAME_VARS` when the names and bindings are known. A renamed saved value
keeps its original input pointer because the source run performs the move.
Subsequent named transfers use the new spelling and retain the lookup entry.
Existing routine aliases keep their captured storage, including when the
source creates a new variable under the old name. Branches with different
binding layouts leave affected lookups unresolved.

Discovery follows `VAR_INFO` for known ordinary variable paths, including
ARRAY prefixes and supported PATH fields and records. It publishes the type,
dimensions, string capacity and status, using known initialization facts
when available. When initialization is unknown, both flag-dependent branches
are considered. A metadata check alone creates no value input.
`GET_VAR`, `SET_VAR` and `VAR_INFO` can also follow explicit saved
`$` bindings. Discovery uses an exact saved path first, then the longest
matching saved prefix and its stored order. Values point to their backing
rows, including rows reached through a different system owner spelling.
Lookups that depend on a robot model or resource state may still need review.

With a validated context, `VAR_LIST` follows known program selectors, name
patterns, type filters, pagination, and output formats. It uses the current
names after source creation or renaming. On success it writes the page,
including empty tail elements. A known failure writes only the status.
Discovery retains the saved roots that may affect the page on refresh.
Dynamic selectors and unproved namespace or output storage are reported as gaps.

### Program metadata

With a validated context, `PROG_LIST` follows known patterns, type filters,
and offsets across the attached modules and saved program catalogs. A
successful page clears unused buffer slots and advances the optional cursor.
A cursor read before a source write remains an input. Failed pages preserve
the buffer, count and cursor.

`LOAD_STATUS` follows known loaded and initialization flags from saved
records and checked programs. When an attached program has globals whose
initialization cannot be proved, discovery considers both flag-dependent
branches. `GET_ATTR_PRG` follows known saved attributes, attached program names
and types, and source comments. Successful lookups write only the selected
attribute output and status. Discovery follows `SET_ATTR_PRG` writes to
supported offline attributes when the target and its activity state are
known. Activity and read-only checks preserve the prior attribute. If a
branch might add a previously absent attribute, the next read may return
either success or the missing-attribute status and preserves its receiver on
failure. Task activity with unresolved ordering still requires review.

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
catalog entries, 32 routine frames and 32 iterations for constant `FOR`
expansion or a checked linked loop activation.
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
scope.

In checked linked child segments, `WRITE` resolves an explicit predefined
alias or the module's default alias through the saved `files` memory backend.
It resolves the alias before evaluating items and keeps it across pauses in
item and format routines. Text and binary formatting use the configured
attributes. Discovery tracks written bytes, the shared cursor, and explicit
`CLOSE FILE` for those aliases in its analysis state.
The file's byte capacity applies at publication, including the existing
length restriction for update mode. Close the predefined FILE in the source
to include its bytes in the saved run results.

A checked child also follows declared FILE variables and FILE ARRAY cells
through `OPEN FILE`, `WRITE`, and `CLOSE FILE` on the same memory backend.
OPEN captures the selected cell before its mode and endpoint run. Each of
those expressions can pause. A WRITE uses the captured cell's current
format while its items run, so an operand can open that same cell before
the batch is written. Explicit CLOSE releases the endpoint for another
handle. `GET_FILE_POS`, `BYTES_LEFT`, and `IO_STATUS` use the modeled
descriptor and cursor, including when selecting the FILE cell pauses.

For those memory FILEs, discovery also follows `SET_FILE_ATR`,
`SET_FILE_POS`, `BYTES_AHEAD`, and `CLR_IO_STAT`. A declared handle retains
its attributes across close and reopen. A seek to `-1` selects the end, and a seek
outside the file returns status `2` and preserves the cursor.
`BYTES_AHEAD` checks that the two output cells are distinct before writing
the available byte count and status. FILE selection, scalar arguments, and
output selectors can pause. Each completed operand is retained for the call.

A checked routine can borrow a scalar FILE, a whole FILE bank, or a selected
row or plane, including through pinned source linkage. Argument selection
captures the original descriptor or cells before later arguments run.
Open ARRAY formals inherit concrete dimensions, and fixed or named formals
are checked at call entry. Forwarding retains the same descriptor state and
cursor. A predefined alias passed directly to a FILE formal retains its
configured binding. `ARRAY_LEN` can inspect a FILE bank or view without a
backend, and `UNINIT` tests whether the selected FILE is closed.

A checked `READ` from a memory file can capture scalar,
ordinary ARRAY, and named STRUCTURE destinations. The FILE selection,
destination subscripts, and format expressions can pause. Each destination
is retained before its format expressions run. Discovery validates the
complete text or binary batch before recording destination initialization
and the new cursor. Modified file images follow seeks, overwrites, truncation,
and close and reopen. In append/read mode (`AP`), reading is available after
a successful nonempty write. Files created or truncated by the program can
supply known values to subsequent branches. Saved bytes remain editable,
so values read from a file that still depends on saved bytes stay unknown
during discovery.

With known PATH storage, memory FILE `READ` also accepts whole PATHs, selected
headers or nodes, ranges in either direction, and PATH banks or rows. The
transfer uses ordinary scalar, ARRAY, and STRUCTURE fields in declaration
order. Range bounds can pause and run before the current PATH records are
selected. Discovery keeps those records' captured fields while formats and
later destinations run. A format routine can remove a node without changing
which storage receives the previously captured values.

Bare PATHs, whole PATH banks, and named ARRAY components passed by reference
retain the caller's storage through pauses and pinned routine forwarding.
Grouped PATHs and flat row or plane arguments with matching schemas capture
private copies before later operands run. Discovery retains shaped records
with uninitialized scalar fields so later reads can fill them. `PATH_LEN`
uses the selected PATH's current node count after its selectors finish.
`ARRAY_LEN` uses the bound bank's concrete dimensions.

For matching schemas, assignment snapshots a PATH, bank, or bank slice before
the destination selectors run. `COPY_PATH` retains the selected source
descriptor while bounds, destination and status selectors, and the optional
flag are evaluated. It follows whole copies and inclusive ranges in either
direction, including a known out-of-range status. A bounded PATH `WRITE` also
keeps the source descriptor selected before its bounds ran. These transfers
can follow a descriptor replaced by another checked `COPY_PATH`.

A direct node subscript keeps the PATH loaded before its index runs. If
the index pauses and a checked `COPY_PATH` replaces the live descriptor,
discovery selects from the original list and checks its bounds. A borrowed
node slot still belongs to that original list. Reads and assignments through
an old field use that record's storage. A later index into an ordinary ARRAY
field also keeps the selected record if the PATH node moves or is deleted.
Flat bank coordinates, including chained coordinates normalized to a flat
list, select the PATH cell after all their index expressions run.

Checked routines can return detached PATHs and PATH ARRAYs with matching
schemas. The return captures records before the routine's local storage is
released. These results can feed assignments, value arguments, `COPY_PATH`
sources, and bounded `WRITE` transfers. Selectors and `PATH_LEN` or
`ARRAY_LEN` use the returned records and concrete dimensions, including
after another pause. A returned PATH can carry shaped records whose scalar
fields are filled later by a FILE read.

Memory FILE `READ` can also replace values in initialized queues and selected
queue banks. Banks are visited in row-major order, and initialized
queues with no entries consume no fields. A batch needs at least one existing
entry per queue transfer. Each queue capture must still match at publication.
A successful read preserves entry IDs and sequence, releases the previous
backing ARRAY binding, and leaves that ARRAY's contents available for ordinary
reads and writes. Later queue operations can bind a different backing ARRAY.
Values read from saved files stay editable through queue copies and removals.

Initialization can come from the source or a matching typed queue in the run
context. Discovery uses saved entry IDs, order, and sequence for queue
operations and keeps entry values editable. Project refresh retains the
compatible queue or bank root when discovery uses that saved state.

Checked routine calls preserve queue argument passing across pauses and
forwarding to pinned modules. Bare queues, whole banks, and separately named
ARRAY components passed by reference keep their caller's cells. Grouped
storage and flat row or plane arguments capture private queue values before
later operands run. Those copies keep initialization, entry IDs, and
sequence, with their own backing ARRAY binding. `UNINIT` inspects the selected
queue and `ARRAY_LEN` uses the bound bank's concrete shape.

Checked routines can return detached queues and queue banks with matching
schemas. These values can feed assignments, value arguments, selectors,
`UNINIT`, `ARRAY_LEN`, and bounded `WRITE`. A queue assignment preserves
entry order, IDs, and the sequence counter and releases the receiver's backing
ARRAY binding. An uninitialized result clears the receiver's queue state,
including any entries it started with in the saved context.

Discovery retains up to 64 KiB of modified file images per tracked flow.
Larger writes can still establish size and cursor facts. Reads whose image
was omitted, PATH reads with unresolved shapes or specialized fields, queues
without proven initialization, other backends, and FILE arguments
obtained through `BYNAME` still use conservative analysis.
Configure the endpoint and supply any PATH storage and input stream data
through the run context.

### PATH records

Discovery supports statically located PATH headers, nodes and their fields,
including PATH ARRAY cells. `ROUTE.COUNT` and `ROUTE[0].COUNT` share the
same input address, `ROUTE[0].COUNT`. READ and WRITE can also use a computed
selector when analysis proves its value. An inclusive range with known bounds
visits the records in range order, including a declared header at either
zero endpoint. The known saved or source-created node count validates the
entire range before discovery lists its inputs. Discovery also checks the
scalar field limit before listing range inputs. If a statically tracked bound
routine replaces the descriptor, WRITE still reads the descriptor captured
before the bounds ran. READ resolves the writable PATH reference after both
bounds run, then captures its selected fields before evaluating formats or
later destinations. Direct selectors and `COPY_PATH` bounds can also call
routines with tracked PATH effects. Unknown selectors remain explicit in the
discovery report. Retranslate older output to add the header-selector and
default-node metadata.

A selector on a scalar PATH routine result, such as `build_route()[1..0]`
or `build_route().total`, uses the returned records and their known fields.
Discovery follows reads in the routine and only checks the selected result data
for completeness. A selected result with unproven data requires review in the
discovery report.

For PATH ARRAYs with known topology, discovery tracks each cell's node count
and known fields through assignments, selected rows and planes, private
arguments and routine results. It follows compatible context-free layout
conversions and retains known values and missing markers through nested
records and array components. It can prove joint padding and track fields
from checked CONFIG word and Cartesian conversions when their inputs are known.
Whole returned-bank WRITE checks the combined scalar field limit.
With the calling task's saved portable DH model, discovery also follows
joint and Cartesian conversions in a PATH ARRAY. It checks every captured
cell before publishing any model results, with a shared solver budget across
the bank. Retranslate older targets to include the order of static
conversions before destination index expressions.

A discovered header in a fresh PATH or fixed PATH ARRAY can be edited directly.
The template builds an empty node list and the declared header with missing
field markers. This consumes the shared template allocation budget. To edit
an existing node, provide the exact typed PATH root in `inputs.context.variables`.
The template preserves supplied records and node counts. An input with no
editable node storage is reported as a `path-storage` requirement.
Standalone and linked saved-run discovery can use the offline runtime's
empty initial node list for a declared PATH or PATH ARRAY cell with no
context override. An exact saved root supplies its own initial node count.
Imports and borrowed calls use the owning program's context. A conflicting
saved type leaves the initial shape unresolved.

A known shape lets discovery expand a whole PATH, selected PATH ARRAY cell,
or whole bank into header and node records. READ requires at least one
existing record and explicit stream data. An empty headerless selection
contributes no fields to WRITE. WRITE adds editable records when their fields
are read before a definite source write. Each whole transfer item is limited
to 1,024 scalar fields. A conditionally reached transfer or possible topology
change can leave the transfer unresolved. The initial defaults apply to
saved-run analysis with a validated context. A conservative linked pass
after a task or handler ordering gap leaves the initial shape unresolved.

`PATH_LEN` uses the known initial or updated node count. This can resolve
branch decisions, node selectors and FILE range bounds without treating any
record field as an input. An unknown shape or unmodeled intervening node
edit produces a `path-topology` gap. `NODE_SIZE`
uses the translator's portable NODEDATA schema size, independently of node
count or values. Subscript expressions still contribute their own inputs
and effects. Retranslate older Python to attach the schema when an unresolved
subscript prevents finding it through the selected location.

With a known shape, discovery follows `APPEND_NODE`, `INSERT_NODE` and
`DELETE_NODE` with known indexes in definite program-body flow. Known invalid
indexes report status 2 and preserve the shape.
Successful edits set status 0 and update later `PATH_LEN`, named data selectors
and FILE transfers. Earlier write facts stay with the records as they move.
If a source statement reads `ROUTE[1]` after deleting the first node, its
candidate can be `ROUTE[2]`, the location to edit in the saved context.

Unseeded records begin with missing data owned by the source, so their
fields must be written or read from a stream before use. A deleted record's
values do not become facts for the record now at that index. A range
outside the edited shape reports a gap for the transfer.

A seeded append or insert discovers reads of the seed before the edit.
The capture precedes evaluation of the status selector and conversion flag.
Discovery follows checked direct routines in the index, seed, scalar-array
status selector, and conversion operands. Node edits resolve the current PATH
through the receiver reference after those operands run. `COPY_PATH` also
follows a direct scalar-array status selector while retaining its earlier
raw source descriptor.
An exact NODEDATA seed carries its known field values into the new record.
A compatible context-free conversion with explicit TRUE tracks known
converted values as well as initialized fields. A known missing seed fails at
capture, before the status selector and conversion flag. A known invalid
conversion or missing converted field fails before the node edit or status
write. A statically rejected layout sets status 3 before the index check.
A shifted PATH record used as a seed retains its original saved input address.
Node edits and `COPY_PATH` stop discovery at a proven overlap between the
live receiver and its status reference, after discovering any earlier
operand reads. If a conversion operand has already detached the captured
status field from the receiver, the status write reaches that original field.

A known model-backed seed is converted using the frame and tool selected
after the other operands have been evaluated. Unknown seeds, conversion
choices for different layouts, unproved alias origins, and uncertain or
potentially repeated edits leave the topology unresolved.
When discovery loses the order of a tracked PATH, it reports unknown saved
origins for its node selectors.

`COPY_PATH` follows a checked whole copy `(0,0)` or an inclusive forward or
reverse range. Discovery reads the selected source nodes and declared
header after evaluating the call operands. It preserves their saved
addresses after prior node edits. A returned PATH is captured when the
source routine runs, and the copy uses that detached value after later
operands run. A proved copy replaces the destination shape with independent
records and preserves checked scalar conversion facts. Later `PATH_LEN`,
data accesses and FILE transfers use that shape. The destination can be a
declared PATH with no saved seed.

A copy preserves missing leaves. Reading an incompletely proven copied
value later can report a `derived-value` gap. Known rejected layouts or
bounds produce status 3 or 2 before reading the source records. A known
conversion failure prevents publication and the success status write.
Unknown bounds, unproved destination references, and unavailable model
results leave the destination effect unresolved.

Discovery also follows whole scalar PATH assignments between declared
variables or selected PATH ARRAY cells in definite program-body flow.
It captures the source header and nodes before evaluating the destination
selector. Later writes to the source leave the copied values independent.
Exact and context-free conversions preserve partial data, and the destination
can start without a saved seed. Retranslate older Python to include the
checked assignment schema. A saved portable DH model also enables conversion
of compatible NODEDATA and PATHHEADER records. Uncertain receiver selection
and unavailable model results produce a discovery gap.

Grouped scalar PATH arguments capture private values before later arguments
are evaluated. Bare reference arguments retain the caller's storage and
ordinary field writes. Fresh routine-local PATHs begin empty. Definite
assignments and node edits on the routine's own local or private PATHs can
establish their shape. Returning a checked PATH snapshot preserves partial
data and detaches it from the routine frame. Model-backed layout conversion
uses the calling task's saved model. The caller can
assign that result or use its node count in `PATH_LEN`. These rules also apply
across pinned linked routines with matching interfaces.

A direct synchronous procedure can edit, copy into, or replace a borrowed
PATH when all active argument references are resolved and the operation
preserves any references into its storage. The updated shape belongs to
the caller, so later queries and transfers use the moved records' original
saved addresses. These calls can be nested or linked.

In-place node edits preserve borrowed header references. A whole-node borrow
follows the contents of its captured list slot through a proved insertion or
deletion. A field or nested element borrow stays with its record when that
record moves or is deleted. Discovery uses the original or source-created
record identity to find saved inputs and keep writes with the correct record.
These borrows also survive checked child pauses in earlier or later
arguments and across pinned calls. They include indexed headers and nodes,
flat or chained PATH ARRAY selections, and nested fields whose indexes can
pause. A grouped value argument loads the record currently in the slot and
takes a private copy.
A captured slot can be forwarded even while it is out of bounds. If the same
list grows to that slot again, discovery can follow later reads and writes.
An access while the slot is out of bounds reports the unavailable position.

Whole assignment updates the existing destination header and replaces the
node list. A whole-header borrow sees the assigned header, and a nested
header borrow can follow a complete replacement header. A checked COPY_PATH
replaces the descriptor, leaving proved borrows of its old header and node
list accessible. In both cases, a whole-node borrow keeps the contents of
its slot in the old list, including any shifts before replacement. Later
writes through old references leave the new nodes independent. A slot that
was missing when the list was replaced stays missing when the new list grows.

The status output must use storage disjoint from the edited PATH at the start
of the service call. A field from a previously deleted or replaced record can
provide this storage. A known rejection of a node edit or COPY_PATH updates
the status and preserves the shape and live references.

Outside checked task slices, some structural edits in operand routines
remain unresolved while the caller holds earlier captured references.
Discovery reports the lost origin before reading or writing an affected
captured record.

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
