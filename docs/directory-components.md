# Directory component destination substitutions

Pythonic COPY_FILE and RENAME_FILE support stars inside ordinary destination
directory components. Each component containing stars consumes one complete
source-relative directory name. [Repeated adjacent or separated stars](repeated-destinations.md)
reuse that same name, with optional literal tags between them. Filename stem and extension
substitutions remain independent.

```karel
COPY_FILE('src/*/*/*.KL','dst/pre_*/post_*/*.PY',FALSE,FALSE,status)
RENAME_FILE('src/*/**/*.KL','done/first_*/**/last_*/saved_*.DAT',FALSE,status)
```

The first call maps src/Alpha/One/a.KL to dst/pre_Alpha/post_One/a.PY.
Source directory matchers such as A* or O?e still provide full names Alpha and
One; the destination does not substitute the matched substrings alone. Source
case is retained. Wildcards never search for an existing destination directory.

This is an authored offline extension. Native compiler/controller wildcard
equivalence and strict mode are unclaimed.

## Relative depth and globstar

The existing [source root rule](directory-globs.md) remains: the literal parent
before the first directory matcher fixes the scan root. Source suffix literals
after that matcher remain part of the relative directory sequence. An exact
source, or a source with only a filename matcher, has zero relative directories.

Without **, the number of source-relative directories must equal the number of
destination directory components containing stars for every selected file,
regardless of repetition inside a component. Extra source levels are
not silently dropped. Literal destination components do not consume source levels.
A wholly literal destination retains its existing flattening behavior.

At most one complete destination ** component may accompany ordinary stars. It
expands to all remaining source directories after reserving enough components
for later stars. It may expand to zero levels. With source-relative directories
Alpha/One/deep, destination pre_*/**/last_* becomes pre_Alpha/One/last_deep.
With Alpha/One it becomes pre_Alpha/last_One. Missing required components reject
the complete batch before publication. Both examples require at least two source
directories because they contain two ordinary stars.

Final-name standalone *, stem/extension substitution, literal names and ordinary
COPY/RENAME extension rules remain unchanged. Source directory matching, DELETE,
MOVE_FILE and FILE_LIST retain their separate existing contracts.

## Preflight, backends and publication

The literal destination prefix before its first directory star anchors recursive
preflight. Use explicitly supplied MemoryFiles, DeviceFiles or rooted
DirectoryFiles. Existing expanded rooted parents must already exist; no directory
is created or relocated. Device names stay literal, with existing mapping and
volume rules. Unqualified paths do not discover other banks or devices.

Validate all expanded components and paths before writes. Retain complete
source/destination rescans, physical and case aliases, source overlap, busy
handles, duplicate target detection and per-file metadata/byte checks. COPY
retains its overwrite flag; RENAME never overwrites and keeps retained payload
identity. Source selectors, destination expressions and output selectors retain
their normal one-time evaluation and completed-effects rules.

Ordinary expanded-depth/path failures raise through the existing runtime-error
boundary without writing status or files. Cross-bank PIP renames retain their
existing invalid-target status behavior. No match still returns the existing
no-match status. A file with incompatible depth fails the whole selected batch.

Memory/device publication uses prepared dictionaries. Virtual capacity and
retained-garbage accounting cover the entire expanded batch. Rooted filesystem
publication remains ordered per file, so a late host failure may retain earlier
changes. This adds no cross-file filesystem transaction or host-isolation lock.

Names/templates remain bounded to 254 ASCII characters; source and target scans
retain 32767 entries, COPY retains 64 MiB snapshots, and existing execution,
backend and per-file quotas remain. Both NOWAIT values stay synchronous.

## Exclusions and saved state

Directory question marks, bracket templates, multiple whole ** components,
empty/dot/traversal components, unsafe device
syntax, reserved expanded names and absolute host paths remain rejected. Plain
PIP sources have no relative directories, so they cannot supply ordinary directory
stars. PIP directory targets/sources and implicit pipe allocation remain excluded.

Context JSON stores resulting bytes and logical device accounting, omitting
templates, scans, open handles and pending plans. DONE guards in the authored
examples permit exact saved-context replay. This does not implement the future
Python runner/input editor or native directory semantics.

Reports expose directory_component_destination_policy and update the existing
directory_destination_policy. See [regressions](../tests/test_directory_component_templates.py),
[semantics](semantics/directory_component_semantics.json),
[copy](../examples/directory_component_copy.kl),
[rename](../examples/directory_component_rename.kl),
[mixed globstar](../examples/directory_component_globstar.kl),
[virtual devices](../examples/directory_component_devices.kl),
[linked copy](../examples/directory_component_forwarded/main.kl) and
[linked virtual rename](../examples/directory_component_device_rename/main.kl).
