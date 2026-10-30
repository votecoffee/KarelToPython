"""Inherited concrete STRING capacities in anonymous owned ARRAY results."""
import ast
import json
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


MISSING={'uninitialized':True}
FACTORY="ROUTINE make: ARRAY OF STRING VAR p:ARRAY[2]OF STRING[3] BEGIN p[1]='abc' p[2]='' RETURN p END make"
COPY='ROUTINE copy(p:ARRAY OF STRING):ARRAY OF STRING BEGIN RETURN p END copy'


def compile_program(body='a=make()',*,routines=FACTORY,declarations='a,b:ARRAY[2]OF STRING[3] n:INTEGER flag:BOOLEAN text:STRING[8]',
        types='',shapes=None,translator=translate,**options):
    source=f'PROGRAM MAIN {types} VAR {declarations} {routines} BEGIN {body} END MAIN'
    result=translator(source,filename='inherited_string_array.kl',array_shapes=shapes)
    ast.parse(result.python_source,feature_version=(3,11));json.dumps(result.report)
    namespace={'__name__':'inherited_string_array_test'};exec(result.python_source,namespace)
    return namespace['Program'](**options),result


def execute(*args,**kwargs):return compile_program(*args,**kwargs)[0].run()


def copied(value,spec=('ARRAY',None,('STRING',None))):
    with rt._numeric_scope('pythonic'):return rt.array_result(spec,value,73)


def array(capacity=3,values=('abc','')):
    result=rt.Array(('ARRAY',len(values),('STRING',capacity)));result.values[:]=values;return result


