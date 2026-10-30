"""Authored READ_KB cancellation, FILE identity, fairness and retained-job checks."""
import copy
import json
import unittest
from karel2py import runtime as rt,translate_project
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source
from tests.test_keyboard import context,WINDOW

DECL='f,g:FILE text:STRING[254] n,key,s,io,count,token,elapsed:INTEGER done,flag:BOOLEAN'
OPEN="OPEN FILE f('RW','KB:TPKB') "
INIT="text='old' n=77 key=88 s=99 "
READ="READ_KB(f,text,254,KC_DISPLAY,KC_ENTER_KEY,200,'',n,key,s)"
FINISH=' io=IO_STATUS(f) CLOSE FILE f done=TRUE'


def execute_cancel(*,events=None,statement=READ,opening=OPEN,extra='',action=None):
    if events is None:events=[dict(key='a'),dict(key='b'),dict(key='ENTER',at_ms=100)]
    ctx=context(events=events);calls=[]
    def sleeper(delay):
        calls.append(delay)
        if action is None:rt.cancel_file(p._state,p._state.values['F'])
        else:action(p,ctx)
    p,result=compile_program(extra+opening+INIT+statement+FINISH,decl=DECL,context=ctx,sleep=sleeper)
    values=p.run();return values,p,ctx,calls,result


def pending(ctx=None,*,body=None):
    ctx=context()if ctx is None else ctx
    body=OPEN+INIT+READ.replace('200,','-1,')+FINISH if body is None else body
    project=translate_project({'main':source('MAIN',body,decl=DECL)}).instantiate(context=ctx);project.scheduler.start('MAIN');p=project.programs['MAIN']
    for _ in range(80):
        project.scheduler.step()
        jobs=[job for job in ctx.keyboard._active.values()if job['operation']=='READ_KB']
        if jobs:return project,p,p._state.values['F'],jobs[0]
    raise AssertionError('READ_KB did not become active')


