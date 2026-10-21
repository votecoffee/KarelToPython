# KarelToPython

KAREL source to Python translator with a checked offline runtime

Translate a supported subset of FANUC KAREL into Python modules with a checked
offline runtime and practical Python numeric equivalents. Unsupported syntax produces explicit
diagnostics or runtime errors. The translator does not connect to a robot.

The repository is named **KarelToPython**; its Python package and command-line
tool are named **karel2py**. The current implementation is **0.51.0**. It is a
development prototype, with no claim of controller runtime equivalence.

## Table of Contents

- [Background](#background)
- [Install](#install)
- [Usage](#usage)
- [Supported Features](#supported-features)
- [Development](#development)
- [Repository Layout](#repository-layout)
- [API](#api)
- [Maintainers](#maintainers)
- [Contributing](#contributing)
- [License](#license)

## Background

KAREL and Python differ in storage, parameter passing, numeric behavior and
control flow. This project makes those differences explicit in a parser, code
generator and runtime. It supports inspecting and exercising small source
programs offline while preserving type, initialization and ownership checks.

Translation acceptance, successful offline execution and controller behavior
are separate results. Motion, controller I/O and robot commissioning are outside
the current implementation. See the [language support guide](docs/language-support.md)
for specific restrictions and [reference notes](docs/references.md) for provenance.

## Install

Requires **Python 3.11 or later**. The runtime uses only the Python standard library.
From a local checkout:

```sh
git clone https://github.com/votecoffee/KarelToPython.git
cd KarelToPython
python -m pip install .
```

An editable development install is also supported:

```sh
python -m pip install -e .
```

Use a virtual environment when installing. No manual PDFs, compiler installation,
private corpus or robot connection is needed to run the public tests and examples.

## Usage

### CLI

Validate a KAREL source without generating or executing a module:

```sh
python -m karel2py examples/control_flow.kl --check
```

Generate a Python module and a JSON translation report, then run the module:

```sh
python -m karel2py examples/control_flow.kl -o converted.py --report translation.json
python converted.py
```

The installed `karel2py` command accepts the same arguments. Output files must be
new unless `--force` is specified. Exit codes are `0` for successful translation
or validation, `2` for rejected source or invalid CLI arguments, and `1` for file
or encoding errors. Translation does not execute the input program.

Generated modules print a snapshot of global values when run directly. For
example, the control-flow example finishes with `TOTAL` equal to `200`.

### Python

```python
from karel2py import translate

source = "PROGRAM DEMO VAR result: INTEGER BEGIN result=6*7 END DEMO"
translation = translate(source, filename="demo.kl")
print(translation.report["program"])  # DEMO
print(translation.python_source)
```

The generated module defines a `Program` class. For a module saved as
`converted.py`, execute it explicitly:

```python
from converted import Program

snapshot = Program().run(max_steps=100_000)
assert snapshot["TOTAL"] == 200
```

Generated Python needs `karel2py` on its import path. See the [API guide](docs/api.md)
for translation options, runtime callbacks, diagnostics and execution limits.

### Translation mode

**Pythonic mode is the default.** Ordinary decimals, rounded arithmetic and
Python math functions work without the former exact binary32 restriction.
For an explicit choice, use `translate(source, mode="pythonic")` or:

```sh
python -m karel2py examples/pythonic_numeric.kl --mode pythonic --check
```

`ROUND` uses Python's ties-to-even rule, so `ROUND(2.5)` returns 2. REAL values
use Python `float`; structural and initialization checks remain. **Strict mode
is a future milestone**; its previous exactness work is preserved internally.
See the [equivalence matrix and mode roadmap](docs/numeric-modes.md).

## Supported Features

- Assignment, `IF`, `SELECT`, `FOR`/`DOWNTO`, `WHILE`, `REPEAT`, restricted labels
  and `GOTO`, internal routines, `RETURN`, bare `ABORT` and host-backed `DELAY`.
- Checked `INTEGER`, `BOOLEAN`, Python-float `REAL`, bounded ASCII `STRING`,
  `BYTE`/`SHORT` storage, fixed and named arrays, named structures and `USING`.
- Reference/value parameters, bare zero-argument function calls, checked aggregate
  copies, restricted scalar, bounded STRING, record, joint and named-component
  ARRAY functions, selected built-ins, general degree trig, SQRT, EXP and LN.
- Positional data records, opaque joint values, selected VECTOR operations and
  explicit-context offline conversion subsets.
- Rounded fixed-decimal REAL text formatting with 0..254 fractional digits,
  minimum-width padding and caller-capacity overflow markers.
- Signed INTEGER text formatting in bases 2..16, with checked output references
  and capacities.
- Restricted text `WRITE` requests through a recorder or supplied callback.

Each item has type and context restrictions. Direct STRING function results,
broad ARRAY result forms, external routines,
motion, controller files/registers/I/O and native task behavior remain unsupported.
Read the [support table and limitations](docs/language-support.md) before using a feature.

## Development

Run from the repository root:

```sh
python -m unittest discover -s tests
python tools/run_examples.py
python tools/check_repository.py
```

The example runner translates the 51 authored runnable examples, checks complete
expected snapshots and validates their output, delay, context and termination
fixtures. It also checks that the unsupported-motion example is rejected.
It uses an injected sleeper, so the delay fixture does not wait in real time.

The aggregate ARRAY example covers named records with nested arrays and STRING
fields, VECTOR arrays, exact-width joint arrays and stable captured references.
Its joint conversion uses the explicit offline axis context in its fixture.
See the [changelog](CHANGELOG.md) for implementation milestones.

Public tests create any corpus fixtures they need in temporary directories.
Optional [corpus audit tools](tools/README.md) accept an explicitly supplied corpus;
their inputs and generated reports are not part of this repository.

## Repository Layout

```text
karel2py/          Parser, lexer, code generator, CLI and checked runtime
tests/            Unit tests and synthetic corpus audit fixtures
examples/         Authored KAREL examples and expected results
docs/             API, language support, references and semantic notes
tools/            Example runner, repository checks and optional corpus scanners
.github/workflows/  Public test workflow
```

Keep machine-specific notes, original robot files, private corpora, manual PDFs,
generated translation reports and release artifacts outside the repository or
under the git-ignored `.local/` directory. Generated Python and reports are not
maintained alongside example sources.

## API

The main entry point is
`translate(source, *, filename="<input>", array_shapes=None, mode="pythonic")`. It returns a
translation containing `python_source` and `report`, or raises
`karel2py.lexer.TranslationError`. See [docs/api.md](docs/api.md).

## Maintainers

[@votecoffee](https://github.com/votecoffee).

## Contributing

Questions and bug reports are welcome in
[GitHub issues](https://github.com/votecoffee/KarelToPython/issues).
Pull requests are welcome. Include a small authored reproducer and meaningful
tests for changed behavior; keep unresolved semantics explicit and exclude
private or proprietary inputs. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 votecoffee.
