"""STRING function values and independent writable Pythonic arguments."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError


DECLARATIONS = 'text: STRING[8] out: STRING[254] small: STRING[3] x: INTEGER flag: BOOLEAN'


def compile_program(body, routines='', *, declarations=DECLARATIONS, prefix='', **context):
    source = f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result = translate(source, filename='pythonic_strings.kl')
    namespace = {'__name__': 'pythonic_string_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](**context), result


def execute(body, routines='', **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


class StringFunctionTests(unittest.TestCase):
    def test_default_string_result(self):
        self.assertEqual(execute('out=f()', "ROUTINE f: STRING BEGIN RETURN 'hello' END f")['OUT'], 'hello')

    def test_explicit_capacity_truncates_at_return(self):
        state = execute('out=f() x=STR_LEN(f())', "ROUTINE f: STRING[3] BEGIN RETURN 'abcdef' END f")
        self.assertEqual((state['OUT'], state['X']), ('abc', 3))

    def test_default_result_truncates_at_254(self):
        state = execute('out=f()', "ROUTINE f: STRING BEGIN RETURN '"+'a'*300+"' END f")
        self.assertEqual(state['OUT'], 'a'*254)

    def test_global_constant_capacity(self):
        self.assertEqual(execute('out=f()', "ROUTINE f: STRING[N+1] BEGIN RETURN 'abcdef' END f",
                                 prefix='CONST N=3')['OUT'], 'abcd')

    def test_empty_return_is_initialized(self):
        state = execute('out=f() flag=UNINIT(out)', "ROUTINE f: STRING BEGIN RETURN '' END f")
        self.assertEqual((state['OUT'], state['FLAG']), ('', False))

    def test_result_capture_precedes_local_frame_cleanup(self):
        routine = "ROUTINE f: STRING VAR local: STRING[4] BEGIN local='abcdef' RETURN local END f"
        program, _ = compile_program('out=f()', routine)
        self.assertEqual(program.run()['OUT'], 'abcd')
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_global_and_local_constants(self):
        routines = "ROUTINE f: STRING CONST C='local' BEGIN RETURN C END f\nROUTINE g: STRING BEGIN RETURN GLOBAL_TEXT END g"
        state = execute('out=f() text=g()', routines, prefix="CONST GLOBAL_TEXT='global'")
        self.assertEqual((state['OUT'], state['TEXT']), ('local', 'global'))

    def test_forwarded_return_applies_both_capacities(self):
        routines = "ROUTINE f: STRING[5] BEGIN RETURN 'abcdef' END f\nROUTINE g: STRING[3] BEGIN RETURN f() END g"
        self.assertEqual(execute('out=g()', routines)['OUT'], 'abc')

    def test_pure_string_function_composes_in_expressions(self):
        routine = "ROUTINE f: STRING BEGIN RETURN 'abc' END f"
        state = execute("out='['+f()+']' flag=f()='abc'", routine)
        self.assertEqual((state['OUT'], state['FLAG']), ('[abc]', True))

    def test_function_can_consume_another_string_result(self):
        routines = "ROUTINE f: STRING BEGIN RETURN 'abcdef' END f\nROUTINE first_two(p: STRING): STRING BEGIN RETURN SUB_STR(p,1,2) END first_two"
        self.assertEqual(execute('out=first_two(f())', routines)['OUT'], 'ab')

    def test_bare_zero_argument_function_name(self):
        program, result = compile_program('out=f', "ROUTINE f: STRING[8] BEGIN RETURN 'abc' END f")
        self.assertEqual(program.run()['OUT'], 'abc')
        self.assertEqual(result.report['bare_function_calls'][0]['result_spec'], ('STRING', 8))

    def test_function_arguments(self):
        routine = "ROUTINE label(n: INTEGER): STRING BEGIN IF n=1 THEN RETURN 'one' ELSE RETURN 'other' ENDIF END label"
        self.assertEqual(execute('out=label(1)', routine)['OUT'], 'one')

    def test_recursive_string_function(self):
        routine = "ROUTINE repeat_text(n: INTEGER): STRING BEGIN IF n=0 THEN RETURN '' ELSE RETURN repeat_text(n-1)+'x' ENDIF END repeat_text"
        program, _ = compile_program('out=repeat_text(12)', routine)
        self.assertEqual(program.run()['OUT'], 'x'*12)
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_caller_storage_applies_its_own_capacity(self):
        state = execute('small=f() out=f()', "ROUTINE f: STRING[8] BEGIN RETURN 'abcdef' END f")
        self.assertEqual((state['SMALL'], state['OUT']), ('abc', 'abcdef'))

    def test_result_does_not_alias_returned_storage(self):
        routine = 'ROUTINE f(p: STRING): STRING BEGIN RETURN p END f'
        state = execute("text='before' out=f(text) text='after'", routine)
        self.assertEqual((state['TEXT'], state['OUT']), ('after', 'before'))

    def test_returned_array_element(self):
        routine = "ROUTINE f: STRING VAR words: ARRAY[1] OF STRING[4] BEGIN words[1]='hello' RETURN words[1] END f"
        self.assertEqual(execute('out=f()', routine)['OUT'], 'hell')

    def test_returned_structure_field(self):
        routine = "ROUTINE f: STRING VAR packet: packet_t BEGIN packet.label='hello' RETURN packet.label END f"
        self.assertEqual(execute('out=f()', routine, prefix='TYPE packet_t=STRUCTURE label: STRING[4] ENDSTRUCTURE')['OUT'], 'hell')

    def test_direct_return_to_string_array_element(self):
        self.assertEqual(execute('words[1]=f()', "ROUTINE f: STRING BEGIN RETURN 'hello' END f",
                                 declarations='words: ARRAY[1] OF STRING[3]')['WORDS'], ['hel'])

    def test_returned_apostrophe_and_control_character(self):
        self.assertEqual(execute('out=f()', "ROUTINE f: STRING BEGIN RETURN 'can''t'+CHR(10) END f")['OUT'], "can't\n")

    def test_returned_string_used_in_write(self):
        program, _ = compile_program('WRITE(f(),CR)', "ROUTINE f: STRING BEGIN RETURN 'hello' END f")
        program.run()
        self.assertEqual(program.write_requests[0]['text'], 'hello\n')

    def test_nested_output_precedes_outer_string_result(self):
        program, _ = compile_program('WRITE(f(),CR)', "ROUTINE f: STRING BEGIN WRITE('inner',CR) RETURN 'outer' END f")
        program.run()
        self.assertEqual([row['text'] for row in program.write_requests], ['inner\n', 'outer\n'])

    def test_result_metadata_records_default_and_explicit_bounds(self):
        _, result = compile_program('out=f() text=g()', "ROUTINE f: STRING BEGIN RETURN 'abc' END f\nROUTINE g: STRING[4] BEGIN RETURN 'xyz' END g")
        declarations = result.report['string_routine_declarations']
        self.assertEqual([(row['capacity'], row['capacity_defaulted']) for row in declarations], [(254, True), (4, False)])
        self.assertEqual([row['capacity'] for row in result.report['string_returns']], [254, 4])
        self.assertTrue(all(row['evaluated_once'] and row['right_truncation'] for row in result.report['string_returns']))
        self.assertFalse(result.report['string_result_policy']['controller_validated'])


class WritableStringValueTests(unittest.TestCase):
    def test_literal_to_writable_formal(self):
        routine = "ROUTINE change(p: STRING) BEGIN p=p+'!' out=p END change"
        self.assertEqual(execute("change('seed')", routine)['OUT'], 'seed!')

    def test_empty_literal_to_writable_formal(self):
        routine = "ROUTINE change(p: STRING) BEGIN p='filled' out=p END change"
        self.assertEqual(execute("change('')", routine)['OUT'], 'filled')

    def test_grouped_variable_is_independent(self):
        routine = "ROUTINE change(p: STRING) BEGIN p='private' out=p END change"
        state = execute("text='caller' change((text))", routine)
        self.assertEqual((state['TEXT'], state['OUT']), ('caller', 'private'))

    def test_bare_variable_keeps_reference_and_capacity(self):
        routine = "ROUTINE change(p: STRING) BEGIN p='longervalue' out=p END change"
        state = execute("small='old' change(small)", routine)
        self.assertEqual((state['SMALL'], state['OUT']), ('lon', 'lon'))

    def test_grouped_small_variable_gets_254_capacity(self):
        routine = "ROUTINE change(p: STRING) BEGIN p='longervalue' out=p END change"
        state = execute("small='old' change((small))", routine)
        self.assertEqual((state['SMALL'], state['OUT']), ('old', 'longervalue'))

    def test_value_temporary_writes_truncate_at_254(self):
        routine = "ROUTINE change(p: STRING) BEGIN p='"+'a'*300+"' out=p x=STR_LEN(p) END change"
        state = execute("change('seed')", routine)
        self.assertEqual((state['OUT'], state['X']), ('a'*254, 254))

    def test_constant_argument_stays_immutable(self):
        routine = "ROUTINE change(p: STRING) BEGIN p='new' out=p END change"
        state = execute('change(C) text=C', routine, prefix="CONST C='seed'")
        self.assertEqual((state['OUT'], state['TEXT']), ('new', 'seed'))

    def test_two_value_arguments_do_not_alias(self):
        routine = "ROUTINE change(a,b: STRING) BEGIN a='new' out=b END change"
        state = execute("text='seed' change((text),(text))", routine)
        self.assertEqual((state['TEXT'], state['OUT']), ('seed', 'seed'))

    def test_value_copy_and_reference_can_share_original_source(self):
        routine = "ROUTINE change(a,b: STRING) BEGIN a='private' b='caller' out=a END change"
        state = execute("text='seed' change((text),text)", routine)
        self.assertEqual((state['TEXT'], state['OUT']), ('caller', 'private'))

    def test_reference_forwarding_updates_only_private_copy(self):
        routines = "ROUTINE change(p: STRING) BEGIN p='new' END change\nROUTINE forward(p: STRING) BEGIN change(p) out=p END forward"
        state = execute("text='seed' forward((text))", routines)
        self.assertEqual((state['TEXT'], state['OUT']), ('seed', 'new'))

    def test_grouped_forwarding_creates_another_copy(self):
        routines = "ROUTINE change(p: STRING) BEGIN p='new' END change\nROUTINE forward(p: STRING) BEGIN change((p)) out=p END forward"
        program, result = compile_program("forward('seed')", routines)
        self.assertEqual(program.run()['OUT'], 'seed')
        self.assertEqual(result.report['routine_effects']['FORWARD']['potential_parameter_writes'], [])

    def test_function_result_to_writable_formal(self):
        routines = "ROUTINE f: STRING[3] BEGIN RETURN 'abcdef' END f\nROUTINE change(p: STRING) BEGIN p=p+'!' out=p END change"
        self.assertEqual(execute('change(f())', routines)['OUT'], 'abc!')

    def test_writable_parameter_in_string_function(self):
        routine = "ROUTINE decorate(p: STRING): STRING BEGIN p=p+'!' RETURN p END decorate"
        state = execute("text='seed' out=decorate((text))", routine)
        self.assertEqual((state['TEXT'], state['OUT']), ('seed', 'seed!'))

    def test_recursive_value_copy(self):
        routine = "ROUTINE grow(p: STRING; n: INTEGER): STRING BEGIN IF n=0 THEN RETURN p ELSE p=p+'x' RETURN grow((p),n-1) ENDIF END grow"
        state = execute("text='seed' out=grow((text),3)", routine)
        self.assertEqual((state['TEXT'], state['OUT']), ('seed', 'seedxxx'))

    def test_conversion_can_write_to_private_temporary(self):
        routine = 'ROUTINE change(p: STRING) BEGIN CNV_INT_STR(42,1,16,p) out=p END change'
        self.assertEqual(execute("change('seed')", routine)['OUT'], ' 2A')

    def test_conversion_can_clear_private_temporary(self):
        routine = 'ROUTINE change(p: STRING) BEGIN CNV_INT_STR(1,1,1,p) flag=UNINIT(p) END change'
        state = execute("text='seed' change((text))", routine)
        self.assertEqual((state['TEXT'], state['FLAG']), ('seed', True))

    def test_real_formatting_uses_private_capacity(self):
        routine = 'ROUTINE change(p: STRING) BEGIN CNV_REAL_STR(0.125,1,2,p) out=p END change'
        state = execute("small='old' change((small))", routine)
        self.assertEqual((state['SMALL'], state['OUT']), ('old', ' 0.12'))

    def test_array_element_and_structure_field_copies(self):
        routine = "ROUTINE change(p: STRING) BEGIN p='private' out=p END change"
        for declaration, assignment, value in [('words: ARRAY[1] OF STRING[4]', "words[1]='seed'", 'words[1]'),
                                                ('packet: packet_t', "packet.label='seed'", 'packet.label')]:
            program, _ = compile_program(assignment+f' change(({value}))', routine,
                                         declarations=DECLARATIONS+' '+declaration,
                                         prefix='TYPE packet_t=STRUCTURE label: STRING[4] ENDSTRUCTURE')
            snapshot = program.run()
            self.assertEqual(snapshot['OUT'], 'private')
            self.assertEqual(snapshot['WORDS'][0] if 'WORDS' in snapshot else snapshot['PACKET']['LABEL'], 'seed')

    def test_uninitialized_input_fails_before_callee(self):
        routine = "ROUTINE change(p: STRING) BEGIN x=7 p='private' END change"
        program, _ = compile_program('x=0 change((text))', routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['X'], 0)
        self.assertEqual(program._state.local_frames, [])

    def test_overlong_input_fails_before_callee(self):
        routine = "ROUTINE change(p: STRING) BEGIN x=7 p='private' END change"
        program, _ = compile_program("x=0 change('"+'a'*255+"')", routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'limited to 254'): program.run()
        self.assertEqual(program.snapshot()['X'], 0)

    def test_value_copy_remains_private_on_failure(self):
        routine = "ROUTINE change(p: STRING) BEGIN p='private' x=7 x=1 DIV 0 END change"
        program, _ = compile_program("text='seed' change((text))", routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['TEXT'], program.snapshot()['X']), ('seed', 7))
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_reference_keeps_earlier_write_on_failure(self):
        routine = "ROUTINE change(p: STRING) BEGIN p='private' x=1 DIV 0 END change"
        program, _ = compile_program("text='seed' change(text)", routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['TEXT'], 'private')

    def test_abort_unwinds_private_string_frame(self):
        program, _ = compile_program("text='seed' change((text))", "ROUTINE change(p: STRING) BEGIN p='private' ABORT END change")
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual(program.snapshot()['TEXT'], 'seed')
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_callback_failure_does_not_write_back(self):
        def write(text): raise OSError('sink failed')
        program, _ = compile_program("text='seed' change((text))", "ROUTINE change(p: STRING) BEGIN p='private' WRITE(p,CR) END change", write=write)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'sink failed'): program.run()
        self.assertEqual(program.snapshot()['TEXT'], 'seed')
        self.assertEqual(program.write_requests[0]['text'], 'private\n')
        self.assertEqual(program._state.local_frames, [])

    def test_argument_metadata_explains_writable_capacity(self):
        _, result = compile_program("change('seed')", "ROUTINE change(p: STRING) BEGIN p='private' END change")
        argument = result.report['string_value_arguments'][0]
        self.assertTrue(argument['independent_writable_copy'])
        self.assertEqual(argument['temporary_capacity'], 254)
        parameter = result.report['routine_effects']['CHANGE']['parameters'][0]
        self.assertEqual(parameter['passing_modes'], ['reference', 'value'])


class StringResultValidationTests(unittest.TestCase):
    def test_wrong_result_types(self):
        for value in ('1', '1.0', 'TRUE'):
            with self.subTest(value=value), self.assertRaises(TranslationError) as caught:
                compile_program('out=f()', f'ROUTINE f: STRING BEGIN RETURN {value} END f')
            self.assertEqual(caught.exception.code, 'E_RETURN')

    def test_invalid_capacities(self):
        for capacity in ('0', '-1', '255', 'TRUE'):
            with self.subTest(capacity=capacity), self.assertRaises(TranslationError) as caught:
                compile_program('out=f()', f"ROUTINE f: STRING[{capacity}] BEGIN RETURN 'abc' END f")
            self.assertEqual(caught.exception.code, 'E_SIZE')

    def test_local_constant_does_not_define_interface_capacity(self):
        with self.assertRaises(TranslationError):
            compile_program('out=f()', "ROUTINE f: STRING[N] CONST N=3 BEGIN RETURN 'abc' END f")

    def test_missing_return_preserves_destination_and_unwinds(self):
        program, _ = compile_program("out='keep' out=f()", 'ROUTINE f: STRING BEGIN END f')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'without RETURN'): program.run()
        self.assertEqual(program.snapshot()['OUT'], 'keep')
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_uninitialized_return_preserves_destination(self):
        program, _ = compile_program("out='keep' out=f()", 'ROUTINE f: STRING VAR value: STRING[8] BEGIN RETURN value END f')
        with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
        self.assertIsNotNone(caught.exception.line)
        self.assertEqual(program.snapshot()['OUT'], 'keep')

    def test_nonascii_is_checked_before_return_truncation(self):
        program, _ = compile_program("out='keep' out=f()", 'ROUTINE f: STRING[1] BEGIN RETURN text END f')
        program._state.values['TEXT'] = 'a\u00e9'
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['OUT'], 'keep')

    def test_invalid_host_string_input_rejected(self):
        for value in (True, 1, 'a\u00e9'):
            program, _ = compile_program('change((text))', "ROUTINE change(p: STRING) BEGIN p='new' END change")
            program._state.values['TEXT'] = value
            with self.assertRaises(rt.KarelRuntimeError): program.run()

    def test_function_result_not_an_integer(self):
        with self.assertRaises(TranslationError):
            compile_program('x=f()', "ROUTINE f: STRING BEGIN RETURN 'abc' END f")

    def test_existing_effect_guard_remains(self):
        routine = "ROUTINE f: STRING BEGIN x=x+1 RETURN 'abc' END f"
        with self.assertRaises(TranslationError) as caught: compile_program("out=f()+'!'", routine)
        self.assertEqual(caught.exception.code, 'E_EVALUATION_ORDER')

    def test_multi_argument_nested_call_guard_remains(self):
        routine = "ROUTINE f: STRING BEGIN RETURN 'abc' END f"
        with self.assertRaises(TranslationError) as caught: compile_program("x=INDEX(f(),'b')", routine)
        self.assertEqual(caught.exception.code, 'E_EVALUATION_ORDER')

    def test_call_depth_failure_unwinds_string_frames(self):
        routine = 'ROUTINE f(n: INTEGER): STRING BEGIN RETURN f(n+1) END f'
        program, _ = compile_program("out='keep' out=f(0)", routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'call-depth'): program.run()
        self.assertEqual(program.snapshot()['OUT'], 'keep')
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_cli_generates_runnable_string_functions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'input.kl'
            source.write_text("PROGRAM T VAR text: STRING[8] ROUTINE f: STRING BEGIN RETURN 'hello' END f BEGIN text=f() WRITE(text,CR) END T", encoding='utf-8')
            process = subprocess.run([sys.executable, '-m', 'karel2py', str(source), '-o', str(root/'converted.py'),
                                      '--report', str(root/'result.json')], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            report = json.loads((root/'result.json').read_text(encoding='utf-8'))
            self.assertEqual(report['string_routine_declarations'][0]['capacity'], 254)
            namespace = {'__name__': 'cli_string_test'}
            exec((root/'converted.py').read_text(encoding='utf-8'), namespace)
            program = namespace['Program']()
            self.assertEqual(program.run()['TEXT'], 'hello')
            self.assertEqual(program.write_requests[0]['text'], 'hello\n')
