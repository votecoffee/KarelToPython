"""Host microsecond counters, rollover arithmetic, clock ownership and source effects."""
import json
from pathlib import Path
import random
import unittest
from unittest.mock import patch

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


ROOT=Path(__file__).resolve().parents[1]
DECLARATIONS='first,last,elapsed,total,i: INTEGER flag: BOOLEAN trace: STRING[20]'


def compile_program(body, *, declarations=DECLARATIONS, prefix='', routines='', translator=translate, labelled=False, **context):
    source=f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n'+('label::\n' if labelled else '')+body+'\nEND T'
    result=translator(source,filename='microseconds.kl'); namespace={'__name__':'microsecond_test'}
    exec(result.python_source,namespace)
    return namespace['Program'](**context),result


def sampled(body, values, **options):
    samples=iter(values)
    return compile_program(body,clock_us=lambda:next(samples),**options)


class MicrosecondBehaviorTests(unittest.TestCase):
    def test_bare_and_explicit_calls(self):
        p,_=sampled('first=GET_USEC_TIM last=GET_USEC_TIM() elapsed=GET_USEC_SUB(last,first)',(100,145))
        self.assertEqual((p.run()['FIRST'],p.snapshot()['LAST'],p.snapshot()['ELAPSED']),(100,145,45))
    def test_counter_rollover(self):
        p,_=sampled('first=GET_USEC_TIM last=GET_USEC_TIM elapsed=GET_USEC_SUB(last,first)',(119999990,120000025))
        self.assertEqual((p.run()['FIRST'],p.snapshot()['LAST'],p.snapshot()['ELAPSED']),(119999990,25,35))
    def test_zero_equal_and_ring_edges(self):
        for later,earlier,delta in ((0,0,0),(1,0,1),(0,119999999,1),(119999999,0,119999999),(42,42,0)):
            p,_=compile_program(f'elapsed=GET_USEC_SUB({later},{earlier})')
            with self.subTest(later=later,earlier=earlier): self.assertEqual(p.run()['ELAPSED'],delta)
    def test_known_elapsed_intervals_on_random_origins(self):
        rng=random.Random(7701)
        with rt._numeric_scope('pythonic'):
            for _ in range(200):
                origin=rng.randrange(0,10**12); delta=rng.randrange(0,120000000)
                self.assertEqual(rt.usec_sub((origin+delta)%120000000,origin%120000000),delta)
    def test_unbounded_nonnegative_host_samples(self):
        p,_=sampled('first=GET_USEC_TIM last=GET_USEC_TIM',(0,10**100+123))
        self.assertEqual((p.run()['FIRST'],p.snapshot()['LAST']),(0,(10**100+123)%120000000))
    def test_default_clock_floors_nanoseconds(self):
        p,_=compile_program('first=GET_USEC_TIM last=GET_USEC_TIM')
        with patch.object(rt.time,'monotonic_ns',side_effect=(123456789,120000000999)) as clock:
            self.assertEqual((p.run()['FIRST'],p.snapshot()['LAST']),(123456,0))
        self.assertEqual(clock.call_count,2); self.assertTrue(all(row['adapter']=='monotonic' for row in p.clock_reads))
    def test_no_eager_clock_sampling(self):
        with patch.object(rt.time,'monotonic_ns',side_effect=AssertionError('unexpected sample')):
            p,_=compile_program('first=1'); self.assertEqual(p.run()['FIRST'],1)
        self.assertEqual(p.clock_reads,())
    def test_subtraction_never_samples_clock(self):
        p,_=compile_program('elapsed=GET_USEC_SUB(10,3)',clock_us=lambda: (_ for _ in ()).throw(AssertionError('unexpected sample')))
        self.assertEqual(p.run()['ELAPSED'],7); self.assertEqual(p.clock_reads,())
    def test_short_circuit_skips_clock(self):
        p,_=sampled('flag=FALSE AND (GET_USEC_TIM>0) flag=TRUE OR (GET_USEC_TIM>0)',())
        self.assertTrue(p.run()['FLAG']); self.assertEqual(p.clock_reads,())
    def test_nested_clock_arguments_in_source_order(self):
        p,_=sampled('elapsed=GET_USEC_SUB(GET_USEC_TIM,GET_USEC_TIM)',(35,10))
        self.assertEqual(p.run()['ELAPSED'],25); self.assertEqual([r['counter'] for r in p.clock_reads],[35,10])
    def test_function_arguments_once_left_to_right(self):
        routines="ROUTINE later: INTEGER BEGIN trace=trace+'L' RETURN 35 END later\nROUTINE earlier: INTEGER BEGIN trace=trace+'E' RETURN 10 END earlier"
        p,_=compile_program("trace='' elapsed=GET_USEC_SUB(later,earlier)",routines=routines)
        self.assertEqual((p.run()['ELAPSED'],p.snapshot()['TRACE']),(25,'LE'))
    def test_clock_reads_in_write(self):
        output=[]; p,_=sampled('WRITE(GET_USEC_SUB(GET_USEC_TIM,GET_USEC_TIM)::0,CR)',(35,10),write=output.append)
        p.run(); self.assertEqual(output,[' 25\n']); self.assertEqual(len(p.clock_reads),2)
    def test_for_bounds_sample_once(self):
        p,_=sampled('total=0 FOR i=GET_USEC_TIM TO GET_USEC_TIM DO total=total+i ENDFOR',(1,3))
        self.assertEqual(p.run()['TOTAL'],6); self.assertEqual(len(p.clock_reads),2)
    def test_wait_condition_rechecks_clock_with_budget(self):
        yields=[]; p,_=sampled('WAIT FOR GET_USEC_TIM>=3 total=7',(1,2,3),sleep=yields.append)
        self.assertEqual(p.run()['TOTAL'],7); self.assertEqual(yields,[0.,0.]); self.assertEqual(len(p.clock_reads),3)
    def test_labelled_flow(self):
        p,_=sampled('first=GET_USEC_TIM',(8,),labelled=True); self.assertEqual(p.run()['FIRST'],8)
    def test_narrow_inputs_promote(self):
        p,_=compile_program('values[1]=12 values[2]=2 elapsed=GET_USEC_SUB(values[1],values[2])',declarations=DECLARATIONS+' values: ARRAY[2] OF BYTE')
        self.assertEqual(p.run()['ELAPSED'],10)


