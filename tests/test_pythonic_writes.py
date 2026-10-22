"""Pythonic mixed text output, scalar formatting and single-request effects."""
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError


def compile_program(body, *, declarations='x: INTEGER r: REAL text: STRING[16]',
                    prefix='', routines='', write=None):
    source = f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result = translate(source, filename='pythonic_writes.kl')
    namespace = {'__name__': 'pythonic_output_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](write=write), result


def output(body, **kwargs):
    program, _ = compile_program(body, **kwargs)
    program.run()
    return [row['text'] for row in program.write_requests]


class PythonicWriteRenderingTests(unittest.TestCase):
    def test_mixed_items_create_one_request(self):
        self.assertEqual(output("WRITE('count=',-42,', value=',1.234::0::2,CR,ON)"),
                         ['count= -42, value= 1.23\n TRUE'])

    def test_default_real_scientific_notation(self):
        for value in (0.1, -1.0, 123.456789, 1e100, 1e-100, -0.0):
            with self.subTest(value=value):
                self.assertEqual(output(f'WRITE({value})'), [' '+format(value, '.5E')])

    def test_real_fixed_precision_and_width(self):
        self.assertEqual(output('WRITE(123.456::9::2)'), ['   123.46'])
        self.assertEqual(output('WRITE(2.5::0::0)'), [' 2'])
        self.assertEqual(output('WRITE(2.675::0::2)'), [' 2.67'])

    def test_real_negative_precision_selects_scientific(self):
        self.assertEqual(output('WRITE(123.0::12::-3)'), ['   1.230E+02'])
        self.assertEqual(output('WRITE(0.1::0::-6)'), [' 1.000000E-01'])

    def test_real_width_never_truncates_digits(self):
        self.assertEqual(output('WRITE(-123.456::1::2)'), [' -123.46'])

    def test_real_precision_resource_boundary(self):
        self.assertEqual(output('WRITE(1.25::0::250)'), [' '+format(1.25, '.250f')])

    def test_real_nan_and_infinity_rejected_before_request(self):
        for value in (math.nan, math.inf, -math.inf):
            program, _ = compile_program('WRITE(r)')
            program._state.values['R'] = value
            with self.assertRaises(rt.KarelRuntimeError): program.run()
            self.assertEqual(program.write_requests, ())

    def test_signed_integer_boundaries(self):
        for expression, expected in [('MININT', ' -2147483648'), ('MAXINT', ' 2147483647'),
                                     ('-5', ' -5'), ('0', ' 0')]:
            self.assertEqual(output(f'WRITE({expression})'), [expected])

    def test_decimal_integer_width(self):
        self.assertEqual(output('WRITE(123::6,-123::2)'), ['   123 -123'])

    def test_integer_base_zero_and_ten(self):
        self.assertEqual(output('WRITE(-42::0::0,-42::0::10)'), [' -42 -42'])

    def test_integer_nondecimal_zero_fill(self):
        self.assertEqual(output('WRITE(5::6::2,42::6::16)'), [' 00101 0002A'])

    def test_integer_nondecimal_negative_uses_minus(self):
        self.assertEqual(output('WRITE(-42::0::16,MININT::0::2)'),
                         [' -2A -10000000000000000000000000000000'])

    def test_integer_base_digits_roundtrip(self):
        for base in range(2, 17):
            text = output(f'WRITE(-123456::0::{base})')[0]
            self.assertEqual(int(text.strip(), base), -123456)
            self.assertEqual(text, text.upper())

    def test_boolean_width(self):
        self.assertEqual(output('WRITE(ON::8,OFF::2,ON::0)'), ['    TRUE FALSE TRUE'])

    def test_narrow_values_support_integer_formatting(self):
        self.assertEqual(output('b[1]=255 s[1]=-12 WRITE(b[1]::0::16,s[1])',
                                declarations='b: ARRAY[1] OF BYTE s: ARRAY[1] OF SHORT'), [' FF -12'])

    def test_unknown_byte_and_short_marker_reject(self):
        for declaration in ('BYTE', 'SHORT'):
            program, _ = compile_program('WRITE(a[1])', declarations=f'a: ARRAY[1] OF {declaration}')
            with self.assertRaises(rt.KarelRuntimeError): program.run()
            self.assertEqual(program.write_requests, ())

    def test_corrupt_narrow_storage_rejects(self):
        for kind, value in [('BYTE', 256), ('BYTE', -1), ('SHORT', 32768), ('SHORT', True)]:
            program, _ = compile_program('WRITE(a[1])', declarations=f'a: ARRAY[1] OF {kind}')
            program._state.values['A'].values[0] = value
            with self.assertRaises(rt.KarelRuntimeError): program.run()

    def test_cr_only_and_repeated_cr(self):
        self.assertEqual(output('WRITE(CR) WRITE(CR,CR)'), ['\n', '\n\n'])

    def test_no_automatic_newline(self):
        self.assertEqual(output("WRITE('a','b') WRITE('c')"), ['ab', 'c'])

    def test_empty_items_still_create_request(self):
        self.assertEqual(output("WRITE('','')"), [''])

    def test_string_formats_remain_available_in_lists(self):
        self.assertEqual(output("WRITE('ABC'::5::1,'D'::3::0,'E'::5::2)"),
                         ["  ABCD   'E' "])

    def test_multiline_items(self):
        self.assertEqual(output("WRITE(\n'answer=',\n42,\nCR\n)"), ['answer= 42\n'])

    def test_physical_continuations(self):
        self.assertEqual(output("WRITE('answer=', &\n42,CR)"), ['answer= 42\n'])

    def test_field_and_using_resolution(self):
        self.assertEqual(output('p.value=0.1 USING p DO WRITE(value::0::2) ENDUSING',
                                declarations='p: packet_t', prefix='TYPE packet_t=STRUCTURE value: REAL ENDSTRUCTURE'),
                         [' 0.10'])

    def test_builtin_results(self):
        self.assertEqual(output("WRITE('root=',SQRT(2)::0::4)"), ['root= 1.4142'])

    def test_total_length_boundary(self):
        self.assertEqual(output("WRITE('"+'a'*253+"',CR)"), ['a'*253+'\n'])

    def test_oversize_combined_output_does_not_reach_sink(self):
        observed = []
        program, _ = compile_program("WRITE('"+'a'*254+"',CR)", write=observed.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'combined output'): program.run()
        self.assertEqual((program.write_requests, observed), ((), []))

    def test_maximum_empty_item_count_is_bounded(self):
        self.assertEqual(output('WRITE('+','.join(["''"]*1024)+')'), [''])


class PythonicWriteEffectsTests(unittest.TestCase):
    def test_multiple_routine_values_evaluated_left_to_right_once(self):
        routine = 'ROUTINE next_value: INTEGER BEGIN x=x+1 RETURN x END next_value'
        program, _ = compile_program('x=0 WRITE(next_value(),next_value(),next_value())', routines=routine)
        self.assertEqual(program.run()['X'], 3)
        self.assertEqual([row['text'] for row in program.write_requests], [' 1 2 3'])

    def test_nested_output_precedes_single_outer_request(self):
        observed = []
        routine = "ROUTINE next_value: INTEGER BEGIN x=x+1 WRITE('inner=',x,CR) RETURN x END next_value"
        program, _ = compile_program("x=0 WRITE('outer=',next_value(),next_value(),CR)",
                                     routines=routine, write=observed.append)
        program.run()
        self.assertEqual(observed, ['inner= 1\n', 'inner= 2\n', 'outer= 1 2\n'])

    def test_earlier_item_is_rendered_before_later_mutation(self):
        routine = "ROUTINE change: INTEGER BEGIN text='new' RETURN 7 END change"
        program, _ = compile_program("text='old' WRITE(text,change())", routines=routine)
        self.assertEqual(program.run()['TEXT'], 'new')
        self.assertEqual(program.write_requests[0]['text'], 'old 7')

    def test_late_error_preserves_earlier_effects_without_outer_request(self):
        routine = "ROUTINE change: INTEGER BEGIN x=x+1 WRITE('inner') RETURN x END change"
        program, _ = compile_program('x=0 WRITE(change(),r)', routines=routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['X'], 1)
        self.assertEqual([row['text'] for row in program.write_requests], ['inner'])
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_item_format_failure_prevents_later_expression(self):
        routine = 'ROUTINE change: INTEGER BEGIN x=x+1 RETURN x END change'
        program, _ = compile_program('x=0 WRITE(r,change())', routines=routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['X'], 0)
        self.assertEqual(program.write_requests, ())

    def test_combined_limit_checked_after_item_effects(self):
        routine = 'ROUTINE change: INTEGER BEGIN x=x+1 RETURN x END change'
        program, _ = compile_program("x=0 WRITE('"+'a'*254+"',change())", routines=routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['X'], 1)
        self.assertEqual(program.write_requests, ())

    def test_callback_receives_complete_statement_once(self):
        observed = []
        program, _ = compile_program("WRITE('a',-42,CR,0.1::0::1)", write=observed.append)
        program.run()
        self.assertEqual(observed, ['a -42\n 0.1'])
        self.assertEqual(program.write_requests[0]['adapter_outcome'], 'callback_completed')

    def test_callback_failure_unwinds_and_keeps_complete_request(self):
        observed = []
        def write(text):
            observed.append(text)
            raise OSError('sink failed')
        program, _ = compile_program('emit', routines="ROUTINE emit BEGIN WRITE('value=',-42,CR) END emit", write=write)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'sink failed'): program.run()
        self.assertEqual(observed, ['value= -42\n'])
        self.assertEqual(program.write_requests[0]['adapter_outcome'], 'callback_failed')
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_callback_interruption_is_not_retried(self):
        def write(text): raise KeyboardInterrupt()
        program, _ = compile_program('WRITE(1,CR)', write=write)
        with self.assertRaises(KeyboardInterrupt): program.run()
        self.assertEqual(len(program.write_requests), 1)
        self.assertEqual(program.write_requests[0]['adapter_outcome'], 'callback_interrupted')

    def test_callback_result_contract_remains(self):
        program, _ = compile_program('WRITE(1,CR)', write=lambda text: len(text))
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'return None'): program.run()
        self.assertEqual(program.write_requests[0]['adapter_outcome'], 'callback_result_rejected')

    def test_output_effect_propagates_through_calls(self):
        routines = "ROUTINE emit BEGIN WRITE(0.1,CR) END emit\nROUTINE outer BEGIN emit END outer"
        program, result = compile_program('outer', routines=routines)
        self.assertTrue(result.report['routine_effects']['OUTER']['potential_output_requests'])
        self.assertEqual(program.run()['X'], {'uninitialized': True})

    def test_output_functions_in_operator_run_once_in_order(self):
        routine = "ROUTINE emit: INTEGER BEGIN WRITE(1,CR) RETURN 1 END emit"
        program, _ = compile_program('x=emit()+emit()', routines=routine)
        self.assertEqual(program.run()['X'], 2)
        self.assertEqual([row['text'] for row in program.write_requests], [' 1\n', ' 1\n'])

    def test_newline_output_during_local_loop(self):
        routine = 'ROUTINE emit VAR i: INTEGER BEGIN FOR i=1 TO 2 DO WRITE(i,CR) ENDFOR END emit'
        self.assertEqual(output('emit', routines=routine), [' 1\n', ' 2\n'])


