"""Opt-in KCL file commands over explicitly configured offline backends."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from karel2py import runtime as rt
from tests.test_directive_group_locks import program
from tests.test_kcl_task_commands import issue


def context(files=None, *, pipes=None, replies=None, enabled=True):
    return rt.ExecutionContext(files=files, file_pipes=pipes,
                               kcl=rt.KclCommands(replies, file_commands=enabled))


class KclFileCommandTests(unittest.TestCase):
    def test_opt_in_and_exact_replies_keep_existing_behavior(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                files = rt.MemoryFiles({'Source.txt': b'data'})
                ctx = context(files, enabled=enabled, replies={'COPY Source.txt TO Output.txt': {'status': 17}})
                self.assertEqual(issue(ctx, 'COPY Source.txt TO Output.txt')['S'], 17)
                self.assertNotIn('Output.txt', files.files)
                self.assertEqual(issue(ctx, 'copy Source.txt to Output.txt')['S'], 0 if enabled else 1)
                self.assertEqual(files.snapshot().get('Output.txt'), b'data' if enabled else None)

    def test_copy_rename_move_and_delete_use_virtual_file_rules(self):
        files = rt.DeviceFiles({'RD:': {'capacity': 30}, 'FR:': {'capacity': 30}},
                               {'RD:src/One.KL': b'one', 'RD:src/Two.KL': b'two'})
        ctx = context(files)
        self.assertEqual(issue(ctx, r'copy file rd:\src\*.KL to fr:')['S'], 0)
        self.assertEqual(files.snapshot()['FR:One.KL'], b'one')
        self.assertEqual(issue(ctx, 'COPY RD:src/One.KL TO FR:Two.KL')['S'], 102)
        self.assertEqual(issue(ctx, 'COPY RD:src/One.KL TO FR:Two.KL OVERWRITE')['S'], 0)
        self.assertEqual(files.snapshot()['FR:Two.KL'], b'one')
        self.assertEqual(issue(ctx, 'RENAME FILE FR:Two.KL TO FR:Next.KL')['S'], 0)
        self.assertEqual(issue(ctx, 'MOVE FR:Next.KL')['S'], 0)
        self.assertEqual(issue(ctx, 'DELETE FILE RD:Next.KL YES')['S'], 0)
        self.assertEqual(files.snapshot(), {'RD:src/One.KL': b'one', 'RD:src/Two.KL': b'two', 'FR:One.KL': b'one'})

    def test_nowait_distinguishes_channel_acceptance_and_file_result(self):
        files = rt.MemoryFiles({'in.txt': b'source', 'out.txt': b'old'})
        ctx = context(files)
        self.assertEqual(issue(ctx, 'COPY in.txt TO out.txt', nowait=True), {'S': 0, 'N': 102})
        self.assertEqual(issue(ctx, 'DELETE FILE absent.txt', nowait=True), {'S': 0, 'N': 101})
        handle = rt.FileHandle()
        files.open(handle, 'RO', 'out.txt')
        self.assertEqual(issue(ctx, 'DELETE FILE out.txt')['S'], 103)
        files.close(handle)
        self.assertEqual(files.snapshot(), {'in.txt': b'source', 'out.txt': b'old'})

    def test_append_preserves_bytes_and_preflights_missing_alias_and_capacity(self):
        files = rt.MemoryFiles({'in.bin': b'\0\xff', 'out.bin': b'old'}, limit=5)
        ctx = context(files)
        self.assertEqual(issue(ctx, 'APPEND FILE in.bin TO out.bin')['S'], 0)
        expected = {'in.bin': b'\0\xff', 'out.bin': b'old\0\xff'}
        for command, status in (('APPEND FILE in.bin TO missing.bin', 101),
                                ('APPEND FILE in.bin TO in.bin', 102),
                                ('APPEND FILE *.bin TO out.bin', 102),
                                ('APPEND FILE in.bin TO out.bin', 104)):
            self.assertEqual(issue(ctx, command)['S'], status)
            self.assertEqual(files.snapshot(), expected)

    def test_append_charges_virtual_growth_without_obsolete_prefix(self):
        files = rt.DeviceFiles({'RD:': {'capacity': 10}, 'FR:': {'capacity': 8, 'garbage': 2}},
                               {'RD:in.dat': b'123', 'FR:out.dat': b'abc'})
        ctx = context(files)
        self.assertEqual(issue(ctx, 'APPEND FILE RD:in.dat TO FR:out.dat')['S'], 0)
        self.assertEqual(files._volumes['FR']['garbage'], 2)
        self.assertEqual(files.used('FR'), 8)
        self.assertEqual(issue(ctx, 'APPEND FILE RD:in.dat TO FR:out.dat')['S'], 4)
        self.assertEqual(files.snapshot()['FR:out.dat'], b'abc123')

    def test_pipe_commands_keep_config_and_never_truncate_appended_prefix(self):
        pipes = rt.FilePipes()
        self.assertEqual(pipes.configure('OUT.DAT', False, 1, 2, '', 0), 0)
        pipes.feed('OUT.DAT', b'a'*1022)
        files = rt.MemoryFiles({'in.dat': b'XY'})
        ctx = context(files, pipes=pipes)
        self.assertEqual(issue(ctx, 'APPEND FILE in.dat TO PIP:OUT.DAT')['S'], 0)
        self.assertEqual(issue(ctx, 'APPEND FILE in.dat TO PIP:OUT.DAT')['S'], 104)
        self.assertEqual(pipes.snapshot()['PIP:OUT.DAT'], b'a'*1022+b'XY')
        self.assertEqual(pipes.pipes['PIP:OUT.DAT']['record_size'], 2)
        self.assertEqual(issue(ctx, 'COPY PIP:OUT.DAT TO copy.dat')['S'], 0)
        self.assertEqual(files.snapshot()['copy.dat'], pipes.snapshot()['PIP:OUT.DAT'])
        output = []
        self.assertEqual(issue(ctx, 'DIRECTORY PIP:', write=output.append)['S'], 0)
        self.assertEqual(output, ['PIP:OUT.DAT\n'])

    def test_rooted_append_is_complete_and_kcl_paths_cannot_escape(self):
        with TemporaryDirectory(prefix='kcl_file_test_') as work:
            root = Path(work).resolve()
            subdir = root/'data'
            subdir.mkdir()
            (subdir/'in.dat').write_bytes(b'b')
            (subdir/'out.dat').write_bytes(b'a')
            files = rt.DirectoryFiles(root, devices={'RD': 'data'})
            ctx = context(files)
            self.assertEqual(issue(ctx, r'APPEND FILE rd:\in.dat TO RD:out.dat')['S'], 0)
            self.assertEqual(issue(ctx, 'DELETE FILE RD:../out.dat')['S'], 4)
            self.assertEqual(issue(ctx, 'COPY RD:in.dat TO /out.dat')['S'], 4)
            self.assertEqual((subdir/'out.dat').read_bytes(), b'ab')
            self.assertFalse((root/'out.dat').exists())

    def test_rooted_append_rejects_physical_alias(self):
        with TemporaryDirectory(prefix='kcl_file_alias_') as work:
            root = Path(work).resolve()
            original, alias = root/'file.dat', root/'alias.dat'
            original.write_bytes(b'one')
            try:
                os.link(original, alias)
            except OSError:
                self.skipTest('Host hardlinks are unavailable')
            ctx = context(rt.DirectoryFiles(root))
            self.assertEqual(issue(ctx, 'APPEND FILE file.dat TO alias.dat')['S'], 102)
            self.assertEqual(alias.read_bytes(), b'one')
            self.assertTrue(original.samefile(alias))

    def test_directory_sorts_names_and_print_validates_before_output(self):
        files = rt.MemoryFiles({'docs/b.txt': b'two', 'docs/a.txt': b'first\n', 'bad.bin': b'a\xff'})
        ctx = context(files)
        output = []
        self.assertEqual(issue(ctx, 'DIRECTORY docs/*.txt', write=output.append)['S'], 0)
        self.assertEqual(issue(ctx, 'PRINT docs/a.txt', write=output.append)['S'], 0)
        self.assertEqual(issue(ctx, 'PRINT bad.bin', write=output.append)['S'], 4)
        self.assertEqual(output, ['docs/a.txt\n', 'docs/b.txt\n', 'first\n'])
        self.assertEqual(issue(ctx, 'DIRECTORY docs/missing.*', write=output.append)['S'], 0)
        self.assertEqual(output[-1], 'first\n')

    def test_output_callback_cannot_reenter_the_command_channel(self):
        ctx = context(rt.MemoryFiles({'in.txt': b'data'}))
        busy = []

        def writer(_):
            task = program("KCL('DELETE FILE in.txt',s)", context=ctx)
            busy.append(task.run()['S'])

        self.assertEqual(issue(ctx, 'PRINT in.txt', write=writer)['S'], 0)
        self.assertEqual(busy, [2])
        self.assertEqual(ctx.files.snapshot(), {'in.txt': b'data'})
        self.assertEqual([row['phase'] for row in ctx.kcl.history], ['completed', 'busy'])

    def test_unsupported_grammar_has_no_effect_and_terminal_config_replays_nothing(self):
        ctx = context(rt.MemoryFiles({'x.txt': b'x'}))
        for command in ('DELETE x.txt', 'APPEND x.txt TO y.txt', 'COPY x.txt y.txt', 'DIRECTORY', 'FORMAT RD:'):
            self.assertEqual(issue(ctx, command)['S'], 1)
        self.assertEqual(issue(ctx, 'COPY x.txt TO S1:')['S'], 4)
        self.assertEqual(ctx.files.snapshot(), {'x.txt': b'x'})
        saved = ctx.to_config()
        restored = rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.kcl.to_config(), saved['kcl'])
        self.assertEqual(restored.files.snapshot(), ctx.files.snapshot())
        with self.assertRaisesRegex(ValueError, 'file_commands requires'):
            rt.KclCommands.from_config({'file_commands': 1})


if __name__ == '__main__':
    unittest.main()
