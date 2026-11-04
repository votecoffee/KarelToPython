"""Same-task borrowed timer control, exact claim ownership and frame boundaries."""
from copy import deepcopy
import json
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source

TYPES='TYPE row_t=STRUCTURE ticks:INTEGER other:INTEGER ENDSTRUCTURE'
DECL='n,m,result,s,index_value,visits:INTEGER a:ARRAY[2]OF INTEGER item:row_t'
STOP='ROUTINE stop_timer(value:INTEGER) BEGIN DISCONNECT TIMER value END stop_timer'

def build(body='CONNECT TIMER TO n stop_timer(n)',*,routines=STOP,decl=DECL,**options):
    now=[0]
    def sleep(seconds):now[0]+=round(seconds*1000000)
    p,r=compile_program(body,decl=decl,prefix=TYPES,routines=routines,clock_us=lambda:now[0],sleep=sleep,**options)
    return p,r,now

def claims(p):return p._state.execution._timer_claims

def banks():
    context=rt.ExecutionContext();owner,_=compile_program('',decl='n:INTEGER',context=context,clock_us=lambda:0);helper,_=compile_program('',decl='n:INTEGER',context=context,clock_us=lambda:0)
    a,b=owner._state,helper._state;b._budget_parent=a
    ref=a.reference('N')
    with rt._numeric_scope('pythonic'):rt.connect_timer(a,ref,11)
    return context,a,b,ref

