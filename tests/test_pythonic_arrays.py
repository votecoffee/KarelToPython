"""Owned ARRAY arguments, composable results and aggregate expression access."""
import ast
import json
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.test_structure_routines import initialized_host


DECLARATIONS = 'a,b: ARRAY[3] OF INTEGER n,x,y,i: INTEGER flag: BOOLEAN trace: STRING[32]'
FACTORY = '''ROUTINE make: ARRAY OF INTEGER VAR values: ARRAY[3] OF INTEGER
BEGIN n=n+1 values[1]=1 values[2]=2 values[3]=3 RETURN values END make'''
INITIALIZE = 'a[1]=1 a[2]=2 a[3]=3 '
UNKNOWN = {'uninitialized': True}


def compile_program(body, routines=FACTORY, *, declarations=DECLARATIONS, types='', shapes=None, **context):
    source=f"PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN\nn=0 trace=''\n{body}\nEND T"
    result=translate(source, filename='pythonic_arrays.kl', array_shapes=shapes)
    ast.parse(result.python_source, feature_version=(3, 11))
    json.dumps(result.report)
    namespace={'__name__': 'pythonic_array_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](**context), result


def execute(body, routines=FACTORY, **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


class ArrayCompositionTests(unittest.TestCase):
    def test_grouped_assignment_result(self):
        state=execute('a=(((make())))')
        self.assertEqual((state['A'], state['N']), ([1,2,3], 1))

    def test_grouped_bare_function_result(self):
        self.assertEqual(execute('a=(make)')['A'], [1,2,3])

    def test_function_result_in_array_len(self):
        state=execute('x=ARRAY_LEN(make())')
        self.assertEqual((state['X'], state['N']), (3,1))

    def test_bare_function_result_in_array_len(self):
        self.assertEqual(execute('x=ARRAY_LEN(make)')['X'], 3)

    def test_array_len_composes_with_arithmetic(self):
        state=execute('x=ARRAY_LEN(make())+ARRAY_LEN(make())')
        self.assertEqual((state['X'], state['N']), (6,2))

    def test_function_result_is_writable_private_actual(self):
        routine=FACTORY+'\nROUTINE use(p: ARRAY OF INTEGER) BEGIN p[1]=99 x=p[1] END use'
        state=execute(INITIALIZE+'use(make())', routine)
        self.assertEqual((state['A'], state['X'], state['N']), ([1,2,3],99,1))

    def test_bare_function_result_as_actual(self):
        routine=FACTORY+'\nROUTINE use(p: ARRAY OF INTEGER) BEGIN x=ARRAY_LEN(p) END use'
        self.assertEqual(execute('use(make)', routine)['X'], 3)

    def test_multiple_function_result_actuals_once(self):
        routine=FACTORY+'\nROUTINE use(p,q: ARRAY OF INTEGER) BEGIN p[1]=99 x=q[1] END use'
        state=execute('use(make(),make())', routine)
        self.assertEqual((state['X'], state['N']), (1,2))

    def test_direct_return_forwarding(self):
        routine=FACTORY+'\nROUTINE outer: ARRAY OF INTEGER BEGIN RETURN make() END outer'
        state=execute('a=outer()', routine)
        self.assertEqual((state['A'], state['N']), ([1,2,3],1))

    def test_grouped_bare_return_forwarding(self):
        routine=FACTORY+'\nROUTINE outer: ARRAY OF INTEGER BEGIN RETURN ((make)) END outer'
        self.assertEqual(execute('a=outer', routine)['A'], [1,2,3])

    def test_nested_result_as_array_argument_and_return(self):
        routine=FACTORY+'\nROUTINE bump(p: ARRAY OF INTEGER): ARRAY OF INTEGER BEGIN p[1]=p[1]+1 RETURN p END bump'
        self.assertEqual(execute('a=bump(bump(make()))', routine)['A'], [3,2,3])

    def test_string_array_result_actual_keeps_capacity(self):
        routine="ROUTINE make: ARRAY OF STRING[3] VAR values: ARRAY[1] OF STRING[3] BEGIN values[1]='a' RETURN values END make\nROUTINE use(p: ARRAY OF STRING) BEGIN p[1]='abcdef' x=STR_LEN(p[1]) END use"
        self.assertEqual(execute('use(make())',routine)['X'],3)

    def test_named_component_result_as_generic_value_actual(self):
        routine='ROUTINE make: ARRAY OF row_t VAR values: ARRAY[1] OF row_t BEGIN values[1,1]=7 values[1,2]=8 RETURN values END make\nROUTINE use(p: ARRAY[*,*] OF INTEGER) BEGIN p[1,2]=99 x=p[1,2] END use'
        self.assertEqual(execute('use(make())',routine,types='TYPE row_t=ARRAY[2] OF INTEGER')['X'],99)

    def test_recursive_direct_forwarding_unwinds(self):
        routine=FACTORY+'\nROUTINE recurse(k: INTEGER): ARRAY OF INTEGER BEGIN IF k=0 THEN RETURN make() ELSE RETURN recurse(k-1) ENDIF END recurse'
        program,_=compile_program('a=recurse(8)', routine)
        self.assertEqual(program.run()['A'], [1,2,3])
        self.assertEqual((program._state.local_frames,program._state.call_depth), ([],0))

    def test_conditional_return_values_have_independent_lengths(self):
        routine='ROUTINE choose(k: INTEGER): ARRAY OF INTEGER VAR small: ARRAY[1] OF INTEGER large: ARRAY[2] OF INTEGER BEGIN small[1]=7 large[1]=8 large[2]=9 IF k=1 THEN RETURN small ELSE RETURN large ENDIF END choose'
        state=execute('x=ARRAY_LEN(choose(1)) y=ARRAY_LEN(choose(2))', routine)
        self.assertEqual((state['X'],state['Y']), (1,2))

    def test_result_length_mismatch_preserves_destination(self):
        program,_=compile_program('a[1]=42 a=(make())', declarations='a: ARRAY[2] OF INTEGER n: INTEGER trace: STRING[32]')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identical type and size'): program.run()
        self.assertEqual((program.snapshot()['A'],program.snapshot()['N']), ([42,UNKNOWN],1))


class ArrayCopyTests(unittest.TestCase):
    def test_grouped_storage_has_no_copy_back(self):
        routine='ROUTINE use(p: ARRAY OF INTEGER) BEGIN p[1]=99 b=p END use'
        state=execute(INITIALIZE+'use((a))',routine)
        self.assertEqual((state['A'],state['B']), ([1,2,3],[99,2,3]))

    def test_bare_storage_still_aliases_caller(self):
        routine='ROUTINE use(p: ARRAY OF INTEGER) BEGIN p[1]=99 END use'
        self.assertEqual(execute(INITIALIZE+'use(a)',routine)['A'], [99,2,3])

    def test_two_value_copies_are_independent(self):
        routine='ROUTINE use(p,q: ARRAY OF INTEGER) BEGIN p[1]=99 x=q[1] END use'
        state=execute(INITIALIZE+'use((a),(a))',routine)
        self.assertEqual((state['A'],state['X']), ([1,2,3],1))

    def test_bare_forwarding_shares_private_copy(self):
        routine='ROUTINE inner(p: ARRAY OF INTEGER) BEGIN p[1]=99 END inner\nROUTINE outer(p: ARRAY OF INTEGER) BEGIN inner(p) x=p[1] END outer'
        state=execute(INITIALIZE+'outer((a))',routine)
        self.assertEqual((state['A'][0],state['X']), (1,99))

    def test_grouped_forwarding_makes_another_copy(self):
        routine='ROUTINE inner(p: ARRAY OF INTEGER) BEGIN p[1]=99 END inner\nROUTINE outer(p: ARRAY OF INTEGER) BEGIN inner((p)) x=p[1] END outer'
        state=execute(INITIALIZE+'outer((a))',routine)
        self.assertEqual((state['A'][0],state['X']), (1,1))

    def test_value_capture_precedes_later_mutating_argument(self):
        routine='ROUTINE change: INTEGER BEGIN a[1]=99 RETURN 1 END change\nROUTINE use(p: ARRAY OF INTEGER; q: INTEGER) BEGIN x=p[1] END use'
        state=execute(INITIALIZE+'use((a),change())',routine)
        self.assertEqual((state['A'][0],state['X']), (99,1))

    def test_reference_reads_later_argument_mutation(self):
        routine='ROUTINE change: INTEGER BEGIN a[1]=99 RETURN 1 END change\nROUTINE use(p: ARRAY OF INTEGER; q: INTEGER) BEGIN x=p[1] END use'
        state=execute(INITIALIZE+'use(a,change())',routine)
        self.assertEqual((state['A'][0],state['X']), (99,99))

    def test_whole_assignment_inside_private_copy(self):
        routine=FACTORY+'\nROUTINE use(p: ARRAY OF INTEGER; cell: INTEGER) BEGIN p=make() cell=99 x=p[2] END use'
        state=execute(INITIALIZE+'use((a),a[2])',routine)
        self.assertEqual((state['A'],state['X']), ([1,99,3],2))

    def test_private_cell_alias_survives_whole_assignment(self):
        routine=FACTORY+'\nROUTINE replace(p: ARRAY OF INTEGER; cell: INTEGER) BEGIN p=make() cell=99 END replace\nROUTINE outer(p: ARRAY OF INTEGER) BEGIN replace(p,p[2]) b=p END outer'
        state=execute(INITIALIZE+'outer((a))',routine)
        self.assertEqual((state['A'],state['B']), ([1,2,3],[1,99,3]))

    def test_copy_from_array_field(self):
        routine='ROUTINE use(p: ARRAY OF INTEGER) BEGIN p[1]=99 b=p END use'
        state=execute('box.values[1]=1 box.values[2]=2 box.values[3]=3 use((box.values))',routine,
                      types='TYPE box_t=STRUCTURE values: ARRAY[3] OF INTEGER ENDSTRUCTURE', declarations=DECLARATIONS+' box: box_t')
        self.assertEqual((state['BOX']['VALUES'][0],state['B'][0]), (1,99))

    def test_named_array_value_preserves_identity(self):
        routine='ROUTINE use(p: row_t) BEGIN p[1]=99 copied=p END use'
        state=execute('row[1]=1 row[2]=2 use((row))',routine, types='TYPE row_t=ARRAY[2] OF INTEGER', declarations=DECLARATIONS+' row,copied: row_t')
        self.assertEqual((state['ROW'],state['COPIED']), ([1,2],[99,2]))

    def test_named_subarray_value_is_detached(self):
        routine='ROUTINE use(p: row_t) BEGIN p[1]=99 x=p[1] END use'
        state=execute('plane[1,1]=1 plane[1,2]=2 use((plane[1]))',routine,types='TYPE row_t=ARRAY[2] OF INTEGER', declarations=DECLARATIONS+' plane: ARRAY[2] OF row_t')
        self.assertEqual((state['PLANE'][0],state['X']), ([1,2],99))

    def test_flat_multidimensional_copy(self):
        routine='ROUTINE use(p: ARRAY[*,*] OF INTEGER) BEGIN p[2,2]=99 x=p[2,2] END use'
        state=execute('grid[1,1]=1 grid[1,2]=2 grid[2,1]=3 grid[2,2]=4 use((grid))',routine, declarations=DECLARATIONS+' grid: ARRAY[2,2] OF INTEGER')
        self.assertEqual((state['GRID'],state['X']), ([[1,2],[3,4]],99))

    def test_flat_three_dimensional_copy(self):
        routine='ROUTINE use(p: ARRAY[*,*,*] OF INTEGER) BEGIN p[1,1,1]=99 x=p[1,1,1] END use'
        state=execute('cube[1,1,1]=7 use((cube))',routine,declarations=DECLARATIONS+' cube: ARRAY[1,1,1] OF INTEGER')
        self.assertEqual((state['CUBE'],state['X']), ([[[7]]],99))

    def test_nested_named_components_copy_recursively(self):
        routine='ROUTINE use(p: ARRAY[*,*] OF INTEGER) BEGIN p[1,2]=99 x=p[1,2] END use'
        state=execute('plane[1,1]=1 plane[1,2]=2 use((plane))',routine, types='TYPE row_t=ARRAY[2] OF INTEGER', declarations=DECLARATIONS+' plane: ARRAY[1] OF row_t')
        self.assertEqual((state['PLANE'],state['X']), ([[1,2]],99))

    def test_string_element_capacity_is_inherited_without_resizing(self):
        routine="ROUTINE use(p: ARRAY OF STRING) BEGIN p[1]='abcdef' x=STR_LEN(p[1]) END use"
        state=execute("words[1]='a' words[2]='' use((words))",routine,declarations=DECLARATIONS+' words: ARRAY[2] OF STRING[3]')
        self.assertEqual((state['WORDS'],state['X']), (['a',''],3))

    def test_narrow_integer_array_values(self):
        for kind,first,last in [('BYTE',0,255),('SHORT',-32768,32766)]:
            with self.subTest(kind=kind):
                routine=f'ROUTINE use(p: ARRAY OF {kind}) BEGIN p[1]={last} x=p[1] END use'
                state=execute(f'values[1]={first} values[2]={last} use((values))',routine,declarations=DECLARATIONS+f' values: ARRAY[2] OF {kind}')
                self.assertEqual((state['VALUES'],state['X']), ([first,last],last))

    def test_rounded_real_array_copy(self):
        routine='ROUTINE use(p: ARRAY OF REAL) BEGIN p[1]=p[1]+0.2 END use'
        self.assertEqual(execute('values[1]=0.1 use((values))',routine,declarations=DECLARATIONS+' values: ARRAY[1] OF REAL')['VALUES'], [.1])

    def test_record_array_value_copy_is_deep(self):
        routine='ROUTINE use(p: ARRAY OF item_t) BEGIN p[1].values[1]=99 x=p[1].values[1] END use'
        state=execute("records[1].id=1 records[1].values[1]=2 records[1].values[2]=3 use((records))",routine,
                      types='TYPE item_t=STRUCTURE id: INTEGER values: ARRAY[2] OF INTEGER ENDSTRUCTURE', declarations=DECLARATIONS+' records: ARRAY[1] OF item_t')
        self.assertEqual((state['RECORDS'][0]['VALUES'],state['X']), ([2,3],99))

    def test_joint_array_copy_preserves_axes(self):
        routine='ROUTINE use(p: ARRAY OF JOINTPOS2) BEGIN joints[1]=p[1] END use'
        program,_=compile_program('use((source))',routine,declarations=DECLARATIONS+' source,joints: ARRAY[1] OF JOINTPOS2')
        program._state.raw('SOURCE').values[0].values[:]=[.1,.2]
        self.assertEqual(program.run()['JOINTS'], [{'axes':[.1,.2]}])

    def test_explicit_wildcard_shape_is_preserved(self):
        routine='ROUTINE use(p: ARRAY OF INTEGER) BEGIN p[1]=99 x=ARRAY_LEN(p) END use'
        state=execute('values[1]=1 values[2]=2 use((values))',routine,declarations=DECLARATIONS+' values: ARRAY[*] OF INTEGER',shapes={'VALUES':[2]})
        self.assertEqual((state['VALUES'],state['X']), ([1,2],2))


class AggregateAccessTests(unittest.TestCase):
    def test_direct_function_result_index(self):
        state=execute('x=make()[2]')
        self.assertEqual((state['X'],state['N']), (2,1))

    def test_grouped_function_result_index(self):
        self.assertEqual(execute('x=(make())[2]')['X'], 2)

    def test_grouped_bare_function_result_index(self):
        self.assertEqual(execute('x=(make)[2]')['X'], 2)

    def test_grouped_storage_index_is_reference_when_actual(self):
        routine='ROUTINE use(p: INTEGER) BEGIN p=99 END use'
        self.assertEqual(execute(INITIALIZE+'use((a)[1])',routine)['A'][0], 99)

    def test_grouped_selected_actual_is_value(self):
        routine='ROUTINE use(p: INTEGER) BEGIN p=99 END use'
        self.assertEqual(execute(INITIALIZE+'use(((a)[1]))',routine)['A'][0], 1)

    def test_result_before_index_function(self):
        routine=FACTORY.replace('n=n+1','n=n+1 trace=trace+\'M\'')+"\nROUTINE indexer: INTEGER BEGIN trace=trace+'I' RETURN 2 END indexer"
        state=execute('x=make()[indexer()]',routine)
        self.assertEqual((state['X'],state['TRACE'],state['N']), (2,'MI',1))

    def test_bad_result_index_unwinds_function(self):
        program,_=compile_program('x=make()[0]')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['N'],program._state.local_frames,program._state.call_depth), (1,[],0))

    def test_reference_into_result_is_private(self):
        routine='ROUTINE copy: ARRAY OF INTEGER BEGIN RETURN a END copy\nROUTINE use(p: INTEGER) BEGIN p=99 x=p END use'
        state=execute(INITIALIZE+'use(copy()[1])',routine)
        self.assertEqual((state['A'][0],state['X']), (1,99))

    def test_array_result_record_field_access(self):
        routine='ROUTINE make: ARRAY OF item_t VAR values: ARRAY[1] OF item_t BEGIN values[1].id=42 RETURN values END make'
        self.assertEqual(execute('x=make()[1].id',routine,types='TYPE item_t=STRUCTURE id: INTEGER ENDSTRUCTURE')['X'],42)

    def test_named_subarray_result_access(self):
        routine='ROUTINE make: ARRAY OF row_t VAR values: ARRAY[1] OF row_t BEGIN values[1,1]=7 values[1,2]=8 RETURN values END make'
        self.assertEqual(execute('x=make()[1,2]',routine,types='TYPE row_t=ARRAY[2] OF INTEGER')['X'],8)

    def test_subarray_result_as_reference_actual_is_private(self):
        routine='ROUTINE make: ARRAY OF row_t VAR values: ARRAY[1] OF row_t BEGIN values[1,1]=7 values[1,2]=8 RETURN values END make\nROUTINE use(p: row_t) BEGIN p[1]=99 x=p[1] END use'
        self.assertEqual(execute('use(make()[1])',routine,types='TYPE row_t=ARRAY[2] OF INTEGER')['X'],99)

    def test_record_function_result_field_access(self):
        routine='ROUTINE make: item_t VAR value: item_t BEGIN value.id=42 RETURN value END make'
        self.assertEqual(execute('x=make().id',routine,types='TYPE item_t=STRUCTURE id: INTEGER ENDSTRUCTURE')['X'],42)

    def test_record_result_array_field_and_subscript(self):
        routine='ROUTINE make: item_t VAR value: item_t BEGIN value.values[1]=42 RETURN value END make'
        self.assertEqual(execute('x=(make()).values[1]',routine,types='TYPE item_t=STRUCTURE values: ARRAY[1] OF INTEGER ENDSTRUCTURE')['X'],42)

    def test_uninit_of_returned_initialized_scalar(self):
        self.assertFalse(execute('flag=UNINIT(make()[1])')['FLAG'])

    def test_conversion_output_into_result_stays_private(self):
        routine='ROUTINE copy: ARRAY OF INTEGER BEGIN RETURN a END copy'
        self.assertEqual(execute(INITIALIZE+"CNV_STR_INT('99',copy()[1])",routine)['A'],[1,2,3])


