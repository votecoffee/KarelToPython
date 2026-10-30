# Record GET_VAR and SET_VAR transfers

Pythonic GET_VAR and SET_VAR can transfer compatible user STRUCTURE values and
same-rank record ARRAY prefixes across different record names. Records must have
exactly the same field-name set, matched in receiver declaration order. This is
an offline extension of the [variable transfer contract](variable-transfers.md),
with its existing lookup, aliases, status and cache rules.

~~~karel
TYPE input_t=STRUCTURE count:INTEGER label:STRING[8] ENDSTRUCTURE
     output_t=STRUCTURE label:STRING[3] count:REAL ENDSTRUCTURE
VAR original:input_t result:output_t entry,status:INTEGER
BEGIN
  original.count=7 original.label='abcdefgh'
  GET_VAR(entry,'','ORIGINAL',result,status)
END
~~~

result becomes LABEL='abc', COUNT=7.0; status is zero. The source retains its own
data and schema. SET_VAR uses the same conversion in the opposite storage direction.
No robot model, live controller bank or native structure layout is inferred.

## Compatible record fields

Fields may contain nested compatible user records, fixed ARRAYs, bounded ASCII
STRING capacities, checked INTEGER/BYTE/SHORT changes and integral-to-REAL
promotion. Context-free Cartesian representation and checked joint-width changes
are supported. Representation-changing geometry must be complete, finite and
valid under the existing positional rules. Exact partial pose/joint copies keep
their existing missing-data behavior.

ARRAY fields within a converted record must match every logical dimension;
receiver component names and flat/nested layout may differ. Field additions,
removal/rename, builtin-record/user-record interchange, BOOLEAN/numeric,
REAL-to-integral and resource fields remain excluded. Joint/Cartesian model
changes now follow [model-backed variable transfers](kinematic-variable-transfers.md)
when explicit robot context is supplied. With no robot service, they retain
incompatible status 3. Configured context/data/model failures preserve outputs.

## Outer record ARRAY prefixes

Outer source and receiver ARRAYs need equal logical rank, from one through three.
Their names, layouts and dimensions may differ. The operation copies the smaller
row-major terminal-record count and preserves every unused receiver cell. Each
selected record converts independently into the receiver's record schema.

This prefix behavior differs from ordinary [source record conversion](record-schema-conversions.md),
which requires matching ARRAY logical dimensions. Inner ARRAY fields within one
record are converted as complete field values and still require matching dimensions.
Ignored numeric source-tail fields are not read as values. Structural/schema and
original STRING capacity checks still cover source storage under the existing
capture contract.

## Missing data and publication

A compatible whole missing record or ARRAY container clears that receiver
container. Partial missing scalar/record fields remain missing. Missing ARRAY
components in a changed field layout rebuild as corresponding missing terminal
data. A representation-changing positional field itself still requires complete
source geometry; missing content never invents pose or joint values.

Only missing data copied by the transfer contributes to status 12311; untouched
receiver tails and ignored source tails do not. Unknown BYTE data remains distinct
from missing data, can be copied as BYTE, and cannot be promoted into an invented
number. SHORT sentinel normalization remains a private checked operation.

Known source domains are checked before receiver truncation, narrowing or
promotion. The entire record or selected prefix is staged before publishing data,
entry, cache ID or status. Late validation failures preserve all those outputs;
earlier source/selector effects remain. Successful known data replacement retains
receiver and child storage so existing captured references stay attached.
The existing 32767-scalar-leaf and 64-schema-level limits remain.

SET captures its independent typed source before later output selectors. GET
resolves and captures its named source after output selectors. Current module,
attached owners, explicit bindings, static fields/elements and PATH-node data use
the same conversion. Routine locals are not discovered through a string path.
Protected fields, overlap checks, resource restrictions and FOR guards remain.

## Status, persistence and reports

The existing statuses remain: 0 success, 1 lookup failure, 3 incompatible type/rank
and 12311 copied missing data. Type/schema compatibility precedes missing-data
propagation. Successful normalized lookups reuse context-local cache IDs; errors
do not allocate new IDs. JSON preserves resulting concrete schemas and values,
but cache IDs, references and live stacks are not persisted.

Reports add record_variable_transfer_policy alongside variable_transfer_policy
and existing service-operation sites. Generic runtime transfer helpers remain
exact unless explicitly opted into this Pythonic record policy; ordinary checked
helpers, BYNAME, linked signatures and raw callback results keep their contracts.
Native cache encodings, controller status mapping, ABI equivalence and public
strict mode remain outside this feature.

See the [semantic ledger](semantics/record_variable_transfer_semantics.json),
[authored tests](../tests/test_record_variable_transfers.py),
[field](../examples/record_variable_fields.kl),
[prefix](../examples/record_variable_prefix.kl),
[missing-data](../examples/record_variable_missing.kl),
[geometry](../examples/record_variable_geometry.kl),
[attached owner](../examples/record_variable_owner_project/main.kl) and
[generic receiver](../examples/record_variable_receiver_project/main.kl) examples.