class InheritedStringArraySourceTests(unittest.TestCase):
    def test_omitted_dimensions_and_capacity_inherit_concrete_storage(self):
        program,_=compile_program();self.assertEqual(program.run()['A'],['abc',''])
        self.assertEqual(program._state.raw('A').spec,('ARRAY',2,('STRING',3)))

    def test_fixed_and_explicit_wildcard_dimensions(self):
        for result in ('ARRAY[2]OF STRING','ARRAY[*]OF STRING'):
            with self.subTest(result=result):self.assertEqual(execute(routines=FACTORY.replace('ARRAY OF STRING',result))['A'],['abc',''])

    def test_concrete_capacity_endpoints_are_inherited_without_default(self):
        for capacity in (1,254):
            with self.subTest(capacity=capacity):
                routine=f"ROUTINE make:ARRAY OF STRING VAR p:ARRAY[1]OF STRING[{capacity}] BEGIN p[1]='x' RETURN p END make"
                program,_=compile_program(routines=routine,declarations=f'a:ARRAY[1]OF STRING[{capacity}]')
                self.assertEqual(program.run()['A'],['x']);self.assertEqual(program._state.raw('A').spec[2],('STRING',capacity))

    def test_fixed_wildcard_and_mixed_matrix_dimensions(self):
        for result in ('ARRAY[2,2]OF STRING','ARRAY[*,*]OF STRING','ARRAY[2,*]OF STRING','ARRAY[*,2]OF STRING'):
            with self.subTest(result=result):
                routine=f"ROUTINE make:{result} VAR p:ARRAY[2,2]OF STRING[4] BEGIN p[1,1]='abcd' p[2,2]='z' RETURN p END make"
                data=execute(routines=routine,declarations='a:ARRAY[2,2]OF STRING[4]')
                self.assertEqual(data['A'],[['abcd',MISSING],[MISSING,'z']])

    def test_cube_retains_rank_and_concrete_capacity(self):
        routine="ROUTINE make:ARRAY[*,1,2]OF STRING VAR p:ARRAY[1,1,2]OF STRING[5] BEGIN p[1,1,1]='abcde' p[1,1,2]='x' RETURN p END make"
        self.assertEqual(execute(routines=routine,declarations='a:ARRAY[1,1,2]OF STRING[5]')['A'],[[['abcde','x']]])

    def test_global_source_and_returned_copy_are_independent(self):
        data=execute("a[1]='abc' b=get() a[1]='z'",routines='ROUTINE get:ARRAY OF STRING BEGIN RETURN ((a)) END get')
        self.assertEqual((data['A'],data['B']),(['z',MISSING],['abc',MISSING]))

    def test_one_generic_function_inherits_each_actual_capacity_and_length(self):
        data=execute("a[1]='abc' b[1]='wxyz' c=copy(a) d=copy(b)",routines=COPY,
            declarations='a,c:ARRAY[1]OF STRING[3] b,d:ARRAY[2]OF STRING[4]')
        self.assertEqual((data['C'],data['D']),(['abc'],['wxyz',MISSING]))

    def test_generic_matrix_forwarding_preserves_shape_and_capacity(self):
        routine='ROUTINE copy(p:ARRAY[*,*]OF STRING):ARRAY[2,*]OF STRING BEGIN RETURN p END copy'
        self.assertEqual(execute("a[2,1]='hello' b=copy(a)",routines=routine,declarations='a,b:ARRAY[2,1]OF STRING[5]')['B'],[[MISSING],['hello']])

    def test_direct_function_result_forwarding_is_independent(self):
        routine=FACTORY+' ROUTINE forward:ARRAY OF STRING BEGIN RETURN make() END forward'
        self.assertEqual(execute('a=forward() a[1]=\'z\' b=forward()',routines=routine)['B'],['abc',''])

    def test_inherited_result_can_feed_an_explicit_bounded_result(self):
        routine=FACTORY+' ROUTINE forward:ARRAY OF STRING[3] BEGIN RETURN make() END forward'
        self.assertEqual(execute('a=forward()',routines=routine)['A'],['abc',''])

    def test_explicit_bounded_result_can_feed_an_inherited_result(self):
        routine=FACTORY.replace('make: ARRAY OF STRING','make: ARRAY OF STRING[3]')+' ROUTINE forward:ARRAY OF STRING BEGIN RETURN make() END forward'
        self.assertEqual(execute('a=forward()',routines=routine)['A'],['abc',''])

    def test_structure_field_source_and_destination(self):
        types='TYPE box_t=STRUCTURE words:ARRAY[2]OF STRING[3] ENDSTRUCTURE'
        routine='ROUTINE get:ARRAY OF STRING BEGIN RETURN first.words END get'
        data=execute("first.words[1]='abc' second.words=get() first.words[1]='z'",types=types,
            declarations='first,second:box_t',routines=routine)
        self.assertEqual(data['SECOND']['WORDS'],['abc',MISSING])

    def test_global_wildcard_context_supplies_shape_but_not_new_capacity(self):
        program,_=compile_program(declarations='a:ARRAY[*]OF STRING[3]',shapes={'a':[2]})
        self.assertEqual(program.run()['A'],['abc','']);self.assertEqual(program._state.raw('A').spec[2],('STRING',3))

    def test_partial_string_leaves_remain_missing_and_scalar_reads_fail(self):
        routine=FACTORY.replace("p[2]=''",'')
        program,_=compile_program('a=make() flag=UNINIT(a[2]) text=a[2]',routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'):program.run()
        self.assertEqual((program.snapshot()['A'],program.snapshot()['FLAG']),(['abc',MISSING],True))

    def test_result_subscripts_have_string_type_and_evaluate_factory_once(self):
        routine=FACTORY.replace('BEGIN p[1]', 'BEGIN n=n+1 p[1]')
        data=execute('n=0 text=make()[1] flag=make()[2]=\'\'',routines=routine)
        self.assertEqual((data['TEXT'],data['FLAG'],data['N']),('abc',True,2))

    def test_result_subscript_supports_string_intrinsics_with_unknown_declared_capacity(self):
        data=execute('n=STR_LEN(make()[1]) text=SUB_STR(make()[1],2,2) flag=ORD(make()[1],1)=97')
        self.assertEqual((data['N'],data['TEXT'],data['FLAG']),(3,'bc',True))

    def test_result_string_subscript_can_be_mutated_privately(self):
        routine='ROUTINE get:ARRAY OF STRING BEGIN RETURN a END get ROUTINE change(p:STRING) BEGIN p=\'longer\' text=p END change'
        data=execute("a[1]='abc' change(get()[1])",routines=routine)
        self.assertEqual((data['A'],data['TEXT']),(['abc',MISSING],'lon'))

    def test_result_whole_value_argument_has_private_concrete_storage(self):
        routine='ROUTINE get:ARRAY OF STRING BEGIN RETURN a END get ROUTINE consume(p:ARRAY OF STRING) BEGIN p[1]=\'longer\' text=p[1] END consume'
        data=execute("a[1]='abc' consume(get())",routines=routine)
        self.assertEqual((data['A'],data['TEXT']),(['abc',MISSING],'lon'))

    def test_grouped_whole_array_argument_preserves_source_and_missing_markers(self):
        routine=COPY+' ROUTINE consume(p:ARRAY OF STRING) BEGIN b=copy(p) p[1]=\'local\' END consume'
        data=execute("a[1]='abc' consume((a))",routines=routine)
        self.assertEqual((data['A'],data['B']),(['abc',MISSING],['abc',MISSING]))

    def test_captured_string_alias_survives_whole_array_replacement(self):
        routine=FACTORY+' ROUTINE replace(p:ARRAY OF STRING; cell:STRING) BEGIN p=make() cell=\'z-long\' END replace'
        self.assertEqual(execute('replace(a,a[2])',routines=routine)['A'],['abc','z-l'])

    def test_recursive_forwarding_returns_checked_independent_copies(self):
        routine=FACTORY+" ROUTINE recur(k:INTEGER):ARRAY OF STRING VAR p:ARRAY[2]OF STRING[3] BEGIN IF k=0 THEN p=make() ELSE p=recur(k-1) p[2]='x' ENDIF RETURN p END recur"
        program,_=compile_program('a=recur(4)',routines=routine);self.assertEqual(program.run()['A'],['abc','x'])
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))


