"""Offline Messaging FILE progress, atomicity and lifetime regressions."""
import json
import struct
import unittest
from unittest.mock import patch

from karel2py import runtime as rt, translate_project
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source


DECL = 'f:FILE n,m,status:INTEGER a:ARRAY[2] OF INTEGER'
OPEN = "OPEN FILE f('RW','S1:') "
CLOSE = ' status=IO_STATUS(f) CLOSE FILE f'


def services(row, *, limit=32, others=None):
    bank = rt.Messaging({'S1:': dict(row, connected=True), **(others or {})}, limit=limit)
    return bank, rt.ExecutionContext(messaging=bank)


def build(body, context, **options):
    return compile_program(body, decl=DECL, context=context, **options)[0]


class SocketReadWaitTests(unittest.TestCase):
    def test_partial_text_does_not_publish_until_whole_request_is_ready(self):
        bank, ctx = services(dict(wait=True, input='1 '))
        calls = []

        def sleeper(seconds):
            calls.append(seconds)
            self.assertEqual((task.snapshot()['N'], task.snapshot()['M']), (77, 88))
            self.assertEqual(task._state.read_requests, [])
            bank.feed('s1:', '2\nleft\n')

        task = build('n=77 m=88 ' + OPEN + 'READ f(n,m,CR)' + CLOSE, ctx, sleep=sleeper)
        result = task.run()
        self.assertEqual((result['N'], result['M'], result['STATUS']), (1, 2, 0))
        self.assertEqual(calls, [.01])
        self.assertEqual(bank.files['S1:'], b'left\n')
        self.assertEqual(len(task._state.read_requests), 1)
        self.assertEqual(bank._pending, {})

    def test_binary_aggregate_wait_consumes_exact_prefix(self):
        bank, ctx = services(dict(wait=True, input=struct.pack('>i', 7)))
        def sleeper(_):
            bank.feed('S1:', struct.pack('>i', 9) + b'keep')
        task = build("SET_FILE_ATR(f,ATR_REVERSE) OPEN FILE f('RB','S1:') READ f(a)" + CLOSE,
                     ctx, sleep=sleeper)
        self.assertEqual(task.run()['A'], [7, 9])
        self.assertEqual(bank.files['S1:'], b'keep')

    def test_finish_input_completes_an_unterminated_text_token(self):
        bank, ctx = services(dict(wait=True, input='42'))
        task = build(OPEN + 'READ f(n)' + CLOSE, ctx, sleep=lambda _: bank.finish_input('S1:'))
        self.assertEqual(task.run()['N'], 42)
        self.assertEqual(bank.files['S1:'], b'')
        with self.assertRaisesRegex(ValueError, 'final'):
            bank.feed('S1:', '9')

    def test_final_short_binary_retains_values_and_rx(self):
        bank, ctx = services(dict(wait=True, final=True, input=struct.pack('<i', 7)))
        task = build("n=77 m=88 OPEN FILE f('RB','S1:') READ f(n,m)", ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'finalized socket'):
            task.run()
        handle = task._state.values['F']
        self.assertEqual((task.snapshot()['N'], task.snapshot()['M'], handle.position, handle.status),
                         (77, 88, 0, 1))
        self.assertEqual(bank.files['S1:'], struct.pack('<i', 7))
        self.assertEqual(bank._pending, {})
        bank.close(handle)

    def test_malformed_complete_field_fails_without_sleep(self):
        bank, ctx = services(dict(wait=True, input='1 wrong\n'))
        calls = []
        task = build('n=77 m=88 ' + OPEN + 'READ f(n,m,CR)', ctx, sleep=calls.append)
        with self.assertRaises(rt.KarelRuntimeError):
            task.run()
        self.assertEqual((task.snapshot()['N'], task.snapshot()['M']), (77, 88))
        self.assertEqual(bank.files['S1:'], b'1 wrong\n')
        self.assertEqual(calls, [])
        bank.close(task._state.values['F'])

    def test_cancel_wins_over_data_fed_in_same_step(self):
        bank, ctx = services(dict(wait=True))

        def sleeper(_):
            bank.feed('S1:', '17\n')
            handle = task._state.values['F']
            rt.cancel_file(task._state, handle)
            rt.cancel_file(task._state, handle)

        task = build('n=99 ' + OPEN + 'READ f(n,CR) status=IO_STATUS(f) READ f(m,CR) CLOSE FILE f',
                     ctx, sleep=sleeper)
        result = task.run()
        self.assertEqual((result['N'], result['M'], result['STATUS']), (99, 17, 6))
        self.assertEqual(bank.files['S1:'], b'')
        self.assertEqual(len(task._state.read_requests), 1)

    def test_oversized_binary_request_rejects_before_wait(self):
        bank, ctx = services(dict(wait=True), limit=7)
        calls = []
        task = build("OPEN FILE f('RB','S1:') READ f(a)", ctx, sleep=calls.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'receive bank limit'):
            task.run()
        self.assertEqual(calls, [])
        self.assertEqual(bank._pending, {})
        bank.close(task._state.values['F'])

    def test_fixed_fields_and_mandatory_record_separator_exceed_capacity(self):
        bank, ctx = services(dict(wait=True, input='123'), limit=3)
        calls = []
        task = build('n=77 ' + OPEN + 'READ f(n::3,CR,CR)', ctx, sleep=calls.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'receive bank limit'):
            task.run()
        handle = task._state.values['F']
        self.assertEqual((task.snapshot()['N'], handle.position, calls, task.read_requests, bank._pending),
                         (77, 0, [], (), {}))
        bank.close(handle)
        self.assertEqual(bank.files['S1:'], b'123')

    def test_finalization_supplies_last_cr_at_exact_capacity(self):
        bank, ctx = services(dict(wait=True, input='123'), limit=3)
        calls = []
        def sleeper(delay):
            calls.append(delay)
            bank.finish_input('S1:')
        task = build(OPEN + 'READ f(n::3,CR)' + CLOSE, ctx, sleep=sleeper)
        self.assertEqual((task.run()['N'], calls), (123, [.01]))


