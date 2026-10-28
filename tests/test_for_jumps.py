"""Authored Pythonic FOR labels, retained iteration scopes and checked exits."""
from pathlib import Path
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program,run


UNKNOWN={'uninitialized':True}
DECL='i,j,total,n,calls,visits,result,skipped:INTEGER flag,first,clean,clean_inner:BOOLEAN'
SCHEMA='TYPE row_t=STRUCTURE value:INTEGER ENDSTRUCTURE'


def execute(body,**options):return run(body,decl=options.pop('decl',DECL),**options)


class ForJumpIterationTests(unittest.TestCase):
    def test_label_inside_for_retains_normal_iterations_and_cleanup(self):
        values=execute('total=0 FOR i=1 TO 3 DO here:: total=total+i ENDFOR')
        self.assertEqual((values['TOTAL'],values['I']),(6,UNKNOWN))

    def test_forward_body_jump_skips_prefix_and_then_advances(self):
        values=execute('total=0 FOR i=1 TO 3 DO GOTO suffix total=99 suffix:: total=total+i ENDFOR')
        self.assertEqual((values['TOTAL'],values['I']),(6,UNKNOWN))

    def test_backward_body_jump_retains_current_counter_and_final_bound(self):
        values=execute('total=0 visits=0 FOR i=1 TO 3 DO again:: total=total+i visits=visits+1 IF visits=1 THEN GOTO again ENDIF ENDFOR')
        self.assertEqual((values['TOTAL'],values['VISITS']),(7,4))

    def test_last_body_label_continues_at_the_next_iteration(self):
        values=execute('total=0 FOR i=1 TO 3 DO total=total+i GOTO suffix total=99 suffix:: ENDFOR')
        self.assertEqual(values['TOTAL'],6);self.assertEqual(values['I'],UNKNOWN)

    def test_downward_loop_keeps_inclusive_step_after_a_jump(self):
        values=execute('total=0 FOR i=3 DOWNTO 1 DO GOTO suffix total=99 suffix:: total=total+i ENDFOR')
        self.assertEqual(values['TOTAL'],6)

    def test_negative_bounds_keep_normal_pythonic_loop_values(self):
        values=execute('total=0 FOR i=-3 TO -1 DO suffix:: total=total+i ENDFOR')
        self.assertEqual(values['TOTAL'],-6);self.assertEqual(values['I'],UNKNOWN)

    def test_empty_for_never_executes_body_label_but_clears_counter(self):
        values=execute('i=9 total=0 FOR i=3 TO 1 DO suffix:: total=99 ENDFOR')
        self.assertEqual((values['TOTAL'],values['I']),(0,UNKNOWN))

    def test_single_iteration_executes_suffix_once(self):
        self.assertEqual(execute('total=0 FOR i=2 TO 2 DO GOTO suffix suffix:: total=total+i ENDFOR')['TOTAL'],2)

    def test_jump_before_for_reenters_through_a_fresh_header(self):
        values=execute('total=0 visits=0 again:: visits=visits+1 FOR i=1 TO 2 DO total=total+i IF visits=1 THEN GOTO again ENDIF ENDFOR')
        self.assertEqual((values['TOTAL'],values['VISITS'],values['I']),(4,2,UNKNOWN))

    def test_skipping_entire_for_leaves_old_counter_untouched(self):
        values=execute('i=9 GOTO done FOR i=1 TO 3 DO suffix:: total=99 ENDFOR done:: total=i')
        self.assertEqual((values['I'],values['TOTAL']),(9,9))

    def test_same_for_sibling_if_transfer_skips_target_condition(self):
        values=execute('total=0 FOR i=1 TO 2 DO IF TRUE THEN GOTO suffix ELSE suffix:: total=total+i ENDIF ENDFOR')
        self.assertEqual(values['TOTAL'],3)

    def test_same_for_select_case_transfer_keeps_the_scope(self):
        values=execute('total=0 FOR i=1 TO 2 DO SELECT 1 OF CASE(1): GOTO suffix CASE(2): suffix:: total=total+i ENDSELECT ENDFOR')
        self.assertEqual(values['TOTAL'],3)

    def test_nested_false_branch_entry_keeps_current_for_counter(self):
        values=execute('total=0 FOR i=1 TO 2 DO GOTO suffix IF flag THEN WHILE FALSE DO suffix:: total=total+i ENDWHILE ENDIF ENDFOR')
        self.assertEqual(values['TOTAL'],3)

    def test_bounds_are_evaluated_once_despite_backward_jumps(self):
        routines='ROUTINE start_value:INTEGER BEGIN calls=calls+1 RETURN 1 END start_value\nROUTINE final_value:INTEGER BEGIN calls=calls+1 RETURN 2 END final_value'
        values=execute('calls=0 total=0 first=TRUE FOR i=start_value() TO final_value() DO again:: total=total+i IF first THEN first=FALSE GOTO again ENDIF ENDFOR',routines=routines)
        self.assertEqual((values['TOTAL'],values['CALLS']),(4,2))

    def test_final_bound_can_observe_and_change_initial_counter_before_capture(self):
        routines='ROUTINE final_value:INTEGER BEGIN n=i i=2 RETURN 3 END final_value'
        values=execute('total=0 FOR i=1 TO final_value() DO suffix:: total=total+i ENDFOR',routines=routines)
        self.assertEqual((values['N'],values['TOTAL'],values['I']),(1,5,UNKNOWN))

    def test_labelled_and_structured_for_execution_and_steps_match(self):
        body='total=0 FOR i=1 TO 3 DO FOR j=2 DOWNTO 1 DO IF j=1 THEN total=total+i ELSE total=total+j ENDIF ENDFOR ENDFOR'
        outcomes=[]
        for prefix in ('','unused:: '):
            program,_=compile_program(prefix+body,decl=DECL);outcomes.append((program.run(),program._state.steps))
        self.assertEqual(outcomes[0],outcomes[1])

    def test_no_labels_still_uses_structured_python(self):
        _,translation=compile_program('FOR i=1 TO 2 DO total=i ENDFOR',decl=DECL)
        self.assertEqual(translation.report['control_flow']['program']['engine'],'structured_python')


