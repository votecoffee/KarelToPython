# Offline FTX forms

Pythonic translation supports `DISCTRL_FORM` using an explicit `FormControls`
service, supplied FTX source, typed globals, injected keys and headless windows.
It opens no desktop UI and acquires no physical keyboard input.

```json
{
  "forms": {"window": "FORM", "rows": 5, "cols": 24},
  "pendant": {"rows": 5, "cols": 24},
  "dictionaries": {
    "sources": {
      "settings": ".form unnumber\n$1,settings\n\"Settings\" &new_line \"Values\" &new_line\n\"Count \" \"-%4d(0,50)\" &new_line\n\"- Done\"\n.endform\n"
    }
  },
  "keyboard": {"events": [{"key": "7"}, {"key": "ENTER"}, {"key": "F3"}]}
}
```

Load the source with `ADD_DICT('settings','FORM',DP_DEFAULT,DP_DRAM,status)`.
Select USER2 with `FORCE_SPMENU(TP_PANEL,SPI_TPUSER2,1)` before calling the form.
Sources are explicit text catalog entries, not host paths or compressed files.
An explicitly named `.FTX` source label also works when ADD_DICT uses that label.
Native compression, associated VR generation/loading and Data ID discovery are
not inferred. Ordinary dictionary elements may share the source with forms.

## Source syntax and fields

`.form` and `.endform` must be on their own lines, surrounding one dictionary
element. Supported attributes are `unnumber` and `noclear`. Missing ends,
nested forms, duplicate attributes and unknown directives fail during loading.
Ordinary dictionary inclusion, cursor positions, newlines, printable text and
style intent can occur inside the form. Styles have no glyph effect. Cursor
positions must move forward; rows 1 and 2 are fixed title/label rows, with data
items starting at row 3. Later logical rows scroll through the window body.

Quoted text starting with `-` defines a selectable item; the dash is removed.
Starting with `-%` defines an editable data item. Starting with `%` defines a
display-only data item. Other quoted text is static. One quoted data item has
one conversion, optionally followed by literal suffix text. Use separate quoted
items for multiple fields. `%%` displays a literal percent. A selectable label
ending with `+` continues onto following ordinary text without adding another
selection. Numbered forms reserve the first three body columns, so position
their content accordingly. The portable model exposes selection in snapshots;
it does not render inverse-video highlighting.

Each data item consumes one entry from `value_array`, including display-only
fields. Entries name static scalar globals, fields, array elements or PATH node
fields; an attached `[PROGRAM]` prefix is supported. Port formats take direct
indexed paths such as `DIN[1]` and `GOUT[2]`. Editable references must be ordinary
writable storage. Wrong types, missing paths and overlaps with outputs, inactivity
flags, change flags or choice metadata fail before editing. Calls are conservatively
blocked in active FOR scopes, including through routine effects.

| Conversion | Storage and behavior |
| --- | --- |
| d/o/x/X/u | INTEGER; decimal, octal or hexadecimal entry as appropriate |
| f/e/E/g/G | Finite Python float in REAL storage |
| h / b | SHORT -32768..32766 / BYTE 0..255; use aggregate elements or fields under existing declaration rules |
| B | BOOLEAN; two enum labels, or default FALSE/TRUE |
| P | Supplied BOOLEAN port; two enum labels, or default FALSE/TRUE |
| pu / px | Supplied INTEGER port; decimal/hexadecimal entry |
| S | Supplied BOOLEAN/INTEGER port simulation state; default UNSIM/SIMULATE labels |
| k / s | Bounded STRING; `(clear)` discards old edit text, otherwise input appends |
| pk | Program-name STRING selected from attached/supplied catalog entries |
| n | INTEGER function-key enumeration from one element with at most five lines |
| w | INTEGER choice enumeration from consecutive single-line elements |
| v | INTEGER choice enumeration from a static STRING array described by a dictionary element |
| t | BOOLEAN controlling a nonnested tree group |

Numeric conversions accept optional `(minimum,maximum)` bounds. BOOLEAN/port
formats accept `(element_name_or_number)` with FALSE first and TRUE second.
Function-key enums use one-based values; blank labels disable their function key.
Subwindow enums contain at most 35 choices and end at an empty element or the
native `"\a"` terminator. Variable enums use a two-line descriptor containing a
program and array path: element 1 is skipped, value 1 starts at element 2, and
the first uninitialized entry ends the choices. Variable choices refresh while
the form is active. Display fields use bounded flags, width and precision.

Program-name selectors use the form-specific manual codes: 1 for TP programs,
2 for PC, 6 for TP/PC/VR, and 16 for TP/PC. These differ from `PROG_LIST` codes.
The default is 16. Only explicitly supplied/attached names are offered; typed
program input must match a supplied name. No code is loaded by selection.

Input ports are selectable but read-only until explicitly simulated. Simulation
can be enabled only when a port value has been supplied; unsimulation retains
that value. These operations affect the logical bank and never controller I/O.
Unknown values display `*`; invalid display/enum values display `?`.

## Input, help and trees

Up/down and left/right move through visible active items. HOME/END jump to the
first/last item; PAGE_UP/PAGE_DOWN move by a body page. ENTER on a selectable
label always returns `KY_SELECT`. ENTER on editable data opens an edit; printable
input starts an edit directly. Numeric input replaces the old value, while STRING
input follows its clear/append policy and preserves case. Cursor/delete/home/end
work during editing. ENTER commits; PREV discards an edit before acting as a form
termination key. A successful SELECT commits an active edit and terminates.
NEW_MENU always terminates and discards an uncommitted edit.