class ReadKbCancelTests(unittest.TestCase):
    def test_cancel_preserves_text_count_key_and_returns_status_six(self):
        v,p,ctx,calls,_=execute_cancel();self.assertEqual((v['TEXT'],v['N'],v['KEY'],v['S'],v['IO'],v['DONE']),('old',77,88,6,6,True));self.assertEqual(calls,[.01]);self.assertEqual(p.read_requests,())
        self.assertEqual(ctx.keyboard._active,{});self.assertEqual(ctx.keyboard.events[0]['key'],'ENTER');self.assertEqual(ctx.keyboard.history[-1]['outcome'],'cancelled')

    def test_cancellation_history_keeps_unpublished_editor_text(self):
        _,_,ctx,_,_=execute_cancel();row=ctx.keyboard.history[-1];self.assertEqual((row['operation'],row['data']),('READ_KB',dict(text='ab',term=0,status=6)))

    def test_initial_editor_value_is_separate_from_output_storage(self):
        v,_,ctx,_,_=execute_cancel(statement=READ.replace("200,'',","200,'seed',"));self.assertEqual(v['TEXT'],'old');self.assertEqual(ctx.keyboard.history[-1]['data']['text'],'seedab')

    def test_repeated_cancel_is_idempotent_without_new_request_ids(self):
        def action(p,ctx):
            number=ctx.keyboard.request_sequence;rt.cancel_file(p._state,p._state.values['F']);rt.cancel_file(p._state,p._state.values['F']);self.assertEqual(ctx.keyboard.request_sequence,number)
        v,_,ctx,_,_=execute_cancel(action=action);self.assertEqual(v['S'],6);self.assertEqual(len(ctx.keyboard.history),1)

    def test_cancel_at_timeout_boundary_takes_precedence(self):
        v,_,_,_,_=execute_cancel(statement=READ.replace('200,','10,'));self.assertEqual(v['S'],6)

    def test_clear_io_status_does_not_clear_pending_cancel_request(self):
        def action(p,ctx):rt.cancel_file(p._state,p._state.values['F']);p._state.values['F'].status=0
        v,_,_,_,_=execute_cancel(action=action);self.assertEqual((v['S'],v['IO']),(6,6))

    def test_prior_explicit_output_changes_are_not_rolled_back(self):
        def action(p,ctx):p._state.set('TEXT','changed');rt.cancel_file(p._state,p._state.values['F'])
        v,_,_,_,_=execute_cancel(action=action);self.assertEqual(v['TEXT'],'changed')

    def test_cancelled_edit_does_not_enter_completed_line_history(self):
        ctx=context(events=[dict(key='a'),dict(key='ENTER',at_ms=100)])
        def sleeper(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=compile_program(OPEN+INIT+READ,decl=DECL,context=ctx,sleep=sleeper);p.run();h=p._state.values['F'];self.assertEqual(ctx.keyboard._handles[h]['past'],[]);self.assertNotIn('_read_kb_job',ctx.keyboard._handles[h]);ctx.keyboard.close(h)

    def test_retry_uses_only_unconsumed_events(self):
        ctx=context(events=[dict(key='a'),dict(key='b'),dict(key='ENTER',at_ms=100)])
        def sleeper(_):
            if not ctx.keyboard.history:rt.cancel_file(p._state,p._state.values['F'])
        p,_=compile_program(OPEN+INIT+READ+' io=s '+READ+' CLOSE FILE f',decl=DECL,context=ctx,sleep=sleeper);v=p.run();self.assertEqual((v['IO'],v['S'],v['TEXT'],v['N']),(6,0,'',0));self.assertEqual([r['outcome']for r in ctx.keyboard.history],['cancelled','completed'])

    def test_idle_cancel_does_not_poison_future_read(self):
        ctx=context(keys=['a','ENTER']);p,_=compile_program(OPEN+'CANCEL FILE f '+READ+FINISH,decl=DECL,context=ctx);v=p.run();self.assertEqual((v['TEXT'],v['S'],v['IO']),('a',0,0))

    def test_completed_read_cancellation_is_an_idle_no_op(self):
        ctx=context(keys=['a','ENTER']);p,_=compile_program(OPEN+READ+' CANCEL FILE f'+FINISH,decl=DECL,context=ctx);v=p.run();self.assertEqual((v['TEXT'],v['N'],v['S'],v['IO']),('a',1,0,0))

    def test_close_remains_busy_until_cancelled_reader_unwinds(self):
        project,p,h,_=pending();rt.cancel_file(p._state,h)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'before closing'):project.context.keyboard.close(h)
        project.scheduler.run();self.assertIsNone(h.owner)

    def test_cancel_does_not_require_spare_history_sequence_capacity(self):
        project,p,h,_=pending();bank=project.context.keyboard;bank.sequence=2147483646;rt.cancel_file(p._state,h);project.scheduler.run();self.assertEqual(p.snapshot()['S'],6);self.assertEqual(bank._active,{})


