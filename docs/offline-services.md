# Offline services and cooperative execution

Version 0.87.0 extends explicit Pythonic implementations for registers and ports,
files and collections, task control, external routines and robot-model calls.
[Portable projects](portable-projects.md) documents persistence, directory files,
events/scheduling, automatic source linkage and loadable DH models.
[Control notifications](control-notifications.md) adds semaphore operations,
ERROR/POWERUP conditions and pending pause/abort suppression.
All state belongs to supplied Python objects. A missing service raises a
source-located error. Strict mode remains a future milestone.

## Equivalence matrix

| KAREL | Python implementation | Contract |
| --- | --- | --- |
| `GET_STR_REG`, `SET_STR_REG` | `StringRegisters` dictionary | Explicit count and ASCII capacity; reads copy and truncate to destination capacity. |
| `GET_POS_REG`, `SET_POS_REG`, `SET_EPOS_REG` | `PositionRegisters` keyed by group and number | Complete independent Cartesian values; getter returns XYZWPREXT. |
| `GET_JPOS_REG`, `SET_JPOS_REG` | Same bank with typed joint values | Getter pads complete narrow joints to nine slots; stored width is retained. No implicit pose/joint conversion. |
| `POS_REG_TYPE`, `CLR_POS_REG` | Stored representation/axes and group value removal | Inspect without conversion; clear one or all groups; independent comments retained. |
| `DIN/DOUT`, `RDI/RDO`, `RDIN/RDOUT` | `PortBank` Boolean values | Host supplies inputs; translated assignments write output kinds only. |
| `GIN/GOUT`, `AIN/AOUT` | Nonnegative checked `int`, finite `float` | Explicit counts and values; no zero-filled or hardware defaults. Analog float values are a portable choice. |
| `GET_VAR`, `SET_VAR` | Checked references and `VariableStore` | Static global paths such as `PARTS[2].VALUE`; foreign programs use attached namespaces or explicit bindings. No Python evaluation of paths. |
| `GET/SET_PORT_VAL`, `GET/SET_PORT_SIM`, `GET/SET_PORT_CMT` | Shared PortBank values plus simulation/comment metadata | Explicit INTEGER type-code mapping; outputs or simulated inputs can be written; bounded scalar conversions. |
| `CLR_PORT_SIM` | Remove a logical simulation flag | Retain last supplied value/comment; subsequent indirect input writes require simulation again. |
| `GET/SET_REG_CMT`, `GET/SET_PREG_CMT`, `GET/SET_SREG_CMT` | Independent bank comment storage | Numeric/position/string capacities 16/16/254; does not initialize values. |
| `GET_TPE_PRM` | Explicit per-root-task CallParameters | Arguments 1..10, type 1/2/3, unused outputs preserved, absent status 17042. |
| `OPEN/CLOSE FILE`, `READ file`, `WRITE file` | `MemoryFiles`/`DirectoryFiles` and `FileHandle` | Byte buffers or an explicit directory root, cursors and checked scalar transfers. |
| Binary FILE fields | Standard-library `struct` | Little endian; INTEGER 1/2/4 bytes, REAL 4/8, BOOLEAN/BYTE 1, SHORT 2, ASCII STRING with byte width. |
| `GET_FILE_POS`, `SET_FILE_POS`, `BYTES_LEFT`, `BYTES_AHEAD`, `IO_STATUS`, `CLR_IO_STAT` | Checked cursor/status operations | Byte positions, seek within current contents; `-1` seeks to end. |
| FILE attributes | ATR_IA interactive flush; ATR_UF binary; ATR_REVERSE byte order; ATR_EOL record terminator; ATR_FIELD capacity-sized STRING reads | Portable package identifiers; `RB/WB/RWB/AB` also select binary. |
| COPY_FILE / DELETE_FILE / RENAME_FILE / FILE_LIST | Both backends | Synchronous operations, portable missing/exists/busy statuses and name listing format 0. |
| `PATH` | Typed node list with optional header | One-based nodes; `NODEDATA` and `PATHHEADER` structures; direct field references. |
| `APPEND_NODE`, `INSERT_NODE`, `DELETE_NODE`, `PATH_LEN`, `COPY_PATH` | Checked list operations and deep copies | Empty paths have length zero; full or reversed partial copying; maximum 32767 nodes. |
| `QUEUE_TYPE` and seven queue procedures | FIFO entries with sequence IDs and an INTEGER backing array | Explicit INIT_QUEUE; fixed capacity; retain original backing-array identity. |
| `CONDITION`, `WHEN`, `ENABLE/DISABLE/PURGE` | Ordered predicates and generator actions | Checkpoint/interval scanning, events/edges, EVAL capture, multiple WHEN clauses and explicit rearm. |
| `CONNECT/DISCONNECT TIMER` | Monotonic elapsed milliseconds in global INTEGER references | Updated at execution checkpoints; injectable microsecond clock; fractional milliseconds carried forward. |
| `GET_TIME`, `SET_TIME` | Explicit CalendarClock | Shared packed date/time fields; frozen or supplied elapsed adapter; zero set no-op; no operating-system clock write. |
| `PAUSE`, host `resume()` | Suspended Python generator | Retains instruction position, routine locals, references and FOR state. |
| `STOP`, host `stop()` | Terminal offline task state | Closes suspended frames; construct a new Program to restart. This is a Pythonic task-stop convention, not native motion STOP behavior. |
| `RESUME`, `UNPAUSE` | Clear a pending offline pause request | A suspended Program needs a host `resume()` or another registered task's CONT_TASK call. Native motion RESUME is not modeled. |
| `RUN_TASK`, `PAUSE_TASK`, `CONT_TASK`, `ABORT_TASK` | Explicit `TaskRegistry` | TaskRegistry or deterministic TaskScheduler; no motion flags, lock masks or arbitrary start line. |
| `ROUTINE ... FROM library` | Python callback or source Project link | Typed references/results, shared imported globals; no native ABI. |
| `MIRROR(point,plane,orient)` | Reflection about the plane frame's XZ plane | XYZWPREXT result; optional orientation reflection uses a documented proper-rotation convention. |
| Extended pose assignments, `:`, `INV`, `FRAME`, `APPROACH`, `ORIENT` | Existing checked frame math plus external metadata | Three explicit external-axis REAL fields; propagation rules below. |
| `JOINT2POS`, `POS2JOINT`, `IN_RANGE`, `J_IN_RANGE` | `RobotContext` adapters and supplied limits | Requires a supplied model or limits; no robot geometry, calibration or reachability is inferred. |
| `CURPOS`, `CURJPOS`, `CURR_PROG` | Explicit current RobotState, optional configured DH math and executing module name | Independent results, optional groups and checked/discarded masks; no physical state acquisition. |

