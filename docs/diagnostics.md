# Offline diagnostics

CHECK_STACK, SET_DEBUG and SET_DB_EVENT require an explicit DiagnosticLog in the
ExecutionContext. The model provides selected source events and logical stack
estimates. It does not inspect native controller memory, execute p-code or enable
a FANUC diagnostic option.

```json
{"diagnostics":{"stack_words":4096,"frame_words":32,"limit":500}}
```

```karel
SET_DB_EVENT(CALL,TRUE)
SET_DB_EVENT(RTN_FRM_RTN,TRUE)
SET_DEBUG(TRUE)
CHECK_STACK(TRUE,FALSE,current_free)
-- Call the routines being inspected.
CHECK_STACK(FALSE,TRUE,lowest_free)
SET_DEBUG(FALSE)
```

## Stack model

Available logical words are `max(0, stack_words - frame_words * active_frames)`.
Top-level source starts at depth zero. Each offline routine/program activation
adds one configured frame cost; source-linked external bridge frames are included.
The existing depth limit remains 64. Reaching zero in this estimate does not add
a new native stack-overflow policy or change source execution.

CHECK_STACK(initialize, low_water, output) returns current availability when
low_water is FALSE, or the smallest observed availability since initialization
when TRUE. A TRUE initializer resets the low-water mark to current availability.
Initialization is required before a low-water query. Entering calls and executing
checkpoints update the mark even when no stack query occurs at the deepest level.

The diagnostic supplement labels initialize INTEGER in its declaration but uses
TRUE/FALSE throughout its examples and prose. Pythonic mode accepts BOOLEAN or
INTEGER 0/1, including checked narrow field values. The low_water argument remains
BOOLEAN. An ordinary writable INTEGER receives the result; literal zero discards
it, matching the documented initialization example. Output type, overlap,
POSITION/CONFIG protection and active-counter guards remain.

## Events and ownership

Both a task enable flag and global event selection are required. SET_DEBUG changes
the calling root task's flag; linked modules share that flag. SET_DB_EVENT changes
the global selected set for every enabled task in the supplied context. The host
logging_enabled switch gates all records. default_enabled selects a new run's
initial task flag; its default is FALSE.

Eight supported labels have portable IDs, independent of native DEBUG encodings:

| Event | Offline observation |
| --- | --- |
| LOG_ENABLE / LOG_DISABLE | Explicit task logging changes. |
| START_K_LINE / PCODE_EXEC | Offline source/call-entry checkpoints. |
| CALL / RTN_FRM_RTN | Offline activation entry/return, including bridge frames. |
| TASK_START / TASK_END | Root run entry and one terminal cleanup observation. |

PCODE_EXEC is a source-checkpoint approximation; it does not claim actual p-code
execution. Parent budget/handler scans do not duplicate the leaf module's records.
Unknown event IDs fail explicitly. Native motion, hardware, interrupt, packet and
other diagnostic events are not synthesized.

Rows contain a monotonic sequence, event label, root task program, executing
module, routine, source line and offline depth. They contain no variable values.
The ring retains the latest limit rows (default 500, maximum 4096). New source
runs reset task flags/low-water state; pause/resume retains them. Abort, stop,
errors and completion produce at most one selected TASK_END observation.

## Persistence and CLI

```sh
python -m karel2py examples/diagnostics.kl -o diagnostics.py
python diagnostics.py --context examples/diagnostics.services.initial.json --state-out diagnostics-state.json
python -m karel2py.project examples/diagnostics_commands_project --entry MAIN --context examples/diagnostics_commands_project/services.initial.json
```

`rt.DiagnosticLog(...)` is also accepted by `ExecutionContext(diagnostics=...)`.
Context JSON saves model configuration, global selections, sequence and bounded
records. Live task flags, frame references and low-water activation state are not
serialized; loading is not task resumption. CHECK_STACK must initialize again in
a new activation when low-water queries are needed.

`diagnostic_policy` in translation reports and the
[semantics ledger](semantics/diagnostic_semantics.json) describe this chosen
contract. Strict mode and native/controller diagnostic acceptance remain future
work. See [scripted KCL](kcl-commands.md) for command-result scenarios.
