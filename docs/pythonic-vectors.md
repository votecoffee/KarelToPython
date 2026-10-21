# Pythonic vector expressions

Since 0.62.0, Pythonic mode supports `VEC(x,y,z)` construction, unary VECTOR
signs and left-associated chains of cross/dot products. Components use checked
Python floats. The existing VECTOR arithmetic, value/reference and storage
rules continue to apply.

```karel
PROGRAM VECTORS
VAR offset,axis,crossed,opposite: VECTOR
length,triple: REAL
BEGIN
  offset=VEC(3,4,0)
  axis=VEC(0,0,2)
  crossed=offset#axis
  opposite=-crossed
  length=SQRT(offset@offset)
  triple=offset#axis@VEC(1,2,0)
  WRITE('length=',length::0::1,', triple=',triple::0::1,CR)
END VECTORS
```

This produces `CROSSED=(8,-6,0)`, `OPPOSITE=(-8,6,0)`, `LENGTH=5` and
`TRIPLE=-4`. WRITE records `length= 5.0, triple= -4.0\n`. See the
[authored example](../examples/pythonic_vectors.kl) for constructor calls with
effectful arguments and writable private VECTOR/component parameters.

## Construction and names

`VEC` accepts three INTEGER/REAL expressions in X, Y, Z order. Narrow integer
elements also promote through the existing numeric rules. Values must be
initialized and finite; BOOLEANs and other aggregates are rejected. Each call
creates fresh writable VECTOR storage. Ordinary destination assignment preserves
captured field references and independent-copy behavior.

Arguments evaluate once, left to right, using the existing
[evaluation rules](evaluation-order.md). A failure retains earlier effects,
skips later evaluation, performs no final assignment and unwinds routine frames.
Earlier argument mutations of the destination remain. Numeric promotion checks
occur at their existing expression positions; constructor component validation
follows argument capture.

An explicitly declared internal routine named `VEC` takes precedence over this
constructor, including its ordinary arity, result type and effect checks. Its
calls are reported as routine calls. Existing `VEC` storage/type names remain
available; explicit constructor calls use expression-call context when there
is no internal routine of that name. Bare `VEC` does not invoke the constructor.

Constructed vectors can be assigned to VECTOR variables, alias types, fields
and elements, returned from functions, passed as writable private value
arguments and used in arithmetic. `VEC(1,2,3).x` reads a component; passing that
component to a writable REAL formal refers to private constructed storage.
Whole VECTOR values retain complete-initialization and ownership checks.

## Signs and product chains

Unary `+vector` and `-vector` produce checked independent VECTOR values.
Unary plus copies the components; unary minus reverses their signs. Every
component must be known, initialized and finite. Source storage and POSITION
orientation protections remain unchanged.

Cross `#` and dot `@` have precedence above multiplication/division, which
precede unary signs and addition/subtraction. This preserves the existing
KAREL-oriented unary precedence. Products at the same level associate left to
right: `a#b#c` means `(a#b)#c`, and `a#b@c` means `(a#b)@c`. Parentheses can
select `a#(b#c)` instead. Intermediate result types are checked, so `a@b#c`
is rejected because the initial dot product is REAL.

Operators capture VECTOR values before evaluating later operands. Chaining
introduces no live alias to an earlier intermediate. Rounded float arithmetic
and zero/parallel cross products follow the existing Pythonic numeric rules.
Division still rejects zero denominators, and non-finite results are errors.

For length, `SQRT(v@v)` composes the existing dot and square-root operations.
It uses ordinary float products/sums; large components can overflow and tiny
products can underflow. This expression provides no scaled norm algorithm.

## Evidence and boundaries

The reviewed [reference edition](references.md) uses three-component `VEC`
notation in arithmetic examples on PDF page 85 and describes VECTOR fields on
page 600. The precedence table is on page 81. This release defines an explicit
offline constructor interpretation and chooses unary signs and left association
for Pythonic mode. These choices have authored execution tests; they establish
no new native constructor ABI, operator rounding or controller acceptance.

POS construction, frame transforms, robot kinematics, ordered VECTOR relations,
VECTOR-by-VECTOR multiplication/division and aggregate CONST values remain
outside this subset. Strict mode remains a future milestone; its conservative
constructor/sign/chain guards are retained internally.

`vector_constructors` records each fallback constructor's body, physical
line/column, X/Y/Z argument order and independent-value/evaluation flags.
`vector_policy` describes construction, name priority, signs and association.
