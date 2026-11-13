# Model-backed position-register setters

Pythonic mode now accepts mixed positional inputs for all three register setters:

```karel
SET_POS_REG(1,joints,status,2)
SET_EPOS_REG(3,joints,status,2)
SET_JPOS_REG(2,point,status,2)
```

SET_POS_REG and SET_EPOS_REG convert complete JOINTPOS inputs to independent
XYZWPREXT values, preserving the forward CONFIG and three external-axis outputs.
SET_JPOS_REG converts complete POSITION, XYZWPR or XYZWPREXT inputs to nine-slot
JOINTPOS values. Plain inverse poses supply zero external values; extended poses
retain their fields. Model widths, unused-axis zero checks, geometry and limits
follow the existing [group-model getters](position-register-models.md).

The **selected register group** chooses its explicit model/adapters, selected
frame/tool and inverse current-joint seed. An explicit group overrides the caller;
omission follows the calling root, including linked routines. Existing destination
values do not seed inverse solving. No model or current state is discovered.

Matching inputs retain their existing path: Cartesian setter inputs keep their
representation, and joint setter inputs keep their supplied width. These calls
do not invoke model callbacks. Scalars, ARRAY banks and unrelated records remain
incompatible source inputs; conservative translation keeps its previous types.

## Capture and publication

Argument expressions run once from left to right: number, typed input, status
selector, then optional group. The input becomes a complete independent snapshot
before later selectors. Conversion starts after all selectors, using that group's
then-current explicit context. The converted result stays private until checked.

Modeled writes may populate an absent register or replace a complete existing
stored pose/joint value. A malformed old value requires repair through a matching
typed setter first. Preparation charges the complete source, existing receiver
schema when present, and one conversion before the model; numerical inverse
evaluations retain their execution charges.

The runtime retains the ordinary bank, count/groups/value dictionary, destination
presence/value/containers, robot/group and status location/data. Callback or
checkpoint edits to those participants reject stale publication. A callback that
fills a previously absent destination cannot be overwritten. Completed callback
effects remain; unrelated effects remain valid on success. Status cannot alias
the destination or bank metadata, including on failure-status paths. Sticky abort
prevents publication even if the adapter catches its exception.

After complete validation, one ordinary dictionary cell receives the independent
converted value, followed by zero status. Selection IDs, current robot state,
other register values and comments are not changed by the write.

| Status or failure | Result |
| --- | --- |
| 0 | Complete converted value published. |
| 2 | Invalid register number or bank group; no model call or value write. |
| 3 | Mixed input has no supplied robot context; no value write. |
| Runtime error | Missing model/seed, invalid data, failed solving, budget exhaustion or participant conflict; previous status and pending value remain unpublished. |

Input capture and overlap checks still apply before status publication. These are
portable offline conventions, rather than native controller alarm mappings.

## Saved data and checks

Written types and data use ordinary position-bank JSON: converted Cartesian rows
are XYZWPREXT and converted joint rows have nine slots. Live guards, callbacks
and suspended execution are not serialized. The
[linked example](../examples/position_register_model_write_project/main.kl)
uses group 2 from a group 1 caller, covers all three mixed setters and reads the
results back without changing current state:

```sh
python -m karel2py.project examples/position_register_model_write_project --entry MAIN --context examples/position_register_model_write_project/services.initial.json --state-out register-writes.json
```

Reports expose `position_register_model_policy.setters` and its setter capture/
publication contracts. Value-free setter and POSITION_REGISTER_MODEL observations
report operation, source line and outcome. See the
[semantic ledger](semantics/position_register_model_write_semantics.json).
This supplies no native register layout, hardware writes, robot motion,
configuration branch certification or strict equivalence.
