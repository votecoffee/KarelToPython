"""Authored private USING timers, captured identities, lifetime and atomic updates."""
import json
import unittest
from unittest.mock import patch

from karel2py import translate, translate_project, runtime as rt
from karel2py.lexer import TranslationError

U={'uninitialized':True}
TYPES='TYPE row_t=STRUCTURE elapsed:INTEGER other:INTEGER ticks:ARRAY[2] OF INTEGER ENDSTRUCTURE box_t=STRUCTURE child:row_t ENDSTRUCTURE'
DECL='seed:row_t box:box_t calls,result,total,index_value,seen:INTEGER ready:BOOLEAN'
MAKE='ROUTINE make:row_t BEGIN calls=calls+1 RETURN seed END make ROUTINE make_box:box_t BEGIN RETURN box END make_box'


def build(body,*,labelled=False,routines=MAKE,decl=DECL,**options):
    source='PROGRAM MAIN '+TYPES+' VAR '+decl+' '+routines+' BEGIN calls=0 '+('unused:: ' if labelled else '')+body+' END MAIN'
    result=translate(source)
    ns={'__name__':'private_timer_tests'};exec(result.python_source,ns)
    return ns['Program'](**options),result


def execute(body,**options):return build(body,**options)[0].run()


def counter_clock(step=500):
    value={'us':-step}
    def read():
        value['us']+=step
        return value['us']
    return read


