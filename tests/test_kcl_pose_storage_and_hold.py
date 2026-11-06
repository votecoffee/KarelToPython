"""Offline KCL pose edits, explicit storage listings and owned motion holds."""
import json
import unittest

from karel2py import runtime as rt
from tests.test_extended_services import pose
from tests.test_kcl_task_commands import issue
from tests.test_task_control_broadcasts import advance_until, worker
from tests.test_task_motion_controls import QUEUE, REPLIES, context as motion_context


class KclPoseStorageTests(unittest.TestCase):
    def setUp(self):
        robot = rt.RobotContext(groups={
            1: rt.RobotContext(current=rt.RobotState(position=pose(10), joints=[11.])),
            2: rt.RobotContext(current=rt.RobotState(position=pose(20), joints=[21., 22.])),
        })
        self.ctx = rt.ExecutionContext(robot=robot, kcl=rt.KclCommands(
            variable_commands=True, environment_commands=True, program_commands=True))

    def test_vector_and_pose_lists_validate_before_any_write(self):
        store = self.ctx.variables
        vector = store.define('CELL', 'SHIFT', ('VECTOR',))
        point = store.define('CELL', 'TARGET', ('XYZWPREXT',))
        self.assertEqual(issue(self.ctx, 'SET VAR [CELL]SHIFT=1,-2,3e1')['S'], 0)
        self.assertEqual(vector.raw().values, {'X': 1., 'Y': -2., 'Z': 30.})
        self.assertEqual(issue(self.ctx, 'SET VAR [CELL]TARGET=1,2,3,4,5,6,7,8,9,"N L U T,1,2,3"')['S'], 0)
        before = rt.snapshot_value(point.raw())
        self.assertEqual((before['EXT3'], before['CONFIG_DATA']['CFG_TURN_NO3']), (9., 3))
        for literal in ('1,2,3,4,5,6,7,8,1e999', '1,2,3,400,5,6,7,8,9',
                        '1,2,3,4,5,6,7,8,9,"N N"', '1,2,3,4,5,6,7,8'):
            with self.subTest(literal=literal):
                self.assertEqual(issue(self.ctx, f'SET VAR [CELL]TARGET={literal}')['S'], 205)
                self.assertEqual(rt.snapshot_value(point.raw()), before)
        matrix = store.define('CELL', 'MATRIX', ('POSITION',))
        self.assertEqual(issue(self.ctx, 'SET VAR [CELL]MATRIX=1,2,3,0,0,0')['S'], 0)
        self.assertEqual(matrix.raw().values['LOCATION'].values['Z'], 3.)

    def test_named_values_use_static_lookups_and_checked_private_copies(self):
        store = self.ctx.variables
        dest = store.define('CELL', 'DEST', ('XYZWPR',))
        source = store.define('INPUTS', 'SOURCE', ('XYZWPR',), pose(27))
        self.assertEqual(issue(self.ctx, 'SET VAR [CELL]DEST=[inputs]source')['S'], 0)
        source.raw().values['X'] = 30.
        self.assertEqual(dest.raw().values['X'], 27.)
        store.define('CELL', 'SMALL', ('STRING', 3), 'old')
        store.define('CELL', 'LARGE', ('STRING', 10), 'long')
        self.assertEqual(issue(self.ctx, 'SET VAR [CELL]SMALL=LARGE')['S'], 205)
        self.assertEqual(store.bindings['CELL', 'SMALL'].raw(), 'old')
        self.assertEqual(issue(self.ctx, 'SET VAR [CELL]DEST=absent')['S'], 205)
        self.assertEqual(dest.raw().values['X'], 27.)

    def test_record_uses_selected_group_and_rejects_lossy_joint_narrowing(self):
        store = self.ctx.variables
        pose_cell = store.define('CELL', 'TARGET', ('XYZWPR',))
        narrow = store.define('CELL', 'NARROW', ('JOINTPOS', 1))
        axes = store.define('CELL', 'AXES', ('JOINTPOS', 2))
        self.assertEqual(issue(self.ctx, 'RECORD [CELL]NARROW')['S'], 0)
        self.assertEqual(issue(self.ctx, 'SET GROUP 2')['S'], 0)
        self.assertEqual(issue(self.ctx, 'RECORD [CELL]TARGET', nowait=True), {'S': 0, 'N': 0})
        self.assertEqual(issue(self.ctx, 'RECORD [CELL]AXES')['S'], 0)
        self.assertEqual(issue(self.ctx, 'RECORD [CELL]NARROW')['S'], 205)
        self.assertEqual((pose_cell.raw().values['X'], axes.raw().values, narrow.raw().values), (20., [21., 22.], [11.]))
        self.ctx.robot.for_group(2).current.update(position=pose(45))
        self.assertEqual(pose_cell.raw().values['X'], 20.)
        store.bind('OTHER', 'ALIAS', pose_cell)
        self.assertEqual(issue(self.ctx, 'RECORD [CELL]TARGET')['S'], 204)

    def test_record_and_variable_copy_preserve_protected_or_missing_storage(self):
        store = self.ctx.variables
        target = store.define('CELL', 'TARGET', ('POSITION',))
        self.assertEqual(issue(self.ctx, 'SET VAR [CELL]TARGET.NORMAL=1,0,0')['S'], 204)
        self.ctx.robot = None
        self.assertEqual(issue(self.ctx, 'RECORD [CELL]TARGET')['S'], 4)
        self.assertFalse(rt.fully_initialized(target.raw()))
        store.define('CELL', 'SOURCE', ('POSITION',))
        self.assertEqual(issue(self.ctx, 'SET VAR [CELL]TARGET=SOURCE')['S'], 205)
        self.assertFalse(rt.fully_initialized(target.raw()))

    def test_system_listing_is_explicit_filtered_and_stably_ordered(self):
        store = self.ctx.variables
        store.define('SYSTEM', '$CTRL.$GAIN', ('REAL',), 2.5)
        store.define('*SYSTEM*', '$CTRL.$GAIN', ('REAL',), 9.)
        store.define('', '$ACTIVE', ('BOOLEAN',), True)
        store.define('OTHER', '$PRIVATE', ('REAL',), 0.)
        text = []
        self.assertEqual(issue(self.ctx, 'SHOW SYSTEM REAL VALUES', write=text.append)['S'], 0)
        self.assertEqual([json.loads(row) for row in text], [
            {'program': 'SYSTEM', 'name': '$CTRL.$GAIN', 'type': 'REAL', 'value': 2.5},
        ])
        text.clear()
        self.assertEqual(issue(self.ctx, 'SHOW SYSTEM', write=text.append)['S'], 0)
        self.assertEqual([json.loads(row)['name'] for row in text], ['$ACTIVE', '$CTRL.$GAIN'])
        self.assertTrue(all('value' not in json.loads(row) for row in text))

    def test_memory_and_builtin_rows_describe_offline_registries(self):
        self.assertEqual(issue(self.ctx, 'CREATE VAR [CELL]COUNTS:ARRAY[3] OF INTEGER')['S'], 0)
        self.ctx.variables.define('CELL', 'EXPLICIT', ('INTEGER',), 9)
        text = []
        self.assertEqual(issue(self.ctx, 'SHOW MEMORY', write=text.append)['S'], 0)
        self.assertEqual(json.loads(text.pop()), {
            'pool': 'CREATE_VAR', 'unit': 'reservation', 'total': 32767, 'used': 3, 'available': 32764,
        })
        self.assertEqual(issue(self.ctx, 'SHOW BUILTINS', write=text.append)['S'], 0)
        rows = [json.loads(row) for row in text]
        names = [row['name'] for row in rows]
        self.assertEqual(names, sorted(set(names)))
        self.assertIn({'name': 'CURPOS', 'kind': 'FUNCTION'}, rows)
        self.assertIn({'name': 'SET_VAR', 'kind': 'PROCEDURE'}, rows)


