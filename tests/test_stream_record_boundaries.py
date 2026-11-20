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


class PassallStreamTests(unittest.TestCase):
    attributes = 'SET_FILE_ATR(f,ATR_PASSALL)'

    def test_fixed_width_and_explicit_cr_on_finite_and_waiting_transports(self):
        for transport in TRANSPORTS:
            for waiting in (False, True):
                with self.subTest(transport=transport, waiting=waiting):
                    task, bank, name, pending, _, _ = stream(
                        transport, b'a\n\x00b2Ajunk;tail',
                        'READ f(first::4,n::2::16,CR) status=IO_STATUS(f)',
                        waiting=waiting, attributes=self.attributes + ' SET_FILE_ATR(f,ATR_EOL,59)',
                    )
                    result = task.run()
                    self.assertEqual((result['FIRST'], result['N'], result['STATUS']), ('a\n\x00b', 42, 0))
                    handle = task._state.values['F']
                    self.assertEqual(bank.files[name][handle.position:], b'tail')
                    self.assertEqual(pending, {})
                    bank.close(handle)

    def test_raw_cr_leaves_following_lf_for_fixed_field(self):
        for transport in TRANSPORTS:
            with self.subTest(transport=transport):
                task, _, _, _, _, _ = stream(
                    transport, b'discard\r\nx', 'READ f(CR) READ f(first::2) CLOSE FILE f',
                    waiting=True, attributes=self.attributes + ' SET_FILE_ATR(f,ATR_EOL,13)',
                )
                self.assertEqual(task.run()['FIRST'], '\nx')

    def test_fragmented_fixed_field_waits_for_explicit_cr(self):
        for transport in ('socket', 'pipe'):
            with self.subTest(transport=transport):
                chunks = iter((b'\x00', b'skip\n'))
                observations = []

                def sleep(_):
                    observations.append((task.snapshot()['FIRST'], task.snapshot()['F']['position']))
                    feed(next(chunks))

                task, _, _, pending, feed, _ = stream(
                    transport, b'\n', 'READ f(first::2,CR) CLOSE FILE f',
                    attributes=self.attributes, sleep=sleep,
                )
                self.assertEqual(task.run()['FIRST'], '\n\x00')
                self.assertEqual(observations, [('old', 0), ('old', 0)])
                self.assertEqual(len(task.read_requests), 1)
                self.assertEqual(pending, {})

    def test_cancel_after_feed_preserves_all_raw_bytes(self):
        for transport in ('socket', 'pipe'):
            with self.subTest(transport=transport):
                def sleep(_):
                    feed(b'b')
                    rt.cancel_file(task._state, task._state.values['F'])

                task, bank, name, pending, feed, _ = stream(
                    transport, b'a\n', 'READ f(first::3) status=IO_STATUS(f) CLOSE FILE f',
                    attributes=self.attributes, sleep=sleep,
                )
                values = task.run()
                self.assertEqual((values['FIRST'], values['STATUS'], task.read_requests), ('old', 6, ()))
                self.assertEqual(bank.files[name], b'a\nb')
                self.assertEqual(pending, {})

    def test_finite_failure_retains_destinations_and_buffer(self):
        for transport in ('socket', 'pipe'):
            for statement, data, reason in (
                ('READ f(first::2,n::2)', b'a\nno', 'invalid INTEGER'),
                ('READ f(first::2,CR)', b'a\n', 'complete PASSALL READ'),
            ):
                with self.subTest(transport=transport, statement=statement):
                    task, bank, name, _, _, _ = stream(
                        transport, data, 'n=77 ' + statement,
                        attributes=self.attributes, waiting=False,
                    )
                    with self.assertRaisesRegex(rt.KarelRuntimeError, reason):
                        task.run()
                    result = task.snapshot()
                    self.assertEqual((result['FIRST'], result['N'], result['F']['position']), ('old', 77, 0))
                    self.assertEqual(bank.files[name], data)
                    bank.close(task._state.values['F'])


class StreamReadDeadlineTests(unittest.TestCase):
    def test_raw_timeout_preserves_starting_state_and_can_retry(self):
        for transport in TRANSPORTS:
            with self.subTest(transport=transport):
                delays = []
                task, bank, name, pending, _, _ = stream(
                    transport, b'a\n',
                    'READ f(first::3) status=IO_STATUS(f) n=GET_FILE_POS(f) '
                    'READ f(second::2) CLOSE FILE f',
                    attributes='SET_FILE_ATR(f,ATR_PASSALL) SET_FILE_ATR(f,ATR_TIMEOUT,13)',
                    sleep=delays.append,
                )
                values = task.run()
                self.assertEqual((values['FIRST'], values['STATUS'], values['N']), ('old', 4, 0))
                self.assertEqual(values['SECOND'], 'a\n')
                self.assertEqual(delays, [.01, .003])
                self.assertEqual(len(task.read_requests), 1)
                self.assertEqual(pending, {})
                self.assertEqual(bank.files[name], b'a\n' if transport == 'pipe' else b'')

    def test_data_on_final_poll_succeeds_unless_cancellation_also_requested(self):
        for transport in TRANSPORTS:
            for cancel in (False, True):
                with self.subTest(transport=transport, cancel=cancel):
                    delays = []

                    def sleep(delay):
                        delays.append(delay)
                        feed(b'\n')
                        if cancel:
                            rt.cancel_file(task._state, task._state.values['F'])

                    task, _, _, pending, feed, _ = stream(
                        transport, b'17', 'READ f(n,CR) status=IO_STATUS(f) CLOSE FILE f',
                        attributes='SET_FILE_ATR(f,ATR_TIMEOUT,3)',
                        sleep=sleep,
                    )
                    values = task.run()
                    self.assertEqual(values['STATUS'], 6 if cancel else 0)
                    if not cancel:
                        self.assertEqual(values['N'], 17)
                    self.assertEqual(len(task.read_requests), 0 if cancel else 1)
                    self.assertEqual(delays, [.003])
                    self.assertEqual(pending, {})

    def test_scheduler_deadline_uses_virtual_time_and_releases_handle(self):
        for transport in ('pipe', 'socket'):
            with self.subTest(transport=transport):
                task, _, _, pending, _, _ = stream(
                    transport, b'1', 'n=77 READ f(n,CR) status=IO_STATUS(f) CLOSE FILE f',
                    attributes='SET_FILE_ATR(f,ATR_TIMEOUT,13)',
                    sleep=lambda _: self.fail('Scheduled waits must use the virtual clock'),
                )
                scheduler = rt.TaskScheduler()
                scheduler.bind('T', task)
                scheduler.start('T')
                for _ in range(25):
                    scheduler.step()
                    if pending:
                        break
                else:
                    self.fail('Timed READ did not wait')
                wait_started = scheduler.now_us
                scheduler.run()
                values = task.snapshot()
                self.assertEqual((values['N'], values['STATUS'], values['F']['open']), (77, 4, False))
                self.assertGreaterEqual(scheduler.now_us - wait_started, 12_000)
                self.assertEqual(pending, {})


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
