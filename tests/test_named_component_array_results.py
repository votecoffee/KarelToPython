"""Named subarrays in unsized results: exact components and owned offline copies."""
import ast
import json
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.test_structure_routines import initialized_host


TYPES = '''TYPE row_t=ARRAY[2] OF INTEGER
other_row_t=ARRAY[2] OF INTEGER
plane_t=ARRAY[2] OF row_t
flat_plane_t=ARRAY[2,2] OF INTEGER'''
INIT = 'p[1,1]=1 p[1,2]=2 p[2,1]=3 p[2,2]=4'
FACTORY = f'ROUTINE make: ARRAY OF row_t VAR p: ARRAY[2] OF row_t BEGIN {INIT} RETURN p END make'
MATRIX = [[1, 2], [3, 4]]


def compile_program(body='a=make()', *, types=TYPES, declarations='a,b: ARRAY[2] OF row_t n: INTEGER',
                    routines=FACTORY, shapes=None):
    result = translate(f'PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T',
                       filename='named_component_results.kl', array_shapes=shapes)
    ast.parse(result.python_source, feature_version=(3, 11))
    json.dumps(result.report)
    namespace = {'__name__': 'named_component_array_result_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(*args, **kwargs):
    return compile_program(*args, **kwargs)[0].run()


class NamedComponentArrayReturnTests(unittest.TestCase):
    def test_local_two_dimensional_result(self):
        self.assertEqual(execute()['A'], MATRIX)

    def test_named_row_identity_is_retained(self):
        program, result = compile_program()
        program.run()
        source = program._state.raw('A')
        self.assertEqual(source.values[0].spec, ('ARRAY', 2, rt.INTEGER, 'ROW_T'))
        self.assertIsNone(rt.array_identity(source.spec))
        row = result.report['array_returns'][0]
        self.assertEqual((row['logical_rank'], row['element_spec'][-1]), (2, 'ROW_T'))
        self.assertIn('named-component ARRAY function result', result.report['features'])

    def test_global_storage_and_grouped_return_are_independent(self):
        routine = 'ROUTINE copy: ARRAY OF row_t BEGIN RETURN ((a)) END copy'
        state = execute(INIT.replace('p[', 'a[') + ' b=copy() a[1,1]=99', routines=routine)
        self.assertEqual(state['B'], MATRIX)

    def test_unsized_formal_retains_each_concrete_outer_length(self):
        routine = 'ROUTINE copy(p: ARRAY OF row_t): ARRAY OF row_t BEGIN RETURN p END copy'
        state = execute('a[1,1]=1 a[1,2]=2 b[1]=a[1] b[2]=a[1] c=copy(a) d=copy(b)',
                        routines=routine, declarations='a,c: ARRAY[1] OF row_t b,d: ARRAY[2] OF row_t')
        self.assertEqual((state['C'], state['D']), ([[1, 2]], [[1, 2], [1, 2]]))

    def test_three_dimensions_with_two_named_boundaries(self):
        routine = 'ROUTINE copy(p: ARRAY OF plane_t): ARRAY OF plane_t BEGIN RETURN p END copy'
        program, result = compile_program('b=copy(a) a[1,1,1]=99', routines=routine,
                                          declarations='a,b: ARRAY[1] OF plane_t')
        source = program._state.raw('A')
        source.values[0] = initialized_host(source.spec[2])
        state = program.run()
        self.assertEqual(state['B'], [[[1, 1], [1, 1]]])
        self.assertEqual(result.report['array_returns'][0]['logical_rank'], 3)
        self.assertIsNot(source.values[0].values[0], program._state.raw('B').values[0].values[0])

    def test_three_dimensions_with_named_flat_plane(self):
        routine = 'ROUTINE copy(p: ARRAY OF flat_plane_t): ARRAY OF flat_plane_t BEGIN RETURN p END copy'
        state = execute('a[1,1,1]=1 a[1,1,2]=2 a[1,2,1]=3 a[1,2,2]=4 b=copy(a)',
                        routines=routine, declarations='a,b: ARRAY[1] OF flat_plane_t')
        self.assertEqual(state['B'], [MATRIX])

    def test_structure_field_source_and_destination(self):
        types = TYPES + '\nbox_t=STRUCTURE data: ARRAY[2] OF row_t ENDSTRUCTURE'
        routine = 'ROUTINE copy: ARRAY OF row_t BEGIN RETURN first.data END copy'
        state = execute(INIT.replace('p[', 'first.data[') + ' second.data=copy() first.data[1,1]=99',
                        types=types, declarations='first,second: box_t', routines=routine)
        self.assertEqual(state['SECOND']['DATA'], MATRIX)

    def test_anonymous_array_field_selected_inside_named_array(self):
        types = TYPES + '\nbox_t=STRUCTURE data: ARRAY[2] OF row_t ENDSTRUCTURE\nboxes_t=ARRAY[1] OF box_t'
        routine = 'ROUTINE copy: ARRAY OF row_t BEGIN RETURN boxes[1].data END copy'
        state = execute(INIT.replace('p[', 'boxes[1].data[') + ' a=copy()', types=types,
                        declarations='boxes: boxes_t a: ARRAY[2] OF row_t', routines=routine)
        self.assertEqual(state['A'], MATRIX)

    def test_stable_scalar_reference_survives_destination_replacement(self):
        routines = FACTORY + '\nROUTINE replace(p: ARRAY OF row_t; captured: INTEGER) BEGIN p=make() captured=99 END replace'
        self.assertEqual(execute('replace(a,a[2,1])', routines=routines)['A'], [[1, 2], [99, 4]])

    def test_stable_named_row_reference_survives_destination_replacement(self):
        routines = FACTORY + '\nROUTINE replace(p: ARRAY OF row_t; captured: row_t) BEGIN p=make() captured[2]=99 END replace'
        self.assertEqual(execute('replace(a,a[1])', routines=routines)['A'], [[1, 99], [3, 4]])

    def test_same_source_destination_is_copied_before_assignment(self):
        routines = FACTORY + '\nROUTINE copy(p: ARRAY OF row_t): ARRAY OF row_t BEGIN RETURN p END copy'
        self.assertEqual(execute('a=make() a=copy(a)', routines=routines)['A'], MATRIX)

    def test_explicit_outer_shape_context(self):
        self.assertEqual(execute(declarations='a: ARRAY[*] OF row_t', shapes={'a': [2]})['A'], MATRIX)

    def test_recursive_staging_before_return_and_cleanup(self):
        routines = FACTORY + '\nROUTINE recurse(k: INTEGER): ARRAY OF row_t VAR p: ARRAY[2] OF row_t BEGIN IF k=0 THEN p=make() ELSE p=recurse(k-1) p[1,1]=p[1,1]+1 ENDIF RETURN p END recurse'
        program, _ = compile_program('a=recurse(4)', routines=routines)
        self.assertEqual(program.run()['A'], [[5, 2], [3, 4]])
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_labelled_and_structured_execution_match(self):
        outcomes = []
        for marker in ('', 'unused:: '):
            program, _ = compile_program(marker + 'a=make() SELECT a[2,1] OF CASE(3): n=7 ELSE: n=8 ENDSELECT')
            outcomes.append((program.run(), program._state.steps))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_unknown_leaf_preserves_destination_and_prior_effects(self):
        routine = 'ROUTINE fail: ARRAY OF row_t VAR p: ARRAY[2] OF row_t BEGIN n=7 p[1,1]=1 RETURN p END fail'
        program, _ = compile_program(INIT.replace('p[', 'a[') + ' a=fail()', routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized') as caught:
            program.run()
        self.assertIsNotNone(caught.exception.line)
        self.assertEqual(program._state.snapshot(), {'A': MATRIX, 'B': [[{'uninitialized': True}]*2]*2, 'N': 7})
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_wrong_outer_length_preserves_initialized_destination(self):
        routine = 'ROUTINE make: ARRAY OF row_t VAR p: ARRAY[1] OF row_t BEGIN p[1,1]=8 p[1,2]=9 RETURN p END make'
        program, _ = compile_program(INIT.replace('p[', 'a[') + ' a=make()', routines=routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program._state.snapshot()['A'], MATRIX)
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_named_outer_actual_cannot_escape_through_generic_formal(self):
        routine = 'ROUTINE copy(p: ARRAY OF row_t): ARRAY OF row_t BEGIN RETURN p END copy'
        program, _ = compile_program('a=copy(b)', declarations='a: ARRAY[2] OF row_t b: plane_t', routines=routine)
        program._state.values['B'] = initialized_host(program._state.raw('B').spec)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'anonymous outer'): program.run()
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_translated_terminal_types_retain_checked_copies(self):
        for spelling in ('INTEGER', 'BOOLEAN', 'REAL', 'BYTE', 'SHORT', *rt.DATA_RECORD_TYPES,
                         *(f'JOINTPOS{n}' for n in range(1, 10)), 'item_t'):
            with self.subTest(spelling=spelling):
                types = 'TYPE item_t=STRUCTURE label: STRING[3] ENDSTRUCTURE\nrow_t=ARRAY[2] OF ' + spelling
                routine = 'ROUTINE copy(p: ARRAY OF row_t): ARRAY OF row_t BEGIN RETURN p END copy'
                program, _ = compile_program('b=copy(a)', types=types,
                                              declarations='a,b: ARRAY[1] OF row_t', routines=routine)
                program._state.values['A'] = initialized_host(program._state.raw('A').spec)
                before = program._state.snapshot()['A']
                self.assertEqual(program.run()['B'], before)
                self.assertIsNot(program._state.raw('A').values[0], program._state.raw('B').values[0])

    def test_nested_unknown_byte_preserves_destination_and_cleans_frames(self):
        types = 'TYPE row_t=ARRAY[2] OF BYTE'
        routine = 'ROUTINE fail: ARRAY OF row_t VAR p: ARRAY[1] OF row_t BEGIN n=7 p[1,1]=1 RETURN p END fail'
        program, _ = compile_program('a[1,1]=8 a[1,2]=9 a=fail()', types=types,
                                      declarations='a: ARRAY[1] OF row_t n: INTEGER', routines=routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program._state.snapshot(), {'A': [[8, 9]], 'N': 7})
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_abort_during_factory_preserves_destination_and_cleans_frames(self):
        routine = 'ROUTINE fail: ARRAY OF row_t VAR p: ARRAY[2] OF row_t BEGIN n=7 ABORT RETURN p END fail'
        program, _ = compile_program(INIT.replace('p[', 'a[') + ' a=fail()', routines=routine)
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual(program._state.snapshot()['A'], MATRIX)
        self.assertEqual(program._state.snapshot()['N'], 7)
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))


