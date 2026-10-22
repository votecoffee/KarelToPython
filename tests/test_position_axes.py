"""Pose axis queries: independent geometry, private values and failure guards."""
import json
from pathlib import Path
import random
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_frame_transforms import INIT, quaternion, rotate, runtime_pose
from tests.test_position_conversions import runtime_position


DECLARATIONS='cfg: CONFIG p,q: POSITION pose: XYZWPR a,b: VECTOR seen: REAL total,i: INTEGER trace: STRING[20]'


def compile_program(body, *, declarations=DECLARATIONS, types='', routines='', labelled=False, translator=translate):
    source=f'PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n'+('marker::\n' if labelled else '')+INIT+'\n'+body+'\nEND T'
    result=translator(source,filename='position_axes.kl'); ns={'__name__':'position_axis_test'}
    exec(result.python_source,ns)
    return ns['Program'](),result


def execute(body, **options): return compile_program(body,**options)[0].run()


class PositionAxisMathTests(unittest.TestCase):
    def test_identity_axes(self):
        state=execute('p=POS(1,2,3,0,0,0,cfg) a=APPROACH(p) b=ORIENT(p)')
        self.assertEqual(state['A'],dict(X=0,Y=0,Z=1)); self.assertEqual(state['B'],dict(X=0,Y=1,Z=0))

    def test_quarter_turn_axes(self):
        for name,angles,expected in (('APPROACH','0,90,0',dict(X=1,Y=0,Z=0)),
                                     ('ORIENT','90,0,0',dict(X=0,Y=0,Z=1)),
                                     ('ORIENT','0,0,90',dict(X=-1,Y=0,Z=0))):
            with self.subTest(name=name,angles=angles):
                self.assertEqual(execute(f'p=POS(0,0,0,{angles},cfg) a={name}(p)')['A'],expected)

    def test_position_axes_equal_detached_column_values(self):
        state=execute('p=POS(1,2,3,17,38,-59,cfg) a=APPROACH(p) b=ORIENT(p)')
        self.assertEqual(state['A'],state['P']['APPROACH']); self.assertEqual(state['B'],state['P']['ORIENT'])

    def test_both_representations_match_independent_quaternions(self):
        rng=random.Random(731)
        for angles in [(40,90,20),(40,-90,20)]+[tuple(rng.uniform(-180,180) for _ in range(3)) for _ in range(50)]:
            for value in (runtime_position(angles),runtime_pose((1,2,3,*angles))):
                for name,basis in (('APPROACH',(0,0,1)),('ORIENT',(0,1,0))):
                    with self.subTest(angles=angles,spec=value.spec,name=name),rt._numeric_scope('pythonic'):
                        result=rt.position_axis(name,value)
                        for axis,expected in zip(('X','Y','Z'),rotate(quaternion(angles),basis)):
                            self.assertAlmostEqual(result.values[axis],expected,places=12)

    def test_position_columns_do_not_pass_through_euler_extraction(self):
        value=runtime_position((40,90-1e-13,20))
        with rt._numeric_scope('pythonic'):
            for name in ('APPROACH','ORIENT'):
                self.assertEqual(rt.position_axis(name,value).values,value.values[name].values)

    def test_small_tolerated_deviation_is_not_repaired(self):
        value=runtime_position(); value.values['ORIENT'].values['X']=5e-10
        with rt._numeric_scope('pythonic'): result=rt.position_axis('ORIENT',value)
        self.assertEqual(result.values['X'],5e-10)

    def test_axis_offset_moves_only_location(self):
        state=execute('p=POS(10,20,30,0,90,0,cfg) q=p q.location=q.location+APPROACH(p)*50+ORIENT(p)*20')
        self.assertEqual(state['Q']['LOCATION'],dict(X=60,Y=40,Z=30))
        for field in ('NORMAL','ORIENT','APPROACH','CONFIG_DATA'): self.assertEqual(state['P'][field],state['Q'][field])


