"""Single-STRING output requests, adapter outcomes and effect-order guards."""
from pathlib import Path
import unittest
from unittest.mock import patch

from karel2py import translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


DECLARATIONS = 'text: STRING[16]\nx,y: INTEGER\nflag: BOOLEAN\nwords: ARRAY[2] OF STRING[8]'


def compile_program(body, routines='', declarations=DECLARATIONS, prefix='', write=None, sleep=None):
    source=f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result=translate(source,filename='writes.kl')
    namespace={'__name__':'write_test'}
    exec(result.python_source,namespace)
    return namespace['Program'](write=write,sleep=sleep),result


def texts(program): return [row['text'] for row in program.write_requests]


class WriteBehaviorTests(unittest.TestCase):
    def test_literal_is_recorded_without_stdout(self):
        program,_=compile_program("WRITE('hello')")
        with patch('sys.stdout.write',side_effect=AssertionError('unexpected stdout')): program.run()
        self.assertEqual(texts(program),['hello'])
        self.assertEqual(program.write_requests[0]['adapter_outcome'],'recorded')
    def test_injected_callback(self):
        observed=[]
        program,_=compile_program("WRITE('hello')",write=observed.append)
        program.run()
        self.assertEqual(observed,['hello'])
        self.assertEqual(program.write_requests[0]['adapter_outcome'],'callback_completed')
    def test_empty_string_is_a_request(self):
        observed=[]
        program,_=compile_program("WRITE('')",write=observed.append)
        program.run()
        self.assertEqual((observed,texts(program)),([''],['']))
    def test_no_implicit_whitespace_or_quotes(self):
        program,_=compile_program("WRITE('abc') WRITE('def')")
        program.run()
        self.assertEqual(texts(program),['abc','def'])
    def test_existing_blanks_are_preserved(self):
        program,_=compile_program("WRITE('  abc  ')")
        program.run()
        self.assertEqual(texts(program),['  abc  '])
    def test_concat_expression(self):
        program,_=compile_program("text='ready' WRITE(text+'!')")
        program.run()
        self.assertEqual(texts(program),['ready!'])
    def test_global_constant(self):
        program,_=compile_program('WRITE(C)',prefix="CONST C='ready'")
        program.run()
        self.assertEqual(texts(program),['ready'])
    def test_local_constant(self):
        program,_=compile_program('work',routines="ROUTINE work CONST C='local' BEGIN WRITE(C) END work")
        program.run()
        self.assertEqual(texts(program),['local'])
    def test_read_only_string_value_formal(self):
        program,result=compile_program("emit('ready')",routines='ROUTINE emit(p: STRING) BEGIN WRITE(p) END emit')
        program.run()
        self.assertEqual(texts(program),['ready'])
        self.assertEqual(result.report['routine_effects']['EMIT']['potential_parameter_writes'],[])
        self.assertTrue(result.report['routine_effects']['EMIT']['potential_output_requests'])
    def test_reference_formal(self):
        program,_=compile_program("text='ready' emit(text)",routines='ROUTINE emit(p: STRING) BEGIN WRITE(p) END emit')
        program.run()
        self.assertEqual(texts(program),['ready'])
    def test_array_element(self):
        program,_=compile_program("words[2]='robot' WRITE(words[2])")
        program.run()
        self.assertEqual(texts(program),['robot'])
    def test_multidimensional_element(self):
        program,_=compile_program("grid[1,2]='robot' WRITE(grid[1,2])",declarations=DECLARATIONS+'\ngrid: ARRAY[2,2] OF STRING[8]')
        program.run()
        self.assertEqual(texts(program),['robot'])
    def test_structure_field(self):
        program,_=compile_program("packet.label='robot' WRITE(packet.label)",prefix='TYPE packet_t=STRUCTURE label: STRING[8] ENDSTRUCTURE',declarations=DECLARATIONS+'\npacket: packet_t')
        program.run()
        self.assertEqual(texts(program),['robot'])
    def test_using_field(self):
        program,_=compile_program("packet.label='robot' USING packet DO WRITE(label) ENDUSING",prefix='TYPE packet_t=STRUCTURE label: STRING[8] ENDSTRUCTURE',declarations=DECLARATIONS+'\npacket: packet_t')
        program.run()
        self.assertEqual(texts(program),['robot'])
    def test_builtin_substring(self):
        program,_=compile_program("WRITE(SUB_STR('abcdef',2,3))")
        program.run()
        self.assertEqual(texts(program),['bcd'])
    def test_ascii_control_is_text_not_reserved_cr(self):
        program,_=compile_program('WRITE(CHR(13))')
        program.run()
        self.assertEqual(texts(program),['\r'])
    def test_argument_routine_evaluated_once(self):
        routine='ROUTINE next_code: INTEGER BEGIN x=x+1 RETURN 64+x END next_code'
        program,_=compile_program('x=0 WRITE(CHR(next_code()))',routines=routine)
        self.assertEqual(program.run()['X'],1)
        self.assertEqual(texts(program),['A'])
    def test_nested_output_before_outer_request(self):
        routine="ROUTINE code: INTEGER BEGIN WRITE('inner') RETURN 65 END code"
        program,_=compile_program('WRITE(CHR(code()))',routines=routine)
        program.run()
        self.assertEqual(texts(program),['inner','A'])
    def test_if_and_select_paths(self):
        program,_=compile_program("IF OFF THEN WRITE('skipped') ELSE WRITE('chosen') ENDIF SELECT 1 OF CASE(1): WRITE('case') ELSE: WRITE('else') ENDSELECT")
        program.run()
        self.assertEqual(texts(program),['chosen','case'])
    def test_while_and_repeat(self):
        program,_=compile_program('x=0 WHILE x<2 DO WRITE(CHR(65+x)) x=x+1 ENDWHILE REPEAT WRITE(CHR(65+x)) x=x-1 UNTIL x=0')
        program.run()
        self.assertEqual(texts(program),['A','B','C','B'])
    def test_routine_local_for(self):
        routines='ROUTINE emit(p: STRING) BEGIN WRITE(p) END emit\nROUTINE work VAR i: INTEGER BEGIN FOR i=1 TO 3 DO emit(CHR(64+i)) ENDFOR flag=UNINIT(i) END work'
        program,_=compile_program('work',routines=routines)
        self.assertTrue(program.run()['FLAG'])
        self.assertEqual(texts(program),['A','B','C'])
    def test_label_dispatcher(self):
        program,_=compile_program("GOTO start WRITE('skipped') start:: WRITE('chosen')")
        program.run()
        self.assertEqual(texts(program),['chosen'])
    def test_recursive_output(self):
        routine='ROUTINE r(n: INTEGER) BEGIN IF n>0 THEN WRITE(CHR(64+n)) r(n-1) ENDIF END r'
        program,_=compile_program('r(3)',routines=routine)
        program.run()
        self.assertEqual(texts(program),['C','B','A'])
    def test_delay_and_write_order(self):
        events=[]
        program,_=compile_program("WRITE('before') DELAY 1 WRITE('after')",write=lambda t:events.append(('write',t)),sleep=lambda s:events.append(('sleep',s)))
        program.run()
        self.assertEqual(events,[('write','before'),('sleep',0.001),('write','after')])
    def test_trace_is_reset_per_valid_run(self):
        observed=[]
        program,_=compile_program("WRITE('again')",write=observed.append)
        program.run(); first=program.write_requests
        program.run()
        self.assertEqual((texts(program),observed),(['again'],['again','again']))
        self.assertEqual(first[0]['text'],'again')
    def test_trace_records_are_defensive_copies(self):
        program,_=compile_program("WRITE('hello')")
        program.run()
        rows=program.write_requests
        rows[0]['text']='altered'
        self.assertEqual(texts(program),['hello'])
        self.assertIsInstance(rows,tuple)
    def test_program_instances_do_not_share_trace_or_sink(self):
        observed=[]
        one,_=compile_program("WRITE('one')",write=observed.append)
        two,_=compile_program("WRITE('two')")
        one.run(); two.run()
        self.assertEqual((observed,texts(one),texts(two)),(['one'],['one'],['two']))
    def test_trace_is_not_part_of_global_snapshot(self):
        program,_=compile_program("WRITE('hello')")
        snapshot=program.run()
        self.assertNotIn('write_requests',snapshot)
        self.assertEqual(set(snapshot),{'TEXT','X','Y','FLAG','WORDS'})
    def test_maximum_text_length(self):
        program,_=compile_program("WRITE('"+'a'*254+"')")
        program.run()
        self.assertEqual(len(texts(program)[0]),254)
    def test_source_site_and_physical_continuation(self):
        program,result=compile_program("WRITE( &\n 'abc')")
        program.run()
        site=result.report['writes'][0]
        self.assertEqual((site['body'],site['data_type'],site['data_items']),('T','STRING',1))
        self.assertEqual(program.write_requests[0]['line'],site['line'])
    def test_transitive_and_mutual_recursive_effect_report(self):
        routines="ROUTINE a(n: INTEGER) BEGIN b(n) END a\nROUTINE b(n: INTEGER) BEGIN IF n>0 THEN a(n-1) ELSE WRITE('end') ENDIF END b"
        program,result=compile_program('a(2)',routines=routines)
        program.run()
        self.assertEqual(texts(program),['end'])
        for name in ('A','B'): self.assertTrue(result.report['routine_effects'][name]['potential_output_requests'])
    def test_generated_example(self):
        path=Path(__file__).resolve().parents[1]/'examples/string_write_requests.kl'
        result=translate(path.read_text())
        namespace={'__name__':'example_test'}
        exec(result.python_source,namespace)
        program=namespace['Program']()
        self.assertEqual(program.run()['TOTAL'],3)
        self.assertEqual(texts(program),['ready','A','B','C','done'])


