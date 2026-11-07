"""Authored cooperative task waits and rooted KCL directory behavior."""
import os
from pathlib import Path
import tempfile
import unittest

from karel2py import runtime as rt
from tests.test_directive_group_locks import program
from tests.test_kcl_task_commands import issue
from tests.test_task_control_broadcasts import worker


class KclTaskWaitTests(unittest.TestCase):
    def context(self, **options):
        scheduler = rt.TaskScheduler()
        return scheduler, rt.ExecutionContext(tasks=scheduler, kcl=rt.KclCommands(task_commands=True, **options))

    def test_blocking_wait_uses_scheduler_deadlines_and_captured_result(self):
        scheduler, ctx = self.context()
        worker(ctx, 'CHILD', 'DELAY 8000000 n=7')
        worker(ctx, 'WATCH', "KCL('WAIT CHILD DONE',s) n=KCL_STATUS")
        scheduler.start('CHILD')
        scheduler.start('WATCH')
        state = scheduler.run(max_cycles=30)
        self.assertEqual(state['WATCH'], {'state': 'completed', 'values': {'N': 0, 'S': 0}})
        self.assertEqual(state['CHILD']['values']['N'], 7)
        self.assertGreaterEqual(scheduler.now_us, 8_000_000_000)
        self.assertEqual([row['phase'] for row in ctx.kcl.history], ['completed'])
        self.assertEqual(scheduler._task_waits, {})

    def test_timed_handler_resumes_target_during_task_wait(self):
        for call in ("KCL('WAIT CHILD DONE',s)", "KCL_NO_WAIT('WAIT CHILD DONE',s) s=KCL_STATUS"):
            with self.subTest(call=call):
                scheduler,ctx=self.context()
                worker(ctx,'CHILD','PAUSE n=7')
                watch=worker(ctx,'WATCH',
                             'n=0 CONNECT TIMER TO n CONDITION[1]: WITH $SCAN_TIME=20 '
                             "WHEN n>=20 DO CONT_TASK('CHILD',s) ENDCONDITION ENABLE CONDITION[1] "+call)
                scheduler.start('CHILD')
                self.assertEqual(scheduler.run()['CHILD']['state'],'paused')
                scheduler.start('WATCH')
                result=scheduler.run(max_cycles=40)
                self.assertEqual((result['CHILD']['state'],result['CHILD']['values']['N']),('completed',7))
                self.assertEqual((result['WATCH']['state'],watch.snapshot()['S']),('completed',0))
                self.assertGreaterEqual(watch.snapshot()['N'],20)
                self.assertEqual(scheduler._task_waits,{})

    def test_direct_program_stop_clears_scheduler_deadline_and_completes_waiter(self):
        scheduler,ctx=self.context()
        child=worker(ctx,'CHILD','DELAY 8000000 n=7')
        scheduler.bind('ALIAS',child)
        scheduler.start('ALIAS')
        for _ in range(5):
            scheduler.step()
            if child.task_state=='waiting':
                break
        self.assertIn('CHILD',scheduler.waiting)
        observer=program("KCL_NO_WAIT('WAIT CHILD DONE',s)",context=ctx)
        self.assertEqual(observer.run()['S'],0)
        self.assertEqual(ctx.kcl.history[-1]['phase'],'pending')
        child.stop()
        self.assertEqual((child.task_state,scheduler.waiting,scheduler._task_waits),('stopped',{},{}))
        self.assertEqual((ctx.kcl.history[-1]['phase'],ctx.kcl.history[-1]['status']),('completed',0))

    def test_done_can_quiesce_on_pause_and_tracks_bound_identity_through_rename(self):
        scheduler, ctx = self.context()
        worker(ctx, 'CHILD', 'PAUSE n=7')
        watcher = worker(ctx, 'WATCH', 'CONDITION[1]: WITH $SCAN_TIME=10 WHEN TRUE DO n=7 ENDCONDITION '
                         "KCL('WAIT CHILD DONE',s) n=KCL_STATUS")
        scheduler.start('CHILD')
        scheduler.start('WATCH')
        state = scheduler.run(max_cycles=30)
        self.assertEqual((state['CHILD']['state'], state['WATCH']['state']), ('paused', 'waiting'))
        with self.assertRaisesRegex(ValueError, 'Cannot persist a pending KCL'):
            ctx.to_config()
        self.assertEqual(program("KCL('RUN CHILD',s)", context=ctx).run()['S'], 2)
        self.assertEqual(scheduler.rename('CHILD', 'RENAMED'), 0)
        self.assertEqual(scheduler.rename('WATCH', 'NEW_WATCH'), 0)
        scheduler.continue_task('RENAMED')
        scheduler.run(max_cycles=30)
        self.assertEqual(watcher.snapshot(), {'N': 0, 'S': 0})
        self.assertEqual(ctx.kcl.history[0]['phase'], 'completed')
        self.assertNotIn('pending', ctx.kcl.snapshot())

    def test_nowait_pause_completes_before_target_resumes(self):
        scheduler, ctx = self.context()
        child = worker(ctx, 'CHILD', 'PAUSE n=7')
        scheduler.start('CHILD')
        observer = program("KCL_NO_WAIT('WAIT CHILD PAUSE',s)", context=ctx)
        self.assertEqual(observer.run()['S'], 0)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'owning scheduler'):
            program('n=KCL_STATUS', name='READER', context=ctx).run()
        self.assertEqual(ctx.kcl.history[0]['phase'], 'pending')
        scheduler.run(max_cycles=30)
        self.assertEqual(child.task_state, 'paused')
        self.assertEqual(ctx.kcl.history[0]['phase'], 'completed')
        scheduler.continue_task('CHILD')
        scheduler.run(max_cycles=30)
        self.assertEqual(program('n=KCL_STATUS', context=ctx).run()['N'], 0)

    def test_caller_abort_retains_wait_and_target_failure_completes_with_error(self):
        scheduler, ctx = self.context()
        worker(ctx, 'CHILD', 'DELAY 100 n=n+1')
        worker(ctx, 'WATCH', "KCL_NO_WAIT('WAIT CHILD DONE',s) ABORT")
        scheduler.start('CHILD')
        scheduler.start('WATCH')
        with self.assertRaises(rt.KarelAbort):
            scheduler.run(max_cycles=30)
        self.assertEqual(ctx.kcl.history[0]['phase'], 'pending')
        with self.assertRaises(rt.KarelRuntimeError):
            scheduler.run(max_cycles=30)
        self.assertEqual(ctx.kcl.history[0]['status'], 4)
        self.assertEqual(scheduler._task_waits, {})
        self.assertEqual(program('n=KCL_STATUS', context=ctx).run()['N'], 4)

    def test_rejects_self_idle_and_pending_standalone_waits_and_prefers_replies(self):
        scheduler, ctx = self.context(replies={'WAIT MISSING DONE': {'status': 17}})
        child = worker(ctx, 'CHILD', 'PAUSE n=7')
        self.assertEqual(issue(ctx, 'WAIT MISSING DONE')['S'], 17)
        self.assertEqual(issue(ctx, 'WAIT CHILD DONE')['S'], 3)
        scheduler.start('CHILD')
        self.assertEqual(issue(ctx, 'WAIT CHILD DONE')['S'], 3)
        self.assertEqual(issue(ctx, 'WAIT DONE')['S'], 1)
        scheduler.run(max_cycles=30)
        self.assertEqual(issue(ctx, 'WAIT CHILD PAUSE')['S'], 0)
        scheduler.stop('CHILD')
        self.assertEqual(child.task_state, 'stopped')
        self.assertEqual(issue(ctx, 'WAIT CHILD DONE')['S'], 0)
        own = worker(ctx, 'OWN', "KCL('WAIT OWN DONE',s)")
        scheduler.start('OWN')
        scheduler.run(max_cycles=30)
        self.assertEqual(own.snapshot()['S'], 3)


