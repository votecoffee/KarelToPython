# Built-in and user record bridges

Pythonic source values can convert between a user STRUCTURE and a built-in data
record when their complete field-name sets match. Field order and the user type
name may differ. This explicit Pythonic extension helps reuse ordinary structured
data across typed interfaces; it is not native compiler, packed-layout or
controller-equivalence evidence. Strict mode remains a future milestone.

```karel
TYPE point_data=STRUCTURE z:REAL y:REAL x:REAL ENDSTRUCTURE
VAR source,copy:point_data vector:VECTOR
BEGIN
  source.x=1 source.y=2 source.z=3
  vector=source
  copy=vector
END
```

## Supported data and boundaries

| Built-in | Required fields |
| --- | --- |
| VECTOR | X, Y, Z |
| CONFIG | Three CFG_TURN_NO fields and four CFG Boolean fields |
| XYZWPR | X, Y, Z, W, P, R and CONFIG_DATA |
| XYZWPREXT | XYZWPR fields plus EXT1, EXT2, EXT3 |
| POSITION | NORMAL, ORIENT, APPROACH, LOCATION and CONFIG_DATA |
| COMMON_ASSOC | SEGTERMTYPE, SEGDECELTOL, SEGRELACCEL, SEGTIMESHFT |
| GROUP_ASSOC | SEGRELSPEED, SEGMOTYPE, SEGORIENTYPE, SEGBREAK |

Nested fields may themselves bridge compatible built-in/user records. Matching
logical ARRAY dimensions use the existing named/flat/nested schema conversion
rules. Numeric fields retain checked integral-family conversions and promotion
to REAL; STRING capacities retain existing truncation/widening rules. There is
no implicit REAL-to-integral conversion, BOOLEAN truthiness, field renaming,
field addition/removal, resize or logical reshape.

These bridges apply at whole assignment, ordinary routine argument and RETURN
boundaries, including linked calls with exact declared signatures. They also
apply to GET_VAR/SET_VAR whole records and selected same-rank ARRAY prefixes.
Variable transfers keep their existing missing-container, partial-prefix,
cache/status and overlap rules; unselected receiver tails remain unchanged.

## Capture, ownership and publication

A schema-changing argument owns private data, including a bare source argument.
Changing it never copies back into its source. Exact same-type bare arguments
retain their normal reference behavior. RETURN values are independent copies.
The RHS is captured and converted before assignment selectors or later arguments
run. Every selected field is checked before publishing receiver data.

Assignments and variable transfers retain existing receiver/descendant storage
so captured aliases stay attached. Private converted arguments survive ordinary
pause/resume and clean up with their frame. Source POSITION orientation fields
remain recursively read-only. A user-record copy of orientation data is private;
it grants no writable alias into the original POSITION.

BYNAME, linked declarations/definitions, raw external callback results and generic
checked/value helpers keep exact schemas. A source function may explicitly
RETURN a converted value; an untyped host callback cannot silently return a
structurally similar record in place of its declared builtin result.

## Domains, missing data and geometry

All selected source domains are validated before receiver conversion. CONFIG
turn numbers remain in -8..7, including when converting CONFIG to a user record;
that outgoing conversion cannot erase invalid source contents. Association
BOOLEAN fields remain actual Booleans. Missing scalar leaves stay missing where
the destination's ordinary data policy allows them. Unknown BYTE contents cannot
be promoted into numbers.

Constructing POSITION from a present user record requires complete location,
configuration and proper unit, orthogonal, right-handed orientation columns.
Invalid or partial geometry fails before receiver publication. Copying a partial
POSITION outward into user data remains a checked private data copy. Existing
variable-transfer whole-missing-container rules remain unchanged.

Mixed user-record trees can contain these bridges alongside explicit-model
joint/Cartesian conversions. The complete selected data, CONFIG domains and any
constructed POSITION geometry are preflighted before invoking a model adapter.
Missing robot context still fails; no frame, tool, geometry or external-axis
mapping is discovered. Earlier unrelated host effects are not rolled back.

## Persistence, limits and verification

Existing JSON and portable VR archives retain concrete receiver schemas and
values, including partial scalar data. They persist no private references,
callbacks, suspended frames or native layouts. Existing 32,767 scalar-leaf,
64-schema-level and one-through-three ARRAY-dimension bounds remain active.
Resources and resource fields stay outside ordinary data conversion.

The [authored tests](../tests/test_record_bridges.py) cover all seven builtin
families, private/reference ownership, arrays, routine boundaries, variable
prefixes, geometry/domain failures, mixed model plans, exact-interface guards
and JSON/VR replay. Four runnable examples and two linked projects provide
independent expected snapshots and full saved-variable rows.

```console
python -m karel2py examples/record_bridge_vectors.kl -o bridge.py
python bridge.py --state-out bridge-state.json
python bridge.py --context bridge-state.json
```

No native controller or strict-mode validation is claimed.
