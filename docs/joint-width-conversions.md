# Joint width conversions

Pythonic mode accepts whole `JOINTPOS1` through `JOINTPOS9` values across
differing declared widths in assignments, ordinary source routine arguments and
`RETURN` expressions. Bare `JOINTPOS` means nine slots.

```karel
VAR small:JOINTPOS2 wide:JOINTPOS9
ROUTINE inspect(value:JOINTPOS9):JOINTPOS4
BEGIN
  RETURN value
END inspect
BEGIN
  wide=small
  small=inspect(small)
END
```

The sample needs initialized `small` data from source initialization or explicit
context. Widening appends zeros. Narrowing succeeds only when every discarded
axis is zero; negative zero is accepted. Every source axis must be initialized,
finite numeric data. A nonzero or missing discarded axis raises before publishing
the destination. This is a portable storage convention, without axis-unit,
group, robot-model or physical-equivalence inference.

Same-width copies retain their existing partial-data behavior. This new complete
input requirement applies to a width change. [Positional ARRAY values](positional-arrays.md)
also support whole-array width conversion, including [named and matching nested
components](named-array-conversions.md) with independent receiver schemas.
Whole STRUCTURE schemas retain their identities.

## Ownership and evaluation

A differing-width actual is captured once at its argument position and converted
into independent writable private storage. There is no copy-back to the caller,
including on return, failure, pause or stop. Exact same-type bare arguments still
alias their original storage. Grouped exact values remain private values.

RETURN converts before routine-frame and active-counter cleanup. Assignment
evaluates and validates its right-hand conversion before evaluating target
selectors. A failed conversion preserves the target and skips later arguments
or target-index calls; earlier source effects remain. Label-dispatched and
cooperative source use the same policy. No robot service request is generated.

The [authored example](../examples/joint_width_conversions.kl) initializes two
axes using explicit `joint_axes=2`, then pads, passes, returns and narrows them.
Generated execution uses `--joint-axes 2` for those initialization calls. Pure
width conversion itself needs no robot or axis context.

## Exact boundaries

BYNAME targets, linked routine declarations and raw external callback return
types retain exact type contracts. Matching linked source signatures can accept
privately converted actuals, including named/component ARRAY values.
[Source ARRAY schemas](array-schema-conversions.md) also support same-width
ARRAY names/layouts. [Checked Pythonic joint-axis data access](joint-axis-access.md)
is now available. Nonzero-axis discard and physical motion remain unavailable. Existing [model-backed conversions](kinematic-interfaces.md)
remain a separate explicitly configured operation.

Reports contain `joint_width_conversions` sites with assignment/argument/RETURN
kind, source and target type specs, source location and independent-value flags.
Converted argument/result rows use `conversion_kind="joint_width"`.
`joint_width_policy` records these choices. The preserved legacy translator
continues to reject cross-width source forms; public strict mode is future work.
