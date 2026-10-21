"""Pythonic READ field widths, bases, quoting, ordered effects and guards."""
import json
from pathlib import Path
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.test_pythonic_read import compile_program
from tests.test_text_input import execute, request
from tests import test_text_input as text_tests


class FieldValueTests(unittest.TestCase):
    def test_adjacent_integer_fields(self):
        state,_,_,_=execute('READ(x::3,y::2)','10042')
        self.assertEqual((state['X'],state['Y']),(100,42))
    def test_integer_base(self): self.assertEqual(execute('READ(x::5::2)','10101')[0]['X'],21)
    def test_hexadecimal_lowercase_and_sign(self): self.assertEqual(execute('READ(x::3::16)','-2a')[0]['X'],-42)
    def test_all_integer_bases(self):
        for base in range(2,17):
            with self.subTest(base=base): self.assertEqual(execute(f'READ(x::0::{base})','10')[0]['X'],base)
    def test_zero_base_selects_decimal(self): self.assertEqual(execute('READ(x::0::0)','42')[0]['X'],42)
    def test_python_prefix_and_underscore_for_explicit_base(self): self.assertEqual(execute('READ(x::0::16)','0x2_a')[0]['X'],42)
    def test_fixed_numeric_field_accepts_surrounding_whitespace(self): self.assertEqual(execute('READ(x::4)',' 7  ')[0]['X'],7)
    def test_real_field(self): self.assertEqual(execute('READ(r::6)','1.25e2')[0]['R'],125.0)
    def test_real_second_format_is_evaluated_but_ignored(self): self.assertEqual(execute('READ(r::4::-7)','2.50')[0]['R'],2.5)
    def test_boolean_fixed_field(self): self.assertTrue(execute('READ(flag::4::99)',' ON ')[0]['FLAG'])
    def test_documented_boolean_abbreviations(self):
        for token,expected in [('TRU',True),('tr',True),('FALS',False),('fal',False),('FA',False),('of',False)]:
            with self.subTest(token=token): self.assertEqual(execute('READ(flag)',token)[0]['FLAG'],expected)
    def test_short_field_does_not_cross_line(self):
        reader=rt.TextInput('7\n8')
        p,_=compile_program('READ(x::2)',read=reader)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'incomplete field.*input line 1, column 1'): p.run()
        self.assertEqual(reader(request(rt.INTEGER)),[8])
    def test_short_field_rejects_all_response_stores(self):
        p,_=compile_program('x=1 y=2 READ(x::1,y::3)',read=rt.TextInput('78'))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['X'],p.snapshot()['Y']),(1,2))
    def test_fixed_string_preserves_blanks_and_adjacent_data(self):
        state,_,_,_=execute('READ(text::3,x::2)',' a 42')
        self.assertEqual((state['TEXT'],state['X']),(' a ',42))
    def test_fixed_string_consumes_before_truncation(self):
        state,_,_,_=execute('READ(text::6,x::2)','abcdef42')
        self.assertEqual((state['TEXT'],state['X']),('abcd',42))
    def test_zero_string_width_retains_line_remainder(self): self.assertEqual(execute('READ(text::0::0)',' abc')[0]['TEXT'],' abc')
    def test_maximum_width(self): self.assertEqual(execute('READ(text::254)','x'*254)[0]['TEXT'],'xxxx')
    def test_width_with_cr_discards_only_current_remainder(self):
        state,reader,_,_=execute('READ(x::2,CR,y::2,CR)','42ignored\n19\n')
        self.assertEqual((state['X'],state['Y'],reader.position),(42,19,dict(line=3,column=1,eof=True)))
    def test_byte_and_short_bases(self):
        state,_,_,_=execute('READ(a[1]::2::16,b[1]::4::16) flag=UNINIT(b[1])','FF7FFF',
                            declarations='a: ARRAY[1] OF BYTE b: ARRAY[1] OF SHORT flag: BOOLEAN')
        self.assertEqual(state['A'],[255]); self.assertTrue(state['FLAG'])
    def test_partial_field_retains_cursor(self):
        _,reader,_,_=execute('READ(x::2)','4219')
        self.assertEqual(reader.position,dict(line=1,column=3,eof=False))
        self.assertEqual(reader(request(rt.INTEGER)),[19])
    def test_multiline_formats_and_cr(self):
        self.assertEqual(execute('READ(\nx:: &\n2::16,\nCR,\ny::2\n)','2A ignored\n19')[0]['Y'],19)


