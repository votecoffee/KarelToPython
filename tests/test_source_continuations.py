"""Manual-derived source examples, lexical negative controls and location checks."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate
from karel2py.lexer import TranslationError, tokenize
from karel2py.runtime import KarelRuntimeError


ROOT = Path(__file__).resolve().parents[1]


def compile_program(body, declarations='x,y: INTEGER s: STRING[8]', extra=''):
    source = f'PROGRAM test\nVAR {declarations}\n{extra}\nBEGIN\n{body}\nEND test\n'
    result = translate(source, filename='continuation.kl')
    namespace = {'__name__': 'continuation_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, **kwargs):
    return compile_program(body, **kwargs)[0].run()


class ContinuationExecutionTests(unittest.TestCase):
    def test_expression_continuation(self):
        self.assertEqual(execute('x = 1 + &\n  2 * 3')['X'], 7)

    def test_expression_with_trailing_comment(self):
        self.assertEqual(execute('x = 1 + & -- more follows &\n  2')['X'], 3)

    def test_multiple_continued_segments(self):
        self.assertEqual(execute('x = 1 + &\n  2 + &\n  3')['X'], 6)

    def test_variable_declaration(self):
        self.assertEqual(execute('x = 7', declarations='x: &\n INTEGER')['X'], 7)

    def test_fixed_array_declaration(self):
        self.assertEqual(execute('x[2] = 7', declarations='x: ARRAY[2]& -- declaration\n OF INTEGER')['X'], [{'uninitialized': True}, 7])

    def test_multidimensional_array_declaration_and_subscripts(self):
        state = execute('x[1,&\n 2] = 7', declarations='x: ARRAY[2,&\n 2] OF INTEGER')
        self.assertEqual(state['X'], [[{'uninitialized': True}, 7], [{'uninitialized': True}, {'uninitialized': True}]])

    def test_constant_declaration(self):
        result = translate('PROGRAM p\nCONST n = 1 + &\n 2\nVAR x: INTEGER\nBEGIN\nx = n\nEND p')
        namespace = {'__name__': 'constant_test'}
        exec(result.python_source, namespace)
        self.assertEqual(namespace['Program']().run()['X'], 3)

    def test_manual_structure_access_form(self):
        source = '''PROGRAM p
TYPE inner_t = STRUCTURE n: INTEGER ENDSTRUCTURE
outer_t = STRUCTURE item: inner_t ENDSTRUCTURE
VAR record: outer_t
BEGIN
record.item&
 .n = 7
END p'''
        result = translate(source)
        namespace = {'__name__': 'field_test'}
        exec(result.python_source, namespace)
        self.assertEqual(namespace['Program']().run(), {'RECORD': {'ITEM': {'N': 7}}})

    def test_routine_formals_return_type_and_return_expression(self):
        extra = '''ROUTINE add(a: &
 INTEGER; b: INTEGER): &
 INTEGER
BEGIN
 RETURN a + &
 b
END add'''
        self.assertEqual(execute('x = add(1,&\n 2)', extra=extra)['X'], 3)

    def test_reference_parameter_across_continuation(self):
        extra = 'ROUTINE set(p: INTEGER)\nBEGIN\np = 7\nEND set'
        self.assertEqual(execute('set(&\n x)', extra=extra)['X'], 7)

    def test_if_condition(self):
        self.assertEqual(execute('IF 1 =&\n 1 THEN x = 7 ELSE x = 0 ENDIF')['X'], 7)

    def test_select_condition(self):
        self.assertEqual(execute('SELECT 1 +&\n 1 OF CASE(2): x = 7 ELSE: x = 0 ENDSELECT')['X'], 7)

    def test_for_bound(self):
        state = execute('y = 0 FOR x = 1 TO &\n 3 DO y = y + x ENDFOR')
        self.assertEqual((state['Y'], state['X']), (6, {'uninitialized': True}))

    def test_while_and_repeat_conditions(self):
        self.assertEqual(execute('x = 0 WHILE x <&\n 2 DO x = x + 1 ENDWHILE REPEAT x = x + 1 UNTIL x =&\n 3')['X'], 3)

    def test_label_and_goto(self):
        self.assertEqual(execute('GO &\n TO done\nx = 0\ndone::\nx = 7')['X'], 7)

    def test_strings_and_comments_preserve_ampersands(self):
        state = execute("s = 'A&B' -- ordinary comment &\nx = STR_LEN(s)")
        self.assertEqual((state['S'], state['X']), ('A&B', 3))

    def test_string_concatenation_across_continuation(self):
        self.assertEqual(execute("s = 'A&' + &\n 'B'")['S'], 'A&B')

    def test_semicolon_survives_removed_newline(self):
        state = execute('x = 1; &\n y = 2')
        self.assertEqual((state['X'], state['Y']), (1, 2))

    def test_no_whitespace_needed_when_tokens_cannot_fuse(self):
        self.assertEqual(execute('x=1+&\n2')['X'], 3)

    def test_explicit_whitespace_before_marker_separates_names(self):
        self.assertEqual(execute('IF TRUE THEN &\nx = 7 ENDIF')['X'], 7)

    def test_explicit_whitespace_after_marker_separates_names(self):
        self.assertEqual(execute('IF TRUE THEN& \nx = 7 ENDIF')['X'], 7)

    def test_252_character_physical_line_is_accepted(self):
        prefix = 'x = 1 + & --'
        self.assertEqual(execute(prefix + 'a' * (252 - len(prefix)) + '\n 2')['X'], 3)

    def test_example_complete_snapshot(self):
        source = (ROOT / 'examples/source_continuations.kl').read_text(encoding='utf-8')
        result = translate(source)
        namespace = {'__name__': 'example_test'}
        exec(result.python_source, namespace)
        self.assertEqual(namespace['Program']().run(), dict(
            RECORD=dict(ITEM=dict(VALUE=31, TAG='A&B')), VALUES=[10, 20, 30], TOTAL=51, TEXT='A&B', RESULT=1))

    def test_example_preserves_behavior_across_all_newline_forms(self):
        source = (ROOT / 'examples/source_continuations.kl').read_text(encoding='utf-8')
        for newline in ('\n', '\r\n', '\r', '\f'):
            with self.subTest(newline=repr(newline)):
                result = translate(source.replace('\n', newline))
                namespace = {'__name__': 'newline_test'}
                exec(result.python_source, namespace)
                self.assertEqual(namespace['Program']().run(), dict(
                    RECORD=dict(ITEM=dict(VALUE=31, TAG='A&B')), VALUES=[10, 20, 30], TOTAL=51, TEXT='A&B', RESULT=1))


class ContinuationBoundaryTests(unittest.TestCase):
    def reject(self, source, code):
        with self.assertRaises(TranslationError) as caught:
            tokenize(source, 'negative.kl')
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.filename, 'negative.kl')
        return caught.exception

    def test_leading_marker(self):
        self.reject('&\nx=1', 'E_CONTINUATION_POSITION')

    def test_marker_only_line(self):
        self.reject('x=1\n  &\nx=2', 'E_CONTINUATION_POSITION')

    def test_inline_marker(self):
        self.reject('x=1 & +2\nx=3', 'E_CONTINUATION_POSITION')

    def test_multiple_markers_on_one_line(self):
        self.reject('x=1 &&\nx=2', 'E_CONTINUATION_POSITION')

    def test_dangling_marker_at_eof(self):
        self.reject('x=1 &', 'E_CONTINUATION_END')

    def test_dangling_marker_before_eof_newline(self):
        self.reject('x=1 &\n', 'E_CONTINUATION_EMPTY')

    def test_empty_target_line(self):
        self.reject('x=1 &\n  \nx=2', 'E_CONTINUATION_EMPTY')

    def test_comment_only_target_line(self):
        self.reject('x=1 &\n -- comment\nx=2', 'E_CONTINUATION_EMPTY')

    def test_target_line_cannot_begin_with_marker(self):
        self.reject('x=1 &\n &\nx=2', 'E_CONTINUATION_POSITION')

    def test_directive_continuation(self):
        self.reject('%NOLOCKGROUP&\nx=1', 'E_CONTINUATION_DIRECTIVE')

    def test_continuation_into_directive(self):
        self.reject('x=1 &\n%NOLOCKGROUP', 'E_CONTINUATION_DIRECTIVE')

    def test_directive_comment_ampersand_is_ordinary_comment(self):
        result = translate('PROGRAM p\n%NOLOCKGROUP -- &\nBEGIN\nEND p')
        self.assertEqual(result.report['continuations'], [])

    def test_split_tokens_do_not_get_reassembled(self):
        for source in ('cou&\nnt', '1&\n2', '1.&\n5', '>&\n=', '-&\n-', ':&\n:', 'THEN&\nx'):
            with self.subTest(source=source):
                self.reject(source, 'E_CONTINUATION_TOKEN')

    def test_continued_begin_needs_semicolon(self):
        self.reject('BEGIN&\nx=1', 'E_CONTINUATION_SEPARATOR')
        self.assertEqual([token.value for token in tokenize('BEGIN; &\nx=1', 'valid.kl')], ['BEGIN', ';', 'X', '=', '1', '<EOF>'])

    def test_strings_cannot_be_split(self):
        self.reject("x='a&\nb'", 'E_LEX')

    def test_marker_line_over_252_is_rejected(self):
        self.reject('x=1 & --' + 'a' * 245 + '\nx=2', 'E_CONTINUATION_LINE_LENGTH')

    def test_target_line_over_252_is_rejected(self):
        self.reject('x=1 + &\n2 --' + 'a' * 249, 'E_CONTINUATION_LINE_LENGTH')

    def test_intermediate_chain_line_over_252_is_rejected(self):
        self.reject('x=1 + &\n2 + & --' + 'a' * 245 + '\n3', 'E_CONTINUATION_LINE_LENGTH')

    def test_continuation_does_not_enable_other_unsupported_features(self):
        with self.assertRaises(TranslationError) as caught:
            translate('PROGRAM p\nVAR f: &\n VISION\nBEGIN\nEND p')
        self.assertEqual(caught.exception.code, 'E_TYPE')


class ContinuationLocationTests(unittest.TestCase):
    def test_token_locations_and_only_marked_newline_removed(self):
        tokens = tokenize('x = 1 + & -- comment\r\n\t2\r\ny=3', 'location.kl')
        self.assertEqual([(t.value, t.line, t.column) for t in tokens], [
            ('X', 1, 1), ('=', 1, 3), ('1', 1, 5), ('+', 1, 7), ('2', 2, 2),
            ('\r\n', 2, 3), ('Y', 3, 1), ('=', 3, 2), ('3', 3, 3), ('<EOF>', 3, 4)])

    def test_continuation_report_has_original_coordinates(self):
        _, result = compile_program('x = 1 + & -- comment\n  2 + &\n  3')
        self.assertEqual(result.report['continuations'], [
            dict(line=5, column=9, next_line=6, next_column=3, trailing_comment=True),
            dict(line=6, column=7, next_line=7, next_column=3, trailing_comment=False)])
        self.assertIn('physical line continuation', result.report['features'])
        self.assertTrue(result.report['source_policy']['physical_locations_preserved'])
        self.assertFalse(result.report['source_policy']['controller_validated'])

    def test_no_continuation_in_strings_comments_or_metadata(self):
        _, result = compile_program("s = '&' -- &\nx=1")
        self.assertEqual(result.report['continuations'], [])
        self.assertNotIn('physical line continuation', result.report['features'])

    def test_source_hash_includes_physical_text(self):
        source = 'PROGRAM p\r\nVAR x: INTEGER\r\nBEGIN\r\nx = 1 + &\r\n 2\r\nEND p'
        self.assertEqual(translate(source).report['source_sha256'], hashlib.sha256(source.encode('utf-8')).hexdigest())

    def test_symbol_error_points_to_following_physical_line(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('x = 1 + &\n  missing')
        self.assertEqual((caught.exception.code, caught.exception.token.line, caught.exception.token.column), ('E_SYMBOL', 6, 3))

    def test_runtime_error_points_to_operand_physical_line(self):
        program, _ = compile_program('x = 1 + &\n  y')
        with self.assertRaises(KarelRuntimeError) as caught:
            program.run()
        self.assertEqual(caught.exception.line, 6)

    def test_source_map_for_continued_target(self):
        _, result = compile_program('x = 1; &\n  y = 2')
        self.assertTrue(any(row['karel_line'] == 6 and row['karel_column'] == 3 for row in result.report['source_map']))

    def test_error_location_with_each_physical_newline_form(self):
        for newline in ('\n', '\r\n', '\r', '\f'):
            with self.subTest(newline=repr(newline)):
                with self.assertRaises(TranslationError) as caught:
                    translate(newline.join(['PROGRAM p', 'VAR x: INTEGER', 'BEGIN', 'x=1+&', ' missing', 'END p']))
                self.assertEqual((caught.exception.code, caught.exception.token.line, caught.exception.token.column), ('E_SYMBOL', 5, 2))

    def test_bom_does_not_shift_columns(self):
        records = []
        tokens = tokenize('\ufeffx=1+&\n 2', 'bom.kl', continuations=records)
        self.assertEqual((tokens[0].line, tokens[0].column), (1, 1))
        self.assertEqual(records[0]['column'], 5)

    def test_cli_acceptance_and_physical_diagnostic_file_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output, report = (Path(folder) / name for name in ('p.kl', 'p.py', 'p.json'))
            source.write_text('PROGRAM p\nVAR x: INTEGER\nBEGIN\nx=1+&\n 2\nEND p', encoding='utf-8')
            command = [sys.executable, '-m', 'karel2py', str(source), '-o', str(output), '--report', str(report)]
            accepted = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(json.loads(report.read_text(encoding='utf-8'))['continuations'][0]['next_line'], 5)
            original_output = output.read_bytes()
            source.write_text('PROGRAM p\nVAR x: INTEGER\nBEGIN\nx=1+&\n missing\nEND p', encoding='utf-8')
            rejected = subprocess.run(command + ['--force'], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 2, rejected.stderr)
            self.assertEqual(output.read_bytes(), original_output)
            diagnostic = json.loads(report.read_text(encoding='utf-8'))['diagnostics'][0]
            self.assertEqual((diagnostic['code'], diagnostic['line'], diagnostic['column']), ('E_SYMBOL', 5, 2))


if __name__ == '__main__':
    unittest.main()
