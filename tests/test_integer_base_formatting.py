"""Nonnegative numeric-digit bases retain conversion ownership and fault guards."""
import unittest

from karel2py import runtime as rt
from karel2py.lexer import TranslationError
from tests.test_text_integer_conversion import compile_program, execute


def output_reference(capacity=40):
    return rt.Reference(('STRING', capacity), {'value': 'keep'}, 'value')


def format_value(value, base, *, capacity=40, length=1):
    target = output_reference(capacity)
    rt.conversion_procedure('CNV_INT_STR', value, length, base, target, line=37)
    return target.raw()


class IntegerBaseRuntimeTests(unittest.TestCase):
    def test_exact_numeric_digit_examples(self):
        for base, digits in ((2, '101010'), (3, '1120'), (4, '222'), (5, '132'),
                             (6, '110'), (7, '60'), (8, '52'), (9, '46')):
            with self.subTest(base=base): self.assertEqual(format_value(42, base), ' '+digits)

    def test_small_values_in_every_numeric_digit_base(self):
        for base in range(2, 10):
            for value in range(256):
                with self.subTest(base=base, value=value):
                    text = format_value(value, base)
                    self.assertEqual(text[0], ' ')
                    digits = text[1:]
                    self.assertTrue(digits and all('0' <= digit < str(base) for digit in digits))
                    self.assertEqual(int(digits, base), value)
                    self.assertTrue(digits == '0' or not digits.startswith('0'))

    def test_powers_and_signed_integer_expression_upper_endpoint(self):
        for base in range(2, 10):
            values = {0, 2147483646, 2147483647}
            power = base
            while power < 2147483647:
                values.update((power-1, power, power+1)); power *= base
            for value in sorted(values):
                with self.subTest(base=base, value=value):
                    text = format_value(value, base)
                    self.assertEqual(int(text[1:], base), value)
                    self.assertTrue(text[1:] == '0' or text[1] != '0')
                    self.assertLessEqual(len(text), 32)

    def test_binary_and_octal_match_independent_standard_formatters(self):
        for value in (0, 1, 7, 8, 15, 16, 255, 256, 65535, 2147483647):
            for base, code in ((2, 'b'), (8, 'o')):
                with self.subTest(base=base, value=value):
                    self.assertEqual(format_value(value, base), ' '+format(value, code))

    def test_capacity_thresholds_keep_overflow_markers(self):
        for capacity in (1, 2, 6, 7, 8, 254):
            with self.subTest(capacity=capacity):
                expected = ' 101010' if capacity >= 7 else ' '+'*'*(capacity-1)
                self.assertEqual(format_value(42, 2, capacity=capacity), expected)

    def test_zero_has_one_digit_and_no_added_zero_padding(self):
        for base in range(2, 10):
            with self.subTest(base=base): self.assertEqual(format_value(0, base), ' 0')

    def test_negative_nondecimal_values_preserve_output(self):
        for base in range(2, 10):
            for value in (-1, -42, -2147483648):
                target = output_reference()
                with self.subTest(base=base, value=value):
                    with self.assertRaisesRegex(rt.KarelRuntimeError, 'negative nondecimal'):
                        rt.conversion_procedure('CNV_INT_STR', value, 1, base, target, line=37)
                    self.assertEqual(target.raw(), 'keep')

    def test_alphabetic_digit_bases_remain_blocked_even_for_small_values(self):
        for base in range(11, 17):
            target = output_reference()
            with self.subTest(base=base):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'alphabetic digit case'):
                    rt.conversion_procedure('CNV_INT_STR', 0, 1, base, target, line=37)
                self.assertEqual(target.raw(), 'keep')

    def test_invalid_bases_still_clear_the_output(self):
        for base in (-2147483648, -1, 1, 17, 2147483647):
            with self.subTest(base=base): self.assertIs(format_value(42, base), rt.UNINITIALIZED)

    def test_source_length_and_base_keep_strict_initialized_types(self):
        for position in range(3):
            for invalid in (True, 2., '2', rt.UNINITIALIZED, rt.UNKNOWN_BYTE):
                values = [42, 1, 2]; values[position] = invalid
                target = output_reference()
                with self.subTest(position=position, invalid=invalid):
                    with self.assertRaisesRegex(rt.KarelRuntimeError, 'line 37'):
                        rt.conversion_procedure('CNV_INT_STR', *values, target, line=37)
                    self.assertEqual(target.raw(), 'keep')

    def test_existing_width_guard_precedes_invalid_base_clearing(self):
        for length in (-1, 0, 2, 2147483647):
            target = output_reference()
            with self.subTest(length=length):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'requires length 1'):
                    rt.conversion_procedure('CNV_INT_STR', 42, length, 1, target, line=37)
                self.assertEqual(target.raw(), 'keep')

    def test_signed_decimal_aliases_are_unchanged(self):
        for base in (0, 10):
            for value in (-2147483648, -42, 0, 2147483647):
                with self.subTest(base=base, value=value):
                    self.assertEqual(format_value(value, base), ' '+str(value))

    def test_source_overflow_preserves_output(self):
        for value in (-2147483649, 2147483648):
            target = output_reference()
            with self.subTest(value=value):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'overflow'):
                    rt.conversion_procedure('CNV_INT_STR', value, 1, 2, target, line=37)
                self.assertEqual(target.raw(), 'keep')

    def test_capacity_is_never_inferred_from_logical_contents(self):
        for capacity in (None, 0, 255, True):
            target = output_reference(capacity)
            with self.subTest(capacity=capacity):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'capacity'):
                    rt.conversion_procedure('CNV_INT_STR', 42, 1, 2, target, line=37)
                self.assertEqual(target.raw(), 'keep')


