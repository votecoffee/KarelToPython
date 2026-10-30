"""Explicit pose representation conversion, checked rotations and retained ownership."""
import json
import math
from pathlib import Path
import random
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_frame_transforms import CONFIG, INIT, FIELDS, runtime_pose, quaternion, rotate


DECLARATIONS='cfg: CONFIG a,b: XYZWPR p,q: POSITION v: VECTOR seen: REAL i,total: INTEGER trace: STRING[20]'


def compile_program(body,*,declarations=DECLARATIONS,types='',routines='',translator=translate,labelled=False):
    source=f'PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n'+('marker::\n' if labelled else '')+INIT+'\n'+body+'\nEND T'
    result=translator(source,filename='position_conversions.kl'); ns={'__name__':'position_conversion_test'}
    exec(result.python_source,ns); return ns['Program'](),result


def execute(body,**options): return compile_program(body,**options)[0].run()


def runtime_position(angles=(0,0,0),location=(1,2,3)):
    result=rt.Structure(('POSITION',)); result.values['CONFIG_DATA'].values.update(CONFIG)
    result.values['LOCATION'].values.update(zip(('X','Y','Z'),map(float,location)))
    q=quaternion(angles)
    for name,basis in zip(('NORMAL','ORIENT','APPROACH'),((1,0,0),(0,1,0),(0,0,1))):
        result.values[name].values.update(zip(('X','Y','Z'),rotate(q,basis)))
    return result


class PositionConversionMathTests(unittest.TestCase):
    def test_identity_initializes_position_axes(self):
        state=execute('p=POS(1,2,3,0,0,0,cfg)')['P']
        self.assertEqual(state['NORMAL'],dict(X=1,Y=0,Z=0)); self.assertEqual(state['ORIENT'],dict(X=0,Y=1,Z=0))
        self.assertEqual(state['APPROACH'],dict(X=0,Y=0,Z=1)); self.assertEqual(state['LOCATION'],dict(X=1,Y=2,Z=3))
    def test_z_rotation_maps_columns(self):
        state=execute('p=POS(1,2,3,0,0,90,cfg)')['P']
        self.assertEqual(state['NORMAL'],dict(X=0,Y=1,Z=0)); self.assertEqual(state['ORIENT'],dict(X=-1,Y=0,Z=0))
        self.assertEqual(state['APPROACH'],dict(X=0,Y=0,Z=1))
    def test_x_rotation_maps_columns(self):
        state=execute('p=POS(0,0,0,90,0,0,cfg)')['P']
        self.assertEqual(state['ORIENT'],dict(X=0,Y=0,Z=1)); self.assertEqual(state['APPROACH'],dict(X=0,Y=-1,Z=0))
    def test_y_rotation_maps_columns(self):
        state=execute('p=POS(0,0,0,0,90,0,cfg)')['P']
        self.assertEqual(state['NORMAL'],dict(X=0,Y=0,Z=-1)); self.assertEqual(state['APPROACH'],dict(X=1,Y=0,Z=0))
    def test_round_trip_preserves_location_and_configuration(self):
        state=execute('a=POS(1,2,3,10,20,30,cfg) p=a b=p')
        for field in FIELDS: self.assertAlmostEqual(state['A'][field],state['B'][field])
        self.assertEqual(state['P']['CONFIG_DATA'],CONFIG); self.assertEqual(state['B']['CONFIG_DATA'],CONFIG)
    def test_canonical_euler_output(self):
        state=execute('a=POS(0,0,0,0,0,0,cfg) a.r=450 p=a b=p')
        self.assertEqual([state['B'][field] for field in FIELDS],[0,0,0,0,0,90])
    def test_general_forward_columns_match_independent_quaternions(self):
        rng=random.Random(711)
        for _ in range(80):
            angles=tuple(rng.uniform(-180,180) for _ in range(3)); q=quaternion(angles)
            with self.subTest(angles=angles),rt._numeric_scope('pythonic'):
                result=rt.convert_position(('POSITION',),runtime_pose((1,2,3,*angles)))
                for name,point in zip(('NORMAL','ORIENT','APPROACH'),((1,0,0),(0,1,0),(0,0,1))):
                    for axis,value in zip(('X','Y','Z'),rotate(q,point)): self.assertAlmostEqual(result.values[name].values[axis],value,places=12)
    def test_general_reverse_matches_independent_quaternions(self):
        rng=random.Random(712)
        angles=[(40,90,20),(40,-90,20),(40,89.99999,20)]+[tuple(rng.uniform(-180,180) for _ in range(3)) for _ in range(80)]
        for angle in angles:
            with self.subTest(angle=angle),rt._numeric_scope('pythonic'):
                result=rt.convert_position(('XYZWPR',),runtime_position(angle))
                actual=quaternion(tuple(result.values[field] for field in ('W','P','R'))); expected=quaternion(angle)
                self.assertAlmostEqual(abs(sum(a*b for a,b in zip(actual,expected))),1,places=12)
    def test_location_and_config_copies_are_independent(self):
        state=execute('a=POS(1,2,3,0,0,0,cfg) p=a p.location.x=9 p.config_data.cfg_left=FALSE b=p p.location.x=11')
        self.assertEqual((state['A']['X'],state['B']['X'],state['P']['LOCATION']['X']),(1,9,11))
        self.assertTrue(state['A']['CONFIG_DATA']['CFG_LEFT']); self.assertFalse(state['B']['CONFIG_DATA']['CFG_LEFT'])
    def test_complete_position_can_now_be_copied_and_queried(self):
        state=execute('p=POS(0,0,0,0,0,0,cfg) q=p total=0 IF NOT UNINIT(q.normal.x) THEN total=1 ENDIF')
        self.assertEqual(state['TOTAL'],1); self.assertEqual(state['P'],state['Q'])
    def test_large_finite_location_is_data_only(self):
        with rt._numeric_scope('pythonic'):
            result=rt.convert_position(('XYZWPR',),rt.convert_position(('POSITION',),runtime_pose((1e300,-1e300,0,0,0,0))))
        self.assertEqual((result.values['X'],result.values['Y']),(1e300,-1e300))


