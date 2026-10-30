"""Authored cooperative FILE cancellation across explicit offline input services."""
import copy
import json
import struct
import tempfile
import unittest
from pathlib import Path
from karel2py import runtime as rt, translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source
from tests.test_keyboard import context as keyboard_context
from tests.test_pipe_attributes import bank as pipe_bank

DECL='f,g:FILE n,m,s,count:INTEGER text:STRING[16] flag,done:BOOLEAN'
OPEN="OPEN FILE f('RO','P2:') "
FINISH=' s=IO_STATUS(f) CLOSE FILE f done=TRUE'


def serial(data=b'',**extra):
    bank=rt.SerialStreams({2:dict(input=data,wait=True,**extra)})
    return bank,rt.ExecutionContext(serial_streams=bank)


def pending(ctx,body=OPEN+'n=77 READ f(n,CR)'+FINISH,*,routines='',decl=DECL):
    project=translate_project({'main':source('MAIN',body,decl=decl,routines=routines)}).instantiate(context=ctx)
    task=project.programs['MAIN'];project.scheduler.start('MAIN')
    for _ in range(80):
        project.scheduler.step()
        if task._state.values['F']._read_operation is not None:return project,task,task._state.values['F']
    raise AssertionError('READ did not become active')


class FileCancelSourceTests(unittest.TestCase):
    def execute_cancel(self,data=b'17 ',body='n=77 m=88 READ f(n,m,CR)',decl=DECL):
        bank,ctx=serial(data);calls=[]
        def sleeper(delay):
            calls.append(delay);rt.cancel_file(task._state,task._state.values['F'])
        task,result=compile_program(OPEN+body+FINISH,decl=decl,context=ctx,sleep=sleeper)
        values=task.run();return values,task,bank,calls,result

    def test_serial_cancel_preserves_all_outputs_cursor_and_prefix(self):
        values,task,bank,calls,_=self.execute_cancel()
        self.assertEqual((values['N'],values['M'],values['S'],values['DONE']),(77,88,6,True))
        self.assertEqual((bank.snapshot()[2]['input'],calls,task.read_requests),(b'17 ',[.01],()))
        self.assertIsNone(task._state.values['F']._read_operation);self.assertEqual(bank._pending,{})

    def test_binary_cancel_discards_no_complete_earlier_field(self):
        bank,ctx=serial(struct.pack('<i',17))
        def sleeper(_):rt.cancel_file(task._state,task._state.values['F'])
        task,_=compile_program(OPEN.replace("'RO'","'RB'")+'n=77 m=88 READ f(n,m)'+FINISH,decl=DECL,context=ctx,sleep=sleeper)
        values=task.run();self.assertEqual((values['N'],values['M'],values['S']),(77,88,6))
        self.assertEqual(bank.snapshot()[2]['input'],struct.pack('<i',17))

    def test_cancel_retains_previously_successful_prefix_consumption(self):
        bank,ctx=serial(b'3\n17 ')
        def sleeper(_):rt.cancel_file(task._state,task._state.values['F'])
        task,_=compile_program(OPEN+'READ f(count,CR) n=77 READ f(n,m,CR)'+FINISH,decl=DECL,context=ctx,sleep=sleeper)
        values=task.run();self.assertEqual((values['COUNT'],values['N'],values['S']),(3,77,6))
        self.assertEqual(bank.snapshot()[2]['input'],b'17 ');self.assertEqual(len(task.read_requests),1)

    def test_cancellation_at_same_time_as_complete_feed_wins(self):
        bank,ctx=serial(b'17')
        def sleeper(_):bank.feed(2,b'\n');rt.cancel_file(task._state,task._state.values['F'])
        task,_=compile_program(OPEN+'n=77 READ f(n,CR)'+FINISH,decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual(task.run()['N'],77);self.assertEqual(bank.snapshot()[2]['input'],b'17\n')

    def test_repeated_cancel_is_idempotent_and_later_read_succeeds(self):
        bank,ctx=serial(b'17')
        def sleeper(_):
            h=task._state.values['F'];rt.cancel_file(task._state,h);rt.cancel_file(task._state,h);bank.feed(2,b'\n')
        task,_=compile_program(OPEN+'n=77 READ f(n,CR) s=IO_STATUS(f) READ f(m,CR) CLOSE FILE f',decl=DECL,context=ctx,sleep=sleeper)
        values=task.run();self.assertEqual((values['N'],values['M'],values['S']),(77,17,6));self.assertEqual(len(task.read_requests),1)

    def test_handler_cancels_active_read_and_task_continues(self):
        bank,ctx=serial(b'17')
        def sleeper(_):task._state.set('FLAG',True)
        body="flag=FALSE CONDITION[1]: WHEN flag DO CANCEL FILE f ENDCONDITION ENABLE CONDITION[1] "+OPEN+'n=77 READ f(n,CR)'+FINISH
        task,_=compile_program(body,decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual((task.run()['N'],task.snapshot()['S'],task.task_state),(77,6,'completed'))

    def test_local_routine_can_cancel_handler_read(self):
        bank,ctx=serial()
        def sleeper(_):task._state.set('FLAG',True)
        routine='ROUTINE cancel_input(h:FILE) BEGIN CANCEL FILE h END cancel_input'
        body='flag=FALSE CONDITION[1]: WHEN flag DO cancel_input(f) ENDCONDITION ENABLE CONDITION[1] '+OPEN+'n=77 READ f(n)'+FINISH
        task,_=compile_program(body,decl=DECL,routines=routine,context=ctx,sleep=sleeper)
        self.assertEqual((task.run()['N'],task.snapshot()['S']),(77,6));self.assertEqual(task._state.local_frames,[])

    def test_idle_open_file_cancel_does_not_discard_data(self):
        bank=rt.MemoryFiles({'data':'17\n'})
        task,result=compile_program("OPEN FILE f('RO','data') CANCEL FILE f s=IO_STATUS(f) READ f(n,CR) CLOSE FILE f",decl=DECL,context=rt.ExecutionContext(files=bank))
        values=task.run();self.assertEqual((values['N'],values['S']),(17,0));self.assertEqual(bank.snapshot(),{'data':b'17\n'})
        self.assertFalse(result.report['file_cancel_policy']['controller_validated'])

    def test_idle_write_cancel_keeps_already_written_bytes(self):
        bank=rt.MemoryFiles();task,_=compile_program("OPEN FILE f('WO','data') WRITE f(17) CANCEL FILE f s=IO_STATUS(f) CLOSE FILE f",decl=DECL,context=rt.ExecutionContext(files=bank))
        self.assertEqual(task.run()['S'],0);self.assertEqual(bank.snapshot()['data'],b' 17')

    def test_file_parameter_alias_is_exact_live_handle(self):
        bank=rt.MemoryFiles({'data':'1'})
        task,_=compile_program("OPEN FILE f('RO','data') stop_input(f) s=IO_STATUS(f) CLOSE FILE f",decl=DECL,routines='ROUTINE stop_input(h:FILE) BEGIN CANCEL FILE h END stop_input',context=rt.ExecutionContext(files=bank))
        self.assertEqual(task.run()['S'],0)

    def test_non_file_target_rejected(self):
        with self.assertRaises(TranslationError):compile_program('CANCEL FILE n')

    def test_omitted_file_is_not_silently_motion_cancel(self):
        with self.assertRaises(TranslationError):compile_program('CANCEL FILE')

    def test_closed_handle_fails_without_creating_service(self):
        task,_=compile_program('CANCEL FILE f',decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not open'):task.run()
        self.assertIsNone(task._state.execution.files)

    def test_motion_cancel_and_purge_condition_still_compile(self):
        task,result=compile_program('CONDITION[1]: WHEN FALSE DO CANCEL FILE f ENDCONDITION PURGE CONDITION[1] CANCEL',decl=DECL)
        self.assertIn('CANCEL',str(result.report['motion_requests']))

    def test_generated_source_has_no_compiler_dependency(self):
        _,result=compile_program("OPEN FILE f('RO','data') CANCEL FILE f CLOSE FILE f",decl=DECL)
        self.assertIn('_rt.cancel_file(',result.python_source);self.assertNotIn('from karel2py.compiler',result.python_source)


class FileCancelBackendTests(unittest.TestCase):
    def test_pipe_wait_cancellation_preserves_bytes(self):
        bank=pipe_bank(b'17 ');ctx=rt.ExecutionContext(file_pipes=bank)
        def sleeper(_):rt.cancel_file(task._state,task._state.values['F'])
        task,_=compile_program("SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','PIP:LOG') n=77 READ f(n,m,CR)"+FINISH,decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual((task.run()['N'],task.snapshot()['S']),(77,6));self.assertEqual(bytes(bank.files['PIP:LOG']),b'17 ');self.assertEqual(bank._reads,{})

    def test_binary_pipe_cancellation_preserves_partial_record(self):
        bank=pipe_bank(struct.pack('<i',17));ctx=rt.ExecutionContext(file_pipes=bank)
        def sleeper(_):rt.cancel_file(task._state,task._state.values['F'])
        task,_=compile_program("SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RB','PIP:LOG') n=77 READ f(n,m)"+FINISH,decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual(task.run()['S'],6);self.assertEqual(bytes(bank.files['PIP:LOG']),struct.pack('<i',17))

    def test_keyboard_line_cancel_keeps_destinations_and_releases_job(self):
        ctx=keyboard_context(events=[dict(key='1'),dict(key='7'),dict(key='ENTER',at_ms=100)]);calls=[]
        def sleeper(_):calls.append(1);rt.cancel_file(task._state,task._state.values['F'])
        task,_=compile_program("OPEN FILE f('RO','KB:TPKB') n=77 READ f(n,CR)"+FINISH,decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual((task.run()['N'],task.snapshot()['S'],task.read_requests),(77,6,()))
        self.assertEqual(ctx.keyboard._active,{});self.assertEqual(ctx.keyboard.history[-1]['outcome'],'cancelled');self.assertTrue(calls)

    def test_keyboard_raw_cancel_retains_buffered_bytes(self):
        ctx=keyboard_context(events=[dict(key='a'),dict(key='b'),dict(key='c',at_ms=100)])
        def sleeper(_):rt.cancel_file(task._state,task._state.values['F'])
        task,_=compile_program("SET_FILE_ATR(f,ATR_PASSALL) OPEN FILE f('RO','KB:TPKB') text='old' READ f(text::4) s=IO_STATUS(f)",decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual((task.run()['TEXT'],task.snapshot()['S'],task.read_requests),('old',6,()))
        h=task._state.values['F'];self.assertEqual(ctx.keyboard._handles[h]['pending'],'ab');self.assertIsNone(h._read_operation);ctx.keyboard.close(h)

    def test_keyboard_submitted_prefix_is_retained(self):
        ctx=keyboard_context(events=[dict(key='1'),dict(key='7'),dict(key='ENTER'),dict(key='0',at_ms=100)])
        def sleeper(_):rt.cancel_file(task._state,task._state.values['F'])
        task,_=compile_program("OPEN FILE f('RO','KB:TPKB') n=77 READ f(n,CR,m,CR) s=IO_STATUS(f)",decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual(task.run()['N'],77);h=task._state.values['F'];self.assertEqual(ctx.keyboard._handles[h]['pending'],'17\n');ctx.keyboard.close(h)

    def test_rooted_directory_idle_cancel_keeps_file(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'data').write_bytes(b'17\n');bank=rt.DirectoryFiles(folder)
            task,_=compile_program("OPEN FILE f('RO','data') CANCEL FILE f READ f(n,CR) CLOSE FILE f",decl=DECL,context=rt.ExecutionContext(files=bank))
            self.assertEqual(task.run()['N'],17);self.assertEqual(Path(folder,'data').read_bytes(),b'17\n')

    def test_closed_context_round_trip_after_cancel(self):
        bank,ctx=serial(b'17');project,task,h=pending(ctx);rt.cancel_file(task._state,h);project.scheduler.run()
        config=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)
        self.assertEqual(bank._pending,{})


class FileCancelLifetimeTests(unittest.TestCase):
    def test_cancel_waiting_scheduled_reader(self):
        bank,ctx=serial(b'17');project,task,h=pending(ctx);rt.cancel_file(task._state,h);project.scheduler.run()
        self.assertEqual((task.snapshot()['N'],task.snapshot()['S'],task.task_state),(77,6,'completed'));self.assertEqual(bank._pending,{})

    def test_pause_retains_cancel_until_resume(self):
        bank,ctx=serial();project,task,h=pending(ctx);task.pause()
        for _ in range(40):
            project.scheduler.step()
            if task.task_state=='paused':break
        self.assertEqual(task.task_state,'paused');rt.cancel_file(task._state,h);self.assertIsNotNone(h._read_operation)
        self.assertEqual(task.task_state,'paused');project.scheduler.continue_task('MAIN');project.scheduler.run()
        self.assertEqual(task.snapshot()['S'],6);self.assertIsNone(h._read_operation)

    def test_stop_after_cancel_does_not_continue_source(self):
        bank,ctx=serial();project,task,h=pending(ctx);rt.cancel_file(task._state,h);project.scheduler.stop('MAIN')
        self.assertEqual(task.task_state,'stopped');self.assertEqual(task.snapshot()['DONE'],{'uninitialized':True});self.assertIsNone(h._read_operation);bank.close(h)

    def test_abort_after_cancel_remains_sticky(self):
        bank,ctx=serial();project,task,h=pending(ctx);rt.cancel_file(task._state,h);rt.request_task_control(task._state,'ABORT')
        with self.assertRaises(rt.KarelAbort):project.scheduler.run()
        self.assertIsNone(h._read_operation);self.assertEqual(bank._pending,{});bank.close(h)

    def test_live_cancelled_handle_still_prevents_save(self):
        bank,ctx=serial();project,task,h=pending(ctx);rt.cancel_file(task._state,h)
        with self.assertRaisesRegex(ValueError,'live serial'):ctx.to_config()
        project.scheduler.run();ctx.to_config()

    def test_second_cancel_does_not_poison_later_idle_use(self):
        bank,ctx=serial();project,task,h=pending(ctx,OPEN+'n=77 READ f(n) s=IO_STATUS(f) done=TRUE')
        rt.cancel_file(task._state,h);project.scheduler.run();rt.cancel_file(task._state,h);self.assertEqual(h.status,0);bank.close(h)

    def test_copied_handle_cannot_cancel_original(self):
        bank,ctx=serial();project,task,h=pending(ctx);foreign=copy.copy(h)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'registration'):rt.cancel_file(task._state,foreign)
        self.assertFalse(h._read_operation['cancelled']);rt.cancel_file(task._state,h);project.scheduler.run()

    def test_changed_endpoint_fails_before_cancel_mark(self):
        bank,ctx=serial();project,task,h=pending(ctx);original=h.name;h.name='P3:'
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identity'):rt.cancel_file(task._state,h)
        self.assertFalse(h._read_operation['cancelled']);h.name=original;rt.cancel_file(task._state,h);project.scheduler.run()

    def test_changed_cursor_fails_before_cancel_mark(self):
        bank,ctx=serial(b'17');project,task,h=pending(ctx);h.position=1
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cursor'):rt.cancel_file(task._state,h)
        h.position=0;rt.cancel_file(task._state,h);project.scheduler.run()

    def test_overlapping_dispatch_does_not_remove_owned_registration(self):
        bank,ctx=serial();project,task,h=pending(ctx);operation=h._read_operation
        other=rt.cooperative_file_read(task._state,h,[task._state.reference('M')])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'pending READ'):next(other)
        self.assertIs(h._read_operation,operation);rt.cancel_file(task._state,h);project.scheduler.run()

    def test_direct_host_read_is_not_silently_cancelled(self):
        bank,ctx=serial();task,_=compile_program(OPEN,decl=DECL,context=ctx,sleep=lambda _:None);task.run();h=task._state.values['F']
        task._state._scheduler=rt.TaskScheduler();job=bank.read_items(task._state,h,[task._state.reference('N')]);next(job)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'direct host'):rt.cancel_file(task._state,h)
        job.close();self.assertEqual(bank._pending,{});bank.close(h)

    def test_linked_handler_cancels_caller_read(self):
        bank,ctx=serial();sources={'main':source('MAIN','flag=FALSE CONDITION[1]: WHEN flag DO cancel_input(f) ENDCONDITION ENABLE CONDITION[1] '+OPEN+'n=77 READ f(n)'+FINISH,decl=DECL,routines='ROUTINE cancel_input(h:FILE) FROM LIB'),
            'lib':source('LIB','',routines='ROUTINE cancel_input(h:FILE) BEGIN CANCEL FILE h END cancel_input')}
        def sleeper(_):project.programs['MAIN']._state.set('FLAG',True)
        project=translate_project(sources).instantiate(context=ctx,options={'sleep':sleeper});project.programs['MAIN'].run()
        self.assertEqual((project.programs['MAIN'].snapshot()['N'],project.programs['MAIN'].snapshot()['S']),(77,6));self.assertEqual(bank._pending,{})

    def test_cancellation_of_other_handle_does_not_cancel_reader(self):
        bank=rt.SerialStreams({2:dict(wait=True,input=b'17'),3:dict(input=b'')});ctx=rt.ExecutionContext(serial_streams=bank)
        def sleeper(_):rt.cancel_file(task._state,task._state.values['G']);bank.feed(2,b'\n')
        task,_=compile_program(OPEN+"OPEN FILE g('RO','P3:') READ f(n,CR) CLOSE FILE f CLOSE FILE g",decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual(task.run()['N'],17);self.assertEqual(len(task.read_requests),1)

    def test_failure_unwinds_cancellation_registration(self):
        bank,ctx=serial(b'bad\n');task,_=compile_program(OPEN+'READ f(n,CR)',decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):task.run()
        h=task._state.values['F'];self.assertIsNone(h._read_operation);self.assertEqual(bank._pending,{});bank.close(h)


class FileCancelIsolationTests(unittest.TestCase):
    def test_stale_serial_registration_is_not_hidden_by_cancel(self):
        bank,ctx=serial();project,task,h=pending(ctx);record=bank._pending[id(h)];foreign=object();bank._pending[id(h)]=foreign
        with self.assertRaisesRegex(rt.KarelRuntimeError,'registration'):rt.cancel_file(task._state,h)
        self.assertFalse(h._read_operation['cancelled']);bank._pending[id(h)]=record;rt.cancel_file(task._state,h);project.scheduler.run()

    def test_stale_pipe_registration_is_not_hidden_by_cancel(self):
        bank=pipe_bank();ctx=rt.ExecutionContext(file_pipes=bank)
        body="SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','PIP:LOG') n=77 READ f(n)"+FINISH
        project,task,h=pending(ctx,body);record=bank._reads[id(h)];foreign=object();bank._reads[id(h)]=foreign
        with self.assertRaisesRegex(rt.KarelRuntimeError,'registration'):rt.cancel_file(task._state,h)
        self.assertFalse(h._read_operation['cancelled']);bank._reads[id(h)]=record;rt.cancel_file(task._state,h);project.scheduler.run()

    def test_cancellation_keeps_captured_targets_and_formats_once(self):
        bank,ctx=serial(b'17');routines='ROUTINE width:INTEGER BEGIN count=count+1 RETURN 3 END width'
        def sleeper(_):rt.cancel_file(task._state,task._state.values['F'])
        task,_=compile_program(OPEN+'count=0 n=77 READ f(n::width())'+FINISH,decl=DECL,routines=routines,context=ctx,sleep=sleeper)
        self.assertEqual((task.run()['N'],task.snapshot()['COUNT'],task.snapshot()['S']),(77,1,6))

    def test_read_kb_cancellation_unwinds_with_portable_status(self):
        ctx=keyboard_context(events=[dict(key='a',at_ms=100)])
        def sleeper(_):rt.cancel_file(task._state,task._state.values['F'])
        task,_=compile_program("OPEN FILE f('RO','KB:TPKB') READ_KB(f,text,16,KC_DISPLAY,KC_ENTER_KEY,200,'',n,m,s)",decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual(task.run()['S'],6);self.assertEqual(task.snapshot()['TEXT'],{'uninitialized':True})
        self.assertEqual(ctx.keyboard._active,{});ctx.keyboard.close(task._state.values['F'])

    def test_independent_root_readers_keep_their_own_operations(self):
        bank=rt.SerialStreams({2:dict(wait=True,input=b'17'),3:dict(wait=True,input=b'29')});ctx=rt.ExecutionContext(serial_streams=bank)
        project=translate_project({name:source(name.upper(),OPEN.replace('P2:',endpoint)+'n=77 READ f(n,CR)'+FINISH,decl=DECL) for name,endpoint in [('main','P2:'),('other','P3:')]}).instantiate(context=ctx)
        project.scheduler.start('MAIN');project.scheduler.start('OTHER')
        for _ in range(100):
            project.scheduler.step()
            if len(bank._pending)==2:break
        self.assertEqual(len(bank._pending),2);main=project.programs['MAIN'];other=project.programs['OTHER']
        rt.cancel_file(main._state,main._state.values['F']);bank.feed(3,b'\n');project.scheduler.run()
        self.assertEqual((main.snapshot()['N'],main.snapshot()['S'],other.snapshot()['N'],other.snapshot()['S']),(77,6,29,0))
        self.assertEqual(bank.snapshot()[2]['input'],b'17');self.assertEqual(bank._pending,{})

    def test_cancel_then_close_in_same_handler_is_busy_until_read_unwinds(self):
        bank,ctx=serial()
        def sleeper(_):task._state.set('FLAG',True)
        body='flag=FALSE CONDITION[1]: WHEN flag DO CANCEL FILE f CLOSE FILE f ENDCONDITION ENABLE CONDITION[1] '+OPEN+'READ f(n)'
        task,_=compile_program(body,decl=DECL,context=ctx,sleep=sleeper)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'pending READ'):task.run()
        h=task._state.values['F'];self.assertIsNone(h._read_operation);self.assertEqual(bank._pending,{});bank.close(h)

    def test_cancel_then_handler_abort_does_not_publish_or_continue(self):
        bank,ctx=serial()
        def sleeper(_):task._state.set('FLAG',True)
        body='flag=FALSE CONDITION[1]: WHEN flag DO CANCEL FILE f ABORT ENDCONDITION ENABLE CONDITION[1] '+OPEN+'n=77 READ f(n)'+FINISH
        task,_=compile_program(body,decl=DECL,context=ctx,sleep=sleeper)
        with self.assertRaises(rt.KarelAbort):task.run()
        self.assertEqual(task.snapshot()['N'],77);self.assertIsNone(task._state.values['F']._read_operation);bank.close(task._state.values['F'])

    def test_cancelled_keyboard_read_can_retry_buffered_input(self):
        ctx=keyboard_context(events=[dict(key='a'),dict(key='b'),dict(key='c',at_ms=100)]);calls=[]
        def sleeper(_):
            calls.append(1)
            if len(calls)==1:rt.cancel_file(task._state,task._state.values['F'])
        task,_=compile_program("SET_FILE_ATR(f,ATR_PASSALL) OPEN FILE f('RO','KB:TPKB') text='old' READ f(text::4) s=IO_STATUS(f) READ f(text::3) CLOSE FILE f",decl=DECL,context=ctx,sleep=sleeper)
        self.assertEqual((task.run()['TEXT'],task.snapshot()['S']),('abc',6));self.assertEqual(len(task.read_requests),1)


if __name__=='__main__':unittest.main()
