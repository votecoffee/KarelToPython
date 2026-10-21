"""The generated module can run with just the small runtime distribution."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate


ROOT = Path(__file__).resolve().parents[1]


class RuntimePortabilityTests(unittest.TestCase):
    def test_only_init_and_runtime_needed(self):
        examples = [('control_flow', 'TOTAL', 200), ('parameters', 'FACTORIAL_RESULT', 120),
                    ('aggregate_parameters', 'VALUES', [99, 20, 30, 40]),
                    ('string_processing', 'LABELS', ['AB', 'BC']),
                    ('exact_numeric', 'HALF_VALUE', 1.25),
                    ('structures', 'SEEN_AFTER_COPY', 5),
                    ('labelled_flow', 'TOTAL', 33),
                    ('loop_routines', 'FIRST_ZERO', 3),
                    ('multidimensional_arrays', 'FOUND_COORDINATE', 23),
                    ('narrow_integers', 'SENTINEL_DETECTED', True),
                    ('square_roots', 'HYPOTENUSE', 5.0),
                    ('structure_arrays', 'SEEN_AFTER_COPY', 20),
                    ('using_fields', 'VALUE', 90),
                    ('host_delays', 'TOTAL', 6),
                    ('string_value_inputs', 'COPIED', 'ready'),
                    ('string_write_requests', 'TOTAL', 3),
                    ('string_write_formats', 'EMITTED', 11),
                    ('string_write_quotes', 'EMITTED', 11),
                    ('boolean_write_requests', 'CHECKS', 5),
                    ('pythonic_numeric', 'ROUNDED', 2),
                    ('pythonic_output', 'COUNT', -42),
                    ('pythonic_strings', 'DECORATED', '[seed]'),
                    ('pythonic_order', 'RESULT', 12),
                    ('pythonic_arrays', 'GENERATED', [40, 5, 6]),
                    ('pythonic_array_shapes', 'NAMED', [[1, 2, 3], [4, 5, 6]]),
                    ('pythonic_text_formats', 'SCIENTIFIC', '   1.235E+02'),
                    ('pythonic_string_operations', 'PAYLOAD', 'robot'),
                    ('pythonic_for', 'TOTAL', 6),
                    ('pythonic_using', 'RESULT', 49),
                    ('pythonic_type_aliases', 'TOTAL', 7),
                    ('pythonic_vectors', 'LENGTH', 5.0),
                    ('pythonic_read', 'TOTAL', 30),
                    ('pythonic_text_input', 'TOTAL', 35),
                    ('pythonic_read_formats', 'TOTAL', 44),
                    ('pythonic_pos', 'X', 1.5),
                    ('pythonic_config_text', 'FAIL_CODE', 1),
                    ('pythonic_directives', 'TOTAL', 10),
                    ('pythonic_frames', 'CODE', 0),
                    ('pythonic_frame_constructor', 'CODE', 0),
                    ('pythonic_position_conversions', 'CODE', 0),
                    ('pythonic_position_geometry', 'CODE', 0),
                    ('pythonic_position_axes', 'CODE', 0),
                    ('pythonic_position_comparisons', 'NEAR', True)]
        for example, key, expected in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as folder:
                result = translate((ROOT / f'examples/{example}.kl').read_text())
                target = Path(folder)
                package = target / 'karel2py'
                package.mkdir()
                for name in ('__init__.py', 'runtime.py'):
                    shutil.copyfile(ROOT / 'karel2py' / name, package / name)
                (target / 'converted.py').write_text(result.python_source, encoding='utf-8')
                input_file=ROOT/f'examples/{example}.read.values.json'
                batches=json.loads(input_file.read_text()) if input_file.exists() else []
                adapter='read=lambda request: next(responses)' if input_file.exists() else ''
                setup=f'responses=iter({batches!r})\n'
                text_file=ROOT/f'examples/{example}.input.txt'
                if text_file.exists():
                    setup=f'from karel2py.runtime import TextInput\nresponses=TextInput({text_file.read_text()!r})\n'
                    adapter='read=responses'
                context_file=ROOT/f'examples/{example}.context.expected.json'
                context=json.loads(context_file.read_text()) if context_file.exists() else {}
                adapter+=(', ' if adapter else '')+f'**{context!r}'
                (target / 'check.py').write_text('import json\nfrom converted import Program\n'
                                               +setup+f'print(json.dumps(Program({adapter}).run()))\n')
                process = subprocess.run([sys.executable, 'check.py'], cwd=target, capture_output=True, text=True)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(json.loads(process.stdout)[key], expected)

    def test_source_identifiers_do_not_collide_with_python_keywords(self):
        result = translate('PROGRAM T\nVAR class, print, R: INTEGER\nBEGIN class = 1 print = 2 R = class + print END T')
        namespace = {'__name__': 'generated'}
        exec(result.python_source, namespace)
        self.assertEqual(namespace['Program']().run()['R'], 3)


if __name__ == '__main__': unittest.main()
