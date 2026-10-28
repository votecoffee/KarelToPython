"""Authored nested/sibling GOTO entry with retained capture and FOR barriers."""
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source

DECL='n,x,y,i,calls,visits:INTEGER flag:BOOLEAN'
SCHEMA='TYPE row_t=STRUCTURE value:INTEGER ENDSTRUCTURE'
RECORDS=DECL+' items:ARRAY[2] OF row_t'


def execute(body,**options):return run(body,decl=options.pop('decl',DECL),**options)


class StructuredEntryTests(unittest.TestCase):
    def test_enter_if_then_without_evaluating_condition(self):
        values=execute('GOTO deep IF flag THEN x=99 deep:: x=7 ENDIF y=x');self.assertEqual((values['X'],values['Y']),(7,7))

    def test_enter_if_else_without_evaluating_condition(self):
        values=execute('GOTO deep IF flag THEN x=99 ELSE x=88 deep:: x=7 ENDIF y=x');self.assertEqual(values['Y'],7)

    def test_sibling_if_branch_transfer(self):
        values=execute('IF TRUE THEN x=1 GOTO other ELSE x=99 other:: x=x+6 ENDIF y=x');self.assertEqual(values['Y'],7)

    def test_sibling_if_blocks_skip_target_condition(self):
        values=execute('IF TRUE THEN GOTO other ENDIF IF flag THEN x=99 other:: x=7 ENDIF y=x');self.assertEqual(values['Y'],7)

    def test_multiple_nested_if_levels(self):
        values=execute('GOTO deep IF flag THEN IF flag THEN deep:: x=7 ENDIF ELSE x=99 ENDIF y=x');self.assertEqual(values['Y'],7)

    def test_direct_entry_skips_condition_function_effects(self):
        values=execute('calls=0 GOTO deep IF probe_flag() THEN deep:: x=7 ENDIF',routines='ROUTINE probe_flag:BOOLEAN BEGIN calls=calls+1 RETURN flag END probe_flag');self.assertEqual((values['CALLS'],values['X']),(0,7))

    def test_while_entry_executes_suffix_then_checks_condition(self):
        values=execute('n=0 visits=0 GOTO deep WHILE FALSE DO n=n+100 deep:: visits=visits+1 ENDWHILE y=visits');self.assertEqual((values['N'],values['Y']),(0,1))

    def test_while_reentry_resumes_normal_loop_head(self):
        values=execute('n=0 calls=0 visits=0 GOTO deep WHILE next_iteration() DO n=n+10 deep:: visits=visits+1 ENDWHILE y=visits',routines='ROUTINE next_iteration:BOOLEAN BEGIN calls=calls+1 RETURN visits<3 END next_iteration')
        self.assertEqual((values['N'],values['VISITS'],values['CALLS']),(20,3,3))

    def test_enter_nested_loops_without_initial_tests(self):
        values=execute('n=0 flag=FALSE GOTO deep WHILE flag DO IF flag THEN WHILE flag DO deep:: n=n+1 ENDWHILE ENDIF ENDWHILE y=n');self.assertEqual(values['Y'],1)

    def test_repeat_entry_runs_until_then_restarts_from_beginning(self):
        values=execute('n=0 GOTO deep REPEAT n=n+10 deep:: n=n+1 UNTIL n>=3 y=n');self.assertEqual(values['Y'],12)

    def test_repeat_entry_can_finish_without_running_prefix(self):
        values=execute('n=0 GOTO deep REPEAT n=99 deep:: n=n+1 UNTIL TRUE y=n');self.assertEqual(values['Y'],1)

    def test_transfer_between_while_and_repeat_bodies(self):
        values=execute('n=0 WHILE TRUE DO GOTO deep ENDWHILE REPEAT n=99 deep:: n=n+1 UNTIL TRUE y=n');self.assertEqual(values['Y'],1)

    def test_enter_case_without_evaluating_selector(self):
        values=execute('GOTO deep SELECT n OF CASE(1): x=99 CASE(2): deep:: x=7 ENDSELECT y=x');self.assertEqual(values['Y'],7)

    def test_enter_select_else_without_selector_or_case_dispatch(self):
        values=execute('GOTO deep SELECT n OF CASE(1): x=99 ELSE: deep:: x=7 ENDSELECT y=x');self.assertEqual(values['Y'],7)

    def test_sibling_select_cases_have_explicit_transfer_only(self):
        values=execute('SELECT 1 OF CASE(1): x=1 GOTO other CASE(2): x=99 other:: x=x+6 CASE(3): x=100 ENDSELECT y=x');self.assertEqual(values['Y'],7)

    def test_enter_case_does_not_fall_through_to_next_case(self):
        values=execute('GOTO deep SELECT n OF CASE(1): deep:: x=7 CASE(2): x=99 ENDSELECT y=x');self.assertEqual(values['Y'],7)

    def test_nested_case_entry_skips_all_enclosing_selectors(self):
        values=execute('GOTO deep SELECT n OF CASE(1): SELECT n OF CASE(2): deep:: x=7 ENDSELECT ENDSELECT y=x');self.assertEqual(values['Y'],7)

    def test_selector_function_skipped_on_direct_case_entry(self):
        values=execute('calls=0 GOTO deep SELECT choose() OF CASE(1): deep:: x=7 ENDSELECT',routines='ROUTINE choose:INTEGER BEGIN calls=calls+1 RETURN n END choose');self.assertEqual((values['CALLS'],values['X']),(0,7))

    def test_label_at_end_of_nested_body_uses_ordinary_continuation(self):
        self.assertEqual(execute('x=7 GOTO deep IF flag THEN x=99 deep:: ENDIF y=x')['Y'],7)

    def test_jump_from_else_to_then(self):
        self.assertEqual(execute('IF FALSE THEN deep:: x=7 ELSE GOTO deep ENDIF y=x')['Y'],7)

    def test_go_to_spelling_and_case_insensitivity(self):
        self.assertEqual(execute('GO TO DeEp IF flag THEN deep:: x=7 ENDIF')['X'],7)

    def test_jump_cycle_remains_budgeted(self):
        p,_=compile_program('GOTO deep IF flag THEN deep:: GOTO deep ENDIF',decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=15)

    def test_post_entry_condition_failure_retains_body_writes(self):
        p,_=compile_program('GOTO deep WHILE flag DO deep:: x=7 ENDWHILE',decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'):p.run()
        self.assertEqual(p.snapshot()['X'],7)

    def test_jump_can_skip_entire_for_without_touching_counter(self):
        values=execute('i=9 GOTO deep IF flag THEN FOR i=1 TO 2 DO x=99 ENDFOR deep:: x=i ENDIF');self.assertEqual(values['X'],9)


class CaptureBarrierTests(unittest.TestCase):
    def reject(self,body,code='E_GOTO_ENTRY'):
        with self.assertRaises(TranslationError) as caught:compile_program(body,decl=RECORDS,prefix=SCHEMA)
        self.assertEqual(caught.exception.code,code)

    def test_entry_to_using_from_root_is_still_rejected(self):self.reject('GOTO deep USING items[1] DO IF TRUE THEN deep:: value=7 ENDIF ENDUSING')

    def test_entry_to_sibling_using_is_rejected_even_for_same_storage(self):self.reject('USING items[1] DO GOTO deep ENDUSING USING items[1] DO deep:: value=7 ENDUSING')

    def test_entry_into_additional_inner_using_is_rejected(self):self.reject('USING items[1] DO GOTO deep IF TRUE THEN USING items[2] DO deep:: value=7 ENDUSING ENDIF ENDUSING')

    def test_structured_sibling_transfer_within_same_using_retains_capture(self):
        values=execute('calls=0 USING items[next_item()] DO IF TRUE THEN GOTO deep ELSE deep:: value=7 ENDIF ENDUSING',decl=RECORDS,prefix=SCHEMA,routines='ROUTINE next_item:INTEGER BEGIN calls=calls+1 RETURN 1 END next_item')
        self.assertEqual((values['CALLS'],values['ITEMS'][0]['VALUE']),(1,7))

    def test_loop_entry_within_using_does_not_recapture(self):
        values=execute('calls=0 USING items[next_item()] DO value=0 GOTO deep WHILE FALSE DO deep:: value=value+7 ENDWHILE ENDUSING',decl=RECORDS,prefix=SCHEMA,routines='ROUTINE next_item:INTEGER BEGIN calls=calls+1 RETURN 1 END next_item')
        self.assertEqual((values['CALLS'],values['ITEMS'][0]['VALUE']),(1,7))

    def test_jump_out_of_inner_using_restores_outer_field_binding(self):
        body='USING items[1] DO value=1 USING items[2] DO value=2 GOTO deep ENDUSING IF flag THEN deep:: value=value+6 ENDIF ENDUSING'
        values=execute(body,decl=RECORDS,prefix=SCHEMA);self.assertEqual([row['VALUE'] for row in values['ITEMS']],[7,2])

    def test_entering_label_before_using_runs_its_capture_normally(self):
        body='calls=0 GOTO deep IF flag THEN deep:: USING items[next_item()] DO value=7 ENDUSING ENDIF'
        values=execute(body,decl=RECORDS,prefix=SCHEMA,routines='ROUTINE next_item:INTEGER BEGIN calls=calls+1 RETURN 1 END next_item');self.assertEqual((values['CALLS'],values['ITEMS'][0]['VALUE']),(1,7))

    def test_sibling_using_entry_through_nested_case_stays_rejected(self):self.reject('USING items[1] DO GOTO deep ENDUSING SELECT n OF CASE(1): USING items[2] DO IF TRUE THEN deep:: value=7 ENDIF ENDUSING ENDSELECT')

    def test_same_using_case_jump_retains_rightmost_field_priority(self):
        body='USING items[1],items[2] DO SELECT 1 OF CASE(1): GOTO deep CASE(2): deep:: value=7 ENDSELECT ENDUSING'
        values=execute(body,decl=RECORDS,prefix=SCHEMA);self.assertEqual(values['ITEMS'][1]['VALUE'],7);self.assertEqual(values['ITEMS'][0]['VALUE'],{'uninitialized':True})

    def test_completed_capture_cannot_be_reentered_from_outside(self):self.reject('USING items[1] DO deep:: value=7 ENDUSING GOTO deep')

    def test_for_exit_cleans_counter_while_new_entry_stays_rejected(self):
        values=execute('FOR i=1 TO 2 DO GOTO deep ENDFOR deep:: flag=UNINIT(i)')
        self.assertTrue(values['FLAG'])
        self.reject('GOTO deep FOR i=1 TO 2 DO deep:: x=7 ENDFOR','E_GOTO_FOR')


class RoutineAndExecutionTests(unittest.TestCase):
    def test_function_entry_can_reach_return_in_false_branch(self):
        values=execute('x=work()',routines='ROUTINE work:INTEGER BEGIN GOTO deep IF FALSE THEN deep:: RETURN 7 ENDIF RETURN 99 END work');self.assertEqual(values['X'],7)

    def test_routine_locals_and_formal_aliases_survive_entry(self):
        values=execute('x=1 work(x) y=x',routines='ROUTINE work(item:INTEGER) VAR local_value:INTEGER BEGIN local_value=6 GOTO deep IF FALSE THEN deep:: item=item+local_value ENDIF END work');self.assertEqual(values['Y'],7)

    def test_error_after_entry_unwinds_routine_frame(self):
        p,_=compile_program('work',decl=DECL,routines='ROUTINE work BEGIN GOTO deep IF FALSE THEN deep:: x=1 DIV 0 ENDIF END work')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))

    def test_abort_after_entry_unwinds_routine_frame(self):
        p,_=compile_program('work',decl=DECL,routines='ROUTINE work BEGIN GOTO deep IF FALSE THEN deep:: x=7 ABORT ENDIF END work')
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual((p.snapshot()['X'],p._state.local_frames,p._state.call_depth),(7,[],0))

    def test_pause_resume_retains_target_and_does_not_replay_prefix(self):
        p,_=compile_program('n=0 GOTO deep IF FALSE THEN n=99 deep:: n=n+1 PAUSE n=n+1 ENDIF',decl=DECL,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['N'],1);self.assertEqual(p.resume()['N'],2)

    def test_stop_paused_entry_releases_routine_frames(self):
        p,_=compile_program('work',decl=DECL,cooperative=True,routines='ROUTINE work BEGIN GOTO deep IF FALSE THEN deep:: x=7 PAUSE ENDIF END work')
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))

    def test_cooperative_budget_failure_remains_bounded(self):
        p,_=compile_program('GOTO deep IF FALSE THEN deep:: GOTO deep ENDIF',decl=DECL,cooperative=True)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=15)

    def test_linked_routine_label_stays_local_and_returns_value(self):
        project=translate_project({'main':source('MAIN','n=work()',routines='ROUTINE work:INTEGER FROM LIB'),'lib':source('LIB','',routines='ROUTINE work:INTEGER BEGIN GOTO deep IF FALSE THEN deep:: RETURN 7 ENDIF RETURN 99 END work')})
        values=project.instantiate().run('MAIN');self.assertEqual(values['MAIN']['values']['N'],7)

    def test_cross_routine_target_still_rejected(self):
        with self.assertRaises(TranslationError):compile_program('GOTO deep',decl=DECL,routines='ROUTINE work BEGIN IF FALSE THEN deep:: ENDIF END work')

    def test_condition_actions_cannot_gain_jump_or_label_statements(self):
        for action in ('GOTO deep','deep:: x=7'):
            with self.subTest(action=action),self.assertRaises(TranslationError):compile_program('CONDITION[1]: WHEN TRUE DO '+action+' ENDCONDITION deep::',decl=DECL,cooperative=True)


