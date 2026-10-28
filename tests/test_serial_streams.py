"""Authored finite serial FILE queues, outboxes and strict configuration."""
from copy import copy
import json
import struct
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py.serial_io import SerialStreams
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


DECL='f,g:FILE n,m,s,ahead,cursor:INTEGER text:STRING[16]'


def context(data=b'',output=b'',*,capacity=1024,limit=4096):
    return rt.ExecutionContext(serial_streams=SerialStreams({2:{'input':data,'output':output,'capacity':capacity}},limit=limit))


def opened(bank,mode='RW',name='P2:'):
    handle=rt.FileHandle();bank.open_for(None,handle,mode,name);return handle


class SerialStreamFileTests(unittest.TestCase):
    def test_text_read_write_close_consumes_rx_and_retains_separate_tx(self):
        ctx=context(b'21\n',b'prior:')
        data=run("OPEN FILE f('RW','p2:') READ f(n,CR) WRITE f('answer=',n*2,CR) CLOSE FILE f",decl=DECL,context=ctx)
        self.assertEqual(data['N'],21)
        self.assertEqual(ctx.serial_streams.snapshot()[2],{'capacity':1024,'input':b'','output':b'prior:answer= 42\n'})
        self.assertEqual((data['F']['open'],data['F']['position']),(False,0))

    def test_writes_never_echo_or_advance_receive_cursor(self):
        ctx=context(b'7\n');data=run("OPEN FILE f('RW','P2:') WRITE f('99',CR) cursor=GET_FILE_POS(f) READ f(n,CR) CLOSE FILE f",decl=DECL,context=ctx)
        self.assertEqual((data['CURSOR'],data['N']),(0,7))
        self.assertEqual(ctx.serial_streams.snapshot()[2]['output'],b'99\n')

    def test_write_modes_preserve_rx_and_previous_tx(self):
        for mode in ('W','WO','A','AP','AO','RW','UD'):
            with self.subTest(mode=mode):
                ctx=context(b'rx',b'old');run(f"OPEN FILE f('{mode}','P2:') WRITE f('new') CLOSE FILE f",decl=DECL,context=ctx)
                self.assertEqual(ctx.serial_streams.snapshot()[2]['input'],b'rx')
                self.assertEqual(ctx.serial_streams.snapshot()[2]['output'],b'oldnew')

    def test_read_only_writes_fail_without_changing_buffers(self):
        ctx=context(b'rx',b'tx');before=ctx.serial_streams.snapshot()
        task,_=compile_program("OPEN FILE f('RO','P2:') WRITE f('new')",decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'read-only'):task.run()
        self.assertEqual(ctx.serial_streams.snapshot(),before);ctx.serial_streams.close(task._state.values['F'])

    def test_write_only_reads_fail_without_consuming_rx(self):
        for mode in ('WO','AP','AO'):
            with self.subTest(mode=mode):
                ctx=context(b'42\n');task,_=compile_program(f"OPEN FILE f('{mode}','P2:') n=77 READ f(n)",decl=DECL,context=ctx)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'not readable'):task.run()
                self.assertEqual(task.snapshot()['N'],77);ctx.serial_streams.close(task._state.values['F'])
                self.assertEqual(ctx.serial_streams.snapshot()[2]['input'],b'42\n')

    def test_rx_prefix_is_retained_until_explicit_close(self):
        ctx=context(b'7\n8\n');task,_=compile_program("OPEN FILE f('RO','P2:') READ f(n,CR)",decl=DECL,context=ctx)
        task.run();self.assertEqual(ctx.serial_streams.snapshot()[2]['input'],b'7\n8\n')
        self.assertEqual(task.snapshot()['F']['position'],2)
        ctx.serial_streams.close(task._state.values['F'])
        self.assertEqual(ctx.serial_streams.snapshot()[2]['input'],b'8\n')

    def test_reopen_reads_unconsumed_suffix(self):
        ctx=context(b'7\n8\n')
        data=run("OPEN FILE f('RO','P2:') READ f(n,CR) CLOSE FILE f OPEN FILE f('RO','P2:') READ f(m,CR) CLOSE FILE f",decl=DECL,context=ctx)
        self.assertEqual((data['N'],data['M']),(7,8));self.assertEqual(ctx.serial_streams.snapshot()[2]['input'],b'')

    def test_availability_queries_measure_only_unread_rx(self):
        ctx=context(b'7\n8\n')
        data=run("OPEN FILE f('RW','P2:') WRITE f('outbox') READ f(n,CR) BYTES_AHEAD(f,ahead,s) m=BYTES_LEFT(f) cursor=GET_FILE_POS(f) CLOSE FILE f",decl=DECL,context=ctx)
        self.assertEqual((data['AHEAD'],data['M'],data['CURSOR'],data['S']),(2,2,2,0))

    def test_serial_seek_is_rejected_without_changing_cursor(self):
        ctx=context(b'7\n8\n')
        data=run("OPEN FILE f('RO','P2:') READ f(n,CR) SET_FILE_POS(f,0,s) cursor=GET_FILE_POS(f) READ f(m,CR) CLOSE FILE f",decl=DECL,context=ctx)
        self.assertEqual((data['S'],data['CURSOR'],data['M']),(2,2,8))

    def test_binary_mixed_fields_use_existing_widths(self):
        payload=struct.pack('<iBh?f',17,255,-7,True,1.5)+b'abc'
        ctx=context(payload)
        data=run("OPEN FILE f('RB','P2:') READ f(n,bytes[1],shorts[1],flag,value,text::3) CLOSE FILE f",
                 decl=DECL+' bytes:ARRAY[1]OF BYTE shorts:ARRAY[1]OF SHORT flag:BOOLEAN value:REAL',context=ctx)
        self.assertEqual((data['N'],data['BYTES'],data['SHORTS'],data['FLAG'],data['VALUE'],data['TEXT']),(17,[255],[-7],True,1.5,'abc'))
        self.assertEqual(ctx.serial_streams.snapshot()[2]['input'],b'')

    def test_binary_write_and_reverse_are_checked_before_append(self):
        ctx=context()
        run("SET_FILE_ATR(f,ATR_UF) SET_FILE_ATR(f,ATR_REVERSE) OPEN FILE f('WO','P2:') WRITE f(16909060) CLOSE FILE f",decl=DECL,context=ctx)
        self.assertEqual(ctx.serial_streams.snapshot()[2]['output'],b'\x01\x02\x03\x04')

    def test_binary_short_input_preserves_outputs_and_cursor(self):
        ctx=context(struct.pack('<i',17))
        task,_=compile_program("OPEN FILE f('RB','P2:') n=77 m=88 READ f(n,m)",decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'serial input'):task.run()
        self.assertEqual((task.snapshot()['N'],task.snapshot()['M'],task.snapshot()['F']['position']),(77,88,0))
        ctx.serial_streams.close(task._state.values['F']);self.assertEqual(ctx.serial_streams.snapshot()[2]['input'],struct.pack('<i',17))

    def test_malformed_text_preserves_all_read_destinations(self):
        ctx=context(b'17 wrong\n')
        task,_=compile_program("OPEN FILE f('RO','P2:') n=77 m=88 READ f(n,m,CR)",decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'invalid INTEGER'):task.run()
        self.assertEqual((task.snapshot()['N'],task.snapshot()['M'],task.snapshot()['F']['position']),(77,88,0))
        ctx.serial_streams.close(task._state.values['F']);self.assertEqual(ctx.serial_streams.snapshot()[2]['input'],b'17 wrong\n')

    def test_failed_later_read_consumes_only_prior_successful_prefix_on_close(self):
        ctx=context(b'7\n8\n')
        task,_=compile_program("OPEN FILE f('RO','P2:') READ f(n,CR) m=88 READ f(n,m,CR)",decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):task.run()
        self.assertEqual((task.snapshot()['N'],task.snapshot()['M'],task.snapshot()['F']['position']),(7,88,2))
        ctx.serial_streams.close(task._state.values['F']);self.assertEqual(ctx.serial_streams.snapshot()[2]['input'],b'8\n')

    def test_non_ascii_text_is_rejected_but_raw_binary_remains_available(self):
        ctx=context(b'\xff');task,_=compile_program("OPEN FILE f('RO','P2:') READ f(text)",decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ASCII'):task.run()
        ctx.serial_streams.close(task._state.values['F'])
        data=run("OPEN FILE f('RB','P2:') READ f(bytes[1]) CLOSE FILE f",decl=DECL+' bytes:ARRAY[1]OF BYTE',context=ctx)
        self.assertEqual(data['BYTES'],[255])

    def test_custom_eol_and_field_widths_use_explicit_file_attributes(self):
        ctx=context(b'abc;')
        data=run("SET_FILE_ATR(f,ATR_EOL,59) SET_FILE_ATR(f,ATR_FIELD) OPEN FILE f('RO','P2:') READ f(text,CR) CLOSE FILE f",decl='f:FILE text:STRING[3]',context=ctx)
        self.assertEqual(data['TEXT'],'abc')

    def test_serial_metadata_does_not_implicitly_change_eol(self):
        ctx=context(b'7\n');ctx.serial_ports=rt.SerialPorts({2:{'ATR_EOL':59}})
        data=run("OPEN FILE f('RO','P2:') READ f(n,CR) CLOSE FILE f",decl=DECL,context=ctx)
        self.assertEqual(data['N'],7)

    def test_empty_input_fails_finitely_without_sleeper(self):
        ctx=context();task,_=compile_program("OPEN FILE f('RO','P2:') READ f(n)",decl=DECL,context=ctx)
        with patch('time.sleep',side_effect=AssertionError('Serial input must not wait'))as sleeper:
            with self.assertRaises(rt.KarelRuntimeError):task.run()
            sleeper.assert_not_called()
        ctx.serial_streams.close(task._state.values['F'])

    def test_stream_names_cannot_fall_back_to_literal_files(self):
        for name in ('P2:','P2:data','P2:../x','P02:','P0:','P6:'):
            with self.subTest(name=name):
                files=rt.MemoryFiles({name:'42\n'});ctx=rt.ExecutionContext(files=files)
                task,_=compile_program(f"OPEN FILE f('RO','{name}') READ f(n)",decl=DECL,context=ctx)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'serial_streams'):task.run()
                self.assertEqual(files.snapshot()[name],b'42\n')

    def test_configured_stream_routing_preserves_ordinary_literal_bank(self):
        ctx=context(b'7\n');ctx.files=rt.MemoryFiles({'P2:':'99\n'})
        data=run("OPEN FILE f('RO','P2:') READ f(n,CR) CLOSE FILE f",decl=DECL,context=ctx)
        self.assertEqual(data['N'],7);self.assertEqual(ctx.files.snapshot(),{'P2:':b'99\n'})

    def test_explicit_fifth_port_is_a_portable_endpoint(self):
        ctx=rt.ExecutionContext(serial_streams=SerialStreams({5:{'input':'5\n'}}))
        self.assertEqual(run("OPEN FILE f('RO','p5:') READ f(n,CR) CLOSE FILE f",decl=DECL,context=ctx)['N'],5)

    def test_xml_passall_and_pipe_attributes_are_rejected_before_open(self):
        for attribute in ('SET_FILE_ATR(f,ATR_XML)','SET_FILE_ATR(f,ATR_PASSALL)','SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED)'):
            with self.subTest(attribute=attribute):
                ctx=context(b'prior');task,_=compile_program(attribute+" OPEN FILE f('RO','P2:')",decl=DECL,context=ctx)
                with self.assertRaises(rt.KarelRuntimeError):task.run()
                self.assertEqual(ctx.serial_streams.handles,[]);self.assertEqual(ctx.serial_streams.snapshot()[2]['input'],b'prior')