class PrivateUsingTimerTests(unittest.TestCase):
    def parity(self,body,**options):
        states=[execute(body,labelled=labelled,clock_us=lambda:0,**options) for labelled in (False,True)]
        self.assertEqual(states[0],states[1]);return states[0]

    def reject(self,body,code='E_FOR_COUNTER',**options):
        with self.assertRaises(TranslationError) as error:build(body,**options)
        self.assertEqual(error.exception.code,code)

    def test_unknown_private_integer_initializes_zero_without_copyback(self):
        v=self.parity('USING make() DO CONNECT TIMER TO elapsed result=elapsed DISCONNECT TIMER elapsed ENDUSING')
        self.assertEqual((v['RESULT'],v['SEED']['ELAPSED'],v['CALLS']),(0,U,1))

    def test_initialized_negative_value_is_preserved_at_connection(self):
        v=self.parity('seed.elapsed=-5 USING make() DO CONNECT TIMER TO elapsed result=elapsed DISCONNECT TIMER elapsed ENDUSING')
        self.assertEqual((v['RESULT'],v['SEED']['ELAPSED']),(-5,-5))

    def test_nested_reference_alias_can_disconnect_same_leaf(self):
        v=self.parity('USING make_box() DO CONNECT TIMER TO child.elapsed USING child DO result=elapsed DISCONNECT TIMER elapsed ENDUSING ENDUSING')
        self.assertEqual((v['RESULT'],v['BOX']['CHILD']['ELAPSED']),(0,U))

    def test_array_leaf_captures_original_index(self):
        v=self.parity('index_value=1 USING make() DO CONNECT TIMER TO ticks[index_value] index_value=2 ticks[2]=99 result=ticks[1] DISCONNECT TIMER ticks[1] ENDUSING')
        self.assertEqual((v['RESULT'],v['INDEX_VALUE'],v['SEED']['TICKS']),(0,2,[U,U]))

    def test_connect_and_disconnect_selector_functions_run_once_each(self):
        routines=MAKE+' ROUTINE pick:INTEGER BEGIN seen=seen+1 RETURN 1 END pick'
        v=self.parity('seen=0 USING make() DO CONNECT TIMER TO ticks[pick()] result=ticks[1] DISCONNECT TIMER ticks[pick()] ENDUSING',routines=routines)
        self.assertEqual((v['SEEN'],v['RESULT']),(2,0))

    def test_independent_copies_can_hold_simultaneous_timers(self):
        p,r=build('USING make() DO CONNECT TIMER TO elapsed USING make() DO CONNECT TIMER TO elapsed PAUSE ENDUSING ENDUSING',clock_us=lambda:0)
        with self.assertRaises(rt.KarelPause):p.run()
        refs=[record[0] for record in p._state._timers.values()]
        self.assertEqual(len(refs),2);self.assertIsNot(refs[0].storage,refs[1].storage)
        self.assertNotEqual(r.report['connected_timers'][0]['protection_root'],r.report['connected_timers'][1]['protection_root'])
        p.stop();self.assertEqual(p._state._timers,{})

    def test_same_leaf_nested_alias_duplicate_is_rejected(self):
        p,_=build('USING make_box() DO CONNECT TIMER TO child.elapsed USING child DO CONNECT TIMER TO elapsed ENDUSING ENDUSING',clock_us=lambda:0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'already connected'):p.run()
        self.assertEqual(p._state._timers,{})

    def test_sibling_integer_leaves_can_be_independent_timers(self):
        v=self.parity('USING make() DO CONNECT TIMER TO elapsed CONNECT TIMER TO other result=elapsed+other DISCONNECT TIMER elapsed DISCONNECT TIMER other ENDUSING')
        self.assertEqual(v['RESULT'],0)

    def test_parameterized_routine_can_create_private_timer(self):
        routines=MAKE+' ROUTINE work(start_value:INTEGER):INTEGER BEGIN USING make() DO elapsed=start_value CONNECT TIMER TO elapsed RETURN elapsed ENDUSING END work'
        self.assertEqual(self.parity('result=work(7)',routines=routines)['RESULT'],7)

    def test_retained_handler_disconnects_timer_after_using_exit(self):
        v=self.parity('USING make() DO elapsed=9 CONNECT TIMER TO elapsed CONDITION[1]: WHEN EVENT[1] DO result=elapsed DISCONNECT TIMER elapsed ENDCONDITION ENDUSING ENABLE CONDITION[1] SIGNAL EVENT[1]')
        self.assertEqual((v['RESULT'],v['SEED']['ELAPSED']),(9,U))

    def test_same_capture_site_reentry_retains_distinct_handler_values(self):
        body='total=0 FOR index_value=1 TO 2 DO USING make() DO elapsed=index_value CONNECT TIMER TO elapsed CONDITION[index_value]: WHEN EVENT[EVAL(index_value)] DO total=total+elapsed DISCONNECT TIMER elapsed ENDCONDITION ENDUSING ENDFOR ENABLE CONDITION[1] ENABLE CONDITION[2] SIGNAL EVENT[1] SIGNAL EVENT[2]'
        self.assertEqual(self.parity(body)['TOTAL'],3)

    def test_retained_timer_survives_source_routine_return(self):
        routines=MAKE+' ROUTINE work BEGIN USING make() DO elapsed=7 CONNECT TIMER TO elapsed CONDITION[1]: WHEN EVENT[1] DO result=elapsed DISCONNECT TIMER elapsed ENDCONDITION ENDUSING END work'
        self.assertEqual(self.parity('work() ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=routines)['RESULT'],7)

    def test_private_timer_drives_checkpoint_handler(self):
        p,_=build('ready=FALSE USING make() DO CONNECT TIMER TO elapsed CONDITION[1]: WHEN elapsed>=5 DO ready=TRUE DISCONNECT TIMER elapsed ENDCONDITION ENABLE CONDITION[1] WHILE NOT ready DO ENDWHILE result=elapsed ENDUSING',clock_us=counter_clock())
        self.assertTrue(p.run()['READY']);self.assertGreaterEqual(p.snapshot()['RESULT'],5)
        self.assertEqual(p._state._timers,{})

    def test_pause_retains_timer_and_applies_elapsed_clock_on_resume(self):
        clock={'us':0};p,_=build('USING make() DO CONNECT TIMER TO elapsed PAUSE result=elapsed DISCONNECT TIMER elapsed ENDUSING',clock_us=lambda:clock['us'])
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(len(p._state._timers),1);clock['us']=7123
        self.assertEqual(p.resume()['RESULT'],7);self.assertEqual(p._state._timers,{})

    def test_stop_releases_paused_timer(self):
        p,_=build('USING make() DO CONNECT TIMER TO elapsed PAUSE ENDUSING',clock_us=lambda:0)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual((p.task_state,p._state._timers),('stopped',{}))

    def test_abort_releases_timers_and_remains_sticky(self):
        p,_=build('USING make() DO CONNECT TIMER TO elapsed ABORT ENDUSING',clock_us=lambda:0)
        for _ in range(2):
            with self.assertRaises(rt.KarelAbort):p.run()
            self.assertEqual(p._state._timers,{})

    def test_runtime_failure_releases_timers_preserving_outside_effects(self):
        p,_=build('result=77 USING make() DO CONNECT TIMER TO elapsed total=1 DIV 0 ENDUSING',clock_us=lambda:0)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['RESULT'],p._state._timers),(77,{}))

    def test_budget_failure_releases_timer(self):
        p,_=build('USING make() DO CONNECT TIMER TO elapsed WHILE TRUE DO ENDWHILE ENDUSING',clock_us=lambda:0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):p.run(max_steps=30)
        self.assertEqual(p._state._timers,{})

    def test_success_without_explicit_disconnect_releases_timer(self):
        p,_=build('USING make() DO CONNECT TIMER TO elapsed result=elapsed ENDUSING',clock_us=lambda:0)
        self.assertEqual(p.run()['RESULT'],0);self.assertEqual(p._state._timers,{})

    def test_declared_global_timer_terminal_cleanup_also_applies(self):
        p,_=build('CONNECT TIMER TO result',clock_us=lambda:0)
        self.assertEqual(p.run()['RESULT'],0);self.assertEqual(p._state._timers,{})

    def test_same_private_root_counter_is_blocked_even_on_sibling(self):
        self.reject('USING make() DO CONNECT TIMER TO elapsed FOR other=1 TO 2 DO ENDFOR ENDUSING')

    def test_lexical_timer_site_after_counter_still_blocks_counter(self):
        self.reject('USING make() DO FOR other=1 TO 2 DO ENDFOR CONNECT TIMER TO elapsed ENDUSING')

    def test_nested_reference_alias_keeps_counter_root_protection(self):
        self.reject('USING make_box() DO CONNECT TIMER TO child.elapsed USING child DO FOR other=1 TO 2 DO ENDFOR ENDUSING ENDUSING')

    def test_separate_private_copy_timer_does_not_block_counter(self):
        v=self.parity('total=0 USING make() DO CONNECT TIMER TO elapsed USING make() DO FOR other=1 TO 2 DO total=total+other ENDFOR ENDUSING DISCONNECT TIMER elapsed ENDUSING')
        self.assertEqual(v['TOTAL'],3)

    def test_source_root_counter_does_not_alias_private_copy(self):
        v=self.parity('total=0 USING make() DO CONNECT TIMER TO elapsed FOR seed.other=1 TO 2 DO total=total+seed.other ENDFOR DISCONNECT TIMER elapsed ENDUSING')
        self.assertEqual((v['TOTAL'],v['SEED']['OTHER']),(3,U))

    def test_declared_local_using_timer_ends_at_routine_return(self):
        p,_=build('work()',routines=MAKE+' ROUTINE work VAR item:row_t BEGIN USING item DO CONNECT TIMER TO elapsed ENDUSING END work')
        p.run();self.assertEqual((p._state._timers,p._state._frame_timers),({},{}))

    def test_declared_formal_storage_stays_blocked(self):
        self.reject('work(result)',code='E_TIMER_SCOPE',routines=MAKE+' ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value END work')

    def test_real_private_leaf_stays_blocked(self):
        self.reject('USING VEC(1,2,3) DO CONNECT TIMER TO x ENDUSING',code='E_TYPE')

    def test_config_turn_domain_stays_blocked(self):
        routines=MAKE+' ROUTINE make_config:CONFIG VAR c:CONFIG BEGIN RETURN c END make_config'
        self.reject('USING make_config() DO CONNECT TIMER TO cfg_turn_no1 ENDUSING',code='E_TYPE',routines=routines)

    def test_private_named_root_is_null_in_reports(self):
        _,r=build('USING make() DO CONNECT TIMER TO elapsed DISCONNECT TIMER elapsed ENDUSING')
        rows=r.report['connected_timers'];self.assertEqual([row['operation'] for row in rows],['CONNECT','DISCONNECT'])
        self.assertTrue(all(row['root'] is None and row['provenance']=='private_temporary' and row['evaluated_once'] for row in rows))
        self.assertEqual(rows[0]['protection_root'],rows[1]['protection_root'])
        self.assertFalse(r.report['connected_timer_policy']['controller_validated']);json.dumps(r.report,allow_nan=False)

    def test_declared_timer_report_keeps_source_name(self):
        _,r=build('CONNECT TIMER TO result DISCONNECT TIMER result')
        row=r.report['connected_timers'][0];self.assertEqual((row['root'],row['provenance']),('RESULT','declared_storage'))

    def test_context_json_excludes_private_capture_and_connections(self):
        p,_=build('USING make() DO elapsed=12 CONNECT TIMER TO elapsed PAUSE ENDUSING',clock_us=lambda:0)
        with self.assertRaises(rt.KarelPause):p.run()
        config=json.loads(json.dumps(p._state.execution.to_config(),allow_nan=False))
        self.assertFalse(any(row['path'].startswith('_') for row in config['variables']))
        self.assertNotIn('timers',config);self.assertNotIn('clock_us',config)
        seed=next(row for row in config['variables'] if row['path']=='SEED')
        self.assertEqual(seed['value']['ELAPSED'],U);p.stop()

    def test_linked_invocation_keeps_private_timer_until_return(self):
        sources={'main':'PROGRAM MAIN VAR result:INTEGER ROUTINE work:INTEGER FROM LIB BEGIN result=work() END MAIN',
            'lib':'PROGRAM LIB TYPE row_t=STRUCTURE elapsed:INTEGER ENDSTRUCTURE VAR seed:row_t ROUTINE make:row_t BEGIN RETURN seed END make ROUTINE work:INTEGER BEGIN USING make() DO CONNECT TIMER TO elapsed DELAY 3 RETURN elapsed ENDUSING END work BEGIN END LIB'}
        instance=translate_project(sources).instantiate()
        with patch('karel2py.runtime.connect_timer',wraps=rt.connect_timer) as connect:
            values=instance.run('MAIN')
        state=connect.call_args.args[0]
        self.assertGreaterEqual(values['MAIN']['values']['RESULT'],3);self.assertEqual(state._timers,{})
        self.assertEqual(instance.programs['LIB'].snapshot()['SEED']['ELAPSED'],U)

    def test_linked_failure_releases_invocation_timers(self):
        sources={'main':'PROGRAM MAIN ROUTINE work FROM LIB BEGIN work() END MAIN',
            'lib':'PROGRAM LIB VAR elapsed,n:INTEGER ROUTINE work BEGIN CONNECT TIMER TO elapsed n=1 DIV 0 END work BEGIN END LIB'}
        instance=translate_project(sources).instantiate()
        with patch('karel2py.runtime.connect_timer',wraps=rt.connect_timer) as connect:
            with self.assertRaises(rt.KarelRuntimeError):instance.run('MAIN')
        self.assertEqual(connect.call_args.args[0]._timers,{})


