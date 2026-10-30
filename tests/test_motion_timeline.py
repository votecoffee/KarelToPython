"""Authored explicit arrival schedules, temporal captures and exact progress events."""
from copy import deepcopy
import json
import unittest

from karel2py import runtime as rt, translate, translate_project
from karel2py.lexer import TranslationError
from tests.test_motion_handlers import program, execute, move
from tests.test_motion_requests import context, DECL
from tests.test_project_scheduler import source


PATH_SETUP='APPEND_NODE(route,s) route[1].node_pos=p APPEND_NODE(route,s) route[2].node_pos=q '


def planned(*, operation='MOVE AWAY', delay=23, nodes=None, completed=True):
    return context(capture_only=False,responses=[dict(operation=operation,completed=completed,
        delay_ms=delay,node_times=nodes if nodes is not None else {'0':0,'1':delay})])


class TemporalConditionTests(unittest.TestCase):
    def test_exact_non_grid_breakpoints_source_order_and_before_clamping(self):
        values,ctx,_,_,pauses=execute(PATH_SETUP+'''n=0 ATTACH MOVE ALONG route,
WHEN AT NODE[0] DO n=n*10+1
WHEN TIME 3 BEFORE NODE[1] DO n=n*10+2
WHEN AT NODE[1] DO n=n*10+3
WHEN TIME 2 AFTER NODE[1] DO n=n*10+4
WHEN TIME 100 BEFORE NODE[2] DO n=n*10+5
WHEN AT NODE[2] DO n=n*10+6
ENDMOVE''',ctx=planned(operation='MOVE ALONG',nodes={'0':0,'1':7,'2':23}))
        self.assertEqual(values['N'],123546)
        self.assertEqual(pauses,[.004,.003,.002,.01,.004])
        self.assertEqual(move(ctx)['data']['execution']['triggered'],[1,2,3,5,4,6])
        self.assertEqual(move(ctx)['data']['execution']['elapsed_ms'],23)

    def test_at_destination_and_start_are_distinct_events(self):
        values,ctx,_,_,pauses=execute('n=0 ATTACH MOVE AWAY 1, WHEN AT NODE[0] DO n=1 WHEN AT NODE[1] DO n=n+10 ENDMOVE',ctx=planned(delay=7))
        self.assertEqual(values['N'],11)
        self.assertEqual(pauses,[.007])
        self.assertEqual(move(ctx)['data']['execution']['conditions'],[
            dict(kind='AT',node=0,offset_ms=0),dict(kind='AT',node=1,offset_ms=0)])

    def test_until_at_node_cancels_at_the_declared_arrival(self):
        values,ctx,_,_,pauses=execute(PATH_SETUP+'n=0 ATTACH MOVE ALONG route, UNTIL AT NODE[1] THEN n=1 ENDMOVE',
            ctx=planned(operation='MOVE ALONG',nodes={'0':0,'1':7,'2':23}))
        self.assertEqual((values['N'],move(ctx)['outcome']),(1,'cancelled'))
        self.assertEqual(pauses,[.007])
        self.assertEqual(move(ctx)['data']['execution']['elapsed_ms'],7)

    def test_before_start_and_after_final_node_never_fire(self):
        values,ctx,_,_,_=execute('''n=0 ATTACH MOVE AWAY 1,
WHEN TIME 0 BEFORE NODE[0] DO n=n+1
WHEN TIME 0 AFTER NODE[1] DO n=n+10
WHEN TIME 1 AFTER NODE[1] DO n=n+100
ENDMOVE''',ctx=planned(delay=7))
        self.assertEqual(values['N'],0)
        self.assertEqual(move(ctx)['data']['execution']['triggered'],[])

    def test_before_large_offset_clamps_to_segment_start(self):
        values,ctx,_,_,pauses=execute('n=0 ATTACH MOVE AWAY 1, WHEN TIME 999 BEFORE NODE[1] DO n=1 ENDMOVE',ctx=planned(delay=7))
        self.assertEqual(values['N'],1)
        self.assertEqual(pauses,[.007])
        self.assertEqual(move(ctx)['data']['execution']['triggered'],[1])

    def test_after_start_can_fire_at_end_but_not_beyond_it(self):
        values,ctx,_,_,_=execute('n=0 ATTACH MOVE AWAY 1, WHEN TIME 7 AFTER NODE[0] DO n=1 WHEN TIME 8 AFTER NODE[0] DO n=99 ENDMOVE',ctx=planned(delay=7))
        self.assertEqual(values['N'],1)
        self.assertEqual(move(ctx)['data']['execution']['triggered'],[1])

    def test_wildcard_excludes_start_and_fires_once(self):
        observations=[];ctx=planned(operation='MOVE ALONG',nodes={'0':0,'1':7,'2':23})
        def sleep(seconds):observations.append((move(ctx)['data']['execution']['elapsed_ms'],p.snapshot()['N'],seconds))
        p,_,_,_=program(PATH_SETUP+'n=0 ATTACH MOVE ALONG route, WHEN AT NODE[*] DO n=n+1 ENDMOVE',ctx=ctx,sleep=sleep)
        self.assertEqual(p.run()['N'],1)
        self.assertEqual(observations[0],(0,0,.007))
        self.assertEqual(observations[1][:2],(7,1))

    def test_wildcard_time_event_can_match_later_node_after_gate_miss(self):
        ctx=planned(operation='MOVE ALONG',nodes={'0':0,'1':7,'2':23});ctx.ports=rt.PortBank({'DIN':1},{('DIN',1):False})
        observations=[]
        def sleep(seconds):
            progress=move(ctx)['data']['execution']['elapsed_ms']
            observations.append((progress,p.snapshot()['N']))
            if progress>=7:ctx.ports.update('DIN',1,True)
        p,_,_,_=program(PATH_SETUP+'n=0 ATTACH MOVE ALONG route, WHEN TIME 2 BEFORE NODE[*] AND DIN[1] DO n=99 ENDMOVE',ctx=ctx,sleep=sleep)
        self.assertEqual(p.run()['N'],99)
        self.assertEqual(observations,[(0,0),(5,0),(7,0),(17,0),(21,99)])

    def test_after_wildcard_omits_final_node(self):
        values,ctx,_,_,pauses=execute(PATH_SETUP+'n=0 ATTACH MOVE ALONG route, WHEN TIME 2 AFTER NODE[*] DO n=n+1 ENDMOVE',
            ctx=planned(operation='MOVE ALONG',nodes={'0':0,'1':7,'2':23}))
        self.assertEqual(values['N'],1)
        self.assertEqual(pauses,[.007,.002,.01,.004])

    def test_selected_path_range_uses_original_node_numbers(self):
        setup=PATH_SETUP+'APPEND_NODE(route,s) route[3].node_pos=p '
        values,ctx,_,_,_=execute(setup+'n=0 ATTACH MOVE ALONG route[2..3], WHEN AT NODE[2] DO n=2 WHEN AT NODE[3] DO n=n+3 ENDMOVE',
            ctx=planned(operation='MOVE ALONG',nodes={'0':0,'2':5,'3':23}))
        self.assertEqual(values['N'],5)
        self.assertEqual(move(ctx)['data']['start'],2)

    def test_equal_and_zero_duration_arrivals_are_explicit(self):
        values,ctx,_,_,pauses=execute(PATH_SETUP+'n=0 ATTACH MOVE ALONG route, WHEN AT NODE[0] DO n=n+1 WHEN AT NODE[1] DO n=n+10 WHEN AT NODE[2] DO n=n+100 ENDMOVE',
            ctx=planned(operation='MOVE ALONG',delay=0,nodes={'0':0,'1':0,'2':0}))
        self.assertEqual(values['N'],111)
        self.assertEqual(pauses,[])
        self.assertEqual(move(ctx)['outcome'],'completed')

    def test_no_conditions_still_records_and_observes_explicit_arrivals(self):
        _,ctx,_,_,pauses=execute(PATH_SETUP+'ATTACH MOVE ALONG route',ctx=planned(operation='MOVE ALONG',nodes={'0':0,'1':7,'2':23}))
        self.assertEqual(pauses,[.007,.01,.006])
        self.assertEqual(move(ctx)['data']['execution']['node_times'],{'0':0,'1':7,'2':23})


