"""Authored semaphore, lifecycle, posted-error and failure notification checks."""
import json
import unittest

from karel2py import translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


def context(count=2,values=None): return rt.ExecutionContext(semaphores=rt.SemaphoreBank(count,values))


class SemaphoreTests(unittest.TestCase):
    def test_post_clear_count_and_signal(self):
        ctx=context();state=run('POST_SEMA(1) SIGNAL SEMAPHORE[1] n=SEMA_COUNT(1) CLEAR_SEMA(1) s=SEMA_COUNT(1)',context=ctx)
        self.assertEqual((state['N'],state['S']),(2,0))

    def test_immediate_wait_consumes_one(self):
        ctx=context(values={1:2});state=run('PEND_SEMA(1,0,timeout) n=SEMA_COUNT(1)',decl='timeout: BOOLEAN n: INTEGER',context=ctx)
        self.assertEqual(state,{'TIMEOUT':False,'N':1})

    def test_zero_timeout_preserves_count(self):
        ctx=context();state=run('PEND_SEMA(1,0,timeout) n=SEMA_COUNT(1)',decl='timeout: BOOLEAN n: INTEGER',context=ctx)
        self.assertEqual(state,{'TIMEOUT':True,'N':0});self.assertEqual(ctx.semaphores.tickets,[])

    def test_wait_uses_virtual_deadline(self):
        instance=translate_project({'a':source('MAIN','PEND_SEMA(1,5,timeout)',decl='timeout: BOOLEAN')}).instantiate(context=context())
        self.assertTrue(instance.run('MAIN')['MAIN']['values']['TIMEOUT']);self.assertGreaterEqual(instance.scheduler.now_us,5000)

    def test_tasks_exchange_semaphore(self):
        instance=translate_project({'a':source('MAIN',"RUN_TASK('CHILD',0,FALSE,FALSE,0,s) PEND_SEMA(1,-1,timeout) n=7",decl='timeout: BOOLEAN n,s: INTEGER'),
            'b':source('CHILD','DELAY 5 POST_SEMA(1)')}).instantiate(context=context())
        result=instance.run('MAIN');self.assertEqual((result['MAIN']['values']['TIMEOUT'],result['MAIN']['values']['N']),(False,7))
        self.assertEqual(instance.context.semaphores.value(1),0)

    def test_negative_count_pending_waiters_and_fifo(self):
        bank=rt.SemaphoreBank(1);first=bank.request(1);second=bank.request(1)
        self.assertEqual(bank.value(1),-2);bank.post(1);self.assertTrue(first['granted']);self.assertFalse(second['granted'])
        bank.finish(first);bank.release(first);self.assertEqual(bank.value(1),-1)
        bank.post(1);bank.finish(second);bank.release(second);self.assertEqual(bank.value(1),0)

    def test_cancel_second_waiter_keeps_first_identity(self):
        bank=rt.SemaphoreBank(1);first=bank.request(1);second=bank.request(1)
        bank.release(second);bank.post(1);self.assertTrue(first['granted']);self.assertFalse(second['granted']);bank.release(first)
        self.assertEqual(bank.value(1),1)

    def test_cancel_granted_wait_refunds_token(self):
        bank=rt.SemaphoreBank(1);first=bank.request(1);second=bank.request(1)
        bank.post(1);bank.release(first);self.assertTrue(second['granted']);bank.finish(second);bank.release(second)
        self.assertEqual(bank.value(1),0)

    def test_clear_preserves_waiters(self):
        bank=rt.SemaphoreBank(1);ticket=bank.request(1);bank.clear(1)
        self.assertEqual(bank.value(1),-1);bank.post(1);self.assertTrue(ticket['granted']);bank.release(ticket)

    def test_stop_waiter_removes_ticket(self):
        ctx=context();p,_=compile_program('PEND_SEMA(1,-1,timeout)',decl='timeout: BOOLEAN',context=ctx)
        scheduler=rt.TaskScheduler();scheduler.bind('main',p);scheduler.start('main')
        for _ in range(4): scheduler.step()
        self.assertEqual(ctx.semaphores.value(1),-1);scheduler.stop('main')
        self.assertEqual((ctx.semaphores.value(1),ctx.semaphores.tickets),(0,[]))
        self.assertEqual(p.service_requests[-1]['outcome'],'cancelled')

    def test_semaphore_condition_does_not_consume(self):
        ctx=context();state=run('n=0 CONDITION[1]: WHEN SEMAPHORE[1] DO n=7 ENDCONDITION ENABLE CONDITION[1] POST_SEMA(1) s=SEMA_COUNT(1)',context=ctx)
        self.assertEqual((state['N'],state['S']),(7,1))

    def test_standalone_wait_callback_can_post(self):
        ctx=context();p,_=compile_program('PEND_SEMA(1,-1,timeout)',decl='timeout: BOOLEAN',context=ctx,sleep=lambda seconds:ctx.semaphores.post(1))
        self.assertFalse(p.run()['TIMEOUT'])

    def test_persistence_and_active_wait_guard(self):
        ctx=context(values={1:4});restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertEqual(restored.semaphores.value(1),4)
        ticket=ctx.semaphores.request(2)
        with self.assertRaisesRegex(ValueError,'outstanding'): ctx.to_config()
        ctx.semaphores.release(ticket)

    def test_missing_and_invalid_bank(self):
        p,_=compile_program('POST_SEMA(1)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit'): p.run()
        for count,values in ((0,{}),(True,{}),(1,{2:0}),(1,{1:-1}),(1,{1:True})):
            with self.subTest(count=count,values=values),self.assertRaises((ValueError,rt.KarelRuntimeError)): rt.SemaphoreBank(count,values)

    def test_bad_duration_or_output_preserves_state(self):
        ctx=context(values={1:1});p,_=compile_program('timeout=TRUE PEND_SEMA(1,-2,timeout)',decl='timeout: BOOLEAN',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['TIMEOUT'],ctx.semaphores.value(1)),(True,1))
        with self.assertRaises(TranslationError): compile_program('PEND_SEMA(1,0,n)')

    def test_overflow_preserves_counter(self):
        bank=rt.SemaphoreBank(1,{1:2147483646})
        with self.assertRaises(rt.KarelRuntimeError): bank.post(1)
        self.assertEqual(bank.value(1),2147483646)

    def test_invalid_persistent_keys_and_fields(self):
        for config in ({'count':1,'values':{'01':0}},{'count':1,'values':None},{'count':1,'other':0}):
            with self.subTest(config=config),self.assertRaises(ValueError): rt.SemaphoreBank.from_config(config)

    def test_pause_then_stop_releases_wait(self):
        ctx=context();p,_=compile_program('PEND_SEMA(1,-1,timeout)',decl='timeout: BOOLEAN',context=ctx)
        scheduler=rt.TaskScheduler();scheduler.bind('main',p);scheduler.start('main')
        for _ in range(4): scheduler.step()
        p.pause();self.assertEqual(scheduler.run()['MAIN']['state'],'paused')
        scheduler.stop('main');self.assertEqual(ctx.semaphores.tickets,[])


