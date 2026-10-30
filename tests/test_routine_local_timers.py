"""Authored routine-local timers with captured leaves and checked frame lifetime."""
import json
import unittest
from unittest.mock import patch
from karel2py import translate_project,runtime as rt
from karel2py.diagnostics import DiagnosticLog
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_private_using_timers import counter_clock
from tests.test_project_scheduler import source

U={'uninitialized':True}
TYPES='TYPE row_t=STRUCTURE elapsed:INTEGER other:INTEGER ticks:ARRAY[2]OF INTEGER ENDSTRUCTURE'
DECL='n,result,total,seen:INTEGER ready,done:BOOLEAN'


def build(body='work()',routines='ROUTINE work VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed result=elapsed END work',*,labelled=False,**options):
    return compile_program(('unused:: ' if labelled else '')+body,prefix=TYPES,decl=DECL,routines=routines,**options)


def execute(body='work()',routines='ROUTINE work VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed result=elapsed END work',**options):
    return build(body,routines,**options)[0].run()


def empty_timers(program):
    return program._state._timers,program._state._frame_timers,program._state._timer_frames


class LocalTimerSourceTests(unittest.TestCase):
    def parity(self,body='work()',routines='ROUTINE work VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed result=elapsed END work'):
        states=[execute(body,routines,labelled=labelled,clock_us=lambda:0) for labelled in (False,True)]
        self.assertEqual(states[0],states[1]);return states[0]

    def test_uninitialized_local_scalar_starts_zero(self):
        self.assertEqual(self.parity()['RESULT'],0)

    def test_initialized_negative_local_value_is_preserved(self):
        self.assertEqual(self.parity(routines='ROUTINE work VAR elapsed:INTEGER BEGIN elapsed=-7 CONNECT TIMER TO elapsed result=elapsed END work')['RESULT'],-7)

    def test_local_record_field_uses_fresh_storage(self):
        self.assertEqual(self.parity(routines='ROUTINE work VAR item:row_t BEGIN item.other=9 CONNECT TIMER TO item.elapsed result=item.elapsed+item.other END work')['RESULT'],9)

    def test_local_array_leaf_retains_original_index(self):
        routines='ROUTINE work VAR ticks:ARRAY[2]OF INTEGER slot:INTEGER BEGIN slot=1 CONNECT TIMER TO ticks[slot] slot=2 ticks[2]=9 result=ticks[1] DISCONNECT TIMER ticks[1] END work'
        self.assertEqual(self.parity(routines=routines)['RESULT'],0)

    def test_nested_named_using_captures_local_timer_leaf(self):
        routines='ROUTINE work VAR item:row_t BEGIN USING (item) DO CONNECT TIMER TO ticks[1] result=ticks[1] DISCONNECT TIMER ticks[1] ENDUSING END work'
        self.assertEqual(self.parity(routines=routines)['RESULT'],0)

    def test_selector_function_runs_once_for_each_source_statement(self):
        routines='ROUTINE pick:INTEGER BEGIN seen=seen+1 RETURN 1 END pick ROUTINE work VAR ticks:ARRAY[2]OF INTEGER BEGIN CONNECT TIMER TO ticks[pick()] DISCONNECT TIMER ticks[pick()] END work'
        self.assertEqual(self.parity('seen=0 work()',routines)['SEEN'],2)

    def test_local_type_alias_to_integer_is_supported(self):
        p,_=compile_program('result=work()',prefix='TYPE clock_t=INTEGER',decl='result:INTEGER',routines='ROUTINE work:INTEGER VAR elapsed:clock_t BEGIN CONNECT TIMER TO elapsed RETURN elapsed END work',clock_us=lambda:0)
        self.assertEqual(p.run()['RESULT'],0)

    def test_normal_return_releases_undisconnected_local_timers(self):
        p,_=build(clock_us=lambda:0);p.run();self.assertEqual(empty_timers(p),({},{},[]))

    def test_early_return_captures_value_before_unwind(self):
        p,_=build('result=work()',routines='ROUTINE work:INTEGER VAR elapsed:INTEGER BEGIN elapsed=9 CONNECT TIMER TO elapsed RETURN elapsed END work',clock_us=lambda:0)
        self.assertEqual(p.run()['RESULT'],9);self.assertEqual(empty_timers(p),({},{},[]))

    def test_return_through_label_dispatcher_releases_local_timer(self):
        routine='ROUTINE work:INTEGER VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed GOTO finish finish:: RETURN elapsed END work'
        p,_=build('result=work()',routine,clock_us=lambda:0)
        self.assertEqual(p.run()['RESULT'],0);self.assertEqual(empty_timers(p),({},{},[]))

    def test_duplicate_connection_of_same_local_leaf_fails(self):
        p,_=build(routines='ROUTINE work VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed CONNECT TIMER TO elapsed END work',clock_us=lambda:0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'already connected'):p.run()
        self.assertEqual(empty_timers(p),({},{},[]))

    def test_explicit_disconnect_then_reconnect_uses_new_record(self):
        routine='ROUTINE work VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed DISCONNECT TIMER elapsed elapsed=7 CONNECT TIMER TO elapsed result=elapsed END work'
        self.assertEqual(self.parity(routines=routine)['RESULT'],7)

    def test_loop_test_polls_local_timer_and_handler(self):
        routine='ROUTINE work VAR elapsed:INTEGER BEGIN ready=FALSE CONNECT TIMER TO elapsed CONDITION[1]: WHEN elapsed>=5 DO ready=TRUE ENDCONDITION ENABLE CONDITION[1] WHILE NOT ready DO ENDWHILE result=elapsed END work'
        p,_=build(routines=routine,clock_us=counter_clock());self.assertTrue(p.run()['READY']);self.assertGreaterEqual(p.snapshot()['RESULT'],5)
        self.assertEqual(empty_timers(p),({},{},[]))

    def test_retained_handler_can_read_frozen_value_after_routine_exit(self):
        routine='ROUTINE work VAR elapsed:INTEGER BEGIN elapsed=7 CONNECT TIMER TO elapsed CONDITION[1]: WHEN EVENT[1] DO result=elapsed ENDCONDITION END work'
        self.assertEqual(self.parity('work() ENABLE CONDITION[1] SIGNAL EVENT[1]',routine)['RESULT'],7)

    def test_retained_local_value_stays_frozen_when_clock_advances_after_return(self):
        clock={'us':0};routine='ROUTINE work VAR elapsed:INTEGER BEGIN elapsed=7 CONNECT TIMER TO elapsed CONDITION[1]: WHEN EVENT[1] DO result=elapsed ENDCONDITION END work'
        p,_=build('work() PAUSE ENABLE CONDITION[1] SIGNAL EVENT[1]',routine,clock_us=lambda:clock['us'])
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p._state._timers,{});clock['us']=99999
        self.assertEqual(p.resume()['RESULT'],7)

    def test_local_handler_policy_purges_handler_and_timer_independently(self):
        routine='ROUTINE work VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed CONDITION[1]: WHEN EVENT[1] DO result=elapsed ENDCONDITION END work'
        p,_=build('work() ENABLE CONDITION[1] SIGNAL EVENT[1]',routine,clock_us=lambda:0,context=rt.ExecutionContext(local_handlers=True))
        self.assertEqual(p.run()['RESULT'],U);self.assertEqual((p._state._handlers,empty_timers(p)),({},({}, {}, [])))

    def test_retained_handler_cannot_restart_timer_on_dead_frame(self):
        routine='ROUTINE work VAR elapsed:INTEGER BEGIN CONDITION[1]: WHEN EVENT[1] DO CONNECT TIMER TO elapsed ENDCONDITION END work'
        p,_=build('work() ENABLE CONDITION[1] SIGNAL EVENT[1]',routine,clock_us=lambda:0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'active routine frame'):p.run()
        self.assertEqual(empty_timers(p),({},{},[]))

    def test_retained_handler_cannot_disconnect_dead_frame(self):
        routine='ROUTINE work VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed CONDITION[1]: WHEN EVENT[1] DO DISCONNECT TIMER elapsed ENDCONDITION END work'
        p,_=build('work() ENABLE CONDITION[1] SIGNAL EVENT[1]',routine,clock_us=lambda:0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'active routine frame'):p.run()

    def test_live_outer_handler_uses_its_captured_frame_during_inner_call(self):
        routines='ROUTINE inner BEGIN SIGNAL EVENT[1] END inner ROUTINE work VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed CONDITION[1]: WHEN EVENT[1] DO result=elapsed DISCONNECT TIMER elapsed ENDCONDITION ENABLE CONDITION[1] inner() END work'
        self.assertEqual(self.parity(routines=routines)['RESULT'],0)

    def test_global_timer_survives_routine_return(self):
        p,_=build('work() PAUSE DISCONNECT TIMER n',routines='ROUTINE work BEGIN CONNECT TIMER TO n END work',clock_us=lambda:0)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual((len(p._state._timers),p._state._frame_timers,p._state._timer_frames),(1,{},[]));p.resume()

    def test_computed_private_timer_retains_separate_invocation_lifetime(self):
        routines='ROUTINE copy_row(p:row_t):row_t BEGIN RETURN p END copy_row ROUTINE work VAR item:row_t BEGIN USING copy_row(item) DO CONNECT TIMER TO elapsed ENDUSING END work'
        p,_=build('work() PAUSE',routines,clock_us=lambda:0)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual((len(p._state._timers),p._state._frame_timers),(1,{}));p.stop()

    def test_local_timer_blocks_same_root_counter_even_on_sibling(self):
        with self.assertRaises(TranslationError) as error:build(routines='ROUTINE work VAR item:row_t BEGIN CONNECT TIMER TO item.elapsed FOR item.other=1 TO 2 DO ENDFOR END work')
        self.assertEqual(error.exception.code,'E_FOR_COUNTER')

    def test_local_timer_does_not_alias_global_counter_with_same_name(self):
        routine='ROUTINE work VAR n:INTEGER BEGIN CONNECT TIMER TO n END work'
        values=self.parity('total=0 FOR n=1 TO 2 DO work() total=total+n ENDFOR',routine)
        self.assertEqual((values['TOTAL'],values['N']),(3,U))

    def test_other_routine_local_timer_does_not_alias_local_counter_name(self):
        routines='ROUTINE inner VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed END inner ROUTINE work VAR elapsed:INTEGER BEGIN total=0 FOR elapsed=1 TO 2 DO inner() total=total+elapsed ENDFOR END work'
        self.assertEqual(self.parity(routines=routines)['TOTAL'],3)

    def test_global_timer_with_same_spelling_does_not_alias_local_counter(self):
        routine='ROUTINE work VAR n:INTEGER BEGIN total=0 FOR n=1 TO 2 DO total=total+n ENDFOR END work'
        self.assertEqual(self.parity('CONNECT TIMER TO n work() DISCONNECT TIMER n',routine)['TOTAL'],3)

    def test_formal_timer_roots_remain_rejected(self):
        with self.assertRaises(TranslationError) as error:build('work(n)',routines='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value END work')
        self.assertEqual(error.exception.code,'E_TIMER_SCOPE')

    def test_noninteger_and_config_local_domains_stay_rejected(self):
        for declaration,selector in [('elapsed:BYTE','elapsed'),('elapsed:SHORT','elapsed'),('elapsed:REAL','elapsed'),('cfg:CONFIG','cfg.cfg_turn_no1')]:
            with self.subTest(declaration=declaration),self.assertRaises(TranslationError) as error:build(routines=f'ROUTINE work VAR {declaration} BEGIN CONNECT TIMER TO {selector} END work')
            self.assertEqual(error.exception.code,'E_TYPE')

    def test_report_identifies_local_provenance_and_frame_lifetime(self):
        _,r=build();row=r.report['connected_timers'][0]
        self.assertEqual((row['root'],row['provenance'],row['lifetime']),('ELAPSED','routine_local','routine_frame'))
        self.assertFalse(r.report['routine_local_timer_policy']['controller_validated']);json.dumps(r.report,allow_nan=False)


