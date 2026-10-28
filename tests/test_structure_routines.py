"""Named STRUCTURE values: identity, full initialization, deep ownership and effects."""
import ast
import unittest
from karel2py import translate,runtime as rt
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError

TYPES='''TYPE child_t=STRUCTURE count: INTEGER label: STRING[3] ENDSTRUCTURE
row_t=ARRAY[2] OF INTEGER
packet_t=STRUCTURE child: child_t values: row_t enabled: BOOLEAN ENDSTRUCTURE
other_t=STRUCTURE count: INTEGER label: STRING[3] ENDSTRUCTURE'''
FACTORY="""ROUTINE build(number: INTEGER): packet_t
VAR local: packet_t
BEGIN local.child.count=number local.child.label='abcde'
local.values[1]=number local.values[2]=number+1 local.enabled=ON RETURN local END build"""
CHANGE='ROUTINE change(p: packet_t) BEGIN p.child.count=99 p.values[1]=77 END change'
UNKNOWN={'uninitialized':True}

def packet(number=1): return dict(CHILD=dict(COUNT=number,LABEL='abc'),VALUES=[number,number+1],ENABLED=True)

def initialize(name='a',number=1):
    return f"{name}.child.count={number} {name}.child.label='abc' {name}.values[1]={number} {name}.values[2]={number+1} {name}.enabled=ON"

def compile_program(body='',*,types=TYPES,declarations='a,b: packet_t n: INTEGER flag: BOOLEAN',routines='',labelled=False, _translator=translate):
    label='entry::\n' if labelled else ''
    result=_translator(f'PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n{label}{body}\nEND T',filename='structure_routines.kl')
    ast.parse(result.python_source,feature_version=(3,11))
    namespace={'__name__':'structure_value_test'}; exec(result.python_source,namespace)
    return namespace['Program'](),result

def execute(body='',**kwargs): return compile_program(body,**kwargs)[0].run()

def initialized_host(spec):
    """Synthetic storage fixture only; not controller state/acquisition evidence."""
    kind=spec[0]
    if kind in rt.RECORD_TYPES:
        value=rt.Structure(spec)
        for name,field in rt.record_fields(spec): value.values[name]=rt.replace_value(value.values[name],initialized_host(field))
        return value
    if kind=='ARRAY':
        value=rt.Array(spec); value.values[:]=[initialized_host(spec[2]) for _ in value.values]; return value
    if kind=='JOINTPOS':
        value=rt.JointPosition(spec); value.values[:]=[1.0]*rt.joint_width(spec); return value
    return {'INTEGER':1,'BYTE':1,'SHORT':1,'BOOLEAN':False,'REAL':1.0,'STRING':'a'}[kind]


