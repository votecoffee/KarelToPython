# Offline peer registers and I/O

Pythonic mode supports 17 `RGET_*`/`RSET_*` procedures over explicit `PeerBanks`.
Each host name selects supplied in-memory banks. The calls do not open sockets,
resolve DNS, use credentials or discover controllers. An IP-looking string is
just a configured lookup key.

| Procedures | Peer bank and values |
| --- | --- |
| `RGET_REG`, `RSET_INT_REG`, `RSET_REALREG` | Numeric registers, preserving INTEGER/REAL kind and selected read outputs |
| `RGET_STR_REG`, `RSET_STR_REG` | String registers, using supplied bank and destination capacities |
| `RGET_REG_CMT`, `RSET_REG_CMT` | Numeric register comments |
| `RGET_PREGCMT`, `RSET_PREGCMT` | Position register comments, independent of stored position data |
| `RGET_SREGCMT`, `RSET_SREGCMT` | String register comments |
| `RGET_PORTCMT`, `RSET_PORTCMT` | Logical port comments |
| `RGET_PORTSIM`, `RSET_PORTSIM` | BOOLEAN simulation query; INTEGER initial simulated value |
| `RGET_PORTVAL`, `RSET_PORTVAL` | INTEGER logical port values; BOOLEAN ports use 0/1 |

Every call takes `host_port` first and writable INTEGER status last. The remaining
arguments follow the corresponding local operation. The remote numeric read uses
`RGET_REG(host,register_no,real_flag,int_value,real_value,status)`, with a BOOLEAN
flag. Remote port calls take `port_type,port_no` before their value/comment.
`RGET_PORTSIM` returns BOOLEAN, while the local simulation query returns INTEGER.

## Explicit peer context

```python
from karel2py import runtime as rt

peer_numeric = rt.NumericRegisters(10, {1: 42})
peers = rt.PeerBanks({
    "CELL_A": {
        "numeric": peer_numeric,
        "strings": rt.StringRegisters(4),
        "ports": rt.PortBank(
            {"DIN": 2, "DOUT": 2},
            type_codes={10: "DIN", 20: "DOUT"},
        ),
    },
})
context = rt.ExecutionContext(peers=peers)
# Pass context=context when constructing the generated Program.
```

Only `numeric`, `strings`, `positions` and `ports` bank objects are accepted per
peer. Omitted banks remain unavailable. Files, tasks, variables, callbacks and
nested contexts cannot become peer services. Position banks currently supply
comments for this family; remote position-value transfer is a separate gap.

Names are case-insensitive ASCII labels of 1..254 characters. They start with a
letter/digit and may include letters, digits, underscore, dot, colon and hyphen.
Duplicate normalized names are rejected. Constructor mappings and `lookup(host)`
mappings are copied; the supplied bank objects are deliberately shared with the
host. Hosts may explicitly share a bank across peers, but ordinary separately
constructed banks remain independent.

Peer numeric calls use the selected peer's numeric bank, including when the
calling Program has its own `registers` argument. Port calls use the selected
peer's explicit `type_codes`; codes never fall back to the caller's mapping or a
guessed native table.

```karel
RSET_INT_REG('CELL_A',1,42,status)
RGET_REG('cell_a',1,is_real,number,decimal,status)
RSET_PORTSIM('CELL_A',10,1,0,status)
RGET_PORTSIM('CELL_A',10,1,simulated,status)
RSET_PORTVAL('CELL_A',20,1,1,status)
```

`RSET_PORTSIM` sets the initial value and simulation flag together. Ordinary
remote writes can then update that simulated input. Writing an unsimulated input
is rejected. Fractional analog values cannot be read into INTEGER remote outputs;
the conversion returns status 3 and preserves the previous output.

## Values, statuses and guards

RGET_REG writes its kind flag and selected numeric output only. The unused
numeric output can remain uninitialized. A missing register preserves all value
outputs. String values truncate to the peer bank's capacity on write and the
destination capacity on read. Register/port comments are limited to 16 characters;
numeric and position comments do not initialize register contents.

| Status | Portable meaning |
| --- | --- |
| 0 | Success |
| 1 | Address exists but no value has been supplied |
| 2 | Invalid bank address or port type code |
| 3 | Invalid port value/conversion |
| 4 | Attempted write to an unsimulated input |
| 5 | Host name is not configured (`runtime.PEER_UNAVAILABLE`) |

Missing PeerBanks context, an omitted required bank or absent port type-code
mapping raises `KarelRuntimeError` before operation outputs or target banks
change. Unbound hosts do not create peers or select local banks. These statuses
are package conventions; they do not map RPCC communication errors.

Arguments evaluate once in source order. An earlier input failure skips later
selectors; earlier completed effects remain. Outputs require ordinary exact,
disjoint writable references. Existing read-only/CONFIG-subfield protections and
direct/transitive active FOR-counter checks apply. Selected read values are
validated before outputs change. Local numeric register observations remain
separate: remote operations appear in value-free `Program.service_requests` and
source-located report `service_operations`, with `remote_bank_policy` describing
the contract.

## Persistence and CLI

Context JSON stores peer banks under `peers`, with the same bank schemas used by
local contexts:

```json
{"peers":{"CELL_A":{"numeric":{"count":10,"values":{"1":42}}}}}
```

`PeerBanks.from_config`, `to_config` and context save/load preserve value kinds,
capacities, register comments, position data, port mappings, simulation and I/O
configuration snapshots. Exported JSON is detached; reloading creates fresh
banks. Shared host object identity and pending pulses are not serialized.

The authored example exercises every supported remote procedure:

```sh
python -c "from pathlib import Path; Path('.local').mkdir(exist_ok=True)"
python -m karel2py examples/remote_banks.kl -o .local/remote_banks.py
python .local/remote_banks.py --context examples/remote_banks.services.initial.json --state-out .local/remote_banks_state.json
```

The runtime package must be installed or on the Python import path. State output
includes the modified peer banks and ordinary global values.

## Reference and remaining scope

MARRC75KR07091E Rev N, PDF pages 510–516 and 523–529,
documents these RPCC routines. Some parameter tables conflict with their details
and examples: numeric register numbers are shown as BOOLEAN, the numeric kind
flag as INTEGER, port comments as INTEGER, and the string-register write value
as output. This implementation follows the explanatory text/examples: INTEGER
register numbers, BOOLEAN kind flag, STRING comments and input STRING writes.
No manual source or proprietary example is distributed here.

The [semantic ledger](semantics/remote_bank_semantics.json) records those choices.
Network transport, remote program/task execution, remote position-value transfers,
native port codes/statuses, communication timing and controller runtime acceptance
remain outside this implementation. Strict mode remains a future milestone.
