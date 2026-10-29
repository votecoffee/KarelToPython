# XML attributes targeting aggregate leaves

Pythonic `XML_SETVAR` can apply attributes to scalar leaves inside an explicitly
resolved user STRUCTURE or [built-in record root](xml-record-roots.md). Flat
attribute names retain their previous behavior.
Dotted names are a portable extension:

```xml
<item child.count="7" child.label="demo" bytes.1="255" grid.2.1="-9"/>
```

Record field components are case-insensitive KAREL identifiers. At an ARRAY
component, decimal components supply all dimensions of that declared ARRAY,
using one-based indices. A two-dimensional `grid` needs two components, such as
`grid.2.1`. Named ARRAY components keep their declared boundaries. Whole arrays,
whole records, unknown fields, expressions, arbitrary host attributes and
out-of-range or incomplete indices are rejected.

This extension interprets dotted attribute names; it does not map nested XML
elements or interpret namespaces. The root target is a user STRUCTURE or supported built-in record,
resolved through existing explicit variable/attached-program rules. The
[authored example](../examples/xml_aggregate_paths.kl) supplies its XML through
MemoryFiles.

## Types and atomic publication

Supported leaves are INTEGER, BYTE, SHORT, finite REAL, BOOLEAN and bounded ASCII
STRING. Integral text is signed decimal. BYTE accepts 0 through 255. SHORT keeps
its ordinary -32768 through 32766 domain and 32767 uninitialized sentinel.
BOOLEAN accepts 0/1, FALSE/TRUE and OFF/ON, ignoring case. STRING must fit in full.
Unmentioned leaves retain their previous values, including missing and unknown
BYTE markers.

All updates are staged in a checked independent copy. An invalid later attribute
leaves every target leaf unchanged. Duplicate destination cells are rejected,
including case variants and indices such as `1` versus `01`. Only after every
attribute passes does replacement update the existing storage, preserving its
record/ARRAY identities and retained references.

Existing runtime field references enforce recursive POSITION orientation
protection and CONFIG turn bounds (-8 through 7). Writable position/location
leaves remain available. The entire target must be disjoint from status output;
direct, transitive and handler FOR-counter guards remain active.

Invalid paths, types, duplicates, domains or protected fields return XML_INVALID
(2). A STRING capacity failure returns XML_CAPACITY (3). Success returns zero.
These are package status conventions. Execution-budget exhaustion propagates as
an execution error, preserving the target and prior status rather than returning
an XML status. Each attribute consumes an execution step before staging its path.

Existing document, schema, attribute-count, path-length and parser limits apply.
XML scanning, text continuation, reopen/pause behavior and the exclusion of live
scanner state from saved JSON retain their [XML input contract](xml-input.md).
There is no XML writing, controller schema discovery or native status claim.
