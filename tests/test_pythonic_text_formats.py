"""Practical text formats, ordered dynamic arguments and retained bounds."""
import json
import math
from pathlib import Path
import unittest

from karel2py import runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_pythonic_writes import compile_program, output


class DynamicWriteFormatTests(unittest.TestCase):
    def test_variable_width(self):
        self.assertEqual(output('x=6 WRITE(42::x)'), ['    42'])

    def test_grouped_literal_and_arithmetic(self):
        self.assertEqual(output('WRITE(42::(3+3),42::2+1)'), ['    42 42'])

    def test_global_constant_and_expression(self):
        self.assertEqual(output('WRITE(42::W+1)', prefix='CONST W=5'), ['    42'])

    def test_dynamic_base(self):
        self.assertEqual(output('x=16 WRITE(-42::8::x)'), [' -00002A'])

    def test_both_formats_dynamic(self):
        self.assertEqual(output('x=5 WRITE(5::x+1::x-3)'), [' 00101'])

    def test_dynamic_scientific_precision(self):
        self.assertEqual(output('x=3 WRITE(123.0::x+9::-x)'), ['   1.230E+02'])

    def test_dynamic_boolean_width(self):
        self.assertEqual(output('x=8 WRITE(ON::x)'), ['    TRUE'])

    def test_string_width_and_alignment(self):
        self.assertEqual(output("x=1 WRITE('ABC'::x+4::x)"), ['  ABC'])

    def test_narrow_storage_is_promoted(self):
        self.assertEqual(output('b[1]=6 WRITE(42::b[1])',
                                declarations='b: ARRAY[1] OF BYTE'), ['    42'])

    def test_using_field_resolution(self):
        self.assertEqual(output('p.width=6 USING p DO WRITE(42::width) ENDUSING',
                                prefix='TYPE packet=STRUCTURE width: INTEGER ENDSTRUCTURE',
                                declarations='p: packet'), ['    42'])

    def test_routine_parameter_and_local_constant(self):
        routines = 'ROUTINE emit(w: INTEGER) CONST BASE=16 BEGIN WRITE(42::w::BASE) END emit'
        self.assertEqual(output('emit(6)', routines=routines), [' 0002A'])

    def test_bare_function_format(self):
        self.assertEqual(output('WRITE(42::width)',
                                routines='ROUTINE width: INTEGER BEGIN RETURN 6 END width'), ['    42'])

    def test_multiline_and_continuation(self):
        self.assertEqual(output('x=5 WRITE(\n42:: &\nx+1,\nCR\n)'), ['    42\n'])

    def test_dynamic_report_is_json_serializable(self):
        _, result = compile_program('x=6 WRITE(42::x::16)')
        site = json.loads(json.dumps(result.report))['writes'][0]
        self.assertEqual(site['format_width'], dict(expression=True, line=6, column=15))
        self.assertEqual(site['format_specifiers'][1], 16)
        self.assertTrue(site['items'][0]['dynamic_formats'])
        self.assertEqual(site['width_policy'], 'dynamic')

    def test_dynamic_string_alignment_report(self):
        _, result = compile_program("x=2 WRITE('ABC'::8::x)")
        site = result.report['writes'][0]
        self.assertEqual((site['alignment'], site['quoted'], site['width_policy']),
                         ('dynamic', 'dynamic', 'dynamic'))

    def test_literal_metadata_retained(self):
        _, result = compile_program('WRITE(123.0::(+12)::(-3))')
        self.assertEqual(result.report['writes'][0]['format_specifiers'], [12, -3])

    def test_noninteger_formats_rejected(self):
        for expression in ('1.0', 'ON', "'x'", 'r'):
            for statement in (f'WRITE(42::{expression})', f'WRITE(42::0::{expression})'):
                with self.subTest(statement=statement), self.assertRaises(TranslationError) as caught:
                    compile_program(statement)
                self.assertEqual(caught.exception.code, 'E_TYPE')

    def test_boolean_second_expression_rejected(self):
        with self.assertRaises(TranslationError) as caught: compile_program('WRITE(ON::6::x)')
        self.assertEqual(caught.exception.code, 'E_WRITE_FORMAT')

    def test_dynamic_ranges_checked_before_request(self):
        for value, statement in [(-1, 'WRITE(42::x)'), (255, 'WRITE(42::x)'),
                                 (1, 'WRITE(42::0::x)'), (17, 'WRITE(42::0::x)'),
                                 (4, "WRITE('a'::8::x)"), (-1, "WRITE('a'::x)"),
                                 (-255, 'WRITE(1.0::0::x)'), (255, 'WRITE(1.0::0::x)')]:
            program, _ = compile_program(f'x={value} {statement}')
            with self.subTest(value=value, statement=statement), self.assertRaises(rt.KarelRuntimeError): program.run()
            self.assertEqual(program.write_requests, ())

    def test_grouped_invalid_literal_still_rejected_at_translation(self):
        with self.assertRaises(TranslationError) as caught: compile_program('WRITE(42::(255))')
        self.assertEqual(caught.exception.code, 'E_WRITE_FORMAT')

    def test_oversized_format_token_has_source_diagnostic(self):
        for expression in ('9'*10000, '('+'9'*10000+')'):
            with self.assertRaises(TranslationError) as caught: compile_program('WRITE(42::'+expression+')')
            self.assertEqual(caught.exception.code, 'E_LITERAL')

    def test_leading_zero_format_literal_is_bounded_by_value(self):
        self.assertEqual(output('WRITE(42::'+'0'*10000+'6)'), ['    42'])

    def test_reserved_integer_and_nonfinite_formats_reject(self):
        for value in (True, math.inf, math.nan, 2147483648):
            program, _ = compile_program('WRITE(42::x)')
            program._state.values['X'] = value
            with self.subTest(value=value), self.assertRaises(rt.KarelRuntimeError): program.run()
            self.assertEqual(program.write_requests, ())


