# Offline data-acquisition pipes

Pythonic mode implements all six DAQ call names over an explicit `Acquisition`
bank: `DAQ_REGPIPE`, `DAQ_START`, `DAQ_STOP`, `DAQ_UNREG`, `DAQ_WRITE` and
`DAQ_CHECKP`. The bank provides bounded binary records, FILE readers, snapshots,
reference-counted activation and synchronous batch streaming. It does not
acquire robot data, create network monitors or discover controller options.

```python
from karel2py.runtime import Acquisition, ExecutionContext, MemoryFiles

context = ExecutionContext(acquisition=Acquisition(), files=MemoryFiles())
```

The JSON equivalent is `{"acquisition": {}, "files": {}}`. The acquisition
bank is required. A file backend is needed only for automatic streaming to an
output file; reading a registered `PIP:` FILE uses the acquisition bank itself.

## Registration and types

```karel
DAQ_REGPIPE(1,DAQ_DRAM,100,'','packet','samples.dat',0,status)
DAQ_START(1,DAQ_STREAM,'',status)
DAQ_WRITE(1,'','packet',status)
DAQ_CHECKP(1,flags,available)
DAQ_STOP(1,FALSE,status)
DAQ_UNREG(1,status)
```

The registration signature is `DAQ_REGPIPE(number,memory,capacity,program,path,
filename,stream_size,status)`. Pipe numbers are 1..5; capacity is 1..32767 whole
records. The named variable supplies the record's concrete type and need not be
initialized for registration. Blank program strings use the executing source
module, including inside linked routines. Attached globals, explicit variable
roots, fields and array indices use the ordinary static variable resolver.

Schemas support portable scalar data, fixed arrays, named structures, CONFIG,
VECTOR, positional records and JOINTPOS1..9. FILE, PATH, QUEUE_TYPE and embedded
resources are excluded. Named type identity, dimensions and STRING capacity
must match exactly when writing another variable. Writes require all record
leaves to be initialized and representable. The value is captured before the
status output is updated, including when status aliases an input field.

Each schema is limited to 32767 scalar leaves. Reserved capacity across all five
pipes is bounded by the bank's configured `limit`, default 16 MiB and maximum
64 MiB. Registration allocates metadata and an empty buffer. Filenames are unique
plain ASCII basenames with an extension, normalized to uppercase `PIP:NAME.EXT`;
paths, device prefixes and traversal are excluded from registration names.

## Portable record encoding

Records use little-endian scalar fields without alignment or structure padding:

| Leaf | Encoding |
| --- | --- |
| BYTE | Unsigned 1 byte |
| SHORT | Signed 2 bytes |
| INTEGER | Signed 4 bytes |
| REAL | IEEE binary32, 4 bytes; unrepresentable values reject |
| BOOLEAN | 1 byte, zero or one |
| STRING[n] | Exactly n ASCII bytes, padded with NUL |
| JOINTPOS | One REAL per declared axis |
| Array or record | Recursively encoded in element or field order |

This layout agrees with the runtime's ordinary default binary FILE field
encoding. It is a portable format, not a native KAREL memory-layout claim.
STRING reads preserve padding unless source explicitly trims it. Existing
POSITION/CONFIG validation and BYTE/SHORT initialization rules remain in force.

## Start, stop and retention

`DAQ_START(number,mode,stream_device,status)` increments the start count.
Repeated starts must use the same active configuration. `DAQ_STOP(number,FALSE,
status)` decrements the count; the pipe remains active until it reaches zero.
`TRUE` forces it to zero. A final stop flushes any pending output batch before
committing the stop. A failed flush preserves both the count and pending data.

Unregister requires an inactive pipe with closed FILE readers and deletes its
records and configuration. Program completion does not stop or unregister these
shared pipes: another program can activate, write, stop or read them. Pause
also retains their state. Registration must be removed before reconfiguration.

The buffer keeps the newest `capacity` complete records. A write to a full pipe
discards its oldest record. Lagging stream readers move to the retained data
and retain an overflow flag while open. Successfully writing task roots never
observe that flag through `DAQ_CHECKP`, following the documented writer rule.

`DAQ_DRAM=0` and `DAQ_CMOS=-1` are portable memory-intent constants. Both persist
when saved explicitly; no native allocation or power-cycle behavior is applied.
`DAQ_SNAPSHT=1` and `DAQ_STREAM=2` are portable mode constants. Use their names
instead of assuming native numeric mode values.

## Reading through FILE or Python

