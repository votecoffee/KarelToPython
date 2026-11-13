# Model-backed position-register getters

Pythonic position-register getters can now bridge stored joint and Cartesian
values when an explicit RobotContext is supplied:

```karel
point=GET_POS_REG(1,status,2)
joints=GET_JPOS_REG(2,status,2)
```

GET_POS_REG converts a stored complete JOINTPOS into an independent XYZWPREXT,
including the forward adapter's CONFIG and three external-axis values.
GET_JPOS_REG converts a stored POSITION, XYZWPR or XYZWPREXT into an independent
nine-slot JOINTPOS. Existing model limits, zero padding and complete geometry
checks apply. Plain inverse poses supply zero external values; XYZWPREXT retains
its supplied axes. Inverse conversion requires explicit current joints as its
seed. Previous destination contents do not seed the search.

The **selected register group** chooses the conversion model/adapters and their
active frame/tool data. An explicit group overrides the calling task's group.
An omitted group uses the calling root's group, including in linked routines.
This follows the register address. Ordinary source and GET_VAR/SET_VAR model
conversions keep their separate caller-group rules.

Matching stored/getter representations keep their existing path and do not call
a model. Reads leave stored type, width, values and comments unchanged.
POS_REG_TYPE therefore still reports the original stored representation.
Matching setter inputs retain their existing data path.
[Model-backed setters](position-register-model-writes.md) now accept mixed
joint/Cartesian inputs under their own capture and publication contract.

## Capture and failures

Arguments and status selectors run once before register lookup. The runtime
detaches the selected source, then charges its complete schema and one conversion
before calling an adapter. Every numerical inverse-model evaluation retains its
source execution charge. Model inputs/results are detached.

Publication retains the position bank, its count/groups/value dictionary, the
selected source value and containers, robot/group, and status location/data.
Source and bank-metadata aliases cannot receive status. Changes during charging
or callbacks reject stale publication, preserving completed callback edits and
leaving the pending result and status unpublished. Unrelated source/host effects
remain valid. Sticky abort prevents publication even if an adapter catches it.

Without a robot context, a representation mismatch retains the existing status 3
and error. Missing/out-of-range registers retain statuses 1/2 and error. Once a
modeled conversion is attempted, missing models/seeds, invalid data, failed
solving, exhausted budgets or retained-participant conflicts raise while keeping
the previous status and assignment. A failed numerical search remains inconclusive
for geometric reachability.

## Saved data and checks

Existing context JSON retains the original typed position-bank values, explicit
model settings and resulting globals. Live guards, callbacks, cache identities
and suspended execution are not restored. Saving and reloading these values
connects to no controller.

The [linked example](../examples/position_register_model_project/main.kl) runs
from group 1 while querying group 2's mixed register bank. Its library converts
both representations and checks supplied external-axis metadata without changing
the bank:

```sh
python -m karel2py.project examples/position_register_model_project --entry MAIN --context examples/position_register_model_project/services.initial.json --state-out register-models.json
```

Reports expose `position_register_model_policy`. Value-free getter and
POSITION_REGISTER_MODEL observations report operation, source line and outcome.
The [semantic ledger](semantics/position_register_model_semantics.json) records
these authored offline choices. No native register layout, physical robot state,
controller behavior, configuration branch certification or strict equivalence is
provided.
