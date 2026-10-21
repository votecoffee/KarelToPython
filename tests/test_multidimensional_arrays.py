"""Fixed multidimensional arrays, captured storage and rank-specific formals."""
import unittest

from karel2py import translate
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


DECLARATIONS = '''
a,z: ARRAY[2,3] OF INTEGER
cube: ARRAY[2,2,3] OF INTEGER
flags: ARRAY[2,2] OF BOOLEAN
words: ARRAY[2,2] OF STRING[3]
measures: ARRAY[2,2] OF REAL
row,column,result,seen,total: INTEGER
flag: BOOLEAN
measurement: REAL
'''
UNINIT = {'uninitialized': True}


def compile_program(body='', routines='', declarations=DECLARATIONS, types='', constants='', *, _translator=translate):
    source = f'PROGRAM T\n{constants}\n{types}\nVAR\n{declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result = _translator(source, filename='multidimensional.kl')
    namespace = {'__name__': 'array_tests'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body='', routines='', **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


class ElementTests(unittest.TestCase):
    def test_two_dimensional_elements_have_distinct_storage(self):
        state = execute('a[1,1] = 11 a[1,3] = 13 a[2,1] = 21 a[2,3] = 23 result = a[2,1]')
        self.assertEqual(state['A'], [[11, UNINIT, 13], [21, UNINIT, 23]])
        self.assertEqual(state['RESULT'], 21)

    def test_three_dimensional_elements_have_distinct_storage(self):
        state = execute('cube[1,1,1] = 111 cube[1,2,3] = 123 cube[2,1,3] = 213 cube[2,2,1] = 221')
        self.assertEqual(state['CUBE'], [[[111, UNINIT, UNINIT], [UNINIT, UNINIT, 123]],
                                        [[UNINIT, UNINIT, 213], [221, UNINIT, UNINIT]]])

    def test_each_dimension_uses_constant_expressions(self):
        state = execute('a[2,3] = 7', declarations='a: ARRAY[N,N+1] OF INTEGER', constants='CONST N = 2')
        self.assertEqual(state['A'], [[UNINIT]*3, [UNINIT, UNINIT, 7]])

    def test_expression_subscripts_and_case_insensitive_access(self):
        state = execute('row = 1 column = 2 A[row+1,column+1] = 9 result = a[2,3]')
        self.assertEqual(state['RESULT'], 9)

    def test_uninitialized_elements_remain_independent(self):
        state = execute('a[1,2] = 7 flag = UNINIT(a[1,1])')
        self.assertTrue(state['FLAG'])
        self.assertEqual(state['A'][0], [UNINIT, 7, UNINIT])

    def test_reading_an_uninitialized_element_fails_with_source_line(self):
        p, _ = compile_program('result = a[2,3]')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized') as caught: p.run()
        self.assertIsNotNone(caught.exception.line)

    def test_boolean_elements_are_checked(self):
        state = execute('flags[1,2] = TRUE flags[2,1] = FALSE flag = flags[1,2]')
        self.assertEqual(state['FLAGS'], [[UNINIT, True], [False, UNINIT]])
        self.assertTrue(state['FLAG'])

    def test_string_element_assignment_truncates_to_physical_capacity(self):
        state = execute("words[2,1] = 'abcdef' result = STR_LEN(words[2,1])")
        self.assertEqual((state['WORDS'][1][0], state['RESULT']), ('abc', 3))

    def test_real_elements_use_existing_exactness_checks(self):
        state = execute('measures[1,2] = 2.5 measures[2,1] = 3 measurement = measures[1,2] / 2')
        self.assertEqual((state['MEASURES'], state['MEASUREMENT']), ([[UNINIT, 2.5], [3.0, UNINIT]], 1.25))

    def test_pythonic_rounded_real_result_updates_element(self):
        p, _ = compile_program('measures[2,2] = 7.0 measures[2,2] = 1.0 / 3.0')
        self.assertEqual(p.run()['MEASURES'][1][1], 1/3)

    def test_nested_for_fills_entire_rectangle(self):
        state = execute('FOR row = 1 TO 2 DO FOR column = 1 TO 3 DO a[row,column] = row * 10 + column ENDFOR ENDFOR')
        self.assertEqual(state['A'], [[11, 12, 13], [21, 22, 23]])
        self.assertEqual((state['ROW'], state['COLUMN']), (UNINIT, UNINIT))

    def test_labelled_engine_uses_same_array_operations(self):
        state = execute('GOTO fill fill:: a[2,3] = 7 result = a[2,3]')
        self.assertEqual(state['RESULT'], 7)

    def test_program_instances_do_not_share_array_storage(self):
        p, _ = compile_program('a[1,1] = 7')
        p.run()
        self.assertEqual(type(p)()._state.snapshot()['A'], [[UNINIT]*3, [UNINIT]*3])

    def test_report_records_rank_and_capacity_policy(self):
        _, result = compile_program('a[1,2] = 7')
        self.assertIn('multidimensional scalar ARRAY', result.report['features'])
        self.assertEqual(result.report['array_policy']['ranks'], [1, 2, 3])
        self.assertEqual(result.report['array_policy']['max_scalar_elements'], 32767)
        self.assertFalse(result.report['array_policy']['controller_validated'])


class ReferenceTests(unittest.TestCase):
    def test_same_rank_formal_accepts_different_shapes(self):
        routine = 'ROUTINE put(p: ARRAY[*,*] OF INTEGER) BEGIN p[2,2] = 7 END put'
        state = execute('put(a) put(other)', routine, declarations=DECLARATIONS + 'other: ARRAY[3,2] OF INTEGER')
        self.assertEqual((state['A'][1][1], state['OTHER'][1][1]), (7, 7))

    def test_three_dimensional_formal(self):
        state = execute('put(cube)', 'ROUTINE put(p: ARRAY[*,*,*] OF INTEGER) BEGIN p[2,1,3] = 9 END put')
        self.assertEqual(state['CUBE'][1][0][2], 9)

    def test_explicit_one_dimensional_wildcard_matches_old_form(self):
        state = execute('put(a)', 'ROUTINE put(p: ARRAY[*] OF INTEGER) BEGIN p[2] = 9 END put', declarations='a: ARRAY[2] OF INTEGER')
        self.assertEqual(state['A'], [UNINIT, 9])

    def test_nested_forwarding_keeps_storage_and_shape(self):
        routines = ('ROUTINE put(p: ARRAY[*,*] OF INTEGER) BEGIN p[2,3] = 9 END put '
                    'ROUTINE forward(p: ARRAY[*,*] OF INTEGER) BEGIN put(p) END forward')
        self.assertEqual(execute('forward(a)', routines)['A'][1][2], 9)

    def test_whole_array_and_scalar_element_alias_immediately(self):
        routine = 'ROUTINE alias(p: ARRAY[*,*] OF INTEGER; q: INTEGER) BEGIN p[2,3] = 7 seen = q q = 9 END alias'
        state = execute('a[2,3] = 1 alias(a,a[2,3])', routine)
        self.assertEqual((state['SEEN'], state['A'][1][2]), (7, 9))

    def test_two_whole_array_formals_can_alias(self):
        routine = 'ROUTINE alias(p,q: ARRAY[*,*] OF INTEGER) BEGIN p[2,3] = 7 q[1,1] = p[2,3] END alias'
        self.assertEqual(execute('alias(a,a)', routine)['A'], [[7, UNINIT, UNINIT], [UNINIT, UNINIT, 7]])

    def test_all_element_indexes_captured_before_callee_writes(self):
        routine = 'ROUTINE put(p: INTEGER) BEGIN row = 2 column = 3 p = 7 END put'
        state = execute('row = 1 column = 2 put(a[row,column])', routine)
        self.assertEqual(state['A'], [[UNINIT, 7, UNINIT], [UNINIT]*3])

    def test_parenthesized_element_is_independent_value(self):
        routine = 'ROUTINE put(p: INTEGER) BEGIN p = 7 END put'
        self.assertEqual(execute('a[2,3] = 1 put((a[2,3]))', routine)['A'][1][2], 1)

    def test_integer_element_to_real_is_independent_value(self):
        routine = 'ROUTINE put(p: REAL) BEGIN p = p + 0.5 measurement = p END put'
        state = execute('a[2,3] = 3 put(a[2,3])', routine)
        self.assertEqual((state['A'][1][2], state['MEASUREMENT']), (3, 3.5))

    def test_string_formal_inherits_element_capacity(self):
        routine = "ROUTINE put(p: STRING) BEGIN p = 'abcdef' END put"
        self.assertEqual(execute('put(words[1,2])', routine)['WORDS'][0][1], 'abc')

    def test_string_array_formal_inherits_shape_and_capacity(self):
        routine = "ROUTINE put(p: ARRAY[*,*] OF STRING) BEGIN p[2,2] = 'abcdef' END put"
        state = execute('put(words) put(wide)', routine, declarations=DECLARATIONS + 'wide: ARRAY[2,2] OF STRING[5]')
        self.assertEqual((state['WORDS'][1][1], state['WIDE'][1][1]), ('abc', 'abcde'))

    def test_real_and_boolean_array_formals(self):
        routines = ('ROUTINE put(p: ARRAY[*,*] OF REAL; q: ARRAY[*,*] OF BOOLEAN) '
                    'BEGIN p[2,1] = 1.25 q[1,2] = TRUE END put')
        state = execute('put(measures,flags)', routines)
        self.assertEqual((state['MEASURES'][1][0], state['FLAGS'][0][1]), (1.25, True))

    def test_fresh_local_array_lifetime_and_forwarding(self):
        routines = ('ROUTINE put(p: ARRAY[*,*] OF INTEGER) BEGIN flag = UNINIT(p[1,1]) p[1,1] = 7 END put '
                    'ROUTINE outer VAR local_table: ARRAY[2,3] OF INTEGER BEGIN put(local_table) result = local_table[1,1] END outer')
        p, _ = compile_program('outer outer', routines)
        state = p.run()
        self.assertEqual((state['FLAG'], state['RESULT']), (True, 7))
        self.assertEqual((p._state.local_frames, p._state.call_depth), ([], 0))

    def test_helper_calls_in_local_loops_and_early_search_return(self):
        routines = ('ROUTINE double_value(p: INTEGER): INTEGER BEGIN RETURN p * 2 END double_value '
                    'ROUTINE fill(p: ARRAY[*,*] OF INTEGER) VAR r,c: INTEGER BEGIN '
                    'FOR r = 1 TO 2 DO FOR c = 1 TO 3 DO p[r,c] = double_value((c)) ENDFOR ENDFOR END fill '
                    'ROUTINE search(p: ARRAY[*,*] OF INTEGER): INTEGER VAR r,c: INTEGER BEGIN '
                    'FOR r = 1 TO 2 DO FOR c = 1 TO 3 DO IF p[r,c] = 0 THEN RETURN r * 10 + c ENDIF ENDFOR ENDFOR RETURN 0 END search')
        state = execute('fill(a) a[2,2] = 0 result = search(a)', routines)
        self.assertEqual((state['A'], state['RESULT']), ([[2, 4, 6], [2, 0, 6]], 22))

    def test_reference_write_survives_error_and_frame_unwinds(self):
        routine = 'ROUTINE fail(p: ARRAY[*,*] OF INTEGER) BEGIN p[2,3] = 7 result = 1 DIV 0 END fail'
        p, _ = compile_program('fail(a)', routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'zero'): p.run()
        self.assertEqual(p._state.snapshot()['A'][1][2], 7)
        self.assertEqual((p._state.local_frames, p._state.call_depth), ([], 0))

    def test_report_keeps_formal_rank_and_passing_modes(self):
        _, result = compile_program('put(a)', 'ROUTINE put(p: ARRAY[*,*] OF INTEGER) BEGIN END put')
        parameter = result.report['routine_effects']['PUT']['parameters'][0]
        self.assertEqual(parameter['type_spec'], ('ARRAY', (None, None), ('INTEGER',)))
        self.assertEqual(parameter['passing_modes'], ['reference', 'value'])


class CopyTests(unittest.TestCase):
    def test_whole_copy_is_independent_and_can_copy_uninitialized_elements(self):
        state = execute('a[1,2] = 7 z = a a[1,2] = 9')
        self.assertEqual((state['Z'][0][1], state['A'][0][1]), (7, 9))
        self.assertEqual(state['Z'][1], [UNINIT]*3)

    def test_three_dimensional_whole_copy(self):
        state = execute('cube[2,1,3] = 7 copy = cube cube[2,1,3] = 9', declarations=DECLARATIONS + 'copy: ARRAY[2,2,3] OF INTEGER')
        self.assertEqual(state['COPY'][1][0][2], 7)

    def test_copy_into_formal_preserves_captured_element_reference(self):
        routine = ('ROUTINE copy(p,q: ARRAY[*,*] OF INTEGER; element: INTEGER) '
                   'BEGIN p = q seen = element element = 99 END copy')
        state = execute('a[2,3] = 1 z[2,3] = 7 copy(a,z,a[2,3])', routine)
        self.assertEqual((state['SEEN'], state['A'][1][2], state['Z'][1][2]), (7, 99, 7))

    def test_self_copy_preserves_captured_reference(self):
        routine = 'ROUTINE copy(p: ARRAY[*,*] OF INTEGER; element: INTEGER) BEGIN p = p element = 99 END copy'
        self.assertEqual(execute('a[2,3] = 1 copy(a,a[2,3])', routine)['A'][1][2], 99)

    def test_shape_mismatch_through_formals_rejects_before_destination_mutation(self):
        routine = 'ROUTINE copy(p,q: ARRAY[*,*] OF INTEGER) BEGIN p = q END copy'
        p, _ = compile_program('a[1,1] = 7 copy(a,other)', routine, declarations=DECLARATIONS + 'other: ARRAY[3,2] OF INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'identical type and size'): p.run()
        self.assertEqual(p._state.snapshot()['A'], [[7, UNINIT, UNINIT], [UNINIT]*3])
        self.assertEqual(p._state.local_frames, [])

    def test_string_capacity_mismatch_through_formals_rejects_before_mutation(self):
        routine = 'ROUTINE copy(p,q: ARRAY[*,*] OF STRING) BEGIN p = q END copy'
        p, _ = compile_program("words[2,2] = 'old' copy(words,wide)", routine, declarations=DECLARATIONS + 'wide: ARRAY[2,2] OF STRING[4]')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'identical type and size'): p.run()
        self.assertEqual(p._state.snapshot()['WORDS'][1][1], 'old')


class StructureFieldTests(unittest.TestCase):
    TYPES = 'TYPE record_t = STRUCTURE table: ARRAY[2,2] OF INTEGER ENDSTRUCTURE'

    def test_multidimensional_field_paths_and_array_parameter(self):
        routine = 'ROUTINE put(p: ARRAY[*,*] OF INTEGER) BEGIN p[2,1] = 7 END put'
        state = execute('put(item.table)', routine, types=self.TYPES, declarations='item: record_t')
        self.assertEqual(state['ITEM'], {'TABLE': [[UNINIT, UNINIT], [7, UNINIT]]})

    def test_whole_structure_copy_preserves_array_element_alias(self):
        routine = 'ROUTINE copy(p,q: record_t; element: INTEGER) BEGIN p = q element = 99 END copy'
        state = execute('src.table[1,1] = 1 src.table[1,2] = 2 src.table[2,1] = 3 src.table[2,2] = 4 copy(dst,src,dst.table[2,1])',
                        routine, types=self.TYPES, declarations='src,dst: record_t')
        self.assertEqual(state['DST']['TABLE'], [[1, 2], [99, 4]])
        self.assertEqual(state['SRC']['TABLE'], [[1, 2], [3, 4]])

    def test_partial_structure_copy_remains_blocked_before_mutation(self):
        p, _ = compile_program('dst.table[1,1] = 7 src.table[1,1] = 1 dst = src', types=self.TYPES, declarations='src,dst: record_t')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized fields'): p.run()
        self.assertEqual(p._state.snapshot()['DST']['TABLE'][0][0], 7)


class BoundaryTests(unittest.TestCase):
    def rejected(self, body='', routines='', code='E_ARRAY_RANK', **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, routines, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_each_dimension_bounds_checked_without_mutation(self):
        for subscripts in ('0,1', '3,1', '1,0', '1,4', '-1,1', '1,-1'):
            with self.subTest(subscripts=subscripts):
                p, _ = compile_program(f'a[1,1] = 7 a[{subscripts}] = 9')
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'outside'): p.run()
                self.assertEqual(p._state.snapshot()['A'], [[7, UNINIT, UNINIT], [UNINIT]*3])

    def test_all_three_dimensions_checked(self):
        for subscripts in ('3,1,1', '1,3,1', '1,1,4'):
            with self.subTest(subscripts=subscripts):
                p, _ = compile_program(f'cube[{subscripts}] = 9')
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'outside'): p.run()

    def test_uninitialized_index_rejected(self):
        p, _ = compile_program('a[row,1] = 7')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): p.run()

    def test_partial_subarray_access_rejected_in_every_context(self):
        for body in ('result = a[1]', 'a[1] = 7', 'flag = UNINIT(a[1])', 'put(a[1])'):
            with self.subTest(body=body): self.rejected(body, 'ROUTINE put(p: ARRAY OF INTEGER) BEGIN END put')

    def test_too_many_subscripts_and_chained_subscripts_rejected(self):
        for body in ('a[1,1,1] = 7', 'a[1][2] = 7', 'a[1,2][1] = 7'):
            with self.subTest(body=body): self.rejected(body, code='E_TYPE' if body == 'a[1,2][1] = 7' else 'E_ARRAY_RANK')

    def test_wrong_index_type_rejected(self):
        for body in ('a[TRUE,1] = 7', 'a[1,1.5] = 7', "a[1,'x'] = 7"):
            with self.subTest(body=body): self.rejected(body, code='E_TYPE')

    def test_wrong_element_assignment_type_rejected(self):
        for body in ('a[1,1] = TRUE', 'flags[1,1] = 1', 'words[1,1] = 7'):
            with self.subTest(body=body): self.rejected(body, code='E_TYPE')

    def test_fixed_shape_copy_mismatch_even_with_same_total_elements(self):
        self.rejected('a = other', code='E_TYPE', declarations=DECLARATIONS + 'other: ARRAY[3,2] OF INTEGER')

    def test_formal_rank_must_match_actual_rank(self):
        for spec, argument in [('ARRAY OF INTEGER', 'a'), ('ARRAY[*,*] OF INTEGER', 'cube'), ('ARRAY[*,*,*] OF INTEGER', 'a')]:
            with self.subTest(spec=spec): self.rejected(f'put({argument})', f'ROUTINE put(p: {spec}) BEGIN END put', code='E_TYPE')

    def test_formal_element_type_must_match(self):
        self.rejected('put(flags)', 'ROUTINE put(p: ARRAY[*,*] OF INTEGER) BEGIN END put', code='E_TYPE')

    def test_fixed_formal_dimensions_remain_blocked(self):
        for spec in ('ARRAY[2,3] OF INTEGER', 'ARRAY[*,3] OF INTEGER', 'ARRAY[2,*] OF INTEGER'):
            with self.subTest(spec=spec): self.rejected(routines=f'ROUTINE put(p: {spec}) BEGIN END put', code='E_PARAMETERS')

    def test_parenthesized_whole_array_value_remains_blocked(self):
        self.rejected('put((a))', 'ROUTINE put(p: ARRAY[*,*] OF INTEGER) BEGIN END put', code='E_ARRAY_VALUE', _translator=legacy_translate)

    def test_aggregate_uninit_remains_blocked(self):
        self.rejected('flag = UNINIT(a)', code='E_TYPE')

    def test_multidimensional_array_len_remains_blocked(self):
        self.rejected('result = ARRAY_LEN(a)', code='E_ARRAY_LEN', _translator=legacy_translate)
        self.rejected('put(a)', 'ROUTINE put(p: ARRAY[*,*] OF INTEGER) BEGIN result = ARRAY_LEN(p) END put', code='E_ARRAY_LEN', _translator=legacy_translate)

    def test_rank_above_three_rejected(self):
        self.rejected(declarations='a: ARRAY[1,1,1,1] OF INTEGER')
        self.rejected(routines='ROUTINE put(p: ARRAY[*,*,*,*] OF INTEGER) BEGIN END put')

    def test_invalid_dimension_sizes_rejected(self):
        for spec in ('ARRAY[0,2] OF INTEGER', 'ARRAY[2,32768] OF INTEGER', 'ARRAY[2,TRUE] OF INTEGER', 'ARRAY[2,1.5] OF INTEGER'):
            with self.subTest(spec=spec): self.rejected(declarations='a: ' + spec, code='E_SIZE')

    def test_total_allocation_guard_rejected_before_runtime(self):
        self.rejected(declarations='a: ARRAY[2,16384] OF INTEGER', code='E_ARRAY_CAPACITY')

    def test_variable_sized_declarations_remain_blocked(self):
        for spec in ('ARRAY[*,*] OF INTEGER', 'ARRAY[2,*] OF INTEGER'):
            with self.subTest(spec=spec): self.rejected(declarations='a: ' + spec, code='E_ARRAY_SIZE')

    def test_nested_type_syntax_and_unknown_structure_type_remain_blocked(self):
        self.rejected(declarations='a: ARRAY[2] OF ARRAY[3] OF INTEGER', code='E_TYPE')
        self.rejected(types='TYPE item_t = STRUCTURE n: INTEGER ENDSTRUCTURE', declarations='a: ARRAY[2,2] OF missing_type', code='E_TYPE')

    def test_routine_calls_in_multi_indexes_remain_blocked(self):
        routine = 'ROUTINE next_index: INTEGER BEGIN RETURN 1 END next_index'
        for body in ('result = a[next_index(),1]', 'a[1,next_index()] = 7', 'flag = UNINIT(a[next_index(),1])'):
            with self.subTest(body=body): self.rejected(body, routine, code='E_EVALUATION_ORDER', _translator=legacy_translate)

    def test_effectful_indexed_result_remains_blocked(self):
        self.rejected('a[row,column] = update()', 'ROUTINE update: INTEGER BEGIN row = 2 RETURN 7 END update', code='E_EVALUATION_ORDER', _translator=legacy_translate)


