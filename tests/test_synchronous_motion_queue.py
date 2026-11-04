"""Blocking source MOVE admission, FIFO waits and cooperative interruption."""
import json
import unittest

from karel2py import runtime as rt, translate_project
from tests.test_queued_motion import run, bank, moves, elapsed
from tests.test_motion_requests import context
from tests.test_project_scheduler import source


def project(body, *delays, ctx=None, lib=None, **options):
    ctx=ctx or bank(*delays)
    docs={'main':source('MAIN',body,routines='ROUTINE work FROM LIB' if lib else '')}
    if lib:docs['lib']=lib
    linked=translate_project(docs).instantiate(context=ctx,options=options)
    return linked,linked.programs['MAIN'],ctx


def waiting(linked,ctx):
    linked.scheduler.start('MAIN')
    for _ in range(200):
        linked.scheduler.step()
        if any(not row['nowait'] and row['outcome']=='pending' for row in moves(ctx)):return
    raise AssertionError('Blocking MOVE never admitted a pending FIFO scope')


class SynchronousQueueProgressTests(unittest.TestCase):
    def test_blocking_move_completes_both_jobs_before_next_source_statement(self):
        seen=[]
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 inspect() n=7',10,20,routines='ROUTINE inspect FROM HOST')
        ctx.externals['HOST','INSPECT']=lambda:seen.append([r['outcome'] for r in moves(ctx)])
        self.assertEqual(p.run()['N'],7);self.assertEqual(seen,[['completed']*2]);self.assertEqual(now[0],30000)
        self.assertEqual([r['nowait'] for r in moves(ctx)],[True,False]);self.assertEqual(elapsed(ctx),[10,20])

    def test_waits_for_every_predecessor(self):
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT MOVE AWAY 3',7,8,9)
        p.run();self.assertEqual(elapsed(ctx),[7,8,9]);self.assertEqual(now[0],24000)

    def test_zero_duration_waiter_is_still_a_barrier(self):
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',25,0)
        p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2);self.assertEqual(now[0],25000)
        self.assertEqual(elapsed(ctx),[25,0])

    def test_unspecified_duration_is_zero_but_waits_for_predecessor(self):
        ctx=bank(25,0);ctx.motion.responses[1].pop('delay_ms')
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',ctx=ctx)
        p.run();self.assertEqual(now[0],25000);self.assertEqual(elapsed(ctx),[25,0])

    def test_non_multiple_of_poll_quantum_has_no_extra_whole_sleep(self):
        sleeps=[]
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',11,12,sleep=sleeps.append)
        p.run();self.assertEqual(now[0],23000);self.assertEqual(sleeps,[.01,.001,.01,.002])

    def test_new_batch_after_synchronous_completion(self):
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 MOVE AWAY 3 NOWAIT MOVE AWAY 4',5,6,7,8)
        p.run();self.assertEqual(elapsed(ctx),[5,6,7,8]);self.assertEqual(now[0],26000)

    def test_all_seven_move_forms_and_via_block_in_the_queue(self):
        forms=[('MOVE TO p VIA q','MOVE TO'),('MOVE NEAR p BY 1','MOVE NEAR'),('MOVE AWAY 1','MOVE AWAY'),('MOVE ABOUT v BY 2','MOVE ABOUT'),('MOVE AXIS 2 BY 3','MOVE AXIS'),('MOVE RELATIVE v','MOVE RELATIVE'),('MOVE ALONG route','MOVE ALONG')]
        for statement,operation in forms:
            with self.subTest(statement=statement):
                ctx=bank(5,7,operations=['MOVE AWAY',operation])
                p,ctx,now,_=run('ATTACH APPEND_NODE(route,s) route[1].node_pos=p MOVE AWAY 1 NOWAIT '+statement,ctx=ctx)
                p.run();self.assertEqual(elapsed(ctx),[5,7]);self.assertEqual(now[0],12000)
                self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2)

    def test_direct_dispatcher_and_cooperative_engines(self):
        for label,cooperative in (('',False),('entry:: ',False),('',True)):
            with self.subTest(label=label,cooperative=cooperative):
                p,ctx,now,_=run(label+'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',10,20,cooperative=cooperative)
                p.run();self.assertEqual(elapsed(ctx),[10,20]);self.assertEqual(now[0],30000)

    def test_existing_idle_synchronous_progress_is_preserved(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1',25,clock=lambda:0)
        p.run();self.assertEqual(elapsed(ctx),[25]);self.assertFalse(moves(ctx)[0]['nowait'])

    def test_existing_idle_immediate_shape_is_preserved(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1',0)
        p.run();self.assertNotIn('execution',moves(ctx)[0]['data'])

    def test_capture_only_remains_immediate(self):
        ctx=context(queue_limit=8)
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',ctx=ctx)
        p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['captured']*2);self.assertEqual(now[0],0)

    def test_response_node_schedule_is_retained(self):
        ctx=bank(10,20);ctx.motion.responses[1]['node_times']={'0':0,'1':20}
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',ctx=ctx)
        p.run();self.assertEqual(moves(ctx)[1]['data']['execution']['node_times'],{'0':0,'1':20})

    def test_operands_and_settings_evaluated_once(self):
        routines='ROUTINE distance:INTEGER BEGIN n=n+1 RETURN n END distance ROUTINE speed:INTEGER BEGIN n=n+10 RETURN n END speed'
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT\nWITH $SPEED=speed() MOVE AWAY distance()',10,20,routines=routines)
        self.assertEqual(p.run()['N'],11);row=moves(ctx)[1]
        self.assertEqual(row['data']['distance'],11.);self.assertEqual(row['data']['settings'],[dict(name='$SPEED',group=1,value=10.)])

    def test_target_detaches_before_waiting_handlers_change_it(self):
        ctx=bank(50,20,operations=['MOVE AWAY','MOVE TO'])
        body='n=0 CONNECT TIMER TO n CONDITION[1]: WHEN n>=10 DO p.x=999 ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT MOVE TO p'
        p,ctx,_,_=run(body,ctx=ctx);self.assertEqual(p.run()['P']['X'],999.)
        self.assertEqual(moves(ctx)[1]['data']['target']['value']['X'],10.)

    def test_path_nodes_detach_before_waiting_handlers_change_them(self):
        ctx=bank(50,20,operations=['MOVE AWAY','MOVE ALONG'])
        body='APPEND_NODE(route,s) route[1].node_pos=p n=0 CONNECT TIMER TO n CONDITION[1]: WHEN n>=10 DO p.x=999 route[1].node_pos=p ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT MOVE ALONG route'
        p,ctx,_,_=run(body,ctx=ctx);p.run();self.assertEqual(moves(ctx)[1]['data']['nodes'][0]['value']['LOCATION']['X'],10.)

    def test_joint_target_detaches_before_later_source_mutation(self):
        ctx=bank(10,20,operations=['MOVE AWAY','MOVE TO'])
        p,ctx,_,_=run('a[1]=5 a[2]=8 CNV_REL_JPOS(a,j,s) ATTACH MOVE AWAY 1 NOWAIT MOVE TO j a[1]=99 CNV_REL_JPOS(a,j,s)',ctx=ctx)
        p.run();self.assertEqual(moves(ctx)[1]['data']['target']['value']['axes'],[5.,8.])

    def test_local_routine_waits_before_returning_result(self):
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT n=work()',10,20,routines='ROUTINE work:INTEGER BEGIN MOVE AWAY 2 RETURN 7 END work')
        self.assertEqual(p.run()['N'],7);self.assertEqual(now[0],30000);self.assertEqual(p._state.local_frames,[])

    def test_history_eviction_does_not_break_wait(self):
        ctx=bank(10,20,limit=1)
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',ctx=ctx);p.run()
        self.assertEqual(len(ctx.motion.history),1);self.assertEqual(moves(ctx)[0]['outcome'],'completed');self.assertEqual(elapsed(ctx),[20])


class SynchronousQueueAdmissionTests(unittest.TestCase):
    def reject(self,ctx,body,pattern):
        p,ctx,_,_=run(body,ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,pattern):p.run()
        self.assertEqual((ctx.motion._active,ctx.motion._queued,ctx.group_locks.owners),({},{},{}))
        return ctx

    def test_default_disabled_queue_still_rejects_busy_group(self):
        ctx=self.reject(bank(10,20,queue_limit=0),'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2','active request')
        self.assertEqual(len(ctx.motion.responses),1)

    def test_capacity_is_checked_before_waiting_or_consumption(self):
        ctx=self.reject(bank(10,20,30,queue_limit=1),'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT MOVE AWAY 3','capacity')
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(len(moves(ctx)),2)

    def test_held_group_still_rejects_new_synchronous_move(self):
        ctx=self.reject(bank(10,20),'ATTACH MOVE AWAY 1 NOWAIT HOLD MOVE AWAY 2','without a hold')
        self.assertEqual(len(ctx.motion.responses),1);self.assertIn(1,ctx.group_locks.held)

    def test_false_response_is_rejected_at_admission(self):
        ctx=bank(10,20);ctx.motion.responses[1]['completed']=False
        self.reject(ctx,'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2','completion rejected')
        self.assertEqual(ctx.motion.responses,[]);self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled','rejected'])

    def test_wrong_response_does_not_consume_or_publish(self):
        ctx=bank(10,20,operations=['MOVE AWAY','MOVE AXIS'])
        self.reject(ctx,'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2','matching completion')
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(len(moves(ctx)),1)

    def test_invalid_axis_does_not_consume(self):
        ctx=bank(10,20,operations=['MOVE AWAY','MOVE AXIS'])
        self.reject(ctx,'ATTACH MOVE AWAY 1 NOWAIT MOVE AXIS 9 BY 1','axis')
        self.assertEqual(len(ctx.motion.responses),1)

    def test_bad_schedule_does_not_consume(self):
        ctx=bank(10,20);ctx.motion.responses[1]['node_times']={'0':0,'2':20}
        self.reject(ctx,'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2','selected move range')
        self.assertEqual(len(ctx.motion.responses),1)

    def test_callback_waiter_does_not_join(self):
        ctx=self.reject(bank(10,20),'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN FALSE DO n=7 ENDMOVE','active request')
        self.assertEqual(len(ctx.motion.responses),1)

    def test_callback_head_does_not_accept_synchronous_waiter(self):
        ctx=self.reject(bank(10,20),'ATTACH MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=7 ENDMOVE MOVE AWAY 2','active request')
        self.assertEqual(len(ctx.motion.responses),1)

    def test_sequence_exhaustion_leaves_reply(self):
        ctx=self.reject(bank(10,20,sequence=2147483644),'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2','sequence exhausted')
        self.assertEqual(len(ctx.motion.responses),1)

    def test_other_task_cannot_join_batch(self):
        ctx=bank(10,20);owner,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT PAUSE',ctx=ctx)
        with self.assertRaises(rt.KarelPause):owner.run()
        other,ctx,_,_=run('MOVE AWAY 2',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'same task'):other.run()
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(moves(ctx)[0]['outcome'],'pending');owner.stop()

    def test_direct_invoke_output_is_not_a_blocking_wait(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT PAUSE',10,20)
        with self.assertRaises(rt.KarelPause):p.run()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'generated NOWAIT'):ctx.motion.invoke(p._state,'MOVE AWAY',dict(distance=2.),False,9)
        self.assertEqual(len(ctx.motion.responses),1);p.stop()


class SynchronousQueueControlsTests(unittest.TestCase):
    def test_global_handler_cancels_and_source_continues(self):
        body='n=0 CONNECT TIMER TO n CONDITION[1]: WHEN n>=10 DO CANCEL ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 s=7'
        p,ctx,_,_=run(body,50,20);self.assertEqual(p.run()['S'],7)
        self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*2);self.assertEqual(elapsed(ctx),[10,0])

    def test_global_handler_hold_delay_and_unhold_excludes_frozen_time(self):
        body='n=0 CONNECT TIMER TO n CONDITION[1]: WHEN n>=10 DO HOLD DELAY 20 UNHOLD ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2'
        p,ctx,now,_=run(body,50,20);p.run();self.assertEqual(elapsed(ctx),[50,20]);self.assertEqual(now[0],90000)

    def test_global_handler_time_counts_as_background_progress(self):
        body='n=0 CONNECT TIMER TO n CONDITION[1]: WHEN n>=10 DO DELAY 100 ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2'
        p,ctx,now,_=run(body,50,20);p.run();self.assertEqual(elapsed(ctx),[50,20]);self.assertEqual(now[0],110000)

    def paused(self):
        requested=[False]
        def sleep(_):
            if not requested[0]:requested[0]=True;p.pause()
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 n=7',50,20,sleep=sleep)
        with self.assertRaises(rt.KarelPause):p.run()
        return p,ctx,now

    def test_pause_resume_excludes_pause_interval(self):
        p,ctx,now=self.paused();before=elapsed(ctx);now[0]+=1000000
        ctx.motion.poll(p._state);self.assertEqual(elapsed(ctx),before)
        self.assertEqual(p.resume()['N'],7);self.assertEqual(elapsed(ctx),[50,20]);self.assertFalse(ctx.motion._queued)

    def test_stop_paused_wait_cancels_batch(self):
        p,ctx,_=self.paused();p.stop();self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*2)
        self.assertEqual((ctx.motion._active,ctx.motion._queued,ctx.group_locks.owners),({},{},{}))

    def test_abort_during_wait_cancels_batch(self):
        def sleep(_):p._state._abort_requested=True
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',50,20,sleep=sleep)
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*2)

    def test_sleep_failure_marks_waiter_failed_and_cancels_predecessor(self):
        def sleep(_):raise ValueError('authored sleeper failure')
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',50,20,sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Host DELAY sleeper failed'):p.run()
        self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled','failed']);self.assertFalse(ctx.motion._queued)

    def test_stalled_custom_clock_retains_step_budget(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',50,20,clock=lambda:0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=40)
        self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled','failed']);self.assertFalse(ctx.motion._queued)

    def test_release_succeeds_immediately_after_wait(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 RELEASE',10,20)
        p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2);self.assertFalse(ctx.group_locks.owners)

    def test_source_stop_after_wait_keeps_completed_outcomes(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 STOP',10,20)
        with self.assertRaises(rt.KarelStop):p.run()
        self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2)


class SynchronousQueueSchedulerTests(unittest.TestCase):
    def test_scheduler_source_waits_until_own_job_completes(self):
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 n=7 RELEASE',10,20)
        linked.run('MAIN');self.assertEqual(p.snapshot()['N'],7);self.assertEqual(elapsed(ctx),[10,20])

    def test_admitted_waiter_blocks_later_source(self):
        linked,p,ctx=project('n=1 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 n=7',50,20)
        waiting(linked,ctx);self.assertEqual(p.snapshot()['N'],1);linked.scheduler.run();self.assertEqual(p.snapshot()['N'],7)

    def test_scheduler_pause_retains_waiter(self):
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 n=7',50,20)
        waiting(linked,ctx);p.pause()
        for _ in range(100):
            linked.scheduler.step()
            if p.task_state=='paused':break
        self.assertEqual(p.task_state,'paused');before=elapsed(ctx)
        linked.scheduler.now_us+=100000;linked.scheduler.step();self.assertEqual(elapsed(ctx),before)
        linked.scheduler.continue_task('MAIN');linked.scheduler.run();self.assertEqual(p.snapshot()['N'],7);self.assertEqual(elapsed(ctx),[50,20])

    def test_scheduler_stop_cancels_waiting_task(self):
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',50,20)
        waiting(linked,ctx);linked.scheduler.stop('MAIN')
        self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*2);self.assertFalse(ctx.motion._queued);self.assertFalse(ctx.group_locks.owners)

    def test_scheduler_rename_retains_wait_identity(self):
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 n=7',50,20)
        waiting(linked,ctx);linked.scheduler.rename('MAIN','RENAMED');linked.scheduler.run()
        self.assertIs(linked.scheduler.tasks['RENAMED'],p);self.assertEqual(p.snapshot()['N'],7);self.assertEqual(elapsed(ctx),[50,20])

    def test_linked_synchronous_routine_blocks_before_return(self):
        lib='PROGRAM LIB ROUTINE work BEGIN MOVE AWAY 2 END work BEGIN END LIB'
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT work() n=7',10,20,lib=lib)
        linked.run('MAIN');self.assertEqual(p.snapshot()['N'],7)
        self.assertEqual([(r['program'],r['source_program']) for r in moves(ctx)],[('MAIN','MAIN'),('MAIN','LIB')]);self.assertEqual(elapsed(ctx),[10,20])

    def test_linked_nowait_launch_then_root_wait(self):
        lib='PROGRAM LIB ROUTINE work BEGIN MOVE AWAY 1 NOWAIT END work BEGIN END LIB'
        linked,p,ctx=project('ATTACH work() MOVE AWAY 2 n=7',10,20,lib=lib)
        linked.run('MAIN');self.assertEqual(elapsed(ctx),[10,20]);self.assertEqual(p.snapshot()['N'],7)

    def test_group_wait_does_not_wait_for_unrelated_group(self):
        ctx=bank(1000,10,20,groups={1:2,2:2})
        lib='PROGRAM LIB\n%DEFGROUP=2\nROUTINE work BEGIN MOVE AWAY 3 NOWAIT MOVE AWAY 4 END work BEGIN END LIB'
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT work() n=7',ctx=ctx,lib=lib)
        linked.run('MAIN');self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled','completed','completed'])
        self.assertLess(elapsed(ctx)[0],1000);self.assertEqual(elapsed(ctx)[1:],[10,20])

    def test_scheduler_clock_failure_fails_batch_and_owner(self):
        now=[0];linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',50,20,clock_us=lambda:now[0])
        waiting(linked,ctx);now[0]=-1
        with self.assertRaises(rt.KarelRuntimeError):linked.scheduler.step()
        self.assertEqual(p.task_state,'failed');self.assertEqual([r['outcome'] for r in moves(ctx)],['failed']*2)
        self.assertFalse(ctx.motion._queued);self.assertFalse(linked.scheduler.waiting)

    def test_custom_clock_does_not_gain_inferred_deadlines(self):
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',50,20,clock_us=lambda:0)
        waiting(linked,ctx);self.assertEqual(ctx.motion.deadlines(linked.scheduler),[]);linked.scheduler.stop('MAIN')


