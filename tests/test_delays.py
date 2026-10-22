"""Host-delay ordering, zero/range semantics and injected-clock failure boundaries."""
import ast
import unittest
from unittest.mock import patch

from karel2py import translate
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


def compile_program(body, routines='', prefix='', declarations='x,y,result,i: INTEGER\nflag: BOOLEAN\na: ARRAY[2] OF INTEGER', *, _translator=translate):
    source = f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    generated = _translator(source, filename='delays.kl')
    ast.parse(generated.python_source, feature_version=(3, 11))
    namespace = {'__name__': 'delay_test'}
    exec(generated.python_source, namespace)
    return namespace['Program'], generated


def execute(body, **kwargs):
    cls, report = compile_program(body, **kwargs)
    calls = []
    program = cls(sleep=calls.append)
    return program.run(), calls, program, report


class DelayBehaviorTests(unittest.TestCase):
    def test_positive_milliseconds_converted_to_seconds(self):
        state, calls, _, _ = execute('x=1 DELAY 125 x=2')
        self.assertEqual((state['X'], calls), (2, [0.125]))

    def test_zero_does_not_call_sleeper(self):
        self.assertEqual(execute('DELAY 0 x=7')[1], [])

    def test_one_millisecond(self):
        self.assertEqual(execute('DELAY 1')[1], [0.001])

    def test_last_millisecond_before_day(self):
        self.assertEqual(execute('DELAY 86399999')[1], [86399.999])

    def test_one_day_is_allowed_with_fake_sleep(self):
        self.assertEqual(execute('DELAY 86400000')[1], [86400.0])

    def test_default_sleeper_uses_python_time_sleep(self):
        cls, _ = compile_program('DELAY 125')
        with patch.object(rt.time, 'sleep') as sleeper:
            sleeper.return_value = None
            cls().run()
        sleeper.assert_called_once_with(0.125)

    def test_default_zero_does_not_yield_host_thread(self):
        cls, _ = compile_program('DELAY 0')
        with patch.object(rt.time, 'sleep') as sleeper:
            cls().run()
        sleeper.assert_not_called()

    def test_none_selects_default_sleeper(self):
        cls, _ = compile_program('DELAY 125')
        with patch.object(rt.time, 'sleep') as sleeper:
            sleeper.return_value = None
            cls(sleep=None).run()
        sleeper.assert_called_once_with(0.125)

    def test_injected_sleeper_does_not_call_default(self):
        cls, _ = compile_program('DELAY 125')
        calls = []
        with patch.object(rt.time, 'sleep') as sleeper:
            cls(sleep=calls.append).run()
        self.assertEqual(calls, [0.125])
        sleeper.assert_not_called()

    def test_expression_evaluated_once(self):
        state, calls, _, _ = execute('x=1 DELAY duration() y=x', routines='ROUTINE duration: INTEGER BEGIN x=x+1 RETURN x*10 END duration')
        self.assertEqual((state['X'], state['Y'], calls), (2, 2, [0.02]))

    def test_duration_reads_old_value_before_sleeper_changes_it(self):
        cls, _ = compile_program('x=125 DELAY x y=x')
        calls = []
        def sleeper(seconds):
            calls.append(seconds)
            program._state.set('X', 7)
        program = cls(sleep=sleeper)
        state = program.run()
        self.assertEqual((calls, state['Y']), ([0.125], 7))

    def test_statement_write_order_around_delay(self):
        cls, _ = compile_program('x=1 DELAY 125 x=2')
        seen = []
        def sleeper(seconds): seen.append((seconds, program._state.get('X')))
        program = cls(sleep=sleeper)
        self.assertEqual(program.run()['X'], 2)
        self.assertEqual(seen, [(0.125, 1)])

    def test_global_constant_duration(self):
        self.assertEqual(execute('DELAY wait_ms', prefix='CONST wait_ms=125')[1], [0.125])

    def test_local_constant_duration(self):
        self.assertEqual(execute('work', routines='ROUTINE work CONST wait_ms=125 BEGIN DELAY wait_ms END work')[1], [0.125])

    def test_short_duration_promotes_to_integer(self):
        self.assertEqual(execute('shorts[1]=125 DELAY shorts[1]', declarations='shorts: ARRAY[1] OF SHORT')[1], [0.125])

    def test_byte_duration_promotes_to_integer(self):
        self.assertEqual(execute('bytes[1]=125 DELAY bytes[1]', declarations='bytes: ARRAY[1] OF BYTE')[1], [0.125])

    def test_array_element_duration(self):
        self.assertEqual(execute('a[2]=125 DELAY a[2]')[1], [0.125])

    def test_using_qualified_duration(self):
        self.assertEqual(execute('record.wait_ms=125 USING record DO DELAY wait_ms ENDUSING', prefix='TYPE item_t=STRUCTURE wait_ms: INTEGER ENDSTRUCTURE', declarations='record: item_t')[1], [0.125])

    def test_named_subarray_duration_element(self):
        self.assertEqual(execute('a[2,1]=125 DELAY a[2,1]', prefix='TYPE row_t=ARRAY[2] OF INTEGER', declarations='a: ARRAY[2] OF row_t')[1], [0.125])

    def test_parenthesized_expression(self):
        self.assertEqual(execute('DELAY (100+25)')[1], [0.125])

    def test_false_branch_does_not_delay(self):
        self.assertEqual(execute('IF OFF THEN DELAY 125 ENDIF')[1], [])

    def test_matching_select_case_only_delays(self):
        self.assertEqual(execute('SELECT 2 OF CASE(1): DELAY 100 CASE(2): DELAY 125 ENDSELECT')[1], [0.125])

    def test_repeat_and_while_delays(self):
        _, calls, _, _ = execute('x=0 REPEAT DELAY 10 x=x+1 UNTIL x=2 WHILE x<4 DO DELAY 20 x=x+1 ENDWHILE')
        self.assertEqual(calls, [0.01, 0.01, 0.02, 0.02])

    def test_delay_in_global_for_without_routine_call(self):
        state, calls, _, _ = execute('FOR i=1 TO 3 DO DELAY i ENDFOR flag=UNINIT(i)')
        self.assertEqual(calls, [0.001, 0.002, 0.003])
        self.assertTrue(state['FLAG'])

    def test_procedure_delay_in_local_for(self):
        routines = 'ROUTINE pause_ms(p: INTEGER) BEGIN DELAY p END pause_ms\nROUTINE work VAR k: INTEGER BEGIN FOR k=1 TO 3 DO pause_ms((k)) ENDFOR END work'
        self.assertEqual(execute('work', routines=routines)[1], [0.001, 0.002, 0.003])

    def test_delay_before_early_local_for_return(self):
        routines = 'ROUTINE work: INTEGER VAR k: INTEGER BEGIN FOR k=1 TO 3 DO DELAY k RETURN k ENDFOR RETURN 0 END work'
        state, calls, program, _ = execute('result=work()', routines=routines)
        self.assertEqual((state['RESULT'], calls, program._state.local_frames), (1, [0.001], []))

    def test_label_dispatcher_skips_delay(self):
        self.assertEqual(execute('GOTO done DELAY 125 done:: x=7')[1], [])

    def test_label_dispatcher_repeats_delay(self):
        self.assertEqual(execute('x=0 again:: DELAY 10 x=x+1 IF x<3 THEN GOTO again ENDIF')[1], [0.01]*3)

    def test_recursive_routine_delay(self):
        routines = 'ROUTINE work(n: INTEGER) BEGIN IF n=0 THEN RETURN ENDIF DELAY n work(n-1) END work'
        self.assertEqual(execute('work(3)', routines=routines)[1], [0.003, 0.002, 0.001])

    def test_nested_duration_delays_have_defined_sequence(self):
        routines = 'ROUTINE duration: INTEGER BEGIN DELAY 10 RETURN 20 END duration'
        self.assertEqual(execute('DELAY duration()', routines=routines)[1], [0.01, 0.02])

    def test_function_delay_in_standalone_scalar_assignment(self):
        routines = 'ROUTINE work: INTEGER BEGIN DELAY 125 RETURN 7 END work'
        state, calls, _, _ = execute('result=work()', routines=routines)
        self.assertEqual((state['RESULT'], calls), (7, [0.125]))

    def test_pure_duration_function_inside_arithmetic(self):
        routines = 'ROUTINE duration: INTEGER BEGIN RETURN 100 END duration'
        self.assertEqual(execute('DELAY duration()+25', routines=routines)[1], [0.125])

    def test_program_instances_have_separate_sleepers(self):
        cls, _ = compile_program('DELAY 125')
        first, second = [], []
        cls(sleep=first.append).run()
        self.assertEqual((first, second), ([0.125], []))
        cls(sleep=second.append).run()
        self.assertEqual((first, second), ([0.125], [0.125]))

    def test_rerun_retains_state_and_same_sleeper(self):
        cls, _ = compile_program('IF UNINIT(x) THEN x=0 ENDIF x=x+1 DELAY x')
        calls = []
        program = cls(sleep=calls.append)
        self.assertEqual(program.run()['X'], 1)
        self.assertEqual(program.run()['X'], 2)
        self.assertEqual(calls, [0.001, 0.002])

    def test_report_scope_locations_and_timing_effects(self):
        _, generated = compile_program('DELAY 0 work', routines='ROUTINE work\nBEGIN\nDELAY 125\nEND work')
        self.assertEqual({row['body'] for row in generated.report['delays']}, {'WORK', 'T'})
        self.assertIn('DELAY', generated.report['features'])
        self.assertTrue(generated.report['routine_effects']['WORK']['potential_host_delays'])
        self.assertFalse(generated.report['routine_effects']['WORK']['potential_external_writes'])
        self.assertFalse(generated.report['delay_policy']['controller_validated'])

    def test_continuation_preserves_statement_line(self):
        _, generated = compile_program('DELAY &\n 125')
        self.assertEqual((generated.report['delays'][0]['line'], generated.report['delays'][0]['column']), (8, 1))


