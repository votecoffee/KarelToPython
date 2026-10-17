"""Exact REAL text conversion, caller references and unchanged safety boundaries."""
from fractions import Fraction
from pathlib import Path
import unittest

from karel2py import translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


def compile_program(body, declarations='x,y: REAL text: STRING[32] flag: BOOLEAN i: INTEGER', routines='', types='', constants=''):
    source = f'PROGRAM test\n{constants}\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND test'
    result = translate(source, filename='real_conversion.kl')
    namespace = {'__name__': 'real_conversion_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, **kwargs):
    return compile_program(body, **kwargs)[0].run()


class RealTextValueTests(unittest.TestCase):
    def test_plain_decimal_signs_and_exact_values(self):
        for text, expected in [('12.5', 12.5), ('+2.5', 2.5), ('-1.25', -1.25), ('0002.500', 2.5), ('0.0', 0.0), ('-0.0', 0.0)]:
            with self.subTest(text=text):
                self.assertEqual(execute(f"CNV_STR_REAL('{text}',x)")['X'], expected)

    def test_scientific_notation_requires_no_host_float_parse(self):
        for text, expected in [('1.25E+2', 125.0), ('-2.5E-1', -0.25), ('0.25E+1', 2.5), ('12.5E+1', 125.0)]:
            with self.subTest(text=text):
                self.assertEqual(execute(f"CNV_STR_REAL('{text}',x)")['X'], expected)

    def test_constant_and_string_expression_inputs(self):
        state = execute("CNV_STR_REAL(digits+'25',x)", constants="CONST digits='1.'")
        self.assertEqual(state['X'], 1.25)

    def test_string_processing_input(self):
        state = execute("CNV_STR_REAL(SUB_STR('X2.5',2,3),x)")
        self.assertEqual(state['X'], 2.5)

    def test_invalid_alphabetic_input_clears_previous_value(self):
        for text in ('A', 'invalid', 'NaN', 'Infinity', 'E'):
            with self.subTest(text=text):
                state = execute(f"x=2.5 CNV_STR_REAL('{text}',x) flag=UNINIT(x)")
                self.assertEqual(state['X'], {'uninitialized': True})
                self.assertTrue(state['FLAG'])

    def test_invalid_input_does_not_read_uninitialized_output(self):
        self.assertEqual(execute("CNV_STR_REAL('A',x)")['X'], {'uninitialized': True})

    def test_existing_underflow_zero_policy_is_explicit(self):
        for text in ('1.0E-40', '-1.0E-40', '1.0E-999999'):
            with self.subTest(text=text):
                self.assertEqual(execute(f"CNV_STR_REAL('{text}',x)")['X'], 0.0)

    def test_smallest_normal_exact_decimal(self):
        text = '1.1754943508222875079687365372222456778186655567720875215087517062784172594547271728515625E-38'
        self.assertEqual(Fraction(execute(f"CNV_STR_REAL('{text}',x)")['X']), Fraction(1, 2 ** 126))

    def test_largest_finite_binary32_exact_decimal(self):
        text = '340282346638528859811704183484516925440.0'
        self.assertEqual(Fraction(execute(f"CNV_STR_REAL('{text}',x)")['X']), Fraction(340282346638528859811704183484516925440))

    def test_caller_string_capacity_truncation_precedes_conversion(self):
        state = execute("text='2.500junk' CNV_STR_REAL(text,x)", declarations='text: STRING[5] x: REAL')
        self.assertEqual(state, dict(TEXT='2.500', X=2.5))

    def test_exact_result_enters_existing_real_arithmetic(self):
        state = execute("CNV_STR_REAL('2.5',x) y=x/2")
        self.assertEqual((state['X'], state['Y']), (2.5, 1.25))

    def test_source_continuation_and_call_case(self):
        self.assertEqual(execute("cNv_StR_ReAl('2.5', &\n x)")['X'], 2.5)

    def test_report_exposes_real_parse_boundaries(self):
        _, result = compile_program("CNV_STR_REAL('2.5',x)")
        self.assertIn('CNV_STR_REAL', result.report['features'])
        self.assertIn('exact REAL guard', result.report['conversion_policy']['real_parse'])
        self.assertFalse(result.report['conversion_policy']['controller_validated'])

    def test_example_complete_snapshot(self):
        source = (Path(__file__).resolve().parents[1] / 'examples/text_real_conversion.kl').read_text(encoding='utf-8')
        result = translate(source)
        namespace = {'__name__': 'example_test'}
        exec(result.python_source, namespace)
        self.assertEqual(namespace['Program']().run(), dict(
            VALUES=[1.25, -0.25, 125.0], COPIED=[1.25, -0.25, 125.0], TOTAL=126.0,
            INVALID={'uninitialized': True}, INVALID_DETECTED=True, UNDERFLOW=0.0,
            PACKET=dict(VALUE=2.5, TEXT='2.5'), PURE_RESULT=3.5))


class RealTextReferenceTests(unittest.TestCase):
    def test_multidimensional_array_destination(self):
        state = execute("CNV_STR_REAL('2.5',grid[2,1])", declarations='grid: ARRAY[2,2] OF REAL')
        self.assertEqual(state['GRID'], [[{'uninitialized': True}, {'uninitialized': True}], [2.5, {'uninitialized': True}]])

    def test_nested_structure_array_and_using_output(self):
        types = 'TYPE item_t=STRUCTURE value: REAL ENDSTRUCTURE packet_t=STRUCTURE items: ARRAY[2] OF item_t ENDSTRUCTURE'
        state = execute("USING packet DO CNV_STR_REAL('2.5',items[2].value) ENDUSING", types=types, declarations='packet: packet_t')
        self.assertEqual(state['PACKET'], dict(ITEMS=[dict(VALUE={'uninitialized': True}), dict(VALUE=2.5)]))

    def test_real_reference_formal_writes_through(self):
        routine = "ROUTINE parse(result: REAL) BEGIN CNV_STR_REAL('2.5',result) END parse"
        self.assertEqual(execute('parse(x)', routines=routine)['X'], 2.5)

    def test_grouped_real_actual_is_independent_value(self):
        routine = "ROUTINE parse(result: REAL) BEGIN CNV_STR_REAL('2.5',result) END parse"
        self.assertEqual(execute('x=1.25 parse((x))', routines=routine)['X'], 1.25)

    def test_integer_to_real_actual_remains_independent_value(self):
        routine = "ROUTINE parse(result: REAL) BEGIN CNV_STR_REAL('2.5',result) END parse"
        self.assertEqual(execute('i=7 parse(i)', routines=routine)['I'], 7)

    def test_string_reference_input_and_real_reference_output(self):
        routine = 'ROUTINE parse(source: STRING; result: REAL) BEGIN CNV_STR_REAL(source,result) END parse'
        self.assertEqual(execute("text='2.5' parse(text,x)", routines=routine)['X'], 2.5)

    def test_captured_real_element_reference_survives_whole_array_copy(self):
        routine = "ROUTINE replace(result: REAL; target,source: ARRAY OF REAL) BEGIN target=source CNV_STR_REAL('2.5',result) END replace"
        state = execute('a[1]=1.0 a[2]=2.0 b[1]=10.0 b[2]=20.0 replace(a[2],a,b)', routines=routine, declarations='a,b: ARRAY[2] OF REAL')
        self.assertEqual(state, dict(A=[10.0, 2.5], B=[10.0, 20.0]))

    def test_invalid_input_clears_only_selected_array_element(self):
        state = execute("a[1]=1.25 a[2]=2.5 CNV_STR_REAL('A',a[1])", declarations='a: ARRAY[2] OF REAL')
        self.assertEqual(state['A'], [{'uninitialized': True}, 2.5])

    def test_aliased_real_formals_observe_same_output(self):
        routine = "ROUTINE alias(first,second: REAL) BEGIN CNV_STR_REAL('2.5',first) y=second END alias"
        self.assertEqual(execute('alias(x,x)', routines=routine)['Y'], 2.5)

    def test_pure_local_function_and_for_conversion(self):
        routine = "ROUTINE parse: REAL VAR k: INTEGER local: REAL BEGIN FOR k=1 TO 2 DO CNV_STR_REAL('2.5',local) ENDFOR RETURN local END parse"
        program, result = compile_program('y=parse()+1.0', routines=routine)
        self.assertFalse(result.report['routine_effects']['PARSE']['potential_external_writes'])
        self.assertEqual(program.run()['Y'], 3.5)

    def test_label_dispatcher_preserves_conversion(self):
        state = execute("i=0 again:: CNV_STR_REAL('2.5',x) i=i+1 IF i<2 THEN GOTO again ENDIF")
        self.assertEqual((state['X'], state['I']), (2.5, 2))


class RealTextRuntimeBoundaryTests(unittest.TestCase):
    def failure(self, text, fragment):
        program, _ = compile_program(f"x=2.5 CNV_STR_REAL('{text}',x)")
        with self.assertRaisesRegex(rt.KarelRuntimeError, fragment) as caught:
            program.run()
        self.assertIsNotNone(caught.exception.line)
        self.assertEqual(program._state.snapshot()['X'], 2.5)

    def test_rounding_dependent_inputs_preserve_destination(self):
        for text in ('0.1', '1.23456789', '16777217.0', '3.4028235E+38'):
            with self.subTest(text=text): self.failure(text, 'rounding')

    def test_overflow_preserves_destination(self):
        for text in ('3.5E+38', '-3.5E+38', '1.0E+999999', '9' * 252 + '.0'):
            with self.subTest(text=text): self.failure(text, 'overflow')

    def test_subnormal_boundary_is_not_silently_rounded(self):
        self.failure('1.1754941E-38', 'subnormal boundary')

    def test_unverified_formats_preserve_destination(self):
        for text in ('', ' 2.5', '2.5 ', '2', '.5', '1.', '1E+2', '1.0E2', '1.0e+2', '1_0.0', '0x10', '2.5junk', '2,5', '--2.5', '1.0E+', '1.0 E+2'):
            with self.subTest(text=text): self.failure(text, 'format needs validation')

    def test_input_length_guard_precedes_decimal_parse(self):
        self.failure('0' * 253 + '.0', '254 characters')

    def test_maximum_supported_length_zero_input(self):
        text = '0' * 252 + '.0'
        self.assertEqual(execute(f"CNV_STR_REAL('{text}',x)")['X'], 0.0)

    def test_extreme_exponent_returns_source_located_error(self):
        self.failure('1.0E+' + '9' * 240, 'Invalid REAL literal')

    def test_uninitialized_source_preserves_destination(self):
        program, _ = compile_program('x=2.5 CNV_STR_REAL(text,x)')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual(program._state.snapshot()['X'], 2.5)

    def test_runtime_error_unwinds_frame_and_retains_prior_writes(self):
        routine = "ROUTINE parse BEGIN y=1.25 CNV_STR_REAL('0.1',x) END parse"
        program, _ = compile_program('x=2.5 parse', routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'rounding'): program.run()
        self.assertEqual((program._state.snapshot()['X'], program._state.snapshot()['Y'], program._state.local_frames, program._state.call_depth), (2.5, 1.25, [], 0))

    def test_call_line_survives_continuation(self):
        program, _ = compile_program("x=2.5\nCNV_STR_REAL('0.1', &\n x)")
        with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
        self.assertEqual(caught.exception.line, 8)

    def test_bad_output_index_preserves_other_elements(self):
        program, _ = compile_program("a[1]=2.5 CNV_STR_REAL('1.25',a[0])", declarations='a: ARRAY[2] OF REAL')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'index'): program.run()
        self.assertEqual(program._state.snapshot()['A'], [2.5, {'uninitialized': True}])

    def test_direct_runtime_exact_output_type_and_arity(self):
        target = rt.Reference(rt.INTEGER, {'value': 7}, 'value')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'REAL output reference'):
            rt.conversion_procedure('CNV_STR_REAL', '2.5', target, line=4)
        self.assertEqual(target.raw(), 7)
        for args in ((), (1, 2)):
            with self.subTest(args=args):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'argument count'):
                    rt.conversion_procedure('CNV_STR_REAL', '2.5', *args)