class ReadKbSchedulingTests(unittest.TestCase):
    def test_global_handler_can_cancel_between_ready_keystrokes(self):
        ctx=context(keys=list('a'*100)+['ENTER']);body=OPEN+INIT+'elapsed=0 CONNECT TIMER TO elapsed CONDITION[1]: WHEN elapsed>=25 DO CANCEL FILE f ENDCONDITION ENABLE CONDITION[1] '+READ.replace('200,','-1,')+' DISCONNECT TIMER elapsed PURGE CONDITION[1]'+FINISH
        project=translate_project({'main':source('MAIN',body,decl=DECL)}).instantiate(context=ctx);project.run('MAIN');v=project.programs['MAIN'].snapshot();self.assertEqual((v['TEXT'],v['N'],v['KEY'],v['S']),('old',77,88,6));self.assertGreater(len(ctx.keyboard.events),1);self.assertEqual(ctx.keyboard.events[-1]['key'],'ENTER')

    def test_blocking_ready_input_honors_positive_deadline(self):
        ctx=context(keys=list('a'*100)+['ENTER']);body=OPEN+INIT+READ.replace('200,','5,')+FINISH
        project=translate_project({'main':source('MAIN',body,decl=DECL)}).instantiate(context=ctx);project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['S'],4);self.assertGreater(len(ctx.keyboard.events),1)

    def test_zero_time_poll_keeps_atomic_ready_input_behavior(self):
        ctx=context(keys=list('abc')+['ENTER']);project=translate_project({'main':source('MAIN',OPEN+INIT+READ.replace('200,','0,')+FINISH,decl=DECL)}).instantiate(context=ctx);project.run('MAIN');v=project.programs['MAIN'].snapshot();self.assertEqual((v['TEXT'],v['N'],v['S']),('abc',3,0))

    def test_ignored_keys_also_visit_blocking_checkpoints(self):
        ctx=context(keys=['F1']*100+['ENTER']);body=OPEN+INIT+'elapsed=0 CONNECT TIMER TO elapsed CONDITION[1]: WHEN elapsed>=25 DO CANCEL FILE f ENDCONDITION ENABLE CONDITION[1] '+READ.replace('200,','-1,')+' DISCONNECT TIMER elapsed'+FINISH
        project=translate_project({'main':source('MAIN',body,decl=DECL)}).instantiate(context=ctx);project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['S'],6);self.assertGreater(len(ctx.keyboard.events),1)

    def test_pause_retains_cancellation_without_resuming_task(self):
        project,p,h,_=pending();p.pause()
        for _ in range(60):
            project.scheduler.step()
            if p.task_state=='paused':break
        self.assertEqual(p.task_state,'paused');rt.cancel_file(p._state,h);self.assertEqual(p.task_state,'paused');self.assertEqual(p.snapshot()['S'],99)
        project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(p.snapshot()['S'],6)

    def test_stop_after_cancel_does_not_publish_source_outputs(self):
        project,p,h,_=pending();rt.cancel_file(p._state,h);project.scheduler.stop('MAIN');self.assertEqual((p.snapshot()['S'],p.snapshot()['TEXT'],p.task_state),(99,'old','stopped'));self.assertEqual(project.context.keyboard._active,{});project.context.keyboard.close(h)

    def test_abort_takes_precedence_over_pending_cancel(self):
        project,p,h,_=pending();rt.cancel_file(p._state,h);rt.request_task_control(p._state,'ABORT')
        with self.assertRaises(rt.KarelAbort):project.scheduler.run()
        self.assertEqual((p.snapshot()['TEXT'],p.snapshot()['S']),('old',99));project.context.keyboard.close(h)

    def test_budget_failure_releases_editor_without_output_publication(self):
        project,p,h,_=pending();p._state.max_steps=p._state.steps
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):project.scheduler.run()
        self.assertEqual(p.snapshot()['S'],99);self.assertEqual(project.context.keyboard._active,{});project.context.keyboard.close(h)

    def test_suspended_editor_can_be_cancelled_without_popping_token(self):
        project,p,h,job=pending();bank=project.context.keyboard
        bank.push_pop(p._state,'PUSH_KEY_RD',['TPKB',255,p._state.reference('TOKEN'),p._state.reference('IO')]);self.assertTrue(job['suspended']);rt.cancel_file(p._state,h);project.scheduler.run();self.assertEqual(p.snapshot()['S'],6);self.assertEqual(len(bank._frames),1)
        bank.push_pop(p._state,'POP_KEY_RD',['TPKB',p.snapshot()['TOKEN'],p._state.reference('IO')]);self.assertEqual(bank._frames,{});project.context.to_config()

    def test_linked_handler_cancels_exact_caller_file(self):
        ctx=context(events=[dict(key='ENTER',at_ms=100)])
        sources={'main':source('MAIN','flag=FALSE CONDITION[1]: WHEN flag DO cancel_input(f) ENDCONDITION ENABLE CONDITION[1] '+OPEN+INIT+READ+FINISH,decl=DECL,routines='ROUTINE cancel_input(h:FILE) FROM LIB'),
            'lib':source('LIB','',routines='ROUTINE cancel_input(h:FILE) BEGIN CANCEL FILE h END cancel_input')}
        def sleeper(_):project.programs['MAIN']._state.set('FLAG',True)
        project=translate_project(sources).instantiate(context=ctx,options={'sleep':sleeper});v=project.programs['MAIN'].run();self.assertEqual((v['S'],v['TEXT']),(6,'old'));self.assertEqual(project.programs['LIB']._state.local_frames,[])

    def test_overlapping_read_kb_returns_busy_without_replacing_owner(self):
        project,p,h,job=pending();bank=project.context.keyboard;args=[h,p._state.reference('TEXT'),254,1,8,0,'',p._state.reference('N'),p._state.reference('KEY'),p._state.reference('IO')]
        other=bank.read(p._state,args)
        with self.assertRaises(StopIteration):next(other)
        self.assertEqual(p.snapshot()['IO'],2);self.assertIs(bank._active[job['id']],job);rt.cancel_file(p._state,h);project.scheduler.run()

    def test_direct_typed_keyboard_generator_remains_separate(self):
        ctx=context(events=[dict(key='ENTER',at_ms=100)]);p,_=compile_program(OPEN,decl=DECL,context=ctx);p.run();h=p._state.values['F'];p._state._scheduler=rt.TaskScheduler()
        generator=ctx.keyboard.file_read(p._state,h,[p._state.reference('N')]);next(generator)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cooperative FILE registration'):rt.cancel_file(p._state,h)
        generator.close();ctx.keyboard.close(h)


