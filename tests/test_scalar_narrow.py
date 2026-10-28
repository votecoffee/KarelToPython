"""Authored Pythonic narrow scalar storage, interfaces and service regressions."""
import json
import struct
import unittest

from karel2py import runtime as rt, translate, translate_project
from karel2py.lexer import TranslationError
from karel2py.storage import decode_typed, typed_value
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source


UNKNOWN = {'unknown_byte': True}
MISSING = {'uninitialized': True}
DECL = 'b,other: BYTE small,short_other: SHORT n,total,seen,calls,entry,status: INTEGER r: REAL flag: BOOLEAN f: FILE'


def program(body='', routines='', decl=DECL, prefix='', **options):
    return compile_program(body, decl=decl, routines=routines, prefix=prefix, **options)


def execute(body='', routines='', **options):
    return program(body, routines, **options)[0].run()


class NarrowScalarStorageTests(unittest.TestCase):
    def test_initial_states_distinguish_unknown_byte_and_missing_short(self):
        state = execute('flag=UNINIT(small)')
        self.assertEqual((state['B'], state['SMALL'], state['FLAG']), (UNKNOWN, MISSING, True))

    def test_byte_endpoints_are_plain_unsigned_values(self):
        state = execute('b=0 other=255 n=b+other')
        self.assertEqual((state['B'], state['OTHER'], state['N']), (0, 255, 255))

    def test_short_endpoints_are_plain_signed_values(self):
        state = execute('small=-32768 short_other=32766 n=small+short_other')
        self.assertEqual((state['SMALL'], state['SHORT_OTHER'], state['N']), (-32768, 32766, -2))

    def test_assignments_cross_integral_domains_with_checked_values(self):
        state = execute('n=200 b=n small=b other=small n=small r=b')
        self.assertEqual((state['B'], state['SMALL'], state['OTHER'], state['N'], state['R']), (200, 200, 200, 200, 200.0))

    def test_arithmetic_promotes_without_narrow_wrapping(self):
        state = execute('b=255 small=-32768 n=b+1 total=small-1 r=b/2')
        self.assertEqual((state['N'], state['TOTAL'], state['R']), (256, -32769, 127.5))

    def test_unary_and_comparison_promote_numeric_values(self):
        state = execute('b=2 small=-3 n=-b total=ABS(small) flag=b>small')
        self.assertEqual((state['N'], state['TOTAL'], state['FLAG']), (-2, 3, True))

    def test_range_failures_keep_previous_storage(self):
        for name, value in (('b', -1), ('b', 256), ('small', -32769), ('small', 32768)):
            with self.subTest(name=name, value=value):
                p, _ = program(f'{name}=7 {name}={value}')
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'outside'): p.run()
                self.assertEqual(p.snapshot()[name.upper()], 7)

    def test_nonintegral_assignments_remain_rejected(self):
        for value in ('1.5', 'TRUE', "'4'"):
            for name in ('b', 'small'):
                with self.subTest(name=name, value=value), self.assertRaises(TranslationError): program(f'{name}={value}')

    def test_short_sentinel_clears_storage_and_can_be_reinitialized(self):
        state = execute('small=8 small=32767 flag=UNINIT(small) IF flag THEN small=-1 ENDIF')
        self.assertEqual((state['FLAG'], state['SMALL']), (True, -1))

    def test_unknown_reads_do_not_become_zero(self):
        for text, message in (('n=b', 'BYTE contents are unknown'), ('n=small', 'uninitialized')):
            with self.subTest(text=text):
                p, _ = program(text)
                with self.assertRaisesRegex(rt.KarelRuntimeError, message): p.run()

    def test_byte_uninit_query_stays_prohibited(self):
        for body in ('flag=UNINIT(b)', 'b=7 flag=UNINIT(b)'):
            with self.subTest(body=body), self.assertRaises(TranslationError) as caught: program(body)
            self.assertEqual(caught.exception.code, 'E_BYTE_UNINIT')

    def test_program_instances_have_independent_storage(self):
        first, result = program('b=9 small=3')
        first.run()
        ns = {'__name__': 'independent_narrow_test'}
        exec(result.python_source, ns)
        second = ns['Program']()
        self.assertEqual((second.snapshot()['B'], second.snapshot()['SMALL']), (UNKNOWN, MISSING))

    def test_scalar_alias_chains_resolve_in_globals_and_locals(self):
        state = execute('b=255 work()', decl='b: octet n: INTEGER', prefix='TYPE raw=BYTE octet=raw signed=SHORT',
                        routines='ROUTINE work VAR local: signed BEGIN local=-11 n=b+local END work')
        self.assertEqual((state['B'], state['N']), (255, 244))


