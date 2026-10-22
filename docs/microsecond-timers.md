# Pythonic microsecond timers

Since 0.77.0, Pythonic mode supports `GET_USEC_TIM` and
`GET_USEC_SUB(later,earlier)` for short elapsed-time measurements. The first
samples a host monotonic clock. The second computes a difference on an explicit
portable two-minute counter ring. Both return INTEGER values.

```karel
PROGRAM PYTHONIC_MICROSECONDS
%ENVIRONMENT TIM
VAR earlier,later,elapsed,same: INTEGER
BEGIN
  earlier=119999990
  later=25
  elapsed=GET_USEC_SUB(later,earlier)
  same=GET_USEC_SUB(42,42)
  WRITE('elapsed=',elapsed::0,' us',CR)
END PYTHONIC_MICROSECONDS
```

This demonstrates supplied counter data across rollover: `elapsed` is 35 and
`same` is zero. It performs no clock reads. The
[authored example](../examples/pythonic_microseconds.kl) has independent
[snapshot](../examples/pythonic_microseconds.expected.json) and
[output](../examples/pythonic_microseconds.write.expected.json) fixtures.

## Reading the clock

Use `GET_USEC_TIM` or `GET_USEC_TIM()` in a value expression. Each evaluated
occurrence reads once. The default samples `time.monotonic_ns()`, floors to whole
microseconds and reduces modulo `120_000_000`. Results are in 0..119999999.
This clock has an unspecified origin and conveys no calendar date or timezone.
Microsecond units do not guarantee microsecond resolution or accuracy.

For repeatable execution, supply `Program(clock_us=...)` with a synchronous
zero-argument callable returning nonnegative Python integer microseconds:

```python
from karel2py import translate

source = """PROGRAM STOPWATCH
VAR first,last,elapsed: INTEGER
BEGIN
  first=GET_USEC_TIM
  last=GET_USEC_TIM()
  elapsed=GET_USEC_SUB(last,first)
END STOPWATCH"""
namespace = {"__name__": "timer_example"}
exec(translate(source).python_source, namespace)
samples = iter((119999990, 120000025))
Program = namespace["Program"]
program = Program(clock_us=lambda: next(samples))
assert program.run() == {"FIRST": 119999990, "LAST": 25, "ELAPSED": 35}
assert [row["counter"] for row in program.clock_reads] == [119999990, 25]
```

The adapter can return an unbounded integer; reduction happens after validation.
It owns its origin and progression and is retained across runs. There are no
clock samples at construction or run start. Boolean, negative, floating-point,
asynchronous and other non-integer results raise `KarelRuntimeError`. Callback
exceptions are wrapped with source location and retain their cause. Clock reads
are synchronous; the step budget does not interrupt a blocking callback.

## Subtraction and limits

`GET_USEC_SUB(later,earlier)` requires INTEGER counters in 0..119999999 and
returns `(later-earlier) % 120_000_000`. Equal counters produce zero. To interpret
the result as elapsed time, both samples must use the same clock and the actual
interval must be shorter than two minutes. Multiple wraps and backward or mixed
clocks cannot be detected from these two counters. In particular, a complete
two-minute interval aliases zero. Use the helper to cross rollover; plain
subtraction can produce a negative number there.

Subtraction arguments evaluate once, left to right, before counter-range checks.
Ordinary initialization/type checks still apply during argument evaluation.
Earlier effects remain on failure, and a pending assignment keeps its previous
target value. BOOLEAN short circuiting skips unused clock expressions. WAIT FOR
rechecks clock expressions under its existing step budget and host-yield rules.
FOR protections, routine cleanup and sticky ABORT remain in effect. Clock errors
do not become a fabricated zero timestamp.

## Names, reports and observations

These are fallback functions. Explicit internal routines keep their own
signatures and effects. A variable, parameter, constant or USING field named
GET_USEC_TIM takes precedence over its bare clock syntax. Explicit function call
syntax uses the fallback when no internal routine with that name exists.

`microsecond_timers` report entries locate evaluated source sites and distinguish
host reads from pure subtraction. `microsecond_timer_policy` describes the model;
routine effects propagate `potential_host_clock_reads` through internal calls.
`Program.clock_reads` returns copied records with `line`, `adapter`
(`monotonic` or `injected`) and `adapter_outcome`. Completed reads also include
`counter`. Failure outcomes are `clock_failed`, `invalid_response` or `aborted`,
without a counter. Observations reset when a new run begins; failed/aborted reads
retain earlier effects. Raw unbounded clock samples are not stored in this trace.

## Evidence boundary

The reviewed [reference edition](references.md), PDF pages 419-420, describes
microsecond sampling, subtraction and a two-minute measurement limit. Its
GET_USEC_SUB heading calls it a procedure, while its syntax, return type and
example use a function. The translator follows the value-returning form.

The exact native counter encoding and wrap behavior are unverified. The
120,000,000-microsecond ring, host monotonic source and adapter validation are
explicit Pythonic choices. Host timing is separate from controller scheduling,
power-on time and native tick precision. GET_TIME and SET_TIME use the separate
[offline calendar service](calendar-clock.md); controller clock changes remain
unsupported, and strict mode remains a future milestone.
