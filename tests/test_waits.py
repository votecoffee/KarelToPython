"""Boolean WAIT polling, cooperative host yields and bounded control flow."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


ROOT=Path(__file__).resolve().parents[1]
DECLARATIONS='flag,done: BOOLEAN n,after,i: INTEGER trace: STRING[32]'
READY='ROUTINE ready_now: BOOLEAN BEGIN n=n+1 RETURN n>=3 END ready_now'


def compile_program(body, *, declarations=DECLARATIONS, types='', routines='', sleep=None, translator=translate, labelled=False, **context):
    source=f'PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n'+('marker::\n' if labelled else '')+body+'\nEND T'
    result=translator(source,filename='waits.kl'); ns={'__name__':'wait_test'}; exec(result.python_source,ns)
    calls=[]
    p=ns['Program'](sleep=calls.append if sleep is None else sleep,**context)
    return p,result,calls


class WaitBehaviorTests(unittest.TestCase):
    def test_true_condition_continues_without_yield(self):
        p,_,calls=compile_program('WAIT FOR TRUE after=7')
        self.assertEqual(p.run()['AFTER'],7); self.assertEqual(calls,[])

    def test_parenthesized_variable_condition(self):
        p,_,calls=compile_program('flag=TRUE WAIT FOR (flag) done=TRUE')
        self.assertTrue(p.run()['DONE']); self.assertEqual(calls,[])

    def test_rechecks_once_per_poll_until_ready(self):
        p,_,calls=compile_program('n=0 WAIT FOR ready_now() after=n',routines=READY)
        state=p.run(); self.assertEqual((state['N'],state['AFTER'],calls),(3,3,[0.,0.]))

    def test_bare_zero_argument_function(self):
        p,_,calls=compile_program('n=0 WAIT FOR ready_now after=n',routines=READY)
        self.assertEqual((p.run()['AFTER'],calls),(3,[0.,0.]))

    def test_constant_false_is_bounded_without_condition_functions(self):
        p,_,calls=compile_program('WAIT FOR FALSE after=9')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'): p.run(max_steps=3)
        self.assertEqual(calls,[0.,0.]); self.assertEqual(p.snapshot()['AFTER'],{'uninitialized':True})

    def test_default_host_sleeper_receives_zero_seconds(self):
        p,_,_=compile_program('n=0 WAIT FOR ready_now()',routines=READY)
        with patch.object(rt.time,'sleep',return_value=None) as sleeper:
            type(p)().run()
        self.assertEqual(sleeper.call_args_list,[unittest.mock.call(0.),unittest.mock.call(0.)])

    def test_yield_follows_false_condition_effects(self):
        observed=[]
        p,_,_=compile_program('n=0 WAIT FOR ready_now() after=n',routines=READY,sleep=lambda seconds: observed.append((seconds,p.snapshot()['N'])))
        self.assertEqual(p.run()['AFTER'],3); self.assertEqual(observed,[(0.,1),(0.,2)])

    def test_short_circuit_skips_unused_function(self):
        p,_,calls=compile_program('n=0 WAIT FOR TRUE OR danger() after=n',routines='ROUTINE danger: BOOLEAN BEGIN n=n+1 RETURN FALSE END danger')
        self.assertEqual(p.run()['AFTER'],0); self.assertEqual(calls,[])

    def test_compound_checks_keep_left_to_right_short_circuit_order(self):
        routines="ROUTINE first: BOOLEAN BEGIN trace=trace+'A' n=n+1 RETURN n>=2 END first ROUTINE second: BOOLEAN BEGIN trace=trace+'B' RETURN TRUE END second"
        p,_,calls=compile_program("trace='' n=0 WAIT FOR first() AND second()",routines=routines)
        self.assertEqual((p.run()['TRACE'],calls),('AAB',[0.]))

    def test_wait_yields_and_delay_calls_remain_distinct(self):
        p,_,calls=compile_program('n=0 WAIT FOR ready_now() DELAY 0 DELAY 1',routines=READY)
        p.run(); self.assertEqual(calls,[0.,0.,.001])

    def test_fields_arrays_and_aliases(self):
        p,_,calls=compile_program('box.ready=TRUE flags[1]=TRUE WAIT FOR box.ready AND flags[1] done=TRUE',
                                 types='TYPE enabled_t=BOOLEAN box_t=STRUCTURE ready: enabled_t ENDSTRUCTURE',
                                 declarations=DECLARATIONS+' box: box_t flags: ARRAY[1] OF enabled_t')
        self.assertTrue(p.run()['DONE']); self.assertEqual(calls,[])

    def test_using_resolves_wait_condition(self):
        p,_,calls=compile_program('box.ready=TRUE USING box DO WAIT FOR ready ENDUSING done=TRUE',
                                 types='TYPE box_t=STRUCTURE ready: BOOLEAN ENDSTRUCTURE',declarations=DECLARATIONS+' box: box_t')
        self.assertTrue(p.run()['DONE']); self.assertEqual(calls,[])


class WaitIntegrationTests(unittest.TestCase):
    def test_labelled_dispatch_wait(self):
        p,result,calls=compile_program('n=0 WAIT FOR ready_now() after=n',routines=READY,labelled=True)
        self.assertEqual((p.run()['AFTER'],calls),(3,[0.,0.]))
        nodes=result.report['control_flow']['program']['nodes']
        self.assertTrue(any(node['statement_kind']=='wait' for node in nodes))

    def test_jump_can_skip_wait(self):
        p,_,calls=compile_program('GOTO finish WAIT FOR FALSE finish:: done=TRUE')
        self.assertTrue(p.run()['DONE']); self.assertEqual(calls,[])

    def test_wait_in_labelled_function_and_operator(self):
        routines='ROUTINE value: INTEGER BEGIN start:: WAIT FOR TRUE RETURN 7 END value'
        p,_,calls=compile_program('after=value()+1',routines=routines)
        self.assertEqual(p.run()['AFTER'],8); self.assertEqual(calls,[])

    def test_for_counter_read_only_argument(self):
        p,_,calls=compile_program('FOR i=1 TO 2 DO check(i) ENDFOR done=TRUE',routines='ROUTINE check(value: INTEGER) BEGIN WAIT FOR (value>0) END check')
        state=p.run(); self.assertTrue(state['DONE']); self.assertEqual(state['I'],{'uninitialized':True}); self.assertEqual(calls,[])

    def test_parameter_boolean_reference(self):
        p,_,calls=compile_program('flag=TRUE await_ready(flag) done=TRUE',routines='ROUTINE await_ready(value: BOOLEAN) BEGIN WAIT FOR value END await_ready')
        self.assertTrue(p.run()['DONE']); self.assertEqual(calls,[])

    def test_typed_read_function_supplies_changing_condition(self):
        responses=iter([[False],[False],[True]])
        p,_,calls=compile_program('n=0 WAIT FOR receive() after=n',
                                 routines='ROUTINE receive: BOOLEAN BEGIN READ(flag) n=n+1 RETURN flag END receive',read=lambda request:next(responses))
        state=p.run(); self.assertEqual((state['AFTER'],state['FLAG'],calls),(3,True,[0.,0.]))
        self.assertEqual(len(p.read_requests),3)

    def test_nested_callback_program_keeps_separate_frames_and_budget(self):
        inner,_,inner_calls=compile_program('n=0 WAIT FOR ready_now()',routines=READY)
        observed=[]
        outer,_,_=compile_program('n=0 WAIT FOR ready_now() after=n',routines=READY,sleep=lambda seconds:observed.append(inner.run()['N']))
        self.assertEqual(outer.run()['AFTER'],3); self.assertEqual(observed,[3,3]); self.assertEqual(inner_calls,[0.,0.,0.,0.])

    def test_routine_wait_effects_propagate_even_on_skipped_paths(self):
        _,result,_=compile_program('outer()',routines='ROUTINE inner BEGIN IF FALSE THEN WAIT FOR TRUE ENDIF END inner ROUTINE outer BEGIN inner END outer')
        for name in ('INNER','OUTER'): self.assertTrue(result.report['routine_effects'][name]['potential_host_delays'])
        self.assertEqual(result.report['waits'][0]['body'],'INNER')

    def test_report_has_one_entry_per_source_wait_and_source_map(self):
        _,result,_=compile_program('n=0 WAIT FOR ready_now() WAIT FOR TRUE',routines=READY)
        rows=result.report['waits']; self.assertEqual(len(rows),2)
        self.assertEqual([row['condition_kind'] for row in rows],['call','literal'])
        self.assertTrue(all(row['body']=='T' and row['line']==6 and row['column']>0 and row['step_budgeted'] for row in rows))
        self.assertTrue(all(row['line'] in [entry['karel_line'] for entry in result.report['source_map']] for row in rows))
        self.assertFalse(result.report['wait_policy']['controller_validated']); json.dumps(result.report)

    def test_continued_wait_keeps_physical_source_location(self):
        p,result,calls=compile_program('WAIT &\n FOR TRUE done=TRUE')
        self.assertTrue(p.run()['DONE']); self.assertEqual(calls,[]); self.assertEqual(result.report['waits'][0]['line'],6)


class WaitFailureTests(unittest.TestCase):
    def test_unknown_condition_fails_before_yield_or_later_statements(self):
        p,_,calls=compile_program('WAIT FOR flag after=7')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(calls,[]); self.assertEqual(p.snapshot()['AFTER'],{'uninitialized':True})

    def test_forged_nonboolean_condition_is_rejected(self):
        p,_,calls=compile_program('WAIT FOR flag'); p._state.values['FLAG']=1
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(calls,[])

    def test_condition_failure_retains_earlier_effects(self):
        p,_,calls=compile_program('n=0 WAIT FOR fail() after=7',routines='ROUTINE fail: BOOLEAN BEGIN n=n+1 RETURN (1 DIV 0)=0 END fail')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['N'],calls),(1,[]))

    def test_bad_sleeper_result_stops_before_next_condition(self):
        for value in (False,0,[],object()):
            p,_,_=compile_program('n=0 WAIT FOR ready_now()',routines=READY,sleep=lambda seconds:value)
            with self.subTest(value=value),self.assertRaisesRegex(rt.KarelRuntimeError,'must return None'): p.run()
            self.assertEqual(p.snapshot()['N'],1)

    def test_callback_exception_is_source_located_without_retry(self):
        calls=[]; failure=ValueError('offline sleeper failed')
        def sleeper(seconds): calls.append(seconds); raise failure
        p,_,_=compile_program('WAIT FOR FALSE',sleep=sleeper)
        with self.assertRaises(rt.KarelRuntimeError) as caught: p.run()
        self.assertEqual(caught.exception.line,6); self.assertIs(caught.exception.__cause__,failure); self.assertEqual(calls,[0.])

    def test_budget_failure_unwinds_routines_and_clears_counter(self):
        p,_,calls=compile_program('FOR i=1 TO 2 DO await_ready ENDFOR',routines='ROUTINE await_ready BEGIN WAIT FOR FALSE END await_ready')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'): p.run(max_steps=15)
        self.assertGreater(len(calls),0); self.assertEqual((p._state.local_frames,p._state.call_depth,p.snapshot()['I']),([],0,{'uninitialized':True}))

    def test_sleeper_failure_unwinds_routines_and_counter(self):
        def sleeper(seconds): raise ValueError('failed')
        p,_,_=compile_program('FOR i=1 TO 2 DO await_ready ENDFOR',routines='ROUTINE await_ready BEGIN WAIT FOR FALSE END await_ready',sleep=sleeper)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p._state.local_frames,p._state.call_depth,p.snapshot()['I']),([],0,{'uninitialized':True}))

    def test_base_exception_propagates_with_cleanup(self):
        def sleeper(seconds): raise KeyboardInterrupt()
        p,_,_=compile_program('FOR i=1 TO 2 DO await_ready ENDFOR',routines='ROUTINE await_ready BEGIN WAIT FOR FALSE END await_ready',sleep=sleeper)
        with self.assertRaises(KeyboardInterrupt): p.run()
        self.assertEqual((p._state.local_frames,p._state.call_depth,p.snapshot()['I']),([],0,{'uninitialized':True}))

    def test_condition_abort_remains_sticky_and_cleans_frames(self):
        p,_,calls=compile_program('FOR i=1 TO 2 DO WAIT FOR stop_now() ENDFOR',routines='ROUTINE stop_now: BOOLEAN BEGIN ABORT RETURN TRUE END stop_now')
        with self.assertRaises(rt.KarelAbort): p.run()
        self.assertEqual(calls,[]); self.assertIsNotNone(p.abort_info)
        self.assertEqual((p._state.local_frames,p._state.call_depth,p.snapshot()['I']),([],0,{'uninitialized':True}))
        with self.assertRaises(rt.KarelAbort): p.run()

    def test_callback_abort_is_not_wrapped_or_followed_by_another_check(self):
        def sleeper(seconds): p._state.abort(91)
        p,_,_=compile_program('n=0 WAIT FOR ready_now()',routines=READY,sleep=sleeper)
        with self.assertRaises(rt.KarelAbort) as caught: p.run()
        self.assertEqual(caught.exception.line,91); self.assertEqual(p.snapshot()['N'],1)

    def test_callback_cannot_hide_sticky_abort_by_catching_it(self):
        def sleeper(seconds):
            try: p._state.abort(92)
            except rt.KarelAbort: pass
        p,_,_=compile_program('n=0 WAIT FOR ready_now()',routines=READY,sleep=sleeper)
        with self.assertRaises(rt.KarelAbort) as caught: p.run()
        self.assertEqual(caught.exception.line,92); self.assertEqual(p.snapshot()['N'],1)


class WaitGuardTests(unittest.TestCase):
    def test_nonboolean_source_conditions_rejected(self):
        for value in ('1','0.1',"'ready'",'VEC(1,2,3)'):
            with self.subTest(value=value),self.assertRaises(TranslationError) as caught: compile_program('WAIT FOR '+value)
            self.assertEqual(caught.exception.code,'E_TYPE')

    def test_missing_for_and_condition_rejected(self):
        for body in ('WAIT TRUE','WAIT FOR','WAIT FOR ()'):
            with self.subTest(body=body),self.assertRaises(TranslationError): compile_program(body)

    def test_native_events_devices_and_handler_forms_stay_blocked(self):
        for body in ('WAIT FOR DIN[1]','WAIT FOR STOP','WAIT FOR TIME 10','WAIT FOR TRUE,TRUE',
                     'CONDITION[1]: WHEN TRUE DO WAIT FOR TRUE ENDCONDITION'):
            with self.subTest(body=body),self.assertRaises(TranslationError): compile_program(body)

    def test_transitive_counter_writes_inside_wait_condition_rejected(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('FOR i=1 TO 2 DO WAIT FOR change() ENDFOR',routines='ROUTINE change: BOOLEAN BEGIN i=9 RETURN TRUE END change')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_legacy_internal_wait_rejection_retained(self):
        with self.assertRaises(TranslationError) as caught: compile_program('WAIT FOR TRUE',translator=legacy_translate)
        self.assertEqual(caught.exception.code,'E_UNSUPPORTED')
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): rt.State({},{}).wait_poll()


class AuthoredWaitTests(unittest.TestCase):
    def test_complete_fixture_output_yields_and_reports(self):
        source=ROOT/'examples/pythonic_wait.kl'; result=translate(source.read_text(),filename=source.name)
        ns={'__name__':'wait_fixture'}; exec(result.python_source,ns); out=[]; yields=[]
        p=ns['Program'](write=out.append,sleep=yields.append)
        self.assertEqual(p.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(out,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual(yields,json.loads(source.with_suffix('.sleep.expected.json').read_text()))
        self.assertEqual([(row['body'],row['line']) for row in result.report['waits']],[('PYTHONIC_WAIT',13),('PYTHONIC_WAIT',15)])
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
