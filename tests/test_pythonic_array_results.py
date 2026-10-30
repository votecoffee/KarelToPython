"""Named and shaped ARRAY result declarations with detached checked storage."""
import ast
import json
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.test_structure_routines import initialized_host


BASE='n,x,y: INTEGER flag: BOOLEAN'
FILL='data[1]=1 data[2]=2'
MATRIX_FILL='data[1,1]=1 data[1,2]=2 data[1,3]=3 data[2,1]=4 data[2,2]=5 data[2,3]=6'
UNKNOWN={'uninitialized':True}


def factory(result='ARRAY[2] OF INTEGER', storage='ARRAY[2] OF INTEGER', fill=FILL, returned='data'):
    return f'ROUTINE build: {result}\nVAR data: {storage}\nBEGIN n=n+1 {fill} RETURN {returned} END build'


def compile_program(body='target=build()', *, result='ARRAY[2] OF INTEGER', storage='ARRAY[2] OF INTEGER',
                    fill=FILL, routines=None, declarations='target: ARRAY[2] OF INTEGER', types='', prefix='', shapes=None, **context):
    routines=factory(result,storage,fill) if routines is None else routines
    source=f'PROGRAM T\n{prefix}\n{types}\nVAR {BASE}\n{declarations}\n{routines}\nBEGIN n=0 {body} END T'
    translated=translate(source,filename='array_result_shapes.kl',array_shapes=shapes)
    ast.parse(translated.python_source,feature_version=(3,11))
    json.dumps(translated.report)
    namespace={'__name__':'array_result_shape_test'}
    exec(translated.python_source,namespace)
    return namespace['Program'](**context),translated


def execute(*args,**kwargs): return compile_program(*args,**kwargs)[0].run()


