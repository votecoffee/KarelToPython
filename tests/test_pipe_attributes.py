"""Authored opt-in circular pipe waiting, snapshots and overflow recovery."""
import json
import struct
import unittest
from unittest.mock import patch

from karel2py import fileops, runtime as rt, translate_project
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


DECL='f:FILE n,m,s:INTEGER text:STRING[16]'
WAIT="SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','PIP:LOG')"
SNAP="SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_NOTUSED) OPEN FILE f('RO','PIP:LOG')"


def bank(data=b'',record_size=0):
    result=rt.FilePipes();result.configure('LOG',False,1,record_size,'',0)
    result.feed('LOG',data);return result


def handle(files,*,wait=None,overflow=None,mode='RO'):
    result=rt.FileHandle();result.pipe_wait=wait;result.pipe_overflow=overflow
    files.open_for(None,result,mode,'PIP:LOG');return result


def waiting_project(files,body=WAIT+' n=77 READ f(n,CR) CLOSE FILE f',decl=DECL):
    result=translate_project({'main':source('MAIN',body,decl=decl)}).instantiate(
        context=rt.ExecutionContext(file_pipes=files))
    result.scheduler.start('MAIN')
    for _ in range(30):
        result.scheduler.step()
        if files._reads:return result
    raise AssertionError('Pipe read did not enter waiting state')


