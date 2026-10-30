# Captured USING selectors

Pythonic mode accepts existing STRUCTURE and supported built-in record storage
as a USING selector. Dotted paths, ARRAY/PATH node indexes and grouping are
accepted. Supported built-in records are VECTOR, CONFIG, XYZWPR, XYZWPREXT and
POSITION. Whole ARRAY, FILE, PATH, QUEUE_TYPE and JOINTPOS values are not records;
select a record element, node or field instead.

```karel
PROGRAM sample
TYPE row_t=STRUCTURE count:INTEGER ENDSTRUCTURE
VAR rows:ARRAY[2] OF row_t slot:INTEGER
BEGIN
  slot=1
  USING (rows[slot]) DO
    count=20
    slot=2
    count=count+22
  ENDUSING
END sample
```

This sets `rows[1].count=42`; `rows[2].count` remains uninitialized. Parentheses
around a selector retain storage; they do not request a value copy.

The KAREL manual's A.20.5 USING section documents structure variables, field
priority and right-most lookup. It does not settle dynamic selector timing or
all built-in record forms. Reference capture and the added record forms are
explicit Pythonic choices, not native compiler/runtime equivalence claims.

## Entry and lifetime

Evaluate selector references once from left to right before the body, including
for an empty block. Index expressions and calls retain the normal checked
INTEGER, rank, bounds, effect and evaluation rules. If a later selector fails,
earlier selector effects remain and the body does not run. Capturing storage
does not require its scalar fields to be initialized.

A later index change does not redirect field aliases. Reentering through the
USING statement from a loop or an outside label captures fresh references.
[Nested/sibling structured transfers](nested-jumps.md) may enter IF/WHILE/REPEAT/
SELECT bodies within an existing USING chain. Entry to an uncaptured USING body
remains rejected, even when its selector names the same storage. Jumps inside the block
retain its captures. Pause/resume retains the suspended selection. RETURN,
ABORT and errors keep earlier writes and use the normal routine cleanup.

References belong to the selected storage objects. Whole record and ARRAY copies
use existing stable destination storage. PATH node selection refers to the
selected node object; collection removal/replacement does not imply automatic
retargeting or a native node-lifetime guarantee. No new runtime storage or
persistence format is introduced.

Condition handlers can outlive a block entry. Their generated predicates and
actions freeze references from enclosing USING scopes at definition. Reentering
a block cannot redirect an older handler to a new selection. A USING inside a
handler action creates its own captures when the action runs. Existing handler
predicate, event, EVAL and scheduler rules otherwise continue unchanged.

## Lookup and protection

The existing [lexical rules](pythonic-using.md) remain: inner fields override
outer fields, the right-most selector wins within a list, and selectors in the
same list resolve only against enclosing bindings. A called routine has its own
scope. Explicit calls retain routine lookup; bare names use matching fields.

Captured field aliases retain the original source root for global/formal write
analysis. Calls in indexes cannot hide writes to active FOR counters. Field-owned
FOR counters now use the [reference-counter contract](reference-for-counters.md),
including whole-root write protection and one-time capture. Existing output-overlap, read-only/formal, exact
schema, STRING capacity, initialization and numeric checks continue to apply.

POSITION NORMAL, ORIENT and APPROACH fields and their descendants remain
protected, including through nested and grouped captures. LOCATION is writable.
CONFIG fields retain bounded turn numbers and output-argument restrictions;
USING does not make protected fields ordinary unconstrained scalar outputs.

[Computed record selectors](computed-using.md), including `USING make()`, now
create explicitly private checked temporaries. Named and grouped storage still
capture live references. Computed captures have no copy-back or original source
root. [Private INTEGER counters](private-using-counters.md) use separate internal
protection identities and reject retained writable aliases. [Private connected
timers](private-using-timers.md) retain captured INTEGER leaves while keeping
whole-root counter guards and terminal cleanup. Method-like field calls, native ABI,
asynchronous selection timing, dynamic caller scope and strict mode remain outside
this contract.

## CLI examples and reports

```sh
python -m karel2py examples/indexed_using.kl --check
python -m karel2py examples/indexed_using.kl -o indexed_using.py --report indexed_using.report.json
python indexed_using.py
python -m karel2py examples/record_using.kl -o record_using.py
python record_using.py
python -m karel2py.project examples/using_selectors_project --entry MAIN
```

The linked project combines checked external TYPE declarations, shared FROM
variables and an external routine selecting a record from its array parameter.
Standalone examples have authored expected snapshots alongside their sources.

`using_scopes` retains source selectors, resolved paths, lexical IDs/parents,
field bindings and source-located uses. It adds `capture_once` and
`selector_types`. The paths describe the source expression, not the runtime index
value. `using_policy` and the [semantics ledger](semantics/using_selector_semantics.json)
record capture, callbacks, boundaries and evidence. Included selectors retain
physical source provenance in the existing source map.
`selector_captures` additionally records source kind, storage provenance, root,
expression kind, independence and copy-back behavior for each capture.
