# Whole POSITION input

Pythonic READ now accepts complete POSITION destinations, including positions
inside data ARRAYs, user records, captured row/plane targets, borrowed routine
arguments and existing PATH headers/nodes. This fills the remaining positional
gap in [whole data READ](aggregate-input.md). It is an authored portable transport,
not a native POSITION record layout or controller input implementation.

```karel
VAR point:POSITION
BEGIN
  READ(point)
END
```

Supply this flat typed response for an identity orientation at (10,20,30):

```json
[1,0,0, 0,1,0, 0,0,1, 10,20,30, 0,0,0, false,false,false,false]
```

The destination must already have its declared containers. Missing scalar leaves
are accepted, as in a fresh POSITION declaration. Missing nested vectors, CONFIG
or ARRAY containers fail before input; READ does not allocate replacement shapes.

## Scalar order and capture

Each POSITION uses 19 fields in the existing aggregate WRITE order:

1. NORMAL X, Y, Z.
2. ORIENT X, Y, Z.
3. APPROACH X, Y, Z.
4. LOCATION X, Y, Z.
5. CONFIG turn numbers 1, 2, 3, then FLIP, LEFT, UP and FRONT flags.

ARRAYs remain row-major; user fields retain declaration order. Root PATH input
captures its supplied header first, then existing nodes. Default STD_PTH_NODE now
accepts its NODE_POS data. Node count is unchanged. CR applies after complete
source items; one POSITION contributes 19 scalar offsets. Existing 1024-field/CR
and schema-depth limits still apply.

Each destination captures its original scalar cells before later selectors and
format calls. A callback or source function replacing a root, vector or PATH node
does not retarget those captures. Completed source/callback effects remain visible.
Repeated positions publish in source order, with the later occurrence winning.
A complete position capture cannot be split, reordered or partially submitted to
the READ helpers. Capture objects do not create source orientation aliases.

## Geometry and publication

Validate the entire response before publishing any destination, including ordinary
scalar siblings and other positions in the same READ. Numbers must be finite;
CONFIG keeps its INTEGER -8..7 turn bounds and exact BOOLEAN flags.

Input rotation columns must be unit length, mutually orthogonal and right-handed
within a 1e-6 transport tolerance. This accepts bounded decimal/float32 rounding.
After admission, normalize NORMAL, remove its projection from ORIENT and normalize
ORIENT, then compute APPROACH as their cross product. Validate the result with
the existing strict frame checks. Larger errors, zero columns, reflections and
malformed values are rejected; no arbitrary orientation or CONFIG is inferred.
This normalization is specific to whole POSITION input. Other matrix operations
retain their existing validation rules.

There are no source callbacks or cooperative yields between final validation and
scalar publication. Existing root/vector identities and orientation protection
remain. Direct `READ(point.normal)`, orientation-field assignments and writable
orientation arguments are still rejected.

## Transports and lifetime

Typed callbacks, CLI JSON values and TextInput use the flat scalar order above.
Uniform formats apply through the existing per-kind rules. Explicit text/binary
FILE, serial, pipe and keyboard input use the same captured destinations and pose
validation. Binary input uses twelve REALs, three INTEGERs and four BOOLEANs with
ordinary scalar widths and selected byte order; the default is 64 bytes. There is
no native padding, framing or robot model lookup.

Invalid geometry leaves the READ destinations unchanged. Binary FILE failures
restore the cursor; text/cooperative transports commit their cursor only after
successful validation. An exact TextInput adapter restores its parse cursor on
failed whole POSITION input. Arbitrary callback side effects are retained.
Pause/resume keeps the captures; cancellation, stop and abort use the existing
pending-input and task cleanup rules. Completed values use ordinary context JSON;
live captures and suspended input are not persisted.

Reports add `position_input_policy`. See the [typed input](../examples/position_read_values.kl),
[prefix ARRAY](../examples/position_read_array.kl), [PATH](../examples/position_read_path.kl),
[binary input](../examples/position_read_binary.kl),
[linked POSITION](../examples/position_input_project/lib.kl),
[linked PATH](../examples/position_input_path_project/lib.kl),
[regressions](../tests/test_position_input.py) and
[semantic ledger](semantics/position_input_semantics.json). Strict mode remains future work.