class NarrowScalarInterfaceTests(unittest.TestCase):
    def test_exact_bare_narrow_arguments_alias_the_caller(self):
        state = execute('b=1 small=2 put(b,small)', 'ROUTINE put(a: BYTE; z: SHORT) BEGIN a=255 z=-11 END put')
        self.assertEqual((state['B'], state['SMALL']), (255, -11))

    def test_grouped_narrow_arguments_own_private_cells(self):
        state = execute('b=1 small=2 put((b),(small))', 'ROUTINE put(a: BYTE; z: SHORT) BEGIN a=255 z=-11 END put')
        self.assertEqual((state['B'], state['SMALL']), (1, 2))

    def test_integer_to_narrow_bare_arguments_are_checked_private_values(self):
        state = execute('n=7 put(n,n)', 'ROUTINE put(a: BYTE; z: SHORT) BEGIN a=8 z=9 seen=a+z END put')
        self.assertEqual((state['N'], state['SEEN']), (7, 17))

    def test_cross_narrow_arguments_are_private(self):
        state = execute('b=7 small=8 put(small,b)', 'ROUTINE put(a: BYTE; z: SHORT) BEGIN a=1 z=2 seen=a+z END put')
        self.assertEqual((state['B'], state['SMALL'], state['SEEN']), (7, 8, 3))

    def test_narrow_to_integer_and_real_arguments_remain_private_promotions(self):
        state = execute('b=7 small=-2 put(b,small)', 'ROUTINE put(a: INTEGER; z: REAL) BEGIN a=10 z=1.5 seen=a r=z END put')
        self.assertEqual((state['B'], state['SMALL'], state['SEEN'], state['R']), (7, -2, 10, 1.5))

    def test_out_of_range_conversion_happens_before_later_argument_effects(self):
        for name, initial in (('n', 256), ('small', -1)):
            with self.subTest(name=name):
                p, _ = program(f'{name}={initial} seen=0 put({name},later())',
                    'ROUTINE later: INTEGER BEGIN seen=1 RETURN 1 END later '
                    'ROUTINE put(a: BYTE; z: INTEGER) BEGIN seen=2 END put')
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'BYTE value outside'): p.run()
                self.assertEqual((p.snapshot()['SEEN'], p._state.call_depth, p._state.local_frames), (0, 0, []))

    def test_unknown_exact_byte_reference_can_be_initialized_by_callee(self):
        state = execute('put(b)', 'ROUTINE put(a: BYTE) BEGIN a=42 END put')
        self.assertEqual(state['B'], 42)

    def test_unknown_grouped_byte_is_a_read_and_fails_before_callee(self):
        p, _ = program('seen=0 put((b))', 'ROUTINE put(a: BYTE) BEGIN seen=1 a=42 END put')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'BYTE contents are unknown'): p.run()
        self.assertEqual((p.snapshot()['B'], p.snapshot()['SEEN'], p._state.local_frames), (UNKNOWN, 0, []))

    def test_missing_exact_short_reference_can_be_queried_and_initialized(self):
        state = execute('put(small)', 'ROUTINE put(a: SHORT) BEGIN flag=UNINIT(a) a=-1 END put')
        self.assertEqual((state['FLAG'], state['SMALL']), (True, -1))

    def test_converted_short_sentinel_is_private_missing_storage(self):
        state = execute('n=32767 put(n)', 'ROUTINE put(a: SHORT) BEGIN flag=UNINIT(a) a=12 seen=a END put')
        self.assertEqual((state['FLAG'], state['N'], state['SEEN']), (True, 32767, 12))

    def test_converted_short_sentinel_cannot_be_read_until_initialized(self):
        p, _ = program('n=32767 seen=7 put(n)', 'ROUTINE put(a: SHORT) BEGIN seen=a END put')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): p.run()
        self.assertEqual((p.snapshot()['SEEN'], p._state.call_depth, p._state.local_frames), (7, 0, []))

    def test_exact_short_output_reference_may_clear_the_caller(self):
        state = execute('small=3 clear(small) flag=UNINIT(small)', 'ROUTINE clear(a: SHORT) BEGIN a=32767 END clear')
        self.assertEqual((state['SMALL'], state['FLAG']), (MISSING, True))

    def test_locals_are_fresh_on_every_routine_call(self):
        state = execute('calls=0 put() put()', 'ROUTINE put VAR a: BYTE z: SHORT BEGIN IF UNINIT(z) THEN calls=calls+1 ENDIF a=2 z=3 END put')
        self.assertEqual(state['CALLS'], 2)

    def test_direct_and_named_result_types_are_checked_values(self):
        state = execute('b=make_byte() small=make_short() n=make_byte+make_short r=make_byte',
            'ROUTINE make_byte: octet BEGIN RETURN 255 END make_byte '
            'ROUTINE make_short: signed BEGIN RETURN -11 END make_short', prefix='TYPE octet=BYTE signed=SHORT')
        self.assertEqual((state['B'], state['SMALL'], state['N'], state['R']), (255, -11, 244, 255.0))

    def test_narrow_result_can_feed_a_private_matching_formal(self):
        state = execute('seen=0 put(make())',
            'ROUTINE make: BYTE BEGIN RETURN 7 END make ROUTINE put(a: BYTE) BEGIN a=a+1 seen=a END put')
        self.assertEqual(state['SEEN'], 8)

    def test_bad_narrow_return_preserves_assignment_and_unwinds(self):
        for kind, value, message in (('BYTE', 256, 'outside'), ('SHORT', -32769, 'outside'), ('SHORT', 32767, 'uninitialized')):
            with self.subTest(kind=kind, value=value):
                p, _ = program('n=9 seen=0 n=make()', f'ROUTINE make: {kind} BEGIN seen=1 RETURN {value} END make')
                with self.assertRaisesRegex(rt.KarelRuntimeError, message): p.run()
                self.assertEqual((p.snapshot()['N'], p.snapshot()['SEEN'], p._state.local_frames, p._state.call_depth), (9, 1, [], 0))

    def test_uninitialized_local_result_fails_at_return(self):
        for kind, message in (('BYTE', 'BYTE contents are unknown'), ('SHORT', 'uninitialized')):
            with self.subTest(kind=kind):
                p, _ = program('n=9 n=make()', f'ROUTINE make: {kind} VAR local: {kind} BEGIN RETURN local END make')
                with self.assertRaisesRegex(rt.KarelRuntimeError, message): p.run()
                self.assertEqual((p.snapshot()['N'], p._state.local_frames), (9, []))

    def test_real_or_boolean_actuals_do_not_silently_narrow(self):
        for kind in ('BYTE', 'SHORT'):
            for value in ('1.0', 'TRUE'):
                with self.subTest(kind=kind, value=value), self.assertRaises(TranslationError):
                    program(f'put({value})', f'ROUTINE put(a: {kind}) BEGIN END put')

    def test_linked_narrow_globals_and_routines_keep_exact_interfaces(self):
        project = translate_project({
            'lib.kl': source('LIB', '', decl='b: BYTE', routines='ROUTINE put(a: BYTE): SHORT BEGIN a=11 RETURN -2 END put'),
            'main.kl': source('MAIN', 'b=1 small=put(b)', decl='b FROM LIB: BYTE small: SHORT', routines='ROUTINE put(a: BYTE): SHORT FROM LIB')})
        instance = project.instantiate(); instance.run('MAIN')
        self.assertEqual((instance.programs['MAIN'].snapshot()['B'], instance.programs['MAIN'].snapshot()['SMALL'], instance.programs['LIB'].snapshot()['B']), (11, -2, 11))


