"""POSITION geometry, independent rotation evidence and expression ownership."""
import json
import math
from pathlib import Path
import random
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_frame_transforms import CONFIG, INIT, quaternion, quaternion_product, rotate, runtime_pose
from tests.test_position_conversions import runtime_position


DECLARATIONS='cfg: CONFIG a,b: XYZWPR p,q,r,s: POSITION seen: REAL total,i: INTEGER trace: STRING[20]'


def compile_program(body, *, declarations=DECLARATIONS, routines='', types='', translator=translate, labelled=False):
    source=f'PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n'+('marker::\n' if labelled else '')+INIT+'\n'+body+'\nEND T'
    result=translator(source,filename='position_geometry.kl'); ns={'__name__':'position_geometry_test'}
    exec(result.python_source,ns)
    return ns['Program'](),result


def execute(body, **options): return compile_program(body,**options)[0].run()


class PositionGeometryMathTests(unittest.TestCase):
    def assert_rotation(self, result, expected):
        for name,basis in zip(('NORMAL','ORIENT','APPROACH'),((1,0,0),(0,1,0),(0,0,1))):
            for axis,value in zip(('X','Y','Z'),rotate(expected,basis)):
                self.assertAlmostEqual(result.values[name].values[axis],value,places=12)

    def test_position_composition(self):
        state=execute('p=POS(10,20,30,0,0,90,cfg) q=POS(2,3,4,0,0,0,cfg) r=p:q')
        self.assertEqual(state['R']['LOCATION'],dict(X=7,Y=22,Z=34))
        self.assertEqual(state['R']['NORMAL'],dict(X=0,Y=1,Z=0))

    def test_mixed_composition_both_orders(self):
        for expression in ('p:a','a:p'):
            with self.subTest(expression=expression):
                state=execute('p=POS(1,0,0,0,0,0,cfg) a=POS(2,0,0,0,0,0,cfg) r='+expression)
                self.assertEqual(state['R']['LOCATION'],dict(X=3,Y=0,Z=0))

    def test_general_mixed_compositions_match_quaternions(self):
        rng=random.Random(721)
        for _ in range(60):
            angles=[tuple(rng.uniform(-180,180) for _ in range(3)) for _ in range(2)]
            locations=[tuple(rng.uniform(-100,100) for _ in range(3)) for _ in range(2)]
            qa,qb=map(quaternion,angles); expected=quaternion_product(qa,qb)
            translation=tuple(a+b for a,b in zip(locations[0],rotate(qa,locations[1])))
            for kinds in ((True,True),(True,False),(False,True)):
                values=[runtime_position(angle,location) if matrix else runtime_pose((*location,*angle))
                        for matrix,angle,location in zip(kinds,angles,locations)]
                with self.subTest(kinds=kinds,angles=angles),rt._numeric_scope('pythonic'):
                    result=rt.frame_transform(*values)
                    self.assertEqual(result.spec,('POSITION',)); self.assert_rotation(result,expected)
                    for axis,value in zip(('X','Y','Z'),translation):
                        self.assertAlmostEqual(result.values['LOCATION'].values[axis],value,places=10)

    def test_inverse_matches_quaternions_at_and_near_gimbal_lock(self):
        for angle in ((12,34,56),(40,90,20),(40,-90,20),(40,90-1e-13,20)):
            q=quaternion(angle); inverse=(q[0],-q[1],-q[2],-q[3])
            with self.subTest(angle=angle),rt._numeric_scope('pythonic'):
                result=rt.frame_inverse(runtime_position(angle,(4,-7,9)))
                self.assert_rotation(result,inverse)
                for axis,value in zip(('X','Y','Z'),rotate(inverse,(-4,7,-9))):
                    self.assertAlmostEqual(result.values['LOCATION'].values[axis],value,places=12)

    def test_position_result_keeps_small_matrix_terms_without_euler_round_trip(self):
        source=runtime_position((40,90-1e-13,20))
        with rt._numeric_scope('pythonic'):
            result=rt.frame_transform(source,runtime_pose())
        for field in ('NORMAL','ORIENT','APPROACH'):
            self.assertEqual(result.values[field].values,source.values[field].values)
        self.assertNotEqual(result.values['NORMAL'].values['X'],0)

    def test_inverse_recovers_local_position(self):
        state=execute('p=POS(10,20,30,0,0,90,cfg) q=POS(2,3,4,0,0,0,cfg) r=INV(p):(p:q)')
        self.assertEqual(state['R'],state['Q'])

    def test_frame_all_position_points(self):
        state=execute('p=POS(10,20,30,0,0,0,cfg) q=POS(10,40,30,0,0,0,cfg) r=POS(-10,20,30,0,0,0,cfg) s=FRAME(p,q,r)')
        self.assertEqual(state['S']['LOCATION'],state['P']['LOCATION'])
        self.assertEqual(state['S']['NORMAL'],dict(X=0,Y=1,Z=0))
        self.assertEqual(state['S']['ORIENT'],dict(X=-1,Y=0,Z=0))
        self.assertEqual(state['S']['APPROACH'],dict(X=0,Y=0,Z=1))

    def test_each_mixed_frame_argument_selects_position_result(self):
        points=((0,0,0),(20,0,0),(0,20,0),(7,8,9))
        for count in (3,4):
            for index in range(count):
                values=[runtime_position((15,30,45),point) if i==index else runtime_pose((*point,15,30,45))
                        for i,point in enumerate(points[:count])]
                with self.subTest(count=count,index=index),rt._numeric_scope('pythonic'):
                    result=rt.frame_from_points(values)
                    self.assertEqual(result.spec,('POSITION',)); self.assert_rotation(result,(1,0,0,0))
                    self.assertEqual(tuple(result.values['LOCATION'].values.values()),points[3 if count==4 else 0])

    def test_frame_fourth_origin_and_config(self):
        state=execute('p=POS(0,0,0,0,0,0,cfg) q=POS(20,0,0,0,0,0,cfg) r=POS(0,20,0,0,0,0,cfg) cfg.cfg_left=FALSE a=POS(7,8,9,30,40,50,cfg) s=FRAME(p,q,r,a)')
        self.assertEqual(state['S']['LOCATION'],dict(X=7,Y=8,Z=9))
        self.assertFalse(state['S']['CONFIG_DATA']['CFG_LEFT'])

    def test_oblique_frame_matches_independent_rotated_points(self):
        expected=quaternion((17,38,-59)); origin=(5,-7,11)
        locations=[origin]+[tuple(a+b for a,b in zip(origin,rotate(expected,basis)))
                            for basis in ((20,0,0),(0,20,0))]
        with rt._numeric_scope('pythonic'):
            result=rt.frame_from_points([runtime_position(location=point) for point in locations])
        self.assert_rotation(result,expected)
        self.assertEqual(tuple(result.values['LOCATION'].values.values()),origin)

    def test_configuration_copies_stay_independent(self):
        state=execute('p=POS(0,0,0,0,0,0,cfg) cfg.cfg_left=FALSE q=POS(1,0,0,0,0,0,cfg) r=p:q s=INV(q) q.config_data.cfg_left=TRUE')
        self.assertFalse(state['R']['CONFIG_DATA']['CFG_LEFT']); self.assertFalse(state['S']['CONFIG_DATA']['CFG_LEFT'])

    def test_xyzwpr_only_results_retain_layout(self):
        with rt._numeric_scope('pythonic'):
            for value in (rt.frame_transform(runtime_pose(),runtime_pose()),rt.frame_inverse(runtime_pose()),
                          rt.frame_from_points([runtime_pose(),runtime_pose((20,0,0,0,0,0)),runtime_pose((0,20,0,0,0,0))])):
                self.assertEqual(value.spec,('XYZWPR',)); self.assertIn('W',value.values)


