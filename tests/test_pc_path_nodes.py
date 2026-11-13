"""Named PATH-node PC data and captured reference guards across preparation."""
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py.pc_exchange import decode_packet
from tests.test_extended_services import compile_program
from tests.test_pc_exchange import context
from tests.test_project_scheduler import source
from tests.test_cartesian_interfaces import value as pose


TYPES='TYPE node_t=STRUCTURE amount:INTEGER enabled:BOOLEAN ENDSTRUCTURE'
DECL='route:PATH NODEDATA=node_t buffer:ARRAY[244]OF BYTE cursor,s:INTEGER'
FILL='APPEND_NODE(route,s) route[1].amount=17 route[1].enabled=TRUE '
B={'unknown_byte':True}


def build(body='',prefix=TYPES,decl=DECL,ctx=None):
    ctx=context() if ctx is None else ctx
    p,result=compile_program(body,decl=decl,prefix=prefix,context=ctx)
    return p,ctx,result.report


def emitted(body=FILL,path='route[1]',**options):
    p,ctx,report=build(body+f"cursor=1 ADD_BYNAMEPC(buffer,cursor,'','{path}',s) SEND_DATAPC(7,buffer,s)",**options)
    assert p.run()['S']==0
    return decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1],p,ctx,report


class PathNodePcTests(unittest.TestCase):
    def test_complete_scalar_path_node_expands_existing_items(self):
        items,p,_,report=emitted()
        self.assertEqual(items,[{'type':'INTEGER','value':17},{'type':'INTEGER','value':1}])
        self.assertEqual(p.snapshot()['CURSOR'],13)
        self.assertEqual(p.snapshot()['ROUTE']['nodes'],[{'AMOUNT':17,'ENABLED':True}])
        self.assertIn('selected',report['pc_path_node_policy']['source'])
        self.assertFalse(report['pc_path_node_policy']['controller_validated'])

    def test_selected_scalar_and_nested_record_fields(self):
        self.assertEqual(emitted(path='route[1].amount')[0],[{'type':'INTEGER','value':17}])
        self.assertEqual(emitted(path='route[1].enabled')[0],[{'type':'INTEGER','value':1}])
        prefix='TYPE child_t=STRUCTURE code:BYTE label:STRING[2] ENDSTRUCTURE node_t=STRUCTURE data:child_t ENDSTRUCTURE'
        items,_,_,_=emitted("APPEND_NODE(route,s) route[1].data.code=255 route[1].data.label='ok' ",
                            path='route[1].data',prefix=prefix)
        self.assertEqual(items,[{'type':'INTEGER','value':255},{'type':'STRING','value':'ok'}])

    def test_selected_joint_data_needs_no_robot_model(self):
        prefix='TYPE node_t=STRUCTURE axes:JOINTPOS2 ENDSTRUCTURE'
        items,_,ctx,_=emitted('APPEND_NODE(route,s) route[1].axes[1]=1 route[1].axes[2]=-2 ',path='route[1].axes',prefix=prefix)
        self.assertEqual([item['value'] for item in items],[1.,-2.]);self.assertIsNone(ctx.robot)

    def test_default_node_position_and_readable_columns(self):
        p,ctx,_=build("cursor=1 ADD_BYNAMEPC(buffer,cursor,'','route[1].node_pos.location',s) SEND_DATAPC(7,buffer,s)",
                      prefix='',decl=DECL.replace('PATH NODEDATA=node_t','PATH'))
        route=p._state.raw('ROUTE');node=rt.Structure(route.node_spec);node.values['NODE_POS']=pose('POSITION');route.nodes.append(node)
        self.assertEqual(p.run()['S'],0)
        self.assertEqual([item['value'] for item in decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1]],[1.,2.,3.])

    def test_bank_nodes_accept_comma_and_chained_static_indexes(self):
        for path in ('routes[2,1]','routes[2][1]'):
            items,_,_,_=emitted('APPEND_NODE(routes[2],s) routes[2][1].amount=17 routes[2][1].enabled=TRUE ',
                                path=path,decl=DECL.replace('route:PATH NODEDATA=node_t','routes:ARRAY[2]OF PATH NODEDATA=node_t'))
            self.assertEqual([item['value'] for item in items],[17,1])

    def test_header_records_keep_the_existing_named_data_contract(self):
        prefix=TYPES+' head_t=STRUCTURE data:node_t ENDSTRUCTURE'
        decl=DECL.replace('PATH NODEDATA=node_t','PATH NODEDATA=node_t PATHHEADER=head_t')
        self.assertEqual([item['value'] for item in emitted('route.data.amount=17 route.data.enabled=TRUE ',path='route.data',prefix=prefix,decl=decl)[0]],[17,1])

    def test_explicit_foreign_path_root_has_no_discovery(self):
        p,ctx,_=build('cursor=1 ADD_BYNAMEPC(buffer,cursor,\'CACHE\',\'ROUTE[1]\',s) SEND_DATAPC(7,buffer,s)')
        schema=p._state.types['ROUTE'];reference=ctx.variables.define('CACHE','ROUTE',schema)
        node=rt.Structure(reference.raw().node_spec);node.values.update(AMOUNT=17,ENABLED=True);reference.raw().nodes.append(node)
        self.assertEqual(p.run()['S'],0)
        self.assertEqual([item['value'] for item in decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1]],[17,1])

    def test_source_linkage_reads_owned_path_nodes(self):
        main=source('MAIN','work',routines='ROUTINE work FROM LIB')
        lib=source('LIB','',decl=DECL,routines='ROUTINE work BEGIN '+FILL+"cursor=1 ADD_BYNAMEPC(buffer,cursor,'','route[1]',s) SEND_DATAPC(7,buffer,s) END work").replace('VAR route:',TYPES+' VAR route:')
        ctx=context();project=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);project.run('MAIN')
        self.assertEqual([item['value'] for item in decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1]],[17,1])

    def test_saved_path_data_and_typed_packet_replay(self):
        _,_,ctx,_=emitted();saved=json.loads(json.dumps(ctx.to_config()))
        self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_unknown_node_fields_and_full_resources_keep_status_boundaries(self):
        for path,status in [('route[0]',1),('route[2]',1),('route[1,1]',1),('route[1].missing',1),('route',4)]:
            p,_,_=build(FILL+f"cursor=1 ADD_BYNAMEPC(buffer,cursor,'','{path}',s)")
            state=p.run();self.assertEqual((state['S'],state['CURSOR']),(status,1))
            self.assertEqual(state['BUFFER'],[B]*244)
        p,_,_=build("APPEND_NODE(route,s) route[1].amount=17 cursor=1 ADD_BYNAMEPC(buffer,cursor,'','route[1]',s)")
        self.assertEqual(p.run()['S'],4)

    def test_large_unselected_path_is_not_cloned_or_budgeted_as_a_packet(self):
        p,_,_=build("cursor=1 ADD_BYNAMEPC(buffer,cursor,'','route[1]',s)")
        route=p._state.raw('ROUTE');route.nodes[:]=[rt.Structure(route.node_spec) for _ in range(1000)]
        route.nodes[0].values.update(AMOUNT=17,ENABLED=True)
        with patch.object(rt.PathValue,'clone',side_effect=AssertionError('must not clone the PATH')):
            self.assertEqual(p.run(max_steps=30)['S'],0)

    def test_bank_node_data_copy_happens_after_scalar_capture_charges(self):
        decl=DECL.replace('route:PATH NODEDATA=node_t','routes:ARRAY[2]OF PATH NODEDATA=node_t')
        p,_,_=build("cursor=1 ADD_BYNAMEPC(buffer,cursor,'','routes[2,1]',s)",decl=decl)
        route=p._state.raw('ROUTES').values[1];node=rt.Structure(route.node_spec);node.values.update(AMOUNT=17,ENABLED=True);route.nodes.append(node)
        tick=p._state.tick;copy=rt._aggregate_value;seen=[]
        def charge(line=None):
            if any(row['operation']=='ADD_BYNAMEPC' for row in p.service_requests):seen.append(1)
            return tick(line)
        def capture(spec,value,*args,**kwargs):
            if spec==route.node_spec:self.assertGreaterEqual(len(seen),3)
            return copy(spec,value,*args,**kwargs)
        with patch.object(p._state,'tick',side_effect=charge),patch.object(rt,'_aggregate_value',side_effect=capture):
            self.assertEqual(p.run()['S'],0)

    def test_removed_node_during_charging_raises_without_buffer_or_status_writes(self):
        p,_,_=build(FILL+"cursor=1 s=77 ADD_BYNAMEPC(buffer,cursor,'','route[1]',s)")
        original=p._state.tick;seen=[]
        def tick(line=None):
            if any(row['operation']=='ADD_BYNAMEPC' for row in p.service_requests):
                seen.append(1)
                if len(seen)==2:p._state.raw('ROUTE').nodes.clear()
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick),self.assertRaisesRegex(rt.KarelRuntimeError,'source binding changed'):p.run()
        self.assertEqual((p.snapshot()['S'],p.snapshot()['CURSOR'],p.snapshot()['BUFFER']),(77,1,[B]*244))


