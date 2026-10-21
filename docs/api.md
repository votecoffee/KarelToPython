# API and command-line guide

## Translation

```python
from karel2py import translate
from karel2py.lexer import TranslationError

try:
    result = translate(
        "PROGRAM DEMO VAR answer: INTEGER BEGIN answer=42 END DEMO",
        filename="demo.kl",
    )
except TranslationError as error:
    print(error.as_dict())
else:
    python_source = result.python_source
    report = result.report
```

`translate(source, *, filename="<input>", array_shapes=None, mode="pythonic")` accepts a KAREL
source string. `filename` labels diagnostics and source locations. Translation
does not run the program. The returned object exposes generated `python_source`
and a JSON-serializable `report` with program/version information, source maps,
hashes, features, effect analysis and feature-specific policies.

Pythonic [POS construction](pos-construction.md) supplies checked XYZWPR values,
independent CONFIG data and source-located `pos_constructors` report entries.
[CONFIG text conversions](config-text.md) expose `config_text_conversions` and
`config_text_policy`, including portable grammar, output guards and status behavior.

[Source directives](source-directives.md) retain raw `directives`, decoded
`directive_metadata` and a `directive_policy` with `required_environments`.
These are recorded requirements and attributes; they do not load definitions or
enable additional source symbols or calls.

[Frame transforms](frame-transforms.md) expose `frame_operations` for explicit
XYZWPR composition/inversion and `frame_policy` for Euler conventions,
configuration handling, capture order and retained controller boundaries.
FRAME construction also records one-based `origin_argument` and three/four operand
types in those entries. See [frame construction](frame-construction.md).
[POSITION conversions](position-conversions.md) add `position_conversions` entries
and `position_conversion_policy` for whole assignments, matrix tolerance and
read-only orientation protection. Routine interfaces retain exact types.

`mode="pythonic"` is the default and currently the only released mode. It uses
ordinary Python floats, rounded math and ties-to-even `ROUND`. The selected mode
is embedded in `Program.translation_mode`, the report translation context and
its hash. `mode="strict"` returns `E_MODE`: strict is a future milestone, with
the prior exactness implementation retained internally. See the
[numeric equivalence matrix](numeric-modes.md) for the complete chosen conventions.

`TranslationError.as_dict()` contains `code`, `message`, `file`, `line` and
`column`. Unsupported source is an error, rather than a partial best-effort module.

For supported global variable-sized declarations, explicitly supply every outer
dimension through `array_shapes`, for example `{"READINGS": [3]}`. Names are
case-insensitive; fixed dimensions must agree. Shapes are embedded during
translation. They do not query or resize controller storage.

## CLI

```sh
python -m karel2py input.kl --check
python -m karel2py input.kl -o converted.py --report translation.json
python -m karel2py input.kl -o converted.py --array-shape READINGS=3
python -m karel2py input.kl --mode pythonic --check
python -m karel2py --version
```

The installed `karel2py` command is equivalent. Inputs are UTF-8, with an optional
BOM. Use `--force` to replace an explicitly named output/report. Source, output
and report paths must differ. Their parent directories must already exist.
`--check` cannot be combined with `--output`.

| Exit code | Meaning |
| --- | --- |
| `0` | Translation or validation succeeded. |
| `1` | File or text-decoding error. |
| `2` | Rejected source or invalid CLI arguments. |

## Generated Program

A generated module defines `Program(*, sleep=None, write=None, read=None, joint_axes=None)`.
Call `Program().run(max_steps=100_000)` to execute explicitly and receive a
snapshot of global variables. Only the generated module's entry point runs it
automatically; importing a module defines its class.

`Program.source_directives` contains immutable normalized `(name, argument)` pairs
in source order, with `None` for directives without arguments. It is empty when
no supported directives occur. It is available without the compiler installed.

`snapshot()` returns the current global state. Names are normalized to uppercase.
Uninitialized scalar values are represented as `{"uninitialized": true}` and
unknown initial BYTE contents as `{"unknown_byte": true}`. Routine locals are
excluded. Aggregate snapshots are detached from mutable runtime storage.

The step limit counts instrumented execution, not wall-clock time. Errors raise
`karel2py.runtime.KarelRuntimeError`. Bare KAREL `ABORT` raises
`karel2py.runtime.KarelAbort`, records `abort_info` and terminates the instance.
Use a new `Program` for a cold restart. Earlier writes and callback effects are
not rolled back by failures or ABORT.

## Host callbacks and context

- `sleep(seconds)` handles supported `DELAY`. The default is the host sleeper.
  Tests can inject a recorder. Zero delay makes no callback.
- `write(text)` handles supported text `WRITE` requests. Without it, requests
  are recorded in `write_requests`; this is not controller output. A callback
  receives one complete statement and must return `None` synchronously.
- `read(request)` supplies typed scalar `READ` values as a list/tuple matching
  defensive line/type metadata. An explicit callback is required when READ
  executes. `read_requests` records defensive metadata and outcomes; generated
  scripts can load JSON response batches with `--read-values`. See
  [Pythonic input](pythonic-read.md).
  `runtime.TextInput(text)` supplies explicit ASCII text with a persistent cursor
  and CR line control; generated scripts can choose `--read-text` instead.
  Optional `line_breaks` metadata describes CR positions. See [text input](text-input.md).
  [READ formats](read-formats.md) add optional per-target `format_specifiers`
  metadata and ordered dynamic expressions for widths, bases and STRING quoting.
- `joint_axes=n` supplies an explicit offline axis count for the restricted
  degree-valued joint conversion subset. It is not robot discovery or group
  configuration. Copying exact joint values does not infer a controller context.

