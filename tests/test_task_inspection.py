"""Authored task lookup, selected outputs, live execution and metadata tests."""
import unittest

from karel2py import translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


DECL='name,text: STRING[32] number,value,status: INTEGER'


def query(ctx,attribute='TSK_STATUS',setup="name='worker' number=0",**options):
    return run(setup+f' GET_TSK_INFO(name,number,{attribute},value,text,status)',decl=DECL,context=ctx,**options)


def registry(body='n=1',attributes=None,kind=rt.TaskRegistry,**options):
    tasks=kind();ctx=rt.ExecutionContext(tasks=tasks)
    worker,_=compile_program(body,cooperative=True,context=ctx,**options)
    tasks.bind('worker',worker,attributes=attributes)
    return ctx,worker


class TaskLookupTests(unittest.TestCase):
    def test_name_lookup_fills_uninitialized_number_only(self):
        ctx,_=registry();state=query(ctx,setup="name='worker' value=7 text='retained'")
        self.assertEqual((state['NAME'],state['NUMBER'],state['VALUE'],state['TEXT'],state['STATUS']),('worker',1,rt.TASK_CONSTANTS['PG_RUNACCEPT'],'retained',0))

    def test_name_lookup_is_case_insensitive(self):
        ctx,_=registry();state=query(ctx,setup="name='WoRkEr' number=0")
        self.assertEqual((state['NAME'],state['NUMBER'],state['STATUS']),('WoRkEr',1,0))

    def test_numeric_lookup_ignores_uninitialized_name(self):
        ctx,_=registry();state=query(ctx,setup='number=1')
        self.assertEqual((state['NAME'],state['NUMBER'],state['STATUS']),('WORKER',1,0))

    def test_numeric_lookup_replaces_name_and_preserves_number(self):
        ctx,_=registry();state=query(ctx,setup="number=1 name='ignored'")
        self.assertEqual((state['NAME'],state['NUMBER']),('WORKER',1))

    def test_unknown_task_preserves_identity_and_value_outputs(self):
        ctx,_=registry()
        for setup in ("name='absent' number=0","name='old' number=2"):
            with self.subTest(setup=setup):
                state=query(ctx,setup=setup+" value=7 text='old'")
                self.assertEqual((state['NAME'],state['NUMBER'],state['VALUE'],state['TEXT'],state['STATUS']),('absent' if 'absent' in setup else 'old',0 if 'absent' in setup else 2,7,'old',1))

    def test_unknown_name_preserves_uninitialized_number(self):
        ctx,_=registry();state=query(ctx,setup="name='absent'")
        self.assertEqual((state['NUMBER'],state['STATUS']),({'uninitialized':True},1))

    def test_uninitialized_input_name_raises_before_outputs_change(self):
        ctx,_=registry();p,_=compile_program('number=0 value=7 status=8 GET_TSK_INFO(name,number,TSK_STATUS,value,text,status)',decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['NUMBER'],p.snapshot()['VALUE'],p.snapshot()['STATUS']),(0,7,8))

    def test_negative_number_and_unknown_attribute_return_status_two(self):
        ctx,_=registry()
        for setup,attribute in (("name='old' number=-1",'TSK_STATUS'),("name='old' number=1",'999')):
            with self.subTest(setup=setup):
                state=query(ctx,attribute,setup=setup+" value=7 text='old'")
                self.assertEqual((state['NAME'],state['VALUE'],state['TEXT'],state['STATUS']),('old',7,'old',2))

    def test_registered_alias_is_distinct_from_source_program_name(self):
        ctx,_=registry();state=query(ctx,'TSK_PROGNAME',setup="number=1 value=7")
        self.assertEqual((state['NAME'],state['TEXT'],state['VALUE']),('WORKER','T',7))

    def test_short_string_outputs_use_existing_capacity_truncation(self):
        ctx,_=registry();state=run('number=1 GET_TSK_INFO(name,number,TSK_PROGNAME,value,text,status)',decl='name: STRING[2] text: STRING[1] number,value,status: INTEGER',context=ctx)
        self.assertEqual((state['NAME'],state['TEXT'],state['STATUS']),('WO','T',0))

    def test_empty_registry_does_not_discover_or_register_current_program(self):
        state=query(rt.ExecutionContext(),setup="name='T' number=0")
        self.assertEqual(state['STATUS'],1)

    def test_registry_order_matches_numeric_control_order(self):
        tasks=rt.TaskRegistry();ctx=rt.ExecutionContext(tasks=tasks)
        first,_=compile_program('PAUSE n=1',context=ctx);second,_=compile_program('PAUSE n=2',context=ctx)
        tasks.bind('first',first);tasks.bind('second',second)
        with self.assertRaises(rt.KarelPause): first.run()
        with self.assertRaises(rt.KarelPause): second.run()
        state=query(ctx,setup="name='second' number=0")
        self.assertEqual(state['NUMBER'],2)
        run('CONTINUE PROGRAM[2]',cooperative=True,context=ctx)
        self.assertEqual((first.task_state,second.task_state),('paused','completed'))

    def test_rebinding_retains_number_and_replaces_metadata(self):
        ctx,worker=registry(attributes={'TSK_PRIORITY':10});ctx.tasks.bind('second',worker)
        ctx.tasks.bind('WORKER',worker,attributes={'TSK_PRIORITY':20})
        state=query(ctx,'TSK_PRIORITY');self.assertEqual((state['NUMBER'],state['VALUE']),(1,20))