class PositionAxisIntegrationTests(unittest.TestCase):
    def test_query_result_is_independent_writable_value(self):
        state=execute('p=POS(0,0,0,0,0,0,cfg) a=APPROACH(p) a.z=9 b=ORIENT(p) b.y=8')
        self.assertEqual((state['A']['Z'],state['B']['Y'],state['P']['APPROACH']['Z'],state['P']['ORIENT']['Y']),(9,8,1,1))

    def test_bare_function_result_argument_is_private(self):
        state=execute('p=POS(0,0,0,0,0,0,cfg) change(APPROACH(p))',
                      routines='ROUTINE change(v: VECTOR) BEGIN v.z=9 seen=v.z END change')
        self.assertEqual((state['SEEN'],state['P']['APPROACH']['Z']),(9,1))

    def test_result_field_argument_is_private(self):
        state=execute('p=POS(0,0,0,0,0,0,cfg) change(ORIENT(p).y)',
                      routines='ROUTINE change(x: REAL) BEGIN x=9 seen=x END change')
        self.assertEqual((state['SEEN'],state['P']['ORIENT']['Y']),(9,1))

    def test_internal_vector_return(self):
        state=execute('p=POS(0,0,0,0,90,0,cfg) a=make()',routines='ROUTINE make: VECTOR BEGIN RETURN APPROACH(p) END make')
        self.assertEqual(state['A'],dict(X=1,Y=0,Z=0))

    def test_alias_and_nested_storage(self):
        state=execute('box.pose=POS(0,0,0,0,0,0,cfg) values[1]=ORIENT(box.pose)',
                      types='TYPE matrix_t=POSITION direction_t=VECTOR box_t=STRUCTURE pose: matrix_t ENDSTRUCTURE',
                      declarations=DECLARATIONS+' box: box_t values: ARRAY[1] OF direction_t')
        self.assertEqual(state['VALUES'],[dict(X=0,Y=1,Z=0)])

    def test_geometry_results_are_query_operands(self):
        state=execute('p=POS(0,0,0,0,0,90,cfg) pose=POS(0,0,0,0,0,0,cfg) a=ORIENT(INV(p):pose) seen=APPROACH(p:pose).z')
        self.assertEqual(state['A'],dict(X=1,Y=0,Z=0)); self.assertEqual(state['SEEN'],1)

    def test_constructor_query_and_grouped_field(self):
        self.assertEqual(execute('seen=(APPROACH(POS(0,0,0,0,90,0,cfg))).x')['SEEN'],1)

    def test_operand_function_evaluates_once(self):
        state=execute('total=0 seen=APPROACH(make()).z',
                      routines='ROUTINE make: POSITION VAR value: POSITION BEGIN total=total+1 value=POS(0,0,0,0,0,0,cfg) RETURN value END make')
        self.assertEqual((state['TOTAL'],state['SEEN']),(1,1))

    def test_capture_precedes_later_vector_effects(self):
        state=execute('p=POS(0,0,0,0,0,0,cfg) a=APPROACH(p)+touch()',
                      routines='ROUTINE touch: VECTOR BEGIN p=POS(0,0,0,0,90,0,cfg) RETURN VEC(1,0,0) END touch')
        self.assertEqual(state['A'],dict(X=1,Y=0,Z=1)); self.assertEqual(state['P']['APPROACH'],dict(X=1,Y=0,Z=0))

    def test_value_precedes_target_index_effects(self):
        state=execute('p=POS(0,0,0,0,0,0,cfg) values[pick()]=ORIENT(p)',declarations=DECLARATIONS+' values: ARRAY[1] OF VECTOR',
                      routines='ROUTINE pick: INTEGER BEGIN p=POS(0,0,0,90,0,0,cfg) RETURN 1 END pick')
        self.assertEqual(state['VALUES'],[dict(X=0,Y=1,Z=0)]); self.assertEqual(state['P']['ORIENT'],dict(X=0,Y=0,Z=1))

    def test_query_does_not_export_read_only_flag(self):
        value=runtime_position(); before=rt.snapshot_value(value)
        with rt._numeric_scope('pythonic'):
            for name in ('APPROACH','ORIENT'):
                result=rt.position_axis(name,value)
                self.assertFalse(result.read_only); self.assertIsNot(result,value.values[name])
                rt.field_reference(result,'X').set(9)
                self.assertTrue(value.values[name].read_only)
        self.assertEqual(rt.snapshot_value(value),before)

    def test_labelled_for_and_local_cleanup(self):
        p,_=compile_program('p=POS(0,0,0,0,0,0,cfg) FOR i=1 TO 2 DO a=APPROACH(p) ENDFOR',labelled=True)
        state=p.run(); self.assertEqual(state['A'],dict(X=0,Y=0,Z=1))
        self.assertEqual((state['I'],p._state.local_frames,p._state.call_depth),({'uninitialized':True},[],0))

    def test_report_types_locations_and_nonemitting_receiver_lookup(self):
        _,result=compile_program('p=POS(0,0,0,0,0,0,cfg) take(APPROACH(p).z) take(ORIENT(pose).y)',
                                 routines='ROUTINE take(x: REAL) BEGIN seen=x END take')
        rows=result.report['position_axis_queries']
        self.assertEqual([(row['function'],row['operand_type'],row['result_type'],row['body'],row['line']) for row in rows],
                         [('APPROACH','POSITION','VECTOR','T',7),('ORIENT','XYZWPR','VECTOR','T',7)])
        self.assertTrue(all(row['column']>0 and row['evaluated_once'] and row['independent_value'] for row in rows))
        self.assertFalse(result.report['position_axis_policy']['controller_validated']); json.dumps(result.report)

    def test_report_body_for_routine_query(self):
        _,result=compile_program('a=make()',routines='ROUTINE make: VECTOR BEGIN RETURN APPROACH(p) END make')
        self.assertEqual(result.report['position_axis_queries'][0]['body'],'MAKE')

    def test_user_routines_with_query_names_keep_precedence(self):
        p,result=compile_program('total=APPROACH(7)+ORIENT(2)',
                                 routines='ROUTINE APPROACH(n: INTEGER): INTEGER BEGIN RETURN n+1 END APPROACH ROUTINE ORIENT(n: INTEGER): INTEGER BEGIN RETURN n END ORIENT')
        self.assertEqual(p.run()['TOTAL'],10); self.assertEqual(result.report['position_axis_queries'],[])

    def test_query_names_remain_ordinary_variables(self):
        state=execute('APPROACH=7 ORIENT=2 total=APPROACH+ORIENT',declarations=DECLARATIONS+' APPROACH,ORIENT: INTEGER')
        self.assertEqual(state['TOTAL'],9)


