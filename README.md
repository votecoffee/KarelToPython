# KarelToPython

KAREL source to Python translator with a checked offline runtime

Translate a supported subset of FANUC KAREL into Python modules with a checked
offline runtime and practical Python numeric equivalents. Unsupported syntax produces explicit
diagnostics or runtime errors. The translator does not connect to a robot.

The repository is named **KarelToPython**; its Python package and command-line
tool are named **karel2py**. The current implementation is **0.76.0**. It is a
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

Pythonic `WRITE` supports mixed text, signed numbers, REAL formatting and `CR`
newlines, for example `WRITE('value=',value::0::3,CR)`. Requests are recorded or
sent to a supplied callback. See the [text output guide](docs/pythonic-output.md).

STRING functions and writable value arguments are supported too. `STRING`
results default to 254 characters; `STRING[n]` results truncate at the declared
capacity. Parenthesized STRING arguments use private storage. See the
[STRING guide](docs/pythonic-strings.md).

Functions compose in operators, argument lists, array subscripts, conversions
and FOR bounds. Pythonic mode evaluates ordinary operands and arguments left
to right, short circuits BOOLEAN `AND`/`OR`, and captures assignment values before
resolving targets. See the [evaluation order guide](docs/evaluation-order.md)
for reference aliasing and compatibility changes.

Whole ARRAY value arguments use private checked copies. ARRAY results can be
passed onward, forwarded by RETURN, or read directly with `make()[1]`.
See the [ARRAY values guide](docs/pythonic-arrays.md) for ownership and limits.
Results also support named types and fixed or wildcard matrix/cube dimensions.
`ARRAY_LEN` returns the first dimension, like Python `len`. See
[ARRAY result shapes](docs/array-result-shapes.md).

WRITE formats accept INTEGER expressions, including function calls. Quoted
STRING fields handle apostrophes and truncation; REAL-to-text conversion supports
fixed and scientific notation. See [Pythonic text formats](docs/text-formats.md)
for the chosen conventions, evaluation order and bounds.

SUB_STR clips at the source end and permits zero counts; INDEX accepts empty
searches. See [STRING operations](docs/string-operations.md) for bounded slicing,
one-based positions and character checks.

Global-counter FOR loops can call helpers when transitive write checks protect
the counters. Read-only counter references are supported, and initialized
counters clear on RETURN, ABORT and errors. See [Pythonic FOR](docs/pythonic-for.md)
for cleanup, argument passing and remaining restrictions.

USING supports nested lexical scopes and dotted STRUCTURE selectors. Inner
fields take precedence, with outer bindings restored afterward. See
[Pythonic USING](docs/pythonic-using.md) for field, constant and routine lookup.

TYPE aliases provide alternate names for supported types and keep original
aggregate identities and capacities. Bounded STRING alias parameters accept
checked references or private value copies. See [TYPE aliases](docs/type-aliases.md).

VEC constructs independent VECTOR values from numeric components. Unary signs
and left-associated cross/dot chains support composed calculations such as
`SQRT(v@v)`. See [Pythonic vector expressions](docs/pythonic-vectors.md).

`POS(x,y,z,w,p,r,c)` constructs an independent XYZWPR with explicit CONFIG data
and checked coordinate/angle bounds. See [POS construction](docs/pos-construction.md).
CONFIG text parsing and complete formatting use an explicit offline grammar and
portable failure status. See [CONFIG text](docs/config-text.md).
Explicit XYZWPR poses also support `a:b` composition and `INV(a)` inversion
with a documented offline angle convention. See [frame transforms](docs/frame-transforms.md).
`FRAME` builds a right-handed frame from three or four explicit points.
See [frame construction](docs/frame-construction.md) for spacing and origin rules.
Whole assignments convert between XYZWPR and POSITION, initializing protected
orientation vectors from explicit poses. See [POSITION conversions](docs/position-conversions.md).
Composition, INV and FRAME also accept POSITION and mixed POSITION/XYZWPR
operands, with direct matrix results whenever POSITION is involved.
See [POSITION geometry](docs/position-geometry.md).
APPROACH and ORIENT return independent VECTOR copies of a pose's positive Z and
Y axes. See [pose axis queries](docs/position-axes.md).
Approximate position comparison (`>=<`) uses explicit host-supplied distance,
angle and CONFIG tolerances. See [position comparisons](docs/position-comparisons.md).
Boolean `WAIT FOR` rechecks its condition with host yields and the ordinary
execution step budget. See [Boolean waits](docs/boolean-waits.md).

