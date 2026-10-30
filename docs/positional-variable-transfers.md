# Positional GET_VAR and SET_VAR conversions

Pythonic GET_VAR and SET_VAR can convert individual positional values across
POSITION, XYZWPR and XYZWPREXT representations. They also support differing
JOINTPOS widths using the existing zero-padding and zero-only narrowing policy.
This applies to individual values and same-rank ARRAY prefixes selected through explicit global,
attached-owner, field, ARRAY-element and supplied-binding paths.

```karel
GET_VAR(entry,'','EXTENDED_POINT',matrix_point,status)
SET_VAR(entry,'','PLAIN_POINT',matrix_point,status)
```

When the declared values have supported differing Cartesian representations,
the calls use the same checked [Cartesian conversion](cartesian-interfaces.md)
as ordinary source assignments/interfaces. Widening into XYZWPREXT supplies zero
external metadata; narrowing drops those three metadata slots. JOINTPOS widening
appends zero axes and narrowing requires every discarded axis to be zero.

## Validation, ownership and missing data

Changing representation requires a complete finite source, valid CONFIG and a
proper POSITION orientation matrix when applicable. No orientation, CONFIG or
nonzero joint-axis data is invented or discarded. An incomplete source or invalid
conversion raises before destination, entry or status publication. Exact same-type
copies retain the existing partial/missing-value behavior and status 12311.

SET captures independent typed source data before later status selectors. GET
resolves and snapshots its named source after output selectors. The conversion
then prepares an independent result before publication. Earlier argument effects
remain visible on failure. Successful replacement preserves destination record
and child identities, including retained aliases and POSITION protection.
Successful lookup/cache hints and ordinary status conventions remain unchanged.

[Positional ARRAY prefixes](positional-arrays.md) now change terminal representations
and checked joint widths while preserving receiver schema and unused tail.
Compatible user STRUCTURE fields now follow [record variable transfers](record-variable-transfers.md).
Selected positional elements
can also be converted individually. JOINTPOS-to-Cartesian pairs remain incompatible
with status 3 even when a robot model is supplied; perform an explicit source
kinematic conversion before transferring that result when needed.

These operations use no robot model, current state, frame/tool selection or
physical conversion. Existing overlap, CONFIG-subfield, readonly POSITION and
FOR-effect guards remain in force. Context JSON preserves concrete source and
receiver representations through the ordinary typed codecs.

The [authored example](../examples/positional_variable_transfers.kl) converts an
extended point through POSITION into a plain pose. Translation reports expose
`positional_variable_transfer_policy`. See the [general transfer contract](variable-transfers.md)
for lookup, missing data, numeric prefixes and resource boundaries. Strict mode
and native controller/ABI equivalence remain separate future work.