class TaskLiveDataTests(unittest.TestCase):
    def test_ready_running_and_completed_statuses(self):
        ctx,worker=registry("name='worker' number=0 GET_TSK_INFO(name,number,TSK_STATUS,n,text,s)",decl='name,text: STRING[32] number,n,s: INTEGER')
        self.assertEqual(query(ctx)['VALUE'],rt.TASK_CONSTANTS['PG_RUNACCEPT'])
        self.assertEqual(worker.run()['N'],rt.TASK_CONSTANTS['PG_RUNNING'])
        self.assertEqual(query(ctx)['VALUE'],rt.TASK_CONSTANTS['PG_COMPLETED'])

    def test_paused_and_stopped_statuses(self):
        ctx,worker=registry('PAUSE n=1')
        with self.assertRaises(rt.KarelPause): worker.run()
        self.assertEqual(query(ctx)['VALUE'],rt.TASK_CONSTANTS['PG_PAUSED'])
        worker.stop();self.assertEqual(query(ctx)['VALUE'],rt.TASK_CONSTANTS['PG_STOPPED'])

    def test_aborted_and_failed_statuses(self):
        for body,error,expected in (('ABORT',rt.KarelAbort,'PG_ABORTED'),('n=1 DIV 0',rt.KarelRuntimeError,'PG_FAILED')):
            with self.subTest(body=body):
                ctx,worker=registry(body)
                with self.assertRaises(error): worker.run()
                self.assertEqual(query(ctx)['VALUE'],rt.TASK_CONSTANTS[expected]);self.assertEqual(worker._state._task_frames,[])

    def test_pending_abort_is_visible_without_delivering_it(self):
        ctx,worker=registry('PAUSE n=1')
        with self.assertRaises(rt.KarelPause): worker.run()
        rt.request_task_control(worker._state,'ABORT')
        self.assertEqual(query(ctx)['VALUE'],rt.TASK_CONSTANTS['PG_ABORTING']);self.assertEqual(worker.task_state,'paused')

    def test_waiting_and_scheduler_quantum(self):
        scheduler=rt.TaskScheduler(quantum_ms=7);ctx=rt.ExecutionContext(tasks=scheduler)
        worker,_=compile_program('DELAY 100 n=1',context=ctx,cooperative=True);scheduler.bind('worker',worker);scheduler.start('worker')
        for _ in range(5):
            scheduler.step()
            if worker.task_state=='waiting': break
        self.assertEqual(query(ctx)['VALUE'],rt.TASK_CONSTANTS['PG_WAITING'])
        self.assertEqual(query(ctx,'TSK_TIMESLIC')['VALUE'],7)

    def test_program_type_before_and_after_execution(self):
        ctx,worker=registry();self.assertEqual(query(ctx,'TSK_PROGTYPE')['VALUE'],rt.TASK_CONSTANTS['PG_NOT_EXEC'])
        worker.run();self.assertEqual(query(ctx,'TSK_PROGTYPE')['VALUE'],rt.TASK_CONSTANTS['PG_AR_KAREL'])

    def test_unscheduled_time_slice_is_zero(self):
        ctx,_=registry();self.assertEqual(query(ctx,'TSK_TIMESLIC')['VALUE'],0)

    def test_ready_line_and_routine_depth_are_zero_or_empty(self):
        ctx,_=registry()
        self.assertEqual(query(ctx,'TSK_LINENUM')['VALUE'],0);self.assertEqual(query(ctx,'TSK_STACK')['VALUE'],0)
        self.assertEqual(query(ctx,'TSK_ROUTNAME')['TEXT'],'')

    def test_paused_internal_routine_retains_name_line_and_depth(self):
        routine='ROUTINE helper BEGIN\n n=1\n PAUSE\n n=2\nEND helper'
        ctx,worker=registry('helper()',routines=routine)
        with self.assertRaises(rt.KarelPause): worker.run()
        self.assertEqual(query(ctx,'TSK_ROUTNAME')['TEXT'],'HELPER');self.assertEqual(query(ctx,'TSK_STACK')['VALUE'],1)
        self.assertGreater(query(ctx,'TSK_LINENUM')['VALUE'],0)
        worker.resume();self.assertEqual(query(ctx,'TSK_ROUTNAME')['TEXT'],'');self.assertEqual(query(ctx,'TSK_STACK')['VALUE'],0)

    def test_rerun_clears_previous_frames_and_retains_real_program_type(self):
        ctx,worker=registry('helper()',routines='ROUTINE helper BEGIN n=1 END helper')
        worker.run();worker.run();self.assertEqual(worker._state._task_frames,[])
        self.assertEqual(query(ctx,'TSK_PROGTYPE')['VALUE'],rt.TASK_CONSTANTS['PG_AR_KAREL'])

    def test_linked_library_is_visible_on_callers_task(self):
        library=source('LIB','',routines='ROUTINE helper BEGIN PAUSE END helper')
        main=source('MAIN','helper()',routines='ROUTINE helper FROM LIB')
        instance=translate_project({'a':main,'b':library}).instantiate();instance.run('MAIN')
        ctx=instance.context
        self.assertEqual(query(ctx,'TSK_PROGNAME',setup="name='MAIN' number=0")['TEXT'],'LIB')
        self.assertEqual(query(ctx,'TSK_ROUTNAME',setup="name='MAIN' number=0")['TEXT'],'HELPER')
        self.assertEqual(query(ctx,'TSK_STACK',setup="name='MAIN' number=0")['VALUE'],2)
        instance.scheduler.continue_task('MAIN');instance.scheduler.run()
        self.assertEqual(instance.programs['MAIN']._state._task_frames,[])

    def test_linked_queries_keep_independent_concurrent_frame_stacks(self):
        library=source('LIB','',routines='ROUTINE helper BEGIN PAUSE END helper')
        routine='ROUTINE helper FROM LIB'
        instance=translate_project({'a':source('FIRST','helper()',routines=routine),'b':source('SECOND','helper()',routines=routine),'c':library}).instantiate()
        instance.scheduler.start('FIRST');instance.scheduler.start('SECOND');instance.scheduler.run()
        for name in ('FIRST','SECOND'):
            self.assertEqual(query(instance.context,'TSK_STACK',setup=f"name='{name}' number=0")['VALUE'],2)
        instance.scheduler.stop('FIRST')
        self.assertEqual(instance.programs['FIRST']._state._task_frames,[])
        self.assertEqual(len(instance.programs['SECOND']._state._task_frames),2)

    def test_line_number_identifies_paused_source_checkpoint(self):
        code='PROGRAM WORKER\nVAR n: INTEGER\nROUTINE helper\nBEGIN\n n=1\n PAUSE\n n=2\nEND helper\nBEGIN\n helper()\nEND WORKER'
        instance=translate_project({'worker.kl':code}).instantiate();instance.run('WORKER')
        self.assertEqual(query(instance.context,'TSK_LINENUM')['VALUE'],6)

    def test_linked_failure_cleans_inspection_frames(self):
        instance=translate_project({'a':source('MAIN','helper()',routines='ROUTINE helper FROM LIB'),'b':source('LIB','',routines='ROUTINE helper BEGIN n=1 DIV 0 END helper')}).instantiate()
        with self.assertRaises(rt.KarelRuntimeError): instance.run('MAIN')
        self.assertEqual(instance.programs['MAIN']._state._task_frames,[])
        self.assertEqual(query(instance.context,'TSK_STACK',setup="name='MAIN' number=0")['VALUE'],0)

    def test_completed_scheduled_task_retains_registry_quantum(self):
        scheduler=rt.TaskScheduler(quantum_ms=9);ctx=rt.ExecutionContext(tasks=scheduler)
        worker,_=compile_program('n=1',cooperative=True,context=ctx);scheduler.bind('worker',worker)
        scheduler.start('worker');scheduler.run()
        self.assertIsNone(worker._state._scheduler);self.assertEqual(query(ctx,'TSK_TIMESLIC')['VALUE'],9)


