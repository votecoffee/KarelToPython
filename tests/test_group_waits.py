"""Bounded logical group waits with atomic mask publication."""
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt, translate_project
from tests.test_directive_group_locks import program, source


class GroupLockWaitTests(unittest.TestCase):
    def test_waits_for_foreign_owner_without_partial_acquisition(self):
        bank = rt.GroupLocks([1, 2], lock_wait_ms=40)
        other = program(name='OTHER', bank=bank)
        bank.update(other._state, 'LOCK_GROUP', 2)
        delays = []

        def sleeper(seconds):
            delays.append(seconds)
            self.assertEqual(bank.owners, {2: other._state})
            self.assertEqual(task.snapshot()['S'], 77)
            bank.update(other._state, 'UNLOCK_GROUP', 2)

        task = program('s=77 LOCK_GROUP(3,s) PAUSE', bank=bank, cooperative=False, sleep=sleeper)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(delays, [.01])
        self.assertEqual(bank.owners, {1: task._state, 2: task._state})
        self.assertEqual(task.snapshot()['S'], 0)
        self.assertFalse(bank._pending)
        task.stop()

    def test_timeout_preserves_preexisting_ownership_and_reports_foreign_group(self):
        bank = rt.GroupLocks([1, 2, 3], lock_wait_ms=23)
        other = program(name='OTHER', bank=bank)
        bank.update(other._state, 'LOCK_GROUP', 2)
        delays = []
        task = program('LOCK_GROUP(7,s) PAUSE', bank=bank, sleep=delays.append)
        bank.update(task._state, 'LOCK_GROUP', 4)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(task.snapshot()['S'], 2)
        self.assertEqual(delays, [.01, .01, .003])
        self.assertEqual(bank.owners, {2: other._state, 3: task._state})
        task.stop()
        self.assertEqual(bank.owners, {2: other._state})

    def test_grant_ready_on_last_retry_succeeds(self):
        bank = rt.GroupLocks([1], lock_wait_ms=3)
        other = program(name='OTHER', bank=bank)
        bank.update(other._state, 'LOCK_GROUP', 1)

        def sleeper(seconds):
            self.assertEqual(seconds, .003)
            bank.update(other._state, 'UNLOCK_GROUP', 1)

        task = program('LOCK_GROUP(1,s) PAUSE', bank=bank, sleep=sleeper)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(task.snapshot()['S'], 0)
        self.assertIs(bank.owners[1], task._state)
        task.stop()

    def test_captures_mask_and_status_selector_once(self):
        bank = rt.GroupLocks([1, 2], lock_wait_ms=30)
        other = program(name='OTHER', bank=bank)
        bank.update(other._state, 'LOCK_GROUP', 2)
        calls = []

        def sleeper(_):
            calls.append(task.snapshot()['N'])
            task._state.set('MASK', 0)
            bank.update(other._state, 'UNLOCK_GROUP', 2)

        routines = 'ROUTINE pick:INTEGER BEGIN n=n+1 RETURN n END pick'
        linked = translate_project({'main': source(
            body='n=0 mask=3 a[1]=77 a[2]=88 LOCK_GROUP(mask,a[pick()]) PAUSE',
            decl='n,mask:INTEGER a:ARRAY[2] OF INTEGER', routines=routines,
        )}).instantiate(context=rt.ExecutionContext(group_locks=bank), options={'sleep': sleeper})
        task = linked.programs['MAIN']
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(calls, [1])
        self.assertEqual(task.snapshot()['A'], [0, 88])
        self.assertEqual(set(bank.owners), {1, 2})
        task.stop()

    def test_blocked_standalone_needs_injected_sleeper(self):
        bank = rt.GroupLocks([1, 2], lock_wait_ms=10)
        other = program(name='OTHER', bank=bank)
        bank.update(other._state, 'LOCK_GROUP', 2)
        task = program('s=77 LOCK_GROUP(3,s)', bank=bank)
        with patch('karel2py.runtime.time.sleep') as sleeper:
            with self.assertRaisesRegex(rt.KarelRuntimeError, 'explicit sleeper'):
                task.run()
            sleeper.assert_not_called()
        self.assertEqual(task.snapshot()['S'], 77)
        self.assertEqual(bank.owners, {2: other._state})

    def test_invalid_masks_and_empty_mask_do_not_wait(self):
        bank = rt.GroupLocks([1], lock_wait_ms=50, unlock_wait_ms=50)
        delays = []
        task = program('LOCK_GROUP(2,n) UNLOCK_GROUP(-1,s) LOCK_GROUP(0,n) UNLOCK_GROUP(0,s)',
                       bank=bank, sleep=delays.append)
        self.assertEqual((task.run()['N'], task.snapshot()['S']), (0, 0))
        task = program('LOCK_GROUP(2,n) UNLOCK_GROUP(-1,s)', bank=bank, sleep=delays.append)
        self.assertEqual((task.run()['N'], task.snapshot()['S']), (1, 1))
        self.assertEqual(delays, [])
        self.assertEqual(bank.owners, {})

    def test_direct_calls_keep_immediate_partial_behavior(self):
        bank = rt.GroupLocks([1, 2], lock_wait_ms=50, unlock_wait_ms=50)
        other = program(name='OTHER', bank=bank)
        bank.update(other._state, 'LOCK_GROUP', 2)
        task = program('n=1', bank=bank, cooperative=False)
        status = task._state.reference('S')
        with rt._numeric_scope('pythonic'):
            task._state.extended_call('LOCK_GROUP', [3, status])
        self.assertEqual(status.raw(), 2)
        self.assertEqual(bank.owners, {1: task._state, 2: other._state})
        bank.release_owner(task._state)


