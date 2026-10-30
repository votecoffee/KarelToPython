"""Authored borrowed formal timers, shared claims, effects and exact frame cleanup."""
import json
import unittest
from unittest.mock import patch
from karel2py import translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source
from tests.test_variable_archives import context as archive_context,install,envelope

U={'uninitialized':True}
TYPES='TYPE row_t=STRUCTURE elapsed:INTEGER other:INTEGER ticks:ARRAY[2]OF INTEGER ENDSTRUCTURE'
DECL='n,result,total,seen,index_value,s:INTEGER ready,done:BOOLEAN'
DEFAULT='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value result=value END work'


def build(body='work(n)',routines=DEFAULT,**options):
    return compile_program(body,prefix=TYPES,decl=DECL,routines=routines,**options)


def execute(body='work(n)',routines=DEFAULT,**options):return build(body,routines,**options)[0].run()


def no_timers(program):
    state=program._state
    return state._timers,state._frame_timers,state._timer_frames,state.execution._timer_claims


class FormalTimerSourceTests(unittest.TestCase):
    def test_missing_bare_actual_initializes_caller_storage(self):
        p,_=build(clock_us=lambda:0);self.assertEqual((p.run()['N'],p.snapshot()['RESULT']),(0,0));self.assertEqual(no_timers(p),({},{},[],{}))

    def test_implicit_return_does_not_add_a_clock_checkpoint(self):
        clock={'us':0}
        p,_=build(routines='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value DELAY 3 END work',clock_us=lambda:clock['us'],sleep=lambda _:clock.update(us=3000))
        self.assertEqual(p.run()['N'],0);self.assertEqual(p._state.execution._timer_claims,{})

    def test_initialized_actual_keeps_start_value(self):
        self.assertEqual(execute('n=-7 work(n)',clock_us=lambda:0)['RESULT'],-7)

    def test_record_formal_field_borrows_caller_leaf(self):
        p,_=compile_program('work(item)',prefix=TYPES,decl='item:row_t result:INTEGER',routines='ROUTINE work(value:row_t) BEGIN CONNECT TIMER TO value.elapsed result=value.elapsed END work',clock_us=lambda:0)
        self.assertEqual(p.run()['ITEM'],dict(ELAPSED=0,OTHER=U,TICKS=[U,U]))

    def test_array_formal_selector_is_captured_once(self):
        routines='ROUTINE pick:INTEGER BEGIN seen=seen+1 RETURN index_value END pick ROUTINE work(value:ARRAY OF INTEGER) BEGIN CONNECT TIMER TO value[pick()] index_value=2 result=value[1] DISCONNECT TIMER value[1] END work'
        p,_=compile_program('seen=0 index_value=1 work(items)',decl=DECL+' items:ARRAY[2]OF INTEGER',routines=routines,clock_us=lambda:0)
        self.assertEqual((p.run()['ITEMS'],p.snapshot()['SEEN'],p.snapshot()['RESULT']),([0,U],1,0))

    def test_named_using_formal_alias_keeps_borrowed_provenance(self):
        p,r=compile_program('work(item)',prefix=TYPES,decl='item:row_t',routines='ROUTINE work(value:row_t) BEGIN USING value DO CONNECT TIMER TO elapsed ENDUSING END work',clock_us=lambda:0)
        self.assertEqual(p.run()['ITEM']['ELAPSED'],0);self.assertEqual(r.report['connected_timers'][0]['provenance'],'borrowed_formal')

    def test_grouped_scalar_argument_remains_private(self):
        routine='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value value=99 result=value END work'
        v=execute('n=7 work((n))',routine,clock_us=lambda:0);self.assertEqual((v['N'],v['RESULT']),(7,99))

    def test_scalar_expression_argument_owns_private_timer_cell(self):
        v=execute('work(1+2)','ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value value=99 result=value END work',clock_us=lambda:0)
        self.assertEqual((v['N'],v['RESULT']),(U,99))

    def test_promoted_short_scalar_is_private(self):
        p,_=compile_program('small=7 work(small)',decl='small:SHORT result:INTEGER',routines='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value value=99 result=value END work',clock_us=lambda:0)
        self.assertEqual((p.run()['SMALL'],p.snapshot()['RESULT']),(7,99))

    def test_converted_numeric_array_is_private_even_for_bare_actual(self):
        p,_=compile_program('work(items)',decl='items:ARRAY[2]OF SHORT',routines='ROUTINE work(value:ARRAY OF INTEGER) BEGIN CONNECT TIMER TO value[1] value[1]=99 END work',clock_us=lambda:0)
        self.assertEqual(p.run()['ITEMS'],[U,U])

    def test_grouped_partial_aggregate_can_initialize_private_timer_leaf(self):
        p,_=compile_program('work((item))',prefix=TYPES,decl='item:row_t result:INTEGER',routines='ROUTINE work(value:row_t) BEGIN CONNECT TIMER TO value.elapsed result=value.elapsed END work',clock_us=lambda:0)
        self.assertEqual((p.run()['ITEM']['ELAPSED'],p.snapshot()['RESULT']),(U,0))

    def test_forwarded_formal_retains_original_reference(self):
        routines='ROUTINE inner(p:INTEGER) BEGIN CONNECT TIMER TO p END inner ROUTINE work(value:INTEGER) BEGIN inner(value) result=value END work'
        self.assertEqual(execute(routines=routines,clock_us=lambda:0)['N'],0)

    def test_parameter_alias_duplicate_is_rejected_and_unwound(self):
        p,_=build('work(n,n)',routines='ROUTINE work(first,second:INTEGER) BEGIN CONNECT TIMER TO first CONNECT TIMER TO second END work',clock_us=lambda:0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'already connected'):p.run()
        self.assertEqual((p.snapshot()['N'],no_timers(p)),(0,({}, {}, [], {})))

    def test_unknown_grouped_scalar_fails_before_callee_entry(self):
        p,_=build('work((n))',clock_us=lambda:0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'):p.run()
        self.assertEqual((p.snapshot()['N'],p._state.execution._timer_claims),(U,{}))

    def test_config_and_noninteger_formals_keep_type_guards(self):
        for spec,selector,decl,actual in [('CONFIG','value.cfg_turn_no1','cfg:CONFIG','cfg'),('SHORT','value','small:SHORT','small'),('REAL','value','number:REAL','number')]:
            with self.subTest(spec=spec),self.assertRaises(TranslationError) as error:
                compile_program(f'work({actual})',decl=decl,routines=f'ROUTINE work(value:{spec}) BEGIN CONNECT TIMER TO {selector} END work')
            self.assertEqual(error.exception.code,'E_TYPE')

    def test_active_counter_bare_actual_is_rejected(self):
        with self.assertRaises(TranslationError) as error:build('FOR n=1 TO 2 DO work(n) ENDFOR')
        self.assertEqual(error.exception.code,'E_FOR_COUNTER')

    def test_transitive_formal_timer_write_is_rejected_for_active_counter(self):
        routines='ROUTINE inner(p:INTEGER) BEGIN CONNECT TIMER TO p END inner ROUTINE work(value:INTEGER) BEGIN inner(value) END work'
        with self.assertRaises(TranslationError) as error:build('FOR n=1 TO 2 DO work(n) ENDFOR',routines)
        self.assertEqual(error.exception.code,'E_FOR_COUNTER')

    def test_grouped_counter_value_is_safe_even_when_formal_has_same_name(self):
        routine='ROUTINE work(n:INTEGER) BEGIN CONNECT TIMER TO n n=99 END work'
        v=execute('total=0 FOR n=1 TO 2 DO work((n)) total=total+n ENDFOR',routine,clock_us=lambda:0)
        self.assertEqual((v['TOTAL'],v['N']),(3,U))

    def test_handler_timer_alias_blocks_active_counter(self):
        body='CONDITION[1]: WHEN EVENT[1] DO work(n) ENDCONDITION FOR n=1 TO 2 DO ENDFOR'
        with self.assertRaises(TranslationError) as error:build(body)
        self.assertEqual(error.exception.code,'E_FOR_COUNTER')

    def test_numeric_array_conversion_does_not_alias_active_narrow_counter(self):
        p,_=compile_program('items[2]=7 total=0 FOR items[1]=1 TO 2 DO work(items) total=total+items[1] ENDFOR',decl='items:ARRAY[2]OF SHORT total:INTEGER',routines='ROUTINE work(value:ARRAY OF INTEGER) BEGIN CONNECT TIMER TO value[1] value[1]=99 END work',clock_us=lambda:0)
        self.assertEqual((p.run()['TOTAL'],p.snapshot()['ITEMS']),(3,[U,7]))

    def test_retained_handler_timer_alias_blocks_later_global_counter(self):
        routines='ROUTINE tick(p:INTEGER) BEGIN CONNECT TIMER TO p END tick ROUTINE work(value:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO tick(value) ENDCONDITION END work'
        with self.assertRaises(TranslationError) as error:build('work(n) FOR n=1 TO 2 DO SIGNAL EVENT[1] ENDFOR',routines)
        self.assertEqual(error.exception.code,'E_FOR_COUNTER')

    def test_transitive_retained_handler_timer_blocks_later_local_counter(self):
        routines='ROUTINE tick(p:INTEGER) BEGIN CONNECT TIMER TO p END tick ROUTINE retain(value:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO tick(value) ENDCONDITION END retain ROUTINE forward(value:INTEGER) BEGIN retain(value) END forward ROUTINE work VAR local_value:INTEGER BEGIN forward(local_value) FOR local_value=1 TO 2 DO ENDFOR END work'
        with self.assertRaises(TranslationError) as error:build('work()',routines)
        self.assertEqual(error.exception.code,'E_FOR_COUNTER')

    def test_handler_using_detached_timer_value_does_not_retain_write_alias(self):
        routines='ROUTINE tick(p:INTEGER) BEGIN CONNECT TIMER TO p END tick ROUTINE work(value:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO tick((value)) ENDCONDITION END work'
        v=execute('n=9 work(n) ENABLE CONDITION[1] total=0 FOR n=1 TO 2 DO SIGNAL EVENT[1] total=total+n ENDFOR',routines,clock_us=lambda:0)
        self.assertEqual(v['TOTAL'],3)

    def test_bare_private_alias_keeps_existing_conservative_escape_guard(self):
        routines='ROUTINE make:row_t VAR item:row_t BEGIN RETURN item END make '+DEFAULT
        body='USING make() DO work(elapsed) FOR other=1 TO 2 DO ENDFOR ENDUSING'
        with self.assertRaises(TranslationError) as error:build(body,routines)
        self.assertEqual(error.exception.code,'E_FOR_COUNTER')

    def test_detached_private_actual_does_not_escape_counter_root(self):
        routines='ROUTINE make:row_t VAR item:row_t BEGIN RETURN item END make '+DEFAULT
        body='total=0 USING make() DO elapsed=9 work((elapsed)) FOR other=1 TO 2 DO total=total+other ENDFOR ENDUSING'
        self.assertEqual(execute(body,routines,clock_us=lambda:0)['TOTAL'],3)

    def test_pause_retains_borrow_and_updates_caller_before_resume_return(self):
        clock={'us':0};p,_=build(routines='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value PAUSE result=value END work',clock_us=lambda:clock['us'])
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(len(p._state.execution._timer_claims),1);clock['us']=7123
        self.assertEqual((p.resume()['N'],p.snapshot()['RESULT']),(7,7));self.assertEqual(no_timers(p),({},{},[],{}))

    def test_stop_releases_claim_without_copyback_or_restart(self):
        p,_=build(routines='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value PAUSE END work',clock_us=lambda:0)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual((p.snapshot()['N'],no_timers(p)),(0,({}, {}, [], {})))

    def test_abort_is_sticky_and_releases_claim(self):
        p,_=build(routines='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value ABORT END work',clock_us=lambda:0)
        for _ in range(2):
            with self.assertRaises(rt.KarelAbort):p.run()
            self.assertEqual(p._state.execution._timer_claims,{})

    def test_budget_failure_releases_claim(self):
        p,_=build(routines='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value WHILE TRUE DO ENDWHILE END work',clock_us=lambda:0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):p.run(max_steps=25)
        self.assertEqual(no_timers(p),({},{},[],{}))

    def test_callee_failure_preserves_completed_caller_writes(self):
        p,_=build(routines='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value value=99 s=1 DIV 0 END work',clock_us=lambda:0)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p._state.execution._timer_claims),(99,{}))

    def test_retained_formal_handler_reads_current_caller_data_after_return(self):
        routine='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value CONDITION[1]: WHEN EVENT[1] DO result=value ENDCONDITION END work'
        v=execute('work(n) n=99 ENABLE CONDITION[1] SIGNAL EVENT[1]',routine,clock_us=lambda:0)
        self.assertEqual((v['N'],v['RESULT']),(99,99))

    def test_retained_formal_handler_cannot_restart_its_dead_frame_timer(self):
        routine='ROUTINE work(value:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO CONNECT TIMER TO value ENDCONDITION END work'
        p,_=build('work(n) ENABLE CONDITION[1] SIGNAL EVENT[1]',routine,clock_us=lambda:0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'active routine frame'):p.run()
        self.assertEqual(p._state.execution._timer_claims,{})

    def test_live_captured_formal_can_control_timer_during_nested_call(self):
        routines='ROUTINE inner BEGIN SIGNAL EVENT[1] END inner ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value CONDITION[1]: WHEN EVENT[1] DO DISCONNECT TIMER value result=value ENDCONDITION ENABLE CONDITION[1] inner() END work'
        self.assertEqual(execute(routines=routines,clock_us=lambda:0)['RESULT'],0)

    def test_new_call_can_borrow_retained_writable_data_under_new_frame(self):
        routines='ROUTINE tick_value(p:INTEGER) BEGIN CONNECT TIMER TO p p=9 END tick_value ROUTINE work(value:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO tick_value(value) ENDCONDITION END work'
        self.assertEqual(execute('work(n) ENABLE CONDITION[1] SIGNAL EVENT[1]',routines,clock_us=lambda:0)['N'],9)

    def test_json_omits_live_claims_and_restores_data_only(self):
        p,_=build(routines='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value PAUSE END work',clock_us=lambda:0)
        with self.assertRaises(rt.KarelPause):p.run()
        data=json.loads(json.dumps(p._state.execution.to_config(),allow_nan=False))
        self.assertNotIn('_timer_claims',data);self.assertNotIn('timers',data)
        restored=rt.ExecutionContext.from_config(data);self.assertEqual(restored._timer_claims,{})
        self.assertEqual(next(row['value'] for row in data['variables'] if row['path']=='N'),0);p.stop()

    def test_report_records_borrowed_frame_lifetime(self):
        _,r=build();row=r.report['connected_timers'][0]
        self.assertEqual((row['provenance'],row['lifetime'],row['root']),('borrowed_formal','routine_frame','VALUE'))
        self.assertFalse(r.report['formal_timer_policy']['controller_validated']);json.dumps(r.report,allow_nan=False)


