"""Atomic named PC data batches use the existing scalar tags and checked storage."""
import json
import struct
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py.pc_exchange import decode_packet
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source
from tests.test_pc_exchange import context
from tests.test_cartesian_interfaces import value as pose


U={'uninitialized':True}
B={'unknown_byte':True}
DECL='buffer:ARRAY[244]OF BYTE cursor,s,n:INTEGER'
CALL="ADD_BYNAMEPC(buffer,cursor,'','value',s)"


def build(body='',decl='value:ARRAY[2]OF INTEGER',prefix='',routines='',ctx=None,buffer=244):
    ctx=context() if ctx is None else ctx
    p,result=compile_program(body,decl=DECL.replace('[244]',f'[{buffer}]')+' '+decl,prefix=prefix,routines=routines,context=ctx)
    return p,ctx,result.report


def sent(fill,**options):
    p,ctx,report=build(fill+' cursor=1 '+CALL+' SEND_DATAPC(7,buffer,s)',**options)
    values=p.run();assert values['S']==0
    packet=bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data'])
    return decode_packet(packet)[1],packet,p,ctx,report


class NamedPcScalarTests(unittest.TestCase):
    def test_boolean_and_narrow_values_map_to_integer_items(self):
        for kind,fill,expected in [('BOOLEAN','value=TRUE',1),('BOOLEAN','value=FALSE',0),
                                    ('BYTE','value=255',255),('SHORT','value=-9',-9)]:
            with self.subTest(kind=kind,fill=fill):
                items,data,_,_,_=sent(fill,decl='value:'+kind)
                self.assertEqual(items,[{'type':'INTEGER','value':expected}])
                self.assertEqual(data,b'\0\x10'+struct.pack('>i',expected)+b'\0\0')

    def test_unknown_byte_short_sentinel_and_uninitialized_boolean_reject(self):
        for kind in ('BYTE','SHORT','BOOLEAN'):
            p,ctx,_=build('cursor=1 '+CALL,decl='value:'+kind)
            values=p.run();self.assertEqual((values['S'],values['CURSOR']),(4,1))
            self.assertEqual(values['BUFFER'],[B]*244);self.assertEqual(ctx.pc_exchange.snapshot(),[])

    def test_transparent_alias_preserves_narrow_domain_validation(self):
        items,_,_,_,_=sent('value=255',decl='value:small_t',prefix='TYPE small_t=BYTE')
        self.assertEqual(items,[{'type':'INTEGER','value':255}])


