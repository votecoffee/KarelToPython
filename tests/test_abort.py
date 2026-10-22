"""Bare ABORT terminates only the bounded offline instance, without rollback."""
import json
from pathlib import Path
import subprocess,sys,tempfile,unittest
from karel2py import translate,runtime as rt
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError

ROOT=Path(__file__).resolve().parents[1]

def compile_program(body='ABORT',*,declarations='value: INTEGER\nfinished: BOOLEAN',routines='',prefix='',_translator=translate, **context):
    result=_translator(f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T',filename='abort.kl')
    namespace={'__name__':'abort_test'}
    exec(result.python_source,namespace)
    return namespace['Program'](**context),result


class AbortExecutionTests(unittest.TestCase):
    def aborted(self,body,**options):
        program,result=compile_program(body,**options)
        with self.assertRaises(rt.KarelAbort) as caught: program.run()
        self.assertEqual(caught.exception.line,program.abort_info['line'])
        self.assertEqual(program._state.call_depth,0)
        self.assertEqual(program._state.local_frames,[])
        return program,result
    def test_bare_abort_distinct_from_runtime_failure(self):
        program,_=self.aborted('ABORT')
        self.assertEqual(program.abort_info['kind'],'ABORT')
        self.assertFalse(issubclass(rt.KarelAbort,rt.KarelRuntimeError))
    def test_no_successful_run_result(self):
        self.aborted('value=1 ABORT value=2')
    def test_writes_before_abort_preserved(self):
        program,_=self.aborted('value=1 finished=OFF ABORT value=2 finished=ON')
        self.assertEqual(program.snapshot(),dict(VALUE=1,FINISHED=False))
    def test_source_line_retained(self):
        program,_=self.aborted('value=1\nABORT\nvalue=2')
        self.assertEqual(program.abort_info['line'],8)
    def test_case_insensitive(self): self.aborted('abort')
    def test_semicolon_separators(self): self.aborted('value=1; ABORT; value=2')
    def test_trailing_comment(self): self.aborted('ABORT -- intended offline stop')
    def test_unexecuted_abort_is_not_termination(self):
        program,_=compile_program('IF OFF THEN ABORT ENDIF value=7')
        self.assertEqual(program.run()['VALUE'],7)
        self.assertIsNone(program.abort_info)
    def test_if_branch(self): self.aborted('IF ON THEN ABORT ELSE value=99 ENDIF')
    def test_select_branch(self): self.aborted('SELECT 2 OF CASE(1): value=1 CASE(2): ABORT ELSE: value=3 ENDSELECT')
    def test_while_body(self): self.aborted('WHILE ON DO ABORT ENDWHILE')
    def test_repeat_skips_condition(self): self.aborted('REPEAT ABORT UNTIL finished')
    def test_using_body(self): self.aborted('USING item DO field=3 ABORT ENDUSING',prefix='TYPE item_t=STRUCTURE field: INTEGER ENDSTRUCTURE',declarations='item: item_t')
    def test_label_dispatch_has_terminal_abort(self):
        program,result=self.aborted('value=1 GO TO stop_here value=2\nstop_here:: ABORT\nvalue=3')
        self.assertEqual(program.snapshot()['VALUE'],1)
        nodes=result.report['control_flow']['program']['nodes']
        self.assertEqual([node['successors'] for node in nodes if node['statement_kind']=='abort'],[[]])
    def test_label_skips_abort(self):
        program,_=compile_program('GO TO finish ABORT\nfinish:: value=7')
        self.assertEqual(program.run()['VALUE'],7)
        self.assertIsNone(program.abort_info)
    def test_procedure_unwinds_frames(self): self.aborted('stop_now',routines='ROUTINE stop_now VAR local_value: INTEGER BEGIN local_value=2 ABORT END stop_now')
    def test_nested_calls_unwind(self): self.aborted('outer',routines='ROUTINE inner BEGIN ABORT END inner\nROUTINE outer BEGIN inner END outer')
    def test_recursive_calls_unwind(self):
        self.aborted('descend(5)',routines='ROUTINE descend(n: INTEGER) BEGIN IF n=0 THEN ABORT ELSE descend(n-1) ENDIF END descend')
    def test_local_for_counter_is_discarded_with_frame(self):
        program,_=self.aborted('loop_stop',routines='ROUTINE loop_stop VAR count: INTEGER BEGIN FOR count=1 TO 3 DO value=count IF count=2 THEN ABORT ENDIF ENDFOR END loop_stop')
        self.assertEqual(program.snapshot()['VALUE'],2)
        self.assertNotIn('COUNT',program.snapshot())
    def test_function_abort_before_assignment(self):
        program,_=self.aborted('value=7 value=stop_value()',routines='ROUTINE stop_value: INTEGER BEGIN ABORT RETURN 9 END stop_value')
        self.assertEqual(program.snapshot()['VALUE'],7)
    def test_abort_before_write_request(self):
        program,_=self.aborted('WRITE(stop_value())',routines='ROUTINE stop_value: INTEGER BEGIN ABORT RETURN 9 END stop_value')
        self.assertEqual(program.write_requests,())
    def test_recorded_output_before_abort_preserved(self):
        program,_=self.aborted("WRITE('first') ABORT WRITE('last')")
        self.assertEqual([r['text'] for r in program.write_requests],['first'])
    def test_injected_output_is_not_rolled_back(self):
        observed=[]
        program,_=self.aborted("WRITE('first') ABORT WRITE('last')",write=observed.append)
        self.assertEqual(observed,['first'])
        self.assertEqual(program.write_requests[0]['adapter_outcome'],'callback_completed')
    def test_delay_before_abort_is_not_rolled_back(self):
        observed=[]
        self.aborted('DELAY 1 ABORT DELAY 2',sleep=observed.append)
        self.assertEqual(observed,[.001])
    def test_aborted_instance_cannot_run_again(self):
        program,_=self.aborted("value=7 WRITE('first') ABORT")
        before=(program.snapshot(),program.write_requests,program._state.steps,program.abort_info)
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual((program.snapshot(),program.write_requests,program._state.steps,program.abort_info),before)
    def test_new_instance_is_cold_restart(self):
        program,_=self.aborted('value=7 ABORT')
        restarted=type(program)()
        self.assertIsNone(restarted.abort_info)
        self.assertEqual(restarted.snapshot()['VALUE'],{'uninitialized':True})
        with self.assertRaises(rt.KarelAbort): restarted.run()
    def test_abort_metadata_defensive_copy(self):
        program,_=self.aborted('ABORT')
        info=program.abort_info
        info['line']=99
        self.assertNotEqual(program.abort_info['line'],99)
    def test_snapshot_defensive_copy_after_abort(self):
        program,_=self.aborted('items[1]=7 ABORT',declarations='items: ARRAY[1] OF INTEGER')
        snapshot=program.snapshot()
        snapshot['ITEMS'][0]=99
        self.assertEqual(program.snapshot()['ITEMS'],[7])
    def test_step_limit_is_not_abort(self):
        program,_=compile_program('WHILE ON DO value=1 ENDWHILE ABORT')
        with self.assertRaises(rt.KarelRuntimeError): program.run(max_steps=3)
        self.assertIsNone(program.abort_info)
    def test_prior_runtime_failure_is_not_abort(self):
        program,_=compile_program('value=value+1 ABORT')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertIsNone(program.abort_info)
    def test_abort_after_run_cannot_be_bypassed_by_private_routine(self):
        program,_=self.aborted('ABORT',routines='ROUTINE change BEGIN value=99 END change')
        with self.assertRaises(rt.KarelAbort): program._routine_CHANGE()
        self.assertEqual(program.snapshot()['VALUE'],{'uninitialized':True})
    def test_repeated_abort_preserves_first_location(self):
        state=rt.State({}, {})
        with self.assertRaises(rt.KarelAbort): state.abort(5)
        with self.assertRaises(rt.KarelAbort) as caught: state.abort(99)
        self.assertEqual(caught.exception.line,5)


class AbortTranslationTests(unittest.TestCase):
    def test_target_forms_blocked(self):
        for form in ('ABORT PROGRAM[1]','ABORT(1)','ABORT()','ABORT[1]','ABORT=1','ABORT.field'):
            with self.subTest(form=form),self.assertRaises(TranslationError) as caught: compile_program(form,_translator=legacy_translate)
            self.assertEqual(caught.exception.code,'E_ABORT_TARGET')
    def test_continued_task_target_blocked(self):
        with self.assertRaises(TranslationError) as caught: compile_program('ABORT &\n PROGRAM[1]',_translator=legacy_translate)
        self.assertEqual(caught.exception.code,'E_ABORT_TARGET')
    def test_action_and_condition_contexts_blocked(self):
        with self.assertRaises(TranslationError): compile_program('CONDITION[1]: WHEN ABORT DO ABORT ENDCONDITION',_translator=legacy_translate)
    def test_abort_task_requires_explicit_registered_target(self):
        program,_=compile_program("ABORT_TASK('T',ON,OFF,value)")
        self.assertEqual(program.run()['VALUE'],1)
    def test_noabort_directive_blocked(self):
        with self.assertRaises(TranslationError): compile_program(prefix='%NOABORT=ERROR')
    def test_global_for_abort_blocked(self):
        with self.assertRaises(TranslationError) as caught: compile_program('FOR value=1 TO 3 DO ABORT ENDFOR', _translator=legacy_translate)
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
    def test_reference_for_abort_blocked(self):
        with self.assertRaises(TranslationError) as caught: compile_program('loop_stop(value)',routines='ROUTINE loop_stop(count: INTEGER) BEGIN FOR count=1 TO 3 DO ABORT ENDFOR END loop_stop')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
    def test_direct_abort_effect_in_operator_blocked(self):
        with self.assertRaises(TranslationError) as caught: compile_program('value=stop_value()+1',routines='ROUTINE stop_value: INTEGER BEGIN ABORT RETURN 9 END stop_value', _translator=legacy_translate)
        self.assertEqual(caught.exception.code,'E_EVALUATION_ORDER')
    def test_transitive_abort_effect_in_indexed_assignment_blocked(self):
        routines='ROUTINE stop_now BEGIN ABORT END stop_now\nROUTINE stop_value: INTEGER BEGIN stop_now RETURN 9 END stop_value'
        with self.assertRaises(TranslationError) as caught: compile_program('items[1]=stop_value()',declarations='items: ARRAY[1] OF INTEGER',routines=routines, _translator=legacy_translate)
        self.assertEqual(caught.exception.code,'E_EVALUATION_ORDER')
    def test_effects_propagate_even_on_skipped_path(self):
        routines='ROUTINE inner BEGIN IF OFF THEN ABORT ENDIF END inner\nROUTINE outer BEGIN inner END outer'
        _,result=compile_program('',routines=routines)
        self.assertTrue(result.report['routine_effects']['INNER']['potential_aborts'])
        self.assertTrue(result.report['routine_effects']['OUTER']['potential_aborts'])
        self.assertEqual(result.report['aborts'][0]['body'],'INNER')
    def test_unreachable_unsupported_source_is_still_rejected(self):
        with self.assertRaises(TranslationError): compile_program('ABORT unknown_procedure')
    def test_abort_expression_blocked(self):
        with self.assertRaises(TranslationError): compile_program('value=ABORT')
    def test_report_source_mapping(self):
        _,result=compile_program()
        use=result.report['aborts'][0]
        self.assertIn('ABORT',result.report['features'])
        self.assertFalse(result.report['abort_policy']['controller_validated'])
        self.assertIn(use['line'],[row['karel_line'] for row in result.report['source_map']])
    def test_cli_check_does_not_execute_abort(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'abort.kl'
            source.write_text('PROGRAM T BEGIN ABORT END T')
            result=subprocess.run([sys.executable,'-m','karel2py',str(source),'--check'],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
    def test_generated_script_termination_is_nonzero(self):
        with tempfile.TemporaryDirectory() as folder:
            module=Path(folder)/'abort_example.py'
            _,translation=compile_program()
            module.write_text(translation.python_source,encoding='utf-8')
            result=subprocess.run([sys.executable,'-c',f"import runpy; runpy.run_path({str(module)!r},run_name='__main__')"],cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('KarelAbort',result.stderr)
            self.assertEqual(result.stdout,'')


if __name__=='__main__': unittest.main()