class SocketWriteWaitTests(unittest.TestCase):
    def test_aggregate_payload_is_captured_once_across_partial_drains(self):
        bank, ctx = services(dict(wait_output=True, output='old!'), limit=8)
        observations = []
        # Three retained RX bytes leave room for only five TX bytes.
        bank.feed('S1:', 'abc')

        def sleeper(_):
            observations.append(bytes(bank.ports['S1:']['output']))
            rt.index_reference(task._state.values['A'], 1).set(9)
            bank.take_output('S1:', 1)

        task = build('a[1]=1 a[2]=2 ' + OPEN + 'WRITE f(a::2)' + CLOSE, ctx, sleep=sleeper)
        self.assertEqual(task.run()['A'], [9, 2])
        self.assertEqual(observations, [b'old!', b'ld!', b'd!'])
        self.assertEqual(bank.take_output('S1:'), b'! 1 2')
        self.assertEqual(bank.files['S1:'], b'abc')

    def test_cancel_wins_when_host_also_drains_tx(self):
        bank, ctx = services(dict(wait_output=True, output='old'), limit=4)

        def sleeper(_):
            bank.take_output('S1:', 2)
            rt.cancel_file(task._state, task._state.values['F'])

        task = build(OPEN + "WRITE f('XY')" + CLOSE, ctx, sleep=sleeper)
        self.assertEqual(task.run()['STATUS'], 6)
        self.assertEqual(bank.take_output('S1:'), b'd')
        self.assertEqual(bank._pending, {})

    def test_wait_for_space_released_by_other_endpoint_read(self):
        bank, ctx = services(dict(wait_output=True, output='old'), limit=5,
                             others={'C1:': dict(connected=True, input='1\n')})
        linked = translate_project({
            'send': source('SEND', OPEN + "WRITE f('XY')" + CLOSE, decl=DECL),
            'recv': source('RECV', "DELAY 15 OPEN FILE f('RO','C1:') READ f(n,CR) CLOSE FILE f", decl=DECL),
        }).instantiate(context=ctx)
        linked.scheduler.start('SEND')
        linked.scheduler.start('RECV')
        linked.scheduler.run()
        self.assertEqual(linked.programs['SEND'].snapshot()['STATUS'], 0)
        self.assertEqual(linked.programs['RECV'].snapshot()['N'], 1)
        self.assertEqual(bank.take_output('S1:'), b'oldXY')
        self.assertEqual(bank.files['C1:'], b'')

    def test_impossible_payload_keeps_rx_and_never_calls_sleeper(self):
        bank, ctx = services(dict(wait_output=True, input='abc'), limit=4)
        calls = []
        task = build(OPEN + "WRITE f('XY')", ctx, sleep=calls.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'retained receive'):
            task.run()
        self.assertEqual(calls, [])
        self.assertEqual(bank.files['S1:'], b'abc')
        self.assertEqual(bank.take_output('S1:'), b'')
        bank.close(task._state.values['F'])


