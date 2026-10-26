# Remaining Pythonic support

Audited on 2026-10-24 against the 465-heading, multi-edition KAREL feature
inventory, the programmer reference and the implemented parser/runtime. This is
a product backlog, not a controller compatibility certificate. The inventory
contains statements, actions, clauses, types and directives as well as calls;
one heading does not equal one executable feature or one percentage of coverage.

The inventory has 334 distinct built-in names after merging repeated headings.
Currently, 188 have a registered translation and 146 do not.
Registration means a supported form exists; it does not mean every overload,
option, type, controller release or native behavior is implemented. Calls outside
this reference set can also be rejected. The complete remaining name list is
below. The [support guide](language-support.md) describes accepted forms.
Some exclusions, such as whole-array UNINIT, retain documented language rules;
they are boundaries rather than promises to accept every such source form later.

## Language and source forms

- `%INCLUDE` and unknown directives. The four original metadata directives,
  seven [task policies](task-attributes.md) and nine additional
  [source policies](source-directives.md#additional-source-policies) are accepted.
  DEFGROUP selects offline defaults and CRTDEVICE labels I/O requests; native
  storage, group locks, periodic delay, stack allocation and real device routing
  are not applied. Include expansion and binary environments remain unavailable.
- Native motion statements: `MOVE TO`, `MOVE NEAR`, `MOVE AWAY`, `MOVE ABOUT`,
  `MOVE ALONG`, `MOVE AXIS`, `MOVE RELATIVE`; their `VIA`, motion `WITH`, `WHEN`
  and `UNTIL` clauses; motion ownership and hand control. `ATTACH`, `RELEASE`,
  `OPEN HAND`, `CLOSE HAND`, `RELAX HAND`, `HOLD`, `UNHOLD`, `CANCEL`,
  `CANCEL FILE` and standalone `PURGE` are not translated. `PURGE CONDITION`
  is supported. `IN GROUP[n]` does not add motion or other native `IN` clauses;
  `IN DRAM` storage placement is unavailable.
- Handler actions involving native motion, hold/unhold or file cancellation;
  path-node arrival (`A TNODE`) conditions. Checkpoint predicates, events, port
  edges, semaphores, errors and lifecycle notifications have offline models.
  TIME-style behavior uses connected timers and comparisons; motion timing,
  asynchronous native interrupts and motion-local handlers are unavailable.
- Arbitrary `GOTO` entry into nested blocks or across FOR scopes; local TYPE
  sections, external FROM types and forward/self/cyclic type aliases.
- `USING` selectors containing indexes, calls or grouping; builtin-record USING,
  field FOR counters and dynamic caller scope. SELECT is INTEGER-only; a miss
  without ELSE fails. Recursion is bounded at 64 calls.
- Unicode/multilingual source, native graphic characters, multiline literals,
  backslash string escapes, token-splicing continuations and arbitrary native
  preprocessor/compiler extensions.

## Types, expressions and interfaces

- `COMMON_ASSOC`, `GROUP_ASSOC`, `DISP_DAT_T` and obsolete `STD_PTH_NODE`
  association layouts. PATH supports authored NODEDATA/PATHHEADER structures;
  it does not reconstruct native group-qualified association records.
- Dynamically resized/ragged arrays, unknown runtime wildcard dimensions, ranks
  above three and aggregates exceeding the 32767-leaf prototype bound. Global
  wildcard declarations require translation-time shapes; no VR auto-discovery.
- Standalone BYTE/SHORT variables and routine interfaces; they remain aggregate
  field/element and file forms. BYTE unknown contents cannot be queried with
  UNINIT. SHORT 32767 is the retained uninitialized sentinel.
- Whole ARRAY, PATH, user STRUCTURE, FILE and QUEUE_TYPE UNINIT queries; arbitrary
  partial aggregate copies/results, flattening, nominal-type coercion, unspecified
  STRING result-element capacities and resource fields in structures.
- VECTOR frame transformations; direct joint field/index access; implicit
  pose/joint conversions in exact routine, RETURN and whole-array interfaces.
  POSITION orientation columns remain recursively read-only source storage.
- Unbounded/Unicode strings, lengths above 254, implicit numeric-to-BOOLEAN
  truthiness, arbitrary-size INTEGERs, MAXINT as ordinary initialized storage,
  NaN/Infinity and exact native numeric/storage/rounding equivalence. Public
  Pythonic mode uses finite Python float and practical numeric equivalents.
- Native external routine ABI, PC binary execution and automatically discovered
  libraries. FROM linkage uses supplied typed source modules or explicit callbacks.

## Registers, variables and I/O

- Live controller banks, physical I/O reads/writes, rack/slot discovery, hardware
  routing, automatic polling and native alarm/status mappings. Numeric, string,
  position and port services use explicit offline banks.
- Automatic system-variable schemas, arbitrary host/Python attribute access,
  dynamic routine-local lookup, native cached variable table IDs and runtime
  variable creation/rename. GET_VAR/SET_VAR support declared/explicit roots,
  checked static paths and documented aggregate/queue transfers.
- Automatic application of staged I/O assignments/modes. The host must explicitly
  apply the supplied offline configuration. Remote bank calls model named peers;
  they do not establish network sessions, discover peers or convert robot poses.
- Native TP caller-stack discovery and local register allocation remain unavailable.
  Twelve [TP local register calls](teach-registers.md) now use explicit caller
  bindings and per-program banks, distinct from ordinary registers, TP program
  positions and GET_TPE_PRM parameters. Seventeen [TP program data calls](teach-programs.md)
  model logical programs, grouped positions, comments and metadata; native TP
  files, execution and physical controller data remain unavailable.

## Files and collections

- Native device mounting/formatting/purging, sockets, serial devices, pipes,
  device discovery and unrestricted absolute-path file access. Backends are
  MemoryFiles or explicitly rooted DirectoryFiles.
  GET_PORT_ATR/SET_PORT_ATR now retain [explicit serial configuration](serial-attributes.md)
  with seven checked attributes; they do not open ports or exchange serial data.
- Proprietary PC/VR/native binary layouts, arbitrary FILE attributes/listing
  formats, device-specific parsing and controller file alarms. Text and binary
  scalar operations use the documented portable formats and bounded sizes;
  FILE_LIST supports name format 0.
- Physical PATH node byte sizes, native association records and native message
  attachments. NODE_SIZE uses [portable packed schema widths](path-geometry.md).
  QUEUE_ATTACH is a separate message-attachment API; QUEUE_TYPE uses a fixed INTEGER buffer,
  FIFO entries and portable sequence/status conventions.
- Persisting live file handles, callbacks, connected clocks, queue buffer
  references, Python closures, generator/call stacks or suspended task execution.
  JSON stores values and logical collection state; it is not a task checkpoint.
- XML writing, DTD/entity processing, Unicode, namespace interpretation and
  native streaming/error equivalence. All five [XML input calls](xml-input.md)
  now support bounded ASCII FILE scanning and checked flat structure updates;
  live scanners and registrations are omitted from saved JSON.

## Tasks, handlers and programs

- Native preemption, priorities, CPU time slices, group locks, interrupt ordering,
  instruction pointers, allocated stack-byte reporting and native parent/child
  relationships. The scheduler runs deterministic cooperative checkpoints.
- Native STOP/RESUME motion behavior. Offline STOP is terminal; resume/continue
  acts on retained cooperative generators. Arbitrary start lines, motion flags
  and lock masks in task procedures remain outside their supported forms.
- Native task policy effects remain unavailable. SET_TSK_ATTR now has nine
  [offline settings](task-attributes.md), including cooperative priority/slice
  policies, request masks and bounded tracing. Other attributes remain read-only
  or require explicit informational metadata. SET_ATTR_PRG retains its four
  metadata writes and activity guards.
- SET_TSK_NAME now has an [offline implementation](task-renaming.md), including
  stable task numbers and retained scheduler state. Native task naming rules and
  controller task identifiers remain unverified.
- Native program load/save/translate/backup/clear/restore, dynamic BYNAME calls,
  task discovery and implicit external linkage. Program catalogs and load status
  describe explicitly attached programs or supplied metadata.
- Native alarm dictionaries, severity encodings, asynchronous history timing,
  power-cycle restoration and controller error recovery. POST_ERR, POST_ERR_L,
  ERR_DATA, semaphores and lifecycle conditions have explicit offline contracts.

## Geometry and robot context

- Physical motion, controller/servo/safety integration and live robot state.
  No geometry, current pose, frame, tool, axis limits or tolerance is discovered
  from hardware; supply it explicitly.
- Calibrated robot-specific geometry, native CONFIG branch selection, collision
  checks and certified/native reachability. Standard-DH models use bounded
  numerical IK; failure to find a solution is not proof of impossibility.
- Unconfigured groups/axes, coupled mechanisms and external axes beyond the
  supplied model's supported width and trailing-axis mapping. Three XYZWPREXT
  metadata slots do not model arbitrary physical external-axis behavior.
- Native reflection/Euler singularity/configuration/default conventions and all
  robot-specific type conversions. MIRROR, framed conversions, range checks and
  CHECK_EPOS are implemented under documented portable conventions.

## Option-specific systems and application milestones

- Native TP parsing/generation/execution, motion instruction linkage and embedded
  register APIs. The explicit TeachPrograms store supports logical position/comment
  editing and opaque line deletion without those native behaviors.
- Controller screens, windows, keyboard interaction, display controls, dictionaries
  and language packs.
- DAQ pipelines, PC data/event exchange, message/pipe/remote-monitor networking,
  KCL commands, controller XML services, vision and conveyor/vision tracking.
  These calls have no implicit Python or hardware fallback.
- The workbench currently validates/translates/reviews/exports. The planned Python
  runner, input-parameter editor, read-before-write discovery and combined
  input/result JSON are still [future work](roadmap.md).
- Public strict mode remains a future milestone. `--mode strict` is rejected;
  preserved historical exactness work is not an available public execution mode.

## Evidence still needed

The manual inventory combines editions and options. Some headings lack a complete
signature, installed environment definitions or an accepted compiler probe.
The reference campaign spans 20 releases; its accepted cases establish acceptance
of particular source forms, not all overloads or runtime behavior. Rejection can
also reflect probe syntax, missing environment/support files or an option.

Runtime equivalence on FANUC controllers, native ABI/binary formats, native status
enums and option-specific commissioning remain unverified. Authored public tests
establish translation and offline behavior only. Manuals and private compiler
campaign reports remain outside this public repository. See
[reference provenance](references.md) and the current per-feature semantic notes;
older conservative ledgers can contain restrictions superseded by Pythonic guides.

## Built-ins with no registered translation

This list is exhaustive for distinct built-in names in the audited inventory.
An explicit user routine can use one of these names, but that does not implement
the corresponding controller built-in. Names are grouped by purpose; grouping
does not assert a particular installed option or environment.

### Vision and tracking (53)

- `IRVU_VRGETMEAS`
- `IRVU_VRGETOFFSET`
- `IRVU_VRGETVIEW`
- `VREG_FND_POS`
- `VREG_OFFSET`
- `VT_ACK_QUEUE`
- `VT_CLR_QUEUE`
- `VT_DELETE_PQ`
- `VT_GET_AREID`
- `VT_GET_FOUND`
- `VT_GET_LINID`
- `VT_GET_PFRT`
- `VT_GET_QUEUE`
- `VT_GET_TIME`
- `VT_GET_TRYID`
- `VT_PUT_QUE2`
- `VT_PUT_QUEUE`
- `VT_READ_PQ`
- `VT_SET_FLAG`
- `VT_SET_LDBAL`
- `VT_WRITE_PQ`
- `V_ACQ_VAMAP`
- `V_ADJ_2D`
- `V_CAM_CALIB`
- `V_CAM_CHECK`
- `V_CLR_VAMAP`
- `V_CSAPI_GETVALUE`
- `V_CSAPI_NUMSET`
- `V_CSAPI_RESETDATA`
- `V_CSAPI_SAVEDATA`
- `V_CSAPI_SETVALUE`
- `V_CSAPI_TESTRUN`
- `V_DISPLAY4D`
- `V_FIND_VIEW`
- `V_FIND_VLINE`
- `V_GET_FOUND`
- `V_GET_OFFSET`
- `V_GET_PASSFL`
- `V_GET_QUEUE`
- `V_GET_READ`
- `V_GET_VPARAM`
- `V_INIT_QUEUE`
- `V_IRCONNECT`
- `V_LED_OFF`
- `V_LED_ON`
- `V_OVERRIDE`
- `V_RALC_QUEUE`
- `V_RUN_FIND`
- `V_SAVE_IMREG`
- `V_SET_REF`
- `V_SNAP_VIEW`
- `V_START_VTRK`
- `V_STOP_VTRK`

### Screens, windows, keyboard and dictionaries (40)

- `ACT_SCREEN`
- `ACT_TBL`
- `ADD_DICT`
- `ATT_WINDOW_D`
- `ATT_WINDOW_S`
- `CHECK_DICT`
- `CLEAR`
- `CNC_DYN_DISB`
- `CNC_DYN_DISE`
- `CNC_DYN_DISI`
- `CNC_DYN_DISP`
- `CNC_DYN_DISR`
- `CNC_DYN_DISS`
- `DEF_SCREEN`
- `DEF_WINDOW`
- `DET_WINDOW`
- `DISCTRL_ALPH`
- `DISCTRL_FORM`
- `DISCTRL_LIST`
- `DISCTRL_PLMN`
- `DISCTRL_SBMN`
- `DISCTRL_TBL`
- `FORCE_SPMENU`
- `INIT_TBL`
- `INI_DYN_DISB`
- `INI_DYN_DISE`
- `INI_DYN_DISI`
- `INI_DYN_DISP`
- `INI_DYN_DISR`
- `INI_DYN_DISS`
- `POP_KEY_RD`
- `PUSH_KEY_RD`
- `READ_DICT`
- `READ_DICT_V`
- `READ_KB`
- `REMOVE_DICT`
- `SET_CURSOR`
- `SET_LANG`
- `WRITE_DICT`
- `WRITE_DICT_V`

### Communications and PC exchange (13)

- `ADD_BYNAMEPC`
- `ADD_INTPC`
- `ADD_REALPC`
- `ADD_STRINGPC`
- `MSG_CONNECT`
- `MSG_DISCO`
- `MSG_PING`
- `PIPE_CONFIG`
- `QUEUE_ATTACH`
- `RMCN_ALERT`
- `RMCN_SEND`
- `SEND_DATAPC`
- `SEND_EVENTPC`

### Data acquisition (6)

- `DAQ_CHECKP`
- `DAQ_REGPIPE`
- `DAQ_START`
- `DAQ_STOP`
- `DAQ_UNREG`
- `DAQ_WRITE`

### Native devices and storage (6)

- `DISMOUNT_DEV`
- `DOSFILE_INF`
- `FORMAT_DEV`
- `MOUNT_DEV`
- `PURGE_DEV`
- `VOL_SPACE`

### Motion and task management (8)

- `CNCL_STP_MTN`
- `LOCK_GROUP`
- `MIXBG_RUN`
- `MIXBG_STOP`
- `MOTION_CTL`
- `RESET`
- `SET_PERCH`
- `UNLOCK_GROUP`

### Programs, dynamic variables and controller commands (20)

- `BYNAME`
- `CALL_PROG`
- `CALL_PROGLIN`
- `CHECK_STACK`
- `CREATE_VAR`
- `FORCE_LINK`
- `KCL`
- `KCL_NO_WAIT`
- `KCL_STATUS`
- `LOAD`
- `PROG_BACKUP`
- `PROG_CLEAR`
- `PROG_RESTORE`
- `RENAME_VAR`
- `RENAME_VARS`
- `SAVE`
- `SAVE_DRAM`
- `SET_DB_EVENT`
- `SET_DEBUG`
- `TRANSLATE`
