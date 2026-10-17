"""Read-only original conversion sources; no trimming, execution or compiler run."""
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
    parser.add_argument('--feature', choices=['integer_text', 'real_text', 'real_format'], default='integer_text')
    parser.add_argument('--translator-package', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    sys.path.insert(0, str(args.translator_package.resolve()))
    from karel2py import __version__, translate
    from karel2py.lexer import TranslationError
    selections = {
        'integer_text': ['builtin_procedure/KB00035.KL', 'builtin_procedure/KB00040.KL',
                         'conversion_text/KF00076.KL', 'conversion_text/KF00077.KL'],
        'real_text': ['builtin_procedure/KB00041.KL', 'conversion_text/KF00079.KL',
                      'builtin_procedure/KB00037.KL', 'conversion_text/KF00078.KL'],
        'real_format': ['builtin_procedure/KB00037.KL', 'conversion_text/KF00078.KL'],
    }
    selected = selections[args.feature]
    cases = []
    for relative in selected:
        source = args.corpus / 'KL/V8.33' / relative
        raw = source.read_bytes()
        row = dict(relative_source=relative, source=str(source), source_sha256=hashlib.sha256(raw).hexdigest())
        pc = args.corpus / 'PC/V8.33' / Path(relative).with_suffix('.pc')
        if not pc.exists(): pc = pc.with_suffix('.PC')
        row['preexisting_pc_present'] = pc.exists()
        if pc.exists(): row['preexisting_pc_sha256'] = hashlib.sha256(pc.read_bytes()).hexdigest()
        try:
            result = translate(raw.decode('utf-8-sig'), filename=str(source))
            row.update(status='translated', python_sha256=result.report['python_sha256'], features=result.report['features'])
            if 'conversion_policy' in result.report: row['conversion_policy'] = result.report['conversion_policy']
        except TranslationError as exc:
            row.update(status='rejected', diagnostic=exc.as_dict())
        cases.append(row)
    report = dict(date='2026-10-13', translator_version=__version__, feature=args.feature, selection=selected,
                  translator_sources={name: hashlib.sha256((args.translator_package / 'karel2py' / name).read_bytes()).hexdigest()
                                      for name in ['__init__.py', 'compiler.py', 'lexer.py', 'runtime.py']},
                  counts=dict(collections.Counter(row['status'] for row in cases)), cases=cases,
                  boundary='Unchanged full original V8.33 conversion sources. Translation acceptance is separate from procedure outcomes. Geometry declarations and environment directives remain blockers. No corpus execution, compiler invocation or controller validation.')
    if args.baseline:
        old = json.loads(args.baseline.read_text(encoding='utf-8'))
        prior = {row['relative_source']: row for row in old['cases']}
        assert set(prior) == set(selected)
        for row in cases:
            before = prior[row['relative_source']]
            assert row['source_sha256'] == before['source_sha256']
            assert row.get('preexisting_pc_sha256') == before.get('preexisting_pc_sha256')
        transitions = collections.Counter(prior[row['relative_source']]['status'] + '_to_' + row['status'] for row in cases)
        report['comparison'] = dict(baseline_version=old['translator_version'], same_source_and_pc_hashes=True,
                                    baseline_report_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
                                    newly_translated=transitions['rejected_to_translated'], regressions=transitions['translated_to_rejected'],
                                    transitions=dict(transitions))
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(counts=report['counts'], comparison=report.get('comparison'))))


if __name__ == '__main__': main()
