import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from karel2py.runtime import KarelRuntimeError


ROOT = Path(__file__).resolve().parents[1]


def source(body, declarations='x, y, i: INTEGER\nb: BOOLEAN\ns: STRING[5]', extra=''):
    return f'PROGRAM T\nVAR\n{declarations}\n{extra}\nBEGIN\n{body}\nEND T\n'


def program(kl):
    result = translate(kl, filename='test.kl')
    namespace = {'__name__': 'generated_test'}
    exec(compile(result.python_source, 'generated_test.py', 'exec'), namespace)
    return namespace['Program'](), result


def run(body, **kwargs):
    return program(source(body, **kwargs))[0].run()


class PositiveTests(unittest.TestCase):
    def test_example_end_to_end(self):
        state = program((ROOT / 'examples/control_flow.kl').read_text())[0].run()
        self.assertEqual(state['TOTAL'], 200)
        self.assertEqual(state['VALUES'], [999, 20, 30, 40])
        self.assertEqual(state['COPIED'], [10, 20, 30, 40])
        self.assertEqual(state['LABEL'], 'complete')
        self.assertTrue(state['COUNTER_CLEARED'])
        self.assertTrue(state['FINISHED'])
        self.assertEqual(state['I'], 2)

    def test_case_insensitive_symbols_preserve_strings(self):
        self.assertEqual(run("X = 3\ny = x + 4\ns = 'MiXeD'")['S'], 'MiXeD')

    def test_comments_do_not_split_string(self):
        self.assertEqual(run("s = '--x' -- not source\nx = 2")['S'], '--x')

    def test_nested_if_and_empty_bodies(self):
        state = run('x = 2\nIF TRUE THEN\nIF x = 2 THEN\ny = 9\nELSE\ny = 0\nENDIF\nELSE\nENDIF')
        self.assertEqual(state['Y'], 9)

    def test_single_line_if(self):
        self.assertEqual(run('IF TRUE THEN x = 7 ELSE x = 9 ENDIF')['X'], 7)

    def test_while_zero_iterations(self):
        self.assertEqual(run('x = 0\nWHILE FALSE DO x = 1 ENDWHILE')['X'], 0)

    def test_repeat_at_least_once(self):
        self.assertEqual(run('x = 0\nREPEAT x = x + 1 UNTIL TRUE')['X'], 1)

    def test_for_inclusive_and_uninitialized_counter(self):
        state = run('x = 0\nFOR i = 1 TO 3 DO x = x + i ENDFOR\nb = UNINIT(i)')
        self.assertEqual(state['X'], 6)
        self.assertTrue(state['B'])
        self.assertEqual(state['I'], {'uninitialized': True})

    def test_for_zero_iterations_counter_cleared(self):
        state = run('x = 0\nFOR i = 3 TO 1 DO x = 1 ENDFOR\nb = UNINIT(i)')
        self.assertEqual(state['X'], 0)
        self.assertTrue(state['B'])

    def test_downto(self):
        self.assertEqual(run('x = 0\nFOR i = 3 DOWNTO 1 DO x = x + i ENDFOR')['X'], 6)

    def test_bounds_evaluated_once(self):
        self.assertEqual(run('x = 3\ny = 0\nFOR i = 1 TO x DO\nx = 0\ny = y + 1\nENDFOR')['Y'], 3)

    def test_final_bound_sees_initialized_counter(self):
        self.assertEqual(run('x = 0\nFOR i = 1 TO i + 2 DO x = x + 1 ENDFOR')['X'], 3)

    def test_nested_for_independent_counters(self):
        self.assertEqual(run('x = 0\nFOR i = 1 TO 2 DO\nFOR y = 1 TO 3 DO\nx = x + 1\nENDFOR\nENDFOR')['X'], 6)

    def test_select_once_no_fallthrough(self):
        extra = 'ROUTINE choose: INTEGER\nBEGIN\nx = x + 1\nRETURN 2\nEND choose'
        state = run('x = 0\nSELECT choose() OF\nCASE(1,2): y = 4\nCASE(3): y = 8\nELSE: y = 0\nENDSELECT', extra=extra)
        self.assertEqual((state['X'], state['Y']), (1, 4))

    def test_select_default_and_no_default(self):
        self.assertEqual(run('SELECT 3 OF CASE(1): x = 1 ELSE: x = 9 ENDSELECT')['X'], 9)
        with self.assertRaisesRegex(KarelRuntimeError, 'No match in CASE'):
            run('x = 7\nSELECT 3 OF CASE(1): x = 1 ENDSELECT')

    def test_routine_return(self):
        extra = 'ROUTINE set_x\nBEGIN\nx = 5\nRETURN\nx = 9\nEND set_x'
        self.assertEqual(run('set_x()', extra=extra)['X'], 5)

    def test_precedence_differs_from_python(self):
        self.assertEqual(run('x = 1 + 2 OR 4')['X'], 7)
        self.assertEqual(run('x = -2 * 3 + 4')['X'], -2)
        self.assertEqual(run('x = -2 - 3')['X'], -5)
        self.assertEqual(run('x = NOT 5')['X'], -6)

    def test_boolean_operators_and_comparison(self):
        self.assertTrue(run('b = (3 > 2) AND NOT FALSE OR FALSE')['B'])
        self.assertTrue(run('b = TRUE > FALSE')['B'])

    def test_division_truncates_toward_zero(self):
        self.assertEqual(run('x = (-11) DIV 2\ny = 11 MOD 2')['X'], -5)

    def test_string_truncation_concat_and_length(self):
        state = run("s = 'abcd' + 'efg'\nx = STR_LEN(s)")
        self.assertEqual((state['S'], state['X']), ('abcde', 5))

    def test_constants_and_array_size(self):
        kl = 'PROGRAM T\nCONST N = 2 + 1\nVAR a: ARRAY[N] OF INTEGER\nx: INTEGER\nBEGIN a[3] = N\nx = ARRAY_LEN(a) END T'
        state = program(kl)[0].run()
        self.assertEqual(state['X'], 3)
        self.assertEqual(state['A'][2], 3)

    def test_uninit_element_without_read(self):
        state = run('b = UNINIT(a[1])', declarations='a: ARRAY[2] OF INTEGER\nb: BOOLEAN')
        self.assertTrue(state['B'])

    def test_array_assignment_copies_values(self):
        state = run('a[1] = 5\na[2] = 6\nz = a\na[1] = 9', declarations='a,z: ARRAY[2] OF INTEGER')
        self.assertEqual(state['Z'], [5, 6])

    def test_integer_minimum_identifier(self):
        self.assertEqual(run('x = MININT')['X'], -2147483648)

    def test_integer_minimum_constant(self):
        kl = 'PROGRAM T\nCONST minimum = MININT\nVAR x: INTEGER\nBEGIN x = minimum END T'
        self.assertEqual(program(kl)[0].run()['X'], -2147483648)

    def test_program_instances_do_not_share_state(self):
        kl = source('IF UNINIT(x) THEN x = 1 ELSE x = x + 1 ENDIF')
        first, _ = program(kl)
        second, _ = program(kl)
        self.assertEqual(first.run()['X'], 1)
        self.assertEqual(first.run()['X'], 2)
        self.assertEqual(second.run()['X'], 1)

    def test_source_map_and_hashes(self):
        result = translate(source('x = 1'))
        self.assertEqual(len(result.report['source_sha256']), 64)
        self.assertTrue(result.report['source_map'])
        self.assertTrue(all(m['python_line'] <= len(result.python_source.splitlines()) for m in result.report['source_map']))