class TimerControlSourceTests(unittest.TestCase):
    def test_helper_disconnects_caller_global(self):
        p,_,_=build('CONNECT TIMER TO n DELAY 5 stop_timer(n) DELAY 9');self.assertEqual(p.run()['N'],5);self.assertEqual(claims(p),{})
    def test_initialized_value_is_retained(self):
        p,_,_=build('n=-7 CONNECT TIMER TO n DELAY 5 stop_timer(n) DELAY 9');self.assertEqual(p.run()['N'],-2)
    def test_array_leaf_control(self):
        p,_,_=build('CONNECT TIMER TO a[2] DELAY 5 stop_timer(a[2]) DELAY 9');self.assertEqual(p.run()['A'],[{'uninitialized':True},5])
    def test_record_leaf_control(self):
        p,_,_=build('CONNECT TIMER TO item.ticks DELAY 5 stop_timer(item.ticks) DELAY 9');self.assertEqual(p.run()['ITEM'],{'TICKS':5,'OTHER':{'uninitialized':True}})
    def test_record_formal_selector(self):
        routine='ROUTINE stop_timer(value:row_t) BEGIN DISCONNECT TIMER value.ticks END stop_timer'
        p,_,_=build('CONNECT TIMER TO item.ticks DELAY 5 stop_timer(item) DELAY 9',routines=routine);self.assertEqual(p.run()['ITEM']['TICKS'],5)
    def test_array_formal_selector(self):
        routine='ROUTINE stop_timer(value:ARRAY OF INTEGER) BEGIN DISCONNECT TIMER value[2] END stop_timer'
        p,_,_=build('CONNECT TIMER TO a[2] DELAY 5 stop_timer(a) DELAY 9',routines=routine);self.assertEqual(p.run()['A'][1],5)
    def test_named_using_formal_control(self):
        routine='ROUTINE stop_timer(value:row_t) BEGIN USING value DO DISCONNECT TIMER ticks ENDUSING END stop_timer'
        p,_,_=build('CONNECT TIMER TO item.ticks DELAY 5 stop_timer(item) DELAY 9',routines=routine);self.assertEqual(p.run()['ITEM']['TICKS'],5)
    def test_byname_borrows_same_cell(self):
        p,_,_=build("CONNECT TIMER TO n DELAY 5 stop_timer(BYNAME('','N',s)) DELAY 9");self.assertEqual(p.run()['N'],5)
    def test_forwarded_formal_can_control_caller(self):
        routine=STOP+' ROUTINE work(value:INTEGER) BEGIN stop_timer(value) END work'
        p,_,_=build('CONNECT TIMER TO n DELAY 5 work(n) DELAY 9',routines=routine);self.assertEqual(p.run()['N'],5)
    def test_nested_alias_names_are_one_registration(self):
        routine='ROUTINE stop_timer(first,second:INTEGER) BEGIN DISCONNECT TIMER second result=first END stop_timer'
        p,_,_=build('CONNECT TIMER TO n DELAY 5 stop_timer(n,n) DELAY 9',routines=routine);v=p.run();self.assertEqual((v['N'],v['RESULT']),(5,5))
    def test_selector_is_evaluated_once(self):
        routine='ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN index_value END pick ROUTINE stop_timer(value:ARRAY OF INTEGER) BEGIN DISCONNECT TIMER value[pick()] index_value=1 END stop_timer'
        p,_,_=build('visits=0 index_value=2 CONNECT TIMER TO a[2] DELAY 5 stop_timer(a) DELAY 9',routines=routine);v=p.run();self.assertEqual((v['A'][1],v['VISITS']),(5,1))
    def test_other_connection_keeps_running(self):
        p,_,_=build('CONNECT TIMER TO n CONNECT TIMER TO m DELAY 5 stop_timer(n) DELAY 9 result=m');v=p.run();self.assertEqual((v['N'],v['M'],v['RESULT']),(5,14,14))
    def test_grouped_scalar_cannot_control_caller_connection(self):
        p,_,_=build('n=7 CONNECT TIMER TO n stop_timer((n))')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not connected'):p.run()
        self.assertEqual(p.snapshot()['N'],7)
    def test_grouped_record_cannot_control_caller_connection(self):
        p,_,_=build('CONNECT TIMER TO item.ticks stop_timer((item))',routines='ROUTINE stop_timer(value:row_t) BEGIN DISCONNECT TIMER value.ticks END stop_timer')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not connected'):p.run()
    def test_grouped_array_cannot_control_caller_connection(self):
        p,_,_=build('CONNECT TIMER TO a[2] stop_timer((a))',routines='ROUTINE stop_timer(value:ARRAY OF INTEGER) BEGIN DISCONNECT TIMER value[2] END stop_timer')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not connected'):p.run()
    def test_duplicate_connect_remains_rejected(self):
        p,_,_=build('CONNECT TIMER TO n connect_again(n)',routines='ROUTINE connect_again(value:INTEGER) BEGIN CONNECT TIMER TO value END connect_again')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'already connected'):p.run()
    def test_disconnect_twice_is_explicit_error(self):
        p,_,_=build('CONNECT TIMER TO n stop_timer(n) stop_timer(n)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not connected'):p.run()
    def test_dispatcher_and_cooperative_engines(self):
        for label,coop in (('',False),('start:: ',False),('',True)):
            p,_,_=build(label+'CONNECT TIMER TO n DELAY 5 stop_timer(n) DELAY 9',cooperative=coop);self.assertEqual(p.run()['N'],5)
    def test_created_named_storage_preserves_endpoint(self):
        routine='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value DELAY 5 stop_timer(value) result=value END work '+STOP
        p,_,_=build("CREATE_VAR('CACHE','VALUE','T','INTEGER',0,0,0,0,s) work(BYNAME('CACHE','VALUE',s))",routines=routine);self.assertEqual(p.run()['RESULT'],5)
    def test_created_rename_does_not_retarget_timer(self):
        routine='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value RENAME_VAR(\'CACHE\',\'VALUE\',\'RENAMED\',s) DELAY 5 stop_timer(value) result=value END work '+STOP
        p,_,_=build("CREATE_VAR('CACHE','VALUE','T','INTEGER',0,0,0,0,s) work(BYNAME('CACHE','VALUE',s))",routines=routine);self.assertEqual(p.run()['RESULT'],5)