class TemporalCaptureTests(unittest.TestCase):
    def test_offset_and_node_expressions_capture_once_in_source_order(self):
        routines='''ROUTINE offset_value:INTEGER BEGIN n=n*10+1 RETURN 3 END offset_value
ROUTINE node_value:INTEGER BEGIN n=n*10+2 RETURN 1 END node_value'''
        values,ctx,_,_,_=execute('n=0 s=0 ATTACH MOVE AWAY 1, WHEN TIME offset_value() BEFORE NODE[node_value()] DO s=1 ENDMOVE',
            ctx=planned(delay=7),routines=routines)
        self.assertEqual((values['N'],values['S']),(12,1))
        self.assertEqual(move(ctx)['data']['execution']['conditions'],[dict(kind='BEFORE',node=1,offset_ms=3)])

    def test_selector_values_do_not_retime_after_actions_change_variables(self):
        values,ctx,_,_,_=execute('n=3 s=1 ATTACH MOVE AWAY 1, WHEN AT NODE[0] DO n=99 s=0 WHEN TIME n BEFORE NODE[s] DO q.x=123 ENDMOVE',ctx=planned(delay=7))
        self.assertEqual(values['Q']['X'],123.)
        self.assertEqual(move(ctx)['data']['execution']['conditions'][-1],dict(kind='BEFORE',node=1,offset_ms=3))

    def test_eval_in_temporal_selector_uses_existing_capture_policy(self):
        _,ctx,_,_,_=execute('n=3 ATTACH MOVE AWAY 1, WHEN TIME EVAL(n) BEFORE NODE[1] DO n=9 ENDMOVE',ctx=planned(delay=7))
        self.assertEqual(move(ctx)['data']['execution']['conditions'],[dict(kind='BEFORE',node=1,offset_ms=3)])

    def test_time_at_and_node_identifiers_remain_ordinary_outside_forms(self):
        values,_,_,_,_=execute('time=1 at=TRUE node=1 n=0 ATTACH MOVE AWAY 1, WHEN at AND (time+1>1) AND AT NODE[node] DO n=1 ENDMOVE',
            ctx=planned(delay=7),decl=DECL+' time,node:INTEGER at:BOOLEAN')
        self.assertEqual(values['N'],1)

    def test_ordinary_time_arithmetic_before_temporal_boolean_is_not_a_prefix(self):
        values,_,_,_,_=execute('time=2 n=0 ATTACH MOVE AWAY 1, WHEN (time+1>2) AND TIME 3 BEFORE NODE[1] DO n=1 ENDMOVE',
            ctx=planned(delay=7),decl=DECL+' time:INTEGER')
        self.assertEqual(values['N'],1)

    def test_parentheses_and_negation_combine_with_temporal_events(self):
        values,_,_,_,_=execute('n=0 ATTACH MOVE AWAY 1, WHEN (AT NODE[1]) AND NOT FALSE DO n=1 ENDMOVE',ctx=planned(delay=7))
        self.assertEqual(values['N'],1)

    def test_report_metadata_stays_on_move_when_actions_append_other_requests(self):
        _,_,_,result,_=execute('ATTACH MOVE AWAY 1, WHEN AT NODE[1] DO OPEN HAND 1 ENDMOVE',ctx=planned(delay=7))
        request=next(row for row in result.report['motion_requests'] if row['operation']=='MOVE AWAY')
        hand=next(row for row in result.report['motion_requests'] if row['operation']=='OPEN HAND')
        self.assertEqual(request['local_handlers'][0]['kind'],'WHEN')
        self.assertEqual(request['conditions'][0]['kind'],'AT')
        self.assertNotIn('local_handlers',hand)
        self.assertNotIn('conditions',hand)

    def test_boolean_only_report_local_handlers_stay_on_move_too(self):
        _,_,_,result,_=execute('ATTACH MOVE AWAY 1, WHEN TRUE DO OPEN HAND 1 ENDMOVE')
        request=next(row for row in result.report['motion_requests'] if row['operation']=='MOVE AWAY')
        self.assertEqual(request['local_handlers'][0]['kind'],'WHEN')

    def test_exactly_64_temporal_terms_are_supported(self):
        condition=' OR '.join('AT NODE[1]' for _ in range(64))
        values,ctx,_,_,_=execute('n=0 ATTACH MOVE AWAY 1, WHEN '+condition+' DO n=1 ENDMOVE',ctx=planned(delay=7))
        self.assertEqual(values['N'],1)
        self.assertEqual(len(move(ctx)['data']['execution']['conditions']),64)


