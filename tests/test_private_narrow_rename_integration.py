"""Private counters, detached narrow values and prepared rename batches compose."""
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError


SOURCE = '''PROGRAM MAIN
TYPE item_t=STRUCTURE count:INTEGER ENDSTRUCTURE
VAR seed:item_t total,status:INTEGER cleared,done:BOOLEAN
ROUTINE make:item_t BEGIN RETURN seed END make
ROUTINE touch(value:BYTE) BEGIN value=1 END touch
BEGIN
 IF UNINIT(done) THEN done=FALSE ENDIF
 IF NOT done THEN
  seed.count=99 total=0
  USING make() DO
   FOR count=1 TO 3 DO
    touch(count)
    IF count=1 THEN RENAME_FILE('part*.DAT','saved_*.BAK',FALSE,status) ENDIF
    total=total+count
   ENDFOR
   cleared=UNINIT(count)
  ENDUSING
  done=TRUE
 ENDIF
END MAIN'''


def build(source, context):
    namespace = {'__name__': 'authored_integration'}
    exec(translate(source).python_source, namespace)
    return namespace['Program'](context=context)


class PrivateNarrowRenameIntegrationTests(unittest.TestCase):
    def context(self):
        return rt.ExecutionContext(files=rt.MemoryFiles({'partA.DAT': b'alpha', 'partB.DAT': b'beta'}))

    def test_detached_narrow_argument_cannot_mutate_private_counter(self):
        for labelled in (False, True):
            with self.subTest(labelled=labelled):
                context = self.context()
                source = SOURCE.replace('  seed.count=99', '  marker:: seed.count=99') if labelled else SOURCE
                task = build(source, context)
                self.assertEqual(task.run(), {'SEED': {'COUNT': 99}, 'TOTAL': 6, 'STATUS': 0, 'CLEARED': True, 'DONE': True})
                self.assertEqual(context.files.snapshot(), {'saved_partA.BAK': b'alpha', 'saved_partB.BAK': b'beta'})
                restored = rt.ExecutionContext.from_config(context.to_config())
                self.assertEqual(restored.files.snapshot(), context.files.snapshot())
                self.assertEqual(task._state.local_frames, [])
                self.assertEqual(task._state.call_depth, 0)

    def test_rename_status_cannot_write_active_private_counter(self):
        source = SOURCE.replace("FALSE,status)", "FALSE,count)")
        with self.assertRaises(TranslationError) as caught:
            translate(source)
        self.assertEqual(caught.exception.code, 'E_FOR_COUNTER')

    def test_later_narrow_overflow_retains_completed_rename(self):
        source = SOURCE.replace('count=1 TO 3', 'count=255 TO 256').replace('IF count=1 THEN', 'IF count=255 THEN')
        context = self.context()
        task = build(source, context)
        with self.assertRaises(rt.KarelRuntimeError):
            task.run()
        self.assertEqual(task.snapshot()['TOTAL'], 255)
        self.assertEqual(task.snapshot()['SEED'], {'COUNT': 99})
        self.assertEqual(context.files.snapshot(), {'saved_partA.BAK': b'alpha', 'saved_partB.BAK': b'beta'})
        self.assertEqual(task._state.local_frames, [])
        self.assertEqual(task._state.call_depth, 0)

    def test_goto_exits_counter_after_narrow_call_and_rename(self):
        source = SOURCE.replace('total=total+count\n   ENDFOR', 'total=total+count GOTO after_loop\n   ENDFOR after_loop::')
        context = self.context()
        values = build(source, context).run()
        self.assertEqual((values['TOTAL'], values['CLEARED'], values['SEED']), (1, True, {'COUNT': 99}))
        self.assertEqual(context.files.snapshot(), {'saved_partA.BAK': b'alpha', 'saved_partB.BAK': b'beta'})


if __name__ == '__main__':
    unittest.main()
