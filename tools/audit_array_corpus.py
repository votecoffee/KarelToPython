"""Audit unchanged array-feature sources; retain earlier blocking features."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--feature', choices=['multidimensional', 'narrow_integers', 'structure_elements'], default='multidimensional')
    parser.add_argument('--translator-package', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    sys.path.insert(0, str(args.translator_package.resolve()))
    from karel2py import __version__, translate
    from karel2py.lexer import TranslationError
    if args.feature == 'multidimensional':
        selected = ['types/KX00021.KL', 'builtin_completion/KC00029.KL', 'builtin_completion/KC00030.KL']
        pattern, declaration_key = r'\bARRAY\s*\[[^\]]*,[^\]]*\]', 'multidimensional_declarations'
        boundary = 'Three unchanged V8.33 sources containing multidimensional declarations. Earlier unsupported declarations/directives remain blockers; rejection does not validate their array operations. No trimmed-source translation, corpus execution, compiler invocation or controller validation.'
    elif args.feature == 'narrow_integers':
        selected = ['types/KX00018.KL', 'types/KX00019.KL']
        pattern, declaration_key = r'\bARRAY\s*\[[^\]]*\]\s+OF\s+(BYTE|SHORT)\b', 'narrow_integer_declarations'
        boundary = 'Two unchanged V8.33 BYTE/SHORT array cases. Earlier unsupported FILE declarations remain blockers; rejection does not validate narrow-integer execution. No trimmed-source translation, corpus execution, compiler invocation or controller validation.'
    else:
        selected = [f'special_type_matrix/KS{number:05d}.KL' for number in (52, 54, 55, 56)]
        pattern, declaration_key = r'\bARRAY\s*\[[^\]]*\]\s+OF\s+REC_T\b', 'structure_array_declarations'
        boundary = 'Four unchanged V8.33 structure-array cases. Full declarations are retained. Source translation is separate from execution: partially initialized aggregate copies can translate and then fail the prototype runtime guard. GET_VAR/SET_VAR remain controller blockers. No trimmed-source translation, corpus execution, compiler invocation or controller validation.'
    rows = []
    for relative in selected:
        source = args.corpus / 'KL/V8.33' / relative
        raw = source.read_bytes()
        text = raw.decode('utf-8-sig')
        pc = args.corpus / 'PC/V8.33' / Path(relative).with_suffix('.pc')
        if not pc.exists(): pc = pc.with_suffix('.PC')
        declarations = [dict(line=i, text=line.strip()) for i, line in enumerate(text.splitlines(), 1)
                        if re.search(pattern, line, re.IGNORECASE)]
        assert declarations
        row = dict(relative_source=relative, source=str(source), source_sha256=hashlib.sha256(raw).hexdigest(),
                   preexisting_pc_present=pc.exists())
        row[declaration_key] = declarations
        if pc.exists(): row['preexisting_pc_sha256'] = hashlib.sha256(pc.read_bytes()).hexdigest()
        try:
            result = translate(text, filename=str(source))
            row.update(status='translated', python_sha256=result.report['python_sha256'], features=result.report['features'])
        except TranslationError as exc:
            row.update(status='rejected', diagnostic=exc.as_dict(),
                       first_blocker_precedes_array_declarations=exc.token.line < min(item['line'] for item in declarations))
        rows.append(row)
    report = dict(date='2026-10-13', translator_version=__version__, feature=args.feature, selection=selected,
                  translator_sources={name: hashlib.sha256((args.translator_package / 'karel2py' / name).read_bytes()).hexdigest()
                                      for name in ['__init__.py','compiler.py','lexer.py','runtime.py'] + (['extended.py'] if (args.translator_package/'karel2py'/'extended.py').is_file() else [])},
                  counts=dict(collections.Counter(row['status'] for row in rows)), cases=rows,
                  boundary=boundary)
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
        prior = {case['relative_source']: case for case in baseline['cases']}
        assert set(prior) == set(selected)
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
