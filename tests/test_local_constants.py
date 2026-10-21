"""Lexical constant scope, caller isolation and checked declaration behavior."""
import ast
import unittest

from karel2py import translate
from karel2py.lexer import TranslationError
from karel2py.runtime import KarelRuntimeError


def compile_program(body='work', routines='', prefix='', declarations='x,y,result: INTEGER\nflag: BOOLEAN\nreal_value: REAL\ntext: STRING[8]'):
    source = f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    generated = translate(source, filename='local_constants.kl')
    ast.parse(generated.python_source, feature_version=(3, 11))
    namespace = {'__name__': 'local_constant_test'}
    exec(generated.python_source, namespace)
    return namespace['Program'](), generated


def execute(routines, body='work', **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


class LocalConstantBehaviorTests(unittest.TestCase):
    def test_procedure_constant(self):
        state = execute('ROUTINE work CONST step=7 BEGIN result=step END work')
        self.assertEqual(state['RESULT'], 7)
        self.assertNotIn('STEP', state)

    def test_integer_function_result(self):
        state = execute('ROUTINE work: INTEGER CONST step=7 BEGIN RETURN step END work', 'result=work()')
        self.assertEqual(state['RESULT'], 7)

    def test_boolean_function_result(self):
        state = execute('ROUTINE work: BOOLEAN CONST yes=ON BEGIN RETURN yes END work', 'flag=work()')
        self.assertTrue(state['FLAG'])

    def test_exact_real_function_result(self):
        state = execute('ROUTINE work: REAL CONST half=1.25 BEGIN RETURN half END work', 'real_value=work()')
        self.assertEqual(state['REAL_VALUE'], 1.25)

    def test_local_constant_dependencies(self):
        self.assertEqual(execute('ROUTINE work CONST a=2 b=a*3 c=b+1 BEGIN result=c END work')['RESULT'], 7)

    def test_global_constant_dependency(self):
        state = execute('ROUTINE work CONST step=global_step+1 BEGIN result=step END work', prefix='CONST global_step=6')
        self.assertEqual(state['RESULT'], 7)

    def test_sibling_scopes_reuse_name(self):
        routines = 'ROUTINE first CONST step=7 BEGIN x=step END first\nROUTINE second CONST step=9 BEGIN y=step END second'
        state = execute(routines, 'first second')
        self.assertEqual((state['X'], state['Y']), (7, 9))

    def test_sibling_scopes_reuse_name_with_different_type(self):
        routines = 'ROUTINE first CONST step=7 BEGIN x=step END first\nROUTINE second CONST step=ON BEGIN flag=step END second'
        state = execute(routines, 'first second')
        self.assertEqual((state['X'], state['FLAG']), (7, True))

    def test_callee_local_variable_independent_of_caller_constant(self):
        routines = 'ROUTINE child VAR step: INTEGER BEGIN step=9 y=step END child\nROUTINE work CONST step=7 BEGIN child x=step END work'
        state = execute(routines)
        self.assertEqual((state['X'], state['Y']), (7, 9))

    def test_callee_constant_independent_of_caller_local_variable(self):
        routines = 'ROUTINE child CONST step=9 BEGIN y=step END child\nROUTINE work VAR step: INTEGER BEGIN step=7 child x=step END work'
        state = execute(routines)
        self.assertEqual((state['X'], state['Y']), (7, 9))

    def test_recursive_calls_keep_constant_and_fresh_variables(self):
        routines = 'ROUTINE factorial(n: INTEGER): INTEGER CONST one=1 VAR next: INTEGER BEGIN IF n=0 THEN RETURN one ENDIF next=n-one RETURN n*factorial((next)) END factorial'
        program, _ = compile_program('result=factorial(5)', routines)
        self.assertEqual(program.run()['RESULT'], 120)
        self.assertEqual(program._state.local_frames, [])

    def test_repeated_calls_do_not_change_constant(self):
        self.assertEqual(execute('ROUTINE work CONST step=7 BEGIN result=result+step END work', 'result=0 work work')['RESULT'], 14)

    def test_scalar_constant_argument_is_value(self):
        routines = 'ROUTINE change(p: INTEGER) BEGIN p=99 y=p END change\nROUTINE work CONST step=7 BEGIN change(step) x=step END work'
        state = execute(routines)
        self.assertEqual((state['X'], state['Y']), (7, 99))

    def test_same_constant_arguments_are_independent(self):
        routines = 'ROUTINE change(p,q: INTEGER) BEGIN p=99 y=q END change\nROUTINE work CONST step=7 BEGIN change(step,step) x=step END work'
        state = execute(routines)
        self.assertEqual((state['X'], state['Y']), (7, 7))

    def test_parenthesized_constant_is_value(self):
        routines = 'ROUTINE change(p: INTEGER) BEGIN p=99 END change\nROUTINE work CONST step=7 BEGIN change((step)) x=step END work'
        self.assertEqual(execute(routines)['X'], 7)

    def test_integer_constant_to_real_value_promotion(self):
        routines = 'ROUTINE change(p: REAL) BEGIN p=9.5 real_value=p END change\nROUTINE work CONST step=7 BEGIN change(step) x=step END work'
        state = execute(routines)
        self.assertEqual((state['X'], state['REAL_VALUE']), (7, 9.5))

    def test_boolean_constant_value_argument(self):
        routines = 'ROUTINE change(p: BOOLEAN) BEGIN p=OFF END change\nROUTINE work CONST yes=ON BEGIN change(yes) flag=yes END work'
        self.assertTrue(execute(routines)['FLAG'])

    def test_real_constant_value_argument(self):
        routines = 'ROUTINE change(p: REAL) BEGIN p=9.5 END change\nROUTINE work CONST amount=1.25 BEGIN change(amount) real_value=amount END work'
        self.assertEqual(execute(routines)['REAL_VALUE'], 1.25)

    def test_string_constant_truncates_at_destination(self):
        state = execute("ROUTINE work CONST label='abcdefghi' BEGIN text=label END work")
        self.assertEqual(state['TEXT'], 'abcdefgh')

    def test_empty_string_constant(self):
        self.assertEqual(execute("ROUTINE work CONST label='' BEGIN text=label x=STR_LEN(label) END work")['X'], 0)

    def test_string_constant_expression(self):
        state = execute("ROUTINE work CONST a='ab' b=a+'cd' BEGIN text=b x=INDEX(b,a) END work")
        self.assertEqual((state['TEXT'], state['X']), ('abcd', 1))

    def test_local_array_dimension(self):
        routines = 'ROUTINE work CONST count=3 VAR a: ARRAY[count] OF INTEGER BEGIN a[count]=7 result=ARRAY_LEN(a) x=a[3] END work'
        state = execute(routines)
        self.assertEqual((state['X'], state['RESULT']), (7, 3))

    def test_local_multidimensional_array(self):
        routines = 'ROUTINE work CONST rows=2 columns=3 VAR a: ARRAY[rows,columns] OF INTEGER BEGIN a[rows,columns]=7 result=a[2,3] END work'
        self.assertEqual(execute(routines)['RESULT'], 7)

    def test_local_three_dimensional_array(self):
        routines = 'ROUTINE work CONST n=2 VAR a: ARRAY[n,n,n] OF INTEGER BEGIN a[n,n,n]=7 result=a[2,2,2] END work'
        self.assertEqual(execute(routines)['RESULT'], 7)

    def test_local_named_component_dimension(self):
        routines = 'ROUTINE work CONST rows=2 VAR a: ARRAY[rows] OF row_t BEGIN a[rows,2]=7 result=a[2,2] END work'
        self.assertEqual(execute(routines, prefix='TYPE row_t=ARRAY[2] OF INTEGER')['RESULT'], 7)

    def test_local_string_capacity(self):
        routines = "ROUTINE work CONST width=3 VAR local_text: STRING[width] BEGIN local_text='abcdef' text=local_text END work"
        self.assertEqual(execute(routines)['TEXT'], 'abc')

    def test_var_then_const_then_var_source_order(self):
        routines = 'ROUTINE work VAR first: INTEGER CONST count=3 VAR a: ARRAY[count] OF INTEGER BEGIN first=count a[3]=first result=a[3] END work'
        self.assertEqual(execute(routines)['RESULT'], 3)

    def test_multiple_const_sections(self):
        routines = 'ROUTINE work CONST a=2 VAR unused: INTEGER CONST b=a+1 BEGIN result=b END work'
        self.assertEqual(execute(routines)['RESULT'], 3)

    def test_local_select_case_constant(self):
        routines = 'ROUTINE work CONST selected=2 alias=selected BEGIN SELECT selected OF CASE(alias): result=7 CASE(2): result=9 ENDSELECT END work'
        self.assertEqual(execute(routines)['RESULT'], 7)

    def test_label_dispatcher_retains_local_constant(self):
        routines = 'ROUTINE work CONST last=3 VAR i: INTEGER BEGIN i=0 again:: i=i+1 IF i<last THEN GOTO again ENDIF result=i END work'
        self.assertEqual(execute(routines)['RESULT'], 3)

    def test_local_for_bound_and_helper_value_call(self):
        routines = 'ROUTINE add(p: INTEGER) BEGIN result=result+p END add\nROUTINE work CONST last=3 VAR i: INTEGER BEGIN FOR i=1 TO last DO add((i)) ENDFOR flag=UNINIT(i) END work'
        state = execute(routines, 'result=0 work')
        self.assertEqual((state['RESULT'], state['FLAG']), (6, True))

    def test_predefined_bound_constants(self):
        routines = 'ROUTINE work CONST lower=MININT upper=MAXINT yes=ON no=OFF BEGIN x=lower y=upper-1 flag=yes OR no END work'
        state = execute(routines)
        self.assertEqual((state['X'], state['Y'], state['FLAG']), (-2147483648, 2147483646, True))

    def test_local_constant_in_using_without_field_collision(self):
        routines = 'ROUTINE work CONST amount=7 VAR record: item_t BEGIN USING record DO count=amount ENDUSING result=record.count END work'
        self.assertEqual(execute(routines, prefix='TYPE item_t=STRUCTURE count: INTEGER ENDSTRUCTURE')['RESULT'], 7)

    def test_using_unqualified_constant_collision_in_expression(self):
        routines = 'ROUTINE work CONST count=7 VAR record: item_t BEGIN USING record DO record.count=count+1 ENDUSING result=record.count END work'
        # Unqualified count is deliberately blocked even in this expression.
        with self.assertRaises(TranslationError) as caught:
            execute(routines, prefix='TYPE item_t=STRUCTURE count: INTEGER ENDSTRUCTURE')
        self.assertEqual(caught.exception.code, 'E_USING_CONST_SHADOW')

    def test_local_constant_used_outside_using_with_explicit_field(self):
        routines = 'ROUTINE work CONST count=7 VAR record: item_t BEGIN record.count=count+1 result=record.count END work'
        self.assertEqual(execute(routines, prefix='TYPE item_t=STRUCTURE count: INTEGER ENDSTRUCTURE')['RESULT'], 8)

    def test_conversion_input_can_use_local_constant(self):
        routines = "ROUTINE work CONST digits='12' BEGIN CNV_STR_INT(digits,result) END work"
        self.assertEqual(execute(routines)['RESULT'], 12)

    def test_error_keeps_prior_write_and_unwinds_frame(self):
        program, _ = compile_program(routines='ROUTINE work CONST upper=MAXINT BEGIN x=7 y=upper END work')
        with self.assertRaises(KarelRuntimeError):
            program.run()
        self.assertEqual(program._state.snapshot()['X'], 7)
        self.assertEqual(program._state.local_frames, [])

    def test_maxint_function_result_still_guarded(self):
        routines = 'ROUTINE work: INTEGER CONST upper=MAXINT BEGIN RETURN upper END work'
        program, _ = compile_program('result=work()', routines)
        with self.assertRaises(KarelRuntimeError): program.run()
        self.assertEqual(program._state.local_frames, [])

    def test_report_keeps_declaring_scope_values_and_positions(self):
        _, generated = compile_program(routines='ROUTINE work\nCONST step=7\n yes=ON\nBEGIN result=step END work')
        rows = generated.report['local_constants']['WORK']
        self.assertEqual([(r['name'], r['value']) for r in rows], [('STEP', 7), ('YES', True)])
        self.assertEqual((rows[0]['line'], rows[0]['column']), (8, 7))
        self.assertIn('routine-local CONST', generated.report['features'])
        self.assertFalse(generated.report['local_constant_policy']['controller_validated'])

    def test_continued_constant_and_local_dimension(self):
        routines = 'ROUTINE work\nCONST count=1 + &\n 2\nVAR a: ARRAY[count] OF INTEGER\nBEGIN a[3]=7 result=a[3] END work'
        self.assertEqual(execute(routines)['RESULT'], 7)

    def test_pure_function_with_local_constants_in_expression(self):
        routines = 'ROUTINE work: INTEGER CONST step=7 BEGIN RETURN step END work'
        self.assertEqual(execute(routines, 'result=1+work()')['RESULT'], 8)


class LocalConstantRejectionTests(unittest.TestCase):
    def reject(self, routine, code, **kwargs):
        with self.assertRaises(TranslationError) as caught:
            compile_program(routines=routine, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_constant_cannot_escape_to_main(self):
        self.reject('ROUTINE work CONST step=7 BEGIN END work', 'E_SYMBOL', body='result=step')

    def test_callee_cannot_see_caller_constant(self):
        self.reject('ROUTINE child BEGIN result=step END child\nROUTINE work CONST step=7 BEGIN child END work', 'E_SYMBOL')

    def test_sibling_cannot_see_other_constant(self):
        self.reject('ROUTINE first CONST step=7 BEGIN END first\nROUTINE work BEGIN result=step END work', 'E_SYMBOL')

    def test_assignment_to_local_constant(self):
        self.reject('ROUTINE work CONST step=7 BEGIN step=9 END work', 'E_CONST_ASSIGN')

    def test_skipped_assignment_still_rejected(self):
        self.reject('ROUTINE work CONST step=7 BEGIN GOTO done step=9 done:: END work', 'E_CONST_ASSIGN')

    def test_constant_cannot_be_for_counter(self):
        self.reject('ROUTINE work CONST step=7 BEGIN FOR step=1 TO 2 DO ENDFOR END work', 'E_FOR_COUNTER')

    def test_constant_uninit_query(self):
        self.reject('ROUTINE work CONST step=7 BEGIN flag=UNINIT(step) END work', 'E_ARGUMENTS')

    def test_conversion_output_constant(self):
        self.reject("ROUTINE work CONST step=7 BEGIN CNV_STR_INT('12',step) END work", 'E_OUTPUT_ARGUMENT')

    def test_duplicate_constant(self):
        self.reject('ROUTINE work CONST step=7 step=9 BEGIN END work', 'E_DUPLICATE')

    def test_duplicate_across_const_sections(self):
        self.reject('ROUTINE work CONST step=7 VAR unused: INTEGER CONST step=9 BEGIN END work', 'E_DUPLICATE')

    def test_parameter_constant_collision(self):
        self.reject('ROUTINE work(step: INTEGER) CONST step=7 BEGIN END work', 'E_DUPLICATE', body='work(1)')

    def test_variable_then_constant_collision(self):
        self.reject('ROUTINE work VAR step: INTEGER CONST step=7 BEGIN END work', 'E_DUPLICATE')

    def test_constant_then_variable_collision(self):
        self.reject('ROUTINE work CONST step=7 VAR step: INTEGER BEGIN END work', 'E_DUPLICATE')

    def test_global_constant_shadowing_blocked(self):
        self.reject('ROUTINE work CONST step=7 BEGIN END work', 'E_DUPLICATE', prefix='CONST step=1')

    def test_global_variable_shadowing_blocked(self):
        self.reject('ROUTINE work CONST x=7 BEGIN END work', 'E_LOCAL_CONST_SHADOW')

    def test_global_routine_shadowing_blocked(self):
        self.reject('ROUTINE work CONST later=7 BEGIN END work\nROUTINE later BEGIN END later', 'E_LOCAL_CONST_SHADOW')

    def test_global_type_shadowing_blocked(self):
        self.reject('ROUTINE work CONST row_t=7 BEGIN END work', 'E_DUPLICATE', prefix='TYPE row_t=ARRAY[2] OF INTEGER')

    def test_program_name_shadowing_blocked(self):
        self.reject('ROUTINE work CONST t=7 BEGIN END work', 'E_LOCAL_CONST_SHADOW')

    def test_predefined_name_collision(self):
        self.reject('ROUTINE work CONST MININT=7 BEGIN END work', 'E_PREDEFINED_NAME')

    def test_controller_name_collision(self):
        self.reject('ROUTINE work CONST DIN=7 BEGIN END work', 'E_DUPLICATE')

    def test_forward_constant_dependency(self):
        self.reject('ROUTINE work CONST a=b b=7 BEGIN END work', 'E_CONSTANT')

    def test_self_constant_dependency(self):
        self.reject('ROUTINE work CONST a=a BEGIN END work', 'E_CONSTANT')

    def test_parameter_not_constant_expression(self):
        self.reject('ROUTINE work(p: INTEGER) CONST a=p BEGIN END work', 'E_CONSTANT', body='work(1)')

    def test_global_variable_not_constant_expression(self):
        self.reject('ROUTINE work CONST a=x BEGIN END work', 'E_CONSTANT')

    def test_local_variable_not_constant_expression(self):
        self.reject('ROUTINE work VAR v: INTEGER CONST a=v BEGIN END work', 'E_CONSTANT')

    def test_local_dimension_cannot_use_later_constant(self):
        self.reject('ROUTINE work VAR a: ARRAY[count] OF INTEGER CONST count=3 BEGIN END work', 'E_CONSTANT')

    def test_routine_local_type_still_prohibited(self):
        self.reject('ROUTINE work CONST size=2 TYPE row_t=ARRAY[size] OF INTEGER BEGIN END work', 'E_ROUTINE_LOCALS')

    def test_builtin_calls_in_constants_remain_blocked(self):
        self.reject('ROUTINE work CONST root=SQRT(4.0) BEGIN END work', 'E_CONSTANT')

    def test_user_calls_in_constants_remain_blocked(self):
        self.reject('ROUTINE value: INTEGER BEGIN RETURN 7 END value\nROUTINE work CONST a=value() BEGIN END work', 'E_CONSTANT')

    def test_integer_overflow_constant(self):
        self.reject('ROUTINE work CONST a=MAXINT+1 BEGIN END work', 'E_CONSTANT')

    def test_pythonic_real_constant(self):
        state = execute('ROUTINE work CONST a=0.1 BEGIN real_value=a END work')
        self.assertEqual(state['REAL_VALUE'], .1)

    def test_pythonic_negative_mod_constant(self):
        state = execute('ROUTINE work CONST a=(-7) MOD 3 BEGIN result=a END work')
        self.assertEqual(state['RESULT'], (-7) % 3)

    def test_minimum_literal_rule_still_applies(self):
        self.reject('ROUTINE work CONST a=-2147483648 BEGIN END work', 'E_MININT_LITERAL')

    def test_boolean_dimension_rejected(self):
        self.reject('ROUTINE work CONST count=ON VAR a: ARRAY[count] OF INTEGER BEGIN END work', 'E_SIZE')

    def test_capacity_guard_uses_local_constant(self):
        self.reject('ROUTINE work CONST count=200 VAR a: ARRAY[count,count] OF INTEGER BEGIN END work', 'E_ARRAY_CAPACITY')

    def test_local_constant_label_collision(self):
        self.reject('ROUTINE work CONST step=7 BEGIN step:: END work', 'E_LABEL_CONFLICT')

    def test_using_field_constant_collision(self):
        self.reject('ROUTINE work CONST count=7 VAR record: item_t BEGIN USING record DO result=count ENDUSING END work', 'E_USING_CONST_SHADOW', prefix='TYPE item_t=STRUCTURE count: INTEGER ENDSTRUCTURE')

    def test_string_constant_value_argument_remains_blocked(self):
        self.reject("ROUTINE label(p: STRING) BEGIN p='changed' END label\nROUTINE work CONST name='abc' BEGIN label(name) END work", 'E_STRING_VALUE')

    def test_unreachable_invalid_constant_still_rejected(self):
        self.reject('ROUTINE work CONST a=1 DIV 0 BEGIN END work', 'E_CONSTANT', body='x=7')

    def test_continued_constant_error_physical_position(self):
        error = self.reject('ROUTINE work\nCONST first=1\n second=first + &\n missing\nBEGIN END work', 'E_CONSTANT')
        self.assertEqual((error.token.line, error.token.column), (10, 2))


if __name__ == '__main__': unittest.main()