class TimerAtomicityTests(unittest.TestCase):
    def state(self,clock=lambda:0):
        p,_=build('',clock_us=clock)
        return p._state

    def reference(self,value=rt.UNINITIALIZED):return rt.Reference(('INTEGER',),{'value':value},'value')

    def test_invalid_initial_storage_fails_before_clock_or_registration(self):
        for value in (True,1.5,'2',2147483647,2147483648,rt.UNKNOWN_BYTE):
            with self.subTest(value=value):
                calls=[];state=self.state(lambda:calls.append(1) or 0);ref=self.reference(value)
                with self.assertRaises(rt.KarelRuntimeError):rt.connect_timer(state,ref,9)
                self.assertEqual((calls,state._timers),([],{}));self.assertIs(ref.raw(),value)

    def test_invalid_clock_keeps_unknown_leaf_and_registry_unchanged(self):
        state=self.state(lambda:False);ref=self.reference()
        with self.assertRaises(rt.KarelRuntimeError):rt.connect_timer(state,ref,7)
        self.assertIs(ref.raw(),rt.UNINITIALIZED);self.assertEqual(state._timers,{})

    def test_fractional_milliseconds_are_carried_across_updates(self):
        clock={'us':0};state=self.state(lambda:clock['us']);ref=self.reference()
        rt.connect_timer(state,ref)
        for now in (500,999,1001,1900,2500):clock['us']=now;rt.update_timers(state)
        self.assertEqual(ref.raw(),2);self.assertEqual(next(iter(state._timers.values()))[2],500)

    def test_multi_timer_overflow_keeps_all_values_and_clock_records(self):
        clock={'us':0};state=self.state(lambda:clock['us']);left=self.reference(4);right=self.reference(2147483646)
        rt.connect_timer(state,left);rt.connect_timer(state,right)
        original=[record[1:] for record in state._timers.values()];clock['us']=1000
        with self.assertRaises(rt.KarelRuntimeError):rt.update_timers(state,11)
        self.assertEqual((left.raw(),right.raw()),(4,2147483646))
        self.assertEqual([record[1:] for record in state._timers.values()],original)

    def test_backward_clock_keeps_all_values_unchanged(self):
        clock={'us':1000};state=self.state(lambda:clock['us']);ref=self.reference(4);rt.connect_timer(state,ref)
        clock['us']=999
        with self.assertRaisesRegex(rt.KarelRuntimeError,'backwards'):rt.update_timers(state,12)
        self.assertEqual(ref.raw(),4)

    def test_duplicate_connection_keeps_original_clock_record(self):
        clock={'us':1};state=self.state(lambda:clock['us']);ref=self.reference(5);rt.connect_timer(state,ref)
        old=next(iter(state._timers.values()));clock['us']=9000
        with self.assertRaisesRegex(rt.KarelRuntimeError,'already connected'):rt.connect_timer(state,rt.Reference(('INTEGER',),ref.storage,ref.key))
        self.assertIs(next(iter(state._timers.values())),old);self.assertEqual(old[1:],[1,0]);self.assertEqual(ref.raw(),5)

    def test_disconnect_rejects_foreign_and_readonly_reference_types(self):
        state=self.state();ref=self.reference();rt.connect_timer(state,ref)
        for other in (None,5,rt.ReadOnlyFieldReference(('INTEGER',),ref.storage,ref.key),rt.Reference(('REAL',),ref.storage,ref.key)):
            with self.subTest(other=other),self.assertRaises(rt.KarelRuntimeError):rt.disconnect_timer(state,other,13)
        self.assertEqual(len(state._timers),1)

    def test_disconnect_mismatch_does_not_remove_other_leaf(self):
        state=self.state();ref=self.reference(5);rt.connect_timer(state,ref)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not connected'):rt.disconnect_timer(state,self.reference(5),14)
        self.assertEqual(len(state._timers),1);rt.disconnect_timer(state,ref);self.assertEqual(state._timers,{})


if __name__=='__main__':unittest.main()
