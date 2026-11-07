# Scalar logical collection values

[PATH-header USING](path-header-using.md) extends these lexical capture rules to
explicit PATH headers. Computed PATH selectors provide isolated private header
data; named selectors retain their existing resource-root protections.

Pythonic PATH and QUEUE_TYPE source assignments, private routine arguments and
internal/compiled linked results copy bounded independent logical data. This is
an authored offline source extension without native compiler, controller, binary
layout, ownership or strict-mode equivalence.

```karel
VAR source,target:QUEUE_TYPE buffer:ARRAY[3]OF INTEGER seq,status:INTEGER
ROUTINE copy(values:QUEUE_TYPE):QUEUE_TYPE
BEGIN RETURN values END copy
BEGIN
  INIT_QUEUE(source)
  APPEND_QUEUE(17,source,buffer,seq,status)
  target=copy((source))
END
```

The queue initialization flag, ordered sequence/value entries and last sequence
counter copy independently. The source keeps its buffer; each receiver/private
copy has no buffer link. A later queue operation can bind its own explicitly
supplied one-dimensional INTEGER buffer. Empty uninitialized queues are valid
logical state; invalid IDs, counters, buffers and entries reject before publication.

## Capture, schemas and ownership

Collection kinds must match. Scalar PATH assignments, grouped or computed
arguments, and RETURN can convert layouts whose node and header fields match by
name under the [record conversion rules](record-schema-conversions.md). Both
layouts must have a header or both must omit it. Compatible joint and Cartesian
fields use the calling task's explicit [robot context](kinematic-records.md).
Source and target each fit the normal scalar leaf bound and both count against
the step budget. Every node and header validates before the first model call.

Source values are evaluated and validated once before destination selectors
or later argument expressions. Receiver validation follows selector effects and
precedes publication. Earlier explicit effects are retained on failure.

Existing receiver roots and compatible PATH headers retain their identities.
Independent nodes replace old node lists, leaving old node aliases detached.
Self-copy follows the same rules. PATH validation rejects shared mutable nodes,
headers or data containers, invalid known leaves and malformed schemas. Partial
missing fields/aggregates and unknown BYTE markers retain their logical meaning.
PATH snapshots contain at most 32,767 scalar leaves, queue snapshots at most
32,767 entries, and data schemas at most 64 levels. These limits bound each
snapshot rather than the total number of copies retained by a running program.

Scalar values selected from ARRAY cells, created storage and imported namespaces
use the same source rules. Scalar selection does not open whole-bank copying
through generic runtime helpers; whole collection banks and prefixes have their
[separate source contract](collection-source-values.md).

## Routines and lifetime

Bare matching variables, complete indexed cells and explicit BYNAME arguments
retain borrowed references. A mismatched argument must be grouped or computed
to request a private conversion. Grouped arguments and computed results own independent
private storage. They can be mutated, forwarded by exact reference and retained
by condition handlers. Pause/resume retains them; stop and failed calls unwind
normal frames without copy-back. Separate private arguments allocate separately.

Results are captured before local cleanup and can feed assignments or further
private calls. Direct PATH result clauses, prior PATH aliases and QUEUE_TYPE
aliases resolve through the normal declaration rules. Linked interfaces still
match exactly. Compiled linked results take the checked logical result path.
[Explicit callback collection results](external-collection-results.md) now also
accept bounded runtime values or typed JSON and detach their logical data.

## Boundaries and saved state

FILE descriptors/arrays, resource fields, generic QUEUE_TYPE checked/value helpers,
whole PATH UNINIT and ordinary resource-root FOR protections remain guarded.
Whole-PATH I/O and [queue entry I/O](queue-io.md) remain separate scalar transport
features; queue input retains IDs/order and detaches the old buffer link.
Source copying does not publish GET_VAR/SET_VAR cache entries or status outputs.

Existing typed JSON and logical VR/DRAM persistence store the copied logical data
and queue sequence; they omit queue buffers, private references, retained handlers
and suspended frames. DONE guards in the authored examples permit exact saved
context replay. The report exposes `scalar_collection_source_policy` and lists converted sites
in `path_schema_conversions`. The
[semantics ledger](semantics/scalar_collection_value_semantics.json) records the
offline evidence boundary.
