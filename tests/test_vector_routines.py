"""VECTOR returned values, writable value temporaries and unchanged effect guards."""
import ast
import unittest
from karel2py import translate, runtime as rt
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError

UNKNOWN={'uninitialized':True}
FACTORY='''ROUTINE make(x,y,z: REAL): VECTOR
VAR v: VECTOR
BEGIN v.x=x v.y=y v.z=z RETURN v END make'''
CHANGE='ROUTINE change(v: VECTOR) BEGIN v.x=99 END change'

def fill(name='a',values=(1,2,3)):
    return ' '.join(f'{name}.{field}={value}' for field,value in zip(('x','y','z'),values))

def vec(x=1,y=2,z=3): return dict(X=float(x),Y=float(y),Z=float(z))

def compile_program(body='',*,declarations='a,b,c: VECTOR r: REAL flag: BOOLEAN',types='',routines='',labelled=False, _translator=translate):
    label='entry::\n' if labelled else ''
    source=f'PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n{label}{body}\nEND T'
    result=_translator(source,filename='vector_routines.kl')
    ast.parse(result.python_source,feature_version=(3,11))
    namespace={'__name__':'vector_routine_test'}
    exec(result.python_source,namespace)
    return namespace['Program'](),result

def execute(body='',**kwargs): return compile_program(body,**kwargs)[0].run()

def host_vector(*values):
    result=rt.Structure(('VECTOR',))
    result.values.update(zip(('X','Y','Z'),values))
    return result


class VectorReturnTests(unittest.TestCase):
    def test_fresh_local_value_survives_frame_unwind(self): self.assertEqual(execute('a=make(1,2,3)',routines=FACTORY)['A'],vec())
    def test_global_return_is_independent(self):
        state=execute(fill()+' b=get() a.x=9',routines='ROUTINE get: VECTOR BEGIN RETURN a END get')
        self.assertEqual(state['B'],vec())
    def test_reference_formal_return_is_independent(self):
        state=execute(fill()+' b=get(a) a.x=9',routines='ROUTINE get(v: VECTOR): VECTOR BEGIN RETURN v END get')
        self.assertEqual(state['B'],vec())
    def test_operator_result_return(self):
        self.assertEqual(execute(fill()+' b=double(a)',routines='ROUTINE double(v: VECTOR): VECTOR BEGIN RETURN v*2 END double')['B'],vec(2,4,6))
    def test_nested_return(self):
        self.assertEqual(execute('a=outer()',routines=FACTORY+'\nROUTINE outer: VECTOR BEGIN RETURN make(1,2,3) END outer')['A'],vec())
    def test_recursive_frames(self):
        routines=FACTORY+'\nROUTINE recurse(n: INTEGER): VECTOR VAR saved: VECTOR BEGIN saved=make(n,0,0) IF n=0 THEN RETURN saved ENDIF saved=recurse(n-1)+saved RETURN saved END recurse'
        self.assertEqual(execute('a=recurse(3)',routines=routines)['A'],vec(6,0,0))
    def test_select_return_paths(self):
        routine=FACTORY+'\nROUTINE choose(n: INTEGER): VECTOR BEGIN SELECT n OF CASE(1): RETURN make(1,2,3) ELSE: RETURN make(4,5,6) ENDSELECT END choose'
        self.assertEqual(execute('a=choose(1) b=choose(2)',routines=routine)['B'],vec(4,5,6))
    def test_labelled_return_dispatch(self):
        routine=FACTORY+'\nROUTINE get: VECTOR BEGIN GOTO result result:: RETURN make(1,2,3) END get'
        self.assertEqual(execute('a=get()',routines=routine)['A'],vec())
    def test_return_from_for_with_fresh_counter(self):
        routine=FACTORY+'\nROUTINE get: VECTOR VAR i: INTEGER BEGIN FOR i=1 TO 2 DO RETURN make(i,0,0) ENDFOR END get'
        self.assertEqual(execute('a=get()',routines=routine)['A'],vec(1,0,0))
    def test_array_element_return_and_destination(self):
        routine='ROUTINE get: VECTOR BEGIN RETURN items[1] END get'
        self.assertEqual(execute(fill('items[1]')+' items[2]=get() items[1].x=9',declarations='items: ARRAY[2] OF VECTOR',routines=routine)['ITEMS'][1],vec())
    def test_structure_field_return(self):
        state=execute(fill('box.offset')+' a=get()',types='TYPE box_t=STRUCTURE offset: VECTOR ENDSTRUCTURE',declarations='box: box_t a: VECTOR',routines='ROUTINE get: VECTOR BEGIN RETURN box.offset END get')
        self.assertEqual(state['A'],vec())
    def test_return_to_captured_field_preserves_references(self):
        routines=FACTORY+'\nROUTINE work(target: VECTOR; field: REAL) BEGIN target=make(4,5,6) field=9 END work'
        self.assertEqual(execute(fill()+' work(a,a.x)',routines=routines)['A'],vec(9,5,6))
    def test_pure_returned_values_in_operator(self):
        self.assertEqual(execute('a=make(1,2,3)+make(4,5,6)',routines=FACTORY)['A'],vec(5,7,9))
    def test_pure_returned_values_in_dot_product(self): self.assertEqual(execute('r=make(1,2,3)@make(4,5,6)',routines=FACTORY)['R'],32.)
    def test_frame_cleanup_after_success(self):
        program,_=compile_program('a=make(1,2,3)',routines=FACTORY)
        program.run(); self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))
    def test_return_copy_cannot_be_mutated_through_saved_host_reference(self):
        program,_=compile_program(fill(),routines='ROUTINE get: VECTOR BEGIN RETURN a END get')
        program.run(); returned=program._routine_GET(); returned.values['X']=99.
        self.assertEqual(program.snapshot()['A'],vec())


