"""Opt-in KCL task dispatch through the existing offline drivers."""
import unittest

from karel2py import runtime as rt
from tests.test_directive_group_locks import program
from tests.test_task_control_broadcasts import advance_until, worker
from tests.test_task_lineage import value


def context(*, scheduler=None, **options):
    return rt.ExecutionContext(tasks=scheduler, kcl=rt.KclCommands(task_commands=True, **options))


def issue(ctx, command, *, nowait=False, **options):
    verb = 'KCL_NO_WAIT' if nowait else 'KCL'
    return program(f"{verb}('{command}',s) n=KCL_STATUS", name='OBSERVER', context=ctx, **options).run()


class KclTaskCommandTests(unittest.TestCase):
    def test_scripted_replies_still_take_precedence_and_opt_in_is_required(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                kcl = rt.KclCommands({'RUN WORKER': {'status': 17}}, task_commands=enabled)
                ctx = rt.ExecutionContext(kcl=kcl)
                task = worker(ctx, 'WORKER', 'n=9')
                self.assertEqual(issue(ctx, 'RUN WORKER')['S'], 17)
                self.assertEqual(task.task_state, 'ready')
                self.assertEqual(issue(ctx, 'run  worker')['S'], 0 if enabled else 1)
                self.assertEqual(task.task_state, 'completed' if enabled else 'ready')

    def test_run_starts_independent_of_the_calling_task(self):
        ctx = context()
        child = worker(ctx, 'WORKER', 'n=1 PAUSE n=2')
        parent = worker(ctx, 'MAIN', "KCL('RUN WORKER',s) PAUSE n=3")
        with self.assertRaises(rt.KarelPause):
            parent.run()
        self.assertEqual(parent.snapshot()['S'], 0)
        self.assertEqual(value(ctx, 'MAIN', 'TSK_NUMCLDS'), 0)
        self.assertEqual(value(ctx, 'WORKER', 'TSK_PARENT'), 0)
        parent.resume()
        self.assertEqual(child.snapshot()['N'], 1)
        self.assertEqual(issue(ctx, 'CONT WORKER'), {'N': 0, 'S': 0})
        self.assertEqual(child.snapshot()['N'], 2)

    def test_continue_all_coalesces_paused_children_bound_before_parents(self):
        ctx = context()
        child = worker(ctx, 'WORKER', 'n=1 PAUSE n=2 PAUSE n=3')
        parent = worker(ctx, 'MAIN', "RUN_TASK('WORKER',0,FALSE,FALSE,0,s) PAUSE n=7 PAUSE")
        ctx.tasks.bind('ALIAS', child)
        with self.assertRaises(rt.KarelPause):
            parent.run()
        self.assertEqual(issue(ctx, 'CONTINUE ALL')['S'], 0)
        self.assertEqual((parent.task_state, child.task_state), ('paused', 'paused'))
        self.assertEqual((parent.snapshot()['N'], child.snapshot()['N']), (7, 2))
        self.assertEqual(child._state._lifecycle['CONTINUE'], 1)
        self.assertEqual(issue(ctx, 'RUN ALIAS')['S'], 0)
        self.assertEqual(child.snapshot()['N'], 3)
        parent.stop()

    def test_nowait_dispatches_scheduler_admission_but_preserves_child_execution(self):
        scheduler = rt.TaskScheduler()
        ctx = context(scheduler=scheduler)
        task = worker(ctx, 'WORKER', 'n=1 PAUSE n=2')
        self.assertEqual(issue(ctx, 'RUN WORKER', nowait=True), {'N': 0, 'S': 0})
        self.assertEqual(task.task_state, 'running')
        self.assertEqual(task.snapshot()['N'], {'uninitialized': True})
        scheduler.run()
        execution = task._execution
        self.assertEqual(issue(ctx, 'CONTINUE WORKER', nowait=True)['S'], 0)
        self.assertIs(task._execution, execution)
        self.assertEqual(scheduler.run()['WORKER']['values']['N'], 2)

    def test_scheduler_admission_error_has_separate_acceptance_and_completion(self):
        scheduler = rt.TaskScheduler()
        bank = rt.GroupLocks([1], apply_directives=True)
        ctx = rt.ExecutionContext(tasks=scheduler, kcl=rt.KclCommands(task_commands=True), group_locks=bank)
        task = worker(ctx, 'WORKER', 'n=9', prefix='%LOCKGROUP=1')
        holder = worker(ctx, 'HOLDER', 'PAUSE', prefix='%LOCKGROUP=1')
        scheduler.start('HOLDER')
        scheduler.run()
        results = program("KCL_NO_WAIT('RUN WORKER',s) n=KCL_STATUS", prefix='%NOLOCKGROUP', context=ctx).run()
        self.assertEqual(results, {'N': 4, 'S': 0})
        self.assertIs(bank.owners[1], holder._state)
        self.assertEqual(task.task_state, 'ready')
        self.assertNotIn('pending', ctx.kcl.snapshot())
        holder.stop()

    def test_pause_abort_broadcasts_honor_masks_unless_forced(self):
        scheduler = rt.TaskScheduler()
        ctx = context(scheduler=scheduler)
        protected = worker(ctx, 'PROTECTED', prefix='%NOPAUSE=COMMAND\n%NOABORT=COMMAND')
        ordinary = worker(ctx, 'ORDINARY')
        scheduler.bind('ALIAS', ordinary)
        for name in ('PROTECTED', 'ORDINARY'):
            scheduler.start(name)
        advance_until(scheduler, lambda: protected.task_state == ordinary.task_state == 'waiting')
        self.assertEqual(issue(ctx, 'PAUSE ALL')['S'], 0)
        advance_until(scheduler, lambda: ordinary.task_state == 'paused')
        self.assertEqual(protected.task_state, 'waiting')
        self.assertEqual(issue(ctx, 'PAUSE PROTECTED FORCE', nowait=True)['S'], 0)
        advance_until(scheduler, lambda: protected.task_state == 'paused')

        self.assertEqual(issue(ctx, 'ABORT ALL')['S'], 0)
        self.assertTrue(ordinary._state._abort_requested)
        self.assertFalse(protected._state._abort_requested)
        self.assertEqual(issue(ctx, 'ABORT ALL FORCE')['S'], 0)
        for _ in range(2):
            with self.assertRaises(rt.KarelAbort):
                scheduler.run()
        self.assertEqual((ordinary.task_state, protected.task_state), ('aborted', 'aborted'))

    def test_self_requests_publish_status_before_checkpoint(self):
        for action, exception, end in (('PAUSE', rt.KarelPause, 'paused'),
                                       ('ABORT', rt.KarelAbort, 'aborted')):
            with self.subTest(action=action):
                ctx = context()
                task = worker(ctx, 'WORKER', f"KCL('{action} WORKER',s)")
                with self.assertRaises(exception):
                    task.run()
                self.assertEqual(task.task_state, end)
                self.assertEqual(task.snapshot()['S'], 0)
                self.assertEqual((ctx.kcl.last_status, ctx.kcl.history[-1]['phase']), (0, 'completed'))
                task.stop()

    def test_ineligible_and_unrecognized_requests_leave_target_unchanged(self):
        ctx = context()
        task = worker(ctx, 'WORKER', 'n=9')
        cases = [('RUN UNKNOWN', False, 3), ('CONT WORKER', False, 3), ('RUN WORKER', True, 3),
                 ('RUN', False, 1), ('RUN ALL', False, 1), ('RUN WORKER FORCE', False, 1),
                 ('RUN WORKER;BAD', False, 1), ('CLEAR ALL', False, 1)]
        for command, nowait, status in cases:
            with self.subTest(command=command):
                self.assertEqual(issue(ctx, command, nowait=nowait), {'N': status, 'S': status})
                self.assertEqual(task.task_state, 'ready')

    def test_foreign_live_task_cannot_be_driven_or_controlled(self):
        own, foreign = rt.TaskScheduler(), rt.TaskScheduler()
        ctx, foreign_ctx = context(scheduler=own), context(scheduler=foreign)
        task = worker(foreign_ctx, 'WORKER', 'PAUSE n=7')
        own.bind('WORKER', task)
        foreign.start('WORKER')
        foreign.run()
        for command in ('RUN WORKER', 'CONTINUE WORKER', 'ABORT WORKER FORCE'):
            self.assertEqual(issue(ctx, command)['S'], 3)
        self.assertEqual(task.task_state, 'paused')
        self.assertFalse(task._state._abort_requested)
        foreign.stop('WORKER')

    def test_pending_scripted_reply_and_synchronous_dispatch_share_busy_channel(self):
        ctx = context(replies={'SHOW': {'status': 17, 'delay_ms': 5}})
        task = worker(ctx, 'WORKER', "KCL('PAUSE ALL',s) n=9")
        values = program("KCL_NO_WAIT('SHOW',s) KCL('RUN WORKER',n) s=KCL_STATUS",
                         context=ctx, clock_us=lambda: 0, sleep=lambda _: None).run()
        self.assertEqual(values, {'N': 2, 'S': 17})
        self.assertEqual(task.task_state, 'ready')
        self.assertEqual(issue(ctx, 'RUN WORKER')['S'], 0)
        self.assertEqual(task.snapshot(), {'N': 9, 'S': 2})
        self.assertEqual([row['phase'] for row in ctx.kcl.history], ['completed', 'busy', 'completed', 'busy'])
        self.assertEqual(ctx.kcl.last_status, 0)

    def test_synchronous_execution_failure_completes_command_and_clears_busy(self):
        ctx = context()
        task = worker(ctx, 'WORKER', 'n=n+1')
        self.assertEqual(issue(ctx, 'RUN WORKER'), {'N': 4, 'S': 4})
        self.assertEqual(task.task_state, 'failed')
        self.assertNotIn('pending', ctx.kcl.snapshot())
        self.assertEqual(ctx.kcl.history[-1]['phase'], 'completed')
        self.assertEqual(issue(ctx, 'ABORT WORKER')['S'], 3)
        saved = ctx.to_config()
        restored = rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.kcl.to_config(), saved['kcl'])
        self.assertEqual(restored.tasks.tasks, {})
        with self.assertRaisesRegex(ValueError, 'task_commands requires'):
            rt.KclCommands.from_config({'task_commands': 1})


if __name__ == '__main__':
    unittest.main()
