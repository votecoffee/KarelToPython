"""Opt-in logical pendant launch, ownership transfer and admission checks."""
import unittest

from karel2py import runtime as rt, translate_project
from tests.test_directive_group_locks import program, source
from tests.test_task_lineage import value
from tests.test_task_run_continuation import command


class TaskGroupHandoffTests(unittest.TestCase):
    def request(self, parent, mask, *, pause=True):
        state = parent._state
        with rt._numeric_scope('pythonic'):
            state.extended_call('RUN_TASK', ['CHILD', 0, pause, True, mask, state.reference('S')], 17)

    def test_linked_handoff_combines_transferred_and_automatic_groups(self):
        bank = rt.GroupLocks([1, 2, 31], apply_directives=True, callee_scopes=True, pendant_enabled=True)
        context = rt.ExecutionContext(group_locks=bank)
        linked = translate_project({
            'main': source(body='launch() PAUSE', prefix='%LOCKGROUP=31', routines='ROUTINE launch FROM LIB'),
            'lib': source('LIB', '', prefix='%LOCKGROUP=1',
                          routines=f'ROUTINE launch BEGIN {command(pause=True, motion=True, mask=1)} END launch'),
            'child': source('CHILD', 'n=9 PAUSE', prefix='%LOCKGROUP=1,2'),
        }).instantiate(context=context)
        linked.run('MAIN')
        main, child = (linked.programs[name] for name in ('MAIN', 'CHILD'))
        self.assertEqual(bank.owners, {1: child._state, 2: child._state, 31: main._state})
        self.assertEqual(value(context, 'CHILD', 'TSK_TPMOTION', prefix='%NOLOCKGROUP'), 1)
        self.assertEqual(value(context, 'CHILD', 'TSK_LOCKGRP', prefix='%NOLOCKGROUP'), 3)
        self.assertEqual(value(context, 'MAIN', 'TSK_LOCKGRP', prefix='%NOLOCKGROUP'), 1 << 30)
        self.assertEqual(linked.scheduler.set_attribute('CHILD', 'TSK_TPMOTION', 0), 0)
        self.assertEqual(value(context, 'CHILD', 'TSK_TPMOTION', prefix='%NOLOCKGROUP'), 0)

        linked.scheduler.continue_task('MAIN')
        linked.scheduler.run()
        self.assertEqual(main.task_state, 'completed')
        self.assertEqual(child.snapshot()['N'], 9)
        self.assertEqual(bank.owners, {1: child._state, 2: child._state})
        linked.scheduler.stop('CHILD')
        self.assertEqual(bank.owners, {})
        self.assertTrue(context.to_config()['group_locks']['pendant_enabled'])

    def test_synchronous_handoff_changes_grant_and_continuation_does_not_reapply(self):
        bank = rt.GroupLocks([1, 31], pendant_enabled=True)
        context = rt.ExecutionContext(group_locks=bank)
        mask = 1 << 30
        child = program('n=7 PAUSE n=8', name='CHILD', context=context)
        parent = program(f'LOCK_GROUP({mask},s) PAUSE n=6', context=context)
        context.tasks.bind('CHILD', child, attributes={'TSK_TPMOTION': 0})
        with self.assertRaises(rt.KarelPause):
            parent.run()
        original = bank._ownership_tokens[31]
        self.request(parent, mask)
        current = bank._ownership_tokens[31]
        self.assertIsNot(current, original)
        self.assertIs(bank.owners[31], child._state)
        self.assertEqual(value(context, 'CHILD', 'TSK_TPMOTION'), 1)

        program(command(motion=True, mask=mask), name='CONTROLLER', context=context).run()
        self.assertEqual(child.snapshot()['N'], 7)
        self.assertIs(bank._ownership_tokens[31], current)
        self.assertEqual(value(context, 'CHILD', 'TSK_TPMOTION'), 1)
        parent.resume()
        self.assertEqual(child.snapshot()['N'], 8)
        self.assertEqual(bank.owners, {})
        self.assertEqual(value(context, 'CHILD', 'TSK_TPMOTION'), 0)

    def test_rejected_masks_and_nonidle_or_foreign_grants_leave_admission_untouched(self):
        for reason, pattern in (('foreign', 'parent grant'), ('unowned', 'parent grant'),
                                ('executing', 'busy group'), ('stopped', 'busy group'),
                                ('held', 'busy group'), ('mask', 'unconfigured groups'),
                                ('negative', 'unconfigured groups'), ('disabled', 'pendant_enabled')):
            with self.subTest(reason=reason):
                bank = rt.GroupLocks([1, 2], pendant_enabled=reason != 'disabled')
                context = rt.ExecutionContext(group_locks=bank)
                parent_mask = 1 if reason in ('foreign', 'unowned') else 3
                parent = program(f'LOCK_GROUP({parent_mask},s) s=77 PAUSE', context=context)
                child = program('n=7', name='CHILD', context=context)
                context.tasks.bind('CHILD', child)
                with self.assertRaises(rt.KarelPause):
                    parent.run()
                foreign = program(name='OTHER', context=context)
                if reason == 'foreign':
                    bank.update(foreign._state, 'LOCK_GROUP', 2)
                if reason in ('executing', 'stopped'):
                    bank.set_motion(2, reason)
                if reason == 'held':
                    bank.held.add(2)
                owners, tokens = bank.owners.copy(), bank._ownership_tokens.copy()
                mask = 5 if reason == 'mask' else -1 if reason == 'negative' else 3
                with self.assertRaisesRegex(rt.KarelRuntimeError, pattern) as raised:
                    self.request(parent, mask)
                self.assertEqual(raised.exception.line, 17)
                self.assertEqual((bank.owners, bank._ownership_tokens), (owners, tokens))
                self.assertEqual(parent.snapshot()['S'], 77)
                self.assertEqual(child.task_state, 'ready')
                self.assertIsNone(child._state._task_launch)
                self.assertFalse(child._state._pause_requested)
                self.assertEqual(value(context, 'CHILD', 'TSK_PROGTYPE'), rt.TASK_CONSTANTS['PG_NOT_EXEC'])
                parent.stop()
                foreign.stop()

    def test_unavailable_automatic_group_preserves_transfer_on_retry(self):
        bank = rt.GroupLocks([1, 2], apply_directives=True, pendant_enabled=True)
        context = rt.ExecutionContext(group_locks=bank)
        parent = program('s=77 PAUSE', prefix='%LOCKGROUP=1', context=context)
        child = program('n=7', prefix='%LOCKGROUP=1,2', name='CHILD', context=context)
        holder = program(prefix='%LOCKGROUP=2', name='HOLDER', context=context)
        context.tasks.bind('CHILD', child)
        for task in (parent, holder):
            with self.assertRaises(rt.KarelPause):
                task.run()
        owners, tokens = bank.owners.copy(), bank._ownership_tokens.copy()
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'another task'):
            self.request(parent, 1)
        self.assertEqual((bank.owners, bank._ownership_tokens), (owners, tokens))
        self.assertEqual(child.task_state, 'ready')
        self.assertEqual(parent.snapshot()['S'], 77)

        holder.stop()
        self.request(parent, 1, pause=False)
        self.assertEqual(child.snapshot()['N'], 7)
        self.assertEqual(parent.snapshot()['S'], 0)
        self.assertEqual(bank.owners, {})
        parent.stop()

    def test_pending_scripted_motion_blocks_even_after_host_clears_label(self):
        bank = rt.GroupLocks([1], pendant_enabled=True)
        motion = rt.MotionRequests({1: 2}, responses=[dict(operation='MOVE AWAY', completed=True, delay_ms=100)])
        context = rt.ExecutionContext(group_locks=bank, motion=motion)
        parent = program('ATTACH MOVE AWAY 1 NOWAIT PAUSE', context=context)
        child = program('n=7', name='CHILD', context=context)
        context.tasks.bind('CHILD', child)
        with self.assertRaises(rt.KarelPause):
            parent.run()
        self.assertTrue(motion.has_pending_group(1))
        bank.set_motion(1, 'idle')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'busy group'):
            self.request(parent, 1)
        self.assertIs(bank.owners[1], parent._state)
        self.assertTrue(motion.has_pending_group(1))
        parent.stop()

    def test_zero_mask_opt_in_and_context_validation(self):
        with self.assertRaisesRegex(ValueError, 'pendant_enabled requires'):
            rt.GroupLocks.from_config({'groups': [1], 'pendant_enabled': 1})
        config = {'group_locks': {'groups': [1], 'motion': {}, 'pendant_enabled': True}}
        context = rt.ExecutionContext.from_config(config)
        self.assertEqual(context.to_config()['group_locks'], config['group_locks'])
        parent = program(command(motion=True), context=context)
        foreign = program('n=7', name='CHILD')
        context.tasks.bind('CHILD', foreign)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'shared execution context'):
            parent.run()
        self.assertEqual(foreign.task_state, 'ready')

        child = program('PAUSE', name='CHILD', context=context)
        context.tasks.bind('CHILD', child)
        parent.run()
        self.assertEqual(value(context, 'CHILD', 'TSK_TPMOTION'), 1)
        self.assertEqual(context.group_locks.owners, {})
        child.stop()


if __name__ == '__main__':
    unittest.main()
