"""Fixed named ARRAY identity, captured references and generic-formal checks."""
import ast
import unittest

from karel2py import translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


def compile_program(body='', *, types='TYPE row_t=ARRAY[2] OF INTEGER', declarations='a,b: row_t\nx: INTEGER', routines='', labelled=False):
    marker = 'unused_marker::\n' if labelled else ''
    source = f'PROGRAM T\n{types}\nVAR\n{declarations}\n{routines}\nBEGIN\n{marker}{body}\nEND T'
    result = translate(source, filename='named_arrays.kl')
    ast.parse(result.python_source, feature_version=(3, 11))
    namespace = {'__name__': 'named_array_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body='', **kwargs): return compile_program(body, **kwargs)[0].run()


class NamedArrayStorageTests(unittest.TestCase):
    def test_declarations_have_independent_uninitialized_elements(self):
        self.assertEqual(execute()['A'], [{'uninitialized': True}, {'uninitialized': True}])
        self.assertEqual(execute('a[1]=7')['B'][0], {'uninitialized': True})

    def test_same_type_whole_copy_is_independent(self):
        state = execute('a[1]=7 b=a a[1]=9')
        self.assertEqual(state['B'], [7, {'uninitialized': True}])
        self.assertEqual(state['A'][0], 9)

    def test_deep_copy_preserves_type_name(self):
        program, result = compile_program('a[1]=7 b=a')
        program.run()
        self.assertEqual(program._state.raw('A').spec, ('ARRAY', 2, ('INTEGER',), 'ROW_T'))
        self.assertEqual(program._state.raw('B').spec, program._state.raw('A').spec)
        self.assertIsNot(program._state.raw('A'), program._state.raw('B'))
        self.assertEqual(result.report['named_array_types'], {'ROW_T': ('ARRAY', 2, ('INTEGER',), 'ROW_T')})

    def test_names_are_case_insensitive(self):
        self.assertEqual(execute('a[1]=7 b=a x=b[1]', types='TYPE Row_T=ARRAY[2] OF INTEGER', declarations='a: rOw_t\nb: ROW_T\nx: INTEGER')['X'], 7)

    def test_size_constant(self):
        self.assertEqual(execute('a[3]=7', types='CONST size=3\nTYPE row_t=ARRAY[size] OF INTEGER', declarations='a: row_t')['A'], [{'uninitialized': True}, {'uninitialized': True}, 7])

    def test_named_boolean_array(self):
        self.assertEqual(execute('a[1]=ON b=a a[1]=OFF', types='TYPE row_t=ARRAY[2] OF BOOLEAN')['B'][0], True)

    def test_named_real_array(self):
        self.assertEqual(execute('a[1]=1.25 a[2]=2 b=a', types='TYPE row_t=ARRAY[2] OF REAL')['B'], [1.25, 2.0])

    def test_named_string_array_capacity(self):
        self.assertEqual(execute("a[1]='abcdef' b=a a[1]='z'", types='TYPE row_t=ARRAY[2] OF STRING[3]')['B'][0], 'abc')

    def test_named_byte_array_unknown_initial_state(self):
        state = execute('a[1]=255 b=a', types='TYPE row_t=ARRAY[2] OF BYTE')
        self.assertEqual(state['B'], [255, {'unknown_byte': True}])

    def test_named_short_array_uninitialized_marker(self):
        self.assertEqual(execute('a[1]=32767 a[2]=-32768 b=a', types='TYPE row_t=ARRAY[2] OF SHORT')['B'], [{'uninitialized': True}, -32768])

    def test_two_dimensional_named_array(self):
        state = execute('a[1,2]=7 b=a a[1,2]=9', types='TYPE row_t=ARRAY[2,3] OF INTEGER')
        self.assertEqual(state['B'][0][1], 7)
        self.assertEqual(state['A'][0][1], 9)

    def test_three_dimensional_named_array(self):
        state = execute('a[2,1,2]=7 b=a', types='TYPE row_t=ARRAY[2,2,2] OF INTEGER')
        self.assertEqual(state['B'][1][0][1], 7)

    def test_array_len_for_one_dimension(self): self.assertEqual(execute('x=ARRAY_LEN(a)')['X'], 2)

    def test_named_array_field(self):
        types = 'TYPE row_t=ARRAY[2] OF INTEGER\npacket_t=STRUCTURE data: row_t ENDSTRUCTURE'
        state = execute('packet.data[1]=7 b=packet.data', types=types, declarations='packet: packet_t\nb: row_t')
        self.assertEqual(state['B'], [7, {'uninitialized': True}])

    def test_using_named_array_field(self):
        types = 'TYPE row_t=ARRAY[2] OF INTEGER\npacket_t=STRUCTURE data: row_t ENDSTRUCTURE'
        state = execute('USING packet DO data[1]=7 data[2]=9 b=data ENDUSING', types=types, declarations='packet: packet_t\nb: row_t')
        self.assertEqual(state['B'], [7, 9])

    def test_structure_copy_with_named_array_field(self):
        types = 'TYPE row_t=ARRAY[2] OF INTEGER\npacket_t=STRUCTURE data: row_t ENDSTRUCTURE'
        state = execute('packet.data[1]=7 packet.data[2]=9 copy=packet packet.data[1]=11', types=types, declarations='packet,copy: packet_t')
        self.assertEqual(state['COPY']['DATA'], [7, 9])

    def test_array_of_structures_with_named_array_fields(self):
        types = 'TYPE row_t=ARRAY[2] OF INTEGER\npacket_t=STRUCTURE data: row_t ENDSTRUCTURE\npackets_t=ARRAY[1] OF packet_t'
        state = execute('a[1].data[1]=7 a[1].data[2]=9 b=a a[1].data[1]=11', types=types, declarations='a,b: packets_t')
        self.assertEqual(state['B'], [{'DATA': [7, 9]}])

    def test_named_structure_array_copy_guard(self):
        types = 'TYPE packet_t=STRUCTURE value: INTEGER ENDSTRUCTURE\nrow_t=ARRAY[2] OF packet_t'
        program, _ = compile_program('a[1].value=7 b=a', types=types)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual(program._state.snapshot()['B'], [{'VALUE': {'uninitialized': True}}, {'VALUE': {'uninitialized': True}}])

    def test_array_boundary_preserves_prior_write(self):
        program, _ = compile_program('a[1]=7 a[3]=9')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'outside 1..2'): program.run()
        self.assertEqual(program._state.snapshot()['A'][0], 7)

    def test_source_continuation_in_named_array_definition(self):
        types = 'TYPE row_t=ARRAY & -- complete tokens\n[2] OF INTEGER'
        self.assertEqual(execute('a[1]=7', types=types)['A'][0], 7)

    def test_labelled_and_structured_execution_parity(self):
        body = 'a[1]=7 a[2]=9 b=a SELECT b[1] OF CASE(7): x=ARRAY_LEN(b) ELSE: x=0 ENDSELECT'
        outcomes = []
        for labelled in (False, True):
            program, _ = compile_program(body, labelled=labelled)
            outcomes.append((program.run(), program._state.steps))
        self.assertEqual(outcomes[0], outcomes[1])


