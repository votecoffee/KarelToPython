"""BYTE/SHORT storage, sentinel state, checked promotion and value arguments."""
import unittest

from karel2py import translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


TYPES = '''TYPE packet_t = STRUCTURE
code: BYTE
count: SHORT
payload: ARRAY[2] OF BYTE
ENDSTRUCTURE'''
DECLARATIONS = '''
bytes,byte_copy: ARRAY[3] OF BYTE
shorts,short_copy: ARRAY[3] OF SHORT
grid: ARRAY[2,2] OF BYTE
short_grid: ARRAY[2,2] OF SHORT
item,copy: packet_t
result,seen,total,before,after,index_value: INTEGER
measurement: REAL
flag: BOOLEAN
'''
UNKNOWN = {'unknown_byte': True}
UNINIT = {'uninitialized': True}
INITIALIZE_ITEM = 'item.code = 7 item.count = 12 item.payload[1] = 10 item.payload[2] = 20 '


def compile_program(body='', routines='', declarations=DECLARATIONS, types=TYPES):
    result = translate(f'PROGRAM T\n{types}\nVAR\n{declarations}\n{routines}\nBEGIN\n{body}\nEND T', filename='narrow.kl')
    namespace = {'__name__': 'narrow_tests'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body='', routines='', **kwargs): return compile_program(body, routines, **kwargs)[0].run()


class StorageTests(unittest.TestCase):
    def test_unwritten_byte_is_explicitly_unknown_in_snapshot(self):
        state = execute()
        self.assertEqual(state['BYTES'], [UNKNOWN]*3)
        self.assertEqual(state['ITEM'], {'CODE': UNKNOWN, 'COUNT': UNINIT, 'PAYLOAD': [UNKNOWN]*2})

    def test_byte_range_endpoints_are_valid_values(self):
        state = execute('bytes[1] = 0 bytes[2] = 255 result = bytes[1] + bytes[2]')
        self.assertEqual((state['BYTES'], state['RESULT']), ([0, 255, UNKNOWN], 255))

    def test_short_range_endpoints_are_valid_values(self):
        state = execute('shorts[1] = -32768 shorts[2] = 32766 result = shorts[1] + shorts[2]')
        self.assertEqual((state['SHORTS'], state['RESULT']), ([-32768, 32766, UNINIT], -2))

    def test_short_32767_assignment_sets_uninitialized_marker(self):
        state = execute('shorts[1] = 7 shorts[1] = 32767 flag = UNINIT(shorts[1])')
        self.assertTrue(state['FLAG'])
        self.assertEqual(state['SHORTS'], [UNINIT]*3)

    def test_short_marker_may_be_computed(self):
        self.assertTrue(execute('shorts[1] = 32766 + 1 flag = UNINIT(shorts[1])')['FLAG'])

    def test_short_can_be_initialized_after_marker_assignment(self):
        state = execute('shorts[1] = 32767 shorts[1] = 9 flag = UNINIT(shorts[1])')
        self.assertEqual((state['SHORTS'][0], state['FLAG']), (9, False))

    def test_short_initialization_predicate_works_before_any_write(self):
        self.assertTrue(execute('flag = UNINIT(shorts[3])')['FLAG'])

    def test_structure_byte_and_short_fields(self):
        state = execute('item.code = 255 item.count = -32768 result = item.code + item.count')
        self.assertEqual((state['ITEM']['CODE'], state['ITEM']['COUNT'], state['RESULT']), (255, -32768, -32513))

    def test_structure_short_marker(self):
        state = execute('item.count = 32767 flag = UNINIT(item.count)')
        self.assertEqual((state['ITEM']['COUNT'], state['FLAG']), (UNINIT, True))

    def test_multidimensional_byte_and_short_arrays(self):
        state = execute('grid[2,1] = 255 short_grid[1,2] = -7 result = grid[2,1] + short_grid[1,2]')
        self.assertEqual((state['GRID'], state['SHORT_GRID'], state['RESULT']),
                         ([[UNKNOWN, UNKNOWN], [255, UNKNOWN]], [[UNINIT, -7], [UNINIT, UNINIT]], 248))

    def test_integer_assignment_to_narrow_storage_and_back(self):
        state = execute('result = 12 bytes[1] = result shorts[1] = bytes[1] bytes[2] = shorts[1] seen = shorts[1]')
        self.assertEqual((state['BYTES'][:2], state['SHORTS'][0], state['SEEN']), ([12, 12], 12, 12))

    def test_scalar_promotion_to_real_is_checked(self):
        state = execute('bytes[1] = 255 shorts[1] = -32768 measurement = bytes[1] + shorts[1] * 0.5')
        self.assertEqual(state['MEASUREMENT'], -16129.0)

    def test_program_instances_have_independent_narrow_storage(self):
        p, _ = compile_program('bytes[1] = 7')
        p.run()
        self.assertEqual(type(p)()._state.snapshot()['BYTES'], [UNKNOWN]*3)

    def test_labelled_engine_uses_same_storage_rules(self):
        self.assertEqual(execute('GOTO fill fill:: bytes[1] = 7 result = bytes[1]')['RESULT'], 7)


