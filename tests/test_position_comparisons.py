"""Explicit pose comparison context, independent rotation math and effect guards."""
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_frame_transforms import CONFIG, INIT, quaternion, quaternion_product, runtime_pose
from tests.test_position_conversions import runtime_position


ROOT=Path(__file__).resolve().parents[1]
DECLARATIONS='cfg: CONFIG p,q: POSITION a,b: XYZWPR near,other: BOOLEAN seen: REAL total,i: INTEGER trace: STRING[20]'


def compile_program(body, *, tolerance=(0.1,0.5,True), declarations=DECLARATIONS, types='', routines='', labelled=False, translator=translate):
    source=f'PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n'+('marker::\n' if labelled else '')+INIT+'\n'+body+'\nEND T'
    result=translator(source,filename='position_comparison.kl'); ns={'__name__':'position_comparison_test'}
    exec(result.python_source,ns)
    return ns['Program'](pose_tolerance=tolerance),result


def execute(body, **options): return compile_program(body,**options)[0].run()


class PositionComparisonMathTests(unittest.TestCase):
    def test_identical_position_and_xyzwpr(self):
        state=execute('a=POS(1,2,3,10,20,30,cfg) p=a near=p>=<p other=a>=<a',tolerance=(0,0,True))
        self.assertTrue(state['NEAR']); self.assertTrue(state['OTHER'])

    def test_mixed_representations_both_orders(self):
        for expression in ('p>=<a','a>=<p'):
            with self.subTest(expression=expression):
                self.assertTrue(execute('a=POS(1,2,3,10,20,30,cfg) p=a near='+expression)['NEAR'])

    def test_location_inclusive_euclidean_boundary(self):
        for tolerance,expected in ((5,True),(4.999999,False)):
            state=execute('a=POS(0,0,0,0,0,0,cfg) b=POS(3,4,0,0,0,0,cfg) near=a>=<b',tolerance=(tolerance,0,True))
            self.assertEqual(state['NEAR'],expected)

    def test_location_uses_distance_rather_than_independent_component_limits(self):
        state=execute('a=POS(0,0,0,0,0,0,cfg) b=POS(0.08,0.08,0,0,0,0,cfg) near=a>=<b')
        self.assertFalse(state['NEAR'])

    def test_orientation_inclusive_boundary(self):
        for angle,expected in ((90,True),(90-1e-8,True),(90+1e-8,False)):
            state=execute(f'a=POS(0,0,0,0,0,0,cfg) b=POS(0,0,0,0,0,{angle},cfg) near=a>=<b',tolerance=(0,90,True))
            self.assertEqual(state['NEAR'],expected)

    def test_wrapped_angles_are_the_same_rotation(self):
        self.assertTrue(execute('a=POS(0,0,0,0,0,0,cfg) b=a b.r=360 near=a>=<b',tolerance=(0,0,True))['NEAR'])

    def test_gimbal_equivalent_angles(self):
        state=execute('a=POS(0,0,0,40,90,20,cfg) b=POS(0,0,0,0,90,-20,cfg) near=a>=<b',tolerance=(0,1e-10,True))
        self.assertTrue(state['NEAR'])

    def test_near_zero_and_half_turn_retain_angle_resolution(self):
        for angle in (1e-9,180-1e-7,180):
            a=runtime_pose(); b=runtime_pose((0,0,0,0,0,angle))
            with self.subTest(angle=angle),rt._numeric_scope('pythonic'):
                self.assertTrue(rt.positions_close(a,b,(0,angle+1e-10 if angle<180 else 180,False)))
                self.assertFalse(rt.positions_close(a,b,(0,angle-1e-10,False)))

    def test_general_rotations_match_independent_quaternion_angles(self):
        rng=random.Random(741)
        for _ in range(60):
            angles=[tuple(rng.uniform(-180,180) for _ in range(3)) for _ in range(2)]
            qa,qb=map(quaternion,angles); delta=quaternion_product((qa[0],-qa[1],-qa[2],-qa[3]),qb)
            expected=math.degrees(2*math.atan2(math.hypot(*delta[1:]),abs(delta[0])))
            for matrix in (False,True):
                a,b=[runtime_position(angle) if matrix else runtime_pose((1,2,3,*angle)) for angle in angles]
                with self.subTest(matrix=matrix,angles=angles),rt._numeric_scope('pythonic'):
                    self.assertTrue(rt.positions_close(a,b,(0,min(180,expected+1e-7),True)))
                    self.assertFalse(rt.positions_close(a,b,(0,max(0,expected-1e-7),True)))

    def test_configuration_check_and_ignore_modes(self):
        for field,value in CONFIG.items():
            a,b=runtime_pose(),runtime_pose(); b.values['CONFIG_DATA'].values[field]=not value if type(value) is bool else value+1
            with self.subTest(field=field),rt._numeric_scope('pythonic'):
                self.assertFalse(rt.positions_close(a,b,(0,0,True)))
                self.assertTrue(rt.positions_close(a,b,(0,0,False)))

    def test_comparison_is_symmetric(self):
        with rt._numeric_scope('pythonic'):
            a=runtime_position((10,20,30)); b=runtime_pose((1.01,2,3,10,20,30.1))
            self.assertEqual(rt.positions_close(a,b,(.1,.5,True)),rt.positions_close(b,a,(.1,.5,True)))


