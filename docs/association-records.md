# COMMON_ASSOC and GROUP_ASSOC data

Pythonic source supports the association records documented in the older
4.30/4.31 reference. They are checked data values with named scalar fields.
The runtime does not discover groups, record a motion environment or apply
these fields to a trajectory. Strict mode remains future work.

| Type | Fields in declaration and I/O order |
| --- | --- |
| COMMON_ASSOC | INTEGER SEGTERMTYPE, SEGDECELTOL, SEGRELACCEL, SEGTIMESHFT |
| GROUP_ASSOC | INTEGER SEGRELSPEED, SEGMOTYPE, SEGORIENTYPE; BOOLEAN SEGBREAK |

The spelling is **SEGORIENTYPE**. Preserve the existing INTEGER storage domain
and exact BOOLEAN values. No guessed native bit widths, option enums or range
clamping are applied. Thus a stored SEGRELSPEED value is data, rather than an
instruction to run a robot at that percentage. Fields initially contain the
ordinary missing marker; native environment defaults are not inferred.

```karel
VAR common:COMMON_ASSOC axes:GROUP_ASSOC IN GROUP[2]
-- Inside BEGIN:
common.segtermtype=1
axes.segmotype=7
axes.segbreak=FALSE
```

GROUP_ASSOC accepts the existing constant `IN GROUP[n]` metadata in 1..32.
It does not acquire ownership or create robot context. COMMON_ASSOC has no group
qualifier. Transparent aliases can be defined from group-qualified GROUP_ASSOC;
generic aliases retain the existing source syntax restrictions.

## Storage, values and interfaces

Use the types in variables, routine locals, transparent aliases, ARRAY elements,
user STRUCTURE fields, custom PATH NODEDATA/PATHHEADER structures and source
results. Whole records and arrays use existing checked partial-data copies,
exact schemas, allocation bounds and independent grouped/result values.
Whole-record UNINIT validates all known fields and reports any missing field;
it does not hide malformed known data behind another missing member.

A bare same-type whole record or complete ARRAY reference borrows its storage.
**Every association scalar-field routine argument is a private value**, including
INTEGER and BOOLEAN fields, captured USING names, indexed receivers and linked
calls. A callee can change that argument without changing the original field.
Selectors and argument values are evaluated once in normal order. Grouped whole
records and ordinary prefix arguments remain independent values; explicit
[live BYNAME ARRAY prefixes](array-prefix-references.md) retain their existing
separate policy.

Whole-record BYNAME remains exact and borrowed. BYNAME of a scalar association
field and generic output/entry/status aliases to those fields are rejected.
Association-field FOR counters and connected timers also remain excluded.
Direct field assignment and supported READ targets are writable. Use ordinary
scalar storage for procedure outputs, then assign it into the record.

## Input, transfers and inspection

READ accepts individual fields, whole association records, nested records,
ARRAYs, prefixes and custom PATH data. It captures declared storage before input
and validates the entire response before publication. WRITE expands the four
fields in the table's order. Text/binary FILEs keep their existing INTEGER and
BOOLEAN formats; there is no compact native association-word format.

GET_VAR/SET_VAR transfer exact whole association data and compatible ordinary
containers through their existing snapshot/publication rules. Explicit *named*
field paths may copy scalar data to/from ordinary storage. Those statement
transfers validate the association field schema without exposing a live field
alias. Missing copied data retains status 12311; metadata overlap and cache
publication guards remain in effect.

CREATE_VAR accepts COMMON_ASSOC, GROUP_ASSOC, aliases and ARRAY OF forms with
existing allocation, group metadata, rename and lifetime rules. Each record
reserves four scalar leaves. VAR_INFO reports COMMON_ASSOC code 20 or GROUP_ASSOC
code 30, including logical ARRAY dimensions. These documented type labels do not
establish native variable-table IDs or binary layout.

XML_SETVAR accepts checked association roots and nested data through the existing
ASCII XML input model. Invalid scalar values preserve the record. XML output
remains a separate unsupported feature.

## PATHs, saving and compatibility

Custom node/header structures can contain either association type. Source PATH
copying, explicit whole-PATH variable transfers, logical JSON/VR archives,
collection arrays and scalar I/O retain the fields. NODE_SIZE reports ordinary
portable widths: COMMON_ASSOC 16 bytes, GROUP_ASSOC 13 bytes. A node containing
both has width 29, without native compact-packing claims.

The default and explicit STD_PTH_NODE schemas remain **NODE_POS only**, preserving
existing programs and saved data. Native GROUP_DATA/COMMON_DATA standard-node
fields, automatic association recording and motion-option application remain
outside this release. Define custom association-bearing NODEDATA when needed.

JSON and VR archives preserve ordinary typed values and creation metadata,
including missing fields; they do not save live aliases, callbacks, suspended
frames or robot bindings. No native ABI, compiler/source-form equivalence or
controller behavior is inferred from these offline records.

Authored examples cover [values and scalar arguments](../examples/association_record_values.kl),
[arrays and live prefixes](../examples/association_record_arrays.kl),
[PATH input](../examples/association_record_paths.kl) and
[dynamic inspection](../examples/association_record_variables.kl). Linked projects
cover [record/field interfaces](../examples/association_record_project/main.kl) and
[PATH/ARRAY interfaces](../examples/association_collection_project/main.kl), with
independent saved-variable and expected-input fixtures.
