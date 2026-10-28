"""Scalar branches compose with exact dynamic aliases and prepared volume moves."""
import unittest

from karel2py import translate, runtime as rt


SOURCE = '''PROGRAM MAIN
VAR entry,status,result:INTEGER copied:BYTE route:STRING[8]
ROUTINE work(item:BYTE)
BEGIN
 SELECT item OF
  CASE(200):
   RENAME_FILE('FR:part*.DAT','RD:saved_*.BAK',FALSE,status)
   SELECT route OF CASE('go'): item=201 result=1 ENDSELECT
  ELSE: result=-1
 ENDSELECT
END work
BEGIN
 CREATE_VAR('CACHE','CODE','','BYTE',0,0,0,0,status)
 SET_VAR(entry,'CACHE','CODE',200,status)
 route='go' result=0 status=77
 work(BYNAME('CACHE','CODE',entry))
 GET_VAR(entry,'CACHE','CODE',copied,status)
END MAIN'''


def build(source, context):
    namespace = {'__name__': 'authored_scalar_dynamic_volumes'}
    exec(translate(source).python_source, namespace)
    return namespace['Program'](context=context)


class ScalarDynamicVolumesIntegrationTests(unittest.TestCase):
    def context(self, target_capacity=8):
        files = rt.DeviceFiles({'FR:': {'capacity': 10, 'garbage': 2},
                                'RD:': {'capacity': target_capacity, 'garbage': 1}},
                               {'FR:partA.DAT': b'abc', 'FR:partB.DAT': b'de'})
        return rt.ExecutionContext(files=files)

    def assert_moved(self, context):
        self.assertEqual(context.files.snapshot(), {'RD:saved_partA.BAK': b'abc', 'RD:saved_partB.BAK': b'de'})
        self.assertEqual(context.files.to_config()['volumes']['FR:']['garbage'], 7)
        self.assertEqual(context.files.to_config()['volumes']['RD:']['garbage'], 1)

    def test_matching_string_branch_mutates_exact_dynamic_byte_alias(self):
        for labelled in (False, True):
            with self.subTest(labelled=labelled):
                context = self.context()
                source = SOURCE.replace(" route='go'", " marker:: route='go'") if labelled else SOURCE
                task = build(source, context)
                self.assertEqual(task.run(), {'ENTRY': 1, 'STATUS': 0, 'RESULT': 1, 'COPIED': 201, 'ROUTE': 'go'})
                self.assertEqual(context.variables.bindings['CACHE', 'CODE'].spec, ('BYTE',))
                self.assertEqual(context.variables.bindings['CACHE', 'CODE'].raw(), 201)
                self.assert_moved(context)
                config = context.to_config()
                self.assertEqual(rt.ExecutionContext.from_config(config).to_config(), config)

    def test_late_batch_capacity_failure_preserves_every_file_and_alias(self):
        context = self.context(target_capacity=4)
        before = context.files.to_config()
        task = build(SOURCE, context)
        with self.assertRaises(rt.KarelRuntimeError):
            task.run()
        self.assertEqual(context.files.to_config(), before)
        self.assertEqual(context.variables.bindings['CACHE', 'CODE'].raw(), 200)
        self.assertEqual((task.snapshot()['STATUS'], task.snapshot()['RESULT']), (77, 0))
        self.assertEqual((task._state.local_frames, task._state.call_depth), ([], 0))

    def test_dynamic_rename_keeps_passed_narrow_reference_alive(self):
        source = SOURCE.replace("  CASE(200):", "  CASE(200): RENAME_VAR('CACHE','CODE','RENAMED',status)")
        source = source.replace(" GET_VAR(entry,'CACHE','CODE',copied,status)", " GET_VAR(entry,'CACHE','RENAMED',copied,status)")
        context = self.context()
        self.assertEqual(build(source, context).run()['COPIED'], 201)
        self.assertNotIn(('CACHE', 'CODE'), context.variables.bindings)
        self.assertEqual(context.variables.bindings['CACHE', 'RENAMED'].raw(), 201)
        self.assert_moved(context)

    def test_unmatched_string_case_retains_completed_virtual_rename(self):
        context = self.context()
        task = build(SOURCE.replace("route='go'", "route='other'"), context)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'No match in CASE'):
            task.run()
        self.assert_moved(context)
        self.assertEqual(context.variables.bindings['CACHE', 'CODE'].raw(), 200)
        self.assertEqual((task.snapshot()['STATUS'], task.snapshot()['RESULT']), (0, 0))
        self.assertEqual((task._state.local_frames, task._state.call_depth), ([], 0))


if __name__ == '__main__':
    unittest.main()
