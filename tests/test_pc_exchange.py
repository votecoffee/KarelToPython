"""Authored PC wire-buffer builders, typed/raw outboxes and context replay."""
from copy import deepcopy
import json
import math
import struct
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from karel2py.pc_exchange import decode_packet,MAX_SEQUENCE
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


DECL='buffer:ARRAY[32] OF BYTE cursor,s,n:INTEGER'


def context(*,capacity=1024,packet_format='typed'):
    return rt.ExecutionContext(pc_exchange=rt.PcExchange(capacity,packet_format=packet_format))


def packet(ctx,body,*,decl=DECL,routines='',prefix=''):
    p,result=compile_program(body,decl=decl,routines=routines,prefix=prefix,context=ctx)
    return p,p.run(),result


class PcBuilderTests(unittest.TestCase):
    def test_integer_layout_signed_values_and_marker_index(self):
        for value in (5,-12,-2147483648,2147483646):
            text='MININT' if value==-2147483648 else str(value)
            data=run(f'cursor=1 ADD_INTPC(buffer,cursor,{text},s)',decl='buffer:ARRAY[8] OF BYTE cursor,s:INTEGER')
            self.assertEqual(data['BUFFER'],list(b'\x00\x10'+struct.pack('>i',value)+b'\0\0'))
            self.assertEqual((data['CURSOR'],data['S']),(7,0))
            self.assertEqual(decode_packet(bytes(data['BUFFER']))[1],[{'type':'INTEGER','value':value}])

    def test_real_layout_and_pythonic_float32_rounding(self):
        for value in (1.5,-2.25,0.1):
            data=run(f'cursor=1 ADD_REALPC(buffer,cursor,{value},s)',decl='buffer:ARRAY[8] OF BYTE cursor,s:INTEGER')
            self.assertEqual(data['BUFFER'],list(b'\x00\x11'+struct.pack('>f',value)+b'\0\0'))

    def test_string_length_nul_and_marker(self):
        for text in ('','go','A\0B'):
            expression="'A'+CHR(0)+'B'" if '\0' in text else repr(text)
            size=len(text)+6
            data=run(f'cursor=1 ADD_STRINGPC(buffer,cursor,{expression},s)',decl=f'buffer:ARRAY[{size}] OF BYTE cursor,s:INTEGER')
            self.assertEqual(data['BUFFER'],list(b'\0\xd1'+bytes((len(text),))+text.encode('ascii')+b'\0\0\0'))
            self.assertEqual(data['CURSOR'],len(text)+5)

    def test_appended_items_overwrite_only_previous_marker(self):
        data=run("cursor=1 ADD_INTPC(buffer,cursor,5,s) ADD_STRINGPC(buffer,cursor,'x',s)",decl=DECL)
        expected=b'\0\x10'+struct.pack('>i',5)+b'\0\xd1\x01x\0\0\0'
        self.assertEqual(data['BUFFER'][:len(expected)],list(expected))
        self.assertEqual(data['CURSOR'],12)
        self.assertEqual(data['BUFFER'][-1],{'unknown_byte':True})

    def test_noninitial_offset_retains_prefix_and_tail(self):
        data=run('buffer[1]=99 cursor=2 ADD_INTPC(buffer,cursor,7,s)',decl=DECL)
        self.assertEqual(data['BUFFER'][0],99);self.assertEqual(data['CURSOR'],8)
        self.assertEqual(data['BUFFER'][9],{'unknown_byte':True})

    def test_capacity_failure_preserves_buffer_and_index(self):
        data=run('buffer[1]=99 cursor=1 ADD_INTPC(buffer,cursor,7,s)',decl='buffer:ARRAY[7] OF BYTE cursor,s:INTEGER')
        self.assertEqual((data['S'],data['CURSOR'],data['BUFFER'][0]),(3,1,99))
        self.assertTrue(all(value=={'unknown_byte':True} for value in data['BUFFER'][1:]))

    def test_uninitialized_and_invalid_indices_fail_without_mutation(self):
        for prefix in ('','cursor=0','cursor=33'):
            data=run(prefix+' ADD_INTPC(buffer,cursor,7,s)',decl=DECL)
            self.assertEqual(data['S'],2)
            self.assertTrue(all(value=={'unknown_byte':True} for value in data['BUFFER']))

    def test_numeric_overflow_preserves_index_and_buffer(self):
        data=run('cursor=1 ADD_REALPC(buffer,cursor,1.0E100,s)',decl=DECL)
        self.assertEqual((data['CURSOR'],data['S']),(1,4))
        self.assertTrue(all(value=={'unknown_byte':True} for value in data['BUFFER']))

    def test_string_maximum_packet_and_too_large_string(self):
        text='x'*238
        data=run(f"cursor=1 ADD_STRINGPC(buffer,cursor,'{text}',s)",decl='buffer:ARRAY[244] OF BYTE cursor,s:INTEGER')
        self.assertEqual((data['CURSOR'],data['S']),(243,0))
        data=run(f"cursor=1 ADD_STRINGPC(buffer,cursor,'{text}x',s)",decl='buffer:ARRAY[244] OF BYTE cursor,s:INTEGER')
        self.assertEqual((data['CURSOR'],data['S']),(1,3))

    def test_byname_integer_real_string_and_static_paths(self):
        for kind,value,body,expected in [('INTEGER',7,'value=7',b'\0\x10'+struct.pack('>i',7)),
                ('REAL',1.5,'value=1.5',b'\0\x11'+struct.pack('>f',1.5)),
                ('STRING[4]','ok',"value='ok'",b'\0\xd1\x02ok\0')]:
            ctx=context();_,data,_=packet(ctx,body+" cursor=1 ADD_BYNAMEPC(buffer,cursor,'','value',s) SEND_DATAPC(1,buffer,s)",decl=DECL+' value:'+kind)
            self.assertEqual(data['S'],0);self.assertEqual(ctx.pc_exchange.snapshot()[0]['data'],(expected+b'\0\0').hex())
        ctx=context();ctx.variables.define('CACHE','VALUES',('ARRAY',2,('INTEGER',)))
        run("SET_VAR(e,'CACHE','VALUES[2]',19,s) cursor=1 ADD_BYNAMEPC(buffer,cursor,'cache','values[2]',s) SEND_DATAPC(1,buffer,s)",decl=DECL+' e:INTEGER',context=ctx)
        self.assertEqual(ctx.pc_exchange.snapshot()[0]['data'],(b'\0\x10'+struct.pack('>i',19)+b'\0\0').hex())

    def test_byname_missing_system_unsupported_and_uninitialized_sources(self):
        for path,decl,code in [('missing','',1),('$SYSTEM','',1),('value','value:BOOLEAN',4),('value','value:ARRAY[2] OF INTEGER',4),('value','value:INTEGER',4)]:
            data=run(f"cursor=1 ADD_BYNAMEPC(buffer,cursor,'','{path}',s)",decl=DECL+' '+decl)
            self.assertEqual((data['S'],data['CURSOR']),(code,1),path)

    def test_generic_reference_builder_preserves_named_array_identity(self):
        p,_=compile_program('cursor=1 fill(buffer)',decl='buffer:series cursor,s:INTEGER',prefix='TYPE series=ARRAY[8] OF BYTE',
            routines='ROUTINE fill(data:ARRAY OF BYTE) BEGIN ADD_INTPC(data,cursor,7,s) END fill')
        original=p._state.values['BUFFER'];data=p.run()
        self.assertIs(p._state.values['BUFFER'],original)
        self.assertEqual(original.spec[-1],'SERIES');self.assertEqual(data['S'],0)

    def test_byname_captures_current_index_before_updating_it(self):
        ctx=context();packet(ctx,"cursor=1 ADD_BYNAMEPC(buffer,cursor,'','cursor',s) SEND_DATAPC(1,buffer,s)")
        self.assertEqual(ctx.pc_exchange.snapshot()[0]['data'],'0010000000010000')

    def test_builder_initializes_portable_missing_whole_array_storage(self):
        ctx=context();spec=('ARRAY',8,('BYTE',))
        ctx.variables.bind('T','BUFFER',rt.Reference(spec,{'value':rt.UNINITIALIZED},'value'))
        _,data,_=packet(ctx,'cursor=1 ADD_INTPC(buffer,cursor,5,s) SEND_DATAPC(1,buffer,s)',decl='buffer:ARRAY[8] OF BYTE cursor,s:INTEGER')
        self.assertEqual(data['S'],0);self.assertEqual(ctx.pc_exchange.snapshot()[0]['data'],'0010000000050000')

    def test_reference_overlap_and_for_counter_guards(self):
        p,_=compile_program('cursor=1 ADD_INTPC(buffer,cursor,7,cursor)',decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p.snapshot()['CURSOR'],1)
        for call in ('ADD_INTPC(buffer,n,7,s)','ADD_REALPC(buffer,cursor,1.5,n)',"ADD_BYNAMEPC(buffer,cursor,'','n',n)"):
            with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO '+call+' ENDFOR',decl=DECL)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_buffer_types_sizes_and_value_arguments_fail_closed(self):
        for decl in ('buffer:ARRAY[245] OF BYTE cursor,s:INTEGER','buffer:ARRAY[2,2] OF BYTE cursor,s:INTEGER','buffer:ARRAY[8] OF INTEGER cursor,s:INTEGER'):
            with self.assertRaises(TranslationError):compile_program('ADD_INTPC(buffer,cursor,7,s)',decl=decl)
        with self.assertRaises(TranslationError):compile_program('ADD_INTPC((buffer),cursor,7,s)',decl=DECL)

    def test_explicit_user_override_remains_available(self):
        self.assertEqual(run('ADD_INTPC(7)',routines='ROUTINE ADD_INTPC(x:INTEGER) BEGIN n=x END ADD_INTPC')['N'],7)


