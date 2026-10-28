# BYTE and SHORT FOR counters

Pythonic mode supports BYTE and SHORT scalar storage as FOR counters, alongside
INTEGER. Counters can be declared globals, fresh routine locals, STRUCTURE
fields, ARRAY elements or fields resolved through USING, including isolated
[private computed captures](private-using-counters.md).

```karel
total=0
FOR counter=254 TO 255 DO
  total=total+counter
ENDFOR
```

For a BYTE `counter`, this totals 509 and leaves its contents unknown. The loop
does not write 256 after its last iteration. This is a deliberate Pythonic
extension; the manual and preserved legacy translator retain INTEGER-only
counter restrictions.

## Bounds and cleanup

| Counter type | Initialized initial/final domain | Value after loop exit |
| --- | --- | --- |
| BYTE | 0..255 | Unknown BYTE marker |
| SHORT | -32768..32766 | Uninitialized marker |
| INTEGER | Existing checked INTEGER rules | Uninitialized marker |

Both narrow bounds must be integral expressions in the counter's initialized
domain. REAL and BOOLEAN expressions do not become integral bounds. Out-of-range
values fail without wrapping, clamping, truncating or turning into an empty
loop. In particular, SHORT 32767 is a storage-clearing sentinel and is rejected
as either bound, rather than silently becoming a missing counter.

The reference is captured once before the initial expression. Its checked
initial assignment occurs before the final expression, which can observe that
new value. The final expression evaluates once. TO/DOWNTO are inclusive, using
the ordinary captured range iterator; only actual iteration values are written.
BYTE 0 and 255, and SHORT -32768 and 32766, are valid endpoints in either
direction. A valid zero-iteration loop still initializes and clears its counter.

Initial expression or initial domain failure leaves the previous selected cell
unchanged. No cleanup frame has been registered at that point. After initial
assignment succeeds, final expression/domain failure clears the counter. Earlier
completed effects remain on either failure.

A narrow-specific captured reference wrapper performs checked iteration writes
and cleanup. BYTE cleanup writes the existing unknown BYTE marker; SHORT cleanup
writes the existing uninitialized marker. Ordinary `Reference.clear()` behavior
is unchanged. BYTE `UNINIT` queries remain prohibited; attempting to read the
unknown BYTE after cleanup still fails. SHORT initialization queries retain
their ordinary behavior.

## Alias and effect protection

The existing [captured counter proof](reference-for-counters.md) protects the
complete declared or private capture root. Writes to another field or index of
that same root, nested counter reuse, READ/conversion/service output aliases and
potentially writable routine references remain rejected. Separate storage roots
can own independent nested counters.

An exact matching bare BYTE or SHORT actual retains reference passing. A formal
proved readonly can observe an active counter; a potentially writable matching
formal is rejected. Existing INTEGER/REAL promotions, mismatched integral
conversions and grouped value arguments own detached private cells and can be
written there. Their formal writes do not propagate to the caller's counter;
explicit global writes and transitive matching-reference writes still do.

Global BYTE/SHORT variables follow the scalar INTEGER external-call policy.
Aggregate roots containing narrow fields/elements retain the conservative guard
against unknown external global writes. Fresh local and isolated private roots
remain separate storage. Parameterized routines still require a fresh local or
isolated private counter root; their formal and nonlocal declared roots remain
restricted.

Handler writes and retained writable private aliases keep their existing guards.
Connected timers still require ordinary declared INTEGER storage; narrow
counters do not widen timer or other INTEGER output-reference interfaces.
CONFIG-domain fields, readonly POSITION descendants, resource roots and direct
function-result counter syntax remain excluded.

## Jumps, suspension and failures

Structured code and the label dispatcher share the same captured scalar
reference. Changing an index variable does not retarget the counter or its
cleanup. Same-active-loop jumps retain the current counter, iterator and final
bound. Leaving loops clears selected counters from inner to outer. Direct entry
to a new FOR or USING scope remains rejected.

RETURN captures its scalar value or independent aggregate snapshot before
cleanup. ABORT, errors, budget exhaustion and stop clear every successfully
initialized active counter using its own marker. Pause/resume retains live
references and iteration state. Stopping during an initial expression preserves
the previous selected cell; stopping during a final expression clears the
already initialized one. Siblings and completed outside effects remain intact.

Context JSON preserves ordinary declared narrow values and their missing
markers. It does not serialize captured references, iterators or suspended
stacks. Private USING counter storage is not published as a new global variable.

## Reports and verification

Narrow `reference_for_counters` rows add `counter_type`, `bound_domain` and
`cleanup_marker` to the existing selector/root/capture metadata. Private roots
retain null public provenance and their separate lexical protection identity.
Existing INTEGER rows retain their previous contract.

The [authored tests](../tests/test_narrow_for.py) cover domain endpoints, initial
and final rejection, every supported storage form, alias/effect guards, both
engines, GOTO, RETURN snapshots, cooperative lifetime, linked routines and JSON
roundtrips. These prove the stated offline Pythonic policy, separately from
native compiler or controller evidence.