class NamedPcAggregateTests(unittest.TestCase):
    def test_array_items_are_row_major_with_one_final_marker(self):
        fill='value[1,1]=1 value[1,2]=2 value[2,1]=3 value[2,2]=4'
        items,data,p,_,_=sent(fill,decl='value:ARRAY[2,2]OF INTEGER')
        self.assertEqual([item['value'] for item in items],[1,2,3,4])
        self.assertEqual(data,b''.join(b'\0\x10'+struct.pack('>i',n) for n in (1,2,3,4))+b'\0\0')
        self.assertEqual(p.snapshot()['CURSOR'],25)

    def test_records_expand_in_declaration_order_and_mix_existing_tags(self):
        types='TYPE item_t=STRUCTURE ready:BOOLEAN small:SHORT amount:REAL text:STRING[4] code:BYTE ENDSTRUCTURE'
        items,data,_,_,_=sent("value.ready=TRUE value.small=-2 value.amount=1.5 value.text='ok' value.code=255",decl='value:item_t',prefix=types)
        self.assertEqual(items,[{'type':'INTEGER','value':1},{'type':'INTEGER','value':-2},
                                {'type':'REAL','value':1.5},{'type':'STRING','value':'ok'},{'type':'INTEGER','value':255}])
        self.assertEqual(data.hex(),'0010000000010010fffffffe00113fc0000000d1026f6b000010000000ff0000')

    def test_named_array_components_and_record_fields_retain_order(self):
        types='TYPE row_t=ARRAY[2]OF INTEGER item_t=STRUCTURE grid:ARRAY[2]OF row_t ENDSTRUCTURE'
        fill='value.grid[1,1]=1 value.grid[1,2]=2 value.grid[2,1]=3 value.grid[2,2]=4'
        items,_,p,_,_=sent(fill,decl='value:item_t',prefix=types)
        self.assertEqual([item['value'] for item in items],[1,2,3,4])
        self.assertEqual(p._state.raw('VALUE').values['GRID'].spec[2][-1],'ROW_T')

    def test_selected_named_row_can_be_inserted(self):
        types='TYPE row_t=ARRAY[2]OF INTEGER'
        body="value[2,1]=7 value[2,2]=9 cursor=1 ADD_BYNAMEPC(buffer,cursor,'','value[2]',s) SEND_DATAPC(7,buffer,s)"
        p,ctx,_=build(body,decl='value:ARRAY[2]OF row_t',prefix=types);self.assertEqual(p.run()['S'],0)
        self.assertEqual([item['value'] for item in decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1]],[7,9])

    def test_joint_axes_become_real_items_without_robot_context(self):
        items,_,_,ctx,_=sent('value[1]=1 value[2]=-2',decl='value:JOINTPOS2')
        self.assertEqual(items,[{'type':'REAL','value':1.},{'type':'REAL','value':-2.}]);self.assertIsNone(ctx.robot)

    def test_vector_and_cartesian_fields_use_existing_data_order(self):
        items,_,_,_,_=sent('value=VEC(1,2,3)',decl='value:VECTOR')
        self.assertEqual([item['value'] for item in items],[1.,2.,3.])
        p,ctx,_=build('cursor=1 '+CALL+' SEND_DATAPC(7,buffer,s)',decl='value:XYZWPR')
        p._state.values['VALUE']=pose('XYZWPR');self.assertEqual(p.run()['S'],0)
        items=decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1]
        self.assertTrue(any(item['type']=='REAL' for item in items))
        self.assertTrue(any(item['type']=='INTEGER' for item in items))

    def test_initialized_position_readonly_columns_can_be_serialized(self):
        p,ctx,_=build('cursor=1 '+CALL+' SEND_DATAPC(7,buffer,s)',decl='value:POSITION')
        with rt._numeric_scope('pythonic'):p._state.values['VALUE']=rt.convert_position(('POSITION',),pose('XYZWPR'))
        self.assertEqual(p.run()['S'],0)
        items=decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1]
        self.assertEqual(len(items),rt.scalar_leaf_count(('POSITION',)))

    def test_string_arrays_keep_empty_and_embedded_nul_values(self):
        items,_,_,_,_=sent("value[1]='' value[2]='A'+CHR(0)+'B'",decl='value:ARRAY[2]OF STRING[4]')
        self.assertEqual([item['value'] for item in items],['','A\0B'])

    def test_maximum_empty_string_batch_fits_one_packet(self):
        fill=' '.join(f"value[{index}]=''" for index in range(1,61))
        items,data,p,_,_=sent(fill,decl='value:ARRAY[60]OF STRING[1]')
        self.assertEqual((len(items),len(data),p.snapshot()['CURSOR']),(60,242,241))
        self.assertTrue(all(item=={'type':'STRING','value':''} for item in items))

    def test_multiple_builders_append_batches_and_keep_prefix_tail_and_identity(self):
        body='buffer[1]=99 value[1]=7 value[2]=9 cursor=2 '+CALL+' ADD_INTPC(buffer,cursor,11,s)'
        p,_,_=build(body,buffer=32);original=p._state.raw('BUFFER');values=p.run()
        expected=b'\0\x10'+struct.pack('>i',7)+b'\0\x10'+struct.pack('>i',9)+b'\0\x10'+struct.pack('>i',11)+b'\0\0'
        self.assertEqual(values['BUFFER'][:21],[99,*expected])
        self.assertEqual(values['BUFFER'][21:],[B]*11);self.assertEqual(values['CURSOR'],20)
        self.assertIs(p._state.raw('BUFFER'),original)

    def test_buffer_and_index_can_also_be_named_source_data(self):
        p,ctx,_=build("value[1]=1 value[2]=2 cursor=1 ADD_BYNAMEPC(buffer,cursor,'','cursor',s) "+CALL+' SEND_DATAPC(7,buffer,s)')
        self.assertEqual(p.run()['S'],0)
        self.assertEqual([item['value'] for item in decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1]],[1,1,2])

    def test_missing_whole_buffer_storage_is_initialized_after_complete_batch(self):
        ctx=context();spec=('ARRAY',14,rt.BYTE)
        ctx.variables.bind('T','BUFFER',rt.Reference(spec,{'value':rt.UNINITIALIZED},'value'))
        _,data,p,_,_=sent('value[1]=7 value[2]=9',ctx=ctx,buffer=14)
        self.assertEqual(p.snapshot()['BUFFER'],list(data))


