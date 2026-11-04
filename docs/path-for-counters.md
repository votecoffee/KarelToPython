# Integral FOR counters in owned PATH data

Pythonic mode accepts INTEGER, BYTE and SHORT counter leaves in owned declared
PATH headers/nodes and PATH ARRAY cells. Fresh routine-local storage and existing
USING aliases use the same rules. This is an authored offline source extension
without native FOR/compiler/controller, counter ABI or strict-mode equivalence.

```karel
TYPE data_t=STRUCTURE count:INTEGER other:INTEGER ENDSTRUCTURE
VAR route:PATH NODEDATA=data_t PATHHEADER=data_t total:INTEGER
BEGIN
  route.other=9 total=0
  FOR route.count=1 TO 3 DO
    total=total+route.count
  ENDFOR
END
```

TOTAL becomes six, COUNT becomes uninitialized, and OTHER remains nine. The
runtime never appends a node or invents missing container storage for a counter.

## Capture, domains and cleanup

Evaluate the scalar selector once, then preflight the exact owned logical root
before initial-bound effects. Validate known data, schemas, capacities and owned
PATH/collection cells, keeping the existing 32,767 logical-leaf/collection-unit
and 64-level data-schema limits. The selected reference must identify a matching
integral leaf in that current root. Unrelated, forged-domain, readonly and
previously detached leaves cannot claim its ownership.

Capture precedes initial expression evaluation and assignment. Evaluate the final
expression once after successful initial assignment; it can observe or update the
initialized counter before the range start is captured. Index changes or node
changes performed by bound expressions do not retarget an already captured scalar.
TO/DOWNTO remain inclusive. A zero-iteration loop still initializes and clears its
selected counter.

[BYTE/SHORT domains and cleanup](narrow-for.md) remain unchanged: BYTE 0..255
restores its unknown marker, SHORT -32768..32766 restores uninitialized state, and
INTEGER follows the existing checked range and uninitialized cleanup. Initial or
selector failure preserves previous storage; after initialization, final/body
failure and ordinary exits clear only the selected scalar. Pause/resume, stop,
abort, return and loop jumps retain existing counter-frame behavior and prior
outside effects. Generic reference/data helpers are unchanged.

## Whole-root and alias proof

During the loop, protect the complete declared PATH or bank root. Reject writes
to sibling fields, other nodes/cells, whole-root assignments, node editing, READ,
conversion/service outputs, indirect variable writes, same-root nested counters
and potentially writable routine arguments. Proven readonly observations and
independent grouped values remain usable. Independent roots may own nested loops.

Retained writable aliases from direct/transitive handler-retaining routines or
opaque external calls block later counters on that root. A mutable retained
BYNAME argument cannot prove its global target disjoint, so it conservatively
blocks owned global PATH counters; fresh local roots remain independently checked.
Readonly retained arguments and detached/promoted values do not claim a writable
alias. Ordinary frame-scoped timers still clean up at return; retained timer and
handler writes keep existing root protection.

Imported PATH roots, borrowed formal roots and nonlocal roots in parameterized
routines remain excluded. A linked routine can count its own declared global PATH
or a fresh local PATH/bank, including parameterized routines with fresh locals.
Global aggregate counters retain the guard against unknown external effects.
FILE/QUEUE descriptors, CONFIG/association domains, readonly POSITION descendants,
REAL/BOOLEAN counters and direct computed counter roots remain excluded. Explicit
host mutation and independently driven program interference are outside this
source proof; it is not a runtime controller lock.

## Stable PATH node USING captures

A named/grouped/indexed PATH node selector now retains the selected node object,
including complete combined bank/node subscripts. Deleting or replacing the PATH
list cannot retarget unqualified fields to a different node or invalid list index.
Ordinary reads/writes, pause and retained callbacks keep that original object.
This also keeps USING reads consistent with a counter captured before a bound
expression removes its node.

A node detached before counter entry cannot claim membership in the current root
and is rejected before initialization. A node removed after successful capture by
an allowed bound effect retains its counter reference and normal cleanup. Source
body mutations of an active root remain rejected. Existing data-record selectors,
private computed copies, POSITION/CONFIG protections and lexical lookup retain
their normal rules.

## Data and evidence

Typed JSON and logical archives store ordinary PATH values and scalar missing
markers; counter frames, node captures, retained callbacks and suspended execution
are not persisted. Authored examples use DONE guards for exact value replay.

`path_for_policy` records the extension. `reference_for_counters` adds
`path_counter`, `root_type_spec` and `root_ownership`; USING capture rows add
`path_node` for frozen node selectors. The [semantics ledger](semantics/path_for_semantics.json)
links authored offline evidence separately from native acceptance.