class KclOwnedHoldTests(unittest.TestCase):
    def test_hold_freezes_queued_progress_and_unhold_leaves_task_paused(self):
        ctx = motion_context(responses=REPLIES)
        ctx.kcl = rt.KclCommands(task_commands=True)
        task = worker(ctx, 'WORKER', QUEUE + ' RELEASE n=7')
        ctx.tasks.start('WORKER')
        advance_until(ctx.tasks, lambda: task.task_state == 'waiting' and ctx.motion._queued)
        head = ctx.motion._active[1]['request']
        self.assertEqual(issue(ctx, 'HO WORKER', nowait=True), {'S': 0, 'N': 0})
        elapsed = head['data']['execution']['elapsed_ms']
        ctx.tasks.run()
        self.assertEqual((task.task_state, ctx.group_locks.held), ('paused', {1}))
        self.assertEqual(head['data']['execution']['elapsed_ms'], elapsed)
        self.assertEqual(issue(ctx, 'UNHOLD WORKER')['S'], 0)
        self.assertEqual((task.task_state, ctx.group_locks.held), ('paused', set()))
        self.assertEqual(issue(ctx, 'CONTINUE WORKER')['S'], 0)
        ctx.tasks.run()
        self.assertEqual((task.snapshot()['N'], head['outcome']), (7, 'completed'))

    def test_hold_broadcast_preflight_is_atomic_and_masks_are_honored(self):
        ctx = motion_context((1, 2), sequence=2147483645)
        ctx.kcl = rt.KclCommands(task_commands=True)
        first = worker(ctx, 'FIRST', 'LOCK_GROUP(1,s) DELAY 100')
        second = worker(ctx, 'SECOND', 'LOCK_GROUP(2,s) DELAY 100')
        ctx.tasks.start('FIRST')
        ctx.tasks.start('SECOND')
        advance_until(ctx.tasks, lambda: len(ctx.tasks.waiting) == 2)
        self.assertEqual(issue(ctx, 'HOLD ALL')['S'], 4)
        self.assertEqual((ctx.group_locks.held, ctx.motion.history), (set(), []))
        self.assertFalse(first._state._pause_requested or second._state._pause_requested)
        ctx.tasks.run()

        masked = worker(ctx, 'MASKED', 'LOCK_GROUP(1,s) DELAY 100', prefix='%NOPAUSE=COMMAND')
        ctx.tasks.start('MASKED')
        advance_until(ctx.tasks, lambda: masked.task_state == 'waiting')
        self.assertEqual(issue(ctx, 'HOLD MASKED')['S'], 0)
        self.assertEqual((ctx.group_locks.held, ctx.motion.history), (set(), []))
        self.assertFalse(masked._state._pause_requested)
        ctx.tasks.run()


if __name__ == '__main__':
    unittest.main()