class SynchronousQueuePersistenceTests(unittest.TestCase):
    def test_completed_blocking_history_roundtrips(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',10,20);p.run()
        saved=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_cancelled_blocking_history_roundtrips(self):
        body='n=0 CONNECT TIMER TO n CONDITION[1]: WHEN n>=10 DO CANCEL ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2'
        p,ctx,_,_=run(body,50,20);p.run();saved=ctx.to_config();self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_active_wait_cannot_be_saved(self):
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',50,20)
        waiting(linked,ctx)
        with self.assertRaisesRegex(ValueError,'active motion'):ctx.motion.to_config()
        linked.scheduler.stop('MAIN')

    def test_pending_blocking_history_cannot_reload(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',10,20);p.run()
        saved=ctx.motion.to_config();saved['history'][-1]['outcome']='pending'
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)


class SynchronousQueueBoundaryTests(unittest.TestCase):
    def test_replaced_clock_fails_wait_and_batch(self):
        def sleep(_):p._state._clock_us=lambda:0
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',50,20,sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'adapter changed'):p.run()
        self.assertEqual([r['outcome'] for r in moves(ctx)],['failed']*2);self.assertFalse(ctx.motion._queued)

    def test_backwards_clock_fails_wait_and_batch(self):
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT DELAY 10 MOVE AWAY 2',50,20)
        # The first authored delay establishes progress before the clock reversal.
        calls=[0]
        def reverse(_):
            calls[0]+=1
            if calls[0]>1:now[0]=0
        def sleeper(seconds):
            now[0]+=round(seconds*1000000);reverse(seconds)
        p._state._sleep=sleeper
        with self.assertRaisesRegex(rt.KarelRuntimeError,'backwards'):p.run()
        self.assertEqual([r['outcome'] for r in moves(ctx)],['failed']*2)

    def test_foreign_ownership_after_wait_begins_is_preserved(self):
        foreign=object()
        def sleep(_):
            ctx.group_locks.release_owner(p._state);ctx.group_locks._grant(1,foreign);ctx.group_locks.set_motion(1,'executing')
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',50,20,sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ownership grant'):p.run()
        self.assertIs(ctx.group_locks.owners[1],foreign);self.assertEqual(ctx.group_locks.motion[1],'executing')
        self.assertEqual([r['outcome'] for r in moves(ctx)],['failed']*2)

    def test_external_stopped_label_is_preserved(self):
        def sleep(_):ctx.group_locks.set_motion(1,'stopped')
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',50,20,sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'work label'):p.run()
        self.assertEqual(ctx.group_locks.motion[1],'stopped');self.assertEqual([r['outcome'] for r in moves(ctx)],['failed']*2)

    def test_handler_cancel_during_own_active_phase_continues_source(self):
        body='n=0 CONNECT TIMER TO n CONDITION[1]: WHEN n>=20 DO CANCEL ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 s=7'
        p,ctx,_,_=run(body,10,50);self.assertEqual(p.run()['S'],7)
        self.assertEqual([r['outcome'] for r in moves(ctx)],['completed','cancelled']);self.assertEqual(elapsed(ctx),[10,10])

    def test_cancelled_waiter_does_not_consume_following_reply(self):
        body='n=0 CONNECT TIMER TO n CONDITION[1]: WHEN n>=10 DO CANCEL ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2'
        p,ctx,_,_=run(body,50,20,30);p.run();self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(ctx.motion.responses[0]['delay_ms'],30)

    def test_cancelled_waiter_allows_new_source_batch(self):
        body='n=0 CONNECT TIMER TO n CONDITION[1]: WHEN n>=10 DO CANCEL ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 MOVE AWAY 3 NOWAIT MOVE AWAY 4'
        p,ctx,_,_=run(body,50,20,7,8);p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled','cancelled','completed','completed'])

    def test_local_condition_handlers_work_while_linked_wait_is_active(self):
        lib='PROGRAM LIB VAR t:INTEGER ROUTINE work BEGIN t=0 CONNECT TIMER TO t CONDITION[1]: WHEN t>=10 DO CANCEL ENDCONDITION ENABLE CONDITION[1] MOVE AWAY 2 END work BEGIN END LIB'
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT work() n=7',50,20,lib=lib)
        linked.run('MAIN');self.assertEqual(p.snapshot()['N'],7);self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*2)

    def test_parent_condition_handlers_work_while_linked_wait_is_active(self):
        lib='PROGRAM LIB ROUTINE work BEGIN MOVE AWAY 2 END work BEGIN END LIB'
        body='n=0 CONNECT TIMER TO n CONDITION[1]: WHEN n>=10 DO CANCEL ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT work() s=7'
        linked,p,ctx=project(body,50,20,lib=lib);linked.run('MAIN')
        self.assertEqual(p.snapshot()['S'],7);self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*2)

    def test_disabled_queue_local_clauses_still_use_synchronous_steps(self):
        ctx=bank(25,queue_limit=0)
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1, WHEN TRUE DO n=7 ENDMOVE',ctx=ctx)
        self.assertEqual(p.run()['N'],7);self.assertEqual(elapsed(ctx),[25])

    def test_enabled_idle_local_clauses_still_use_synchronous_steps(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1, WHEN TRUE DO n=7 ENDMOVE',25)
        self.assertEqual(p.run()['N'],7);self.assertEqual(elapsed(ctx),[25])

    def test_wait_cannot_escape_missing_admitted_scope(self):
        # An external host discards the explicit job. A source wait must fail,
        # rather than accepting an idle label as successful completion.
        def sleep(_):
            ctx.motion._queued.clear();ctx.motion._active.clear();ctx.group_locks.set_motion(1,'idle')
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',50,20,sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'lost its admitted scope'):p.run()
        self.assertEqual(moves(ctx)[1]['outcome'],'failed')

    def test_retained_failed_terminal_result_never_returns_success(self):
        def sleep(_):ctx.motion.finish_scope(ctx.motion._active[1],'failed')
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 n=7',50,20,sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'did not complete successfully'):p.run()
        self.assertNotEqual(p.snapshot().get('N'),7);self.assertEqual([r['outcome'] for r in moves(ctx)],['failed']*2)

    def test_failed_history_roundtrips_after_wait_error(self):
        def sleep(_):p._state._clock_us=lambda:0
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',50,20,sleep=sleep)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        saved=ctx.to_config();self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_snapshot_does_not_store_wait_generators(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',10,20);p.run()
        data=json.dumps(ctx.to_config());self.assertNotIn('wait_for_scope',data);self.assertNotIn('_queue_wait',data)


