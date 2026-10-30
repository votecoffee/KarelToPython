"""Narrow ARRAY result ownership, checked storage and failure boundaries."""
import ast
import unittest
from pathlib import Path
from karel2py import translate, runtime as rt
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError


def factory(kind='BYTE', values=(0,255)):
    assignments=' '.join(f'p[{i}]={value}' for i,value in enumerate(values,1))
    return f'ROUTINE make: ARRAY OF {kind} VAR p: ARRAY[{len(values)}] OF {kind} BEGIN {assignments} RETURN p END make'


def compile_program(body='a=make()',kind='BYTE',routines=None,declarations=None,types='',context=None, *, _translator=translate):
    if routines is None: routines=factory(kind,(0,255) if kind=='BYTE' else (-32768,32766))
    if declarations is None: declarations=f'a,b: ARRAY[2] OF {kind} n: INTEGER'
    result=_translator(f'PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN {body}\nEND T',filename='narrow_array_results.kl',**(context or {}))
    namespace={'__name__':'narrow_array_results_test'}
    exec(result.python_source,namespace)
    return namespace['Program'](),result


def execute(*args,**kwargs): return compile_program(*args,**kwargs)[0].run()


class NarrowArrayFunctionTests(unittest.TestCase):
    def test_local_byte_endpoints(self): self.assertEqual(execute()['A'],[0,255])

    def test_local_short_endpoints(self): self.assertEqual(execute(kind='SHORT')['A'],[-32768,32766])

    def test_global_source_is_independent(self):
        self.assertEqual(execute('a[1]=0 a[2]=255 b=get() a[2]=1',routines='ROUTINE get: ARRAY OF BYTE BEGIN RETURN a END get')['B'],[0,255])

    def test_formals_preserve_each_concrete_length(self):
        for kind in ('BYTE','SHORT'):
            with self.subTest(kind=kind):
                state=execute('a[1]=7 b[1]=8 b[2]=9 c=duplicate(a) d=duplicate(b)',kind=kind,
                    declarations=f'a,c: ARRAY[1] OF {kind} b,d: ARRAY[2] OF {kind}',
                    routines=f'ROUTINE duplicate(p: ARRAY OF {kind}): ARRAY OF {kind} BEGIN RETURN p END duplicate')
                self.assertEqual((state['C'],state['D']),([7],[8,9]))

    def test_generic_reference_destination(self):
        routines=factory()+'\nROUTINE put(p: ARRAY OF BYTE) BEGIN p=make() END put'
        self.assertEqual(execute('put(a)',routines=routines)['A'],[0,255])

    def test_promoted_integer_argument_is_independent_of_narrow_array(self):
        for kind in ('BYTE','SHORT'):
            with self.subTest(kind=kind):
                routines=factory(kind)+'\n'+f'ROUTINE put(p: ARRAY OF {kind}; promoted: INTEGER) BEGIN p=make() promoted=42 n=promoted END put'
                state=execute('a[2]=9 put(a,a[2])',kind=kind,routines=routines)
                self.assertEqual((state['A'],state['N']),([0,255],42))

    def test_array_field_return_and_destination(self):
        routines='ROUTINE get: ARRAY OF SHORT BEGIN RETURN first.values END get'
        state=execute('first.values[1]=-32768 first.values[2]=32766 second.values=get() first.values[2]=0',kind='SHORT',
            types='TYPE packet_t=STRUCTURE values: ARRAY[2] OF SHORT ENDSTRUCTURE',declarations='first,second: packet_t',routines=routines)
        self.assertEqual(state['SECOND']['VALUES'],[-32768,32766])

    def test_same_source_destination_is_checked_before_replacement(self):
        routine='ROUTINE change(p: ARRAY OF BYTE): ARRAY OF BYTE BEGIN p[1]=7 RETURN p END change'
        self.assertEqual(execute('a[1]=0 a[2]=255 a=change(a)',routines=routine)['A'],[7,255])

    def test_result_staged_before_passing_to_another_routine(self):
        routines=factory()+'\nROUTINE touch(p: ARRAY OF BYTE) BEGIN p[1]=99 END touch'
        state=execute('a=make() b=a touch(a)',routines=routines)
        self.assertEqual((state['A'],state['B']),([99,255],[0,255]))

    def test_grouped_storage_return(self):
        self.assertEqual(execute(routines=factory().replace('RETURN p','RETURN ((p))'))['A'],[0,255])

    def test_recursion_stages_short_result(self):
        routines=factory('SHORT',(0,7))+'\nROUTINE recurse(k: INTEGER): ARRAY OF SHORT VAR p: ARRAY[2] OF SHORT BEGIN IF k=0 THEN p=make() ELSE p=recurse(k-1) p[1]=p[1]+1 ENDIF RETURN p END recurse'
        program,_=compile_program('a=recurse(3)',kind='SHORT',routines=routines)
        self.assertEqual(program.run()['A'],[3,7])
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))

    def test_explicit_wildcard_storage_specialization(self):
        program,_=compile_program(declarations='a: ARRAY[*] OF BYTE',context={'array_shapes':{'a':[2]}})
        self.assertEqual(program.run()['A'],[0,255])

    def test_reports_include_narrow_element_types_and_311_syntax(self):
        for kind in ('BYTE','SHORT'):
            with self.subTest(kind=kind):
                _,result=compile_program(kind=kind)
                ast.parse(result.python_source,feature_version=(3,11))
                self.assertEqual([row['element_type'] for row in result.report['array_returns']],[kind])
                self.assertFalse(result.report['array_returns'][0]['initialized_elements_required'])
                self.assertIn('32767',result.report['array_routine_policy']['narrow_elements'])
                self.assertFalse(result.report['array_routine_policy']['controller_validated'])

    def test_authored_example_complete_snapshot(self):
        path=Path(__file__).resolve().parents[1]/'examples/narrow_array_functions.kl'
        result=translate(path.read_text(),filename=path.name)
        namespace={'__name__':'narrow_array_example_test'}; exec(result.python_source,namespace)
        program=namespace['Program']()
        self.assertEqual(program.run(),dict(BYTES=[0,127,255],COPIED=[0,127,255],STAGED=[0,127,255],SHORTS=[-32768,7,32766],SHORT_COPY=[-32768,0,32766],PACKET={'PAYLOAD':[0,127,1]},TOTAL=380))
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))


