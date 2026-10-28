# Pythonic source directives

Since 0.68.0, Pythonic mode accepts a small set of top-level directives as
syntax-checked metadata. This lets otherwise supported code retain its environment
requirements and program attributes when translated.
Version 26.1024.141821 adds seven task directives that initialize applied offline
policies, described in [task attributes](task-attributes.md).

```karel
PROGRAM DIRECTIVES
%COMMENT = 'Can''t -- &sort' -- real trailing comment
%ENVIRONMENT STRNG
%ENVIRONMENT SYSTEM
%ALPHABETIZE
%NOLOCKGROUP
VAR z,a,total: INTEGER
BEGIN
  CNV_STR_INT('7',z)
  a=3
  total=z+a
  WRITE('total=',total::0,CR)
END DIRECTIVES
```

This finishes with `Z=7`, `A=3`, `TOTAL=10`, in declaration order, and records
`total= 10` followed by a newline. The generated `Program.source_directives` is:

```python
(
    ('%COMMENT', "Can't -- &sort"),
    ('%ENVIRONMENT', 'STRNG'),
    ('%ENVIRONMENT', 'SYSTEM'),
    ('%ALPHABETIZE', None),
    ('%NOLOCKGROUP', None),
)
```

The [authored example](../examples/pythonic_directives.kl) also calls a helper
routine. Its [snapshot](../examples/pythonic_directives.expected.json) and
[output](../examples/pythonic_directives.write.expected.json) are independent fixtures.

## Accepted forms

Directives are case-insensitive, run through the end of their physical line,
and are accepted after `PROGRAM` and before the program body. Real trailing `--`
comments are accepted.
An ampersand outside a quoted payload and before a trailing comment remains an
unsupported directive continuation.

| Directive | Pythonic behavior |
| --- | --- |
| `%ENVIRONMENT name` | Record a required facility name, normalized to uppercase. |
| `%COMMENT = 'text'` | Record the decoded program comment without changing runtime state. |
| `%ALPHABETIZE` | Record the request to display static variables alphabetically. Offline storage and snapshots keep declaration order. |
| `%NOLOCKGROUP` | Retain the existing offline metadata behavior without acquiring task/group ownership. |
| `%PRIORITY = n` | Priority 1..99 orders the next cooperative round. |
| `%TIMESLICE = n` | Slice 1..1000 ms determines the bounded checkpoint budget per turn. |
| `%NOABORT = ERROR + COMMAND` | Unique selected flags suppress new error/command abort requests. |
| `%NOPAUSE = ERROR + COMMAND + TPENABLE` | Unique selected flags suppress new pause requests by origin. |
| `%NOBUSYLAMP` | Set readable TSK_NOBUSY capability metadata. |
| `%NOPAUSESHFT` | Set TSK_PAUSESFT=0 for explicit shift notifications. |
| `%TPMOTION` | Set readable TSK_TPMOTION capability metadata. |
| `%DEFGROUP = n` | Select offline calling-root group 1..32. |
| `%LOCKGROUP = n, n, ...` | Record up to 32 distinct groups in 1..32 without acquiring locks; also select the optional MOTION_CTL query mask. |
| `%CMOSVARS` | Record CMOS as the default storage intent. |
| `%CMOS2SHADOW` | Record CMOS-to-SHADOW mapping; combined with CMOSVARS the default intent is SHADOW. |
| `%SHADOWVARS` | Record SHADOW as the default storage intent. |
| `%UNINITVARS` | Retain the runtime's existing uninitialized defaults. |
| `%CRTDEVICE` | Label omitted-file READ/WRITE observations `device="CRT/KB"`. |
| `%DELAY = n` | Record periodic native delay intent, portable range 0..86400000 ms. |
| `%STACKSIZE = n` | Record stack intent, portable range 1..32767 long words. |

An environment name must start with an ASCII letter, then contain only ASCII
letters, digits or underscores, with at most 36 characters. Custom names and
repeated declarations are preserved. This is an explicit portable identifier
subset: quoted filenames, extensions, paths, assignments and lists are rejected.

COMMENT accepts one single-quoted ASCII literal of at most 16 decoded characters,
including an empty literal. Doubled apostrophes decode to one apostrophe; `--`
and `&` inside the literal remain data. COMMENT must precede CONST, TYPE, VAR and
routine declarations. Duplicate COMMENT attributes are rejected because this
translator does not choose a native precedence rule. ALPHABETIZE and NOLOCKGROUP
accept no arguments. ENVIRONMENT and ALPHABETIZE may appear between top-level
declaration sections; directives inside routines or executable blocks remain blocked.

