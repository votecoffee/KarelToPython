"""Narrow counters compose with detached Cartesian and STRING-array values."""
import unittest

from karel2py import translate, runtime as rt


SOURCE = '''PROGRAM MAIN
TYPE item_t=STRUCTURE count:BYTE ENDSTRUCTURE
VAR seed:item_t cfg:CONFIG status,total:INTEGER octet:BYTE base:XYZWPR result:POSITION
    labels,copied:ARRAY[2] OF STRING[8] seen:REAL
ROUTINE make:item_t BEGIN RETURN seed END make
ROUTINE names:ARRAY OF STRING BEGIN RETURN labels END names
ROUTINE build(value:POSITION):XYZWPREXT
BEGIN value.location.x=value.location.x+1 seen=value.location.x RETURN value END build
BEGIN
 seed.count=200 labels[1]='one' labels[2]='two' copied=names()
 CNV_STR_CONF('N R U T, 0, 0, 0',cfg,status)
 base=POS(1,2,3,0,0,0,cfg) total=0 seen=9
 FOR octet=1 TO 1 DO
  USING make() DO
   FOR count=254 TO 255 DO
    result=build(base)
    total=total+count+ARRAY_LEN(names())
   ENDFOR
  ENDUSING
 ENDFOR
END MAIN'''


def build(source):
    namespace = {'__name__': 'authored_counter_cartesian_string'}
    exec(translate(source).python_source, namespace)
    return namespace['Program']()


class CounterCartesianStringIntegrationTests(unittest.TestCase):
    def assert_counter_and_source(self, values):
        self.assertEqual(values['OCTET'], {'unknown_byte': True})
        self.assertEqual(values['SEED'], {'COUNT': 200})
        self.assertEqual(values['BASE']['X'], 1.)

    def test_converted_position_arguments_are_private_inside_narrow_loops(self):
        for labelled in (False, True):
            with self.subTest(labelled=labelled):
                source = SOURCE.replace(' seed.count=200', ' marker:: seed.count=200') if labelled else SOURCE
                task = build(source)
                values = task.run()
                self.assert_counter_and_source(values)
                self.assertEqual((values['TOTAL'], values['SEEN'], values['RESULT']['LOCATION']['X']), (513, 2., 2.))
                self.assertEqual(values['COPIED'], ['one', 'two'])
                self.assertEqual(task._state.values['COPIED'].spec[2], ('STRING', 8))
                context = task._state.execution.to_config()
                self.assertEqual(rt.ExecutionContext.from_config(context).to_config(), context)

    def test_runtime_capacity_mismatch_preserves_destination_and_clears_counter(self):
        source = SOURCE.replace('labels,copied:ARRAY[2] OF STRING[8]', 'labels:ARRAY[2] OF STRING[8] copied:ARRAY[2] OF STRING[7]')
        source = source.replace('copied=names()', "copied[1]='keep' copied[2]='saved'")
        source = source.replace('result=build(base)', 'result=build(base) copied=names()')
        task = build(source)
        with self.assertRaises(rt.KarelRuntimeError):
            task.run()
        values = task.snapshot()
        self.assert_counter_and_source(values)
        self.assertEqual(values['COPIED'], ['keep', 'saved'])
        self.assertEqual((values['SEEN'], values['RESULT']['LOCATION']['X']), (2., 2.))
        self.assertEqual((task._state.local_frames, task._state.call_depth), ([], 0))

    def test_failed_cartesian_conversion_does_not_enter_callee(self):
        task = build(SOURCE.replace('base=POS(1,2,3,0,0,0,cfg)', 'base.x=1'))
        with self.assertRaises(rt.KarelRuntimeError):
            task.run()
        values = task.snapshot()
        self.assert_counter_and_source(values)
        self.assertEqual((values['SEEN'], values['TOTAL'], values['COPIED']), (9., 0, ['one', 'two']))
        self.assertEqual((task._state.local_frames, task._state.call_depth), ([], 0))

    def test_jump_exits_both_narrow_scopes_after_one_conversion(self):
        source = SOURCE.replace('total=total+count+ARRAY_LEN(names())', 'total=total+count+ARRAY_LEN(names()) GOTO finished')
        source = source.replace(' ENDFOR\nEND MAIN', ' ENDFOR\n finished::\nEND MAIN')
        values = build(source).run()
        self.assert_counter_and_source(values)
        self.assertEqual((values['TOTAL'], values['SEEN']), (256, 2.))


if __name__ == '__main__':
    unittest.main()