class ResultDeclarationTests(unittest.TestCase):
    def test_fixed_one_dimensional_result(self):
        state=execute()
        self.assertEqual((state['TARGET'],state['N']),([1,2],1))

    def test_explicit_wildcard_one_dimensional_result(self):
        self.assertEqual(execute(result='ARRAY[*] OF INTEGER')['TARGET'],[1,2])

    def test_omitted_dimensions_keep_existing_rank_one_behavior(self):
        self.assertEqual(execute(result='ARRAY OF INTEGER')['TARGET'],[1,2])

    def test_fixed_matrix_result(self):
        state=execute(result='ARRAY[2,3] OF INTEGER',storage='ARRAY[2,3] OF INTEGER',fill=MATRIX_FILL,declarations='target: ARRAY[2,3] OF INTEGER')
        self.assertEqual(state['TARGET'],[[1,2,3],[4,5,6]])

    def test_wildcard_matrix_result(self):
        state=execute(result='ARRAY[*,*] OF INTEGER',storage='ARRAY[2,3] OF INTEGER',fill=MATRIX_FILL,declarations='target: ARRAY[2,3] OF INTEGER')
        self.assertEqual(state['TARGET'],[[1,2,3],[4,5,6]])

    def test_mixed_matrix_dimensions(self):
        for result in ('ARRAY[*,3] OF INTEGER','ARRAY[2,*] OF INTEGER'):
            with self.subTest(result=result):
                self.assertEqual(execute(result=result,storage='ARRAY[2,3] OF INTEGER',fill=MATRIX_FILL,declarations='target: ARRAY[2,3] OF INTEGER')['TARGET'],[[1,2,3],[4,5,6]])

    def test_fixed_cube_result(self):
        self.assertEqual(execute(result='ARRAY[1,1,2] OF INTEGER',storage='ARRAY[1,1,2] OF INTEGER',fill='data[1,1,1]=7 data[1,1,2]=8',declarations='target: ARRAY[1,1,2] OF INTEGER')['TARGET'],[[[7,8]]])

    def test_wildcard_cube_result(self):
        self.assertEqual(execute(result='ARRAY[*,*,*] OF INTEGER',storage='ARRAY[1,1,2] OF INTEGER',fill='data[1,1,1]=7 data[1,1,2]=8',declarations='target: ARRAY[1,1,2] OF INTEGER')['TARGET'],[[[7,8]]])

    def test_global_constant_dimension_expression(self):
        self.assertEqual(execute(result='ARRAY[WIDTH+1] OF INTEGER',prefix='CONST WIDTH=1')['TARGET'],[1,2])

    def test_named_scalar_array_result(self):
        self.assertEqual(execute(result='row_t',storage='row_t',types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='target: row_t')['TARGET'],[1,2])

    def test_named_flat_matrix_result(self):
        self.assertEqual(execute(result='matrix_t',storage='matrix_t',fill=MATRIX_FILL,types='TYPE matrix_t=ARRAY[2,3] OF INTEGER',declarations='target: matrix_t')['TARGET'],[[1,2,3],[4,5,6]])

    def test_named_component_matrix_result(self):
        types='TYPE row_t=ARRAY[2] OF INTEGER plane_t=ARRAY[2] OF row_t'
        self.assertEqual(execute(result='plane_t',storage='plane_t',fill='data[1,1]=1 data[1,2]=2 data[2,1]=3 data[2,2]=4',types=types,declarations='target: plane_t')['TARGET'],[[1,2],[3,4]])

    def test_named_cube_result(self):
        self.assertEqual(execute(result='cube_t',storage='cube_t',fill='data[1,1,1]=7 data[1,1,2]=8',types='TYPE cube_t=ARRAY[1,1,2] OF INTEGER',declarations='target: cube_t')['TARGET'],[[[7,8]]])

    def test_fixed_outer_with_named_inner_component(self):
        self.assertEqual(execute(result='ARRAY[1] OF row_t',storage='ARRAY[1] OF row_t',fill='data[1,1]=7 data[1,2]=8',types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='target: ARRAY[1] OF row_t')['TARGET'],[[7,8]])

    def test_wildcard_outer_with_named_inner_component(self):
        self.assertEqual(execute(result='ARRAY[*] OF row_t',storage='ARRAY[1] OF row_t',fill='data[1,1]=7 data[1,2]=8',types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='target: ARRAY[1] OF row_t')['TARGET'],[[7,8]])

    def test_matrix_outer_plus_named_inner_reaches_rank_three(self):
        self.assertEqual(execute(result='ARRAY[*,1] OF row_t',storage='ARRAY[1,1] OF row_t',fill='data[1,1,1]=7 data[1,1,2]=8',types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='target: ARRAY[1,1] OF row_t')['TARGET'],[[[7,8]]])

    def test_boolean_matrix_result(self):
        self.assertEqual(execute(result='ARRAY[1,2] OF BOOLEAN',storage='ARRAY[1,2] OF BOOLEAN',fill='data[1,1]=TRUE data[1,2]=FALSE',declarations='target: ARRAY[1,2] OF BOOLEAN')['TARGET'],[[True,False]])

    def test_rounded_real_matrix_result(self):
        self.assertEqual(execute(result='ARRAY[*,*] OF REAL',storage='ARRAY[1,2] OF REAL',fill='data[1,1]=0.1 data[1,2]=0.2',declarations='target: ARRAY[1,2] OF REAL')['TARGET'],[[.1,.2]])

    def test_narrow_matrix_results(self):
        for kind,first,last in [('BYTE',0,255),('SHORT',-32768,32766)]:
            with self.subTest(kind=kind):
                self.assertEqual(execute(result=f'ARRAY[1,2] OF {kind}',storage=f'ARRAY[1,2] OF {kind}',fill=f'data[1,1]={first} data[1,2]={last}',declarations=f'target: ARRAY[1,2] OF {kind}')['TARGET'],[[first,last]])

    def test_bounded_string_matrix_result(self):
        self.assertEqual(execute(result='ARRAY[1,*] OF STRING[3]',storage='ARRAY[1,2] OF STRING[3]',fill="data[1,1]='abcde' data[1,2]=''",declarations='target: ARRAY[1,2] OF STRING[3]')['TARGET'],[['abc','']])

    def test_named_string_result(self):
        self.assertEqual(execute(result='words_t',storage='words_t',fill="data[1]='abcde' data[2]=''",types='TYPE words_t=ARRAY[2] OF STRING[3]',declarations='target: words_t')['TARGET'],['abc',''])


