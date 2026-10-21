"""Extended exact decimal formatting, with independent Decimal text oracles."""
from decimal import Decimal
import math
import unittest

from karel2py import runtime as rt
from karel2py.lexer import TranslationError
from tests.test_real_text_format import compile_program, execute


def output_reference(capacity=254):
    return rt.Reference(('STRING', capacity), {'value': 'keep'}, 'value')


def format_value(value, precision, *, capacity=254, length=1):
    target = output_reference(capacity)
    rt.conversion_procedure('CNV_REAL_STR', value, length, precision, target, line=37)
    return target.raw()


def decimal_text(value, precision):
    """Independent formatting oracle; callers select values needing no rounding."""
    return ' ' + format(Decimal.from_float(value), f'.{precision}f')


class FixedPrecisionRuntimeTests(unittest.TestCase):
    def test_every_supported_precision_against_decimal_oracle(self):
        for value in (0., 12., -12.):
            for precision in range(255):
                with self.subTest(value=value, precision=precision):
                    expected = decimal_text(value, precision)
                    if len(expected) > 254: expected = ' ' + '*'*253
                    self.assertEqual(format_value(value, precision), expected)

    def test_exact_dyadic_values_with_long_fractional_expansions(self):
        for power in range(1, 127):
            value = math.ldexp(1., -power)
            with self.subTest(power=power):
                self.assertEqual(format_value(value, power), decimal_text(value, power))

    def test_normal_binary32_endpoints_and_149_digit_expansion(self):
        for value in (math.ldexp(1., -126), math.ldexp(8388609., -149),
                      float.fromhex('0x1.fffffep127')):
            for sign in (1, -1):
                with self.subTest(value=value, sign=sign):
                    self.assertEqual(format_value(sign*value, 149), decimal_text(sign*value, 149))

    def test_exact_fractional_values_retain_requested_trailing_zeros(self):
        for value, precision in ((1.125, 3), (-1.234375, 6), (1/8192, 13), (1.25, 7)):
            with self.subTest(value=value, precision=precision):
                self.assertEqual(format_value(value, precision), decimal_text(value, precision))

    def test_maximum_precision_uses_capacity_overflow_marker(self):
        for capacity in (1, 2, 5, 253, 254):
            with self.subTest(capacity=capacity):
                self.assertEqual(format_value(1.125, 254, capacity=capacity), ' '+'*'*(capacity-1))

    def test_output_capacity_thresholds_include_sign_and_decimal_point(self):
        for value in (1.125, -1.125):
            expected = decimal_text(value, 248)
            for capacity in (len(expected)-1, len(expected), 254):
                with self.subTest(value=value, capacity=capacity):
                    result = expected if capacity >= len(expected) else ' '+'*'*(capacity-1)
                    self.assertEqual(format_value(value, 248, capacity=capacity), result)

    def test_254_character_output_limit_boundary(self):
        self.assertEqual(format_value(0., 251), ' 0.'+'0'*251)
        self.assertEqual(format_value(0., 252), ' '+'*'*253)

    def test_rounding_dependent_values_preserve_output(self):
        for value, precision in ((.0625, 3), (-.0625, 3), (1/1024, 9)):
            target = output_reference()
            with self.subTest(value=value, precision=precision):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'decimal rounding'):
                    rt.conversion_procedure('CNV_REAL_STR', value, 1, precision, target, line=37)
                self.assertEqual(target.raw(), 'keep')

    def test_rounding_check_cannot_be_bypassed_by_small_output_capacity(self):
        target = output_reference(1)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'decimal rounding'):
            rt.conversion_procedure('CNV_REAL_STR', .0625, 1, 3, target, line=37)
        self.assertEqual(target.raw(), 'keep')

    def test_scientific_and_out_of_bound_precision_preserve_output(self):
        for precision in (-2147483648, -1, 255, 2147483647):
            target = output_reference()
            with self.subTest(precision=precision):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'line 37'):
                    rt.conversion_procedure('CNV_REAL_STR', 1.125, 1, precision, target, line=37)
                self.assertEqual(target.raw(), 'keep')

    def test_precision_remains_a_strict_initialized_integer(self):
        for precision in (True, 3., '3', rt.UNINITIALIZED, rt.UNKNOWN_BYTE):
            target = output_reference()
            with self.subTest(precision=precision):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'line 37'):
                    rt.conversion_procedure('CNV_REAL_STR', 1.125, 1, precision, target, line=37)
                self.assertEqual(target.raw(), 'keep')

    def test_existing_real_input_guard_runs_before_formatting(self):
        for value in (.1, float('nan'), float('inf'), True, 16777217, rt.UNINITIALIZED):
            target = output_reference()
            with self.subTest(value=value):
                with self.assertRaises(rt.KarelRuntimeError):
                    rt.conversion_procedure('CNV_REAL_STR', value, 1, 13, target, line=37)
                self.assertEqual(target.raw(), 'keep')

    def test_width_and_output_capacity_guards_remain(self):
        for length, capacity in ((0, 254), (-1, 254), (7, 254), (2147483647, 254),
                                 (1, None), (1, 0), (1, 255), (1, True)):
            target = output_reference(capacity)
            with self.subTest(length=length, capacity=capacity):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'line 37'):
                    rt.conversion_procedure('CNV_REAL_STR', 1.125, length, 3, target, line=37)
                self.assertEqual(target.raw(), 'keep')

    def test_signed_zero_and_underflow_keep_existing_zero_policy(self):
        for value in (-0., 1e-50, -1e-50):
            with self.subTest(value=value):
                self.assertEqual(format_value(value, 13), ' 0.'+'0'*13)