class StructureReturnTests(unittest.TestCase):
    def test_local_record_return(self): self.assertEqual(execute('a=build(1)',routines=FACTORY)['A'],packet())
    def test_nested_fields_and_string_capacity_survive_return(self): self.assertEqual(execute('a=build(7)',routines=FACTORY)['A'],packet(7))
    def test_global_return_is_detached(self):
        state=execute(initialize()+' b=get() a.child.count=9',routines='ROUTINE get: packet_t BEGIN RETURN a END get')
        self.assertEqual(state['B'],packet())
    def test_reference_formal_return_is_detached(self):
        state=execute(initialize()+' b=get(a) a.values[1]=9',routines='ROUTINE get(p: packet_t): packet_t BEGIN RETURN p END get')
        self.assertEqual(state['B'],packet())
    def test_nested_return(self): self.assertEqual(execute('a=outer()',routines=FACTORY+'\nROUTINE outer: packet_t BEGIN RETURN build(3) END outer')['A'],packet(3))
    def test_recursive_frame_ownership(self):
        routine=FACTORY+'\nROUTINE recurse(number: INTEGER): packet_t VAR local: packet_t BEGIN IF number=0 THEN RETURN build(1) ENDIF local=recurse(number-1) local.child.count=local.child.count+number RETURN local END recurse'
        expected=packet(); expected['CHILD']['COUNT']=7
        self.assertEqual(execute('a=recurse(3)',routines=routine)['A'],expected)
    def test_forward_routine_declaration(self):
        self.assertEqual(execute('a=outer()',routines='ROUTINE outer: packet_t BEGIN RETURN build(2) END outer\n'+FACTORY)['A'],packet(2))
    def test_record_field_result(self):
        state=execute(initialize()+' child=get()',declarations='a: packet_t child: child_t',routines='ROUTINE get: child_t BEGIN RETURN a.child END get')
        self.assertEqual(state['CHILD'],packet()['CHILD'])
    def test_array_element_result(self):
        state=execute(initialize('items[1]')+' items[2]=get()',declarations='items: ARRAY[2] OF packet_t',routines='ROUTINE get: packet_t BEGIN RETURN items[1] END get')
        self.assertEqual(state['ITEMS'],[packet(),packet()])
    def test_case_insensitive_return_type(self): self.assertEqual(execute('a=build(1)',routines=FACTORY.replace(': packet_t',': pAcKeT_t'))['A'],packet())
    def test_labelled_function_return(self):
        self.assertEqual(execute('a=get()',routines=FACTORY+'\nROUTINE get: packet_t BEGIN GOTO answer answer:: RETURN build(1) END get')['A'],packet())
    def test_select_function_return(self):
        routine=FACTORY+'\nROUTINE choose(number: INTEGER): packet_t BEGIN SELECT number OF CASE(1): RETURN build(1) ELSE: RETURN build(2) ENDSELECT END choose'
        self.assertEqual(execute('a=choose(2)',routines=routine)['A'],packet(2))
    def test_early_return_from_fresh_local_for(self):
        routine=FACTORY+'\nROUTINE get: packet_t VAR i: INTEGER BEGIN FOR i=1 TO 3 DO RETURN build((i)) ENDFOR END get'
        self.assertEqual(execute('a=get()',routines=routine)['A'],packet())
    def test_return_copy_before_frame_cleanup(self):
        program,_=compile_program('a=build(1)',routines=FACTORY); program.run()
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))
    def test_host_return_object_does_not_alias_globals(self):
        program,_=compile_program(initialize(),routines='ROUTINE get: packet_t BEGIN RETURN a END get'); program.run()
        result=program._routine_GET(); result.values['CHILD'].values['COUNT']=99
        self.assertEqual(program.snapshot()['A'],packet())


