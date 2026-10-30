"""Authored offline request contracts, independent values and lifecycle checks."""
from copy import deepcopy
import json
import unittest

from karel2py import runtime as rt, translate, translate_project
from karel2py.lexer import TranslationError, tokenize
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source


DECL = 'p,q:XYZWPR c:CONFIG v:VECTOR j:JOINTPOS2 a:ARRAY[2] OF REAL s,n:INTEGER route:PATH'
SETUP = "CNV_STR_CONF('N',c,s) p=POS(10,20,30,0,0,0,c) q=POS(40,50,60,0,0,0,c) v=VEC(1,2,3) "


def context(*, capture_only=True, responses=None, groups=None, **kwargs):
    groups = groups or {1:2}
    return rt.ExecutionContext(motion=rt.MotionRequests(groups, hands={1:'relaxed',2:'open'},
        capture_only=capture_only, responses=responses, **kwargs), group_locks=rt.GroupLocks(list(groups)))


def program(body, *, ctx=None, setup=SETUP, prefix='', decl=DECL, routines='', **kwargs):
    ctx = ctx or context()
    p, result = compile_program(setup + body, decl=decl, prefix=prefix,
        routines=routines, context=ctx, sleep=lambda _:None, joint_axes=2, **kwargs)
    return p, ctx, result


def execute(body, **kwargs):
    p, ctx, result = program(body, **kwargs)
    values = p.run()
    return values, ctx, p, result