class ErrorNotificationTests(unittest.TestCase):
    def test_warning_specific_and_wildcard_conditions(self):
        p,result=compile_program("n=0 s=0 CONDITION[1]: WHEN ERROR[15018] DO n=7 ENDCONDITION CONDITION[2]: WHEN ERROR[*] DO s=9 ENDCONDITION ENABLE CONDITION[1] ENABLE CONDITION[2] POST_ERR(15018,'part',0,0)")
        self.assertEqual((p.run()['N'],p.snapshot()['S']),(7,9));self.assertTrue(result.report['cooperative_execution'])
        record=p._state.execution.errors.snapshot()[0];self.assertEqual((record['code'],record['parameter'],record['origin']),(15018,'part','posted'))

    def test_unrelated_error_does_not_trigger(self):
        self.assertEqual(run("n=0 CONDITION[1]: WHEN ERROR[12] DO n=7 ENDCONDITION ENABLE CONDITION[1] POST_ERR(13,'',0,0)")['N'],0)

    def test_nopause_cancels_pending_pause(self):
        self.assertEqual(run('n=1 CONDITION[1]: WHEN PAUSE DO NOPAUSE,n=7 ENDCONDITION ENABLE CONDITION[1] PAUSE s=n')['S'],7)

    def test_noabort_cancels_pending_abort(self):
        p,_=compile_program('n=1 CONDITION[1]: WHEN ABORT DO NOABORT,n=7 ENDCONDITION ENABLE CONDITION[1] ABORT s=n')
        self.assertEqual(p.run()['S'],7);self.assertIsNone(p.abort_info)

    def test_error_action_suppresses_message_and_pause(self):
        p,_=compile_program("CONDITION[1]: WHEN ERROR[*] DO NOMESSAGE,NOPAUSE,n=7 ENDCONDITION ENABLE CONDITION[1] POST_ERR(12,'part',0,1) s=n")
        self.assertEqual(p.run()['S'],7);self.assertTrue(p._state.execution.errors.snapshot()[0]['suppressed'])

    def test_error_noabort_and_source_continues(self):
        self.assertEqual(run("CONDITION[1]: WHEN ERROR[*] DO NOABORT ENDCONDITION ENABLE CONDITION[1] POST_ERR(12,'',0,2) n=7")['N'],7)

    def test_posted_pause_and_resume(self):
        p,_=compile_program("n=1 POST_ERR(12,'',0,1) n=2")
        with self.assertRaises(rt.KarelPause): p.run()
        self.assertEqual(p.snapshot()['N'],1);self.assertEqual(p.resume()['N'],2)

    def test_posted_abort_is_sticky(self):
        p,_=compile_program("n=1 POST_ERR(12,'',0,2) n=2")
        with self.assertRaises(rt.KarelAbort): p.run()
        self.assertEqual(p.snapshot()['N'],1)
        with self.assertRaises(rt.KarelAbort): p.run()

    def test_runtime_failure_notifies_and_preserves_failure(self):
        p,_=compile_program('n=1 s=0 CONDITION[1]: WHEN ERROR[*] DO NOABORT,NOMESSAGE,n=7 ENDCONDITION ENABLE CONDITION[1] s=1 DIV s n=9')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'zero'): p.run()
        self.assertEqual(p.snapshot()['N'],7);record=p._state.execution.errors.snapshot()[0]
        self.assertEqual((record['code'],record['origin'],record['suppressed']),(1,'runtime',True))

    def test_error_handler_failure_retains_original(self):
        p,_=compile_program('s=0 CONDITION[1]: WHEN ERROR[*] DO n=2 DIV s ENDCONDITION ENABLE CONDITION[1] n=1 DIV s')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'zero') as caught: p.run()
        self.assertIn('Error handler failed',caught.exception.__notes__[0])

    def test_runtime_failure_keeps_budget_bound(self):
        p,_=compile_program('CONDITION[1]: WHEN ERROR[*] DO n=7 ENDCONDITION ENABLE CONDITION[1] WHILE TRUE DO ENDWHILE')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'): p.run(max_steps=20)
        self.assertEqual(p._state.execution.errors.snapshot()[0]['origin'],'runtime')

    def test_action_eval_captures_at_definition(self):
        self.assertEqual(run('n=1 CONDITION[1]: WHEN EVENT[1] DO s=EVAL(n+2) ENDCONDITION ENABLE CONDITION[1] n=7 SIGNAL EVENT[1]')['S'],3)

    def test_handler_actions_rejected_outside_handler(self):
        for action in ('NOABORT','NOPAUSE','NOMESSAGE'):
            with self.subTest(action=action),self.assertRaises(TranslationError) as caught: compile_program(action)
            self.assertEqual(caught.exception.code,'E_CONDITION_ACTION')

    def test_error_history_bound_copy_and_persistence(self):
        errors=rt.ErrorHistory(limit=2)
        for code in (10,11,12): errors.post(code)
        copy=errors.snapshot();copy[0]['code']=99
        self.assertEqual([row['code'] for row in errors.snapshot()],[11,12])
        ctx=rt.ExecutionContext(errors=errors);restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertEqual(restored.errors.snapshot(),errors.snapshot());self.assertEqual(restored.errors.post(13)['sequence'],4)

    def test_invalid_post_preserves_history(self):
        for code,cause,severity in ((-1,0,0),(1,-1,0),(1,0,3)):
            with self.subTest(code=code,cause=cause,severity=severity):
                ctx=rt.ExecutionContext(errors=rt.ErrorHistory());p,_=compile_program(f"POST_ERR({code},'',{cause},{severity})",context=ctx)
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual([row['origin'] for row in ctx.errors.snapshot()],['runtime'])

    def test_unicode_failure_message_preserves_original(self):
        def broken(request): raise ValueError('host \u00fc failure')
        p,_=compile_program('n=0 CONDITION[1]: WHEN ERROR[*] DO n=7 ENDCONDITION ENABLE CONDITION[1] READ(s)',read=broken)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'host'): p.run()
        self.assertEqual(p.snapshot()['N'],7);self.assertTrue(p._state.execution.errors.snapshot()[0]['parameter'].isascii())

    def test_host_error_program_scope(self):
        errors=rt.ErrorHistory();errors.post(17,program='CHILD')
        body='n=0 CONDITION[1]: WHEN ERROR[*] DO n=7 ENDCONDITION ENABLE CONDITION[1] s=n'
        instance=translate_project({'a':source('MAIN',body),'b':source('CHILD',body)}).instantiate(context=rt.ExecutionContext(errors=errors))
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['N'],0)
        self.assertEqual(instance.run('CHILD')['CHILD']['values']['N'],7)


