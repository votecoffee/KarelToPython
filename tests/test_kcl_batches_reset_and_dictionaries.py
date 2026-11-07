"""Portable KCL archives, owned RESET and explicit dictionary files."""
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from karel2py import runtime as rt
from karel2py.dictionaries import PORTABLE_TX_HEADER
from tests.test_directive_group_locks import program
from tests.test_extended_services import compile_program
from tests.test_kcl_task_commands import issue
from tests.test_mixed_archives import context as mixed_context, state as mixed_state
from tests.test_task_control_broadcasts import advance_until, worker


class KclBatchTests(unittest.TestCase):
    def setUp(self):
        self.ctx = mixed_context()
        self.ctx.kcl = rt.KclCommands(program_commands=True)

    def test_archive_batch_roundtrip_with_saved_default(self):
        before = mixed_state(self.ctx)
        self.assertEqual(issue(self.ctx, 'SAVE ALL')['S'], 502)
        self.assertEqual(issue(self.ctx, 'SET DEFAULT ROOT')['S'], 0)
        self.assertEqual(issue(self.ctx, 'SAVE ALL', nowait=True), {'S': 0, 'N': 0})
        files = self.ctx.files.snapshot()
        self.assertEqual(set(files), {'ROOT.PB', 'ROOT.TP', 'ROOT.VR', 'WORK.TP', 'DATA.VR'})
        self.assertEqual(issue(self.ctx, 'SAVE ALL ROOT.PB')['S'], 503)
        self.assertEqual(issue(self.ctx, 'CLEAR ALL')['S'], 502)
        self.assertEqual(mixed_state(self.ctx), before)
        self.assertEqual(issue(self.ctx, 'CLEAR ALL Y')['S'], 0)
        self.assertEqual(self.ctx.teach_programs.entries, ())
        self.assertEqual(self.ctx.variables.bindings, {})
        self.assertEqual(issue(self.ctx, 'LOAD ALL')['S'], 0)
        self.assertEqual(mixed_state(self.ctx), before)
        self.assertEqual(self.ctx.files.snapshot(), files)

    def test_manifest_validation_and_destination_guards_precede_publication(self):
        ctx = self.ctx
        self.assertEqual(issue(ctx, 'SAVE ALL FR:batch/ROOT')['S'], 0)
        self.assertEqual(issue(ctx, 'CLEAR ALL YES')['S'], 0)
        member = ctx.files.files['FR:batch/DATA.VR']
        ctx.files.files['FR:batch/DATA.VR'] = bytearray(b'{}')
        self.assertEqual(issue(ctx, 'LOAD ALL FR:batch/ROOT.PB')['S'], 506)
        self.assertEqual((ctx.teach_programs.entries, ctx.variables.bindings), ((), {}))
        ctx.files.files['FR:batch/DATA.VR'] = member
        attached = worker(ctx, 'DATA', 'n=19')
        self.assertEqual(issue(ctx, 'LOAD ALL FR:batch/ROOT.PB')['S'], 504)
        self.assertEqual((ctx.teach_programs.entries, ctx.variables.bindings), ((), {}))
        self.assertEqual(attached.run()['N'], 19)

    def test_clear_protects_both_banks_and_retains_source_and_system_data(self):
        ctx = self.ctx
        ctx.variables.define('SYSTEM', '$LIMIT', ('INTEGER',), 9)
        attached = worker(ctx, 'LIVE', 'n=8 PAUSE')
        with self.assertRaises(rt.KarelPause):
            attached.run()
        ctx.variables.define('LIVE', 'EXPLICIT', ('INTEGER',), 12)
        handle_ref = ctx.variables.define('DATA', 'STREAM', ('FILE',))
        ctx.files.open(handle_ref.raw(), 'WO', 'open')
        before = mixed_state(ctx)
        self.assertEqual(issue(ctx, 'CLEAR ALL YES')['S'], 504)
        self.assertEqual(mixed_state(ctx), before)
        ctx.files.close(handle_ref.raw())
        ctx.teach_programs.selected = 'ROOT'
        self.assertEqual(issue(ctx, 'CLEAR ALL YES')['S'], 504)
        self.assertEqual(set(ctx.variables.bindings), {
            ('DATA', 'STREAM'), ('DATA', 'VALUE'), ('ROOT', 'VALUE'), ('LIVE', 'EXPLICIT'), ('SYSTEM', '$LIMIT'),
        })
        ctx.teach_programs.selected = None
        self.assertEqual(issue(ctx, 'CLEAR ALL YES')['S'], 0)
        self.assertEqual(set(ctx.variables.bindings), {('LIVE', 'EXPLICIT'), ('SYSTEM', '$LIMIT')})
        self.assertEqual(attached.snapshot()['N'], 8)
        self.assertEqual(attached.task_state, 'paused')
        attached.stop()

    def test_missing_manifest_and_save_collision_do_not_use_partial_sidecars(self):
        self.ctx.files.files['ROOT.TP'] = bytearray(b'existing')
        self.assertEqual(issue(self.ctx, 'LOAD ALL ROOT')['S'], 501)
        self.assertEqual(issue(self.ctx, 'SAVE ALL ROOT')['S'], 503)
        self.assertEqual(self.ctx.files.snapshot(), {'ROOT.TP': b'existing'})
        self.assertEqual(issue(self.ctx, 'LOAD ALL ROOT.PC')['S'], 502)


