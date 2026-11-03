"""Authored owned collection ARRAY archives, publication and allocation contracts."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate,translate_project
from karel2py import variable_archives as vr
from karel2py.storage import typed_value,restore_collection_array
from tests.test_extended_services import compile_program
from tests.test_path_archives import SPEC as PATH,path,PREFIX

Q=('ARRAY',2,('QUEUE_TYPE',));P=('ARRAY',2,PATH)
SAVE="SAVE('CACHE','CACHE.VR',s)";LOAD="LOAD('CACHE.VR',0,s)";CLEAR="CLEAR('CACHE.VR',s)"


def leaves(array):
    for item in array.values:
        if type(item) is rt.Array:yield from leaves(item)
        else:yield item


def array(spec=P):
    with rt._numeric_scope('pythonic'):
        result=rt.Array(spec)
        for i,item in enumerate(leaves(result),1):
            if type(item) is rt.PathValue:
                value=path(item.spec,(i,));item.data=value.data;item.nodes=value.nodes
            else:item.initialized=True;item.sequence=i;item.entries=[(i,i*7)]
        return result


def bind(ctx,value,program='CACHE',name='ITEM'):
    ref=rt.Reference(value.spec,{'value':value},'value');ctx.variables.bind(program,name,ref);return ref


def context(spec=P,**options):
    ctx=rt.ExecutionContext(files=rt.MemoryFiles(),variable_archives=rt.VariableArchives(**options));bind(ctx,array(spec));return ctx


def raw(ctx,program='CACHE',name='ITEM'):return ctx.variables.bindings[program,name].raw()
def call(ctx,body):
    p,_=compile_program(body,decl='s:INTEGER',context=ctx);return p.run()['S']
def saved(ctx):return json.loads(bytes(ctx.files.files['CACHE.VR']))
def install(ctx,row):ctx.files.files['CACHE.VR']=bytearray(ctx.variable_archives.encode(row))
def snap(value):return rt.snapshot_value(value)
def payload(value):return typed_value(value)


class CollectionArchiveValueTests(unittest.TestCase):
    def test_save_includes_path_cells_and_exact_schema(self):
        ctx=context();self.assertEqual(call(ctx,SAVE),0);self.assertEqual(saved(ctx)['variables']['ITEM'],payload(raw(ctx)));self.assertEqual(saved(ctx)['excluded'],[])
    def test_save_includes_queue_sequence_and_entries(self):
        ctx=context(Q);self.assertEqual(call(ctx,SAVE),0);self.assertEqual(saved(ctx)['variables']['ITEM']['value'][1],dict(initialized=True,sequence=2,entries=[[2,14]]))
    def test_clear_load_roundtrip_paths(self):
        ctx=context();before=snap(raw(ctx));self.assertEqual(call(ctx,SAVE+' '+CLEAR+' '+LOAD),0);self.assertEqual(snap(raw(ctx)),before)
    def test_clear_load_roundtrip_queues(self):
        ctx=context(Q);before=snap(raw(ctx));self.assertEqual(call(ctx,SAVE+' '+CLEAR+' '+LOAD),0);self.assertEqual(snap(raw(ctx)),before)
    def test_clear_resets_all_path_nodes_and_headers(self):
        ctx=context();self.assertEqual(call(ctx,CLEAR),0);self.assertTrue(all(not item.nodes and item.data.values['COUNT'] is rt.UNINITIALIZED for item in raw(ctx).values))
    def test_clear_resets_all_queue_states(self):
        ctx=context(Q);self.assertEqual(call(ctx,CLEAR),0);self.assertTrue(all(not item.initialized and not item.entries and item.sequence==0 and item.buffer is None for item in raw(ctx).values))
    def test_partial_path_node_and_header_data_roundtrip(self):
        ctx=context();root=raw(ctx);root.values[0].nodes[0]=rt.UNINITIALIZED;root.values[1].data.values['COUNT']=rt.UNINITIALIZED;before=snap(root);self.assertEqual(call(ctx,SAVE+' '+CLEAR+' '+LOAD),0);self.assertEqual(snap(root),before)
    def test_default_path_cells_and_empty_arrays_roundtrip(self):
        ctx=context()
        with rt._numeric_scope('pythonic'):value=rt.Array(('ARRAY',2,('PATH',None,None)))
        bind(ctx,value);before=snap(value);self.assertEqual(call(ctx,SAVE+' '+CLEAR+' '+LOAD),0);self.assertEqual(snap(value),before)
    def test_multidimensional_rows_keep_coordinate_order(self):
        ctx=context(('ARRAY',(2,2),PATH));self.assertEqual(call(ctx,SAVE),0);self.assertEqual([row[0]['nodes'][0]['VALUE'] for row in saved(ctx)['variables']['ITEM']['value']],[1,3])
    def test_named_nested_arrays_keep_nominal_components(self):
        spec=('ARRAY',2,('ARRAY',2,PATH,'ROW_T'),'BANK_T');ctx=context(spec);before=payload(raw(ctx));self.assertEqual(call(ctx,SAVE+' '+CLEAR+' '+LOAD),0);self.assertEqual(payload(raw(ctx)),before)
    def test_new_namespace_owns_independent_path_cells(self):
        ctx=context();call(ctx,SAVE);fresh=rt.ExecutionContext(files=rt.MemoryFiles(ctx.files.snapshot()),variable_archives=rt.VariableArchives());self.assertEqual(call(fresh,LOAD),0);self.assertEqual(snap(raw(fresh)),snap(raw(ctx)));self.assertIsNot(raw(fresh).values[0],raw(fresh).values[1]);self.assertIsNot(raw(fresh).values[0],raw(ctx).values[0])
    def test_new_namespace_queue_buffers_are_unbound(self):
        ctx=context(Q);raw(ctx).values[0].buffer=rt.Array(('ARRAY',3,('INTEGER',)));call(ctx,SAVE);fresh=rt.ExecutionContext(files=rt.MemoryFiles(ctx.files.snapshot()),variable_archives=rt.VariableArchives());self.assertEqual(call(fresh,LOAD),0);self.assertTrue(all(item.buffer is None for item in raw(fresh).values))
    def test_older_excluded_array_rows_keep_existing_contents(self):
        ctx=context();before=snap(raw(ctx));install(ctx,dict(format=vr.FORMAT,program='CACHE',variables={},excluded=['ITEM'],calls=[]));self.assertEqual(call(ctx,LOAD),0);self.assertEqual(snap(raw(ctx)),before)
    def test_file_arrays_stay_excluded(self):
        ctx=context()
        with rt._numeric_scope('pythonic'):value=rt.Array(('ARRAY',2,('FILE',)))
        bind(ctx,value,name='STREAMS');self.assertEqual(call(ctx,SAVE),0);self.assertEqual(saved(ctx)['excluded'],['STREAMS']);self.assertNotIn('STREAMS',saved(ctx)['variables'])


class CollectionArchiveIdentityTests(unittest.TestCase):
    def test_load_retains_array_container_and_original_cells(self):
        ctx=context();root=raw(ctx);storage=root.values;cells=list(storage);call(ctx,SAVE+' '+LOAD);self.assertIs(raw(ctx),root);self.assertIs(root.values,storage);self.assertTrue(all(a is b for a,b in zip(cells,root.values)))
    def test_clear_retains_array_cells_and_headers(self):
        ctx=context();cells=list(raw(ctx).values);headers=[item.data for item in cells];call(ctx,CLEAR);self.assertTrue(all(a is b for a,b in zip(cells,raw(ctx).values)));self.assertTrue(all(item.data is header for item,header in zip(cells,headers)))
    def test_load_retains_header_aliases_and_detaches_old_nodes(self):
        ctx=context();root=raw(ctx);header=rt.field_reference(root.values[0].data,'COUNT');nodes=root.values[0].nodes;field=rt.field_reference(nodes[0],'VALUE');call(ctx,SAVE);header.set(99);field.set(88);call(ctx,LOAD);self.assertEqual(header.raw(),1);self.assertEqual(field.raw(),88);self.assertIsNot(root.values[0].nodes,nodes)
    def test_nested_array_containers_keep_identity(self):
        ctx=context(('ARRAY',2,('ARRAY',2,PATH,'ROW_T')));inner=raw(ctx).values[0];cell=inner.values[0];call(ctx,SAVE+' '+CLEAR+' '+LOAD);self.assertIs(raw(ctx).values[0],inner);self.assertIs(inner.values[0],cell)
    def test_queue_identity_retained_but_buffer_link_removed(self):
        ctx=context(Q);queue=raw(ctx).values[0];buffer=rt.Array(('ARRAY',3,('INTEGER',)));buffer.values[:]=[7,0,0];queue.buffer=buffer;call(ctx,SAVE+' '+LOAD);self.assertIs(raw(ctx).values[0],queue);self.assertIsNone(queue.buffer);self.assertEqual(buffer.values,[7,0,0])
    def test_existing_live_byname_row_observes_load(self):
        ctx=context(('ARRAY',(2,2),PATH));root=raw(ctx)
        with rt._numeric_scope('pythonic'):view=rt.resource_array_prefix_reference(root,2,root.spec).raw()
        call(ctx,SAVE);root.values[2].nodes[0].values['VALUE']=99;call(ctx,LOAD)
        with rt._numeric_scope('pythonic'):self.assertIs(view.values[0],root.values[2]);self.assertEqual(view.values[0].nodes[0].values['VALUE'],3)
    def test_disjoint_root_is_not_removed_by_load(self):
        ctx=context();call(ctx,SAVE);ctx.variables.define('CACHE','EXTRA',('INTEGER',),99);call(ctx,LOAD);self.assertEqual(ctx.variables.bindings['CACHE','EXTRA'].raw(),99)
    def test_restored_arrays_allocate_no_throwaway_collection_objects(self):
        spec=('ARRAY',2,('ARRAY',2,PATH,'ROW_T'));data=payload(array(spec))['value'];original=rt.PathValue.__init__;created=[]
        def build(value,schema):created.append(schema);original(value,schema)
        with rt._numeric_scope('pythonic'),patch.object(rt.PathValue,'__init__',build):restored=restore_collection_array(spec,data)
        self.assertEqual(len(created),4);self.assertEqual(len(list(leaves(restored))),4)


class CollectionArchiveGuardTests(unittest.TestCase):
    def assert_rejected_save(self,mutate,code=6):
        ctx=context();mutate(raw(ctx));self.assertEqual(call(ctx,SAVE),code);self.assertNotIn('CACHE.VR',ctx.files.files)
    def test_malformed_unselected_cell_rejects_save(self):self.assert_rejected_save(lambda a:a.values[1].nodes[0].values.update(VALUE=True))
    def test_invalid_header_rejects_save(self):self.assert_rejected_save(lambda a:a.values[1].data.values.update(COUNT='bad'))
    def test_missing_collection_cell_rejects_save(self):self.assert_rejected_save(lambda a:a.values.__setitem__(1,rt.UNINITIALIZED))
    def test_wrong_container_size_rejects_save(self):self.assert_rejected_save(lambda a:a.values.pop())
    def test_wrong_container_schema_rejects_save(self):self.assert_rejected_save(lambda a:setattr(a,'spec',('ARRAY',3,PATH)))
    def test_duplicate_owned_path_cell_is_rejected(self):self.assert_rejected_save(lambda a:a.values.__setitem__(1,a.values[0]),4)
    def test_shared_headers_between_cells_are_rejected(self):self.assert_rejected_save(lambda a:setattr(a.values[1],'data',a.values[0].data),4)
    def test_shared_node_lists_between_cells_are_rejected(self):self.assert_rejected_save(lambda a:setattr(a.values[1],'nodes',a.values[0].nodes),4)
    def test_shared_nested_array_container_is_rejected(self):
        ctx=context(('ARRAY',2,('ARRAY',2,PATH,'ROW_T')));raw(ctx).values[1]=raw(ctx).values[0];self.assertEqual(call(ctx,SAVE),4)
    def test_duplicate_owned_queue_cell_is_rejected(self):
        ctx=context(Q);raw(ctx).values[1]=raw(ctx).values[0];self.assertEqual(call(ctx,SAVE),4)
    def test_queue_payload_domains_are_checked(self):
        ctx=context(Q);raw(ctx).values[1].sequence=True;self.assertEqual(call(ctx,SAVE),6)
    def test_load_rejects_existing_malformed_array_before_any_updates(self):
        ctx=context();call(ctx,SAVE);root=raw(ctx);root.values[0].data.values['COUNT']=88;root.values.pop();self.assertEqual(call(ctx,LOAD),6);self.assertEqual(root.values[0].data.values['COUNT'],88)
    def test_status_inside_header_blocks_load(self):
        ctx=context();call(ctx,SAVE);p,_=compile_program("LOAD('CACHE.VR',0,slot)",decl='slot:INTEGER',context=ctx);p._state.values['SLOT']=rt.field_reference(raw(ctx).values[0].data,'COUNT');self.assertEqual(p.run()['SLOT'],4);self.assertEqual(raw(ctx).values[0].nodes[0].values['VALUE'],1)
    def test_overlapping_array_roots_reject_save(self):
        ctx=context();bind(ctx,raw(ctx),name='ALIAS');self.assertEqual(call(ctx,SAVE),4)
    def test_live_row_carrier_is_not_an_owned_archive_root(self):
        ctx=context(('ARRAY',(2,2),PATH));root=raw(ctx)
        with rt._numeric_scope('pythonic'):view=rt.resource_array_prefix_reference(root,2,root.spec).raw()
        bind(ctx,view);self.assertEqual(call(ctx,SAVE),6)


class CollectionArchivePayloadTests(unittest.TestCase):
    def bad(self,mutate):
        ctx=context();call(ctx,SAVE);row=saved(ctx);mutate(row['variables']['ITEM']);install(ctx,row);before=snap(raw(ctx));self.assertEqual(call(ctx,LOAD),6);self.assertEqual(snap(raw(ctx)),before)
    def test_payload_rank_mismatch_rejects(self):self.bad(lambda r:r.update(value=[r['value']]))
    def test_payload_missing_cell_rejects(self):self.bad(lambda r:r['value'].pop())
    def test_payload_extra_cell_rejects(self):self.bad(lambda r:r['value'].append(deepcopy(r['value'][0])))
    def test_payload_unknown_cell_fields_reject(self):self.bad(lambda r:r['value'][1].update(extra=1))
    def test_payload_invalid_node_scalar_rejects(self):self.bad(lambda r:r['value'][1]['nodes'][0].update(VALUE=True))
    def test_payload_noncanonical_marker_rejects(self):self.bad(lambda r:r['value'][1]['nodes'][0].update(VALUE={'uninitialized':1}))
    def test_payload_wrong_path_schema_rejects(self):self.bad(lambda r:r['type'].__setitem__(2,['QUEUE_TYPE']))
    def test_named_schema_identity_is_exact(self):
        ctx=context(('ARRAY',2,PATH,'A_T'));call(ctx,SAVE);row=saved(ctx);row['variables']['ITEM']['type'][3]='B_T';install(ctx,row);self.assertEqual(call(ctx,LOAD),6)
    def test_all_record_schemas_preflight_before_decode(self):
        ctx=context();call(ctx,SAVE);row=saved(ctx);row['variables']['ZZZ']={'type':['ARRAY',32768,['INTEGER']],'value':[]};install(ctx,row)
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('premature decode')):self.assertEqual(call(ctx,LOAD),6)
    def test_array_total_content_limit_preflights_before_decode(self):
        ctx=context();call(ctx,SAVE);row=saved(ctx);cell=row['variables']['ITEM']['value'][0];cell['nodes']=[{'VALUE':1}]*32766;install(ctx,row)
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('premature decode')):self.assertEqual(call(ctx,LOAD),6)
    def test_combined_root_content_limit_preflights_before_decode(self):
        ctx=context(Q);call(ctx,SAVE);row=saved(ctx);item=row['variables']['ITEM'];item['value'][0]['entries']=[[n,n] for n in range(1,9001)];item['value'][0]['sequence']=9000;row['variables']['SECOND']=deepcopy(item);install(ctx,row)
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('premature decode')):self.assertEqual(call(ctx,LOAD),6)
    def test_scalar_queue_contents_share_the_array_snapshot_budget(self):
        ctx=context(Q);call(ctx,SAVE);row=saved(ctx);entry={'type':['QUEUE_TYPE'],'value':dict(initialized=True,sequence=16382,entries=[[n,n] for n in range(1,16383)])};row['variables']['SCALAR']=entry;install(ctx,row)
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('premature decode')):self.assertEqual(call(ctx,LOAD),6)
    def test_new_namespace_preflight_failure_publishes_no_binding(self):
        ctx=context();call(ctx,SAVE);row=saved(ctx);row['variables']['ITEM']['value'][1]['nodes'][0]['VALUE']=True;fresh=rt.ExecutionContext(files=rt.MemoryFiles(),variable_archives=rt.VariableArchives());install(fresh,row);self.assertEqual(call(fresh,LOAD),6);self.assertNotIn(('CACHE','ITEM'),fresh.variables.bindings)


class CollectionArchiveServiceTests(unittest.TestCase):
    def test_dram_roundtrip_retains_cells(self):
        ctx=context();p,_=compile_program("SAVE_DRAM('CACHE',s)",decl='s:INTEGER',context=ctx);self.assertEqual(p.run()['S'],0);root=raw(ctx);cell=root.values[0];cell.nodes[0].values['VALUE']=99;self.assertEqual(ctx.variable_archives.restore_dram(p._state,'CACHE'),0);self.assertIs(root.values[0],cell);self.assertEqual(cell.nodes[0].values['VALUE'],1)
    def test_dram_json_snapshot_roundtrip(self):
        ctx=context(Q);call(ctx,"SAVE_DRAM('CACHE',s)");data=json.loads(json.dumps(ctx.variable_archives.to_config()));restored=rt.VariableArchives.from_config(data);self.assertEqual(restored.to_config(),data)
    def test_failed_dram_save_preserves_previous_snapshot(self):
        ctx=context();call(ctx,"SAVE_DRAM('CACHE',s)");before=deepcopy(ctx.variable_archives.flash);raw(ctx).values[1].nodes[0].values['VALUE']=True;self.assertEqual(call(ctx,"SAVE_DRAM('CACHE',s)"),6);self.assertEqual(ctx.variable_archives.flash,before)
    def test_recursive_backup_restore_and_clear(self):
        ctx=context(calls={'CACHE':['CHILD']});bind(ctx,array(Q),program='CHILD');before=snap(raw(ctx));self.assertEqual(call(ctx,"PROG_BACKUP('CACHE',PBR_VRTYPE,0,TRUE,s) PROG_CLEAR('CACHE',PBR_VRTYPE,s) PROG_RESTORE('CACHE.VR',s)"),0);self.assertEqual(snap(raw(ctx)),before);self.assertEqual(raw(ctx,'CHILD').values[1].entries,[(2,14)])
    def test_recursive_restore_failure_keeps_earlier_namespace(self):
        ctx=context(calls={'CACHE':['CHILD']});bind(ctx,array(Q),program='CHILD');call(ctx,"PROG_BACKUP('CACHE',PBR_VRTYPE,0,TRUE,s)");raw(ctx).values[0].nodes[0].values['VALUE']=99;row=json.loads(bytes(ctx.files.files['CHILD.VR']));row['variables']['ITEM']['value'][0]['sequence']=True;ctx.files.files['CHILD.VR']=bytearray(ctx.variable_archives.encode(row));self.assertEqual(call(ctx,"PROG_RESTORE('CACHE.VR',s)"),6);self.assertEqual(raw(ctx).values[0].nodes[0].values['VALUE'],99)
    def test_recursive_backup_invalid_child_writes_no_files(self):
        ctx=context(calls={'CACHE':['CHILD']});bind(ctx,array(Q),program='CHILD');raw(ctx,'CHILD').values[1].sequence=True;self.assertEqual(call(ctx,"PROG_BACKUP('CACHE',PBR_VRTYPE,0,TRUE,s)"),6);self.assertEqual(ctx.files.snapshot(),{})
    def test_mixed_tp_vr_batch_restores_arrays(self):
        from tests.test_mixed_archives import context as mixed,BACKUP,CLEAR as MCLEAR,RESTORE
        ctx=mixed();bind(ctx,array(),program='ROOT');before=snap(raw(ctx,'ROOT'));self.assertEqual(call(ctx,BACKUP+' '+MCLEAR+' '+RESTORE),0);self.assertEqual(snap(raw(ctx,'ROOT')),before);self.assertIn('ROOT',ctx.teach_programs.to_config()['programs'])
    def test_dynamic_creation_policy_roundtrip_into_fresh_namespace(self):
        from tests.test_dynamic_collection_arrays import allocation,invoke,FILL,execute
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(),variable_archives=rt.VariableArchives());values,ctx,_,_=execute(allocation()+invoke()+"SAVE('CACHE','CACHE.VR',status)",routines=FILL,context=ctx);self.assertEqual(values['STATUS'],0);fresh=rt.ExecutionContext(files=rt.MemoryFiles(ctx.files.snapshot()),variable_archives=rt.VariableArchives());self.assertEqual(call(fresh,LOAD),0);self.assertEqual(fresh.variables.metadata['CACHE','ITEM'],ctx.variables.metadata['CACHE','ITEM']);self.assertEqual(raw(fresh).values[1].entries,[(1,9)])
    def test_dynamic_policy_mismatch_is_atomic(self):
        ctx=context();ctx.variables.metadata['CACHE','ITEM']={'group':0,'memory_pool':0};call(ctx,SAVE);ctx.variables.metadata['CACHE','ITEM']={'group':0,'memory_pool':1};before=snap(raw(ctx));self.assertEqual(call(ctx,LOAD),6);self.assertEqual(snap(raw(ctx)),before)
    def test_linked_imports_remain_excluded_from_archive_ownership(self):
        sources={'main':'PROGRAM MAIN '+PREFIX+' VAR routes:ARRAY[2]OF route_t ROUTINE work FROM LIB BEGIN work END MAIN','lib':"PROGRAM LIB "+PREFIX+" VAR routes FROM MAIN:ARRAY[2]OF route_t s:INTEGER ROUTINE work BEGIN SAVE('MAIN','MAIN.VR',s) END work BEGIN END LIB"}
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(),variable_archives=rt.VariableArchives());project=translate_project(sources).instantiate(context=ctx);project.run('MAIN');row=json.loads(bytes(ctx.files.files['MAIN.VR']));self.assertIn('ROUTES',row['variables']);self.assertEqual(row['excluded'],[])


class CollectionArchiveLifetimeTests(unittest.TestCase):
    def test_connected_header_timer_blocks_clear_and_keeps_connection(self):
        ctx=context();p,_=compile_program("work(BYNAME('CACHE','ITEM',entry))",prefix=PREFIX,decl='entry,s:INTEGER',routines="ROUTINE work(items:ARRAY OF route_t) BEGIN CONNECT TIMER TO items[1].count CLEAR('CACHE.VR',s) PAUSE END work",context=ctx,cooperative=True,clock_us=lambda:0)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['S'],4);self.assertEqual(raw(ctx).values[0].nodes[0].values['VALUE'],1);self.assertTrue(ctx._timer_claims);p.stop();self.assertEqual(ctx._timer_claims,{})
    def test_paused_foreign_collection_alias_blocks_load(self):
        ctx=context();call(ctx,SAVE);namespace={'__name__':'paused_array_owner'};exec(translate('PROGRAM OTHER '+PREFIX+' VAR routes:ARRAY[2]OF route_t BEGIN PAUSE END OTHER',cooperative=True).python_source,namespace);p=namespace['Program'](context=ctx);p._state.values['ROUTES']=raw(ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(call(ctx,LOAD),4);p.stop()
    def test_old_cell_reference_observes_restored_original_path(self):
        ctx=context();root=raw(ctx);ref=rt.Reference(PATH,root.values,0);cell=ref.raw();call(ctx,SAVE);cell.nodes[0].values['VALUE']=99;call(ctx,LOAD);self.assertIs(ref.raw(),cell);self.assertEqual(ref.raw().nodes[0].values['VALUE'],1)
    def test_new_root_load_skips_throwaway_array_initialization(self):
        ctx=context();call(ctx,SAVE);fresh=rt.ExecutionContext(files=rt.MemoryFiles(ctx.files.snapshot()),variable_archives=rt.VariableArchives());original=rt.initial_value
        def initial(spec):
            if rt.collection_array_type(spec):raise AssertionError('throwaway collection root')
            return original(spec)
        with patch.object(rt,'initial_value',side_effect=initial):self.assertEqual(call(fresh,LOAD),0)
    def test_uninitialized_queue_cells_roundtrip_without_inventing_entries(self):
        ctx=context(Q);queue=raw(ctx).values[1];queue.initialized=False;queue.sequence=0;queue.entries=[];self.assertEqual(call(ctx,SAVE+' '+CLEAR+' '+LOAD),0);self.assertFalse(queue.initialized);self.assertEqual(queue.entries,[])
    def test_unknown_byte_path_nodes_roundtrip(self):
        node=('STRUCTURE','BYTE_NODE',(('VALUE',('BYTE',)),));spec=('ARRAY',2,('PATH',node,None))
        with rt._numeric_scope('pythonic'):value=rt.Array(spec)
        value.values[0].append();ctx=context();bind(ctx,value);before=payload(value);self.assertEqual(call(ctx,SAVE+' '+CLEAR+' '+LOAD),0);self.assertEqual(payload(value),before)
    def test_archive_size_limit_writes_no_partial_file(self):
        ctx=context(limit=100);self.assertNotEqual(call(ctx,SAVE),0);self.assertEqual(ctx.files.snapshot(),{})
    def test_virtual_device_capacity_failure_preserves_source_cells(self):
        ctx=context();ctx.files=rt.DeviceFiles({'FR:':{'capacity':10}});before=snap(raw(ctx));self.assertNotEqual(call(ctx,"SAVE('CACHE','FR:CACHE.VR',s)"),0);self.assertEqual(snap(raw(ctx)),before);self.assertEqual(ctx.files.snapshot(),{})
    def test_whole_missing_collection_array_payload_is_rejected(self):
        ctx=context();call(ctx,SAVE);row=saved(ctx);row['variables']['ITEM']['value']={'uninitialized':True};install(ctx,row)
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('premature decode')):self.assertEqual(call(ctx,LOAD),6)
    def test_recursive_restore_overlapping_namespace_roots_is_atomic(self):
        ctx=context(calls={'CACHE':['CHILD']});bind(ctx,raw(ctx),program='CHILD');self.assertEqual(call(ctx,"PROG_BACKUP('CACHE',PBR_VRTYPE,0,TRUE,s)"),0);raw(ctx).values[0].nodes[0].values['VALUE']=99;self.assertEqual(call(ctx,"PROG_RESTORE('CACHE.VR',s)"),4);self.assertEqual(raw(ctx).values[0].nodes[0].values['VALUE'],99)


class CollectionArchivePolicyTests(unittest.TestCase):
    def policy(self):return compile_program("SAVE('T','T.VR',s)")[1].report['collection_array_archive_policy']
    def test_report_lists_archive_and_explicit_dram_operations(self):
        policy=self.policy();self.assertEqual(policy['operations'],['SAVE','LOAD','CLEAR','PROG_BACKUP','PROG_RESTORE','PROG_CLEAR','SAVE_DRAM','restore_dram']);self.assertIn('32767',policy['preflight'])
    def test_report_records_owned_identity_and_allocation_rules(self):
        policy=self.policy();self.assertIn('Retain existing ARRAY containers',policy['identity']);self.assertIn('throwaway',policy['allocation']);self.assertIn('connected timers',policy['guards'])
    def test_report_links_offline_guide_and_existing_format(self):
        policy=self.policy();self.assertEqual(policy['guide'],'docs/collection-array-archives.md');self.assertFalse(policy['controller_validated']);self.assertIn('karel2py-variables-v1',policy['format']);self.assertIn('explicit DRAM restore only',policy['persistence'])


if __name__=='__main__':unittest.main()
