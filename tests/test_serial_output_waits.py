"""Captured serial TX waits, cancellation and exact pending-operation lifetimes."""
from copy import deepcopy
import json
import struct
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate_project
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source
from tests.test_predefined_files import binding

DECL='f:FILE n,s,visits:INTEGER text:STRING[16] flag,done:BOOLEAN a:ARRAY[2]OF INTEGER'
OPEN="OPEN FILE f('WO','P2:') "
CLOSE=' s=IO_STATUS(f) CLOSE FILE f done=TRUE'


def streams(output=b'old',capacity=4,*,incoming=b'',limit=32,wait_output=True,**row):
    bank=rt.SerialStreams({2:dict(capacity=capacity,input=incoming,output=output,wait_output=wait_output,**row)},limit=limit)
    return bank,rt.ExecutionContext(serial_streams=bank)


def build(body=OPEN+"WRITE f('XY')"+CLOSE,*,ctx=None,routines='',decl=DECL,**options):
    bank,ctx=streams() if ctx is None else (ctx.serial_streams,ctx)
    task,result=compile_program(body,decl=decl,routines=routines,context=ctx,**options)
    return task,bank,ctx,result


def pending(body=OPEN+"WRITE f('XY')"+CLOSE,*,ctx=None,routines='',decl=DECL):
    bank,ctx=streams() if ctx is None else (ctx.serial_streams,ctx)
    linked=translate_project({'main':source('MAIN',body,decl=decl,routines=routines)}).instantiate(context=ctx)
    linked.scheduler.start('MAIN')
    for _ in range(100):
        linked.scheduler.step()
        if bank._writes:return linked,linked.programs['MAIN'],bank,ctx
    raise AssertionError('Serial WRITE did not wait')


def clean(test,task,bank):
    test.assertEqual(bank._writes,{})
    for _,handle in [(key,record[0]) for key,record in bank._open.items()]:test.assertIsNone(handle._write_operation)


