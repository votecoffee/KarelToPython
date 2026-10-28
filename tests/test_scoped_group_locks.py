"""Authored module-scoped logical group grants with stable task ownership."""
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from tests.test_directive_group_locks import source


U={'uninitialized':True}


def scenario(child='WRITE(\'child\')',*,main="CALL_PROG('CHILD',s) WRITE('caller')",
             main_prefix='%LOCKGROUP=1',child_prefix='%LOCKGROUP=2',groups=(1,2,3),scoped=True,seen=None):
    bank=rt.GroupLocks(list(groups),apply_directives=True,callee_scopes=scoped)
    options={} if seen is None else {'write':lambda text:seen.append((text,set(bank.owners)))}
    project=translate_project({'main':source(body=main,prefix=main_prefix),
        'child':source('CHILD',child,prefix=child_prefix)}).instantiate(
            context=rt.ExecutionContext(group_locks=bank),options=options)
    return project,bank


def direct_scope(groups=(1,2,3),child_prefix='%LOCKGROUP=2'):
    project,bank=scenario(child_prefix=child_prefix,groups=groups)
    root=project.programs['MAIN']._state;child=project.programs['CHILD']._state
    child._budget_parent=root;bank.begin(root)
    return bank,root,child


class ScopedGroupProgramTests(unittest.TestCase):
    def test_called_program_gets_only_additional_groups_then_releases_them(self):
        seen=[];project,bank=scenario(seen=seen)
        project.run('MAIN')
        self.assertEqual(seen,[('child',{1,2}),('caller',{1})]);self.assertEqual(bank.owners,{})

    def test_default_callee_policy_uses_all_configured_groups(self):
        seen=[];project,bank=scenario(seen=seen,child_prefix='')
        project.run('MAIN')
        self.assertEqual(seen,[('child',{1,2,3}),('caller',{1})]);self.assertEqual(bank.owners,{})

    def test_nolock_callee_retains_caller_groups(self):
        seen=[];project,bank=scenario(seen=seen,child_prefix='%NOLOCKGROUP')
        project.run('MAIN');self.assertEqual(seen,[('child',{1}),('caller',{1})])

    def test_nolock_caller_can_borrow_callee_groups(self):
        seen=[];project,bank=scenario(seen=seen,main_prefix='%NOLOCKGROUP')
        project.run('MAIN');self.assertEqual(seen,[('child',{2}),('caller',set())])

    def test_nested_programs_release_each_additional_level(self):
        bank=rt.GroupLocks([1,2,3],apply_directives=True,callee_scopes=True);seen=[]
        project=translate_project({'main':source(body="CALL_PROG('MIDDLE',s) WRITE('caller')",prefix='%LOCKGROUP=1'),
            'middle':source('MIDDLE',"CALL_PROG('LEAF',s) WRITE('middle')",prefix='%LOCKGROUP=2'),
            'leaf':source('LEAF',"WRITE('leaf')",prefix='%LOCKGROUP=3')}).instantiate(
                context=rt.ExecutionContext(group_locks=bank),options={'write':lambda text:seen.append((text,set(bank.owners)))})
        project.run('MAIN');self.assertEqual(seen,[('leaf',{1,2,3}),('middle',{1,2}),('caller',{1})])

    def test_call_proglin_pause_on_entry_already_holds_callee_groups(self):
        project,bank=scenario('n=7',main="CALL_PROGLIN('CHILD',1,s,TRUE) n=9")
        result=project.run('MAIN');self.assertEqual(result['MAIN']['state'],'paused')
        root=project.programs['MAIN']._state;self.assertEqual(bank.owners,{1:root,2:root})
        self.assertEqual(project.programs['CHILD'].snapshot()['N'],U)
        project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(bank.owners,{})

    def test_pause_inside_callee_retains_both_scopes_until_resume(self):
        seen=[];project,bank=scenario("PAUSE WRITE('child')",seen=seen)
        project.run('MAIN');root=project.programs['MAIN']._state
        self.assertEqual(bank.owners,{1:root,2:root});self.assertEqual(seen,[])
        project.scheduler.continue_task('MAIN');project.scheduler.run()
        self.assertEqual(seen,[('child',{1,2}),('caller',{1})]);self.assertEqual(bank.owners,{})

    def test_standalone_powerup_continuation_keeps_existing_scope(self):
        seen=[];project,bank=scenario("PAUSE WRITE('child')",seen=seen)
        task=project.programs['MAIN']
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(set(bank.owners),{1,2});task.powerup()
        self.assertEqual(seen,[('child',{1,2}),('caller',{1})]);self.assertEqual(bank.owners,{})

    def test_recursive_called_program_keeps_outer_scope_until_outer_return(self):
        seen=[];project,bank=scenario("IF UNINIT(n) THEN n=3 ENDIF n=n-1 IF n>0 THEN CALL_PROG('CHILD',s) ENDIF WRITE('child')",seen=seen)
        project.run('MAIN');self.assertEqual(seen,[('child',{1,2})]*3+[('caller',{1})])
        self.assertEqual(bank.owners,{})

    def test_root_only_opt_in_remains_unchanged(self):
        seen=[];project,bank=scenario(seen=seen,scoped=False,groups=(1,),child_prefix='%LOCKGROUP=2')
        project.run('MAIN');self.assertEqual(seen,[('child',{1}),('caller',{1})])


