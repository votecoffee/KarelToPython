# Offline task inspection

Version 0.88.0 adds GET_TSK_INFO over the existing TaskRegistry and TaskScheduler.
The host binds cooperative Programs explicitly; source-project linkage binds its
supplied modules automatically. Inspection does not launch or resume a task.

## Selecting a task and outputs

The source form is
`GET_TSK_INFO(task_name,task_no,attribute,value_int,value_str,status)`.
Both identity operands must be writable STRING/INTEGER variables. The value
outputs require writable INTEGER/STRING storage too; all five references must
be disjoint, including array/record descendants.

When task_no is uninitialized or zero, task_name is an input. Name lookup is
case-insensitive and a successful call fills task_no, preserving the input name.
Otherwise the positive task_no selects a registered task and the call writes
its uppercase binding name into task_name. Numbering follows the current
one-based registry insertion order, the same order used by numeric task control.
Rebinding an existing name retains its slot.
SET_TSK_NAME also retains that slot while changing the binding name and moving
its metadata and scheduler state; see [task renaming](task-renaming.md).

TSK_PROGNAME and TSK_ROUTNAME write only value_str. Other attributes write only
value_int. Unused value outputs retain their previous state. STRING results
follow normal destination-capacity truncation. Failed calls preserve both
identity operands and both value outputs; only status changes.

| Portable status | Meaning |
| --- | --- |
| 0 | Success |
| 1 | No task matches the supplied name or positive number |
| 2 | Unknown attribute or negative task number |
| 3 | Known attribute requires metadata that was not supplied |

An uninitialized input name raises an ordinary initialization error. Invalid
types, protected references, output overlap and FOR-counter writes fail before
inspection outputs change. Inputs and reference selectors are captured once in
source order. Earlier completed source effects remain on a later failure.

```python
from karel2py import translate, runtime as rt

context = rt.ExecutionContext()
namespace = {"__name__": "worker_demo"}
exec(translate("PROGRAM WORKER VAR count: INTEGER BEGIN count=1 PAUSE count=2 END WORKER").python_source, namespace)
Worker = namespace["Program"]
worker = Worker(context=context)
context.tasks.bind("worker", worker, attributes={"TSK_PRIORITY": 50})
try:
    worker.run()
except rt.KarelPause:
    pass

observer_source = """PROGRAM OBSERVER
VAR name,text: STRING[16] number,value,status: INTEGER
BEGIN
  name='worker'
  GET_TSK_INFO(name,number,TSK_STATUS,value,text,status)
END OBSERVER"""
observer_namespace = {"__name__": "observer_demo"}
exec(translate(observer_source).python_source, observer_namespace)
Observer = observer_namespace["Program"]
result = Observer(context=context).run()
assert result["NUMBER"] == 1
assert result["VALUE"] == rt.TASK_CONSTANTS["PG_PAUSED"]
assert result["STATUS"] == 0
assert worker.task_state == "paused"
```

An empty registry returns unknown-task status; it does not discover host processes
or implicitly register the inspecting Program. Binding aliases and source program
names can differ, as in the example. Bindings and inspection metadata are live
host configuration and are not serialized by ExecutionContext value snapshots.

## Live attributes

| Attribute | Pythonic value |
| --- | --- |
| TSK_STATUS | Current task state, including pending abort requests |
| TSK_PROGTYPE | PG_NOT_EXEC before execution begins; PG_AR_KAREL afterward |
| TSK_PROGNAME | Source module of the active routine, or the task's root module |
| TSK_ROUTNAME | Active routine name, or empty outside routines |
| TSK_LINENUM | Most recent source checkpoint line; zero before execution |
| TSK_STACK | Number of active logical routine frames, not an allocated byte size |
| TSK_TIMESLIC | Applied slice value, otherwise scheduler quantum in milliseconds or zero for synchronous registry execution |

The task state values are PG_RUNACCEPT (ready), PG_RUNNING, PG_PAUSED,
PG_ABORTED and PG_ABORTING (an undelivered abort request). Pythonic extensions
PG_COMPLETED, PG_STOPPED, PG_FAILED and PG_WAITING represent the other existing
runtime states. Inspection reports them without delivering requests or advancing
the target. PG_MNEMONIC is a named program-type constant but is not returned for
these KAREL Programs.

Paused routine names and frames remain available until resume, stop or failure
unwinds them. Linked library routines are attributed to the calling root task;
two tasks using the same library retain separate inspection stacks. External
declaration proxies count as logical frames. The line is a retained checkpoint,
not a native instruction pointer; it can remain from the last routine checkpoint
until the caller next ticks. Handler-captured local storage does not create an
additional active call frame merely by being retained.

## Supplied attributes and portable constants

When no applied policy supplies a value, these attributes require INTEGER metadata on
`bind(name,program,attributes={...})`: TSK_HOLDCOND, TSK_LOCKGRP, TSK_MCTL,
TSK_NOABORT, TSK_NOBUSY, TSK_NOPAUSE, TSK_NUMCLDS, TSK_PARENT, TSK_PAUSESFT,
TSK_PRIORITY, TSK_STEP, TSK_TPMOTION, TSK_TRACE and TSK_TRACELEN. Missing metadata
returns status 3. Binding validates the entire mapping before replacing a task
or its metadata. Dynamic execution fields cannot be supplied as bind metadata.

Metadata is informational: a priority value does not change scheduling, and
TSK_NOABORT does not suppress abort requests. Use the existing handler actions
and task APIs to change modeled behavior. SET_TSK_ATTR and seven task directives
now apply explicit policies, overriding matching informational reads; see
[task attributes](task-attributes.md). Parent and child relationships are not
inferred from synchronous or scheduled launch history.

All named TSK_/PG_ constants are package INTEGER identifiers, independent of
native controller enums. TSK attributes are 1..21 in the manual's listed order;
state IDs are 100..108 in the order recorded by the report; program types
PG_NOT_EXEC/PG_MNEMONIC/PG_AR_KAREL are 200/201/202. `rt.TASK_CONSTANTS` and
`task_inspection_policy.constants` expose the full mapping. Use these named
constants in portable source; predefined names cannot be redefined. Four portable
request-mask bits are also named: PG_NP_ERROR=1, PG_NP_CMD=2, PG_NP_END=4 and
PG_NP_TPENB=8, with their separate uses documented in the task attribute guide.

The [two-task example](../examples/task_inspection_project/main.kl) inspects a
worker before launch, during pause and after completion:

```sh
python -m karel2py.project examples/task_inspection_project --entry MAIN
```

The [semantic ledger](semantics/task_inspection_semantics.json) records manual
locators and the Pythonic choices. Native task IDs, attribute/status enums,
stack byte counts, priorities, interrupts, motion and strict mode remain separate
work. Service records retain operation/line/outcome without inspection values.