class RealTextTranslationBoundaryTests(unittest.TestCase):
    def reject(self, body, code, **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_procedure_cannot_return_expression_result(self):
        self.reject("y=CNV_STR_REAL('2.5',x)", 'E_PROCEDURE_RESULT')

    def test_arity_and_source_type(self):
        for call in ("CNV_STR_REAL('2.5')", "CNV_STR_REAL('2.5',x,y)"):
            with self.subTest(call=call): self.reject(call, 'E_ARGUMENTS')
        self.reject('CNV_STR_REAL(2.5,x)', 'E_TYPE')

    def test_writable_output_and_exact_real_storage(self):
        for output in ('2.5', '(x)', 'x+1.0', 'bound', 'MAXINT'):
            with self.subTest(output=output):
                self.reject("CNV_STR_REAL('2.5'," + output + ')', 'E_OUTPUT_ARGUMENT', constants='CONST bound=1.25')
        for spec, output in [('INTEGER', 'x'), ('BOOLEAN', 'x'), ('STRING[8]', 'x'), ('ARRAY[1] OF BYTE', 'x[1]'), ('ARRAY[1] OF SHORT', 'x[1]'), ('ARRAY[1] OF REAL', 'x')]:
            with self.subTest(spec=spec):
                self.reject("CNV_STR_REAL('2.5'," + output + ')', 'E_TYPE', declarations='x: ' + spec)

    def test_user_routine_in_source_or_destination_index_is_blocked(self):
        routines = 'ROUTINE one: INTEGER BEGIN RETURN 1 END one'
        self.reject("CNV_STR_REAL(SUB_STR('2.5',one(),3),x)", 'E_EVALUATION_ORDER', routines=routines)
        self.reject("CNV_STR_REAL('2.5',a[one()])", 'E_EVALUATION_ORDER', routines=routines, declarations='a: ARRAY[1] OF REAL')

    def test_conversion_calls_under_global_for_counter_remain_blocked(self):
        self.reject("FOR i=1 TO 2 DO CNV_STR_REAL('2.5',x) ENDFOR", 'E_FOR_COUNTER')

    def test_global_and_formal_conversion_effects_are_detected(self):
        routine = "ROUTINE parse: REAL BEGIN CNV_STR_REAL('2.5',x) RETURN x END parse"
        self.reject('y=parse()+1.0', 'E_EVALUATION_ORDER', routines=routine)
        routine = "ROUTINE parse(result: REAL): REAL BEGIN CNV_STR_REAL('2.5',result) RETURN result END parse"
        self.reject('y=parse(x)+1.0', 'E_EVALUATION_ORDER', routines=routine)

    def test_transitive_using_effects_are_detected(self):
        types = 'TYPE packet_t=STRUCTURE value: REAL ENDSTRUCTURE'
        routines = "ROUTINE parse BEGIN USING packet DO CNV_STR_REAL('2.5',value) ENDUSING END parse ROUTINE wrap: REAL BEGIN parse RETURN 1.0 END wrap"
        self.reject('y=wrap()+1.0', 'E_EVALUATION_ORDER', types=types, routines=routines, declarations='packet: packet_t y: REAL')

    def test_constant_context_and_redefinition_remain_blocked(self):
        self.reject('', 'E_CONSTANT', constants="CONST bad=CNV_STR_REAL('2.5',x)")
        self.reject('', 'E_NAME', declarations='CNV_STR_REAL: REAL')

    def test_read_only_user_string_value_input(self):
        routine = 'ROUTINE parse(source: STRING; result: REAL) BEGIN CNV_STR_REAL(source,result) END parse'
        program, _ = compile_program("parse('2.5',x)", routines=routine)
        self.assertEqual(program.run()['X'], 2.5)

    def test_real_to_string_extra_padding_remains_guarded(self):
        program, _ = compile_program("text='keep' CNV_REAL_STR(2.5,7,2,text)")
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'padding/invalid-length'): program.run()
        self.assertEqual(program._state.snapshot()['TEXT'], 'keep')


if __name__ == '__main__': unittest.main()
