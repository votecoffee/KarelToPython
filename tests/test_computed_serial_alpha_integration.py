"""Computed values suspend once and retain ordinary stream/image boundaries."""
import unittest

from karel2py import translate, translate_project, runtime as rt


SOURCE = '''PROGRAM MAIN
TYPE item_t=STRUCTURE value:INTEGER ENDSTRUCTURE
VAR calls,observed:INTEGER
ROUTINE receive:item_t
VAR channel:FILE answer:item_t
BEGIN
 calls=calls+1 OPEN FILE channel('RO','P2:')
 READ channel(answer.value,CR) CLOSE FILE channel
 RETURN answer
END receive
BEGIN
 calls=0 observed=9
 USING receive() DO value=value+1 observed=value ENDUSING
END MAIN'''


def program(source, context, **options):
    namespace = {'__name__': 'authored_computed_input'}
    exec(translate(source).python_source, namespace)
    return namespace['Program'](context=context, **options)


class ComputedSerialAlphaIntegrationTests(unittest.TestCase):
    def test_computed_selector_calls_once_across_serial_wait(self):
        bank = rt.SerialStreams({2: {'input': '4', 'wait': True, 'capacity': 1024}})
        delays = []
        def feed(seconds):
            delays.append(seconds)
            self.assertEqual(task.snapshot()['CALLS'], 1)
            self.assertTrue(bank._pending)
            bank.feed(2, b'1\n')
        task = program(SOURCE, rt.ExecutionContext(serial_streams=bank), sleep=feed)
        self.assertEqual(task.run(), {'CALLS': 1, 'OBSERVED': 42})
        self.assertEqual(len(delays), 1)
        self.assertFalse(bank._pending)
        self.assertEqual(bank.snapshot()[2]['input'], b'')

    def test_stop_pending_computed_call_preserves_prefix_and_explicit_file_lifetime(self):
        bank = rt.SerialStreams({2: {'input': '4', 'wait': True, 'capacity': 1024}})
        context = rt.ExecutionContext(serial_streams=bank)
        instance = translate_project({'main.kl': SOURCE}).instantiate(context=context)
        instance.scheduler.start('MAIN')
        for _ in range(32):
            instance.scheduler.step()
            if bank._pending:
                break
        self.assertTrue(bank._pending)
        self.assertEqual(instance.programs['MAIN'].snapshot(), {'CALLS': 1, 'OBSERVED': 9})
        handle = bank.handles[0]
        with self.assertRaises(rt.KarelRuntimeError):
            bank.close(handle)
        instance.scheduler.stop('MAIN')
        self.assertFalse(bank._pending)
        self.assertIs(handle.owner, bank)
        self.assertEqual(handle.position, 0)
        bank.close(handle)
        self.assertEqual(bank.snapshot()[2]['input'], b'4')
        self.assertEqual(context.to_config()['serial_streams']['ports']['2']['final'], False)

    def test_final_incomplete_computed_call_does_not_publish_read_or_using_outputs(self):
        source = '''PROGRAM T
TYPE item_t=STRUCTURE value:INTEGER ENDSTRUCTURE
VAR calls,value,other,observed:INTEGER
ROUTINE receive:item_t
VAR channel:FILE answer:item_t
BEGIN
 calls=calls+1 OPEN FILE channel('RO','P2:')
 READ channel(value,other) CLOSE FILE channel
 answer.value=value RETURN answer
END receive
BEGIN calls=0 value=7 other=8 observed=9
 USING receive() DO observed=value ENDUSING
END T'''
        bank = rt.SerialStreams({2: {'input': '41 ', 'wait': True, 'capacity': 1024}})
        task = program(source, rt.ExecutionContext(serial_streams=bank), sleep=lambda seconds: bank.finish_input(2))
        with self.assertRaises(rt.KarelRuntimeError):
            task.run()
        self.assertEqual(task.snapshot(), {'CALLS': 1, 'VALUE': 7, 'OTHER': 8, 'OBSERVED': 9})
        self.assertFalse(bank._pending)
        handle = bank.handles[0]
        self.assertEqual(handle.position, 0)
        bank.close(handle)
        self.assertEqual(bank.snapshot()[2]['input'], b'41 ')

    def test_private_selector_edit_does_not_change_image_selection_source(self):
        source = '''PROGRAM T
TYPE choice_t=STRUCTURE slot:INTEGER ENDSTRUCTURE
VAR seed:choice_t calls,status:INTEGER
ROUTINE selected:choice_t BEGIN calls=calls+1 RETURN seed END selected
BEGIN seed.slot=1 calls=0
 USING selected() DO V_SAVE_IMREG(slot,'alpha.png',status) slot=7 ENDUSING
END T'''
        context = rt.ExecutionContext.from_config({'files': {}, 'vision': {
            'processes': {'SCAN': {'views': [1], 'runs': []}}, 'io': {'image_count': 1, 'images': {'1': {
                'process': 'SCAN', 'views': [1], 'image': {'width': 1, 'height': 1,
                    'channels': 4, 'pixels': 'ff000080'}}}}}})
        task = program(source, context)
        self.assertEqual(task.run(), {'SEED': {'SLOT': 1}, 'CALLS': 1, 'STATUS': 0})
        self.assertEqual(context.files.snapshot()['alpha.png'][24:26], b'\x08\x06')
        self.assertEqual(context.vision.io.images[1]['image']['pixels'], bytes.fromhex('ff000080'))


if __name__ == '__main__':
    unittest.main()
