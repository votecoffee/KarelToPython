"""Opaque joint data and degree-only conversions with explicit offline context."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate,runtime as rt
from karel2py.lexer import TranslationError

ROOT=Path(__file__).resolve().parents[1]
FILL='a[1]=1.25 a[2]=-2.5 a[3]=3'
LOAD='CNV_REL_JPOS(a,j,s)'


def compile_program(body='',*,declarations='a,b: ARRAY[3] OF REAL\nj,k: JOINTPOS3\ns: INTEGER\nflag: BOOLEAN',prefix='',routines='',joint_axes=3):
    result=translate(f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T',filename='joint_data.kl')
    namespace={'__name__':'joint_test'}
    exec(result.python_source,namespace)
    return namespace['Program'](joint_axes=joint_axes),result


class JointDataTests(unittest.TestCase):
    def test_all_declared_widths(self):
        for width in range(1,10):
            with self.subTest(width=width):
                program,_=compile_program(declarations=f'j: JOINTPOS{width}',joint_axes=None)
                self.assertEqual(program.run()['J'],{'axes':[{'uninitialized':True}]*width})
    def test_unsuffixed_width_is_nine_not_configured_count(self):
        program,_=compile_program(declarations='j: JOINTPOS',joint_axes=3)
        self.assertEqual(len(program.run()['J']['axes']),9)
    def test_default_and_nine_are_same_declared_type(self):
        program,result=compile_program(declarations='j: JOINTPOS\nk: JOINTPOS9',joint_axes=None)
        self.assertEqual(program._state.types['J'],program._state.types['K'])
    def test_unknown_joint_initialization_query(self):
        program,_=compile_program('flag=UNINIT(j)',joint_axes=None)
        self.assertTrue(program.run()['FLAG'])
    def test_loaded_joint_initialization_query(self):
        program,_=compile_program(FILL+' '+LOAD+' flag=UNINIT(j)')
        self.assertFalse(program.run()['FLAG'])
    def test_roundtrip_exact_degrees(self):
        program,_=compile_program(FILL+' '+LOAD+' CNV_JPOS_REL(j,b,s)')
        state=program.run()
        self.assertEqual((state['J'],state['B'],state['S']),({'axes':[1.25,-2.5,3.0]},[1.25,-2.5,3.0],0))
    def test_one_axis(self):
        program,_=compile_program('a[1]=7 CNV_REL_JPOS(a,j,s) CNV_JPOS_REL(j,b,s)',declarations='a,b: ARRAY[1] OF REAL\nj: JOINTPOS1\ns: INTEGER',joint_axes=1)
        self.assertEqual(program.run()['B'],[7.0])
    def test_nine_axis_default_roundtrip(self):
        body=' '.join(f'a[{i}]={i}' for i in range(1,10))+' CNV_REL_JPOS(a,j,s) CNV_JPOS_REL(j,b,s)'
        program,_=compile_program(body,declarations='a,b: ARRAY[9] OF REAL\nj: JOINTPOS\ns: INTEGER',joint_axes=9)
        self.assertEqual(program.run()['B'],[float(i) for i in range(1,10)])
    def test_input_excess_uninitialized_values_ignored(self):
        program,_=compile_program(FILL+' '+LOAD,declarations='a: ARRAY[5] OF REAL\nj: JOINTPOS3\ns: INTEGER')
        state=program.run()
        self.assertEqual(state['J']['axes'],[1.25,-2.5,3.0])
        self.assertEqual(state['A'][4],{'uninitialized':True})
    def test_short_output_gets_prefix(self):
        program,_=compile_program(FILL+' '+LOAD+' CNV_JPOS_REL(j,b,s)',declarations='a: ARRAY[3] OF REAL\nb: ARRAY[2] OF REAL\nj: JOINTPOS3\ns: INTEGER')
        self.assertEqual(program.run()['B'],[1.25,-2.5])
    def test_output_excess_preserved(self):
        program,_=compile_program(FILL+' '+LOAD+' b[4]=91 CNV_JPOS_REL(j,b,s)',declarations='a: ARRAY[3] OF REAL\nb: ARRAY[5] OF REAL\nj: JOINTPOS3\ns: INTEGER')
        self.assertEqual(program.run()['B'],[1.25,-2.5,3.0,91.0,{'uninitialized':True}])
    def test_copy_is_independent(self):
        program,_=compile_program(FILL+' '+LOAD+' k=j a[1]=7 '+LOAD)
        state=program.run()
        self.assertEqual((state['J']['axes'][0],state['K']['axes'][0]),(7.0,1.25))
    def test_joint_field_and_structure_copy(self):
        program,_=compile_program(FILL+' CNV_REL_JPOS(a,first.joint,s) second=first a[1]=7 CNV_REL_JPOS(a,first.joint,s)',prefix='TYPE holder=STRUCTURE joint: JOINTPOS3 ENDSTRUCTURE',declarations='a: ARRAY[3] OF REAL\nfirst,second: holder\ns: INTEGER')
        self.assertEqual(program.run()['SECOND']['JOINT']['axes'],[1.25,-2.5,3.0])
    def test_joint_array_copy(self):
        program,_=compile_program(FILL+' CNV_REL_JPOS(a,first[1],s) second=first a[1]=7 CNV_REL_JPOS(a,first[1],s)',declarations='a: ARRAY[3] OF REAL\nfirst,second: ARRAY[1] OF JOINTPOS3\ns: INTEGER')
        self.assertEqual(program.run()['SECOND'][0]['axes'],[1.25,-2.5,3.0])
    def test_named_joint_array(self):
        program,_=compile_program(FILL+' CNV_REL_JPOS(a,items[1],s)',prefix='TYPE joints_t=ARRAY[2] OF JOINTPOS3',declarations='a: ARRAY[3] OF REAL\nitems: joints_t\ns: INTEGER')
        self.assertEqual(program.run()['ITEMS'][0]['axes'],[1.25,-2.5,3.0])
    def test_joint_reference_formal(self):
        program,_=compile_program(FILL+' load(j)',routines='ROUTINE load(target: JOINTPOS3) BEGIN CNV_REL_JPOS(a,target,s) END load')
        self.assertEqual(program.run()['J']['axes'],[1.25,-2.5,3.0])
    def test_real_array_formal_inherits_size(self):
        program,_=compile_program(FILL+' load(a,j,s)',routines='ROUTINE load(values: ARRAY OF REAL; target: JOINTPOS3; status: INTEGER) BEGIN CNV_REL_JPOS(values,target,status) END load')
        self.assertEqual(program.run()['S'],0)
    def test_joint_array_formal(self):
        program,_=compile_program(FILL+' load(items)',declarations='a: ARRAY[3] OF REAL\nitems: ARRAY[1] OF JOINTPOS3\ns: INTEGER',routines='ROUTINE load(values: ARRAY OF JOINTPOS3) BEGIN CNV_REL_JPOS(a,values[1],s) END load')
        self.assertEqual(program.run()['ITEMS'][0]['axes'],[1.25,-2.5,3.0])
    def test_local_joint_starts_unknown_on_each_call(self):
        program,_=compile_program('visit visit',routines='ROUTINE visit VAR local: JOINTPOS3 BEGIN flag=UNINIT(local) END visit')
        self.assertTrue(program.run()['FLAG'])
        self.assertEqual(program._state.local_frames,[])
    def test_named_subarray_real_input(self):
        program,_=compile_program('a[1,1]=1 a[1,2]=2 a[1,3]=3 CNV_REL_JPOS(a[1],j,s)',prefix='TYPE row_t=ARRAY[3] OF REAL',declarations='a: ARRAY[1] OF row_t\nj: JOINTPOS3\ns: INTEGER')
        self.assertEqual(program.run()['J']['axes'],[1.0,2.0,3.0])
    def test_named_subarray_real_output(self):
        program,_=compile_program(FILL+' '+LOAD+' CNV_JPOS_REL(j,b[1],s)',prefix='TYPE row_t=ARRAY[3] OF REAL',declarations='a: ARRAY[3] OF REAL\nb: ARRAY[1] OF row_t\nj: JOINTPOS3\ns: INTEGER')
        self.assertEqual(program.run()['B'],[[1.25,-2.5,3.0]])
    def test_report_declared_width_and_context(self):
        _,result=compile_program(FILL+' '+LOAD)
        self.assertEqual(result.report['joint_conversions'][0]['declared_axes'],3)
        self.assertEqual(result.report['joint_conversions'][0]['output_parameters'],[2,3])
        self.assertEqual(result.report['joint_policy']['default_declared_axes'],9)
        self.assertFalse(result.report['joint_policy']['controller_validated'])
    def test_both_output_effects_reported(self):
        _,result=compile_program('',routines='ROUTINE load(values: ARRAY OF REAL; target: JOINTPOS3; status: INTEGER) BEGIN CNV_REL_JPOS(values,target,status) END load')
        effect=result.report['routine_effects']['LOAD']
        self.assertEqual(effect['potential_parameter_writes'],['STATUS','TARGET'])
        self.assertTrue(effect['potential_external_writes'])
    def test_both_effects_forward_transitively(self):
        routines='ROUTINE load(values: ARRAY OF REAL; target: JOINTPOS3; status: INTEGER) BEGIN CNV_REL_JPOS(values,target,status) END load\nROUTINE forward(values: ARRAY OF REAL; target: JOINTPOS3; status: INTEGER) BEGIN load(values,target,status) END forward'
        _,result=compile_program('',routines=routines)
        self.assertEqual(result.report['routine_effects']['FORWARD']['potential_parameter_writes'],['STATUS','TARGET'])
    def test_joint_leaf_count(self): self.assertEqual(rt.scalar_leaf_count(('ARRAY',3,('JOINTPOS',6))),18)
    def test_destination_joint_storage_is_stable(self):
        program,_=compile_program(FILL+' '+LOAD)
        original=program._state.values['J']
        program.run()
        self.assertIs(program._state.values['J'],original)


class JointGuardTests(unittest.TestCase):
    def reject(self,body='',code='E_TYPE',**kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**kwargs)
        self.assertEqual(caught.exception.code,code)
    def test_invalid_width_names(self):
        for name in ('JOINTPOS0','JOINTPOS10'):
            with self.subTest(name=name): self.reject(declarations=f'j: {name}')
    def test_group_qualifier(self): self.reject(code='E_POSITION_GROUP',declarations='j: JOINTPOS3 IN GROUP[1]')
    def test_direct_joint_index_not_invented(self): self.reject('s=j[1]')
    def test_direct_joint_fields_not_invented(self): self.reject('j.j1=1')
    def test_joint_value_argument_requires_initialized_axes(self):
        program,_=compile_program('load((j))',routines='ROUTINE load(value: JOINTPOS3) BEGIN END load')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'initialized axes'): program.run()
    def test_width_conversion_argument_blocked(self): self.reject('load(j)',routines='ROUTINE load(value: JOINTPOS6) BEGIN END load')
    def test_width_conversion_copy_blocked(self): self.reject('j=k',declarations='j: JOINTPOS3\nk: JOINTPOS6')
    def test_joint_result_fallthrough_is_guarded(self):
        program,_=compile_program('j=f()',routines='ROUTINE f: JOINTPOS3 BEGIN END f')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'without RETURN'): program.run()
    def test_cartesian_conversion_blocked(self): self.reject('p=j',declarations='p: XYZWPR\nj: JOINTPOS3')
    def test_integer_array_input_not_promoted(self): self.reject(LOAD,declarations='a: ARRAY[3] OF INTEGER\nj: JOINTPOS3\ns: INTEGER')
    def test_multidimensional_real_input_blocked(self): self.reject(LOAD,declarations='a: ARRAY[1,3] OF REAL\nj: JOINTPOS3\ns: INTEGER')
    def test_narrow_status_blocked(self): self.reject('CNV_REL_JPOS(a,j,item.value)',prefix='TYPE holder=STRUCTURE value: SHORT ENDSTRUCTURE',declarations='a: ARRAY[3] OF REAL\nj: JOINTPOS3\nitem: holder')
    def test_config_status_blocked(self): self.reject('CNV_REL_JPOS(a,j,c.cfg_turn_no1)',code='E_CONFIG_OUTPUT',declarations='a: ARRAY[3] OF REAL\nj: JOINTPOS3\nc: CONFIG')
    def test_grouped_source_blocked(self): self.reject('CNV_REL_JPOS((a),j,s)',code='E_JOINT_ARGUMENT')
    def test_constant_output_blocked(self): self.reject('CNV_REL_JPOS(a,j,C)',code='E_JOINT_ARGUMENT',prefix='CONST C=0')
    def test_wrong_argument_count(self): self.reject('CNV_REL_JPOS(a,j)',code='E_ARGUMENTS')
    def test_function_call_in_arguments_blocked(self): self.reject('CNV_REL_JPOS(a,items[indexer()],s)',code='E_EVALUATION_ORDER',declarations='a: ARRAY[3] OF REAL\nitems: ARRAY[1] OF JOINTPOS3\ns: INTEGER',routines='ROUTINE indexer: INTEGER BEGIN RETURN 1 END indexer')
    def test_conversion_is_not_function(self):
        with self.assertRaises(TranslationError): compile_program('s=CNV_REL_JPOS(a,j,s)')
    def test_active_counter_status_blocked(self): self.reject('FOR s=1 TO 2 DO CNV_REL_JPOS(a,j,s) ENDFOR',code='E_FOR_COUNTER')
    def test_conversion_effectful_function_in_operator_blocked(self): self.reject('s=f()+1',code='E_EVALUATION_ORDER',routines='ROUTINE f: INTEGER BEGIN CNV_REL_JPOS(a,j,s) RETURN 1 END f')
    def test_missing_context_before_mutation(self):
        program,_=compile_program(FILL+' s=17 '+LOAD,joint_axes=None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit Program'): program.run()
        self.assertEqual((program._state.snapshot()['S'],rt.uninit(program._state.values['J'])),(17,True))
    def test_declared_width_must_match_context(self):
        program,_=compile_program(FILL+' s=17 '+LOAD,joint_axes=6)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'declared width'): program.run()
        self.assertEqual(program._state.snapshot()['S'],17)
    def test_short_input_before_mutation(self):
        program,_=compile_program('a[1]=1 s=17 '+LOAD,declarations='a: ARRAY[2] OF REAL\nj: JOINTPOS3\ns: INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'smaller'): program.run()
        self.assertEqual((program._state.snapshot()['S'],rt.uninit(program._state.values['J'])),(17,True))
    def test_required_input_unknown_preserves_prior_joint_and_status(self):
        program,_=compile_program(FILL+' '+LOAD)
        program.run()
        program._state.values['A'].values[1]=rt.UNINITIALIZED
        program._state.values['S']=17
        with self.assertRaises(rt.KarelRuntimeError): program._state.joint_conversion('CNV_REL_JPOS',program._state.values['A'],program._state.reference('J'),program._state.reference('S'),17)
        self.assertEqual((program._state.snapshot()['J']['axes'],program._state.snapshot()['S']),([1.25,-2.5,3.0],17))
    def test_unknown_joint_output_preserves_array_and_status(self):
        program,_=compile_program('b[1]=9 s=17 CNV_JPOS_REL(j,b,s)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'initialized'): program.run()
        self.assertEqual((program._state.snapshot()['B'][0],program._state.snapshot()['S']),(9.0,17))
    def test_unknown_joint_copy_fails(self):
        program,_=compile_program('k=j')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertTrue(rt.uninit(program._state.values['K']))
    def test_partial_joint_array_copy_fails_atomically(self):
        program,_=compile_program('second=first',declarations='first,second: ARRAY[1] OF JOINTPOS3')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertTrue(rt.uninit(program._state.values['SECOND'].values[0]))
    def test_failed_routine_conversion_unwinds(self):
        program,_=compile_program('load(j)',routines='ROUTINE load(target: JOINTPOS3) BEGIN CNV_REL_JPOS(a,target,s) END load')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_invalid_context_types(self):
        for value in (False,True,0,10,-1,3.0,'3'):
            with self.subTest(value=value),self.assertRaises(ValueError): compile_program(joint_axes=value)
    def test_joint_allocation_limit(self):
        with self.assertRaises(rt.KarelRuntimeError): rt.Array(('ARRAY',4000,('JOINTPOS',9)))


class JointRuntimeAndCLITests(unittest.TestCase):
    def test_runtime_invalid_specs(self):
        for spec in (('JOINTPOS',),('JOINTPOS',0),('JOINTPOS',10),('JOINTPOS',True),('JOINTPOS',3,1)):
            with self.subTest(spec=spec),self.assertRaises(rt.KarelRuntimeError): rt.initial_value(spec)
    def test_runtime_context_guard(self):
        state=rt.State({}, {})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit Program'): state.joint_conversion('CNV_REL_JPOS',None,None,None,17)
    def test_runtime_bad_status_before_joint_mutation(self):
        state=rt.State({'A':('ARRAY',1,('REAL',)),'J':('JOINTPOS',1)}, {},joint_axes=1)
        state.values['A'].set(1,7)
        with self.assertRaises(rt.KarelRuntimeError): state.joint_conversion('CNV_REL_JPOS',state.values['A'],state.reference('J'),rt.value_argument(('REAL',),0),17)
        self.assertTrue(rt.uninit(state.values['J']))
    def test_runtime_bad_real_axis_before_outputs(self):
        state=rt.State({'A':('ARRAY',1,('REAL',)),'J':('JOINTPOS',1),'S':('INTEGER',)}, {},joint_axes=1)
        state.values['A'].values[0]=True
        with self.assertRaises(rt.KarelRuntimeError): state.joint_conversion('CNV_REL_JPOS',state.values['A'],state.reference('J'),state.reference('S'),17)
        self.assertTrue(rt.uninit(state.values['J']))
        self.assertIs(state.values['S'],rt.UNINITIALIZED)
    def test_malformed_nested_joint_copy_guard(self):
        spec=('STRUCTURE','HOLDER',(('J',('JOINTPOS',1)),))
        value=rt.initial_value(spec)
        value.values['J'].values[:]=[True]
        with self.assertRaises(rt.KarelRuntimeError): rt.checked(spec,value,17)
    def test_generated_example(self):
        result=translate((ROOT/'examples/joint_data.kl').read_text())
        namespace={'__name__':'joint_example_test'}
        exec(result.python_source,namespace)
        state=namespace['Program'](joint_axes=3).run()
        self.assertEqual((state['JOINT']['axes'],state['SAVED']['axes']),([7.0,-2.5,3.0],[1.25,-2.5,3.0]))
        self.assertEqual(state['READ_BACK'],[7.0,-2.5,3.0,91.0,92.0])
        self.assertEqual(state['PREFIX'],[7.0,-2.5])
        self.assertEqual((state['WAS_UNKNOWN'],state['IS_UNKNOWN'],state['TAIL_UNKNOWN'],state['STATUS']),(True,False,True,0))
    def test_generated_cli_accepts_explicit_context(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'joint.py'
            result=translate('PROGRAM T VAR a: ARRAY[1] OF REAL j: JOINTPOS1 s: INTEGER BEGIN a[1]=7 CNV_REL_JPOS(a,j,s) END T')
            path.write_text(result.python_source)
            env=__import__('os').environ.copy()
            env['PYTHONPATH']=str(ROOT)
            process=subprocess.run([sys.executable,str(path),'--joint-axes','1'],env=env,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertIn("'axes': [7.0]",process.stdout)
    def test_generated_cli_requires_context_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'joint.py'
            path.write_text(translate('PROGRAM T VAR a: ARRAY[1] OF REAL j: JOINTPOS1 s: INTEGER BEGIN CNV_REL_JPOS(a,j,s) END T').python_source)
            env=__import__('os').environ.copy()
            env['PYTHONPATH']=str(ROOT)
            process=subprocess.run([sys.executable,str(path)],env=env,capture_output=True,text=True)
            self.assertEqual(process.returncode,2)
            self.assertIn('--joint-axes',process.stderr)
            self.assertEqual(process.stdout,'')


if __name__=='__main__': unittest.main()