class KclResetTests(unittest.TestCase):
    def context(self, responses, **options):
        return rt.ExecutionContext(controller=rt.ControllerServices(resets=responses),
            ports=rt.PortBank({'OPOUT': 3}, {('OPOUT', 3): True}),
            kcl=rt.KclCommands(task_commands=True, procedure_commands=True), **options)

    def test_blocking_reset_reports_completion_and_preserves_nonblocking_plans(self):
        ctx = self.context([{'completed': False, 'fault': True}, {'completed': True, 'fault': False}])
        self.assertEqual(issue(ctx, 'RESET', nowait=True), {'S': 3, 'N': 3})
        self.assertEqual(len(ctx.controller.resets), 2)
        self.assertEqual(issue(ctx, 'RESET'), {'S': 4, 'N': 4})
        self.assertTrue(ctx.ports.read('OPOUT', 3))
        self.assertEqual(issue(ctx, 'RESET'), {'S': 0, 'N': 0})
        self.assertFalse(ctx.ports.read('OPOUT', 3))
        self.assertEqual(issue(ctx, 'RESET')['S'], 4)
        self.assertEqual(ctx.controller.sequence, 2)

    def test_procedure_can_run_reset_and_uses_its_result(self):
        ctx = self.context([{'completed': True, 'fault': False, 'delay_ms': 20}],
                           files=rt.MemoryFiles({'reset.CF': 'RESET\n'}))
        sleeps = []
        self.assertEqual(issue(ctx, 'RUNCF reset result', sleep=sleeps.append)['S'], 0)
        self.assertEqual(sleeps, [0.01, 0.01])
        self.assertEqual(ctx.files.snapshot()['result.LS'], b'RESET\n')
        self.assertEqual(ctx.controller.elapsed_ms, 20)
        self.assertFalse(ctx.ports.read('OPOUT', 3))

    def test_timed_condition_runs_before_first_reset_interval_finishes(self):
        scheduler=rt.TaskScheduler()
        ctx=self.context([{'completed':True,'fault':False,'delay_ms':30}],tasks=scheduler)
        task=worker(ctx,'OWNER','n=0 s=99 CONDITION[1]: WITH $SCAN_TIME=1 WHEN s=98 DO n=7 '
                    "ENDCONDITION ENABLE CONDITION[1] KCL('RESET',s)")
        scheduler.start('OWNER')
        advance_until(scheduler,lambda:'OWNER' in scheduler.waiting)
        task._state.set('S',98)
        advance_until(scheduler,lambda:task.snapshot()['N']==7)
        self.assertEqual(ctx.controller.elapsed_ms,0)
        self.assertTrue(ctx.ports.read('OPOUT',3))
        self.assertEqual(task.snapshot()['S'],98)
        self.assertEqual(scheduler.run()['OWNER']['values']['S'],0)
        self.assertEqual(ctx.controller.elapsed_ms,30)
        self.assertFalse(ctx.ports.read('OPOUT',3))

    def test_stop_retires_reset_and_releases_channel_without_publishing_fault(self):
        scheduler = rt.TaskScheduler()
        ctx = self.context([{'completed': True, 'fault': False, 'delay_ms': 100}], tasks=scheduler)
        task = worker(ctx, 'OWNER', "s=99 KCL('RESET',s)")
        scheduler.start('OWNER')
        advance_until(scheduler, lambda: task.task_state == 'waiting')
        self.assertEqual(program("KCL('RESET',s)", name='OBSERVER', context=ctx).run()['S'], 2)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'calling activation'):
            program('n=KCL_STATUS', context=ctx).run()
        scheduler.stop('OWNER')
        self.assertEqual((ctx.kcl.last_status, task.snapshot()['S']), (4, 99))
        self.assertTrue(ctx.ports.read('OPOUT', 3))
        self.assertEqual(ctx.controller.history[-1]['outcome'], 'cancelled')
        self.assertEqual(ctx.controller.resets, [])
        ctx.to_config()


