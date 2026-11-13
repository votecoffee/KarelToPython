# KCL logical collection rows and planes

Pythonic opt-in KCL variable commands now copy and inspect final ARRAY rows and
planes containing PATH or QUEUE_TYPE cells. The existing
[logical-copy contract](kcl-collection-copies.md) still defines exact schemas,
partial data, owned storage and portable statuses.

```text
SET VAR [CACHE]ROUTES[2] = [MAIN]SOURCE[1]
SET VAR [CACHE]ROW = [CACHE]CUBE[2][1]
SET VAR [CACHE]CUBE[1,2] = [CACHE]ROW
SHOW VAR [CACHE]CUBE[2]
```

## Selections and values

Flat two-dimensional banks supply rows; three-dimensional banks also supply
planes. Static comma and chained bracket indexes normalize before lookup. Named
ARRAY components keep their declared boundaries and identities. A prefix must be
the final selector. Both selected values require exactly matching remaining
ARRAY schemas, dimensions and PATH node/header or queue types. Complete cells,
whole banks and complete named components retain their earlier behavior.

The destination remains independent explicit storage. The source can come from
supplied compiled globals or explicit namespaces. Explicit full-path bindings
retain lookup precedence; a borrowed live view must match its named containing
owner. [Owned paused-local copies](kcl-local-collections.md) use their own retained
frame and source-scope checks. Borrowed local destinations and system discovery
remain excluded.

Partial PATH data and uninitialized queues remain valid logical values. Generic
data codecs, FILE copying, resource STRUCTURE fields, conversions, expression
indexes and reshaping retain their guards.

## Preparation and publication

Locate prefix cells using bounded schema/container metadata. Do not encode or
copy payloads before budget admission. For each side resolved as a live row/plane,
count and charge its complete containing bank. Other sides retain their selected
value charges. Each admitted bank/value fits 32,767 descriptor/header/node/entry
units under the existing rules. Unselected content counts toward that bound.

After charging both sides, require the original target root location, variable
store, owner object, selected parent and backing list/cell range. Resizing or
replacing the backing list rejects, even if a new list holds the same objects.
Replacing the owner with a new ARRAY sharing the old list also rejects.
Whole-owner alias, program-protection and timer checks still apply, including
claims on an unselected sibling.

Resolve the current named source after the final checkpoint and require its
admitted schema and unit count. A replacement source with the same schema/count
can supply current data. Validate/copy its complete containing bank, then select
independent prepared cells. Validate the complete receiver owner before publishing.
Malformed or shared owned siblings and changed counts fail without partial writes.
Earlier independent callback/checkpoint effects remain visible.

Publication preserves actual receiver cells and compatible headers. PATH node
lists become independent, leaving old node aliases detached. Only copied queue
buffer links reset; source and unselected receiver links/data remain live. Copies
within one bank and self-copies use prepared independent source data.

Existing portable statuses apply: 204 for protected/changed receivers, 205 for
invalid data/schema/counts and 4 for budget/execution failures. KCL_NO_WAIT keeps
acceptance separate from completion. Copies allocate no variable-cache entries.

## Inspection, replay and evidence

SHOW VAR reports the selected remaining dimensions and typed logical values,
including queue sequence counters. It follows the existing bounded inspection
rules and validates a resource prefix before encoding its selected rows. It does
not edit storage, change queue links or create a retained binding. Invalid
selection/data emits no partial listing. FILE prefixes remain unavailable.

Closed context JSON retains ordinary bank values, creation metadata and command
history. It restores no selected row view, queue buffer, active alias or suspended
task. The [standalone example](../examples/kcl_collection_rows.kl) copies PATH and
queue rows, changes their sources and reads back independent data. The
[linked example](../examples/kcl_collection_rows_project/main.kl) issues a library
command against a compiled source row and a detached dynamic destination row.
Both use DONE guards for exact saved-context replay.

Reports extend `kcl_collection_copy_policy` with prefix and inspection behavior.
The [semantic ledger](semantics/kcl_collection_prefix_semantics.json) and
[authored regressions](../tests/test_kcl_collection_prefixes.py) record offline
behavior. Native KCL/controller acceptance and strict mode remain separate.
