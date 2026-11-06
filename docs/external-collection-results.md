# External collection function results

Pythonic FROM functions can return scalar PATH/QUEUE_TYPE values or collection
ARRAYs through explicit Python callbacks. The result may be exact runtime storage
or a canonical typed JSON object. Compiled source links keep their existing exact
interface checks. These are offline adapters, without native routine ABI,
controller/compiler acceptance, external library discovery or strict equivalence.

## Runtime values and typed JSON

```python
from karel2py import runtime as rt

row = {
    "type": ["QUEUE_TYPE"],
    "value": {
        "initialized": True,
        "sequence": 7,
        "entries": [[3, 17], [1, 9]]
    }
}
context = rt.ExecutionContext(externals={("HOST", "FETCH"): lambda: row})
```

A source `ROUTINE fetch:QUEUE_TYPE FROM HOST` can assign that result, pass it as a
private argument, forward it through another RETURN or use the applicable I/O
rules. A PATH with an explicit header can also supply a private USING selector.
The same callback can return an owned QueueValue, PathValue or collection Array.
No callback-owned runtime storage or JSON object becomes the receiver's storage.

Typed objects require exactly `type` and `value`, with the existing list-form
schema. Scalar kinds and PATH node/header layouts must match exactly. Collection
ARRAY components and names stay exact; declared generic outer dimensions become
concrete from returned storage. Equal-size reshaping, numeric/geometry conversion
and resource-bearing STRUCTURE results are not inferred.

Validate the complete logical result before selecting an assignment destination
or evaluating later source arguments. Keep partial PATH missing markers, BYTE
unknown markers, queue initialization, sparse IDs, FIFO order and last sequence.
Copy all nodes, headers, entries and bank cells independently; omit queue buffer
links. Existing receivers retain their normal root/header/cell identities during
source assignment. Explicit callback writes or other completed source effects
remain visible if result validation later fails.

Existing bounds apply: 32,767 PATH scalar leaves, queue entries or collection-bank
snapshot units, one through three logical ARRAY dimensions and 64 data-schema
levels. JSON PATH totals are checked before node allocation; bank totals are
checked before cell allocation. Malformed known values, missing shaped containers,
shared owned runtime cells and inconsistent JSON markers reject.

Generator callbacks retain the normal pause/resume/stop/abort and routine-frame
cleanup contracts. Callback results are captured before frame cleanup, and
private values never copy back to the callback. Generic queue checked/value/
result helpers, whole ARRAY/PATH UNINIT and FILE results retain their guards.
[Typed ordinary data results](external-values.md) now have a separate explicit
contract; logical collection schemas keep the rules documented here.

[External logical responses](external-logical-values.md) now extend
`--external-values` to fixed logical results, exact argument cases and atomic
scalar/bank outputs. The legacy fixed loader below remains unchanged.

## Fixed values from the CLI

Create the ignored `.local` directory before running this example:

```sh
python -m karel2py examples/external_queue_result.kl -o .local/external_queue.py
python .local/external_queue.py --external-collections examples/external_queue_result.external.collections.json --state-out .local/external-state.json
python -m karel2py.project examples/external_result_forward --entry MAIN --external-collections examples/external_result_forward/external.collections.json --state-out .local/project-state.json
```

The binding file maps program names to function names and typed logical values:

```json
{
  "HOST": {
    "FETCH": {
      "type": ["QUEUE_TYPE"],
      "value": {
        "initialized": true,
        "sequence": 7,
        "entries": [[3, 17], [1, 9]]
      }
    }
  }
}
```

These functions return a fresh copy of the same supplied value on every call.
Source arguments still evaluate and undergo normal interface checks, but this
fixed-value adapter ignores them and never writes borrowed arguments. Use
separate [external data case bindings](external-values.md) for exact supplied
argument-dependent data responses. Use an explicit Python callback or supplied
KAREL source for algorithms or resource effects. Separate
[explicit data response outputs](external-outputs.md) now add staged ordinary
argument writes. No host code or native library is loaded.

Program/function names are case-insensitive ASCII identifiers of 1..254
characters. Normalized pairs must be distinct; at most 128 bindings are accepted.
All bindings validate before installation. Files require UTF-8, optionally with a
BOM, within 4 MiB. Duplicate JSON keys, NaN/Infinity and malformed bindings reject
before program execution. State/trace outputs cannot alias the binding input,
including through hard links. Ordinary filesystem-root selection stays separate.

For API use, `rt.external_collection_callbacks(config)` returns fixed callbacks;
`rt.load_external_collections(path, outputs=...)` adds strict file loading and
input protection. Install them explicitly into `context.externals`. Existing
explicit bindings retain the project linker's normal callback precedence.

Saved JSON/VR/DRAM state contains copied logical values, omitting callbacks,
generators, frames and buffer links. Supply the binding file again on replay;
it is not embedded in the state document. The future input-discovery/runner
milestone and GUI execution controls are unchanged.

Reports expose `external_collection_result_policy`. See the
[semantics ledger](semantics/external_collection_result_semantics.json),
[regressions](../tests/test_external_collection_results.py),
[scalar PATH](../examples/external_path_result.kl),
[queue bank](../examples/external_queue_bank.kl),
[named PATH bank](../examples/external_path_bank.kl),
[borrowed project](../examples/external_result_borrowed/main.kl) and
[forwarding project](../examples/external_result_forward/main.kl).
