"""Authored hold/cancel state, local WITH settings and ownership regressions."""
from copy import deepcopy
import json
import unittest

from karel2py import runtime as rt, translate, translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_motion_requests import context, execute, program
from tests.test_project_scheduler import source


def banks(*, motion=None, held=None, sequence=0):
    ctx=context(groups={1:2,2:2,3:2},sequence=sequence)
    ctx.group_locks=rt.GroupLocks([1,2,3],motion=motion,held=held)
    ctx.controller=rt.ControllerServices()
    return ctx


class MotionControlTests(unittest.TestCase):
    def test_idle_hold_blocks_future_move_until_unhold(self):
        p,ctx,_=program('ATTACH HOLD PAUSE MOVE TO p')
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(ctx.group_locks.held,{1})
        self.assertEqual(ctx.group_locks.motion,{})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'without a hold'):p.resume()
        self.assertEqual([r['operation'] for r in ctx.motion.history],['ATTACH','HOLD'])
        self.assertEqual(ctx.group_locks.owners,{})
        self.assertEqual(ctx.group_locks.held,{1})

    def test_unhold_preserves_active_stopped_and_idle_work(self):
        ctx=banks(motion={1:'executing',2:'stopped'},held=[1,2,3])
        execute('LOCK_GROUP(7,s) UNHOLD',ctx=ctx)
        self.assertEqual(ctx.group_locks.motion,{1:'executing',2:'stopped'})
        self.assertEqual(ctx.group_locks.held,set())
        self.assertEqual(ctx.motion.history[0]['data']['groups'],[1,2,3])

    def test_hold_and_cancel_keep_stopped_work_separate(self):
        ctx=banks(motion={1:'executing',2:'stopped'})
        execute('LOCK_GROUP(7,s) HOLD GROUP[1,2] CANCEL GROUP[1,2]',ctx=ctx)
        self.assertEqual(ctx.group_locks.motion,{2:'stopped'})
        self.assertEqual(ctx.group_locks.held,{1,2})
        first,last=ctx.motion.history
        self.assertEqual(first['data']['states'][0],dict(group=1,
            before=dict(motion='executing',held=False),after=dict(motion='executing',held=True)))
        self.assertEqual(last['data']['states'][1],dict(group=2,
            before=dict(motion='stopped',held=True),after=dict(motion='stopped',held=True)))

    def test_cancel_stopped_then_unhold_clears_two_independent_states(self):
        ctx=banks(motion={1:'stopped'},held=[1])
        execute('LOCK_GROUP(1,s) CNCL_STP_MTN UNHOLD GROUP[1] MOVE AWAY 2',ctx=ctx)
        self.assertEqual(ctx.group_locks.motion,{})
        self.assertEqual(ctx.group_locks.held,set())
        self.assertEqual(ctx.controller.history[0]['data']['groups'],[1])

    def test_mixed_group_selection_and_repeated_actions_are_deterministic(self):
        _,ctx,_,_=execute('ATTACH HOLD GROUP[1] HOLD GROUP[1] UNHOLD GROUP[1] UNHOLD GROUP[1] CANCEL GROUP[1]')
        self.assertEqual(ctx.group_locks.held,set())
        self.assertEqual([r['sequence'] for r in ctx.motion.history],list(range(1,7)))
        self.assertEqual(ctx.motion.history[-1]['data']['states'][0]['after'],dict(motion='idle',held=False))

    def test_bare_control_without_owned_groups_is_a_recorded_noop(self):
        _,ctx,_,_=execute('HOLD UNHOLD CANCEL')
        self.assertEqual([r['data'] for r in ctx.motion.history],[dict(groups=[],states=[])]*3)

    def test_foreign_owner_is_not_affected_by_bare_control(self):
        ctx=banks(motion={2:'executing'})
        foreign,_,_=program('',ctx=ctx,setup='');ctx.group_locks._grant(2,foreign._state)
        execute('LOCK_GROUP(1,s) HOLD CANCEL UNHOLD',ctx=ctx)
        self.assertEqual(ctx.group_locks.motion,{2:'executing'})
        self.assertIs(ctx.group_locks.owners[2],foreign._state)
        self.assertEqual([r['data']['groups'] for r in ctx.motion.history],[[1]]*3)
        ctx.group_locks.release_owner(foreign._state)

    def test_explicit_foreign_group_fails_atomically(self):
        ctx=banks(motion={1:'executing',2:'executing'})
        foreign,_,_=program('',ctx=ctx,setup='');ctx.group_locks._grant(2,foreign._state)
        p,_,_=program('LOCK_GROUP(1,s) HOLD GROUP[1,2]',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'another task'):p.run()
        self.assertEqual(ctx.group_locks.held,set())
        self.assertEqual(ctx.motion.history,[])
        self.assertIs(ctx.group_locks.owners[2],foreign._state)
        ctx.group_locks.release_owner(foreign._state)

    def test_explicit_unowned_invalid_and_duplicate_groups_fail_before_changes(self):
        for selection in ('[1]','[0]','[4]','[1,1]'):
            p,ctx,_=program('HOLD GROUP'+selection)
            with self.subTest(selection=selection),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(ctx.motion.history,[])
            self.assertEqual(ctx.group_locks.held,set())

    def test_group_expressions_are_captured_once_in_source_order(self):
        ctx=banks()
        routines='ROUTINE next_group:INTEGER BEGIN n=n+1 RETURN n END next_group'
        values,ctx,_,_=execute('n=0 ATTACH HOLD GROUP[next_group(),next_group()] UNHOLD',ctx=ctx,routines=routines)
        self.assertEqual(values['N'],2)
        self.assertEqual(ctx.motion.history[1]['data']['groups'],[1,2])

    def test_handler_control_uses_current_owned_set(self):
        ctx=banks(motion={1:'executing',2:'stopped'})
        execute('''n=0
CONDITION[1]: WHEN n=1 DO HOLD, CANCEL ENDCONDITION
ENABLE CONDITION[1]
LOCK_GROUP(3,s) n=1 DELAY 0
UNHOLD''',ctx=ctx)
        self.assertEqual([r['operation'] for r in ctx.motion.history],['HOLD','CANCEL','UNHOLD'])
        self.assertEqual(ctx.motion.history[0]['data']['groups'],[1,2])
        self.assertEqual(ctx.group_locks.motion,{2:'stopped'})
        self.assertEqual(ctx.group_locks.held,set())

    def test_hands_can_be_controlled_while_motion_is_held_or_busy(self):
        ctx=banks(motion={1:'executing'},held=[1])
        execute('LOCK_GROUP(1,s) OPEN HAND 1 CLOSE HAND 1 RELAX HAND 1',ctx=ctx)
        self.assertEqual(ctx.motion.hands[1],'relaxed')
        self.assertEqual(ctx.group_locks.motion,{1:'executing'})
        self.assertEqual(ctx.group_locks.held,{1})

    def test_release_and_unlock_do_not_bypass_idle_hold(self):
        values,ctx,_,_=execute('ATTACH HOLD UNLOCK_GROUP(1,s) n=s UNHOLD UNLOCK_GROUP(1,s)')
        self.assertEqual((values['N'],values['S']),(17039,0))
        p,ctx,_=program('ATTACH HOLD RELEASE')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'without a hold'):p.run()
        self.assertEqual([r['operation'] for r in ctx.motion.history],['ATTACH','HOLD'])
        self.assertEqual(ctx.group_locks.held,{1})

    def test_automatic_root_and_scoped_acquisition_cannot_steal_held_group(self):
        for scoped in (False,True):
            ctx=context();ctx.group_locks=rt.GroupLocks([1],held=[1],apply_directives=True,callee_scopes=scoped)
            p,_,_=program('n=9',ctx=ctx,setup='')
            with self.subTest(scoped=scoped),self.assertRaisesRegex(rt.KarelRuntimeError,'busy'):p.run()
            self.assertEqual(ctx.group_locks.owners,{})

    def test_control_does_not_consume_future_scripted_move_reply(self):
        ctx=context(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True)])
        execute('ATTACH HOLD CANCEL UNHOLD MOVE AWAY 2',ctx=ctx)
        self.assertEqual([r['outcome'] for r in ctx.motion.history],['completed']*5)
        self.assertEqual(ctx.motion.responses,[])

    def test_sequence_exhaustion_does_not_publish_hold(self):
        ctx=banks(sequence=2147483646);p,_,_=program('LOCK_GROUP(1,s) HOLD',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'sequence exhausted'):p.run()
        self.assertEqual(ctx.motion.history,[])
        self.assertEqual(ctx.group_locks.held,set())

    def test_child_program_retains_root_hold_until_caller_unholds(self):
        ctx=context()
        instance=translate_project({'main':source('MAIN',"ATTACH CALL_PROG('WORKER',entry) UNHOLD MOVE AWAY 1",decl='entry:INTEGER'),
            'worker':source('WORKER','HOLD')}).instantiate(context=ctx)
        instance.run('MAIN')
        self.assertEqual([r['program'] for r in ctx.motion.history],['MAIN']*4)
        self.assertEqual(ctx.motion.history[1]['source_program'],'WORKER')
        self.assertEqual(ctx.group_locks.held,set())

    def test_linked_routine_control_uses_calling_root(self):
        ctx=context()
        instance=translate_project({'main':source('MAIN','ATTACH control_group() UNHOLD MOVE AWAY 1',routines='ROUTINE control_group FROM LIB'),
            'lib':source('LIB','',routines='ROUTINE control_group BEGIN HOLD GROUP[1] END control_group')}).instantiate(context=ctx)
        instance.run('MAIN')
        self.assertEqual((ctx.motion.history[1]['program'],ctx.motion.history[1]['source_program']),('MAIN','LIB'))

    def test_stop_abort_and_budget_release_owners_but_preserve_logical_hold(self):
        for ending,error in [('PAUSE',rt.KarelPause),('ABORT',rt.KarelAbort),('WHILE TRUE DO n=1 ENDWHILE',rt.KarelRuntimeError)]:
            p,ctx,_=program('ATTACH HOLD '+ending)
            with self.subTest(ending=ending),self.assertRaises(error):p.run(max_steps=40)
            if ending=='PAUSE':p.stop()
            self.assertEqual(ctx.group_locks.owners,{})
            self.assertEqual(ctx.group_locks.held,{1})

    def test_released_task_cannot_control_a_group_reacquired_by_another_task(self):
        p,ctx,_=program('ATTACH RELEASE PAUSE UNHOLD GROUP[1]')
        with self.assertRaises(rt.KarelPause):p.run()
        foreign,_,_=program('',ctx=ctx,setup='');ctx.group_locks._grant(1,foreign._state);ctx.group_locks.held.add(1)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'another task'):p.resume()
        self.assertIs(ctx.group_locks.owners[1],foreign._state)
        self.assertEqual(ctx.group_locks.held,{1})
        ctx.group_locks.release_owner(foreign._state)


