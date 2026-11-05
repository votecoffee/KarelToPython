"""Named and broadcast task flags over explicit logical motion ownership."""
import json
import unittest

from karel2py import runtime as rt
from tests.test_task_control_broadcasts import advance_until, request, worker


def context(groups=(1,), *, motion=None, held=(), responses=(), sequence=0, scheduled=True):
    bank = rt.MotionRequests({group: 2 for group in groups},
                             capture_only=not responses, responses=list(responses),
                             queue_limit=2 if responses else 0, sequence=sequence)
    locks = rt.GroupLocks(list(groups), motion=motion, held=list(held))
    tasks = rt.TaskScheduler() if scheduled else rt.TaskRegistry()
    return rt.ExecutionContext(tasks=tasks, motion=bank, group_locks=locks)


REPLIES = (
    dict(operation='MOVE AWAY', completed=True, delay_ms=40),
    dict(operation='MOVE AXIS', completed=True, delay_ms=50),
)
QUEUE = 'ATTACH MOVE AWAY 1 NOWAIT MOVE AXIS 2 BY 20 NOWAIT DELAY 200'


class TaskMotionControlTests(unittest.TestCase):
    def test_pause_holds_active_queue_and_continue_keeps_hold_until_unhold(self):
        ctx = context(responses=REPLIES)
        task = worker(ctx, 'WORKER', QUEUE + ' UNHOLD DELAY 120 RELEASE n=7')
        ctx.tasks.start('WORKER')
        advance_until(ctx.tasks, lambda: task.task_state == 'waiting' and ctx.motion._queued)
        head = ctx.motion._active[1]
        tail = ctx.motion._queued[1][0]
        self.assertEqual(request(ctx, 'PAUSE', 'worker', motion=True).run()['S'], 0)
        self.assertEqual(ctx.group_locks.held, {1})
        self.assertIs(ctx.motion._active[1], head)
        self.assertIs(ctx.motion._queued[1][0], tail)
        elapsed = head['request']['data']['execution']['elapsed_ms']
        ctx.tasks.run()
        self.assertEqual(task.task_state, 'paused')
        self.assertEqual(head['request']['data']['execution']['elapsed_ms'], elapsed)
        ctx.tasks.continue_task('WORKER')
        ctx.tasks.step()
        self.assertEqual(ctx.group_locks.held, {1})
        ctx.tasks.run()
        self.assertEqual(task.snapshot()['N'], 7)
        self.assertEqual(ctx.group_locks.held, set())
        self.assertEqual((head['request']['outcome'], tail['request']['outcome']), ('completed', 'completed'))
        hold = next(row for row in ctx.motion.history if row['operation'] == 'HOLD')
        self.assertEqual((hold['program'], hold['source_program'], hold['data']['groups']),
                         ('WORKER', 'CALLER', [1]))

    def test_abort_cancels_head_and_waiter_before_task_unwinds(self):
        ctx = context((1, 2), motion={1: 'executing'}, responses=REPLIES)
        task = worker(ctx, 'WORKER', QUEUE, prefix='%DEFGROUP=2\n%LOCKGROUP=2')
        ctx.tasks.start('WORKER')
        advance_until(ctx.tasks, lambda: task.task_state == 'waiting' and ctx.motion._queued)
        head = ctx.motion._active[2]['request']
        tail = ctx.motion._queued[2][0]['request']
        caller = request(ctx, 'ABORT', 'WORKER', motion=True)
        ctx.group_locks.update(caller._state, 'LOCK_GROUP', 1)
        self.assertEqual(caller.run()['S'], 0)
        self.assertEqual((head['outcome'], tail['outcome']), ('cancelled', 'cancelled'))
        self.assertEqual(tail['data']['execution']['elapsed_ms'], 0)
        self.assertEqual(ctx.group_locks.motion, {1: 'executing'})
        self.assertEqual(ctx.motion._active, {})
        self.assertEqual(ctx.motion._queued, {})
        self.assertIs(ctx.group_locks.owners[2], task._state)
        with self.assertRaises(rt.KarelAbort):
            ctx.tasks.run()
        self.assertEqual(ctx.group_locks.owners, {})
        self.assertEqual(ctx.motion.history[-1]['data']['groups'], [2])
        config = json.loads(json.dumps(ctx.to_config()))
        self.assertEqual(rt.ExecutionContext.from_config(config).to_config(), config)

    def test_cancel_preserves_stopped_labels_and_hold_flags(self):
        ctx = context((1, 2), motion={1: 'stopped', 2: 'executing'}, held=(1, 2))
        task = worker(ctx, 'WORKER', 'LOCK_GROUP(3,s) DELAY 100')
        ctx.tasks.start('WORKER')
        advance_until(ctx.tasks, lambda: task.task_state == 'waiting')
        self.assertEqual(request(ctx, 'ABORT', 'WORKER', motion=True).run()['S'], 0)
        self.assertEqual(ctx.group_locks.motion, {1: 'stopped'})
        self.assertEqual(ctx.group_locks.held, {1, 2})
        self.assertEqual(ctx.motion.history[-1]['data']['groups'], [1, 2])
        with self.assertRaises(rt.KarelAbort):
            ctx.tasks.run()

    def test_handler_can_clear_task_request_after_motion_commit(self):
        ctx = context(motion={1: 'executing'}, scheduled=False)
        task = worker(ctx, 'WORKER', (
            'LOCK_GROUP(1,s) n=0 CONDITION[1]: WHEN ABORT DO NOABORT,n=s+7 ENDCONDITION '
            "ENABLE CONDITION[1] ABORT_TASK('WORKER',TRUE,TRUE,s)"
        ))
        self.assertEqual(task.run(), {'N': 7, 'S': 0})
        self.assertEqual(task.task_state, 'completed')
        self.assertEqual(ctx.group_locks.motion, {})
        self.assertEqual(ctx.motion.history[-1]['operation'], 'CANCEL')

    def test_masked_named_request_leaves_motion_untouched_until_forced(self):
        ctx = context()
        task = worker(ctx, 'WORKER', 'LOCK_GROUP(1,s) DELAY 100', prefix='%NOPAUSE=COMMAND')
        ctx.tasks.start('WORKER')
        advance_until(ctx.tasks, lambda: task.task_state == 'waiting')
        self.assertEqual(request(ctx, 'PAUSE', 'WORKER', force=False, motion=True).run()['S'], 0)
        self.assertFalse(task._state._pause_requested)
        self.assertEqual(ctx.motion.history, [])
        self.assertEqual(ctx.group_locks.held, set())
        self.assertEqual(request(ctx, 'PAUSE', 'WORKER', motion=True).run()['S'], 0)
        self.assertEqual(ctx.group_locks.held, {1})
        ctx.tasks.run()
        self.assertEqual(task.task_state, 'paused')
        ctx.tasks.stop('WORKER')

    def test_broadcast_ignores_force_and_skips_masked_motion(self):
        ctx = context((1, 2))
        first = worker(ctx, 'FIRST', 'LOCK_GROUP(1,s) DELAY 100')
        second = worker(ctx, 'SECOND', 'LOCK_GROUP(2,s) DELAY 100', prefix='%NOPAUSE=COMMAND')
        ctx.tasks.bind('ALIAS', first)
        ctx.tasks.start('FIRST')
        ctx.tasks.start('SECOND')
        advance_until(ctx.tasks, lambda: len(ctx.tasks.waiting) == 2)
        self.assertEqual(request(ctx, 'PAUSE', '*ALL*', motion=True).run()['S'], 0)
        self.assertEqual(ctx.group_locks.held, {1})
        self.assertEqual([(row['program'], row['data']['groups']) for row in ctx.motion.history],
                         [('FIRST', [1])])
        self.assertFalse(second._state._pause_requested)
        ctx.tasks.run()
        self.assertEqual((first.task_state, second.task_state), ('paused', 'completed'))
        ctx.tasks.stop('ALIAS')

    def test_broadcast_preflights_total_history_capacity(self):
        ctx = context((1, 2), sequence=2147483645)
        first = worker(ctx, 'FIRST', 'LOCK_GROUP(1,s) DELAY 100')
        second = worker(ctx, 'SECOND', 'LOCK_GROUP(2,s) DELAY 100')
        ctx.tasks.start('FIRST')
        ctx.tasks.start('SECOND')
        advance_until(ctx.tasks, lambda: len(ctx.tasks.waiting) == 2)
        caller = request(ctx, 'PAUSE', '*ALL*', motion=True)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'sequence exhausted'):
            caller.run()
        self.assertEqual(caller.snapshot()['S'], 77)
        self.assertEqual(ctx.group_locks.held, set())
        self.assertEqual(ctx.motion.history, [])
        self.assertEqual(ctx.motion.sequence, 2147483645)
        self.assertFalse(first._state._pause_requested)
        self.assertFalse(second._state._pause_requested)
        ctx.tasks.run()

    def test_broadcast_rejects_later_unconfigured_group_before_any_change(self):
        ctx = context()
        # GroupLocks may be wider than the motion bank.
        ctx.group_locks = rt.GroupLocks([1, 2])
        first = worker(ctx, 'FIRST', 'LOCK_GROUP(1,s) DELAY 100')
        second = worker(ctx, 'SECOND', 'LOCK_GROUP(2,s) DELAY 100')
        ctx.tasks.start('FIRST')
        ctx.tasks.start('SECOND')
        advance_until(ctx.tasks, lambda: len(ctx.tasks.waiting) == 2)
        caller = request(ctx, 'ABORT', '*ALL*', motion=True)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'configured group'):
            caller.run()
        self.assertEqual(caller.snapshot()['S'], 77)
        self.assertEqual(ctx.motion.history, [])
        self.assertEqual(ctx.group_locks.owners, {1: first._state, 2: second._state})
        self.assertFalse(first._state._abort_requested)
        self.assertFalse(second._state._abort_requested)
        ctx.tasks.run()

    def test_named_motion_cannot_cross_banks_or_scheduler_ownership(self):
        owner = context()
        task = worker(owner, 'WORKER', 'LOCK_GROUP(1,s) PAUSE')
        owner.tasks.start('WORKER')
        owner.tasks.run()
        foreign = context()
        foreign.tasks.bind('ALIAS', task)
        caller = request(foreign, 'ABORT', 'ALIAS', motion=True)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'owning task driver'):
            caller.run()
        self.assertEqual(caller.snapshot()['S'], 77)
        self.assertEqual(task.task_state, 'paused')
        self.assertFalse(task._state._abort_requested)
        owner.tasks.stop('WORKER')

        first = context(scheduled=False)
        second = context(scheduled=False)
        task = worker(second, 'WORKER', 'LOCK_GROUP(1,s) PAUSE')
        first.tasks.bind('ALIAS', task)
        with self.assertRaises(rt.KarelPause):
            task.run()
        caller = request(first, 'PAUSE', 'ALIAS', motion=True)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'shared MotionRequests and GroupLocks'):
            caller.run()
        self.assertEqual(caller.snapshot()['S'], 77)
        self.assertEqual(first.group_locks.held, set())
        self.assertEqual(second.group_locks.held, set())
        task.stop()

    def test_lost_active_grant_is_rejected_before_control_record(self):
        ctx = context(responses=REPLIES)
        task = worker(ctx, 'WORKER', QUEUE)
        ctx.tasks.start('WORKER')
        advance_until(ctx.tasks, lambda: task.task_state == 'waiting' and ctx.motion._queued)
        scope = ctx.motion._active[1]
        ctx.group_locks._ownership_tokens[1] = object()
        count = len(ctx.motion.history)
        caller = request(ctx, 'PAUSE', 'WORKER', motion=True)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'ownership grant'):
            caller.run()
        self.assertEqual(caller.snapshot()['S'], 77)
        self.assertEqual(len(ctx.motion.history), count)
        self.assertIs(ctx.motion._active[1], scope)
        self.assertFalse(task._state._pause_requested)
        self.assertEqual(ctx.group_locks.held, set())
        ctx.tasks.stop('WORKER')

    def test_live_unowned_target_has_no_motion_history_row(self):
        ctx = context()
        task = worker(ctx, 'WORKER', 'DELAY 100')
        ctx.tasks.start('WORKER')
        advance_until(ctx.tasks, lambda: task.task_state == 'waiting')
        self.assertEqual(request(ctx, 'PAUSE', 'WORKER', motion=True).run()['S'], 0)
        self.assertEqual(ctx.motion.history, [])
        ctx.tasks.run()
        self.assertEqual(task.task_state, 'paused')
        ctx.tasks.stop('WORKER')


if __name__ == '__main__':
    unittest.main()
