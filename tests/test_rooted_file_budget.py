"""Rooted FILE lifecycle budget and publication checks through translated source."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from karel2py import fileops, runtime as rt
from tests.test_extended_services import compile_program


RETAINED = b'a' * 8193


def program(files, body):
    return compile_program(body, decl='f:FILE', context=rt.ExecutionContext(files=files))[0]


class RootedFileBudgetTests(unittest.TestCase):
    def test_open_budget_precedes_host_read_and_preserves_cache(self):
        with TemporaryDirectory() as folder:
            files = rt.DirectoryFiles(folder)
            path = files.root / 'data'
            path.write_bytes(RETAINED)
            cached = files.files['data'] = bytearray(b'cached')
            open_path = Path.open

            def forbid_read(candidate, *args, **kwargs):
                if candidate == path:
                    self.fail('OPEN read host bytes before charging')
                return open_path(candidate, *args, **kwargs)

            for mode in ('RO', 'RW', 'AP'):
                with self.subTest(mode=mode):
                    task = program(files, f"OPEN FILE f('{mode}','data')")
                    with patch.object(Path, 'open', forbid_read):
                        with self.assertRaisesRegex(rt.KarelRuntimeError, 'step budget'):
                            task.run(max_steps=1)
                    self.assertIsNone(task._state.values['F'].owner)
                    self.assertIs(files.files['data'], cached)
                    self.assertEqual(files.handles, [])

    def test_truncating_open_skips_old_bytes_until_publication(self):
        with TemporaryDirectory() as folder:
            files = rt.DirectoryFiles(folder)
            path = files.root / 'data'
            path.write_bytes(RETAINED)
            task = program(files, "OPEN FILE f('WB','data')")
            with patch.object(Path, 'open', side_effect=AssertionError('Truncating OPEN read old data')):
                task.run(max_steps=1)
            handle = task._state.values['F']
            self.assertEqual(files.files['data'], b'')
            self.assertTrue(handle.binary)
            self.assertEqual(path.read_bytes(), RETAINED)
            files.close(handle)
            self.assertEqual(path.read_bytes(), b'')

    def test_open_rechecks_disk_before_loading(self):
        with TemporaryDirectory() as folder:
            files = rt.DirectoryFiles(folder)
            path = files.root / 'data'
            path.write_bytes(RETAINED)
            task = program(files, "OPEN FILE f('RO','data')")
            charge = fileops.charge_file_bytes

            def replace(size, check):
                charge(size, check)
                path.write_bytes(b'replacement')

            with patch.object(fileops, 'charge_file_bytes', side_effect=replace):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'source changed'):
                    task.run()
            self.assertIsNone(task._state.values['F'].owner)
            self.assertEqual(files.files, {})
            self.assertEqual(path.read_bytes(), b'replacement')

    def test_flush_budget_preserves_disk_and_keeps_handle_available(self):
        for interactive in (False, True):
            with self.subTest(interactive=interactive), TemporaryDirectory() as folder:
                files = rt.DirectoryFiles(folder)
                path = files.root / 'data'
                path.write_bytes(RETAINED)
                before = 'SET_FILE_ATR(f,ATR_IA) ' if interactive else ''
                after = '' if interactive else ' CLOSE FILE f'
                task = program(files, before + "OPEN FILE f('RW','data') WRITE f('Z')" + after)
                charge = fileops.charge_file_bytes
                sizes = []

                def limit(size, check):
                    sizes.append(size)
                    if len(sizes) == 3:
                        task._state.max_steps = task._state.steps + 1
                    charge(size, check)

                with patch.object(fileops, 'charge_file_bytes', side_effect=limit):
                    with self.assertRaisesRegex(rt.KarelRuntimeError, 'step budget'):
                        task.run()
                self.assertEqual(sizes, [len(RETAINED), 1, len(RETAINED)])
                handle = task._state.values['F']
                buffered = RETAINED if interactive else b'Z' + RETAINED[1:]
                self.assertIs(handle.owner, files)
                self.assertEqual(handle.position, 0 if interactive else 1)
                self.assertEqual(files.files['data'], buffered)
                self.assertEqual(path.read_bytes(), RETAINED)
                files.close(handle)
                self.assertEqual(path.read_bytes(), buffered)

    def test_interactive_flush_preserves_external_change_during_accounting(self):
        with TemporaryDirectory() as folder:
            files = rt.DirectoryFiles(folder)
            path = files.root / 'data'
            path.write_bytes(RETAINED)
            task = program(files, "SET_FILE_ATR(f,ATR_IA) OPEN FILE f('AP','data') WRITE f('Z')")
            charge = fileops.charge_file_bytes

            def replace(size, check):
                charge(size, check)
                if size == len(RETAINED) + 1:
                    path.write_bytes(b'external update')

            with patch.object(fileops, 'charge_file_bytes', side_effect=replace):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'destination changed'):
                    task.run()
            handle = task._state.values['F']
            self.assertIs(handle.owner, files)
            self.assertEqual(handle.position, len(RETAINED))
            self.assertEqual(files.files['data'], RETAINED)
            self.assertEqual(path.read_bytes(), b'external update')

    def test_failed_atomic_replace_preserves_exact_interactive_buffer(self):
        with TemporaryDirectory() as folder:
            files = rt.DirectoryFiles(folder)
            path = files.root / 'data'
            path.write_bytes(RETAINED)
            task = program(files, "SET_FILE_ATR(f,ATR_IA) OPEN FILE f('AP','data') WRITE f('Z')")
            captured = []

            def fail_publish(target, staged):
                self.assertEqual(target, path)
                self.assertEqual(staged, RETAINED + b'Z')
                captured.append(files.files['data'])
                raise OSError('authored replace failure')

            with patch('karel2py.storage.atomic_bytes', side_effect=fail_publish):
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'authored replace failure'):
                    task.run()
            self.assertIs(files.files['data'], captured[0])
            self.assertEqual(files.files['data'], RETAINED)
            self.assertEqual(task._state.values['F'].position, len(RETAINED))
            self.assertEqual(path.read_bytes(), RETAINED)


if __name__ == '__main__':
    unittest.main()