class ResultCompositionTests(unittest.TestCase):
    def test_named_result_forwarding(self):
        routines=factory('row_t','row_t')+'\nROUTINE outer: row_t BEGIN RETURN build END outer'
        self.assertEqual(execute('target=outer()',routines=routines,types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='target: row_t')['TARGET'],[1,2])

    def test_named_result_as_named_value_argument(self):
        routines=factory('row_t','row_t')+'\nROUTINE use(p: row_t) BEGIN p[1]=99 target=p END use'
        self.assertEqual(execute('use(build())',routines=routines,types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='target: row_t')['TARGET'],[99,2])

    def test_matrix_result_as_rank_matched_value_argument(self):
        routines=factory('ARRAY[*,*] OF INTEGER','ARRAY[2,3] OF INTEGER',MATRIX_FILL)+'\nROUTINE use(p: ARRAY[*,*] OF INTEGER) BEGIN p[1,1]=99 x=p[2,3] END use'
        state=execute('use(build())',routines=routines)
        self.assertEqual((state['X'],state['N']),(6,1))

    def test_mixed_result_direct_forwarding(self):
        routines=factory('ARRAY[*,3] OF INTEGER','ARRAY[2,3] OF INTEGER',MATRIX_FILL)+'\nROUTINE outer: ARRAY[2,*] OF INTEGER BEGIN RETURN build() END outer'
        self.assertEqual(execute('target=outer()',routines=routines,declarations='target: ARRAY[2,3] OF INTEGER')['TARGET'],[[1,2,3],[4,5,6]])

    def test_named_result_direct_index(self):
        state=execute('x=build()[2]',result='row_t',storage='row_t',types='TYPE row_t=ARRAY[2] OF INTEGER')
        self.assertEqual((state['X'],state['N']),(2,1))

    def test_matrix_result_direct_index(self):
        self.assertEqual(execute('x=build()[2,3]',result='ARRAY[*,*] OF INTEGER',storage='ARRAY[2,3] OF INTEGER',fill=MATRIX_FILL)['X'],6)

    def test_named_result_references_stay_private(self):
        routines='ROUTINE copy: row_t BEGIN RETURN source END copy\nROUTINE use(p: INTEGER) BEGIN p=99 x=p END use'
        state=execute('source[1]=1 source[2]=2 use(copy()[1])',routines=routines,types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='source: row_t')
        self.assertEqual((state['SOURCE'],state['X']),([1,2],99))

    def test_named_result_whole_assignment_preserves_captured_alias(self):
        routines=factory('row_t','row_t')+'\nROUTINE replace(p: row_t; cell: INTEGER) BEGIN p=build() cell=99 END replace'
        self.assertEqual(execute('replace(target,target[2])',routines=routines,types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='target: row_t')['TARGET'],[1,99])

    def test_named_result_from_matching_generic_parameter(self):
        routines='ROUTINE copy(p: ARRAY OF INTEGER): row_t BEGIN RETURN p END copy'
        self.assertEqual(execute('source[1]=1 source[2]=2 target=copy(source) source[1]=99',routines=routines,types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='source,target: row_t')['TARGET'],[1,2])

    def test_matrix_result_from_generic_parameter(self):
        routines='ROUTINE copy(p: ARRAY[*,*] OF INTEGER): ARRAY[*,3] OF INTEGER BEGIN RETURN p END copy'
        fill=MATRIX_FILL.replace('data','source')
        self.assertEqual(execute(fill+' target=copy(source)',routines=routines,declarations='source,target: ARRAY[2,3] OF INTEGER')['TARGET'],[[1,2,3],[4,5,6]])

    def test_global_wildcard_storage_can_supply_concrete_result(self):
        routines='ROUTINE copy: ARRAY[*,2] OF INTEGER BEGIN RETURN source END copy'
        fill='source[1,1]=1 source[1,2]=2 source[2,1]=3 source[2,2]=4'
        self.assertEqual(execute(fill+' target=copy()',routines=routines,declarations='source: ARRAY[*,2] OF INTEGER target: ARRAY[2,2] OF INTEGER',shapes={'SOURCE':[2,2]})['TARGET'],[[1,2],[3,4]])

    def test_recursive_named_result_unwinds(self):
        routines=factory('row_t','row_t')+'\nROUTINE recurse(k: INTEGER): row_t BEGIN IF k=0 THEN RETURN build() ELSE RETURN recurse(k-1) ENDIF END recurse'
        program,_=compile_program('target=recurse(8)',routines=routines,types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='target: row_t')
        self.assertEqual(program.run()['TARGET'],[1,2])
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))

    def test_named_subarray_can_be_returned_by_its_name(self):
        routines='ROUTINE build: row_t VAR rows: ARRAY[1] OF row_t BEGIN rows[1,1]=1 rows[1,2]=2 RETURN rows[1] END build'
        self.assertEqual(execute(routines=routines,types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='target: row_t')['TARGET'],[1,2])

    def test_named_result_from_record_field(self):
        routines='ROUTINE build: row_t VAR item: item_t BEGIN item.values[1]=1 item.values[2]=2 RETURN item.values END build'
        self.assertEqual(execute(routines=routines,types='TYPE row_t=ARRAY[2] OF INTEGER item_t=STRUCTURE values: row_t ENDSTRUCTURE',declarations='target: row_t')['TARGET'],[1,2])

    def test_labelled_matrix_return_matches_structured_execution(self):
        states=[]
        for marker in ('','unused:: '):
            routines=factory('ARRAY[*,*] OF INTEGER','ARRAY[2,3] OF INTEGER',MATRIX_FILL).replace('RETURN data',marker+'RETURN data')
            states.append(execute(routines=routines,declarations='target: ARRAY[2,3] OF INTEGER'))
        self.assertEqual(states[0],states[1])


