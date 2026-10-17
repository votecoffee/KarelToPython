"""Default BOOLEAN WRITE text, strict typing, source contexts and adapter contracts."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError


ROOT=Path(__file__).resolve().parents[1]


def compile_program(body, *, declarations='flag: BOOLEAN\nx: INTEGER', prefix='', routines='', write=None, sleep=None):
    source=f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result=translate(source,filename='boolean_writes.kl')
    namespace={'__name__':'boolean_write_test'}
    exec(result.python_source,namespace)
    return namespace['Program'](write=write,sleep=sleep),result


def texts(program): return [row['text'] for row in program.write_requests]


class BooleanWriteBehaviorTests(unittest.TestCase):
    def test_true_default_recorded_without_stdout(self):
        program,_=compile_program('WRITE(ON)')
        with patch('sys.stdout.write',side_effect=AssertionError('unexpected stdout')): program.run()
        self.assertEqual(texts(program),[' TRUE'])
        self.assertEqual(program.write_requests[0]['adapter_outcome'],'recorded')
    def test_false_default_has_one_blank_and_no_trailing_blank(self):
        program,_=compile_program('WRITE(OFF)')
        program.run()
        self.assertEqual(texts(program),[' FALSE'])
    def test_mixed_string_and_boolean_requests(self):
        observed=[]
        program,_=compile_program("WRITE('ready=') WRITE(ON) WRITE('next=') WRITE(OFF)",write=observed.append)
        program.run()
        self.assertEqual((texts(program),observed),(['ready=',' TRUE','next=',' FALSE'],['ready=',' TRUE','next=',' FALSE']))
        self.assertTrue(all(r['adapter_outcome']=='callback_completed' for r in program.write_requests))
    def test_initialized_variable_is_unchanged(self):
        program,_=compile_program('flag=ON WRITE(flag) WRITE(NOT flag)')
        self.assertTrue(program.run()['FLAG'])
        self.assertEqual(texts(program),[' TRUE',' FALSE'])
    def test_global_constant(self):
        program,_=compile_program('WRITE(C)',prefix='CONST C=ON')
        program.run()
        self.assertEqual(texts(program),[' TRUE'])
    def test_local_constant(self):
        program,_=compile_program('emit',routines='ROUTINE emit CONST C=OFF BEGIN WRITE(C) END emit')
        program.run()
        self.assertEqual(texts(program),[' FALSE'])
    def test_comparison(self):
        program,_=compile_program('WRITE(3<4) WRITE(3=4)')
        program.run()
        self.assertEqual(texts(program),[' TRUE',' FALSE'])
    def test_real_comparison(self):
        program,_=compile_program('WRITE(1.5<2.5)')
        program.run()
        self.assertEqual(texts(program),[' TRUE'])
    def test_string_comparison(self):
        program,_=compile_program("WRITE('same'='same')")
        program.run()
        self.assertEqual(texts(program),[' TRUE'])
    def test_boolean_operators(self):
        program,_=compile_program('WRITE(ON AND OFF) WRITE(ON OR OFF) WRITE(NOT OFF)')
        program.run()
        self.assertEqual(texts(program),[' FALSE',' TRUE',' TRUE'])
    def test_scalar_value_argument(self):
        program,_=compile_program('emit(ON)',routines='ROUTINE emit(p: BOOLEAN) BEGIN WRITE(p) END emit')
        program.run()
        self.assertEqual(texts(program),[' TRUE'])
    def test_scalar_reference_argument(self):
        program,_=compile_program('flag=OFF emit(flag)',routines='ROUTINE emit(p: BOOLEAN) BEGIN WRITE(p) END emit')
        self.assertFalse(program.run()['FLAG'])
        self.assertEqual(texts(program),[' FALSE'])
    def test_field_value(self):
        program,_=compile_program('packet.ready=ON WRITE(packet.ready)',prefix='TYPE p=STRUCTURE ready: BOOLEAN ENDSTRUCTURE',declarations='packet: p')
        program.run()
        self.assertEqual(texts(program),[' TRUE'])
    def test_using_field(self):
        program,_=compile_program('packet.ready=OFF USING packet DO WRITE(ready) ENDUSING',prefix='TYPE p=STRUCTURE ready: BOOLEAN ENDSTRUCTURE',declarations='packet: p')
        program.run()
        self.assertEqual(texts(program),[' FALSE'])
    def test_array_element(self):
        program,_=compile_program('flags[2]=ON WRITE(flags[2])',declarations='flags: ARRAY[2] OF BOOLEAN')
        program.run()
        self.assertEqual(texts(program),[' TRUE'])
    def test_multidimensional_array_element(self):
        program,_=compile_program('flags[1,2]=OFF WRITE(flags[1,2])',declarations='flags: ARRAY[2,2] OF BOOLEAN')
        program.run()
        self.assertEqual(texts(program),[' FALSE'])
    def test_initialization_query_can_be_written(self):
        program,_=compile_program('WRITE(UNINIT(flag)) flag=OFF WRITE(UNINIT(flag))')
        program.run()
        self.assertEqual(texts(program),[' TRUE',' FALSE'])
    def test_boolean_function_evaluated_once(self):
        program,_=compile_program('x=0 WRITE(next_flag())',routines='ROUTINE next_flag: BOOLEAN BEGIN x=x+1 RETURN x=1 END next_flag')
        self.assertEqual(program.run()['X'],1)
        self.assertEqual(texts(program),[' TRUE'])
    def test_nested_output_before_outer_boolean_request(self):
        program,_=compile_program('WRITE(next_flag())',routines='ROUTINE next_flag: BOOLEAN BEGIN WRITE(ON) RETURN OFF END next_flag')
        program.run()
        self.assertEqual(texts(program),[' TRUE',' FALSE'])
    def test_delay_then_boolean_output_order(self):
        observed=[]
        program,_=compile_program('WRITE(next_flag())',routines='ROUTINE next_flag: BOOLEAN BEGIN DELAY 1 RETURN ON END next_flag',sleep=lambda value: observed.append(('sleep',value)),write=lambda value: observed.append(('write',value)))
        program.run()
        self.assertEqual(observed,[('sleep',0.001),('write',' TRUE')])
    def test_select_and_skipped_paths(self):
        program,_=compile_program('IF OFF THEN WRITE(OFF) ELSE WRITE(ON) ENDIF SELECT 1 OF CASE(1): WRITE(OFF) ELSE: WRITE(ON) ENDSELECT')
        program.run()
        self.assertEqual(texts(program),[' TRUE',' FALSE'])
    def test_label_dispatch(self):
        program,_=compile_program('GO TO chosen WRITE(OFF) chosen:: WRITE(ON)')
        program.run()
        self.assertEqual(texts(program),[' TRUE'])
    def test_continuation_preserves_physical_source_line(self):
        program,result=compile_program('WRITE( &\n ON)')
        program.run()
        self.assertEqual(texts(program),[' TRUE'])
        self.assertEqual(program.write_requests[0]['line'],result.report['writes'][0]['line'])
        self.assertEqual(len(result.report['continuations']),1)
    def test_reports_item_type_and_default_policy(self):
        _,result=compile_program("WRITE(ON) WRITE('plain')")
        self.assertEqual([s['data_type'] for s in result.report['writes']],['BOOLEAN','STRING'])
        site=result.report['writes'][0]
        self.assertEqual((site['data_items'],site['format_specifiers'],site['format_width'],site['quoted'],site['width_policy']),(1,[],None,False,'unformatted'))
        self.assertIn('exactly one leading blank',result.report['write_policy']['boolean'])
        self.assertFalse(result.report['write_policy']['controller_validated'])
    def test_transitive_routine_output_effects(self):
        program,result=compile_program('forward(ON)',routines='ROUTINE emit(p: BOOLEAN) BEGIN WRITE(p) END emit\nROUTINE forward(p: BOOLEAN) BEGIN emit(p) END forward')
        program.run()
        self.assertEqual(texts(program),[' TRUE'])
        for name in ('EMIT','FORWARD'):
            self.assertTrue(result.report['routine_effects'][name]['potential_output_requests'])
            self.assertEqual(result.report['routine_effects'][name]['potential_parameter_writes'],[])
    def test_record_is_a_copy_and_per_run(self):
        program,_=compile_program('WRITE(ON)')
        program.run()
        program.write_requests[0]['text']='changed'
        self.assertEqual(texts(program),[' TRUE'])
        program.run()
        self.assertEqual(texts(program),[' TRUE'])
    def test_generated_example(self):
        result=translate((ROOT/'examples/boolean_write_requests.kl').read_text())
        namespace={'__name__':'example_test'}
        exec(result.python_source,namespace)
        program=namespace['Program']()
        self.assertEqual(program.run(),dict(READY=True,PACKET=dict(ENABLED=False,LABEL='ready'),FLAGS=[True,False,True],CHECKS=5,COUNTER_CLEARED=True))
        self.assertEqual(texts(program),['start',' TRUE',' FALSE',' TRUE',' TRUE',' FALSE',' TRUE',' FALSE',' TRUE',' TRUE',' TRUE','done'])


class BooleanWriteGuardTests(unittest.TestCase):
    def reject(self,body,code,**kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**kwargs)
        self.assertEqual(caught.exception.code,code)
    def test_width_format_stays_blocked(self): self.reject('WRITE(ON::8)','E_WRITE_FORMAT')
    def test_width_fallback_stays_blocked(self): self.reject('WRITE(ON::0)','E_WRITE_FORMAT')
    def test_right_alignment_stays_blocked(self): self.reject('WRITE(OFF::8::1)','E_WRITE_FORMAT')
    def test_quote_mode_stays_blocked(self): self.reject('WRITE(ON::8::2)','E_WRITE_FORMAT')
    def test_quote_fallback_has_boolean_diagnostic(self):
        with self.assertRaises(TranslationError) as caught: compile_program('WRITE(ON::0::2)')
        self.assertEqual(caught.exception.code,'E_WRITE_FORMAT')
        self.assertIn('BOOLEAN WRITE',caught.exception.message)
    def test_multiple_data_items_remain_blocked(self): self.reject("WRITE('ready',ON)",'E_WRITE_ITEM')
    def test_reserved_cr_remains_blocked(self): self.reject('WRITE(ON,CR)','E_WRITE_ITEM')
    def test_integer_format_remains_blocked(self): self.reject('WRITE(1::8)','E_WRITE_FORMAT')
    def test_real_output_remains_blocked(self): self.reject('WRITE(1.5)','E_TYPE')
    def test_whole_boolean_array_remains_blocked(self): self.reject('WRITE(flags)','E_TYPE',declarations='flags: ARRAY[2] OF BOOLEAN')
    def test_explicit_device_remains_blocked(self): self.reject('WRITE OUTPUT(ON)','E_WRITE_TARGET')
    def test_boolean_output_function_inside_operator_remains_blocked(self): self.reject('x=f()+1','E_EVALUATION_ORDER',routines='ROUTINE f: INTEGER BEGIN WRITE(ON) RETURN 1 END f')
    def test_boolean_output_function_in_indexed_assignment_remains_blocked(self): self.reject('numbers[1]=f()','E_EVALUATION_ORDER',routines='ROUTINE f: INTEGER BEGIN WRITE(ON) RETURN 1 END f',declarations='numbers: ARRAY[2] OF INTEGER')
    def test_boolean_function_operands_remain_blocked(self): self.reject('WRITE(f() AND ON)','E_EVALUATION_ORDER',routines='ROUTINE f: BOOLEAN BEGIN RETURN ON END f')
    def test_format_diagnostic_points_to_continued_width(self):
        with self.assertRaises(TranslationError) as caught: compile_program('WRITE(ON &\n ::8)')
        self.assertEqual((caught.exception.code,caught.exception.token.line,caught.exception.token.column),('E_WRITE_FORMAT',8,4))
    def test_uninitialized_value_fails_before_callback(self):
        observed=[]
        program,_=compile_program('WRITE(flag)',write=observed.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
        self.assertEqual((texts(program),observed),([],[]))
    def test_uninitialized_element_fails_before_request(self):
        program,_=compile_program('WRITE(flags[2])',declarations='flags: ARRAY[2] OF BOOLEAN')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.write_requests,())
    def test_out_of_bounds_fails_before_request(self):
        program,_=compile_program('WRITE(flags[3])',declarations='flags: ARRAY[2] OF BOOLEAN')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.write_requests,())
    def test_runtime_rejects_python_truthiness(self):
        state=rt.State({}, {})
        for value in (0,1,None,'TRUE',[],{},object(),rt.UNINITIALIZED,rt.UNKNOWN_BYTE):
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError): state.write_boolean(value,17)
        self.assertEqual(state.write_requests,[])
    def test_runtime_error_has_source_line(self):
        state=rt.State({}, {})
        with self.assertRaises(rt.KarelRuntimeError) as caught: state.write_boolean(1,17)
        self.assertEqual(caught.exception.line,17)
    def test_callback_failure_preserves_boolean_text_and_unwinds(self):
        observed=[]
        def fail(value): observed.append(value); raise OSError('sink failed')
        program,_=compile_program('emit(ON)',routines='ROUTINE emit(p: BOOLEAN) BEGIN WRITE(p) END emit',write=fail)
        with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
        self.assertIsInstance(caught.exception.__cause__,OSError)
        self.assertEqual((texts(program),observed),([' TRUE'],[' TRUE']))
        self.assertEqual(program.write_requests[0]['adapter_outcome'],'callback_failed')
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_callback_false_result_is_rejected(self):
        program,_=compile_program('WRITE(OFF)',write=lambda value: False)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'return None'): program.run()
        self.assertEqual(texts(program),[' FALSE'])
        self.assertEqual(program.write_requests[0]['adapter_outcome'],'callback_result_rejected')
    def test_callback_interruption_unwinds(self):
        def interrupt(value): raise KeyboardInterrupt()
        program,_=compile_program('emit(OFF)',routines='ROUTINE emit(p: BOOLEAN) BEGIN WRITE(p) END emit',write=interrupt)
        with self.assertRaises(KeyboardInterrupt): program.run()
        self.assertEqual(program._state.local_frames,[])
        self.assertEqual(program.write_requests[0]['adapter_outcome'],'callback_interrupted')


class BooleanWriteCLITests(unittest.TestCase):
    def test_cli_generates_default_boolean_output(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            source=target/'source.kl'
            source.write_text('PROGRAM T\nBEGIN WRITE(ON) WRITE(OFF) END T')
            process=subprocess.run([sys.executable,'-m','karel2py',str(source),'-o',str(target/'converted.py'),'--report',str(target/'report.json')],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertEqual([s['data_type'] for s in json.loads((target/'report.json').read_text())['writes']],['BOOLEAN','BOOLEAN'])
            namespace={'__name__':'cli_test'}
            exec((target/'converted.py').read_text(),namespace)
            program=namespace['Program']()
            program.run()
            self.assertEqual(texts(program),[' TRUE',' FALSE'])
    def test_cli_rejects_boolean_format_without_module(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            source=target/'source.kl'
            source.write_text('PROGRAM T\nBEGIN WRITE(ON::8) END T')
            process=subprocess.run([sys.executable,'-m','karel2py',str(source),'-o',str(target/'converted.py'),'--report',str(target/'report.json')],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(process.returncode,2,process.stderr)
            self.assertFalse((target/'converted.py').exists())
            self.assertEqual(json.loads((target/'report.json').read_text())['diagnostics'][0]['code'],'E_WRITE_FORMAT')


if __name__ == '__main__': unittest.main()
