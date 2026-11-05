"""Forced task requests, live broadcasts and scheduler alias ownership."""
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from tests.test_directive_group_locks import program


def scheduled():
    scheduler = rt.TaskScheduler()
    return scheduler, rt.ExecutionContext(tasks=scheduler)


def worker(context, name, body='n=1 DELAY 100 n=2', **options):
    task = program(body, name=name, context=context, **options)
    context.tasks.bind(name, task)
    return task


def request(context, action, name, force=True, motion=False):
    body = f"{action}_TASK('{name}',{str(force).upper()},{str(motion).upper()},s)"
    return program('s=77 ' + body, context=context, name='CALLER')


def advance_until(scheduler, condition):
    for _ in range(100):
        if condition():
            return
        scheduler.step()
    raise AssertionError('Scheduler did not reach the expected state')


class ForcedTaskControlTests(unittest.TestCase):
    def test_forced_pause_bypasses_command_mask_and_retains_frame(self):
        scheduler, ctx = scheduled()
        task = worker(ctx, 'WORKER', prefix='%NOPAUSE=COMMAND')
        scheduler.start('WORKER')
        advance_until(scheduler, lambda: task.task_state == 'waiting')
        execution = task._execution
        self.assertEqual(request(ctx, 'PAUSE', 'worker', False).run()['S'], 0)
        self.assertFalse(task._state._pause_requested)
        self.assertEqual(request(ctx, 'PAUSE', 'worker').run()['S'], 0)
        scheduler.run()
        self.assertEqual(task.task_state, 'paused')
        self.assertIs(task._execution, execution)
        self.assertEqual(task.snapshot()['N'], 1)
        scheduler.continue_task('WORKER')
        self.assertEqual(scheduler.run()['WORKER']['values']['N'], 2)

    def test_forced_abort_bypasses_command_mask_of_paused_target(self):
        scheduler, ctx = scheduled()
        task = worker(ctx, 'WORKER', 'n=7 PAUSE n=9', prefix='%NOABORT=COMMAND')
        scheduler.start('WORKER')
        scheduler.run()
        self.assertEqual(request(ctx, 'ABORT', 'WORKER', False).run()['S'], 0)
        self.assertEqual(task.task_state, 'paused')
        self.assertEqual(request(ctx, 'ABORT', 'WORKER').run()['S'], 0)
        with self.assertRaises(rt.KarelAbort):
            scheduler.run()
        self.assertEqual((task.task_state, task.snapshot()['N']), ('aborted', 7))

    def test_forced_self_request_status_is_visible_to_handler(self):
        ctx = rt.ExecutionContext()
        body = ("n=0 CONDITION[1]: WHEN ABORT DO n=s+1 NOABORT ENDCONDITION "
                "ENABLE CONDITION[1] ABORT_TASK('WORKER',TRUE,FALSE,s) n=n+10")
        task = worker(ctx, 'WORKER', body, prefix='%NOABORT=COMMAND')
        self.assertEqual(task.run(), {'N': 11, 'S': 0})

    def test_invalid_motion_flag_changes_neither_status_nor_task(self):
        scheduler, ctx = scheduled()
        task = worker(ctx, 'WORKER')
        scheduler.start('WORKER')
        caller = request(ctx, 'ABORT', '*ALL*', motion=True)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'Motion-stop'):
            caller.run()
        self.assertEqual(caller.snapshot()['S'], 77)
        self.assertFalse(task._state._abort_requested)
        self.assertEqual(task.task_state, 'running')
        scheduler.stop('WORKER')


