# Pythonic TYPE aliases

Since 0.61.0, Pythonic mode supports transparent aliases for supported scalar
types, bounded STRINGs, data records, joints and previously defined named types.
An alias gives an existing checked type another name. It introduces no wrapper
value or conversion and gives ARRAYs and STRUCTUREs no new nominal identity.

```karel
PROGRAM ALIASES
TYPE count_t=INTEGER
text_t=STRING[4]
row_t=ARRAY[2] OF count_t
row_alias=row_t
VAR values: row_alias
total: count_t
label: text_t
ROUTINE sum(p: row_t): count_t
BEGIN
  RETURN p[1]+p[2]
END sum
BEGIN
  values[1]=3
  values[2]=4
  total=sum(values)
  label='ready'
  WRITE(label,':',total::0,CR)
END ALIASES
```

This finishes with `VALUES=[3,4]`, `TOTAL=7`, `LABEL='read'` and one recorded
WRITE request, `read: 7\n` (numeric WRITE retains its leading blank). See the complete [authored example](../examples/pythonic_type_aliases.kl)
for aliases used in STRUCTURE fields, ARRAY results and bounded STRING parameters.

## Resolution and identity

Names are case-insensitive. Alias chains resolve eagerly in TYPE declaration
order, so each target must already exist. Forward references, self references,
cycles and unknown targets produce source-located diagnostics. Duplicate names
and ordinary declaration collisions retain their existing checks.

`TYPE copy_t=row_t` retains `row_t`'s ARRAY identity and can share its reference,
assignment and result interfaces. A new `TYPE other_t=ARRAY[2] OF count_t`
creates a distinct ARRAY type even if its dimensions and element type match.
The same distinction applies to an alias of a STRUCTURE versus a new STRUCTURE
definition. Nested ARRAY aliases retain their original component identities.

Scalar aliases use the underlying arithmetic and comparison rules, including
INTEGER-to-REAL promotion and Pythonic numeric approximations. Bounded STRING
aliases retain their declared capacity for variables, fields, ARRAY elements,
locals and function results. ARRAY dimensions, record kinds and joint widths
also remain unchanged. Named function-result aliases must precede the routine.

## Arguments and copies

Bare storage arguments retain ordinary references. Grouped storage and value
expressions retain the existing independent-value behavior. Aggregate value
arguments and results require known, initialized scalar leaves and preserve
shape, capacity and nominal identity. Ordinary scalar ARRAY assignments can
preserve uninitialized elements under the existing whole-copy rules.

A plain `STRING` formal continues to inherit the actual reference capacity;
its Pythonic value arguments use capacity 254. A bounded STRING alias formal
requires a reference with exactly the alias capacity. Grouping a different-sized
STRING makes a value argument: check initialized ASCII input of at most 254
characters, then copy and right-truncate to the alias capacity before the body.
Later writes to that private temporary use the same capacity, with no copy-back.
For example, a `text_t=STRING[4]` value formal receives `'abcdef'` as `'abcd'`.

Alias expansion introduces no evaluation effects. Existing left-to-right argument
capture, prior effects on failure, frame cleanup, writable-formal analysis and
active FOR-counter protection still apply.

## Boundaries and reports

BYTE and SHORT aliases are useful for ARRAY elements and STRUCTURE fields.
They remain prohibited as standalone globals, locals, parameters and results.
Aliases preserve INTEGER range/MAXINT, narrow-element sentinel, ASCII, capacity,
initialization, allocation, ownership and positional-context checks. Unsupported
types, external FROM declarations, local TYPE sections, wildcard TYPE dimensions
and inline anonymous nested ARRAY definitions remain outside this subset.

`user_types` contains resolved type specs. `type_aliases` records each alias's
name, immediate target, resolved spec and physical declaration location.
`type_alias_policy` states the chosen contract; `named_array_types` includes
aliases while retaining the original ARRAY identity. Bounded STRING value sites
report their actual `temporary_capacity`.

These are chosen offline Pythonic rules. Conservative alias rejections remain
internal for the future strict milestone. No new native compiler acceptance,
controller type ABI or runtime equivalence is claimed.
