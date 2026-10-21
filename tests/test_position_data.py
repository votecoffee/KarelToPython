"""POSITION access protection and XYZWPREXT data, without frame conversions.

Seeded orientation tests use an explicit synthetic host fixture solely to check
protection/copy behavior. No source constructor or controller data is inferred.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_data_records import init_config,init_pose

ROOT=Path(__file__).resolve().parents[1]


def compile_program(body='',*,declarations='p,q: POSITION\next,other: XYZWPREXT\nv: VECTOR\nresult: REAL\nflag: BOOLEAN',prefix='',routines=''):
    result=translate(f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T',filename='position_data.kl')
    namespace={'__name__':'position_test'}
    exec(result.python_source,namespace)
    return namespace['Program'](),result


def init_extended(name='ext'):
    return init_pose(name)+f' {name}.ext1=7 {name}.ext2=-8 {name}.ext3=0.5'


def init_location(name='p'):
    return f'{name}.location.x=1 {name}.location.y=2 {name}.location.z=3 '+init_config(name+'.config_data')


def seed_orientation(record):
    for row,name in enumerate(('NORMAL','ORIENT','APPROACH')):
        record.values[name].values.update({axis:float(row==column) for column,axis in enumerate(('X','Y','Z'))})


class PositionFieldTests(unittest.TestCase):
    def test_writable_location_components(self):
        program,_=compile_program('p.location.x=1.25 p.location.y=-2 p.location.z=3')
        self.assertEqual(program.run()['P']['LOCATION'],dict(X=1.25,Y=-2.0,Z=3.0))
    def test_whole_location_assignment(self):
        program,_=compile_program('v.x=1 v.y=2 v.z=3 p.location=v v.x=9')
        self.assertEqual(program.run()['P']['LOCATION']['X'],1.0)
    def test_config_fields_writable(self):
        program,_=compile_program('p.config_data.cfg_turn_no1=-8 p.config_data.cfg_flip=ON')
        self.assertEqual(program.run()['P']['CONFIG_DATA']['CFG_TURN_NO1'],-8)
    def test_whole_config_assignment(self):
        program,_=compile_program(init_config('p.config_data')+' q.config_data=p.config_data p.config_data.cfg_flip=ON')
        self.assertFalse(program.run()['Q']['CONFIG_DATA']['CFG_FLIP'])
    def test_no_orientation_defaults_fabricated(self):
        program,_=compile_program()
        snapshot=program.run()['P']
        for name in ('NORMAL','ORIENT','APPROACH'):
            self.assertEqual(snapshot[name],dict.fromkeys(('X','Y','Z'),{'uninitialized':True}))
    def test_read_uninitialized_orientation_fails(self):
        program,_=compile_program('result=p.normal.x')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
    def test_scalar_orientation_uninit_query(self):
        program,_=compile_program('flag=UNINIT(p.orient.y)')
        self.assertTrue(program.run()['FLAG'])
    def test_seeded_orientation_read(self):
        program,_=compile_program('result=p.normal.x+p.orient.y+p.approach.z')
        seed_orientation(program._state.values['P'])
        self.assertEqual(program.run()['RESULT'],3.0)
    def test_detached_orientation_copy_is_writable(self):
        program,_=compile_program('v=p.normal v.x=9 result=p.normal.x')
        seed_orientation(program._state.values['P'])
        state=program.run()
        self.assertEqual((state['V']['X'],state['RESULT']),(9.0,1.0))
    def test_explicit_scalar_orientation_value_argument(self):
        program,_=compile_program('accept((p.normal.x))',routines='ROUTINE accept(x: REAL) BEGIN result=x x=9 END accept')
        seed_orientation(program._state.values['P'])
        state=program.run()
        self.assertEqual((state['RESULT'],state['P']['NORMAL']['X']),(1.0,1.0))
    def test_scalar_expression_argument(self):
        program,_=compile_program('accept(p.normal.x+1)',routines='ROUTINE accept(x: REAL) BEGIN result=x END accept')
        seed_orientation(program._state.values['P'])
        self.assertEqual(program.run()['RESULT'],2.0)
    def test_position_reference_parameter(self):
        program,_=compile_program('change(p)',routines='ROUTINE change(x: POSITION) BEGIN x.location.z=7 END change')
        self.assertEqual(program.run()['P']['LOCATION']['Z'],7.0)
    def test_location_component_reference_parameter(self):
        program,_=compile_program('p.location.x=1 change(p.location.x)',routines='ROUTINE change(x: REAL) BEGIN x=7 END change')
        self.assertEqual(program.run()['P']['LOCATION']['X'],7.0)
    def test_position_config_scalar_still_value(self):
        program,_=compile_program('p.config_data.cfg_turn_no1=0 change(p.config_data.cfg_turn_no1)',routines='ROUTINE change(x: INTEGER) BEGIN x=7 END change')
        self.assertEqual(program.run()['P']['CONFIG_DATA']['CFG_TURN_NO1'],0)
    def test_location_conversion_output(self):
        program,_=compile_program("CNV_STR_REAL('2.5',p.location.x)")
        self.assertEqual(program.run()['P']['LOCATION']['X'],2.5)
    def test_position_in_structure(self):
        program,_=compile_program('item.frame.location.z=3',prefix='TYPE holder=STRUCTURE frame: POSITION ENDSTRUCTURE',declarations='item: holder')
        self.assertEqual(program.run()['ITEM']['FRAME']['LOCATION']['Z'],3.0)
    def test_multidimensional_position_array(self):
        program,_=compile_program('items[2,1].location.x=7',declarations='items: ARRAY[2,2] OF POSITION')
        self.assertEqual(program.run()['ITEMS'][1][0]['LOCATION']['X'],7.0)
    def test_position_array_formal(self):
        program,_=compile_program('change(items)',declarations='items: ARRAY[2] OF POSITION',routines='ROUTINE change(x: ARRAY OF POSITION) BEGIN x[2].location.x=7 END change')
        self.assertEqual(program.run()['ITEMS'][1]['LOCATION']['X'],7.0)
    def test_named_position_array(self):
        program,_=compile_program('items[1].location.x=7',prefix='TYPE positions=ARRAY[2] OF POSITION',declarations='items: positions')
        self.assertEqual(program.run()['ITEMS'][0]['LOCATION']['X'],7.0)
    def test_new_policy_report(self):
        _,result=compile_program()
        policy=result.report['data_record_policy']
        self.assertIn('read-only recursively',policy['position'])
        self.assertIn('No orientation defaults',policy['position_initialization'])
        self.assertIn('EXT1/EXT2/EXT3',policy['extended'])
        self.assertFalse(policy['controller_validated'])
    def test_receiver_checks_do_not_duplicate_argument_sites_or_execution(self):
        routines='ROUTINE next_slot(turn: INTEGER): INTEGER BEGIN n=n+1 RETURN 1 END next_slot\nROUTINE inspect(value: REAL) BEGIN result=value END inspect'
        program,result=compile_program('n=0 c.cfg_turn_no1=0 items[1].location.x=7 inspect(items[next_slot(c.cfg_turn_no1)].location.x)',declarations='items: ARRAY[1] OF POSITION\nc: CONFIG\nn: INTEGER\nresult: REAL',routines=routines)
        state=program.run()
        self.assertEqual((state['N'],state['RESULT']),(1,7.0))
        self.assertEqual(len(result.report['config_subfield_arguments']),1)


class PositionGuardTests(unittest.TestCase):
    def reject(self,body='',code='E_POSITION_READ_ONLY',**kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**kwargs)
        self.assertEqual(caught.exception.code,code)
    def test_orientation_vector_assignment_blocked(self):
        for name in ('normal','orient','approach'):
            with self.subTest(name=name): self.reject(f'p.{name}=v')
    def test_orientation_scalar_assignment_blocked(self):
        for name in ('normal','orient','approach'):
            for axis in ('x','y','z'):
                with self.subTest(name=name,axis=axis): self.reject(f'p.{name}.{axis}=1')
    def test_nested_structure_readonly_target(self): self.reject('item.frame.normal.x=1',prefix='TYPE holder=STRUCTURE frame: POSITION ENDSTRUCTURE',declarations='item: holder')
    def test_array_readonly_target(self): self.reject('items[2,1].orient.z=1',declarations='items: ARRAY[2,2] OF POSITION')
    def test_readonly_conversion_output(self): self.reject("CNV_STR_REAL('1.0',p.normal.x)")
    def test_bare_scalar_orientation_argument_blocked(self): self.reject('change(p.normal.x)',code='E_POSITION_READ_ONLY_ARG',routines='ROUTINE change(x: REAL) BEGIN x=9 END change')
    def test_bare_whole_orientation_argument_blocked(self): self.reject('change(p.normal)',code='E_POSITION_READ_ONLY_ARG',routines='ROUTINE change(x: VECTOR) BEGIN x.x=9 END change')
    def test_readonly_callee_is_also_guarded(self): self.reject('change(p.normal.x)',code='E_POSITION_READ_ONLY_ARG',routines='ROUTINE change(x: REAL) BEGIN result=x END change')
    def test_grouped_orientation_value_requires_initialized_contents(self):
        program,_=compile_program('change((p.normal))',routines='ROUTINE change(x: VECTOR) BEGIN END change')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
    def test_grouped_whole_position_value_requires_initialized_contents(self):
        program,_=compile_program('change((p))',routines='ROUTINE change(x: POSITION) BEGIN END change')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
    def test_continued_readonly_diagnostic_location(self):
        with self.assertRaises(TranslationError) as caught: compile_program('p.normal. &\n x=1')
        self.assertEqual(caught.exception.code,'E_POSITION_READ_ONLY')
        self.assertEqual(caught.exception.token.line,11)
    def test_group_qualifier_still_blocked(self): self.reject(code='E_POSITION_GROUP',declarations='p: POSITION IN GROUP[1]')
    def test_cross_type_conversion_still_blocked(self): self.reject('p=ext',code='E_TYPE')
    def test_position_constructor_not_synthesized(self): self.reject('p=POS(0,0,0,0,0,0,ext.config_data)',code='E_TYPE')
    def test_whole_uninit_still_blocked(self): self.reject('flag=UNINIT(p)',code='E_TYPE')
    def test_position_using_still_blocked(self): self.reject('USING p DO x=1 ENDUSING',code='E_USING_TYPE')
    def test_partial_position_copy_guard_preserves_destination(self):
        program,_=compile_program('q.location.x=9 p.location.x=1 q=p')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program._state.snapshot()['Q']['LOCATION']['X'],9.0)
    def test_partial_orientation_copy_guard(self):
        program,_=compile_program('v=p.normal')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
    def test_position_record_leaf_count(self):
        self.assertEqual(rt.scalar_leaf_count(('POSITION',)),19)
        with self.assertRaises(rt.KarelRuntimeError): rt.Array(('ARRAY',1725,('POSITION',)))


class PositionRuntimeProtectionTests(unittest.TestCase):
    def test_top_level_orientation_set_and_clear_guarded(self):
        position=rt.initial_value(('POSITION',))
        for name in rt.POSITION_READ_ONLY_FIELDS:
            reference=rt.field_reference(position,name,17)
            with self.assertRaises(rt.KarelRuntimeError) as caught: reference.set(rt.initial_value(('VECTOR',)))
            self.assertEqual(caught.exception.line,17)
            with self.assertRaises(rt.KarelRuntimeError): reference.clear()
    def test_nested_component_set_and_clear_guarded(self):
        position=rt.initial_value(('POSITION',))
        vector=rt.raw_field(position,'NORMAL')
        reference=rt.field_reference(vector,'X',17)
        with self.assertRaises(rt.KarelRuntimeError): reference.set(1)
        with self.assertRaises(rt.KarelRuntimeError): reference.clear()
    def test_clone_preserves_position_protection(self):
        position=rt.initial_value(('POSITION',))
        copied=position.clone()
        with self.assertRaises(rt.KarelRuntimeError): rt.field_reference(rt.raw_field(copied,'ORIENT'),'Y').set(1)
    def test_detached_vector_clone_is_writable(self):
        position=rt.initial_value(('POSITION',))
        seed_orientation(position)
        vector=rt.checked(('VECTOR',),rt.load_field(position,'NORMAL'))
        rt.field_reference(vector,'X').set(9)
        self.assertEqual(rt.load_field(rt.load_field(position,'NORMAL'),'X'),1.0)
        self.assertEqual(rt.load_field(vector,'X'),9.0)
    def test_full_position_copy_keeps_alias_and_protection(self):
        program,_=compile_program(init_location()+' copy(q.location.x,q)',routines='ROUTINE copy(field: REAL; target: POSITION) BEGIN target=p field=99 END copy')
        seed_orientation(program._state.values['P'])
        orientation=rt.raw_field(program._state.values['Q'],'APPROACH')
        state=program.run()
        self.assertEqual((state['P']['LOCATION']['X'],state['Q']['LOCATION']['X']),(1.0,99.0))
        self.assertIs(orientation,rt.raw_field(program._state.values['Q'],'APPROACH'))
        with self.assertRaises(rt.KarelRuntimeError): rt.field_reference(orientation,'Z').set(7)
    def test_full_position_copy_is_independent(self):
        program,_=compile_program(init_location()+' q=p q.config_data.cfg_flip=ON q.location.z=9')
        seed_orientation(program._state.values['P'])
        state=program.run()
        self.assertFalse(state['P']['CONFIG_DATA']['CFG_FLIP'])
        self.assertEqual(state['P']['LOCATION']['Z'],3.0)
        with self.assertRaises(rt.KarelRuntimeError): rt.field_reference(rt.raw_field(program._state.values['Q'],'NORMAL'),'X').set(9)
    def test_copied_nested_structure_keeps_protection(self):
        program,_=compile_program(init_location('a.frame')+' b=a',prefix='TYPE holder=STRUCTURE frame: POSITION ENDSTRUCTURE',declarations='a,b: holder')
        seed_orientation(program._state.values['A'].values['FRAME'])
        program.run()
        frame=program._state.values['B'].values['FRAME']
        with self.assertRaises(rt.KarelRuntimeError): rt.field_reference(rt.raw_field(frame,'NORMAL'),'X').set(9)
    def test_copied_position_array_keeps_protection(self):
        program,_=compile_program(init_location('a[1]')+' b=a',declarations='a,b: ARRAY[1] OF POSITION')
        seed_orientation(program._state.values['A'].values[0])
        program.run()
        frame=program._state.values['B'].values[0]
        with self.assertRaises(rt.KarelRuntimeError): rt.field_reference(rt.raw_field(frame,'NORMAL'),'X').set(9)
    def test_location_does_not_become_readonly_after_clone(self):
        copied=rt.initial_value(('POSITION',)).clone()
        rt.field_reference(rt.raw_field(copied,'LOCATION'),'X').set(7)
        self.assertEqual(rt.load_field(rt.raw_field(copied,'LOCATION'),'X'),7.0)


class ExtendedPositionTests(unittest.TestCase):
    def test_three_extended_axes(self):
        program,_=compile_program('ext.ext1=7 ext.ext2=-8 ext.ext3=0.5')
        state=program.run()['EXT']
        self.assertEqual([state[name] for name in ('EXT1','EXT2','EXT3')],[7.0,-8.0,0.5])
    def test_whole_extended_copy(self):
        program,_=compile_program(init_extended()+' other=ext ext.ext1=99 ext.config_data.cfg_flip=ON')
        state=program.run()
        self.assertEqual((state['OTHER']['EXT1'],state['OTHER']['CONFIG_DATA']['CFG_FLIP']),(7.0,False))
    def test_extended_reference_parameter(self):
        program,_=compile_program('change(ext)',routines='ROUTINE change(x: XYZWPREXT) BEGIN x.ext3=7 END change')
        self.assertEqual(program.run()['EXT']['EXT3'],7.0)
    def test_extended_real_field_reference(self):
        program,_=compile_program('ext.ext1=0 change(ext.ext1)',routines='ROUTINE change(x: REAL) BEGIN x=7 END change')
        self.assertEqual(program.run()['EXT']['EXT1'],7.0)
    def test_extended_config_field_value_isolation(self):
        program,_=compile_program('ext.config_data.cfg_flip=OFF change(ext.config_data.cfg_flip)',routines='ROUTINE change(x: BOOLEAN) BEGIN x=ON END change')
        self.assertFalse(program.run()['EXT']['CONFIG_DATA']['CFG_FLIP'])
    def test_extended_array_copy(self):
        program,_=compile_program(init_extended('a[1]')+' b=a a[1].ext2=9',declarations='a,b: ARRAY[1] OF XYZWPREXT')
        self.assertEqual(program.run()['B'][0]['EXT2'],-8.0)
    def test_extended_array_formal(self):
        program,_=compile_program('change(items)',declarations='items: ARRAY[2] OF XYZWPREXT',routines='ROUTINE change(x: ARRAY OF XYZWPREXT) BEGIN x[2].ext1=3 END change')
        self.assertEqual(program.run()['ITEMS'][1]['EXT1'],3.0)
    def test_extended_copy_requires_every_extra_axis(self):
        program,_=compile_program(init_pose('ext')+' other=ext')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
    def test_extended_leaf_count(self): self.assertEqual(rt.scalar_leaf_count(('XYZWPREXT',)),16)
    def test_extended_wrong_field_type(self):
        with self.assertRaises(TranslationError): compile_program('ext.ext1=ON')
    def test_extended_pythonic_real_field(self):
        self.assertEqual(compile_program('ext.ext1=0.1')[0].run()['EXT']['EXT1'], .1)
    def test_extended_group_still_blocked(self):
        with self.assertRaises(TranslationError) as caught: compile_program(declarations='ext: XYZWPREXT IN GROUP[1]')
        self.assertEqual(caught.exception.code,'E_POSITION_GROUP')
    def test_extended_distinct_from_xyzwpr(self):
        with self.assertRaises(TranslationError): compile_program('a=b',declarations='a: XYZWPREXT\nb: XYZWPR')
    def test_generated_example(self):
        result=translate((ROOT/'examples/position_data.kl').read_text())
        namespace={'__name__':'position_example_test'}
        exec(result.python_source,namespace)
        state=namespace['Program']().run()
        self.assertEqual((state['FRAME']['LOCATION']['X'],state['SAVED']['EXT1'],state['OBSERVED']),(10.0,99.0,10.5))
        self.assertTrue(state['ORIENTATION_UNKNOWN'])
        self.assertTrue(state['CONFIG_VALUE_UNCHANGED'])


class PositionCLITests(unittest.TestCase):
    def test_cli_accepts_writable_position_field(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            source=target/'source.kl'
            source.write_text('PROGRAM T VAR p: POSITION BEGIN p.location.x=1 END T')
            result=subprocess.run([sys.executable,'-m','karel2py',str(source),'-o',str(target/'converted.py'),'--report',str(target/'report.json')],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('POSITION data record',json.loads((target/'report.json').read_text())['features'])
    def test_cli_rejects_readonly_write_without_output(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            source=target/'source.kl'
            source.write_text('PROGRAM T VAR p: POSITION BEGIN p.normal.x=1 END T')
            result=subprocess.run([sys.executable,'-m','karel2py',str(source),'-o',str(target/'converted.py'),'--report',str(target/'report.json')],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertFalse((target/'converted.py').exists())
            self.assertEqual(json.loads((target/'report.json').read_text())['diagnostics'][0]['code'],'E_POSITION_READ_ONLY')


if __name__=='__main__': unittest.main()
