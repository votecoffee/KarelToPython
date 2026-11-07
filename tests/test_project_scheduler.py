"""Authored linked-program, event and deterministic scheduling scenarios."""
import tempfile
from pathlib import Path
import unittest

from karel2py import translate_project,load_project,runtime as rt
from tests.test_extended_services import compile_program


def source(name,body,decl='n,s: INTEGER',routines=''):
    return f'PROGRAM {name} VAR {decl} {routines} BEGIN {body} END {name}'


class ProjectTests(unittest.TestCase):
    def test_scheduler_requires_boolean_paused_start_before_launch(self):
        instance=translate_project({'main':source('MAIN','n=7')}).instantiate()
        program=instance.programs['MAIN']
        scheduler=instance.scheduler
        for flag in (1,0,None,'false'):
            with self.subTest(flag=flag),self.assertRaisesRegex(TypeError,'paused must be BOOLEAN'):
                scheduler.start('MAIN',paused=flag)
        self.assertIsNone(getattr(program,'_execution',None))
        self.assertIsNone(program._state._scheduler)
        self.assertEqual(scheduler.waiting,{})
        scheduler.start('MAIN',paused=True)
        self.assertEqual(scheduler.run()['MAIN']['state'],'paused')
        scheduler.continue_task('MAIN')
        self.assertEqual(scheduler.run()['MAIN']['values']['N'],7)

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

    def test_host_pause_inside_library_loop(self):
        instance=translate_project({'a':source('LIB','',routines='ROUTINE loop BEGIN WHILE TRUE DO ENDWHILE END loop'),'b':source('MAIN','loop()',routines='ROUTINE loop FROM LIB')}).instantiate()
        instance.scheduler.start('MAIN')
        for _ in range(10): instance.scheduler.step()
        instance.programs['MAIN'].pause()
        self.assertEqual(instance.scheduler.run(max_cycles=10)['MAIN']['state'],'paused')
        instance.scheduler.stop('MAIN');self.assertEqual(instance.programs['MAIN']._state.call_depth,0)

    def test_caller_handler_scans_inside_linked_call(self):
        instance=translate_project({'lib':source('LIB','',decl='n FROM MAIN: INTEGER',routines='ROUTINE loop BEGIN WHILE n<10 DO n=n+1 ENDWHILE END loop'),
            'main':source('MAIN','n=0 CONDITION[1]: WHEN n>=3 DO PAUSE ENDCONDITION ENABLE CONDITION[1] loop()',routines='ROUTINE loop FROM LIB')}).instantiate()
        self.assertEqual(instance.run('MAIN')['MAIN']['state'],'paused')
        self.assertLess(instance.programs['MAIN'].snapshot()['N'],10)
        instance.scheduler.continue_task('MAIN');self.assertEqual(instance.scheduler.run()['MAIN']['values']['N'],10)

    def test_load_explicit_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'main.KL').write_text(source('MAIN','n=7'))
            instance=load_project(folder).instantiate();self.assertEqual(instance.run('MAIN')['MAIN']['values']['N'],7)