class NamedComponentArrayRejectionTests(unittest.TestCase):
    def reject(self, code, **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_different_component_names_in_return(self):
        self.reject('E_RETURN', routines='ROUTINE make: ARRAY OF row_t VAR p: ARRAY[2] OF other_row_t BEGIN RETURN p END make')

    def test_different_component_names_in_destination(self):
        self.reject('E_TYPE', declarations='a: ARRAY[2] OF other_row_t')

    def test_different_inner_lengths_in_return(self):
        types = TYPES + '\nlong_t=ARRAY[3] OF INTEGER'
        self.reject('E_RETURN', types=types, routines='ROUTINE make: ARRAY OF row_t VAR p: ARRAY[2] OF long_t BEGIN RETURN p END make')

    def test_same_rank_different_component_hierarchy_is_not_coerced(self):
        self.reject('E_RETURN', declarations='a: ARRAY[1] OF plane_t',
                    routines='ROUTINE make: ARRAY OF plane_t VAR p: ARRAY[1] OF flat_plane_t BEGIN RETURN p END make')

    def test_flat_multidimensional_source_is_not_rebuilt(self):
        self.reject('E_ARRAY_RETURN_SOURCE', routines='ROUTINE make: ARRAY OF row_t VAR p: ARRAY[2,2] OF INTEGER BEGIN RETURN p END make')

    def test_flat_generic_multidimensional_source_is_not_rebuilt(self):
        self.reject('E_ARRAY_RETURN_SOURCE', body='', routines='ROUTINE make(p: ARRAY[*,*] OF INTEGER): ARRAY OF row_t BEGIN RETURN p END make')

    def test_named_outer_source_remains_blocked(self):
        self.reject('E_ARRAY_RETURN_SOURCE', routines='ROUTINE make: ARRAY OF row_t VAR p: plane_t BEGIN RETURN p END make')

    def test_named_subarray_source_remains_blocked(self):
        self.reject('E_ARRAY_RETURN_SOURCE', body='', routines='ROUTINE make: ARRAY OF INTEGER VAR p: ARRAY[2] OF row_t BEGIN RETURN p[1] END make')

    def test_named_outer_result_declaration_remains_blocked(self):
        self.reject('E_RETURN_TYPE', routines='ROUTINE make: plane_t BEGIN END make')

    def test_direct_string_results_remain_blocked(self):
        self.reject('E_RETURN_TYPE', body='', routines="ROUTINE make: STRING[3] BEGIN RETURN 'abc' END make")

    def test_four_logical_dimensions_rejected(self):
        types = TYPES + '\ncube_t=ARRAY[2] OF plane_t'
        self.reject('E_ARRAY_RANK', types=types, body='', routines='ROUTINE make: ARRAY OF cube_t BEGIN END make')

    def test_forward_named_component_rejected(self):
        with self.assertRaises(TranslationError) as caught:
            translate('PROGRAM T ROUTINE make: ARRAY OF row_t BEGIN END make TYPE row_t=ARRAY[2] OF INTEGER BEGIN END T')
        self.assertEqual(caught.exception.code, 'E_TYPE')

    def test_only_complete_direct_assignment_accepts_result(self):
        for body in ('a=(make())', 'a=make()+1', 'n=ARRAY_LEN(make())', 'IF make() THEN n=1 ENDIF'):
            with self.subTest(body=body): self.reject('E_ARRAY_RESULT_CONTEXT', body=body)

    def test_direct_result_forwarding_rejected(self):
        self.reject('E_ARRAY_RESULT_CONTEXT', body='', routines=FACTORY + '\nROUTINE copy: ARRAY OF row_t BEGIN RETURN make() END copy')

    def test_whole_array_value_argument_remains_blocked(self):
        routine = 'ROUTINE copy(p: ARRAY OF row_t) BEGIN END copy'
        self.reject('E_ARRAY_VALUE', body='copy((a))', routines=routine)


class NamedComponentArrayRuntimeTests(unittest.TestCase):
    def test_all_supported_terminal_kinds_detach_recursively(self):
        structure = ('STRUCTURE', 'ITEM_T', (('LABEL', ('STRING', 3)), ('COUNT', rt.INTEGER)))
        for terminal in (rt.INTEGER, rt.BOOLEAN, rt.REAL, rt.BYTE, rt.SHORT, structure,
                         *((kind,) for kind in rt.DATA_RECORD_TYPES), *(('JOINTPOS', n) for n in range(1, 10))):
            with self.subTest(terminal=terminal):
                row = ('ARRAY', 2, terminal, 'ROW_T')
                source = initialized_host(('ARRAY', 1, row))
                result = rt.array_result(('ARRAY', None, row), source, 37)
                self.assertEqual(result.snapshot(), source.snapshot())
                self.assertIsNot(result.values[0], source.values[0])
                if terminal[0] in rt.DATA_RECORD_TYPES or terminal[0] in ('STRUCTURE', 'JOINTPOS'):
                    self.assertIsNot(result.values[0].values[0], source.values[0].values[0])
                if terminal == ('POSITION',):
                    for name in rt.POSITION_READ_ONLY_FIELDS:
                        self.assertTrue(result.values[0].values[0].values[name].read_only)

    def test_inner_host_shape_corruption_is_source_located(self):
        row = ('ARRAY', 2, rt.INTEGER, 'ROW_T')
        for change in ('identity', 'shape', 'length', 'scalar'):
            with self.subTest(change=change):
                source = initialized_host(('ARRAY', 1, row))
                child = source.values[0]
                if change == 'identity': child.spec = ('ARRAY', 2, rt.INTEGER, 'OTHER_T')
                elif change == 'shape': child.shape = (1, 2)
                elif change == 'length': child.values.pop()
                else: child.values[1] = True
                before = source.snapshot()
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'line 37'):
                    rt.array_result(('ARRAY', None, row), source, 37)
                self.assertEqual(source.snapshot(), before)

    def test_unknown_narrow_leaves_and_short_marker_are_rejected(self):
        for terminal, value in ((rt.BYTE, rt.UNKNOWN_BYTE), (rt.SHORT, 32767), (rt.INTEGER, rt.UNINITIALIZED)):
            with self.subTest(terminal=terminal):
                row = ('ARRAY', 2, terminal, 'ROW_T')
                source = initialized_host(('ARRAY', 1, row)); source.values[0].values[1] = value
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'line 37'):
                    rt.array_result(('ARRAY', None, row), source, 37)

    def test_malformed_component_declarations_are_checked(self):
        row = ('ARRAY', 2, rt.INTEGER, 'ROW_T')
        source = initialized_host(('ARRAY', 1, row))
        for element in (('ARRAY', 2, rt.INTEGER), ('ARRAY', 2, rt.INTEGER, ''),
                        ('ARRAY', None, rt.INTEGER, 'ROW_T'), ('ARRAY', (), rt.INTEGER, 'ROW_T'),
                        ('ARRAY', True, rt.INTEGER, 'ROW_T'), ('ARRAY', 2, [], 'ROW_T'),
                        ('ARRAY', 2, (), 'ROW_T'), ('ARRAY', 2, ('STRING', 3), 'ROW_T'),
                        ('ARRAY', (2, 2, 2), rt.INTEGER, 'ROW_T'),
                        ('ARRAY', 2, ('ARRAY', 2, rt.INTEGER), 'PLANE_T')):
            with self.subTest(element=element):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'line 37'):
                    rt.array_result(('ARRAY', None, element), source, 37)

    def test_total_scalar_leaf_limit_includes_named_inner_dimensions(self):
        row = ('ARRAY', 2, rt.INTEGER, 'ROW_T')
        source = initialized_host(('ARRAY', 1, row)); source.spec = ('ARRAY', 16384, row); source.shape = (16384,)
        with self.assertRaisesRegex(rt.KarelRuntimeError, '32767 scalar leaves'):
            rt.array_result(('ARRAY', None, row), source, 37)


if __name__ == '__main__':
    unittest.main()
