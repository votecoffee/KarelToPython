"""Authored timed-output, clock, ownership and scheduler integration checks."""
import json
import unittest

from karel2py import translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source


def setup(body='PULSE DOUT[1] FOR 9 NOWAIT',*,initial=False,**options):
    ports=rt.PortBank({'DOUT':2},{('DOUT',1):initial,('DOUT',2):False});clock={'us':0}
    context=rt.ExecutionContext(ports=ports)
    p,result=compile_program(body,context=context,clock_us=lambda:clock['us'],**options)
    return p,ports,clock,result


class PulseClockTests(unittest.TestCase):
    def test_nowait_turns_on_then_expires_at_rounded_deadline(self):
        p,ports,clock,result=setup();p.run()
        self.assertTrue(result.report['cooperative_execution']);self.assertTrue(ports.read('DOUT',1));self.assertEqual(ports.pending_pulses,1)
        clock['us']=15999;self.assertTrue(ports.read('DOUT',1))
        clock['us']=16000;self.assertEqual(ports.poll_pulses(),1);self.assertFalse(ports.read('DOUT',1));self.assertEqual(ports.pending_pulses,0)

    def test_blocking_sleep_uses_rounded_duration_and_forces_logical_completion(self):
        sleeps=[];p,ports,clock,_=setup('PULSE DOUT[1] FOR 9 after=DOUT[1]',decl='after: BOOLEAN',sleep=sleeps.append)
        self.assertFalse(p.run()['AFTER']);self.assertEqual(sleeps,[.016]);self.assertEqual(clock['us'],0);self.assertEqual(ports.pending_pulses,0)

    def test_rounding_and_maximum_duration(self):
        for duration,rounded in ((1,8),(8,8),(9,16),(86400000,86400000)):
            with self.subTest(duration=duration):
                p,ports,clock,_=setup(f'PULSE DOUT[1] FOR {duration} NOWAIT');p.run()
                clock['us']=rounded*1000;self.assertEqual(ports.poll_pulses(),1)

    def test_zero_duration_preserves_value_without_clock_or_wait(self):
        for initial in (False,True):
            with self.subTest(initial=initial):
                p,ports,_,_=setup('PULSE DOUT[1] FOR 0',initial=initial,sleep=lambda _:self.fail('zero pulse waited'))
                p._state._clock_us=lambda:self.fail('zero pulse sampled a clock');p.run()
                self.assertEqual(ports.snapshot()['DOUT',1],initial);self.assertEqual(ports.pending_pulses,0)

    def test_zero_duration_does_not_cancel_an_existing_pulse(self):
        p,ports,clock,_=setup('PULSE DOUT[1] FOR 9 NOWAIT PULSE DOUT[1] FOR 0');p.run()
        self.assertEqual(ports.pending_pulses,1);clock['us']=16000;ports.poll_pulses();self.assertFalse(ports.read('DOUT',1))

    def test_normally_on_port_ends_off(self):
        p,ports,clock,_=setup(initial=True);p.run();clock['us']=16000;ports.poll_pulses();self.assertFalse(ports.read('DOUT',1))

    def test_invalid_duration_and_port_do_not_change_values(self):
        for body in ('PULSE DOUT[1] FOR -1','PULSE DOUT[1] FOR 86400001','PULSE DOUT[0] FOR 8','PULSE DOUT[3] FOR 8'):
            with self.subTest(body=body):
                p,ports,_,_=setup(body)
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertFalse(ports.read('DOUT',1));self.assertEqual(ports.pending_pulses,0)

    def test_bad_clock_samples_fail_before_start(self):
        for value in (-1,True,1.5):
            with self.subTest(value=value):
                p,ports,_,_=setup();p._state._clock_us=lambda:value
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertFalse(ports.values['DOUT',1]);self.assertEqual(ports.pending_pulses,0)

    def test_clock_exception_has_source_line(self):
        p,ports,_,_=setup()
        def failed(): raise OSError('authored clock failure')
        p._state._clock_us=failed
        with self.assertRaisesRegex(rt.KarelRuntimeError,'authored clock failure') as caught: p.run()
        self.assertIsNotNone(caught.exception.line);self.assertFalse(ports.values['DOUT',1])

    def test_backward_clock_does_not_expire_or_modify_pending_pulse(self):
        p,ports,clock,_=setup();clock['us']=1000;p.run();clock['us']=0
        with self.assertRaisesRegex(rt.KarelRuntimeError,'backwards'): ports.poll_pulses()
        self.assertTrue(ports.values['DOUT',1]);self.assertEqual(ports.pending_pulses,1)

    def test_multiple_expirations_validate_all_samples_before_mutation(self):
        p,ports,clock,_=setup('PULSE DOUT[1] FOR 8 NOWAIT PULSE DOUT[2] FOR 8 NOWAIT');p.run()
        ports._pulses['DOUT',2].clock=lambda:-1;clock['us']=8000
        with self.assertRaises(rt.KarelRuntimeError): ports.poll_pulses()
        self.assertEqual(ports.values,{('DOUT',1):True,('DOUT',2):True});self.assertEqual(ports.pending_pulses,2)

    def test_recursive_clock_poll_is_rejected(self):
        p,ports,_,_=setup();p.run();ports._pulses['DOUT',1].clock=lambda:ports.read('DOUT',1)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'recurse'): ports.poll_pulses()
        self.assertTrue(ports.values['DOUT',1])

    def test_serialization_keeps_current_values_but_not_pending_work(self):
        p,ports,clock,_=setup();p.run();context=p._state.execution
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(context.to_config())))
        self.assertTrue(restored.ports.read('DOUT',1));self.assertEqual(restored.ports.pending_pulses,0)
        clock['us']=16000;self.assertFalse(ports.snapshot()['DOUT',1]);self.assertTrue(restored.ports.read('DOUT',1))


