"""Transparent TYPE aliases preserve checked storage and nominal aggregates."""
import json
from pathlib import Path
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


def compile_program(body='', *, types='TYPE count_t=INTEGER', declarations='value: count_t',
                    routines='', constants='', translator=translate, **context):
    result = translator(f'PROGRAM T\n{constants}\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T',
                        filename='type_aliases.kl')
    namespace = {'__name__': 'alias_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](**context), result


def execute(body='', **kwargs):
    return compile_program(body, **kwargs)[0].run()


class ScalarAliasTests(unittest.TestCase):
    def test_integer_alias_arithmetic(self):
        self.assertEqual(execute('value=6*7')['VALUE'], 42)

    def test_real_alias_uses_python_float(self):
        self.assertEqual(execute('value=1/3', types='TYPE fraction_t=REAL', declarations='value: fraction_t')['VALUE'], 1/3)

    def test_boolean_alias_condition(self):
        self.assertTrue(execute('value=ON IF value THEN value=NOT OFF ENDIF', types='TYPE flag_t=BOOLEAN', declarations='value: flag_t')['VALUE'])

    def test_alias_chain_is_case_insensitive(self):
        self.assertEqual(execute('value=42', types='TYPE first_t=INTEGER second_t=FiRsT_T count_t=second_t')['VALUE'], 42)

    def test_aliases_across_type_sections(self):
        self.assertEqual(execute('value=42', types='TYPE first_t=INTEGER\nTYPE count_t=first_t')['VALUE'], 42)

    def test_alias_reference_writes_caller(self):
        state = execute('value=1 change(value)', routines='ROUTINE change(p: count_t) BEGIN p=p+1 END change')
        self.assertEqual(state['VALUE'], 2)

    def test_alias_value_argument_is_independent(self):
        state = execute('value=1 change((value))', routines='ROUTINE change(p: count_t) BEGIN p=99 END change')
        self.assertEqual(state['VALUE'], 1)

    def test_alias_scalar_result_and_bare_call(self):
        self.assertEqual(execute('value=answer', routines='ROUTINE answer: count_t BEGIN RETURN 42 END answer')['VALUE'], 42)

    def test_alias_result_integer_to_real_promotion(self):
        state = execute('value=answer()', types='TYPE fraction_t=REAL', declarations='value: fraction_t',
                        routines='ROUTINE answer: fraction_t BEGIN RETURN 7 END answer')
        self.assertEqual(state['VALUE'], 7.0)

    def test_alias_boolean_result(self):
        self.assertTrue(execute('value=answer()', types='TYPE flag_t=BOOLEAN', declarations='value: flag_t',
                                routines='ROUTINE answer: flag_t BEGIN RETURN ON END answer')['VALUE'])

    def test_local_variable_and_constant_dimensions(self):
        state = execute('value=answer()', constants='CONST width=2', types='TYPE row_t=ARRAY[width] OF INTEGER count_t=INTEGER',
                        routines='ROUTINE answer: count_t VAR local: count_t row: row_t BEGIN local=42 row[2]=local RETURN row[2] END answer')
        self.assertEqual(state['VALUE'], 42)

    def test_integer_range_and_no_partial_store(self):
        program, _ = compile_program('value=7 value=MAXINT')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'MAXINT'): program.run()
        self.assertEqual(program.snapshot()['VALUE'], 7)

    def test_uninitialized_alias_read(self):
        program, _ = compile_program('value=value+1')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()

    def test_alias_for_counter_rules_remain(self):
        state = execute('total=0 FOR value=1 TO 2 DO total=total+value ENDFOR', declarations='value: count_t total: INTEGER')
        self.assertEqual(state, {'VALUE': {'uninitialized': True}, 'TOTAL': 3})


