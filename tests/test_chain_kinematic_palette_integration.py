"""Chained references retain model conversion, palette and failure boundaries."""
from copy import deepcopy
import struct
import unittest
import zlib

from karel2py import translate, runtime as rt


CONFIG = {
    'robot': {'dh': [{'a': 100}, {'a': 100}],
              'current': {'joints': {'type': ['JOINTPOS', 2], 'value': [0., 0.]}}},
    'files': {},
    'vision': {'processes': {'SCAN': {'views': [1], 'runs': []}},
               'io': {'image_count': 1, 'images': {'1': {'process': 'SCAN', 'views': [1],
                   'image': {'width': 2, 'height': 1, 'channels': 1, 'pixels': '0001', 'palette': 'ff00008000ff0000'}}}}}
}
SOURCE = '''PROGRAM MAIN
VAR joints:ARRAY[1,1] OF JOINTPOS poses:ARRAY[1,1] OF XYZWPR status,visits:INTEGER
ROUTINE paint(value:XYZWPR):XYZWPR
BEGIN
 visits=visits+1 V_SAVE_IMREG(1,'indexed.png',status)
 value.x=value.x+5 RETURN value
END paint
BEGIN
 visits=0 status=77 joints[1][1]=CURJPOS(0,0)
 poses[1][1]=paint(joints[1][1])
END MAIN'''


def palette_png(data):
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    chunks = []; offset = 8
    while offset < len(data):
        length = struct.unpack_from('>I', data, offset)[0]
        kind = data[offset + 4:offset + 8]; payload = data[offset + 8:offset + 8 + length]
        checksum = struct.unpack_from('>I', data, offset + 8 + length)[0]
        assert checksum == zlib.crc32(kind + payload) & 0xffffffff
        chunks.append((kind, payload)); offset += 12 + length
    assert offset == len(data) and [kind for kind, _ in chunks] == [b'IHDR', b'PLTE', b'tRNS', b'IDAT', b'IEND']
    table = dict(chunks)
    assert struct.unpack('>IIBBBBB', table[b'IHDR']) == (2, 1, 8, 3, 0, 0, 0)
    assert table[b'PLTE'] == bytes.fromhex('ff000000ff00')
    assert table[b'tRNS'] == bytes.fromhex('8000')
    assert zlib.decompress(table[b'IDAT']) == b'\x00\x00\x01'


def build(source, context):
    namespace = {'__name__': 'authored_chain_kinematic_palette'}
    exec(translate(source).python_source, namespace)
    return namespace['Program'](context=context)


class ChainKinematicPaletteIntegrationTests(unittest.TestCase):
    def context(self):
        return rt.ExecutionContext.from_config(deepcopy(CONFIG))

    def test_chained_joint_actual_converts_privately_before_palette_export(self):
        for labelled in (False, True):
            with self.subTest(labelled=labelled):
                context = self.context(); robot = context.robot.to_config()
                source = SOURCE.replace(' visits=0', ' marker:: visits=0') if labelled else SOURCE
                task = build(source, context); values = task.run()
                self.assertEqual((values['VISITS'], values['STATUS'], values['POSES'][0][0]['X']), (1, 0, 205.))
                self.assertEqual(values['JOINTS'][0][0]['axes'], [0.] * 9)
                self.assertEqual(context.robot.to_config(), robot)
                palette_png(context.files.snapshot()['indexed.png'])
                config = context.to_config()
                self.assertEqual(rt.ExecutionContext.from_config(config).to_config(), config)

    def test_target_index_failure_keeps_completed_model_and_image_effects(self):
        source = SOURCE.replace('BEGIN\n visits=0', 'ROUTINE choose:INTEGER BEGIN visits=visits+100 RETURN 2 END choose\nBEGIN\n visits=0')
        source = source.replace('poses[1][1]=paint', 'poses[choose()][1]=paint')
        context = self.context(); robot = context.robot.to_config(); task = build(source, context)
        with self.assertRaises(rt.KarelRuntimeError): task.run()
        self.assertEqual(task.snapshot()['VISITS'], 101)
        self.assertEqual(task.snapshot()['POSES'][0][0]['X'], {'uninitialized': True})
        self.assertEqual(context.robot.to_config(), robot)
        palette_png(context.files.snapshot()['indexed.png'])
        self.assertEqual((task._state.local_frames, task._state.call_depth), ([], 0))

    def test_missing_robot_fails_before_callee_or_export(self):
        config = deepcopy(CONFIG); config.pop('robot')
        context = rt.ExecutionContext.from_config(config)
        task = build(SOURCE.replace('joints[1][1]=CURJPOS(0,0)', ''), context)
        joint = rt.JointPosition(('JOINTPOS', 9)); joint.values[:] = [0.] * 9
        task._state.values['JOINTS'].set((1, 1), joint)
        with self.assertRaises(rt.KarelRuntimeError): task.run()
        self.assertEqual((task.snapshot()['VISITS'], task.snapshot()['STATUS']), (0, 77))
        self.assertEqual(context.files.snapshot(), {})
        self.assertEqual((task._state.local_frames, task._state.call_depth), ([], 0))

    def test_export_capacity_status_preserves_previous_bytes_and_source_pixels(self):
        context = self.context(); robot = context.robot.to_config(); vision = context.vision.to_config()
        context.files = rt.MemoryFiles({'indexed.png': b'old'}, limit=3)
        values = build(SOURCE, context).run()
        self.assertEqual((values['VISITS'], values['STATUS'], values['POSES'][0][0]['X']), (1, 5, 205.))
        self.assertEqual(context.files.snapshot(), {'indexed.png': b'old'})
        self.assertEqual(context.vision.to_config()['io']['images'], vision['io']['images'])
        self.assertEqual(context.robot.to_config(), robot)


if __name__ == '__main__':
    unittest.main()