class PositionComparisonContextTests(unittest.TestCase):
    def test_missing_context_errors_when_comparison_executes(self):
        p,_=compile_program('a=POS(0,0,0,0,0,0,cfg) near=a>=<a',tolerance=None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit Program'): p.run()

    def test_missing_context_allowed_when_comparison_is_skipped(self):
        state=execute('near=FALSE AND (a>=<b) other=TRUE OR (p>=<q)',tolerance=None)
        self.assertFalse(state['NEAR']); self.assertTrue(state['OTHER'])

    def test_context_copies_input_and_property_is_immutable(self):
        context=[1,2,False]; p,_=compile_program('',tolerance=context); context[0]=99
        self.assertEqual(p.pose_tolerance,(1.,2.,False))
        with self.assertRaises(AttributeError): p.pose_tolerance=(9,9,True)

    def test_invalid_contexts_rejected_before_execution(self):
        cases=((),(1,2),(1,2,True,4),'1,2,true',{},(True,1,True),(1,False,True),('1',2,True),
               (-1,2,True),(1,-1,True),(1,181,True),(1,2,1),(math.inf,1,True),(1,math.nan,True),(10**1000,1,True))
        for value in cases:
            with self.subTest(value=repr(value)),self.assertRaises(ValueError): compile_program('',tolerance=value)

    def test_instances_keep_independent_context(self):
        p,result=compile_program('a=POS(0,0,0,0,0,0,cfg) b=POS(1,0,0,0,0,0,cfg) near=a>=<b',tolerance=(2,0,True))
        ns={'__name__':'other_context'}; exec(result.python_source,ns); q=ns['Program'](pose_tolerance=(0,0,True))
        self.assertTrue(p.run()['NEAR']); self.assertFalse(q.run()['NEAR']); self.assertTrue(p.run()['NEAR'])

    def test_nested_callback_program_does_not_replace_context(self):
        p,result=compile_program("a=POS(0,0,0,0,0,0,cfg) b=POS(1,0,0,0,0,0,cfg) WRITE('x') near=a>=<b",tolerance=(2,0,True))
        ns={'__name__':'nested_context'}; exec(result.python_source,ns)
        q=ns['Program'](pose_tolerance=(0,0,True))
        observed=[]
        def callback(text): observed.append(q.run()['NEAR'])
        p=type(p)(pose_tolerance=(2,0,True),write=callback)
        self.assertTrue(p.run()['NEAR']); self.assertEqual(observed,[False])


class PositionComparisonIntegrationTests(unittest.TestCase):
    def test_boolean_arguments_return_and_labelled_for(self):
        state=execute('a=POS(0,0,0,0,0,0,cfg) FOR i=1 TO 2 DO near=compare(a) ENDFOR',labelled=True,
                      routines='ROUTINE compare(value: XYZWPR): BOOLEAN BEGIN RETURN value>=<a END compare')
        self.assertTrue(state['NEAR']); self.assertEqual(state['I'],{'uninitialized':True})

    def test_aliases_nested_fields_and_array_elements(self):
        state=execute('box.pose=POS(0,0,0,0,0,0,cfg) points[1]=box.pose near=box.pose>=<points[1]',
                      types='TYPE matrix_t=POSITION box_t=STRUCTURE pose: matrix_t ENDSTRUCTURE',
                      declarations=DECLARATIONS+' box: box_t points: ARRAY[1] OF matrix_t')
        self.assertTrue(state['NEAR'])

    def test_composed_geometry_results(self):
        self.assertTrue(execute('p=POS(1,2,3,0,0,90,cfg) a=POS(0,0,0,0,0,0,cfg) near=(INV(p):p)>=<a')['NEAR'])

    def test_left_operand_captured_before_right_mutation(self):
        state=execute('p=POS(0,0,0,0,0,0,cfg) q=p near=p>=<touch()',
                      routines='ROUTINE touch: POSITION BEGIN p.location.x=99 RETURN q END touch')
        self.assertTrue(state['NEAR']); self.assertEqual(state['P']['LOCATION']['X'],99)

    def test_calls_run_once_in_order(self):
        state=execute("trace='' near=make(1)>=<make(2)",tolerance=(1,0,False),
                      routines="ROUTINE make(n: INTEGER): XYZWPR BEGIN trace=trace+CHR(64+n) RETURN POS(n,0,0,0,0,0,cfg) END make")
        self.assertTrue(state['NEAR']); self.assertEqual(state['TRACE'],'AB')

    def test_result_precedes_target_index_effect(self):
        state=execute('a=POS(0,0,0,0,0,0,cfg) b=a flags[pick()]=a>=<b',declarations=DECLARATIONS+' flags: ARRAY[1] OF BOOLEAN',
                      routines='ROUTINE pick: INTEGER BEGIN b.x=99 RETURN 1 END pick')
        self.assertEqual(state['FLAGS'],[True]); self.assertEqual(state['B']['X'],99)

    def test_write_and_same_precedence_boolean_equality(self):
        p,_=compile_program('a=POS(0,0,0,0,0,0,cfg) near=a>=<a=TRUE WRITE(near,CR)')
        self.assertTrue(p.run()['NEAR']); self.assertEqual([row['text'] for row in p.write_requests],[' TRUE\n'])

    def test_source_report_locations_and_types(self):
        _,result=compile_program('near=p>=<a other=a>=<b')
        rows=result.report['position_comparisons']
        self.assertEqual([(row['operand_types'],row['result_type'],row['body'],row['line']) for row in rows],
                         [(['POSITION','XYZWPR'],'BOOLEAN','T',7),(['XYZWPR','XYZWPR'],'BOOLEAN','T',7)])
        self.assertTrue(all(row['column']>0 and row['evaluated_once'] and row['operands_copied'] for row in rows))
        self.assertFalse(result.report['position_comparison_policy']['controller_validated']); json.dumps(result.report)


class PositionComparisonGuardTests(unittest.TestCase):
    def reject(self,body,code='E_TYPE',**options):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**options)
        self.assertEqual(caught.exception.code,code)

    def test_other_types_remain_blocked(self):
        for kind in ('JOINTPOS','VECTOR','CONFIG','INTEGER','REAL','BOOLEAN','STRING[10]'):
            for expr in ('value>=<value','p>=<value','value>=<p'):
                with self.subTest(kind=kind,expr=expr): self.reject('near='+expr,declarations=DECLARATIONS+' value: '+kind)

    def test_exact_and_ordered_pose_relations_stay_blocked(self):
        for op in ('=','<>','<','<=','>','>='):
            with self.subTest(op=op): self.reject('near=p'+op+'q')

    def test_invalid_left_stops_right_effects(self):
        p,_=compile_program("trace='' near=p>=<touch()",routines="ROUTINE touch: POSITION BEGIN trace='touched' RETURN q END touch")
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TRACE'],'')

    def test_false_location_does_not_hide_invalid_orientation_or_config(self):
        for fault in ('orientation','config'):
            a=runtime_position(); b=runtime_position(location=(100,0,0))
            if fault=='orientation': b.values['NORMAL'].values['X']=2
            else: b.values['CONFIG_DATA'].values['CFG_TURN_NO1']=8
            with self.subTest(fault=fault),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.positions_close(a,b,(0,0,False))

    def test_context_failure_retains_operand_effects_and_skips_target_index(self):
        p,_=compile_program("trace='' flags[pick()]=make(1)>=<make(2)",tolerance=None,declarations=DECLARATIONS+' flags: ARRAY[1] OF BOOLEAN',
                            routines="ROUTINE make(n: INTEGER): XYZWPR BEGIN trace=trace+CHR(64+n) RETURN POS(n,0,0,0,0,0,cfg) END make ROUTINE pick: INTEGER BEGIN trace=trace+'X' RETURN 1 END pick")
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TRACE'],'AB')

    def test_failure_preserves_destination_and_cleans_frames(self):
        p,_=compile_program('near=TRUE FOR i=1 TO 2 DO fail ENDFOR',routines='ROUTINE fail BEGIN near=p>=<q END fail')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertTrue(p.snapshot()['NEAR']); self.assertEqual((p._state.local_frames,p._state.call_depth,p.snapshot()['I']),([],0,{'uninitialized':True}))

    def test_transitive_counter_writes_stay_blocked(self):
        self.reject('FOR i=1 TO 2 DO near=p>=<touch() ENDFOR','E_FOR_COUNTER',routines='ROUTINE touch: POSITION BEGIN i=9 RETURN q END touch')

    def test_declared_pose_type_remains_checked(self):
        p,_=compile_program('near=p>=<q'); p._state.values['P']=runtime_pose()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'declared pose type'): p.run()

    def test_nonfinite_distance_rejected(self):
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):
            rt.positions_close(runtime_pose((1e308,0,0,0,0,0)),runtime_pose((-1e308,0,0,0,0,0)),(1e308,180,False))

    def test_legacy_internal_rejection_retained(self):
        self.reject('near=p>=<q','E_OPERATOR',translator=legacy_translate)
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): rt.positions_close(runtime_pose(),runtime_pose(),(0,0,False))


