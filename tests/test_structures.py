"""Named type identity, field paths, aggregate copies and reference lifetime."""
import unittest

from karel2py import translate
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


TYPES = '''
CONST size = 2
TYPE
  inner = STRUCTURE
    count: INTEGER
    label: STRING[3]
  ENDSTRUCTURE
  outer = STRUCTURE
    child: inner
    enabled: BOOLEAN
    measurement: REAL
    slots: ARRAY[size] OF INTEGER
  ENDSTRUCTURE
  other = STRUCTURE
    count: INTEGER
    label: STRING[3]
  ENDSTRUCTURE
'''
DECLARATIONS = '''
src,dst: outer
item: inner
alien: other
result,slot_index: INTEGER
flag: BOOLEAN
real_result: REAL
'''
INITIALIZE = '''
src.child.count = 5
src.child.label = 'abcdef'
src.enabled = TRUE
src.measurement = 2.5
src.slots[1] = 10
src.slots[2] = 20
'''


def compile_program(body, routines='', types=TYPES, declarations=DECLARATIONS, *, _translator=translate):
    result = _translator(f'PROGRAM T\n{types}\nVAR\n{declarations}\n{routines}\nBEGIN\n{body}\nEND T', filename='structures.kl')
    namespace = {'__name__': 'structure_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, routines='', **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


class FieldTests(unittest.TestCase):
    def test_initial_snapshot_has_independent_uninitialized_fields(self):
        state = execute('')
        self.assertEqual(state['SRC'], {'CHILD': {'COUNT': {'uninitialized': True}, 'LABEL': {'uninitialized': True}},
                                      'ENABLED': {'uninitialized': True}, 'MEASUREMENT': {'uninitialized': True},
                                      'SLOTS': [{'uninitialized': True}, {'uninitialized': True}]})

    def test_nested_scalar_fields_and_array_fields(self):
        state = execute(INITIALIZE + 'result = src.child.count + src.slots[2]')
        self.assertEqual(state['RESULT'], 25)
        self.assertEqual(state['SRC']['CHILD']['LABEL'], 'abc')
        self.assertEqual(state['SRC']['MEASUREMENT'], 2.5)
        self.assertTrue(state['SRC']['ENABLED'])

    def test_names_are_case_insensitive(self):
        self.assertEqual(execute('sRc.ChIlD.CoUnT = 7 ReSuLt = SrC.cHiLd.COUNT')['RESULT'], 7)

    def test_field_name_can_match_global_and_other_type_field(self):
        state = execute('src.child.count = 7 alien.count = 8 result = src.child.count + alien.count', declarations=DECLARATIONS + 'count: INTEGER')
        self.assertEqual(state['RESULT'], 15)
        self.assertEqual(state['COUNT'], {'uninitialized': True})

    def test_scalar_field_uninit(self):
        state = execute('flag = UNINIT(src.child.count) src.child.count = 7')
        self.assertTrue(state['FLAG'])
        self.assertEqual(state['SRC']['CHILD']['COUNT'], 7)

    def test_array_field_element_uninit(self):
        self.assertTrue(execute('flag = UNINIT(src.slots[1])')['FLAG'])

    def test_field_read_reports_source_line(self):
        p, _ = compile_program('result = src.child.count')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'KAREL line .*uninitialized') as caught: p.run()
        self.assertIsNotNone(caught.exception.line)

    def test_array_field_bounds_checked_before_write(self):
        p, _ = compile_program('src.slots[1] = 7 src.slots[3] = 9')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'outside 1..2'): p.run()
        self.assertEqual(p._state.snapshot()['SRC']['SLOTS'], [7, {'uninitialized': True}])

    def test_whole_array_field_assignment(self):
        state = execute('src.slots[1] = 7 dst.slots = src.slots src.slots[1] = 9')
        self.assertEqual(state['DST']['SLOTS'], [7, {'uninitialized': True}])
        self.assertEqual(state['SRC']['SLOTS'][0], 9)

    def test_integer_to_real_field_promotion(self):
        self.assertEqual(execute('src.measurement = 3')['SRC']['MEASUREMENT'], 3.0)

    def test_pythonic_real_field_allows_rounding(self):
        p, _ = compile_program('src.measurement = 1.0 / 3.0')
        self.assertEqual(p.run()['SRC']['MEASUREMENT'], 1/3)

    def test_builtins_on_fields(self):
        state = execute(INITIALIZE + 'result = STR_LEN(src.child.label) + ARRAY_LEN(src.slots)')
        self.assertEqual(state['RESULT'], 5)

    def test_string_boolean_and_real_array_fields(self):
        types = 'TYPE record_t = STRUCTURE words: ARRAY[2] OF STRING[2] flags: ARRAY[2] OF BOOLEAN measures: ARRAY[2] OF REAL ENDSTRUCTURE'
        state = execute("item.words[1] = 'abcd' item.flags[2] = TRUE item.measures[1] = 2.5", types=types, declarations='item: record_t')
        self.assertEqual(state['ITEM'], {'WORDS': ['ab', {'uninitialized': True}], 'FLAGS': [{'uninitialized': True}, True], 'MEASURES': [2.5, {'uninitialized': True}]})

    def test_three_level_nested_field_paths(self):
        types = TYPES + 'TYPE wrapper = STRUCTURE value: outer ENDSTRUCTURE'
        self.assertEqual(execute('item.value.child.count = 7', types=types, declarations='item: wrapper')['ITEM']['VALUE']['CHILD']['COUNT'], 7)

    def test_global_structure_storage_is_independent(self):
        state = execute('src.child.count = 7 src.slots[1] = 9')
        self.assertEqual(state['DST']['CHILD']['COUNT'], {'uninitialized': True})
        self.assertEqual(state['DST']['SLOTS'][0], {'uninitialized': True})


