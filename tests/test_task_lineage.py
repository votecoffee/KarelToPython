"""Live RUN_TASK lineage and logical ownership through GET_TSK_INFO."""
import unittest

from karel2py import runtime as rt, translate_project
from tests.test_directive_group_locks import program, source
from tests.test_extended_services import compile_program
from tests.test_task_inspection import query


def run_child(name='WORKER'):
    return f"RUN_TASK('{name}',0,FALSE,FALSE,0,s)"


def inspect(context, name, attribute, **options):
    return query(context, attribute, setup=f"name='{name}' number=0", **options)


def value(context, name, attribute, **options):
    result = inspect(context, name, attribute, **options)
    if result['STATUS'] != 0:
        raise AssertionError(result)
    return result['VALUE']


def project(main, worker='n=1 PAUSE n=2', *, context=None, **modules):
    sources = {'main': source(body=main), 'worker': source('WORKER', worker), **modules}
    return translate_project(sources).instantiate(context=context)


class TaskLineageTests(unittest.TestCase):
    def test_live_parent_number_and_child_count_survive_aliases_and_rename(self):
        linked = project(run_child() + ' PAUSE')
        scheduler, context = linked.scheduler, linked.context
        scheduler.bind('PARENT_ALIAS', linked.programs['MAIN'])
        scheduler.bind('WORKER_ALIAS', linked.programs['WORKER'])
        scheduler.start('PARENT_ALIAS')
        scheduler.run()

        self.assertEqual(value(context, 'WORKER_ALIAS', 'TSK_PARENT'), 1)
        self.assertEqual(value(context, 'PARENT_ALIAS', 'TSK_NUMCLDS'), 1)
        self.assertEqual(value(context, 'WORKER', 'TSK_NUMCLDS'), 0)
        self.assertEqual(scheduler.rename('MAIN', 'RENAMED'), 0)
        self.assertEqual(value(context, 'WORKER', 'TSK_PARENT'), 1)
        self.assertEqual(value(context, 'RENAMED', 'TSK_NUMCLDS'), 1)
        scheduler.stop('WORKER_ALIAS')
        self.assertEqual(value(context, 'RENAMED', 'TSK_NUMCLDS'), 0)
        self.assertEqual(value(context, 'WORKER', 'TSK_PARENT'), 0)
        scheduler.stop('PARENT_ALIAS')

    def test_continuation_by_another_task_keeps_original_parent(self):
        linked = project(run_child() + ' PAUSE', 'n=1 PAUSE n=2 PAUSE n=3')
        linked.run('MAIN')
        worker = linked.programs['WORKER']
        execution = worker._execution
        other = program(run_child() + ' PAUSE', context=linked.context, name='OTHER')
        linked.scheduler.bind('OTHER', other)
        linked.scheduler.start('OTHER')
        linked.scheduler.run()
        self.assertIs(worker._execution, execution)
        self.assertEqual(worker.snapshot()['N'], 2)
        self.assertEqual(value(linked.context, 'WORKER', 'TSK_PARENT'), 1)
        self.assertEqual(value(linked.context, 'MAIN', 'TSK_NUMCLDS'), 1)
        self.assertEqual(value(linked.context, 'OTHER', 'TSK_NUMCLDS'), 0)
        for name in ('WORKER', 'MAIN', 'OTHER'):
            linked.scheduler.stop(name)

    def test_completed_parent_does_not_adopt_old_child_on_next_run(self):
        main = "IF UNINIT(n) THEN n=1 " + run_child() + " ELSE n=2 PAUSE ENDIF"
        linked = project(main)
        linked.run('MAIN')
        self.assertEqual(linked.programs['MAIN'].task_state, 'completed')
        self.assertEqual(linked.programs['WORKER'].task_state, 'paused')
        self.assertEqual(value(linked.context, 'WORKER', 'TSK_PARENT'), 0)
        linked.run('MAIN')
        self.assertEqual(linked.programs['MAIN'].task_state, 'paused')
        self.assertEqual(value(linked.context, 'MAIN', 'TSK_NUMCLDS'), 0)
        self.assertEqual(value(linked.context, 'WORKER', 'TSK_PARENT'), 0)
        linked.scheduler.continue_task('MAIN')
        linked.scheduler.run()
        self.assertEqual(linked.programs['WORKER'].task_state, 'paused')
        linked.scheduler.stop('WORKER')

    def test_synchronous_child_can_query_parent_during_run_task(self):
        context = rt.ExecutionContext()
        main = program(run_child(), context=context, name='MAIN')
        worker, _ = compile_program(
            "name='WORKER' number=0 GET_TSK_INFO(name,number,TSK_PARENT,p,text,status) "
            "name='MAIN' number=0 GET_TSK_INFO(name,number,TSK_NUMCLDS,c,text,status)",
            decl='name,text:STRING[24] number,p,c,status:INTEGER',
            context=context, cooperative=True,
        )
        context.tasks.bind('MAIN', main)
        context.tasks.bind('WORKER', worker)
        main.run()
        self.assertEqual((worker.snapshot()['P'], worker.snapshot()['C']), (1, 1))
        self.assertEqual(value(context, 'WORKER', 'TSK_PARENT'), 0)
        self.assertEqual(value(context, 'MAIN', 'TSK_NUMCLDS'), 0)

    def test_linked_launch_uses_calling_root_and_counts_direct_children(self):
        sources = {
            'main': source(body='launch() PAUSE', routines='ROUTINE launch FROM LIB'),
            'lib': source('LIB', '', routines=f'ROUTINE launch BEGIN {run_child()} END launch'),
            'worker': source('WORKER', run_child('LEAF') + ' PAUSE'),
            'leaf': source('LEAF', 'PAUSE'),
        }
        linked = translate_project(sources).instantiate()
        linked.run('MAIN')
        context = linked.context
        self.assertEqual(list(context.tasks.tasks), ['MAIN', 'LIB', 'WORKER', 'LEAF'])
        self.assertEqual(value(context, 'WORKER', 'TSK_PARENT'), 1)
        self.assertEqual(value(context, 'LEAF', 'TSK_PARENT'), 3)
        self.assertEqual(value(context, 'MAIN', 'TSK_NUMCLDS'), 1)
        self.assertEqual(value(context, 'WORKER', 'TSK_NUMCLDS'), 1)
        self.assertEqual(value(context, 'LIB', 'TSK_NUMCLDS'), 0)
        for name in ('MAIN', 'WORKER', 'LEAF'):
            linked.scheduler.stop(name)

    def test_failed_start_leaves_no_parent_on_host_retry(self):
        locks = rt.GroupLocks([1], apply_directives=True)
        linked = translate_project({
            'main': source(body=run_child(), prefix='%NOLOCKGROUP'),
            'worker': source('WORKER', 'PAUSE', prefix='%LOCKGROUP=1'),
        }).instantiate(context=rt.ExecutionContext(group_locks=locks))
        holder = program(context=linked.context, name='HOLDER', prefix='%NOLOCKGROUP')
        locks.update(holder._state, 'LOCK_GROUP', 1)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'another task'):
            linked.run('MAIN')
        child = linked.programs['WORKER']
        self.assertEqual(child.task_state, 'ready')
        self.assertIsNone(child._state._task_launch)
        self.assertIsNone(child._state._task_parent)
        locks.release_owner(holder._state)
        linked.scheduler.start('WORKER')
        linked.scheduler.run()
        self.assertEqual(value(linked.context, 'WORKER', 'TSK_PARENT', prefix='%NOLOCKGROUP'), 0)
        linked.scheduler.stop('WORKER')

    def test_lineage_is_qualified_by_the_launch_registry(self):
        linked = project(run_child() + ' PAUSE')
        linked.run('MAIN')
        other = rt.TaskScheduler()
        other.bind('MAIN', linked.programs['MAIN'])
        other.bind('WORKER', linked.programs['WORKER'], attributes={'TSK_PARENT': 9})
        foreign = rt.ExecutionContext(tasks=other)
        self.assertEqual(value(foreign, 'WORKER', 'TSK_PARENT'), 9)
        self.assertEqual(value(foreign, 'MAIN', 'TSK_NUMCLDS'), 0)
        self.assertEqual(value(linked.context, 'WORKER', 'TSK_PARENT'), 1)
        linked.scheduler.stop('MAIN')
        linked.scheduler.stop('WORKER')


    def test_standalone_alias_in_another_registry_uses_metadata(self):
        context = rt.ExecutionContext()
        main = program(run_child() + ' PAUSE', context=context, name='MAIN')
        child = program('PAUSE', context=context, name='WORKER')
        context.tasks.bind('MAIN', main)
        context.tasks.bind('WORKER', child)
        with self.assertRaises(rt.KarelPause):
            main.run()

        foreign = rt.ExecutionContext()
        foreign.tasks.bind('MAIN', main)
        foreign.tasks.bind('WORKER', child, attributes={'TSK_PARENT': 9})
        self.assertEqual(value(foreign, 'WORKER', 'TSK_PARENT'), 9)
        self.assertEqual(value(foreign, 'MAIN', 'TSK_NUMCLDS'), 0)
        self.assertEqual(value(context, 'WORKER', 'TSK_PARENT'), 1)
        self.assertEqual(value(context, 'MAIN', 'TSK_NUMCLDS'), 1)
        child.stop()
        main.stop()


