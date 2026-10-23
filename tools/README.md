# Developer tools

Run tools from the repository root with Python 3.11 or later.

## Release versions

Set `karel2py.__version__` to the release's UTC timestamp in `YY.MMDD.HHmmss`
format, for example `26.1011.172201` for 2026-10-11 at 17:22:01 UTC. Keep it
constant for that release; imports, translation and package builds must not
generate a new timestamp. Setuptools reads this constant for package metadata.
Python package metadata may normalize leading zeroes in numeric version segments;
the application retains the full display format.

Update the current version in the README, language support guide, aggregate
service ledger and changelog. Historical release entries and feature-specific
ledgers keep their original versions. The application has a command-line
interface and a desktop workbench: commands display the version in their help
and normal stderr banners, with `--version` available for direct lookup. The GUI
displays it in the title, header and About dialog.

## Public checks

```sh
python -m unittest discover -s tests
python tools/run_examples.py
python tools/check_repository.py
```

Use the CLI for development translation and validation. The focused subprocess
checks run with `python -m unittest tests.test_cli tests.test_translation.CliTests`;
they exercise generated-script execution, exit codes, report hashes, forced
replacement, source aliases and operation without desktop imports.

The default suite opens no windows. Native GUI/editor tests require explicit
`KAREL2PY_GUI_TESTS=1`; headless editor/document helpers still run by default.
Set that variable only for GUI work, then run discovery with `-p test_gui.py` or
`-p test_editor.py`. Linux native tests also need a display such as `xvfb-run -a`.
Both GitHub Actions workflows are manual-only: **Tests (manual)** runs the CLI,
runtime, example and repository checks; **GUI checks (manual)** runs native
desktop checks. Open the repository's **Actions** tab, select the desired
workflow and choose **Run workflow** to request a hosted run. Pushes and pull
requests do not start either workflow. Routine development and installed-package
acceptance use local CLI checks; do not dispatch hosted tests automatically.

The example runner compiles authored sources in memory and compares independent
fixtures, using an injected delay callback. It writes no generated example modules
or translation reports. It deliberately executes only the checked-in authored
examples; optional corpus tools never execute their inputs.

The repository check inspects tracked files and untracked files Git would include.
It rejects local artifact paths, private release/report formats, user-profile
paths and unsupported Python syntax, and checks local Markdown links. Ignored
`.local/` content is excluded unless force-added to Git, in which case the check
rejects it.

The eight supplied application PNGs under `karel2py/assets/icons/` are the only
approved binary assets. Their exact paths and SHA-256 values are checked;
unrelated binary images and changed artwork remain rejected. The originals are
packaged without resizing or recompression.

## Optional corpus scanners

`audit_*_corpus.py` tools translate or scan an explicitly supplied KAREL corpus
read-only. The existing adapter expects uppercase `.KL` files below
`KL/V8.33/`, with optional paired files below `PC/V8.33/`; individual selectors
can require particular categories. Their `--help` describes available options.
The unit tests create small synthetic layouts, so no external corpus is required
to run the public suite.

Store inputs and reports outside the repository or under `.local/`. For a supplied
corpus at `.local/corpus` and an existing `.local/` output directory:

```sh
python tools/audit_array_result_corpus.py --corpus .local/corpus --output .local/array-results.json
```

Some tools also accept `--baseline` and `--translator-package` for comparisons.
Audit JSON can contain absolute input paths, source hashes and program identifiers;
keep it local. Translation acceptance does not establish successful execution,
compiler equivalence or controller behavior. No corpus, reports or historical
release archives are bundled here.