class PositionComparisonCliTests(unittest.TestCase):
    def run_script(self,arguments,source=None):
        source=source or 'PROGRAM T VAR cfg: CONFIG a: XYZWPR near: BOOLEAN BEGIN '+INIT+' a=POS(0,0,0,0,0,0,cfg) near=a>=<a END T'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); package=root/'karel2py'; package.mkdir()
            for name in ('__init__.py','runtime.py','extended.py','storage.py','kinematics.py','scheduling.py'): shutil.copyfile(ROOT/'karel2py'/name,package/name)
            script=root/'converted.py'; script.write_text(translate(source).python_source,encoding='utf-8')
            (root/'input.json').write_text('[[7]]',encoding='utf-8')
            return subprocess.run([sys.executable,str(script),*arguments],cwd=root,capture_output=True,text=True)

    def test_cli_explicit_check_config(self):
        process=self.run_script(['--location-tolerance-mm','0','--orientation-tolerance-deg','0','--check-config'])
        self.assertEqual(process.returncode,0,process.stderr); self.assertIn("'NEAR': True",process.stdout)

    def test_cli_ignore_config(self):
        process=self.run_script(['--location-tolerance-mm','1','--orientation-tolerance-deg','180','--ignore-config'])
        self.assertEqual(process.returncode,0,process.stderr)

    def test_cli_missing_or_conflicting_context_rejected(self):
        for arguments in ([],['--location-tolerance-mm','1','--orientation-tolerance-deg','1'],
                          ['--location-tolerance-mm','1','--orientation-tolerance-deg','1','--check-config','--ignore-config']):
            with self.subTest(arguments=arguments): self.assertEqual(self.run_script(arguments).returncode,2)

    def test_cli_invalid_bounds_are_usage_errors(self):
        for location,angle in (('-1','0'),('nan','1'),('inf','1'),('1','181'),('1','-1')):
            with self.subTest(location=location,angle=angle):
                process=self.run_script(['--location-tolerance-mm',location,'--orientation-tolerance-deg',angle,'--check-config'])
                self.assertEqual(process.returncode,2); self.assertNotIn('Traceback',process.stderr)

    def test_cli_read_context_combines_with_comparison_context(self):
        source='PROGRAM T VAR cfg: CONFIG a: XYZWPR near: BOOLEAN n: INTEGER BEGIN '+INIT+' READ(n) a=POS(0,0,0,0,0,0,cfg) near=a>=<a END T'
        process=self.run_script(['--read-values','input.json','--location-tolerance-mm','0','--orientation-tolerance-deg','0','--check-config'],source)
        self.assertEqual(process.returncode,0,process.stderr); self.assertIn("'N': 7",process.stdout)


class AuthoredPositionComparisonTests(unittest.TestCase):
    def test_complete_fixture_output_and_context(self):
        source=ROOT/'examples/pythonic_position_comparisons.kl'; result=translate(source.read_text(),filename=source.name)
        ns={'__name__':'comparison_fixture'}; exec(result.python_source,ns); out=[]
        context=json.loads(source.with_suffix('.context.expected.json').read_text()); p=ns['Program'](write=out.append,**context)
        self.assertEqual(p.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(out,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual(p.pose_tolerance,(.1,.5,True)); self.assertEqual(len(result.report['position_comparisons']),4)
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