class NamedArrayReferenceTests(unittest.TestCase):
    def test_named_reference_initializes_caller(self):
        routine = 'ROUTINE fill(p: row_t) BEGIN p[1]=7 p[2]=9 END fill'
        self.assertEqual(execute('fill(a)', routines=routine)['A'], [7, 9])

    def test_reference_forwarding_preserves_identity(self):
        routines = 'ROUTINE fill(p: row_t) BEGIN p[1]=7 END fill\nROUTINE forward(p: row_t) BEGIN fill(p) END forward'
        self.assertEqual(execute('forward(a)', routines=routines)['A'][0], 7)

    def test_same_storage_aliases(self):
        routine = 'ROUTINE work(p,q: row_t) BEGIN p[1]=7 q[2]=p[1]+2 END work'
        self.assertEqual(execute('work(a,a)', routines=routine)['A'], [7, 9])

    def test_capture_element_survives_whole_copy(self):
        routine = 'ROUTINE work(p: INTEGER; table,source: row_t) BEGIN table=source p=11 END work'
        state = execute('a[1]=1 b[1]=7 b[2]=9 work(a[1],a,b)', routines=routine)
        self.assertEqual(state['A'], [11, 9])

    def test_named_array_field_reference(self):
        types = 'TYPE row_t=ARRAY[2] OF INTEGER\npacket_t=STRUCTURE data: row_t ENDSTRUCTURE'
        routine = 'ROUTINE fill(p: row_t) BEGIN p[1]=7 END fill'
        state = execute('fill(packet.data)', types=types, declarations='packet: packet_t', routines=routine)
        self.assertEqual(state['PACKET']['DATA'][0], 7)

    def test_named_structure_field_reference_survives_copy(self):
        types = 'TYPE packet_t=STRUCTURE value: INTEGER ENDSTRUCTURE\nrow_t=ARRAY[1] OF packet_t'
        routine = 'ROUTINE work(p: INTEGER; table,source: row_t) BEGIN table=source p=11 END work'
        state = execute('a[1].value=1 b[1].value=7 work(a[1].value,a,b)', types=types, routines=routine)
        self.assertEqual(state['A'], [{'VALUE': 11}])

    def test_generic_reference_keeps_concrete_named_spec(self):
        routine = 'ROUTINE fill(p: ARRAY OF INTEGER) BEGIN p[1]=7 END fill'
        program, _ = compile_program('fill(a)', routines=routine)
        program.run()
        self.assertEqual(program._state.raw('A').spec[3], 'ROW_T')
        self.assertEqual(program._state.snapshot()['A'][0], 7)

    def test_generic_same_named_copy(self):
        routine = 'ROUTINE copy(p,q: ARRAY OF INTEGER) BEGIN p=q END copy'
        self.assertEqual(execute('b[1]=7 copy(a,b)', routines=routine)['A'][0], 7)

    def test_generic_different_named_copy_rejected_before_destination_write(self):
        types = 'TYPE row_t=ARRAY[2] OF INTEGER\nother_t=ARRAY[2] OF INTEGER'
        routine = 'ROUTINE copy(p,q: ARRAY OF INTEGER) BEGIN p=q END copy'
        program, _ = compile_program('a[1]=1 b[1]=7 copy(a,b)', types=types, declarations='a: row_t\nb: other_t', routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'identical type and size'): program.run()
        self.assertEqual(program._state.snapshot()['A'], [1, {'uninitialized': True}])
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_generic_named_and_anonymous_copy_rejected(self):
        routine = 'ROUTINE copy(p,q: ARRAY OF INTEGER) BEGIN p=q END copy'
        for declarations in ('a: row_t\nb: ARRAY[2] OF INTEGER', 'a: ARRAY[2] OF INTEGER\nb: row_t'):
            program, _ = compile_program('a[1]=1 b[1]=7 copy(a,b)', declarations=declarations, routines=routine)
            with self.assertRaisesRegex(rt.KarelRuntimeError, 'identical type and size'): program.run()
            self.assertEqual(program._state.snapshot()['A'][0], 1)

    def test_generic_copy_from_known_same_named_global(self):
        routine = 'ROUTINE copy(p: ARRAY OF INTEGER) BEGIN p=b END copy'
        self.assertEqual(execute('b[1]=7 copy(a)', routines=routine)['A'][0], 7)

    def test_generic_copy_from_known_different_named_global_fails(self):
        types = 'TYPE row_t=ARRAY[2] OF INTEGER\nother_t=ARRAY[2] OF INTEGER'
        routine = 'ROUTINE copy(p: ARRAY OF INTEGER) BEGIN p=b END copy'
        program, _ = compile_program('a[1]=1 b[1]=7 copy(a)', types=types, declarations='a: row_t\nb: other_t', routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'identical type and size'): program.run()
        self.assertEqual(program._state.snapshot()['A'][0], 1)

    def test_generic_string_capacity_is_inherited(self):
        routine = "ROUTINE fill(p: ARRAY OF STRING) BEGIN p[1]='abcdef' END fill"
        self.assertEqual(execute('fill(a)', types='TYPE row_t=ARRAY[2] OF STRING[3]', routines=routine)['A'][0], 'abc')

    def test_generic_two_dimensional_reference(self):
        routine = 'ROUTINE fill(p: ARRAY[*,*] OF INTEGER) BEGIN p[2,3]=7 END fill'
        self.assertEqual(execute('fill(a)', types='TYPE row_t=ARRAY[2,3] OF INTEGER', routines=routine)['A'][1][2], 7)

    def test_fresh_local_storage_each_call(self):
        routine = 'ROUTINE work(n: INTEGER): INTEGER VAR local_data: row_t BEGIN IF n=1 THEN local_data[1]=7 RETURN local_data[1] ELSE RETURN local_data[1] ENDIF END work'
        program, _ = compile_program('x=work(1) x=work(2)', routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual(program._state.snapshot()['X'], 7)
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_routine_local_named_array_copy(self):
        routine = 'ROUTINE work: INTEGER VAR local_data: row_t BEGIN local_data=a RETURN local_data[1] END work'
        self.assertEqual(execute('a[1]=7 x=work()', routines=routine)['X'], 7)

    def test_recursive_named_references(self):
        routine = 'ROUTINE work(p: row_t; n: INTEGER) BEGIN IF n>0 THEN p[1]=p[1]+1 work(p,n-1) ENDIF END work'
        self.assertEqual(execute('a[1]=0 work(a,3)', routines=routine)['A'][0], 3)

    def test_named_array_effect_analysis(self):
        routine = 'ROUTINE change(p: row_t): INTEGER BEGIN p[1]=7 RETURN 1 END change'
        with self.assertRaises(TranslationError) as caught: compile_program('x=change(a)+1', routines=routine)
        self.assertEqual(caught.exception.code, 'E_EVALUATION_ORDER')

    def test_conversion_output_in_named_array(self):
        routine = "ROUTINE parse(p: row_t) BEGIN CNV_STR_INT('7',p[1]) END parse"
        self.assertEqual(execute('parse(a)', routines=routine)['A'][0], 7)

    def test_report_formal_identity_and_policy(self):
        _, result = compile_program('fill(a)', routines='ROUTINE fill(p: row_t) BEGIN END fill')
        formal = result.report['routine_effects']['FILL']['parameters'][0]
        self.assertEqual(formal['type_spec'], ('ARRAY', 2, ('INTEGER',), 'ROW_T'))
        self.assertEqual(formal['passing_modes'], ['reference'])
        self.assertFalse(result.report['named_array_policy']['controller_validated'])


class NamedArrayRejectionTests(unittest.TestCase):
    def rejected(self, body='', *, code='E_TYPE', **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_identically_declared_distinct_names_cannot_copy(self):
        self.rejected('a=b', types='TYPE row_t=ARRAY[2] OF INTEGER\nother_t=ARRAY[2] OF INTEGER', declarations='a: row_t\nb: other_t')
    def test_named_and_anonymous_arrays_cannot_copy(self):
        self.rejected('a=b', declarations='a: row_t\nb: ARRAY[2] OF INTEGER')
        self.rejected('b=a', declarations='a: row_t\nb: ARRAY[2] OF INTEGER')
    def test_distinct_named_formal_rejected(self):
        self.rejected('work(b)', types='TYPE row_t=ARRAY[2] OF INTEGER\nother_t=ARRAY[2] OF INTEGER', declarations='b: other_t', routines='ROUTINE work(p: row_t) BEGIN END work')
    def test_anonymous_actual_to_named_formal_rejected(self):
        self.rejected('work(a)', declarations='a: ARRAY[2] OF INTEGER', routines='ROUTINE work(p: row_t) BEGIN END work')
    def test_parenthesized_named_array_value_rejected(self):
        self.rejected('work((a))', code='E_ARRAY_VALUE', routines='ROUTINE work(p: row_t) BEGIN END work')
    def test_generic_forwarding_to_named_formal_remains_blocked(self):
        routines = 'ROUTINE named(p: row_t) BEGIN END named\nROUTINE generic(p: ARRAY OF INTEGER) BEGIN named(p) END generic'
        self.rejected('generic(a)', routines=routines)
    def test_generic_rank_mismatch(self):
        self.rejected('work(a)', routines='ROUTINE work(p: ARRAY[*,*] OF INTEGER) BEGIN END work')
    def test_named_array_len_rank_guard(self):
        self.rejected('x=ARRAY_LEN(a)', code='E_ARRAY_LEN', types='TYPE row_t=ARRAY[2,3] OF INTEGER')
    def test_partial_named_array_subscript_blocked(self):
        self.rejected('x=a[1]', code='E_ARRAY_RANK', types='TYPE row_t=ARRAY[2,3] OF INTEGER')
    def test_nested_named_array_definition(self):
        self.assertEqual(execute('a[1,2]=7', types='TYPE row_t=ARRAY[2] OF INTEGER\nouter_t=ARRAY[2] OF row_t', declarations='a: outer_t')['A'][0][1], 7)
    def test_nested_named_array_variable(self):
        self.assertEqual(execute('a[1,2]=7', declarations='a: ARRAY[2] OF row_t')['A'][0][1], 7)
    def test_nested_named_array_formal(self):
        self.assertEqual(execute('work(a)', declarations='a: ARRAY[2] OF row_t', routines='ROUTINE work(p: ARRAY OF row_t) BEGIN p[1,2]=7 END work')['A'][0][1], 7)
    def test_named_array_function_result_blocked(self):
        self.rejected(routines='ROUTINE work: row_t BEGIN RETURN a END work', code='E_RETURN_TYPE')
    def test_type_to_type_alias_remains_blocked(self):
        self.rejected(types='TYPE row_t=ARRAY[2] OF INTEGER\nother_t=row_t', code='E_TYPE_ALIAS')
    def test_named_string_alias_remains_blocked(self):
        self.rejected(types='TYPE text_t=STRING[3]', declarations='a: text_t', code='E_TYPE_ALIAS')
    def test_named_scalar_alias_remains_blocked(self):
        self.rejected(types='TYPE count_t=INTEGER', declarations='a: count_t', code='E_TYPE_ALIAS')
    def test_forward_structure_element_blocked(self):
        self.rejected(types='TYPE row_t=ARRAY[2] OF later_t\nlater_t=STRUCTURE x: INTEGER ENDSTRUCTURE')
    def test_self_reference_blocked(self):
        self.rejected(types='TYPE row_t=ARRAY[2] OF row_t')
    def test_duplicate_named_array_type(self):
        self.rejected(types='TYPE row_t=ARRAY[2] OF INTEGER\nROW_T=ARRAY[3] OF INTEGER', code='E_DUPLICATE')
    def test_type_name_variable_collision(self): self.rejected(declarations='row_t: INTEGER', code='E_DUPLICATE')
    def test_type_name_local_collision(self): self.rejected(routines='ROUTINE work VAR row_t: INTEGER BEGIN END work', code='E_DUPLICATE')
    def test_variable_sized_named_array_blocked(self): self.rejected(types='TYPE row_t=ARRAY[*] OF INTEGER', code='E_VARIABLE_ARRAY_SCOPE')
    def test_invalid_named_array_size(self): self.rejected(types='TYPE row_t=ARRAY[0] OF INTEGER', code='E_SIZE')
    def test_named_array_capacity_limit(self): self.rejected(types='TYPE row_t=ARRAY[200,200] OF INTEGER', code='E_ARRAY_CAPACITY')
    def test_named_structure_array_leaf_limit(self):
        self.rejected(types='TYPE packet_t=STRUCTURE data: ARRAY[200] OF INTEGER ENDSTRUCTURE\nrow_t=ARRAY[200] OF packet_t', code='E_ARRAY_CAPACITY')
    def test_named_array_byte_uninit_guard(self): self.rejected('x=UNINIT(a[1])', types='TYPE row_t=ARRAY[2] OF BYTE', code='E_BYTE_UNINIT')
    def test_routine_local_type_remains_blocked(self): self.rejected(routines='ROUTINE work TYPE local_t=ARRAY[2] OF INTEGER BEGIN END work', code='E_ROUTINE_LOCALS')


class NamedArrayRuntimeTests(unittest.TestCase):
    def test_named_spec_identity(self): self.assertEqual(rt.array_identity(('ARRAY', 2, rt.INTEGER, 'ROW_T')), 'ROW_T')
    def test_anonymous_spec_identity(self): self.assertIsNone(rt.array_identity(('ARRAY', 2, rt.INTEGER)))
    def test_invalid_nominal_specs(self):
        for spec in (('ARRAY', 2, rt.INTEGER, None), ('ARRAY', 2, rt.INTEGER, ''), ('ARRAY', 2, rt.INTEGER, 'caf\u00e9'), ('ARRAY', 2, rt.INTEGER, 'T', 'extra')):
            with self.subTest(spec=spec), self.assertRaises(rt.KarelRuntimeError): rt.Array(spec)
    def test_named_parameter_requires_same_identity(self):
        named = ('ARRAY', 2, rt.INTEGER, 'ROW_T')
        self.assertTrue(rt.parameter_accepts(named, named))
        self.assertFalse(rt.parameter_accepts(named, ('ARRAY', 2, rt.INTEGER, 'OTHER_T')))
        self.assertFalse(rt.parameter_accepts(named, ('ARRAY', 2, rt.INTEGER)))
    def test_generic_formal_accepts_named_storage(self):
        self.assertTrue(rt.parameter_accepts(('ARRAY', None, rt.INTEGER), ('ARRAY', 2, rt.INTEGER, 'ROW_T')))
    def test_checked_copy_requires_nominal_identity(self):
        named = ('ARRAY', 2, rt.INTEGER, 'ROW_T')
        other = rt.Array(('ARRAY', 2, rt.INTEGER, 'OTHER_T'))
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'identical type and size'): rt.checked(named, other, 42)
    def test_cloning_and_replacement_keep_identity_and_alias(self):
        spec = ('ARRAY', 2, rt.INTEGER, 'ROW_T')
        target, source = rt.Array(spec), rt.Array(spec)
        reference = rt.index_reference(target, 1)
        source.set(1, 7)
        rt.replace_value(target, rt.checked(spec, source))
        reference.set(9)
        self.assertEqual((target.spec, source.spec), (spec, spec))
        self.assertEqual((target.get(1), source.get(1)), (9, 7))


if __name__ == '__main__': unittest.main()
