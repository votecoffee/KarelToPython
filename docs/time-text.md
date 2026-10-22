# Pythonic time text

Since 0.76.0, Pythonic mode supports `CNV_STR_TIME(source,target)` and
`CNV_TIME_STR(source,target)` for explicit packed date/time data. They use the
documented date/time bit layout and Python's Gregorian calendar validation.

```karel
PROGRAM PYTHONIC_TIME_TEXT
%ENVIRONMENT TIM
VAR encoded,bad,epoch: INTEGER text,epoch_text: STRING[20]
BEGIN
  CNV_STR_TIME('29-FEB-2024 12:34:57',encoded)
  CNV_TIME_STR(encoded,text)
  CNV_STR_TIME('01-JAN-1980 00:00',epoch)
  CNV_TIME_STR(epoch,epoch_text)
  CNV_STR_TIME('31-APR-2024 00:00:00',bad)
  WRITE(text,CR)
  WRITE('epoch=',epoch_text,', invalid=',bad::0,CR)
END PYTHONIC_TIME_TEXT
```

The first output is `29-FEB-2024 12:34:56`. Odd seconds round down to the previous
even second. The epoch value is `2162688`; the invalid April date writes zero.
The [authored example](../examples/pythonic_time_text.kl) has independent
[snapshot](../examples/pythonic_time_text.expected.json) and
[output](../examples/pythonic_time_text.write.expected.json) fixtures.

## Parsing and packing

Input uses ASCII `DD-MMM-YYYY HH:MM[:SS]`. Day, hour, minute and supplied seconds
have exactly two digits, and the year has four. English month names JAN through
DEC are case-insensitive. Outer whitespace is allowed; the internal separator
is a single space. Omitted seconds mean zero.

Valid years are 1980..2107, with real Gregorian dates, hours 0..23, minutes
0..59 and seconds 0..59. Invalid text, including an invalid calendar date,
overwrites the INTEGER output with zero. Unknown input, wrong runtime types,
non-ASCII input and input longer than 254 characters raise `KarelRuntimeError`
and preserve the output. Ordinary STRING capacity rules apply before conversion.

| Packed bits | Value |
| --- | --- |
| 31..25 | Year minus 1980 |
| 24..21 | Month 1..12 |
| 20..16 | Day 1..31, checked against month/year |
| 15..11 | Hour 0..23 |
| 10..5 | Minute 0..59 |
| 4..0 | Seconds divided by two, rounded down, 0..29 |

The 32-bit pattern is stored as a signed INTEGER. Dates from 2044 onward
therefore have negative values; formatting reinterprets those same bits.
Ordinary signed comparisons across the 2043/2044 boundary do not establish
chronological order. These are calendar fields without a timezone, offset or
Unix epoch interpretation.

## Complete formatting and outputs

`CNV_TIME_STR` always emits 20 characters: `DD-MMM-YYYY HH:MM:SS`, using uppercase
English months independent of host locale. It decodes the signed INTEGER as a
32-bit pattern and validates every field. Zero and impossible dates or clock
fields raise; there is no guessed date, truncation or overflow marker.

Parsing requires exact INTEGER output storage. Formatting requires a concrete
STRING capacity in 20..254, sufficient for all 20 characters. Targets can be
ordinary variables, fields, ARRAY elements or reference formals. STRING
reference formals keep their caller's capacity; grouped value arguments use
writable private storage. Type, initialization, capacity and decoded-field
failures preserve the target. Earlier argument effects remain.

Arguments are captured once, left to right: source value, then target reference.
Conversion occurs after both captures. A target-index function cannot change
the captured source, but its effects persist if conversion subsequently fails.
Uninitialized source reads fail before target-index effects occur. Outputs
participate in transitive routine write analysis and active FOR-counter checks.
Existing CONFIG/POSITION reference protection and routine/FOR cleanup remain.

The names are fallback procedures: explicit internal routines keep their own
signatures, function results and effects. Ordinary declarations remain usable.
Reports expose source-located `time_text_conversions` and `time_text_policy`.

## Evidence boundary

The reviewed [reference edition](references.md), PDF pages 342-343 and the
GET_TIME table on page 415, supplies the conversion signatures, optional seconds,
invalid-text zero and packed fields. Its displayed year and formatting text is
inconsistent, and SET_TIME's detail bullets disagree with its table. This
implementation explicitly chooses four-digit years, complete seconds, fixed
English months, odd-second flooring, signed bit patterns and checked failures.
Native formatting, invalid-packed behavior and odd-second behavior are unverified.

These procedures convert supplied data without clock access. Version 0.87.0 adds
[GET_TIME and SET_TIME](calendar-clock.md) through a separate explicit offline
calendar service. Timezone conversion and controller scheduling remain unsupported. The TIM
directive is metadata. Offline checks do not establish controller acceptance;
strict mode remains a future milestone.
