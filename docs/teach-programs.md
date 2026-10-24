# Offline TP program data

Version 26.1024.144946 adds 17 TP program calls over an explicitly supplied
`TeachPrograms` store. It holds logical program records and positions. It does
not parse, generate or execute native TP programs, connect to a pendant, perform
motion or discover controller data.

## Calls and records

| Calls | Pythonic behavior |
| --- | --- |
| CREATE_TPE / COPY_TPE / SELECT_TPE | Create a typed logical program, deep-copy its data, or retain an offline selection. |
| OPEN_TPE / CLOSE_TPE | Root-owned access handles and symmetric sharing rejection. |
| AVL_POS_NUM / DEL_INST_TPE | Lowest unrecorded position number across groups; delete a one-based opaque instruction line. |
| GET_POS_TPE / GET_JPOS_TPE | Independent extended Cartesian or zero-padded JOINTPOS9 result. |
| SET_POS_TPE / SET_EPOS_TPE / SET_JPOS_TPE / SET_TRNS_TPE | Store Cartesian, extended, exact-width joint or matrix POSITION data. |
| GET_POS_TYP / GET_POS_FRM | Stored representation/axis count and explicit frame/tool identifiers. |
| GET_TPE_CMT / SET_TPE_CMT | Position comments with capacity checks and documented truncation warning. |

The source signatures appear in the translation report's `service_policy` and
`teach_program_policy`. Names use case-insensitive, letter-starting ASCII
identifiers of 1..36 characters, without `.TP` or paths. CREATE_TPE accepts the
existing portable PT_MNE_UNDEF / PT_MNE_JOB / PT_MNE_PROC / PT_MNE_MACRO constants,
represented in the store as TP / JB / PR / MR.

Each record contains opaque single-line ASCII instructions, grouped complete
positions, position comments and four writable header fields. Instructions are
at most 254 characters each and 32767 lines; deletion shifts following lines.
No TP instruction syntax, position references or execution semantics are inferred.
Deleting a line leaves positions/comments intact. AVL_POS_NUM examines recorded
positions, without reserving a slot or analyzing instruction text.

## Explicit context and JSON

```python
from karel2py import runtime as rt

bank = rt.TeachPrograms(
    {"DEMO": {"type": "TP", "instructions": ["authored line"]}},
    groups=(1, 2), position_limit=100, program_limit=16,
)
context = rt.ExecutionContext(teach_programs=bank)
assert bank.create("job", "JB") == 0
```

Groups must be distinct integers in 1..32. Position limits are 1..32767 and
program limits 1..4096; defaults are group 1, 32767 positions and 256 programs.
These are portable bounds, independent of a controller's capacities.

Constructor program rows accept `type`, `instructions`, `positions`, `comments`
and `attributes`. Each position row contains `group`, `number`, a checked runtime
`value`, and optional `uframe`/`utool` integers in 0..32767. Comments map canonical
decimal position-number strings to at most 16 ASCII characters and require an
existing position in some group. Attributes accept AT_OWNER, AT_COMMENT,
AT_SRC_NAME and AT_SRC_VRSN under the existing header capacities.

`to_config()` returns detached JSON-ready records; `from_config()` decodes typed
position values. Context JSON uses the `teach_programs` key and includes group/
capacity configuration, all records and optional `selected` name. A position's
`value` contains `type` and `value`, using the existing typed-state format. See
the [authored initial context](../examples/teach_programs.services.initial.json).

Save/load keeps data and selection, omitting handles, access/reject locks, owner
objects and handle sequence. Open handles therefore need reopening after load.
Snapshots taken while open include completed immediate data updates; they are
logical state snapshots, without native TP files or suspended task restoration.

## Handles and ownership

OPEN_TPE takes `name,open_mode,reject_mode,open_id,status`. Access modes are zero
(no data access), TPE_RDACC (1) and TPE_RWACC (2). Reject modes are TPE_NOREJ (0),
TPE_RDREJ (1), TPE_WRTREJ (2), TPE_RWREJ (3) and TPE_ALLREJ (4). These are package
identifiers. Conflicting access/reject choices are checked in both directions
between different owners, including ALLREJ against no-access opens. A root may
open the same program more than once. Each handle remains subject to its access.