class StructureValueArgumentTests(unittest.TestCase):
    def test_bare_reference_changes_source(self):
        state=execute(initialize()+' change(a)',routines=CHANGE)
        self.assertEqual((state['A']['CHILD']['COUNT'],state['A']['VALUES'][0]),(99,77))
    def test_grouped_argument_preserves_source(self): self.assertEqual(execute(initialize()+' change((a))',routines=CHANGE)['A'],packet())
    def test_nested_grouping_preserves_source(self): self.assertEqual(execute(initialize()+' change(((a)))',routines=CHANGE)['A'],packet())
    def test_returned_value_argument(self):
        routine=FACTORY+'\nROUTINE revise(p: packet_t): packet_t BEGIN p.child.count=99 RETURN p END revise'
        expected=packet(2); expected['CHILD']['COUNT']=99
        self.assertEqual(execute('a=revise(build(2))',routines=routine)['A'],expected)
    def test_grouped_nested_record(self):
        state=execute(initialize()+' update((a.child))',routines='ROUTINE update(p: child_t) BEGIN p.count=99 END update')
        self.assertEqual(state['A'],packet())
    def test_grouped_array_element(self):
        self.assertEqual(execute(initialize('items[1]')+' change((items[1]))',declarations='items: ARRAY[1] OF packet_t',routines=CHANGE)['ITEMS'][0],packet())
    def test_repeated_values_do_not_alias(self):
        state=execute(initialize()+' work((a),(a))',routines='ROUTINE work(p,q: packet_t) BEGIN p.child.count=99 n=q.child.count END work')
        self.assertEqual((state['A'],state['N']),(packet(),1))
    def test_mixed_bare_reference_and_copy(self):
        state=execute(initialize()+' work(a,(a))',routines='ROUTINE work(p,q: packet_t) BEGIN p.child.count=99 n=q.child.count END work')
        self.assertEqual((state['A']['CHILD']['COUNT'],state['N']),(99,1))
    def test_reference_forwarding_uses_owned_temporary(self):
        routine=CHANGE+'\nROUTINE forward(p: packet_t) BEGIN change(p) n=p.child.count END forward'
        state=execute(initialize()+' forward((a))',routines=routine)
        self.assertEqual((state['A'],state['N']),(packet(),99))
    def test_grouped_forwarding_makes_second_copy(self):
        routine=CHANGE+'\nROUTINE forward(p: packet_t) BEGIN change((p)) n=p.child.count END forward'
        state=execute(initialize()+' forward((a))',routines=routine)
        self.assertEqual((state['A'],state['N']),(packet(),1))
    def test_captured_nested_field_survives_whole_temporary_assignment(self):
        routine=FACTORY+'\nROUTINE inner(p: packet_t; field: INTEGER) BEGIN p=build(2) field=99 END inner\nROUTINE forward(p: packet_t) BEGIN inner(p,p.child.count) n=p.child.count END forward'
        state=execute(initialize()+' forward((a))',routines=routine)
        self.assertEqual((state['A'],state['N']),(packet(),99))
    def test_captured_named_array_survives_whole_temporary_assignment(self):
        routine=FACTORY+'\nROUTINE inner(p: packet_t; values: row_t) BEGIN p=build(2) values[2]=99 END inner\nROUTINE forward(p: packet_t) BEGIN inner(p,p.values) n=p.values[2] END forward'
        state=execute(initialize()+' forward((a))',routines=routine)
        self.assertEqual((state['A'],state['N']),(packet(),99))
    def test_value_function_argument_evaluated_once(self):
        routine=FACTORY+'\nROUTINE counted: packet_t BEGIN n=n+1 RETURN build(2) END counted\n'+CHANGE
        self.assertEqual(execute('n=0 change(counted())',routines=routine)['N'],1)
    def test_value_index_evaluated_once(self):
        routine='ROUTINE next_index: INTEGER BEGIN n=n+1 RETURN 1 END next_index\n'+CHANGE
        self.assertEqual(execute(initialize('items[1]')+' n=0 change((items[next_index()]))',declarations='items: ARRAY[1] OF packet_t n: INTEGER',routines=routine)['N'],1)
    def test_pure_record_factory_and_scalar_consumer_in_operator(self):
        routine=FACTORY+'\nROUTINE number(p: packet_t): INTEGER BEGIN RETURN p.child.count END number'
        self.assertEqual(execute('n=number(build(2))+1',routines=routine)['N'],3)


