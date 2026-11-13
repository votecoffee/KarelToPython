# KCL paused-local logical copies

Pythonic opt-in KCL variable commands now copy exact logical PATH/QUEUE_TYPE data
into owned declared locals of paused routines. This adds scalar roots, banks,
complete indexed/named components and final ARRAY rows/planes to the existing
[local data editor](kcl-commands.md#local-variable-inspection). It uses retained
offline frames, with no controller command interpreter or native symbol lookup.

```text
SET LOCAL VAR target IN stage WORKER = source
SET LOCAL VAR path_target[2] IN stage FROM LIB WORKER = paths
SET LOCAL VAR queue_target[1] WORKER = queues[2]
SHOW LOCAL VAR queue_target[1] IN stage FROM LIB WORKER
```

## Sources, destinations and values

The receiver must be a fresh owned local root. Formal/borrowed destinations stay
protected. Static indexes, including comma/chained coordinates, preserve exact
remaining schemas and named component identities. No conversion or reshape is
inferred. Reads prefer a declared name in the selected frame, including readable
borrowed formals, then that frame's source-module globals. Explicit `[program]`
names use global lookup. A missing or invalid declared local never falls back.

Local sources are captured through their complete actual root or formal view.
A borrowed formal row keeps its captured concrete schema and cells; there is no
new lookup of its caller's containing variable. Global sources retain their
[selected/containing-bank rules](kcl-collection-prefixes.md). Partial PATH data,
missing nodes/header data and initialized or uninitialized queues follow the
existing logical codecs. Whole missing PATH objects remain invalid storage.

## Admission, ownership and publication

Count source and receiver scopes without payload copying, then charge one step
per descriptor/header/node scalar/queue sequence-value unit on both sides. The
complete containing local receiver root is charged even for a selected cell or
row. Each admitted scope fits 32,767 units; schemas retain their 64-level bound
and ARRAY rank limit of three. Changed admitted schemas/counts reject.

After all charges, require the same task binding, run, continuation, entered
frames, declarations, root object and selected original storage. Both execution
contexts and variable stores, the source program metadata and module identity
must remain stable. The task must still be paused and not actively driven or
aborting. Compiler FOR-root metadata must still permit the edit.

Inspect known references in both live contexts, including other global/local
roots and formal views. Aliases into any part of the receiver, including private
header holders and unselected siblings, protect the entire root. Connected timers
also protect that root. The reference scan is bounded at 32,767 entries. Source
queue buffer links are observational data and never become target ownership.

Resolve the current source after the final charge. Valid same-size data changes
are included. Validate/copy both admitted scopes before publishing selected data,
with no further checkpoints. Preserve receiver ARRAY/collection cells and
compatible PATH headers; replace PATH node lists independently and clear only
copied queue buffer links. Unselected receiver data/links and source data remain
unchanged. Earlier independent host/checkpoint effects remain visible on failure.

Existing portable statuses apply: 201 missing task/frame/root, 204 protected or
changed receiver, 205 invalid schema/data/counts or excessive scan, and 4 execution
budget failure. KCL_NO_WAIT keeps acceptance separate from completion.

## Inspection and replay

SHOW LOCAL VAR adds logical row/plane selections under the existing bounded
typed listing rules. It reports remaining dimensions, task/module/routine and
logical values without editing storage or creating aliases/cache entries. Reads
can inspect borrowed formal views.

After continuation, ordinary globals can retain independent copied results.
Closed JSON preserves those globals and command history, without restoring local
frames, borrowed views, queue buffer links or suspended execution. The
[linked example](../examples/kcl_local_collections/main.kl) starts a worker,
pauses in a library routine, copies borrowed PATH/queue inputs into owned local
rows, continues, and observes independent global results after source changes.
Its MAIN DONE guard avoids replaying commands against absent saved frames;
fresh tasks still start with fresh execution states.

Owned [local PATH data edits](kcl-local-path-data.md) now cover header/node fields,
named record/row copies and checked scalar/pose literals through private preflight.
FILE copying, resource STRUCTURE fields,
formal destinations, conversions, expression selectors and implicit discovery
remain outside this contract. Reports expose `kcl_local_collection_policy`; see
the [semantic ledger](semantics/kcl_local_collection_semantics.json) and
[authored regressions](../tests/test_kcl_local_collections.py). Native/controller
and strict-mode equivalence remain separate.
