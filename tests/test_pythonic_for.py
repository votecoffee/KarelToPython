"""Checked global FOR calls, read-only counter aliases and deterministic cleanup."""
import json
from pathlib import Path
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


DECLARATIONS = '''i,j,total,result,seen,visits: INTEGER r: REAL flag: BOOLEAN
text: STRING[254] values: ARRAY[3] OF INTEGER v: VECTOR'''


def compile_program(body, routines='', *, declarations=DECLARATIONS, prefix='', translator=translate, **context):
    result = translator(f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T', filename='pythonic_for.kl')
    namespace = {'__name__': 'pythonic_for_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](**context), result


def execute(body, routines='', **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


class GlobalForCallTests(unittest.TestCase):
    def test_global_counter_procedure(self):
        state = execute('total=0 FOR i=1 TO 3 DO add ENDFOR', 'ROUTINE add BEGIN total=total+i END add')
        self.assertEqual((state['TOTAL'], state['I']), (6, {'uninitialized':True}))

    def test_global_counter_function(self):
        state = execute('total=0 FOR i=1 TO 3 DO total=total+twice() ENDFOR',
                        'ROUTINE twice: INTEGER BEGIN RETURN i*2 END twice')
        self.assertEqual(state['TOTAL'], 12)

    def test_bare_function_call(self):
        state = execute('FOR i=1 TO 2 DO result=answer ENDFOR', 'ROUTINE answer: INTEGER BEGIN RETURN i END answer')
        self.assertEqual(state['RESULT'], 2)

    def test_downto_with_helper(self):
        state = execute('total=0 FOR i=3 DOWNTO 1 DO add ENDFOR', 'ROUTINE add BEGIN total=total+i END add')
        self.assertEqual(state['TOTAL'], 6)

    def test_transitive_helpers(self):
        routines = 'ROUTINE add BEGIN total=total+i END add\nROUTINE outer BEGIN add END outer'
        self.assertEqual(execute('total=0 FOR i=1 TO 3 DO outer ENDFOR', routines)['TOTAL'], 6)

    def test_unrelated_global_write_allowed(self):
        self.assertEqual(execute('FOR i=1 TO 2 DO change ENDFOR', 'ROUTINE change BEGIN seen=99 END change')['SEEN'], 99)

    def test_local_shadow_does_not_write_global_counter(self):
        routine = 'ROUTINE work VAR i: INTEGER BEGIN i=99 seen=i END work'
        self.assertEqual(execute('total=0 FOR i=1 TO 3 DO work total=total+i ENDFOR', routine)['TOTAL'], 6)

    def test_fresh_local_counter_can_call_global_writer_with_same_name(self):
        routines = 'ROUTINE write_i BEGIN i=99 END write_i\nROUTINE work VAR i: INTEGER BEGIN FOR i=1 TO 3 DO write_i total=total+i ENDFOR END work'
        state = execute('total=0 work', routines)
        self.assertEqual((state['TOTAL'], state['I']), (6, 99))

    def test_nested_global_and_local_counters(self):
        routines = 'ROUTINE add BEGIN total=total+1 END add\nROUTINE work VAR k: INTEGER BEGIN FOR i=1 TO 2 DO FOR k=1 TO 3 DO add ENDFOR ENDFOR END work'
        self.assertEqual(execute('total=0 work', routines)['TOTAL'], 6)

    def test_nonparameter_routine_with_global_counter(self):
        routines = 'ROUTINE add BEGIN total=total+i END add\nROUTINE work BEGIN FOR i=1 TO 3 DO add ENDFOR END work'
        self.assertEqual(execute('total=0 work', routines)['TOTAL'], 6)

    def test_builtin_output_to_other_storage(self):
        state = execute("FOR i=1 TO 2 DO CNV_INT_STR(i,1,10,text) ENDFOR")
        self.assertEqual(state['TEXT'], ' 2')

    def test_dynamic_write_format_helper(self):
        observed = []
        program, _ = compile_program('FOR i=1 TO 2 DO WRITE(i::width()) ENDFOR',
                                     'ROUTINE width: INTEGER BEGIN RETURN 4 END width', write=observed.append)
        program.run()
        self.assertEqual(observed, ['   1', '   2'])

    def test_delay_helper(self):
        sleeps = []
        program, _ = compile_program('FOR i=1 TO 2 DO wait_moment ENDFOR', 'ROUTINE wait_moment BEGIN DELAY(1) END wait_moment', sleep=sleeps.append)
        program.run()
        self.assertEqual(sleeps, [.001, .001])

    def test_label_dispatcher_around_loop(self):
        state = execute('total=0 GOTO work work:: FOR i=1 TO 3 DO add ENDFOR', 'ROUTINE add BEGIN total=total+i END add')
        self.assertEqual(state['TOTAL'], 6)


class CounterReferenceTests(unittest.TestCase):
    def test_read_only_integer_formal(self):
        state = execute('total=0 FOR i=1 TO 3 DO inspect(i) ENDFOR', 'ROUTINE inspect(p: INTEGER) BEGIN total=total+p END inspect')
        self.assertEqual(state['TOTAL'], 6)

    def test_read_only_function_formal(self):
        state = execute('total=0 FOR i=1 TO 3 DO total=total+twice(i) ENDFOR', 'ROUTINE twice(p: INTEGER): INTEGER BEGIN RETURN p*2 END twice')
        self.assertEqual(state['TOTAL'], 12)

    def test_read_only_forwarding(self):
        routines = 'ROUTINE inspect(p: INTEGER) BEGIN total=total+p END inspect\nROUTINE forward(p: INTEGER) BEGIN inspect(p) END forward'
        self.assertEqual(execute('total=0 FOR i=1 TO 3 DO forward(i) ENDFOR', routines)['TOTAL'], 6)

    def test_recursion_preserves_read_only_formal(self):
        routine = 'ROUTINE inspect(p,n: INTEGER) BEGIN total=total+p IF n>0 THEN inspect(p,n-1) ENDIF END inspect'
        self.assertEqual(execute('total=0 FOR i=1 TO 2 DO inspect(i,2) ENDFOR', routine)['TOTAL'], 9)

    def test_grouped_counter_still_writable_value(self):
        state = execute('total=0 FOR i=1 TO 3 DO change((i)) total=total+i ENDFOR', 'ROUTINE change(p: INTEGER) BEGIN p=99 END change')
        self.assertEqual(state['TOTAL'], 6)

    def test_real_promotion_is_writable_value(self):
        state = execute('r=0 FOR i=1 TO 3 DO change(i) ENDFOR', 'ROUTINE change(p: REAL) BEGIN r=r+p p=99.0 END change')
        self.assertEqual(state['R'], 6.0)

    def test_transitive_real_promotion_does_not_mark_integer_formal_writable(self):
        routines = 'ROUTINE change(p: REAL) BEGIN p=99.0 END change\nROUTINE forward(p: INTEGER) BEGIN change(p) seen=p END forward'
        program, result = compile_program('FOR i=1 TO 2 DO forward(i) ENDFOR', routines)
        self.assertEqual(program.run()['SEEN'], 2)
        self.assertEqual(result.report['routine_effects']['FORWARD']['potential_parameter_writes'], [])

    def test_transitive_real_promotion_does_not_mark_global_written(self):
        routines = 'ROUTINE change(p: REAL) BEGIN p=99.0 END change\nROUTINE forward BEGIN change(i) END forward'
        program, result = compile_program('total=0 FOR i=1 TO 3 DO forward total=total+i ENDFOR', routines)
        self.assertEqual(program.run()['TOTAL'], 6)
        self.assertEqual(result.report['routine_effects']['FORWARD']['potential_global_writes'], [])

    def test_fresh_local_counter_read_only_reference(self):
        routines = 'ROUTINE inspect(p: INTEGER) BEGIN total=total+p END inspect\nROUTINE work VAR k: INTEGER BEGIN FOR k=1 TO 3 DO inspect(k) ENDFOR END work'
        self.assertEqual(execute('total=0 work', routines)['TOTAL'], 6)


class CounterWriteProofTests(unittest.TestCase):
    def reject(self, body, routines='', **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, routines, **kwargs)
        self.assertEqual(caught.exception.code, 'E_FOR_COUNTER')

    def test_direct_global_write_in_helper(self):
        self.reject('FOR i=1 TO 3 DO change ENDFOR', 'ROUTINE change BEGIN i=99 END change')

    def test_transitive_global_write(self):
        self.reject('FOR i=1 TO 3 DO outer ENDFOR', 'ROUTINE change BEGIN i=99 END change\nROUTINE outer BEGIN change END outer')

    def test_global_write_through_actual_parameter(self):
        self.reject('FOR i=1 TO 3 DO outer ENDFOR', 'ROUTINE change(p: INTEGER) BEGIN p=99 END change\nROUTINE outer BEGIN change(i) END outer')

    def test_recursive_global_write_fixed_point(self):
        routines = 'ROUTINE first(n: INTEGER) BEGIN IF n>0 THEN second(n-1) ENDIF END first\nROUTINE second(n: INTEGER) BEGIN IF n=0 THEN i=99 ELSE first(n-1) ENDIF END second'
        self.reject('FOR i=1 TO 3 DO first(3) ENDFOR', routines)

    def test_dead_branch_write_stays_conservative(self):
        self.reject('FOR i=1 TO 3 DO change ENDFOR', 'ROUTINE change BEGIN IF OFF THEN i=99 ENDIF END change')

    def test_callee_loop_counts_as_global_write(self):
        self.reject('FOR i=1 TO 3 DO change ENDFOR', 'ROUTINE change BEGIN FOR i=3 TO 1 DO ENDFOR END change')

    def test_builtin_output_counts_as_global_write(self):
        self.reject('FOR i=1 TO 3 DO change ENDFOR', "ROUTINE change BEGIN CNV_STR_INT('3',i) END change")

    def test_write_format_function_counts_as_global_write(self):
        self.reject('FOR i=1 TO 3 DO outer ENDFOR', 'ROUTINE width: INTEGER BEGIN i=6 RETURN 6 END width\nROUTINE outer BEGIN WRITE(42::width()) END outer')

    def test_nested_bound_function_cannot_write_outer_counter(self):
        self.reject('FOR i=1 TO 3 DO FOR j=1 TO change() DO ENDFOR ENDFOR', 'ROUTINE change: INTEGER BEGIN i=6 RETURN 2 END change')

    def test_writable_counter_reference(self):
        self.reject('FOR i=1 TO 3 DO change(i) ENDFOR', 'ROUTINE change(p: INTEGER) BEGIN p=99 END change')

    def test_transitively_writable_counter_reference(self):
        self.reject('FOR i=1 TO 3 DO forward(i) ENDFOR', 'ROUTINE change(p: INTEGER) BEGIN p=99 END change\nROUTINE forward(p: INTEGER) BEGIN change(p) END forward')

    def test_duplicate_alias_in_writable_formal(self):
        self.reject('FOR i=1 TO 3 DO change(i,i) ENDFOR', 'ROUTINE change(p,q: INTEGER) BEGIN seen=p q=99 END change')

    def test_written_counter_reference_in_dead_branch(self):
        self.reject('FOR i=1 TO 3 DO change(i) ENDFOR', 'ROUTINE change(p: INTEGER) BEGIN IF OFF THEN p=99 ENDIF END change')

    def test_nested_global_counter_write_rejected(self):
        self.reject('FOR i=1 TO 2 DO FOR j=1 TO 2 DO change ENDFOR ENDFOR', 'ROUTINE change BEGIN i=99 END change')

    def test_direct_counter_assignment_still_blocked(self):
        self.reject('FOR i=1 TO 3 DO i=99 ENDFOR')

    def test_builtin_direct_counter_output_still_blocked(self):
        self.reject("FOR i=1 TO 3 DO CNV_STR_INT('2',i) ENDFOR")

    def test_formal_counter_still_blocked(self):
        self.reject('work(i)', 'ROUTINE work(p: INTEGER) BEGIN FOR p=1 TO 3 DO ENDFOR END work')

    def test_parameterized_routine_nonlocal_counter_still_blocked(self):
        self.reject('work(total)', 'ROUTINE work(p: INTEGER) BEGIN FOR i=1 TO 3 DO p=p+i ENDFOR END work')

    def test_nested_reused_counter_still_blocked(self):
        self.reject('FOR i=1 TO 3 DO FOR i=1 TO 2 DO ENDFOR ENDFOR')


class ForCleanupTests(unittest.TestCase):
    def assert_uninitialized(self, program, *names):
        for name in names: self.assertEqual(program.snapshot()[name], {'uninitialized': True})
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_normal_completion(self):
        program, _ = compile_program('FOR i=1 TO 2 DO total=i ENDFOR')
        self.assertEqual(program.run()['TOTAL'], 2)
        self.assert_uninitialized(program, 'I')

    def test_empty_completion(self):
        program, _ = compile_program('FOR i=2 TO 1 DO total=99 ENDFOR')
        program.run()
        self.assert_uninitialized(program, 'I', 'TOTAL')

    def test_global_counter_return_value_captured_before_clear(self):
        program, _ = compile_program('result=first()', 'ROUTINE first: INTEGER BEGIN FOR i=2 TO 3 DO RETURN i ENDFOR RETURN 0 END first')
        self.assertEqual(program.run()['RESULT'], 2)
        self.assert_uninitialized(program, 'I')

    def test_global_counter_procedure_return(self):
        program, _ = compile_program('work', 'ROUTINE work BEGIN FOR i=1 TO 3 DO seen=i RETURN ENDFOR seen=99 END work')
        self.assertEqual(program.run()['SEEN'], 1)
        self.assert_uninitialized(program, 'I')

    def test_nested_global_counter_return_clears_both(self):
        program, _ = compile_program('result=first()', 'ROUTINE first: INTEGER BEGIN FOR i=1 TO 2 DO FOR j=3 TO 4 DO RETURN i*10+j ENDFOR ENDFOR RETURN 0 END first')
        self.assertEqual(program.run()['RESULT'], 13)
        self.assert_uninitialized(program, 'I', 'J')

    def test_string_return_checked_before_clear(self):
        program, _ = compile_program('text=first()', "ROUTINE first: STRING[2] BEGIN FOR i=1 TO 2 DO RETURN 'ABC' ENDFOR RETURN '' END first")
        self.assertEqual(program.run()['TEXT'], 'AB')
        self.assert_uninitialized(program, 'I')

    def test_array_return_copy_survives_clear(self):
        routine = 'ROUTINE first: ARRAY OF INTEGER VAR data: ARRAY[3] OF INTEGER BEGIN data[1]=7 data[2]=8 data[3]=9 FOR i=1 TO 2 DO RETURN data ENDFOR RETURN data END first'
        program, _ = compile_program('values=first()', routine)
        self.assertEqual(program.run()['VALUES'], [7,8,9])
        self.assert_uninitialized(program, 'I')

    def test_body_error_clears_and_preserves_other_writes(self):
        program, _ = compile_program('FOR i=1 TO 3 DO seen=i result=1 DIV 0 ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['SEEN'], 1)
        self.assert_uninitialized(program, 'I')

    def test_final_bound_error_clears_initialized_counter(self):
        program, _ = compile_program('i=9 FOR i=2 TO 1 DIV 0 DO ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assert_uninitialized(program, 'I')

    def test_final_bound_error_preserves_other_effects(self):
        routine = 'ROUTINE last: INTEGER BEGIN seen=i RETURN 1 DIV 0 END last'
        program, _ = compile_program('FOR i=2 TO last() DO ENDFOR', routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['SEEN'], 2)
        self.assert_uninitialized(program, 'I')

    def test_initial_expression_error_keeps_previous_counter(self):
        program, _ = compile_program('i=9 FOR i=1 DIV 0 TO 3 DO ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['I'], 9)

    def test_initial_storage_error_keeps_previous_counter(self):
        program, _ = compile_program('i=9 FOR i=MAXINT TO 3 DO ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['I'], 9)

    def test_maxint_final_iteration_error_clears_counter_and_keeps_body_writes(self):
        program, _ = compile_program('visits=0 FOR i=2147483646 TO MAXINT DO visits=visits+1 ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['VISITS'], 1)
        self.assert_uninitialized(program, 'I')

    def test_failed_initial_expression_keeps_its_prior_effects(self):
        routine = 'ROUTINE first: INTEGER BEGIN i=7 RETURN 1 DIV 0 END first'
        program, _ = compile_program('i=9 FOR i=first() TO 3 DO ENDFOR', routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['I'], 7)

    def test_final_bound_may_change_start_before_range_capture(self):
        routine = 'ROUTINE last: INTEGER BEGIN i=2 RETURN 3 END last'
        state = execute('total=0 FOR i=1 TO last() DO total=total+i ENDFOR', routine)
        self.assertEqual(state['TOTAL'], 5)

    def test_return_value_failure_clears_counter(self):
        routine = 'ROUTINE first: INTEGER BEGIN FOR i=1 TO 3 DO RETURN seen ENDFOR RETURN 0 END first'
        program, _ = compile_program('result=first()', routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assert_uninitialized(program, 'I', 'RESULT')

    def test_direct_abort_clears_active_counters(self):
        program, _ = compile_program('FOR i=1 TO 2 DO FOR j=1 TO 2 DO seen=i+j ABORT ENDFOR ENDFOR')
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual(program.snapshot()['SEEN'], 2)
        self.assert_uninitialized(program, 'I', 'J')
        with self.assertRaises(rt.KarelAbort): program.run()

    def test_helper_abort_clears_counter(self):
        program, _ = compile_program('FOR i=1 TO 2 DO stop_now ENDFOR', 'ROUTINE stop_now BEGIN seen=i ABORT END stop_now')
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual(program.snapshot()['SEEN'], 1)
        self.assert_uninitialized(program, 'I')

    def test_step_budget_clears_counter(self):
        program, _ = compile_program('visits=0 FOR i=1 TO 1000 DO count ENDFOR', 'ROUTINE count BEGIN visits=visits+1 END count')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'step budget'): program.run(max_steps=20)
        self.assertGreater(program.snapshot()['VISITS'], 0)
        self.assert_uninitialized(program, 'I')

    def test_call_depth_failure_clears_counter(self):
        program, _ = compile_program('FOR i=1 TO 2 DO recurse ENDFOR', 'ROUTINE recurse BEGIN recurse END recurse')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'call-depth'): program.run(max_steps=1000)
        self.assert_uninitialized(program, 'I')

    def test_callback_error_clears_counter_without_retry(self):
        observed = []
        def write(text):
            observed.append(text)
            raise OSError('failed sink')
        program, _ = compile_program('FOR i=1 TO 3 DO WRITE(i) ENDFOR', write=write)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'failed sink'): program.run()
        self.assertEqual(observed, [' 1'])
        self.assert_uninitialized(program, 'I')

    def test_callback_interruption_clears_counter(self):
        def write(text): raise KeyboardInterrupt()
        program, _ = compile_program('FOR i=1 TO 3 DO WRITE(i) ENDFOR', write=write)
        with self.assertRaises(KeyboardInterrupt): program.run()
        self.assertEqual(program.write_requests[0]['adapter_outcome'], 'callback_interrupted')
        self.assert_uninitialized(program, 'I')

    def test_nested_helper_failure_clears_inner_and_outer_counters(self):
        routine = 'ROUTINE work BEGIN FOR j=1 TO 3 DO seen=j result=1 DIV 0 ENDFOR END work'
        program, _ = compile_program('FOR i=1 TO 2 DO work ENDFOR', routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assert_uninitialized(program, 'I', 'J')

    def test_labelled_function_global_for_return(self):
        routine = 'ROUTINE first: INTEGER BEGIN GOTO work work:: FOR i=1 TO 2 DO RETURN i ENDFOR RETURN 0 END first'
        program, _ = compile_program('result=first()', routine)
        self.assertEqual(program.run()['RESULT'], 1)
        self.assert_uninitialized(program, 'I')


class ForReportAndCompatibilityTests(unittest.TestCase):
    def test_report_records_transitive_global_writes(self):
        routines = 'ROUTINE change(p: INTEGER) BEGIN p=7 END change\nROUTINE forward BEGIN change(seen) END forward\nROUTINE outer BEGIN forward END outer'
        _, result = compile_program('outer', routines)
        report = json.loads(json.dumps(result.report))
        self.assertEqual(report['routine_effects']['CHANGE']['potential_parameter_writes'], ['P'])
        self.assertEqual(report['routine_effects']['CHANGE']['potential_global_writes'], [])
        self.assertEqual(report['routine_effects']['OUTER']['potential_global_writes'], ['SEEN'])

    def test_report_distinguishes_local_shadow_from_global(self):
        _, result = compile_program('work', 'ROUTINE work VAR i: INTEGER BEGIN i=7 END work')
        self.assertEqual(result.report['routine_effects']['WORK']['potential_global_writes'], [])

    def test_report_describes_cleanup_and_read_only_reference(self):
        _, result = compile_program('FOR i=1 TO 2 DO inspect(i) ENDFOR', 'ROUTINE inspect(p: INTEGER) BEGIN seen=p END inspect')
        self.assertIn('finally clear', result.report['for_policy']['cleanup'])
        self.assertIn('read-only', result.report['for_policy']['counter_arguments'])
        self.assertIn('read-only active FOR counter reference', result.report['features'])
        self.assertFalse(result.report['for_policy']['controller_validated'])

    def test_legacy_global_call_and_reference_guards_remain(self):
        for body, routines in [('FOR i=1 TO 2 DO helper ENDFOR', 'ROUTINE helper BEGIN END helper'),
                               ('work', 'ROUTINE helper(p: INTEGER) BEGIN seen=p END helper\nROUTINE work VAR k: INTEGER BEGIN FOR k=1 TO 2 DO helper(k) ENDFOR END work')]:
            with self.subTest(body=body), self.assertRaises(TranslationError): compile_program(body, routines, translator=legacy_translate)

    def test_legacy_exception_keeps_old_observable_counter(self):
        program, _ = compile_program('FOR i=1 TO 2 DO result=1 DIV 0 ENDFOR', translator=legacy_translate)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['I'], 1)

    def test_authored_example_matches_independent_fixtures(self):
        source = Path(__file__).resolve().parents[1]/'examples/pythonic_for.kl'
        result = translate(source.read_text(), filename=source.name)
        namespace = {'__name__':'for_fixture'}
        exec(result.python_source, namespace)
        observed = []
        program = namespace['Program'](write=observed.append)
        self.assertEqual(program.run(), json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(observed, json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))