class MotionSourceTests(unittest.TestCase):
    def test_seven_forms_and_via_capture_detached_data(self):
        _, ctx, p, result = execute('''ATTACH
MOVE TO p VIA q NOWAIT
MOVE NEAR p BY 12
MOVE AWAY -3
MOVE ABOUT v BY 45
MOVE AXIS 2 BY 90
MOVE RELATIVE v
APPEND_NODE(route,s) route[1].node_pos=p
APPEND_NODE(route,s) route[2].node_pos=q
MOVE ALONG route[1..2]
p.x=999 q.x=888 v.x=777 route[1].node_pos=p
''')
        rows = ctx.motion.history
        self.assertEqual([r['operation'] for r in rows], ['ATTACH','MOVE TO','MOVE NEAR','MOVE AWAY','MOVE ABOUT','MOVE AXIS','MOVE RELATIVE','MOVE ALONG'])
        self.assertEqual([r['outcome'] for r in rows], ['completed'] + ['captured']*7)
        self.assertTrue(rows[1]['nowait'])
        self.assertEqual(rows[1]['data']['target']['value']['X'], 10.)
        self.assertEqual(rows[1]['data']['via']['value']['X'], 40.)
        self.assertEqual(rows[2]['data']['distance'],12.)
        self.assertEqual(rows[3]['data'], {'distance':-3.})
        self.assertEqual(rows[4]['data']['vector']['value'],dict(X=1.,Y=2.,Z=3.))
        self.assertEqual(rows[4]['data']['angle'],45.)
        self.assertEqual(rows[5]['data'],dict(axis=2,distance=90.))
        self.assertEqual(rows[7]['data']['nodes'][0]['value']['LOCATION']['X'],10.)
        self.assertEqual((rows[7]['data']['start'],rows[7]['data']['end']),(1,2))
        self.assertEqual(ctx.group_locks.owners,{})
        self.assertEqual(len(result.report['motion_requests']),8)
        self.assertFalse(result.report['motion_request_policy']['controller_validated'])
        self.assertEqual(p._state.local_frames,[])

    def test_joint_destination_preserves_exact_axes(self):
        _,ctx,_,_=execute('ATTACH a[1]=5 a[2]=8 CNV_REL_JPOS(a,j,s) MOVE TO j')
        self.assertEqual(ctx.motion.history[-1]['data']['target'],{'type':['JOINTPOS',2],'value':{'axes':[5.,8.]}})

    def test_cartesian_relative_pose_is_a_request_without_feedback_changes(self):
        ctx=context();ctx.robot=rt.RobotContext()
        before=ctx.robot.to_config()
        execute('ATTACH MOVE RELATIVE p',ctx=ctx)
        self.assertEqual(ctx.robot.to_config(),before)
        self.assertEqual(ctx.motion.history[-1]['data']['offset']['type'],['XYZWPR'])

    def test_capture_only_is_explicit_and_missing_reply_preserves_script_and_history(self):
        ctx=context(capture_only=False)
        p,_,_=program('ATTACH MOVE TO p',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'matching completion'):p.run()
        self.assertEqual([r['operation'] for r in ctx.motion.history],['ATTACH'])
        self.assertEqual(ctx.motion.sequence,1)
        self.assertEqual(ctx.group_locks.owners,{})

    def test_scripted_zero_duration_reply_and_nowait_metadata(self):
        ctx=context(capture_only=False,responses=[dict(operation='MOVE TO',completed=True),dict(operation='MOVE AWAY',completed=True)])
        execute('ATTACH MOVE TO p NOWAIT MOVE AWAY 8',ctx=ctx)
        self.assertEqual([r['outcome'] for r in ctx.motion.history],['completed']*3)
        self.assertEqual(ctx.motion.responses,[])
        self.assertTrue(ctx.motion.history[1]['nowait'])

    def test_scripted_failure_consumes_one_reply_and_retains_evidence(self):
        replies=[dict(operation='MOVE TO',completed=False),dict(operation='MOVE AWAY',completed=True)]
        ctx=context(capture_only=False,responses=replies)
        p,_,_=program('ATTACH MOVE TO p n=99',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'completion rejected'):p.run()
        self.assertEqual(ctx.motion.responses,replies[1:])
        self.assertEqual(ctx.motion.history[-1]['outcome'],'rejected')
        self.assertIs(p._state.values['N'],rt.UNINITIALIZED)
        self.assertEqual(ctx.group_locks.owners,{})

    def test_wrong_reply_not_consumed(self):
        replies=[dict(operation='MOVE AWAY',completed=True)]
        ctx=context(capture_only=False,responses=replies)
        p,_,_=program('ATTACH MOVE TO p',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'matching completion'):p.run()
        self.assertEqual(ctx.motion.responses,replies)
        self.assertEqual(len(ctx.motion.history),1)

    def test_group_directive_and_declaration_select_same_explicit_bank(self):
        ctx=context(groups={3:2})
        execute('ATTACH MOVE TO p',ctx=ctx,prefix='%DEFGROUP=3\n%LOCKGROUP=3')
        self.assertEqual([r['group'] for r in ctx.motion.history],[3,3])
        self.assertEqual(ctx.motion.history[0]['data'],{'groups':[3]})

    def test_explicit_lock_is_sufficient_without_attach(self):
        _,ctx,_,_=execute('LOCK_GROUP(1,s) MOVE TO p')
        self.assertEqual(ctx.motion.history[0]['operation'],'MOVE TO')

    def test_opted_in_root_directive_acquisition(self):
        ctx=context();ctx.group_locks=rt.GroupLocks([1],apply_directives=True)
        execute('MOVE TO p',ctx=ctx)
        self.assertEqual(len(ctx.motion.history),1)
        self.assertEqual(ctx.group_locks.owners,{})

    def test_missing_service_fails_at_source_line(self):
        p,_,_=program('ATTACH',ctx=rt.ExecutionContext())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'motion') as error:p.run()
        self.assertIsInstance(error.exception.line,int)

    def test_missing_group_locks_is_not_implicitly_constructed(self):
        ctx=context();ctx.group_locks=None;p,_,_=program('ATTACH',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'group_locks'):p.run()
        self.assertEqual(ctx.motion.history,[])

    def test_unowned_or_busy_motion_preserves_data(self):
        for body,label in [('MOVE TO p',None),('ATTACH MOVE TO p','executing')]:
            ctx=context();p,_,_=program(body,ctx=ctx)
            if label:ctx.group_locks.set_motion(1,label)
            with self.subTest(body=body),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(ctx.motion.history,[])
            self.assertEqual(ctx.group_locks.motion,{1:label} if label else {})

    def test_bad_or_partial_values_and_axis_preserve_script(self):
        for setup,call in [('', 'MOVE TO p'),(SETUP+'p.x=1.0e308*2 ', 'MOVE TO p'),
                           (SETUP,'MOVE AXIS 3 BY 1'),(SETUP,'OPEN HAND 3')]:
            ctx=context(capture_only=False,responses=[dict(operation='MOVE TO',completed=True)])
            p,_,_=program('ATTACH '+call,ctx=ctx,setup=setup)
            with self.subTest(call=call),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(len(ctx.motion.responses),1)
            self.assertNotIn('MOVE TO',[r['operation'] for r in ctx.motion.history])

    def test_group_joint_width_mismatch_does_not_convert(self):
        ctx=context(groups={1:3});p,_,_=program('ATTACH a[1]=1 a[2]=2 CNV_REL_JPOS(a,j,s) MOVE TO j',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'joint width'):p.run()
        self.assertEqual(len(ctx.motion.history),1)

    def test_argument_capture_precedes_later_operand_side_effects(self):
        routines='''ROUTINE distance:REAL
BEGIN
n=n+1 p.x=999
RETURN 12.0
END distance'''
        values,ctx,_,_=execute('n=0 ATTACH MOVE NEAR p BY distance()',routines=routines)
        self.assertEqual(values['N'],1)
        self.assertEqual(ctx.motion.history[-1]['data']['target']['value']['X'],10.)

    def test_hand_state_and_global_handler_action(self):
        values,ctx,_,_=execute('''n=0 ATTACH
CONDITION[1]: WHEN n=1 DO CLOSE HAND 1 ENDCONDITION
ENABLE CONDITION[1]
OPEN HAND 1 n=1 DELAY 0 RELAX HAND 2''')
        self.assertEqual(ctx.motion.hands,{1:'closed',2:'relaxed'})
        self.assertEqual([r['operation'] for r in ctx.motion.history],['ATTACH','OPEN HAND','CLOSE HAND','RELAX HAND'])
        self.assertEqual(values['N'],1)

    def test_release_reattach_retains_original_groups_and_no_lock_leaks(self):
        _,ctx,_,_=execute('ATTACH RELEASE RELEASE ATTACH MOVE TO p')
        self.assertEqual([r['data']['groups'] for r in ctx.motion.history[:4]],[[1],[1],[],[1]])
        self.assertEqual(ctx.motion._released,{})
        self.assertEqual(ctx.group_locks.owners,{})

    def test_move_after_release_fails_until_attach(self):
        ctx=context();p,_,_=program('ATTACH RELEASE MOVE TO p',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'attached logical'):p.run()
        self.assertEqual(ctx.motion._released,{})
        self.assertEqual(ctx.group_locks.owners,{})

    def test_attach_conflict_is_atomic_across_groups(self):
        ctx=context(groups={1:2,2:2});other,_,_=program('',ctx=ctx,setup='')
        ctx.group_locks._grant(2,other._state)
        p,_,_=program('ATTACH',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'another task'):p.run()
        self.assertEqual(ctx.group_locks.owners,{2:other._state})
        self.assertEqual(ctx.motion.history,[])
        ctx.group_locks.release_owner(other._state)

    def test_release_busy_is_atomic(self):
        ctx=context(groups={1:2,2:2});p,_,_=program('ATTACH PAUSE RELEASE',ctx=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        ctx.group_locks.set_motion(2,'stopped')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'idle logical'):p.resume()
        self.assertEqual([r['operation'] for r in ctx.motion.history],['ATTACH'])
        self.assertEqual(ctx.motion._released,{})

    def test_pause_released_save_guard_then_stop_cleanup(self):
        p,ctx,_=program('ATTACH RELEASE PAUSE')
        with self.assertRaises(rt.KarelPause):p.run()
        with self.assertRaisesRegex(ValueError,'reattach'):ctx.to_config()
        p.stop()
        self.assertEqual(ctx.motion._released,{})
        self.assertEqual(ctx.group_locks.owners,{})
        rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))

    def test_abort_and_budget_failure_clear_released_bindings(self):
        for body,limit,error in [('ATTACH RELEASE ABORT',1000,rt.KarelAbort),
                                 ('ATTACH RELEASE WHILE TRUE DO n=1 ENDWHILE',40,rt.KarelRuntimeError)]:
            p,ctx,_=program(body)
            with self.subTest(body=body),self.assertRaises(error):p.run(max_steps=limit)
            self.assertEqual(ctx.motion._released,{})
            self.assertEqual(ctx.group_locks.owners,{})

    def test_ring_and_sequence_exhaustion_preserve_hand_state(self):
        _,ctx,_,_=execute('ATTACH OPEN HAND 1 CLOSE HAND 1 RELAX HAND 1',ctx=context(limit=2))
        self.assertEqual([r['sequence'] for r in ctx.motion.history],[3,4])
        ctx=context(sequence=2147483645);p,_,_=program('ATTACH OPEN HAND 1',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'sequence exhausted'):p.run()
        self.assertEqual(ctx.motion.hands[1],'relaxed')
        self.assertEqual(ctx.motion.sequence,2147483646)

    def test_attached_program_uses_calling_root_and_does_not_release_it(self):
        ctx=context()
        main=source('MAIN',"ATTACH CALL_PROG('WORKER',entry) MOVE AWAY 2",decl='entry:INTEGER')
        worker=source('WORKER','OPEN HAND 1 MOVE AXIS 2 BY 3')
        project=translate_project({'main':main,'worker':worker}).instantiate(context=ctx)
        project.run('MAIN')
        self.assertEqual([r['program'] for r in ctx.motion.history],['MAIN']*4)
        self.assertEqual([r['source_program'] for r in ctx.motion.history],['MAIN','WORKER','WORKER','MAIN'])
        self.assertEqual(ctx.group_locks.owners,{})

    def test_linked_routine_retains_root_and_module_identity(self):
        ctx=context()
        main=source('MAIN','ATTACH move_axis()',routines='ROUTINE move_axis FROM LIB')
        library=source('LIB','',routines='ROUTINE move_axis BEGIN MOVE AXIS 2 BY 3 END move_axis')
        translate_project({'main':main,'lib':library}).instantiate(context=ctx).run('MAIN')
        self.assertEqual((ctx.motion.history[-1]['program'],ctx.motion.history[-1]['source_program']),('MAIN','LIB'))

    def test_existing_attach_identifier_still_works(self):
        p,_=compile_program('attach=TRUE',decl='attach:BOOLEAN')
        self.assertEqual(p.run(),{'ATTACH':True})


