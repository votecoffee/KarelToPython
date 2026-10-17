"""Read-only predefined-name scan and full-source translation; never executes KL."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys


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
    names = {'ON', 'OFF', 'MININT', 'MAXINT'}
    cases, manifest = [], []
    totals = collections.Counter()
    for source in files:
        raw = source.read_bytes()
        text = raw.decode('utf-8-sig')
        relative = source.relative_to(base).as_posix()
        digest = hashlib.sha256(raw).hexdigest()
        manifest.append(dict(relative_source=relative, bytes=len(raw), source_sha256=digest))
        uses = collections.Counter(match.group().upper() for match in PATTERN.finditer(text)
                                   if match.lastgroup == 'NAME' and match.group().upper() in names)
        totals.update(uses)
        if not uses: continue
        row = dict(relative_source=relative, source=str(source), source_sha256=digest, predefined_tokens=dict(uses))
        pc = args.corpus / 'PC/V8.33' / Path(relative).with_suffix('.pc')
        if not pc.exists(): pc = pc.with_suffix('.PC')
        row['preexisting_pc_present'] = pc.exists()
        if pc.exists(): row['preexisting_pc_sha256'] = hashlib.sha256(pc.read_bytes()).hexdigest()
        try:
            result = translate(text, filename=str(source))
            row.update(status='translated', python_sha256=result.report['python_sha256'], predefined_uses=result.report.get('predefined_uses', []))
        except TranslationError as exc:
            row.update(status='rejected', diagnostic=exc.as_dict())
        cases.append(row)
    encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    report = dict(date='2026-10-13', translator_version=__version__, scanned_files=len(files),
                  source_manifest_sha256=hashlib.sha256(encoded).hexdigest(),
                  selection='Every V8.33 KL source with lexical ON/OFF/MININT/MAXINT name tokens; strings, comments and directives excluded by the lexer pattern',
                  token_counts=dict(totals), counts=dict(collections.Counter(row['status'] for row in cases)), cases=cases,
                  translator_sources={name: hashlib.sha256((args.translator_package / 'karel2py' / name).read_bytes()).hexdigest()
                                      for name in ['__init__.py', 'compiler.py', 'lexer.py', 'runtime.py']},
                  boundary='Original full source and paired-PC hashes only. Unsupported controller declarations/constructs remain blockers. No trimmed source, corpus execution, compiler invocation or controller validation. Only the V8.33 tree was scanned.')
    if args.baseline:
        old = json.loads(args.baseline.read_text(encoding='utf-8'))
        prior = {row['relative_source']: row for row in old['cases']}
        assert old['source_manifest_sha256'] == report['source_manifest_sha256']
        assert set(prior) == {row['relative_source'] for row in cases}
        for row in cases:
            before = prior[row['relative_source']]
            assert row['source_sha256'] == before['source_sha256']
            assert row.get('preexisting_pc_sha256') == before.get('preexisting_pc_sha256')
            assert row['predefined_tokens'] == before['predefined_tokens']
        transitions = collections.Counter(prior[row['relative_source']]['status'] + '_to_' + row['status'] for row in cases)
        report['comparison'] = dict(baseline_version=old['translator_version'], same_source_and_pc_hashes=True,
                                    baseline_report_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
                                    newly_translated=transitions['rejected_to_translated'], regressions=transitions['translated_to_rejected'],
                                    transitions=dict(transitions))
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(scanned_files=len(files), matching_sources=len(cases), token_counts=dict(totals), counts=report['counts'], comparison=report.get('comparison'))))


if __name__ == '__main__': main()