class GroupUnlockWaitTests(unittest.TestCase):
    def test_waits_for_all_owned_labels_and_holds_to_clear(self):
        bank = rt.GroupLocks([1, 2, 3], motion={2: 'executing', 3: 'stopped'}, held=[3],
                             unlock_wait_ms=40)
        delays = []

        def sleeper(seconds):
            delays.append(seconds)
            self.assertEqual(set(bank.owners), {1, 2, 3})
            self.assertEqual(task.snapshot()['S'], 77)
            if len(delays) == 1:
                bank.set_motion(2, 'idle')
                bank.set_motion(3, 'idle')
            else:
                bank.held.remove(3)

        task = program('LOCK_GROUP(7,s) s=77 UNLOCK_GROUP(7,s) PAUSE', bank=bank, sleep=sleeper)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(delays, [.01, .01])
        self.assertEqual(task.snapshot()['S'], 0)
        self.assertEqual(bank.owners, {})
        task.stop()

    def test_timeout_uses_current_first_blocker_and_releases_nothing(self):
        bank = rt.GroupLocks([1, 2, 3], motion={2: 'executing', 3: 'stopped'}, unlock_wait_ms=7)

        def sleeper(seconds):
            self.assertEqual(seconds, .007)
            bank.set_motion(2, 'idle')

        task = program('LOCK_GROUP(7,s) UNLOCK_GROUP(7,s) PAUSE', bank=bank, sleep=sleeper)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(task.snapshot()['S'], 17040)
        self.assertEqual(set(bank.owners), {1, 2, 3})
        task.stop()

    def test_foreign_unlock_returns_immediately_without_releasing_owned_groups(self):
        bank = rt.GroupLocks([1, 2], unlock_wait_ms=50)
        other = program(name='OTHER', bank=bank)
        bank.update(other._state, 'LOCK_GROUP', 2)
        delays = []
        task = program('LOCK_GROUP(1,s) UNLOCK_GROUP(3,s) PAUSE', bank=bank, sleep=delays.append)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(delays, [])
        self.assertEqual(task.snapshot()['S'], 2)
        self.assertEqual(bank.owners, {1: task._state, 2: other._state})
        task.stop()

    def test_unlock_rejects_a_replaced_same_owner_grant(self):
        bank = rt.GroupLocks([1, 2], motion={2: 'stopped'}, unlock_wait_ms=30)

        def sleeper(_):
            state = task._state
            bank.set_motion(2, 'idle')
            bank.update(state, 'UNLOCK_GROUP', 2)
            bank.update(state, 'LOCK_GROUP', 2)

        task = program('LOCK_GROUP(3,n) s=77 UNLOCK_GROUP(3,s)', bank=bank, sleep=sleeper)
        with patch.object(bank, '_apply', wraps=bank._apply) as apply:
            with self.assertRaisesRegex(rt.KarelRuntimeError, 'grant changed'):
                task.run()
        self.assertEqual([call.args[1:] for call in apply.call_args_list],
                         [(1, True), (2, True), (2, False), (2, True)])
        self.assertEqual(task.snapshot()['S'], 77)
        self.assertEqual(bank.owners, {})
        self.assertFalse(bank._pending)

    def test_zero_unlock_policy_still_uses_partial_release(self):
        bank = rt.GroupLocks([1, 2], motion={2: 'stopped'}, lock_wait_ms=20)
        task = program('LOCK_GROUP(3,s) UNLOCK_GROUP(3,s) PAUSE', bank=bank)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(task.snapshot()['S'], 17040)
        self.assertEqual(bank.owners, {2: task._state})
        task.stop()


