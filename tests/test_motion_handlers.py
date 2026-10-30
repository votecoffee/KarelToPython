"""Authored local motion clauses, explicit progress and cooperative lifetime checks."""
from copy import deepcopy
import json
import unittest

from karel2py import runtime as rt, translate, translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_motion_requests import context, DECL, SETUP
from tests.test_project_scheduler import source


def scripted(delay=25, *, completed=True, **options):
    return context(capture_only=False, responses=[dict(operation='MOVE AWAY',completed=completed,delay_ms=delay)],**options)


def program(body, *, ctx=None, setup=SETUP, decl=DECL, routines='', prefix='', sleep=None, **options):
    ctx=ctx or context()
    pauses=[]
    p,result=compile_program(setup+body,decl=decl,routines=routines,prefix=prefix,
        context=ctx,sleep=sleep or pauses.append,joint_axes=2,**options)
    return p,ctx,result,pauses


def execute(body, **options):
    p,ctx,result,pauses=program(body,**options)
    return p.run(),ctx,p,result,pauses


def move(ctx):
    return next(row for row in reversed(ctx.motion.history) if row['operation'].startswith('MOVE '))


class LocalMotionClauseTests(unittest.TestCase):
    def test_independent_when_blocks_fire_once_in_source_order(self):
        values,ctx,p,result,_=execute('''n=0 ATTACH MOVE AWAY 1,
WHEN TRUE DO n=n+1
WHEN n=1 DO n=n+10
UNTIL FALSE
ENDMOVE n=n+100''')
        self.assertEqual(values['N'],111)
        self.assertEqual(move(ctx)['outcome'],'captured')
        self.assertEqual(move(ctx)['data']['execution']['triggered'],[1,2])
        self.assertEqual(len(result.report['motion_requests'][1]['local_handlers']),3)
        self.assertEqual(ctx.motion._active,{})
        self.assertFalse(p._state._in_handler)

    def test_until_cancels_before_then_actions_and_continues_source(self):
        values,ctx,_,_,_=execute('n=0 ATTACH MOVE TO p, UNTIL TRUE THEN n=5 ENDMOVE n=n+1')
        self.assertEqual(values['N'],6)
        self.assertEqual(move(ctx)['outcome'],'cancelled')
        self.assertEqual([row['operation'] for row in ctx.motion.history],['ATTACH','MOVE TO','CANCEL'])
        self.assertEqual(ctx.motion.history[-1]['data']['states'][0]['after'],dict(motion='idle',held=False))
        self.assertEqual(ctx.group_locks.motion,{})

    def test_until_without_then_is_an_implicit_cancel(self):
        _,ctx,_,_,_=execute('ATTACH MOVE AWAY 1, UNTIL TRUE ENDMOVE')
        self.assertEqual(move(ctx)['outcome'],'cancelled')
        self.assertEqual(move(ctx)['data']['execution']['triggered'],[1])

    def test_cancel_stops_later_local_clauses_but_finishes_current_actions(self):
        values,ctx,_,_,_=execute('''n=0 ATTACH MOVE AWAY 1,
WHEN TRUE DO CANCEL n=n+1
WHEN TRUE DO n=99
ENDMOVE''')
        self.assertEqual(values['N'],1)
        self.assertEqual(move(ctx)['data']['execution']['triggered'],[1])

    def test_false_clause_has_no_action_or_cancel(self):
        values,ctx,_,_,_=execute('n=0 ATTACH MOVE AWAY 1, WHEN FALSE DO n=99 UNTIL FALSE ENDMOVE')
        self.assertEqual(values['N'],0)
        self.assertEqual(move(ctx)['outcome'],'captured')
        self.assertEqual(move(ctx)['data']['execution']['triggered'],[])

    def test_exactly_32_one_shot_clauses_are_supported(self):
        _,ctx,_,_,_=execute('ATTACH MOVE AWAY 1, '+('WHEN FALSE DO n=1\n'*32)+'ENDMOVE')
        self.assertEqual(len(move(ctx)['data']['execution']['handlers']),32)
        self.assertEqual(move(ctx)['data']['execution']['triggered'],[])

    def test_eval_is_frozen_at_definition_after_operand_capture(self):
        routines='ROUTINE target:XYZWPR BEGIN n=2 RETURN p END target'
        values,ctx,_,_,_=execute('n=1 ATTACH MOVE TO target(), WHEN n=EVAL(n) DO n=3 ENDMOVE',routines=routines)
        self.assertEqual(values['N'],3)
        self.assertEqual(move(ctx)['data']['target']['value']['X'],10.)

    def test_routine_local_parameters_and_values_remain_live_until_completion(self):
        routines='''ROUTINE work(value:INTEGER):INTEGER
VAR local:INTEGER
BEGIN local=value MOVE AWAY 1, WHEN local=value DO local=local+1 ENDMOVE RETURN local END work'''
        values,ctx,p,_,_=execute('ATTACH n=work(4) s=work(8)',routines=routines)
        self.assertEqual((values['N'],values['S']),(5,9))
        self.assertEqual(p._state.local_frames,[])
        self.assertEqual(ctx.motion._local_actions,{})

    def test_using_selector_keeps_the_captured_reference(self):
        values,_,_,_,_=execute('rec.value=2 ATTACH USING rec DO MOVE AWAY 1, WHEN value=2 DO value=3 ENDMOVE ENDUSING n=rec.value',
            setup='',decl='rec:row_t n:INTEGER',prefix='TYPE row_t=STRUCTURE value:INTEGER ENDSTRUCTURE')
        self.assertEqual(values['N'],3)

    def test_source_repeat_until_after_plain_move_is_not_a_local_clause(self):
        values,ctx,_,_,_=execute('n=0 ATTACH REPEAT\nMOVE AWAY 1\nn=n+1\nUNTIL n=1')
        self.assertEqual(values['N'],1)
        self.assertNotIn('execution',move(ctx)['data'])

    def test_all_seven_forms_accept_local_clauses(self):
        ctx_factory=lambda:context()
        for body in ('MOVE TO p','MOVE NEAR p BY 1','MOVE AWAY 1','MOVE ABOUT v BY 1',
                     'MOVE AXIS 1 BY 1','MOVE RELATIVE v','MOVE ALONG route'):
            with self.subTest(body=body):
                values,ctx,_,_,_=execute('APPEND_NODE(route,s) route[1].node_pos=p n=0 ATTACH '+body+', WHEN TRUE DO n=1 ENDMOVE',ctx=ctx_factory())
                self.assertEqual(values['N'],1)
                self.assertEqual(move(ctx)['data']['execution']['triggered'],[1])

    def test_with_settings_and_local_clause_share_one_private_target(self):
        values,ctx,_,_,_=execute('ATTACH WITH $SPEED=20 MOVE TO p, WHEN TRUE DO p.x=99 ENDMOVE')
        self.assertEqual(values['P']['X'],99.)
        self.assertEqual(move(ctx)['data']['target']['value']['X'],10.)
        self.assertEqual(move(ctx)['data']['settings'],[dict(name='$SPEED',group=1,value=20.)])

    def test_local_bare_cancel_targets_only_current_group(self):
        ctx=context(groups={1:2,2:2});ctx.group_locks=rt.GroupLocks([1,2],motion={2:'executing'})
        execute('LOCK_GROUP(3,s) MOVE AWAY 1, WHEN TRUE DO CANCEL ENDMOVE',ctx=ctx)
        self.assertEqual(ctx.motion.history[-1]['data']['groups'],[1])
        self.assertEqual(ctx.group_locks.motion,{2:'executing'})

    def test_local_bare_hold_and_unhold_are_scoped_to_current_group(self):
        ctx=context(groups={1:2,2:2})
        _,ctx,_,_,_=execute('ATTACH MOVE AWAY 1, WHEN TRUE DO HOLD UNHOLD ENDMOVE',ctx=ctx)
        self.assertEqual([row['data']['groups'] for row in ctx.motion.history if row['operation'] in ('HOLD','UNHOLD')],[[1],[1]])


