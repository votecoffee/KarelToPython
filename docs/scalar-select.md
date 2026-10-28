# Scalar SELECT

Pythonic translation accepts BOOLEAN, ASCII STRING and finite numeric scalar
selectors. Numeric selectors include INTEGER, BYTE, SHORT and REAL. This is a
deliberate portable extension: the manual's SELECT contract remains INTEGER-only,
and the preserved legacy translator/runtime retain that restriction.

```karel
SELECT ready OF
  CASE(TRUE): result=1
  CASE(FALSE): result=0
ENDSELECT

SELECT response OF
  CASE('ready','done'): result=42
  ELSE: result=0
ENDSELECT

SELECT measurement OF
  CASE(1,1.25): result=7
  CASE(2.5): result=9
  ELSE: result=0
ENDSELECT
```

## Comparison categories

| Selector | Allowed case constants | Comparison |
| --- | --- | --- |
| BOOLEAN | BOOLEAN only | Exact Boolean equality; ON/TRUE and OFF/FALSE are equivalent |
| STRING | ASCII STRING only | Case-sensitive equality, preserving all characters and spaces |
| INTEGER, BYTE, SHORT, REAL | INTEGER or finite REAL | Ordinary Python numeric equality, without rounding or tolerance |

BOOLEAN values never enter the numeric category. `CASE(TRUE)` cannot match a
numeric selector, and `CASE(1)` cannot match a BOOLEAN selector. Strings never
coerce to numbers or Boolean values. A mixed-category case table is rejected at
translation, including an invalid label after an earlier matching case.

Numeric INTEGER and REAL labels may mix. Thus integer 2 matches REAL 2.0; the
first matching clause wins if both labels occur. Integers remain integers during
comparison rather than being converted to floats. Integer expression limits
remain signed 32-bit, including existing expression-only MAXINT behavior.
Finite REAL values follow the ordinary Pythonic numeric policy: signed zeros
compare equal, and `0.3` need not equal `0.1+0.2`. There is no approximate match.
Subnormal and underflow results keep their existing Pythonic behavior. NaN and
infinities are rejected, rather than becoming ELSE/no-match outcomes.

Strings can be empty and contain up to 254 ASCII characters. No case folding,
trimming, escaping transformation or padding occurs during comparison. Existing
literal, concatenation and storage rules apply before SELECT; a selector is not
truncated to the length of a case constant.

## Constants, order and first match

The selector may be an ordinary scalar expression, field/element access or
typed function result. It evaluates once before dispatch. Its ordinary calls,
argument modes, effects, short-circuit behavior and active-counter guards remain
in force. Case labels must be literals or previously declared constant
expressions of the selector's category. Local constants retain lexical scope;
dynamic variables, function calls, USING fields, aggregates and resources do not
become case constants.

Clauses are checked in source order. Duplicates and overlapping label lists are
valid; only the first matching clause executes. An empty matching body still
counts as the selected clause and does not fall through. At most 1000 CASE
clauses are allowed, as before; a multi-value CASE remains one clause.

ELSE runs only when no case matches. An explicitly empty ELSE permits ordinary
continuation. Without ELSE, no match raises a source-located `KarelRuntimeError`
and preserves prior completed effects. Unknown/uninitialized selectors, invalid
types or nonfinite values fail before matching and do not run ELSE. Even an
unreachable case body retains normal translation-time checks.

## Control flow, cooperative tasks and state

Structured code, the label dispatcher, linked routines and cooperative tasks use
the same checked selection helper. A pause in a selector function resumes that
call; a pause in the selected body resumes that body without reevaluating the
selector. Stop, ABORT, errors, RETURN and budget exhaustion keep their ordinary
routine-frame and active-counter cleanup.

Existing Pythonic label-entry rules remain unchanged. A direct permitted jump
into a SELECT case skips the selector and dispatch, and runs that target's
suffix. An explicit sibling-case jump does not introduce implicit fall-through.
New FOR/USING scope entry and cross-body jumps remain rejected.

Context JSON preserves ordinary scalar inputs and outputs. It does not serialize
a suspended SELECT dispatch, iterator or Python stack. A new instance restored
from that data starts at its normal source entry; it does not resume a previous
case location.

## Runtime validation and reports

Generated Pythonic calls use
`select_case(value, cases, has_else, line, category=...)` with an explicit
`BOOLEAN`, `STRING` or `NUMERIC` category. The helper checks the selector and
every case value before the first comparison, so a malformed later clause cannot
hide behind an early match. Exact primitive types exclude custom equality
objects and Boolean/numeric leakage. The returned ordinal identifies the first
matching clause, or ELSE when present.

Inside Pythonic runtime mode, callers may omit `category` to infer it from a
valid scalar selector. Generated code always supplies the statically checked
category. Existing calls made outside Pythonic mode retain the INTEGER-only
helper contract and reject an explicit scalar category. `select_scalar` provides
the shared primitive/category validation; it does not execute source code.

Each `selects` report row retains case values, clause count, source location,
body and ELSE/no-match metadata, and adds:

| Field | Meaning |
| --- | --- |
| `selector_type` | Resolved source type, including BYTE/SHORT or STRING capacity |
| `comparison_category` | BOOLEAN, STRING or NUMERIC |
| `case_types` | Primitive type of every constant, retaining INTEGER/REAL distinctions |

The [authored tests](../tests/test_scalar_select.py) cover comparison boundaries,
both execution engines, effects, malformed tables, control flow, cooperative
lifetime, linked routines, CLI generation and JSON state. These are offline
Pythonic checks, without native compiler or controller acceptance claims.
