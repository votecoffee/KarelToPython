# Whole PATH variable transfers

Pythonic GET_VAR and SET_VAR copy whole logical PATH values with exact resolved
NODEDATA and PATHHEADER schemas. This is an authored Pythonic extension: the
reviewed KAREL manual excludes whole PATH from these calls. Offline translation
and execution do not establish native source acceptance or controller behavior.
Strict mode remains a future milestone.

## Copying a path

```karel
PROGRAM path_copy
TYPE node_t = STRUCTURE value: INTEGER ENDSTRUCTURE
     header_t = STRUCTURE count: INTEGER ENDSTRUCTURE
     route_t = PATH NODEDATA=node_t PATHHEADER=header_t
VAR source,target: route_t
    entry,status: INTEGER
BEGIN
  APPEND_NODE(source,status)
  source[1].value=7
  source.count=1
  SET_VAR(entry,'','TARGET',source,status)
END path_copy
```

GET_VAR uses the named path as its source and its fourth argument as the
receiver. SET_VAR reverses those roles. Empty program names select the executing
module's globals. Declared globals, explicit context bindings, dynamically created
roots, exact BYNAME reference formals and supplied linked programs use the same
copy rules. See the [copy example](../examples/path_transfer.kl),
[dynamic example](../examples/path_dynamic_transfer.kl) and
[linked example](../examples/path_transfer_project/main.kl).

Node and header schemas must match exactly, including nominal STRUCTURE/ARRAY
names, dimensions, STRING capacities and positional widths. Default NODEDATA
canonicalizes to STD_PTH_NODE using existing declaration rules. There is no field
mapping, numeric promotion, pose conversion or robot-model lookup inside a PATH.
Resource fields and ARRAYs containing PATH, QUEUE_TYPE or FILE remain excluded.
Whole FILE transfer and ordinary generic ANY acceptance remain excluded.

## Identity and aliases

Publication retains the existing PathValue root. A compatible existing header
uses stable data replacement, preserving header container and field aliases.
A missing header replaces that container using the ordinary missing-data rules.
The receiver gets a fresh nodes list with independent node data, even for a
self-copy. Captured aliases to the old node list, node records or node fields
continue to refer to detached old storage; they are not retargeted to new nodes.
A distinct source and its aliases remain independent. See the
[alias example](../examples/path_transfer_alias.kl).

SET_VAR validates and captures its source once at the fourth argument, before
later output-selector effects. GET_VAR resolves and snapshots its named source
after output selectors finish. Expressions run once in source order, including
cooperative pause/resume. Earlier completed selector and statement effects remain
visible if later validation fails.

## Partial data and bounds

Known values and missing scalar, node and header markers are copied. Status 12311
means the copy included initialization-tracked missing data. Unknown BYTE contents
keep the existing no-initialization-tracking policy and alone yield status 0.
An empty headerless PATH succeeds with status 0. A whole missing PATH root is
invalid storage, rather than an empty PATH. See the
[partial-data example](../examples/path_transfer_partial.kl).

Before payload allocation, each side must have at most 32767 nodes, data schemas
of at most 64 levels, and at most 32767 scalar leaves across its header and all
nodes. Missing containers still count their declared width. The complete source
and existing receiver are checked before publication: malformed known values,
nonfinite REALs, invalid CONFIG turns, SHORT/BYTE ranges, wrong fields and invalid
storage are rejected. These transfer bounds are independent of the existing
collection persistence and ordinary PATH operation limits.

| Status | Portable meaning |
| --- | --- |
| 0 | Copied without initialization-tracked missing data |
| 1 | Named program/path unavailable; status only |
| 3 | Incompatible exact schemas or data/resource kinds; status only |
| 12311 | Copied initialization-tracked missing data |

Malformed or over-limit state raises a source-located runtime error before data,
cache entry or transfer outputs are published. Output entry/status references
must be exact and disjoint from each other and the receiver; SET also checks its
dynamically resolved target. Active FOR guards remain in force.

## Saved state and evidence

Existing typed context JSON preserves logical copied nodes/header and partial
markers. It restores data, without captured aliases or suspended execution.
PATH remains excluded from portable VR variable archives; use context JSON.
Native association records, byte layouts, cache/status equivalence and controller
execution remain unverified. See [collection persistence](collection-persistence.md).

The compiler's `path_transfer_policy` describes schemas, limits, alias lifetime,
ordering and evidence boundaries. Service records keep ordinary value-free
operation/line/outcome observations. The [semantic ledger](semantics/path_transfer_semantics.json)
links authored regressions and examples separately from the reviewed manual
exclusion.