CNV_STR_TIME and CNV_TIME_STR convert supplied packed date/time values and
complete English text, with checked calendars and two-second precision.
See [time text](docs/time-text.md) for the format and signed bit representation.

ENVIRONMENT, COMMENT and ALPHABETIZE directives are retained as checked metadata
alongside NOLOCKGROUP. Environment requirements are recorded without loading
definitions or enabling extra facilities. See [source directives](docs/source-directives.md).

READ accepts typed scalar input through an explicit host callback. Generated
scripts can use JSON response batches with `--read-values` or ASCII text with
`--read-text`, field widths/bases/quotes and explicit CR line control. See
[READ formats](docs/read-formats.md), [text input](docs/text-input.md) and
[Pythonic input](docs/pythonic-read.md) for capture order, validation and failure behavior.

## Supported Features

- Assignment, `IF`, `SELECT`, `FOR`/`DOWNTO`, `WHILE`, `REPEAT`, restricted labels
  and `GOTO`, internal routines, `RETURN`, bare `ABORT` and host-backed `DELAY`.
- Checked `INTEGER`, `BOOLEAN`, Python-float `REAL`, bounded ASCII `STRING`,
  `BYTE`/`SHORT` storage, fixed and named arrays, named structures, transparent
  TYPE aliases and `USING`.
- Reference/value parameters, bare zero-argument function calls, checked aggregate
  copies, restricted scalar, bounded STRING, record, joint and named-component
  ARRAY functions, selected built-ins, general degree trig, SQRT, EXP and LN.
- Positional data records, POS/XYZWPR construction, opaque joint values,
  VECTOR construction/signs/products and explicit-context offline conversion subsets.
- CONFIG text parsing/formatting, with checked complete outputs and portable status.
- Explicit XYZWPR frame composition and inversion, with independent CONFIG copies.
- Three/four-point FRAME construction with checked geometry and an optional origin.
- POSITION/XYZWPR assignment conversion with checked orientation matrices.
- POSITION and mixed POSITION/XYZWPR geometry, preserving protected matrix columns.
- APPROACH/ORIENT axis queries on POSITION and XYZWPR, with writable VECTOR results.
- Approximate POSITION/XYZWPR comparison with explicit per-instance tolerances.
- Boolean WAIT FOR with repeated checks, host yields and bounded execution.
- Packed date/time text conversion with checked calendars and complete outputs.
- Source directive metadata for environment requirements, comments and display order.
- Rounded fixed/scientific REAL text formatting with precision -254..254,
  minimum-width padding and caller-capacity overflow markers.
- Signed INTEGER text formatting in bases 2..16, with checked output references
  and capacities.
- Mixed scalar `WRITE` lists, CR newlines, dynamic formats and quoted STRING
  truncation/escaping through a recorder or supplied callback.
- Scalar `READ` destinations through a typed callback, JSON batches or text/CR input,
  with complete-response checks and input-request observations.

Each item has type and context restrictions. External routines,
motion, controller files/registers/I/O and native task behavior remain unsupported.
Read the [support table and limitations](docs/language-support.md) before using a feature.

## Development

Run from the repository root:

```sh
python -m unittest discover -s tests
python tools/run_examples.py
python tools/check_repository.py
```

The example runner translates all authored runnable examples, checks complete
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
