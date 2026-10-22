"""Authored linked-program, event and deterministic scheduling scenarios."""
import tempfile
from pathlib import Path
import unittest

from karel2py import translate_project,load_project,runtime as rt
from tests.test_extended_services import compile_program


def source(name,body,decl='n,s: INTEGER',routines=''):
    return f'PROGRAM {name} VAR {decl} {routines} BEGIN {body} END {name}'


class ProjectTests(unittest.TestCase):
    def test_automatic_routine_and_variable_links(self):
        project=translate_project({'lib.kl':source('LIB','n=10',routines='ROUTINE add(x: INTEGER): INTEGER BEGIN n=n+x RETURN n END add'),
            'main.kl':source('MAIN','n=3 s=add(4)',decl='n FROM LIB: INTEGER s: INTEGER',routines='ROUTINE add(x: INTEGER): INTEGER FROM LIB')})
        instance=project.instantiate();instance.run('MAIN')
        self.assertEqual(instance.programs['MAIN'].snapshot(),{'N':7,'S':7})
        self.assertEqual(instance.programs['LIB'].snapshot()['N'],7)
        self.assertEqual(instance.programs['LIB']._state.call_depth,0)

    def test_reference_outputs_and_aggregate_alias(self):
        instance=translate_project({'a':source('LIB','',decl='a: ARRAY[2] OF INTEGER',routines='ROUTINE put(x: INTEGER) BEGIN x=42 END put'),
            'b':source('MAIN','a[1]=1 put(a[1]) GET_VAR(e,\'LIB\',\'A[1]\',n,s)',decl='a FROM LIB: ARRAY[2] OF INTEGER e,n,s: INTEGER',routines='ROUTINE put(x: INTEGER) FROM LIB')}).instantiate()
        instance.run('MAIN');self.assertEqual(instance.programs['MAIN'].snapshot()['A'][0],42)

    def test_unresolved_and_mismatched_links(self):
        cases=[{'a':source('MAIN','',routines='ROUTINE absent FROM LIB')},
            {'a':source('LIB','',routines='ROUTINE f(x: REAL) BEGIN END f'),'b':source('MAIN','',routines='ROUTINE f(x: INTEGER) FROM LIB')},
            {'a':source('MAIN','',decl='n FROM LIB: INTEGER')},
            {'a':source('MAIN','',decl='n FROM LIB: INTEGER'),'b':source('LIB','',decl='n FROM MAIN: INTEGER')}]
        for sources in cases:
            with self.subTest(sources=sources),self.assertRaises(ValueError): translate_project(sources).instantiate()

    def test_external_abort_propagates(self):
        instance=translate_project({'a':source('LIB','',routines='ROUTINE halt BEGIN ABORT END halt'),'b':source('MAIN','halt() n=9',routines='ROUTINE halt FROM LIB')}).instantiate()
        with self.assertRaises(rt.KarelAbort): instance.run('MAIN')
        self.assertEqual(instance.programs['MAIN'].task_state,'aborted')

    def test_linked_recursion_has_global_budget(self):
        instance=translate_project({'a':source('LIB','',routines='ROUTINE f BEGIN f() END f'),'b':source('MAIN','f()',routines='ROUTINE f FROM LIB')}).instantiate()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'depth'): instance.run('MAIN')
        self.assertEqual(instance.programs['MAIN']._state.call_depth,0)

    def test_concurrent_external_calls_have_independent_stacks(self):
        external='ROUTINE work(x: INTEGER): INTEGER FROM LIB'
        instance=translate_project({'lib':source('LIB','',routines='ROUTINE work(x: INTEGER): INTEGER VAR local: INTEGER BEGIN local=x DELAY 5 RETURN local END work'),
            'a':source('MAIN',"RUN_TASK('SECOND',0,FALSE,FALSE,0,s) n=work(1)",routines=external),
            'b':source('SECOND','n=work(2)',routines=external)}).instantiate()
        result=instance.run('MAIN');self.assertEqual((result['MAIN']['values']['N'],result['SECOND']['values']['N']),(1,2))

    def test_linked_abort_is_sticky(self):
        instance=translate_project({'a':source('LIB','',routines='ROUTINE halt BEGIN ABORT END halt'),'b':source('MAIN','halt()',routines='ROUTINE halt FROM LIB')}).instantiate()
        for _ in range(2):
            with self.assertRaises(rt.KarelAbort): instance.run('MAIN')

    def test_global_budget_counts_library_work(self):
        instance=translate_project({'a':source('LIB','',routines='ROUTINE loop BEGIN WHILE TRUE DO ENDWHILE END loop'),'b':source('MAIN','loop()',routines='ROUTINE loop FROM LIB')}).instantiate()
        instance.scheduler.max_steps=25
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'): instance.run('MAIN')
        self.assertEqual(instance.programs['MAIN']._state.call_depth,0)

    def test_load_explicit_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'main.KL').write_text(source('MAIN','n=7'))
            instance=load_project(folder).instantiate();self.assertEqual(instance.run('MAIN')['MAIN']['values']['N'],7)


