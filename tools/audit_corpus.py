"""Read-only, deterministic subset audit against an existing KL/PC corpus.

No compiler or robot is invoked; corpus KL files are never executed or modified.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from karel2py import translate
from karel2py import __version__
from karel2py.lexer import TranslationError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', type=Path, required=True, help='Karel Feature Set directory')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    categories = ['control', 'documented_statement', 'Probes4/NestedControl',
                  'Probes4/CallsReturns', 'Probes4/MathPrecedence', 'Probes4/NumericMath']
    base = args.corpus / 'KL/V8.33'
    rows = []
    for category in categories:
        files = sorted((base / category).glob('*.KL'))[:8]
        if len(files) != 8:
            raise SystemExit(f'Expected at least eight source files in {category}')
        for path in files:
            raw = path.read_bytes()
            relative = path.relative_to(base)
            row = dict(source=str(path), relative_source=relative.as_posix(),
                       source_sha256=hashlib.sha256(raw).hexdigest(), category=category)
            pc = args.corpus / 'PC/V8.33' / relative.with_suffix('.pc')
            if not pc.exists(): pc = pc.with_suffix('.PC')
            row['preexisting_pc_present'] = pc.exists()
            if pc.exists(): row['preexisting_pc_sha256'] = hashlib.sha256(pc.read_bytes()).hexdigest()
            try:
                result = translate(raw.decode('utf-8-sig'), filename=str(path))
                row.update(status='translated', python_sha256=result.report['python_sha256'],
                           features=result.report['features'])
            except TranslationError as exc:
                row.update(status='rejected', diagnostic=exc.as_dict())
            rows.append(row)
    counts = dict(collections.Counter(row['status'] for row in rows))
    report = dict(date='2026-10-13', translator_version=__version__, selection='First eight lexically sorted V8.33 KL files in each of six named categories',
                  counts=counts, boundary='Source translation only. Existing paired PCs are hashed as corpus provenance; no fresh compiler run, corpus execution, or runtime equivalence check.', cases=rows)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(counts))


if __name__ == '__main__': main()
