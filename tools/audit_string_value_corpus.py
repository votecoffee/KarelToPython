"""Translate fixed original STRING call/return controls; never execute KL or PCs."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys


SELECTED = [f'Probes4/CallsReturns/CA{number:04d}.KL' for number in (91, 92, 93, 94, 108)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--translator-package', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    sys.path.insert(0, str(args.translator_package.resolve()))
    from karel2py import __version__, translate
    from karel2py.lexer import TranslationError
    cases = []
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
            row.update(status='translated', python_sha256=result.report['python_sha256'],
                       string_value_arguments=result.report.get('string_value_arguments', []),
                       routine_effects=result.report['routine_effects'])
        except TranslationError as exc:
            row.update(status='rejected', diagnostic=exc.as_dict())
        cases.append(row)
    report = dict(date='2026-10-13', translator_version=__version__, selection=SELECTED,
                  feature='STRING reference, grouped-value, literal-value and STRING-return controls',
                  counts=dict(collections.Counter(row['status'] for row in cases)), cases=cases,
                  translator_sources={name: hashlib.sha256((args.translator_package / 'karel2py' / name).read_bytes()).hexdigest()
                                      for name in ['__init__.py', 'compiler.py', 'lexer.py', 'runtime.py']},
                  boundary='Fixed five-source V8.33 sample. Complete declarations and paired PCs are preserved; earlier geometry blockers remain meaningful. No trimmed source, source execution, compiler run or controller validation. STRING-return compiler corpus presence does not resolve the conflicting manual statements or establish runtime behavior.')
    if args.baseline:
        old = json.loads(args.baseline.read_text(encoding='utf-8'))
        prior = {row['relative_source']: row for row in old['cases']}
        assert old['selection'] == SELECTED and set(prior) == set(SELECTED)
        for row in cases:
            before = prior[row['relative_source']]
            assert row['source_sha256'] == before['source_sha256']
            assert row.get('preexisting_pc_sha256') == before.get('preexisting_pc_sha256')
        transitions = collections.Counter(prior[row['relative_source']]['status'] + '_to_' + row['status'] for row in cases)
        diagnostics = collections.Counter()
        for row in cases:
            before = prior[row['relative_source']]
            if before['status'] == row['status'] == 'rejected' and before['diagnostic']['code'] != row['diagnostic']['code']:
                diagnostics[before['diagnostic']['code'] + '_to_' + row['diagnostic']['code']] += 1
        report['comparison'] = dict(baseline_version=old['translator_version'], same_source_and_pc_hashes=True,
                                    baseline_report_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
                                    newly_translated=transitions['rejected_to_translated'], regressions=transitions['translated_to_rejected'],
                                    transitions=dict(transitions), diagnostic_changes=dict(diagnostics))
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(counts=report['counts'], comparison=report.get('comparison'))))


if __name__ == '__main__': main()