class MicrosecondOwnershipTests(unittest.TestCase):
    def test_observations_defensive_and_source_located(self):
        p,result=sampled('first=GET_USEC_TIM\nlast=GET_USEC_TIM()',(12,15)); p.run()
        self.assertEqual(p.clock_reads,({'line':6,'adapter':'injected','adapter_outcome':'completed','counter':12},{'line':7,'adapter':'injected','adapter_outcome':'completed','counter':15}))
        observed=p.clock_reads; observed[0]['counter']=99; self.assertEqual(p.clock_reads[0]['counter'],12)
        self.assertFalse(result.report['microsecond_timer_policy']['controller_validated']); json.dumps(result.report)
    def test_observations_reset_on_new_run(self):
        p,_=sampled('first=GET_USEC_TIM',(12,15)); p.run(); p.run()
        self.assertEqual([r['counter'] for r in p.clock_reads],[15])
    def test_injected_clock_is_not_reset_at_run_start(self):
        p,_=sampled('first=GET_USEC_TIM',(1,2)); self.assertEqual(p.run()['FIRST'],1); self.assertEqual(p.run()['FIRST'],2)
    def test_nested_programs_keep_clocks_independent(self):
        inner,_=sampled('first=GET_USEC_TIM',(7,)); outer,_=compile_program('first=GET_USEC_TIM',clock_us=lambda:inner.run()['FIRST']+1)
        self.assertEqual(outer.run()['FIRST'],8); self.assertEqual(inner.clock_reads[0]['counter'],7); self.assertEqual(outer.clock_reads[0]['counter'],8)
    def test_direct_and_transitive_clock_effect_reports(self):
        p,result=sampled('first=outer()',(9,),routines='ROUTINE inner: INTEGER BEGIN RETURN GET_USEC_TIM END inner\nROUTINE outer: INTEGER BEGIN RETURN inner END outer')
        self.assertEqual(p.run()['FIRST'],9)
        for name in ('INNER','OUTER'): self.assertTrue(result.report['routine_effects'][name]['potential_host_clock_reads'])
        self.assertEqual(result.report['microsecond_timers'][0]['body'],'INNER')
    def test_subtraction_is_not_a_clock_read_effect(self):
        _,result=compile_program('first=delta()',routines='ROUTINE delta: INTEGER BEGIN RETURN GET_USEC_SUB(8,1) END delta')
        self.assertFalse(result.report['routine_effects']['DELTA']['potential_host_clock_reads'])
    def test_reports_one_source_site_per_function(self):
        _,result=sampled('first=GET_USEC_TIM\nelapsed=GET_USEC_SUB(10,first)',(2,))
        rows=result.report['microsecond_timers']
        self.assertEqual([(r['function'],r['line'],r['column'],r['host_clock_read']) for r in rows],[('GET_USEC_TIM',6,7,True),('GET_USEC_SUB',7,9,False)])
        self.assertEqual(rows[1]['argument_order'],['later','earlier']); self.assertTrue(all(r['arguments_evaluated_once'] for r in rows))
    def test_using_field_shadows_bare_clock_name(self):
        p,_=sampled('box.GET_USEC_TIM=17 USING box DO first=GET_USEC_TIM ENDUSING',(),prefix='TYPE record_t=STRUCTURE GET_USEC_TIM: INTEGER ENDSTRUCTURE',declarations=DECLARATIONS+' box: record_t')
        self.assertEqual(p.run()['FIRST'],17); self.assertEqual(p.clock_reads,())
    def test_global_and_local_storage_shadow_bare_name(self):
        p,_=sampled('GET_USEC_TIM=17 first=GET_USEC_TIM last=value()',(),declarations=DECLARATIONS+' GET_USEC_TIM: INTEGER',routines='ROUTINE value: INTEGER VAR GET_USEC_TIM: INTEGER BEGIN GET_USEC_TIM=23 RETURN GET_USEC_TIM END value')
        self.assertEqual((p.run()['FIRST'],p.snapshot()['LAST']),(17,23)); self.assertEqual(p.clock_reads,())
    def test_constants_shadow_bare_clock_name(self):
        p,_=sampled('first=GET_USEC_TIM',(),prefix='CONST GET_USEC_TIM=17')
        self.assertEqual(p.run()['FIRST'],17); self.assertEqual(p.clock_reads,())
        p,_=sampled('last=value()',(),routines='ROUTINE value: INTEGER CONST GET_USEC_TIM=23 BEGIN RETURN GET_USEC_TIM END value')
        self.assertEqual(p.run()['LAST'],23); self.assertEqual(p.clock_reads,())
    def test_user_functions_keep_precedence_and_signatures(self):
        p,result=sampled('first=GET_USEC_TIM(4) last=GET_USEC_SUB(5)',(),routines='ROUTINE GET_USEC_TIM(n: INTEGER): INTEGER BEGIN RETURN n+1 END GET_USEC_TIM\nROUTINE GET_USEC_SUB(n: INTEGER): INTEGER BEGIN RETURN n+2 END GET_USEC_SUB')
        self.assertEqual((p.run()['FIRST'],p.snapshot()['LAST']),(5,7)); self.assertEqual(result.report['microsecond_timers'],[])
    def test_user_procedure_keeps_precedence(self):
        p,result=sampled('GET_USEC_TIM(4)',(),routines='ROUTINE GET_USEC_TIM(n: INTEGER) BEGIN first=n END GET_USEC_TIM')
        self.assertEqual(p.run()['FIRST'],4); self.assertEqual(result.report['microsecond_timers'],[])