class TaskMetadataTests(unittest.TestCase):
    def test_explicit_priority_is_informational(self):
        ctx,_=registry(attributes={'TSK_PRIORITY':50});state=query(ctx,'TSK_PRIORITY',setup="name='worker' number=0 text='keep'")
        self.assertEqual((state['VALUE'],state['TEXT'],state['STATUS']),(50,'keep',0))

    def test_every_unmodeled_attribute_accepts_explicit_integer_metadata(self):
        from karel2py.scheduling import TASK_ATTRIBUTES,TASK_DYNAMIC
        metadata={name:index for index,name in enumerate(TASK_ATTRIBUTES) if name not in TASK_DYNAMIC}
        for kind in (rt.TaskRegistry,rt.TaskScheduler):
            ctx,_=registry(attributes=metadata,kind=kind)
            for name,value in metadata.items():
                with self.subTest(kind=kind,name=name): self.assertEqual(query(ctx,name)['VALUE'],value)

    def test_unsupplied_attribute_preserves_all_data_outputs(self):
        ctx,_=registry();state=query(ctx,'TSK_PRIORITY',setup="name='worker' value=7 text='keep'")
        self.assertEqual((state['NUMBER'],state['VALUE'],state['TEXT'],state['STATUS']),({'uninitialized':True},7,'keep',3))

    def test_invalid_metadata_rebind_is_atomic(self):
        ctx,worker=registry(attributes={'TSK_PRIORITY':10})
        for metadata in (True,[],{'bad':1},{'TSK_STATUS':1},{'TSK_PRIORITY':True},{'TSK_PRIORITY':1.5},{'TSK_PRIORITY':10,'tsk_priority':20}):
            with self.subTest(metadata=metadata),self.assertRaises((ValueError,rt.KarelRuntimeError)): ctx.tasks.bind('worker',worker,attributes=metadata)
            self.assertIs(ctx.tasks.tasks['WORKER'],worker);self.assertEqual(ctx.tasks.attributes['WORKER'],{'TSK_PRIORITY':10})

    def test_names_and_noncooperative_programs_are_validated(self):
        ctx,worker=registry()
        for name in ('','x'*255,'\u00fc'):
            with self.subTest(name=name),self.assertRaises((ValueError,rt.KarelRuntimeError)): ctx.tasks.bind(name,worker)
        plain,_=compile_program('n=1')
        with self.assertRaises(TypeError): ctx.tasks.bind('plain',plain)

    def test_task_bindings_and_metadata_are_not_value_snapshots(self):
        ctx,_=registry(attributes={'TSK_PRIORITY':50});config=ctx.to_config()
        self.assertNotIn('tasks',config);self.assertNotIn('attributes',config)
        restored=rt.ExecutionContext.from_config(config);self.assertEqual(restored.tasks.tasks,{})


