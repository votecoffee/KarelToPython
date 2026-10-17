"""Supported decimal text and fail-closed INTEGER WRITE spacing boundaries."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError

ROOT = Path(__file__).resolve().parents[1]


def compile_program(body, *, declarations='x: INTEGER', prefix='', routines='', write=None, sleep=None):
    source = f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result = translate(source, filename='integer_writes.kl')
    namespace = {'__name__': 'integer_write_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](write=write, sleep=sleep), result


def texts(program): return [row['text'] for row in program.write_requests]


class IntegerWriteBehaviorTests(unittest.TestCase):
    def assert_output(self, expression, expected, **kwargs):
        program, _ = compile_program(f'WRITE({expression})', **kwargs)
        program.run()
        self.assertEqual(texts(program), [expected])
    def test_manual_positive_example(self): self.assert_output('123', ' 123')
    def test_zero(self): self.assert_output('0', ' 0')
    def test_maximum_expression(self): self.assert_output('MAXINT', ' 2147483647')
    def test_largest_storable_value(self): self.assert_output('MAXINT-1', ' 2147483646')
    def test_grouped_expression(self): self.assert_output('(3+4)', ' 7')
    def test_negative_operand_with_positive_result(self): self.assert_output('-5+10', ' 5')
    def test_abs_minimum_overflow_before_request(self):
        program, _ = compile_program('WRITE(ABS(MININT))')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.write_requests, ())
    def test_bit_expression(self): self.assert_output('5 OR 2', ' 7')
    def test_real_to_integer_builtin(self): self.assert_output('TRUNC(2.5)', ' 2')
    def test_global_constant(self): self.assert_output('C', ' 123', prefix='CONST C=123')
    def test_local_constant(self):
        program, _ = compile_program('emit', routines='ROUTINE emit CONST C=42 BEGIN WRITE(C) END emit')
        program.run()
        self.assertEqual(texts(program), [' 42'])
    def test_source_variable_is_unchanged(self):
        program, _ = compile_program('x=123 WRITE(x)')
        self.assertEqual(program.run()['X'], 123)
        self.assertEqual(texts(program), [' 123'])
    def test_scalar_reference(self):
        program, _ = compile_program('x=7 emit(x)', routines='ROUTINE emit(p: INTEGER) BEGIN WRITE(p) END emit')
        self.assertEqual(program.run()['X'], 7)
        self.assertEqual(texts(program), [' 7'])
    def test_scalar_value(self):
        program, _ = compile_program('emit(42)', routines='ROUTINE emit(p: INTEGER) BEGIN WRITE(p) END emit')
        program.run()
        self.assertEqual(texts(program), [' 42'])
    def test_structure_field(self):
        program, _ = compile_program('p.count=42 WRITE(p.count)', declarations='p: packet_t', prefix='TYPE packet_t=STRUCTURE count: INTEGER ENDSTRUCTURE')
        self.assertEqual(program.run()['P']['COUNT'], 42)
        self.assertEqual(texts(program), [' 42'])
    def test_using_field(self):
        program, _ = compile_program('p.count=42 USING p DO WRITE(count) ENDUSING', declarations='p: packet_t', prefix='TYPE packet_t=STRUCTURE count: INTEGER ENDSTRUCTURE')
        program.run()
        self.assertEqual(texts(program), [' 42'])
    def test_multidimensional_element(self):
        program, _ = compile_program('values[2,1]=12 WRITE(values[2,1])', declarations='values: ARRAY[2,2] OF INTEGER')
        program.run()
        self.assertEqual(texts(program), [' 12'])
    def test_named_subarray_element(self):
        program, _ = compile_program('values[1,2]=8 WRITE(values[1,2])', prefix='TYPE row_t=ARRAY[2] OF INTEGER', declarations='values: ARRAY[2] OF row_t')
        program.run()
        self.assertEqual(texts(program), [' 8'])
    def test_function_evaluated_once(self):
        program, _ = compile_program('x=0 WRITE(next_value())', routines='ROUTINE next_value: INTEGER BEGIN x=x+1 RETURN x END next_value')
        self.assertEqual(program.run()['X'], 1)
        self.assertEqual(texts(program), [' 1'])
    def test_nested_output_before_outer_request(self):
        program, _ = compile_program('WRITE(next_value())', routines='ROUTINE next_value: INTEGER BEGIN WRITE(0) RETURN 123 END next_value')
        program.run()
        self.assertEqual(texts(program), [' 0', ' 123'])
    def test_delay_before_request(self):
        observed = []
        program, _ = compile_program('WRITE(next_value())', routines='ROUTINE next_value: INTEGER BEGIN DELAY 1 RETURN 7 END next_value', sleep=lambda value: observed.append(('sleep', value)), write=lambda value: observed.append(('write', value)))
        program.run()
        self.assertEqual(observed, [('sleep', 0.001), ('write', ' 7')])
    def test_mixed_types_keep_request_order(self):
        observed = []
        program, _ = compile_program("WRITE('count') WRITE(123) WRITE(ON)", write=observed.append)
        with patch('sys.stdout.write', side_effect=AssertionError('unexpected stdout')): program.run()
        self.assertEqual(observed, ['count', ' 123', ' TRUE'])
        self.assertTrue(all(row['adapter_outcome'] == 'callback_completed' for row in program.write_requests))
    def test_negative_skipped_path_does_not_fail(self):
        program, _ = compile_program('IF OFF THEN WRITE(-5) ENDIF SELECT 1 OF CASE(1): WRITE(123) ELSE: WRITE(-1) ENDSELECT')
        program.run()
        self.assertEqual(texts(program), [' 123'])
    def test_labels_skip_negative_request(self):
        program, _ = compile_program('GO TO chosen WRITE(-5) chosen:: WRITE(0)')
        program.run()
        self.assertEqual(texts(program), [' 0'])
    def test_continuation_source_location(self):
        program, result = compile_program('WRITE( &\n 123)')
        program.run()
        self.assertEqual(texts(program), [' 123'])
        self.assertEqual(program.write_requests[0]['line'], result.report['writes'][0]['line'])
        self.assertEqual(len(result.report['continuations']), 1)
    def test_reports_domain_and_types(self):
        _, result = compile_program("WRITE(123) WRITE(ON) WRITE('text')")
        self.assertEqual([site['data_type'] for site in result.report['writes']], ['INTEGER', 'BOOLEAN', 'STRING'])
        site = result.report['writes'][0]
        self.assertEqual((site['data_items'], site['format_specifiers'], site['format_width'], site['width_policy']), (1, [], None, 'unformatted'))
        self.assertIn('nonnegative', site['evaluated'])
        self.assertIn('negative INTEGER values fail before request', result.report['write_policy']['integer'])
        self.assertFalse(result.report['write_policy']['controller_validated'])
    def test_transitive_effects(self):
        program, result = compile_program('forward(7)', routines='ROUTINE emit(p: INTEGER) BEGIN WRITE(p) END emit\nROUTINE forward(p: INTEGER) BEGIN emit(p) END forward')
        program.run()
        self.assertEqual(texts(program), [' 7'])
        for name in ('EMIT', 'FORWARD'):
            self.assertTrue(result.report['routine_effects'][name]['potential_output_requests'])
            self.assertEqual(result.report['routine_effects'][name]['potential_parameter_writes'], [])
    def test_trace_copy_and_valid_run_reset(self):
        program, _ = compile_program('WRITE(123)')
        program.run()
        program.write_requests[0]['text'] = 'changed'
        self.assertEqual(texts(program), [' 123'])
        program.run()
        self.assertEqual(texts(program), [' 123'])
    def test_generated_example(self):
        result = translate((ROOT / 'examples/integer_write_requests.kl').read_text())
        namespace = {'__name__': 'integer_example_test'}
        exec(result.python_source, namespace)
        program = namespace['Program']()
        self.assertEqual(program.run(), dict(COUNT=123, PACKET=dict(COUNT=42, READY=True), NUMBERS=[0, 7, 2147483646], CHECKS=5, COUNTER_CLEARED=True))
        self.assertEqual(texts(program), ['start', ' 123', ' 42', ' 0', ' 2', ' 42', ' TRUE', ' 0', ' 7', ' 2147483646', ' 5', ' TRUE', 'done'])


class IntegerWriteGuardTests(unittest.TestCase):
    def reject(self, body, code='E_WRITE_FORMAT', **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, **kwargs)
        self.assertEqual(caught.exception.code, code)
    def test_width_remains_blocked(self): self.reject('WRITE(123::6)')
    def test_width_fallback_remains_blocked(self): self.reject('WRITE(123::0)')
    def test_decimal_base_remains_blocked(self): self.reject('WRITE(123::6::10)')
    def test_other_bases_remain_blocked(self):
        for base in (0, 1, 2, 3, 8, 16):
            with self.subTest(base=base): self.reject(f'WRITE(5::6::{base})')
    def test_string_modes_not_applied_to_integer(self):
        with self.assertRaises(TranslationError) as caught: compile_program('WRITE(123::0::2)')
        self.assertIn('INTEGER WRITE', caught.exception.message)
        self.assertNotIn('Quoted', caught.exception.message)
    def test_continued_width_error_position(self):
        with self.assertRaises(TranslationError) as caught: compile_program('WRITE(123 &\n ::8)')
        self.assertEqual((caught.exception.code, caught.exception.token.line, caught.exception.token.column), ('E_WRITE_FORMAT', 7, 4))
    def test_multiple_items_remain_blocked(self): self.reject('WRITE(1,2)', 'E_WRITE_ITEM')
    def test_cr_remains_blocked(self): self.reject('WRITE(1,CR)', 'E_WRITE_ITEM')
    def test_explicit_device_remains_blocked(self): self.reject('WRITE OUTPUT(123)', 'E_WRITE_TARGET')
    def test_real_output_remains_blocked(self): self.reject('WRITE(1.5)', 'E_TYPE')
    def test_narrow_storage_write_remains_blocked(self):
        for kind in ('BYTE', 'SHORT'):
            with self.subTest(kind=kind): self.reject('x=7 WRITE(x)', 'E_TYPE', declarations=f'x: {kind}')
    def test_whole_integer_array_remains_blocked(self): self.reject('WRITE(values)', 'E_TYPE', declarations='values: ARRAY[2] OF INTEGER')
    def test_operator_order_guard(self): self.reject('x=f()+1', 'E_EVALUATION_ORDER', routines='ROUTINE f: INTEGER BEGIN WRITE(123) RETURN 1 END f')
    def test_indexed_target_order_guard(self): self.reject('values[1]=f()', 'E_EVALUATION_ORDER', declarations='values: ARRAY[2] OF INTEGER', routines='ROUTINE f: INTEGER BEGIN WRITE(123) RETURN 1 END f')
    def test_uninitialized_fails_before_sink(self):
        observed = []
        program, _ = compile_program('WRITE(x)', write=observed.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual((texts(program), observed), ([], []))
    def test_uninitialized_element_fails_before_request(self):
        program, _ = compile_program('WRITE(values[1])', declarations='values: ARRAY[2] OF INTEGER')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.write_requests, ())
    def test_bounds_fail_before_request(self):
        program, _ = compile_program('WRITE(values[3])', declarations='values: ARRAY[2] OF INTEGER')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.write_requests, ())
    def test_all_negative_boundaries_fail_before_sink(self):
        for expression in ('-1', '-5', '-123', 'MININT'):
            with self.subTest(expression=expression):
                observed = []
                program, _ = compile_program(f'WRITE({expression})', write=observed.append)
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'Negative INTEGER WRITE'): program.run()
                self.assertEqual((texts(program), observed), ([], []))
    def test_negative_result_keeps_prior_expression_effects(self):
        program, _ = compile_program('x=0 WRITE(f())', routines='ROUTINE f: INTEGER BEGIN x=x+1 WRITE(0) RETURN -5 END f')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'Negative INTEGER WRITE'): program.run()
        self.assertEqual((program._state.values['X'], texts(program)), (1, [' 0']))
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))
    def test_runtime_strict_integer_and_range(self):
        state = rt.State({}, {})
        for value in (False, True, 1.0, '123', None, [], {}, object(), rt.UNINITIALIZED, rt.UNKNOWN_BYTE, -2147483649, 2147483648):
            with self.subTest(value=value), self.assertRaises(rt.KarelRuntimeError): state.write_integer(value, 17)
        self.assertEqual(state.write_requests, [])
    def test_runtime_negative_guard_has_line(self):
        state = rt.State({}, {})
        with self.assertRaises(rt.KarelRuntimeError) as caught: state.write_integer(-5, 17)
        self.assertEqual(caught.exception.line, 17)
        self.assertEqual(state.write_requests, [])
    def test_callback_failure_keeps_text_and_unwinds(self):
        observed = []
        def fail(value): observed.append(value); raise OSError('sink failed')
        program, result = compile_program('emit(123)', routines='ROUTINE emit(p: INTEGER) BEGIN WRITE(p) END emit', write=fail)
        with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertEqual(caught.exception.line, result.report['writes'][0]['line'])
        self.assertEqual((texts(program), observed), ([' 123'], [' 123']))
        self.assertEqual(program.write_requests[0]['adapter_outcome'], 'callback_failed')
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))
    def test_non_none_callback_results_rejected(self):
        for returned in (False, 0, 'ok'):
            with self.subTest(returned=returned):
                program, _ = compile_program('WRITE(123)', write=lambda value: returned)
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'return None'): program.run()
                self.assertEqual(texts(program), [' 123'])
                self.assertEqual(program.write_requests[0]['adapter_outcome'], 'callback_result_rejected')
    def test_callback_interruption_unwinds(self):
        def interrupt(value): raise KeyboardInterrupt()
        program, _ = compile_program('emit(0)', routines='ROUTINE emit(p: INTEGER) BEGIN WRITE(p) END emit', write=interrupt)
        with self.assertRaises(KeyboardInterrupt): program.run()
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))
        self.assertEqual(program.write_requests[0]['adapter_outcome'], 'callback_interrupted')


class IntegerWriteCLITests(unittest.TestCase):
    def test_cli_generates_supported_requests(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            source = target / 'source.kl'
            source.write_text('PROGRAM T\nBEGIN WRITE(0) WRITE(123) END T')
            process = subprocess.run([sys.executable, '-m', 'karel2py', str(source), '-o', str(target / 'converted.py'), '--report', str(target / 'report.json')], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual([site['data_type'] for site in json.loads((target / 'report.json').read_text())['writes']], ['INTEGER', 'INTEGER'])
            namespace = {'__name__': 'integer_cli_test'}
            exec((target / 'converted.py').read_text(), namespace)
            program = namespace['Program']()
            program.run()
            self.assertEqual(texts(program), [' 0', ' 123'])
    def test_cli_rejects_integer_format_without_module(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            source = target / 'source.kl'
            source.write_text('PROGRAM T\nBEGIN WRITE(123::6) END T')
            process = subprocess.run([sys.executable, '-m', 'karel2py', str(source), '-o', str(target / 'converted.py'), '--report', str(target / 'report.json')], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(process.returncode, 2, process.stderr)
            self.assertFalse((target / 'converted.py').exists())
            self.assertEqual(json.loads((target / 'report.json').read_text())['diagnostics'][0]['code'], 'E_WRITE_FORMAT')


if __name__ == '__main__': unittest.main()