class PythonicWriteValidationTests(unittest.TestCase):
    def reject(self, body, code, **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_unsupported_output_types_remain_explicit(self):
        for spec in ('ARRAY[1] OF INTEGER', 'VECTOR', 'JOINTPOS3'):
            self.reject('WRITE(value)', 'E_TYPE', declarations=f'value: {spec}')

    def test_empty_and_trailing_items(self):
        for body in ('WRITE()', 'WRITE(1,)', 'WRITE(,1)'):
            self.reject(body, 'E_WRITE_ITEM')

    def test_explicit_device_remains_blocked(self):
        self.reject('WRITE OUTPUT(1,CR)', 'E_SYMBOL')

    def test_extra_formats_remain_blocked(self):
        self.reject('WRITE(1::2::10::3)', 'E_WRITE_FORMAT')

    def test_type_specific_format_ranges(self):
        for body in ('WRITE(1::0::1)', 'WRITE(1::0::17)', 'WRITE(1::255)',
                     'WRITE(ON::8::1)', 'WRITE(0.1::0::255)', 'WRITE(0.1::0::-255)',
                     "WRITE('x'::8::-1)", 'WRITE(1::-1)', 'WRITE(CR::8)'):
            self.reject(body, 'E_WRITE_FORMAT')

    def test_single_colon_still_rejected(self):
        self.reject("WRITE('x':2)", 'E_WRITE_ITEM')

    def test_item_count_limit(self):
        self.reject('WRITE('+','.join(["''"]*1025)+')', 'E_WRITE_ITEMS')

    def test_format_failure_preserves_physical_location(self):
        error = self.reject("WRITE(\n 'x',\n 1::8::1\n)", 'E_WRITE_FORMAT')
        self.assertEqual((error.token.line, error.token.column), (8, 8))

    def test_report_lists_items_and_chosen_policy(self):
        _, result = compile_program("WRITE('x=',0.1::8::2,CR)")
        site = result.report['writes'][0]
        self.assertEqual(site['data_items'], 3)
        self.assertEqual([item['data_type'] for item in site['items']], ['STRING', 'REAL', 'CR'])
        self.assertEqual(site['items'][1]['format_specifiers'], [8, 2])
        self.assertIn('Left to right', site['evaluated'])
        self.assertIn('LF', result.report['write_policy']['newline'])
        self.assertFalse(result.report['write_policy']['controller_validated'])

    def test_runtime_piece_validation(self):
        state = rt.State({}, {})
        for pieces in ([], '', [1], ['nonascii\u00e9'], ['x'*255]):
            with self.subTest(pieces=pieces), self.assertRaises(rt.KarelRuntimeError):
                state.write_items(pieces, line=7)
        self.assertEqual(state.write_requests, [])

    def test_cli_generates_runnable_mixed_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'input.kl'
            source.write_text("PROGRAM T BEGIN WRITE('x=',0.1::0::2,CR) END T", encoding='utf-8')
            process = subprocess.run([sys.executable, '-m', 'karel2py', str(source), '-o', str(root/'converted.py'),
                                      '--report', str(root/'result.json')], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            report = json.loads((root/'result.json').read_text(encoding='utf-8'))
            self.assertEqual(report['writes'][0]['data_items'], 3)
            namespace = {'__name__': 'cli_output_test'}
            exec((root/'converted.py').read_text(encoding='utf-8'), namespace)
            observed = []
            namespace['Program'](write=observed.append).run()
            self.assertEqual(observed, ['x= 0.10\n'])
