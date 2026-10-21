"""Data-only XYZWPR/CONFIG/VECTOR behavior, copy ownership and fail-closed limits."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError

ROOT = Path(__file__).resolve().parents[1]


def init_config(name='c'):
    return ' '.join(f'{name}.{field}=0' for field in ('cfg_turn_no1','cfg_turn_no2','cfg_turn_no3')) + ' ' + ' '.join(f'{name}.{field}=OFF' for field in ('cfg_flip','cfg_left','cfg_up','cfg_front'))


def init_pose(name='p'):
    return ' '.join(f'{name}.{field}={value}' for field,value in zip(('x','y','z','w','p','r'),(1,2,3,0,90,180))) + ' ' + init_config(name+'.config_data')


def compile_program(body='', *, declarations='v,w: VECTOR\np,q: XYZWPR\nc,d: CONFIG\nresult: REAL\nflag: BOOLEAN', prefix='', routines=''):
    result = translate(f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T', filename='data_records.kl')
    namespace = {'__name__':'data_records_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


class DataRecordTypeTests(unittest.TestCase):
    def test_vector_fields(self):
        program,_=compile_program('v.x=1 v.y=2.5 v.z=-3')
        self.assertEqual(program.run()['V'],dict(X=1.0,Y=2.5,Z=-3.0))
    def test_xyzwpr_fields(self):
        program,_=compile_program(init_pose())
        point=program.run()['P']
        self.assertEqual({k:point[k] for k in ('X','Y','Z','W','P','R')},dict(X=1.0,Y=2.0,Z=3.0,W=0.0,P=90.0,R=180.0))
        self.assertEqual(point['CONFIG_DATA']['CFG_TURN_NO1'],0)
    def test_config_turn_boundaries(self):
        program,_=compile_program('c.cfg_turn_no1=-8 c.cfg_turn_no2=7 c.cfg_turn_no3=0')
        config=program.run()['C']
        self.assertEqual([config[name] for name in ('CFG_TURN_NO1','CFG_TURN_NO2','CFG_TURN_NO3')],[-8,7,0])
    def test_config_boolean_fields(self):
        program,_=compile_program('c.cfg_flip=ON c.cfg_left=OFF c.cfg_up=ON c.cfg_front=OFF')
        config=program.run()['C']
        self.assertEqual([config[name] for name in ('CFG_FLIP','CFG_LEFT','CFG_UP','CFG_FRONT')],[True,False,True,False])
    def test_case_insensitive_fields(self):
        program,_=compile_program('P.Config_Data.Cfg_Flip=ON p.X=1.25')
        point=program.run()['P']
        self.assertTrue(point['CONFIG_DATA']['CFG_FLIP'])
        self.assertEqual(point['X'],1.25)
    def test_uninitialized_leaves_snapshot(self):
        program,_=compile_program()
        snapshot=program.run()
        self.assertEqual(snapshot['V'],dict.fromkeys(('X','Y','Z'),{'uninitialized':True}))
        self.assertEqual(snapshot['P']['CONFIG_DATA']['CFG_FLIP'],{'uninitialized':True})
    def test_scalar_uninit_fields(self):
        program,_=compile_program('flag=UNINIT(p.x) p.x=1 result=p.x')
        self.assertEqual((program.run()['FLAG'],program._state.snapshot()['RESULT']),(True,1.0))
    def test_config_scalar_uninit(self):
        program,_=compile_program('flag=UNINIT(c.cfg_turn_no1) c.cfg_turn_no1=0')
        self.assertTrue(program.run()['FLAG'])
    def test_nested_structure_fields(self):
        program,_=compile_program('item.pose.x=1.5 item.offset.z=-2 item.configuration.cfg_left=ON',prefix='TYPE item_t=STRUCTURE pose: XYZWPR offset: VECTOR configuration: CONFIG ENDSTRUCTURE',declarations='item: item_t')
        item=program.run()['ITEM']
        self.assertEqual((item['POSE']['X'],item['OFFSET']['Z'],item['CONFIGURATION']['CFG_LEFT']),(1.5,-2.0,True))
    def test_multidimensional_record_array(self):
        program,_=compile_program('items[2,1].x=3 items[1,2].config_data.cfg_front=ON',declarations='items: ARRAY[2,2] OF XYZWPR')
        items=program.run()['ITEMS']
        self.assertEqual(items[1][0]['X'],3.0)
        self.assertTrue(items[0][1]['CONFIG_DATA']['CFG_FRONT'])
    def test_named_record_array(self):
        program,_=compile_program('items[1,2].x=7',prefix='TYPE row_t=ARRAY[2] OF VECTOR',declarations='items: ARRAY[2] OF row_t')
        self.assertEqual(program.run()['ITEMS'][0][1]['X'],7.0)
    def test_fresh_local_records(self):
        program,_=compile_program('visit visit',routines='ROUTINE visit VAR local: VECTOR BEGIN flag=UNINIT(local.x) local.x=7 END visit')
        self.assertTrue(program.run()['FLAG'])
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_continuation_field_line(self):
        program,result=compile_program('p.config_data. &\n cfg_flip=ON')
        self.assertTrue(program.run()['P']['CONFIG_DATA']['CFG_FLIP'])
        self.assertEqual(len(result.report['continuations']),1)
    def test_data_record_policy_report(self):
        _,result=compile_program()
        policy=result.report['data_record_policy']
        self.assertEqual(set(policy['types']),{'XYZWPR','CONFIG','VECTOR','POSITION','XYZWPREXT'})
        self.assertEqual(policy['fields']['XYZWPR']['CONFIG_DATA'],('CONFIG',))
        self.assertEqual(policy['config_turn_range'],[-8,7])
        self.assertFalse(policy['controller_validated'])


class DataRecordCopyTests(unittest.TestCase):
    def test_vector_copy_is_independent(self):
        program,_=compile_program('v.x=1 v.y=2 v.z=3 w=v v.x=9')
        state=program.run()
        self.assertEqual((state['V']['X'],state['W']['X']),(9.0,1.0))
    def test_pose_copy_is_deep(self):
        program,_=compile_program(init_pose()+' q=p p.x=9 p.config_data.cfg_flip=ON')
        state=program.run()
        self.assertEqual((state['Q']['X'],state['Q']['CONFIG_DATA']['CFG_FLIP']),(1.0,False))
    def test_config_copy_is_independent(self):
        program,_=compile_program(init_config()+' d=c c.cfg_turn_no1=7')
        self.assertEqual(program.run()['D']['CFG_TURN_NO1'],0)
    def test_partial_copy_does_not_mutate_destination(self):
        program,_=compile_program('v.x=1 w.x=9 w.y=8 w.z=7 w=v')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program._state.snapshot()['W'],dict(X=9.0,Y=8.0,Z=7.0))
    def test_pose_copy_requires_config_initialized(self):
        program,_=compile_program('p.x=1 p.y=2 p.z=3 p.w=0 p.p=0 p.r=0 q=p')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program._state.snapshot()['Q']['X'],{'uninitialized':True})
    def test_config_copy_requires_every_flag(self):
        program,_=compile_program('c.cfg_turn_no1=0 d=c')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
    def test_record_array_copy(self):
        body='a[1].x=1 a[1].y=2 a[1].z=3 a[2]=a[1] b=a a[1].x=9'
        program,_=compile_program(body,declarations='a,b: ARRAY[2] OF VECTOR')
        state=program.run()
        self.assertEqual((state['A'][0]['X'],state['B'][0]['X']),(9.0,1.0))
    def test_record_array_partial_copy_atomic(self):
        program,_=compile_program('a[1].x=1 b[1].x=9 b=a',declarations='a,b: ARRAY[2] OF VECTOR')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program._state.snapshot()['B'][0]['X'],9.0)
    def test_captured_real_alias_survives_pose_copy(self):
        program,_=compile_program(init_pose()+' update(q.x,q)',routines='ROUTINE update(field: REAL; target: XYZWPR) BEGIN target=p field=9 END update')
        state=program.run()
        self.assertEqual((state['P']['X'],state['Q']['X']),(1.0,9.0))
    def test_captured_config_alias_survives_pose_copy(self):
        program,_=compile_program(init_pose()+' update(q.config_data,q)',routines='ROUTINE update(configuration: CONFIG; target: XYZWPR) BEGIN target=p configuration.cfg_flip=ON END update')
        self.assertTrue(program.run()['Q']['CONFIG_DATA']['CFG_FLIP'])
    def test_structure_containing_records_copies(self):
        program,_=compile_program('a.value.x=1 a.value.y=2 a.value.z=3 b=a a.value.x=9',prefix='TYPE t=STRUCTURE value: VECTOR ENDSTRUCTURE',declarations='a,b: t')
        self.assertEqual(program.run()['B']['VALUE']['X'],1.0)
    def test_array_allocation_counts_all_record_leaves(self):
        self.assertEqual(rt.scalar_leaf_count(('ARRAY',2,('XYZWPR',))),26)
        with self.assertRaises(rt.KarelRuntimeError): rt.Array(('ARRAY',3000,('XYZWPR',)))


class ConfigPassingTests(unittest.TestCase):
    def test_turn_field_is_always_value(self):
        program,_=compile_program('c.cfg_turn_no1=0 change(c.cfg_turn_no1)',routines='ROUTINE change(x: INTEGER) BEGIN x=7 END change')
        self.assertEqual(program.run()['C']['CFG_TURN_NO1'],0)
    def test_boolean_field_is_always_value(self):
        program,_=compile_program('c.cfg_flip=OFF change(c.cfg_flip)',routines='ROUTINE change(x: BOOLEAN) BEGIN x=ON END change')
        self.assertFalse(program.run()['C']['CFG_FLIP'])
    def test_nested_pose_config_is_value(self):
        program,_=compile_program('p.config_data.cfg_left=OFF change(p.config_data.cfg_left)',routines='ROUTINE change(x: BOOLEAN) BEGIN x=ON END change')
        self.assertFalse(program.run()['P']['CONFIG_DATA']['CFG_LEFT'])
    def test_array_config_is_value(self):
        program,_=compile_program('items[2].cfg_turn_no1=-8 change(items[2].cfg_turn_no1)',declarations='items: ARRAY[2] OF CONFIG',routines='ROUTINE change(x: INTEGER) BEGIN x=7 END change')
        self.assertEqual(program.run()['ITEMS'][1]['CFG_TURN_NO1'],-8)
    def test_config_reference_forwarding_retains_value_subfields(self):
        routines='ROUTINE change(x: INTEGER) BEGIN x=7 END change\nROUTINE forward(value: CONFIG) BEGIN change(value.cfg_turn_no1) value.cfg_up=ON END forward'
        program,_=compile_program('c.cfg_turn_no1=0 forward(c)',routines=routines)
        config=program.run()['C']
        self.assertEqual((config['CFG_TURN_NO1'],config['CFG_UP']),(0,True))
    def test_config_integer_to_real_is_value(self):
        program,_=compile_program('c.cfg_turn_no1=2 change(c.cfg_turn_no1)',routines='ROUTINE change(x: REAL) BEGIN result=x x=7 END change')
        state=program.run()
        self.assertEqual((state['C']['CFG_TURN_NO1'],state['RESULT']),(2,2.0))
    def test_uninitialized_subfield_fails_and_unwinds(self):
        program,_=compile_program('forward(c)',routines='ROUTINE change(x: INTEGER) BEGIN x=7 END change\nROUTINE forward(value: CONFIG) BEGIN change(value.cfg_turn_no1) END forward')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_real_components_still_pass_by_reference(self):
        program,_=compile_program('p.x=1 change(p.x)',routines='ROUTINE change(x: REAL) BEGIN x=2 END change')
        self.assertEqual(program.run()['P']['X'],2.0)
    def test_whole_vector_reference(self):
        program,_=compile_program('change(v)',routines='ROUTINE change(x: VECTOR) BEGIN x.z=3 END change')
        self.assertEqual(program.run()['V']['Z'],3.0)
    def test_record_array_formal(self):
        program,_=compile_program('change(items)',declarations='items: ARRAY[2] OF VECTOR',routines='ROUTINE change(x: ARRAY OF VECTOR) BEGIN x[2].y=5 END change')
        self.assertEqual(program.run()['ITEMS'][1]['Y'],5.0)
    def test_config_subscript_evaluated_once(self):
        routines='ROUTINE next_index: INTEGER BEGIN n=n+1 RETURN 1 END next_index\nROUTINE change(x: INTEGER) BEGIN x=7 END change'
        program,_=compile_program('n=0 items[1].cfg_turn_no1=0 change(items[next_index()].cfg_turn_no1)',declarations='items: ARRAY[1] OF CONFIG\nn: INTEGER',routines=routines)
        self.assertEqual(program.run()['N'],1)
    def test_config_argument_report(self):
        _,result=compile_program('c.cfg_turn_no1=0 change(c.cfg_turn_no1)',routines='ROUTINE change(x: INTEGER) BEGIN x=7 END change')
        site=result.report['config_subfield_arguments'][0]
        self.assertEqual((site['routine'],site['parameter'],site['field'],site['evaluated_once']),('CHANGE','X','CFG_TURN_NO1',True))
        self.assertEqual(result.report['routine_effects']['CHANGE']['parameters'][0]['passing_modes'],['reference','value'])


class DataRecordGuardTests(unittest.TestCase):
    def reject(self,body='',code='E_TYPE',**kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**kwargs)
        self.assertEqual(caught.exception.code,code)
    def test_other_position_types_stay_blocked(self):
        for kind in ('FILE','PATH','VISION','QUEUE_TYPE'):
            with self.subTest(kind=kind): self.reject(declarations=f'x: {kind}')
    def test_group_qualifier_stays_blocked(self): self.reject(declarations='p: XYZWPR IN GROUP[1]',code='E_POSITION_GROUP')
    def test_builtin_using_stays_blocked(self): self.reject('USING p DO x=1 ENDUSING',code='E_USING_TYPE')
    def test_unknown_field(self): self.reject('p.ext1=1',code='E_FIELD')
    def test_wrong_real_field_type(self): self.reject('v.x=ON')
    def test_wrong_config_flag_type(self): self.reject('c.cfg_flip=1')
    def test_wrong_config_turn_type(self): self.reject('c.cfg_turn_no1=1.5')
    def test_distinct_record_types_not_interchangeable(self): self.reject('v=p')
    def test_structural_lookalike_not_interchangeable(self): self.reject('v=other',prefix='TYPE look=STRUCTURE x: REAL y: REAL z: REAL ENDSTRUCTURE',declarations='v: VECTOR\nother: look')
    def test_positional_value_parameters_require_initialized_contents(self):
        for kind in ('XYZWPR','CONFIG'):
            with self.subTest(kind=kind):
                program,_=compile_program('change((x))',declarations=f'x: {kind}',routines=f'ROUTINE change(p: {kind}) BEGIN END change')
                with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
    def test_direct_string_results_remain_blocked(self): self.reject(code='E_RETURN_TYPE',routines='ROUTINE f: STRING[3] BEGIN END f')
    def test_aggregate_uninit_blocked(self):
        for name in ('v','p','c'):
            with self.subTest(name=name): self.reject(f'flag=UNINIT({name})')
    def test_vector_operators_not_silently_componentwise(self):
        for operator in ('*','/','<','<=','>','>='):
            with self.subTest(operator=operator),self.assertRaises(TranslationError): compile_program(f'v=v{operator}w')
    def test_configuration_conversion_output_blocked(self): self.reject("CNV_STR_INT('1',c.cfg_turn_no1)",code='E_CONFIG_OUTPUT')
    def test_config_out_of_range_before_storage_mutation(self):
        for value in (-9,8):
            with self.subTest(value=value):
                program,_=compile_program(f'c.cfg_turn_no1=0 c.cfg_turn_no1={value}')
                with self.assertRaisesRegex(rt.KarelRuntimeError,'-8..7'): program.run()
                self.assertEqual(program._state.snapshot()['C']['CFG_TURN_NO1'],0)
    def test_pythonic_real_field_accepts_decimal(self):
        self.assertEqual(compile_program('v.x=0.1')[0].run()['V']['X'], .1)
    def test_copy_bound_prevents_large_record_array(self): self.reject(declarations='items: ARRAY[3000] OF XYZWPR',code='E_ARRAY_CAPACITY')
    def test_cross_type_formal_conversion_blocked(self): self.reject('change(v)',routines='ROUTINE change(x: XYZWPR) BEGIN END change')
    def test_record_write_blocked(self): self.reject('WRITE(p)')
    def test_config_effects_remain_conservative(self): self.reject('result=f()+1',code='E_EVALUATION_ORDER',routines='ROUTINE f: REAL BEGIN c.cfg_flip=ON RETURN 1 END f')


class DataRecordRuntimeTests(unittest.TestCase):
    def test_builtin_identity_has_no_user_type_name(self):
        self.assertEqual(rt.initial_value(('VECTOR',)).spec,('VECTOR',))
        with self.assertRaises(rt.KarelRuntimeError): rt.checked(('CONFIG',),rt.initial_value(('VECTOR',)),17)
    def test_no_group_metadata_in_runtime_spec(self):
        with self.assertRaises(rt.KarelRuntimeError): rt.initial_value(('XYZWPR',1))
    def test_config_strict_runtime_turn_type(self):
        config=rt.initial_value(('CONFIG',))
        for value in (True,1.0,'1',None,8,-9):
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError): rt.field_reference(config,'CFG_TURN_NO1').set(value,17)
    def test_config_strict_runtime_flag_type(self):
        config=rt.initial_value(('CONFIG',))
        for value in (0,1,'TRUE',None):
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError): rt.field_reference(config,'CFG_FLIP').set(value,17)
    def test_malformed_config_copy_range_rechecked(self):
        config=rt.initial_value(('CONFIG',))
        for name,spec in rt.record_fields(('CONFIG',)): rt.field_reference(config,name).set(0 if spec==rt.INTEGER else False)
        config.values['CFG_TURN_NO1']=8
        with self.assertRaises(rt.KarelRuntimeError) as caught: rt.checked(('CONFIG',),config,17)
        self.assertEqual(caught.exception.line,17)
    def test_unknown_runtime_field(self):
        with self.assertRaises(rt.KarelRuntimeError): rt.field_reference(rt.initial_value(('VECTOR',)),'W',17)


class DataRecordCLITests(unittest.TestCase):
    def test_generated_example(self):
        result=translate((ROOT/'examples/cartesian_data.kl').read_text())
        namespace={'__name__':'cartesian_example_test'}
        exec(result.python_source,namespace)
        state=namespace['Program']().run()
        self.assertEqual((state['POINT']['X'],state['SAVED_POINT']['X'],state['OBSERVED']),(1.25,99.0,-7.75))
        self.assertTrue(state['CONFIG_VALUE_UNCHANGED'])
        self.assertFalse(state['POINT']['CONFIG_DATA']['CFG_FLIP'])
        self.assertTrue(state['CONFIG_COPY']['CFG_FLIP'])
    def test_cli_generates_data_records(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            source=target/'source.kl'
            source.write_text('PROGRAM T VAR v: VECTOR BEGIN v.x=1 END T')
            process=subprocess.run([sys.executable,'-m','karel2py',str(source),'-o',str(target/'converted.py'),'--report',str(target/'report.json')],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            report=json.loads((target/'report.json').read_text())
            self.assertIn('VECTOR data record',report['features'])
            namespace={'__name__':'record_cli_test'}
            exec((target/'converted.py').read_text(),namespace)
            self.assertEqual(namespace['Program']().run()['V']['X'],1.0)


if __name__=='__main__': unittest.main()
