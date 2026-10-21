"""Pythonic substring/search edges, bounded values and ordered failure effects."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


ROOT = Path(__file__).resolve().parents[1]


def compile_program(body, *, declarations='text,result: STRING[254] x,y: INTEGER', routines='',
                    prefix='', write=None, translator=translate):
    result = translator(f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T',
                        filename='string_operations.kl')
    namespace = {'__name__': 'string_operations_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](write=write), result


def execute(body, **kwargs):
    return compile_program(body, **kwargs)[0].run()


class PythonicSubstringTests(unittest.TestCase):
    def test_request_crossing_end_clips(self):
        self.assertEqual(execute("result=SUB_STR('abcdef',4,99)")['RESULT'], 'def')

    def test_request_starting_at_last_character(self):
        self.assertEqual(execute("result=SUB_STR('abcdef',6,99)")['RESULT'], 'f')

    def test_zero_count_in_source(self):
        self.assertEqual(execute("result=SUB_STR('abcdef',3,0)")['RESULT'], '')

    def test_zero_count_after_end(self):
        self.assertEqual(execute("result=SUB_STR('abc',MAXINT,0)")['RESULT'], '')

    def test_empty_source_and_zero_count(self):
        self.assertEqual(execute("result=SUB_STR('',1,0)")['RESULT'], '')

    def test_empty_source_and_large_count(self):
        self.assertEqual(execute("result=SUB_STR('',1,MAXINT)")['RESULT'], '')

    def test_maximum_count_uses_remaining_contents(self):
        self.assertEqual(execute("result=SUB_STR('abcdef',2,MAXINT)")['RESULT'], 'bcdef')

    def test_maximum_start_and_count_returns_empty(self):
        self.assertEqual(execute("result=SUB_STR('abcdef',MAXINT,MAXINT)")['RESULT'], '')

    def test_substring_boundary_table(self):
        for start, count, expected in [(1, 1, 'a'), (1, 3, 'abc'), (1, 4, 'abc'),
                                       (2, 1, 'b'), (2, 2, 'bc'), (2, 3, 'bc'),
                                       (3, 1, 'c'), (3, 4, 'c'), (4, 1, ''), (5, 0, '')]:
            with self.subTest(start=start, count=count):
                self.assertEqual(execute(f"result=SUB_STR('abc',{start},{count})")['RESULT'], expected)

    def test_destination_truncation_still_applies(self):
        self.assertEqual(execute("result=SUB_STR('abcdef',2,MAXINT)",
                                 declarations='result: STRING[3]')['RESULT'], 'bcd')

    def test_variable_start_count(self):
        self.assertEqual(execute("x=4 y=100 result=SUB_STR('abcdef',x,y)")['RESULT'], 'def')

    def test_narrow_start_count_promoted(self):
        self.assertEqual(execute("n[1]=2 n[2]=0 result=SUB_STR('abc',n[1],n[2])",
                                 declarations='n: ARRAY[2] OF BYTE result: STRING[8]')['RESULT'], '')

    def test_logical_apostrophe_positions(self):
        self.assertEqual(execute("result=SUB_STR('O''Brien',2,MAXINT)")['RESULT'], "'Brien")

    def test_controls_preserved(self):
        self.assertEqual(execute('result=SUB_STR(CHR(0)+CHR(10)+CHR(127),2,MAXINT)')['RESULT'], '\n\x7f')

    def test_using_field(self):
        self.assertEqual(execute("p.label='robot' USING p DO result=SUB_STR(label,3,MAXINT) ENDUSING",
                                 prefix='TYPE packet=STRUCTURE label: STRING[8] ENDSTRUCTURE',
                                 declarations='p: packet result: STRING[8]')['RESULT'], 'bot')


class PythonicSubstringCapacityTests(unittest.TestCase):
    def test_return_value_capped_before_length_query(self):
        state = execute("text='"+'a'*127+"' x=STR_LEN(SUB_STR(text+text+'Z',1,MAXINT))")
        self.assertEqual(state['X'], 254)

    def test_return_value_cap_starts_at_requested_position(self):
        state = execute("text='"+'a'*127+"' result=SUB_STR('X'+text+text+'Z',2,MAXINT)")
        self.assertEqual(state['RESULT'], 'a'*254)

    def test_exact_long_request_with_later_start(self):
        state = execute("text='"+'a'*127+"' result=SUB_STR(text+text+'Z',254,MAXINT)")
        self.assertEqual(state['RESULT'], 'aZ')

    def test_count_below_cap_is_not_promoted(self):
        state = execute("text='"+'a'*127+"' x=STR_LEN(SUB_STR(text+text+'Z',1,253))")
        self.assertEqual(state['X'], 253)

    def test_small_function_result_truncates_further(self):
        routines = "ROUTINE tail: STRING[3] BEGIN RETURN SUB_STR('abcdef',2,MAXINT) END tail"
        self.assertEqual(execute('result=tail()', routines=routines)['RESULT'], 'bcd')

    def test_default_string_result_keeps_bounded_value(self):
        routines = "ROUTINE tail: STRING BEGIN RETURN SUB_STR(text+text+'Z',1,MAXINT) END tail"
        state = execute("text='"+'a'*127+"' result=tail()", routines=routines)
        self.assertEqual(state['RESULT'], 'a'*254)

    def test_writable_value_argument_is_independent(self):
        routine = "ROUTINE edit(p: STRING) BEGIN p=p+'!' result=p END edit"
        state = execute("text='abc' edit(SUB_STR(text,2,MAXINT))", routines=routine)
        self.assertEqual((state['TEXT'], state['RESULT']), ('abc', 'bc!'))

    def test_zero_count_value_argument_is_initialized_empty(self):
        routine = "ROUTINE edit(p: STRING) BEGIN x=STR_LEN(p) p='new' result=p END edit"
        state = execute("edit(SUB_STR('abc',1,0))", routines=routine)
        self.assertEqual((state['X'], state['RESULT']), (0, 'new'))

    def test_bounded_result_consumed_by_value_argument(self):
        routine = 'ROUTINE read_text(p: STRING) BEGIN x=STR_LEN(p) END read_text'
        state = execute("text='"+'a'*127+"' read_text(SUB_STR(text+text+'Z',1,MAXINT))", routines=routine)
        self.assertEqual(state['X'], 254)

    def test_bounded_result_consumed_by_write(self):
        program, _ = compile_program("text='"+'a'*127+"' WRITE(SUB_STR(text+text+'Z',1,MAXINT))")
        program.run()
        self.assertEqual(program.write_requests[0]['text'], 'a'*254)

    def test_combined_write_limit_still_applies(self):
        observed = []
        program, _ = compile_program("text='"+'a'*127+"' WRITE(SUB_STR(text+text+'Z',1,MAXINT),CR)", write=observed.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'combined output'): program.run()
        self.assertEqual((program.write_requests, observed), ((), []))


class PythonicSearchTests(unittest.TestCase):
    def test_empty_search_returns_first_position(self):
        self.assertEqual(execute("x=INDEX('robot','')")['X'], 1)

    def test_both_empty_returns_first_position(self):
        self.assertEqual(execute("x=INDEX('','')")['X'], 1)

    def test_empty_source_nonempty_search_is_absent(self):
        self.assertEqual(execute("x=INDEX('','r')")['X'], 0)

    def test_zero_count_substring_as_search(self):
        self.assertEqual(execute("x=INDEX('robot',SUB_STR('prefix',1,0))")['X'], 1)

    def test_substring_as_empty_source(self):
        self.assertEqual(execute("x=INDEX(SUB_STR('robot',99,0),'')")['X'], 1)

    def test_search_is_first_exact_case_sensitive_match(self):
        for source, search, expected in [('banana','ana',2), ('Abc','a',0), ('abc','c',3),
                                         ('abc','abc',1), ('abc','abcd',0), (' abc',' ',1)]:
            with self.subTest(source=source, search=search):
                self.assertEqual(execute(f"x=INDEX('{source}','{search}')")['X'], expected)

    def test_apostrophe_and_control_searches(self):
        state = execute("x=INDEX('O''Brien',CHR(39)) y=INDEX('A'+CHR(0)+'B',CHR(0))")
        self.assertEqual((state['X'], state['Y']), (2, 2))

    def test_clipped_substring_search_composition(self):
        state = execute("result=SUB_STR('part:robot',INDEX('part:robot',':')+1,MAXINT) x=INDEX(result,'bot')")
        self.assertEqual((state['RESULT'], state['X']), ('robot', 3))


class StringOperationEffectTests(unittest.TestCase):
    def test_source_start_count_evaluated_once_in_order(self):
        routines = '''ROUTINE source: STRING BEGIN x=x*10+1 RETURN 'abcdef' END source
ROUTINE start: INTEGER BEGIN x=x*10+2 RETURN 4 END start
ROUTINE count: INTEGER BEGIN x=x*10+3 RETURN 99 END count'''
        state = execute('x=0 result=SUB_STR(source(),start(),count())', routines=routines)
        self.assertEqual((state['X'], state['RESULT']), (123, 'def'))

    def test_zero_count_still_evaluates_all_actuals(self):
        routines = '''ROUTINE source: STRING BEGIN x=x*10+1 RETURN 'abc' END source
ROUTINE start: INTEGER BEGIN x=x*10+2 RETURN 1 END start
ROUTINE count: INTEGER BEGIN x=x*10+3 RETURN 0 END count'''
        state = execute('x=0 result=SUB_STR(source(),start(),count())', routines=routines)
        self.assertEqual((state['X'], state['RESULT']), (123, ''))

    def test_source_captured_before_start_mutates_storage(self):
        routine = "ROUTINE start: INTEGER BEGIN text='new' RETURN 2 END start"
        state = execute("text='old' result=SUB_STR(text,start(),99)", routines=routine)
        self.assertEqual((state['TEXT'], state['RESULT']), ('new', 'ld'))

    def test_empty_search_function_still_runs_after_source_capture(self):
        routine = "ROUTINE empty: STRING BEGIN text='changed' x=x+1 RETURN '' END empty"
        state = execute("x=0 text='abc' y=INDEX(text,empty())", routines=routine)
        self.assertEqual((state['X'], state['Y'], state['TEXT']), (1, 1, 'changed'))

    def test_domain_error_preserves_destination_and_prior_effects(self):
        routines = "ROUTINE count: INTEGER BEGIN x=x+1 WRITE('count') RETURN -1 END count"
        program, _ = compile_program("x=0 result='kept' result=SUB_STR('abc',1,count())", routines=routines)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['X'], program.snapshot()['RESULT']), (1, 'kept'))
        self.assertEqual([row['text'] for row in program.write_requests], ['count'])
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_uninitialized_source_skips_later_actuals(self):
        routines = 'ROUTINE start: INTEGER BEGIN x=x+1 RETURN 1 END start'
        program, _ = compile_program('x=0 result=SUB_STR(text,start(),0)', routines=routines)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['X'], 0)

    def test_abort_skips_later_actual_and_assignment(self):
        routines = '''ROUTINE start: INTEGER BEGIN x=x+1 ABORT RETURN 1 END start
ROUTINE count: INTEGER BEGIN x=99 RETURN 0 END count'''
        program, _ = compile_program("x=0 result='kept' result=SUB_STR('abc',start(),count())", routines=routines)
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual((program.snapshot()['X'], program.snapshot()['RESULT']), (1, 'kept'))
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_invalid_start_is_checked_after_count_effect(self):
        routine = 'ROUTINE count: INTEGER BEGIN x=x+1 RETURN 0 END count'
        program, _ = compile_program("x=0 result=SUB_STR('abc',0,count())", routines=routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['X'], 1)

    def test_argument_mutation_of_destination_survives_operation_error(self):
        routine = "ROUTINE count: INTEGER BEGIN result='changed' RETURN -1 END count"
        program, _ = compile_program("result='old' result=SUB_STR('abc',1,count())", routines=routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['RESULT'], 'changed')
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))


class StringOperationGuardTests(unittest.TestCase):
    def test_invalid_start_and_negative_count_remain_errors(self):
        for start, count in [('0','0'), ('-1','1'), ('MININT','0'), ('1','-1'), ('MAXINT','-1')]:
            program, _ = compile_program(f"result='kept' result=SUB_STR('abc',{start},{count})")
            with self.subTest(start=start, count=count), self.assertRaises(rt.KarelRuntimeError): program.run()
            self.assertEqual(program.snapshot()['RESULT'], 'kept')

    def test_nonascii_source_checked_even_for_zero_result(self):
        program, _ = compile_program('result=SUB_STR(text,1,0)')
        program._state.values['TEXT'] = '\u00e9'
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'ASCII'): program.run()

    def test_empty_search_does_not_hide_invalid_source(self):
        for value in ('\u00e9', 42, rt.UNINITIALIZED):
            program, _ = compile_program("x=INDEX(text,'')")
            program._state.values['TEXT'] = value
            with self.subTest(value=value), self.assertRaises(rt.KarelRuntimeError): program.run()

    def test_invalid_search_does_not_hide_empty_source(self):
        for value in ('\u00e9', 42, rt.UNINITIALIZED):
            program, _ = compile_program("x=INDEX('',text)")
            program._state.values['TEXT'] = value
            with self.subTest(value=value), self.assertRaises(rt.KarelRuntimeError): program.run()

    def test_zero_count_does_not_hide_invalid_integer_start(self):
        for value in (True, 1.0, 2147483648, rt.UNINITIALIZED):
            program, _ = compile_program("result=SUB_STR('abc',x,0)")
            program._state.values['X'] = value
            with self.subTest(value=value), self.assertRaises(rt.KarelRuntimeError): program.run()

    def test_invalid_types_and_arity_still_rejected(self):
        for expression in ("SUB_STR('abc',1,ON)", "SUB_STR('abc',1.0,0)", "INDEX('abc',1)",
                           "SUB_STR('abc',1)", "INDEX('abc')"):
            with self.subTest(expression=expression), self.assertRaises(TranslationError):
                compile_program('result='+expression)

    def test_character_domain_still_checked(self):
        for expression in ('CHR(128)', "CHR(-1)", "CHR(ORD('',1))", "CHR(ORD('abc',0))"):
            program, _ = compile_program('result='+expression)
            with self.subTest(expression=expression), self.assertRaises(rt.KarelRuntimeError): program.run()

    def test_runtime_policy_restored_after_success_and_failure(self):
        self.assertEqual(execute("x=INDEX('','')")['X'], 1)
        with self.assertRaises(rt.KarelRuntimeError): execute("result=SUB_STR('abc',1,-1)")
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'empty search'): rt.builtin('INDEX', ['', ''])


class StringOperationIntegrationTests(unittest.TestCase):
    def test_public_report_describes_only_current_edges(self):
        _, result = compile_program("result=SUB_STR('abc',2,99) x=INDEX('','')")
        report = json.loads(json.dumps(result.report))
        self.assertIn('min(count,254)', report['string_operation_policy']['substring'])
        self.assertIn('one for an empty search', report['string_operation_policy']['search'])
        self.assertFalse(report['string_operation_policy']['controller_validated'])
        self.assertFalse(any('blocked' in item and item.startswith(('INDEX with an empty', 'SUB_STR beyond'))
                             for item in report['limitations']))

    def test_conservative_guards_remain_internal(self):
        for expression in ("SUB_STR('abc',1,0)", "SUB_STR('abc',2,99)", "INDEX('','')",
                           "SUB_STR('"+'a'*255+"',1,255)"):
            assignment = 'x=' if expression.startswith('INDEX') else 'result='
            program, _ = compile_program(assignment+expression, translator=legacy_translate)
            with self.subTest(expression=expression[:40]), self.assertRaises(rt.KarelRuntimeError): program.run()

    def test_authored_example_matches_independent_fixtures(self):
        source = ROOT/'examples/pythonic_string_operations.kl'
        result = translate(source.read_text(), filename=source.name)
        namespace = {'__name__': 'string_operations_fixture'}
        exec(result.python_source, namespace)
        observed = []
        program = namespace['Program'](write=observed.append)
        self.assertEqual(program.run(), json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(observed, json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))

    def test_cli_generated_module_retains_pythonic_edges(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'source.kl'
            source.write_text("PROGRAM T VAR text: STRING[8] x: INTEGER BEGIN text=SUB_STR('abc',2,99) x=INDEX('','') END T")
            output = Path(folder)/'converted.py'
            process = subprocess.run([sys.executable, '-m', 'karel2py', str(source), '-o', str(output)],
                                     cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            namespace = {'__name__': 'cli_string_operations'}
            exec(output.read_text(), namespace)
            self.assertEqual(namespace['Program']().run(), {'TEXT':'bc', 'X':1})

    def test_guide_example_runs_as_documented(self):
        import re
        guide = (ROOT/'docs/string-operations.md').read_text()
        source = re.search(r'```karel\n(.*?)\n```', guide, re.S)[1]
        result = translate(source)
        namespace = {'__name__': 'documented_string_operations'}
        exec(result.python_source, namespace)
        program = namespace['Program']()
        self.assertEqual(program.run(), {'TEXT':'part:robot', 'PAYLOAD':'robot', 'EMPTY':'', 'MATCH':1})
        self.assertEqual([row['text'] for row in program.write_requests], ['robot\n'])