class PulseOwnershipTests(unittest.TestCase):
    def test_direct_write_cancels_pending_expiration(self):
        p,ports,clock,_=setup('PULSE DOUT[1] FOR 9 NOWAIT DOUT[1]=TRUE');p.run()
        self.assertEqual(ports.pending_pulses,0);clock['us']=16000;self.assertTrue(ports.read('DOUT',1))

    def test_host_update_cancels_pending_expiration(self):
        p,ports,clock,_=setup();p.run();ports.update('DOUT',1,True);clock['us']=16000
        self.assertTrue(ports.read('DOUT',1));self.assertEqual(ports.pending_pulses,0)

    def test_indirect_write_cancels_pending_expiration(self):
        p,ports,clock,_=setup('PULSE DOUT[1] FOR 9 NOWAIT SET_PORT_VAL(7,1,TRUE,s)');ports.type_codes={7:'DOUT'}
        self.assertEqual(p.run()['S'],0);clock['us']=16000;self.assertTrue(ports.read('DOUT',1));self.assertEqual(ports.pending_pulses,0)

    def test_failed_write_does_not_cancel_pending_pulse(self):
        p,ports,clock,_=setup();p.run()
        with self.assertRaises(rt.KarelRuntimeError): ports.write('DOUT',1,42)
        self.assertEqual(ports.pending_pulses,1);clock['us']=16000;ports.poll_pulses();self.assertFalse(ports.read('DOUT',1))

    def test_busy_port_rejects_new_pulse_without_replacing_owner(self):
        p,ports,clock,_=setup();p.run();original=ports._pulses['DOUT',1]
        other,_=compile_program('PULSE DOUT[1] FOR 8 NOWAIT',context=p._state.execution,clock_us=lambda:clock['us'])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'pending pulse'): other.run()
        self.assertIs(ports._pulses['DOUT',1],original);clock['us']=16000;ports.poll_pulses();self.assertFalse(ports.read('DOUT',1))

    def test_abort_freezes_last_output_and_cancels_deadline(self):
        p,ports,clock,_=setup('PULSE DOUT[1] FOR 9 NOWAIT ABORT')
        with self.assertRaises(rt.KarelAbort): p.run()
        clock['us']=16000;ports.poll_pulses();self.assertTrue(ports.read('DOUT',1));self.assertEqual(ports.pending_pulses,0)

    def test_stop_and_runtime_failure_freeze_output(self):
        for ending in ('STOP','n=1 DIV 0'):
            with self.subTest(ending=ending):
                p,ports,clock,_=setup('PULSE DOUT[1] FOR 9 NOWAIT '+ending)
                with self.assertRaises((rt.KarelStop,rt.KarelRuntimeError)): p.run()
                clock['us']=16000;ports.poll_pulses();self.assertTrue(ports.read('DOUT',1));self.assertEqual(ports.pending_pulses,0)

    def test_paused_pulse_expires_without_resume(self):
        p,ports,clock,_=setup('PULSE DOUT[1] FOR 9 NOWAIT PAUSE n=1')
        with self.assertRaises(rt.KarelPause): p.run()
        clock['us']=16000;ports.poll_pulses();self.assertFalse(ports.read('DOUT',1));self.assertEqual(p.task_state,'paused')
        self.assertEqual(p.resume()['N'],1)

    def test_stopping_paused_owner_freezes_output(self):
        p,ports,clock,_=setup('PULSE DOUT[1] FOR 9 NOWAIT PAUSE')
        with self.assertRaises(rt.KarelPause): p.run()
        p.stop();clock['us']=16000;ports.poll_pulses();self.assertTrue(ports.read('DOUT',1))

    def test_abort_from_clock_cannot_start_pulse(self):
        p,ports,_,_=setup()
        def aborting():
            try: p._state.abort(99)
            except rt.KarelAbort: pass
            return 0
        p._state._clock_us=aborting
        with self.assertRaises(rt.KarelAbort): p.run()
        self.assertFalse(ports.values['DOUT',1]);self.assertEqual(ports.pending_pulses,0)

    def test_abort_during_poll_does_not_turn_output_off(self):
        p,ports,_,_=setup();p.run()
        def aborting():
            try: p._state.abort(99)
            except rt.KarelAbort: pass
            return 16000
        ports._pulses['DOUT',1].clock=aborting;ports.poll_pulses()
        self.assertTrue(ports.values['DOUT',1]);self.assertEqual(ports.pending_pulses,0)

    def test_blocking_wait_failure_retains_on_value(self):
        def failed(_): raise OSError('authored wait failure')
        p,ports,_,_=setup('PULSE DOUT[1] FOR 8',sleep=failed)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'authored wait failure'): p.run()
        ports.poll_pulses();self.assertTrue(ports.read('DOUT',1))

    def test_blocking_wait_override_is_not_overwritten_at_completion(self):
        ports=None
        def override(_): ports.update('DOUT',1,True)
        p,ports,_,_=setup('PULSE DOUT[1] FOR 8',sleep=override);p.run()
        self.assertTrue(ports.read('DOUT',1));self.assertEqual(ports.pending_pulses,0)


