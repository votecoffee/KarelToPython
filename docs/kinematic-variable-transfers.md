# Model-backed variable transfers

Pythonic GET_VAR and SET_VAR now convert joint/Cartesian values through an
explicitly supplied robot context. This includes individual values, same-rank
ARRAY prefixes and compatible user STRUCTURE fields, including nested ARRAYs.
The portable conventions match existing source model conversions.

With no robot service supplied, model-backed pairs remain incompatible with
status 3. A configured model/adapter still requires its selected frame/tool and,
for inverse conversion, supplied current joints. Nothing is discovered from a
controller, and the operation does not update robot state.

All selected source data and geometry are captured and validated before any
model call. Calls follow receiver field order and ARRAY row-major order. Results
remain private until the complete transfer succeeds. Receiver storage is rechecked
after callbacks and before publication. Failure leaves data, entry,
cache and status unchanged. Earlier explicit source/selector/adapter effects remain.
GET captures its named source after output selectors; SET captures independent
source data before later selectors.

Outer ARRAY dimensions may differ within the same logical rank. Copy the smaller
terminal count and preserve the receiver tail, including explicit adapter updates
to unselected tail cells. Inner ARRAY fields of a record
retain matching logical dimensions. Only copied missing data sets status 12311;
unselected receiver tails and ignored source numeric tails do not contribute.

Whole missing compatible record containers retain ordinary missing propagation;
missing ordinary fields survive conversion. Every selected model geometry value
must be complete and finite. Missing whole positional ARRAY input is rejected.
Original STRING capacities, numeric domains, schema limits and geometric checks
run before model calls. No missing geometry is replaced by a default pose.

Each call uses the root caller's group and current explicit selected frame/tool
and inverse seed. There is no hidden seed chaining, new checkpoint or physical
motion. Sticky ABORT prevents later calls and output publication. Ordinary alias,
readonly CONFIG/POSITION, overlap and FOR guards remain in force. Known receiver
storage identities remain stable after successful publication.

JSON retains concrete schemas, model data and resulting values through existing
codecs; callbacks, cache IDs and live references are not persisted. Generic
variable_transfer helpers remain context-free even with existing conversion
flags. Public strict mode and native ABI/controller equivalence remain unverified.

Reports expose kinematic_variable_transfer_policy alongside existing service
operation sites and scalar model request outcomes. See the
[authored regressions](../tests/test_kinematic_variable_transfers.py),
[record transfers](record-variable-transfers.md) and
[positional transfers](positional-variable-transfers.md). The
[semantic ledger](semantics/kinematic_variable_transfer_semantics.json) records
this extension. Authored examples cover [scalar round trips](../examples/model_variable_scalar.kl),
[prefixes](../examples/model_variable_prefix.kl), [record fields](../examples/model_variable_record.kl),
[partial data](../examples/model_variable_missing.kl), [attached owners](../examples/model_variable_owner_project/main.kl)
and [generic linked receivers](../examples/model_variable_array_project/main.kl).