Handles are positive, monotonically allocated INTEGERs, with at most 1024 open
and no wrap/reuse within the store's lifetime. Source operations require the
calling root to own the handle. FROM-linked routines share that root, so handles
survive routine return and task rename. Pause retains handles; completion,
runtime failure, abort and stop release only that root's handles.

The host API exposes `create`, `copy`, `select`, `open`, `close`, `read_position`,
`write_position` and `release_owner`. Pass the same explicit `owner` token to
related host handle operations; omitted owner means one shared host owner.
Operations return a status, or `(status, value)` for open/read. `entries` and
`open_count` expose detached catalog entries and live handle count.

Copy requires closed source/destination records and refuses a selected target.
An existing destination requires overwrite=TRUE. Selection refuses an open
program and changes only the store's selected name; no task or robot starts.

## Positions, metadata and comments

The two position getters and three grouped setters accept optional final group.
Omission uses the calling root's group or portable group 1. SET_TRNS_TPE uses
that same root default; GET_POS_TYP/GET_POS_FRM require explicit groups.

Cartesian setters accept complete POSITION/XYZWPR/XYZWPREXT values and normalize
to the requested representation. Extended writes/reads retain external slots;
widening plain data fills them with zero, narrowing drops them. Same-format
writes preserve angles and values. POSITION conversion checks proper matrices.
No pose/joint kinematics are inferred. Joint writes retain the input width;
joint getters pad to nine axes without changing stored width.

GET_POS_TYP returns 2 for XYZWPR, 6 for XYZWPREXT and 9 for JOINTPOS, plus portable
1 for matrix POSITION. Its second output is joint width, three external metadata
slots for XYZWPREXT, or zero for plain/matrix positions. These are stored-data
facts rather than discovered physical axes. GET_POS_FRM returns supplied IDs.
Source setters preserve existing IDs; new records start at portable IDs 0/0.
Host write_position can explicitly supply new IDs. No active frame/tool or
robot context is silently substituted.

Position comments apply across groups. SET_TPE_CMT truncates overlong text to
16 and returns warning 7 after the update. GET_TPE_CMT requires space for the
complete comment: status 8 preserves an undersized destination. Missing comments
on recorded positions return empty text; missing positions return 17038.

Explicit TP records also join PROG_LIST and LOAD_STATUS. Header queries derive
program type and instruction count and support four writable header fields via
GET_ATTR_PRG/SET_ATTR_PRG. Open/selected records block header writes. Separate
ProgramAttributes snapshots can supply other metadata and retain their existing
precedence; copying TP records copies their own stored headers, not that separate
metadata service. Attached KAREL namespaces retain precedence on name collisions.

## Status and verification

| Status | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Missing program |
| 2 | Invalid name, mode, type, position/group/line or representation |
| 3 | Invalid/foreign handle or access denied |
| 4 | Sharing rejection, open-record operation or selected-target guard |
| 5 | Existing program/destination without overwrite |
| 6 | Program, position or handle capacity exhausted |
| 7 | Comment updated with truncation warning |
| 8 | Comment destination too small; output preserved |
| 17038 | Position is uninitialized, following the documented sentinel |

Other codes are portable and do not claim native alarm mappings. Procedures
preserve data outputs on failure; status 7 is a completed update. A failed position
function sets status then raises, preserving the assignment target, consistently
with offline register getters. Check metadata first when absence is expected.
Inputs/selectors evaluate once in source order, with exact disjoint writable
outputs and transitive FOR-counter protection. Ordinary type, initialization,
matrix and range failures raise before the operation changes data.

```sh
python -m karel2py examples/teach_programs.kl -o teach.py --report teach-report.json
python teach.py --context examples/teach_programs.services.initial.json --state-out state.json
```

The [example](../examples/teach_programs.kl) exercises all 17 calls and metadata
integration. Tests cover sharing, grouped records, cleanup, copies, JSON, CLI
replay and execution with compiler/GUI modules absent. The
[semantic ledger](semantics/teach_program_semantics.json) records manual locators
and the portable choices. Native TP import/export/execution, motion linkage,
embedded TP registers, native limits and strict mode remain separate work.
