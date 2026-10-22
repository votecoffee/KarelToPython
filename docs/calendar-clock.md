# Offline calendar time

Version 0.87.0 adds GET_TIME and SET_TIME using an explicit
`ExecutionContext(calendar=CalendarClock(...))`. A clock starts from a supplied
naive Python datetime or valid packed INTEGER. It stays frozen unless the host
supplies an elapsed-microsecond callback. No operating-system clock is changed.

## Source operations

`GET_TIME(target)` writes a checked INTEGER in the same packed representation as
CNV_STR_TIME/CNV_TIME_STR. It validates the clock before changing the target.
`SET_TIME(value)` validates the supplied packed value and replaces only this
offline clock's anchor. SET_TIME(0) is a no-op, following the manual: it neither
samples an adapter nor resets elapsed progression. Both operations require an
explicit calendar service, including the zero no-op.

```python
from datetime import datetime
from karel2py import translate, runtime as rt

context = rt.ExecutionContext(calendar=rt.CalendarClock(datetime(2024,2,29,12,34,57)))
source = """PROGRAM DEMO VAR stamp: INTEGER text: STRING[20] BEGIN
GET_TIME(stamp)
CNV_TIME_STR(stamp,text)
END DEMO"""
namespace = {"__name__": "calendar_demo"}
exec(translate(source).python_source, namespace)
Program = namespace["Program"]
assert Program(context=context).run() == {
    "STAMP": 1482515548, "TEXT": "29-FEB-2024 12:34:56"
}
assert context.calendar.now() == datetime(2024,2,29,12,34,57)
```

Packing uses year minus 1980 in bits 31..25, month 24..21, day 20..16, hour
15..11, minute 10..5 and two-second increments 4..0. Years are 1980..2107, with
Gregorian calendar validation. Odd seconds floor when packed; internal values
retain odd seconds and microseconds. Dates from 2044 onward have negative signed
32-bit values. Signed INTEGER ordering across that boundary is not chronological.
Zero is not a valid calendar date or initial clock value.

The host methods are `CalendarClock.now()` for the complete immutable datetime,
`read()` for packed INTEGER, and `set(value)` for a datetime or packed value.
Invalid values fail before replacing the clock. Naive calendar fields have no
implicit timezone or Unix-epoch interpretation. See [time text](time-text.md).

## Advancing the clock

Supply `clock_us` as a synchronous zero-argument callable returning nonnegative
integer microseconds. It is sampled once during CalendarClock construction to
establish the elapsed origin, then once per read, nonzero set or snapshot. Its
origin does not need to be zero. Observations must never move backward.

```python
from datetime import datetime
from karel2py import runtime as rt

elapsed = {"us": 100}
clock = rt.CalendarClock(datetime(2024,2,29,12,34,56),
                         clock_us=lambda: elapsed["us"])
elapsed["us"] += 2_000_000
assert clock.read() == 1482515549
snapshot = clock.to_config()
restored = rt.CalendarClock.from_config(snapshot)
elapsed["us"] += 2_000_000
assert restored.now() == datetime(2024,2,29,12,34,58)
assert clock.now() == datetime(2024,2,29,12,35,0)
```

For host elapsed time, explicitly supply `lambda: time.monotonic_ns()//1000` after
importing Python's time module. For deterministic task execution, a callback can
read the owning TaskScheduler's `now_us`. DELAY does not advance a frozen clock;
an advancing clock observes only its chosen adapter.

SET_TIME resets the calendar anchor at the current elapsed sample. A previous
successful observation remains the lower bound for the elapsed adapter, even
after setting a different date. Backward/invalid samples, callback failures and
elapsed times outside 1980..2107 raise source-located errors without replacing
the anchor or a pending GET output. Earlier source effects remain. An invalid
SET value is rejected before sampling. Async callbacks/results are rejected.

Calendar time is separate from GET_USEC_TIM's two-minute counter and connected
timers' global millisecond storage. SET_TIME does not alter those services.
Contexts shared by programs and linked routines share the same calendar object.
Pause/resume retains that object; an advancing clock can continue during a pause.
Clock callbacks run synchronously and remain responsible for returning promptly.

## Configuration and persistence

```json
{"calendar":{"value":"2024-02-29T12:34:57.123456"}}
```

Configuration requires a complete naive ISO datetime, with optional one-to-six
fractional digits. Snapshot output uses six fractional digits and preserves the
complete current value. A restored clock is frozen: callbacks, elapsed origins
and continuation state are not serialized. The host can construct a new advancing
clock from the restored datetime and explicitly supply its adapter.

Generated scripts accept this service through their existing `--context` option;
`--state-out` saves the latest value after successful completion. See the
[frozen-clock example](../examples/calendar_clock.kl) and
[clock-setting example](../examples/calendar_reset.kl). The translation report's
`calendar_clock_policy` describes these choices. Value-free `service_requests`
record GET_TIME/SET_TIME operation, source line and outcome.

The [semantic ledger](semantics/calendar_clock_semantics.json) records the supplied
manual locators and its inconsistent SET_TIME field descriptions. This implementation
uses the shared GET_TIME table layout. Native timing, host/controller clock
configuration, locale/timezone discovery and strict mode remain outside this scope.