class NarrowCounterAndBoundaryTests(unittest.TestCase):
    def test_integer_counter_is_private_when_converted_to_byte(self):
        state = execute('total=0 FOR n=1 TO 3 DO put(n) total=total+n ENDFOR flag=UNINIT(n)',
                        'ROUTINE put(a: BYTE) BEGIN a=100 END put')
        self.assertEqual((state['TOTAL'], state['FLAG'], state['N']), (6, True, MISSING))

    def test_transitive_converted_parameter_writes_do_not_escape(self):
        state = execute('total=0 FOR n=1 TO 3 DO relay(n) total=total+n ENDFOR flag=UNINIT(n)',
            'ROUTINE put(a: BYTE) BEGIN a=100 END put '
            'ROUTINE relay(a: INTEGER) BEGIN put(a) END relay')
        self.assertEqual((state['TOTAL'], state['FLAG'], state['N']), (6, True, MISSING))

    def test_real_global_counter_writes_still_reject(self):
        with self.assertRaises(TranslationError) as caught:
            program('FOR n=1 TO 3 DO put(n) ENDFOR', 'ROUTINE put(a: BYTE) BEGIN n=7 END put')
        self.assertEqual(caught.exception.code, 'E_FOR_COUNTER')

    def test_narrow_storage_cannot_be_a_for_counter(self):
        for name in ('b', 'small'):
            with self.subTest(name=name), self.assertRaises(TranslationError) as caught:
                program(f'FOR {name}=1 TO 3 DO ENDFOR')
            self.assertEqual(caught.exception.code, 'E_FOR_COUNTER')

    def test_narrow_values_are_valid_integer_for_bounds(self):
        state = execute('b=1 small=3 total=0 FOR n=b TO small DO total=total+n ENDFOR')
        self.assertEqual(state['TOTAL'], 6)

    def test_builtin_integer_output_refs_stay_exact(self):
        for name in ('b', 'small'):
            with self.subTest(name=name), self.assertRaises(TranslationError):
                program(f"CNV_STR_INT('7',{name})")

    def test_legacy_declaration_and_interface_guards_are_preserved(self):
        for kind in ('BYTE', 'SHORT'):
            for part in (f'VAR value:{kind}', f'ROUTINE work(p:{kind}) BEGIN END work', f'ROUTINE work:{kind} BEGIN RETURN 1 END work'):
                with self.subTest(kind=kind, part=part), self.assertRaises(TranslationError):
                    legacy_translate(f'PROGRAM T VAR n:INTEGER {part} BEGIN END T')

    def test_runtime_narrow_value_cells_are_pythonic_only(self):
        for kind, value in (('BYTE', 255), ('SHORT', -32768)):
            with self.subTest(kind=kind):
                with rt._numeric_scope('strict'), self.assertRaisesRegex(rt.KarelRuntimeError, 'Unsupported value-parameter'): rt.value_argument((kind,), value)
                with rt._numeric_scope('pythonic'): self.assertEqual(rt.value_argument((kind,), value).raw(), value)


