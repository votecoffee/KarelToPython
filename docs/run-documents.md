# Saved run documents

The standalone Pythonic runner executes an explicitly selected generated Python
module and stores supplied inputs and results in separate sections of one JSON
document. It uses the existing offline runtime and adds no controller connection.
This is the first foundation of the [runner milestone](roadmap.md#python-runner-and-parameter-editor).
[Bounded input discovery and optional input templates](input-discovery.md) are
available through the CLI and the [desktop runner](desktop.md#discover-inputs-and-run-python).
Both use explicit initial values and the same saved document format.

## Prepare and run

```sh
python -c "from pathlib import Path; Path('.local').mkdir(exist_ok=True)"
python -m karel2py examples/motion_statement_boundaries.kl -o .local/converted.py
python -m karel2py.runner create .local/converted.py .local/session.run.json --context examples/motion_statement_boundaries.services.initial.json
python -m karel2py.runner run .local/session.run.json
```

Creation parses the Python with Python 3.11 syntax, inspects its literal Program
identity and pins the exact source bytes with SHA-256. It does not import or
execute the target. The target path is relative to the document when possible;
different volumes retain an explicit absolute path. Existing documents are
preserved, and output aliases of the target or supplied context are rejected.

Add `--discover` to prepare missing whole-root variable shapes in `inputs.context`
and save the discovery report, edit pointers and requirements in `inputs.template`.
It can be combined with `--context` to preserve compatible supplied values and
services. Edit the missing values before running. No bank counts or initial
values are guessed; unsupported data and services remain explicit requirements.

The run command checks the target hash and supplied context before loading the
selected Python. It executes one fresh Program, never resumes an old execution
stack, and starts from the saved inputs on every replay. Changed source requires
a new document. Run only trusted generated Python: this is ordinary Python
execution with the current account's permissions, not a sandbox or code
authenticity check. Metadata inspection does not establish that code is safe.

`refresh source.run.json new.run.json [--target converted-v2.py]` prepares a new
document from the source's edited inputs and preserved limits. It rediscovers
the selected target, retains compatible values and records input/schema changes.
The original and its results remain intact; the new result section is null.
See [refreshing inputs](input-discovery.md#refresh-edited-inputs) for migration,
provenance and unresolved-running-marker behavior.

The CLI runs synchronously. The desktop runner uses the same standalone
document service through a worker. `--version` displays the same fixed
application version as the translator and project CLIs.

## Linked project runs

Export checked cooperative Python from a source directory, select the exported
modules in scheduling order, and name the program to start:

```sh
python -c "from pathlib import Path; Path('.local/linked-python').mkdir(parents=True, exist_ok=True)"
python -m karel2py.project examples/for_start_capture_linked --python-out .local/linked-python
python -m karel2py.runner create-project .local/linked.run.json .local/linked-python/main.py .local/linked-python/lib.py --entry MAIN --discover
python -m karel2py.runner run .local/linked.run.json
```

The exporter uses declared program names for the new filenames. It checks
the source project and its linkage before publishing each module atomically.
Use a fresh output directory to keep the exported set together. You can also select
already generated Pythonic modules translated with `--cooperative`. Include
every module required by the linked project. The project scheduler uses the
listed order to break ties between tasks of equal priority.

The `karel2py.project-run.v1` document stores the entry in `target.program`
and each module's path, declared program, and SHA-256 in `target.modules`.
Paths are relative when the document and module are on the same volume.
Creation inspects Python syntax and pins bytes without
executing the modules. Execution verifies every pin before loading trusted
Python from the captured bytes. The existing linker checks types, imported
variables and routine signatures before starting the entry body. A changed
module requires a new document. You can select up to 64 modules of up to
16 MiB each, within a 32 MiB combined byte limit.

Use `--discover` to save a template with owner-qualified variable paths,
missing-value shapes, and requirements. Supply initial values with `--context`
at creation or edit `inputs.context` before replay. All programs share one fresh
offline context and virtual scheduler. `--max-steps` limits
each task, `--max-cycles` bounds the scheduler and `--max-output-chars` bounds
combined WRITE text. `results.programs` records each program's observed state
and available variables. The variable snapshots include cleanup of suspended
frames and counters. The document also records output, final context, and any
failure or cancellation. Replay always starts from saved inputs.

In the desktop runner, **New linked** inspects selected Python files, lets you
choose the entry and module order, and prepares editable inputs. **Prepare
inputs** prepares the template for an existing run. Saving inputs checks the
document revision and module pins and preserves the last result.
[Run a linked project in the desktop runner](desktop.md#run-a-linked-project)

```sh
python -m karel2py.runner prepare-project .local/linked.run.json
python -m karel2py.runner discover-project .local/linked.run.json
```

`prepare-project` uses the saved input context by default. Add `--context FILE`
to replace it with an explicit context from a separate JSON file. Preparation
updates the input template and preserves the entry, module order, limits and
previous results. `discover-project` reports input candidates without changing
the document. [Linked input discovery](input-discovery.md#linked-project-discovery)

### Refresh a linked module set

```sh
python -m karel2py.runner refresh-project .local/linked.run.json .local/revised.run.json .local/revised/lib.py .local/revised/main.py --entry MAIN
```

Supply the replacement modules in scheduling order. The saved entry is used
when `--entry` is omitted. The old modules may have changed or moved. Refresh
uses the original document's saved inputs and prior discovery annotations. It
pins the replacement modules, keeps the limits and creates a document with
empty results. The original document and results are preserved.

Variable values carry forward by owning program, root path and compatible
schema. Values with no discovered matching root are listed with pointers to the
original document. Review the new missing values and unresolved analysis before
replay. Desktop **Revise linked** uses the same migration.
[Linked refresh details](input-discovery.md#refresh-a-linked-run)

## Inputs and results

The schema is `karel2py.run.v1`, with `target`, `limits`, `inputs` and `results`.
The explicit adapter is `inputs.context`: an ordinary
[ExecutionContext configuration](offline-services.md#register-port-and-variable-context)
for variables, registers, ports, files, robot context and other supported offline
services. For example, an input section for a generated program named T with an
INTEGER variable X is:

```json
{
  "context": {
    "variables": [{"program": "T", "path": "X", "type": ["INTEGER"], "value": 21}]
  }
}
```

Edit this section in the prepared document before running it. The runner copies
context data rather than sharing the input dictionaries with execution. Results
are never used as implicit inputs, so repeated runs begin with the same values
unless the saved inputs are edited. Source-specific restoration still follows
the generated Program's checked constructor; constructor failures are recorded
without running the KAREL body. Optional discovered templates populate shapes
with missing markers; review the requirements and supply values explicitly.
`inputs.template` is an optional preparation snapshot with a source-bound
envelope. Its statuses do not refresh after edits or determine runtime readiness.
Older documents with only `inputs.context` remain compatible. No initial values
are invented.

Before loading the target, the runner atomically saves the supplied document with
a `running` result. Terminal results contain:

- `status`: completed, failed, aborted, stopped, paused or cancelled.
- `variables`: the final available variable snapshot, including missing markers.
- `context`: available final offline banks and global values in context format.
- `text_output`: captured omitted-file WRITE callback text.
- `error`: exception type, message and available KAREL line, or null.
- `capture_errors`: unavailable snapshots/context or cleanup errors by name.
- Runner version and UTC start/finish timestamps.

A normal runtime failure retains completed writes, valid partial values and
captured text. Ctrl+C during target execution records cancellation when cleanup
and publication can finish. Paused/stopped/failed continuations are cleaned up
before results are collected; this can clear active FOR counters or cancel owned
requests. Pause records a terminal paused outcome; it does not save a resumable
continuation. An unavailable snapshot/context is null with an explicit capture
error, while other valid results remain available. FILE descriptors and other
nonpersistent runtime ownership do not become resumable JSON resources.

## Limits and publication

Creation accepts `--max-steps` (default 100000) and `--max-output-chars` (default
1048576). Both values remain editable in `limits`. Steps bound runtime
checkpoints; imports, host calls and delays retain existing behavior and are not
wall-clock bounded. JSON inputs, target source and saved documents are limited
to 16 MiB. UTF-8 JSON accepts an optional input BOM; duplicate keys, nonfinite
numbers and invalid schemas are rejected. Saved JSON uses UTF-8 without BOM,
LF endings and a final newline.

Publication writes a complete temporary file before replacing the document.
Document byte checks before publication preserve detected external edits.
Use one writer per document; these checks are not cross-process transactions.
A failed initial save prevents execution. A failed final save leaves the last
complete document, normally with `running` status. A killed process can leave
that same marker. Such a document is refused on replay: resolve the previous
attempt and explicitly reset `results` to null before starting a fresh run.
The runner never assumes an interrupted attempt did nothing or retries it.

CLI exit codes are 0 for preparation or completed execution with captured
results, 1 for another terminal outcome or unavailable result capture, and 2 for
preflight/publication errors. The normal stdout response is a JSON summary;
WRITE text is retained in the document.

## Python API and scope

`karel2py.runner.make_document` inspects without publication.
`create_document(target, destination, context=...)` creates a new document;
both accept `discover=True` for optional input preparation.
`refresh_document(source, destination, target=...)` rediscovers into a new
document, preserving compatible inputs without executing the target.
`karel2py.project_run.inspect_project_modules(paths)` returns the ordered pins
without executing the modules. Pass the reviewed pins in that same order as
`expected_modules` to `create_project_document` or
`refresh_project_document(source, destination, modules, entry=...)` to check
them before saving. Linked refresh accepts the source document's exact JSON
bytes as `expected`.
`run_document(path)` executes and returns the saved document. API preflight or
publication errors raise `RunDocumentError` or a filesystem error. Run documents
and generated modules belong outside tracked public source or in ignored `.local/`.
The recommended `.run.json` suffix is ignored; the public repository check also
rejects run-document instances saved under another JSON name.

Both run formats use the offline runtime and its supported services.
The [semantic ledger](semantics/run_document_semantics.json) records the
original standalone execution contract.
