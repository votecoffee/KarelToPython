"""Execution budget and publication checks for translated FILE WRITE."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from karel2py import fileops, runtime as rt
from tests.test_extended_services import compile_program


FIELDS = ','.join(["'x'::254"] * 17)
PAYLOAD = (b'x' + b' ' * 253) * 17


def program(context, name, *, tail='', sleep=None):
    task, _ = compile_program(
        f"SET_FILE_ATR(f,ATR_EOL,59) OPEN FILE f('RW','{name}') WRITE f({FIELDS},CR) {tail}",
        decl='f:FILE s:INTEGER', context=context, sleep=sleep,
    )
    return task


def stream(kind, *, waiting, output=b'old', capacity=8192):
    if kind == 'socket':
        name = 'S1:'
        bank = rt.Messaging(
            {name: {'connected': True, 'output': output, 'wait_output': waiting}},
            limit=capacity,
        )
        return rt.ExecutionContext(messaging=bank), name, bank.ports[name], bank._pending
    bank = rt.SerialStreams(
        {2: {'capacity': capacity, 'output': output, 'wait_output': waiting}},
        limit=capacity,
    )
    return rt.ExecutionContext(serial_streams=bank), 'P2:', bank.ports[2], bank._writes


class FileWriteBudgetTests(unittest.TestCase):
    def assert_budget_failure(self, task, get_output, original):
        charge = fileops.charge_file_bytes
        charged = []

        def limit(size, check):
            if size != len(PAYLOAD) + 1:
                return charge(size, check)
            state = task._state
            state.max_steps = state.steps + 1

            def verify():
                self.assertEqual(get_output(), original)
                charged.append(size)
                check()

            charge(size, verify)

        with patch.object(fileops, 'charge_file_bytes', side_effect=limit):
            with self.assertRaisesRegex(rt.KarelRuntimeError, 'Execution step budget exceeded'):
                task.run()
        self.assertEqual(charged, [len(PAYLOAD) + 1] * 2)
        handle = task._state.values['F']
        self.assertEqual(handle.position, 0)
        self.assertIsNone(handle._write_operation)
        self.assertEqual(get_output(), original)

    def test_budget_exhaustion_preserves_memory_disk_and_circular_pipe(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original = b'original'
            disk_file = root / 'data'
            disk_file.write_bytes(original)
            disk = rt.DirectoryFiles(root)
            memory = rt.MemoryFiles({'data': original})
            pipes = rt.FilePipes()
            self.assertEqual(pipes.configure('LOG', False, 8, 0, '', 0), 0)
            pipes.feed('LOG', original)
            for bank, name, context in (
                (memory, 'data', rt.ExecutionContext(files=memory)),
                (disk, 'data', rt.ExecutionContext(files=disk)),
                (pipes, 'PIP:LOG', rt.ExecutionContext(file_pipes=pipes)),
            ):
                with self.subTest(backend=type(bank).__name__):
                    task = program(context, name)
                    self.assert_budget_failure(task, lambda: bank.files[name], original)
                    self.assertEqual(bank.files[name], original)
                    self.assertEqual(disk_file.read_bytes(), original)

    def test_budget_exhaustion_preserves_immediate_and_waiting_tx(self):
        for kind in ('socket', 'serial'):
            for waiting in (False, True):
                with self.subTest(kind=kind, waiting=waiting):
                    context, name, row, pending = stream(kind, waiting=waiting)
                    task = program(context, name)
                    self.assert_budget_failure(task, lambda: row['output'], b'old')
                    self.assertEqual(pending, {})

    def test_waits_reuse_one_charge_and_one_render(self):
        for kind in ('socket', 'serial'):
            with self.subTest(kind=kind):
                context, name, row, pending = stream(kind, waiting=True, output=b'z' * 4500)
                expected = len(PAYLOAD) + 1
                waits = []

                def sleep(seconds):
                    waits.append(seconds)
                    self.assertEqual([call.args[0] for call in charged.call_args_list], [expected])
                    if len(waits) == 2:
                        if kind == 'socket':
                            context.messaging.take_output(name)
                        else:
                            context.serial_streams.take_output(2)

                task = program(context, name, sleep=sleep)
                with patch.object(fileops, 'charge_file_bytes', wraps=fileops.charge_file_bytes) as charged:
                    task.run()
                self.assertEqual([call.args[0] for call in charged.call_args_list], [expected])
                self.assertEqual(waits, [.01, .01])
                self.assertEqual(row['output'], PAYLOAD + b';')
                self.assertEqual(pending, {})

    def test_cancellation_during_accounting_keeps_existing_tx(self):
        for kind in ('socket', 'serial'):
            with self.subTest(kind=kind):
                context, name, row, pending = stream(kind, waiting=True)
                task = program(context, name, tail="s=IO_STATUS(f) WRITE f('ok')")
                charge = fileops.charge_file_bytes

                def cancel(size, check):
                    if size == len(PAYLOAD) + 1:
                        self.assertTrue(pending)
                        rt.cancel_file(task._state, task._state.values['F'])
                    charge(size, check)

                with patch.object(fileops, 'charge_file_bytes', side_effect=cancel):
                    self.assertEqual(task.run()['S'], 6)
                self.assertEqual(row['output'], b'oldok')
                self.assertEqual(pending, {})
                self.assertIsNone(task._state.values['F']._write_operation)

    def test_direct_state_preserves_contiguous_bytes_like_fields(self):
        bank = rt.MemoryFiles()
        handle = rt.FileHandle()
        bank.open(handle, 'WB', 'data')
        state = rt.State({}, {})
        state.write_items([bytearray(b'one'), memoryview(b'two')], file=handle)
        self.assertEqual(bank.files['data'], b'onetwo')
        self.assertEqual(handle.position, 6)

    def test_replaced_destination_during_accounting_is_not_written(self):
        bank = rt.MemoryFiles({'data': b'original'})
        original = bank.files['data']
        replacement = bytearray(b'replacement')
        task = program(rt.ExecutionContext(files=bank), 'data')
        charge = fileops.charge_file_bytes

        def replace(size, check):
            bank.files['data'] = replacement
            charge(size, check)

        with patch.object(fileops, 'charge_file_bytes', side_effect=replace):
            with self.assertRaisesRegex(rt.KarelRuntimeError, 'destination or cursor changed'):
                task.run()
        self.assertIs(bank.files['data'], replacement)
        self.assertEqual(replacement, b'replacement')
        self.assertEqual(original, b'original')
        self.assertEqual(task._state.values['F'].position, 0)


if __name__ == '__main__':
    unittest.main()
