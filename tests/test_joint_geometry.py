"""Authored forward-model joint operands, evaluation order and context guards."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.kinematics import pose as identity_pose
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program,run
from tests.test_joint_interoperability import joint,model_context
from tests.test_kinematic_assignments import callback_context


DECL='j,k: JOINTPOS p: POSITION e,f: XYZWPREXT a,b: VECTOR flag: BOOLEAN s,n: INTEGER cfg: CONFIG'
START="j=CURJPOS(0,0) CNV_STR_CONF('N',cfg,s) f=POS(0,0,0,0,0,0,cfg) "
TOL=dict(pose_tolerance=(.001,.001,True),external_tolerance=(0.,0.,0.))


def explicit(body,values=(0.,0.),**options):
    return run(START+body,decl=DECL,context=model_context(values),**options)


def point_forward(value,frame,tool,selector):
    point=identity_pose()
    for axis,number in zip(('X','Y','Z'),value.values[:3]): point.values['LOCATION'].values[axis]=number
    return point,point.values['CONFIG_DATA'],[value.values[0],value.values[1],0.]


class JointGeometryValueTests(unittest.TestCase):
    def test_inverse_uses_forward_pose(self):
        state=explicit('e=INV(j)')
        self.assertEqual((state['E']['X'],state['E']['Y'],state['E']['Z']),(-200.,0.,0.))

    def test_joint_colon_joint(self): self.assertEqual(explicit('e=j:j')['E']['X'],400.)

    def test_mixed_colon_operands(self):
        for expression in ('j:f','f:j','j:p','p:j'):
            with self.subTest(expression=expression):
                state=explicit('p=f e='+expression)
                self.assertEqual(state['E']['X'],200.)

    def test_result_is_extended_even_with_position_destination(self):
        p,result=compile_program(START+'p=INV(j)',decl=DECL,context=model_context((0.,0.)))
        self.assertEqual(p.run()['P']['LOCATION']['X'],-200.)
        self.assertEqual(result.report['frame_operations'][-1]['result_type'],'XYZWPREXT')

    def test_axes_are_independent_cartesian_vectors(self):
        state=explicit('a=APPROACH(j) b=ORIENT(j) a.x=7',(0.,90.))
        self.assertEqual(state['A'],{'X':7.,'Y':0.,'Z':1.});self.assertEqual(state['B'],{'X':-1.,'Y':0.,'Z':0.})

    def test_approximate_comparison_uses_cartesian_tolerances(self):
        self.assertTrue(explicit('flag=j>=<j',**TOL)['FLAG'])

    def test_different_joint_poses_compare_false(self):
        p,_=compile_program(START+'flag=j>=<k',decl=DECL,context=model_context((0.,0.)),**TOL)
        p._state.values['K']=joint([90.,0.]+[0.]*7);self.assertFalse(p.run()['FLAG'])

    def test_mirror_joint_value(self):
        state=explicit('e=MIRROR(j,f,FALSE)',(0.,90.))
        self.assertAlmostEqual(state['E']['X'],100.);self.assertAlmostEqual(state['E']['Y'],-100.)

    def test_mirror_joint_frame(self):
        state=explicit('f.x=1 f.y=3 e=MIRROR(f,j,FALSE)')
        self.assertEqual((state['E']['X'],state['E']['Y']),(1.,-3.))

    def test_mirror_joint_value_and_frame(self):
        state=explicit('e=MIRROR(j,j,TRUE)')
        self.assertEqual((state['E']['X'],state['E']['Y']),(200.,0.))

    def frame(self,arguments):
        p,_=compile_program('e=FRAME('+arguments+')',decl='x,y,z,o: JOINTPOS3 e: XYZWPREXT',context=callback_context(forward=point_forward))
        for name,values in (('X',[0.,0.,0.]),('Y',[20.,0.,0.]),('Z',[0.,20.,0.]),('O',[8.,9.,0.])): p._state.values[name]=joint(values)
        return p.run()

    def test_three_joint_frame_points(self):
        state=self.frame('x,y,z');self.assertEqual((state['E']['X'],state['E']['Y'],state['E']['R']),(0.,0.,0.))

    def test_four_joint_frame_points(self):
        state=self.frame('x,y,z,o');self.assertEqual((state['E']['X'],state['E']['Y'],state['E']['EXT1'],state['E']['EXT2']),(8.,9.,8.,9.))

    def test_joint_frame_result_can_feed_inverse(self):
        state=self.frame('x,y,z');self.assertEqual(state['E']['Z'],0.)
        self.assertEqual(explicit('e=INV(j:f)')['E']['X'],-200.)

    def test_external_axes_survive_inverse_mirror_and_colon(self):
        for expression in ('INV(j)','MIRROR(j,f,FALSE)','f:j'):
            with self.subTest(expression=expression):
                ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100},{'type':'prismatic'}],'external_axes':1,'current':{'joints':{'type':['JOINTPOS',2],'value':[0.,25.]}}}})
                state=run(START+'e='+expression,decl=DECL,context=ctx)
                self.assertEqual([state['E'][key] for key in ('EXT1','EXT2','EXT3')],[25.,0.,0.])

    def test_colon_keeps_right_extended_metadata(self):
        p,_=compile_program('e=j:k',decl=DECL.replace('j,k: JOINTPOS','j,k: JOINTPOS3'),context=callback_context(forward=point_forward))
        p._state.values['J']=joint([1.,2.,0.]);p._state.values['K']=joint([3.,4.,0.])
        state=p.run();self.assertEqual((state['E']['X'],state['E']['Y'],state['E']['EXT1'],state['E']['EXT2']),(4.,6.,3.,4.))

    def test_selected_frame_and_tool(self):
        ctx=model_context((0.,0.));ctx.robot.frames[2]=identity_pose();ctx.robot.frames[2].values['LOCATION'].values['X']=10.
        ctx.robot.tools[3]=identity_pose();ctx.robot.tools[3].values['LOCATION'].values['Y']=20.;ctx.robot.active_frame=2;ctx.robot.active_tool=3
        state=run(START+'e=INV(j)',decl=DECL,context=ctx)
        self.assertEqual((state['E']['X'],state['E']['Y']),(-190.,-20.))

    def test_narrow_joint_width(self):
        p,_=compile_program('e=INV(j)',decl=DECL.replace('j,k: JOINTPOS','j,k: JOINTPOS2'),context=model_context((0.,0.)))
        p._state.values['J']=joint([0.,0.]);self.assertEqual(p.run()['E']['X'],-200.)

    def test_forward_geometry_does_not_require_current_seed(self):
        ctx=model_context();ctx.robot.current=None;p,_=compile_program('e=INV(j)',decl=DECL,context=ctx)
        p._state.values['J']=joint([0.]*9);self.assertEqual(p.run()['E']['X'],-200.);self.assertIsNone(ctx.robot.current)


class JointGeometryGuardTests(unittest.TestCase):
    def test_missing_robot_context_is_not_invented(self):
        for expression in ('INV(j)','j:j','FRAME(j,j,j)','MIRROR(j,j,FALSE)','APPROACH(j)','ORIENT(j)'):
            with self.subTest(expression=expression):
                p,_=compile_program(('a=' if expression.startswith(('APPROACH','ORIENT')) else 'e=')+expression,decl=DECL)
                p._state.values['J']=joint([0.]*9)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'robot'): p.run()

    def test_limits_only_context_does_not_supply_forward_model(self):
        ctx=rt.ExecutionContext(robot=rt.RobotContext(joint_limits=[(-180,180)]*9,frames={0:identity_pose()},tools={0:identity_pose()}))
        p,_=compile_program('e=INV(j)',decl=DECL,context=ctx);p._state.values['J']=joint([0.]*9)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'adapter'): p.run()

    def test_frame_and_tool_maps_are_required(self):
        for field in ('frames','tools'):
            with self.subTest(field=field):
                ctx=model_context();getattr(ctx.robot,field).clear();p,_=compile_program('e=INV(j)',decl=DECL,context=ctx);p._state.values['J']=joint([0.]*9)
                with self.assertRaisesRegex(rt.KarelRuntimeError,field[:-1]): p.run()

    def test_invalid_partial_or_padded_joint_values_fail(self):
        for values in ([0.,rt.UNINITIALIZED]+[0.]*7,[float('nan')]+[0.]*8,[0.]*8+[1.]):
            with self.subTest(values=values):
                p,_=compile_program('e=INV(j)',decl=DECL,context=model_context());p._state.values['J']=joint(values)
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual(p.snapshot()['E']['X'],{'uninitialized':True})

    def test_declared_joint_width_must_match_storage(self):
        seen=[];ctx=callback_context(forward=lambda *args:seen.append(args));p,_=compile_program('e=INV(j)',decl=DECL,context=ctx);p._state.values['J']=joint([0.,0.])
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(seen,[])

    def test_invalid_forward_result_preserves_destination(self):
        for answer in (None,(identity_pose(),identity_pose().values['CONFIG_DATA'],[0.])):
            with self.subTest(answer=answer):
                p,_=compile_program('e=INV(j)',decl=DECL,context=callback_context(forward=lambda *args:answer));p._state.values['J']=joint([0.]*9)
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual(p.snapshot()['E']['X'],{'uninitialized':True})

    def test_model_limits_remain_checked(self):
        ctx=model_context((90.,0.));ctx.robot.model.limits[0]=(-5.,5.)
        p,_=compile_program(START+'e=INV(j)',decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'limits'): p.run()

    def test_comparison_needs_pose_and_external_tolerances(self):
        for options in ({},dict(pose_tolerance=(1.,1.,True))):
            with self.subTest(options=options),self.assertRaisesRegex(rt.KarelRuntimeError,'tolerance'): explicit('flag=j>=<j',**options)

    def test_vector_and_config_operands_remain_rejected(self):
        for kind in ('VECTOR','CONFIG'):
            with self.subTest(kind=kind),self.assertRaises(TranslationError): compile_program('e=INV(value)',decl=DECL+' value: '+kind)

    def test_legacy_unpos_retains_exact_source_interface(self):
        with self.assertRaises(TranslationError): legacy_translate('PROGRAM T VAR j: JOINTPOS x,y,z,w,p,r: REAL cfg: CONFIG BEGIN UNPOS(j,x,y,z,w,p,r,cfg) END T')

    def test_routine_and_named_array_kinematics_keep_explicit_context(self):
        for body,routines in (('take(j)','ROUTINE take(value: POSITION) BEGIN END take'),('e=produce()','ROUTINE produce: POSITION BEGIN RETURN j END produce')):
            with self.subTest(body=body):
                program,_=compile_program(START+body,decl=DECL,routines=routines,context=model_context((0.,90.)))
                program.run()
                self.assertEqual(len([row for row in program.service_requests if row['operation'] in ('KINEMATIC_ARGUMENT','KINEMATIC_RETURN')]),1)
                with self.assertRaises(TranslationError): legacy_translate('PROGRAM T VAR '+DECL+' '+routines+' BEGIN '+body+' END T')
        program,_=compile_program('a=b',prefix='TYPE joints_t=ARRAY[1]OF JOINTPOS',decl='a:ARRAY[1]OF POSITION b:joints_t',context=model_context((0.,90.)))
        program._state.values['B'].values[0]=joint([0.,90.]+[0.]*7)
        self.assertAlmostEqual(program.run()['A'][0]['LOCATION']['X'],100.);self.assertEqual(program.snapshot()['B'][0]['axes'],[0.,90.]+[0.]*7)

    def test_runtime_strict_guard(self):
        p,_=compile_program('',decl=DECL,context=model_context())
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): p._state.geometry_value(joint([0.]*9),('JOINTPOS',9))

    def test_legacy_translation_rejections_remain(self):
        for expression in ('INV(j)','j:j','APPROACH(j)','MIRROR(j,j,FALSE)'):
            with self.subTest(expression=expression),self.assertRaises(TranslationError): legacy_translate('PROGRAM T VAR '+DECL+' BEGIN e='+expression+' END T')


class JointGeometryOwnershipTests(unittest.TestCase):
    def test_forward_callback_receives_detached_joint_values(self):
        def forward(value,*args):
            value.values[0]=99.;point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=compile_program('e=INV(j)',decl=DECL,context=callback_context(forward=forward));p._state.values['J']=joint([0.]*9);p.run()
        self.assertEqual(p.snapshot()['J']['axes'],[0.]*9)

    def test_left_conversion_precedes_right_source_effects(self):
        routines='ROUTINE later: XYZWPREXT BEGIN j=k RETURN f END later'
        p,_=compile_program(START+'e=j:later()',decl=DECL,context=model_context((0.,0.)),routines=routines)
        p._state.values['K']=joint([90.,0.]+[0.]*7);state=p.run()
        self.assertEqual((state['E']['X'],state['J']['axes'][0]),(200.,90.))

    def test_failed_left_conversion_skips_right_function(self):
        p,_=compile_program('n=0 e=j:later()',decl=DECL,context=callback_context(forward=lambda *args:None),routines='ROUTINE later: XYZWPREXT BEGIN n=n+1 RETURN f END later')
        p._state.values['J']=joint([0.]*9)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['N'],0)

    def test_conversion_precedes_assignment_target_selector(self):
        calls=[]
        def forward(*args): calls.append('F');point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        routines='ROUTINE at: INTEGER BEGIN n=n+1 RETURN 1 END at'
        p,_=compile_program('n=0 points[at()]=INV(j)',decl=DECL+' points: ARRAY[1] OF XYZWPREXT',routines=routines,context=callback_context(forward=forward));p._state.values['J']=joint([0.]*9)
        self.assertEqual(p.run()['N'],1);self.assertEqual(calls,['F'])

    def test_conversion_failure_skips_target_selector(self):
        p,_=compile_program('n=0 points[at()]=INV(j)',decl=DECL+' points: ARRAY[1] OF XYZWPREXT',routines='ROUTINE at: INTEGER BEGIN n=n+1 RETURN 1 END at',context=callback_context(forward=lambda *args:None));p._state.values['J']=joint([0.]*9)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['N'],0)

    def test_each_joint_function_and_conversion_runs_once(self):
        seen=[]
        def forward(*args): seen.append('F');point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        routines='ROUTINE value: JOINTPOS BEGIN n=n+1 RETURN j END value'
        p,_=compile_program('n=0 e=value():value()',decl=DECL,routines=routines,context=callback_context(forward=forward));p._state.values['J']=joint([0.]*9)
        self.assertEqual(p.run()['N'],2);self.assertEqual(seen,['F','F'])

    def test_mirror_boolean_argument_follows_joint_conversions(self):
        seen=[]
        def forward(*args): seen.append('F');point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=compile_program('n=0 e=MIRROR(j,j,turn())',decl=DECL,routines='ROUTINE turn: BOOLEAN BEGIN n=n+1 RETURN FALSE END turn',context=callback_context(forward=forward));p._state.values['J']=joint([0.]*9)
        self.assertEqual(p.run()['N'],1);self.assertEqual(seen,['F','F'])

    def test_swallowed_abort_prevents_geometry_commit(self):
        p=None
        def forward(*args):
            try: p._state.abort(99)
            except rt.KarelAbort: pass
            point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=compile_program('e=INV(j)',decl=DECL,context=callback_context(forward=forward));p._state.values['J']=joint([0.]*9)
        with self.assertRaises(rt.KarelAbort): p.run()
        self.assertEqual(p.snapshot()['E']['X'],{'uninitialized':True})

    def test_abort_is_authoritative_over_later_callback_failure(self):
        p=None
        def forward(*args):
            try: p._state.abort(99)
            except rt.KarelAbort: pass
            raise ValueError('later failure')
        p,_=compile_program('e=INV(j)',decl=DECL,context=callback_context(forward=forward));p._state.values['J']=joint([0.]*9)
        with self.assertRaises(rt.KarelAbort): p.run()

    def test_pause_resume_does_not_repeat_completed_operand(self):
        p,_=compile_program(START+'e=INV(j) PAUSE a=APPROACH(j)',decl=DECL,context=model_context((0.,0.)))
        with self.assertRaises(rt.KarelPause): p.run()
        self.assertEqual(len([row for row in p.service_requests if row['operation']=='JOINT_GEOMETRY']),1)
        p.resume();self.assertEqual(len([row for row in p.service_requests if row['operation']=='JOINT_GEOMETRY']),2)

    def test_linked_geometry_uses_root_task_group(self):
        sources={'main':'PROGRAM MAIN VAR j: JOINTPOS e: XYZWPREXT dummy: XYZWPREXT IN GROUP[2] ROUTINE convert(value: JOINTPOS): XYZWPREXT FROM LIB BEGIN j=CURJPOS(0,0) e=convert(j) END MAIN',
                 'lib':'PROGRAM LIB VAR dummy: XYZWPREXT IN GROUP[1] ROUTINE convert(value: JOINTPOS): XYZWPREXT BEGIN RETURN INV(value) END convert BEGIN END LIB'}
        other=model_context((0.,0.)).robot;other.model=rt.SerialRobotModel([{'a':30},{'a':40}]);other.forward=other.model.forward
        ctx=rt.ExecutionContext(robot=rt.RobotContext(groups={1:model_context((0.,0.)).robot,2:other},active_group=1))
        state=translate_project(sources).instantiate(context=ctx).run('MAIN')
        self.assertEqual(state['MAIN']['values']['E']['X'],-70.)

    def test_report_records_joint_operand_and_services_are_value_free(self):
        p,result=compile_program(START+'e=INV(j)',decl=DECL,context=model_context((0.,0.)));p.run()
        row=result.report['joint_geometry'][0];self.assertEqual((row['operation'],row['source_type'],row['target_type']),('INV',('JOINTPOS',9),('XYZWPREXT',)))
        self.assertTrue(row['evaluated_once']);self.assertTrue(row['independent_value'])
        self.assertFalse(result.report['joint_geometry_policy']['controller_validated'])
        self.assertTrue(all(set(row)=={'operation','line','outcome'} for row in p.service_requests))

    def test_repeated_run_resets_geometry_records(self):
        p,_=compile_program(START+'e=INV(j)',decl=DECL,context=model_context((0.,0.)));p.run();p.run()
        self.assertEqual(len([row for row in p.service_requests if row['operation']=='JOINT_GEOMETRY']),1)

    def test_robot_current_state_is_not_changed_and_persists(self):
        ctx=model_context((0.,90.));before=ctx.to_config()['robot'];run(START+'e=INV(j) a=ORIENT(j)',decl=DECL,context=ctx)
        self.assertEqual(ctx.to_config()['robot'],before)
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())));self.assertEqual(restored.to_config(),ctx.to_config())

    def test_geometry_supports_individual_array_and_structure_fields(self):
        p,_=compile_program('e=INV(items[1].j)',decl='items: ARRAY[1] OF item_t e: XYZWPREXT',prefix='TYPE item_t=STRUCTURE j: JOINTPOS2 ENDSTRUCTURE',context=model_context((0.,0.)))
        p._state.values['ITEMS'].values[0].values['J']=joint([0.,0.]);self.assertEqual(p.run()['E']['X'],-200.)

    def test_short_circuit_does_not_convert_skipped_operands(self):
        p,_=compile_program('flag=FALSE AND (j>=<j)',decl=DECL)
        self.assertFalse(p.run()['FLAG']);self.assertEqual(p.service_requests,())

    def test_callback_configuration_failure_preserves_result(self):
        def forward(*args):
            point=identity_pose();point.values['CONFIG_DATA'].values['CFG_TURN_NO1']=8
            return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=compile_program('e=INV(j)',decl=DECL,context=callback_context(forward=forward));p._state.values['J']=joint([0.]*9)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['E']['X'],{'uninitialized':True})

    def test_callback_input_mutation_does_not_change_second_source(self):
        seen=[]
        def forward(value,*args):
            seen.append(value.values[0]);value.values[0]=99.;point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=compile_program('e=j:j',decl=DECL,context=callback_context(forward=forward));p._state.values['J']=joint([0.]*9);p.run()
        self.assertEqual(seen,[0.,0.]);self.assertEqual(p.snapshot()['J']['axes'],[0.]*9)

    def test_implicit_service_effects_propagate_through_routine_calls(self):
        routines='ROUTINE outer: XYZWPREXT BEGIN RETURN inner() END outer ROUTINE inner: XYZWPREXT BEGIN RETURN INV(j) END inner'
        p,result=compile_program(START+'e=outer()',decl=DECL,context=model_context((0.,0.)),routines=routines)
        self.assertEqual(p.run()['E']['X'],-200.)
        self.assertTrue(all(result.report['routine_effects'][name]['potential_service_requests'] for name in ('INNER','OUTER')))


if __name__=='__main__': unittest.main()