class DynamicFormatEffectTests(unittest.TestCase):
    def test_value_width_base_evaluated_once_in_source_order(self):
        routines = '''ROUTINE value: INTEGER BEGIN x=x*10+1 RETURN 42 END value
ROUTINE width: INTEGER BEGIN x=x*10+2 RETURN 8 END width
ROUTINE base: INTEGER BEGIN x=x*10+3 RETURN 16 END base'''
        program, _ = compile_program('x=0 WRITE(value()::width()::base())', routines=routines)
        self.assertEqual(program.run()['X'], 123)
        self.assertEqual(program.write_requests[0]['text'], ' 000002A')

    def test_string_value_captured_before_width_mutation(self):
        routine = "ROUTINE width: INTEGER BEGIN text='new' RETURN 6 END width"
        program, _ = compile_program("text='old' WRITE(text::width())", routines=routine)
        self.assertEqual(program.run()['TEXT'], 'new')
        self.assertEqual(program.write_requests[0]['text'], 'old   ')

    def test_nested_requests_from_formats_precede_outer(self):
        routines = "ROUTINE width: INTEGER BEGIN WRITE('width') RETURN 6 END width"
        self.assertEqual(output("WRITE('outer=',42::width(),CR)", routines=routines),
                         ['width', 'outer=    42\n'])

    def test_item_rendered_before_next_item(self):
        routine = 'ROUTINE width: INTEGER BEGIN x=x+1 RETURN 6 END width'
        program, _ = compile_program('x=0 WRITE(x::width(),x)', routines=routine)
        self.assertEqual(program.run()['X'], 1)
        self.assertEqual(program.write_requests[0]['text'], '     0 1')

    def test_format_expression_failure_skips_later_format_and_item(self):
        routine = 'ROUTINE change: INTEGER BEGIN x=x+1 RETURN 16 END change'
        program, _ = compile_program('x=0 WRITE(42::missing::change(),change())',
                                     declarations='x,missing: INTEGER', routines=routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['X'], 0)
        self.assertEqual(program.write_requests, ())

    def test_formats_evaluated_before_item_range_validation(self):
        routine = "ROUTINE base: INTEGER BEGIN x=x+1 WRITE('base') RETURN 16 END base"
        program, _ = compile_program('x=0 bad=255 WRITE(42::bad::base(),base())',
                                     declarations='x,bad: INTEGER', routines=routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['X'], 1)
        self.assertEqual([row['text'] for row in program.write_requests], ['base'])
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_abort_in_format_retains_prior_effects(self):
        routine = 'ROUTINE width: INTEGER BEGIN x=x+1 ABORT RETURN 6 END width'
        program, _ = compile_program('x=0 WRITE(42::width())', routines=routine)
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual(program.snapshot()['X'], 1)
        self.assertEqual(program.write_requests, ())
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_runtime_arithmetic_error_skips_later_item(self):
        routine = 'ROUTINE later: INTEGER BEGIN x=99 RETURN 1 END later'
        program, _ = compile_program('x=0 WRITE(42::(6 DIV x),later())', routines=routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['X'], 0)

    def test_format_callee_effects_propagate(self):
        routines = '''ROUTINE width: INTEGER BEGIN x=6 RETURN x END width
ROUTINE emit BEGIN WRITE(42::width()) END emit'''
        program, result = compile_program('emit', routines=routines)
        self.assertTrue(result.report['routine_effects']['EMIT']['potential_external_writes'])
        self.assertEqual(program.run()['X'], 6)

    def test_callback_failure_unwinds_format_callers_without_retry(self):
        observed = []
        def write(text):
            observed.append(text)
            raise OSError('failed sink')
        routines = 'ROUTINE width: INTEGER BEGIN x=x+1 RETURN 6 END width\nROUTINE emit BEGIN WRITE(42::width()) END emit'
        program, _ = compile_program('x=0 emit', routines=routines, write=write)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'failed sink'): program.run()
        self.assertEqual((program.snapshot()['X'], observed), (1, ['    42']))
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_step_limit_applies_to_format_functions(self):
        routine = 'ROUTINE width: INTEGER BEGIN WHILE ON DO x=x+1 ENDWHILE RETURN 6 END width'
        program, _ = compile_program('x=0 WRITE(42::width())', routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'step'): program.run(max_steps=12)
        self.assertGreater(program.snapshot()['X'], 0)
        self.assertEqual(program.write_requests, ())
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_format_call_preserves_for_counter_guards(self):
        routine = 'ROUTINE width: INTEGER BEGIN RETURN 6 END width'
        with self.assertRaises(TranslationError) as caught:
            compile_program('FOR x=1 TO 2 DO WRITE(42::width()) ENDFOR', routines=routine)
        self.assertEqual(caught.exception.code, 'E_FOR_COUNTER')

    def test_numeric_policy_restored_after_format_failure(self):
        program, _ = compile_program('x=255 WRITE(1.1::x)')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'rounding'): rt.real(0.1)

    def test_format_expression_nested_call_parameter_effects(self):
        routines = '''ROUTINE width(p: INTEGER): INTEGER BEGIN p=p+1 RETURN 6 END width
ROUTINE emit(p: INTEGER) BEGIN WRITE(42::width(p)) END emit'''
        program, result = compile_program('x=0 emit(x)', routines=routines)
        self.assertEqual(program.run()['X'], 1)
        self.assertEqual(result.report['routine_effects']['EMIT']['potential_parameter_writes'], ['P'])