class SerialStreamBackendTests(unittest.TestCase):
    def test_one_live_handle_per_endpoint_without_closing_other_ports(self):
        bank=SerialStreams({1:{},2:{}});first=opened(bank,name='P1:');second=opened(bank,name='P2:');extra=rt.FileHandle()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'already'):bank.open_for(None,extra,'RW','p1:')
        self.assertIsNone(extra.owner);self.assertEqual(len(bank.handles),2)
        bank.close(first);self.assertIs(second.owner,bank);bank.close(second)

    def test_open_checks_exact_name_and_mode_before_buffer_changes(self):
        bank=SerialStreams({2:{'input':'rx','output':'tx'}});before=bank.snapshot()
        for mode,name in (('RW','P02:'),('RW','P2:data'),('RW',' P2:'),('RW','P2:/'),('RW','P9:'),('RBB','P2:'),('BR','P2:'),('BAD','P2:')):
            with self.subTest(mode=mode,name=name):
                h=rt.FileHandle()
                with self.assertRaises(rt.KarelRuntimeError):bank.open_for(None,h,mode,name)
                self.assertIsNone(h.owner);self.assertEqual(bank.snapshot(),before)

    def test_closed_copied_and_foreign_handles_are_rejected(self):
        bank=SerialStreams({2:{'input':'rx'}});other=SerialStreams({2:{'input':'other'}});h=opened(bank);clone=copy(h)
        for operation in (lambda:bank.read_bytes(clone,1),lambda:bank.write(clone,b'x'),lambda:bank.close(clone),
                          lambda:other.read_bytes(h,1),lambda:other.write(h,b'x'),lambda:other.close(h)):
            with self.subTest(operation=operation),self.assertRaises(rt.KarelRuntimeError):operation()
        self.assertEqual((h.position,bank.snapshot()[2]['input']),(0,b'rx'));bank.close(h)
        for operation in (lambda:bank.read_bytes(h,1),lambda:bank.write(h,b'x'),lambda:bank.flush(h),lambda:bank.close(h)):
            with self.subTest(operation=operation),self.assertRaises(rt.KarelRuntimeError):operation()

    def test_cursor_bounds_and_write_only_cursor_invariant(self):
        bank=SerialStreams({2:{'input':'rx'}});h=opened(bank)
        for value in (-1,3,True,1.0):
            h.position=value
            with self.subTest(value=value),self.assertRaisesRegex(rt.KarelRuntimeError,'cursor'):bank.bytes_ahead(h)
        h.position=0;bank.close(h);h=opened(bank,'WO');h.position=1
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cursor'):bank.close(h)
        h.position=0;bank.close(h);self.assertEqual(bank.snapshot()[2]['input'],b'rx')

    def test_changed_endpoint_metadata_cannot_redirect_io(self):
        bank=SerialStreams({2:{'input':'rx'},3:{'input':'other'}});h=opened(bank);h.name='P3:'
        with self.assertRaisesRegex(rt.KarelRuntimeError,'metadata'):bank.read_bytes(h,1)
        h.name='P2:';bank.close(h);self.assertEqual(bank.snapshot()[3]['input'],b'other')

    def test_numeric_aliases_for_boolean_handle_flags_are_rejected(self):
        bank=SerialStreams({2:{'input':'rx'}});h=opened(bank);h.binary=0
        with self.assertRaisesRegex(rt.KarelRuntimeError,'attributes'):bank.bytes_ahead(h)
        h.binary=False;bank.close(h)

    def test_feed_during_open_preserves_unread_suffix_after_close(self):
        bank=SerialStreams({2:{'input':'ab'}});h=opened(bank);self.assertEqual(bank.read_bytes(h,1),b'a')
        bank.feed(2,b'cd');bank.close(h);self.assertEqual(bank.snapshot()[2]['input'],b'bcd')

    def test_output_drain_is_detached_and_does_not_consume_input(self):
        bank=SerialStreams({2:{'input':'rx','output':'abcd'}});h=opened(bank)
        self.assertEqual(bank.take_output(2,2),b'ab');self.assertEqual(bank.take_output(2),b'cd')
        self.assertEqual(bank.snapshot()[2]['input'],b'rx');bank.close(h)

    def test_per_port_capacity_is_atomic_for_feed_and_write(self):
        bank=SerialStreams({2:{'input':'ab','output':'cd','capacity':4}},limit=8);before=bank.snapshot();h=opened(bank)
        with self.assertRaises(ValueError):bank.feed(2,b'e')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):bank.write(h,b'e')
        self.assertEqual(bank.snapshot(),before);self.assertEqual(h.position,0);bank.close(h)

    def test_global_capacity_covers_all_input_and_output_buffers(self):
        bank=SerialStreams({1:{'input':'abc'},2:{'output':'de'}},limit=5);h=opened(bank,name='P1:');before=bank.snapshot()
        with self.assertRaises(ValueError):bank.feed(2,b'f')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):bank.write(h,b'f')
        self.assertEqual(bank.snapshot(),before);bank.close(h)

    def test_consumed_but_unclosed_rx_still_counts_against_capacity(self):
        bank=SerialStreams({2:{'input':'ab','capacity':2}},limit=2);h=opened(bank);bank.read_bytes(h,2)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):bank.write(h,b'x')
        bank.close(h);h=opened(bank,'WO');bank.write(h,b'x');bank.close(h)
        self.assertEqual(bank.snapshot()[2]['output'],b'x')

    def test_zero_byte_operations_are_finite(self):
        bank=SerialStreams({2:{'capacity':1}},limit=1);h=opened(bank)
        bank.feed(2,b'');bank.write(h,b'');self.assertEqual(bank.read_bytes(h,0),b'')
        self.assertEqual(bank.take_output(2,0),b'');bank.close(h)

    def test_host_port_and_count_inputs_are_exact_types(self):
        bank=SerialStreams({2:{'output':'x'}})
        for port in (True,'2','P2:',0,6,2.0):
            with self.subTest(port=port),self.assertRaises(ValueError):bank.feed(port,b'x')
        for count in (True,-1,2,1.0):
            with self.subTest(count=count),self.assertRaises(ValueError):bank.take_output(2,count)
        self.assertEqual(bank.snapshot()[2]['output'],b'x')

    def test_snapshot_is_detached(self):
        bank=SerialStreams({2:{'input':'rx','output':'tx'}});snapshot=bank.snapshot()
        snapshot[2]['input']=b'changed';snapshot[2]['capacity']=1
        self.assertEqual(bank.snapshot()[2]['input'],b'rx');self.assertGreater(bank.snapshot()[2]['capacity'],1)


