"""Named-component subarrays from PDF pages 74-75; no controller execution."""
import ast
import unittest

from karel2py import translate
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


TYPES = 'TYPE row_t=ARRAY[2] OF INTEGER\nplane_t=ARRAY[2] OF row_t\ncube_t=ARRAY[2] OF plane_t'
DECLARATIONS = 'row,other_row: row_t\nplane,other_plane: plane_t\ncube,other_cube: cube_t\nx,y,visits: INTEGER'
U = {'uninitialized': True}


def compile_program(body='', *, types=TYPES, declarations=DECLARATIONS, routines='', labelled=False, _translator=translate):
    marker = 'unused_marker::\n' if labelled else ''
    source = f'PROGRAM T\n{types}\nVAR\n{declarations}\n{routines}\nBEGIN\n{marker}{body}\nEND T'
    result = _translator(source, filename='subarrays.kl')
    ast.parse(result.python_source, feature_version=(3, 11))
    namespace = {'__name__': 'subarray_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body='', **kwargs): return compile_program(body, **kwargs)[0].run()


class SubarrayStorageTests(unittest.TestCase):
    def test_full_two_dimensional_subscripts(self): self.assertEqual(execute('plane[2,1]=7 x=plane[2,1]')['X'], 7)
    def test_full_three_dimensional_subscripts(self): self.assertEqual(execute('cube[2,1,2]=7 x=cube[2,1,2]')['X'], 7)
    def test_named_row_read_copy_is_independent(self):
        state = execute('plane[2,1]=7 row=plane[2] plane[2,1]=9')
        self.assertEqual(state['ROW'], [7, U])
        self.assertEqual(state['PLANE'][1], [9, U])
    def test_named_row_assignment(self): self.assertEqual(execute('row[1]=7 row[2]=9 plane[2]=row')['PLANE'][1], [7, 9])
    def test_named_plane_read_from_cube(self): self.assertEqual(execute('cube[2,1,2]=7 plane=cube[2]')['PLANE'], [[U, 7], [U, U]])
    def test_named_plane_assignment_to_cube(self): self.assertEqual(execute('plane[1,2]=7 cube[2]=plane')['CUBE'][1], [[U, 7], [U, U]])
    def test_named_row_read_with_two_prefix_subscripts(self): self.assertEqual(execute('cube[2,1,2]=7 row=cube[2,1]')['ROW'], [U, 7])
    def test_named_row_assignment_with_two_prefix_subscripts(self): self.assertEqual(execute('row[1]=7 cube[2,1]=row')['CUBE'][1][0], [7, U])
    def test_row_to_row_copy(self):
        state = execute('plane[1,1]=7 plane[2]=plane[1] plane[1,1]=9')
        self.assertEqual(state['PLANE'], [[9, U], [7, U]])
    def test_parent_self_copy(self): self.assertEqual(execute('cube[1,1,1]=7 cube=cube')['CUBE'][0][0], [7, U])
    def test_subarray_self_copy(self): self.assertEqual(execute('cube[1,1,1]=7 cube[1]=cube[1] cube[1,1]=cube[1,1]')['CUBE'][0][0], [7, U])
    def test_anonymous_outer_array_retains_named_row(self):
        self.assertEqual(execute('a[2,1]=7 row=a[2]', declarations='a: ARRAY[2] OF row_t\nrow: row_t')['ROW'], [7, U])
    def test_two_outer_dimensions_plus_named_row(self):
        state = execute('a[2,3,1]=7 row=a[2,3]', declarations='a: ARRAY[2,3] OF row_t\nrow: row_t')
        self.assertEqual(state['ROW'], [7, U])
        self.assertEqual(state['A'][1][2], [7, U])
    def test_named_structure_field_contains_nested_array(self):
        types = TYPES + '\npacket_t=STRUCTURE data: plane_t ENDSTRUCTURE'
        self.assertEqual(execute('packet.data[1,2]=7 row=packet.data[1]', types=types, declarations='packet: packet_t\nrow: row_t')['ROW'], [U, 7])
    def test_using_subarray_field(self):
        types = TYPES + '\npacket_t=STRUCTURE data: plane_t ENDSTRUCTURE'
        self.assertEqual(execute('USING packet DO data[1,2]=7 row=data[1] ENDUSING', types=types, declarations='packet: packet_t\nrow: row_t')['ROW'], [U, 7])
    def test_nested_string_capacity(self):
        types = 'TYPE row_t=ARRAY[2] OF STRING[3]\nplane_t=ARRAY[2] OF row_t'
        self.assertEqual(execute("plane[1,2]='abcdef' row=plane[1]", types=types, declarations='row: row_t\nplane: plane_t')['ROW'], [U, 'abc'])
    def test_nested_byte_unknown_state_copy(self):
        types = 'TYPE row_t=ARRAY[2] OF BYTE\nplane_t=ARRAY[2] OF row_t'
        self.assertEqual(execute('plane[1,2]=255 row=plane[1]', types=types, declarations='row: row_t\nplane: plane_t')['ROW'], [{'unknown_byte': True}, 255])
    def test_nested_short_marker(self):
        types = 'TYPE row_t=ARRAY[2] OF SHORT\nplane_t=ARRAY[2] OF row_t'
        self.assertEqual(execute('plane[1,1]=32767 plane[1,2]=-32768 row=plane[1]', types=types, declarations='row: row_t\nplane: plane_t')['ROW'], [U, -32768])
    def test_nested_real_model(self):
        types = 'TYPE row_t=ARRAY[2] OF REAL\nplane_t=ARRAY[2] OF row_t'
        self.assertEqual(execute('plane[1,2]=1.25 row=plane[1]', types=types, declarations='row: row_t\nplane: plane_t')['ROW'], [U, 1.25])
    def test_nested_boolean_values(self):
        types = 'TYPE row_t=ARRAY[2] OF BOOLEAN\nplane_t=ARRAY[2] OF row_t'
        self.assertEqual(execute('plane[1,2]=ON row=plane[1]', types=types, declarations='row: row_t\nplane: plane_t')['ROW'], [U, True])
    def test_initialized_nested_structure_array_copy(self):
        types = 'TYPE rec_t=STRUCTURE n: INTEGER ENDSTRUCTURE\nrow_t=ARRAY[1] OF rec_t\nplane_t=ARRAY[2] OF row_t'
        state = execute('plane[1,1].n=7 plane[2,1].n=9 other_plane=plane plane[1,1].n=11', types=types, declarations='plane,other_plane: plane_t')
        self.assertEqual(state['OTHER_PLANE'], [[{'N': 7}], [{'N': 9}]])
    def test_partial_nested_structure_copy_fails_before_destination_change(self):
        types = 'TYPE rec_t=STRUCTURE n: INTEGER ENDSTRUCTURE\nrow_t=ARRAY[1] OF rec_t\nplane_t=ARRAY[2] OF row_t'
        program, _ = compile_program('plane[1,1].n=7 other_plane[1,1].n=11 other_plane=plane', types=types, declarations='plane,other_plane: plane_t')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual(program._state.snapshot()['OTHER_PLANE'], [[{'N': 11}], [{'N': U}]])
    def test_unknown_byte_in_nested_structure_copy_remains_blocked(self):
        types = 'TYPE rec_t=STRUCTURE n: INTEGER data: BYTE ENDSTRUCTURE\nrow_t=ARRAY[1] OF rec_t\nplane_t=ARRAY[1] OF row_t'
        program, _ = compile_program('plane[1,1].n=7 other_plane[1,1].n=11 other_plane[1,1].data=3 other_plane=plane', types=types, declarations='plane,other_plane: plane_t')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'unknown STRUCTURE'): program.run()
        self.assertEqual(program._state.snapshot()['OTHER_PLANE'], [[{'N': 11, 'DATA': 3}]])
    def test_uninitialized_leaf_read(self):
        program, _ = compile_program('x=cube[1,1,1]')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
    def test_inner_bound_error_has_source_line_and_preserves_prior_write(self):
        program, result = compile_program('plane[1,1]=7\nx=plane[1,3]')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'outside 1..2') as caught: program.run()
        self.assertIsNotNone(caught.exception.line)
        self.assertEqual(program._state.snapshot()['PLANE'][0][0], 7)
    def test_array_len_of_named_row(self): self.assertEqual(execute('x=ARRAY_LEN(cube[1,1])')['X'], 2)
    def test_structured_labelled_engine_parity(self):
        body = 'plane[1,1]=7 row=plane[1] plane[2]=row SELECT plane[2,1] OF CASE(7): x=ARRAY_LEN(plane[2]) ELSE: x=0 ENDSELECT'
        outcomes = []
        for labelled in (False, True):
            program, _ = compile_program(body, labelled=labelled)
            outcomes.append((program.run(), program._state.steps))
        self.assertEqual(outcomes[0], outcomes[1])


