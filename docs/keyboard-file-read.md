# Typed READ from injected keyboard FILEs

Pythonic `READ file(...)` accepts the explicit `KB:TPKB` and `WD:name/TPKB`
text endpoints opened through `KeyboardInput`. It consumes supplied key events,
with cooperative waits and no physical keyboard, desktop window or controller
connection. `READ_KB` keeps its separate masked key/edit interface.

```karel
OPEN FILE input_file('RO','KB:TPKB')
READ input_file(quantity,CR,part_name,CR)
CLOSE FILE input_file
```

Supply printable events followed by `ENTER` for each input line:

```json
{"keyboard":{"events":[{"key":"4"},{"key":"2"},{"key":"ENTER"},{"key":"A"},{"key":"ENTER"}]}}
```

The example reads quantity 42 and part name A. No `Program(read=...)` callback is
consulted for an explicit keyboard FILE. Other READ endpoints retain their own
contracts. Services are explicit; the translator never opens a host terminal.

## Text parsing and transactions

`ENTER` submits an ASCII line. Existing `TextInput` parsing handles INTEGER,
REAL, BOOLEAN, bounded STRING and aggregate BYTE/SHORT element destinations.
Widths, integer bases, quoted STRING input, `ATR_FIELD` and ordered `CR` markers
use the same rules as ordinary text FILE input. Examples include
`READ input_file(value::2::16)` and `READ input_file(label::0::2,CR)`.

A statement may need several submitted lines. It validates every result before
publishing any destination. Pausing after the first line leaves every target at
its old value. Invalid later data preserves the earlier targets, committed input
cursor and all submitted text, and sets the portable FILE status to 1 before
raising. A later READ sees the same retained data; closing and reopening the
FILE discards that buffer. No native invalid-field prompt/reentry is modeled.

Only one READ observation is recorded per completed, failed or interrupted
statement. Speculative parsing while more lines are needed produces no duplicate
observations. Ordinary format/destination checks run before consuming keys.

Unread line suffixes remain with the open FILE. A numeric read followed by a
STRING read on the same line retains separating blanks. Consecutive STRING
reads advance completed records. `CR` discards the current line's remainder;
leading/repeated `CR` markers consume their specified records. A trailing `CR`
does not consume key events for a future line.

## Editing, echo and shared reads

Printable keys insert at the cursor; DELETE removes the preceding character.
LEFT/RIGHT and HOME/END move within the current line. UP/DOWN recall up to 32
completed nonempty lines from the same open FILE. Unhandled control/function
keys are consumed without producing text or terminating the line. Only ENTER
submits. A full line does not implicitly submit it.

A combined `WD:name/TPKB` endpoint echoes through its existing logical window,
clipped to one row from the current cursor. Editing preserves that cursor.
`ATR_NOECHO` suppresses this echo while ordinary window output remains available.
`KB:TPKB` has no output window. No GUI is opened.

OPEN captures the root program's DEVICE_STAT pane, defaulting to 1. All keyboard
consumers use the existing pane and oldest-reader arbitration. Generic READ jobs
claim all key classes; PUSH_KEY_RD/POP_KEY_RD suspend and resume them using the
existing masks. Concurrent reads on one FILE are rejected. Different FILEs can
wait on the same pane, with supplied events consumed once in request order.

READ_KB and typed READ share completed line history. If a typed READ leaves
nonseparator text in its buffer, READ_KB returns status 1 without changing its
outputs or consuming more events. Consume the suffix with another typed READ,
or close and reopen the FILE. A lone consumed record separator is discarded
when switching to READ_KB. Idle CLOSE discards any remaining text and history.

## Waits, limits and lifetime

Each processed key visits an ordinary execution checkpoint. Future event times
advance the explicit keyboard clock through cooperative delays. An indefinite
standalone wait without queued future input fails explicitly. Scheduler reads
can remain pending while other tasks run or supply events. Independent standalone
root clock domains cannot overlap on one KeyboardInput service.

Pause retains editor text, submitted lines and captured destination references.
Stop, abort, budget errors and ordinary failures release the active request.
Already consumed events stay consumed. Open handles remain for explicit cleanup,
and CLOSE is blocked while a read is active. Saving context requires all keyboard
FILEs closed, active reads finished and suspension frames popped. Saved events
never include consumed keys or closed-handle buffers.

Lines are limited to 254 printable characters; each statement processes at most
4096 keys and retains at most 4096 submitted bytes. The existing 64 active reads,
256 handles, finite sequence IDs and bounded history limits also apply.
IO_STATUS uses portable success/error outcomes; these are not native alarm codes.

Generic typed READ retains its line-parsing rules. A separate
[raw keyboard contract](keyboard-raw-read.md) now supports bounded PASSALL ASCII
STRING fields, and printable ATR_EOL delimiters are an explicit keyboard
extension. Binary/XML, unsupported nonprintable delimiters and native key
encodings remain excluded. Raw native transfer, physical keyboard input, native
error recovery and strict mode remain outside this feature.

This guide uses MARRC75KR07091E Rev N sections 7.2.1, 7.4 and 7.7 for source and
format context. Authored verification is in
[the keyboard FILE regressions](../tests/test_keyboard_file_read.py). It establishes
offline behavior only, without controller or native widget acceptance.

[Explicit CANCEL FILE](file-cancellation.md) now requests cooperative typed READ
cancellation without publishing partial outputs. Read its lifetime and buffering
rules before canceling; CLOSE belongs after the pending READ has unwound.