class ForJumpExitTests(unittest.TestCase):
    def test_exit_clears_counter_before_target_can_observe_it(self):
        values=execute('FOR i=1 TO 3 DO GOTO done ENDFOR done:: clean=UNINIT(i)')
        self.assertTrue(values['CLEAN']);self.assertEqual(values['I'],UNKNOWN)

    def test_nested_exit_clears_only_inner_counter_and_preserves_outer_iteration(self):
        values=execute('total=0 visits=0 FOR i=1 TO 3 DO FOR j=1 TO 2 DO total=total+i GOTO next_outer ENDFOR next_outer:: clean_inner=UNINIT(j) visits=visits+1 ENDFOR')
        self.assertEqual((values['TOTAL'],values['VISITS'],values['CLEAN_INNER']),(6,3,True))
        self.assertEqual((values['I'],values['J']),(UNKNOWN,UNKNOWN))

    def test_exit_multiple_nested_fors_clears_every_counter(self):
        values=execute('FOR i=1 TO 3 DO FOR j=1 TO 2 DO GOTO done ENDFOR ENDFOR done:: clean=UNINIT(i) clean_inner=UNINIT(j)')
        self.assertEqual((values['CLEAN'],values['CLEAN_INNER']),(True,True))

    def test_exit_into_a_sibling_while_skips_its_initial_test(self):
        values=execute('FOR i=1 TO 2 DO GOTO suffix ENDFOR WHILE FALSE DO suffix:: clean=UNINIT(i) total=7 ENDWHILE')
        self.assertEqual((values['CLEAN'],values['TOTAL']),(True,7))

    def test_exit_into_select_suffix_does_not_evaluate_selector(self):
        values=execute('FOR i=1 TO 2 DO GOTO suffix ENDFOR SELECT n OF CASE(1): suffix:: clean=UNINIT(i) ENDSELECT')
        self.assertTrue(values['CLEAN'])

    def test_exited_scope_no_longer_protects_counter_at_the_target(self):
        self.assertEqual(execute('FOR i=1 TO 2 DO GOTO done ENDFOR done:: i=9')['I'],9)

    def test_using_capture_survives_jumps_within_for(self):
        routines='ROUTINE pick:INTEGER BEGIN calls=calls+1 RETURN 1 END pick'
        values=execute('calls=0 USING items[pick()] DO value=0 FOR i=1 TO 2 DO GOTO suffix suffix:: value=value+i ENDFOR ENDUSING',
            decl=DECL+' items:ARRAY[2] OF row_t',prefix=SCHEMA,routines=routines)
        self.assertEqual((values['CALLS'],values['ITEMS'][0]['VALUE']),(1,3))

    def test_exit_inner_using_keeps_outer_for_active(self):
        values=execute('total=0 FOR i=1 TO 2 DO USING items[1] DO value=i GOTO suffix ENDUSING suffix:: total=total+i ENDFOR',
            decl=DECL+' items:ARRAY[2] OF row_t',prefix=SCHEMA)
        self.assertEqual((values['TOTAL'],values['ITEMS'][0]['VALUE']),(3,2))

    def test_exit_for_and_inner_using_restores_outer_using_binding(self):
        values=execute('USING items[1] DO value=1 FOR i=1 TO 2 DO USING items[2] DO value=2 GOTO done ENDUSING ENDFOR done:: value=value+6 ENDUSING',
            decl=DECL+' items:ARRAY[2] OF row_t',prefix=SCHEMA)
        self.assertEqual([row['VALUE'] for row in values['ITEMS']],[7,2]);self.assertEqual(values['I'],UNKNOWN)

    def test_function_return_captures_counter_before_unwinding(self):
        routine='ROUTINE work:INTEGER BEGIN FOR i=1 TO 3 DO suffix:: RETURN i ENDFOR RETURN 9 END work'
        values=execute('result=work()',routines=routine)
        self.assertEqual((values['RESULT'],values['I']),(1,UNKNOWN))

    def test_nested_return_clears_both_counters_and_routine_frames(self):
        routine='ROUTINE work:INTEGER BEGIN FOR i=1 TO 3 DO FOR j=2 TO 3 DO suffix:: RETURN i+j ENDFOR ENDFOR RETURN 9 END work'
        program,_=compile_program('result=work()',decl=DECL,routines=routine);values=program.run()
        self.assertEqual((values['RESULT'],values['I'],values['J']),(3,UNKNOWN,UNKNOWN))
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))

    def test_parameterized_routine_uses_fresh_local_counter_and_preserves_global(self):
        routine='ROUTINE work(value:INTEGER):INTEGER VAR local_count:INTEGER BEGIN FOR local_count=1 TO 2 DO suffix:: RETURN value+local_count ENDFOR RETURN 9 END work'
        values=execute('i=8 result=work(6)',routines=routine)
        self.assertEqual((values['RESULT'],values['I']),(7,8))

    def test_recursive_routine_invocations_have_independent_for_frames(self):
        routine='ROUTINE work(depth:INTEGER):INTEGER VAR local_count,total_value:INTEGER BEGIN IF depth=0 THEN RETURN 0 ENDIF total_value=0 FOR local_count=1 TO 2 DO suffix:: total_value=total_value+1 total_value=total_value+work(depth-1) GOTO done ENDFOR done:: RETURN total_value END work'
        values=execute('result=work(3)',routines=routine)
        self.assertEqual(values['RESULT'],3)


