"""Read-only V8.33 ampersand source scan; no compiler or corpus execution."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from karel2py import __version__, translate
from karel2py.lexer import TranslationError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base = args.corpus / 'KL/V8.33'
    files = sorted(base.rglob('*.KL'))
    if not files:
        raise SystemExit('No V8.33 KL sources found')
    manifest, cases = [], []
    raw_count = 0
    for source in files:
        raw = source.read_bytes()
        relative = source.relative_to(base).as_posix()
        row = dict(relative_source=relative, bytes=len(raw), source_sha256=hashlib.sha256(raw).hexdigest())
        manifest.append(row)
        count = raw.count(b'&')
        raw_count += count
        if not count:
            continue
        row = dict(row, source=str(source), raw_ampersands=count)
        pc = args.corpus / 'PC/V8.33' / Path(relative).with_suffix('.pc')
        if not pc.exists(): pc = pc.with_suffix('.PC')
        row['preexisting_pc_present'] = pc.exists()
        if pc.exists(): row['preexisting_pc_sha256'] = hashlib.sha256(pc.read_bytes()).hexdigest()
        try:
            result = translate(raw.decode('utf-8-sig'), filename=str(source))
            row.update(status='translated', continuations=result.report['continuations'], python_sha256=result.report['python_sha256'])
        except TranslationError as exc:
            row.update(status='rejected', diagnostic=exc.as_dict())
        cases.append(row)
    encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    package = Path(__file__).resolve().parents[1]
    report = dict(date='2026-10-13', translator_version=__version__, corpus_base=str(base),
                  selection='All V8.33 *.KL files, sorted by path; raw ASCII ampersand search includes comments and literals',
                  scanned_files=len(files), scanned_bytes=sum(row['bytes'] for row in manifest),
                  source_manifest_encoding='Sorted path/bytes/source_sha256 records serialized with sorted JSON keys, compact separators, ensure_ascii=True',
                  source_manifest_sha256=hashlib.sha256(encoded).hexdigest(),
                  raw_ampersands=raw_count, matching_files=len(cases),
                  translator_sources={name: hashlib.sha256((package / 'karel2py' / name).read_bytes()).hexdigest()
                                      for name in ['__init__.py', 'compiler.py', 'lexer.py', 'runtime.py']},
                  counts=dict(collections.Counter(row['status'] for row in cases)), cases=cases,
                  boundary='Only this V8.33 tree was scanned. Absence of ampersands does not establish coverage in other releases or the 465-heading inventory. No added original-source acceptance claimed; no corpus execution or compiler/controller run.')
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(scanned_files=len(files), matching_files=len(cases), raw_ampersands=raw_count)))


if __name__ == '__main__': main()