class PipeWaitingTests(unittest.TestCase):
    def test_handler_can_read_ready_data_but_cannot_wait(self):
        routines='ROUTINE collect BEGIN READ f(n,CR) END collect'
        body=WAIT+' n=77 CONDITION[1]: WHEN TRUE DO collect ENDCONDITION ENABLE CONDITION[1] m=1 CLOSE FILE f'
        for ready in (True,False):
            with self.subTest(ready=ready):
                files=bank(b'17\n' if ready else b'')
                calls=[]
                task,_=compile_program(body,decl=DECL,routines=routines,context=rt.ExecutionContext(file_pipes=files),sleep=calls.append)
                if ready:
                    self.assertEqual(task.run()['N'],17)
                else:
                    with self.assertRaisesRegex(rt.KarelRuntimeError,'Pending pipe READ.*handler'):task.run()
                    handle=task._state.values['F']
                    self.assertEqual((task.snapshot()['N'],handle.position,task.read_requests),(77,0,()))
                    files.close(handle)
                self.assertEqual((calls,files._reads),([],{}))

    def test_complete_data_uses_no_sleeper(self):
        files=bank(b'42\n');calls=[]
        data=run(WAIT+' READ f(n,CR) CLOSE FILE f',decl=DECL,
                 context=rt.ExecutionContext(file_pipes=files),sleep=lambda delay:calls.append(delay))
        self.assertEqual((data['N'],calls),(42,[]));self.assertEqual(files._reads,{})

    def test_standalone_wait_requires_explicit_sleeper(self):
        files=bank();program,_=compile_program(WAIT+' n=77 READ f(n)',decl=DECL,
                                              context=rt.ExecutionContext(file_pipes=files))
        with patch('time.sleep',side_effect=AssertionError('Real sleep must not run')):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit sleeper'):program.run()
        self.assertEqual((program.snapshot()['N'],program.snapshot()['F']['position']),(77,0))
        self.assertEqual(files._reads,{})

    def test_fragmented_numeric_input_preserves_outputs_until_delimiter(self):
        files=bank();chunks=[b'1',b'2',b'\n'];calls=[]
        def sleeper(delay):
            calls.append(delay)
            self.assertEqual(program.snapshot()['N'],77)
            self.assertEqual(program.snapshot()['F']['position'],0)
            self.assertEqual(program.read_requests,())
            files.feed('LOG',chunks.pop(0))
        program,_=compile_program(WAIT+' n=77 READ f(n,CR) CLOSE FILE f',decl=DECL,
                                  context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        self.assertEqual(program.run()['N'],12)
        self.assertEqual(calls,[.01,.01,.01]);self.assertEqual(len(program.read_requests),1)
        self.assertEqual(program.read_requests[0]['adapter_outcome'],'callback_completed')

    def test_multiple_outputs_wait_for_complete_transaction(self):
        files=bank(b'12 ');calls=[]
        def sleeper(delay):
            calls.append(delay);self.assertEqual((program.snapshot()['N'],program.snapshot()['M']),(77,88))
            self.assertEqual(program.snapshot()['F']['position'],0);files.feed('LOG',b'34\n')
        program,_=compile_program(WAIT+' n=77 m=88 READ f(n,m,CR) CLOSE FILE f',decl=DECL,
                                  context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        data=program.run();self.assertEqual((data['N'],data['M'],calls),(12,34,[.01]))

    def test_unformatted_string_waits_for_terminator(self):
        files=bank(b'ab');calls=[]
        def sleeper(delay):calls.append(delay);files.feed('LOG',b'cd\n')
        data=run(WAIT+' READ f(text,CR) CLOSE FILE f',decl=DECL,
                 context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        self.assertEqual((data['TEXT'],calls),('abcd',[.01]))

    def test_fixed_width_string_can_finish_without_terminator(self):
        files=bank(b'abc');data=run(WAIT+' READ f(text::3) CLOSE FILE f',decl=DECL,
                                  context=rt.ExecutionContext(file_pipes=files))
        self.assertEqual(data['TEXT'],'abc')

    def test_fixed_width_with_cr_waits_for_record_terminator(self):
        files=bank(b'abc');calls=[]
        def sleeper(delay):calls.append(delay);files.feed('LOG',b'\n')
        data=run(WAIT+' READ f(text::3,CR) CLOSE FILE f',decl=DECL,
                 context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        self.assertEqual((data['TEXT'],calls),('abc',[.01]))

    def test_fixed_width_field_waits_for_remaining_characters(self):
        files=bank(b'1');calls=[]
        def sleeper(delay):calls.append(delay);files.feed('LOG',b'23')
        data=run(WAIT+' READ f(n::3) CLOSE FILE f',decl=DECL,
                 context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        self.assertEqual((data['N'],calls),(123,[.01]))

    def test_closed_quoted_string_can_finish_without_delimiter(self):
        data=run(WAIT+' READ f(text::0::2) CLOSE FILE f',decl=DECL,
                 context=rt.ExecutionContext(file_pipes=bank(b"'alpha'")))
        self.assertEqual(data['TEXT'],'alpha')

    def test_partial_quoted_string_waits_for_closing_quote(self):
        files=bank(b"'al");calls=[]
        def sleeper(delay):calls.append(delay);files.feed('LOG',b"pha'")
        data=run(WAIT+' READ f(text::0::2) CLOSE FILE f',decl=DECL,
                 context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        self.assertEqual((data['TEXT'],calls),('alpha',[.01]))

    def test_malformed_complete_field_fails_without_waiting(self):
        files=bank(b'12 wrong\n');calls=[]
        program,_=compile_program(WAIT+' n=77 m=88 READ f(n,m,CR)',decl=DECL,
                                  context=rt.ExecutionContext(file_pipes=files),sleep=lambda delay:calls.append(delay))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'invalid INTEGER'):program.run()
        self.assertEqual((program.snapshot()['N'],program.snapshot()['M'],program.snapshot()['F']['position']),(77,88,0))
        self.assertEqual((calls,program.read_requests,files._reads),([],(),{}))

    def test_non_ascii_text_fails_without_consuming(self):
        files=bank(b'\xff\n');program,_=compile_program(WAIT+' READ f(text)',decl=DECL,
                                                    context=rt.ExecutionContext(file_pipes=files))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ASCII'):program.run()
        self.assertEqual(program.snapshot()['F']['position'],0);self.assertEqual(files._reads,{})

    def test_custom_eol_is_a_completion_boundary(self):
        files=bank(b'41');calls=[]
        def sleeper(delay):calls.append(delay);files.feed('LOG',b';')
        data=run('SET_FILE_ATR(f,ATR_EOL,59) '+WAIT+' READ f(n,CR) CLOSE FILE f',decl=DECL,
                 context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        self.assertEqual((data['N'],calls),(41,[.01]))

    def test_binary_fields_wait_until_all_bytes_arrive(self):
        files=bank(struct.pack('<i',17));calls=[]
        def sleeper(delay):
            calls.append(delay);self.assertEqual((program.snapshot()['N'],program.snapshot()['M']),(77,88))
            self.assertEqual(program.snapshot()['F']['position'],0);files.feed('LOG',struct.pack('<i',29))
        program,_=compile_program(WAIT.replace("'RO'","'RB'")+' n=77 m=88 READ f(n,m) CLOSE FILE f',
                                  decl=DECL,context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        data=program.run();self.assertEqual((data['N'],data['M'],calls),(17,29,[.01]))
        self.assertEqual(len(program.read_requests),1)

    def test_binary_reverse_and_string_widths(self):
        files=bank(struct.pack('>i',23)+b'abc')
        data=run('SET_FILE_ATR(f,ATR_REVERSE) '+WAIT.replace("'RO'","'RB'")+
                 ' READ f(n,text::3) CLOSE FILE f',decl=DECL,context=rt.ExecutionContext(file_pipes=files))
        self.assertEqual((data['N'],data['TEXT']),(23,'abc'))

    def test_atomic_binary_read_cannot_exceed_pipe_capacity(self):
        files=bank();decl='f:FILE a,b,c,d,e:STRING[254]'
        program,_=compile_program(WAIT.replace("'RO'","'RB'")+' READ f(a,b,c,d,e)',decl=decl,
                                  context=rt.ExecutionContext(file_pipes=files))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):program.run()
        self.assertEqual(files._reads,{})

    def test_impossible_waiting_text_read_rejects_before_sleeper_or_publication(self):
        for body in ('READ f(a::254,b::254,c::254,d::254,e::254)',
                     'READ f(a::254,b::254,c::254,d::254,e::8,CR)',
                     'READ f(a,b,c,d,e)'):
            with self.subTest(body=body):
                files=bank();calls=[]
                setup='SET_FILE_ATR(f,ATR_FIELD) ' if body=='READ f(a,b,c,d,e)' else ''
                program,_=compile_program(setup+WAIT+" a='old' "+body,decl='f:FILE a,b,c,d,e:STRING[254]',
                    context=rt.ExecutionContext(file_pipes=files),sleep=calls.append)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):program.run()
                self.assertEqual((program.snapshot()['A'],program._state.values['F'].position),('old',0))
                self.assertEqual((calls,files._reads),([],{}))

    def test_exact_capacity_text_with_cr_completes(self):
        files=bank(b'a'*1016+b'1234567\n')
        data=run(WAIT+' READ f(a::254,b::254,c::254,d::254,e::7,CR) CLOSE FILE f',
                 decl='f:FILE a,b,c,d,e:STRING[254]',context=rt.ExecutionContext(file_pipes=files))
        self.assertEqual(data['E'],'1234567')

    def test_target_and_format_expressions_are_captured_once(self):
        files=bank();calls=[]
        def sleeper(delay):calls.append(delay);files.feed('LOG',b'123')
        routines='ROUTINE slot:INTEGER BEGIN count=count+1 RETURN 1 END slot ROUTINE columns:INTEGER BEGIN count=count+1 RETURN 3 END columns'
        data=run(WAIT+' count=0 READ f(a[slot()]::columns()) CLOSE FILE f',
                 decl='f:FILE count:INTEGER a:ARRAY[1]OF INTEGER',routines=routines,
                 context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        self.assertEqual((data['A'],data['COUNT'],calls),([123],2,[.01]))


class PipeSnapshotAndOverflowTests(unittest.TestCase):
    def test_explicit_snapshot_excludes_later_appends(self):
        files=bank(b'one');reader=handle(files,wait=0);files.feed('LOG',b'two')
        self.assertEqual(files.bytes_ahead(reader),3)
        self.assertEqual(files.read_bytes(reader,3),b'one')
        self.assertEqual(files.bytes_ahead(reader),0)
        with self.assertRaises(rt.KarelRuntimeError):files.read_bytes(reader,1)
        files.close(reader);reader=handle(files,wait=0)
        self.assertEqual(files.bytes_ahead(reader),6);files.close(reader)

    def test_snapshot_source_availability_obeys_open_boundary(self):
        files=bank(b'one\n');calls=[]
        def sleeper(delay):calls.append(delay);files.feed('LOG',b'two\n')
        data=run(SNAP+' DELAY 1 BYTES_AHEAD(f,n,s) m=BYTES_LEFT(f) READ f(text,CR) CLOSE FILE f',
                 decl=DECL,context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        self.assertEqual((data['N'],data['M'],data['TEXT']),(4,4,'one'))

    def test_snapshot_seek_to_end_uses_captured_boundary(self):
        files=bank(b'one\n')
        def sleeper(delay):files.feed('LOG',b'two\n')
        data=run(SNAP+' DELAY 1 SET_FILE_POS(f,-1,s) n=GET_FILE_POS(f) m=BYTES_LEFT(f) CLOSE FILE f',
                 decl=DECL,context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        self.assertEqual((data['N'],data['M'],data['S']),(4,0,0))

    def test_snapshot_seek_beyond_boundary_rejects_even_if_live_bytes_exist(self):
        files=bank(b'one\n');reader=handle(files,wait=0);files.feed('LOG',b'two\n')
        self.assertEqual(files.seek(reader,5),2);self.assertEqual(reader.position,0)
        self.assertEqual(files.seek(reader,-2),2);self.assertEqual(reader.position,0)
        self.assertEqual(files.seek(reader,4),0);self.assertEqual(reader.position,4)
        files.close(reader)

    def test_overflow_eof_cannot_be_cleared_by_seeking(self):
        files=bank(b'a'*1024);reader=handle(files,overflow=-1);files.feed('LOG',b'b')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overflow'):files.seek(reader,0)
        files.close(reader)

    def test_snapshot_eof_does_not_wait(self):
        files=bank();calls=[]
        program,_=compile_program(SNAP+' n=77 READ f(n)',decl=DECL,
                                  context=rt.ExecutionContext(file_pipes=files),sleep=lambda delay:calls.append(delay))
        with self.assertRaises(rt.KarelRuntimeError):program.run()
        self.assertEqual((calls,program.snapshot()['N'],files._reads),([],77,{}))

    def test_absent_attributes_keep_legacy_live_reads_and_cursor_clamping(self):
        files=bank(b'a'*1024);reader=handle(files);files.feed('LOG',b'b')
        self.assertEqual((reader.position,files.read_bytes(reader,1)),(0,b'a'))
        files.feed('LOG',b'c');self.assertEqual(files.read_bytes(reader,1),b'a');files.close(reader)

    def test_wait_attr_alone_uses_explicit_overflow_eof_policy(self):
        files=bank(b'a'*1024);reader=handle(files,wait=1);files.feed('LOG',b'b')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overflow'):files.bytes_ahead(reader)
        self.assertEqual(reader.status,1);files.close(reader)

    def test_explicit_ovf_eof_is_sticky_until_reopen(self):
        files=bank(b'a'*1024);reader=handle(files,overflow=-1);files.feed('LOG',b'b')
        for _ in range(2):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'overflow'):files.read_bytes(reader,1)
        files.close(reader);reader=handle(files,overflow=-1)
        self.assertEqual(files.read_bytes(reader,1),b'a');files.close(reader)

    def test_consumed_prefix_overwrite_does_not_signal_overflow(self):
        files=bank(b'a'*1024);reader=handle(files,overflow=-1)
        files.read_bytes(reader,5);files.feed('LOG',b'12345')
        self.assertEqual(reader.position,0);self.assertEqual(files.read_bytes(reader,1),b'a');files.close(reader)

    def test_zero_advance_reads_new_oldest_byte(self):
        files=bank(b'a'*1024);reader=handle(files,overflow=0);files.feed('LOG',b'bc')
        self.assertEqual((reader.position,files.read_bytes(reader,1)),(0,b'a'));files.close(reader)

    def test_positive_advance_is_relative_to_new_oldest(self):
        files=bank(b'a'*1024);reader=handle(files,overflow=7);files.feed('LOG',b'bc')
        self.assertEqual(reader.position,7);self.assertEqual(files.bytes_ahead(reader),1017);files.close(reader)

    def test_advance_rounds_up_to_binary_record_size(self):
        files=bank(b'a'*1024,record_size=16);reader=handle(files,overflow=17)
        self.assertEqual(reader._pipe_advance,32);files.feed('LOG',b'b')
        self.assertEqual(reader.position,32);files.close(reader)

    def test_full_capacity_advance_can_wait_for_future_data(self):
        files=bank(b'a'*1024);reader=handle(files,overflow=1024);files.feed('LOG',b'b')
        self.assertEqual((reader.position,files.bytes_ahead(reader)),(1024,0))
        files.feed('LOG',b'c');self.assertEqual(files.bytes_ahead(reader),1);files.close(reader)

    def test_snapshot_end_moves_with_dropped_prefix(self):
        files=bank(b'a'*1020);reader=handle(files,wait=0,overflow=0);files.read_bytes(reader,10)
        files.feed('LOG',b'12345678')
        self.assertEqual((reader.position,reader._pipe_snapshot_end,files.bytes_ahead(reader)),(6,1016,1010))
        files.close(reader)

    def test_each_reader_has_its_own_overflow_policy(self):
        files=bank(b'a'*1024);eof=handle(files,overflow=-1);advance=handle(files,overflow=16);legacy=handle(files)
        files.feed('LOG',b'b')
        self.assertEqual((advance.position,legacy.position),(16,0))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overflow'):files.bytes_ahead(eof)
        for item in (eof,advance,legacy):files.close(item)

    def test_invalid_handle_configurations_fail_before_open(self):
        for wait,overflow in ((2,None),(True,None),(None,-2),(None,1025),(None,True)):
            with self.subTest(wait=wait,overflow=overflow):
                files=bank(b'prior');reader=rt.FileHandle();reader.pipe_wait=wait;reader.pipe_overflow=overflow
                with self.assertRaises(rt.KarelRuntimeError):files.open_for(None,reader,'RW','PIP:LOG')
                self.assertIsNone(reader.owner);self.assertEqual(files.files['PIP:LOG'],b'prior')
                self.assertEqual(files.handles,[])

    def test_rounded_advance_beyond_capacity_fails_before_open(self):
        files=bank(record_size=100);reader=rt.FileHandle();reader.pipe_overflow=1024
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Rounded'):files.open_for(None,reader,'RO','PIP:LOG')
        self.assertIsNone(reader.owner)

    def test_read_attributes_reject_write_only_modes_before_truncation(self):
        for mode in ('WO','AP'):
            files=bank(b'prior')
            with self.assertRaisesRegex(rt.KarelRuntimeError,'readable'):handle(files,wait=1,mode=mode)
            self.assertEqual(files.files['PIP:LOG'],b'prior')

    def test_source_overflow_preserves_outputs(self):
        files=bank(b'a'*1024)
        def sleeper(delay):files.feed('LOG',b'b')
        program,_=compile_program("SET_FILE_ATR(f,ATR_PIPOVADV,OVF_EOF) OPEN FILE f('RB','PIP:LOG') n=77 DELAY 1 READ f(n)",
                                  decl=DECL,context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overflow'):program.run()
        self.assertEqual((program.snapshot()['N'],program.snapshot()['F']['position']),(77,0))
        self.assertEqual(files._reads,{})

    def test_feed_rejects_unconfigured_or_invalid_bytes_without_mutation(self):
        files=bank(b'prior');before=files.snapshot()
        for name,data in (('MISSING',b'x'),('../LOG',b'x'),('LOG',{'hex':'0'})):
            with self.subTest(name=name,data=data),self.assertRaises((ValueError,rt.KarelRuntimeError)):files.feed(name,data)
        self.assertEqual(files.snapshot(),before)


class PipePendingOverflowTests(unittest.TestCase):
    def test_pending_read_can_advance_after_full_overwrite(self):
        files=bank(b' '*1024)
        waits=[]
        replacement=b' '*16+b'37\n'+b' '*(1024-19)

        def sleep(seconds):
            waits.append(seconds)
            files.feed('LOG',replacement)
            self.assertEqual(task._state.values['F'].position,16)

        task,_=compile_program(
            'SET_FILE_ATR(f,ATR_PIPOVADV,16) '+WAIT+' READ f(n,CR)',decl=DECL,
            context=rt.ExecutionContext(file_pipes=files),sleep=sleep,
        )
        values=task.run()
        self.assertEqual((values['N'],values['F']['position'],waits),(37,19,[.01]))
        self.assertEqual(len(task.read_requests),1)
        self.assertEqual(files._reads,{})

    def test_pending_read_tracks_overwrite_of_consumed_prefix(self):
        files=bank(b' '*1024)
        task,_=compile_program(
            WAIT+' SET_FILE_POS(f,1000,s) READ f(n,CR)',decl=DECL,
            context=rt.ExecutionContext(file_pipes=files),sleep=lambda _:files.feed('LOG',b'17\n'),
        )
        values=task.run()
        self.assertEqual((values['N'],values['F']['position']),(17,1024))
        self.assertFalse(task._state.values['F']._pipe_overflowed)

    def test_cancel_after_authorized_advance_keeps_targets_and_allows_next_read(self):
        files=bank(b' '*1024)

        def sleep(_):
            files.feed('LOG',b' '*16+b'17\n'+b' '*(1024-19))
            rt.cancel_file(task._state,task._state.values['F'])

        task,_=compile_program(
            'SET_FILE_ATR(f,ATR_PIPOVADV,16) '+WAIT+
            ' n=77 READ f(n,CR) s=IO_STATUS(f) READ f(m,CR)',decl=DECL,
            context=rt.ExecutionContext(file_pipes=files),sleep=sleep,
        )
        values=task.run()
        self.assertEqual((values['N'],values['M'],values['S']),(77,17,6))
        self.assertEqual(len(task.read_requests),1)
        self.assertEqual(files._reads,{})

    def test_writer_does_not_authorize_a_forged_pending_cursor(self):
        files=bank(b' '*1024)

        def sleep(_):
            task._state.values['F'].position=1
            files.feed('LOG',b' ')

        task,_=compile_program(
            WAIT+' n=77 READ f(n,CR)',decl=DECL,
            context=rt.ExecutionContext(file_pipes=files),sleep=sleep,
        )
        with self.assertRaisesRegex(rt.KarelRuntimeError,'registration, binding or cursor changed'):
            task.run()
        self.assertEqual((task.snapshot()['N'],task.snapshot()['F']['position']),(77,0))
        self.assertEqual(files._reads,{})

    def test_same_size_overwrite_during_capture_rejects_both_read_paths(self):
        initial=b'17\n'+b' '*(1024-3)
        replacement=b'18\n'+b' '*(1024-3)
        for opening in ("OPEN FILE f('RO','PIP:LOG')",'SET_FILE_ATR(f,ATR_PIPOVADV,0) '+WAIT):
            with self.subTest(opening=opening):
                files=bank(initial)
                task,_=compile_program(
                    opening+' n=77 READ f(n,CR)',decl=DECL,
                    context=rt.ExecutionContext(file_pipes=files),
                )
                charge=fileops.charge_file_bytes

                def overwrite(size,check):
                    charge(size,check)
                    files.feed('LOG',replacement)

                with patch.object(fileops,'charge_file_bytes',side_effect=overwrite):
                    with self.assertRaisesRegex(rt.KarelRuntimeError,'changed during'):
                        task.run()
                self.assertEqual((task.snapshot()['N'],task.snapshot()['F']['position']),(77,0))
                self.assertEqual(files.files['PIP:LOG'],replacement)
                self.assertEqual(task.read_requests,())
                self.assertEqual(files._reads,{})

    def test_cancel_finite_read_without_attributes_preserves_history(self):
        files=bank(b'17\n')
        task,_=compile_program(
            "OPEN FILE f('RO','PIP:LOG') n=77 READ f(n,CR) s=IO_STATUS(f)",decl=DECL,
            context=rt.ExecutionContext(file_pipes=files),
        )
        charge=fileops.charge_file_bytes

        def cancel(size,check):
            charge(size,check)
            rt.cancel_file(task._state,task._state.values['F'])

        with patch.object(fileops,'charge_file_bytes',side_effect=cancel):
            values=task.run()
        self.assertEqual((values['N'],values['S'],values['F']['position']),(77,6,0))
        self.assertEqual(files.files['PIP:LOG'],b'17\n')

    def test_direct_typed_read_respects_snapshot_end(self):
        files=bank(b'17')
        channel=handle(files,wait=0)
        files.feed('LOG',b'9\n')
        state=rt.State({'N':('INTEGER',)},{})
        state.file_read(channel,[state.reference('N')])
        self.assertEqual((state.get('N'),channel.position),(17,2))
        files.close(channel)

    def test_direct_reads_cannot_consume_an_active_wait(self):
        files=bank()

        def sleep(_):
            channel=task._state.values['F']
            with self.assertRaisesRegex(rt.KarelRuntimeError,'active READ'):
                files.read_bytes(channel,0)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'active READ'):
                task._state.file_read(channel,[task._state.reference('N')])
            files.feed('LOG',b'17\n')

        task,_=compile_program(
            WAIT+' READ f(n,CR)',decl=DECL,
            context=rt.ExecutionContext(file_pipes=files),sleep=sleep,
        )
        self.assertEqual(task.run()['N'],17)
        self.assertEqual(len(task.read_requests),1)


class PipeSchedulingAndLifetimeTests(unittest.TestCase):
    def test_linked_routine_inherits_explicit_standalone_sleeper(self):
        files=bank();calls=[]
        def sleeper(delay):calls.append(delay);files.feed('LOG',b'61\n')
        routine='ROUTINE consume:INTEGER BEGIN '+WAIT+' READ f(n,CR) CLOSE FILE f RETURN n END consume'
        project=translate_project({'main':source('MAIN','n=consume()',routines='ROUTINE consume:INTEGER FROM LIB'),
            'lib':source('LIB','',decl=DECL,routines=routine)}).instantiate(
                context=rt.ExecutionContext(file_pipes=files),options={'sleep':sleeper})
        self.assertEqual(project.programs['MAIN'].run()['N'],61)
        self.assertEqual((calls,files._reads),([.01],{}))

    def test_same_task_program_call_inherits_explicit_standalone_sleeper(self):
        files=bank();calls=[]
        def sleeper(delay):calls.append(delay);files.feed('LOG',b'73\n')
        project=translate_project({'main':source('MAIN',"CALL_PROG('WORKER',s)"),
            'worker':source('WORKER',WAIT+' READ f(n,CR) CLOSE FILE f',decl=DECL)}).instantiate(
                context=rt.ExecutionContext(file_pipes=files),options={'sleep':sleeper})
        project.programs['MAIN'].run()
        self.assertEqual(project.programs['WORKER'].snapshot()['N'],73)
        self.assertEqual((calls,files._reads),([.01],{}))

    def test_nested_calls_preserve_absent_sleeper_provenance(self):
        for kind in ('routine','program'):
            with self.subTest(kind=kind):
                files=bank()
                if kind=='routine':
                    routine='ROUTINE consume BEGIN '+WAIT+' READ f(n,CR) END consume'
                    sources={'main':source('MAIN','consume()',routines='ROUTINE consume FROM LIB'),
                             'lib':source('LIB','',decl=DECL,routines=routine)}
                else:sources={'main':source('MAIN',"CALL_PROG('LIB',s)"),'lib':source('LIB',WAIT+' READ f(n,CR)',decl=DECL)}
                project=translate_project(sources).instantiate(context=rt.ExecutionContext(file_pipes=files))
                with patch('time.sleep',side_effect=AssertionError('Real sleep must not run')):
                    with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit sleeper'):project.programs['MAIN'].run()
                self.assertEqual(files._reads,{})

    def test_sibling_producer_unblocks_consumer_without_polling_source(self):
        files=bank();ctx=rt.ExecutionContext(file_pipes=files)
        project=translate_project({'main':source('MAIN',"RUN_TASK('CONSUMER',0,FALSE,FALSE,0,s) RUN_TASK('PRODUCER',0,FALSE,FALSE,0,s)"),
            'consumer':source('CONSUMER',WAIT+' READ f(n,CR) CLOSE FILE f',decl=DECL),
            'producer':source('PRODUCER',"DELAY 20 OPEN FILE f('AP','PIP:LOG') WRITE f('37',CR) CLOSE FILE f",decl='f:FILE')}).instantiate(context=ctx)
        with patch('time.sleep',side_effect=AssertionError('Scheduler must not sleep')):result=project.run('MAIN')
        self.assertEqual(result['CONSUMER']['values']['N'],37)
        self.assertTrue(all(row['state']=='completed' for row in result.values()));self.assertEqual(files._reads,{})

    def test_pause_retains_pending_read_then_resume_publishes_once(self):
        files=bank();project=waiting_project(files);program=project.programs['MAIN'];program.pause()
        for _ in range(30):
            project.scheduler.step()
            if program.task_state=='paused':break
        self.assertEqual(program.task_state,'paused');self.assertEqual(len(files._reads),1)
        files.feed('LOG',b'52\n');self.assertEqual(program.snapshot()['N'],77)
        project.scheduler.continue_task('MAIN');result=project.scheduler.run()
        self.assertEqual(result['MAIN']['values']['N'],52);self.assertEqual(len(program.read_requests),1)
        self.assertEqual(files._reads,{})

    def test_stop_cleans_pending_registration_without_consuming_bytes(self):
        files=bank(b'1');project=waiting_project(files);program=project.programs['MAIN']
        project.scheduler.stop('MAIN')
        self.assertEqual(files._reads,{});self.assertEqual(files.files['PIP:LOG'],b'1')
        self.assertEqual((program.snapshot()['N'],program.snapshot()['F']['position']),(77,0))
        self.assertEqual(program.read_requests,())

    def test_budget_failure_cleans_pending_registration(self):
        files=bank();project=waiting_project(files);program=project.programs['MAIN']
        program._state.max_steps=program._state.steps+2
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):project.scheduler.run(max_cycles=100)
        self.assertEqual(files._reads,{});self.assertEqual(program.snapshot()['F']['position'],0)

    def test_sleeper_failure_cleans_pending_registration(self):
        files=bank()
        def sleeper(delay):raise ValueError('scripted failure')
        program,_=compile_program(WAIT+' READ f(n)',decl=DECL,
                                  context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'scripted failure'):program.run()
        self.assertEqual(files._reads,{})

    def test_close_during_wait_fails_busy_and_cleans_registration(self):
        files=bank()
        def sleeper(delay):files.close(program._state.values['F'])
        program,_=compile_program(WAIT+' READ f(n)',decl=DECL,
                                  context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'active READ'):program.run()
        self.assertEqual(files._reads,{})
        self.assertIs(program._state.values['F'].owner,files)
        files.close(program._state.values['F'])

    def test_seek_during_wait_fails_busy_and_preserves_pending_cursor(self):
        files=bank()
        def sleeper(delay):files.seek(program._state.values['F'],-1)
        program,_=compile_program(WAIT+' n=77 READ f(n)',decl=DECL,
                                  context=rt.ExecutionContext(file_pipes=files),sleep=sleeper)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'active READ'):program.run()
        self.assertEqual((program.snapshot()['N'],program.snapshot()['F']['position']),(77,0))
        self.assertEqual(files._reads,{})
        files.close(program._state.values['F'])

    def test_suspended_read_not_serialized_and_closed_values_roundtrip(self):
        files=bank();project=waiting_project(files);context=project.context
        with self.assertRaisesRegex(ValueError,'live'):context.to_config()
        project.scheduler.stop('MAIN');project.programs['MAIN']._state.file_close(project.programs['MAIN']._state.values['F'])
        config=json.loads(json.dumps(context.to_config()))
        self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)
        restored=rt.ExecutionContext.from_config(config).file_pipes
        self.assertEqual(restored._reads,{})

    def test_non_pipe_backend_rejects_pipe_attributes(self):
        program,_=compile_program("SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','x')",decl=DECL,
                                  context=rt.ExecutionContext(files=rt.MemoryFiles({'x':'1'})))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'plain.*pipe|plain.*PIP|plain.*FilePipes'):program.run()


if __name__=='__main__':unittest.main()
