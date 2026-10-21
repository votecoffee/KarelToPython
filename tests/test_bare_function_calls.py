"""Zero-parameter function names use the same checked call path as explicit calls."""
import ast
import json
import unittest

from karel2py import translate, runtime as rt
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from tests.test_structure_routines import initialized_host


ANSWER = 'ROUTINE answer: INTEGER BEGIN RETURN 7 END answer'
EFFECT = 'ROUTINE answer: INTEGER BEGIN n=n+1 RETURN 7 END answer'
ARRAY = 'ROUTINE build: ARRAY OF INTEGER VAR p: ARRAY[2] OF INTEGER BEGIN p[1]=7 p[2]=8 RETURN p END build'


def compile_program(body='x=answer', *, routines=ANSWER, declarations='x,y,n,i: INTEGER flag: BOOLEAN a: ARRAY[2] OF INTEGER',
                    types='', _translator=translate, **context):
    source = f'PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result = _translator(source, filename='bare_functions.kl')
    ast.parse(result.python_source, feature_version=(3, 11))
    json.dumps(result.report)
    namespace = {'__name__': 'bare_function_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](**context), result


def execute(*args, **kwargs): return compile_program(*args, **kwargs)[0].run()


class BareFunctionExecutionTests(unittest.TestCase):
    def test_integer_result(self):
        self.assertEqual(execute()['X'], 7)

    def test_pure_operator_operands(self):
        self.assertEqual(execute('x=answer+answer')['X'], 14)

    def test_boolean_condition_from_manual_pattern(self):
        routine = 'ROUTINE ready: BOOLEAN BEGIN RETURN ON END ready'
        self.assertEqual(execute('IF ready THEN x=7 ELSE x=9 ENDIF', routines=routine)['X'], 7)

    def test_real_result_in_single_argument_builtin(self):
        routine = 'ROUTINE measure: REAL BEGIN RETURN 1.25 END measure'
        self.assertEqual(execute('x=TRUNC(measure)', routines=routine)['X'], 1)

    def test_effectful_direct_assignment_evaluates_once(self):
        state = execute('n=0 x=answer', routines=EFFECT)
        self.assertEqual((state['N'], state['X']), (1, 7))

    def test_effectful_standalone_condition_evaluates_once(self):
        routine = 'ROUTINE ready: BOOLEAN BEGIN n=n+1 RETURN ON END ready'
        self.assertEqual(execute('n=0 IF ready THEN x=7 ENDIF', routines=routine)['N'], 1)

    def test_loop_condition_reinvokes_function(self):
        routine = 'ROUTINE more: BOOLEAN BEGIN n=n+1 RETURN n<3 END more'
        state = execute('n=0 x=0 WHILE more DO x=x+1 ENDWHILE', routines=routine)
        self.assertEqual((state['X'], state['N']), (2, 3))

    def test_repeat_condition_reinvokes_function(self):
        routine = 'ROUTINE done: BOOLEAN BEGIN RETURN n=3 END done'
        self.assertEqual(execute('n=0 REPEAT n=n+1 UNTIL done', routines=routine)['N'], 3)

    def test_scalar_return_forwarding(self):
        routine = ANSWER + '\nROUTINE outer: INTEGER BEGIN RETURN answer END outer'
        self.assertEqual(execute('x=outer', routines=routine)['X'], 7)

    def test_function_argument_is_an_independent_value(self):
        routine = ANSWER + '\nROUTINE touch(p: INTEGER) BEGIN x=p p=99 END touch'
        self.assertEqual(execute('touch(answer)', routines=routine)['X'], 7)

    def test_source_index_expression_invokes_function(self):
        routine = 'ROUTINE first: INTEGER BEGIN RETURN 1 END first'
        self.assertEqual(execute('a[1]=9 x=a[first]', routines=routine)['X'], 9)

    def test_select_selector_and_labelled_engine_parity(self):
        outcomes = []
        for marker in ('', 'unused:: '):
            program, _ = compile_program(marker + 'SELECT answer OF CASE(7): x=1 ELSE: x=2 ENDSELECT')
            outcomes.append((program.run(), program._state.steps))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0][0]['X'], 1)

    def test_bare_procedure_statement_keeps_existing_path(self):
        routine = 'ROUTINE set_value BEGIN x=9 END set_value'
        program, result = compile_program('set_value', routines=routine)
        self.assertEqual(program.run()['X'], 9)
        self.assertEqual(result.report['bare_function_calls'], [])

    def test_local_variable_shadows_function_value_name(self):
        routine = ANSWER + '\nROUTINE outer: INTEGER VAR answer: INTEGER BEGIN answer=9 RETURN answer END outer'
        program, result = compile_program('x=outer', routines=routine)
        self.assertEqual(program.run()['X'], 9)
        self.assertEqual([row['name'] for row in result.report['bare_function_calls']], ['OUTER'])

    def test_parameter_shadows_function_value_name(self):
        routine = ANSWER + '\nROUTINE outer(answer: INTEGER): INTEGER BEGIN RETURN answer END outer'
        program, result = compile_program('x=outer(9)', routines=routine)
        self.assertEqual(program.run()['X'], 9)
        self.assertEqual(result.report['bare_function_calls'], [])

    def test_using_field_resolution_precedes_function_names(self):
        types = 'TYPE box_t=STRUCTURE answer: INTEGER ENDSTRUCTURE'
        state = execute('box.answer=9 USING box DO x=answer ENDUSING y=answer',
                        types=types, declarations='box: box_t x,y: INTEGER')
        self.assertEqual((state['X'], state['Y']), (9, 7))

    def test_local_array_receiver_shadows_function_name(self):
        routine = ANSWER + '\nROUTINE outer: INTEGER VAR answer: ARRAY[1] OF INTEGER BEGIN answer[1]=9 RETURN answer[1] END outer'
        self.assertEqual(execute('x=outer', routines=routine)['X'], 9)

    def test_array_direct_assignment_retains_independent_copy(self):
        state = execute('a=build b=copy a[1]=99', routines=ARRAY + '\nROUTINE copy: ARRAY OF INTEGER BEGIN RETURN a END copy',
                        declarations='a,b: ARRAY[2] OF INTEGER')
        self.assertEqual((state['A'], state['B']), ([99, 8], [7, 8]))

    def test_named_component_array_result(self):
        types = 'TYPE row_t=ARRAY[2] OF INTEGER'
        routine = 'ROUTINE build: ARRAY OF row_t VAR p: ARRAY[1] OF row_t BEGIN p[1,1]=7 p[1,2]=8 RETURN p END build'
        self.assertEqual(execute('a=build', types=types, declarations='a: ARRAY[1] OF row_t', routines=routine)['A'], [[7, 8]])

    def test_structure_result_and_value_passing(self):
        types = 'TYPE item_t=STRUCTURE n: INTEGER ENDSTRUCTURE'
        routine = 'ROUTINE build: item_t VAR p: item_t BEGIN p.n=7 RETURN p END build\nROUTINE touch(p: item_t) BEGIN x=p.n p.n=99 END touch'
        state = execute('a=build touch(build)', types=types, declarations='a: item_t x: INTEGER', routines=routine)
        self.assertEqual((state['A'], state['X']), ({'N': 7}, 7))

    def test_exact_record_and_joint_results_retain_ownership(self):
        types = [(kind, (kind,)) for kind in rt.DATA_RECORD_TYPES]
        types += [(f'JOINTPOS{n}', ('JOINTPOS', n)) for n in range(1, 10)]
        for spelling, spec in types:
            with self.subTest(spelling=spelling):
                routine = f'ROUTINE build: {spelling} BEGIN RETURN a END build'
                program, _ = compile_program('b=build', routines=routine, declarations=f'a,b: {spelling}')
                program._state.values['A'] = initialized_host(spec)
                state = program.run()
                self.assertEqual(state['A'], state['B'])
                self.assertIsNot(program._state.raw('A'), program._state.raw('B'))

    def test_explicit_empty_parentheses_remain_accepted(self):
        program, result = compile_program('x=answer()')
        self.assertEqual(program.run()['X'], 7)
        self.assertEqual(result.report['bare_function_calls'], [])

    def test_forward_internal_declaration_resolves(self):
        routines = 'ROUTINE outer: INTEGER BEGIN RETURN answer END outer\n' + ANSWER
        self.assertEqual(execute('x=outer', routines=routines)['X'], 7)

    def test_call_inside_for_with_fresh_local_counter(self):
        routines = ANSWER + '\nROUTINE loop VAR j: INTEGER BEGIN FOR j=1 TO 2 DO x=answer ENDFOR END loop'
        self.assertEqual(execute('loop', routines=routines)['X'], 7)

    def test_report_retains_original_call_location_and_result_spec(self):
        _, result = compile_program()
        row = result.report['bare_function_calls'][0]
        self.assertEqual((row['body'], row['name'], row['result_spec']), ('T', 'ANSWER', rt.INTEGER))
        self.assertEqual((row['line'], row['column']), (6, 3))
        self.assertIn('bare zero-argument function call', result.report['features'])
        self.assertFalse(result.report['bare_function_policy']['controller_validated'])


