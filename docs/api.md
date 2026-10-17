# API and command-line guide

## Translation

```python
from karel2py import translate
from karel2py.lexer import TranslationError

try:
    result = translate(
        "PROGRAM DEMO VAR answer: INTEGER BEGIN answer=42 END DEMO",
        filename="demo.kl",
    )
except TranslationError as error:
    print(error.as_dict())
else:
    python_source = result.python_source
    report = result.report
```

`translate(source, *, filename="<input>", array_shapes=None)` accepts a KAREL
source string. `filename` labels diagnostics and source locations. Translation
does not run the program. The returned object exposes generated `python_source`
and a JSON-serializable `report` with program/version information, source maps,
hashes, features, effect analysis and feature-specific policies.

`TranslationError.as_dict()` contains `code`, `message`, `file`, `line` and
`column`. Unsupported source is an error, rather than a partial best-effort module.

For supported global variable-sized declarations, explicitly supply every outer
dimension through `array_shapes`, for example `{"READINGS": [3]}`. Names are
case-insensitive; fixed dimensions must agree. Shapes are embedded during
translation. They do not query or resize controller storage.

## CLI

```sh
python -m karel2py input.kl --check
python -m karel2py input.kl -o converted.py --report translation.json
python -m karel2py input.kl -o converted.py --array-shape READINGS=3
python -m karel2py --version
```

The installed `karel2py` command is equivalent. Inputs are UTF-8, with an optional
BOM. Use `--force` to replace an explicitly named output/report. Source, output
and report paths must differ. Their parent directories must already exist.
`--check` cannot be combined with `--output`.

| Exit code | Meaning |
| --- | --- |
| `0` | Translation or validation succeeded. |
| `1` | File or text-decoding error. |
| `2` | Rejected source or invalid CLI arguments. |

## Generated Program

A generated module defines `Program(*, sleep=None, write=None, joint_axes=None)`.
Call `Program().run(max_steps=100_000)` to execute explicitly and receive a
snapshot of global variables. Only the generated module's entry point runs it
automatically; importing a module defines its class.

`snapshot()` returns the current global state. Names are normalized to uppercase.
Uninitialized scalar values are represented as `{"uninitialized": true}` and
unknown initial BYTE contents as `{"unknown_byte": true}`. Routine locals are
excluded. Aggregate snapshots are detached from mutable runtime storage.

The step limit counts instrumented execution, not wall-clock time. Errors raise
`karel2py.runtime.KarelRuntimeError`. Bare KAREL `ABORT` raises
`karel2py.runtime.KarelAbort`, records `abort_info` and terminates the instance.
Use a new `Program` for a cold restart. Earlier writes and callback effects are
not rolled back by failures or ABORT.

## Host callbacks and context

- `sleep(seconds)` handles supported `DELAY`. The default is the host sleeper.
  Tests can inject a recorder. Zero delay makes no callback.
- `write(text)` handles supported text `WRITE` requests. Without it, requests
  are recorded in `write_requests`; this is not controller output. A callback
  must return `None` synchronously.
- `joint_axes=n` supplies an explicit offline axis count for the restricted
  degree-valued joint conversion subset. It is not robot discovery or group
  configuration. Copying exact joint values does not infer a controller context.

For example, a generated program using supported WRITE requests can be exercised
with `Program(write=messages.append)`, where `messages` is a list. The
`write_requests` and `abort_info` properties return defensive observations.

## Limits

The runtime uses conservative exactness, range, shape, initialization and alias
checks. Successful translation does not guarantee successful execution for all
inputs. The [language support guide](language-support.md) and [semantic notes](semantics/README.md)
describe the supported input domains and unresolved behavior.
