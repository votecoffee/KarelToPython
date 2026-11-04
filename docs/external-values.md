# Explicit external values and argument cases

Pythonic FROM routines now accept typed JSON data results from explicit callbacks.
The generated Python and project CLIs also accept `--external-values` to supply
fixed data, explicit no-op procedures, or exact argument/result tables. They run
without executable host code or inferred external-library behavior.

[Explicit response outputs](external-outputs.md) now add selected writable data
arguments through result/outputs responses or optional case outputs. Legacy fixed
values, null no-ops and cases without outputs retain the rules below.

## Binding file and CLI

```json
{
  "HOST": {
    "FETCH": {
      "cases": [
        {"arguments": [{"type": ["INTEGER"], "value": 1}],
         "result": {"type": ["INTEGER"], "value": 17}},
        {"arguments": [{"type": ["INTEGER"], "value": 2}],
         "result": {"type": ["INTEGER"], "value": 42}}
      ]
    },
    "LABEL": {"type": ["STRING", 4], "value": "seed"},
    "NOTIFY": null
  }
}
```

FETCH selects a supplied response; LABEL always returns fresh supplied data.
NOTIFY explicitly returns None and changes no arguments or services. It is useful
only where that no-op is the intended offline response. No missing binding is
silently replaced with a no-op or an invented result.

Create the ignored `.local` directory before running these commands:

```sh
python -m karel2py examples/external_value_scalars.kl -o .local/external_values.py
python .local/external_values.py --external-values examples/external_value_scalars.external.values.json --state-out .local/external-values-state.json
python -m karel2py.project examples/external_value_forwarded --entry MAIN --external-values examples/external_value_forwarded/external.values.json --state-out .local/external-project-state.json
```

`rt.external_value_callbacks(config)` prepares a callback bank for API use.
`rt.load_external_values(path, outputs=...)` loads strict JSON with input alias
protection. `rt.load_external_bindings(values=..., collections=..., outputs=...)`
validates both data and legacy collection files before returning their disjoint
union. The CLI uses that same operation. Existing explicit callback precedence
over supplied source libraries is unchanged.

The separate `--external-collections` option retains its existing logical
PATH/QUEUE contract. Both files may be supplied for one execution when normalized
program/routine pairs are disjoint. [Logical snapshots](external-logical-values.md) now extend the same value file
to PATH/QUEUE_TYPE results, cases and scalar/bank outputs. FILE storage and
resource-bearing record fields remain excluded; generic data helpers stay guarded.

## Data and interfaces

Fixed results and case results support INTEGER, REAL, BOOLEAN, BYTE, SHORT,
bounded ASCII STRING, builtin and named records, Cartesian poses, JOINTPOS and
concrete data ARRAYs. Missing scalar leaves and unknown BYTE leaves survive
ordinary aggregate copies. Missing shaped containers, missing scalar function
results, malformed known values and resource fields reject.

Typed rows require exactly `type` (a concrete list-form schema) and `value`.
ARRAY payloads use their declared nested shape, records use exact uppercase field
names, and joints use exactly an `axes` list. Missing markers require a single
key with Boolean true. STRING payloads must fit their supplied capacity; the
loader does not silently truncate malformed input. Schema validation precedes
codec allocation. Existing data domains and 64-level schemas remain in force.

Every selected result is checked against the source declaration when called.
Scalar, record, joint and named ARRAY types remain exact. Anonymous ARRAY result
wildcards and inherited STRING capacities follow the existing result rules.
Tagged BYTE data is not an implicit INTEGER cast, and a different Cartesian
representation is not an implicit conversion. Explicitly convert data at the
existing source boundaries when needed. Raw Python callback results retain their
existing behavior; typed JSON is an additional explicit result form.

For an API callback, return the same typed row directly. Generator callbacks may
also return it after their normal yields. Result decoding finishes before later
destination selectors or source arguments. Failed results leave an unassigned
receiver intact; earlier explicit callback/source effects remain visible.

## Case capture and matching

All ordinary source arguments evaluate and undergo interface checks first. A case
adapter snapshots every supplied ordinary data reference without changing it.
The complete concrete schema participates in matching, including nominal names,
STRING capacities, actual dimensions, known values and explicit missing markers.
Generic formals retain the caller's actual schema. Computed/grouped/converted
arguments keep their ordinary private-cell rules; live data prefixes are copied
for matching. [Logical collection arguments](external-logical-values.md) use
their own checked snapshots; FILE and protected reference objects are excluded.

Matching uses canonical typed snapshots. Payload object key order is ignored;
schema lists and nominal layouts remain exact. REAL JSON integers normalize to
floats, and negative zero matches positive zero.
BOOLEAN and numeric categories remain distinct. Every case for one binding has
the same argument count; zero-argument cases are allowed. Duplicate normalized
selectors reject during loading. There are no wildcard cases, expressions,
implicit fallbacks, partial argument matches or executable snippets.

An unmatched call raises a source-line runtime error without echoing argument
payloads or writing arguments. A selected null result must be used by a procedure;
a function still requires its declared data result. A procedure still rejects a
non-None result. Case matching calls no host services and adds no checkpoints,
clock reads or pauses. Ordinary handlers, FOR guards, pause/resume, stop,
sticky abort and frame cleanup retain their existing contracts.

## Bounds, saved state and evidence

The data file permits 128 case-insensitive program/routine bindings and at most
128 total fixed/case rows. Names are ASCII identifiers within 254 characters.
Each case has at most 64 arguments. The complete data configuration is limited
to 32767 stored snapshot units; each case call's incoming arguments share that
same bound, checked before copying. Ordinary leaves cost one unit; logical
descriptors and contents follow the [logical response budget](external-logical-values.md). STRING capacity and ordinary schema
bounds still apply. These are offline prototype limits.

Files are strict UTF-8 JSON, optionally with a BOM, within 4 MiB per file.
Duplicate keys, NaN/Infinity and invalid later rows reject before installation.
State/trace outputs cannot alias either input, including hard links. The adapter
bank is installed only after both supplied files validate and duplicate bindings
are excluded.

Saved context/VR/DRAM contains copied global data. It contains no binding tables,
callbacks, private arguments, generators or suspended execution. Supply the data
file again on saved-context replay. This adds no GUI execution controls or input
discovery runner; those remain separate milestones. No external algorithms,
native ABI, controller execution or strict equivalence are inferred.

`external_value_policy` reports the scope and limits. See the
[semantic ledger](semantics/external_value_semantics.json),
[regressions](../tests/test_external_values.py),
[scalar cases](../examples/external_value_scalars.kl),
[record copies](../examples/external_value_records.kl),
[pose/joint data](../examples/external_value_poses.kl),
[mixed data/collection bindings](../examples/external_value_procedures.kl),
[forwarding project](../examples/external_value_forwarded/main.kl) and
[ARRAY case project](../examples/external_value_cases/main.kl).