## Environment requirements and reports

Native ENVIRONMENT declarations select translator definition files. Here they
record requirements only. Translation does not load files or modules, import
definitions, grant extra built-ins, or infer controller facilities. Every source
symbol, type and call still has to satisfy the implemented language subset. A
supported built-in works with or without an ENVIRONMENT declaration; this offline
policy does not reproduce native environment visibility or default-file rules.

The report retains raw directive text, physical lines and dispositions in
`directives`. `directive_metadata` adds normalized names, decoded arguments,
physical line/column and dispositions in source order. `directive_policy` describes
the chosen behavior and lists unique `required_environments` in first-use order.
Generated modules retain immutable `(name, argument)` pairs in
`Program.source_directives`, available with the small standalone runtime too.
Changing report dictionaries does not change generated metadata.

## Additional source policies

The nine additional directives above must precede declarations and cannot repeat.
LOCKGROUP conflicts with NOLOCKGROUP. CMOSVARS conflicts with SHADOWVARS;
CMOS2SHADOW can modify CMOSVARS. Group lists retain source order. Numeric forms
require an unsigned decimal INTEGER literal after `=`; expressions are rejected.

`Program.source_settings` returns a detached dictionary with `default_group`,
`lock_groups`, `storage`, `cmos_to_shadow`, `uninitialized_variables`,
`default_io_device`, `periodic_delay_ms` and `stack_words`. Defaults are the
existing context/inferred group or 1, unspecified locks, DRAM, false, true,
TPDISPLAY, 8 ms and 300 long words. NOLOCKGROUP records an empty lock tuple.
These settings come from the generated source, not saved task checkpoints.

DEFGROUP takes precedence over the existing single-group declaration inference
and the supplied RobotContext's active group. Explicit per-call groups still win.
Linked routines use their calling root for group-sensitive operations. Ordinary
position-register getters/setters now use that same root default when their
optional group is omitted. Their host bank APIs retain explicit group defaults.
Missing groups fail rather than selecting another bank.

CRTDEVICE adds the device label to READ callback metadata, read observations and
omitted-file WRITE observations. WRITE callbacks still receive only text. Explicit
FILE operations keep their backend behavior and receive no device labels. There
is no native keyboard/window routing, discovery or implicit file/device access.

Storage, periodic DELAY and STACKSIZE settings are metadata only. LOCKGROUP and
NOLOCKGROUP can opt into [root logical acquisition](directive-group-locks.md)
with an explicitly configured GroupLocks bank. The additional `callee_scopes`
flag enables [scoped module acquisition](scoped-group-locks.md); both default off.
They do not allocate CMOS/SHADOW, acquire motion control, sleep periodically or
allocate a native stack. TSK_STACK still reports active offline frames. Existing
values survive reruns; UNINITVARS does not clear assigned/restored values. JSON
save/load remains explicit, independent of storage intent. The
[authored policy example](../examples/source_policies.kl) demonstrates a group-2
register read and portable node size with these directives retained. See the
[policy ledger](semantics/source_policy_semantics.json) for source provenance.

Malformed supported forms produce `E_DIRECTIVE_SYNTAX` or `E_DIRECTIVE_VALUE`;
late or duplicate COMMENT attributes produce `E_DIRECTIVE_POSITION` or
`E_DIRECTIVE_DUPLICATE`. Unknown and unimplemented directives retain `E_DIRECTIVE`.

## Evidence boundary

The reviewed [reference edition](references.md), one-based PDF pages 310,
343-344 and 387-388, describes alphabetical static-variable display, COMMENT's
length/header placement and ENVIRONMENT definition loading. Metadata preservation,
the portable name subset, duplicate policy and unchanged offline storage order
are explicit implementation choices.

The seven task directives require placement before declarations and reject
duplicates. They configure the portable policies in the task attribute guide;
they do not load native task/group ownership or native scheduler behavior.
Native persistence/storage, group locks and waits, periodic scheduling, stack allocation
and actual device routing remain unavailable. [Source includes](includes.md)
now expand explicitly supplied text before parsing. Unknown directives stay
blocked; there is no native environment loading or controller validation.
Strict mode remains a future milestone and retains its previous internal directive
restrictions.