class NarrowArrayFailureTests(unittest.TestCase):
    def rejected(self,code,**kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(**kwargs)
        self.assertEqual(caught.exception.code,code)

    def failure(self,routines,kind='BYTE',message='uninitialized'):
        program,_=compile_program('a[1]=7 a[2]=8 n=0 a=make()',kind=kind,routines=routines,_translator=legacy_translate)
        with self.assertRaisesRegex(rt.KarelRuntimeError,message): program.run()
        self.assertEqual(program.snapshot()['A'],[7,8])
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
        return program.snapshot()

    def test_strict_unknown_byte_failure_preserves_effects_and_destination(self):
        state=self.failure('ROUTINE make: ARRAY OF BYTE VAR p: ARRAY[2] OF BYTE BEGIN p[1]=0 n=9 RETURN p END make',message='unknown|uninitialized')
        self.assertEqual(state['N'],9)

    def test_strict_unwritten_short_result_fails_before_assignment(self):
        self.failure('ROUTINE make: ARRAY OF SHORT VAR p: ARRAY[2] OF SHORT BEGIN p[1]=0 RETURN p END make',kind='SHORT')

    def test_strict_short_marker_result_fails_before_assignment(self):
        state=self.failure('ROUTINE make: ARRAY OF SHORT VAR p: ARRAY[2] OF SHORT BEGIN p[1]=-32768 p[2]=32767 n=9 RETURN p END make',kind='SHORT')
        self.assertEqual(state['N'],9)

    def test_byte_range_failure_preserves_earlier_effects(self):
        state=self.failure('ROUTINE make: ARRAY OF BYTE VAR p: ARRAY[2] OF BYTE BEGIN n=9 p[1]=256 RETURN p END make',message='0..255')
        self.assertEqual(state['N'],9)

    def test_short_range_failure_preserves_earlier_effects(self):
        self.failure('ROUTINE make: ARRAY OF SHORT VAR p: ARRAY[2] OF SHORT BEGIN n=9 p[1]=-32769 RETURN p END make',kind='SHORT',message='outside')

    def test_length_mismatch_does_not_resize_destination(self):
        self.failure(factory(values=(0,1,255)),message='identical type and size')

    def test_legacy_no_whole_array_numeric_promotion_in_return(self):
        for result,source in (('BYTE','INTEGER'),('SHORT','INTEGER'),('SHORT','BYTE'),('BYTE','SHORT')):
            with self.subTest(result=result,source=source):
                self.rejected('E_RETURN',body='',routines=f'ROUTINE make: ARRAY OF {result} VAR p: ARRAY[1] OF {source} BEGIN p[1]=1 RETURN p END make',_translator=legacy_translate)

    def test_legacy_no_whole_array_numeric_promotion_in_assignment(self):
        for kind in ('BYTE','SHORT'):
            for destination in ('INTEGER','REAL','BOOLEAN',('SHORT' if kind=='BYTE' else 'BYTE')):
                with self.subTest(kind=kind,destination=destination):
                    self.rejected('E_TYPE',kind=kind,declarations=f'a: ARRAY[2] OF {destination}',_translator=legacy_translate)

    def test_result_still_requires_direct_assignment_context(self):
        for kind in ('BYTE','SHORT'):
            for body in ('a=(make())','n=ARRAY_LEN(make())','use(make())'):
                with self.subTest(kind=kind,body=body):
                    self.rejected('E_ARRAY_RESULT_CONTEXT',kind=kind,body=body,routines=factory(kind)+f'\nROUTINE use(p: ARRAY OF {kind}) BEGIN END use', _translator=legacy_translate)

    def test_direct_scalar_narrow_results_are_pythonic_extensions(self):
        for kind in ('BYTE','SHORT'):
            with self.subTest(kind=kind):
                routine=f'ROUTINE make: {kind} BEGIN RETURN 1 END make'
                self.assertEqual(execute(body='n=make()',declarations='n: INTEGER',routines=routine)['N'],1)
                self.rejected('E_RETURN_TYPE',body='',routines=routine,_translator=legacy_translate)

    def test_byte_initialization_query_remains_blocked(self): self.rejected('E_BYTE_UNINIT',body='IF UNINIT(a[1]) THEN ENDIF')

    def test_short_can_be_reinitialized_after_marker_before_return(self):
        routine='ROUTINE make: ARRAY OF SHORT VAR p: ARRAY[2] OF SHORT BEGIN p[1]=32767 p[2]=32766 IF UNINIT(p[1]) THEN p[1]=-32768 ENDIF RETURN p END make'
        self.assertEqual(execute(kind='SHORT',routines=routine)['A'],[-32768,32766])

    def test_whole_array_value_argument_remains_blocked(self):
        self.rejected('E_ARRAY_VALUE',body='use((a))',routines='ROUTINE use(p: ARRAY OF BYTE) BEGIN END use', _translator=legacy_translate)

    def test_named_byte_array_source_returns_owned_anonymous_storage(self):
        p,_=compile_program(types='TYPE row_t=ARRAY[2]OF BYTE',routines='ROUTINE make:ARRAY OF BYTE VAR p:row_t BEGIN p[1]=7 RETURN p END make')
        self.assertEqual(p.run()['A'],[7,{'unknown_byte':True}]);self.assertEqual(len(p._state.raw('A').spec),3)


class NarrowArrayRuntimeTests(unittest.TestCase):
    def copy(self,kind,values):
        source=rt.Array(('ARRAY',len(values),(kind,))); source.values[:]=values
        return source,rt.array_result(('ARRAY',None,(kind,)),source,23)

    def test_all_256_byte_values_survive_without_coercion(self):
        source,copied=self.copy('BYTE',list(range(256)))
        self.assertEqual(copied.snapshot(),list(range(256)))
        self.assertEqual(copied.spec,('ARRAY',256,rt.BYTE))
        self.assertIsNot(source.values,copied.values)
        copied.set(1,255); self.assertEqual(source.get(1),0)

    def test_short_boundaries_and_interior_values(self):
        source,copied=self.copy('SHORT',[-32768,-1,0,1,32766])
        self.assertEqual(copied.snapshot(),[-32768,-1,0,1,32766])
        source.set(2,7); self.assertEqual(copied.get(2),-1)

    def test_invalid_byte_leaves_never_escape(self):
        for value in (-1,256,True,False,1.,'1',rt.UNKNOWN_BYTE,rt.UNINITIALIZED):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(rt.KarelRuntimeError,'line 23'): self.copy('BYTE',[0,value,255])

    def test_invalid_short_leaves_and_raw_32767_marker_never_escape(self):
        for value in (-32769,32768,32767,True,1.,'1',rt.UNKNOWN_BYTE,rt.UNINITIALIZED):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(rt.KarelRuntimeError,'line 23'): self.copy('SHORT',[-32768,value,32766])

    def test_failed_copy_does_not_change_source(self):
        source=rt.Array(('ARRAY',3,rt.SHORT)); source.values[:]=[-32768,32767,32766]
        with self.assertRaises(rt.KarelRuntimeError): rt.array_result(('ARRAY',None,rt.SHORT),source,23)
        self.assertEqual(source.values,[-32768,32767,32766])

    def test_runtime_does_not_promote_array_elements(self):
        source,_=self.copy('BYTE',[0,255])
        for formal in (rt.SHORT,rt.INTEGER,rt.REAL):
            with self.subTest(formal=formal):
                with self.assertRaisesRegex(rt.KarelRuntimeError,'matching'): rt.array_result(('ARRAY',None,formal),source,23)


if __name__=='__main__': unittest.main()
