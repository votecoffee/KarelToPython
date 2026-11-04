# Wildcard ARRAY dimensions from saved schemas

Pythonic conversion can specialize direct global wildcard ARRAY declarations
from root ARRAY schemas in an explicitly supplied saved JSON context. Use the
`array_context` API option or `--array-context` on the converter/project CLI.
No values or services are restored during schema selection.

```sh
python -m karel2py input.kl --array-context saved.json -o translated.py
python translated.py --context saved.json
python -m karel2py.project sources --array-context saved.json --context saved.json --entry MAIN --state-out next.json
```

The first command generates concrete storage. The second separately loads the
saved values into that storage. The project command makes both choices explicit.
Omitting `--array-context` retains the existing requirement for `--array-shape`.
The generated Python does not require schema selection at runtime.

```python
from karel2py import translate, translate_project

saved = {"variables": [{"program": "MAIN", "path": "VALUES",
          "type": ["ARRAY", 3, ["INTEGER"]], "value": [7, 9, 11]}]}
result = translate(source_text, array_context=saved)
project = translate_project(source_modules, array_context=saved)
```

`load_project(..., array_context=saved)` accepts the same metadata. This is
optional translation-time specialization, not automatic controller discovery or
an implementation of the future Python runner/input-discovery milestone.

## Selection and exact interfaces

Parse PROGRAM names and declarations after normal include expansion. Match
case-insensitive `(program, root variable)` pairs. Only direct global declarations
containing `*` are candidates. Fixed/named globals, routine locals, fields and
indexed-path cache entries are not specialized. Unrelated scalar and nonroot
bindings do not supply dimensions. Missing metadata leaves the normal missing
dimension diagnostic in force; it does not invent a shape.

Use the complete concrete outer dimensions, including fixed dimensions in mixed
declarations such as `ARRAY[2,*]`. Explicit `array_shapes`/`--array-shape` keys may
cover other variables or agree with the selected schema. Conflicts reject; old
duplicate, unused and common/qualified-overlap checks remain unchanged.

Validate concrete ARRAY schemas and allocation bounds before using them. The
ordinary compiler still checks rank, fixed dimensions, named components and
leaf/descriptor quotas. After resolving source types, compare the complete
schema exactly, including scalar category, STRING capacity, named record/ARRAY
identity, Cartesian representation, joint width and PATH node/header layouts.
No reshape, cast, type inference, capacity inheritance or source-type replacement
is added. Data, joint, PATH/QUEUE_TYPE and FILE ARRAY allocation schemas retain
their existing source rules. FILE metadata does not restore an open handle.

Projects follow explicit imported-variable owner/reexport chains. An owner's
saved root schema can supply matching wildcard declarations in its importers.
Conflicting schemas along that chain and cycles reject before returning a
translated project. Unrelated programs with the same variable name may have
different dimensions. Existing type, variable and routine linkage checks remain.

## Metadata, payloads and saved values

The API requires a context object containing a `variables` list. Each row uses
the normal `program`, `path`, `type`, `value` keys and optional `creation` metadata.
Root ARRAY types use canonical list-form concrete schemas. Duplicate variable
bindings reject case-insensitively. All recognized root ARRAY schemas are checked,
including unused ones; payload values, non-ARRAY schemas, creation policies and
other service fields are not restored or validated as execution state here.

This distinction permits a schema-only document whose required `value` fields
are null. Such a document supplies dimensions but is not necessarily a runnable
execution context. Supply complete valid state separately through `--context` or
`ExecutionContext.from_config()` when initial values are wanted. Invalid saved
values/services remain errors at that ordinary execution boundary.

Generated modules embed concrete dimensions. Reports record selected schemas,
their source program/root identities and normal specialization metadata, without
payload values or unused service settings. Their translation-context hash depends
on selected schemas, not saved values. Reusing a schema catalog does not mutate
the caller's metadata or import graph. A changed shape requires retranslation.

## Files, bounds and evidence

Schema files are explicit regular UTF-8 JSON, optionally with a BOM, within
16 MiB. Duplicate JSON keys and nonfinite numbers reject anywhere in the file.
API/file catalogs permit at most 32767 variable rows; existing dimension,
64-level data-schema and 32767-leaf/reserved-unit bounds remain. Type/schema
checks do not allocate ARRAY contents or execute KAREL bodies.

Converter output/report and project state/trace outputs cannot alias the schema
input, including hard links and forced converter overwrites. Project execution
context loading and generated-code execution remain separate explicit actions.
There is no native PC/VR inspection, file searching, runtime resizing, wildcard
TYPE/field/local support, GUI interaction or controller allocation equivalence.
The stored-source TRANSLATE service retains its existing explicit `array_shapes`
configuration. Strict mode remains future work.

See [project shape routing](project-array-shapes.md),
[regressions](../tests/test_array_context.py),
[semantic ledger](semantics/array_context_semantics.json),
[scalar input](../examples/array_context_scalars.kl),
[record input](../examples/array_context_records.kl),
[joint components](../examples/array_context_joints.kl),
[PATH banks](../examples/array_context_paths.kl),
[imported globals](../examples/array_context_forwarded/main.kl) and
[linked queue banks](../examples/array_context_collections/main.kl).