class RuntimeGuards(unittest.TestCase):
    def test_direct_runtime_rank_type_and_bounds_guards(self):
        value = rt.Array(('ARRAY', (2, 3), rt.INTEGER))
        for index in (1, (1,), (1, 1, 1), (True, 1), (1, 4)):
            with self.subTest(index=index), self.assertRaises(rt.KarelRuntimeError): rt.index_reference(value, index, 3)

    def test_direct_runtime_allocation_guards(self):
        for shape in ((2, 16384), (0, 2), (2, None), (1, 1, 1, 1), (True, 2)):
            with self.subTest(shape=shape), self.assertRaises(rt.KarelRuntimeError): rt.Array(('ARRAY', shape, rt.INTEGER))

    def test_direct_runtime_formal_rank_guard(self):
        self.assertFalse(rt.parameter_accepts(('ARRAY', None, rt.INTEGER), ('ARRAY', (2, 3), rt.INTEGER)))
        self.assertFalse(rt.parameter_accepts(('ARRAY', (None, None), rt.INTEGER), ('ARRAY', (2, 3, 1), rt.INTEGER)))

    def test_direct_runtime_array_len_guard(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'dimension-count'):
            rt.builtin('ARRAY_LEN', [rt.Array(('ARRAY', (2, 3), rt.INTEGER))], 3)


if __name__ == '__main__': unittest.main()