class BroadcastTaskControlTests(unittest.TestCase):
    def test_pause_selects_live_roots_once_and_ignores_force(self):
        scheduler, ctx = scheduled()
        task = worker(ctx, 'WORKER')
        guarded = worker(ctx, 'GUARDED', prefix='%NOPAUSE=COMMAND')
        ready = worker(ctx, 'READY')
        scheduler.bind('ALIAS', task)
        scheduler.start('ALIAS')
        scheduler.start('GUARDED')
        advance_until(scheduler, lambda: len(scheduler.waiting) == 2)
        with patch('karel2py.control.request_task_control', wraps=rt.request_task_control) as queue:
            self.assertEqual(request(ctx, 'PAUSE', '*all*').run()['S'], 0)
        self.assertEqual([call.args[0] for call in queue.call_args_list], [task._state, guarded._state])
        self.assertTrue(all(call.kwargs['force'] is False for call in queue.call_args_list))
        self.assertFalse(guarded._state._pause_requested)
        self.assertFalse(ready._state._pause_requested)
        scheduler.run()
        self.assertEqual((task.task_state, guarded.task_state, ready.task_state),
                         ('paused', 'completed', 'ready'))
        scheduler.stop('ALIAS')

    def test_broadcast_abort_wakes_paused_task_and_keeps_masks(self):
        scheduler, ctx = scheduled()
        child = worker(ctx, 'CHILD', 'n=1 PAUSE n=2')
        protected = worker(ctx, 'PROTECTED', 'n=3 PAUSE n=4', prefix='%NOABORT=COMMAND')
        ready = worker(ctx, 'READY')
        scheduler.start('CHILD')
        scheduler.start('PROTECTED')
        scheduler.run()
        self.assertEqual(request(ctx, 'ABORT', '*ALL*').run()['S'], 0)
        self.assertTrue(child._state._abort_requested)
        self.assertFalse(protected._state._abort_requested)
        self.assertEqual(ready.task_state, 'ready')
        with self.assertRaises(rt.KarelAbort):
            scheduler.run()
        self.assertEqual((child.task_state, protected.task_state), ('aborted', 'paused'))
        scheduler.stop('PROTECTED')

    def test_batch_is_queued_before_self_pause(self):
        scheduler, ctx = scheduled()
        caller = worker(ctx, 'MAIN', "PAUSE_TASK('*ALL*',FALSE,FALSE,s) n=7")
        child = worker(ctx, 'CHILD')
        scheduler.start('MAIN')
        scheduler.start('CHILD')
        scheduler.run()
        self.assertEqual((caller.task_state, child.task_state), ('paused', 'paused'))
        self.assertEqual(caller.snapshot()['S'], 0)
        scheduler.stop('MAIN')
        scheduler.stop('CHILD')

    def test_foreign_scheduler_alias_is_outside_broadcast_scope(self):
        owner, ctx = scheduled()
        task = worker(ctx, 'WORKER')
        owner.start('WORKER')
        other, foreign = scheduled()
        other.bind('ALIAS', task)
        self.assertEqual(request(foreign, 'ABORT', '*ALL*').run()['S'], 0)
        self.assertFalse(task._state._abort_requested)
        owner.run()
        self.assertEqual(task.snapshot()['N'], 2)

    def test_standalone_registry_broadcast_uses_live_paused_targets(self):
        ctx = rt.ExecutionContext()
        child = worker(ctx, 'CHILD', 'n=3 PAUSE n=4')
        ready = worker(ctx, 'READY')
        with self.assertRaises(rt.KarelPause):
            child.run()
        self.assertEqual(request(ctx, 'ABORT', '*ALL*').run()['S'], 0)
        self.assertEqual(child.task_state, 'paused')
        self.assertTrue(child._state._abort_requested)
        self.assertEqual(ready.task_state, 'ready')
        with self.assertRaises(rt.KarelAbort):
            child.resume()

    def test_empty_broadcast_succeeds_and_unknown_name_remains_missing(self):
        ctx = rt.ExecutionContext()
        self.assertEqual(request(ctx, 'PAUSE', '*ALL*').run()['S'], 0)
        self.assertEqual(request(ctx, 'PAUSE', 'ABSENT').run()['S'], 1)


