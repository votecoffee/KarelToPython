# Offline services and cooperative execution

Version 0.91.0 extends explicit Pythonic implementations for registers and ports,
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
| `CHECK_EPOS` | Explicit-frame RobotContext check | Supplied DH model or synchronous three-operand callback, selected group, portable 0/1 result and protected status; see [position checks](position-checks.md). |
| `ERR_DATA` | Shared bounded ErrorHistory | Oldest/next/latest lookup, disjoint outputs, message capacities 40..254 and optional text/time metadata; see [error history](error-history.md). |
| `CNV_CNF_STRG` | Explicit ConfigTextFormats group profiles | Selected flags/turns, optional caller-rooted group, portable missing-group status and persisted JSON; see [group CONFIG text](group-config-text.md). |
| `GET_STR_REG`, `SET_STR_REG` | `StringRegisters` dictionary | Explicit count and ASCII capacity; reads copy and truncate to destination capacity. |
| `GET_POS_REG`, `SET_POS_REG`, `SET_EPOS_REG` | `PositionRegisters` keyed by group and number | Complete independent Cartesian values; getter returns XYZWPREXT. |
| `GET_JPOS_REG`, `SET_JPOS_REG` | Same bank with typed joint values | Getter pads complete narrow joints to nine slots; stored width is retained. No implicit pose/joint conversion. |
| `POS_REG_TYPE`, `CLR_POS_REG` | Stored representation/axes and group value removal | Inspect without conversion; clear one or all groups; independent comments retained. |
| `DIN/DOUT`, `RDI/RDO`, `RDIN/RDOUT` | `PortBank` Boolean values | Host supplies inputs; translated assignments write output kinds only. |
| `GIN/GOUT`, `AIN/AOUT` | Nonnegative checked `int`, finite `float` | Explicit counts and values; no zero-filled or hardware defaults. Analog float values are a portable choice. |
| `PULSE DOUT[n] FOR ms [NOWAIT]` | Timed logical DOUT values | Checked rounded durations, explicit host polling or scheduler virtual time, caller ownership and terminal freeze. |
| `GET_VAR`, `SET_VAR` | Checked references and `VariableStore` | Static globals, bounded ARRAY/partial data and independent logical queue copies; foreign programs use attached namespaces or explicit bindings. See [variable transfers](variable-transfers.md) and [queue transfers](queue-transfers.md). |
| `VAR_INFO`, `VAR_LIST` | Static global metadata and bounded name catalogs | Canonical type codes, ARRAY dimensions, capacities, portable flags and sorted/paged output; see [variable inspection](variable-inspection.md). |
| `PROG_LIST` | Attached Programs and explicit immutable program metadata | Type filters, star patterns, sorted pages, 15/39-character formats and optional cursor; see [program listing](program-listing.md). |
| `LOAD_STATUS`, `GET_ATTR_PRG`, `SET_ATTR_PRG` | Attached Programs and explicit ProgramAttributes snapshots | Any known global data, selected typed reads, four metadata writes, activity guards and persisted snapshots; see [program metadata](program-metadata.md). |
| Remote `RGET_*` / `RSET_*` | Explicit PeerBanks numeric/string/position-comment/port banks | 17 procedures, isolated peer lookup, portable statuses and persisted updates; see [remote banks](remote-banks.md). |
| `RNUMREG_RECV/SEND`, `RPOSREG_RECV/SEND` (also `RPREG_*`) | Caller and selected peer numeric/position banks | Snapshot copies, selected comments, explicit groups, checked destinations and persisted updates; see [register transfers](register-transfers.md). |
| `UNPOS` | Checked pose-value decomposition | POSITION/XYZWPREXT, expressions and model-backed joints; independent source capture and disjoint outputs; see [pose decomposition](pose-decomposition.md). |
| MOVE forms / VIA / hands / ATTACH / RELEASE | Explicit MotionRequests and GroupLocks | Detached bounded request capture or immediate scripted results, logical hand state and ownership; no trajectories or robot feedback. See [motion requests](motion-requests.md). |
| MOTION_CTL / CNCL_STP_MTN / SET_PERCH / RESET / MIXBG_RUN / MIXBG_STOP | Explicit ControllerServices plus ownership/port/task banks | Logical control labels, detached six-axis perches, scripted reset acknowledgement/faults and background suspension/resume; see [controller services](controller-services.md). |
| `GET/SET_PORT_VAL`, `GET/SET_PORT_SIM`, `GET/SET_PORT_CMT` | Shared PortBank values plus simulation/comment metadata | Explicit INTEGER type-code mapping; outputs or simulated inputs can be written; bounded scalar conversions. |
| `CLR_PORT_SIM` | Remove a logical simulation flag | Retain last supplied value/comment; subsequent indirect input writes require simulation again. |
| `GET/SET_PORT_ASG`, `GET/SET_PORT_MOD`, `IO_MOD_TYPE` | Explicit topology, active/pending settings and module metadata | Checked assignment spans and modes; host applies staged settings; logical values stay independent. See [I/O configuration](port-configuration.md). |
| `GET/SET_REG_CMT`, `GET/SET_PREG_CMT`, `GET/SET_SREG_CMT` | Independent bank comment storage | Numeric/position/string capacities 16/16/254; does not initialize values. |
| `GET_TPE_PRM` | Explicit per-root-task CallParameters | Arguments 1..10, type 1/2/3, unused outputs preserved, absent status 17042. |
| `OPEN/CLOSE FILE`, `READ file`, `WRITE file` | `MemoryFiles`/`DirectoryFiles` and `FileHandle` | Byte buffers or an explicit directory root, cursors and checked scalar transfers. |
| Binary FILE fields | Standard-library `struct` | Little endian; INTEGER 1/2/4 bytes, REAL 4/8, BOOLEAN/BYTE 1, SHORT 2, ASCII STRING with byte width. |
| Five XML input calls | Explicit text RO FILE with ATR_XML | Bounded registered-tag scanning, attribute/text chunks and atomic nested scalar updates on user/built-in records; see [XML input](xml-input.md). |
| GET_PORT_ATR / SET_PORT_ATR | Explicit SerialPorts configuration metadata | Seven attributes, ports 1..5, checked values and JSON persistence; see [serial attributes](serial-attributes.md). |
| P1:..P5: FILE streams | Explicit SerialStreams finite or opted-in host-fed RX/TX data | Atomic text/binary input, explicit EOF, appended output and close-time RX consumption. Exclusive FILEs, bounded state and no host device access; see [serial streams](serial-streams.md) and [waiting](serial-waiting.md). |
| Six device/storage calls | Explicit DeviceFiles virtual volumes | Shared FILE namespace, quotas, mount/closed-file guards, purge/format and supplied information; see [virtual devices](virtual-devices.md). |
| `GET_FILE_POS`, `SET_FILE_POS`, `BYTES_LEFT`, `BYTES_AHEAD`, `IO_STATUS`, `CLR_IO_STAT` | Checked cursor/status operations | Byte positions, seek within current contents; `-1` seeks to end. |
| FILE attributes | ATR_IA interactive flush; ATR_UF binary; ATR_REVERSE byte order; ATR_EOL record terminator; ATR_FIELD capacity-sized STRING reads | Portable package identifiers; `RB/WB/RWB/AB` also select binary. |
| COPY_FILE / DELETE_FILE / RENAME_FILE / FILE_LIST | Explicit ordinary file backends and configured plain pipes | Synchronous operations, portable missing/exists/busy statuses; [wildcard COPY/DELETE batches](wildcard-file-operations.md), [preflighted renames](wildcard-rename.md), [virtual-volume batches](cross-volume-rename.md), [pipe batches](pipe-wildcard-files.md), [listing formats 0 through 4](file-listing.md), atomic pages and blank timestamps. |
| TRANSLATE | Opt-in SourceTranslations with an ordinary FILE backend | Bounded source to sibling Python and optional listing; preserved source, explicit overwrite and no product execution. See [source translations](source-translations.md). |
| LOCKGROUP / NOLOCKGROUP directives | Opt-in GroupLocks root and nested module policies | Atomic configured-group acquisition; default metadata only, callee scopes require a second flag. See [directive locks](directive-group-locks.md) and [scoped locks](scoped-group-locks.md). |
| CHECK_NAME / MOVE_FILE | Portable name grammar; both explicit backends for moves | Base names without extensions; RD/FR wildcard batches with collision/busy/size preflight and explicit late-failure behavior. See [file management](file-management.md). |
| `COMPARE_FILE` | Same-numbered ASCII records or binary first difference | Closed inputs, open writable result FILE, bounded JSON report and portable statuses. |
| `PRINT_FILE` | Existing WRITE recorder/callback | Validated ASCII in <=254-character synchronous chunks; both nowait values supported. |
| `PATH` | Typed node list with optional header | One-based nodes; `NODEDATA` and `PATHHEADER` structures; direct field references. |
| PATH/QUEUE persistence | Typed logical collection snapshots | Partial PATH data, queue order/sequence and explicit first-use buffer rebinding; see [collection persistence](collection-persistence.md). |
| `APPEND_NODE`, `INSERT_NODE`, `DELETE_NODE`, `PATH_LEN`, `COPY_PATH` | Checked list operations and deep copies | Empty paths have length zero; full or reversed partial copying; maximum 32767 nodes. |
| `NODE_SIZE`, `INTSCT_VL_PL` | Packed portable node-schema bytes and supplied line/plane intersections | Structural view-line/point PATH schemas, staged append, normalized projected polarity and explicit frame/group metadata; see [PATH geometry](path-geometry.md). |
| `QUEUE_TYPE` and seven queue procedures | FIFO entries with sequence IDs and an INTEGER backing array | Explicit INIT_QUEUE; fixed capacity; retain original backing-array identity. |
| `CONDITION`, `WHEN`, `ENABLE/DISABLE/PURGE` | Ordered predicates and generator actions | Checkpoint/interval scanning, events/edges, EVAL capture, multiple WHEN clauses and explicit rearm. |
| `CONNECT/DISCONNECT TIMER` | Monotonic elapsed milliseconds in global INTEGER references | Updated at execution checkpoints; injectable microsecond clock; fractional milliseconds carried forward. |
| `GET_TIME`, `SET_TIME` | Explicit CalendarClock | Shared packed date/time fields; frozen or supplied elapsed adapter; zero set no-op; no operating-system clock write. |
| `PAUSE`, host `resume()` | Suspended Python generator | Retains instruction position, routine locals, references and FOR state. |
| `STOP`, host `stop()` | Terminal offline task state | Closes suspended frames; construct a new Program to restart. This is a Pythonic task-stop convention, not native motion STOP behavior. |
| `RESUME`, `UNPAUSE` | Clear a pending offline pause request | A suspended Program needs a host `resume()` or another registered task's CONT_TASK call. Native motion RESUME is not modeled. |
| `RUN_TASK`, `PAUSE_TASK`, `CONT_TASK`, `ABORT_TASK` | Explicit `TaskRegistry` | TaskRegistry or deterministic TaskScheduler; no motion flags, lock masks or arbitrary start line. |
| `GET_TSK_INFO` | Registered task lookup plus live execution data or supplied attributes | Directional name/number operands; selected output only; portable identifiers and statuses. |
| `SET_TSK_NAME` | In-place task binding rename | Stable task numbers, caller-rooted self lookup, retained waits/attributes/errors and collision preflight; see [task renaming](task-renaming.md). |
| `SET_TSK_ATTR` and seven task directives | Applied task policies and bounded checkpoint traces | Nine checked settings, cooperative priority/slice effects, origin masks and explicit capability flags; see [task attributes](task-attributes.md). |
| TP program management and position/comment calls | Explicit TeachPrograms logical store | 17 calls with root-owned access, grouped data, metadata integration and typed JSON; see [TP program data](teach-programs.md). |
| TP caller-local registers | Twelve numeric/string/grouped position calls over explicit TP caller bindings | Independent per-program banks, linked-root scope, foreign handle rejection and typed JSON; see [TP local registers](teach-registers.md). |
| `ROUTINE ... FROM library` | Python callback or source Project link | Typed references/results, shared imported globals; no native ABI. |
| `MIRROR(point,plane,orient)` | Reflection about the plane frame's XZ plane | XYZWPREXT result; optional orientation reflection uses a documented proper-rotation convention. |
| Extended pose assignments, `:`, `INV`, `FRAME`, `APPROACH`, `ORIENT` | Existing checked frame math plus external metadata | Three explicit external-axis REAL fields; propagation rules below. |
| `JOINT2POS`, `POS2JOINT`, `IN_RANGE`, `J_IN_RANGE` | `RobotContext` adapters and supplied limits | Requires a supplied model or limits; no robot geometry, calibration or reachability is inferred. |
| JOINTPOS/Cartesian whole assignment | Supplied forward/inverse model and selected frame/tool | Calling root group; inverse requires current-joint seed; no current-state update or physical motion. |
| Joint geometry operands | Supplied forward model and selected frame/tool | Colon/INV/FRAME/MIRROR, axis queries and approximate comparison use independent Cartesian values; see [joint geometry](joint-geometry.md). |
| `CURPOS`, `CURJPOS`, `CURR_PROG` | Explicit current RobotState, optional configured DH math and executing module name | Independent results, optional groups and checked/discarded masks; no physical state acquisition. |