class StringAliasTests(unittest.TestCase):
    TYPES = 'TYPE text_t=STRING[3] other_t=text_t'

    def run_text(self, body, **kwargs):
        return execute(body, types=self.TYPES, declarations='value: other_t', **kwargs)

    def test_bounded_storage_truncates(self):
        self.assertEqual(self.run_text("value='abcdef'")['VALUE'], 'abc')

    def test_string_result_keeps_alias_capacity(self):
        self.assertEqual(self.run_text('value=answer()', routines="ROUTINE answer: text_t BEGIN RETURN 'abcdef' END answer")['VALUE'], 'abc')

    def test_formal_reference_preserves_capacity(self):
        self.assertEqual(self.run_text('change(value)', routines="ROUTINE change(p: text_t) BEGIN p='abcdef' END change")['VALUE'], 'abc')

    def test_value_formal_truncates_before_body(self):
        self.assertEqual(self.run_text("copy('abcdef')", routines='ROUTINE copy(p: text_t) BEGIN value=p END copy')['VALUE'], 'abc')

    def test_value_formal_keeps_capacity_on_later_write(self):
        self.assertEqual(self.run_text("copy('a')", routines="ROUTINE copy(p: text_t) BEGIN p='abcdef' value=p END copy")['VALUE'], 'abc')

    def test_grouped_storage_is_independent(self):
        state = self.run_text("value='abc' change((value))", routines="ROUTINE change(p: text_t) BEGIN p='xyz' END change")
        self.assertEqual(state['VALUE'], 'abc')

    def test_generic_string_formal_accepts_alias_reference(self):
        self.assertEqual(self.run_text('change(value)', routines="ROUTINE change(p: STRING) BEGIN p='abcdef' END change")['VALUE'], 'abc')

    def test_bounded_reference_requires_same_capacity(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('change(wide)', types=self.TYPES, declarations='wide: STRING[4]',
                            routines='ROUTINE change(p: text_t) BEGIN END change')
        self.assertEqual(caught.exception.code, 'E_TYPE')

    def test_grouping_different_capacity_makes_value_copy(self):
        state = execute("wide='abcd' copy((wide))", types=self.TYPES, declarations='wide: STRING[4] value: text_t',
                        routines='ROUTINE copy(p: text_t) BEGIN value=p END copy')
        self.assertEqual(state, {'WIDE': 'abcd', 'VALUE': 'abc'})

    def test_array_formal_element_alias_keeps_capacity(self):
        state = execute("data[1]='abcd' copy(data)", types=self.TYPES, declarations='data: ARRAY[1] OF text_t value: text_t',
                        routines='ROUTINE copy(p: ARRAY OF text_t) BEGIN value=p[1] END copy')
        self.assertEqual(state, {'DATA': ['abc'], 'VALUE': 'abc'})

    def test_value_temporary_report(self):
        _, result = compile_program("change('abcdef')", types=self.TYPES, declarations='value: text_t',
                                    routines='ROUTINE change(p: text_t) BEGIN END change')
        self.assertEqual(result.report['string_value_arguments'][0]['temporary_capacity'], 3)

    def test_value_limit_precedes_truncation_and_unwinds_frames(self):
        program, _ = compile_program("outer()", types=self.TYPES, declarations='value: text_t',
            routines="ROUTINE copy(p: text_t) BEGIN value=p END copy\nROUTINE outer BEGIN copy('"+'x'*128+"'+'"+'y'*127+"') END outer")
        with self.assertRaisesRegex(rt.KarelRuntimeError, '254 characters'): program.run()
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))
        self.assertEqual(program.snapshot()['VALUE'], {'uninitialized': True})

    def test_value_capture_precedes_later_argument_effect(self):
        state = execute("wide='abcde' copy((wide),touch())", types=self.TYPES+' count_t=INTEGER',
            declarations='wide: STRING[5] value: text_t',
            routines="ROUTINE touch: count_t BEGIN wide='xxxxx' RETURN 1 END touch\n"
                     'ROUTINE copy(p: text_t; q: count_t) BEGIN value=p END copy')
        self.assertEqual(state, {'WIDE': 'xxxxx', 'VALUE': 'abc'})

    def test_prior_effect_survives_later_argument_failure(self):
        program, _ = compile_program("copy(touch(),1 DIV 0)", types=self.TYPES,
            declarations='value: text_t calls: INTEGER',
            routines="ROUTINE touch: text_t BEGIN calls=1 RETURN 'abc' END touch\n"
                     'ROUTINE copy(p: text_t; q: INTEGER) BEGIN value=p END copy')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['CALLS'], 1)
        self.assertEqual(program.snapshot()['VALUE'], {'uninitialized': True})
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_bounded_alias_forwarding_to_generic_string(self):
        state = self.run_text("copy('abcdef')", routines="ROUTINE inner(p: STRING) BEGIN p='xyz123' value=p END inner\n"
                              'ROUTINE copy(p: text_t) BEGIN inner(p) END copy')
        self.assertEqual(state['VALUE'], 'xyz')

    def test_uninitialized_alias_reference_stays_uninitialized(self):
        program, _ = compile_program("change(value)", types=self.TYPES, declarations='value: text_t',
                                    routines='ROUTINE change(p: text_t) BEGIN value=p END change')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))


