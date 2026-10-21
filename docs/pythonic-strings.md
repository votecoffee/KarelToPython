# Pythonic STRING functions and arguments

Pythonic mode supports internal functions returning `STRING` or `STRING[n]`.
Results are immutable Python strings with a bounded ASCII contract. A STRING
value argument has independent writable storage, so a routine can edit its own
copy without changing the caller's string.

```karel
PROGRAM string_demo
VAR original,decorated: STRING[16]
ROUTINE bracket(value: STRING): STRING
BEGIN
  value='['+value+']'
  RETURN value
END bracket
BEGIN
  original='hello'
  decorated=bracket((original))
  WRITE(decorated,CR)
END string_demo
```

The final values are `ORIGINAL="hello"` and `DECORATED="[hello]"`, and the output
request contains `[hello]\n`. Parentheses around the actual argument select a
value copy. Without them, `bracket(original)` receives the original storage and
can change it. See the [complete authored example](../examples/pythonic_strings.kl),
[expected values](../examples/pythonic_strings.expected.json) and
[expected output](../examples/pythonic_strings.write.expected.json).

## Function results

`ROUTINE label: STRING` chooses a result capacity of 254. An explicit
`ROUTINE label: STRING[8]` chooses capacity 8. The explicit capacity must be an
INTEGER constant expression in 1..254, resolved from the global interface scope;
routine-local constants cannot change it.

RETURN evaluates its expression once, checks initialization and the full ASCII
contents, then truncates on the right to the result capacity. Validation happens
before the routine frame is removed. A later destination assignment applies that
destination's own capacity. For example, a `STRING[8]` function returning
`'abcdef'` produces six characters; assignment to `STRING[3]` stores `'abc'`.
An empty result is initialized, and no padding is added.

Results support explicit calls and existing bare zero-argument function names.
They can be assigned, concatenated or compared, written, returned by another
function, or consumed by compatible built-ins and STRING parameters. Functions
compose using the chosen [Pythonic evaluation order](evaluation-order.md),
including multiple arguments and effectful operators. Missing RETURN, wrong result types, non-ASCII
contents and uninitialized values fail before destination assignment and unwind
the routine frame. Earlier effects remain visible.

## Argument storage

| Actual argument | Passing behavior | Capacity |
| --- | --- | --- |
| Bare ordinary variable, field or array element | Reference to caller storage; writes remain visible | Actual caller capacity. |
| Parenthesized storage, such as `(text)` | Independent writable value temporary | Chosen Pythonic capacity 254. |
| Literal, constant, expression or STRING function result | Independent writable value temporary | Chosen Pythonic capacity 254. |

The input must be initialized ASCII of at most 254 characters. Oversized value
arguments fail before the callee starts. Writes to a temporary use normal
right-truncating STRING assignment; supported conversion procedures may also
write or clear it. The copy is never written back to the original argument,
including after errors or ABORT. Two copies of one source have independent
storage. Forwarding a temporary by reference shares that temporary; grouping it
again creates another copy.

These rules let routines accept literal inputs while using their parameters as
scratch strings. Bare reference arguments still retain their smaller capacities,
aliasing behavior and existing guards. Potential formal writes remain visible in
the effect report even when a particular call supplies a private value.

## Reports and evidence

`string_routine_declarations` records each result capacity and whether it was
defaulted. `string_returns` records RETURN sites, capacities and truncation policy.
`string_value_arguments` records independent writable copies and temporary
capacity. STRING parameter `passing_modes` includes both reference and value.

The reviewed manual describes STRING function syntax in one section and prohibits
STRING function values in another. Pythonic mode deliberately supports the syntax
and chooses the bounded result/temporary behavior above. This is a practical
translation policy, with no controller STRING ABI or native acceptance claim.
The [semantic contract](semantics/pythonic_string_semantics.json) records the
conflicting source pages and the tests. The older string ledgers and conservative
tests are retained as input to the future strict milestone.
