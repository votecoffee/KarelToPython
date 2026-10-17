"""Caller capacity, whole-array reference identity and rejection boundaries."""
from pathlib import Path
import unittest

from karel2py import translate
from karel2py.lexer import TranslationError
from karel2py.runtime import KarelRuntimeError


DECLARATIONS = '''
small: STRING[3]
large: STRING[8]
words: ARRAY[2] OF STRING[4]
a,z: ARRAY[3] OF INTEGER
wide: ARRAY[5] OF INTEGER
flags: ARRAY[2] OF BOOLEAN
result,other: INTEGER
flag: BOOLEAN
'''


def compile_program(body, routines='', declarations=DECLARATIONS, constants=''):
    result = translate(f'PROGRAM T\n{constants}\nVAR\n{declarations}\n{routines}\nBEGIN\n{body}\nEND T')
    namespace = {'__name__': 'aggregate_parameter_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, routines='', **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


class StringReferenceTests(unittest.TestCase):
    def test_reference_uses_each_callers_capacity(self):
        routine = "ROUTINE label(p: STRING) BEGIN p = 'abcdef' END label"
        state = execute('label(small) label(large)', routine)
        self.assertEqual((state['SMALL'], state['LARGE']), ('abc', 'abcdef'))

    def test_uninitialized_string_can_be_output(self):
        routine = "ROUTINE label(p: STRING) BEGIN flag = UNINIT(p) p = 'abc' END label"
        state = execute('label(small)', routine)
        self.assertTrue(state['FLAG'])
        self.assertEqual(state['SMALL'], 'abc')

    def test_reading_uninitialized_string_fails_and_unwinds(self):
        p, _ = compile_program('read_text(small)', 'ROUTINE read_text(p: STRING) BEGIN result = STR_LEN(p) END read_text')
        with self.assertRaisesRegex(KarelRuntimeError, 'uninitialized'): p.run()
        self.assertEqual(p._state.local_frames, [])
        self.assertEqual(p._state.call_depth, 0)

    def test_length_reports_stored_value_after_truncation(self):
        routine = "ROUTINE label(p: STRING) BEGIN p = 'abcdef' result = STR_LEN(p) END label"
        self.assertEqual(execute('label(small)', routine)['RESULT'], 3)

    def test_string_element_has_its_own_capacity(self):
        routine = "ROUTINE label(p: STRING) BEGIN p = 'abcdef' END label"
        state = execute('label(words[1])', routine)
        self.assertEqual(state['WORDS'], ['abcd', {'uninitialized': True}])

    def test_nested_forwarding_preserves_capacity(self):
        routines = "ROUTINE label(p: STRING) BEGIN p = 'abcdef' END label\nROUTINE forward(q: STRING) BEGIN label(q) END forward"
        self.assertEqual(execute('forward(small)', routines)['SMALL'], 'abc')

    def test_same_string_reference_aliases_immediately(self):
        routine = "ROUTINE alias(p,q: STRING) BEGIN p = 'abcdef' result = STR_LEN(q) q = q + '!' END alias"
        state = execute('small = \'x\' alias(small,small)', routine)
        self.assertEqual((state['SMALL'], state['RESULT']), ('abc', 3))

    def test_formals_with_different_capacities_are_independent(self):
        routine = "ROUTINE copy(p,q: STRING) BEGIN q = p p = 'abcdef' END copy"
        state = execute("large = '12345678' copy(large,small)", routine)
        self.assertEqual((state['SMALL'], state['LARGE']), ('123', 'abcdef'))

    def test_local_string_output_parameter(self):
        routines = "ROUTINE label(p: STRING) BEGIN p = 'abcdef' END label\nROUTINE outer VAR local_text: STRING[2] BEGIN label(local_text) result = STR_LEN(local_text) END outer"
        self.assertEqual(execute('outer', routines)['RESULT'], 2)

    def test_string_comparison_inside_routine(self):
        routine = "ROUTINE check(p: STRING): BOOLEAN BEGIN RETURN p = 'abc' END check"
        self.assertTrue(execute("small = 'abc' flag = check(small)", routine)['FLAG'])

    def test_string_reference_index_captured_once(self):
        routine = "ROUTINE label(p: STRING) BEGIN result = 2 p = 'abcdef' END label"
        state = execute('result = 1 label(words[result])', routine)
        self.assertEqual(state['WORDS'], ['abcd', {'uninitialized': True}])

    def test_truncated_reference_write_persists_after_error(self):
        routine = "ROUTINE fail(p: STRING) BEGIN p = 'abcdef' result = 1 DIV 0 END fail"
        p, _ = compile_program('fail(small)', routine)
        with self.assertRaisesRegex(KarelRuntimeError, 'zero'): p.run()
        self.assertEqual(p._state.get('SMALL'), 'abc')
        self.assertEqual(p._state.local_frames, [])


class ArrayReferenceTests(unittest.TestCase):
    def test_same_routine_accepts_different_lengths(self):
        routine = 'ROUTINE fill(p: ARRAY OF INTEGER) VAR i: INTEGER BEGIN FOR i = 1 TO ARRAY_LEN(p) DO p[i] = i * 2 ENDFOR END fill'
        state = execute('fill(a) fill(wide)', routine)
        self.assertEqual(state['A'], [2, 4, 6])
        self.assertEqual(state['WIDE'], [2, 4, 6, 8, 10])

    def test_boolean_array_parameter(self):
        routine = 'ROUTINE fill(p: ARRAY OF BOOLEAN) BEGIN p[1] = TRUE p[2] = FALSE END fill'
        self.assertEqual(execute('fill(flags)', routine)['FLAGS'], [True, False])

    def test_nested_forwarding_retains_whole_array_storage(self):
        routines = 'ROUTINE change(p: ARRAY OF INTEGER) BEGIN p[1] = 7 END change\nROUTINE forward(q: ARRAY OF INTEGER) BEGIN change(q) END forward'
        self.assertEqual(execute('forward(a)', routines)['A'][0], 7)

    def test_forwarding_element_to_scalar_routine(self):
        routines = 'ROUTINE change(p: INTEGER) BEGIN p = 7 END change\nROUTINE forward(q: ARRAY OF INTEGER) BEGIN change(q[2]) END forward'
        self.assertEqual(execute('forward(a)', routines)['A'][1], 7)

    def test_forwarding_parenthesized_element_by_value(self):
        routines = 'ROUTINE change(p: INTEGER) BEGIN p = 7 END change\nROUTINE forward(q: ARRAY OF INTEGER) BEGIN change((q[2])) END forward'
        self.assertEqual(execute('a[2] = 4 forward(a)', routines)['A'][1], 4)

    def test_aliasing_whole_array_and_element(self):
        routine = 'ROUTINE alias(p: ARRAY OF INTEGER; q: INTEGER) BEGIN p[1] = 7 result = q q = 9 END alias'
        state = execute('a[1] = 1 alias(a,a[1])', routine)
        self.assertEqual((state['A'][0], state['RESULT']), (9, 7))

    def test_two_whole_array_parameters_alias(self):
        routine = 'ROUTINE alias(p,q: ARRAY OF INTEGER) BEGIN p[1] = 7 result = q[1] q[2] = 9 END alias'
        state = execute('alias(a,a)', routine)
        self.assertEqual(state['A'][:2], [7, 9])
        self.assertEqual(state['RESULT'], 7)

    def test_whole_array_assignment_updates_caller(self):
        routine = 'ROUTINE copy(p,q: ARRAY OF INTEGER) BEGIN p = q END copy'
        state = execute('z[1] = 4 z[2] = 5 z[3] = 6 copy(a,z)', routine)
        self.assertEqual(state['A'], [4, 5, 6])

    def test_whole_array_copy_keeps_caller_arrays_independent(self):
        routine = 'ROUTINE copy(p,q: ARRAY OF INTEGER) BEGIN p = q q[1] = 9 END copy'
        state = execute('z[1] = 4 copy(a,z)', routine)
        self.assertEqual((state['A'][0], state['Z'][0]), (4, 9))

    def test_element_reference_survives_assignment_through_formal(self):
        routine = 'ROUTINE copy(p,q: ARRAY OF INTEGER; slot: INTEGER) BEGIN p = q result = slot slot = 9 END copy'
        state = execute('a[1] = 1 z[1] = 4 z[2] = 5 z[3] = 6 copy(a,z,a[1])', routine)
        self.assertEqual(state['RESULT'], 4)
        self.assertEqual(state['A'], [9, 5, 6])

    def test_array_self_assignment_preserves_alias(self):
        routine = 'ROUTINE copy(p: ARRAY OF INTEGER; slot: INTEGER) BEGIN p = p slot = 9 END copy'
        self.assertEqual(execute('a[1] = 1 copy(a,a[1])', routine)['A'][0], 9)

    def test_copy_of_uninitialized_elements_does_not_read_them(self):
        routine = 'ROUTINE copy(p,q: ARRAY OF INTEGER) BEGIN p = q flag = UNINIT(p[1]) END copy'
        state = execute('a[1] = 3 copy(a,z)', routine)
        self.assertTrue(state['FLAG'])
        self.assertEqual(state['A'], [{'uninitialized': True}] * 3)

    def test_local_array_forwarded_with_its_actual_length(self):
        routines = 'ROUTINE fill(p: ARRAY OF INTEGER) BEGIN p[2] = 8 END fill\nROUTINE outer VAR local_array: ARRAY[2] OF INTEGER BEGIN fill(local_array) result = local_array[2] END outer'
        self.assertEqual(execute('outer', routines)['RESULT'], 8)

    def test_global_assignment_from_array_formal(self):
        routine = 'ROUTINE copy(p: ARRAY OF INTEGER) BEGIN a = p END copy'
        self.assertEqual(execute('z[1] = 7 copy(z)', routine)['A'][0], 7)

    def test_function_reads_array_and_uses_local_for(self):
        routine = 'ROUTINE sum_values(p: ARRAY OF INTEGER): INTEGER VAR i,total: INTEGER BEGIN total = 0 FOR i = 1 TO ARRAY_LEN(p) DO total = total + p[i] ENDFOR RETURN total END sum_values'
        self.assertEqual(execute('a[1] = 1 a[2] = 2 a[3] = 3 result = sum_values(a)', routine)['RESULT'], 6)

    def test_mismatched_runtime_lengths_reject_before_mutation(self):
        routine = 'ROUTINE copy(p,q: ARRAY OF INTEGER) BEGIN p = q END copy'
        p, _ = compile_program('a[1] = 7 wide[1] = 9 copy(a,wide)', routine)
        with self.assertRaisesRegex(KarelRuntimeError, 'identical type and size'): p.run()
        self.assertEqual(p._state.get('A').get(1), 7)
        self.assertEqual(p._state.get('WIDE').get(1), 9)
        self.assertEqual(p._state.local_frames, [])

    def test_mismatched_formal_to_fixed_array_assignment_rejects(self):
        p, _ = compile_program('a[1] = 7 copy(wide)', 'ROUTINE copy(p: ARRAY OF INTEGER) BEGIN a = p END copy')
        with self.assertRaisesRegex(KarelRuntimeError, 'identical type and size'): p.run()
        self.assertEqual(p._state.get('A').get(1), 7)

    def test_bounds_use_actual_caller_length_and_unwind(self):
        p, _ = compile_program('change(a)', 'ROUTINE change(p: ARRAY OF INTEGER) BEGIN p[4] = 7 END change')
        with self.assertRaisesRegex(KarelRuntimeError, 'outside 1..3'): p.run()
        self.assertEqual(p._state.local_frames, [])

    def test_unknown_length_does_not_weaken_element_types(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('fill(a)', 'ROUTINE fill(p: ARRAY OF INTEGER) BEGIN p[1] = TRUE END fill')
        self.assertEqual(caught.exception.code, 'E_TYPE')


class AggregateRejectionTests(unittest.TestCase):
    def rejected(self, body, routine, code, **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, routine, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_string_value_arguments_to_writers_remain_blocked(self):
        for argument in ("'abc'", 'small + large', '(small)', '((small))', '(words[1])', 'C'):
            with self.subTest(argument=argument):
                self.rejected(f'label({argument})', "ROUTINE label(p: STRING) BEGIN p='changed' END label", 'E_STRING_VALUE', constants="CONST C = 'abc'")

    def test_parenthesized_whole_arrays_rejected(self):
        for argument in ('(a)', '((a))'):
            with self.subTest(argument=argument):
                self.rejected(f'fill({argument})', 'ROUTINE fill(p: ARRAY OF INTEGER) BEGIN END fill', 'E_ARRAY_VALUE')

    def test_forwarding_array_by_value_rejected(self):
        routines = 'ROUTINE fill(p: ARRAY OF INTEGER) BEGIN END fill\nROUTINE forward(q: ARRAY OF INTEGER) BEGIN fill((q)) END forward'
        self.rejected('forward(a)', routines, 'E_ARRAY_VALUE')

    def test_wrong_array_element_type_rejected(self):
        self.rejected('fill(flags)', 'ROUTINE fill(p: ARRAY OF INTEGER) BEGIN END fill', 'E_TYPE')

    def test_scalar_not_accepted_as_array(self):
        self.rejected('fill(result)', 'ROUTINE fill(p: ARRAY OF INTEGER) BEGIN END fill', 'E_TYPE')

    def test_array_element_not_accepted_as_whole_array(self):
        self.rejected('fill(a[1])', 'ROUTINE fill(p: ARRAY OF INTEGER) BEGIN END fill', 'E_TYPE')

    def test_wrong_string_actual_type_rejected(self):
        self.rejected('label(result)', 'ROUTINE label(p: STRING) BEGIN END label', 'E_TYPE')

    def test_whole_array_uninit_remains_blocked(self):
        self.rejected('fill(a)', 'ROUTINE fill(p: ARRAY OF INTEGER) BEGIN flag = UNINIT(p) END fill', 'E_TYPE')

    def test_string_function_result_remains_blocked(self):
        self.rejected('', 'ROUTINE text: STRING[3] BEGIN RETURN \'abc\' END text', 'E_RETURN_TYPE')

    def test_aggregate_function_effects_guard_remains_active(self):
        self.rejected('result = other + f(a)', 'ROUTINE f(p: ARRAY OF INTEGER): INTEGER BEGIN p[1] = 7 RETURN 1 END f', 'E_EVALUATION_ORDER')

    def test_array_argument_effect_report_includes_element_type(self):
        _, result = compile_program('fill(a)', 'ROUTINE fill(p: ARRAY OF INTEGER) BEGIN p[1] = 7 END fill')
        parameter = result.report['routine_effects']['FILL']['parameters'][0]
        self.assertEqual(parameter['type_spec'], ('ARRAY', None, ('INTEGER',)))
        self.assertEqual(parameter['passing_modes'], ['reference'])
        self.assertTrue(result.report['routine_effects']['FILL']['potential_external_writes'])

    def test_aggregate_example(self):
        root = Path(__file__).resolve().parents[1]
        result = translate((root / 'examples/aggregate_parameters.kl').read_text())
        namespace = {'__name__': 'aggregate_example'}
        exec(result.python_source, namespace)
        state = namespace['Program']().run()
        self.assertEqual(state['SMALL_TEXT'], 'abc')
        self.assertEqual(state['LARGE_TEXT'], 'abcdef')
        self.assertEqual(state['VALUES'], [99, 20, 30, 40])
        self.assertEqual(state['SAVED'], [10, 20, 30, 40])
        self.assertEqual(state['SEEN_AFTER_COPY'], 10)


if __name__ == '__main__': unittest.main()