class MotionSettingTests(unittest.TestCase):
    def test_six_settings_are_detached_without_changing_source_values(self):
        values,ctx,_,result=execute('''ATTACH
WITH $SPEED=250, $ROTSPEED=40, $MOTYPE=LINEAR,
     $UFRAME=p, $UTOOL=q, $USE_CONFIG=FALSE
MOVE TO p
p.x=999 q.x=888
MOVE AWAY 1''')
        rows=ctx.motion.history[1]['data']['settings']
        self.assertEqual([r['name'] for r in rows],['$SPEED','$ROTSPEED','$MOTYPE','$UFRAME','$UTOOL','$USE_CONFIG'])
        self.assertEqual([rows[i]['value'] for i in (0,1,2,5)],[250.,40.,'LINEAR',False])
        self.assertEqual(rows[3]['value']['value']['X'],10.)
        self.assertEqual(rows[4]['value']['value']['X'],40.)
        self.assertEqual(values['P']['X'],999.)
        self.assertNotIn('settings',ctx.motion.history[2]['data'])
        self.assertEqual(len(result.report['motion_requests'][1]['settings']),6)
        self.assertEqual([r['line'] for r in result.report['motion_requests'][1]['settings']],[7,7,7,8,8,8])

    def test_group_and_setting_expressions_precede_move_operands_once(self):
        routines='''ROUTINE group_id:INTEGER BEGIN n=n*10+1 RETURN 1 END group_id
ROUTINE speed_value:REAL BEGIN n=n*10+2 RETURN 25.0 END speed_value
ROUTINE target:XYZWPR BEGIN n=n*10+3 RETURN p END target'''
        values,ctx,_,_=execute('n=0 ATTACH WITH $SPEED[group_id()]=speed_value() MOVE TO target()',routines=routines)
        self.assertEqual(values['N'],123)
        self.assertEqual(ctx.motion.history[-1]['data']['settings'],[dict(name='$SPEED',group=1,value=25.)])

    def test_setting_frame_is_captured_before_later_setting_call_mutates_it(self):
        routines='ROUTINE speed:REAL BEGIN p.x=999 RETURN 25.0 END speed'
        _,ctx,_,_=execute('ATTACH WITH $UFRAME=p, $SPEED=speed() MOVE TO p',routines=routines)
        self.assertEqual(ctx.motion.history[-1]['data']['settings'][0]['value']['value']['X'],10.)
        self.assertEqual(ctx.motion.history[-1]['data']['target']['value']['X'],999.)

    def test_dynamic_motion_type_integer_and_contextual_constants(self):
        for expression,expected in [('JOINT','JOINT'),('LINEAR','LINEAR'),('JOINT+1','LINEAR'),('n','LINEAR')]:
            with self.subTest(expression=expression):
                _,ctx,_,_=execute('n=7 ATTACH WITH $MOTYPE='+expression+' MOVE TO p')
                self.assertEqual(ctx.motion.history[-1]['data']['settings'][0]['value'],expected)
        p,_=compile_program('linear=9',decl='linear:INTEGER')
        self.assertEqual(p.run(),{'LINEAR':9})

    def test_explicit_circular_requires_to_and_via(self):
        _,ctx,_,_=execute('ATTACH WITH $MOTYPE=CIRCULAR MOVE TO p VIA q')
        self.assertEqual(ctx.motion.history[-1]['data']['settings'][0]['value'],'CIRCULAR')
        for body in ('WITH $MOTYPE=CIRCULAR MOVE TO p','WITH $MOTYPE=CIRCULAR MOVE AWAY 1',
                     'WITH $MOTYPE=LINEAR MOVE TO p VIA q'):
            p,ctx,_=program('ATTACH '+body)
            with self.subTest(body=body),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(len(ctx.motion.history),1)

    def test_invalid_settings_do_not_consume_script_or_publish_move(self):
        for setting_text in ('$SPEED=-1','$ROTSPEED=-1','$MOTYPE=9','$SPEED[2]=1',
                             '$SPEED=1,$SPEED=2','$SPEED=1,$SPEED[1]=2'):
            ctx=context(capture_only=False,responses=[dict(operation='MOVE TO',completed=True)])
            p,_,_=program('ATTACH WITH '+setting_text+' MOVE TO p',ctx=ctx)
            with self.subTest(setting_text=setting_text),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(len(ctx.motion.responses),1)
            self.assertEqual(len(ctx.motion.history),1)

    def test_zero_and_finite_pythonic_speed_above_native_range_are_metadata(self):
        _,ctx,_,_=execute('ATTACH WITH $SPEED=0,$ROTSPEED=1.0e100 MOVE AWAY 1')
        saved=json.loads(json.dumps(ctx.to_config()))
        self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_partial_or_invalid_frame_precedes_later_effectful_expression(self):
        routines='ROUTINE later:REAL BEGIN n=99 RETURN 1.0 END later'
        p,ctx,_=program('n=0 ATTACH WITH $UFRAME=p,$SPEED=later() MOVE AWAY 1',setup='',routines=routines)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],0)
        self.assertEqual(len(ctx.motion.history),1)

    def test_frame_representation_retains_explicit_external_axes(self):
        _,ctx,_,_=execute('extended=p extended.ext1=5 ATTACH WITH $UTOOL=extended MOVE AWAY 1',
            decl='p,q:XYZWPR c:CONFIG v:VECTOR extended:XYZWPREXT s,n:INTEGER')
        self.assertEqual(ctx.motion.history[-1]['data']['settings'][0]['value']['value']['EXT1'],5.)

    def test_report_uses_physical_include_map_for_with_settings(self):
        result=translate("PROGRAM INCLUDED\n%INCLUDE move_part\nEND INCLUDED",includes={'move_part':"BEGIN\nWITH $SPEED=20 MOVE AWAY 1\n"})
        self.assertEqual(result.report['motion_requests'][0]['settings'][0]['name'],'$SPEED')
        self.assertTrue(result.report['source_map'])

    def test_settings_supported_for_all_seven_basic_forms(self):
        setup='APPEND_NODE(route,s) route[1].node_pos=p '
        bodies=['MOVE TO p','MOVE NEAR p BY 1','MOVE AWAY 1','MOVE ABOUT v BY 2',
                'MOVE AXIS 1 BY 2','MOVE RELATIVE v','MOVE ALONG route']
        for body in bodies:
            with self.subTest(body=body):
                _,ctx,_,_=execute(setup+'ATTACH WITH $SPEED=25 '+body)
                self.assertEqual(ctx.motion.history[-1]['data']['settings'],[dict(name='$SPEED',group=1,value=25.)])

    def test_context_robot_is_not_required_or_inferred_by_with(self):
        ctx=context();self.assertIsNone(ctx.robot)
        execute('ATTACH WITH $UFRAME=p,$UTOOL=q MOVE TO p',ctx=ctx)
        self.assertIsNone(ctx.robot)

    def test_with_calls_keep_active_for_counter_protection(self):
        routines='ROUTINE change:REAL BEGIN n=8 RETURN 25.0 END change'
        with self.assertRaisesRegex(TranslationError,'E_FOR_COUNTER'):
            program('ATTACH FOR n=1 TO 2 DO WITH $SPEED=change() MOVE AWAY 1 ENDFOR',routines=routines)


