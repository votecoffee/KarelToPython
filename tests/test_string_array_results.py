"""Bounded STRING leaves in owned ARRAY results and scalar result assignments."""
import ast
import json
import unittest

from karel2py import translate, runtime as rt
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError


FACTORY = "ROUTINE make: ARRAY OF STRING[3] VAR p: ARRAY[2] OF STRING[3] BEGIN p[1]='abcde' p[2]='' RETURN p END make"
COPY = 'ROUTINE copy(p: ARRAY OF STRING): ARRAY OF STRING[3] BEGIN RETURN p END copy'
TYPES = 'TYPE row_t=ARRAY[2] OF STRING[3]\nplane_t=ARRAY[2] OF row_t'


def compile_program(body='a=make', *, declarations='a,b: ARRAY[2] OF STRING[3] n: INTEGER',
                    routines=FACTORY, types='', constants='', shapes=None, _translator=translate):
    source = f'PROGRAM T\n{constants}\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result = _translator(source, filename='string_array_results.kl', array_shapes=shapes)
    ast.parse(result.python_source, feature_version=(3, 11))
    json.dumps(result.report)
    namespace = {'__name__': 'string_array_result_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(*args, **kwargs): return compile_program(*args, **kwargs)[0].run()


class StringArrayReturnTests(unittest.TestCase):
    def test_fixed_element_capacity_and_empty_initialized_value(self):
        self.assertEqual(execute()['A'], ['abc', ''])

    def test_explicit_function_call_spelling(self):
        self.assertEqual(execute('a=make()')['A'], ['abc', ''])

    def test_global_source_is_independent(self):
        routine = 'ROUTINE copy: ARRAY OF STRING[3] BEGIN RETURN a END copy'
        state = execute("a[1]='abc' a[2]='def' b=copy a[1]='z'", routines=routine)
        self.assertEqual(state['B'], ['abc', 'def'])

    def test_grouped_storage_source_is_allowed(self):
        self.assertEqual(execute(routines=FACTORY.replace('RETURN p', 'RETURN ((p))'))['A'], ['abc', ''])

    def test_global_capacity_constant_is_resolved(self):
        routine = FACTORY.replace('STRING[3]', 'STRING[CAPACITY]')
        program, result = compile_program(routines=routine, constants='CONST CAPACITY=3')
        self.assertEqual(program.run()['A'], ['abc', ''])
        self.assertEqual(result.report['array_returns'][0]['element_spec'], ('STRING', 3))

    def test_concrete_capacity_endpoints(self):
        for capacity in (1, 254):
            with self.subTest(capacity=capacity):
                routine = f"ROUTINE make: ARRAY OF STRING[{capacity}] VAR p: ARRAY[1] OF STRING[{capacity}] BEGIN p[1]='x' RETURN p END make"
                self.assertEqual(execute(routines=routine, declarations=f'a: ARRAY[1] OF STRING[{capacity}]')['A'], ['x'])

    def test_generic_reference_formal_retains_concrete_capacity(self):
        self.assertEqual(execute('a=make b=copy(a) a[1]=\'z\'', routines=FACTORY+'\n'+COPY)['B'], ['abc', ''])

    def test_reference_formal_retains_each_concrete_length(self):
        state = execute("a[1]='abc' b[1]='x' b[2]='y' c=copy(a) d=copy(b)", routines=COPY,
                        declarations='a,c: ARRAY[1] OF STRING[3] b,d: ARRAY[2] OF STRING[3]')
        self.assertEqual((state['C'], state['D']), (['abc'], ['x', 'y']))

    def test_structure_field_source_and_destination(self):
        types = 'TYPE box_t=STRUCTURE words: ARRAY[2] OF STRING[3] ENDSTRUCTURE'
        routine = 'ROUTINE copy: ARRAY OF STRING[3] BEGIN RETURN first.words END copy'
        state = execute("first.words[1]='abc' first.words[2]='def' second.words=copy first.words[1]='z'",
                        routines=routine, types=types, declarations='first,second: box_t')
        self.assertEqual(state['SECOND']['WORDS'], ['abc', 'def'])

    def test_same_source_and_destination(self):
        self.assertEqual(execute('a=make a=copy(a)', routines=FACTORY+'\n'+COPY)['A'], ['abc', ''])

    def test_captured_string_reference_survives_replacement(self):
        routine = FACTORY + "\nROUTINE replace(p: ARRAY OF STRING; captured: STRING) BEGIN p=make captured='z-long' END replace"
        self.assertEqual(execute('replace(a,a[1])', routines=routine)['A'], ['z-l', ''])

    def test_explicit_global_outer_shape_context(self):
        self.assertEqual(execute(declarations='a: ARRAY[*] OF STRING[3]', shapes={'a': [2]})['A'], ['abc', ''])

    def test_named_string_row_result_retains_identity_and_shape(self):
        routine = "ROUTINE make: ARRAY OF row_t VAR p: ARRAY[1] OF row_t BEGIN p[1,1]='abcde' p[1,2]='xyz' RETURN p END make"
        program, result = compile_program(types=TYPES, declarations='a: ARRAY[1] OF row_t', routines=routine)
        self.assertEqual(program.run()['A'], [['abc', 'xyz']])
        self.assertEqual(program._state.raw('A').values[0].spec, ('ARRAY', 2, ('STRING', 3), 'ROW_T'))
        self.assertEqual(result.report['array_returns'][0]['logical_rank'], 2)

    def test_three_dimensions_of_named_string_components(self):
        routine = "ROUTINE make: ARRAY OF plane_t VAR p: ARRAY[1] OF plane_t BEGIN p[1,1,1]='a' p[1,1,2]='b' p[1,2,1]='c' p[1,2,2]='d' RETURN p END make"
        self.assertEqual(execute(types=TYPES, declarations='a: ARRAY[1] OF plane_t', routines=routine)['A'], [[['a', 'b'], ['c', 'd']]])

    def test_named_row_captured_element_survives_replacement(self):
        factory = "ROUTINE make: ARRAY OF row_t VAR p: ARRAY[1] OF row_t BEGIN p[1,1]='abc' p[1,2]='xyz' RETURN p END make"
        routine = factory + "\nROUTINE replace(p: ARRAY OF row_t; captured: STRING) BEGIN p=make captured='z' END replace"
        self.assertEqual(execute('replace(a,a[1,2])', types=TYPES, declarations='a: ARRAY[1] OF row_t', routines=routine)['A'], [['abc', 'z']])

    def test_string_element_can_be_staged_for_readonly_value_use(self):
        routine = FACTORY + '\nROUTINE inspect_text(value: STRING) BEGIN n=STR_LEN(value) END inspect_text'
        self.assertEqual(execute('a=make inspect_text((a[1]))', routines=routine)['N'], 3)

    def test_recursive_results_are_staged_before_return(self):
        routine = FACTORY + "\nROUTINE recur(k: INTEGER): ARRAY OF STRING[3] VAR p: ARRAY[2] OF STRING[3] BEGIN IF k=0 THEN p=make ELSE p=recur(k-1) p[2]='x' ENDIF RETURN p END recur"
        program, _ = compile_program('a=recur(4)', routines=routine)
        self.assertEqual(program.run()['A'], ['abc', 'x'])
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_labelled_and_structured_execution_match(self):
        outcomes = []
        for marker in ('', 'unused:: '):
            program, _ = compile_program(marker+'a=make IF a[1]=\'abc\' THEN n=7 ENDIF')
            outcomes.append((program.run(), program._state.steps))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_result_report_carries_element_capacity(self):
        _, result = compile_program()
        self.assertEqual(result.report['array_returns'][0]['element_spec'], ('STRING', 3))
        self.assertIn('bounded STRING ARRAY function result', result.report['features'])
        self.assertEqual(result.report['array_schema_policy']['guide'],'docs/array-schema-conversions.md')
        self.assertFalse(result.report['array_routine_policy']['controller_validated'])


class StringArrayRejectionTests(unittest.TestCase):
    def reject(self, code, **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_legacy_unspecified_element_capacity_remains_blocked(self):
        self.reject('E_RETURN_TYPE', body='', routines='ROUTINE make: ARRAY OF STRING BEGIN END make', _translator=legacy_translate)

    def test_invalid_capacity_bounds_and_types(self):
        for capacity in ('0', '-1', '255', 'ON', '1.25'):
            with self.subTest(capacity=capacity):
                self.reject('E_SIZE', body='', routines=f'ROUTINE make: ARRAY OF STRING[{capacity}] BEGIN END make')

    def test_capacity_must_be_a_constant_expression(self):
        self.reject('E_CONSTANT', body='', routines='ROUTINE make: ARRAY OF STRING[n] BEGIN END make')

    def test_return_capacity_conversion_checks_source_then_truncates(self):
        routine=FACTORY.replace('VAR p: ARRAY[2] OF STRING[3]','VAR p: ARRAY[2] OF STRING[4]')
        p,_=compile_program(routines=routine);self.assertEqual(p.run()['A'],['abc',''])

    def test_destination_capacity_conversion_retains_receiver_schema(self):
        p,_=compile_program(declarations='a:ARRAY[2]OF STRING[4]');self.assertEqual(p.run()['A'],['abc','']);self.assertEqual(p._state.raw('A').spec[2],('STRING',4))

    def test_direct_string_result_assigns_to_array_element(self):
        program,_=compile_program(body='a[1]=make',routines="ROUTINE make: STRING[3] BEGIN RETURN 'abc' END make")
        self.assertEqual(program.run()['A'][0],'abc')

    def test_named_outer_string_source_returns_owned_anonymous_value(self):
        routine="ROUTINE make:ARRAY OF STRING[3] VAR p:words_t BEGIN p[1]='abc' RETURN p END make"
        p,_=compile_program(types='TYPE words_t=ARRAY[2]OF STRING[3]',routines=routine);self.assertEqual(p.run()['A'],['abc',{'uninitialized':True}]);self.assertEqual(len(p._state.raw('A').spec),3)

    def test_named_outer_result_type_still_blocked(self):
        self.reject('E_RETURN_TYPE', types=TYPES, body='', routines='ROUTINE make: row_t BEGIN END make', _translator=legacy_translate)

    def test_flat_multidimensional_source_still_blocked(self):
        self.reject('E_RETURN', body='', routines='ROUTINE make: ARRAY OF STRING[3] VAR p: ARRAY[2,2] OF STRING[3] BEGIN RETURN p END make')

    def test_flat_generic_string_source_can_return_named_rows(self):
        routine='ROUTINE make(p:ARRAY[*,*]OF STRING):ARRAY OF row_t BEGIN RETURN p END make'
        p,_=compile_program("seed[1,1]='abc' a=make(seed)",types=TYPES,routines=routine,declarations='seed:ARRAY[2,2]OF STRING[4] a:ARRAY[2]OF row_t')
        self.assertEqual(p.run()['A'][0][0],'abc');self.assertEqual(p._state.raw('A').spec[2][3],'ROW_T')

    def test_result_contexts_remain_restricted(self):
        for body in ('a=(make)', 'n=STR_LEN(make)', 'a=make+make', 'IF make THEN n=1 ENDIF'):
            with self.subTest(body=body): self.reject('E_ARRAY_RESULT_CONTEXT', body=body, _translator=legacy_translate)

    def test_direct_result_forwarding_still_blocked(self):
        self.reject('E_ARRAY_RESULT_CONTEXT', body='', routines=FACTORY+'\nROUTINE copy: ARRAY OF STRING[3] BEGIN RETURN make END copy', _translator=legacy_translate)

    def test_whole_array_value_argument_still_blocked(self):
        self.reject('E_ARRAY_VALUE', body='b=copy((a))', routines=COPY, _translator=legacy_translate)

    def test_effectful_array_result_to_indexed_target_still_blocked(self):
        types = 'TYPE box_t=STRUCTURE words: ARRAY[2] OF STRING[3] ENDSTRUCTURE'
        self.reject('E_EVALUATION_ORDER', body='boxes[1].words=make', types=types,
                    declarations='boxes: ARRAY[1] OF box_t n: INTEGER', routines=FACTORY.replace("BEGIN p[1]", "BEGIN n=7 p[1]"), _translator=legacy_translate)


class StringArrayFailureTests(unittest.TestCase):
    def test_generic_return_prepares_declared_capacity_before_copy(self):
        routine=COPY.replace('BEGIN RETURN p','BEGIN n=9 RETURN p')
        p,_=compile_program("a[1]='abcd' a[2]='defg' b[1]='one' b[2]='two' b=copy(a)",routines=routine,declarations='a:ARRAY[2]OF STRING[4] b:ARRAY[2]OF STRING[3] n:INTEGER')
        self.assertEqual((p.run()['B'],p.snapshot()['N']),(['abc','def'],9));self.assertEqual((p._state.call_depth,p._state.local_frames),(0,[]))

    def test_generic_destination_retains_actual_capacity(self):
        routine=FACTORY+'\nROUTINE replace(p:ARRAY OF STRING) BEGIN p=make END replace'
        p,_=compile_program("a[1]='one' a[2]='two' replace(a)",routines=routine,declarations='a:ARRAY[2]OF STRING[4]')
        self.assertEqual(p.run()['A'],['abc','']);self.assertEqual(p._state.raw('A').spec[2],('STRING',4))

    def test_strict_unknown_element_preserves_destination_and_prior_effects(self):
        routine = FACTORY.replace("p[2]=''", 'n=9')
        program, _ = compile_program("a[1]='one' a[2]='two' a=make", routines=routine, _translator=legacy_translate)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual((program.snapshot()['A'], program.snapshot()['N']), (['one', 'two'], 9))
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_wrong_result_length_preserves_destination(self):
        routine = "ROUTINE make: ARRAY OF STRING[3] VAR p: ARRAY[1] OF STRING[3] BEGIN p[1]='abc' RETURN p END make"
        program, _ = compile_program("a[1]='one' a[2]='two' a=make", routines=routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['A'], ['one', 'two'])

    def test_abort_unwinds_array_factory_frames(self):
        program, _ = compile_program("a[1]='one' a[2]='two' a=make", routines=FACTORY.replace('RETURN p', 'ABORT RETURN p'))
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual(program.snapshot()['A'], ['one', 'two'])
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_named_string_actual_returns_owned_anonymous_value(self):
        p,_=compile_program("a[1]='abc' a[2]='def' b=copy(a)",types='TYPE words_t=ARRAY[2]OF STRING[3]',routines=COPY,declarations='a:words_t b:ARRAY[2]OF STRING[3]')
        self.assertEqual(p.run()['B'],['abc','def']);self.assertEqual((p._state.call_depth,p._state.local_frames),(0,[]));self.assertEqual(len(p._state.raw('B').spec),3)


class StringArrayRuntimeTests(unittest.TestCase):
    def source(self, capacity=3, values=('abc', '')):
        source = rt.Array(('ARRAY', len(values), ('STRING', capacity)))
        source.values[:] = values
        return source

    def test_all_capacities_keep_exact_owned_storage(self):
        for capacity in range(1, 255):
            with self.subTest(capacity=capacity):
                value = 'x'*capacity
                source = self.source(capacity, (value, ''))
                result = rt.array_result(('ARRAY', None, ('STRING', capacity)), source, 37)
                self.assertEqual(result.snapshot(), [value, ''])
                self.assertEqual(result.spec, source.spec)
                result.set(1, 'z')
                self.assertEqual(source.snapshot(), [value, ''])

    def test_ascii_controls_and_apostrophe_are_not_formatted(self):
        values = ('\x00\r\x7f', "a'b")
        self.assertEqual(rt.array_result(('ARRAY', None, ('STRING', 3)), self.source(values=values), 37).snapshot(), list(values))

    def test_oversize_host_value_is_rejected_without_truncation(self):
        source = self.source(values=('abcd', ''))
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'capacity'): rt.array_result(('ARRAY', None, ('STRING', 3)), source, 37)
        self.assertEqual(source.snapshot(), ['abcd', ''])

    def test_non_ascii_wrong_type_and_markers_are_source_located(self):
        for value in ('\u00e9', 7, True, rt.UNINITIALIZED, rt.UNKNOWN_BYTE):
            with self.subTest(value=value):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'line 37'):
                    rt.array_result(('ARRAY', None, ('STRING', 3)), self.source(values=('abc', value)), 37)

    def test_bad_element_capacities_remain_explicit_errors(self):
        for element in (('STRING',), ('STRING', None), ('STRING', 0), ('STRING', 255), ('STRING', True), ('STRING', 3, 'EXTRA')):
            with self.subTest(element=element):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'line 37'):
                    rt.array_result(('ARRAY', None, element), self.source(), 37)

    def test_named_component_capacity_is_checked_recursively(self):
        row = ('ARRAY', 2, ('STRING', 3), 'ROW_T')
        source = rt.Array(('ARRAY', 1, row)); source.values[0].values[:] = ['abc', '']
        copied = rt.array_result(('ARRAY', None, row), source, 37)
        self.assertIsNot(copied.values[0], source.values[0])
        source.values[0].values[1] = 'abcd'
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'capacity'):
            rt.array_result(('ARRAY', None, row), source, 37)
        self.assertEqual(copied.snapshot(), [['abc', '']])


if __name__ == '__main__':
    unittest.main()