For example, a generated program using supported WRITE requests can be exercised
with `Program(write=messages.append)`, where `messages` is a list. The
`write_requests` and `abort_info` properties return defensive observations.
Mixed STRING/BOOLEAN/INTEGER/BYTE/SHORT/REAL items and CR newlines are supported.
Numeric width/base/precision specifiers follow the chosen
[Pythonic output contract](pythonic-output.md). Items render left to right once;
the combined ASCII output is limited to 254 characters. Rendering/length failure
creates no outer request while preserving earlier effects and nested requests.

`string_operation_policy` describes SUB_STR clipping, its 254-character result
bound before consumption, zero counts, one-based starts and INDEX empty-search
results. It also records STR_LEN/CHR/ORD domains, argument evaluation order and
retained checks. See [STRING operations](string-operations.md).

`routine_effects[].potential_global_writes` reports transitive global roots.
Together with `potential_parameter_writes`, it supports checked global-counter
FOR calls and read-only counter references. `for_policy` records cleanup after
successful initial assignment, including early exits and failures. See
[Pythonic FOR](pythonic-for.md) for proof boundaries and compatibility changes.

`using_scopes` records lexical `id`, `parent` and zero-based `depth`, original
`source_selectors`, resolved paths in `variables`, inherited `field_bindings` and
source-located `resolved_uses`. `using_policy` describes nested precedence and
constant/routine-name lookup. See [Pythonic USING](pythonic-using.md).

## Limits

`conversion_policy.format` includes signed `CNV_INT_STR` bases 2..16, with base 0
selecting decimal. Digits use uppercase A..F and no prefix; minimum widths in
1..254 add left padding. These are chosen Pythonic conventions.

`conversion_policy` reports rounded Python `CNV_REAL_STR` precision in -254..254:
negative selects uppercase scientific with absolute digits, nonnegative selects
fixed output. Minimum widths are in 1..254. Those bounds limit formatting work;
caller-capacity blank/asterisk overflow and checked output references remain.
Input conversions use Python int/float
text grammar, bounded ASCII text and finite/range checks.

WRITE accepts INTEGER format expressions. Report `format_specifiers` entries
are integers for signed/grouped literals, or objects containing `expression=true`
and physical `line`/`column` for dynamic values. `items[].dynamic_formats` identifies
dynamic sites; `format_width` retains the integer or expression object, while
`alignment`, `quoted` and `width_policy` explicitly mark dynamic cases.
`write_policy.string` describes paired quotes, doubled apostrophes and bounded
truncation/fallback. See [text formats](text-formats.md).

`bare_function_calls` records each resolved zero-parameter function-name use with
its body, original source line/column and exact `result_spec`.
`bare_function_policy` describes the resolution and effect boundaries. These sites
use the ordinary checked call path; they do not represent first-class functions
or external linkage.

ARRAY return reports include the exact resolved `element_spec` and `logical_rank`
(one through three). Anonymous outer results may contain prior named
fixed ARRAY components. Bounded STRING elements carry their exact physical
capacity in `element_spec`; generic source-formal capacities are checked at
runtime, and result copying never truncates to match a different capacity.
Results also support grouping, compatible user-routine value arguments,
direct RETURN forwarding, ARRAY_LEN returning the first dimension and aggregate access.
Copies retain exact types/shapes and known initialized leaves. The
[ARRAY result contract](language-support.md#array-function-results) describes the
supported forms and remaining restrictions.

Internal STRING functions support `STRING` (default capacity 254) and
`STRING[n]` (global constant capacity 1..254). RETURN validates initialized ASCII
and right-truncates before frame cleanup. Literals, expressions, function results
and grouped STRING actuals receive independent writable capacity-254 storage;
bare storage keeps caller identity and capacity. Input values remain bounded to
254 characters, and private mutations are never copied back. See the
[STRING contract](pythonic-strings.md) and report fields
`string_routine_declarations`, `string_returns`, and `string_value_arguments`.

The runtime uses Pythonic numeric equivalents and checked range, shape, initialization and alias
checks. Successful translation does not guarantee successful execution for all
inputs. The [language support guide](language-support.md) and [semantic notes](semantics/README.md)
describe the supported input domains and unresolved behavior.

`evaluation_policy` records the chosen Pythonic order, Boolean short circuiting,
assignment value capture, live reference actuals, conversions, FOR bounds and
failure behavior. See the [evaluation order guide](evaluation-order.md) for
examples and the compatibility changes introduced in 0.54.0.

`array_value_arguments` records private ARRAY copy sites with formal and source
type specs. `array_function_uses` records ARRAY-valued expression calls.
`array_value_policy` describes checked ownership and `aggregate_access_policy`
describes subscripts/fields on explicit calls and groups. ARRAY formal
`passing_modes` includes reference and value; see the
[ARRAY values guide](pythonic-arrays.md).

`array_result_declarations` and `array_returns` record the complete result type,
declared dimension mask and nominal identity. Named types and anonymous fixed,
wildcard or mixed dimensions follow the [result shape contract](array-result-shapes.md).
`array_length_policy` defines Pythonic ARRAY_LEN as the first concrete dimension;
it also supports matrices and nested arrays without reading scalar leaves.

`type_aliases` records transparent TYPE declarations with name, immediate target,
resolved spec and physical source location. `user_types` and `named_array_types`
retain original aggregate identities. `type_alias_policy` describes resolution
and boundaries; bounded STRING alias value arguments report the declared alias
capacity in `string_value_arguments[].temporary_capacity`. See [TYPE aliases](type-aliases.md).

`vector_constructors` records fallback VEC construction sites with body,
physical line/column, X/Y/Z argument order, one-time evaluation and independent
value flags. `vector_policy` records constructor/internal-routine name priority,
unary VECTOR signs, product association and numeric boundaries. See
[Pythonic vector expressions](pythonic-vectors.md).
