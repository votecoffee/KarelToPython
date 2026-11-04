"""Queued owner-checkpoint handlers, promotion, lifetime and counter proofs."""
import json
import unittest

from karel2py import runtime as rt, translate_project
from karel2py.lexer import TranslationError
from tests.test_queued_motion import run, bank, moves
from tests.test_nowait_clauses import authored
from tests.test_motion_requests import DECL
from tests.test_project_scheduler import source


def triggered(ctx):return [list(row['data'].get('execution',{}).get('triggered',[])) for row in moves(ctx)]


def elapsed(ctx):return [row['data'].get('execution',{}).get('elapsed_ms',0) for row in moves(ctx)]


def terminal(ctx):return [row['outcome'] for row in moves(ctx)]


def project(body,*delays,ctx=None,lib=None,**options):
    ctx=ctx or bank(*delays)
    docs={'main':source('MAIN',body,routines='ROUTINE work FROM LIB' if lib else '')}
    if lib:docs['lib']=lib
    linked=translate_project(docs).instantiate(context=ctx,options=options)
    return linked,linked.programs['MAIN'],ctx


def queued(linked,ctx):
    linked.scheduler.start('MAIN')
    for _ in range(200):
        linked.scheduler.step()
        if ctx.motion._queued:return
    raise AssertionError('No queued motion was admitted')


