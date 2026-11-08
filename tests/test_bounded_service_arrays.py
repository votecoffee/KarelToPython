"""Bounded ARRAY arguments for Pythonic packet and attachment calls."""
import unittest
from unittest.mock import patch

from karel2py import extended, runtime as rt
from tests.test_extended_services import compile_program


class BoundedServiceArrayTests(unittest.TestCase):
    def test_generic_oversized_packet_skips_copy_and_preserves_later_selector(self):
        bank = rt.PcExchange()
        task, _ = compile_program(
            'n=0 transmit(data)',
            decl='data:ARRAY[32767] OF BYTE result:ARRAY[1] OF INTEGER n:INTEGER',
            routines='''
ROUTINE slot:INTEGER BEGIN n=n+1 RETURN 1 END slot
ROUTINE transmit(value:ARRAY OF BYTE) BEGIN SEND_DATAPC(1,value,result[slot]) END transmit
''',
            context=rt.ExecutionContext(pc_exchange=bank),
        )
        with patch.object(extended, 'variable_value', side_effect=AssertionError('Copied oversized packet')):
            values = task.run()
        self.assertEqual((values['N'], values['RESULT']), (1, [4]))
        self.assertEqual(bank.snapshot(), [])

    def test_packet_captures_chained_row_without_copying_containing_array(self):
        bank = rt.PcExchange()
        task, _ = compile_program(
            'n=0 data[2,3,1]=0 data[2,3,2]=0 SEND_DATAPC(7,data[2][row],result[slot])',
            decl='data:ARRAY[2,4,8] OF BYTE result:ARRAY[1] OF INTEGER n:INTEGER',
            routines='''
ROUTINE row:INTEGER BEGIN n=n*10+1 RETURN 3 END row
ROUTINE slot:INTEGER BEGIN n=n*10+2 data[2,3,2]=9 RETURN 1 END slot
''',
            context=rt.ExecutionContext(pc_exchange=bank),
        )
        with patch.object(rt, 'array_prefix_value', side_effect=AssertionError('Copied the containing ARRAY')):
            values = task.run()
        self.assertEqual((values['N'], values['RESULT']), (12, [0]))
        self.assertEqual(bank.snapshot(), [{'sequence': 1, 'event': 7, 'data': '0000'}])
        self.assertEqual(task._state.values['DATA'].get((2, 3, 2)), 9)

    def test_pc_capture_builder_and_decode_budget_preserve_outputs(self):
        for body, budget in (
            ('ADD_INTPC(data,cursor,5,s)', 1),
            ('SEND_DATAPC(7,data,s)', 1),
            ('SEND_DATAPC(7,data,s)', 2),
        ):
            with self.subTest(body=body, budget=budget):
                bank = rt.PcExchange()
                task, _ = compile_program(
                    body, decl='data:ARRAY[8] OF BYTE cursor,s:INTEGER',
                    context=rt.ExecutionContext(pc_exchange=bank),
                )
                source = task._state.values['DATA']
                source.values[:2] = [0, 0]
                before = list(source.values)
                task._state.values.update(CURSOR=1, S=77)
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'step budget'):
                    task.run(max_steps=budget)
                self.assertEqual((task.snapshot()['CURSOR'], task.snapshot()['S']), (1, 77))
                self.assertIs(task._state.values['DATA'], source)
                self.assertEqual(source.values, before)
                self.assertEqual(bank.snapshot(), [])

    def test_oversized_attachment_list_skips_copy_and_leaves_xml_available(self):
        bank = rt.RemoteMessages(message_types=['A'])
        files = rt.MemoryFiles({'TD:note.xml': b'<item/>'})
        task, _ = compile_program(
            "RMCN_SEND('TD:note.xml',paths,0,s) QUEUE_ATTACH('A',paths,0,t)",
            decl='paths:ARRAY[4096] OF STRING[8] s,t:INTEGER',
            context=rt.ExecutionContext(remote_messages=bank, files=files),
        )
        with patch.object(rt, 'service_value', side_effect=AssertionError('Copied oversized attachment list')):
            values = task.run()
        self.assertEqual((values['S'], values['T']), (2, 2))
        self.assertEqual(files.snapshot(), {'TD:note.xml': b'<item/>'})
        self.assertEqual(bank.snapshot(), [])
        self.assertEqual(bank.pending, {})

    def test_remote_attachment_row_is_captured_before_status_selector(self):
        bank = rt.RemoteMessages(message_types=['A'])
        files = rt.MemoryFiles({'TD:note.xml': b'<item/>'})
        task, _ = compile_program(
            "paths[2,1]='TD:first' paths[2,2]='' n=0 "
            "RMCN_SEND('TD:note.xml',paths[2],0,result[slot]) "
            "QUEUE_ATTACH('A',paths[2],0,result[2])",
            decl='paths:ARRAY[4,2] OF STRING[16] result:ARRAY[2] OF INTEGER n:INTEGER',
            routines="ROUTINE slot:INTEGER BEGIN n=n+1 paths[2,1]='TD:later' RETURN 1 END slot",
            context=rt.ExecutionContext(remote_messages=bank, files=files),
        )
        with patch.object(rt, 'array_prefix_value', side_effect=AssertionError('Copied the containing ARRAY')):
            values = task.run()
        self.assertEqual((values['N'], values['RESULT']), (1, [0, 0]))
        self.assertEqual(bank.snapshot()[0]['attachments'], ['TD:first'])
        self.assertEqual(bank.pending['A']['attachments'], ['TD:later'])


if __name__ == '__main__':
    unittest.main()