class KclDirectoryTests(unittest.TestCase):
    def context(self, files, **options):
        return rt.ExecutionContext(files=files, kcl=rt.KclCommands(file_commands=True, **options))

    def test_rooted_commands_select_portable_paths_without_changing_host_cwd(self):
        before = os.getcwd()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'Device').mkdir()
            (root / 'Device' / 'part.txt').write_text('part', encoding='ascii')
            (root / 'part.txt').write_text('root', encoding='ascii')
            ctx = self.context(rt.DirectoryFiles(root, devices={'RD': 'Device'}))
            self.assertEqual(issue(ctx, 'MKDIR RD:/Jobs')['S'], 0)
            self.assertEqual(issue(ctx, 'CD RD:\\')['S'], 0)
            output = []
            self.assertEqual(issue(ctx, 'CHDIR', write=output.append)['S'], 0)
            self.assertEqual(issue(ctx, 'TYPE part.txt', write=output.append)['S'], 0)
            self.assertEqual(output, ['Device\n', 'part'])
            self.assertEqual(issue(ctx, 'COPY part.txt TO Jobs/copied.txt')['S'], 0)
            self.assertEqual((root / 'Device/Jobs/copied.txt').read_bytes(), b'part')
            self.assertEqual(issue(ctx, 'CD Jobs')['S'], 0)
            output.clear()
            self.assertEqual(issue(ctx, 'DIRECTORY *', write=output.append)['S'], 0)
            self.assertEqual(output, ['Device/Jobs/copied.txt\n'])
            self.assertEqual(issue(ctx, 'CD ..')['S'], 0)
            self.assertEqual(issue(ctx, 'RMDIR Jobs')['S'], 103)
            self.assertEqual(issue(ctx, 'DELETE FILE Jobs/copied.txt')['S'], 0)
            self.assertEqual(issue(ctx, 'RMDIR Jobs')['S'], 0)
            self.assertEqual(issue(ctx, 'CD /')['S'], 0)
            output.clear()
            self.assertEqual(issue(ctx, 'TYPE part.txt', write=output.append)['S'], 0)
            self.assertEqual(output, ['root'])
        self.assertEqual(os.getcwd(), before)

    def test_invalid_busy_and_active_directory_guards_and_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'Data').mkdir()
            (root / 'Data' / 'Nested').mkdir()
            ctx = self.context(rt.DirectoryFiles(root, devices={'RD': ''}))
            self.assertEqual(issue(ctx, 'CD ..')['S'], 102)
            self.assertEqual(issue(ctx, 'MKDIR ../escape')['S'], 4)
            self.assertEqual(issue(ctx, 'MKDIR missing/child')['S'], 101)
            self.assertEqual(issue(ctx, 'MKDIR Data')['S'], 102)
            self.assertEqual(issue(ctx, 'CD Data/Nested')['S'], 0)
            self.assertEqual(issue(ctx, 'RMDIR RD:Data')['S'], 103)
            self.assertEqual(issue(ctx, 'CD /')['S'], 0)
            handle = rt.FileHandle()
            ctx.files.open(handle, 'WO', 'Data/Nested/busy.txt')
            self.assertEqual(issue(ctx, 'RMDIR Data/Nested')['S'], 103)
            ctx.files.close(handle)
            self.assertEqual(issue(ctx, 'CD Data')['S'], 0)
            saved = ctx.to_config()
            restored = rt.ExecutionContext.from_config(saved)
            self.assertEqual(issue(restored, 'TYPE Nested/busy.txt')['S'], 4)
            restored.files = rt.DirectoryFiles(root)
            self.assertEqual(issue(restored, 'TYPE Nested/busy.txt')['S'], 0)
            self.assertEqual(restored.kcl.snapshot()['working_directory'], 'Data')
        for value in ('../escape','/absolute','RD:Data','Data\\Nested','*'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rt.KclCommands.from_config({'file_commands': True, 'working_directory': value})

    def test_type_reuses_plain_ascii_output_and_directories_require_rooted_backend(self):
        ctx = self.context(rt.MemoryFiles({'text.txt': b'text', 'binary.txt': b'\xff'}))
        output = []
        self.assertEqual(issue(ctx, 'TYPE text.txt', write=output.append)['S'], 0)
        self.assertEqual(issue(ctx, 'TYPE binary.txt', write=output.append)['S'], 4)
        self.assertEqual(output, ['text'])
        for command in ('CHDIR', 'MKDIR sub', 'RMDIR sub'):
            self.assertEqual(issue(ctx, command)['S'], 4)
