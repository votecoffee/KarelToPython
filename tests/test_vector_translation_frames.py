"""Explicit VECTOR translation frames, inverse vectors and configured point frames."""
from copy import deepcopy
import math
import random
import unittest

from karel2py import translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program,run
from tests.test_frame_transforms import runtime_pose
from tests.test_position_conversions import runtime_position
from tests.test_vector_frames import vector,DECL,SETUP
from tests.test_joint_interoperability import joint,model_context
from tests.test_kinematic_assignments import callback_context
from tests.test_project_scheduler import source


def execute(body,**options):return run(SETUP+body,decl=options.pop('decl',DECL),**options)


class VectorTranslationRuntimeTests(unittest.TestCase):
    def setUp(self):
        mode=rt._numeric_scope('pythonic');mode.__enter__();self.addCleanup(mode.__exit__,None,None,None)

    def test_vector_pair_adds_components_without_pose_metadata(self):
        left=vector((2,3,4));right=vector((5,6,7));result=rt.frame_transform(left,right)
        self.assertEqual(result.spec,('VECTOR',));self.assertEqual(result.values,dict(X=7.,Y=9.,Z=11.))
        self.assertEqual(set(result.values),{'X','Y','Z'})

    def test_vector_left_preserves_pose_orientation_and_configuration_exactly(self):
        right=runtime_pose((10,20,30,721,92,-1080));before=rt.snapshot_value(right)
        result=rt.frame_transform(vector((2,3,4)),right)
        self.assertEqual([result.values[field] for field in ('X','Y','Z','W','P','R')],[12.,23.,34.,721.,92.,-1080.])
        self.assertEqual(rt.snapshot_value(right),before);self.assertIsNot(result.values['CONFIG_DATA'],right.values['CONFIG_DATA'])

    def test_vector_left_position_preserves_matrix_columns(self):
        right=runtime_position((30,40,50),(10,20,30));before=rt.snapshot_value(right)
        result=rt.frame_transform(vector((2,3,4)),right)
        self.assertEqual(result.values['LOCATION'].values,dict(X=12.,Y=23.,Z=34.))
        for field in ('NORMAL','ORIENT','APPROACH','CONFIG_DATA'):
            self.assertEqual(rt.snapshot_value(result.values[field]),before[field]);self.assertIsNot(result.values[field],right.values[field])

    def test_vector_left_extended_pose_keeps_supplied_axes(self):
        right=rt.Structure(('XYZWPREXT',));right.values.update(runtime_pose((10,20,30,1,2,3)).values)
        right.values.update(EXT1=7.,EXT2=-8.,EXT3=9.)
        result=rt.frame_transform(vector((2,3,4)),right)
        self.assertEqual(result.spec,('XYZWPREXT',));self.assertEqual([result.values[field] for field in ('EXT1','EXT2','EXT3')],[7.,-8.,9.])

    def test_vector_inverse_is_negative_translation_and_independent(self):
        original=vector((2,-3,4));result=rt.frame_inverse(original)
        self.assertEqual(result.spec,('VECTOR',));self.assertEqual(result.values,dict(X=-2.,Y=3.,Z=-4.))
        result.values['X']=99.;self.assertEqual(original.values['X'],2.)

    def test_inverse_translation_recovers_vector_and_pose(self):
        left=vector((2,3,4));right=runtime_pose((10,20,30,721,92,-1080));point=vector((5,6,7))
        self.assertEqual(rt.snapshot_value(rt.frame_transform(rt.frame_inverse(left),rt.frame_transform(left,right))),rt.snapshot_value(right))
        self.assertEqual(rt.snapshot_value(rt.frame_transform(rt.frame_inverse(left),rt.frame_transform(left,point))),rt.snapshot_value(point))

    def test_random_translations_preserve_right_geometry(self):
        rng=random.Random(281190)
        for _ in range(80):
            left=tuple(rng.uniform(-100,100) for _ in range(3));where=tuple(rng.uniform(-100,100) for _ in range(3))
            angles=tuple(rng.uniform(-540,540) for _ in range(3))
            for right in (runtime_pose((*where,*angles)),runtime_position(angles,where)):
                result=rt.frame_transform(vector(left),right);position=result.values['LOCATION'].values if result.spec==('POSITION',) else result.values
                for axis,wanted in zip(('X','Y','Z'),(a+b for a,b in zip(left,where))):self.assertAlmostEqual(position[axis],wanted)
                self.assertEqual(result.spec,right.spec)

    def test_translation_result_has_no_storage_alias_to_either_source(self):
        left=vector((2,3,4));right=runtime_position((0,0,0),(10,20,30));result=rt.frame_transform(left,right)
        result.values['LOCATION'].values['X']=99.;result.values['CONFIG_DATA'].values['CFG_LEFT']=not right.values['CONFIG_DATA'].values['CFG_LEFT']
        self.assertEqual(left.values['X'],2.);self.assertEqual(right.values['LOCATION'].values['X'],10.)

    def test_translation_overflow_rejects_without_mutating_sources(self):
        left=vector((1e308,0,0));right=runtime_pose((1e308,0,0,0,0,0));before=(rt.snapshot_value(left),rt.snapshot_value(right))
        with self.assertRaises(rt.KarelRuntimeError):rt.frame_transform(left,right)
        self.assertEqual((rt.snapshot_value(left),rt.snapshot_value(right)),before)

    def test_partial_or_nonfinite_left_vector_rejected(self):
        for left in (rt.Structure(('VECTOR',)),vector((math.inf,0,0)),vector((math.nan,0,0))):
            with self.subTest(left=left.values),self.assertRaises(rt.KarelRuntimeError):rt.frame_transform(left,runtime_pose())

    def test_extra_vector_fields_are_not_silently_ignored(self):
        left=vector((1,2,3));left.values['W']=0.
        with self.assertRaises(rt.KarelRuntimeError):rt.frame_transform(left,runtime_pose())

    def test_complete_right_pose_checks_are_preserved(self):
        bad=runtime_pose();bad.values['CONFIG_DATA'].values['CFG_LEFT']=rt.UNINITIALIZED
        matrix=runtime_position();matrix.values['NORMAL'].values['X']=2.
        ext=rt.Structure(('XYZWPREXT',));ext.values.update(runtime_pose().values)
        for value in (bad,matrix,ext):
            with self.subTest(kind=value.spec),self.assertRaises(rt.KarelRuntimeError):rt.frame_transform(vector((1,2,3)),value)

    def test_frame_value_axis_and_conversion_remain_pose_only(self):
        for operation in (lambda:rt.frame_value(vector((1,2,3))),lambda:rt.position_axis('APPROACH',vector((1,2,3))),lambda:rt.convert_position(('POSITION',),vector((1,2,3)))):
            with self.assertRaises(rt.KarelRuntimeError):operation()

    def test_strict_runtime_guards_remain(self):
        with rt._numeric_scope('strict'):
            for operation in (lambda:rt.frame_inverse(vector((1,2,3))),lambda:rt.frame_transform(vector((1,2,3)),runtime_pose())):
                with self.assertRaises(rt.KarelRuntimeError):operation()


