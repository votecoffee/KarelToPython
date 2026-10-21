"""Lexical USING aliases, documented field priority and retained flow/effect guards."""
from pathlib import Path
import unittest

from karel2py import translate
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


TYPES = '''TYPE child_t = STRUCTURE
  n: INTEGER
ENDSTRUCTURE
left_t = STRUCTURE
  count: INTEGER
  label: STRING[3]
  slots: ARRAY[2] OF INTEGER
  child: child_t
ENDSTRUCTURE
right_t = STRUCTURE
  count: INTEGER
  ready: BOOLEAN
ENDSTRUCTURE
'''
DECLARATIONS = '''left: left_t right: right_t
count,result,index_value: INTEGER
flag: BOOLEAN
child: child_t
'''


def compile_program(body, routines='', types=TYPES, declarations=DECLARATIONS, constants='', *, _translator=translate):
    result = _translator(f'PROGRAM T\n{constants}\n{types}\nVAR\n{declarations}\n{routines}\nBEGIN\n{body}\nEND T', filename='using.kl')
    namespace = {'__name__': 'using_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, routines='', **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


class UsingResolutionTests(unittest.TestCase):
    def test_field_overrides_global_variable(self):
        state = execute('count = 90 USING left DO count = 7 ENDUSING result = count')
        self.assertEqual((state['LEFT']['COUNT'], state['COUNT'], state['RESULT']), (7, 90, 90))

    def test_constant_name_collision_is_explicitly_blocked(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('USING left DO count = 7 ENDUSING', declarations='left: left_t', constants='CONST count = 90', _translator=legacy_translate)
        self.assertEqual(caught.exception.code, 'E_USING_CONST_SHADOW')

    def test_noncolliding_constant_remains_usable(self):
        self.assertEqual(execute('USING left DO count = limit ENDUSING', constants='CONST limit = 7')['LEFT']['COUNT'], 7)

    def test_explicit_field_path_is_valid_despite_same_named_constant(self):
        state = execute('USING left DO left.count = 7 ENDUSING', declarations='left: left_t', constants='CONST count = 90')
        self.assertEqual(state['LEFT']['COUNT'], 7)

    def test_rightmost_matching_field_wins(self):
        state = execute('left.count = 1 USING left,right DO count = 7 ENDUSING')
        self.assertEqual((state['LEFT']['COUNT'], state['RIGHT']['COUNT']), (1, 7))

    def test_reversing_selector_order_reverses_priority(self):
        state = execute('right.count = 1 USING right,left DO count = 7 ENDUSING')
        self.assertEqual((state['LEFT']['COUNT'], state['RIGHT']['COUNT']), (7, 1))

    def test_no_fallback_when_rightmost_field_is_uninitialized(self):
        program, _ = compile_program('left.count = 7 USING left,right DO result = count ENDUSING')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()

    def test_unmatched_fields_are_resolved_from_other_selector(self):
        state = execute("USING left,right DO label = 'abcdef' ready = TRUE ENDUSING")
        self.assertEqual((state['LEFT']['LABEL'], state['RIGHT']['READY']), ('abc', True))

    def test_ordinary_names_still_use_lexical_declarations(self):
        state = execute('result = 4 USING left DO count = result + 1 ENDUSING')
        self.assertEqual((state['LEFT']['COUNT'], state['RESULT']), (5, 4))

    def test_arrays_and_nested_structure_paths(self):
        state = execute('USING left DO slots[2] = 7 child.n = 8 result = slots[2] + child.n ENDUSING')
        self.assertEqual((state['RESULT'], state['LEFT']['SLOTS'][1], state['CHILD']['N']), (15, 7, {'uninitialized': True}))

    def test_only_direct_fields_are_exposed(self):
        with self.assertRaises(TranslationError) as caught: compile_program('USING left DO result = n ENDUSING')
        self.assertEqual(caught.exception.code, 'E_SYMBOL')

    def test_scalar_uninit_retains_raw_read(self):
        self.assertTrue(execute('USING left DO flag = UNINIT(count) ENDUSING')['FLAG'])

    def test_array_len_retains_aggregate_reference(self):
        self.assertEqual(execute('USING left DO result = ARRAY_LEN(slots) ENDUSING')['RESULT'], 2)

    def test_separate_scopes_do_not_leak_field_bindings(self):
        state = execute('count = 90 USING left DO count = 1 ENDUSING USING right DO count = 2 ENDUSING result = count')
        self.assertEqual((state['LEFT']['COUNT'], state['RIGHT']['COUNT'], state['RESULT']), (1, 2, 90))

    def test_empty_body_is_valid(self):
        self.assertEqual(execute('count = 7 USING left DO ENDUSING result = count')['RESULT'], 7)

    def test_case_insensitive_aliases(self):
        self.assertEqual(execute('uSiNg LeFt DO CoUnT = 7 eNdUsInG')['LEFT']['COUNT'], 7)

    def test_qualified_root_spelling_can_be_shadowed_by_a_structure_field(self):
        types = '''TYPE inner_t = STRUCTURE n: INTEGER ENDSTRUCTURE
outer_t = STRUCTURE item: inner_t ENDSTRUCTURE'''
        state = execute('USING outer DO item.n = 7 ENDUSING', types=types, declarations='outer: outer_t item: inner_t')
        self.assertEqual((state['OUTER']['ITEM']['N'], state['ITEM']['N']), (7, {'uninitialized': True}))

    def test_inserted_qualifier_is_not_resolved_a_second_time(self):
        types = '''TYPE item_t = STRUCTURE n: INTEGER ENDSTRUCTURE
outer_t = STRUCTURE first: item_t ENDSTRUCTURE'''
        state = execute('USING first,second DO n = 7 ENDUSING', types=types, declarations='first: item_t second: outer_t')
        self.assertEqual((state['FIRST']['N'], state['SECOND']['FIRST']['N']), (7, {'uninitialized': True}))

    def test_report_records_each_scope_and_use(self):
        _, report = compile_program('USING left,right DO count = 7 result = count ENDUSING')
        scope = report.report['using_scopes'][0]
        self.assertEqual(scope['variables'], ['LEFT', 'RIGHT'])
        self.assertEqual(scope['field_bindings']['COUNT'], 'RIGHT')
        self.assertEqual([(item['field'], item['variable']) for item in scope['resolved_uses']], [('COUNT', 'RIGHT'), ('COUNT', 'RIGHT')])
        self.assertTrue(all(item['line'] > 0 and item['column'] > 0 for item in scope['resolved_uses']))
        self.assertFalse(report.report['using_policy']['controller_validated'])

    def test_example_complete_snapshot(self):
        path = Path(__file__).resolve().parents[1] / 'examples/using_fields.kl'
        result = translate(path.read_text())
        namespace = {'__name__': 'using_example'}
        exec(result.python_source, namespace)
        self.assertEqual(namespace['Program']().run(), dict(
            FIRST=dict(VALUE=3, LABEL='abc', SLOTS=[1, 2]), SECOND=dict(VALUE=11, READY=True),
            VALUE=90, TOTAL=12, INSPECTED=3))


class UsingRoutineTests(unittest.TestCase):
    def test_selector_can_be_a_structure_reference_parameter(self):
        routine = 'ROUTINE put(p: left_t) BEGIN USING p DO count = 7 ENDUSING END put'
        self.assertEqual(execute('put(left)', routine)['LEFT']['COUNT'], 7)

    def test_selector_can_be_a_fresh_local_structure(self):
        routine = 'ROUTINE read_value: INTEGER VAR p: left_t BEGIN USING p DO count = 7 RETURN count ENDUSING END read_value'
        self.assertEqual(execute('result = read_value()', routine)['RESULT'], 7)

    def test_field_overrides_routine_local_and_parameter_variables(self):
        routine = 'ROUTINE put(count: INTEGER) VAR p: left_t BEGIN USING p DO count = 7 result = count ENDUSING END put'
        state = execute('count = 90 put(count)', routine)
        self.assertEqual((state['COUNT'], state['RESULT']), (90, 7))

    def test_scalar_alias_argument_keeps_reference_passing(self):
        routine = 'ROUTINE put(p: INTEGER) BEGIN p = 7 END put'
        self.assertEqual(execute('USING left DO put(count) ENDUSING', routine)['LEFT']['COUNT'], 7)

    def test_parenthesized_alias_argument_keeps_value_passing(self):
        routine = 'ROUTINE put(p: INTEGER) BEGIN p = 7 END put'
        self.assertEqual(execute('left.count = 1 USING left DO put((count)) ENDUSING', routine)['LEFT']['COUNT'], 1)

    def test_array_alias_argument_retains_whole_reference(self):
        routine = 'ROUTINE put(p: ARRAY OF INTEGER) BEGIN p[2] = 7 END put'
        self.assertEqual(execute('USING left DO put(slots) ENDUSING', routine)['LEFT']['SLOTS'][1], 7)

    def test_callee_does_not_inherit_callers_field_scope(self):
        routine = 'ROUTINE read_global: INTEGER BEGIN RETURN count END read_global'
        state = execute('count = 90 left.count = 1 USING left DO result = read_global() ENDUSING', routine)
        self.assertEqual(state['RESULT'], 90)

    def test_pure_local_field_function_remains_usable_in_binary_expression(self):
        routine = 'ROUTINE compute: INTEGER VAR p: left_t BEGIN USING p DO count = 7 RETURN count ENDUSING END compute'
        self.assertEqual(execute('result = compute() + 1', routine)['RESULT'], 8)

    def test_structure_replacement_is_visible_to_later_alias_reads(self):
        types = 'TYPE item_t = STRUCTURE count: INTEGER ENDSTRUCTURE'
        routine = 'ROUTINE copy(dst,src: item_t) BEGIN dst = src END copy'
        state = execute('first.count = 1 second.count = 7 USING first DO copy(first,second) result = count ENDUSING', routine,
                        types=types, declarations='first,second: item_t result: INTEGER')
        self.assertEqual((state['FIRST']['COUNT'], state['RESULT']), (7, 7))

    def test_narrow_alias_arguments_keep_value_promotion(self):
        routine = 'ROUTINE put(p: INTEGER) BEGIN p = 99 END put'
        state = execute('p.code = 7 USING p DO put(code) ENDUSING', routine,
                        types='TYPE item_t = STRUCTURE code: BYTE ENDSTRUCTURE', declarations='p: item_t')
        self.assertEqual(state['P']['CODE'], 7)

    def test_error_unwinds_routine_frames_and_retains_prior_field_write(self):
        routine = 'ROUTINE fail(p: left_t) BEGIN USING p DO count = 7 result = slots[1] ENDUSING END fail'
        program, _ = compile_program('fail(left)', routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual((program._state.snapshot()['LEFT']['COUNT'], program._state.local_frames, program._state.call_depth), (7, [], 0))

    def test_plain_procedure_return_before_endusing(self):
        routine = 'ROUTINE put(p: left_t) BEGIN USING p DO count = 7 RETURN ENDUSING result = 99 END put'
        state = execute('result = 1 put(left)', routine)
        self.assertEqual((state['LEFT']['COUNT'], state['RESULT']), (7, 1))


class UsingControlFlowTests(unittest.TestCase):
    def test_if_while_repeat_and_select_use_qualified_fields(self):
        state = execute('''USING left DO count = 0
WHILE count < 2 DO count = count + 1 ENDWHILE
REPEAT count = count + 1 UNTIL count = 3
IF count = 3 THEN SELECT count OF CASE(3): result = 7 ELSE: result = 99 ENDSELECT ENDIF
ENDUSING''')
        self.assertEqual((state['LEFT']['COUNT'], state['RESULT']), (3, 7))

    def test_for_with_unshadowed_counter_and_field_bounds(self):
        state = execute('left.count = 2 USING left DO FOR index_value = 1 TO count DO slots[index_value] = index_value ENDFOR ENDUSING')
        self.assertEqual(state['LEFT']['SLOTS'], [1, 2])

    def test_using_inside_fresh_local_for_with_helper_call(self):
        routines = '''ROUTINE put(p: INTEGER) BEGIN p = 7 END put
ROUTINE work VAR p: left_t k: INTEGER BEGIN FOR k = 1 TO 2 DO USING p DO put(slots[k]) ENDUSING ENDFOR result = p.slots[2] END work'''
        self.assertEqual(execute('work', routines)['RESULT'], 7)

    def test_using_inside_global_for_does_not_bypass_call_guard(self):
        routine = 'ROUTINE put(p: INTEGER) BEGIN p = 7 END put'
        with self.assertRaises(TranslationError) as caught: compile_program('FOR index_value = 1 TO 2 DO USING left DO put(count) ENDUSING ENDFOR', routine, _translator=legacy_translate)
        self.assertEqual(caught.exception.code, 'E_FOR_COUNTER')

    def test_backward_jump_within_using(self):
        state = execute('USING left DO count = 0 again:: count = count + 1 IF count < 3 THEN GO TO again ENDIF ENDUSING')
        self.assertEqual(state['LEFT']['COUNT'], 3)

    def test_jump_out_restores_ordinary_name_resolution(self):
        state = execute('count = 90 USING left DO count = 7 GO TO finished count = 99 ENDUSING finished:: result = count')
        self.assertEqual((state['LEFT']['COUNT'], state['RESULT']), (7, 90))

    def test_jump_from_using_nested_if_to_using_label(self):
        self.assertEqual(execute('USING left DO count = 1 IF TRUE THEN GO TO done ENDIF count = 99 done:: result = count ENDUSING')['RESULT'], 1)

    def test_using_inside_loop_in_label_dispatcher(self):
        state = execute('count = 0 left.count = 0 again:: WHILE count < 2 DO USING left DO count = count + 1 ENDUSING count = count + 1 ENDWHILE')
        self.assertEqual((state['COUNT'], state['LEFT']['COUNT']), (2, 2))

    def test_step_budget_still_limits_alias_loop(self):
        program, _ = compile_program('USING left DO count = 0 again:: count = count + 1 GO TO again ENDUSING')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'step budget'): program.run(max_steps=10)


class UsingBoundaryTests(unittest.TestCase):
    def rejected(self, body, code, **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_non_structure_selector_is_rejected(self):
        self.rejected('USING count DO ENDUSING', 'E_USING_TYPE')

    def test_unknown_selector_is_rejected(self):
        self.rejected('USING missing DO ENDUSING', 'E_SYMBOL')

    def test_indexed_and_field_selectors_remain_blocked(self):
        for selector in ('items[1]', 'left.child'):
            with self.subTest(selector=selector): self.rejected(f'USING {selector} DO ENDUSING', 'E_USING_TARGET', _translator=legacy_translate)

    def test_function_selector_remains_blocked(self):
        self.rejected('USING make() DO ENDUSING', 'E_USING_TARGET')

    def test_nested_using_remains_blocked(self):
        self.rejected('USING left DO USING right DO count = 7 ENDUSING ENDUSING', 'E_USING_NESTED', _translator=legacy_translate)

    def test_shadowed_for_counter_remains_blocked(self):
        self.rejected('USING left DO FOR count = 1 TO 2 DO ENDFOR ENDUSING', 'E_USING_FOR_COUNTER')

    def test_call_name_colliding_with_field_remains_blocked(self):
        self.rejected('USING left DO count() ENDUSING', 'E_USING_CALL_SHADOW', _translator=legacy_translate)

    def test_function_call_name_collision_remains_blocked(self):
        self.rejected('USING left DO result = count() ENDUSING', 'E_USING_CALL_SHADOW', _translator=legacy_translate)

    def test_field_type_checks_still_apply(self):
        self.rejected("USING left DO count = 'bad' ENDUSING", 'E_TYPE')

    def test_aggregate_uninit_stays_blocked(self):
        self.rejected('USING left DO flag = UNINIT(child) ENDUSING', 'E_TYPE')

    def test_effect_analysis_sees_rewritten_global_field_writes(self):
        routine = 'ROUTINE change: INTEGER BEGIN USING left DO count = 7 RETURN count ENDUSING END change'
        self.rejected('result = change() + 1', 'E_EVALUATION_ORDER', routines=routine, _translator=legacy_translate)

    def test_effect_analysis_sees_rewritten_reference_field_writes(self):
        routine = 'ROUTINE change(p: left_t): INTEGER BEGIN USING p DO count = 7 RETURN count ENDUSING END change'
        self.rejected('result = change(left) + 1', 'E_EVALUATION_ORDER', routines=routine, _translator=legacy_translate)

    def test_transitive_effect_guard_survives_using_resolution(self):
        routines = '''ROUTINE change: INTEGER BEGIN USING left DO count = 7 RETURN count ENDUSING END change
ROUTINE relay: INTEGER BEGIN RETURN change() END relay'''
        self.rejected('result = relay() + 1', 'E_EVALUATION_ORDER', routines=routines, _translator=legacy_translate)

    def test_indexed_alias_effectful_result_stays_blocked(self):
        routine = 'ROUTINE change: INTEGER BEGIN index_value = 2 RETURN 7 END change'
        self.rejected('USING left DO slots[index_value] = change() ENDUSING', 'E_EVALUATION_ORDER', routines=routine, _translator=legacy_translate)

    def test_multi_argument_call_order_guard_stays_blocked(self):
        routines = 'ROUTINE f: INTEGER BEGIN RETURN 1 END f\nROUTINE put(p,q: INTEGER) BEGIN END put'
        self.rejected('USING left DO put(count,f()) ENDUSING', 'E_EVALUATION_ORDER', routines=routines, _translator=legacy_translate)

    def test_jump_into_using_is_rejected(self):
        self.rejected('GO TO inside USING left DO inside:: count = 7 ENDUSING', 'E_GOTO_ENTRY')

    def test_jump_between_using_blocks_is_rejected(self):
        self.rejected('USING left DO GO TO inside ENDUSING USING right DO inside:: count = 7 ENDUSING', 'E_GOTO_ENTRY')

    def test_for_body_labels_inside_using_stay_blocked(self):
        self.rejected('FOR index_value = 1 TO 2 DO USING left DO inside:: count = 7 ENDUSING ENDFOR', 'E_GOTO_FOR')

    def test_shadowed_case_constant_does_not_become_a_runtime_case(self):
        self.rejected('USING left DO SELECT result OF CASE(count): result = 1 ENDSELECT ENDUSING', 'E_USING_CONST_SHADOW',
                      declarations='left: left_t result: INTEGER', constants='CONST count = 7', _translator=legacy_translate)


if __name__ == '__main__': unittest.main()