class ForJumpFailureAndLifetimeTests(unittest.TestCase):
    def test_initial_expression_failure_preserves_previous_own_counter(self):
        program,_=compile_program('i=9 FOR i=n TO 2 DO suffix:: total=i ENDFOR',decl=DECL)
        with self.assertRaises(rt.KarelRuntimeError):program.run()
        self.assertEqual(program.snapshot()['I'],9)

    def test_nested_initial_failure_clears_outer_and_preserves_inner_old_value(self):
        program,_=compile_program('j=9 FOR i=1 TO 2 DO FOR j=n TO 2 DO suffix:: total=i ENDFOR ENDFOR',decl=DECL)
        with self.assertRaises(rt.KarelRuntimeError):program.run()
        self.assertEqual((program.snapshot()['I'],program.snapshot()['J']),(UNKNOWN,9))

    def test_final_bound_failure_clears_initialized_counter(self):
        program,_=compile_program('i=9 FOR i=1 TO n DO suffix:: total=i ENDFOR',decl=DECL)
        with self.assertRaises(rt.KarelRuntimeError):program.run()
        self.assertEqual(program.snapshot()['I'],UNKNOWN)

    def test_body_failure_clears_all_active_counters(self):
        program,_=compile_program('FOR i=1 TO 2 DO FOR j=1 TO 2 DO suffix:: total=7 n=1 DIV 0 ENDFOR ENDFOR',decl=DECL)
        with self.assertRaises(rt.KarelRuntimeError):program.run()
        self.assertEqual((program.snapshot()['TOTAL'],program.snapshot()['I'],program.snapshot()['J']),(7,UNKNOWN,UNKNOWN))

    def test_abort_unwinds_counters_and_preserves_prior_non_counter_effects(self):
        program,_=compile_program('FOR i=1 TO 2 DO suffix:: total=7 ABORT ENDFOR',decl=DECL)
        with self.assertRaises(rt.KarelAbort):program.run()
        self.assertEqual((program.snapshot()['TOTAL'],program.snapshot()['I']),(7,UNKNOWN))

    def test_same_iteration_cycle_is_bounded_and_clears_counter(self):
        program,_=compile_program('FOR i=1 TO 2 DO suffix:: GOTO suffix ENDFOR',decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):program.run(max_steps=12)
        self.assertEqual(program.snapshot()['I'],UNKNOWN)

    def test_write_callback_failure_unwinds_registered_for_scope(self):
        def fail(request):raise RuntimeError('authored writer failure')
        program,_=compile_program('FOR i=1 TO 2 DO suffix:: WRITE(i) ENDFOR',decl=DECL,write=fail)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'writer failure'):program.run()
        self.assertEqual(program.snapshot()['I'],UNKNOWN)

    def test_read_validation_failure_unwinds_registered_for_scope(self):
        program,_=compile_program('FOR i=1 TO 2 DO suffix:: READ(total) ENDFOR',decl=DECL,read=lambda request:['bad'])
        with self.assertRaises(rt.KarelRuntimeError):program.run()
        self.assertEqual(program.snapshot()['I'],UNKNOWN)

    def test_call_depth_failure_clears_counter_and_every_routine_frame(self):
        program,_=compile_program('FOR i=1 TO 2 DO suffix:: recurse ENDFOR',decl=DECL,
            routines='ROUTINE recurse BEGIN recurse END recurse')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'depth'):program.run()
        self.assertEqual(program.snapshot()['I'],UNKNOWN);self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))

    def test_cooperative_pause_resume_preserves_iterator_and_current_counter(self):
        program,_=compile_program('total=0 FOR i=1 TO 2 DO suffix:: total=total+i IF i=1 THEN PAUSE ENDIF GOTO body_end body_end:: ENDFOR',decl=DECL,cooperative=True)
        with self.assertRaises(rt.KarelPause):program.run()
        self.assertEqual((program.snapshot()['I'],program.snapshot()['TOTAL']),(1,1))
        values=program.resume();self.assertEqual((values['I'],values['TOTAL']),(UNKNOWN,3))

    def test_stopping_paused_nested_for_clears_both_counters(self):
        program,_=compile_program('FOR i=1 TO 2 DO FOR j=1 TO 2 DO suffix:: PAUSE ENDFOR ENDFOR',decl=DECL,cooperative=True)
        with self.assertRaises(rt.KarelPause):program.run()
        self.assertEqual((program.snapshot()['I'],program.snapshot()['J']),(1,1))
        program.stop();self.assertEqual((program.snapshot()['I'],program.snapshot()['J']),(UNKNOWN,UNKNOWN))

    def test_pause_in_final_bound_retains_cleanup_even_before_iterator_exists(self):
        routine='ROUTINE final_value:INTEGER BEGIN PAUSE RETURN 2 END final_value'
        program,_=compile_program('i=9 FOR i=1 TO final_value() DO suffix:: total=i ENDFOR',decl=DECL,routines=routine,cooperative=True)
        with self.assertRaises(rt.KarelPause):program.run()
        self.assertEqual(program.snapshot()['I'],1)
        program.stop();self.assertEqual(program.snapshot()['I'],UNKNOWN);self.assertEqual(program._state.local_frames,[])

    def test_stop_during_initial_expression_preserves_previous_counter(self):
        routine='ROUTINE first_value:INTEGER BEGIN PAUSE RETURN 1 END first_value'
        program,_=compile_program('i=9 FOR i=first_value() TO 2 DO suffix:: total=i ENDFOR',decl=DECL,routines=routine,cooperative=True)
        with self.assertRaises(rt.KarelPause):program.run()
        self.assertEqual(program.snapshot()['I'],9)
        program.stop();self.assertEqual(program.snapshot()['I'],9)

    def test_cooperative_budget_cycle_cleans_routine_local_scope(self):
        routine='ROUTINE work VAR local_count:INTEGER BEGIN FOR local_count=1 TO 2 DO suffix:: GOTO suffix ENDFOR END work'
        program,_=compile_program('work',decl=DECL,routines=routine,cooperative=True)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):program.run(max_steps=15)
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))


