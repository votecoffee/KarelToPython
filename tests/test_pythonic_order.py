"""Chosen Pythonic order, live references, value captures and failure boundaries."""
import ast
import json
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError


DECLARATIONS = '''n,x,y,i,total: INTEGER flag: BOOLEAN trace,text: STRING[254]
a: ARRAY[3] OF INTEGER grid: ARRAY[2,2] OF INTEGER
v,w: VECTOR items: ARRAY[2] OF VECTOR'''
MARK = '''ROUTINE mark(p: INTEGER): INTEGER
BEGIN trace=trace+CHR(64+p) RETURN p END mark'''
TRUTH = '''ROUTINE truth(p: INTEGER; value: BOOLEAN): BOOLEAN
BEGIN trace=trace+CHR(64+p) RETURN value END truth'''
VECTOR = 'v.x=1 v.y=2 v.z=3'


def compile_program(body, routines='', *, declarations=DECLARATIONS, types='', **context):
    source = f'PROGRAM T\n{types}\nVAR {declarations}\n{MARK}\n{routines}\nBEGIN\ntrace=\'\' n=0\n{body}\nEND T'
    result = translate(source, filename='pythonic_order.kl')
    ast.parse(result.python_source, feature_version=(3, 11))
    json.dumps(result.report)
    namespace = {'__name__': 'pythonic_order_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](**context), result


def execute(body, routines='', **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


def seed_pose(program):
    pose=program._state.raw('POSE')
    for name,value in zip(('X','Y','Z','W','P','R'),range(1,7)): pose.values[name]=float(value)
    config=pose.values['CONFIG_DATA']
    for name,spec in rt.record_fields(('CONFIG',)): config.values[name]=False if spec[0]=='BOOLEAN' else 0


class OperandOrderTests(unittest.TestCase):
    def test_arithmetic_operands_once_left_to_right(self):
        state = execute('x=mark(1)+mark(2)*mark(3)')
        self.assertEqual((state['X'], state['TRACE']), (7, 'ABC'))

    def test_scalar_left_captured_before_mutating_right(self):
        routine = 'ROUTINE change: INTEGER BEGIN n=9 RETURN 2 END change'
        state = execute('n=1 x=n+change()', routine)
        self.assertEqual((state['X'], state['N']), (3, 9))

    def test_reference_mutator_in_operator(self):
        routine = 'ROUTINE change(p: INTEGER): INTEGER BEGIN p=p+1 RETURN p END change'
        state = execute('n=1 x=change(n)+change(n)', routine)
        self.assertEqual((state['X'], state['N']), (5, 3))

    def test_comparison_left_to_right(self):
        state = execute('flag=mark(1)<mark(2)')
        self.assertEqual((state['FLAG'], state['TRACE']), (True, 'AB'))

    def test_string_values_before_later_mutation(self):
        routine = "ROUTINE change: STRING BEGIN text='after' RETURN '!' END change"
        state = execute("text='before' text=text+change()", routine)
        self.assertEqual(state['TEXT'], 'before!')

    def test_writable_string_temporary_in_operator(self):
        routine = "ROUTINE bracket(p: STRING): STRING BEGIN p='['+p+']' RETURN p END bracket"
        self.assertEqual(execute("text=bracket('seed')+'!'", routine)['TEXT'], '[seed]!')

    def test_bare_function_calls_keep_order(self):
        routine = 'ROUTINE next_value: INTEGER BEGIN n=n+1 RETURN n END next_value'
        state = execute('x=next_value*10+next_value', routine)
        self.assertEqual((state['X'], state['N']), (12, 2))

    def test_vector_left_detached_before_right_mutates_it(self):
        routine = 'ROUTINE change: VECTOR BEGIN v.x=9 RETURN v END change'
        state = execute(VECTOR+' w=v+change()', routine)
        self.assertEqual(state['W'], dict(X=10., Y=4., Z=6.))

    def test_vector_scaling_captures_vector_first(self):
        routine = 'ROUTINE scale: REAL BEGIN v.x=9 RETURN 2 END scale'
        state = execute(VECTOR+' w=v*scale()', routine)
        self.assertEqual(state['W'], dict(X=2., Y=4., Z=6.))

    def test_vector_right_reads_after_left_effect(self):
        routine = 'ROUTINE scale: REAL BEGIN v.x=9 RETURN 2 END scale'
        state = execute(VECTOR+' w=scale()*v', routine)
        self.assertEqual(state['W'], dict(X=18., Y=4., Z=6.))

    def test_dot_product_uses_captured_left(self):
        routine = 'ROUTINE change: VECTOR BEGIN v.x=9 RETURN v END change'
        self.assertEqual(execute(VECTOR+' x=TRUNC(v@change())', routine)['X'], 22)

    def test_vector_equality_uses_captured_left(self):
        routine = 'ROUTINE change: VECTOR BEGIN v.x=9 RETURN v END change'
        self.assertFalse(execute(VECTOR+' flag=v=change()', routine)['FLAG'])

    def test_uninitialized_vector_left_prevents_right_effect(self):
        routine = 'ROUTINE change: VECTOR BEGIN n=9 RETURN v END change'
        program, _ = compile_program('w=v+change()', routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual(program.snapshot()['N'], 0)

    def test_delay_and_output_inside_arithmetic(self):
        routine = "ROUTINE effect: INTEGER BEGIN DELAY 1 WRITE('hit') RETURN 2 END effect"
        delays=[]
        program, _ = compile_program('x=effect()+effect()', routine, sleep=delays.append)
        self.assertEqual(program.run()['X'], 4)
        self.assertEqual(delays, [0.001, 0.001])
        self.assertEqual([r['text'] for r in program.write_requests], ['hit', 'hit'])

    def test_transitive_effects_still_reported(self):
        routine = "ROUTINE inner: INTEGER BEGIN WRITE('hit') RETURN 1 END inner\nROUTINE outer: INTEGER BEGIN RETURN inner()+1 END outer"
        program, result = compile_program('x=outer()+1', routine)
        self.assertEqual(program.run()['X'], 3)
        self.assertTrue(result.report['routine_effects']['OUTER']['potential_output_requests'])


class BooleanOrderTests(unittest.TestCase):
    def test_false_and_skips_right(self):
        state = execute('flag=truth(1,FALSE) AND truth(2,TRUE)', TRUTH)
        self.assertEqual((state['FLAG'], state['TRACE']), (False, 'A'))

    def test_true_or_skips_right(self):
        state = execute('flag=truth(1,TRUE) OR truth(2,FALSE)', TRUTH)
        self.assertEqual((state['FLAG'], state['TRACE']), (True, 'A'))

    def test_true_and_evaluates_right(self):
        state = execute('flag=truth(1,TRUE) AND truth(2,FALSE)', TRUTH)
        self.assertEqual((state['FLAG'], state['TRACE']), (False, 'AB'))

    def test_false_or_evaluates_right(self):
        state = execute('flag=truth(1,FALSE) OR truth(2,TRUE)', TRUTH)
        self.assertEqual((state['FLAG'], state['TRACE']), (True, 'AB'))

    def test_integer_and_evaluates_both(self):
        state = execute('x=(mark(1)-1) AND mark(2)')
        self.assertEqual((state['X'], state['TRACE']), (0, 'AB'))

    def test_integer_or_evaluates_both(self):
        state = execute('x=mark(1) OR mark(2)')
        self.assertEqual((state['X'], state['TRACE']), (3, 'AB'))

    def test_nested_short_circuit_respects_precedence(self):
        state = execute('flag=truth(1,TRUE) OR truth(2,TRUE) AND truth(3,FALSE)', TRUTH)
        self.assertEqual((state['FLAG'], state['TRACE']), (True, 'A'))

    def test_skipped_division_error(self):
        self.assertFalse(execute('flag=FALSE AND (1 DIV 0=0)')['FLAG'])

    def test_skipped_uninitialized_read(self):
        self.assertTrue(execute('flag=TRUE OR flag')['FLAG'])

    def test_skipped_abort(self):
        routine = 'ROUTINE stop_now: BOOLEAN BEGIN ABORT RETURN TRUE END stop_now'
        program, _ = compile_program('flag=FALSE AND stop_now() x=7', routine)
        self.assertEqual(program.run()['X'], 7)
        self.assertIsNone(program.abort_info)

    def test_skipped_branch_is_still_type_checked(self):
        with self.assertRaises(TranslationError): compile_program('flag=TRUE OR 1')

    def test_labelled_and_structured_conditions_agree(self):
        states=[]
        for marker in ('', 'unused:: '):
            states.append(execute(marker+'IF truth(1,FALSE) AND truth(2,TRUE) THEN x=1 ELSE x=2 ENDIF', TRUTH))
        self.assertEqual(states[0], states[1])
        self.assertEqual((states[0]['X'], states[0]['TRACE']), (2, 'A'))


class ArgumentOrderTests(unittest.TestCase):
    def test_multiple_routine_actuals_evaluated_in_source_order(self):
        routine = 'ROUTINE use(p,q,r: INTEGER) BEGIN x=p*100+q*10+r END use'
        state = execute('use(mark(1),mark(2),mark(3))', routine)
        self.assertEqual((state['X'], state['TRACE']), (123, 'ABC'))

    def test_reference_first_remains_live_after_later_argument(self):
        routine = 'ROUTINE change: INTEGER BEGIN n=9 RETURN 2 END change\nROUTINE use(p,q: INTEGER) BEGIN x=p y=q END use'
        state = execute('n=1 use(n,change())', routine)
        self.assertEqual((state['X'], state['Y']), (9, 2))

    def test_grouped_first_captures_before_later_argument(self):
        routine = 'ROUTINE change: INTEGER BEGIN n=9 RETURN 2 END change\nROUTINE use(p,q: INTEGER) BEGIN x=p y=q END use'
        state = execute('n=1 use((n),change())', routine)
        self.assertEqual((state['X'], state['Y']), (1, 2))

    def test_index_reference_captures_selected_cell(self):
        routine = 'ROUTINE change: INTEGER BEGIN i=2 a[1]=9 RETURN 2 END change\nROUTINE use(p,q: INTEGER) BEGIN x=p p=7 END use'
        state = execute('i=1 a[1]=1 a[2]=2 use(a[i],change())', routine)
        self.assertEqual((state['X'], state['A'][:2]), (9, [7, 2]))

    def test_string_value_arguments_are_independent(self):
        routine = "ROUTINE label(p: INTEGER): STRING BEGIN trace=trace+CHR(64+p) RETURN CHR(64+p) END label\nROUTINE use(p,q: STRING) BEGIN p=p+'!' text=p+q END use"
        state = execute('use(label(1),label(2))', routine)
        self.assertEqual((state['TEXT'], state['TRACE']), ('A!B', 'AB'))

    def test_builtin_substring_all_actuals_in_order(self):
        routine = "ROUTINE label: STRING BEGIN trace=trace+'S' RETURN 'abc' END label"
        state = execute('text=SUB_STR(label(),mark(1),mark(2))', routine)
        self.assertEqual((state['TEXT'], state['TRACE']), ('ab', 'SAB'))

    def test_builtin_index_function_result(self):
        routine = "ROUTINE label: STRING BEGIN RETURN 'abc' END label"
        self.assertEqual(execute("x=INDEX(label(),'b')", routine)['X'], 2)

    def test_builtin_atan2_actuals_once_in_order(self):
        state = execute('x=ROUND(ATAN2(mark(1),mark(2)))')
        self.assertEqual((state['X'], state['TRACE']), (63, 'AB'))

    def test_multidimensional_read_indexes_in_order(self):
        state = execute('grid[1,2]=7 x=grid[mark(1),mark(2)]')
        self.assertEqual((state['X'], state['TRACE']), (7, 'AB'))

    def test_uninit_indexes_in_order(self):
        state = execute('flag=UNINIT(grid[mark(1),mark(2)])')
        self.assertEqual((state['FLAG'], state['TRACE']), (True, 'AB'))

    def test_later_subscript_runs_before_bounds_check(self):
        program, _ = compile_program('x=grid[0,mark(1)]')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['TRACE'], 'A')

    def test_first_actual_failure_skips_later_actuals_and_callee(self):
        routine = 'ROUTINE use(p,q: INTEGER) BEGIN n=9 END use'
        # Bare uninitialized x is a legal reference; force a value read here.
        program, _ = compile_program('use((x),mark(1))', routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual((program.snapshot()['TRACE'], program.snapshot()['N']), ('', 0))
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_aggregate_value_argument_captured_before_next_actual(self):
        routine='ROUTINE change: INTEGER BEGIN v.x=9 RETURN 2 END change\nROUTINE use(p: VECTOR; q: INTEGER) BEGIN w=p END use'
        state=execute(VECTOR+' use((v),change())', routine)
        self.assertEqual((state['W']['X'], state['V']['X']), (1., 9.))

    def test_aggregate_reference_stays_live_through_next_actual(self):
        routine='ROUTINE change: INTEGER BEGIN v.x=9 RETURN 2 END change\nROUTINE use(p: VECTOR; q: INTEGER) BEGIN w=p END use'
        state=execute(VECTOR+' use(v,change())', routine)
        self.assertEqual((state['W']['X'], state['V']['X']), (9., 9.))

    def test_named_subarray_indexes_can_contain_functions(self):
        state=execute('plane[1,2]=7 x=plane[mark(1),mark(2)]',
                      types='TYPE row_t=ARRAY[2] OF INTEGER', declarations=DECLARATIONS+' plane: ARRAY[2] OF row_t')
        self.assertEqual((state['X'], state['TRACE']), (7, 'AB'))

    def test_bare_uninitialized_reference_is_legal_output(self):
        routine = 'ROUTINE use(p,q: INTEGER) BEGIN p=q END use'
        state = execute('use(x,mark(1))', routine)
        self.assertEqual((state['X'], state['TRACE']), (1, 'A'))


class AssignmentOrderTests(unittest.TestCase):
    def test_rhs_before_target_index(self):
        state = execute('a[mark(1)]=mark(2)')
        self.assertEqual((state['A'][0], state['TRACE']), (2, 'BA'))

    def test_rhs_before_multiple_target_indexes(self):
        state = execute('grid[mark(1),mark(2)]=mark(3)')
        self.assertEqual((state['GRID'][0][1], state['TRACE']), (3, 'CAB'))

    def test_rhs_changes_target_index(self):
        routine = 'ROUTINE change: INTEGER BEGIN i=2 RETURN 7 END change'
        state = execute('i=1 a[i]=change()', routine)
        self.assertEqual(state['A'], [{'uninitialized': True}, 7, {'uninitialized': True}])

    def test_aggregate_rhs_captured_before_target_changes_source(self):
        routine = 'ROUTINE pick: INTEGER BEGIN v.x=9 RETURN 1 END pick'
        state = execute(VECTOR+' items[pick()]=v', routine)
        self.assertEqual(state['ITEMS'][0], dict(X=1., Y=2., Z=3.))
        self.assertEqual(state['V']['X'], 9.)

    def test_array_rhs_captured_before_target_changes_source(self):
        types='TYPE row_t=ARRAY[2] OF INTEGER'
        routine='ROUTINE pick: INTEGER BEGIN row[1]=9 RETURN 1 END pick'
        state=execute('row[1]=1 row[2]=2 rows[pick()]=row', routine,
                      types=types, declarations='trace: STRING[8] n: INTEGER row: row_t rows: ARRAY[2] OF row_t')
        self.assertEqual((state['ROWS'][0], state['ROW']), ([1, 2], [9, 2]))

    def test_invalid_target_retains_rhs_effect(self):
        program, _ = compile_program('a[0]=mark(1)')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['TRACE'], 'A')

    def test_target_index_changes_rhs_source_after_capture(self):
        routine='ROUTINE pick: INTEGER BEGIN x=9 RETURN 1 END pick'
        state=execute('x=1 a[pick()]=x', routine)
        self.assertEqual((state['A'][0], state['X']), (1, 9))

    def test_target_type_failure_retains_target_effect_but_no_assignment(self):
        routine='ROUTINE pick: INTEGER BEGIN n=9 RETURN 1 END pick\nROUTINE copy(src: ARRAY OF INTEGER) BEGIN boxes[pick()].row=src END copy'
        program, _=compile_program('source[1]=1 copy(source)', routine,
            types='TYPE box_t=STRUCTURE row: ARRAY[2] OF INTEGER ENDSTRUCTURE',
            declarations=DECLARATIONS+' source: ARRAY[1] OF INTEGER boxes: ARRAY[1] OF box_t')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'identical type and size'): program.run()
        self.assertEqual(program.snapshot()['N'], 9)
        self.assertEqual(program.snapshot()['BOXES'][0]['ROW'], [{'uninitialized': True}]*2)
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_rhs_failure_skips_target_effect(self):
        program, _ = compile_program('a[mark(1)]=1 DIV 0')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'zero'): program.run()
        self.assertEqual(program.snapshot()['TRACE'], '')

    def test_uninitialized_rhs_skips_target_effect(self):
        program, _ = compile_program('a[mark(1)]=x')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual(program.snapshot()['TRACE'], '')

    def test_incomplete_aggregate_rhs_skips_target_effect(self):
        program, _ = compile_program('items[mark(1)]=v')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual(program.snapshot()['TRACE'], '')

    def test_direct_array_function_result_before_target_call(self):
        routine='ROUTINE make: ARRAY OF INTEGER VAR local_row: ARRAY[2] OF INTEGER BEGIN trace=trace+\'R\' local_row[1]=7 local_row[2]=8 RETURN local_row END make'
        state=execute('boxes[mark(1)].row=make()', routine, types='TYPE box_t=STRUCTURE row: ARRAY[2] OF INTEGER ENDSTRUCTURE',
                      declarations='trace: STRING[8] n: INTEGER boxes: ARRAY[2] OF box_t')
        self.assertEqual((state['BOXES'][0]['ROW'], state['TRACE']), ([7, 8], 'RA'))

    def test_labelled_assignment_uses_same_order(self):
        state = execute('unused:: a[mark(1)]=mark(2)')
        self.assertEqual((state['A'][0], state['TRACE']), (2, 'BA'))


