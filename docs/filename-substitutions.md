# Extensionless and hidden filename substitutions

Pythonic COPY_FILE and RENAME_FILE batches accept extensionless names, ordinary
dotted names, leading-dot files, and stem-only destination templates. The same
expansion applies to explicit ordinary, virtual-volume and configured plain-PIP
routes. This is an authored offline extension, without native/compiler/controller
wildcard equivalence or strict-mode claims.

~~~karel
COPY_FILE('src/*','dst/*.*',FALSE,FALSE,status)
RENAME_FILE('src/*','dst/backup_*',FALSE,status)
~~~

## Parts and templates

Split a filename at its last dot only when a nonempty stem precedes it. A single
leading dot is part of the complete stem: `.env` has an empty extension, while
`.env.local` has stem `.env` and extension `local`. Earlier dots remain in the
stem. No extension or filename is inferred from the source selector.

| Source | Destination template | Expanded basename |
| --- | --- | --- |
| `LOG` | `copy_*` | `copy_LOG` |
| `LOG` | `*.*` | `LOG` |
| `LOG` | `*.txt` | `LOG.txt` |
| `part.KL` | `backup_*` | `backup_part` |
| `.env` | `copy_*.*` | `copy_.env` |
| `.env.local` | `copy_*.*` | `copy_.env.local` |
| `part.rev1.KL` | `*_*.*_*` | `part.rev1_part.rev1.KL_KL` |
| `part.KL` | `**.**` | `partpart.KLKL` |
| `part.KL` | `**` | `partpart` |

A standalone final * preserves the complete source filename, including its
extension. Every other stem star substitutes the complete source stem. Extension
stars independently substitute the optional extension. [Adjacent and separated
repeated stars](repeated-destinations.md) reuse that same part. A stem-only destination
such as `backup_*` deliberately drops the source extension.

When the expanded extension is empty, omit its dot separator. Literal extension
tags remain literal: `LOG` with `*.pre*_post*` becomes `LOG.pre_post`. Replacements
run once and do not recursively interpret inserted characters.

## Selection, backends and directories

Source matching is unchanged: star/question match within one component, and a
whole directory ** follows the [existing bounded depth rules](directory-globs.md).
Source `*.*` requires a dot and does not select extensionless `LOG`; source * can
select mixed valid names. Hidden files participate in ordinary supplied banks
and rooted scans. Existing backend syntax still applies, including the stricter
plain FilePipes name domain, literal devices and rooted containment.

[Directory substitutions](directory-components.md) and one optional destination
** retain their own source-relative depth consumption. A source with only a
filename matcher supplies no relative directory levels. Existing expanded rooted
parents must exist; no directory, pipe, volume or namespace is discovered or
created implicitly. MOVE_FILE, DELETE_FILE and FILE_LIST keep their existing
selection contracts.

## Complete-batch checks

Capture expressions and status selectors once, retaining ordinary call order
and completed effects. Validate the entire selected plan before publication.
Dropping extensions may create duplicate targets: `a.KL` and `a.TXT` both map to
`backup_a`, so that complete batch returns status 2 without publishing either
file. Empty-extension expansion can cause the same kind of collision.

Retain case/physical aliases, source overlap, busy handles, complete name/byte
rescans, readonly/mounted-device rules and all quotas. COPY retains overwrite
permission; copying into an existing reserved pipe still requires overwrite.
RENAME retains original bytes/configuration identities and existing no-overwrite
and guarded cross-bank rules. Plain pipe target names must be explicitly
configured where required by those routes.

Input and expanded names stay at most 254 ASCII characters. Scans retain 32767
entries, COPY retains its 64 MiB snapshot bound, and per-file, device, pipe and
execution limits remain. Directory question and bracket templates,
trailing dots/spaces, empty/dot/traversal components, reserved names and absolute
host paths remain rejected. [Fixed-width filename captures](question-file-wildcards.md)
can supply destination question marks. Ordinary runtime-error/status boundaries
are retained.

Memory/device publication uses prepared state and existing retained-garbage
accounting. Rooted filesystem publication stays per file: a late host failure may
retain earlier completed changes. No cross-file host transaction or concurrent
filesystem isolation is added. Both NOWAIT values remain synchronous.

## Reports, replay and examples

Reports expose `filename_substitution_policy`. Saved context stores resulting
bytes and accounting without templates, scans, open handles or pending plans.
DONE guards in the examples permit exact saved-state replay.

See [mixed copy](../examples/plain_names_copy.kl),
[stem-only rename](../examples/plain_names_rename.kl),
[leading-dot names](../examples/plain_names_hidden.kl),
[virtual devices](../examples/plain_names_devices.kl),
[linked copy](../examples/plain_names_linked/main.kl),
[plain pipe transfers](../examples/plain_names_pipes/main.kl),
[regressions](../tests/test_filename_substitutions.py) and the
[semantic ledger](semantics/filename_substitution_semantics.json).