class ScriptedMotionProgressTests(unittest.TestCase):
    def test_explicit_delay_has_bounded_steps_and_complete_progress(self):
        _,ctx,_,_,pauses=execute('ATTACH MOVE AWAY 1',ctx=scripted(25))
        self.assertEqual(pauses,[.01,.01,.005])
        self.assertEqual(move(ctx)['outcome'],'completed')
        self.assertEqual(move(ctx)['data']['execution'],dict(delay_ms=25,elapsed_ms=25,handlers=[],triggered=[]))
        self.assertEqual(ctx.motion.responses,[])

    def test_zero_delay_without_handlers_preserves_old_payload(self):
        _,ctx,_,_,pauses=execute('ATTACH MOVE AWAY 1',ctx=scripted(0))
        self.assertEqual(pauses,[])
        self.assertEqual(move(ctx)['data'],dict(distance=1.))

    def test_input_edge_is_observed_once_during_supplied_progress(self):
        ctx=scripted(35);ctx.ports=rt.PortBank({'DIN':1},{('DIN',1):False});pauses=[]
        def sleep(seconds):
            pauses.append(seconds);ctx.ports.update('DIN',1,True)
        values,ctx,p,_,_=execute('n=0 ATTACH MOVE AWAY 1, WHEN DIN[1]+ DO n=n+1 ENDMOVE',ctx=ctx,sleep=sleep)
        self.assertEqual(values['N'],1)
        self.assertEqual(move(ctx)['data']['execution']['triggered'],[1])
        self.assertEqual(pauses,[.01,.01,.01,.005])
        self.assertEqual(p._state._edge_history,{})

    def test_predicate_function_is_polled_until_its_one_shot_trigger(self):
        routines='ROUTINE ready:BOOLEAN BEGIN n=n+1 RETURN n>=3 END ready'
        values,ctx,_,_,_=execute('n=0 s=0 ATTACH MOVE AWAY 1, WHEN ready() DO s=1 ENDMOVE',ctx=scripted(30),routines=routines)
        self.assertEqual((values['N'],values['S']),(3,1))
        self.assertEqual(move(ctx)['data']['execution']['elapsed_ms'],30)

    def test_until_connected_timer_cancels_before_full_supplied_delay(self):
        now=[0]
        def sleep(seconds):now[0]+=round(seconds*1000000)
        values,ctx,_,_,_=execute('n=0 ticks=0 CONNECT TIMER TO ticks ATTACH MOVE AWAY 1, UNTIL ticks>=20 THEN n=ticks ENDMOVE',
            decl=DECL+' ticks:INTEGER',ctx=scripted(1000),clock_us=lambda:now[0],sleep=sleep)
        self.assertEqual(values['N'],20)
        self.assertEqual(move(ctx)['outcome'],'cancelled')
        self.assertEqual(move(ctx)['data']['execution']['elapsed_ms'],20)

    def test_global_and_local_event_cursors_do_not_consume_each_other(self):
        ctx=scripted(20);signalled=[False]
        def sleep(_):
            if not signalled[0]:ctx.events.signal(1);signalled[0]=True
        values,ctx,p,_,_=execute('''n=0
CONDITION[1]: WHEN EVENT[1] DO n=n+10 ENDCONDITION
ENABLE CONDITION[1] ATTACH MOVE AWAY 1, WHEN EVENT[1] DO n=n+1 ENDMOVE''',ctx=ctx,sleep=sleep)
        self.assertEqual(values['N'],11)
        self.assertTrue(all(type(key[0]) is not tuple for key in p._state._event_seen))

    def test_global_and_local_error_cursors_are_independent_and_error_state_restores(self):
        ctx=scripted(20);ctx.errors=rt.ErrorHistory();posted=[False]
        def sleep(_):
            if not posted[0]:ctx.errors.post(7,'supplied fault');posted[0]=True
        values,ctx,p,_,_=execute('''n=0
CONDITION[1]: WHEN ERROR[7] DO n=n+10 ENDCONDITION
ENABLE CONDITION[1] ATTACH MOVE AWAY 1, WHEN ERROR[7] DO n=n+1 ENDMOVE''',ctx=ctx,sleep=sleep)
        self.assertEqual(values['N'],11)
        self.assertIsNone(p._state._current_error)
        self.assertTrue(all(type(key[0]) is not tuple for key in p._state._event_seen))

    def test_global_cancel_finishes_before_local_action_scan(self):
        ctx=scripted(20);ctx.ports=rt.PortBank({'DIN':1},{('DIN',1):False})
        def sleep(_):ctx.ports.update('DIN',1,True)
        values,ctx,_,_,_=execute('''n=0
CONDITION[1]: WHEN DIN[1] DO CANCEL ENDCONDITION ENABLE CONDITION[1]
ATTACH MOVE AWAY 1, WHEN DIN[1] DO n=99 ENDMOVE''',ctx=ctx,sleep=sleep)
        self.assertEqual(values['N'],0)
        self.assertEqual(move(ctx)['outcome'],'cancelled')
        self.assertEqual(move(ctx)['data']['execution']['triggered'],[])

    def test_active_hold_pauses_progress_and_local_scans_until_global_unhold(self):
        ctx=scripted(20);ctx.ports=rt.PortBank({'DIN':1},{('DIN',1):False});observations=[]
        def sleep(seconds):
            observations.append((seconds,bool(ctx.group_locks.held)))
            ctx.ports.update('DIN',1,True)
        values,ctx,_,_,_=execute('''n=0
CONDITION[1]: WHEN DIN[1] DO UNHOLD ENDCONDITION ENABLE CONDITION[1]
ATTACH MOVE AWAY 1,
WHEN TRUE DO HOLD
WHEN TRUE DO n=n+1
ENDMOVE''',ctx=ctx,sleep=sleep)
        self.assertEqual(observations,[(.01,True),(.01,False),(.01,False)])
        self.assertEqual(values['N'],1)
        self.assertEqual(move(ctx)['data']['execution']['elapsed_ms'],20)
        self.assertEqual(ctx.group_locks.held,set())

    def test_handler_delay_is_not_counted_as_scripted_motion_progress(self):
        _,ctx,_,_,pauses=execute('ATTACH MOVE AWAY 1, WHEN TRUE DO DELAY 7 ENDMOVE',ctx=scripted(10))
        self.assertEqual(pauses,[.007,.01])
        self.assertEqual(move(ctx)['data']['execution']['elapsed_ms'],10)

    def test_false_scripted_completion_runs_no_actions_or_delay(self):
        p,ctx,_,pauses=program('n=0 ATTACH MOVE AWAY 1, WHEN TRUE DO n=99 ENDMOVE',ctx=scripted(25,completed=False))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'completion rejected'):p.run()
        self.assertEqual(p.snapshot()['N'],0)
        self.assertEqual(pauses,[])
        self.assertEqual(move(ctx)['outcome'],'rejected')
        self.assertEqual(move(ctx)['data']['execution']['triggered'],[])
        self.assertEqual(ctx.motion._active,{})

    def test_delayed_nowait_fails_without_consuming_response(self):
        p,ctx,_,pauses=program('ATTACH MOVE AWAY 1 NOWAIT',ctx=scripted(20))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'NOWAIT'):p.run()
        self.assertEqual(len(ctx.motion.responses),1)
        self.assertEqual([row['operation'] for row in ctx.motion.history],['ATTACH'])
        self.assertEqual(pauses,[])

    def test_uninitialized_target_precedes_scope_and_reply_consumption(self):
        ctx=context(capture_only=False,responses=[dict(operation='MOVE TO',completed=True,delay_ms=10)])
        p,_,_,_=program('ATTACH MOVE TO p, WHEN TRUE DO n=99 ENDMOVE',ctx=ctx,setup='')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(len(ctx.motion.responses),1)
        self.assertEqual(ctx.motion._active,{})


