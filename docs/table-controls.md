# Lists and tables

Pythonic translation supports `DISCTRL_LIST`, `INIT_TBL`, `ACT_TBL` and
`DISCTRL_TBL` through an explicitly configured `TableControls` service. These
are offline controls over typed program data, injected keys and logical windows.
They open no desktop windows and acquire no physical keyboard input.

```json
{
  "table_controls": {"window": "TABL"},
  "pendant": {"rows": 3, "cols": 16},
  "dictionaries": {"sources": {"headers": "$1 \"Counts\""}},
  "keyboard": {"events": [{"key": "7"}, {"key": "ENTER"}, {"key": "F2"}]}
}
```

Define the configured window with `DEF_WINDOW` and load the header dictionary
with `ADD_DICT`. Table headers support printable text, newlines, nested elements
and ignored style intent from the [text dictionary service](text-dictionaries.md).
Native function-key/help attributes and the form compiler grammar are unsupported.
The header must fit the window and leave at least one data row.

## Column data and backing arrays

`COL_DESC_T` is a predefined nominal record with these portable fields:

| Fields | Meaning |
| --- | --- |
| `ITEM_TYPE`, `START_COL`, `FIELD_WIDTH` | Required item code, one-based column and positive field width |
| `ENUM_DICT`, `ENUM_ELE` | Dictionary name and first label element; element defaults to 1 |
| `FORMAT_SPEC` | One bounded printf conversion with literal prefix/suffix; defaults by type |
| `MIN_INTEGER`, `MAX_INTEGER`, `MIN_REAL`, `MAX_REAL` | Optional numeric entry bounds |
| `CLEAR_FLAG`, `LOWER_CASE` | 0/1 string edit policies, default 0: retain existing text and uppercase committed input |

`ENUM_DICT` has capacity 4 and `FORMAT_SPEC` capacity 80. Other fields are INTEGER
except REAL range fields. These fields and `XWORK_T` are portable schemas, with
no native record-size, memory-layout or pointer compatibility claim.

Each `value_array` entry names one static global one-dimensional array. Its
elements supply the table rows. Names can use an attached `[PROGRAM]` prefix,
structure fields and subscripts leading to a named array. Local/computed paths,
protected storage, incorrect element types and short backing arrays are rejected.
Cells are captured once at initialization; subsequent edits update that storage.
Columns can share backing data, but data cannot overlap the call's output/resource
storage. Indirect editor calls are conservatively blocked in active FOR scopes,
including through routine effects.

| Item constant | Backing array | Portable editing |
| --- | --- | --- |
| `TPX_INT_ITEM` | INTEGER | Decimal integer |
| `TPX_REL_ITEM` | REAL | Finite decimal/exponent float |
| `TPX_FKY_ITEM` | INTEGER | One-based numeric index into up to 10 newline-separated labels in one dictionary element |
| `TPX_SUB_ITEM` | INTEGER | One-based numeric index into up to 28 consecutive single-line elements ending with an empty element |
| `TPX_KST_ITEM` | STRING | Editable string |
| `TPX_KSL_ITEM` | STRING | Read-only selectable string |
| `TPX_KBL_ITEM` | BOOLEAN | Toggle; two dictionary labels or default FALSE/TRUE |
| `TPX_BYT_ITEM` | BYTE | Decimal 0..255; optional `%c` display |
| `TPX_SHT_ITEM` | SHORT | Decimal -32768..32766 |
| `TPX_PBL_ITEM` | STRING containing port paths | Supplied BOOLEAN ports, e.g. `DOUT[1]` |
| `TPX_PIN_ITEM` | STRING containing port paths | Supplied INTEGER ports, e.g. `GOUT[1]` |

Port columns require an explicit bank; input ports are selectable and can be
edited only when explicitly simulated. They observe pending portable pulses.
Missing values display `*`; invalid enum/display values display `?`. Integer
formats support d/o/x/X/u, REAL formats f/e/E/g/G, and strings/labels `%s`.
Flags `-`, `+`, space and `0`, bounded width/precision, and `%%` are supported
where applicable. Fields clip/pad to their declared widths; overlap is rejected.

The optional inactivity array contains one flag per column. Unknown or omitted
flags mean active. All columns inactive is an error. Change grids are initialized
FALSE and cells become TRUE on successful commits. Smaller two-dimensional grids
record only available cells; an unused one-element BOOLEAN array is accepted.
Larger grids retain their unused cells. `INIT_TBL` requires a two-dimensional
INTEGER pointer grid large enough for the table; its entries are logical one-based
cell ordinals, never native pointers.