class AggregateAliasTests(unittest.TestCase):
    TYPES = 'TYPE row_t=ARRAY[2] OF INTEGER row_alias=row_t row_chain=row_alias'

    def test_array_alias_copy_same_identity(self):
        state = execute('a[1]=1 a[2]=2 b=a a[1]=9', types=self.TYPES, declarations='a: row_t b: row_chain')
        self.assertEqual(state, {'A': [9, 2], 'B': [1, 2]})

    def test_named_array_alias_reference(self):
        state = execute('change(a)', types=self.TYPES, declarations='a: row_t',
                        routines='ROUTINE change(p: row_chain) BEGIN p[1]=7 END change')
        self.assertEqual(state['A'][0], 7)

    def test_named_array_alias_value_copy(self):
        state = execute('a[1]=1 a[2]=2 change((a))', types=self.TYPES, declarations='a: row_t',
                        routines='ROUTINE change(p: row_chain) BEGIN p[1]=7 END change')
        self.assertEqual(state['A'], [1, 2])

    def test_alias_array_result(self):
        state = execute('a[1]=1 a[2]=2 b=copy() a[1]=9', types=self.TYPES, declarations='a: row_t b: row_chain',
                        routines='ROUTINE copy: row_alias BEGIN RETURN a END copy')
        self.assertEqual(state['B'], [1, 2])

    def test_nested_array_alias_subarray(self):
        state = execute('matrix[1,1]=7 matrix[1,2]=8 row=matrix[1]', types=self.TYPES+' grid_t=ARRAY[2] OF row_chain',
                        declarations='matrix: grid_t row: row_t')
        self.assertEqual(state['ROW'], [7, 8])

    def test_nested_component_result_alias(self):
        state = execute('a[1,1]=1 a[1,2]=2 b=copy()', types=self.TYPES, declarations='a,b: ARRAY[1] OF row_alias',
                        routines='ROUTINE copy: ARRAY OF row_chain BEGIN RETURN a END copy')
        self.assertEqual(state['B'], [[1, 2]])

    def test_scalar_alias_array_result(self):
        state = execute('a[1]=7 b=copy()', declarations='a,b: ARRAY[1] OF count_t',
                        routines='ROUTINE copy: ARRAY OF count_t BEGIN RETURN a END copy')
        self.assertEqual(state['B'], [7])

    def test_structure_alias_uses_original_identity(self):
        state = execute('a.x=1 b=a b.x=2', types='TYPE item_t=STRUCTURE x: INTEGER ENDSTRUCTURE alias_t=item_t',
                        declarations='a: item_t b: alias_t')
        self.assertEqual(state, {'A': {'X': 1}, 'B': {'X': 2}})

    def test_structure_alias_result_and_using(self):
        state = execute('USING a DO x=7 ENDUSING b=copy()',
                        types='TYPE item_t=STRUCTURE x: INTEGER ENDSTRUCTURE alias_t=item_t',
                        declarations='a,b: alias_t', routines='ROUTINE copy: alias_t BEGIN RETURN a END copy')
        self.assertEqual(state['B'], {'X': 7})

    def test_new_array_definition_stays_distinct_through_schema_copy(self):
        p,_=compile_program('a[1]=7 b=a b[1]=9',types=self.TYPES+' other_t=ARRAY[2]OF INTEGER',declarations='a:row_chain b:other_t')
        self.assertEqual((p.run()['A'][0],p.snapshot()['B'][0]),(7,9))
        self.assertNotEqual(p._state.raw('A').spec[3],p._state.raw('B').spec[3])

    def test_new_structure_definition_keeps_independent_receiver_identity(self):
        program,_=compile_program('a.x=7 b=a b.x=9',types='TYPE a_t=STRUCTURE x:INTEGER ENDSTRUCTURE alias_t=a_t b_t=STRUCTURE x:INTEGER ENDSTRUCTURE',declarations='a:alias_t b:b_t')
        state=program.run();self.assertEqual((state['A']['X'],state['B']['X']),(7,9))
        self.assertEqual((program._state.values['A'].spec[1],program._state.values['B'].spec[1]),('A_T','B_T'))
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.checked(program._state.types['B'],program._state.values['A'])

    def test_array_alias_result_preserves_missing_leaf_and_private_storage(self):
        program, _ = compile_program('a[1]=1 b=copy() b[1]=9', types=self.TYPES, declarations='a: row_t b: row_chain',
                                    routines='ROUTINE copy: row_alias BEGIN RETURN a END copy')
        state=program.run()
        self.assertEqual((state['A'],state['B']),([1,{'uninitialized':True}],[9,{'uninitialized':True}]))

    def test_array_alias_assignment_preserves_uninitialized_scalar_state(self):
        state = execute('a[1]=1 b=a', types=self.TYPES, declarations='a: row_t b: row_chain')
        self.assertEqual(state['B'], [1, {'uninitialized': True}])

    def test_vector_alias_data_and_result(self):
        state = execute('a.x=1 a.y=2 a.z=3 b=copy()', types='TYPE vector_t=VECTOR', declarations='a,b: vector_t',
                        routines='ROUTINE copy: vector_t BEGIN RETURN a END copy')
        self.assertEqual(state['B'], {'X': 1.0, 'Y': 2.0, 'Z': 3.0})

    def test_joint_alias_keeps_width(self):
        _, result = compile_program(types='TYPE joint_t=JOINTPOS3 alias_t=joint_t', declarations='value: alias_t')
        self.assertEqual(result.report['user_types']['ALIAS_T'], ('JOINTPOS', 3))

    def test_narrow_alias_element_ranges_and_promotion(self):
        state = execute('a[1]=255 value=a[1]+1', types='TYPE byte_t=BYTE count_t=INTEGER',
                        declarations='a: ARRAY[1] OF byte_t value: count_t')
        self.assertEqual(state['VALUE'], 256)

    def test_short_alias_field_sentinel(self):
        state = execute('a.x=32767 value=UNINIT(a.x)', types='TYPE short_t=SHORT item_t=STRUCTURE x: short_t ENDSTRUCTURE',
                        declarations='a: item_t value: BOOLEAN')
        self.assertTrue(state['VALUE'])


