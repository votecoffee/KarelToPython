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
    def test_runtime_distribution_without_compiler(self):
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
                    ('pythonic_position_comparisons', 'NEAR', True),
                    ('pythonic_wait', 'AFTER_WAIT', 3),
                    ('pythonic_time_text', 'ENCODED', 1482515548),
                    ('pythonic_microseconds', 'ELAPSED', 35),
                    ('pythonic_numeric_registers', 'VALUE', 42),
                    ('calendar_clock', 'STAMP', 1482515548),
                    ('calendar_reset', 'READBACK', -2145320960),
                    ('file_compare', 'DIFFERENT', 2),
                    ('file_print', 'STATUS', 0),
                    ('joint_assignment', 'RESTORED', {'axes': [0.] * 9}),
                    ('joint_external_assignment', 'RESTORED', {'axes': [0., 25.] + [0.] * 7}),
                    ('pulse_wait', 'AFTER', False),
                    ('pulse_override', 'AFTER', True),
                    ('record_initialization', 'PARTIAL', True),
                    ('pose_initialization', 'AXES_READY', True),
                    ('variable_metadata', 'CODE', 209),
                    ('variable_catalog', 'COUNT', 1),
                    ('joint_geometry', 'INVERSE_X', -200.),
                    ('joint_mirror', 'REFLECTED_Y', -100.),
                    ('program_catalog', 'COUNT', 1),
                    ('program_pages', 'CURSOR_NO', 3),
                    ('program_metadata', 'COMMENT', 'converted'),
                    ('teach_programs', 'AVAILABLE', 5),
                    ('teach_registers', 'NUMBER', 42),
                    ('source_policies', 'SIZE', 10),
                    ('path_geometry', 'NODE_BYTES', 28),
                    ('xml_input', 'STATUS', 0),
                    ('serial_attributes', 'BAUD', 9600),
                    ('virtual_devices', 'TOTAL', 256),
                    ('device_capacity', 'FREE_AFTER', 4),
                    ('remote_banks', 'NUMBER', 42),
                    ('register_transfers', 'STATUS', 0),
                    ('pose_decomposition', 'CONSTRUCTOR_X', 4.),
                    ('joint_decomposition', 'X', 100.),
                    ('collection_state', 'FIRST', 42),
                    ('restored_collections', 'NEW_ID', 4),
                    ('variable_prefix', 'DESTINATION', [[10,20,30],[40,50,60]]),
                    ('variable_missing', 'PARTIAL_STATUS', 12311),
                    ('queue_transfer', 'N', 30),
                    ('queue_missing', 'MISSING_STATUS', 12311),
                    ('file_move', 'MOVE_STATUS', 0),
                    ('file_move_guards', 'BUSY_STATUS', 3),
                    ('port_configuration', 'ACTIVE_MODE', 0),
                    ('port_configuration_guards', 'WRONG_DIRECTION', 3)]
        for example, key, expected in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as folder:
                result = translate((ROOT / f'examples/{example}.kl').read_text())
                target = Path(folder)
                package = target / 'karel2py'
                package.mkdir()
                for name in ('__init__.py', 'runtime.py', 'extended.py', 'storage.py', 'kinematics.py', 'scheduling.py', 'control.py', 'clocks.py', 'fileops.py', 'pulses.py', 'inspection.py', 'configtext.py', 'teach.py', 'xmlio.py', 'devices.py', 'dynamic.py', 'programs.py', 'remote.py'):
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
                registers_file=ROOT/f'examples/{example}.registers.initial.json'
                if registers_file.exists():
                    setup+='from karel2py.runtime import NumericRegisters\n'
                    adapter+=(', ' if adapter else '')+f'registers=NumericRegisters.from_config({json.loads(registers_file.read_text())!r})'
                services_file=ROOT/f'examples/{example}.services.initial.json'
                if services_file.exists():
                    setup+='from karel2py.runtime import ExecutionContext\n'
                    adapter+=(', ' if adapter else '')+f'context=ExecutionContext.from_config({json.loads(services_file.read_text())!r})'
                adapter+=(', ' if adapter else '')+f'sleep=lambda _: None, **{context!r}'
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

    def test_task_inspection_without_compiler(self):
        observer=translate("PROGRAM OBSERVER VAR name,text: STRING[16] number,value,status: INTEGER BEGIN name='worker' GET_TSK_INFO(name,number,TSK_STATUS,value,text,status) END OBSERVER")
        worker=translate('PROGRAM WORKER VAR n: INTEGER BEGIN n=1 PAUSE n=2 END WORKER')
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder);package=target/'karel2py';package.mkdir()
            for name in ('__init__.py','runtime.py','extended.py','storage.py','kinematics.py','scheduling.py','control.py','clocks.py', 'fileops.py', 'pulses.py', 'configtext.py', 'teach.py', 'xmlio.py', 'devices.py', 'dynamic.py', 'programs.py'):
                shutil.copyfile(ROOT/'karel2py'/name,package/name)
            (target/'observer.py').write_text(observer.python_source,encoding='utf-8')
            (target/'worker.py').write_text(worker.python_source,encoding='utf-8')
            script='''from karel2py import runtime as rt
from observer import Program as Observer
from worker import Program as Worker
ctx=rt.ExecutionContext();worker=Worker(context=ctx);ctx.tasks.bind('worker',worker)
try: worker.run()
except rt.KarelPause: pass
else: raise AssertionError('worker did not pause')
state=Observer(context=ctx).run()
assert (state['NAME'],state['NUMBER'],state['VALUE'],state['STATUS'])==('worker',1,rt.TASK_CONSTANTS['PG_PAUSED'],0)
assert worker.task_state=='paused'
'''
            (target/'check.py').write_text(script,encoding='utf-8')
            process=subprocess.run([sys.executable,'check.py'],cwd=target,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)


if __name__ == '__main__': unittest.main()