## Keys and session lifetime

`INIT_TBL` prepares a session without painting. `XWORK_T` contains an opaque
portable SESSION identifier. Pass the same record to subsequent `ACT_TBL` calls;
copies, foreign tasks and stale identifiers cannot operate on its session.

`ACT_TBL` accepts a writable INTEGER action or an INTEGER value/constant:

- `KY_DISP_UPDT` draws and optionally attaches the configured window at (1,1).
- `KY_REISSUE` cooperatively reads one injected key and returns its code in a
  writable action argument.
- Other supported key codes act directly without consuming queued input.
- `KY_CANCEL` releases the session, resets its record identifier to zero, and
  removes only the attachment created by that session. Cleanup works after
  display history exhaustion. A `KY_NEW_MENU` event cancels automatically.

Selection uses one-based rows and skips inactive columns. Up/down select rows;
left/right select columns. Printable input begins editing; numeric input replaces
the old value. ENTER opens an existing edit or commits checked input. During an
edit, cursor, home/end and delete keys work, and PREV discards the edit. A string
commit exceeding its destination capacity fails without truncating live data.
Boolean ENTER/input toggles the cell. Selecting a read-only cell returns
`KY_SELECT`. Enum entry uses numeric indices; native soft-key/submenu widgets
are not reproduced. Selected row/column/edit state is visible in `snapshot()`;
highlight glyphs are not rendered.

`DISCTRL_TBL` combines preparation, display and an injected-key loop. SELECT and
NEW_MENU always terminate; outside an edit, the supplied key-class mask also
terminates before acting on that key. Commits stay within the loop. Edits which
fail validation return status 1, preserve the rejected cell's value and release
the internal session. Earlier successful commits remain. Nonterminal iterations
and budgeted key waits cooperate with task scheduling; repainting observes live
data after keys and during waits. There is no independent background display task.

Portable statuses are 0 success, 1 invalid layout/data/entry or capacity, 3 missing
or foreign session, and 5 per-call event-budget exhaustion. Missing services,
unsupplied indefinite standalone input, runtime failures and forbidden aliases
raise runtime errors. Cancel explicit INIT/ACT sessions before saving context or
leaving their source lifecycle; interrupted active ACT calls release the session.
Internal DISCTRL sessions always release on exit. Saving retains the manager's
window, capacity and finite ID sequence plus ordinary pendant/keyboard state;
it rejects active sessions and never serializes references or active edits.

Limits are 64 sessions, 40 columns, 16384 cells per table, 32766 rows, 254 editing
characters and 4096 processed events per DISCTRL call. The window/array limits
can impose smaller bounds. Constants/statuses are portable, not native encodings.

## Resident lists

`DISCTRL_LIST` takes an open window FILE, a `DISP_DAT_T` reference, resident
STRING rows, an action and status. Both ordinary WD and writable combined
WD/TPKB handles work. Its actions are `DC_DISP`, `DC_UP`, `DC_DN`, `DC_LF` and
`DC_RT`. The current viewport is zero-based 0..3; row bounds are one-based and
field bounds zero-based. Only the selected viewport and used field entries need
initialization. MENU_ID and unused viewport/field entries may remain unknown.

The model validates resident SOB/EOB bounds, row/field bounds and LINS_PER_PG;
viewport height determines the painted page. It scrolls within supplied resident
data, updates current item/field/row and moves the FILE cursor to the selected
field. LAST_IT_NUM can describe a larger list, but there is no implicit fetching
or navigation outside the resident array. Painting and cursor requests are
preflighted together. Unsupported fields cannot silently cause a partial paint.

## CLI examples and evidence

```sh
python -m karel2py examples/table_editor.kl -o table_editor.py
python table_editor.py --context examples/table_editor.services.initial.json --state-out table-state.json
python -m karel2py examples/resident_list.kl -o resident_list.py
python resident_list.py --context examples/resident_list.services.initial.json
python -m karel2py.project examples/project_table --entry MAIN --context examples/project_table/services.initial.json
```

The [semantics ledger](semantics/table_control_semantics.json), translation
`table_control_policy` and authored tests describe the contract. `DISCTRL_FORM`,
native key encodings, form/table binary layouts, controller rendering/acceptance
and strict equivalence remain future work.