class SynchronousQueueCapacityAndFramesTests(unittest.TestCase):
    def test_blocking_wait_uses_last_available_slot(self):
        ctx=bank(1,*([0]*127),queue_limit=127)
        body='ATTACH '+' '.join('MOVE AWAY 1 NOWAIT' for _ in range(127))+' MOVE AWAY 2'
        p,ctx,now,_=run(body,ctx=ctx);p.run()
        self.assertEqual(len(moves(ctx)),128);self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*128)
        self.assertEqual(now[0],1000);self.assertFalse(ctx.motion._queued)

    def test_blocking_wait_does_not_overflow_maximum_capacity(self):
        ctx=bank(1,*([0]*128),queue_limit=127)
        body='ATTACH '+' '.join('MOVE AWAY 1 NOWAIT' for _ in range(128))+' MOVE AWAY 2'
        p,ctx,_,_=run(body,ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):p.run()
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*128)

    def test_budget_failure_after_promotion_keeps_completed_predecessor(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',10,100000)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=40)
        self.assertEqual([r['outcome'] for r in moves(ctx)],['completed','failed']);self.assertFalse(ctx.motion._active)

    def test_completed_predecessor_does_not_force_a_new_fifo_scope(self):
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT DELAY 10 MOVE AWAY 2',10,0)
        p.run();self.assertNotIn('execution',moves(ctx)[1]['data']);self.assertEqual(now[0],10000)

    def test_routine_timer_and_parameter_stay_live_during_wait(self):
        routines='ROUTINE work(value:INTEGER):INTEGER VAR t:INTEGER BEGIN t=0 CONNECT TIMER TO t MOVE AWAY value RETURN t END work'
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT n=work(2)',10,20,routines=routines)
        self.assertEqual(p.run()['N'],30);self.assertEqual(p._state.local_frames,[]);self.assertFalse(p._state._timers)

    def test_independent_idle_synchronous_group_keeps_existing_progress(self):
        ctx=bank(10,20,30,groups={1:2,2:2})
        lib='PROGRAM LIB\n%DEFGROUP=2\nROUTINE work BEGIN MOVE AWAY 3 END work BEGIN END LIB'
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT work()',ctx=ctx,lib=lib)
        linked.run('MAIN');self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*3);self.assertEqual(elapsed(ctx),[10,20,30])


if __name__=='__main__':
    unittest.main()
