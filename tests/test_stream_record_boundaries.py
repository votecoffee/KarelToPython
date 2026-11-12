"""Authored fragmented record transfers through translated FILE instructions."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from karel2py import fileops, runtime as rt
from tests.test_extended_services import compile_program


TRANSPORTS = ('socket', 'serial', 'pipe')


def stream(transport, data, body, *, sleep=None, waiting=True, attributes='', capacity=8192):
    if transport == 'socket':
        name = 'S1:'
        bank = rt.Messaging({name: dict(input=data, wait=waiting, connected=True)}, limit=capacity)
        context = rt.ExecutionContext(messaging=bank)
        pending = bank._pending
    elif transport == 'serial':
        name = 'P2:'
        bank = rt.SerialStreams({2: dict(input=data, wait=waiting, capacity=capacity)}, limit=capacity)
        context = rt.ExecutionContext(serial_streams=bank)
        pending = bank._pending
    else:
        name = 'PIP:LOG'
        bank = rt.FilePipes()
        bank.configure(name, False, capacity // 1024, 0, '', 0)
        bank.feed(name, data)
        context = rt.ExecutionContext(file_pipes=bank)
        pending = bank._reads
        if waiting:
            attributes += ' SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED)'
    opening = f"OPEN FILE f('RO','{name}')"
    body = body.replace('@OPEN', opening)
    task, translation = compile_program(
        f"first='old' second='old' {attributes} {opening} {body}",
        decl='f:FILE first,second:STRING[32] n,status:INTEGER', context=context, sleep=sleep,
    )

    def feed(payload):
        bank.feed(2 if transport == 'serial' else name, payload)

    return task, bank, name, pending, feed, translation


class StreamRecordBoundaryTests(unittest.TestCase):
    def test_closed_rooted_file_releases_record_continuation(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'input.txt').write_bytes(b'discard\r')
            bank = rt.DirectoryFiles(directory)
            task, _ = compile_program(
                "OPEN FILE f('RO','input.txt') READ f(CR) CLOSE FILE f",
                decl='f:FILE', context=rt.ExecutionContext(files=bank),
            )
            task.run()
            handle = task._state.values['F']
            self.assertIsNone(handle.owner)
            self.assertIsNone(handle._text_cr)

    def test_crlf_split_across_successful_requests(self):
        for transport in TRANSPORTS:
            with self.subTest(transport=transport):
                parts = iter((b'\nnext\r', b'\ntail\r\n'))
                task, bank, name, pending, feed, _ = stream(
                    transport, b'discard\r', 'READ f(CR) READ f(first,CR) READ f(second,CR)',
                    sleep=lambda _: feed(next(parts)),
                )
                values = task.run()
                self.assertEqual((values['FIRST'], values['SECOND']), ('next', 'tail'))
                self.assertEqual(len(task.read_requests), 3)
                handle = task._state.values['F']
                self.assertEqual(bank.files[name][handle.position:], b'')
                self.assertEqual(pending, {})

    def test_only_one_optional_lf_is_absorbed(self):
        for transport in TRANSPORTS:
            for suffix, expected in ((b'next\n', 'next'), (b'\n\nnext\n', ''), (b'\rnext\n', '')):
                with self.subTest(transport=transport, suffix=suffix):
                    task, _, _, _, feed, _ = stream(
                        transport, b'discard\r', 'READ f(CR) READ f(first,CR)',
                        sleep=lambda _: feed(suffix),
                    )
                    self.assertEqual(task.run()['FIRST'], expected)

    def test_lf_only_fragment_waits_without_publishing(self):
        for transport in TRANSPORTS:
            with self.subTest(transport=transport):
                waits = []

                def sleep(seconds):
                    waits.append(seconds)
                    self.assertEqual(task.snapshot()['FIRST'], 'old')
                    self.assertEqual(len(task.read_requests), 1)
                    feed(b'\n' if len(waits) == 1 else b'next\n')

                task, _, _, pending, feed, _ = stream(
                    transport, b'discard\r', 'READ f(CR) READ f(first,CR)', sleep=sleep,
                )
                self.assertEqual(task.run()['FIRST'], 'next')
                self.assertEqual(waits, [.01, .01])
                self.assertEqual(pending, {})

    def test_complete_crlf_and_lone_cr_remain_immediate(self):
        for transport in TRANSPORTS:
            for data in (b'one\r\ntwo\r\n', b'one\rtwo\r'):
                with self.subTest(transport=transport, data=data):
                    task, _, _, _, _, _ = stream(
                        transport, data, 'READ f(first,CR) READ f(second,CR)',
                        sleep=lambda _: self.fail('Complete records must not wait'),
                    )
                    values = task.run()
                    self.assertEqual((values['FIRST'], values['SECOND']), ('one', 'two'))

    def test_fixed_width_and_quoted_fields_after_fragmented_crlf(self):
        for transport in TRANSPORTS:
            for fields, data, expected in (
                ('first::3', b'\nabc', 'abc'),
                ('first::0::2', b"\n'it''s ready'", "it's ready"),
            ):
                with self.subTest(transport=transport, fields=fields):
                    task, _, _, _, feed, _ = stream(
                        transport, b'discard\r', f'READ f(CR) READ f({fields})',
                        sleep=lambda _: feed(data),
                    )
                    self.assertEqual(task.run()['FIRST'], expected)

    def test_finite_read_can_continue_after_host_append(self):
        for transport in TRANSPORTS:
            with self.subTest(transport=transport):
                task, _, _, _, feed, _ = stream(
                    transport, b'discard\r', 'READ f(CR) DELAY 10 READ f(first,CR)',
                    sleep=lambda _: feed(b'\nnext\r\n'), waiting=False,
                )
                self.assertEqual(task.run()['FIRST'], 'next')

    def test_custom_eol_preserves_lf_as_data(self):
        for transport in TRANSPORTS:
            with self.subTest(transport=transport):
                task, _, _, _, _, _ = stream(
                    transport, b'discard;\nabc;', 'READ f(CR) READ f(first,CR)',
                    attributes='SET_FILE_ATR(f,ATR_EOL,59)',
                )
                self.assertEqual(task.run()['FIRST'], '\nabc')

    def test_cancel_during_accounting_retains_optional_lf(self):
        for transport in TRANSPORTS:
            with self.subTest(transport=transport):
                task, bank, name, pending, feed, _ = stream(
                    transport, b'discard\r', 'READ f(CR) READ f(first,CR)',
                    sleep=lambda _: feed(b'\nnext\n'),
                )
                charge = fileops.charge_file_bytes

                def cancel(size, check):
                    charge(size, check)
                    if len(task.read_requests) == 1 and size:
                        rt.cancel_file(task._state, task._state.values['F'])

                with patch.object(fileops, 'charge_file_bytes', side_effect=cancel):
                    values = task.run()
                handle = task._state.values['F']
                self.assertEqual((values['FIRST'], handle.status), ('old', 6))
                self.assertEqual(bank.files[name][handle.position:], b'\nnext\n')
                self.assertTrue(handle._text_cr_pending())
                self.assertEqual(pending, {})
                self.assertIsNone(handle._read_operation)

    def test_invalid_field_after_optional_lf_retains_cursor(self):
        for transport in TRANSPORTS:
            with self.subTest(transport=transport):
                task, bank, name, pending, feed, _ = stream(
                    transport, b'discard\r', 'READ f(CR) READ f(n,CR)',
                    sleep=lambda _: feed(b'\ninvalid\n'),
                )
                with self.assertRaises(rt.KarelRuntimeError):
                    task.run()
                handle = task._state.values['F']
                self.assertEqual(bank.files[name][handle.position:], b'\ninvalid\n')
                self.assertEqual(pending, {})

    def test_final_lf_completes_old_separator_without_creating_record(self):
        for transport in ('socket', 'serial'):
            with self.subTest(transport=transport):
                def finish(_):
                    feed(b'\n')
                    bank.finish_input(2 if transport == 'serial' else name)

                task, bank, name, pending, feed, _ = stream(
                    transport, b'discard\r', 'READ f(CR) READ f(first,CR)', sleep=finish,
                )
                with self.assertRaises(rt.KarelRuntimeError):
                    task.run()
                handle = task._state.values['F']
                self.assertEqual(task.snapshot()['FIRST'], 'old')
                self.assertEqual(bank.files[name][handle.position:], b'\n')
                self.assertEqual(pending, {})

    def test_binary_reopen_keeps_lf_as_byte_data(self):
        for transport in ('socket', 'serial'):
            with self.subTest(transport=transport):
                task, _, name, _, feed, _ = stream(
                    transport, b'discard\r',
                    "READ f(CR) DELAY 10 CLOSE FILE f OPEN FILE f('RB','@NAME') READ f(n::1)".replace(
                        '@NAME', 'S1:' if transport == 'socket' else 'P2:'),
                    sleep=lambda _: feed(b'\n'),
                )
                self.assertEqual(task.run()['N'], 10)

    def test_successful_seek_resets_continuation(self):
        for transport in TRANSPORTS:
            with self.subTest(transport=transport):
                task, _, _, _, feed, _ = stream(
                    transport, b'discard\r',
                    'READ f(CR) DELAY 10 SET_FILE_POS(f,GET_FILE_POS(f),status) READ f(first,CR)',
                    sleep=lambda _: feed(b'\nnext\n'),
                )
                values = task.run()
                self.assertEqual((values['FIRST'], values['STATUS']), ('next', 2) if transport == 'serial' else ('', 0))

    def test_reopen_does_not_inherit_continuation(self):
        for transport in ('socket', 'serial'):
            with self.subTest(transport=transport):
                task, _, _, _, feed, _ = stream(
                    transport, b'discard\r', 'READ f(CR) DELAY 10 CLOSE FILE f @OPEN READ f(first,CR)',
                    sleep=lambda _: feed(b'\nnext\n'),
                )
                self.assertEqual(task.run()['FIRST'], '')

    def test_pipe_discards_consumed_history_without_losing_crlf_pair(self):
        task, _, _, _, feed, _ = stream(
            'pipe', b'discard\r', 'READ f(CR) READ f(first::3)', capacity=1024,
            sleep=lambda _: feed(b'\nabc' + b' ' * 1020),
        )
        self.assertEqual(task.run()['FIRST'], 'abc')

    def test_pipe_lost_input_resets_continuation(self):
        task, _, _, _, feed, _ = stream(
            'pipe', b'discard\r', 'READ f(CR) READ f(first,CR) READ f(second,CR)', capacity=1024,
            attributes='SET_FILE_ATR(f,ATR_PIPOVADV,0)',
            sleep=lambda _: feed(b'x\nabc\r' + b' ' * 1019),
        )
        values = task.run()
        self.assertEqual((values['FIRST'], values['SECOND']), ('', 'abc'))


if __name__ == '__main__':
    unittest.main()
