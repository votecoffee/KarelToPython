# Injected keyboard input and headless menus

READ_KB, PUSH_KEY_RD, POP_KEY_RD, DISCTRL_ALPH, DISCTRL_SBMN and DISCTRL_PLMN
use an explicit KeyboardInput service. It consumes configured or host-fed key
events, with no physical keyboard capture, desktop window or controller link.

```json
{"keyboard":{"events":[{"key":"O"},{"key":"K"},{"key":"ENTER"}]}}
```

Events accept a single printable ASCII character, a supported key name or its
portable numeric code. Optional pane defaults to 1; at_ms defaults to zero.
Events sort by logical time, then monotonic sequence. Explicit supported names
include ENTER, DELETE, LEFT/RIGHT, UP/DOWN, HOME/END, PREV/NEXT, NEW_MENU, SELECT
and F1..F10. Saved context retains only unconsumed events; it never replays input.

```python
keyboard = rt.KeyboardInput(events=[{'key':'ENTER','at_ms':25}])
keyboard.feed('F1', pane=2)
keyboard.feed_text('ready', pane=1)
context = rt.ExecutionContext(keyboard=keyboard)
```

## FILEs and panes

```karel
SET_FILE_ATR(input_file,ATR_PASSALL)
OPEN FILE input_file('RW','KB:TPKB')
READ_KB(input_file,text,12,KC_DISPLAY,KC_ENTER_KEY,0,'',count,key,status)
CLOSE FILE input_file
```

KB:TPKB accepts text input modes RO/R or RW/UD. It has no output window.
WD:name/TPKB also requires an existing window in PendantDisplay. Combined FILEs
forward ordinary WRITE, WRITE_DICT/WRITE_DICT_V and SET_CURSOR to that window.
Closing releases both handles. [Typed FILE READ](keyboard-file-read.md) parses
submitted lines through the ordinary scalar format rules. Binary/XML, byte
positions, seeking and input-availability queries remain explicitly rejected.
IO_STATUS reports completed reads and accepted cancellation requests; CLR_IO_STAT
clears that value without clearing a pending cancellation.

OPEN captures the calling root program's global DEVICE_STAT, or pane 1 when it
is missing/uninitialized. Valid panes are 1..9. Later changes to DEVICE_STAT do
not retarget an open FILE; routine-local values do not select the root pane.

Combined input echoes a one-row field at the window's current cursor, clipped
to the available columns. The full buffer can be longer than its visible field.
Echo pads the visible field and preserves ordinary FILE cursors/byte positions.
ATR_NOECHO suppresses read echo. ATR_PASSALL records input intent without
changing a host terminal mode. Their portable attribute IDs are 8 and 7.
Ordinary output still works with NOECHO. A readonly combined FILE rejects WRITE.

## Editing and masks

READ_KB(file,buffer,size,accept_mask,term_mask,timeout,initial,count,key,status)
requires disjoint writable STRING/INTEGER outputs. Capacity is the smaller of
size and the destination STRING capacity; size is 0..254. Initial text must fit
and contain printable ASCII. A positive full buffer completes with KY_FULL;
zero capacity can wait for a termination key without accepting text.

| Class constant | Portable mask |
| --- | --- |
| KC_DISPLAY | 1 |
| KC_FUNC_KEY | 2 |
| KC_KEYPAD | 4 |
| KC_ENTER_KEY | 8 |
| KC_DELETE | 16 |
| KC_LR_ARW | 32 |
| KC_UD_ARW | 64 |
| KC_OTHER / KC_PREV_KEY | 128 |

Masks combine with OR or addition. A terminating class takes priority and does
not insert that event into the buffer. Otherwise accepted printable keys insert
at the cursor. Accepted DELETE removes the character to the left. LEFT/RIGHT
and HOME/END move within the field. These editing keys require both their class
and KC_DISPLAY in accept_mask. UP/DOWN recall up to 32 previously completed,
nonempty values from the same open FILE; history is lost when it closes.
Unaccepted events are consumed without insertion unless another pending read
owns that key class. The oldest eligible reader gets a matching event.

KY_ENTER=13 and character terminators use ASCII codes. Arrow/control constants
start at 1001, F1..F10 at 1101, KY_FULL=1015 and KY_TIMEOUT=1016. These IDs are
package conventions, independent of native include-file encodings. Reports list
all supported constants. No native key-code or terminal-driver equivalence is
implied.

Timeout zero polls queued input immediately. Positive timeout is bounded at one
day and returns partial text/count with portable status 4 when it expires.
Timeout -1 waits for supplied input. An indefinite standalone read with no queued
future input fails explicitly rather than capturing a host keyboard or inventing
a reply. Scheduler waits can remain pending for input while other tasks execute.