class ForJumpProofTests(unittest.TestCase):
    def reject(self,body,code='E_GOTO_FOR',**options):
        with self.assertRaises(TranslationError) as caught:compile_program(body,decl=options.pop('decl',DECL),**options)
        self.assertEqual(caught.exception.code,code,str(caught.exception))

    def test_entry_to_new_for_scope_is_rejected(self):self.reject('GOTO suffix FOR i=1 TO 2 DO suffix:: total=i ENDFOR')

    def test_entry_to_additional_nested_for_scope_is_rejected(self):self.reject('FOR i=1 TO 2 DO GOTO suffix FOR j=1 TO 2 DO suffix:: total=j ENDFOR ENDFOR')

    def test_entry_to_sibling_for_is_rejected_even_with_the_same_counter(self):self.reject('FOR i=1 TO 2 DO GOTO suffix ENDFOR FOR i=1 TO 2 DO suffix:: total=i ENDFOR')

    def test_completed_for_capture_cannot_be_reentered_from_outside(self):self.reject('FOR i=1 TO 2 DO suffix:: total=i ENDFOR GOTO suffix')

    def test_for_entry_inside_nested_if_is_also_rejected(self):self.reject('GOTO suffix IF FALSE THEN FOR i=1 TO 2 DO IF TRUE THEN suffix:: total=i ENDIF ENDFOR ENDIF')

    def test_new_using_scope_cannot_be_entered_from_an_active_for(self):self.reject('FOR i=1 TO 2 DO GOTO suffix USING items[1] DO suffix:: value=7 ENDUSING ENDFOR','E_GOTO_ENTRY',decl=DECL+' items:ARRAY[2] OF row_t',prefix=SCHEMA)

    def test_active_counter_write_guard_still_applies_at_body_labels(self):self.reject('FOR i=1 TO 2 DO suffix:: i=7 ENDFOR','E_FOR_COUNTER')

    def test_active_counter_read_output_remains_protected(self):self.reject('FOR i=1 TO 2 DO suffix:: READ(i) ENDFOR','E_FOR_COUNTER')

    def test_transitive_global_counter_writes_remain_protected(self):self.reject('FOR i=1 TO 2 DO suffix:: relay ENDFOR','E_FOR_COUNTER',routines='ROUTINE change BEGIN i=7 END change\nROUTINE relay BEGIN change END relay')

    def test_active_counter_mutable_formal_remains_protected(self):self.reject('FOR i=1 TO 2 DO suffix:: change(i) ENDFOR','E_FOR_COUNTER',routines='ROUTINE change(value:INTEGER) BEGIN value=7 END change')

    def test_active_counter_readonly_formal_remains_usable(self):
        values=execute('total=0 FOR i=1 TO 2 DO suffix:: observe(i) ENDFOR',routines='ROUTINE observe(value:INTEGER) BEGIN total=total+value END observe')
        self.assertEqual(values['TOTAL'],3)

    def test_formal_counter_and_parameterized_global_counter_remain_rejected(self):
        for routine in ('ROUTINE work(i:INTEGER) BEGIN FOR i=1 TO 2 DO suffix:: total=i ENDFOR END work',
                        'ROUTINE work(value:INTEGER) BEGIN FOR i=1 TO 2 DO suffix:: total=i ENDFOR END work'):
            self.reject('work(1)','E_FOR_COUNTER',routines=routine)

    def test_nested_loops_cannot_share_the_same_counter(self):self.reject('FOR i=1 TO 2 DO FOR i=1 TO 2 DO suffix:: total=i ENDFOR ENDFOR','E_FOR_COUNTER')

    def test_handler_counter_writes_and_connected_timers_remain_rejected(self):
        for prefix in ('CONDITION[1]: WHEN TRUE DO i=7 ENDCONDITION ', 'CONNECT TIMER TO i '):
            self.reject(prefix+'FOR i=1 TO 2 DO suffix:: total=i ENDFOR','E_FOR_COUNTER',cooperative=True)

    def test_undefined_and_duplicate_labels_inside_for_still_reject(self):
        self.reject('FOR i=1 TO 2 DO GOTO missing ENDFOR','E_LABEL')
        self.reject('FOR i=1 TO 2 DO suffix:: ENDFOR FOR j=1 TO 2 DO suffix:: ENDFOR','E_DUPLICATE_LABEL')

    def test_cross_routine_targets_still_reject(self):self.reject('GOTO suffix','E_LABEL',routines='ROUTINE work BEGIN FOR i=1 TO 2 DO suffix:: total=i ENDFOR END work')

    def test_legacy_for_jump_and_label_restrictions_are_preserved(self):
        for body in ('FOR i=1 TO 2 DO suffix:: total=i ENDFOR','FOR i=1 TO 2 DO GOTO done ENDFOR done::'):
            with self.assertRaises(TranslationError) as caught:legacy_translate('PROGRAM T VAR i,total:INTEGER BEGIN '+body+' END T')
            self.assertEqual(caught.exception.code,'E_GOTO_FOR')

    def test_unreachable_labelled_for_body_still_receives_type_checks(self):self.reject('GOTO done FOR i=1 TO 2 DO suffix:: total=TRUE ENDFOR done::','E_TYPE')