class MotionControlPersistenceTests(unittest.TestCase):
    def test_orthogonal_held_config_and_control_history_roundtrip(self):
        ctx=banks(motion={1:'executing',2:'stopped'})
        execute('LOCK_GROUP(7,s) HOLD GROUP[1,2] CANCEL GROUP[1,2]',ctx=ctx)
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved)
        self.assertEqual(restored.group_locks.held,{1,2})
        saved['group_locks']['held'].append(3)
        saved['motion']['history'][0]['data']['states'][0]['after']['held']=False
        self.assertEqual(restored.group_locks.held,{1,2})
        self.assertTrue(restored.motion.history[0]['data']['states'][0]['after']['held'])

    def test_old_empty_hold_configuration_remains_byte_contract_compatible(self):
        self.assertEqual(rt.GroupLocks([1]).to_config(),dict(groups=[1],motion={}))
        self.assertNotIn('held',rt.GroupLocks([1]).snapshot())

    def test_held_configuration_rejects_unknown_duplicate_and_boolean_ids(self):
        for held in ('1',[True],[0],[2],[1,1],{}):
            with self.subTest(held=held),self.assertRaises(ValueError):rt.GroupLocks.from_config(dict(groups=[1],held=held))

    def test_tampered_transition_and_state_metadata_are_rejected(self):
        _,ctx,_,_=execute('ATTACH HOLD')
        original=ctx.motion.to_config()
        for field,value in [('after',dict(motion='idle',held=False)),('before',dict(motion='stopped',held='yes')),
                            ('group',True),('extra',1)]:
            data=deepcopy(original);data['history'][-1]['data']['states'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)
        data=deepcopy(original);data['history'][-1]['data']['states']=[]
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_setting_history_rejects_unknown_fields_types_and_group_mismatch(self):
        _,ctx,_,_=execute('ATTACH WITH $SPEED=25 MOVE AWAY 1')
        original=ctx.motion.to_config()
        for row in [dict(name='$SPEED',group=True,value=25.),dict(name='$SPEED',group=2,value=25.),
                    dict(name='$SPEED',group=1,value=float('nan')),dict(name='$USE_CONFIG',group=1,value=1),
                    dict(name='$MOTYPE',group=1,value=7),dict(name='$UNKNOWN',group=1,value=1),
                    dict(name='$UTOOL',group=1,value={}),dict(name='$SPEED',group=1,value=25.,extra=1)]:
            data=deepcopy(original);data['history'][-1]['data']['settings']=[row]
            with self.subTest(row=row),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_duplicate_or_empty_setting_history_is_rejected(self):
        _,ctx,_,_=execute('ATTACH WITH $SPEED=25 MOVE AWAY 1')
        original=ctx.motion.to_config()
        row=original['history'][-1]['data']['settings'][0]
        for settings in ([],[row,row]):
            data=deepcopy(original);data['history'][-1]['data']['settings']=settings
            with self.subTest(settings=settings),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)