class TaskLineageContinuationTests(unittest.TestCase):
    def test_scheduled_powerup_cascades_across_paused_paths_once(self):
        worker = run_child('LEAF') + ' PAUSE n=2 PAUSE'
        main = run_child() + ' PAUSE n=3 PAUSE'
        linked = project(main, worker, leaf=source('LEAF', 'PAUSE n=4 PAUSE'),
                         unrelated=source('UNRELATED', 'PAUSE n=5'))
        scheduler = linked.scheduler
        scheduler.bind('WORKER_ALIAS', linked.programs['WORKER'])
        scheduler.start('UNRELATED')
        linked.run('MAIN')
        self.assertEqual(scheduler.rename('WORKER', 'RENAMED'), 0)
        scheduler.powerup('MAIN')
        self.assertEqual({name: task.task_state for name, task in linked.programs.items()},
                         {'MAIN': 'running', 'WORKER': 'running', 'LEAF': 'running', 'UNRELATED': 'paused'})
        scheduler.run()
        for name, number, powerup in (('MAIN', 3, 1), ('WORKER', 2, 0), ('LEAF', 4, 0)):
            task = linked.programs[name]
            self.assertEqual(task.snapshot()['N'], number)
            self.assertEqual(task.task_state, 'paused')
            self.assertEqual(task._state._lifecycle['CONTINUE'], 1)
            self.assertEqual(task._state._lifecycle.get('POWERUP', 0), powerup)
        for name in ('MAIN', 'WORKER_ALIAS', 'LEAF', 'UNRELATED'):
            scheduler.stop(name)

    def test_waiting_child_does_not_carry_continuation_to_paused_leaf(self):
        linked = project(run_child() + ' PAUSE', run_child('LEAF') + ' DELAY 500',
                         leaf=source('LEAF', 'PAUSE n=4'))
        scheduler = linked.scheduler
        scheduler.start('MAIN')
        for _ in range(30):
            if linked.programs['WORKER'].task_state == 'waiting':
                break
            scheduler.step()
        self.assertEqual(linked.programs['WORKER'].task_state, 'waiting')
        self.assertEqual(linked.programs['LEAF'].task_state, 'paused')
        scheduler.continue_task('MAIN')
        self.assertEqual(linked.programs['LEAF'].task_state, 'paused')
        for name in ('MAIN', 'WORKER', 'LEAF'):
            scheduler.stop(name)

    def standalone(self, main_body, worker_body, **workers):
        context = rt.ExecutionContext()
        main = program(main_body, context=context, name='MAIN')
        child = program(worker_body, context=context, name='WORKER')
        context.tasks.bind('MAIN', main)
        context.tasks.bind('WORKER', child)
        for name, body in workers.items():
            context.tasks.bind(name, program(body, context=context, name=name))
        with self.assertRaises(rt.KarelPause):
            main.run()
        return context, main, child

    def test_standalone_named_continue_delivers_descendant_handlers(self):
        body = ('n=0 CONDITION[1]: WHEN CONTINUE DO n=n+1 ENDCONDITION '
                'ENABLE CONDITION[1] PAUSE s=n PAUSE')
        context, main, child = self.standalone(
            run_child() + ' PAUSE n=3',
            run_child('LEAF') + ' ' + body, LEAF=body)
        context.tasks.bind('ALIAS', child)
        caller = program("CONT_TASK('MAIN',s)", context=context, name='CALLER')
        self.assertEqual(caller.run()['S'], 0)
        self.assertEqual(main.snapshot()['N'], 3)
        for task in (child, context.tasks.tasks['LEAF']):
            self.assertEqual(task.snapshot(), {'N': 1, 'S': 1})
            self.assertEqual(task.task_state, 'paused')
            task.stop()

    def test_standalone_explicit_child_resume_does_not_double_deliver(self):
        _, main, child = self.standalone(
            run_child() + " PAUSE CONT_TASK('WORKER',s)",
            'PAUSE n=1 PAUSE n=2')
        main.powerup()
        self.assertEqual(child.snapshot()['N'], 1)
        self.assertEqual(child._state._lifecycle['CONTINUE'], 1)
        self.assertEqual(child._state._lifecycle.get('POWERUP', 0), 0)
        self.assertEqual(main._state._lifecycle['POWERUP'], 1)
        child.stop()

    def test_standalone_remote_commands_use_live_lineage(self):
        for request in ('CONTINUE PROGRAM[1]', run_child('MAIN')):
            with self.subTest(request=request):
                context, main, child = self.standalone(run_child() + ' PAUSE n=1', 'PAUSE n=2')
                program(request, context=context, name='CALLER').run()
                self.assertEqual(main.snapshot()['N'], 1)
                self.assertEqual(child.snapshot()['N'], 2)

    def test_bare_and_numeric_self_continue_leave_child_paused(self):
        for request in ('CONTINUE', 'CONTINUE PROGRAM[1]'):
            with self.subTest(request=request):
                _, main, child = self.standalone(run_child() + ' ' + request + ' PAUSE', 'PAUSE n=2')
                self.assertEqual(main._state._lifecycle['CONTINUE'], 1)
                self.assertEqual(child.task_state, 'paused')
                main.stop()
                child.stop()

    def test_standalone_child_error_keeps_parent_at_its_new_pause(self):
        _, main, child = self.standalone(run_child() + ' PAUSE n=1 PAUSE n=2',
                                         'PAUSE n=n+1')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'):
            main.resume()
        self.assertEqual(child.task_state, 'failed')
        self.assertEqual(main.task_state, 'paused')
        self.assertEqual(main.resume()['N'], 2)


