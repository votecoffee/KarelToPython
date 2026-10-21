"""Restricted conversion behavior, output references and effect/flow boundaries."""
from pathlib import Path
import unittest

from karel2py import translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


def compile_program(body, declarations='n,m,i: INTEGER text: STRING[12] small: STRING[3] flag: BOOLEAN', routines='', types='', constants=''):
    source = f'PROGRAM test\n{constants}\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND test'
    result = translate(source, filename='conversion.kl')
    namespace = {'__name__': 'conversion_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, **kwargs):
    return compile_program(body, **kwargs)[0].run()


class ConversionValueTests(unittest.TestCase):
    def test_unsigned_positive_zero_negative_and_explicit_signs(self):
        for text, expected in [('12', 12), ('0', 0), ('-12', -12), ('+12', 12), ('-0', 0), ('+0', 0), ('00012', 12)]:
            with self.subTest(text=text):
                self.assertEqual(execute(f"CNV_STR_INT('{text}', n)")['N'], expected)

    def test_integer_storage_boundaries(self):
        state = execute("CNV_STR_INT('-2147483648', n) CNV_STR_INT('2147483646', m)")
        self.assertEqual((state['N'], state['M']), (-2147483648, 2147483646))

    def test_parse_constant_and_expression_input(self):
        state = execute("CNV_STR_INT(digits + '2', n)", constants="CONST digits = '1'")
        self.assertEqual(state['N'], 12)

    def test_invalid_alphabetic_representation_clears_previous_value(self):
        state = execute("n = 7 CNV_STR_INT('A', n) flag = UNINIT(n)")
        self.assertEqual(state['N'], {'uninitialized': True})
        self.assertTrue(state['FLAG'])

    def test_invalid_alphabetic_input_does_not_require_target_initialized(self):
        self.assertEqual(execute("CNV_STR_INT('invalid', n)")['N'], {'uninitialized': True})

    def test_decimal_base_0_and_10(self):
        state = execute('CNV_INT_STR(12,1,0,text) CNV_INT_STR(12,1,10,small)')
        self.assertEqual((state['TEXT'], state['SMALL']), (' 12', ' 12'))

    def test_decimal_zero_negative_minint_and_maxint_expression(self):
        for number, expected in [('0', ' 0'), ('-12', ' -12'), ('MININT', ' -2147483648'), ('MAXINT', ' 2147483647')]:
            with self.subTest(number=number):
                self.assertEqual(execute(f'CNV_INT_STR({number},1,10,text)')['TEXT'], expected)

    def test_format_is_not_regular_string_assignment_truncation(self):
        self.assertEqual(execute('CNV_INT_STR(12345,1,10,small)')['SMALL'], ' **')

    def test_capacity_thresholds_and_one_character_output(self):
        for size, expected in [(1, ' '), (2, ' *'), (3, ' 12'), (4, ' 12'), (254, ' 12')]:
            with self.subTest(size=size):
                self.assertEqual(execute('CNV_INT_STR(12,1,10,s)', declarations=f's: STRING[{size}]')['S'], expected)

    def test_invalid_bases_clear_output(self):
        for base in (-1, 1, 17, 2147483647):
            with self.subTest(base=base):
                state = execute(f"text = 'keep' CNV_INT_STR(12,1,{base},text) flag=UNINIT(text)")
                self.assertEqual(state['TEXT'], {'uninitialized': True})
                self.assertTrue(state['FLAG'])

    def test_roundtrip_with_explicit_padding_removal(self):
        self.assertEqual(execute("CNV_INT_STR(-12,1,10,text) CNV_STR_INT(SUB_STR(text,2,3),n)")['N'], -12)

    def test_narrow_integer_sources_are_values(self):
        state = execute('bytes[1]=12 CNV_INT_STR(bytes[1],1,10,text)', declarations='bytes: ARRAY[1] OF BYTE text: STRING[8]')
        self.assertEqual((state['BYTES'], state['TEXT']), ([12], ' 12'))

    def test_continuations_and_case_insensitive_calls(self):
        self.assertEqual(execute("cnv_str_int('12', &\n n) cNv_InT_sTr(n,1,10,text)")['TEXT'], ' 12')

    def test_report_describes_bounded_policy(self):
        _, result = compile_program("CNV_STR_INT('12',n) CNV_INT_STR(n,1,10,text)")
        self.assertTrue({'CNV_STR_INT', 'CNV_INT_STR', 'conversion output by reference'} <= set(result.report['features']))
        self.assertFalse(result.report['conversion_policy']['controller_validated'])
        self.assertIn('length 1', result.report['conversion_policy']['format'])

    def test_example_complete_snapshot(self):
        source = (Path(__file__).resolve().parents[1] / 'examples/text_integer_conversion.kl').read_text(encoding='utf-8')
        result = translate(source)
        namespace = {'__name__': 'example_test'}
        exec(result.python_source, namespace)
        self.assertEqual(namespace['Program']().run(), dict(
            PARSED=12, MINIMUM=-2147483648, POSITIVE=42, INVALID_NUMBER={'uninitialized': True}, ROUNDTRIPPED=25,
            VALUES=[12, -5], TEXTS=[' 12', ' -5'], SMALL=' ***', BAD_BASE={'uninitialized': True},
            INVALID_TEXT_DETECTED=True, INVALID_BASE_DETECTED=True, PACKET=dict(NUMBER=25, TEXT=' 25')))


class ConversionReferenceTests(unittest.TestCase):
    def test_array_outputs_and_full_multidimensional_indexes(self):
        state = execute("CNV_STR_INT('12',numbers[2,1]) CNV_INT_STR(12,1,10,labels[1,2])", declarations='numbers: ARRAY[2,2] OF INTEGER labels: ARRAY[2,2] OF STRING[3]')
        self.assertEqual((state['NUMBERS'][1][0], state['LABELS'][0][1]), (12, ' 12'))

    def test_structure_fields_and_using_aliases(self):
        types = 'TYPE record_t = STRUCTURE n: INTEGER text: STRING[3] ENDSTRUCTURE'
        state = execute("USING record DO CNV_STR_INT('12',n) CNV_INT_STR(n,1,10,text) ENDUSING", types=types, declarations='record: record_t')
        self.assertEqual(state['RECORD'], dict(N=12, TEXT=' 12'))

    def test_string_array_output_uses_actual_element_capacity(self):
        state = execute('CNV_INT_STR(12345,1,10,labels[2])', declarations='labels: ARRAY[2] OF STRING[3]')
        self.assertEqual(state['LABELS'], [{'uninitialized': True}, ' **'])

    def test_invalid_conversion_clears_array_element_only(self):
        state = execute("a[1]=7 a[2]=8 CNV_STR_INT('A',a[1])", declarations='a: ARRAY[2] OF INTEGER')
        self.assertEqual(state['A'], [{'uninitialized': True}, 8])

    def test_integer_reference_formal_writes_through(self):
        routine = "ROUTINE parse(result: INTEGER) BEGIN CNV_STR_INT('12',result) END parse"
        self.assertEqual(execute('parse(n)', routines=routine)['N'], 12)

    def test_grouped_caller_scalar_still_passes_independent_value(self):
        routine = "ROUTINE parse(result: INTEGER) BEGIN CNV_STR_INT('12',result) END parse"
        self.assertEqual(execute('n=7 parse((n))', routines=routine)['N'], 7)

    def test_string_reference_formal_keeps_caller_capacity(self):
        routine = 'ROUTINE format(result: STRING) BEGIN CNV_INT_STR(12345,1,10,result) END format'
        state = execute('format(text) format(small)', routines=routine)
        self.assertEqual((state['TEXT'], state['SMALL']), (' 12345', ' **'))

    def test_captured_integer_reference_survives_whole_array_copy(self):
        routine = "ROUTINE replace(result: INTEGER; target,source: ARRAY OF INTEGER) BEGIN target=source CNV_STR_INT('99',result) END replace"
        state = execute('a[1]=1 a[2]=2 b[1]=10 b[2]=20 replace(a[2],a,b)', routines=routine, declarations='a,b: ARRAY[2] OF INTEGER')
        self.assertEqual((state['A'], state['B']), ([10, 99], [10, 20]))

    def test_two_formals_alias_same_output(self):
        routine = "ROUTINE alias(first,second: INTEGER) BEGIN CNV_STR_INT('12',first) m=second END alias"
        self.assertEqual(execute('alias(n,n)', routines=routine)['M'], 12)

    def test_local_outputs_make_pure_conversion_functions(self):
        routine = "ROUTINE parse: INTEGER VAR local: INTEGER BEGIN CNV_STR_INT('12',local) RETURN local END parse"
        program, result = compile_program('n=parse()+1', routines=routine)
        self.assertFalse(result.report['routine_effects']['PARSE']['potential_external_writes'])
        self.assertEqual(program.run()['N'], 13)

    def test_local_conversion_under_fresh_for_counter(self):
        routine = "ROUTINE fill VAR k,result: INTEGER BEGIN FOR k=1 TO 2 DO CNV_STR_INT('12',result) ENDFOR n=result END fill"
        self.assertEqual(execute('fill', routines=routine)['N'], 12)

    def test_string_input_reference_formal_uses_caller_value(self):
        routine = 'ROUTINE parse(source: STRING; result: INTEGER) BEGIN CNV_STR_INT(source,result) END parse'
        self.assertEqual(execute("text='12' parse(text,n)", routines=routine)['N'], 12)

    def test_local_structure_output_keeps_function_pure(self):
        types = 'TYPE packet_t=STRUCTURE number: INTEGER ENDSTRUCTURE'
        routine = "ROUTINE parse: INTEGER VAR local: packet_t BEGIN USING local DO CNV_STR_INT('12',number) ENDUSING RETURN local.number END parse"
        program, result = compile_program('m=parse()+1', types=types, routines=routine)
        self.assertFalse(result.report['routine_effects']['PARSE']['potential_external_writes'])
        self.assertEqual(program.run()['M'], 13)

    def test_labelled_body_keeps_conversion_statements(self):
        self.assertEqual(execute("n=1 again:: CNV_INT_STR(n,1,10,text) n=n+1 IF n<3 THEN GOTO again ENDIF")['TEXT'], ' 2')


class ConversionRuntimeBoundaryTests(unittest.TestCase):
    def failure(self, body, fragment, **kwargs):
        program, _ = compile_program(body, **kwargs)
        with self.assertRaisesRegex(rt.KarelRuntimeError, fragment) as caught: program.run()
        self.assertIsNotNone(caught.exception.line)
        return program

    def test_unverified_parse_formats_preserve_destination(self):
        for value in ('', ' 12', '12 ', '1 2', '1_2', '1.0', '1e2', '0x10', '+', '--1', '12x'):
            with self.subTest(value=value):
                self.assertEqual(self.failure(f"n=7 CNV_STR_INT('{value}',n)", 'format needs validation')._state.snapshot()['N'], 7)

    def test_numeric_parse_range_and_maxint_preserve_destination(self):
        for value in ('2147483647', '2147483648', '-2147483649', '9' * 254):
            with self.subTest(value=value):
                program, _ = compile_program(f"n=7 CNV_STR_INT('{value}',n)")
                with self.assertRaises(rt.KarelRuntimeError): program.run()
                self.assertEqual(program._state.snapshot()['N'], 7)

    def test_oversize_input_is_bounded_before_host_integer_parse(self):
        self.assertEqual(self.failure("n=7 CNV_STR_INT('" + '0' * 255 + "',n)", '254 characters')._state.snapshot()['N'], 7)

    def test_unverified_widths_preserve_output(self):
        for width in (-1, 0, 2, 8, 2147483647):
            with self.subTest(width=width):
                self.assertEqual(self.failure(f"text='keep' CNV_INT_STR(12,{width},10,text)", 'requires length 1')._state.snapshot()['TEXT'], 'keep')

    def test_alphabetic_digit_bases_preserve_output(self):
        for base in (11, 12, 16):
            with self.subTest(base=base):
                self.assertEqual(self.failure(f"text='keep' CNV_INT_STR(12,1,{base},text)", 'alphabetic digit case')._state.snapshot()['TEXT'], 'keep')

    def test_uninitialized_source_does_not_clear_output(self):
        self.assertEqual(self.failure('n=7 CNV_STR_INT(text,n)', 'uninitialized')._state.snapshot()['N'], 7)

    def test_uninitialized_numeric_source_does_not_change_output(self):
        self.assertEqual(self.failure("text='keep' CNV_INT_STR(n,1,10,text)", 'uninitialized')._state.snapshot()['TEXT'], 'keep')

    def test_bad_output_index_does_not_change_other_elements(self):
        program = self.failure("a[1]=7 CNV_STR_INT('12',a[0])", 'index', declarations='a: ARRAY[2] OF INTEGER')
        self.assertEqual(program._state.snapshot()['A'], [7, {'uninitialized': True}])

    def test_runtime_error_unwinds_frame_and_preserves_prior_writes(self):
        routine = "ROUTINE parse BEGIN m=9 CNV_STR_INT('2147483647',n) END parse"
        program = self.failure('n=7 parse', 'storage excludes MAXINT', routines=routine)
        self.assertEqual((program._state.snapshot()['N'], program._state.snapshot()['M'], program._state.local_frames, program._state.call_depth), (7, 9, [], 0))

    def test_error_line_is_original_call_line_after_continuation(self):
        program, _ = compile_program("n=7\nCNV_STR_INT('2147483647', &\n n)")
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'storage excludes MAXINT') as caught: program.run()
        self.assertEqual(caught.exception.line, 8)
        self.assertEqual(program._state.snapshot()['N'], 7)

    def test_direct_runtime_checks_output_type_and_call_arity(self):
        for call in [('unknown', '12'), ('CNV_STR_INT', '12'), ('CNV_STR_INT', '12', 1)]:
            with self.subTest(call=call):
                with self.assertRaises(rt.KarelRuntimeError): rt.conversion_procedure(*call)


