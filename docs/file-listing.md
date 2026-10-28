# Portable FILE_LIST formats

Pythonic `FILE_LIST(file_spec, n_skip, format, names, n_files, status)` lists
an explicitly supplied MemoryFiles, DirectoryFiles or DeviceFiles backend. It
never discovers controller devices or files outside a DirectoryFiles root.

| Format | Each returned STRING |
| --- | --- |
| 0 | Complete backend key, preserving the preexisting portable extension |
| 1 | Base name without the final extension |
| 2 | Final extension without the dot; empty if absent |
| 3 | Base name with its extension |
| 4 | Forty-character portable name/type/size record with blank timestamps |

Formats 1 through 4 follow the source forms described in MARRC75KR07091E Rev N,
section A.6.2. Exact native formatting and native status values remain unverified.

## Selection and pages

The backend applies its ordinary wildcard and device rules, sorts its complete
keys, skips `n_skip` matches, and selects up to the length of the one-dimensional
STRING array. Formatting happens after selection, so duplicate stems remain
separate entries and formatting does not reorder results. `n_files` counts the
entries in this page. Increment the skip by that count to request the next page.
Unused array slots retain their previous values, including uninitialized values.
An empty or exhausted page returns count zero and success without clearing them.

Format 0 preserves complete paths/device keys exactly. Formats 1 through 4 remove
device and directory components, preserve case, and split on the final dot. A
leading-dot name such as `.settings` has no extension. A trailing dot such as
`part.` produces stem `part` and an empty extension. Spaces and control characters
inside the resulting base name are rejected for formats 1 through 4. Their
strings have no padding except in format 4.

DirectoryFiles keeps its existing case-sensitive pattern matching and explicit
device mapping. DeviceFiles honors its explicit volume names and mount flags.
No implicit controller or host drive mapping is added.

## Metadata columns

Format 4 is always 40 characters, including trailing spaces:

| One-based columns | Portable content |
| --- | --- |
| 1 through 8 | Base stem, left aligned |
| 9 | Dot when an extension exists; otherwise a space |
| 10 through 12 | Extension, left aligned |
| 13 through 20 | Spaces |
| 21 through 25 | Decimal byte count, left aligned |
| 26 through 35 | Spaces reserved for date |
| 36 through 40 | Spaces reserved for time |

Names longer than eight stem characters or three extension characters, or sizes
above 99999 bytes, return capacity status. No name, extension or size is silently
truncated. This is an explicit portable 8.3 layout within the documented column
starts; it does not claim native formatting for larger files.

The portable backends do not expose controller timestamp metadata, so all date
and time columns are blank, including for DirectoryFiles. Host modification times
are not copied into controller-shaped data. MemoryFiles and DeviceFiles report
current buffered sizes. DirectoryFiles reports the pending buffered size while a
file is open and the current regular-file size on disk while it is closed.
Listing neither reads the file payload nor flushes or advances an open FILE.

## Outcomes and atomic updates

| Status | Portable meaning |
| --- | --- |
| 0 | Page returned successfully, including no matches |
| 1 | A selected file disappeared before metadata inspection |
| 2 | Invalid format, negative skip or invalid formatted base name |
| 3 | A destination STRING or format-4 field cannot hold the full result |

The whole selected page is validated before any names or count change. Errors
preserve those outputs and update only status. This capacity rule also applies
to format 0: overly long keys return status 3 rather than silently truncating.
Backend access/security failures, unsupported live services, output aliases and
execution-budget exhaustion raise their ordinary errors before page publication.
These status numbers are package choices, not native alarm equivalence.

There is no file-list cursor to serialize. Ordinary file contents remain covered
by the existing context JSON facilities; DirectoryFiles retains its explicit root
and ordinary host-lifetime behavior. Strict mode remains future work.
