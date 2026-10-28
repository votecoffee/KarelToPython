"""Authored opt-in serial waits, explicit EOF and captured atomic READs."""
import json
import struct
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


DECL='f:FILE n,m,count:INTEGER text:STRING[16] a:ARRAY[2]OF INTEGER'
OPEN="OPEN FILE f('RO','P2:') "
U={'uninitialized':True}


def streams(data=b'',*,final=False,capacity=1024):
    bank=rt.SerialStreams({2:{'capacity':capacity,'input':data,'wait':True,'final':final}},limit=max(4096,capacity))
    return bank,rt.ExecutionContext(serial_streams=bank)


def pending_project(bank,body=OPEN+'n=77 READ f(n,CR) CLOSE FILE f',decl=DECL):
    project=translate_project({'main':source('MAIN',body,decl=decl)}).instantiate(context=rt.ExecutionContext(serial_streams=bank))
    project.scheduler.start('MAIN')
    for _ in range(50):
        project.scheduler.step()
        if bank._pending:return project
    raise AssertionError('Serial READ did not wait')


class SerialWaitInputTests(unittest.TestCase):
    def test_fragmented_numeric_token_waits_for_delimiter(self):
        bank,ctx=streams();chunks=[b'1',b'7',b'\n'];calls=[]
        def sleeper(delay):
            calls.append(delay);self.assertEqual(task.snapshot()['N'],77)
            self.assertEqual(task.snapshot()['F']['position'],0);self.assertEqual(task.read_requests,())
            bank.feed(2,chunks.pop(0))
        task,_=compile_program(OPEN+'n=77 READ f(n,CR) CLOSE FILE f',decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual(task.run()['N'],17);self.assertEqual(calls,[.01]*3)
        self.assertEqual(len(task.read_requests),1);self.assertEqual(bank.snapshot()[2]['input'],b'')
        self.assertEqual(bank._pending,{})

    def test_multiple_fields_publish_only_complete_read(self):
        bank,ctx=streams(b'17 ');calls=[]
        def sleeper(delay):
            calls.append(delay);self.assertEqual((task.snapshot()['N'],task.snapshot()['M']),(77,88))
            bank.feed(2,b'29\n')
        task,_=compile_program(OPEN+'n=77 m=88 READ f(n,m,CR) CLOSE FILE f',decl=DECL,context=ctx,sleep=sleeper)
        result=task.run();self.assertEqual((result['N'],result['M'],calls),(17,29,[.01]))

    def test_unformatted_string_waits_for_complete_record(self):
        bank,ctx=streams(b'ab');calls=[]
        def sleeper(delay):calls.append(delay);bank.feed(2,b'cd\n')
        result=run(OPEN+'READ f(text,CR) CLOSE FILE f',decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual((result['TEXT'],calls),('abcd',[.01]))

    def test_fixed_width_can_finish_without_delimiter(self):
        bank,ctx=streams(b'123')
        self.assertEqual(run(OPEN+'READ f(n::3) CLOSE FILE f',decl=DECL,context=ctx)['N'],123)
        self.assertEqual(bank._pending,{})

    def test_fixed_width_with_cr_waits_for_record_boundary(self):
        bank,ctx=streams(b'abc');calls=[]
        def sleeper(delay):calls.append(delay);bank.feed(2,b'\n')
        result=run(OPEN+'READ f(text::3,CR) CLOSE FILE f',decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual((result['TEXT'],calls),('abc',[.01]))

    def test_cr_only_read_waits_and_consumes_exact_record(self):
        bank,ctx=streams();calls=[]
        def sleeper(delay):calls.append(delay);bank.feed(2,b'ignored\n')
        result=run(OPEN+'READ f(CR) CLOSE FILE f',decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual(calls,[.01]);self.assertEqual(bank.snapshot()[2]['input'],b'')
        self.assertEqual(result['F']['position'],0)

    def test_quoted_string_waits_until_closing_quote(self):
        bank,ctx=streams(b"'al");calls=[]
        def sleeper(delay):calls.append(delay);bank.feed(2,b"pha'")
        result=run(OPEN+'READ f(text::0::2) CLOSE FILE f',decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual((result['TEXT'],calls),('alpha',[.01]))

    def test_custom_terminator_is_explicit(self):
        bank,ctx=streams(b'17');calls=[]
        def sleeper(delay):calls.append(delay);bank.feed(2,b';')
        result=run('SET_FILE_ATR(f,ATR_EOL,59) '+OPEN+'READ f(n,CR) CLOSE FILE f',decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual((result['N'],calls),(17,[.01]))

    def test_binary_waits_for_every_width_and_records_one_completion(self):
        bank,ctx=streams(struct.pack('<i',17));calls=[]
        def sleeper(delay):
            calls.append(delay);self.assertEqual((task.snapshot()['N'],task.snapshot()['M']),(77,88))
            self.assertEqual(task.snapshot()['F']['position'],0);bank.feed(2,struct.pack('<i',29))
        task,_=compile_program(OPEN.replace("'RO'","'RB'")+'n=77 m=88 READ f(n,m) CLOSE FILE f',decl=DECL,context=ctx,sleep=sleeper)
        result=task.run();self.assertEqual((result['N'],result['M'],calls),(17,29,[.01]))
        self.assertEqual(len(task.read_requests),1)

    def test_reverse_binary_uses_existing_checked_format(self):
        bank,ctx=streams(b'\x01\x02');calls=[]
        def sleeper(delay):calls.append(delay);bank.feed(2,b'\x03\x04')
        result=run('SET_FILE_ATR(f,ATR_REVERSE) '+OPEN.replace("'RO'","'RB'")+'READ f(n) CLOSE FILE f',decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual((result['N'],calls),(16909060,[.01]))

    def test_invalid_complete_text_fails_without_waiting_or_partial_outputs(self):
        bank,ctx=streams(b'17 wrong\n');calls=[]
        task,_=compile_program(OPEN+'n=77 m=88 READ f(n,m,CR)',decl=DECL,context=ctx,sleep=lambda delay:calls.append(delay))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'invalid INTEGER'):task.run()
        self.assertEqual((task.snapshot()['N'],task.snapshot()['M'],task.snapshot()['F']['position']),(77,88,0))
        self.assertEqual((calls,task.read_requests,bank._pending),([],(),{}));bank.close(task._state.values['F'])

    def test_non_ascii_text_rejects_without_waiting(self):
        bank,ctx=streams(b'\xff');task,_=compile_program(OPEN+'READ f(text)',decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ASCII'):task.run()
        self.assertEqual(task.snapshot()['F']['position'],0);self.assertEqual(bank._pending,{})
        bank.close(task._state.values['F'])

    def test_pending_standalone_read_requires_explicit_sleeper_provenance(self):
        bank,ctx=streams();task,_=compile_program(OPEN+'n=77 READ f(n)',decl=DECL,context=ctx)
        with patch('time.sleep',side_effect=AssertionError('Serial wait must not use host sleep'))as sleeper:
            with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit sleeper'):task.run()
            sleeper.assert_not_called()
        self.assertEqual((task.snapshot()['N'],bank._pending),(77,{}));bank.close(task._state.values['F'])

    def test_binary_or_fixed_read_over_capacity_fails_before_wait(self):
        for mode,body,extra in (('RB','READ f(n)',''),('RO','READ f(text::4)',''),('RO','READ f(text)','SET_FILE_ATR(f,ATR_FIELD) ')):
            with self.subTest(mode=mode,body=body):
                bank,ctx=streams(capacity=3);calls=[]
                task,_=compile_program(extra+f"OPEN FILE f('{mode}','P2:') "+body,decl=DECL,context=ctx,sleep=lambda delay:calls.append(delay))
                with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):task.run()
                self.assertEqual((calls,bank._pending),([],{}));bank.close(task._state.values['F'])

    def test_prior_unclosed_prefix_counts_against_atomic_capacity(self):
        bank,ctx=streams(b'1234',capacity=4);calls=[]
        task,_=compile_program(OPEN+'READ f(n::1) m=88 READ f(m::4)',decl=DECL,context=ctx,sleep=lambda delay:calls.append(delay))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):task.run()
        self.assertEqual((task.snapshot()['N'],task.snapshot()['M'],task.snapshot()['F']['position']),(1,88,1))
        self.assertEqual(calls,[]);bank.close(task._state.values['F']);self.assertEqual(bank.snapshot()[2]['input'],b'234')


class SerialWaitFinalInputTests(unittest.TestCase):
    def test_preloaded_final_input_allows_unterminated_field(self):
        bank,ctx=streams(b'17',final=True)
        result=run(OPEN+'READ f(n) CLOSE FILE f',decl=DECL,context=ctx)
        self.assertEqual(result['N'],17);self.assertTrue(bank.snapshot()[2]['final'])

    def test_finish_input_completes_trailing_field(self):
        bank,ctx=streams(b'17');calls=[]
        def sleeper(delay):calls.append(delay);bank.finish_input(2)
        result=run(OPEN+'READ f(n) CLOSE FILE f',decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual((result['N'],calls),(17,[.01]));self.assertTrue(bank.snapshot()[2]['final'])

    def test_final_empty_input_reports_eof_with_outputs_preserved(self):
        bank,ctx=streams();calls=[]
        def sleeper(delay):calls.append(delay);bank.finish_input(2)
        task,_=compile_program(OPEN+'n=77 READ f(n)',decl=DECL,context=ctx,sleep=sleeper)
        with self.assertRaises(rt.KarelRuntimeError):task.run()
        self.assertEqual((task.snapshot()['N'],task.snapshot()['F']['position'],calls),(77,0,[.01]))
        self.assertEqual(bank._pending,{});bank.close(task._state.values['F'])

    def test_binary_final_short_field_fails_atomically(self):
        bank,ctx=streams(struct.pack('<i',17));calls=[]
        def sleeper(delay):calls.append(delay);bank.finish_input(2)
        task,_=compile_program(OPEN.replace("'RO'","'RB'")+'n=77 m=88 READ f(n,m)',decl=DECL,context=ctx,sleep=sleeper)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'finalized serial input'):task.run()
        self.assertEqual((task.snapshot()['N'],task.snapshot()['M'],task.snapshot()['F']['position']),(77,88,0))
        bank.close(task._state.values['F']);self.assertEqual(bank.snapshot()[2]['input'],struct.pack('<i',17))

    def test_final_partial_quoted_string_is_invalid_instead_of_waiting(self):
        bank,ctx=streams(b"'abc",final=True);calls=[]
        task,_=compile_program(OPEN+'READ f(text::0::2)',decl=DECL,context=ctx,sleep=lambda delay:calls.append(delay))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'quoted STRING'):task.run()
        self.assertEqual((calls,bank._pending),([],{}));bank.close(task._state.values['F'])

    def test_final_input_rejects_additional_feeds_even_after_close(self):
        bank,ctx=streams(b'17',final=True);before=bank.snapshot()
        for data in (b'',b'18'):
            with self.subTest(data=data),self.assertRaisesRegex(ValueError,'final'):bank.feed(2,data)
        self.assertEqual(bank.snapshot(),before);bank.finish_input(2)
        run(OPEN+'READ f(n) CLOSE FILE f',decl=DECL,context=ctx)
        with self.assertRaisesRegex(ValueError,'final'):bank.feed(2,b'18')

    def test_finite_ports_keep_feed_behavior_and_reject_finish_input(self):
        bank=rt.SerialStreams({2:{'input':'17'}})
        with self.assertRaisesRegex(ValueError,'waiting'):bank.finish_input(2)
        bank.feed(2,b'8');self.assertEqual(bank.snapshot()[2]['input'],b'178')
        self.assertNotIn('wait',bank.snapshot()[2]);self.assertNotIn('final',bank.snapshot()[2])

    def test_wait_final_flags_use_actual_booleans_and_valid_combination(self):
        for row in ({'wait':1},{'wait':None},{'final':1},{'wait':True,'final':None},{'wait':False,'final':False}):
            with self.subTest(row=row),self.assertRaises(ValueError):rt.SerialStreams({2:row})
        bank=rt.SerialStreams({2:{'wait':True}});self.assertEqual((bank.ports[2]['wait'],bank.ports[2]['final']),(True,False))

    def test_wait_final_json_roundtrip_and_legacy_shapes(self):
        bank,_=streams(b'partial');config=json.loads(json.dumps(bank.to_config()))
        self.assertEqual((config['ports']['2']['wait'],config['ports']['2']['final']),(True,False))
        self.assertEqual(rt.SerialStreams.from_config(config).to_config(),config)
        bank.finish_input(2);config=json.loads(json.dumps(bank.to_config()))
        self.assertTrue(config['ports']['2']['final']);self.assertEqual(rt.SerialStreams.from_config(config).to_config(),config)
        finite=rt.SerialStreams.from_config({'ports':{'2':{'wait':False,'final':True}}})
        self.assertNotIn('wait',finite.to_config()['ports']['2']);self.assertNotIn('final',finite.to_config()['ports']['2'])


class SerialWaitLifecycleTests(unittest.TestCase):
    def test_pause_resume_retains_captured_target_and_format_once(self):
        bank,_=streams();routines='ROUTINE slot:INTEGER BEGIN count=count+1 RETURN 1 END slot ROUTINE columns:INTEGER BEGIN count=count+1 RETURN 3 END columns'
        project=translate_project({'main':source('MAIN',OPEN+'count=0 READ f(a[slot()]::columns()) CLOSE FILE f',decl=DECL,routines=routines)}).instantiate(
            context=rt.ExecutionContext(serial_streams=bank))
        project.scheduler.start('MAIN')
        for _ in range(50):
            project.scheduler.step()
            if bank._pending:break
        task=project.programs['MAIN'];self.assertEqual(task.snapshot()['COUNT'],2);task.pause()
        for _ in range(30):
            project.scheduler.step()
            if task.task_state=='paused':break
        self.assertEqual(task.task_state,'paused');self.assertEqual(len(bank._pending),1)
        bank.feed(2,b'123');project.scheduler.continue_task('MAIN');project.scheduler.run()
        self.assertEqual((task.snapshot()['COUNT'],task.snapshot()['A']),(2,[123,U]))
        self.assertEqual(len(task.read_requests),1);self.assertEqual(bank._pending,{})

    def test_queries_allowed_but_close_and_raw_read_cannot_interfere(self):
        bank,_=streams(b'1');project=pending_project(bank);task=project.programs['MAIN'];h=task._state.values['F']
        self.assertEqual(bank.bytes_ahead(h),1);self.assertEqual(bank.seek(h,0),2)
        for operation in (lambda:bank.close(h),lambda:bank.read_bytes(h,1),
                          lambda:task._state.file_read(h,[task._state.reference('M')])):
            with self.subTest(operation=operation),self.assertRaisesRegex(rt.KarelRuntimeError,'pending READ'):operation()
        self.assertEqual(len(bank._pending),1);self.assertEqual(h.position,0)
        bank.feed(2,b'7\n');project.scheduler.run();self.assertEqual(task.snapshot()['N'],17)
        self.assertEqual(bank._pending,{})

    def test_overlapping_cooperative_read_rejects_without_cancelling_owner(self):
        bank,_=streams();project=pending_project(bank);task=project.programs['MAIN'];h=task._state.values['F']
        other=bank.read_items(task._state,h,[task._state.reference('M')])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'pending READ'):next(other)
        self.assertEqual(len(bank._pending),1);bank.feed(2,b'7\n');project.scheduler.run()
        self.assertEqual(task.snapshot()['N'],7);self.assertEqual(bank._pending,{})

    def test_stop_cleans_pending_but_preserves_open_handle_for_explicit_close(self):
        bank,_=streams(b'1');project=pending_project(bank);task=project.programs['MAIN'];project.scheduler.stop('MAIN')
        self.assertEqual(bank._pending,{});self.assertEqual(task.snapshot()['F']['position'],0)
        self.assertEqual(bank.snapshot()[2]['input'],b'1')
        with self.assertRaisesRegex(ValueError,'live serial'):project.context.to_config()
        bank.close(task._state.values['F']);self.assertEqual(bank.snapshot()[2]['input'],b'1')

    def test_abort_unwinds_pending_read_without_consuming_prefix(self):
        bank,_=streams(b'1');project=pending_project(bank);task=project.programs['MAIN']
        rt.request_task_control(task._state,'ABORT')
        with self.assertRaises(rt.KarelAbort):project.scheduler.run()
        self.assertEqual((bank._pending,task.snapshot()['N'],task.snapshot()['F']['position']),({},77,0))
        bank.close(task._state.values['F']);self.assertEqual(bank.snapshot()[2]['input'],b'1')

    def test_budget_exhaustion_cleans_pending_read(self):
        bank,_=streams();project=pending_project(bank);task=project.programs['MAIN'];task._state.max_steps=task._state.steps+1
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):project.scheduler.run(max_cycles=100)
        self.assertEqual(bank._pending,{});self.assertEqual(task.snapshot()['F']['position'],0);bank.close(task._state.values['F'])

    def test_sleeper_failure_cleans_pending_and_restores_input_adapter(self):
        bank,ctx=streams()
        def sleeper(delay):raise ValueError('scripted failure')
        original=lambda request:[99]
        task,_=compile_program(OPEN+'READ f(n)',decl=DECL,context=ctx,sleep=sleeper,read=original)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'scripted failure'):task.run()
        self.assertEqual(bank._pending,{});self.assertIs(task._state._read,original);bank.close(task._state.values['F'])

    def test_stale_pending_registration_fails_without_deleting_foreign_entry(self):
        bank,_=streams();project=pending_project(bank);task=project.programs['MAIN'];h=task._state.values['F'];foreign=object()
        bank._pending[id(h)]=foreign
        with self.assertRaisesRegex(rt.KarelRuntimeError,'registration'):project.scheduler.run()
        self.assertIs(bank._pending[id(h)],foreign);self.assertEqual(task.snapshot()['N'],77)
        bank._pending.pop(id(h));bank.close(h)

    def test_cursor_change_during_pending_read_fails_closed(self):
        bank,_=streams(b'1');project=pending_project(bank);task=project.programs['MAIN'];h=task._state.values['F'];h.position=1
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cursor changed'):project.scheduler.run()
        self.assertEqual(bank._pending,{});self.assertEqual(task.snapshot()['N'],77)
        h.position=0;bank.close(h);self.assertEqual(bank.snapshot()[2]['input'],b'1')

    def test_same_task_called_program_inherits_explicit_sleeper(self):
        bank,ctx=streams();calls=[]
        def sleeper(delay):calls.append(delay);bank.feed(2,b'17');bank.finish_input(2)
        project=translate_project({'main':source('MAIN',"CALL_PROG('CHILD',s)"),
            'child':source('CHILD',OPEN+'READ f(n) CLOSE FILE f',decl=DECL)}).instantiate(context=ctx,options={'sleep':sleeper})
        project.programs['MAIN'].run();self.assertEqual(project.programs['CHILD'].snapshot()['N'],17)
        self.assertEqual(calls,[.01]);self.assertEqual(bank._pending,{})

    def test_linked_routine_waits_without_new_clock_or_task(self):
        bank,ctx=streams();calls=[]
        def sleeper(delay):calls.append(delay);bank.feed(2,b'29\n')
        project=translate_project({'main':source('MAIN','n=read_value()',routines='ROUTINE read_value:INTEGER FROM LIB'),
            'lib':source('LIB','',decl=DECL,routines='ROUTINE read_value:INTEGER BEGIN '+OPEN+'READ f(n,CR) CLOSE FILE f RETURN n END read_value')}).instantiate(context=ctx,options={'sleep':sleeper})
        self.assertEqual(project.programs['MAIN'].run()['N'],29);self.assertEqual(calls,[.01]);self.assertEqual(bank._pending,{})

    def test_saved_final_state_after_completion_has_no_live_registry(self):
        bank,ctx=streams(b'17',final=True);run(OPEN+'READ f(n) CLOSE FILE f',decl=DECL,context=ctx)
        config=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(config)
        self.assertEqual(restored.to_config(),config);self.assertEqual(restored.serial_streams._pending,{})
        with self.assertRaisesRegex(ValueError,'final'):restored.serial_streams.feed(2,b'18')


if __name__=='__main__':unittest.main()
