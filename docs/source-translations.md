# Stored KAREL source to Python

Pythonic mode accepts `TRANSLATE(file_spec,listing_sw,status)` with an explicitly
enabled SourceTranslations service. It compiles a stored KAREL source into a real
Python source artifact. It does not execute the generated code, attach a program,
load a library or produce native PC data.

```python
from karel2py.runtime import ExecutionContext, MemoryFiles, SourceTranslations

context = ExecutionContext(
    files=MemoryFiles({
        "child.KL": "PROGRAM CHILD VAR value:INTEGER BEGIN value=7 END CHILD\n",
    }),
    source_translations=SourceTranslations(overwrite=False),
)
```

A source program can then call:

```karel
TRANSLATE('child',TRUE,status)
```

On success, the example backend contains `child.KL`, `child.py` and `child.LS`.
The caller receives status zero. Running the resulting Python remains a separate
explicit host action. Existing LOAD/CALL_PROG contracts do not gain native code
loading or automatic linkage from this call.

## Configuration and lazy compiler availability

The JSON service field is:

```json
{
  "source_translations": {
    "enabled": true,
    "overwrite": false,
    "source_limit": 1048576,
    "output_limit": 16777216,
    "limit": 64,
    "includes": {},
    "array_shapes": {}
  }
}
```

Supply the existing ordinary `files` or `device_files` configuration separately.
The service supports exact MemoryFiles, DirectoryFiles and DeviceFiles backends.
PIP/socket/keyboard/window devices, implicit filesystem discovery and native
controller files are unavailable.

The service is absent by default. Absence, `enabled: false`, or a runtime-only
installation without the optional compiler returns 268. Importing the runtime,
constructing the service and restoring its JSON require no compiler, lexer,
include loader, GUI or project linker. The compiler is imported only during an
enabled translation request with a readable source. A missing compiler leaves
existing output files unchanged.

## Source selection and explicit translation options

The supplied extension is ignored and `.KL` is forced, following the source
procedure's documented selection rule. Names are bounded relative ASCII paths,
with 1..36-character basenames and ordinary explicit device mappings. Lookup is
case-insensitive and must identify exactly one source; ambiguous case/separator
aliases reject the request. Backslashes in requests normalize to relative path
separators. DirectoryFiles keeps its supplied root, device mappings, symlink
checks and path confinement. Lookup scans at most 32767 stored names or entries
per selected directory, charging bounded execution steps.

Output files are placed beside the actual source, using its existing stem and
the suffixes `.py` and optional `.LS`. This is a portable same-directory policy;
there is no native default-device/RAM-disk selection. Existing output case aliases
must also resolve uniquely. Source and output files must be closed. Hardlinks
between the source/products, between products, or to other live DirectoryFiles
handles reject publication.

`includes` is an explicitly supplied mapping of include names to source text.
It is copied into the service configuration and uses the ordinary include depth,
count, format and expansion rules. Backend include files are not automatically
read. `array_shapes` supplies ordinary single-program global wildcard dimensions;
unused or incompatible shapes reject through the normal compiler. Program-qualified
project shapes do not apply to this single-source call. Translation mode is
Pythonic; strict remains future work.

The primary source is decoded as UTF-8 with an optional BOM. Its original bytes,
encoding, line endings and final newline remain unchanged. Invalid UTF-8 or
unsupported KAREL is a translation rejection. Requested listings retain numbered
source lines and diagnostics, using UTF-8/LF and escaped undecodable source bytes.
They identify Python generation and explicitly state that native PC output is
unavailable. They are portable diagnostics rather than a native compiler listing.

## Publication, status and failures

`overwrite` is false by default. Existing planned products require explicit
`overwrite: true`; no source input is overwritten. A rejected source preserves
any previous Python artifact. With `listing_sw=TRUE`, a rejection may publish an
error `.LS` under the same overwrite and file-access policy. With FALSE, rejection
changes no files. An absent source or unavailable compiler creates no listing.

Successful generation prepares and validates the complete product set before
publication. Combined output size, ordinary backend limits, busy/alias guards,
virtual device quotas and obsolete-byte accounting are checked first. The listing
is published first, and Python source last. DirectoryFiles uses an atomic file
replacement for each product; in-memory backends also validate before replacement.

This is ordered per-file publication. A later Python publication failure can
leave a new listing with the previous Python artifact retained. Such a request
returns file-failure status and records `listing_only`, without claiming Python
publication. If a budget/abort exception interrupts between products, the listing
may similarly remain, while the source status output retains its previous value.
History records the raised exception and only the artifacts actually published.

| Status | Portable meaning |
| --- | --- |
| 0 | Python artifact published successfully. |
| -1 | KAREL/UTF-8 rejected; optional error listing published if allowed. |
| 268 | Service disabled/absent or optional compiler unavailable. |
| 35084 | Source/output missing, ambiguous, busy, inaccessible, unconfigured, over capacity or publication failed. |

These values follow the reference procedure's documented broad outcomes; they do
not establish native option, alarm, binary format or default-device equivalence.
Ordinary source reference/output guards remain active. Unexpected compiler
failures, exhausted execution budgets and aborts raise instead of inventing a
successful source status.

## Bounds, abort checks and persistence

Default primary-source and combined-product limits are 1 MiB and 16 MiB.
Configurable ranges are 1 byte..4 MiB and 1 byte..64 MiB. Explicit includes retain
the compiler's 256-file, 4-MiB-per-file/8-MiB-library bounds. Source/include bytes
and prepared output bytes charge each 4096-byte block; listing and lookup work
also charge bounded steps before publication. Compilation is synchronous over
bounded supplied source. There is no native timing, background translation or
asynchronous cancellation claim.

The service checks sticky and queued abort requests before publication of each
product. It cannot create a PC artifact; a stopped/aborted generator or pending
task is not resumed by saving or loading this service.

`SourceTranslations.to_config/from_config` retain checked settings, copied include
texts/shapes, a nonwrapping request sequence and bounded history. The `limit`
history ring is 1..4096 rows, default 64. Each terminal row records caller/request,
resolved source, status/phase, a bounded diagnostic and SHA-256 hashes. Python and
listing paths/hashes are present only after those products publish. Restored rows
must have consistent phases, artifact roles and hashes; this is stored evidence,
not executable linkage or a claim that older artifact bytes remain unchanged.
Saving while a source translation is active is rejected.

The [authored regressions](../tests/test_source_translations.py) cover actual code
generation and separate execution, lazy runtime portability, source rejection,
aliases/busy files, abort/budget boundaries, per-file partial publication,
aggregate quotas and JSON replay. Manual/compiler/controller acceptance remain
separate evidence layers.