class MotionScopeLifetimeTests(unittest.TestCase):
    def test_source_pause_retains_local_scope_and_resumes_remaining_actions(self):
        p,ctx,_,_=program('n=0 ATTACH MOVE AWAY 1, WHEN TRUE DO n=1 PAUSE n=2 ENDMOVE n=n+1')
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['N'],1)
        self.assertEqual(move(ctx)['outcome'],'pending')
        self.assertEqual(ctx.group_locks.motion,{1:'executing'})
        with self.assertRaisesRegex(ValueError,'active motion'):ctx.motion.to_config()
        self.assertEqual(p.resume()['N'],3)
        self.assertEqual(move(ctx)['outcome'],'captured')
        self.assertEqual(ctx.motion._active,{})
        self.assertEqual(ctx.motion._local_actions,{})
        self.assertFalse(p._state._in_handler)

    def test_stop_of_paused_action_restores_flags_and_preserves_hold(self):
        p,ctx,_,_=program('n=0 ATTACH MOVE AWAY 1, WHEN TRUE DO HOLD n=1 PAUSE n=2 ENDMOVE')
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop()
        self.assertEqual(p.snapshot()['N'],1)
        self.assertEqual(move(ctx)['outcome'],'cancelled')
        self.assertEqual(ctx.group_locks.motion,{})
        self.assertEqual(ctx.group_locks.held,{1})
        self.assertEqual(ctx.motion._active,{})
        self.assertEqual(ctx.motion._local_actions,{})
        self.assertFalse(p._state._in_handler)
        rt.ExecutionContext.from_config(ctx.to_config())

    def test_stop_abort_and_failure_are_distinct_terminal_evidence(self):
        for action,error,outcome in [('STOP',rt.KarelStop,'cancelled'),('ABORT',rt.KarelAbort,'cancelled'),('n=1 DIV 0',rt.KarelRuntimeError,'failed')]:
            p,ctx,_,_=program('ATTACH MOVE AWAY 1, WHEN TRUE DO '+action+' ENDMOVE')
            with self.subTest(action=action),self.assertRaises(error):p.run()
            self.assertEqual(move(ctx)['outcome'],outcome)
            self.assertEqual(ctx.motion._active,{})
            self.assertEqual(ctx.group_locks.owners,{})
            self.assertFalse(p._state._in_handler)

    def test_until_then_failure_is_not_a_successful_motion(self):
        p,ctx,_,_=program('ATTACH MOVE AWAY 1, UNTIL TRUE THEN n=1 DIV 0 ENDMOVE')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(move(ctx)['outcome'],'failed')
        self.assertEqual(ctx.group_locks.motion,{})

    def test_budget_failure_during_progress_cleans_scope(self):
        p,ctx,_,_=program('ATTACH MOVE AWAY 1',ctx=scripted(100000))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=35)
        self.assertEqual(move(ctx)['outcome'],'failed')
        self.assertLess(move(ctx)['data']['execution']['elapsed_ms'],100000)
        self.assertEqual(ctx.motion._active,{})
        self.assertEqual(ctx.group_locks.motion,{})

    def test_budget_failure_in_indefinite_hold_preserves_hold_only(self):
        p,ctx,_,_=program('ATTACH MOVE AWAY 1, WHEN TRUE DO HOLD ENDMOVE')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=35)
        self.assertEqual(move(ctx)['outcome'],'failed')
        self.assertEqual(ctx.group_locks.held,{1})
        self.assertEqual(ctx.group_locks.motion,{})

    def test_source_unlock_observes_active_scope_as_busy(self):
        values,ctx,_,_,_=execute('ATTACH MOVE AWAY 1, WHEN TRUE DO UNLOCK_GROUP(1,s) n=s CANCEL ENDMOVE')
        self.assertEqual(values['N'],17039)
        self.assertEqual(move(ctx)['outcome'],'cancelled')

    def test_ownership_loss_does_not_modify_foreign_motion(self):
        ctx=scripted(20);foreign,_,_,_=program('',ctx=ctx,setup='')
        def sleep(_):
            ctx.group_locks.release_owner(p._state)
            ctx.group_locks._grant(1,foreign._state)
            ctx.group_locks.set_motion(1,'stopped')
        p,_,_,_=program('ATTACH MOVE AWAY 1',ctx=ctx,sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ownership grant'):p.run()
        self.assertEqual(ctx.group_locks.motion,{1:'stopped'})
        self.assertIs(ctx.group_locks.owners[1],foreign._state)
        self.assertEqual(ctx.motion._active,{})
        ctx.group_locks.release_owner(foreign._state)

    def test_external_stopped_label_is_preserved_without_false_completion(self):
        ctx=scripted(20)
        def sleep(_):ctx.group_locks.set_motion(1,'stopped')
        p,_,_,_=program('ATTACH MOVE AWAY 1',ctx=ctx,sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'work label'):p.run()
        self.assertEqual(move(ctx)['outcome'],'failed')
        self.assertEqual(ctx.group_locks.motion,{1:'stopped'})

    def test_action_callback_cannot_replace_ownership_and_then_report_completion(self):
        ctx=context();foreign,_,_,_=program('',ctx=ctx,setup='')
        def mutate():
            ctx.group_locks.release_owner(p._state)
            ctx.group_locks._grant(1,foreign._state)
            ctx.group_locks.set_motion(1,'stopped')
        ctx.externals['HOST','MUTATE']=mutate
        p,_,_,_=program('ATTACH MOVE AWAY 1, WHEN TRUE DO mutate() ENDMOVE',ctx=ctx,routines='ROUTINE mutate FROM HOST')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ownership grant'):p.run()
        self.assertEqual(move(ctx)['outcome'],'failed')
        self.assertEqual(ctx.group_locks.motion,{1:'stopped'})
        self.assertIs(ctx.group_locks.owners[1],foreign._state)
        ctx.group_locks.release_owner(foreign._state)

    def test_sequence_ring_can_evict_active_row_without_leaking_scope(self):
        values,ctx,_,_,_=execute('n=0 ATTACH MOVE AWAY 1, WHEN TRUE DO OPEN HAND 1 CLOSE HAND 1 n=1 ENDMOVE',ctx=context(limit=1))
        self.assertEqual(values['N'],1)
        self.assertEqual(len(ctx.motion.history),1)
        self.assertEqual(ctx.motion.history[0]['operation'],'CLOSE HAND')
        self.assertEqual(ctx.motion._active,{})
        rt.ExecutionContext.from_config(ctx.to_config())

    def test_nested_scope_from_handler_routine_fails_closed(self):
        routines='ROUTINE nested BEGIN MOVE AWAY 1, WHEN TRUE DO n=1 ENDMOVE END nested'
        p,ctx,_,_=program('ATTACH MOVE AWAY 1, WHEN TRUE DO nested() ENDMOVE',routines=routines)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(move(ctx)['outcome'],'failed')
        self.assertEqual(ctx.motion._active,{})


class LinkedMotionScopeTests(unittest.TestCase):
    def test_library_local_actions_keep_root_ownership_and_frame_values(self):
        ctx=context()
        library=source('LIB','',routines='ROUTINE work(value:INTEGER):INTEGER VAR local:INTEGER BEGIN local=value MOVE AWAY 1, WHEN TRUE DO local=local+1 ENDMOVE RETURN local END work')
        main=source('MAIN','ATTACH n=work(5)',routines='ROUTINE work(value:INTEGER):INTEGER FROM LIB')
        instance=translate_project({'main':main,'lib':library}).instantiate(context=ctx)
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['N'],6)
        self.assertEqual((move(ctx)['program'],move(ctx)['source_program']),('MAIN','LIB'))
        self.assertEqual(ctx.motion._active,{})

    def test_pause_and_stop_in_library_restore_parent_handler_flags(self):
        ctx=context()
        library=source('LIB','',routines='ROUTINE work BEGIN MOVE AWAY 1, WHEN TRUE DO PAUSE ENDMOVE END work')
        main=source('MAIN','ATTACH work()',routines='ROUTINE work FROM LIB')
        instance=translate_project({'main':main,'lib':library}).instantiate(context=ctx)
        self.assertEqual(instance.run('MAIN')['MAIN']['state'],'paused')
        self.assertTrue(instance.programs['MAIN']._state._in_handler)
        instance.scheduler.stop('MAIN')
        self.assertFalse(instance.programs['MAIN']._state._in_handler)
        self.assertEqual(ctx.motion._active,{})
        self.assertEqual(ctx.motion._local_actions,{})

    def test_scheduler_event_arrives_during_scripted_progress(self):
        ctx=scripted(40)
        main=source('MAIN',"n=0 RUN_TASK('SIGNALER',0,FALSE,FALSE,0,s) ATTACH MOVE AWAY 1, WHEN EVENT[1] DO n=1 ENDMOVE")
        signaler=source('SIGNALER','DELAY 15 SIGNAL EVENT[1]')
        instance=translate_project({'main':main,'signaler':signaler}).instantiate(context=ctx)
        values=instance.run('MAIN')
        self.assertEqual(values['MAIN']['values']['N'],1)
        self.assertEqual(values['SIGNALER']['state'],'completed')
        self.assertGreaterEqual(instance.scheduler.now_us,40000)
        self.assertEqual(move(ctx)['data']['execution']['elapsed_ms'],40)

    def test_two_task_scopes_share_history_without_sharing_owner_or_stack(self):
        ctx=context(capture_only=False,groups={1:2,2:2},responses=[dict(operation='MOVE AWAY',completed=True,delay_ms=20),dict(operation='MOVE AWAY',completed=True,delay_ms=25)])
        main=source('MAIN','LOCK_GROUP(1,s) n=0 MOVE AWAY 1, WHEN TRUE DO n=1 ENDMOVE')
        second='PROGRAM SECOND\n%DEFGROUP=2\nVAR n,s:INTEGER\nBEGIN LOCK_GROUP(2,s) n=0 MOVE AWAY 1, WHEN TRUE DO n=2 ENDMOVE END SECOND'
        instance=translate_project({'main':main,'second':second}).instantiate(context=ctx)
        instance.scheduler.start('MAIN');instance.scheduler.start('SECOND');maximum=0
        for _ in range(200):
            instance.scheduler.step();maximum=max(maximum,len(ctx.motion._active))
            if all(p.task_state=='completed' for p in instance.programs.values()):break
        self.assertEqual(maximum,2)
        self.assertEqual((instance.programs['MAIN'].snapshot()['N'],instance.programs['SECOND'].snapshot()['N']),(1,2))
        self.assertEqual({r['program'] for r in ctx.motion.history},{'MAIN','SECOND'})
        self.assertEqual(ctx.group_locks.owners,{})
        self.assertEqual(ctx.motion._active,{})