class VectorPointFrameTests(unittest.TestCase):
    def test_pose_origin_and_two_vector_axis_points(self):
        values=execute('b=FRAME(a,VEC(30,20,30),VEC(10,40,30))')
        self.assertEqual([values['B'][field] for field in ('X','Y','Z','W','P','R')],[10.,20.,30.,0.,0.,0.])
        self.assertEqual(values['B']['CONFIG_DATA'],values['A']['CONFIG_DATA'])

    def test_three_vector_points_with_explicit_fourth_pose_origin(self):
        values=execute('b=FRAME(VEC(0,0,0),VEC(0,20,0),VEC(-20,0,0),a)')
        self.assertEqual([values['B'][field] for field in ('X','Y','Z','W','P','R')],[10.,20.,30.,0.,0.,90.])

    def test_position_origin_keeps_position_representation(self):
        values=execute('p=FRAME(p,VEC(30,20,30),VEC(10,40,30))')
        self.assertEqual(values['P']['LOCATION'],dict(X=10.,Y=20.,Z=30.))
        self.assertEqual(values['P']['NORMAL'],dict(X=1.,Y=0.,Z=0.))

    def test_extended_origin_retains_external_axes_and_configuration(self):
        values=execute('e.ext1=7 e.ext2=-8 e.ext3=9 e=FRAME(VEC(0,0,0),VEC(20,0,0),VEC(0,20,0),e)')
        self.assertEqual([values['E'][field] for field in ('X','Y','Z','EXT1','EXT2','EXT3')],[10.,20.,30.,7.,-8.,9.])

    def test_nonorigin_pose_representation_precedence_is_unchanged(self):
        values=execute('p=POS(30,20,30,0,0,0,cfg) p=FRAME(a,p,VEC(10,40,30))')
        self.assertEqual(values['P']['LOCATION'],dict(X=10.,Y=20.,Z=30.))

    def test_all_vector_frame_has_no_implicit_config(self):
        for expression in ('FRAME(v,v,v)','FRAME(v,a,a)','FRAME(v,v,v,v)','FRAME(a,v,v,v)'):
            with self.subTest(expression=expression),self.assertRaises(TranslationError):compile_program(SETUP+'b='+expression,decl=DECL)

    def test_runtime_all_vector_or_vector_origin_is_rejected(self):
        with rt._numeric_scope('pythonic'):
            for points in ([vector((0,0,0)),vector((20,0,0)),vector((0,20,0))],
                [runtime_pose(),vector((20,0,0)),vector((0,20,0)),vector((0,0,0))]):
                with self.assertRaisesRegex(rt.KarelRuntimeError,'origin.*CONFIG'):rt.frame_from_points(points)

    def test_existing_spacing_thresholds_apply_to_vector_points(self):
        for x,y in ((9,20),(20,9),(0,20),(20,0)):
            with self.subTest(x=x,y=y):
                p,_=compile_program(SETUP+f'b=FRAME(a,VEC({10+x},20,30),VEC(10,{20+y},30))',decl=DECL)
                with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_partial_vector_point_leaves_previous_pose_unchanged(self):
        p,_=compile_program(SETUP+'b=a b.x=77 b=FRAME(a,w,VEC(10,40,30))',decl=DECL)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B']['X'],77.)

    def test_unused_pose_origin_orientation_and_config_still_complete(self):
        with rt._numeric_scope('pythonic'):
            for field in ('W','CONFIG_DATA'):
                origin=runtime_pose();origin.values[field]=rt.UNINITIALIZED
                with self.assertRaises(rt.KarelRuntimeError):rt.frame_from_points([vector((0,0,0)),vector((20,0,0)),vector((0,20,0)),origin])

    def test_config_and_geometry_results_are_independent(self):
        values=execute('b=FRAME(a,VEC(30,20,30),VEC(10,40,30)) a.x=99 a.config_data.cfg_left=NOT a.config_data.cfg_left')
        self.assertEqual(values['B']['X'],10.);self.assertNotEqual(values['B']['CONFIG_DATA']['CFG_LEFT'],values['A']['CONFIG_DATA']['CFG_LEFT'])