## Register, port and variable context

```python
from karel2py import translate
from karel2py.runtime import ExecutionContext, StringRegisters, PortBank

source = """PROGRAM DEMO
VAR text: STRING[8] status: INTEGER
BEGIN
  GET_STR_REG(1,text,status)
  DOUT[1]=DIN[1]
END DEMO"""
namespace = {"__name__": "offline_demo"}
exec(translate(source).python_source, namespace)
ports = PortBank({"DIN": 1, "DOUT": 1}, {("DIN", 1): True})
context = ExecutionContext(strings=StringRegisters(1, {1: "ready"}), ports=ports)
Program = namespace["Program"]
program = Program(context=context)
assert program.run()["TEXT"] == "ready"
assert ports.read("DOUT", 1) is True
```

Numeric registers retain their separate `Program(registers=NumericRegisters(...))`
interface. Other services use `Program(context=ExecutionContext(...))`.
String and position banks use portable status 0 success, 1 absent, 2 range/group
error and 3 representation mismatch. Failed position getters set status and
raise, preserving the assignment target. They never fabricate a pose.

`PositionRegisters(count, initial, groups=(1,))` accepts keys `number` or
`(group,number)` and checked Structure/JointPosition values. Reads and snapshots
are detached. String and port banks expose copied snapshots too. Shared context
objects retain writes across runs and programs.
See [I/O and CALL parameters](io-and-call-parameters.md) for indirect procedures,
simulation flags, comment persistence and supplied teach-pendant arguments.
See [register lifecycle](register-lifecycle.md) for stored representation codes,
axis counts, optional query groups, grouped clearing and logical unsimulation.

`GET_VAR(entry,program,path,value,status)` and SET_VAR use five arguments.
The entry output is a stable positive cache ID. An empty program string selects
the current program's globals, independently of current routine-local shadows.
Unknown paths return status 1; GET type mismatch returns 3. An uninitialized GET
clears the destination and returns 12311. SET validates before replacing storage.
Foreign storage is supplied with `VariableStore.define(program,path,spec,value)`
or `bind(program,path,reference)`. Files, queues, paths and protected positional
fields are not generic variable outputs.

Output/resource references must be ordinary writable exact types and disjoint,
including aggregate descendants. Inputs and reference selectors are captured once
in source order. Errors preserve earlier completed effects; they do not roll back
prior source statements. `Program.service_requests` returns defensive operation,
line and outcome records; it omits values and resets at each new run.