class WriteRejectionTests(unittest.TestCase):
    def reject(self,body,code,**kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**kwargs)
        self.assertEqual(caught.exception.code,code,str(caught.exception))
    def test_empty_data_list(self): self.reject('WRITE()','E_WRITE_ITEM')
    def test_multiple_items(self): self.reject("WRITE('a','b')",'E_WRITE_ITEM')
    def test_reserved_cr(self): self.reject('WRITE(CR)','E_WRITE_ITEM')
    def test_format_width(self): self.reject("WRITE('abc':5)",'E_WRITE_ITEM')
    def test_unknown_double_colon_format(self): self.reject("WRITE('abc'::5::4)",'E_WRITE_FORMAT')
    def test_explicit_predefined_device(self): self.reject("WRITE OUTPUT('abc')",'E_WRITE_TARGET')
    def test_explicit_variable_target(self): self.reject("WRITE text('abc')",'E_WRITE_TARGET')
    def test_unparenthesized_list(self): self.reject("WRITE 'abc'",'E_WRITE_TARGET')
    def test_integer_format(self): self.reject('WRITE(1::8)','E_WRITE_FORMAT')
    def test_boolean_format(self): self.reject('WRITE(ON::8)','E_WRITE_FORMAT')
    def test_real(self): self.reject('WRITE(2.5)','E_TYPE')
    def test_whole_array(self): self.reject('WRITE(words)','E_TYPE')
    def test_expression_valued_write(self): self.reject("x=WRITE('abc')",'E_EXPRESSION')
    def test_cr_is_reserved_identifier(self): self.reject('', 'E_DECLARATION',declarations='CR: STRING[8]')
    def test_file_open_remains_blocked(self): self.reject("OPEN FILE text('abc')",'E_UNSUPPORTED')
    def test_read_remains_blocked(self): self.reject('READ(text)','E_UNSUPPORTED')
    def test_output_function_in_operator(self): self.reject('x=f()+1','E_EVALUATION_ORDER',routines="ROUTINE f: INTEGER BEGIN WRITE('abc') RETURN 1 END f")
    def test_transitive_output_function_in_operator(self): self.reject('x=f()+1','E_EVALUATION_ORDER',routines="ROUTINE emit BEGIN WRITE('abc') END emit\nROUTINE f: INTEGER BEGIN emit RETURN 1 END f")
    def test_skipped_output_still_marks_function(self): self.reject('x=f()+1','E_EVALUATION_ORDER',routines="ROUTINE f: INTEGER BEGIN IF OFF THEN WRITE('abc') ENDIF RETURN 1 END f")
    def test_output_function_assigned_to_indexed_target(self): self.reject('numbers[1]=f()','E_EVALUATION_ORDER',routines="ROUTINE f: INTEGER BEGIN WRITE('abc') RETURN 1 END f",declarations=DECLARATIONS+'\nnumbers: ARRAY[2] OF INTEGER')
    def test_existing_multi_argument_order_guard(self): self.reject("WRITE(SUB_STR('abc',f(),1))",'E_EVALUATION_ORDER',routines='ROUTINE f: INTEGER BEGIN RETURN 1 END f')