class RejectionTests(unittest.TestCase):
    def reject(self, body, code, **kwargs):
        with self.assertRaises(TranslationError) as caught:
            kwargs.pop('_translator', translate)(source(body, **kwargs), filename='negative.kl')
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        self.assertGreater(caught.exception.token.line, 0)

    def test_unsupported_controller_constructs(self):
        for statement in ('MOVE TO x', 'ABORT PROGRAM[1]', 'HOLD'):
            with self.subTest(statement=statement): self.reject(statement, 'E_ABORT_TARGET' if statement.startswith('ABORT') else 'E_UNSUPPORTED', _translator=legacy_translate)

    def test_directives_fail_closed(self):
        for directive,code in (('%CMOSVARS','E_DIRECTIVE_POSITION'),('%INCLUDE ABC','E_DIRECTIVE'),('%DEFGROUP=1','E_DIRECTIVE_POSITION')):
            with self.subTest(directive=directive): self.reject('x = 1', code, extra=directive)

    def test_unsupported_types(self):
        for kind in ('XYZWPR', 'FILE', 'BYTE', 'STRUCTURE'):
            with self.subTest(kind=kind): self.reject('x = 1', 'E_TYPE', declarations='x: ' + kind)

    def test_real_literal_and_division(self):
        self.reject('x = 1.25', 'E_TYPE')
        self.reject('x = 4 / 2', 'E_TYPE')

    def test_unknown_symbols_and_calls(self):
        self.reject('x = missing', 'E_SYMBOL')
        self.reject('x = UNKNOWN(1)', 'E_CALL')
        self.reject('GET_POS_REG(1, x)', 'E_CALL')
        self.reject('b = DIN[1] + 1', 'E_TYPE')

    def test_no_partial_translation_on_later_failure(self):
        self.reject('x = 1\ny = x + 2\nMOVE TO x', 'E_UNSUPPORTED')

    def test_type_mismatches(self):
        for body in ('x = TRUE', 'b = 1', 'IF 1 THEN x = 1 ENDIF', "x = 'text'", 'x = b + 1'):
            with self.subTest(body=body): self.reject(body, 'E_TYPE')

    def test_constants_cannot_be_assigned(self):
        kl = 'PROGRAM T\nCONST C = 1\nBEGIN C = 2 END T'
        with self.assertRaises(TranslationError) as caught: translate(kl)
        self.assertEqual(caught.exception.code, 'E_CONST_ASSIGN')

    def test_duplicate_declarations(self):
        self.reject('x = 1', 'E_DUPLICATE', declarations='x: INTEGER\nX: BOOLEAN')

    def test_array_type_size_mismatch(self):
        self.reject('a = z', 'E_TYPE', declarations='a: ARRAY[2] OF INTEGER\nz: ARRAY[3] OF INTEGER')

    def test_invalid_sizes(self):
        for kind in ('ARRAY[0] OF INTEGER', 'ARRAY[32768] OF INTEGER', 'STRING[0]', 'STRING[255]'):
            with self.subTest(kind=kind): self.reject('', 'E_SIZE', declarations='x: ' + kind)

    def test_routine_parameters_and_local_constants(self):
        self.reject('', 'E_PARAMETERS', extra='ROUTINE r(x: VISION)\nBEGIN END r')
        self.reject('', 'E_ROUTINE_LOCALS', extra='ROUTINE r\nTYPE z = ARRAY[1] OF INTEGER\nBEGIN END r')

    def test_procedure_not_expression(self):
        self.reject('x = proc()', 'E_TYPE', extra='ROUTINE proc BEGIN END proc')

    def test_return_contract(self):
        self.reject('RETURN', 'E_RETURN')
        self.reject('', 'E_RETURN', extra='ROUTINE f: INTEGER BEGIN RETURN END f')

    def test_for_counter_writes_or_side_effects_blocked(self):
        self.reject('FOR i = 1 TO 2 DO i = 8 ENDFOR', 'E_FOR_COUNTER')
        self.reject('FOR i = 1 TO 2 DO FOR i = 1 TO 3 DO ENDFOR ENDFOR', 'E_FOR_COUNTER')
        self.reject('FOR i = 1 TO 2 DO x = f() ENDFOR', 'E_FOR_COUNTER', extra='ROUTINE f: INTEGER BEGIN RETURN 3 END f', _translator=legacy_translate)

    def test_duplicate_select_cases(self):
        self.assertEqual(run('SELECT 1 OF CASE(1): x = 0 CASE(1): x = 9 ENDSELECT')['X'], 0)

    def test_boolean_side_effect_order_blocked(self):
        self.reject('b = TRUE OR f()', 'E_EVALUATION_ORDER', extra='ROUTINE f: BOOLEAN BEGIN RETURN TRUE END f', _translator=legacy_translate)

    def test_unknown_character_cannot_be_python_injection(self):
        self.reject('x = __import__("os")', 'E_LEX')

    def test_non_ascii_string_rejected(self):
        self.reject("s = 'é'", 'E_ENCODING')

    def test_integer_literal_out_of_range(self):
        self.reject('x = 2147483648', 'E_LITERAL')

    def test_missing_block_terminator(self):
        self.reject('WHILE TRUE DO x = 1', 'E_UNSUPPORTED')


