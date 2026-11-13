# Saved run documents

The standalone Pythonic runner executes an explicitly selected generated Python
module and stores supplied inputs and results in separate sections of one JSON
document. It uses the existing offline runtime and adds no controller connection.
This is the first foundation of the [runner milestone](roadmap.md#python-runner-and-parameter-editor).
[Bounded input discovery](input-discovery.md) is available through the CLI;
automatic value population and the GUI parameter editor remain future work.

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

The run command checks the target hash and supplied context before loading the
selected Python. It executes one fresh Program, never resumes an old execution
stack, and starts from the saved inputs on every replay. Changed source requires
a new document. Run only trusted generated Python: this is ordinary Python
execution with the current account's permissions, not a sandbox or code
authenticity check. Metadata inspection does not establish that code is safe.

No GUI is opened. The CLI process runs synchronously; a future GUI worker can
use the shared service. `--version` displays the same fixed application version
as the translator and project CLIs.

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
without running the KAREL body. Preparation does not populate discovered values;
review a discovery report and supply the context explicitly. No initial values
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
`run_document(path)` executes and returns the saved document. API preflight or
publication errors raise `RunDocumentError` or a filesystem error. Run documents
and generated modules belong outside tracked public source or in ignored `.local/`.
The recommended `.run.json` suffix is ignored; the public repository check also
rejects run-document instances saved under another JSON name.

This version runs one standalone Pythonic generated Program. Linked-project
execution, complete input discovery, automatic input editing, worker control
and GUI integration remain planned. It preserves existing offline service
restrictions and does not authenticate native compiler/controller behavior.
The [semantic ledger](semantics/run_document_semantics.json) records this contract.
