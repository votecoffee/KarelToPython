# Cooperative FILE cancellation

Pythonic `CANCEL FILE f` interrupts the exact active cooperative typed READ on
an explicitly opened FILE. [Dynamically created descriptors](dynamic-files.md)
participate through exact FILE routine aliases, including linked handlers. SerialStreams, opted-in waiting FilePipes, and keyboard
line/PASSALL FILE reads support cancellation. It opens no device or GUI.

```karel
CONDITION[1]:
  WHEN timeout DO CANCEL FILE f
ENDCONDITION
ENABLE CONDITION[1]
READ f(value,CR)
status=IO_STATUS(f)
CLOSE FILE f
```

Define and enable the handler before entering READ. The condition must become
true while that READ is active; canceling an idle FILE succeeds without affecting
a future READ. The example's timeout is an explicit BOOLEAN supplied by source
logic or a host driver, not an implicit native I/O timeout. Connected timers can
supply a condition in explicitly scheduled projects.

## Completion and data

The canceled READ returns normally and source execution continues after it.
`IO_STATUS(f)` is portable status 6. No destination, cursor or READ observation
is published for the canceled operation. Existing successful reads and writes
remain committed. A subsequent successful READ or an idle CANCEL resets status
to zero. Repeated cancellation of the same pending operation is idempotent.

Serial input retains the uncompleted READ prefix; CLOSE consumes only the prefix
from earlier successful reads. Pipes retain their existing circular/snapshot
rules and bytes. Keyboard submitted lines and PASSALL bytes remain in the open
handle's buffer for a later typed READ. Unsubmitted line-editor text has already
consumed its key events and is discarded when that editor is canceled. Closing
keyboard FILEs discards their remaining local buffers under the existing policy.
Keyboard request history records cancellation with status 6, without a fabricated
source READ completion or failure observation.

A registered idle FILE accepts cancellation as a no-op, preserving data, position
and open state. This includes ordinary memory/rooted files and already completed
atomic writes. Cancellation never truncates, flushes, closes or deletes a file.
There are no pending modeled writes to interrupt.

## Identity, handlers and lifetime

The explicit FILE selector is evaluated once. Reference parameters and linked
routines can pass the same live handle; global or motion-local handler actions
can request its cancellation. The request captures the active READ's identity.
Changing an active READ's FILE owner, endpoint, attributes, cursor or backend registration
fails before cancellation can conceal that change. Copied/foreign handles fail.
Independent readers and endpoints retain separate registrations.

Cancellation marks the operation for checked unwind. It does not close a running
generator from inside its own handler. CLOSE in that handler remains busy until
the READ has unwound; put CLOSE after READ as above. The owned registration is
removed exactly once on completion, cancellation, failure, stop or generator
close. A second overlapping READ cannot replace the first registration.

Pause retains the READ and its captured destinations. Cancellation of a paused
reader leaves it paused; resume completes the cancellation. Stop/abort and
existing step-budget failures retain their precedence and cleanup. Cancellation
does not restart a stopped task or clear a sticky abort.

Host drivers can call `runtime.cancel_file(state, handle, line=None)` for generated
cooperative reads and [READ_KB editors](read-kb-cancellation.md). Direct typed
backend generators retain separate lifetimes and reject this cancellation request.
Closed handles fail. Live handles still prevent context saves after a cancellation
request; close them explicitly after unwind. Closed context JSON retains only
existing service data/history, without operation tokens, callbacks or stacks.

## Boundaries and examples

An explicit FILE is required; omitted/default FILE aliases are not implemented.
Native pending WRITE interruption, hardware/controller timing and native status
enum equivalence remain unavailable. `CANCEL` and `CANCEL GROUP[...]` keep their
separate logical motion behavior. `PURGE CONDITION[n]` is already supported;
standalone PURGE is not a separate implemented source form.

See the authored [idle read/write example](../examples/file_cancel_idle.kl) and
scheduled linked [serial](../examples/file_cancel_serial_project/main.kl),
[pipe](../examples/file_cancel_pipe_project/main.kl) and
[raw keyboard](../examples/file_cancel_keyboard_project/main.kl) cancellation
projects. The regression suite also covers keyboard line reads, saved-context
replay, aliases, retries, pause/abort and independent roots.