class VectorTranslationSourceTests(unittest.TestCase):
    def test_colon_result_type_follows_right_representation(self):
        values=execute('w=v:v b=v:a p=v:p e=v:e')
        self.assertEqual(values['W'],dict(X=4.,Y=6.,Z=8.))
        self.assertEqual([values['B'][field] for field in ('X','Y','Z','R')],[12.,23.,34.,90.])
        self.assertEqual(values['P']['LOCATION'],dict(X=12.,Y=23.,Z=34.));self.assertEqual(values['E']['X'],12.)

    def test_left_translation_and_right_local_point_are_distinct(self):
        values=execute('b=v:a res=a:v')
        self.assertEqual([values['B'][field] for field in ('X','Y','Z')],[12.,23.,34.]);self.assertEqual(values['RES'],dict(X=7.,Y=22.,Z=34.))

    def test_inverse_vector_composes_and_is_exact_routine_result(self):
        values=execute('res=negate(INV(v))',routines='ROUTINE negate(value:VECTOR):VECTOR BEGIN value.x=99 RETURN value END negate')
        self.assertEqual(values['V'],dict(X=2.,Y=3.,Z=4.));self.assertEqual(values['RES'],dict(X=99.,Y=-3.,Z=-4.))

    def test_computed_vector_operands_and_result_field_arguments(self):
        values=execute('take(INV(v+v).x) res=(INV(v):v):VEC(1,2,3)',routines='ROUTINE take(x:REAL) BEGIN value=x END take')
        self.assertEqual(values['VALUE'],-4.);self.assertEqual(values['RES'],dict(X=1.,Y=2.,Z=3.))

    def test_frame_computed_point_result_field_has_exact_real_type(self):
        values=execute('take(FRAME(a,VEC(30,20,30)+VEC(0,0,0),VEC(10,40,30)).x)',routines='ROUTINE take(x:REAL) BEGIN value=x END take')
        self.assertEqual(values['VALUE'],10.)

    def test_named_aliases_array_and_record_points(self):
        values=execute('points[1]=VEC(30,20,30) rec.point=VEC(10,40,30) b=FRAME(a,points[1],rec.point)',
            decl=DECL+' points:ARRAY[1] OF VECTOR rec:row_t',prefix='TYPE row_t=STRUCTURE point:VECTOR ENDSTRUCTURE')
        self.assertEqual(values['B']['R'],0.)

    def test_existing_destination_component_reference_survives_replacement(self):
        values=execute('replace(b.x)',routines='ROUTINE replace(alias:REAL) BEGIN b=v:a alias=99 END replace')
        self.assertEqual([values['B'][field] for field in ('X','Y','Z')],[99.,23.,34.])

    def test_no_implicit_vector_pose_assignment_or_return(self):
        for routines,body in [('', 'a=INV(v)'),('ROUTINE wrong:POSITION BEGIN RETURN INV(v) END wrong','p=wrong()'),
            ('ROUTINE take(x:VECTOR) BEGIN END take','take(v:a)')]:
            with self.subTest(body=body),self.assertRaises(TranslationError):compile_program(SETUP+body,decl=DECL,routines=routines)

    def test_approach_and_orient_do_not_gain_vector_pose_inputs(self):
        for operation in ('APPROACH','ORIENT'):
            with self.subTest(operation=operation),self.assertRaises(TranslationError):compile_program(SETUP+'res='+operation+'(v)',decl=DECL)

    def test_legacy_strict_restrictions_remain(self):
        for expression in ('v:a','INV(v)','FRAME(a,v,v)'):
            with self.subTest(expression=expression),self.assertRaises(TranslationError):legacy_translate('PROGRAM T VAR a:XYZWPR v:VECTOR BEGIN a='+expression+' END T')

    def test_source_project_linked_vector_result_and_pose_interface(self):
        main=source('MAIN',SETUP+'b=point():a',decl=DECL,routines='ROUTINE point:VECTOR FROM LIB')
        library=source('LIB','',routines='ROUTINE point:VECTOR BEGIN RETURN VEC(2,3,4) END point')
        values=translate_project({'main':main,'lib':library}).instantiate().run('MAIN')['MAIN']['values']
        self.assertEqual([values['B'][field] for field in ('X','Y','Z')],[12.,23.,34.])

    def test_reports_capture_one_site_per_computed_result(self):
        p,result=compile_program(SETUP+'take(INV(v).x) take((v:a).x) take(FRAME(a,VEC(30,20,30),VEC(10,40,30)).x)',decl=DECL,
            routines='ROUTINE take(x:REAL) BEGIN value=x END take');p.run()
        uses=result.report['frame_operations'];self.assertEqual([row['operation'] for row in uses],['INV',':','FRAME'])
        self.assertEqual([row['result_type'] for row in uses],['VECTOR','XYZWPR','XYZWPR'])
        self.assertTrue(all(row['evaluated_once'] and row['operands_copied'] for row in uses))


