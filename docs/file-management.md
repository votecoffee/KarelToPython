# Name checks and file movement

Since 0.100.0, Pythonic CHECK_NAME validates simple names and MOVE_FILE transfers
closed files between explicit RD and FR namespaces. They complement the existing
[file backends and operations](offline-services.md#files-and-collections).

## CHECK_NAME

`CHECK_NAME(name,status)` checks a base name without an extension, path or device.
It needs no file backend and does not look up a file or program.

The portable grammar is **1–36 ASCII letters, digits or underscores**. It accepts
either letter case and permits a leading digit. Status 0 means valid; status 2
means invalid syntax/length. Dots, spaces, hyphens, separators, controls and
special names such as `*SYSTEM*` are excluded. Missing/non-ASCII input and an
invalid status reference retain ordinary data-domain/output errors. This grammar
does not establish that a name is valid in the KAREL source-program grammar or
match every native controller name rule.

## MOVE_FILE

`MOVE_FILE(file_spec,status)` switches **RD to FR, or FR to RD**. This follows
the manual's RAM/FROM direction contract. It does not take a target path.

MemoryFiles uses its existing explicitly supplied logical names:

```python
from karel2py import translate, runtime as rt

source = """PROGRAM DEMO
VAR status: INTEGER
BEGIN
  MOVE_FILE('RD:job_*.KL',status)
END DEMO"""
files = rt.MemoryFiles({"RD:job_a.KL": b"alpha\n", "RD:notes.TP": b"keep\n"})
namespace = {"__name__": "move_demo"}
exec(translate(source).python_source, namespace)
Program = namespace["Program"]
assert Program(context=rt.ExecutionContext(files=files)).run()["STATUS"] == 0
assert files.snapshot() == {"FR:job_a.KL": b"alpha\n", "RD:notes.TP": b"keep\n"}
```

DirectoryFiles requires both device mappings inside its selected root:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from karel2py import translate, runtime as rt

with TemporaryDirectory() as folder:
    root = Path(folder)
    (root / "ram").mkdir()
    (root / "flash").mkdir()
    (root / "ram" / "part.KL").write_bytes(b"\x00\xffpayload")
    files = rt.DirectoryFiles(root, devices={"RD": "ram", "FR": "flash"})
    namespace = {"__name__": "directory_move_demo"}
    exec(translate("PROGRAM DEMO VAR s: INTEGER BEGIN MOVE_FILE('RD:*.KL',s) END DEMO").python_source, namespace)
    Program = namespace["Program"]
    assert Program(context=rt.ExecutionContext(files=files)).run()["S"] == 0
    assert not (root / "ram" / "part.KL").exists()
    assert (root / "flash" / "part.KL").read_bytes() == b"\x00\xffpayload"
```

Both backends preserve exact bytes and filename case, including binary content.
MemoryFiles target names use an uppercase peer-device prefix. DirectoryFiles
updates its byte cache from the current source data. Other devices are not
inferred, mounted or queried. An unsupported device, a missing mapping or two
mappings that resolve to the same source/target directory return status 4.

## Patterns and batch preparation

The final filename/extension component supports `*`, including prefixes/suffixes
such as `RD:job_*.K*`. Matching is case-insensitive. A single optional slash or
backslash after the colon is accepted, including the manual's `RD:\*.KL` spelling.
Stored source names are literal names, not patterns.

Literal subdirectories such as `RD:jobs/*.KL` preserve that relative directory
under the peer mapping. The selection does not recurse into deeper directories.
Parents must already exist; the operation creates no directories. Traversal,
empty/dot components, wildcard parent components, `?` and bracket patterns fail
before file changes. Directory paths retain the backend's root/symlink guards.

Preparation selects and sorts at most 32767 matching files. It checks the whole
batch for open source/target handles, destination collisions, duplicate target
names and the per-file size limit before the first move. Case-only collisions
are rejected on every host. MemoryFiles also detects aliases formed by device
case or a device-root separator. A busy candidate takes precedence over an
existing-target collision. Directories are not files and are never moved.

| Status | Portable MOVE_FILE meaning |
| --- | --- |
| 0 | All selected files moved |
| 1 | No matching source, or a source disappeared before its move |
| 2 | Existing target or duplicate target name |
| 3 | Open source/target through the selected backend |
| 4 | Unsupported/unmapped device pair or identical mapped roots |

Malformed patterns/paths, oversized sources and OS failures raise runtime errors.
Preflight rejection leaves all files unchanged. Status results write status only;
exceptions preserve its previous value. Inputs and status selectors run once,
left-to-right, before selection. Earlier selector/source effects remain visible.

## Execution and persistence

Moves run synchronously in sorted source-name order using the existing backend
rename convention. Preparation and each move consume the normal execution step
budget. A late OS error, changed source/target or budget failure can occur after
earlier files moved. Those completed moves remain; the runtime does not retry or
roll back a partially completed batch. This is not a concurrent-filesystem
transaction or a native flash/mount/erase-cycle model.

Moved byte contents survive context save/load using existing file snapshots.
Directory roots/mappings are supplied again by the host; saved context file data
loads as MemoryFiles. FILE handle/cursor state is not a task checkpoint.
`file_management_policy` records these choices; ordinary service records contain
operation, line and outcome without file names or content values.

See the authored [wildcard example](../examples/file_move.kl),
[collision/busy example](../examples/file_move_guards.kl) and
[semantics ledger](semantics/file_management_semantics.json).
Native status/name rules and controller execution remain unvalidated; strict mode
is a future milestone.

MOVE_FILE also accepts [single-character question matching](question-file-wildcards.md)
in the final source basename. Directory wildcard/traversal guards, explicit RD/FR
mapping, complete preflight and ordinary publication outcomes remain in force.
