"""Opt-in virtual volume, decoded dictionary and plain pipe KCL operations."""
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from tests.test_extended_services import compile_program
from tests.test_kcl_task_commands import issue


class KclVirtualDeviceTests(unittest.TestCase):
    def context(self, *, replies=None, enabled=True):
        files = rt.DeviceFiles({'RD:': {'capacity': 40, 'garbage': 3},
                                'FR:': {'capacity': 40, 'garbage': 5}},
                               {'RD:note': b'rd', 'FR:note': b'fr'})
        return rt.ExecutionContext(files=files, kcl=rt.KclCommands(replies, device_commands=enabled))

    def test_device_opt_in_and_exact_reply_precedence(self):
        ctx = self.context(replies={'FORMAT RD:': {'status': 17}})
        self.assertEqual(issue(ctx, 'FORMAT RD:')['S'], 17)
        self.assertEqual(ctx.files.snapshot(), {'RD:note': b'rd', 'FR:note': b'fr'})
        self.assertEqual(issue(ctx, 'format rd:')['S'], 0)
        self.assertEqual(ctx.files.snapshot(), {'FR:note': b'fr'})
        disabled = self.context(enabled=False)
        self.assertEqual(issue(disabled, 'FORMAT RD:')['S'], 1)
        self.assertIn('RD:note', disabled.files.files)

    def test_mount_dismount_and_format_use_only_the_selected_virtual_volume(self):
        ctx = self.context()
        self.assertEqual(issue(ctx, 'DISMOUNT rd:')['S'], 0)
        self.assertEqual(issue(ctx, 'FORMAT RD: replacement YES', nowait=True), {'N': 303, 'S': 0})
        self.assertEqual(ctx.files.snapshot(), {'RD:note': b'rd', 'FR:note': b'fr'})
        self.assertEqual(issue(ctx, 'MOUNT rd')['S'], 0)
        self.assertEqual(issue(ctx, 'FORMAT RD: MixedCaseLabel y')['S'], 0)
        self.assertEqual(ctx.files.snapshot(), {'FR:note': b'fr'})
        self.assertEqual(ctx.files._volumes['RD']['label'], 'MixedCaseLa')
        self.assertEqual(ctx.files._volumes['RD']['garbage'], 0)
        self.assertEqual(ctx.files._volumes['FR']['garbage'], 5)
        self.assertEqual(issue(ctx, 'MOUNT UNKNOWN:')['S'], 302)

    def test_open_file_blocks_purge_pair_without_partial_reclamation(self):
        ctx = self.context()
        handle = rt.FileHandle()
        ctx.files.open(handle, 'RO', 'FR:note')
        self.assertEqual(issue(ctx, 'DISMOUNT FR:')['S'], 304)
        self.assertEqual(issue(ctx, 'PURGE MF:')['S'], 304)
        self.assertEqual(tuple(ctx.files._volumes[name]['garbage'] for name in ('RD', 'FR')), (3, 5))
        self.assertTrue(ctx.files._volumes['FR']['mounted'])
        ctx.files.close(handle)
        self.assertEqual(issue(ctx, 'PURGE MF:')['S'], 0)
        self.assertEqual(issue(ctx, 'PURGE MF:')['S'], rt.DEVICE_CONSTANTS['DEV_NOTHING_TO_PURGE'])
        self.assertEqual(ctx.files.snapshot(), {'RD:note': b'rd', 'FR:note': b'fr'})

    def test_format_rechecks_busy_state_after_its_checkpoint(self):
        ctx = self.context()
        task, _ = compile_program("KCL('FORMAT RD:',s)", context=ctx)
        tick = task._state.tick
        handle = rt.FileHandle()

        def open_during_preflight(*args, **kwargs):
            tick(*args, **kwargs)
            if ctx.kcl._pending is not None and handle.owner is None:
                ctx.files.open(handle, 'RO', 'RD:note')

        with patch.object(task._state, 'tick', side_effect=open_during_preflight):
            self.assertEqual(task.run()['S'], 304)
        ctx.files.close(handle)
        self.assertEqual(ctx.files.snapshot()['RD:note'], b'rd')
        self.assertEqual(ctx.files._volumes['RD']['garbage'], 3)

    def test_volume_commands_require_virtual_backend(self):
        files = rt.MemoryFiles({'RD:note': b'rd'})
        ctx = rt.ExecutionContext(files=files, kcl=rt.KclCommands(device_commands=True))
        self.assertEqual(issue(ctx, 'FORMAT RD:')['S'], 4)
        self.assertEqual(issue(ctx, 'FORMAT RD: a b')['S'], 1)
        self.assertEqual(files.snapshot(), {'RD:note': b'rd'})


