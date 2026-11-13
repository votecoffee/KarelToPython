# KCL selected data copies

Pythonic opt-in KCL variable commands copy exact ordinary ARRAY rows and planes
through SET VAR and SET LOCAL VAR. SHOW VAR and SHOW LOCAL VAR inspect the same
static selections. Existing command permissions and scripted-reply precedence
remain in force; these operate on supplied offline data and paused source frames.

```text
SET VAR [CACHE]GRID[2] = [CACHE]ROW
SET VAR [CACHE]ROW = [CACHE]CUBE[2][1]
SET LOCAL VAR grid[2] IN stage WORKER = row
SHOW LOCAL VAR grid[2] WORKER
```

## Selection and values

`GRID[2]` selects a flat two-dimensional row; `CUBE[2]` selects a plane.
`CUBE[2,1]` and `CUBE[2][1]` select the same row. Adjacent integer bracket groups
normalize before lookup, including complete scalar paths. Field selection and
named ARRAY component boundaries retain their existing types. A prefix must be
the final selector; there is no vectorized field lookup or expression index.

Both sides must have exactly matching concrete schemas: dimensions, named inner
ARRAY/record identities, scalar kinds and STRING capacities. Every source leaf
must be initialized and valid. Unknown BYTEs and SHORT missing sentinels do not
become default values. Data may contain supported ordinary records, Cartesian
fields or joint values under their existing complete-data rules. No numeric
coercion, reshape, aggregate literal or whole resource serialization is added.

An unqualified local source uses the selected paused frame first, then that
frame's source module. A declared missing local does not fall back to a global.
Explicit program qualifiers use attached/store globals. Detached PATH node/header
data fields retain their existing lookup. Separate [logical collection copies](kcl-collection-copies.md)
support detached whole PATH/queue values, banks and complete indexed/named
components. [Collection row/plane copies](kcl-collection-prefixes.md) now add
complete containing-bank charges and checks. Local resource roots/prefixes remain
excluded. Copies preserve receiver containers/children and do not retain
aliases into the source.

## Preparation and ownership

Locate prefix cells through bounded schema/container metadata without copying
their values. Detached copies charge selected scalar leaves; paused-local edits
retain their containing-root charges and validation. Source copying starts after
the preparation charges. Selected source windows detach into ordinary data before
the unchanged complete-source validation. Unselected source rows are not copied.

Re-resolve destination paths after charging and require the same original cells.
A changed backing list, selected parent, root binding/schema, task generation,
continuation, frame or declaration rejects before writing. Detached root reference
locations must also remain stable, even when another location holds the same
value. Earlier callback effects remain visible; this command supplies no rollback
for independent changes completed before its publication.

Whole-owner protection remains: a retained alias or connected timer on an
unselected sibling still blocks the edit. Compiled globals and borrowed owners
remain protected. Paused-local owners retain compiler FOR-root checks and must
remain paused in the same eligible frame. POSITION orientation and CONFIG field
rules remain in force. Resource data cannot become an ordinary ARRAY copy.

The existing statuses apply: 204 for changed/protected storage, 205 for invalid or
incomplete data, and 4 for command budget failure. KCL_NO_WAIT still separates
acceptance from final KCL_STATUS. No writes occur after a failed copy preflight.
SHOW operations report remaining dimensions and selected values without editing
the owner or introducing a variable-cache entry.

## Replay and evidence

Saved context retains ordinary roots and inactive command history, without row
bindings or live windows. A paused call stack is not a JSON checkpoint. The
[standalone example](../examples/kcl_data_rows.kl) uses a DONE guard for exact
saved replay. The [linked local example](../examples/kcl_local_rows/main.kl)
starts a fresh worker, edits its owned paused row, then continues it to completion.

Reports expose `kcl_prefix_data_policy`; see the
[semantic ledger](semantics/kcl_prefix_data_semantics.json) and
[authored regressions](../tests/test_kcl_data_prefixes.py). Native KCL status,
controller memory and public strict-mode equivalence remain separate.
