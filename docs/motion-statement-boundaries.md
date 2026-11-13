# Motion statement boundaries

Pythonic motion statements retain their enclosing control flow when written
inline. A MOVE at the end of a REPEAT body leaves that block's `UNTIL` for the
loop. A following `WITH ... MOVE` begins a separate motion statement.

```karel
count=0
ATTACH
REPEAT count=count+1 MOVE AWAY 1 WITH $SPEED=25 MOVE AWAY 2 UNTIL count=2
RELEASE
```

With an explicit capture-only motion bank, this records four moves in order:
distances 1, 2, 1 and 2. Only the second move of each iteration has the local
speed setting. The loop condition runs after both moves on every iteration.
The [authored example](../examples/motion_statement_boundaries.kl) supplies
[offline context](../examples/motion_statement_boundaries.services.initial.json)
and [independent request expectations](../examples/motion_statement_boundaries.services.expected.json).

All seven MOVE forms, VIA and NOWAIT use this statement boundary. Nested REPEAT
blocks retain their own terminators. An incomplete inner IF, WHILE or other
block cannot consume an outer REPEAT's terminator. Routine-local loops, linked
source routines and cooperative pause/resume use the same parsed structure.
Newlines and semicolons retain their existing statement-separation behavior.

## Local clauses and incomplete source

MOVE-local `WHEN` and `UNTIL` clauses still require a comma before the first
clause and an `ENDMOVE` terminator. For example:

```karel
REPEAT
  MOVE AWAY 1,
    WHEN TRUE DO count=count+1
    UNTIL FALSE
  ENDMOVE
UNTIL count=2
```

Here the first UNTIL is a motion-local cancellation condition; the second is
the loop condition. The nearest parsed block determines whether a bare UNTIL
can terminate a REPEAT. Outside that block, a missing motion-clause comma is
still rejected. A WITH prefix without its own following MOVE is also rejected.

An orphan WHEN reports `E_MOTION_CLAUSE`, identifying its required CONDITION or
comma-led MOVE scope. An orphan UNTIL identifies its required REPEAT or
comma-led MOVE scope. A premature block terminator or end of source inside
motion actions names the expected `ENDMOVE`; inside CONDITION actions it names
the expected `ENDCONDITION`. These diagnostics preserve physical source locations
through the existing include mapping. They do not accept malformed source or
enable MOVE/WITH inside handler actions.

This is an offline Pythonic parsing contract. Motion still requires explicitly
configured services and logical ownership; capture-only requests do not execute
a trajectory or update robot feedback. Native source layout and controller
equivalence remain unverified. The [semantic ledger](semantics/motion_statement_boundary_semantics.json)
records this scope.