class SchedulerTests(unittest.TestCase):
    def test_timed_conditions_run_between_cooperative_file_polls(self):
        serial=rt.SerialStreams({
            1:dict(wait=True),
            2:dict(wait_output=True,capacity=4,output=b'old'),
        })
        socket_input=rt.Messaging({'S1:':dict(connected=True,wait=True)})
        socket_output=rt.Messaging({'S2:':dict(connected=True,wait_output=True,output=b'old')},limit=4)
        pipes=rt.FilePipes()
        pipes.configure('LOG',False,1,0,'',0)
        cases=(
            ('serial read',rt.ExecutionContext(serial_streams=serial),
             "OPEN FILE f('RO','P1:') READ f(n,CR)",lambda:serial.feed(1,b'17\n'),17),
            ('serial write',rt.ExecutionContext(serial_streams=serial),
             "OPEN FILE f('WO','P2:') WRITE f('XY')",lambda:serial.take_output(2),77),
            ('socket write',rt.ExecutionContext(messaging=socket_output),
             "OPEN FILE f('WO','S2:') WRITE f('XY')",lambda:socket_output.take_output('S2:'),77),
            ('socket read',rt.ExecutionContext(messaging=socket_input),
             "OPEN FILE f('RO','S1:') READ f(n,CR)",lambda:socket_input.feed('S1:',b'17\n'),17),
            ('pipe read',rt.ExecutionContext(file_pipes=pipes),
             "SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','PIP:LOG') READ f(n,CR)",
             lambda:pipes.feed('LOG',b'17\n'),17),
        )
        for label,context,operation,make_ready,expected in cases:
            with self.subTest(label=label):
                body=('n=77 seen=0 trigger=FALSE CONDITION[1]: WITH $SCAN_TIME=1 '
                      'WHEN trigger DO seen=7 ENDCONDITION ENABLE CONDITION[1] '
                      +operation+' CLOSE FILE f')
                project=translate_project({'main':source('MAIN',body,decl='f:FILE n,seen:INTEGER trigger:BOOLEAN')}).instantiate(context=context)
                scheduler=project.scheduler;task=project.programs['MAIN']
                scheduler.start('MAIN')
                for _ in range(25):
                    scheduler.step()
                    if 'MAIN' in scheduler.waiting:break
                else:self.fail('FILE operation did not park')
                parked_at=scheduler.now_us
                task._state.set('TRIGGER',True)
                for _ in range(25):
                    scheduler.step()
                    if task.snapshot()['SEEN']==7:break
                self.assertEqual(task.snapshot()['SEEN'],7)
                self.assertLess(scheduler.now_us-parked_at,8000)
                self.assertEqual(task.snapshot()['N'],77)
                make_ready()
                result=scheduler.run()['MAIN']
                self.assertEqual((result['state'],result['values']['N']),('completed',expected))

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
        with self.assertRaises(rt.KarelAbort): instance.run('MAIN')
        self.assertEqual(instance.scheduler.snapshot()['CHILD']['state'],'aborted')
        self.assertIsNone(instance.programs['CHILD']._state._scheduler)

    def test_scheduler_budget_bounded(self):
        instance=self.programs('WAIT FOR FALSE','n=1')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cycle budget'): instance.run('MAIN',max_cycles=5)

    def test_invalid_project_cycle_budget_leaves_entry_ready(self):
        instance=self.programs('n=1','')
        before=instance.snapshot()
        with self.assertRaisesRegex(ValueError,'cycle budget'):
            instance.run('MAIN',max_cycles=0)
        self.assertEqual(instance.snapshot(),before)
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['N'],1)

    def test_nested_project_run_leaves_other_entry_ready(self):
        def writer(_):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'recursively'):
                instance.run('CHILD')
        instance=translate_project({'a':source('MAIN','WRITE(1)'), 'b':source('CHILD','n=7')}).instantiate(options={'write':writer})
        result=instance.run('MAIN')
        self.assertEqual(result['CHILD']['state'],'ready')
        self.assertEqual(instance.run('CHILD')['CHILD']['values']['N'],7)

    def test_scheduler_budget_accepts_completion_on_last_cycle(self):
        instance=self.programs('n=1','')
        result=instance.run('MAIN',max_cycles=2)
        self.assertEqual(result['MAIN']['state'],'completed')
        self.assertEqual(result['MAIN']['values']['N'],1)
        self.assertEqual(instance.scheduler.now_us,2*instance.scheduler.quantum_us)

    def test_cycle_budget_failure_can_continue_without_restarting_task(self):
        instance=self.programs('n=1','')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cycle budget'):
            instance.run('MAIN',max_cycles=1)
        self.assertEqual(instance.programs['MAIN'].task_state,'running')
        result=instance.scheduler.run(max_cycles=1)
        self.assertEqual(result['MAIN']['state'],'completed')
        self.assertEqual(result['MAIN']['values']['N'],1)

    def test_service_poll_cannot_reenter_step_or_run(self):
        ctx=rt.ExecutionContext(ports=rt.PortBank({'DOUT':1}))
        instance=translate_project({'a':source('MAIN','n=1')}).instantiate(context=ctx)
        scheduler=instance.scheduler
        attempts=[]
        armed=False

        def clock():
            if armed:
                for drive in (scheduler.step,scheduler.run):
                    with self.assertRaisesRegex(rt.KarelRuntimeError,'recursively'):drive()
                attempts.append(scheduler.now_us)
            return 0

        pulse,_=compile_program('PULSE DOUT[1] FOR 8 NOWAIT',context=ctx,clock_us=clock)
        pulse.run()
        scheduler.start('MAIN')
        armed=True
        self.assertTrue(scheduler.step())
        self.assertEqual(set(attempts),{0,scheduler.quantum_us})
        self.assertEqual(scheduler.run(max_cycles=1)['MAIN']['values']['N'],1)
        self.assertEqual(scheduler.now_us,2*scheduler.quantum_us)

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

    def test_periodic_handler_runs_before_a_linked_delay_completes(self):
        body=('n=0 s=0 CONNECT TIMER TO s CONDITION[1]: WITH $SCAN_TIME=10 '
              'WHEN s>=10 DO n=7 ENDCONDITION ENABLE CONDITION[1] work() n=n+1')
        instance=translate_project({
            'main':source('MAIN',body,routines='ROUTINE work FROM LIB'),
            'lib':source('LIB','',routines='ROUTINE work BEGIN DELAY 100 END work'),
        }).instantiate()
        scheduler=instance.scheduler
        task=instance.programs['MAIN']
        scheduler.start('MAIN')
        for _ in range(30):
            scheduler.step()
            if task.snapshot()['N']==7:break
        self.assertEqual(task.snapshot()['N'],7)
        self.assertLess(scheduler.now_us,100000)
        self.assertNotEqual(task.task_state,'completed')
        self.assertEqual(scheduler.run()['MAIN']['values']['N'],8)

    def test_injected_handler_clock_does_not_schedule_virtual_deadlines(self):
        scheduler=rt.TaskScheduler()
        p,_=compile_program('n=0 CONDITION[1]: WITH $SCAN_TIME=10 WHEN n=1 DO n=7 ENDCONDITION '
                            'ENABLE CONDITION[1] n=1 DELAY 100',clock_us=lambda:0,
                            context=rt.ExecutionContext(tasks=scheduler),cooperative=True)
        scheduler.bind('MAIN',p)
        result=scheduler.run(max_cycles=20,entry='MAIN')['MAIN']
        self.assertEqual((result['state'],result['values']['N']),('completed',1))
        self.assertGreaterEqual(scheduler.now_us,100000)

    def test_periodic_scans_count_against_task_budget(self):
        program=source('MAIN','n=0 CONDITION[1]: WITH $SCAN_TIME=1 WHEN FALSE DO n=7 ENDCONDITION '
                               'ENABLE CONDITION[1] DELAY 1000 n=8')
        instance=translate_project({'main':program}).instantiate()
        instance.scheduler.max_steps=10
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):instance.run('MAIN')
        self.assertEqual(instance.programs['MAIN'].snapshot()['N'],0)
        self.assertLess(instance.scheduler.now_us,1000000)

    def test_local_handler_lifetime(self):
        p,_=compile_program('work() n=1',routines='ROUTINE work BEGIN CONDITION[1]: WHEN FALSE DO n=9 ENDCONDITION END work',context=rt.ExecutionContext(local_handlers=True))
        p.run();self.assertEqual(p._state._handlers,{})


if __name__=='__main__': unittest.main()
