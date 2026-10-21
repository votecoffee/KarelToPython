"""Exact square roots, numeric guards and interactions with existing source rules."""
from fractions import Fraction
from pathlib import Path
import math
import struct
import unittest

from tests.legacy_numeric_support import translate
from karel2py.lexer import TranslationError
from karel2py.runtime import KarelRuntimeError, builtin


DECLARATIONS = '''
r,s: REAL
i,visits: INTEGER
flag: BOOLEAN
a: ARRAY[2,2] OF REAL
bytes: ARRAY[2] OF BYTE
shorts: ARRAY[2] OF SHORT
'''


def compile_program(body, routines='', declarations=DECLARATIONS, prefix=''):
    source = f'PROGRAM T\n{prefix}\nVAR\n{declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result = translate(source)
    namespace = {'__name__': 'sqrt_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, routines='', **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


class SquareRootValueTests(unittest.TestCase):
    def test_exact_integer_and_fractional_roots_return_real(self):
        for argument, expected in [('0', 0.0), ('1', 1.0), ('81', 9.0),
                                   ('0.0625', 0.25), ('0.25', 0.5),
                                   ('2.25', 1.5), ('6.25', 2.5)]:
            with self.subTest(argument=argument):
                value = execute(f'r = SQRT({argument})')['R']
                self.assertEqual(value, expected)
                self.assertIs(type(value), float)

    def test_manual_hypotenuse_expression(self):
        state = execute('r = 3.0 s = 4.0 r = SQRT(r*r + s*s)')
        self.assertEqual((state['R'], state['S']), (5.0, 4.0))

    def test_integer_input_storage_is_unchanged(self):
        state = execute('i = 81 r = SQRT(i)')
        self.assertEqual((state['I'], state['R']), (81, 9.0))

    def test_nested_roots_and_conversions(self):
        state = execute('r = SQRT(SQRT(256.0)) i = ROUND(SQRT(6.25)) s = TRUNC(SQRT(6.25))')
        self.assertEqual((state['R'], state['I'], state['S']), (4.0, 3, 2.0))

    def test_root_in_comparison(self):
        self.assertTrue(execute('flag = SQRT(4.0) = 2')['FLAG'])

    def test_builtin_composition(self):
        self.assertEqual(execute('r = SQRT(ABS(-16.0))')['R'], 4.0)

    def test_case_insensitive_name(self):
        self.assertEqual(execute('r = sQrT(9.0)')['R'], 3.0)

    def test_exact_roots_across_binary32_exponents(self):
        # Independent expected roots; cover both extremes and fractional mantissas.
        for exponent in range(-63, 64):
            expected = math.ldexp(1.0, exponent)
            argument = math.ldexp(1.0, 2 * exponent)
            self.assertEqual(builtin('SQRT', [argument]), expected)
        for numerator in (1, 3, 5, 7, 31, 255):
            for shift in (0, 1, 4, 16, 32):
                expected = Fraction(numerator, 2 ** shift)
                value = builtin('SQRT', [float(expected * expected)])
                self.assertEqual(Fraction(value), expected)

    def test_zero_normalization_and_existing_underflow_policy(self):
        for value in (0.0, -0.0, 1e-39, -1e-39):
            root = builtin('SQRT', [value])
            self.assertEqual(struct.pack('>f', root), bytes.fromhex('00000000'))
        self.assertEqual(execute('r = SQRT(-1E-99)')['R'], 0.0)

    def test_generated_example_complete_snapshot(self):
        path = Path(__file__).resolve().parents[1] / 'examples/square_roots.kl'
        result = translate(path.read_text())
        namespace = {'__name__': 'sqrt_example'}
        exec(result.python_source, namespace)
        self.assertEqual(namespace['Program']().run(), dict(
            LEG_A=3.0, LEG_B=4.0, HYPOTENUSE=5.0, NESTED_ROOT=4.0,
            SQUARES=[[0.0, 0.25], [2.25, 16.0]], ROOTS=[[0.0, 0.5], [1.5, 4.0]],
            BYTES=[144, {'unknown_byte': True}], SOURCE_COUNT=81, ROUNDED_ROOT=3,
            PROMOTED_ROOT=9.0, BYTE_ROOT=12.0))


class SquareRootInteractionTests(unittest.TestCase):
    def test_multidimensional_input_and_destination(self):
        state = execute('a[2,1] = 6.25 a[1,2] = SQRT(a[2,1])')
        self.assertEqual((state['A'][1][0], state['A'][0][1]), (6.25, 2.5))

    def test_known_byte_and_short_promotion(self):
        state = execute('bytes[1] = 144 shorts[1] = 81 r = SQRT(bytes[1]) s = SQRT(shorts[1])')
        self.assertEqual((state['R'], state['S'], state['BYTES'][0], state['SHORTS'][0]), (12.0, 9.0, 144, 81))

    def test_structure_field_input(self):
        prefix = 'TYPE packet = STRUCTURE value: SHORT ENDSTRUCTURE'
        state = execute('p.value = 81 r = SQRT(p.value)', prefix=prefix, declarations='p: packet\nr: REAL')
        self.assertEqual((state['P']['VALUE'], state['R']), (81, 9.0))

    def test_single_effectful_argument_evaluated_once(self):
        routine = 'ROUTINE next_value: REAL BEGIN visits = visits + 1 RETURN 9.0 END next_value'
        state = execute('visits = 0 r = SQRT(next_value())', routine)
        self.assertEqual((state['VISITS'], state['R']), (1, 3.0))

    def test_user_function_can_return_root_with_integer_value_promotion(self):
        routine = 'ROUTINE root(p: REAL): REAL BEGIN p = SQRT(p) RETURN p END root'
        state = execute('i = 81 r = root(i)', routine)
        self.assertEqual((state['I'], state['R']), (81, 9.0))

    def test_root_helper_inside_fresh_local_for(self):
        routines = '''ROUTINE root(p: REAL): REAL BEGIN RETURN SQRT(p) END root
ROUTINE fill VAR k: INTEGER BEGIN FOR k = 1 TO 2 DO a[k,1] = root(k*k) ENDFOR END fill'''
        state = execute('fill', routines)
        self.assertEqual([row[0] for row in state['A']], [1.0, 2.0])

    def test_error_unwinds_nested_for_frames_and_preserves_prior_write(self):
        routines = '''ROUTINE root(p: REAL): REAL BEGIN visits = visits + 1 RETURN SQRT(p) END root
ROUTINE fill VAR k: INTEGER value: REAL BEGIN FOR k = 1 TO 2 DO value = root(k) a[k,1] = value ENDFOR END fill'''
        program, _ = compile_program('visits = 0 fill', routines)
        with self.assertRaisesRegex(KarelRuntimeError, 'SQRT rounding'): program.run()
        self.assertEqual(program._state.snapshot()['A'], [[1.0, {'uninitialized': True}],
                                                        [{'uninitialized': True}, {'uninitialized': True}]])
        self.assertEqual((program._state.get('VISITS'), program._state.local_frames, program._state.call_depth), (2, [], 0))

    def test_numeric_policy_and_feature_report(self):
        _, result = compile_program('r = SQRT(4.0)')
        self.assertIn('SQRT', result.report['features'])
        self.assertIn('exact rational roots', result.report['numeric_policy']['sqrt'])
        self.assertFalse(result.report['numeric_policy']['controller_validated'])


class SquareRootRuntimeBoundaryTests(unittest.TestCase):
    def test_irrational_roots_fail_without_destination_write(self):
        for expression in ('2', '3.0', '0.5', '1.125', '2.5'):
            with self.subTest(expression=expression):
                program, _ = compile_program(f'r = 7.0 r = SQRT({expression})')
                with self.assertRaisesRegex(KarelRuntimeError, 'SQRT rounding'): program.run()
                self.assertEqual(program._state.get('R'), 7.0)

    def test_negative_inputs_raise_source_located_errors(self):
        for value in (-1, -2.5):
            with self.subTest(value=value):
                with self.assertRaisesRegex(KarelRuntimeError, 'SQRT argument must not be negative') as caught:
                    builtin('SQRT', [value], 27)
                self.assertEqual(caught.exception.line, 27)

    def test_negative_array_destination_remains_unchanged(self):
        program, _ = compile_program('a[1,1] = 7.0 a[1,1] = SQRT(-4.0)')
        with self.assertRaisesRegex(KarelRuntimeError, 'negative'): program.run()
        self.assertEqual(program._state.snapshot()['A'][0][0], 7.0)

    def test_next_binary32_after_one_is_not_mistaken_for_a_square(self):
        value = struct.unpack('>f', bytes.fromhex('3f800001'))[0]
        with self.assertRaisesRegex(KarelRuntimeError, 'SQRT rounding'): builtin('SQRT', [value])

    def test_integer_promotion_must_be_exact_even_when_root_would_be_exact(self):
        # 4097 is exact, but its square needs rounding on conversion to REAL.
        program, _ = compile_program('i = 16785409 r = 7.0 r = SQRT(i)')
        with self.assertRaisesRegex(KarelRuntimeError, 'REAL rounding'): program.run()
        self.assertEqual((program._state.get('I'), program._state.get('R')), (16785409, 7.0))

    def test_uninitialized_and_unknown_inputs_are_not_zero(self):
        for expression, message in [('r', 'uninitialized'), ('shorts[1]', 'uninitialized'),
                                    ('bytes[1]', 'unknown')]:
            with self.subTest(expression=expression):
                program, _ = compile_program(f's = SQRT({expression})')
                with self.assertRaisesRegex(KarelRuntimeError, message): program.run()

    def test_short_sentinel_cannot_be_rooted(self):
        program, _ = compile_program('shorts[1] = 32767 r = SQRT(shorts[1])')
        with self.assertRaisesRegex(KarelRuntimeError, 'uninitialized'): program.run()

    def test_host_values_respect_existing_real_guards(self):
        for value in (True, '4', float('nan'), float('inf'), 1e100, 0.1):
            with self.subTest(value=value):
                with self.assertRaises(KarelRuntimeError): builtin('SQRT', [value])


class SquareRootSourceBoundaryTests(unittest.TestCase):
    def rejected(self, body, code, **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_arity_is_checked(self):
        for expression in ('SQRT()', 'SQRT(1,4)'):
            with self.subTest(expression=expression): self.rejected('r = ' + expression, 'E_ARGUMENTS')

    def test_non_numeric_arguments_are_rejected(self):
        for expression in ('TRUE', "'4'", 'a', 'flag'):
            with self.subTest(expression=expression): self.rejected(f'r = SQRT({expression})', 'E_TYPE')

    def test_real_result_requires_explicit_integer_conversion(self):
        self.rejected('i = SQRT(4)', 'E_TYPE')

    def test_constant_evaluation_remains_restricted(self):
        self.rejected('r = ROOT', 'E_CONSTANT', prefix='CONST ROOT = SQRT(4.0)')

    def test_rounding_dependent_input_literal_remains_rejected(self):
        self.rejected('r = SQRT(0.1)', 'E_REAL_LITERAL')

    def test_builtin_name_is_reserved(self):
        self.rejected('r = 1.0', 'E_NAME', declarations='r: REAL\nSQRT: INTEGER')

    def test_effectful_argument_nested_in_binary_expression_remains_blocked(self):
        routine = 'ROUTINE next_value: REAL BEGIN visits = visits + 1 RETURN 9.0 END next_value'
        self.rejected('r = SQRT(next_value()) + r', 'E_EVALUATION_ORDER', routines=routine)

    def test_multi_argument_order_guard_applies_through_sqrt(self):
        routines = '''ROUTINE source_value: REAL BEGIN RETURN 4.0 END source_value
ROUTINE consume(p,q: REAL) BEGIN END consume'''
        self.rejected('consume(SQRT(source_value()),4.0)', 'E_EVALUATION_ORDER', routines=routines)

    def test_indexed_target_order_guard_applies_through_sqrt(self):
        routine = 'ROUTINE next_value: REAL BEGIN i = 2 RETURN 4.0 END next_value'
        self.rejected('a[i,1] = SQRT(next_value())', 'E_EVALUATION_ORDER', routines=routine)

    def test_unsupported_math_names_stay_explicit(self):
        self.rejected('r = LOG10(0.0)', 'E_CALL')


if __name__ == '__main__': unittest.main()