class SubarrayReferenceTests(unittest.TestCase):
    def test_named_row_parameter(self):
        routine = 'ROUTINE fill(p: row_t) BEGIN p[1]=7 END fill'
        self.assertEqual(execute('fill(cube[2,1])', routines=routine)['CUBE'][1][0], [7, U])
    def test_generic_row_parameter(self):
        routine = 'ROUTINE fill(p: ARRAY OF INTEGER) BEGIN p[1]=7 END fill'
        self.assertEqual(execute('fill(cube[2,1])', routines=routine)['CUBE'][1][0], [7, U])
    def test_named_plane_parameter(self):
        routine = 'ROUTINE fill(p: plane_t) BEGIN p[1,1]=7 END fill'
        self.assertEqual(execute('fill(cube[2])', routines=routine)['CUBE'][1][0][0], 7)
    def test_flat_generic_two_dimensional_interface(self):
        routine = 'ROUTINE fill(p: ARRAY[*,*] OF INTEGER) BEGIN p[2,1]=7 END fill'
        self.assertEqual(execute('fill(plane)', routines=routine)['PLANE'][1][0], 7)
    def test_flat_generic_three_dimensional_interface(self):
        routine = 'ROUTINE fill(p: ARRAY[*,*,*] OF INTEGER) BEGIN p[2,1,2]=7 END fill'
        self.assertEqual(execute('fill(cube)', routines=routine)['CUBE'][1][0][1], 7)
    def test_generic_interface_retains_named_component(self):
        routines = 'ROUTINE row_user(p: row_t) BEGIN p[1]=7 END row_user\nROUTINE matrix_user(p: ARRAY OF row_t) BEGIN row_user(p[2]) END matrix_user'
        self.assertEqual(execute('matrix_user(plane)', routines=routines)['PLANE'][1][0], 7)
    def test_generic_interface_retains_named_plane_component(self):
        routine = 'ROUTINE fill(p: ARRAY OF plane_t) BEGIN p[2,1,2]=7 END fill'
        self.assertEqual(execute('fill(cube)', routines=routine)['CUBE'][1][0][1], 7)
    def test_generic_flat_parameter_forwarding(self):
        routines = 'ROUTINE inner(p: ARRAY[*,*] OF INTEGER) BEGIN p[1,2]=7 END inner\nROUTINE outer(p: ARRAY[*,*] OF INTEGER) BEGIN inner(p) END outer'
        self.assertEqual(execute('outer(plane)', routines=routines)['PLANE'][0][1], 7)
    def test_captured_element_survives_row_replacement(self):
        routine = 'ROUTINE work(cell: INTEGER; selected,source: row_t) BEGIN selected=source cell=11 END work'
        state = execute('row[1]=7 row[2]=9 work(plane[1,1],plane[1],row)', routines=routine)
        self.assertEqual(state['PLANE'][0], [11, 9])
        self.assertEqual(state['ROW'], [7, 9])
    def test_captured_row_and_element_survive_whole_cube_replacement(self):
        routine = 'ROUTINE work(cell: INTEGER; selected: row_t; whole,source: cube_t) BEGIN whole=source selected[2]=9 cell=11 END work'
        state = execute('other_cube[1,1,1]=7 work(cube[1,1,1],cube[1,1],cube,other_cube)', routines=routine)
        self.assertEqual(state['CUBE'][0][0], [11, 9])
        self.assertEqual(state['OTHER_CUBE'][0][0], [7, U])
    def test_captured_structure_field_survives_outer_copy(self):
        types = 'TYPE rec_t=STRUCTURE n: INTEGER ENDSTRUCTURE\nrow_t=ARRAY[1] OF rec_t\nplane_t=ARRAY[1] OF row_t'
        routine = 'ROUTINE work(cell: INTEGER; whole,source: plane_t) BEGIN whole=source cell=11 END work'
        state = execute('plane[1,1].n=1 other_plane[1,1].n=7 work(plane[1,1].n,plane,other_plane)', types=types, declarations='plane,other_plane: plane_t', routines=routine)
        self.assertEqual(state['PLANE'][0][0]['N'], 11)
    def test_subarray_index_routine_evaluated_once(self):
        routines = 'ROUTINE choose: INTEGER BEGIN visits=visits+1 RETURN 1 END choose\nROUTINE fill(p: row_t) BEGIN p[1]=7 END fill'
        state = execute('visits=0 fill(plane[choose()])', routines=routines)
        self.assertEqual((state['VISITS'], state['PLANE'][0][0]), (1, 7))
    def test_reference_writes_survive_later_error_and_frames_unwind(self):
        routine = 'ROUTINE fill(p: row_t) BEGIN p[1]=7 p[3]=9 END fill'
        program, _ = compile_program('fill(plane[1])', routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'outside 1..2'): program.run()
        self.assertEqual(program._state.snapshot()['PLANE'][0][0], 7)
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))
    def test_generic_copy_same_concrete_nested_type(self):
        routine = 'ROUTINE copy(p,q: ARRAY[*,*] OF INTEGER) BEGIN p=q END copy'
        self.assertEqual(execute('other_plane[1,1]=7 copy(plane,other_plane)', routines=routine)['PLANE'][0][0], 7)
    def test_generic_copy_mixed_flat_nested_representation_fails(self):
        routine = 'ROUTINE copy(p,q: ARRAY[*,*] OF INTEGER) BEGIN p=q END copy'
        program, _ = compile_program('plane[1,1]=1 flat[1,1]=7 copy(plane,flat)', declarations='plane: plane_t\nflat: ARRAY[2,2] OF INTEGER', routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'identical type and size'): program.run()
        self.assertEqual(program._state.snapshot()['PLANE'][0][0], 1)
    def test_generic_copy_distinct_nested_names_fails(self):
        types = TYPES + '\nalien_t=ARRAY[2] OF row_t'
        routine = 'ROUTINE copy(p,q: ARRAY[*,*] OF INTEGER) BEGIN p=q END copy'
        program, _ = compile_program('plane[1,1]=1 alien[1,1]=7 copy(plane,alien)', types=types, declarations='plane: plane_t\nalien: alien_t', routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'identical type and size'): program.run()
        self.assertEqual(program._state.snapshot()['PLANE'][0][0], 1)
    def test_generic_copy_known_named_global(self):
        routine = 'ROUTINE copy(p: ARRAY[*,*] OF INTEGER) BEGIN p=other_plane END copy'
        self.assertEqual(execute('other_plane[1,1]=7 copy(plane)', routines=routine)['PLANE'][0][0], 7)
    def test_generic_string_interface_inherits_leaf_capacity(self):
        types = 'TYPE row_t=ARRAY[2] OF STRING[3]\nplane_t=ARRAY[2] OF row_t'
        routine = "ROUTINE fill(p: ARRAY[*,*] OF STRING) BEGIN p[1,1]='abcdef' END fill"
        self.assertEqual(execute('fill(plane)', types=types, declarations='plane: plane_t', routines=routine)['PLANE'][0][0], 'abc')
    def test_generic_structure_interface_keeps_element_nominality(self):
        types = 'TYPE rec_t=STRUCTURE n: INTEGER ENDSTRUCTURE\nrow_t=ARRAY[1] OF rec_t\nplane_t=ARRAY[1] OF row_t'
        routine = 'ROUTINE fill(p: ARRAY[*,*] OF rec_t) BEGIN p[1,1].n=7 END fill'
        self.assertEqual(execute('fill(plane)', types=types, declarations='plane: plane_t', routines=routine)['PLANE'][0][0]['N'], 7)
    def test_recursive_subarray_reference(self):
        routine = 'ROUTINE bump(p: row_t; n: INTEGER) BEGIN IF n>0 THEN p[1]=p[1]+1 bump(p,n-1) ENDIF END bump'
        self.assertEqual(execute('plane[1,1]=0 bump(plane[1],3)', routines=routine)['PLANE'][0][0], 3)
    def test_local_nested_array_storage_is_fresh(self):
        routine = 'ROUTINE work(n: INTEGER): INTEGER VAR data: plane_t BEGIN IF n=1 THEN data[1,1]=7 ENDIF RETURN data[1,1] END work'
        program, _ = compile_program('x=work(1) x=work(2)', routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual(program._state.snapshot()['X'], 7)
    def test_report_records_named_boundaries(self):
        _, result = compile_program('row=cube[1,2] plane=cube[1]')
        uses = result.report['subarray_uses']
        self.assertEqual([(r['selected_type'], r['supplied_subscripts'], r['logical_rank']) for r in uses], [('ROW_T', 2, 3), ('PLANE_T', 1, 3)])
        self.assertTrue(all(r['body'] == 'T' and r['line'] > 0 for r in uses))
        self.assertFalse(result.report['subarray_policy']['controller_validated'])


class SubarrayRejectionTests(unittest.TestCase):
    def rejected(self, body='', *, code='E_TYPE', **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
    def test_unnamed_dimension_boundary_remains_blocked(self): self.rejected('row=a[1]', declarations='a: ARRAY[2,2] OF INTEGER\nrow: row_t', code='E_ARRAY_RANK')
    def test_partial_outer_component_remains_blocked(self): self.rejected('row=a[1]', declarations='a: ARRAY[2,2] OF row_t\nrow: row_t', code='E_ARRAY_RANK')
    def test_four_logical_dimensions_in_type_blocked(self): self.rejected(types=TYPES+'\nextra_t=ARRAY[2] OF cube_t', code='E_ARRAY_RANK')
    def test_four_logical_dimensions_in_variable_blocked(self): self.rejected(declarations='a: ARRAY[2] OF cube_t', code='E_ARRAY_RANK')
    def test_four_logical_dimensions_in_formal_blocked(self): self.rejected(routines='ROUTINE work(p: ARRAY[*,*] OF plane_t) BEGIN END work', code='E_ARRAY_RANK')
    def test_nested_leaf_capacity_guard(self): self.rejected(types='TYPE row_t=ARRAY[200] OF INTEGER\nplane_t=ARRAY[200] OF row_t', declarations='a: plane_t', code='E_ARRAY_CAPACITY')
    def test_named_row_type_mismatch(self): self.rejected('alien=plane[1]', types=TYPES+'\nalien_t=ARRAY[2] OF INTEGER', declarations='alien: alien_t\nplane: plane_t')
    def test_named_component_formal_mismatch(self): self.rejected('work(plane)', types=TYPES+'\nalien_t=ARRAY[2] OF INTEGER', routines='ROUTINE work(p: ARRAY OF alien_t) BEGIN END work')
    def test_whole_copy_between_formals_with_distinct_named_components(self): self.rejected(types=TYPES+'\nalien_t=ARRAY[2] OF INTEGER', routines='ROUTINE copy(p: ARRAY OF row_t; q: ARRAY OF alien_t) BEGIN p=q END copy')
    def test_flat_generic_rank_mismatch(self): self.rejected('work(cube)', routines='ROUTINE work(p: ARRAY[*,*] OF INTEGER) BEGIN END work')
    def test_flat_generic_does_not_expose_unproven_boundary(self): self.rejected(routines='ROUTINE work(p: ARRAY[*,*] OF INTEGER) BEGIN row=p[1] END work', code='E_ARRAY_RANK')
    def test_chained_subscript_syntax_remains_blocked(self): self.rejected('x=plane[1][2]', code='E_ARRAY_RANK')
    def test_parenthesized_subarray_value_remains_blocked(self): self.rejected('work((plane[1]))', routines='ROUTINE work(p: row_t) BEGIN END work', code='E_ARRAY_VALUE', _translator=legacy_translate)
    def test_nested_array_len_is_logically_multidimensional(self): self.rejected('x=ARRAY_LEN(plane)', code='E_ARRAY_LEN', _translator=legacy_translate)
    def test_subarray_array_len_is_logically_multidimensional(self): self.rejected('x=ARRAY_LEN(cube[1])', code='E_ARRAY_LEN', _translator=legacy_translate)
    def test_multiple_indexes_with_user_calls_remain_blocked(self): self.rejected('x=plane[choose(),1]', routines='ROUTINE choose: INTEGER BEGIN RETURN 1 END choose', code='E_EVALUATION_ORDER', _translator=legacy_translate)
    def test_effectful_indexed_result_guard_preserved(self): self.rejected('plane[1]=choose()', routines='ROUTINE choose: INTEGER BEGIN x=7 RETURN 1 END choose', code='E_EVALUATION_ORDER', _translator=legacy_translate)
    def test_subarray_assignment_target_user_call_guard(self): self.rejected('plane[choose()]=row', routines='ROUTINE choose: INTEGER BEGIN RETURN 1 END choose', code='E_EVALUATION_ORDER', _translator=legacy_translate)
    def test_transitive_subarray_reference_effect_guard(self): self.rejected('x=change(plane[1])+1', routines='ROUTINE change(p: row_t): INTEGER BEGIN p[1]=7 RETURN 1 END change', code='E_EVALUATION_ORDER', _translator=legacy_translate)
    def test_inline_anonymous_nested_syntax_remains_blocked(self): self.rejected(declarations='a: ARRAY[2] OF ARRAY[2] OF INTEGER')
    def test_aggregate_uninit_remains_blocked(self): self.rejected('x=UNINIT(plane[1])')


class SubarrayRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.row = ('ARRAY', 2, rt.INTEGER, 'ROW_T')
        self.plane = ('ARRAY', 2, self.row, 'PLANE_T')
        self.cube = ('ARRAY', 2, self.plane, 'CUBE_T')
    def test_runtime_logical_dimensions(self): self.assertEqual(rt.array_dimensions(self.cube), (2, 2, 2))
    def test_native_array_full_and_prefix_access(self):
        data = rt.Array(self.cube)
        data.set((2, 1, 2), 7)
        self.assertEqual(data.get((2, 1, 2)), 7)
        self.assertEqual(data.get((2, 1)).spec, self.row)
        self.assertEqual(data.get(2).spec, self.plane)
    def test_runtime_subarray_reference_matches_named_spec(self): self.assertEqual(rt.index_reference(rt.Array(self.cube), (1, 2)).spec, self.row)
    def test_runtime_generic_formal_checks_logical_rank(self):
        self.assertTrue(rt.parameter_accepts(('ARRAY', (None, None), rt.INTEGER), self.plane))
        self.assertFalse(rt.parameter_accepts(('ARRAY', None, rt.INTEGER), self.plane))
    def test_runtime_component_identity_is_not_erased(self):
        alien = ('ARRAY', 2, rt.INTEGER, 'ALIEN_T')
        self.assertFalse(rt.parameter_accepts(('ARRAY', None, alien), self.plane))
    def test_runtime_constructor_rejects_four_dimensions(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'three dimensions'): rt.Array(('ARRAY', 2, self.cube))
    def test_runtime_constructor_rejects_unnamed_nested_element(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'separately named'): rt.Array(('ARRAY', 2, ('ARRAY', 2, rt.INTEGER)))
    def test_runtime_prefix_not_at_type_boundary(self):
        data = rt.Array(('ARRAY', (2, 2), self.row))
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'type boundary'): data.get(1)
    def test_runtime_empty_and_excess_indexes(self):
        data = rt.Array(self.plane)
        for indexes in ((), (1, 1, 1)):
            with self.subTest(indexes=indexes), self.assertRaises(rt.KarelRuntimeError): data.get(indexes)
    def test_runtime_inner_boolean_index_rejected(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'INTEGER'): rt.Array(self.plane).get((1, True))
    def test_runtime_array_len_rejects_nested_rank(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'multidimensional'): rt.builtin('ARRAY_LEN', [rt.Array(self.plane)])
    def test_runtime_clone_and_replacement_preserve_captured_subarray(self):
        target, source = rt.Array(self.plane), rt.Array(self.plane)
        selected = rt.index_reference(target, 1)
        cell = rt.index_reference(target, (1, 1))
        source.set((1, 1), 7)
        rt.replace_value(target, rt.checked(self.plane, source))
        cell.set(9)
        self.assertEqual(selected.raw().get(1), 9)
        self.assertEqual(source.get((1, 1)), 7)


if __name__ == '__main__': unittest.main()