class RuntimeTests(unittest.TestCase):
    def fail(self, body, message, **kwargs):
        with self.assertRaisesRegex(KarelRuntimeError, message):
            program(source(body, **kwargs))[0].run()

    def test_uninitialized_read(self): self.fail('x = y + 1', 'uninitialized')
    def test_integer_overflow(self): self.fail('x = 2147483647 + 1', 'overflow')
    def test_abs_minimum_overflow(self): self.fail('x = ABS(MININT)', 'overflow')
    def test_zero_divisor(self): self.fail('x = 10 DIV 0', 'Division by zero')
    def test_pythonic_signed_mod(self): self.assertEqual(run('x = (-11) MOD 2')['X'], 1)

    def test_array_bounds_fail_instead_of_python_negative_index(self):
        for index in (0, -1, 3):
            with self.subTest(index=index):
                self.fail(f'a[{index}] = 1', 'outside', declarations='a: ARRAY[2] OF INTEGER')

    def test_function_fallthrough(self):
        self.fail('x = f()', 'without RETURN', extra='ROUTINE f: INTEGER BEGIN END f')

    def test_empty_while_has_step_budget(self):
        p, _ = program(source('WHILE TRUE DO ENDWHILE'))
        with self.assertRaisesRegex(KarelRuntimeError, 'step budget'): p.run(max_steps=10)

    def test_return_from_function_not_program(self):
        self.assertEqual(run('x = f()\ny = 9', extra='ROUTINE f: INTEGER BEGIN RETURN 3 END f')['Y'], 9)

    def test_recursive_routine_guard_is_explicit(self):
        p, _ = program(source('recursive', extra='ROUTINE recursive BEGIN recursive END recursive'))
        with self.assertRaisesRegex(KarelRuntimeError, 'call-depth'): p.run()
        self.assertEqual(p._state.call_depth, 0)

    def test_routine_failure_unwinds_depth(self):
        p, _ = program(source('fail', extra='ROUTINE fail BEGIN x = y END fail'))
        with self.assertRaises(KarelRuntimeError): p.run()
        self.assertEqual(p._state.call_depth, 0)
        self.assertEqual(p._state.local_frames, [])

    def test_local_frame_is_fresh_per_call(self):
        state = run('x = 0\nr\nr', extra='ROUTINE r\nVAR temp: INTEGER\nBEGIN\nIF UNINIT(temp) THEN x = x + 1 ENDIF\ntemp = 9\nEND r')
        self.assertEqual(state['X'], 2)

    def test_local_shadowing_and_callee_scope(self):
        extra = 'ROUTINE callee\nBEGIN\nx = x + 1\nEND callee\nROUTINE caller\nVAR x: INTEGER\nBEGIN\nx = 100\ncallee\ny = x\nEND caller'
        state = run('x = 1\ncaller', extra=extra)
        self.assertEqual((state['X'], state['Y']), (2, 100))

    def test_local_function_result(self):
        extra = 'ROUTINE f: INTEGER\nVAR z: INTEGER\nBEGIN z = 12 RETURN z END f'
        self.assertEqual(run('x = f()', extra=extra)['X'], 12)

    def test_local_for_counter_uninitialized_after_loop(self):
        extra = 'ROUTINE r\nVAR k: INTEGER\nBEGIN FOR k = 1 TO 2 DO x = x + 1 ENDFOR\nb = UNINIT(k) END r'
        state = run('x = 0\nr', extra=extra)
        self.assertTrue(state['B'])
        self.assertEqual(state['X'], 2)


