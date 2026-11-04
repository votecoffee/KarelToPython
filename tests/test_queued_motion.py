"""Authored finite callback-free FIFO motion, ownership and task lifetime."""
import json
import unittest

from karel2py import runtime as rt, translate_project
from tests.test_motion_requests import context
from tests.test_nowait_motion import build, active
from tests.test_project_scheduler import source


def bank(*delays, queue_limit=8, operations=None, **options):
    operations = operations or ['MOVE AWAY'] * len(delays)
    return context(capture_only=False, queue_limit=queue_limit,
        responses=[dict(operation=operation, completed=True, delay_ms=delay)
                   for operation, delay in zip(operations, delays)], **options)


def moves(ctx):
    return [row for row in ctx.motion.history if row['operation'].startswith('MOVE ')]


def elapsed(ctx):
    return [row['data']['execution']['elapsed_ms'] for row in moves(ctx)]


def run(body, *delays, ctx=None, routines='', **options):
    ctx = ctx or bank(*delays)
    p, ctx, now, seen, result = build(body, ctx=ctx, routines=routines, **options)
    return p, ctx, now, result


class QueueProgressTests(unittest.TestCase):
    def test_fifo_and_source_continuation(self):
        snapshots=[]
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT MOVE AWAY 3 NOWAIT n=7 inspect() DELAY 30 inspect()',10,10,10,routines='ROUTINE inspect FROM HOST')
        ctx.externals['HOST','INSPECT']=lambda:snapshots.append((elapsed(ctx),[r['outcome'] for r in moves(ctx)]))
        self.assertEqual(p.run()['N'],7)
        self.assertEqual(snapshots,[([0,0,0],['pending']*3),([10,10,10],['completed']*3)])
        self.assertEqual((ctx.motion._active,ctx.motion._queued,ctx.motion.responses),({},{},[]))

    def test_waiting_time_does_not_count_toward_duration(self):
        snapshots=[]
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 15 inspect() DELAY 15',10,20,routines='ROUTINE inspect FROM HOST')
        ctx.externals['HOST','INSPECT']=lambda:snapshots.append(elapsed(ctx))
        p.run();self.assertEqual(snapshots,[[10,5]]);self.assertEqual(elapsed(ctx),[10,20])

    def test_one_poll_carries_overshoot_across_multiple_jobs(self):
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT MOVE AWAY 3 NOWAIT advance() inspect()',10,20,30,routines='ROUTINE advance FROM HOST ROUTINE inspect FROM HOST')
        ctx.externals['HOST','ADVANCE']=lambda:now.__setitem__(0,65000)
        snapshots=[];ctx.externals['HOST','INSPECT']=lambda:snapshots.append(elapsed(ctx))
        p.run();self.assertEqual(snapshots,[[10,20,30]]);self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*3)

    def test_fractional_remainder_survives_promotion(self):
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT advance() inspect() advance() inspect()',1,1,routines='ROUTINE advance FROM HOST ROUTINE inspect FROM HOST')
        snapshots=[];ctx.externals['HOST','ADVANCE']=lambda:now.__setitem__(0,now[0]+1500)
        ctx.externals['HOST','INSPECT']=lambda:snapshots.append(elapsed(ctx))
        p.run();self.assertEqual(snapshots,[[1,0],[1,1]]);self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2)

    def test_zero_duration_jobs_wait_their_turn(self):
        snapshots=[]
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT MOVE AWAY 3 NOWAIT inspect() DELAY 10 inspect()',10,0,0,routines='ROUTINE inspect FROM HOST')
        ctx.externals['HOST','INSPECT']=lambda:snapshots.append([r['outcome'] for r in moves(ctx)])
        p.run();self.assertEqual(snapshots,[['pending']*3,['completed']*3]);self.assertEqual(elapsed(ctx),[10,0,0])

    def test_zero_duration_first_job_is_immediate(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 5',0,5)
        p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2)

    def test_all_move_forms_and_via_queue_in_source_order(self):
        operations=['MOVE TO','MOVE NEAR','MOVE AWAY','MOVE ABOUT','MOVE AXIS','MOVE RELATIVE','MOVE ALONG']
        ctx=bank(*([1]*7),operations=operations)
        p,ctx,_,_=run('ATTACH APPEND_NODE(route,s) route[1].node_pos=p MOVE TO p VIA q NOWAIT MOVE NEAR p BY 2 NOWAIT MOVE AWAY 3 NOWAIT MOVE ABOUT v BY 4 NOWAIT MOVE AXIS 2 BY 5 NOWAIT MOVE RELATIVE v NOWAIT MOVE ALONG route NOWAIT DELAY 7',ctx=ctx)
        p.run();self.assertEqual([r['operation'] for r in moves(ctx)],operations);self.assertEqual(elapsed(ctx),[1]*7)
        self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*7)

    def test_direct_dispatcher_and_cooperative_engines(self):
        for prefix,cooperative in (('',False),('entry:: ',False),('',True)):
            with self.subTest(prefix=prefix,cooperative=cooperative):
                p,ctx,_,_=run(prefix+'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 2',1,1,cooperative=cooperative)
                p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2)

    def test_node_schedule_validates_for_each_queued_move(self):
        ctx=bank(10,20);ctx.motion.responses[1]['node_times']={'0':0,'1':20}
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 30',ctx=ctx)
        p.run();self.assertEqual(moves(ctx)[1]['data']['execution']['node_times'],{'0':0,'1':20})

    def test_operand_and_with_settings_detach_at_admission(self):
        ctx=bank(10,10,operations=['MOVE AWAY','MOVE TO'])
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT\nWITH $SPEED=50 MOVE TO p NOWAIT p.x=999 DELAY 20',ctx=ctx)
        p.run();row=moves(ctx)[1];self.assertEqual(row['data']['target']['value']['X'],10.)
        self.assertEqual(row['data']['settings'],[dict(name='$SPEED',group=1,value=50.)])

    def test_waiting_operands_evaluated_once(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY next_distance() NOWAIT DELAY 2',1,1,routines='ROUTINE next_distance:INTEGER BEGIN n=n+1 RETURN n END next_distance')
        self.assertEqual(p.run()['N'],1);self.assertEqual(moves(ctx)[1]['data']['distance'],1.)

    def test_history_eviction_does_not_drop_live_queue(self):
        ctx=bank(1,1,1,limit=1)
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT MOVE AWAY 3 NOWAIT DELAY 3',ctx=ctx)
        p.run();self.assertEqual(len(ctx.motion.history),1);self.assertEqual(moves(ctx)[0]['outcome'],'completed');self.assertFalse(ctx.motion._queued)


class QueueAdmissionTests(unittest.TestCase):
    def reject(self,ctx,body,pattern):
        p,ctx,_,_=run(body,ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,pattern):p.run()
        self.assertEqual((ctx.motion._active,ctx.motion._queued),({},{}))
        return ctx

    def test_default_retains_busy_group_rejection(self):
        ctx=self.reject(bank(10,10,queue_limit=0),'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT','active request')
        self.assertEqual(len(ctx.motion.responses),1)

    def test_full_queue_preserves_unadmitted_response(self):
        ctx=self.reject(bank(10,10,10,queue_limit=1),'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT MOVE AWAY 3 NOWAIT','capacity')
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*2)

    def test_capacity_reused_after_promotion(self):
        ctx=bank(5,5,5,queue_limit=1)
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 5 MOVE AWAY 3 NOWAIT DELAY 10',ctx=ctx)
        p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*3)

    def test_synchronous_move_waits_for_its_queued_completion(self):
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2',10,10)
        p.run();self.assertEqual(elapsed(ctx),[10,10]);self.assertEqual(now[0],20000)
        self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2)

    def test_local_callback_move_joins_queue_and_runs_after_promotion(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE DELAY 20 s=7',10,10)
        p.run();self.assertEqual(p.snapshot()['N'],7);self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2)

    def test_callback_head_acquires_waiter(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT, WHEN FALSE DO n=7 ENDMOVE MOVE AWAY 2 NOWAIT DELAY 10 s=7 DELAY 10',10,10)
        p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2)

    def test_held_queue_does_not_accept_more_work(self):
        ctx=self.reject(bank(10,10,10),'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT HOLD MOVE AWAY 3 NOWAIT','without a hold')
        self.assertEqual(len(ctx.motion.responses),1);self.assertIn(1,ctx.group_locks.held)

    def test_wrong_response_does_not_publish_waiter(self):
        ctx=bank(10,10,operations=['MOVE AWAY','MOVE AXIS'])
        self.reject(ctx,'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT','matching completion')
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(len(moves(ctx)),1)

    def test_false_response_rejects_at_admission(self):
        ctx=bank(10,10);ctx.motion.responses[1]['completed']=False
        self.reject(ctx,'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT','completion rejected')
        self.assertEqual(ctx.motion.responses,[]);self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled','rejected'])

    def test_invalid_schedule_preserves_response_and_queue(self):
        ctx=bank(10,10);ctx.motion.responses[1]['node_times']={'0':0,'2':10}
        self.reject(ctx,'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT','selected move range')
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(len(moves(ctx)),1)

    def test_invalid_operand_preserves_response(self):
        ctx=self.reject(bank(10,10,operations=['MOVE AWAY','MOVE AXIS']),'ATTACH MOVE AWAY 1 NOWAIT MOVE AXIS 9 BY 2 NOWAIT','axis')
        self.assertEqual(len(ctx.motion.responses),1)

    def test_sequence_exhaustion_preserves_response(self):
        ctx=bank(10,10,sequence=2147483644)
        self.reject(ctx,'ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT','sequence exhausted')
        self.assertEqual(len(ctx.motion.responses),1)

    def test_invalid_queue_limits(self):
        for value in (-1,128,True,False,1.,'1',None):
            with self.subTest(value=value),self.assertRaises(ValueError):bank(1,queue_limit=value)

    def test_maximum_queue_is_finite_and_supported(self):
        ctx=bank(1,*([0]*127),queue_limit=127)
        p,ctx,_,_=run('ATTACH '+' '.join('MOVE AWAY 1 NOWAIT' for _ in range(128))+' DELAY 1',ctx=ctx)
        p.run();self.assertEqual(ctx.motion.responses,[]);self.assertFalse(ctx.motion._queued)


