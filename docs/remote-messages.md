# Mobile messages and ZDT attachments

Pythonic mode implements `RMCN_ALERT`, `RMCN_SEND` and `QUEUE_ATTACH` over an
explicit `RemoteMessages` bank. Programs can prepare inspectable alerts, queue
XML messages and select deferred ZDT attachments. Success records local work;
there is no email, SMS, mobile application or ZDT connection.

```python
from karel2py.runtime import ExecutionContext, MemoryFiles, RemoteMessages

context = ExecutionContext(
    remote_messages=RemoteMessages(
        capacity=1024,
        message_types=['ALARM_MSG_P'],
        defaults={'address': 'operator@example.invalid', 'url': 'offline://alerts'},
    ),
    files=MemoryFiles({'TD:note.xml': '<message><value>7</value></message>'}),
)
```

JSON uses the `remote_messages` context field, with `capacity`, `limit`,
`message_types` and `defaults`. A missing service raises instead of discovering
controller settings. RMCN_SEND also requires the explicit ordinary file bank.
Alert publication and attachment selection require no file bank.

## Source forms

| Call | Arguments |
| --- | --- |
| RMCN_ALERT | address, subject, message, URL, INTEGER status output |
| RMCN_SEND | XML filename, STRING ARRAY attachments, INTEGER priority, status |
| QUEUE_ATTACH | message type, STRING ARRAY attachments, priority, status |

Blank alert address, subject and URL use the bank's explicit defaults. The
default subject is `iRConnect Alert`; default address and URL are empty. Empty
address/URL values remain inspectable offline placeholders. Other supplied text,
including semicolon-separated addresses, is preserved as ASCII data up to 254
characters. Address validity and native mobile link behavior are not inferred.

Attachments are a one-dimensional ARRAY of STRING with 1..32 entries. Empty
strings mean no attachment in that slot; an all-empty array means none. Names
are captured once before later argument-selector effects. Uninitialized entries
return status 2. Named arrays and compatible generic routine references work.
Arrays are read-only inputs, and status retains ordinary writable-reference,
type and active-FOR-counter checks. Direct source errors can raise first.

Filenames use relative slash-separated paths with an optional ordinary device
prefix. Device prefixes normalize to uppercase; relative path spelling remains
exact. Traversal, absolute paths, backslashes, control characters, duplicate
attachment names, socket/PIP/MF devices and XML-file self-attachment reject.
File names are at most 254 ASCII characters. Priority is exactly 0 or 1 and is
retained as metadata; it does not schedule a background send.

## XML publication

RMCN_SEND reads and validates the XML file before publishing its complete bytes
as hex in the outbox. XML must be UTF-8, optionally with a BOM, contain one
well-formed document, and stay within 64 nested elements and 4096 total elements.
DTDs and entity declarations reject. There is no native iRConnect schema
validation, template expansion or interpretation of the message body.

The source XML file is deleted after queue capacity, payload, access and XML
checks pass. This includes XML files on MD; the MD retention exception applies
to attachments. Failure preserves the XML file and queue. Attachments need not
exist at publication time: their paths are queued for later collection.

Only exact `MemoryFiles` and `DeviceFiles` backends support message file reads
and deletion. Open files, unmounted devices and read-only deletion targets
reject. `DirectoryFiles`, custom subclasses and other FILE services reject;
these calls cannot delete files on the host filesystem. Device deletion keeps
the existing obsolete-byte accounting policy.

## Deferred collection and ZDT selection

Host code explicitly calls `bank.collect(sequence, files)` to consume one row.
It returns `(status, detached_message)`; failure returns `(status, None)`.
Attachments are read from their current contents at collection time. After a
complete preflight, ordinary attachments are deleted and MD attachments are
retained. The returned `attachments` list contains `name`, payload `data` hex
and a `retained` Boolean for each file.

Missing, busy, inaccessible or excessive attachments preserve every file and
the queued row. There are no external callbacks or host I/O during commit.
This is an in-memory operation, without a crash journal or concurrency contract.
Alert rows and messages without attachments can be collected without files.
Collection is local consumption, without an external delivery acknowledgement.

QUEUE_ATTACH selects attachments and priority for one of up to 32 explicitly
configured message types. Type names are case-insensitive ASCII identifiers,
up to 64 characters. Unknown types return status 1; there is no native type
discovery. Repeating the call replaces the selection, and empty slots can clear
it. Selection itself reads no files and sends no message.

For an offline ZDT producer, host code calls
`bank.publish('ALARM_MSG_P', b'opaque payload')`. It snapshots the current
selection and queues opaque bytes. An absent selection uses no attachments and
priority 0. The selection remains available for later publications; changing it
does not alter previously queued rows. `SET_VAR` retains its ordinary variable
behavior and does not implicitly send native ZDT structures.

```python
bank = context.remote_messages
bank.queue_attach('ALARM_MSG_P', ['MD:latest.dg'], 1)
bank.publish('ALARM_MSG_P', b'offline event')
# Supply MD:latest.dg in context.files before collecting the queued row.
status, message = bank.collect(bank.sequence, context.files)
```

## Bounds, status and saved state

Capacity is 1..32767 queued messages, default 1024. The byte budget is 1..64 MiB,
default 4 MiB. It counts compact ASCII JSON for queued rows and pending type
selections, including hex expansion and metadata. Defaults and the explicit
type catalog are separately bounded. A collection result must also fit that
budget; its preflight conservatively reserves the queued metadata and expanded
attachment records. Payload bytes are checked before copying/hex expansion.

| Status | Portable meaning |
| --- | --- |
| 0 | Alert/XML queued, attachment selection updated, or host operation completed |
| 1 | Missing file, message type or collection sequence |
| 2 | Invalid text, attachment list/name, priority or collection sequence |
| 3 | Busy FILE |
| 4 | Unsupported backend, inaccessible file, invalid XML or host payload type |
| 5 | Byte/count limit or sequence exhaustion |

Sequences increase through 2147483646 and remain monotonic after collection.
A full outbox rejects new rows without dropping older rows or deleting input.
Host `snapshot()` and `to_config()` return detached values. Context JSON retains
all three row kinds, bounded payload hex, alert defaults, explicit type names,
pending selections and sequence history. Loading checks schemas, XML, list and
byte limits, and increasing row sequences. Files save through their existing
backend contracts; no consumer or external session is restored.

The [mobile example](../examples/mobile_messages.kl) queues an alert and XML
message while retaining attachment files. The
[ZDT example](../examples/zdt_attachments.kl) demonstrates explicit type selection.
Their fixtures support CLI execution and saved-state replay.

```sh
python -m karel2py examples/mobile_messages.kl --check
python -m karel2py examples/mobile_messages.kl -o .local/mobile_messages.py
python .local/mobile_messages.py --context examples/mobile_messages.services.initial.json --state-out .local/mobile_state.json
python .local/mobile_messages.py --context .local/mobile_state.json --state-out .local/mobile_state.json
```

Create `.local` first. Per-operation completion flags avoid duplicate messages
when replaying a successfully saved example; they are not crash recovery.
The report's `remote_message_policy` and
[semantic ledger](semantics/remote_message_semantics.json) record these choices.
Native priority dispatch, schemas, SET_VAR triggers, transport/status equivalence
and strict mode remain future work.