class AliasBoundaryTests(unittest.TestCase):
    def reject(self, code, **options):
        with self.assertRaises(TranslationError) as caught: compile_program(**options)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.filename, 'type_aliases.kl')

    def test_forward_alias(self): self.reject('E_TYPE', types='TYPE count_t=later_t later_t=INTEGER')
    def test_self_alias(self): self.reject('E_TYPE', types='TYPE count_t=count_t')
    def test_cyclic_alias(self): self.reject('E_TYPE', types='TYPE count_t=other_t other_t=count_t')
    def test_unknown_alias(self): self.reject('E_TYPE', types='TYPE count_t=missing_t')
    def test_duplicate_alias(self): self.reject('E_DUPLICATE', types='TYPE count_t=INTEGER COUNT_T=REAL')
    def test_alias_variable_collision(self): self.reject('E_DUPLICATE', declarations='count_t: INTEGER')
    def test_alias_constant_collision(self): self.reject('E_DUPLICATE', constants='CONST count_t=2')
    def test_alias_local_collision(self): self.reject('E_DUPLICATE', routines='ROUTINE work VAR count_t: INTEGER BEGIN END work')
    def test_alias_formal_collision(self): self.reject('E_DUPLICATE', routines='ROUTINE work(count_t: INTEGER) BEGIN END work')
    def test_invalid_string_capacity(self): self.reject('E_SIZE', types='TYPE count_t=STRING[255]')
    def test_alias_wildcard_definition(self): self.reject('E_VARIABLE_ARRAY_SCOPE', types='TYPE count_t=ARRAY[*] OF INTEGER')
    def test_forward_result_alias(self): self.reject('E_TYPE', types='', routines='ROUTINE work: count_t BEGIN RETURN 7 END work TYPE count_t=INTEGER')
    def test_narrow_global_alias(self):
        self.assertEqual(execute('value=255', types='TYPE count_t=BYTE')['VALUE'], 255)
        self.reject('E_TYPE_ALIAS', types='TYPE count_t=BYTE', translator=legacy_translate)

    def test_narrow_local_alias(self):
        self.assertEqual(execute('work()', types='TYPE count_t=SHORT', declarations='value: INTEGER',
                                 routines='ROUTINE work VAR local: count_t BEGIN local=-2 value=local END work')['VALUE'], -2)

    def test_narrow_formal_alias(self):
        self.assertEqual(execute('value=1 work(value)', types='TYPE count_t=BYTE',
                                 routines='ROUTINE work(p: count_t) BEGIN p=2 END work')['VALUE'], 2)

    def test_narrow_result_alias(self):
        self.assertEqual(execute('value=work()', types='TYPE count_t=SHORT', declarations='value: INTEGER',
                                 routines='ROUTINE work: count_t BEGIN RETURN -7 END work')['VALUE'], -7)
    def test_alias_for_write_protection(self): self.reject('E_FOR_COUNTER', body='FOR value=1 TO 2 DO change(value) ENDFOR', routines='ROUTINE change(p: count_t) BEGIN p=7 END change')
    def test_alias_wrong_result_type(self): self.reject('E_RETURN', routines="ROUTINE work: count_t BEGIN RETURN 'bad' END work")
    def test_unsupported_type_alias(self): self.reject('E_TYPE', types='TYPE count_t=VISION')
    def test_inline_nested_array_alias(self): self.reject('E_TYPE', types='TYPE count_t=ARRAY[2] OF ARRAY[2] OF INTEGER')

    def test_legacy_alias_guards(self):
        for types in ('TYPE count_t=INTEGER', 'TYPE count_t=STRING[3]', 'TYPE row_t=ARRAY[2] OF INTEGER count_t=row_t'):
            with self.subTest(types=types): self.reject('E_TYPE_ALIAS', types=types, translator=legacy_translate)

    def test_report_alias_chain_and_json(self):
        _, result = compile_program(types='TYPE first_t=INTEGER count_t=first_t')
        report = json.loads(json.dumps(result.report))
        self.assertEqual([(r['name'], r['target'], r['resolved_spec']) for r in report['type_aliases']],
                         [('FIRST_T', 'INTEGER', ['INTEGER']), ('COUNT_T', 'FIRST_T', ['INTEGER'])])
        self.assertIn('transparent TYPE alias', report['features'])
        self.assertFalse(report['type_alias_policy']['controller_validated'])
        self.assertNotIn('scalar/type aliases', ' '.join(report['limitations']))

    def test_report_aggregate_alias_retains_original_name(self):
        _, result = compile_program(types=AggregateAliasTests.TYPES, declarations='value: row_chain')
        self.assertEqual(result.report['named_array_types']['ROW_CHAIN'][-1], 'ROW_T')

    def test_authored_example_matches_complete_fixtures(self):
        source = Path(__file__).resolve().parents[1]/'examples/pythonic_type_aliases.kl'
        result = translate(source.read_text(), filename=source.name)
        namespace = {'__name__':'alias_fixture'}
        exec(result.python_source, namespace)
        observed = []
        program = namespace['Program'](write=observed.append)
        self.assertEqual(program.run(), json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(observed, json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual((program._state.local_frames,program._state.call_depth), ([],0))


class BoundedStringValueRuntimeTests(unittest.TestCase):
    def test_private_capacity_and_later_write(self):
        with rt._numeric_scope('pythonic'):
            ref = rt.value_argument(('STRING', 3), 'abcdef', 17)
            self.assertEqual((ref.spec, ref.raw()), (('STRING', 3), 'abc'))
            ref.set('uvwxyz')
            self.assertEqual(ref.raw(), 'uvw')

    def test_ascii_checked_before_truncation(self):
        with rt._numeric_scope('pythonic'), self.assertRaisesRegex(rt.KarelRuntimeError, 'ASCII'):
            rt.value_argument(('STRING', 1), 'a\u00e9', 17)

    def test_length_checked_before_truncation(self):
        with rt._numeric_scope('pythonic'), self.assertRaisesRegex(rt.KarelRuntimeError, '254 characters'):
            rt.value_argument(('STRING', 1), 'x'*255, 17)

    def test_capacity_validation(self):
        for spec in (('STRING', None), ('STRING', True), ('STRING', 0), ('STRING', 255), ('STRING', 1, 'extra')):
            with self.subTest(spec=spec), rt._numeric_scope('pythonic'), self.assertRaisesRegex(rt.KarelRuntimeError, 'capacity'):
                rt.value_argument(spec, 'a', 17)

    def test_strict_value_argument_boundary_remains(self):
        with rt._numeric_scope('strict'), self.assertRaisesRegex(rt.KarelRuntimeError, 'Unsupported'):
            rt.value_argument(('STRING', 3), 'abc', 17)