class MotionPathTests(unittest.TestCase):
    def test_selected_node_quota_is_enforced_before_response_consumption(self):
        ctx=context(capture_only=False,responses=[dict(operation='MOVE ALONG',completed=True)])
        setup=SETUP+'FOR n=1 TO 257 DO APPEND_NODE(route,s) route[n].node_pos=p ENDFOR '
        p,_,_=program('ATTACH MOVE ALONG route',setup=setup,ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'256 selected'):p.run()
        self.assertEqual(len(ctx.motion.responses),1)
        self.assertEqual(len(ctx.motion.history),1)

    def test_whole_request_byte_quota_is_independent_of_node_quota(self):
        setup=SETUP+'FOR n=1 TO 256 DO APPEND_NODE(route,s) route[n].node_pos=p ENDFOR '
        p,ctx,_=program('ATTACH MOVE ALONG route',setup=setup)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'64 KiB'):p.run()
        self.assertEqual(len(ctx.motion.history),1)

    def test_authored_node_metadata_is_not_treated_as_motion_data(self):
        result=translate('''PROGRAM NODE_REQUEST
TYPE node_t=STRUCTURE node_pos:XYZWPR metadata:INTEGER ENDSTRUCTURE
VAR route:PATH NODEDATA=node_t p:XYZWPR c:CONFIG s:INTEGER
BEGIN
CNV_STR_CONF('N',c,s) p=POS(1,2,3,0,0,0,c)
APPEND_NODE(route,s) route[1].node_pos=p
ATTACH MOVE TO route[1] MOVE ALONG route
END NODE_REQUEST''')
        namespace={'__name__':'test_node_request'};exec(result.python_source,namespace)
        ctx=context();namespace['Program'](context=ctx).run()
        self.assertEqual(ctx.motion.history[-1]['data']['nodes'][0]['value']['X'],1.)
        self.assertNotIn('METADATA',ctx.motion.history[-1]['data']['nodes'][0]['value'])

    def test_node_without_positional_node_pos_is_rejected(self):
        result=translate('''PROGRAM NO_NODE_POSITION
TYPE node_t=STRUCTURE value:INTEGER ENDSTRUCTURE
VAR route:PATH NODEDATA=node_t s:INTEGER
BEGIN APPEND_NODE(route,s) ATTACH MOVE ALONG route END NO_NODE_POSITION''')
        namespace={'__name__':'test_bad_node'};exec(result.python_source,namespace)
        ctx=context()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'NODE_POS'):namespace['Program'](context=ctx).run()
        self.assertEqual(len(ctx.motion.history),1)

    def test_move_to_path_node_extracts_only_positional_data(self):
        _,ctx,_,_=execute('ATTACH MOVE TO route[1]',setup=SETUP+'APPEND_NODE(route,s) route[1].node_pos=p ')
        self.assertEqual(ctx.motion.history[-1]['data']['target']['type'],['POSITION'])
        self.assertEqual(ctx.motion.history[-1]['data']['target']['value']['LOCATION']['X'],10.)

    def test_full_path_and_start_only_ranges(self):
        setup=SETUP+'APPEND_NODE(route,s) route[1].node_pos=p APPEND_NODE(route,s) route[2].node_pos=q '
        for selection,expected in [('route',(1,2)),('route[2]',(2,2)),('route[1..1]',(1,1))]:
            with self.subTest(selection=selection):
                _,ctx,_,_=execute('ATTACH MOVE ALONG '+selection,setup=setup)
                row=ctx.motion.history[-1]['data']
                self.assertEqual((row['start'],row['end']),expected)
                self.assertEqual(len(row['nodes']),expected[1]-expected[0]+1)

    def test_outside_selected_range_can_be_partial(self):
        _,ctx,_,_=execute('ATTACH MOVE ALONG route[2]',setup=SETUP+'APPEND_NODE(route,s) APPEND_NODE(route,s) route[2].node_pos=q ')
        self.assertEqual(ctx.motion.history[-1]['data']['nodes'][0]['value']['LOCATION']['X'],40.)

    def test_range_bounds_empty_or_partial_nodes_fail_without_request(self):
        setup=SETUP+'APPEND_NODE(route,s) '
        for selection in ('route[0]','route[2]','route[1..0]','route','route[1..2]'):
            p,ctx,_=program('ATTACH MOVE ALONG '+selection,setup=setup)
            with self.subTest(selection=selection),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(len(ctx.motion.history),1)

    def test_path_bounds_are_evaluated_once_in_order(self):
        routines='''ROUTINE next_index:INTEGER
BEGIN n=n+1 RETURN n END next_index'''
        setup=SETUP+'APPEND_NODE(route,s) route[1].node_pos=p APPEND_NODE(route,s) route[2].node_pos=q n=0 '
        values,ctx,_,_=execute('ATTACH MOVE ALONG route[next_index()..next_index()]',setup=setup,routines=routines)
        self.assertEqual(values['N'],2)
        self.assertEqual((ctx.motion.history[-1]['data']['start'],ctx.motion.history[-1]['data']['end']),(1,2))

    def test_range_token_does_not_change_real_literals(self):
        tokens=[(t.kind,t.value) for t in tokenize('1..2 1. .2 1.2 1.e2','range') if t.kind!='EOF']
        self.assertEqual(tokens,[('INT','1'),('OP','..'),('INT','2'),('REAL','1.'),('REAL','.2'),('REAL','1.2'),('REAL','1.e2')])