class ReadKbIdentityTests(unittest.TestCase):
    def mutate_and_recover(self,change,restore):
        project,p,h,job=pending();bank=project.context.keyboard;before=len(bank.events);original=change(bank,h,job)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identity|registration'):rt.cancel_file(p._state,h)
        self.assertFalse(job['_cancel_requested']);self.assertEqual(len(bank.events),before);restore(bank,h,job,original);rt.cancel_file(p._state,h);project.scheduler.run();self.assertEqual(p.snapshot()['S'],6)

    def test_endpoint_change_is_rejected_before_mark(self):
        def change(bank,h,job):old=h.name;h.name='KB:OTHER';return old
        self.mutate_and_recover(change,lambda bank,h,job,old:setattr(h,'name',old))

    def test_attribute_type_change_is_rejected_before_mark(self):
        def change(bank,h,job):old=h.noecho;h.noecho=0;return old
        self.mutate_and_recover(change,lambda bank,h,job,old:setattr(h,'noecho',old))

    def test_binding_replacement_is_not_retargeted(self):
        def change(bank,h,job):old=bank._handles[h];bank._handles[h]=dict(old);return old
        self.mutate_and_recover(change,lambda bank,h,job,old:bank._handles.__setitem__(h,old))

    def test_pane_change_is_rejected(self):
        def change(bank,h,job):old=bank._handles[h]['pane'];bank._handles[h]['pane']=2;return old
        self.mutate_and_recover(change,lambda bank,h,job,old:bank._handles[h].__setitem__('pane',old))

    def test_history_binding_change_is_rejected(self):
        def change(bank,h,job):old=bank._handles[h]['past'];bank._handles[h]['past']=[];return old
        self.mutate_and_recover(change,lambda bank,h,job,old:bank._handles[h].__setitem__('past',old))

    def test_copied_file_cannot_cancel_registered_reader(self):
        project,p,h,job=pending();foreign=copy.copy(h)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'registration'):rt.cancel_file(p._state,foreign)
        self.assertFalse(job['_cancel_requested']);rt.cancel_file(p._state,h);project.scheduler.run()

    def test_lost_active_registration_cannot_be_hidden_by_idle_cancel(self):
        def change(bank,h,job):return bank._active.pop(job['id'])
        self.mutate_and_recover(change,lambda bank,h,job,old:bank._active.__setitem__(job['id'],old))

    def test_copied_active_registration_cannot_receive_original_cancel(self):
        def change(bank,h,job):old=bank._active[job['id']];bank._active[job['id']]=dict(old);return old
        self.mutate_and_recover(change,lambda bank,h,job,old:bank._active.__setitem__(job['id'],old))

    def test_foreign_active_entry_survives_failed_reader_cleanup(self):
        project,p,h,job=pending();bank=project.context.keyboard;foreign=dict(job);bank._active[job['id']]=foreign
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identity|registration'):project.scheduler.run()
        self.assertIs(bank._active[job['id']],foreign);self.assertNotIn('_read_kb_job',bank._handles[h]);bank._active.pop(job['id']);bank._domain=None;bank.close(h)

    def test_identity_change_after_cancel_still_fails_closed(self):
        project,p,h,job=pending();rt.cancel_file(p._state,h);original=h.name;h.name='KB:OTHER'
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identity|registration'):project.scheduler.run()
        self.assertEqual(p.snapshot()['S'],99);h.name=original;project.context.keyboard.close(h)

    def test_other_file_and_pane_are_not_cancelled(self):
        ctx=context(events=[dict(key='ENTER',at_ms=100)]);project,p,h,job=pending(ctx);g=p._state.values['G'];ctx.keyboard.open_for(p._state,g,'RW','KB:TPKB')
        rt.cancel_file(p._state,g);self.assertFalse(job['_cancel_requested']);ctx.keyboard.close(g);project.scheduler.run();self.assertEqual(p.snapshot()['S'],0)