```karel
OPEN FILE reader('RB','PIP:SAMPLES.DAT')
READ reader(sequence,measurement,label::3)
CLOSE FILE reader
```

Pipes must have been successfully started at least once before OPEN. Only
binary read-only access is accepted; `ATR_UF` with `RO` also works. Explicit
CLOSE is required. FILE positioning and byte counts apply to the current view.

Stream readers have independent cursors. Complete records release after all
live stream readers pass them; partial records stay intact. Closing a lagging
reader releases records already consumed by the remaining readers. Cursors
adjust when retained bytes are released or overflowed, so offsets are relative
to retained data rather than a permanent file offset. A failed READ batch
preserves its outputs, cursor and retained data.

Snapshot mode freezes the current retained bytes at OPEN and keeps the source
records. Close and reopen to refresh the snapshot. This is a chosen offline
view policy. At most 32 FILE readers can be open, with combined frozen-view
bytes limited to the bank's configured limit in addition to its record capacity.

`bank.read_records(number, count=None)` returns complete encoded records to a
Python caller. Stream mode consumes them; snapshot mode retains them. Close
FILE readers on that pipe first. Host reads and successful FILE reads set the
first-read flag. An empty read does not.

## Automatic file batches

Set `stream_size` to 1..capacity to append that many records per batch to
`stream_device + filename`. Automatic output requires DAQ_STREAM mode and an
explicit MemoryFiles, DeviceFiles or DirectoryFiles backend. A zero stream size
disables automatic output and ignores the device string.

Batches append synchronously. The complete target write is checked before
publishing the new record or changing pipe state. Busy output files, file-size
limits, virtual mount/read-only/quota rules, missing parent directories and
invalid rooted paths preserve the pending batch and ring data. A partial final
batch flushes on the final or forced stop. Output batching is independent of
FILE-reader consumption; reading records does not remove pending output data.

Directory output remains under the caller's explicit root and device mappings,
using atomic file replacement. There is no background worker or automatic
retry. Native asynchronous streaming, network delivery and monitor events are
not implemented.

## Status and flags

| Status | Portable meaning |
| --- | --- |
| 0 | Success |
| 1 | Missing pipe or variable |
| 2 | Invalid registration or start options/name |
| 3 | Busy pipe/file, duplicate registration or filename |
| 4 | Unsupported schema, incompatible or unrepresentable data |
| 5 | Capacity, file-size or start-count limit |
| 6 | Pipe inactive |
| 7 | Streaming backend, path, permissions or publication failure |

Invalid pipe numbers raise before output writes. `DAQ_CHECKP(number,flags,
available)` has two disjoint exact INTEGER outputs and no status argument.
An unregistered valid pipe returns zero for both. Available bytes refer to the
calling root's open reader views when present, otherwise the retained buffer.
For multiple matching views the largest unread byte count is reported.

Flag values follow the manual: DAQ_PIPREG=1, DAQ_ACTIVE=2, DAQ_CREATD=4,
DAQ_SNAPSH=8, DAQ_1STRD=16, DAQ_OVFLOW=32 and DAQ_FLUSH=64. First-read state is
retained until unregister. FLUSH is never exposed because publication is
synchronous. Output/reference, active FOR-counter and explicit routine-override
guards retain the existing service rules.

## Saved context and examples

JSON retains schema, memory intent, mode, start count, complete-record hex data,
first-read state, target prefix and pending batch bytes. Loading validates
schemas and allocation limits before decoding bounded byte strings. Writer
identities, FILE handles, reader cursors and frozen views are excluded. Close
live readers before saving; otherwise saving raises. Restored active counts
describe the offline model, not live controller or PC monitor connections.

The [record example](../examples/daq_records.kl) reads a structure through PIP
and retains a second record. The [batch example](../examples/daq_stream.kl)
flushes binary output and reads it with ordinary FILE operations. Both replay
from saved context:

```sh
python -m karel2py examples/daq_records.kl --check
python -m karel2py examples/daq_records.kl -o .local/daq_records.py
python .local/daq_records.py --context examples/daq_records.services.initial.json --state-out .local/daq_state.json
python .local/daq_records.py --context .local/daq_state.json --state-out .local/daq_state.json
```

Create `.local` before using those output paths. The report's
`data_acquisition_policy` and [semantic ledger](semantics/data_acquisition_semantics.json)
record the contract. Native byte layout, hardware sampling, option availability,
CMOS lifetime, asynchronous timing and strict equivalence remain unverified.
