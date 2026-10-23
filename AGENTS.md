# Repository guidance

- Keep the root README current and organized using the Standard Readme sections.
- Release versions use a fixed UTC build timestamp, `YY.MMDD.HHmmss`, stored in
  `karel2py.__version__`; packaging reads that constant. Keep the current README
  version and visible CLI identity current. Preserve historical feature versions.
- This is an offline translator. Keep uncertain source semantics explicit and
  fail closed; do not weaken generic checks or special-case individual programs.
- Keep code in `karel2py/`, tests in `tests/`, authored inputs and fixtures in
  `examples/`, public documentation in `docs/`, and developer utilities in `tools/`.
- This repository is public. Keep personal paths, usage notes, private corpus
  reports/baselines, controller/customer data, manual PDFs, generated translations
  and release archives outside Git. Use ignored `.local/` for local work.
- Do not copy proprietary source into tests. Use small authored synthetic fixtures.
- Preserve the distinction between translation acceptance, offline execution,
  compiler evidence and controller-runtime behavior.
- Run `python -m unittest discover -s tests`, `python tools/run_examples.py`, and
  `python tools/check_repository.py` for implementation or layout changes.
- Routine conversion checks use the CLI and open no GUI windows. Native GUI
  tests require explicit `KAREL2PY_GUI_TESTS=1`; use them only for GUI work or
  an explicitly requested desktop check. Keep package acceptance window-free.
- Generated Python and diagnostic reports are outputs; maintain the KAREL source
  and expected fixtures, rather than checking in generated example modules.
- Commit completed, verified changes in small, cohesive checkpoints and push them
  to origin after the relevant checks pass.