class ArrayFailureTests(unittest.TestCase):
    def test_partial_value_argument_uses_private_storage(self):
        routine='ROUTINE use(p: ARRAY OF INTEGER) BEGIN n=99 p[1]=9 END use'
        program,_=compile_program('a[1]=1 use((a))',routine)
        state=program.run()
        self.assertEqual((state['N'],state['A']),(99,[1,UNKNOWN,UNKNOWN]))
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))

    def test_bare_uninitialized_array_is_legal_output(self):
        routine='ROUTINE use(p: ARRAY OF INTEGER) BEGIN p[1]=9 END use'
        self.assertEqual(execute('use(a)',routine)['A'][0],9)

    def test_unknown_byte_value_copy_preserves_source_marker(self):
        routine='ROUTINE use(p: ARRAY OF BYTE) BEGIN n=99 p[1]=7 END use'
        state=execute('use((values))',routine,declarations=DECLARATIONS+' values: ARRAY[1] OF BYTE')
        self.assertEqual((state['N'],state['VALUES']),(99,[{'unknown_byte':True}]))

    def test_short_missing_marker_survives_private_copy(self):
        routine='ROUTINE use(p: ARRAY OF SHORT) BEGIN n=99 p[1]=7 END use'
        state=execute('values[1]=32767 use((values))',routine,declarations=DECLARATIONS+' values: ARRAY[1] OF SHORT')
        self.assertEqual((state['N'],state['VALUES']),(99,[UNKNOWN]))

    def test_partial_copy_allows_later_argument_without_aliasing(self):
        routine="ROUTINE change: INTEGER BEGIN trace='late' a[1]=7 RETURN 1 END change\nROUTINE use(p: ARRAY OF INTEGER; q: INTEGER) BEGIN n=99 flag=UNINIT(p[1]) END use"
        state=execute('use((a),change())',routine)
        self.assertEqual((state['TRACE'],state['N'],state['FLAG'],state['A'][0]),('late',99,True,7))

    def test_callee_error_does_not_copy_back(self):
        routine='ROUTINE use(p: ARRAY OF INTEGER) BEGIN p[1]=99 n=7 x=1 DIV 0 END use'
        program,_=compile_program(INITIALIZE+'use((a))',routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['A'],program.snapshot()['N']),([1,2,3],7))
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))

    def test_abort_does_not_copy_back(self):
        routine='ROUTINE use(p: ARRAY OF INTEGER) BEGIN p[1]=99 n=7 ABORT END use'
        program,_=compile_program(INITIALIZE+'use((a))',routine)
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual((program.snapshot()['A'],program.snapshot()['N']),([1,2,3],7))
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))

    def test_partial_result_can_be_passed_to_argument_callee(self):
        routine=FACTORY.replace('values[3]=3','')+'\nROUTINE use(p: ARRAY OF INTEGER) BEGIN x=99 flag=UNINIT(p[3]) END use'
        program,_=compile_program('use(make())',routine)
        state=program.run()
        self.assertEqual((state['N'],state['X'],state['FLAG']),(1,99,True))
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))

    def test_forwarded_string_capacity_mismatch_still_fails(self):
        routine='ROUTINE copy(p: ARRAY OF STRING): ARRAY OF STRING[3] BEGIN RETURN p END copy'
        program,_=compile_program("words[1]='a' output[1]='old' output=copy((words))",routine,
                                  declarations=DECLARATIONS+' words: ARRAY[1] OF STRING[4] output: ARRAY[1] OF STRING[3]')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['WORDS'],program.snapshot()['OUTPUT']),(['a'],['old']))

    def test_copy_depth_limit_cleans_up(self):
        routine='ROUTINE recurse(p: ARRAY OF INTEGER) BEGIN recurse((p)) END recurse'
        program,_=compile_program(INITIALIZE+'recurse((a))',routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'call-depth'): program.run()
        self.assertEqual((program.snapshot()['A'],program._state.local_frames,program._state.call_depth),([1,2,3],[],0))

    def test_wrong_formal_rank_rejected(self):
        routine='ROUTINE use(p: ARRAY[*,*] OF INTEGER) BEGIN END use'
        with self.assertRaises(TranslationError) as caught: compile_program('use((a))',routine)
        self.assertEqual(caught.exception.code,'E_TYPE')

    def test_array_numeric_element_coercion_remains_blocked(self):
        routine='ROUTINE use(p: ARRAY OF REAL) BEGIN END use'
        with self.assertRaises(TranslationError) as caught: compile_program('use((a))',routine)
        self.assertEqual(caught.exception.code,'E_TYPE')

    def test_nominal_type_mismatch_remains_blocked(self):
        routine='ROUTINE use(p: row_t) BEGIN END use'
        with self.assertRaises(TranslationError) as caught:
            compile_program('use((other))',routine,types='TYPE row_t=ARRAY[2] OF INTEGER other_t=ARRAY[2] OF INTEGER',declarations=DECLARATIONS+' other: other_t')
        self.assertEqual(caught.exception.code,'E_TYPE')

    def test_generic_value_parameter_does_not_erase_named_return_identity(self):
        routine='ROUTINE copy(p: ARRAY OF INTEGER): ARRAY OF INTEGER BEGIN RETURN p END copy'
        program,_=compile_program('row[1]=1 row[2]=2 output[1]=42 output=copy((row))',routine,
            types='TYPE row_t=ARRAY[2] OF INTEGER',declarations=DECLARATIONS+' row: row_t output: ARRAY[2] OF INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'anonymous outer storage'): program.run()
        self.assertEqual((program.snapshot()['ROW'],program.snapshot()['OUTPUT']),([1,2],[42,UNKNOWN]))
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))

    def test_array_result_cannot_be_boolean(self):
        with self.assertRaises(TranslationError) as caught: compile_program('IF make() THEN ENDIF')
        self.assertEqual(caught.exception.code,'E_TYPE')

    def test_array_result_cannot_be_arithmetic_operand(self):
        with self.assertRaises(TranslationError) as caught: compile_program('a=make()+a')
        self.assertEqual(caught.exception.code,'E_TYPE')

    def test_multidimensional_array_len_uses_first_dimension(self):
        routine='ROUTINE make: ARRAY OF row_t VAR values: ARRAY[1] OF row_t BEGIN values[1,1]=1 RETURN values END make'
        self.assertEqual(execute('x=ARRAY_LEN(make())',routine,types='TYPE row_t=ARRAY[1] OF INTEGER')['X'],1)

    def test_chained_result_indexes_share_existing_named_component_path(self):
        routine='ROUTINE make: ARRAY OF row_t VAR values: ARRAY[1] OF row_t BEGIN values[1,1]=1 RETURN values END make'
        self.assertEqual(execute('x=make()[1][1]',routine,types='TYPE row_t=ARRAY[1] OF INTEGER')['X'],1)

    def test_bare_receiver_root_remains_storage(self):
        with self.assertRaises(TranslationError): compile_program('x=make[1]')

    def test_scalar_function_result_cannot_be_indexed(self):
        with self.assertRaises(TranslationError): compile_program('x=number()[1]','ROUTINE number: INTEGER BEGIN RETURN 1 END number')

    def test_grouped_position_receiver_does_not_bypass_protection(self):
        routine='ROUTINE use(p: REAL) BEGIN p=99 END use'
        with self.assertRaises(TranslationError) as caught: compile_program('use((frame.normal).x)',routine,declarations=DECLARATIONS+' frame: POSITION')
        self.assertEqual(caught.exception.code,'E_POSITION_READ_ONLY_ARG')

    def test_config_subfield_receiver_group_keeps_value_passing(self):
        routine='ROUTINE use(p: INTEGER) BEGIN p=7 END use'
        state=execute('cfg.cfg_turn_no1=1 use((cfg).cfg_turn_no1)',routine,declarations=DECLARATIONS+' cfg: CONFIG')
        self.assertEqual(state['CFG']['CFG_TURN_NO1'],1)