class SerialOutputProgressTests(unittest.TestCase):
    def test_waits_then_appends_one_complete_payload(self):
        calls=[];task,bank,_,_=build(sleep=lambda seconds:(calls.append(seconds),bank.take_output(2))and None)
        self.assertEqual(task.run()['S'],0);self.assertEqual(bank.snapshot()[2]['output'],b'XY');self.assertEqual(calls,[.01]);clean(self,task,bank)

    def test_partial_drains_do_not_publish_partial_write(self):
        bank,ctx=streams(b'abc',3);seen=[]
        def sleep(_):seen.append(bank.snapshot()[2]['output']);bank.take_output(2,1)
        task,_,_,_=build(ctx=ctx,sleep=sleep);task.run();self.assertEqual(seen,[b'abc',b'bc']);self.assertEqual(bank.snapshot()[2]['output'],b'cXY')

    def test_immediate_room_needs_no_sleeper(self):
        bank,ctx=streams(b'a',4);task,_,_,_=build(ctx=ctx);task.run();self.assertEqual(bank.snapshot()[2]['output'],b'aXY')

    def test_default_still_rejects_full_output_without_wait(self):
        bank,ctx=streams(wait_output=False);calls=[];task,_,_,_=build(ctx=ctx,sleep=calls.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):task.run()
        self.assertEqual(bank.snapshot()[2]['output'],b'old');self.assertEqual(calls,[]);clean(self,task,bank)

    def test_full_opt_in_requires_explicit_standalone_sleeper(self):
        task,bank,_,_=build()
        with patch('karel2py.runtime.time.sleep') as sleeper,self.assertRaisesRegex(rt.KarelRuntimeError,'explicit sleeper'):task.run()
        sleeper.assert_not_called();self.assertEqual(bank.snapshot()[2]['output'],b'old');clean(self,task,bank)

    def test_atomic_payload_too_large_fails_before_wait(self):
        bank,ctx=streams(b'',1);calls=[];task,_,_,_=build(ctx=ctx,sleep=calls.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Atomic'):task.run()
        self.assertEqual(calls,[]);self.assertEqual(bank.snapshot()[2]['output'],b'');clean(self,task,bank)

    def test_retained_receive_bytes_count_against_capacity(self):
        bank,ctx=streams(b'',3,incoming=b'ab');calls=[];task,_,_,_=build(ctx=ctx,sleep=calls.append)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Atomic'):task.run()
        self.assertEqual(calls,[]);self.assertEqual(bank.snapshot()[2]['input'],b'ab')

    def test_exact_capacity_payload_can_complete_after_drain(self):
        bank,ctx=streams(b'old',4);task,_,_,_=build(OPEN+"WRITE f('WXYZ')"+CLOSE,ctx=ctx,sleep=lambda _:bank.take_output(2) and None)
        task.run();self.assertEqual(bank.snapshot()[2]['output'],b'WXYZ')

    def test_scalar_value_is_captured_before_wait(self):
        def sleep(_):task._state.set('N',99);bank.take_output(2)
        task,bank,_,_=build('n=7 '+OPEN+'WRITE f(n::2)'+CLOSE,sleep=sleep)
        self.assertEqual(task.run()['N'],99);self.assertEqual(bank.snapshot()[2]['output'],b' 7')

    def test_array_bytes_are_detached_before_wait(self):
        bank,ctx=streams(b'12345678',8)
        def sleep(_):
            for index in (1,2):rt.index_reference(task._state.values['A'],index).set(9)
            bank.take_output(2)
        task,_,_,_=build("a[1]=1 a[2]=2 OPEN FILE f('WB','P2:') WRITE f(a)"+CLOSE,ctx=ctx,sleep=sleep)
        self.assertEqual(task.run()['A'],[9,9]);self.assertEqual(bank.snapshot()[2]['output'],struct.pack('<ii',1,2))

    def test_format_and_value_routines_run_once(self):
        routines="ROUTINE val:STRING BEGIN visits=visits*10+1 RETURN 'A' END val ROUTINE width:INTEGER BEGIN visits=visits*10+2 RETURN 2 END width"
        task,bank,_,_=build('visits=0 '+OPEN+'WRITE f(val()::width())'+CLOSE,routines=routines,sleep=lambda _:bank.take_output(2) and None)
        self.assertEqual(task.run()['VISITS'],12);self.assertEqual(len(bank.snapshot()[2]['output']),2)

    def test_binary_numeric_batch_is_atomic(self):
        bank,ctx=streams(b'123456789',16);task,_,_,_=build("OPEN FILE f('WB','P2:') WRITE f(1,-2,1.25)"+CLOSE,ctx=ctx,sleep=lambda _:bank.take_output(2) and None)
        task.run();self.assertEqual(bank.snapshot()[2]['output'],struct.pack('<iif',1,-2,1.25))

    def test_custom_eol_is_applied_once(self):
        task,bank,_,_=build("SET_FILE_ATR(f,ATR_EOL,59) "+OPEN+"WRITE f('X',CR)"+CLOSE,sleep=lambda _:bank.take_output(2) and None)
        task.run();self.assertEqual(bank.snapshot()[2]['output'],b'X;')

    def test_two_writes_wait_independently(self):
        calls=[]
        def sleep(_):calls.append(bank.take_output(2))
        task,bank,_,_=build(OPEN+"WRITE f('XY') WRITE f('ZZZ')"+CLOSE,sleep=sleep)
        task.run();self.assertEqual(calls,[b'old',b'XY']);self.assertEqual(bank.snapshot()[2]['output'],b'ZZZ')

    def test_file_write_records_keep_existing_shape(self):
        task,bank,_,_=build(sleep=lambda _:bank.take_output(2) and None);task.run();self.assertEqual(task.write_requests,())

    def test_label_dispatcher_retains_wait(self):
        task,bank,_,_=build('entry:: '+OPEN+"WRITE f('XY')"+CLOSE,sleep=lambda _:bank.take_output(2) and None)
        self.assertTrue(task.run()['DONE']);self.assertEqual(bank.snapshot()[2]['output'],b'XY')

    def test_scheduler_waits_for_explicit_host_drain(self):
        linked,task,bank,_=pending();self.assertEqual(bank.snapshot()[2]['output'],b'old');bank.take_output(2)
        linked.scheduler.run();self.assertEqual(task.snapshot()['S'],0);self.assertEqual(bank.snapshot()[2]['output'],b'XY');clean(self,task,bank)

    def test_shared_bank_space_can_be_freed_from_another_port(self):
        bank=rt.SerialStreams({1:dict(capacity=4,output=b'abcd'),2:dict(capacity=4,output=b'',wait_output=True)},limit=4)
        ctx=rt.ExecutionContext(serial_streams=bank);calls=[]
        def sleep(_):calls.append(bank.take_output(1))
        task,_,_,_=build(ctx=ctx,sleep=sleep);task.run();self.assertEqual(calls,[b'abcd']);self.assertEqual(bank.snapshot()[2]['output'],b'XY')


class SerialOutputCancellationTests(unittest.TestCase):
    def test_host_cancel_continues_without_append(self):
        def sleep(_):rt.cancel_file(task._state,task._state.values['F'])
        task,bank,_,_=build(sleep=sleep);self.assertEqual(task.run()['S'],6);self.assertEqual(bank.snapshot()[2]['output'],b'old');clean(self,task,bank)

    def test_cancel_wins_over_drain_in_same_callback(self):
        def sleep(_):bank.take_output(2);rt.cancel_file(task._state,task._state.values['F'])
        task,bank,_,_=build(sleep=sleep);self.assertEqual(task.run()['S'],6);self.assertEqual(bank.snapshot()[2]['output'],b'')

    def test_repeated_cancellation_is_idempotent(self):
        def sleep(_):
            handle=task._state.values['F'];rt.cancel_file(task._state,handle);rt.cancel_file(task._state,handle)
        task,bank,_,_=build(sleep=sleep);self.assertEqual(task.run()['S'],6);clean(self,task,bank)

    def test_global_handler_cancels_pending_write(self):
        body='flag=FALSE CONDITION[1]: WHEN flag DO CANCEL FILE f ENDCONDITION ENABLE CONDITION[1] '+OPEN+"WRITE f('XY')"+CLOSE
        task,bank,_,_=build(body,sleep=lambda _:task._state.set('FLAG',True));self.assertEqual(task.run()['S'],6);self.assertEqual(bank.snapshot()[2]['output'],b'old')

    def test_idle_cancel_does_not_cancel_future_write(self):
        task,bank,_,_=build(OPEN+"CANCEL FILE f WRITE f('XY')"+CLOSE,sleep=lambda _:bank.take_output(2) and None)
        self.assertEqual(task.run()['S'],0);self.assertEqual(bank.snapshot()[2]['output'],b'XY')

    def test_cancelled_write_can_be_followed_by_successful_write(self):
        calls=[]
        def sleep(_):
            calls.append(1)
            if len(calls)==1:rt.cancel_file(task._state,task._state.values['F'])
            else:bank.take_output(2)
        task,bank,_,_=build(OPEN+"WRITE f('XY') n=IO_STATUS(f) WRITE f('ZZ')"+CLOSE,sleep=sleep)
        self.assertEqual((task.run()['N'],task.snapshot()['S']),(6,0));self.assertEqual(bank.snapshot()[2]['output'],b'ZZ')

    def test_changed_cursor_is_validated_before_cancellation(self):
        def sleep(_):
            task._state.values['F'].position=1;rt.cancel_file(task._state,task._state.values['F'])
        task,bank,_,_=build(sleep=sleep)
        with self.assertRaises(rt.KarelRuntimeError):task.run()
        self.assertEqual(bank.snapshot()[2]['output'],b'old');clean(self,task,bank)

    def test_changed_attributes_cannot_be_hidden_by_cancel(self):
        def sleep(_):task._state.values['F'].eol=13;rt.cancel_file(task._state,task._state.values['F'])
        task,bank,_,_=build(sleep=sleep)
        with self.assertRaises(rt.KarelRuntimeError):task.run()
        self.assertEqual(bank.snapshot()[2]['output'],b'old')

    def test_binary_cancel_keeps_prior_tx_bytes(self):
        bank,ctx=streams(b'1234',4)
        def sleep(_):rt.cancel_file(task._state,task._state.values['F'])
        task,_,_,_=build("OPEN FILE f('WB','P2:') WRITE f(17)"+CLOSE,ctx=ctx,sleep=sleep)
        self.assertEqual(task.run()['S'],6);self.assertEqual(bank.snapshot()[2]['output'],b'1234')

    def test_close_remains_busy_after_cancel_until_unwind(self):
        def sleep(_):
            handle=task._state.values['F'];rt.cancel_file(task._state,handle)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'pending WRITE'):bank.close(handle)
        task,bank,_,_=build(sleep=sleep);self.assertEqual(task.run()['S'],6);self.assertEqual(bank.handles,[])