class NamedPcLookupAndLifetimeTests(unittest.TestCase):
    def test_explicit_dynamic_roots_and_static_fields_are_supported(self):
        ctx=context();ctx.variables.define('CACHE','DATA',('ARRAY',2,rt.BYTE))
        ctx.variables.bindings['CACHE','DATA'].raw().set(1,7);ctx.variables.bindings['CACHE','DATA'].raw().set(2,9)
        p,ctx,_=build("cursor=1 ADD_BYNAMEPC(buffer,cursor,'cache','data',s) SEND_DATAPC(7,buffer,s)",decl='',ctx=ctx)
        self.assertEqual(p.run()['S'],0)
        self.assertEqual([item['value'] for item in decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1]],[7,9])

    def test_linked_blank_program_reads_the_executing_module(self):
        ctx=context();main=source('MAIN','work',routines='ROUTINE work FROM LIB')
        lib=source('LIB','',decl='value:ARRAY[2]OF INTEGER '+DECL,
            routines="ROUTINE work BEGIN value[1]=7 value[2]=9 cursor=1 "+CALL+' SEND_DATAPC(7,buffer,s) END work')
        project=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);project.run('MAIN')
        self.assertEqual([item['value'] for item in decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1]],[7,9])

    def test_outbox_and_complete_source_data_survive_json_replay(self):
        _,data,p,ctx,_=sent('value[1]=7 value[2]=9')
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved)
        self.assertEqual(restored.pc_exchange.snapshot()[0]['data'],data.hex())
        self.assertEqual(p.snapshot()['VALUE'],[7,9])

    def test_builders_work_without_configuring_a_pc_outbox(self):
        p,_,_=build('value[1]=7 value[2]=9 cursor=1 '+CALL,ctx=rt.ExecutionContext())
        self.assertEqual((p.run()['S'],p.snapshot()['CURSOR']),(0,13))

    def test_direct_scalar_builders_and_existing_named_scalar_bytes_do_not_change(self):
        expected=b'\0\x10'+struct.pack('>i',7)+b'\0\0'
        self.assertEqual(sent('value=7',decl='value:INTEGER')[1],expected)
        p,ctx,_=build('cursor=1 ADD_INTPC(buffer,cursor,7,s) SEND_DATAPC(7,buffer,s)',decl='')
        self.assertEqual(p.run()['S'],0);self.assertEqual(ctx.pc_exchange.snapshot()[0]['data'],expected.hex())

    def test_report_exposes_named_batch_encoding_and_atomicity(self):
        _,_,report=build()
        policy=report['pc_named_data_policy']
        self.assertFalse(policy['controller_validated'])
        self.assertEqual(policy['guide'],'docs/pc-named-data.md')
        self.assertIn('BYTE/SHORT/BOOLEAN',policy['encoding'])
        self.assertIn('without overwriting status',policy['publication'])


