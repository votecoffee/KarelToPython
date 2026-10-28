"""Authored pose-to-VECTOR point transforms, type flow and ownership checks."""
import math
import random
import unittest

from karel2py import translate,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program,run
from tests.test_frame_transforms import quaternion,rotate,runtime_pose
from tests.test_position_conversions import runtime_position
from tests.test_joint_interoperability import model_context,joint
from tests.test_kinematic_assignments import callback_context

DECL='cfg:CONFIG code,n,i,calls:INTEGER a,b:XYZWPR p:POSITION e:XYZWPREXT v,w,res:VECTOR value:REAL trace:STRING[20]'
SETUP="CNV_STR_CONF('N',cfg,code) a=POS(10,20,30,0,0,90,cfg) p=a e=a v=VEC(2,3,4) "


def execute(body,**options):return run(SETUP+body,decl=options.pop('decl',DECL),**options)


def vector(values):
    result=rt.Structure(('VECTOR',));result.values.update(zip(('X','Y','Z'),map(float,values)));return result


class VectorFrameMathTests(unittest.TestCase):
    def test_report_records_affine_point_choice_and_exact_result(self):
        p,result=compile_program(SETUP+'res=a:v',decl=DECL);p.run();policy=result.report['vector_frame_policy']
        self.assertFalse(policy['controller_validated']);self.assertIn('local point',policy['calculation']);self.assertIn('right VECTOR',result.report['frame_policy']['result_type'])
        self.assertEqual(result.report['frame_operations'][0]['result_type'],'VECTOR')

    def test_cartesian_representations_transform_to_vector(self):
        for pose in ('a','p','e'):
            with self.subTest(pose=pose):self.assertEqual(execute('res='+pose+':v')['RES'],dict(X=7.,Y=22.,Z=34.))

    def test_zero_vector_selects_frame_origin(self):self.assertEqual(execute('res=a:VEC(0,0,0)')['RES'],dict(X=10.,Y=20.,Z=30.))

    def test_identity_preserves_local_point(self):self.assertEqual(execute('a=POS(0,0,0,0,0,0,cfg) res=a:v')['RES'],dict(X=2.,Y=3.,Z=4.))

    def test_inverse_recovers_local_point(self):self.assertEqual(execute('w=a:v res=INV(a):w')['RES'],dict(X=2.,Y=3.,Z=4.))

    def test_pose_chain_and_nested_point_transform_agree(self):
        values=execute('b=POS(-4,5,6,90,0,0,cfg) w=a:b:v res=a:(b:v)');self.assertEqual(values['RES'],values['W'])

    def test_vector_difference_expresses_rotated_direction(self):self.assertEqual(execute('res=(a:v)-(a:VEC(0,0,0))')['RES'],dict(X=-3.,Y=2.,Z=4.))

    def test_rotation_about_x(self):self.assertEqual(execute('a=POS(0,0,0,90,0,0,cfg) res=a:v')['RES'],dict(X=2.,Y=-4.,Z=3.))

    def test_rotation_about_y(self):self.assertEqual(execute('a=POS(0,0,0,0,90,0,cfg) res=a:v')['RES'],dict(X=4.,Y=3.,Z=-2.))

    def test_result_has_no_config_or_external_axes(self):
        values=execute('e.ext1=100 e.ext2=200 e.ext3=300 res=e:v');self.assertEqual(set(values['RES']),{'X','Y','Z'})

    def test_random_matrix_and_euler_inputs_match_independent_quaternions(self):
        rng=random.Random(281831)
        with rt._numeric_scope('pythonic'):
            for _ in range(100):
                angles=tuple(rng.uniform(-540,540) for _ in range(3));origin=tuple(rng.uniform(-100,100) for _ in range(3));local=tuple(rng.uniform(-30,30) for _ in range(3))
                expected=tuple(a+b for a,b in zip(origin,rotate(quaternion(angles),local)))
                for pose in (runtime_pose((*origin,*angles)),runtime_position(angles,origin)):
                    actual=rt.frame_transform(pose,vector(local))
                    for axis,wanted in zip(('X','Y','Z'),expected):self.assertAlmostEqual(actual.values[axis],wanted,places=10)

    def test_gimbal_lock_inputs_need_no_euler_result_conversion(self):
        with rt._numeric_scope('pythonic'):
            for angles in ((30,90,40),(30,-90,40),(30,90-1e-12,40)):
                actual=rt.frame_transform(runtime_pose((1,2,3,*angles)),vector((4,5,6)))
                expected=tuple(a+b for a,b in zip((1,2,3),rotate(quaternion(angles),(4,5,6))))
                for axis,wanted in zip(('X','Y','Z'),expected):self.assertAlmostEqual(actual.values[axis],wanted,places=10)

    def test_overflow_is_explicit(self):
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.frame_transform(runtime_pose((1.7e308,0,0,0,0,0)),vector((1.7e308,0,0)))

    def test_invalid_position_basis_is_not_repaired(self):
        bad=runtime_position((0,0,0),(0,0,0));bad.values['NORMAL'].values['X']=2.
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'unit'):rt.frame_transform(bad,vector((1,2,3)))

    def test_partial_vector_and_nonfinite_component_are_rejected(self):
        with rt._numeric_scope('pythonic'):
            for point in (rt.Structure(('VECTOR',)),vector((float('inf'),0,0)),vector((float('nan'),0,0))):
                with self.subTest(point=point.values),self.assertRaises(rt.KarelRuntimeError):rt.frame_transform(runtime_pose(),point)

    def test_missing_config_and_external_metadata_still_fail(self):
        pose=runtime_pose();pose.values['CONFIG_DATA'].values['CFG_LEFT']=rt.UNINITIALIZED
        ext=rt.Structure(('XYZWPREXT',));ext.values.update(runtime_pose().values)
        with rt._numeric_scope('pythonic'):
            for value in (pose,ext):
                with self.assertRaises(rt.KarelRuntimeError):rt.frame_transform(value,vector((1,2,3)))

    def test_runtime_and_legacy_strict_guards_remain(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.frame_transform(runtime_pose(),vector((1,2,3)))
        with self.assertRaises(TranslationError):legacy_translate('PROGRAM T VAR p:POSITION v:VECTOR BEGIN v=p:v END T')


class VectorFrameLanguageTests(unittest.TestCase):
    def test_grouped_result_component_type_is_real(self):self.assertEqual(execute('value=(a:v).x')['VALUE'],7.)

    def test_computed_point_components_are_valid_value_arguments(self):
        routines='ROUTINE take(x:REAL) BEGIN value=x END take'
        for expression,expected in [('(a:(v+v)).x',4.),('(a:-v).x',13.),('(a:(2*v)).z',38.),('(a:(v*(v+v).x)).z',46.)]:
            with self.subTest(expression=expression):self.assertEqual(execute('take('+expression+')',routines=routines)['VALUE'],expected)

    def test_computed_argument_type_inspection_has_no_duplicate_effects(self):
        p,result=compile_program(SETUP+'calls=0 take((a:(point()+v)).x)',decl=DECL,routines='ROUTINE point:VECTOR BEGIN calls=calls+1 RETURN v END point ROUTINE take(x:REAL) BEGIN value=x END take')
        values=p.run();self.assertEqual((values['CALLS'],values['VALUE']),(1,4.));self.assertEqual(len(result.report['frame_operations']),1)

    def test_result_is_valid_exact_vector_routine_argument(self):
        values=execute('take(a:v)',routines='ROUTINE take(point:VECTOR) BEGIN res=point point.x=99 END take');self.assertEqual(values['RES']['X'],7.);self.assertEqual(values['V']['X'],2.)

    def test_result_can_return_through_vector_function(self):
        values=execute('res=project(v)',routines='ROUTINE project(point:VECTOR):VECTOR BEGIN RETURN a:point END project');self.assertEqual(values['RES']['Y'],22.)

    def test_bare_vector_function_result_can_be_transformed(self):
        values=execute('res=a:point',routines='ROUTINE point:VECTOR BEGIN RETURN VEC(2,3,4) END point');self.assertEqual(values['RES']['Z'],34.)

    def test_alias_types_and_structure_fields(self):
        values=execute('record.pose_value=a record.point=v res=record.pose_value:record.point',prefix='TYPE point_t=VECTOR packet_t=STRUCTURE pose_value:XYZWPR point:point_t ENDSTRUCTURE',decl=DECL+' record:packet_t');self.assertEqual(values['RES']['X'],7.)

    def test_array_elements_and_vector_result_arrays(self):
        values=execute('points[1]=a:v points[2]=INV(a):points[1] res=points[2]',decl=DECL+' points:ARRAY[2] OF VECTOR');self.assertEqual(values['RES'],dict(X=2.,Y=3.,Z=4.))

    def test_array_function_result_element_can_be_transformed(self):
        values=execute('res=a:points()[1]',prefix='TYPE points_t=ARRAY[1] OF VECTOR',routines='ROUTINE points:points_t VAR values:points_t BEGIN values[1]=VEC(2,3,4) RETURN values END points');self.assertEqual(values['RES']['X'],7.)

    def test_whole_vector_array_copy_remains_exact(self):
        values=execute('points[1]=a:v other=points res=other[1]',decl=DECL+' points,other:ARRAY[1] OF VECTOR');self.assertEqual(values['RES']['Y'],22.)

    def test_orientation_operand_is_read_only_source_but_valid_point_value(self):
        values=execute('res=a:p.normal');self.assertEqual(values['RES'],dict(X=9.,Y=20.,Z=30.))

    def test_result_is_independently_writable(self):
        values=execute('res=a:v w=res res.x=99 v.y=100 a.z=200');self.assertEqual(values['W'],dict(X=7.,Y=22.,Z=34.))

    def test_existing_destination_component_reference_survives_replacement(self):
        values=execute('update(res.x)',routines='ROUTINE update(alias:REAL) BEGIN res=a:v alias=99 END update');self.assertEqual(values['RES'],dict(X=99.,Y=22.,Z=34.))

    def test_read_write_grouped_expression_formats(self):
        p,_=compile_program(SETUP+"WRITE((a:v).x::0::1,CR)",decl=DECL);p.run();self.assertEqual(p.write_requests[0]['text'],' 7.0\n')

    def test_vector_cannot_be_a_frame_in_either_vector_or_pose_pair(self):
        for expression in ('v:a','v:v','VEC(1,2,3):p'):
            with self.subTest(expression=expression),self.assertRaises(TranslationError):compile_program(SETUP+'res='+expression,decl=DECL)

    def test_frame_construction_and_inverse_do_not_gain_vector_operands(self):
        for expression in ('INV(v)','FRAME(a,b,v)','FRAME(v,a,b)'):
            with self.subTest(expression=expression),self.assertRaises(TranslationError):compile_program(SETUP+'res='+expression,decl=DECL)

    def test_pose_and_vector_routine_return_interfaces_remain_exact(self):
        for routines,body in [('ROUTINE take(point:POSITION) BEGIN END take','take(a:v)'),('ROUTINE point:POSITION BEGIN RETURN a:v END point','p=point()')]:
            with self.subTest(body=body),self.assertRaises(TranslationError):compile_program(SETUP+body,decl=DECL,routines=routines)

    def test_no_implicit_vector_pose_assignment(self):
        with self.assertRaises(TranslationError):compile_program(SETUP+'a=a:v',decl=DECL)

    def test_for_counter_effects_remain_transitive(self):
        with self.assertRaises(TranslationError):compile_program(SETUP+'FOR n=1 TO 2 DO res=a:point() ENDFOR',decl=DECL,routines='ROUTINE point:VECTOR BEGIN n=n+1 RETURN v END point')

    def test_for_counter_read_in_transform_is_allowed(self):
        values=execute('FOR n=1 TO 2 DO res=a:VEC(n,0,0) ENDFOR');self.assertEqual(values['RES'],dict(X=10.,Y=22.,Z=30.))


class VectorFrameOrderTests(unittest.TestCase):
    def test_each_operand_evaluates_once_left_to_right(self):
        values=execute("trace='' calls=0 res=frame_value():point_value()",routines="ROUTINE frame_value:XYZWPR BEGIN trace=trace+'L' calls=calls+1 RETURN a END frame_value ROUTINE point_value:VECTOR BEGIN trace=trace+'R' calls=calls+1 RETURN v END point_value")
        self.assertEqual((values['TRACE'],values['CALLS'],values['RES']['X']),('LR',2,7.))

    def test_right_call_cannot_modify_captured_frame(self):
        values=execute('res=a:point()',routines='ROUTINE point:VECTOR BEGIN a.x=500 RETURN v END point');self.assertEqual((values['A']['X'],values['RES']['X']),(500.,7.))

    def test_bad_left_operand_prevents_right_side_effects(self):
        p,_=compile_program('calls=0 res=p:point()',decl=DECL,routines='ROUTINE point:VECTOR BEGIN calls=calls+1 RETURN VEC(1,2,3) END point')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['CALLS'],0)

    def test_bad_right_retains_left_effect_and_does_not_assign(self):
        p,_=compile_program(SETUP+'calls=0 res=VEC(9,8,7) res=frame_value():w',decl=DECL,routines='ROUTINE frame_value:XYZWPR BEGIN calls=calls+1 RETURN a END frame_value')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['CALLS'],p.snapshot()['RES']),(1,dict(X=9.,Y=8.,Z=7.)))

    def test_target_index_runs_after_successful_transform(self):
        values=execute("trace='' points[target()]=frame_value():point() res=points[1]",decl=DECL+' points:ARRAY[1] OF VECTOR',routines="ROUTINE target:INTEGER BEGIN trace=trace+'T' RETURN 1 END target ROUTINE frame_value:XYZWPR BEGIN trace=trace+'L' RETURN a END frame_value ROUTINE point:VECTOR BEGIN trace=trace+'R' RETURN v END point")
        self.assertEqual((values['TRACE'],values['RES']['X']),('LRT',7.))

    def test_failed_transform_skips_target_index(self):
        p,_=compile_program(SETUP+'calls=0 points[target()]=a:w',decl=DECL+' points:ARRAY[1] OF VECTOR',routines='ROUTINE target:INTEGER BEGIN calls=calls+1 RETURN 1 END target')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['CALLS'],0)

    def test_result_field_inspection_does_not_duplicate_report_sites(self):
        _,result=compile_program(SETUP+'value=(a:v).x',decl=DECL);uses=result.report['frame_operations'];self.assertEqual(len(uses),1);self.assertEqual(uses[0]['operand_types'],['XYZWPR','VECTOR']);self.assertEqual(uses[0]['result_type'],'VECTOR')

    def test_routine_frames_release_after_operand_abort(self):
        p,_=compile_program(SETUP+'res=a:point()',decl=DECL,routines='ROUTINE point:VECTOR BEGIN ABORT RETURN v END point')
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual((p._state.call_depth,p._state.local_frames),(0,[]))


