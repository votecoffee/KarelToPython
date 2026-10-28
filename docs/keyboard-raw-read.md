# Keyboard terminators and raw ASCII fields

Pythonic keyboard FILE input adds two explicit contracts to
[typed keyboard READ](keyboard-file-read.md): printable record delimiters and
bounded raw ASCII STRING fields. Both consume only injected `KeyboardInput`
events and retain ordinary pane arbitration, cooperative waits and cleanup.
No host keyboard, GUI or native key encoding is used.

## Printable record delimiters

Set `ATR_EOL` before OPEN to a printable ASCII character code, 32 through 126:

```karel
SET_FILE_ATR(channel,ATR_EOL,59)
OPEN FILE channel('RO','KB:TPKB')
READ channel(quantity,CR)
CLOSE FILE channel
```

The injected sequence `4`, `2`, `;` reads quantity 42. The configured delimiter
submits the edited line and is excluded from its field values. ENTER is consumed
without submitting or inserting text while a printable delimiter is selected.
LF/CR configurations keep the existing ENTER-submission behavior.

The normal line editor still supports insertion, deletion, cursor movement and
history. Typed widths, bases, STRING parsing and CR markers retain their existing
rules; CR now means advance one configured-delimiter record. Delimiters inside
quoted input still end the record; no quoting or escaping of delimiters is
inferred. Custom nonprintable delimiters other than LF/CR are rejected before
consuming events.

A consumed delimiter-only suffix can be discarded when switching to READ_KB.
Nonseparator buffered text still blocks that switch. Unconsumed future events
remain queued after a completed statement.

The manual describes ATR_EOL as a serial-port setting. Applying a printable
terminator to an injected keyboard endpoint is an explicit portable extension,
without a claim that a native teach-pendant keyboard accepts that setting.

## ATR_PASSALL fixed fields

```karel
SET_FILE_ATR(channel,ATR_PASSALL)
OPEN FILE channel('RO','KB:TPKB')
READ channel(command::3,suffix::2)
CLOSE FILE channel
```

With `A`, `B`, `C`, `x`, `y` events, the STRING results are `ABC` and `xy`.
No ENTER is needed: passall input ends when all fixed fields are full. It ignores
the configured EOL as a termination rule, and ATR_FIELD is implied for this
portable raw mode.

Every destination must be an ordinary writable bounded STRING. A positive first
format specifies its exact input width, from 1 through 254. An omitted or zero
width uses the concrete STRING capacity. A field wider than its destination is
fully consumed before right truncation. The second format may be omitted or zero;
quoted format 2, numeric destinations, CR markers and binary/XML are rejected.
The sum of all field widths must not exceed 4096 bytes, checked before input.
Repeated destinations retain ordinary source assignment order after validation.

Supported raw event encodings are deliberately narrow:

| Injected key | ASCII byte |
| --- | --- |
| A single printable character | Its code, 32 through 126 |
| ENTER | 13, carriage return |
| DELETE | 8, backspace |
| REFRESH | 23, control-W |

These controls are literal STRING bytes. DELETE does not edit, ENTER does not
terminate, and REFRESH does not refresh a display. Other named control/function
keys have no portable raw encoding. An offending event is consumed once and the
READ fails; it is not replayed or converted to an invented native layout.
The global injected-key schema is unchanged.

Raw READ performs no echo or cursor editing, including on WD:name/TPKB endpoints.
Ordinary explicit WRITE operations still work under their existing contract.
Raw fields do not enter editable line history. Completed request history stores
a bounded hexadecimal sample, byte count and field count rather than interpreting
control bytes as printable display text.

## Atomicity, buffering and lifetime

All raw fields are collected and validated before any source destination changes.
A later wait or unsupported key preserves every old destination and the committed
input position. Already collected ASCII bytes stay in the open FILE's raw buffer,
and consumed events stay consumed. Exactly one READ observation records success,
failure or interruption; unsuccessful preflight does not start a request.
Portable IO_STATUS is zero after completion and one for raw preparation/input
errors. These values do not assert native alarm equivalence.

A subsequent compatible raw READ can consume a retained prefix. Buffered raw and
line input cannot be reinterpreted across modes. READ_KB returns status 1 when
any raw bytes remain, including a lone control character. Source FILE attributes
are set before OPEN; host changes to an open handle's mode do not bypass these
buffer checks. Idle CLOSE discards the pending bytes; reopen starts fresh.

Raw requests use the same captured OPEN pane, oldest eligible reader selection,
PUSH_KEY_RD/POP_KEY_RD suspension and finite request IDs as other keyboard reads.
Each consumed event visits an execution checkpoint. Future input advances the
explicit logical clock; an indefinite standalone wait without queued future input
fails. A scheduler request may wait while other tasks supply or consume events.

Pause retains the partial raw buffer and captured destinations. Stop, abort and
errors release the active job while keeping the FILE open for explicit cleanup.
CLOSE is blocked during an active read. Context saving requires closed handles,
finished reads and popped suspension frames; consumed bytes are never restored as
future key events. The existing 64-request and 256-handle limits remain in force.

The source context is MARRC75KR07091E Rev N sections 7.2.1, 7.3 and 7.7.4. The
portable choices above are verified by
[authored raw keyboard tests](../tests/test_keyboard_raw_read.py), alongside the
existing typed keyboard tests. Native passall key layouts, live terminal input,
native keyboard error recovery and strict mode remain outside this feature.
