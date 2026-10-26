"""Authored same-task program calls and explicit logical group ownership."""
import json
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


def module(name,body,*,decl='n,e,s:INTEGER',routines='',context=None,cooperative=True,prefix=''):
    result=translate(f'PROGRAM {name}\n{prefix}\nVAR {decl} {routines} BEGIN {body} END {name}',cooperative=cooperative)
    namespace={};exec(result.python_source,namespace)
    return namespace['Program'](context=context)


def project(main,child,*,decl='n,e,s:INTEGER',child_decl='n,s:INTEGER',context=None):
    return translate_project({'main':source('MAIN',main,decl=decl),
        'child':source('CHILD',child,decl=child_decl)}).instantiate(context=context)


class ProgramCallTests(unittest.TestCase):
    def test_call_reuses_globals_and_cache_without_starting_other_task(self):
        p=project("CALL_PROG('child',e) CALL_PROG('CHILD',s)",'IF UNINIT(n) THEN n=0 ENDIF n=n+1')
        result=p.run('MAIN')
        self.assertEqual(result['MAIN']['values']['E'],result['MAIN']['values']['S'])
        self.assertEqual(result['CHILD'],{'state':'ready','values':{'N':2,'S':{'uninitialized':True}}})
        self.assertEqual(p.context.program_entries,{'CHILD':1})

    def test_karel_call_line_always_starts_at_beginning(self):
        for line in (0,1,40):
            p=project(f"CALL_PROGLIN('CHILD',{line},e,FALSE)",'n=9')
            p.run('MAIN');self.assertEqual(p.programs['CHILD'].snapshot()['N'],9)

    def test_pause_on_entry_retains_index_and_defers_body(self):
        p=project("CALL_PROGLIN('CHILD',1,e,TRUE) n=8",'n=9')
        result=p.run('MAIN')
        self.assertEqual(result['MAIN']['state'],'paused')
        self.assertEqual(result['MAIN']['values']['E'],1)
        self.assertEqual(result['CHILD']['values']['N'],{'uninitialized':True})
        self.assertEqual(len(p.programs['MAIN']._state._task_frames),1)
        p.scheduler.continue_task('MAIN');p.scheduler.run()
        self.assertEqual(p.programs['MAIN'].snapshot()['N'],8)
        self.assertEqual(p.programs['CHILD'].snapshot()['N'],9)
        self.assertEqual(p.programs['MAIN']._state._task_frames,[])

    def test_pause_inside_body_preserves_callee_cursor(self):
        p=project("CALL_PROG('CHILD',e) n=8",'n=1 PAUSE n=n+1')
        self.assertEqual(p.run('MAIN')['MAIN']['state'],'paused')
        self.assertEqual(p.programs['CHILD'].snapshot()['N'],1)
        p.scheduler.continue_task('MAIN');p.scheduler.run()
        self.assertEqual(p.programs['CHILD'].snapshot()['N'],2)

    def test_missing_invalid_negative_line_and_noncooperative_targets_preserve_index(self):
        for call in ("CALL_PROG('MISSING',e)","CALL_PROG('bad.name',e)","CALL_PROGLIN('CHILD',-1,e,FALSE)"):
            ctx=rt.ExecutionContext();module('CHILD','n=3',context=ctx)
            caller=module('MAIN','e=77 '+call,context=ctx)
            with self.assertRaises(rt.KarelRuntimeError):caller.run()
            self.assertEqual(caller.snapshot()['E'],77,call);self.assertEqual(ctx.program_entries,{})
        ctx=rt.ExecutionContext();module('CHILD','n=3',context=ctx,cooperative=False)
        caller=module('MAIN',"e=77 CALL_PROG('CHILD',e)",context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cooperative'):caller.run()
        self.assertEqual(caller.snapshot()['E'],77)

    def test_opaque_teach_program_cannot_be_executed(self):
        ctx=rt.ExecutionContext(teach_programs=rt.TeachPrograms({'CHILD':{'instructions':['opaque']}}))
        caller=module('MAIN',"e=77 CALL_PROG('CHILD',e)",context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'attached'):caller.run()
        self.assertEqual(caller.snapshot()['E'],77)

    def test_standalone_explicit_cooperative_attachment(self):
        ctx=rt.ExecutionContext();callee=module('CHILD','n=6',context=ctx)
        caller=module('MAIN',"CALL_PROG('CHILD',e) n=8",context=ctx)
        self.assertEqual(caller.run()['N'],8)
        self.assertEqual(callee.snapshot()['N'],6);self.assertEqual(callee.task_state,'ready')

    def test_self_calls_have_separate_cursors_and_shared_globals(self):
        p=module('MAIN',"IF UNINIT(n) THEN n=3 ENDIF n=n-1 IF n>0 THEN CALL_PROG('MAIN',e) ENDIF")
        self.assertEqual(p.run()['N'],0);self.assertEqual(p._state._task_frames,[])

    def test_unbounded_recursion_reaches_shared_call_depth_guard(self):
        p=module('MAIN',"CALL_PROG('MAIN',e)")
        with self.assertRaisesRegex(rt.KarelRuntimeError,'call-depth'):p.run(max_steps=100000)
        self.assertEqual((p._state._task_frames,p._state.local_frames,p._state.call_depth),([],[],0))

    def test_callee_uses_calling_root_step_budget(self):
        ctx=rt.ExecutionContext();module('CHILD','WHILE TRUE DO ENDWHILE',context=ctx)
        caller=module('MAIN',"CALL_PROG('CHILD',e)",context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):caller.run(max_steps=12)
        self.assertEqual(caller.task_state,'failed');self.assertEqual(caller._state._task_frames,[])

    def test_abort_propagates_to_calling_root_and_cleans_frames(self):
        p=project("CALL_PROG('CHILD',e) n=8",'n=2 ABORT')
        with self.assertRaises(rt.KarelAbort):p.run('MAIN')
        root=p.programs['MAIN'];self.assertEqual(root.task_state,'aborted')
        self.assertIsNotNone(root.abort_info);self.assertEqual(root._state._task_frames,[])
        self.assertEqual(root.snapshot()['N'],{'uninitialized':True})

    def test_runtime_failure_cleans_frames_and_marks_request_failed(self):
        p=project("CALL_PROG('CHILD',e)",'n=1 n=n DIV 0')
        with self.assertRaises(rt.KarelRuntimeError):p.run('MAIN')
        root=p.programs['MAIN'];self.assertEqual(root.task_state,'failed')
        self.assertEqual(root._state._task_frames,[])
        self.assertEqual(root.service_requests[0]['outcome'],'failed')

    def test_stop_cancels_suspended_invocation(self):
        p=project("CALL_PROG('CHILD',e)",'n=1 PAUSE n=2')
        p.run('MAIN');p.scheduler.stop('MAIN')
        self.assertEqual(p.programs['MAIN']._state._task_frames,[])
        self.assertEqual(p.programs['CHILD'].snapshot()['N'],1)
        self.assertEqual(p.programs['MAIN'].service_requests[0]['outcome'],'cancelled')

    def test_concurrent_invocations_do_not_share_stacks(self):
        p=translate_project({'a':source('A',"CALL_PROG('CHILD',s)"),'b':source('B',"CALL_PROG('CHILD',s)"),
            'child':source('CHILD','n=n+1 PAUSE n=n+1')}).instantiate()
        p.programs['CHILD']._state.values['N']=0
        p.scheduler.start('A');p.scheduler.start('B');p.scheduler.run()
        self.assertEqual(p.programs['CHILD'].snapshot()['N'],2)
        self.assertEqual([len(p.programs[key]._state._task_frames) for key in ('A','B')],[1,1])
        p.scheduler.continue_task('A');p.scheduler.continue_task('B');p.scheduler.run()
        self.assertEqual(p.programs['CHILD'].snapshot()['N'],4)
        self.assertEqual([p.programs[key]._state._task_frames for key in ('A','B')],[[],[]])

    def test_nested_external_routine_and_byname_use_calling_root(self):
        p=translate_project({'main':source('MAIN',"n=4 CALL_PROG('CHILD',s)"),
            'child':source('CHILD','helper',routines='ROUTINE helper FROM LIB'),
            'lib':source('LIB', '',routines="ROUTINE put(x:INTEGER) BEGIN x=x+1 END put ROUTINE helper BEGIN put(BYNAME('','n',s)) END helper")}).instantiate()
        p.run('MAIN');self.assertEqual(p.programs['MAIN'].snapshot()['N'],5)

    def test_imported_globals_and_outputs_keep_caller_services(self):
        p=translate_project({'main':source('MAIN',"n=4 CALL_PROG('CHILD',s) WRITE('after')"),
            'child':source('CHILD',"n=n+1 WRITE('child')",decl='n FROM MAIN:INTEGER')}).instantiate()
        p.run('MAIN');root=p.programs['MAIN']
        self.assertEqual(root.snapshot()['N'],5)
        self.assertEqual([row['text'] for row in root.write_requests],['child','after'])

    def test_curr_prog_and_trace_identify_nested_program(self):
        p=project("CALL_PROG('CHILD',e)",'text=CURR_PROG',child_decl='text:STRING[12]')
        p.scheduler.set_attribute('MAIN','TSK_TRACE',1);p.run('MAIN')
        self.assertEqual(p.programs['CHILD'].snapshot()['TEXT'],'CHILD')
        self.assertTrue(any(row['program']=='CHILD' and row['routine']=='' for row in p.programs['MAIN'].task_trace))

    def test_index_cache_is_not_a_persisted_executable_link(self):
        p=project("CALL_PROG('CHILD',e)",'n=4');p.run('MAIN')
        config=json.loads(json.dumps(p.context.to_config()));ctx=rt.ExecutionContext.from_config(config)
        self.assertEqual(ctx.program_entries,{});self.assertEqual(ctx.variables.programs,{})
        q=project("CALL_PROG('CHILD',e)",'n=5',context=ctx);q.run('MAIN')
        self.assertEqual(q.programs['CHILD'].snapshot()['N'],5)

    def test_indirect_for_guards_and_explicit_user_override(self):
        for call in ("CALL_PROG('CHILD',e)","CALL_PROGLIN('CHILD',0,e,FALSE)"):
            with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO '+call+' ENDFOR',decl='n,e:INTEGER')
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
        self.assertEqual(run('CALL_PROG(7)',routines='ROUTINE CALL_PROG(x:INTEGER) BEGIN n=x END CALL_PROG')['N'],7)

    def test_call_signatures_fail_closed(self):
        for call in ("CALL_PROG('CHILD',0)","CALL_PROG(7,e)","CALL_PROGLIN('CHILD',0,e,1)","CALL_PROGLIN('CHILD',e)"):
            with self.assertRaises(TranslationError):compile_program(call,decl='e:INTEGER')

    def test_program_calls_from_hidden_routines_keep_for_guards(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('FOR n=1 TO 2 DO hidden ENDFOR',routines="ROUTINE hidden VAR cache:INTEGER BEGIN CALL_PROG('CHILD',cache) END hidden")
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_calling_root_frame_and_tpe_arguments_are_inherited(self):
        ctx=rt.ExecutionContext(parameters=rt.CallParameters({'MAIN':{1:17},'CHILD':{1:99}}))
        p=project("CALL_PROG('CHILD',e)",'GET_TPE_PRM(1,kind,n,x,text,s)',
            child_decl='n,s,kind:INTEGER x:REAL text:STRING[16]',context=ctx)
        p.run('MAIN');self.assertEqual(p.programs['CHILD'].snapshot()['N'],17)

    def test_nested_calls_expose_current_program_on_calling_task(self):
        p=project("CALL_PROG('CHILD',e)","who='MAIN' task=0 GET_TSK_INFO(who,task,TSK_PROGNAME,n,text,s)",
            child_decl='who,text:STRING[36] task,n,s:INTEGER')
        p.run('MAIN');self.assertEqual(p.programs['CHILD'].snapshot()['TEXT'],'CHILD')


class GroupOwnershipTests(unittest.TestCase):
    def test_lock_relock_and_zero_mask_are_idempotent(self):
        bank=rt.GroupLocks([1,2]);p=module('MAIN','LOCK_GROUP(3,s) LOCK_GROUP(1,s) LOCK_GROUP(0,s) PAUSE',context=rt.ExecutionContext(group_locks=bank))
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['S'],0);self.assertEqual(set(bank.owners),{1,2})
        self.assertTrue(all(owner is p._state for owner in bank.owners.values()));p.stop()

    def test_competing_lock_partially_acquires_available_groups(self):
        bank=rt.GroupLocks([1,2]);a=module('A','');b=module('B','')
        self.assertEqual(bank.update(a._state,'LOCK_GROUP',1),0)
        self.assertEqual(bank.update(b._state,'LOCK_GROUP',3),2)
        self.assertIs(bank.owners[1],a._state);self.assertIs(bank.owners[2],b._state)

    def test_foreign_unlock_retains_other_owners(self):
        bank=rt.GroupLocks([1,2]);a=module('A','');b=module('B','')
        bank.update(a._state,'LOCK_GROUP',1);bank.update(b._state,'LOCK_GROUP',2)
        self.assertEqual(bank.update(b._state,'UNLOCK_GROUP',3),2)
        self.assertEqual(bank.owners,{1:a._state})

    def test_busy_motion_labels_retain_ownership_and_release_idle_groups(self):
        for label,code in (('executing',17039),('stopped',17040)):
            bank=rt.GroupLocks([1,2],motion={1:label});p=module('MAIN','')
            bank.update(p._state,'LOCK_GROUP',3)
            self.assertEqual(bank.update(p._state,'UNLOCK_GROUP',3),code)
            self.assertEqual(bank.owners,{1:p._state})
            bank.set_motion(1,'idle');self.assertEqual(bank.update(p._state,'UNLOCK_GROUP',1),0)

    def test_invalid_mask_never_partially_mutates(self):
        bank=rt.GroupLocks([1,3]);p=module('MAIN','')
        for mask in (-1,2,3,8):
            self.assertEqual(bank.update(p._state,'LOCK_GROUP',mask),1);self.assertEqual(bank.owners,{})

    def test_pause_retains_and_completion_releases(self):
        bank=rt.GroupLocks([1]);p=module('MAIN','LOCK_GROUP(1,s) PAUSE n=2',context=rt.ExecutionContext(group_locks=bank))
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(bank.owners,{1:p._state});p.resume();self.assertEqual(bank.owners,{})

    def test_abort_stop_and_runtime_failure_release(self):
        for body,error in (('ABORT',rt.KarelAbort),('n=1 n=n DIV 0',rt.KarelRuntimeError),('PAUSE',rt.KarelPause)):
            bank=rt.GroupLocks([1],motion={1:'stopped'});p=module('MAIN','LOCK_GROUP(1,s) '+body,context=rt.ExecutionContext(group_locks=bank))
            with self.assertRaises(error):p.run()
            if body=='PAUSE':p.stop()
            self.assertEqual(bank.owners,{},body)

    def test_noncooperative_completion_and_error_release(self):
        for body in ('n=1','n=1 n=n DIV 0'):
            bank=rt.GroupLocks([1]);p=module('MAIN','LOCK_GROUP(1,s) '+body,context=rt.ExecutionContext(group_locks=bank),cooperative=False)
            if 'DIV' in body:
                with self.assertRaises(rt.KarelRuntimeError):p.run()
            else:p.run()
            self.assertEqual(bank.owners,{})

    def test_nested_call_reuses_root_owner_and_return_keeps_locks(self):
        bank=rt.GroupLocks([1]);ctx=rt.ExecutionContext(group_locks=bank)
        p=project("LOCK_GROUP(1,s) CALL_PROG('CHILD',e) PAUSE",'LOCK_GROUP(1,s)',context=ctx)
        p.run('MAIN');self.assertEqual(p.programs['CHILD'].snapshot()['S'],0)
        self.assertEqual(bank.owners,{1:p.programs['MAIN']._state})
        p.scheduler.continue_task('MAIN');p.scheduler.run();self.assertEqual(bank.owners,{})

    def test_scheduled_competitors_keep_root_identity(self):
        bank=rt.GroupLocks([1,2]);ctx=rt.ExecutionContext(group_locks=bank)
        p=translate_project({'a':source('A','LOCK_GROUP(1,s) PAUSE'),
            'b':source('B','LOCK_GROUP(3,s) PAUSE')}).instantiate(context=ctx)
        p.scheduler.start('A');p.scheduler.start('B');p.scheduler.run()
        self.assertEqual((p.programs['A'].snapshot()['S'],p.programs['B'].snapshot()['S']),(0,2))
        self.assertIs(bank.owners[1],p.programs['A']._state);self.assertIs(bank.owners[2],p.programs['B']._state)
        p.scheduler.stop('A');self.assertEqual(set(bank.owners),{2});p.scheduler.stop('B')

    def test_task_rename_preserves_lock_identity(self):
        bank=rt.GroupLocks([1]);ctx=rt.ExecutionContext(group_locks=bank)
        p=translate_project({'main':source('MAIN',"LOCK_GROUP(1,s) SET_TSK_NAME('MAIN','RENAMED',s) PAUSE UNLOCK_GROUP(1,s)")}).instantiate(context=ctx)
        p.run('MAIN');self.assertIs(bank.owners[1],p.programs['MAIN']._state)
        p.scheduler.continue_task('RENAMED');p.scheduler.run();self.assertEqual(bank.owners,{})

    def test_source_lock_directives_remain_metadata_only(self):
        bank=rt.GroupLocks([1]);p=module('MAIN','PAUSE',prefix='%LOCKGROUP=1',context=rt.ExecutionContext(group_locks=bank))
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(bank.owners,{});p.stop()

    def test_missing_service_is_not_discovered(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'group_locks'):run('LOCK_GROUP(1,s)')

    def test_json_roundtrip_retains_config_and_rejects_live_owners(self):
        ctx=rt.ExecutionContext(group_locks=rt.GroupLocks([1,3],motion={3:'stopped'}))
        config=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(config)
        self.assertEqual(restored.to_config(),config)
        p=module('MAIN','LOCK_GROUP(1,s) PAUSE',context=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        with self.assertRaisesRegex(ValueError,'live group ownership'):ctx.to_config()
        p.stop();self.assertEqual(ctx.to_config()['group_locks'],config['group_locks'])

    def test_invalid_configurations_reject(self):
        for groups in ([],[0],[32],[True],[1,1],'1'):
            with self.assertRaises(ValueError):rt.GroupLocks(groups)
        for config in ({'groups':[1],'owners':{}},{'groups':[1],'motion':{'01':'idle'}},
                {'groups':[1],'motion':{'2':'stopped'}},{'groups':[1],'motion':{'1':'unknown'}},{}):
            with self.assertRaises(ValueError):rt.GroupLocks.from_config(config)

    def test_status_for_guards_and_explicit_override(self):
        for call in ('LOCK_GROUP(1,n)','UNLOCK_GROUP(1,n)'):
            with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO '+call+' ENDFOR')
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
        self.assertEqual(run('LOCK_GROUP(7)',routines='ROUTINE LOCK_GROUP(x:INTEGER) BEGIN n=x END LOCK_GROUP')['N'],7)

    def test_status_assignment_and_snapshot_are_defensive(self):
        bank=rt.GroupLocks([1,3]);ctx=rt.ExecutionContext(group_locks=bank)
        p=module('MAIN','LOCK_GROUP(4,s) PAUSE',context=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        snapshot=bank.snapshot();snapshot['owners'].clear();snapshot['groups'].append(2)
        self.assertEqual(bank.snapshot()['owners'],{'3':'MAIN'});self.assertEqual(bank.groups,(1,3))
        p.stop()


if __name__=='__main__':unittest.main()