class VectorValueArgumentTests(unittest.TestCase):
    def test_bare_reference_still_writes_caller(self): self.assertEqual(execute(fill()+' change(a)',routines=CHANGE)['A'],vec(99,2,3))
    def test_grouped_variable_is_writable_copy(self): self.assertEqual(execute(fill()+' change((a))',routines=CHANGE)['A'],vec())
    def test_nested_grouping_still_makes_copy(self): self.assertEqual(execute(fill()+' change(((a)))',routines=CHANGE)['A'],vec())
    def test_expression_argument_has_independent_storage(self): self.assertEqual(execute(fill()+' change(a+a)',routines=CHANGE)['A'],vec())
    def test_returned_value_argument(self):
        routine=FACTORY+'\nROUTINE modify(v: VECTOR): VECTOR BEGIN v.x=99 RETURN v END modify'
        self.assertEqual(execute('a=modify(make(1,2,3))',routines=routine)['A'],vec(99,2,3))
    def test_grouped_field_argument(self):
        state=execute(fill('box.offset')+' change((box.offset))',types='TYPE box_t=STRUCTURE offset: VECTOR ENDSTRUCTURE',declarations='box: box_t',routines=CHANGE)
        self.assertEqual(state['BOX']['OFFSET'],vec())
    def test_grouped_array_element_argument(self):
        self.assertEqual(execute(fill('items[1]')+' change((items[1]))',declarations='items: ARRAY[1] OF VECTOR',routines=CHANGE)['ITEMS'][0],vec())
    def test_multiple_grouped_arguments_do_not_alias(self):
        routine='ROUTINE work(p,q: VECTOR) BEGIN p.x=99 r=q.x END work'
        state=execute(fill()+' work((a),(a))',routines=routine)
        self.assertEqual((state['A'],state['R']),(vec(),1.))
    def test_mixed_reference_and_value_arguments(self):
        routine='ROUTINE work(p,q: VECTOR) BEGIN p.x=99 r=q.x END work'
        state=execute(fill()+' work(a,(a))',routines=routine)
        self.assertEqual((state['A'],state['R']),(vec(99,2,3),1.))
    def test_forwarding_retains_own_temporary(self):
        routines=CHANGE+'\nROUTINE forward(v: VECTOR) BEGIN change(v) r=v.x END forward'
        state=execute(fill()+' forward((a))',routines=routines)
        self.assertEqual((state['A'],state['R']),(vec(),99.))
    def test_forwarding_grouped_creates_another_copy(self):
        routines=CHANGE+'\nROUTINE forward(v: VECTOR) BEGIN change((v)) r=v.x END forward'
        state=execute(fill()+' forward((a))',routines=routines)
        self.assertEqual((state['A'],state['R']),(vec(),1.))
    def test_field_reference_survives_whole_temporary_assignment(self):
        routines='ROUTINE inner(v: VECTOR; field: REAL) BEGIN v=v*2 field=9 END inner\nROUTINE forward(v: VECTOR) BEGIN inner(v,v.x) r=v.x END forward'
        state=execute(fill()+' forward((a))',routines=routines)
        self.assertEqual((state['A'],state['R']),(vec(),9.))
    def test_value_expression_evaluated_once(self):
        routines=FACTORY+'\nROUTINE counted: VECTOR BEGIN n=n+1 RETURN make(1,2,3) END counted\n'+CHANGE
        state=execute('n=0 change(counted())',declarations='n: INTEGER',routines=routines)
        self.assertEqual(state['N'],1)
    def test_grouped_index_evaluated_once(self):
        routines='ROUTINE next_index: INTEGER BEGIN n=n+1 RETURN 1 END next_index\n'+CHANGE
        state=execute(fill('items[1]')+' n=0 change((items[next_index()]))',declarations='items: ARRAY[1] OF VECTOR n: INTEGER',routines=routines)
        self.assertEqual((state['ITEMS'][0],state['N']),(vec(),1))
    def test_protected_fixture_grouped_value_is_detached_and_writable(self):
        program,_=compile_program('change((pose.normal))',declarations='pose: POSITION',routines=CHANGE)
        protected=program._state.raw('POSE').values['NORMAL']; protected.values.update(vec())
        program.run()
        self.assertEqual(rt.snapshot_value(protected),vec()); self.assertTrue(protected.read_only)
    def test_returned_protected_fixture_is_detached_and_writable(self):
        program,_=compile_program('a=get() a.x=99',declarations='pose: POSITION a: VECTOR',routines='ROUTINE get: VECTOR BEGIN RETURN pose.normal END get')
        protected=program._state.raw('POSE').values['NORMAL']; protected.values.update(vec())
        self.assertEqual(program.run()['A'],vec(99,2,3)); self.assertEqual(rt.snapshot_value(protected),vec())