class SchedulerTests(unittest.TestCase):
    def programs(self,main,child,**kwargs):
        return translate_project({'a':source('MAIN',main,**kwargs),'b':source('CHILD',child,**kwargs)}).instantiate()

    def test_round_robin_and_virtual_delay(self):
        instance=self.programs("RUN_TASK('CHILD',0,FALSE,FALSE,0,s) n=1 DELAY 20 n=2",'n=7 DELAY 2 n=9')
        result=instance.run('MAIN');self.assertEqual((result['MAIN']['values']['N'],result['CHILD']['values']['N']),(2,9))
        self.assertGreaterEqual(instance.scheduler.now_us,20000)

    def test_wait_and_broadcast_event(self):
        instance=self.programs("RUN_TASK('CHILD',0,FALSE,FALSE,0,s) WAIT FOR EVENT[1] n=7",'SIGNAL EVENT[1] n=9')
        result=instance.run('MAIN');self.assertEqual(result['MAIN']['values']['N'],7)

    def test_pause_continue_and_stop_cleanup(self):
        instance=self.programs("RUN_TASK('CHILD',0,FALSE,FALSE,0,s) DELAY 10 CONTINUE PROGRAM[2]",'n=1 PAUSE n=2')
        self.assertEqual(instance.run('MAIN')['CHILD']['values']['N'],2)
        instance=self.programs("RUN_TASK('CHILD',0,FALSE,FALSE,0,s) DELAY 5 ABORT PROGRAM[2]",'PAUSE n=9')
        self.assertEqual(instance.run('MAIN')['CHILD']['state'],'aborted')
        self.assertIsNone(instance.programs['CHILD']._state._scheduler)

    def test_scheduler_budget_bounded(self):
        instance=self.programs('WAIT FOR FALSE','n=1')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cycle budget'): instance.run('MAIN',max_cycles=5)

    def test_events_in_handler_and_eval_capture(self):
        p,_=compile_program('n=1 CONDITION[1]: WHEN EVENT[1] AND EVAL(n=1) DO n=7 ENDCONDITION ENABLE CONDITION[1] n=2 SIGNAL EVENT[1] s=n')
        self.assertEqual(p.run()['S'],7)

    def test_edge_condition_rearm(self):
        ports=rt.PortBank({'DIN':1,'DOUT':1},{('DIN',1):False,('DOUT',1):False})
        p,_=compile_program('n=0 CONDITION[1]: WHEN DOUT[1]+ DO n=n+1,ENABLE CONDITION[1] ENDCONDITION ENABLE CONDITION[1] DOUT[1]=FALSE DOUT[1]=TRUE s=n DOUT[1]=FALSE DOUT[1]=TRUE s=n',context=rt.ExecutionContext(ports=ports))
        self.assertEqual(p.run()['N'],2)

    def test_scan_interval_and_timer(self):
        program=source('MAIN','n=0 s=0 CONNECT TIMER TO s CONDITION[1]: WITH $SCAN_TIME=10 WHEN s>=10 DO n=7 ENDCONDITION ENABLE CONDITION[1] DELAY 30 s=s')
        instance=translate_project({'a':program}).instantiate();self.assertEqual(instance.run('MAIN')['MAIN']['values']['N'],7)

    def test_local_handler_lifetime(self):
        p,_=compile_program('work() n=1',routines='ROUTINE work BEGIN CONDITION[1]: WHEN FALSE DO n=9 ENDCONDITION END work',context=rt.ExecutionContext(local_handlers=True))
        p.run();self.assertEqual(p._state._handlers,{})


if __name__=='__main__': unittest.main()