class TemporalValidationTests(unittest.TestCase):
    def test_capture_only_cannot_invent_arrivals_even_for_node_zero(self):
        for expression in ('AT NODE[0]','AT NODE[1]','TIME 0 AFTER NODE[0]','FALSE AND AT NODE[1]'):
            p,ctx,_,_=program('ATTACH MOVE AWAY 1, WHEN '+expression+' DO n=1 ENDMOVE')
            with self.subTest(expression=expression),self.assertRaisesRegex(rt.KarelRuntimeError,'node_times'):p.run()
            self.assertEqual([r['operation'] for r in ctx.motion.history],['ATTACH'])
            self.assertEqual(ctx.motion._active,{})

    def test_delay_alone_does_not_invent_node_arrivals(self):
        ctx=context(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True,delay_ms=7)])
        p,_,_,_=program('ATTACH MOVE AWAY 1, WHEN AT NODE[1] DO n=1 ENDMOVE',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'node_times'):p.run()
        self.assertEqual(len(ctx.motion.responses),1)

    def test_plan_must_match_actual_nonpath_or_selected_path_nodes(self):
        for body,nodes in [('MOVE AWAY 1',{'0':0,'2':23}),('MOVE ALONG route',{'0':0,'1':23}),
                           ('MOVE ALONG route[2]',{'0':0,'1':7,'2':23})]:
            operation='MOVE ALONG' if 'ALONG' in body else 'MOVE AWAY'
            ctx=planned(operation=operation,nodes=nodes);p,_,_,_=program(PATH_SETUP+'ATTACH '+body,ctx=ctx)
            with self.subTest(body=body),self.assertRaisesRegex(rt.KarelRuntimeError,'range'):p.run()
            self.assertEqual(len(ctx.motion.responses),1)
            self.assertEqual(len(ctx.motion.history),1)

    def test_unknown_node_and_invalid_captured_values_fail_before_consumption(self):
        for expression in ('AT NODE[2]','AT NODE[-1]','AT NODE[32768]','TIME -1 BEFORE NODE[1]',
                           'TIME 86400001 AFTER NODE[0]'):
            ctx=planned(delay=7);p,_,_,_=program('ATTACH MOVE AWAY 1, WHEN '+expression+' DO n=1 ENDMOVE',ctx=ctx)
            with self.subTest(expression=expression),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(len(ctx.motion.responses),1)
            self.assertEqual(len(ctx.motion.history),1)

    def test_invalid_arrival_scripts_rejected_during_configuration(self):
        cases=[None,{},[],{'0':0},{'00':0,'1':23},{'0':1,'1':23},{'0':0,'1':22},
               {'0':0,'1':24},{'0':0,'1':True},{'0':0,'1':7.0},{'0':0,'32768':23},
               {'0':0,'1':15,'2':7,'3':23}]
        for nodes in cases:
            with self.subTest(nodes=nodes),self.assertRaises(ValueError):
                rt.MotionRequests({1:2},responses=[dict(operation='MOVE AWAY',completed=True,delay_ms=23,node_times=nodes)])
        with self.assertRaises(ValueError):
            rt.MotionRequests({1:2},responses=[dict(operation='MOVE AWAY',completed=True,node_times={'0':0,'1':0})])

    def test_nowait_cannot_ignore_even_a_zero_duration_plan(self):
        ctx=planned(delay=0);p,_,_,_=program('ATTACH MOVE AWAY 1 NOWAIT',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'NOWAIT'):p.run()
        self.assertEqual(len(ctx.motion.responses),1)

    def test_false_response_validates_plan_but_runs_no_temporal_actions(self):
        ctx=planned(delay=7,completed=False);p,_,_,pauses=program('n=0 ATTACH MOVE AWAY 1, WHEN AT NODE[0] DO n=1 ENDMOVE',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'completion rejected'):p.run()
        self.assertEqual(p.snapshot()['N'],0)
        self.assertEqual(pauses,[])
        self.assertEqual(move(ctx)['outcome'],'rejected')

    def test_raw_history_plan_and_unused_response_inputs_are_copied(self):
        nodes={'1':7,'0':0};ctx=planned(delay=7,nodes=nodes);nodes['1']=3
        _,ctx,_,_,_=execute('ATTACH MOVE AWAY 1, WHEN AT NODE[1] DO n=1 ENDMOVE',ctx=ctx)
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved)
        saved['motion']['history'][1]['data']['execution']['node_times']['1']=3
        self.assertEqual(move(restored)['data']['execution']['node_times']['1'],7)

    def test_tampered_plan_and_temporal_history_are_rejected(self):
        _,ctx,_,_,_=execute('ATTACH MOVE AWAY 1, WHEN AT NODE[1] DO n=1 ENDMOVE',ctx=planned(delay=7))
        original=ctx.motion.to_config()
        for key,value in [('node_times',{'0':0,'2':7}),('node_times',{'0':0,'1':6}),
                          ('conditions',[]),('conditions',[dict(kind='AT',node=True,offset_ms=0)]),
                          ('conditions',[dict(kind='AT',node=1,offset_ms=1)]),
                          ('conditions',[dict(kind='AFTER',node=2,offset_ms=0)]),
                          ('conditions',[dict(kind='AT',node=1,offset_ms=0,extra=1)])]:
            data=deepcopy(original);data['history'][1]['data']['execution'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)
        data=deepcopy(original);data['history'][1]['data']['execution'].pop('node_times')
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(data)