class ExpressionTests(unittest.TestCase):
    def test_narrow_arithmetic_promotes_to_integer_without_wrapping(self):
        state = execute('bytes[1] = 255 shorts[1] = 32766 result = bytes[1] + shorts[1]')
        self.assertEqual(state['RESULT'], 33021)

    def test_unary_negative_and_not_use_integer_results(self):
        state = execute('bytes[1] = 0 shorts[1] = -7 result = NOT bytes[1] seen = -shorts[1]')
        self.assertEqual((state['RESULT'], state['SEEN']), (-1, 7))

    def test_integer_bit_operations_and_division(self):
        state = execute('bytes[1] = 7 shorts[1] = 2 result = bytes[1] AND shorts[1] seen = bytes[1] DIV shorts[1] total = bytes[1] MOD shorts[1]')
        self.assertEqual((state['RESULT'], state['SEEN'], state['TOTAL']), (2, 3, 1))

    def test_comparisons_between_narrow_integer_and_real(self):
        self.assertTrue(execute('bytes[1] = 7 shorts[1] = 7 flag = (bytes[1] = shorts[1]) AND (shorts[1] = 7.0)')['FLAG'])

    def test_abs_returns_integer_and_handles_short_minimum(self):
        self.assertEqual(execute('shorts[1] = -32768 result = ABS(shorts[1])')['RESULT'], 32768)

    def test_numeric_conversion_builtins_accept_narrow_values(self):
        state = execute('bytes[1] = 255 shorts[1] = -7 result = ROUND(bytes[1]) seen = TRUNC(shorts[1])')
        self.assertEqual((state['RESULT'], state['SEEN']), (255, -7))

    def test_narrow_element_as_array_index(self):
        self.assertEqual(execute('bytes[1] = 2 shorts[bytes[1]] = 9 result = shorts[2]')['RESULT'], 9)

    def test_narrow_element_as_select_selector(self):
        state = execute('bytes[1] = 2 SELECT bytes[1] OF CASE(2): result = 9 ELSE: result = 0 ENDSELECT')
        self.assertEqual(state['RESULT'], 9)

    def test_narrow_values_as_for_bounds(self):
        state = execute('bytes[1] = 2 shorts[1] = 3 total = 0 FOR index_value = bytes[1] TO shorts[1] DO total = total + index_value ENDFOR')
        self.assertEqual(state['TOTAL'], 5)

    def test_narrow_values_as_string_builtin_integer_arguments(self):
        self.assertEqual(execute("bytes[1] = 65 result = ORD(CHR(bytes[1]),1)")['RESULT'], 65)


