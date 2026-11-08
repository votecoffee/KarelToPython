"""Byte-accounting regressions through translated cooperative FILE READ."""
import struct
import unittest
from unittest.mock import patch

from karel2py import fileops, runtime as rt
from karel2py.communications import StreamRead
from tests.test_extended_services import compile_program


TRANSPORTS = ('socket', 'serial', 'pipe')


def open_case(transport, data, *, binary=False, sleep=None):
    if transport == 'socket':
        name = 'S1:'
        bank = rt.Messaging({name: {'input': data, 'wait': True, 'connected': True}}, limit=8192)
        context = rt.ExecutionContext(messaging=bank)
        prefix = ''
        pending = bank._pending
    elif transport == 'serial':
        name = 'P2:'
        bank = rt.SerialStreams({2: {'capacity': 8192, 'input': data, 'wait': True}}, limit=8192)
        context = rt.ExecutionContext(serial_streams=bank)
        prefix = ''
        pending = bank._pending
    else:
        name = 'PIP:LOG'
        bank = rt.FilePipes()
        bank.configure(name, False, 8, 0, '', 0)
        bank.feed(name, data)
        context = rt.ExecutionContext(file_pipes=bank)
        prefix = 'SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) '
        pending = bank._reads
    mode, fields = ('RB', 'n') if binary else ('RO', 'n,CR')
    task, _ = compile_program(
        f"n=99 {prefix}OPEN FILE f('{mode}','{name}') READ f({fields})",
        decl='f:FILE n:INTEGER', context=context, sleep=sleep,
    )

    def feed(payload):
        bank.feed(2 if transport == 'serial' else name, payload)

    return task, bank.files[name], pending, feed


class StreamReadBudgetTests(unittest.TestCase):
    def assert_unpublished(self, task, pending, *, status):
        handle = task._state.values['F']
        self.assertEqual((task.snapshot()['N'], handle.position, handle.status), (99, 0, status))
        self.assertEqual(task._state.read_requests, [])
        self.assertEqual(pending, {})
        self.assertIsNone(handle._read_operation)

    def test_binary_wait_only_accounts_for_complete_requested_prefix(self):
        for transport in TRANSPORTS:
            with self.subTest(transport=transport):
                field = struct.pack('<i', 42)
                suffix = b'x' * 4096
                waits = []
                captured = []
                probe = StreamRead.probe

                def observe(request, handle, raw, *, final):
                    captured.append(len(raw))
                    return probe(request, handle, raw, final=final)

                def sleep(seconds):
                    waits.append(seconds)
                    self.assertEqual(charge.call_count, 0)
                    feed(field[1:] + suffix)

                task, retained, pending, feed = open_case(transport, field[:1], binary=True, sleep=sleep)
                with (
                    patch.object(fileops, 'charge_file_bytes', wraps=fileops.charge_file_bytes) as charge,
                    patch.object(StreamRead, 'probe', new=observe),
                ):
                    self.assertEqual(task.run()['N'], 42)
                self.assertEqual([call.args[0] for call in charge.call_args_list], [4])
                self.assertEqual(captured, [0, 4])
                handle = task._state.values['F']
                self.assertEqual(retained[handle.position:], suffix)
                self.assertEqual(waits, [.01])
                self.assertEqual(pending, {})

    def test_text_budget_is_charged_before_probe(self):
        data = b'17\n' + b' ' * 4096
        for transport in TRANSPORTS:
            with self.subTest(transport=transport):
                task, retained, pending, _ = open_case(transport, data)
                tick = task._state.tick
                charged = []

                def limited_tick(*args, **kwargs):
                    if pending:
                        charged.append(1)
                        if len(charged) == 1:
                            task._state.max_steps = task._state.steps + 1
                    return tick(*args, **kwargs)

                with patch.object(task._state, 'tick', side_effect=limited_tick), patch.object(StreamRead, 'probe') as probe:
                    with self.assertRaisesRegex(rt.KarelRuntimeError, 'Execution step budget exceeded'):
                        task.run()
                    probe.assert_not_called()
                self.assertEqual(len(charged), 2)
                self.assertEqual(retained, data)
                self.assert_unpublished(task, pending, status=1)

    def test_cancel_during_accounting_preserves_input(self):
        for transport in TRANSPORTS:
            with self.subTest(transport=transport):
                task, retained, pending, _ = open_case(transport, b'17\n')
                charge = fileops.charge_file_bytes

                def cancel(size, check):
                    charge(size, check)
                    rt.cancel_file(task._state, task._state.values['F'])

                with patch.object(fileops, 'charge_file_bytes', side_effect=cancel):
                    task.run()
                self.assertEqual(retained, b'17\n')
                self.assert_unpublished(task, pending, status=6)

    def test_append_during_accounting_rejects_changed_input_extent(self):
        for transport in TRANSPORTS:
            with self.subTest(transport=transport):
                task, retained, pending, feed = open_case(transport, b'17\n')
                charge = fileops.charge_file_bytes

                def append(size, check):
                    charge(size, check)
                    feed(b'18\n')

                with patch.object(fileops, 'charge_file_bytes', side_effect=append):
                    with self.assertRaisesRegex(rt.KarelRuntimeError, 'changed during byte accounting'):
                        task.run()
                self.assertEqual(retained, b'17\n18\n')
                self.assert_unpublished(task, pending, status=1)


if __name__ == '__main__':
    unittest.main()
