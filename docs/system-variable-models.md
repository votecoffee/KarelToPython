# Model-backed robot system transfers

Whole numbered and active frame/tool GET_VAR/SET_VAR paths now support explicit
joint/Cartesian model conversions:

```karel
SET_VAR(entry,'SYSTEM','$MNUFRAME[1,7]',joints,status)
GET_VAR(entry,'SYSTEM','$GROUP[1].$UTOOL',joints,status)
```

SET_VAR converts a complete JOINTPOS input into an independent XYZWPREXT row,
retaining the forward adapter's CONFIG and three external-axis values. GET_VAR
converts a complete POSITION, XYZWPR or XYZWPREXT row into the declared JOINTPOS
output width. Existing model widths, zero padding, limits and adapter checks apply.
XYZWPREXT inverse input retains its external values; plain poses supply zeros.

Like [ordinary model transfers](kinematic-variable-transfers.md), conversion uses
the **calling root task's group**, explicit model/adapters, selected frame/tool
and, for inverse conversion, supplied current joints as the seed. The quoted
system group chooses the source or destination table. It does not choose another
conversion model. Linked routines and handlers retain this caller context.

SET captures its typed source before later argument selectors. GET resolves its
row after output selectors. The complete conversion stays private until final
publication. Modeled SET may populate an absent numbered row or replace a
complete configured row. Active targets require an existing selected row. Repair
a malformed old row with an explicit Cartesian SET before using modeled SET.

## Retained publication

Preparation retains the endpoint's robot bank, group object, table, selected row
and active selection where applicable. It also retains ordinary output reference
locations, selected values and containers, the variable resolver and cache bank.
Budgeted source capture and final publication recheck these participants. A new
explicit full-path binding cannot silently replace a captured system endpoint.

If a callback changes a selected row, output data/binding, active selection or
bank, publication raises before data, entry, status or cache are written. The
callback's completed edits remain. Unrelated callback effects remain valid on
success. Existing configured-row/output overlap protection still applies, and a
sticky abort prevents publication even if the adapter catches its exception.
Each numerical inverse-model evaluation retains its source execution charge.

Successful calls publish the converted value before the ordinary context-local
cache ID and zero status. Invalid models, input geometry, missing inverse seeds,
adapter errors, budget exhaustion and retained-participant conflicts raise while
preserving unpublished outputs. Existing lookup failures use status 1 and
incompatible non-model forms use status 3.

Only whole row/joint pairs gain this conversion. LOCATION, CONFIG_DATA, external
fields, selection IDs, whole ARRAY/resource banks and writable system aliases
keep their existing data contracts. Explicit full/root VariableStore bindings
still take precedence. The direct `ExecutionContext.system_pose_write` host API
continues to require a Cartesian value; [source assignments](system-pose-joints.md)
use their own conversion-before-target-selectors policy.

## Saved state and checks

Published rows, joint data and explicit models use ordinary context JSON. Cache
IDs, retained guards, callbacks and suspended execution do not persist. A fresh
execution can use the restored values without restoring a live call stack.

The [linked example](../examples/system_variable_model_project/main.kl) converts
using group 2 and accesses all four table forms in group 1, with a supplied
external joint and independent complete table expectations:

```sh
python -m karel2py.project examples/system_variable_model_project --entry MAIN --context examples/system_variable_model_project/services.initial.json --state-out model-tables.json
```

Reports expose `system_variable_transfer_policy.models`. The
[semantic ledger](semantics/system_variable_model_semantics.json) records these
authored offline choices. No controller access, native table layout, motion,
configuration branch certification or strict equivalence is provided.
