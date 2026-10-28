"""Captured counters and finite serial failures share ordinary loop lifetime."""
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError


def program(source, context):
    namespace = {'__name__': 'authored_integration'}
    exec(translate(source).python_source, namespace)
    return namespace['Program'](context=context)


SOURCE = '''PROGRAM T
VAR slots:ARRAY[2] OF INTEGER slot,value:INTEGER channel:FILE translated:VECTOR
BEGIN
  slots[2]=99
  slot=1
  OPEN FILE channel('RO','P2:')
  FOR slots[slot]=1 TO 2 DO
    READ channel(value,CR)
    slot=2
    PAUSE
    translated=VEC(slots[1],0,0):INV(VEC(0,1,0))
  ENDFOR
  CLOSE FILE channel
END T'''
U = {'uninitialized': True}


class ReferenceGeometrySerialIntegrationTests(unittest.TestCase):
    def test_resume_preserves_selected_cell_rx_cursor_and_translation_result(self):
        streams = rt.SerialStreams({2: {'input': '11\n22\n', 'capacity': 1024}})
        task = program(SOURCE, rt.ExecutionContext(serial_streams=streams))
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(task.snapshot()['SLOTS'], [1, 99])
        with self.assertRaises(rt.KarelPause):
            task.resume()
        self.assertEqual(task.snapshot()['SLOTS'], [2, 99])
        values = task.resume()
        self.assertEqual(values['SLOTS'], [U, 99])
        self.assertEqual(values['VALUE'], 22)
        self.assertEqual(values['TRANSLATED'], {'X': 2., 'Y': -1., 'Z': 0.})
        self.assertEqual(streams.to_config()['ports']['2']['input'], {'hex': ''})

    def test_stop_clears_captured_counter_but_keeps_explicit_file_close_contract(self):
        streams = rt.SerialStreams({2: {'input': '11\n22\n', 'capacity': 1024}})
        task = program(SOURCE, rt.ExecutionContext(serial_streams=streams))
        with self.assertRaises(rt.KarelPause):
            task.run()
        handle = task._state.raw('CHANNEL')
        task.stop()
        self.assertEqual(task.snapshot()['SLOTS'], [U, 99])
        self.assertIs(handle.owner, streams)
        with self.assertRaises(ValueError):
            task._state.execution.to_config()
        streams.close(handle)
        self.assertEqual(streams.to_config()['ports']['2']['input'], {'hex': b'22\n'.hex()})

    def test_serial_eof_preserves_last_value_and_unwinds_field_counter(self):
        source = '''PROGRAM T
TYPE counter_t=STRUCTURE count:INTEGER ENDSTRUCTURE
VAR cursor:counter_t channel:FILE value,total:INTEGER
BEGIN
 total=0 OPEN FILE channel('RO','P2:')
 FOR cursor.count=1 TO 3 DO READ channel(value,CR) total=total+value ENDFOR
 CLOSE FILE channel
END T'''
        streams = rt.SerialStreams({2: {'input': '1\n2\n', 'capacity': 1024}})
        task = program(source, rt.ExecutionContext(serial_streams=streams))
        with self.assertRaises(rt.KarelRuntimeError):
            task.run()
        values = task.snapshot()
        self.assertEqual((values['CURSOR'], values['VALUE'], values['TOTAL']), ({'COUNT': U}, 2, 3))
        streams.close(task._state.raw('CHANNEL'))
        self.assertEqual(streams.to_config()['ports']['2']['input'], {'hex': ''})

    def test_serial_read_cannot_write_active_aggregate_counter_root(self):
        source = '''PROGRAM T
TYPE counter_t=STRUCTURE count:INTEGER other:INTEGER ENDSTRUCTURE
VAR cursor:counter_t channel:FILE
BEGIN FOR cursor.count=1 TO 2 DO READ channel(cursor.other) ENDFOR END T'''
        with self.assertRaises(TranslationError) as caught:
            translate(source)
        self.assertEqual(caught.exception.code, 'E_FOR_COUNTER')


if __name__ == '__main__':
    unittest.main()