class QueueControlTests(unittest.TestCase):
    def test_hold_freezes_head_and_all_waiters(self):
        seen=[]
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 5 HOLD DELAY 100 inspect() UNHOLD DELAY 15',10,10,routines='ROUTINE inspect FROM HOST')
        ctx.externals['HOST','INSPECT']=lambda:seen.append(elapsed(ctx));p.run()
        self.assertEqual(seen,[[5,0]]);self.assertEqual(elapsed(ctx),[10,10])

    def test_cancel_discards_whole_group_queue(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 5 CANCEL',10,10)
        p.run();self.assertEqual(elapsed(ctx),[5,0]);self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*2)

    def test_cancel_keeps_hold_flag(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT HOLD CANCEL',10,10)
        p.run();self.assertIn(1,ctx.group_locks.held);self.assertFalse(ctx.motion._queued)

    def test_cancel_after_partial_batch_keeps_completed_history(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 15 CANCEL',10,10)
        p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['completed','cancelled']);self.assertEqual(elapsed(ctx),[10,5])

    def test_fresh_batch_after_cancel(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT CANCEL MOVE AWAY 3 NOWAIT DELAY 2',10,10,2)
        p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled','cancelled','completed'])

    def test_pause_freezes_queue_and_resume_preserves_order(self):
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 5 PAUSE DELAY 15',10,10)
        with self.assertRaises(rt.KarelPause):p.run()
        now[0]+=100000;p.resume();self.assertEqual(elapsed(ctx),[10,10]);self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2)

    def test_stop_paused_task_cancels_all(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT PAUSE',10,10)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*2);self.assertFalse(ctx.motion._queued)

    def test_abort_cancels_all(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT ABORT',10,10)
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*2);self.assertFalse(ctx.motion._queued)

    def test_normal_end_cancels_unfinished_queue(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 5',10,10)
        p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*2);self.assertEqual(elapsed(ctx),[5,0])

    def test_failure_cancels_unfinished_queue(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT n=1 DIV 0',10,10)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*2);self.assertFalse(ctx.motion._queued)

    def test_release_requires_entire_batch_idle(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 10 RELEASE',10,10)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'idle logical'):p.run()
        self.assertEqual([r['outcome'] for r in moves(ctx)],['completed','cancelled'])

    def test_release_succeeds_after_batch_completion(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 20 RELEASE',10,10)
        p.run();self.assertFalse(ctx.motion._active);self.assertFalse(ctx.motion._queued)

    def test_global_handler_can_cancel_entire_queue(self):
        p,ctx,_,_=run('n=0 CONDITION[1]: WHEN n=1 DO CANCEL ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT n=1 DELAY 10',10,10)
        p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*2)

    def test_local_routine_return_keeps_callback_free_batch(self):
        p,ctx,_,_=run('ATTACH launch() DELAY 20',10,10,routines='ROUTINE launch BEGIN MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT END launch')
        p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2);self.assertEqual(p._state.local_frames,[])


class QueueClockAndPersistenceTests(unittest.TestCase):
    def paused(self):
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT PAUSE',10,10)
        with self.assertRaises(rt.KarelPause):p.run()
        return p,ctx,now

    def test_replaced_clock_fails_entire_queue(self):
        p,ctx,_=self.paused();p._state._clock_us=lambda:0
        with self.assertRaisesRegex(rt.KarelRuntimeError,'adapter changed'):ctx.motion.poll(p._state)
        self.assertEqual([r['outcome'] for r in moves(ctx)],['failed']*2);self.assertFalse(ctx.motion._queued);p.stop()

    def test_backwards_clock_fails_entire_queue(self):
        p,ctx,now=self.paused();now[0]=-1
        with self.assertRaises(rt.KarelRuntimeError):ctx.motion.poll(p._state)
        self.assertEqual([r['outcome'] for r in moves(ctx)],['failed']*2);p.stop()

    def test_foreign_grant_is_preserved(self):
        p,ctx,_=self.paused();foreign=object();ctx.group_locks.release_owner(p._state);ctx.group_locks._grant(1,foreign);ctx.group_locks.set_motion(1,'executing')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ownership grant'):ctx.motion.poll(p._state)
        self.assertIs(ctx.group_locks.owners[1],foreign);self.assertEqual(ctx.group_locks.motion[1],'executing')
        self.assertEqual([r['outcome'] for r in moves(ctx)],['failed']*2);p.stop()

    def test_regranted_same_task_is_preserved(self):
        p,ctx,_=self.paused();ctx.group_locks.release_owner(p._state);ctx.group_locks._grant(1,p._state);ctx.group_locks.set_motion(1,'executing')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ownership grant'):ctx.motion.poll(p._state)
        self.assertEqual(ctx.group_locks.motion[1],'executing');self.assertEqual([r['outcome'] for r in moves(ctx)],['failed']*2);p.stop()

    def test_external_stopped_label_is_preserved(self):
        p,ctx,_=self.paused();ctx.group_locks.set_motion(1,'stopped')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'work label'):ctx.motion.poll(p._state)
        self.assertEqual(ctx.group_locks.motion[1],'stopped');self.assertEqual([r['outcome'] for r in moves(ctx)],['failed']*2);p.stop()

    def test_pending_queue_cannot_save(self):
        p,ctx,_=self.paused()
        with self.assertRaisesRegex(ValueError,'active motion'):ctx.motion.to_config()
        p.stop()

    def test_completed_batch_and_limit_roundtrip(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 20',10,10);p.run()
        saved=json.loads(json.dumps(ctx.to_config()));self.assertEqual(saved['motion']['queue_limit'],8)
        self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_cancelled_batch_roundtrip(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 5 CANCEL',10,10);p.run()
        saved=ctx.to_config();self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_failed_batch_roundtrip(self):
        p,ctx,_=self.paused();p._state._clock_us=lambda:-1
        with self.assertRaises(rt.KarelRuntimeError):ctx.motion.poll(p._state)
        p.stop();saved=ctx.to_config();self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_old_config_omits_disabled_queue(self):
        saved=context().motion.to_config();self.assertNotIn('queue_limit',saved)
        saved['queue_limit']=0;self.assertNotIn('queue_limit',rt.MotionRequests.from_config(saved).to_config())

    def test_config_limit_validates(self):
        for value in (-1,128,True,1.0,'1',None):
            saved=context().motion.to_config();saved['queue_limit']=value
            with self.subTest(value=value),self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)

    def test_pending_history_still_rejects(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 20',10,10);p.run()
        saved=ctx.motion.to_config();saved['history'][1]['outcome']='pending'
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)


class QueueSchedulerTests(unittest.TestCase):
    def project(self,body,*,ctx=None,lib=None,**options):
        ctx=ctx or bank(10,20)
        docs={'main':source('MAIN',body,decl='n:INTEGER',routines='ROUTINE launch FROM LIB' if lib else '')}
        if lib:docs['lib']=source('LIB','',routines=lib)
        project=translate_project(docs).instantiate(context=ctx,options=options)
        return project,project.programs['MAIN'],ctx

    def test_scheduler_drains_queue_while_owner_waits(self):
        project,p,ctx=self.project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 100')
        active(project,ctx)
        for _ in range(200):
            project.scheduler.step()
            if len(moves(ctx))==2 and all(r['outcome']=='completed' for r in moves(ctx)):break
        self.assertEqual(elapsed(ctx),[10,20]);self.assertEqual(p.task_state,'waiting');project.scheduler.run()

    def test_deadlines_advance_to_each_head_completion(self):
        project,p,ctx=self.project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 100')
        project.run('MAIN');self.assertEqual(elapsed(ctx),[10,20]);self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2)

    def test_linked_launch_keeps_caller_lifetime(self):
        project,p,ctx=self.project('ATTACH launch() DELAY 30',lib='ROUTINE launch BEGIN MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT END launch')
        project.run('MAIN');self.assertEqual([(r['program'],r['source_program'],r['outcome']) for r in moves(ctx)],[('MAIN','LIB','completed')]*2)

    def test_scheduler_stop_discards_queue(self):
        project,p,ctx=self.project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 100')
        project.scheduler.start('MAIN')
        for _ in range(100):
            project.scheduler.step()
            if ctx.motion._queued:break
        self.assertTrue(ctx.motion._queued);project.scheduler.stop('MAIN')
        self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*2);self.assertFalse(ctx.motion._queued)

    def test_scheduler_custom_clock_failure_discards_queue(self):
        now=[0];project,p,ctx=self.project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 100',clock_us=lambda:now[0])
        project.scheduler.start('MAIN')
        for _ in range(100):
            project.scheduler.step()
            if ctx.motion._queued:break
        now[0]=-1
        with self.assertRaises(rt.KarelRuntimeError):project.scheduler.step()
        self.assertEqual(p.task_state,'failed');self.assertEqual([r['outcome'] for r in moves(ctx)],['failed']*2);self.assertFalse(ctx.motion._queued)

    def test_groups_have_independent_fifos(self):
        ctx=bank(10,20,10,20,groups={1:2,2:2})
        docs={'main':source('MAIN','ATTACH launch_one() launch_two() DELAY 30',routines='ROUTINE launch_one FROM ONE ROUTINE launch_two FROM TWO'),
              'one':source('ONE','',routines='ROUTINE launch_one BEGIN MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT END launch_one'),
              'two':source('TWO','',routines='ROUTINE launch_two BEGIN MOVE AWAY 3 NOWAIT MOVE AWAY 4 NOWAIT END launch_two')}
        docs['two']=docs['two'].replace('PROGRAM TWO','PROGRAM TWO\n%DEFGROUP=2\n')
        project=translate_project(docs).instantiate(context=ctx);project.run('MAIN')
        self.assertEqual([r['group'] for r in moves(ctx)],[1,1,2,2]);self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*4)

    def test_shared_waiting_capacity_across_groups(self):
        ctx=bank(10,20,10,20,groups={1:2,2:2},queue_limit=1)
        docs={'main':source('MAIN','ATTACH launch_one() launch_two() DELAY 30',routines='ROUTINE launch_one FROM ONE ROUTINE launch_two FROM TWO'),
              'one':source('ONE','',routines='ROUTINE launch_one BEGIN MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT END launch_one'),
              'two':source('TWO','',routines='ROUTINE launch_two BEGIN MOVE AWAY 3 NOWAIT MOVE AWAY 4 NOWAIT END launch_two')}
        docs['two']=docs['two'].replace('PROGRAM TWO','PROGRAM TWO\n%DEFGROUP=2\n')
        project=translate_project(docs).instantiate(context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):project.run('MAIN')
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*3)