class SerialOutputLifetimeTests(unittest.TestCase):
    def test_pause_retains_bytes_and_resume_can_complete(self):
        body='flag=FALSE CONDITION[1]: WHEN flag DO PAUSE ENDCONDITION ENABLE CONDITION[1] '+OPEN+"WRITE f('XY')"+CLOSE
        task,bank,_,_=build(body,sleep=lambda _:task._state.set('FLAG',True))
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertTrue(bank._writes);self.assertEqual(bank.snapshot()[2]['output'],b'old');bank.take_output(2)
        self.assertEqual(task.resume()['S'],0);self.assertEqual(bank.snapshot()[2]['output'],b'XY');clean(self,task,bank)

    def test_paused_cancellation_leaves_task_paused_until_resume(self):
        body='flag=FALSE CONDITION[1]: WHEN flag DO PAUSE ENDCONDITION ENABLE CONDITION[1] '+OPEN+"WRITE f('XY')"+CLOSE
        task,bank,_,_=build(body,sleep=lambda _:task._state.set('FLAG',True))
        with self.assertRaises(rt.KarelPause):task.run()
        rt.cancel_file(task._state,task._state.values['F']);self.assertEqual(task.task_state,'paused');self.assertEqual(task.resume()['S'],6)

    def test_stop_releases_exact_pending_registration(self):
        linked,task,bank,_=pending();task.stop();clean(self,task,bank);self.assertEqual(bank.snapshot()[2]['output'],b'old')

    def test_abort_releases_pending_registration(self):
        def sleep(_):task._state.abort(7)
        task,bank,_,_=build(sleep=sleep)
        with self.assertRaises(rt.KarelAbort):task.run()
        clean(self,task,bank);self.assertEqual(bank.snapshot()[2]['output'],b'old')

    def test_step_budget_bounds_explicit_wait_loop(self):
        task,bank,_,_=build(sleep=lambda _:None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):task.run(max_steps=50)
        clean(self,task,bank);self.assertEqual(bank.snapshot()[2]['output'],b'old')

    def test_sleeper_exception_cleans_pending_registration(self):
        def sleep(_):raise ValueError('authored TX driver failure')
        task,bank,_,_=build(sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'TX driver failure'):task.run()
        clean(self,task,bank)

    def test_sleeper_must_return_none(self):
        task,bank,_,_=build(sleep=lambda _:True)
        with self.assertRaises(rt.KarelRuntimeError):task.run()
        clean(self,task,bank)

    def test_direct_write_cannot_bypass_pending_payload(self):
        def sleep(_):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'pending WRITE'):bank.write(task._state.values['F'],b'Q')
            bank.take_output(2)
        task,bank,_,_=build(sleep=sleep);task.run();self.assertEqual(bank.snapshot()[2]['output'],b'XY')

    def test_pending_write_blocks_read_seek_flush_and_close(self):
        bank,ctx=streams(incoming=b'1',capacity=5,output=b'old')
        def sleep(_):
            handle=task._state.values['F']
            for action in (lambda:bank.read_bytes(handle,1),lambda:bank.seek(handle,0),lambda:bank.flush(handle),lambda:bank.close(handle)):
                with self.assertRaisesRegex(rt.KarelRuntimeError,'pending WRITE'):action()
            bank.take_output(2)
        task,_,_,_=build("OPEN FILE f('RW','P2:') WRITE f('XYZ')"+CLOSE,ctx=ctx,sleep=sleep)
        task.run();self.assertEqual(bank.snapshot()[2]['input'],b'1');self.assertEqual(bank.snapshot()[2]['output'],b'XYZ')

    def test_replaced_tx_buffer_fails_without_new_payload(self):
        def sleep(_):bank.ports[2]['output']=bytearray(b'new')
        task,bank,_,_=build(sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identity'):task.run()
        self.assertEqual(bank.snapshot()[2]['output'],b'new');clean(self,task,bank)

    def test_changed_limit_fails_before_publication(self):
        def sleep(_):bank.limit+=1;bank.take_output(2)
        task,bank,_,_=build(sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identity'):task.run()
        self.assertEqual(bank.snapshot()[2]['output'],b'')

    def test_false_opt_in_after_wait_cannot_silently_complete(self):
        def sleep(_):bank.ports[2]['wait_output']=False;bank.take_output(2)
        task,bank,_,_=build(sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identity'):task.run()
        self.assertEqual(bank.snapshot()[2]['output'],b'')

    def test_overlapping_generated_write_preserves_original_token(self):
        def sleep(_):
            handle=task._state.values['F'];original=handle._write_operation;other=rt.cooperative_write_items(task._state,['Z'],file=handle)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'pending I/O'):next(other)
            self.assertIs(handle._write_operation,original);bank.take_output(2)
        task,bank,_,_=build(sleep=sleep);task.run();self.assertEqual(bank.snapshot()[2]['output'],b'XY')

    def test_live_context_save_is_still_rejected(self):
        def sleep(_):
            with self.assertRaisesRegex(ValueError,'Close live serial'):ctx.to_config()
            bank.take_output(2)
        task,bank,ctx,_=build(sleep=sleep);task.run();self.assertEqual(rt.ExecutionContext.from_config(ctx.to_config()).to_config(),ctx.to_config())


class SerialOutputBindingTests(unittest.TestCase):
    def test_linked_helper_uses_calling_task_wait_driver(self):
        bank,ctx=streams();calls=[]
        def sleep(_):calls.append(1);bank.take_output(2)
        docs={'m':source('MAIN','work()',routines='ROUTINE work FROM LIB'),
              'l':source('LIB', '',decl=DECL,routines="ROUTINE work BEGIN "+OPEN+"WRITE f('XY')"+CLOSE+' END work')}
        linked=translate_project(docs).instantiate(context=ctx,options=dict(sleep=sleep));linked.programs['MAIN'].run()
        self.assertEqual(calls,[1]);self.assertEqual(bank.snapshot()[2]['output'],b'XY');self.assertEqual(bank._writes,{})

    def test_borrowed_file_argument_retains_original_handle(self):
        routines="ROUTINE send(value:FILE) BEGIN WRITE value('XY') END send"
        task,bank,_,_=build(OPEN+'send(f)'+CLOSE,routines=routines,sleep=lambda _:bank.take_output(2) and None)
        self.assertEqual(task.run()['S'],0);self.assertEqual(bank.snapshot()[2]['output'],b'XY')

    def test_bound_default_output_can_wait(self):
        bank,ctx=streams();ctx=rt.ExecutionContext(serial_streams=bank,predefined_files={'TPDISPLAY':binding('P2:','WO')})
        task,_,_,_=build("WRITE('XY') CLOSE FILE TPDISPLAY",ctx=ctx,sleep=lambda _:bank.take_output(2) and None)
        task.run();self.assertEqual(bank.snapshot()[2]['output'],b'XY');self.assertEqual(bank._writes,{})

    def test_predefined_cleanup_is_busy_until_write_unwinds(self):
        bank,ctx=streams();ctx=rt.ExecutionContext(serial_streams=bank,predefined_files={'TPDISPLAY':binding('P2:','WO')})
        def sleep(_):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'pending WRITE'):ctx.close_predefined_files()
            bank.take_output(2)
        task,_,_,_=build("WRITE('XY') CLOSE FILE TPDISPLAY",ctx=ctx,sleep=sleep);task.run();self.assertEqual(bank.snapshot()[2]['output'],b'XY')

    def test_blocked_write_in_handler_fails_without_waiting(self):
        body="flag=TRUE CONDITION[1]: WHEN flag DO WRITE f('XY') ENDCONDITION "+OPEN+'ENABLE CONDITION[1] n=7'
        task,bank,_,_=build(body,sleep=lambda _:self.fail('Handler must not wait'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'handler'):task.run()
        clean(self,task,bank);self.assertEqual(bank.snapshot()[2]['output'],b'old')

    def test_scalar_callback_write_keeps_existing_observation(self):
        recorded=[];task,_=compile_program("WRITE('OK')",write=recorded.append)
        task.run();self.assertEqual(recorded,['OK']);self.assertEqual(task.write_requests[0]['adapter_outcome'],'callback_completed')


class SerialOutputOwnershipTests(unittest.TestCase):
    def test_file_array_selector_is_captured_once(self):
        bank=rt.SerialStreams({1:dict(capacity=4,output=b'old',wait_output=True),2:dict(capacity=4,output=b'keep')},limit=32)
        ctx=rt.ExecutionContext(serial_streams=bank)
        def sleep(_):task._state.set('N',2);bank.take_output(1)
        routines='ROUTINE slot:INTEGER BEGIN visits=visits+1 RETURN n END slot'
        body="n=1 visits=0 OPEN FILE f[1]('WO','P1:') OPEN FILE f[2]('WO','P2:') WRITE f[slot()]('XY') CLOSE FILE f[1] CLOSE FILE f[2]"
        task,_,_,_=build(body,ctx=ctx,decl='f:ARRAY[2]OF FILE n,visits:INTEGER',routines=routines,sleep=sleep)
        self.assertEqual(task.run()['VISITS'],1);self.assertEqual(bank.snapshot()[1]['output'],b'XY');self.assertEqual(bank.snapshot()[2]['output'],b'keep')

    def test_replaced_registration_remains_reserved(self):
        linked,task,bank,_=pending();handle=task._state.values['F'];foreign=object();bank._writes[id(handle)]=foreign
        with self.assertRaisesRegex(rt.KarelRuntimeError,'registration'):linked.scheduler.run()
        self.assertIs(bank._writes[id(handle)],foreign);self.assertEqual(bank.snapshot()[2]['output'],b'old')
        bank._writes.pop(id(handle));bank.close(handle)

    def test_replaced_operation_token_is_not_freed(self):
        linked,task,bank,_=pending();handle=task._state.values['F'];foreign={};handle._write_operation=foreign
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identity'):linked.scheduler.run()
        self.assertIs(handle._write_operation,foreign);self.assertEqual(bank._writes,{})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'pending WRITE'):bank.close(handle)
        handle._write_operation=None;bank.close(handle)

    def test_replaced_receive_buffer_fails_without_append(self):
        def sleep(_):bank.files['P2:']=bytearray();bank.take_output(2)
        task,bank,_,_=build(sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identity'):task.run()
        self.assertEqual(bank.snapshot()[2]['output'],b'')

    def test_direct_backend_wait_cannot_use_source_cancel(self):
        bank,ctx=streams();handle=rt.FileHandle();bank.open(handle,'WO','P2:')
        linked=translate_project({'main':source('MAIN','n=0')}).instantiate(context=ctx);task=linked.programs['MAIN'];task._state._scheduler=linked.scheduler
        job=bank.write_items(task._state,handle,b'XY');next(job)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'direct'):rt.cancel_file(task._state,handle)
        job.close();task._state._scheduler=None;self.assertEqual(bank._writes,{});bank.close(handle)

    def test_source_read_cannot_replace_pending_write(self):
        def sleep(_):
            handle=task._state.values['F'];other=rt.cooperative_file_read(task._state,handle,[])
            with self.assertRaisesRegex(rt.KarelRuntimeError,'pending WRITE'):next(other)
            self.assertIsNone(handle._read_operation);bank.take_output(2)
        task,bank,_,_=build(sleep=sleep);task.run();self.assertEqual(bank.snapshot()[2]['output'],b'XY')

    def test_wait_output_is_independent_from_receive_waiting(self):
        bank,ctx=streams(wait=True,final=False);task,_,_,_=build(ctx=ctx,sleep=lambda _:bank.take_output(2) and None)
        task.run();self.assertEqual(bank.snapshot()[2]['output'],b'XY');self.assertFalse(bank.snapshot()[2]['final'])

    def test_existing_immediate_write_can_run_during_waiting_read(self):
        bank,ctx=streams(b'',16,wait_output=False,wait=True,final=False)
        def sleep(_):task._state.set('FLAG',True);bank.feed(2,b'7\n')
        body="flag=FALSE CONDITION[1]: WHEN flag DO WRITE f('X') ENDCONDITION ENABLE CONDITION[1] OPEN FILE f('RW','P2:') READ f(n,CR)"+CLOSE
        task,_,_,_=build(body,ctx=ctx,sleep=sleep);self.assertEqual(task.run()['N'],7);self.assertEqual(bank.snapshot()[2]['output'],b'X')

    def test_ready_opted_in_handler_write_stays_immediate(self):
        bank,ctx=streams(b'old',8)
        body="flag=TRUE CONDITION[1]: WHEN flag DO WRITE f('XY') ENDCONDITION "+OPEN+'ENABLE CONDITION[1] n=7'+CLOSE
        task,_,_,_=build(body,ctx=ctx,sleep=lambda _:self.fail('Ready handler must not wait'));task.run();self.assertEqual(bank.snapshot()[2]['output'],b'oldXY')

    def test_legacy_direct_state_write_stays_synchronous(self):
        bank,ctx=streams();handle=rt.FileHandle();bank.open(handle,'WO','P2:');task,_=compile_program('n=0',context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):task._state.write_items(['XY'],file=handle)
        self.assertEqual((bank.snapshot()[2]['output'],bank._writes),(b'old',{}));bank.close(handle)


class SerialOutputCapacityChangeTests(unittest.TestCase):
    def test_other_port_close_can_release_bank_space(self):
        bank=rt.SerialStreams({1:dict(capacity=4,input=b'abcd'),2:dict(capacity=4,wait_output=True)},limit=4)
        reader=rt.FileHandle();bank.open(reader,'RO','P1:');self.assertEqual(bank.read_bytes(reader,4),b'abcd')
        ctx=rt.ExecutionContext(serial_streams=bank)
        def sleep(_):bank.close(reader)
        task,_,_,_=build(ctx=ctx,sleep=sleep);task.run();self.assertEqual(bank.snapshot()[1]['input'],b'');self.assertEqual(bank.snapshot()[2]['output'],b'XY')

    def test_host_feed_can_make_payload_impossible_without_indefinite_wait(self):
        calls=[]
        def sleep(_):calls.append(1);bank.take_output(2);bank.feed(2,b'abc')
        task,bank,_,_=build(sleep=sleep)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Atomic'):task.run()
        self.assertEqual(calls,[1]);self.assertEqual(bank.snapshot()[2]['input'],b'abc');self.assertEqual(bank.snapshot()[2]['output'],b'');clean(self,task,bank)

    def test_host_feed_and_drain_retain_shared_capacity_rules(self):
        bank,ctx=streams(b'1234567',8)
        def sleep(_):bank.take_output(2,3);bank.feed(2,b'ab')
        task,_,_,_=build(ctx=ctx,sleep=sleep);task.run();self.assertEqual(bank.snapshot()[2]['input'],b'ab');self.assertEqual(bank.snapshot()[2]['output'],b'4567XY')

    def test_empty_payload_does_not_need_output_space(self):
        bank,ctx=streams(b'full',4);task,_,_,_=build(OPEN+"WRITE f('')"+CLOSE,ctx=ctx)
        self.assertEqual(task.run()['S'],0);self.assertEqual(bank.snapshot()[2]['output'],b'full')

    def test_read_only_endpoint_rejects_even_empty_write(self):
        task,bank,_,_=build("OPEN FILE f('RO','P2:') WRITE f('')"+CLOSE)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'read-only'):task.run()
        self.assertEqual(bank.snapshot()[2]['output'],b'old');clean(self,task,bank)