class TaskInspectionOwnershipTests(unittest.TestCase):
    def test_aliasing_is_rejected_before_selection(self):
        for call in ('GET_TSK_INFO(name,number,TSK_STATUS,number,text,status)','GET_TSK_INFO(name,number,TSK_STATUS,value,name,status)','GET_TSK_INFO(name,number,TSK_STATUS,status,text,status)'):
            with self.subTest(call=call):
                p,_=compile_program('number=0 status=7 '+call,decl=DECL)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): p.run()
                self.assertEqual(p.snapshot()['STATUS'],7)

    def test_arity_exact_types_and_writable_references(self):
        for call in ('GET_TSK_INFO(name,number,TSK_STATUS,value,text)','GET_TSK_INFO(name,number,TSK_STATUS,value,text,status,status)','GET_TSK_INFO(\'worker\',number,TSK_STATUS,value,text,status)','GET_TSK_INFO(name,0,TSK_STATUS,value,text,status)','GET_TSK_INFO(name,number,TSK_STATUS,small,text,status)','GET_TSK_INFO(name,number,TSK_STATUS,x,text,status)'):
            with self.subTest(call=call),self.assertRaises(TranslationError): compile_program(call,decl=DECL+' small: SHORT x: REAL')

    def test_direct_transitive_and_handler_counter_guards(self):
        call='GET_TSK_INFO(name,number,TSK_STATUS,value,text,status)'
        for body,routines in ((f'FOR number=1 TO 2 DO {call} ENDFOR',''),('FOR number=1 TO 2 DO inspect() ENDFOR',f'ROUTINE inspect BEGIN {call} END inspect'),(f'CONDITION[1]: WHEN TRUE DO {call} ENDCONDITION FOR value=1 TO 2 DO ENDFOR','')):
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught: compile_program(body,decl=DECL,routines=routines)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_reference_selectors_captured_once_in_source_order(self):
        ctx,_=registry()
        routine='ROUTINE slot: INTEGER BEGIN count=count+1 RETURN 1 END slot'
        state=run("count=0 names[1]='worker' GET_TSK_INFO(names[slot()],number,TSK_STATUS,value,text,status)",decl='names: ARRAY[1] OF STRING[32] number,value,status,count: INTEGER text: STRING[32]',routines=routine,context=ctx)
        self.assertEqual((state['COUNT'],state['NUMBER'],state['STATUS']),(1,1,0))

    def test_user_procedure_keeps_precedence(self):
        self.assertEqual(run('GET_TSK_INFO(7)',routines='ROUTINE GET_TSK_INFO(n: INTEGER) BEGIN s=n END GET_TSK_INFO')['S'],7)

    def test_report_and_records_preserve_explicit_boundary(self):
        ctx,_=registry();p,result=compile_program("name='worker' GET_TSK_INFO(name,number,TSK_STATUS,value,text,status)",decl=DECL,context=ctx)
        p.run();self.assertFalse(result.report['task_inspection_policy']['controller_validated'])
        self.assertEqual(result.report['task_inspection_policy']['constants'],rt.TASK_CONSTANTS)
        self.assertTrue(all(set(row)=={'operation','line','outcome'} for row in p.service_requests))


if __name__=='__main__': unittest.main()
