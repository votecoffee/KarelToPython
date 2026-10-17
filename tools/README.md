# Developer tools

Run tools from the repository root with Python 3.11 or later.

## Public checks

```sh
python -m unittest discover -s tests
python tools/run_examples.py
python tools/check_repository.py
```

The example runner compiles authored sources in memory and compares independent
fixtures, using an injected delay callback. It writes no generated example modules
or translation reports. It deliberately executes only the checked-in authored
examples; optional corpus tools never execute their inputs.

The repository check inspects tracked files and untracked files Git would include.
It rejects local artifact paths, private release/report formats, user-profile
paths and unsupported Python syntax, and checks local Markdown links. Ignored
`.local/` content is excluded unless force-added to Git, in which case the check
rejects it.

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