class ArrayRuntimeAndReportTests(unittest.TestCase):
    def value(self,formal,actual):
        with rt._numeric_scope('pythonic'): return rt.value_argument(formal,actual,73)

    def test_runtime_actual_shape_and_identity_retained(self):
        source=initialized_host(('ARRAY',2,rt.INTEGER,'ROW_T'))
        copied=self.value(('ARRAY',None,rt.INTEGER),source)
        self.assertEqual(copied.spec,source.spec)
        self.assertIsNot(copied.raw(),source)
        copied.raw().set(1,9)
        self.assertEqual(source.raw(1),1)

    def test_runtime_wrong_concrete_shape_rejected(self):
        source=initialized_host(('ARRAY',2,rt.INTEGER))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'line 73'): self.value(('ARRAY',3,rt.INTEGER),source)

    def test_runtime_nonarray_value_rejected(self):
        with self.assertRaises(rt.KarelRuntimeError): self.value(('ARRAY',None,rt.INTEGER),1)

    def test_runtime_malformed_storage_rejected(self):
        source=initialized_host(('ARRAY',2,rt.INTEGER)); source.values.pop()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'shape and storage'): self.value(('ARRAY',None,rt.INTEGER),source)

    def test_runtime_string_corruption_rejected_without_truncation(self):
        source=initialized_host(('ARRAY',1,('STRING',3))); source.values[0]='abcd'
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'): self.value(('ARRAY',None,('STRING',None)),source)
        self.assertEqual(source.values[0],'abcd')

    def test_runtime_nonascii_leaf_rejected(self):
        source=initialized_host(('ARRAY',1,('STRING',3))); source.values[0]='caf\u00e9'
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ASCII'): self.value(('ARRAY',None,('STRING',None)),source)

    def test_runtime_config_range_rechecked(self):
        source=initialized_host(('ARRAY',1,('CONFIG',))); source.values[0].values['CFG_TURN_NO1']=8
        with self.assertRaisesRegex(rt.KarelRuntimeError,'-8..7'): self.value(('ARRAY',None,('CONFIG',)),source)

    def test_runtime_all_record_array_values_copy_independently(self):
        for kind in rt.DATA_RECORD_TYPES:
            with self.subTest(kind=kind):
                source=initialized_host(('ARRAY',1,(kind,)))
                copied=self.value(('ARRAY',None,(kind,)),source).raw()
                self.assertEqual(copied.snapshot(),source.snapshot())
                self.assertIsNot(copied.values[0],source.values[0])

    def test_runtime_position_orientation_copy_remains_protected(self):
        source=initialized_host(('ARRAY',1,('POSITION',)))
        copied=self.value(('ARRAY',None,('POSITION',)),source).raw()
        normal=copied.values[0].values['NORMAL']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'read-only'): rt.field_reference(normal,'X',73).set(9.)
        self.assertIsNot(normal,source.values[0].values['NORMAL'])

    def test_runtime_leaf_count_bound_rechecked(self):
        source=initialized_host(('ARRAY',1,rt.INTEGER)); source.spec=('ARRAY',32768,rt.INTEGER)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'32767'): self.value(('ARRAY',None,rt.INTEGER),source)

    def test_runtime_unknown_byte_and_short_marker_copies(self):
        for kind,missing in ((rt.BYTE,rt.UNKNOWN_BYTE),(rt.SHORT,32767)):
            with self.subTest(kind=kind):
                source=rt.Array(('ARRAY',1,kind));source.values[0]=missing
                value=self.value(('ARRAY',None,kind),source).raw()
                self.assertIs(value.values[0],rt.UNKNOWN_BYTE if kind==rt.BYTE else rt.UNINITIALIZED)
                self.assertIsNot(value,source)

    def test_report_records_value_copies_and_function_sites(self):
        routine=FACTORY+'\nROUTINE use(p: ARRAY OF INTEGER) BEGIN p[1]=99 END use'
        _,result=compile_program(INITIALIZE+'use((a)) use(make()) x=make()[1]',routine)
        self.assertEqual(len(result.report['array_value_arguments']),2)
        self.assertEqual(len(result.report['array_function_uses']),2)
        self.assertTrue(all(row['independent_writable_copy'] and row['evaluated_once'] for row in result.report['array_value_arguments']))
        self.assertEqual(result.report['routine_effects']['USE']['parameters'][0]['passing_modes'],['reference','value'])
        self.assertFalse(result.report['array_value_policy']['controller_validated'])

    def test_grouped_assignment_records_function_source(self):
        _,result=compile_program('a=(make())')
        self.assertEqual(result.report['array_result_assignments'][0]['routine'],'MAKE')
        self.assertEqual(len(result.report['array_function_uses']),1)

    def test_grouped_receivers_keep_reference_effects_but_grouped_actuals_copy(self):
        routine='ROUTINE inner(p: INTEGER) BEGIN p=99 END inner\nROUTINE by_ref(p: ARRAY OF INTEGER) BEGIN inner((p)[1]) END by_ref\nROUTINE by_value(p: ARRAY OF INTEGER) BEGIN inner(((p)[1])) END by_value'
        program,result=compile_program(INITIALIZE+'by_ref((a)) by_value((a))',routine)
        self.assertEqual(program.run()['A'],[1,2,3])
        self.assertEqual(result.report['routine_effects']['BY_REF']['potential_parameter_writes'],['P'])
        self.assertEqual(result.report['routine_effects']['BY_VALUE']['potential_parameter_writes'],[])


if __name__ == '__main__': unittest.main()
