"""Exact fixed-decimal formatting and unchanged output/reference guard policies."""
from pathlib import Path
import unittest

from karel2py import translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


def compile_program(body, declarations='text: STRING[64] small: STRING[3] x: REAL i: INTEGER flag: BOOLEAN', routines='', types='', constants=''):
    source = f'PROGRAM test\n{constants}\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND test'
    result = translate(source, filename='real_format.kl')
    namespace = {'__name__': 'real_format_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, **kwargs):
    return compile_program(body, **kwargs)[0].run()


class RealFormatValueTests(unittest.TestCase):
    def test_exact_fixed_fractional_digits(self):
        for value, precision, expected in [('12.0', 0, ' 12'), ('2.5', 1, ' 2.5'), ('2.5', 2, ' 2.50'), ('0.25', 2, ' 0.25'), ('-1.25', 2, ' -1.25'), ('-1.0', 0, ' -1')]:
            with self.subTest(value=value, precision=precision):
                self.assertEqual(execute(f'CNV_REAL_STR({value},1,{precision},text)')['TEXT'], expected)

    def test_zero_decimal_point_suppression_and_trailing_zeros(self):
        for precision, expected in [(0, ' 0'), (1, ' 0.0'), (2, ' 0.00')]:
            with self.subTest(precision=precision):
                self.assertEqual(execute(f'CNV_REAL_STR(0.0,1,{precision},text)')['TEXT'], expected)

    def test_signed_zero_uses_existing_positive_zero_policy(self):
        self.assertEqual(execute('CNV_REAL_STR(-0.0,1,2,text)')['TEXT'], ' 0.00')

    def test_positive_minimum_lengths_not_requiring_padding(self):
        for width in range(1, 8):
            with self.subTest(width=width):
                self.assertEqual(execute(f'CNV_REAL_STR(123.25,{width},2,text)')['TEXT'], ' 123.25')

    def test_manual_example_width_and_precision_without_padding(self):
        self.assertEqual(execute('CNV_REAL_STR(123.25,7,2,text)')['TEXT'], ' 123.25')

    def test_capacity_overflow_markers_are_not_right_truncation(self):
        self.assertEqual(execute('CNV_REAL_STR(-1.25,1,2,small)')['SMALL'], ' **')

    def test_caller_capacity_thresholds(self):
        for size, expected in [(1, ' '), (2, ' *'), (3, ' **'), (4, ' ***'), (5, ' 2.50'), (254, ' 2.50')]:
            with self.subTest(size=size):
                self.assertEqual(execute('CNV_REAL_STR(2.5,1,2,s)', declarations=f's: STRING[{size}]')['S'], expected)

    def test_large_exact_real_stays_fixed_decimal(self):
        value = '340282346638528859811704183484516925440.0'
        self.assertEqual(execute(f'CNV_REAL_STR({value},1,2,text)')['TEXT'], ' 340282346638528859811704183484516925440.00')

    def test_integer_source_promotion_is_checked(self):
        self.assertEqual(execute('CNV_REAL_STR(12,1,2,text)')['TEXT'], ' 12.00')

    def test_narrow_sources_and_format_arguments_are_values(self):
        state = execute('b[1]=255 s[1]=1 s[2]=2 CNV_REAL_STR(b[1],s[1],s[2],text)', declarations='b: ARRAY[1] OF BYTE s: ARRAY[2] OF SHORT text: STRING[12]')
        self.assertEqual(state, dict(B=[255], S=[1, 2], TEXT=' 255.00'))

    def test_constants_and_input_expressions(self):
        state = execute('CNV_REAL_STR(value/2,width+1,digits,text)', constants='CONST value=5.0 width=0 digits=2')
        self.assertEqual(state['TEXT'], ' 2.50')

    def test_input_reads_existing_output_before_write(self):
        self.assertEqual(execute("text='abc' CNV_REAL_STR(STR_LEN(text),1,0,text)")['TEXT'], ' 3')

    def test_roundtrip_with_explicit_leading_blank_removal(self):
        state = execute('CNV_REAL_STR(-1.25,1,2,text) CNV_STR_REAL(SUB_STR(text,2,STR_LEN(text)-1),x)')
        self.assertEqual((state['TEXT'], state['X']), (' -1.25', -1.25))

    def test_case_insensitive_call_with_continuation(self):
        self.assertEqual(execute('cNv_ReAl_StR(2.5,1, &\n 2,text)')['TEXT'], ' 2.50')

    def test_report_exposes_format_restrictions(self):
        _, result = compile_program('CNV_REAL_STR(2.5,1,2,text)')
        self.assertIn('CNV_REAL_STR', result.report['features'])
        self.assertIn('0/1/2', result.report['conversion_policy']['real_format'])
        self.assertIn('Rounding', result.report['conversion_policy']['real_format_guard'])
        self.assertFalse(result.report['conversion_policy']['controller_validated'])

    def test_complete_example_snapshot(self):
        source = (Path(__file__).resolve().parents[1] / 'examples/real_text_format.kl').read_text(encoding='utf-8')
        result = translate(source)
        namespace = {'__name__': 'example_test'}
        exec(result.python_source, namespace)
        self.assertEqual(namespace['Program']().run(), dict(
            NUMBERS=[12.0, 2.5, -1.25], LABELS=[' 12', ' 2.5', ' -1.25'], SMALL=' **',
            PACKET=dict(VALUE=123.25, TEXT=' 123.25'), PARSED_REAL=2.5, PARSED_INTEGER=12, VERIFIED=True))


class RealFormatReferenceTests(unittest.TestCase):
    def test_multidimensional_string_array_output(self):
        state = execute('CNV_REAL_STR(2.5,1,2,labels[2,1])', declarations='labels: ARRAY[2,2] OF STRING[5]')
        self.assertEqual(state['LABELS'], [[{'uninitialized': True}, {'uninitialized': True}], [' 2.50', {'uninitialized': True}]])

    def test_using_output_field_keeps_capacity(self):
        types = 'TYPE packet_t=STRUCTURE text: STRING[3] ENDSTRUCTURE'
        state = execute('USING packet DO CNV_REAL_STR(2.5,1,2,text) ENDUSING', types=types, declarations='packet: packet_t')
        self.assertEqual(state['PACKET'], dict(TEXT=' **'))

    def test_reference_formal_uses_caller_capacity(self):
        routine = 'ROUTINE format(target: STRING) BEGIN CNV_REAL_STR(2.5,1,2,target) END format'
        state = execute('format(text) format(small)', routines=routine)
        self.assertEqual((state['TEXT'], state['SMALL']), (' 2.50', ' **'))

    def test_array_formal_keeps_element_capacity(self):
        routine = 'ROUTINE format(target: ARRAY OF STRING) BEGIN CNV_REAL_STR(2.5,1,2,target[1]) END format'
        self.assertEqual(execute('format(labels)', routines=routine, declarations='labels: ARRAY[1] OF STRING[3]')['LABELS'], [' **'])

    def test_captured_string_reference_survives_whole_array_copy(self):
        routine = 'ROUTINE replace(result: STRING; target,source: ARRAY OF STRING) BEGIN target=source CNV_REAL_STR(2.5,1,2,result) END replace'
        state = execute("a[1]='a' a[2]='b' b[1]='first' b[2]='second' replace(a[2],a,b)", routines=routine, declarations='a,b: ARRAY[2] OF STRING[8]')
        self.assertEqual(state, dict(A=['first', ' 2.50'], B=['first', 'second']))

    def test_captured_field_survives_whole_structure_copy(self):
        types = 'TYPE packet_t=STRUCTURE text: STRING[8] ENDSTRUCTURE'
        routine = 'ROUTINE replace(result: STRING; target,source: packet_t) BEGIN target=source CNV_REAL_STR(2.5,1,2,result) END replace'
        state = execute("a.text='old' b.text='new' replace(a.text,a,b)", types=types, routines=routine, declarations='a,b: packet_t')
        self.assertEqual(state, dict(A=dict(TEXT=' 2.50'), B=dict(TEXT='new')))

    def test_two_string_formals_alias_same_storage(self):
        routine = 'ROUTINE alias(first,second: STRING) BEGIN CNV_REAL_STR(2.5,1,2,first) small=second END alias'
        self.assertEqual(execute('alias(text,text)', routines=routine)['SMALL'], ' 2.')

    def test_pure_local_format_function(self):
        routine = "ROUTINE format: BOOLEAN VAR label: STRING[8] BEGIN CNV_REAL_STR(2.5,1,2,label) RETURN label=' 2.50' END format"
        program, result = compile_program('flag=format()', routines=routine)
        self.assertFalse(result.report['routine_effects']['FORMAT']['potential_external_writes'])
        self.assertTrue(program.run()['FLAG'])

    def test_conversion_under_fresh_local_for_counter(self):
        routine = 'ROUTINE fill VAR k: INTEGER BEGIN FOR k=1 TO 2 DO CNV_REAL_STR(k,1,0,text) ENDFOR END fill'
        self.assertEqual(execute('fill', routines=routine)['TEXT'], ' 2')

    def test_label_dispatcher_preserves_formatting(self):
        self.assertEqual(execute('i=0 again:: CNV_REAL_STR(i,1,0,text) i=i+1 IF i<2 THEN GOTO again ENDIF')['TEXT'], ' 1')


class RealFormatRuntimeBoundaryTests(unittest.TestCase):
    def failure(self, call, fragment, **kwargs):
        program, _ = compile_program("text='keep' " + call, **kwargs)
        with self.assertRaisesRegex(rt.KarelRuntimeError, fragment) as caught: program.run()
        self.assertIsNotNone(caught.exception.line)
        self.assertEqual(program._state.snapshot()['TEXT'], 'keep')
        return program

    def test_decimal_rounding_is_blocked_before_destination_write(self):
        for value, precision in [('2.5', 0), ('2.75', 1), ('0.125', 2), ('-1.25', 1)]:
            with self.subTest(value=value, precision=precision):
                self.failure(f'CNV_REAL_STR({value},1,{precision},text)', 'decimal rounding')

    def test_scientific_and_other_precisions_preserve_output(self):
        for precision in (-2, -1, 3, 7, 2147483647):
            with self.subTest(precision=precision):
                self.failure(f'CNV_REAL_STR(2.5,1,{precision},text)', 'scientific/other precision')

    def test_padding_and_invalid_length_outcomes_not_inferred(self):
        for width in (-1, 0, 6, 7, 2147483647):
            with self.subTest(width=width):
                self.failure(f'CNV_REAL_STR(2.5,{width},2,text)', 'padding/invalid-length')

    def test_integer_source_promotion_that_needs_rounding_preserves_output(self):
        self.failure('CNV_REAL_STR(MAXINT,1,0,text)', 'REAL rounding')

    def test_uninitialized_source_preserves_output(self):
        self.failure('CNV_REAL_STR(x,1,2,text)', 'uninitialized')

    def test_uninitialized_format_argument_preserves_output(self):
        self.failure('CNV_REAL_STR(2.5,i,2,text)', 'uninitialized')
        self.failure('CNV_REAL_STR(2.5,1,i,text)', 'uninitialized')

    def test_unknown_byte_source_preserves_output(self):
        self.failure('CNV_REAL_STR(b[1],1,0,text)', 'Initial BYTE', declarations='b: ARRAY[1] OF BYTE text: STRING[8]')

    def test_runtime_failure_unwinds_frame_and_keeps_earlier_writes(self):
        routine = 'ROUTINE format BEGIN i=9 CNV_REAL_STR(2.5,1,0,text) END format'
        program = self.failure('format', 'decimal rounding', routines=routine)
        self.assertEqual((program._state.snapshot()['I'], program._state.local_frames, program._state.call_depth), (9, [], 0))

    def test_call_line_survives_continuation(self):
        program, _ = compile_program("text='keep'\nCNV_REAL_STR(2.5, &\n 1,0,text)")
        with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
        self.assertEqual(caught.exception.line, 8)
        self.assertEqual(program._state.snapshot()['TEXT'], 'keep')

    def test_bad_output_index_preserves_existing_element(self):
        program, _ = compile_program("labels[1]='keep' CNV_REAL_STR(2.5,1,2,labels[0])", declarations='labels: ARRAY[1] OF STRING[8]')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'index'): program.run()
        self.assertEqual(program._state.snapshot()['LABELS'], ['keep'])

    def test_runtime_output_type_and_arity(self):
        target = rt.Reference(rt.REAL, {'value': 1.25}, 'value')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'STRING output reference'):
            rt.conversion_procedure('CNV_REAL_STR', 2.5, 1, 2, target)
        self.assertEqual(target.raw(), 1.25)
        for args in ((), (1,), (1, 2), (1, 2, 3, 4)):
            with self.subTest(args=args):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'argument count'):
                    rt.conversion_procedure('CNV_REAL_STR', 2.5, *args)

    def test_runtime_concrete_capacity_guard_preserves_output(self):
        for capacity in (None, 0, 255, True):
            with self.subTest(capacity=capacity):
                target = rt.Reference(('STRING', capacity), {'value': 'keep'}, 'value')
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'concrete caller STRING capacity'):
                    rt.conversion_procedure('CNV_REAL_STR', 2.5, 1, 2, target)
                self.assertEqual(target.raw(), 'keep')

    def test_nonfinite_or_wrong_host_source_type_preserves_output(self):
        for value in (float('inf'), float('nan'), True, '2.5'):
            with self.subTest(value=value):
                target = rt.Reference(('STRING', 8), {'value': 'keep'}, 'value')
                with self.assertRaises(rt.KarelRuntimeError):
                    rt.conversion_procedure('CNV_REAL_STR', value, 1, 2, target)
                self.assertEqual(target.raw(), 'keep')


