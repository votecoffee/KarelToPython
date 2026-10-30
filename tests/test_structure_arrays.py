"""Named structure elements, deep copies, captured references and allocation guards."""
from pathlib import Path
import unittest

from karel2py import translate
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


TYPES = '''
TYPE item_t = STRUCTURE
  count: INTEGER
  label: STRING[3]
  slots: ARRAY[2] OF INTEGER
ENDSTRUCTURE
other_t = STRUCTURE
  count: INTEGER
  label: STRING[3]
  slots: ARRAY[2] OF INTEGER
ENDSTRUCTURE
outer_t = STRUCTURE
  child: item_t
  flag: BOOLEAN
ENDSTRUCTURE
holder_t = STRUCTURE
  records: ARRAY[2] OF item_t
  tag: INTEGER
ENDSTRUCTURE
narrow_t = STRUCTURE
  code: BYTE
  small: SHORT
ENDSTRUCTURE
'''
DECLARATIONS = '''
items,copied: ARRAY[2] OF item_t
grid: ARRAY[2,2] OF item_t
cube: ARRAY[1,1,2] OF item_t
outer_table: ARRAY[2] OF outer_t
narrow: ARRAY[2] OF narrow_t
alien: ARRAY[2] OF other_t
holder,saved_holder: holder_t
item: item_t
result,index_value: INTEGER
flag: BOOLEAN
'''
INITIALIZE = '''
items[1].count = 5 items[1].label = 'abcdef'
items[1].slots[1] = 10 items[1].slots[2] = 20
items[2].count = 6 items[2].label = 'def'
items[2].slots[1] = 30 items[2].slots[2] = 40
'''
EXPECTED = [dict(COUNT=5, LABEL='abc', SLOTS=[10, 20]), dict(COUNT=6, LABEL='def', SLOTS=[30, 40])]
UNKNOWN_ITEM = dict(COUNT={'uninitialized': True}, LABEL={'uninitialized': True},
                    SLOTS=[{'uninitialized': True}, {'uninitialized': True}])


def compile_program(body, routines='', types=TYPES, declarations=DECLARATIONS, *, _translator=translate):
    result = _translator(f'PROGRAM T\n{types}\nVAR\n{declarations}\n{routines}\nBEGIN\n{body}\nEND T', filename='structure_arrays.kl')
    namespace = {'__name__': 'structure_array_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body, routines='', **kwargs):
    return compile_program(body, routines, **kwargs)[0].run()


class StructureArrayFieldTests(unittest.TestCase):
    def test_example_complete_snapshot(self):
        path = Path(__file__).resolve().parents[1] / 'examples/structure_arrays.kl'
        result = translate(path.read_text())
        namespace = {'__name__': 'structure_array_example'}
        exec(result.python_source, namespace)
        first = dict(COUNT=10, LABEL='par', SLOTS=[10, 11])
        second = dict(COUNT=20, LABEL='par', SLOTS=[20, 21])
        self.assertEqual(namespace['Program']().run(), dict(
            SOURCE=[dict(COUNT=10, LABEL='par', SLOTS=[7, 11]), second],
            SAVED=[first, second], TARGET=[first, dict(COUNT=99, LABEL='par', SLOTS=[20, 21])],
            GRID=[[UNKNOWN_ITEM, UNKNOWN_ITEM], [first, UNKNOWN_ITEM]],
            HOLDER=dict(RECORDS=[dict(COUNT=77, LABEL='par', SLOTS=[10, 11]), second], READY=True),
            SAVED_HOLDER=dict(RECORDS=[first, second], READY=True), SEEN_AFTER_COPY=20))

    def test_initial_contents_are_independent_structures(self):
        state = execute('items[1].count = 7 items[1].slots[2] = 8')
        self.assertEqual(state['ITEMS'][0], dict(COUNT=7, LABEL={'uninitialized': True}, SLOTS=[{'uninitialized': True}, 8]))
        self.assertEqual(state['ITEMS'][1], UNKNOWN_ITEM)

    def test_field_paths_and_string_capacity(self):
        state = execute(INITIALIZE + 'result = items[1].count + items[2].slots[2]')
        self.assertEqual((state['ITEMS'], state['RESULT']), (EXPECTED, 45))

    def test_multidimensional_field_access(self):
        state = execute('grid[2,1].count = 7 cube[1,1,2].slots[2] = 8')
        self.assertEqual((state['GRID'][1][0]['COUNT'], state['CUBE'][0][0][1]['SLOTS'][1]), (7, 8))

    def test_nested_structure_fields(self):
        self.assertEqual(execute('outer_table[2].child.count = 7 result = outer_table[2].child.count')['RESULT'], 7)

    def test_array_of_structures_in_structure_field(self):
        self.assertEqual(execute('holder.records[2].slots[1] = 7 result = holder.records[2].slots[1]')['RESULT'], 7)

    def test_scalar_uninit_from_array_field(self):
        state = execute('flag = UNINIT(items[2].count) items[2].count = 7')
        self.assertTrue(state['FLAG'])
        self.assertEqual(state['ITEMS'][1]['COUNT'], 7)

    def test_array_len_counts_structure_elements_without_reading_fields(self):
        self.assertEqual(execute('result = ARRAY_LEN(items)')['RESULT'], 2)

    def test_case_insensitive_field_paths(self):
        self.assertEqual(execute('ItEmS[1].CoUnT = 7 ReSuLt = ITEMS[1].COUNT')['RESULT'], 7)

    def test_bounds_fail_before_field_write(self):
        program, _ = compile_program('items[1].count = 7 items[3].count = 8')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'outside 1..2'): program.run()
        self.assertEqual(program._state.snapshot()['ITEMS'][0]['COUNT'], 7)

    def test_uninitialized_field_read_is_source_located(self):
        program, _ = compile_program('result = items[1].count')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized') as caught: program.run()
        self.assertIsNotNone(caught.exception.line)