class ArrayLengthTests(unittest.TestCase):
    def test_flat_matrix_first_dimension(self):
        self.assertEqual(execute('x=ARRAY_LEN(grid)',routines='',declarations='grid: ARRAY[2,3] OF INTEGER')['X'],2)

    def test_named_matrix_first_dimension(self):
        self.assertEqual(execute('x=ARRAY_LEN(grid)',routines='',types='TYPE grid_t=ARRAY[2,3] OF INTEGER',declarations='grid: grid_t')['X'],2)

    def test_named_nested_array_outer_count(self):
        self.assertEqual(execute('x=ARRAY_LEN(grid)',routines='',types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='grid: ARRAY[3] OF row_t')['X'],3)

    def test_cube_first_dimension(self):
        self.assertEqual(execute('x=ARRAY_LEN(grid)',routines='',declarations='grid: ARRAY[2,3,4] OF INTEGER')['X'],2)

    def test_selected_named_plane_first_dimension(self):
        self.assertEqual(execute('x=ARRAY_LEN(cube[1])',routines='',types='TYPE plane_t=ARRAY[3,4] OF INTEGER',declarations='cube: ARRAY[2] OF plane_t')['X'],3)

    def test_matrix_result_length_evaluated_once(self):
        state=execute('x=ARRAY_LEN(build())',result='ARRAY[*,*] OF INTEGER',storage='ARRAY[2,3] OF INTEGER',fill=MATRIX_FILL)
        self.assertEqual((state['X'],state['N']),(2,1))

    def test_wildcard_storage_length_requires_no_initialized_leaves(self):
        self.assertEqual(execute('x=ARRAY_LEN(grid)',routines='',declarations='grid: ARRAY[*,*] OF INTEGER',shapes={'GRID':[4,2]})['X'],4)

    def test_generic_parameter_reports_concrete_first_dimension(self):
        routines='ROUTINE use(p: ARRAY[*,*] OF INTEGER) BEGIN x=ARRAY_LEN(p) END use'
        self.assertEqual(execute('use(grid)',routines=routines,declarations='grid: ARRAY[2,3] OF INTEGER')['X'],2)

    def test_result_length_reads_shape_without_missing_element_values(self):
        program,_=compile_program('x=ARRAY_LEN(build())',fill='data[1]=1')
        state=program.run()
        self.assertEqual((state['N'],state['X']),(1,2))


