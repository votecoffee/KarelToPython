# Directory-preserving COPY and RENAME destinations

Pythonic COPY_FILE and RENAME_FILE accept one whole-directory ** destination
placeholder. It inserts the actual source directories relative to the captured
literal scan root, while the existing filename template chooses each basename.
This is an authored offline extension; native wildcard/compiler/controller
equivalence and strict mode are not established.

```karel
COPY_FILE('src/**/*.KL','dst/**/*.PY',FALSE,FALSE,status)
RENAME_FILE('src/**/*.KL','done/**/saved_*.DAT',FALSE,status)
```

The first call copies src/root.KL to dst/root.PY, src/cell/part.KL to
dst/cell/part.PY and src/cell/deep/part.KL to dst/cell/deep/part.PY. Equal basenames
in different directories remain distinct. A literal destination such as
dst/*.PY keeps its existing flattening and collision behavior.

## Root and expansion rules

The source's literal prefix before the first directory matcher fixes its scan
root. An exact source or a source with only a final-name matcher uses its literal
parent. For src/*/part.KL the relative directories include the matched component;
for src/**/deep/*.KL they also include the literal deep suffix. For
src/cell/*.KL the root is src/cell, so the inserted directory sequence is empty.

Only one complete destination directory component can be **. It can insert zero,
one or several components. Literal components before and after it retain their
meaning: dst/**/saved/*.PY inserts the source directories before saved. No wildcard
is interpreted as a search for a destination directory.

Final-name standalone * keeps the full source basename. [Repeated adjacent or
separated stars](repeated-destinations.md) independently reuse the complete source stem
or optional extension. [Extensionless and leading-dot files](filename-substitutions.md)
now use the same rules across COPY/RENAME routes, including stem-only templates. A final filename ** does not
become a recursive destination placeholder.

[Ordinary directory component stars](directory-components.md) substitute full
source-relative names with optional literal tags, alongside one **. Directory
question marks, multiple whole destination ** components,
bracket classes, empty/dot components, traversal, absolute host paths, reserved
names and unsafe device syntax remain rejected. Template and expanded names stay
within the existing 254-character ASCII bound.

## Backends, parents and checks

Use an explicitly supplied MemoryFiles, DeviceFiles or rooted DirectoryFiles
bank. Device names remain literal, and unqualified roots do not discover other
namespaces. The literal destination prefix fixes the target preflight root.
All expanded DirectoryFiles parents must already exist, using the backend's
literal case rules. No directory is created, renamed or removed by this feature.

Recursive target preflight counts directories and files and rejects encountered
links/junctions. Source and target scans keep their 32,767-entry bound; scanning,
selection and ordinary batch work charge the existing execution budget. COPY
keeps the 64 MiB snapshot limit and existing per-file bounds.

All expanded destinations participate in case/physical aliases, duplicate
targets, source-target overlap, busy-handle checks and whole-batch collision
decisions before publication. COPY keeps its overwrite flag; RENAME never
overwrites. Complete source/target rescans and byte/configuration checks reject
preflight changes without deleting independently added data. Argument effects
completed before a later failure remain visible; failed preflight leaves status
and bytes under their existing interface rules.

Memory/device publication uses prepared dictionaries. Renames retain their
original byte objects; DeviceFiles checks complete final live bytes and retained
source/overwrite garbage before publishing. Rooted files still publish in sorted
per-file order: a late host error or external race may leave earlier files
changed. This is not a cross-file filesystem transaction or host-isolation lock.

## Pipes, other calls and saved data

Plain PIP sources remain flat. Copying or exporting them into an ordinary
destination with ** inserts zero directory components, retaining the existing
configuration, capacity, ownership and byte-identity rules. PIP directory sources
and targets, socket/DAQ routing and implicit pipe configuration remain excluded.

MOVE_FILE keeps its existing explicit RD/FR peer-path contract, and FILE_LIST keeps
its existing selection/listing rules. DELETE_FILE is unchanged. Both NOWAIT
values retain synchronous finite execution for COPY/RENAME batches.

Context JSON stores resulting bytes, closed pipe configuration and logical device
accounting. Templates, scans, operation plans and open handles are not restored.
Reports expose directory_destination_policy; see the
[semantics ledger](semantics/directory_destination_semantics.json) and
[regressions](../tests/test_directory_templates.py).

Authored examples cover [copy](../examples/directory_template_copy.kl),
[rename](../examples/directory_template_rename.kl),
[virtual copy](../examples/directory_template_devices_copy.kl),
[virtual rename](../examples/directory_template_devices_rename.kl),
[linked copy](../examples/directory_template_linked/main.kl) and
[linked PIP export](../examples/directory_template_pipe_export/main.kl).