class FixedPrecisionSourceTests(unittest.TestCase):
    def test_source_fractions_that_previously_required_more_than_two_digits(self):
        for value, precision, expected in (('1.125', 3, ' 1.125'), ('-1.234375', 6, ' -1.234375'),
                                           ('0.0001220703125', 13, ' 0.0001220703125')):
            with self.subTest(value=value, precision=precision):
                self.assertEqual(execute(f'CNV_REAL_STR({value},1,{precision},text)')['TEXT'], expected)

    def test_constant_and_dynamic_precision_arguments(self):
        state = execute('i=digits+1 CNV_REAL_STR(value,width,i,text)', constants='CONST value=1.125 width=1 digits=2')
        self.assertEqual(state['TEXT'], ' 1.125')

    def test_narrow_values_are_promoted_without_reference_writes(self):
        state = execute('values[1]=3 values[2]=1 CNV_REAL_STR(values[2],1,values[1],text)',
                        declarations='values: ARRAY[2] OF BYTE text: STRING[8]')
        self.assertEqual(state, {'VALUES': [3, 1], 'TEXT': ' 1.000'})

    def test_caller_string_formal_retains_capacity(self):
        routine = 'ROUTINE format(target: STRING) BEGIN CNV_REAL_STR(1.125,1,3,target) END format'
        state = execute('format(text) format(small)', routines=routine)
        self.assertEqual((state['TEXT'], state['SMALL']), (' 1.125', ' **'))

    def test_array_reference_formal_retains_element_capacity(self):
        routine = 'ROUTINE format(target: ARRAY OF STRING) BEGIN CNV_REAL_STR(1.125,1,3,target[1]) END format'
        self.assertEqual(execute('format(labels)', routines=routine, declarations='labels: ARRAY[1] OF STRING[6]')['LABELS'], [' 1.125'])

    def test_named_row_and_using_field_outputs(self):
        types = 'TYPE row_t=ARRAY[1] OF STRING[6] box_t=STRUCTURE text: STRING[6] ENDSTRUCTURE'
        state = execute('CNV_REAL_STR(1.125,1,3,row[1]) USING box DO CNV_REAL_STR(-1.125,1,3,text) ENDUSING',
                        types=types, declarations='row: row_t box: box_t')
        self.assertEqual(state, {'ROW': [' 1.125'], 'BOX': {'TEXT': ' *****'}})

    def test_captured_string_reference_survives_aggregate_replacement(self):
        routine = 'ROUTINE replace(captured: STRING; target,source: ARRAY OF STRING) BEGIN target=source CNV_REAL_STR(1.125,1,3,captured) END replace'
        state = execute("a[1]='a' b[1]='b' replace(a[1],a,b)", routines=routine, declarations='a,b: ARRAY[1] OF STRING[8]')
        self.assertEqual(state, {'A': [' 1.125'], 'B': ['b']})

    def test_formatted_strings_survive_array_function_result_copy(self):
        routine = 'ROUTINE build: ARRAY OF STRING[8] VAR p: ARRAY[1] OF STRING[8] BEGIN CNV_REAL_STR(1.125,1,3,p[1]) RETURN p END build'
        self.assertEqual(execute('a=build', routines=routine, declarations='a: ARRAY[1] OF STRING[8]')['A'], [' 1.125'])

    def test_roundtrip_after_explicit_leading_blank_removal(self):
        state = execute('CNV_REAL_STR(0.0001220703125,1,13,text) CNV_STR_REAL(SUB_STR(text,2,STR_LEN(text)-1),x)')
        self.assertEqual((state['TEXT'], state['X']), (' 0.0001220703125', 1/8192))

    def test_formatting_under_fresh_local_for_counter(self):
        routine = 'ROUTINE fill VAR k: INTEGER BEGIN FOR k=3 TO 4 DO CNV_REAL_STR(1.125,1,k,text) ENDFOR END fill'
        self.assertEqual(execute('fill', routines=routine)['TEXT'], ' 1.1250')

    def test_labelled_and_structured_execution_match(self):
        outcomes = []
        for marker in ('', 'unused:: '):
            program, _ = compile_program(marker+'CNV_REAL_STR(1.125,1,3,text)')
            outcomes.append((program.run(), program._state.steps))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_output_effects_still_propagate_through_bare_function_calls(self):
        routine = 'ROUTINE format: INTEGER BEGIN CNV_REAL_STR(1.125,1,3,text) RETURN 7 END format\nROUTINE wrapper: INTEGER BEGIN RETURN format END wrapper'
        with self.assertRaises(TranslationError) as caught:
            compile_program('i=wrapper+1', routines=routine)
        self.assertEqual(caught.exception.code, 'E_EVALUATION_ORDER')

    def test_readonly_value_temporary_cannot_be_a_format_output(self):
        routine = 'ROUTINE format(target: STRING) BEGIN CNV_REAL_STR(1.125,1,3,target) END format'
        with self.assertRaises(TranslationError) as caught: compile_program("format('seed')", routines=routine)
        self.assertEqual(caught.exception.code, 'E_STRING_VALUE')

    def test_guard_failure_preserves_output_effects_and_unwinds_frames(self):
        routine = 'ROUTINE fail(target: STRING) BEGIN i=7 CNV_REAL_STR(0.0625,1,3,target) END fail'
        program, _ = compile_program("text='keep' fail(text)", routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'decimal rounding') as caught: program.run()
        self.assertIsNotNone(caught.exception.line)
        self.assertEqual((program.snapshot()['TEXT'], program.snapshot()['I']), ('keep', 7))
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_maximum_precision_is_bounded_before_output_assignment(self):
        self.assertEqual(execute('CNV_REAL_STR(1.125,1,254,text)')['TEXT'], ' '+'*'*63)

    def test_metadata_describes_precision_as_a_prototype_bound(self):
        _, result = compile_program('CNV_REAL_STR(1.125,1,3,text)')
        self.assertIn('0..254', result.report['conversion_policy']['real_format'])
        self.assertIn('prototype bound', result.report['conversion_policy']['real_format_guard'])
        self.assertFalse(result.report['conversion_policy']['controller_validated'])


if __name__ == '__main__':
    unittest.main()