class NestedJumpReportAndGuardTests(unittest.TestCase):
    def test_policy_reports_supported_forms_and_retained_barriers(self):
        policy=translate('PROGRAM T BEGIN END T').report['nested_jump_policy']
        self.assertEqual(policy['forms'],['IF','WHILE','REPEAT','SELECT']);self.assertFalse(policy['controller_validated'])
        self.assertIn('prefix',policy['captures']);self.assertIn('FOR',policy['guards'])

    def test_report_records_nested_and_sibling_paths(self):
        p,result=compile_program('GOTO deep IF FALSE THEN deep:: GOTO other ELSE other:: x=7 ENDIF',decl=DECL);self.assertEqual(p.run()['X'],7)
        graph=result.report['control_flow'];self.assertEqual(graph['jump_policy'],'body_labels_no_new_for_or_using');self.assertEqual([row['entry_kind'] for row in graph['program']['jumps']],['nested','sibling'])
        for row in graph['program']['jumps']:self.assertGreater(row['source']['line'],0);self.assertGreater(row['target']['line'],0);self.assertTrue(row['target']['blocks'])

    def test_existing_same_block_and_ancestor_jumps_are_reported(self):
        _,result=compile_program('GOTO done x=99 done:: IF TRUE THEN GOTO last ENDIF last::',decl=DECL);self.assertEqual([row['entry_kind'] for row in result.report['control_flow']['program']['jumps']],['same_block','ancestor'])

    def test_no_labels_retains_structured_python_engine(self):
        _,result=compile_program('IF TRUE THEN x=7 ENDIF',decl=DECL);self.assertEqual(result.report['control_flow']['program']['engine'],'structured_python');self.assertEqual(result.report['control_flow']['program']['jumps'],[])

    def test_legacy_nested_entry_keeps_conservative_gate(self):
        with self.assertRaises(TranslationError) as caught:legacy_translate('PROGRAM T VAR x:INTEGER BEGIN GOTO deep IF TRUE THEN deep:: x=7 ENDIF END T')
        self.assertEqual(caught.exception.code,'E_GOTO_ENTRY')

    def test_unreachable_source_types_are_still_checked(self):
        with self.assertRaises(TranslationError):compile_program('GOTO deep IF FALSE THEN x=TRUE deep:: x=7 ENDIF',decl=DECL)

    def test_duplicate_labels_in_different_blocks_still_rejected(self):
        with self.assertRaises(TranslationError) as caught:compile_program('IF TRUE THEN deep:: ELSE deep:: ENDIF',decl=DECL)
        self.assertEqual(caught.exception.code,'E_DUPLICATE_LABEL')

    def test_missing_target_still_rejected(self):
        with self.assertRaises(TranslationError) as caught:compile_program('GOTO missing IF FALSE THEN deep:: ENDIF',decl=DECL)
        self.assertEqual(caught.exception.code,'E_LABEL')

    def test_include_source_map_retains_physical_target_origin(self):
        result=translate('PROGRAM T VAR x:INTEGER BEGIN\nGOTO deep\n%INCLUDE branch\nEND T',includes={'branch.kl':'IF FALSE THEN\ndeep:: x=7\nENDIF'},filename='main.kl')
        ns={'__name__':'include'};exec(result.python_source,ns);self.assertEqual(ns['Program']().run()['X'],7)
        target=result.report['control_flow']['program']['jumps'][0]['target']['line'];mapped=[row for row in result.report['source_map'] if row['karel_line']==target]
        self.assertTrue(any(row['source_file'].lower().endswith('branch.kl') and row['source_line']==2 for row in mapped))


if __name__=='__main__':unittest.main()
