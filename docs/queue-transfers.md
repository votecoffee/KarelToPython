# Queue transfers

Since 0.99.0, Pythonic GET_VAR and SET_VAR transfer whole QUEUE_TYPE logical
values through explicit global namespaces. This extends
[variable transfers](variable-transfers.md) and reuses the checked queue
snapshot format from [collection persistence](collection-persistence.md).

```karel
PROGRAM queue_demo
VAR source,target: QUEUE_TYPE
    source_data: ARRAY[2] OF INTEGER
    target_data: ARRAY[3] OF INTEGER
    entry,status,value,sequence: INTEGER
BEGIN
  INIT_QUEUE(source)
  APPEND_QUEUE(7,source,source_data,sequence,status)
  SET_VAR(entry,'','TARGET',source,status)
  GET_QUEUE(target,target_data,value,sequence,status)
END queue_demo
```

This returns `VALUE=7`, `SEQUENCE=1`, `STATUS=0`. SOURCE still contains its entry.
TARGET consumed its independent copy using a different, explicitly supplied
ARRAY. The [transfer example](../examples/queue_transfer.kl) also exercises
INSERT order, sequence gaps and replacing a previously bound receiver.

## Copied state and ownership

A transfer copies the queue's initialization flag, ordered sequence/value pairs
and last issued sequence counter. FIFO order is preserved, including inserted
entries whose sequence IDs are out of numeric order. Empty initialized queues
retain their counter, so later APPEND_QUEUE continues issuing IDs correctly.

Both queues must be whole QUEUE_TYPE values. Queue/data type mismatches return
status 3 without changing the entry output or receiver. Whole FILE/PATH values
and resources embedded inside ARRAY/STRUCTURE remain excluded. Ordinary QUEUE
assignment, value parameters and RETURN retain their existing exclusions.
UNINIT(whole_queue) and VAR_INFO's unsupported QUEUE metadata code also remain
unchanged; transfer status uses the explicit flag described below.

The receiver keeps its QueueValue object where it already exists, receives an
independent entries list, and releases its old backing ARRAY binding.
Transfer does not synchronize or clear any ARRAY. This
applies even to self-copy. A distinct source queue retains its original buffer
and logical contents; the copied state shares neither entries nor buffer with it.

The receiver's next queue operation supplies an INTEGER ARRAY large enough for
the copied entries. That first operation binds the ARRAY and follows normal
synchronization rules, including zeroing unused slots. Its capacity can differ
from either former buffer. An undersized ARRAY fails before binding or consuming
an entry. Once bound, later operations retain the ordinary same-buffer rule.
INIT_QUEUE intentionally clears the copied entries/counter and releases binding.

## Initialization, ordering and failures

An initialized queue, including an empty one, transfers with status 0. As a
portable choice, copying a queue whose initialization flag is FALSE replaces
the receiver with an empty uninitialized queue and returns status 12311. A whole
missing source marker supplied by the host normalizes to that same logical state.
The receiver then requires INIT_QUEUE before ordinary queue operations. See the
[missing-queue example](../examples/queue_missing.kl). These rules do not infer a
native queue initialization bit or enable general resource UNINIT queries.

SET_VAR captures a validated independent queue snapshot at its fourth argument,
before later status-selector effects. GET_VAR resolves and snapshots its named
source after output selectors have run. All expressions run once in source
order. Generic queue reference formals and linked routines use the same rules.
An empty program string still selects the executing module's globals.

Both source and receiver are validated before commit. Known values and sequence
IDs use checked INTEGER domains. IDs must be distinct, positive and no greater
than the counter; at most 32767 entries are allowed. An uninitialized queue
cannot contain entries, a nonzero counter or a buffer. A supplied bound buffer
must be an adequately sized one-dimensional INTEGER ARRAY with valid shape.

Malformed source state raises before later SET selectors. A malformed receiver
raises after argument capture, retaining earlier selector effects. Neither
failure publishes cache IDs, queue changes or transfer outputs. Exact/disjoint
output checks and SET's dynamic entry/status-overlap guard remain in force.
Completed source statements and earlier host effects remain visible on errors.

## Host context and persistence

Explicit host definitions can supply queue snapshots:

```python
from karel2py import runtime as rt

queue = rt.QueueValue()
queue.initialized = True
queue.sequence = 3
queue.entries = [(2, 70), (1, 50)]
context = rt.ExecutionContext()
reference = context.variables.define("LIB", "JOBS", ("QUEUE_TYPE",), queue)
queue.entries.clear()
assert reference.raw().entries == [(2, 70), (1, 50)]
assert reference.raw().buffer is None
```

`VariableStore.define` validates and detaches an explicit queue value. Attached
programs and explicit bindings can be read or written by GET_VAR/SET_VAR. Typed
context save/load preserves the transferred flag, order and counter; loaded
queues again bind an explicit buffer on first use. No call stacks are restored.

The generated `queue_transfer_policy` describes snapshot, initialization,
ordering and ownership choices; `variable_transfer_policy` links the broader
service contract. Runtime service records contain operation, line and outcome
without data values. See the [semantics ledger](semantics/queue_transfer_semantics.json)
for reviewed source locators and the authored verification coverage.

These are portable logical copies. Native queue/VR bytes, exact copy ownership,
cache/status equivalence, message-queue attachment and controller execution
remain outside this implementation. Strict mode is a future milestone.