class MotionScopePersistenceTests(unittest.TestCase):
    def test_delay_and_local_history_roundtrip_without_live_aliases(self):
        _,ctx,_,_,_=execute('n=0 ATTACH MOVE AWAY 1, WHEN TRUE DO n=1 ENDMOVE',ctx=scripted(25))
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved)
        saved['motion']['history'][1]['data']['execution']['triggered'].clear()
        self.assertEqual(restored.motion.history[1]['data']['execution']['triggered'],[1])

    def test_bad_delay_configuration_rejected(self):
        for delay in (-1,86400001,True,1.5,'1',None):
            with self.subTest(delay=delay),self.assertRaises(ValueError):scripted(delay)

    def test_execution_progress_and_handler_history_are_checked(self):
        _,ctx,_,_,_=execute('ATTACH MOVE AWAY 1, WHEN TRUE DO n=1 ENDMOVE',ctx=scripted(20))
        original=ctx.motion.to_config()
        for key,value in [('elapsed_ms',21),('elapsed_ms',0),('delay_ms',True),('triggered',[1,1]),
                          ('triggered',[True]),('triggered',[2]),('handlers',[dict(kind='NODE',line=1)]),('handlers',[dict(kind='WHEN',line=0)])]:
            data=deepcopy(original);data['history'][1]['data']['execution'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)
        data=deepcopy(original);data['history'][1]['nowait']=True
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_pending_history_cannot_be_restored_as_completed_work(self):
        _,ctx,_,_,_=execute('ATTACH MOVE AWAY 1, WHEN TRUE DO n=1 ENDMOVE')
        data=ctx.motion.to_config();data['history'][1]['outcome']='pending'
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_until_and_failure_status_cannot_be_forged_as_success(self):
        _,ctx,_,_,_=execute('ATTACH MOVE AWAY 1, UNTIL TRUE ENDMOVE')
        for outcome in ('completed','captured'):
            data=ctx.motion.to_config();data['history'][1]['outcome']=outcome
            with self.subTest(outcome=outcome),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)