class SerialStreamConfigurationAndLifetimeTests(unittest.TestCase):
    def test_context_roundtrip_keeps_remaining_rx_and_tx(self):
        ctx=context(b'7\n8\n');run("OPEN FILE f('RW','P2:') READ f(n,CR) WRITE f('done') CLOSE FILE f",decl=DECL,context=ctx)
        config=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(config)
        self.assertEqual(restored.to_config(),config)
        self.assertEqual(restored.serial_streams.snapshot()[2]['input'],b'8\n')
        self.assertEqual(restored.serial_streams.snapshot()[2]['output'],b'done')

    def test_live_handle_prevents_save_until_close(self):
        ctx=context(b'rx');h=opened(ctx.serial_streams)
        with self.assertRaisesRegex(ValueError,'live serial'):ctx.to_config()
        ctx.serial_streams.close(h);self.assertIsInstance(ctx.to_config(),dict)

    def test_config_hex_is_canonical_and_detached(self):
        bank=SerialStreams({5:{'input':{'hex':'00ff'},'output':{'hex':'fe'},'capacity':4}},limit=8)
        config=json.loads(json.dumps(bank.to_config()))
        self.assertEqual(config,{'limit':8,'ports':{'5':{'capacity':4,'input':{'hex':'00ff'},'output':{'hex':'fe'}}}})
        self.assertEqual(SerialStreams.from_config(config).to_config(),config)
        config['ports']['5']['capacity']=1;self.assertEqual(bank.snapshot()[5]['capacity'],4)

    def test_unknown_fields_or_noncanonical_json_keys_reject(self):
        for config in ({'extra':1},{'ports':[]},{'ports':{2:{}}},{'ports':{'02':{}}},{'ports':{'P2:':{}}},
                       {'ports':{'0':{}}},{'ports':{'6':{}}},{'ports':{'2':{'baud':9600}}}):
            with self.subTest(config=config),self.assertRaises(ValueError):SerialStreams.from_config(config)

    def test_constructor_rejects_noninteger_ports_or_malformed_rows(self):
        for ports in ({True:{}},{'2':{}},{0:{}},{6:{}},{2:None},{2:{'input':None}},{2:{'input':{'hex':'f'}}},
                      {2:{'capacity':True}},{2:{'capacity':0}},{2:{'capacity':9}},{2:{'input':'caf\u00e9'}}):
            with self.subTest(ports=ports),self.assertRaises(ValueError):SerialStreams(ports,limit=8)

    def test_initial_data_cannot_exceed_port_or_bank_budget(self):
        for ports in ({2:{'input':'abc','output':'de','capacity':4}},
                      {1:{'input':'abc'},2:{'input':'def'}}):
            with self.subTest(ports=ports),self.assertRaises(ValueError):SerialStreams(ports,limit=5)
        for limit in (True,0,-1,64*1024*1024+1,1.0):
            with self.subTest(limit=limit),self.assertRaises(ValueError):SerialStreams({},limit=limit)

    def test_empty_bank_does_not_discover_ports(self):
        bank=SerialStreams.from_config({});self.assertEqual(bank.to_config()['ports'],{})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicitly configured'):opened(bank)

    def test_pause_and_stop_do_not_silently_close_or_consume_stream(self):
        ctx=context(b'7\n8\n');task,_=compile_program("OPEN FILE f('RO','P2:') READ f(n,CR) PAUSE",decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelPause):task.run()
        task.stop();self.assertEqual(ctx.serial_streams.snapshot()[2]['input'],b'7\n8\n')
        with self.assertRaisesRegex(ValueError,'live serial'):ctx.to_config()
        ctx.serial_streams.close(task._state.values['F']);self.assertEqual(ctx.serial_streams.snapshot()[2]['input'],b'8\n')

    def test_linked_programs_share_explicit_streams_and_remaining_input(self):
        ctx=context(b'7\n8\n')
        project=translate_project({'main':source('MAIN',"CALL_PROG('CHILD',s) OPEN FILE f('RO','P2:') READ f(n,CR) CLOSE FILE f",decl=DECL),
            'child':source('CHILD',"OPEN FILE f('RW','P2:') READ f(n,CR) WRITE f('child') CLOSE FILE f",decl=DECL)}).instantiate(context=ctx)
        result=project.run('MAIN')
        self.assertEqual((result['CHILD']['values']['N'],result['MAIN']['values']['N']),(7,8))
        self.assertEqual(ctx.serial_streams.snapshot()[2]['output'],b'child')


if __name__=='__main__':unittest.main()
