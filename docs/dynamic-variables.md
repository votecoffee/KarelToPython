# Dynamic variables and named routine arguments

Pythonic mode supports `CREATE_VAR`, `RENAME_VAR`, `RENAME_VARS` and `BYNAME`
over the explicit offline `ExecutionContext.variables` store. These calls share
storage with `GET_VAR`, `SET_VAR`, `VAR_INFO` and `VAR_LIST`. No controller or
variable discovery is involved.

## Creation

```karel
CREATE_VAR('CACHE','ITEM','','INTEGER',0,0,0,0,status)
SET_VAR(entry,'CACHE','ITEM',7,status)
```

The signature is `CREATE_VAR(program,name,type_program,type_name,group,inner,
middle,outer,status[,memory_pool])`. Names are case-insensitive ASCII identifiers
of up to 36 characters. Blank program and type-program strings, including spaces,
use the currently executing source program. A new namespace needs no compiled
program. Existing declared globals, explicit roots and descendant bindings prevent
creation under the same root; an existing value is never reset.

Supported data types are INTEGER, REAL, BOOLEAN, BYTE, SHORT, STRING[n], CONFIG, VECTOR, POSITION,
XYZWPR, XYZWPREXT, JOINTPOS and JOINTPOS1..9. STRING defaults to capacity 12;
explicit capacities are 1..254. JOINTPOS defaults to nine axes. `ARRAY OF BYTE`
and `ARRAY OF SHORT` require a nonzero inner dimension. Other types can use the
resolved user-type declarations of the specified attached program, including
named arrays and structures containing portable data.
[Direct narrow types and transparent aliases](dynamic-narrow.md) use ordinary
BYTE unknown contents and SHORT missing markers, with exact BYNAME references
and checked values under the existing metadata/allocation limits.

Dimensions follow the manual's inner-to-outer argument order: inner=4, middle=3,
outer=2 creates ARRAY[2,3,4]. Used dimensions are contiguous, positive and at most
32767. Omitted dimensions are zero. An already declared array type takes zero
dimensions; additional dimensions around a named array are rejected. All created
variables together are limited to 32767 reserved creation units, checked before
allocation: ordinary data uses scalar leaves; [root collections](dynamic-collections.md)
use descriptors and allocated PATH header leaves.

New storage uses ordinary runtime uninitialized defaults. BYTE retains its
existing unknown-byte policy. Group is retained as metadata in 0..32; positional
leaf types require 1..32. Memory pool is metadata only: omitted/0 means DRAM
intent and -1 means CMOS intent. Saving JSON preserves values for both policies;
no power-cycle or native memory behavior is simulated. [Dynamic logical collections](dynamic-collections.md)
add root PATH/QUEUE_TYPE and supplied aliases with zero extra dimensions. FILE,
embedded resources, collection ARRAYs and proprietary vision types remain excluded.

## Renaming

```karel
RENAME_VAR('CACHE','ITEM','RESULT',status)
RENAME_VARS('CACHE','SAVED',status)
```

`RENAME_VAR(program,old,new,status)` renames an explicit ordinary root. Related
explicit field/element bindings move with it. The target must be unused.
`RENAME_VARS(old_program,new_program,status)` moves all ordinary root bindings
from an unattached namespace into an unused namespace. Same-name requests are
successful no-ops after validating the source. Both calls preserve underlying
references, values, creation metadata and existing variable lookup entry numbers.

Compiled globals and attached program namespaces cannot be renamed: generated
code retains their static names. Namespace moves containing system roots or
standalone field/element bindings are also rejected. An alias already passed to
a routine remains valid when its explicit root is renamed, including across a
cooperative pause. Renaming variables does not rename scheduler tasks or programs.

| Status | Portable meaning |
| --- | --- |
| 0 | Success |
| 1 | Source variable/namespace missing |
| 2 | Invalid name or memory pool |
| 3 | Target already exists |
| 4 | Compiled or protected source namespace/name |
| 5 | Unsupported type, dimensions or group |
| 6 | Aggregate created-variable allocation limit |

Failure statuses preserve the variable store. Source inputs and writable status
references retain the ordinary exact-type, protection and indirect FOR guards.
Creation and rename commits also charge the execution step budget. Creation
rechecks the bank identity, root collisions and reserved capacity after its
checkpoint, preserving completed callback effects without overwriting a competing root.

## BYNAME

```karel
ROUTINE increment(item: INTEGER)
BEGIN
  item=item+1
END increment

increment(BYNAME('CACHE','RESULT',entry))
```

`BYNAME(program,path,entry)` is accepted only as a direct argument to a declared
user routine, including explicitly linked external routines. It supplies a true
reference, without requiring the variable's value to be initialized. The resolved
type must match the formal parameter using the existing STRING capacity, array
shape and named-type identity rules; numeric coercions are not applied.

An empty program uses the calling task root's source program, including inside a
linked routine. Explicit names select current/attached programs or supplied
variable-store roots. Static fields and array indices are accepted. System paths,
protected POSITION/CONFIG fields and an entry output overlapping the selected
variable raise before writing the entry or entering the called routine. Missing
variables and type mismatches also raise without changing the entry. Arguments
and selectors evaluate once, left to right. Active FOR counters retain indirect
write guards, including through nested routines and handlers.

Entry numbers are offline cache hints. They need not be initialized and are not
native table identifiers. Renaming keeps these hints within the current context;
loading JSON creates a fresh lookup cache. BYNAME is not an ordinary value
expression, a dynamic routine lookup or a way to access routine-local variables.

## Saved context and CLI examples

Created values use the existing typed `variables` rows. Rows additionally carry
`creation: {"group": 0, "memory_pool": -1}` when created by source. Metadata,
schemas and aggregate limits are validated before decoding created arrays.
Duplicate rows, including case-folded duplicates, are rejected. Saved data does
not include live aliases or executable user-type declarations; attach translated
programs again to use their user types for later creation.

Run the authored [dynamic lifecycle](../examples/dynamic_variables.kl) and
[named arguments](../examples/byname_arguments.kl) examples through the CLI:

```sh
python -m karel2py examples/dynamic_variables.kl --check
python -m karel2py examples/byname_arguments.kl --check
python -m karel2py examples/dynamic_variables.kl -o .local/dynamic_variables.py
python .local/dynamic_variables.py --state-out .local/dynamic_state.json
python .local/dynamic_variables.py --context .local/dynamic_state.json --state-out .local/dynamic_state.json
```

Create `.local` before using these output paths. The lifecycle example restores
its working names before replay and produces the same final data.

The translation report's `dynamic_variable_policy` and the
[semantic ledger](semantics/dynamic_variable_semantics.json) describe this
contract. Native variable layout, allocation, task naming, statuses and memory
pool lifetime remain unverified; strict mode is future work.