class MotionControlExclusions(unittest.TestCase):
    def test_invalid_control_qualifiers_and_settings_fail_translation(self):
        for body in ('CANCEL FILE route','HOLD PROGRAM[1]','UNHOLD GROUP[]','CANCEL GROUP[TRUE]',
                     'WITH $SCAN_TIME=1 MOVE AWAY 1','WITH $SPEED_EXTRA=1 MOVE AWAY 1',
                     'WITH $SPEED=TRUE MOVE AWAY 1','WITH $USE_CONFIG=1 MOVE AWAY 1',
                     'WITH $UFRAME=v MOVE AWAY 1','WITH $UTOOL=j MOVE AWAY 1',
                     'WITH $MOTYPE=6.0 MOVE AWAY 1','WITH $SPEED=1 OPEN HAND 1',
                     'WITH $SPEED=1 MOVE AWAY 1 NOWAIT, WHEN TRUE DO CANCEL ENDMOVE',
                     'CONDITION[1]: WHEN TRUE DO WITH $SPEED=1 MOVE AWAY 1 ENDCONDITION',
                     'n=$SPEED','$SPEED=25'):
            with self.subTest(body=body),self.assertRaises(TranslationError):program(body)

    def test_more_than_31_control_groups_or_nine_settings_is_rejected(self):
        for body in ('HOLD GROUP['+','.join('1' for _ in range(32))+']',
                     'WITH '+','.join('$SPEED=1' for _ in range(10))+' MOVE AWAY 1'):
            with self.subTest(body=body),self.assertRaises(TranslationError):program(body)


if __name__ == '__main__':
    unittest.main()