class StructureArrayCopyTests(unittest.TestCase):
    def test_whole_copy_deeply_isolates_all_elements(self):
        state = execute(INITIALIZE + 'copied = items items[1].count = 99 items[2].slots[1] = 77')
        self.assertEqual(state['COPIED'], EXPECTED)
        self.assertEqual((state['ITEMS'][0]['COUNT'], state['ITEMS'][1]['SLOTS'][0]), (99, 77))

    def test_element_copy_deeply_isolates_array_fields(self):
        state = execute(INITIALIZE + 'copied[1] = items[2] items[2].slots[1] = 77')
        self.assertEqual(state['COPIED'][0], EXPECTED[1])

    def test_scalar_structure_to_element_and_back(self):
        state = execute(INITIALIZE + 'item = items[1] copied[2] = item item.count = 99')
        self.assertEqual(state['COPIED'][1], EXPECTED[0])
        self.assertEqual(state['ITEM']['COUNT'], 99)

    def test_self_copy_keeps_contents(self):
        self.assertEqual(execute(INITIALIZE + 'items = items items[1] = items[1]')['ITEMS'], EXPECTED)

    def test_overlapping_elements_copied_independently(self):
        state = execute(INITIALIZE + 'items[2] = items[1] items[1].slots[1] = 77')
        self.assertEqual(state['ITEMS'][1], EXPECTED[0])

    def test_multidimensional_structure_copy(self):
        state = execute('grid[1,1].count = 7', types='TYPE item_t = STRUCTURE count: INTEGER ENDSTRUCTURE',
                        declarations='grid,saved: ARRAY[1,1] OF item_t')
        self.assertEqual(state['GRID'][0][0]['COUNT'], 7)
        state = execute('grid[1,1].count = 7 saved = grid grid[1,1].count = 9',
                        types='TYPE item_t = STRUCTURE count: INTEGER ENDSTRUCTURE',
                        declarations='grid,saved: ARRAY[1,1] OF item_t')
        self.assertEqual(state['SAVED'], [[{'COUNT': 7}]])

    def test_enclosing_structure_copy_is_deep(self):
        state = execute(INITIALIZE + 'holder.records = items holder.tag = 1 saved_holder = holder holder.records[1].slots[2] = 99')
        self.assertEqual(state['SAVED_HOLDER'], dict(RECORDS=EXPECTED, TAG=1))

    def test_strict_partial_array_copy_is_rejected_before_any_mutation(self):
        program, _ = compile_program(INITIALIZE + 'copied = items grid[1] = items[1] grid[1].count = 99 grid[2].count = 88 copied = grid',
                                     declarations='items,copied,grid: ARRAY[2] OF item_t', _translator=legacy_translate)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized.*STRUCTURE'): program.run()
        self.assertEqual(program._state.snapshot()['COPIED'], EXPECTED)

    def test_strict_incomplete_same_type_array_does_not_overwrite_initialized_destination(self):
        program, _ = compile_program(INITIALIZE + 'copied = items copied = grid',
                                     declarations='items,copied: ARRAY[2] OF item_t\ngrid: ARRAY[2] OF item_t', _translator=legacy_translate)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized.*STRUCTURE'): program.run()
        self.assertEqual(program._state.snapshot()['COPIED'], EXPECTED)

    def test_strict_partial_element_copy_keeps_destination(self):
        program, _ = compile_program(INITIALIZE + 'items[1] = item', _translator=legacy_translate)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized fields'): program.run()
        self.assertEqual(program._state.snapshot()['ITEMS'], EXPECTED)

    def test_strict_unknown_byte_structure_array_copy_is_blocked(self):
        program, _ = compile_program('narrow[1].small = 1 narrow[2].small = 2 saved = narrow',
                                     declarations='narrow,saved: ARRAY[2] OF narrow_t', _translator=legacy_translate)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'unknown STRUCTURE'): program.run()
        self.assertEqual(program._state.snapshot()['SAVED'][0]['CODE'], {'unknown_byte': True})

    def test_known_narrow_fields_copy_and_remain_independent(self):
        state = execute('narrow[1].code = 255 narrow[1].small = -32768 saved = narrow narrow[1].code = 7',
                        declarations='narrow,saved: ARRAY[1] OF narrow_t')
        self.assertEqual(state['SAVED'], [dict(CODE=255, SMALL=-32768)])

    def test_strict_short_marker_in_structure_array_copy_is_blocked(self):
        program, _ = compile_program('narrow[1].code = 7 narrow[1].small = 32767 saved = narrow',
                                     declarations='narrow,saved: ARRAY[1] OF narrow_t', _translator=legacy_translate)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()


