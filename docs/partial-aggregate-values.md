# Partial aggregate values

Pythonic mode copies resource-free ARRAY, user STRUCTURE, built-in record and
JOINTPOS values while preserving missing scalar contents. A partly initialized
value can be assigned, returned from a routine, or passed as an independent
value argument. Missing fields are not filled with zeros or robot defaults.

```karel
PROGRAM partial_example
TYPE item_t = STRUCTURE count:INTEGER label:STRING[8] ENDSTRUCTURE
VAR source,copy:item_t
BEGIN
  source.count=7
  copy=source
  copy.label='ready'
END partial_example
```

The copy has count 7 and label ready; the source label remains uninitialized.
This is an explicit Pythonic convention. Native aggregate initialization and
copy equivalence have not been established. Public strict mode remains future
work; preserved internal strict regressions retain their previous restrictions.

## Transfer boundaries

The same checked copy applies to whole assignments, record/ARRAY elements,
resource-free aggregate routine results and grouped value arguments. A direct
storage argument such as `consume(source)` retains its ordinary reference
semantics. A grouped argument such as `consume((source))` owns private writable
storage, including any missing leaves. Changing the private copy cannot change
its source. Function results also own their data.

A source value is captured once before later argument or assignment-target
selectors execute. A valid partial value therefore permits those later effects.
An invalid known leaf or layout still fails before its target selector executes.
Validation prepares the complete copied value before destination storage changes;
prior routine side effects are retained if validation fails. Assignment uses the
existing destination storage, preserving captured aliases to its descendants.

These rules keep exact nominal identities and concrete dimensions. Wildcard
formal/result shapes resolve through the existing checked concrete-shape rules;
no array resizing, flattening, identity erasure or new implicit conversion is
introduced by the generic copy contract. Separate [numeric ARRAY conversions](numeric-arrays.md)
retain missing leaves while checking every known source and receiver domain.
POSITION orientation columns remain read-only source storage,
including after partial copies. Detached standalone VECTOR copies remain writable.

## Missing and known leaves

| Contents | Copy behavior |
| --- | --- |
| UNINITIALIZED scalar | Retain the same missing marker |
| UNKNOWN_BYTE in a BYTE leaf | Retain the unknown-byte marker |
| UNKNOWN_BYTE in any other leaf | Reject |
| SHORT 32767 sentinel | Normalize to UNINITIALIZED, as ordinary SHORT storage does |
| Known scalar | Validate its declared type, range and finite/ASCII rules |

All known fields are checked even when another field is missing. INTEGER bounds
and MAXINT exclusion, Boolean type checks, BYTE/SHORT bounds, finite REAL values,
STRING capacities and ASCII, and CONFIG turn-number/Boolean rules still apply.
STRING data exceeding an aggregate field's declared capacity is rejected rather
than silently truncated. Partial CONFIG fields can be copied only when every
known field is valid.

Aggregate containers themselves must remain concrete typed storage. A marker
cannot replace an entire nested ARRAY, record or JOINTPOS. A partial record still
has all declared fields, a partial ARRAY retains every element slot, and a
partial joint retains its complete declared axis list. Missing scalar leaves are
different from malformed or absent aggregate storage.

## Validation limits

Before allocating a copy, the runtime checks a resource-free concrete schema,
canonical ASCII STRUCTURE/field identifiers, distinct declared fields, exact
nominal types and field layouts. It validates physical ARRAY shapes and list
lengths, at most three logical ARRAY dimensions, exact joint widths, and ordinary
STRING capacities. Malformed host objects, cyclic storage and embedded FILE,
PATH or QUEUE_TYPE fields are rejected.

The existing 32767-scalar-leaf limit applies to the full value, including nested
records and joints. Copy schemas are additionally bounded to 64 levels, counting
aggregate and scalar type nodes. No scalar missing marker bypasses these layout
or size checks. Copies detach each child independently, so repeated host aliases
do not become shared mutable children in the result.

Top-level FILE, PATH and QUEUE_TYPE retain their existing resource contracts.
This convention does not add aggregate resource assignment, whole ARRAY/user
STRUCTURE UNINIT queries, BYTE initialization queries or new source type forms.

## Reading and geometry

Copying an unknown leaf does not make it readable. Scalar loads and expressions
still raise when they require UNINITIALIZED or UNKNOWN_BYTE. Existing permitted
UNINIT queries retain their documented type rules.

Geometry and kinematics consume complete values. INV, FRAME, pose composition,
pose comparison/conversion, VECTOR operators and joint conversion still reject
missing components with KarelRuntimeError before numeric calculations or output
publication. CONFIG text formatting and pose construction likewise require the
complete CONFIG they consume. This prevents Python truthiness or arithmetic from
turning missing markers into plausible robot data. No physical robot context,
reachability or controller acceptance is implied.

Existing typed JSON and variable/archive formats continue to retain explicit
missing markers. This feature changes checked Pythonic value transfers; it does
not serialize live resources, references or execution stacks. The authored
regressions are in `tests/test_partial_aggregate_values.py`, alongside retained
strict rejection cases and updated Pythonic copy/return examples.