class StructureCopyTests(unittest.TestCase):
    def test_whole_copy_is_deep_and_preserves_type(self):
        state = execute(INITIALIZE + 'dst = src src.child.count = 99 src.slots[1] = 77')
        self.assertEqual(state['DST']['CHILD'], {'COUNT': 5, 'LABEL': 'abc'})
        self.assertEqual(state['DST']['SLOTS'], [10, 20])
        self.assertEqual(state['SRC']['CHILD']['COUNT'], 99)

    def test_nested_structure_assignment(self):
        state = execute('item.count = 7 item.label = \'hi\' src.child = item item.count = 9')
        self.assertEqual(state['SRC']['CHILD'], {'COUNT': 7, 'LABEL': 'hi'})

    def test_self_copy_keeps_field_references(self):
        routine = 'ROUTINE copy(p: outer; n: INTEGER) BEGIN p = p result = n n = 9 END copy'
        state = execute(INITIALIZE + 'copy(src,src.child.count)', routine)
        self.assertEqual((state['RESULT'], state['SRC']['CHILD']['COUNT']), (5, 9))

    def test_copy_preserves_scalar_field_alias(self):
        routine = 'ROUTINE copy(p,q: outer; n: INTEGER) BEGIN p = q result = n n = 99 END copy'
        state = execute(INITIALIZE + 'copy(dst,src,dst.child.count)', routine)
        self.assertEqual((state['RESULT'], state['DST']['CHILD']['COUNT']), (5, 99))
        self.assertEqual(state['SRC']['CHILD']['COUNT'], 5)

    def test_copy_preserves_nested_structure_alias(self):
        routine = 'ROUTINE copy(p,q: outer; child_ref: inner) BEGIN p = q child_ref.count = 99 END copy'
        state = execute(INITIALIZE + 'copy(dst,src,dst.child)', routine)
        self.assertEqual(state['DST']['CHILD']['COUNT'], 99)
        self.assertEqual(state['SRC']['CHILD']['COUNT'], 5)

    def test_copy_preserves_array_field_alias(self):
        routine = 'ROUTINE copy(p,q: outer; a: ARRAY OF INTEGER) BEGIN p = q result = a[1] a[1] = 99 END copy'
        state = execute(INITIALIZE + 'copy(dst,src,dst.slots)', routine)
        self.assertEqual((state['RESULT'], state['DST']['SLOTS']), (10, [99, 20]))

    def test_copy_preserves_array_element_alias(self):
        routine = 'ROUTINE copy(p,q: outer; n: INTEGER) BEGIN p = q result = n n = 99 END copy'
        state = execute(INITIALIZE + 'copy(dst,src,dst.slots[2])', routine)
        self.assertEqual((state['RESULT'], state['DST']['SLOTS']), (20, [10, 99]))

    def test_copy_partially_initialized_structure_rejected_without_mutation(self):
        p, _ = compile_program('dst.child.count = 42 src.child.count = 5 dst = src')
        before = None
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized fields'): p.run()
        before = p._state.snapshot()
        self.assertEqual(before['DST']['CHILD']['COUNT'], 42)
        self.assertEqual(before['DST']['SLOTS'], [{'uninitialized': True}] * 2)

    def test_uninitialized_array_leaf_blocks_structure_copy(self):
        p, _ = compile_program(INITIALIZE.replace('src.slots[2] = 20', '') + 'dst = src')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized fields'): p.run()
        self.assertEqual(p._state.snapshot()['DST']['CHILD']['COUNT'], {'uninitialized': True})


