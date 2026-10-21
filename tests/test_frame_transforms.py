"""Portable rigid transforms checked against independent quaternion geometry."""
import json
import math
from pathlib import Path
import random
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


FIELDS=('X','Y','Z','W','P','R')
CONFIG=dict(CFG_TURN_NO1=0,CFG_TURN_NO2=-1,CFG_TURN_NO3=2,
            CFG_FLIP=False,CFG_LEFT=True,CFG_UP=False,CFG_FRONT=True)
DECLARATIONS='cfg: CONFIG a,b,c,result: XYZWPR seen: REAL total,i: INTEGER trace: STRING[20]'
INIT=' '.join('cfg.'+field+'='+('TRUE' if value else 'FALSE') if type(value) is bool
              else 'cfg.'+field+'='+str(value) for field,value in CONFIG.items())


def compile_program(body,*,declarations=DECLARATIONS,types='',routines='',translator=translate,labelled=False):
    source=f'PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n'+('marker::\n' if labelled else '')+INIT+'\n'+body+'\nEND T'
    result=translator(source,filename='frames.kl'); ns={'__name__':'frame_test'}
    exec(result.python_source,ns); return ns['Program'](),result


def execute(body,**options): return compile_program(body,**options)[0].run()


def runtime_pose(values=(0,0,0,0,0,0)):
    pose=rt.Structure(('XYZWPR',)); pose.values.update(zip(FIELDS,map(float,values)))
    pose.values['CONFIG_DATA'].values.update(CONFIG); return pose


def quaternion_product(a,b):
    w,x,y,z=a; v,i,j,k=b
    return (w*v-x*i-y*j-z*k,w*i+x*v+y*k-z*j,w*j-x*k+y*v+z*i,w*k+x*j-y*i+z*v)


def quaternion(angles):
    result=(1,0,0,0)
    for axis,angle in zip(range(3),angles):
        half=math.radians(angle)/2; value=[math.cos(half),0,0,0]; value[axis+1]=math.sin(half)
        result=quaternion_product(value,result)
    return result


def rotate(q,point):
    conjugate=(q[0],-q[1],-q[2],-q[3])
    return quaternion_product(quaternion_product(q,(0,*point)),conjugate)[1:]


