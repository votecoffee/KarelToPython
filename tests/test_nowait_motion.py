"""Authored pending NOWAIT timing, controls, ownership and offline history."""
from copy import deepcopy
import json
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_motion_requests import context,DECL,SETUP
from tests.test_project_scheduler import source


def build(body,*,delay=25,plan=None,completed=True,routines='',ctx=None,clock=None,sleep=None,**options):
    now=[0];seen=[]
    response=dict(operation='MOVE AWAY',completed=completed,delay_ms=delay)
    if plan is not None:response['node_times']=plan
    ctx=ctx or context(capture_only=False,responses=[response])
    def sleeper(seconds):
        now[0]+=round(seconds*1000000)
        if sleep is not None:sleep(seconds)
    p,r=compile_program(SETUP+body,decl=DECL,prefix='',routines='ROUTINE mark FROM HOST '+routines,context=ctx,joint_axes=2,clock_us=clock or (lambda:now[0]),sleep=sleeper,**options)
    def mark():
        row=move(ctx);seen.append(dict(motion=ctx.group_locks.motion.get(1,'idle'),elapsed=row['data'].get('execution',{}).get('elapsed_ms'),outcome=row['outcome'],active=len(ctx.motion._active)))
    ctx.externals['HOST','MARK']=mark
    return p,ctx,now,seen,r

def move(ctx):return next(row for row in reversed(ctx.motion.history) if row['operation'].startswith('MOVE '))
def progress(ctx):return move(ctx)['data']['execution']['elapsed_ms']
def scheduled(body,*,delay=25,extra=None,**options):
    ctx=context(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True,delay_ms=delay)])
    documents={'main':source('MAIN',SETUP+body,decl=DECL)}
    if extra:documents.update(extra)
    project=translate_project(documents).instantiate(context=ctx,options=dict(joint_axes=2,**options));p=project.programs['MAIN'];return project,p,ctx

def active(project,ctx):
    project.scheduler.start('MAIN')
    for _ in range(100):
        project.scheduler.step()
        if ctx.motion._active:return
    raise AssertionError('NOWAIT did not remain pending')

