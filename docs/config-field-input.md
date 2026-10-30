# Bounded CONFIG field input

Pythonic READ accepts the three INTEGER turn fields and four BOOLEAN flag fields
of declared CONFIG storage. This includes CONFIGs in records/ARRAYs,
POSITION.CONFIG_DATA, exact routine formals and captured USING values.
No full CONFIG binary layout or implicit robot configuration is inferred.

~~~karel
VAR cfg:CONFIG
BEGIN
  READ(cfg.cfg_turn_no1,cfg.cfg_turn_no2,cfg.cfg_turn_no3,
       cfg.cfg_flip,cfg.cfg_left,cfg.cfg_up,cfg.cfg_front)
END
~~~

Supply typed values through the existing explicit callback/JSON interface, ASCII
text through TextInput, or an explicitly opened FILE. A typed INTEGER response
must be a Python int excluding bool; a typed BOOLEAN response must be bool.
Text input retains its ordinary numeric and ON/OFF/TRUE/FALSE token rules.

## Domains and capture

CFG_TURN_NO1, CFG_TURN_NO2 and CFG_TURN_NO3 retain the existing -8..7 prototype
bounds. CFG_FLIP, CFG_LEFT, CFG_UP and CFG_FRONT retain exact BOOLEAN storage.
Use canonical field names; abbreviated names such as TURN_NO1 are not inferred.
Scalar widths, integer bases, BOOLEAN second-format behavior and CR remain the
same as [ordinary READ formats](read-formats.md).

Each destination and its formats evaluate once, left to right. Known CONFIG
source captures validate the complete parent schema and its writable field
reference before input. Malformed/substituted parent schemas, readonly parents,
forged field references and unsupported reference subclasses fail closed.
Unselected fields may remain uninitialized; no flags or turns are defaulted.
Computed USING owns its private CONFIG copy and does not copy changes back.

CONFIG scalar arguments to ordinary routines keep their existing value-passing
rules. Pass an exact whole CONFIG formal when a routine should update the
caller's fields. BYNAME itself retains its exact schema/alias contract.

## Validation and publication

The runtime validates the entire typed response, including every CONFIG turn
bound, before assigning any destination. An invalid late turn therefore cannot
publish an earlier ordinary INTEGER or BOOLEAN. Repeated aliases still use the
last value after all values have passed validation. BYTE/SHORT targets in the
same request retain their existing unknown/sentinel rules without double
normalization.

FILE reads commit their cursor only after validation. A typed FILE validation
failure retains all READ outputs and the cursor, using the backend's existing
portable I/O status 1. A capture/format failure occurs before I/O and retains the
previous status. Earlier argument and explicit callback effects remain; direct
callbacks/TextInput may already have consumed their own input before rejection.
No retry or input rewind is invented for an arbitrary host callback.

## FILEs and cooperative reads

MemoryFiles, explicitly rooted DirectoryFiles and virtual DeviceFiles use their
existing scalar text/binary formats. Shared finite messaging/acquisition FILE
input follows the same checks. Binary reads describe separate scalar fields,
not a packed native CONFIG record; byte widths and reversal keep their ordinary
portable rules.

Finite and opted-in waiting serial streams, snapshot/waiting pipes and injected
keyboard line FILE reads use the same preflight. A rejected keyboard line remains
in that handle's pending buffer; already consumed key events retain the existing
editor/history behavior. PASSALL numeric fields remain unsupported.

A waiting read retains its captured destinations and formats through pause.
Resume does not repeat selectors or format calls. CANCEL FILE preserves output
values and uncommitted data and uses status 6. Stop, sticky ABORT and step-budget
failure retain their precedence and release pending-read registrations. Close
live handles explicitly before context save. No native device or GUI opens.

## Boundaries and metadata

Whole aggregate/resource READ, constants, active counters and POSITION orientation
writes remain blocked. CONFIG turn fields do not become FOR counters. Generic
service output aliases and conversion status outputs such as CNV_STR_CONF still
require their existing ordinary writable references. Public strict mode remains
future work; native input parsing, controller status, compact layout and runtime
equivalence are not established.

Reports expose config_field_reads with canonical field/type, source location,
file/callback choice, capture/publication metadata and INTEGER bounds, plus
config_field_read_policy. Existing runtime READ observations retain their typed
metadata/outcome format; they do not store supplied values. Saved JSON retains
normal CONFIG data and partial markers, without callbacks, pending reads or FILE
handles.

See the [semantic ledger](semantics/config_field_input_semantics.json),
[tests](../tests/test_config_field_input.py),
[typed callback](../examples/config_field_callback.kl),
[text FILE](../examples/config_field_text.kl),
[binary FILE](../examples/config_field_binary.kl),
[private USING](../examples/config_field_scopes.kl),
[linked owner](../examples/config_field_owner_project/main.kl) and
[linked ARRAY capture](../examples/config_field_array_project/main.kl) examples.
