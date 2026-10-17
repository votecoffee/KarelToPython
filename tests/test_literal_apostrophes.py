"""Doubled source apostrophes are decoded as data, with physical locations intact."""
import unittest
from karel2py import translate,runtime as rt
from karel2py.lexer import TranslationError,tokenize


def compile_program(body='',*,declarations='text: STRING[80]\nnumber: INTEGER',prefix='',routines='',**context):
    result=translate(f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T',filename='literal_apostrophes.kl')
    namespace={'__name__':'literal_apostrophe_test'}
    exec(result.python_source,namespace)
    return namespace['Program'](**context),result


class LiteralApostropheValueTests(unittest.TestCase):
    def test_apostrophe_in_word(self):
        program,_=compile_program("text='can''t'")
        self.assertEqual(program.run()['TEXT'],"can't")
    def test_only_apostrophe(self):
        program,_=compile_program("text=''''")
        self.assertEqual(program.run()['TEXT'],"'")
    def test_two_apostrophes(self):
        program,_=compile_program("text=''''''")
        self.assertEqual(program.run()['TEXT'],"''")
    def test_boundary_apostrophes(self):
        program,_=compile_program("text='''wrapped'''")
        self.assertEqual(program.run()['TEXT'],"'wrapped'")
    def test_empty_literal_unchanged(self):
        program,_=compile_program("text=''")
        self.assertEqual(program.run()['TEXT'],'')
    def test_literal_case_preserved(self):
        program,_=compile_program("text='Can''T'")
        self.assertEqual(program.run()['TEXT'],"Can'T")
    def test_comment_delimiters_inside_literal(self):
        program,_=compile_program("text='A''--B' -- trailing comment")
        self.assertEqual(program.run()['TEXT'],"A'--B")
    def test_directive_and_continuation_inside_literal(self):
        program,_=compile_program("text='A''%NOLOCKGROUP&B'")
        self.assertEqual(program.run()['TEXT'],"A'%NOLOCKGROUP&B")
    def test_backslashes_remain_literal_data(self):
        program,_=compile_program(r"text='C:\can''t\n'")
        self.assertEqual(program.run()['TEXT'],"C:\\can't\\n")
    def test_code_like_contents_remain_inert(self):
        program,_=compile_program("text='__import__(''not_a_real_module'')'")
        self.assertEqual(program.run()['TEXT'],"__import__('not_a_real_module')")
    def test_manual_generated_source_text(self):
        program,_=compile_program("text=' WRITE (''hello world'', CR)'")
        self.assertEqual(program.run()['TEXT']," WRITE ('hello world', CR)")
    def test_global_constant(self):
        program,_=compile_program('text=label',prefix="CONST label='robot''s'")
        self.assertEqual(program.run()['TEXT'],"robot's")
    def test_local_constant(self):
        program,_=compile_program('inspect',routines="ROUTINE inspect CONST label='robot''s' BEGIN text=label END inspect")
        self.assertEqual(program.run()['TEXT'],"robot's")
    def test_concatenation(self):
        program,_=compile_program("text='A''B'+''''+'C'")
        self.assertEqual(program.run()['TEXT'],"A'B'C")
    def test_equality_and_order(self):
        program,_=compile_program("flag='can''t'='can'+CHR(39)+'t' ordered='''a'<'a'",declarations='flag,ordered: BOOLEAN')
        self.assertEqual(program.run(),dict(FLAG=True,ORDERED=True))
    def test_logical_length(self):
        program,_=compile_program("number=STR_LEN('can''t')")
        self.assertEqual(program.run()['NUMBER'],5)
    def test_substring_uses_logical_positions(self):
        program,_=compile_program("text=SUB_STR('can''t',4,1)")
        self.assertEqual(program.run()['TEXT'],"'")
    def test_index_uses_logical_positions(self):
        program,_=compile_program("number=INDEX('can''t','''')")
        self.assertEqual(program.run()['NUMBER'],4)
    def test_ord_of_apostrophe(self):
        program,_=compile_program("number=ORD('''',1)")
        self.assertEqual(program.run()['NUMBER'],39)
    def test_assignment_truncation_after_decoding(self):
        program,_=compile_program("text='can''t'",declarations='text: STRING[4]')
        self.assertEqual(program.run()['TEXT'],"can'")
    def test_exact_physical_capacity(self):
        program,_=compile_program("text=''''''''''",declarations='text: STRING[4]')
        self.assertEqual(program.run()['TEXT'],"''''")
    def test_array_and_structure_storage(self):
        program,_=compile_program("labels[1]='A''B' packet.label='robot''s'",declarations='labels: ARRAY[1] OF STRING[8]\npacket: packet_t',prefix='TYPE packet_t=STRUCTURE label: STRING[8] ENDSTRUCTURE')
        self.assertEqual(program.run(),dict(LABELS=["A'B"],PACKET=dict(LABEL="robot's")))
    def test_read_only_string_value_argument(self):
        program,_=compile_program("number=inspect('can''t')",routines='ROUTINE inspect(value: STRING): INTEGER BEGIN RETURN STR_LEN(value) END inspect')
        self.assertEqual(program.run()['NUMBER'],5)
    def test_string_reference_output_unchanged(self):
        program,_=compile_program('fill(text)',routines="ROUTINE fill(dest: STRING) BEGIN dest='robot''s' END fill")
        self.assertEqual(program.run()['TEXT'],"robot's")
    def test_unformatted_write_records_decoded_text(self):
        program,_=compile_program("WRITE('can''t')")
        program.run()
        self.assertEqual([row['text'] for row in program.write_requests],["can't"])
    def test_unquoted_write_padding_and_truncation(self):
        program,_=compile_program("WRITE('can''t'::8) WRITE('a''b'::2)")
        program.run()
        self.assertEqual([row['text'] for row in program.write_requests],["can't   ","a'"])
    def test_injected_write_gets_decoded_text(self):
        observed=[]
        program,_=compile_program("WRITE('can''t')",write=observed.append)
        program.run()
        self.assertEqual(observed,["can't"])


class LiteralApostropheSourceTests(unittest.TestCase):
    def test_raw_token_is_preserved(self):
        literal=next(token for token in tokenize("text='can''t'",'raw.kl') if token.kind=='STRING')
        self.assertEqual((literal.value,literal.column),("'can''t'",6))
    def test_following_token_uses_physical_column(self):
        source="text='can''t'; number=7"
        number=next(token for token in tokenize(source,'raw.kl') if token.value=='NUMBER')
        self.assertEqual(number.column,source.index('number=7')+1)
    def test_report_has_raw_and_logical_lengths(self):
        _,result=compile_program("text='can''t'")
        site=result.report['escaped_string_literals'][0]
        self.assertEqual((site['source_characters'],site['logical_characters'],site['escaped_apostrophes']),(8,5,1))
        self.assertIn('doubled apostrophe STRING literal',result.report['features'])
        self.assertFalse(result.report['literal_policy']['controller_validated'])
    def test_comments_do_not_create_literal_entries(self):
        _,result=compile_program("text='simple' -- ''decoy''")
        self.assertEqual(result.report['escaped_string_literals'],[])
    def test_complete_token_continuation(self):
        program,_=compile_program("text='can''t' + & -- comment\n ' stop'")
        self.assertEqual(program.run()['TEXT'],"can't stop")
    def test_continuation_cannot_fuse_quoted_tokens(self):
        with self.assertRaises(TranslationError) as caught: compile_program("text='a'&\n'b'")
        self.assertEqual(caught.exception.code,'E_CONTINUATION_TOKEN')
    def test_implicit_literal_concatenation_blocked(self):
        with self.assertRaises(TranslationError): compile_program("text='a' 'b'")
    def test_multiline_literal_blocked(self):
        for newline in ('\n','\r','\r\n','\f'):
            with self.subTest(newline=repr(newline)),self.assertRaises(TranslationError): compile_program("text='can''"+newline+"t'")
    def test_unmatched_apostrophe_is_rejected(self):
        for literal in ("'", "'''", "'can''", "'can''t"):
            with self.subTest(literal=literal),self.assertRaises(TranslationError): compile_program('text='+literal)
    def test_non_ascii_contents_still_blocked(self):
        with self.assertRaises(TranslationError) as caught: compile_program("text='caf\u00e9''s'")
        self.assertEqual(caught.exception.code,'E_ENCODING')
    def test_quoted_write_embedded_apostrophe_remains_blocked(self):
        program,_=compile_program("WRITE('can''t'::12::2)")
        with self.assertRaisesRegex(rt.KarelRuntimeError,'embedded apostrophes'): program.run()
        self.assertEqual(program.write_requests,())
    def test_string_function_result_remains_blocked(self):
        with self.assertRaises(TranslationError) as caught: compile_program('',routines="ROUTINE label: STRING[8] BEGIN RETURN 'can''t' END label")
        self.assertEqual(caught.exception.code,'E_RETURN_TYPE')
    def test_writable_string_value_argument_remains_blocked(self):
        with self.assertRaises(TranslationError) as caught: compile_program("change('can''t')",routines="ROUTINE change(value: STRING) BEGIN value='new' END change")
        self.assertEqual(caught.exception.code,'E_STRING_VALUE')
    def test_reports_do_not_leak_between_translations(self):
        compile_program("text='can''t'")
        _,result=compile_program("text='plain'")
        self.assertEqual(result.report['escaped_string_literals'],[])
    def test_source_map_after_escaped_literal(self):
        _,result=compile_program("text='can''t'; number=7")
        physical=next(token for token in tokenize("text='can''t'; number=7",'raw.kl') if token.value=='NUMBER').column
        self.assertIn(physical,[row['karel_column'] for row in result.report['source_map']])


if __name__=='__main__': unittest.main()