class KclDictionaryFileTests(unittest.TestCase):
    def context(self, files, **options):
        return rt.ExecutionContext(files=files, dictionaries=rt.TextDictionaries(**options),
            kcl=rt.KclCommands(dictionary_commands=True, file_commands=True))

    def test_compiled_tx_loads_and_persists_without_reloading_file(self):
        ctx = self.context(rt.MemoryFiles({'Label.UTX': '$1 "Portable"\n'}))
        self.assertEqual(issue(ctx, 'COMPRESS DICT Label', nowait=True), {'S': 0, 'N': 0})
        tx = ctx.files.snapshot()['Label.TX']
        self.assertTrue(tx.startswith(PORTABLE_TX_HEADER))
        self.assertEqual(zlib.decompress(tx[len(PORTABLE_TX_HEADER):]), b'$1 "Portable"\n')
        self.assertEqual(issue(ctx, 'COMPRESS DICT Label')['S'], 402)
        self.assertEqual(ctx.files.snapshot()['Label.TX'], tx)
        self.assertEqual(issue(ctx, 'LOAD DICT Label MenuLong')['S'], 0)
        restored = rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        del restored.files.files['Label.TX']
        task, _ = compile_program("READ_DICT('MENU',1,lines,1,n,s)",
            decl='lines:ARRAY[1] OF STRING[16] n,s:INTEGER', context=restored)
        self.assertEqual(task.run(), {'LINES': ['Portable'], 'N': 1, 'S': 0})

    def test_configured_sources_precede_files_and_rooted_names_follow_chdir(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'Data').mkdir()
            (root / 'Data' / 'label.UTX').write_bytes(b'$1 "Rooted"\n')
            ctx = self.context(rt.DirectoryFiles(root), sources={'label': '$1 "Configured"'})
            self.assertEqual(issue(ctx, 'CD Data')['S'], 0)
            self.assertEqual(issue(ctx, 'COMPRESS DICT label.UTX')['S'], 0)
            self.assertEqual(issue(ctx, 'LOAD DICT label first')['S'], 0)
            self.assertEqual(issue(ctx, 'LOAD DICT label.UTX second')['S'], 0)
            self.assertEqual(ctx.dictionaries.loaded['ENGLISH']['FIRS']['text'], '$1 "Configured"')
            self.assertEqual(ctx.dictionaries.loaded['ENGLISH']['SECO']['text'], '$1 "Rooted"\n')
            self.assertTrue((root / 'Data' / 'label.TX').is_file())

    def test_malformed_and_expanding_streams_and_busy_files_leave_state_intact(self):
        raw = b'$1 "Valid"\n'
        header = PORTABLE_TX_HEADER
        ctx = self.context(rt.MemoryFiles({
            'bad.UTX': b'$1 "unterminated', 'open.UTX': raw,
            'trailing.TX': header+zlib.compress(raw)+b'trailing',
            'large.TX': header+zlib.compress(b' '*65537),
            'invalid.TX': header+b'invalid', 'native.TX': b'\xff\x80',
        }))
        opened = rt.FileHandle()
        ctx.files.open(opened, 'RO', 'open.UTX')
        before = ctx.files.snapshot()
        for command, expected in (
            ('COMPRESS DICT bad', 401), ('COMPRESS DICT open', 404),
            ('LOAD DICT trailing MENU', 401), ('LOAD DICT invalid MENU', 401),
            ('LOAD DICT native MENU', 401), ('LOAD DICT large MENU', 405),
            ('LOAD DICT missing MENU', 403), ('LOAD DICT ../escape MENU', 401),
        ):
            with self.subTest(command=command):
                self.assertEqual(issue(ctx, command)['S'], expected)
                self.assertEqual(ctx.dictionaries.loaded, {})
                self.assertEqual(ctx.files.snapshot(), before)
        ctx.files.close(opened)


if __name__ == '__main__':
    unittest.main()