class VectorRoutineGuardTests(unittest.TestCase):
    def reject(self,code,body='',**kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**kwargs)
        self.assertEqual(caught.exception.code,code,str(caught.exception))
    def test_wrong_return_type(self): self.reject('E_RETURN',routines='ROUTINE get: VECTOR BEGIN RETURN 1 END get')
    def test_missing_return_expression(self): self.reject('E_RETURN',routines='ROUTINE get: VECTOR BEGIN RETURN END get')
    def test_function_not_allowed_as_statement(self): self.reject('E_CALL','get()',routines='ROUTINE get: VECTOR BEGIN RETURN a END get')
    def test_sized_array_result_remains_blocked(self):
        self.reject('E_RETURN_TYPE',routines='ROUTINE get: ARRAY[2] OF INTEGER BEGIN END get')
    def test_whole_record_array_values_remain_blocked(self): self.reject('E_ARRAY_VALUE','work((items))',declarations='items: ARRAY[2] OF XYZWPR',routines='ROUTINE work(v: ARRAY OF XYZWPR) BEGIN END work', _translator=legacy_translate)
    def test_bare_protected_argument_remains_blocked(self): self.reject('E_POSITION_READ_ONLY_ARG','change(pose.normal)',declarations='pose: POSITION',routines=CHANGE)
    def test_effectful_vector_result_in_operator_blocked(self): self.reject('E_EVALUATION_ORDER','b=get()+a',routines='ROUTINE get: VECTOR BEGIN r=1 RETURN a END get', _translator=legacy_translate)
    def test_effectful_vector_result_for_indexed_target_blocked(self): self.reject('E_EVALUATION_ORDER','items[1]=get()',declarations='items: ARRAY[1] OF VECTOR a: VECTOR r: REAL',routines='ROUTINE get: VECTOR BEGIN r=1 RETURN a END get', _translator=legacy_translate)
    def test_delay_effect_in_operator_blocked(self): self.reject('E_EVALUATION_ORDER','b=get()+a',routines='ROUTINE get: VECTOR BEGIN DELAY 0 RETURN a END get', _translator=legacy_translate)
    def test_output_effect_in_operator_blocked(self): self.reject('E_EVALUATION_ORDER','b=get()+a',routines="ROUTINE get: VECTOR BEGIN WRITE('value') RETURN a END get", _translator=legacy_translate)
    def test_abort_effect_in_operator_blocked(self): self.reject('E_EVALUATION_ORDER','b=get()+a',routines='ROUTINE get: VECTOR BEGIN IF FALSE THEN ABORT ENDIF RETURN a END get', _translator=legacy_translate)
    def test_transitive_effect_in_operator_blocked(self): self.reject('E_EVALUATION_ORDER','b=get()+a',routines='ROUTINE inner: VECTOR BEGIN r=1 RETURN a END inner\nROUTINE get: VECTOR BEGIN RETURN inner() END get', _translator=legacy_translate)
    def test_multiple_arguments_containing_function_calls_blocked(self): self.reject('E_EVALUATION_ORDER','work(make(1,2,3),a)',routines=FACTORY+'\nROUTINE work(p,q: VECTOR) BEGIN END work', _translator=legacy_translate)
    def test_uninitialized_return_preserves_destination_and_cleans_frames(self):
        program,_=compile_program(fill('b')+' b=get()',routines='ROUTINE get: VECTOR VAR v: VECTOR BEGIN v.x=1 v.y=2 RETURN v END get')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
        self.assertEqual(program.snapshot()['B'],vec()); self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))
    def test_uninitialized_value_rejected_before_callee_effects(self):
        program,_=compile_program('r=0 change((a))',routines='ROUTINE change(v: VECTOR) BEGIN r=1 END change')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
        self.assertEqual(program.snapshot()['R'],0.); self.assertEqual(program._state.call_depth,0)
    def test_fallthrough_is_runtime_error(self):
        program,_=compile_program('a=get()',routines='ROUTINE get: VECTOR BEGIN END get')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'without RETURN'): program.run()
        self.assertEqual(program._state.local_frames,[])
    def test_call_depth_guard_and_frame_cleanup(self):
        program,_=compile_program('a=get()',routines='ROUTINE get: VECTOR BEGIN RETURN get() END get')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'depth'): program.run()
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))
    def test_abort_keeps_prior_effects_and_unwinds_vector_frames(self):
        program,_=compile_program('a=get()',routines='ROUTINE get: VECTOR VAR v: VECTOR BEGIN r=7 ABORT RETURN v END get')
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual(program.snapshot()['R'],7.); self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))
    def test_value_parameter_write_is_still_potential_reference_effect(self):
        _,result=compile_program(fill()+' change((a))',routines=CHANGE)
        self.assertTrue(result.report['routine_effects']['CHANGE']['potential_external_writes'])
        self.assertEqual(result.report['routine_effects']['CHANGE']['potential_parameter_writes'],['V'])
        self.assertEqual(result.report['routine_effects']['CHANGE']['parameters'][0]['passing_modes'],['reference','value'])


