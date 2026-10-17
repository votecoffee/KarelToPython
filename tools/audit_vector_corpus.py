"""Read-only positional token scan and full-source translation; never invokes an output adapter or runs KL."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys


def vector_tokens(text, pattern):
    uses, line, column = [], 1, 1
    for match in pattern.finditer(text):
        kind, value = match.lastgroup, match.group()
        if kind == 'NAME' and value.upper() in ('VECTOR',):
            uses.append(dict(name=value.upper(), line=line, column=column))
        if kind == 'NL': line, column = line + 1, 1
        else: column += len(value)
    return uses


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--translator-package', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    sys.path.insert(0, str(args.translator_package.resolve()))
    from karel2py import __version__, translate
    from karel2py.lexer import PATTERN, TranslationError
    base = args.corpus / 'KL/V8.33'
    files = sorted(base.rglob('*.KL'))
    if not files: raise SystemExit('No V8.33 KL files found')
    cases, manifest, scanned_bytes, token_count = [], [], 0, 0
    for source in files:
        raw = source.read_bytes()
        text = raw.decode('utf-8-sig')
        relative = source.relative_to(base).as_posix()
        digest = hashlib.sha256(raw).hexdigest()
        scanned_bytes += len(raw)
        manifest.append(dict(relative_source=relative, bytes=len(raw), source_sha256=digest))
        tokens = vector_tokens(text, PATTERN)
        if not tokens: continue
        token_count += len(tokens)
        row = dict(relative_source=relative, source=str(source), source_sha256=digest, vector_tokens=tokens)
        pc = args.corpus / 'PC/V8.33' / Path(relative).with_suffix('.pc')
        if not pc.exists(): pc = pc.with_suffix('.PC')
        row['preexisting_pc_present'] = pc.exists()
        if pc.exists(): row['preexisting_pc_sha256'] = hashlib.sha256(pc.read_bytes()).hexdigest()
        try:
            result = translate(text, filename=str(source))
            row.update(status='translated', python_sha256=result.report['python_sha256'],
                       features=result.report['features'])
        except TranslationError as exc:
            row.update(status='rejected', diagnostic=exc.as_dict())
        cases.append(row)
    encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    report = dict(date='2026-10-15', translator_version=__version__, scanned_files=len(files), scanned_bytes=scanned_bytes,
                  source_manifest_sha256=hashlib.sha256(encoded).hexdigest(),
                  selection='Every V8.33 KL source with a lexical VECTOR name token; strings, comments and directives excluded',
                  selection_boundary='Token selection is not a validated executable-statement count; full-source translation decides support.',
                  vector_token_count=token_count, counts=dict(collections.Counter(row['status'] for row in cases)), cases=cases,
                  translator_sources={name: hashlib.sha256((args.translator_package / 'karel2py' / name).read_bytes()).hexdigest()
                                      for name in ['__init__.py', 'compiler.py', 'lexer.py', 'runtime.py']},
                  boundary='Original complete sources and paired-PC hashes are preserved. No trimmed source, corpus execution, output callback, compiler invocation or controller validation. Only V8.33 was scanned.')
    if args.baseline:
        old = json.loads(args.baseline.read_text(encoding='utf-8'))
        prior = {row['relative_source']: row for row in old['cases']}
        assert old['source_manifest_sha256'] == report['source_manifest_sha256']
        assert old['scanned_files'] == report['scanned_files'] and old['scanned_bytes'] == report['scanned_bytes']
        assert set(prior) == {row['relative_source'] for row in cases}
        for row in cases:
            before = prior[row['relative_source']]
            assert row['source_sha256'] == before['source_sha256']
            assert row.get('preexisting_pc_sha256') == before.get('preexisting_pc_sha256')
            assert row['vector_tokens'] == before['vector_tokens']
        transitions = collections.Counter(prior[row['relative_source']]['status'] + '_to_' + row['status'] for row in cases)
        diagnostic_changes = collections.Counter()
        for row in cases:
            before = prior[row['relative_source']]
            if before['status'] == row['status'] == 'rejected' and before['diagnostic']['code'] != row['diagnostic']['code']:
                diagnostic_changes[before['diagnostic']['code'] + '_to_' + row['diagnostic']['code']] += 1
        report['comparison'] = dict(baseline_version=old['translator_version'], same_source_and_pc_hashes=True,
                                    baseline_report_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
                                    newly_translated=transitions['rejected_to_translated'], regressions=transitions['translated_to_rejected'],
                                    transitions=dict(transitions), diagnostic_changes=dict(diagnostic_changes))
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(scanned_files=len(files), matching_sources=len(cases), vector_token_count=token_count,
                         counts=report['counts'], comparison=report.get('comparison'))))


if __name__ == '__main__': main()
