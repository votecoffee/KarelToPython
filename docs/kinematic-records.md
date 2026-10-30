# Model-backed geometry inside STRUCTURE values

Pythonic assignments, ordinary routine arguments and RETURN can convert compatible
user STRUCTURE trees containing JOINTPOS and POSITION/XYZWPR/XYZWPREXT field
changes. This includes nested records, ARRAY fields and whole record ARRAYs.
The operation uses the existing explicit scalar model/adaptor engine; it does
not discover robot context, move a robot or update supplied current state.

~~~karel
TYPE joints_t=STRUCTURE point:JOINTPOS2 label:STRING[8] ENDSTRUCTURE
     pose_t=STRUCTURE label:STRING[3] point:POSITION ENDSTRUCTURE
VAR original:joints_t result:pose_t
BEGIN
  -- Supply complete original.point and explicit robot model/context.
  result=original
END
~~~

Both records have the same field-name set. result retains its declared field
order, bounded STRING capacity and POSITION representation. Supported ordinary
fields follow [context-free record conversion](record-schema-conversions.md).
Model-backed changes add no field renaming, additions, removal, resource fields,
builtin-record/user-record interchange, BOOLEAN coercion or REAL-to-integral
conversion. ARRAY logical dimensions must still match; receiver names and
flat/nested component layout may differ.

## Two-phase conversion

The RHS evaluates once. Before any adapter call, the runtime captures independent
source data, validates its declared schema and every known leaf, checks output
schema/allocation limits, completes every context-free field conversion, and
captures every model operand. Model operands must be complete and finite, with
proper POSITION rotation matrices. Ordinary missing scalar leaves and exact
partial pose/joint fields retain their existing partial-data rules.

A late malformed source field, overflowing numeric conversion or invalid matrix
therefore prevents all model calls. The existing 32767-scalar-leaf and
64-schema-level bounds apply before output allocation.

The runtime then executes model calls in receiver field declaration order,
depth-first, with logical row-major order within ARRAY fields. Different field
orders intentionally change this explicit adapter order. All operands were
captured before the first call, so host changes to source storage do not change
later captured operands. Output remains private until every conversion succeeds.

Model-specific widths, limits, solutions, selected context and returned values
are checked at each scalar call. A failure preserves the whole receiver and
skips later model calls, source arguments or destination selectors. Earlier
explicit source and host-adapter effects remain; they are not retried or rolled
back. A solver failure is not proof that a pose is geometrically impossible.
Assignment retains the receiver and its nested child storage identities.

## Explicit robot context

Each model call uses the root caller's group, including in linked libraries,
with that group's currently supplied selected frame/tool and inverse seed.
Forward conversion requires an explicit forward adapter or model. Inverse
conversion requires supplied current joints. Receiver contents and earlier
converted fields never become implicit seeds. Existing native-width/nine-slot
model rules and exact custom-adapter result-width rules remain unchanged.

Adapter inputs are detached. An explicit adapter can replace context state;
later calls observe that change under the existing sequential scalar contract.
The engine does not silently change calibration, current joints or selections.
See [scalar interfaces](kinematic-interfaces.md) and
[model-backed ARRAYs](kinematic-arrays.md) for the underlying model contracts.

## Interfaces and lifecycle

Schema-changing arguments receive private writable data, with no copy-back.
Already compatible references retain their aliases. Exact forwarding or retained
handlers may reference private converted data; pause/resume retains it without
repeating conversion. Stop, abort and failures unwind ordinary frames and timer
claims. RETURN prepares its independent declared output before frame, counter
and timer cleanup. Computed USING can own that prepared result.

The operation is synchronous and introduces no intermediate handler checkpoint.
Sticky ABORT prevents later calls and publication even if an adapter catches the
abort or raises a later exception. BYNAME, generic checked/value/result helpers,
context-free record helpers, linked declarations/definitions and raw callback
result schemas retain their exact contracts. GET_VAR/SET_VAR do not gain implicit
model-backed record conversion.

Bare generic ARRAY source assignments use their actual borrowed receiver schema.
JSON stores concrete schemas, values and serializable supplied model state; it
does not persist private references, handlers, callbacks or suspended execution.
The authored examples use DONE guards for deterministic data replay.

## Reports and examples

Reports add kinematic_record_conversions sites with source/target schemas,
boundary, location, one-time capture, private ownership and geometry-preflight
metadata, plus kinematic_record_policy. Service observations contain one
value-free KINEMATIC_RECORD_ASSIGNMENT, KINEMATIC_RECORD_ARGUMENT or
KINEMATIC_RECORD_RETURN row with source line and completed/failed outcome.
These are offline software observations without native record ABI, motion,
controller or public strict-mode equivalence claims.

See the [semantic ledger](semantics/kinematic_record_semantics.json),
[authored regressions](../tests/test_kinematic_records.py),
[forward](../examples/kinematic_record_forward.kl),
[round-trip](../examples/kinematic_record_roundtrip.kl),
[nested layout](../examples/kinematic_record_nested.kl),
[lifetime](../examples/kinematic_record_lifetime.kl),
[linked caller-group](../examples/kinematic_record_project/main.kl) and
[generic receiver](../examples/kinematic_record_receiver_project/main.kl) examples.
