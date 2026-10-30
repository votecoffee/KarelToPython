# Dynamic FILE descriptors

Pythonic `CREATE_VAR` accepts a root `FILE` or a supplied transparent FILE alias,
with zero extra ARRAY dimensions. Creation allocates a fresh closed logical
handle and costs one reserved creation unit. It neither opens a file nor supplies
an I/O service. This is an authored offline extension over the existing
[dynamic variable arguments](dynamic-variables.md); native resource allocation
and compiler/controller acceptance remain unverified.

```karel
VAR entry,status,value:INTEGER
ROUTINE read_value(handle:FILE)
BEGIN
  OPEN FILE handle('RO','input.txt')
  READ handle(value,CR)
  status=IO_STATUS(handle)
  CLOSE FILE handle
END read_value
-- Inside the main BEGIN:
CREATE_VAR('CACHE','INPUT','','FILE',0,0,0,0,status)
read_value(BYNAME('CACHE','INPUT',entry))
```

Supply the selected memory, rooted directory, virtual volume, serial stream,
keyboard, pipe or other supported offline backend explicitly. Group 0..32 and
DRAM/CMOS intent remain metadata and do not route files or connect a device.
Arrays/fields containing resources remain excluded. The existing name, schema,
collision, quota, callback and terminal ABORT/stop creation guards still apply.

## Typed use and lifetime

Exact BYNAME FILE formals use ordinary OPEN/CLOSE, scalar text/binary READ/WRITE,
attributes and source file procedures, including explicitly linked routines.
Passing a FILE to an incompatible formal fails before entry writes or routine
effects. Whole-FILE GET_VAR/SET_VAR and source handle-field access remain excluded.
VAR_INFO uses existing FILE code 29 and reports a closed handle as uninitialized;
VAR_LIST type filtering uses the same code.

Root/namespace renames preserve the live handle, captured references, backend
registration, cursor and lookup entry hints. Ordinary FILE assignment can alias
the same live handle through two roots. Pause/resume retains those references.
ABORT, stop or read failure keeps completed effects and existing handle lifetime:
close any still-open handle explicitly after the pending operation has unwound.

[Cooperative cancellation](file-cancellation.md) works through a retained FILE
formal, including source handlers and READ_KB editors. It preserves the existing
status 6, unread-prefix, output/cursor and cleanup rules. The FILE must still be
explicitly opened; omitted/default FILE aliases and native pending writes remain
outside that contract.

## Closed descriptor JSON

Only creation-tagged context variable rows use this additional representation:

```json
{
  "program": "CACHE",
  "path": "INPUT",
  "type": ["FILE"],
  "value": {"closed": true},
  "creation": {"group": 0, "memory_pool": 0}
}
```

Encoding requires exact FILE storage with no owner and no pending read operation.
An open or pending created handle rejects the save, including ownership by a
backend outside the context. Failed encoding preserves an existing state file.
The marker requires the exact Boolean true and no additional payload fields.

Restore validates creation metadata, schema and combined reserved capacity before
allocating a fresh closed FileHandle. Filename, cursor, mode, status, attributes,
XML scanners, backend registration and alias relationships reset to constructor
defaults. File bytes and other service data follow their existing independent
snapshots. A directory snapshot restores as the existing memory snapshot model,
without recreating a host directory connection. A descriptor alone does not
configure a files service.

This representation stores allocation intent, not an open handle or suspended
execution. Generic typed FILE encoding/decoding still rejects FILE values, rows
without creation metadata remain rejected, and portable variable archives retain
FILE exclusions. Existing declared FILE globals keep their prior save policy.
Reattach source definitions for later custom-alias creation or linked calls.

Reports add `dynamic_file_policy`, covering allocation, typed operations, reset
rules and persistence boundaries. See [text I/O](../examples/dynamic_file_text.kl),
[binary I/O and aliases](../examples/dynamic_file_binary.kl),
[renaming](../examples/dynamic_file_rename.kl),
[serial input](../examples/dynamic_file_serial.kl),
[linked input](../examples/dynamic_file_project/main.kl),
[timed cancellation](../examples/dynamic_file_cancel_project/lib.kl),
[regressions](../tests/test_dynamic_files.py) and
[semantic ledger](semantics/dynamic_file_semantics.json).
Strict mode remains a future milestone.
