# Pythonic Boolean waits

Since 0.75.0, `WAIT FOR condition` rechecks a supported BOOLEAN expression until
it becomes true. A false check yields through the existing host sleeper with
`sleep(0.0)`. Every check consumes the ordinary execution step budget.

```karel
PROGRAM PYTHONIC_WAIT
VAR checks,after_wait: INTEGER ready: BOOLEAN
ROUTINE ready_now: BOOLEAN
BEGIN
  checks=checks+1
  ready=checks>=3
  RETURN ready
END ready_now
BEGIN
  checks=0
  ready=FALSE
  WAIT FOR ready_now()
  after_wait=checks
  WAIT FOR ready
  WRITE('checks=',after_wait::0,', ready=',ready,CR)
END PYTHONIC_WAIT
```

The first wait checks the function three times and yields twice. The second wait
finds `ready` true immediately and makes no sleeper call. The final snapshot has
CHECKS=3, AFTER_WAIT=3 and READY=true. Recorded text is `checks= 3, ready= TRUE`
followed by a newline.

The [authored example](../examples/pythonic_wait.kl) adds environment metadata
and independent complete [snapshot](../examples/pythonic_wait.expected.json),
[text](../examples/pythonic_wait.write.expected.json) and
[sleeper-call](../examples/pythonic_wait.sleep.expected.json) fixtures.

## Conditions and evaluation

Use BOOLEAN variables, fields/elements, expressions or internal BOOLEAN function
results. Group comparisons inside compound conditions, for example
`WAIT FOR (count>=3) AND enabled`, following ordinary operator precedence.
Existing Pythonic AND/OR short-circuit rules apply within each check. An unknown
condition raises an initialization error before the wait yields.

The entire condition evaluates once per check. A function is called again on the
next check; its earlier effects remain. Ordinary initialization, type, routine
parameter, FOR-counter and cleanup checks apply. Function calls in a wait are a
Pythonic extension; native condition-handler expression restrictions are not
implicitly adopted or authenticated.

An internal condition function can use existing typed READ input to acquire a
new Boolean value on each check. The wait does not acquire hardware or controller
data itself. In routines, WAIT contributes to transitive potential-host-delay
reports, including when it appears on a skipped branch.

## Host execution and bounds

`Program(sleep=callback)` supplies the same synchronous sleeper used by DELAY.
WAIT calls it with `0.0` after each false check; the callback must return `None`.
The default is Python `time.sleep`. DELAY 0 retains its existing no-callback rule.
Zero-second WAIT calls are host scheduling opportunities, without a specified
polling period or native controller timing guarantee.

The wait consumes the existing `run(max_steps=...)` budget on every condition
test; statements in condition functions consume their usual steps too. A plain
`WAIT FOR FALSE` therefore ends with a step-budget error instead of spinning
without a bound. The budget is not a wall-clock timeout and cannot bound the
duration of an external callback. As with existing WHILE tests, condition effects
occur before the test's budget check.

Sleeper errors become source-located `KarelRuntimeError` without automatic retry.
KeyboardInterrupt and other BaseException interruptions propagate. Errors and
ABORT retain earlier effects, unwind routine frames and clear initialized active
FOR counters. Sticky ABORT of the current instance stops further checks, including
when triggered during a host yield. A successful wait continues with the next
statement. Labels and dispatch use the same checked polling behavior.

Reports expose `waits` with body, physical source line/column, condition kind,
BOOLEAN type, repeated-check policy, zero-second yield and step-budget flag.
There is one entry per source wait. `wait_policy` records the execution choices
and remaining boundaries. Generated modules need only the existing runtime files.

## Evidence boundary

The reviewed [reference edition](references.md), one-based PDF pages 621 and 778,
defines WAIT FOR conditions and shows AND/OR condition syntax. This implementation
covers the supported BOOLEAN expression subset. Polling, function calls,
short-circuit evaluation, host yielding and the step budget are explicit Pythonic
choices, verified with authored examples and injected callbacks.

Native event/global-condition syntax, condition handlers, hardware ports, motion
conditions, task coordination and controller scheduling remain unsupported.
Strict mode remains a future milestone. These checks establish offline behavior,
without native compiler or controller acceptance.
