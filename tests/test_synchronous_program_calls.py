"""Private synchronous source entries preserve caller ownership and lifecycle."""
from copy import deepcopy
import json
import unittest

from karel2py import translate,runtime as rt
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_program_calls import module


def attached(child='n=3',main="CALL_PROG('CHILD',e)",*,decl='n,e,s:INTEGER',prefix=''):
    ctx=rt.ExecutionContext();target=module('CHILD',child,context=ctx,cooperative=False,decl=decl,prefix=prefix)
    caller=module('MAIN',main,context=ctx)
    return caller,target,ctx


class SynchronousProgramCallTests(unittest.TestCase):
    def test_default_source_has_private_body_and_standalone_run(self):
        p=module('CHILD','n=3',cooperative=False)
        self.assertTrue(callable(p._execute_sync));self.assertFalse(hasattr(p,'_execute'))
        self.assertEqual(p.run()['N'],3);self.assertFalse(p._state._driving)

    def test_same_task_call_executes_plain_attached_source(self):
        caller,target,ctx=attached();caller.run()
        self.assertEqual((target.snapshot()['N'],caller.snapshot()['E']),(3,1))
        self.assertFalse(target._state._driving);self.assertEqual(ctx.program_entries,{'CHILD':1})

    def test_repeated_calls_share_globals_and_use_stable_hint(self):
        caller,target,_=attached('IF UNINIT(n) THEN n=0 ENDIF n=n+1',"CALL_PROG('CHILD',e) CALL_PROG('CHILD',s)")
        caller.run();self.assertEqual((target.snapshot()['N'],caller.snapshot()['E'],caller.snapshot()['S']),(2,1,1))

    def test_body_does_not_reset_prototype_steps_or_drive_flag(self):
        caller,target,_=attached();target._state.steps=17;target._state.max_steps=42
        caller.run();self.assertEqual((target._state.steps,target._state.max_steps,target._state._driving),(17,42,False))

    def test_prior_standalone_run_and_later_call_share_original_storage(self):
        caller,target,_=attached('IF UNINIT(n) THEN n=0 ENDIF n=n+1');target.run();storage=target._state.values
        caller.run();self.assertIs(target._state.values,storage);self.assertEqual(target.snapshot()['N'],2)

    def test_caller_budget_is_not_reset_by_sync_entry(self):
        caller,target,_=attached('n=0 WHILE TRUE DO n=n+1 ENDWHILE',"n=7 CALL_PROG('CHILD',e) n=99")
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):caller.run(max_steps=20)
        self.assertEqual((caller.snapshot()['N'],caller.snapshot()['E']),(7,1));self.assertGreater(target.snapshot()['N'],0)
        self.assertEqual(caller._state._task_frames,[]);self.assertEqual(target._state.local_frames,[])

    def test_body_failure_retains_hint_and_completed_source_effects(self):
        caller,target,_=attached('n=7 s=1 DIV 0',"n=3 CALL_PROG('CHILD',e) n=99")
        with self.assertRaises(rt.KarelRuntimeError):caller.run()
        self.assertEqual((caller.snapshot()['N'],caller.snapshot()['E'],target.snapshot()['N']),(3,1,7))
        self.assertEqual(caller._state._task_frames,[])

    def test_pause_on_entry_defers_plain_body_and_resumes_once(self):
        caller,target,_=attached('IF UNINIT(n) THEN n=0 ENDIF n=n+1',"CALL_PROGLIN('CHILD',42,e,TRUE) n=8")
        with self.assertRaises(rt.KarelPause):caller.run()
        self.assertEqual((caller.snapshot()['E'],target.snapshot()['N']),(1,{'uninitialized':True}))
        self.assertEqual(caller.resume()['N'],8);self.assertEqual(target.snapshot()['N'],1)

    def test_stop_while_paused_before_entry_does_not_run_target(self):
        caller,target,_=attached(main="CALL_PROGLIN('CHILD',0,e,TRUE)")
        with self.assertRaises(rt.KarelPause):caller.run()
        caller.stop();self.assertEqual(target.snapshot()['N'],{'uninitialized':True});self.assertEqual(caller._state._task_frames,[])

    def test_sync_body_uses_caller_write_adapter_and_observations(self):
        caller,target,_=attached("n=3 WRITE('hello')");seen=[]
        caller._state._write=seen.append;target._state._write=lambda text:self.fail('Prototype write adapter was used')
        caller.run();self.assertEqual(seen,['hello']);self.assertEqual(caller.write_requests[0]['text'],'hello')
        self.assertEqual(target.write_requests,())

    def test_sync_body_uses_caller_read_adapter(self):
        caller,target,_=attached('READ(n)');caller._state._read=lambda request:[7]
        caller.run();self.assertEqual(target.snapshot()['N'],7);self.assertEqual(len(caller.read_requests),1)

    def test_source_delay_uses_inherited_explicit_sleeper(self):
        caller,target,_=attached('DELAY(2) n=3');delays=[]
        caller._state._sleep=delays.append;caller._state._sleep_injected=True
        caller.run();self.assertEqual((delays,target.snapshot()['N']),([.002],3))

    def test_injected_callback_pause_is_a_failure_with_no_false_resume(self):
        caller,target,_=attached('n=3 READ(s) n=99')
        def reader(request):raise rt.KarelPause()
        caller._state._read=reader
        # READ validates callback exceptions as an input error; direct injected
        # pauses from WRITE also cannot create a resumable synchronous frame.
        with self.assertRaises(rt.KarelRuntimeError):caller.run()
        self.assertEqual(target.snapshot()['N'],3);self.assertEqual(caller._state._task_frames,[])

    def test_direct_write_callback_pause_is_rejected_explicitly(self):
        caller,target,_=attached("n=3 WRITE('pause') n=99")
        def writer(text):raise rt.KarelPause()
        caller._state._write=writer
        with self.assertRaises(rt.KarelRuntimeError):caller.run()
        self.assertEqual(target.snapshot()['N'],3);self.assertEqual(caller._state._task_frames,[])

    def test_swallowed_root_abort_remains_sticky_at_return(self):
        caller,target,_=attached("n=3 WRITE('abort')",main="CALL_PROG('CHILD',e) n=99")
        def writer(text):
            try:caller._state.abort(99)
            except rt.KarelAbort:pass
        caller._state._write=writer
        with self.assertRaises(rt.KarelAbort):caller.run()
        self.assertEqual(target.snapshot()['N'],3);self.assertEqual(caller.snapshot()['N'],{'uninitialized':True})
        self.assertEqual(caller._state._task_frames,[])
        with self.assertRaises(rt.KarelAbort):caller.run()

    def test_invalid_target_or_negative_line_preserves_hint(self):
        for call in ("CALL_PROG('MISSING',e)","CALL_PROG('bad.name',e)","CALL_PROGLIN('CHILD',-1,e,FALSE)"):
            caller,target,ctx=attached(main='e=77 '+call)
            with self.subTest(call=call),self.assertRaises(rt.KarelRuntimeError):caller.run()
            self.assertEqual(caller.snapshot()['E'],77);self.assertFalse(ctx.program_entries)

    def test_older_generated_normal_target_requires_retranslation(self):
        caller,target,ctx=attached(main="e=77 CALL_PROG('CHILD',e)");delattr(type(target),'_execute_sync')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'callable KAREL'):caller.run()
        self.assertEqual(caller.snapshot()['E'],77);self.assertFalse(ctx.program_entries)

    def test_legacy_target_does_not_gain_sync_private_entry(self):
        ctx=rt.ExecutionContext();ns={};exec(legacy_translate('PROGRAM CHILD VAR n:INTEGER BEGIN n=3 END CHILD').python_source,ns)
        target=ns['Program'](context=ctx);caller=module('MAIN',"e=77 CALL_PROG('CHILD',e)",context=ctx)
        self.assertFalse(hasattr(target,'_execute_sync'))
        with self.assertRaises(rt.KarelRuntimeError):caller.run()
        self.assertEqual(caller.snapshot()['E'],77)

    def test_source_routine_frames_are_fresh_with_shared_globals(self):
        ctx=rt.ExecutionContext();target=module('CHILD','n=work()',context=ctx,cooperative=False,
            routines='ROUTINE work:INTEGER VAR scratch:INTEGER BEGIN scratch=7 RETURN scratch END work')
        caller=module('MAIN',"CALL_PROG('CHILD',e)",context=ctx);caller.run()
        self.assertEqual(target.snapshot()['N'],7);self.assertEqual(target._state.local_frames,[])

    def test_nested_plain_targets_share_one_callers_scope(self):
        # An ordinary middle module with CALL_PROG becomes cooperative by source
        # policy; its nested simple leaf still follows the synchronous entry.
        ctx=rt.ExecutionContext();leaf=module('LEAF','n=7',context=ctx,cooperative=False)
        middle=module('MIDDLE',"CALL_PROG('LEAF',e)",context=ctx)
        caller=module('MAIN',"CALL_PROG('MIDDLE',e)",context=ctx);caller.run()
        self.assertEqual((leaf.snapshot()['N'],middle.snapshot()['E'],caller.snapshot()['E']),(7,2,1))
        self.assertEqual(caller._state._task_frames,[])

    def test_context_roundtrip_requires_reattachment_and_keeps_values(self):
        caller,target,ctx=attached('IF UNINIT(n) THEN n=0 ENDIF n=n+1');caller.run()
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        target=module('CHILD','IF UNINIT(n) THEN n=0 ENDIF n=n+1',context=restored,cooperative=False)
        caller=module('MAIN',"CALL_PROG('CHILD',e)",context=restored);caller.run()
        self.assertEqual(target.snapshot()['N'],2);self.assertEqual(restored.program_entries,{'CHILD':1})

    def test_report_describes_atomic_sync_body_and_cooperative_optin(self):
        result=translate('PROGRAM CHILD VAR n:INTEGER BEGIN n=3 END CHILD')
        self.assertFalse(result.report['cooperative_execution']);self.assertIn('def _execute_sync',result.python_source)
        self.assertIn('without scheduler yields',result.report['synchronous_program_call_policy']['execution'])


if __name__=='__main__':unittest.main()