class PcReferencePublicationTests(unittest.TestCase):
    def builder(self,call='ADD_INTPC(buffer,cursor,7,s)',decl=''):
        return build('value[1]=7 value[2]=9 cursor=1 s=77 '+call,decl='buffer:ARRAY[32]OF BYTE cursor,s:INTEGER value:ARRAY[2]OF INTEGER '+decl,prefix='')[0]

    def mutate(self,p,callback,at=1):
        original=p._state.tick;seen=[]
        def tick(line=None):
            result=original(line)
            if any(row['operation'].startswith('ADD_') for row in p.service_requests):
                seen.append(1)
                if len(seen)==at:callback()
            return result
        return patch.object(p._state,'tick',side_effect=tick)

    def test_builder_status_binding_retargeting_is_preserved(self):
        for call,at in [('ADD_INTPC(buffer,cursor,7,s)',1),("ADD_BYNAMEPC(buffer,cursor,'','value',s)",2)]:
            p=self.builder(call);old={'value':77};new={'value':55};ref=rt.Reference(rt.INTEGER,old,'value');p._state.values['S']=ref
            with self.mutate(p,lambda:setattr(ref,'storage',new),at),self.assertRaisesRegex(rt.KarelRuntimeError,'reference binding changed'):p.run()
            self.assertEqual((old,new),({'value':77},{'value':55}))
            self.assertEqual((p.snapshot()['CURSOR'],p.snapshot()['BUFFER']),(1,[B]*32))

    def test_builder_index_binding_retargeting_is_preserved(self):
        p=self.builder();old={'value':1};new={'value':2};ref=rt.Reference(rt.INTEGER,old,'value');p._state.values['CURSOR']=ref
        with self.mutate(p,lambda:setattr(ref,'storage',new)),self.assertRaisesRegex(rt.KarelRuntimeError,'reference binding changed'):p.run()
        self.assertEqual((old,new),({'value':1},{'value':2}));self.assertEqual(p.snapshot()['S'],77)

    def test_builder_status_schema_change_is_not_reinterpreted(self):
        p=self.builder();ref=rt.Reference(rt.INTEGER,{'value':77},'value');p._state.values['S']=ref
        with self.mutate(p,lambda:setattr(ref,'spec',rt.REAL)),self.assertRaisesRegex(rt.KarelRuntimeError,'reference binding changed'):p.run()
        self.assertEqual(ref.raw(),77);self.assertEqual(p.snapshot()['BUFFER'],[B]*32)

    def test_status_key_removal_preserves_completed_deletion(self):
        p=self.builder();mapping={'value':77};ref=rt.Reference(rt.INTEGER,mapping,'value');p._state.values['S']=ref
        with self.mutate(p,lambda:mapping.pop('value')),self.assertRaisesRegex(rt.KarelRuntimeError,'reference binding changed'):p.run()
        self.assertEqual(mapping,{});self.assertEqual(rt.snapshot_value(p._state.raw('BUFFER')),[B]*32)

    def test_named_source_reference_retargeting_cannot_silently_change_packet_input(self):
        p=self.builder("ADD_BYNAMEPC(buffer,cursor,'','value',s)")
        value=p._state.raw('VALUE');old={'value':value};ref=rt.Reference(value.spec,old,'value');p._state.values['VALUE']=ref
        new={'value':rt.Array(value.spec)}
        with self.mutate(p,lambda:setattr(ref,'storage',new),2),self.assertRaisesRegex(rt.KarelRuntimeError,'source binding changed'):p.run()
        self.assertIs(ref.raw(),new['value']);self.assertEqual((p.snapshot()['S'],p.snapshot()['CURSOR']),(77,1))

    def test_plain_index_value_change_at_initial_checkpoint_remains_allowed(self):
        p=self.builder()
        with self.mutate(p,lambda:p._state.values.__setitem__('CURSOR',2)):state=p.run()
        self.assertEqual((state['S'],state['CURSOR'],state['BUFFER'][0]),(0,8,B))

    def test_send_status_retargeting_during_packet_preparation_publishes_no_event(self):
        p,ctx,_=build('cursor=1 ADD_INTPC(buffer,cursor,7,s) s=77 SEND_DATAPC(7,buffer,s)',prefix='',decl='buffer:ARRAY[8]OF BYTE cursor,s:INTEGER')
        old={'value':77};new={'value':55};ref=rt.Reference(rt.INTEGER,old,'value');p._state.values['S']=ref
        original=p._state.tick;send=ctx.pc_exchange.send;inside=[]
        def transmit(*args,**kwargs):
            inside.append(True)
            try:return send(*args,**kwargs)
            finally:inside.pop()
        def tick(line=None):
            result=original(line)
            if inside:ref.storage=new
            return result
        with patch.object(ctx.pc_exchange,'send',side_effect=transmit),patch.object(p._state,'tick',side_effect=tick),self.assertRaisesRegex(rt.KarelRuntimeError,'status binding changed'):p.run()
        self.assertEqual((old,new),({'value':77},{'value':55}))
        self.assertEqual((ctx.pc_exchange.snapshot(),ctx.pc_exchange.sequence),([],0))


if __name__=='__main__':unittest.main()
