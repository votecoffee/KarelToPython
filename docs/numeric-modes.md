# Pythonic mode and the strict milestone

Since 0.51.0, public translation defaults to **Pythonic mode**. It uses practical
Python numeric equivalents, accepting reasonable differences from KAREL. Existing
source/type, initialization, array shape, ownership and effect checks still apply.
The profile also includes [mixed text output](pythonic-output.md) and
[STRING functions with writable value copies](pythonic-strings.md).

```sh
python -m karel2py examples/pythonic_numeric.kl --mode pythonic --check
```

```python
from karel2py import translate

result = translate("PROGRAM T VAR r: REAL BEGIN r=0.1+SQRT(2) END T",
                   mode="pythonic")
```

The option is optional. The selected mode is embedded in generated
`Program.translation_mode`, recorded in `report["translation_context"]` and
included in the translation-context hash. A generated module retains its mode
when imported or executed later. Nested programs restore the enclosing numeric
policy even after errors, and independent threads do not share mutable mode state.

## Equivalent operations

| KAREL feature | Pythonic equivalent | Chosen convention |
| --- | --- | --- |
| `REAL` | Python `float` | Host floating-point precision, range, subnormals and underflow; finite values required. Ordinary decimals such as `0.1` are accepted. |
| REAL `+ - * /`, `ABS` | Float arithmetic and `abs` | Rounded Python results; division by zero raises a source-located error. |
| `INTEGER`, `BYTE`, `SHORT` | Python `int` with checked storage | Existing signed-32-bit, narrow-storage and reserved-marker checks remain. REAL to INTEGER still requires an explicit conversion. |
| `ROUND(x)` | `round(x)` | Ties to even: `ROUND(2.5)` is 2 and `ROUND(3.5)` is 4. This changes the previous half-away-from-zero behavior. |
| `TRUNC(x)` | `math.trunc(x)` | Toward zero; checked INTEGER result. |
| `DIV` | Integer quotient truncated toward zero | Existing KAREL-oriented convention, including negative inputs. |
| `MOD` | Python `%` | Negative inputs accepted; the remainder has the divisor's sign. |
| `SQRT`, `EXP`, `LN` | `math.sqrt`, `math.exp`, `math.log` | General rounded results; SQRT requires a nonnegative argument and LN a positive argument. |
| `SIN`, `COS`, `TAN` | Python `math` after degree conversion | Forward inputs reduced by period; available exact identities retained. TAN at odd multiples of 90 degrees raises a domain error. |
| `ASIN`, `ACOS` | Python inverse trig, converted to degrees | Inputs in -1..1; general rounded results. |
| `ATAN2(x,y)` | `math.degrees(math.atan2(y,x))` | KAREL argument order, all quadrants, result in -180..180 degrees; origin rejected. |
| `CNV_STR_REAL`, `CNV_STR_INT` | `float(text)`, `int(text,10)` | Bounded ASCII input, including Python whitespace/exponent conventions. Invalid numeric text clears the output; non-finite/out-of-range values raise before mutation. |
| `CNV_REAL_STR` | Python fixed/scientific `format` | Precision -254..254; negative selects uppercase scientific with absolute digits. Leading blank and optional left padding to minimum width 1..254. See [text formats](text-formats.md). |
| `CNV_INT_STR` | Positional integer formatting | Signed bases 2..16, uppercase A..F, no prefix; base 0 selects decimal. Leading blank and minimum width 1..254. |
| `CNV_STR_TIME`, `CNV_TIME_STR` | Gregorian calendar validation and packed bit fields | Fixed English text, 1980..2107, two-second precision and signed 32-bit patterns; see [time text](time-text.md). |
| `GET_USEC_TIM`, `GET_USEC_SUB` | Host monotonic microseconds and modular subtraction | Explicit two-minute ring and optional test clock; one clock and intervals shorter than two minutes; see [microsecond timers](microsecond-timers.md). |
| `GET_REG`, `SET_INT_REG`, `SET_REAL_REG` | Explicit bounded dictionary-backed numeric register bank | Distinct int/float kinds, checked outputs and portable status codes; see [numeric registers](numeric-registers.md). |
| Registers, ports, GET_VAR/SET_VAR | Explicit checked banks and references | Offline values and portable statuses; see [service matrix](offline-services.md). |
| FILE, PATH, QUEUE_TYPE | Byte buffers, typed lists and FIFO entries | Bounded state, explicit ownership and documented Pythonic conventions. |
| Handlers, timers and task control | Generator checkpoints and monotonic elapsed time | Retained pause/resume frames, explicit task/callback registries; no native scheduler. |
| MIRROR, extended frames and model calls | Checked geometry plus supplied adapters | Explicit metadata/reflection choices and robot-model requirements. |
| VECTOR math, REAL record fields and joint data | Checked float components | Rounded intermediates/results; zero and parallel cross products allowed. Structural identity and explicit joint context remain required. |
| Numeric WRITE items | Python integer/float formatting | Mixed scalar lists, INTEGER expressions for width/base/precision, CR mapped to LF and one complete output request; see [text output](pythonic-output.md). |

Both text formatters retain caller STRING capacity and the blank/asterisk
overflow marker. Prototype width/precision bounds limit formatting work. Math
domain errors, non-finite results and INTEGER overflow remain errors. Pythonic
mode does not provide unrestricted Python evaluation of source text.

## Compatibility and the strict milestone

Programs translated before 0.51.0 used a conservative exact binary32 subset.
Retranslating now can change values, ROUND ties, underflow and accepted inputs.
Use the authored [example](../examples/pythonic_numeric.kl) and its
[expected snapshot](../examples/pythonic_numeric.expected.json) to see the current
contract. Numerical approximations do not provide native controller equivalence.

**Strict mode is a future milestone.** `mode="strict"` and `--mode strict`
currently return `E_MODE` with that explanation. The older exactness runtime and
regression tests are preserved internally as a starting point; they are not a
released strict mode or an exact controller model. Pythonic coverage takes
priority before implementing and validating a public strict contract.

The older numeric/trig/conversion/vector semantic ledgers record that conservative
research contract. Their exactness restrictions do not describe the public
Pythonic mode; this document and the generated report describe its current rules.

Pythonic mode also defines [evaluation order](evaluation-order.md), including
function composition, Boolean short circuiting and assignment value capture.
Older ordering rejections are retained internally for the strict milestone.
