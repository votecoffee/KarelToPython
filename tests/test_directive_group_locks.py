"""Authored opt-in root-entry logical group acquisition and ownership lifetime."""
import json
import unittest
from unittest.mock import patch

from karel2py import translate,translate_project,runtime as rt


U={'uninitialized':True}


def source(name='MAIN',body='PAUSE',prefix='',decl='n,s:INTEGER',routines=''):
    return f'PROGRAM {name}\n{prefix}\nVAR {decl}\n{routines}\nBEGIN {body} END {name}'


def program(body='PAUSE',*,prefix='',bank=None,context=None,cooperative=True,name='MAIN',**options):
    result=translate(source(name,body,prefix),cooperative=cooperative)
    namespace={'__name__':'directive_group_test'};exec(result.python_source,namespace)
    return namespace['Program'](context=context or rt.ExecutionContext(group_locks=bank),**options)


class DirectiveGroupEntryTests(unittest.TestCase):
    def test_opt_out_retains_existing_metadata_only_behavior(self):
        bank=rt.GroupLocks([1]);task=program(prefix='%LOCKGROUP=2',bank=bank)
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(bank.owners,{});task.stop()

    def test_absent_bank_does_not_discover_or_create_group_locks(self):
        task=program('n=7',prefix='%LOCKGROUP=1')
        self.assertEqual(task.run()['N'],7);self.assertIsNone(task._state.execution.group_locks)

    def test_default_policy_acquires_all_explicitly_configured_groups(self):
        bank=rt.GroupLocks([3,1],apply_directives=True);task=program(bank=bank)
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(bank.owners,{1:task._state,3:task._state});task.stop()

    def test_explicit_policy_selects_only_listed_groups(self):
        bank=rt.GroupLocks([1,2,3],apply_directives=True);task=program(prefix='%LOCKGROUP=3,1',bank=bank)
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(bank.owners,{1:task._state,3:task._state});task.stop()

    def test_nolockgroup_acquires_no_groups(self):
        bank=rt.GroupLocks([1,2],apply_directives=True);task=program(prefix='%NOLOCKGROUP',bank=bank)
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(bank.owners,{});task.stop()

    def test_default_robot_group_does_not_narrow_implicit_lock_groups(self):
        bank=rt.GroupLocks([1,3],apply_directives=True);task=program(prefix='%DEFGROUP=3',bank=bank)
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(set(bank.owners),{1,3});task.stop()

    def test_group_31_is_supported_without_signed_mask_overflow(self):
        bank=rt.GroupLocks([1,31],apply_directives=True);task=program(prefix='%LOCKGROUP=31',bank=bank)
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(bank.owners,{31:task._state});task.stop()

    def test_busy_entry_is_atomic_and_preserves_preowned_groups_and_source(self):
        for cooperative in (False,True):
            with self.subTest(cooperative=cooperative):
                bank=rt.GroupLocks([1,2,3],apply_directives=True)
                task=program('n=99',prefix='%LOCKGROUP=1,2',bank=bank,cooperative=cooperative)
                foreign=program(name='OTHER',bank=bank,prefix='%NOLOCKGROUP')
                bank.update(task._state,'LOCK_GROUP',4);bank.update(foreign._state,'LOCK_GROUP',2)
                task._state.values['N']=77;before=dict(bank.owners)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'another task'):task.run()
                self.assertEqual(bank.owners,before);self.assertEqual(task.snapshot()['N'],77)
                self.assertIsNone(getattr(task,'_execution',None));self.assertFalse(task._state._driving)

    def test_unconfigured_entry_preserves_preowned_groups_and_source(self):
        bank=rt.GroupLocks([1,2],apply_directives=True);task=program('n=99',prefix='%LOCKGROUP=1,3',bank=bank)
        bank.update(task._state,'LOCK_GROUP',2);before=dict(bank.owners)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'unconfigured groups: 3'):task.run()
        self.assertEqual(bank.owners,before);self.assertEqual(task.snapshot()['N'],U)

    def test_unowned_busy_labels_fail_without_partial_acquisition(self):
        for label in ('executing','stopped'):
            with self.subTest(label=label):
                bank=rt.GroupLocks([1,2],motion={2:label},apply_directives=True);task=program(bank=bank)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'busy label'):task.run()
                self.assertEqual(bank.owners,{});self.assertEqual(bank.motion,{2:label})

    def test_reentrant_owned_busy_group_is_retained_at_entry(self):
        bank=rt.GroupLocks([1],motion={1:'stopped'},apply_directives=True);task=program(bank=bank)
        bank.update(task._state,'LOCK_GROUP',1)
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(bank.owners,{1:task._state});task.stop()
        self.assertEqual(bank.motion,{1:'stopped'})

    def test_nolockgroup_does_not_unlock_manually_held_groups(self):
        bank=rt.GroupLocks([1],apply_directives=True);task=program(bank=bank,prefix='%NOLOCKGROUP')
        bank.update(task._state,'LOCK_GROUP',1)
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(bank.owners,{1:task._state});task.stop()

    def test_invalid_host_requirements_fail_closed(self):
        for groups in ((1,1),(0,),(32,),(True,),1,'1',{'1':True}):
            with self.subTest(groups=groups):
                bank=rt.GroupLocks([1],apply_directives=True);task=program(bank=bank)
                task._state._source_settings['lock_groups']=groups
                with self.assertRaisesRegex(rt.KarelRuntimeError,'requirements'):task.run()
                self.assertEqual(bank.owners,{})

    def test_manual_lock_group_keeps_partial_acquisition_contract(self):
        bank=rt.GroupLocks([1,2],apply_directives=True);foreign=program(bank=bank,name='FOREIGN')
        bank.update(foreign._state,'LOCK_GROUP',2)
        task=program('LOCK_GROUP(3,s) PAUSE',bank=bank,prefix='%NOLOCKGROUP')
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(task.snapshot()['S'],2)
        self.assertEqual(bank.owners,{1:task._state,2:foreign._state})
        task.stop();self.assertEqual(bank.owners,{2:foreign._state})


