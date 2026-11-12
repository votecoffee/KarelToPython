# Contributing

Open an [issue](https://github.com/votecoffee/KarelToPython/issues) for questions,
bugs or proposals. Pull requests are welcome.

## Working on changes

Use Python 3.11 or later. From the repository root:

```sh
python -m pip install -e .
```

Use targeted tests and a relevant CLI smoke check for routine changes, such as:

```sh
python -m unittest tests.test_serial_read_binding tests.test_serial_waits
python -m karel2py examples/serial_streams.kl --check
```

Run the broader checks about every 20 implementation iterations, or earlier for
changes whose scope or risk warrants them. Keep a local cadence record in
ignored `.local/` and distinguish focused checks from a full validation run:

```sh
python -m unittest discover -s tests
python tools/run_examples.py
python tools/check_repository.py
```

GitHub Actions tests are manual-only. Pushes and pull requests do not start
workflows. Run local checks before submitting changes; use **Actions** >
**Tests (manual)** > **Run workflow** when hosted validation is wanted.
Native desktop checks have a separate **GUI checks (manual)** workflow.

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