class ResultFailureTests(unittest.TestCase):
    def reject(self,code,**kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(**kwargs)
        self.assertEqual(caught.exception.code,code)

    def test_invalid_fixed_dimensions(self):
        for size in ('0','-1','32768','TRUE','1.5'):
            with self.subTest(size=size): self.reject('E_SIZE',result=f'ARRAY[{size}] OF INTEGER')

    def test_four_explicit_dimensions_rejected(self):
        self.reject('E_ARRAY_RANK',result='ARRAY[*,*,*,*] OF INTEGER')

    def test_four_logical_dimensions_rejected(self):
        self.reject('E_ARRAY_RANK',result='ARRAY[*,*] OF plane_t',types='TYPE plane_t=ARRAY[1,1] OF INTEGER')

    def test_fixed_result_leaf_budget(self):
        self.reject('E_ARRAY_CAPACITY',result='ARRAY[10923] OF VECTOR')

    def test_wildcard_result_minimum_leaf_budget(self):
        self.reject('E_ARRAY_CAPACITY',result='ARRAY[*,10923] OF VECTOR')

    def test_local_constant_cannot_define_interface_size(self):
        self.reject('E_CONSTANT',routines='ROUTINE build: ARRAY[M] OF INTEGER CONST M=2 BEGIN END build')

    def test_runtime_expression_cannot_define_interface_size(self):
        self.reject('E_CONSTANT',result='ARRAY[n] OF INTEGER')

    def test_inherited_string_capacity_still_rejects_integer_return_storage(self):
        self.reject('E_RETURN',result='ARRAY[2] OF STRING')

    def test_inline_anonymous_nested_component_remains_blocked(self):
        self.reject('E_RETURN_TYPE',result='ARRAY[2] OF ARRAY[2] OF INTEGER')

    def test_named_type_must_precede_routine(self):
        source='PROGRAM T ROUTINE build: row_t BEGIN END build TYPE row_t=ARRAY[2] OF INTEGER BEGIN END T'
        with self.assertRaises(TranslationError) as caught: translate(source)
        self.assertEqual(caught.exception.code,'E_TYPE')

    def test_distinct_named_result_owns_declared_identity(self):
        p,_=compile_program(result='row_t',storage='other_t',types='TYPE row_t=ARRAY[2]OF INTEGER other_t=ARRAY[2]OF INTEGER',declarations='target:row_t')
        self.assertEqual(p.run()['TARGET'],[1,2]);self.assertEqual(p._state.raw('TARGET').spec[3],'ROW_T')

    def test_anonymous_storage_is_captured_in_declared_named_result(self):
        p,_=compile_program(result='row_t',types='TYPE row_t=ARRAY[2]OF INTEGER');self.assertEqual(p.run()['TARGET'],[1,2])
        self.assertEqual(len(p._state.raw('TARGET').spec),3)

    def test_named_storage_returns_independent_anonymous_result(self):
        p,_=compile_program(result='ARRAY[*]OF INTEGER',storage='row_t',types='TYPE row_t=ARRAY[2]OF INTEGER')
        self.assertEqual(p.run()['TARGET'],[1,2]);self.assertEqual(len(p._state.raw('TARGET').spec),3)

    def test_known_fixed_shape_mismatch_rejected(self):
        self.reject('E_RETURN',result='ARRAY[3] OF INTEGER')

    def test_known_rank_mismatch_rejected(self):
        self.reject('E_RETURN',result='ARRAY[*,*] OF INTEGER')

    def test_flat_source_is_captured_in_declared_named_components(self):
        p,_=compile_program(result='ARRAY[*]OF row_t',storage='ARRAY[2,2]OF INTEGER',types='TYPE row_t=ARRAY[2]OF INTEGER',fill='data[1,1]=7',declarations='target:ARRAY[2]OF row_t')
        self.assertEqual(p.run()['TARGET'][0][0],7);self.assertEqual(p._state.raw('TARGET').spec[2][3],'ROW_T')

    def test_undefined_named_result_type(self):
        self.reject('E_TYPE',result='missing_t')

    def test_wildcard_local_storage_is_still_blocked(self):
        self.reject('E_VARIABLE_ARRAY_SCOPE',storage='ARRAY[*] OF INTEGER')

    def test_wildcard_named_type_is_still_blocked(self):
        self.reject('E_VARIABLE_ARRAY_SCOPE',types='TYPE row_t=ARRAY[*] OF INTEGER',result='row_t')

    def test_generic_shape_mismatch_preserves_destination_and_effects(self):
        routines='ROUTINE copy(p: ARRAY[*,*] OF INTEGER): ARRAY[2,2] OF INTEGER BEGIN n=7 RETURN p END copy'
        fill=MATRIX_FILL.replace('data','source')
        program,_=compile_program(fill+' target[1,1]=42 target=copy(source)',routines=routines,declarations='source: ARRAY[2,3] OF INTEGER target: ARRAY[2,2] OF INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'matching logical dimensions'): program.run()
        self.assertEqual((program.snapshot()['TARGET'][0][0],program.snapshot()['N']),(42,7))
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))

    def test_generic_named_result_copy_preserves_receiver_schema(self):
        routines='ROUTINE copy(p:ARRAY OF INTEGER):row_t BEGIN RETURN p END copy'
        p,_=compile_program('source[1]=1 source[2]=2 target[1]=42 target=copy(source)',routines=routines,types='TYPE row_t=ARRAY[2]OF INTEGER',declarations='source:ARRAY[2]OF INTEGER target:row_t')
        self.assertEqual(p.run()['TARGET'],[1,2]);self.assertEqual(p._state.raw('TARGET').spec[3],'ROW_T');self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))

    def test_partial_matrix_result_preserves_unknown_and_unwinds(self):
        program,_=compile_program(result='ARRAY[*,*] OF INTEGER',storage='ARRAY[1,2] OF INTEGER',fill='data[1,1]=1',declarations='target: ARRAY[1,2] OF INTEGER')
        state=program.run()
        self.assertEqual(state['TARGET'],[[1,UNKNOWN]])
        self.assertEqual((state['N'],program._state.local_frames,program._state.call_depth),(1,[],0))

    def test_missing_named_return_unwinds(self):
        program,_=compile_program(routines='ROUTINE build: row_t BEGIN n=7 END build',types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='target: row_t')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'RETURN'): program.run()
        self.assertEqual((program.snapshot()['N'],program._state.local_frames,program._state.call_depth),(7,[],0))

    def test_abort_in_named_result_stays_distinct(self):
        program,_=compile_program(routines='ROUTINE build: row_t BEGIN n=7 ABORT END build',types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='target: row_t')
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual((program.snapshot()['N'],program._state.local_frames,program._state.call_depth),(7,[],0))


