# Contributing

Open an [issue](https://github.com/votecoffee/KarelToPython/issues) for questions,
bugs or proposals. Pull requests are welcome.

## Working on changes

Use Python 3.11 or later. From the repository root:

```sh
python -m pip install -e .
python -m unittest discover -s tests
python tools/run_examples.py
python tools/check_repository.py
```

Change generic parser, emitter or runtime behavior rather than special-casing an
input program. Include a minimal authored reproducer and a test that distinguishes
the intended behavior from a plausible incorrect implementation. Keep source
locations, type checks, effects, initialization and frame cleanup intact.

## Semantics and evidence

Document supported forms and limits in [the support guide](docs/language-support.md)
and the relevant [semantic notes](docs/semantics/README.md). Distinguish manual
rules, conservative prototype restrictions and offline test observations. Do not
expand controller, numeric rounding or ABI claims from translation acceptance alone.
Update the root README when usage or supported features change.

## Public repository contents

Use authored examples and temporary synthetic fixtures. Do not add customer or
robot backups, proprietary application source, credentials, internal paths,
manual PDFs or private corpus reports. Store local research and generated files
outside the checkout or in `.local/`, which is ignored by Git. Review
`git status --short` and run the repository check before committing.

Submitting a contribution means it is available under this repository's
[MIT license](LICENSE).