class ForJumpReportAndProjectTests(unittest.TestCase):
    def test_report_describes_scope_graph_and_inner_to_outer_exit_order(self):
        _,translation=compile_program('FOR i=1 TO 2 DO FOR j=1 TO 2 DO GOTO done ENDFOR ENDFOR done::',decl=DECL)
        report=translation.report;graph=report['control_flow']['program']
        self.assertEqual(report['control_flow']['jump_policy'],'body_labels_no_new_for_or_using')
        self.assertEqual({row['counter'] for row in graph['for_scopes']},{'I','J'})
        kinds={row['kind'] for row in graph['nodes']};self.assertTrue({'for_enter','for_next','for_exit'}<=kinds)
        transfer=graph['jumps'][0];self.assertEqual(transfer['retained_for_scopes'],[])
        self.assertEqual(transfer['exited_for_scopes'],list(reversed([block for block in transfer['source']['blocks'] if block.startswith('for@')])))
        self.assertFalse(report['for_jump_policy']['controller_validated'])

    def test_report_lists_the_outer_scope_retained_after_inner_exit(self):
        _,translation=compile_program('FOR i=1 TO 2 DO FOR j=1 TO 2 DO GOTO next_outer ENDFOR next_outer:: total=i ENDFOR',decl=DECL)
        transfer=translation.report['control_flow']['program']['jumps'][0]
        self.assertEqual((len(transfer['retained_for_scopes']),len(transfer['exited_for_scopes'])),(1,1))

    def test_include_source_map_preserves_physical_for_and_target_origins(self):
        translation=translate("PROGRAM T VAR i,total:INTEGER BEGIN\n%INCLUDE loop_body\nEND T",filename='main.kl',
            includes={'loop_body.kl':'FOR i=1 TO 2 DO\nsuffix:: total=i\nGOTO done\nENDFOR\ndone::'})
        namespace={'__name__':'for_include'};exec(translation.python_source,namespace)
        self.assertEqual(namespace['Program']().run()['I'],UNKNOWN)
        nodes=translation.report['control_flow']['program']['nodes']
        target=next(row for row in nodes if row['kind']=='for_enter')['karel_line']
        self.assertTrue(any(row['karel_line']==target and row.get('source_file','').lower().endswith('loop_body.kl') for row in translation.report['source_map']))

    def test_linked_call_has_independent_local_for_state_and_cleans_caller_counter(self):
        sources={'main':'PROGRAM MAIN VAR i,total:INTEGER ROUTINE work:INTEGER FROM LIB BEGIN total=0 FOR i=1 TO 2 DO total=total+work() ENDFOR END MAIN',
            'lib':'PROGRAM LIB ROUTINE work:INTEGER VAR local_count,total_value:INTEGER BEGIN total_value=0 FOR local_count=1 TO 3 DO IF local_count=3 THEN GOTO done ENDIF total_value=total_value+local_count ENDFOR done:: RETURN total_value END work BEGIN END LIB'}
        instance=translate_project(sources).instantiate();values=instance.run('MAIN')
        self.assertEqual((values['MAIN']['values']['TOTAL'],values['MAIN']['values']['I']),(6,UNKNOWN))
        self.assertTrue(all(not p._state.local_frames for p in instance.programs.values()))

    def test_public_authored_for_jump_example_matches_its_reviewed_result(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'examples/for_jumps.kl').read_text(encoding='utf-8')
        translation=translate(source);namespace={'__name__':'for_jumps_example'};exec(translation.python_source,namespace)
        values=namespace['Program']().run()
        self.assertEqual((values['TOTAL'],values['SKIPPED'],values['I'],values['J']),(6,2,UNKNOWN,UNKNOWN))


if __name__=='__main__':unittest.main()
