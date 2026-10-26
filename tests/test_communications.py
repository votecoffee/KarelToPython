"""Authored offline socket/FILE behavior and circular plain-pipe regressions."""
from copy import deepcopy
import json
import struct
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


DECL='f,g:FILE n,m,s,available:INTEGER text:STRING[16]'
CONFIG="PIPE_CONFIG('PIP:LOG.DAT',FALSE,1,0,'',0,s)"


def socket_context(data='42\n',**options):
    return rt.ExecutionContext(messaging=rt.Messaging({'S1:':{'input':data}},**options))


def pipe_context(*,limit=16*1024*1024):return rt.ExecutionContext(file_pipes=rt.FilePipes(limit=limit))


def pipe_handle(bank,mode='RW',name='PIP:LOG.DAT'):
    handle=rt.FileHandle();bank.open_for(None,handle,mode,name);return handle


class MessagingTests(unittest.TestCase):
    def test_connect_read_write_disconnect_uses_separate_rx_and_tx(self):
        ctx=socket_context()
        data=run("MSG_CONNECT('s1:',s) OPEN FILE f('RW','s1:') READ f(n,CR) WRITE f('ack',CR) CLOSE FILE f MSG_DISCO('S1:',s)",decl=DECL,context=ctx)
        self.assertEqual((data['N'],data['S']),(42,0))
        self.assertEqual(ctx.messaging.files['S1:'],b'');self.assertEqual(ctx.messaging.take_output('S1:'),b'ack\n')

    def test_mount_and_dismount_preserve_queued_bytes(self):
        bank=rt.Messaging({'C1:':{'mounted':False,'input':'in','output':'out'}});ctx=rt.ExecutionContext(messaging=bank)
        data=run("MSG_CONNECT('C1:',s) n=s MOUNT_DEV('C1:',s) MSG_CONNECT('C1:',s) MSG_DISCO('C1:',s) DISMOUNT_DEV('C1:',s)",decl=DECL,context=ctx)
        self.assertEqual((data['N'],data['S']),(4,0));self.assertFalse(bank.ports['C1:']['mounted'])
        self.assertEqual(bank.files['C1:'],b'in');self.assertEqual(bank.take_output('C1:'),b'out')

    def test_unknown_invalid_unavailable_and_repeat_connect(self):
        bank=rt.Messaging({'S1:':{'available':False},'C1:':{'input':'x'}});ctx=rt.ExecutionContext(messaging=bank)
        for tag,code in (('S2:',1),('S9:',2),('C1',2),('S1:',4)):
            self.assertEqual(run(f"MSG_CONNECT('{tag}',s)",context=ctx)['S'],code)
        self.assertEqual(run("MSG_CONNECT('C1:',s) MSG_CONNECT('C1:',s)",context=ctx)['S'],0)
        self.assertEqual(bank.files['C1:'],b'x')

    def test_ping_reads_only_supplied_results_without_network_calls(self):
        ctx=socket_context(hosts={'fixture':0,'timeout':282,'memory':283})
        with patch('socket.socket',side_effect=AssertionError('Unexpected network operation')):
            for host,code in (('FIXTURE',0),('timeout',282),('memory',283),('missing',1),('bad host',2)):
                self.assertEqual(run(f"MSG_PING('{host}',s)",context=ctx)['S'],code)

    def test_busy_disconnect_and_dismount_retain_state(self):
        ctx=socket_context();p,_=compile_program("MSG_CONNECT('S1:',s) OPEN FILE f('RW','S1:') MSG_DISCO('S1:',s) n=s DISMOUNT_DEV('S1:',s)",decl=DECL,context=ctx)
        self.assertEqual((p.run()['N'],p.snapshot()['S']),(3,3))
        self.assertTrue(ctx.messaging.ports['S1:']['connected']);p._state.file_close(p._state.values['F'])
        self.assertEqual(run("MSG_DISCO('S1:',s)",context=ctx)['S'],0)

    def test_disconnect_during_open_file_preserves_unread_text_and_outputs(self):
        ctx=socket_context();p,_=compile_program("n=77 MSG_CONNECT('S1:',s) OPEN FILE f('RW','S1:')",decl=DECL,context=ctx);p.run()
        ctx.messaging.set_available('S1:',False)
        target=p._state.reference('N')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'disconnected'):p._state.file_read(p._state.values['F'],[target])
        self.assertEqual((target.raw(),ctx.messaging.files['S1:']),(77,b'42\n'))
        p._state.file_close(p._state.values['F'])

    def test_failed_binary_read_restores_batch_and_rx_cursor(self):
        ctx=socket_context(struct.pack('<i',7));p,_=compile_program("n=77 m=88 MSG_CONNECT('S1:',s) OPEN FILE f('RWB','S1:') READ f(n,m)",decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['M'],p.snapshot()['F']['position']),(77,88,0))
        self.assertEqual(ctx.messaging.files['S1:'],struct.pack('<i',7));p._state.file_close(p._state.values['F'])

    def test_socket_write_limit_preserves_prior_output(self):
        ctx=socket_context('',limit=4);p,_=compile_program("MSG_CONNECT('S1:',s) OPEN FILE f('RW','S1:') WRITE f('full') WRITE f('x')",decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'limit'):p.run()
        self.assertEqual(ctx.messaging.take_output('S1:'),b'full');p._state.file_close(p._state.values['F'])

    def test_feed_and_output_drain_validate_before_mutation(self):
        bank=rt.Messaging({'S1:':{'input':'a','output':'bc'}},limit=5)
        bank.feed('S1:',b'de');before=bank.to_config()
        with self.assertRaises(ValueError):bank.feed('S1:',b'f')
        self.assertEqual(bank.to_config(),before)
        with self.assertRaises(ValueError):bank.take_output('S1:',3)
        self.assertEqual(bank.take_output('S1:',1),b'b');self.assertEqual(bank.take_output('S1:'),b'c')

    def test_bytes_ahead_reports_rx_independently_of_output(self):
        ctx=socket_context('12\n34\n')
        data=run("MSG_CONNECT('S1:',s) OPEN FILE f('RW','S1:') READ f(n,CR) WRITE f('ok') BYTES_AHEAD(f,available,s) READ f(m,CR) CLOSE FILE f",decl=DECL,context=ctx)
        self.assertEqual((data['N'],data['M'],data['AVAILABLE']),(12,34,3))
        self.assertEqual(ctx.messaging.take_output('S1:'),b'ok')

    def test_only_one_file_can_open_an_endpoint_and_xml_is_excluded(self):
        ctx=socket_context();p,_=compile_program("MSG_CONNECT('S1:',s) OPEN FILE f('RW','S1:') OPEN FILE g('RO','S1:')",decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'open FILE'):p.run()
        self.assertEqual(len(ctx.messaging.handles),1);p._state.file_close(p._state.values['F'])
        with self.assertRaises(rt.KarelRuntimeError):run("SET_FILE_ATR(f,ATR_XML) OPEN FILE f('RO','S1:')",decl=DECL,context=ctx)

    def test_binary_input_accepts_bytes_that_text_input_rejects(self):
        ctx=socket_context(b'\xff')
        p,_=compile_program("MSG_CONNECT('S1:',s) OPEN FILE f('RO','S1:') READ f(text)",decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ASCII'):p.run()
        p._state.file_close(p._state.values['F'])
        data=run("OPEN FILE f('RB','S1:') READ f(bytes[1]) CLOSE FILE f",decl=DECL+' bytes:ARRAY[1] OF BYTE',context=ctx)
        self.assertEqual(data['BYTES'],[255])

    def test_access_modes_preserve_input_and_output_on_invalid_operations(self):
        for mode,body in (('RO',"WRITE f('x')"),('WO','READ f(n)')):
            ctx=socket_context('42\n');ctx.messaging.ports['S1:']['output'].extend(b'prior')
            p,_=compile_program(f"n=77 MSG_CONNECT('S1:',s) OPEN FILE f('{mode}','S1:') "+body,decl=DECL,context=ctx)
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['N'],ctx.messaging.files['S1:']),(77,b'42\n'))
            self.assertEqual(ctx.messaging.take_output('S1:'),b'prior');p._state.file_close(p._state.values['F'])

    def test_host_can_explicitly_link_client_output_to_server_input(self):
        ctx=rt.ExecutionContext(messaging=rt.Messaging({'C1:':{},'S1:':{}}))
        run("MSG_CONNECT('C1:',s) MSG_CONNECT('S1:',s) OPEN FILE f('WO','C1:') WRITE f('out') CLOSE FILE f",decl=DECL,context=ctx)
        self.assertEqual(ctx.messaging.files['S1:'],b'')
        ctx.messaging.feed('S1:',ctx.messaging.take_output('C1:'))
        self.assertEqual(run("OPEN FILE f('RO','S1:') READ f(text) CLOSE FILE f",decl=DECL,context=ctx)['TEXT'],'out')


