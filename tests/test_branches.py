"""Statement transfer, scope boundaries, execution guards and structured-flow parity."""
from pathlib import Path
import unittest

from karel2py import translate
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from karel2py.runtime import KarelRuntimeError


DECLARATIONS = 'x,y,i,total,visits,result: INTEGER\nb,flag: BOOLEAN\na: ARRAY[2] OF INTEGER'


def compile_program(body, routines='', declarations=DECLARATIONS, extra='', *, _translator=translate):
    source = f'PROGRAM T\n{extra}\nVAR\n{declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result = _translator(source, filename='branches.kl')
    namespace = {'__name__': 'branch_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, routines='', **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


class LabelTransferTests(unittest.TestCase):
    def test_forward_go_to_skips_assignment(self):
        self.assertEqual(execute('x = 1 GO TO finished x = 2 finished:: y = x')['Y'], 1)

    def test_goto_spelling_and_case_insensitive_label(self):
        self.assertEqual(execute('goto FiNiShEd x = 2 finished:: x = 7')['X'], 7)

    def test_backward_jump_loop(self):
        state = execute('x = 0 again:: x = x + 1 IF x < 4 THEN GOTO again ENDIF y = x')
        self.assertEqual((state['X'], state['Y']), (4, 4))

    def test_consecutive_labels_share_following_statement(self):
        self.assertEqual(execute('GOTO second first:: second:: x = 7')['X'], 7)

    def test_label_at_end_finishes_program_body(self):
        self.assertEqual(execute('x = 1 GOTO finished x = 2 finished::')['X'], 1)

    def test_label_with_no_jumps_is_noop(self):
        p, _ = compile_program('first:: x = 7 last::')
        self.assertEqual(p.run()['X'], 7)
        self.assertEqual(p._state.steps, 1)

    def test_labels_only_body_has_no_executable_steps(self):
        p, _ = compile_program('first:: second::')
        self.assertEqual(p.run()['X'], {'uninitialized': True})
        self.assertEqual(p._state.steps, 0)

    def test_semicolon_and_newline_after_label(self):
        self.assertEqual(execute('GO TO finished\nx = 2\nfinished::;\nx = 7')['X'], 7)

    def test_same_block_jump_skips_faulting_read(self):
        state = execute('IF TRUE THEN GOTO safe x = y safe:: x = 7 ENDIF')
        self.assertEqual(state['X'], 7)

    def test_jump_out_of_if_then(self):
        state = execute('x = 1 IF TRUE THEN GOTO finished x = 2 ENDIF x = 3 finished:: y = x')
        self.assertEqual((state['X'], state['Y']), (1, 1))

    def test_jump_out_of_if_else(self):
        self.assertEqual(execute('IF FALSE THEN x = 1 ELSE x = 7 GOTO finished ENDIF x = 2 finished::')['X'], 7)

    def test_jump_out_of_nested_blocks(self):
        self.assertEqual(execute('WHILE TRUE DO IF TRUE THEN x = 7 GOTO finished ENDIF ENDWHILE x = 2 finished::')['X'], 7)

    def test_jump_to_ancestor_loop_body_label(self):
        state = execute('x = 0 WHILE x < 3 DO again:: x = x + 1 IF x < 3 THEN GOTO again ENDIF ENDWHILE y = x')
        self.assertEqual(state['Y'], 3)

    def test_jump_out_of_repeat_skips_until_read(self):
        self.assertEqual(execute('REPEAT x = 7 GOTO finished UNTIL b finished::')['X'], 7)

    def test_jump_out_of_select_case(self):
        body = 'SELECT 1 OF CASE(1): x = 7 GOTO finished CASE(2): x = 9 ELSE: x = 8 ENDSELECT x = 3 finished::'
        self.assertEqual(execute(body)['X'], 7)

    def test_jump_out_of_select_else(self):
        body = 'SELECT 3 OF CASE(1): x = 7 ELSE: x = 8 GOTO finished ENDSELECT x = 3 finished::'
        self.assertEqual(execute(body)['X'], 8)

    def test_loop_around_atomic_for_clears_counter_each_time(self):
        body = 'total = 0 visits = 0 again:: FOR i = 1 TO 2 DO total = total + i ENDFOR flag = UNINIT(i) visits = visits + 1 IF visits < 2 THEN GOTO again ENDIF'
        state = execute(body)
        self.assertEqual((state['TOTAL'], state['VISITS'], state['FLAG']), (6, 2, True))

    def test_jump_can_skip_entire_for_statement(self):
        self.assertEqual(execute('i = 9 GOTO finished FOR i = 1 TO 2 DO x = 7 ENDFOR finished:: result = i')['RESULT'], 9)

    def test_for_body_remains_checked_when_dispatcher_used(self):
        state = execute('unused:: total = 0 FOR i = 2 DOWNTO 1 DO total = total + i ENDFOR flag = UNINIT(i)')
        self.assertEqual((state['TOTAL'], state['FLAG']), (3, True))

    def test_pure_jump_cycle_has_step_budget(self):
        p, _ = compile_program('again:: GOTO again')
        with self.assertRaisesRegex(KarelRuntimeError, 'step budget'): p.run(max_steps=12)
        self.assertEqual(p._state.steps, 13)

    def test_runtime_failure_still_names_karel_line(self):
        p, _ = compile_program('GOTO fail\nfail:: x = 1 DIV 0')
        with self.assertRaisesRegex(KarelRuntimeError, 'KAREL line .*zero') as caught: p.run()
        self.assertIsNotNone(caught.exception.line)

    def test_graph_report_records_labels_and_jump_edges(self):
        _, result = compile_program('GOTO finished x = 7 finished::')
        graph = result.report['control_flow']['program']
        self.assertEqual(graph['engine'], 'label_dispatcher')
        jump = next(node for node in graph['nodes'] if node['kind'] == 'goto')
        self.assertEqual(jump['successors'], [graph['labels']['FINISHED']])
        self.assertTrue(all(node['karel_line'] > 0 for node in graph['nodes']))

    def test_no_labels_keep_structured_python_engine(self):
        _, result = compile_program('x = 7')
        self.assertEqual(result.report['control_flow']['program']['engine'], 'structured_python')

    def test_report_source_map_covers_jump_and_label(self):
        _, result = compile_program('GOTO finished\nfinished:: x = 7')
        graph = result.report['control_flow']['program']
        mapped = {row['karel_line'] for row in result.report['source_map']}
        for node in graph['nodes']: self.assertIn(node['karel_line'], mapped)


class RoutineBranchTests(unittest.TestCase):
    def test_procedure_jump_reaches_return_and_unwinds(self):
        routine = 'ROUTINE work BEGIN GOTO done x = 7 done:: RETURN END work'
        p, _ = compile_program('x = 1 work y = x', routine)
        self.assertEqual(p.run()['Y'], 1)
        self.assertEqual((p._state.local_frames, p._state.call_depth), ([], 0))

    def test_function_jump_returns_value(self):
        routine = 'ROUTINE compute: INTEGER BEGIN GOTO done RETURN 9 done:: RETURN 7 END compute'
        self.assertEqual(execute('result = compute()', routine)['RESULT'], 7)

    def test_function_jump_to_end_still_requires_return(self):
        routine = 'ROUTINE compute: INTEGER BEGIN GOTO done RETURN 9 done:: END compute'
        p, _ = compile_program('result = compute()', routine)
        with self.assertRaisesRegex(KarelRuntimeError, 'without RETURN'): p.run()
        self.assertEqual((p._state.local_frames, p._state.call_depth), ([], 0))

    def test_same_label_name_in_different_bodies(self):
        routines = 'ROUTINE first BEGIN GOTO done x = 9 done:: x = 7 END first\nROUTINE second BEGIN GOTO done y = 9 done:: y = 8 END second'
        state = execute('GOTO done x = 1 done:: first second', routines)
        self.assertEqual((state['X'], state['Y']), (7, 8))

    def test_reference_parameter_updates_through_backward_jumps(self):
        routine = 'ROUTINE increment(p: INTEGER) BEGIN again:: p = p + 1 IF p < 3 THEN GOTO again ENDIF END increment'
        self.assertEqual(execute('x = 0 increment(x)', routine)['X'], 3)

    def test_parenthesized_value_parameter_stays_independent(self):
        routine = 'ROUTINE increment(p: INTEGER) BEGIN again:: p = p + 1 IF p < 3 THEN GOTO again ENDIF result = p END increment'
        state = execute('x = 0 increment((x))', routine)
        self.assertEqual((state['X'], state['RESULT']), (0, 3))

    def test_recursive_dispatcher_has_per_call_control_state(self):
        routine = 'ROUTINE factorial(n: INTEGER): INTEGER BEGIN IF n <= 1 THEN GOTO base ENDIF RETURN n * factorial(n - 1) base:: RETURN 1 END factorial'
        self.assertEqual(execute('result = factorial(5)', routine)['RESULT'], 120)

    def test_jump_loop_budget_failure_unwinds_and_retains_writes(self):
        routine = 'ROUTINE spin(p: INTEGER) BEGIN again:: p = p + 1 GOTO again END spin'
        p, _ = compile_program('x = 0 spin(x)', routine)
        with self.assertRaisesRegex(KarelRuntimeError, 'step budget'): p.run(max_steps=15)
        self.assertGreater(p._state.get('X'), 0)
        self.assertEqual((p._state.local_frames, p._state.call_depth), ([], 0))

    def test_labelled_function_global_effect_analysis_retained(self):
        routine = 'ROUTINE update: INTEGER BEGIN GOTO work work:: x = 7 RETURN 1 END update'
        with self.assertRaises(TranslationError) as caught: compile_program('result = update() + 1', routine, _translator=legacy_translate)
        self.assertEqual(caught.exception.code, 'E_EVALUATION_ORDER')


class StructuredFlowParityTests(unittest.TestCase):
    def compare(self, body, routines=''):
        normal, _ = compile_program(body, routines)
        labelled, _ = compile_program('unused_label:: ' + body, routines)
        self.assertEqual(labelled.run(), normal.run())
        self.assertEqual(labelled._state.steps, normal._state.steps)

    def test_if_else_parity(self):
        self.compare('x = 1 IF TRUE THEN x = 7 ELSE x = 8 ENDIF IF FALSE THEN y = 1 ELSE y = 2 ENDIF')

    def test_while_pretest_parity(self):
        self.compare('x = 0 WHILE x < 3 DO x = x + 1 ENDWHILE WHILE FALSE DO y = 9 ENDWHILE')

    def test_repeat_posttest_parity(self):
        self.compare('x = 0 REPEAT x = x + 1 UNTIL x = 3 REPEAT y = 7 UNTIL TRUE')

    def test_select_no_fallthrough_parity(self):
        self.compare('SELECT 2 OF CASE(1): x = 1 CASE(2,3): x = 7 ELSE: x = 9 ENDSELECT SELECT 8 OF CASE(1): y = 1 ELSE: y = 8 ENDSELECT')

    def test_select_unmatched_without_else_parity(self):
        for prefix in ('', 'unused_label:: '):
            with self.subTest(prefix=prefix):
                program, _ = compile_program(prefix + 'x = 7 SELECT 9 OF CASE(1): x = 1 ENDSELECT')
                with self.assertRaisesRegex(KarelRuntimeError, 'No match in CASE'): program.run()
                self.assertEqual(program._state.snapshot()['X'], 7)

    def test_empty_structured_blocks_parity(self):
        self.compare('IF TRUE THEN ELSE ENDIF WHILE FALSE DO ENDWHILE REPEAT UNTIL TRUE SELECT 1 OF CASE(1): ELSE: ENDSELECT')

    def test_nested_control_parity(self):
        self.compare('x = 0 total = 0 WHILE x < 3 DO x = x + 1 SELECT x OF CASE(1): total = total + 10 CASE(2): IF TRUE THEN total = total + 20 ENDIF ELSE: REPEAT total = total + 30 UNTIL TRUE ENDSELECT ENDWHILE')

    def test_for_parity(self):
        self.compare('total = 0 FOR i = 1 TO 3 DO total = total + i ENDFOR FOR i = 2 DOWNTO 1 DO total = total + i ENDFOR flag = UNINIT(i)')

    def test_select_effectful_selector_evaluated_once(self):
        routine = 'ROUTINE choose: INTEGER BEGIN visits = visits + 1 RETURN 2 END choose'
        self.compare('visits = 0 SELECT choose() OF CASE(1): x = 1 CASE(2): x = 7 ELSE: x = 9 ENDSELECT', routine)
        self.assertEqual(execute('unused:: visits = 0 SELECT choose() OF CASE(1): x = 1 CASE(2): x = 7 ENDSELECT', routine)['VISITS'], 1)

    def test_while_condition_evaluated_each_iteration(self):
        routine = 'ROUTINE test_next: BOOLEAN BEGIN visits = visits + 1 RETURN visits <= 3 END test_next'
        self.compare('visits = 0 x = 0 WHILE test_next() DO x = x + 1 ENDWHILE', routine)
        state = execute('unused:: visits = 0 x = 0 WHILE test_next() DO x = x + 1 ENDWHILE', routine)
        self.assertEqual((state['X'], state['VISITS']), (3, 4))

    def test_existing_examples_match_with_unused_label(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('control_flow', 'parameters', 'aggregate_parameters', 'string_processing', 'exact_numeric', 'structures'):
            with self.subTest(example=name):
                source = (root / f'examples/{name}.kl').read_text()
                # Place a no-op label in the main body, after any routine bodies.
                end = source.rfind('\nEND ')
                labelled = source[:end] + '\nfinal_marker::\n' + source[end:]
                def run_source(text):
                    namespace = {'__name__': 'parity'}
                    exec(translate(text).python_source, namespace)
                    program = namespace['Program']()
                    return program.run(), program._state.steps
                self.assertEqual(run_source(source), run_source(labelled))


class BranchRejectionTests(unittest.TestCase):
    def rejected(self, body, code, routines='', **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, routines, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_undefined_label(self): self.rejected('GO TO missing', 'E_LABEL')

    def test_duplicate_label(self): self.rejected('again:: x = 1 AGAIN:: x = 2', 'E_DUPLICATE_LABEL')

    def test_label_conflicts_with_variable(self): self.rejected('x::', 'E_LABEL_CONFLICT')

    def test_label_conflicts_with_constant(self): self.rejected('fixed::', 'E_LABEL_CONFLICT', extra='CONST fixed = 1')

    def test_label_conflicts_with_type(self): self.rejected('record_t::', 'E_LABEL_CONFLICT', extra='TYPE record_t = STRUCTURE value: INTEGER ENDSTRUCTURE')

    def test_label_conflicts_with_routine(self): self.rejected('work::', 'E_LABEL_CONFLICT', routines='ROUTINE work BEGIN END work')

    def test_label_conflicts_with_program_name(self): self.rejected('T::', 'E_LABEL_CONFLICT')

    def test_label_conflicts_with_local(self): self.rejected('work', 'E_LABEL_CONFLICT', routines='ROUTINE work VAR local_value: INTEGER BEGIN local_value:: END work')

    def test_label_conflicts_with_formal(self): self.rejected('work(x)', 'E_LABEL_CONFLICT', routines='ROUTINE work(p: INTEGER) BEGIN p:: END work')

    def test_invalid_label_names(self):
        for name in ('123', '_label', 'a' * 37, 'IF', 'ABS', 'DIN'):
            with self.subTest(name=name): self.rejected(f'{name}::', 'E_LABEL_NAME')

    def test_invalid_jump_target_name(self):
        for name in ('123', '_label', 'a' * 37, 'IF', 'ABS', 'DIN'):
            with self.subTest(name=name): self.rejected(f'GOTO {name}', 'E_LABEL_NAME')

    def test_go_requires_to(self): self.rejected('GO finished finished::', 'E_SYNTAX')

    def test_labels_not_visible_from_program_to_routine(self):
        self.rejected('finished:: work', 'E_LABEL', routines='ROUTINE work BEGIN GOTO finished END work')

    def test_labels_not_visible_from_routine_to_program(self):
        self.rejected('GOTO finished', 'E_LABEL', routines='ROUTINE work BEGIN finished:: END work')

    def test_labels_not_visible_between_routines(self):
        self.rejected('first', 'E_LABEL', routines='ROUTINE first BEGIN GOTO finished END first\nROUTINE second BEGIN finished:: END second')

    def test_jump_inside_for_blocked(self): self.rejected('FOR i = 1 TO 2 DO GOTO finished ENDFOR finished::', 'E_GOTO_FOR')

    def test_jump_inside_nested_for_branch_blocked(self): self.rejected('FOR i = 1 TO 2 DO IF TRUE THEN GOTO finished ENDIF ENDFOR finished::', 'E_GOTO_FOR')

    def test_label_inside_for_blocked_even_unused(self): self.rejected('FOR i = 1 TO 2 DO inside:: x = 7 ENDFOR', 'E_GOTO_FOR')

    def test_jump_into_for_blocked(self): self.rejected('GOTO inside FOR i = 1 TO 2 DO inside:: x = 7 ENDFOR', 'E_GOTO_FOR')

    def test_legacy_jump_into_if_blocked(self): self.rejected('GOTO inside IF TRUE THEN inside:: x = 7 ENDIF', 'E_GOTO_ENTRY', _translator=legacy_translate)

    def test_legacy_jump_into_while_blocked(self): self.rejected('GOTO inside WHILE TRUE DO inside:: x = 7 ENDWHILE', 'E_GOTO_ENTRY', _translator=legacy_translate)

    def test_legacy_jump_into_repeat_blocked(self): self.rejected('GOTO inside REPEAT inside:: x = 7 UNTIL TRUE', 'E_GOTO_ENTRY', _translator=legacy_translate)

    def test_legacy_jump_into_select_case_blocked(self): self.rejected('GOTO inside SELECT 1 OF CASE(1): inside:: x = 7 ENDSELECT', 'E_GOTO_ENTRY', _translator=legacy_translate)

    def test_legacy_jump_between_sibling_branches_blocked(self): self.rejected('IF TRUE THEN GOTO inside ELSE inside:: x = 7 ENDIF', 'E_GOTO_ENTRY', _translator=legacy_translate)

    def test_duplicate_labels_across_branches_blocked(self): self.rejected('IF TRUE THEN here:: ELSE here:: ENDIF', 'E_DUPLICATE_LABEL')

    def test_select_duplicate_case_first_match(self):
        self.assertEqual(execute('unused:: SELECT 1 OF CASE(1): x = 7 CASE(1): x = 8 ENDSELECT')['X'], 7)

    def test_for_counter_write_guard_retained(self): self.rejected('unused:: FOR i = 1 TO 2 DO i = 7 ENDFOR', 'E_FOR_COUNTER')

    def test_return_in_for_guard_retained(self): self.rejected('work', 'E_FOR_COUNTER', routines='ROUTINE work: INTEGER BEGIN unused:: FOR i = 1 TO 2 DO RETURN 7 ENDFOR RETURN 9 END work', _translator=legacy_translate)

    def test_unreachable_unsupported_source_still_rejected(self): self.rejected('GOTO finished MOVE TO x finished::', 'E_UNSUPPORTED')

    def test_unreachable_wrong_type_still_rejected(self): self.rejected('GOTO finished x = TRUE finished::', 'E_TYPE')


if __name__ == '__main__': unittest.main()