class IntegerBaseSourceTests(unittest.TestCase):
    def test_literal_binary_and_octal_source_calls(self):
        state = execute('CNV_INT_STR(42,1,2,text) CNV_INT_STR(42,1,8,other)',
                        declarations='text,other: STRING[12]')
        self.assertEqual(state, {'TEXT': ' 101010', 'OTHER': ' 52'})

    def test_constant_and_dynamic_base_arguments(self):
        self.assertEqual(execute('i=radix+1 CNV_INT_STR(number,width,i,text)',
                                 constants='CONST radix=2 number=42 width=1')['TEXT'], ' 1120')

    def test_narrow_inputs_are_promoted_independent_values(self):
        state = execute('value[1]=255 options[1]=1 options[2]=8 CNV_INT_STR(value[1],options[1],options[2],text)',
                        declarations='value: ARRAY[1] OF BYTE options: ARRAY[2] OF SHORT text: STRING[8]')
        self.assertEqual(state, {'VALUE': [255], 'OPTIONS': [1, 8], 'TEXT': ' 377'})

    def test_caller_string_formals_retain_each_capacity(self):
        routine = 'ROUTINE format(target: STRING) BEGIN CNV_INT_STR(42,1,2,target) END format'
        state = execute('format(text) format(small)', routines=routine)
        self.assertEqual((state['TEXT'], state['SMALL']), (' 101010', ' **'))

    def test_array_formal_keeps_element_capacity(self):
        routine = 'ROUTINE format(target: ARRAY OF STRING) BEGIN CNV_INT_STR(42,1,2,target[1]) END format'
        self.assertEqual(execute('format(labels)', routines=routine, declarations='labels: ARRAY[1] OF STRING[7]')['LABELS'], [' 101010'])

    def test_named_rows_and_using_fields_are_writable_outputs(self):
        types = 'TYPE row_t=ARRAY[1] OF STRING[7] box_t=STRUCTURE label: STRING[4] ENDSTRUCTURE'
        state = execute('CNV_INT_STR(42,1,2,row[1]) USING box DO CNV_INT_STR(42,1,8,label) ENDUSING',
                        types=types, declarations='row: row_t box: box_t')
        self.assertEqual(state, {'ROW': [' 101010'], 'BOX': {'LABEL': ' 52'}})

    def test_captured_string_reference_survives_array_replacement(self):
        routine = 'ROUTINE replace(captured: STRING; target,source: ARRAY OF STRING) BEGIN target=source CNV_INT_STR(42,1,2,captured) END replace'
        state = execute("a[1]='a' b[1]='b' replace(a[1],a,b)", routines=routine, declarations='a,b: ARRAY[1] OF STRING[8]')
        self.assertEqual(state, {'A': [' 101010'], 'B': ['b']})

    def test_binary_text_survives_array_function_result_copy(self):
        routine = 'ROUTINE build: ARRAY OF STRING[8] VAR p: ARRAY[1] OF STRING[8] BEGIN CNV_INT_STR(42,1,2,p[1]) RETURN p END build'
        self.assertEqual(execute('a=build', routines=routine, declarations='a: ARRAY[1] OF STRING[8]')['A'], [' 101010'])

    def test_labelled_and_structured_execution_match(self):
        outcomes = []
        for marker in ('', 'unused:: '):
            program, _ = compile_program(marker+'CNV_INT_STR(42,1,2,text)')
            outcomes.append((program.run(), program._state.steps))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_fresh_local_for_counter_can_supply_base(self):
        routine = 'ROUTINE fill VAR k: INTEGER BEGIN FOR k=2 TO 9 DO CNV_INT_STR(42,1,k,text) ENDFOR END fill'
        self.assertEqual(execute('fill', routines=routine)['TEXT'], ' 46')

    def test_output_effects_still_propagate_through_function_calls(self):
        routine = 'ROUTINE format: INTEGER BEGIN CNV_INT_STR(42,1,2,text) RETURN 7 END format\nROUTINE wrapper: INTEGER BEGIN RETURN format END wrapper'
        with self.assertRaises(TranslationError) as caught: compile_program('n=wrapper+1', routines=routine)
        self.assertEqual(caught.exception.code, 'E_EVALUATION_ORDER')

    def test_string_value_temporaries_remain_protected(self):
        routine = 'ROUTINE format(target: STRING) BEGIN CNV_INT_STR(42,1,2,target) END format'
        with self.assertRaises(TranslationError) as caught: compile_program("format('seed')", routines=routine)
        self.assertEqual(caught.exception.code, 'E_STRING_VALUE')

    def test_failure_retains_prior_effects_and_unwinds_frames(self):
        routine = 'ROUTINE fail(target: STRING) BEGIN n=9 CNV_INT_STR(-42,1,2,target) END fail'
        program, _ = compile_program("text='keep' fail(text)", routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'negative nondecimal') as caught: program.run()
        self.assertIsNotNone(caught.exception.line)
        self.assertEqual((program.snapshot()['TEXT'], program.snapshot()['N']), ('keep', 9))
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_user_function_arguments_remain_blocked(self):
        routine = 'ROUTINE radix: INTEGER BEGIN RETURN 2 END radix'
        with self.assertRaises(TranslationError) as caught:
            compile_program('CNV_INT_STR(42,1,radix,text)', routines=routine)
        self.assertEqual(caught.exception.code, 'E_EVALUATION_ORDER')

    def test_result_can_feed_existing_write_request_recorder(self):
        program, _ = compile_program('CNV_INT_STR(42,1,2,text) WRITE(text)')
        program.run()
        self.assertEqual([row['text'] for row in program.write_requests], [' 101010'])

    def test_report_records_nondecimal_boundaries(self):
        _, result = compile_program('CNV_INT_STR(42,1,2,text)')
        self.assertIn('bases 2..9', result.report['conversion_policy']['format'])
        self.assertIn('11..16', result.report['conversion_policy']['nondecimal_format'])
        self.assertFalse(result.report['conversion_policy']['controller_validated'])


if __name__ == '__main__':
    unittest.main()