class StructureRoutineGuardTests(unittest.TestCase):
    def reject(self,code,body='',**kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**kwargs)
        self.assertEqual(caught.exception.code,code,str(caught.exception))
    def test_distinct_nominal_result_type(self): self.reject('E_RETURN',declarations='alien: other_t',routines='ROUTINE get: child_t BEGIN RETURN alien END get')
    def test_distinct_nominal_argument_type(self): self.reject('E_TYPE','change((alien))',declarations='alien: other_t',routines='ROUTINE change(p: child_t) BEGIN END change')
    def test_wrong_scalar_return(self): self.reject('E_RETURN',routines='ROUTINE get: packet_t BEGIN RETURN 1 END get')
    def test_missing_return_expression(self): self.reject('E_RETURN',routines='ROUTINE get: packet_t BEGIN RETURN END get')
    def test_unknown_return_type(self): self.reject('E_TYPE',routines='ROUTINE get: missing_t BEGIN END get')
    def test_result_type_declared_after_routine_is_blocked(self):
        with self.assertRaises(TranslationError) as caught:
            translate('PROGRAM T ROUTINE get: later_t BEGIN END get TYPE later_t=STRUCTURE n: INTEGER ENDSTRUCTURE BEGIN END T')
        self.assertEqual(caught.exception.code,'E_TYPE')
    def test_named_array_return_remains_blocked(self): self.reject('E_RETURN_TYPE',routines='ROUTINE get: row_t BEGIN END get', _translator=legacy_translate)
    def test_sized_array_result_remains_blocked(self):
        self.reject('E_RETURN_TYPE',routines='ROUTINE get: ARRAY[2] OF INTEGER BEGIN END get', _translator=legacy_translate)
    def test_whole_array_value_remains_blocked(self): self.reject('E_ARRAY_VALUE','fill((a.values))',routines='ROUTINE fill(p: ARRAY OF INTEGER) BEGIN END fill', _translator=legacy_translate)
    def test_aggregate_uninit_remains_blocked(self): self.reject('E_TYPE','flag=UNINIT(a)')
    def test_structure_comparison_remains_blocked(self): self.reject('E_TYPE','flag=a=b')
    def test_function_used_as_statement(self): self.reject('E_CALL','build(1)',routines=FACTORY)
    def test_multiple_arguments_with_function_results(self): self.reject('E_EVALUATION_ORDER','work(build(1),a)',routines=FACTORY+'\nROUTINE work(p,q: packet_t) BEGIN END work', _translator=legacy_translate)
    def test_effectful_result_for_indexed_target(self): self.reject('E_EVALUATION_ORDER','items[1]=get()',declarations='a: packet_t items: ARRAY[1] OF packet_t n: INTEGER',routines='ROUTINE get: packet_t BEGIN n=1 RETURN a END get', _translator=legacy_translate)
    def test_delay_result_for_indexed_target(self): self.reject('E_EVALUATION_ORDER','items[1]=get()',declarations='a: packet_t items: ARRAY[1] OF packet_t',routines='ROUTINE get: packet_t BEGIN DELAY 0 RETURN a END get', _translator=legacy_translate)
    def test_output_result_for_indexed_target(self): self.reject('E_EVALUATION_ORDER','items[1]=get()',declarations='a: packet_t items: ARRAY[1] OF packet_t',routines="ROUTINE get: packet_t BEGIN WRITE('record') RETURN a END get", _translator=legacy_translate)
    def test_abort_result_for_indexed_target(self): self.reject('E_EVALUATION_ORDER','items[1]=get()',declarations='a: packet_t items: ARRAY[1] OF packet_t',routines='ROUTINE get: packet_t BEGIN IF FALSE THEN ABORT ENDIF RETURN a END get', _translator=legacy_translate)
    def test_strict_uninitialized_nested_leaf_fails_before_callee_effect(self):
        program,_=compile_program(initialize()+' n=0 change((b))',routines='ROUTINE change(p: packet_t) BEGIN n=1 END change', _translator=legacy_translate)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
        self.assertEqual(program.snapshot()['N'],0); self.assertEqual(program._state.call_depth,0)
    def test_strict_partial_array_field_return_fails_before_destination_mutation(self):
        program,_=compile_program(initialize('b')+' a.child.count=1 a.child.label=\'abc\' a.enabled=ON a.values[1]=1 b=get()',routines='ROUTINE get: packet_t BEGIN RETURN a END get', _translator=legacy_translate)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
        self.assertEqual(program.snapshot()['B'],packet()); self.assertEqual(program._state.local_frames,[])
    def test_fallthrough_error_and_cleanup(self):
        program,_=compile_program('a=get()',routines='ROUTINE get: packet_t BEGIN END get')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'without RETURN'): program.run()
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))
    def test_recursive_depth_guard_and_cleanup(self):
        program,_=compile_program('a=get()',routines='ROUTINE get: packet_t BEGIN RETURN get() END get')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'depth'): program.run()
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))
    def test_abort_prior_effect_and_frame_cleanup(self):
        program,_=compile_program('a=get()',routines='ROUTINE get: packet_t BEGIN n=7 ABORT RETURN a END get')
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual(program.snapshot()['N'],7); self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))
    def test_oversize_record_value_guard(self):
        types='TYPE large_t=STRUCTURE first: ARRAY[16384] OF INTEGER second: ARRAY[16384] OF INTEGER ENDSTRUCTURE'
        program,_=compile_program('accept((a))',types=types,declarations='a: large_t',routines='ROUTINE accept(p: large_t) BEGIN END accept')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'32767 scalar leaves'): program.run()