class WriteFailureTests(unittest.TestCase):
    def test_invalid_sinks_rejected_at_construction(self):
        for value in (False,0,'writer',[],object()):
            with self.subTest(value=value),self.assertRaises(TypeError): compile_program("WRITE('a')",write=value)
    def test_uninitialized_text_fails_before_request(self):
        program,_=compile_program('WRITE(text)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
        self.assertEqual(program.write_requests,())
    def test_out_of_bounds_fails_before_request(self):
        program,_=compile_program('WRITE(words[3])')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.write_requests,())
    def test_overlong_expression_fails_before_request(self):
        observed=[]
        program,_=compile_program("text='"+'a'*16+"' WRITE("+'+'.join(['text']*16)+')',write=observed.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'254 characters'): program.run()
        self.assertEqual((observed,program.write_requests),([],()))
    def test_runtime_non_ascii_fails_before_request(self):
        state=rt.State({}, {})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ASCII'): state.write_string('\u00e9',7)
        self.assertEqual(state.write_requests,[])
    def test_runtime_wrong_type_fails_before_request(self):
        state=rt.State({}, {})
        with self.assertRaises(rt.KarelRuntimeError): state.write_string(1,7)
        self.assertEqual(state.write_requests,[])
    def test_callback_failure_keeps_prior_writes_and_cause(self):
        error=OSError('sink failed')
        def fail(text): raise error
        program,result=compile_program("x=9 WRITE('a') y=7",write=fail)
        with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
        self.assertIs(caught.exception.__cause__,error)
        self.assertEqual(program._state.get('X'),9)
        self.assertTrue(rt.uninit(program._state.raw('Y')))
        self.assertEqual(program.write_requests[0]['adapter_outcome'],'callback_failed')
        self.assertEqual(caught.exception.line,result.report['writes'][0]['line'])
    def test_wrong_callback_result_rejected(self):
        program,_=compile_program("WRITE('a')",write=lambda text:1)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'return None'): program.run()
        self.assertEqual(program.write_requests[0]['adapter_outcome'],'callback_result_rejected')
    def test_false_callback_result_also_rejected(self):
        program,_=compile_program("WRITE('a')",write=lambda text:False)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
    def test_callback_interruption_cleans_frames(self):
        def interrupt(text): raise KeyboardInterrupt()
        program,_=compile_program("emit('a')",routines='ROUTINE emit(p: STRING) BEGIN WRITE(p) END emit',write=interrupt)
        with self.assertRaises(KeyboardInterrupt): program.run()
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
        self.assertEqual(program.write_requests[0]['adapter_outcome'],'callback_interrupted')
    def test_nested_callback_failure_cleans_frames(self):
        def fail(text): raise OSError('sink failed')
        routines='ROUTINE emit(p: STRING) BEGIN WRITE(p) END emit\nROUTINE forward(q: STRING) BEGIN emit(q) END forward'
        program,_=compile_program("forward('a')",routines=routines,write=fail)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_callback_partial_external_effect_is_not_rolled_back(self):
        observed=[]
        def fail(text): observed.append(text); raise OSError('after effect')
        program,_=compile_program("WRITE('a')",write=fail)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(observed,['a'])
        self.assertEqual(program.write_requests[0]['adapter_outcome'],'callback_failed')
    def test_budget_failure_retains_prior_request_and_cleans_frame(self):
        program,_=compile_program('work',routines="ROUTINE work BEGIN WHILE ON DO WRITE('a') ENDWHILE END work")
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'): program.run(max_steps=10)
        self.assertGreater(len(program.write_requests),0)
        self.assertEqual(program._state.local_frames,[])
    def test_invalid_budget_does_not_clear_existing_trace(self):
        program,_=compile_program("WRITE('a')")
        program.run()
        with self.assertRaises(ValueError): program.run(max_steps=0)
        self.assertEqual(texts(program),['a'])
    def test_later_failure_preserves_completed_request(self):
        program,_=compile_program("WRITE('a') x=1 DIV 0")
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(texts(program),['a'])


if __name__ == '__main__': unittest.main()