class StructureArrayReferenceTests(unittest.TestCase):
    def test_structure_element_reference_can_initialize_fields(self):
        routine = 'ROUTINE fill(p: item_t) BEGIN p.count = 7 p.label = \'abcdef\' p.slots[1] = 8 p.slots[2] = 9 END fill'
        self.assertEqual(execute('fill(items[2])', routine)['ITEMS'][1], dict(COUNT=7, LABEL='abc', SLOTS=[8, 9]))

    def test_whole_array_reference_accepts_different_lengths(self):
        routine = 'ROUTINE put(p: ARRAY OF item_t) BEGIN p[ARRAY_LEN(p)].count = ARRAY_LEN(p) END put'
        state = execute('put(a) put(b)', routine, declarations='a: ARRAY[1] OF item_t\nb: ARRAY[3] OF item_t')
        self.assertEqual((state['A'][0]['COUNT'], state['B'][2]['COUNT']), (1, 3))

    def test_rank_specific_formals_and_forwarding(self):
        routines = '''ROUTINE put(p: ARRAY[*,*] OF item_t) BEGIN p[2,1].count = 7 END put
ROUTINE relay(p: ARRAY[*,*] OF item_t) BEGIN put(p) END relay'''
        self.assertEqual(execute('relay(grid)', routines)['GRID'][1][0]['COUNT'], 7)

    def test_three_dimensional_formal(self):
        routine = 'ROUTINE put(p: ARRAY[*,*,*] OF item_t) BEGIN p[1,1,2].count = 7 END put'
        self.assertEqual(execute('put(cube)', routine)['CUBE'][0][0][1]['COUNT'], 7)

    def test_local_structure_arrays_are_fresh_each_call(self):
        routine = '''ROUTINE work VAR local_table: ARRAY[1] OF item_t BEGIN
IF UNINIT(local_table[1].count) THEN result = result + 1 ENDIF local_table[1].count = 7 END work'''
        self.assertEqual(execute('result = 0 work work', routine)['RESULT'], 2)

    def test_scalar_field_reference_survives_whole_array_copy(self):
        routine = '''ROUTINE copy_and_change(p: INTEGER; dst,src: ARRAY OF item_t)
BEGIN dst = src result = p p = 99 END copy_and_change'''
        state = execute(INITIALIZE + 'copy_and_change(copied[2].count,copied,items)', routine)
        self.assertEqual((state['RESULT'], state['COPIED'][1]['COUNT'], state['ITEMS']), (6, 99, EXPECTED))

    def test_structure_element_reference_survives_whole_array_copy(self):
        routine = '''ROUTINE copy_and_change(p: item_t; dst,src: ARRAY OF item_t)
BEGIN dst = src result = p.count p.slots[1] = 99 END copy_and_change'''
        state = execute(INITIALIZE + 'copy_and_change(copied[2],copied,items)', routine)
        self.assertEqual((state['RESULT'], state['COPIED'][1]['SLOTS'][0], state['ITEMS']), (6, 99, EXPECTED))

    def test_scalar_reference_survives_whole_element_copy(self):
        routine = 'ROUTINE copy_and_change(p: INTEGER; dst,src: item_t) BEGIN dst = src result = p p = 99 END copy_and_change'
        state = execute(INITIALIZE + 'copy_and_change(items[1].count,items[1],items[2])', routine)
        self.assertEqual((state['RESULT'], state['ITEMS'][0]['COUNT'], state['ITEMS'][1]), (6, 99, EXPECTED[1]))

    def test_array_field_reference_survives_enclosing_array_copy(self):
        routine = '''ROUTINE copy_and_change(p: ARRAY OF INTEGER; dst,src: ARRAY OF item_t)
BEGIN dst = src result = p[1] p[2] = 99 END copy_and_change'''
        state = execute(INITIALIZE + 'copy_and_change(copied[2].slots,copied,items)', routine)
        self.assertEqual((state['RESULT'], state['COPIED'][1]['SLOTS'], state['ITEMS']), (30, [30, 99], EXPECTED))

    def test_reference_survives_enclosing_structure_copy(self):
        routine = '''ROUTINE copy_and_change(p: INTEGER; dst,src: holder_t)
BEGIN dst = src result = p p = 99 END copy_and_change'''
        state = execute(INITIALIZE + 'holder.records = items holder.tag = 1 copy_and_change(saved_holder.records[1].count,saved_holder,holder)', routine)
        self.assertEqual((state['RESULT'], state['SAVED_HOLDER']['RECORDS'][0]['COUNT'], state['HOLDER']['RECORDS']), (5, 99, EXPECTED))

    def test_element_indexes_are_captured_before_later_writes(self):
        routine = 'ROUTINE put(p: item_t) BEGIN index_value = 2 p.count = 7 END put'
        state = execute('index_value = 1 put(items[index_value])', routine)
        self.assertEqual((state['ITEMS'][0]['COUNT'], state['ITEMS'][1]['COUNT']), (7, {'uninitialized': True}))

    def test_known_short_field_passes_by_value_to_integer(self):
        routine = 'ROUTINE change(p: INTEGER) BEGIN p = 99 END change'
        state = execute('narrow[1].small = 7 change(narrow[1].small)', routine)
        self.assertEqual(state['NARROW'][0]['SMALL'], 7)

    def test_strict_failed_copy_unwinds_routine_and_keeps_prior_write(self):
        routine = 'ROUTINE copy(dst,src: ARRAY OF item_t) BEGIN result = 7 dst = src END copy'
        program, _ = compile_program('copy(copied,items)', routine, _translator=legacy_translate)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual((program._state.get('RESULT'), program._state.local_frames, program._state.call_depth), (7, [], 0))

    def test_unknown_formal_shape_mismatch_keeps_destination(self):
        routine = 'ROUTINE copy(dst,src: ARRAY OF item_t) BEGIN dst = src END copy'
        program, _ = compile_program(INITIALIZE + 'small[1]=items[1] copy(items,small)', routine, declarations='items: ARRAY[2] OF item_t\nsmall: ARRAY[1] OF item_t')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'matching logical dimensions'): program.run()
        self.assertEqual(program._state.snapshot()['ITEMS'], EXPECTED)