class NamedPcAtomicityTests(unittest.TestCase):
    def test_missing_leaf_unknown_byte_and_narrow_sentinel_reject_whole_batch(self):
        for kind,fill in [('INTEGER','value[1]=7'),('BYTE','value[1]=7'),('SHORT','value[1]=7')]:
            p,_,_=build(fill+' cursor=1 '+CALL,decl=f'value:ARRAY[2]OF {kind}')
            values=p.run();self.assertEqual((values['S'],values['CURSOR'],values['BUFFER']),(4,1,[B]*244))

    def test_later_float32_overflow_keeps_the_entire_prior_packet(self):
        p,_,_=build('cursor=1 ADD_INTPC(buffer,cursor,19,s) value[1]=1 value[2]=1.0E100 '+CALL,decl='value:ARRAY[2]OF REAL')
        values=p.run();self.assertEqual((values['S'],values['CURSOR']),(4,7))
        self.assertEqual(values['BUFFER'][:8],list(bytes.fromhex('0010000000130000')))
        self.assertEqual(values['BUFFER'][8:],[B]*236)

    def test_exact_batch_capacity_and_short_buffer(self):
        for size,status in [(13,3),(14,0)]:
            p,_,_=build('value[1]=7 value[2]=9 cursor=1 '+CALL,buffer=size)
            values=p.run();self.assertEqual(values['S'],status)
            self.assertEqual(values['CURSOR'],1 if status else 13)
            if status:self.assertEqual(values['BUFFER'],[B]*size)

    def test_schema_lower_bound_rejects_large_arrays_before_copy_or_budget_capture(self):
        p,_,_=build('cursor=1 '+CALL,decl='value:ARRAY[32767]OF INTEGER')
        with patch.object(rt,'capture_aggregate_write',side_effect=AssertionError('must not expand')):
            values=p.run(max_steps=20)
        self.assertEqual((values['S'],values['CURSOR']),(3,1))

    def test_resources_retain_their_boundaries(self):
        for kind in ('FILE','PATH','QUEUE_TYPE','ARRAY[2]OF FILE','ARRAY[2]OF QUEUE_TYPE'):
            p,_,_=build('cursor=1 '+CALL,decl='value:'+kind)
            values=p.run();self.assertEqual((values['S'],values['CURSOR']),(4,1))
        p,_,_=build("cursor=1 ADD_BYNAMEPC(buffer,cursor,'','value[1]',s)",decl='value:ARRAY[2,2]OF INTEGER')
        self.assertEqual(p.run()['S'],4)  # selected incomplete data, no longer a missing path

    def test_malformed_source_shape_does_not_publish_prefix_items(self):
        p,_,_=build('cursor=1 '+CALL);p._state.raw('VALUE').shape=(3,)
        values=p.run();self.assertEqual((values['S'],values['CURSOR'],values['BUFFER']),(4,1,[B]*244))

    def test_malformed_late_string_keeps_the_existing_marker(self):
        p,_,_=build('cursor=1 ADD_INTPC(buffer,cursor,19,s) '+CALL,
            decl='value:item_t',prefix='TYPE item_t=STRUCTURE number:INTEGER text:STRING[2] ENDSTRUCTURE')
        value=p._state.raw('VALUE');value.values['NUMBER']=7;value.values['TEXT']='long'
        snapshot=p.run();self.assertEqual((snapshot['S'],snapshot['CURSOR']),(4,7))
        self.assertEqual(snapshot['BUFFER'][:8],list(bytes.fromhex('0010000000130000')))

    def test_source_schema_change_during_charging_is_not_reinterpreted(self):
        ctx=context();schema=('ARRAY',2,rt.INTEGER);value=rt.Array(schema);value.values[:]=[7,9]
        reference=rt.Reference(schema,{'value':value},'value');ctx.variables.bind('CACHE','DATA',reference)
        p,_,_=build("cursor=1 s=23 ADD_BYNAMEPC(buffer,cursor,'CACHE','DATA',s)",decl='',ctx=ctx)
        original=p._state.tick;seen=[]
        def tick(line=None):
            if any(row['operation']=='ADD_BYNAMEPC' for row in p.service_requests):
                seen.append(1)
                if len(seen)==2:reference.spec=('ARRAY',3,rt.INTEGER)
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick),self.assertRaisesRegex(rt.KarelRuntimeError,'schema changed'):p.run()
        self.assertEqual((p.snapshot()['S'],p.snapshot()['CURSOR'],p.snapshot()['BUFFER']),(23,1,[B]*244))

    def test_pure_resource_and_oversize_failures_do_not_rewrite_prior_data(self):
        p,_,_=build('cursor=1 ADD_INTPC(buffer,cursor,19,s) '+CALL,decl='value:ARRAY[61]OF STRING[1]')
        snapshot=p.run();self.assertEqual((snapshot['S'],snapshot['CURSOR']),(3,7))
        self.assertEqual(snapshot['BUFFER'][:8],list(bytes.fromhex('0010000000130000')))

    def test_budget_failure_during_named_capture_preserves_status_buffer_and_index(self):
        p,ctx,_=build('value[1]=7 value[2]=9 cursor=1 s=23 '+CALL)
        original=p._state.tick;seen=[]
        def tick(line=None):
            if any(row['operation']=='ADD_BYNAMEPC' for row in p.service_requests):
                seen.append(1)
                if len(seen)==2:raise rt.KarelRuntimeError('authored budget exhaustion')
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick),self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):p.run()
        self.assertEqual((p.snapshot()['S'],p.snapshot()['CURSOR'],p.snapshot()['BUFFER']),(23,1,[B]*244))
        self.assertEqual(ctx.pc_exchange.snapshot(),[])

    def test_checkpoint_edits_to_buffer_index_or_storage_are_preserved_and_raise(self):
        for mutation in ('contents','index','root','storage'):
            p,_,_=build('value[1]=7 value[2]=9 cursor=1 s=23 '+CALL)
            original=p._state.tick;seen=[]
            def tick(line=None):
                if any(row['operation']=='ADD_BYNAMEPC' for row in p.service_requests):
                    seen.append(1)
                    if len(seen)==2:
                        if mutation=='contents':p._state.raw('BUFFER').values[0]=99
                        elif mutation=='index':p._state.values['CURSOR']=2
                        elif mutation=='root':p._state.values['BUFFER']=rt.Array(p._state.types['BUFFER'])
                        else:p._state.raw('BUFFER').values=list(p._state.raw('BUFFER').values)
                return original(line)
            with self.subTest(mutation=mutation),patch.object(p._state,'tick',side_effect=tick),self.assertRaisesRegex(rt.KarelRuntimeError,'changed'):p.run()
            self.assertEqual(p.snapshot()['S'],23)
            self.assertEqual(p.snapshot()['CURSOR'],2 if mutation=='index' else 1)
            if mutation=='contents':self.assertEqual(p.snapshot()['BUFFER'][0],99)

    def test_source_edits_during_capture_charging_are_read_once_afterward(self):
        p,ctx,_=build('value[1]=7 value[2]=9 cursor=1 '+CALL+' SEND_DATAPC(7,buffer,s)')
        original=p._state.tick;seen=[]
        def tick(line=None):
            if any(row['operation']=='ADD_BYNAMEPC' for row in p.service_requests):
                seen.append(1)
                if len(seen)==2:p._state.raw('VALUE').set(2,11)
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick):self.assertEqual(p.run()['S'],0)
        self.assertEqual([item['value'] for item in decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1]],[7,11])


if __name__=='__main__':unittest.main()