class PositionAxisGuardTests(unittest.TestCase):
    def reject(self, body, code='E_TYPE', **options):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**options)
        self.assertEqual(caught.exception.code,code)

    def test_other_operand_types_rejected(self):
        for kind in ('VECTOR','CONFIG','INTEGER','STRING[20]'):
            for name in ('APPROACH','ORIENT'):
                with self.subTest(kind=kind,name=name): self.reject(f'a={name}(value)',declarations=DECLARATIONS+' value: '+kind)

    def test_arity_rejected_in_direct_and_field_contexts(self):
        for name in ('APPROACH','ORIENT'):
            for arguments in ('','p,q'):
                for suffix in ('','.x'):
                    with self.subTest(name=name,arguments=arguments,suffix=suffix):
                        self.reject(('seen=' if suffix else 'a=')+name+'('+arguments+')'+suffix,'E_ARGUMENTS')

    def test_position_orientation_destination_stays_protected(self):
        self.reject('p.approach=APPROACH(q)','E_POSITION_READ_ONLY')
        self.reject('p.orient.x=ORIENT(q).x','E_POSITION_READ_ONLY')

    def test_direct_orientation_reference_remains_blocked(self):
        self.reject('take(p.approach)','E_POSITION_READ_ONLY_ARG',routines='ROUTINE take(v: VECTOR) BEGIN END take')

    def test_incomplete_pose_preserves_destination(self):
        p,_=compile_program('a=VEC(7,8,9) a=APPROACH(p)')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['A'],dict(X=7,Y=8,Z=9))

    def test_invalid_pose_stops_later_expression_effects(self):
        p,_=compile_program("trace='' a=ORIENT(p)+touch()",routines="ROUTINE touch: VECTOR BEGIN trace='touched' RETURN VEC(0,0,0) END touch")
        value=runtime_position(); value.values['NORMAL'].values['X']=2; p._state.values['P']=value
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TRACE'],'')

    def test_failed_query_skips_target_index_effects(self):
        p,_=compile_program("trace='' values[pick()]=APPROACH(p)",declarations=DECLARATIONS+' values: ARRAY[1] OF VECTOR',
                            routines="ROUTINE pick: INTEGER BEGIN trace='picked' RETURN 1 END pick")
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TRACE'],'')

    def test_failure_retains_operand_effects_and_unwinds_frames(self):
        p,_=compile_program("trace='' FOR i=1 TO 2 DO a=ORIENT(make()) ENDFOR",
                            routines="ROUTINE make: POSITION VAR value: POSITION BEGIN trace='made' RETURN value END make")
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['TRACE'],p.snapshot()['I'],p._state.local_frames,p._state.call_depth),('made',{'uninitialized':True},[],0))

    def test_for_counter_transitive_writes_rejected(self):
        self.reject('FOR i=1 TO 2 DO a=APPROACH(touch()) ENDFOR','E_FOR_COUNTER',
                    routines='ROUTINE touch: POSITION BEGIN i=9 RETURN p END touch')

    def test_malformed_nonfinite_and_invalid_config_rejected(self):
        for fault in ('shape','nonfinite','config','unknown','reflection'):
            value=runtime_position()
            if fault=='shape': value.values['EXTRA']=0
            elif fault=='nonfinite': value.values['ORIENT'].values['Y']=float('inf')
            elif fault=='config': value.values['CONFIG_DATA'].values['CFG_TURN_NO1']=8
            elif fault=='unknown': value.values['LOCATION'].values['X']=rt.UNINITIALIZED
            else: value.values['NORMAL'].values['X']=-1
            for name in ('APPROACH','ORIENT'):
                with self.subTest(fault=fault,name=name),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):
                    rt.position_axis(name,value)

    def test_declared_pose_type_guard_remains(self):
        p,_=compile_program('a=APPROACH(p)'); p._state.values['P']=runtime_pose()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'declared pose type'): p.run()

    def test_runtime_dispatch_arity_and_query_name_guards(self):
        with rt._numeric_scope('pythonic'):
            for name in ('APPROACH','ORIENT'):
                for values in ([],[runtime_position(),runtime_position()]):
                    with self.subTest(name=name,values=values),self.assertRaises(rt.KarelRuntimeError): rt.builtin(name,values)
            with self.assertRaises(rt.KarelRuntimeError): rt.position_axis('NORMAL',runtime_position())

    def test_legacy_internal_guards_retained(self):
        for name in ('APPROACH','ORIENT'):
            with self.subTest(name=name): self.reject('a='+name+'(p)','E_CALL',translator=legacy_translate)
            with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): rt.position_axis(name,runtime_position())


class AuthoredPositionAxisTests(unittest.TestCase):
    def test_complete_fixture_output_and_report(self):
        source=Path(__file__).resolve().parents[1]/'examples/pythonic_position_axes.kl'
        result=translate(source.read_text(),filename=source.name); ns={'__name__':'position_axis_fixture'}
        exec(result.python_source,ns); out=[]; p=ns['Program'](write=out.append)
        self.assertEqual(p.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(out,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual([(row['function'],row['operand_type'],row['line']) for row in result.report['position_axis_queries']],
                         [('APPROACH','POSITION',8),('ORIENT','XYZWPR',9),('APPROACH','POSITION',14),('ORIENT','POSITION',14)])
        self.assertEqual(p.source_directives,(('%ENVIRONMENT','VECTR'),))
        self.assertFalse(p._state.values['APP'].read_only)
        self.assertTrue(p._state.values['P'].values['APPROACH'].read_only)
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
