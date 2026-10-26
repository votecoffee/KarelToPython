# Offline socket messaging and file pipes

Pythonic mode implements `MSG_CONNECT`, `MSG_DISCO`, `MSG_PING` and
`PIPE_CONFIG` with explicit offline services. FILE operations route configured
socket tags and plain `PIP:` names to those services. No host socket, DNS lookup,
operating-system ping or controller connection is created.

## Socket messaging

```python
from karel2py.runtime import ExecutionContext, Messaging

context = ExecutionContext(messaging=Messaging(
    {'S1:': {'mounted': False, 'input': '42\n'}},
    hosts={'fixture': 0, 'timeout': 282},
))
```

The JSON equivalent is:

```json
{
  "messaging": {
    "ports": {"S1:": {"mounted": false, "input": "42\n"}},
    "hosts": {"fixture": 0, "timeout": 282}
  }
}
```

Configure at most sixteen distinct C1:..C8: or S1:..S8: tags. Names are
case-insensitive and require a colon. Ports default to mounted and available,
with connected false. Input and output accept ASCII text, bytes through the
Python API, or JSON `{"hex": "..."}` values. Their combined byte limit defaults
to 4 MiB, configurable from 1 byte to 64 MiB. Initialization and host input
feeding check the combined budget before adding bytes.

`MSG_CONNECT(tag,status)` sets the logical connected flag when the configured
tag is mounted and available. Repeated connect requests are idempotent.
`MSG_DISCO(tag,status)` clears it. `MOUNT_DEV` and `DISMOUNT_DEV` also accept
these socket tags through Messaging; dismount clears connected while preserving
queued input/output. Disconnect and dismount reject an open FILE. Other device
forms keep their [virtual-device contract](virtual-devices.md).

`MSG_PING(host,status)` reads an explicitly supplied case-insensitive host-result
table. Configured integer result codes pass through, including supplied timeout
codes such as 282. Missing hosts are not resolved or contacted. The table is
limited to 256 bounded ASCII names without whitespace or control characters.

### FILE input and output

```karel
MOUNT_DEV('S1:',status)
MSG_CONNECT('S1:',status)
OPEN FILE channel('RW','S1:')
READ channel(answer,CR)
WRITE channel('ack',CR)
CLOSE FILE channel
MSG_DISCO('S1:',status)
```

One FILE can be open on each connected endpoint. Ordinary R/RO, W/WO, RW and
A/AP access forms and explicit binary variants use the existing FILE field
encoding. XML access is excluded. Opening for write preserves queued data;
sockets have no file-truncation behavior.

Receive and transmit queues are independent. A successful READ consumes its
receive bytes; a WRITE appends output without echoing into input or advancing
the input cursor. `BYTES_AHEAD`/`BYTES_LEFT` describe receive data. Input offsets
are relative to the current queue and return to zero when successful reads
consume their prefix. Failed reads preserve outputs, receive bytes and cursor.
Empty input produces the ordinary EOF/error outcome, rather than waiting for
a network peer. Connection loss also fails before reading or writing bytes.

Host code can append scripted input using `bank.feed(tag,data)` and consume
detached output with `bank.take_output(tag,count=None)`. There is no automatic
peer link, reply, retry or transport callback. To simulate a peer, host code can
explicitly feed one endpoint with another's output. `set_available(tag,False)`
disconnects the logical endpoint; setting it true does not reconnect it.

| Socket status | Portable meaning |
| --- | --- |
| 0 | Logical operation succeeded |
| 1 | Configured tag or host result missing |
| 2 | Invalid tag or host name |
| 3 | Disconnect/dismount blocked by an open FILE |
| 4 | Configured endpoint unavailable or unmounted |

FILE mode, connection and byte-limit failures raise before modifying the
affected buffers. These are portable outcomes, not native transport status
equivalence.

## Plain PIP files

```python
from karel2py.runtime import ExecutionContext, FilePipes

context = ExecutionContext(file_pipes=FilePipes())
```

Use JSON `{"file_pipes": {}}` for the same empty service. Configure source
files before opening them:

```karel
PIPE_CONFIG('PIP:LOG.DAT',FALSE,1,0,'',0,status)
OPEN FILE writer('RW','PIP:LOG.DAT')
WRITE writer('hello',CR)
CLOSE FILE writer
```

