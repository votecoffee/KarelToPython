"""Manual STRING format examples, exact spaces, boundaries and failure guards."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import runtime as rt
from tests.legacy_numeric_support import translate
from karel2py.lexer import TranslationError


ROOT = Path(__file__).resolve().parents[1]


def compile_program(body, *, prefix='', declarations='text: STRING[16]\nx: INTEGER', routines='', write=None):
    source=f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result=translate(source, filename='write_formats.kl')
    namespace={'__name__':'format_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](write=write), result


def texts(program): return [request['text'] for request in program.write_requests]


class WriteFormatBehaviorTests(unittest.TestCase):
    def assert_output(self, expression, expected):
        observed=[]
        program, result=compile_program(f'WRITE({expression})', write=observed.append)
        program.run()
        self.assertEqual(texts(program), [expected])
        self.assertEqual(observed, [expected])
        self.assertEqual(program.write_requests[0]['adapter_outcome'], 'callback_completed')
        return result
    def test_manual_no_format(self): self.assert_output("'ABC'", 'ABC')
    def test_manual_right_truncation(self): self.assert_output("'ABC'::2", 'AB')
    def test_manual_left_default(self): self.assert_output("'ABC'::8", 'ABC     ')
    def test_manual_left_explicit(self): self.assert_output("'ABC'::8::0", 'ABC     ')
    def test_manual_right_explicit(self): self.assert_output("'ABC'::8::1", '     ABC')
    def test_width_one(self): self.assert_output("'ABC'::1", 'A')
    def test_same_width_left(self): self.assert_output("'ABC'::3::0", 'ABC')
    def test_same_width_right(self): self.assert_output("'ABC'::3::1", 'ABC')
    def test_truncation_stays_on_right_with_right_alignment(self): self.assert_output("'ABC'::2::1", 'AB')
    def test_maximum_width_left(self): self.assert_output("'ABC'::254", 'ABC'+' '*251)
    def test_maximum_width_right(self): self.assert_output("'ABC'::254::1", ' '*251+'ABC')
    def test_empty_left(self): self.assert_output("''::3", '   ')
    def test_empty_right(self): self.assert_output("''::3::1", '   ')
    def test_empty_width_one(self): self.assert_output("''::1", ' ')
    def test_existing_blanks_left(self): self.assert_output("' A '::5", ' A   ')
    def test_existing_blanks_right(self): self.assert_output("' A '::5::1", '   A ')
    def test_control_character_is_retained(self): self.assert_output('CHR(13)::3', '\r  ')
    def test_concat_is_formatted_as_one_value(self): self.assert_output("('AB'+'C')::5::1", '  ABC')
    def test_format_integer_leading_zeros(self): self.assert_output("'ABC'::008::01", '     ABC')
    def test_largest_input_width(self):
        program,_=compile_program("text='"+'a'*127+"' WRITE((text+text)::254)", declarations='text: STRING[127]')
        program.run()
        self.assertEqual(texts(program), ['a'*254])
    def test_format_does_not_change_stored_string(self):
        program,_=compile_program("text='ABC' WRITE(text::2) WRITE(text::8::1)")
        self.assertEqual(program.run()['TEXT'], 'ABC')
        self.assertEqual(texts(program), ['AB','     ABC'])
    def test_local_constant_string(self):
        program,_=compile_program('emit', routines="ROUTINE emit CONST C='ABC' BEGIN WRITE(C::8) END emit")
        program.run()
        self.assertEqual(texts(program), ['ABC     '])
    def test_string_value_formal_stays_read_only(self):
        program,result=compile_program("emit('ABC')", routines='ROUTINE emit(p: STRING) BEGIN WRITE(p::8::1) END emit')
        program.run()
        self.assertEqual(texts(program), ['     ABC'])
        self.assertEqual(result.report['routine_effects']['EMIT']['potential_parameter_writes'], [])
    def test_structure_using_field(self):
        program,_=compile_program("packet.label='ABC' USING packet DO WRITE(label::5) ENDUSING", prefix='TYPE p=STRUCTURE label: STRING[8] ENDSTRUCTURE', declarations='packet: p')
        program.run()
        self.assertEqual(texts(program), ['ABC  '])
    def test_array_element(self):
        program,_=compile_program("words[2]='ABC' WRITE(words[2]::5::1)", declarations='words: ARRAY[2] OF STRING[8]')
        program.run()
        self.assertEqual(texts(program), ['  ABC'])
    def test_argument_evaluated_once(self):
        program,_=compile_program('x=0 WRITE(CHR(next_code())::3)', routines='ROUTINE next_code: INTEGER BEGIN x=x+1 RETURN 64+x END next_code')
        self.assertEqual(program.run()['X'], 1)
        self.assertEqual(texts(program), ['A  '])
    def test_nested_output_before_formatted_outer(self):
        program,_=compile_program('WRITE(CHR(code())::3::1)', routines="ROUTINE code: INTEGER BEGIN WRITE('inner'::7) RETURN 65 END code")
        program.run()
        self.assertEqual(texts(program), ['inner  ','  A'])
    def test_continued_format_physical_positions(self):
        program,result=compile_program("WRITE('ABC' &\n ::8 &\n ::1)")
        program.run()
        self.assertEqual(texts(program), ['     ABC'])
        self.assertEqual(program.write_requests[0]['line'], result.report['writes'][0]['line'])
        self.assertEqual(len(result.report['continuations']), 2)
    def test_format_report(self):
        result=self.assert_output("'ABC'::8::1", '     ABC')
        site=result.report['writes'][0]
        self.assertEqual(site['format_specifiers'], [8,1])
        self.assertEqual((site['format_width'],site['alignment'],site['quoted']), (8,'right',False))
        self.assertFalse(result.report['write_policy']['controller_validated'])
    def test_default_and_implicit_alignment_report(self):
        _,result=compile_program("WRITE('ABC') WRITE('ABC'::8) WRITE('ABC'::8::0)")
        self.assertEqual([site['format_specifiers'] for site in result.report['writes']], [[],[8],[8,0]])
        self.assertEqual([site['format_width'] for site in result.report['writes']], [None,8,8])
    def test_recursive_effect_report(self):
        routines="ROUTINE a(n: INTEGER) BEGIN b(n) END a\nROUTINE b(n: INTEGER) BEGIN IF n>0 THEN a(n-1) ELSE WRITE('end'::5) ENDIF END b"
        program,result=compile_program('a(2)', routines=routines)
        program.run()
        self.assertEqual(texts(program), ['end  '])
        for name in ('A','B'): self.assertTrue(result.report['routine_effects'][name]['potential_output_requests'])
    def test_generated_example(self):
        result=translate((ROOT/'examples/string_write_formats.kl').read_text())
        namespace={'__name__':'example_test'}
        exec(result.python_source,namespace)
        program=namespace['Program']()
        self.assertEqual(program.run(), dict(PACKET=dict(LABEL='robot'),WORDS=['left','right'],KEPT='ABC',EMITTED=11,COUNTER_CLEARED=True))
        self.assertEqual(texts(program), ['AB','ABC     ','ABC     ','     ABC','      ok','robot  ','   right','   ','A  ','B  ','  done'])


class WriteFormatRejectionTests(unittest.TestCase):
    def reject(self, expression, code='E_WRITE_FORMAT', **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(f'WRITE({expression})', **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
    def test_quoted_zero_width_stays_blocked(self): self.reject("'ABC'::0::2")
    def test_width_over_integer_range(self): self.reject("'ABC'::2147483648")
    def test_negative_width(self): self.reject("'ABC'::-1")
    def test_signed_positive_width(self): self.reject("'ABC'::+8")
    def test_variable_width(self): self.reject("'ABC'::x")
    def test_constant_width(self): self.reject("'ABC'::W", prefix='CONST W=8')
    def test_predefined_width(self): self.reject("'ABC'::MAXINT")
    def test_grouped_width(self): self.reject("'ABC'::(8)")
    def test_real_width(self): self.reject("'ABC'::8.0")
    def test_boolean_width(self): self.reject("'ABC'::ON")
    def test_expression_width(self): self.reject("'ABC'::8+1")
    def test_function_width(self): self.reject("'ABC'::f()", routines='ROUTINE f: INTEGER BEGIN RETURN 8 END f')
    def test_missing_width(self): self.reject("'ABC'::")
    def test_missing_alignment(self): self.reject("'ABC'::8::")
    def test_left_quoted_fallback(self): self.reject("'ABC'::0::2")
    def test_right_quoted_fallback(self): self.reject("'ABC'::255::3")
    def test_unknown_alignment(self): self.reject("'ABC'::8::4")
    def test_negative_alignment(self): self.reject("'ABC'::8::-1")
    def test_boolean_alignment(self): self.reject("'ABC'::8::OFF")
    def test_real_alignment(self): self.reject("'ABC'::8::1.0")
    def test_variable_alignment(self): self.reject("'ABC'::8::x")
    def test_constant_alignment(self): self.reject("'ABC'::8::A", prefix='CONST A=1')
    def test_expression_alignment(self): self.reject("'ABC'::8::1+0")
    def test_third_specifier(self): self.reject("'ABC'::8::1::0")
    def test_single_colon(self): self.reject("'ABC':8", 'E_WRITE_ITEM')
    def test_multiple_formatted_items(self): self.reject("'ABC'::8,'DEF'::8", 'E_WRITE_ITEM')
    def test_cr_after_format(self): self.reject("'ABC'::8,CR", 'E_WRITE_ITEM')
    def test_integer_data(self): self.reject('1::8', 'E_WRITE_FORMAT')
    def test_real_data(self): self.reject('1.5::8', 'E_TYPE')
    def test_boolean_formatted_data(self): self.reject('ON::8', 'E_WRITE_FORMAT')
    def test_whole_array(self): self.reject('words::8', 'E_TYPE', declarations='words: ARRAY[2] OF STRING[8]')
    def test_formatted_function_effect_inside_operator(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('x=f()+1', routines="ROUTINE f: INTEGER BEGIN WRITE('ABC'::8) RETURN 1 END f")
        self.assertEqual(caught.exception.code, 'E_EVALUATION_ORDER')
    def test_formatted_function_effect_indexed_assignment(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('numbers[1]=f()', routines="ROUTINE f: INTEGER BEGIN WRITE('ABC'::8) RETURN 1 END f", declarations='numbers: ARRAY[2] OF INTEGER')
        self.assertEqual(caught.exception.code, 'E_EVALUATION_ORDER')
    def test_rejection_column_points_to_bad_format_literal(self):
        with self.assertRaises(TranslationError) as caught: compile_program("WRITE('ABC' &\n ::8 &\n ::4)")
        self.assertEqual((caught.exception.code,caught.exception.token.line,caught.exception.token.column), ('E_WRITE_FORMAT',9,4))


class WriteFormatFailureTests(unittest.TestCase):
    def test_unknown_contents_fail_before_padding_or_callback(self):
        observed=[]
        program,_=compile_program('WRITE(text::8)', write=observed.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
        self.assertEqual((texts(program),observed), ([],[]))
    def test_overlong_value_cannot_be_hidden_by_truncation(self):
        observed=[]
        program,_=compile_program("text='"+'a'*16+"' WRITE("+'+'.join(['text']*16)+'::2)', write=observed.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'254 characters'): program.run()
        self.assertEqual((texts(program),observed), ([],[]))
    def test_non_ascii_cannot_be_hidden_by_truncation(self):
        state=rt.State({}, {})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ASCII'): state.write_string('A\u00e9',7,width=1)
        self.assertEqual(state.write_requests, [])
    def test_callback_failure_preserves_formatted_trace_and_unwinds(self):
        observed=[]
        def fail(value): observed.append(value); raise OSError('sink failed')
        program,_=compile_program("emit('ABC')", routines='ROUTINE emit(p: STRING) BEGIN WRITE(p::8::1) END emit', write=fail)
        with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertEqual(texts(program), ['     ABC'])
        self.assertEqual(observed, ['     ABC'])
        self.assertEqual(program.write_requests[0]['adapter_outcome'], 'callback_failed')
        self.assertEqual(program._state.local_frames, [])
    def test_runtime_width_guards_before_request(self):
        observed=[]
        state=rt.State({}, {},write=observed.append)
        for width in (False,True,-1,2147483648,8.0,'8'):
            with self.subTest(width=width),self.assertRaises(rt.KarelRuntimeError): state.write_string('ABC',7,width=width)
        self.assertEqual((state.write_requests,observed), ([],[]))
    def test_runtime_alignment_guards_before_request(self):
        state=rt.State({}, {})
        for alignment in (False,True,-1,4,1.0,'1',None):
            with self.subTest(alignment=alignment),self.assertRaises(rt.KarelRuntimeError): state.write_string('ABC',7,width=8,alignment=alignment)
        self.assertEqual(state.write_requests, [])
    def test_runtime_alignment_without_width_rejected(self):
        state=rt.State({}, {})
        with self.assertRaises(rt.KarelRuntimeError): state.write_string('ABC',7,alignment=1)
        self.assertEqual(state.write_requests, [])
    def test_runtime_error_retains_source_line(self):
        state=rt.State({}, {})
        with self.assertRaises(rt.KarelRuntimeError) as caught: state.write_string('ABC',17,width=-1)
        self.assertEqual(caught.exception.line, 17)
    def test_repeated_run_resets_formatted_trace(self):
        program,_=compile_program("WRITE('ABC'::8::1)")
        program.run(); program.run()
        self.assertEqual(texts(program), ['     ABC'])


class WriteFormatCLITests(unittest.TestCase):
    def test_cli_writes_report_and_module_with_exact_spaces(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            source=target/'source.kl'
            source.write_text("PROGRAM T\nBEGIN WRITE('ABC'::8::1) END T")
            process=subprocess.run([sys.executable,'-m','karel2py',str(source),'-o',str(target/'converted.py'),'--report',str(target/'report.json')],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            report=json.loads((target/'report.json').read_text())
            self.assertEqual(report['writes'][0]['format_specifiers'], [8,1])
            namespace={'__name__':'cli_test'}
            exec((target/'converted.py').read_text(),namespace)
            program=namespace['Program']()
            program.run()
            self.assertEqual(texts(program), ['     ABC'])
    def test_cli_rejects_unknown_format_without_module(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            source=target/'source.kl'
            source.write_text("PROGRAM T\nBEGIN WRITE('ABC'::8::4) END T")
            process=subprocess.run([sys.executable,'-m','karel2py',str(source),'-o',str(target/'converted.py'),'--report',str(target/'report.json')],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(process.returncode,2,process.stderr)
            self.assertFalse((target/'converted.py').exists())
            self.assertEqual(json.loads((target/'report.json').read_text())['diagnostics'][0]['code'], 'E_WRITE_FORMAT')


if __name__ == '__main__': unittest.main()
