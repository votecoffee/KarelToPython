"""Predefined values, INTEGER storage boundaries and source migration controls."""
from pathlib import Path
import unittest

from karel2py import translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


def compile_program(body, declarations='x,y: INTEGER a: ARRAY[2] OF INTEGER b,c: BOOLEAN r: REAL', routines='', constants='', types=''):
    source = f'PROGRAM test\n{constants}\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND test'
    result = translate(source, filename='predefined.kl')
    namespace = {'__name__': 'predefined_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, **kwargs):
    return compile_program(body, **kwargs)[0].run()


class PredefinedValueTests(unittest.TestCase):
    def test_on_off_are_booleans(self):
        state = execute('b = ON c = OFF')
        self.assertIs(state['B'], True)
        self.assertIs(state['C'], False)

    def test_on_off_comparisons_and_eager_operators(self):
        state = execute('b = ON = TRUE c = (ON AND NOT OFF) OR OFF')
        self.assertEqual((state['B'], state['C']), (True, True))

    def test_minint_and_largest_storable_integer(self):
        state = execute('x = MININT y = MAXINT - 1')
        self.assertEqual((state['X'], state['Y']), (-2147483648, 2147483646))

    def test_maxint_is_a_usable_expression_value(self):
        state = execute('b = MAXINT > 2147483646 x = MAXINT DIV 2 y = MAXINT MOD 2')
        self.assertEqual((state['B'], state['X'], state['Y']), (True, 1073741823, 1))

    def test_constants_alias_each_predefined_type(self):
        state = execute('x = lower y = upper - 1 b = yes c = no', constants='CONST lower = MININT upper = MAXINT yes = ON no = OFF')
        self.assertEqual((state['X'], state['Y'], state['B'], state['C']), (-2147483648, 2147483646, True, False))

    def test_constant_arithmetic_retains_signed_range(self):
        state = execute('x = cap y = floor', constants='CONST cap = MAXINT - 1 floor = MININT + 1')
        self.assertEqual((state['X'], state['Y']), (2147483646, -2147483647))

    def test_small_constant_array_size(self):
        state = execute('table[1] = MININT table[2] = MAXINT - 1', declarations='table: ARRAY[MAXINT MOD 2 + 1] OF INTEGER')
        self.assertEqual(state['TABLE'], [-2147483648, 2147483646])

    def test_case_insensitive_spelling(self):
        state = execute('x = mInInT y = mAxInT - 1 b = oN c = oFf')
        self.assertEqual((state['X'], state['Y'], state['B'], state['C']), (-2147483648, 2147483646, True, False))

    def test_predefined_values_in_control_flow(self):
        self.assertEqual(execute('x = 0 IF ON THEN x = 1 ENDIF WHILE OFF DO x = 2 ENDWHILE REPEAT x = x + 1 UNTIL ON')['X'], 2)

    def test_integer_select_case_constants(self):
        self.assertEqual(execute('SELECT MININT OF CASE(MININT): x = 7 ELSE: x = 0 ENDSELECT')['X'], 7)

    def test_select_can_compare_maxint_without_storing_it(self):
        self.assertEqual(execute('SELECT MAXINT OF CASE(MAXINT): x = 7 ELSE: x = 0 ENDSELECT')['X'], 7)

    def test_largest_storable_for_bound_completes_and_clears_counter(self):
        state = execute('y = 0 FOR x = MAXINT - 1 TO MAXINT - 1 DO y = y + 1 ENDFOR b = UNINIT(x)')
        self.assertEqual((state['Y'], state['B']), (1, True))

    def test_minimum_downward_for_bound_completes_and_clears_counter(self):
        state = execute('y = 0 FOR x = MININT DOWNTO MININT DO y = y + 1 ENDFOR b = UNINIT(x)')
        self.assertEqual((state['Y'], state['B']), (1, True))

    def test_literal_names_in_comments_and_strings_are_unchanged(self):
        _, result = compile_program("s = 'MININT MAXINT ON OFF' -- MAXINT\nx = 7", declarations='s: STRING[32] x: INTEGER')
        self.assertEqual(result.report['predefined_uses'], [])

    def test_names_containing_predefined_spelling_remain_ordinary(self):
        self.assertEqual(execute('on_count = 7', declarations='on_count: INTEGER')['ON_COUNT'], 7)

    def test_minint_to_real_is_exact_value_promotion(self):
        self.assertEqual(execute('r = MININT')['R'], -2147483648.0)

    def test_boolean_value_arguments_have_independent_storage(self):
        routine = 'ROUTINE change(flag: BOOLEAN) BEGIN flag = OFF END change'
        self.assertEqual(execute('change(ON) b = ON', routines=routine)['B'], True)

    def test_minint_value_argument_does_not_change_constant(self):
        routine = 'ROUTINE change(n: INTEGER) BEGIN n = 7 END change'
        self.assertEqual(execute('change(MININT) x = MININT', routines=routine)['X'], -2147483648)

    def test_minint_reference_and_value_bindings_still_differ(self):
        routine = 'ROUTINE change(n: INTEGER) BEGIN n = 7 END change'
        state = execute('x = MININT change((x)) y = x change(x)', routines=routine)
        self.assertEqual((state['X'], state['Y']), (7, -2147483648))

    def test_minint_function_return(self):
        routine = 'ROUTINE lower: INTEGER BEGIN RETURN MININT END lower'
        self.assertEqual(execute('x = lower()', routines=routine)['X'], -2147483648)

    def test_boolean_function_return(self):
        routine = 'ROUTINE enabled: BOOLEAN BEGIN RETURN ON END enabled'
        self.assertIs(execute('b = enabled()', routines=routine)['B'], True)

    def test_report_records_constant_declaration_and_operand_locations(self):
        _, result = compile_program('x = MININT b = ON', constants='CONST bound = MAXINT')
        self.assertEqual([row['name'] for row in result.report['predefined_uses']], ['MAXINT', 'MININT', 'ON'])
        self.assertTrue(all(row['line'] > 0 and row['column'] > 0 for row in result.report['predefined_uses']))
        self.assertEqual(result.report['predefined_constants']['MININT'], dict(value=-2147483648, type='INTEGER'))
        self.assertEqual(result.report['predefined_constants']['ON'], dict(value=True, type='BOOLEAN'))
        self.assertEqual(result.report['integer_policy']['storage_range'], [-2147483648, 2147483646])
        self.assertIn('predefined MAXINT', result.report['features'])
        self.assertFalse(result.report['integer_policy']['controller_validated'])

    def test_example_complete_snapshot(self):
        source = (Path(__file__).resolve().parents[1] / 'examples/predefined_constants.kl').read_text(encoding='utf-8')
        result = translate(source)
        namespace = {'__name__': 'predefined_example'}
        exec(result.python_source, namespace)
        self.assertEqual(namespace['Program']().run(), dict(
            LOWEST=-2147483648, HIGHEST=2147483646, VALUES=[-2147483648, 2147483646], ENABLED=True,
            DISABLED=False, COPIED_FLAG=True, MINIMUM_AS_REAL=-2147483648.0,
            PACKET=dict(COUNT=-2147483647, READY=True), BEFORE_CHANGE=-2147483648, AFTER_CHANGE=7))


class IntegerStorageBoundaryTests(unittest.TestCase):
    def fail_storage(self, body, **kwargs):
        program, _ = compile_program(body, **kwargs)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'storage excludes MAXINT') as caught:
            program.run()
        self.assertIsNotNone(caught.exception.line)
        return program

    def test_global_maxint_store_preserves_previous_value(self):
        self.assertEqual(self.fail_storage('x = 7 x = MAXINT')._state.snapshot()['X'], 7)

    def test_numeric_maxint_store_is_also_blocked(self):
        self.assertEqual(self.fail_storage('x = 7 x = 2147483647')._state.snapshot()['X'], 7)

    def test_maxint_alias_constant_store_is_blocked(self):
        self.assertEqual(self.fail_storage('x = 7 x = upper', constants='CONST upper = MAXINT')._state.snapshot()['X'], 7)

    def test_expression_maxint_result_store_is_blocked(self):
        self.assertEqual(self.fail_storage('x = 7 x = 2147483646 + 1')._state.snapshot()['X'], 7)

    def test_array_store_preserves_other_elements(self):
        self.assertEqual(self.fail_storage('a[1] = 7 a[2] = MININT a[1] = MAXINT')._state.snapshot()['A'], [7, -2147483648])

    def test_structure_field_and_using_store_preserve_previous_value(self):
        types = 'TYPE packet_t = STRUCTURE count: INTEGER ENDSTRUCTURE'
        for body in ('p.count = MAXINT', 'USING p DO count = MAXINT ENDUSING'):
            with self.subTest(body=body):
                program = self.fail_storage('p.count = 7 ' + body, types=types, declarations='p: packet_t')
                self.assertEqual(program._state.snapshot()['P']['COUNT'], 7)

    def test_local_store_cleans_up_routine_frame(self):
        routine = 'ROUTINE run VAR local: INTEGER BEGIN x = 7 local = MAXINT END run'
        program = self.fail_storage('run', routines=routine)
        self.assertEqual((program._state.snapshot()['X'], program._state.local_frames, program._state.call_depth), (7, [], 0))

    def test_reference_formal_write_preserves_caller_storage(self):
        routine = 'ROUTINE change(n: INTEGER) BEGIN n = MAXINT END change'
        program = self.fail_storage('x = 7 change(x)', routines=routine)
        self.assertEqual((program._state.snapshot()['X'], program._state.local_frames), (7, []))

    def test_maxint_value_parameter_fails_before_callee_runs(self):
        routine = 'ROUTINE change(n: INTEGER) BEGIN x = 99 END change'
        program = self.fail_storage('x = 7 change(MAXINT)', routines=routine)
        self.assertEqual((program._state.snapshot()['X'], program._state.local_frames), (7, []))

    def test_maxint_function_result_uses_conservative_storage_guard(self):
        routine = 'ROUTINE upper: INTEGER BEGIN y = 9 RETURN MAXINT END upper'
        program = self.fail_storage('x = 7 x = upper()', routines=routine)
        self.assertEqual((program._state.snapshot()['X'], program._state.snapshot()['Y'], program._state.local_frames), (7, 9, []))

    def test_for_counter_cannot_be_initialized_to_maxint(self):
        self.assertEqual(self.fail_storage('x = 7 FOR x = MAXINT TO MAXINT DO y = 9 ENDFOR')._state.snapshot()['X'], 7)

    def test_maxint_is_not_reinterpreted_as_uninitialized(self):
        program = self.fail_storage('x = 7 x = MAXINT b = UNINIT(x)')
        self.assertIs(program._state.snapshot()['B'].get('uninitialized'), True)
        self.assertFalse(rt.uninit(program._state.values['X']))

    def test_arithmetic_reaching_minint_is_storable(self):
        self.assertEqual(execute('x = -2147483647 - 1')['X'], -2147483648)

    def test_maxint_final_for_bound_preserves_prior_body_writes_on_error(self):
        program = self.fail_storage('y = 0 FOR x = MAXINT - 1 TO MAXINT DO y = y + 1 ENDFOR')
        self.assertEqual((program._state.snapshot()['X'], program._state.snapshot()['Y']), (2147483646, 1))

    def test_direct_runtime_boundary_guard(self):
        self.assertEqual(rt.integer(2147483647), 2147483647)
        self.assertEqual(rt.checked(rt.INTEGER, -2147483648), -2147483648)
        self.assertEqual(rt.checked(rt.INTEGER, 2147483646), 2147483646)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'storage excludes MAXINT'):
            rt.checked(rt.INTEGER, 2147483647)

    def test_maxint_plus_one_and_negative_minint_still_overflow(self):
        for expression in ('MAXINT + 1', '-MININT', 'ABS(MININT)'):
            with self.subTest(expression=expression):
                program, _ = compile_program('x = 7 x = ' + expression)
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'INTEGER overflow'): program.run()
                self.assertEqual(program._state.snapshot()['X'], 7)