The signature is `PIPE_CONFIG(name,cmos,sectors,record_size,form_dict,form_ele,
status)`. Names are plain ASCII basenames up to 72 characters, normalized to
uppercase `PIP:NAME`; an optional PIP: prefix and single leading slash are
accepted. Directory paths, traversal and other device prefixes are excluded.

Each sector is 1024 bytes. Zero sectors selects the default eight sectors.
There can be up to 32 configured files, with their combined reserved capacities
bounded by the bank's limit, default 16 MiB and maximum 64 MiB. Configuration
creates an empty buffer or preserves existing bytes. Busy reconfiguration and
shrinking below retained data fail without changing the configuration or data.

### Circular history and cursors

Plain pipe files retain the newest bytes up to their configured capacity,
following the manual's circular-buffer model. Writes beyond capacity discard
the oldest bytes and adjust all live read cursors. A write larger than the
capacity retains only its newest suffix. These are byte boundaries; no record
alignment is inferred from `record_size`.

Multiple FILEs can read and write simultaneously, up to 32 open handles per
bank. Each reader has its own cursor, and reads retain the circular history.
New readers start at the oldest retained byte. W/WO opens clear the retained
history and reset existing reader cursors; A/AP and RW append. Writes do not
advance a handle's input cursor. Seek and byte-count operations use the current
retained buffer. EOF is immediate; source can poll `BYTES_AHEAD` cooperatively.

The ordinary FILE access mode and attributes select text or binary field
encoding. FILE binary flags persist across close/reopen, as with other runtime
FILEs; use separate handles when switching between binary and text examples.
Explicit CLOSE is required, including in routines.

CMOS intent, `record_size`, formatting dictionary name and element number are
retained as metadata. They do not introduce record padding/alignment, render a
native dictionary or apply power-cycle behavior. `record_size` is nonnegative
and no larger than capacity; dictionary names are bounded ASCII strings up to
64 characters, and element numbers are 0..32767.

| PIPE_CONFIG status | Portable meaning |
| --- | --- |
| 0 | Configured successfully |
| 2 | Invalid name or configuration |
| 3 | Busy FILE or existing DAQ pipe name |
| 5 | Combined capacity, file-count or shrink limit |

### Coexistence with DAQ

Plain FilePipes and [DAQ typed pipes](data-acquisition.md) share the reserved
`PIP:` namespace but have separate stores and behavior. A name must be unique
across both. Source registration and JSON context loading reject collisions;
OPEN rejects an ambiguous name after direct host mutation. No ordinary file
backend is used as a fallback for an unconfigured PIP or socket address.

Native pipe wait/snapshot attributes, formatted dictionary display, generic
copy/list/delete routing to this bank and controller timing remain unsupported.
DAQ keeps its own typed record, snapshot and stream-consumption contract.

## Persistence and CLI examples

Messaging JSON retains supplied host results, logical endpoint flags and
bounded RX/TX bytes. FilePipes JSON retains configuration and circular history.
Both refuse saving while FILEs are open. Handles, read cursors, waiting tasks,
native connections and CMOS lifetime are not restored. A saved connected flag
is only an offline model value. Ordinary source reference, alias and active
FOR-counter guards remain in effect for the new procedures.

The [socket example](../examples/socket_messaging.kl) consumes scripted input,
queues an acknowledgement and disconnects. Its completion flag prevents a
second read when replaying a successfully saved run. The
[pipe example](../examples/file_pipes.kl) demonstrates text/binary round-trips
and truncates its output histories before each run, allowing the same replay.

```sh
python -m karel2py examples/socket_messaging.kl --check
python -m karel2py examples/socket_messaging.kl -o .local/socket_messaging.py
python .local/socket_messaging.py --context examples/socket_messaging.services.initial.json --state-out .local/socket_state.json
python .local/socket_messaging.py --context .local/socket_state.json --state-out .local/socket_state.json
```

Create `.local` before using the output paths. Reports expose
`socket_messaging_policy` and `file_pipe_policy`; the
[semantic ledger](semantics/communications_semantics.json) records their
boundaries. Native hardware, networking, timing, protocol behavior and strict
equivalence remain unverified.
