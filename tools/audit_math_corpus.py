"""Focused SQRT source audit. Original KL/PC files are read, hashed and never executed."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys


SELECTED = ['builtin_function/KB00187.KL', 'math_builtin/KF00066.KL',
            *[f'Probes4/NumericMath/NM{number:04d}.KL' for number in range(43, 52)],
            'Probes4/NumericMath/NM0054.KL']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--translator-package', type=Path, default=Path(__file__).resolve().parents[1],
                        help='Package root; may point at an authenticated earlier ZIP extraction')
    args = parser.parse_args()
    sys.path.insert(0, str(args.translator_package.resolve()))
    from karel2py import __version__, translate
    from karel2py.lexer import TranslationError
    rows = []
    for relative in SELECTED:
        source = args.corpus / 'KL/V8.33' / relative
        raw = source.read_bytes()
        pc = args.corpus / 'PC/V8.33' / Path(relative).with_suffix('.pc')
        if not pc.exists(): pc = pc.with_suffix('.PC')
        row = dict(relative_source=relative, source=str(source), source_sha256=hashlib.sha256(raw).hexdigest(),
                   preexisting_pc_present=pc.exists())
        if pc.exists(): row['preexisting_pc_sha256'] = hashlib.sha256(pc.read_bytes()).hexdigest()
        try:
            result = translate(raw.decode('utf-8-sig'), filename=str(source))
            row.update(status='translated', python_sha256=result.report['python_sha256'], features=result.report['features'],
                       runtime_outcome='Not observed; accepted source may fail exactness, domain or initialization checks')
        except TranslationError as exc:
            row.update(status='rejected', diagnostic=exc.as_dict())
        rows.append(row)
    report = dict(date='2026-10-13', translator_version=__version__, selection=SELECTED, feature='SQRT',
                  translator_sources={name: hashlib.sha256((args.translator_package / 'karel2py' / name).read_bytes()).hexdigest()
                                      for name in ['__init__.py','compiler.py','lexer.py','runtime.py'] + (['extended.py'] if (args.translator_package/'karel2py'/'extended.py').is_file() else [])},
                  counts=dict(collections.Counter(row['status'] for row in rows)), cases=rows,
                  boundary='Fixed supplementary source sample, separate from the original 48-source audit. Full declarations are preserved. Translation accepts negative and irrational-root expressions; prototype runtime checks them when evaluated. Paired PCs provide provenance only; no source execution, compiler run or controller validation.')
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
        prior = {case['relative_source']: case for case in baseline['cases']}
        assert set(prior) == set(SELECTED)
        for row in rows:
            old = prior[row['relative_source']]
            assert row['source_sha256'] == old['source_sha256']
            assert row.get('preexisting_pc_sha256') == old.get('preexisting_pc_sha256')
        changes = collections.Counter(prior[row['relative_source']]['status'] + '_to_' + row['status'] for row in rows)
        report['comparison'] = dict(baseline_version=baseline['translator_version'], same_source_and_pc_hashes=True,
                                    baseline_report_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
                                    newly_translated=changes['rejected_to_translated'], regressions=changes['translated_to_rejected'],
                                    transitions=dict(changes))
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(counts=report['counts'], comparison=report.get('comparison'))))


if __name__ == '__main__': main()
