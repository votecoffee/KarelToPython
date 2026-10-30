# Opt-in pipe waiting, snapshots and overflow

Pythonic mode accepts two read attributes for explicitly configured plain
`FilePipes` FILEs. Set them before OPEN FILE:

```karel
SET_FILE_ATR(channel,ATR_PIPWAIT,WAIT_USED)
SET_FILE_ATR(channel,ATR_PIPOVADV,OVF_EOF)
OPEN FILE channel('RO','PIP:MEASUREMENTS')
READ channel(value,CR)
CLOSE FILE channel
```

Use `PIPE_CONFIG` or the host FilePipes API to configure the named pipe first.
Acquisition pipes, sockets, keyboard/display FILEs and ordinary file backends
reject these attributes. Read-only and read/write modes are accepted; write-only
and append modes reject the read attributes before changing pipe data.

The source forms follow MARRC75KR07091E Rev N, sections 7.3 and 10.2.4. Those
sections contain conflicting descriptions of the default pipe read mode. This
implementation preserves its established behavior when attributes are absent:
reads inspect currently available data, fail at EOF, and clamp cursors after
circular overwrites. The new behavior always requires an explicit attribute.
Native defaults, status values, timing and binary layout remain unverified.

## Waiting and complete reads

`ATR_PIPWAIT,WAIT_USED` waits until an entire READ can complete. A scheduler task
yields for logical 10 ms intervals and ordinary checkpoints, letting other tasks
append data. Host code can append explicitly supplied ASCII text, bytes or a
`{"hex":"..."}` value with `bank.feed(name,data)`. No connection, host file,
background thread or automatic producer is created.

Unformatted numeric/BOOLEAN tokens require a delimiter. An unformatted STRING
requires the configured record terminator; fixed widths can complete as soon as
the requested characters are available. A quoted STRING can complete when its
closing quote arrives. A CR marker also waits for its record boundary, even after
a fixed-width field. A malformed complete field fails immediately. Text follows
the existing ASCII, width, base, quote, field-mode and custom-EOL rules.

Binary reads wait for the sum of their checked field widths. The complete READ
must fit in the circular capacity. Existing binary width, byte-order and finite
numeric conventions apply. Text and binary probes publish no observations,
values or cursor progress until all fields validate. A completed opted-in READ
publishes one ordinary read-request record and advances its cursor once. Target
selectors and format expressions are captured once before the wait.

Standalone Programs can wait only when constructed with an explicit `sleep`
callback. Each callback invocation receives 0.01 seconds and must return None;
it may feed scripted data. The default host sleeper is rejected before any wait,
so an empty standalone pipe never causes an indefinite real-clock sleep. Ordinary
execution budgets still bound explicit callback loops. This callback provenance
is retained through linked routines and same-task program calls.

## Snapshot mode

`ATR_PIPWAIT,WAIT_NOTUSED` captures the current end of the pipe when the FILE
opens. Later appends are excluded from that handle. BYTES_AHEAD and BYTES_LEFT
report bytes up to that boundary. SET_FILE_POS with -1 selects that logical end;
positions beyond it fail even when newer bytes exist. Reads return EOF when the snapshot is exhausted
and never wait. Close and reopen to take a new snapshot. This is a logical end
boundary, not a copy of the circular buffer: later overwrites can still destroy
unread snapshot data and trigger the selected overflow policy.

Without an explicit wait attribute, a separately configured overflow attribute
keeps the existing immediate-read behavior and does not create a snapshot.

## Circular overwrite policy

`ATR_PIPOVADV` accepts `OVF_EOF` or an integer byte count in 0 through the pipe's
capacity. When `record_size` is nonzero, a byte count rounds upward to its next
multiple. A rounded value above capacity is invalid and fails before opening.
These portable meanings apply only when a write discards unread bytes:

| Attribute value | Result |
| --- | --- |
| OVF_EOF | Latch an overflow EOF; subsequent reads and availability queries fail |
| 0 | Continue from the new oldest retained byte |
| Positive count | Continue that many bytes after the new oldest retained byte |

An explicit wait attribute with no overflow attribute uses OVF_EOF. Overwriting
an already consumed prefix simply adjusts the cursor and does not trigger an
overflow. Each handle retains its own policy. Snapshot end boundaries move with
the discarded prefix. Bytes consumed by a successful read remain in the pipe's
circular history for other readers.

The overflow EOF latch requires close/reopen to clear. CLR_IO_STAT can clear the
status cell but does not restore lost bytes or clear the latch. Ordinary reads,
availability queries and direct backend read_bytes calls honor this rule. A
configured advance reaching the current end can subsequently wait for new data.
Record-size rounding is a portable byte-offset rule; it does not infer native
record alignment, dictionary formatting or binary schema boundaries.

## Lifetime and persistence

Pause retains the pending READ and its captured targets. Resume retries against
current retained data. CLOSE and SET_FILE_POS reject a handle with a pending READ;
unwind or stop that read before closing or repositioning it. Stop, abort, generator closure, budget exhaustion, sleeper
failure and invalid data release the pending-read registration. Standard FILE
lifetime still applies: stopping a task does not implicitly close its FILE.

Active FILE handles prevent context serialization. After explicitly closing them,
context JSON retains pipe configuration and circular bytes. It omits cursors,
snapshot boundaries, overflow latches, pending reads, callbacks and task stacks.
Opening a restored pipe creates fresh handle state. These guarantees establish
headless offline behavior; physical/native pipe services and strict mode remain
outside this implementation.

[Explicit CANCEL FILE](file-cancellation.md) now requests cooperative typed READ
cancellation without publishing partial outputs. Read its lifetime and buffering
rules before canceling; CLOSE belongs after the pending READ has unwound.
