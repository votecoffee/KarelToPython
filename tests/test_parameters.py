"""Behavioral tests for reference identity, aliasing and value temporaries."""
from pathlib import Path
import unittest

from karel2py import translate
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from karel2py.runtime import KarelRuntimeError


def compile_program(body, routines, declarations='x,y,result: INTEGER\nflag: BOOLEAN\na,z: ARRAY[3] OF INTEGER', constants='', *, _translator=translate):
    source = f'PROGRAM T\n{constants}\nVAR\n{declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    generated = _translator(source)
    namespace = {'__name__': 'generated_parameter_test'}
    exec(generated.python_source, namespace)
    return namespace['Program'](), generated


def execute(body, routines, **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


TRIPLE = 'ROUTINE triple(p: INTEGER) BEGIN p = p * 3 END triple'


class ParameterBehaviorTests(unittest.TestCase):
    def test_bare_variable_updates_caller(self):
        self.assertEqual(execute('x = 5\ntriple(x)', TRIPLE)['X'], 15)

    def test_parenthesized_variable_does_not_update_caller(self):
        self.assertEqual(execute('x = 5\ntriple((x))', TRIPLE)['X'], 5)

    def test_extra_parentheses_stay_by_value(self):
        self.assertEqual(execute('x = 5\ntriple((((x))))', TRIPLE)['X'], 5)

    def test_expression_argument_does_not_update_caller(self):
        self.assertEqual(execute('x = 5\ntriple(x + 1)', TRIPLE)['X'], 5)

    def test_literal_and_constant_temporaries(self):
        state = execute('triple(5)\ntriple(C)\nresult = C', TRIPLE, constants='CONST C = 5')
        self.assertEqual(state['RESULT'], 5)

    def test_parenthesized_constant_temporaries(self):
        self.assertEqual(execute('triple((C))\nresult = C', TRIPLE, constants='CONST C = 5')['RESULT'], 5)

    def test_uninitialized_reference_can_be_output(self):
        routine = 'ROUTINE init(p: INTEGER) BEGIN flag = UNINIT(p) p = 7 END init'
        state = execute('init(x)', routine)
        self.assertTrue(state['FLAG'])
        self.assertEqual(state['X'], 7)

    def test_uninitialized_by_value_fails_before_call(self):
        p, _ = compile_program('triple((x))', TRIPLE)
        with self.assertRaisesRegex(KarelRuntimeError, 'uninitialized'): p.run()
        self.assertEqual(p._state.call_depth, 0)

    def test_aliases_share_storage_during_call(self):
        routine = 'ROUTINE alias(first,second: INTEGER) BEGIN first = 7 result = second second = 9 END alias'
        state = execute('x = 1\nalias(x,x)', routine)
        self.assertEqual((state['X'], state['RESULT']), (9, 7))

    def test_reference_and_value_from_same_variable_are_distinct(self):
        routine = 'ROUTINE alias(first,second: INTEGER) BEGIN first = 7 result = second second = 9 END alias'
        state = execute('x = 1\nalias(x,(x))', routine)
        self.assertEqual((state['X'], state['RESULT']), (7, 1))

    def test_nested_forwarding_preserves_reference(self):
        wrapper = 'ROUTINE forward(p: INTEGER) BEGIN triple(p) END forward'
        self.assertEqual(execute('x = 2\nforward(x)', TRIPLE + '\n' + wrapper)['X'], 6)

    def test_nested_parenthesized_forwarding_copies(self):
        wrapper = 'ROUTINE forward(p: INTEGER) BEGIN triple((p)) END forward'
        self.assertEqual(execute('x = 2\nforward(x)', TRIPLE + '\n' + wrapper)['X'], 2)

    def test_nested_value_parameter_forwarded_by_reference_is_private(self):
        wrapper = 'ROUTINE forward(p: INTEGER) BEGIN triple(p) result = p END forward'
        state = execute('x = 2\nforward((x))', TRIPLE + '\n' + wrapper)
        self.assertEqual((state['X'], state['RESULT']), (2, 6))

    def test_caller_local_remains_bound_across_callee_frame(self):
        wrapper = 'ROUTINE wrapper\nVAR local: INTEGER\nBEGIN local = 2 triple(local) result = local END wrapper'
        self.assertEqual(execute('wrapper', TRIPLE + '\n' + wrapper)['RESULT'], 6)

    def test_parameter_shadows_global_and_restores_scope(self):
        routine = 'ROUTINE r(x: INTEGER) BEGIN x = 7 END r'
        state = execute('x = 1 y = 2 r(y)', routine)
        self.assertEqual((state['X'], state['Y']), (1, 7))

    def test_array_element_by_reference(self):
        self.assertEqual(execute('a[1] = 2 triple(a[1])', TRIPLE)['A'][0], 6)

    def test_array_element_by_value(self):
        self.assertEqual(execute('a[1] = 2 triple((a[1]))', TRIPLE)['A'][0], 2)

    def test_array_reference_can_initialize_element(self):
        routine = 'ROUTINE init(p: INTEGER) BEGIN p = 7 END init'
        self.assertEqual(execute('init(a[1])', routine)['A'][0], 7)

    def test_array_index_is_captured_once(self):
        routine = 'ROUTINE r(p: INTEGER) BEGIN x = 2 p = 9 END r'
        state = execute('x = 1 a[1] = 3 a[2] = 4 r(a[x])', routine)
        self.assertEqual(state['A'][:2], [9, 4])

    def test_element_alias_survives_whole_array_assignment(self):
        routine = 'ROUTINE r(p: INTEGER) BEGIN a = z result = p p = 9 END r'
        state = execute('a[1] = 1 a[2] = 2 a[3] = 3 z[1] = 4 z[2] = 5 z[3] = 6 r(a[1])', routine)
        self.assertEqual(state['RESULT'], 4)
        self.assertEqual(state['A'], [9, 5, 6])

    def test_two_references_to_same_array_element_alias(self):
        routine = 'ROUTINE alias(p,q: INTEGER) BEGIN p = 7 result = q q = 9 END alias'
        state = execute('a[1] = 1 alias(a[1],a[1])', routine)
        self.assertEqual((state['A'][0], state['RESULT']), (9, 7))

    def test_boolean_output_parameter(self):
        routine = 'ROUTINE set_flag(p: BOOLEAN) BEGIN p = TRUE END set_flag'
        self.assertTrue(execute('set_flag(flag)', routine)['FLAG'])

    def test_boolean_value_parameter_is_independent(self):
        routine = 'ROUTINE set_flag(p: BOOLEAN) BEGIN p = TRUE END set_flag'
        self.assertFalse(execute('flag = FALSE set_flag((flag))', routine)['FLAG'])

    def test_grouped_parameter_names_and_typed_groups(self):
        routine = 'ROUTINE calc(p,q: INTEGER; ready: BOOLEAN) BEGIN p = p + q ready = TRUE END calc'
        state = execute('x = 2 y = 3 calc(x,y,flag)', routine)
        self.assertEqual(state['X'], 5)
        self.assertTrue(state['FLAG'])

    def test_parameterized_function_returns_and_writes_reference(self):
        routine = 'ROUTINE f(p: INTEGER): INTEGER BEGIN p = p + 1 RETURN p * 2 END f'
        state = execute('x = 2 result = f(x)', routine)
        self.assertEqual((state['X'], state['RESULT']), (3, 6))

    def test_nested_single_argument_function_call(self):
        routine = 'ROUTINE f(p: INTEGER): INTEGER BEGIN RETURN p + 1 END f'
        self.assertEqual(execute('result = f(f(2))', routine)['RESULT'], 4)

    def test_factorial_value_expression_recursion(self):
        routine = 'ROUTINE factorial(n: INTEGER): INTEGER BEGIN IF n = 0 THEN RETURN 1 ELSE RETURN n * factorial(n - 1) ENDIF END factorial'
        state = execute('x = 5 result = factorial(x)', routine)
        self.assertEqual((state['X'], state['RESULT']), (5, 120))

    def test_reference_mutations_persist_after_exception(self):
        routine = 'ROUTINE fail(p: INTEGER) BEGIN p = 9 y = 1 DIV 0 END fail'
        p, _ = compile_program('x = 1 fail(x)', routine)
        with self.assertRaises(KarelRuntimeError): p.run()
        self.assertEqual(p._state.get('X'), 9)
        self.assertEqual(p._state.local_frames, [])

    def test_semicolon_statement_and_declaration_separators(self):
        routine = 'ROUTINE r(p: INTEGER) BEGIN p = p + 1; RETURN; END r'
        state = execute('x = 1; r(x); y = 3;', routine, declarations='x: INTEGER; y: INTEGER')
        self.assertEqual((state['X'], state['Y']), (2, 3))

    def test_grouped_minimum_integer(self):
        self.assertEqual(execute('x = (MININT) triple(0)', TRIPLE)['X'], -2147483648)

    def test_parameterized_routine_local_for_counter(self):
        routine = 'ROUTINE accumulate(p: INTEGER) VAR i: INTEGER BEGIN FOR i = 1 TO 3 DO p = p + i ENDFOR END accumulate'
        self.assertEqual(execute('x = 0 accumulate(x)', routine)['X'], 6)

    def test_pure_recursive_effect_report(self):
        routine = 'ROUTINE f(n: INTEGER): INTEGER BEGIN IF n = 0 THEN RETURN 1 ELSE RETURN n * f(n - 1) ENDIF END f'
        _, result = compile_program('result = f(4)', routine)
        self.assertFalse(result.report['routine_effects']['F']['potential_external_writes'])

    def test_parameter_example(self):
        root = Path(__file__).resolve().parents[1]
        result = translate((root / 'examples/parameters.kl').read_text())
        namespace = {'__name__': 'example'}
        exec(result.python_source, namespace)
        state = namespace['Program']().run()
        self.assertEqual(state['AFTER_VALUE'], 5)
        self.assertEqual(state['ARGUMENT'], 9)
        self.assertEqual(state['FACTORIAL_RESULT'], 120)
        self.assertEqual(state['VALUES'][0], 6)
        self.assertTrue(state['SAME_STORAGE'])


class ParameterRejectionTests(unittest.TestCase):
    def rejected(self, body, routine, expected, **kwargs):
        with self.assertRaises(TranslationError) as caught:
            compile_program(body, routine, **kwargs)
        self.assertEqual(caught.exception.code, expected, str(caught.exception))

    def test_wrong_arity(self):
        for call in ('triple()', 'triple(x,y)', 'triple'):
            with self.subTest(call=call): self.rejected(call, TRIPLE, 'E_ARGUMENTS')

    def test_wrong_reference_type(self):
        self.rejected('triple(flag)', TRIPLE, 'E_TYPE')

    def test_wrong_value_type(self):
        self.rejected('triple(TRUE)', TRIPLE, 'E_TYPE')

    def test_duplicate_parameter_names(self):
        self.rejected('', 'ROUTINE r(p,p: INTEGER) BEGIN END r', 'E_DUPLICATE')

    def test_local_parameter_name_collision(self):
        self.rejected('', 'ROUTINE r(p: INTEGER) VAR p: INTEGER BEGIN END r', 'E_DUPLICATE')

    def test_unsupported_formal_parameter_forms_remain_blocked(self):
        for spec in ('STRING[10]', 'ARRAY[3] OF INTEGER', 'ARRAY OF STRING[4]', 'ARRAY OF ARRAY OF INTEGER', 'FILE'):
            with self.subTest(spec=spec):
                self.rejected('', f'ROUTINE r(p: {spec}) BEGIN END r', 'E_PARAMETERS')

    def test_whole_array_actual_is_not_scalar(self):
        self.rejected('triple(a)', TRIPLE, 'E_TYPE')

    def test_multiargument_side_effect_order_remains_blocked(self):
        routines = 'ROUTINE f: INTEGER BEGIN x = x + 1 RETURN x END f\nROUTINE r(p,q: INTEGER) BEGIN END r'
        self.rejected('x = 1 r(x,f())', routines, 'E_EVALUATION_ORDER', _translator=legacy_translate)

    def test_double_parenthesis_uninit_not_treated_as_reference(self):
        self.rejected('flag = UNINIT((x))', '', 'E_ARGUMENTS')

    def test_reference_argument_index_out_of_bounds(self):
        p, _ = compile_program('triple(a[0])', TRIPLE)
        with self.assertRaisesRegex(KarelRuntimeError, 'outside'): p.run()
        self.assertEqual(p._state.local_frames, [])

    def test_formal_for_counter_alias_effects_blocked(self):
        self.rejected('x = 1 r(x,x)', 'ROUTINE r(p,q: INTEGER) BEGIN FOR p = 1 TO 2 DO q = 9 ENDFOR END r', 'E_FOR_COUNTER')

    def test_global_for_counter_in_parameterized_routine_blocked(self):
        self.rejected('x = 1 r(x)', 'ROUTINE r(p: INTEGER) BEGIN FOR x = 1 TO 2 DO p = 9 ENDFOR END r', 'E_FOR_COUNTER')

    def test_side_effect_function_in_binary_expression_blocked(self):
        routine = 'ROUTINE f(p: INTEGER): INTEGER BEGIN p = p + 1 RETURN p END f'
        self.rejected('x = 1 result = x + f(x)', routine, 'E_EVALUATION_ORDER', _translator=legacy_translate)

    def test_indirect_side_effects_propagate(self):
        routines = 'ROUTINE change BEGIN x = x + 1 END change\nROUTINE f: INTEGER BEGIN change RETURN x END f'
        self.rejected('x = 1 result = x + f()', routines, 'E_EVALUATION_ORDER', _translator=legacy_translate)

    def test_assignment_index_routine_call_blocked(self):
        routine = 'ROUTINE idx: INTEGER BEGIN RETURN 1 END idx'
        self.rejected('a[idx()] = 5', routine, 'E_EVALUATION_ORDER', _translator=legacy_translate)


if __name__ == '__main__': unittest.main()
