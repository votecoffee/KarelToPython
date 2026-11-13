"""Audit selected source trees without executing KAREL or generated Python.

Reports contain private source paths and diagnostics; keep them outside Git.
Each distinct byte sequence is translated once, with all occurrences retained.
"""
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from karel2py import __version__, translate
from karel2py.lexer import TranslationError


BOUNDARY = (
    'Standalone Pythonic source translation and Python 3.11 syntax checks only. '
    'No input or generated code execution, native compiler invocation, linkage '
    'validation or controller checks. Includes and saved ARRAY schemas are not '
    'inferred. Duplicate counts describe byte-identical sources, not coverage.'
)


def _plain(path):
    info = path.lstat()
    return not (stat.S_ISLNK(info.st_mode) or
                getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def source_files(root, names):
    """Select deterministic basename matches, without following child links."""
    if not root.is_dir():
        raise ValueError('Source root must be an existing directory')
    if (isinstance(names, str) or not names
            or any(not isinstance(name, str) or not name or '/' in name or '\\' in name for name in names)):
        raise ValueError('Source names must be nonempty basename patterns')
    paths = []

    def fail(error):
        raise error

    for directory, children, files in os.walk(root, followlinks=False, onerror=fail):
        parent = Path(directory)
        children[:] = sorted(name for name in children if _plain(parent / name))
        for name in sorted(files):
            path = parent / name
            if (any(fnmatch.fnmatchcase(name.casefold(), pattern.casefold()) for pattern in names)
                    and _plain(path) and stat.S_ISREG(path.lstat().st_mode)):
                paths.append(path)
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def audit(root, *, names=('*.kl',), baseline=None):
    root = Path(root).resolve(strict=True)
    paths = source_files(root, names)
    if not paths:
        raise ValueError('No source files match the selected basename patterns')
    manifest, groups = [], {}
    for path in paths:
        raw = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(raw).hexdigest()
        manifest.append(dict(path=relative, bytes=len(raw), sha256=digest))
        if digest in groups:
            groups[digest]['sources'].append(relative)
            continue
        row = dict(source_sha256=digest, representative=relative, sources=[relative])
        try:
            result = translate(raw.decode('utf-8-sig'), filename=relative)
            ast.parse(result.python_source, filename=relative, feature_version=(3, 11))
            compile(result.python_source, relative, 'exec')
            row.update(status='translated', representative_python_sha256=result.report['python_sha256'])
        except TranslationError as error:
            row.update(status='rejected', diagnostic=error.as_dict())
        except UnicodeDecodeError as error:
            row.update(status='decode_error', message=str(error))
        except Exception as error:
            row.update(status='unexpected_error', error_type=type(error).__name__, message=str(error))
        groups[digest] = row
    if baseline is not None:
        if (not isinstance(baseline, dict) or type(baseline.get('format_version')) is not int
                or baseline['format_version'] != 1 or baseline.get('source_manifest') != manifest):
            raise ValueError('Baseline source manifest differs; compare the same paths and bytes')
    cases = list(groups.values())
    counts = Counter()
    for row in cases:
        counts[row['status']] += len(row['sources'])
    diagnostic_groups = Counter()
    for row in cases:
        if row['status'] == 'rejected':
            diagnostic_groups[(row['diagnostic']['code'], row['diagnostic']['message'])] += 1
    changes = []
    if baseline is not None:
        previous = {}
        records = baseline.get('unique_cases')
        if not isinstance(records, list):
            raise ValueError('Baseline distinct source inventory must be a list')
        for row in records:
            if (not isinstance(row, dict) or not isinstance(row.get('source_sha256'), str)
                    or row['source_sha256'] in previous
                    or row.get('status') not in ('translated', 'rejected', 'decode_error', 'unexpected_error')):
                raise ValueError('Baseline distinct source inventory is invalid')
            previous[row['source_sha256']] = row['status']
        if set(previous) != set(groups):
            raise ValueError('Baseline distinct source inventory differs')
        changes = [dict(source_sha256=row['source_sha256'], before=previous[row['source_sha256']],
                        after=row['status'], occurrences=len(row['sources']))
                   for row in cases if previous[row['source_sha256']] != row['status']]
    canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return dict(format_version=1, created_utc=datetime.now(timezone.utc).isoformat(),
                translator_version=__version__, source_root=str(root), names=list(names),
                boundary=BOUNDARY, source_manifest=manifest,
                source_manifest_sha256=hashlib.sha256(canonical).hexdigest(),
                source_count=len(paths), unique_source_count=len(cases),
                counts=dict(sorted(counts.items())),
                unique_counts=dict(sorted(Counter(row['status'] for row in cases).items())),
                diagnostics=[dict(code=code, message=message, unique_sources=count)
                             for (code, message), count in sorted(diagnostic_groups.items())],
                changes=changes, unique_cases=cases)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key in baseline: ' + key)
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('Nonfinite JSON constant in baseline: ' + value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Explicit source tree to scan read-only')
    parser.add_argument('--name', action='append', help='Case-insensitive basename glob; repeatable, default *.kl')
    parser.add_argument('--output', type=Path, required=True, help='New private JSON report; existing files are preserved')
    parser.add_argument('--baseline', type=Path, help='Earlier report; require the same selected paths and bytes')
    args = parser.parse_args(argv)
    try:
        # Exclusive creation also protects sources, old reports and link aliases.
        if args.output.exists() or args.output.is_symlink():
            raise ValueError('Output already exists; choose a new report path')
        baseline = None
        if args.baseline is not None:
            baseline = json.loads(args.baseline.read_text(encoding='utf-8-sig'),
                                  object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        report = audit(args.root, names=tuple(args.name or ('*.kl',)), baseline=baseline)
        with args.output.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(report, indent=2, allow_nan=False) + '\n')
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({key: report[key] for key in ('source_count', 'unique_source_count', 'counts', 'unique_counts', 'changes')}))
    return int(any(row['status'] in ('decode_error', 'unexpected_error') for row in report['unique_cases']))


if __name__ == '__main__':
    raise SystemExit(main())