class StructureParameterTests(unittest.TestCase):
    def test_structure_reference_initializes_fields(self):
        routine = "ROUTINE fill(p: inner) BEGIN p.count = 7 p.label = 'abcdef' END fill"
        self.assertEqual(execute('fill(src.child)', routine)['SRC']['CHILD'], {'COUNT': 7, 'LABEL': 'abc'})

    def test_reference_forwarding_retains_identity(self):
        routines = 'ROUTINE set_count(p: inner) BEGIN p.count = 9 END set_count\nROUTINE forward(q: outer) BEGIN set_count(q.child) END forward'
        self.assertEqual(execute('forward(src)', routines)['SRC']['CHILD']['COUNT'], 9)

    def test_same_structure_two_formals_alias_immediately(self):
        routine = 'ROUTINE alias(p,q: inner) BEGIN p.count = 7 result = q.count q.count = 9 END alias'
        state = execute('alias(item,item)', routine)
        self.assertEqual((state['RESULT'], state['ITEM']['COUNT']), (7, 9))

    def test_scalar_field_reference_and_parenthesized_value(self):
        routine = 'ROUTINE change(p: INTEGER) BEGIN p = 9 END change'
        state = execute('item.count = 3 change((item.count)) result = item.count change(item.count)', routine)
        self.assertEqual((state['RESULT'], state['ITEM']['COUNT']), (3, 9))

    def test_field_string_reference_inherits_capacity(self):
        routine = "ROUTINE label(p: STRING) BEGIN p = 'abcdef' END label"
        self.assertEqual(execute('label(item.label)', routine)['ITEM']['LABEL'], 'abc')

    def test_string_array_field_reference_inherits_capacity(self):
        types = 'TYPE record_t = STRUCTURE words: ARRAY[2] OF STRING[2] ENDSTRUCTURE'
        routine = "ROUTINE fill(p: ARRAY OF STRING) BEGIN p[1] = 'abcd' END fill"
        state = execute('fill(item.words)', routine, types=types, declarations='item: record_t')
        self.assertEqual(state['ITEM']['WORDS'], ['ab', {'uninitialized': True}])

    def test_field_array_reference_uses_actual_size(self):
        routine = 'ROUTINE fill(p: ARRAY OF INTEGER) BEGIN p[2] = 7 result = ARRAY_LEN(p) END fill'
        state = execute('fill(src.slots)', routine)
        self.assertEqual((state['RESULT'], state['SRC']['SLOTS'][1]), (2, 7))

    def test_field_index_reference_captured_once(self):
        routine = 'ROUTINE change(p: INTEGER) BEGIN slot_index = 2 p = 9 END change'
        self.assertEqual(execute('slot_index = 1 change(src.slots[slot_index])', routine)['SRC']['SLOTS'], [9, {'uninitialized': True}])

    def test_real_field_reference(self):
        routine = 'ROUTINE change(p: REAL) BEGIN p = 4.5 END change'
        self.assertEqual(execute('change(src.measurement)', routine)['SRC']['MEASUREMENT'], 4.5)

    def test_integer_field_to_real_formal_is_value_copy(self):
        routine = 'ROUTINE change(p: REAL) BEGIN p = p + 0.5 real_result = p END change'
        state = execute('item.count = 3 change(item.count)', routine)
        self.assertEqual((state['ITEM']['COUNT'], state['REAL_RESULT']), (3, 3.5))

    def test_fresh_local_structure_per_invocation(self):
        routine = 'ROUTINE fresh VAR local_item: inner BEGIN flag = UNINIT(local_item.count) local_item.count = 9 END fresh'
        p, _ = compile_program('fresh fresh', routine)
        self.assertTrue(p.run()['FLAG'])
        self.assertEqual(p._state.local_frames, [])

    def test_local_structure_can_be_forwarded(self):
        routines = 'ROUTINE set_count(p: inner) BEGIN p.count = 9 END set_count\nROUTINE work VAR local_item: inner BEGIN set_count(local_item) result = local_item.count END work'
        self.assertEqual(execute('work', routines)['RESULT'], 9)

    def test_local_structure_writes_remain_pure(self):
        routine = 'ROUTINE compute: INTEGER VAR local_item: inner BEGIN local_item.count = 7 RETURN local_item.count END compute'
        p, result = compile_program('result = compute() + 1', routine)
        self.assertEqual(p.run()['RESULT'], 8)
        self.assertFalse(result.report['routine_effects']['COMPUTE']['potential_external_writes'])

    def test_reference_writes_persist_and_frame_unwinds_on_error(self):
        routine = 'ROUTINE fail(p: inner) BEGIN p.count = 7 result = 1 DIV 0 END fail'
        p, _ = compile_program('fail(item)', routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'zero'): p.run()
        self.assertEqual(p._state.snapshot()['ITEM']['COUNT'], 7)
        self.assertEqual((p._state.local_frames, p._state.call_depth), ([], 0))

    def test_report_retains_named_identity_and_reference_only_mode(self):
        _, result = compile_program('fill(item)', 'ROUTINE fill(p: inner) BEGIN END fill')
        parameter = result.report['routine_effects']['FILL']['parameters'][0]
        self.assertEqual(parameter['type_spec'][0:2], ('STRUCTURE', 'INNER'))
        self.assertEqual(parameter['passing_modes'], ['reference', 'value'])
        self.assertEqual(set(result.report['user_types']), {'INNER', 'OUTER', 'OTHER'})


