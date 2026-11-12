"""Authored persistent serial readers with bounded reclaimed receive storage."""
import json
from itertools import product
import struct
import unittest
from unittest.mock import patch

from karel2py import fileops, runtime as rt
from tests.test_extended_services import compile_program
from tests.test_serial_waits import pending_project


DECL = 'f:FILE n,m,i,total,cursor,status:INTEGER first,second:STRING[32]'


def streams(data=b'', *, waiting=False, capacity=8192, **fields):
    bank = rt.SerialStreams({2: dict(input=data, capacity=capacity, wait=waiting,
                                   reclaim_input=True, **fields)}, limit=capacity)
    return bank, rt.ExecutionContext(serial_streams=bank)


def program(body, *, context, binary=False, **options):
    mode = 'RWB' if binary else 'RW'
    return compile_program(f"OPEN FILE f('{mode}','P2:') {body}", decl=DECL, context=context, **options)[0]


class SerialInputReclamationTests(unittest.TestCase):
    def test_repeated_reads_exceed_total_capacity_without_reopening(self):
        for waiting in (False, True):
            with self.subTest(waiting=waiting):
                bank, context = streams(b'1\n', waiting=waiting, capacity=2)
                chunks = iter((b'2\n', b'3\n', b'4\n', b'5\n'))
                calls = []

                def feed(seconds):
                    calls.append(seconds)
                    self.assertEqual(bank.snapshot()[2]['input'], b'')
                    bank.feed(2, next(chunks))

                delay = '' if waiting else 'IF i<5 THEN DELAY 10 ENDIF'
                task = program(
                    f'total=0 FOR i=1 TO 5 DO READ f(n,CR) total=total+n {delay} ENDFOR '
                    'cursor=GET_FILE_POS(f) CLOSE FILE f', context=context, sleep=feed,
                )
                values = task.run()
                self.assertEqual((values['TOTAL'], values['CURSOR']), (15, 0))
                self.assertEqual(calls, [.01] * 4)
                self.assertEqual(len(task.read_requests), 5)
                self.assertEqual((bank.used(), bank._pending, bank._open), (0, {}, {}))

    def test_preserves_unread_suffix_and_reuses_receive_space(self):
        for waiting in (False, True):
            with self.subTest(waiting=waiting):
                bank, context = streams(b'1\n2\n', waiting=waiting, capacity=4)

                def feed(_):
                    self.assertEqual(bank.snapshot()[2]['input'], b'2\n')
                    bank.feed(2, b'3\n')

                task = program('READ f(n,CR) DELAY 10 READ f(m,CR) READ f(total,CR) CLOSE FILE f',
                               context=context, sleep=feed)
                values = task.run()
                self.assertEqual((values['N'], values['M'], values['TOTAL']), (1, 2, 3))
                self.assertEqual(bank.used(), 0)

    def test_reclaimed_receive_space_is_available_to_output(self):
        for waiting in (False, True):
            with self.subTest(waiting=waiting):
                bank, context = streams(b'7\nx', waiting=waiting, capacity=4, output=b'!', wait_output=True)
                task = program("READ f(n,CR) WRITE f('ok') CLOSE FILE f", context=context,
                               sleep=lambda _: self.fail('Complete input and reclaimed output space are ready'))
                self.assertEqual(task.run()['N'], 7)
                self.assertEqual((bank.snapshot()[2]['input'], bank.snapshot()[2]['output']), (b'x', b'!ok'))

    def test_binary_reads_preserve_suffix_and_selected_byte_order(self):
        for waiting in (False, True):
            for reverse in (False, True):
                with self.subTest(waiting=waiting, reverse=reverse):
                    data = struct.pack('>ii' if reverse else '<ii', 17, 29)
                    bank, context = streams(data, waiting=waiting)
                    prefix = 'SET_FILE_ATR(f,ATR_REVERSE) ' if reverse else ''
                    task, _ = compile_program(prefix + "OPEN FILE f('RB','P2:') READ f(n) READ f(m) CLOSE FILE f",
                                              decl=DECL, context=context)
                    values = task.run()
                    self.assertEqual((values['N'], values['M'], bank.used()), (17, 29, 0))

    def test_fragmented_crlf_continues_after_reclamation(self):
        bank, context = streams(b'discard\r', waiting=True, capacity=8)
        chunks = iter((b'\nnext\r', b'\ntail\r\n'))

        def feed(_):
            self.assertEqual(bank.snapshot()[2]['input'], b'')
            bank.feed(2, next(chunks))

        task = program('READ f(CR) READ f(first,CR) READ f(second,CR) CLOSE FILE f', context=context, sleep=feed)
        values = task.run()
        self.assertEqual((values['FIRST'], values['SECOND'], bank.used()), ('next', 'tail', 0))

    def test_invalid_later_record_does_not_discard_its_prefix(self):
        for waiting in (False, True):
            with self.subTest(waiting=waiting):
                bank, context = streams(b'7\n12 bad\n', waiting=waiting)
                task = program('READ f(n,CR) n=99 m=88 READ f(n,m,CR)', context=context)
                with self.assertRaises(rt.KarelRuntimeError):
                    task.run()
                handle = task._state.values['F']
                self.assertEqual((task.snapshot()['N'], task.snapshot()['M'], handle.position), (99, 88, 0))
                self.assertEqual(bank.snapshot()[2]['input'], b'12 bad\n')
                self.assertEqual(bank._pending, {})
                bank.close(handle)
                self.assertEqual(bank.snapshot()[2]['input'], b'12 bad\n')

    def test_cancel_preserves_pending_record_and_unwinds_registration(self):
        for transport, waiting in product(('socket', 'serial'), (False, True)):
            with self.subTest(transport=transport, waiting=waiting):
                data = struct.pack('<i', 17) + b'tail'
                if transport=='serial':
                    bank, context = streams(data, waiting=waiting)
                    task = program('n=99 READ f(n)', context=context, binary=True)
                else:
                    bank=rt.Messaging({'S1:':dict(input=data,wait=waiting,connected=True)})
                    task,_=compile_program("OPEN FILE f('RB','S1:') n=99 READ f(n)",decl=DECL,
                                           context=rt.ExecutionContext(messaging=bank))
                charge = fileops.charge_file_bytes

                def cancel(size, check):
                    charge(size, check)
                    rt.cancel_file(task._state, task._state.values['F'])

                with patch.object(fileops, 'charge_file_bytes', side_effect=cancel):
                    values = task.run()
                handle = task._state.values['F']
                self.assertEqual((values['N'], handle.position, handle.status), (99, 0, 6))
                self.assertEqual(bank.files[handle.name], data)
                self.assertEqual(bank._pending, {})
                self.assertIsNone(handle._read_operation)

    def test_finite_socket_connection_change_during_accounting_rejects_read(self):
        bank=rt.Messaging({'S1:':dict(input=b'17\n',connected=True)})
        task,_=compile_program("OPEN FILE f('RO','S1:') n=99 READ f(n,CR)",decl=DECL,
                               context=rt.ExecutionContext(messaging=bank))
        charge=fileops.charge_file_bytes

        def reconnect(size,check):
            charge(size,check)
            bank.ports['S1:']['_connection']=object()

        with patch.object(fileops,'charge_file_bytes',side_effect=reconnect):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'Finite socket READ registration changed'):
                task.run()
        self.assertEqual((task.snapshot()['N'],task._state.values['F'].position),(99,0))
        self.assertEqual(bank.files['S1:'],b'17\n')

    def test_waiting_read_cannot_be_reclassified_as_finite_for_cancellation(self):
        bank,_=streams(b'1',waiting=True)
        project=pending_project(bank,decl=DECL)
        task=project.programs['MAIN']
        handle=task._state.values['F']
        record=bank._pending.pop(id(handle))
        bank.ports[2]['wait']=False
        bank.ports[2]['final']=True
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Serial pending READ registration changed'):
            rt.cancel_file(task._state,handle)
        self.assertFalse(handle._read_operation['cancelled'])
        bank._pending[id(handle)]=record
        bank.ports[2]['wait']=True
        rt.cancel_file(task._state,handle)
        project.scheduler.run()
        self.assertEqual(bank.snapshot()[2]['input'],b'1')

    def test_suffix_movement_budget_precedes_binary_decode_and_publication(self):
        data = struct.pack('<i', 17) + b'x' * 4096
        for transport in ('socket', 'serial'):
            for waiting in (False, True):
                with self.subTest(transport=transport, waiting=waiting):
                    if transport == 'serial':
                        bank, context = streams(data, waiting=waiting)
                        name = 'P2:'
                    else:
                        name = 'S1:'
                        bank = rt.Messaging({name: dict(input=data, wait=waiting, connected=True)})
                        context = rt.ExecutionContext(messaging=bank)
                    task, _ = compile_program(f"OPEN FILE f('RB','{name}') n=99 READ f(n)", decl=DECL, context=context)
                    charge = fileops.charge_file_bytes
                    sizes = []

                    def limited(size, check):
                        sizes.append(size)
                        task._state.max_steps = task._state.steps + 1
                        charge(size, check)

                    with patch.object(fileops, 'charge_file_bytes', side_effect=limited), patch('struct.unpack') as decode:
                        with self.assertRaisesRegex(rt.KarelRuntimeError, 'Execution step budget exceeded'):
                            task.run()
                        decode.assert_not_called()
                    handle = task._state.values['F']
                    self.assertEqual((sizes, task.snapshot()['N'], handle.position), ([len(data)], 99, 0))
                    self.assertEqual(bank.files[name], data)
                    self.assertEqual(bank._pending, {})

    def test_policy_change_during_byte_accounting_fails_before_publication(self):
        for waiting in (False, True):
            with self.subTest(waiting=waiting):
                bank, context = streams(b'17\n', waiting=waiting)
                task = program('n=99 READ f(n,CR)', context=context)
                charge = fileops.charge_file_bytes

                def change(size, check):
                    charge(size, check)
                    bank.ports[2]['reclaim_input'] = False

                with patch.object(fileops, 'charge_file_bytes', side_effect=change):
                    with self.assertRaisesRegex(rt.KarelRuntimeError, 'reclaim_input policy changed'):
                        task.run()
                self.assertEqual((task.snapshot()['N'], task._state.values['F'].position), (99, 0))
                self.assertEqual(bank.snapshot()[2]['input'], b'17\n')
                self.assertEqual(bank._pending, {})
                bank.ports[2]['reclaim_input'] = True
                bank.close(task._state.values['F'])

    def test_pause_resume_keeps_captured_read_after_prior_reclamation(self):
        bank, _ = streams(b'7\n', waiting=True, capacity=3)
        project = pending_project(bank, "OPEN FILE f('RO','P2:') READ f(n,CR) READ f(m,CR) CLOSE FILE f", decl=DECL)
        task = project.programs['MAIN']
        self.assertEqual((task.snapshot()['N'], bank.used()), (7, 0))
        task.pause()
        for _ in range(30):
            project.scheduler.step()
            if task.task_state == 'paused':
                break
        self.assertEqual(task.task_state, 'paused')
        self.assertEqual(len(bank._pending), 1)
        bank.feed(2, b'29\n')
        project.scheduler.continue_task('MAIN')
        project.scheduler.run()
        self.assertEqual((task.snapshot()['M'], bank.used(), bank._pending), (29, 0, {}))

    def test_context_roundtrip_preserves_opt_in_and_remaining_queues(self):
        bank, context = streams(b'7\n8\n', output=b'!')
        task = program('READ f(n,CR) CLOSE FILE f', context=context)
        task.run()
        saved = json.loads(json.dumps(context.to_config()))
        self.assertIs(saved['serial_streams']['ports']['2']['reclaim_input'], True)
        restored = rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.serial_streams.snapshot(), bank.snapshot())
        next_task = program('READ f(n,CR) CLOSE FILE f', context=restored)
        self.assertEqual(next_task.run()['N'], 8)
        self.assertEqual(restored.serial_streams.snapshot()[2]['output'], b'!')

    def test_default_keeps_close_time_consumption_and_saved_shape(self):
        bank = rt.SerialStreams({2: dict(input=b'7\n8\n', reclaim_input=False)})
        context = rt.ExecutionContext(serial_streams=bank)
        task = program('READ f(n,CR)', context=context)
        task.run()
        self.assertEqual((task.snapshot()['F']['position'], bank.snapshot()[2]['input']), (2, b'7\n8\n'))
        bank.close(task._state.values['F'])
        self.assertNotIn('reclaim_input', bank.to_config()['ports']['2'])

    def test_reclaim_option_requires_actual_boolean(self):
        for value in (0, 1, None, 'true', [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'reclaim_input requires BOOLEAN'):
                rt.SerialStreams({2: dict(reclaim_input=value)})


if __name__ == '__main__':
    unittest.main()