class StructureArrayBoundaryTests(unittest.TestCase):
    def rejected(self, body='', code='E_TYPE', **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_compatible_record_copies_keep_receiver_names(self):
        for body in ('items=alien','items[1]=alien[1]'):
            p,_=compile_program('alien[1].count=7 '+body+' alien[1].count=9')
            self.assertEqual(p.run()['ITEMS'][0]['COUNT'],7)
            self.assertEqual(p._state.values['ITEMS'].values[0].spec[1],'ITEM_T')

    def test_compatible_named_record_formal_is_private(self):
        p,_=compile_program('alien[1].count=7 put(alien)',routines='ROUTINE put(p:ARRAY OF item_t) BEGIN p[1].count=9 result=p[1].count END put')
        state=p.run();self.assertEqual((state['ALIEN'][0]['COUNT'],state['RESULT']),(7,9))

    def test_wrong_rank_formal_is_rejected(self):
        self.rejected('put(items)', routines='ROUTINE put(p: ARRAY[*,*] OF item_t) BEGIN END put')

    def test_parenthesized_array_value_remains_blocked(self):
        self.rejected('put((items))', code='E_ARRAY_VALUE', routines='ROUTINE put(p: ARRAY OF item_t) BEGIN END put', _translator=legacy_translate)

    def test_strict_parenthesized_structure_element_requires_initialized_contents(self):
        program,_=compile_program('put((items[1]))',routines='ROUTINE put(p: item_t) BEGIN END put', _translator=legacy_translate)
        with self.assertRaises(rt.KarelRuntimeError): program.run()

    def test_aggregate_uninit_remains_blocked(self):
        for expression in ('items', 'items[1]', 'items[1].slots'):
            with self.subTest(expression=expression): self.rejected(f'flag = UNINIT({expression})')

    def test_multidimensional_array_len_remains_blocked(self):
        self.rejected('result = ARRAY_LEN(grid)', code='E_ARRAY_LEN', _translator=legacy_translate)

    def test_partial_subscripts_remain_blocked(self):
        self.rejected('result = grid[1].count', code='E_ARRAY_RANK')

    def test_complete_chained_record_indexes_match_comma_access(self):
        state=execute('grid[1][1].count=7 result=grid[1,1].count')
        self.assertEqual(state['RESULT'],7)

    def test_routine_call_in_target_index_remains_blocked(self):
        self.rejected('items[next_index()].count = 7', code='E_EVALUATION_ORDER', routines='ROUTINE next_index: INTEGER BEGIN RETURN 1 END next_index', _translator=legacy_translate)

    def test_effectful_field_destination_order_remains_blocked(self):
        self.rejected('items[index_value].count = update()', code='E_EVALUATION_ORDER', routines='ROUTINE update: INTEGER BEGIN index_value = 2 RETURN 7 END update', _translator=legacy_translate)

    def test_multi_subscript_call_order_remains_blocked(self):
        self.rejected('result = grid[next_index(),1].count', code='E_EVALUATION_ORDER', routines='ROUTINE next_index: INTEGER BEGIN RETURN 1 END next_index', _translator=legacy_translate)

    def test_structure_array_return_remains_blocked(self):
        self.rejected(routines='ROUTINE make: ARRAY[2] OF item_t BEGIN RETURN items END make', code='E_RETURN_TYPE', _translator=legacy_translate)

    def test_forward_or_recursive_named_element_remains_blocked(self):
        self.rejected(types='TYPE outer_t = STRUCTURE children: ARRAY[2] OF item_t ENDSTRUCTURE item_t = STRUCTURE n: INTEGER ENDSTRUCTURE', declarations='outer: outer_t')

    def test_unknown_named_element_formal_remains_blocked(self):
        self.rejected(routines='ROUTINE put(p: ARRAY OF missing_type) BEGIN END put')

    def test_array_capacity_counts_nested_scalar_leaves(self):
        self.rejected(declarations='items: ARRAY[8192] OF item_t', code='E_ARRAY_CAPACITY')
        self.rejected(declarations='items: ARRAY[128,64] OF item_t', code='E_ARRAY_CAPACITY')

    def test_array_capacity_includes_structure_array_fields(self):
        self.rejected(declarations='items: ARRAY[3641] OF holder_t', code='E_ARRAY_CAPACITY')

    def test_maximum_permitted_scalar_leaf_count(self):
        _, result = compile_program('', types='TYPE single = STRUCTURE n: INTEGER ENDSTRUCTURE', declarations='items: ARRAY[32767] OF single')
        self.assertIn('ARRAY OF named STRUCTURE', result.report['features'])

    def test_reserved_type_name_cannot_be_a_formal_element(self):
        self.rejected(routines='ROUTINE put(p: ARRAY OF SQRT) BEGIN END put', code='E_PARAMETERS')


class StructureArrayRuntimeTests(unittest.TestCase):
    def test_direct_array_set_preserves_nested_field_reference(self):
        spec = ('STRUCTURE', 'ITEM', (('COUNT', rt.INTEGER),))
        array = rt.Array(('ARRAY', 1, spec))
        reference = rt.field_reference(array.get(1), 'COUNT')
        source = rt.Structure(spec)
        rt.field_reference(source, 'COUNT').set(7)
        array.set(1, source)
        self.assertEqual(reference.raw(), 7)
        reference.set(9)
        self.assertEqual((array.snapshot(), source.values['COUNT']), ([{'COUNT': 9}], 7))

    def test_direct_array_clone_deeply_isolates_uninitialized_storage(self):
        spec = ('STRUCTURE', 'ITEM', (('COUNT', rt.INTEGER),))
        original = rt.Array(('ARRAY', 2, spec))
        copy = original.clone()
        rt.field_reference(copy.get(1), 'COUNT').set(7)
        self.assertEqual(original.snapshot(), [{'COUNT': {'uninitialized': True}}] * 2)

    def test_runtime_capacity_guard_counts_structure_fields(self):
        spec = ('STRUCTURE', 'ITEM', (('A', rt.INTEGER), ('B', ('ARRAY', 2, rt.SHORT))))
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'scalar leaves'): rt.Array(('ARRAY', 10923, spec))

    def test_runtime_type_and_initialization_guards_before_mutation(self):
        spec = ('STRUCTURE', 'ITEM', (('COUNT', rt.INTEGER),))
        original = rt.Array(('ARRAY', 1, spec))
        alias = rt.field_reference(original.get(1), 'COUNT')
        alias.set(7)
        for source in (rt.Array(('ARRAY', 1, spec)), rt.Array(('ARRAY', 2, spec))):
            with self.subTest(size=source.shape):
                with self.assertRaises(rt.KarelRuntimeError): rt.checked(original.spec, source)
                self.assertEqual(alias.raw(), 7)

    def test_leaf_count_saturates_large_type_graphs(self):
        spec = ('STRUCTURE', 'LEAF', (('N', rt.INTEGER),))
        for depth in range(20): spec = ('STRUCTURE', f'T{depth}', (('A', spec), ('B', spec)))
        self.assertEqual(rt.scalar_leaf_count(spec), 32768)


if __name__ == '__main__': unittest.main()
