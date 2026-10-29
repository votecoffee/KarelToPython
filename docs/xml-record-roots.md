# Built-in record roots for XML_SETVAR

Pythonic XML_SETVAR accepts explicit VECTOR, CONFIG, XYZWPR, XYZWPREXT and POSITION
record roots alongside user STRUCTURE roots. The root may be a declared global,
supplied binding, attached program's record, selected ARRAY element or static
record field. Existing [aggregate attribute paths](xml-aggregate-paths.md) and
scalar conversion/status rules apply.

```xml
<item x="7" y="8" z="9"/>
```

```karel
XML_SETVAR(input_file,'','direction',status)
```

When `direction` is a declared VECTOR, these attributes initialize its three
REAL fields. For a POSITION root, writable location uses attributes such as
`location.x`. A pose's CONFIG fields use paths such as
`config_data.cfg_turn_no1`.

All values are staged through existing typed field references before publication.
Recursive POSITION NORMAL, ORIENT and APPROACH descendants remain readonly.
CONFIG turn values remain limited to -8 through 7. A late protected-field,
unknown-field, duplicate-cell, capacity or domain error preserves every original
field. Successful replacement keeps record/child identities and retained aliases.

Unmentioned data remains unchanged, including unknown leaves. Initializing a
POSITION location does not provide orientation, CONFIG, units, calibration or
robot context. A complete proper orientation must come from existing supported
source data or explicitly supplied context before geometry needs it. No inferred
model, physical motion or controller schema is introduced.

Scalar, whole ARRAY, JOINTPOS, FILE, PATH and QUEUE_TYPE roots remain invalid
targets with status 2. A record stored inside a supported ARRAY/PATH selection
can still be resolved by the existing static path rules. The XML scanner's
registration, read-only FILE, ASCII, namespace and lifetime restrictions remain.

`xml_record_root_policy` and `xml_input_policy` describe supported roots and
protection. The [authored example](../examples/xml_record_roots.kl) initializes an
explicit extended pose from supplied XML. Public strict mode and native XML
parser/status equivalence remain separate future work.