class QueueBoundaryTests(unittest.TestCase):
    def test_advancing_admission_clock_cannot_credit_time_before_head_completion(self):
        samples=iter([0,9000,11000,11000])
        p,ctx,_,_=run('',10,20,clock=lambda:next(samples));state=p._state
        state.task_state='running';ctx.group_locks._grant(1,state)
        try:
            list(ctx.motion.execute(state,'MOVE AWAY',dict(distance=1.),True,1))
            list(ctx.motion.execute(state,'MOVE AWAY',dict(distance=2.),True,2))
            ctx.motion.poll(state)
            self.assertEqual(elapsed(ctx),[10,1])
        finally:
            ctx.motion.finish(state);ctx.group_locks.release_owner(state)

    def test_queued_path_nodes_detach_before_later_mutation(self):
        ctx=bank(10,10,operations=['MOVE AWAY','MOVE ALONG'])
        p,ctx,_,_=run('ATTACH APPEND_NODE(route,s) route[1].node_pos=p MOVE AWAY 1 NOWAIT MOVE ALONG route NOWAIT p.x=999 route[1].node_pos=p DELAY 20',ctx=ctx)
        p.run();self.assertEqual(moves(ctx)[1]['data']['nodes'][0]['value']['LOCATION']['X'],10.)

    def test_queued_joint_destination_detaches_exact_axes(self):
        ctx=bank(10,10,operations=['MOVE AWAY','MOVE TO'])
        p,ctx,_,_=run('ATTACH a[1]=5 a[2]=8 CNV_REL_JPOS(a,j,s) MOVE AWAY 1 NOWAIT MOVE TO j NOWAIT a[1]=99 CNV_REL_JPOS(a,j,s) DELAY 20',ctx=ctx)
        p.run();self.assertEqual(moves(ctx)[1]['data']['target'],dict(type=['JOINTPOS',2],value=dict(axes=[5.,8.])))

    def test_selected_cancel_preserves_other_group_fifo(self):
        ctx=bank(10,20,10,20,groups={1:2,2:2})
        docs={'main':source('MAIN','ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT launch() CANCEL GROUP[1] DELAY 30',routines='ROUTINE launch FROM LIB'),
              'lib':'PROGRAM LIB\n%DEFGROUP=2\nROUTINE launch BEGIN MOVE AWAY 3 NOWAIT MOVE AWAY 4 NOWAIT END launch BEGIN END LIB'}
        project=translate_project(docs).instantiate(context=ctx);project.run('MAIN')
        self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled','cancelled','completed','completed'])
        self.assertGreaterEqual(elapsed(ctx)[0],0);self.assertLess(elapsed(ctx)[0],10)
        self.assertEqual(elapsed(ctx)[1:],[0,10,20]);self.assertFalse(ctx.motion._queued)

    def test_other_task_cannot_join_or_cancel_existing_batch(self):
        ctx=bank(10,10,10)
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT PAUSE',ctx=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        other,ctx,_,_=run('MOVE AWAY 3 NOWAIT',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'same task'):other.run()
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual([r['outcome'] for r in moves(ctx)],['pending']*2)
        self.assertEqual(len(ctx.motion._queued[1]),1);p.stop()

    def test_direct_invoke_output_does_not_queue(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT PAUSE',10,10,10)
        with self.assertRaises(rt.KarelPause):p.run()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'generated NOWAIT'):ctx.motion.invoke(p._state,'MOVE AWAY',dict(distance=3.),True,9)
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(len(ctx.motion._queued[1]),1);p.stop()

    def test_enabled_capture_only_endpoint_keeps_immediate_behavior(self):
        ctx=context(queue_limit=8)
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT',ctx=ctx)
        p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['captured']*2)
        self.assertEqual(elapsed(ctx),[0,0]);self.assertFalse(ctx.motion._queued)

    def test_omitted_delays_are_zero_duration_waiters(self):
        ctx=bank(10,0);ctx.motion.responses[1].pop('delay_ms')
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 10',ctx=ctx)
        p.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2);self.assertEqual(elapsed(ctx),[10,0])

    def test_waiter_admitted_after_partial_head_progress(self):
        seen=[]
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT DELAY 8 MOVE AWAY 2 NOWAIT DELAY 7 inspect() DELAY 15',10,20,routines='ROUTINE inspect FROM HOST')
        ctx.externals['HOST','INSPECT']=lambda:seen.append(elapsed(ctx));p.run();self.assertEqual(seen,[[10,5]]);self.assertEqual(elapsed(ctx),[10,20])

    def test_maximum_waiting_capacity_rejects_129th_live_request(self):
        ctx=bank(*([1]*129),queue_limit=127)
        p,ctx,_,_=run('ATTACH '+' '.join('MOVE AWAY 1 NOWAIT' for _ in range(129)),ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):p.run()
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual([r['outcome'] for r in moves(ctx)],['cancelled']*128)

    def test_new_clock_failure_before_waiter_admission_preserves_reply(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT replace_clock() MOVE AWAY 2 NOWAIT',10,10,routines='ROUTINE replace_clock FROM HOST')
        ctx.externals['HOST','REPLACE_CLOCK']=lambda:setattr(p._state,'_clock_us',lambda:0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'adapter changed'):p.run()
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(len(moves(ctx)),1);self.assertFalse(ctx.motion._queued)

    def test_empty_queue_config_roundtrips_without_clocks(self):
        saved=bank(1,2).to_config();self.assertNotIn('_queued',saved['motion']);self.assertNotIn('clock',saved['motion'])
        self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_report_declares_opt_in_and_offline_boundary(self):
        _,_,_,result=run('ATTACH MOVE AWAY 1 NOWAIT',1)
        policy=result.report['motion_queue_policy'];self.assertEqual(policy['guide'],'docs/queued-motion.md')
        self.assertIn('0..127',policy['configuration']);self.assertIn('before',policy['admission'])
        self.assertIn('no callbacks after defining-frame return',policy['boundary']);self.assertFalse(policy['controller_validated'])

    def test_task_rename_retains_queue_ownership(self):
        project,p,ctx=QueueSchedulerTests().project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 100')
        project.scheduler.start('MAIN')
        for _ in range(100):
            project.scheduler.step()
            if ctx.motion._queued:break
        self.assertTrue(ctx.motion._queued);project.scheduler.rename('MAIN','RENAMED');project.scheduler.run()
        self.assertIs(project.scheduler.tasks['RENAMED'],p);self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2)

    def test_scheduler_pause_freezes_batch_until_continue(self):
        project,p,ctx=QueueSchedulerTests().project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT DELAY 100 DELAY 30')
        project.scheduler.start('MAIN')
        for _ in range(100):
            project.scheduler.step()
            if ctx.motion._queued:break
        p.pause()
        for _ in range(100):
            project.scheduler.step()
            if p.task_state=='paused':break
        self.assertEqual(p.task_state,'paused');before=elapsed(ctx)
        project.scheduler.now_us+=100000;project.scheduler.step();self.assertEqual(elapsed(ctx),before)
        project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual([r['outcome'] for r in moves(ctx)],['completed']*2)

    def test_paused_poll_without_state_does_not_advance_waiters(self):
        now=[0];ctx=bank(10,10,groups={1:2,2:2})
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT PAUSE',ctx=ctx,clock=lambda:now[0])
        with self.assertRaises(rt.KarelPause):p.run()
        now[0]=50000;ctx.motion.poll();self.assertEqual(elapsed(ctx),[0,0]);p.stop()


if __name__ == '__main__':
    unittest.main()
