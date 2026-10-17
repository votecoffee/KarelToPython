"""Manual-backed string operations and explicit uncertain-edge guards."""
from pathlib import Path
import unittest

from karel2py import translate
from karel2py.lexer import TranslationError
from karel2py.runtime import KarelRuntimeError


DECLARATIONS = '''
s,t: STRING[20]
small: STRING[3]
words,copy_words: ARRAY[2] OF STRING[3]
long_words: ARRAY[3] OF STRING[8]
numbers: ARRAY[2] OF INTEGER
x,y: INTEGER
flag: BOOLEAN
'''


def compile_program(body, routines='', declarations=DECLARATIONS):
    result = translate(f'PROGRAM T\nVAR\n{declarations}\n{routines}\nBEGIN\n{body}\nEND T')
    namespace = {'__name__': 'string_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, routines='', **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


class StringArrayTests(unittest.TestCase):
    def test_caller_element_capacity_and_array_length(self):
        routine = "ROUTINE fill(p: ARRAY OF STRING) VAR i: INTEGER BEGIN FOR i = 1 TO ARRAY_LEN(p) DO p[i] = 'abcdef' ENDFOR END fill"
        state = execute('fill(words) fill(long_words)', routine)
        self.assertEqual(state['WORDS'], ['abc', 'abc'])
        self.assertEqual(state['LONG_WORDS'], ['abcdef'] * 3)

    def test_nested_array_forwarding_preserves_capacity(self):
        routines = "ROUTINE fill(p: ARRAY OF STRING) BEGIN p[2] = 'abcdef' END fill\nROUTINE forward(q: ARRAY OF STRING) BEGIN fill(q) END forward"
        self.assertEqual(execute('forward(words)', routines)['WORDS'][1], 'abc')

    def test_element_forwarding_to_string_scalar_parameter(self):
        routines = "ROUTINE label(p: STRING) BEGIN p = 'abcdef' END label\nROUTINE fill(q: ARRAY OF STRING) BEGIN label(q[1]) END fill"
        self.assertEqual(execute('fill(words)', routines)['WORDS'][0], 'abc')

    def test_two_whole_string_arrays_can_alias(self):
        routine = "ROUTINE alias(p,q: ARRAY OF STRING) BEGIN p[1] = 'abcdef' x = STR_LEN(q[1]) END alias"
        self.assertEqual(execute('alias(words,words)', routine)['X'], 3)

    def test_whole_copy_preserves_captured_string_element(self):
        routine = "ROUTINE copy(p,q: ARRAY OF STRING; slot: STRING) BEGIN p = q x = STR_LEN(slot) slot = 'abcdef' END copy"
        state = execute("copy_words[1] = 'hi' copy_words[2] = 'bye' copy(words,copy_words,words[1])", routine)
        self.assertEqual(state['X'], 2)
        self.assertEqual(state['WORDS'], ['abc', 'bye'])
        self.assertEqual(state['COPY_WORDS'], ['hi', 'bye'])

    def test_self_assignment_preserves_element_reference(self):
        routine = "ROUTINE copy(p: ARRAY OF STRING; slot: STRING) BEGIN p = p slot = 'abcdef' END copy"
        self.assertEqual(execute('copy(words,words[1])', routine)['WORDS'][0], 'abc')

    def test_uninitialized_elements_can_be_copied(self):
        routine = 'ROUTINE copy(p,q: ARRAY OF STRING) BEGIN p = q flag = UNINIT(p[1]) END copy'
        state = execute("words[1] = 'abc' copy(words,copy_words)", routine)
        self.assertTrue(state['FLAG'])
        self.assertEqual(state['WORDS'], [{'uninitialized': True}] * 2)

    def test_matching_formal_to_global_array_assignment(self):
        routine = 'ROUTINE copy(p: ARRAY OF STRING) BEGIN words = p END copy'
        self.assertEqual(execute("copy_words[1] = 'hi' copy(copy_words)", routine)['WORDS'][0], 'hi')

    def test_capacity_mismatch_fails_before_assignment(self):
        p, _ = compile_program("words[1] = 'old' long_words[1] = 'new text' copy(words,long_words)",
                               'ROUTINE copy(p,q: ARRAY OF STRING) BEGIN p = q END copy')
        with self.assertRaisesRegex(KarelRuntimeError, 'identical type and size'): p.run()
        self.assertEqual(p._state.get('WORDS').get(1), 'old')
        self.assertEqual(p._state.local_frames, [])

    def test_same_length_different_element_capacity_fails(self):
        declarations = 'words: ARRAY[2] OF STRING[3]\ncopy_words: ARRAY[2] OF STRING[8]'
        p, _ = compile_program("words[1] = 'old' copy_words[1] = 'new text' copy(words,copy_words)",
                               'ROUTINE copy(p,q: ARRAY OF STRING) BEGIN p = q END copy', declarations)
        with self.assertRaisesRegex(KarelRuntimeError, 'identical type and size'): p.run()
        self.assertEqual(p._state.get('WORDS').get(1), 'old')

    def test_local_string_array_passed_to_formal(self):
        routines = "ROUTINE fill(p: ARRAY OF STRING) BEGIN p[1] = 'abcdef' END fill\nROUTINE outer VAR local_words: ARRAY[1] OF STRING[2] BEGIN fill(local_words) x = STR_LEN(local_words[1]) END outer"
        self.assertEqual(execute('outer', routines)['X'], 2)

    def test_string_array_formal_report(self):
        _, result = compile_program('fill(words)', 'ROUTINE fill(p: ARRAY OF STRING) BEGIN END fill')
        spec = result.report['routine_effects']['FILL']['parameters'][0]['type_spec']
        self.assertEqual(spec, ('ARRAY', None, ('STRING', None)))


class SubstringTests(unittest.TestCase):
    def runtime_error(self, body, message):
        p, _ = compile_program(body)
        with self.assertRaisesRegex(KarelRuntimeError, message): p.run()

    def test_substring_uses_one_based_start(self):
        self.assertEqual(execute("s = SUB_STR('abcdef',2,3)")['S'], 'bcd')

    def test_exact_source_length(self):
        self.assertEqual(execute("s = SUB_STR('abcdef',1,6)")['S'], 'abcdef')

    def test_last_character(self):
        self.assertEqual(execute("s = SUB_STR('abcdef',6,1)")['S'], 'f')

    def test_start_past_source_returns_empty(self):
        self.assertEqual(execute("s = SUB_STR('abc',4,2)")['S'], '')

    def test_start_past_source_with_large_positive_length(self):
        self.assertEqual(execute("s = SUB_STR('abc',2147483647,2147483647)")['S'], '')

    def test_empty_source_returns_empty(self):
        self.assertEqual(execute("s = SUB_STR('',1,1)")['S'], '')

    def test_nonpositive_start_rejected(self):
        for start in (0, -1):
            with self.subTest(start=start): self.runtime_error(f"s = SUB_STR('abc',{start},1)", 'positive')

    def test_nonpositive_length_rejected_even_past_source(self):
        for count in (0, -1):
            with self.subTest(count=count): self.runtime_error(f"s = SUB_STR('abc',4,{count})", 'positive')

    def test_request_crossing_source_end_remains_blocked(self):
        self.runtime_error("s = SUB_STR('abc',2,3)", 'extending beyond source')

    def test_long_result_capacity_remains_blocked(self):
        self.runtime_error("s = SUB_STR('" + 'a' * 255 + "',1,255)", 'return-capacity validation')

    def test_maximum_supported_result_length(self):
        state = execute("s = SUB_STR('" + 'a' * 254 + "',1,254) x = STR_LEN(s)",
                        declarations='s: STRING[254]\nx: INTEGER')
        self.assertEqual(state['S'], 'a' * 254)
        self.assertEqual(state['X'], 254)

    def test_result_assignment_truncates_to_destination(self):
        self.assertEqual(execute("small = SUB_STR('abcdef',2,5)")['SMALL'], 'bcd')

    def test_substring_in_nested_expression(self):
        self.assertEqual(execute("x = STR_LEN(SUB_STR('abcdef',2,3))")['X'], 3)

    def test_uninitialized_source_rejected(self):
        self.runtime_error('t = SUB_STR(s,1,1)', 'uninitialized')

    def test_substring_through_formal_uses_stored_value(self):
        routine = 'ROUTINE trim(p: STRING) BEGIN p = SUB_STR(p,2,2) END trim'
        self.assertEqual(execute("small = 'abc' trim(small)", routine)['SMALL'], 'bc')


class IndexTests(unittest.TestCase):
    def test_first_match_is_one_based(self):
        self.assertEqual(execute("x = INDEX('banana','ana')")['X'], 2)

    def test_no_match_returns_zero(self):
        self.assertEqual(execute("x = INDEX('banana','pear')")['X'], 0)

    def test_match_at_start(self):
        self.assertEqual(execute("x = INDEX('banana','ban')")['X'], 1)

    def test_match_at_last_character(self):
        self.assertEqual(execute("x = INDEX('banana','a')")['X'], 2)
        self.assertEqual(execute("x = INDEX('abcd','d')")['X'], 4)

    def test_whole_string_match(self):
        self.assertEqual(execute("x = INDEX('abc','abc')")['X'], 1)

    def test_long_search_returns_zero(self):
        self.assertEqual(execute("x = INDEX('abc','abcdef')")['X'], 0)

    def test_empty_source_with_nonempty_search(self):
        self.assertEqual(execute("x = INDEX('','a')")['X'], 0)

    def test_search_is_case_sensitive(self):
        self.assertEqual(execute("x = INDEX('Abc','a')")['X'], 0)

    def test_empty_search_remains_blocked(self):
        for source in ('abc', ''):
            with self.subTest(source=source):
                p, _ = compile_program(f"x = INDEX('{source}','')")
                with self.assertRaisesRegex(KarelRuntimeError, 'empty search'): p.run()

    def test_nested_builtin_arguments(self):
        self.assertEqual(execute("x = INDEX(SUB_STR('abcdef',2,3),CHR(99))")['X'], 2)

    def test_uninitialized_search_fails(self):
        p, _ = compile_program("x = INDEX('abc',s)")
        with self.assertRaisesRegex(KarelRuntimeError, 'uninitialized'): p.run()


class CharacterTests(unittest.TestCase):
    def test_chr_printable_ascii_table(self):
        for code, character in [(32, ' '), (39, "'"), (48, '0'), (65, 'A'), (90, 'Z'), (97, 'a'), (126, '~')]:
            with self.subTest(code=code): self.assertEqual(execute(f's = CHR({code})')['S'], character)

    def test_chr_ascii_controls_are_single_characters(self):
        for code, character in [(0, '\x00'), (9, '\t'), (10, '\n'), (13, '\r'), (127, '\x7f')]:
            with self.subTest(code=code):
                state = execute(f's = CHR({code}) x = STR_LEN(s)')
                self.assertEqual((state['S'], state['X']), (character, 1))

    def test_chr_extended_codes_remain_blocked(self):
        for code in (-1, 128, 255, 2147483647):
            with self.subTest(code=code):
                p, _ = compile_program(f's = CHR({code})')
                with self.assertRaisesRegex(KarelRuntimeError, 'ASCII codes'): p.run()

    def test_ord_one_based_first_and_last(self):
        state = execute("x = ORD('Az',1) y = ORD('Az',2)")
        self.assertEqual((state['X'], state['Y']), (65, 122))

    def test_ord_nonpositive_or_past_end_rejected(self):
        for index in (0, -1, 4):
            with self.subTest(index=index):
                p, _ = compile_program(f"x = ORD('abc',{index})")
                with self.assertRaisesRegex(KarelRuntimeError, 'outside 1..3'): p.run()

    def test_ord_empty_string_rejected(self):
        p, _ = compile_program("x = ORD('',1)")
        with self.assertRaisesRegex(KarelRuntimeError, 'outside 1..0'): p.run()

    def test_ord_chr_for_ascii_controls(self):
        for code in (0, 9, 10, 13, 127):
            with self.subTest(code=code): self.assertEqual(execute(f'x = ORD(CHR({code}),1)')['X'], code)

    def test_character_builtins_inside_for(self):
        state = execute('y = 0 FOR x = 65 TO 67 DO y = y + ORD(CHR(x),1) ENDFOR')
        self.assertEqual(state['Y'], 198)
        self.assertEqual(state['X'], {'uninitialized': True})

    def test_ord_error_retains_source_line(self):
        p, _ = compile_program("s = 'abc'\nx = ORD(s,4)")
        with self.assertRaises(KarelRuntimeError) as caught: p.run()
        self.assertEqual(caught.exception.line, 15)


class StringRejectionTests(unittest.TestCase):
    def rejected(self, body, code, routines=''):
        with self.assertRaises(TranslationError) as caught: compile_program(body, routines)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_builtin_arities(self):
        for expression in ("CHR()", "CHR(1,2)", "ORD('abc')", "ORD('abc',1,2)", "INDEX('abc')", "INDEX('abc','b','c')", "SUB_STR('abc',1)", "SUB_STR('abc',1,1,1)"):
            with self.subTest(expression=expression): self.rejected('x = STR_LEN(' + expression + ')', 'E_ARGUMENTS')

    def test_builtin_argument_types(self):
        for expression in ("CHR(TRUE)", "ORD(1,1)", "ORD('abc',TRUE)", "INDEX(1,'abc')", "INDEX('abc',1)", "SUB_STR(1,1,1)", "SUB_STR('abc',TRUE,1)", "SUB_STR('abc',1,FALSE)"):
            with self.subTest(expression=expression): self.rejected('s = ' + expression, 'E_TYPE')

    def test_string_builtin_cannot_be_assigned_to_integer(self):
        self.rejected('x = CHR(65)', 'E_TYPE')

    def test_string_array_parameter_rejects_integer_array(self):
        self.rejected('fill(numbers)', 'E_TYPE', 'ROUTINE fill(p: ARRAY OF STRING) BEGIN END fill')

    def test_string_array_whole_value_passing_remains_prohibited(self):
        self.rejected('fill((words))', 'E_ARRAY_VALUE', 'ROUTINE fill(p: ARRAY OF STRING) BEGIN END fill')

    def test_string_element_value_to_writer_remains_blocked(self):
        self.rejected('label((words[1]))', 'E_STRING_VALUE', "ROUTINE label(p: STRING) BEGIN p='changed' END label")

    def test_builtin_with_routine_argument_order_remains_blocked(self):
        routine = 'ROUTINE f: INTEGER BEGIN x = 2 RETURN 1 END f'
        self.rejected("x = ORD('abc',f())", 'E_EVALUATION_ORDER', routine)

    def test_pure_routine_argument_order_remains_blocked(self):
        routine = 'ROUTINE f: INTEGER BEGIN RETURN 1 END f'
        self.rejected("s = SUB_STR('abc',f(),1)", 'E_EVALUATION_ORDER', routine)

    def test_single_argument_routine_in_chr_is_supported(self):
        self.assertEqual(execute('s = CHR(f())', 'ROUTINE f: INTEGER BEGIN RETURN 65 END f')['S'], 'A')

    def test_new_string_features_reported(self):
        _, result = compile_program("s = SUB_STR('abc',1,2) x = INDEX(s,CHR(98)) y = ORD(s,1)")
        self.assertTrue({'SUB_STR', 'INDEX', 'CHR', 'ORD'} <= set(result.report['features']))

    def test_string_example(self):
        root = Path(__file__).resolve().parents[1]
        result = translate((root / 'examples/string_processing.kl').read_text())
        namespace = {'__name__': 'string_example'}
        exec(result.python_source, namespace)
        state = namespace['Program']().run()
        self.assertEqual(state['LABELS'], ['AB', 'BC'])
        self.assertEqual(state['MATCH_POSITION'], 2)
        self.assertEqual(state['CHARACTER_CODE'], 67)
        self.assertEqual(state['EXTRACTED'], 'BC')


if __name__ == '__main__': unittest.main()