class StructureValueRuntimeTests(unittest.TestCase):
    def spec(self,fields=(('VALUE',('INTEGER',)),)): return ('STRUCTURE','ITEM_T',fields)
    def test_recursive_copy_and_nominal_identity(self):
        spec=self.spec((('VALUES',('ARRAY',2,('INTEGER',),'ROW_T')),))
        original=initialized_host(spec); copied=rt.structure_value(spec,original,17)
        copied.values['VALUES'].values[0]=9
        self.assertEqual(original.values['VALUES'].values,[1,1]); self.assertEqual(copied.spec,spec)
    def test_all_supported_scalar_field_types(self):
        spec=self.spec(tuple((kind,(kind,3) if kind=='STRING' else (kind,)) for kind in ('INTEGER','BOOLEAN','REAL','STRING','BYTE','SHORT')))
        value=initialized_host(spec)
        self.assertEqual(rt.snapshot_value(rt.structure_value(spec,value,17)),rt.snapshot_value(value))
    def test_nested_builtin_records_and_joint_values_copy(self):
        spec=self.spec((('V',('VECTOR',)),('C',('CONFIG',)),('J',('JOINTPOS',3))))
        value=initialized_host(spec); copied=rt.structure_value(spec,value,17)
        copied.values['V'].values['X']=9.; copied.values['J'].values[0]=9.
        self.assertEqual(value.values['V'].values['X'],1.); self.assertEqual(value.values['J'].values[0],1.)
    def test_position_protection_is_preserved_in_copied_container(self):
        spec=self.spec((('POSE',('POSITION',)),)); value=initialized_host(spec)
        copied=rt.structure_value(spec,value,17); pose=copied.values['POSE']
        self.assertTrue(pose.values['NORMAL'].read_only)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'read-only'): rt.field_reference(pose.values['NORMAL'],'X',17).set(9.,17)
    def test_nested_multidimensional_named_arrays(self):
        row=('ARRAY',2,('INTEGER',),'ROW_T'); spec=self.spec((('MATRIX',('ARRAY',(2,2),row)),))
        value=initialized_host(spec); copied=rt.structure_value(spec,value,17)
        copied.values['MATRIX'].values[0].values[0]=9
        self.assertEqual(value.values['MATRIX'].values[0].values,[1,1])
    def test_unknown_byte_field_rejected(self):
        spec=self.spec((('VALUE',('BYTE',)),)); value=rt.Structure(spec)
        with self.assertRaises(rt.KarelRuntimeError): rt.structure_value(spec,value,17)
    def test_short_sentinel_rejected(self):
        spec=self.spec((('VALUE',('SHORT',)),)); value=rt.Structure(spec); value.values['VALUE']=32767
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): rt.structure_value(spec,value,17)
    def test_config_range_checked_recursively(self):
        spec=self.spec((('C',('CONFIG',)),)); value=initialized_host(spec); value.values['C'].values['CFG_TURN_NO1']=8
        with self.assertRaisesRegex(rt.KarelRuntimeError,'-8..7'): rt.structure_value(spec,value,17)
    def test_wrong_nominal_type_rejected(self):
        spec=self.spec(); other=('STRUCTURE','OTHER_T',spec[2])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'nominal'): rt.structure_value(spec,initialized_host(other),17)
    def test_wrong_root_type_rejected(self):
        with self.assertRaises(rt.KarelRuntimeError): rt.structure_value(('VECTOR',),rt.Structure(('VECTOR',)),17)
    def test_wrong_record_fields_or_metadata_rejected(self):
        for mutate in (lambda v:v.values.update(EXTRA=1),lambda v:v.values.clear(),lambda v:v.types.update(VALUE=('REAL',))):
            spec=self.spec(); value=initialized_host(spec); mutate(value)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'nominal'): rt.structure_value(spec,value,17)
    def test_malformed_array_storage_rejected(self):
        spec=self.spec((('VALUES',('ARRAY',2,('INTEGER',))),))
        for mutate in (lambda v:v.values['VALUES'].values.pop(),lambda v:setattr(v.values['VALUES'],'shape',(3,)),lambda v:setattr(v.values['VALUES'],'spec',('ARRAY',3,('INTEGER',)))):
            value=initialized_host(spec); mutate(value)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'shape'): rt.structure_value(spec,value,17)
    def test_invalid_scalar_contents_rejected_with_source_line(self):
        spec=self.spec()
        for item in (True,'1',2**31,rt.UNINITIALIZED,rt.UNKNOWN_BYTE):
            value=initialized_host(spec); value.values['VALUE']=item
            with self.subTest(item=item),self.assertRaisesRegex(rt.KarelRuntimeError,'line 17'): rt.structure_value(spec,value,17)
    def test_invalid_real_field_rejected(self):
        spec=self.spec((('VALUE',('REAL',)),)); value=initialized_host(spec); value.values['VALUE']=0.1
        with self.assertRaisesRegex(rt.KarelRuntimeError,'rounding'): rt.structure_value(spec,value,17)
    def test_overcapacity_string_does_not_silently_truncate_at_value_boundary(self):
        spec=self.spec((('VALUE',('STRING',2)),)); value=initialized_host(spec); value.values['VALUE']='abc'
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'): rt.structure_value(spec,value,17)
    def test_failed_copy_does_not_mutate_source(self):
        spec=self.spec((('FIRST',('INTEGER',)),('SECOND',('BOOLEAN',)))); value=initialized_host(spec); value.values['SECOND']=1
        before=dict(value.values)
        with self.assertRaises(rt.KarelRuntimeError): rt.structure_value(spec,value,17)
        self.assertEqual(value.values,before)


