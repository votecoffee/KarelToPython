"""Source diagnostics and explicitly scripted KCL completion contracts."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from karel2py import runtime as rt,translate,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


EVENTS=rt.DIAGNOSTIC_CONSTANTS


def diagnostic(**options):return rt.ExecutionContext(diagnostics=rt.DiagnosticLog(**options))


def commands(replies=None,**options):return rt.ExecutionContext(kcl=rt.KclCommands(replies,**options))


def event_names(ctx):return [row['event'] for row in ctx.diagnostics.records]


class DiagnosticStackTests(unittest.TestCase):
    def test_current_logical_stack_and_boolean_initialization(self):
        self.assertEqual(run('CHECK_STACK(TRUE,FALSE,n)',context=diagnostic())['N'],4096)

    def test_integer_initialization_compatibility(self):
        self.assertEqual(run('CHECK_STACK(1,FALSE,n)',context=diagnostic())['N'],4096)

    def test_literal_zero_discards_stack_output(self):
        self.assertEqual(run('CHECK_STACK(TRUE,FALSE,0) CHECK_STACK(FALSE,TRUE,n)',context=diagnostic())['N'],4096)

    def test_low_water_tracks_nested_calls_without_queries_in_deepest_frame(self):
        ctx=diagnostic(stack_words=100,frame_words=10)
        values=run('CHECK_STACK(TRUE,FALSE,n) outer CHECK_STACK(FALSE,TRUE,s)',context=ctx,
            routines='ROUTINE inner BEGIN n=1 END inner ROUTINE outer BEGIN inner END outer')
        self.assertEqual(values['S'],80)

    def test_current_free_stack_returns_after_unwind(self):
        values=run('work CHECK_STACK(FALSE,FALSE,s)',context=diagnostic(stack_words=100,frame_words=10),
            routines='ROUTINE work BEGIN CHECK_STACK(FALSE,FALSE,n) END work')
        self.assertEqual((values['N'],values['S']),(90,100))

    def test_initialization_resets_low_water(self):
        values=run('CHECK_STACK(TRUE,FALSE,n) work CHECK_STACK(TRUE,TRUE,s)',context=diagnostic(stack_words=100,frame_words=10),
            routines='ROUTINE work BEGIN n=1 END work')
        self.assertEqual(values['S'],100)

    def test_low_water_requires_initialization(self):
        p,_=compile_program('n=7 CHECK_STACK(FALSE,TRUE,n)',context=diagnostic())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'initialization'):p.run()
        self.assertEqual(p.snapshot()['N'],7)

    def test_invalid_integer_flag_does_not_write_output(self):
        p,_=compile_program('n=7 CHECK_STACK(2,FALSE,n)',context=diagnostic())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'0/1'):p.run()
        self.assertEqual(p.snapshot()['N'],7)

    def test_exhausted_logical_model_clamps_at_zero_without_changing_call_policy(self):
        values=run('work',context=diagnostic(stack_words=1,frame_words=1),routines='ROUTINE work BEGIN CHECK_STACK(FALSE,FALSE,n) END work')
        self.assertEqual(values['N'],0)

    def test_stack_model_is_separate_for_each_task(self):
        ctx=diagnostic(stack_words=100,frame_words=10)
        project=translate_project({'main':source('MAIN','CHECK_STACK(TRUE,FALSE,n) work CHECK_STACK(FALSE,TRUE,s)',routines='ROUTINE work BEGIN n=1 END work'),
            'worker':source('WORKER','CHECK_STACK(FALSE,TRUE,n)')}).instantiate(context=ctx)
        project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['S'],90)
        with self.assertRaises(rt.KarelRuntimeError):project.run('WORKER')

    def test_stack_output_retains_active_counter_guard(self):
        with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO CHECK_STACK(FALSE,FALSE,n) ENDFOR')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_missing_diagnostic_service_is_explicit(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'diagnostics'):run('CHECK_STACK(TRUE,FALSE,n)')


class DiagnosticEventTests(unittest.TestCase):
    def test_task_enable_and_event_selection_both_required(self):
        ctx=diagnostic();run('SET_DEBUG(TRUE) n=1',context=ctx)
        self.assertEqual(ctx.diagnostics.records,[])
        ctx=diagnostic();run('SET_DB_EVENT(START_K_LINE,TRUE) n=1',context=ctx)
        self.assertEqual(ctx.diagnostics.records,[])

    def test_selected_routine_events_have_task_and_source_module(self):
        ctx=diagnostic();run('SET_DB_EVENT(CALL,TRUE) SET_DB_EVENT(RTN_FRM_RTN,TRUE) SET_DEBUG(TRUE) work',context=ctx,
            routines='ROUTINE work BEGIN n=42 END work')
        self.assertEqual(event_names(ctx),['CALL','RTN_FRM_RTN'])
        self.assertTrue(all(row['task']=='T' and row['program']=='T' and row['depth']==1 for row in ctx.diagnostics.records))

    def test_logging_disable_event_and_later_calls(self):
        ctx=diagnostic();run('SET_DB_EVENT(LOG_ENABLE,TRUE) SET_DB_EVENT(LOG_DISABLE,TRUE) SET_DB_EVENT(CALL,TRUE) SET_DEBUG(TRUE) work SET_DEBUG(FALSE) work',context=ctx,
            routines='ROUTINE work BEGIN n=42 END work')
        self.assertEqual(event_names(ctx),['LOG_ENABLE','CALL','LOG_DISABLE'])

    def test_global_master_disable_is_respected(self):
        ctx=diagnostic(logging_enabled=False,selected=[EVENTS['CALL']]);run('SET_DEBUG(TRUE) work',context=ctx,routines='ROUTINE work BEGIN n=42 END work')
        self.assertEqual(ctx.diagnostics.records,[])

    def test_global_selection_changes_apply_to_other_tasks(self):
        ctx=diagnostic(default_enabled=True)
        instance=translate_project({'main':source('MAIN','SET_DB_EVENT(CALL,TRUE)'),
            'worker':source('WORKER','work',routines='ROUTINE work BEGIN n=42 END work')}).instantiate(context=ctx)
        instance.run('MAIN');instance.run('WORKER')
        self.assertEqual(event_names(ctx),['CALL'])
        self.assertEqual(ctx.diagnostics.records[0]['task'],'WORKER')

    def test_source_checkpoint_labels_are_an_offline_pcode_approximation(self):
        ctx=diagnostic(default_enabled=True,selected=[EVENTS['START_K_LINE'],EVENTS['PCODE_EXEC']])
        run('n=42',context=ctx)
        self.assertEqual(event_names(ctx),['START_K_LINE','PCODE_EXEC'])

    def test_source_program_start_and_end_events(self):
        ctx=diagnostic(default_enabled=True,selected=[EVENTS['TASK_START'],EVENTS['TASK_END']])
        run('n=42',context=ctx)
        self.assertEqual(event_names(ctx),['TASK_START','TASK_END'])

    def test_ring_limit_keeps_latest_records_and_monotonic_sequence(self):
        ctx=diagnostic(limit=2,default_enabled=True,selected=[EVENTS['START_K_LINE']]);run('n=1 n=2 n=3',context=ctx)
        self.assertEqual([r['sequence'] for r in ctx.diagnostics.records],[2,3])

    def test_global_deselection_stops_later_events(self):
        ctx=diagnostic();run('SET_DB_EVENT(CALL,TRUE) SET_DEBUG(TRUE) work SET_DB_EVENT(CALL,FALSE) work',context=ctx,
            routines='ROUTINE work BEGIN n=42 END work')
        self.assertEqual(event_names(ctx),['CALL'])

    def test_linked_module_uses_calling_task_logging_and_stack(self):
        ctx=diagnostic(stack_words=100,frame_words=10,selected=[EVENTS['CALL'],EVENTS['RTN_FRM_RTN']])
        instance=translate_project({'main':source('MAIN','SET_DEBUG(TRUE) CHECK_STACK(TRUE,FALSE,n) s=work() CHECK_STACK(FALSE,TRUE,n)',routines='ROUTINE work:INTEGER FROM LIB'),
            'lib':source('LIB','',routines='ROUTINE work:INTEGER VAR available:INTEGER BEGIN CHECK_STACK(FALSE,FALSE,available) RETURN available END work')}).instantiate(context=ctx)
        values=instance.run('MAIN')['MAIN']['values'];self.assertEqual((values['N'],values['S']),(80,80))
        self.assertEqual([(r['task'],r['program']) for r in ctx.diagnostics.records],[('MAIN','MAIN'),('MAIN','LIB'),('MAIN','LIB'),('MAIN','MAIN')])

    def test_linked_ticks_log_only_the_executing_leaf_module(self):
        ctx=diagnostic(default_enabled=True,selected=[EVENTS['START_K_LINE']])
        instance=translate_project({'main':source('MAIN','n=work()',routines='ROUTINE work:INTEGER FROM LIB'),
            'lib':source('LIB','',routines='ROUTINE work:INTEGER BEGIN RETURN 42 END work')}).instantiate(context=ctx)
        instance.run('MAIN')
        self.assertEqual([row['program'] for row in ctx.diagnostics.records],['MAIN','MAIN','LIB','LIB'])

    def test_pause_does_not_end_logging_activation(self):
        ctx=diagnostic(default_enabled=True,selected=[EVENTS['TASK_START'],EVENTS['TASK_END']])
        p,_=compile_program('n=1 PAUSE n=42',context=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(event_names(ctx),['TASK_START'])
        p.resume();self.assertEqual(event_names(ctx),['TASK_START','TASK_END'])

    def test_abort_unwinds_and_records_a_single_terminal_event(self):
        ctx=diagnostic(default_enabled=True,selected=[EVENTS['TASK_END']])
        p,_=compile_program('work',context=ctx,routines='ROUTINE work BEGIN ABORT END work')
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(event_names(ctx),['TASK_END'])
        self.assertEqual(p._state.local_frames,[])

    def test_unknown_event_is_rejected_without_changing_selected_set(self):
        ctx=diagnostic();p,_=compile_program('SET_DB_EVENT(999,TRUE)',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.diagnostics.selected,set())

    def test_new_run_resets_task_enable_and_stack_watermark(self):
        ctx=diagnostic();p,_=compile_program('IF UNINIT(n) THEN SET_DEBUG(TRUE) CHECK_STACK(TRUE,FALSE,n) ELSE CHECK_STACK(FALSE,TRUE,s) ENDIF',context=ctx)
        p.run()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'initialization'):p.run()


class KclExecutionTests(unittest.TestCase):
    def test_blocking_reply_and_last_status(self):
        ctx=commands({'SHOW PROGRAMS':{'status':17}})
        values=run("KCL('SHOW PROGRAMS',s) n=KCL_STATUS",context=ctx)
        self.assertEqual((values['N'],values['S']),(17,17))
        self.assertEqual(ctx.kcl.history[0]['phase'],'completed')

    def test_explicit_parentheses_for_last_status(self):
        self.assertEqual(run('n=KCL_STATUS()',context=commands(last_status=7))['N'],7)

    def test_only_bare_status_enables_cooperative_generation(self):
        p,_=compile_program('n=KCL_STATUS',context=commands(last_status=7))
        self.assertTrue(callable(getattr(p,'_execute',None)))
        self.assertEqual(p.run()['N'],7)

    def test_unsubmitted_status_is_not_an_invented_success(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'no submitted'):run('n=KCL_STATUS',context=commands())

    def test_unknown_command_returns_portable_unsupported(self):
        ctx=commands();values=run("KCL('UNKNOWN',s) n=KCL_STATUS",context=ctx)
        self.assertEqual((values['N'],values['S']),(1,1))
        self.assertEqual(ctx.kcl.history[0]['phase'],'unsupported')

    def test_rejected_command_returns_acceptance_status(self):
        ctx=commands({'SHOW':{'status':0,'accept_status':19,'delay_ms':100}})
        values=run("KCL_NO_WAIT('SHOW',s) n=KCL_STATUS",context=ctx)
        self.assertEqual((values['N'],values['S']),(19,19))
        self.assertNotIn('pending',ctx.kcl.snapshot())

    def test_no_wait_returns_acceptance_and_status_waits_for_completion(self):
        delays=[];ctx=commands({'SHOW':{'status':17,'delay_ms':5}})
        values=run("KCL_NO_WAIT('SHOW',s) n=KCL_STATUS",context=ctx,clock_us=lambda:0,sleep=delays.append)
        self.assertEqual((values['N'],values['S']),(17,0))
        self.assertEqual(delays,[0.005])

    def test_blocking_command_waits_without_changing_native_resources(self):
        delays=[];ctx=commands({'CLEAR ALL':{'status':0,'delay_ms':3}})
        ctx.variables.define('CACHE','VALUE',('INTEGER',),42)
        run("KCL('CLEAR ALL',s)",context=ctx,clock_us=lambda:0,sleep=delays.append)
        self.assertEqual(delays,[0.003])
        self.assertEqual(ctx.variables.bindings['CACHE','VALUE'].raw(),42)

    def test_pending_channel_rejects_second_submission_as_busy(self):
        ctx=commands({'FIRST':{'status':17,'delay_ms':5},'SECOND':{'status':0}})
        values=run("KCL_NO_WAIT('FIRST',s) KCL('SECOND',s) n=KCL_STATUS",context=ctx,clock_us=lambda:0,sleep=lambda _:None)
        self.assertEqual((values['S'],values['N']),(2,17))
        self.assertEqual([r['phase'] for r in ctx.kcl.history],['completed','busy'])

    def test_completion_can_be_polled_without_resubmitting(self):
        now=[0];ctx=commands({'SHOW':{'status':17,'delay_ms':5}})
        run("KCL_NO_WAIT('SHOW',s)",context=ctx,clock_us=lambda:now[0])
        now[0]=5000;ctx.kcl.poll()
        self.assertEqual(ctx.kcl.last_status,17)
        self.assertEqual(ctx.kcl.sequence,1)

    def test_trimmed_commands_keep_exact_case_and_internal_spacing(self):
        ctx=commands({'SHOW PROGRAMS':{'status':17}})
        values=run("KCL(' SHOW PROGRAMS ',s) KCL('show programs',n)",context=ctx)
        self.assertEqual((values['S'],values['N']),(17,1))

    def test_command_length_and_control_characters_are_rejected_before_history(self):
        for value in ('',' '*3,'x'*127,'a\x00b','a\nb'):
            with self.subTest(value=repr(value)):
                ctx=commands();state=rt.State({}, {},context=ctx)
                with self.assertRaises(rt.KarelRuntimeError):ctx.kcl.submit(state,'KCL',value)
                self.assertEqual(ctx.kcl.history,[])

    def test_missing_kcl_service_is_explicit(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,' kcl'):run("KCL('SHOW',s)")

    def test_active_counter_cannot_receive_kcl_status_output(self):
        with self.assertRaises(TranslationError) as caught:compile_program("FOR n=1 TO 2 DO KCL('SHOW',n) ENDFOR")
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_failed_sleeper_retains_accepted_job_for_later_collection(self):
        ctx=commands({'SHOW':{'status':17,'delay_ms':5}})
        def broken(_):raise RuntimeError('fixture sleeper failure')
        p,_=compile_program("KCL('SHOW',s)",context=ctx,clock_us=lambda:0,sleep=broken)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIn('pending',ctx.kcl.snapshot());self.assertEqual(ctx.kcl.sequence,1)
        self.assertEqual(run('n=KCL_STATUS',context=ctx,sleep=lambda _:None)['N'],17)
        self.assertEqual(ctx.kcl.sequence,1)

    def test_scheduler_tasks_share_the_channel_and_wait_for_one_accepted_job(self):
        ctx=commands({'FIRST':{'status':17,'delay_ms':10},'SECOND':{'status':23}})
        instance=translate_project({'main':source('MAIN',"RUN_TASK('WORKER',0,FALSE,FALSE,0,s) KCL('FIRST',s)"),
            'worker':source('WORKER',"DELAY 3 KCL_NO_WAIT('SECOND',s) n=KCL_STATUS")}).instantiate(context=ctx)
        values=instance.run('MAIN')
        self.assertEqual(values['MAIN']['values']['S'],17)
        self.assertEqual((values['WORKER']['values']['S'],values['WORKER']['values']['N']),(2,17))
        self.assertEqual(ctx.kcl.sequence,2)

    def test_status_function_in_expression_does_not_submit_again(self):
        ctx=commands({'SHOW':{'status':17}})
        self.assertEqual(run("KCL('SHOW',s) n=KCL_STATUS+KCL_STATUS()",context=ctx)['N'],34)
        self.assertEqual(ctx.kcl.sequence,1)

    def test_zero_delay_reply_needs_no_clock_or_sleeper(self):
        def forbidden(*_):raise AssertionError('zero-delay reply must not touch the host clock')
        ctx=commands({'SHOW':{'status':17}})
        self.assertEqual(run("KCL('SHOW',s)",context=ctx,clock_us=forbidden,sleep=forbidden)['S'],17)

    def test_accepted_job_survives_program_stop_without_retry(self):
        ctx=commands({'SHOW':{'status':17,'delay_ms':5}})
        p,_=compile_program("KCL_NO_WAIT('SHOW',s) PAUSE",context=ctx,clock_us=lambda:0)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertIn('pending',ctx.kcl.snapshot())
        self.assertEqual(run('n=KCL_STATUS',context=ctx,sleep=lambda _:None)['N'],17)
        self.assertEqual(ctx.kcl.sequence,1)

    def test_scheduler_wait_uses_virtual_time(self):
        ctx=commands({'SHOW':{'status':17,'delay_ms':10}})
        instance=translate_project({'main':source('MAIN',"KCL('SHOW',s) n=KCL_STATUS")}).instantiate(context=ctx)
        result=instance.run('MAIN')['MAIN']['values']
        self.assertEqual((result['S'],result['N']),(17,17))
        self.assertGreaterEqual(instance.scheduler.now_us,10000)


class ServiceConfigurationTests(unittest.TestCase):
    def test_completed_context_roundtrip_keeps_history_and_global_selections(self):
        ctx=rt.ExecutionContext(diagnostics=rt.DiagnosticLog(),kcl=rt.KclCommands({'SHOW':{'status':17}}))
        run("SET_DB_EVENT(CALL,TRUE) SET_DEBUG(TRUE) work KCL('SHOW',s)",context=ctx,routines='ROUTINE work BEGIN n=42 END work')
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.diagnostics.to_config(),ctx.diagnostics.to_config())
        self.assertEqual(restored.kcl.to_config(),ctx.kcl.to_config())

    def test_pending_command_cannot_be_serialized_or_replayed_implicitly(self):
        ctx=commands({'SHOW':{'status':17,'delay_ms':10}})
        run("KCL_NO_WAIT('SHOW',s)",context=ctx,clock_us=lambda:0)
        with self.assertRaisesRegex(ValueError,'pending KCL'):ctx.to_config()
        self.assertIn('pending',ctx.kcl.snapshot())

    def test_task_watermark_is_not_restored_as_a_live_activation(self):
        ctx=diagnostic();run('CHECK_STACK(TRUE,FALSE,n)',context=ctx)
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'initialization'):run('CHECK_STACK(FALSE,TRUE,n)',context=restored)

    def test_copied_snapshots_do_not_expose_service_owned_objects(self):
        ctx=commands({'SHOW':{'status':17}});run("KCL('SHOW',s)",context=ctx)
        config=ctx.kcl.snapshot();config['history'][0]['status']=99;config['replies']['SHOW']['status']=99
        self.assertEqual((ctx.kcl.history[0]['status'],ctx.kcl.replies['SHOW']['status']),(17,17))

    def test_history_ring_is_bounded(self):
        ctx=commands({'SHOW':{'status':0}},limit=2)
        run("KCL('SHOW',s) KCL('SHOW',s) KCL('SHOW',s)",context=ctx)
        self.assertEqual([row['sequence'] for row in ctx.kcl.history],[2,3])

    def test_sequence_exhaustion_cannot_submit_again(self):
        ctx=commands({'SHOW':{'status':0}},sequence=2147483646)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'exhausted'):run("KCL('SHOW',s)",context=ctx)
        self.assertEqual(ctx.kcl.history,[])

    def test_diagnostic_configuration_rejects_invalid_values(self):
        for options in ({'limit':0},{'stack_words':True},{'frame_words':5000},{'selected':[999]},
                        {'selected':[{}]},{'selected':[4,4]},{'default_enabled':1},{'records':[{}]}):
            with self.subTest(options=options),self.assertRaises(ValueError):rt.DiagnosticLog(**options)

    def test_kcl_configuration_rejects_invalid_replies(self):
        for replies in ({'SHOW':{}},{'SHOW':{'status':True}},{'SHOW':{'status':2147483647}},
                        {'SHOW':{'status':0,'delay_ms':-1}},{'SHOW':{'status':0,'extra':0}},
                        {' SHOW':{'status':0},'SHOW':{'status':0}}):
            with self.subTest(replies=replies),self.assertRaises(ValueError):rt.KclCommands(replies)

    def test_unknown_context_and_service_fields_are_not_ignored(self):
        for config in ({'diagnostics':{'extra':0}},{'kcl':{'pending':{}}}):
            with self.subTest(config=config),self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)

    def test_services_require_their_exact_explicit_types(self):
        for options in ({'diagnostics':{}},{'kcl':{}}):
            with self.subTest(options=options),self.assertRaises(TypeError):rt.ExecutionContext(**options)

    def test_native_log_ids_are_not_claimed(self):
        self.assertEqual(set(EVENTS),{'LOG_ENABLE','LOG_DISABLE','START_K_LINE','CALL','RTN_FRM_RTN','TASK_START','TASK_END','PCODE_EXEC'})
        self.assertEqual(len(set(EVENTS.values())),len(EVENTS))