class PendingMotionTests(unittest.TestCase):
    def test_grouped_stop_resume_freezes_progress_and_preserves_independent_hold(self):
        body=('ATTACH MOVE AWAY 1 NOWAIT DELAY 5 STOP GROUP[1] mark() '
              'DELAY 100 mark() HOLD GROUP[1] RESUME GROUP[1] DELAY 20 mark() '
              'UNHOLD GROUP[1] DELAY 20 mark()')
        program,ctx,_,seen,_=build(body)
        program.run()
        self.assertEqual([(row['motion'],row['elapsed'],row['outcome']) for row in seen],
                         [('stopped',5,'pending'),('stopped',5,'pending'),
                          ('executing',5,'pending'),('idle',25,'completed')])
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertEqual(restored.motion.history,ctx.motion.history)

    def test_grouped_stop_resume_through_global_handlers_during_blocking_move(self):
        body=('ATTACH n=0 '
              'CONDITION[1]: WHEN n=1 DO STOP GROUP[1] ENDCONDITION '
              'CONDITION[2]: WHEN n=2 DO RESUME GROUP[1] ENDCONDITION '
              'ENABLE CONDITION[1] ENABLE CONDITION[2] MOVE AWAY 1 n=7')
        waits=[]
        def sleeper(seconds):
            waits.append((ctx.group_locks.motion.get(1),seconds))
            if len(waits)<=2:program._state.set('N',len(waits))
        program,ctx,_,_,_=build(body,sleep=sleeper)
        self.assertEqual(program.run()['N'],7)
        self.assertEqual(waits,[('executing',.01),('stopped',.01),('executing',.01),('executing',.005)])
        self.assertEqual((progress(ctx),move(ctx)['outcome']),(25,'completed'))

    def test_cncl_stp_mtn_cancels_frozen_fifo_without_leaking_scope(self):
        responses=[dict(operation='MOVE AWAY',completed=True,delay_ms=25) for _ in range(2)]
        ctx=context(capture_only=False,responses=responses,queue_limit=2)
        ctx.controller=rt.ControllerServices()
        body=('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT STOP GROUP[1] '
              'CNCL_STP_MTN RESUME GROUP[1]')
        program,_,_,_,_=build(body,ctx=ctx)
        program.run()
        self.assertEqual([row['outcome'] for row in ctx.motion.history if row['operation']=='MOVE AWAY'],
                         ['cancelled','cancelled'])
        self.assertEqual(ctx.controller.history[-1]['data']['groups'],[1])
        self.assertEqual(ctx.group_locks.motion,{})
        self.assertFalse(ctx.motion.has_pending_group(1))

    def test_bare_task_stop_releases_frozen_scope(self):
        program,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT STOP GROUP[1] STOP')
        with self.assertRaises(rt.KarelStop):program.run()
        self.assertEqual(move(ctx)['outcome'],'cancelled')
        self.assertEqual(ctx.group_locks.motion,{})
        self.assertFalse(ctx.motion.has_pending_group(1))

    def test_nowait_continues_before_supplied_completion(self):
        p,ctx,_,seen,_=build('ATTACH MOVE AWAY 1 NOWAIT n=7 mark() DELAY 25 mark()');self.assertEqual(p.run()['N'],7);self.assertEqual([(r['motion'],r['elapsed'],r['outcome']) for r in seen],[('executing',0,'pending'),('idle',25,'completed')])
    def test_partial_elapsed_time_is_retained(self):
        p,ctx,_,seen,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 10 mark() DELAY 15 mark()');p.run();self.assertEqual([r['elapsed'] for r in seen],[10,25]);self.assertEqual(ctx.motion._active,{})
    def test_progress_caps_at_supplied_delay(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 100');p.run();self.assertEqual(progress(ctx),25);self.assertEqual(move(ctx)['outcome'],'completed')
    def test_fractional_milliseconds_accumulate(self):
        p,ctx,now,seen,_=build('ATTACH MOVE AWAY 1 NOWAIT advance() advance() advance() advance() mark()',routines='ROUTINE advance FROM HOST')
        def advance():now[0]+=500
        ctx.externals['HOST','ADVANCE']=advance;p.run();self.assertEqual(seen[0]['elapsed'],2)
    def test_no_sleep_is_injected_by_nowait(self):
        sleeps=[];p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT n=7',sleep=sleeps.append);p.run();self.assertEqual(sleeps,[]);self.assertEqual(move(ctx)['outcome'],'cancelled')
    def test_terminal_completion_cancels_unfinished_move(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 10');p.run();self.assertEqual((progress(ctx),move(ctx)['outcome']),(10,'cancelled'));self.assertEqual(ctx.group_locks.owners,{})
    def test_busy_group_rejects_second_move_without_consuming_its_response(self):
        ctx=context(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True,delay_ms=25),dict(operation='MOVE AWAY',completed=True,delay_ms=10)])
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'active request'):p.run()
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(move(ctx)['outcome'],'cancelled')
    def test_completed_group_admits_another_move(self):
        ctx=context(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True,delay_ms=25),dict(operation='MOVE AWAY',completed=True,delay_ms=10)])
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 25 MOVE AWAY 2 NOWAIT DELAY 10',ctx=ctx);p.run();self.assertEqual([row['outcome'] for row in ctx.motion.history if row['nowait']],['completed','completed'])
    def test_false_completion_rejects_without_starting_pending_job(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT',completed=False)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'completion rejected'):p.run()
        self.assertEqual(ctx.motion.responses,[]);self.assertEqual((move(ctx)['outcome'],ctx.motion._active),('rejected',{}))
    def test_zero_delay_preserves_immediate_reply(self):
        p,ctx,_,seen,_=build('ATTACH MOVE AWAY 1 NOWAIT mark()',delay=0);p.run();self.assertEqual(seen[0]['outcome'],'completed');self.assertNotIn('execution',move(ctx)['data'])
    def test_zero_duration_schedule_is_validated_and_completed(self):
        p,ctx,_,seen,_=build('ATTACH MOVE AWAY 1 NOWAIT mark()',delay=0,plan={'0':0,'1':0});p.run();self.assertEqual((seen[0]['elapsed'],seen[0]['outcome']),(0,'completed'));self.assertEqual(ctx.motion._active,{})
    def test_supplied_schedule_is_retained(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 25',plan={'0':0,'1':25});p.run();self.assertEqual(move(ctx)['data']['execution']['node_times'],{'0':0,'1':25})
    def test_incomplete_schedule_does_not_consume_response(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT',plan={'0':0,'2':25})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'selected move range'):p.run()
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(len(ctx.motion.history),1)
    def test_dispatcher_and_cooperative_engines(self):
        for label,cooperative in (('',False),('start:: ',False),('',True)):
            p,ctx,_,_,_=build(label+'ATTACH MOVE AWAY 1 NOWAIT DELAY 25',cooperative=cooperative);p.run();self.assertEqual(move(ctx)['outcome'],'completed')
    def test_operand_effect_runs_once(self):
        p,ctx,_,_,_=build('n=0 ATTACH MOVE AWAY distance() NOWAIT DELAY 25',routines='ROUTINE distance:INTEGER BEGIN n=n+1 RETURN 7 END distance');self.assertEqual(p.run()['N'],1);self.assertEqual(move(ctx)['data']['distance'],7)
    def test_pose_is_detached_before_source_continues(self):
        ctx=context(capture_only=False,responses=[dict(operation='MOVE TO',completed=True,delay_ms=25)])
        p,ctx,_,_,_=build('ATTACH MOVE TO p NOWAIT p.x=99 DELAY 25',ctx=ctx);p.run();self.assertEqual(move(ctx)['data']['target']['value']['X'],10.)

class PendingControlTests(unittest.TestCase):
    def test_hold_freezes_elapsed_and_unhold_resumes(self):
        p,ctx,_,seen,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 10 HOLD DELAY 100 mark() UNHOLD DELAY 15 mark()');p.run();self.assertEqual([r['elapsed'] for r in seen],[10,25]);self.assertEqual(move(ctx)['outcome'],'completed')
    def test_cancel_finishes_pending_request_immediately(self):
        p,ctx,_,seen,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 10 CANCEL mark()');p.run();self.assertEqual((seen[0]['motion'],seen[0]['outcome'],seen[0]['active']),('idle','cancelled',0));self.assertEqual(progress(ctx),10)
    def test_cancel_preserves_hold(self):
        p,ctx,_,seen,_=build('ATTACH MOVE AWAY 1 NOWAIT HOLD CANCEL mark()');p.run();self.assertEqual(seen[0]['outcome'],'cancelled');self.assertIn(1,ctx.group_locks.held)
    def test_cancel_after_completion_keeps_completed_outcome(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 25 CANCEL');p.run();self.assertEqual(move(ctx)['outcome'],'completed')
    def test_already_held_group_rejects_admission(self):
        p,ctx,_,_,_=build('ATTACH HOLD MOVE AWAY 1 NOWAIT')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'without a hold'):p.run()
        self.assertEqual(len(ctx.motion.responses),1)
    def test_global_handler_can_cancel_background_request(self):
        body='n=0 CONDITION[1]: WHEN n=1 DO CANCEL ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT n=1 DELAY 10'
        p,ctx,_,_,_=build(body);p.run();self.assertEqual(move(ctx)['outcome'],'cancelled')
    def test_global_handler_delay_counts_as_background_time(self):
        body='n=0 CONDITION[1]: WHEN n=1 DO DELAY 25 ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT n=1 mark()'
        p,ctx,_,seen,_=build(body);p.run();self.assertEqual(seen[0]['outcome'],'completed')
    def test_release_rejects_pending_group(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT RELEASE')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'idle logical group'):p.run()
        self.assertEqual(move(ctx)['outcome'],'cancelled')
    def test_release_after_completion(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 25 RELEASE ATTACH');p.run();self.assertEqual(move(ctx)['outcome'],'completed')
    def test_pause_retains_scope_and_excludes_paused_time(self):
        p,ctx,now,seen,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 10 PAUSE mark() DELAY 15 mark()')
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(progress(ctx),10);now[0]+=100000;p.resume();self.assertEqual([r['elapsed'] for r in seen],[10,25])
    def test_stop_cancels_paused_scope(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT PAUSE')
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(move(ctx)['outcome'],'cancelled');self.assertEqual(ctx.motion._active,{})
    def test_abort_cancels_pending_scope(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT ABORT')
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(move(ctx)['outcome'],'cancelled');self.assertEqual(ctx.motion._active,{})
    def test_later_runtime_failure_cancels_scope(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT n=1 DIV 0')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(move(ctx)['outcome'],'cancelled');self.assertEqual(ctx.group_locks.owners,{})
    def test_local_routine_can_return_while_job_is_pending(self):
        p,ctx,_,_,_=build('ATTACH launch() DELAY 25',routines='ROUTINE launch BEGIN MOVE AWAY 1 NOWAIT END launch');p.run();self.assertEqual(move(ctx)['outcome'],'completed');self.assertEqual(p._state.local_frames,[])

class PendingClockTests(unittest.TestCase):
    def test_invalid_clock_rejects_before_response_consumption(self):
        for value in (True,-1,1.,None):
            p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT',clock=lambda:value)
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(len(ctx.motion.history),1)
    def test_clock_exception_rejects_before_admission(self):
        def fail():raise ValueError('clock failed')
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT',clock=fail)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(len(ctx.motion.responses),1)
    def test_backwards_clock_fails_scope(self):
        p,ctx,now,_,_=build('ATTACH MOVE AWAY 1 NOWAIT PAUSE');now[0]=1000
        with self.assertRaises(rt.KarelPause):p.run()
        now[0]=0
        with self.assertRaisesRegex(rt.KarelRuntimeError,'backwards'):ctx.motion.poll(p._state)
        self.assertEqual(move(ctx)['outcome'],'failed');p.stop()
    def test_clock_adapter_replacement_fails_scope(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT PAUSE')
        with self.assertRaises(rt.KarelPause):p.run()
        p._state._clock_us=lambda:0
        with self.assertRaisesRegex(rt.KarelRuntimeError,'adapter changed'):ctx.motion.poll(p._state)
        self.assertEqual(move(ctx)['outcome'],'failed');p.stop()
    def test_clock_adapter_cannot_change_during_initial_sample(self):
        def clock():p._state._clock_us=lambda:0;return 0
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT',clock=clock)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'during capture'):p.run()
        self.assertEqual(len(ctx.motion.responses),1)
    def test_lost_grant_does_not_relabel_foreign_motion(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT PAUSE')
        with self.assertRaises(rt.KarelPause):p.run()
        foreign=object();ctx.group_locks.release_owner(p._state);ctx.group_locks._grant(1,foreign);ctx.group_locks.set_motion(1,'executing')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ownership grant'):ctx.motion.poll(p._state)
        self.assertIs(ctx.group_locks.owners[1],foreign);self.assertEqual(ctx.group_locks.motion[1],'executing');p.stop()
    def test_regranted_same_owner_has_a_new_identity(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT PAUSE')
        with self.assertRaises(rt.KarelPause):p.run()
        ctx.group_locks.release_owner(p._state);ctx.group_locks._grant(1,p._state);ctx.group_locks.set_motion(1,'executing')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ownership grant'):ctx.motion.poll(p._state)
        self.assertEqual(ctx.group_locks.motion[1],'executing');p.stop()
    def test_external_stopped_label_is_preserved(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT PAUSE')
        with self.assertRaises(rt.KarelPause):p.run()
        ctx.group_locks.set_motion(1,'stopped')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'work label'):ctx.motion.poll(p._state)
        self.assertEqual(ctx.group_locks.motion[1],'stopped');p.stop()

class PendingSchedulerTests(unittest.TestCase):
    def test_scheduler_completes_delayed_nowait(self):
        project,p,ctx=scheduled('ATTACH MOVE AWAY 1 NOWAIT n=7 DELAY 30');project.run('MAIN');self.assertEqual((p.snapshot()['N'],move(ctx)['outcome'],progress(ctx)),(7,'completed',25))
    def test_pending_motion_completes_while_owner_waits_longer(self):
        project,p,ctx=scheduled('ATTACH MOVE AWAY 1 NOWAIT DELAY 100');active(project,ctx)
        for _ in range(100):
            project.scheduler.step()
            if move(ctx)['outcome']=='completed':break
        self.assertEqual(move(ctx)['outcome'],'completed');self.assertEqual(p.task_state,'waiting');project.scheduler.run()
    def test_another_task_observes_completion_before_owner_wakes(self):
        watcher=source('WATCH','DELAY 30 n=probe()',decl='n:INTEGER',routines='ROUTINE probe:INTEGER FROM HOST')
        ctx=context(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True,delay_ms=25)]);ctx.externals['HOST','PROBE']=lambda:int(ctx.group_locks.motion.get(1,'idle')=='executing')
        project=translate_project({'main':source('MAIN',SETUP+'ATTACH MOVE AWAY 1 NOWAIT DELAY 100',decl=DECL),'watch':watcher}).instantiate(context=ctx,options={'joint_axes':2});project.scheduler.start('MAIN');project.scheduler.start('WATCH');project.scheduler.run();self.assertEqual(project.programs['WATCH'].snapshot()['N'],0)
    def test_stop_waiting_task_releases_pending_request(self):
        project,p,ctx=scheduled('ATTACH MOVE AWAY 1 NOWAIT DELAY 100');active(project,ctx);project.scheduler.stop('MAIN');self.assertEqual(move(ctx)['outcome'],'cancelled');self.assertEqual((ctx.motion._active,ctx.group_locks.owners),({},{}))
    def test_paused_scheduler_task_freezes_progress(self):
        project,p,ctx=scheduled('ATTACH MOVE AWAY 1 NOWAIT DELAY 100 DELAY 30');active(project,ctx);p.pause()
        for _ in range(100):
            project.scheduler.step()
            if p.task_state=='paused':break
        self.assertEqual(p.task_state,'paused');before=progress(ctx);project.scheduler.now_us+=100000;project.scheduler.step();self.assertEqual(progress(ctx),before);project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(move(ctx)['outcome'],'completed')
    def test_scheduler_poll_failure_fails_owner_and_cleans_wait(self):
        now=[0];project,p,ctx=scheduled('ATTACH MOVE AWAY 1 NOWAIT DELAY 100',clock_us=lambda:now[0]);active(project,ctx);now[0]=-1
        with self.assertRaises(rt.KarelRuntimeError):project.scheduler.step()
        self.assertEqual(p.task_state,'failed');self.assertIn('MAIN',project.scheduler.errors);self.assertEqual((ctx.motion._active,ctx.group_locks.owners,project.scheduler.waiting),({},{},{}))
    def test_custom_clock_gets_no_inferred_virtual_deadline(self):
        now=[0];project,p,ctx=scheduled('ATTACH MOVE AWAY 1 NOWAIT DELAY 100',clock_us=lambda:now[0]);active(project,ctx);self.assertEqual(ctx.motion.deadlines(project.scheduler),[]);project.scheduler.stop('MAIN')
    def test_linked_launch_uses_calling_task_clock_after_return(self):
        ctx=context(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True,delay_ms=25)])
        main=source('MAIN','ATTACH launch() DELAY 30',routines='ROUTINE launch FROM LIB')
        lib=source('LIB','',routines='ROUTINE launch BEGIN MOVE AWAY 1 NOWAIT END launch')
        project=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);project.run('MAIN');self.assertEqual((move(ctx)['program'],move(ctx)['source_program'],move(ctx)['outcome']),('MAIN','LIB','completed'))

class PendingHistoryTests(unittest.TestCase):
    def test_completed_history_roundtrip(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 25');p.run();saved=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_cancelled_history_roundtrip(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 10 CANCEL');p.run();saved=ctx.motion.to_config();self.assertEqual(rt.MotionRequests.from_config(saved).to_config(),saved)
    def test_rejected_history_roundtrip(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT',completed=False)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        saved=ctx.motion.to_config();self.assertEqual(rt.MotionRequests.from_config(saved).to_config(),saved)
    def test_pending_scope_cannot_be_saved(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT PAUSE')
        with self.assertRaises(rt.KarelPause):p.run()
        with self.assertRaisesRegex(ValueError,'active motion'):ctx.motion.to_config()
        p.stop()
    def test_pending_history_cannot_be_reloaded(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 25');p.run();saved=ctx.motion.to_config();saved['history'][1]['outcome']='pending'
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)
    def test_nowait_history_with_malformed_local_handlers_stays_closed(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 25');p.run();saved=ctx.motion.to_config();saved['history'][1]['data']['execution']['handlers']=[dict(kind='INVALID',line=1)]
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)
    def test_nowait_history_with_malformed_temporal_conditions_stays_closed(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 25',plan={'0':0,'1':25});p.run();saved=ctx.motion.to_config();saved['history'][1]['data']['execution']['conditions']=[dict(kind='INVALID',node=1,offset_ms=0)]
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)
    def test_partial_completed_history_rejects(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT DELAY 25');p.run();saved=ctx.motion.to_config();saved['history'][1]['data']['execution']['elapsed_ms']=24
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)
    def test_history_ring_eviction_does_not_end_job(self):
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT HOLD UNHOLD HOLD UNHOLD DELAY 25');ctx.motion.limit=2;p.run();self.assertEqual(ctx.motion._active,{});self.assertEqual(len(ctx.motion.history),2)
    def test_legacy_direct_invoke_still_rejects_delay(self):
        p,ctx,_,_,_=build('ATTACH');p.run()
        p._state.task_state='running';ctx.group_locks._grant(1,p._state)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'newly generated'):ctx.motion.invoke(p._state,'MOVE AWAY',{'distance':1},True,1)
        ctx.group_locks.release_owner(p._state)
    def test_invalid_local_nowait_predicate_stays_rejected(self):
        with self.assertRaises(TranslationError):build('ATTACH MOVE AWAY 1 NOWAIT, WHEN 1 DO n=7 ENDMOVE')

class PendingFormTests(unittest.TestCase):
    def check_move(self,body,operation):
        ctx=context(capture_only=False,responses=[dict(operation=operation,completed=True,delay_ms=25)])
        p,ctx,_,_,_=build('ATTACH '+body+' NOWAIT DELAY 25',ctx=ctx);p.run();self.assertEqual(move(ctx)['outcome'],'completed');self.assertEqual(progress(ctx),25);return move(ctx)
    def test_move_to(self):self.check_move('MOVE TO p','MOVE TO')
    def test_move_via(self):self.assertIn('via',self.check_move('MOVE TO p VIA q','MOVE TO')['data'])
    def test_move_near(self):self.check_move('MOVE NEAR p BY 12','MOVE NEAR')
    def test_move_relative(self):self.check_move('MOVE RELATIVE v','MOVE RELATIVE')
    def test_move_about(self):self.check_move('MOVE ABOUT v BY 45','MOVE ABOUT')
    def test_move_axis(self):self.check_move('MOVE AXIS 2 BY 90','MOVE AXIS')
    def test_move_along_retains_selected_detached_nodes(self):
        ctx=context(capture_only=False,responses=[dict(operation='MOVE ALONG',completed=True,delay_ms=25,node_times={'0':0,'1':10,'2':25})])
        body='APPEND_NODE(route,s) APPEND_NODE(route,s) route[1].node_pos=p route[2].node_pos=q ATTACH MOVE ALONG route NOWAIT DELETE_NODE(route,1,s) DELAY 25'
        p,ctx,_,_,_=build(body,ctx=ctx);p.run();self.assertEqual(move(ctx)['outcome'],'completed');self.assertEqual(len(move(ctx)['data']['nodes']),2)
    def test_with_settings_capture_once(self):
        p,ctx,_,_,_=build('n=0 ATTACH WITH $SPEED=speed() MOVE AWAY 1 NOWAIT n=99 DELAY 25',routines='ROUTINE speed:INTEGER BEGIN n=n+1 RETURN n END speed');p.run();self.assertEqual(move(ctx)['data']['settings'],[dict(name='$SPEED',group=1,value=1.)])
    def test_global_wait_can_observe_pending_completion(self):
        p,ctx,now,_,_=build('ATTACH MOVE AWAY 1 NOWAIT WAIT FOR finished()',routines='ROUTINE finished:BOOLEAN FROM HOST')
        def finished():now[0]+=1000;return not ctx.motion._active
        ctx.externals['HOST','FINISHED']=finished;p.run();self.assertEqual(move(ctx)['outcome'],'completed')
    def test_robot_pose_is_not_updated_by_completion(self):
        p,ctx,_,_,_=build('ATTACH MOVE TO p NOWAIT DELAY 25',ctx=context(capture_only=False,responses=[dict(operation='MOVE TO',completed=True,delay_ms=25)]));p.run();self.assertIsNone(ctx.robot)
    def test_connected_timer_continues_during_motion_hold(self):
        p,ctx,_,_,_=build('n=0 CONNECT TIMER TO n ATTACH MOVE AWAY 1 NOWAIT DELAY 10 HOLD DELAY 100 UNHOLD DELAY 15 DISCONNECT TIMER n');self.assertEqual(p.run()['N'],125);self.assertEqual(progress(ctx),25)
    def test_two_owned_groups_can_progress_independently(self):
        ctx=context(groups={1:2,2:2},capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True,delay_ms=25),dict(operation='MOVE AWAY',completed=True,delay_ms=25)])
        main=source('MAIN','ATTACH MOVE AWAY 1 NOWAIT launch() HOLD GROUP[1] DELAY 30 UNHOLD GROUP[1] DELAY 30',routines='ROUTINE launch FROM LIB')
        lib='PROGRAM LIB\n%DEFGROUP=2\nROUTINE launch BEGIN MOVE AWAY 2 NOWAIT END launch\nBEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);project.run('MAIN');moves=[r for r in ctx.motion.history if r['nowait']];self.assertEqual([(r['group'],r['outcome']) for r in moves],[(1,'completed'),(2,'completed')])
    def test_scheduler_rename_keeps_pending_owner_identity(self):
        project,p,ctx=scheduled('ATTACH MOVE AWAY 1 NOWAIT DELAY 30');active(project,ctx);project.scheduler.rename('MAIN','RENAMED');project.scheduler.run();self.assertEqual(move(ctx)['outcome'],'completed');self.assertIs(project.scheduler.tasks['RENAMED'],p)
    def test_clock_adapter_switch_during_poll_fails_closed(self):
        enabled=[False]
        def clock():
            if enabled[0]:p._state._clock_us=lambda:0
            return 0
        p,ctx,_,_,_=build('ATTACH MOVE AWAY 1 NOWAIT PAUSE',clock=clock)
        with self.assertRaises(rt.KarelPause):p.run()
        enabled[0]=True
        with self.assertRaisesRegex(rt.KarelRuntimeError,'during poll'):ctx.motion.poll(p._state)
        self.assertEqual(move(ctx)['outcome'],'failed');p.stop()
    def test_failed_history_roundtrip(self):
        p,ctx,now,_,_=build('ATTACH MOVE AWAY 1 NOWAIT PAUSE');now[0]=1000
        with self.assertRaises(rt.KarelPause):p.run()
        now[0]=0
        with self.assertRaises(rt.KarelRuntimeError):ctx.motion.poll(p._state)
        p.stop();saved=ctx.motion.to_config();self.assertEqual(rt.MotionRequests.from_config(saved).to_config(),saved)
    def test_private_background_admission_cannot_smuggle_handlers(self):
        p,ctx,_,_,_=build('ATTACH');p.run();ctx.group_locks._grant(1,p._state)
        execution=dict(delay_ms=25,elapsed_ms=0,handlers=[dict(kind='WHEN',line=1)],triggered=[])
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'local handlers'):ctx.motion.invoke(p._state,'MOVE AWAY',{'distance':1},True,1,_execution=execution,_background=True)
        self.assertEqual(len(ctx.motion.responses),1);ctx.group_locks.release_owner(p._state)