Waiting uses cooperative delay and ordinary budget/handler/control checkpoints.
A standalone sleeper completion advances the keyboard's logical clock; scheduler
requests share a captured virtual clock. Standalone requests from unrelated root
clock domains cannot overlap. Time outside active requests does not advance this
keyboard clock. Pause retains the pending edit; stop/error releases the request.
Already consumed events stay consumed on cancellation or failure.

## PUSH and POP

PUSH_KEY_RD('TPKB',mask,pop_id,status) snapshots existing reads on the root's
current pane whose accept/termination classes intersect mask. Those reads are
suspended. A null snapshot still returns a valid token. Later reads are not
implicitly suspended and can receive input. POP_KEY_RD('TPKB',pop_id,status)
releases only that token; nested tokens may be popped by ID. Tokens belong to
the pane/root task that pushed them, including calls through linked routines.

Suspension does not stop timeout time. Multiple tokens must all release a reader
before it is eligible again. Frames remain until POP even if the captured reader
has completed. POP/close cleanup can run after history sequence exhaustion.

## Alphanumeric and dictionary controls

DISCTRL_ALPH(window,row,col,string,dict_name,element,key,status) edits an existing
STRING in a defined window. The pane must have SPI_TPUSER or SPI_TPUSER2 selected
through FORCE_SPMENU; otherwise status is 9093. COMM permits printable text.
PROG permits identifier characters and normalizes a submitted valid identifier
to uppercase. Invalid submission preserves the original variable and records
failure; PREV/function/new-menu termination can return an unsubmitted value.
A custom dictionary element supplies the allowed character set from up to five
plain text rows, with no trailing new_line. Soft-key rendering/word cycling is
not modeled; direct injected characters drive the edit.

DISCTRL_SBMN(dictionary,first_element,default_item,key,status) reads up to 35
consecutive dictionary options ending in an empty element. Options are at most
16 characters, or 40 when there are four or fewer. DISCTRL_PLMN additionally
takes a function-key number 1..5 before default_item and supports up to nine
12-character options. Options may not contain newlines.

UP/DOWN move one item. LEFT/RIGHT move one pull-up item or seven subwindow items,
clamped to the list. ENTER/SELECT, PREV/NEXT, NEW_MENU and F1..F10 terminate and
return the current one-based selection and key. Menu options and results appear
in JSON-safe request snapshots/history; native menu widgets are not opened.
Dictionary and [pendant services](pendant-display.md) remain explicit where used.

## Limits, persistence and CLI

The model permits 4096 queued events, 4096 processed keys per call, 64 active
requests, 64 suspension frames and 256 open handles. Terminal history defaults to
500 rows and supports a maximum of 4096. Event/request/history IDs are finite.
Terminal rows retain monotonic completion order and request IDs, including reads
that complete after later PUSH/POP operations. Invalid configuration is rejected.

Portable statuses are 0 success, 1 invalid arguments/layout/menu, 2 busy or clock
domain conflict, 3 missing/foreign suspension token, 4 timeout, 5 capacity and
6 canceled READ_KB.
Missing required services, unbounded standalone input gaps, exhausted new-request
IDs and normal source execution errors raise runtime errors. Typed output,
active-counter, POSITION/CONFIG and overlap guards apply before consuming input.

Context save requires closed keyboard FILEs, no pending requests and no unpopped
frames. Host close_all() closes idle handles and discards leftover frames after
requests finish or stop; it rejects cleanup while requests are active. Context
retains unconsumed events, IDs, logical time and bounded terminal history. File
history, active editors, clock links and suspension ownership are not restored.
Rerunning source without replenishing input can time out; it is a fresh read.

```sh
python -m karel2py examples/keyboard_edit.kl -o keyboard_edit.py
python keyboard_edit.py --context examples/keyboard_edit.services.initial.json --state-out keyboard-state.json
python -m karel2py examples/keyboard_menus.kl -o keyboard_menus.py
python keyboard_menus.py --context examples/keyboard_menus.services.initial.json
python -m karel2py.project examples/keyboard_project --entry MAIN --context examples/keyboard_project/services.initial.json
```

Reports expose keyboard_policy and a [semantics ledger](semantics/keyboard_semantics.json).
Native keyboard capture, soft-key widgets, generic keyboard FILE READ, native widgets,
controller acceptance and strict equivalence remain future work. The
[form service](forms.md) now models FTX fields, help/choices and tree navigation.
REFRESH, PAGE_UP and PAGE_DOWN are additional injected portable events. The separate
[list/table service](table-controls.md) uses the same injected keyboard events
for resident navigation and array-backed typed editing.

[READ_KB cancellation](read-kb-cancellation.md) now accepts explicit CANCEL FILE
requests, returning portable status 6 while preserving text/count/key outputs.
Blocking reads visit per-key checkpoints; zero-time polls remain atomic. Checked
FILE/binding identities and owned cleanup preserve independent readers and frames.
