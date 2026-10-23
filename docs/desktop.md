# Desktop workbench

Launch with `python -m karel2py.gui` or the installed `karel2py-gui` command.
The latter is a windowed launcher on Windows. An optional source filename opens
that file at startup. `python -m karel2py.gui --version` prints the fixed UTC
build timestamp without creating a window. The title, header and About dialog
display the same version as the CLI and package.

The GUI requires Python 3.11+ with Tkinter and a graphical display. It adds no
third-party runtime packages. Use the existing CLI on machines without a desktop.

The supplied icon set is bundled as original transparent PNGs at 16, 20, 24,
32, 48, 64, 128 and 256 pixels. The header uses the 48-pixel image; the window
manager chooses an appropriate supplied size for the application icon on supported
platforms. Windows launches set a dedicated application identity for taskbar
grouping. Resource loading uses installed package paths and does not depend on
the working directory or the original ZIP file.

## Translate a file

1. Choose **Open KAREL** or paste source into the left editor.
2. Choose **Validate** to check supported syntax/types, or **Translate to Python**
   to generate the Python preview. Neither action executes the source program.
3. Review the **Python**, **Diagnostics**, and **Report** tabs. Double-click a
   diagnostic to jump to its line and column. Project diagnostics can open their
   source file after checking for unsaved edits.
4. Use **Save Python**, **Copy Python**, or **Save report** to export results.

Source/options changes clear earlier results and disable their exports until a
new operation completes. The worker runs separately from the GUI event loop;
only one operation runs at a time. Editing/options are disabled while it runs.
Closing during a job asks for confirmation and does not publish its results.

## Edit and navigate

The KAREL editor has Undo/Redo, Cut/Copy/Paste and Select All commands. Source,
Python and report views show line numbers; KAREL and Python also show syntax
colors. Coloring is a bounded visual hint for the visible excerpt and can accept
unfinished source. Validate or Translate determines language acceptance.

Choose **Edit > Find / Replace** to search literal text. Select KAREL, Python or
Report, optionally enable **Match case**, then choose Next or Previous. Search
wraps at the end or beginning. Replacements apply to KAREL only. Replace All is
one Undo operation; replacements exceeding the 4 MiB UTF-8 limit leave the editor
unchanged. Changing source invalidates previous translation results.

After translating, place the cursor on a KAREL statement and choose **Show
Python →**. The matching generated lines are highlighted. In the Python preview,
choose **← Show KAREL**, or Ctrl+click a line, to return to its source location.
Navigation uses exact compiler source-map entries. Declarations and generated
scaffolding without entries report that no location is mapped. Navigation is
available for a single translated source, and does not modify the source.

| Shortcut | Action |
| --- | --- |
| Ctrl+O / Ctrl+N | Open / New |
| Ctrl+S | Save Source As |
| F5 / Ctrl+Enter | Validate / Translate |
| Ctrl+F | Show Find/Replace |
| F3 / Shift+F3 | Next / Previous match |
| Escape | Close Find/Replace |
| Ctrl+G | Go to KAREL line |
| Ctrl++ / Ctrl+- | Increase / decrease code font size |
| Alt+Right / Alt+Left | Show mapped Python / KAREL |

## Options and linked projects

Pythonic mode is the default. **Enable pause / resume** requests cooperative
code generation, including for source without explicit task-control statements.
This option does not execute, pause or resume a task inside the GUI.

**ARRAY sizes** supplies otherwise unknown global dimensions, using the CLI's
literal shape grammar. Separate entries with semicolons, for example
`DATA=3,4; FLAGS=8`. Duplicate names, expressions and unbounded sizes are rejected.
Strict mode remains a future milestone.

**Check project** selects a directory of regular top-level `.kl` files and checks
translation, program construction and typed source linkage. The report contains
per-program translation reports. It does not generate a single merged Python
module or run any program body. Projects needing explicit construction/runtime
context can use the [project API and CLI](portable-projects.md).

## Source and output handling

Opening/translation leaves the source file unchanged. Source files and editor
text are bounded to 4 MiB. Source input accepts UTF-8, including a BOM, and the
editor presents normalized LF line breaks. **Save source as** is an explicit
write: it preserves a loaded BOM and homogeneous LF/CRLF/CR style. Edited files
with mixed newline styles are saved with LF; an unchanged source is not rewritten.

Unsaved source edits prompt before New, Open or Close. Cancelling a save/discard
dialog preserves the current buffer. Saving over the loaded source detects a
changed/deleted on-disk file and asks the user to reopen or choose another path.

Output dialogs ask before replacement. Existing outputs are replaced after a
complete temporary write beside the target; a failed replacement retains the
old output. Generated Python and report exports reject the loaded source,
project source paths, and their resolved/hard-link aliases. Symbolic-link output
targets are rejected. There is no concurrent filesystem transaction guarantee.

The report's `source_text_sha256` hashes the actual UTF-8 editor text submitted
to translation, including unsaved edits. It is distinct from an original file's
bytes, BOM and newline representation. Reports may contain local paths and
source details; save them locally rather than adding them to public source.

The GUI constructs no controller connection and offers no source execution
button. Generated modules retain the existing [offline runtime](offline-services.md)
and must be run explicitly with the required context outside the workbench.
A [future runner milestone](roadmap.md#python-runner-and-parameter-editor)
will add a parameter tab or popup and execution results saved with the inputs
in one JSON file. It is not implemented in the current workbench.

## Development checks

`tests/test_workbench.py` checks document, compiler, project and export behavior
without a display. `tests/test_gui.py` exercises real Tk widgets, worker completion,
invalidation, cancellation, navigation and source protection. `tests/test_editor.py`
checks literal replacement, source maps and native editor behavior, including
Unicode search ranges, Undo/Redo, scrolling and keyboard shortcuts. Native checks
require explicit `KAREL2PY_GUI_TESTS=1` and skip when Tk or a graphical display
is unavailable. Routine conversion tests open no windows. Both GitHub Actions
workflows require a manual **Run workflow** action; pushes and pull requests
start no tests. **Tests (manual)** runs CLI checks, and **GUI checks (manual)**
runs native checks with a virtual Linux display and a Windows desktop. These
checks do not imply controller acceptance.