class PcSendingTests(unittest.TestCase):
    def test_typed_send_ignores_unknown_unused_tail_and_preserves_source(self):
        ctx=context();p,data,_=packet(ctx,"cursor=1 ADD_INTPC(buffer,cursor,5,s) SEND_DATAPC(12,buffer,s)")
        self.assertEqual(data['BUFFER'][-1],{'unknown_byte':True})
        self.assertEqual(ctx.pc_exchange.snapshot(),[{'sequence':1,'event':12,'data':'0010000000050000'}])
        self.assertEqual(p.service_requests[-1]['outcome'],'completed')

    def test_raw_mode_keeps_all_bytes_including_embedded_marker(self):
        ctx=context(packet_format='raw')
        _,data,_=packet(ctx,'buffer[1]=0 buffer[2]=0 buffer[3]=9 buffer[4]=255 buffer[5]=1 SEND_DATAPC(1,buffer,s)',decl='buffer:ARRAY[5] OF BYTE s:INTEGER')
        self.assertEqual(data['S'],0);self.assertEqual(ctx.pc_exchange.snapshot()[0]['data'],'000009ff01')

    def test_raw_unknown_tail_is_rejected_without_publication(self):
        ctx=context(packet_format='raw');_,data,_=packet(ctx,'cursor=1 ADD_INTPC(buffer,cursor,5,s) SEND_DATAPC(1,buffer,s)')
        self.assertEqual(data['S'],4);self.assertEqual(ctx.pc_exchange.sequence,0)

    def test_invalid_typed_envelopes_do_not_publish(self):
        for payload in (b'\0',b'\0\x12\0\0',b'\0\x10\0\0',b'\0\xd1\x01x!\0\0',b'\0\x11\x7f\x80\0\0\0\0',b'\0\xd1\x01\xff\0\0\0'):
            bank=rt.PcExchange();self.assertEqual(bank.send(1,payload),4,payload);self.assertEqual(bank.snapshot(),[])

    def test_empty_typed_packet_and_event_only_are_distinct(self):
        ctx=context();_,data,_=packet(ctx,'buffer[1]=0 buffer[2]=0 SEND_DATAPC(0,buffer,s) SEND_EVENTPC(255,s)')
        self.assertEqual(data['S'],0)
        self.assertEqual([row['data'] for row in ctx.pc_exchange.snapshot()],['0000',None])

    def test_event_bounds_capacity_and_sequence_are_checked(self):
        ctx=context(capacity=1)
        self.assertEqual(run('SEND_EVENTPC(-1,s)',context=ctx)['S'],2)
        self.assertEqual(run('SEND_EVENTPC(256,s)',context=ctx)['S'],2)
        self.assertEqual(run('SEND_EVENTPC(0,s)',context=ctx)['S'],0)
        self.assertEqual(run('SEND_EVENTPC(255,s)',context=ctx)['S'],5)
        self.assertEqual(ctx.pc_exchange.snapshot(),[{'sequence':1,'event':0,'data':None}])

    def test_send_captures_buffer_before_status_selector_effects(self):
        ctx=context();routines='ROUTINE outputslot:INTEGER BEGIN buffer[6]=9 RETURN 1 END outputslot'
        _,data,_=packet(ctx,'cursor=1 ADD_INTPC(buffer,cursor,5,s) SEND_DATAPC(12,buffer,statuses[outputslot])',decl=DECL+' statuses:ARRAY[1] OF INTEGER',routines=routines)
        self.assertEqual(data['BUFFER'][5],9)
        self.assertEqual(ctx.pc_exchange.snapshot()[0]['data'],'0010000000050000')

    def test_inputs_and_reference_selectors_evaluate_once_in_order(self):
        ctx=context();routines='''
ROUTINE eventno:INTEGER BEGIN n=n*10+1 buffer[6]=7 RETURN 12 END eventno
ROUTINE outputslot:INTEGER BEGIN n=n*10+2 buffer[6]=9 RETURN 1 END outputslot
'''
        _,data,_=packet(ctx,'n=0 cursor=1 ADD_INTPC(buffer,cursor,5,s) SEND_DATAPC(eventno,buffer,statuses[outputslot])',decl=DECL+' statuses:ARRAY[1] OF INTEGER',routines=routines)
        self.assertEqual(data['N'],12);self.assertEqual(ctx.pc_exchange.snapshot()[0]['data'],'0010000000070000')

    def test_builders_need_no_outbox_but_sends_require_explicit_service(self):
        self.assertEqual(run('cursor=1 ADD_INTPC(buffer,cursor,5,s)',decl=DECL)['S'],0)
        p,_=compile_program('s=77 SEND_EVENTPC(1,s)',decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'pc_exchange'):p.run()
        self.assertEqual(p.snapshot()['S'],77)

    def test_drain_detaches_messages_and_retains_sequence(self):
        bank=rt.PcExchange();bank.send(1);bank.send(2)
        result=bank.drain(1);result[0]['event']=99
        self.assertEqual(bank.snapshot(),[{'sequence':2,'event':2,'data':None}])
        self.assertEqual(bank.send(3),0);self.assertEqual(bank.snapshot()[-1]['sequence'],3)
        before=bank.to_config()
        for count in (-1,3,True):
            with self.assertRaises(ValueError):bank.drain(count)
        self.assertEqual(bank.to_config(),before)

    def test_sending_formal_is_read_only_for_effect_analysis(self):
        ctx=context();p,_,result=packet(ctx,'cursor=1 ADD_INTPC(buffer,cursor,5,s) transmit(buffer)',
            routines='ROUTINE transmit(data:ARRAY OF BYTE) VAR status:INTEGER BEGIN SEND_DATAPC(1,data,status) END transmit')
        self.assertEqual(result.report['routine_effects']['TRANSMIT']['potential_global_writes'],[])
        self.assertEqual(ctx.pc_exchange.snapshot()[0]['event'],1)

    def test_oversized_generic_formal_is_checked_at_runtime(self):
        ctx=context();p,_=compile_program('s=77 cursor=1 fill(buffer)',decl='buffer:ARRAY[245] OF BYTE cursor,s:INTEGER',context=ctx,
            routines='ROUTINE fill(data:ARRAY OF BYTE) BEGIN ADD_INTPC(data,cursor,5,s) END fill')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['S'],77)
        _,data,_=packet(ctx,'transmit(buffer)',decl='buffer:ARRAY[245] OF BYTE s:INTEGER',
            routines='ROUTINE transmit(data:ARRAY OF BYTE) BEGIN SEND_DATAPC(1,data,s) END transmit')
        self.assertEqual(data['S'],4)

    def test_linked_lookup_defaults_to_executing_module(self):
        ctx=context()
        lib=source('LIB','',decl=DECL+' value:INTEGER',routines="ROUTINE publish BEGIN value=42 cursor=1 ADD_BYNAMEPC(buffer,cursor,'','value',s) SEND_DATAPC(1,buffer,s) END publish")
        p=translate_project({'lib':lib,'main':source('MAIN','n=5 publish',routines='ROUTINE publish FROM LIB')}).instantiate(context=ctx)
        p.run('MAIN');self.assertEqual(p.programs['MAIN'].snapshot()['N'],5)
        self.assertEqual(ctx.pc_exchange.snapshot()[0]['data'],'00100000002a0000')

    def test_nested_program_call_shares_outbox_and_retains_events_on_stop(self):
        ctx=context();p=translate_project({'main':source('MAIN',"CALL_PROG('CHILD',s)"),
            'child':source('CHILD','SEND_EVENTPC(7,s) PAUSE')}).instantiate(context=ctx)
        p.run('MAIN');p.scheduler.stop('MAIN')
        self.assertEqual(ctx.pc_exchange.snapshot(),[{'sequence':1,'event':7,'data':None}])