class SocketWaitLifetimeTests(unittest.TestCase):
    def test_incomplete_operations_require_explicit_sleeper(self):
        for body, row in [('READ f(n)', dict(wait=True)),
                          ("WRITE f('XY')", dict(wait_output=True, output='old'))]:
            with self.subTest(body=body):
                bank, ctx = services(row, limit=4)
                task = build(OPEN + body, ctx)
                with patch('karel2py.runtime.time.sleep') as sleep:
                    with self.assertRaisesRegex(rt.KarelRuntimeError, 'explicit sleeper'):
                        task.run()
                    sleep.assert_not_called()
                self.assertEqual(bank._pending, {})
                bank.close(task._state.values['F'])

    def test_connection_loss_is_terminal_even_if_reconnected_before_retry(self):
        for reconnect in (False, True):
            with self.subTest(reconnect=reconnect):
                bank, ctx = services(dict(wait=True, input='1'))

                def sleeper(_):
                    bank.set_available('S1:', False)
                    if reconnect:
                        bank.set_available('S1:', True)
                        self.assertEqual(bank.change('MSG_CONNECT', 'S1:'), 0)
                    bank.feed('S1:', '\n')

                task = build('n=77 ' + OPEN + 'READ f(n,CR)', ctx, sleep=sleeper)
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'disconnected|connection changed'):
                    task.run()
                self.assertEqual(task.snapshot()['N'], 77)
                self.assertEqual(bank.files['S1:'], b'1\n')
                self.assertEqual(bank._pending, {})
                bank.close(task._state.values['F'])

    def test_pending_file_blocks_close_seek_flush_and_direct_io(self):
        bank, ctx = services(dict(wait=True))

        def sleeper(_):
            handle = task._state.values['F']
            operations = [
                lambda: bank.close(handle),
                lambda: bank.flush(handle),
                lambda: bank.read_bytes(handle, 1),
                lambda: bank.write(handle, b'x'),
                lambda: ctx.invoke(task._state, 'SET_FILE_POS',
                                   [handle, 0, task._state.reference('STATUS')]),
            ]
            for operation in operations:
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'pending'):
                    operation()
            with self.assertRaisesRegex(ValueError, 'Close live messaging'):
                ctx.to_config()
            bank.feed('S1:', '8\n')

        task = build(OPEN + 'READ f(n,CR)' + CLOSE, ctx, sleep=sleeper)
        self.assertEqual(task.run()['N'], 8)

    def test_replacement_buffer_fails_without_appending_payload(self):
        bank, ctx = services(dict(wait_output=True, output='old'), limit=4)

        def sleeper(_):
            bank.ports['S1:']['output'] = bytearray(b'x')

        task = build(OPEN + "WRITE f('XY')", ctx, sleep=sleeper)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'buffer identity'):
            task.run()
        self.assertEqual(bank.take_output('S1:'), b'x')
        self.assertEqual(bank._pending, {})
        bank.close(task._state.values['F'])

    def test_stop_releases_pending_registration_and_preserves_rx(self):
        bank, ctx = services(dict(wait=True, input='1'))
        linked = translate_project({'main': source('MAIN', OPEN + 'READ f(n,CR)', decl=DECL)}).instantiate(context=ctx)
        linked.scheduler.start('MAIN')
        for _ in range(20):
            linked.scheduler.step()
            if bank._pending:
                break
        self.assertTrue(bank._pending)
        linked.scheduler.stop('MAIN')
        task = linked.programs['MAIN']
        self.assertEqual(bank._pending, {})
        self.assertEqual(bank.files['S1:'], b'1')
        self.assertIsNone(task._state.values['F']._read_operation)
        bank.close(task._state.values['F'])

    def test_paused_writer_keeps_its_bytes_until_cancel_and_resume(self):
        bank, ctx = services(dict(wait_output=True, output='old'), limit=4)
        body = ("pause_now=FALSE CONDITION[1]: WHEN pause_now DO PAUSE ENDCONDITION "
                "ENABLE CONDITION[1] " + OPEN + "WRITE f('XY')" + CLOSE)
        task, _ = compile_program(body, decl=DECL + ' pause_now:BOOLEAN', context=ctx,
                                  sleep=lambda _: task._state.set('PAUSE_NOW', True))
        with self.assertRaises(rt.KarelPause):
            task.run()
        handle = task._state.values['F']
        self.assertTrue(bank._pending)
        rt.cancel_file(task._state, handle)
        self.assertEqual(task.task_state, 'paused')
        self.assertEqual(task.resume()['STATUS'], 6)
        self.assertEqual(bank.take_output('S1:'), b'old')
        self.assertEqual(bank._pending, {})

    def test_direct_state_operations_keep_immediate_behavior(self):
        bank, ctx = services(dict(wait=True, wait_output=True, output='full'), limit=4)
        task = build(OPEN, ctx)
        task.run()
        state = task._state
        handle = state.values['F']
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'end of input'):
            state.file_read(handle, [state.reference('N')])
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'bank limit'):
            state.write_items(['x'], file=handle)
        self.assertEqual(bank._pending, {})
        bank.close(handle)

    def test_closed_json_roundtrip_preserves_enabled_flags_and_legacy_shape(self):
        bank, ctx = services(dict(wait=True, input='12', wait_output=True), others={'C1:': {}})
        bank.finish_input('S1:')
        config = json.loads(json.dumps(ctx.to_config()))
        self.assertEqual(rt.ExecutionContext.from_config(config).to_config(), config)
        self.assertTrue(config['messaging']['ports']['S1:']['final'])
        self.assertNotIn('wait', config['messaging']['ports']['C1:'])
        self.assertNotIn('wait_output', config['messaging']['ports']['C1:'])
        for row in (dict(wait=1), dict(final=False), dict(wait_output=1), dict(wait=True, final=1)):
            with self.subTest(row=row), self.assertRaises(ValueError):
                services(row)


if __name__ == '__main__':
    unittest.main()
