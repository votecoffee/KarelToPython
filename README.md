# KarelToPython

![KarelToPython icon](karel2py/assets/icons/karel_to_python_icon_64x64.png)

KarelToPython translates a supported subset of FANUC KAREL into Python for
offline inspection and execution. The current build is **26.1119.230858**.

## Table of Contents

- [Background](#background)
- [Install](#install)
- [Usage](#usage)
- [Supported Features](#supported-features)
- [Development](#development)
- [Maintainers](#maintainers)
- [Contributing](#contributing)
- [License](#license)

## Background

The translator checks KAREL types, storage, and control flow before generating
Python. The offline runtime models variables, I/O, files, and other services
using supplied data. See the [language support guide](docs/language-support.md)
and [remaining support inventory](docs/unsupported.md).

## Install

Requires **Python 3.11 or later**. The desktop workbench also requires Tkinter.
From a virtual environment:

```sh
git clone https://github.com/votecoffee/KarelToPython.git
cd KarelToPython
python -m pip install .
```

## Usage

### CLI

Validate, translate, and run the sample. The final snapshot has `TOTAL=200`.

```sh
python -m karel2py examples/control_flow.kl --check
python -m karel2py examples/control_flow.kl -o converted.py
python converted.py
```

Add `--report translation.json` to save diagnostics and the source map. The CLI
requires new output paths by default. Use `--force` to replace selected outputs
and `--version` to check the installed build. For linked sources, see the
[project CLI](docs/portable-projects.md).

### Desktop GUI

```sh
python -m karel2py.gui
```

Open KAREL, choose **Translate to Python**, then **Save Python**. Choose
**Run Python**, then **New from Python** to select the generated file and
create a saved run. Select a discovered input and choose **Edit value** or
**Edit fields**. Use **Edit context** to configure services. **Run** executes
the saved inputs, and **Last result** shows termination status and saved state.
**WRITE output** shows the captured text. Choose **New linked** to pin several
cooperative Python modules and select an entry program. Use **Discover
inputs** on a linked run to review reads and unresolved dependencies across
the selected modules.
See the [desktop guide](docs/desktop.md).

### Python

```python
from karel2py import translate

result = translate("PROGRAM DEMO VAR n:INTEGER BEGIN n=6*7 END DEMO")
print(result.python_source)
```

See the [API guide](docs/api.md) for generated Program instances, context
providers, execution limits, and linked projects.

### Saved runs from the CLI

```sh
python -m karel2py.runner create converted.py session.run.json --discover
python -m karel2py.runner run session.run.json
```

Edit `inputs.context` before running a program that requires initial values.
Inputs and results share one JSON file. Use `runner refresh` to carry compatible
inputs to a new translation. See [saved runs](docs/run-documents.md) and
[input discovery](docs/input-discovery.md).
For multiple linked modules, export cooperative Python and pin the set with
`runner create-project`. Use `runner discover-project` to inspect read-before-write
candidates in saved linked runs.
See [linked project runs](docs/run-documents.md#linked-project-runs).

## Supported Features

- Structured control flow, labels and jumps, routines, and reference parameters.
- Checked scalar types, arrays and records, and common math and string builtins.
- Offline registers, ports, files, PATH and queues, task control, and timers.
- Position and joint operations with explicit models for kinematics.

Pythonic mode uses practical Python numeric behavior. The [feature guide](docs/feature-guide.md)
covers translation options, offline services, and the detailed feature history.
See the [roadmap](docs/roadmap.md) for the compiler decomposition, remaining
linked runner work, and the future strict mode.

## Development

Install with `python -m pip install -e .`. Run focused tests near each change.
The full local checks cover unit tests, 609 standalone examples, and 250 linked
projects:

```sh
python -m unittest discover -s tests
python tools/run_examples.py
python tools/check_repository.py
```

Native GUI checks are opt-in. GitHub Actions workflows run by manual dispatch.
See the [developer tools](tools/README.md), [compiler architecture](docs/compiler-architecture.md),
and [changelog](CHANGELOG.md). Keep private research and generated artifacts
outside tracked source or in `.local/`.

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
