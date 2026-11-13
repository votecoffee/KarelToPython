# XML variable publication checks

Pythonic XML_SETVAR retains the captured target and status contracts while it
stages attributes. A valid staged update publishes only if the captured target
still contains the values and storage that were copied. This prevents a callback
or condition handler edit from being silently overwritten by an older staged
record, including edits to unmentioned fields.

## Capture and verification

Resolve the existing explicit record target once, retaining its reference
location and schema. Charge the existing per-leaf budget before copying the
target. Data edits completed during that charging phase are included in the
subsequent copy; a changed reference binding or schema rejects preparation.

The capture retains bounded scalar tokens and strong references to original
containers and backing storage. It checks:

- The root, child records, ARRAYs and JOINTPOS objects and their backing storage.
- Record type maps, field sets and protection flags, ARRAY shapes and view mappings.
- Typed scalar values, including signed zero and missing/unknown markers.
- The captured target and status reference locations and schemas.

Strong owners keep replaced objects alive until verification finishes, so object
identifier reuse cannot make a replacement appear unchanged. No additional full
value clone is needed for these checks. Existing 64-level/32767-leaf data bounds
and per-attribute budget charges remain.

Before a valid staged update is published, verify the original XML FILE and its
bytes, then the captured target. A conflict raises KarelRuntimeError, retaining
completed callback edits, the prior status value, FILE status, cursor and current
event. No XML field update is published. The session's active-operation flag is
released on every exit. No automatic retry or rollback occurs.

## Edits that remain allowed

An edit completed before target copying is part of the captured data. An
unrelated global edit does not conflict. A scalar write that leaves the same
typed value is also allowed; distinct positive/negative REAL zero is detected.
Ordinary status-value edits still receive the operation's completion code.

Reference retargeting is separate from writing a value. A changed status binding
rejects completion, including when attribute validation returns an XML data
error. Existing invalid-path/domain/capacity statuses otherwise retain their
behavior and do not publish partial XML data. Earlier callback edits remain
visible on those failures.

Successful updates preserve existing root/child identities and retained aliases.
Guard state is local to the operation and is never saved in JSON. Captured
reference semantics remain: names are not repeatedly resolved to retarget the
operation.

## Accepted forms and evidence

This fixes publication behavior across the existing [record roots](xml-record-roots.md)
and [nested scalar paths](xml-aggregate-paths.md), including selected ARRAY/PATH
records, builtin records and supplied linked programs. It adds no scalar,
whole ARRAY, JOINTPOS or resource root form. POSITION orientation protection,
CONFIG limits, output overlap and active FOR checks remain unchanged.

The [authored regressions](../tests/test_xml_publication.py) exercise callback
edits before/after capture, nested storage, signed zero, live views, reference
retargeting, PATH nodes, linked calls, pause/resume and normal JSON data.
`xml_variable_publication_policy` and the
[semantic ledger](semantics/xml_variable_publication_semantics.json) record the
contract. These are cooperative offline runtime checks, without native
concurrency, controller or public strict-mode equivalence claims.
