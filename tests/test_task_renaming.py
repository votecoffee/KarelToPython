"""Authored task identity, retained execution and scheduler rename regressions."""
import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest

from karel2py import translate, translate_project, runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program, run
from tests.test_project_scheduler import source
from tests.test_task_inspection import registry, query


ROOT=Path(__file__).resolve().parents[1]


class TaskRenameRegistryTests(unittest.TestCase):
    def test_case_insensitive_rename_preserves_slot_metadata_and_source_name(self):
        ctx,worker=registry(attributes={'TSK_PRIORITY':50})
        other,_=compile_program('n=2',cooperative=True,context=ctx)
        ctx.tasks.bind('second',other)
        mappings=(ctx.tasks.tasks,ctx.tasks.attributes)
        state=run("SET_TSK_NAME('WoRkEr','NeW',s)",context=ctx)
        self.assertEqual(state['S'],0)
        self.assertEqual(list(ctx.tasks.tasks),['NEW','SECOND'])
        self.assertIs(ctx.tasks.tasks['NEW'],worker)
        self.assertIs(ctx.tasks.tasks,mappings[0]);self.assertIs(ctx.tasks.attributes,mappings[1])
        data=query(ctx,'TSK_PRIORITY',setup="name='new' number=0")
        self.assertEqual((data['NUMBER'],data['VALUE']),(1,50))
        self.assertEqual(query(ctx,'TSK_PROGNAME',setup='number=1')['TEXT'],'T')
        self.assertEqual(query(ctx,setup="name='worker' number=0")['STATUS'],1)

    def test_collision_and_empty_new_name_leave_registry_unchanged(self):
        ctx,worker=registry();ctx.tasks.bind('taken',worker,attributes={'TSK_PRIORITY':7})
        before=(ctx.tasks.tasks.copy(),ctx.tasks.attributes.copy())
        for new in ('taken',''):
            with self.subTest(new=new):
                state=run(f"SET_TSK_NAME('worker','{new}',s)",context=ctx)
                self.assertEqual(state['S'],2)
                self.assertEqual((ctx.tasks.tasks,ctx.tasks.attributes),before)

    def test_unknown_old_name_and_unregistered_caller(self):
        ctx,_=registry()
        self.assertEqual(run("SET_TSK_NAME('missing','new',s)",context=ctx)['S'],1)
        self.assertEqual(run("SET_TSK_NAME('','new',s)",context=ctx)['S'],3)

    def test_explicit_alias_rename_does_not_rename_other_aliases(self):
        ctx,worker=registry();ctx.tasks.bind('alias',worker)
        self.assertEqual(ctx.tasks.rename('alias','renamed'),0)
        self.assertEqual(list(ctx.tasks.tasks),['WORKER','RENAMED'])

    def test_empty_self_name_rejects_ambiguous_aliases(self):
        ctx,worker=registry("SET_TSK_NAME('','new',s)")
        ctx.tasks.bind('alias',worker)
        self.assertEqual(worker.run()['S'],3)
        self.assertEqual(list(ctx.tasks.tasks),['WORKER','ALIAS'])

    def test_noop_rename_succeeds_without_replacing_metadata(self):
        ctx,_=registry(attributes={'TSK_PRIORITY':7});metadata=ctx.tasks.attributes['WORKER']
        self.assertEqual(ctx.tasks.rename('worker','WoRkEr'),0)
        self.assertIs(ctx.tasks.attributes['WORKER'],metadata)

    def test_host_api_validates_names_without_numeric_scope(self):
        ctx,_=registry()
        for name in ('','x'*255):self.assertEqual(ctx.tasks.rename('worker',name),2)
        for old,new in ((None,'new'),('worker',False),('worker','\u00fc')):
            with self.subTest(old=old,new=new),self.assertRaises(rt.KarelRuntimeError):ctx.tasks.rename(old,new)
        self.assertEqual(ctx.tasks.rename('worker','x'*254),0)

    def test_rename_preserves_standalone_pause_and_numeric_continue(self):
        ctx,worker=registry('n=1 PAUSE n=2')
        with self.assertRaises(rt.KarelPause):worker.run()
        self.assertEqual(ctx.tasks.rename('worker','new'),0)
        self.assertEqual((worker.task_state,worker.snapshot()['N']),('paused',1))
        run('CONTINUE PROGRAM[1]',cooperative=True,context=ctx)
        self.assertEqual((worker.task_state,worker.snapshot()['N']),('completed',2))

    def test_renamed_names_are_live_configuration_not_value_persistence(self):
        ctx,_=registry();ctx.tasks.rename('worker','new')
        self.assertEqual(rt.ExecutionContext.from_config(ctx.to_config()).tasks.tasks,{})