class FrameMathTests(unittest.TestCase):
    def test_identity_composition(self):
        state=execute('a=POS(0,0,0,0,0,0,cfg) b=POS(1,2,3,10,20,30,cfg) result=a:b')
        for field in FIELDS: self.assertAlmostEqual(state['RESULT'][field],state['B'][field])
    def test_translation_composition(self):
        state=execute('result=POS(10,20,30,0,0,0,cfg):POS(1,2,3,0,0,0,cfg)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[11,22,33,0,0,0])
    def test_z_rotation_moves_local_translation(self):
        state=execute('result=POS(10,20,30,0,0,90,cfg):POS(1,2,3,0,0,0,cfg)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[8,21,33,0,0,90])
    def test_x_rotation_moves_local_translation(self):
        state=execute('result=POS(0,0,0,90,0,0,cfg):POS(1,2,3,0,0,0,cfg)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[1,-3,2,90,0,0])
    def test_y_rotation_moves_local_translation(self):
        state=execute('result=POS(0,0,0,0,90,0,cfg):POS(1,2,3,0,0,0,cfg)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[3,2,-1,0,90,0])
    def test_composition_is_not_commutative(self):
        state=execute('a=POS(0,0,0,0,0,90,cfg) b=POS(1,0,0,0,0,0,cfg) c=a:b result=b:a')
        self.assertEqual((state['C']['X'],state['C']['Y'],state['RESULT']['X'],state['RESULT']['Y']),(0,1,1,0))
    def test_inverse_translation(self):
        state=execute('result=INV(POS(1,2,3,0,0,0,cfg))')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[-1,-2,-3,0,0,0])
    def test_inverse_rotates_negative_translation(self):
        state=execute('result=INV(POS(10,20,30,0,0,90,cfg))')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[-20,10,-30,0,0,-90])
    def test_inverse_recovers_local_pose(self):
        state=execute('a=POS(10,20,30,0,0,90,cfg) b=POS(2,3,4,0,0,0,cfg) result=INV(a):(a:b)')
        for field in FIELDS: self.assertAlmostEqual(state['RESULT'][field],state['B'][field])
    def test_general_compositions_match_independent_quaternions(self):
        rng=random.Random(6921)
        for _ in range(80):
            a=[rng.uniform(-100,100) for _ in range(3)]+[rng.uniform(-180,180) for _ in range(3)]
            b=[rng.uniform(-100,100) for _ in range(3)]+[rng.uniform(-180,180) for _ in range(3)]
            qa,qb=quaternion(a[3:]),quaternion(b[3:]); expected=quaternion_product(qa,qb)
            location=[x+y for x,y in zip(a[:3],rotate(qa,b[:3]))]
            with self.subTest(a=a,b=b),rt._numeric_scope('pythonic'):
                result=rt.frame_transform(runtime_pose(a),runtime_pose(b))
                actual=quaternion([result.values[field] for field in ('W','P','R')])
                self.assertAlmostEqual(abs(sum(x*y for x,y in zip(actual,expected))),1,places=12)
                for field,value in zip(('X','Y','Z'),location): self.assertAlmostEqual(result.values[field],value,places=10)
    def test_general_inverses_match_independent_quaternions(self):
        for angles in ((12,34,56),(-135,89.99,170),(40,-90,20),(40,90,20),(0,0,180)):
            q=quaternion(angles); inverse=(q[0],-q[1],-q[2],-q[3]); expected=rotate(inverse,(-4,7,-9))
            with self.subTest(angles=angles),rt._numeric_scope('pythonic'):
                result=rt.frame_inverse(runtime_pose((4,-7,9,*angles)))
                actual=quaternion([result.values[field] for field in ('W','P','R')])
                self.assertAlmostEqual(abs(sum(x*y for x,y in zip(actual,inverse))),1,places=12)
                for field,value in zip(('X','Y','Z'),expected): self.assertAlmostEqual(result.values[field],value,places=10)
    def test_positive_gimbal_lock_has_zero_roll(self):
        state=execute('result=POS(0,0,0,40,90,20,cfg):POS(0,0,0,0,0,0,cfg)')
        for field,value in zip(('W','P','R'),(0,90,-20)): self.assertAlmostEqual(state['RESULT'][field],value)
    def test_negative_gimbal_lock_has_zero_roll(self):
        state=execute('result=POS(0,0,0,40,-90,20,cfg):POS(0,0,0,0,0,0,cfg)')
        for field,value in zip(('W','P','R'),(0,-90,60)): self.assertAlmostEqual(state['RESULT'][field],value)
    def test_near_gimbal_lock_retains_orientation(self):
        for pitch in (89.99999,-89.99999,90-1e-13,-90+1e-13):
            with self.subTest(pitch=pitch),rt._numeric_scope('pythonic'):
                result=rt.frame_transform(runtime_pose((0,0,0,40,pitch,20)),runtime_pose())
                q=quaternion((40,pitch,20)); actual=quaternion([result.values[field] for field in ('W','P','R')])
                self.assertAlmostEqual(abs(sum(x*y for x,y in zip(actual,q))),1,places=12)
    def test_large_angles_reduce_before_trigonometry(self):
        state=execute('a=POS(1,2,3,0,0,0,cfg) a.r=450 result=a:POS(1,0,0,0,0,0,cfg)')
        self.assertEqual([state['RESULT'][field] for field in FIELDS],[1,3,3,0,0,90])
    def test_finite_output_is_not_limited_by_pos_constructor_range(self):
        state=execute('a=POS(10000000,0,0,0,0,0,cfg) result=a:a')
        self.assertEqual(state['RESULT']['X'],20000000)
    def test_composition_copies_right_configuration(self):
        state=execute('a=POS(0,0,0,0,0,0,cfg) cfg.cfg_left=FALSE b=POS(0,0,0,0,0,0,cfg) result=a:b b.config_data.cfg_left=TRUE')
        self.assertFalse(state['RESULT']['CONFIG_DATA']['CFG_LEFT']); self.assertTrue(state['A']['CONFIG_DATA']['CFG_LEFT'])
    def test_inverse_copies_configuration(self):
        state=execute('a=POS(0,0,0,0,0,0,cfg) result=INV(a) a.config_data.cfg_left=FALSE')
        self.assertEqual(state['RESULT']['CONFIG_DATA'],CONFIG)


class FrameIntegrationTests(unittest.TestCase):
    def test_chains_associate_left(self):
        state=execute('a=POS(0,0,0,0,0,90,cfg) b=POS(1,0,0,0,0,0,cfg) result=a:b:b')
        self.assertEqual((state['RESULT']['X'],state['RESULT']['Y']),(0,2))
        state=execute('a=POS(0,0,0,0,0,0,cfg) b=a c=a a.x=1E16 b.x=-1E16 c.x=1 result=a:b:c')
        self.assertEqual(state['RESULT']['X'],1)
    def test_field_of_grouped_composition(self): self.assertEqual(execute('seen=(POS(1,0,0,0,0,0,cfg):POS(2,0,0,0,0,0,cfg)).x')['SEEN'],3)
    def test_field_of_inverse_call(self): self.assertEqual(execute('seen=INV(POS(1,0,0,0,0,0,cfg)).x')['SEEN'],-1)
    def test_grouped_geometry_in_io_values_and_format_expressions(self):
        p,_=compile_program('a=POS(1,0,0,0,0,0,cfg) READ(total::ROUND((a:a).x)) WRITE((a:a).x::0::1,CR)')
        p=type(p)(read=lambda request:[7])
        self.assertEqual(p.run()['TOTAL'],7)
        self.assertEqual([row['text'] for row in p.write_requests],[' 2.0\n'])
    def test_transform_field_argument_is_private(self):
        state=execute('a=POS(1,0,0,0,0,0,cfg) change((a:a).x)',routines='ROUTINE change(x: REAL) BEGIN x=9 seen=x END change')
        self.assertEqual((state['SEEN'],state['A']['X']),(9,1))
    def test_inverse_field_argument_is_private(self):
        state=execute('a=POS(1,0,0,0,0,0,cfg) change(INV(a).x)',routines='ROUTINE change(x: REAL) BEGIN x=9 seen=x END change')
        self.assertEqual((state['SEEN'],state['A']['X']),(9,1))
    def test_aggregate_argument_and_return(self):
        state=execute('a=POS(1,0,0,0,0,0,cfg) result=make(a:a)',routines='ROUTINE make(v: XYZWPR): XYZWPR BEGIN v.x=9 RETURN INV(v) END make')
        self.assertEqual((state['RESULT']['X'],state['A']['X']),(-9,1))
    def test_named_array_and_structure_storage(self):
        state=execute('a=POS(1,0,0,0,0,0,cfg) box.pose=a:a values[1]=INV(box.pose)',
                      types='TYPE box_t=STRUCTURE pose: XYZWPR ENDSTRUCTURE',declarations=DECLARATIONS+' box: box_t values: ARRAY[1] OF XYZWPR')
        self.assertEqual((state['BOX']['POSE']['X'],state['VALUES'][0]['X']),(2,-2))
    def test_left_operand_captured_before_right_call(self):
        state=execute('a=POS(10,0,0,0,0,0,cfg) b=POS(1,0,0,0,0,0,cfg) result=a:touch()',routines='ROUTINE touch: XYZWPR BEGIN a.x=99 RETURN b END touch')
        self.assertEqual((state['RESULT']['X'],state['A']['X']),(11,99))
    def test_uninitialized_left_stops_before_right_effects(self):
        p,_=compile_program("trace='' result=a:touch()",routines="ROUTINE touch: XYZWPR BEGIN trace='touched' RETURN a END touch")
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TRACE'],'')
    def test_operand_calls_run_once_in_source_order(self):
        state=execute("trace='' result=make(1):make(2)",routines="ROUTINE make(n: INTEGER): XYZWPR BEGIN trace=trace+CHR(64+n) RETURN POS(n,0,0,0,0,0,cfg) END make")
        self.assertEqual((state['TRACE'],state['RESULT']['X']),('AB',3))
    def test_assignment_value_precedes_target_index_effect(self):
        state=execute('a=POS(1,0,0,0,0,0,cfg) values[pick()]=a:a',declarations=DECLARATIONS+' values: ARRAY[1] OF XYZWPR',routines='ROUTINE pick: INTEGER BEGIN a.x=99 RETURN 1 END pick')
        self.assertEqual((state['VALUES'][0]['X'],state['A']['X']),(2,99))
    def test_replacement_preserves_captured_field_reference(self):
        state=execute('a=POS(1,0,0,0,0,0,cfg) change(a,a.x)',routines='ROUTINE change(v: XYZWPR; x: REAL) BEGIN v=v:v seen=x x=9 END change')
        self.assertEqual((state['SEEN'],state['A']['X']),(2,9))
    def test_labelled_dispatch_and_for_helper(self):
        state=execute('a=POS(1,0,0,0,0,0,cfg) FOR i=1 TO 2 DO result=make(a) ENDFOR',labelled=True,routines='ROUTINE make(v: XYZWPR): XYZWPR BEGIN RETURN v:v END make')
        self.assertEqual(state['RESULT']['X'],2); self.assertEqual(state['I'],{'uninitialized':True})
    def test_source_reports_do_not_duplicate_on_field_lookup(self):
        _,r=compile_program('a=POS(1,0,0,0,0,0,cfg) change(INV(a).x) change((a:a).x)',routines='ROUTINE change(x: REAL) BEGIN seen=x END change')
        self.assertEqual([row['operation'] for row in r.report['frame_operations']],['INV',':'])
        self.assertFalse(r.report['frame_policy']['controller_validated']); json.dumps(r.report)
    def test_user_inv_routine_has_precedence(self):
        p,r=compile_program('total=INV(7)',routines='ROUTINE INV(n: INTEGER): INTEGER BEGIN RETURN n+1 END INV')
        self.assertEqual(p.run()['TOTAL'],8); self.assertEqual(r.report['frame_operations'],[])
    def test_inv_can_still_be_an_ordinary_variable(self): self.assertEqual(execute('INV=7 total=INV',declarations=DECLARATIONS+' INV: INTEGER')['TOTAL'],7)
    def test_errors_clean_local_frames_and_for_counter(self):
        p,_=compile_program('FOR i=1 TO 2 DO result=fail() ENDFOR',routines='ROUTINE fail: XYZWPR VAR v: XYZWPR BEGIN RETURN INV(v) END fail')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p._state.local_frames,p._state.call_depth,p.snapshot()['I']),([],0,{'uninitialized':True}))


