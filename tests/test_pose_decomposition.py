"""Authored Pythonic UNPOS values, source capture and forward-model coverage."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.kinematics import pose as identity_pose
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program,run
from tests.test_joint_interoperability import joint,model_context
from tests.test_kinematic_assignments import callback_context
from tests.test_project_scheduler import source
from tests.test_unpos import runtime_fixture


DECL='pose: XYZWPR point: POSITION e: XYZWPREXT j: JOINTPOS cfg,result_cfg: CONFIG x,y,z,w,p,r: REAL s,n: INTEGER values: ARRAY[6] OF REAL'
START="CNV_STR_CONF('F L U T,1,2,3',cfg,s) pose=POS(1,2,3,10,20,30,cfg) "
FIELDS=('X','Y','Z','W','P','R')


def call(value='pose',outputs='x,y,z,w,p,r,result_cfg'): return f'UNPOS({value},{outputs})'


def components(snapshot): return [snapshot[name] for name in FIELDS]


class PoseDecompositionValueTests(unittest.TestCase):
    def test_xyz_storage_keeps_supplied_angles(self):
        state=run(START+'pose.w=360 pose.r=-270 '+call(),decl=DECL)
        self.assertEqual(components(state),[1.,2.,3.,360.,20.,-270.])
        self.assertEqual(state['RESULT_CFG'],state['CFG'])

    def test_grouped_pose(self):
        self.assertEqual(components(run(START+call('((pose))'),decl=DECL)),[1.,2.,3.,10.,20.,30.])

    def test_constructor_result(self):
        state=run(START+call('POS(4,5,6,40,50,60,cfg)'),decl=DECL)
        self.assertEqual(components(state),[4.,5.,6.,40.,50.,60.])

    def test_extended_pose_validates_and_omits_external_axes(self):
        state=run(START+'e=pose e.ext1=25 e.ext2=-50 e.ext3=10 '+call('e'),decl=DECL)
        self.assertEqual(components(state),[state['E'][name] for name in FIELDS])
        self.assertEqual([state['E'][name] for name in ('EXT1','EXT2','EXT3')],[25.,-50.,10.])

    def test_position_uses_canonical_angles(self):
        state=run(START+'point=pose '+call('point'),decl=DECL)
        for observed,expected in zip(components(state),[1.,2.,3.,10.,20.,30.]): self.assertAlmostEqual(observed,expected)
        self.assertEqual(state['RESULT_CFG'],state['CFG'])

    def test_position_gimbal_convention(self):
        state=run(START+'pose=POS(1,2,3,10,90,30,cfg) point=pose '+call('point'),decl=DECL)
        self.assertAlmostEqual(state['W'],0.);self.assertAlmostEqual(state['P'],90.);self.assertAlmostEqual(state['R'],20.)

    def test_frame_expression(self):
        state=run(START+'pose=POS(1,0,0,0,0,0,cfg) '+call('INV(pose):pose'),decl=DECL)
        self.assertEqual(components(state),[0.]*6)

    def test_each_cartesian_routine_result(self):
        for kind,value in (('XYZWPR','pose'),('POSITION','point'),('XYZWPREXT','e')):
            with self.subTest(kind=kind):
                routines=f'ROUTINE make: {kind} BEGIN n=n+1 RETURN {value} END make'
                state=run(START+'point=pose e=pose n=0 '+call('make()'),decl=DECL,routines=routines)
                self.assertEqual(state['N'],1);self.assertAlmostEqual(state['X'],1.);self.assertAlmostEqual(state['R'],30.)

    def test_bare_routine_result(self):
        state=run(START+call('make'),decl=DECL,routines='ROUTINE make: XYZWPR BEGIN RETURN pose END make')
        self.assertEqual(state['X'],1.)

    def test_array_element_and_nested_structure_source(self):
        for value,extra,prefix in (('points[1]','points: ARRAY[1] OF POSITION',''),
                                   ('box.point','box: box_t','TYPE box_t=STRUCTURE point: POSITION ENDSTRUCTURE')):
            with self.subTest(value=value):
                state=run(START+value+'=pose '+call(value),decl=DECL+' '+extra,prefix=prefix)
                self.assertAlmostEqual(state['X'],1.)

    def test_transparent_pose_alias(self):
        state=run(START+'alias=pose '+call('alias'),decl=DECL+' alias: pose_t',prefix='TYPE pose_t=XYZWPREXT')
        self.assertEqual(state['X'],1.)

    def test_current_pose_function_with_explicit_context(self):
        ctx=model_context((0.,90.));state=run(call('CURPOS(0,0)'),decl=DECL,context=ctx)
        self.assertAlmostEqual(state['X'],100.);self.assertAlmostEqual(state['Y'],100.);self.assertAlmostEqual(state['R'],90.)

    def test_current_pose_bare_function(self):
        state=run(call('CURPOS'),decl=DECL,context=model_context((0.,0.)))
        self.assertEqual(state['X'],200.)

    def test_current_joint_bare_function(self):
        state=run(call('CURJPOS'),decl=DECL,context=model_context((0.,0.)))
        self.assertEqual(state['X'],200.)

    def test_current_zero_argument_calls(self):
        for expression in ('CURPOS()','CURJPOS()'):
            with self.subTest(expression=expression): self.assertEqual(run(call(expression),decl=DECL,context=model_context((0.,0.)))['X'],200.)

    def test_bare_queries_work_outside_decomposition(self):
        program,result=compile_program('e=CURPOS j=CURJPOS',decl=DECL,context=model_context((0.,0.)))
        state=program.run();self.assertEqual((state['E']['X'],state['J']['axes']),(200.,[0.]*9))
        self.assertEqual([row['name'] for row in result.report['bare_function_calls']],['CURPOS','CURJPOS'])

    def test_bare_current_name_keeps_storage_priority(self):
        state=run(START+'CURPOS=pose '+call('CURPOS'),decl=DECL+' CURPOS: XYZWPR')
        self.assertEqual(state['X'],1.)

    def test_bare_current_name_keeps_constant_priority(self):
        state=run('n=CURPOS',decl=DECL,prefix='CONST CURPOS=7')
        self.assertEqual(state['N'],7)

    def test_bare_current_name_keeps_internal_routine_priority(self):
        program,_=compile_program(START+call('CURPOS'),decl=DECL,routines='ROUTINE CURPOS: XYZWPR BEGIN RETURN pose END CURPOS')
        self.assertEqual(program.run()['X'],1.);self.assertEqual(program.service_requests,())

    def test_partial_current_query_arguments_remain_invalid(self):
        for expression in ('CURPOS(0)','CURJPOS(0)'):
            with self.subTest(expression=expression),self.assertRaises(TranslationError) as caught: compile_program(call(expression),decl=DECL)
            self.assertEqual(caught.exception.code,'E_ARGUMENTS')

    def test_position_register_function(self):
        point=identity_pose();point.values['LOCATION'].values['X']=15.
        ctx=rt.ExecutionContext(positions=rt.PositionRegisters(1,{1:point}))
        state=run(call('GET_POS_REG(1,s)'),decl=DECL,context=ctx)
        self.assertEqual((state['X'],state['S']),(15.,0))

    def test_source_component_and_config_can_be_outputs(self):
        state=run(START+call('pose','pose.y,pose.x,z,w,p,r,pose.config_data'),decl=DECL)
        self.assertEqual((state['POSE']['X'],state['POSE']['Y']),(2.,1.))
        self.assertEqual(state['POSE']['CONFIG_DATA'],state['CFG'])

    def test_position_location_can_be_output(self):
        state=run(START+'point=pose '+call('point','point.location.y,point.location.x,z,w,p,r,point.config_data'),decl=DECL)
        self.assertEqual((state['POINT']['LOCATION']['X'],state['POINT']['LOCATION']['Y']),(2.,1.))

    def test_config_output_owns_independent_copy(self):
        state=run(START+call()+' result_cfg.cfg_flip=FALSE',decl=DECL)
        self.assertTrue(state['POSE']['CONFIG_DATA']['CFG_FLIP']);self.assertFalse(state['RESULT_CFG']['CFG_FLIP'])

    def test_existing_config_field_alias_survives_output(self):
        _,outputs,storage=runtime_fixture();alias=rt.field_reference(storage['CFG'],'CFG_TURN_NO2')
        source_value,_,_=runtime_fixture()
        with rt._numeric_scope('pythonic'): rt.unpos_value(source_value.raw(),outputs)
        self.assertEqual(alias.raw(),-1)


class PoseDecompositionOrderingTests(unittest.TestCase):
    def test_source_runs_once_before_all_selectors(self):
        routines='ROUTINE make: XYZWPR BEGIN n=n*10+1 RETURN pose END make ROUTINE pick: INTEGER BEGIN n=n*10+2 RETURN 1 END pick'
        state=run(START+'n=0 '+call('make()','values[pick()],y,z,w,p,r,result_cfg'),decl=DECL,routines=routines)
        self.assertEqual((state['N'],state['VALUES'][0]),(12,1.))

    def test_source_snapshot_precedes_later_source_mutation(self):
        routines='ROUTINE pick: INTEGER BEGIN pose.x=99 RETURN 1 END pick'
        state=run(START+call('pose','values[pick()],y,z,w,p,r,result_cfg'),decl=DECL,routines=routines)
        self.assertEqual((state['VALUES'][0],state['POSE']['X']),(1.,99.))

    def test_config_snapshot_precedes_later_config_mutation(self):
        routines='ROUTINE pick: INTEGER BEGIN pose.config_data.cfg_flip=FALSE RETURN 1 END pick'
        state=run(START+call('pose','values[pick()],y,z,w,p,r,result_cfg'),decl=DECL,routines=routines)
        self.assertTrue(state['RESULT_CFG']['CFG_FLIP']);self.assertFalse(state['POSE']['CONFIG_DATA']['CFG_FLIP'])

    def test_invalid_source_skips_output_selector(self):
        program,_=compile_program('n=0 x=99 '+call('pose','values[pick()],y,z,w,p,r,result_cfg'),decl=DECL,routines='ROUTINE pick: INTEGER BEGIN n=n+1 RETURN 1 END pick')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['N'],program.snapshot()['X']),(0,99.))

    def test_invalid_extended_leaf_is_not_ignored(self):
        program,_=compile_program(START+'n=0 '+call('e','values[pick()],y,z,w,p,r,result_cfg'),decl=DECL,routines='ROUTINE pick: INTEGER BEGIN n=n+1 RETURN 1 END pick')
        with rt._numeric_scope('pythonic'):
            program._state.values['E']=rt.convert_position(('XYZWPREXT',),identity_pose())
        program._state.values['E'].values['EXT3']=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['N'],0)

    def test_source_effect_survives_later_output_error(self):
        routines='ROUTINE make: XYZWPR BEGIN n=n+1 RETURN pose END make'
        program,_=compile_program(START+'n=0 x=99 '+call('make()','values[7],y,z,w,p,r,result_cfg'),decl=DECL,routines=routines)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['N'],program.snapshot()['X']),(1,99.))

    def test_duplicate_output_failure_retains_selector_effects(self):
        routines='ROUTINE pick: INTEGER BEGIN n=n+1 RETURN 1 END pick'
        program,_=compile_program(START+'n=0 values[1]=99 '+call('pose','values[pick()],values[pick()],z,w,p,r,result_cfg'),decl=DECL,routines=routines)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlapping'): program.run()
        self.assertEqual((program.snapshot()['N'],program.snapshot()['VALUES'][0]),(2,99.))

    def test_partial_position_fails_before_writes(self):
        program,_=compile_program('x=99 '+call('point'),decl=DECL)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['X'],99.)

    def test_nonorthogonal_position_fails_before_selectors(self):
        program,_=compile_program('n=0 '+call('point','values[pick()],y,z,w,p,r,result_cfg'),decl=DECL,routines='ROUTINE pick: INTEGER BEGIN n=n+1 RETURN 1 END pick')
        program._state.values['POINT']=identity_pose();program._state.values['POINT'].values['NORMAL'].values['X']=2.
        with self.assertRaisesRegex(rt.KarelRuntimeError,'unit columns'): program.run()
        self.assertEqual(program.snapshot()['N'],0)

    def test_malformed_output_config_fails_atomically(self):
        program,_=compile_program(START+'x=99 '+call(),decl=DECL)
        del program._state.values['RESULT_CFG'].values['CFG_FRONT']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'malformed storage'): program.run()
        self.assertEqual(program.snapshot()['X'],99.)

    def test_failed_source_function_cleans_frames(self):
        program,_=compile_program('n=0 '+call('make()'),decl=DECL,routines='ROUTINE make: XYZWPR BEGIN n=n+1 RETURN pose END make')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['N'],program._state.local_frames,program._state.call_depth),(1,[],0))


class JointDecompositionTests(unittest.TestCase):
    def test_supplied_joint_storage(self):
        state=run('j=CURJPOS(0,0) '+call('j'),decl=DECL,context=model_context((0.,90.)))
        self.assertAlmostEqual(state['X'],100.);self.assertAlmostEqual(state['Y'],100.);self.assertAlmostEqual(state['R'],90.)

    def test_joint_function_result_converts_once(self):
        seen=[]
        def forward(*args):
            seen.append('F');point=identity_pose();point.values['LOCATION'].values['X']=7.
            return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        program,_=compile_program('n=0 '+call('make()'),decl=DECL,context=callback_context(forward=forward),routines='ROUTINE make: JOINTPOS BEGIN n=n+1 RETURN j END make')
        program._state.values['J']=joint([0.]*9)
        self.assertEqual((program.run()['N'],program.snapshot()['X'],seen),(1,7.,['F']))

    def test_forward_requires_no_current_joint_seed(self):
        ctx=model_context();ctx.robot.current=None
        program,_=compile_program(call('j'),decl=DECL,context=ctx);program._state.values['J']=joint([0.]*9)
        self.assertEqual(program.run()['X'],200.);self.assertIsNone(ctx.robot.current)

    def test_external_model_validates_axes_without_output_slots(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100},{'type':'prismatic'}],'external_axes':1,'current':{'joints':{'type':['JOINTPOS',2],'value':[0.,25.]}}}})
        state=run(call('CURJPOS(0,0)'),decl=DECL,context=ctx)
        self.assertEqual((state['X'],state['Z']),(100.,25.));self.assertEqual(ctx.robot.current.joints.values,[0.,25.])

    def test_forward_conversion_precedes_output_selector(self):
        calls=[]
        def forward(*args):
            calls.append('F');point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        program,_=compile_program('n=0 '+call('j','values[pick()],y,z,w,p,r,result_cfg'),decl=DECL,context=callback_context(forward=forward),routines='ROUTINE pick: INTEGER BEGIN n=n+1 RETURN 1 END pick')
        program._state.values['J']=joint([0.]*9);self.assertEqual(program.run()['N'],1);self.assertEqual(calls,['F'])

    def test_missing_model_skips_output_selectors(self):
        program,_=compile_program('n=0 x=99 '+call('j','values[pick()],y,z,w,p,r,result_cfg'),decl=DECL,routines='ROUTINE pick: INTEGER BEGIN n=n+1 RETURN 1 END pick')
        program._state.values['J']=joint([0.]*9)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'robot'): program.run()
        self.assertEqual((program.snapshot()['N'],program.snapshot()['X']),(0,99.))

    def test_failed_forward_adapter_preserves_outputs(self):
        program,_=compile_program('n=0 x=99 '+call('j','values[pick()],y,z,w,p,r,result_cfg'),decl=DECL,context=callback_context(forward=lambda *args:None),routines='ROUTINE pick: INTEGER BEGIN n=n+1 RETURN 1 END pick')
        program._state.values['J']=joint([0.]*9)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['N'],program.snapshot()['X']),(0,99.))

    def test_forward_callback_gets_independent_joints(self):
        def forward(value,*args):
            value.values[0]=99.;point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        program,_=compile_program(call('j'),decl=DECL,context=callback_context(forward=forward));program._state.values['J']=joint([0.]*9)
        program.run();self.assertEqual(program.snapshot()['J']['axes'],[0.]*9)

    def test_joint_padding_guard(self):
        program,_=compile_program('x=99 '+call('j'),decl=DECL,context=model_context());program._state.values['J']=joint([0.]*8+[1.])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Unused'): program.run()
        self.assertEqual(program.snapshot()['X'],99.)

    def test_config_and_frame_tool_selection(self):
        ctx=model_context((0.,0.));frame=identity_pose();frame.values['LOCATION'].values['X']=25.;ctx.robot.frames[0]=frame
        tool=identity_pose();tool.values['LOCATION'].values['Z']=10.;ctx.robot.tools[0]=tool
        state=run('j=CURJPOS(0,0) '+call('j'),decl=DECL,context=ctx)
        self.assertEqual((state['X'],state['Z']),(175.,10.))

    def test_abort_is_sticky_before_decomposition(self):
        program=None
        def forward(*args):
            try: program._state.abort(90)
            except rt.KarelAbort: pass
            point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        program,_=compile_program('x=99 '+call('j'),decl=DECL,context=callback_context(forward=forward));program._state.values['J']=joint([0.]*9)
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual(program.snapshot()['X'],99.)


class DecompositionIntegrationTests(unittest.TestCase):
    def test_cartesian_extraction_has_no_service_requests(self):
        program,result=compile_program(START+call(),decl=DECL);program.run()
        self.assertEqual(program.service_requests,());self.assertEqual(result.report['joint_geometry'],[])
        self.assertTrue(result.report['unpos_calls'][0]['source_snapshot'])

    def test_joint_service_reports_and_transitive_effects(self):
        routines='ROUTINE extract BEGIN '+call('j')+' END extract ROUTINE relay BEGIN extract END relay'
        program,result=compile_program('j=CURJPOS(0,0) relay',decl=DECL,context=model_context((0.,0.)),routines=routines)
        program.run();self.assertEqual([row['operation'] for row in program.service_requests],['CURJPOS','JOINT_GEOMETRY'])
        self.assertTrue(result.report['routine_effects']['RELAY']['potential_service_requests'])
        self.assertEqual(result.report['joint_geometry'][0]['operation'],'UNPOS')
        self.assertEqual(result.report['unpos_calls'][0]['source_type'],('JOINTPOS',9))
        self.assertFalse(result.report['unpos_policy']['controller_validated'])

    def test_linked_library_uses_calling_root_group(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'groups':{'1':{'dh':[{'a':100}]},'2':{'dh':[{'a':20}]}},'active_group':1}})
        main=source('MAIN','extract(j)',decl='dummy: XYZWPREXT IN GROUP[2] j: JOINTPOS',routines='ROUTINE extract(value: JOINTPOS) FROM LIB')
        lib=source('LIB','',decl='x,y,z,w,p,r: REAL cfg: CONFIG',routines='ROUTINE extract(value: JOINTPOS) BEGIN UNPOS(value,x,y,z,w,p,r,cfg) END extract')
        instance=translate_project({'main':main,'lib':lib}).instantiate(context=ctx)
        instance.programs['MAIN']._state.values['J']=joint([0.]*9)
        snapshot=instance.run('MAIN');self.assertEqual(snapshot['LIB']['values']['X'],20.)

    def test_context_roundtrip_preserves_model_and_values(self):
        ctx=model_context((0.,90.));program,result=compile_program('j=CURJPOS(0,0) '+call('j'),decl=DECL,context=ctx)
        expected=program.run();restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        namespace={'__name__':'restored_decomposition'};exec(result.python_source,namespace)
        self.assertEqual(namespace['Program'](context=restored).run(),expected)

    def test_wrong_inputs_and_protected_outputs_stay_rejected(self):
        for body in (call('cfg'),call('x'),call('point.normal'),call('pose','point.normal.x,y,z,w,p,r,result_cfg'),call('pose','cfg.cfg_turn_no1,y,z,w,p,r,result_cfg')):
            with self.subTest(body=body),self.assertRaises(TranslationError): compile_program(body,decl=DECL)

    def test_legacy_storage_only_guards_remain(self):
        for value in ('(pose)','point','e','j','POS(1,2,3,0,0,0,cfg)'):
            with self.subTest(value=value),self.assertRaises(TranslationError): legacy_translate('PROGRAM T VAR '+DECL+' BEGIN '+call(value)+' END T')

    def test_runtime_value_helper_remains_pythonic_only(self):
        source_ref,outputs,_=runtime_fixture()
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): rt.unpos_value(source_ref.raw(),outputs)


if __name__=='__main__': unittest.main()