class PositionGeometryIntegrationTests(unittest.TestCase):
    def test_chain_and_result_fields(self):
        state=execute('p=POS(1,0,0,0,0,0,cfg) a=POS(2,0,0,0,0,0,cfg) r=a:p:a seen=INV(r).location.x')
        self.assertEqual((state['R']['LOCATION']['X'],state['SEEN']),(5,-5))

    def test_mixed_frame_inferred_fields_and_report_types(self):
        _,result=compile_program('p=POS(0,0,0,0,0,0,cfg) a=POS(20,0,0,0,0,0,cfg) b=POS(0,20,0,0,0,0,cfg) take(FRAME(p,a,b).location.x) take((p:a).location.x) take(INV(p).location.x)',
                                 routines='ROUTINE take(x: REAL) BEGIN seen=x END take')
        rows=result.report['frame_operations']
        self.assertEqual([row['operation'] for row in rows],['FRAME',':','INV'])
        self.assertEqual([row['operand_types'] for row in rows],[['POSITION','XYZWPR','XYZWPR'],['POSITION','XYZWPR'],['POSITION']])
        self.assertTrue(all(row['result_type']=='POSITION' for row in rows)); json.dumps(result.report)

    def test_position_function_result_and_private_argument(self):
        state=execute('p=POS(1,0,0,0,0,0,cfg) r=make(p:p)',
                      routines='ROUTINE make(v: POSITION): POSITION BEGIN v.location.x=9 RETURN INV(v) END make')
        self.assertEqual((state['R']['LOCATION']['X'],state['P']['LOCATION']['X']),(-9,1))

    def test_grouped_result_orientation_is_private_writable_vector(self):
        state=execute('p=POS(1,0,0,0,0,0,cfg) take((INV(p).normal))',
                      routines='ROUTINE take(v: VECTOR) BEGIN v.x=9 seen=v.x END take')
        self.assertEqual((state['SEEN'],state['P']['NORMAL']['X']),(9,1))

    def test_result_location_argument_is_private(self):
        state=execute('p=POS(1,0,0,0,0,0,cfg) take(INV(p).location.x)',
                      routines='ROUTINE take(x: REAL) BEGIN x=9 seen=x END take')
        self.assertEqual((state['SEEN'],state['P']['LOCATION']['X']),(9,1))

    def test_left_captured_before_right_mutation(self):
        state=execute('p=POS(10,0,0,0,0,0,cfg) q=POS(1,0,0,0,0,0,cfg) r=p:touch()',
                      routines='ROUTINE touch: POSITION BEGIN p.location.x=99 RETURN q END touch')
        self.assertEqual((state['R']['LOCATION']['X'],state['P']['LOCATION']['X']),(11,99))

    def test_point_captured_before_later_mutation(self):
        state=execute('p=POS(0,0,0,0,0,0,cfg) q=POS(20,0,0,0,0,0,cfg) r=POS(0,20,0,0,0,0,cfg) s=FRAME(p,touch(),r)',
                      routines='ROUTINE touch: POSITION BEGIN p.location.x=99 RETURN q END touch')
        self.assertEqual((state['S']['LOCATION']['X'],state['P']['LOCATION']['X']),(0,99))

    def test_calls_run_once_in_order(self):
        state=execute("trace='' p=make(1):make(2)",
                      routines="ROUTINE make(n: INTEGER): POSITION VAR value: POSITION BEGIN trace=trace+CHR(64+n) value=POS(n,0,0,0,0,0,cfg) RETURN value END make")
        self.assertEqual((state['TRACE'],state['P']['LOCATION']['X']),('AB',3))

    def test_frame_calls_run_once_in_order(self):
        state=execute("trace='' p=FRAME(make(1),make(2),make(3),make(4))",
                      routines="ROUTINE make(n: INTEGER): POSITION VAR value: POSITION BEGIN trace=trace+CHR(64+n) value=POS(0,0,0,0,0,0,cfg) IF n=2 THEN value.location.x=20 ENDIF IF n=3 THEN value.location.y=20 ENDIF RETURN value END make")
        self.assertEqual(state['TRACE'],'ABCD')

    def test_assignment_result_precedes_target_index_mutation(self):
        state=execute('p=POS(1,0,0,0,0,0,cfg) items[pick()]=p:p',declarations=DECLARATIONS+' items: ARRAY[1] OF POSITION',
                      routines='ROUTINE pick: INTEGER BEGIN p.location.x=99 RETURN 1 END pick')
        self.assertEqual((state['ITEMS'][0]['LOCATION']['X'],state['P']['LOCATION']['X']),(2,99))

    def test_replacement_preserves_location_and_config_references(self):
        state=execute('p=POS(1,0,0,0,0,0,cfg) change(p,p.location.x,p.config_data)',
                      routines='ROUTINE change(v: POSITION; x: REAL; c: CONFIG) BEGIN v=v:v seen=x x=9 c.cfg_left=FALSE END change')
        self.assertEqual((state['SEEN'],state['P']['LOCATION']['X']),(2,9)); self.assertFalse(state['P']['CONFIG_DATA']['CFG_LEFT'])

    def test_aliases_records_and_arrays(self):
        state=execute('p=POS(1,0,0,0,0,0,cfg) box.pose=p:p items[1]=INV(box.pose)',
                      types='TYPE matrix_t=POSITION box_t=STRUCTURE pose: matrix_t ENDSTRUCTURE',
                      declarations=DECLARATIONS+' box: box_t items: ARRAY[1] OF matrix_t')
        self.assertEqual(state['ITEMS'][0]['LOCATION']['X'],-2)

    def test_label_dispatch_for_and_cleanup(self):
        p,_=compile_program('p=POS(1,0,0,0,0,0,cfg) FOR i=1 TO 2 DO q=INV(p:p) ENDFOR',labelled=True)
        state=p.run(); self.assertEqual(state['Q']['LOCATION']['X'],-2)
        self.assertEqual((state['I'],p._state.local_frames,p._state.call_depth),({'uninitialized':True},[],0))

    def test_user_routines_still_override_geometry_fallbacks(self):
        state=execute('total=INV(7)+FRAME(2)',routines='ROUTINE INV(x: INTEGER): INTEGER BEGIN RETURN x+1 END INV ROUTINE FRAME(x: INTEGER): INTEGER BEGIN RETURN x END FRAME')
        self.assertEqual(state['TOTAL'],10)