class MotionConfigTests(unittest.TestCase):
    def test_underscored_source_program_identity_roundtrips(self):
        result=translate('PROGRAM _REQUEST_DEMO BEGIN ATTACH MOVE AWAY 1 END _REQUEST_DEMO')
        namespace={'__name__':'underscored'};exec(result.python_source,namespace)
        ctx=context();namespace['Program'](context=ctx).run()
        self.assertEqual(rt.MotionRequests.from_config(ctx.motion.to_config()).to_config(),ctx.motion.to_config())

    def test_history_unknown_fields_and_nonfinite_data_fail(self):
        _,ctx,_,_=execute('ATTACH MOVE AWAY 1')
        original=ctx.motion.to_config()
        for field,value in [('distance',float('inf')),('distance',True),('unknown',1)]:
            data=deepcopy(original);data['history'][-1]['data'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_configuration_copies_response_and_hand_inputs(self):
        hands={1:'open'};responses=[dict(operation='MOVE TO',completed=True)]
        bank=rt.MotionRequests({1:2},hands=hands,responses=responses)
        hands[1]='closed';responses[0]['completed']=False
        self.assertEqual(bank.hands,{1:'open'})
        self.assertTrue(bank.responses[0]['completed'])

    def test_finite_pythonic_distance_exceeding_binary32_roundtrips(self):
        _,ctx,_,_=execute('ATTACH MOVE AWAY 1.0e100')
        data=json.loads(json.dumps(ctx.to_config()))
        self.assertEqual(rt.ExecutionContext.from_config(data).to_config(),data)

    def test_complete_json_roundtrip_and_no_aliases(self):
        _,ctx,_,_=execute('ATTACH MOVE TO p OPEN HAND 1 RELEASE ATTACH')
        data=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(data)
        self.assertEqual(restored.to_config(),data)
        data['motion']['history'][1]['data']['target']['value']['X']=555
        data['motion']['hands']['1']='closed'
        self.assertEqual(restored.motion.history[1]['data']['target']['value']['X'],10.)
        self.assertEqual(restored.motion.hands[1],'open')

    def test_malformed_service_configuration_is_rejected(self):
        cases=[{'groups':{}},{'groups':{'01':2}},{'groups':{'32':2}},{'groups':{'1':True}},
            {'groups':{'1':10}},{'groups':{'1':2},'capture_only':1},{'groups':{'1':2},'hands':{'1':'bad'}},
            {'groups':{'1':2},'hands':{'3':'open'}},{'groups':{'1':2},'limit':129},
            {'groups':{'1':2},'responses':[{'operation':'MOVE TO','completed':1}]},
            {'groups':{'1':2},'capture_only':True,'responses':[{'operation':'MOVE TO','completed':True}]},
            {'groups':{'1':2},'native':True}]
        for data in cases:
            with self.subTest(data=data),self.assertRaises(ValueError):rt.ExecutionContext.from_config({'motion':data})

    def test_tampered_history_fails_before_rehydration(self):
        _,ctx,_,_=execute('ATTACH MOVE TO p')
        original=ctx.motion.to_config()
        changes=[('sequence',0),('program','bad/path'),('source_program',''),('line',0),
            ('nowait',1),('outcome','pending'),('group',True),('operation','SYSTEM')]
        for key,value in changes:
            data=deepcopy(original);data['history'][1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)
        for payload in ({'type':['XYZWPR',1],'value':{}},{'type':['XYZWPR'],'value':{}},
                        {'type':['JOINTPOS',9],'value':{'joints':[0.]*9}}):
            data=deepcopy(original);data['history'][1]['data']['target']=payload
            with self.subTest(payload=payload),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_context_service_type_is_checked(self):
        with self.assertRaises(TypeError):rt.ExecutionContext(motion={})


class MotionExclusionTests(unittest.TestCase):
    def test_unsupported_clauses_and_types_fail_translation(self):
        for body in ('MOVE TO p NOWAIT, WHEN TRUE DO CANCEL ENDMOVE','WITH n=1 MOVE TO p',
            'MOVE AWAY 1 VIA p','MOVE TO p WHEN TRUE DO CANCEL','MOVE TO p UNTIL TRUE',
            'MOVE TO v','MOVE ABOUT p BY 2','MOVE NEAR j BY 2','MOVE RELATIVE j',
            'MOVE ALONG route[1,2]','MOVE AXIS TRUE BY 1','MOVE SOMETHING p','CANCEL FILE route',
            'HOLD PROGRAM[1]','UNHOLD GROUP[*]','CONDITION[1]: WHEN TRUE DO ATTACH ENDCONDITION',
            'CONDITION[1]: WHEN TRUE DO MOVE TO p ENDCONDITION'):
            with self.subTest(body=body),self.assertRaises(TranslationError):program(body)

    def test_strict_remains_future(self):
        with self.assertRaisesRegex(TranslationError,'E_MODE'):translate('PROGRAM T BEGIN ATTACH END T',mode='strict')


if __name__ == '__main__':
    unittest.main()