class BareFunctionRejectionTests(unittest.TestCase):
    def reject(self, code, body='x=answer', **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_parameterized_function_requires_arguments(self):
        self.reject('E_ARGUMENTS', routines='ROUTINE answer(p: INTEGER): INTEGER BEGIN RETURN p END answer')

    def test_procedure_cannot_be_used_as_value(self):
        self.reject('E_TYPE', routines='ROUTINE answer BEGIN END answer')

    def test_unknown_names_still_reject(self):
        self.reject('E_SYMBOL', 'x=missing')

    def test_builtin_names_do_not_become_bare_calls(self):
        self.reject('E_SYMBOL', 'x=ROUND')

    def test_function_name_does_not_become_assignment_storage(self):
        self.reject('E_SYMBOL', 'answer=1')

    def test_field_receiver_is_not_implicitly_called(self):
        self.reject('E_SYMBOL', 'x=answer.x', routines='ROUTINE answer: VECTOR VAR p: VECTOR BEGIN RETURN p END answer')

    def test_array_receiver_is_not_implicitly_called(self):
        self.reject('E_SYMBOL', 'x=build[1]', routines=ARRAY)

    def test_assignment_target_subscript_call_rejected(self):
        self.reject('E_EVALUATION_ORDER', 'a[answer]=1', _translator=legacy_translate)

    def test_effectful_operator_operand_rejected(self):
        self.reject('E_EVALUATION_ORDER', 'x=answer+1', routines=EFFECT, _translator=legacy_translate)

    def test_transitive_effectful_operator_operand_rejected(self):
        routine = EFFECT + '\nROUTINE outer: INTEGER BEGIN RETURN answer END outer'
        self.reject('E_EVALUATION_ORDER', 'x=outer+1', routines=routine, _translator=legacy_translate)

    def test_boolean_operator_call_rejected_even_when_pure(self):
        routine = 'ROUTINE ready: BOOLEAN BEGIN RETURN ON END ready'
        self.reject('E_EVALUATION_ORDER', 'flag=ready AND ON', routines=routine, _translator=legacy_translate)

    def test_multiple_argument_order_guards_see_bare_calls(self):
        routine = ANSWER + '\nROUTINE use(first,second: INTEGER) BEGIN END use'
        self.reject('E_EVALUATION_ORDER', 'use(answer,1)', routines=routine, _translator=legacy_translate)

    def test_multi_argument_builtin_order_guard_sees_bare_calls(self):
        self.reject('E_EVALUATION_ORDER', 'x=ATAN2(answer,1)', _translator=legacy_translate)

    def test_multiple_subscript_guard_sees_bare_calls(self):
        self.reject('E_EVALUATION_ORDER', 'x=a[answer,1]', declarations='x: INTEGER a: ARRAY[7,1] OF INTEGER', _translator=legacy_translate)

    def test_for_bounds_guard_sees_bare_calls(self):
        self.reject('E_EVALUATION_ORDER', 'FOR i=1 TO answer DO x=1 ENDFOR', _translator=legacy_translate)

    def test_for_global_counter_call_guard_sees_bare_calls(self):
        self.reject('E_FOR_COUNTER', 'FOR i=1 TO 2 DO x=answer ENDFOR', _translator=legacy_translate)

    def test_effectful_rhs_to_indexed_target_rejected(self):
        self.reject('E_EVALUATION_ORDER', 'a[1]=answer', routines=EFFECT, _translator=legacy_translate)

    def test_transitive_delay_and_output_are_not_hidden(self):
        for statement in ('DELAY 1', "WRITE('x')", 'ABORT'):
            with self.subTest(statement=statement):
                routine = f'ROUTINE answer: INTEGER BEGIN {statement} RETURN 7 END answer\nROUTINE outer: INTEGER BEGIN RETURN answer END outer'
                self.reject('E_EVALUATION_ORDER', 'x=outer+1', routines=routine, _translator=legacy_translate)

    def test_array_context_rules_apply_to_bare_calls(self):
        for body in ('a=(build)', 'a=build+1', 'x=ARRAY_LEN(build)', 'IF build THEN x=1 ENDIF'):
            with self.subTest(body=body): self.reject('E_ARRAY_RESULT_CONTEXT', body, routines=ARRAY, _translator=legacy_translate)

    def test_array_result_forwarding_still_rejected(self):
        routine = ARRAY + '\nROUTINE copy: ARRAY OF INTEGER BEGIN RETURN build END copy'
        self.reject('E_ARRAY_RESULT_CONTEXT', 'a=copy', routines=routine, _translator=legacy_translate)

    def test_array_result_as_argument_still_rejected(self):
        routine = ARRAY + '\nROUTINE use(p: ARRAY OF INTEGER) BEGIN END use'
        self.reject('E_ARRAY_RESULT_CONTEXT', 'use(build)', routines=routine, _translator=legacy_translate)

    def test_uninit_does_not_consume_a_function_value(self):
        self.reject('E_ARGUMENTS', 'flag=UNINIT(answer)')

    def test_local_constant_name_collision_keeps_existing_rejection(self):
        routine = ANSWER + '\nROUTINE outer: INTEGER CONST answer=9 BEGIN RETURN answer END outer'
        self.reject('E_LOCAL_CONST_SHADOW', 'x=outer', routines=routine)

    def test_case_values_remain_compile_time_constants(self):
        self.reject('E_CONSTANT', 'SELECT 7 OF CASE(answer): x=1 ENDSELECT')


class BareFunctionFailureTests(unittest.TestCase):
    def test_abort_retains_prior_effects_and_unwinds_frames(self):
        routine = 'ROUTINE answer: INTEGER BEGIN n=9 ABORT RETURN 7 END answer'
        program, _ = compile_program('x=3 x=answer', routines=routine)
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual((program.snapshot()['X'], program.snapshot()['N']), (3, 9))
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_recursive_bare_calls_obey_depth_limit(self):
        routine = 'ROUTINE answer: INTEGER BEGIN RETURN answer END answer'
        program, _ = compile_program(routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'depth'): program.run()
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_indirect_recursive_bare_calls_obey_depth_limit(self):
        routine = 'ROUTINE answer: INTEGER BEGIN RETURN other END answer\nROUTINE other: INTEGER BEGIN RETURN answer END other'
        program, _ = compile_program(routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'depth'): program.run()
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_fallthrough_is_source_located_and_leaves_destination(self):
        program, _ = compile_program('x=3 x=answer', routines='ROUTINE answer: INTEGER BEGIN END answer')
        with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
        self.assertIsNotNone(caught.exception.line)
        self.assertEqual(program.snapshot()['X'], 3)
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_array_uninitialized_failure_precedes_assignment(self):
        routine = ARRAY.replace('p[2]=8', 'n=9')
        program, _ = compile_program('a[1]=1 a[2]=2 a=build', routines=routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['A'], program.snapshot()['N']), ([1, 2], 9))
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))


if __name__ == '__main__':
    unittest.main()