class PositionGeometryGuardTests(unittest.TestCase):
    def reject(self, body, code='E_TYPE', **options):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**options)
        self.assertEqual(caught.exception.code,code)

    def test_bare_result_orientation_reference_stays_protected(self):
        self.reject('take(INV(p).normal)','E_POSITION_READ_ONLY_ARG',routines='ROUTINE take(v: VECTOR) BEGIN END take')

    def test_destination_orientation_stays_protected(self):
        self.reject('p.normal.x=INV(q).normal.x','E_POSITION_READ_ONLY')

    def test_other_operand_types_and_exact_vector_pose_interfaces_stay_blocked(self):
        for kind in ('CONFIG','INTEGER'):
            for expression in ('p:x','x:p','INV(x)','FRAME(p,q,x)'):
                with self.subTest(kind=kind,expression=expression):
                    self.reject('r='+expression,declarations=DECLARATIONS+' x: '+kind)
        for expression in ('p:x','INV(x)'):
            self.reject('r='+expression,declarations=DECLARATIONS+' x:VECTOR')
        for expression in ('x:p','FRAME(p,q,x)'):
            compile_program('r='+expression,declarations=DECLARATIONS+' x:VECTOR')

    def test_cartesian_geometry_results_convert_at_routine_boundaries(self):
        state=execute('p=POS(1,0,0,0,0,0,cfg) take(p:p)',routines='ROUTINE take(v: XYZWPR) BEGIN seen=v.x v.x=99 END take')
        self.assertEqual((state['SEEN'],state['P']['LOCATION']['X']),(2.,1.))
        routine='ROUTINE make: POSITION BEGIN RETURN INV(a) END make'
        self.assertEqual(execute('a=POS(2,0,0,0,0,0,cfg) q=make()',routines=routine)['Q']['LOCATION']['X'],-2.)
        with self.assertRaises(TranslationError): compile_program('take(p:p)',routines='ROUTINE take(v: XYZWPR) BEGIN END take',translator=legacy_translate)
        with self.assertRaises(TranslationError): compile_program('q=make()',routines=routine,translator=legacy_translate)

    def test_legacy_internal_geometry_guards_retained(self):
        for expression in ('p:p','INV(p)','FRAME(p,q,r)'):
            with self.subTest(expression=expression),self.assertRaises(TranslationError):
                compile_program('s='+expression,translator=legacy_translate)

    def test_for_counter_transitive_effect_stays_blocked(self):
        self.reject('FOR i=1 TO 2 DO r=p:touch() ENDFOR','E_FOR_COUNTER',
                    routines='ROUTINE touch: POSITION BEGIN i=9 RETURN q END touch')

    def test_invalid_left_stops_later_operand_effects(self):
        for invalid in (rt.Structure(('POSITION',)),runtime_position()):
            if invalid.values['NORMAL'].values['X'] is not rt.UNINITIALIZED: invalid.values['NORMAL'].values['X']=2
            p,_=compile_program("trace='' r=p:touch()",routines="ROUTINE touch: POSITION BEGIN trace='touched' RETURN q END touch")
            p._state.values['P']=invalid
            with self.subTest(invalid=invalid),self.assertRaises(rt.KarelRuntimeError): p.run()
            self.assertEqual(p.snapshot()['TRACE'],'')

    def test_invalid_point_stops_later_argument_effects(self):
        p,_=compile_program("trace='' s=FRAME(p,touch(),r)",routines="ROUTINE touch: POSITION BEGIN trace='touched' RETURN q END touch")
        invalid=runtime_position(); invalid.values['NORMAL'].values['X']=2; p._state.values['P']=invalid
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TRACE'],'')

    def test_geometry_failure_retains_all_captured_effects(self):
        p,_=compile_program("trace='' s.location.x=7 s=FRAME(make(1),make(2),make(3))",
                            routines="ROUTINE make(n: INTEGER): POSITION VAR value: POSITION BEGIN trace=trace+CHR(64+n) value=POS(n,0,0,0,0,0,cfg) RETURN value END make")
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['TRACE'],p.snapshot()['S']['LOCATION']['X']),('ABC',7))

    def test_failed_operation_skips_target_index_effect(self):
        p,_=compile_program("trace='' items[pick()]=INV(p)",declarations=DECLARATIONS+' items: ARRAY[1] OF POSITION',
                            routines="ROUTINE pick: INTEGER BEGIN trace='picked' RETURN 1 END pick")
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TRACE'],'')

    def test_declared_pose_type_checked_before_later_effects(self):
        p,_=compile_program("trace='' r=p:touch()",routines="ROUTINE touch: POSITION BEGIN trace='touched' RETURN q END touch")
        p._state.values['P']=runtime_pose()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'declared pose type'): p.run()
        self.assertEqual(p.snapshot()['TRACE'],'')

    def test_invalid_matrices_rejected_for_every_operation(self):
        for fault,message in (('unit','unit'),('skew','orthogonal'),('reflection','right-handed')):
            value=runtime_position()
            if fault=='unit': value.values['NORMAL'].values['X']=2
            elif fault=='skew': value.values['ORIENT'].values.update(X=1,Y=0,Z=0)
            else: value.values['ORIENT'].values['Y']=-1
            for operation in (lambda:rt.frame_inverse(value),lambda:rt.frame_transform(value,runtime_pose()),
                              lambda:rt.frame_from_points([value,runtime_pose((20,0,0,0,0,0)),runtime_pose((0,20,0,0,0,0))])):
                with self.subTest(fault=fault,operation=operation),rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,message): operation()

    def test_incomplete_and_malformed_values_rejected(self):
        for fault in ('unknown','extra','config','nonfinite'):
            value=runtime_position()
            if fault=='unknown': value.values['APPROACH'].values['Z']=rt.UNINITIALIZED
            elif fault=='extra': value.values['EXTRA']=0
            elif fault=='config': value.values['CONFIG_DATA'].values['CFG_TURN_NO1']=8
            else: value.values['LOCATION'].values['X']=math.inf
            with self.subTest(fault=fault),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.frame_inverse(value)

    def test_frame_spacing_boundaries_retained(self):
        for points in (((0,0,0),(9.999,0,0),(0,20,0)),((0,0,0),(20,0,0),(0,9.999,0))):
            with self.subTest(points=points),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):
                rt.frame_from_points([runtime_position(location=point) for point in points])
        with rt._numeric_scope('pythonic'):
            rt.frame_from_points([runtime_position(location=point) for point in ((0,0,0),(10,0,0),(0,10,0))])

    def test_accumulated_matrix_deviation_is_rejected_without_repair(self):
        value=runtime_position(); value.values['ORIENT'].values['X']=6e-10
        with rt._numeric_scope('pythonic'):
            captured=rt.frame_value(value)
            self.assertEqual(captured.values['ORIENT'].values['X'],6e-10)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'orthogonal'):
                rt.frame_transform(value,value)
        self.assertEqual(value.values['ORIENT'].values['X'],6e-10)

    def test_results_retain_read_only_orientation_and_do_not_mutate_inputs(self):
        source=runtime_position((10,20,30)); before=rt.snapshot_value(source)
        with rt._numeric_scope('pythonic'):
            results=[rt.frame_inverse(source),rt.frame_transform(source,runtime_pose()),
                     rt.frame_from_points([source,runtime_position(location=(21,2,3)),runtime_position(location=(1,22,3))])]
        self.assertEqual(rt.snapshot_value(source),before)
        for value in results:
            self.assertTrue(all(value.values[name].read_only for name in rt.POSITION_READ_ONLY_FIELDS))
            self.assertIsNot(value.values['LOCATION'],source.values['LOCATION'])
            self.assertIsNot(value.values['CONFIG_DATA'],source.values['CONFIG_DATA'])

    def test_error_cleans_local_frames_and_active_counter(self):
        p,_=compile_program('FOR i=1 TO 2 DO fail ENDFOR',routines='ROUTINE fail BEGIN q=INV(p) END fail')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p._state.local_frames,p._state.call_depth,p.snapshot()['I']),([],0,{'uninitialized':True}))


class AuthoredPositionGeometryTests(unittest.TestCase):
    def test_complete_fixture_output_and_report(self):
        source=Path(__file__).resolve().parents[1]/'examples/pythonic_position_geometry.kl'
        result=translate(source.read_text(),filename=source.name); ns={'__name__':'position_geometry_fixture'}
        exec(result.python_source,ns); out=[]; p=ns['Program'](write=out.append)
        self.assertEqual(p.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(out,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual([row['operation'] for row in result.report['frame_operations']],['FRAME',':','INV',':'])
        self.assertTrue(all(row['result_type']=='POSITION' for row in result.report['frame_operations']))
        self.assertFalse(result.report['frame_policy']['controller_validated'])
        self.assertTrue(all(p._state.values['WORLD'].values[name].read_only for name in rt.POSITION_READ_ONLY_FIELDS))
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
