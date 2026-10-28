"""SELECT semantics from PDF page 532, for both generated execution engines."""
import ast
import unittest

from karel2py import translate
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from karel2py.runtime import KarelRuntimeError, select_case


def compile_program(body, *, labelled=False, routines='', extra='', declarations='x,y,visits,i,total: INTEGER', _translator=translate):
    prefix = 'unused_marker::\n' if labelled else ''
    source = f'PROGRAM T\n{extra}\nVAR {declarations}\n{routines}\nBEGIN\n{prefix}{body}\nEND T'
    result = _translator(source, filename='select.kl')
    ast.parse(result.python_source, feature_version=(3, 11))
    namespace = {'__name__': 'select_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result, source


class SelectExecutionTests(unittest.TestCase):
    def parity(self, body, expected, **kwargs):
        outcomes = []
        for labelled in (False, True):
            with self.subTest(labelled=labelled):
                program, _, _ = compile_program(body, labelled=labelled, **kwargs)
                state = program.run()
                for name, value in expected.items(): self.assertEqual(state[name], value)
                outcomes.append((state, program._state.steps))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_duplicate_clauses_choose_first(self):
        self.parity('SELECT 2 OF CASE(2): x=7 CASE(2): x=9 ENDSELECT', {'X': 7})

    def test_duplicate_values_in_one_clause(self):
        self.parity('SELECT 2 OF CASE(2,2,2): x=7 CASE(2): x=9 ENDSELECT', {'X': 7})

    def test_overlapping_case_lists(self):
        self.parity('SELECT 3 OF CASE(1,3): x=7 CASE(2,3): x=9 ELSE: x=11 ENDSELECT', {'X': 7})

    def test_later_nonoverlapping_match(self):
        self.parity('SELECT 4 OF CASE(1,3): x=7 CASE(2,4): x=9 ELSE: x=11 ENDSELECT', {'X': 9})

    def test_empty_first_match_does_not_fall_through(self):
        self.parity('x=5 SELECT 2 OF CASE(2): CASE(2): x=9 ELSE: x=11 ENDSELECT y=x', {'X': 5, 'Y': 5})

    def test_ordinary_match_does_not_execute_else(self):
        self.parity('SELECT 1 OF CASE(1): x=7 ELSE: x=9 ENDSELECT y=x', {'X': 7, 'Y': 7})

    def test_no_match_runs_else_once(self):
        self.parity('visits=0 SELECT 9 OF CASE(1): x=7 ELSE: visits=visits+1 x=9 ENDSELECT y=x', {'VISITS': 1, 'Y': 9})

    def test_empty_else_allows_continuation(self):
        self.parity('x=7 SELECT 9 OF CASE(1): x=1 ELSE: ENDSELECT y=x', {'X': 7, 'Y': 7})

    def test_all_empty_clauses(self):
        self.parity('x=7 SELECT 2 OF CASE(1): CASE(2): ELSE: ENDSELECT y=x', {'Y': 7})

    def test_unmatched_without_else_preserves_prior_writes(self):
        for labelled in (False, True):
            program, _, source = compile_program('x=7\nSELECT 9 OF CASE(1): x=1 ENDSELECT\ny=9', labelled=labelled)
            with self.assertRaisesRegex(KarelRuntimeError, 'No match in CASE') as caught: program.run()
            line = next(i for i, text in enumerate(source.splitlines(), 1) if text.startswith('SELECT'))
            self.assertEqual(caught.exception.line, line)
            self.assertEqual(program._state.snapshot()['X'], 7)
            self.assertEqual(program._state.snapshot()['Y'], {'uninitialized': True})
            self.assertEqual(program._state.steps, 2)

    def test_effectful_selector_is_read_once(self):
        routine = 'ROUTINE choose: INTEGER BEGIN visits=visits+1 RETURN 2 END choose'
        self.parity('visits=0 SELECT choose() OF CASE(2): x=7 CASE(2): x=9 ENDSELECT', {'VISITS': 1, 'X': 7}, routines=routine)

    def test_unmatched_effectful_selector_runs_once_before_error(self):
        routine = 'ROUTINE choose: INTEGER BEGIN visits=visits+1 RETURN 9 END choose'
        for labelled in (False, True):
            program, _, _ = compile_program('visits=0 SELECT choose() OF CASE(1): x=7 ENDSELECT y=9', labelled=labelled, routines=routine)
            with self.assertRaisesRegex(KarelRuntimeError, 'No match in CASE'): program.run()
            self.assertEqual(program._state.snapshot()['VISITS'], 1)
            self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_uninitialized_selector_fails_before_matching(self):
        for labelled in (False, True):
            program, _, _ = compile_program('SELECT x OF CASE(1): y=7 ELSE: y=9 ENDSELECT', labelled=labelled)
            with self.assertRaisesRegex(KarelRuntimeError, '[Uu]ninitialized'): program.run()
            self.assertEqual(program._state.snapshot()['Y'], {'uninitialized': True})

    def test_constant_aliases_keep_first_match(self):
        self.parity('SELECT 2 OF CASE(a): x=7 CASE(b): x=9 ENDSELECT', {'X': 7}, extra='CONST a=2 b=a')

    def test_minint_case(self):
        self.parity('SELECT MININT OF CASE(MININT): x=7 CASE(MININT): x=9 ENDSELECT', {'X': 7})

    def test_maxint_expression_case(self):
        self.parity('SELECT MAXINT OF CASE(MAXINT): x=7 ELSE: x=9 ENDSELECT', {'X': 7})

    def test_signed_case(self):
        self.parity('SELECT -7 OF CASE(-7,0): x=7 CASE(-7): x=9 ENDSELECT', {'X': 7})

    def test_nested_select_first_match(self):
        self.parity('SELECT 2 OF CASE(2): SELECT 3 OF CASE(3): x=7 CASE(3): x=9 ENDSELECT CASE(2): x=11 ENDSELECT', {'X': 7})

    def test_nested_empty_else(self):
        self.parity('x=7 SELECT 2 OF CASE(2): SELECT 9 OF CASE(3): x=9 ELSE: ENDSELECT y=x ENDSELECT', {'Y': 7})

    def test_nested_missing_match_stops_outer_continuation(self):
        for labelled in (False, True):
            program, _, _ = compile_program('x=7 SELECT 2 OF CASE(2): SELECT 9 OF CASE(3): x=9 ENDSELECT y=11 ELSE: y=13 ENDSELECT', labelled=labelled)
            with self.assertRaisesRegex(KarelRuntimeError, 'No match in CASE'): program.run()
            self.assertEqual(program._state.snapshot()['X'], 7)
            self.assertEqual(program._state.snapshot()['Y'], {'uninitialized': True})

    def test_routine_reference_writes_survive_missing_match(self):
        for marker in ('', 'routine_marker:: '):
            routine = f'ROUTINE work(p: INTEGER) BEGIN {marker}p=7 SELECT 9 OF CASE(1): p=11 ENDSELECT END work'
            program, _, _ = compile_program('x=1 work(x) y=9', routines=routine)
            with self.assertRaisesRegex(KarelRuntimeError, 'No match in CASE'): program.run()
            self.assertEqual(program._state.snapshot()['X'], 7)
            self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_recursive_frames_unwind_on_missing_match(self):
        routine = 'ROUTINE work(n: INTEGER) BEGIN marker:: IF n>0 THEN work(n-1) ELSE x=7 SELECT 9 OF CASE(1): x=11 ENDSELECT ENDIF END work'
        program, _, _ = compile_program('x=1 work(3) y=9', routines=routine)
        with self.assertRaisesRegex(KarelRuntimeError, 'No match in CASE'): program.run()
        self.assertEqual(program._state.snapshot()['X'], 7)
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_function_selected_return(self):
        routine = 'ROUTINE choose(n: INTEGER): INTEGER BEGIN SELECT n OF CASE(2): RETURN 7 CASE(2): RETURN 9 ELSE: RETURN 11 ENDSELECT END choose'
        self.parity('x=choose(2) y=choose(8)', {'X': 7, 'Y': 11}, routines=routine)

    def test_fresh_local_for_counter_selected_return(self):
        routine = 'ROUTINE choose: INTEGER VAR counter: INTEGER BEGIN FOR counter=1 TO 3 DO SELECT counter OF CASE(1): CASE(2): RETURN 7 ELSE: ENDSELECT ENDFOR RETURN 9 END choose'
        self.parity('x=choose()', {'X': 7}, routines=routine)

    def test_global_for_with_select(self):
        self.parity('total=0 FOR i=1 TO 3 DO SELECT i OF CASE(1): total=total+1 CASE(2): total=total+2 ELSE: total=total+3 ENDSELECT ENDFOR', {'TOTAL': 6, 'I': {'uninitialized': True}})

    def test_select_backward_jump(self):
        program, result, _ = compile_program('visits=0 again:: visits=visits+1 SELECT visits OF CASE(1,2): GOTO again CASE(3): x=7 ELSE: x=9 ENDSELECT')
        self.assertEqual(program.run()['X'], 7)
        self.assertEqual(program._state.snapshot()['VISITS'], 3)
        self.assertEqual(result.report['control_flow']['program']['python_dispatch'], 'match')

    def test_select_can_exit_to_ancestor_label(self):
        program, _, _ = compile_program('SELECT 2 OF CASE(2): x=7 GOTO done CASE(2): x=9 ENDSELECT x=11 done:: y=x')
        self.assertEqual(program.run()['Y'], 7)

    def test_selection_statement_has_one_step(self):
        for labelled in (False, True):
            program, _, _ = compile_program('SELECT 2 OF CASE(1): CASE(2): ENDSELECT', labelled=labelled)
            program.run(max_steps=1)
            self.assertEqual(program._state.steps, 1)

    def test_budget_checked_before_selector_effect(self):
        routine = 'ROUTINE choose: INTEGER BEGIN x=7 RETURN 2 END choose'
        for labelled in (False, True):
            program, _, _ = compile_program('x=1 SELECT choose() OF CASE(2): ENDSELECT', labelled=labelled, routines=routine)
            with self.assertRaisesRegex(KarelRuntimeError, 'step budget'): program.run(max_steps=1)
            self.assertEqual(program._state.snapshot()['X'], 1)


class SelectLimitAndReportTests(unittest.TestCase):
    def test_thousand_nonempty_cases_compile_and_run_both_engines(self):
        clauses = ' '.join(f'CASE({n}): x={n}' for n in range(1000))
        for labelled in (False, True):
            program, result, _ = compile_program(f'SELECT 999 OF {clauses} ENDSELECT', labelled=labelled)
            self.assertEqual(program.run()['X'], 999)
            self.assertEqual(program._state.steps, 2)
            self.assertEqual(result.report['selects'][0]['case_count'], 1000)
            matches = [node for node in ast.walk(ast.parse(result.python_source)) if isinstance(node, ast.Match)]
            self.assertTrue(any(len(node.cases) == 1001 for node in matches))

    def test_thousand_duplicate_cases_first_empty_match(self):
        clauses = 'CASE(1): ' * 999 + 'CASE(1): x=9'
        for labelled in (False, True):
            program, _, _ = compile_program(f'x=7 SELECT 1 OF {clauses} ENDSELECT', labelled=labelled)
            self.assertEqual(program.run()['X'], 7)

    def test_thousand_cases_with_else_and_missing_match(self):
        clauses = ' '.join(f'CASE({n}):' for n in range(1000))
        for labelled in (False, True):
            program, _, _ = compile_program(f'SELECT 1000 OF {clauses} ELSE: x=7 ENDSELECT', labelled=labelled)
            self.assertEqual(program.run()['X'], 7)
            program, _, _ = compile_program(f'SELECT 1000 OF {clauses} ENDSELECT', labelled=labelled)
            with self.assertRaisesRegex(KarelRuntimeError, 'No match in CASE'): program.run()

    def test_thousand_and_one_cases_rejected_at_extra_clause(self):
        body = 'SELECT 1 OF\n' + 'CASE(1):\n' * 1001 + 'ENDSELECT'
        with self.assertRaises(TranslationError) as caught: compile_program(body)
        self.assertEqual(caught.exception.code, 'E_SELECT_LIMIT')
        self.assertEqual(caught.exception.token.line, 1007)

    def test_case_values_do_not_count_as_clauses(self):
        body = 'SELECT 1001 OF CASE(' + ','.join(str(n) for n in range(1002)) + '): x=7 ENDSELECT'
        program, result, _ = compile_program(body)
        self.assertEqual(program.run()['X'], 7)
        self.assertEqual(result.report['selects'][0]['case_count'], 1)

    def test_report_distinguishes_absent_and_empty_else(self):
        for labelled in (False, True):
            _, result, _ = compile_program('SELECT 1 OF CASE(1): ENDSELECT\nSELECT 1 OF CASE(1): ELSE: ENDSELECT', labelled=labelled)
            rows = sorted(result.report['selects'], key=lambda row: row['line'])
            self.assertEqual([(r['has_else'], r['empty_else'], r['no_match']) for r in rows], [(False, False, 'KarelRuntimeError'), (True, True, 'else_clause')])
            self.assertTrue(all(r['body'] == 'T' and r['column'] == 1 for r in rows))
            self.assertEqual(result.report['select_policy']['max_case_clauses'], 1000)
            self.assertFalse(result.report['select_policy']['controller_validated'])

    def test_report_records_duplicates_and_routine_scope(self):
        routine = 'ROUTINE work BEGIN SELECT 2 OF CASE(1,2): CASE(2): ELSE: ENDSELECT END work'
        _, result, _ = compile_program('work', routines=routine)
        row = result.report['selects'][0]
        self.assertEqual(row['body'], 'WORK')
        self.assertEqual(row['case_values'], [(1, 2), (2,)])

    def test_continued_select_fault_uses_physical_start_line(self):
        program, result, source = compile_program('x=7\nSELECT & -- selector follows\n9 OF CASE(1): x=9 ENDSELECT', labelled=True)
        with self.assertRaisesRegex(KarelRuntimeError, 'No match in CASE') as caught: program.run()
        line = next(i for i, text in enumerate(source.splitlines(), 1) if text.startswith('SELECT'))
        self.assertEqual(caught.exception.line, line)
        self.assertEqual(result.report['selects'][0]['line'], line)


class SelectRejectionTests(unittest.TestCase):
    def rejected(self, body, code, **kwargs):
        for labelled in (False, True):
            with self.subTest(labelled=labelled):
                with self.assertRaises(TranslationError) as caught: compile_program(body, labelled=labelled, **kwargs)
                self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_boolean_selector_rejected(self): self.rejected('SELECT ON OF CASE(1): ENDSELECT', 'E_TYPE')
    def test_real_selector_rejected(self): self.rejected('SELECT 1.0 OF CASE(1): ENDSELECT', 'E_TYPE')
    def test_string_selector_rejected(self): self.rejected("SELECT '1' OF CASE(1): ENDSELECT", 'E_TYPE')
    def test_boolean_case_rejected(self): self.rejected('SELECT 1 OF CASE(ON): ENDSELECT', 'E_CASE')
    def test_real_case_rejected(self): self.rejected('SELECT 1 OF CASE(1.0): ENDSELECT', 'E_CASE')
    def test_string_case_rejected(self): self.rejected("SELECT 1 OF CASE('1'): ENDSELECT", 'E_CASE')
    def test_variable_case_rejected(self): self.rejected('x=1 SELECT 1 OF CASE(x): ENDSELECT', 'E_CONSTANT')
    def test_minimum_integer_literal_guard_preserved(self): self.rejected('SELECT 1 OF CASE(-2147483648): ENDSELECT', 'E_MININT_LITERAL')
    def test_invalid_unreachable_body_remains_checked(self): self.rejected('SELECT 1 OF CASE(1): x=7 CASE(1): x=ON ENDSELECT', 'E_TYPE')
    def test_legacy_sibling_case_jump_rejected(self): self.rejected('SELECT 1 OF CASE(1): GOTO other CASE(2): other:: ENDSELECT', 'E_GOTO_ENTRY', _translator=legacy_translate)
    def test_legacy_entry_into_case_rejected(self): self.rejected('GOTO nested SELECT 1 OF CASE(1): nested:: ENDSELECT', 'E_GOTO_ENTRY', _translator=legacy_translate)
    def test_legacy_select_does_not_relax_for_jump_guard(self): self.rejected('FOR i=1 TO 2 DO SELECT i OF CASE(1): GOTO done ELSE: ENDSELECT ENDFOR done::', 'E_GOTO_FOR', _translator=legacy_translate)


class SelectRuntimeTests(unittest.TestCase):
    def test_first_matching_ordinal(self): self.assertEqual(select_case(2, ((1, 2), (2,)), False), 0)
    def test_else_ordinal(self): self.assertEqual(select_case(3, ((1,), (2,)), True), 2)
    def test_no_else_error_location(self):
        with self.assertRaisesRegex(KarelRuntimeError, 'No match in CASE') as caught: select_case(3, ((1,),), False, 42)
        self.assertEqual(caught.exception.line, 42)
    def test_expression_extremes(self):
        for value in (-2147483648, 2147483647): self.assertEqual(select_case(value, ((value,),), False), 0)
    def test_list_tables_supported(self): self.assertEqual(select_case(2, [[1], [2]], False), 1)
    def test_invalid_selector_types(self):
        for value in (True, 1.0, '1', None, -2147483649, 2147483648):
            with self.subTest(value=value), self.assertRaises(KarelRuntimeError): select_case(value, ((1,),), True)
    def test_invalid_case_tables(self):
        for table in (None, {}, (), ((1,),) * 1001, ((),), ({1},), (1,), ((True,),), ((1.0,),), ((2147483648,),)):
            with self.subTest(table_type=type(table).__name__), self.assertRaises(KarelRuntimeError): select_case(1, table, True)
    def test_invalid_later_clause_checked_before_first_match(self):
        with self.assertRaises(KarelRuntimeError): select_case(1, ((1,), (True,)), False)
    def test_else_flag_requires_exact_boolean(self):
        for flag in (0, 1, None, 'true'):
            with self.subTest(flag=flag), self.assertRaises(KarelRuntimeError): select_case(1, ((1,),), flag)
    def test_runtime_thousand_clause_limit(self):
        self.assertEqual(select_case(999, tuple((n,) for n in range(1000)), False), 999)


if __name__ == '__main__': unittest.main()
