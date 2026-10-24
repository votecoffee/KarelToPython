"""Authored portable policies, scheduling, notifications, tracing and directives."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate, translate_project, runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program, run
from tests.test_project_scheduler import source
from tests.test_task_inspection import registry, query


ROOT=Path(__file__).resolve().parents[1]


class TaskSettingTests(unittest.TestCase):
    def test_all_nine_attributes_can_be_written_and_inspected(self):
        values={'TSK_PRIORITY':20,'TSK_TIMESLIC':3,'TSK_NOBUSY':1,'TSK_NOABORT':3,
                'TSK_NOPAUSE':13,'TSK_TRACE':1,'TSK_TRACELEN':7,'TSK_TPMOTION':1,'TSK_PAUSESFT':0}
        for kind in (rt.TaskRegistry,rt.TaskScheduler):
            ctx,worker=registry(kind=kind)
            for attribute,value in values.items():
                with self.subTest(kind=kind,attribute=attribute):
                    self.assertEqual(run(f"SET_TSK_ATTR('WoRkEr',{attribute},{value},s)",context=ctx)['S'],0)
                    self.assertEqual(query(ctx,attribute)['VALUE'],value)
            self.assertEqual(worker.task_state,'ready')
            self.assertEqual(worker.task_settings,values)

    def test_invalid_value_never_changes_prior_setting(self):
        invalid={'TSK_PRIORITY':(0,100),'TSK_TIMESLIC':(0,1001),'TSK_NOBUSY':(-1,2),
                 'TSK_NOABORT':(-1,4),'TSK_NOPAUSE':(2,3,6,14),'TSK_TRACE':(-1,2),
                 'TSK_TRACELEN':(0,10001),'TSK_TPMOTION':(-1,2),'TSK_PAUSESFT':(-1,2)}
        ctx,worker=registry()
        for key,values in invalid.items():
            for value in values:
                with self.subTest(attribute=key,value=value):
                    self.assertEqual(ctx.tasks.set_attribute('worker',key,value),2)
                    self.assertEqual(worker.task_settings,{})

    def test_unknown_and_readonly_attributes_have_distinct_statuses(self):
        ctx,worker=registry()
        self.assertEqual(ctx.tasks.set_attribute('worker',999,1),2)
        self.assertEqual(ctx.tasks.set_attribute('worker','unknown',1),2)
        self.assertEqual(ctx.tasks.set_attribute('worker','TSK_STATUS',1),3)
        self.assertEqual(worker.task_settings,{})

    def test_missing_and_ambiguous_self_lookup(self):
        ctx,worker=registry("SET_TSK_ATTR('',TSK_TRACE,1,s)")
        self.assertEqual(run("SET_TSK_ATTR('',TSK_TRACE,1,s)",context=ctx)['S'],3)
        self.assertEqual(run("SET_TSK_ATTR('absent',TSK_TRACE,1,s)",context=ctx)['S'],1)
        ctx.tasks.bind('alias',worker)
        self.assertEqual(worker.run()['S'],3)

    def test_aliases_share_applied_task_policy(self):
        ctx,worker=registry(attributes={'TSK_PRIORITY':80})
        ctx.tasks.bind('alias',worker,attributes={'TSK_PRIORITY':90})
        self.assertEqual(ctx.tasks.set_attribute('alias','TSK_PRIORITY',10),0)
        self.assertEqual(query(ctx,'TSK_PRIORITY')['VALUE'],10)
        self.assertEqual(ctx.tasks.attributes['WORKER']['TSK_PRIORITY'],80)
        self.assertEqual(ctx.tasks.rename('alias','new'),0)
        self.assertEqual(query(ctx,'TSK_PRIORITY',setup="name='new' number=0")['VALUE'],10)

    def test_bound_metadata_remains_informational_until_explicit_write(self):
        ctx,worker=registry(attributes={'TSK_NOABORT':3,'TSK_TRACE':1})
        self.assertEqual(worker.task_settings,{})
        rt.request_task_control(worker._state,'ABORT')
        self.assertEqual(worker.task_state,'aborted')

    def test_foreign_active_scheduler_write_is_rejected(self):
        ctx,worker=registry('PAUSE n=2',kind=rt.TaskScheduler)
        ctx.tasks.start('worker');ctx.tasks.run()
        foreign=rt.TaskRegistry();foreign.bind('alias',worker)
        self.assertEqual(foreign.set_attribute('alias','TSK_PRIORITY',1),3)
        self.assertEqual(worker.task_settings,{})

    def test_host_api_exact_types_and_case_insensitive_attribute_names(self):
        ctx,worker=registry()
        for attribute,value in ((True,1),('TSK_TRACE',True),('TSK_TRACE',1.5)):
            with self.subTest(attribute=attribute,value=value),self.assertRaises(rt.KarelRuntimeError):ctx.tasks.set_attribute('worker',attribute,value)
        self.assertEqual(ctx.tasks.set_attribute('worker','tsk_priority',5),0)
        self.assertEqual(worker.task_settings['TSK_PRIORITY'],5)

    def test_live_policies_and_trace_are_not_value_persistence(self):
        ctx,worker=registry();ctx.tasks.set_attribute('worker','TSK_TRACE',1);worker.run()
        config=ctx.to_config()
        self.assertNotIn('tasks',config);self.assertNotIn('task_settings',config);self.assertNotIn('task_trace',config)
        self.assertEqual(rt.ExecutionContext.from_config(config).tasks.tasks,{})


class TaskDirectiveTests(unittest.TestCase):
    def test_seven_directives_initialize_policy_and_auto_cooperative_mode(self):
        header='%PRIORITY=20\n%TIMESLICE=3\n%NOABORT=ERROR+COMMAND\n%NOPAUSE=ERROR+COMMAND+TPENABLE\n%NOBUSYLAMP\n%NOPAUSESHFT\n%TPMOTION'
        p,result=compile_program('n=7',prefix=header)
        self.assertTrue(result.report['cooperative_execution'])
        self.assertEqual(p.task_settings,{'TSK_PRIORITY':20,'TSK_TIMESLIC':3,'TSK_NOABORT':3,'TSK_NOPAUSE':13,'TSK_NOBUSY':1,'TSK_PAUSESFT':0,'TSK_TPMOTION':1})
        self.assertEqual(p.run()['N'],7)

    def test_mask_order_case_and_comments(self):
        p,_=compile_program('n=1',prefix='%noabort = command + error -- comment\n%nopause = tpenable + error')
        self.assertEqual(p.source_directives,(('%NOABORT',3),('%NOPAUSE',9)))

    def test_flags_ranges_and_duplicates_fail_during_translation(self):
        cases=('%PRIORITY=0','%PRIORITY=100','%TIMESLICE=0','%TIMESLICE=1001',
               '%PRIORITY=1+2','%TIMESLICE=1.5','%PRIORITY=-1','%NOBUSYLAMP=1',
               '%NOPAUSESHFT yes','%TPMOTION=TRUE','%NOABORT=TPENABLE',
               '%NOABORT=ERROR+ERROR','%NOPAUSE=UNKNOWN','%NOPAUSE=1',
               '%NOPAUSE=ERROR+','%TIMESLICE=2\n%TIMESLICE=3')
        for directive in cases:
            with self.subTest(directive=directive),self.assertRaises(TranslationError):compile_program('n=1',prefix=directive)

    def test_task_directive_after_declarations_is_rejected(self):
        with self.assertRaises(TranslationError) as caught:translate('PROGRAM T VAR n: INTEGER\n%PRIORITY=1\nBEGIN n=1 END T')
        self.assertEqual(caught.exception.code,'E_DIRECTIVE_POSITION')

    def test_library_directives_do_not_replace_calling_root_policy(self):
        main='PROGRAM MAIN\n%PRIORITY=20\nVAR n,s: INTEGER\nROUTINE f FROM LIB\nBEGIN f() END MAIN'
        library="PROGRAM LIB\n%PRIORITY=90\nVAR n,s: INTEGER\nROUTINE f BEGIN SET_TSK_ATTR('',TSK_NOABORT,PG_NP_CMD,s) END f\nBEGIN END LIB"
        instance=translate_project({'main':main,'lib':library}).instantiate();instance.run('MAIN')
        self.assertEqual(instance.programs['MAIN'].task_settings,{'TSK_PRIORITY':20,'TSK_NOABORT':2})
        self.assertEqual(instance.programs['LIB'].task_settings,{'TSK_PRIORITY':90})


class TaskNotificationPolicyTests(unittest.TestCase):
    def test_command_masks_suppress_remote_named_and_numeric_requests(self):
        ctx,worker=registry('PAUSE n=2',kind=rt.TaskScheduler)
        ctx.tasks.set_attribute('worker','TSK_NOABORT',2);ctx.tasks.set_attribute('worker','TSK_NOPAUSE',4)
        ctx.tasks.start('worker')
        for command in ("ABORT_TASK('worker',TRUE,FALSE,s)","PAUSE_TASK('worker',FALSE,FALSE,s)",'PAUSE PROGRAM[1]'):
            run(command,context=ctx,cooperative=True)
            self.assertFalse(worker._state._abort_requested);self.assertFalse(worker._state._pause_requested)
        worker.pause();self.assertFalse(worker._state._pause_requested)
        ctx.tasks.run();self.assertEqual(worker.task_state,'paused')
        ctx.tasks.continue_task('worker');ctx.tasks.run();self.assertEqual(worker.snapshot()['N'],2)

    def test_self_named_requests_obey_masks_but_bare_statements_do_not(self):
        for request,setting,value in (("ABORT_TASK('worker',TRUE,FALSE,s)",'TSK_NOABORT',2),("PAUSE_TASK('worker',FALSE,FALSE,s)",'TSK_NOPAUSE',4)):
            with self.subTest(request=request):
                ctx,worker=registry(request+' n=7')
                ctx.tasks.set_attribute('worker',setting,value)
                self.assertEqual(worker.run()['N'],7)
        for statement,error in (('ABORT',rt.KarelAbort),('PAUSE',rt.KarelPause)):
            ctx,worker=registry(statement)
            ctx.tasks.set_attribute('worker','TSK_NOABORT',3);ctx.tasks.set_attribute('worker','TSK_NOPAUSE',13)
            with self.subTest(statement=statement),self.assertRaises(error):worker.run()

    def test_numeric_self_requests_obey_applied_command_masks(self):
        for command,key,value in (('ABORT PROGRAM[1]','TSK_NOABORT',2),('PAUSE PROGRAM[1]','TSK_NOPAUSE',4)):
            with self.subTest(command=command):
                ctx,worker=registry(command+' n=7')
                ctx.tasks.set_attribute('worker',key,value)
                self.assertEqual(worker.run()['N'],7)

    def test_error_mask_preserves_error_record_and_handler_notifications(self):
        for severity,directive in ((1,'%NOPAUSE=ERROR'),(2,'%NOABORT=ERROR')):
            with self.subTest(severity=severity):
                ctx=rt.ExecutionContext()
                state=run(f"n=0 CONDITION[1]: WHEN ERROR[7] DO n=8 ENDCONDITION ENABLE CONDITION[1] POST_ERR(7,'authored',0,{severity}) s=n",prefix=directive,context=ctx)
                self.assertEqual((state['N'],state['S']),(8,8))
                self.assertEqual((ctx.errors.records[-1]['code'],ctx.errors.records[-1]['severity']),(7,severity))

    def test_command_and_error_masks_remain_independent(self):
        ctx,worker=registry('PAUSE n=2')
        ctx.tasks.set_attribute('worker','TSK_NOABORT',1)
        rt.request_task_control(worker._state,'ABORT',origin='command')
        self.assertEqual(worker.task_state,'aborted')
        ctx,worker=registry('PAUSE n=2')
        ctx.tasks.set_attribute('worker','TSK_NOABORT',2)
        rt.request_task_control(worker._state,'ABORT',origin='error')
        self.assertEqual(worker.task_state,'aborted')

    def test_runtime_failure_and_host_stop_are_never_suppressed(self):
        ctx,worker=registry('n=1 DIV 0')
        ctx.tasks.set_attribute('worker','TSK_NOABORT',3)
        with self.assertRaises(rt.KarelRuntimeError):worker.run()
        self.assertEqual(worker.task_state,'failed')
        worker.stop();self.assertEqual(worker.task_state,'stopped')

    def test_explicit_shift_and_tp_enable_events_use_distinct_settings(self):
        ctx,worker=registry()
        ctx.tasks.set_attribute('worker','TSK_PAUSESFT',0)
        rt.request_task_control(worker._state,'PAUSE',origin='shift')
        self.assertFalse(worker._state._pause_requested)
        rt.request_task_control(worker._state,'PAUSE',origin='tpenable')
        self.assertTrue(worker._state._pause_requested);worker._state._pause_requested=False
        ctx.tasks.set_attribute('worker','TSK_NOPAUSE',8)
        rt.request_task_control(worker._state,'PAUSE',origin='tpenable')
        self.assertFalse(worker._state._pause_requested)

    def test_bad_origin_leaves_pending_state_unchanged(self):
        ctx,worker=registry()
        with self.assertRaises(rt.KarelRuntimeError):rt.request_task_control(worker._state,'PAUSE',origin='unknown')
        self.assertFalse(worker._state._pause_requested)


class TaskTraceTests(unittest.TestCase):
    def test_enable_trace_capacity_trimming_and_defensive_snapshots(self):
        ctx,worker=registry('n=0 WHILE n<10 DO n=n+1 ENDWHILE')
        self.assertEqual(ctx.tasks.set_attribute('worker','TSK_TRACE',1),0)
        self.assertEqual(query(ctx,'TSK_TRACELEN')['VALUE'],1000)
        ctx.tasks.set_attribute('worker','TSK_TRACELEN',5);worker.run()
        trace=worker.task_trace
        self.assertEqual(len(trace),5)
        self.assertGreater(trace[0]['sequence'],1)
        self.assertTrue(all(set(row)=={'sequence','program','routine','line'} for row in trace))
        trace[0]['program']='changed';self.assertEqual(worker.task_trace[0]['program'],'T')
        settings=worker.task_settings;settings['TSK_TRACELEN']=999
        self.assertEqual(worker.task_settings['TSK_TRACELEN'],5)
        ctx.tasks.set_attribute('worker','TSK_TRACELEN',2)
        self.assertEqual(len(worker.task_trace),2)

    def test_trace_disable_retains_history_and_new_run_resets_sequence(self):
        ctx,worker=registry('n=1 PAUSE n=2')
        ctx.tasks.set_attribute('worker','TSK_TRACE',1)
        with self.assertRaises(rt.KarelPause):worker.run()
        trace=worker.task_trace
        ctx.tasks.set_attribute('worker','TSK_TRACE',0);worker.resume()
        self.assertEqual(worker.task_trace,trace)
        ctx.tasks.set_attribute('worker','TSK_TRACE',1)
        with self.assertRaises(rt.KarelPause):worker.run()
        self.assertEqual(worker.task_trace[0]['sequence'],1)

    def test_linked_routine_trace_uses_caller_buffer_and_library_source(self):
        library=source('LIB','',routines='ROUTINE work BEGIN n=1 PAUSE n=2 END work')
        main=source('MAIN','work()',routines='ROUTINE work FROM LIB')
        instance=translate_project({'main':main,'lib':library}).instantiate()
        instance.scheduler.set_attribute('MAIN','TSK_TRACE',1)
        instance.run('MAIN')
        trace=instance.programs['MAIN'].task_trace
        self.assertTrue(any(row['program']=='LIB' and row['routine']=='WORK' for row in trace))
        self.assertEqual(instance.programs['LIB'].task_trace,())
        instance.scheduler.rename('MAIN','NEW');before=len(trace)
        instance.scheduler.continue_task('NEW');instance.scheduler.run()
        self.assertGreater(len(instance.programs['MAIN'].task_trace),before)


class TaskSchedulingPolicyTests(unittest.TestCase):
    def workers(self):
        scheduler=rt.TaskScheduler();ctx=rt.ExecutionContext(tasks=scheduler);seen=[]
        workers=[]
        for name in ('first','second'):
            worker,_=compile_program('n=0 WHILE n<3 DO WRITE(n) n=n+1 ENDWHILE',context=ctx,cooperative=True,write=lambda text,name=name:seen.append((name,text)))
            scheduler.bind(name,worker);workers.append(worker)
        return scheduler,workers,seen

    def test_priority_orders_turns_without_renumbering(self):
        scheduler,workers,seen=self.workers()
        scheduler.set_attribute('second','TSK_PRIORITY',1)
        scheduler.start('first');scheduler.start('second');scheduler.run()
        self.assertEqual([name for name,_ in seen[:2]],['second','first'])
        self.assertEqual(list(scheduler.tasks),['FIRST','SECOND'])
        self.assertEqual([worker.snapshot()['N'] for worker in workers],[3,3])

    def test_time_slice_budget_advances_more_checkpoints_without_advancing_clock(self):
        scheduler,workers,_=self.workers()
        scheduler.set_attribute('second','TSK_TIMESLIC',8)
        scheduler.start('first');scheduler.start('second');scheduler.step()
        self.assertGreater(workers[1]._state.steps,workers[0]._state.steps)
        self.assertEqual(scheduler.now_us,1000)
        scheduler.run();self.assertEqual([worker.snapshot()['N'] for worker in workers],[3,3])

    def test_sleep_pause_and_completion_end_weighted_turn(self):
        for body,state in (('DELAY 50 n=1','waiting'),('PAUSE n=1','paused'),('n=1','completed')):
            with self.subTest(body=body):
                ctx,worker=registry(body,kind=rt.TaskScheduler)
                ctx.tasks.set_attribute('worker','TSK_TIMESLIC',1000)
                ctx.tasks.start('worker');ctx.tasks.step()
                self.assertEqual(worker.task_state,state)

    def test_weighted_self_rename_preserves_wait_key_and_failures(self):
        ctx,worker=registry("SET_TSK_NAME('','new',s) DELAY 10 n=1",kind=rt.TaskScheduler)
        ctx.tasks.set_attribute('worker','TSK_TIMESLIC',100)
        ctx.tasks.start('worker');ctx.tasks.step()
        self.assertEqual(list(ctx.tasks.waiting),['NEW'])
        ctx.tasks.run();self.assertEqual(worker.snapshot()['N'],1)

    def test_weighted_turn_keeps_step_budget_enforcement(self):
        ctx,worker=registry('WHILE TRUE DO ENDWHILE',kind=rt.TaskScheduler)
        ctx.tasks.max_steps=20
        ctx.tasks.set_attribute('worker','TSK_TIMESLIC',1000)
        ctx.tasks.start('worker')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):ctx.tasks.step()
        self.assertEqual(worker.task_state,'failed')

    def test_weighted_turn_uses_connected_virtual_time(self):
        ctx,worker=registry('n=0 CONNECT TIMER TO n DELAY 10 s=n',kind=rt.TaskScheduler)
        ctx.tasks.set_attribute('worker','TSK_TIMESLIC',1000)
        ctx.tasks.start('worker');ctx.tasks.run()
        self.assertEqual(worker.snapshot()['S'],10)

    def test_source_policies_can_be_overridden_without_mutating_directives(self):
        ctx,worker=registry('n=1',prefix='%PRIORITY=70\n%TIMESLICE=3',kind=rt.TaskScheduler)
        ctx.tasks.set_attribute('worker','TSK_PRIORITY',2)
        self.assertEqual(query(ctx,'TSK_PRIORITY')['VALUE'],2)
        self.assertEqual(query(ctx,'TSK_TIMESLIC')['VALUE'],3)
        self.assertEqual(worker.source_directives,(('%PRIORITY',70),('%TIMESLICE',3)))


class TaskSettingSourceChecks(unittest.TestCase):
    def test_exact_types_arity_and_writable_status(self):
        for call in ("SET_TSK_ATTR('a',TSK_TRACE,1)","SET_TSK_ATTR('a',TSK_TRACE,1,s,s)","SET_TSK_ATTR(1,TSK_TRACE,1,s)","SET_TSK_ATTR('a',TRUE,1,s)","SET_TSK_ATTR('a',TSK_TRACE,TRUE,s)","SET_TSK_ATTR('a',TSK_TRACE,1,0)"):
            with self.subTest(call=call),self.assertRaises(TranslationError):compile_program(call)

    def test_direct_transitive_and_handler_counter_guards(self):
        call="SET_TSK_ATTR('worker',TSK_TRACE,1,s)"
        for body,routines in ((f'FOR s=1 TO 2 DO {call} ENDFOR',''),('FOR s=1 TO 2 DO change() ENDFOR',f'ROUTINE change BEGIN {call} END change'),(f'CONDITION[1]: WHEN TRUE DO {call} ENDCONDITION FOR s=1 TO 2 DO ENDFOR','')):
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught:compile_program(body,routines=routines)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_arguments_and_selector_evaluate_once_in_source_order(self):
        ctx,_=registry()
        routines="ROUTINE target: STRING BEGIN order=order*10+1 RETURN 'worker' END target ROUTINE attr: INTEGER BEGIN order=order*10+2 RETURN TSK_PRIORITY END attr ROUTINE value: INTEGER BEGIN order=order*10+3 RETURN 10 END value ROUTINE slot: INTEGER BEGIN order=order*10+4 RETURN 1 END slot"
        state=run('order=0 SET_TSK_ATTR(target(),attr(),value(),codes[slot()])',decl='order: INTEGER codes: ARRAY[1] OF INTEGER',routines=routines,context=ctx)
        self.assertEqual((state['ORDER'],state['CODES']),(1234,[0]))

    def test_internal_routine_keeps_precedence(self):
        self.assertEqual(run('SET_TSK_ATTR(7)',routines='ROUTINE SET_TSK_ATTR(n: INTEGER) BEGIN s=n END SET_TSK_ATTR')['S'],7)

    def test_uninitialized_input_preserves_status_and_policy(self):
        ctx,worker=registry()
        p,_=compile_program("s=99 SET_TSK_ATTR('worker',TSK_PRIORITY,n,s)",context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['S'],99);self.assertEqual(worker.task_settings,{})

    def test_reports_describe_effects_and_portable_constants(self):
        result=translate(source('T',"SET_TSK_ATTR('',TSK_TRACE,1,s)"))
        self.assertFalse(result.report['task_attribute_policy']['controller_validated'])
        self.assertEqual(result.report['task_attribute_policy']['masks'],{'PG_NP_ERROR':1,'PG_NP_CMD':2,'PG_NP_END':4,'PG_NP_TPENB':8})
        self.assertIn('%PRIORITY',result.report['directive_policy']['allowed'])

    def test_authored_project_cli_execution(self):
        folder=ROOT/'examples/task_policies_project'
        result=subprocess.run([sys.executable,'-X','utf8','-m','karel2py.project',str(folder),'--entry','MAIN'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),json.loads((folder/'expected.json').read_text(encoding='utf-8')))


class TaskTraceExportTests(unittest.TestCase):
    def cli(self,folder,*args):
        return subprocess.run([sys.executable,'-X','utf8','-m','karel2py.project',str(folder),*map(str,args)],cwd=ROOT,capture_output=True,text=True)

    def test_cli_export_includes_bounded_trace_and_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'trace.json'
            result=self.cli(ROOT/'examples/task_policies_project','--entry','MAIN','--trace-out',output)
            self.assertEqual(result.returncode,0,result.stderr)
            saved=json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(saved['schema'],'karel2py.task-trace.v1')
            self.assertEqual(saved['tasks']['MAIN']['state'],'completed')
            self.assertEqual(saved['tasks']['MAIN']['settings']['TSK_TRACELEN'],4)
            self.assertEqual(len(saved['tasks']['MAIN']['trace']),4)
            self.assertEqual(saved['tasks']['WORKER']['trace'],[])

    def test_cli_failure_writes_partial_trace_then_reports_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);output=folder/'trace.json'
            code="PROGRAM MAIN VAR s,n: INTEGER BEGIN SET_TSK_ATTR('',TSK_TRACE,1,s) n=1 DIV 0 END MAIN"
            (folder/'main.kl').write_text(code,encoding='utf-8')
            result=self.cli(folder,'--entry','MAIN','--trace-out',output)
            self.assertNotEqual(result.returncode,0)
            task=json.loads(output.read_text(encoding='utf-8'))['tasks']['MAIN']
            self.assertEqual(task['state'],'failed');self.assertTrue(task['trace'])
            self.assertIn('Division by zero',result.stderr)

    def test_trace_write_failure_does_not_hide_execution_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);output=folder/'missing'/'trace.json'
            (folder/'main.kl').write_text('PROGRAM MAIN VAR n: INTEGER BEGIN n=1 DIV 0 END MAIN',encoding='utf-8')
            result=self.cli(folder,'--entry','MAIN','--trace-out',output)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Division by zero',result.stderr)
            self.assertIn('Task trace export failed',result.stderr)

    def test_trace_export_requires_execution_and_separate_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);path=folder/'main.kl';original='PROGRAM MAIN BEGIN END MAIN'
            path.write_text(original,encoding='utf-8')
            for options in (('--trace-out',folder/'trace.json'),('--entry','MAIN','--trace-out',path),('--entry','MAIN','--trace-out',folder/'state.json','--state-out',folder/'state.json')):
                with self.subTest(options=options):
                    result=self.cli(folder,*options);self.assertEqual(result.returncode,2)
                    self.assertEqual(path.read_text(encoding='utf-8'),original)


if __name__=='__main__':unittest.main()