See [file comparison and printing](file-comparison.md) for report format,
source capture, budget, callback and failure behavior.

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
Unknown paths return status 1; incompatible GET/SET types or ARRAY ranks return 3.
Same-rank ARRAY transfers copy the smaller element count and preserve the receiver
tail. Typed missing/partial data propagates with status 12311; unknown BYTE remains
distinct. Complete replacements are prepared before writes. See
[variable transfers](variable-transfers.md) for capture timing and type rules.
Foreign storage is supplied with `VariableStore.define(program,path,spec,value)`
or `bind(program,path,reference)`. Whole QUEUE_TYPE values copy logical state
and release receiver buffer binding; an uninitialized queue copies with status
12311. Files, paths and protected positional fields remain excluded as generic
variable outputs. See [queue transfers](queue-transfers.md).

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
See [task inspection](task-inspection.md) for GET_TSK_INFO, active linked-routine
identity, checkpoint lines, logical frame counts and supplied task metadata.

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

[Numeric variable transfers](numeric-variable-transfers.md) add checked
integral-family/integral-to-REAL scalar and same-rank prefix conversion in both
GET_VAR and SET_VAR. [Built-in XML roots](xml-record-roots.md) use explicit
VECTOR/CONFIG/pose record schemas with atomic protected leaf updates. Neither
feature discovers controller state or changes native execution evidence.

[Positional variable transfers](positional-variable-transfers.md) add complete
Cartesian/joint-width value conversion to GET_VAR/SET_VAR, with exact ARRAY leaves
and no inferred kinematics. [Synchronous program calls](synchronous-program-calls.md)
reuse attached ordinary source bodies under the caller's ownership. Supplied
[16-bit images](vision-16bit-images.md) retain big-endian samples through PNG and
context JSON; BMP precision reduction and native acquisition remain unavailable.
