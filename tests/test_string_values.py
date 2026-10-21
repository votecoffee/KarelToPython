"""Read-only STRING temporaries, captured values and transitive write guards."""
from pathlib import Path
import unittest

from tests.legacy_numeric_support import translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


DECLARATIONS = 'text: STRING[16]\nout: STRING[254]\nx,y: INTEGER\nflag: BOOLEAN\nwords: ARRAY[2] OF STRING[8]'
READ = 'ROUTINE read_text(p: STRING) BEGIN out=p x=STR_LEN(p) END read_text'
WRITE = "ROUTINE write_text(p: STRING) BEGIN p='changed' END write_text"


def compile_program(body, routines=READ, declarations=DECLARATIONS, prefix=''):
    source = f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result = translate(source, filename='string_values.kl')
    namespace = {'__name__': 'string_value_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def run(body, **kwargs): return compile_program(body, **kwargs)[0].run()


class StringValueBehaviorTests(unittest.TestCase):
    def test_literal(self): self.assertEqual(run("read_text('abc')")['OUT'], 'abc')
    def test_empty_literal_is_initialized(self):
        routine = 'ROUTINE r(p: STRING) BEGIN flag=UNINIT(p) x=STR_LEN(p) out=p END r'
        state = run("r('')", routines=routine)
        self.assertEqual((state['FLAG'], state['X'], state['OUT']), (False, 0, ''))
    def test_global_constant(self): self.assertEqual(run('read_text(C)', prefix="CONST C='abc'")['OUT'], 'abc')
    def test_grouped_constant(self): self.assertEqual(run('read_text((C))', prefix="CONST C='abc'")['OUT'], 'abc')
    def test_grouped_variable(self): self.assertEqual(run("text='abc' read_text((text))")['OUT'], 'abc')
    def test_nested_grouping(self): self.assertEqual(run("text='abc' read_text((((text))))")['OUT'], 'abc')
    def test_concatenation(self): self.assertEqual(run("text='abc' read_text(text+'!')")['OUT'], 'abc!')
    def test_builtin_chr(self): self.assertEqual(run('read_text(CHR(65))')['OUT'], 'A')
    def test_builtin_substring(self): self.assertEqual(run("read_text(SUB_STR('abcdef',2,3))")['OUT'], 'bcd')
    def test_ascii_control(self): self.assertEqual(run('read_text(CHR(0))')['OUT'], '\x00')
    def test_shorter_destination_applies_existing_assignment_bound(self):
        state = run("read_text('abcdef')", declarations=DECLARATIONS.replace('out: STRING[254]', 'out: STRING[2]'))
        self.assertEqual((state['OUT'], state['X']), ('ab', 6))
    def test_array_element_copy(self):
        state = run("words[1]='robot' read_text((words[1]))")
        self.assertEqual((state['OUT'], state['WORDS'][0]), ('robot', 'robot'))
    def test_multidimensional_element_copy(self):
        state = run("grid[1,2]='robot' read_text((grid[1,2]))", declarations=DECLARATIONS+'\ngrid: ARRAY[2,2] OF STRING[8]')
        self.assertEqual(state['OUT'], 'robot')
    def test_structure_field_copy(self):
        state = run("packet.label='robot' read_text((packet.label))", prefix='TYPE packet_t=STRUCTURE label: STRING[8] ENDSTRUCTURE', declarations=DECLARATIONS+'\npacket: packet_t')
        self.assertEqual((state['OUT'], state['PACKET']['LABEL']), ('robot', 'robot'))
    def test_nested_structure_array_field_copy(self):
        prefix = 'TYPE child_t=STRUCTURE label: STRING[8] ENDSTRUCTURE\nparent_t=STRUCTURE child: child_t ENDSTRUCTURE'
        state = run("packets[2].child.label='robot' read_text((packets[2].child.label))", prefix=prefix, declarations=DECLARATIONS+'\npackets: ARRAY[2] OF parent_t')
        self.assertEqual(state['OUT'], 'robot')
    def test_named_subarray_element_copy(self):
        prefix = 'TYPE row_t=ARRAY[2] OF STRING[8]\ngrid_t=ARRAY[2] OF row_t'
        state = run("grid[2,1]='robot' read_text((grid[2,1]))", prefix=prefix, declarations=DECLARATIONS+'\ngrid: grid_t')
        self.assertEqual(state['OUT'], 'robot')
    def test_local_constant(self):
        wrapper = "ROUTINE work CONST C='local' BEGIN read_text(C) END work"
        self.assertEqual(run('work', routines=READ+'\n'+wrapper)['OUT'], 'local')
    def test_local_variable(self):
        wrapper = "ROUTINE work VAR local: STRING[8] BEGIN local='local' read_text((local)) END work"
        self.assertEqual(run('work', routines=READ+'\n'+wrapper)['OUT'], 'local')
    def test_nested_reference_forwarding_retains_read_only_copy(self):
        forward = 'ROUTINE forward(p: STRING) BEGIN read_text(p) END forward'
        self.assertEqual(run("forward('abc')", routines=READ+'\n'+forward)['OUT'], 'abc')
    def test_nested_value_forwarding_creates_independent_copy(self):
        forward = "ROUTINE forward(p: STRING) BEGIN read_text((p+'!')) END forward"
        self.assertEqual(run("forward('abc')", routines=READ+'\n'+forward)['OUT'], 'abc!')
    def test_snapshot_survives_caller_global_change(self):
        routine = "ROUTINE r(p: STRING) BEGIN text='changed' out=p END r"
        state = run("text='original' r((text))", routines=routine)
        self.assertEqual((state['TEXT'], state['OUT']), ('changed', 'original'))
    def test_bare_reference_observes_global_change(self):
        routine = "ROUTINE r(p: STRING) BEGIN text='changed' out=p END r"
        self.assertEqual(run("text='original' r(text)", routines=routine)['OUT'], 'changed')
    def test_two_value_arguments_can_copy_same_source(self):
        routine = "ROUTINE r(p,q: STRING) BEGIN text='changed' out=p+q END r"
        state = run("text='abc' r((text),(text))", routines=routine)
        self.assertEqual((state['TEXT'], state['OUT']), ('changed', 'abcabc'))
    def test_value_input_and_writable_reference_output(self):
        routine = 'ROUTINE copy(p,q: STRING) BEGIN q=p END copy'
        state = run("text='abc' copy((text),text)", routines=routine)
        self.assertEqual(state['TEXT'], 'abc')
    def test_read_only_input_to_integer_conversion(self):
        routine = 'ROUTINE parse(p: STRING; q: INTEGER) BEGIN CNV_STR_INT(p,q) END parse'
        self.assertEqual(run("parse('42',x)", routines=routine)['X'], 42)
    def test_read_only_input_to_real_conversion(self):
        routine = 'ROUTINE parse(p: STRING; q: REAL) BEGIN CNV_STR_REAL(p,q) END parse'
        self.assertEqual(run("parse('2.5',number)", routines=routine, declarations=DECLARATIONS+'\nnumber: REAL')['NUMBER'], 2.5)
    def test_integer_function_result(self):
        routine = 'ROUTINE length(p: STRING): INTEGER BEGIN RETURN STR_LEN(p) END length'
        self.assertEqual(run("x=length('robot')", routines=routine)['X'], 5)
    def test_boolean_function_result(self):
        routine = "ROUTINE ready(p: STRING): BOOLEAN BEGIN RETURN p='ready' END ready"
        self.assertTrue(run("flag=ready('ready')", routines=routine)['FLAG'])
    def test_read_only_function_in_operator(self):
        routine = 'ROUTINE length(p: STRING): INTEGER BEGIN RETURN STR_LEN(p) END length'
        self.assertEqual(run("x=length('robot')+2", routines=routine)['X'], 7)
    def test_recursive_value_forwarding(self):
        routine = 'ROUTINE count(p: STRING; n: INTEGER): INTEGER BEGIN IF n=0 THEN RETURN STR_LEN(p) ELSE RETURN count((p),n-1) ENDIF END count'
        self.assertEqual(run("x=count('abc',3)", routines=routine)['X'], 3)
    def test_mutual_recursive_reference_forwarding(self):
        routines = ('ROUTINE a(p: STRING; n: INTEGER): INTEGER BEGIN IF n=0 THEN RETURN STR_LEN(p) ELSE RETURN b(p,n-1) ENDIF END a\n'
                    'ROUTINE b(q: STRING; n: INTEGER): INTEGER BEGIN RETURN a(q,n-1) END b')
        self.assertEqual(run("x=a('abc',4)", routines=routines)['X'], 3)
    def test_routine_local_for(self):
        routine = 'ROUTINE work VAR i: INTEGER BEGIN FOR i=1 TO 3 DO read_text(CHR(64+i)) ENDFOR flag=UNINIT(i) END work'
        state = run('work', routines=READ+'\n'+routine)
        self.assertEqual((state['OUT'], state['FLAG']), ('C', True))
    def test_label_dispatcher(self):
        state = run("GOTO start read_text('skipped') start:: read_text('chosen')")
        self.assertEqual(state['OUT'], 'chosen')
    def test_using_resolves_grouped_field(self):
        state = run("packet.label='robot' USING packet DO read_text((label)) ENDUSING", prefix='TYPE packet_t=STRUCTURE label: STRING[8] ENDSTRUCTURE', declarations=DECLARATIONS+'\npacket: packet_t')
        self.assertEqual(state['OUT'], 'robot')
    def test_argument_expression_evaluated_once(self):
        routines = READ+'\nROUTINE next_code: INTEGER BEGIN y=y+1 RETURN 64+y END next_code'
        state = run('y=0 read_text(CHR(next_code()))', routines=routines)
        self.assertEqual((state['Y'], state['OUT']), (1, 'A'))
    def test_maximum_logical_length(self):
        state = run("read_text('"+'a'*254+"')")
        self.assertEqual((state['X'], len(state['OUT'])), (254, 254))
    def test_report_records_static_value_site(self):
        _, result = compile_program("read_text('abc')")
        site = result.report['string_value_arguments'][0]
        self.assertEqual((site['body'], site['routine'], site['parameter'], site['expression_kind']), ('T','READ_TEXT','P','literal'))
        self.assertTrue(site['evaluated_once'])
        self.assertEqual(result.report['routine_effects']['READ_TEXT']['potential_parameter_writes'], [])
        self.assertEqual(result.report['routine_effects']['READ_TEXT']['parameters'][0]['passing_modes'], ['reference','value_read_only'])
    def test_per_formal_effects(self):
        routine = 'ROUTINE copy(source,destination: STRING) BEGIN destination=source END copy'
        _, result = compile_program("copy('abc',text)", routines=routine)
        effect = result.report['routine_effects']['COPY']
        self.assertEqual(effect['potential_parameter_writes'], ['DESTINATION'])
        self.assertEqual(effect['parameters'][0]['passing_modes'], ['reference','value_read_only'])
        self.assertEqual(effect['parameters'][1]['passing_modes'], ['reference'])
    def test_callee_global_write_does_not_write_same_named_caller_formal(self):
        routines = "ROUTINE change BEGIN text='changed' END change\nROUTINE r(text: STRING) BEGIN change out=text END r"
        state = run("text='original' r((text))", routines=routines)
        self.assertEqual((state['TEXT'],state['OUT']),('changed','original'))
    def test_permuted_read_only_input_and_reference_output(self):
        routines = 'ROUTINE copy(p,q: STRING) BEGIN q=p END copy\nROUTINE forward(a,b: STRING) BEGIN copy(b,a) END forward'
        program,result = compile_program("forward(text,'abc')", routines=routines)
        self.assertEqual(program.run()['TEXT'],'abc')
        self.assertEqual(result.report['routine_effects']['FORWARD']['potential_parameter_writes'],['A'])
    def test_grouped_numeric_write_does_not_propagate_to_caller_formal(self):
        routines = 'ROUTINE set_count(n: INTEGER) BEGIN n=9 END set_count\nROUTINE r(p: STRING; n: INTEGER) BEGIN set_count((n)) out=p END r'
        program,result = compile_program("y=1 r('abc',y)", routines=routines)
        self.assertEqual(program.run()['Y'],1)
        self.assertEqual(result.report['routine_effects']['R']['potential_parameter_writes'],[])
    def test_separate_translation_does_not_leak_effects(self):
        compile_program('write_text(text)', routines=WRITE)
        self.assertEqual(run("read_text('abc')")['OUT'], 'abc')
    def test_generated_example(self):
        path = Path(__file__).resolve().parents[1]/'examples/string_value_inputs.kl'
        result = translate(path.read_text())
        namespace = {'__name__':'example_test'}
        exec(result.python_source, namespace)
        self.assertEqual(namespace['Program']().run()['PARSED'], 42)


class StringValueRejectionTests(unittest.TestCase):
    def reject(self, body, routines=WRITE, code='E_STRING_VALUE', **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, routines=routines, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
    def test_direct_formal_write(self): self.reject("write_text('abc')")
    def test_grouped_variable_to_writer(self): self.reject("write_text((text))")
    def test_local_constant_to_writer(self): self.reject('work', routines=WRITE+"\nROUTINE work CONST C='abc' BEGIN write_text(C) END work")
    def test_write_after_return_is_conservatively_blocked(self): self.reject("write_text('abc')", routines="ROUTINE write_text(p: STRING) BEGIN RETURN; p='changed' END write_text")
    def test_unreachable_branch_write(self): self.reject("write_text('abc')", routines="ROUTINE write_text(p: STRING) BEGIN IF OFF THEN p='changed' ENDIF END write_text")
    def test_transitive_reference_write(self): self.reject("forward('abc')", routines=WRITE+'\nROUTINE forward(p: STRING) BEGIN write_text(p) END forward')
    def test_multiple_hop_write(self): self.reject("outer('abc')", routines=WRITE+'\nROUTINE inner(q: STRING) BEGIN write_text(q) END inner\nROUTINE outer(p: STRING) BEGIN inner(p) END outer')
    def test_recursive_write(self): self.reject("r('abc',0)", routines="ROUTINE r(p: STRING; n: INTEGER) BEGIN IF n=0 THEN p='changed' ELSE r(p,n-1) ENDIF END r")
    def test_mutual_recursive_write(self):
        routines = "ROUTINE a(p: STRING; n: INTEGER) BEGIN b(p,n) END a\nROUTINE b(q: STRING; n: INTEGER) BEGIN IF n=0 THEN q='changed' ELSE a(q,n-1) ENDIF END b"
        self.reject("a('abc',0)", routines=routines)
    def test_grouped_forward_to_writer_still_blocked(self): self.reject('forward(text)', routines=WRITE+'\nROUTINE forward(p: STRING) BEGIN write_text((p)) END forward')
    def test_conversion_integer_output_write(self): self.reject("r('abc')", routines='ROUTINE r(p: STRING) BEGIN CNV_INT_STR(1,1,0,p) END r')
    def test_conversion_real_output_write(self): self.reject("r('abc')", routines='ROUTINE r(p: STRING) BEGIN CNV_REAL_STR(2.5,1,1,p) END r')
    def test_writable_second_formal_value(self): self.reject("copy(text,'abc')", routines='ROUTINE copy(p,q: STRING) BEGIN q=p END copy')
    def test_parameter_permutation_propagates_correct_write(self):
        routines = 'ROUTINE copy(p,q: STRING) BEGIN q=p END copy\nROUTINE forward(a,b: STRING) BEGIN copy(b,a) END forward'
        self.reject("forward('abc',text)", routines=routines)
    def test_function_nested_in_expression_write(self):
        routines = "ROUTINE mutate(p: STRING): INTEGER BEGIN p='changed' RETURN 1 END mutate\nROUTINE r(q: STRING) BEGIN x=mutate(q) END r"
        self.reject("r('abc')", routines=routines)
    def test_wrong_actual_type(self): self.reject('read_text(1)', routines=READ, code='E_TYPE')
    def test_string_function_result_remains_blocked(self): self.reject("out=f()", routines="ROUTINE f: STRING[8] BEGIN RETURN 'abc' END f", code='E_RETURN_TYPE')
    def test_whole_array_value_remains_blocked(self): self.reject('r((words))', routines='ROUTINE r(p: ARRAY OF STRING) BEGIN END r', code='E_ARRAY_VALUE')
    def test_multi_argument_routine_order_stays_blocked(self):
        routines = 'ROUTINE code: INTEGER BEGIN RETURN 65 END code\nROUTINE r(p,q: STRING) BEGIN END r'
        self.reject("r(CHR(code()),'a')", routines=routines, code='E_EVALUATION_ORDER')
    def test_timing_effect_in_operator_stays_blocked(self):
        routine = 'ROUTINE f(p: STRING): INTEGER BEGIN DELAY 0 RETURN STR_LEN(p) END f'
        self.reject("x=f('a')+1", routines=routine, code='E_EVALUATION_ORDER')
    def test_reference_write_remains_supported(self): self.assertEqual(run("text='abc' write_text(text)", routines=WRITE)['TEXT'], 'changed')
    def test_transitive_reference_write_remains_supported(self): self.assertEqual(run("text='abc' forward(text)", routines=WRITE+'\nROUTINE forward(p: STRING) BEGIN write_text(p) END forward')['TEXT'], 'changed')


class StringValueRuntimeTests(unittest.TestCase):
    def test_uninitialized_copy_fails_before_call(self):
        program, _ = compile_program('read_text((text))')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0, []))
    def test_out_of_bounds_copy_fails_before_call(self):
        program, _ = compile_program('read_text((words[3]))')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program._state.call_depth, 0)
    def test_overlong_expression_preserves_prior_writes(self):
        program, _ = compile_program("x=9 text='"+'a'*16+"' read_text("+'+'.join(['text']*16)+')')
        with self.assertRaisesRegex(rt.KarelRuntimeError, '254 characters'): program.run()
        self.assertEqual((program._state.get('X'), program._state.call_depth), (9, 0))
    def test_exception_cleans_forwarded_frames(self):
        routines = 'ROUTINE fail(p: STRING) BEGIN out=p x=1 DIV 0 END fail\nROUTINE r(q: STRING) BEGIN fail(q) END r'
        program, _ = compile_program("r('abc')", routines=routines)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program._state.get('OUT'), program._state.call_depth, program._state.local_frames), ('abc',0,[]))
    def test_step_budget_cleans_frames(self):
        routine = 'ROUTINE r(p: STRING) BEGIN WHILE ON DO out=p ENDWHILE END r'
        program, _ = compile_program("r('abc')", routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'step budget'): program.run(max_steps=10)
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0,[]))
    def test_call_depth_cleans_frames(self):
        routine = 'ROUTINE r(p: STRING) BEGIN r(p) END r'
        program, _ = compile_program("r('abc')", routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'call-depth'): program.run()
        self.assertEqual((program._state.call_depth, program._state.local_frames), (0,[]))
    def test_runtime_adapter_has_no_capacity(self):
        reference = rt.string_value_argument('abc', 7)
        self.assertEqual((reference.spec, reference.raw()), (('STRING',None),'abc'))
    def test_runtime_adapter_rejects_write(self):
        reference = rt.string_value_argument('abc')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'line 7'): reference.set('changed',7)
        self.assertEqual(reference.raw(), 'abc')
    def test_runtime_adapter_rejects_clear(self):
        reference = rt.string_value_argument('abc')
        with self.assertRaises(rt.KarelRuntimeError): reference.clear()
        self.assertEqual(reference.raw(), 'abc')
    def test_runtime_adapter_rejects_wrong_type(self):
        with self.assertRaises(rt.KarelRuntimeError): rt.string_value_argument(1,7)
    def test_runtime_adapter_rejects_non_ascii(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'ASCII'): rt.string_value_argument('\u00e9',7)
    def test_runtime_adapter_rejects_overlong_value(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError, '254 characters'): rt.string_value_argument('a'*255,7)
    def test_forwarded_reference_cannot_mutate_temporary(self):
        state = rt.State({}, {})
        reference = rt.string_value_argument('abc')
        state.enter_routine({'P':('STRING',None)}, arguments={'P':reference})
        self.assertIs(state.reference('P'), reference)
        with self.assertRaises(rt.KarelRuntimeError): state.set('P','changed',7)
        self.assertEqual(state.get('P'), 'abc')
        state.leave_routine()


if __name__ == '__main__': unittest.main()