class JointVectorFrameTests(unittest.TestCase):
    def test_joint_left_operand_uses_supplied_forward_model(self):
        values=execute('j=CURJPOS(0,0) res=j:v',decl=DECL+' j:JOINTPOS',context=model_context((0.,0.)));self.assertEqual(values['RES'],dict(X=202.,Y=3.,Z=4.))

    def test_joint_rotation_and_translation_are_both_applied(self):
        values=execute('j=CURJPOS(0,0) res=j:VEC(1,0,0)',decl=DECL+' j:JOINTPOS',context=model_context((0.,90.)));self.assertAlmostEqual(values['RES']['X'],100.);self.assertAlmostEqual(values['RES']['Y'],101.)

    def test_joint_result_is_vector_and_records_one_conversion(self):
        p,result=compile_program(SETUP+'j=CURJPOS(0,0) value=(j:v).x',decl=DECL+' j:JOINTPOS',context=model_context((0.,0.)));p.run()
        self.assertEqual(result.report['frame_operations'][0]['result_type'],'VECTOR');self.assertEqual(len(result.report['joint_geometry']),1);self.assertEqual(len([row for row in p.service_requests if row['operation']=='JOINT_GEOMETRY']),1)

    def test_joint_failure_precedes_right_function(self):
        p,_=compile_program(SETUP+'calls=0 res=j:point()',decl=DECL+' j:JOINTPOS',context=model_context(),routines='ROUTINE point:VECTOR BEGIN calls=calls+1 RETURN v END point')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['CALLS'],0)

    def test_forward_callback_invoked_once_and_no_inverse_needed(self):
        seen=[]
        def forward(value,frame,tool,selector):
            seen.append(value.values[:]);point=runtime_position((0,0,90),(5,6,7));return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        ctx=callback_context(forward=forward);p,_=compile_program(SETUP+'res=j:v',decl=DECL+' j:JOINTPOS2',context=ctx);p._state.values['J']=joint([10.,20.]);values=p.run()
        self.assertEqual(values['RES'],dict(X=2.,Y=8.,Z=11.));self.assertEqual(seen,[[10.,20.]])

    def test_joint_current_context_remains_unchanged(self):
        ctx=model_context((0.,90.));before=ctx.robot.to_config();execute('j=CURJPOS(0,0) res=j:v',decl=DECL+' j:JOINTPOS',context=ctx);self.assertEqual(ctx.robot.to_config(),before)

    def test_joint_width_guard_is_preserved(self):
        p,_=compile_program(SETUP+'res=j:v',decl=DECL+' j:JOINTPOS1',context=model_context());p._state.values['J']=joint([0.])
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_missing_robot_context_does_not_fabricate_pose(self):
        p,_=compile_program(SETUP+'res=j:v',decl=DECL+' j:JOINTPOS2');p._state.values['J']=joint([0.,0.])
        with self.assertRaises(rt.KarelRuntimeError):p.run()


if __name__=='__main__':unittest.main()