class ParameterTests(unittest.TestCase):
    def test_bare_byte_argument_to_integer_is_always_value(self):
        state = execute('bytes[1] = 7 change(bytes[1])', 'ROUTINE change(p: INTEGER) BEGIN p = 99 seen = p END change')
        self.assertEqual((state['BYTES'][0], state['SEEN']), (7, 99))

    def test_bare_short_argument_to_integer_is_always_value(self):
        state = execute('shorts[1] = -7 change(shorts[1])', 'ROUTINE change(p: INTEGER) BEGIN p = 99 END change')
        self.assertEqual(state['SHORTS'][0], -7)

    def test_structure_byte_field_to_integer_is_value(self):
        state = execute('item.code = 7 change(item.code)', 'ROUTINE change(p: INTEGER) BEGIN p = 99 END change')
        self.assertEqual(state['ITEM']['CODE'], 7)

    def test_narrow_to_real_is_value_and_uses_exactness_guard(self):
        state = execute('shorts[1] = -7 change(shorts[1])', 'ROUTINE change(p: REAL) BEGIN p = p + 0.5 measurement = p END change')
        self.assertEqual((state['SHORTS'][0], state['MEASUREMENT']), (-7, -6.5))

    def test_parentheses_and_expressions_remain_value_arguments(self):
        routine = 'ROUTINE change(p: INTEGER) BEGIN p = 99 END change'
        self.assertEqual(execute('bytes[1] = 7 change((bytes[1])) change(bytes[1]+0)', routine)['BYTES'][0], 7)

    def test_two_narrow_arguments_create_independent_temporaries(self):
        routine = 'ROUTINE change(p,q: INTEGER) BEGIN p = 99 seen = q END change'
        state = execute('bytes[1] = 7 change(bytes[1],bytes[1])', routine)
        self.assertEqual((state['BYTES'][0], state['SEEN']), (7, 7))

    def test_whole_byte_array_parameter_is_reference(self):
        state = execute('fill(bytes)', 'ROUTINE fill(p: ARRAY OF BYTE) BEGIN p[1] = 255 result = ARRAY_LEN(p) END fill')
        self.assertEqual((state['BYTES'][0], state['RESULT']), (255, 3))

    def test_whole_short_array_parameter_is_reference(self):
        state = execute('fill(shorts)', 'ROUTINE fill(p: ARRAY OF SHORT) BEGIN p[1] = 32767 p[2] = -9 flag = UNINIT(p[1]) END fill')
        self.assertEqual((state['SHORTS'], state['FLAG']), ([UNINIT, -9, UNINIT], True))

    def test_multidimensional_narrow_array_formals(self):
        routines = ('ROUTINE fill(p: ARRAY[*,*] OF BYTE; q: ARRAY[*,*] OF SHORT) '
                    'BEGIN p[1,2] = 255 q[2,1] = -9 END fill')
        state = execute('fill(grid,short_grid)', routines)
        self.assertEqual((state['GRID'][0][1], state['SHORT_GRID'][1][0]), (255, -9))

    def test_whole_array_forwarding_preserves_narrow_storage(self):
        routines = ('ROUTINE fill(p: ARRAY OF BYTE) BEGIN p[2] = 9 END fill '
                    'ROUTINE forward(p: ARRAY OF BYTE) BEGIN fill(p) END forward')
        self.assertEqual(execute('forward(bytes)', routines)['BYTES'][1], 9)

    def test_forwarded_integer_formal_retains_independent_narrow_value(self):
        routines = ('ROUTINE change(p: INTEGER) BEGIN p = 99 END change '
                    'ROUTINE forward(p: INTEGER) BEGIN change(p) seen = p END forward')
        state = execute('bytes[1] = 7 forward(bytes[1])', routines)
        self.assertEqual((state['BYTES'][0], state['SEEN']), (7, 99))

    def test_function_can_return_narrow_value_as_integer_or_real(self):
        routines = ('ROUTINE code(p: packet_t): INTEGER BEGIN RETURN p.code END code '
                    'ROUTINE count(p: packet_t): REAL BEGIN RETURN p.count END count')
        state = execute('item.code = 7 item.count = -9 result = code(item) measurement = count(item)', routines)
        self.assertEqual((state['RESULT'], state['MEASUREMENT']), (7, -9.0))

    def test_local_arrays_are_fresh_each_call(self):
        routine = ('ROUTINE fill VAR local_bytes: ARRAY[1] OF BYTE local_shorts: ARRAY[1] OF SHORT '
                   'BEGIN flag = UNINIT(local_shorts[1]) local_bytes[1] = 7 result = local_bytes[1] END fill')
        p, _ = compile_program('fill fill', routine)
        self.assertEqual((p.run()['FLAG'], p._state.local_frames, p._state.call_depth), (True, [], 0))

    def test_report_records_value_conversion_and_policy(self):
        _, result = compile_program('bytes[1] = 7 change(bytes[1])', 'ROUTINE change(p: INTEGER) BEGIN END change')
        self.assertIn('BYTE to INTEGER value argument', result.report['features'])
        self.assertEqual(result.report['narrow_integer_policy']['short_uninitialized_assignment'], 32767)
        self.assertFalse(result.report['narrow_integer_policy']['controller_validated'])