class LocalTimerLifetimeTests(unittest.TestCase):
    def paused(self,routine=None):
        p,_=build(routines=routine or 'ROUTINE work VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed PAUSE result=elapsed END work',clock_us=lambda:0)
        with self.assertRaises(rt.KarelPause):p.run()
        return p

    def test_pause_retains_exact_frame_and_fractional_carry(self):
        clock={'us':0};p,_=build(routines='ROUTINE work VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed PAUSE result=elapsed END work',clock_us=lambda:clock['us'])
        with self.assertRaises(rt.KarelPause):p.run()
        binding=next(iter(p._state._frame_timers.values()));self.assertIs(binding[0],p._state.local_frames[-1])
        clock['us']=7123;self.assertEqual(p.resume()['RESULT'],7);self.assertEqual(empty_timers(p),({},{},[]))

    def test_parent_local_timer_survives_child_frame_unwind(self):
        routines='ROUTINE inner VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed END inner ROUTINE work VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed inner() PAUSE END work'
        p=self.paused(routines);self.assertEqual((len(p._state._timers),len(p._state._frame_timers),len(p._state._timer_frames)),(1,1,1));p.stop()

    def test_recursive_frames_have_independent_local_timers(self):
        routine='ROUTINE work(depth:INTEGER) VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed IF depth>0 THEN work(depth-1) ELSE PAUSE ENDIF END work'
        p,_=build('work(2)',routine,clock_us=lambda:0)
        with self.assertRaises(rt.KarelPause):p.run()
        bindings=list(p._state._frame_timers.values());self.assertEqual(len(bindings),3)
        self.assertEqual(len({id(row[0]) for row in bindings}),3);self.assertEqual(len({id(row[1][0].storage) for row in bindings}),3)
        p.resume();self.assertEqual(empty_timers(p),({},{},[]))

    def test_stop_releases_all_paused_frame_connections(self):
        p=self.paused();p.stop();self.assertEqual((empty_timers(p),p._state.local_frames),(({}, {}, []),[]))

    def test_abort_unwinds_connections_and_is_sticky(self):
        p,_=build(routines='ROUTINE work VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed ABORT END work',clock_us=lambda:0)
        for _ in range(2):
            with self.assertRaises(rt.KarelAbort):p.run()
            self.assertEqual(empty_timers(p),({},{},[]))

    def test_runtime_failure_cleans_connections_and_preserves_effects(self):
        p,_=build(routines='ROUTINE work VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed result=77 n=1 DIV 0 END work',clock_us=lambda:0)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['RESULT'],empty_timers(p)),(77,({}, {}, [])))

    def test_budget_failure_cleans_local_frame_connections(self):
        p,_=build(routines='ROUTINE work VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed WHILE TRUE DO ENDWHILE END work',clock_us=lambda:0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):p.run(max_steps=25)
        self.assertEqual(empty_timers(p),({},{},[]))

    def test_json_excludes_local_data_and_frame_timer_bindings(self):
        p=self.paused();config=json.loads(json.dumps(p._state.execution.to_config(),allow_nan=False))
        self.assertNotIn('ELAPSED',{row['path'] for row in config['variables']});self.assertNotIn('timers',config)
        self.assertNotIn('_frame_timers',config);p.stop()

    def test_linked_local_timer_cleans_invocation_and_keeps_caller_timer(self):
        project=translate_project({'main':source('MAIN','CONNECT TIMER TO elapsed n=work() PAUSE DISCONNECT TIMER elapsed',decl='elapsed,n:INTEGER',routines='ROUTINE work:INTEGER FROM LIB'),
            'lib':source('LIB','',routines='ROUTINE work:INTEGER VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed DELAY 3 RETURN elapsed END work')}).instantiate()
        with patch('karel2py.runtime.connect_timer',wraps=rt.connect_timer) as connect:project.run('MAIN')
        calls=connect.call_args_list;caller,callee=calls[0].args[0],calls[1].args[0]
        self.assertEqual((len(caller._timers),callee._timers,callee._frame_timers),(1,{},{}))
        self.assertGreaterEqual(project.programs['MAIN'].snapshot()['N'],3);project.scheduler.stop('MAIN')

    def test_concurrent_linked_invocations_keep_fresh_timer_owners(self):
        sources={'lib':source('LIB','',routines='ROUTINE work:INTEGER VAR elapsed:INTEGER BEGIN CONNECT TIMER TO elapsed DELAY 3 RETURN elapsed END work'),
            'main':source('MAIN',"RUN_TASK('SECOND',0,FALSE,FALSE,0,s) n=work()",routines='ROUTINE work:INTEGER FROM LIB'),
            'second':source('SECOND','n=work()',routines='ROUTINE work:INTEGER FROM LIB')}
        project=translate_project(sources).instantiate()
        with patch('karel2py.runtime.connect_timer',wraps=rt.connect_timer) as connect:values=project.run('MAIN')
        states=[call.args[0] for call in connect.call_args_list];self.assertEqual(len(states),2);self.assertIsNot(states[0],states[1])
        self.assertTrue(all(empty_state._timers=={} and empty_state._frame_timers=={} for empty_state in states))
        self.assertTrue(values['MAIN']['values']['N']>=3 and values['SECOND']['values']['N']>=3)