class SchedulerAliasTests(unittest.TestCase):
    def trace(self, aliases):
        scheduler, ctx = scheduled()
        task = worker(ctx, 'WORKER', 'n=1 DELAY 20 n=2 n=3')
        if aliases:
            scheduler.bind('ALIAS', task)
            scheduler.bind('ANOTHER', task)
        scheduler.start('ALIAS' if aliases else 'WORKER')
        trace = []
        for _ in range(25):
            scheduler.step()
            trace.append((scheduler.now_us, task.task_state, task._state.steps,
                          task.snapshot(), dict(scheduler.waiting)))
            if task.task_state == 'completed':
                return trace
        self.fail('Task did not complete')

    def test_aliases_leave_rounds_steps_and_deadlines_identical(self):
        self.assertEqual(self.trace(True), self.trace(False))

    def test_primary_rename_and_stop_through_alias_keep_one_wait_entry(self):
        scheduler, ctx = scheduled()
        task = worker(ctx, 'WORKER')
        scheduler.bind('ALIAS', task)
        scheduler.start('ALIAS')
        advance_until(scheduler, lambda: task.task_state == 'waiting')
        deadline = scheduler.waiting['WORKER']
        self.assertEqual(scheduler.rename('WORKER', 'NEW'), 0)
        self.assertEqual(scheduler.rename('ALIAS', 'SECOND'), 0)
        self.assertEqual(scheduler.waiting, {'NEW': deadline})
        scheduler.stop('SECOND')
        self.assertEqual(task.task_state, 'stopped')
        self.assertEqual(scheduler.waiting, {})

    def test_failure_is_recorded_on_primary_even_when_started_by_alias(self):
        scheduler, ctx = scheduled()
        task = worker(ctx, 'WORKER', 's=0 n=1 DIV s')
        scheduler.bind('ALIAS', task)
        scheduler.start('ALIAS')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'zero'):
            scheduler.run()
        self.assertEqual(task.task_state, 'failed')
        self.assertEqual(set(scheduler.errors), {'WORKER'})

    def test_foreign_scheduler_cannot_advance_or_stop_bound_task(self):
        owner, ctx = scheduled()
        task = worker(ctx, 'WORKER')
        owner.start('WORKER')
        advance_until(owner, lambda: task.task_state == 'waiting')
        execution = task._execution
        steps = task._state.steps
        deadline = owner.waiting['WORKER']
        foreign = rt.TaskScheduler()
        foreign.bind('ALIAS', task)
        self.assertEqual(foreign.run(max_cycles=1)['ALIAS']['state'], 'waiting')
        self.assertFalse(foreign.step())
        self.assertEqual((task._state.steps, owner.waiting['WORKER']), (steps, deadline))
        self.assertIs(task._execution, execution)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'owning TaskScheduler'):
            foreign.stop('ALIAS')
        self.assertEqual(owner.run()['WORKER']['values']['N'], 2)

    def test_previous_scheduler_drains_its_pulse_during_later_run(self):
        owner = rt.TaskScheduler()
        ports = rt.PortBank({'DOUT': 1})
        context = rt.ExecutionContext(tasks=owner, ports=ports)
        task = worker(context, 'WORKER', 'PULSE DOUT[1] FOR 100 NOWAIT')
        owner.start('WORKER')
        advance_until(owner, lambda: task.task_state == 'completed')
        self.assertEqual(ports.pending_pulses, 1)

        other = rt.TaskScheduler()
        other.bind('ALIAS', task)
        other.start('ALIAS')
        execution = task._execution
        owner.run()

        self.assertEqual(ports.pending_pulses, 0)
        self.assertFalse(ports.read('DOUT', 1))
        self.assertGreaterEqual(owner.now_us, 100000)
        self.assertEqual(other.now_us, 0)
        self.assertIs(task._execution, execution)
        self.assertEqual(task.task_state, 'running')
        other.stop('ALIAS')

    def test_live_slot_replacement_rejects_without_rekeying_wait(self):
        scheduler, ctx = scheduled()
        other = worker(ctx, 'EARLIER')
        task = worker(ctx, 'WORKER')
        scheduler.start('WORKER')
        advance_until(scheduler, lambda: task.task_state == 'waiting')
        deadline = scheduler.waiting['WORKER']
        for name, replacement in (('WORKER', other), ('EARLIER', task)):
            with self.assertRaisesRegex(rt.KarelRuntimeError, 'replace a scheduler binding'):
                scheduler.bind(name, replacement)
        self.assertIs(scheduler.tasks['WORKER'], task)
        self.assertIs(scheduler.tasks['EARLIER'], other)
        self.assertEqual(scheduler.waiting, {'WORKER': deadline})
        scheduler.stop('WORKER')

    def test_foreign_numeric_continue_cannot_adopt_paused_task(self):
        owner, ctx = scheduled()
        task = worker(ctx, 'WORKER', 'PAUSE n=8')
        owner.start('WORKER')
        owner.run()
        other, foreign = scheduled()
        other.bind('ALIAS', task)
        caller = program('CONTINUE PROGRAM[1]', context=foreign, name='CALLER')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'owning TaskScheduler'):
            caller.run()
        self.assertEqual(task.task_state, 'paused')
        owner.continue_task('WORKER')
        self.assertEqual(owner.run()['WORKER']['values']['N'], 8)


if __name__ == '__main__':
    unittest.main()