class PositionConversionIntegrationTests(unittest.TestCase):
    def test_type_aliases(self):
        state=execute('x=POS(1,2,3,0,0,90,cfg) y=x z=y',types='TYPE cart_t=XYZWPR matrix_t=POSITION',declarations=DECLARATIONS+' x,z: cart_t y: matrix_t')
        self.assertEqual(state['Z']['R'],90)
    def test_nested_structure_and_array_elements(self):
        state=execute('box.pose=POS(1,2,3,0,0,90,cfg) points[1]=box.pose box.pose=points[1]',
                      types='TYPE box_t=STRUCTURE pose: XYZWPR ENDSTRUCTURE',declarations=DECLARATIONS+' box: box_t points: ARRAY[1] OF POSITION')
        self.assertEqual((state['BOX']['POSE']['R'],state['POINTS'][0]['NORMAL']['Y']),(90,1))
    def test_source_function_evaluates_once(self):
        state=execute('total=0 p=make()',routines='ROUTINE make: XYZWPR BEGIN total=total+1 RETURN POS(1,2,3,0,0,90,cfg) END make')
        self.assertEqual((state['TOTAL'],state['P']['NORMAL']['Y']),(1,1))
    def test_internal_local_conversion_then_exact_return(self):
        state=execute('p=make()',routines='ROUTINE make: POSITION VAR local: POSITION BEGIN local=POS(1,2,3,0,0,90,cfg) RETURN local END make')
        self.assertEqual(state['P']['NORMAL']['Y'],1)
    def test_captured_value_precedes_target_index_effects(self):
        state=execute('a=POS(1,2,3,0,0,90,cfg) items[pick()]=a',declarations=DECLARATIONS+' items: ARRAY[1] OF POSITION',
                      routines='ROUTINE pick: INTEGER BEGIN a.x=99 RETURN 1 END pick')
        self.assertEqual((state['ITEMS'][0]['LOCATION']['X'],state['A']['X']),(1,99))
    def test_failed_conversion_skips_target_index_effects(self):
        p,_=compile_program("trace='' items[pick()]=q",declarations=DECLARATIONS+' items: ARRAY[1] OF XYZWPR',
                            routines="ROUTINE pick: INTEGER BEGIN trace='picked' RETURN 1 END pick")
        invalid=runtime_position(); invalid.values['NORMAL'].values['X']=2; p._state.values['Q']=invalid
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TRACE'],'')
    def test_replacement_preserves_location_reference(self):
        state=execute('p=POS(1,2,3,0,0,0,cfg) change(p,p.location.x)',
                      routines='ROUTINE change(value: POSITION; x: REAL) BEGIN value=POS(7,8,9,0,0,90,cfg) seen=x x=11 END change')
        self.assertEqual((state['SEEN'],state['P']['LOCATION']['X'],state['P']['NORMAL']['Y']),(7,11,1))
    def test_replacement_preserves_config_reference(self):
        state=execute('p=POS(1,2,3,0,0,0,cfg) change(p,p.config_data)',
                      routines='ROUTINE change(value: POSITION; c: CONFIG) BEGIN value=POS(7,8,9,0,0,90,cfg) c.cfg_left=FALSE END change')
        self.assertFalse(state['P']['CONFIG_DATA']['CFG_LEFT']); self.assertTrue(state['CFG']['CFG_LEFT'])
    def test_detached_orientation_copy_remains_writable(self):
        state=execute('p=POS(0,0,0,0,0,90,cfg) v=p.normal v.x=9')
        self.assertEqual((state['V']['X'],state['P']['NORMAL']['X']),(9,0))
    def test_grouped_orientation_value_argument_remains_private(self):
        state=execute('p=POS(0,0,0,0,0,90,cfg) change((p.normal))',routines='ROUTINE change(v: VECTOR) BEGIN v.x=9 seen=v.x END change')
        self.assertEqual((state['SEEN'],state['P']['NORMAL']['X']),(9,0))
    def test_geometry_result_assignment_conversion(self):
        state=execute('a=POS(1,0,0,0,0,90,cfg) p=a:a b=p')
        self.assertEqual((state['B']['X'],state['B']['Y'],state['B']['R']),(1,1,-180))
    def test_label_dispatch_and_for(self):
        state=execute('FOR i=1 TO 2 DO p=POS(i,0,0,0,0,0,cfg) ENDFOR b=p',labelled=True)
        self.assertEqual((state['B']['X'],state['I']),(2,{'uninitialized':True}))
    def test_failure_cleans_local_frames_and_for_counter(self):
        p,_=compile_program('FOR i=1 TO 2 DO fail ENDFOR',routines='ROUTINE fail VAR value: POSITION local: XYZWPR BEGIN local=value END fail')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p._state.local_frames,p._state.call_depth,p.snapshot()['I']),([],0,{'uninitialized':True}))
    def test_report_entries_and_boundaries(self):
        _,r=compile_program('p=POS(1,2,3,0,0,90,cfg) b=p q=p')
        self.assertEqual([(x['source_type'],x['target_type']) for x in r.report['position_conversions']],[('XYZWPR','POSITION'),('POSITION','XYZWPR')])
        self.assertFalse(r.report['position_conversion_policy']['controller_validated']); json.dumps(r.report)


