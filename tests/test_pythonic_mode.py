"""Public Pythonic numeric behavior, generated execution and policy isolation."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


def compile_program(body, *, declarations='r,s: REAL i: INTEGER text: STRING[32]',
                    prefix='', routines='', translator=translate):
    source = f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result = translator(source, filename='pythonic.kl')
    namespace = {'__name__': 'pythonic_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, **kwargs):
    return compile_program(body, **kwargs)[0].run()


class PythonicNumericTests(unittest.TestCase):
    def test_ordinary_literals_constants_and_rounding(self):
        state = execute('r=C s=0.1+0.2', prefix='CONST C=1.0/3.0')
        self.assertEqual(state['R'], 1.0 / 3.0)
        self.assertEqual(state['S'], 0.1 + 0.2)

    def test_python_float_range_subnormals_and_underflow(self):
        for literal, expected in [('1E100', 1e100), ('1E-39', 1e-39),
                                  ('5E-324', 5e-324), ('1E-99999', 0.0)]:
            with self.subTest(literal=literal):
                self.assertEqual(execute('r=' + literal)['R'], expected)

    def test_literal_overflow_is_source_located(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('r=1E99999')
        self.assertEqual(caught.exception.code, 'E_REAL_LITERAL')
        self.assertEqual(caught.exception.filename, 'pythonic.kl')

    def test_integer_promotion_beyond_binary32_precision(self):
        self.assertEqual(execute('i=16777217 r=i')['R'], 16777217.0)

    def test_arithmetic_matches_host_float(self):
        for expression, expected in [('0.1+0.2', 0.1+0.2), ('1.0/3', 1.0/3),
                                     ('0.2*0.3', 0.2*0.3), ('0.1-0.2', 0.1-0.2),
                                     ('ABS(-0.1)', 0.1)]:
            with self.subTest(expression=expression):
                self.assertEqual(execute('r=' + expression)['R'], expected)

    def test_signed_zero_survives_scalar_operations(self):
        self.assertEqual(math.copysign(1, execute('r=-0.0 s=r*2')['S']), -1)

    def test_round_uses_ties_to_even(self):
        for value in (0.1, 0.5, 1.5, 2.5, -0.5, -1.5, -2.5, 123.7):
            with self.subTest(value=value):
                self.assertEqual(execute(f'i=ROUND({value})')['I'], round(value))

    def test_truncation_toward_zero(self):
        for value in (1.9, -1.9, 0.1, -0.1):
            with self.subTest(value=value):
                self.assertEqual(execute(f'i=TRUNC({value})')['I'], math.trunc(value))

    def test_signed_remainder_matches_python(self):
        for left, right in ((-11, 2), (11, -2), (-11, -2)):
            with self.subTest(left=left, right=right):
                self.assertEqual(execute(f'i=({left}) MOD ({right})')['I'], left % right)

    def test_general_math_functions(self):
        for expression, expected in [('SQRT(2)', math.sqrt(2)), ('EXP(1)', math.e),
                                     ('LN(0.1)', math.log(.1)), ('LN(EXP(1))', 1.0)]:
            with self.subTest(expression=expression):
                self.assertAlmostEqual(execute('r=' + expression)['R'], expected)

    def test_general_degree_trigonometry(self):
        for name, function in [('SIN', math.sin), ('COS', math.cos), ('TAN', math.tan)]:
            for angle in (10.1, -10.1, 18001):
                with self.subTest(name=name, angle=angle):
                    self.assertAlmostEqual(execute(f'r={name}({angle})')['R'],
                                           function(math.radians(angle)), places=11)

    def test_inverse_trigonometry_in_degrees(self):
        for name, function in [('ASIN', math.asin), ('ACOS', math.acos)]:
            self.assertAlmostEqual(execute(f'r={name}(0.1)')['R'], math.degrees(function(.1)))

    def test_exact_trig_identities_remain_exact(self):
        self.assertEqual(execute('r=SIN(180) s=COS(90)')['R'], 0.0)
        self.assertEqual(execute('r=SIN(180) s=COS(90)')['S'], 0.0)

    def test_atan2_all_quadrants_keeps_karel_argument_order(self):
        for x, y in ((.1, .2), (-1, 1), (-1, -1), (1, -1), (-1, 0)):
            with self.subTest(x=x, y=y):
                self.assertAlmostEqual(execute(f'r=ATAN2({x},{y})')['R'], math.degrees(math.atan2(y, x)))

    def test_rounded_fixed_decimal_format_and_padding(self):
        state = execute('CNV_REAL_STR(1.234,10,2,text)')
        self.assertEqual(state['TEXT'], '      1.23')
        self.assertEqual(execute('CNV_REAL_STR(2.5,1,0,text)')['TEXT'], ' 2')

    def test_decimal_parse_uses_float(self):
        self.assertEqual(execute("CNV_STR_REAL('0.1',r)")['R'], .1)

    def test_python_numeric_input_grammar(self):
        for text in (' .1 ', '1e-3', '1', '1_000.25'):
            self.assertEqual(execute(f"CNV_STR_REAL('{text}',r)")['R'], float(text))
        self.assertEqual(execute("CNV_STR_INT(' -42 ',i)")['I'], -42)

    def test_invalid_numeric_input_clears_output(self):
        self.assertEqual(execute("r=0.1 CNV_STR_REAL('1x',r)")['R'], {'uninitialized': True})
        self.assertEqual(execute("i=42 CNV_STR_INT('1x',i)")['I'], {'uninitialized': True})

    def test_nonfinite_parsed_input_preserves_output(self):
        for text in ('nan', 'inf', '-Infinity', '1e9999'):
            program, _ = compile_program(f"r=0.1 CNV_STR_REAL('{text}',r)")
            with self.assertRaises(rt.KarelRuntimeError): program.run()
            self.assertEqual(program.snapshot()['R'], .1)

    def test_integer_base_formatting_and_width(self):
        for base, expected in ((2, ' -101010'), (8, ' -52'), (10, ' -42'), (16, ' -2A')):
            self.assertEqual(execute(f'CNV_INT_STR(-42,1,{base},text)')['TEXT'], expected)
        self.assertEqual(execute('CNV_INT_STR(42,8,16,text)')['TEXT'], '      2A')

    def test_integer_base_formatting_matches_independent_oracles(self):
        for base, spec in ((2, 'b'), (8, 'o'), (16, 'X')):
            for value in (-2147483648, -255, 0, 255, 2147483647):
                expected = ' ' + format(value, spec)
                self.assertEqual(execute(f'CNV_INT_STR({"MININT" if value == -2147483648 else value},1,{base},text)')['TEXT'],
                                 expected if len(expected) <= 32 else ' ' + '*' * 31)

    def test_format_capacity_overflow_marker(self):
        state = execute('CNV_REAL_STR(123.456,1,2,text)', declarations='text: STRING[4]')
        self.assertEqual(state['TEXT'], ' ***')

    def test_real_reference_value_and_function_results(self):
        routines = 'ROUTINE f(x: REAL): REAL BEGIN x=x+0.1 RETURN x/3 END f'
        state = execute('r=0.2 s=f((r))', routines=routines)
        self.assertEqual(state['R'], .2)
        self.assertEqual(state['S'], (.2+.1)/3)

    def test_real_array_and_structure_leaves(self):
        state = execute('a[1]=0.1 a[2]=1.0/3 p.x=a[1]+a[2]',
                        declarations='a: ARRAY[2] OF REAL p: pose', prefix='TYPE pose=STRUCTURE x: REAL ENDSTRUCTURE')
        self.assertEqual(state['P']['X'], .1+1/3)

    def test_vector_rounded_scaling_and_parallel_cross_product(self):
        state = execute('a.x=0.1 a.y=0.2 a.z=0.3 b=a/3 c=a#a r=a@a',
                        declarations='a,b,c: VECTOR r: REAL')
        self.assertEqual(state['B']['X'], .1/3)
        self.assertEqual(state['C'], dict(X=0.0, Y=0.0, Z=0.0))
        self.assertAlmostEqual(state['R'], .14)

    def test_joint_conversion_accepts_float_components(self):
        program, _ = compile_program('a[1]=0.1 CNV_REL_JPOS(a,j,i)',
                                     declarations='a: ARRAY[1] OF REAL j: JOINTPOS1 i: INTEGER')
        program = type(program)(joint_axes=1)
        self.assertEqual(program.run()['J'], {'axes': [.1]})


class PythonicGuardTests(unittest.TestCase):
    def test_domain_and_overflow_errors_preserve_destination(self):
        for expression in ('SQRT(-0.1)', 'LN(0)', 'ASIN(1.1)', 'ACOS(-1.1)',
                           'TAN(90)', 'ATAN2(0,0)', 'EXP(1000)', '1E308*10', '1.0/0'):
            with self.subTest(expression=expression):
                program, _ = compile_program('r=0.1 r=' + expression)
                with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
                self.assertIsNotNone(caught.exception.line)
                self.assertEqual(program.snapshot()['R'], .1)
                self.assertEqual(program._state.local_frames, [])

    def test_integer_storage_guards_remain(self):
        for expression in ('ROUND(1E100)', 'TRUNC(2147483647.0)'):
            with self.subTest(expression=expression), self.assertRaises(rt.KarelRuntimeError):
                execute('i=' + expression)

    def test_format_bounds_preserve_destination(self):
        for width, precision in ((0, 2), (255, 2), (1, -255), (1, 255)):
            program, _ = compile_program(f"text='keep' CNV_REAL_STR(0.1,{width},{precision},text)")
            with self.assertRaises(rt.KarelRuntimeError): program.run()
            self.assertEqual(program.snapshot()['TEXT'], 'keep')

    def test_invalid_builtin_types_and_arity(self):
        for expression in ("EXP('x')", 'LN(TRUE)', 'EXP()', 'LN(1,2)'):
            with self.subTest(expression=expression), self.assertRaises(TranslationError):
                compile_program('r=' + expression)

    def test_structural_checks_remain(self):
        for body in ('r=s', 'i=0.1'):
            with self.subTest(body=body), self.assertRaises((TranslationError, rt.KarelRuntimeError)):
                execute(body)

    def test_runtime_policy_restored_after_success_and_failure(self):
        execute('r=0.1')
        with self.assertRaises(rt.KarelRuntimeError): execute('r=SQRT(-1)')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'rounding'): rt.real(.1)

    def test_compile_policy_restored_after_error(self):
        with self.assertRaises(TranslationError): compile_program('r=0.1+TRUE')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'rounding'): rt.real(.1)

    def test_domain_error_unwinds_routine_and_preserves_prior_effects(self):
        routines = "ROUTINE f(value: REAL) BEGIN value=0.2 WRITE('before') value=LN(0) END f"
        program, _ = compile_program('r=0.1 f(r)', routines=routines)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'positive'): program.run()
        self.assertEqual(program.snapshot()['R'], .2)
        self.assertEqual([row['text'] for row in program.write_requests], ['before'])
        self.assertEqual(program._state.local_frames, [])
        self.assertEqual(program._state.call_depth, 0)

    def test_host_callback_error_restores_numeric_policy(self):
        program, _ = compile_program("r=0.1 WRITE('probe')")
        def write(text):
            raise ValueError('host failure')
        program = type(program)(write=write)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'host failure'): program.run()
        self.assertEqual(program.snapshot()['R'], .1)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'rounding'): rt.real(.1)

    def test_nested_generated_programs_restore_outer_policy(self):
        strict, _ = compile_program('r=1.0/3.0', translator=legacy_translate)
        outer, _ = compile_program("WRITE('probe') r=0.1")
        calls = []
        def write(text):
            with self.assertRaisesRegex(rt.KarelRuntimeError, 'rounding'): strict.run()
            calls.append(text)
        outer = type(outer)(write=write)
        self.assertEqual(outer.run()['R'], .1)
        self.assertEqual(calls, ['probe'])

    def test_parallel_programs_do_not_share_mode(self):
        def worker(index):
            if index % 2:
                program, _ = compile_program('r=1.0/3.0', translator=legacy_translate)
                with self.assertRaises(rt.KarelRuntimeError): program.run()
                return True
            return execute('r=1.0/3.0')['R'] == 1/3
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertTrue(all(pool.map(worker, range(24))))

    def test_report_context_and_generated_mode(self):
        program, result = compile_program('r=SIN(0.1) s=ATAN2(0.1,0.2)')
        self.assertEqual(program.translation_mode, 'pythonic')
        self.assertEqual(result.report['numeric_policy']['real_model'], 'python_float')
        self.assertEqual(result.report['translation_context']['mode'], 'pythonic')
        context = json.dumps(result.report['translation_context'], sort_keys=True, separators=(',', ':')).encode('ascii')
        self.assertEqual(result.report['translation_context_sha256'], hashlib.sha256(context).hexdigest())
        self.assertFalse(result.report['trig_uses'][0]['runtime_exact_subset_guard'])
        self.assertFalse(result.report['atan2_uses'][0]['runtime_exact_subset_guard'])
        self.assertNotIn('exact REAL literal', result.report['features'])

    def test_strict_is_explicitly_reserved(self):
        with self.assertRaises(TranslationError) as caught:
            translate('PROGRAM T BEGIN END T', mode='strict')
        self.assertEqual(caught.exception.code, 'E_MODE')
        self.assertIn('future milestone', caught.exception.message)

    def test_invalid_modes_are_rejected(self):
        for mode in (None, True, '', 'python', 'STRICT', []):
            with self.subTest(mode=mode), self.assertRaises(TranslationError):
                translate('PROGRAM T BEGIN END T', mode=mode)


class PythonicCliTests(unittest.TestCase):
    def test_default_explicit_and_future_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.kl'
            source.write_text('PROGRAM T VAR r: REAL BEGIN r=0.1+SQRT(2) END T', encoding='utf-8')
            for mode in (None, 'pythonic', 'strict', 'unknown'):
                with self.subTest(mode=mode):
                    report = root / 'result.json'
                    output = root / 'converted.py'
                    args = [sys.executable, '-m', 'karel2py', str(source), '-o', str(output),
                            '--report', str(report), '--force']
                    if mode is not None: args.extend(['--mode', mode])
                    output.unlink(missing_ok=True)
                    process = subprocess.run(args, capture_output=True, text=True)
                    data = json.loads(report.read_text(encoding='utf-8'))
                    self.assertEqual(data['translation_context']['mode'], mode or 'pythonic')
                    if mode in (None, 'pythonic'):
                        self.assertEqual(process.returncode, 0, process.stderr)
                        executed = subprocess.run([sys.executable, '-c',
                                                   'import runpy,sys; runpy.run_path(sys.argv[1],run_name="__main__")',
                                                   str(output)], capture_output=True, text=True)
                        self.assertEqual(executed.returncode, 0, executed.stderr)
                        self.assertIn(str(.1+math.sqrt(2)), executed.stdout)
                    else:
                        self.assertEqual(process.returncode, 2)
                        self.assertEqual(data['diagnostics'][0]['code'], 'E_MODE')
                        self.assertFalse(output.exists())
