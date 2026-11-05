"""RUN_TASK entry hints and exact continuation across both task drivers."""
import unittest

from karel2py import runtime as rt, translate_project
from tests.test_directive_group_locks import program, source


def command(target='CHILD', line_hint=0, pause=False, motion=False, mask=0):
    return (f"RUN_TASK('{target}',{line_hint},{str(pause).upper()},"
            f"{str(motion).upper()},{mask},s)")


def registry_pair(body, *, prefix='', **options):
    tasks = rt.TaskRegistry()
    context = rt.ExecutionContext(tasks=tasks, **options)
    child = program(body, name='CHILD', prefix=prefix, context=context)
    tasks.bind('CHILD', child)
    return context, child


def caller(context, request, **options):
    return program(request, context=context, **options)


class TaskRegistryRunTests(unittest.TestCase):
    def test_nonnegative_line_hint_starts_at_karel_main_entry(self):
        context, child = registry_pair('n=7 n=n+2')
        result = caller(context, command(line_hint=999)).run()
        self.assertEqual(result['S'], 0)
        self.assertEqual(child.snapshot()['N'], 9)
        self.assertEqual(child.task_state, 'completed')

    def test_run_task_continues_same_routine_frame_and_sends_one_event(self):
        context = rt.ExecutionContext()
        linked = translate_project({'child': source(
            'CHILD', 'n=0 work()', routines=(
                'ROUTINE work VAR x:INTEGER BEGIN '
                'x=11 PAUSE n=x x=x+1 PAUSE n=x END work'
            ),
        )})
        child = linked.instantiate().programs['CHILD']
        context.tasks.bind('CHILD', child)
        self.assertEqual(caller(context, command()).run()['S'], 0)
        execution = child._execution
        frame = child._state.local_frames[-1]
        self.assertEqual(child.snapshot()['N'], 0)
        self.assertEqual(caller(context, command(line_hint=10, pause=True)).run()['S'], 0)
        self.assertIs(child._execution, execution)
        self.assertIs(child._state.local_frames[-1], frame)
        self.assertEqual(child.snapshot()['N'], 11)
        self.assertEqual(child._state._lifecycle['CONTINUE'], 1)
        self.assertEqual(caller(context, command(line_hint=50)).run()['S'], 0)
        self.assertEqual(child.snapshot()['N'], 12)
        self.assertEqual(child._state._lifecycle['CONTINUE'], 2)
        self.assertEqual(child.task_state, 'completed')

    def test_resume_runs_continue_handler_once(self):
        body = ('n=0 CONDITION[1]: WHEN CONTINUE DO n=n+1 ENDCONDITION '
                'ENABLE CONDITION[1] PAUSE s=n n=n+10')
        context, child = registry_pair(body)
        caller(context, command()).run()
        caller(context, command()).run()
        self.assertEqual(child.snapshot(), {'N': 11, 'S': 1})

    def test_start_pause_applies_only_to_fresh_entry(self):
        context, child = registry_pair('n=9')
        request = command(line_hint=444, pause=True)
        self.assertEqual(caller(context, request).run()['S'], 0)
        self.assertEqual(child.task_state, 'paused')
        self.assertEqual(child.snapshot()['N'], {'uninitialized': True})
        self.assertEqual(caller(context, request).run()['S'], 0)
        self.assertEqual(child.task_state, 'completed')
        self.assertEqual(child.snapshot()['N'], 9)

    def test_failed_paused_entry_request_does_not_leak_to_retry(self):
        bank = rt.GroupLocks([1], apply_directives=True)
        context, child = registry_pair('n=9', prefix='%LOCKGROUP=1', group_locks=bank)
        owner = program(name='HOLDER', context=context, prefix='%NOLOCKGROUP')
        bank.update(owner._state, 'LOCK_GROUP', 1)
        parent = caller(context, 's=77 ' + command(pause=True), prefix='%NOLOCKGROUP')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'another task'):
            parent.run()
        self.assertEqual(parent.snapshot()['S'], 77)
        self.assertFalse(child._state._pause_requested)
        self.assertIsNone(getattr(child, '_execution', None))
        bank.release_owner(owner._state)
        self.assertEqual(child.run()['N'], 9)
        self.assertEqual(child.task_state, 'completed')

    def test_active_standalone_target_is_not_left_with_a_pause_request(self):
        tasks = rt.TaskRegistry()
        context = rt.ExecutionContext(tasks=tasks)
        parent = caller(context, command(pause=True))
        attempts = []

        def sleep(seconds):
            attempts.append(seconds)
            with self.assertRaisesRegex(rt.KarelRuntimeError, 'already active'):
                parent.run()
            self.assertFalse(child._state._pause_requested)

        child = program('n=1 DELAY 1 n=2', name='CHILD', context=context, sleep=sleep)
        tasks.bind('CHILD', child)
        self.assertEqual(child.run()['N'], 2)
        self.assertEqual(attempts, [.001])
        self.assertEqual(child.task_state, 'completed')

    def test_invalid_launch_options_preserve_paused_task(self):
        context, child = registry_pair('n=1 PAUSE n=2')
        caller(context, command()).run()
        execution = child._execution
        for args, pattern in ((dict(line_hint=-1), 'nonnegative'),
                              (dict(motion=True), 'no motion'),
                              (dict(mask=1), 'lock mask 0')):
            with self.subTest(args=args):
                task = caller(context, 's=77 ' + command(**args))
                with self.assertRaisesRegex(rt.KarelRuntimeError, pattern):
                    task.run()
                self.assertEqual(task.snapshot()['S'], 77)
                self.assertIs(child._execution, execution)
                self.assertEqual(child.task_state, 'paused')
                self.assertEqual(child._state._lifecycle['CONTINUE'], 0)
        child.stop()

    def test_missing_target_reports_existing_status(self):
        context, child = registry_pair('n=9')
        self.assertEqual(caller(context, command(target='UNKNOWN')).run()['S'], 1)
        self.assertEqual(child.task_state, 'ready')

    def test_resumed_child_termination_returns_control_to_caller(self):
        for action, state in (('ABORT', 'aborted'), ('STOP', 'stopped')):
            with self.subTest(action=action):
                context, child = registry_pair('PAUSE ' + action)
                caller(context, command()).run()
                parent = caller(context, command() + ' n=9')
                self.assertEqual(parent.run(), {'N': 9, 'S': 0})
                self.assertEqual(child.task_state, state)