class ResultRuntimeTests(unittest.TestCase):
    def copy(self,spec,value):
        with rt._numeric_scope('pythonic'): return rt.array_result(spec,value,91)

    def test_runtime_fixed_matrix_copy(self):
        source=initialized_host(('ARRAY',(2,3),rt.INTEGER))
        copied=self.copy(source.spec,source)
        copied.set((1,1),9)
        self.assertEqual(source.raw((1,1)),1)

    def test_runtime_mixed_matrix_shape_inheritance(self):
        source=initialized_host(('ARRAY',(2,3),rt.INTEGER))
        self.assertEqual(self.copy(('ARRAY',(None,3),rt.INTEGER),source).spec,source.spec)

    def test_runtime_named_result_retains_identity(self):
        source=initialized_host(('ARRAY',2,rt.INTEGER,'ROW_T'))
        self.assertEqual(self.copy(source.spec,source).spec,source.spec)

    def test_runtime_named_inner_identity_is_preserved(self):
        row=('ARRAY',2,rt.INTEGER,'ROW_T'); source=initialized_host(('ARRAY',(1,1),row))
        copied=self.copy(('ARRAY',(None,1),row),source)
        self.assertEqual(copied.spec,source.spec)
        self.assertIsNot(copied.values[0],source.values[0])

    def test_runtime_all_record_terminals_in_matrix_results(self):
        for kind in rt.DATA_RECORD_TYPES:
            with self.subTest(kind=kind):
                source=initialized_host(('ARRAY',(1,2),(kind,)))
                copied=self.copy(('ARRAY',(None,None),(kind,)),source)
                self.assertEqual(copied.snapshot(),source.snapshot())
                self.assertIsNot(copied.values[0],source.values[0])

    def test_runtime_joint_matrix_result(self):
        source=initialized_host(('ARRAY',(1,2),('JOINTPOS',2)))
        copied=self.copy(('ARRAY',(None,2),('JOINTPOS',2)),source)
        copied.values[0].values[0]=9.
        self.assertEqual(source.values[0].values[0],1.)

    def test_runtime_string_capacity_retained(self):
        source=initialized_host(('ARRAY',(1,2),('STRING',3)))
        self.assertEqual(self.copy(('ARRAY',(None,2),('STRING',3)),source).spec,source.spec)

    def test_runtime_matrix_shape_mismatch(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'line 91'): self.copy(('ARRAY',(None,2),rt.INTEGER),initialized_host(('ARRAY',(2,3),rt.INTEGER)))

    def test_runtime_named_type_mismatch(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identical named ARRAY'): self.copy(('ARRAY',2,rt.INTEGER,'ROW_T'),initialized_host(('ARRAY',2,rt.INTEGER,'OTHER_T')))

    def test_runtime_anonymous_declaration_keeps_named_identity_guard(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'anonymous outer'): self.copy(('ARRAY',None,rt.INTEGER),initialized_host(('ARRAY',2,rt.INTEGER,'ROW_T')))

    def test_runtime_bad_declaration_shapes(self):
        for shape in ((),(None,)*4,0,True,32768,(None,0),(None,1.5)):
            with self.subTest(shape=shape),self.assertRaises(rt.KarelRuntimeError):
                self.copy(('ARRAY',shape,rt.INTEGER),initialized_host(('ARRAY',2,rt.INTEGER)))

    def test_runtime_named_declaration_cannot_have_wildcards(self):
        with self.assertRaises(rt.KarelRuntimeError): self.copy(('ARRAY',None,rt.INTEGER,'ROW_T'),initialized_host(('ARRAY',2,rt.INTEGER,'ROW_T')))

    def test_runtime_bad_root_specs(self):
        for spec in (None,[],(),('ARRAY',),('ARRAY',2,()),('ARRAY',2,rt.INTEGER,'ROW_T','extra')):
            with self.subTest(spec=spec),self.assertRaises(rt.KarelRuntimeError): self.copy(spec,initialized_host(('ARRAY',2,rt.INTEGER)))

    def test_runtime_malformed_matrix_storage(self):
        source=initialized_host(('ARRAY',(2,3),rt.INTEGER)); source.values.pop()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'shape and storage'): self.copy(('ARRAY',(None,3),rt.INTEGER),source)

    def test_runtime_actual_shape_must_be_concrete(self):
        source=initialized_host(('ARRAY',(2,3),rt.INTEGER)); source.spec=('ARRAY',(None,3),rt.INTEGER)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'concrete shape'): self.copy(('ARRAY',(None,3),rt.INTEGER),source)

    def test_runtime_leaf_limit_before_copy(self):
        source=initialized_host(('ARRAY',(1,1),rt.INTEGER)); source.spec=('ARRAY',(32767,2),rt.INTEGER); source.shape=(32767,2)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'32767 scalar leaves'): self.copy(('ARRAY',(None,2),rt.INTEGER),source)

    def test_runtime_position_protection_is_retained(self):
        source=initialized_host(('ARRAY',(1,1),('POSITION',),'POSES_T'))
        copied=self.copy(source.spec,source)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'read-only'): rt.field_reference(copied.values[0].values['NORMAL'],'X').set(9.)

    def test_runtime_array_len_checks_host_shape(self):
        source=rt.Array(('ARRAY',(2,3),rt.INTEGER)); source.shape=(3,2)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'concrete valid shape'): rt.builtin('ARRAY_LEN',[source],91)

    def test_reports_record_result_shape_and_identity(self):
        _,result=compile_program(result='row_t',storage='row_t',types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='target: row_t')
        declaration=result.report['array_result_declarations'][0]
        self.assertEqual((declaration['nominal_identity'],declaration['declared_dimensions'],declaration['logical_rank']),('ROW_T',(2,),1))
        self.assertEqual(result.report['array_returns'][0]['result_spec'],('ARRAY',2,rt.INTEGER,'ROW_T'))
        self.assertFalse(result.report['array_length_policy']['controller_validated'])

    def test_reports_keep_wildcard_mask(self):
        _,result=compile_program(result='ARRAY[*,3] OF INTEGER',storage='ARRAY[2,3] OF INTEGER',fill=MATRIX_FILL,declarations='target: ARRAY[2,3] OF INTEGER')
        self.assertEqual(result.report['array_result_declarations'][0]['declared_dimensions'],(None,3))
        self.assertIn('First concrete dimension',result.report['array_length_policy']['result'])


if __name__=='__main__': unittest.main()