class DirectiveGroupLifetimeTests(unittest.TestCase):
    def test_pure_standalone_body_observes_locks_and_completion_releases_them(self):
        for cooperative in (False,True):
            with self.subTest(cooperative=cooperative):
                bank=rt.GroupLocks([1],apply_directives=True);seen=[]
                task=program("WRITE('body') n=7",bank=bank,cooperative=cooperative,
                             write=lambda text:seen.append(dict(bank.owners)))
                self.assertEqual(task.run()['N'],7);self.assertEqual(seen,[{1:task._state}])
                self.assertEqual(bank.owners,{})

    def test_pause_retains_and_resume_does_not_reacquire_explicitly_unlocked_group(self):
        bank=rt.GroupLocks([1],apply_directives=True);seen=[]
        task=program("PAUSE WRITE('continued')",bank=bank,write=lambda text:seen.append(dict(bank.owners)))
        with patch.object(bank,'begin',wraps=bank.begin) as begin:
            with self.assertRaises(rt.KarelPause):task.run()
            self.assertEqual(bank.owners,{1:task._state})
            self.assertEqual(bank.update(task._state,'UNLOCK_GROUP',1),0)
            task.resume();self.assertEqual(begin.call_count,1)
        self.assertEqual(seen,[{}]);self.assertEqual(bank.owners,{})

    def test_terminal_failures_release_only_this_root(self):
        for body,error in (('ABORT',rt.KarelAbort),('n=1 DIV 0',rt.KarelRuntimeError)):
            with self.subTest(body=body):
                bank=rt.GroupLocks([1,2],apply_directives=True);foreign=program(name='FOREIGN',bank=bank)
                bank.update(foreign._state,'LOCK_GROUP',2)
                task=program(body,bank=bank,prefix='%LOCKGROUP=1')
                with self.assertRaises(error):task.run()
                self.assertEqual(bank.owners,{2:foreign._state})

    def test_budget_failure_releases_root_groups(self):
        bank=rt.GroupLocks([1],apply_directives=True);task=program('WHILE TRUE DO ENDWHILE',bank=bank)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):task.run(max_steps=5)
        self.assertEqual(bank.owners,{})

    def test_stop_releases_groups_even_with_busy_label(self):
        bank=rt.GroupLocks([1],apply_directives=True);task=program(bank=bank)
        with self.assertRaises(rt.KarelPause):task.run()
        bank.set_motion(1,'stopped');task.stop()
        self.assertEqual(bank.owners,{});self.assertEqual(bank.motion,{1:'stopped'})

    def test_normal_rerun_applies_policy_once_per_new_run(self):
        bank=rt.GroupLocks([1],apply_directives=True);task=program('n=7',bank=bank)
        with patch.object(bank,'begin',wraps=bank.begin) as begin:
            task.run();task.run();self.assertEqual(begin.call_count,2)
        self.assertEqual(bank.owners,{})

    def test_failed_scheduler_start_keeps_ready_state_and_can_retry(self):
        bank=rt.GroupLocks([1],apply_directives=True);ctx=rt.ExecutionContext(group_locks=bank)
        project=translate_project({'main':source(body='n=7 PAUSE'),'second':source('SECOND','n=9')}).instantiate(context=ctx)
        project.scheduler.start('MAIN');project.scheduler.run()
        owner=project.programs['MAIN']._state
        with self.assertRaisesRegex(rt.KarelRuntimeError,'another task'):project.scheduler.start('SECOND')
        second=project.programs['SECOND']
        self.assertEqual(second.task_state,'ready');self.assertIsNone(getattr(second,'_execution',None))
        self.assertEqual(second.snapshot()['N'],U);self.assertEqual(bank.owners,{1:owner})
        project.scheduler.stop('MAIN');project.scheduler.start('SECOND');project.scheduler.run()
        self.assertEqual(second.snapshot()['N'],9);self.assertEqual(bank.owners,{})

    def test_rename_retains_stable_owner_until_stop(self):
        bank=rt.GroupLocks([1],apply_directives=True)
        project=translate_project({'main':source()}).instantiate(context=rt.ExecutionContext(group_locks=bank))
        project.run('MAIN');owner=project.programs['MAIN']._state
        self.assertEqual(project.scheduler.rename('MAIN','RENAMED'),0)
        self.assertEqual(bank.owners,{1:owner});project.scheduler.stop('RENAMED')
        self.assertEqual(bank.owners,{})