class CopyTests(unittest.TestCase):
    def test_byte_array_copy_is_independent_including_unknown_elements(self):
        state = execute('bytes[1] = 7 byte_copy = bytes bytes[1] = 9')
        self.assertEqual((state['BYTE_COPY'], state['BYTES']), ([7, UNKNOWN, UNKNOWN], [9, UNKNOWN, UNKNOWN]))

    def test_short_array_copy_preserves_uninitialized_marker(self):
        state = execute('shorts[1] = 7 shorts[2] = 32767 short_copy = shorts shorts[1] = 9')
        self.assertEqual(state['SHORT_COPY'], [7, UNINIT, UNINIT])

    def test_structure_copy_keeps_source_independent(self):
        state = execute(INITIALIZE_ITEM + 'copy = item item.code = 9')
        self.assertEqual(state['COPY'], {'CODE': 7, 'COUNT': 12, 'PAYLOAD': [10, 20]})

    def test_scalar_narrow_argument_is_copied_before_whole_array_assignment(self):
        routine = ('ROUTINE copy_array(p,q: ARRAY OF BYTE; scalar: INTEGER) '
                   'BEGIN p = q seen = scalar scalar = 99 END copy_array')
        state = execute('bytes[1] = 1 byte_copy[1] = 7 copy_array(bytes,byte_copy,bytes[1])', routine)
        # Narrow scalar parameters were copied before the call; they cannot retain an element alias.
        self.assertEqual((state['SEEN'], state['BYTES'][0]), (1, 7))

    def test_array_formal_alias_survives_enclosing_structure_copy(self):
        routine = 'ROUTINE copy_packet(p,q: packet_t; payload: ARRAY OF BYTE) BEGIN p = q payload[1] = 99 END copy_packet'
        state = execute(INITIALIZE_ITEM + 'copy_packet(copy,item,copy.payload)', routine)
        self.assertEqual((state['COPY']['PAYLOAD'], state['ITEM']['PAYLOAD']), ([99, 20], [10, 20]))

    def test_unknown_byte_blocks_structure_copy_before_mutation(self):
        p, _ = compile_program('copy.code = 99 item.count = 7 copy = item')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized fields'): p.run()
        self.assertEqual(p._state.snapshot()['COPY']['CODE'], 99)


