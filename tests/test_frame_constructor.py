"""Three/four-point frames, geometry thresholds and independent operand capture."""
import json
import math
from pathlib import Path
import random
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_frame_transforms import CONFIG, INIT, FIELDS, runtime_pose, quaternion, rotate


DECLARATIONS='cfg: CONFIG a,b,c,d,result: XYZWPR seen: REAL i,total: INTEGER trace: STRING[20]'
POINTS='a=POS(0,0,0,0,0,0,cfg) b=POS(20,0,0,0,0,0,cfg) c=POS(0,20,0,0,0,0,cfg)'


def compile_program(body,*,declarations=DECLARATIONS,types='',routines='',translator=translate,labelled=False):
    source=f'PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n'+('marker::\n' if labelled else '')+INIT+'\n'+body+'\nEND T'
    result=translator(source,filename='frame_constructor.kl'); ns={'__name__':'frame_constructor_test'}
    exec(result.python_source,ns); return ns['Program'](),result


def execute(body,**options): return compile_program(body,**options)[0].run()


class FrameConstructionMathTests(unittest.TestCase):
    def test_axis_aligned_basis(self):
        state=execute(POINTS+' result=FRAME(a,b,c)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[0,0,0,0,0,0])
    def test_shifted_origin(self):
        state=execute('a=POS(10,20,30,0,0,0,cfg) b=POS(30,20,30,0,0,0,cfg) c=POS(10,40,30,0,0,0,cfg) result=FRAME(a,b,c)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[10,20,30,0,0,0])
    def test_z_rotated_basis(self):
        state=execute('a=POS(10,20,30,0,0,0,cfg) b=POS(10,40,30,0,0,0,cfg) c=POS(-10,20,30,0,0,0,cfg) result=FRAME(a,b,c)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[10,20,30,0,0,90])
    def test_x_rotated_basis(self):
        state=execute('a=POS(0,0,0,0,0,0,cfg) b=POS(20,0,0,0,0,0,cfg) c=POS(0,0,20,0,0,0,cfg) result=FRAME(a,b,c)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[0,0,0,90,0,0])
    def test_negative_plane_half_selects_right_handed_basis(self):
        state=execute(POINTS+' c.y=-20 result=FRAME(a,b,c)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[0,0,0,-180,0,0])
    def test_skew_plane_point_keeps_orthogonal_y(self):
        state=execute(POINTS+' c.x=100 result=FRAME(a,b,c)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[0,0,0,0,0,0])
    def test_fourth_point_changes_origin_without_orientation(self):
        state=execute(POINTS+' d=POS(100,200,300,12,34,56,cfg) result=FRAME(a,b,c,d)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[100,200,300,0,0,0])
    def test_fourth_point_has_no_separation_requirement(self):
        state=execute(POINTS+' result=FRAME(a,b,c,a)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[0,0,0,0,0,0])
    def test_input_orientation_is_not_used_for_basis(self):
        state=execute(POINTS+' a.w=13 a.p=91 b.r=-77 c.w=29 result=FRAME(a,b,c)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[0,0,0,0,0,0])
    def test_spacing_boundaries_are_inclusive(self):
        state=execute(POINTS+' b.x=10 c.y=10 result=FRAME(a,b,c)')
        self.assertEqual(state['RESULT']['R'],0)
    def test_diagonal_spacing_uses_euclidean_distance(self):
        state=execute(POINTS+' b.x=6 b.y=8 c.x=0 c.y=0 c.z=10 result=FRAME(a,b,c)')
        self.assertAlmostEqual(state['RESULT']['R'],math.degrees(math.atan2(8,6)))
    def test_first_point_supplies_independent_configuration(self):
        state=execute(POINTS+' b.config_data.cfg_left=FALSE result=FRAME(a,b,c) a.config_data.cfg_left=FALSE')
        self.assertEqual(state['RESULT']['CONFIG_DATA'],CONFIG)
    def test_fourth_point_supplies_independent_configuration(self):
        state=execute(POINTS+' d=a d.config_data.cfg_left=FALSE result=FRAME(a,b,c,d) d.config_data.cfg_left=TRUE')
        self.assertFalse(state['RESULT']['CONFIG_DATA']['CFG_LEFT'])
    def test_rotated_frames_match_independent_quaternion_bases(self):
        rng=random.Random(7031)
        angles=[(40,90,20),(40,-90,20)]+[tuple(rng.uniform(-180,180) for _ in range(3)) for _ in range(80)]
        for angle in angles:
            q=quaternion(angle); origin=tuple(rng.uniform(-100,100) for _ in range(3))
            x=tuple(a+b for a,b in zip(origin,rotate(q,(50,0,0))))
            plane=tuple(a+b for a,b in zip(origin,rotate(q,(15,40,0))))
            with self.subTest(angle=angle),rt._numeric_scope('pythonic'):
                result=rt.frame_from_points([runtime_pose((*value,0,0,0)) for value in (origin,x,plane)])
                actual=quaternion(tuple(result.values[field] for field in ('W','P','R')))
                self.assertAlmostEqual(abs(sum(a*b for a,b in zip(q,actual))),1,places=12)
                self.assertEqual(tuple(result.values[field] for field in ('X','Y','Z')),origin)
    def test_large_finite_geometry_uses_stable_norms(self):
        with rt._numeric_scope('pythonic'):
            result=rt.frame_from_points([runtime_pose(),runtime_pose((1e300,0,0,0,0,0)),runtime_pose((0,1e300,0,0,0,0))])
        self.assertEqual([result.values[field] for field in FIELDS],[0,0,0,0,0,0])
    def test_constructor_composes_with_inverse_and_relative_operator(self):
        state=execute(POINTS+' a.x=10 b.x=30 c.x=10 result=INV(FRAME(a,b,c)):POS(12,3,4,0,0,0,cfg)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[2,3,4,0,0,0])


class FrameConstructorIntegrationTests(unittest.TestCase):
    def test_arguments_run_once_in_source_order(self):
        state=execute(POINTS+" trace='' result=FRAME(point(1),point(2),point(3))",
                      routines="ROUTINE point(n: INTEGER): XYZWPR BEGIN trace=trace+CHR(64+n) IF n=1 THEN RETURN a ELSE IF n=2 THEN RETURN b ELSE RETURN c ENDIF ENDIF END point")
        self.assertEqual(state['TRACE'],'ABC'); self.assertEqual(state['RESULT']['R'],0)
    def test_first_operand_is_captured_before_later_mutation(self):
        state=execute(POINTS+' result=FRAME(a,touch(),c)',routines='ROUTINE touch: XYZWPR BEGIN a.x=999 RETURN b END touch')
        self.assertEqual((state['RESULT']['X'],state['RESULT']['R'],state['A']['X']),(0,0,999))
    def test_second_operand_is_captured_before_third_mutation(self):
        state=execute(POINTS+' result=FRAME(a,b,touch())',routines='ROUTINE touch: XYZWPR BEGIN b.y=30 RETURN c END touch')
        self.assertEqual((state['RESULT']['R'],state['B']['Y']),(0,30))
    def test_third_operand_is_captured_before_fourth_mutation(self):
        state=execute(POINTS+' d=POS(100,200,300,0,0,0,cfg) result=FRAME(a,b,c,touch())',routines='ROUTINE touch: XYZWPR BEGIN c.z=20 RETURN d END touch')
        self.assertEqual((state['RESULT']['W'],state['RESULT']['X'],state['C']['Z']),(0,100,20))
    def test_invalid_operand_stops_later_argument_effects(self):
        p,_=compile_program("trace='' result=FRAME(a,touch(),c)",routines="ROUTINE touch: XYZWPR BEGIN trace='touched' RETURN b END touch")
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TRACE'],'')
    def test_geometry_failure_retains_prior_argument_effects_and_destination(self):
        p,_=compile_program(POINTS+" b.x=5 result=a result.x=7 trace='' result=FRAME(a,b,touch())",
                            routines="ROUTINE touch: XYZWPR BEGIN trace='C' RETURN c END touch")
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['TRACE'],p.snapshot()['RESULT']['X']),('C',7))
    def test_result_field_is_a_private_value_argument(self):
        state=execute(POINTS+' change(FRAME(a,b,c).x)',routines='ROUTINE change(x: REAL) BEGIN x=9 seen=x END change')
        self.assertEqual((state['SEEN'],state['A']['X']),(9,0))
    def test_frame_result_parameter_and_return(self):
        state=execute(POINTS+' result=change(FRAME(a,b,c))',routines='ROUTINE change(value: XYZWPR): XYZWPR BEGIN value.x=9 RETURN value END change')
        self.assertEqual((state['RESULT']['X'],state['A']['X']),(9,0))
    def test_alias_structure_and_array_points(self):
        state=execute(POINTS+' box.point=a items[1]=b alias=c result=FRAME(box.point,items[1],alias)',
                      types='TYPE point_t=XYZWPR box_t=STRUCTURE point: point_t ENDSTRUCTURE',
                      declarations=DECLARATIONS+' box: box_t items: ARRAY[1] OF point_t alias: point_t')
        self.assertEqual(state['RESULT']['R'],0)
    def test_result_replacement_preserves_captured_field_storage(self):
        state=execute(POINTS+' result=a change(result,result.x)',routines='ROUTINE change(value: XYZWPR; x: REAL) BEGIN value=FRAME(a,b,c) x=9 END change')
        self.assertEqual(state['RESULT']['X'],9)
    def test_label_dispatch_for_and_constructor_field_output(self):
        p,_=compile_program(POINTS+' FOR i=1 TO 2 DO seen=FRAME(a,b,c).x ENDFOR WRITE(FRAME(a,b,c).r::0::1,CR)',labelled=True)
        self.assertEqual(p.run()['I'],{'uninitialized':True}); self.assertEqual([r['text'] for r in p.write_requests],[' 0.0\n'])
    def test_frame_variable_name_remains_usable(self): self.assertEqual(execute('frame=7 total=frame',declarations=DECLARATIONS+' frame: INTEGER')['TOTAL'],7)
    def test_user_frame_function_keeps_precedence(self):
        p,r=compile_program('total=FRAME(7)',routines='ROUTINE FRAME(n: INTEGER): INTEGER BEGIN RETURN n+1 END FRAME')
        self.assertEqual(p.run()['TOTAL'],8); self.assertEqual(r.report['frame_operations'],[])
    def test_report_arity_origin_and_receiver_lookup(self):
        _,r=compile_program(POINTS+' seen=FRAME(a,b,c).x seen=FRAME(a,b,c,a).x')
        rows=r.report['frame_operations']; self.assertEqual([r['operation'] for r in rows],['FRAME','FRAME'])
        self.assertEqual([r['origin_argument'] for r in rows],[1,4]); self.assertEqual([len(r['operand_types']) for r in rows],[3,4])
        self.assertFalse(r.report['frame_policy']['controller_validated']); json.dumps(r.report)
    def test_failure_cleans_routine_frames_and_for_counter(self):
        p,_=compile_program(POINTS+' b.x=5 FOR i=1 TO 2 DO result=build() ENDFOR',routines='ROUTINE build: XYZWPR BEGIN RETURN FRAME(a,b,c) END build')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p._state.local_frames,p._state.call_depth,p.snapshot()['I']),([],0,{'uninitialized':True}))


class AuthoredFrameConstructorTests(unittest.TestCase):
    def test_complete_fixture_and_source_reports(self):
        source=Path(__file__).resolve().parents[1]/'examples/pythonic_frame_constructor.kl'
        result=translate(source.read_text(),filename=source.name); ns={'__name__':'frame_constructor_fixture'}
        exec(result.python_source,ns); out=[]; p=ns['Program'](write=out.append)
        self.assertEqual(p.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(out,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual([(r['operation'],r['line']) for r in result.report['frame_operations']],[('FRAME',10),('FRAME',12),(':',13)])
        self.assertEqual([r['origin_argument'] for r in result.report['frame_operations'] if r['operation']=='FRAME'],[1,4])
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))


class FrameConstructorGuardTests(unittest.TestCase):
    def reject(self,body,code='E_TYPE',**options):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**options)
        self.assertEqual(caught.exception.code,code)
    def test_argument_counts(self):
        for args in ('','a','a,b','a,b,c,d,a'):
            with self.subTest(args=args): self.reject('result=FRAME('+args+')','E_ARGUMENTS')
    def test_unsupported_point_types(self):
        for kind in ('XYZWPREXT','VECTOR','JOINTPOS','INTEGER','CONFIG'):
            for position in (0,1,2,3):
                args=['a','b','c','d']; args[position]='x'
                with self.subTest(kind=kind,position=position): self.reject('result=FRAME('+','.join(args)+')',declarations=DECLARATIONS+f' x: {kind}')
    def test_legacy_rejection_retained(self): self.reject('result=FRAME(a,b,c)','E_CALL',translator=legacy_translate)
    def test_for_counter_write_checks_stay_active(self):
        self.reject('FOR i=1 TO 2 DO result=FRAME(a,b,touch()) ENDFOR','E_FOR_COUNTER',routines='ROUTINE touch: XYZWPR BEGIN i=9 RETURN c END touch')
    def test_coincident_and_too_close_first_pair(self):
        for distance in (0,1,-1,math.nextafter(10,0)):
            with self.subTest(distance=distance),rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'apart'):
                rt.frame_from_points([runtime_pose(),runtime_pose((distance,0,0,0,0,0)),runtime_pose((0,20,0,0,0,0))])
    def test_collinear_and_too_close_third_point(self):
        for distance in (0,1,-1,math.nextafter(10,0)):
            with self.subTest(distance=distance),rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'line'):
                rt.frame_from_points([runtime_pose(),runtime_pose((20,0,0,0,0,0)),runtime_pose((100,distance,0,0,0,0))])
    def test_geometry_uses_distance_to_infinite_line(self):
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'10 mm from'):
            rt.frame_from_points([runtime_pose(),runtime_pose((20,0,0,0,0,0)),runtime_pose((1000,1,0,0,0,0))])
    def test_direct_runtime_argument_container_and_counts(self):
        for arguments in (None,{},(),[runtime_pose()]*2,[runtime_pose()]*5):
            with self.subTest(arguments=type(arguments).__name__),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.builtin('FRAME',arguments,17)
    def test_runtime_wrong_types_and_shapes(self):
        for value in (None,1,rt.Structure(('VECTOR',)),{}):
            with self.subTest(value=repr(value)),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.frame_from_points([runtime_pose(),runtime_pose(),value])
        value=runtime_pose(); del value.values['W']
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.frame_from_points([runtime_pose(),runtime_pose(),value])
    def test_unused_orientations_still_require_complete_finite_data(self):
        for value in (rt.UNINITIALIZED,float('inf'),float('nan'),True):
            p=runtime_pose((0,20,0,0,0,0)); p.values['R']=value
            with self.subTest(value=repr(value)),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.frame_from_points([runtime_pose(),runtime_pose((20,0,0,0,0,0)),p])
    def test_unused_configuration_still_checked(self):
        p=runtime_pose((20,0,0,0,0,0)); p.values['CONFIG_DATA'].values['CFG_TURN_NO1']=8
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.frame_from_points([runtime_pose(),p,runtime_pose((0,20,0,0,0,0))])
    def test_overflowing_difference_rejected_without_source_mutation(self):
        p=runtime_pose((-1e308,0,0,0,0,0)); before=rt.snapshot_value(p)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'line 17'):
            rt.frame_from_points([p,runtime_pose((1e308,0,0,0,0,0)),runtime_pose((0,20,0,0,0,0))],17)
        self.assertEqual(rt.snapshot_value(p),before)
    def test_runtime_strict_guard(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): rt.frame_from_points([runtime_pose()]*3)
