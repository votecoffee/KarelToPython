"""Translate authored examples afresh and compare independent expected fixtures."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from karel2py import translate
from karel2py.lexer import TranslationError
from karel2py.runtime import KarelAbort


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def run_example(source, *, inject_write=False):
    name = source.stem
    fixture = source.parent
    context_file = fixture / f'{name}.translation_context.json'
    translation_context = read_json(context_file) if context_file.exists() else {}
    result = translate(source.read_text(encoding='utf-8'),
                       filename=source.relative_to(ROOT).as_posix(), **translation_context)
    namespace = {'__name__': 'checked_example'}
    exec(compile(result.python_source, name + '.generated.py', 'exec'), namespace)
    delays, texts = [], []
    context_file = fixture / f'{name}.context.expected.json'
    context = read_json(context_file) if context_file.exists() else {}
    program = namespace['Program'](sleep=delays.append,
                                  write=texts.append if inject_write else None, **context)
    termination_file = fixture / f'{name}.termination.expected.json'
    try:
        snapshot = program.run()
    except KarelAbort:
        if not termination_file.exists():
            raise
        assert program.abort_info == read_json(termination_file), name + ': ABORT evidence'
        snapshot = program.snapshot()
    else:
        assert not termination_file.exists(), name + ': expected ABORT'
        assert program.abort_info is None, name + ': unexpected termination state'
    assert snapshot == read_json(fixture / f'{name}.expected.json'), name + ': snapshot'
    assert program._state.local_frames == [] and program._state.call_depth == 0, name + ': frames'
    sleep_file = fixture / f'{name}.sleep.expected.json'
    assert delays == (read_json(sleep_file) if sleep_file.exists() else []), name + ': delays'
    write_file = fixture / f'{name}.write.expected.json'
    expected_texts = read_json(write_file) if write_file.exists() else []
    assert [row['text'] for row in program.write_requests] == expected_texts, name + ': WRITE records'
    outcome = 'callback_completed' if inject_write else 'recorded'
    assert all(row['adapter_outcome'] == outcome for row in program.write_requests), name + ': WRITE outcomes'
    assert texts == (expected_texts if inject_write else []), name + ': WRITE callback'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    count = 0
    for source in sorted((ROOT / 'examples').glob('*.kl')):
        if source.stem == 'unsupported_motion':
            try:
                translate(source.read_text(encoding='utf-8'), filename=source.name)
            except TranslationError:
                continue
            raise AssertionError('Unsupported-motion example unexpectedly translated')
        run_example(source)
        if (source.parent / f'{source.stem}.write.expected.json').exists():
            run_example(source, inject_write=True)
        count += 1
        print('PASS ' + source.stem)
    assert count == 48, 'Update the expected example count when adding examples'
    print(f'{count} examples passed; unsupported motion rejected; no generated files written')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