class VectorRoutineRuntimeTests(unittest.TestCase):
    def test_vector_value_creates_fresh_storage(self):
        original=host_vector(1.,2.,3.); copied=rt.vector_value(original,17)
        self.assertIsNot(copied,original); copied.values['X']=9.
        self.assertEqual(rt.snapshot_value(original),vec())
    def test_value_argument_temporary_is_writable(self):
        original=host_vector(1.,2.,3.); reference=rt.value_argument(('VECTOR',),original,17)
        rt.field_reference(reference.raw(),'X',17).set(9.,17)
        self.assertEqual(rt.snapshot_value(original),vec()); self.assertEqual(rt.snapshot_value(reference.raw()),vec(9,2,3))
    def test_wrong_nominal_type_and_shape_rejected(self):
        wrong=host_vector(1.,2.,3.); wrong.values['EXTRA']=4.
        for value in (wrong,rt.Structure(('XYZWPR',)),[1.,2.,3.],1):
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError): rt.vector_value(value,17)
    def test_invalid_components_rejected(self):
        for value in (rt.UNINITIALIZED,rt.UNKNOWN_BYTE,True,None,'1',float('nan'),float('inf'),0.1,16777217):
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError): rt.value_argument(('VECTOR',),host_vector(1.,value,3.),17)
    def test_all_components_checked_before_exposing_temporary(self):
        for component in range(3):
            values=[1.,2.,3.]; values[component]=rt.UNINITIALIZED
            with self.subTest(component=component),self.assertRaisesRegex(rt.KarelRuntimeError,'line 17'): rt.vector_value(host_vector(*values),17)
    def test_protected_vector_copy_is_writable(self):
        original=host_vector(1.,2.,3.); original.read_only=True
        copied=rt.vector_value(original,17); self.assertFalse(copied.read_only)
        rt.field_reference(copied,'X',17).set(9.,17)
        self.assertEqual(rt.snapshot_value(original),vec())


class VectorRoutineEvidenceTests(unittest.TestCase):
    def test_reports_capture_returns_and_value_arguments_once(self):
        _,result=compile_program('a=make(1,2,3) change((a)) change(a+a) change(make(4,5,6))',routines=FACTORY+'\n'+CHANGE)
        self.assertEqual(len(result.report['vector_returns']),1)
        self.assertEqual([row['expression_kind'] for row in result.report['vector_value_arguments']],['group','binary','call'])
        self.assertTrue(all(row['evaluated_once'] and row['independent_writable_copy'] for row in result.report['vector_value_arguments']))
        self.assertFalse(result.report['vector_routine_policy']['controller_validated'])
    def test_labelled_and_structured_callers_match(self):
        states=[]
        for labelled in (False,True):
            program,_=compile_program('a=make(1,2,3) change((a))',routines=FACTORY+'\n'+CHANGE,labelled=labelled)
            states.append((program.run(),program._state.steps))
        self.assertEqual(states[0],states[1])


if __name__=='__main__': unittest.main()