class DirectiveGroupNestedPolicyTests(unittest.TestCase):
    def test_called_program_directive_is_deferred_and_caller_lock_survives_return(self):
        bank=rt.GroupLocks([1],apply_directives=True)
        project=translate_project({'main':source(body="CALL_PROG('CHILD',s) PAUSE",prefix='%LOCKGROUP=1'),
            'child':source('CHILD','n=7',prefix='%LOCKGROUP=2')}).instantiate(context=rt.ExecutionContext(group_locks=bank))
        with patch.object(bank,'begin',wraps=bank.begin) as begin:project.run('MAIN');self.assertEqual(begin.call_count,1)
        self.assertEqual(bank.owners,{1:project.programs['MAIN']._state})
        self.assertEqual(project.programs['CHILD'].snapshot()['N'],7);project.scheduler.stop('MAIN')

    def test_nolock_caller_does_not_acquire_called_program_groups(self):
        bank=rt.GroupLocks([1],apply_directives=True);seen=[]
        project=translate_project({'main':source(body="CALL_PROG('CHILD',s) PAUSE",prefix='%NOLOCKGROUP'),
            'child':source('CHILD',"WRITE('child') n=7",prefix='%LOCKGROUP=1')}).instantiate(
                context=rt.ExecutionContext(group_locks=bank),options={'write':lambda text:seen.append(dict(bank.owners))})
        project.run('MAIN');self.assertEqual(seen,[{}]);self.assertEqual(bank.owners,{})
        project.scheduler.stop('MAIN')

    def test_from_routine_uses_calling_root_policy(self):
        bank=rt.GroupLocks([1],apply_directives=True)
        project=translate_project({'main':source(body='n=work() PAUSE',prefix='%LOCKGROUP=1',routines='ROUTINE work:INTEGER FROM LIB'),
            'lib':source('LIB','',prefix='%LOCKGROUP=2',routines='ROUTINE work:INTEGER BEGIN RETURN 7 END work')}).instantiate(
                context=rt.ExecutionContext(group_locks=bank))
        project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['N'],7)
        self.assertEqual(bank.owners,{1:project.programs['MAIN']._state});project.scheduler.stop('MAIN')

    def test_pause_inside_called_program_retains_caller_lock(self):
        bank=rt.GroupLocks([1],apply_directives=True)
        project=translate_project({'main':source(body="CALL_PROG('CHILD',s) n=9",prefix='%LOCKGROUP=1'),
            'child':source('CHILD','PAUSE n=7',prefix='%NOLOCKGROUP')}).instantiate(context=rt.ExecutionContext(group_locks=bank))
        project.run('MAIN');owner=project.programs['MAIN']._state
        self.assertEqual(bank.owners,{1:owner})
        project.scheduler.continue_task('MAIN');project.scheduler.run()
        self.assertEqual(project.programs['MAIN'].snapshot()['N'],9);self.assertEqual(bank.owners,{})

    def test_manual_lock_in_linked_routine_uses_root_and_retains_until_terminal(self):
        bank=rt.GroupLocks([1,2],apply_directives=True)
        project=translate_project({'main':source(body='work() PAUSE',prefix='%NOLOCKGROUP',routines='ROUTINE work FROM LIB'),
            'lib':source('LIB','',prefix='%NOLOCKGROUP',routines='ROUTINE work BEGIN LOCK_GROUP(2,s) END work')}).instantiate(
                context=rt.ExecutionContext(group_locks=bank))
        project.run('MAIN');self.assertEqual(bank.owners,{2:project.programs['MAIN']._state})
        project.scheduler.stop('MAIN');self.assertEqual(bank.owners,{})

    def test_recursive_program_call_does_not_repeat_root_acquisition(self):
        bank=rt.GroupLocks([1],apply_directives=True)
        task=program("IF UNINIT(n) THEN n=3 ENDIF n=n-1 IF n>0 THEN CALL_PROG('MAIN',s) ENDIF",bank=bank)
        with patch.object(bank,'begin',wraps=bank.begin) as begin:
            self.assertEqual(task.run()['N'],0);self.assertEqual(begin.call_count,1)
        self.assertEqual(bank.owners,{})