class SerialOutputConfigurationTests(unittest.TestCase):
    def test_only_exact_booleans_are_accepted(self):
        for value in (0,1,None,'true',[],{}):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'BOOLEAN'):streams(wait_output=value)

    def test_default_flag_is_omitted_from_snapshot_and_json(self):
        bank,_=streams(wait_output=False);self.assertNotIn('wait_output',bank.snapshot()[2]);self.assertNotIn('wait_output',bank.to_config()['ports']['2'])

    def test_true_flag_round_trips_with_bytes(self):
        bank,_=streams();data=json.loads(json.dumps(bank.to_config()));self.assertIs(data['ports']['2']['wait_output'],True)
        self.assertEqual(rt.SerialStreams.from_config(data).to_config(),data)

    def test_closed_context_round_trip_keeps_enabled_flag(self):
        task,bank,ctx,_=build(sleep=lambda _:bank.take_output(2) and None);task.run()
        data=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(data).to_config(),data);self.assertIs(data['serial_streams']['ports']['2']['wait_output'],True)

    def test_ports_have_independent_wait_output_options(self):
        bank=rt.SerialStreams({1:{},2:dict(wait_output=True)});self.assertNotIn('wait_output',bank.snapshot()[1]);self.assertIs(bank.snapshot()[2]['wait_output'],True)

    def test_report_explains_cancellation_and_atomicity(self):
        _,_,_,result=build();policy=result.report['serial_output_wait_policy'];self.assertIn('before',policy['admission']);self.assertIn('immutable',policy['capture'])
        self.assertFalse(policy['controller_validated']);self.assertIn('status 6',policy['cancellation']);json.dumps(result.report)