class TaskGroupInspectionTests(unittest.TestCase):
    def test_live_masks_use_only_selected_roots_grants_and_include_high_bit(self):
        bank = rt.GroupLocks([1, 2, 31], held=[31])
        context = rt.ExecutionContext(group_locks=bank)
        worker = program(context=context, name='WORKER')
        other = program(context=context, name='OTHER')
        context.tasks.bind('WORKER', worker, attributes={'TSK_LOCKGRP': 2, 'TSK_MCTL': 2})
        context.tasks.bind('OTHER', other)
        bank.update(worker._state, 'LOCK_GROUP', (1 << 30) | 1)
        bank.update(other._state, 'LOCK_GROUP', 2)
        for attribute in ('TSK_LOCKGRP', 'TSK_MCTL'):
            self.assertEqual(value(context, 'WORKER', attribute), (1 << 30) | 1)
            self.assertEqual(value(context, 'OTHER', attribute), 2)
        self.assertEqual(bank.update(worker._state, 'UNLOCK_GROUP', 1), 0)
        self.assertEqual(value(context, 'WORKER', 'TSK_LOCKGRP'), 1 << 30)
        bank.release_owner(worker._state)
        self.assertEqual(value(context, 'WORKER', 'TSK_MCTL'), 0)

    def test_missing_bank_retains_explicit_metadata_and_unavailable_status(self):
        context = rt.ExecutionContext()
        worker = program(context=context, name='WORKER')
        context.tasks.bind('WORKER', worker, attributes={'TSK_MCTL': 5})
        self.assertEqual(value(context, 'WORKER', 'TSK_MCTL'), 5)
        self.assertEqual(inspect(context, 'WORKER', 'TSK_LOCKGRP')['STATUS'], 3)

    def test_full_mask_returns_unavailable_without_overwriting_outputs(self):
        bank = rt.GroupLocks(list(range(1, 32)))
        context = rt.ExecutionContext(group_locks=bank)
        worker = program(context=context, name='WORKER')
        context.tasks.bind('WORKER', worker)
        bank.update(worker._state, 'LOCK_GROUP', 2147483647)
        for attribute in ('TSK_LOCKGRP', 'TSK_MCTL'):
            result = query(context, attribute, setup="name='worker' number=0 value=7 text='old'")
            self.assertEqual(result, {'NAME': 'worker', 'NUMBER': 0, 'VALUE': 7, 'TEXT': 'old', 'STATUS': 3})
        self.assertEqual(len(bank.owners), 31)
        bank.release_owner(worker._state)


if __name__ == '__main__':
    unittest.main()
