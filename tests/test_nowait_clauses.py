"""Owner-checkpoint NOWAIT callbacks, supplied temporal windows and frame cleanup."""
from copy import deepcopy
import json
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_nowait_motion import build,move,progress,scheduled,active
from tests.test_motion_requests import context,DECL,SETUP
from tests.test_project_scheduler import source
from tests.test_extended_services import compile_program


def authored(body,*,decl=DECL,prefix='',routines='',ctx=None,delay=25,plan=None):
    now=[0]
    def sleep(seconds):now[0]+=round(seconds*1000000)
    response=dict(operation='MOVE AWAY',completed=True,delay_ms=delay)
    if plan is not None:response['node_times']=plan
    ctx=ctx or context(capture_only=False,responses=[response])
    p,r=compile_program(SETUP+body,decl=decl,prefix=prefix,routines=routines,context=ctx,joint_axes=2,clock_us=lambda:now[0],sleep=sleep)
    return p,ctx,now,r


class NowaitLocalClauseTests(unittest.TestCase):
    def test_entry_clauses_scan_once_before_source_continues(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO n=n+1 ENDMOVE n=n+10 DELAY 25 n=n+100')
        self.assertEqual(p.run()['N'],111);self.assertEqual(move(ctx)['data']['execution']['triggered'],[1]);self.assertEqual(move(ctx)['outcome'],'completed')
    def test_later_boolean_state_triggers_at_source_checkpoint(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN n=1 DO n=7 ENDMOVE n=1 DELAY 25 n=n+10')
        self.assertEqual(p.run()['N'],17)
    def test_until_cancels_then_finishes_actions(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, UNTIL TRUE THEN n=7 ENDMOVE n=n+1')
        self.assertEqual(p.run()['N'],8);self.assertEqual(move(ctx)['outcome'],'cancelled');self.assertEqual(progress(ctx),0)
    def test_until_without_then(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT, UNTIL TRUE ENDMOVE n=1');p.run();self.assertEqual(move(ctx)['outcome'],'cancelled')
    def test_cancel_finishes_current_actions_and_skips_later_clauses(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO CANCEL n=n+1 WHEN TRUE DO n=99 ENDMOVE')
        self.assertEqual(p.run()['N'],1);self.assertEqual(move(ctx)['data']['execution']['triggered'],[1])
    def test_source_order_and_dependent_predicates(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN n=0 DO n=1 WHEN n=1 DO n=n+10 ENDMOVE DELAY 25 n=n+100')
        self.assertEqual(p.run()['N'],111);self.assertEqual(move(ctx)['data']['execution']['triggered'],[1,2])
    def test_false_clause_completes_without_action(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=99 ENDMOVE DELAY 25 n=n+1')
        self.assertEqual(p.run()['N'],1);self.assertEqual(move(ctx)['outcome'],'completed')
    def test_source_sleep_does_not_execute_callbacks_inside_sleeper(self):
        seen=[];p,ctx,_,_,_=build('n=0 CONNECT TIMER TO s ATTACH MOVE AWAY 1 NOWAIT, WHEN s>=25 DO n=7 ENDMOVE DELAY 25 n=n+10 DISCONNECT TIMER s',sleep=lambda seconds:seen.append(p.snapshot()['N']))
        self.assertEqual(p.run()['N'],17);self.assertEqual(seen,[0])
    def test_callback_action_time_does_not_advance_its_job(self):
        p,ctx,_,seen,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO DELAY 100 n=1 ENDMOVE mark() DELAY 25 n=n+1')
        self.assertEqual(p.run()['N'],2);self.assertEqual(seen[0]['elapsed'],0);self.assertEqual(progress(ctx),25)
    def test_pause_inside_action_retains_one_shot_and_captured_storage(self):
        p,ctx,now,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO n=n+1 PAUSE n=n+10 ENDMOVE DELAY 25 n=n+100')
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['N'],1);now[0]+=100000
        self.assertEqual(p.resume()['N'],111);self.assertEqual(move(ctx)['data']['execution']['triggered'],[1])
    def test_until_then_failure_records_failed_outcome(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT, UNTIL TRUE THEN n=1 DIV 0 ENDMOVE')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(move(ctx)['outcome'],'failed');self.assertEqual(ctx.motion._active,{})
    def test_zero_delay_clauses_keep_entry_scan(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO n=7 ENDMOVE',delay=0)
        self.assertEqual(p.run()['N'],7);self.assertEqual(move(ctx)['outcome'],'completed')
    def test_no_implicit_final_scan_after_last_delay(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN n=1 DO n=99 ENDMOVE DELAY 25')
        self.assertEqual(p.run()['N'],0);self.assertEqual(move(ctx)['outcome'],'cancelled');self.assertEqual(progress(ctx),25)


class NowaitTemporalClauseTests(unittest.TestCase):
    def test_crossed_temporal_events_fire_at_next_owner_checkpoint(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN AT NODE[0] DO n=1 WHEN TIME 3 BEFORE NODE[1] DO n=n*10+2 WHEN AT NODE[1] DO n=n*10+3 ENDMOVE DELAY 25 n=n+100',plan={'0':0,'1':25})
        self.assertEqual(p.run()['N'],223);self.assertEqual(move(ctx)['data']['execution']['triggered'],[1,2,3])
    def test_crossed_events_use_source_order(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO n=n*10+1 WHEN TIME 5 BEFORE NODE[1] DO n=n*10+2 ENDMOVE DELAY 25 n=n+100',plan={'0':0,'1':25})
        self.assertEqual(p.run()['N'],112)
    def test_until_temporal_cancel_uses_observed_not_inferred_time(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, UNTIL TIME 5 BEFORE NODE[1] THEN n=7 ENDMOVE DELAY 25 n=n+1',plan={'0':0,'1':25})
        self.assertEqual(p.run()['N'],8);self.assertEqual((move(ctx)['outcome'],progress(ctx)),('cancelled',25))
    def test_missing_schedule_rejects_without_response_consumption(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO n=7 ENDMOVE')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(len(ctx.motion.responses),1)


class NowaitClauseFrameTests(unittest.TestCase):
    def test_routine_can_finish_job_before_return(self):
        routines='ROUTINE work VAR local:INTEGER BEGIN local=1 MOVE AWAY 1 NOWAIT, WHEN local=2 DO local=7 ENDMOVE local=2 DELAY 25 n=local END work'
        p,ctx,_,_,_=build('ATTACH work()',routines=routines);self.assertEqual(p.run()['N'],7);self.assertEqual(move(ctx)['outcome'],'completed')
    def test_unfinished_routine_callbacks_end_at_its_return(self):
        routines='ROUTINE work VAR local:INTEGER BEGIN local=1 MOVE AWAY 1 NOWAIT, WHEN FALSE DO local=99 ENDMOVE END work'
        p,ctx,_,_,_=build('n=0 ATTACH work() DELAY 25 n=n+1',routines=routines);self.assertEqual(p.run()['N'],1);self.assertEqual(move(ctx)['outcome'],'cancelled');self.assertEqual(progress(ctx),0)
    def test_ancestor_callback_uses_captured_frame_inside_nested_call(self):
        routines='ROUTINE inner VAR local:INTEGER BEGIN local=99 DELAY 25 n=local END inner ROUTINE work VAR local:INTEGER BEGIN local=7 MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO s=local ENDMOVE inner() END work'
        p,ctx,_,_,_=build('ATTACH work()',routines=routines,plan={'0':0,'1':25});self.assertEqual((p.run()['N'],p.snapshot()['S']),(99,7));self.assertEqual(move(ctx)['data']['execution']['triggered'],[1])
    def test_callback_writes_after_launch_block_counter(self):
        with self.assertRaises(TranslationError):build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=7 ENDMOVE FOR n=1 TO 3 DO s=s+1 ENDFOR')


class NowaitClauseSchedulerTests(unittest.TestCase):
    def test_waiting_owner_does_not_spin_at_supplied_completion(self):
        project,p,ctx=scheduled('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO n=7 ENDMOVE DELAY 100 n=n+1')
        # The scripted response needs an explicit supplied arrival table.
        ctx.motion.responses[0]['node_times']={'0':0,'1':25}
        values=project.run('MAIN');self.assertEqual(values['MAIN']['values']['N'],8);self.assertEqual(move(ctx)['outcome'],'completed')

    def test_external_poll_observes_progress_without_running_callbacks(self):
        p,ctx,now,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO n=7 ENDMOVE PAUSE n=n+1',plan={'0':0,'1':25})
        with self.assertRaises(rt.KarelPause):p.run()
        # A paused job excludes time, and even explicit polling never runs source.
        now[0]=25000;ctx.motion.poll(p._state);self.assertEqual(p.snapshot()['N'],0);self.assertEqual(progress(ctx),0);p.stop()
    def test_foreign_task_checkpoints_do_not_run_owner_local_callbacks(self):
        project,p,ctx=scheduled('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN n=0 DO n=7 ENDMOVE DELAY 100')
        active(project,ctx)
        watcher,_=compile_program('n=1',context=ctx);watcher.run()
        self.assertEqual(p.snapshot()['N'],0);project.scheduler.run();self.assertEqual(p.snapshot()['N'],7)
    def test_task_renaming_preserves_callback_identity(self):
        project,p,ctx=scheduled('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO n=n+1 ENDMOVE DELAY 100 n=n+10')
        active(project,ctx);project.scheduler.rename('MAIN','RENAMED');project.scheduler.run();self.assertEqual(p.snapshot()['N'],11)
    def test_stopping_waiting_owner_cancels_callbacks(self):
        project,p,ctx=scheduled('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=99 ENDMOVE DELAY 100')
        active(project,ctx);project.scheduler.stop('MAIN');self.assertEqual(move(ctx)['outcome'],'cancelled');self.assertEqual(ctx.motion._active,{})
    def test_scheduler_pause_inside_callback_retains_action(self):
        project,p,ctx=scheduled('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO n=1 PAUSE n=n+10 ENDMOVE DELAY 25 n=n+100')
        project.run('MAIN');self.assertEqual(p.snapshot()['N'],1);project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(p.snapshot()['N'],111)


class NowaitClauseCaptureTests(unittest.TestCase):
    def test_eval_is_captured_once_before_source_changes(self):
        p,ctx,_,_,_=build('n=1 ATTACH MOVE AWAY 1 NOWAIT, WHEN (n=2) AND (EVAL(n)=1) DO n=7 ENDMOVE n=2 DELAY 25 n=n+10')
        self.assertEqual(p.run()['N'],17)
    def test_function_predicate_uses_normal_source_calls(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN ready() DO n=7 ENDMOVE n=1 DELAY 25 n=n+10',routines='ROUTINE ready:BOOLEAN BEGIN RETURN n=1 END ready')
        self.assertEqual(p.run()['N'],17)
    def test_global_handler_scans_before_local_clause(self):
        body='n=0 CONDITION[1]: WHEN n=1 DO n=2 ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT, WHEN n=2 DO n=7 ENDMOVE n=1 DELAY 25 n=n+10'
        p,ctx,_,_,_=build(body);self.assertEqual(p.run()['N'],17)
    def test_event_consumers_are_independent(self):
        body='n=0 CONDITION[1]: WHEN EVENT[1] DO n=n+1 ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT, WHEN EVENT[1] DO n=n+10 ENDMOVE SIGNAL EVENT[1] DELAY 25 n=n+100'
        p,ctx,_,_,_=build(body);self.assertEqual(p.run()['N'],111);self.assertEqual({key[0] for key in p._state._event_seen},{1})
    def test_private_using_reference_survives_lexical_exit(self):
        prefix='TYPE item_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        routines='ROUTINE copy_item:item_t BEGIN RETURN item END copy_item'
        body='n=0 ATTACH USING copy_item() DO amount=7 MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO n=amount ENDMOVE ENDUSING DELAY 25 s=n'
        p,ctx,_,_=authored(body,decl=DECL+' item:item_t',prefix=prefix,routines=routines,plan={'0':0,'1':25})
        self.assertEqual((p.run()['N'],p.snapshot()['S']),(7,7));self.assertEqual(p.snapshot()['ITEM']['AMOUNT'],{'uninitialized':True})
    def test_named_using_reference_remains_live(self):
        prefix='TYPE item_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        body='n=0 item.amount=1 ATTACH USING item DO MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO n=amount ENDMOVE ENDUSING item.amount=7 DELAY 25 s=n'
        p,ctx,_,_=authored(body,decl=DECL+' item:item_t',prefix=prefix,plan={'0':0,'1':25});self.assertEqual(p.run()['N'],7)
    def test_formal_alias_captures_original_caller_cell(self):
        routines='ROUTINE work(value:INTEGER) BEGIN MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO value=7 ENDMOVE DELAY 25 s=value END work'
        p,ctx,_,_,_=build('n=0 ATTACH work(n)',routines=routines,plan={'0':0,'1':25});self.assertEqual((p.run()['N'],p.snapshot()['S']),(7,7))
    def test_grouped_formal_stays_private(self):
        routines='ROUTINE work(value:INTEGER) BEGIN MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO value=7 ENDMOVE DELAY 25 s=value END work'
        p,ctx,_,_,_=build('n=0 ATTACH work((n))',routines=routines,plan={'0':0,'1':25});self.assertEqual((p.run()['N'],p.snapshot()['S']),(0,7))


class NowaitClauseLifecycleTests(unittest.TestCase):
    def test_hold_defers_scans_and_freezes_progress(self):
        p,ctx,_,seen,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO n=7 ENDMOVE HOLD DELAY 100 mark() UNHOLD DELAY 25 n=n+1',plan={'0':0,'1':25})
        self.assertEqual(p.run()['N'],8);self.assertEqual(seen[0]['elapsed'],0)
    def test_local_hold_finishes_action_then_waits_for_global_unhold(self):
        body='n=0 CONDITION[1]: WHEN n=1 DO UNHOLD ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO HOLD n=1 ENDMOVE DELAY 25 n=n+10'
        p,ctx,_,_,_=build(body);self.assertEqual(p.run()['N'],11);self.assertEqual(move(ctx)['outcome'],'completed')
    def test_cancel_preserves_local_hold_flag(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO HOLD CANCEL n=7 ENDMOVE');self.assertEqual(p.run()['N'],7);self.assertIn(1,ctx.group_locks.held)
    def test_stop_during_action_releases_callback_scope(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO PAUSE n=99 ENDMOVE')
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual((ctx.motion._active,ctx.motion._local_actions),({},{}));self.assertEqual(move(ctx)['outcome'],'cancelled')
    def test_abort_action_cancels_scope(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO ABORT ENDMOVE')
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(move(ctx)['outcome'],'cancelled');self.assertFalse(p._state._in_handler)
    def test_budget_failure_in_action_marks_failed(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO WHILE TRUE DO n=1 ENDWHILE ENDMOVE')
        with self.assertRaises(rt.KarelRuntimeError):p.run(max_steps=100)
        self.assertEqual(move(ctx)['outcome'],'failed');self.assertEqual(ctx.motion._active,{})
    def test_global_cancel_precedes_local_scan(self):
        body='n=0 CONDITION[1]: WHEN n=1 DO CANCEL ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT, WHEN n=1 DO n=99 ENDMOVE n=1 DELAY 25 n=n+1'
        p,ctx,_,_,_=build(body);self.assertEqual(p.run()['N'],2);self.assertEqual(move(ctx)['data']['execution']['triggered'],[])
    def test_second_pending_move_does_not_consume_response(self):
        ctx=context(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True,delay_ms=25)]*2)
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=7 ENDMOVE MOVE AWAY 2 NOWAIT',ctx=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(len(ctx.motion.responses),1)


class NowaitClauseFormTests(unittest.TestCase):
    def form(self,text,operation,*,setup=''):
        ctx=context(capture_only=False,responses=[dict(operation=operation,completed=True,delay_ms=25)])
        p,ctx,_,_,_=build(setup+'n=0 ATTACH '+text+' NOWAIT, WHEN TRUE DO n=7 ENDMOVE DELAY 25 n=n+1',ctx=ctx)
        self.assertEqual(p.run()['N'],8);self.assertEqual(move(ctx)['outcome'],'completed')
    def test_move_to(self):self.form('MOVE TO p','MOVE TO')
    def test_move_to_via(self):self.form('MOVE TO p VIA q','MOVE TO')
    def test_move_near(self):self.form('MOVE NEAR p BY 1','MOVE NEAR')
    def test_move_away(self):self.form('MOVE AWAY 1','MOVE AWAY')
    def test_move_about(self):self.form('MOVE ABOUT v BY 1','MOVE ABOUT')
    def test_move_axis(self):self.form('MOVE AXIS 1 BY 1','MOVE AXIS')
    def test_move_relative(self):self.form('MOVE RELATIVE v','MOVE RELATIVE')
    def test_move_along(self):self.form('MOVE ALONG route','MOVE ALONG',setup='APPEND_NODE(route,s) route[1].node_pos=p ')


class NowaitClauseBoundaryTests(unittest.TestCase):
    def paused(self,*,routines='',body=None):
        p,ctx,now,_,_=build(body or 'n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=7 ENDMOVE PAUSE n=n+1',routines=routines)
        with self.assertRaises(rt.KarelPause):p.run()
        return p,ctx,now
    def test_replaced_clock_during_callback_fails(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO replace_clock() ENDMOVE',routines='ROUTINE replace_clock FROM HOST')
        ctx.externals['HOST','REPLACE_CLOCK']=lambda:setattr(p._state,'_clock_us',lambda:0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'clock adapter'):p.run()
        self.assertEqual(move(ctx)['outcome'],'failed');self.assertEqual(ctx.motion._local_actions,{})
    def test_stale_frame_is_rejected_before_poll_clock(self):
        p,ctx,_=self.paused(routines='ROUTINE work BEGIN MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=7 ENDMOVE PAUSE END work',body='ATTACH work()')
        live=p._state._timer_frames.pop()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'frame is inactive'):ctx.motion.poll(p._state)
        p._state._timer_frames.append(live);self.assertEqual(move(ctx)['outcome'],'failed');p.stop()
    def test_frame_changed_by_clock_is_revalidated(self):
        p,ctx,_=self.paused(routines='ROUTINE work BEGIN MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=7 ENDMOVE PAUSE END work',body='ATTACH work()')
        original=p._state._clock_us;live=p._state._timer_frames[-1]
        def clock():p._state._timer_frames.clear();return original()
        p._state._clock_us=clock;scope=next(iter(ctx.motion._active.values()));scope['clock']=clock
        with self.assertRaisesRegex(rt.KarelRuntimeError,'frame is inactive'):ctx.motion.poll(p._state)
        p._state._timer_frames.append(live);self.assertEqual(move(ctx)['outcome'],'failed');p.stop()
    def test_foreign_grant_is_preserved_on_failure(self):
        p,ctx,_=self.paused();other=object();ctx.group_locks.release_owner(p._state);ctx.group_locks._grant(1,other);ctx.group_locks.set_motion(1,'executing')
        with self.assertRaises(rt.KarelRuntimeError):ctx.motion.poll(p._state)
        self.assertIs(ctx.group_locks.owners[1],other);p.stop()
    def test_invalid_callback_descriptors_precede_response_consumption(self):
        p,ctx,_,_,_=build('');p.run();p._state.task_state='running';ctx.group_locks._grant(1,p._state)
        for rows in (None,[('WHEN',None,lambda:None,1)],[('WHEN',lambda:True,lambda:None,True)]):
            with self.subTest(rows=rows),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):
                list(ctx.motion.execute(p._state,'MOVE AWAY',{'distance':1},True,1,clauses=rows))
        self.assertEqual(len(ctx.motion.responses),1);ctx.group_locks.release_owner(p._state)
    def test_old_private_handler_smuggling_guard_remains(self):
        p,ctx,_,_,_=build('');p.run();ctx.group_locks._grant(1,p._state)
        execution=dict(delay_ms=25,elapsed_ms=0,handlers=[dict(kind='WHEN',line=1)],triggered=[])
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):ctx.motion.invoke(p._state,'MOVE AWAY',{'distance':1},True,1,_execution=execution,_background=True)
        self.assertEqual(len(ctx.motion.responses),1);ctx.group_locks.release_owner(p._state)
    def test_callback_admission_requires_original_task_identity(self):
        p,ctx,_,_,_=build('');p.run();ctx.group_locks._grant(1,p._state)
        clauses=[('WHEN',lambda:False,lambda:None,1)];execution=dict(delay_ms=25,elapsed_ms=0,handlers=[dict(kind='WHEN',line=1)],triggered=[])
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'defining frames'):
            ctx.motion.invoke(p._state,'MOVE AWAY',{'distance':1},True,1,_execution=execution,_background=True,_clauses=clauses,_callback_context=(object(),()))
        self.assertEqual(len(ctx.motion.responses),1);ctx.group_locks.release_owner(p._state)
    def test_callback_admission_requires_exact_live_frames(self):
        p,ctx,_,_,_=build('');p.run();ctx.group_locks._grant(1,p._state)
        clauses=[('WHEN',lambda:False,lambda:None,1)];execution=dict(delay_ms=25,elapsed_ms=0,handlers=[dict(kind='WHEN',line=1)],triggered=[])
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'defining frames'):
            ctx.motion.invoke(p._state,'MOVE AWAY',{'distance':1},True,1,_execution=execution,_background=True,_clauses=clauses,_callback_context=(p._state,(object(),)))
        self.assertEqual(len(ctx.motion.responses),1);ctx.group_locks.release_owner(p._state)
    def test_clock_side_effect_cannot_replace_the_ownership_grant(self):
        p,ctx,_=self.paused();other=object();original=p._state._clock_us
        def clock():
            ctx.group_locks.release_owner(p._state);ctx.group_locks._grant(1,other);ctx.group_locks.set_motion(1,'executing');return original()
        p._state._clock_us=clock;next(iter(ctx.motion._active.values()))['clock']=clock
        with self.assertRaises(rt.KarelRuntimeError):ctx.motion.poll(p._state)
        self.assertIs(ctx.group_locks.owners[1],other);self.assertEqual(ctx.group_locks.motion[1],'executing');self.assertEqual(move(ctx)['outcome'],'failed');p.stop()
    def test_stale_cleanup_does_not_relabel_same_grant_replacement(self):
        p,ctx,_=self.paused();old=next(iter(ctx.motion._active.values()));replacement=dict(old,request=deepcopy(old['request']))
        ctx.motion._active[1]=replacement;ctx.motion.finish_scope(old,'failed')
        self.assertIs(ctx.motion._active[1],replacement);self.assertEqual(ctx.group_locks.motion[1],'executing');ctx.motion.finish_scope(replacement,'cancelled');p.stop()


class NowaitClauseHistoryTests(unittest.TestCase):
    def terminal(self,clause='WHEN TRUE DO n=7'):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT, '+clause+' ENDMOVE DELAY 25 n=1');p.run();return ctx.motion.to_config()
    def test_terminal_history_roundtrip_contains_data_only(self):
        saved=self.terminal();self.assertEqual(rt.MotionRequests.from_config(json.loads(json.dumps(saved))).to_config(),saved)
    def test_active_callbacks_cannot_be_saved(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=7 ENDMOVE PAUSE')
        with self.assertRaises(rt.KarelPause):p.run()
        with self.assertRaises(ValueError):ctx.motion.to_config()
        p.stop()
    def test_duplicate_trigger_indexes_reject(self):
        saved=self.terminal();saved['history'][1]['data']['execution']['triggered']=[1,1]
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)
    def test_triggered_until_cannot_claim_completed(self):
        saved=self.terminal('UNTIL TRUE');saved['history'][1]['outcome']='completed'
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)
    def test_completed_local_job_needs_full_progress(self):
        saved=self.terminal();saved['history'][1]['data']['execution']['elapsed_ms']=24
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)
    def test_restore_does_not_restore_callbacks(self):
        restored=rt.MotionRequests.from_config(self.terminal());self.assertEqual((restored._active,restored._local_actions),({},{}))


class NowaitClauseCounterTests(unittest.TestCase):
    def guarded(self,action,*,routines='',decl=DECL):
        with self.assertRaises(TranslationError):authored('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN FALSE DO '+action+' ENDMOVE FOR n=1 TO 2 DO s=1 ENDFOR',routines=routines,decl=decl)
    def test_transitive_global_writes_protect_later_counter(self):self.guarded('change()',routines='ROUTINE change BEGIN n=7 END change')
    def test_transitive_formal_writes_protect_later_counter(self):self.guarded('change(n)',routines='ROUTINE change(value:INTEGER) BEGIN value=7 END change')
    def test_service_output_protects_later_counter(self):self.guarded("CNV_STR_INT('7',n)")
    def test_predicate_effect_protects_later_counter(self):
        with self.assertRaises(TranslationError):build('ATTACH MOVE AWAY 1 NOWAIT, WHEN change() DO s=1 ENDMOVE FOR n=1 TO 2 DO s=1 ENDFOR',routines='ROUTINE change:BOOLEAN BEGIN n=7 RETURN FALSE END change')
    def test_array_sibling_writes_protect_complete_root(self):
        with self.assertRaises(TranslationError):authored('ATTACH MOVE AWAY 1 NOWAIT, WHEN FALSE DO values[2]=7 ENDMOVE FOR values[1]=1 TO 2 DO n=1 ENDFOR',decl=DECL+' values:ARRAY[2]OF INTEGER')
    def test_independent_counter_can_continue(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=7 ENDMOVE FOR s=1 TO 2 DO n=n+1 ENDFOR DELAY 25 n=n+10')
        self.assertEqual(p.run()['N'],12)


class NowaitClauseLinkedTests(unittest.TestCase):
    def linked(self,routine,body='ATTACH work() DELAY 25 n=1',*,extra=''):
        ctx=context(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True,delay_ms=25,node_times={'0':0,'1':25})])
        main=source('MAIN',body,decl='n,s:INTEGER',routines='ROUTINE work FROM LIB '+extra)
        lib=source('LIB','',decl='result:INTEGER',routines=routine)
        project=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);return project,ctx
    def test_library_callbacks_complete_while_defining_routine_is_live(self):
        project,ctx=self.linked('ROUTINE work VAR local:INTEGER BEGIN local=7 MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO result=local ENDMOVE DELAY 25 local=8 END work')
        values=project.run('MAIN');self.assertEqual(values['LIB']['values']['RESULT'],7);self.assertEqual(move(ctx)['outcome'],'completed')
    def test_linked_return_cancels_unfinished_callbacks(self):
        project,ctx=self.linked('ROUTINE work BEGIN MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO result=99 ENDMOVE END work')
        values=project.run('MAIN');self.assertEqual(values['LIB']['values']['RESULT'],{'uninitialized':True});self.assertEqual(move(ctx)['outcome'],'cancelled')
    def test_linked_action_can_call_back_into_main(self):
        routine='ROUTINE record(value:INTEGER) FROM MAIN ROUTINE work BEGIN MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO record(7) ENDMOVE DELAY 25 result=1 END work'
        project,ctx=self.linked(routine,body='n=0 ATTACH work() n=n+1',extra='ROUTINE record(value:INTEGER) BEGIN n=value END record')
        self.assertEqual(project.run('MAIN')['MAIN']['values']['N'],8)
    def test_linked_pause_keeps_callback_frame_live(self):
        project,ctx=self.linked('ROUTINE work BEGIN result=0 MOVE AWAY 1 NOWAIT, WHEN TRUE DO result=1 PAUSE result=result+10 ENDMOVE DELAY 25 result=result+100 END work')
        project.run('MAIN');self.assertEqual(project.programs['LIB'].snapshot()['RESULT'],1)
        project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(project.programs['LIB'].snapshot()['RESULT'],111)
    def test_early_return_cancels_before_following_source(self):
        p,ctx,_,_,_=build('ATTACH work() DELAY 25 n=1',routines='ROUTINE work BEGIN MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=99 ENDMOVE RETURN END work')
        self.assertEqual(p.run()['N'],1);self.assertEqual(move(ctx)['outcome'],'cancelled')
    def test_callback_free_linked_launch_still_survives_return(self):
        project,ctx=self.linked('ROUTINE work BEGIN MOVE AWAY 1 NOWAIT END work')
        project.run('MAIN');self.assertEqual(move(ctx)['outcome'],'completed')


class NowaitClauseTemporalWindowsTests(unittest.TestCase):
    def test_wildcard_fires_only_once_across_observations(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN AT NODE[*] DO n=n+1 ENDMOVE DELAY 25 n=n+10 DELAY 25 n=n+100',plan={'0':0,'1':25})
        self.assertEqual(p.run()['N'],111);self.assertEqual(move(ctx)['data']['execution']['triggered'],[1])
    def test_false_gate_does_not_replay_a_past_event(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN (TIME 5 AFTER NODE[0]) AND (n=1) DO n=99 ENDMOVE DELAY 10 n=1 DELAY 15 s=n',plan={'0':0,'1':25})
        self.assertEqual(p.run()['N'],1);self.assertEqual(move(ctx)['data']['execution']['triggered'],[])
    def test_zero_duration_temporal_entry_is_observed(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN AT NODE[0] DO n=1 WHEN AT NODE[1] DO n=n+10 ENDMOVE',delay=0,plan={'0':0,'1':0})
        self.assertEqual(p.run()['N'],11);self.assertEqual(move(ctx)['outcome'],'completed')
    def test_selected_path_range_keeps_original_node_numbers(self):
        ctx=context(capture_only=False,responses=[dict(operation='MOVE ALONG',completed=True,delay_ms=25,node_times={'0':0,'2':25})])
        p,ctx,_,_,_=build('APPEND_NODE(route,s) APPEND_NODE(route,s) route[1].node_pos=p route[2].node_pos=q n=0 ATTACH MOVE ALONG route[2..2] NOWAIT, WHEN AT NODE[2] DO n=7 ENDMOVE DELAY 25 n=n+1',ctx=ctx)
        self.assertEqual(p.run()['N'],8);self.assertEqual(move(ctx)['data']['start'],2)
    def test_temporal_selector_expression_is_captured_once(self):
        routines='ROUTINE offset:INTEGER BEGIN s=s+1 RETURN 5 END offset'
        p,ctx,_,_,_=build('n=0 s=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN TIME offset() BEFORE NODE[1] DO n=7 ENDMOVE DELAY 25 n=n+1',routines=routines,plan={'0':0,'1':25})
        self.assertEqual((p.run()['N'],p.snapshot()['S']),(8,1))
    def test_incomplete_temporal_schedule_precedes_publication(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO n=7 ENDMOVE',plan={'0':0,'2':25})
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(len(ctx.motion.history),1)
    def test_poll_progress_does_not_force_boolean_truth(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN n=1 DO n=99 ENDMOVE DELAY 25 s=n')
        self.assertEqual(p.run()['N'],0);self.assertEqual(move(ctx)['data']['execution']['triggered'],[])


class NowaitClauseReportTests(unittest.TestCase):
    def report(self):return build('ATTACH MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=7 ENDMOVE')[4].report
    def test_report_identifies_observation_and_lifetime(self):
        row=next(row for row in self.report()['motion_requests'] if row['nowait']);self.assertEqual(row['callback_observation'],'owner_checkpoints');self.assertEqual(row['callback_lifetime'],'defining_frame_or_invocation')
    def test_policy_links_the_public_semantics_guide(self):self.assertEqual(self.report()['motion_nowait_clause_policy']['guide'],'docs/nowait-local-clauses.md')
    def test_policy_distinguishes_clock_polling_from_callbacks(self):self.assertIn('never executes callbacks',self.report()['motion_nowait_clause_policy']['observation'])
    def test_policy_retains_native_boundary(self):self.assertFalse(self.report()['motion_nowait_clause_policy']['controller_validated']);self.assertIn('strict',self.report()['motion_nowait_clause_policy']['boundary'])


if __name__=='__main__':unittest.main()
