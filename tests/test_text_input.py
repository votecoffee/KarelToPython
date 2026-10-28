"""Line-oriented Pythonic text input, CR controls and explicit script adapters."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.test_pythonic_read import compile_program


def request(*specs, breaks=()):
    result=dict(line=17,targets=[dict(type=spec[0],type_spec=spec) for spec in specs])
    if breaks: result['line_breaks']=list(breaks)
    return result


def execute(body, text, **options):
    reader=rt.TextInput(text)
    program,result=compile_program(body,read=reader,**options)
    return program.run(),reader,program,result


class TextValueTests(unittest.TestCase):
    def test_signed_decimal_integers(self):
        state,_,_,_=execute('READ(x,y)','+7 -8')
        self.assertEqual((state['X'],state['Y']),(7,-8))
    def test_python_integer_underscores(self): self.assertEqual(execute('READ(x)','1_024')[0]['X'],1024)
    def test_decimal_base_only(self):
        with self.assertRaises(rt.KarelRuntimeError): execute('READ(x)','0x10')
    def test_fractional_and_exponent_reals(self): self.assertEqual(execute('READ(r)','-1.25e2')[0]['R'],-125.0)
    def test_real_integer_text(self): self.assertEqual(execute('READ(r)','7')[0]['R'],7.0)
    def test_python_float_underscores(self): self.assertEqual(execute('READ(r)','1_000.25')[0]['R'],1000.25)
    def test_boolean_spellings(self):
        for token,expected in [('true',True),('FALSE',False),('On',True),('off',False),('T',True),('f',False),('1',True),('0',False)]:
            with self.subTest(token=token): self.assertEqual(execute('READ(flag)',token)[0]['FLAG'],expected)
    def test_invalid_boolean_token(self):
        with self.assertRaises(rt.KarelRuntimeError): execute('READ(flag)','maybe')
    def test_numeric_whitespace_and_blank_lines(self):
        state,_,_,_=execute('READ(x,y)',' \t\n\n7\v\f 8')
        self.assertEqual((state['X'],state['Y']),(7,8))
    def test_string_preserves_leading_spaces(self): self.assertEqual(execute('READ(text)',' abcdef')[0]['TEXT'],' abc')
    def test_string_remainder_after_numeric(self):
        state,_,_,_=execute('READ(x,text)','7 label')
        self.assertEqual((state['X'],state['TEXT']),(7,' lab'))
    def test_string_after_numeric_at_line_end(self):
        self.assertEqual(execute('READ(x,text)','7\nword\n')[0]['TEXT'],'word')
    def test_successive_strings_advance_completed_lines(self):
        self.assertEqual(execute('READ(text) READ(text)','first\nnext\n')[0]['TEXT'],'next')
    def test_empty_line_is_initialized_string(self): self.assertEqual(execute('READ(text)','\n')[0]['TEXT'],'')
    def test_string_after_number_can_be_remaining_spaces(self):
        self.assertEqual(execute('READ(x,text)','7  \n')[0]['TEXT'],'  ')
    def test_byte_and_short_input(self):
        state,_,_,_=execute('READ(a[1],b[1]) flag=UNINIT(b[1])','255 32767',
                            declarations='a: ARRAY[1] OF BYTE b: ARRAY[1] OF SHORT flag: BOOLEAN')
        self.assertEqual(state['A'],[255]); self.assertTrue(state['FLAG'])
    def test_string_alias_capacity(self):
        state,_,_,_=execute('READ(value)','abcdef',types='TYPE text_t=STRING[3]',declarations='value: text_t')
        self.assertEqual(state['VALUE'],'abc')
    def test_input_constructor_rejects_nonascii(self):
        with self.assertRaisesRegex(ValueError,'ASCII'): rt.TextInput('caf\u00e9')
    def test_input_constructor_rejects_nonstring(self):
        with self.assertRaises(ValueError): rt.TextInput(b'7')


class TextLineAndCRTests(unittest.TestCase):
    def test_cr_discards_numeric_line_remainder(self):
        state,_,_,_=execute('READ(x,CR,y)','7 ignored\n8')
        self.assertEqual((state['X'],state['Y']),(7,8))
    def test_cr_after_string_does_not_discard_next_line(self):
        self.assertEqual(execute('READ(text,CR) READ(x)','abc\n7')[0]['X'],7)
    def test_leading_cr(self): self.assertEqual(execute('READ(CR,x)','ignored\n7')[0]['X'],7)
    def test_repeated_cr(self): self.assertEqual(execute('READ(CR,CR,x)','first\nsecond\n7')[0]['X'],7)
    def test_cr_only_request(self):
        _,reader,program,_=execute('READ(CR)','ignored\n')
        self.assertEqual(reader.position,dict(line=2,column=1,eof=True))
        self.assertEqual(program.read_requests[0]['targets'],[])
        self.assertEqual(program.read_requests[0]['line_breaks'],[0])
    def test_cr_finishes_unterminated_numeric_line(self):
        state,reader,_,_=execute('READ(x,CR)','7')
        self.assertEqual(state['X'],7)
        self.assertEqual(reader.position,dict(line=1,column=2,eof=True))
    def test_cr_finishes_unterminated_string_line(self): self.assertEqual(execute('READ(text,CR)','abc')[0]['TEXT'],'abc')
    def test_cr_at_initial_eof_fails(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'end of input'): execute('READ(CR)','')
    def test_cr_empty_line_then_value(self): self.assertEqual(execute('READ(CR,x)','\n7')[0]['X'],7)
    def test_newline_forms(self):
        for ending in ('\n','\r\n','\r'):
            with self.subTest(ending=repr(ending)):
                state,reader,_,_=execute('READ(x,CR) READ(y,CR)','7'+ending+'8'+ending)
                self.assertEqual((state['X'],state['Y'],reader.position),(7,8,dict(line=3,column=1,eof=True)))
    def test_empty_input_is_not_an_empty_line(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'end of input'): execute('READ(text)','')
    def test_final_newline_does_not_invent_another_line(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'end of input'): execute('READ(text) READ(text)','abc\n')
    def test_final_blank_line_is_real_input(self): self.assertEqual(execute('READ(text) READ(text)','abc\n\n')[0]['TEXT'],'')
    def test_position_is_defensive(self):
        reader=rt.TextInput('7'); reader.position['line']=99
        self.assertEqual(reader.position,dict(line=1,column=1,eof=False))
    def test_unterminated_position_after_token(self):
        reader=rt.TextInput('7'); reader(request(rt.INTEGER))
        self.assertEqual(reader.position,dict(line=1,column=2,eof=True))
    def test_input_error_position_counts_crlf_as_one_line(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'input line 2, column 3'):
            execute('READ(x)','\r\n  bad')
    def test_typed_callback_receives_cr_without_extra_values(self):
        program,_=compile_program('READ(x,CR,y)',batches=[[7,8]])
        self.assertEqual(program.run()['Y'],8)
        self.assertEqual(program.read_requests[0]['line_breaks'],[1])
    def test_typed_cr_only_uses_empty_batch(self):
        program,_=compile_program('READ(CR)',batches=[[]])
        program.run(); self.assertEqual(program.read_requests[0]['adapter_outcome'],'callback_completed')


class TextFailureAndEffectTests(unittest.TestCase):
    def test_batch_failure_performs_no_response_assignment(self):
        reader=rt.TextInput('7 bad 9'); program,_=compile_program('x=1 y=2 READ(x,y)',read=reader)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'invalid INTEGER'): program.run()
        self.assertEqual((program.snapshot()['X'],program.snapshot()['Y']),(1,2))
        self.assertEqual(reader(request(rt.INTEGER)),[9])
    def test_failed_token_is_consumed(self):
        reader=rt.TextInput('bad 7')
        with self.assertRaises(rt.KarelRuntimeError): reader(request(rt.INTEGER))
        self.assertEqual(reader.position,dict(line=1,column=4,eof=False))
    def test_integer_range_checked_before_later_field_consumption(self):
        reader=rt.TextInput('2147483647 7')
        with self.assertRaises(rt.KarelRuntimeError): reader(request(rt.INTEGER,rt.INTEGER))
        self.assertEqual(reader(request(rt.INTEGER)),[7])
    def test_nonfinite_real_is_rejected(self):
        for token in ('nan','inf','1e9999'):
            with self.subTest(token=token),self.assertRaises(rt.KarelRuntimeError): execute('READ(r)',token)
    def test_oversize_string_before_capacity_truncation(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'invalid STRING'): execute('READ(text)','x'*255)
    def test_fractional_integer_is_not_rounded(self):
        with self.assertRaises(rt.KarelRuntimeError): execute('READ(x)','7.5')
    def test_eof_during_batch_retains_destinations(self):
        reader=rt.TextInput('7'); program,_=compile_program('x=1 y=2 READ(x,y)',read=reader)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'end of input'): program.run()
        self.assertEqual((program.snapshot()['X'],program.snapshot()['Y']),(1,2))
    def test_response_observation_has_no_input_values(self):
        _,_,program,_=execute('READ(text)','hidden')
        self.assertNotIn('hidden',json.dumps(program.read_requests))
        self.assertEqual(program.read_requests[0]['adapter_outcome'],'callback_completed')
    def test_failure_records_callback_outcome_and_unwinds_frames(self):
        reader=rt.TextInput('bad'); program,_=compile_program('load()',read=reader,
            routines='ROUTINE load VAR local: INTEGER BEGIN READ(local) END load')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.read_requests[0]['adapter_outcome'],'callback_failed')
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))
    def test_cursor_persists_across_warm_runs(self):
        reader=rt.TextInput('7 8'); program,_=compile_program('READ(x)',read=reader)
        self.assertEqual(program.run()['X'],7); self.assertEqual(program.run()['X'],8)
    def test_cr_only_helper_has_input_effect_without_global_write(self):
        _,_,_,result=execute('skip()', '\n', routines='ROUTINE skip BEGIN READ(CR) END skip')
        effects=result.report['routine_effects']['SKIP']
        self.assertTrue(effects['potential_input_requests'])
        self.assertEqual(effects['potential_global_writes'],[])
    def test_for_failure_clears_counter(self):
        reader=rt.TextInput('bad'); program,_=compile_program('FOR i=1 TO 2 DO READ(x,CR) ENDFOR',read=reader)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['I'],{'uninitialized':True})
    def test_numeric_scope_restored_after_direct_adapter_use(self):
        with rt._numeric_scope('strict'):
            self.assertEqual(rt.TextInput('0.1')(request(rt.REAL)),[.1])
            with self.assertRaises(rt.KarelRuntimeError): rt.real(.1)
    def test_invalid_request_metadata_does_not_consume_text(self):
        reader=rt.TextInput('7')
        invalid=[None,{},dict(targets=[]),dict(targets=[dict(type='REAL',type_spec=('INTEGER',))]),
                 dict(targets=[dict(type='STRING',type_spec=('STRING',None))]),request(rt.INTEGER,breaks=(1,0))]
        for value in invalid:
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError): reader(value)
        self.assertEqual(reader(request(rt.INTEGER)),[7])
    def test_cr_limit_includes_markers(self):
        with self.assertRaises(TranslationError) as caught: compile_program('READ('+','.join(['CR']*1025)+')')
        self.assertEqual(caught.exception.code,'E_READ_LIMIT')
    def test_maximum_cr_count(self):
        _,reader,_,_=execute('READ('+','.join(['CR']*1024)+')','\n'*1024)
        self.assertEqual(reader.position,dict(line=1025,column=1,eof=True))


class TextInputScriptTests(unittest.TestCase):
    def run_script(self,body,text,extra=(),*,option='--read-text',bom=False,**options):
        _,result=compile_program(body,**options)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'converted.py'; data=root/'input.txt'; package=root/'karel2py'; package.mkdir()
            for name in ('__init__.py','runtime.py','extended.py','storage.py','kinematics.py','scheduling.py','control.py','clocks.py', 'fileops.py', 'pulses.py', 'configtext.py', 'teach.py', 'xmlio.py', 'devices.py', 'dynamic.py', 'programs.py', 'acquisition.py', 'pc_exchange.py', 'communications.py', 'remote_messages.py', 'archives.py', 'variable_archives.py','diagnostics.py','kcl.py','pendant.py','dictionaries.py','dynamic_display.py','keyboard.py','table_controls.py','forms.py','controller.py', 'vision.py'):
                shutil.copyfile(Path(__file__).resolve().parents[1]/'karel2py'/name,package/name)
            source.write_text(result.python_source,encoding='utf-8')
            data.write_bytes((b'\xef\xbb\xbf' if bom else b'')+text.encode('utf-8'))
            return subprocess.run([sys.executable,str(source),option,str(data),*extra],capture_output=True,text=True)
    def test_script_loads_text(self):
        result=self.run_script('READ(x,CR) READ(y)','7 ignored\n8')
        self.assertEqual(result.returncode,0,result.stderr); self.assertIn("'Y': 8",result.stdout)
    def test_script_loads_utf8_bom(self):
        result=self.run_script('READ(x)','7',bom=True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_script_rejects_nonascii_text(self):
        result=self.run_script('READ(text)','caf\u00e9')
        self.assertEqual(result.returncode,2); self.assertIn('ASCII',result.stderr)
    def test_script_reports_parse_failure(self):
        result=self.run_script('READ(x)','bad')
        self.assertEqual(result.returncode,1); self.assertIn('input line 1, column 1',result.stderr)
    def test_input_options_are_mutually_exclusive(self):
        result=self.run_script('READ(x)','7',extra=('--read-values','unused.json'))
        self.assertEqual(result.returncode,2)
    def test_empty_input_path_is_a_cli_error(self):
        result=self.run_script('READ(x)','7',extra=('--read-values',''),option='--read-values')
        self.assertEqual(result.returncode,2); self.assertIn('Unable to load READ input',result.stderr)
    def test_text_and_joint_context_compose(self):
        result=self.run_script('READ(x) data[1]=5 CNV_REL_JPOS(data,j,status)','7',extra=('--joint-axes','1'),
                               declarations='x,status: INTEGER data: ARRAY[1] OF REAL j: JOINTPOS1')
        self.assertEqual(result.returncode,0,result.stderr); self.assertIn("'STATUS': 0",result.stdout)
    def test_json_batches_remain_supported_with_cr(self):
        result=self.run_script('READ(x,CR) READ(CR)','[[7],[]]',option='--read-values')
        self.assertEqual(result.returncode,0,result.stderr); self.assertIn("'X': 7",result.stdout)


class AuthoredTextInputTests(unittest.TestCase):
    def test_complete_fixtures(self):
        root=Path(__file__).resolve().parents[1]/'examples'; source=root/'pythonic_text_input.kl'
        result=translate(source.read_text(),filename=source.name); namespace={'__name__':'text_fixture'}
        exec(result.python_source,namespace)
        reader=rt.TextInput(source.with_suffix('.input.txt').read_text()); output=[]
        program=namespace['Program'](read=reader,write=output.append)
        self.assertEqual(program.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(output,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual(json.loads(json.dumps(program.read_requests)),json.loads(source.with_suffix('.read.expected.json').read_text()))
        self.assertEqual(reader.position,json.loads(source.with_suffix('.input.expected.json').read_text()))
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))