class PcPersistenceTests(unittest.TestCase):
    def test_json_context_roundtrip_keeps_unknown_tail_and_outbox(self):
        ctx=context();packet(ctx,'cursor=1 ADD_INTPC(buffer,cursor,5,s) SEND_DATAPC(12,buffer,s) SEND_EVENTPC(1,s)')
        config=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(config)
        self.assertEqual(json.loads(json.dumps(restored.to_config())),config)
        self.assertEqual(run('SEND_EVENTPC(2,s)',context=restored)['S'],0)
        self.assertEqual(restored.pc_exchange.snapshot()[-1]['sequence'],3)

    def test_raw_saved_packet_can_contain_marker_and_custom_bytes(self):
        bank=rt.PcExchange(packet_format='raw');self.assertEqual(bank.send(9,b'\0\0\x09\xff'),0)
        saved=bank.to_config();self.assertEqual(rt.PcExchange.from_config(saved).to_config(),saved)
        saved['format']='typed'
        with self.assertRaises(ValueError):rt.PcExchange.from_config(saved)

    def test_invalid_capacities_formats_and_counters_reject(self):
        for capacity in (0,32768,True):
            with self.assertRaises(ValueError):rt.PcExchange(capacity)
        for config in ({'format':'other'},{'sequence':True},{'sequence':-1},{'sequence':MAX_SEQUENCE+1},{'extra':1}):
            with self.assertRaises(ValueError):rt.PcExchange.from_config(config)

    def test_invalid_saved_messages_are_bounded_and_ordered(self):
        base={'capacity':2,'format':'typed','sequence':2,'messages':[{'sequence':1,'event':7,'data':'0010000000050000'}]}
        for key,value in [('sequence',0),('sequence',3),('event',256),('event',True),('data','0'),('data','zz'),('data','00'*245),('data','00000000')]:
            saved=deepcopy(base);saved['messages'][0][key]=value
            with self.assertRaises(ValueError):rt.PcExchange.from_config(saved)
        for rows in ([base['messages'][0]]*2,[base['messages'][0]]*3,[{'sequence':1,'event':1}]):
            saved=deepcopy(base);saved['messages']=rows
            with self.assertRaises(ValueError):rt.PcExchange.from_config(saved)

    def test_sequence_exhaustion_rejects_without_publication(self):
        bank=rt.PcExchange.from_config({'sequence':MAX_SEQUENCE})
        self.assertEqual(bank.send(1),5);self.assertEqual(bank.snapshot(),[])

    def test_full_outbox_recovers_after_drain_without_reusing_sequence(self):
        bank=rt.PcExchange(1);self.assertEqual(bank.send(1),0);self.assertEqual(bank.send(2),5)
        self.assertEqual(bank.drain(),[{'sequence':1,'event':1,'data':None}])
        self.assertEqual(bank.send(2),0)
        self.assertEqual(rt.PcExchange.from_config(bank.to_config()).snapshot(),[{'sequence':2,'event':2,'data':None}])

    def test_snapshots_and_config_rows_are_detached(self):
        bank=rt.PcExchange();bank.send(7);snapshot=bank.snapshot();snapshot[0]['event']=99
        config=bank.to_config();config['messages'].clear()
        self.assertEqual(bank.snapshot(),[{'sequence':1,'event':7,'data':None}])

    def test_decoder_retains_negative_zero_and_bounds_its_input(self):
        data=b'\0\x11'+struct.pack('>f',-0.)+b'\0\0';payload,items=decode_packet(data)
        self.assertEqual(payload,data);self.assertEqual(math.copysign(1,items[0]['value']),-1)
        for data in (b'',b'\0'*245):
            with self.assertRaises(rt.KarelRuntimeError):decode_packet(data)

    def test_public_host_send_accepts_bytes_and_arrays_and_rejects_unknown_types(self):
        bank=rt.PcExchange(packet_format='raw');array=rt.Array(('ARRAY',1,('BYTE',)));array.values[0]=255
        self.assertEqual(bank.send(1,array),0);self.assertEqual(bank.snapshot()[0]['data'],'ff')
        self.assertEqual(bank.send(1,object()),4)


if __name__=='__main__':unittest.main()
