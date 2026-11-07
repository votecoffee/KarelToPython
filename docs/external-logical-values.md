# Explicit external logical values

Pythonic `--external-values` bindings now accept PATH and QUEUE_TYPE logical
snapshots in fixed results, exact argument cases and result/outputs responses.
Scalar collections and concrete collection ARRAYs use the existing typed JSON
schemas and logical codecs. The same response form works in explicit Python
callbacks. FILE storage and resource-bearing record fields remain excluded.

```json
{
  "HOST": {
    "FILL": {
      "result": null,
      "outputs": [{"argument": 1, "value": {
        "type": ["QUEUE_TYPE"],
        "value": {"initialized": true, "sequence": 7,
                  "entries": [[3, 17], [1, 9]]}
      }}]
    }
  }
}
```

Calling `ROUTINE fill(value:QUEUE_TYPE) FROM HOST` with a borrowed queue updates
that captured queue. The response carries logical initialized state, last sequence
and ordered ID/value entries. IDs may be sparse and out of numerical order.
It supplies no buffer ownership, queue algorithm or controller connection.

## Interfaces, matching and ownership

Collection kinds, nominal node/header layouts and concrete output dimensions
must match exactly. Anonymous function-result ARRAY dimensions retain the existing
wildcard rules. Named/nested ARRAY components remain exact. No resource field,
schema inference, equal-size reshaping, numeric cast or native layout is added.
PATH missing/unknown leaves retain the existing logical codec rules.

Each argument case captures the complete checked logical value before matching
or response writes. Schemas, header/node values, queue initialized state, last
sequence, IDs and entry order all participate. Buffer links do not participate;
an existing link must still satisfy the normal queue validity checks. Ordinary
data and logical arguments can share a case or output batch. Canonical payload
key order and REAL-zero matching follow the existing external-value policy.

Bare exact arguments, complete indexed cells and explicit live BYNAME rows
retain their original storage. Grouped/computed arguments and direct collection
row/plane arguments own private copies; outputs to them do not copy back. Every
returned value and each separately supplied output owns independent logical data.

## Atomic publication and aliases

Validate the result, all new values, all selected current logical values and
complete disjoint target cells before any response write. Malformed old storage,
wrong interfaces, protected references, readonly PATH headers or target overlap
reject the entire response. Normal source-selector and earlier Python-callback
effects remain visible. No checkpoint, host callback or clock read runs during
publication.

Whole banks retain ARRAY roots and collection-cell identities. Scalar PATH roots
and compatible headers retain their identities; new independent nodes replace
old node lists. Old node aliases detach. Queue roots retain their identities,
replace logical entries/counters and detach old buffer links without writing
the old buffer. A separate output to that buffer's ordinary data cells is allowed
when it is physically disjoint from the queue root. A PATH plus its header/node
field, or a bank plus one of its collection cells, overlaps and rejects.

## Bounds and replay

The external-values configuration and each incoming case argument set share a
32767-unit limit. Each response result and all its outputs also share that limit,
checked before decoding contents. Ordinary scalar leaves cost one unit. Each
collection descriptor costs one; PATH headers/nodes add their scalar leaves,
and each queue entry adds two units for ID and value. ARRAY costs include every
collection cell and its contents. Existing dimensions, 64-level data schemas,
64 arguments/outputs, 128 bindings/rows and strict 4 MiB JSON-file bounds remain.
Each selected old logical snapshot must independently fit these bounds.
Structured replies charge one execution step per supplied snapshot unit and
per existing output target unit before decoding. Budget exhaustion publishes
no response outputs. The earlier effects of the calling Python callback remain.

Pause delays response writes until return. Stop, abort, failure or budget
exhaustion discards an unreturned response. Saved context/VR/DRAM includes copied
global logical data and sequence counters, omitting queue buffer links, response
tables, callbacks, captured references and suspended frames. Supply bindings
again for replay. The existing `--external-collections` fixed-result loader is
unchanged and may be combined with disjoint normalized bindings.

Create the ignored `.local` directory before running these commands:

```sh
python -m karel2py examples/external_logical_paths.kl -o .local/external_logical.py
python .local/external_logical.py --external-values examples/external_logical_paths.external.values.json --state-out .local/external-logical-state.json
python -m karel2py.project examples/external_logical_cases --entry MAIN --external-values examples/external_logical_cases/external.values.json
```

This is an authored offline protocol. External algorithms, FILE effects, native
ABI, controller execution and strict-mode equivalence require separate work.
The future Python runner/input-editor milestone is unchanged.

See [ordinary values](external-values.md), [response outputs](external-outputs.md),
[logical results](external-collection-results.md),
[regressions](../tests/test_external_logical_values.py) and the
[semantic ledger](semantics/external_logical_value_semantics.json).
