# Canceling READ_KB editors

Pythonic `CANCEL FILE input_file` now interrupts the exact active READ_KB editor
on that explicitly opened keyboard FILE. It uses the existing injected event
service and opens no desktop window, hardware keyboard or controller connection.

```karel
CONDITION[1]:
  WHEN elapsed>=50 DO CANCEL FILE input_file
ENDCONDITION
ENABLE CONDITION[1]
READ_KB(input_file,text,254,KC_DISPLAY,KC_ENTER_KEY,-1,'seed',count,key,status)
io=IO_STATUS(input_file)
CLOSE FILE input_file
```

Supply and connect elapsed explicitly under a scheduler, as in the
[timer project](../examples/read_kb_cancel_timer_project/main.kl). The source
[checkpoint example](../examples/read_kb_cancel_keys.kl) uses a deterministic
predicate counter to demonstrate cancellation between already queued keys.
These are explicit offline models of source behavior, without native timing.

## Outputs, events and history

Cancellation returns normally. The procedure's status output and IO_STATUS are
portable value 6. Edited text, count and terminating-key outputs are not published;
earlier explicit changes to those variables remain. The caller continues after
READ_KB. Requesting cancellation repeatedly is idempotent and allocates no new
request/history ID. Canceling an idle registered FILE sets IO_STATUS zero and
does not affect a future read or discard data.

Already consumed key events remain consumed. Unpublished line-editor text is
retained only in terminal request history and its last logical echo; it is not
inserted into the destination, completed-line history or a future READ_KB buffer.
Unconsumed events remain queued. A later read can consume that suffix, as the
[retry example](../examples/read_kb_cancel_retry.kl) demonstrates.

History records one READ_KB outcome of `cancelled`, with text, term zero and
status 6. No ordinary source READ observation is fabricated. The READ_KB source
procedure returns successfully with its portable cancellation status; its existing
service-call observation retains the normal completed-call convention.

## Blocking checkpoints and polling

Positive-timeout and indefinite READ_KB calls visit execution checkpoints after
each consumed nonterminating key, including ignored keys. Scheduled readers
therefore permit other tasks and global handlers to run between ready keys.
Each such checkpoint consumes the ordinary source budget and scheduler quantum.
Paused snapshots retain the latest editor text.

Positive deadlines include this scheduled processing time. Input at the exact
deadline remains eligible; later processing times out under the existing timeout
output rules. Cancellation wins when requested at that boundary. A timeout is
separate from cancellation and retains its existing partial-result behavior.

A zero-time READ_KB poll retains its atomic ready-input behavior and consumes no
per-key scheduler quantum. It processes immediately available keys until completion
or exhaustion, subject to existing capacities and the 4096-key limit. It does not
wait for future input. A completed poll is idle when a later CANCEL FILE runs.

## Identity, pause and cleanup

The editor retains the actual FILE, backend binding and active request identity.
It validates endpoint, pane, echo binding, FILE attributes, attribute domains and
history/buffer ownership before cancellation or continued publication. A copied,
redirected, replaced or malformed registration fails before cancellation can
conceal the change. Active-ID equality alone is not ownership proof. Cleanup
removes only owned registrations and retains a foreign replacement for explicit
recovery. Pending READ_KB, typed READ and CLOSE keep their overlap/busy guards.

READ_KB does not consume a byte cursor. Explicit WRITE through an RW combined
window FILE can advance its output position while reading; it does not retarget
the editor. A malformed negative/noninteger position still fails. Echo/noecho and
captured pane semantics retain their existing rules. Cancellation does not clear
or restore the window surface. See the [window project](../examples/read_kb_cancel_window_project/main.kl).

Pause retains the editor and captured outputs. Cancellation of a paused reader
leaves it paused until explicit resume. Stop, sticky abort and budget failures
retain their precedence and cannot publish canceled outputs. A canceled suspended
reader can unwind without becoming eligible for keys; PUSH_KEY_RD frames remain
until explicit POP, as in the [suspension project](../examples/read_kb_cancel_suspended_project/main.kl).

Live handles, editors and unpopped suspension frames still prevent context save.
After ordinary close/POP, JSON retains unconsumed events, logical time and terminal
history. Pending tokens, handle identities, frames and suspended execution are
not serialized or restored.

Fileless menu/alphanumeric controls and direct typed backend read generators keep
their separate lifetimes. Omitted/default FILE aliases, physical keyboard capture,
native alarm/status equivalence and public strict mode remain outside this model.
See [typed FILE cancellation](file-cancellation.md), [keyboard input](keyboard-input.md)
and the [45 authored regression cases](../tests/test_read_kb_cancellation.py).