class ScheduledRunTests(unittest.TestCase):
    def project(self, body, request=None, bank=None):
        return translate_project({
            'main': source(body=request or command(line_hint=200, pause=True), prefix='%NOLOCKGROUP'),
            'child': source('CHILD', body, prefix='%LOCKGROUP=1'),
        }).instantiate(context=rt.ExecutionContext(group_locks=bank))

    def advance_until(self, scheduler, predicate):
        for _ in range(100):
            if predicate():
                return
            scheduler.step()
        self.fail('Scheduler did not reach the expected state')

    def test_source_resumes_owning_scheduler_and_keeps_group_grant(self):
        bank = rt.GroupLocks([1], apply_directives=True)
        linked = self.project('n=1 PAUSE n=2 PAUSE n=3', bank=bank)
        scheduler = linked.scheduler
        child = linked.programs['CHILD']
        scheduler.start('CHILD')
        scheduler.run()
        execution = child._execution
        grant = bank._ownership_tokens[1]
        result = linked.run('MAIN')
        self.assertEqual(result['MAIN']['values']['S'], 0)
        self.assertEqual((child.task_state, child.snapshot()['N']), ('paused', 2))
        self.assertIs(child._execution, execution)
        self.assertIs(bank._ownership_tokens[1], grant)
        self.assertIs(bank.owners[1], child._state)
        linked.run('MAIN')
        self.assertEqual(child.snapshot()['N'], 3)
        self.assertEqual(bank.owners, {})

    def test_run_task_resume_keeps_original_sleep_deadline(self):
        linked = self.project('n=1 DELAY 100 n=2')
        scheduler = linked.scheduler
        child = linked.programs['CHILD']
        scheduler.start('CHILD')
        self.advance_until(scheduler, lambda: child.task_state == 'waiting')
        deadline = scheduler.waiting['CHILD']
        child.pause()
        self.advance_until(scheduler, lambda: child.task_state == 'paused')
        execution = child._execution
        scheduler.start('MAIN')
        self.advance_until(scheduler, lambda: child.task_state == 'waiting')
        self.assertEqual(scheduler.waiting['CHILD'], deadline)
        self.assertIs(child._execution, execution)
        self.assertEqual(scheduler.run()['CHILD']['values']['N'], 2)

    def test_foreign_scheduler_cannot_adopt_paused_task_through_run_or_continue(self):
        linked = self.project('PAUSE n=8')
        owner = linked.scheduler
        child = linked.programs['CHILD']
        owner.start('CHILD')
        owner.run()
        execution = child._execution
        foreign = rt.TaskScheduler()
        foreign.bind('ALIAS', child)
        context = rt.ExecutionContext(tasks=foreign)
        for request in (command(target='alias'), "CONT_TASK('ALIAS',s)"):
            with self.subTest(request=request):
                task = caller(context, 's=77 ' + request)
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'owning TaskScheduler'):
                    task.run()
                self.assertEqual(task.snapshot()['S'], 77)
                self.assertIs(child._execution, execution)
                self.assertEqual(child.task_state, 'paused')
                self.assertEqual(child._state._lifecycle['CONTINUE'], 0)
        owner.continue_task('CHILD')
        self.assertEqual(owner.run()['CHILD']['values']['N'], 8)

    def test_scheduler_cannot_adopt_paused_standalone_task(self):
        child = program('PAUSE n=5', name='CHILD')
        with self.assertRaises(rt.KarelPause):
            child.run()
        scheduler = rt.TaskScheduler()
        scheduler.bind('CHILD', child)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'owning TaskScheduler'):
            scheduler.continue_task('CHILD')
        self.assertEqual(child.task_state, 'paused')
        self.assertEqual(child.resume()['N'], 5)


if __name__ == '__main__':
    unittest.main()