class VectorTranslationOrderTests(unittest.TestCase):
    def test_colon_operands_evaluate_once_left_to_right(self):
        values=execute("trace='' calls=0 b=left_value():right_value()",routines="ROUTINE left_value:VECTOR BEGIN trace=trace+'L' calls=calls+1 RETURN v END left_value ROUTINE right_value:XYZWPR BEGIN trace=trace+'R' calls=calls+1 RETURN a END right_value")
        self.assertEqual((values['TRACE'],values['CALLS'],values['B']['X']),('LR',2,12.))

    def test_later_pose_function_cannot_change_captured_left_translation(self):
        values=execute('b=v:touch()',routines='ROUTINE touch:XYZWPR BEGIN v.x=500 RETURN a END touch')
        self.assertEqual((values['V']['X'],values['B']['X']),(500.,12.))

    def test_invalid_left_vector_skips_right_side_effects(self):
        p,_=compile_program(SETUP+'calls=0 b=w:touch()',decl=DECL,routines='ROUTINE touch:XYZWPR BEGIN calls=calls+1 RETURN a END touch')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['CALLS'],0)

    def test_invalid_right_pose_keeps_left_effect_without_assignment(self):
        p,_=compile_program(SETUP+'calls=0 b=a b.x=77 b=left_value():missing',decl=DECL+' missing:XYZWPR',
            routines='ROUTINE left_value:VECTOR BEGIN calls=calls+1 RETURN v END left_value')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['CALLS'],p.snapshot()['B']['X']),(1,77.))

    def test_failed_addition_skips_assignment_target_index(self):
        p,_=compile_program(SETUP+'calls=0 a.x=1e308 v=VEC(1e308,0,0) points[indexer()]=v:a',decl=DECL+' points:ARRAY[1] OF XYZWPR',
            routines='ROUTINE indexer:INTEGER BEGIN calls=calls+1 RETURN 1 END indexer')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['CALLS'],0)

    def test_frame_vector_point_captured_before_next_function(self):
        values=execute('v=VEC(0,0,0) w=VEC(20,0,0) b=FRAME(v,point(),VEC(0,20,0),a)',
            routines='ROUTINE point:VECTOR BEGIN v.x=500 RETURN w END point')
        self.assertEqual((values['V']['X'],values['B']['X'],values['B']['R']),(500.,10.,0.))

    def test_invalid_vector_point_skips_later_argument_function(self):
        p,_=compile_program(SETUP+'calls=0 b=FRAME(a,w,point())',decl=DECL,
            routines='ROUTINE point:VECTOR BEGIN calls=calls+1 RETURN VEC(10,40,30) END point')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['CALLS'],0)

    def test_frame_geometry_failure_keeps_argument_effect_and_old_destination(self):
        p,_=compile_program(SETUP+'calls=0 b=a b.x=77 b=FRAME(a,VEC(11,20,30),point())',decl=DECL,
            routines='ROUTINE point:VECTOR BEGIN calls=calls+1 RETURN VEC(10,40,30) END point')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['CALLS'],p.snapshot()['B']['X']),(1,77.))

    def test_active_for_counter_effects_remain_transitively_blocked(self):
        for expression,kind in [('v:point()','XYZWPR'),('INV(point())','VECTOR'),('FRAME(a,point(),VEC(10,40,30))','VECTOR')]:
            body='FOR n=1 TO 2 DO '+('b=' if kind=='XYZWPR' or expression.startswith('FRAME') else 'res=')+expression+' ENDFOR'
            routines='ROUTINE point:'+kind+' BEGIN n=n+1 RETURN '+('a' if kind=='XYZWPR' else 'v')+' END point'
            with self.subTest(expression=expression),self.assertRaises(TranslationError):compile_program(SETUP+body,decl=DECL,routines=routines)

    def test_operand_abort_unwinds_routine_frames(self):
        p,_=compile_program(SETUP+'b=v:point()',decl=DECL,routines='ROUTINE point:XYZWPR BEGIN ABORT RETURN a END point')
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual((p._state.call_depth,p._state.local_frames),(0,[]))