class BoundaryTests(unittest.TestCase):
    def rejected(self, body='', routines='', code='E_TYPE', **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body, routines, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_byte_range_errors_preserve_previous_value(self):
        for value in (-1, 256, -2147483648, 2147483647):
            with self.subTest(value=value):
                spelling = 'MININT' if value == -2147483648 else str(value)
                p, _ = compile_program(f'bytes[1] = 7 bytes[1] = {spelling}')
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'BYTE value outside'): p.run()
                self.assertEqual(p._state.snapshot()['BYTES'][0], 7)

    def test_short_range_errors_preserve_previous_value(self):
        for value in (-32769, 32768):
            with self.subTest(value=value):
                p, _ = compile_program(f'shorts[1] = 7 shorts[1] = {value}')
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'SHORT value outside'): p.run()
                self.assertEqual(p._state.snapshot()['SHORTS'][0], 7)

    def test_short_sentinel_read_is_uninitialized_error(self):
        p, _ = compile_program('shorts[1] = 32767 result = shorts[1]')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): p.run()

    def test_unwritten_byte_read_never_assumes_zero_or_uninitialized(self):
        for body in ('result = bytes[1]', 'result = item.code', 'result = bytes[1] + 0'):
            with self.subTest(body=body):
                p, _ = compile_program(body)
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'BYTE contents are unknown'): p.run()

    def test_unknown_byte_value_argument_fails_before_callee_runs(self):
        p, _ = compile_program('seen = 1 change(bytes[1])', 'ROUTINE change(p: INTEGER) BEGIN seen = 9 END change')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'BYTE contents are unknown'): p.run()
        self.assertEqual((p._state.get('SEEN'), p._state.local_frames), (1, []))

    def test_uninitialized_short_value_argument_fails_before_callee_runs(self):
        p, _ = compile_program('seen = 1 change(shorts[1])', 'ROUTINE change(p: INTEGER) BEGIN seen = 9 END change')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): p.run()
        self.assertEqual((p._state.get('SEEN'), p._state.local_frames), (1, []))

    def test_byte_initialization_queries_remain_blocked(self):
        for body in ('flag = UNINIT(bytes[1])', 'bytes[1] = 7 flag = UNINIT(bytes[1])', 'flag = UNINIT(item.code)'):
            with self.subTest(body=body): self.rejected(body, code='E_BYTE_UNINIT')

    def test_standalone_byte_and_short_declarations_remain_blocked(self):
        for name in ('BYTE', 'SHORT'):
            with self.subTest(name=name):
                self.rejected(declarations='value: ' + name)
                self.rejected(routines=f'ROUTINE work VAR value: {name} BEGIN END work')

    def test_scalar_narrow_formals_and_returns_remain_blocked(self):
        for name in ('BYTE', 'SHORT'):
            with self.subTest(name=name):
                self.rejected(routines=f'ROUTINE work(p: {name}) BEGIN END work', code='E_PARAMETERS')
                self.rejected(routines=f'ROUTINE work: {name} BEGIN RETURN 1 END work', code='E_RETURN_TYPE')

    def test_wrong_scalar_assignment_types_rejected(self):
        for body in ('bytes[1] = TRUE', 'shorts[1] = 1.5', "bytes[1] = 'x'"):
            with self.subTest(body=body): self.rejected(body)

    def test_narrow_scalar_cannot_bind_boolean_formal(self):
        self.rejected('work(bytes[1])', 'ROUTINE work(p: BOOLEAN) BEGIN END work')

    def test_whole_arrays_do_not_convert_element_types(self):
        self.rejected('shorts = bytes')
        self.rejected('work(bytes)', 'ROUTINE work(p: ARRAY OF INTEGER) BEGIN END work')
        self.rejected('work(shorts)', 'ROUTINE work(p: ARRAY OF BYTE) BEGIN END work')

    def test_whole_narrow_array_value_passing_remains_blocked(self):
        self.rejected('work((bytes))', 'ROUTINE work(p: ARRAY OF BYTE) BEGIN END work', code='E_ARRAY_VALUE')

    def test_narrow_field_cannot_be_for_counter(self):
        self.rejected('FOR item.code = 1 TO 3 DO ENDFOR', code='E_SYNTAX')

    def test_effectful_indexed_result_guard_still_applies(self):
        self.rejected('bytes[index_value] = update()', 'ROUTINE update: INTEGER BEGIN index_value = 2 RETURN 7 END update', code='E_EVALUATION_ORDER')

    def test_narrow_array_formal_shape_failure_unwinds_frames(self):
        p, _ = compile_program('work(bytes)', 'ROUTINE work(p: ARRAY OF BYTE) BEGIN p[4] = 7 END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'outside'): p.run()
        self.assertEqual((p._state.local_frames, p._state.call_depth), ([], 0))

    def test_reference_write_persists_after_range_error_and_frame_unwinds(self):
        p, _ = compile_program('work(bytes)', 'ROUTINE work(p: ARRAY OF BYTE) BEGIN p[1] = 7 p[2] = 256 END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'BYTE value outside'): p.run()
        self.assertEqual((p._state.snapshot()['BYTES'], p._state.local_frames), ([7, UNKNOWN, UNKNOWN], []))


class RuntimeTests(unittest.TestCase):
    def test_checked_short_sentinel_and_byte_ranges(self):
        self.assertIs(rt.checked(rt.SHORT, 32767), rt.UNINITIALIZED)
        self.assertEqual(rt.checked(rt.BYTE, 255), 255)
        for spec, value in ((rt.BYTE, True), (rt.BYTE, 256), (rt.SHORT, 32768)):
            with self.subTest(spec=spec), self.assertRaises(rt.KarelRuntimeError): rt.checked(spec, value)

    def test_runtime_unknown_byte_is_distinct_from_uninitialized(self):
        self.assertIsNot(rt.UNKNOWN_BYTE, rt.UNINITIALIZED)
        self.assertEqual(rt.snapshot_value(rt.UNKNOWN_BYTE), UNKNOWN)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'BYTE contents are unknown'): rt.require(rt.UNKNOWN_BYTE, 3)

    def test_direct_runtime_byte_query_is_blocked_for_unknown_storage(self):
        with self.assertRaises(rt.KarelRuntimeError): rt.uninit(rt.UNKNOWN_BYTE)

    def test_runtime_captured_byte_storage_survives_whole_copy(self):
        spec = ('ARRAY', 2, rt.BYTE)
        state = rt.State({'A': spec, 'B': spec}, {})
        reference = rt.index_reference(state.raw('A'), 1)
        rt.store_index(state.raw('B'), 1, 7)
        state.set('A', state.raw('B'))
        reference.set(99)
        self.assertEqual((state.snapshot()['A'], state.snapshot()['B']), ([99, UNKNOWN], [7, UNKNOWN]))


if __name__ == '__main__': unittest.main()
