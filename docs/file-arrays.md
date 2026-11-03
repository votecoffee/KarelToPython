# FILE arrays

Pythonic mode supports fixed `ARRAY OF FILE` storage. Every element starts as
an independent closed descriptor. Indexed operations use the same explicit
backends, formats, cursor/status rules and cooperative input as an ordinary FILE.
This is an offline storage extension, without a native ABI or controller claim.

```karel
PROGRAM STREAMS
VAR files: ARRAY[2] OF FILE
    value: INTEGER
BEGIN
  OPEN FILE files[1] ('WB','data')
  WRITE files[1] (17)
  CLOSE FILE files[1]
  OPEN FILE files[2] ('RB','data')
  READ files[2] (value)
  CLOSE FILE files[2]
END STREAMS
```

Supply `ExecutionContext(files=MemoryFiles())`, another supported explicit FILE
service, or an explicitly rooted filesystem through the generated CLI. The
translator does not create a host filesystem or controller connection implicitly.

```sh
python -m karel2py examples/file_array_binary.kl -o converted.py
python converted.py --context examples/file_array_binary.services.initial.json --state-out state.json
```

## Declarations and interfaces

- Global and routine-local declarations, transparent FILE aliases, named ARRAY
  types and named ARRAY components are supported. Fresh local arrays are allocated
  for each invocation. Concrete logical rank is limited to three and allocation
  to 32767 descriptor cells. Direct global wildcard declarations still require
  explicit translation-time shapes.
- Bare ARRAY arguments borrow original storage. Generic `ARRAY OF FILE` and
  rank-specific `ARRAY[*,*] OF FILE` interfaces inherit compatible caller shapes;
  named interfaces retain exact type identity. A fully selected named component
  row can be borrowed. Incomplete flat rows/planes can now be borrowed explicitly
  through [BYNAME](resource-prefix-references.md). Ordinary resource-prefix values
  remain unavailable.
- Individual cells can be passed to FILE formals. Source-linked routines, imported
  globals and exact BYNAME references retain descriptor identity. Grouped ARRAY
  arguments, ARRAY results, whole ARRAY assignment and resource-bearing STRUCTURE
  fields are rejected. GET_VAR/SET_VAR whole-data transfers do not copy descriptors.

## Operations and lifetime

OPEN, CLOSE, READ, WRITE, attributes, cursor/status queries and CANCEL FILE accept
selected cells. `UNINIT(files[index])` uses the descriptor open-state policy;
whole ARRAY UNINIT remains excluded. Binary output keeps the existing portable
scalar encoding; text input keeps the existing parser rules.

A statement captures its FILE selector before its later operands using the
ordinary FILE rules. Routine arguments and named-component selection retain the
original storage. A cooperative READ retains the selected descriptor across
pause/resume. Cancellation or stopping unwinds the pending read without publishing
partial input. Stopping does not implicitly close every open descriptor: explicit
CLOSE and backend ownership rules still apply.

## Saving and boundaries

Program snapshots show nested per-cell FILE observations. Context JSON omits
static FILE arrays from `variables`, just as it omits ordinary static FILEs.
VR SAVE/CLEAR/LOAD excludes these roots and leaves live descriptors alone. Supplied
backend bytes retain their existing persistence and open-handle save restrictions.
A new Program creates fresh closed descriptors; cursor, mode, attributes, open
registrations and pending work are not restored.

Generic typed FILE ARRAY codecs, explicit FILE ARRAY binding snapshots and copying
such bindings into attached globals fail. An explicit external BYNAME binding may
borrow live storage, but cannot turn it into serializable data. [CREATE_VAR FILE
arrays](dynamic-file-arrays.md) use a separate creation-tagged closed-allocation
marker. No implicit resize, resource prefix copies, native FILE layout or
strict-mode equivalence is added.

The [semantic ledger](semantics/file_array_semantics.json) lists the verification
sources. Runnable examples cover text, binary, named rows, input, linked routines
and imported globals.
