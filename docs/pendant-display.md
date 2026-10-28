# Offline pendant display

Ten pendant built-ins have an explicit Pythonic model through PendantDisplay.
It records link/menu requests, selects configured language labels and maintains
headless character windows. Host code can inspect a composed screen as text.
No browser, desktop window, network request or controller display is opened.

```json
{"pendant":{"rows":24,"cols":80,"languages":["ENGLISH","SPANISH"],"default_language":"ENGLISH"}}
```

Supply that JSON through a generated program's --context option, or construct
`rt.ExecutionContext(pendant=rt.PendantDisplay(...))` in host Python.
Calls require the service explicitly; a missing service raises a source-located
runtime error. Standard source argument, output, overlap and active-counter
checks apply before the backend receives a request.

## Calls and constants

| Call | Supported behavior |
| --- | --- |
| FORCE_LINK(pane, location) | Store the pane's latest opaque printable location. |
| FORCE_SPMENU(pane, menu, screen) | Store a positive menu/screen request. |
| SET_LANG(language, status) | Select a label from the configured language list. |
| DEF_SCREEN(name, device, status) | Define a unique logical TP screen. |
| DEF_WINDOW(name, rows, cols, options, status) | Allocate a blank character grid. |
| ACT_SCREEN(name, previous, status) | Activate an existing screen and return its previous name. |
| ATT_WINDOW_S(window, screen, row, col, status) | Attach a window at a one-based screen location. |
| ATT_WINDOW_D(window, device, row, col, screen, status) | Attach to the device's active screen and return its name. |
| DET_WINDOW(window, screen, status) | Remove one attachment without deleting the window. |
| SET_CURSOR(file, row, col, status) | Move an open window FILE's one-based cursor. |

Names use 1..4 ASCII identifier characters and are case insensitive. TP is the
only logical screen device. Screens start with SYS active. Each attachment must
fit entirely within the configured display; duplicate attachments are rejected.
A window may belong to multiple screens. Later attachments overlay earlier
ones; detaching reveals the retained underlying surfaces.

TP_PANEL, TP2_PANEL and TP3_PANEL select panes 1, 2 and 3; integer panes 4..9
are also accepted for link/menu requests. Locations contain 1..254 printable
ASCII characters. Requests such as current=... or refresh=... remain opaque
text: they are recorded without interpretation, fetching or refresh scheduling.

The supplied SPI_* menu names have portable IDs starting at 1001; SCR_* screen
names start at 2001. Positive INTEGER IDs through 32767 are accepted. These IDs
are package conventions rather than native menu encodings. ACT_SCREEN requires
the primary pane's menu to be SPI_TPUSER or SPI_TPUSER2 before activation.

DP_DEFAULT, DP_ENGLISH, DP_JAPANESE, DP_FRENCH, DP_GERMAN and DP_SPANISH are
STRING-valued predefined constants. DP_DEFAULT selects default_language. A
configured language is a label; it supplies no translation, dictionary or font.
The default language list contains ENGLISH only. Additional labels must be
configured explicitly; at most 32 distinct labels are allowed.

## Window FILE output

```karel
DEF_SCREEN('MAIN','TP',status)
DEF_WINDOW('INFO',3,12,WD_COM_CURSR+WD_SCROLLED,status)
ATT_WINDOW_S('INFO','MAIN',1,1,status)
FORCE_SPMENU(TP_PANEL,SPI_TPUSER,1)
ACT_SCREEN('MAIN',previous,status)
OPEN FILE output('RW','WD:INFO')
SET_CURSOR(output,1,1,status)
WRITE output('KAREL -> PY',CR)
WRITE output('value: 42')
CLOSE FILE output
```

WD:name resolves only through the pendant service, independently of ordinary
memory/directory files. Modes W/WO, RW/UD and A/AP permit text output. Opening
never clears a window; explicit form feed clears it. READ, keyboard suffixes,
read-only mode, binary/XML transfer, SET_FILE_POS and byte availability queries
are rejected. GET_FILE_POS returns the handle's logical bytes written;
IO_STATUS and CLR_IO_STAT retain their ordinary FILE interfaces.