class ConversionTranslationBoundaryTests(unittest.TestCase):
    def reject(self, body, code, **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_procedures_are_not_expression_results(self):
        self.reject("n=CNV_STR_INT('12',m)", 'E_PROCEDURE_RESULT')
        self.reject('n=STR_LEN(CNV_INT_STR(12,1,10,text))', 'E_PROCEDURE_RESULT')

    def test_argument_counts(self):
        for call in ("CNV_STR_INT('12')", "CNV_STR_INT('12',n,m)", 'CNV_INT_STR(12,1,text)', 'CNV_INT_STR(12,1,10,text,n)'):
            with self.subTest(call=call): self.reject(call, 'E_ARGUMENTS')

    def test_exact_input_types(self):
        self.reject('CNV_STR_INT(12,n)', 'E_TYPE')
        self.reject('CNV_INT_STR(1.0,1,10,text)', 'E_TYPE')
        self.reject('CNV_INT_STR(1,ON,10,text)', 'E_TYPE')
        self.reject('CNV_INT_STR(1,1,OFF,text)', 'E_TYPE')

    def test_output_must_be_writable_unparenthesized_storage(self):
        for output in ('1', 'MAXINT', '(n)', 'n+1', 'bound'):
            with self.subTest(output=output): self.reject("CNV_STR_INT('12'," + output + ')', 'E_OUTPUT_ARGUMENT', constants='CONST bound=7')
        self.reject("CNV_INT_STR(12,1,10,'abc')", 'E_OUTPUT_ARGUMENT')

    def test_narrow_real_boolean_and_aggregate_outputs_are_blocked(self):
        for spec, target in [('ARRAY[1] OF BYTE', 'n[1]'), ('ARRAY[1] OF SHORT', 'n[1]'), ('REAL', 'n'), ('BOOLEAN', 'n'), ('ARRAY[1] OF INTEGER', 'n')]:
            with self.subTest(spec=spec): self.reject("CNV_STR_INT('12'," + target + ')', 'E_TYPE', declarations='n: ' + spec)
        self.reject('CNV_INT_STR(12,1,10,n)', 'E_TYPE')

    def test_user_call_in_any_conversion_argument_is_blocked(self):
        routines = 'ROUTINE one: INTEGER BEGIN RETURN 1 END one'
        for call in ('CNV_INT_STR(one(),1,10,text)', 'CNV_INT_STR(12,one(),10,text)', 'CNV_INT_STR(12,1,one(),text)'):
            with self.subTest(call=call): self.reject(call, 'E_EVALUATION_ORDER', routines=routines)
        self.reject("CNV_STR_INT('12',a[one()])", 'E_EVALUATION_ORDER', routines=routines, declarations='a: ARRAY[2] OF INTEGER')

    def test_global_counter_conversion_calls_remain_blocked(self):
        self.reject("FOR i=1 TO 2 DO CNV_STR_INT('12',n) ENDFOR", 'E_FOR_COUNTER')

    def test_active_local_counter_output_is_blocked(self):
        routine = "ROUTINE fill VAR k: INTEGER BEGIN FOR k=1 TO 2 DO CNV_STR_INT('12',k) ENDFOR END fill"
        self.reject('fill', 'E_FOR_COUNTER', routines=routine)

    def test_global_conversion_write_is_detected_in_function_expression(self):
        routine = "ROUTINE parse: INTEGER BEGIN CNV_STR_INT('12',n) RETURN 1 END parse"
        self.reject('m=parse()+1', 'E_EVALUATION_ORDER', routines=routine)

    def test_formal_conversion_write_and_transitive_effects_are_detected(self):
        routines = "ROUTINE parse(result: INTEGER) BEGIN CNV_STR_INT('12',result) END parse ROUTINE wrapped: INTEGER BEGIN parse(n) RETURN 1 END wrapped"
        self.reject('m=wrapped()+1', 'E_EVALUATION_ORDER', routines=routines)

    def test_using_output_cannot_hide_global_field_write(self):
        types = 'TYPE packet_t=STRUCTURE n: INTEGER ENDSTRUCTURE'
        routine = "ROUTINE parse: INTEGER BEGIN USING packet DO CNV_STR_INT('12',n) ENDUSING RETURN 1 END parse"
        self.reject('m=parse()+1', 'E_EVALUATION_ORDER', routines=routine, types=types, declarations='packet: packet_t m: INTEGER')

    def test_constant_calls_and_redefinition_remain_blocked(self):
        self.reject('', 'E_CONSTANT', constants="CONST result=CNV_STR_INT('12',n)")
        self.reject('', 'E_NAME', declarations='CNV_STR_INT: INTEGER')

    def test_read_only_user_string_value_input(self):
        routine = 'ROUTINE parse(source: STRING; result: INTEGER) BEGIN CNV_STR_INT(source,result) END parse'
        program, _ = compile_program("parse('12',n)", routines=routine)
        self.assertEqual(program.run()['N'], 12)


if __name__ == '__main__': unittest.main()