class TaskRenameSchedulerTests(unittest.TestCase):
    def test_empty_self_name_in_linked_routine_uses_calling_root(self):
        main=source('MAIN','rename()',routines='ROUTINE rename FROM LIB')
        library=source('LIB','',routines="ROUTINE rename BEGIN SET_TSK_NAME('','new',s) END rename",decl='s: INTEGER')
        instance=translate_project({'main':main,'lib':library}).instantiate()
        snapshot=instance.run('MAIN')
        self.assertEqual(list(snapshot),['NEW','LIB'])
        self.assertEqual(snapshot['LIB']['values']['S'],0)
        self.assertEqual(query(instance.context,'TSK_PROGNAME',setup='number=1')['TEXT'],'MAIN')
        self.assertIn('MAIN',instance.programs)
        self.assertIn('MAIN',instance.context.variables.programs)

    def test_self_rename_then_delay_uses_new_waiting_key(self):
        ctx,worker=registry("SET_TSK_NAME('','new',s) DELAY 30 n=2",kind=rt.TaskScheduler)
        ctx.tasks.start('worker')
        while worker.task_state!='waiting':ctx.tasks.step()
        self.assertEqual(list(ctx.tasks.waiting),['NEW'])
        ctx.tasks.run()
        self.assertEqual((worker.task_state,worker.snapshot()['N']),('completed',2))
        self.assertEqual(ctx.tasks.waiting,{})

    def test_self_rename_then_pause_and_named_continue(self):
        ctx,worker=registry("SET_TSK_NAME('','new',s) PAUSE n=2",kind=rt.TaskScheduler)
        ctx.tasks.start('worker');ctx.tasks.run()
        self.assertEqual(worker.task_state,'paused')
        run("CONT_TASK('new',s)",context=ctx)
        ctx.tasks.run();self.assertEqual(worker.snapshot()['N'],2)

    def test_rename_waiting_task_preserves_deadline_and_state(self):
        ctx,worker=registry('DELAY 30 n=2',kind=rt.TaskScheduler)
        ctx.tasks.start('worker')
        while worker.task_state!='waiting':ctx.tasks.step()
        deadline=ctx.tasks.waiting['WORKER'];now=ctx.tasks.now_us
        self.assertEqual(ctx.tasks.rename('worker','new'),0)
        self.assertEqual((ctx.tasks.waiting,ctx.tasks.now_us,worker.task_state),({'NEW':deadline},now,'waiting'))
        ctx.tasks.run();self.assertEqual(worker.snapshot()['N'],2)

    def test_rename_later_task_during_same_batch_executes_it_once(self):
        scheduler=rt.TaskScheduler();ctx=rt.ExecutionContext(tasks=scheduler)
        first,_=compile_program("SET_TSK_NAME('worker','new',s)",cooperative=True,context=ctx)
        worker,_=compile_program('n=1 n=n+1',cooperative=True,context=ctx)
        scheduler.bind('first',first);scheduler.bind('worker',worker)
        scheduler.start('first');scheduler.start('worker');scheduler.run()
        self.assertEqual(list(scheduler.tasks),['FIRST','NEW'])
        self.assertEqual(worker.snapshot()['N'],2)

    def test_repeated_self_rename_in_one_checkpoint_keeps_final_name(self):
        ctx,worker=registry("SET_TSK_NAME('','middle',s) SET_TSK_NAME('','last',s) DELAY 10 n=2",kind=rt.TaskScheduler)
        ctx.tasks.start('worker');ctx.tasks.run()
        self.assertEqual(list(ctx.tasks.tasks),['LAST'])
        self.assertEqual(worker.snapshot()['S'],0)

    def test_failure_after_rename_is_recorded_under_new_name(self):
        ctx,worker=registry("SET_TSK_NAME('','new',s) n=1 DIV 0",kind=rt.TaskScheduler)
        ctx.tasks.start('worker')
        with self.assertRaises(rt.KarelRuntimeError):ctx.tasks.run()
        self.assertEqual(list(ctx.tasks.errors),['NEW'])
        self.assertIsNone(ctx.tasks._step_names)
        self.assertEqual(ctx.tasks.rename('new','failed'),0)
        self.assertEqual(list(ctx.tasks.errors),['FAILED'])
        self.assertEqual(worker.task_state,'failed')

    def test_rename_is_rejected_through_foreign_active_registry(self):
        ctx,worker=registry('PAUSE n=2',kind=rt.TaskScheduler)
        ctx.tasks.start('worker');ctx.tasks.run()
        other=rt.TaskRegistry();other.bind('alias',worker)
        self.assertEqual(other.rename('alias','new'),3)
        self.assertEqual(list(other.tasks),['ALIAS'])
        self.assertEqual(list(ctx.tasks.tasks),['WORKER'])

    def test_scheduler_metadata_collision_preflight_preserves_all_maps(self):
        ctx,_=registry(kind=rt.TaskScheduler)
        ctx.tasks.errors['NEW']=RuntimeError('retained')
        self.assertEqual(ctx.tasks.rename('worker','new'),2)
        self.assertEqual(list(ctx.tasks.tasks),['WORKER'])
        self.assertEqual(list(ctx.tasks.errors),['NEW'])

    def test_nested_step_is_rejected_and_iteration_marker_is_cleared(self):
        scheduler=rt.TaskScheduler();ctx=rt.ExecutionContext(tasks=scheduler)
        worker,_=compile_program('WRITE(1)',cooperative=True,context=ctx,write=lambda *args:scheduler.step())
        scheduler.bind('worker',worker);scheduler.start('worker')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'recursively'):scheduler.run()
        self.assertIsNone(scheduler._step_names)