class ReadKbWindowAndPersistenceTests(unittest.TestCase):
    def test_combined_window_cancel_closes_both_registered_handles(self):
        v,_,ctx,_,_=execute_cancel(extra=WINDOW,opening="OPEN FILE f('RW','WD:W1/TPKB') ");self.assertEqual(v['S'],6);self.assertEqual(ctx.keyboard._handles,{});self.assertEqual(ctx.pendant._handles,{})

    def test_noecho_cancel_preserves_untouched_surface(self):
        v,_,ctx,_,_=execute_cancel(extra=WINDOW+' SET_FILE_ATR(f,ATR_NOECHO) ',opening="OPEN FILE f('RW','WD:W1/TPKB') ");self.assertEqual(v['S'],6);self.assertTrue(all(not line.strip()for line in ctx.pendant.windows['W1']['lines']))

    def test_explicit_window_write_during_read_does_not_change_read_identity(self):
        def action(p,ctx):h=p._state.values['F'];h.owner.write(h,b'!');rt.cancel_file(p._state,h)
        v,_,_,_,_=execute_cancel(extra=WINDOW,opening="OPEN FILE f('RW','WD:W1/TPKB') ",action=action);self.assertEqual((v['S'],v['F']['position']),(6,1))

    def test_closed_cancelled_context_round_trips_without_private_tokens(self):
        _,_,ctx,_,_=execute_cancel();config=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config);self.assertNotIn('_read_kb_job',json.dumps(config))

    def test_pending_cancellation_still_prevents_context_save(self):
        project,p,h,_=pending();rt.cancel_file(p._state,h)
        with self.assertRaises(ValueError):project.context.to_config()
        project.scheduler.run();project.context.to_config()

    def test_fileless_menu_is_not_targeted_by_idle_file_cancel(self):
        ctx=context();p,_=compile_program(OPEN,decl=DECL,context=ctx);p.run();h=p._state.values['F'];job=ctx.keyboard.start(p._state,'DISCTRL_ALPH',1,255)
        rt.cancel_file(p._state,h);self.assertIs(ctx.keyboard._active[job['id']],job);ctx.keyboard.end(job);ctx.keyboard.close(h)

    def test_parameter_and_output_selectors_are_captured_once(self):
        ctx=context(events=[dict(key='ENTER',at_ms=100)])
        def sleeper(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=compile_program(OPEN+INIT+'count=0 READ_KB(f,text,width(),KC_DISPLAY,KC_ENTER_KEY,200,initial(),n,key,s)'+FINISH,decl=DECL,context=ctx,sleep=sleeper,routines="ROUTINE width:INTEGER BEGIN count=count+1 RETURN 254 END width ROUTINE initial:STRING BEGIN count=count+10 RETURN 'seed' END initial")
        self.assertEqual((p.run()['COUNT'],p.snapshot()['TEXT'],p.snapshot()['S']),(11,'old',6))


class ReadKbAttributeDomainTests(unittest.TestCase):
    def test_invalid_cursor_is_not_hidden_by_cancellation(self):
        project,p,h,job=pending();h.position=-1
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identity|registration'):rt.cancel_file(p._state,h)
        self.assertFalse(job['_cancel_requested']);h.position=0;rt.cancel_file(p._state,h);project.scheduler.run()

    def test_malformed_preexisting_attribute_fails_before_key_consumption(self):
        ctx=context(keys=['ENTER']);p,_=compile_program(OPEN,decl=DECL,context=ctx);p.run();h=p._state.values['F'];h.noecho=0
        args=[h,p._state.reference('TEXT'),254,1,8,0,'',p._state.reference('N'),p._state.reference('KEY'),p._state.reference('S')]
        generator=ctx.keyboard.read(p._state,args)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identity|registration'):next(generator)
        self.assertEqual(ctx.keyboard.events[0]['key'],'ENTER');self.assertEqual(ctx.keyboard._active,{});h.noecho=False;ctx.keyboard.close(h)


if __name__=='__main__':unittest.main()