Invalid format/range/capacity input leaves the live cell unchanged and permits
correction. The current error appears in the final logical window row and in
`snapshot()`. Successful commits clear the error and set the corresponding data
change flag. Smaller change arrays record only available cells; unused tails are
preserved. Inactivity flags address selectable items, including plain labels;
unknown/missing flags mean active. Display-only fields consume data indices but
do not consume selectable-item indices. `def_item` updates continuously to the
current selectable item; display-only forms use zero.

F4/F5 select TRUE/FALSE for BOOLEAN and simulation fields. F1..F5 select active
function-enum labels. F4 opens a choice overlay for w/v/pk fields; arrow keys and
ENTER select, PREV cancels. These field-specific keys take precedence over form
termination masks. Outside an edit, other key classes in `term_mask` terminate
before normal navigation/editing. SELECT and NEW_MENU always terminate.

`^element` associates up to ten function labels, and `?element` associates up to
48 help lines. A function element may instead contain `"*PROGRAM"` and
`"*ARRAY_PATH"` to use a live STRING array. Blank labels disable those keys.
F5 labeled HELP opens the help overlay; arrows/pages scroll it and PREV or F5
restores the form. Soft-key labels and overlays are logical state, with no native
widget rendering.

An editable `-%t` latches its BOOLEAN initial state; ENTER toggles it and writes
the result. A display-only `%t` monitors the BOOLEAN during repaints. Each tree
controls following body rows until another tree or `.endtree`. Hidden children
cannot be selected. REFRESH (`KY_REFRESH`, the portable Ctrl-W event) resamples
all tree values. A new `%t` ends the preceding group, so its own selector stays
visible even when the preceding group is collapsed. Tree items never nest.

Complete FTX forms can be concatenated through ordinary `+element` dictionary
references. Each included `.form` / `.endform` pair is a sequential fragment;
these markers do not create nested tree items. Field paths, change flags and
selectable item numbers continue across fragments. Dictionary nesting retains
its existing five-level and expanded-token bounds.

A fragment starts outside the preceding tree. Use `.tree` to inherit the open
tree from the preceding text; `.endtree` closes that inheritance. An intervening
fragment without `.tree` ends the previous grouping, and `.tree` with no open
preceding tree is rejected. A new `%t` replaces the current group. For example,
this authored form keeps the amount field inside the editable switch's group:

```text
.form unnumber
$1,editor
&home "Settings" &new_line "Values" &new_line
"-%t Details" &new_line
+2
.endtree
"- Done"
.endform
.form
$2,details
.tree
"Amount " "-%4d(0,10)" &new_line
.endform
```

The corresponding paths are the BOOLEAN switch followed by the INTEGER amount.
A collapsed group skips the included field during selection and editing. An
editable tree latches its initial BOOLEAN across every inherited fragment until
ENTER or REFRESH; a display tree uses the existing logical repaint policy.

The outer form owns `unnumber` and `noclear`; a fragment may omit attributes or
repeat a subset of the outer attributes. Conflicting attributes fail preparation.
Text, newlines and forward cursor controls are concatenated literally. Headers
are not implicitly stripped, merged or rebased, and a fragment cannot backtrack
to replace the outer title. This is a portable composition contract, not a claim
about native compressed-form association records or layout.

## Lifetime, limits and CLI

The configured window is created on the first valid invocation if absent; an
existing window is reused. The default is 12 rows by 40 columns. Two rows remain
fixed while the body scrolls. `noclear` captures the initial window background
and preserves untouched cells during form/overlay repaints. FILE cursors stay
unchanged. Only attachments created by the manager are removed; shared manager
attachments survive until their last session exits. This is a portable single
window layout, not the native TPSC/FULL/FSCR/PRMP/FTNK arrangement.

All exits release internal sessions and keyboard reads, including task stop,
budget failure and exhausted display history. Active forms prevent context save.
Inactive configuration retains window/dimensions, capacity and finite IDs; ordinary
dictionary, pendant and keyboard state persists separately. No active edits,
references or execution links are serialized. Reruns require explicit new keys.

Portable status 0 means completion, 1 invalid preparation/changed live metadata
or capacity, and 5 event-budget exhaustion. Invalid edits remain in the form for
correction. Missing services, missing indefinite standalone input and runtime
alias/execution failures raise errors. Limits are 64 sessions, 256 logical rows,
256 data items, 256 selectable items, 254 editing characters, 35 enum choices,
10 function labels, 48 help lines and 4096 processed key events per call.

```sh
python -m karel2py examples/form_settings.kl -o form_settings.py
python form_settings.py --context examples/form_settings.services.initial.json --state-out form-state.json
python -m karel2py examples/form_navigation.kl -o form_navigation.py
python form_navigation.py --context examples/form_navigation.services.initial.json
python -m karel2py.project examples/form_project --entry MAIN --context examples/form_project/services.initial.json
```

Reports expose `form_policy`; the [semantics ledger](semantics/form_semantics.json)
records manual provenance and authored verification. Native binary compatibility,
key encodings, glyphs, exact timing, controller acceptance and strict mode remain
outside this contract.
