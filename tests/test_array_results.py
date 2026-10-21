"""Unsized 1D scalar ARRAY results, assignment-only use and concrete ownership."""
import ast,unittest
from karel2py import translate,runtime as rt
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError

FACTORY='ROUTINE make: ARRAY OF INTEGER VAR values: ARRAY[3] OF INTEGER BEGIN values[1]=1 values[2]=2 values[3]=3 RETURN values END make'
def compile_program(body='',routines=FACTORY,declarations='a,b: ARRAY[3] OF INTEGER n: INTEGER',prefix='',context=None, *, _translator=translate):
    result=_translator(f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T',filename='array_results.kl',**(context or {}))
    namespace={'__name__':'array_result_test'}; exec(result.python_source,namespace)
    return namespace['Program'](),result
def execute(body='',**kwargs): return compile_program(body,**kwargs)[0].run()

class ArrayFunctionTests(unittest.TestCase):
    def test_local_integer_array_result(self): self.assertEqual(execute('a=make()')['A'],[1,2,3])
    def test_boolean_array_result(self):
        routine='ROUTINE make: ARRAY OF BOOLEAN VAR p: ARRAY[2] OF BOOLEAN BEGIN p[1]=ON p[2]=OFF RETURN p END make'
        self.assertEqual(execute('a=make()',routines=routine,declarations='a: ARRAY[2] OF BOOLEAN')['A'],[True,False])
    def test_real_array_result(self):
        routine='ROUTINE make: ARRAY OF REAL VAR p: ARRAY[2] OF REAL BEGIN p[1]=1.25 p[2]=2.5 RETURN p END make'
        self.assertEqual(execute('a=make()',routines=routine,declarations='a: ARRAY[2] OF REAL')['A'],[1.25,2.5])
    def test_global_array_result_is_independent(self):
        state=execute('a[1]=1 a[2]=2 a[3]=3 b=get() a[2]=99',routines='ROUTINE get: ARRAY OF INTEGER BEGIN RETURN a END get')
        self.assertEqual(state['B'],[1,2,3])
    def test_reference_formal_result_is_independent(self):
        routine=FACTORY+'\nROUTINE duplicate(p: ARRAY OF INTEGER): ARRAY OF INTEGER BEGIN RETURN p END duplicate'
        self.assertEqual(execute('a=make() b=duplicate(a) a[2]=99',routines=routine)['B'],[1,2,3])
    def test_same_function_returns_different_lengths(self):
        routine='ROUTINE duplicate(p: ARRAY OF INTEGER): ARRAY OF INTEGER BEGIN RETURN p END duplicate'
        state=execute('a[1]=7 a[2]=8 b[1]=9 c=duplicate(a) d=duplicate(b)',routines=routine,declarations='a,c: ARRAY[2] OF INTEGER b,d: ARRAY[1] OF INTEGER')
        self.assertEqual((state['C'],state['D']),([7,8],[9]))
    def test_array_reference_destination_retains_size(self):
        routines=FACTORY+'\nROUTINE put(p: ARRAY OF INTEGER) BEGIN p=make() END put'
        self.assertEqual(execute('put(a)',routines=routines)['A'],[1,2,3])
    def test_grouped_storage_return(self): self.assertEqual(execute('a=make()',routines=FACTORY.replace('RETURN values','RETURN ((values))'))['A'],[1,2,3])
    def test_array_field_return(self):
        state=execute('box.values[1]=7 box.values[2]=8 a=get()',prefix='TYPE box_t=STRUCTURE values: ARRAY[2] OF INTEGER ENDSTRUCTURE',declarations='box: box_t a: ARRAY[2] OF INTEGER',routines='ROUTINE get: ARRAY OF INTEGER BEGIN RETURN box.values END get')
        self.assertEqual(state['A'],[7,8])
    def test_array_field_destination(self):
        state=execute('box.values=make()',prefix='TYPE box_t=STRUCTURE values: ARRAY[3] OF INTEGER ENDSTRUCTURE',declarations='box: box_t')
        self.assertEqual(state['BOX']['VALUES'],[1,2,3])
    def test_pure_result_to_indexed_record_field(self):
        state=execute('boxes[1].values=make()',prefix='TYPE box_t=STRUCTURE values: ARRAY[3] OF INTEGER ENDSTRUCTURE',declarations='boxes: ARRAY[1] OF box_t')
        self.assertEqual(state['BOXES'][0]['VALUES'],[1,2,3])
    def test_captured_element_survives_whole_result_assignment(self):
        routines=FACTORY+'\nROUTINE change(p: ARRAY OF INTEGER; item: INTEGER) BEGIN p=make() item=99 END change'
        self.assertEqual(execute('change(a,a[2])',routines=routines)['A'],[1,99,3])
    def test_result_evaluated_once(self):
        self.assertEqual(execute('n=0 a=make()',routines=FACTORY.replace('BEGIN values[1]','BEGIN n=n+1 values[1]'))['N'],1)
    def test_result_can_be_staged_then_passed_by_reference(self):
        routines=FACTORY+'\nROUTINE change(p: ARRAY OF INTEGER) BEGIN p[1]=99 END change'
        self.assertEqual(execute('a=make() change(a)',routines=routines)['A'],[99,2,3])
    def test_recursion_stages_array_result_before_return(self):
        routines=FACTORY+'\nROUTINE recurse(k: INTEGER): ARRAY OF INTEGER VAR p: ARRAY[3] OF INTEGER BEGIN IF k=0 THEN p=make() ELSE p=recurse(k-1) p[1]=p[1]+1 ENDIF RETURN p END recurse'
        program,_=compile_program('a=recurse(4)',routines=routines)
        self.assertEqual(program.run()['A'],[5,2,3]); self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_labelled_array_function(self):
        routine=FACTORY.replace('BEGIN values[1]','BEGIN GOTO fill fill:: values[1]')
        self.assertEqual(execute('entry:: a=make()',routines=routine)['A'],[1,2,3])
    def test_return_inside_local_for(self):
        routine='ROUTINE make: ARRAY OF INTEGER VAR p: ARRAY[1] OF INTEGER i: INTEGER BEGIN p[1]=7 FOR i=1 TO 2 DO RETURN p ENDFOR END make'
        self.assertEqual(execute('a=make()',routines=routine,declarations='a: ARRAY[1] OF INTEGER')['A'],[7])
    def test_select_return(self):
        routine=FACTORY.replace('RETURN values','SELECT 1 OF CASE(1): RETURN values ELSE: RETURN values ENDSELECT')
        self.assertEqual(execute('a=make()',routines=routine)['A'],[1,2,3])
    def test_external_shape_context_produces_concrete_result(self):
        program,result=compile_program('a[1]=7 a[2]=8 b=get()',routines='ROUTINE get: ARRAY OF INTEGER BEGIN RETURN a END get',declarations='a,b: ARRAY[*] OF INTEGER',context={'array_shapes':{'a':[2],'b':[2]}})
        self.assertEqual(program.run()['B'],[7,8]); self.assertIn('INTEGER/BOOLEAN/REAL/BYTE/SHORT',result.report['array_routine_policy']['results'])
    def test_same_source_and_destination(self):
        routines=FACTORY+'\nROUTINE duplicate(p: ARRAY OF INTEGER): ARRAY OF INTEGER BEGIN p[1]=7 RETURN p END duplicate'
        self.assertEqual(execute('a=make() a=duplicate(a)',routines=routines)['A'],[7,2,3])

class ArrayResultFailureTests(unittest.TestCase):
    def rejected(self,body='',code='E_ARRAY_RESULT_CONTEXT',**kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**kwargs)
        self.assertEqual(caught.exception.code,code,str(caught.exception))
    def test_grouped_result_is_not_direct_assignment(self): self.rejected('a=(make())')
    def test_result_cannot_be_routine_argument(self): self.rejected('use(make())',routines=FACTORY+'\nROUTINE use(p: ARRAY OF INTEGER) BEGIN END use')
    def test_result_cannot_be_builtin_argument(self): self.rejected('n=ARRAY_LEN(make())')
    def test_result_cannot_be_directly_returned(self): self.rejected('a=outer()',routines=FACTORY+'\nROUTINE outer: ARRAY OF INTEGER BEGIN RETURN make() END outer')
    def test_result_cannot_be_operator_operand(self): self.rejected('a=make()+a')
    def test_result_cannot_be_condition(self): self.rejected('IF make() THEN ENDIF')
    def test_result_cannot_be_select_selector(self): self.rejected('SELECT make() OF CASE(1): ENDSELECT')
    def test_wrong_element_type_in_assignment(self): self.rejected('a=make()','E_TYPE',declarations='a: ARRAY[3] OF REAL')
    def test_wrong_element_type_in_return(self): self.rejected('','E_RETURN',routines='ROUTINE make: ARRAY OF REAL VAR p: ARRAY[1] OF INTEGER BEGIN p[1]=1 RETURN p END make')
    def test_array_result_return_requires_value(self): self.rejected('','E_RETURN',routines='ROUTINE make: ARRAY OF INTEGER BEGIN RETURN END make')
    def test_fixed_or_wildcard_result_dimensions_are_blocked(self):
        for dimensions in ('[1]','[*]','[*,*]'):
            self.rejected('','E_RETURN_TYPE',routines=f'ROUTINE make: ARRAY{dimensions} OF INTEGER BEGIN END make')
    def test_other_array_element_result_types_are_blocked(self):
        for element in ('STRING','FILE','PATH','ARRAY'):
            self.rejected('','E_RETURN_TYPE',routines=f'ROUTINE make: ARRAY OF {element} BEGIN END make')
    def test_named_array_result_declaration_remains_blocked(self):
        self.rejected('','E_RETURN_TYPE',prefix='TYPE row_t=ARRAY[3] OF INTEGER',routines='ROUTINE make: row_t BEGIN END make')
    def test_multidimensional_return_source_blocked(self):
        self.rejected('','E_RETURN',routines='ROUTINE make: ARRAY OF INTEGER VAR p: ARRAY[2,2] OF INTEGER BEGIN RETURN p END make')
    def test_whole_array_value_arguments_remain_blocked(self):
        self.rejected('use((a))','E_ARRAY_VALUE',routines='ROUTINE use(p: ARRAY OF INTEGER) BEGIN END use')
    def test_effectful_result_to_indexed_target_is_blocked(self):
        self.rejected('boxes[1].values=make()','E_EVALUATION_ORDER',prefix='TYPE box_t=STRUCTURE values: ARRAY[3] OF INTEGER ENDSTRUCTURE',declarations='boxes: ARRAY[1] OF box_t n: INTEGER',routines=FACTORY.replace('BEGIN values[1]','BEGIN n=7 values[1]'), _translator=legacy_translate)
    def test_length_failure_retains_destination_and_effects(self):
        program,_=compile_program('a[1]=99 a[2]=88 n=0 a=make()',declarations='a: ARRAY[2] OF INTEGER n: INTEGER',routines=FACTORY.replace('BEGIN values[1]','BEGIN n=n+1 values[1]'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identical type and size'): program.run()
        self.assertEqual((program.snapshot()['A'],program.snapshot()['N']),([99,88],1))
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_unknown_element_failure_precedes_assignment(self):
        program,_=compile_program('a[1]=99 n=0 a=make()',routines=FACTORY.replace('values[3]=3','n=7'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
        self.assertEqual((program.snapshot()['A'][0],program.snapshot()['N']),(99,7))
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_function_fallthrough_error(self):
        program,_=compile_program('a=make()',routines='ROUTINE make: ARRAY OF INTEGER BEGIN END make')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_abort_remains_distinct(self):
        program,_=compile_program('a=make()',routines='ROUTINE make: ARRAY OF INTEGER BEGIN ABORT END make')
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_call_depth_guard_unwinds_array_frames(self):
        routine='ROUTINE recurse(k: INTEGER): ARRAY OF INTEGER VAR p: ARRAY[3] OF INTEGER BEGIN p=recurse(k+1) RETURN p END recurse'
        program,_=compile_program('a=recurse(0)',routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'depth'): program.run()
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_named_array_source_directly_blocked(self):
        self.rejected('','E_ARRAY_RETURN_SOURCE',prefix='TYPE row_t=ARRAY[3] OF INTEGER',routines='ROUTINE make: ARRAY OF INTEGER VAR p: row_t BEGIN RETURN p END make')
    def test_named_storage_via_generic_parameter_is_runtime_guarded(self):
        routine='ROUTINE duplicate(p: ARRAY OF INTEGER): ARRAY OF INTEGER BEGIN RETURN p END duplicate'
        program,_=compile_program('p[1]=7 a=duplicate(p)',prefix='TYPE row_t=ARRAY[1] OF INTEGER',declarations='p: row_t a: ARRAY[1] OF INTEGER',routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'anonymous'): program.run()
    def test_named_destination_remains_exact(self):
        program,_=compile_program('p=make()',prefix='TYPE row_t=ARRAY[3] OF INTEGER',declarations='p: row_t')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identical type and size'): program.run()

class ArrayResultRuntimeTests(unittest.TestCase):
    def value(self,kind='INTEGER',values=(1,2,3)):
        result=rt.Array(('ARRAY',len(values),(kind,))); result.values[:]=values; return result
    def test_fresh_storage_and_concrete_type(self):
        source=self.value(); copied=rt.array_result(('ARRAY',None,rt.INTEGER),source,17)
        self.assertIsNot(copied,source); self.assertIsNot(copied.values,source.values)
        self.assertEqual(copied.spec,('ARRAY',3,rt.INTEGER)); copied.set(1,99)
        self.assertEqual(source.snapshot(),[1,2,3])
    def test_invalid_integer_leaves_and_unknown_markers(self):
        for bad in (True,'1',2**31,2147483647,rt.UNINITIALIZED,rt.UNKNOWN_BYTE):
            source=self.value(values=(1,bad,3)); before=list(source.values)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'line 17'): rt.array_result(('ARRAY',None,rt.INTEGER),source,17)
            self.assertEqual(source.values,before)
    def test_invalid_boolean_leaves(self):
        for bad in (0,1,'TRUE',rt.UNINITIALIZED):
            with self.assertRaises(rt.KarelRuntimeError): rt.array_result(('ARRAY',None,rt.BOOLEAN),self.value('BOOLEAN',(True,bad)),17)
    def test_invalid_real_leaves(self):
        for bad in (.1,float('nan'),float('inf'),True,rt.UNINITIALIZED):
            with self.assertRaises(rt.KarelRuntimeError): rt.array_result(('ARRAY',None,rt.REAL),self.value('REAL',(1.,bad)),17)
    def test_malformed_storage_length_and_shape(self):
        for mutation in ('length','shape','storage'):
            source=self.value()
            if mutation=='length': source.values.pop()
            elif mutation=='shape': source.shape=(2,)
            else: source.values=tuple(source.values)
            with self.assertRaises(rt.KarelRuntimeError): rt.array_result(('ARRAY',None,rt.INTEGER),source,17)
    def test_malformed_concrete_type_is_explicit(self):
        for spec in (None,[],('ARRAY',0,rt.INTEGER),('ARRAY',None,rt.INTEGER),('ARRAY',32768,rt.INTEGER),('ARRAY',(1,3),rt.INTEGER)):
            source=self.value(); source.spec=spec
            with self.assertRaises(rt.KarelRuntimeError): rt.array_result(('ARRAY',None,rt.INTEGER),source,17)
    def test_invalid_result_formals_and_actual_types(self):
        for formal in (('ARRAY',3,rt.INTEGER),('ARRAY',None,rt.BYTE),('ARRAY',None,('STRING',None)),('INTEGER',)):
            with self.assertRaises(rt.KarelRuntimeError): rt.array_result(formal,self.value(),17)
        for value in ([1,2,3],True,rt.UNINITIALIZED,rt.Structure(('VECTOR',))):
            with self.assertRaises(rt.KarelRuntimeError): rt.array_result(('ARRAY',None,rt.INTEGER),value,17)
    def test_maximum_prototype_length(self):
        source=self.value(values=[1]*32767)
        self.assertEqual(len(rt.array_result(('ARRAY',None,rt.INTEGER),source,17).values),32767)
    def test_reports_and_311_syntax(self):
        _,result=compile_program('a=make()'); ast.parse(result.python_source,feature_version=(3,11))
        self.assertEqual(len(result.report['array_returns']),1); self.assertEqual(len(result.report['array_result_assignments']),1)
        self.assertEqual(result.report['array_returns'][0]['element_type'],'INTEGER')
        self.assertTrue(result.report['array_returns'][0]['independent_copy'])
        self.assertTrue(result.report['array_result_assignments'][0]['runtime_exact_type_and_size'])
        self.assertFalse(result.report['array_routine_policy']['controller_validated'])

if __name__=='__main__': unittest.main()