class QueuedClausePromotionTests(unittest.TestCase):
    def test_waiting_handlers_do_not_run_at_admission(self):
        seen=[]
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE inspect() DELAY 30 s=7',10,20,routines='ROUTINE inspect FROM HOST')
        ctx.externals['HOST','INSPECT']=lambda:seen.append((p.snapshot()['N'],triggered(ctx)))
        self.assertEqual(p.run()['N'],7);self.assertEqual(seen,[(0,[[],[]])]);self.assertEqual(triggered(ctx),[[],[1]])

    def test_boolean_clause_runs_after_promotion(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN n=1 DO n=7 ENDMOVE n=1 DELAY 30 s=7',10,20)
        self.assertEqual(p.run()['N'],7);self.assertEqual(terminal(ctx),['completed']*2)

    def test_callback_heads_and_waiters_preserve_source_order(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO n=1 ENDMOVE MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=n*10+2 ENDMOVE MOVE AWAY 3 NOWAIT, WHEN TRUE DO n=n*10+3 ENDMOVE MOVE AWAY 4',5,6,7,0)
        self.assertEqual(p.run()['N'],123);self.assertEqual(terminal(ctx),['completed']*4);self.assertEqual(triggered(ctx),[[1],[1],[1],[]])

    def test_all_seven_forms_and_via_accept_waiting_handlers(self):
        forms=[('MOVE TO p VIA q','MOVE TO'),('MOVE NEAR p BY 1','MOVE NEAR'),('MOVE AWAY 2','MOVE AWAY'),('MOVE ABOUT v BY 1','MOVE ABOUT'),('MOVE AXIS 2 BY 3','MOVE AXIS'),('MOVE RELATIVE v','MOVE RELATIVE'),('MOVE ALONG route','MOVE ALONG')]
        for statement,operation in forms:
            with self.subTest(statement=statement):
                ctx=bank(5,6,0,operations=['MOVE AWAY',operation,'MOVE AWAY'])
                p,ctx,_,_=run('n=0 APPEND_NODE(route,s) route[1].node_pos=p ATTACH MOVE AWAY 1 NOWAIT '+statement+' NOWAIT, WHEN TRUE DO n=7 ENDMOVE MOVE AWAY 4',ctx=ctx)
                self.assertEqual(p.run()['N'],7);self.assertEqual(terminal(ctx),['completed']*3);self.assertEqual(triggered(ctx)[1],[1])

    def test_blocking_barrier_observes_queued_handlers(self):
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE MOVE AWAY 3 RELEASE',10,20,5)
        self.assertEqual(p.run()['N'],7);self.assertEqual(terminal(ctx),['completed']*3);self.assertEqual(now[0],35000)

    def test_blocking_barrier_observes_handler_head(self):
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO n=7 ENDMOVE MOVE AWAY 2',10,20)
        self.assertEqual(p.run()['N'],7);self.assertEqual(elapsed(ctx),[10,20]);self.assertEqual(now[0],30000)

    def test_zero_duration_promotions_need_no_artificial_sleep(self):
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=n+1 ENDMOVE MOVE AWAY 3 NOWAIT, WHEN TRUE DO n=n+10 ENDMOVE MOVE AWAY 4',1,0,0,0)
        self.assertEqual(p.run()['N'],11);self.assertEqual(now[0],1000);self.assertEqual(terminal(ctx),['completed']*4)

    def test_zero_entry_selector_runs_before_next_sleep(self):
        ctx=bank(5,20,0);ctx.motion.responses[1]['node_times']={'0':0,'1':20}
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN AT NODE[0] DO stamp() ENDMOVE MOVE AWAY 3',ctx=ctx,routines='ROUTINE stamp FROM HOST')
        seen=[];ctx.externals['HOST','STAMP']=lambda:seen.append(now[0]);p.run();self.assertEqual(seen,[5000])

    def test_callback_free_overshoot_reaches_waiter_event_window(self):
        ctx=bank(10,20,0);ctx.motion.responses[1]['node_times']={'0':0,'1':20}
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN AT NODE[1] DO n=7 ENDMOVE DELAY 50 MOVE AWAY 3',ctx=ctx)
        self.assertEqual(p.run()['N'],7);self.assertEqual(elapsed(ctx),[10,20,0])

    def test_handler_head_completion_starts_successor_at_observation(self):
        seen=[]
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=7 ENDMOVE MOVE AWAY 2 NOWAIT DELAY 50 inspect() DELAY 20',10,20,routines='ROUTINE inspect FROM HOST')
        ctx.externals['HOST','INSPECT']=lambda:seen.append(elapsed(ctx));p.run()
        self.assertEqual(seen,[[10,0]]);self.assertEqual(terminal(ctx),['completed']*2)

    def test_one_handler_head_per_group_is_scanned_per_checkpoint(self):
        # A promoted job is observed at the next checkpoint, not recursively
        # scanned inside the predecessor's completion cleanup.
        ctx=bank(1,0,0);p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=99 ENDMOVE MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE MOVE AWAY 3',ctx=ctx)
        self.assertEqual(p.run()['N'],7);self.assertEqual(now[0],1000)

    def test_dispatcher_and_cooperative_engines(self):
        for label,cooperative in (('',False),('entry:: ',False),('',True)):
            with self.subTest(label=label,cooperative=cooperative):
                p,ctx,_,_=run(label+'n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE MOVE AWAY 3',5,6,0,cooperative=cooperative)
                self.assertEqual(p.run()['N'],7);self.assertEqual(terminal(ctx),['completed']*3)


class QueuedTemporalCaptureTests(unittest.TestCase):
    def test_waiter_events_use_its_supplied_timeline(self):
        ctx=bank(10,20,0);ctx.motion.responses[1]['node_times']={'0':0,'1':20}
        body='n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN AT NODE[0] DO n=1 WHEN TIME 5 BEFORE NODE[1] DO n=n*10+2 WHEN AT NODE[1] DO n=n*10+3 ENDMOVE MOVE AWAY 3'
        p,ctx,_,_=run(body,ctx=ctx);self.assertEqual(p.run()['N'],123);self.assertEqual(triggered(ctx)[1],[1,2,3])

    def test_missing_waiter_schedule_preserves_reply(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN AT NODE[1] DO n=7 ENDMOVE',10,20)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(len(moves(ctx)),1)

    def test_eval_captures_before_waiting(self):
        p,ctx,_,_=run('n=1 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN EVAL(n)=1 DO s=7 ENDMOVE n=99 MOVE AWAY 3',10,20,0)
        self.assertEqual(p.run()['S'],7)

    def test_false_temporal_gate_does_not_replay_an_old_event(self):
        ctx=bank(10,20,0);ctx.motion.responses[1]['node_times']={'0':0,'1':20}
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN AT NODE[0] AND (n=1) DO s=99 ENDMOVE DELAY 10 s=7 n=1 MOVE AWAY 3',ctx=ctx)
        self.assertEqual(p.run()['S'],7);self.assertEqual(triggered(ctx)[1],[])

    def test_using_named_storage_remains_live_until_promotion(self):
        prefix='TYPE item_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        ctx=bank(10,20,0)
        p,ctx,_,_=authored('n=0 ATTACH item.amount=1 MOVE AWAY 1 NOWAIT USING item DO MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=amount ENDMOVE ENDUSING item.amount=7 MOVE AWAY 3',decl='item:item_t '+DECL,prefix=prefix,ctx=ctx)
        self.assertEqual(p.run()['N'],7)

    def test_private_using_capture_survives_lexical_exit(self):
        prefix='TYPE item_t=STRUCTURE amount:INTEGER ENDSTRUCTURE';ctx=bank(10,20,0)
        routines='ROUTINE copy_item:item_t BEGIN RETURN item END copy_item'
        body='n=0 ATTACH item.amount=1 MOVE AWAY 1 NOWAIT USING copy_item() DO amount=7 MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=amount ENDMOVE ENDUSING item.amount=99 MOVE AWAY 3'
        p,ctx,_,_=authored(body,decl=DECL+' item:item_t',prefix=prefix,routines=routines,ctx=ctx)
        self.assertEqual(p.run()['N'],7);self.assertEqual(p.snapshot()['ITEM']['AMOUNT'],99)

    def test_operands_detach_at_queue_admission(self):
        ctx=bank(10,20,0,operations=['MOVE AWAY','MOVE TO','MOVE AWAY'])
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE TO p NOWAIT, WHEN TRUE DO n=7 ENDMOVE p.x=999 MOVE AWAY 3',ctx=ctx)
        p.run();self.assertEqual(moves(ctx)[1]['data']['target']['value']['X'],10.)

    def test_with_settings_detach_at_queue_admission(self):
        p,ctx,_,_=run('s=50 ATTACH MOVE AWAY 1 NOWAIT\nWITH $SPEED=s MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE s=99 MOVE AWAY 3',10,20,0)
        p.run();self.assertEqual(moves(ctx)[1]['data']['settings'],[dict(name='$SPEED',group=1,value=50.)])


class QueuedClauseControlsTests(unittest.TestCase):
    def test_until_cancels_head_and_all_followers_before_then(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, UNTIL TRUE THEN n=7 ENDMOVE MOVE AWAY 3 NOWAIT MOVE AWAY 4 s=7',5,20,30,0)
        self.assertEqual(p.run()['N'],7);self.assertEqual(terminal(ctx),['completed','cancelled','cancelled','cancelled']);self.assertEqual(triggered(ctx)[1],[1])

    def test_explicit_cancel_finishes_current_actions(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO CANCEL n=7 WHEN TRUE DO n=99 ENDMOVE MOVE AWAY 3',5,20,0)
        self.assertEqual(p.run()['N'],7);self.assertEqual(triggered(ctx)[1],[1]);self.assertEqual(terminal(ctx),['completed','cancelled','cancelled'])

    def test_callback_action_time_is_excluded_before_successor_starts(self):
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO DELAY 100 n=7 ENDMOVE MOVE AWAY 3',5,20,10)
        self.assertEqual(p.run()['N'],7);self.assertEqual(now[0],135000);self.assertEqual(elapsed(ctx),[5,20,10])

    def test_then_failure_fails_the_rest_of_the_batch(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, UNTIL TRUE THEN n=1 DIV 0 ENDMOVE MOVE AWAY 3',5,20,0)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(terminal(ctx),['completed','failed','failed'])

    def test_pause_inside_promoted_action_retains_oneshot_state(self):
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=1 PAUSE n=n+10 ENDMOVE MOVE AWAY 3',5,20,10)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['N'],1);now[0]+=1000000
        self.assertEqual(p.resume()['N'],11);self.assertEqual(triggered(ctx)[1],[1]);self.assertEqual(terminal(ctx),['completed']*3)

    def test_stop_inside_paused_action_cancels_queued_jobs(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO PAUSE ENDMOVE MOVE AWAY 3',5,20,10)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(terminal(ctx),['completed','cancelled','cancelled']);self.assertFalse(ctx.motion._queued)

    def test_abort_inside_promoted_action_cancels_batch(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO ABORT ENDMOVE MOVE AWAY 3',5,20,10)
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(terminal(ctx),['completed','cancelled','cancelled'])

    def test_hold_freezes_promoted_handler_and_waiters(self):
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO HOLD DELAY 30 UNHOLD n=7 ENDMOVE MOVE AWAY 3',5,20,10)
        self.assertEqual(p.run()['N'],7);self.assertEqual(now[0],65000);self.assertEqual(elapsed(ctx),[5,20,10])

    def test_global_cancel_precedes_queued_local_scan(self):
        body='n=0 CONNECT TIMER TO n CONDITION[1]: WHEN n>=5 DO CANCEL ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO s=99 ENDMOVE MOVE AWAY 3 s=7'
        p,ctx,_,_=run(body,5,20,0);self.assertEqual(p.run()['S'],7);self.assertEqual(triggered(ctx)[1],[])

    def test_no_final_callback_scan_after_last_delay(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE DELAY 50',10,20)
        self.assertEqual(p.run()['N'],0);self.assertEqual(terminal(ctx),['completed','cancelled'])


class QueuedClauseFrameTests(unittest.TestCase):
    def test_return_cancels_unstarted_callback_only(self):
        routines='ROUTINE work VAR local:INTEGER BEGIN local=7 MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=local ENDMOVE END work'
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT work() MOVE AWAY 3',50,20,0,routines=routines)
        self.assertEqual(p.run()['N'],0);self.assertEqual(terminal(ctx),['completed','cancelled','completed']);self.assertEqual(elapsed(ctx),[50,0,0])

    def test_return_frees_waiting_slot(self):
        ctx=bank(10,20,0,queue_limit=1)
        routines='ROUTINE work BEGIN MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE END work'
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT work() MOVE AWAY 3',ctx=ctx,routines=routines)
        self.assertEqual(p.run()['N'],0);self.assertEqual(terminal(ctx),['completed','cancelled','completed'])

    def test_early_return_cancels_unstarted_handler(self):
        routines='ROUTINE work:INTEGER BEGIN MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=99 ENDMOVE RETURN 7 END work'
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT s=work() MOVE AWAY 3',10,20,0,routines=routines)
        self.assertEqual((p.run()['N'],p.snapshot()['S']),(0,7));self.assertEqual(triggered(ctx)[1],[])

    def test_active_callback_frame_exit_cancels_its_batch(self):
        routines='ROUTINE work BEGIN MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=99 ENDMOVE MOVE AWAY 2 NOWAIT END work'
        p,ctx,_,_=run('n=0 ATTACH work()',10,20,routines=routines)
        self.assertEqual(p.run()['N'],0);self.assertEqual(terminal(ctx),['cancelled']*2)

    def test_queued_ancestor_capture_is_not_redirected_by_inner_frame(self):
        routines='ROUTINE inner VAR local:INTEGER BEGIN local=99 MOVE AWAY 3 s=local END inner ROUTINE work VAR local:INTEGER BEGIN local=7 MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=local ENDMOVE inner() END work'
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT work()',10,20,0,routines=routines)
        self.assertEqual((p.run()['N'],p.snapshot()['S']),(7,99));self.assertEqual(p._state.local_frames,[])

    def test_queued_formal_keeps_borrowed_caller_cell(self):
        routines='ROUTINE work(value:INTEGER) BEGIN MOVE AWAY 2 NOWAIT, WHEN TRUE DO value=7 ENDMOVE MOVE AWAY 3 s=value END work'
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT work(n)',10,20,0,routines=routines)
        self.assertEqual((p.run()['N'],p.snapshot()['S']),(7,7))

    def test_queued_grouped_formal_keeps_private_cell(self):
        routines='ROUTINE work(value:INTEGER) BEGIN MOVE AWAY 2 NOWAIT, WHEN TRUE DO value=7 ENDMOVE MOVE AWAY 3 s=value END work'
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT work((n))',10,20,0,routines=routines)
        self.assertEqual((p.run()['N'],p.snapshot()['S']),(0,7))

    def test_queued_callback_may_finish_before_routine_return(self):
        routines='ROUTINE work BEGIN MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE MOVE AWAY 3 END work'
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT work()',10,20,0,routines=routines)
        self.assertEqual(p.run()['N'],7);self.assertEqual(terminal(ctx),['completed']*3)

    def test_routine_timer_remains_live_while_queued(self):
        routines='ROUTINE work VAR ticks:INTEGER BEGIN ticks=0 CONNECT TIMER TO ticks MOVE AWAY 2 NOWAIT, WHEN ticks>=10 DO n=ticks ENDMOVE MOVE AWAY 3 END work'
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT work()',10,20,0,routines=routines)
        self.assertEqual(p.run()['N'],10);self.assertFalse(p._state._timers)

    def test_linked_live_routine_keeps_queue_callbacks(self):
        lib='PROGRAM LIB VAR local:INTEGER ROUTINE work BEGIN local=7 MOVE AWAY 2 NOWAIT, WHEN TRUE DO local=local+10 ENDMOVE MOVE AWAY 3 END work BEGIN END LIB'
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT work()',10,20,0,lib=lib)
        linked.run('MAIN');self.assertEqual(linked.programs['LIB'].snapshot()['LOCAL'],17)
        self.assertEqual([(r['program'],r['source_program']) for r in moves(ctx)],[('MAIN','MAIN'),('MAIN','LIB'),('MAIN','LIB')])

    def test_linked_return_cancels_unstarted_callback(self):
        lib='PROGRAM LIB VAR local:INTEGER ROUTINE work BEGIN local=7 MOVE AWAY 2 NOWAIT, WHEN TRUE DO local=99 ENDMOVE END work BEGIN END LIB'
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT work() MOVE AWAY 3',10,20,0,lib=lib)
        linked.run('MAIN');self.assertEqual(linked.programs['LIB'].snapshot()['LOCAL'],7);self.assertEqual(terminal(ctx),['completed','cancelled','completed'])

    def test_unstarted_inner_callback_removal_keeps_ancestor_job(self):
        routines='ROUTINE inner BEGIN MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=99 ENDMOVE END inner ROUTINE work BEGIN MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=88 ENDMOVE inner() MOVE AWAY 3 END work'
        p,ctx,_,_=run('n=0 ATTACH work()',10,20,0,routines=routines)
        self.assertEqual(p.run()['N'],0);self.assertEqual(terminal(ctx),['completed','cancelled','completed'])


class QueuedClauseGuardTests(unittest.TestCase):
    def paused(self):
        routines='ROUTINE work VAR local:INTEGER BEGIN local=7 MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=local ENDMOVE PAUSE END work'
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT work()',50,20,routines=routines)
        with self.assertRaises(rt.KarelPause):p.run()
        return p,ctx,now

    def test_dead_waiter_frame_rejects_before_clock_sample(self):
        p,ctx,_=self.paused();frames=list(p._state._timer_frames);p._state._timer_frames.pop()
        calls=[];original=p._state._clock_us
        def clock():calls.append(1);return original()
        p._state._clock_us=clock
        for scope in ctx.motion._scopes():scope['clock']=clock
        with self.assertRaisesRegex(rt.KarelRuntimeError,'frame is inactive'):ctx.motion.poll(p._state)
        self.assertEqual(calls,[]);self.assertEqual(terminal(ctx),['failed']*2)
        p._state._timer_frames[:]=frames;p.stop()

    def test_clock_side_effect_revalidates_waiter_frames(self):
        p,ctx,_=self.paused();frames=list(p._state._timer_frames);original=p._state._clock_us
        def clock():p._state._timer_frames.clear();return original()
        p._state._clock_us=clock
        for scope in ctx.motion._scopes():scope['clock']=clock
        with self.assertRaisesRegex(rt.KarelRuntimeError,'frame is inactive'):ctx.motion.poll(p._state)
        self.assertEqual(terminal(ctx),['failed']*2);p._state._timer_frames[:]=frames;p.stop()

    def test_changed_waiter_task_identity_fails_batch(self):
        p,ctx,_=self.paused();other,_,_,_=run('')
        ctx.motion._queued[1][0]['state']=other._state
        with self.assertRaisesRegex(rt.KarelRuntimeError,'defining task changed'):ctx.motion.poll(p._state)
        self.assertEqual(terminal(ctx),['failed']*2);p.stop()

    def test_changed_waiter_grant_fails_batch(self):
        p,ctx,_=self.paused();ctx.motion._queued[1][0]['grant']=object()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Queued motion lost'):ctx.motion.poll(p._state)
        self.assertEqual(terminal(ctx),['failed']*2);p.stop()

    def test_foreign_grant_is_preserved_when_queued_handler_fails(self):
        p,ctx,_=self.paused();foreign=object();ctx.group_locks.release_owner(p._state);ctx.group_locks._grant(1,foreign);ctx.group_locks.set_motion(1,'executing')
        with self.assertRaises(rt.KarelRuntimeError):ctx.motion.poll(p._state)
        self.assertIs(ctx.group_locks.owners[1],foreign);self.assertEqual(ctx.group_locks.motion[1],'executing');self.assertEqual(terminal(ctx),['failed']*2);p.stop()

    def test_changed_waiter_clock_fails_before_promotion(self):
        p,ctx,_=self.paused();ctx.motion._queued[1][0]['clock']=lambda:0
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Queued motion clock'):ctx.motion.poll(p._state)
        self.assertEqual(terminal(ctx),['failed']*2);p.stop()

    def test_handler_callable_smuggling_still_rejects(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT PAUSE',50,20)
        with self.assertRaises(rt.KarelPause):p.run()
        data=dict(delay_ms=20,elapsed_ms=0,handlers=[dict(kind='WHEN',line=1)],triggered=[])
        with self.assertRaises(rt.KarelRuntimeError):ctx.motion.invoke(p._state,'MOVE AWAY',dict(distance=2.),True,1,_execution=data,_background=True)
        self.assertEqual(len(ctx.motion.responses),1);p.stop()

    def test_waiter_admission_needs_original_task_context(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT PAUSE',50,20)
        with self.assertRaises(rt.KarelPause):p.run()
        clauses=[('WHEN',lambda:False,lambda:None,1)];data=dict(delay_ms=20,elapsed_ms=0,handlers=[dict(kind='WHEN',line=1)],triggered=[])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'defining frames'):
            ctx.motion.invoke(p._state,'MOVE AWAY',dict(distance=2.),True,1,_execution=data,_background=True,_clauses=clauses,_callback_context=(object(),()))
        self.assertEqual(len(ctx.motion.responses),1);p.stop()

    def test_full_queue_rejects_handler_before_consuming_reply(self):
        ctx=bank(50,20,30,queue_limit=1)
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT MOVE AWAY 3 NOWAIT, WHEN TRUE DO n=7 ENDMOVE',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):p.run()
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(len(moves(ctx)),2)

    def test_default_queue_still_rejects_second_handler_move(self):
        ctx=bank(50,20,queue_limit=0)
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'active request'):p.run()
        self.assertEqual(len(ctx.motion.responses),1)

    def test_blocking_local_clause_joins_queue(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',50,20)
        self.assertEqual(p.run()['N'],7);self.assertEqual(terminal(ctx),['completed']*2);self.assertEqual(triggered(ctx),[[],[1]])


class QueuedClauseCounterProofTests(unittest.TestCase):
    def test_pending_action_write_blocks_scalar_counter(self):
        with self.assertRaises(TranslationError):run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN FALSE DO n=7 ENDMOVE FOR n=1 TO 3 DO s=1 ENDFOR',10,20)

    def test_pending_predicate_write_blocks_scalar_counter(self):
        routines='ROUTINE ready:BOOLEAN BEGIN n=7 RETURN FALSE END ready'
        with self.assertRaises(TranslationError):run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN ready() DO s=1 ENDMOVE FOR n=1 TO 3 DO s=1 ENDFOR',10,20,routines=routines)

    def test_pending_builtin_output_blocks_counter(self):
        with self.assertRaises(TranslationError):run("ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN FALSE DO CNV_STR_INT('7',n) ENDMOVE FOR n=1 TO 3 DO s=1 ENDFOR",10,20)

    def test_pending_aggregate_write_protects_complete_counter_root(self):
        with self.assertRaises(TranslationError):run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN FALSE DO a[2]=7 ENDMOVE FOR a[1]=1 TO 3 DO s=1 ENDFOR',10,20)

    def test_pending_transitive_write_blocks_counter(self):
        routines='ROUTINE change BEGIN n=7 END change'
        with self.assertRaises(TranslationError):run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN FALSE DO change() ENDMOVE FOR n=1 TO 3 DO s=1 ENDFOR',10,20,routines=routines)

    def test_independent_counter_remains_usable(self):
        p,ctx,_,_=run('n=0 a[1]=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE FOR s=1 TO 3 DO a[1]=a[1]+1 ENDFOR MOVE AWAY 3',10,20,0)
        self.assertEqual(p.run()['N'],7);self.assertEqual(p.snapshot()['A'][0],3.)


class QueuedClauseSchedulerTests(unittest.TestCase):
    def test_waiting_owner_observes_handler_after_wakeup_without_spin(self):
        ctx=bank(10,20);ctx.motion.responses[1]['node_times']={'0':0,'1':20}
        linked,p,ctx=project('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN AT NODE[1] DO n=7 ENDMOVE DELAY 100 n=n+1',ctx=ctx)
        linked.run('MAIN');self.assertEqual(p.snapshot()['N'],8);self.assertEqual(terminal(ctx),['completed']*2)

    def test_scheduler_barrier_scans_callbacks(self):
        linked,p,ctx=project('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE MOVE AWAY 3',10,20,0)
        linked.run('MAIN');self.assertEqual(p.snapshot()['N'],7);self.assertEqual(terminal(ctx),['completed']*3)

    def test_scheduler_pause_retains_queued_handler(self):
        linked,p,ctx=project('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE MOVE AWAY 3',50,20,0)
        queued(linked,ctx);p.pause()
        for _ in range(100):
            linked.scheduler.step()
            if p.task_state=='paused':break
        self.assertEqual(p.task_state,'paused');before=elapsed(ctx);linked.scheduler.now_us+=100000
        linked.scheduler.step();self.assertEqual(elapsed(ctx),before)
        linked.scheduler.continue_task('MAIN');linked.scheduler.run();self.assertEqual(p.snapshot()['N'],7)

    def test_scheduler_stop_cancels_pending_handlers(self):
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE DELAY 100',50,20)
        queued(linked,ctx);linked.scheduler.stop('MAIN');self.assertEqual(terminal(ctx),['cancelled']*2);self.assertFalse(ctx.motion._queued)

    def test_scheduler_rename_preserves_callback_task(self):
        linked,p,ctx=project('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE MOVE AWAY 3',50,20,0)
        queued(linked,ctx);linked.scheduler.rename('MAIN','RENAMED');linked.scheduler.run()
        self.assertIs(linked.scheduler.tasks['RENAMED'],p);self.assertEqual(p.snapshot()['N'],7)

    def test_scheduler_clock_failure_fails_waiter_callbacks(self):
        now=[0];linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE DELAY 100',50,20,clock_us=lambda:now[0])
        queued(linked,ctx);now[0]=-1
        with self.assertRaises(rt.KarelRuntimeError):linked.scheduler.step()
        self.assertEqual(p.task_state,'failed');self.assertEqual(terminal(ctx),['failed']*2);self.assertFalse(ctx.motion._queued)

    def test_scheduler_pause_inside_promoted_callback(self):
        linked,p,ctx=project('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=1 PAUSE n=n+10 ENDMOVE MOVE AWAY 3',5,20,0)
        linked.run('MAIN');self.assertEqual(p.snapshot()['N'],1)
        linked.scheduler.continue_task('MAIN');linked.scheduler.run();self.assertEqual(p.snapshot()['N'],11);self.assertEqual(triggered(ctx)[1],[1])

    def test_foreign_task_does_not_execute_waiting_owner_callbacks(self):
        ctx=bank(10,20)
        docs={'main':source('MAIN','n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE DELAY 100 s=7'),
              'watch':source('WATCH','DELAY 50 n=peek()',routines='ROUTINE peek:INTEGER FROM HOST')}
        ctx.externals['HOST','PEEK']=lambda:linked.programs['MAIN'].snapshot()['N']
        linked=translate_project(docs).instantiate(context=ctx)
        linked.scheduler.start('MAIN');linked.scheduler.start('WATCH');linked.scheduler.run()
        self.assertEqual(linked.programs['WATCH'].snapshot()['N'],0);self.assertEqual(linked.programs['MAIN'].snapshot()['N'],7)

    def test_independent_groups_have_distinct_handler_consumers(self):
        ctx=bank(10,20,5,10,0,0,groups={1:2,2:2})
        lib='PROGRAM LIB\n%DEFGROUP=2\nVAR n:INTEGER ROUTINE work BEGIN n=0 MOVE AWAY 3 NOWAIT MOVE AWAY 4 NOWAIT, WHEN TRUE DO n=17 ENDMOVE MOVE AWAY 5 END work BEGIN END LIB'
        linked,p,ctx=project('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE work() MOVE AWAY 6',ctx=ctx,lib=lib)
        linked.run('MAIN');self.assertEqual(p.snapshot()['N'],7);self.assertEqual(linked.programs['LIB'].snapshot()['N'],17)
        self.assertEqual(terminal(ctx),['completed']*6)

    def test_qualified_callback_cancel_preserves_other_group(self):
        ctx=bank(1000,5,10,0,0,groups={1:2,2:2})
        lib='PROGRAM LIB\n%DEFGROUP=2\nVAR n:INTEGER ROUTINE work BEGIN n=0 MOVE AWAY 3 NOWAIT MOVE AWAY 4 NOWAIT, UNTIL TRUE THEN n=17 ENDMOVE MOVE AWAY 5 END work BEGIN END LIB'
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT work() MOVE AWAY 6',ctx=ctx,lib=lib)
        linked.run('MAIN');self.assertEqual(linked.programs['LIB'].snapshot()['N'],17)
        self.assertEqual(terminal(ctx),['completed','completed','cancelled','cancelled','completed'])
        self.assertEqual([r['data']['groups'] for r in ctx.motion.history if r['operation']=='CANCEL'],[[2]])


class QueuedClauseDataTests(unittest.TestCase):
    def completed(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE MOVE AWAY 3',10,20,0);p.run();return p,ctx

    def test_completed_history_roundtrip(self):
        _,ctx=self.completed();saved=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_cancelled_history_roundtrip(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, UNTIL TRUE THEN n=7 ENDMOVE MOVE AWAY 3',10,20,0)
        p.run();saved=ctx.to_config();self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_failed_history_roundtrip(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=1 DIV 0 ENDMOVE MOVE AWAY 3',10,20,0)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        saved=ctx.to_config();self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_expired_waiter_history_roundtrip(self):
        routines='ROUTINE work BEGIN MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE END work'
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT work() MOVE AWAY 3',10,20,0,routines=routines)
        p.run();saved=ctx.to_config();self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_waiting_handlers_cannot_be_saved(self):
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE DELAY 100',50,20)
        queued(linked,ctx)
        with self.assertRaisesRegex(ValueError,'active motion'):ctx.motion.to_config()
        linked.scheduler.stop('MAIN')

    def test_pending_handler_history_still_cannot_load(self):
        _,ctx=self.completed();saved=ctx.motion.to_config();saved['history'][2]['outcome']='pending'
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)

    def test_terminal_metadata_never_stores_callbacks_or_frames(self):
        _,ctx=self.completed();data=json.dumps(ctx.motion.to_config())
        for name in ('local_frames','_scopes','scanning','clock_us','predicate','<function'):
            self.assertNotIn(name,data)

    def test_history_eviction_does_not_discard_queued_callback(self):
        ctx=bank(10,20,0,limit=1)
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE MOVE AWAY 3',ctx=ctx)
        self.assertEqual(p.run()['N'],7);self.assertFalse(ctx.motion._queued);self.assertFalse(ctx.motion._active)

    def test_triggered_until_requires_cancelled_or_failed_history(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, UNTIL TRUE THEN n=7 ENDMOVE MOVE AWAY 3',10,20,0);p.run()
        saved=ctx.motion.to_config();saved['history'][2]['outcome']='completed';saved['history'][2]['data']['execution']['elapsed_ms']=20
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)

    def test_malformed_handler_metadata_still_rejects(self):
        _,ctx=self.completed();saved=ctx.motion.to_config();saved['history'][2]['data']['execution']['handlers'][0]['kind']='INVALID'
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)


class QueuedClauseAdmissionTests(unittest.TestCase):
    def test_false_waiter_reply_consumes_only_that_rejection(self):
        ctx=bank(50,20,30);ctx.motion.responses[1]['completed']=False
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'completion rejected'):p.run()
        self.assertEqual(terminal(ctx),['cancelled','rejected']);self.assertEqual(len(ctx.motion.responses),1)

    def test_held_group_rejects_waiting_handler(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT HOLD MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE',50,20)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'without a hold'):p.run()
        self.assertEqual(len(ctx.motion.responses),1)

    def test_bad_waiter_schedule_keeps_reply(self):
        ctx=bank(50,20);ctx.motion.responses[1]['node_times']={'0':0,'2':20}
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN AT NODE[1] DO n=7 ENDMOVE',ctx=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(len(ctx.motion.responses),1)

    def test_later_source_failure_cancels_unstarted_handlers(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE n=1 DIV 0',50,20)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(terminal(ctx),['cancelled']*2);self.assertEqual(triggered(ctx)[1],[])

    def test_no_implicit_handler_after_normal_root_completion(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE',50,20)
        self.assertEqual(p.run()['N'],0);self.assertEqual(terminal(ctx),['cancelled']*2)

    def test_release_does_not_force_queued_callback_progress(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE RELEASE',50,20)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'idle logical group'):p.run()
        self.assertEqual(terminal(ctx),['cancelled']*2)

    def test_ordinary_callback_reentry_does_not_bypass_move_guard(self):
        with self.assertRaises(TranslationError):run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO MOVE AWAY 3 ENDMOVE',50,20,30)


class QueuedClauseFiniteConsumerTests(unittest.TestCase):
    def test_maximum_waiting_slots_drain_zero_handler_jobs(self):
        ctx=bank(1,*([0]*127),queue_limit=127)
        clauses=' '.join('MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=n+1 ENDMOVE' for _ in range(126))
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT '+clauses+' MOVE AWAY 3',ctx=ctx)
        self.assertEqual(p.run()['N'],126);self.assertEqual(now[0],1000);self.assertEqual(terminal(ctx),['completed']*128)

    def test_waiter_event_consumers_are_independent(self):
        body='n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN EVENT[1] DO n=n+1 ENDMOVE MOVE AWAY 3 NOWAIT, WHEN EVENT[1] DO n=n+10 ENDMOVE SIGNAL EVENT[1] MOVE AWAY 4'
        p,ctx,_,_=run(body,10,5,5,0);self.assertEqual(p.run()['N'],11)
        self.assertEqual(triggered(ctx),[[],[1],[1],[]]);self.assertEqual(p._state._event_seen,{})

    def test_global_event_cursor_is_independent_and_local_cursors_clean(self):
        body='n=0 CONDITION[1]: WHEN EVENT[1] DO n=n+1 ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN EVENT[1] DO n=n+10 ENDMOVE MOVE AWAY 3 NOWAIT, WHEN EVENT[1] DO n=n+100 ENDMOVE SIGNAL EVENT[1] MOVE AWAY 4'
        p,ctx,_,_=run(body,10,5,5,0);self.assertEqual(p.run()['N'],111);self.assertEqual({key[0] for key in p._state._event_seen},{1})

    def test_maximum_clause_count_on_queued_job(self):
        clauses=' '.join('WHEN FALSE DO n=99' for _ in range(31))+' WHEN TRUE DO n=7'
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, '+clauses+' ENDMOVE MOVE AWAY 3',10,5,0)
        self.assertEqual(p.run()['N'],7);self.assertEqual(triggered(ctx)[1],[32])


if __name__=='__main__':
    unittest.main()