class DelayFailureTests(unittest.TestCase):
    def fail_duration(self, expression, declarations=None, setup=''):
        kwargs = {'declarations': declarations} if declarations else {}
        cls, _ = compile_program('x=7 '+setup+' DELAY '+expression+' x=9', **kwargs)
        calls = []
        program = cls(sleep=calls.append)
        with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
        self.assertEqual(calls, [])
        self.assertEqual(program._state.snapshot()['X'], 7)
        return caught.exception

    def test_negative_duration(self): self.fail_duration('-1')
    def test_beyond_one_day(self): self.fail_duration('86400001')
    def test_maxint_duration(self): self.fail_duration('MAXINT')
    def test_minint_duration(self): self.fail_duration('MININT')
    def test_uninitialized_duration(self): self.fail_duration('y')
    def test_uninitialized_short_duration(self): self.fail_duration('shorts[1]', 'x: INTEGER shorts: ARRAY[1] OF SHORT')
    def test_unknown_byte_duration(self): self.fail_duration('bytes[1]', 'x: INTEGER bytes: ARRAY[1] OF BYTE')
    def test_out_of_bounds_duration_element(self): self.fail_duration('a[3]')
    def test_integer_overflow_in_duration(self): self.fail_duration('MAXINT+1')
    def test_divide_by_zero_in_duration(self): self.fail_duration('1 DIV 0')

    def test_source_located_runtime_range_error(self):
        error = self.fail_duration('86400001')
        self.assertEqual(error.line, 8)

    def test_sleeper_exception_is_source_located_and_chained(self):
        cls, _ = compile_program('work x=9', routines='ROUTINE work BEGIN x=7 DELAY 125 END work')
        original = OSError('clock failure')
        def fail(seconds): raise original
        program = cls(sleep=fail)
        with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
        self.assertIs(caught.exception.__cause__, original)
        self.assertEqual(caught.exception.line, 6)
        self.assertEqual(program._state.snapshot()['X'], 7)
        self.assertEqual(program._state.local_frames, [])

    def test_bad_sleeper_result_is_rejected_after_prior_write(self):
        cls, _ = compile_program('x=7 DELAY 125 x=9')
        program = cls(sleep=lambda seconds: 5)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'return None'): program.run()
        self.assertEqual(program._state.snapshot()['X'], 7)

    def test_keyboard_interrupt_is_not_wrapped_and_unwinds(self):
        cls, _ = compile_program('work', routines='ROUTINE work BEGIN DELAY 125 END work')
        def interrupt(seconds): raise KeyboardInterrupt()
        program = cls(sleep=interrupt)
        with self.assertRaises(KeyboardInterrupt): program.run()
        self.assertEqual(program._state.local_frames, [])

    def test_step_budget_fails_before_sleep(self):
        cls, _ = compile_program('x=7 DELAY 125')
        calls = []
        program = cls(sleep=calls.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'step budget'): program.run(max_steps=1)
        self.assertEqual(calls, [])
        self.assertEqual(program._state.snapshot()['X'], 7)

    def test_fake_delay_loop_still_has_step_budget(self):
        cls, _ = compile_program('WHILE ON DO DELAY 125 ENDWHILE')
        calls = []
        program = cls(sleep=calls.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'step budget'): program.run(max_steps=6)
        self.assertGreater(len(calls), 0)

    def test_sleep_configuration_requires_callable(self):
        cls, _ = compile_program('DELAY 0')
        with self.assertRaises(TypeError): cls(sleep=5)

    def test_native_runtime_rejects_bool(self):
        state = rt.State({}, {}, sleep=lambda seconds: None)
        with self.assertRaises(rt.KarelRuntimeError): state.delay(True, 12)

    def test_native_runtime_rejects_float(self):
        state = rt.State({}, {}, sleep=lambda seconds: None)
        with self.assertRaises(rt.KarelRuntimeError): state.delay(1.0, 12)

    def test_native_runtime_rejects_string(self):
        state = rt.State({}, {}, sleep=lambda seconds: None)
        with self.assertRaises(rt.KarelRuntimeError): state.delay('1', 12)