class QuotedInputTests(unittest.TestCase):
    def test_quotes_removed(self): self.assertEqual(execute('READ(text::0::2)'," 'abc'")[0]['TEXT'],'abc')
    def test_empty_quoted_string(self): self.assertEqual(execute('READ(text::0::2)',"''")[0]['TEXT'],'')
    def test_doubled_apostrophe(self): self.assertEqual(execute('READ(text::0::2)',"'a''b'")[0]['TEXT'],"a'b")
    def test_quoted_truncation_consumes_complete_field(self):
        state,_,_,_=execute('READ(text::0::2,x)',"'abcdef'42")
        self.assertEqual((state['TEXT'],state['X']),('abcd',42))
    def test_successive_quoted_fields(self): self.assertEqual(execute('READ(text::0::2,text::0::2)',"'abc' 'def'")[0]['TEXT'],'def')
    def test_fixed_quote_field_with_padding(self):
        state,_,_,_=execute('READ(text::7::2,x::2)'," 'abc' 42")
        self.assertEqual((state['TEXT'],state['X']),('abc',42))
    def test_fixed_quote_field_rejects_trailing_data(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'invalid quoted STRING'): execute('READ(text::6::2)',"'abc'x")
    def test_missing_quote(self):
        for text in ('abc',"'abc", "'a''",'   '):
            with self.subTest(text=text),self.assertRaisesRegex(rt.KarelRuntimeError,'invalid quoted STRING'):
                execute('READ(text::0::2)',text)
    def test_quote_failure_consumes_remainder_without_next_line(self):
        reader=rt.TextInput("'bad\n7")
        p,_=compile_program('READ(text::0::2)',read=reader)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(reader.position,dict(line=1,column=5,eof=False))
        self.assertEqual(reader(request(rt.INTEGER)),[7])
    def test_quoted_string_cr_retains_next_line(self): self.assertEqual(execute('READ(text::0::2,CR,x)',"'abc' extra\n7")[0]['X'],7)
    def test_quoted_input_bound_is_decoded_content(self):
        value="'"*254; text="'"+value.replace("'","''")+"'"
        self.assertEqual(execute('READ(text::0::2)',text)[0]['TEXT'],"''''")
    def test_oversized_decoded_string(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'invalid STRING'): execute('READ(text::0::2)',"'"+'x'*255+"'")
    def test_write_read_quoted_roundtrip(self):
        p,_=compile_program("text='a''b' WRITE(text::0::2,CR)"); p.run()
        self.assertEqual(execute('READ(text::0::2,CR)',p.write_requests[0]['text'])[0]['TEXT'],"a'b")