class ScopedGroupRoutineTests(unittest.TestCase):
    def test_linked_definition_policy_acquires_additional_groups(self):
        bank=rt.GroupLocks([1,2],apply_directives=True,callee_scopes=True);seen=[]
        project=translate_project({'main':source(body="work() WRITE('caller')",prefix='%LOCKGROUP=1',routines='ROUTINE work FROM LIB'),
            'lib':source('LIB','',prefix='%LOCKGROUP=2',routines="ROUTINE work BEGIN WRITE('library') END work")}).instantiate(
                context=rt.ExecutionContext(group_locks=bank),options={'write':lambda text:seen.append((text,set(bank.owners)))})
        project.run('MAIN');self.assertEqual(seen,[('library',{1,2}),('caller',{1})]);self.assertEqual(bank.owners,{})

    def test_forwarding_declaration_does_not_reacquire_callers_unlocked_group(self):
        bank=rt.GroupLocks([1],apply_directives=True,callee_scopes=True);seen=[]
        project=translate_project({'main':source(body="UNLOCK_GROUP(1,s) work() WRITE('caller')",prefix='%LOCKGROUP=1',routines='ROUTINE work FROM LIB'),
            'lib':source('LIB','',prefix='%NOLOCKGROUP',routines="ROUTINE work BEGIN WRITE('library') END work")}).instantiate(
                context=rt.ExecutionContext(group_locks=bank),options={'write':lambda text:seen.append((text,set(bank.owners)))})
        project.run('MAIN');self.assertEqual(seen,[('library',set()),('caller',set())])

    def test_internal_routine_reacquires_own_module_policy_for_its_scope(self):
        bank=rt.GroupLocks([1],apply_directives=True,callee_scopes=True);seen=[]
        project=translate_project({'main':source(body="UNLOCK_GROUP(1,s) work() WRITE('caller')",prefix='%LOCKGROUP=1',
            routines="ROUTINE work BEGIN WRITE('routine') END work")}).instantiate(
                context=rt.ExecutionContext(group_locks=bank),options={'write':lambda text:seen.append((text,set(bank.owners)))})
        project.run('MAIN');self.assertEqual(seen,[('routine',{1}),('caller',set())])

    def test_recursive_linked_routine_retains_outer_library_grant(self):
        bank=rt.GroupLocks([1,2],apply_directives=True,callee_scopes=True);seen=[]
        project=translate_project({'main':source(body="work(3) WRITE('caller')",prefix='%LOCKGROUP=1',routines='ROUTINE work(k:INTEGER) FROM LIB'),
            'lib':source('LIB','',prefix='%LOCKGROUP=2',routines="ROUTINE work(k:INTEGER) BEGIN IF k>1 THEN work(k-1) ENDIF WRITE('library') END work")}).instantiate(
                context=rt.ExecutionContext(group_locks=bank),options={'write':lambda text:seen.append((text,set(bank.owners)))})
        project.run('MAIN');self.assertEqual(seen,[('library',{1,2})]*3+[('caller',{1})])

    def test_pause_inside_linked_routine_keeps_stable_root_owner(self):
        bank=rt.GroupLocks([1,2],apply_directives=True,callee_scopes=True)
        project=translate_project({'main':source(body='n=work()',prefix='%LOCKGROUP=1',routines='ROUTINE work:INTEGER FROM LIB'),
            'lib':source('LIB','',prefix='%LOCKGROUP=2',routines='ROUTINE work:INTEGER BEGIN PAUSE RETURN 7 END work')}).instantiate(
                context=rt.ExecutionContext(group_locks=bank))
        project.run('MAIN');root=project.programs['MAIN']._state
        self.assertEqual(bank.owners,{1:root,2:root});self.assertEqual(project.programs['MAIN'].snapshot()['N'],U)
        project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(bank.owners,{})


