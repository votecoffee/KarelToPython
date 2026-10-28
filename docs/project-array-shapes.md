# Variable-sized ARRAYs in linked projects

Projects can specialize direct global wildcard ARRAY declarations using explicit
outer dimensions. The project API and CLI accept common variable names or
program-qualified names:

```python
from karel2py import load_project

project = load_project(
    "source_modules",
    array_shapes={"MAIN.VALUES": [3, 2], "LIB.VALUES": [2]},
)
instance = project.instantiate()
result = instance.run("MAIN")
```

```sh
python -m karel2py.project source_modules --array-shape MAIN.VALUES=3,2 --array-shape LIB.VALUES=2
python -m karel2py.project source_modules --array-shape MAIN.VALUES=3,2 --array-shape LIB.VALUES=2 --entry MAIN --state-out state.json
```

The first CLI invocation validates and links without executing KAREL bodies. The
second explicitly executes MAIN and saves the ordinary context values. Every
invocation needs the same explicit specialization; saved JSON does not discover
ARRAY dimensions or resize generated storage.

## Routing and validation

An unqualified `VALUES` key applies to each program declaring a direct global
variable-sized `VALUES` ARRAY. Other programs, including those with a scalar or
fixed ARRAY of that name, receive no shape for it. This lets a project combine a
wildcard-using application and ordinary libraries without the old unused-context
failure. Use qualified keys when different programs need different shapes.

Qualification uses the declared PROGRAM name, independent of source filenames.
Names are ASCII and case-insensitive. Include expansion and the ordinary KAREL
parser identify the declarations; comments and routine-local variables do not
create candidates. Unknown programs, unused names, case-insensitive duplicate
keys and overlapping common/qualified keys reject the project. Overlap rejects
even when both dimensions agree; use one unambiguous specification per target.

Shapes are lists or tuples of one to three positive INTEGER dimensions in
1..32767. Supply every outer dimension, including fixed dimensions in mixed
declarations such as `ARRAY[*,2]`. The ordinary compiler still checks rank, fixed
dimension agreement, named element layouts and the 32767-scalar-leaf bound.
Named ARRAY declarations, TYPE/field/local wildcards and fixed global ARRAYs
cannot be specialized with these keys.

Imported global wildcard declarations are also explicit targets. Specialize the
owner and every importing declaration, either with one common name or matching
qualified keys. Existing exact type/linkage checks still reject mismatched
shapes. A routine using wildcard formals can receive either concrete shape when
its existing rank/element interface permits it.

## Metadata and limits

`Project.array_shapes` exposes the normalized per-program shape maps, including
empty maps for programs without specialization. Each translation report retains
its own local `translation_context.array_shapes`, context hash and variable-array
records. Generated `Program.external_array_shapes` contains the same concrete
local specialization. Program qualification is a project routing choice; it does
not change the single-source `translate()` or `karel2py` CLI name grammar.

This is translation-time allocation from supplied source and dimensions. There
is no VR inspection, runtime wildcard discovery, ragged ARRAY, native allocation
or controller-loading behavior. Stored task/FILE handles and suspended stacks
keep their existing persistence restrictions. Strict mode remains future work.
