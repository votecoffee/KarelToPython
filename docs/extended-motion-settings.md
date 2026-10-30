# Termination, orientation and qualified WITH settings

Pythonic MOVE requests accept nine temporary WITH settings. In addition to the
six original speed, interpolation, frame/tool and configuration settings, they
capture termination and orientation choices as checked request metadata.

~~~karel
WITH $GROUP[1].$TERMTYPE=FINE, $SEGTERMTYPE[1]=NODECEL,
     $ORIENT_TYPE=RSWORLD, $MOTYPE=STRAIGHT
MOVE AWAY 1
~~~

## Choices

| Setting | Contextual names and INTEGER values | Saved value |
| --- | --- | --- |
| $TERMTYPE, $SEGTERMTYPE | FINE=1, COARSE=2, NOSETTLE=3, NODECEL=4, VARDECEL=5 | Canonical name |
| $ORIENT_TYPE | RSWORLD=1, AESWORLD=2, WRISTJOINT=3 | Canonical name |
| $MOTYPE | JOINT=6, LINEAR=7, STRAIGHT=7, CIRCULAR=8 | STRAIGHT becomes LINEAR |

Names are contextual within their corresponding setting expression, including
parenthesized arithmetic. Ordinary identifiers retain normal lexical lookup
elsewhere, including the MOVE operands and following local conditions/statements.
A contextual name takes precedence within that setting; no global constants or
arbitrary system-variable namespace are added. Dynamic INTEGER, BYTE and SHORT
values use the same domains; BOOLEAN truthiness, REAL and STRING choices are rejected.

The reviewed R-J3iB KAREL Reference Manual, Rev A, PDF page 66, lists these enum
values and the STRAIGHT alias. Pages 219-220 and 228 describe termination;
pages 323-324 and 744 describe group notation and temporary WITH values. This
extension establishes authored translation/offline behavior; native compiler,
controller settling/interpolation/orientation behavior remains unverified.

## Groups and capture

Accepted spellings are $NAME, $NAME[group] and $GROUP[group].$NAME. The explicit
$GROUP prefix is a Pythonic input extension using the documented group notation.
A setting may specify its group once. Every explicit group must match the MOVE's
selected source group; cross-group settings remain blocked.

Capture each group expression, then its value, once in source order before MOVE
operands and local condition captures. Frame/tool values detach immediately.
All nine settings may occur once in the same request. Duplicate canonical names,
unknown names, malformed groups, invalid values, ownership, VIA and script checks
reject before MOVE publication or response consumption. Earlier expression effects
remain visible; no invented rollback of source routines is performed.

Existing CIRCULAR/VIA restrictions still apply. Termination and orientation do
not add trajectory execution, settling, speed application, timing changes, feedback
updates or RobotContext mutation. They remain request-local metadata through
immediate NOWAIT, supplied finite delays, local WHEN/UNTIL and explicit node/time
scopes. Pause/resume retains captured values; stop/abort/budget cleanup retains its
existing rules. NOWAIT with delayed/local scopes remains unavailable.

## History and examples

JSON history stores canonical setting names, selected groups and enum strings.
Numeric enum values and the source-only STRAIGHT spelling are rejected in saved
history. Old six-setting histories remain valid. Existing active-scope/ownership
save restrictions, 64 KiB request bounds and history/sequence limits remain.

Reports add motion_setting_policy with domains, contextual aliases, group forms,
maximum count and evidence boundaries. motion_requests keeps canonical setting
names, group-qualification flags and physical source locations, including includes.

See [authored regressions](../tests/test_extended_motion_settings.py),
[termination choices](../examples/motion_termination_choices.kl),
[qualified capture](../examples/motion_qualified_choices.kl),
[all nine settings](../examples/motion_nine_settings.kl),
[contextual expressions](../examples/motion_enum_expressions.kl),
[linked choices](../examples/motion_termination_project/main.kl),
[request-local scope](../examples/motion_settings_scope_project/main.kl) and the
[semantic ledger](semantics/extended_motion_setting_semantics.json).