class StructureRejectionTests(unittest.TestCase):
    def rejected(self, body='', routines='', code='E_TYPE', **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, routines, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_identical_shape_different_type_cannot_assign(self):
        self.rejected('item = alien')

    def test_identical_shape_different_type_cannot_bind(self):
        self.rejected('fill(alien)', 'ROUTINE fill(p: inner) BEGIN END fill')

    def test_parenthesized_structure_requires_initialized_value(self):
        program,_=compile_program('fill((item))','ROUTINE fill(p: inner) BEGIN END fill')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()

    def test_parenthesized_nested_structure_requires_initialized_value(self):
        program,_=compile_program('fill((src.child))','ROUTINE fill(p: inner) BEGIN END fill')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()

    def test_unknown_field(self):
        self.rejected('item.missing = 7', code='E_FIELD')

    def test_dot_on_scalar(self):
        self.rejected('result.field = 7')

    def test_wrong_scalar_field_type(self):
        self.rejected('item.count = TRUE')

    def test_real_to_integer_field_requires_conversion(self):
        self.rejected('item.count = 2.5')

    def test_whole_structure_uninit_blocked(self):
        self.rejected('flag = UNINIT(item)')

    def test_array_field_uninit_blocked(self):
        self.rejected('flag = UNINIT(src.slots)')

    def test_structure_comparison_blocked(self):
        self.rejected('flag = item = item')

    def test_duplicate_fields(self):
        self.rejected(types='TYPE inner = STRUCTURE count: INTEGER COUNT: BOOLEAN ENDSTRUCTURE', declarations='item: inner', code='E_DUPLICATE')

    def test_duplicate_user_type(self):
        self.rejected(types='TYPE inner = STRUCTURE x: INTEGER ENDSTRUCTURE inner = STRUCTURE y: INTEGER ENDSTRUCTURE', declarations='item: inner', code='E_DUPLICATE')

    def test_type_and_variable_cannot_share_name(self):
        self.rejected(declarations='inner: INTEGER', code='E_DUPLICATE')

    def test_empty_structure(self):
        self.rejected(types='TYPE inner = STRUCTURE ENDSTRUCTURE', declarations='item: inner', code='E_STRUCTURE')

    def test_self_reference_blocked(self):
        self.rejected(types='TYPE inner = STRUCTURE child: inner ENDSTRUCTURE', declarations='item: inner')

    def test_forward_and_cyclic_type_reference_blocked(self):
        self.rejected(types='TYPE first = STRUCTURE child: second ENDSTRUCTURE second = STRUCTURE parent: first ENDSTRUCTURE', declarations='item: first')

    def test_inline_structure_field_blocked(self):
        self.rejected(types='TYPE inner = STRUCTURE x: STRUCTURE y: INTEGER ENDSTRUCTURE ENDSTRUCTURE', declarations='item: inner')

    def test_inline_structure_variable_blocked(self):
        self.rejected(declarations='item: STRUCTURE count: INTEGER ENDSTRUCTURE')

    def test_scalar_type_alias_blocked(self):
        self.rejected(types='TYPE count_t = INTEGER', declarations='item: count_t', code='E_TYPE_ALIAS', _translator=legacy_translate)

    def test_structure_alias_blocked(self):
        self.rejected(types=TYPES + 'TYPE copy_t = inner', declarations='item: copy_t', code='E_TYPE_ALIAS', _translator=legacy_translate)

    def test_array_of_unknown_structure_type_blocked(self):
        self.rejected(declarations='items: ARRAY[2] OF missing_type')

    def test_nested_arrays_inside_field_blocked(self):
        self.rejected(types='TYPE inner = STRUCTURE x: ARRAY[2] OF ARRAY[2] OF INTEGER ENDSTRUCTURE', declarations='item: inner')

    def test_forbidden_controller_field_types_blocked(self):
        for spec in ('FILE', 'PATH', 'VISION', 'QUEUE_TYPE'):
            with self.subTest(spec=spec):
                self.rejected(types=f'TYPE inner = STRUCTURE x: {spec} ENDSTRUCTURE', declarations='item: inner')

    def test_external_type_definition_blocked(self):
        self.rejected(types='TYPE inner FROM remote = STRUCTURE x: INTEGER ENDSTRUCTURE', declarations='item: inner', code='E_SYNTAX')

    def test_local_type_definition_blocked(self):
        self.rejected(routines='ROUTINE work TYPE local_t = STRUCTURE x: INTEGER ENDSTRUCTURE BEGIN END work', code='E_ROUTINE_LOCALS')

    def test_structure_return_requires_initialized_value(self):
        program,_=compile_program('item=work()',routines='ROUTINE work: inner BEGIN RETURN item END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()

    def test_using_structure_field_selector_blocked(self):
        self.rejected('USING src.child DO count = 7 ENDUSING', code='E_USING_TARGET', _translator=legacy_translate)

    def test_field_index_with_routine_call_blocked_in_assignment(self):
        self.rejected('src.slots(next_index()) = 7', 'ROUTINE next_index: INTEGER BEGIN RETURN 1 END next_index', 'E_SYNTAX', _translator=legacy_translate)
        self.rejected('src.slots[next_index()] = 7', 'ROUTINE next_index: INTEGER BEGIN RETURN 1 END next_index', 'E_EVALUATION_ORDER', _translator=legacy_translate)

    def test_global_structure_field_writes_mark_function_effectful(self):
        self.rejected('result = update() + 1', 'ROUTINE update: INTEGER BEGIN item.count = 7 RETURN 1 END update', 'E_EVALUATION_ORDER', _translator=legacy_translate)

    def test_parameter_structure_field_writes_mark_function_effectful(self):
        self.rejected('result = update(item) + 1', 'ROUTINE update(p: inner): INTEGER BEGIN p.count = 7 RETURN 1 END update', 'E_EVALUATION_ORDER', _translator=legacy_translate)

    def test_effectful_result_assignment_to_indexed_field_blocked(self):
        self.rejected('src.slots[slot_index] = update()', 'ROUTINE update: INTEGER BEGIN slot_index = 2 RETURN 7 END update', 'E_EVALUATION_ORDER', _translator=legacy_translate)

    def test_effectful_result_assignment_to_plain_array_blocked(self):
        self.rejected('plain[slot_index] = update()', 'ROUTINE update: INTEGER BEGIN slot_index = 2 RETURN 7 END update', 'E_EVALUATION_ORDER', declarations=DECLARATIONS + 'plain: ARRAY[2] OF INTEGER', _translator=legacy_translate)


class RuntimeStructureGuards(unittest.TestCase):
    def test_nominal_mismatch_rejected_before_mutation(self):
        a_spec = ('STRUCTURE', 'A', (('X', rt.INTEGER),))
        b_spec = ('STRUCTURE', 'B', (('X', rt.INTEGER),))
        state = rt.State({'A': a_spec, 'B': b_spec}, {})
        rt.field_reference(state.raw('A'), 'X').set(7)
        rt.field_reference(state.raw('B'), 'X').set(9)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'identical named type'): state.set('A', state.get('B'))
        self.assertEqual(state.snapshot(), {'A': {'X': 7}, 'B': {'X': 9}})

    def test_field_access_runtime_type_and_name_guards(self):
        value = rt.Structure(('STRUCTURE', 'A', (('X', rt.INTEGER),)))
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'Unknown STRUCTURE field'): rt.raw_field(value, 'NOPE', 3)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'Expected STRUCTURE'): rt.raw_field(7, 'X', 3)


if __name__ == '__main__': unittest.main()