class MotionScopeSourceGuards(unittest.TestCase):
    def test_unsupported_source_shapes_remain_blocked(self):
        for body in ('MOVE TO p NOWAIT, WHEN TRUE DO n=1 ENDMOVE','MOVE AWAY 1, ENDMOVE',
                     'MOVE AWAY 1, WHEN TRUE DO ENDMOVE','MOVE AWAY 1, UNTIL TRUE THEN ENDMOVE',
                     'MOVE AWAY 1, WHEN TRUE DO n=1','MOVE AWAY 1, WHEN AT NODE[1] DO n=1 ENDMOVE',
                     'MOVE AWAY 1, WHEN TIME 10 DO n=1 ENDMOVE','MOVE AWAY 1, WHEN 1 DO n=1 ENDMOVE',
                     'MOVE AWAY 1, WHEN TRUE DO RETURN ENDMOVE','MOVE AWAY 1, WHEN TRUE DO GOTO x ENDMOVE',
                     'MOVE AWAY 1, WHEN TRUE DO MOVE AWAY 1 ENDMOVE',
                     'MOVE AWAY 1, WHEN TRUE DO CONDITION[1]: WHEN TRUE DO n=1 ENDCONDITION ENDMOVE'):
            with self.subTest(body=body),self.assertRaises(TranslationError):program(body)

    def test_more_than_32_local_clauses_rejected(self):
        body='MOVE AWAY 1, '+('WHEN FALSE DO n=1\n'*33)+'ENDMOVE'
        with self.assertRaises(TranslationError):program(body)

    def test_active_for_counter_write_in_action_or_predicate_rejected(self):
        for body,routines in [('FOR n=1 TO 2 DO MOVE AWAY 1, WHEN TRUE DO n=5 ENDMOVE ENDFOR',''),
            ('FOR n=1 TO 2 DO MOVE AWAY 1, WHEN change() DO s=1 ENDMOVE ENDFOR','ROUTINE change:BOOLEAN BEGIN n=5 RETURN TRUE END change')]:
            with self.subTest(body=body),self.assertRaisesRegex(TranslationError,'E_FOR_COUNTER'):program(body,routines=routines)


if __name__ == '__main__':
    unittest.main()