class JointTranslationFrameTests(unittest.TestCase):
    def test_vector_left_joint_uses_explicit_forward_geometry(self):
        values=execute('j=CURJPOS(0,0) e=v:j',decl=DECL+' j:JOINTPOS',context=model_context((0.,0.)))
        self.assertEqual([values['E'][field] for field in ('X','Y','Z')],[202.,3.,4.])

    def test_joint_origin_supplies_frame_config_and_metadata(self):
        values=execute('j=CURJPOS(0,0) e=FRAME(j,VEC(220,0,0),VEC(200,20,0))',decl=DECL+' j:JOINTPOS',context=model_context((0.,0.)))
        self.assertEqual([values['E'][field] for field in ('X','Y','Z','W','P','R')],[200.,0.,0.,0.,0.,0.])

    def test_fourth_joint_origin_supports_three_vector_points(self):
        values=execute('j=CURJPOS(0,0) e=FRAME(VEC(0,0,0),VEC(20,0,0),VEC(0,20,0),j)',decl=DECL+' j:JOINTPOS',context=model_context((0.,0.)))
        self.assertEqual([values['E'][field] for field in ('X','Y','Z')],[200.,0.,0.])

    def test_model_forward_callback_runs_once_without_inverse_discovery(self):
        seen=[]
        def forward(value,frame,tool,selector):
            seen.append(value.values[:]);pose=runtime_position((0,0,90),(5,6,7));return pose,pose.values['CONFIG_DATA'],[7.,8.,9.]
        ctx=callback_context(forward=forward);p,result=compile_program(SETUP+'e=v:j',decl=DECL+' j:JOINTPOS2',context=ctx)
        p._state.values['J']=joint([10.,20.]);values=p.run()
        self.assertEqual([values['E'][field] for field in ('X','Y','Z','R','EXT1','EXT2','EXT3')],[7.,9.,11.,90.,7.,8.,9.])
        self.assertEqual(seen,[[10.,20.]]);self.assertEqual(len(result.report['joint_geometry']),1)
        self.assertEqual(len([row for row in p.service_requests if row['operation']=='JOINT_GEOMETRY']),1)

    def test_bad_vector_prevents_joint_forward_callback(self):
        seen=[]
        def forward(*args):seen.append(True);raise AssertionError('must not run')
        ctx=callback_context(forward=forward);p,_=compile_program(SETUP+'e=w:j',decl=DECL+' j:JOINTPOS2',context=ctx)
        p._state.values['J']=joint([10.,20.])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(seen,[])

    def test_missing_robot_context_does_not_fabricate_joint_origin(self):
        p,_=compile_program(SETUP+'e=FRAME(VEC(0,0,0),VEC(20,0,0),VEC(0,20,0),j)',decl=DECL+' j:JOINTPOS2')
        p._state.values['J']=joint([0.,0.])
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_joint_geometry_does_not_change_current_robot_state(self):
        ctx=model_context((0.,0.));before=deepcopy(ctx.robot.to_config())
        execute('j=CURJPOS(0,0) e=v:j',decl=DECL+' j:JOINTPOS',context=ctx)
        self.assertEqual(ctx.robot.to_config(),before)


if __name__=='__main__':unittest.main()
