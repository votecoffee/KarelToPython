# Error history queries

Pythonic mode supports `ERR_DATA` over the shared offline `ErrorHistory`:

```karel
VAR
  seq,code,cause,stamp,severity: INTEGER
  message,reason: STRING[80]
  owner: STRING[12]
BEGIN
  seq=0
  ERR_DATA(seq,code,message,cause,reason,stamp,severity,owner)
END
```

Set `seq=0` to read the oldest retained record. Each successful call updates
`seq` and the seven output fields. Calling again selects the next greater
retained sequence, including across gaps and evicted records. At the end, or
with no history, only `seq` is set to zero; the other outputs keep their values.
Negative or uninitialized cursors raise an error before any output changes.

`ERR_DATA(MAXINT,code,message,cause,reason,stamp,severity,owner)` reads the newest
record and discards its sequence output. A literal `2147483647` or a named
constant with that value also works, including parentheses. This is an explicit
Pythonic adaptation: ordinary INTEGER storage still rejects MAXINT, so assigning
it to a cursor variable remains unsupported. Ordinary cursors must be writable
INTEGER variables, fields or array elements.

Both message destinations need declared capacity **40 through 254**. Message
and program text right-truncate to each actual destination capacity. All output
references must be ordinary, exact-type, disjoint writable storage; active FOR
counters remain protected through routine calls. The service validates all
returned fields before publishing any outputs.

## Messages and timestamps

Existing records remain valid. Without optional presentation metadata:

- `error_string` returns the recorded `parameter` text.
- `cause_string` returns an empty string; the numeric cause is retained.
- `time_int` returns **0, meaning unknown**, not a valid packed calendar date.
- `severity` returns the existing portable 0 warning, 1 pause or 2 abort value.
- Source-posted errors return an empty program name; other origins return their
  supplied program name, truncated to the output capacity.

Hosts can supply known text and a packed timestamp without an alarm dictionary:

```python
from datetime import datetime
from karel2py import runtime as rt

history = rt.ErrorHistory(limit=1000)
clock = rt.CalendarClock(datetime(2026, 10, 23, 12, 34, 56))
history.post(15018, cause=42, program="MAIN",
             error_string="Authored example error",
             cause_string="Authored example cause", time_int=clock.read())
context = rt.ExecutionContext(errors=history)
```

Presentation strings must be ASCII with at most 254 characters. `time_int` must
be a valid packed time or the explicit unknown value zero. Metadata is optional
and survives `ExecutionContext` JSON save/load. Invalid metadata is rejected
before appending a record or advancing its sequence. IDs are in 1..2147483646;
exhaustion raises instead of wrapping into the MAXINT selector.

Source `POST_ERR` and `POST_ERR_L` capture a timestamp when their context has an
explicit [calendar clock](calendar-clock.md). Without one, no clock is acquired
and their timestamp remains unknown. Runtime-failure notifications also keep
an unknown timestamp, preserving the original failure without sampling a possibly
failing clock. `ERR_DATA` itself never samples a clock or creates an empty history.

## Notification and compatibility boundaries

Queries include suppressed records and all program scopes in the retained
history. They do not consume `ERROR` handler notifications or modify records.
Host `ErrorHistory.read_after(seq)` offers the same traversal and returns a
defensive copy, or `None` at exhaustion.

This implementation makes posted records visible synchronously and chooses
strictly greater sequence traversal. It does not reproduce controller history
timing, native alarm text, facility dictionaries or controller side effects.
The manual warns that a just-posted controller error may not yet be visible.
See [control notifications](control-notifications.md) for posting and task effects,
the [semantic ledger](semantics/error_history_semantics.json) for provenance, and
the authored [example](../examples/error_history.kl) for CLI execution.
