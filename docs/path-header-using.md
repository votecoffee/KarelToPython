# PATH-header USING selectors

Pythonic USING accepts PATH values with an explicit PATHHEADER, including the
PATHDATA spelling. It exposes the header's direct fields through the existing
lexical record rules. Headerless PATHs and whole ARRAY/FILE/QUEUE_TYPE/JOINTPOS
selectors remain excluded. This is an authored offline extension without native
USING source/compiler/controller or strict-mode equivalence.

```karel
TYPE header_t=STRUCTURE count:INTEGER ENDSTRUCTURE
VAR route:PATH PATHHEADER=header_t
BEGIN
  USING route DO
    count=42
  ENDUSING
END
```

The existing route header receives COUNT=42; no node is created. A PATH node or
nested header field can still be selected as an ordinary record where its type
supports USING.

## Storage and computed values

| Selector | Capture | Field writes |
| --- | --- | --- |
| Named/grouped/indexed PATH storage | Original selected header object | Update that existing header |
| Computed PATH result, including compiled linked calls | Checked independent header data | Update only the private header |
| Nested record selected through an existing header capture | Existing nested object | Follow that capture's ownership |

Selectors evaluate exactly once, left to right, before the body, including an
empty body. All selectors in one list resolve against enclosing bindings. Inner
fields override outer fields, the rightmost matching selector wins, and normal
lookup returns after the block. Bare zero-argument function names follow existing
computed-selector resolution.

Validate the complete exact logical PATH before exposing fields. Require an
existing shaped header; never infer or allocate one. Known data, bounded strings,
partial scalar/aggregate markers and ordinary owned header/node containers follow
logical collection validation. Shared owned data, malformed schemas and missing
headers reject before body execution. Existing limits remain 32,767 PATH scalar
leaves and 64 data-schema levels. Computed values are independent; editing them
never copies back to a source PATH or argument.

A capture retains the selected header object. Supported whole-PATH assignments
preserve compatible header identity, while replacing a root or ARRAY cell does
not redirect an existing capture to a different header. Header fields keep their
normal scalar/aggregate input, assignment and routine-argument checks.

## Counters, timers and lifetime

Named captures preserve their original global/formal PATH root for effect analysis
and whole-root protection. Named PATH/resource-root FOR counters remain rejected.
Computed header data owns an isolated private record identity: INTEGER/BYTE/SHORT
counter fields and nested leaves use the existing private-counter range, cleanup,
retained-alias and whole-root write proofs. Selector calls cannot bypass active
outer-counter protections. POSITION orientation fields and CONFIG domains retain
their existing guards.

Ordinary INTEGER header leaves can use connected timers under the existing
declared/private/routine/formal ownership rules. Unknown INTEGER leaves initialize
through the normal checked timer path. Private connections never write back to
the source; duplicates, incompatible fields and timer/counter root conflicts keep
their normal errors. Routine/formal connections retain frame cleanup, while private
retained handlers use ordinary in-process timer lifetimes.

Pause/resume and jumps within a USING retain its capture. A fresh entry creates a
fresh computed header. Condition handlers freeze enclosing captures when defined;
later entries do not redirect them. RETURN, stop, abort and failure retain normal
frame/timer cleanup and prior outside effects. Entry that would skip a new USING
capture remains rejected.

## Saved data and reports

Existing typed JSON and logical archives retain ordinary PATH/header values.
They omit captures, private temporaries, retained callbacks and suspended frames.
The examples use DONE guards for deterministic logical-value replay; executable
links and callbacks are supplied afresh by a new Program/project instance.

`path_header_using_policy` records the extension. `using_scopes` retains the
original PATH selector schema and adds `path_header`, `path_type_spec` and
`selected_type_spec` to its capture metadata. Source roots remain declared names
for storage and null for computed values. Counter and timer reports use the
existing provenance/protection fields. The [semantics ledger](semantics/path_header_using_semantics.json)
records authored evidence separately from native acceptance.
