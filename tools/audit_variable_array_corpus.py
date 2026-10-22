"""Read-only positional token scan and full-source translation; never invokes an output adapter or runs KL."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys


# Stable independent selection, including formal and declaration syntax.
# Every non-whitespace character is retained so 2*3 is not a wildcard.
import re
ARRAY_PATTERN = re.compile(
    r"(?P<COMMENT>--[^\r\n\f]*)|(?P<DIRECTIVE>%[^\r\n\f]*)|"
    r"(?P<STRING>'(?:[^'\r\n\f]|'')*')|(?P<NL>\r\n|[\r\n\f])|"
    r"(?P<CONT>&[ \t]*(?:--[^\r\n\f]*)?(?=\r\n|[\r\n\f]|$))|"
    r"(?P<SPACE>[^\S\r\n\f]+)|(?P<NAME>[A-Za-z_][A-Za-z_0-9]*)|(?P<OTHER>.)"
)

def wildcard_array_tokens(text):
    tokens, uses, line, column = [], [], 1, 1
    for match in ARRAY_PATTERN.finditer(text):
        kind, value = match.lastgroup, match.group()
        if kind not in ('COMMENT','DIRECTIVE','STRING','NL','SPACE','CONT'):
            tokens.append((value.upper(),line,column))
        elif kind == 'STRING':
            tokens.append(('<STRING>',line,column))
        if kind == 'NL': line, column = line + 1, 1
        else: column += len(value)
    for i, (value,line,column) in enumerate(tokens):
        if value != 'ARRAY' or i+1 == len(tokens) or tokens[i+1][0] != '[': continue
        dimensions, dimension, depth = [], [], 0
        for token in tokens[i+2:]:
            value = token[0]
            if value == ']' and depth == 0:
                dimensions.append(dimension)
                stars = [n+1 for n, items in enumerate(dimensions) if len(items)==1 and items[0][0]=='*']
                if stars: uses.append(dict(line=line,column=column,declared_rank=len(dimensions),wildcard_dimensions=stars))
                break
            if value == ',' and depth == 0: dimensions.append(dimension); dimension=[]
            else:
                dimension.append(token)
                if value in ('[','('): depth += 1
                elif value in (']',')'): depth -= 1
            if depth < 0: break
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
    from karel2py.lexer import TranslationError
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
        tokens = wildcard_array_tokens(text)
        if not tokens: continue
        token_count += len(tokens)
        row = dict(relative_source=relative, source=str(source), source_sha256=digest, wildcard_array_tokens=tokens)
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
                  selection='Every V8.33 KL source containing a wildcard ARRAY dimension; includes formal and declaration contexts; excludes strings/comments/directives and multiplication-only dimensions; independent stable scanner',
                  selection_boundary='Token selection is not a validated executable-statement count; full-source translation decides support.',
                  wildcard_array_token_count=token_count, counts=dict(collections.Counter(row['status'] for row in cases)), cases=cases,
                  translator_sources={name: hashlib.sha256((args.translator_package / 'karel2py' / name).read_bytes()).hexdigest()
                                      for name in ['__init__.py','compiler.py','lexer.py','runtime.py'] + (['extended.py'] if (args.translator_package/'karel2py'/'extended.py').is_file() else [])},
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
            assert row['wildcard_array_tokens'] == before['wildcard_array_tokens']
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
    print(json.dumps(dict(scanned_files=len(files), matching_sources=len(cases), wildcard_array_token_count=token_count,
                         counts=report['counts'], comparison=report.get('comparison'))))


if __name__ == '__main__': main()
