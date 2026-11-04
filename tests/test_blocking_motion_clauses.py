"""Queued blocking clauses, supplied breakpoints and live source continuations."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_queued_motion import run,bank,moves
from tests.test_queued_motion_clauses import elapsed,triggered,terminal,project
from tests.test_nowait_clauses import authored
from tests.test_motion_requests import DECL


def planned(*delays,operation='MOVE AWAY'):
    ctx=bank(*delays,operations=['MOVE AWAY']+[operation]*(len(delays)-1))
    ctx.motion.responses[-1]['node_times']={'0':0,'1':delays[-1]}
    return ctx


def waiting(linked,ctx):
    linked.scheduler.start('MAIN')
    for _ in range(200):
        linked.scheduler.step()
        if any(not row['nowait'] and row['outcome']=='pending' for row in moves(ctx)):return
    raise AssertionError('Blocking local scope did not remain pending')


class BlockingClauseProgressTests(unittest.TestCase):
    def test_blocking_handler_waits_for_predecessor(self):
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE s=7',10,20)
        self.assertEqual(p.run()['N'],7);self.assertEqual(now[0],30000);self.assertEqual(triggered(ctx),[[],[1]])
        self.assertEqual([r['nowait'] for r in moves(ctx)],[True,False]);self.assertEqual(terminal(ctx),['completed']*2)

    def test_handler_does_not_execute_while_waiting(self):
        snapshots=[]
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',20,20,sleep=lambda _:snapshots.append(p.snapshot()['N']))
        p.run();self.assertEqual(snapshots[:2],[0,0]);self.assertEqual(snapshots[2:],[7,7])

    def test_all_seven_forms_and_via(self):
        forms=[('MOVE TO p VIA q','MOVE TO'),('MOVE NEAR p BY 1','MOVE NEAR'),('MOVE AWAY 2','MOVE AWAY'),('MOVE ABOUT v BY 3','MOVE ABOUT'),('MOVE AXIS 2 BY 4','MOVE AXIS'),('MOVE RELATIVE v','MOVE RELATIVE'),('MOVE ALONG route','MOVE ALONG')]
        for statement,operation in forms:
            with self.subTest(statement=statement):
                ctx=bank(5,6,operations=['MOVE AWAY',operation])
                p,ctx,now,_=run('n=0 APPEND_NODE(route,s) route[1].node_pos=p ATTACH MOVE AWAY 1 NOWAIT '+statement+', WHEN TRUE DO n=7 ENDMOVE',ctx=ctx)
                self.assertEqual(p.run()['N'],7);self.assertEqual(now[0],11000);self.assertEqual(terminal(ctx),['completed']*2)

    def test_mixed_handler_chain_keeps_fifo_order(self):
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=1 ENDMOVE MOVE AWAY 3, WHEN TRUE DO n=n*10+2 ENDMOVE',10,20,30)
        self.assertEqual(p.run()['N'],12);self.assertEqual(now[0],60000);self.assertEqual(triggered(ctx),[[],[1],[1]])

    def test_handler_head_can_precede_blocking_handler(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT, WHEN TRUE DO n=1 ENDMOVE MOVE AWAY 2, WHEN TRUE DO n=n*10+2 ENDMOVE',10,20)
        self.assertEqual(p.run()['N'],12);self.assertEqual(terminal(ctx),['completed']*2)

    def test_zero_duration_blocking_handler_scans_once_without_extra_sleep(self):
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=n+1 ENDMOVE',5,0)
        self.assertEqual(p.run()['N'],1);self.assertEqual(now[0],5000);self.assertEqual(elapsed(ctx),[5,0])

    def test_false_handler_completes_without_writing(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN FALSE DO n=99 ENDMOVE',10,20)
        self.assertEqual(p.run()['N'],0);self.assertEqual(triggered(ctx),[[],[]])

    def test_clauses_run_in_source_order(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN n=0 DO n=1 WHEN n=1 DO n=n+10 ENDMOVE',10,20)
        self.assertEqual(p.run()['N'],11);self.assertEqual(triggered(ctx)[1],[1,2])

    def test_direct_dispatcher_and_cooperative_engines(self):
        for label,cooperative in (('',False),('entry:: ',False),('',True)):
            with self.subTest(label=label,cooperative=cooperative):
                p,ctx,_,_=run(label+'n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',10,20,cooperative=cooperative)
                self.assertEqual(p.run()['N'],7);self.assertEqual(terminal(ctx),['completed']*2)

    def test_idle_synchronous_clauses_keep_existing_policy(self):
        ctx=planned(20);ctx.motion.responses[0]['node_times']={'0':0,'1':20}
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1, WHEN TIME 5 BEFORE NODE[1] DO n=7 ENDMOVE',ctx=ctx)
        self.assertEqual(p.run()['N'],7);self.assertEqual(now[0],20000)

    def test_zero_queue_limit_keeps_busy_rejection(self):
        ctx=bank(10,20,queue_limit=0)
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'active request'):p.run()
        self.assertEqual(len(ctx.motion.responses),1)

    def test_capture_only_clauses_stay_immediate(self):
        from tests.test_motion_requests import context
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',ctx=context(queue_limit=8))
        self.assertEqual(p.run()['N'],7);self.assertEqual(now[0],0);self.assertEqual(terminal(ctx),['captured']*2)


class BlockingClauseTimelineTests(unittest.TestCase):
    def test_supplied_breakpoints_clip_wait_sleeps(self):
        ctx=planned(10,20);sleeps=[];seen=[]
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TIME 5 BEFORE NODE[1] DO stamp() ENDMOVE',ctx=ctx,routines='ROUTINE stamp FROM HOST',sleep=sleeps.append)
        ctx.externals['HOST','STAMP']=lambda:seen.append(now[0]);p.run()
        self.assertEqual(seen,[25000]);self.assertEqual(sleeps,[.01,.01,.005,.005]);self.assertEqual(elapsed(ctx),[10,20])

    def test_until_cancels_at_supplied_early_breakpoint(self):
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, UNTIL TIME 5 BEFORE NODE[1] THEN n=7 ENDMOVE s=7',ctx=planned(10,20))
        self.assertEqual(p.run()['N'],7);self.assertEqual(terminal(ctx),['completed','cancelled']);self.assertEqual(elapsed(ctx),[10,15]);self.assertEqual(now[0],25000)

    def test_entry_and_terminal_selectors_keep_source_order(self):
        body='n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN AT NODE[0] DO n=1 WHEN TIME 5 BEFORE NODE[1] DO n=n*10+2 WHEN AT NODE[1] DO n=n*10+3 ENDMOVE'
        p,ctx,_,_=run(body,ctx=planned(10,20));self.assertEqual(p.run()['N'],123);self.assertEqual(triggered(ctx)[1],[1,2,3])

    def test_selector_eval_captures_before_entry_actions(self):
        body='n=3 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN AT NODE[0] DO n=99 WHEN TIME EVAL(n) BEFORE NODE[1] DO stamp() ENDMOVE'
        p,ctx,now,_=run(body,ctx=planned(10,20),routines='ROUTINE stamp FROM HOST');seen=[]
        ctx.externals['HOST','STAMP']=lambda:seen.append(now[0]);p.run();self.assertEqual(seen,[27000])
        self.assertEqual(moves(ctx)[1]['data']['execution']['conditions'][1]['offset_ms'],3)

    def test_missing_schedule_rejects_before_response_consumption(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN AT NODE[1] DO n=7 ENDMOVE',10,20)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(len(ctx.motion.responses),1)

    def test_incomplete_schedule_rejects_before_response_consumption(self):
        ctx=planned(10,20);ctx.motion.responses[1]['node_times']={'0':0,'2':20}
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN AT NODE[1] DO n=7 ENDMOVE',ctx=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(len(ctx.motion.responses),1)

    def test_callback_action_time_is_excluded(self):
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO DELAY 100 n=7 ENDMOVE',10,20)
        self.assertEqual(p.run()['N'],7);self.assertEqual(now[0],130000);self.assertEqual(elapsed(ctx),[10,20])

    def test_nowait_predecessor_retains_checkpoint_observation(self):
        ctx=planned(20,10);ctx.motion.responses[0]['node_times']={'0':0,'1':20};ctx.motion.responses[1].pop('node_times')
        body='ATTACH MOVE AWAY 1 NOWAIT, WHEN TIME 5 BEFORE NODE[1] DO stamp() ENDMOVE MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE'
        p,ctx,now,_=run(body,ctx=ctx,routines='ROUTINE stamp FROM HOST');seen=[];ctx.externals['HOST','STAMP']=lambda:seen.append(now[0])
        p.run();self.assertEqual(seen,[20000]);self.assertEqual(elapsed(ctx),[20,10])

    def test_late_host_clock_uses_crossed_event_window(self):
        ctx=planned(10,20);seen=[]
        p,ctx,now,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TIME 5 BEFORE NODE[1] DO stamp() ENDMOVE',ctx=ctx,routines='ROUTINE stamp FROM HOST',sleep=lambda _:now.__setitem__(0,now[0]+50000))
        ctx.externals['HOST','STAMP']=lambda:seen.append(now[0]);p.run()
        self.assertEqual(len(seen),1);self.assertGreaterEqual(seen[0],25000);self.assertEqual(elapsed(ctx),[10,20])

    def test_false_gate_does_not_replay_passed_entry_event(self):
        body='n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN AT NODE[0] AND (n=1) DO s=99 WHEN TIME 5 BEFORE NODE[1] DO n=1 ENDMOVE s=7'
        p,ctx,_,_=run(body,ctx=planned(10,20));self.assertEqual(p.run()['S'],7);self.assertEqual(triggered(ctx)[1],[2])


class BlockingClauseControlTests(unittest.TestCase):
    def test_until_then_finishes_before_source_continues(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, UNTIL TRUE THEN n=7 ENDMOVE n=n+1',10,20)
        self.assertEqual(p.run()['N'],8);self.assertEqual(terminal(ctx),['completed','cancelled'])

    def test_cancel_finishes_current_actions_and_skips_later_clauses(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO CANCEL n=7 WHEN TRUE DO n=99 ENDMOVE',10,20)
        self.assertEqual(p.run()['N'],7);self.assertEqual(triggered(ctx)[1],[1]);self.assertEqual(terminal(ctx),['completed','cancelled'])

    def test_pause_inside_clause_retains_source_and_oneshot(self):
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=1 PAUSE n=n+10 ENDMOVE n=n+100',10,20)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['N'],1);now[0]+=1000000
        self.assertEqual(p.resume()['N'],111);self.assertEqual(triggered(ctx)[1],[1]);self.assertEqual(terminal(ctx),['completed']*2)

    def test_stop_paused_clause_cleans_only_unfinished_scope(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO PAUSE ENDMOVE',10,20)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(terminal(ctx),['completed','cancelled']);self.assertFalse(ctx.motion._active);self.assertFalse(ctx.motion._queued)

    def test_abort_inside_clause_cancels_own_scope(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO ABORT ENDMOVE',10,20)
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(terminal(ctx),['completed','cancelled'])

    def test_clause_failure_preserves_completed_predecessor(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=1 DIV 0 ENDMOVE',10,20)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(terminal(ctx),['completed','failed'])

    def test_then_failure_retains_failed_outcome(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, UNTIL TRUE THEN n=1 DIV 0 ENDMOVE',10,20)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(terminal(ctx),['completed','failed'])

    def test_hold_delay_unhold_excludes_frozen_time(self):
        p,ctx,now,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO HOLD DELAY 30 UNHOLD n=7 ENDMOVE',10,20)
        self.assertEqual(p.run()['N'],7);self.assertEqual(now[0],60000);self.assertEqual(elapsed(ctx),[10,20])

    def test_global_cancel_precedes_own_local_scan(self):
        body='n=0 CONNECT TIMER TO n CONDITION[1]: WHEN n>=10 DO CANCEL ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO s=99 ENDMOVE s=7'
        p,ctx,_,_=run(body,50,20);self.assertEqual(p.run()['S'],7);self.assertEqual(triggered(ctx)[1],[]);self.assertEqual(terminal(ctx),['cancelled']*2)

    def test_predecessor_until_during_operand_call_keeps_idle_semantics(self):
        routines='ROUTINE distance:INTEGER BEGIN n=1 RETURN 2 END distance'
        body='n=0 ATTACH MOVE AWAY 1 NOWAIT, UNTIL n=1 THEN s=7 ENDMOVE MOVE AWAY distance(), WHEN TRUE DO n=99 ENDMOVE'
        p,ctx,_,_=run(body,50,20,routines=routines);self.assertEqual(p.run()['N'],99);self.assertEqual(terminal(ctx),['cancelled','completed']);self.assertEqual(triggered(ctx)[1],[1])

    def test_new_batch_after_cancelled_blocking_clause(self):
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, UNTIL TRUE THEN n=7 ENDMOVE MOVE AWAY 3 NOWAIT MOVE AWAY 4, WHEN TRUE DO n=n+10 ENDMOVE',10,20,5,6)
        self.assertEqual(p.run()['N'],17);self.assertEqual(terminal(ctx),['completed','cancelled','completed','completed'])

    def test_step_budget_remains_enforced_inside_action(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO WHILE TRUE DO n=1 ENDWHILE ENDMOVE',10,20)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=100)
        self.assertEqual(terminal(ctx),['completed','failed']);self.assertFalse(ctx.motion._active)


class BlockingClauseCaptureTests(unittest.TestCase):
    def test_routine_local_cell_remains_live(self):
        routines='ROUTINE work VAR local:INTEGER BEGIN local=1 MOVE AWAY 2, WHEN TRUE DO local=7 ENDMOVE n=local END work'
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT work()',10,20,routines=routines)
        self.assertEqual(p.run()['N'],7);self.assertEqual(p._state.local_frames,[])

    def test_borrowed_formal_updates_caller(self):
        routines='ROUTINE work(value:INTEGER) BEGIN MOVE AWAY 2, WHEN TRUE DO value=7 ENDMOVE s=value END work'
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT work(n)',10,20,routines=routines)
        self.assertEqual((p.run()['N'],p.snapshot()['S']),(7,7))

    def test_grouped_formal_keeps_private_cell(self):
        routines='ROUTINE work(value:INTEGER) BEGIN MOVE AWAY 2, WHEN TRUE DO value=7 ENDMOVE s=value END work'
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT work((n))',10,20,routines=routines)
        self.assertEqual((p.run()['N'],p.snapshot()['S']),(0,7))

    def test_nested_predicate_call_uses_defining_local(self):
        routines='ROUTINE ready(value:INTEGER):BOOLEAN VAR local:INTEGER BEGIN local=99 RETURN value=7 END ready ROUTINE work VAR local:INTEGER BEGIN local=7 MOVE AWAY 2, WHEN ready(local) DO n=local ENDMOVE END work'
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT work()',10,20,routines=routines)
        self.assertEqual(p.run()['N'],7);self.assertEqual(triggered(ctx)[1],[1])

    def test_named_using_retains_live_storage(self):
        ctx=planned(10,20);ctx.motion.responses[0]['node_times']={'0':0,'1':10}
        prefix='TYPE item_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        body='item.amount=1 ATTACH MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO item.amount=7 ENDMOVE USING item DO MOVE AWAY 2, WHEN TRUE DO n=amount ENDMOVE ENDUSING'
        p,ctx,_,_=authored(body,decl=DECL+' item:item_t',prefix=prefix,ctx=ctx)
        self.assertEqual(p.run()['N'],7);self.assertEqual(p.snapshot()['ITEM']['AMOUNT'],7)

    def test_computed_using_keeps_private_snapshot(self):
        ctx=planned(10,20);ctx.motion.responses[0]['node_times']={'0':0,'1':10}
        prefix='TYPE item_t=STRUCTURE amount:INTEGER ENDSTRUCTURE';routines='ROUTINE copy_item:item_t BEGIN RETURN item END copy_item'
        body='item.amount=1 ATTACH MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO item.amount=7 ENDMOVE USING copy_item() DO MOVE AWAY 2, WHEN TRUE DO n=amount ENDMOVE ENDUSING'
        p,ctx,_,_=authored(body,decl=DECL+' item:item_t',prefix=prefix,routines=routines,ctx=ctx)
        self.assertEqual(p.run()['N'],1);self.assertEqual(p.snapshot()['ITEM']['AMOUNT'],7)

    def test_boolean_eval_captures_before_entry_action(self):
        p,ctx,_,_=run('n=3 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=99 WHEN EVAL(n)=3 DO s=7 ENDMOVE',10,20)
        self.assertEqual((p.run()['N'],p.snapshot()['S']),(99,7));self.assertEqual(triggered(ctx)[1],[1,2])

    def test_cartesian_operand_detaches_before_predecessor_changes_it(self):
        ctx=planned(10,20,operation='MOVE TO');ctx.motion.responses[0]['node_times']={'0':0,'1':10}
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO p.x=999 ENDMOVE MOVE TO p, WHEN TRUE DO n=7 ENDMOVE',ctx=ctx)
        p.run();self.assertEqual(moves(ctx)[1]['data']['target']['value']['X'],10.);self.assertEqual(p.snapshot()['P']['X'],999.)

    def test_path_operand_detaches_before_predecessor_changes_it(self):
        ctx=planned(10,20,operation='MOVE ALONG');ctx.motion.responses[0]['node_times']={'0':0,'1':10}
        body='APPEND_NODE(route,s) route[1].node_pos=p ATTACH MOVE AWAY 1 NOWAIT, WHEN AT NODE[1] DO p.x=999 route[1].node_pos=p ENDMOVE MOVE ALONG route, WHEN TRUE DO n=7 ENDMOVE'
        p,ctx,_,_=run(body,ctx=ctx);p.run();self.assertEqual(moves(ctx)[1]['data']['nodes'][0]['value']['LOCATION']['X'],10.)

    def test_with_setting_captures_before_clause_write(self):
        p,ctx,_,_=run('s=50 ATTACH MOVE AWAY 1 NOWAIT\nWITH $SPEED=s MOVE AWAY 2, WHEN TRUE DO s=99 ENDMOVE',10,20)
        p.run();self.assertEqual(moves(ctx)[1]['data']['settings'],[dict(name='$SPEED',group=1,value=50.)])

    def test_connected_routine_timer_stays_live(self):
        routines='ROUTINE work VAR ticks:INTEGER BEGIN ticks=0 CONNECT TIMER TO ticks MOVE AWAY 2, WHEN AT NODE[1] DO n=ticks ENDMOVE END work'
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT work()',ctx=planned(10,20),routines=routines)
        self.assertEqual(p.run()['N'],30);self.assertFalse(p._state._timers)

    def test_linked_routine_blocks_through_own_clauses(self):
        lib='PROGRAM LIB VAR amount:INTEGER ROUTINE work BEGIN amount=0 MOVE AWAY 2, WHEN TRUE DO amount=17 ENDMOVE END work BEGIN END LIB'
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT work()',10,20,lib=lib)
        linked.run('MAIN');self.assertEqual(linked.programs['LIB'].snapshot()['AMOUNT'],17)
        self.assertEqual([(r['program'],r['source_program']) for r in moves(ctx)],[('MAIN','MAIN'),('MAIN','LIB')])

    def test_parent_handler_can_cancel_linked_queued_clauses(self):
        lib='PROGRAM LIB VAR amount:INTEGER ROUTINE work BEGIN amount=0 MOVE AWAY 2, WHEN TRUE DO amount=17 ENDMOVE END work BEGIN END LIB'
        body='n=0 CONNECT TIMER TO n CONDITION[1]: WHEN n>=100 DO CANCEL ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1 NOWAIT work() s=7'
        linked,p,ctx=project(body,500,200,lib=lib);linked.run('MAIN')
        self.assertEqual(linked.programs['LIB'].snapshot()['AMOUNT'],0);self.assertEqual(p.snapshot()['S'],7);self.assertEqual(terminal(ctx),['cancelled']*2)

    def test_pause_retains_borrowed_formal_and_return_path(self):
        routines='ROUTINE work(value:INTEGER) BEGIN MOVE AWAY 2, WHEN TRUE DO value=7 PAUSE value=value+10 ENDMOVE s=value END work'
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT work(n)',10,20,routines=routines)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['N'],7);self.assertEqual((p.resume()['N'],p.snapshot()['S']),(17,17));self.assertEqual(p._state.local_frames,[])

    def test_return_result_observes_completed_clause(self):
        routines='ROUTINE work:INTEGER VAR local:INTEGER BEGIN local=0 MOVE AWAY 2, WHEN TRUE DO local=7 ENDMOVE RETURN local END work'
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT n=work()',10,20,routines=routines)
        self.assertEqual(p.run()['N'],7);self.assertEqual(terminal(ctx),['completed']*2)

    def test_following_counter_is_legal_after_blocking_clause_finishes(self):
        p,ctx,_,_=run('a[1]=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE FOR n=1 TO 3 DO a[1]=a[1]+1 ENDFOR',10,20)
        p.run();self.assertEqual(p.snapshot()['A'][0],3.)


class BlockingClauseGuardTests(unittest.TestCase):
    def test_full_queue_rejects_before_clause_admission(self):
        ctx=bank(50,20,30,queue_limit=1)
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2 NOWAIT MOVE AWAY 3, WHEN TRUE DO n=7 ENDMOVE',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):p.run()
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(len(moves(ctx)),2)

    def test_held_group_rejects_before_clause_admission(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT HOLD MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',50,20)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'without a hold'):p.run()
        self.assertEqual(len(ctx.motion.responses),1)

    def test_false_completion_rejects_without_executing_clause(self):
        ctx=bank(50,20);ctx.motion.responses[1]['completed']=False
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=99 ENDMOVE',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'completion rejected'):p.run()
        self.assertEqual(p.snapshot()['N'],0);self.assertEqual(triggered(ctx)[1],[]);self.assertEqual(terminal(ctx),['cancelled','rejected'])

    def test_wrong_response_preserves_unaccepted_reply(self):
        ctx=bank(50,20,operations=['MOVE AWAY','MOVE AXIS'])
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'matching completion'):p.run()
        self.assertEqual(len(ctx.motion.responses),1)

    def test_invalid_operand_preserves_reply(self):
        ctx=bank(50,20,operations=['MOVE AWAY','MOVE AXIS'])
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AXIS 9 BY 1, WHEN TRUE DO n=7 ENDMOVE',ctx=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(len(ctx.motion.responses),1)

    def test_private_queue_wait_does_not_accept_bad_callable_descriptors(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT PAUSE',50,20)
        with self.assertRaises(rt.KarelPause):p.run()
        data=dict(delay_ms=20,elapsed_ms=0,handlers=[dict(kind='WHEN',line=1)],triggered=[])
        with self.assertRaises(rt.KarelRuntimeError):
            ctx.motion.invoke(p._state,'MOVE AWAY',dict(distance=2.),False,1,_execution=data,_background=True,_queue_wait=True,_clauses=[('WHEN',None,lambda:None,1)],_callback_context=(p._state,()))
        self.assertEqual(len(ctx.motion.responses),1);p.stop()

    def test_clock_replacement_fails_admitted_blocking_clauses(self):
        def sleep(_):p._state._clock_us=lambda:0
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',50,20,sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'clock adapter'):p.run()
        self.assertEqual(terminal(ctx),['failed']*2)

    def test_foreign_grant_after_promotion_is_preserved(self):
        foreign=object();calls=[0]
        def sleep(_):
            calls[0]+=1
            if calls[0]==2:
                ctx.group_locks.release_owner(p._state);ctx.group_locks._grant(1,foreign);ctx.group_locks.set_motion(1,'executing')
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',10,50,sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ownership grant'):p.run()
        self.assertIs(ctx.group_locks.owners[1],foreign);self.assertEqual(ctx.group_locks.motion[1],'executing');self.assertEqual(terminal(ctx),['completed','failed'])

    def test_stopped_label_after_promotion_is_preserved(self):
        calls=[0]
        def sleep(_):
            calls[0]+=1
            if calls[0]==2:ctx.group_locks.set_motion(1,'stopped')
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',10,50,sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'work label'):p.run()
        self.assertEqual(ctx.group_locks.motion[1],'stopped');self.assertEqual(terminal(ctx),['completed','failed'])

    def test_active_counter_write_is_still_rejected(self):
        with self.assertRaises(TranslationError):run('ATTACH FOR n=1 TO 3 DO MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE ENDFOR',10,20)

    def test_active_counter_predicate_write_is_still_rejected(self):
        routines='ROUTINE change:BOOLEAN BEGIN n=7 RETURN TRUE END change'
        with self.assertRaises(TranslationError):run('ATTACH FOR n=1 TO 3 DO MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN change() DO s=7 ENDMOVE ENDFOR',10,20,routines=routines)

    def test_independent_counter_and_clause_writes_are_supported(self):
        p,ctx,_,_=run('a[1]=0 ATTACH FOR s=1 TO 3 DO MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 a[1]=a[1]+1 ENDMOVE ENDFOR',5,6,5,6,5,6)
        self.assertEqual(p.run()['N'],7);self.assertEqual(p.snapshot()['A'][0],3.)


class BlockingClauseSchedulerTests(unittest.TestCase):
    def test_scheduler_drives_queued_blocking_clauses(self):
        linked,p,ctx=project('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',10,20)
        linked.run('MAIN');self.assertEqual(p.snapshot()['N'],7);self.assertEqual(terminal(ctx),['completed']*2)

    def test_scheduler_source_stays_before_following_statement(self):
        linked,p,ctx=project('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE s=17',50,20)
        waiting(linked,ctx);self.assertEqual(p.snapshot()['N'],0);linked.scheduler.run();self.assertEqual(p.snapshot()['S'],17)

    def test_scheduler_pause_keeps_admitted_handler(self):
        linked,p,ctx=project('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',50,20)
        waiting(linked,ctx);p.pause()
        for _ in range(100):
            linked.scheduler.step()
            if p.task_state=='paused':break
        self.assertEqual(p.task_state,'paused');before=elapsed(ctx);linked.scheduler.now_us+=100000
        linked.scheduler.step();self.assertEqual(elapsed(ctx),before)
        linked.scheduler.continue_task('MAIN');linked.scheduler.run();self.assertEqual(p.snapshot()['N'],7)

    def test_scheduler_stop_cancels_waiting_blocking_handler(self):
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',50,20)
        waiting(linked,ctx);linked.scheduler.stop('MAIN');self.assertEqual(terminal(ctx),['cancelled']*2);self.assertFalse(ctx.motion._queued)

    def test_scheduler_rename_preserves_blocking_handler_identity(self):
        linked,p,ctx=project('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',50,20)
        waiting(linked,ctx);linked.scheduler.rename('MAIN','RENAMED');linked.scheduler.run()
        self.assertIs(linked.scheduler.tasks['RENAMED'],p);self.assertEqual(p.snapshot()['N'],7)

    def test_scheduler_pause_inside_blocking_handler(self):
        linked,p,ctx=project('n=0 ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=1 PAUSE n=n+10 ENDMOVE',10,20)
        linked.run('MAIN');self.assertEqual(p.snapshot()['N'],1)
        linked.scheduler.continue_task('MAIN');linked.scheduler.run();self.assertEqual(p.snapshot()['N'],11);self.assertEqual(triggered(ctx)[1],[1])

    def test_scheduler_clock_failure_fails_whole_waiting_batch(self):
        now=[0];linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',50,20,clock_us=lambda:now[0])
        waiting(linked,ctx);now[0]=-1
        with self.assertRaises(rt.KarelRuntimeError):linked.scheduler.step()
        self.assertEqual(p.task_state,'failed');self.assertEqual(terminal(ctx),['failed']*2);self.assertFalse(linked.scheduler.waiting)

    def test_scheduler_linked_temporal_clause(self):
        lib='PROGRAM LIB VAR amount:INTEGER ROUTINE work BEGIN amount=0 MOVE AWAY 2, WHEN TIME 5 BEFORE NODE[1] DO amount=17 ENDMOVE END work BEGIN END LIB'
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT work()',ctx=planned(10,20),lib=lib)
        linked.run('MAIN');self.assertEqual(linked.programs['LIB'].snapshot()['AMOUNT'],17);self.assertEqual(triggered(ctx)[1],[1])

    def test_other_groups_do_not_become_a_global_barrier(self):
        ctx=bank(1000,5,20,groups={1:2,2:2})
        lib='PROGRAM LIB\n%DEFGROUP=2\nVAR amount:INTEGER ROUTINE work BEGIN amount=0 MOVE AWAY 3 NOWAIT MOVE AWAY 4, WHEN TRUE DO amount=17 ENDMOVE END work BEGIN END LIB'
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT work()',ctx=ctx,lib=lib)
        linked.run('MAIN');self.assertEqual(linked.programs['LIB'].snapshot()['AMOUNT'],17);self.assertEqual(terminal(ctx),['cancelled','completed','completed'])

    def test_qualified_local_cancel_keeps_other_group(self):
        ctx=bank(100,5,20,0,groups={1:2,2:2})
        lib='PROGRAM LIB\n%DEFGROUP=2\nVAR amount:INTEGER ROUTINE work BEGIN amount=0 MOVE AWAY 3 NOWAIT MOVE AWAY 4, UNTIL TRUE THEN amount=17 ENDMOVE END work BEGIN END LIB'
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT work() MOVE AWAY 5',ctx=ctx,lib=lib)
        linked.run('MAIN');self.assertEqual(terminal(ctx),['completed','completed','cancelled','completed'])
        self.assertEqual([r['data']['groups'] for r in ctx.motion.history if r['operation']=='CANCEL'],[[2]])


class BlockingClausePersistenceTests(unittest.TestCase):
    def finished(self,clause='WHEN TRUE DO n=7'):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, '+clause+' ENDMOVE',10,20);p.run();return ctx

    def test_completed_history_roundtrip(self):
        ctx=self.finished();saved=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_cancelled_history_roundtrip(self):
        ctx=self.finished('UNTIL TRUE THEN n=7');saved=ctx.to_config();self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_failed_history_roundtrip(self):
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=1 DIV 0 ENDMOVE',10,20)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        saved=ctx.to_config();self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_pending_blocking_handler_cannot_be_saved(self):
        linked,p,ctx=project('ATTACH MOVE AWAY 1 NOWAIT MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',50,20)
        waiting(linked,ctx)
        with self.assertRaisesRegex(ValueError,'active motion'):ctx.motion.to_config()
        linked.scheduler.stop('MAIN')

    def test_pending_history_cannot_reload(self):
        saved=self.finished().motion.to_config();saved['history'][-1]['outcome']='pending'
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)

    def test_malformed_handler_data_cannot_reload(self):
        saved=self.finished().motion.to_config();saved['history'][-1]['data']['execution']['handlers'][0]['kind']='INVALID'
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)

    def test_no_callables_or_wait_generators_in_saved_state(self):
        data=json.dumps(self.finished().to_config())
        for text in ('local_frames','_queue_wait','predicate','<function','generator'):
            self.assertNotIn(text,data)

    def test_terminal_false_nowait_flag_stays_false(self):
        ctx=self.finished();saved=ctx.motion.to_config();self.assertFalse(saved['history'][-1]['nowait'])
        self.assertFalse(rt.MotionRequests.from_config(saved).history[-1]['nowait'])


if __name__=='__main__':
    unittest.main()