WD_COM_CURSR=1 shares the window cursor across open FILE handles. Without that
flag, each new handle starts at row 1, column 1 and retains its own cursor.
WD_SCROLLED=2 enables vertical scrolling; add the flags for both policies.
The window's saved cursor is its most recently used cursor. After reload it
continues shared-cursor output; fresh independent handles still start at 1,1.

Printable ASCII writes replace grid cells. Filling the final column leaves a
pending wrap; the next printable character advances the line. LF advances to
column 1 of the next line. At the bottom, a scrolled window shifts upward and
adds a blank row; a non-scrolled window clears its bottom row. CR returns to
column 1, FF clears the grid and resets to 1,1, BS moves left without erasing,
and TAB writes spaces to the next eight-column stop. Unsupported controls
reject the complete write before mutation. Source WRITE CR produces LF through
the runtime's ordinary text formatter. No native terminal/glyph policy is implied.

Host inspection is window-free:

```python
lines = context.pendant.render()          # current active screen
other = context.pendant.render('MAIN')    # explicit logical screen
snapshot = context.pendant.snapshot()     # detached state, including open names
```

Linked routines may borrow FILE references; scheduled tasks may use separate
handles on the same shared-cursor window. Accepted operations retain the opening
root task's name for FILE output and the calling root task for ordinary calls.
No native task-end or abort-time screen restoration is synthesized.

## Limits, results and persistence

Display and window dimensions are 1..256 per axis. At most 64 screens and 64
windows are supported, with a default total window budget of 65536 cells
(configurable through max_cells up to 262144). There may be 256 live window
handles. Each backend write is limited to 65536 ASCII bytes; ordinary source
WRITE formatting bounds also apply.

| Status | Meaning |
| --- | --- |
| 0 | Success. |
| 1 | Invalid name, device, dimensions, cursor or options. |
| 2 | Duplicate definition or attachment. |
| 3 | Missing screen/window. |
| 4 | Missing attachment or non-window FILE cursor target. |
| 5 | Capacity exhausted or screen-name output too small. |
| 9093 | ACT_SCREEN requires the primary USER/USER2 menu. |
| 33003 | Language label is not configured. |

Only 9093 and 33003 preserve the cited documented cases; the other statuses
are portable choices. Rejected operations preserve existing surface/request
state. Screen-name outputs must fit completely before activation/attachment.
FORCE_LINK/FORCE_SPMENU have no status output and reject invalid requests with
a runtime error.

The accepted-request ring defaults to 500 rows, configurable through limit up
to 4096. Rows contain a monotonic sequence, root program, operation and bounded
data. FILE writes record byte counts; window text lives in the grid. Finite
sequence exhaustion blocks new operations before mutation but still permits
FILE cleanup. Failed status-returning requests add no accepted history row.

Context JSON retains windows, lines, common cursors, screens, attachments,
active screen, link/menu requests, language labels and bounded history. Every
window FILE must be closed before saving; live handles/per-handle positions
are not serialized or reopened. Reload restores logical data without executing
requests. Rerunning source is a fresh invocation and may encounter duplicate
resource statuses. Always check statuses or deliberately reuse existing names.

```sh
python -m karel2py examples/window_display.kl -o window_display.py
python window_display.py --context examples/window_display.services.initial.json --state-out window-state.json
python -m karel2py.project examples/pendant_project --entry MAIN --context examples/pendant_project/services.initial.json
```

The translation report's pendant_policy and the
[semantics ledger](semantics/pendant_display_semantics.json) record this contract.
[Text dictionaries](text-dictionaries.md) now provide a separate explicit service
for dictionary reads and logical window writes. Twelve [dynamic display calls](dynamic-displays.md)
now add read-only static-variable and port watches with deterministic polling.
[Keyboard input](keyboard-input.md) now supplies explicit queued events, read
suspension and combined WD:name/TPKB endpoints. [List/table controls](table-controls.md)
add resident paging and array-backed editors. [FTX forms](forms.md) now add
logical typed fields, help/choices and tree groups. Native keyboard capture,
compressed native dictionaries, graphic styles, native language packs and
controller acceptance remain future work. Strict mode remains a later milestone.