class FilePipeTests(unittest.TestCase):
    def test_pipe_config_creates_default_capacity_and_canonical_name(self):
        ctx=pipe_context();data=run("PIPE_CONFIG('pip:/log.dat',TRUE,0,0,'',0,s)",context=ctx)
        self.assertEqual(data['S'],0);self.assertEqual(ctx.file_pipes.pipes['PIP:LOG.DAT']['sectors'],8)
        self.assertEqual(ctx.file_pipes.files['PIP:LOG.DAT'],b'')

    def test_text_writer_reader_preserves_circular_history(self):
        ctx=pipe_context()
        data=run(CONFIG+" OPEN FILE f('RW','PIP:LOG.DAT') WRITE f('hello',CR) OPEN FILE g('RO','PIP:LOG.DAT') READ g(text,CR) CLOSE FILE f CLOSE FILE g",decl=DECL,context=ctx)
        self.assertEqual(data['TEXT'],'hello');self.assertEqual(ctx.file_pipes.files['PIP:LOG.DAT'],b'hello\n')

    def test_record_size_and_dictionary_are_metadata_not_write_alignment(self):
        ctx=pipe_context()
        data=run("PIPE_CONFIG('PIP:LOG.DAT',TRUE,1,128,'FORM',1,s) OPEN FILE f('RWB','PIP:LOG.DAT') WRITE f(17,23) READ f(n,m) CLOSE FILE f",decl=DECL,context=ctx)
        self.assertEqual((data['N'],data['M']),(17,23))
        self.assertEqual(ctx.file_pipes.pipes['PIP:LOG.DAT']['form_dict'],'FORM')
        self.assertEqual(ctx.file_pipes.files['PIP:LOG.DAT'],struct.pack('<ii',17,23))

    def test_independent_readers_can_read_the_same_retained_bytes(self):
        ctx=pipe_context()
        data=run(CONFIG+" OPEN FILE f('RWB','PIP:LOG.DAT') WRITE f(7) OPEN FILE g('RB','PIP:LOG.DAT') READ g(n) READ f(m) CLOSE FILE f CLOSE FILE g",decl=DECL,context=ctx)
        self.assertEqual((data['N'],data['M']),(7,7))

    def test_circular_overflow_adjusts_all_reader_cursors(self):
        bank=rt.FilePipes();self.assertEqual(bank.configure('LOG.DAT',False,1,0,'',0),0)
        writer=pipe_handle(bank);first=pipe_handle(bank,'R');second=pipe_handle(bank,'R')
        bank.write(writer,b'a'*1024);first.position=30;second.position=1000
        bank.write(writer,b'b'*100)
        self.assertEqual((first.position,second.position),(0,900))
        self.assertEqual(bank.files['PIP:LOG.DAT'],b'a'*924+b'b'*100)
        for handle in (writer,first,second):bank.close(handle)

    def test_single_write_larger_than_capacity_keeps_newest_bytes(self):
        bank=rt.FilePipes();bank.configure('LOG.DAT',False,1,0,'',0);writer=pipe_handle(bank)
        bank.write(writer,b'old'+b'n'*1024)
        self.assertEqual(bank.files['PIP:LOG.DAT'],b'n'*1024);bank.close(writer)

    def test_write_open_truncates_and_resets_reader_offsets(self):
        bank=rt.FilePipes();bank.configure('LOG.DAT',False,1,0,'',0)
        writer=pipe_handle(bank);bank.write(writer,b'old');reader=pipe_handle(bank,'R');reader.position=2;bank.close(writer)
        writer=pipe_handle(bank,'W');self.assertEqual(bank.files['PIP:LOG.DAT'],b'');self.assertEqual(reader.position,0)
        bank.close(writer);bank.close(reader)

    def test_append_and_readwrite_open_retain_existing_history(self):
        bank=rt.FilePipes();bank.configure('LOG.DAT',False,1,0,'',0)
        for mode,value in (('RW',b'a'),('A',b'b'),('RW',b'c')):
            handle=pipe_handle(bank,mode);bank.write(handle,value);bank.close(handle)
        self.assertEqual(bank.files['PIP:LOG.DAT'],b'abc')

    def test_busy_reconfigure_and_shrink_preserve_metadata_and_bytes(self):
        bank=rt.FilePipes();bank.configure('LOG.DAT',False,2,0,'',0);writer=pipe_handle(bank)
        bank.write(writer,b'a'*1500)
        self.assertEqual(bank.configure('LOG.DAT',True,3,0,'',0),3);bank.close(writer);before=bank.to_config()
        self.assertEqual(bank.configure('LOG.DAT',True,1,0,'',0),5);self.assertEqual(bank.to_config(),before)

    def test_configuration_options_and_names_fail_closed(self):
        for name,cmos,sectors,size,form,element,code in [('PIP:../x',False,1,0,'',0,2),('RD:X',False,1,0,'',0,2),
                ('a',False,-1,0,'',0,2),('a',False,1,1025,'',0,2),('a',False,1,0,'x'*65,0,2),('a',False,1,0,'',-1,2),('a',False,3,0,'',0,5)]:
            bank=rt.FilePipes(limit=2048)
            self.assertEqual(bank.configure(name,cmos,sectors,size,form,element),code);self.assertEqual(bank.files,{})

    def test_combined_capacity_and_pipe_count_limits(self):
        bank=rt.FilePipes(limit=2048)
        self.assertEqual(bank.configure('A',False,1,0,'',0),0);self.assertEqual(bank.configure('B',False,1,0,'',0),0)
        self.assertEqual(bank.configure('C',False,1,0,'',0),5)
        bank=rt.FilePipes(limit=64*1024)
        for index in range(32):self.assertEqual(bank.configure('P'+str(index),False,1,0,'',0),0)
        self.assertEqual(bank.configure('EXTRA',False,1,0,'',0),5)

    def test_failed_binary_read_preserves_cursor_and_outputs(self):
        ctx=pipe_context();p,_=compile_program(CONFIG+" OPEN FILE f('RWB','PIP:LOG.DAT') WRITE f(7) n=77 m=88 READ f(n,m)",decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['M'],p.snapshot()['F']['position']),(77,88,0))
        self.assertEqual(ctx.file_pipes.files['PIP:LOG.DAT'],struct.pack('<i',7));p._state.file_close(p._state.values['F'])

    def test_handle_limit_rejects_before_opening_an_extra_file(self):
        bank=rt.FilePipes();bank.configure('LOG.DAT',False,1,0,'',0)
        handles=[pipe_handle(bank,'R') for _ in range(32)];extra=rt.FileHandle()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'limit'):bank.open_for(None,extra,'R','PIP:LOG.DAT')
        self.assertIsNone(extra.owner);self.assertEqual(len(bank.handles),32)
        for handle in handles:bank.close(handle)