class GroupWaitLifetimeTests(unittest.TestCase):
    def test_pause_retains_pending_wait_even_after_owner_releases(self):
        bank = rt.GroupLocks([1], lock_wait_ms=30)
        other = program(name='OTHER', bank=bank)
        bank.update(other._state, 'LOCK_GROUP', 1)
        body = ('n=0 CONDITION[1]: WHEN n=1 DO PAUSE ENDCONDITION ENABLE CONDITION[1] '
                's=77 LOCK_GROUP(1,s)')
        task = program(body, bank=bank, sleep=lambda _: task._state.set('N', 1))
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(task.snapshot()['S'], 77)
        bank.release_owner(other._state)
        with self.assertRaisesRegex(ValueError, 'pending group operation'):
            bank.to_config()
        self.assertEqual(task.resume()['S'], 0)
        self.assertFalse(bank._pending)
        self.assertEqual(bank.owners, {})

    def test_blocked_handler_returns_status_without_yielding(self):
        bank = rt.GroupLocks([1, 2], lock_wait_ms=50)
        other = program(name='OTHER', bank=bank)
        bank.update(other._state, 'LOCK_GROUP', 2)
        body = ('CONDITION[1]: WHEN TRUE DO LOCK_GROUP(3,s) ENDCONDITION '
                'ENABLE CONDITION[1] n=7 PAUSE')
        task = program(body, bank=bank)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(task.snapshot()['S'], 2)
        self.assertEqual(bank.owners, {2: other._state})
        self.assertFalse(bank._pending)
        task.stop()

    def test_stop_removes_pending_registration_and_preserves_foreign_grant(self):
        bank = rt.GroupLocks([1, 2], lock_wait_ms=50)
        context = rt.ExecutionContext(group_locks=bank)
        linked = translate_project({'main': source(body='s=77 LOCK_GROUP(3,s)')}).instantiate(context=context)
        foreign = program(name='FOREIGN', context=context)
        bank.update(foreign._state, 'LOCK_GROUP', 2)
        linked.scheduler.start('MAIN')
        for _ in range(20):
            linked.scheduler.step()
            if bank._pending:
                break
        self.assertTrue(bank._pending)
        linked.scheduler.stop('MAIN')
        self.assertEqual(linked.programs['MAIN'].snapshot()['S'], 77)
        self.assertEqual(bank.owners, {2: foreign._state})
        self.assertFalse(bank._pending)

    def test_replaced_bank_fails_before_grant_publication(self):
        bank = rt.GroupLocks([1], lock_wait_ms=50)
        foreign = program(name='OTHER', bank=bank)
        bank.update(foreign._state, 'LOCK_GROUP', 1)
        context = rt.ExecutionContext(group_locks=bank)
        replacement = rt.GroupLocks([1], lock_wait_ms=50)

        def sleeper(_):
            context.group_locks = replacement
            bank.release_owner(foreign._state)

        task = program('s=77 LOCK_GROUP(1,s)', context=context, sleep=sleeper)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'ownership or configuration changed'):
            task.run()
        self.assertEqual(task.snapshot()['S'], 77)
        self.assertEqual(bank.owners, {})
        self.assertEqual(replacement.owners, {})
        self.assertFalse(bank._pending)

    def test_configuration_roundtrips_enabled_limits_and_rejects_coercion(self):
        bank = rt.GroupLocks([1], lock_wait_ms=10, unlock_wait_ms=86400000)
        config = rt.ExecutionContext(group_locks=bank).to_config()
        restored = rt.ExecutionContext.from_config(json.loads(json.dumps(config)))
        self.assertEqual(restored.to_config(), config)
        self.assertEqual(restored.group_locks.snapshot()['unlock_wait_ms'], 86400000)
        self.assertNotIn('lock_wait_ms', rt.GroupLocks([1], lock_wait_ms=0).to_config())
        for name in ('lock_wait_ms', 'unlock_wait_ms'):
            for value in (True, None, -1, 86400001, '10'):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    rt.GroupLocks.from_config({'groups': [1], name: value})


if __name__ == '__main__':
    unittest.main()