class ScopedGroupOriginsTests(unittest.TestCase):
    def test_caller_manual_group_is_not_released_by_callee(self):
        seen=[];project,bank=scenario(main="LOCK_GROUP(2,s) CALL_PROG('CHILD',s) WRITE('caller')",seen=seen)
        project.run('MAIN');self.assertEqual(seen,[('child',{1,2}),('caller',{1,2})])

    def test_manual_extra_group_acquired_inside_callee_survives_return(self):
        seen=[];project,bank=scenario("LOCK_GROUP(4,s) WRITE('child')",seen=seen)
        project.run('MAIN');self.assertEqual(seen,[('child',{1,2,3}),('caller',{1,3})])

    def test_manual_unlock_then_relock_creates_new_grant_not_owned_by_scope(self):
        seen=[];project,bank=scenario("UNLOCK_GROUP(2,s) LOCK_GROUP(2,s) WRITE('child')",seen=seen)
        project.run('MAIN');self.assertEqual(seen,[('child',{1,2}),('caller',{1,2})])

    def test_idempotent_manual_relock_does_not_pin_automatic_grant(self):
        seen=[];project,bank=scenario("LOCK_GROUP(2,s) WRITE('child')",seen=seen)
        project.run('MAIN');self.assertEqual(seen,[('child',{1,2}),('caller',{1})])

    def test_manual_unlock_without_relock_does_not_restore_old_grant(self):
        seen=[];project,bank=scenario("UNLOCK_GROUP(2,s) WRITE('child')",seen=seen)
        project.run('MAIN');self.assertEqual(seen,[('child',{1}),('caller',{1})])

    def test_foreign_reacquisition_is_preserved_during_scope_and_root_cleanup(self):
        project,bank=scenario("UNLOCK_GROUP(2,s) WRITE('released')")
        foreign=project.programs['CHILD']._state
        def takeover(text):
            if text=='released':self.assertEqual(bank.update(foreign,'LOCK_GROUP',2),0)
        for task in project.programs.values():task._state._write=takeover
        # Linked program clones inherit the caller's callback, retaining this root.
        project.options['write']=takeover
        project.run('MAIN');self.assertEqual(bank.owners,{2:foreign})

    def test_old_scope_token_cannot_release_later_manual_acquisition(self):
        bank,root,child=direct_scope();scope=bank.enter_scope(child)
        self.assertEqual(set(bank.owners),{1,2});bank.leave_scope(scope)
        bank.update(root,'LOCK_GROUP',2);bank.leave_scope(scope)
        self.assertEqual(bank.owners,{1:root,2:root})

    def test_reentrant_caller_owned_busy_group_is_not_released(self):
        bank,root,child=direct_scope(child_prefix='%LOCKGROUP=2,3')
        bank.update(root,'LOCK_GROUP',2);bank.set_motion(2,'stopped')
        scope=bank.enter_scope(child);self.assertEqual(set(bank.owners),{1,2,3});bank.leave_scope(scope)
        self.assertEqual(bank.owners,{1:root,2:root});self.assertEqual(bank.motion,{2:'stopped'})

    def test_automatic_scope_release_leaves_new_busy_label_unchanged(self):
        bank,root,child=direct_scope();scope=bank.enter_scope(child);bank.set_motion(2,'executing')
        bank.leave_scope(scope)
        self.assertEqual(bank.owners,{1:root});self.assertEqual(bank.motion,{2:'executing'})