class DelayRejectionTests(unittest.TestCase):
    def reject(self, body, code, **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_real_duration(self): self.reject('DELAY 1.25', 'E_TYPE')
    def test_boolean_duration(self): self.reject('DELAY ON', 'E_TYPE')
    def test_string_duration(self): self.reject("DELAY '125'", 'E_TYPE')
    def test_array_duration(self): self.reject('DELAY a', 'E_TYPE')
    def test_structure_duration(self): self.reject('DELAY record', 'E_TYPE', prefix='TYPE item_t=STRUCTURE x: INTEGER ENDSTRUCTURE', declarations='record: item_t')
    def test_unknown_duration(self): self.reject('DELAY missing', 'E_SYMBOL')
    def test_expression_result_delay(self): self.reject('x=DELAY(125)', 'E_EXPRESSION')
    def test_missing_duration(self): self.reject('DELAY\nEND T', 'E_EXPRESSION')
    def test_predefined_minimum_literal_rule(self): self.reject('DELAY -2147483648', 'E_MININT_LITERAL')
    def test_directive_delay_remains_blocked(self): self.reject('x=7', 'E_DIRECTIVE', prefix='%DELAY=0')
    def test_incomplete_condition_handler_rejected(self): self.reject('CONDITION[1]:', 'E_SYNTAX')
    def test_motion_hold_remains_blocked(self): self.reject('HOLD', 'E_UNSUPPORTED')
    def test_task_targeted_abort_remains_blocked(self): self.reject('ABORT PROGRAM[1]', 'E_ABORT_TARGET')

    def test_delay_function_inside_operator_blocked(self):
        self.reject('x=1+wait_value()', 'E_EVALUATION_ORDER', routines='ROUTINE wait_value: INTEGER BEGIN DELAY 125 RETURN 7 END wait_value', _translator=legacy_translate)

    def test_transitive_delay_function_inside_operator_blocked(self):
        routines = 'ROUTINE sleeper BEGIN DELAY 125 END sleeper\nROUTINE wait_value: INTEGER BEGIN sleeper RETURN 7 END wait_value'
        self.reject('x=1+wait_value()', 'E_EVALUATION_ORDER', routines=routines, _translator=legacy_translate)

    def test_recursive_effect_propagation(self):
        routines = 'ROUTINE first(n: INTEGER): INTEGER BEGIN IF n=0 THEN DELAY 125 RETURN 7 ENDIF RETURN second(n-1) END first\nROUTINE second(n: INTEGER): INTEGER BEGIN RETURN first(n) END second'
        self.reject('x=1+second(3)', 'E_EVALUATION_ORDER', routines=routines, _translator=legacy_translate)

    def test_delay_function_inside_comparison_blocked(self):
        self.reject('flag=wait_value()>0', 'E_EVALUATION_ORDER', routines='ROUTINE wait_value: INTEGER BEGIN DELAY 125 RETURN 7 END wait_value', _translator=legacy_translate)

    def test_delay_function_to_indexed_target_blocked(self):
        self.reject('a[1]=wait_value()', 'E_EVALUATION_ORDER', routines='ROUTINE wait_value: INTEGER BEGIN DELAY 125 RETURN 7 END wait_value', _translator=legacy_translate)

    def test_delaying_duration_function_inside_operator_blocked(self):
        self.reject('DELAY wait_value()+1', 'E_EVALUATION_ORDER', routines='ROUTINE wait_value: INTEGER BEGIN DELAY 125 RETURN 7 END wait_value', _translator=legacy_translate)

    def test_delay_function_in_global_for_remains_blocked(self):
        self.reject('FOR i=1 TO 2 DO DELAY duration() ENDFOR', 'E_FOR_COUNTER', routines='ROUTINE duration: INTEGER BEGIN RETURN 125 END duration', _translator=legacy_translate)

    def test_multiple_arguments_with_delaying_call_remain_blocked(self):
        routines = 'ROUTINE wait_value: INTEGER BEGIN DELAY 125 RETURN 7 END wait_value\nROUTINE use(p,q: INTEGER) BEGIN END use'
        self.reject('use(wait_value(),1)', 'E_EVALUATION_ORDER', routines=routines, _translator=legacy_translate)


if __name__ == '__main__': unittest.main()
