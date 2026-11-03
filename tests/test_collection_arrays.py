"""Authored collection cells, borrowed interfaces and bounded logical snapshots."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate,translate_project
from karel2py.lexer import TranslationError
from karel2py.storage import typed_value,decode_typed,collection_array_cost,collection_array_payload,restore_collection_array
from karel2py.variable_archives import roots
from tests.test_extended_services import compile_program

TYPES='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE header_t=STRUCTURE count:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t PATHHEADER=header_t'
NODE=('STRUCTURE','NODE_T',(('AMOUNT',('INTEGER',)),))
HEADER=('STRUCTURE','HEADER_T',(('COUNT',('INTEGER',)),))
PATH=('PATH',NODE,HEADER)
PARRAY=('ARRAY',2,PATH)
QARRAY=('ARRAY',2,('QUEUE_TYPE',))
DECL='paths:ARRAY[2]OF route_t queues:ARRAY[2]OF QUEUE_TYPE buf_a,buf_b:ARRAY[3]OF INTEGER status,seq,n,m,entry,visits:INTEGER'
SEED='APPEND_NODE(paths[1],status) paths[1].count=1 paths[1][1].amount=7 INIT_QUEUE(queues[1]) INIT_QUEUE(queues[2]) APPEND_QUEUE(7,queues[1],buf_a,seq,status) APPEND_QUEUE(9,queues[2],buf_b,seq,status) '


def build(body='',**options):return compile_program(body,prefix=options.pop('prefix',TYPES),decl=options.pop('decl',DECL),**options)

def execute(body='',**options):
    p,r=build(body,**options);v=p.run();return v,p,r

def raw(p,name):return p._state.values[name]

def queue_array():
    with rt._numeric_scope('pythonic'):return rt.Array(QARRAY)


class CollectionArrayStorageTests(unittest.TestCase):
    def test_independent_path_roots_and_headers(self):
        _,p,_=execute();a=raw(p,'PATHS');self.assertIsNot(a.values[0],a.values[1]);self.assertIsNot(a.values[0].data,a.values[1].data)
    def test_independent_queue_descriptors(self):
        _,p,_=execute();a=raw(p,'QUEUES');self.assertIsNot(a.values[0],a.values[1]);self.assertTrue(all(not q.initialized and q.buffer is None for q in a.values))
    def test_separate_program_instances_have_independent_collections(self):
        _,p,_=execute();q=type(p)();self.assertIsNot(raw(p,'PATHS').values[0],raw(q,'PATHS').values[0])
    def test_path_header_and_node_edits_select_one_cell(self):
        v,_,_=execute(SEED);self.assertEqual(v['PATHS'][0],dict(nodes=[{'AMOUNT':7}],data={'COUNT':1}));self.assertEqual(v['PATHS'][1]['nodes'],[])
    def test_two_queues_keep_separate_buffers_and_sequences(self):
        v,p,_=execute(SEED);self.assertEqual([q.entries for q in raw(p,'QUEUES').values],[[(1,7)],[(1,9)]])
        self.assertIs(raw(p,'QUEUES').values[0].buffer,raw(p,'BUF_A'));self.assertIs(raw(p,'QUEUES').values[1].buffer,raw(p,'BUF_B'))
    def test_queue_operation_reads_selected_cell(self):
        v,_,_=execute(SEED+'GET_QUEUE(queues[2],buf_b,n,seq,status)');self.assertEqual((v['N'],v['SEQ'],v['STATUS']),(9,1,0));self.assertEqual(v['QUEUES'][0]['entries'],[[1,7]])
    def test_default_path_array_nodes(self):
        v,_,_=execute('APPEND_NODE(paths[2],status) paths[2][1].node_pos.location.x=17',decl='paths:ARRAY[2]OF PATH status:INTEGER');self.assertEqual(v['PATHS'][1]['nodes'][0]['NODE_POS']['LOCATION']['X'],17.)
    def test_multidimensional_array_coordinates_precede_node(self):
        v,_,_=execute('APPEND_NODE(paths[2,1],status) paths[2][1][1].amount=17 n=paths[2,1,1].amount',decl=DECL.replace('paths:ARRAY[2]','paths:ARRAY[2,2]'));self.assertEqual(v['N'],17);self.assertEqual(v['PATHS'][0][0]['nodes'],[])
    def test_rank_three_array_has_separate_node_coordinate(self):
        v,_,_=execute('APPEND_NODE(paths[1,2,1],status) paths[1][2][1][1].amount=17 n=paths[1,2,1,1].amount',decl=DECL.replace('paths:ARRAY[2]','paths:ARRAY[1,2,1]'));self.assertEqual(v['N'],17)
    def test_named_nested_array_components(self):
        prefix=TYPES+' TYPE row_t=ARRAY[2]OF route_t'
        v,_,_=execute('APPEND_NODE(paths[1,2],status) paths[1][2][1].amount=19 n=paths[1,2,1].amount',prefix=prefix,decl=DECL.replace('paths:ARRAY[2]OF route_t','paths:ARRAY[2]OF row_t'));self.assertEqual(v['N'],19)
    def test_local_collection_array_is_fresh_per_call(self):
        routines='ROUTINE work VAR p:ARRAY[2]OF PATH BEGIN n=PATH_LEN(p[1]) APPEND_NODE(p[1],status) END work'
        v,_,_=execute('work work',routines=routines);self.assertEqual(v['N'],0)
    def test_supplied_wildcard_global_shape(self):
        r=translate('PROGRAM T VAR queues:ARRAY[*]OF QUEUE_TYPE n:INTEGER BEGIN INIT_QUEUE(queues[2]) n=ARRAY_LEN(queues) END T',array_shapes={'queues':[2]})
        namespace={};exec(r.python_source,namespace);self.assertEqual(namespace['Program']().run()['N'],2)
    def test_path_cell_copy_remains_independent(self):
        v,_,_=execute(SEED+'paths[2]=paths[1] paths[1][1].amount=99');self.assertEqual(v['PATHS'][1]['nodes'][0]['AMOUNT'],7)
    def test_queue_cell_copy_remains_unavailable(self):
        p,_=build(SEED+'queues[2]=queues[1]')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_missing_node_is_not_allocated_by_selector(self):
        p,_=build('paths[1][1].amount=7')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['PATHS'][0]['nodes'],[])
    def test_array_and_node_selectors_run_once_in_order(self):
        routines='ROUTINE cell:INTEGER BEGIN visits=visits*10+1 RETURN 1 END cell ROUTINE node_index:INTEGER BEGIN visits=visits*10+2 RETURN 1 END node_index'
        v,_,_=execute('visits=0 APPEND_NODE(paths[1],status) paths[cell()][node_index()].amount=7',routines=routines);self.assertEqual(v['VISITS'],12)
    def test_node_read_and_reference_share_schema(self):
        v,_,_=execute(SEED+'READ(paths[1][1]) n=paths[1][1].amount',read=lambda _:[17]);self.assertEqual(v['N'],17)
    def test_path_array_cell_whole_read_uses_existing_path_transport(self):
        v,_,_=execute(SEED+'READ(paths[1])',read=lambda _:[2,17]);self.assertEqual(v['PATHS'][0],dict(nodes=[{'AMOUNT':17}],data={'COUNT':2}))
    def test_position_input_inside_default_path_cell(self):
        values=[1.,0.,0.,0.,1.,0.,0.,0.,1.,10.,20.,30.,0,0,0,False,False,False,False]
        v,_,_=execute('APPEND_NODE(paths[1],status) READ(paths[1])',decl='paths:ARRAY[2]OF PATH status:INTEGER',read=lambda _:values);self.assertEqual(v['PATHS'][0]['nodes'][0]['NODE_POS']['LOCATION']['X'],10.)
    def test_using_selected_node_resolves_fields(self):
        v,_,_=execute(SEED+'USING paths[1][1] DO amount=17 ENDUSING');self.assertEqual(v['PATHS'][0]['nodes'][0]['AMOUNT'],17)


class CollectionArrayReferenceTests(unittest.TestCase):
    def test_generic_borrowed_path_array(self):
        routines='ROUTINE work(p:ARRAY OF route_t) BEGIN APPEND_NODE(p[2],status) p[2][1].amount=17 END work'
        v,_,_=execute('work(paths)',routines=routines);self.assertEqual(v['PATHS'][1]['nodes'][0]['AMOUNT'],17)
    def test_generic_borrowed_queue_array(self):
        routines='ROUTINE work(q:ARRAY OF QUEUE_TYPE) BEGIN INIT_QUEUE(q[2]) APPEND_QUEUE(17,q[2],buf_b,seq,status) END work'
        v,_,_=execute('work(queues)',routines=routines);self.assertEqual(v['QUEUES'][1]['entries'],[[1,17]])
    def test_selected_collection_cell_is_borrowed(self):
        routines='ROUTINE work(p:route_t) BEGIN APPEND_NODE(p,status) p[1].amount=17 END work'
        v,_,_=execute('work(paths[2])',routines=routines);self.assertEqual(v['PATHS'][1]['nodes'][0]['AMOUNT'],17)
    def test_selected_node_record_is_borrowed(self):
        routines='ROUTINE work(item:node_t) BEGIN item.amount=17 END work'
        v,_,_=execute(SEED+'work(paths[1][1])',routines=routines);self.assertEqual(v['PATHS'][0]['nodes'][0]['AMOUNT'],17)
    def test_byname_root_array_is_borrowed(self):
        routines='ROUTINE work(q:ARRAY OF QUEUE_TYPE) BEGIN INIT_QUEUE(q[2]) END work'
        v,_,_=execute("work(BYNAME('','QUEUES',entry))",routines=routines);self.assertTrue(v['QUEUES'][1]['initialized'])
    def test_byname_selected_cell(self):
        routines='ROUTINE work(q:QUEUE_TYPE) BEGIN INIT_QUEUE(q) END work'
        v,_,_=execute("work(BYNAME('','QUEUES[2]',entry))",routines=routines);self.assertTrue(v['QUEUES'][1]['initialized'])
    def test_byname_path_node_field(self):
        routines='ROUTINE work(value:INTEGER) BEGIN value=17 END work'
        v,_,_=execute(SEED+"work(BYNAME('','PATHS[1][1].AMOUNT',entry))",routines=routines);self.assertEqual(v['PATHS'][0]['nodes'][0]['AMOUNT'],17)
    def test_get_var_selected_path_field(self):
        v,_,_=execute(SEED+"GET_VAR(entry,'','PATHS[1][1].AMOUNT',n,status)");self.assertEqual((v['N'],v['STATUS']),(7,0))
    def test_set_var_selected_path_field(self):
        v,_,_=execute(SEED+"SET_VAR(entry,'','PATHS[1][1].AMOUNT',17,status)");self.assertEqual(v['PATHS'][0]['nodes'][0]['AMOUNT'],17)
    def test_pause_retains_borrowed_array_and_call_count(self):
        routines='ROUTINE work(q:ARRAY OF QUEUE_TYPE) BEGIN visits=visits+1 INIT_QUEUE(q[1]) PAUSE INIT_QUEUE(q[2]) END work'
        p,_=build('visits=0 work(queues)',routines=routines,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        v=p.resume();self.assertEqual(v['VISITS'],1);self.assertTrue(all(q['initialized'] for q in v['QUEUES']))
    def test_linked_source_array_parameter(self):
        main='PROGRAM MAIN VAR q:ARRAY[2]OF QUEUE_TYPE ROUTINE work(q:ARRAY OF QUEUE_TYPE) FROM LIB BEGIN work(q) END MAIN'
        lib='PROGRAM LIB ROUTINE work(q:ARRAY OF QUEUE_TYPE) BEGIN INIT_QUEUE(q[2]) END work BEGIN END LIB'
        instance=translate_project({'main':main,'lib':lib}).instantiate();self.assertTrue(instance.run('MAIN')['MAIN']['values']['Q'][1]['initialized'])
    def test_linked_imported_array_retains_live_root(self):
        main='PROGRAM MAIN VAR q FROM LIB:ARRAY[2]OF QUEUE_TYPE BEGIN INIT_QUEUE(q[2]) END MAIN'
        lib='PROGRAM LIB VAR q:ARRAY[2]OF QUEUE_TYPE BEGIN END LIB'
        instance=translate_project({'main':main,'lib':lib}).instantiate();self.assertTrue(instance.run('MAIN')['LIB']['values']['Q'][1]['initialized'])
    def test_byname_entry_cannot_overlap_selected_path_array(self):
        routines='ROUTINE work(p:ARRAY OF route_t) BEGIN END work'
        p,_=build(SEED+"work(BYNAME('','PATHS',paths[1].count))",routines=routines)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['PATHS'][0]['data']['COUNT'],1)

    def test_later_selector_effect_is_retained_on_bad_array_coordinate(self):
        routines='ROUTINE node_index:INTEGER BEGIN visits=visits+1 RETURN 1 END node_index'
        p,_=build('visits=0 paths[0][node_index()].amount=7',routines=routines)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],1)

    def test_named_complete_subarray_boundary_is_borrowed(self):
        prefix=TYPES+' TYPE row_t=ARRAY[2]OF QUEUE_TYPE'
        routines='ROUTINE work(q:row_t) BEGIN INIT_QUEUE(q[2]) END work'
        v,_,_=execute('work(rows[2])',prefix=prefix,decl=DECL+' rows:ARRAY[2]OF row_t',routines=routines);self.assertTrue(v['ROWS'][1][1]['initialized'])


class CollectionArrayCodecTests(unittest.TestCase):
    def test_queue_payload_retains_sequence_counter(self):
        _,p,_=execute(SEED);data=typed_value(raw(p,'QUEUES'));self.assertEqual(data['value'][0],dict(initialized=True,sequence=1,entries=[[1,7]]))
    def test_queue_restore_drops_buffer_links(self):
        _,p,_=execute(SEED);spec,value=decode_typed(typed_value(raw(p,'QUEUES')));self.assertEqual(spec,QARRAY);self.assertTrue(all(q.buffer is None for q in value.values))
    def test_path_payload_retains_header_nodes_and_partial_siblings(self):
        _,p,_=execute(SEED);data=typed_value(raw(p,'PATHS'));self.assertEqual(data['value'][0],dict(nodes=[{'AMOUNT':7}],data={'COUNT':1}));self.assertEqual(data['value'][1]['data'],{'COUNT':{'uninitialized':True}})
    def test_context_json_roundtrip_includes_both_arrays(self):
        _,p,_=execute(SEED);saved=json.loads(json.dumps(p._state.execution.to_config(),allow_nan=False));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_fresh_restore_rebuilds_independent_cells(self):
        _,p,_=execute(SEED);_,restored=decode_typed(typed_value(raw(p,'PATHS')));self.assertIsNot(restored.values[0],raw(p,'PATHS').values[0]);self.assertIsNot(restored.values[0].data,restored.values[1].data)
    def test_named_multidimensional_payload_shape(self):
        with rt._numeric_scope('pythonic'):a=rt.Array(('ARRAY',(2,2),('QUEUE_TYPE',),'BATCH_T'))
        data=typed_value(a);self.assertEqual([len(row) for row in data['value']],[2,2]);self.assertEqual(decode_typed(data)[0],a.spec)
    def test_nested_named_components_roundtrip(self):
        with rt._numeric_scope('pythonic'):a=rt.Array(('ARRAY',2,('ARRAY',2,('QUEUE_TYPE',),'ROW_T')))
        data=typed_value(a);_,b=decode_typed(data);self.assertEqual(typed_value(b),data)
    def test_malformed_array_shape_rejects(self):
        a=queue_array();a.values.pop()
        with self.assertRaises(ValueError):typed_value(a)
    def test_missing_collection_cell_rejects(self):
        a=queue_array();a.values[0]=rt.UNINITIALIZED
        with self.assertRaises(ValueError):typed_value(a)
    def test_wrong_collection_cell_type_rejects(self):
        a=queue_array();a.values[0]=rt.PathValue(('PATH',None,None))
        with self.assertRaises(ValueError):typed_value(a)
    def test_initialized_flag_is_exact_boolean(self):
        data=typed_value(queue_array());data['value'][0]['initialized']=1
        with self.assertRaises(ValueError):decode_typed(data)
    def test_duplicate_queue_sequences_reject(self):
        data=typed_value(queue_array());data['value'][0]=dict(initialized=True,sequence=1,entries=[[1,7],[1,9]])
        with self.assertRaises(ValueError):decode_typed(data)
    def test_unknown_payload_keys_reject(self):
        data=typed_value(queue_array());data['value'][0]['buffer']=[]
        with self.assertRaises(ValueError):decode_typed(data)
    def test_entire_array_missing_marker_is_not_a_collection_allocation(self):
        with self.assertRaises(ValueError):decode_typed({'type':['ARRAY',2,['QUEUE_TYPE']],'value':{'uninitialized':True}})
    def test_old_flat_multidimensional_payload_is_not_invented(self):
        cell=dict(initialized=False,sequence=0,entries=[])
        with self.assertRaises(ValueError):decode_typed({'type':['ARRAY',[2,2],['QUEUE_TYPE']],'value':[cell]*4})
    def test_queue_payload_budget_precedes_array_allocation(self):
        cell=dict(initialized=True,sequence=9000,entries=[[i,i]for i in range(1,9001)])
        with patch.object(rt,'Array') as factory,self.assertRaisesRegex(ValueError,'32767'):
            decode_typed({'type':['ARRAY',2,['QUEUE_TYPE']],'value':[cell,cell]})
        factory.assert_not_called()
    def test_path_payload_budget_precedes_node_allocation(self):
        cell={'nodes':[{}]*900,'data':None}
        with patch.object(rt,'PathValue') as factory,self.assertRaisesRegex(ValueError,'32767'):
            decode_typed({'type':['ARRAY',2,['PATH',None,None]],'value':[cell,cell]})
        factory.assert_not_called()
    def test_encoding_budget_precedes_collection_payload_expansion(self):
        a=queue_array();a.values[0].initialized=True;a.values[0].entries=[(1,7)]*17000
        with self.assertRaisesRegex(ValueError,'32767'):typed_value(a)
    def test_data_array_cannot_use_collection_codec(self):
        with self.assertRaises(ValueError):restore_collection_array(('ARRAY',2,('INTEGER',)),[1,2])
    def test_context_restore_then_existing_queue_operations(self):
        _,p,_=execute(SEED);saved=p._state.execution.to_config();ctx=rt.ExecutionContext.from_config(saved)
        q,_=build('GET_QUEUE(queues[1],buf_a,n,seq,status)',context=ctx);self.assertEqual(q.run()['N'],7)


class CollectionArrayGuardTests(unittest.TestCase):
    def reject(self,body,**options):
        with self.assertRaises(TranslationError):build(body,**options)
    def test_whole_path_array_assignment_rejects(self):self.reject('paths=other',decl=DECL+' other:ARRAY[2]OF route_t')
    def test_whole_queue_array_assignment_rejects(self):self.reject('queues=other',decl=DECL+' other:ARRAY[2]OF QUEUE_TYPE')
    def test_grouped_array_argument_rejects(self):self.reject('work((queues))',routines='ROUTINE work(q:ARRAY OF QUEUE_TYPE) BEGIN END work')
    def test_returned_resource_arrays_reject(self):self.reject('',routines='ROUTINE work:ARRAY[2]OF QUEUE_TYPE BEGIN RETURN queues END work')
    def test_named_resource_array_results_reject(self):self.reject('',prefix=TYPES+' TYPE batch_t=ARRAY[2]OF QUEUE_TYPE',routines='ROUTINE work:batch_t BEGIN RETURN queues END work')
    def test_record_resource_array_fields_reject(self):self.reject('',prefix='TYPE data_t=STRUCTURE q:ARRAY[2]OF QUEUE_TYPE ENDSTRUCTURE',decl='d:data_t')
    def test_whole_resource_array_input_rejects(self):self.reject('READ(paths)')
    def test_whole_resource_array_output_rejects(self):self.reject('WRITE(queues)')
    def test_whole_resource_array_uninit_rejects(self):self.reject('n=UNINIT(queues)')
    def test_incomplete_flat_resource_prefix_rejects(self):self.reject('work(q[1])',decl='q:ARRAY[2,2]OF QUEUE_TYPE',routines='ROUTINE work(v:ARRAY OF QUEUE_TYPE) BEGIN END work')
    def test_path_array_counter_root_remains_resource(self):self.reject('FOR paths[1][1].amount=1 TO 3 DO n=1 ENDFOR')
    def test_direct_clone_does_not_share_resource_cells(self):
        with self.assertRaises(rt.KarelRuntimeError):queue_array().clone()
    def test_checked_whole_array_copy_rejects(self):
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.checked(QARRAY,queue_array())
    def test_value_argument_does_not_make_implicit_resource_copy(self):
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.value_argument(QARRAY,queue_array())
    def test_unknown_path_node_does_not_override_rank_errors(self):self.reject('n=paths[1,1,1].amount')
    def test_extra_queue_subscript_rejects(self):self.reject('n=queues[1,1]')
    def test_oversized_header_allocation_rejects_at_translation(self):self.reject('',decl=DECL.replace('paths:ARRAY[2]','paths:ARRAY[20000]'))
    def test_runtime_header_allocation_is_bounded_before_factory(self):
        with rt._numeric_scope('pythonic'),patch.object(rt,'PathValue') as factory,self.assertRaises(rt.KarelRuntimeError):rt.Array(('ARRAY',20000,PATH))
        factory.assert_not_called()
    def test_creation_cost_counts_headers_and_descriptors(self):self.assertEqual(collection_array_cost(PARRAY),4);self.assertEqual(collection_array_cost(QARRAY),2)
    def test_noncollection_array_cost_is_not_claimed(self):self.assertIsNone(collection_array_cost(('ARRAY',2,('INTEGER',))))
    def test_wildcard_runtime_allocation_is_rejected(self):
        with self.assertRaises(ValueError):collection_array_cost(('ARRAY',None,('QUEUE_TYPE',)))
    def test_rank_four_resource_arrays_reject(self):
        with self.assertRaises(ValueError):collection_array_cost(('ARRAY',(1,1,1,1),('QUEUE_TYPE',)))
    def test_invalid_path_component_schema_rejects_before_allocation(self):
        with self.assertRaises((ValueError,rt.KarelRuntimeError)):collection_array_cost(('ARRAY',2,('PATH',('FILE',),None)))
    def test_resource_arrays_require_pythonic_runtime(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.Array(QARRAY)
    def test_archives_exclude_resource_arrays_and_retain_data_roots(self):
        _,p,_=execute(SEED);owned,excluded=roots(p._state.execution,p._state,'T');self.assertIn('PATHS',excluded);self.assertIn('QUEUES',excluded);self.assertIn('STATUS',owned)
    def test_report_marks_authored_offline_extension(self):
        _,_,r=execute();policy=r.report['collection_array_policy'];self.assertFalse(policy['controller_validated']);self.assertIn('32767',policy['limits']);self.assertEqual(policy['guide'],'docs/collection-arrays.md')


if __name__=='__main__':unittest.main()
