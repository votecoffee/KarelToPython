"""Checked pre-statement skips and portable headless form packages."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from karel2py import runtime as rt, translate_project
from karel2py.dictionaries import portable_tx
from tests.test_extended_services import compile_program
from tests.test_forms import CALL, DECL, SETUP, context as form_context, ftx
from tests.test_kcl_debug_commands import context as debug_context
from tests.test_kcl_inspection_commands import listing
from tests.test_kcl_task_commands import issue
from tests.test_task_control_broadcasts import advance_until, worker


class KclStatementSkipTests(unittest.TestCase):
    def test_skip_is_bound_to_the_exact_pause_and_precedes_rhs_side_effects(self):
        ctx = debug_context()
        task, result = compile_program(
            's=0\nn=3\nn=effect()\nn=n+1', cooperative=True, context=ctx,
            routines='ROUTINE effect: INTEGER BEGIN s=s+1 RETURN 99 END effect',
        )
        ctx.tasks.bind('WORKER', task)
        line = task.skippable_checkpoints[-2]
        self.assertEqual(result.report['kcl_policy']['skippable_checkpoints'], list(task.skippable_checkpoints))
        self.assertEqual(issue(ctx, f'SET BREAK PROGRAM WORKER 1 {line}')['S'], 0)
        self.assertEqual(issue(ctx, 'SKIP WORKER')['S'], 802)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(listing(ctx, 'SHOW CHECKPOINT WORKER'), (0, [
            {'program': 'T', 'line': line, 'skip': False},
        ]))
        self.assertEqual(issue(ctx, 'SKIP WORKER', nowait=True), {'S': 0, 'N': 0})
        self.assertEqual(issue(ctx, 'SKIP WORKER')['S'], 0)
        self.assertTrue(listing(ctx, 'SHOW CHECKPOINT WORKER')[1][0]['skip'])
        self.assertEqual(task.resume(), {'N': 4, 'S': 0})
        self.assertIsNone(task._state._debug_statement)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertFalse(listing(ctx, 'SHOW CHECKPOINT WORKER')[1][0]['skip'])
        self.assertEqual(task.resume(), {'N': 100, 'S': 1})

    def test_file_skip_bypasses_handle_access_and_preserves_following_work(self):
        ctx = debug_context()
        task, _ = compile_program('n=1\nREAD handle(n)\nn=2',
                                  decl='handle:FILE n:INTEGER', context=ctx)
        ctx.tasks.bind('WORKER', task)
        line = task.skippable_checkpoints[1]
        self.assertEqual(issue(ctx, f'SET BREAK PROGRAM WORKER 1 {line}')['S'], 0)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(issue(ctx, 'SKIP WORKER')['S'], 0)
        self.assertEqual(task.resume()['N'], 2)
        self.assertEqual(task.read_requests, ())

    def test_skip_is_unavailable_for_structural_and_inflight_pauses(self):
        scheduler = rt.TaskScheduler()
        ctx = debug_context(scheduler=scheduler)
        task = worker(ctx, 'WORKER', 'n=1\nIF n=1 THEN\n DELAY 100\nENDIF\nn=2')
        structure = next(line for line in task.source_checkpoints if line not in task.skippable_checkpoints)
        self.assertEqual(issue(ctx, f'SET BREAK PROGRAM WORKER 1 {structure}')['S'], 0)
        scheduler.start('WORKER')
        scheduler.run(max_cycles=40)
        self.assertEqual(issue(ctx, 'SKIP WORKER')['S'], 802)
        scheduler.continue_task('WORKER')
        advance_until(scheduler, lambda: task.task_state == 'waiting')
        self.assertEqual(issue(ctx, 'PAUSE WORKER')['S'], 0)
        scheduler.run(max_cycles=40)
        self.assertEqual(task.task_state, 'paused')
        self.assertEqual(issue(ctx, 'SKIP WORKER')['S'], 802)
        scheduler.continue_task('WORKER')
        self.assertEqual(scheduler.run(max_cycles=40)['WORKER']['values']['N'], 2)

    def test_linked_pause_mark_belongs_to_root_and_abort_retires_it(self):
        ctx = debug_context()
        instance = translate_project({
            'main.kl': 'PROGRAM MAIN VAR n:INTEGER ROUTINE edit(value:INTEGER) FROM LIB BEGIN n=1 edit(n) n=n+1 END MAIN',
            'lib.kl': 'PROGRAM LIB ROUTINE edit(value:INTEGER) BEGIN\n value=7\nEND edit BEGIN END LIB',
        }).instantiate(context=ctx)
        line, = instance.programs['LIB'].skippable_checkpoints
        self.assertEqual(issue(ctx, f'SET BREAK PROGRAM LIB 1 {line}')['S'], 0)
        self.assertEqual(instance.run('MAIN', max_cycles=50)['MAIN']['state'], 'paused')
        self.assertEqual(listing(ctx, 'SHOW CHECKPOINT MAIN')[1][0]['program'], 'LIB')
        self.assertEqual(issue(ctx, 'SKIP MAIN')['S'], 0)
        instance.scheduler.continue_task('MAIN')
        self.assertEqual(instance.scheduler.run(max_cycles=50)['MAIN']['values']['N'], 2)
        instance.scheduler.start('MAIN')
        self.assertEqual(instance.scheduler.run(max_cycles=50)['MAIN']['state'], 'paused')
        self.assertEqual(issue(ctx, 'SKIP MAIN')['S'], 0)
        self.assertEqual(issue(ctx, 'ABORT MAIN')['S'], 0)
        with self.assertRaises(rt.KarelAbort):
            instance.scheduler.run(max_cycles=50)
        self.assertIsNone(instance.programs['MAIN']._state._debug_statement)
        self.assertEqual(instance.programs['MAIN'].snapshot()['N'], 1)


class KclFormPackageTests(unittest.TestCase):
    def context(self, files, *, languages=None):
        return rt.ExecutionContext(files=files, dictionaries=rt.TextDictionaries(languages=languages),
            kcl=rt.KclCommands(dictionary_commands=True, file_commands=True))

    def test_compile_load_and_edit_a_form_via_headless_source_calls(self):
        ctx = form_context(keys=('7','ENTER','F3'), files=rt.MemoryFiles({'FORM.FTX': ftx()}),
                           kcl=rt.KclCommands(dictionary_commands=True))
        self.assertEqual(issue(ctx, 'COMPRESS FORM', nowait=True), {'S': 0, 'N': 0})
        payload = ctx.files.snapshot()
        self.assertEqual(set(payload), {'FORM.FTX', 'FORM.TX', 'FORM.VR'})
        self.assertEqual(json.loads(payload['FORM.VR']), {
            'format': 'karel2py-form-association-v1', 'source': 'FORM', 'dictionary': 'FORM',
            'language': 'DEFAULT', 'forms': [{'number': 1, 'name': 'editor'}],
            'tx_sha256': hashlib.sha256(payload['FORM.TX']).hexdigest(),
        })
        self.assertEqual(issue(ctx, 'LOAD FORM')['S'], 0)
        task, _ = compile_program(SETUP + ' ' + CALL, decl=DECL, context=ctx, sleep=lambda _:None)
        values = task.run()
        self.assertEqual((values['N'],values['STATUS'],values['CHANGED'][0]), (7,0,True))
        self.assertEqual(ctx.forms.active_count, 0)

    def test_incomplete_or_mismatched_pair_cannot_load_a_dictionary(self):
        ctx = self.context(rt.MemoryFiles({'ABMENUFR.FTX': ftx()}), languages=['ENGLISH','FRENCH'])
        self.assertEqual(issue(ctx, 'COMPRESS FORM ABMENUFR')['S'], 0)
        original = ctx.files.snapshot()
        del ctx.files.files['MENU.VR']
        self.assertEqual(issue(ctx, 'LOAD FORM ABMENUFR')['S'], 403)
        ctx.files.files['MENU.VR'] = bytearray(original['MENU.VR'])
        ctx.files.files['ABMENUFR.TX'] = bytearray(portable_tx(ftx('"- Other"')))
        self.assertEqual(issue(ctx, 'LOAD FORM ABMENUFR')['S'], 401)
        self.assertEqual(ctx.dictionaries.loaded, {})
        ctx.files.files['ABMENUFR.TX'] = bytearray(original['ABMENUFR.TX'])
        self.assertEqual(issue(ctx, 'LOAD FORM ABMENUFR')['S'], 0)
        self.assertIn('MENU', ctx.dictionaries.loaded['FRENCH'])
        self.assertEqual(issue(ctx, 'LOAD FORM ABMENUFR')['S'], 402)

    def test_collision_and_device_capacity_reject_both_outputs(self):
        files = rt.MemoryFiles({'FORM.FTX': ftx(), 'FORM.VR': b'prior'})
        ctx = self.context(files)
        before = files.snapshot()
        self.assertEqual(issue(ctx, 'COMPRESS FORM')['S'], 402)
        self.assertEqual(files.snapshot(), before)
        del files.files['FORM.VR']
        self.assertEqual(issue(ctx, 'COMPRESS FORM')['S'], 0)
        pair = files.snapshot()
        size = sum(map(len,pair.values()))
        device = rt.DeviceFiles({'RD:': {'capacity': size-1}}, {'RD:FORM.FTX': ftx()})
        ctx = self.context(device)
        before = device.snapshot()
        self.assertEqual(issue(ctx, 'COMPRESS FORM RD:FORM')['S'], 405)
        self.assertEqual(device.snapshot(), before)
        self.assertEqual(device.to_config()['volumes']['RD:']['garbage'], 0)

    def test_rooted_load_uses_current_directory_and_rejects_rooted_pair_publication(self):
        ctx = self.context(rt.MemoryFiles({'FORM.FTX': ftx()}))
        self.assertEqual(issue(ctx, 'COMPRESS FORM')['S'], 0)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            assets = root / 'Forms'
            assets.mkdir()
            for name,data in ctx.files.snapshot().items():
                (assets / name).write_bytes(data)
            rooted = self.context(rt.DirectoryFiles(root))
            self.assertEqual(issue(rooted, 'CD Forms')['S'], 0)
            self.assertEqual(issue(rooted, 'LOAD FORM')['S'], 0)
            self.assertEqual(rooted.dictionaries.loaded['ENGLISH']['FORM']['text'], ftx())
            (assets / 'NEXT.FTX').write_text(ftx(), encoding='ascii')
            self.assertEqual(issue(rooted, 'COMPRESS FORM NEXT')['S'], 404)
            self.assertEqual(sorted(path.name for path in assets.iterdir()), ['FORM.FTX','FORM.TX','FORM.VR','NEXT.FTX'])


if __name__ == '__main__':
    unittest.main()
