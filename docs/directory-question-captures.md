# Directory destination question captures

Pythonic COPY_FILE and RENAME_FILE reuse fixed-width source-directory question
matches in destination components. This is an authored offline extension without
native compiler/controller wildcard equivalence or a strict-mode claim.

```karel
COPY_FILE('src/Cell??/*.KL','dst/line_??/*.py',FALSE,FALSE,status)
RENAME_FILE('src/A?/**/B?/*.KL','dst/first_?/**/last_?/*.py',FALSE,status)
```

The first maps `src/CellA1/a.KL` to `dst/line_A1/a.py`. Captures retain source case.
The second maps `src/A1/mid/B2/a.KL` to `dst/first_1/mid/last_2/a.py`; its globstar
may insert zero levels for `src/A1/B2/a.KL`.

## Component and alignment rules

Use the existing captured literal source root. Every ordinary destination
directory containing stars or questions consumes one source-relative directory
name. Literal destination directories consume none. Stars repeat the entire name,
including adjacent stars; questions consume only the matched characters, in order.
For example, `CellA1` matched by `Cell??` expands `**_??` to `CellA1CellA1_A1`.
Dots do not split a directory component into filename parts.

Each questioned destination component requires the same number of source question
marks in its corresponding fixed-width source component. That source component
must contain no stars. Other source components may contain stars or globstars.
Questions and repeated stars within one target still consume only one directory.
One whole-directory destination `**` retains its existing remaining-depth rule,
reserving one level for each later component containing stars or questions.

Every complete source-globstar alignment must supply the same fixed-width capture
tuple at each questioned directory. A source star or globstar that could consume
that directory makes its capture unavailable. For example, selector
`src/**/??/**/*.KL` can assign `src/Z1/Z2/a.KL` in multiple ways, so a destination
question on `Z1` rejects. No greedy alignment or guessed character is selected.
Leading, middle and trailing source globstars work when the queried captures are
unambiguous. Matching is case-insensitive while substitutions preserve spelling.

Filename questions keep their separate final-filename capture list and count
rules. Directory questions cannot consume filename captures or vice versa.
Captured characters must satisfy the portable name rules. No substitution
searches for existing target directories, and inserted characters are not reparsed.

## Complete-batch checks and bounds

Missing, count-mismatched or ambiguous captures return status 2 before any copy or
rename is published. No matches still use status 1. Existing ordinary invalid
depth/path failures raise; guarded cross-bank renames retain their status rules.
Capture source/target expressions and the status selector once as usual.

Alignment uses bounded forward/backward grids rather than enumerating paths.
Before allocating the grids, charge three times their cell count against the
execution budget, per selected file. Each grid has one row/column beyond the
source-pattern/source-name directory counts. Input and expanded paths stay at
most 254 ASCII characters. Existing 32767-entry scans, 64 MiB COPY snapshots,
backend quotas and step limits remain. Budget failures propagate without writing
status or publishing files.

The first target star/question fixes the literal preflight root. Retain complete
source/destination rescans, case/physical aliases, collisions, busy handles and
overwrite checks. Every rooted expanded parent must already exist within the
supplied DirectoryFiles root. No directory is created. MemoryFiles and DeviceFiles
publish prepared state; rename retains original bytes and existing garbage
accounting. Rooted publication remains per file and can retain earlier changes
on a late host failure. There is no cross-file host transaction or isolation lock.

Plain PIP sources remain flat and cannot supply directory levels. Destination
brackets, multiple whole-directory `**` placeholders, PIP directories, implicit
backend discovery and socket/DAQ batches remain excluded. MOVE_FILE, DELETE_FILE
and FILE_LIST keep their existing contracts. Both NOWAIT choices stay synchronous.

Saved context retains resulting bytes and logical accounting, with no templates,
match grids, captures, active scans, pending plans or live handles. Reports expose
`directory_question_capture_policy`. See the [runnable example](../examples/directory_question_captures.kl),
[regressions](../tests/test_directory_question_captures.py) and
[semantic ledger](semantics/directory_question_semantics.json).