Generated scripts accept `--context configuration.json`. The JSON schema has
optional `strings` (`count`, `capacity`, `values`), `positions` (`count`, `groups`,
`values`), `numeric`, `ports` (`counts`, `values` by kind and number), `variables`,
`robot`, `events`, `calendar`, `local_handlers` and `files` (name to ASCII text or
`{"hex":"..."}`). Typed values retain aggregate/joint specs and initialization.
Callbacks, elapsed clock adapters and task registries use Python embedding. See
[configuration and persistence](portable-projects.md#shared-and-persistent-state).
The calendar value itself persists; its optional elapsed callback uses Python
embedding. See [calendar time](calendar-clock.md).

```sh
python -m karel2py examples/offline_services.kl -o converted.py
python converted.py --context examples/offline_services.services.initial.json
```

## Files and collections

`MemoryFiles({"input.txt":"42\n"})` holds named files. `snapshot()` returns
independent `bytes`. The per-file limit defaults to 16 MiB and can be explicitly
set up to 64 MiB. Access modes are `RO/R`, `WO/W`, `RW/UD`, and `AP/A`; writes
truncate in W and append in A. RW preserves existing contents. Handle assignment
aliases the same open handle, including close and cursor state.

Text transfers use the existing ASCII READ/WRITE formatters and CR defaults to LF.
ATR_EOL selects a custom ASCII record boundary. ATR_FIELD reads unformatted
STRINGs at declared capacity; explicit widths override it. Cursors count actual
bytes and failed text transfers preserve destinations and cursor. See the
[field and record guide](task-and-file-extensions.md#field-and-record-reads).
Binary fields use `::width`; unformatted INTEGER/REAL use four bytes. Binary
STRING writes default to content length and reads to destination capacity.
Explicit widths truncate/pad STRINGs with NUL. Binary reads validate the entire
transfer before writing outputs and restore the cursor on failure. Text reads
use the existing complete-response validation. End-of-file is an error, with
portable file status 1; successful transfers clear status to zero. This format
is portable project behavior, not a controller binary-file format claim.

```sh
python -m karel2py examples/offline_files.kl -o files.py
python files.py --context examples/offline_files.services.initial.json
```

PATH declarations follow KAREL spelling:

```karel
PROGRAM LIST_DEMO
TYPE node=STRUCTURE value: INTEGER ENDSTRUCTURE
     header=STRUCTURE count: INTEGER ENDSTRUCTURE
VAR entries: PATH NODEDATA=node, PATHHEADER=header
    status: INTEGER
BEGIN
  entries.count=1
  APPEND_NODE(entries,status)
  entries[1].value=42
END LIST_DEMO
```

Omitted NODEDATA supplies a portable STD_PTH_NODE with `NODE_POS: POSITION`.
Obsolete association records and group-qualified node types are not modeled.
Custom NODEDATA can include XYZWPREXT fields. Whole path copies are independent,
including unknown leaves. `COPY_PATH(source,0,0,destination,status)` copies all;
positive start/end select an inclusive range, reversed when start exceeds end.
Header data is retained in copied paths. Invalid bounds preserve the destination.
Resource fields in ordinary STRUCTUREs and arrays of paths remain unsupported.

Queue procedures are INIT_QUEUE, APPEND_QUEUE, INSERT_QUEUE, DELETE_QUEUE,
MODIFY_QUEUE, GET_QUEUE and COPY_QUEUE. Successful changes synchronize the backing
array, zeroing unused slots. Status 2 means full, 1 means bad sequence, and 61002
means empty for GET; these are portable statuses. INSERT goes before an existing
sequence. COPY starts at a specified sequence or the oldest entry for zero,
then skips the requested count and copies as many entries as fit.

`GET_QUEUE(queue,data,value,sequence,status)` follows the manual's parameter
descriptions and worked example. Its syntax line lists the last two arguments
in the opposite order; native/compiler confirmation remains open. Queue metadata
cannot be assigned as a value. See the authored
[collections example](../examples/offline_collections.kl).

## Cooperative tasks, handlers and timers

Task statements, handlers, connected timers and external routines automatically
select cooperative generation. `translate(source,cooperative=True)` or CLI
`--cooperative` also enables it for ordinary source; this choice is recorded in
the translation-context hash. A TaskRegistry accepts cooperative programs only.

```python
from karel2py import translate
from karel2py.runtime import KarelPause

namespace = {"__name__": "pause_demo"}
source = "PROGRAM DEMO VAR n: INTEGER BEGIN n=1 PAUSE n=n+1 END DEMO"
exec(translate(source).python_source, namespace)
program = namespace["Program"]()
try:
    program.run()
except KarelPause:
    assert program.task_state == "paused"
    assert program.snapshot()["N"] == 1
assert program.resume()["N"] == 2
assert program.task_state == "completed"
```

State names are ready, running, paused, completed, stopped, aborted and failed.
`pause()` requests suspension at the next checkpoint. `run()` cannot restart a
live suspended execution. `resume()` continues its existing budget and call
stack. `stop()` closes the suspended generator and clears active FOR counters
and frames. Bare ABORT remains sticky and distinct from a runtime failure.
Calls are synchronous; concurrent drive of one Program is unsupported.

Handlers 1..1000 scan at statements and loop tests, in definition order. The
first true WHEN clause runs and disables the handler before its actions.
An ENABLE action can rearm it. Multiple actions accept commas or newlines.
Purging is required before redefining an existing number; controls on undefined
numbers have no effect. Predicates use ordinary BOOLEAN expressions, including
explicit ports, or `WHEN PAUSE` for a pending pause. Handler definitions retain
their lexical frame references. Actions may call routines, assign values, control
handlers or pause/abort; local jumps, RETURN and nested definitions are rejected.
Handler reentry is suppressed. Actions for a pending pause run before suspension.
Scan intervals, event broadcasts and port edges follow the
[portable project conventions](portable-projects.md). Native interrupt priorities
and motion scanning are outside the model.

Connected timers require global INTEGER storage. Updates carry fractional
milliseconds and reject backward clocks or overflow. Timers poll at checkpoints,
including empty loop tests; no background thread runs while Python is idle.
Elapsed wall time during a pause is applied on the next checkpoint. An injected
`clock_us` should supply nonnegative integer microseconds for connected timers.
Handlers/timers that could modify a FOR counter are conservatively rejected.

`TaskRegistry.bind(name,program)` supplies named targets. RUN_TASK requires line
0, no motion and lock mask 0. PAUSE_TASK/ABORT_TASK reject motion flags. CONT_TASK
continues a paused target; task calls return status 1 for unknown names. Child
tasks run synchronously until completion, pause or intentional ABORT/STOP;
runtime failures still propagate. Remote pause/abort requests are queued for
target checkpoints so its handlers can suppress them. The no_wait flag does
not change this portable behavior. See [task requests](task-and-file-extensions.md#task-requests).
No source program can launch
an arbitrary host process.

External declarations use `ROUTINE name(parameters): result_type FROM library`.
Bind `ExecutionContext(externals={("LIBRARY","NAME"): callback})`. Callbacks
receive checked Reference objects; use `raw()` and `set(value)` for parameters.
Procedures return None; functions return a checked declared value. Callback
errors unwind frames while preserving prior writes. Linkage is explicit and
does not imply native ABI or cross-program global storage discovery.

## Geometry and robot context

CURPOS/CURJPOS use explicit current snapshots in RobotContext, with optional
DH-based Cartesian evaluation. Host updates and grouped state persist as typed
JSON. CURR_PROG names the executing module. See
[current robot state](current-robot-state.md) for mask handling, unused joint
slots, caller groups and the boundary between supplied and measured state.
See [joint interoperability](joint-interoperability.md) for composing those
values with model conversions and range checks, plus persisted frame/tool updates.

Whole assignments convert POSITION, XYZWPR and XYZWPREXT. Widening fills three
external-axis fields with zero; narrowing drops them. Routine interfaces remain
exact types. INV preserves external fields. Colon composition takes external
fields from the right operand if extended, otherwise the left. FRAME uses the
origin operand's external fields, otherwise zero. Frame operators propagate these fields as metadata. Explicit serial-DH models
can instead give external joints a kinematic role. Extended `>=<` uses supplied
per-axis absolute tolerances; see [model context](portable-projects.md#robot-models-and-extended-poses).

MIRROR reflects locations about a supplied frame's XZ plane and preserves the
point's external fields and CONFIG. With orientation false, orientation is
unchanged. With true, the world reflection is followed by reversal of local Y
to retain a right-handed proper rotation. This is an explicit Pythonic choice:
reflecting all three axes alone would produce an improper rotation.

RobotContext supplies `forward`, `inverse`, `reachable` and/or `joint_limits`,
or loads a standard-DH model through `from_config`.
JOINT2POS calls `forward(joints,uframe,utool,config_ref)` and expects a tuple
`(pose,config,external_axes)`. POS2JOINT calls
`inverse(reference_joints,pose,uframe,utool,config_ref,config,external_axes)` and
expects a matching JointPosition. Inputs are independent copies; outputs are
validated before assignment, including external-array length and joint width.
Successful calls write status zero; adapter errors raise with the source line.

IN_RANGE calls `reachable(complete_pose)` and requires a Boolean result.
J_IN_RANGE compares every axis against explicit inclusive `(minimum,maximum)`
limits, one pair per declared joint. Missing models/limits raise. These checks
do not establish collision clearance, controller reachability or commissioning
acceptance. Model adapters can be tested without any robot connection.

The integration tests cover all four service areas and invalid inputs. The
public examples use authored state and independent expected fixtures. Reference
provenance and unresolved behavior are retained in the
[semantic ledger](semantics/extended_service_semantics.json).