class MicrosecondFailureTests(unittest.TestCase):
    def test_invalid_counter_inputs_preserve_pending_assignment(self):
        for expression in ('GET_USEC_SUB(-1,0)','GET_USEC_SUB(0,120000000)','GET_USEC_SUB(2147483647,0)'):
            p,_=compile_program('elapsed=42 elapsed='+expression)
            with self.subTest(expression=expression),self.assertRaisesRegex(rt.KarelRuntimeError,'counter'): p.run()
            self.assertEqual(p.snapshot()['ELAPSED'],42)
    def test_uninitialized_first_argument_skips_second_clock_read(self):
        p,_=sampled('elapsed=42 elapsed=GET_USEC_SUB(first,GET_USEC_TIM)',())
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.clock_reads,()); self.assertEqual(p.snapshot()['ELAPSED'],42)
    def test_invalid_first_counter_is_checked_after_both_argument_captures(self):
        p,_=sampled('elapsed=GET_USEC_SUB(-1,GET_USEC_TIM)',(8,))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.clock_reads[0]['counter'],8)
    def test_bad_callback_values_preserve_target_and_record_failure(self):
        for value in (True,False,1.5,-1,None,[],{}):
            p,_=sampled('first=42 first=GET_USEC_TIM',(value,))
            with self.subTest(value=value),self.assertRaisesRegex(rt.KarelRuntimeError,'nonnegative integer'): p.run()
            self.assertEqual(p.snapshot()['FIRST'],42); self.assertEqual(p.clock_reads[0]['adapter_outcome'],'invalid_response'); self.assertNotIn('counter',p.clock_reads[0])
    def test_async_clock_response_is_closed_and_rejected(self):
        async def clock(): return 1
        p,_=compile_program('first=GET_USEC_TIM',clock_us=clock)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'synchronously'): p.run()
        self.assertEqual(p.clock_reads[0]['adapter_outcome'],'invalid_response')
    def test_generator_clock_response_is_rejected(self):
        def clock(): yield 1
        p,_=compile_program('first=GET_USEC_TIM',clock_us=clock)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'synchronously'): p.run()
    def test_callback_error_has_cause_and_source_line(self):
        failure=ValueError('clock unavailable')
        def clock(): raise failure
        p,_=compile_program('first=42\nfirst=GET_USEC_TIM',clock_us=clock)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'line 7') as caught: p.run()
        self.assertIs(caught.exception.__cause__,failure); self.assertEqual(p.snapshot()['FIRST'],42); self.assertEqual(p.clock_reads[0]['adapter_outcome'],'clock_failed')
    def test_failure_unwinds_for_and_routine_frames(self):
        p,_=sampled('FOR i=1 TO 2 DO first=value() ENDFOR',(None,),routines='ROUTINE value: INTEGER BEGIN RETURN GET_USEC_TIM END value')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['I'],{'uninitialized':True}); self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
    def test_sticky_abort_swallowed_by_callback_still_wins(self):
        def clock():
            try: p._state.abort(99)
            except rt.KarelAbort: pass
            return 7
        p,_=compile_program('first=42 first=GET_USEC_TIM',clock_us=clock)
        with self.assertRaises(rt.KarelAbort): p.run()
        self.assertEqual(p.snapshot()['FIRST'],42); self.assertEqual(p.clock_reads[0]['adapter_outcome'],'aborted')
        with self.assertRaises(rt.KarelAbort): p.run()
        self.assertEqual(len(p.clock_reads),1)
    def test_callback_failure_after_abort_keeps_abort(self):
        def clock():
            try: p._state.abort(99)
            except rt.KarelAbort: raise ValueError('secondary')
        p,_=compile_program('first=GET_USEC_TIM',clock_us=clock)
        with self.assertRaises(rt.KarelAbort): p.run()
        self.assertEqual(p.clock_reads[0]['adapter_outcome'],'aborted')
    def test_constant_clock_wait_has_step_budget(self):
        p,_=compile_program('WAIT FOR GET_USEC_TIM>0',clock_us=lambda:0,sleep=lambda seconds:None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'): p.run(max_steps=4)
        self.assertEqual(len(p.clock_reads),4)
    def test_noncallable_clock_rejected(self):
        with self.assertRaisesRegex(TypeError,'clock_us'): compile_program('first=1',clock_us=17)
    def test_strict_runtime_guards(self):
        state=rt.State({}, {},clock_us=lambda:7)
        with rt._numeric_scope('strict'):
            with self.assertRaises(rt.KarelRuntimeError): state.microsecond_time(6)
            with self.assertRaises(rt.KarelRuntimeError): rt.usec_sub(7,1,6)
        self.assertEqual(state.clock_reads,[])
    def test_forged_runtime_counter_types_rejected(self):
        with rt._numeric_scope('pythonic'):
            for value in (True,1.0,rt.UNINITIALIZED,2**31):
                with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError): rt.usec_sub(value,0)