class PulseSchedulerTests(unittest.TestCase):
    def scheduler(self,body,**options):
        ports=rt.PortBank({'DOUT':1},{('DOUT',1):False});tasks=rt.TaskScheduler()
        p,_=compile_program(body,context=rt.ExecutionContext(ports=ports,tasks=tasks),**options)
        tasks.bind('worker',p);tasks.start('worker');return tasks,p,ports

    def test_scheduler_drains_nowait_pulse_after_owner_completion(self):
        tasks,p,ports=self.scheduler('PULSE DOUT[1] FOR 9 NOWAIT n=1')
        tasks.run();self.assertEqual(p.task_state,'completed');self.assertFalse(ports.read('DOUT',1));self.assertGreaterEqual(tasks.now_us,16000)

    def test_scheduler_drains_pulse_while_owner_is_paused(self):
        tasks,p,ports=self.scheduler('PULSE DOUT[1] FOR 9 NOWAIT PAUSE n=1')
        tasks.run();self.assertEqual(p.task_state,'paused');self.assertFalse(ports.read('DOUT',1));tasks.continue_task('worker');tasks.run();self.assertEqual(p.snapshot()['N'],1)

    def test_blocking_pulse_parks_task_without_host_sleep(self):
        tasks,p,ports=self.scheduler('PULSE DOUT[1] FOR 9 n=1',sleep=lambda _:self.fail('scheduler called host sleep'))
        tasks.run();self.assertEqual(p.snapshot()['N'],1);self.assertFalse(ports.read('DOUT',1))

    def test_scheduler_uses_virtual_time_with_an_injected_program_clock(self):
        tasks,p,ports=self.scheduler('PULSE DOUT[1] FOR 9 NOWAIT',clock_us=lambda:0)
        tasks.run();self.assertFalse(ports.read('DOUT',1));self.assertGreaterEqual(tasks.now_us,16000)

    def test_another_task_observes_on_and_off_during_blocking_pulse(self):
        ports=rt.PortBank({'DOUT':1},{('DOUT',1):False});tasks=rt.TaskScheduler();ctx=rt.ExecutionContext(ports=ports,tasks=tasks)
        pulse,_=compile_program('PULSE DOUT[1] FOR 40',context=ctx)
        watch,_=compile_program('before=DOUT[1] DELAY 60 after=DOUT[1]',decl='before,after: BOOLEAN',context=ctx,cooperative=True)
        tasks.bind('pulse',pulse);tasks.bind('watch',watch);tasks.start('pulse');tasks.start('watch');tasks.run()
        self.assertEqual(watch.snapshot(),{'BEFORE':True,'AFTER':False})

    def test_linked_pulse_is_owned_by_calling_task(self):
        sources={'main':source('MAIN','trigger() PAUSE',routines='ROUTINE trigger FROM LIB'),
                 'lib':source('LIB','',routines='ROUTINE trigger BEGIN PULSE DOUT[1] FOR 40 NOWAIT END trigger')}
        ports=rt.PortBank({'DOUT':1},{('DOUT',1):False});instance=translate_project(sources).instantiate(context=rt.ExecutionContext(ports=ports))
        instance.scheduler.start('MAIN')
        for _ in range(10):
            instance.scheduler.step()
            if ports._pulses: break
        else: self.fail('linked pulse did not start')
        self.assertIs(ports._pulses['DOUT',1].owner,instance.programs['MAIN']._state)
        instance.scheduler.run();self.assertFalse(ports.read('DOUT',1));self.assertEqual(instance.programs['MAIN'].task_state,'paused')

    def test_cycle_budget_does_not_silently_finish_pending_pulse(self):
        tasks,p,ports=self.scheduler('PULSE DOUT[1] FOR 40 NOWAIT FOR n=1 TO 10 DO ENDFOR')
        for _ in range(10):
            tasks.step()
            if ports._pulses: break
        else: self.fail('pulse did not start')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cycle budget'): tasks.run(max_cycles=1)
        self.assertTrue(ports.read('DOUT',1));tasks.run();self.assertFalse(ports.read('DOUT',1))