class StructureRoutineEvidenceTests(unittest.TestCase):
    def test_return_and_value_reports_include_identity(self):
        _,result=compile_program('a=build(1) change((a)) change(build(2))',routines=FACTORY+'\n'+CHANGE)
        self.assertEqual(len(result.report['structure_returns']),1)
        self.assertEqual([row['expression_kind'] for row in result.report['structure_value_arguments']],['group','call'])
        self.assertTrue(all(row['type_name']=='PACKET_T' and row['independent_writable_copy'] for row in result.report['structure_returns']))
        self.assertEqual(result.report['routine_effects']['CHANGE']['parameters'][0]['passing_modes'],['reference','value'])
        self.assertFalse(result.report['structure_routine_policy']['controller_validated'])
    def test_parameter_write_effect_remains_conservative(self):
        _,result=compile_program(initialize()+' change((a))',routines=CHANGE)
        self.assertEqual(result.report['routine_effects']['CHANGE']['potential_parameter_writes'],['P'])
        self.assertTrue(result.report['routine_effects']['CHANGE']['potential_external_writes'])
    def test_labelled_and_structured_callers_agree(self):
        observations=[]
        for labelled in (False,True):
            program,_=compile_program('a=build(1) change((a))',routines=FACTORY+'\n'+CHANGE,labelled=labelled)
            observations.append((program.run(),program._state.steps))
        self.assertEqual(observations[0],observations[1])


if __name__=='__main__': unittest.main()