class InheritedStringArrayGuardTests(unittest.TestCase):
    def test_named_outer_storage_returns_owned_anonymous_storage(self):
        routine="ROUTINE make:ARRAY OF STRING VAR p:words_t BEGIN p[1]='abc' RETURN p END make"
        program,_=compile_program(routines=routine,types='TYPE words_t=ARRAY[2]OF STRING[3]')
        self.assertEqual(program.run()['A'],['abc',MISSING]);self.assertEqual(len(program._state.raw('A').spec),3)

    def test_named_actual_returns_private_value_through_generic_formal(self):
        program,_=compile_program("a[1]='abc' b=copy(a)",routines=COPY,types='TYPE words_t=ARRAY[2]OF STRING[3]',declarations='a:words_t b:ARRAY[2]OF STRING[3]')
        self.assertEqual(program.run()['B'],['abc',MISSING]);self.assertIsNot(program._state.raw('A'),program._state.raw('B'))
        self.assertEqual(program._state.local_frames,[])

    def test_fixed_shape_and_rank_mismatches_remain_static_errors(self):
        for result in ('ARRAY[3]OF STRING','ARRAY[*,*]OF STRING'):
            with self.subTest(result=result),self.assertRaises(TranslationError) as caught:
                compile_program(body='',routines=FACTORY.replace('ARRAY OF STRING',result))
            self.assertEqual(caught.exception.code,'E_RETURN')

    def test_non_string_returned_storage_remains_static_error(self):
        routine='ROUTINE make:ARRAY OF STRING VAR p:ARRAY[2]OF INTEGER BEGIN RETURN p END make'
        with self.assertRaises(TranslationError) as caught:compile_program(body='',routines=routine)
        self.assertEqual(caught.exception.code,'E_RETURN')

    def test_destination_capacity_conversion_preserves_receiver_capacity(self):
        program,_=compile_program("a[1]='keep' a[2]='safe' a=make()",declarations='a:ARRAY[2]OF STRING[4]')
        self.assertEqual(program.run()['A'],['abc','']);self.assertEqual(program._state.raw('A').spec[2],('STRING',4));self.assertEqual(program._state.local_frames,[])

    def test_generic_destination_retains_its_actual_capacity(self):
        routine=FACTORY+' ROUTINE put(p:ARRAY OF STRING) BEGIN n=9 p=make() END put'
        program,_=compile_program("a[1]='keep' a[2]='safe' put(a)",routines=routine,declarations='a:ARRAY[2]OF STRING[4] n:INTEGER')
        self.assertEqual((program.run()['A'],program.snapshot()['N']),(['abc',''],9));self.assertEqual(program._state.raw('A').spec[2],('STRING',4))

    def test_forward_to_explicit_bounded_result_uses_declared_capacity(self):
        routine=FACTORY+' ROUTINE forward:ARRAY OF STRING[4] BEGIN n=9 RETURN make() END forward'
        program,_=compile_program("a[1]='keep' a[2]='safe' a=forward()",routines=routine,declarations='a:ARRAY[2]OF STRING[4] n:INTEGER')
        self.assertEqual((program.run()['A'],program.snapshot()['N']),(['abc',''],9));self.assertEqual(program._state.raw('A').spec[2],('STRING',4))

    def test_explicit_capacity_return_prepares_declared_capacity(self):
        routine=FACTORY.replace('make: ARRAY OF STRING','make: ARRAY OF STRING[4]')
        program,_=compile_program(routines=routine);self.assertEqual(program.run()['A'],['abc',''])
        self.assertEqual(program._state.raw('A').spec[2],('STRING',3))

    def test_legacy_parser_still_rejects_omitted_string_capacity(self):
        with self.assertRaises(TranslationError) as caught:compile_program(translator=legacy_translate)
        self.assertEqual(caught.exception.code,'E_RETURN_TYPE')

    def test_pause_resume_retains_factory_storage_until_checked_return(self):
        program,_=compile_program(routines=FACTORY.replace('RETURN p','PAUSE RETURN p'))
        with self.assertRaises(rt.KarelPause):program.run()
        self.assertEqual(program.snapshot()['A'],[MISSING,MISSING]);self.assertTrue(program._state.local_frames)
        self.assertEqual(program.resume()['A'],['abc','']);self.assertEqual(program._state.local_frames,[])

    def test_stop_and_abort_unwind_without_replacing_destination(self):
        program,_=compile_program(routines=FACTORY.replace('RETURN p','PAUSE RETURN p'))
        with self.assertRaises(rt.KarelPause):program.run()
        program.stop();self.assertEqual(program.snapshot()['A'],[MISSING,MISSING]);self.assertEqual(program._state.local_frames,[])
        aborted,_=compile_program(routines=FACTORY.replace('RETURN p','ABORT RETURN p'))
        with self.assertRaises(rt.KarelAbort):aborted.run()
        self.assertEqual(aborted.snapshot()['A'],[MISSING,MISSING]);self.assertEqual(aborted._state.local_frames,[])

    def test_budget_failure_retains_destination_and_unwinds(self):
        program,_=compile_program(routines=FACTORY.replace('RETURN p','WHILE TRUE DO n=1 ENDWHILE RETURN p'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):program.run(max_steps=30)
        self.assertEqual(program.snapshot()['A'],[MISSING,MISSING]);self.assertEqual(program._state.local_frames,[])

    def test_context_roundtrip_retains_actual_string_capacity(self):
        program,result=compile_program();expected=program.run();saved=json.loads(json.dumps(program._state.execution.to_config()))
        context=rt.ExecutionContext.from_config(saved);namespace={'__name__':'inherited_string_restore'};exec(result.python_source,namespace)
        restored=namespace['Program'](context=context)
        self.assertEqual(restored.snapshot(),expected);self.assertEqual(restored._state.raw('A').spec[2],('STRING',3))


class InheritedStringArrayRuntimeTests(unittest.TestCase):
    def test_all_concrete_capacities_are_inherited_and_copied(self):
        for capacity in range(1,255):
            with self.subTest(capacity=capacity):
                value=array(capacity,('x'*capacity,''));result=copied(value)
                self.assertEqual(result.spec,value.spec);self.assertEqual(result.snapshot(),value.snapshot());self.assertIsNot(result,value)
                result.set(1,'z');self.assertEqual(value.get(1),'x'*capacity)

    def test_known_ascii_values_and_missing_leaves_are_not_formatted(self):
        value=array(4,('\0\r\x7f',rt.UNINITIALIZED));result=copied(value)
        self.assertEqual(result.snapshot(),['\0\r\x7f',MISSING]);self.assertIs(result.values[1],rt.UNINITIALIZED)

    def test_actual_capacity_must_be_concrete_integer_in_range(self):
        for capacity in (None,True,False,0,-1,255,1.5,'3'):
            with self.subTest(capacity=capacity):
                value=array();value.spec=('ARRAY',2,('STRING',capacity))
                with self.assertRaisesRegex(rt.KarelRuntimeError,'line 73'):copied(value)

    def test_malformed_actual_leaf_schema_is_rejected(self):
        for element in (('STRING',),('STRING',3,'EXTRA'),('INTEGER',),('STRING',254)):
            with self.subTest(element=element):
                value=array();value.spec=('ARRAY',2,element)
                if element==('STRING',254):value.values[1]='x'*255
                with self.assertRaises(rt.KarelRuntimeError):copied(value)

    def test_non_ascii_non_string_and_unknown_byte_leaves_fail_without_mutating_source(self):
        for invalid in ('\u00e9',1,True,rt.UNKNOWN_BYTE,['abc'],rt.Array(('ARRAY',1,('STRING',3)))):
            with self.subTest(invalid=invalid):
                value=array(values=('abc',invalid));before=list(value.values)
                with self.assertRaises(rt.KarelRuntimeError):copied(value)
                self.assertEqual(value.values,before)

    def test_oversize_known_leaf_is_rejected_instead_of_truncating(self):
        value=array(values=('abcd',''))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):copied(value)
        self.assertEqual(value.values,['abcd',''])

    def test_named_outer_or_named_component_cannot_be_erased(self):
        named=array();named.spec=('ARRAY',2,('STRING',3),'WORDS_T')
        with self.assertRaises(rt.KarelRuntimeError):copied(named)
        row=('ARRAY',2,('STRING',3),'ROW_T');nested=rt.Array(('ARRAY',1,row))
        with self.assertRaises(rt.KarelRuntimeError):copied(nested)

    def test_named_result_declaration_cannot_inherit_an_omitted_capacity(self):
        value=array();value.spec=('ARRAY',2,('STRING',3),'WORDS_T')
        with self.assertRaises(rt.KarelRuntimeError):copied(value,('ARRAY',2,('STRING',None),'WORDS_T'))

    def test_matrix_shape_and_storage_length_are_validated(self):
        value=rt.Array(('ARRAY',(2,2),('STRING',3)));value.values[:]=['abc',rt.UNINITIALIZED,'x','']
        result=copied(value,('ARRAY',(2,None),('STRING',None)))
        self.assertEqual(result.spec,value.spec);self.assertEqual(result.snapshot(),[['abc',MISSING],['x','']])
        value.values.pop()
        with self.assertRaises(rt.KarelRuntimeError):copied(value,('ARRAY',(None,None),('STRING',None)))

    def test_wrong_rank_fixed_shape_and_non_array_values_are_rejected(self):
        value=array()
        for spec in (('ARRAY',3,('STRING',None)),('ARRAY',(None,None),('STRING',None))):
            with self.subTest(spec=spec),self.assertRaises(rt.KarelRuntimeError):copied(value,spec)
        for value in (['abc',''],None,'abc'):
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError):copied(value)

    def test_scalar_leaf_limit_is_preserved(self):
        value=rt.Array(('ARRAY',32767,('STRING',1)));result=copied(value)
        self.assertEqual(len(result.values),32767)
        value.spec=('ARRAY',32768,('STRING',1));value.shape=(32768,);value.values.append(rt.UNINITIALIZED)
        with self.assertRaises(rt.KarelRuntimeError):copied(value)

    def test_bounded_declared_capacity_still_requires_exact_match(self):
        with self.assertRaises(rt.KarelRuntimeError):copied(array(4,('abcd','')),('ARRAY',None,('STRING',3)))

    def test_legacy_runtime_rejects_inherited_capacity(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.array_result(('ARRAY',None,('STRING',None)),array(),73)


class InheritedStringArrayProjectTests(unittest.TestCase):
    def sources(self,*,caller_result='ARRAY OF STRING',owner_result='ARRAY OF STRING'):
        return {'main':f"PROGRAM MAIN VAR result:ARRAY[2]OF STRING[6] text:STRING[8] ROUTINE words:{caller_result} FROM LIB BEGIN result=words() result[1]='local' text=words()[1] END MAIN",
            'lib':f"PROGRAM LIB VAR source:ARRAY[2]OF STRING[6] ROUTINE words:{owner_result} BEGIN source[1]='linked' RETURN source END words BEGIN END LIB"}

    def test_typed_from_result_keeps_source_capacity_and_private_copies(self):
        instance=translate_project(self.sources()).instantiate();instance.run('MAIN')
        main=instance.programs['MAIN'];owner=instance.programs['LIB']
        self.assertEqual((main.snapshot()['RESULT'],main.snapshot()['TEXT']),(['local',MISSING],'linked'))
        self.assertEqual(owner.snapshot()['SOURCE'],['linked',MISSING]);self.assertEqual(main._state.raw('RESULT').spec[2],('STRING',6))
        self.assertEqual((main._state.local_frames,owner._state.local_frames),([],[]))

    def test_typed_from_interfaces_remain_exact(self):
        project=translate_project(self.sources(owner_result='ARRAY OF STRING[6]'))
        with self.assertRaisesRegex(ValueError,'External routine type mismatch'):project.instantiate()


if __name__=='__main__':unittest.main()