class TemporalLifecycleTests(unittest.TestCase):
    def test_pause_at_arrival_retains_future_temporal_events(self):
        p,ctx,_,_=program(PATH_SETUP+'n=0 ATTACH MOVE ALONG route, WHEN AT NODE[1] DO n=1 PAUSE WHEN AT NODE[2] DO n=2 ENDMOVE',
            ctx=planned(operation='MOVE ALONG',nodes={'0':0,'1':7,'2':23}))
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(move(ctx)['data']['execution']['elapsed_ms'],7)
        with self.assertRaises(ValueError):ctx.motion.to_config()
        self.assertEqual(p.resume()['N'],2)
        self.assertEqual(move(ctx)['data']['execution']['triggered'],[1,2])

    def test_stop_at_arrival_purges_scope_without_fake_destination(self):
        p,ctx,_,_=program(PATH_SETUP+'n=0 ATTACH MOVE ALONG route, WHEN AT NODE[1] DO n=1 PAUSE WHEN AT NODE[2] DO n=2 ENDMOVE',
            ctx=planned(operation='MOVE ALONG',nodes={'0':0,'1':7,'2':23}))
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop()
        self.assertEqual(p.snapshot()['N'],1)
        self.assertEqual(move(ctx)['outcome'],'cancelled')
        self.assertEqual(move(ctx)['data']['execution']['elapsed_ms'],7)
        self.assertEqual(ctx.motion._active,{})
        rt.ExecutionContext.from_config(ctx.to_config())

    def test_hold_freezes_progress_while_global_polling_can_release_it(self):
        ctx=planned(delay=7);ctx.ports=rt.PortBank({'DIN':1},{('DIN',1):False});observations=[]
        def sleep(seconds):
            observations.append((move(ctx)['data']['execution']['elapsed_ms'],seconds))
            ctx.ports.update('DIN',1,True)
        values,ctx,_,_,_=execute('''n=0
CONDITION[1]: WHEN DIN[1] DO UNHOLD ENDCONDITION ENABLE CONDITION[1]
ATTACH MOVE AWAY 1, WHEN AT NODE[0] DO HOLD WHEN AT NODE[1] DO n=1 ENDMOVE''',ctx=ctx,sleep=sleep)
        self.assertEqual(values['N'],1)
        self.assertEqual(observations,[(0,.01),(0,.007)])
        self.assertEqual(move(ctx)['data']['execution']['elapsed_ms'],7)

    def test_linked_routine_uses_caller_scope_and_local_selector_values(self):
        ctx=planned(delay=7)
        lib=source('LIB','',routines='ROUTINE work(target:INTEGER):INTEGER VAR local:INTEGER BEGIN local=0 MOVE AWAY 1, WHEN AT NODE[target] DO local=7 ENDMOVE RETURN local END work')
        main=source('MAIN','ATTACH n=work(1)',routines='ROUTINE work(target:INTEGER):INTEGER FROM LIB')
        instance=translate_project({'main':main,'lib':lib}).instantiate(context=ctx)
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['N'],7)
        self.assertEqual((move(ctx)['program'],move(ctx)['source_program']),('MAIN','LIB'))
        self.assertEqual(ctx.motion._active,{})

    def test_until_before_node_ends_without_reaching_later_schedule_points(self):
        _,ctx,_,_,pauses=execute(PATH_SETUP+'ATTACH MOVE ALONG route, UNTIL TIME 3 BEFORE NODE[2] ENDMOVE',
            ctx=planned(operation='MOVE ALONG',nodes={'0':0,'1':7,'2':23}))
        self.assertEqual(move(ctx)['outcome'],'cancelled')
        self.assertEqual(move(ctx)['data']['execution']['elapsed_ms'],20)
        self.assertEqual(pauses,[.007,.01,.003])

    def test_new_scope_does_not_reuse_old_temporal_event_map(self):
        ctx=context(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True,delay_ms=7,node_times={'0':0,'1':7}),dict(operation='MOVE AWAY',completed=True,delay_ms=3,node_times={'0':0,'1':3})])
        values,ctx,_,_,pauses=execute('n=0 ATTACH MOVE AWAY 1, WHEN AT NODE[1] DO n=n+1 ENDMOVE MOVE AWAY 1, WHEN AT NODE[1] DO n=n+10 ENDMOVE',ctx=ctx)
        self.assertEqual(values['N'],11)
        self.assertEqual(pauses,[.007,.003])
        self.assertEqual(ctx.motion._active,{})

    def test_global_cancellation_at_arrival_precedes_the_local_node_event(self):
        ctx=planned(delay=7);ctx.ports=rt.PortBank({'DIN':1},{('DIN',1):False})
        def sleep(_):ctx.ports.update('DIN',1,True)
        values,ctx,_,_,_=execute('n=0 CONDITION[1]: WHEN DIN[1] DO CANCEL ENDCONDITION ENABLE CONDITION[1] ATTACH MOVE AWAY 1, WHEN AT NODE[1] DO n=1 ENDMOVE',ctx=ctx,sleep=sleep)
        self.assertEqual(values['N'],0)
        self.assertEqual(move(ctx)['outcome'],'cancelled')
        self.assertEqual(move(ctx)['data']['execution']['elapsed_ms'],7)
        self.assertEqual(move(ctx)['data']['execution']['triggered'],[])

    def test_concurrent_tasks_keep_distinct_arrival_maps_and_condition_frames(self):
        ctx=context(capture_only=False,groups={1:2,2:2},responses=[
            dict(operation='MOVE AWAY',completed=True,delay_ms=7,node_times={'0':0,'1':7}),
            dict(operation='MOVE AWAY',completed=True,delay_ms=13,node_times={'0':0,'1':13})])
        main=source('MAIN','LOCK_GROUP(1,s) n=0 MOVE AWAY 1, WHEN AT NODE[1] DO n=1 ENDMOVE')
        second='PROGRAM SECOND\n%DEFGROUP=2\nVAR n,s:INTEGER\nBEGIN LOCK_GROUP(2,s) n=0 MOVE AWAY 1, WHEN AT NODE[1] DO n=2 ENDMOVE END SECOND'
        instance=translate_project({'main':main,'second':second}).instantiate(context=ctx)
        instance.scheduler.start('MAIN');instance.scheduler.start('SECOND');instance.scheduler.run()
        self.assertEqual((instance.programs['MAIN'].snapshot()['N'],instance.programs['SECOND'].snapshot()['N']),(1,2))
        self.assertEqual({row['data']['execution']['elapsed_ms'] for row in ctx.motion.history},{7,13})
        self.assertEqual(ctx.motion._active,{})
        self.assertEqual(ctx.group_locks.owners,{})