class CliTests(unittest.TestCase):
    def cli(self, *arguments):
        return subprocess.run([sys.executable, '-m', 'karel2py', *map(str, arguments)],
                              cwd=ROOT, capture_output=True, text=True)

    def test_actual_generated_module_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            out, report = Path(folder) / 'result.py', Path(folder) / 'report.json'
            result = self.cli(ROOT / 'examples/control_flow.kl', '-o', out, '--report', report)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(report.read_text())['status'], 'translated')
            # Import from a different output directory while runtime is available.
            spec = importlib.util.spec_from_file_location('generated', out)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertEqual(module.Program().run()['TOTAL'], 200)

    def test_rejected_source_does_not_emit_python(self):
        with tempfile.TemporaryDirectory() as folder:
            out, report = Path(folder) / 'result.py', Path(folder) / 'report.json'
            result = self.cli(ROOT / 'examples/unsupported_motion.kl', '-o', out, '--report', report)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(out.exists())
            self.assertEqual(json.loads(report.read_text())['status'], 'rejected')

    def test_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'result.py'
            out.write_text('preserve me')
            result = self.cli(ROOT / 'examples/control_flow.kl', '-o', out)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(out.read_text(), 'preserve me')

    def test_input_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            inp = Path(folder) / 'input.kl'
            inp.write_text(source('x = 1'))
            result = self.cli(inp, '-o', inp, '--force')
            self.assertEqual(result.returncode, 2)
            self.assertTrue(inp.read_text().startswith('PROGRAM'))


if __name__ == '__main__': unittest.main()