class TimerControlLifetimeTests(unittest.TestCase):
    def test_ancestor_local_timer_can_be_disconnected(self):
        routine=STOP+' ROUTINE work VAR local_value:INTEGER BEGIN CONNECT TIMER TO local_value DELAY 5 stop_timer(local_value) DELAY 9 result=local_value END work'
        p,_,_=build('work()',routines=routine);self.assertEqual(p.run()['RESULT'],5);self.assertEqual(claims(p),{})
    def test_private_using_invocation_timer_can_be_disconnected(self):
        p,_,_=build('USING make() DO CONNECT TIMER TO ticks DELAY 5 stop_timer(ticks) DELAY 9 result=ticks ENDUSING',routines=STOP+' ROUTINE make:row_t BEGIN RETURN item END make');self.assertEqual(p.run()['RESULT'],5);self.assertEqual(p.snapshot()['ITEM']['TICKS'],{'uninitialized':True})
    def test_outer_formal_connection_is_controlled_by_inner_frame(self):
        routine=STOP+' ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value DELAY 5 stop_timer(value) DELAY 9 result=value END work'
        p,_,_=build('work(n)',routines=routine);self.assertEqual((p.run()['N'],p.snapshot()['RESULT']),(5,5))
    def test_defining_frame_cleanup_does_not_remove_reconnected_root_timer(self):
        routine=STOP+' ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value stop_timer(value) END work'
        p,_,_=build('work(n) CONNECT TIMER TO n DELAY 5 result=n',routines=routine);self.assertEqual(p.run()['RESULT'],5)
    def test_callee_disconnect_then_failure_keeps_completed_effect(self):
        routine='ROUTINE stop_timer(value:INTEGER) BEGIN DISCONNECT TIMER value s=1 DIV 0 END stop_timer'
        p,_,_=build('CONNECT TIMER TO n DELAY 5 stop_timer(n)',routines=routine)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],5);self.assertEqual(claims(p),{})
    def test_pause_retains_caller_connection_until_resume(self):
        routine='ROUTINE stop_timer(value:INTEGER) BEGIN PAUSE DISCONNECT TIMER value END stop_timer'
        p,_,now=build('CONNECT TIMER TO n stop_timer(n) DELAY 9',routines=routine)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(len(claims(p)),1);now[0]=5000;p.resume();self.assertEqual(p.snapshot()['N'],5);self.assertEqual(claims(p),{})
    def test_stop_releases_owned_timer_while_helper_paused(self):
        routine='ROUTINE stop_timer(value:INTEGER) BEGIN PAUSE DISCONNECT TIMER value END stop_timer'
        p,_,_=build('CONNECT TIMER TO n stop_timer(n)',routines=routine)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(claims(p),{})
    def test_retained_dead_handler_cannot_disconnect_live_root(self):
        routine='ROUTINE work(value:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO DISCONNECT TIMER value ENDCONDITION END work'
        p,_,_=build('work(n) CONNECT TIMER TO n ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'active routine frame'):p.run()
    def test_fresh_helper_from_retained_handler_can_control_root(self):
        routine=STOP+' ROUTINE work(value:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO stop_timer(value) ENDCONDITION END work'
        p,_,_=build('work(n) CONNECT TIMER TO n DELAY 5 ENABLE CONDITION[1] SIGNAL EVENT[1] DELAY 9',routines=routine);self.assertEqual(p.run()['N'],5)
    def test_connect_through_formal_still_ends_at_return(self):
        routine='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value END work'
        p,_,_=build('work(n) DELAY 5 result=n',routines=routine);self.assertEqual(p.run()['RESULT'],0)
    def test_json_still_omits_connections(self):
        p,_,_=build('CONNECT TIMER TO n stop_timer(n)');p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertNotIn('timers',saved);self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

class TimerControlClaimTests(unittest.TestCase):
    def test_same_task_cross_bank_disconnect(self):
        ctx,a,b,ref=banks()
        with rt._numeric_scope('pythonic'):rt.disconnect_timer(b,ref,13)
        self.assertEqual((ctx._timer_claims,a._timers,b._timers),({},{},{}));self.assertEqual(ref.raw(),0)
    def test_cross_bank_control_does_not_sample_clock(self):
        ctx,a,b,ref=banks();a._clock_us=lambda:self.fail('clock sampled');b._clock_us=lambda:self.fail('clock sampled')
        with rt._numeric_scope('pythonic'):rt.disconnect_timer(b,ref,13)
        self.assertEqual(ctx._timer_claims,{})
    def test_same_name_different_task_is_rejected(self):
        ctx,a,b,ref=banks();b._budget_parent=None;a.program_name=b.program_name='SAME'
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'another task'):rt.disconnect_timer(b,ref,13)
        self.assertEqual(len(ctx._timer_claims),1);a.finish_timers()
    def test_other_context_cannot_control_claim(self):
        ctx,a,b,ref=banks();other=rt.ExecutionContext();b.execution=other;other._timer_claims=dict(ctx._timer_claims)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'execution context'):rt.disconnect_timer(b,ref,13)
        self.assertEqual(len(ctx._timer_claims),1);a.finish_timers()
    def test_missing_owner_record_leaves_reserved_claim(self):
        ctx,a,b,ref=banks();key=next(iter(ctx._timer_claims));claim=ctx._timer_claims[key];a._timers.clear()
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'reserved'):rt.disconnect_timer(b,ref,13)
        self.assertIs(ctx._timer_claims[key],claim)
    def test_replaced_owner_record_leaves_reserved_claim(self):
        ctx,a,b,ref=banks();key=next(iter(ctx._timer_claims));claim=ctx._timer_claims[key];a._timers[key]=[ref,0,0]
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'registration changed'):rt.disconnect_timer(b,ref,13)
        self.assertIs(ctx._timer_claims[key],claim);a.finish_timers();self.assertIs(ctx._timer_claims[key],claim)
    def test_changed_registered_reference_is_rejected(self):
        ctx,a,b,ref=banks();old=ref.storage;ref.storage={'N':0}
        original=rt.Reference(rt.INTEGER,old,'N')
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'reference changed'):rt.disconnect_timer(b,original,13)
        self.assertEqual(len(ctx._timer_claims),1);a.finish_timers()
    def test_malformed_shared_claim_is_preserved(self):
        ctx,a,b,ref=banks();key=next(iter(ctx._timer_claims));claim=(a,);ctx._timer_claims[key]=claim
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'not connected'):rt.disconnect_timer(b,ref,13)
        self.assertIs(ctx._timer_claims[key],claim);a.finish_timers()
    def test_changed_ownership_metadata_is_preserved(self):
        ctx,a,b,ref=banks();key=next(iter(ctx._timer_claims));record=a._timers[key];ctx._timer_claims[key]=(b,record,ref.storage,ref.key)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'registration changed'):rt.disconnect_timer(b,ref,13)
        self.assertEqual(len(ctx._timer_claims),1);a.finish_timers()
    def test_boolean_key_cannot_alias_registered_integer_key(self):
        ctx,a,b,ref=banks();a.finish_timers();storage=[0];ref=rt.Reference(rt.INTEGER,storage,0)
        with rt._numeric_scope('pythonic'):rt.connect_timer(a,ref,11)
        alias=rt.Reference(rt.INTEGER,storage,False)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'registered endpoint'):rt.disconnect_timer(b,alias,13)
        self.assertEqual(len(ctx._timer_claims),1);a.finish_timers()
    def test_readonly_alias_is_rejected(self):
        ctx,a,b,ref=banks();alias=rt.ReadOnlyFieldReference(rt.INTEGER,ref.storage,ref.key)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'ordinary INTEGER'):rt.disconnect_timer(b,alias,13)
        self.assertEqual(len(ctx._timer_claims),1);a.finish_timers()
    def test_inactive_owner_frame_claim_stays_reserved(self):
        ctx,a,b,ref=banks();key=next(iter(ctx._timer_claims));record=a._timers[key];a._frame_timers[key]=({},record)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'inactive'):rt.disconnect_timer(b,ref,13)
        self.assertEqual(len(ctx._timer_claims),1);a.finish_timers()
    def test_replaced_owner_frame_record_stays_reserved(self):
        for malformed in (None,False,(),({},[None,0,0])):
            ctx,a,b,ref=banks();key=next(iter(ctx._timer_claims));a._frame_timers[key]=malformed
            with self.subTest(binding=malformed),rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'registration changed'):rt.disconnect_timer(b,ref,13)
            self.assertEqual(len(ctx._timer_claims),1);a.finish_timers()
    def test_formal_control_requires_live_callee_frame(self):
        ctx,a,b,ref=banks()
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'active routine frame'):rt.disconnect_timer(b,ref,13,scoped=True)
        self.assertEqual(len(ctx._timer_claims),1);a.finish_timers()
    def test_success_does_not_move_record_to_helper(self):
        ctx,a,b,ref=banks()
        with rt._numeric_scope('pythonic'):rt.disconnect_timer(b,ref,13)
        self.assertEqual((a._frame_timers,b._frame_timers),({},{}));self.assertEqual(ref.raw(),0)