class AuthoredFrameTests(unittest.TestCase):
    def test_complete_fixture_and_reports(self):
        source=Path(__file__).resolve().parents[1]/'examples/pythonic_frames.kl'
        result=translate(source.read_text(),filename=source.name); ns={'__name__':'frame_fixture'}
        exec(result.python_source,ns); output=[]; program=ns['Program'](write=output.append)
        self.assertEqual(program.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(output,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual([row['operation'] for row in result.report['frame_operations']],[':','INV',':'])
        self.assertEqual([row['line'] for row in result.report['frame_operations']],[9,10,10])
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))


class FrameGuardTests(unittest.TestCase):
    def reject(self,body,code='E_TYPE',**options):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**options)
        self.assertEqual(caught.exception.code,code)
    def test_other_relative_operand_types_stay_blocked(self):
        for kind in ('XYZWPREXT','VECTOR','JOINTPOS','CONFIG','INTEGER'):
            with self.subTest(kind=kind): self.reject('result=x:y',declarations=DECLARATIONS+f' x,y: {kind}')
    def test_mixed_relative_operand_types_stay_blocked(self): self.reject('result=a:VEC(1,2,3)')
    def test_other_inverse_operand_types_stay_blocked(self):
        for kind in ('XYZWPREXT','VECTOR','JOINTPOS','CONFIG','INTEGER'):
            with self.subTest(kind=kind): self.reject('result=INV(x)',declarations=DECLARATIONS+f' x: {kind}')
    def test_inverse_argument_count(self):
        for body in ('result=INV()','result=INV(a,b)'):
            with self.subTest(body=body): self.reject(body,'E_ARGUMENTS')
    def test_legacy_relative_rejection_retained(self): self.reject('result=a:b','E_UNSUPPORTED',translator=legacy_translate)
    def test_legacy_inverse_rejection_retained(self): self.reject('result=INV(a)','E_CALL',translator=legacy_translate)
    def test_for_counter_write_analysis_stays_active(self):
        self.reject('FOR i=1 TO 2 DO result=INV(touch()) ENDFOR','E_FOR_COUNTER',routines='ROUTINE touch: XYZWPR BEGIN i=9 RETURN a END touch')
    def test_incomplete_config_and_real_fields_fail_without_destination_writes(self):
        p,_=compile_program('result=POS(5,0,0,0,0,0,cfg) a.x=1 result=INV(a)')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['RESULT']['X'],5)
    def test_forged_record_layouts_rejected(self):
        for change in ('extra','missing','type','spec'):
            value=runtime_pose()
            if change=='extra': value.values['EXTRA']=0
            elif change=='missing': del value.values['W']
            elif change=='type': value.types['W']=rt.INTEGER
            else: value.spec=('POSITION',)
            with self.subTest(change=change),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.frame_inverse(value,17)
    def test_bad_configuration_rejected(self):
        for field,value in (('CFG_FLIP',1),('CFG_TURN_NO1',8),('CFG_UP',rt.UNINITIALIZED)):
            pose=runtime_pose(); pose.values['CONFIG_DATA'].values[field]=value
            with self.subTest(field=field),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.frame_inverse(pose)
    def test_nonfinite_and_nonreal_components_rejected(self):
        for value in (float('nan'),float('inf'),True,'x',rt.UNINITIALIZED):
            pose=runtime_pose(); pose.values['W']=value
            with self.subTest(value=repr(value)),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.frame_transform(pose,runtime_pose())
    def test_runtime_wrong_types_rejected(self):
        for value in (None,1,rt.Structure(('VECTOR',)),{}):
            with self.subTest(value=repr(value)),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.binary(':',runtime_pose(),value,17)
    def test_runtime_inverse_argument_count(self):
        for values in ([],[runtime_pose(),runtime_pose()]):
            with self.subTest(count=len(values)),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.builtin('INV',values,17)
    def test_nonfinite_translation_result_rejected(self):
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.frame_transform(runtime_pose((1e308,0,0,0,0,0)),runtime_pose((1e308,0,0,0,0,0)))
    def test_runtime_failure_retains_input_data_and_location(self):
        left=runtime_pose(); right=runtime_pose(); right.values['X']=float('inf'); before=rt.snapshot_value(left)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'line 17'): rt.frame_transform(left,right,17)
        self.assertEqual(rt.snapshot_value(left),before)
    def test_runtime_strict_guard(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): rt.frame_inverse(runtime_pose())
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): rt.frame_transform(runtime_pose(),runtime_pose())
