# Explicit external response outputs

Pythonic FROM functions and procedures can now apply checked data outputs from
explicit JSON responses. Use the existing `--external-values` option or return a
response object from an explicit Python callback. The response result and all
selected outputs validate before any response write is published.

## Response format

```json
{
  "HOST": {
    "FILL": {
      "result": null,
      "outputs": [
        {"argument": 1, "value": {"type": ["INTEGER"], "value": 17}},
        {"argument": 2, "value": {"type": ["INTEGER"], "value": 42}}
      ]
    }
  }
}
```

A source `ROUTINE fill(value,status:INTEGER) FROM HOST` can call `fill(n,s)` to
populate those captured caller cells. Argument numbers are one-based. Outputs
are explicit; no parameter directions, algorithm or library are inferred. A
procedure uses a null result. A function supplies its ordinary typed result.
An empty output list is allowed.

Each response requires exactly `result` and `outputs`; each output requires
exactly `argument` and `value`. `outputs` is a list of at most 64 entries, with
distinct integer ordinals in 1..64. Boolean, string, negative or repeated
ordinals reject. Each selected argument must exist in the actual call.

A case may add an optional `outputs` member alongside its existing `arguments`
and `result`. All input snapshots are matched before output writes. Case output
ordinals must also fit the case's declared argument count. Legacy fixed typed
values, null procedures and cases without outputs retain their existing behavior.
The [external value guide](external-values.md) covers strict JSON loading,
case matching and disjoint legacy collection bindings.

Create the ignored `.local` directory before running these commands:

```sh
python -m karel2py examples/external_output_scalars.kl -o .local/external_outputs.py
python .local/external_outputs.py --external-values examples/external_output_scalars.external.values.json --state-out .local/external-outputs-state.json
python -m karel2py.project examples/external_output_forwarded --entry MAIN --external-values examples/external_output_forwarded/external.values.json --state-out .local/external-output-project-state.json
```

## Argument ownership and data

Normal source argument evaluation and interface conversion happen first, once
in source order. Outputs use the actual captured references, not later variable
lookups. Bare exact scalar/aggregate arguments and explicit live BYNAME data
prefixes update their original cells. Grouped, computed, converted and ordinary
copied-prefix values have private cells and do not copy back. Generic STRING
and ARRAY formals retain the caller's concrete capacities, dimensions and names.

Outputs require exact concrete data metadata matching those cells: INTEGER,
REAL, BOOLEAN, BYTE, SHORT, bounded STRING, builtin/named records, Cartesian
poses, JOINTPOS and data ARRAYs. No implicit reference cast, capacity truncation,
layout change or joint conversion is added. Explicit missing scalar markers and
unknown BYTE values may be written, including partial aggregate leaves. All
selected old containers and new containers must remain shaped; known old and new
data must satisfy the existing domains and bounds.

Ordinary writable reference objects are required. Protected reference classes
and readonly record roots reject. Source constants, computed values and protected
CONFIG subfields retain their existing private-argument rules; POSITION
orientation source arguments retain their existing rejection. Whole POSITION
replacement remains legal and keeps its orientation-column protection.
FILE, PATH and QUEUE_TYPE outputs/results are excluded from this data response
form. Use the existing explicit callbacks or source implementations where those
resource effects are needed.

## Atomic response publication

Validate the declared result, output metadata, known destination data and every
selected output value. Then check complete physical target-cell overlap,
including record fields, ARRAY/prefix cells and joint axes. Multiple outputs
must be disjoint, even when their supplied values are equal. An untargeted input
may alias an output; only the explicitly written batch is checked for overlap.

After complete validation, publish outputs in argument-number order, preserving
ordinary root, record-field, element and joint-axis aliases. No callback, pause,
checkpoint or clock read occurs during publication. Return the already detached
result. The caller's later assignment and destination selectors run normally;
a result assignment to an output cell follows the response writes.

A rejected response changes none of its selected output cells and supplies no
result to the caller. Earlier ordinary argument-selector or Python-callback
effects remain visible. Raw callbacks that directly write arguments keep their
existing behavior; this batch guarantee applies to the explicit response data.
Errors retain source-line handling and do not echo argument payloads.

## Lifetimes, bounds and saved state

A generator callback may return a response after its normal yields. Pause retains
its ordinary frame; response outputs wait until the response is returned and
validated. Stop, sticky abort, failure or budget exhaustion discards an unreturned
response. Already completed response writes remain normal source effects.
Handlers, linked source forwarding, retained aliases, FOR counter checks and
existing timer/frame cleanup retain their normal rules.

The existing data configuration limits remain: 128 bindings/fixed/case rows,
64-level schemas and 32767 stored scalar leaves. Each response's result and
outputs share a 32767-leaf budget checked before decoding. A response call has
at most 64 arguments and at most 64 outputs. The input file remains strict UTF-8
JSON within 4 MiB, with duplicate-key/nonfinite checks and state/trace output
alias protection, including hard links. All definitions validate before loading.

Context/VR/DRAM saves copied global values only. Output definitions, captured
references, callbacks and suspended frames are not serialized. Supply the binding
file again on replay. This is an explicit offline data protocol; no native ABI,
controller writes, inferred external algorithms or strict equivalence is claimed.
The future GUI runner and input-discovery milestone are unchanged.

`external_output_policy` reports the scope and publication rules. See the
[regressions](../tests/test_external_outputs.py),
[semantic ledger](semantics/external_output_semantics.json),
[scalar outputs](../examples/external_output_scalars.kl),
[record aliases](../examples/external_output_records.kl),
[live rows](../examples/external_output_prefixes.kl),
[pose/joint data](../examples/external_output_poses.kl),
[linked forwarding](../examples/external_output_forwarded/main.kl) and
[case outputs](../examples/external_output_cases/main.kl).
