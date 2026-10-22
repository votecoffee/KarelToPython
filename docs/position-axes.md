# Pythonic pose axis queries

Version 0.79.0 extends the base contract below with XYZWPREXT operands and
explicit external-axis metadata. The [offline service guide](offline-services.md)
defines the added conversions, propagation rules and remaining boundaries.

Since 0.73.0, `APPROACH(pose)` returns the positive Z axis and `ORIENT(pose)`
returns the positive Y axis as independent VECTOR values. Both accept complete
POSITION values. Pythonic mode also accepts XYZWPR under the existing rotation
convention.

```karel
PROGRAM POSITION_AXES
VAR cfg: CONFIG code: INTEGER p,moved: POSITION pose: XYZWPR app,side: VECTOR
BEGIN
  CNV_STR_CONF('N R U T, 0, 0, 0',cfg,code)
  pose=POS(10,20,30,0,90,0,cfg)
  p=pose
  app=APPROACH(p)
  side=ORIENT(pose)
  moved=p
  moved.location=moved.location+app*50+side*20
  app.x=9
  WRITE('moved=',moved.location.x::0::1,',',moved.location.y::0::1,',',moved.location.z::0::1,CR)
  WRITE('axes=',APPROACH(moved).x::0::1,',',ORIENT(p).y::0::1,CR)
END POSITION_AXES
```

The 90-degree Y rotation puts the positive Z axis at `(1,0,0)`, while positive Y
remains `(0,1,0)`. Adding 50 along Z and 20 along Y moves LOCATION from
`(10,20,30)` to `(60,40,30)`. Editing the detached `app` vector afterward leaves
the pose's protected orientation unchanged. Output is `moved= 60.0, 40.0, 30.0`
and `axes= 1.0, 1.0`, each followed by a newline.

The [authored example](../examples/pythonic_position_axes.kl) adds environment
metadata and has independent complete
[snapshot](../examples/pythonic_position_axes.expected.json) and
[output](../examples/pythonic_position_axes.write.expected.json) fixtures.

## Equivalent operations

| Function | POSITION equivalent | XYZWPR equivalent |
| --- | --- | --- |
| `APPROACH(p)` | Copy `p.APPROACH`. | Copy the third rotation column. |
| `ORIENT(p)` | Copy `p.ORIENT`. | Copy the second rotation column. |

XYZWPR uses the portable `R = Rz(r) Ry(p) Rx(w)` degree convention described in
[frame transforms](frame-transforms.md). POSITION uses its columns directly,
without Euler extraction. The result is an ordinary writable VECTOR with
independent storage. `change(APPROACH(p))` and `change(ORIENT(p).Y)` pass private
temporary values. Direct POSITION orientation writes and bare protected
orientation reference arguments remain blocked.

Type aliases, nested fields and array elements, constructors, internal function
results and [POSITION geometry results](position-geometry.md) are valid operands
when their resolved type is POSITION or XYZWPR. VECTOR results compose with
existing arithmetic, field reads, assignment, arguments and RETURN.

Internal routines named APPROACH or ORIENT retain their own signatures, types
and effects. Ordinary variables with these names remain usable. Environment
metadata records requirements without loading controller facilities.

## Validation, evaluation and reports

These functions require a complete, initialized, finite and structurally exact
pose, including CONFIG and LOCATION even though the returned axis does not use
them. This is the same explicit complete-value policy as frame geometry.
POSITION matrices must pass the existing unit-column, orthogonality and positive
determinant checks, each with absolute tolerance `1e-9`. Columns are copied
without normalization or matrix repair, so a tolerated small deviation remains
in the result. No orientation defaults are supplied.

The operand evaluates once. The result is computed and detached before later
expressions or assignment target functions run. A failure retains earlier
operand effects, skips later expressions and target effects, and leaves the
assignment destination unchanged. Ordinary active-FOR-counter checks and local
routine-frame cleanup apply.

Reports expose `position_axis_queries` with function, body, physical source
line/column, actual operand type, VECTOR result type and independent/evaluate-once
flags. `position_axis_policy` records the mapping, input checks, ownership and
remaining boundaries. Type inspection of result fields does not duplicate query
entries. Queries inside user routines report that routine's body name.

## Evidence boundary

The reviewed [reference edition](references.md), one-based PDF pages 311-312 and
470, defines POSITION APPROACH and ORIENT as the positive Z and Y axes and notes
the equivalent direct field access. XYZWPR acceptance, the complete-pose guard,
matrix tolerance and portable rotation convention are Pythonic choices.
Independent quaternion checks and authored fixtures establish offline behavior.

XYZWPREXT is supported; JOINTPOS uses supplied forward context under
[joint geometry](joint-geometry.md). VECTOR and scalar operands remain blocked.
Queries retain complete-pose checks and explicit context; controller acquisition,
frame discovery and native configuration validity remain unverified. Strict mode
remains a future milestone.