class PythonicQuotedStringTests(unittest.TestCase):
    def test_embedded_apostrophe_is_doubled(self):
        self.assertEqual(output("WRITE('O''Brien'::11::2)"), [" 'O''Brien'"])

    def test_quoted_left_truncates_contents(self):
        self.assertEqual(output("WRITE('ABCDE'::6::2)"), [" 'ABC'"])

    def test_quoted_right_truncates_contents(self):
        self.assertEqual(output("WRITE('ABCDE'::6::3)"), [" 'ABC'"])

    def test_truncation_keeps_complete_escaped_apostrophe(self):
        self.assertEqual(output("WRITE(CHR(39)::4::2,CHR(39)::5::2)"), [" ''  ''''"])

    def test_truncation_does_not_skip_an_unfitting_character(self):
        self.assertEqual(output("WRITE((CHR(39)+'A')::4::3)"), ["  ''"])

    def test_padding_outside_quotes(self):
        self.assertEqual(output("WRITE('O''B'::10::2,'O''B'::10::3)"),
                         [" 'O''B'       'O''B'"])

    def test_tiny_width_preserves_wrapper(self):
        for width in (1, 2, 3):
            for alignment in (2, 3):
                with self.subTest(width=width, alignment=alignment):
                    self.assertEqual(output(f"WRITE('ABC'::{width}::{alignment})"), [" ''"])

    def test_quoted_width_fallback_is_natural_rendered_length(self):
        for width in (0, 255, 2147483647):
            for alignment in (2, 3):
                with self.subTest(width=width, alignment=alignment):
                    self.assertEqual(output(f"WRITE('O''B'::{width}::{alignment})"), [" 'O''B'"])

    def test_dynamic_quote_mode_and_width(self):
        self.assertEqual(output("x=2 WRITE('ABC'::x+x::x)"), [" 'A'"])

    def test_empty_quoted_fallback(self):
        self.assertEqual(output("WRITE(''::0::2,''::255::3)"), [" '' ''"])

    def test_controls_are_plain_contents(self):
        self.assertEqual(output('WRITE((CHR(13)+CHR(10))::5::2)'), [" '\r\n'"])

    def test_exact_total_output_boundary(self):
        self.assertEqual(output("text='"+'a'*125+"' WRITE((text+text)::0::2,CR)",
                                declarations='text: STRING[125]'), [" '"+'a'*250+"'\n"])

    def test_full_width_truncates_long_contents(self):
        self.assertEqual(output("text='"+'a'*127+"' WRITE((text+text)::254::2)",
                                declarations='text: STRING[127]'), [" '"+'a'*251+"'"])

    def test_large_escaped_natural_output_rejected_before_sink(self):
        observed = []
        program, _ = compile_program("text='"+"''"*127+"' WRITE((text+text)::0::2)",
                                     declarations='text: STRING[127]', write=observed.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'combined output'): program.run()
        self.assertEqual((program.write_requests, observed), ((), []))

    def test_nonascii_and_oversized_input_still_rejected(self):
        for value in ('\u00e9', 'a'*255):
            program, _ = compile_program('WRITE(text::4::2)')
            program._state.values['TEXT'] = value
            with self.subTest(value=value), self.assertRaises(rt.KarelRuntimeError): program.run()
            self.assertEqual(program.write_requests, ())

    def test_quote_rendering_does_not_modify_storage(self):
        program, _ = compile_program("text='O''Brien' WRITE(text::4::2)")
        self.assertEqual(program.run()['TEXT'], "O'Brien")
        self.assertEqual(program.write_requests[0]['text'], " 'O'")