class TemporalSourceGuards(unittest.TestCase):
    def test_nonlocal_and_malformed_temporal_forms_stay_blocked(self):
        for body in ('CONDITION[1]: WHEN AT NODE[1] DO n=1 ENDCONDITION',
                     'MOVE AWAY 1, WHEN AT NODE[TRUE] DO n=1 ENDMOVE',
                     'MOVE AWAY 1, WHEN TIME 1.5 BEFORE NODE[1] DO n=1 ENDMOVE',
                     'MOVE AWAY 1, WHEN TIME 1 BEFORE START DO n=1 ENDMOVE',
                     'MOVE AWAY 1, WHEN AT NODE[1,2] DO n=1 ENDMOVE',
                     'MOVE AWAY 1, WHEN AT NODE[] DO n=1 ENDMOVE',
                     'n=AT NODE[1]'):
            with self.subTest(body=body),self.assertRaises(TranslationError):program(body)

    def test_more_than_64_terms_and_outer_for_counter_writes_rejected(self):
        with self.assertRaises(TranslationError):
            program('MOVE AWAY 1, WHEN '+' OR '.join('AT NODE[1]' for _ in range(65))+' DO n=1 ENDMOVE')
        routines='ROUTINE changed:INTEGER BEGIN n=9 RETURN 1 END changed'
        with self.assertRaisesRegex(TranslationError,'E_FOR_COUNTER'):
            program('FOR n=1 TO 2 DO MOVE AWAY 1, WHEN AT NODE[changed()] DO s=1 ENDMOVE ENDFOR',routines=routines)


if __name__ == '__main__':
    unittest.main()