class ScopedGroupFailuresAndCleanupTests(unittest.TestCase):
    def test_foreign_entry_failure_has_no_partial_grants(self):
        bank,root,child=direct_scope(child_prefix='%LOCKGROUP=2,3')
        foreign=rt.State({},{});bank.update(foreign,'LOCK_GROUP',4);before=dict(bank.owners)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'another task'):bank.enter_scope(child)
        self.assertEqual(bank.owners,before)

    def test_unknown_and_unowned_busy_entry_fail_atomically(self):
        for prefix,busy in (('%LOCKGROUP=2,4',False),('%LOCKGROUP=2,3',True)):
            with self.subTest(prefix=prefix):
                bank,root,child=direct_scope(child_prefix=prefix)
                if busy:bank.set_motion(3,'stopped')
                before=dict(bank.owners)
                with self.assertRaises(rt.KarelRuntimeError):bank.enter_scope(child)
                self.assertEqual(bank.owners,before)

    def test_failed_call_preserves_index_and_callee_body_globals(self):
        project,bank=scenario('n=9',main="s=77 CALL_PROG('CHILD',s)",child_prefix='%LOCKGROUP=2,4')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'unconfigured'):project.run('MAIN')
        self.assertEqual(project.programs['MAIN'].snapshot()['S'],77)
        self.assertEqual(project.programs['CHILD'].snapshot()['N'],U)
        self.assertEqual(bank.owners,{})

    def test_abort_and_runtime_error_release_callee_before_root_cleanup(self):
        for body,error in (('ABORT',rt.KarelAbort),('n=1 DIV 0',rt.KarelRuntimeError)):
            with self.subTest(body=body):
                project,bank=scenario(body);after=[];original=bank.leave_scope
                def leave(scope):
                    original(scope)
                    if scope and scope[2]:after.append(set(bank.owners))
                with patch.object(bank,'leave_scope',side_effect=leave):
                    with self.assertRaises(error):project.run('MAIN')
                self.assertIn({1},after);self.assertEqual(bank.owners,{})
                self.assertEqual(project.programs['MAIN']._state._group_scope_frames,[])

    def test_stop_closes_nested_scopes_and_preserves_foreign_ownership(self):
        project,bank=scenario('PAUSE');foreign=rt.State({},{});bank.update(foreign,'LOCK_GROUP',4)
        project.run('MAIN');self.assertEqual(set(bank.owners),{1,2,3})
        project.scheduler.stop('MAIN')
        self.assertEqual(bank.owners,{3:foreign});self.assertEqual(project.programs['MAIN']._state._group_scope_frames,[])
        self.assertEqual(project.programs['MAIN']._state._task_frames,[])

    def test_budget_failure_closes_all_owned_scopes(self):
        project,bank=scenario('WHILE TRUE DO ENDWHILE');project.scheduler.max_steps=12
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):project.run('MAIN')
        self.assertEqual(bank.owners,{});self.assertEqual(bank._ownership_tokens,{})

    def test_rename_preserves_scoped_owner_until_stop(self):
        project,bank=scenario('PAUSE');project.run('MAIN');root=project.programs['MAIN']._state
        project.scheduler.rename('MAIN','RENAMED');self.assertEqual(bank.owners,{1:root,2:root})
        project.scheduler.stop('RENAMED');self.assertEqual(bank.owners,{})

    def test_frame_entry_diagnostics_failure_rolls_back_scope_and_stack(self):
        bank,root,child=direct_scope();child.execution.diagnostics=rt.DiagnosticLog()
        with patch.object(child.execution.diagnostics,'observe',side_effect=rt.KarelRuntimeError('diagnostic failure')):
            with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'diagnostic failure'):
                child.enter_routine({},routine='')
        self.assertEqual(bank.owners,{1:root})
        self.assertEqual((child.local_frames,child._group_scope_frames,root._task_frames,child.call_depth),([],[],[],0))

    def test_frame_exit_diagnostics_failure_still_releases_scope_and_stack(self):
        bank,root,child=direct_scope();child.execution.diagnostics=rt.DiagnosticLog()
        with rt._numeric_scope('pythonic'):child.enter_routine({},routine='')
        with patch.object(child.execution.diagnostics,'record',side_effect=rt.KarelRuntimeError('diagnostic failure')):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'diagnostic failure'):child.leave_routine()
        self.assertEqual(bank.owners,{1:root})
        self.assertEqual((child.local_frames,child._group_scope_frames,root._task_frames,child.call_depth),([],[],[],0))

    def test_parameter_or_depth_failure_does_not_acquire_groups(self):
        bank,root,child=direct_scope()
        with rt._numeric_scope('pythonic'):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'binding'):child.enter_routine({'P':rt.REAL},arguments={'P':rt.Reference(rt.INTEGER,{'v':1},'v')})
            child.call_depth=64
            with self.assertRaisesRegex(rt.KarelRuntimeError,'depth'):child.enter_routine({})
        self.assertEqual(bank.owners,{1:root});self.assertEqual(child._group_scope_frames,[])