class RealFormatTranslationBoundaryTests(unittest.TestCase):
    def reject(self, body, code, **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_procedure_cannot_be_expression_result(self):
        self.reject('i=STR_LEN(CNV_REAL_STR(2.5,1,2,text))', 'E_PROCEDURE_RESULT')

    def test_argument_count_and_exact_format_argument_types(self):
        for call in ('CNV_REAL_STR(2.5,1,text)', 'CNV_REAL_STR(2.5,1,2,text,small)'):
            with self.subTest(call=call): self.reject(call, 'E_ARGUMENTS')
        for call in ('CNV_REAL_STR(ON,1,2,text)', "CNV_REAL_STR('2.5',1,2,text)", 'CNV_REAL_STR(2.5,1.0,2,text)', 'CNV_REAL_STR(2.5,1,OFF,text)'):
            with self.subTest(call=call): self.reject(call, 'E_TYPE')

    def test_writable_output_and_exact_string_storage(self):
        for output in ("'abc'", '(text)', "text+'x'", 'bound'):
            with self.subTest(output=output):
                self.reject('CNV_REAL_STR(2.5,1,2,' + output + ')', 'E_OUTPUT_ARGUMENT', constants="CONST bound='abc'")
        for output in ('x', 'i', 'flag'):
            with self.subTest(output=output): self.reject('CNV_REAL_STR(2.5,1,2,' + output + ')', 'E_TYPE')

    def test_user_routine_calls_in_all_arguments_are_blocked(self):
        routines = 'ROUTINE one: INTEGER BEGIN RETURN 1 END one'
        for call in ('CNV_REAL_STR(one(),1,2,text)', 'CNV_REAL_STR(2.5,one(),2,text)', 'CNV_REAL_STR(2.5,1,one(),text)', 'CNV_REAL_STR(2.5,1,2,labels[one()])'):
            with self.subTest(call=call):
                self.reject(call, 'E_EVALUATION_ORDER', routines=routines, declarations='text: STRING[8] labels: ARRAY[1] OF STRING[8]')

    def test_global_for_counter_call_remains_blocked(self):
        self.reject('FOR i=1 TO 2 DO CNV_REAL_STR(2.5,1,2,text) ENDFOR', 'E_FOR_COUNTER')

    def test_global_and_formal_writes_are_visible_to_effect_analysis(self):
        routines = ['ROUTINE format: INTEGER BEGIN CNV_REAL_STR(2.5,1,2,text) RETURN 1 END format',
                    'ROUTINE format(target: STRING): INTEGER BEGIN CNV_REAL_STR(2.5,1,2,target) RETURN 1 END format']
        for routine, call in [(routines[0], 'i=format()+1'), (routines[1], 'i=format(text)+1')]:
            with self.subTest(call=call): self.reject(call, 'E_EVALUATION_ORDER', routines=routine)

    def test_using_transitive_write_cannot_hide_global_output(self):
        types = 'TYPE packet_t=STRUCTURE label: STRING[8] ENDSTRUCTURE'
        routines = 'ROUTINE format BEGIN USING packet DO CNV_REAL_STR(2.5,1,2,label) ENDUSING END format ROUTINE wrap: INTEGER BEGIN format RETURN 1 END wrap'
        self.reject('i=wrap()+1', 'E_EVALUATION_ORDER', types=types, routines=routines, declarations='i: INTEGER packet: packet_t')

    def test_constant_context_and_builtin_redefinition_remain_blocked(self):
        self.reject('', 'E_CONSTANT', constants='CONST bad=CNV_REAL_STR(2.5,1,2,text)')
        self.reject('', 'E_NAME', declarations='CNV_REAL_STR: STRING[8]')

    def test_rounding_dependent_real_literal_still_fails_translation(self):
        self.reject('CNV_REAL_STR(0.1,1,2,text)', 'E_REAL_LITERAL')

    def test_environment_directive_remains_unsupported(self):
        with self.assertRaises(TranslationError) as caught:
            translate('PROGRAM test\n%NOLOCKGROUP\n%ENVIRONMENT STRNG\nVAR text: STRING[8]\nBEGIN CNV_REAL_STR(2.5,1,2,text) END test')
        self.assertEqual(caught.exception.code, 'E_DIRECTIVE')


if __name__ == '__main__': unittest.main()