class AuthoredPositionConversionTests(unittest.TestCase):
    def test_complete_fixture_and_source_reports(self):
        source=Path(__file__).resolve().parents[1]/'examples/pythonic_position_conversions.kl'
        result=translate(source.read_text(),filename=source.name); ns={'__name__':'position_conversion_fixture'}
        exec(result.python_source,ns); out=[]; p=ns['Program'](write=out.append)
        self.assertEqual(p.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(out,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual([(r['source_type'],r['target_type'],r['line']) for r in result.report['position_conversions']],
                         [('XYZWPR','POSITION',8),('POSITION','XYZWPR',12)])
        self.assertTrue(all(p._state.values['P'].values[name].read_only for name in rt.POSITION_READ_ONLY_FIELDS))
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))


class PositionConversionGuardTests(unittest.TestCase):
    def reject(self,body,code='E_TYPE',**options):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**options)
        self.assertEqual(caught.exception.code,code)
    def test_orientation_assignments_remain_read_only(self):
        for body in ('p.normal=VEC(1,0,0)','p.normal.x=1','p.orient.y=1','p.approach.z=1'):
            with self.subTest(body=body): self.reject(body,'E_POSITION_READ_ONLY')
    def test_bare_orientation_references_remain_blocked(self): self.reject('change(p.normal)','E_POSITION_READ_ONLY_ARG',routines='ROUTINE change(v: VECTOR) BEGIN END change')
    def test_other_positional_types_stay_blocked(self):
        for kind in ('VECTOR','CONFIG'):
            for body in ('p=x','x=p','a=x','x=a'):
                with self.subTest(kind=kind,body=body): self.reject(body,declarations=DECLARATIONS+f' x: {kind}')
    def test_cartesian_routine_conversion_is_private_and_pythonic(self):
        routine='ROUTINE take(v: POSITION) BEGIN v.location.x=99 seen=v.location.x END take'
        for value in ('a','(a)','POS(1,2,3,0,0,0,cfg)'):
            with self.subTest(value=value):
                state=execute('a=POS(1,2,3,0,0,0,cfg) take('+value+')',routines=routine)
                self.assertEqual((state['A']['X'],state['SEEN']),(1.,99.))
                self.reject('take('+value+')','E_CALL' if value.startswith('POS(') else 'E_TYPE',routines=routine,translator=legacy_translate)

    def test_cartesian_return_conversion_is_pythonic(self):
        routine='ROUTINE make: POSITION BEGIN RETURN a END make'
        self.assertEqual(execute('a=POS(1,2,3,0,0,0,cfg) q=make()',routines=routine)['Q']['LOCATION']['X'],1.)
        self.reject('q=make()','E_RETURN',routines=routine,translator=legacy_translate)
    def test_named_arrays_convert_components_into_receiver_schema(self):
        p,_=compile_program('poses[1]=POS(1,2,3,0,0,0,cfg) positions=poses',types='TYPE poses_t=ARRAY[1]OF XYZWPR',declarations=DECLARATIONS+' positions:ARRAY[1]OF POSITION poses:poses_t')
        self.assertEqual(p.run()['POSITIONS'][0]['LOCATION']['X'],1.);self.assertEqual(p.snapshot()['POSES'][0]['X'],1.)
    def test_legacy_conversions_remain_blocked(self):
        for body in ('p=a','a=p'):
            with self.subTest(body=body): self.reject(body,translator=legacy_translate)
    def test_for_counter_effect_protection_remains(self): self.reject('FOR i=1 TO 2 DO p=touch() ENDFOR','E_FOR_COUNTER',routines='ROUTINE touch: XYZWPR BEGIN i=9 RETURN a END touch')
    def test_incomplete_sources_preserve_destination(self):
        for body,root,field,expected in (('p.location.x=7 p=a','P','LOCATION',dict(X=7,Y={'uninitialized':True},Z={'uninitialized':True})),('b.x=7 b=p','B','X',7)):
            p,_=compile_program(body)
            with self.subTest(body=body),self.assertRaises(rt.KarelRuntimeError): p.run()
            self.assertEqual(p.snapshot()[root][field],expected)
    def test_nonunit_columns_rejected(self):
        for value in (0,2,1+2e-9):
            p=runtime_position(); p.values['NORMAL'].values['X']=value
            with self.subTest(value=value),rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'unit'): rt.convert_position(('XYZWPR',),p)
    def test_nonorthogonal_columns_rejected(self):
        p=runtime_position(); p.values['ORIENT'].values.update(X=1,Y=0,Z=0)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'orthogonal'): rt.convert_position(('XYZWPR',),p)
    def test_left_handed_matrix_rejected(self):
        p=runtime_position(); p.values['ORIENT'].values['Y']=-1
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'right-handed'): rt.convert_position(('XYZWPR',),p)
    def test_determinant_tolerance_checked_independently(self):
        p=runtime_position()
        for name,axis in zip(('NORMAL','ORIENT','APPROACH'),('X','Y','Z')): p.values[name].values[axis]=1+5e-10
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'right-handed'): rt.convert_position(('XYZWPR',),p)
    def test_small_rounding_deviation_is_accepted(self):
        p=runtime_position(); p.values['ORIENT'].values['X']=5e-10
        with rt._numeric_scope('pythonic'): result=rt.convert_position(('XYZWPR',),p)
        self.assertTrue(all(math.isfinite(result.values[field]) for field in FIELDS))
    def test_nonfinite_unknown_and_wrong_scalar_types_rejected(self):
        for value in (float('nan'),float('inf'),True,rt.UNINITIALIZED,'x'):
            p=runtime_position(); p.values['NORMAL'].values['X']=value
            with self.subTest(value=repr(value)),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.convert_position(('XYZWPR',),p)
    def test_malformed_shapes_rejected(self):
        for edit in ('extra','missing','type'):
            p=runtime_position()
            if edit=='extra': p.values['EXTRA']=0
            elif edit=='missing': del p.values['ORIENT']
            else: p.types['NORMAL']=('INTEGER',)
            with self.subTest(edit=edit),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.convert_position(('XYZWPR',),p)
    def test_invalid_config_rejected_in_both_directions(self):
        for target,p in ((('POSITION',),runtime_pose()),(('XYZWPR',),runtime_position())):
            p.values['CONFIG_DATA'].values['CFG_TURN_NO1']=8
            with self.subTest(target=target),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.convert_position(target,p)
    def test_bad_source_target_and_same_type_pairs_rejected(self):
        for target,value in ((('POSITION',),None),(('VECTOR',),runtime_pose())):
            with self.subTest(target=target),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.convert_position(target,value,17)
    def test_runtime_protection_is_preserved_after_conversion_and_copy(self):
        with rt._numeric_scope('pythonic'): p=rt.convert_position(('POSITION',),runtime_pose())
        for value in (p,p.clone()):
            for name in rt.POSITION_READ_ONLY_FIELDS:
                with self.subTest(name=name),self.assertRaises(rt.KarelRuntimeError): rt.field_reference(value.values[name],'X').set(9)
    def test_failed_conversion_retains_source_and_location(self):
        p=runtime_position(); p.values['ORIENT'].values['Y']=-1; before=rt.snapshot_value(p)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'line 17'): rt.convert_position(('XYZWPR',),p,17)
        self.assertEqual(rt.snapshot_value(p),before)
    def test_runtime_strict_guard(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): rt.convert_position(('POSITION',),runtime_pose())