class CommunicationPersistenceAndScopeTests(unittest.TestCase):
    def test_messaging_json_roundtrip_keeps_scripted_state_and_buffers(self):
        ctx=socket_context('input',hosts={'test':282});run("MSG_CONNECT('S1:',s)",context=ctx)
        config=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(config)
        self.assertEqual(restored.to_config(),config);self.assertTrue(restored.messaging.ports['S1:']['connected'])

    def test_file_pipe_json_roundtrip_keeps_history_and_configuration(self):
        ctx=pipe_context();run(CONFIG+" OPEN FILE f('WO','PIP:LOG.DAT') WRITE f('data') CLOSE FILE f",decl=DECL,context=ctx)
        config=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(config)
        self.assertEqual(restored.to_config(),config);self.assertEqual(restored.file_pipes.files['PIP:LOG.DAT'],b'data')

    def test_live_files_prevent_context_save_then_close_restores_it(self):
        cases=[(socket_context(),"MSG_CONNECT('S1:',s) OPEN FILE f('RW','S1:')"),
            (pipe_context(),CONFIG+" OPEN FILE f('RW','PIP:LOG.DAT')")]
        for ctx,body in cases:
            p,_=compile_program(body,decl=DECL,context=ctx);p.run()
            with self.assertRaisesRegex(ValueError,'live'):ctx.to_config()
            p._state.file_close(p._state.values['F']);self.assertIsInstance(ctx.to_config(),dict)

    def test_invalid_messaging_configuration_and_duplicate_names_reject(self):
        for ports in ({'C9:':{}},{'S1:':{'connected':True,'mounted':False}},{'S1:':{'available':1}},
                {'S1:':{},'s1:':{}},{'S1:':{'input':{'hex':'0'}}},{'S1:':{'extra':1}}):
            with self.assertRaises(ValueError):rt.Messaging(ports)
        with self.assertRaises(ValueError):rt.Messaging({'C1:':{'input':'123'},'S1:':{'output':'456'}},limit=5)
        for hosts in ({'bad host':0},{'test':True},{'TEST':0,'test':1}):
            with self.assertRaises(ValueError):rt.Messaging(hosts=hosts)

    def test_invalid_saved_pipe_data_and_duplicate_aliases_reject(self):
        for config in ({'pipes':{'A':{'data':{'hex':'0'}}}}, {'pipes':{'A':{},'PIP:A':{}}},
                {'pipes':{'A':{'extra':1}}},{'pipes':{'A':{'form_dict':7}}},{'pipes':{'A':{'sectors':1,'data':'x'*1025}}}):
            with self.assertRaises(ValueError):rt.FilePipes.from_config(config)

    def test_daq_and_plain_registration_reject_namespace_collisions(self):
        for first in ('daq','plain'):
            ctx=rt.ExecutionContext(acquisition=rt.Acquisition(),file_pipes=rt.FilePipes())
            daq="DAQ_REGPIPE(1,DAQ_DRAM,1,'','n','log.dat',0,s)"
            body=(daq+' '+CONFIG) if first=='daq' else (CONFIG+' '+daq)
            self.assertEqual(run(body,decl=DECL,context=ctx)['S'],3)
            self.assertEqual(len(ctx.acquisition.pipes)+len(ctx.file_pipes.pipes),1)

    def test_context_and_open_reject_ambiguous_pipe_names(self):
        daq=rt.Acquisition();daq.register(1,0,1,('INTEGER',),'log.dat',0)
        pipes=rt.FilePipes();pipes.configure('LOG.DAT',False,1,0,'',0)
        with self.assertRaises(ValueError):rt.ExecutionContext(acquisition=daq,file_pipes=pipes)
        ctx=rt.ExecutionContext(acquisition=daq,file_pipes=rt.FilePipes())
        ctx.file_pipes.configure('LOG.DAT',False,1,0,'',0)
        p,_=compile_program("OPEN FILE f('RO','PIP:LOG.DAT')",decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'one explicitly'):p.run()
        self.assertIsNone(p._state.values['F'].owner)

    def test_missing_services_do_not_fall_back_to_filesystem_data(self):
        for body in ("MSG_CONNECT('S1:',s)","MSG_PING('fixture',s)",CONFIG,"OPEN FILE f('RO','S1:')","OPEN FILE f('RO','PIP:LOG.DAT')"):
            with self.assertRaises(rt.KarelRuntimeError):run(body,decl=DECL)

    def test_nested_routines_and_programs_share_scripted_endpoints(self):
        ctx=socket_context('17\n')
        p=translate_project({'main':source('MAIN',"MSG_CONNECT('S1:',s) CALL_PROG('CHILD',s) MSG_DISCO('S1:',s)"),
            'child':source('CHILD',"OPEN FILE f('RW','S1:') READ f(n,CR) WRITE f('ok') CLOSE FILE f",decl='n:INTEGER f:FILE')}).instantiate(context=ctx)
        p.run('MAIN');self.assertEqual(p.programs['CHILD'].snapshot()['N'],17)
        self.assertEqual(ctx.messaging.take_output('S1:'),b'ok')

    def test_producer_and_consumer_can_use_distinct_linked_programs(self):
        ctx=pipe_context()
        p=translate_project({'main':source('MAIN',CONFIG+" CALL_PROG('PRODUCER',s) CALL_PROG('CONSUMER',s)"),
            'producer':source('PRODUCER',"OPEN FILE f('WB','PIP:LOG.DAT') WRITE f(19) CLOSE FILE f",decl='f:FILE'),
            'consumer':source('CONSUMER',"OPEN FILE f('RB','PIP:LOG.DAT') READ f(n) CLOSE FILE f",decl='f:FILE n:INTEGER')}).instantiate(context=ctx)
        p.run('MAIN');self.assertEqual(p.programs['CONSUMER'].snapshot()['N'],19)

    def test_scheduled_consumer_polls_until_producer_appends_data(self):
        ctx=pipe_context()
        main=source('MAIN',CONFIG+" RUN_TASK('CONSUMER',0,FALSE,FALSE,0,s) RUN_TASK('PRODUCER',0,FALSE,FALSE,0,s)")
        producer=source('PRODUCER',"DELAY 2 OPEN FILE f('WB','PIP:LOG.DAT') WRITE f(29) CLOSE FILE f",decl='f:FILE')
        consumer=source('CONSUMER',"OPEN FILE f('RB','PIP:LOG.DAT') BYTES_AHEAD(f,available,s) WHILE available<4 DO BYTES_AHEAD(f,available,s) ENDWHILE READ f(n) CLOSE FILE f",decl='f:FILE n,available,s:INTEGER')
        p=translate_project({'main':main,'producer':producer,'consumer':consumer}).instantiate(context=ctx)
        result=p.run('MAIN',max_cycles=200)
        self.assertTrue(all(row['state']=='completed' for row in result.values()))
        self.assertEqual(result['CONSUMER']['values']['N'],29)

    def test_saved_context_rejects_normalized_daq_pipe_collisions(self):
        daq=rt.Acquisition();daq.register(1,0,1,('INTEGER',),'log.dat',0)
        pipes=rt.FilePipes();pipes.configure('LOG.DAT',False,1,0,'',0)
        with self.assertRaisesRegex(ValueError,'distinct'):
            rt.ExecutionContext.from_config({'acquisition':daq.to_config(),'file_pipes':pipes.to_config()})

    def test_status_counter_guards_and_user_override_remain(self):
        for call in ("MSG_CONNECT('S1:',n)","MSG_PING('fixture',n)","PIPE_CONFIG('A',FALSE,1,0,'',0,n)","MOUNT_DEV('S1:',n)"):
            with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO '+call+' ENDFOR')
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
        self.assertEqual(run('MSG_CONNECT(7)',routines='ROUTINE MSG_CONNECT(x:INTEGER) BEGIN n=x END MSG_CONNECT')['N'],7)


if __name__=='__main__':unittest.main()
