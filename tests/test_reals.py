"""Exact-value REAL model, promotion rules, conversion limits and fail-closed edges."""
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import struct
import unittest

from karel2py import translate
from karel2py.lexer import TranslationError
from karel2py.runtime import KarelRuntimeError, real, real_literal


DECLARATIONS = '''
r,s: REAL
x,y: INTEGER
flag: BOOLEAN
a,z: ARRAY[2] OF REAL
ints: ARRAY[2] OF INTEGER
'''


def compile_program(body, routines='', declarations=DECLARATIONS, constants=''):
    result = translate(f'PROGRAM T\n{constants}\nVAR\n{declarations}\n{routines}\nBEGIN\n{body}\nEND T')
    namespace = {'__name__': 'real_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, routines='', **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


class RealLiteralTests(unittest.TestCase):
    def test_decimal_and_scientific_forms(self):
        for literal, expected in [('1.25', 1.25), ('.5', 0.5), ('1.', 1.0), ('1E2', 100.0), ('1.E2', 100.0), ('1.25e+1', 12.5), ('125E-2', 1.25)]:
            with self.subTest(literal=literal):
                value = execute(f'r = {literal}')['R']
                self.assertEqual(value, expected)
                self.assertIs(type(value), float)

    def test_signed_real_literals(self):
        self.assertEqual(execute('r = -2.5 s = +1.25')['R'], -2.5)

    def test_real_constants_and_constant_expressions(self):
        state = execute('r = C s = D flag = C > 1', constants='CONST C = 1.25\nD = C * 2.0')
        self.assertEqual((state['R'], state['S'], state['FLAG']), (1.25, 2.5, True))

    def test_real_constant_in_routine(self):
        self.assertEqual(execute('r = f()', 'ROUTINE f: REAL BEGIN RETURN C END f', constants='CONST C = 2.5')['R'], 2.5)

    def test_rounding_dependent_literal_rejected_at_conversion(self):
        for literal in ('0.1', '1.0000000000000001', '16777217.0', '1E20'):
            with self.subTest(literal=literal):
                with self.assertRaises(TranslationError) as caught: compile_program(f'r = {literal}')
                self.assertEqual(caught.exception.code, 'E_REAL_LITERAL')
                self.assertIn('rounding', caught.exception.message)

    def test_rounding_dependent_constant_rejected(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('r = C', constants='CONST C = 1.0 / 3.0')
        self.assertEqual(caught.exception.code, 'E_CONSTANT')

    def test_underflow_literal_is_zero(self):
        state = execute('r = 1E-39 s = -1E-99')
        self.assertEqual((state['R'], state['S']), (0.0, 0.0))

    def test_extreme_exponents_checked_without_huge_fraction(self):
        self.assertEqual(execute('r = 1E-99999')['R'], 0.0)
        with self.assertRaises(TranslationError) as caught: compile_program('r = 1E99999')
        self.assertEqual(caught.exception.code, 'E_REAL_LITERAL')
        self.assertIn('overflow', caught.exception.message)

    def test_maximum_normal_binary32_is_exact(self):
        literal = '340282346638528859811704183484516925440.0'
        value = execute('r = ' + literal)['R']
        self.assertEqual(struct.pack('>f', value), bytes.fromhex('7f7fffff'))

    def test_minimum_normal_binary32_is_exact(self):
        expected = struct.unpack('>f', bytes.fromhex('00800000'))[0]
        literal = str(Decimal.from_float(expected))
        self.assertEqual(struct.pack('>f', execute('r = ' + literal)['R']), bytes.fromhex('00800000'))

    def test_nearby_subnormal_boundary_is_blocked(self):
        value = struct.unpack('>f', bytes.fromhex('007fffff'))[0]
        with self.assertRaises(TranslationError) as caught: compile_program('r = ' + str(Decimal.from_float(value)))
        self.assertEqual(caught.exception.code, 'E_REAL_LITERAL')
        self.assertIn('subnormal boundary', caught.exception.message)

    def test_no_nonfinite_or_boolean_runtime_real_values(self):
        for value in (float('nan'), float('inf'), -float('inf'), True, '1.0'):
            with self.subTest(value=value):
                with self.assertRaises(KarelRuntimeError): real(value)

    def test_literal_parser_does_not_round_through_host_float(self):
        with self.assertRaisesRegex(KarelRuntimeError, 'rounding'): real_literal('1.0000000000000001')

    def test_report_states_exact_model_and_validation_boundary(self):
        _, result = compile_program('r = 1.25')
        self.assertEqual(result.report['numeric_policy']['real_model'], 'exact_binary32_normal_or_zero')
        self.assertFalse(result.report['numeric_policy']['controller_validated'])


class RealArithmeticTests(unittest.TestCase):
    def runtime_error(self, body, message):
        p, _ = compile_program(body)
        with self.assertRaisesRegex(KarelRuntimeError, message): p.run()
        return p

    def test_exact_arithmetic(self):
        state = execute('r = (1.25 + 2.5) * 2 s = r - 0.5')
        self.assertEqual((state['R'], state['S']), (7.5, 7.0))

    def test_integer_slash_produces_real(self):
        value = execute('r = 5 / 2')['R']
        self.assertEqual(value, 2.5)
        self.assertIs(type(value), float)

    def test_mixed_operand_order(self):
        state = execute('r = 2 + 1.25 s = 1.25 + 2')
        self.assertEqual((state['R'], state['S']), (3.25, 3.25))

    def test_mixed_comparisons(self):
        for expression in ('2.5 > 2', '2 < 2.5', '2 = 2.0', '2.5 <> 2', '2.0 <= 2', '2 >= 2.0'):
            with self.subTest(expression=expression): self.assertTrue(execute('flag = ' + expression)['FLAG'])

    def test_unary_precedence_applies_to_reals(self):
        self.assertEqual(execute('r = -1.0 + 2.0 * 3.0')['R'], 5.0)

    def test_abs_real_preserves_type(self):
        value = execute('r = ABS(-2.5)')['R']
        self.assertEqual(value, 2.5)
        self.assertIs(type(value), float)

    def test_integer_assignment_promotes_without_changing_integer(self):
        state = execute('x = 3 r = x')
        self.assertIs(type(state['X']), int)
        self.assertIs(type(state['R']), float)
        self.assertEqual(state['R'], 3.0)

    def test_division_requiring_rounding_rejects_before_assignment(self):
        p = self.runtime_error('r = 2.5 r = 1 / 3', 'rounding')
        self.assertEqual(p._state.get('R'), 2.5)

    def test_half_ulp_addition_is_not_silently_rounded(self):
        self.runtime_error('r = 1.0 + 0.000000059604644775390625', 'rounding')

    def test_full_ulp_addition_is_exact(self):
        value = execute('r = 1.0 + 0.00000011920928955078125')['R']
        self.assertEqual(struct.pack('>f', value), bytes.fromhex('3f800001'))

    def test_large_integer_promotion_needing_rounding_is_blocked(self):
        self.runtime_error('x = 16777217 r = x', 'rounding')

    def test_mixed_comparison_needing_promotion_rounding_is_blocked(self):
        self.runtime_error('x = 16777217 flag = x > 16777216.0', 'rounding')

    def test_integer_arithmetic_stays_integer_before_assignment(self):
        self.runtime_error('r = 2147483647 + 1', 'INTEGER overflow')

    def test_real_overflow_rejected(self):
        self.runtime_error('r = 1.70141183460469231731687303715884105728E38 * 2.0', 'REAL overflow')

    def test_real_underflow_result_is_zero(self):
        minimum = struct.unpack('>f', bytes.fromhex('00800000'))[0]
        state = execute('r = ' + str(Decimal.from_float(minimum)) + ' s = r * 0.5')
        self.assertEqual(state['S'], 0.0)

    def test_real_and_integer_division_by_zero(self):
        for expression in ('1.0 / 0.0', '1 / 0', '1.0 / 1E-99'):
            with self.subTest(expression=expression): self.runtime_error('r = ' + expression, 'Division by zero')

    def test_uninitialized_real_read(self):
        self.runtime_error('s = r + 1.0', 'uninitialized')

    def test_uninit_real_and_array_element(self):
        state = execute('flag = UNINIT(r) a[1] = 1.25 x = 1 IF UNINIT(a[2]) THEN x = 2 ENDIF')
        self.assertTrue(state['FLAG'])
        self.assertEqual(state['X'], 2)

    def test_real_while_control_flow(self):
        self.assertEqual(execute('r = 0.0 WHILE r < 2.0 DO r = r + 0.5 ENDWHILE')['R'], 2.0)

    def test_result_is_exact_rational_not_host_approximation(self):
        value = execute('r = 1.25 / 2.5')['R']
        self.assertEqual(Fraction(value), Fraction(1, 2))


class RealParameterTests(unittest.TestCase):
    def test_real_reference_mutates_caller(self):
        self.assertEqual(execute('r = 1.25 change(r)', 'ROUTINE change(p: REAL) BEGIN p = p * 2.0 END change')['R'], 2.5)

    def test_real_parenthesized_argument_is_value(self):
        self.assertEqual(execute('r = 1.25 change((r))', 'ROUTINE change(p: REAL) BEGIN p = p * 2.0 END change')['R'], 1.25)

    def test_real_literal_and_expression_value_arguments(self):
        routine = 'ROUTINE remember(p: REAL) BEGIN s = p p = 9.0 END remember'
        self.assertEqual(execute('remember(1.25 + 1.25)', routine)['S'], 2.5)

    def test_integer_variable_to_real_parameter_is_value(self):
        state = execute('x = 3 change(x)', 'ROUTINE change(p: REAL) BEGIN p = 9.5 s = p END change')
        self.assertEqual((state['X'], state['S']), (3, 9.5))

    def test_integer_array_element_to_real_parameter_is_value(self):
        routine = 'ROUTINE change(p: REAL) BEGIN p = 9.5 END change'
        self.assertEqual(execute('ints[1] = 3 change(ints[1])', routine)['INTS'][0], 3)

    def test_uninitialized_integer_promotion_requires_read(self):
        p, _ = compile_program('change(x)', 'ROUTINE change(p: REAL) BEGIN p = 2.5 END change')
        with self.assertRaisesRegex(KarelRuntimeError, 'uninitialized'): p.run()
        self.assertEqual(p._state.local_frames, [])

    def test_uninitialized_real_reference_can_be_output(self):
        self.assertEqual(execute('change(r)', 'ROUTINE change(p: REAL) BEGIN p = 2.5 END change')['R'], 2.5)

    def test_integer_to_real_promotion_is_reported_as_value(self):
        _, result = compile_program('change(x)', 'ROUTINE change(p: REAL) BEGIN END change')
        self.assertIn('INTEGER to REAL value argument', result.report['features'])
        self.assertIn('parameter by value', result.report['features'])
        self.assertNotIn('parameter by reference', result.report['features'])

    def test_promoted_integer_temporary_can_be_forwarded_as_real_reference(self):
        routines = 'ROUTINE change(p: REAL) BEGIN p = 2.5 END change\nROUTINE forward(q: REAL) BEGIN change(q) s = q END forward'
        state = execute('x = 3 forward(x)', routines)
        self.assertEqual((state['X'], state['S']), (3, 2.5))

    def test_two_real_references_alias_immediately(self):
        routine = 'ROUTINE alias(p,q: REAL) BEGIN p = 2.5 s = q q = 3.5 END alias'
        state = execute('alias(r,r)', routine)
        self.assertEqual((state['R'], state['S']), (3.5, 2.5))

    def test_two_promoted_integer_arguments_are_independent(self):
        routine = 'ROUTINE alias(p,q: REAL) BEGIN p = 9.5 s = q END alias'
        state = execute('x = 3 alias(x,x)', routine)
        self.assertEqual((state['X'], state['S']), (3, 3.0))

    def test_real_function_can_return_integer_value(self):
        value = execute('r = f()', 'ROUTINE f: REAL BEGIN RETURN 3 END f')['R']
        self.assertEqual(value, 3.0)
        self.assertIs(type(value), float)

    def test_real_function_and_local_frame(self):
        routine = 'ROUTINE f(p: REAL): REAL VAR local_value: REAL BEGIN local_value = p / 2.0 RETURN local_value END f'
        self.assertEqual(execute('r = f(2.5)', routine)['R'], 1.25)

    def test_failed_real_operation_unwinds_without_overwriting_reference(self):
        routine = 'ROUTINE fail(p: REAL) BEGIN p = p / 3.0 END fail'
        p, _ = compile_program('r = 1.0 fail(r)', routine)
        with self.assertRaisesRegex(KarelRuntimeError, 'rounding'): p.run()
        self.assertEqual(p._state.get('R'), 1.0)
        self.assertEqual(p._state.local_frames, [])

    def test_real_array_formal_and_element_reference(self):
        routines = 'ROUTINE change(p: REAL) BEGIN p = 2.5 END change\nROUTINE fill(q: ARRAY OF REAL) BEGIN change(q[2]) END fill'
        self.assertEqual(execute('fill(a)', routines)['A'][1], 2.5)

    def test_real_array_element_integer_assignment_promotes(self):
        state = execute('a[1] = 3 z = a z[1] = 2.5')
        self.assertEqual((state['A'][0], state['Z'][0]), (3.0, 2.5))


class NumericConversionTests(unittest.TestCase):
    def test_round_ties_away_from_zero(self):
        for value, expected in [('2.5', 3), ('-2.5', -3), ('0.5', 1), ('-0.5', -1), ('2.25', 2), ('-2.25', -2), ('2.75', 3)]:
            with self.subTest(value=value): self.assertEqual(execute('x = ROUND(' + value + ')')['X'], expected)

    def test_trunc_discards_fraction_toward_zero(self):
        for value, expected in [('2.75', 2), ('-2.75', -2), ('0.5', 0), ('-0.5', 0)]:
            with self.subTest(value=value): self.assertEqual(execute('x = TRUNC(' + value + ')')['X'], expected)

    def test_integer_builtin_argument_promotes(self):
        self.assertEqual(execute('x = ROUND(3) y = TRUNC(-3)')['X'], 3)

    def test_conversion_minimum_integer_boundary(self):
        state = execute('x = ROUND(-2147483648.0) y = TRUNC(-2147483648.0)')
        self.assertEqual((state['X'], state['Y']), (-2147483648, -2147483648))

    def test_largest_exact_real_within_positive_conversion_ranges(self):
        state = execute('x = ROUND(2147483520.0) y = TRUNC(2147483520.0)')
        self.assertEqual((state['X'], state['Y']), (2147483520, 2147483520))

    def test_documented_conversion_range_errors(self):
        for expression in ('ROUND(2147483648.0)', 'TRUNC(2147483648.0)', 'ROUND(-4294967296.0)', 'TRUNC(-4294967296.0)'):
            with self.subTest(expression=expression):
                p, _ = compile_program('x = ' + expression)
                with self.assertRaisesRegex(KarelRuntimeError, 'conversion range'): p.run()

    def test_conversion_can_be_used_as_array_index(self):
        self.assertEqual(execute('a[ROUND(1.5)] = 2.5')['A'][1], 2.5)


class RealRejectionTests(unittest.TestCase):
    def rejected(self, body, code='E_TYPE', routines='', **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, routines, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_real_to_integer_assignment_requires_conversion(self):
        self.rejected('x = 1.25')

    def test_real_arguments_cannot_bind_integer_parameters(self):
        self.rejected('change(r)', routines='ROUTINE change(p: INTEGER) BEGIN END change')

    def test_integer_array_cannot_promote_to_real_array(self):
        self.rejected('fill(ints)', routines='ROUTINE fill(p: ARRAY OF REAL) BEGIN END fill')

    def test_real_array_cannot_assign_integer_array(self):
        self.rejected('a = ints')

    def test_boolean_and_string_are_not_numeric(self):
        for expression in ('TRUE + 1.0', "'a' + 1.0", 'TRUE / 2', 'TRUE = 1.0', "1.0 > 'a'"):
            with self.subTest(expression=expression): self.rejected('r = ' + expression)

    def test_integer_only_operators_remain_integer_only(self):
        for expression in ('1.0 DIV 2', '1 MOD 2.0', '1.0 AND 2.0', '1.0 OR 2.0', 'NOT 1.0'):
            with self.subTest(expression=expression): self.rejected('r = ' + expression)

    def test_real_index_and_for_counter_are_blocked(self):
        self.rejected('a[1.0] = 2.5')
        self.rejected('FOR r = 1 TO 2 DO ENDFOR', 'E_FOR_COUNTER')

    def test_real_function_cannot_return_real_to_integer_contract(self):
        self.rejected('', 'E_RETURN', routines='ROUTINE f: INTEGER BEGIN RETURN 1.25 END f')

    def test_conversion_argument_types_and_arity(self):
        for expression, code in [('ROUND(TRUE)', 'E_TYPE'), ("TRUNC('abc')", 'E_TYPE'), ('ROUND()', 'E_ARGUMENTS'), ('TRUNC(1.0,2.0)', 'E_ARGUMENTS')]:
            with self.subTest(expression=expression): self.rejected('x = ' + expression, code)

    def test_real_side_effect_order_guards_remain_active(self):
        self.rejected('r = r + f(r)', 'E_EVALUATION_ORDER', routines='ROUTINE f(p: REAL): REAL BEGIN p = 2.5 RETURN p END f')

    def test_numeric_example(self):
        root = Path(__file__).resolve().parents[1]
        result = translate((root / 'examples/exact_numeric.kl').read_text())
        namespace = {'__name__': 'numeric_example'}
        exec(result.python_source, namespace)
        state = namespace['Program']().run()
        self.assertEqual(state['SOURCE_COUNT'], 3)
        self.assertEqual(state['PROMOTED_VALUE'], 4.5)
        self.assertEqual(state['MEASUREMENT'], 2.5)
        self.assertEqual(state['HALF_VALUE'], 1.25)
        self.assertEqual(state['ROUNDED'], 3)
        self.assertEqual(state['TRUNCATED'], -2)


if __name__ == '__main__': unittest.main()