class ConversionAndLoopOrderTests(unittest.TestCase):
    def test_numeric_conversion_inputs_then_output_index(self):
        state = execute('CNV_INT_STR(mark(1),mark(2),10,words[mark(3)])',
                        declarations=DECLARATIONS+' words: ARRAY[3] OF STRING[8]')
        self.assertEqual((state['WORDS'][2], state['TRACE']), (' 1', 'ABC'))

    def test_parse_function_result_then_output_index(self):
        routine="ROUTINE number: STRING BEGIN trace=trace+'S' RETURN '42' END number"
        state=execute('CNV_STR_INT(number(),a[mark(1)])', routine)
        self.assertEqual((state['A'][0], state['TRACE']), (42, 'SA'))

    def test_invalid_conversion_input_still_evaluates_output_reference(self):
        state=execute("a[1]=7 CNV_STR_INT('bad',a[mark(1)])")
        self.assertEqual((state['A'][0], state['TRACE']), ({'uninitialized': True}, 'A'))

    def test_conversion_validation_follows_all_argument_evaluations(self):
        program, _=compile_program('CNV_INT_STR(mark(1),0,10,words[mark(2)])',
                                  declarations=DECLARATIONS+' words: ARRAY[2] OF STRING[8]')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['TRACE'], 'AB')
        self.assertEqual(program.snapshot()['WORDS'], [{'uninitialized': True}]*2)

    def test_joint_conversion_indexes_in_order(self):
        state=execute('axes[1]=1 axes[2]=2 CNV_REL_JPOS(axes,joints[mark(1)],statuses[mark(2)])',
                      declarations=DECLARATIONS+' axes: ARRAY[2] OF REAL joints: ARRAY[2] OF JOINTPOS2 statuses: ARRAY[2] OF INTEGER', joint_axes=2)
        self.assertEqual((state['JOINTS'][0], state['STATUSES'][1], state['TRACE']), ({'axes': [1., 2.]}, 0, 'AB'))

    def test_joint_source_stays_live_during_later_reference_evaluation(self):
        routine='ROUTINE pick: INTEGER BEGIN axes[1]=9 RETURN 1 END pick'
        state=execute('axes[1]=1 axes[2]=2 CNV_REL_JPOS(axes,joints[pick()],x)', routine,
                      declarations=DECLARATIONS+' axes: ARRAY[2] OF REAL joints: ARRAY[1] OF JOINTPOS2', joint_axes=2)
        self.assertEqual(state['JOINTS'][0], {'axes': [9., 2.]})

    def test_joint_to_real_conversion_indexes_in_order(self):
        state=execute('axes[1]=1 axes[2]=2 CNV_REL_JPOS(axes,j,x) CNV_JPOS_REL(j,rows[mark(1)],statuses[mark(2)])',
                      types='TYPE row_t=ARRAY[2] OF REAL',
                      declarations=DECLARATIONS+' axes: ARRAY[2] OF REAL j: JOINTPOS2 rows: ARRAY[2] OF row_t statuses: ARRAY[2] OF INTEGER', joint_axes=2)
        self.assertEqual((state['ROWS'][0], state['STATUSES'][1], state['TRACE']), ([1., 2.], 0, 'AB'))

    def test_missing_joint_context_retains_index_effects_without_outputs(self):
        program, _=compile_program('axes[1]=1 axes[2]=2 CNV_REL_JPOS(axes,joints[mark(1)],statuses[mark(2)])',
            declarations=DECLARATIONS+' axes: ARRAY[2] OF REAL joints: ARRAY[2] OF JOINTPOS2 statuses: ARRAY[2] OF INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'explicit'): program.run()
        self.assertEqual((program.snapshot()['TRACE'], program.snapshot()['STATUSES'][1]), ('AB', {'uninitialized': True}))

    def test_unpos_output_indexes_evaluated_before_writes(self):
        declarations=DECLARATIONS+' pose: XYZWPR components: ARRAY[6] OF REAL cfg: CONFIG'
        program, _=compile_program('UNPOS(pose,components[mark(1)],components[mark(2)],components[3],components[4],components[5],components[6],cfg)', declarations=declarations)
        seed_pose(program)
        state=program.run()
        self.assertEqual((state['COMPONENTS'], state['TRACE']), ([1.,2.,3.,4.,5.,6.], 'AB'))

    def test_unpos_dynamic_overlap_keeps_outputs_and_index_effects(self):
        declarations=DECLARATIONS+' pose: XYZWPR components: ARRAY[6] OF REAL cfg: CONFIG'
        program, _=compile_program('components[1]=42 UNPOS(pose,components[mark(1)],components[mark(1)],components[3],components[4],components[5],components[6],cfg)', declarations=declarations)
        seed_pose(program)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'overlapping'): program.run()
        self.assertEqual((program.snapshot()['COMPONENTS'][0], program.snapshot()['TRACE']), (42., 'AA'))

    def test_for_bounds_evaluated_once(self):
        state=execute('total=0 FOR i=mark(1) TO mark(3) DO total=total+i ENDFOR')
        self.assertEqual((state['TOTAL'], state['TRACE'], state['I']), (6, 'AC', {'uninitialized': True}))

    def test_for_final_reads_initialized_counter(self):
        routine='ROUTINE last: INTEGER BEGIN RETURN i+2 END last'
        self.assertEqual(execute('total=0 FOR i=1 TO last() DO total=total+i ENDFOR', routine)['TOTAL'], 6)

    def test_for_final_effect_on_counter_is_observable(self):
        routine='ROUTINE last: INTEGER BEGIN i=2 RETURN 3 END last'
        self.assertEqual(execute('total=0 FOR i=1 TO last() DO total=total+i ENDFOR', routine)['TOTAL'], 5)

    def test_for_downto_bounds(self):
        state=execute('total=0 FOR i=mark(3) DOWNTO mark(1) DO total=total+i ENDFOR')
        self.assertEqual((state['TOTAL'], state['TRACE']), (6, 'CA'))

    def test_empty_for_still_evaluates_both_bounds(self):
        state=execute('total=0 FOR i=mark(3) TO mark(1) DO total=9 ENDFOR')
        self.assertEqual((state['TOTAL'], state['TRACE'], state['I']), (0, 'CA', {'uninitialized': True}))

    def test_for_final_failure_clears_initialized_counter(self):
        routine='ROUTINE last: INTEGER BEGIN RETURN 1 DIV 0 END last'
        program, _=compile_program('FOR i=2 TO last() DO ENDFOR', routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['I'], {'uninitialized': True})
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_for_initial_failure_skips_final_call(self):
        program, _=compile_program('i=9 FOR i=1 DIV 0 TO mark(1) DO ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['I'], program.snapshot()['TRACE']), (9, ''))

    def test_fresh_local_for_can_call_composed_functions(self):
        routine='ROUTINE work VAR k: INTEGER BEGIN FOR k=1 TO 2 DO x=mark(1)+mark(2) ENDFOR END work'
        state=execute('work', routine)
        self.assertEqual((state['X'], state['TRACE']), (3, 'ABAB'))

    def test_global_for_body_calls_keep_chosen_order(self):
        state=execute('FOR i=1 TO 2 DO x=mark(1) ENDFOR')
        self.assertEqual((state['X'],state['TRACE'],state['I']), (1,'AA',{'uninitialized': True}))


class FailureAndReportTests(unittest.TestCase):
    def test_abort_skips_later_operand_and_target(self):
        routine="ROUTINE stop_now: INTEGER BEGIN trace=trace+'S' ABORT RETURN 7 END stop_now"
        program, _=compile_program('a[mark(3)]=mark(1)+stop_now()+mark(2)', routine)
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual(program.snapshot()['TRACE'], 'AS')
        self.assertEqual(program.abort_info['kind'], 'ABORT')
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_argument_abort_does_not_enter_outer_callee(self):
        routine='ROUTINE stop_now: INTEGER BEGIN ABORT RETURN 1 END stop_now\nROUTINE use(p,q: INTEGER) BEGIN n=9 END use'
        program, _=compile_program('use(mark(1),stop_now())', routine)
        with self.assertRaises(rt.KarelAbort): program.run()
        state=program.snapshot()
        self.assertEqual((state['TRACE'], state['N']), ('A', 0))
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_nested_output_precedes_outer_write(self):
        routine="ROUTINE emit: STRING BEGIN WRITE('inner') RETURN 'value' END emit"
        program, _=compile_program("WRITE('outer=',emit()+'!',CR)", routine)
        program.run()
        self.assertEqual([r['text'] for r in program.write_requests], ['inner', 'outer=value!\n'])

    def test_failed_output_callback_skips_later_operand(self):
        routine="ROUTINE emit: INTEGER BEGIN WRITE('inner') RETURN 1 END emit"
        def fail(text): raise ValueError('callback failed')
        program, _=compile_program('x=emit()+mark(2)', routine, write=fail)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['TRACE'], '')
        self.assertEqual((program._state.local_frames, program._state.call_depth), ([], 0))

    def test_report_states_chosen_order(self):
        _, result=compile_program('x=mark(1)+mark(2)')
        policy=result.report['evaluation_policy']
        self.assertIn('RHS first', policy['assignment'])
        self.assertIn('short circuit', policy['boolean'])
        self.assertIn('live reference', policy['arguments'])
        self.assertFalse(policy['controller_validated'])
        self.assertFalse(any('ordering remains blocked' in str(value) for value in result.report.values()))


if __name__ == '__main__': unittest.main()
