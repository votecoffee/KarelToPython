# Stored translation dependencies and saved ARRAY schemas

Pythonic TRANSLATE can now read explicitly mapped include FILEs and specialize
global wildcard ARRAYs using supplied schema metadata. These are opt-in
SourceTranslations settings over the existing ordinary FILE backends.

```json
{
  "source_translations": {
    "include_files": {"decl": "shared/decl.inc"},
    "array_context": {"variables": [{"program": "CHILD", "path": "VALUES",
      "type": ["ARRAY", 2, ["INTEGER"]], "value": null}]}
  }
}
```

Supply a source FILE with `PROGRAM CHILD`, `%INCLUDE 'decl'` and a normal body,
plus the explicitly selected `shared/decl.inc` FILE containing
`VAR values:ARRAY[*]OF INTEGER`. Calling `TRANSLATE('child',TRUE,status)` generates
sibling Python/listing products using those inputs. It does not run or attach
the generated child. No native PC output, library discovery or strict equivalence
is supplied.

## Explicit include selection

`include_files` maps virtual include names to exact relative ordinary backend
specifications. Include aliases retain the existing KL/KH/INC extension and
1..36-character basename rules; an omitted extension becomes KL. Targets may
use supplied ordinary device mappings and need not have the alias's extension.
No directory, source-relative search or automatic backend include discovery is
added. Literal `includes` texts and mapped files may coexist with distinct
canonical names. Case-insensitive duplicates across either map reject.

Snapshot every explicit mapped file before compilation, including unused
bindings. Nested include expansion still follows the ordinary compiler's depth,
cycle, byte and diagnostic-location rules. Virtual aliases appear in compiler
diagnostics; history records actual selected backend paths and raw-byte SHA-256
hashes. UTF-8 BOMs are accepted and remain part of those original-byte hashes.

Use exact MemoryFiles, rooted DirectoryFiles or DeviceFiles backends. Existing
case ambiguity, directory confinement, link/junction, busy-handle, virtual device
and file-size rules apply. Mapped dependencies obey source_limit, capped at
4 MiB each. Literal and file include bindings share 256 names and 8 MiB total
input bytes. Explicit file reads and compilation remain synchronous and bounded.

## Schema metadata and runtime-only use

`array_context` uses the [saved ARRAY schema contract](array-context.md). Its
configuration is copied into canonical root ARRAY metadata. Payload values,
non-ARRAY/nonroot bindings, creation policies, services and import graphs are
discarded. Canonical metadata remains within 16 MiB and the existing schema,
dimension, row and allocation limits. Returned configurations are independent.

The compiler checks the source declaration and concrete schema exactly, including
element type, STRING capacity, nominal layouts, joint width and PATH components.
Matching explicit array_shapes may coexist; conflicting shapes or schemas reject.
Schema metadata supplies dimensions only. Child values/services must be loaded
separately when the generated Python is explicitly executed.

Constructing, saving and restoring these settings imports no compiler, lexer,
include loader, GUI or project linker. Disabled/unavailable compilation retains
status 268. A missing optional compiler is detected after reading the primary
source and before reading mapped dependencies. The generated child remains usable
with its ordinary runtime dependencies.

## Publication, status and evidence

Keep the primary and mapped input bytes/resolutions captured for the request.
Before publishing the complete product set, and again before each individual
publication, recheck all captured inputs. The final pass adds no checkpoints or
callbacks. Changed/missing/ambiguous/busy inputs prevent stale code publication;
earlier explicit source or host effects remain. Output paths cannot alias any
input, including hard links and forced overwrites.

The existing listing-first, Python-last publication order remains. A late host
failure or changed dependency after the listing can retain that listing while
preserving old Python. This is not a filesystem lock or multi-file transaction;
external host races remain possible. Primary-source byte stability is now checked
for ordinary requests without mapped includes as well.

Missing/unreadable/oversized/non-UTF-8 mapped FILEs and changed inputs return
35084. Compiler source/include/schema rejection returns -1 and may publish a
diagnostic listing. Accepted generation returns 0. Abort and budget failures
retain their existing propagation and status-output rules.

Context JSON retains copied configuration and bounded history. Optional
`include_sources` history rows contain canonical aliases, actual paths and raw
input hashes for dependencies read; they do not contain source text or executable
links. Existing history rows/configurations remain valid. Published product
hashes remain exact saved evidence. A saved service is not an execution checkpoint.

Reports expose the extended stored_source_translation_policy. See
[regressions](../tests/test_stored_translation_inputs.py),
[semantic ledger](semantics/stored_translation_input_semantics.json),
[mapped include](../examples/stored_inputs_file.kl),
[nested includes](../examples/stored_inputs_nested.kl),
[record arrays](../examples/stored_inputs_records.kl),
[joint arrays](../examples/stored_inputs_joints.kl),
[linked caller](../examples/stored_inputs_forwarded/main.kl) and
[queue arrays](../examples/stored_inputs_queues/main.kl).

Authored public fixtures compare the complete translation configuration/history,
tagging only version-dependent Python/listing hashes after checking their digest
format. Primary and include hashes remain exact. Installed acceptance also checks
artifact generation, separate child execution, compiler-free configuration and
saved-context replay. Controller/native/compiler source equivalence is unclaimed.
