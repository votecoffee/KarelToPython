# Named paths for dictionaries, forms and tables

Pythonic dictionary formatting and headless form/table controls share ordinary
static variable lookup. Adjacent numeric bracket groups normalize before lookup:
`GRID[2][1]` and `GRID[2,1]` select the same scalar. Named ARRAY component
boundaries, record fields, PATH node fields and checked joint axes keep their
existing types. No expression evaluation or routine-local discovery is added.

Blank owners use the executing source module, including supplied linked code.
`[PROGRAM]` selects an explicit attached/store owner. `[*SYSTEM*].$PATH` and its
existing undotted spelling select only explicitly supplied system bindings.
No robot or host attribute is discovered.

## Rows and consumer types

A final incomplete flat ARRAY selection captures an ordinary data row or plane
through the existing live prefix mechanism. For example, `CHOICES[2]` selects
a row of a two-dimensional STRING ARRAY; `CHOICES[2][1]` selects a row of a
three-dimensional ARRAY. Consumer requirements still apply:

| Consumer | Accepted selected data |
| --- | --- |
| READ_DICT_V / WRITE_DICT_V format argument | A fully selected scalar matching the format; ARRAY/row values remain rejected. |
| Ordinary form field | A scalar matching its declared conversion and writable/protection requirements. |
| Form variable choice metadata | A one-dimensional STRING row; skip entry one, stop at the first missing label, at most 35 choices. |
| Form function-key metadata | A one-dimensional STRING row with at most ten labels. |
| INIT_TBL / DISCTRL_TBL column path | A one-dimensional ordinary row matching the column kind and containing enough cells. |

A selected plane with two remaining dimensions cannot supply a one-dimensional
consumer. Resource rows and nonfinal vectorized field selection remain excluded.
The [dictionary example](../examples/dictionary_index_paths.kl) formats chained
INTEGER and joint-axis paths without a desktop window.

## Capture, guards and lifetime

Use existing complete containing-data validation before capturing original
cells. Unknown or uninitialized scalar leaves retain their normal rules; invalid
known data elsewhere in the containing ARRAY rejects capture. This differs from
the selected-only DAQ/PC data preparation policies. Generic transfers are unchanged.

Form choices/function labels refresh from captured original cells. Table reads
and commits target those cells as well. Replacing a root or its backing list does
not redirect an active capture, and no routine copyback is performed. Resizing
the retained list raises before subsequent row-window or table-cell access.
Existing session cleanup releases attachments after failure or interruption.
Previously completed edits remain ordinary state; the whole session is not an
all-or-nothing transaction.

Actual backing cells participate in overlap checks, including choice metadata,
service outputs and table change/inactivity arrays. Existing readonly POSITION,
typed ports, bounds and active FOR restrictions remain. Numeric and STRING
editing retain their current conversion, case and capacity policies.

Close active controls before saving. Context JSON retains ordinary source roots
and inactive services, without registered row aliases, live windows, suspended
controls or closures. Completed runs can use ordinary DONE guards for replay.

Reports expose `display_named_path_policy`; the
[semantic ledger](semantics/display_named_path_semantics.json) and
[authored regressions](../tests/test_display_named_rows.py) record the scope.
No native controller, physical keyboard, desktop UI, widget or strict-mode
equivalence is inferred by these offline checks.