class LocalTimerOwnershipTests(unittest.TestCase):
    def active(self):
        p,_=build(clock_us=lambda:0);state=p._state
        state.enter_routine({'E':('INTEGER',)},routine='DIRECT')
        return p,state,state.reference('E')

    def connect(self,state,ref):
        with rt._numeric_scope('pythonic'):rt.connect_timer(state,ref,23,scoped=True)

    def test_scoped_connection_requires_live_frame_before_clock_or_initialization(self):
        p,_=build(clock_us=lambda:False);state=p._state;ref=rt.Reference(('INTEGER',),{'E':rt.UNINITIALIZED},'E')
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'active routine frame'):rt.connect_timer(state,ref,23,scoped=True)
        self.assertIs(ref.raw(),rt.UNINITIALIZED);self.assertEqual(state._timers,{})

    def test_retained_dead_frame_cannot_be_presented_as_live(self):
        p,state,ref=self.active();frame=state.local_frames[-1];state.leave_routine();state.local_frames=[frame]
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'active routine frame'):rt.connect_timer(state,ref,23,scoped=True)
        self.assertIs(ref.raw(),rt.UNINITIALIZED);state.local_frames=[]

    def test_invalid_scope_flag_does_not_initialize_local_storage(self):
        for value in (1,None,'yes'):
            p,state,ref=self.active()
            with self.subTest(value=value),self.assertRaisesRegex(rt.KarelRuntimeError,'scope flag'):rt.connect_timer(state,ref,23,scoped=value)
            self.assertIs(ref.raw(),rt.UNINITIALIZED);state.leave_routine()

    def test_disconnect_from_other_active_frame_preserves_connection(self):
        p,state,ref=self.active();self.connect(state,ref);state.enter_routine({'N':('INTEGER',)},routine='INNER')
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'another frame'):rt.disconnect_timer(state,ref,23,scoped=True)
        state.leave_routine();self.assertEqual(len(state._timers),1);state.leave_routine();self.assertEqual(empty_timers(p),({},{},[]))

    def test_frame_cleanup_preserves_foreign_registration_replacement(self):
        p,state,ref=self.active();self.connect(state,ref);key=next(iter(state._timers));foreign=[ref,0,0];state._timers[key]=foreign
        state.leave_routine();self.assertIs(state._timers[key],foreign);self.assertEqual((state._frame_timers,state._timer_frames),({},[]))

    def test_changed_registration_fails_before_clock_or_value_update(self):
        p,state,ref=self.active();self.connect(state,ref);key=next(iter(state._timers));state._timers[key]=[ref,0,0]
        state._clock_us=lambda:False
        with self.assertRaisesRegex(rt.KarelRuntimeError,'registration changed'):rt.update_timers(state,23)
        self.assertEqual(ref.raw(),0);state.leave_routine()

    def test_lost_registration_is_not_hidden_by_empty_bank(self):
        p,state,ref=self.active();self.connect(state,ref);state._timers.clear()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'registration changed'):rt.update_timers(state,23)
        state.leave_routine();self.assertEqual(empty_timers(p),({},{},[]))

    def test_disconnect_rejects_replaced_registration(self):
        p,state,ref=self.active();self.connect(state,ref);key=next(iter(state._timers));foreign=[ref,0,0];state._timers[key]=foreign
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'registration changed'):rt.disconnect_timer(state,ref,23,scoped=True)
        self.assertIs(state._timers[key],foreign);state.leave_routine()

    def test_invalid_clock_does_not_register_or_initialize_local(self):
        p,state,ref=self.active();state._clock_us=lambda:False
        with self.assertRaises(rt.KarelRuntimeError):self.connect(state,ref)
        self.assertIs(ref.raw(),rt.UNINITIALIZED);self.assertEqual((state._timers,state._frame_timers),({},{}));state.leave_routine()

    def test_diagnostic_entry_failure_unwinds_timer_registered_by_observer(self):
        log=DiagnosticLog();p,_=build(context=rt.ExecutionContext(diagnostics=log),clock_us=lambda:0);state=p._state
        def fail_entry(owner):
            self.connect(owner,owner.reference('E'))
            raise ValueError('entry observer failed')
        with patch.object(log,'observe',side_effect=fail_entry),self.assertRaisesRegex(ValueError,'entry observer'):
            state.enter_routine({'E':('INTEGER',)},routine='DIRECT')
        self.assertEqual((empty_timers(p),state.local_frames,state.call_depth),(({}, {}, []),[],0))

    def test_legacy_scoped_api_stays_unavailable(self):
        p,state,ref=self.active()
        with rt._numeric_scope('strict'),self.assertRaisesRegex(rt.KarelRuntimeError,'Pythonic'):rt.connect_timer(state,ref,23,scoped=True)
        state.leave_routine()


if __name__=='__main__':unittest.main()