class NarrowScalarServiceTests(unittest.TestCase):
    def test_text_file_scalar_fields_and_short_sentinel(self):
        ctx = rt.ExecutionContext(files=rt.MemoryFiles({'input': '255 -32768 32767\n'}))
        state = execute("OPEN FILE f('RO','input') READ f(b,small,short_other,CR) CLOSE FILE f flag=UNINIT(short_other)", context=ctx)
        self.assertEqual((state['B'], state['SMALL'], state['SHORT_OTHER'], state['FLAG']), (255, -32768, MISSING, True))

    def test_text_read_range_failure_preserves_all_targets_and_cursor(self):
        ctx = rt.ExecutionContext(files=rt.MemoryFiles({'input': '255 32768\n'}))
        p, _ = program("b=1 small=2 OPEN FILE f('RO','input') READ f(b,small)", context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'TextInput invalid SHORT'): p.run()
        self.assertEqual((p.snapshot()['B'], p.snapshot()['SMALL'], p.snapshot()['F']['position']), (1, 2, 0))

    def test_binary_scalar_fields_roundtrip_without_size_widening(self):
        files = rt.MemoryFiles(); ctx = rt.ExecutionContext(files=files)
        state = execute("b=255 small=-32768 OPEN FILE f('RWB','data') WRITE f(b,small) SET_FILE_POS(f,0,status) READ f(other,short_other) CLOSE FILE f", context=ctx)
        self.assertEqual((state['OTHER'], state['SHORT_OTHER'], files.snapshot()['data']), (255, -32768, b'\xff\x00\x80'))

    def test_binary_short_sentinel_publishes_atomically(self):
        ctx = rt.ExecutionContext(files=rt.MemoryFiles({'input': b'\xff\xff\x7f'}))
        state = execute("b=1 small=2 OPEN FILE f('RB','input') READ f(b,small) CLOSE FILE f flag=UNINIT(small)", context=ctx)
        self.assertEqual((state['B'], state['SMALL'], state['FLAG']), (255, MISSING, True))

    def test_binary_eof_preserves_earlier_narrow_target_and_cursor(self):
        ctx = rt.ExecutionContext(files=rt.MemoryFiles({'input': b'\xff\x00'}))
        p, _ = program("b=1 small=2 OPEN FILE f('RB','input') READ f(b,small)", context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['B'], p.snapshot()['SMALL'], p.snapshot()['F']['position']), (1, 2, 0))

    def test_binary_short_marker_is_not_published_before_later_invalid_field(self):
        ctx = rt.ExecutionContext(files=rt.MemoryFiles({'input': struct.pack('<hf', 32767, float('nan'))}))
        p, _ = program("small=2 r=3 OPEN FILE f('RB','input') READ f(small,r)", context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['SMALL'], p.snapshot()['R'], p.snapshot()['F']['position']), (2, 3.0, 0))

    def test_finite_pipe_binary_read_preserves_short_sentinel(self):
        bank = rt.FilePipes(); bank.configure('NARROW', False, 1, 0, '', 0)
        bank.feed('NARROW', b'\xff\xff\x7f')
        p, _ = program("OPEN FILE f('RB','PIP:NARROW') READ f(b,small) CLOSE FILE f flag=UNINIT(small)",
                       context=rt.ExecutionContext(file_pipes=bank))
        state = p.run()
        self.assertEqual((state['B'], state['SMALL'], state['FLAG']), (255, MISSING, True))

    def test_waiting_pipe_narrow_read_captures_once_and_publishes_together(self):
        bank = rt.FilePipes(); bank.configure('NARROW', False, 1, 0, '', 0)
        bank.feed('NARROW', b'\xff'); delays = []
        def sleeper(delay):
            delays.append(delay)
            self.assertEqual((p.snapshot()['B'], p.snapshot()['SMALL'], p.snapshot()['F']['position']), (1, 2, 0))
            self.assertEqual(p.read_requests, ())
            bank.feed('NARROW', b'\xff\x7f')
        p, _ = program("b=1 small=2 SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RB','PIP:NARROW') READ f(b,small) CLOSE FILE f flag=UNINIT(small)",
                       context=rt.ExecutionContext(file_pipes=bank), sleep=sleeper)
        state = p.run()
        self.assertEqual((state['B'], state['SMALL'], state['FLAG'], delays, len(p.read_requests), bank._reads),
                         (255, MISSING, True, [.01], 1, {}))

    def test_finite_serial_binary_read_preserves_short_sentinel(self):
        bank = rt.SerialStreams({2: {'input': b'\xff\xff\x7f'}})
        p, _ = program("OPEN FILE f('RB','P2:') READ f(b,small) CLOSE FILE f flag=UNINIT(small)",
                       context=rt.ExecutionContext(serial_streams=bank))
        state = p.run()
        self.assertEqual((state['B'], state['SMALL'], state['FLAG'], bank.snapshot()[2]['input']),
                         (255, MISSING, True, b''))

    def test_waiting_serial_narrow_read_captures_once_and_publishes_together(self):
        bank = rt.SerialStreams({2: {'input': b'\xff', 'wait': True}}); delays = []
        def sleeper(delay):
            delays.append(delay)
            self.assertEqual((p.snapshot()['B'], p.snapshot()['SMALL'], p.snapshot()['F']['position']), (1, 2, 0))
            self.assertEqual(p.read_requests, ())
            bank.feed(2, b'\xff\x7f')
        p, _ = program("b=1 small=2 OPEN FILE f('RB','P2:') READ f(b,small) CLOSE FILE f flag=UNINIT(small)",
                       context=rt.ExecutionContext(serial_streams=bank), sleep=sleeper)
        state = p.run()
        self.assertEqual((state['B'], state['SMALL'], state['FLAG'], delays, len(p.read_requests), bank._pending, bank.snapshot()[2]['input']),
                         (255, MISSING, True, [.01], 1, {}, b''))

    def test_waiting_serial_eof_keeps_narrow_targets_and_unconsumed_input(self):
        bank = rt.SerialStreams({2: {'input': b'\xff', 'wait': True, 'final': True}})
        p, _ = program("b=1 small=2 OPEN FILE f('RB','P2:') READ f(b,small)", context=rt.ExecutionContext(serial_streams=bank))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['B'], p.snapshot()['SMALL'], p.snapshot()['F']['position'], bank._pending), (1, 2, 0, {}))
        bank.close(p._state.values['F'])
        self.assertEqual(bank.snapshot()[2]['input'], b'\xff')

    def test_pipe_and_serial_late_invalid_binary_field_keep_marker_unpublished(self):
        raw = struct.pack('<hf', 32767, float('nan'))
        for backend in ('pipe', 'serial'):
            with self.subTest(backend=backend):
                if backend == 'pipe':
                    bank = rt.FilePipes(); bank.configure('NARROW', False, 1, 0, '', 0); bank.feed('NARROW', raw)
                    ctx = rt.ExecutionContext(file_pipes=bank); name = 'PIP:NARROW'
                else:
                    bank = rt.SerialStreams({2: {'input': raw, 'wait': True}})
                    ctx = rt.ExecutionContext(serial_streams=bank); name = 'P2:'
                p, _ = program(f"small=2 r=3 OPEN FILE f('RB','{name}') READ f(small,r)", context=ctx)
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual((p.snapshot()['SMALL'], p.snapshot()['R'], p.snapshot()['F']['position']), (2, 3.0, 0))
                self.assertEqual(bank._reads if backend == 'pipe' else bank._pending, {})
                bank.close(p._state.values['F'])
                if backend == 'serial': self.assertEqual(bank.snapshot()[2]['input'], raw)

    def test_get_and_set_var_use_narrow_global_domains(self):
        state = execute("b=7 small=-2 GET_VAR(entry,'','B',other,status) SET_VAR(entry,'','SMALL',b,status)")
        self.assertEqual((state['B'], state['OTHER'], state['SMALL'], state['STATUS']), (7, 7, 7, 0))

    def test_get_var_does_not_widen_narrow_output_reference(self):
        state = execute("b=7 n=42 GET_VAR(entry,'','B',n,status)")
        self.assertEqual((state['N'], state['STATUS']), (42, 3))

    def test_set_var_checked_integer_to_byte_preserves_target_on_range_error(self):
        p, _ = program("b=7 n=256 SET_VAR(entry,'','B',n,status)")
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'outside'): p.run()
        self.assertEqual(p.snapshot()['B'], 7)

    def test_variable_transfer_preserves_unknown_byte(self):
        state = execute("other=7 GET_VAR(entry,'','B',other,status)")
        self.assertEqual((state['OTHER'], state['STATUS']), (UNKNOWN, 0))

    def test_set_var_short_sentinel_is_missing_not_numeric(self):
        state = execute("small=7 n=32767 SET_VAR(entry,'','SMALL',n,status) flag=UNINIT(small)")
        self.assertEqual((state['SMALL'], state['FLAG'], state['STATUS']), (MISSING, True, 12311))

    def test_context_json_preserves_scalar_types_values_and_unknown_markers(self):
        p, result = program('b=255 small=-11')
        expected = p.run(); saved = json.loads(json.dumps(p._state.execution.to_config()))
        ctx = rt.ExecutionContext.from_config(saved)
        ns = {'__name__': 'restored_narrow_test'}; exec(result.python_source, ns)
        self.assertEqual(ns['Program'](context=ctx).snapshot(), expected)
        self.assertEqual(ctx.to_config(), saved)

    def test_explicit_typed_json_preserves_unknown_and_short_marker(self):
        for spec, value in ((('BYTE',), rt.UNKNOWN_BYTE), (('SHORT',), rt.UNINITIALIZED), (('BYTE',), 255), (('SHORT',), -32768)):
            with self.subTest(spec=spec, value=value):
                other_spec, other = decode_typed(json.loads(json.dumps(typed_value(value, spec))))
                self.assertEqual(other_spec, spec); self.assertEqual(rt.snapshot_value(other), rt.snapshot_value(value))


if __name__ == '__main__': unittest.main()