class FormatEffectTests(unittest.TestCase):
    def test_target_width_base_next_target_order(self):
        routines='''ROUTINE first: INTEGER BEGIN total=total*10+1 RETURN 1 END first
ROUTINE width: INTEGER BEGIN total=total*10+2 RETURN 2 END width
ROUTINE radix: INTEGER BEGIN total=total*10+3 RETURN 16 END radix
ROUTINE second: INTEGER BEGIN total=total*10+4 RETURN 2 END second'''
        state,_,_,_=execute('total=0 READ(a[first]::width::radix,a[second])','2A 7',routines=routines)
        self.assertEqual((state['TOTAL'],state['A']),(1234,[42,7]))
    def test_invalid_format_stops_before_later_target_and_callback(self):
        routines='''ROUTINE width: INTEGER BEGIN total=1 RETURN -1 END width
ROUTINE later: INTEGER BEGIN total=2 RETURN 2 END later'''
        p,_=compile_program('total=0 READ(a[1]::width,a[later])',routines=routines,batches=[[7,8]])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'READ width'): p.run()
        self.assertEqual(p.snapshot()['TOTAL'],1); self.assertEqual(p.read_requests,())
    def test_nested_read_in_width(self):
        routines='ROUTINE width: INTEGER VAR n: INTEGER BEGIN READ(n) RETURN n END width'
        p,_=compile_program('READ(x::width)',routines=routines,batches=[[2],[42]])
        self.assertEqual(p.run()['X'],42); self.assertEqual(len(p.read_requests),2)
        self.assertEqual(p.read_requests[1]['targets'][0]['format_specifiers'],(2,))
    def test_string_formal_keeps_concrete_caller_capacity(self):
        state,_,_,_=execute('load(text)', 'abcdef',routines='ROUTINE load(s: STRING) BEGIN READ(s::6) END load')
        self.assertEqual(state['TEXT'],'abcd')
    def test_format_formal_bare_function_resolution(self):
        state,_,_,_=execute('load(2)', '42',routines='ROUTINE load(w: INTEGER) BEGIN READ(x::w) END load')
        self.assertEqual(state['X'],42)
    def test_using_fields_apply_to_target_and_format(self):
        state,_,_,_=execute('p.width=2 USING p DO READ(value::width) ENDUSING','42',
                            types='TYPE packet=STRUCTURE value: INTEGER width: INTEGER ENDSTRUCTURE',declarations='p: packet')
        self.assertEqual(state['P'],dict(VALUE=42,WIDTH=2))
    def test_label_dispatcher(self): self.assertEqual(execute('READ(x::2)','42',labelled=True)[0]['X'],42)
    def test_failed_parse_clears_for_counter_and_frames(self):
        p,_=compile_program('FOR i=1 TO 2 DO load() ENDFOR',read=rt.TextInput('xx'),
                            routines='ROUTINE load VAR n: INTEGER BEGIN READ(n::2) END load')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['I'],{'uninitialized':True})
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
    def test_width_call_writes_are_in_for_effect_analysis(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('FOR i=1 TO 2 DO READ(x::width) ENDFOR',routines='ROUTINE width: INTEGER BEGIN i=1 RETURN 2 END width')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
    def test_formatted_read_marks_formal_writable(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('FOR i=1 TO 2 DO load(i) ENDFOR',routines='ROUTINE load(n: INTEGER) BEGIN READ(n::2) END load')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
    def test_dynamic_formats_are_reported_without_values(self):
        _,_,p,result=execute('y=2 READ(x::y::16)','2A')
        destination=result.report['reads'][0]['destinations'][0]
        self.assertTrue(destination['dynamic_formats'])
        self.assertEqual(destination['format_specifiers'][1],16)
        self.assertEqual(p.read_requests[0]['targets'][0]['format_specifiers'],(2,16))
        json.dumps(result.report); json.dumps(p.read_requests)
    def test_plain_scalar_metadata_stays_compatible_in_mixed_request(self):
        _,_,p,_=execute('READ(x::2,y)','42 7')
        self.assertNotIn('format_specifiers',p.read_requests[0]['targets'][1])
    def test_typed_batches_ignore_text_formats_but_validate_storage(self):
        p,_=compile_program('READ(x::2::16,text::0::2)',batches=[[99,'widget']])
        self.assertEqual((p.run()['X'],p.snapshot()['TEXT']),(99,'widg'))


class FormatGuardTests(unittest.TestCase):
    def test_static_invalid_formats(self):
        for body in ('READ(x::-1)','READ(x::255)','READ(x::0::1)','READ(x::0::17)',
                     'READ(text::0::1)','READ(text::0::3)','READ(CR::2)','READ(x::1::2::3)','READ(x:2)'):
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught: compile_program(body)
            self.assertEqual(caught.exception.code,'E_READ_FORMAT')
    def test_format_type(self):
        for value in ('1.0','ON',"'x'"):
            with self.subTest(value=value),self.assertRaises(TranslationError) as caught: compile_program(f'READ(x::{value})')
            self.assertEqual(caught.exception.code,'E_TYPE')
    def test_runtime_format_domains_checked_before_observation(self):
        for body in ('y=-1 READ(x::y)','y=255 READ(text::y)','y=1 READ(x::0::y)','y=3 READ(text::0::y)'):
            p,_=compile_program(body,batches=[[7]])
            with self.subTest(body=body),self.assertRaises(rt.KarelRuntimeError): p.run()
            self.assertEqual(p.read_requests,())
    def test_invalid_metadata_is_rejected_before_any_consumption(self):
        reader=rt.TextInput('42')
        for formats in (None,[True],[-1],[255],[0,1],[1,2,3]):
            metadata=request(rt.INTEGER); metadata['targets'][0]['format_specifiers']=formats
            with self.subTest(formats=formats),self.assertRaises(rt.KarelRuntimeError): reader(metadata)
        self.assertEqual(reader(request(rt.INTEGER)),[42])
    def test_later_target_metadata_is_checked_before_consumption(self):
        reader=rt.TextInput('42 7'); metadata=request(rt.INTEGER,rt.INTEGER)
        metadata['targets'][1]['format_specifiers']=[-1]
        with self.assertRaises(rt.KarelRuntimeError): reader(metadata)
        self.assertEqual(reader.position,dict(line=1,column=1,eof=False))
    def test_direct_state_requires_one_format_list_per_target(self):
        p,_=compile_program('READ(x)')
        with self.assertRaises(rt.KarelRuntimeError): p._state.read_items([],line_breaks=[0],formats=[[]])
        self.assertEqual(p.read_requests,())
    def test_bad_base_digit_consumes_only_field(self):
        reader=rt.TextInput('ZZ42'); p,_=compile_program('READ(x::2::16)',read=reader)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        metadata=request(rt.INTEGER); metadata['targets'][0]['format_specifiers']=[2]
        self.assertEqual(reader(metadata),[42])
    def test_field_zero_is_default_not_empty_input(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'end of input'): execute('READ(x::0)','')
    def test_counter_destination_stays_protected(self):
        with self.assertRaises(TranslationError) as caught: compile_program('FOR i=1 TO 2 DO READ(i::2) ENDFOR')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')


class FormatScriptTests(unittest.TestCase):
    run_script=text_tests.TextInputScriptTests.run_script
    def test_generated_script_uses_field_formats(self):
        result=self.run_script('READ(x::2::16,text::0::2)',"2A 'abc'")
        self.assertEqual(result.returncode,0,result.stderr); self.assertIn("'X': 42",result.stdout); self.assertIn("'TEXT': 'abc'",result.stdout)
    def test_generated_script_typed_json_still_works(self):
        result=self.run_script('READ(x::2::16)','[[99]]',option='--read-values')
        self.assertEqual(result.returncode,0,result.stderr); self.assertIn("'X': 99",result.stdout)


class AuthoredFormatTests(unittest.TestCase):
    def test_complete_fixtures(self):
        source=Path(__file__).resolve().parents[1]/'examples/pythonic_read_formats.kl'
        result=translate(source.read_text(),filename=source.name); namespace={'__name__':'format_fixture'}
        exec(result.python_source,namespace)
        reader=rt.TextInput(source.with_suffix('.input.txt').read_text()); output=[]
        p=namespace['Program'](read=reader,write=output.append)
        self.assertEqual(p.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(output,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual(json.loads(json.dumps(p.read_requests)),json.loads(source.with_suffix('.read.expected.json').read_text()))
        self.assertEqual(reader.position,json.loads(source.with_suffix('.input.expected.json').read_text()))