class MicrosecondSourceGuardTests(unittest.TestCase):
    def reject(self,body,code,**options):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**options)
        self.assertEqual(caught.exception.code,code)
    def test_argument_counts(self):
        for body in ('first=GET_USEC_TIM(1)','elapsed=GET_USEC_SUB(1)','elapsed=GET_USEC_SUB(1,2,3)'):
            with self.subTest(body=body): self.reject(body,'E_ARGUMENTS')
    def test_subtraction_input_types(self):
        for expression in ("GET_USEC_SUB('bad',1)",'GET_USEC_SUB(1,TRUE)','GET_USEC_SUB(1.5,0)'):
            with self.subTest(expression=expression): self.reject('elapsed='+expression,'E_TYPE')
    def test_active_for_counter_writes_through_user_override_remain_blocked(self):
        self.reject('FOR i=1 TO 2 DO first=GET_USEC_TIM() ENDFOR','E_FOR_COUNTER',routines='ROUTINE GET_USEC_TIM: INTEGER BEGIN i=9 RETURN 0 END GET_USEC_TIM')
    def test_clock_names_are_not_constant_expressions(self): self.reject('first=1','E_CONSTANT',prefix='CONST n=GET_USEC_TIM')
    def test_legacy_calls_remain_unsupported(self):
        for body in ('first=GET_USEC_TIM()','elapsed=GET_USEC_SUB(1,0)'):
            with self.subTest(body=body): self.reject(body,'E_CALL',translator=legacy_translate)


class AuthoredMicrosecondTests(unittest.TestCase):
    def test_complete_fixture(self):
        source=ROOT/'examples/pythonic_microseconds.kl'; result=translate(source.read_text(),filename=source.name)
        namespace={'__name__':'authored_microseconds'}; exec(result.python_source,namespace)
        output=[]; p=namespace['Program'](write=output.append)
        self.assertEqual(p.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(output,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual(p.clock_reads,()); self.assertEqual(len(result.report['microsecond_timers']),2)
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