class PredefinedRejectionTests(unittest.TestCase):
    def reject(self, body, code, **kwargs):
        with self.assertRaises(TranslationError) as caught:
            compile_program(body, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_bare_grouped_and_constant_minimum_integer_literals_rejected(self):
        for expression in ('-2147483648', '-(2147483648)', '-((2147483648))'):
            with self.subTest(expression=expression):
                self.reject('x = ' + expression, 'E_MININT_LITERAL')
                self.reject('x = low', 'E_MININT_LITERAL', constants='CONST low = ' + expression)

    def test_minimum_literal_error_preserves_physical_location(self):
        error = self.reject('x = &\n -2147483648', 'E_MININT_LITERAL')
        self.assertEqual((error.token.column, error.message.startswith('The manual requires MININT')), (2, True))

    def test_predefined_declarations_are_explicitly_blocked(self):
        for name in ('ON', 'OFF', 'MAXINT', 'MININT'):
            with self.subTest(name=name):
                self.reject('', 'E_PREDEFINED_NAME', declarations=name + ': INTEGER')
                self.reject('', 'E_PREDEFINED_NAME', constants='CONST ' + name + ' = 7')
                self.reject('', 'E_PREDEFINED_NAME', routines='ROUTINE ' + name + ' BEGIN END ' + name)
                self.reject('', 'E_PREDEFINED_NAME', types='TYPE p = STRUCTURE ' + name + ': INTEGER ENDSTRUCTURE')

    def test_local_and_formal_redefinitions_are_blocked(self):
        self.reject('', 'E_PREDEFINED_NAME', routines='ROUTINE r VAR ON: BOOLEAN BEGIN END r')
        self.reject('', 'E_PREDEFINED_NAME', routines='ROUTINE r(OFF: BOOLEAN) BEGIN END r')

    def test_predefined_type_names_are_blocked(self):
        self.reject('', 'E_TYPE', declarations='x: MAXINT')
        self.reject('', 'E_PARAMETERS', routines='ROUTINE r(x: MAXINT) BEGIN END r')

    def test_write_call_index_and_field_contexts_are_blocked(self):
        for source in ('MAXINT = 7', 'ON()', 'MININT[1] = 7', 'OFF.x = 7'):
            with self.subTest(source=source): self.reject(source, 'E_PREDEFINED_TARGET')
        for expression in ('MAXINT()', 'MININT[1]', 'ON.x'):
            with self.subTest(expression=expression): self.reject('x = ' + expression, 'E_PREDEFINED_CONTEXT')

    def test_labels_and_jump_targets_cannot_use_predefined_names(self):
        self.reject('ON:: x = 7', 'E_LABEL_NAME')
        self.reject('GOTO MAXINT', 'E_LABEL_NAME')

    def test_constants_are_not_uninit_storage(self):
        for name in ('ON', 'OFF', 'MININT', 'MAXINT'):
            with self.subTest(name=name): self.reject('b = UNINIT(' + name + ')', 'E_ARGUMENTS')

    def test_boolean_integer_types_remain_distinct(self):
        self.reject('x = ON', 'E_TYPE')
        self.reject('b = MININT', 'E_TYPE')

    def test_controller_identifiers_are_not_enabled_by_on_off(self):
        self.reject('b = DIN[1] = ON', 'E_CONTROLLER')
        self.reject('x = LINEAR', 'E_SYMBOL')


if __name__ == '__main__': unittest.main()
