"""Early routine exits and calls with isolated, non-escaping FOR counters."""
import unittest

from karel2py import translate
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from karel2py.runtime import KarelRuntimeError


DECLARATIONS = '''
i,j,total,result,visits,seen: INTEGER
flag,found: BOOLEAN
measurement: REAL
a: ARRAY[4] OF INTEGER
words: ARRAY[2] OF STRING[3]
'''


def compile_program(body, routines, declarations=DECLARATIONS, *, _translator=translate):
    result = _translator(f'PROGRAM T\nVAR\n{declarations}\n{routines}\nBEGIN\n{body}\nEND T', filename='for_routines.kl')
    namespace = {'__name__': 'for_routine_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, routines, **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


class ForReturnTests(unittest.TestCase):
    def test_manual_search_pattern_returns_first_zero_index(self):
        routine = 'ROUTINE index_value(table: ARRAY OF INTEGER; table_size: INTEGER): INTEGER VAR k: INTEGER BEGIN FOR k = 1 TO table_size DO IF table[k] = 0 THEN RETURN k ENDIF ENDFOR RETURN 0 END index_value'
        state = execute('a[1] = 7 a[2] = 0 result = index_value(a,4)', routine)
        self.assertEqual(state['RESULT'], 2)

    def test_search_return_skips_uninitialized_later_elements(self):
        routine = 'ROUTINE search(table: ARRAY OF INTEGER): INTEGER VAR k: INTEGER BEGIN FOR k = 1 TO ARRAY_LEN(table) DO IF table[k] = 0 THEN RETURN k ENDIF ENDFOR RETURN 0 END search'
        self.assertEqual(execute('a[1] = 0 result = search(a)', routine)['RESULT'], 1)

    def test_search_without_match_returns_zero_and_clears_counter(self):
        routine = 'ROUTINE search(table: ARRAY OF INTEGER): INTEGER VAR k: INTEGER BEGIN FOR k = 1 TO ARRAY_LEN(table) DO IF table[k] = 0 THEN RETURN k ENDIF ENDFOR flag = UNINIT(k) RETURN 0 END search'
        state = execute('a[1] = 1 a[2] = 2 a[3] = 3 a[4] = 4 result = search(a)', routine)
        self.assertEqual((state['RESULT'], state['FLAG']), (0, True))

    def test_zero_iteration_loop_does_not_return_from_body(self):
        routine = 'ROUTINE search: INTEGER VAR k: INTEGER BEGIN FOR k = 3 TO 1 DO RETURN k ENDFOR flag = UNINIT(k) RETURN 9 END search'
        state = execute('result = search()', routine)
        self.assertEqual((state['RESULT'], state['FLAG']), (9, True))

    def test_downward_loop_early_return(self):
        routine = 'ROUTINE search: INTEGER VAR k: INTEGER BEGIN FOR k = 4 DOWNTO 1 DO IF k = 2 THEN RETURN k ENDIF ENDFOR RETURN 0 END search'
        self.assertEqual(execute('result = search()', routine)['RESULT'], 2)

    def test_return_from_nested_for_counters(self):
        routine = 'ROUTINE search: INTEGER VAR outer_k,inner_k: INTEGER BEGIN FOR outer_k = 1 TO 3 DO FOR inner_k = 1 TO 3 DO IF inner_k = 2 THEN RETURN outer_k * 10 + inner_k ENDIF ENDFOR ENDFOR RETURN 0 END search'
        self.assertEqual(execute('result = search()', routine)['RESULT'], 12)

    def test_return_from_select_in_for(self):
        routine = 'ROUTINE search: INTEGER VAR k: INTEGER BEGIN FOR k = 1 TO 3 DO SELECT k OF CASE(2): RETURN k ELSE: ENDSELECT ENDFOR RETURN 0 END search'
        self.assertEqual(execute('result = search()', routine)['RESULT'], 2)

    def test_return_from_while_in_for(self):
        routine = 'ROUTINE search: INTEGER VAR k: INTEGER BEGIN FOR k = 1 TO 3 DO WHILE TRUE DO RETURN k ENDWHILE ENDFOR RETURN 0 END search'
        self.assertEqual(execute('result = search()', routine)['RESULT'], 1)

    def test_return_from_repeat_in_for_skips_pending_condition(self):
        routine = 'ROUTINE search: INTEGER VAR k: INTEGER BEGIN FOR k = 1 TO 3 DO REPEAT RETURN k UNTIL flag ENDFOR RETURN 0 END search'
        self.assertEqual(execute('result = search()', routine)['RESULT'], 1)

    def test_procedure_return_keeps_reference_writes_and_unwinds(self):
        routine = 'ROUTINE search(table: ARRAY OF INTEGER) VAR k: INTEGER BEGIN FOR k = 1 TO ARRAY_LEN(table) DO table[k] = 7 RETURN ENDFOR table[4] = 9 END search'
        p, _ = compile_program('search(a)', routine)
        state = p.run()
        self.assertEqual(state['A'], [7] + [{'uninitialized': True}] * 3)
        self.assertEqual((p._state.local_frames, p._state.call_depth), ([], 0))

    def test_return_value_reads_counter_before_local_frame_destroyed(self):
        routine = 'ROUTINE first: INTEGER VAR k: INTEGER BEGIN FOR k = 2 TO 3 DO RETURN k ENDFOR RETURN 0 END first'
        p, _ = compile_program('result = first()', routine)
        self.assertEqual(p.run()['RESULT'], 2)
        self.assertNotIn('K', p._state.values)

    def test_real_return_from_integer_counter_uses_checked_promotion(self):
        routine = 'ROUTINE first: REAL VAR k: INTEGER BEGIN FOR k = 2 TO 3 DO RETURN k ENDFOR RETURN 0 END first'
        self.assertEqual(execute('measurement = first()', routine)['MEASUREMENT'], 2.0)

    def test_boolean_return_from_for(self):
        routine = 'ROUTINE search: BOOLEAN VAR k: INTEGER BEGIN FOR k = 1 TO 3 DO RETURN k = 1 ENDFOR RETURN FALSE END search'
        self.assertTrue(execute('found = search()', routine)['FOUND'])

    def test_labelled_routine_preserves_early_for_return(self):
        routine = 'ROUTINE first: INTEGER VAR k: INTEGER BEGIN GOTO work work:: FOR k = 1 TO 3 DO RETURN k ENDFOR RETURN 0 END first'
        self.assertEqual(execute('result = first()', routine)['RESULT'], 1)

    def test_early_return_local_counter_does_not_change_shadowed_global(self):
        routine = 'ROUTINE first: INTEGER VAR i: INTEGER BEGIN FOR i = 1 TO 3 DO RETURN i ENDFOR RETURN 0 END first'
        state = execute('i = 99 result = first()', routine)
        self.assertEqual((state['I'], state['RESULT']), (99, 1))

    def test_repeated_calls_recreate_local_counters(self):
        routine = 'ROUTINE first: INTEGER VAR k: INTEGER BEGIN flag = UNINIT(k) FOR k = 1 TO 3 DO RETURN k ENDFOR RETURN 0 END first'
        state = execute('result = first() seen = first()', routine)
        self.assertEqual((state['RESULT'], state['SEEN'], state['FLAG']), (1, 1, True))


class ForCallTests(unittest.TestCase):
    def test_parenthesized_counter_passes_independent_value(self):
        routines = 'ROUTINE change(p: INTEGER) BEGIN total = total + p p = 99 END change\nROUTINE work VAR k: INTEGER BEGIN FOR k = 1 TO 3 DO change((k)) ENDFOR flag = UNINIT(k) END work'
        state = execute('total = 0 work', routines)
        self.assertEqual((state['TOTAL'], state['FLAG']), (6, True))

    def test_counter_expression_is_value_argument(self):
        routines = 'ROUTINE change(p: INTEGER) BEGIN total = total + p p = 99 END change\nROUTINE work VAR k: INTEGER BEGIN FOR k = 1 TO 3 DO change(k + 10) ENDFOR END work'
        self.assertEqual(execute('total = 0 work', routines)['TOTAL'], 36)

    def test_integer_counter_to_real_formal_is_value_argument(self):
        routines = 'ROUTINE change(p: REAL) BEGIN measurement = measurement + p p = 99.0 END change\nROUTINE work VAR k: INTEGER BEGIN FOR k = 1 TO 3 DO change(k) ENDFOR END work'
        self.assertEqual(execute('measurement = 0.0 work', routines)['MEASUREMENT'], 6.0)

    def test_non_counter_scalar_reference_can_be_changed(self):
        routines = 'ROUTINE increment(p: INTEGER) BEGIN p = p + 1 END increment\nROUTINE work(p: INTEGER) VAR k: INTEGER BEGIN FOR k = 1 TO 3 DO increment(p) ENDFOR END work'
        self.assertEqual(execute('total = 0 work(total)', routines)['TOTAL'], 3)

    def test_indexed_argument_uses_current_counter_each_iteration(self):
        routines = 'ROUTINE fill(p: INTEGER) BEGIN p = 7 END fill\nROUTINE work(table: ARRAY OF INTEGER) VAR k: INTEGER BEGIN FOR k = 1 TO ARRAY_LEN(table) DO fill(table[k]) ENDFOR END work'
        self.assertEqual(execute('work(a)', routines)['A'], [7] * 4)

    def test_string_element_reference_can_be_output(self):
        routines = "ROUTINE label(p: STRING) BEGIN p = 'abcdef' END label\nROUTINE work(table: ARRAY OF STRING) VAR k: INTEGER BEGIN FOR k = 1 TO ARRAY_LEN(table) DO label(table[k]) ENDFOR END work"
        self.assertEqual(execute('work(words)', routines)['WORDS'], ['abc', 'abc'])

    def test_helper_function_results_in_for(self):
        routines = 'ROUTINE double(p: INTEGER): INTEGER BEGIN RETURN p * 2 END double\nROUTINE work VAR k: INTEGER BEGIN FOR k = 1 TO 3 DO total = total + double((k)) ENDFOR END work'
        self.assertEqual(execute('total = 0 work', routines)['TOTAL'], 12)

    def test_function_result_uses_local_counter_in_expression(self):
        routines = 'ROUTINE double(p: INTEGER): INTEGER BEGIN RETURN p * 2 END double\nROUTINE work: INTEGER VAR k,sum_value: INTEGER BEGIN sum_value = 0 FOR k = 1 TO 3 DO sum_value = sum_value + double((k)) ENDFOR RETURN sum_value END work'
        self.assertEqual(execute('result = work()', routines)['RESULT'], 12)

    def test_boolean_helper_condition_can_return_from_for(self):
        routines = 'ROUTINE zero(p: INTEGER): BOOLEAN BEGIN RETURN p = 0 END zero\nROUTINE search(table: ARRAY OF INTEGER): INTEGER VAR k: INTEGER BEGIN FOR k = 1 TO ARRAY_LEN(table) DO IF zero(table[k]) THEN RETURN k ENDIF ENDFOR RETURN 0 END search'
        self.assertEqual(execute('a[1] = 7 a[2] = 0 result = search(a)', routines)['RESULT'], 2)

    def test_no_argument_helper_global_writes_do_not_change_local_counter(self):
        routines = 'ROUTINE change BEGIN i = 99 visits = visits + 1 END change\nROUTINE work VAR i: INTEGER BEGIN FOR i = 1 TO 3 DO change ENDFOR END work'
        state = execute('visits = 0 work', routines)
        self.assertEqual((state['I'], state['VISITS']), (99, 3))

    def test_formal_reference_aliasing_shadowed_global_is_separate_from_counter(self):
        routines = 'ROUTINE change(p: INTEGER) BEGIN p = 99 visits = visits + 1 END change\nROUTINE work(p: INTEGER) VAR i: INTEGER BEGIN FOR i = 1 TO 3 DO change(p) ENDFOR END work'
        state = execute('i = 0 visits = 0 work(i)', routines)
        self.assertEqual((state['I'], state['VISITS']), (99, 3))

    def test_nested_local_counters_pass_values_to_two_formals(self):
        routines = 'ROUTINE combine(p,q: INTEGER) BEGIN total = total + p * 10 + q END combine\nROUTINE work VAR first_k,second_k: INTEGER BEGIN FOR first_k = 1 TO 2 DO FOR second_k = 1 TO 2 DO combine((first_k),(second_k)) ENDFOR ENDFOR END work'
        self.assertEqual(execute('total = 0 work', routines)['TOTAL'], 66)

    def test_nested_loop_call_has_independent_callee_counter_with_same_name(self):
        routines = 'ROUTINE inner_work VAR k: INTEGER BEGIN FOR k = 1 TO 2 DO total = total + k ENDFOR END inner_work\nROUTINE outer_work VAR k: INTEGER BEGIN FOR k = 1 TO 3 DO inner_work ENDFOR END outer_work'
        self.assertEqual(execute('total = 0 outer_work', routines)['TOTAL'], 9)

    def test_recursive_function_call_from_for(self):
        routines = 'ROUTINE factorial(n: INTEGER): INTEGER BEGIN IF n <= 1 THEN RETURN 1 ENDIF RETURN n * factorial(n - 1) END factorial\nROUTINE work VAR k: INTEGER BEGIN FOR k = 1 TO 3 DO total = total + factorial((k)) ENDFOR END work'
        self.assertEqual(execute('total = 0 work', routines)['TOTAL'], 9)

    def test_report_records_local_counter_policy(self):
        routines = 'ROUTINE first: INTEGER VAR k: INTEGER BEGIN FOR k = 1 TO 2 DO RETURN k ENDFOR RETURN 0 END first'
        _, result = compile_program('result = first()', routines)
        self.assertFalse(result.report['for_policy']['controller_validated'])
        self.assertIn('RETURN from FOR with fresh local counters', result.report['features'])


class ForFailureTests(unittest.TestCase):
    def test_faulting_helper_unwinds_both_frames_and_keeps_writes(self):
        routines = 'ROUTINE fail(p: INTEGER) BEGIN p = 7 result = 1 DIV 0 END fail\nROUTINE work(table: ARRAY OF INTEGER) VAR k: INTEGER BEGIN FOR k = 1 TO ARRAY_LEN(table) DO fail(table[k]) ENDFOR END work'
        p, _ = compile_program('work(a)', routines)
        with self.assertRaisesRegex(KarelRuntimeError, 'zero'): p.run()
        self.assertEqual(p._state.snapshot()['A'][0], 7)
        self.assertEqual((p._state.local_frames, p._state.call_depth), ([], 0))

    def test_return_read_failure_unwinds_frame(self):
        routine = 'ROUTINE first(table: ARRAY OF INTEGER): INTEGER VAR k: INTEGER BEGIN FOR k = 1 TO ARRAY_LEN(table) DO RETURN table[k] ENDFOR RETURN 0 END first'
        p, _ = compile_program('result = first(a)', routine)
        with self.assertRaisesRegex(KarelRuntimeError, 'uninitialized'): p.run()
        self.assertEqual((p._state.local_frames, p._state.call_depth), ([], 0))

    def test_return_overflow_is_checked_before_escape(self):
        routine = 'ROUTINE first: INTEGER VAR k: INTEGER BEGIN FOR k = 2147483646 TO 2147483646 DO RETURN k + 2 ENDFOR RETURN 0 END first'
        p, _ = compile_program('result = first()', routine)
        with self.assertRaisesRegex(KarelRuntimeError, 'overflow'): p.run()
        self.assertEqual(p._state.local_frames, [])

    def test_step_budget_during_helper_loop_unwinds_frames(self):
        routines = 'ROUTINE count BEGIN visits = visits + 1 END count\nROUTINE work VAR k: INTEGER BEGIN FOR k = 1 TO 100 DO count ENDFOR END work'
        p, _ = compile_program('visits = 0 work', routines)
        with self.assertRaisesRegex(KarelRuntimeError, 'step budget'): p.run(max_steps=12)
        self.assertGreater(p._state.get('VISITS'), 0)
        self.assertEqual((p._state.local_frames, p._state.call_depth), ([], 0))


class ForSafetyBoundaryTests(unittest.TestCase):
    def rejected(self, body, routines, code='E_FOR_COUNTER', **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, routines, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_global_counter_calls_remain_blocked(self):
        self.rejected('FOR i = 1 TO 3 DO helper ENDFOR', 'ROUTINE helper BEGIN END helper', _translator=legacy_translate)

    def test_global_counter_function_calls_remain_blocked(self):
        self.rejected('FOR i = 1 TO 3 DO result = helper() ENDFOR', 'ROUTINE helper: INTEGER BEGIN RETURN 7 END helper', _translator=legacy_translate)

    def test_nonparameter_routine_global_counter_call_blocked(self):
        self.rejected('work', 'ROUTINE helper BEGIN END helper\nROUTINE work BEGIN FOR i = 1 TO 3 DO helper ENDFOR END work', _translator=legacy_translate)

    def test_nonparameter_routine_global_counter_return_blocked(self):
        self.rejected('result = work()', 'ROUTINE work: INTEGER BEGIN FOR i = 1 TO 3 DO RETURN i ENDFOR RETURN 0 END work', _translator=legacy_translate)

    def test_parameter_counter_still_cannot_own_for(self):
        self.rejected('work(i)', 'ROUTINE work(p: INTEGER) BEGIN FOR p = 1 TO 3 DO RETURN ENDFOR END work')

    def test_direct_counter_reference_blocked_even_readonly_helper(self):
        self.rejected('work', 'ROUTINE inspect(p: INTEGER) BEGIN seen = p END inspect\nROUTINE work VAR k: INTEGER BEGIN FOR k = 1 TO 3 DO inspect(k) ENDFOR END work', _translator=legacy_translate)

    def test_counter_reference_to_function_blocked(self):
        self.rejected('result = work()', 'ROUTINE inspect(p: INTEGER): INTEGER BEGIN RETURN p END inspect\nROUTINE work: INTEGER VAR k: INTEGER BEGIN FOR k = 1 TO 3 DO RETURN inspect(k) ENDFOR RETURN 0 END work', _translator=legacy_translate)

    def test_outer_counter_reference_inside_nested_for_blocked(self):
        self.rejected('work', 'ROUTINE change(p: INTEGER) BEGIN p = 99 END change\nROUTINE work VAR first_k,second_k: INTEGER BEGIN FOR first_k = 1 TO 2 DO FOR second_k = 1 TO 2 DO change(first_k) ENDFOR ENDFOR END work')

    def test_global_outer_local_inner_call_blocked(self):
        self.rejected('work', 'ROUTINE helper BEGIN END helper\nROUTINE work VAR k: INTEGER BEGIN FOR i = 1 TO 2 DO FOR k = 1 TO 2 DO helper ENDFOR ENDFOR END work', _translator=legacy_translate)

    def test_global_outer_local_inner_return_blocked(self):
        self.rejected('result = work()', 'ROUTINE work: INTEGER VAR k: INTEGER BEGIN FOR i = 1 TO 2 DO FOR k = 1 TO 2 DO RETURN k ENDFOR ENDFOR RETURN 0 END work', _translator=legacy_translate)

    def test_local_counter_direct_write_still_blocked(self):
        self.rejected('work', 'ROUTINE work VAR k: INTEGER BEGIN FOR k = 1 TO 2 DO k = 99 ENDFOR END work')

    def test_reusing_active_local_counter_for_nested_loop_still_blocked(self):
        self.rejected('work', 'ROUTINE work VAR k: INTEGER BEGIN FOR k = 1 TO 2 DO FOR k = 1 TO 2 DO ENDFOR ENDFOR END work')

    def test_routine_calls_in_for_bounds_still_blocked(self):
        self.rejected('work', 'ROUTINE bound: INTEGER BEGIN RETURN 2 END bound\nROUTINE work VAR k: INTEGER BEGIN FOR k = 1 TO bound() DO ENDFOR END work', 'E_EVALUATION_ORDER', _translator=legacy_translate)

    def test_effectful_function_in_binary_expression_still_blocked(self):
        self.rejected('work', 'ROUTINE helper: INTEGER BEGIN visits = 7 RETURN 1 END helper\nROUTINE work VAR k: INTEGER BEGIN FOR k = 1 TO 2 DO total = total + helper() ENDFOR END work', 'E_EVALUATION_ORDER', _translator=legacy_translate)

    def test_multiple_arguments_containing_routine_calls_still_blocked(self):
        self.rejected('work', 'ROUTINE first: INTEGER BEGIN RETURN 1 END first\nROUTINE helper(p,q: INTEGER) BEGIN END helper\nROUTINE work VAR k: INTEGER BEGIN FOR k = 1 TO 2 DO helper(first(),(k)) ENDFOR END work', 'E_EVALUATION_ORDER', _translator=legacy_translate)

    def test_return_wrong_scalar_type_still_blocked(self):
        self.rejected('result = work()', 'ROUTINE work: INTEGER VAR k: INTEGER BEGIN FOR k = 1 TO 2 DO RETURN TRUE ENDFOR RETURN 0 END work', 'E_RETURN')

    def test_procedure_return_value_still_blocked(self):
        self.rejected('work', 'ROUTINE work VAR k: INTEGER BEGIN FOR k = 1 TO 2 DO RETURN k ENDFOR END work', 'E_RETURN')

    def test_legacy_labels_and_jumps_in_for_still_blocked(self):
        self.rejected('work', 'ROUTINE work VAR k: INTEGER BEGIN FOR k = 1 TO 2 DO GO TO finished ENDFOR finished:: END work', 'E_GOTO_FOR', _translator=legacy_translate)


if __name__ == '__main__': unittest.main()
