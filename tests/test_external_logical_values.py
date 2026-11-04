"""Explicit logical external values, argument cases and atomic response batches."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from karel2py.storage import typed_value,tuple_spec
from tests.test_extended_services import compile_program
from tests.test_external_outputs import output,reply,cases
from tests.test_external_values import row,integer,U,B,reference

NODE=['STRUCTURE','NODE_T',[['ID',['INTEGER']],['OCTET',['BYTE']]]]
HEADER=['STRUCTURE','HEADER_T',[['TAG',['INTEGER']]]]
PATH=['PATH',NODE,HEADER]
QUEUE=['QUEUE_TYPE']
PREFIX='TYPE node_t=STRUCTURE id:INTEGER octet:BYTE ENDSTRUCTURE header_t=STRUCTURE tag:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t PATHHEADER=header_t'


def logical(kind,number=17):
    return (row(PATH,dict(nodes=[dict(ID=number,OCTET=B)],data=dict(TAG=7))) if kind=='path'
            else row(QUEUE,dict(initialized=True,sequence=7,entries=[[3,number],[1,9]])))


def initial(kind):
    return (row(PATH,dict(nodes=[],data=dict(TAG=U))) if kind=='path'
            else row(QUEUE,dict(initialized=False,sequence=0,entries=[])))


def callbacks(binding):return rt.external_value_callbacks({'HOST':{'WORK':binding}})


def build(binding,kind='path',*,body='work(n)',params=None,result=None,decl=None,routines='',direct=False,**options):
    name='route_t' if kind=='path' else 'QUEUE_TYPE'
    context=options.pop('context',rt.ExecutionContext())
    context.externals.update({('HOST','WORK'):lambda *args:binding} if direct else callbacks(binding))
    return compile_program(body,prefix=PREFIX,decl=decl or f'n,target:{name} bank:ARRAY[2]OF {name} s,seen:INTEGER',
        routines=f'ROUTINE work({params or "value:"+name})'+(f':{result}' if result else '')+' FROM HOST '+routines,context=context,**options)


def encoded(value):
    with rt._numeric_scope('pythonic'):return typed_value(value)


class LogicalCases:
    def make(self,binding,**options):return build(binding,self.kind,**options)
    @property
    def name(self):return 'route_t' if self.kind=='path' else 'QUEUE_TYPE'
    @property
    def value(self):return logical(self.kind)
    def test_fixed_result(self):
        p,_=self.make(self.value,body='target=work(n)',result=self.name);p.run();self.assertEqual(encoded(p._state.raw('TARGET')),self.value)
    def test_raw_callback_result_with_output_batch(self):
        p,_=self.make(reply(output(1,self.value),result=self.value),result=self.name,body='target=work(n)',direct=True);p.run();self.assertEqual(encoded(p._state.raw('N')),self.value);self.assertEqual(encoded(p._state.raw('TARGET')),self.value)
    def test_callback_result_is_detached_from_json(self):
        value=self.value;p,_=self.make(value,body='target=work(n)',result=self.name,direct=True);p.run();self.assertEqual(value,self.value);self.assertIsNot(p._state.raw('N'),p._state.raw('TARGET'))
    def test_output_replaces_existing_root_in_place(self):
        p,_=self.make(reply(output(1,self.value)));old=p._state.raw('N');p.run();self.assertIs(p._state.raw('N'),old);self.assertEqual(encoded(old),self.value)
    def test_grouped_actual_output_is_private(self):
        p,_=self.make(reply(output(1,self.value)),body='work((n))');p.run();self.assertEqual(encoded(p._state.raw('N')),initial(self.kind))
    def test_collection_result_can_be_private_output_argument(self):
        config={'HOST':{'MAKE':self.value,'WORK':reply(output(1,logical(self.kind,42)))}}
        ctx=rt.ExecutionContext(externals=rt.external_value_callbacks(config));p,_=self.make(reply(),context=ctx,body='work(make())',routines=f'ROUTINE make:{self.name} FROM HOST')
        p._state.execution.externals.update(rt.external_value_callbacks(config));p.run();self.assertEqual(encoded(p._state.raw('N')),initial(self.kind))
    def test_whole_bank_output_preserves_cells(self):
        value=row(['ARRAY',2,self.value['type']],[self.value['value'],logical(self.kind,42)['value']]);p,_=self.make(reply(output(1,value)),params='value:ARRAY OF '+self.name,body='work(bank)');root=p._state.raw('BANK');cells=list(root.values);p.run();self.assertIs(p._state.raw('BANK'),root);self.assertTrue(all(a is b for a,b in zip(cells,root.values)));self.assertEqual(encoded(root),value)
    def test_generic_bank_function_result(self):
        value=row(['ARRAY',2,self.value['type']],[self.value['value']]*2);p,_=self.make(value,params='value:INTEGER',result='ARRAY OF '+self.name,body='bank=work(s)');p.run();self.assertEqual(encoded(p._state.raw('BANK')),value)
    def test_bank_and_scalar_outputs_together(self):
        value=row(['ARRAY',2,self.value['type']],[self.value['value']]*2);p,_=self.make(reply(output(1,value),output(2,integer(42))),params='values:ARRAY OF '+self.name+';status:INTEGER',body='work(bank,s)');p.run();self.assertEqual(encoded(p._state.raw('BANK')),value);self.assertEqual(p.snapshot()['S'],42)
    def test_indexed_cell_output(self):
        p,_=self.make(reply(output(1,self.value)),body='work(bank[2])');p.run();self.assertEqual(encoded(p._state.raw('BANK').values[1]),self.value);self.assertEqual(encoded(p._state.raw('BANK').values[0]),initial(self.kind))
    def test_direct_row_output_is_private(self):
        value=row(['ARRAY',2,self.value['type']],[self.value['value']]*2);p,_=self.make(reply(output(1,value)),params='value:ARRAY OF '+self.name,decl=f'n:ARRAY[2,2]OF {self.name} s:INTEGER',body='work(n[1])');p.run();self.assertEqual(encoded(p._state.raw('N'))['value'][0],[initial(self.kind)['value']]*2)
    def test_byname_row_output_is_live(self):
        value=row(['ARRAY',2,self.value['type']],[self.value['value']]*2);p,_=self.make(reply(output(1,value)),params='value:ARRAY OF '+self.name,decl=f'n:ARRAY[2,2]OF {self.name} s:INTEGER',body="work(BYNAME('','N[1]',s))");p.run();self.assertEqual(encoded(p._state.raw('N'))['value'][0],[self.value['value']]*2);self.assertEqual(encoded(p._state.raw('N'))['value'][1],[initial(self.kind)['value']]*2)
    def test_byname_live_row_case_matching(self):
        value=row(['ARRAY',2,self.value['type']],[initial(self.kind)['value']]*2);p,_=self.make(cases([value],reply(output(1,row(value['type'],[self.value['value']]*2)))),params='value:ARRAY OF '+self.name,decl=f'n:ARRAY[2,2]OF {self.name} s:INTEGER',body="work(BYNAME('','N[2]',s))");p.run();self.assertEqual(encoded(p._state.raw('N'))['value'][1],[self.value['value']]*2)
    def test_matching_initial_collection_and_writing_it(self):
        p,_=self.make(cases([initial(self.kind)],reply(output(1,self.value))));p.run();self.assertEqual(encoded(p._state.raw('N')),self.value)
    def test_match_contains_collection_order_and_metadata(self):
        p,_=self.make(cases([self.value],reply(output(1,initial(self.kind)))));self.install(p,self.value);p.run();self.assertEqual(encoded(p._state.raw('N')),initial(self.kind))
    def test_case_miss_leaves_output_intact(self):
        p,_=self.make(cases([self.value],reply(output(1,self.value))));before=encoded(p._state.raw('N'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'No external value case'):p.run()
        self.assertEqual(encoded(p._state.raw('N')),before)
    def test_case_uses_prior_argument_snapshot(self):
        p,_=self.make(cases([initial(self.kind),integer(U)],reply(output(1,self.value),output(2,integer(42)),result=integer(99))),params='value:'+self.name+';status:INTEGER',result='INTEGER',body='seen=work(n,s)');p.run();self.assertEqual((p.snapshot()['S'],p.snapshot()['SEEN']),(42,99));self.assertEqual(encoded(p._state.raw('N')),self.value)
    def test_duplicate_same_target_output_rejects_atomically(self):
        p,_=self.make(reply(output(1,self.value),output(2,logical(self.kind,42))),params='a,b:'+self.name,body='work(n,n)');before=encoded(p._state.raw('N'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(encoded(p._state.raw('N')),before)
    def test_bank_and_member_overlap_rejects(self):
        value=row(['ARRAY',2,self.value['type']],[self.value['value']]*2);p,_=self.make(reply(output(1,value),output(2,self.value)),params='a:ARRAY OF '+self.name+';b:'+self.name,body='work(bank,bank[1])');before=encoded(p._state.raw('BANK'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(encoded(p._state.raw('BANK')),before)
    def test_invalid_later_output_keeps_logical_root(self):
        p,_=self.make(reply(output(1,self.value),output(2,row(['BOOLEAN'],True))),params='value:'+self.name+';status:INTEGER',body='s=7 work(n,s)');before=encoded(p._state.raw('N'))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(encoded(p._state.raw('N')),before);self.assertEqual(p.snapshot()['S'],7)
    def test_wrong_result_keeps_all_outputs(self):
        p,_=self.make(reply(output(1,self.value),result=integer(42)),result=self.name,body='target=work(n)');before=encoded(p._state.raw('N'))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(encoded(p._state.raw('N')),before)
    def test_malformed_current_storage_keeps_ordinary_output(self):
        p,_=self.make(reply(output(1,integer(42)),output(2,self.value)),params='status:INTEGER;value:'+self.name,body='s=7 work(s,n)');old=p._state.raw('N')
        if self.kind=='path':old.nodes=[object()]
        else:old.sequence=-1
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['S'],7);self.assertIs(p._state.raw('N'),old)
    def test_protected_reference_is_rejected(self):
        value=rt.initial_value(tuple_spec(self.value['type']));ref=rt.ReadOnlyFieldReference(value.spec,{'v':value},'v')
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.external_reply_result(None,reply(output(1,self.value)),[ref])
        self.assertEqual(encoded(value),initial(self.kind))
    def test_pause_defers_outputs_until_return(self):
        p,_=self.make(reply(),result=self.name,body='target=work(n)');binding=reply(output(1,self.value),result=self.value)
        def callback(value):
            yield dict(kind='pause',line=1)
            return binding
        p._state.execution.externals['HOST','WORK']=callback
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(encoded(p._state.raw('N')),initial(self.kind));p.resume();self.assertEqual(encoded(p._state.raw('N')),self.value);self.assertEqual(p._state.local_frames,[])
    def test_stop_discards_suspended_response(self):
        p,_=self.make(reply());binding=reply(output(1,self.value))
        def callback(value):
            yield dict(kind='pause',line=1)
            return binding
        p._state.execution.externals['HOST','WORK']=callback
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(encoded(p._state.raw('N')),initial(self.kind));self.assertEqual(p._state.local_frames,[])
    def test_linked_forwarding_retains_borrowed_argument(self):
        p,_=self.make(reply(output(1,self.value)),body='forward(n)',routines=f'ROUTINE forward(value:{self.name}) BEGIN work(value) END forward');p.run();self.assertEqual(encoded(p._state.raw('N')),self.value)
    def test_created_storage_output(self):
        p,_=self.make(reply(output(1,self.value)),body=f"CREATE_VAR('CACHE','ITEM','T','{self.name}',0,0,0,0,s) work(BYNAME('CACHE','ITEM',s))")
        p.run();ref=p._state.execution.variables.bindings['CACHE','ITEM'];self.assertEqual(encoded(ref.raw()),self.value)
    def test_binding_mutation_after_prepare_cannot_change_output(self):
        binding=reply(output(1,self.value));p,_=self.make(binding);binding['outputs'].clear();p.run();self.assertEqual(encoded(p._state.raw('N')),self.value)
    def test_fresh_responses_and_saved_globals(self):
        bank=callbacks(reply(output(1,self.value)));first=bank['HOST','WORK']();first['outputs'].clear();self.assertEqual(len(bank['HOST','WORK']()['outputs']),1)
        p,_=self.make(reply(output(1,self.value)));p.run();saved=p._state.execution.to_config();self.assertNotIn('externals',saved);self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def install(self,p,value):
        with rt._numeric_scope('pythonic'):p._state.values['N']=rt.external_collection_result(tuple_spec(value['type']),value)


class PathExternalLogicalTests(LogicalCases,unittest.TestCase):kind='path'
class QueueExternalLogicalTests(LogicalCases,unittest.TestCase):kind='queue'


class PathOwnershipTests(unittest.TestCase):
    def test_header_alias_survives_and_nodes_detach(self):
        p,_=build(reply(output(1,logical('path'))));old=p._state.raw('N');old.append();old.nodes[0].values['ID']=99;node=old.nodes[0];header=old.data;p.run();self.assertIs(old.data,header);self.assertEqual(header.values['TAG'],7);self.assertIsNot(old.nodes[0],node);self.assertEqual(node.values['ID'],99)
    def test_header_output_alias_is_rejected(self):
        p,_=build(reply(output(1,logical('path')),output(2,integer(99))),params='a:route_t;b:INTEGER',body='n.tag=3 work(n,n.tag)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p._state.raw('N').data.values['TAG'],3)
    def test_node_alias_output_is_rejected(self):
        p,_=build(reply(output(1,logical('path')),output(2,integer(99))),params='a:route_t;b:INTEGER',body='work(n,n[1].id)');p._state.raw('N').append()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertIs(p._state.raw('N').nodes[0].values['ID'],rt.UNINITIALIZED)
    def test_readonly_header_rejects_all_outputs(self):
        p,_=build(reply(output(1,integer(42)),output(2,logical('path'))),params='s:INTEGER;n:route_t',body='s=7 work(s,n)');p._state.raw('N').data.read_only=True
        with self.assertRaisesRegex(rt.KarelRuntimeError,'read-only PATH header'):p.run()
        self.assertEqual(p.snapshot()['S'],7)
    def test_shared_node_storage_is_rejected(self):
        p,_=build(reply(output(1,logical('path'))));old=p._state.raw('N');old.append();old.nodes.append(old.nodes[0])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(old.nodes[0],old.nodes[1])


class QueueOwnershipTests(unittest.TestCase):
    def test_queue_output_detaches_buffer_without_writing_it(self):
        p,_=build(reply(output(1,logical('queue'))),'queue',decl='n:QUEUE_TYPE buffer:ARRAY[3]OF INTEGER s,seq:INTEGER',body='INIT_QUEUE(n) APPEND_QUEUE(99,n,buffer,seq,s) work(n)');p.run();self.assertIsNone(p._state.raw('N').buffer);self.assertEqual(p.snapshot()['BUFFER'][0],99)
    def test_case_snapshot_ignores_valid_buffer_link(self):
        p,_=build(cases([logical('queue')],reply(output(1,initial('queue')))),'queue');value=rt.QueueValue();value.initialized=True;value.sequence=7;value.entries=[(3,17),(1,9)];value.buffer=rt.Array(('ARRAY',3,rt.INTEGER));p._state.values['N']=value;p.run();self.assertEqual(encoded(value),initial('queue'));self.assertIsNone(value.buffer)
    def test_queue_and_its_buffer_can_be_independent_outputs(self):
        p,_=build(reply(output(1,logical('queue')),output(2,row(['ARRAY',3,['INTEGER']],[7,8,9]))),'queue',params='q:QUEUE_TYPE;b:ARRAY OF INTEGER',decl='n:QUEUE_TYPE buffer:ARRAY[3]OF INTEGER s,seq:INTEGER',body='INIT_QUEUE(n) APPEND_QUEUE(99,n,buffer,seq,s) work(n,buffer)');p.run();self.assertEqual(p.snapshot()['BUFFER'],[7,8,9]);self.assertIsNone(p._state.raw('N').buffer)


class LogicalValidationTests(unittest.TestCase):
    def reject(self,value):
        with self.assertRaises((ValueError,rt.KarelRuntimeError)):callbacks(value)
    def test_queue_order_and_counter_are_significant(self):
        a=logical('queue');b=deepcopy(a);b['value']['entries'].reverse();bank=callbacks({'cases':[dict(arguments=[a],result=integer(17)),dict(arguments=[b],result=integer(42))]});self.assertEqual(len(bank),1)
    def test_duplicate_normalized_path_case_rejects(self):
        a=logical('path');b=deepcopy(a);b['value']=dict(reversed(list(b['value'].items())));self.reject({'cases':[dict(arguments=[a],result=None),dict(arguments=[b],result=None)]})
    def test_invalid_duplicate_queue_ids(self):
        a=logical('queue');a['value']['entries'].append([3,99]);self.reject(a)
    def test_uninitialized_queue_with_entries(self):
        a=logical('queue');a['value']['initialized']=False;self.reject(a)
    def test_queue_integer_categories_remain_checked(self):
        a=logical('queue');a['value']['entries'][0][1]=True;self.reject(a)
    def test_missing_collection_container_rejects(self):self.reject(row(QUEUE,U))
    def test_path_lowercase_field_rejects(self):
        a=logical('path');a['value']['nodes'][0]={'id':17,'OCTET':B};self.reject(a)
    def test_headerless_path_data_rejects(self):self.reject(row(['PATH',None,None],dict(nodes=[],data={})))
    def test_file_array_result_stays_excluded(self):self.reject(row(['ARRAY',2,['FILE']],[{},{}]))
    def test_resource_record_fields_stay_excluded(self):self.reject(row(['STRUCTURE','R',[['Q',QUEUE]]],{'Q':logical('queue')['value']}))
    def test_resource_path_fields_stay_excluded(self):self.reject(row(['PATH',['STRUCTURE','N',[['Q',QUEUE]]],None],dict(nodes=[],data=None)))
    def test_oversized_path_preflight_precedes_decode(self):
        a=logical('path');a['value']['nodes']*=16384
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('decode')) as decode:self.reject(a)
        decode.assert_not_called()
    def test_oversized_queue_preflight_precedes_decode(self):
        a=logical('queue');a['value']['entries']*=8192
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('decode')) as decode:self.reject(a)
        decode.assert_not_called()
    def test_response_budget_combines_queue_entries_and_data(self):
        a=logical('queue');a['value']['entries']=[[n,n] for n in range(1,8193)];a['value']['sequence']=8192;b=row(['ARRAY',16384,['INTEGER']],[U]*16384)
        with rt._numeric_scope('pythonic'),patch('karel2py.storage.decode_typed',side_effect=AssertionError('decode')) as decode,self.assertRaises(rt.KarelRuntimeError):rt.external_reply_result(None,reply(output(1,a),output(2,b)),[reference(tuple_spec(QUEUE),rt.QueueValue()),reference(tuple_spec(b['type']),rt.Array(tuple_spec(b['type'])))])
        decode.assert_not_called()
    def test_global_configuration_budget_spans_data_and_collections(self):
        a=row(['ARRAY',32766,['INTEGER']],[U]*32766)
        with self.assertRaisesRegex(ValueError,'32767'):rt.external_value_callbacks({'HOST':{'A':a,'B':initial('queue'),'C':integer(1)}})
    def test_strict_collection_response_rejects(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.external_reply_result(None,reply(output(1,logical('path'))),[])


if __name__=='__main__':unittest.main()