class TimerControlProjectTests(unittest.TestCase):
    def project(self,body='CONNECT TIMER TO n DELAY 5 stop_timer(n) DELAY 9',libbody='DISCONNECT TIMER value',*,shared=False):
        main=source('MAIN',body,decl='n,s:INTEGER',routines='ROUTINE stop_timer(value:INTEGER) FROM LIB');lib=source('LIB','',routines='ROUTINE stop_timer(value:INTEGER) BEGIN '+libbody+' END stop_timer')
        return translate_project({'main':main,'lib':lib}).instantiate()
    def test_linked_helper_stops_calling_task_timer(self):
        project=self.project();v=project.run('MAIN');self.assertGreaterEqual(v['MAIN']['values']['N'],5);self.assertLess(v['MAIN']['values']['N'],14);self.assertEqual(project.context._timer_claims,{})
    def test_linked_helper_cannot_duplicate_caller_connection(self):
        project=self.project(libbody='CONNECT TIMER TO value')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'already connected'):project.run('MAIN')
    def test_linked_nested_formal_chain(self):
        main=source('MAIN','CONNECT TIMER TO n DELAY 5 outer(n) DELAY 9',decl='n:INTEGER',routines='ROUTINE outer(value:INTEGER) FROM LIB')
        lib=source('LIB','',routines='ROUTINE inner(value:INTEGER) FROM CHILD ROUTINE outer(value:INTEGER) BEGIN inner(value) END outer')
        child=source('CHILD','',routines=STOP.replace('stop_timer','inner'))
        project=translate_project({'main':main,'lib':lib,'child':child}).instantiate();v=project.run('MAIN');self.assertGreaterEqual(v['MAIN']['values']['N'],5);self.assertEqual(project.context._timer_claims,{})
    def test_library_ancestor_local_timer(self):
        main=source('MAIN','work()',routines='ROUTINE work FROM LIB')
        lib=source('LIB','',decl='result:INTEGER',routines='ROUTINE stop_timer(value:INTEGER) FROM CHILD ROUTINE work VAR value:INTEGER BEGIN CONNECT TIMER TO value DELAY 5 stop_timer(value) DELAY 9 result=value END work')
        child=source('CHILD','',routines=STOP);project=translate_project({'main':main,'lib':lib,'child':child}).instantiate();v=project.run('MAIN');self.assertGreaterEqual(v['LIB']['values']['RESULT'],5);self.assertEqual(project.context._timer_claims,{})
    def test_project_pause_and_resume(self):
        project=self.project(libbody='PAUSE DISCONNECT TIMER value');project.run('MAIN');self.assertEqual(len(project.context._timer_claims),1);project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(project.context._timer_claims,{})
    def test_project_stop_during_helper_keeps_cleanup_owned(self):
        project=self.project(libbody='PAUSE DISCONNECT TIMER value');project.run('MAIN');project.scheduler.stop('MAIN');self.assertEqual(project.context._timer_claims,{})
    def test_project_shared_context_other_task_control_rejects(self):
        ctx,a,b,ref=banks();b._budget_parent=None
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.disconnect_timer(b,ref,13)
        a.finish_timers()

