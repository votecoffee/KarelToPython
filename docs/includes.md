# KAREL source includes

Pythonic translation expands `%INCLUDE` from explicitly supplied text or selected
filesystem roots. Fragments can contain constants, types, variables, routines,
executable statements or a complete program. They enter the existing parser and
retain its scope, type, initialization and control-flow checks.

```python
from karel2py import translate

result = translate(
    'PROGRAM DEMO\n%INCLUDE declarations\nBEGIN\n%INCLUDE body\nEND DEMO',
    filename='main.kl',
    includes={'declarations.kl': 'VAR answer:INTEGER', 'body.kl': 'answer=42'},
)
```

The `includes` mapping is case-insensitive, snapshots string values, and performs
no filesystem lookup. Duplicate names after extension/path normalization reject.
Only files actually included enter dependency provenance. Supplying unused text
does not change a plain program's generated code or context fingerprint.

## Syntax and resolution

Write `%INCLUDE file_spec` on its own physical line. Real trailing `--` comments
are accepted. The default extension is `.KL`; explicit `.KL`, `.KH` and `.INC`
text files are supported. A single-quoted specification is also accepted as a
Pythonic convenience. Quoted text and comments containing `%INCLUDE` do not
expand. Directive continuation and inline include directives reject.

Names use relative slash or backslash paths, with an optional device prefix such
as `FR:\types`. A single leading separator after a device is accepted. Basenames
are bounded to 36 characters and specifications to 254 ASCII characters.
Components use letters, digits, underscore, hyphen or period; empty components,
absolute paths and `.`/`..` traversal reject. Includes do not splice tokens
across file boundaries.

For memory mappings, resolution checks the including file's logical directory
first, then its device root when applicable, then the library root. For example,
`folder/definitions.kl` can include `constants` from `folder/constants.kl`.
Use a logical filename such as `src/main.kl` to give the main source a directory.
Device-qualified sources can be supplied directly as keys such as `FR:types.kl`.

Filesystem lookup requires an explicit `IncludeLibrary`:

```python
from karel2py.includes import IncludeLibrary

library = IncludeLibrary.from_directories(
    ['project', 'shared_headers'], devices={'FR': 'controller_headers'}
)
result = translate(source_text, filename='project/main.kl', includes=library)
```

The containing directory is searched first within its selected root, followed
by ordinary roots in their supplied order. Device-qualified requests require an
explicit device mapping. Components resolve case-insensitively; ambiguous folded
names reject. Included paths cannot follow symbolic links or junctions or escape
their selected root. No environment variables, installed controller support
folders, network locations or controller devices are searched automatically.
Supplied roots themselves are resolved once when selected.

One library captures each physical file once. Reusing it keeps a stable source
snapshot; create a new library to refresh changed files. Hard-linked aliases
share captured bytes while retaining their own lookup directories and provenance.
Expansion is translation-time text processing and executes no KAREL code.

## CLI and linked projects

The single-source CLI searches the source's directory automatically. Repeat
`-I`/`--include-dir` to add ordered roots, and use `--include-device DEVICE=DIR`
for device mappings:

```sh
python -m karel2py examples/include_expansion.kl --check
python -m karel2py examples/include_expansion.kl -o .local/include_expansion.py --report .local/include_report.json
python -m karel2py main.kl --check -I shared_headers --include-device FR=controller_headers
```

Create `.local` first. The CLI validates both output targets against every
resolved include before publishing either file. `--force` cannot overwrite an
include or a hard-link alias, including when writing a rejection report.

`translate_project(sources, includes=...)` uses the same explicit text library
for its named program sources. `load_project(directory, include_dirs=(),
include_devices=None)` reads a selected directory and resolves includes through
the same provider. Referenced top-level `.kl` fragments are excluded from program
entries, so a declarations file is not translated as a standalone program.
Nested fragment directories are supported. Unreferenced top-level `.kl` files
remain program candidates and must contain valid programs.

```sh
python -m karel2py.project examples/include_project
python -m karel2py.project examples/include_project --entry MAIN
```

The project CLI accepts the same include options. Its state and trace outputs
cannot replace any program/include input, including file aliases. Program
linkage, imported-variable identities and routine type matching retain their
existing checks. Included [external FROM type declarations](external-types.md)
retain physical source locations for project-link diagnostics.

## Provenance and errors

Reports retain the primary `source_sha256` and add `expanded_source_sha256`,
`include_files`, `include_expansions` and compact `source_origins` spans when an
include is used. Each include has a text hash; filesystem sources also have a
hash of their original bytes, preserving BOM and physical-line-ending evidence.
The translation-context fingerprint includes the resolved dependency metadata.

Compiler and lexer diagnostics map to the original file, physical line and
column. Generated Python source-map rows add `source_file`, `source_line`,
`source_column` and `include_stack`. Existing `karel_line` fields, other feature
report lines and runtime error/checkpoint lines retain expanded-source numbering.
Use the physical spans or enriched source map to resolve those runtime lines;
runtime exceptions do not automatically open or reread source files.

| Diagnostic | Meaning |
| --- | --- |
| E_INCLUDE_NAME | Invalid name, extension, path or empty specification |
| E_INCLUDE_POSITION | Directive shares a physical line with source tokens |
| E_INCLUDE_MISSING | Source was not supplied or found in selected roots |
| E_INCLUDE_DEVICE | Device has no explicit directory mapping |
| E_INCLUDE_READ | Unreadable, nonregular or invalid UTF-8 input |
| E_INCLUDE_PATH | Symbolic link, junction or root escape |
| E_INCLUDE_AMBIGUOUS | Case-insensitive path matches more than one entry |
| E_INCLUDE_CYCLE | Active include chain returns to the same source identity |
| E_INCLUDE_DEPTH | More than three nested included files |
| E_INCLUDE_LIMIT | File, cache, expansion, byte or physical-line limit |

The depth of three follows the manual. Portable resource limits also bound each
included file to 4 MiB, expanded source to 8 MiB/100000 physical lines, include
expansions and library entries to 256, file snapshots to 64 MiB, and ordinary
roots/device mappings to 32 each. Repeated includes expand repeatedly; they are
not include-once guards. Cycles use physical file identity for file sources.

Binary environments, macro substitution, native install/search rules, dynamic
file discovery and continuation through include directives remain unsupported.
Routine-local TYPE declarations remain prohibited by KAREL's scope rules.
The workbench's existing text-validation interface has no include-root editor;
use the CLI or API for explicit include configuration.

The [single-program example](../examples/include_expansion.kl) includes nested
constants, a named array, a routine and executable code. The
[linked example](../examples/include_project/MAIN.kl) shares structure definitions
with an external routine and a top-level declarations fragment. The report's
`include_policy` and [semantic ledger](semantics/include_semantics.json) record
the accepted forms and boundaries.