class KclDictionaryTests(unittest.TestCase):
    def context(self, *, replies=None, enabled=True):
        catalog = rt.TextDictionaries(sources={'first': '$1 "Default"', 'second.tx': '$1 "Current"',
                                               'bad': '$1 "Incomplete'},
                                      languages=['ENGLISH', 'FRENCH'], language='FRENCH')
        return rt.ExecutionContext(dictionaries=catalog,
                                   kcl=rt.KclCommands(replies, dictionary_commands=enabled))

    def test_dictionary_opt_in_preserves_exact_scripted_reply(self):
        ctx = self.context(replies={'LOAD DICT first menu': {'status': 17}})
        self.assertEqual(issue(ctx, 'LOAD DICT first menu')['S'], 17)
        self.assertEqual(ctx.dictionaries.loaded, {})
        self.assertEqual(issue(ctx, 'load dict first menu')['S'], 0)
        disabled = self.context(enabled=False)
        self.assertEqual(issue(disabled, 'LOAD DICT first menu')['S'], 1)
        self.assertEqual(disabled.dictionaries.loaded, {})

    def test_default_language_clear_leaves_explicit_current_language(self):
        ctx = self.context()
        self.assertEqual(issue(ctx, 'LOAD DICT first MenuLong')['S'], 0)
        self.assertEqual(issue(ctx, 'LOAD DICT second.tx MENU FRENCH')['S'], 0)
        self.assertEqual(issue(ctx, 'CLEAR DICT MENU')['S'], 0)
        self.assertNotIn('ENGLISH', ctx.dictionaries.loaded)
        self.assertEqual(ctx.dictionaries.loaded['FRENCH']['MENU']['source'], 'SECOND.TX')
        task, _ = compile_program("READ_DICT('MENU',1,lines,1,n,s)",
                                  decl='lines:ARRAY[1] OF STRING[16] n,s:INTEGER', context=ctx)
        self.assertEqual(task.run()['LINES'], ['Current'])
        self.assertEqual(issue(ctx, 'LOAD DICT first MENU DEFAULT')['S'], 0)
        self.assertEqual(issue(ctx, 'CLEAR DICT menu ALL')['S'], 0)
        self.assertEqual(ctx.dictionaries.loaded, {})
        self.assertEqual(ctx.dictionaries._parsed, {})
        self.assertIn('FIRST.TX', ctx.dictionaries.sources)

    def test_missing_duplicate_and_invalid_load_preserve_existing_catalog(self):
        ctx = self.context()
        self.assertEqual(issue(ctx, 'LOAD DICT first MENU')['S'], 0)
        before = ctx.dictionaries.to_config()
        self.assertEqual(issue(ctx, 'LOAD DICT second MENU', nowait=True), {'S': 0, 'N': 402})
        self.assertEqual(issue(ctx, 'LOAD DICT missing NEW')['S'], 403)
        self.assertEqual(issue(ctx, 'LOAD DICT bad NEW')['S'], 401)
        self.assertEqual(issue(ctx, 'LOAD DICT first NEW GERMAN')['S'], 33003)
        self.assertEqual(issue(ctx, 'LOAD FORM')['S'], 404)
        self.assertEqual(ctx.dictionaries.to_config(), before)
        saved = ctx.to_config()
        restored = rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.dictionaries.to_config(), before)
        self.assertTrue(restored.kcl.dictionary_commands)

    def test_command_opt_ins_require_boolean(self):
        for field in ('device_commands', 'dictionary_commands'):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field+' requires'):
                rt.KclCommands.from_config({field: 1})


class KclPipePrintTests(unittest.TestCase):
    def test_prints_only_closed_ascii_plain_pipes_and_preserves_bytes(self):
        pipes = rt.FilePipes()
        for name, width, dictionary, data in (('RAW', 0, '', b'plain\n'), ('BAD', 0, '', b'\xff'),
                                               ('FORM', 0, 'MENU', b'text'), ('BIN', 2, '', b'AB')):
            self.assertEqual(pipes.configure(name, False, 1, width, dictionary, 0), 0)
            pipes.feed(name, data)
        ctx = rt.ExecutionContext(file_pipes=pipes, kcl=rt.KclCommands(file_commands=True))
        saved = pipes.snapshot()
        output = []
        handle = rt.FileHandle()
        pipes.open(handle, 'RO', 'PIP:RAW')
        self.assertEqual(issue(ctx, 'PRINT PIP:RAW', write=output.append)['S'], 103)
        pipes.close(handle)
        for name, code in (('MISSING', 101), ('BAD', 4), ('FORM', 102), ('BIN', 102), ('RAW', 0)):
            self.assertEqual(issue(ctx, 'PRINT PIP:'+name, write=output.append)['S'], code)
        self.assertEqual(output, ['plain\n'])
        self.assertEqual(pipes.snapshot(), saved)


if __name__ == '__main__':
    unittest.main()
