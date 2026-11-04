# Repeated destination substitutions

Pythonic COPY_FILE and RENAME_FILE accept repeated nonadjacent stars in
destination directories, filename stems and extensions. Every star in one part
reuses that same complete source part. This is an authored offline extension;
native/compiler/controller wildcard behavior and strict equivalence are unclaimed.

~~~karel
COPY_FILE('src/*/*.KL','dst/cell_*_backup_*/*_*.saved*_*',FALSE,FALSE,status)
RENAME_FILE('src/*.KL','dst/*_*.*_*',FALSE,status)
~~~

The first call maps `src/Alpha/part.KL` to
`dst/cell_Alpha_backup_Alpha/part_part.savedKL_KL`. The second maps
`src/part.rev1.KL` to `dst/part.rev1_part.rev1.KL_KL`. Source case and binary
payloads are retained. Replacements are performed once, without recursive
interpretation of inserted characters.

## Directory depth and filename parts

A directory component containing stars consumes exactly one directory name
relative to the source's captured literal scan root, regardless of the number
of stars in that component. Literal destination directories consume none.
Source matchers capture complete names rather than the substrings matched by
individual wildcards. Without a whole-directory **, selected relative depth must
match the number of destination components containing stars.

At most one complete ** may insert the remaining source directories. It reserves
one source level per later component containing stars. For example, source
`src/A/B/C/d.KL` with selector `src/*/**/*.KL` and destination
`dst/*_*/**/*_*/*_*.py` produces `dst/A_A/B/C_C/d_d.py`. With `src/A/C/e.KL`,
the same globstar inserts zero levels and produces `dst/A_A/C_C/e_e.py`.

Split the final filename at its last dot. Stem stars repeat the complete source
stem, including earlier dots; extension stars repeat the complete source
extension. A standalone final * still preserves the whole basename. Other
wildcard filename substitutions require nonempty source name/type and nonempty
destination stem/type. Literal target and extensionless exact-rename rules stay
unchanged. A source with only filename matchers has no relative directory levels.

Adjacent stars within an ordinary directory, filename stem or extension remain
rejected. Whole-directory ** retains its distinct role. Question/bracket
destination templates, partial/repeated ** directories, stem-only star templates,
traversal, empty/dot components and absolute host paths remain excluded.

## Backends and preflight

Supply MemoryFiles, DeviceFiles, rooted DirectoryFiles or configured plain
FilePipes explicitly. COPY retains its overwrite flag; existing reserved pipe
names still require overwrite for COPY, even when empty. RENAME retains its
same-bank, cross-volume and guarded cross-bank rules, including empty reserved
pipe targets and no ordinary overwrite. A plain PIP source cannot supply
directory names. No pipe, directory, device mapping or endpoint is discovered
or created implicitly.

Capture source/target expressions and the status selector once through the
existing call rules. Validate every expanded name/depth, collision, case/physical
alias, overlap, busy handle, source/target rescan, payload and quota before
publication. Existing status/runtime-error boundaries remain: invalid basename
templates use status 2; ordinary expanded path/depth failures raise; guarded
cross-bank rename target failures retain their existing status conventions.
Completed source-expression effects remain visible on failure.

Input and expanded paths remain at most 254 ASCII characters. Scans retain the
32767-entry limit, COPY keeps its 64 MiB snapshot bound, and backend/device/pipe
quotas and execution budgets still apply to the complete batch. Repetition does
not add extra source-directory consumption or relax these limits.

Memory/device publication uses prepared state. Rename retains original byte
objects and existing virtual retained-garbage accounting. Rooted publication
remains per file; a late host error may retain earlier completed changes. There
is no cross-file filesystem transaction or host-isolation lock. Both NOWAIT
values remain synchronous. MOVE_FILE and FILE_LIST keep their existing contracts.

## Reports and replay

Reports expose `repeated_destination_policy` and update the existing wildcard
and directory policies. Context JSON retains resulting bytes and logical
accounting, with no templates, scans, live handles or pending plans. The examples
use DONE guards for exact saved-context replay.

See [copy](../examples/repeat_dest_copy.kl),
[rename](../examples/repeat_dest_rename.kl),
[mixed globstar](../examples/repeat_dest_globstar.kl),
[virtual devices](../examples/repeat_dest_devices.kl),
[linked copy](../examples/repeat_dest_linked/main.kl),
[linked pipe export](../examples/repeat_dest_pipes/main.kl),
[regressions](../tests/test_repeated_destinations.py) and the
[semantic ledger](semantics/repeated_destination_semantics.json).