class LifecycleAndLinkedControlTests(unittest.TestCase):
    def test_powerup_is_explicit_recovery(self):
        p,_=compile_program('n=0 CONDITION[1]: WHEN POWERUP DO n=n+1 ENDCONDITION ENABLE CONDITION[1] PAUSE s=n')
        with self.assertRaises(rt.KarelPause): p.run()
        self.assertEqual(p.snapshot()['N'],0);self.assertEqual(p.powerup()['S'],1)

    def test_normal_continue_does_not_signal_powerup(self):
        p,_=compile_program('n=0 CONDITION[1]: WHEN POWERUP DO n=7 ENDCONDITION ENABLE CONDITION[1] PAUSE s=n')
        with self.assertRaises(rt.KarelPause): p.run()
        self.assertEqual(p.resume()['S'],0)

    def test_scheduler_powerup(self):
        instance=translate_project({'a':source('MAIN','n=0 CONDITION[1]: WHEN POWERUP DO n=7 ENDCONDITION ENABLE CONDITION[1] PAUSE s=n')}).instantiate()
        self.assertEqual(instance.run('MAIN')['MAIN']['state'],'paused');instance.scheduler.powerup('MAIN')
        self.assertEqual(instance.scheduler.run()['MAIN']['values']['S'],7)

    def test_powerup_requires_pause(self):
        p,_=compile_program('n=7',cooperative=True)
        with self.assertRaises(rt.KarelRuntimeError): p.powerup()

    def test_powerup_after_final_pause_scans_before_completion(self):
        p,_=compile_program('n=0 CONDITION[1]: WHEN POWERUP DO n=7 ENDCONDITION ENABLE CONDITION[1] PAUSE')
        with self.assertRaises(rt.KarelPause): p.run()
        self.assertEqual(p.powerup()['N'],7)

    def test_continue_after_final_pause_scans_before_completion(self):
        p,_=compile_program('n=0 CONDITION[1]: WHEN CONTINUE DO n=7 ENDCONDITION ENABLE CONDITION[1] PAUSE')
        with self.assertRaises(rt.KarelPause): p.run()
        self.assertEqual(p.resume()['N'],7)

    def test_caller_noabort_cancels_abort_inside_library(self):
        instance=translate_project({'a':source('LIB','',routines='ROUTINE halt BEGIN ABORT END halt'),'b':source('MAIN','CONDITION[1]: WHEN ABORT DO NOABORT ENDCONDITION ENABLE CONDITION[1] halt() n=7',routines='ROUTINE halt FROM LIB')}).instantiate()
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['N'],7)

    def test_caller_nopause_cancels_library_pause(self):
        instance=translate_project({'a':source('LIB','',routines='ROUTINE wait_here BEGIN PAUSE END wait_here'),'b':source('MAIN','CONDITION[1]: WHEN PAUSE DO NOPAUSE ENDCONDITION ENABLE CONDITION[1] wait_here() n=7',routines='ROUTINE wait_here FROM LIB')}).instantiate()
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['N'],7)

    def test_global_post_pause_targets_active_tasks(self):
        instance=translate_project({'a':source('MAIN',"RUN_TASK('CHILD',0,FALSE,FALSE,0,s) DELAY 10 POST_ERR(12,'',0,1) n=7"),'b':source('CHILD','DELAY 100 n=9')}).instantiate()
        result=instance.run('MAIN');self.assertEqual((result['MAIN']['state'],result['CHILD']['state']),('paused','paused'))
        for name in ('MAIN','CHILD'): instance.scheduler.continue_task(name)
        result=instance.scheduler.run();self.assertEqual((result['MAIN']['values']['N'],result['CHILD']['values']['N']),(7,9))

    def test_global_abort_removes_other_pending_wait(self):
        instance=translate_project({'a':source('MAIN',"RUN_TASK('CHILD',0,FALSE,FALSE,0,s) DELAY 10 POST_ERR(12,'',0,2)"),
            'b':source('CHILD','PEND_SEMA(1,-1,timeout)',decl='timeout: BOOLEAN')}).instantiate(context=context())
        with self.assertRaises(rt.KarelAbort): instance.run('MAIN')
        with self.assertRaises(rt.KarelAbort): instance.scheduler.run()
        self.assertEqual(instance.context.semaphores.tickets,[]);self.assertEqual(instance.programs['CHILD'].task_state,'aborted')


if __name__=='__main__': unittest.main()