class FormalTimerProjectTests(unittest.TestCase):
    def project(self,main='n=work(n)',lib='CONNECT TIMER TO value DELAY 3 RETURN value'):
        return translate_project({'main':source('MAIN',main,decl='n,s:INTEGER',routines='ROUTINE work(value:INTEGER):INTEGER FROM LIB'),
            'lib':source('LIB','',routines='ROUTINE work(value:INTEGER):INTEGER BEGIN '+lib+' END work')}).instantiate()

    def test_linked_borrow_updates_caller_and_releases_transient_claim(self):
        project=self.project();values=project.run('MAIN')
        self.assertGreaterEqual(values['MAIN']['values']['N'],3);self.assertEqual(project.context._timer_claims,{})

    def test_caller_connection_prevents_linked_duplicate(self):
        project=self.project('CONNECT TIMER TO n s=work(n)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'already connected'):project.run('MAIN')
        self.assertEqual(project.context._timer_claims,{})

    def test_formal_disconnect_does_not_take_over_caller_connection(self):
        project=self.project('CONNECT TIMER TO n s=work(n)',lib='DISCONNECT TIMER value RETURN value')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not connected|another frame'):project.run('MAIN')
        self.assertEqual(project.context._timer_claims,{})

    def test_stop_inside_linked_borrow_releases_actual_callee_claim(self):
        project=self.project('s=work(n)',lib='CONNECT TIMER TO value PAUSE RETURN value')
        project.run('MAIN');self.assertEqual(len(project.context._timer_claims),1)
        project.scheduler.stop('MAIN');self.assertEqual(project.context._timer_claims,{})

    def test_independent_concurrent_borrows_do_not_collide(self):
        sources={'lib':source('LIB','',routines='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value DELAY 3 DISCONNECT TIMER value END work'),
            'main':source('MAIN',"RUN_TASK('SECOND',0,FALSE,FALSE,0,s) work(n)",routines='ROUTINE work(value:INTEGER) FROM LIB'),
            'second':source('SECOND','work(n)',routines='ROUTINE work(value:INTEGER) FROM LIB')}
        project=translate_project(sources).instantiate();v=project.run('MAIN')
        self.assertTrue(v['MAIN']['values']['N']>=3 and v['SECOND']['values']['N']>=3);self.assertEqual(project.context._timer_claims,{})

    def test_shared_cell_concurrent_borrow_is_rejected_and_peer_retained(self):
        sources={'lib':source('LIB','',decl='shared_value:INTEGER',routines='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value DELAY 20 END work'),
            'main':source('MAIN',"RUN_TASK('SECOND',0,FALSE,FALSE,0,s) work(shared_value)",decl='shared_value FROM LIB:INTEGER s:INTEGER',routines='ROUTINE work(value:INTEGER) FROM LIB'),
            'second':source('SECOND','work(shared_value)',decl='shared_value FROM LIB:INTEGER',routines='ROUTINE work(value:INTEGER) FROM LIB')}
        project=translate_project(sources).instantiate()
        try:
            with self.assertRaisesRegex(rt.KarelRuntimeError,'already connected'):project.run('MAIN')
            self.assertEqual(len(project.context._timer_claims),1)
        finally:
            for name in ('MAIN','SECOND'):project.scheduler.stop(name)
        self.assertEqual(project.context._timer_claims,{})

    def test_archive_load_does_not_overwrite_active_borrowed_caller(self):
        ctx=archive_context();install(ctx,envelope('T',{'N':{'type':['INTEGER'],'value':17}}),'FR:T.VR')
        p,_=build('n=99 work(n)',routines="ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value LOAD('FR:T.VR',0,s) END work",context=ctx,clock_us=lambda:0)
        self.assertEqual((p.run()['N'],p.snapshot()['S']),(99,4))


class TimerClaimOwnershipTests(unittest.TestCase):
    def states(self,context=None):
        ctx=context or rt.ExecutionContext();a,_=build(context=ctx,clock_us=lambda:0);b,_=build(context=ctx,clock_us=lambda:0)
        ref=rt.Reference(('INTEGER',),{'N':rt.UNINITIALIZED},'N')
        return ctx,a._state,b._state,ref

    def connect(self,state,ref,scoped=False):
        with rt._numeric_scope('pythonic'):rt.connect_timer(state,ref,23,scoped=scoped)

    def test_duplicate_across_states_is_rejected_before_second_clock(self):
        ctx,a,b,ref=self.states();self.connect(a,ref);calls=[];b._clock_us=lambda:calls.append(1) or False
        with self.assertRaisesRegex(rt.KarelRuntimeError,'already connected'):self.connect(b,ref)
        self.assertEqual((calls,len(ctx._timer_claims),b._timers),([],1,{}));a.finish_timers()

    def test_explicit_disconnect_releases_claim_for_another_state(self):
        ctx,a,b,ref=self.states();self.connect(a,ref);rt.disconnect_timer(a,ref);self.connect(b,ref)
        self.assertIs(next(iter(ctx._timer_claims.values()))[0],b);b.finish_timers();self.assertEqual(ctx._timer_claims,{})

    def test_frame_unwind_releases_only_its_claim(self):
        ctx,a,b,ref=self.states();a.enter_routine({'E':('INTEGER',)},routine='A');self.connect(a,a.reference('E'),True)
        self.connect(b,ref);a.leave_routine();self.assertEqual(len(ctx._timer_claims),1);self.assertIs(next(iter(ctx._timer_claims.values()))[0],b);b.finish_timers()

    def test_existing_local_connection_is_not_borrowed_again_by_another_state(self):
        ctx,a,b,ref=self.states();a.enter_routine({'E':('INTEGER',)},routine='A');ref=a.reference('E');self.connect(a,ref,True)
        b.enter_routine({'P':('INTEGER',)},arguments={'P':ref},routine='B')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'already connected'):self.connect(b,b.reference('P'),True)
        b.leave_routine();self.assertEqual(len(ctx._timer_claims),1);a.leave_routine();self.assertEqual(ctx._timer_claims,{})

    def test_separate_contexts_keep_separate_explicit_model_domains(self):
        ctx,a,b,ref=self.states();other=rt.ExecutionContext();p,_=build(context=other,clock_us=lambda:0)
        self.connect(a,ref);self.connect(p._state,ref);self.assertEqual((len(ctx._timer_claims),len(other._timer_claims)),(1,1));a.finish_timers();p._state.finish_timers()

    def test_replaced_claim_fails_before_clock_and_is_preserved_on_cleanup(self):
        ctx,a,b,ref=self.states();self.connect(a,ref);key=next(iter(ctx._timer_claims));record=a._timers[key];foreign=(b,record);ctx._timer_claims[key]=foreign;a._clock_us=lambda:False
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ownership changed'):rt.update_timers(a,23)
        self.assertEqual(ref.raw(),0);a.finish_timers();self.assertIs(ctx._timer_claims[key],foreign)

    def test_replaced_record_retains_uncertain_claim_and_blocks_reuse(self):
        ctx,a,b,ref=self.states();self.connect(a,ref);key=next(iter(ctx._timer_claims));claim=ctx._timer_claims[key];a._timers[key]=[ref,0,0]
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ownership changed'):rt.update_timers(a,23)
        a.finish_timers();self.assertIs(ctx._timer_claims[key],claim)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'reserved'):self.connect(b,ref)

    def test_lost_claim_does_not_allow_update_or_disconnect(self):
        ctx,a,b,ref=self.states();self.connect(a,ref);ctx._timer_claims.clear()
        for operation in (lambda:rt.update_timers(a,23),lambda:rt.disconnect_timer(a,ref,23)):
            with self.subTest(operation=operation),self.assertRaisesRegex(rt.KarelRuntimeError,'ownership changed'):operation()
        self.assertEqual((ref.raw(),len(a._timers)),(0,1));a.finish_timers()

    def test_clock_reference_redirection_fails_before_initialization(self):
        ctx,a,b,ref=self.states();old=ref.storage;new={'N':rt.UNINITIALIZED}
        def redirect():ref.storage=new;return 0
        a._clock_us=redirect
        with self.assertRaisesRegex(rt.KarelRuntimeError,'reference changed'):self.connect(a,ref)
        self.assertIs(old['N'],rt.UNINITIALIZED);self.assertIs(new['N'],rt.UNINITIALIZED);self.assertEqual(ctx._timer_claims,{})

    def test_clock_key_type_redirection_is_rejected_even_when_equal(self):
        ctx,a,b,ref=self.states();ref=rt.Reference(('INTEGER',),[rt.UNINITIALIZED],0)
        def redirect():ref.key=False;return 0
        a._clock_us=redirect
        with self.assertRaisesRegex(rt.KarelRuntimeError,'reference changed'):self.connect(a,ref)
        self.assertEqual(ctx._timer_claims,{})

    def test_registered_reference_endpoint_change_keeps_original_storage_reserved(self):
        ctx,a,b,ref=self.states();self.connect(a,ref);old=ref.storage;key=next(iter(ctx._timer_claims));ref.storage={'N':99};a._clock_us=lambda:False
        with self.assertRaisesRegex(rt.KarelRuntimeError,'reference changed'):rt.update_timers(a,23)
        self.assertEqual((old['N'],ref.raw()),(0,99));a.finish_timers()
        self.assertIs(ctx._timer_claims[key][2],old)

    def test_archive_protects_retained_original_endpoint_after_ref_redirection(self):
        ctx=archive_context();ctx,a,b,ref=self.states(ctx);ref.set(99);self.connect(a,ref);old=ref.storage
        ctx.variables.bind('CACHE','VALUE',rt.Reference(('INTEGER',),old,'N'));ref.storage={'N':0};install(ctx)
        p,_=compile_program("LOAD('FR:CACHE.VR',0,s)",context=ctx,clock_us=lambda:0)
        self.assertEqual((p.run()['S'],old['N']),(4,99));a.finish_timers();self.assertEqual(len(ctx._timer_claims),1)

    def test_reentrant_clock_claim_is_preserved_without_outer_publication(self):
        ctx,a,b,ref=self.states()
        def claim():self.connect(b,ref);return 0
        a._clock_us=claim
        with self.assertRaisesRegex(rt.KarelRuntimeError,'already connected'):self.connect(a,ref)
        self.assertEqual(a._timers,{});self.assertIs(next(iter(ctx._timer_claims.values()))[0],b)
        a.finish_timers();self.assertEqual(len(ctx._timer_claims),1);b.finish_timers()

    def test_update_clock_endpoint_redirection_does_not_write_any_cell(self):
        ctx,a,b,ref=self.states();self.connect(a,ref);old=ref.storage;new={'N':99}
        def redirect():ref.storage=new;return 3000
        a._clock_us=redirect
        with self.assertRaisesRegex(rt.KarelRuntimeError,'reference changed'):rt.update_timers(a,23)
        self.assertEqual((old['N'],new['N']),(0,99));a.finish_timers();self.assertEqual(len(ctx._timer_claims),1)

    def test_update_clock_claim_replacement_is_preserved_before_writes(self):
        ctx,a,b,ref=self.states();self.connect(a,ref);key=next(iter(ctx._timer_claims));foreign=(b,a._timers[key],ref.storage,ref.key)
        def replace():ctx._timer_claims[key]=foreign;return 3000
        a._clock_us=replace
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ownership changed'):rt.update_timers(a,23)
        self.assertEqual(ref.raw(),0);a.finish_timers();self.assertIs(ctx._timer_claims[key],foreign)

    def test_update_clock_bank_retirement_preserves_new_owner(self):
        ctx,a,b,ref=self.states();self.connect(a,ref)
        def replace():a.finish_timers();self.connect(b,ref);return 3000
        a._clock_us=replace
        with self.assertRaisesRegex(rt.KarelRuntimeError,'bank changed'):rt.update_timers(a,23)
        self.assertEqual(ref.raw(),0);self.assertIs(next(iter(ctx._timer_claims.values()))[0],b);b.finish_timers()

    def test_update_clock_frame_retirement_does_not_tick_retired_cell(self):
        ctx,a,b,ref=self.states();a.enter_routine({'E':('INTEGER',)},routine='A');ref=a.reference('E');self.connect(a,ref,True)
        def leave():a.leave_routine();return 3000
        a._clock_us=leave
        with self.assertRaisesRegex(rt.KarelRuntimeError,'bank changed'):rt.update_timers(a,23)
        self.assertEqual((ref.raw(),ctx._timer_claims),(0,{}))

    def test_connect_clock_frame_retirement_prevents_publication(self):
        ctx,a,b,ref=self.states();a.enter_routine({'E':('INTEGER',)},routine='A');ref=a.reference('E')
        def leave():a.leave_routine();return 0
        a._clock_us=leave
        with self.assertRaisesRegex(rt.KarelRuntimeError,'active routine frame'):self.connect(a,ref,True)
        self.assertIs(ref.raw(),rt.UNINITIALIZED);self.assertEqual((a._timers,ctx._timer_claims),({},{}))

    def test_connect_clock_completed_initialization_is_preserved(self):
        ctx,a,b,ref=self.states()
        def initialize():ref.set(99);return 0
        a._clock_us=initialize;self.connect(a,ref)
        self.assertEqual(ref.raw(),99);a.finish_timers();self.assertEqual(ctx._timer_claims,{})

    def test_unattached_claim_prevents_archive_alias_overwrite(self):
        ctx=archive_context();ctx,a,b,ref=self.states(ctx);ref.set(99);self.connect(a,ref)
        ctx.variables.bind('CACHE','VALUE',ref);install(ctx)
        p,_=compile_program("LOAD('FR:CACHE.VR',0,s)",context=ctx,clock_us=lambda:0)
        self.assertEqual((p.run()['S'],ref.raw()),(4,99));self.assertEqual(len(ctx._timer_claims),1);a.finish_timers()

    def test_uncertain_claim_still_protects_archive_cells_after_bank_is_lost(self):
        ctx=archive_context();ctx,a,b,ref=self.states(ctx);ref.set(99);self.connect(a,ref);a._timers.clear()
        ctx.variables.bind('CACHE','VALUE',ref);install(ctx)
        p,_=compile_program("LOAD('FR:CACHE.VR',0,s)",context=ctx,clock_us=lambda:0)
        self.assertEqual((p.run()['S'],ref.raw()),(4,99));self.assertEqual(len(ctx._timer_claims),1)


if __name__=='__main__':unittest.main()
