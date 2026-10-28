# Dynamic BYTE and SHORT variables

Pythonic `CREATE_VAR` accepts the direct type names `BYTE` and `SHORT`, together
with transparent aliases to those types from the current or an explicitly
attached translated program. Created variables use the same checked storage as
[standalone narrow scalars](scalar-narrow.md), static narrow aggregate leaves,
`GET_VAR`, `SET_VAR` and typed routine references.

This is an explicit Pythonic extension. The KAREL Reference Manual
MARRC75KR07091E Rev N, A.3.53 (`CREATE_VAR`), lists `ARRAY OF BYTE` and
`ARRAY OF SHORT`; its BYTE/SHORT descriptions restrict native declarations to
aggregate members. Standalone dynamic narrow variables and transparent scalar
alias creation do not establish native compiler, allocation, memory layout or
controller acceptance. Internal legacy scalar guards remain in place, and
public strict mode is a future milestone.

## Creation and initial values

```karel
PROGRAM DYNAMIC_NARROW
TYPE octet = BYTE
VAR
  entry, status: INTEGER
  observed: BYTE
ROUTINE initialize(value: octet)
BEGIN
  value = 255
END initialize
BEGIN
  CREATE_VAR('CACHE','VALUE','','octet',0,0,0,0,status,-1)
  initialize(BYNAME('CACHE','VALUE',entry))
  GET_VAR(entry,'CACHE','VALUE',observed,status)
END DYNAMIC_NARROW
```

Direct `BYTE` and `SHORT` names work in the same call. New BYTE storage contains
an explicit unknown marker; it never starts with a guessed zero. A matching
reference can initialize it without first reading it. Scalar reads fail until
it is written, and `UNINIT` remains prohibited for BYTE storage. Initialized
BYTE values are integers in 0..255.

New SHORT storage is uninitialized. Values -32768 through 32766 are initialized;
32767 clears storage to the uninitialized marker. A matching SHORT reference can
use `UNINIT`, assign a value, or clear it. Range failures preserve the previous
value. Numeric coercions and scalar result rules follow the existing narrow
scalar contract; dynamic creation changes none of those domains.

Names are case-insensitive ASCII identifiers of up to 36 characters. Blank
creation namespace and type-program strings use the currently executing source
program, including inside linked routines. A direct built-in type needs no
attached type-program declaration. An alias requires the translated program's
existing type table; supplying a string does not define a new alias or discover
a program. This differs from blank-program `BYNAME`, which uses the calling
task root's source program.

Zero dimensions create one scalar leaf. Nonzero dimensions around direct narrow
names or transparent narrow aliases follow the existing inner/middle/outer
argument order: `(4,3,2)` creates `ARRAY[2,3,4]`. The documented `ARRAY OF BYTE`
and `ARRAY OF SHORT` spellings still require a nonzero inner dimension. Named
array types retain their shape and cannot receive additional dimensions.

## Exact references and variable services

`BYNAME` supplies the created variable's actual storage to a directly declared
routine parameter. The formal must match the scalar type exactly: a BYTE root
cannot bind a SHORT or INTEGER formal through `BYNAME`, even when a private
numeric value conversion would be allowed for a normal expression argument.
Missing/type errors preserve the entry output and do not enter the routine.
Aliased storage survives root/namespace renaming, linked routine calls and
cooperative pause/resume. No alias handle is serialized.

`GET_VAR` likewise requires a matching output reference. Unknown BYTE contents
copy as unknown with status 0; missing SHORT contents copy as uninitialized with
the existing missing-value status 12311. INTEGER output storage does not silently
widen a BYTE or SHORT source. `SET_VAR` keeps its existing checked integral
conversions; INTEGER 32767 written to SHORT produces missing storage and status
12311. BYTE initialization checks, protected writes and indirect FOR-counter
guards retain their existing boundaries.

## Limits, failures and persistence

The existing portable creation statuses apply: 0 success, 2 invalid name/pool,
3 collision, 5 unsupported type/dimensions/group and 6 created-leaf limit. All
created variables together retain the 32767 scalar-leaf cap; a scalar consumes
one leaf. Invalid dimensions, groups, collisions and excess allocation reject
before storage allocation or publication. The execution budget is charged before
creation commits. An existing variable is never reset by duplicate creation.

Nonpositional group metadata remains in 0..32. Memory pool metadata remains
0/omitted for DRAM intent or -1 for CMOS intent. These are stored policy values,
without simulated power-cycle or native allocation behavior. Renaming preserves
the same reference, type, value, policy and existing lookup cache entry.

Context JSON and portable variable archives preserve explicit narrow types,
known values, unknown BYTE/uninitialized SHORT markers and creation metadata.
Archive restoration retains matching storage identities, rejects conflicting
creation policies before publication, and uses the existing whole-batch checks.
JSON does not store executable alias declarations: reattach the translated type
owner to create another variable by that alias after restoring a context. The
restored variable's concrete BYTE/SHORT schema remains usable without that table.

Authored checks are in [test_dynamic_narrow.py](../tests/test_dynamic_narrow.py).
The broader [dynamic variables](dynamic-variables.md),
[variable transfers](variable-transfers.md) and
[variable archives](variable-archives.md) guides describe the inherited policies.