class PythonicScientificConversionTests(unittest.TestCase):
    def conversion(self, value, precision=-3, width=1, capacity=64):
        program, result = compile_program(f'CNV_REAL_STR({value},{width},{precision},text)',
                                          declarations=f'text: STRING[{capacity}]')
        return program.run()['TEXT'], result

    def test_negative_precision_selects_scientific(self):
        self.assertEqual(self.conversion('123.0')[0], ' 1.230E+02')

    def test_scientific_minimum_width(self):
        self.assertEqual(self.conversion('123.0', width=14)[0], '     1.230E+02')

    def test_sign_zero_subnormal_and_exponent_bounds(self):
        for value in ('0.0', '-0.0', '-123.456', '5E-324', '1E308'):
            with self.subTest(value=value):
                self.assertEqual(self.conversion(value, -5)[0], ' '+format(float(value), '.5E'))

    def test_fixed_zero_precision_still_rounds(self):
        self.assertEqual(self.conversion('2.5', 0)[0], ' 2')

    def test_scientific_capacity_overflow_marker(self):
        for capacity in (1, 3, 8):
            with self.subTest(capacity=capacity):
                self.assertEqual(self.conversion('123.0', capacity=capacity)[0], ' '+'*'*(capacity-1))

    def test_exact_capacity_fit(self):
        self.assertEqual(self.conversion('123.0', capacity=10)[0], ' 1.230E+02')

    def test_maximum_scientific_precision_is_bounded(self):
        self.assertEqual(self.conversion('1.0', -254, capacity=254)[0], ' '+'*'*253)

    def test_invalid_precision_preserves_output(self):
        for precision in (-255, 255, -2147483648, 2147483647):
            spelling = 'MININT' if precision == -2147483648 else str(precision)
            program, _ = compile_program(f"text='keep' CNV_REAL_STR(1.0,1,{spelling},text)")
            with self.subTest(precision=precision), self.assertRaises(rt.KarelRuntimeError): program.run()
            self.assertEqual(program.snapshot()['TEXT'], 'keep')

    def test_conversion_and_write_share_scientific_convention(self):
        program, _ = compile_program('CNV_REAL_STR(123.456,1,-4,text) WRITE(123.456::0::-4)')
        self.assertEqual(program.run()['TEXT'], program.write_requests[0]['text'])

    def test_report_records_pythonic_policy(self):
        _, result = self.conversion('123.0')
        self.assertIn('negative precision uppercase scientific', result.report['conversion_policy']['real_format'])
        self.assertIn('doubled apostrophes', result.report['write_policy']['string'])
        self.assertFalse(result.report['write_policy']['controller_validated'])

    def test_legacy_guards_remain_internal(self):
        with self.assertRaises(TranslationError):
            legacy_translate('PROGRAM T VAR w: INTEGER BEGIN w=6 WRITE(42::w) END T')
        for body in ("WRITE('O''Brien'::16::2)", 'CNV_REAL_STR(123.0,1,-3,text)'):
            result = legacy_translate('PROGRAM T VAR text: STRING[32] BEGIN '+body+' END T')
            namespace = {'__name__': 'legacy_text_guard'}
            exec(result.python_source, namespace)
            with self.subTest(body=body), self.assertRaises(rt.KarelRuntimeError): namespace['Program']().run()

    def test_authored_example_matches_complete_fixtures(self):
        root = Path(__file__).resolve().parents[1]/'examples'
        from karel2py import translate
        result = translate((root/'pythonic_text_formats.kl').read_text())
        namespace = {'__name__': 'text_formats_fixture'}
        exec(result.python_source, namespace)
        observed = []
        program = namespace['Program'](write=observed.append)
        self.assertEqual(program.run(), json.loads((root/'pythonic_text_formats.expected.json').read_text()))
        self.assertEqual(observed, json.loads((root/'pythonic_text_formats.write.expected.json').read_text()))
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))