class ScopedGroupPersistenceAndOptInTests(unittest.TestCase):
    def test_true_scope_flag_roundtrips_without_live_ownership(self):
        bank=rt.GroupLocks([1,2],apply_directives=True,callee_scopes=True)
        config=json.loads(json.dumps(bank.to_config()))
        self.assertEqual(config,{'groups':[1,2],'motion':{},'apply_directives':True,'callee_scopes':True})
        self.assertEqual(rt.GroupLocks.from_config(config).to_config(),config)
        self.assertTrue(bank.snapshot()['callee_scopes'])

    def test_false_scope_flag_keeps_root_only_json_shape(self):
        bank=rt.GroupLocks.from_config({'groups':[1],'apply_directives':True,'callee_scopes':False})
        self.assertEqual(bank.to_config(),{'groups':[1],'motion':{},'apply_directives':True})
        self.assertNotIn('callee_scopes',bank.snapshot())

    def test_scope_flag_requires_boolean_and_directive_opt_in(self):
        for value in (0,1,None,'true',[],{}):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'BOOLEAN'):
                rt.GroupLocks([1],apply_directives=True,callee_scopes=value)
        with self.assertRaisesRegex(ValueError,'requires apply_directives'):rt.GroupLocks([1],callee_scopes=True)
        with self.assertRaisesRegex(ValueError,'requires apply_directives'):rt.GroupLocks.from_config({'groups':[1],'callee_scopes':True})

    def test_context_persists_settings_after_scope_and_root_finish(self):
        project,bank=scenario();project.run('MAIN')
        config=json.loads(json.dumps(project.context.to_config()))
        self.assertTrue(config['group_locks']['callee_scopes'])
        self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)
        self.assertNotIn('_ownership_tokens',config['group_locks'])

    def test_live_scoped_ownership_cannot_be_saved(self):
        project,bank=scenario('PAUSE');project.run('MAIN')
        with self.assertRaisesRegex(ValueError,'live group ownership'):project.context.to_config()
        project.scheduler.stop('MAIN');self.assertIsInstance(project.context.to_config(),dict)

    def test_absent_bank_and_default_opt_out_keep_legacy_called_policy(self):
        for bank in (None,rt.GroupLocks([1])):
            with self.subTest(bank=bank):
                project=translate_project({'main':source(body="CALL_PROG('CHILD',s)",prefix='%LOCKGROUP=1'),
                    'child':source('CHILD','n=7',prefix='%LOCKGROUP=2')}).instantiate(context=rt.ExecutionContext(group_locks=bank))
                project.run('MAIN');self.assertEqual(project.programs['CHILD'].snapshot()['N'],7)


if __name__=='__main__':unittest.main()