class DirectiveGroupPersistenceTests(unittest.TestCase):
    def test_enabled_flag_roundtrips_without_ownership(self):
        bank=rt.GroupLocks([1,3],motion={3:'stopped'},apply_directives=True)
        config=json.loads(json.dumps(bank.to_config()))
        self.assertTrue(config['apply_directives']);self.assertEqual(rt.GroupLocks.from_config(config).to_config(),config)

    def test_default_and_explicit_false_keep_legacy_configuration_shape(self):
        expected={'groups':[1],'motion':{}}
        self.assertEqual(rt.GroupLocks([1]).to_config(),expected)
        self.assertEqual(rt.GroupLocks.from_config({**expected,'apply_directives':False}).to_config(),expected)
        self.assertNotIn('apply_directives',rt.GroupLocks([1]).snapshot())

    def test_context_flag_persists_after_explicit_terminal_cleanup(self):
        bank=rt.GroupLocks([1],apply_directives=True);ctx=rt.ExecutionContext(group_locks=bank);task=program(context=ctx)
        with self.assertRaises(rt.KarelPause):task.run()
        with self.assertRaisesRegex(ValueError,'live group ownership'):ctx.to_config()
        task.stop();config=json.loads(json.dumps(ctx.to_config()))
        self.assertTrue(config['group_locks']['apply_directives'])
        self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)

    def test_snapshot_is_detached_and_contains_enabled_flag(self):
        bank=rt.GroupLocks([1],apply_directives=True);snap=bank.snapshot()
        snap['groups'].append(2);snap['owners']['1']='fake';snap['apply_directives']=False
        self.assertEqual(bank.groups,(1,));self.assertEqual(bank.owners,{});self.assertTrue(bank.apply_directives)

    def test_invalid_opt_in_values_fail_without_coercion(self):
        for value in (0,1,None,'true',[],{}):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError,'BOOLEAN'):rt.GroupLocks([1],apply_directives=value)
                with self.assertRaisesRegex(ValueError,'BOOLEAN'):rt.GroupLocks.from_config({'groups':[1],'apply_directives':value})

    def test_malformed_mutated_runtime_flag_fails_closed(self):
        bank=rt.GroupLocks([1],apply_directives=True);bank.apply_directives=1;task=program(bank=bank)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'BOOLEAN'):task.run()
        self.assertEqual(bank.owners,{})


if __name__=='__main__':unittest.main()