class TaskRenameSourceTests(unittest.TestCase):
    def test_arity_types_and_writable_status(self):
        for call in ("SET_TSK_NAME('a','b')","SET_TSK_NAME('a','b',s,s)","SET_TSK_NAME(1,'b',s)","SET_TSK_NAME('a',TRUE,s)","SET_TSK_NAME('a','b',0)","SET_TSK_NAME('a','b',x)"):
            with self.subTest(call=call),self.assertRaises(TranslationError):compile_program(call,decl='s: INTEGER x: REAL')

    def test_counter_output_direct_transitive_and_handler_protection(self):
        call="SET_TSK_NAME('worker','new',s)"
        for body,routines in ((f'FOR s=1 TO 2 DO {call} ENDFOR',''),('FOR s=1 TO 2 DO rename() ENDFOR',f'ROUTINE rename BEGIN {call} END rename'),(f'CONDITION[1]: WHEN TRUE DO {call} ENDCONDITION FOR s=1 TO 2 DO ENDFOR','')):
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught:compile_program(body,routines=routines)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_uninitialized_input_preserves_status_and_registry(self):
        ctx,_=registry()
        p,_=compile_program("s=99 SET_TSK_NAME(name,'new',s)",decl='name: STRING[16] s: INTEGER',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['S'],99);self.assertEqual(list(ctx.tasks.tasks),['WORKER'])

    def test_inputs_and_status_selector_evaluate_once_in_source_order(self):
        ctx,_=registry()
        routines="ROUTINE old: STRING BEGIN order=order*10+1 RETURN name END old ROUTINE new: STRING BEGIN order=order*10+2 name='changed' RETURN 'renamed' END new ROUTINE slot: INTEGER BEGIN order=order*10+3 RETURN 1 END slot"
        state=run("order=0 name='worker' SET_TSK_NAME(old(),new(),codes[slot()])",decl='name: STRING[16] order: INTEGER codes: ARRAY[1] OF INTEGER',routines=routines,context=ctx)
        self.assertEqual((state['ORDER'],state['NAME'],state['CODES']),(123,'changed',[0]))
        self.assertEqual(list(ctx.tasks.tasks),['RENAMED'])

    def test_user_routine_retains_precedence(self):
        self.assertEqual(run('SET_TSK_NAME(7)',routines='ROUTINE SET_TSK_NAME(n: INTEGER) BEGIN s=n END SET_TSK_NAME')['S'],7)

    def test_report_and_service_records_describe_portable_behavior(self):
        ctx,_=registry();p,result=compile_program("SET_TSK_NAME('worker','new',s)",context=ctx)
        p.run();self.assertFalse(result.report['task_rename_policy']['controller_validated'])
        self.assertIn('SET_TSK_NAME',result.report['service_policy']['procedures'])
        self.assertEqual(p.service_requests,({'operation':'SET_TSK_NAME','line':6,'outcome':'completed'},))

    def test_project_cli_uses_renamed_bindings_and_preserved_source_identity(self):
        folder=ROOT/'examples/task_rename_project'
        result=subprocess.run([sys.executable,'-X','utf8','-m','karel2py.project',str(folder),'--entry','MAIN'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(ast.literal_eval(result.stdout),json.loads((folder/'expected.json').read_text(encoding='utf-8')))


if __name__=='__main__':unittest.main()
