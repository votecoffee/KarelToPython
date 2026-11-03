# Dynamic FILE arrays

Pythonic CREATE_VAR now accepts `FILE` with dimensions, `ARRAY OF FILE`, transparent
FILE aliases and supplied named FILE ARRAY types. Each new cell owns a fresh closed
descriptor. It uses the [static FILE ARRAY](file-arrays.md) borrowed-storage rules
and the existing explicit FILE transports. No backend is opened or discovered by
creation itself. This is an offline allocation extension, without native ABI,
controller or strict-mode equivalence claims.

```karel
PROGRAM STREAMS
VAR entry,status,value:INTEGER
ROUTINE work(a:ARRAY OF FILE)
BEGIN
  OPEN FILE a[2] ('WO','out')
  WRITE a[2] (17)
  status=IO_STATUS(a[2])
  CLOSE FILE a[2]
  value=17
END work
BEGIN
  CREATE_VAR('CACHE','STREAMS','','ARRAY OF FILE',0,2,0,0,status)
  work(BYNAME('CACHE','STREAMS',entry))
END STREAMS
```

Supply a supported ExecutionContext FILE service. The generated CLI examples run
with explicit initial context and save replayable context JSON:

```sh
python -m karel2py examples/dynamic_file_array_binary.kl -o converted.py
python converted.py --context examples/dynamic_file_array_binary.services.initial.json --state-out state.json
python converted.py --context state.json --state-out replay.json
```

## Shapes, allocation and references

The three dimension slots retain their inner-to-outer order. `2,3,0` creates
logical shape `[3,2]`; zero means unused and gaps are rejected. ARRAY OF requires a
positive inner slot. A named ARRAY type with zero extra dimensions retains its
complete schema; extra dimensions wrap that named component. Aliases and foreign
type owners resolve only through explicitly supplied source definitions.

Schemas require concrete positive dimensions, named nested components, logical
rank at most three and at most 32767 descriptor cells. Every cell reserves one
unit in the shared 32767 dynamic-creation budget. Metadata, schema, group/pool,
name collisions and capacity are checked before allocation. The existing creation
checkpoint rechecks bank identity, terminal state, collisions and shared quota
before publication. Group and memory-pool choices remain metadata.

Borrow exact named ARRAYs, rank-compatible generic ARRAYs, fully selected named
rows or individual FILE cells through BYNAME. Typed linked routines retain the
same storage. Root/namespace renaming retains live descriptors and lookup hints;
ordinary cancellation, pause/resume and pending-read cleanup apply. FILE ARRAY
metadata uses the existing FILE leaf type code and logical dimensions in VAR_INFO
and VAR_LIST. Whole ARRAY assignment, grouped value arguments, resource fields,
ARRAY results and whole-FILE GET_VAR/SET_VAR copies remain unavailable.

## Closed allocation markers

Only creation-tagged context variable rows accept this representation:

```json
{
  "program": "CACHE",
  "path": "STREAMS",
  "type": ["ARRAY", 2, ["FILE"]],
  "value": {"closed": true},
  "creation": {"group": 0, "memory_pool": 0}
}
```

The single marker describes the entire allocation. Encoding validates every exact
ARRAY container, its schema/shape/list length and every exact FILE descriptor.
Every FILE must have no owner and no pending read. Open or malformed storage
rejects the complete save before an existing state file is replaced. The payload
requires exactly Boolean true, with no extra fields or per-cell state.

Restore checks schema, metadata and combined reservation limits before allocating
fresh independent closed descriptors. Names, cursor, mode, status, attributes,
backend registrations, scanner state, pending work and aliases reset to defaults.
The complete ARRAY schema, named components, group and pool remain. Explicit
backend bytes follow their existing service snapshots. Later source routines can
open the restored descriptors again; no suspended execution is restored.

Generic typed FILE/FILE ARRAY codecs still reject descriptors. Rows without
creation metadata cannot use the marker. Static FILE ARRAY globals retain their
omission policy; explicit bindings cannot copy resource storage into those globals.
VR SAVE/CLEAR/LOAD excludes created FILE ARRAY roots and leaves their descriptors
alone. [PATH/QUEUE ARRAY creation](collection-arrays.md) now uses a separate
logical-snapshot contract; resource STRUCTURE fields remain excluded.

The [semantic ledger](semantics/dynamic_file_array_semantics.json) and authored
regressions cover creation, checkpoint changes, quota/schema preflight, text/binary
I/O, inspection, linked references, cancellation, saves and restoration. Runnable
examples also cover named rows and renamed allocations. Strict mode remains a
future milestone.
