"""Quoted STRING output that fits, unquoted width fallback and fail-closed gaps."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import runtime as rt
from tests.legacy_numeric_support import translate
from karel2py.lexer import TranslationError


ROOT=Path(__file__).resolve().parents[1]


def compile_program(body, *, declarations='text: STRING[16]\nx: INTEGER', prefix='', routines='', write=None):
    source=f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result=translate(source,filename='write_quotes.kl')
    namespace={'__name__':'quote_test'}
    exec(result.python_source,namespace)
    return namespace['Program'](write=write),result


def texts(program): return [row['text'] for row in program.write_requests]


class QuotedWriteBehaviorTests(unittest.TestCase):
    def assert_output(self,expression,expected):
        observed=[]
        program,result=compile_program(f'WRITE({expression})',write=observed.append)
        program.run()
        self.assertEqual((texts(program),observed),([expected],[expected]))
        self.assertEqual(program.write_requests[0]['adapter_outcome'],'callback_completed')
        return result
    def test_manual_left_quoted(self): self.assert_output("'ABC'::8::2"," 'ABC'  ")
    def test_manual_right_quoted(self): self.assert_output("'ABC'::8::3","   'ABC'")
    def test_exact_fit_left(self): self.assert_output("'ABC'::6::2"," 'ABC'")
    def test_exact_fit_right(self): self.assert_output("'ABC'::6::3"," 'ABC'")
    def test_empty_exact_left(self): self.assert_output("''::3::2"," ''")
    def test_empty_exact_right(self): self.assert_output("''::3::3"," ''")
    def test_empty_padded_left(self): self.assert_output("''::6::2"," ''   ")
    def test_empty_padded_right(self): self.assert_output("''::6::3","    ''")
    def test_single_character_minimum_width(self): self.assert_output("'A'::4::2"," 'A'")
    def test_blanks_inside_quotes_left(self): self.assert_output("' A '::8::2"," ' A '  ")
    def test_blanks_inside_quotes_right(self): self.assert_output("' A '::8::3","   ' A '")
    def test_double_quote_is_plain_content(self): self.assert_output("'A\"B'::8::2"," 'A\"B'  ")
    def test_ascii_control_is_plain_content(self): self.assert_output('CHR(13)::5::2'," '\r' ")
    def test_max_width_left(self): self.assert_output("'ABC'::254::2"," 'ABC'"+' '*248)
    def test_max_width_right(self): self.assert_output("'ABC'::254::3",' '*249+"'ABC'")
    def test_maximum_fitting_contents(self):
        program,_=compile_program("part='"+'a'*126+"' WRITE((part+SUB_STR(part,1,125))::254::2)",declarations='part: STRING[126]')
        program.run()
        self.assertEqual(texts(program),[" '"+'a'*251+"'"])
    def test_contents_keep_their_capacity_and_value(self):
        program,_=compile_program("text='ABC' WRITE(text::8::2) WRITE(text::8::3)")
        self.assertEqual(program.run()['TEXT'],'ABC')
        self.assertEqual(texts(program),[" 'ABC'  ","   'ABC'"])
    def test_literal_value_formal(self):
        program,result=compile_program("emit('ABC')",routines='ROUTINE emit(p: STRING) BEGIN WRITE(p::8::2) END emit')
        program.run()
        self.assertEqual(texts(program),[" 'ABC'  "])
        self.assertEqual(result.report['routine_effects']['EMIT']['potential_parameter_writes'],[])
    def test_reference_formal(self):
        program,_=compile_program("text='ABC' emit(text)",routines='ROUTINE emit(p: STRING) BEGIN WRITE(p::8::3) END emit')
        self.assertEqual(program.run()['TEXT'],'ABC')
        self.assertEqual(texts(program),["   'ABC'"])
    def test_local_constant(self):
        program,_=compile_program('emit',routines="ROUTINE emit CONST C='ABC' BEGIN WRITE(C::8::2) END emit")
        program.run()
        self.assertEqual(texts(program),[" 'ABC'  "])
    def test_using_field(self):
        program,_=compile_program("packet.label='ABC' USING packet DO WRITE(label::8::3) ENDUSING",prefix='TYPE p=STRUCTURE label: STRING[8] ENDSTRUCTURE',declarations='packet: p')
        program.run()
        self.assertEqual(texts(program),["   'ABC'"])
    def test_array_element(self):
        program,_=compile_program("words[2]='ABC' WRITE(words[2]::8::2)",declarations='words: ARRAY[2] OF STRING[8]')
        program.run()
        self.assertEqual(texts(program),[" 'ABC'  "])
    def test_expression_evaluated_once(self):
        program,_=compile_program('x=0 WRITE(CHR(next_code())::6::2)',routines='ROUTINE next_code: INTEGER BEGIN x=x+1 RETURN 64+x END next_code')
        self.assertEqual(program.run()['X'],1)
        self.assertEqual(texts(program),[" 'A'  "])
    def test_nested_output_then_wrapping(self):
        program,_=compile_program('WRITE(CHR(code())::6::3)',routines="ROUTINE code: INTEGER BEGIN WRITE('inner'::0) RETURN 65 END code")
        program.run()
        self.assertEqual(texts(program),['inner',"   'A'"])
    def test_label_dispatch_preserves_quote_mode(self):
        program,_=compile_program("GO TO done WRITE('skip'::8::2) done:: WRITE('ABC'::8::3)")
        program.run()
        self.assertEqual(texts(program),["   'ABC'"])
    def test_physical_continuation(self): self.assert_output("'ABC' &\n ::8 &\n ::2"," 'ABC'  ")
    def test_quoted_source_report(self):
        _,result=compile_program("WRITE('ABC'::8::2) WRITE('ABC'::8::3)")
        self.assertEqual([s['format_specifiers'] for s in result.report['writes']],[[8,2],[8,3]])
        self.assertEqual([s['alignment'] for s in result.report['writes']],['left','right'])
        self.assertTrue(all(s['quoted'] and s['width_policy']=='fixed' for s in result.report['writes']))
        self.assertFalse(result.report['write_policy']['controller_validated'])
    def test_generated_example(self):
        result=translate((ROOT/'examples/string_write_quotes.kl').read_text())
        namespace={'__name__':'example_test'}
        exec(result.python_source,namespace)
        program=namespace['Program']()
        self.assertEqual(program.run(),dict(ORIGINAL='kept',PACKET=dict(LABEL='robot'),WORDS=['left','right'],EMITTED=11,COUNTER_CLEARED=True))
        self.assertEqual(texts(program),[" 'ABC'  ","   'ABC'",'ABC','ABC'," 'ok'   ","   'robot'"," 'left' "," ''","   'A'","   'B'",'done'])


class WriteWidthFallbackTests(unittest.TestCase):
    def assert_fallback(self,expression,expected):
        observed=[]
        program,result=compile_program(f'WRITE({expression})',write=observed.append)
        program.run()
        self.assertEqual((texts(program),observed),([expected],[expected]))
        self.assertEqual(result.report['writes'][0]['width_policy'],'contents_length')
        return result
    def test_zero_default(self): self.assert_fallback("'ABC'::0",'ABC')
    def test_zero_left(self): self.assert_fallback("'ABC'::0::0",'ABC')
    def test_zero_right(self): self.assert_fallback("'ABC'::0::1",'ABC')
    def test_255_default(self): self.assert_fallback("'ABC'::255",'ABC')
    def test_255_left(self): self.assert_fallback("'ABC'::255::0",'ABC')
    def test_255_right(self): self.assert_fallback("'ABC'::255::1",'ABC')
    def test_256(self): self.assert_fallback("'ABC'::256",'ABC')
    def test_maximum_integer_no_huge_padding(self): self.assert_fallback("'ABC'::2147483647::1",'ABC')
    def test_empty_zero(self): self.assert_fallback("''::0",'')
    def test_empty_255(self): self.assert_fallback("''::255::1",'')
    def test_existing_blanks_preserved(self): self.assert_fallback("' A '::0::1",' A ')
    def test_apostrophe_unquoted_is_retained(self): self.assert_fallback('CHR(39)::0',"'")
    def test_control_character_preserved(self): self.assert_fallback('CHR(13)::255','\r')
    def test_width_fallback_uses_current_contents(self):
        program,_=compile_program("text='A' WRITE(text::0) text='ABCDE' WRITE(text::255::1)")
        self.assertEqual(program.run()['TEXT'],'ABCDE')
        self.assertEqual(texts(program),['A','ABCDE'])
    def test_maximum_input_contents(self):
        program,_=compile_program("text='"+'a'*127+"' WRITE((text+text)::255)",declarations='text: STRING[127]')
        program.run()
        self.assertEqual(texts(program),['a'*254])
    def test_runtime_width_fallback(self):
        state=rt.State({}, {})
        state.write_string('ABC',7,width=0,alignment=1)
        state.write_string('DEF',8,width=2147483647)
        self.assertEqual([r['text'] for r in state.write_requests],['ABC','DEF'])
    def test_format_report_keeps_requested_width(self):
        result=self.assert_fallback("'ABC'::2147483647::1",'ABC')
        self.assertEqual(result.report['writes'][0]['format_width'],2147483647)
        self.assertEqual(result.report['writes'][0]['format_specifiers'],[2147483647,1])


class QuotedWriteGuardTests(unittest.TestCase):
    def reject(self,expression):
        with self.assertRaises(TranslationError) as caught: compile_program(f'WRITE({expression})')
        self.assertEqual(caught.exception.code,'E_WRITE_FORMAT')
    def assert_runtime_guard(self,expression,message):
        observed=[]
        program,_=compile_program(f'WRITE({expression})',write=observed.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError,message): program.run()
        self.assertEqual((texts(program),observed),([],[]))
    def test_quoted_zero_left(self): self.reject("'ABC'::0::2")
    def test_quoted_zero_right(self): self.reject("'ABC'::0::3")
    def test_quoted_255_left(self): self.reject("'ABC'::255::2")
    def test_quoted_255_right(self): self.reject("'ABC'::255::3")
    def test_quoted_maxint(self): self.reject("'ABC'::2147483647::2")
    def test_invalid_mode(self): self.reject("'ABC'::8::4")
    def test_oversized_width_token_has_source_diagnostic(self): self.reject("'ABC'::"+'9'*10000)
    def test_oversized_mode_token_has_source_diagnostic(self): self.reject("'ABC'::8::"+'9'*10000)
    def test_signed_width_remains_blocked(self): self.reject("'ABC'::-1::2")
    def test_truncation_example_is_guarded(self): self.assert_runtime_guard("'ABC'::4::2",'truncation')
    def test_one_character_too_narrow(self): self.assert_runtime_guard("'ABC'::5::2",'truncation')
    def test_right_quoted_too_narrow(self): self.assert_runtime_guard("'ABC'::5::3",'truncation')
    def test_empty_width_one(self): self.assert_runtime_guard("''::1::2",'truncation')
    def test_empty_width_two(self): self.assert_runtime_guard("''::2::3",'truncation')
    def test_embedded_apostrophe_left(self): self.assert_runtime_guard("('A'+CHR(39)+'B')::8::2",'apostrophes')
    def test_embedded_apostrophe_right(self): self.assert_runtime_guard("('A'+CHR(39)+'B')::8::3",'apostrophes')
    def test_unknown_contents(self): self.assert_runtime_guard('text::8::2','uninitialized')
    def test_input_limit_still_precedes_truncation(self):
        program,_=compile_program("text='"+'a'*16+"' WRITE("+'+'.join(['text']*16)+'::254::2)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'254 characters'): program.run()
        self.assertEqual(program.write_requests,())
    def test_max_width_cannot_fit_252_contents(self):
        program,_=compile_program("part='"+'a'*126+"' WRITE((part+part)::254::2)",declarations='part: STRING[126]')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'truncation'): program.run()
        self.assertEqual(program.write_requests,())
    def test_runtime_quoted_fallback_guard(self):
        state=rt.State({}, {})
        for width in (0,255,2147483647):
            with self.subTest(width=width),self.assertRaisesRegex(rt.KarelRuntimeError,'fallback'): state.write_string('ABC',7,width=width,alignment=2)
        self.assertEqual(state.write_requests,[])
    def test_runtime_quoted_guard_source_line(self):
        state=rt.State({}, {})
        with self.assertRaises(rt.KarelRuntimeError) as caught: state.write_string('ABC',17,width=5,alignment=2)
        self.assertEqual(caught.exception.line,17)
    def test_failed_format_unwinds_and_preserves_prior_request(self):
        observed=[]
        program,_=compile_program("WRITE('ready'::0) emit('ABC')",routines='ROUTINE emit(p: STRING) BEGIN WRITE(p::4::2) END emit',write=observed.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'truncation'): program.run()
        self.assertEqual((texts(program),observed),(['ready'],['ready']))
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_callback_failure_preserves_formatted_request(self):
        observed=[]
        def fail(value): observed.append(value); raise OSError('sink failed')
        program,_=compile_program("emit('ABC')",routines='ROUTINE emit(p: STRING) BEGIN WRITE(p::8::3) END emit',write=fail)
        with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
        self.assertIsInstance(caught.exception.__cause__,OSError)
        self.assertEqual((texts(program),observed),(["   'ABC'"],["   'ABC'"]))
        self.assertEqual(program.write_requests[0]['adapter_outcome'],'callback_failed')
        self.assertEqual(program._state.local_frames,[])
    def test_quoted_effect_inside_operator_remains_blocked(self):
        with self.assertRaises(TranslationError) as caught: compile_program('x=f()+1',routines="ROUTINE f: INTEGER BEGIN WRITE('ABC'::8::2) RETURN 1 END f")
        self.assertEqual(caught.exception.code,'E_EVALUATION_ORDER')
    def test_fallback_effect_inside_operator_remains_blocked(self):
        with self.assertRaises(TranslationError) as caught: compile_program('x=f()+1',routines="ROUTINE f: INTEGER BEGIN WRITE('ABC'::0) RETURN 1 END f")
        self.assertEqual(caught.exception.code,'E_EVALUATION_ORDER')
    def test_non_ascii_before_quote_wrapping(self):
        state=rt.State({}, {})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ASCII'): state.write_string('\u00e9',7,width=8,alignment=2)
        self.assertEqual(state.write_requests,[])


class QuotedWriteCLITests(unittest.TestCase):
    def test_cli_positive_quoted_and_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            source=target/'source.kl'
            source.write_text("PROGRAM T\nBEGIN WRITE('ABC'::8::2) WRITE('ABC'::0) END T")
            process=subprocess.run([sys.executable,'-m','karel2py',str(source),'-o',str(target/'converted.py'),'--report',str(target/'report.json')],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            sites=json.loads((target/'report.json').read_text())['writes']
            self.assertEqual([(s['quoted'],s['width_policy']) for s in sites],[(True,'fixed'),(False,'contents_length')])
            namespace={'__name__':'cli_test'}
            exec((target/'converted.py').read_text(),namespace)
            program=namespace['Program']()
            program.run()
            self.assertEqual(texts(program),[" 'ABC'  ",'ABC'])
    def test_cli_quoted_zero_uses_pythonic_natural_width(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            source=target/'source.kl'
            source.write_text("PROGRAM T\nBEGIN WRITE('ABC'::0::2) END T")
            process=subprocess.run([sys.executable,'-m','karel2py',str(source),'-o',str(target/'converted.py'),'--report',str(target/'report.json')],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            site=json.loads((target/'report.json').read_text())['writes'][0]
            self.assertEqual((site['quoted'],site['width_policy']),(True,'contents_length'))
            namespace={'__name__':'cli_pythonic_quote_test'}
            exec((target/'converted.py').read_text(),namespace)
            program=namespace['Program']()
            program.run()
            self.assertEqual(texts(program),[" 'ABC'"])


if __name__ == '__main__': unittest.main()
