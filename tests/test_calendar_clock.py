"""Authored offline calendar time, elapsed adapters and persistence checks."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest

from karel2py import translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


BASE=datetime(2024,2,29,12,34,56)
PACKED=1482515548


def context(value=BASE,**options): return rt.ExecutionContext(calendar=rt.CalendarClock(value,**options))


class CalendarDataTests(unittest.TestCase):
    def test_frozen_get_matches_independent_known_bit_pattern(self):
        state=run('GET_TIME(n) CNV_TIME_STR(n,text)',decl='n: INTEGER text: STRING[20]',context=context())
        self.assertEqual(state,{'N':PACKED,'TEXT':'29-FEB-2024 12:34:56'})

    def test_set_from_text_roundtrips_through_calendar_service(self):
        state=run("CNV_STR_TIME('01-JAN-1980 00:00:00',n) SET_TIME(n) GET_TIME(s) CNV_TIME_STR(s,text)",decl='n,s: INTEGER text: STRING[20]',context=context())
        self.assertEqual((state['N'],state['S'],state['TEXT']),(2162688,2162688,'01-JAN-1980 00:00:00'))

    def test_set_zero_does_not_change_frozen_value(self):
        ctx=context();state=run('SET_TIME(0) GET_TIME(n)',context=ctx)
        self.assertEqual(state['N'],PACKED);self.assertEqual(ctx.calendar.now(),BASE)

    def test_invalid_text_zero_is_a_noop(self):
        ctx=context();state=run("CNV_STR_TIME('invalid',n) SET_TIME(n) GET_TIME(s)",context=ctx)
        self.assertEqual((state['N'],state['S']),(0,PACKED))

    def test_all_year_boundaries_and_leap_dates(self):
        for stamp in (datetime(1980,1,1),datetime(2000,2,29,23,59,58),datetime(2043,12,31,23,59,58),datetime(2044,1,1),datetime(2107,12,31,23,59,58)):
            with self.subTest(stamp=stamp):
                clock=rt.CalendarClock(stamp);clone=rt.CalendarClock(clock.read())
                self.assertEqual(clone.now(),stamp);self.assertEqual(clock.read()<0,stamp.year>=2044)

    def test_odd_seconds_and_fractions_retained_in_host_value(self):
        stamp=BASE.replace(second=57,microsecond=987654);clock=rt.CalendarClock(stamp)
        self.assertEqual(clock.read(),PACKED);self.assertEqual(clock.now(),stamp)

    def test_host_set_accepts_datetime_and_packed_values(self):
        clock=rt.CalendarClock(BASE);clock.set(datetime(1980,1,1));self.assertEqual(clock.read(),2162688)
        clock.set(PACKED);self.assertEqual(clock.now(),BASE)

    def test_invalid_initial_values_are_not_guessed(self):
        for value in (0,True,False,1.,'2024-01-01',rt.UNINITIALIZED,datetime(1979,12,31),datetime(2108,1,1),BASE.replace(tzinfo=timezone.utc)):
            with self.subTest(value=value),self.assertRaises((ValueError,rt.KarelRuntimeError)): rt.CalendarClock(value)

    def test_invalid_set_preserves_previous_calendar_value(self):
        clock=rt.CalendarClock(BASE)
        for value in (True,-1,1,2**31,PACKED|31,BASE.replace(tzinfo=timezone.utc),datetime(2108,1,1)):
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError): clock.set(value)
            self.assertEqual(clock.now(),BASE)

    def test_separate_programs_share_calendar_updates(self):
        ctx=context();run('SET_TIME(2162688)',context=ctx)
        self.assertEqual(run('GET_TIME(n)',context=ctx)['N'],2162688)

    def test_independent_contexts_do_not_share_time(self):
        first=context();second=context();run('SET_TIME(2162688)',context=first)
        self.assertEqual(run('GET_TIME(n)',context=second)['N'],PACKED)


class ElapsedCalendarTests(unittest.TestCase):
    def clock(self,value=BASE):
        current={'us':100,'reads':0}
        def sample(): current['reads']+=1;return current['us']
        return rt.CalendarClock(value,clock_us=sample),current

    def test_constructor_samples_anchor_once_then_floors_observations(self):
        clock,current=self.clock();self.assertEqual(current['reads'],1)
        current['us']+=1999999;self.assertEqual(clock.read(),PACKED)
        current['us']+=1;self.assertEqual(clock.read(),PACKED+1);self.assertEqual(current['reads'],3)

    def test_fractional_time_carried_across_calendar_boundary(self):
        clock,current=self.clock(datetime(2024,2,28,23,59,59,500000))
        current['us']+=500000;self.assertEqual(clock.now(),datetime(2024,2,29))
        current['us']+=86400000000;self.assertEqual(clock.now(),datetime(2024,3,1))

    def test_elapsed_clock_advances_when_program_delays(self):
        clock,current=self.clock();ctx=rt.ExecutionContext(calendar=clock)
        def sleep(seconds): current['us']+=round(seconds*1000000)
        state=run('GET_TIME(n) DELAY 2000 GET_TIME(s)',context=ctx,sleep=sleep)
        self.assertEqual((state['N'],state['S']),(PACKED,PACKED+1))

    def test_set_resets_anchor_and_later_elapsed_time_continues(self):
        clock,current=self.clock();current['us']+=5000000;clock.set(2162688)
        current['us']+=2000000;self.assertEqual(clock.now(),datetime(1980,1,1,0,0,2))

    def test_zero_set_does_not_sample_or_reset_anchor(self):
        clock,current=self.clock();current['us']+=2000000;clock.set(0)
        self.assertEqual(current['reads'],1);self.assertEqual(clock.read(),PACKED+1)

    def test_invalid_set_is_checked_before_sampling(self):
        clock,current=self.clock()
        with self.assertRaises(rt.KarelRuntimeError): clock.set(-1)
        self.assertEqual(current['reads'],1);self.assertEqual(clock.read(),PACKED)

    def test_backward_observation_fails_and_can_recover(self):
        clock,current=self.clock();current['us']=200;clock.read();current['us']=199
        with self.assertRaisesRegex(rt.KarelRuntimeError,'backwards'): clock.read()
        current['us']=200;self.assertEqual(clock.read(),PACKED)

    def test_backward_set_does_not_replace_anchor(self):
        clock,current=self.clock();current['us']=200;clock.read();current['us']=199
        with self.assertRaisesRegex(rt.KarelRuntimeError,'backwards'): clock.set(2162688)
        current['us']=200;self.assertEqual(clock.read(),PACKED)

    def test_bad_adapter_result_preserves_get_output(self):
        for invalid in (True,-1,1.,None,'2'):
            with self.subTest(invalid=invalid):
                samples=iter((0,invalid,0));clock=rt.CalendarClock(BASE,clock_us=lambda:next(samples))
                p,_=compile_program('n=7 GET_TIME(n)',context=rt.ExecutionContext(calendar=clock))
                with self.assertRaises(rt.KarelRuntimeError) as caught: p.run()
                self.assertIsNotNone(caught.exception.line);self.assertEqual(p.snapshot()['N'],7);self.assertEqual(clock.read(),PACKED)

    def test_callback_exception_has_cause_and_does_not_retry(self):
        calls=[]
        def sample():
            calls.append(1)
            if len(calls)>1: raise OSError('authored failure')
            return 0
        p,_=compile_program('n=7 GET_TIME(n)',context=context(clock_us=sample))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Calendar elapsed clock failed') as caught: p.run()
        self.assertIsInstance(caught.exception.__cause__,OSError);self.assertEqual(len(calls),2);self.assertEqual(p.snapshot()['N'],7)

    def test_invalid_adapter_type_rejected_at_construction(self):
        async def async_sample(): return 0
        for adapter in (7,True,async_sample):
            with self.subTest(adapter=adapter),self.assertRaises(TypeError): rt.CalendarClock(BASE,clock_us=adapter)

    def test_awaitable_result_is_closed_and_rejected(self):
        async def value(): return 0
        with self.assertRaisesRegex(rt.KarelRuntimeError,'synchronous'): rt.CalendarClock(BASE,clock_us=lambda:value())

    def test_elapsed_outside_calendar_range_preserves_output(self):
        clock,current=self.clock(datetime(2107,12,31,23,59,59));current['us']+=1000000
        p,_=compile_program('n=7 GET_TIME(n)',context=rt.ExecutionContext(calendar=clock))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['N'],7)

    def test_enormous_elapsed_interval_is_a_source_located_error(self):
        clock,current=self.clock();current['us']=10**100
        p,_=compile_program('n=7 GET_TIME(n)',context=rt.ExecutionContext(calendar=clock))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'supported range') as caught: p.run()
        self.assertIsNotNone(caught.exception.line);self.assertEqual(p.snapshot()['N'],7)

    def test_scheduler_can_supply_explicit_virtual_elapsed_time(self):
        scheduler=rt.TaskScheduler();clock=rt.CalendarClock(BASE,clock_us=lambda:scheduler.now_us)
        ctx=rt.ExecutionContext(tasks=scheduler,calendar=clock)
        p,_=compile_program('GET_TIME(n) DELAY 2000 GET_TIME(s)',cooperative=True,context=ctx)
        scheduler.bind('T',p);scheduler.start('T');scheduler.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(PACKED,PACKED+1))

    def test_calendar_set_does_not_reset_connected_timer_or_microsecond_clock(self):
        current={'us':0};sample=lambda:current['us'];ctx=context(clock_us=sample)
        def sleep(seconds): current['us']+=round(seconds*1000000)
        state=run('elapsed_ms=0 CONNECT TIMER TO elapsed_ms first=GET_USEC_TIM SET_TIME(2162688) DELAY 2000 GET_TIME(n) last=GET_USEC_TIM delta=GET_USEC_SUB(last,first) DISCONNECT TIMER elapsed_ms',decl='elapsed_ms,first,last,delta,n: INTEGER',context=ctx,clock_us=sample,sleep=sleep)
        self.assertEqual((state['ELAPSED_MS'],state['FIRST'],state['LAST'],state['DELTA'],state['N']),(2000,0,2000000,2000000,2162689))


class CalendarPersistenceTests(unittest.TestCase):
    def test_snapshot_retains_complete_microsecond_value(self):
        stamp=BASE.replace(second=57,microsecond=123456);ctx=context(stamp)
        config=ctx.to_config();self.assertEqual(config,{'calendar':{'value':'2024-02-29T12:34:57.123456'}})
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(config)))
        self.assertEqual(restored.calendar.now(),stamp);self.assertEqual(restored.to_config(),config)

    def test_live_adapter_restores_as_frozen_snapshot(self):
        current={'us':0};ctx=context(clock_us=lambda:current['us']);current['us']=1234567
        config=ctx.to_config();restored=rt.ExecutionContext.from_config(config);current['us']=9999999
        self.assertEqual(restored.calendar.now(),BASE+timedelta(microseconds=1234567))
        self.assertEqual(restored.to_config(),config);self.assertNotEqual(ctx.calendar.now(),restored.calendar.now())

    def test_save_load_preserves_source_set_and_attached_globals(self):
        ctx=context();run('SET_TIME(2162688) GET_TIME(n)',context=ctx)
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'state.json';ctx.save(target);restored=rt.ExecutionContext.load(target)
        self.assertEqual(restored.to_config(),ctx.to_config());self.assertEqual(restored.calendar.read(),2162688)

    def test_invalid_configuration_shapes_and_dates(self):
        for row in (None,True,{},[],{'value':1},{'value':True},{'value':BASE.isoformat(),'extra':0},{'value':'2024-02-30T12:00:00'},{'value':'2024-01-01'},{'value':'2024-01-01T00:00:00Z'},{'value':'2108-01-01T00:00:00'},{'value':'2024-01-01T00:00:00.1234567'}):
            with self.subTest(row=row),self.assertRaises((ValueError,rt.KarelRuntimeError)): rt.ExecutionContext.from_config({'calendar':row})

    def test_missing_calendar_keeps_legacy_context_shape(self):
        self.assertEqual(rt.ExecutionContext().to_config(),{});self.assertEqual(rt.ExecutionContext.from_config({}).to_config(),{})
        with self.assertRaises(TypeError): rt.ExecutionContext(calendar=BASE)

    def test_failed_snapshot_does_not_replace_existing_file(self):
        current={'us':0};ctx=context(clock_us=lambda:current['us'])
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'state.json';target.write_text('original',encoding='utf-8');current['us']=-1
            with self.assertRaises(rt.KarelRuntimeError): ctx.save(target)
            self.assertEqual(target.read_text(),'original')


class CalendarSourceOwnershipTests(unittest.TestCase):
    def test_missing_context_preserves_pending_get_output(self):
        for body in ('GET_TIME(n)','SET_TIME(2162688)','SET_TIME(0)'):
            with self.subTest(body=body):
                p,_=compile_program('n=7 '+body)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'calendar'): p.run()
                self.assertEqual(p.snapshot()['N'],7)

    def test_invalid_source_set_preserves_clock_and_prior_source_effects(self):
        ctx=context();p,_=compile_program('n=7 SET_TIME(-1)',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['N'],7);self.assertEqual(ctx.calendar.read(),PACKED)

    def test_argument_types_arity_and_output_reference_guards(self):
        for body in ('GET_TIME()','GET_TIME(n,s)','GET_TIME(0)','GET_TIME(x)','GET_TIME(short)','SET_TIME()','SET_TIME(n,s)','SET_TIME(x)','SET_TIME(TRUE)'):
            with self.subTest(body=body),self.assertRaises(TranslationError): compile_program(body,decl='n,s: INTEGER x: REAL short: SHORT')

    def test_direct_transitive_and_handler_for_counter_guards(self):
        for body,routines in (('FOR n=1 TO 2 DO GET_TIME(n) ENDFOR',''),('FOR n=1 TO 2 DO sample(n) ENDFOR','ROUTINE sample(out: INTEGER) BEGIN GET_TIME(out) END sample'),('FOR n=1 TO 2 DO sample() ENDFOR','ROUTINE sample BEGIN GET_TIME(n) END sample'),('CONDITION[1]: WHEN TRUE DO GET_TIME(n) ENDCONDITION FOR n=1 TO 2 DO ENDFOR','')):
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught: compile_program(body,routines=routines)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_target_selectors_run_once_before_clock_observation(self):
        current={'us':0};ctx=context(clock_us=lambda:current['us'])
        def update(text): current['us']=2000000
        state=run('count=0 GET_TIME(a[slot()])',decl='count: INTEGER a: ARRAY[1] OF INTEGER',routines="ROUTINE slot: INTEGER BEGIN count=count+1 WRITE('advance') RETURN 1 END slot",context=ctx,write=update)
        self.assertEqual((state['COUNT'],state['A'][0]),(1,PACKED+1))

    def test_set_input_is_captured_once(self):
        state=run('count=0 SET_TIME(value()) GET_TIME(n)',decl='count,n,s: INTEGER',routines='ROUTINE value: INTEGER BEGIN count=count+1 RETURN 2162688 END value',context=context())
        self.assertEqual((state['COUNT'],state['N']),(1,2162688))

    def test_user_routines_and_variables_keep_precedence(self):
        for name in ('GET_TIME','SET_TIME'):
            with self.subTest(name=name):
                self.assertEqual(run(f'{name}(7)',routines=f'ROUTINE {name}(value: INTEGER) BEGIN n=value END {name}')['N'],7)
                self.assertEqual(run(f'{name}=7',decl=f'{name}: INTEGER')[name],7)

    def test_budget_exhaustion_happens_before_get_sampling(self):
        calls=[];clock=rt.CalendarClock(BASE,clock_us=lambda:calls.append(0) or 0)
        p,_=compile_program('n=7 GET_TIME(n)',context=rt.ExecutionContext(calendar=clock))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'): p.run(max_steps=1)
        self.assertEqual(len(calls),1);self.assertEqual(p.snapshot()['N'],7)

    def test_runtime_failure_unwinds_frames(self):
        p,_=compile_program('sample()',routines='ROUTINE sample VAR local: INTEGER BEGIN local=7 GET_TIME(local) END sample')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p._state.local_frames,[]);self.assertEqual(p._state.call_depth,0)

    def test_linked_set_and_get_share_callers_context(self):
        routine='ROUTINE reset BEGIN SET_TIME(2162688) END reset'
        instance=translate_project({'lib':source('LIB','',routines=routine),'main':source('MAIN','reset() GET_TIME(n)',routines='ROUTINE reset FROM LIB')}).instantiate(context=context())
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['N'],2162688)

    def test_pause_resume_retains_same_calendar_service(self):
        ctx=context();p,_=compile_program('GET_TIME(n) PAUSE GET_TIME(s)',context=ctx)
        with self.assertRaises(rt.KarelPause): p.run()
        ctx.calendar.set(2162688);self.assertEqual((p.resume()['N'],p.snapshot()['S']),(PACKED,2162688))

    def test_report_and_service_records_omit_clock_values(self):
        p,result=compile_program('GET_TIME(n) SET_TIME(0)',context=context());p.run()
        self.assertFalse(result.report['calendar_clock_policy']['controller_validated'])
        self.assertEqual([row['operation'] for row in p.service_requests],['GET_TIME','SET_TIME'])
        self.assertTrue(all(set(row)=={'operation','line','outcome'} for row in p.service_requests))


if __name__=='__main__': unittest.main()
