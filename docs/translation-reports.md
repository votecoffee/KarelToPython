# Current Pythonic translation reports

Successful public API and generated JSON reports describe the active Pythonic mode.
They do not inherit the internal legacy strict limitations. Forward types,
nested/sibling jumps, partial data copies, writable STRING temporaries and
supported source conversions must not be described as blocked features.

Generate a report without executing source:

```sh
python -m karel2py examples/nested_jumps.kl --check --report .local/translation.json
```

Create the ignored `.local` folder first. The GUI's existing Report view uses the
same data; no separate GUI interpretation or native controller check is implied.
Rejected CLI diagnostic reports retain their existing error fields and do not
claim a successful translation's capability summary.

## Compatible strings and stable categories

`limitations` remains a list of strings for existing report readers.
`limitation_details` contains corresponding rows with four fields:

| Field | Meaning |
| --- | --- |
| `id` | Stable category identifier, such as `control_transfers` or `initialization`. |
| `description` | The same current-mode text as the corresponding `limitations` entry. |
| `policies` | Keys of detailed policy objects in this report; a category may have none. |
| `guide` | Public repository-relative documentation path. |

Use IDs and policy keys for integrations instead of matching English prefixes.
Descriptions may improve without changing category identity. Each report owns its
rows and lists; modifying one report does not alter later translations.

`limitation_policy.schema_version` is 1. Its mode is `pythonic`, and it identifies
the summary's fields, scope and [remaining-support guide](unsupported.md).
`controller_validated` remains false. The rows summarize broad limits rather than
claiming a complete overload inventory, coverage percentage or native acceptance.

## Supported behavior and remaining guards

The summary distinguishes checked capabilities from actual restrictions:

- Forward constants/types resolve acyclic supplied definitions. Missing owners
  and cyclic storage still reject.
- Partial ARRAY/record copies preserve missing markers. Scalar reads and complete
  geometry consumers still require available data.
- Source numeric, record and Cartesian conversions preserve declared receiver
  schemas. Explicit aliases, generic helpers and linked declarations retain their
  exact-interface rules.
- Nested/sibling and active-FOR jumps follow checked continuations. Entry into
  unstarted FOR or uncaptured USING scopes and cross-body transfers remain blocked.
- Writable STRING value arguments remain private with documented capacities.
  Bare arguments retain caller storage.
- Files, robot data, communications and external routines require explicit
  offline context. Saved data does not restore live resources or suspended code.

Detailed policies remain the place to check particular forms. The positional
conversion, record-result and ARRAY-result descriptions use resolved source types
and their conversion policies rather than older exact-only source restrictions.
Runtime checks and source diagnostics keep their existing contracts.

The internal legacy translation path retains its separate conservative report;
public `--mode strict` is still a future milestone. This report cleanup adds no
new execution semantics or native/controller equivalence claim. The
[behavioral report tests](../tests/test_pythonic_report_contracts.py) execute
representative supported programs and verify that important rejected forms remain
rejected. Linked projects use the same current-mode summary per source module.