class PulseSourceTests(unittest.TestCase):
    def test_types_target_and_handler_nowait_guards(self):
        for body in ('PULSE DIN[1] FOR 8','PULSE DOUT[TRUE] FOR 8','PULSE DOUT[1] FOR 1.5','CONDITION[1]: WHEN TRUE DO PULSE DOUT[1] FOR 8 NOWAIT ENDCONDITION'):
            with self.subTest(body=body),self.assertRaises(TranslationError): compile_program(body)

    def test_shadowed_dout_does_not_silently_use_port_bank(self):
        with self.assertRaises(TranslationError): compile_program('PULSE DOUT[1] FOR 8',decl='DOUT: ARRAY[1] OF BOOLEAN')

    def test_operands_are_evaluated_once_in_source_order(self):
        routines="ROUTINE port_no: INTEGER BEGIN trace=trace+'P' RETURN 1 END port_no ROUTINE duration: INTEGER BEGIN trace=trace+'D' RETURN 9 END duration"
        p,ports,_,_=setup("trace='' PULSE DOUT[port_no()] FOR duration()",decl='trace: STRING[8]',routines=routines,sleep=lambda _:None)
        self.assertEqual(p.run()['TRACE'],'PD');self.assertFalse(ports.read('DOUT',1))

    def test_blocking_handler_action_runs(self):
        sleeps=[];p,ports,_,_=setup('CONDITION[1]: WHEN TRUE DO PULSE DOUT[1] FOR 9 ENDCONDITION ENABLE CONDITION[1] n=1',sleep=sleeps.append)
        self.assertEqual(p.run()['N'],1);self.assertEqual(sleeps,[.016]);self.assertFalse(ports.read('DOUT',1))

    def test_missing_context_is_source_located(self):
        p,_=compile_program('PULSE DOUT[1] FOR 8')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ports') as caught: p.run()
        self.assertIsNotNone(caught.exception.line)

    def test_for_counter_can_be_read_as_pulse_operand(self):
        sleeps=[];p,ports,_,_=setup('FOR n=1 TO 2 DO PULSE DOUT[n] FOR n ENDFOR',sleep=sleeps.append)
        p.run();self.assertEqual(sleeps,[.008,.008]);self.assertEqual(ports.snapshot(),{('DOUT',1):False,('DOUT',2):False})

    def test_pulse_cannot_bypass_transitive_for_counter_write_guards(self):
        routines='ROUTINE helper BEGIN n=9 PULSE DOUT[1] FOR 8 END helper'
        with self.assertRaises(TranslationError): compile_program('FOR n=1 TO 2 DO helper() ENDFOR',routines=routines)

    def test_pulse_observations_contain_no_values(self):
        p,_,_,result=setup();p.run();rows=[row for row in p.service_requests if row['operation']=='PULSE']
        self.assertEqual(len(rows),1);self.assertEqual(set(rows[0]),{'operation','line','outcome'});self.assertEqual(rows[0]['outcome'],'completed')
        self.assertFalse(result.report['pulse_policy']['controller_validated']);self.assertTrue(result.report['pulses'][0]['nowait'])

    def test_blocking_delay_effect_propagates_through_routines(self):
        for suffix,delays in (('',True),(' NOWAIT',False)):
            with self.subTest(suffix=suffix):
                routines=f'ROUTINE inner BEGIN PULSE DOUT[1] FOR 8{suffix} END inner ROUTINE outer BEGIN inner() END outer'
                p,_,_,result=setup('outer()',routines=routines,sleep=lambda _:None);p.run()
                for name in ('INNER','OUTER'): self.assertEqual(result.report['routine_effects'][name]['potential_host_delays'],delays)


if __name__=='__main__': unittest.main()