class TimerControlEffectTests(unittest.TestCase):
    def test_active_scalar_counter_remains_guarded(self):
        with self.assertRaises(TranslationError):build('FOR n=1 TO 3 DO stop_timer(n) ENDFOR')
    def test_active_array_counter_remains_guarded(self):
        with self.assertRaises(TranslationError):build('FOR a[1]=1 TO 3 DO stop_timer(a[1]) ENDFOR')
    def test_connect_formal_lifetime_is_unchanged(self):
        p,_,_=build('work(n) DELAY 5 result=n',routines='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value END work');self.assertEqual(p.run()['RESULT'],0)
    def test_wrong_formal_domains_remain_rejected(self):
        for spec in ('SHORT','BYTE','REAL','BOOLEAN'):
            with self.subTest(spec=spec),self.assertRaises(TranslationError):build('',routines='ROUTINE stop_timer(value:'+spec+') BEGIN DISCONNECT TIMER value END stop_timer')

class TimerControlAdditionalTests(unittest.TestCase):
    def test_byname_row_prefix_controls_original_array_cell(self):
        routine='ROUTINE stop_timer(value:ARRAY OF INTEGER) BEGIN DISCONNECT TIMER value[1] END stop_timer'
        p,_,_=build("CONNECT TIMER TO values[2,1] DELAY 5 stop_timer(BYNAME('','VALUES[2]',s)) DELAY 9",decl=DECL+' values:ARRAY[2,2]OF INTEGER',routines=routine);self.assertEqual(p.run()['VALUES'][1][0],5)
    def test_computed_scalar_cannot_control_caller_timer(self):
        p,_,_=build('n=7 CONNECT TIMER TO n stop_timer(n+0)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not connected'):p.run()
        self.assertEqual(p.snapshot()['N'],7)
    def test_promoted_scalar_does_not_control_another_cell(self):
        p,_,_=build('small=7 CONNECT TIMER TO n stop_timer(small)',decl=DECL+' small:SHORT')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not connected'):p.run()
        self.assertEqual(p.snapshot()['N'],0)
    def test_helper_can_explicitly_reconnect_under_its_own_frame(self):
        routine='ROUTINE work(value:INTEGER) BEGIN DISCONNECT TIMER value CONNECT TIMER TO value END work'
        p,_,_=build('CONNECT TIMER TO n DELAY 5 work(n) DELAY 9 result=n',routines=routine);self.assertEqual(p.run()['RESULT'],5);self.assertEqual(claims(p),{})
    def test_private_argument_timer_does_not_disconnect_caller(self):
        routine='ROUTINE work(value:INTEGER) BEGIN CONNECT TIMER TO value DISCONNECT TIMER value END work'
        p,_,_=build('n=7 CONNECT TIMER TO n work((n)) DELAY 5 result=n',routines=routine);self.assertEqual(p.run()['RESULT'],12)
    def test_null_record_reservation_fails_closed(self):
        ctx,a,b,ref=banks();key=next(iter(ctx._timer_claims));a._timers.clear();claim=(a,None,ref.storage,ref.key);ctx._timer_claims[key]=claim
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'reserved'):rt.disconnect_timer(b,ref,13)
        self.assertIs(ctx._timer_claims[key],claim)
    def test_invalid_owner_in_shared_claim_fails_closed(self):
        ctx,a,b,ref=banks();key=next(iter(ctx._timer_claims));claim=(object(),a._timers[key],ref.storage,ref.key);ctx._timer_claims[key]=claim
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'another task'):rt.disconnect_timer(b,ref,13)
        self.assertIs(ctx._timer_claims[key],claim);a.finish_timers()
    def test_cross_bank_control_preserves_unrelated_timer(self):
        ctx,a,b,ref=banks();other=rt.Reference(rt.INTEGER,{'OTHER':rt.UNINITIALIZED},'OTHER')
        with rt._numeric_scope('pythonic'):rt.connect_timer(a,other,11);rt.disconnect_timer(b,ref,13)
        self.assertEqual(len(ctx._timer_claims),1);self.assertEqual(other.raw(),0);a.finish_timers()
    def test_imported_global_storage_remains_same_endpoint(self):
        main='PROGRAM MAIN VAR n FROM STORAGE:INTEGER ROUTINE stop_timer(value:INTEGER) FROM LIB BEGIN CONNECT TIMER TO n DELAY 5 stop_timer(n) DELAY 9 END MAIN'
        lib=source('LIB','',routines=STOP);storage=source('STORAGE','',decl='n:INTEGER');project=translate_project({'main':main,'lib':lib,'storage':storage}).instantiate();v=project.run('MAIN');self.assertEqual(v['MAIN']['values']['N'],v['STORAGE']['values']['N']);self.assertEqual(project.context._timer_claims,{})
    def test_global_handler_can_delegate_control_to_fresh_helper(self):
        p,_,_=build('CONNECT TIMER TO n CONDITION[1]: WHEN EVENT[1] DO stop_timer(n) ENDCONDITION DELAY 5 ENABLE CONDITION[1] SIGNAL EVENT[1] DELAY 9');self.assertEqual(p.run()['N'],5)

class TimerControlReportTests(unittest.TestCase):
    def test_disconnect_report_records_actual_claim_control(self):
        _,r,_=build();rows=r.report['connected_timers'];self.assertEqual(next(row for row in rows if row['operation']=='DISCONNECT')['control_scope'],'same_task_existing_claim')
    def test_report_keeps_connection_lifetime_boundary(self):
        _,r,_=build();policy=r.report['timer_control_policy'];self.assertEqual(policy['guide'],'docs/timer-control.md');self.assertFalse(policy['controller_validated']);self.assertIn('frame lifetime',policy['lifetime'])
    def test_invalid_scope_flags_do_not_release_claim(self):
        ctx,a,b,ref=banks()
        for flag in (1,None,'yes'):
            with self.subTest(flag=flag),rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'scope flag'):rt.disconnect_timer(b,ref,13,scoped=flag)
        self.assertEqual(len(ctx._timer_claims),1);a.finish_timers()
