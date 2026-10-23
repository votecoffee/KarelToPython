# Register transfers between offline peers

Pythonic mode supports numeric and position register transfers between the caller
and an explicitly supplied [PeerBanks](remote-banks.md) host. These operations
copy bank data; they do not use networking or transform robot coordinates.

```karel
RNUMREG_RECV(host,src_idx,dest_idx,option,status)
RNUMREG_SEND(host,dest_idx,src_idx,option,status)
RPOSREG_RECV(host,src_idx,src_group,dest_idx,dest_group,option,status)
RPOSREG_SEND(host,dest_idx,dest_group,src_idx,src_group,option,status)
```

`RPREG_RECV` and `RPREG_SEND` are also accepted as position-transfer aliases.
The reference headings use RPREG while their syntax and examples use RPOSREG;
both spellings use the same checked implementation. Internal routines retain
their normal precedence over built-ins.

## Direction, options and context

RECV copies a peer's source register to the caller's destination. SEND copies
the caller's source register to a peer's destination. SEND lists the destination
first, including its group for positional data. All indices, groups and options
are INTEGER inputs, and status is a writable INTEGER output.

| Family | Option 0 | Option 1 | Option 2 |
| --- | --- | --- | --- |
| Numeric | Value and comment | Value only | Comment only |
| Position/joint | Value and comment | Value only | Invalid |

Local numeric access uses the generated Program's `registers` bank, falling back
to `ExecutionContext.numeric` when no explicit Program bank is supplied. Local
positional access uses `ExecutionContext.positions`. The selected peer must have
its own `numeric` or `positions` bank. No missing bank is created automatically,
and a peer never substitutes for a missing local bank.

```python
from karel2py import runtime as rt

local = rt.NumericRegisters(10)
peer = rt.NumericRegisters(10, {3: 1.25}, comments={3: "peer count"})
context = rt.ExecutionContext(
    numeric=local,
    peers=rt.PeerBanks({"CELL_A": {"numeric": peer}}),
)
# RNUMREG_RECV('CELL_A',3,2,0,status) gives local R[2] the REAL value
# 1.25 and its comment. Pass context=context to the generated Program.
```

Position transfers require both explicit groups to exist in their respective
banks. They retain the source POSITION, XYZWPR, XYZWPREXT or JOINTPOS
representation, configuration, external-axis values and joint width. They do not
pad axes, infer calibration, change frames/tools or invoke a kinematics model.
The destination's previous representation can be replaced by the source's
checked representation. Comments are per register, independent of group, matching
the existing PositionRegisters model.

## Preflight and failure behavior

Every argument evaluates once in source order. The operation snapshots selected
source data and checks both addresses/groups, selected content and comment
destination before changing either the value or comment. Malformed or partially
initialized positional data raises before transfer writes. Numeric INTEGER/REAL
kind is retained. Positional data is copied independently, so later source or
destination changes do not affect the other bank.

Comment-only numeric transfers work even if the source value is absent; an empty
source comment clears the destination comment. Value-only transfers leave the
destination comment unchanged and do not inspect comment contents. Combined
transfers with a missing source value preserve the destination value and comment.
Transferred comments are limited to 16 characters and then to any smaller
destination comment capacity. Explicitly shared source/destination bank objects
are allowed; source snapshots make overlapping register copies deterministic.

| Status | Portable meaning |
| --- | --- |
| 0 | Successful transfer |
| 1 | Selected source value absent |
| 2 | Invalid register/group or selected comment address |
| 3 | Invalid option |
| 5 | Unbound peer (`runtime.PEER_UNAVAILABLE`) |

Missing context/banks and invalid typed contents raise `KarelRuntimeError` while
preserving the previous status and bank data. Prior completed argument effects
remain. Status references retain ordinary exact-type, read-only and active
FOR-counter protections, including transitive routine effects. These checks do
not provide concurrent host-thread transactions or native RPC guarantees.

Reports include `remote_transfer_policy` and source-located `service_operations`.
Runtime observations retain operation, line and outcome without transferred values
or comments. Existing local and peer context JSON schemas persist completed bank
updates; task state, network sessions and native controller layouts are excluded.

## CLI example

```sh
python -c "from pathlib import Path; Path('.local').mkdir(exist_ok=True)"
python -m karel2py examples/register_transfers.kl -o .local/register_transfers.py
python .local/register_transfers.py --context examples/register_transfers.services.initial.json --state-out .local/register_transfers_state.json
```

The authored example performs both directions for numeric and joint registers,
using explicit source/destination groups and comment/value options. The runtime
package must be installed or on the Python import path. The saved state contains
the updated local and peer banks.

## Reference and limits

MARRC75KR07091E Rev N, PDF pages 518–520 and 521–523, documents RNUMREG and
positional receive/send routines. Status is labeled input in their tables, while
the descriptions define it as the operation result; this implementation requires
writable output status. The RPREG/RPOSREG naming conflict is preserved explicitly
through aliases. Numeric option 2 is documented; the position option tables list
only 0 and 1, so comment-only positional transfer remains rejected.

The [semantic ledger](semantics/register_transfer_semantics.json) records the
portable copying and preflight choices. Authored tests and CLI execution provide
offline evidence. Native RPC, error codes, robot compatibility and controller
runtime acceptance remain separate; strict mode is a future milestone.
