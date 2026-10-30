"""Authored dynamic PATH/QUEUE roots, allocation, aliases and saved lifetimes."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate_project
from karel2py.dynamic import creation_cost,restore_metadata,concrete_type
from karel2py.storage import typed_value
from tests.test_extended_services import compile_program
from tests.test_dynamic_narrow import create

DECL='entry,status,n,seen,prior,calls:INTEGER buffer:ARRAY[3] OF INTEGER flag:BOOLEAN'
PREFIX='''TYPE node_t=STRUCTURE id:INTEGER label:STRING[4] axes:JOINTPOS2 ENDSTRUCTURE
header_t=STRUCTURE count:INTEGER name:STRING[4] ENDSTRUCTURE
route_t=PATH NODEDATA=node_t PATHHEADER=header_t
path_alias=route_t queue_alias=QUEUE_TYPE'''
PATH=('PATH',None,None)
QUEUE=('QUEUE_TYPE',)
FILL='ROUTINE fill(q:QUEUE_TYPE) BEGIN INIT_QUEUE(q) APPEND_QUEUE(7,q,buffer,seen,status) APPEND_QUEUE(9,q,buffer,seen,status) END fill'
TAKE='ROUTINE take(q:QUEUE_TYPE) BEGIN GET_QUEUE(q,buffer,n,seen,status) END take'
GROW='ROUTINE grow(p:PATH) BEGIN APPEND_NODE(p,status) n=PATH_LEN(p) END grow'
CUSTOM='ROUTINE grow(p:route_t) BEGIN APPEND_NODE(p,status) p[1].id=7 p[1].label=\'hello\' p.count=1 p.name=\'route\' END grow'


def program(body='',**options):return compile_program(body,decl=options.pop('decl',DECL),**options)
def execute(body='',**options):
    p,r=program(body,**options);return p.run(),p._state.execution,p,r

def ref(ctx,name='ITEM',owner='CACHE'):return ctx.variables.bindings[owner,name]
def invoke(name='fill',owner='CACHE',path='ITEM'):return name+"(BYNAME('"+owner+"','"+path+"',entry)) "


class DynamicCollectionCreationTests(unittest.TestCase):
    def test_default_path_starts_empty_with_portable_node_layout(self):
        v,ctx,_,_=execute(create('PATH'));value=ref(ctx).raw()
        self.assertEqual((v['STATUS'],value.spec,value.nodes,value.data),(0,PATH,[],None));self.assertEqual(value.node_spec,rt.PREDEFINED_STRUCTURES['STD_PTH_NODE'])

    def test_queue_starts_uninitialized_without_backing_buffer(self):
        v,ctx,_,_=execute(create('QUEUE_TYPE'));q=ref(ctx).raw()
        self.assertEqual((v['STATUS'],q.spec,q.initialized,q.entries,q.sequence,q.buffer),(0,QUEUE,False,[],0,None))

    def test_direct_casefolded_and_trimmed_type_names(self):
        for kind,spec in [(' path ',PATH),('queue_type',QUEUE)]:
            v,ctx,_,_=execute(create(kind));self.assertEqual((v['STATUS'],ref(ctx).spec),(0,spec))

    def test_transparent_path_alias_uses_supplied_components(self):
        v,ctx,_,_=execute(create('path_alias'),prefix=PREFIX);value=ref(ctx).raw()
        self.assertEqual(v['STATUS'],0);self.assertEqual(value.node_spec[1],'NODE_T');self.assertEqual(value.data.spec[1],'HEADER_T')
        self.assertIs(value.data.values['COUNT'],rt.UNINITIALIZED)

    def test_transparent_queue_alias_has_exact_queue_schema(self):
        v,ctx,_,_=execute(create('queue_alias'),prefix=PREFIX);self.assertEqual((v['STATUS'],ref(ctx).spec),(0,QUEUE))

    def test_foreign_type_owner_uses_resolved_source_layout(self):
        sources={'lib':'PROGRAM LIB '+PREFIX+' BEGIN END LIB','main':'PROGRAM MAIN VAR status:INTEGER BEGIN '+create('route_t',type_owner='LIB')+' END MAIN'}
        instance=translate_project(sources).instantiate();instance.run('MAIN');self.assertEqual(ref(instance.context).raw().node_spec[1],'NODE_T')

    def test_source_program_default_uses_callee_type_environment(self):
        main="PROGRAM MAIN ROUTINE make FROM LIB BEGIN make END MAIN"
        lib='PROGRAM LIB '+PREFIX+' VAR status:INTEGER ROUTINE make BEGIN '+create('route_t',owner='')+' END make BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate();project.run('MAIN');self.assertIn(('LIB','ITEM'),project.context.variables.bindings)

    def test_group_and_pool_remain_checked_metadata(self):
        for kind in ('PATH','QUEUE_TYPE'):
            for group,pool in ((0,0),(32,-1),(2,0)):
                v,ctx,_,_=execute(create(kind,group=group,pool=pool));self.assertEqual(v['STATUS'],0);self.assertEqual(ctx.variables.metadata['CACHE','ITEM'],dict(group=group,memory_pool=pool))

    def test_resource_array_dimensions_are_rejected_without_allocation(self):
        for kind in ('PATH','QUEUE_TYPE','route_t','queue_alias'):
            for dims in ((1,0,0),(2,3,0),(1,1,1)):
                v,ctx,_,_=execute(create(kind,dims=dims),prefix=PREFIX);self.assertEqual((v['STATUS'],ctx.variables.bindings),(5,{}))

    def test_invalid_names_group_pool_and_dimensions_preserve_store(self):
        for call,code in [(create('PATH',name='BAD.NAME'),2),(create('QUEUE_TYPE',group=33),5),(create('PATH',pool=1),2),(create('PATH',dims=(0,1,0)),5)]:
            v,ctx,_,_=execute(call);self.assertEqual((v['STATUS'],ctx.variables.bindings),(code,{}))

    def test_duplicate_collection_creation_preserves_identity_and_contents(self):
        v,ctx,_,_=execute(create('PATH')+invoke('grow')+create('QUEUE_TYPE'),routines=GROW)
        self.assertEqual((v['STATUS'],ref(ctx).spec,len(ref(ctx).raw().nodes)),(3,PATH,1))

    def test_existing_descendant_binding_blocks_collection_root(self):
        ctx=rt.ExecutionContext();ctx.variables.define('CACHE','ITEM.ID',('INTEGER',),7)
        v,_,_,_=execute(create('PATH'),context=ctx);self.assertEqual((v['STATUS'],ref(ctx,'ITEM.ID').raw()),(3,7));self.assertNotIn(('CACHE','ITEM'),ctx.variables.bindings)

    def test_declared_resource_global_cannot_be_replaced(self):
        v,ctx,p,_=execute(create('PATH',owner='',name='LOCAL'),decl=DECL+' local:PATH');self.assertEqual(v['STATUS'],3);self.assertFalse(ctx.variables.bindings);self.assertEqual(p._state.values['LOCAL'].nodes,[])

    def test_independent_created_roots_have_separate_storage(self):
        v,ctx,_,_=execute(create('PATH')+create('PATH',name='OTHER')+invoke('grow'),routines=GROW)
        self.assertIsNot(ref(ctx).raw(),ref(ctx,'OTHER').raw());self.assertEqual((len(ref(ctx).raw().nodes),ref(ctx,'OTHER').raw().nodes),(1,[]))

    def test_embedded_resource_creation_remains_rejected(self):
        for kind in ('ARRAY OF FILE','ARRAY OF PATH','ARRAY OF QUEUE_TYPE'):
            v,ctx,_,_=execute(create(kind));self.assertEqual((v['STATUS'],ctx.variables.bindings),(5,{}))

    def test_preserved_runtime_does_not_gain_collection_creation(self):
        p,_=program(prefix=PREFIX)
        with rt._numeric_scope('strict'):
            for kind in ('PATH','QUEUE_TYPE','route_t','queue_alias'):
                self.assertIsNone(concrete_type(p._state.execution,p._state,'T',kind,0,(0,0,0),1))

    def test_report_describes_boundaries_and_reservation_accounting(self):
        _,_,_,r=execute(create('PATH'));policy=r.report['dynamic_collection_policy'];self.assertIn('header',policy['allocation']);self.assertIn('QUEUE_TYPE',policy['source']);self.assertFalse(policy['controller_validated'])


class DynamicCollectionInterfaceTests(unittest.TestCase):
    def test_byname_queue_procedures_share_the_created_object(self):
        v,ctx,_,_=execute(create('QUEUE_TYPE')+invoke()+invoke('take'),routines=FILL+' '+TAKE)
        self.assertEqual((v['N'],v['SEEN'],v['STATUS'],v['BUFFER']),(7,1,0,[9,0,0]));self.assertEqual(ref(ctx).raw().entries,[(2,9)])

    def test_uninitialized_queue_rejects_without_inventing_entries(self):
        p,_=program(create('QUEUE_TYPE')+invoke('take'),routines=TAKE)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'INIT_QUEUE'):p.run()
        self.assertFalse(ref(p._state.execution).raw().initialized)

    def test_default_path_append_and_remove_use_live_alias(self):
        routine='ROUTINE work(p:PATH) BEGIN APPEND_NODE(p,status) APPEND_NODE(p,status) DELETE_NODE(p,1,status) n=PATH_LEN(p) END work'
        v,ctx,_,_=execute(create('PATH')+invoke('work'),routines=routine);self.assertEqual((v['N'],len(ref(ctx).raw().nodes)),(1,1))

    def test_custom_header_node_and_string_capacity_are_preserved(self):
        v,ctx,_,_=execute(create('route_t')+invoke('grow'),prefix=PREFIX,routines=CUSTOM);p=ref(ctx).raw()
        self.assertEqual((p.nodes[0].values['ID'],p.nodes[0].values['LABEL'],p.data.values['COUNT'],p.data.values['NAME']),(7,'hell',1,'rout'))

    def test_get_set_var_access_custom_header_and_nodes(self):
        v,ctx,_,_=execute(create('route_t')+invoke('grow')+" SET_VAR(entry,'CACHE','ITEM[1].ID',9,status) GET_VAR(entry,'CACHE','ITEM[1].ID',n,status) SET_VAR(entry,'CACHE','ITEM.COUNT',2,status)",prefix=PREFIX,routines=CUSTOM)
        self.assertEqual((v['N'],v['STATUS'],ref(ctx).raw().data.values['COUNT']),(9,0,2))

    def test_joint_axis_paths_in_dynamic_nodes_keep_real_cells(self):
        v,ctx,_,_=execute(create('route_t')+invoke('grow')+" SET_VAR(entry,'CACHE','ITEM[1].AXES[2]',2.5,status) GET_VAR(entry,'CACHE','ITEM[1].AXES[2]',out,status)",prefix=PREFIX,routines=CUSTOM,decl=DECL+' out:REAL')
        self.assertEqual((v['OUT'],v['STATUS']),(2.5,0));self.assertIs(ref(ctx).raw().nodes[0].values['AXES'].values[0],rt.UNINITIALIZED)

    def test_queue_variable_transfer_clones_contents_without_buffer_alias(self):
        v,ctx,_,_=execute(create('QUEUE_TYPE')+invoke()+" GET_VAR(entry,'CACHE','ITEM',copy,status) INIT_QUEUE(copy)",routines=FILL,decl=DECL+' copy:QUEUE_TYPE')
        self.assertEqual((v['STATUS'],ref(ctx).raw().entries),(0,[(1,7),(2,9)]))

    def test_set_queue_variable_retains_target_object_identity(self):
        v,ctx,p,_=execute(create('QUEUE_TYPE')+invoke()+" GET_VAR(entry,'CACHE','ITEM',copy,status) SET_VAR(entry,'CACHE','ITEM',copy,status)",routines=FILL,decl=DECL+' copy:QUEUE_TYPE')
        self.assertEqual(v['STATUS'],0);self.assertIsNone(ref(ctx).raw().buffer);self.assertEqual(ref(ctx).raw().entries,[(1,7),(2,9)])

    def test_whole_path_variable_transfer_remains_a_data_boundary(self):
        from karel2py.lexer import TranslationError
        with self.assertRaises(TranslationError):program(create('PATH')+" GET_VAR(entry,'CACHE','ITEM',local,status)",decl=DECL+' local:PATH')

    def test_byname_type_mismatch_preserves_entry_and_routine_effects(self):
        p,_=program(create('PATH')+" entry=77 n=0 "+invoke(),routines=FILL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type does not match'):p.run()
        self.assertEqual((p.snapshot()['ENTRY'],p.snapshot()['N'],p._state.local_frames),(77,0,[]))

    def test_namespace_rename_keeps_captured_resource_reference(self):
        routines="ROUTINE work(p:PATH) BEGIN RENAME_VARS('CACHE','MOVED',status) APPEND_NODE(p,status) n=PATH_LEN(p) END work"
        v,ctx,_,_=execute(create('PATH')+invoke('work'),routines=routines);self.assertEqual(v['N'],1);self.assertNotIn(('CACHE','ITEM'),ctx.variables.bindings);self.assertEqual(len(ref(ctx,owner='MOVED').raw().nodes),1)

    def test_root_rename_keeps_existing_entry_number(self):
        body=create('PATH')+invoke('grow')+" prior=entry RENAME_VAR('CACHE','ITEM','RENAMED',status) "+invoke('grow',path='RENAMED')
        v,ctx,_,_=execute(body,routines=GROW);self.assertEqual((v['ENTRY'],v['N']),(v['PRIOR'],2));self.assertIn(('CACHE','RENAMED'),ctx.variables.metadata)

    def test_pause_resume_retains_alias_across_rename(self):
        routine="ROUTINE work(p:PATH) BEGIN APPEND_NODE(p,status) PAUSE APPEND_NODE(p,status) n=PATH_LEN(p) END work"
        p,_=program(create('PATH')+invoke('work'),routines=routine,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        value=ref(p._state.execution).raw();execute("RENAME_VAR('CACHE','ITEM','RENAMED',status)",context=p._state.execution)
        self.assertEqual(p.resume()['N'],2);self.assertIs(ref(p._state.execution,'RENAMED').raw(),value);self.assertFalse(p._state.local_frames)

    def test_abort_cleans_frames_but_preserves_completed_collection_edits(self):
        p,_=program(create('PATH')+invoke('work'),routines='ROUTINE work(p:PATH) BEGIN APPEND_NODE(p,status) ABORT END work',cooperative=True)
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(len(ref(p._state.execution).raw().nodes),1);self.assertEqual(p._state.local_frames,[])

    def test_linked_queue_routine_can_mutate_dynamic_root(self):
        main='PROGRAM MAIN VAR status,entry:INTEGER ROUTINE fill(q:QUEUE_TYPE) FROM LIB BEGIN '+create('QUEUE_TYPE')+invoke()+' END MAIN'
        lib='PROGRAM LIB VAR buffer:ARRAY[3]OF INTEGER status,seen:INTEGER '+FILL+' BEGIN END LIB'
        instance=translate_project({'main':main,'lib':lib}).instantiate();instance.run('MAIN');self.assertEqual(ref(instance.context).raw().entries,[(1,7),(2,9)])

    def test_var_info_path_uses_existing_type_code_and_missing_policy(self):
        body=create('PATH')+" VAR_INFO('CACHE','ITEM',flag,type_name,seen,dims,n,status)"
        v,_,_,_=execute(body,decl=DECL+' type_name:STRING[12] dims:ARRAY[3]OF INTEGER')
        self.assertEqual((v['STATUS'],v['SEEN'],v['TYPE_NAME'],v['FLAG'],v['DIMS']),(0,31,'PATH',False,[0,0,0]))

    def test_var_info_queue_retains_unknown_type_code_status(self):
        body=create('QUEUE_TYPE')+" seen=77 VAR_INFO('CACHE','ITEM',flag,type_name,seen,dims,n,status)"
        v,_,_,_=execute(body,decl=DECL+' type_name:STRING[12] dims:ARRAY[3]OF INTEGER');self.assertEqual((v['STATUS'],v['SEEN']),(4,77))

    def test_var_list_unfiltered_includes_collections_but_path_filter_is_exact(self):
        body=create('PATH')+create('QUEUE_TYPE',name='QUEUE')+" VAR_LIST('CACHE','*',0,0,2,names,n,status) prior=n VAR_LIST('CACHE','*',31,0,2,names,n,status)"
        v,_,_,_=execute(body,decl=DECL+' names:ARRAY[3]OF STRING[36]');self.assertEqual((v['PRIOR'],v['N'],v['NAMES']),(2,1,['ITEM','','']))

    def test_sparse_node_alias_rename_keeps_selected_storage(self):
        v,ctx,p,_=execute(create('route_t')+invoke('grow'),prefix=PREFIX,routines=CUSTOM)
        node=ctx.resolve(p._state,'CACHE','ITEM[1].ID');ctx.variables.bind('CACHE','ITEM[1].ID',node)
        execute("RENAME_VAR('CACHE','ITEM','RENAMED',status) SET_VAR(entry,'CACHE','RENAMED[1].ID',42,status)",context=ctx)
        self.assertIs(ctx.variables.bindings['CACHE','RENAMED[1].ID'],node);self.assertEqual(node.raw(),42)


class DynamicCollectionPersistenceTests(unittest.TestCase):
    def test_empty_created_collections_and_policy_roundtrip(self):
        _,ctx,_,_=execute(create('PATH',pool=-1)+create('QUEUE_TYPE',name='QUEUE',group=2));saved=json.loads(json.dumps(ctx.to_config()))
        self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_partial_path_nodes_header_and_axes_roundtrip(self):
        _,ctx,_,_=execute(create('route_t')+invoke('grow'),prefix=PREFIX,routines=CUSTOM);saved=json.loads(json.dumps(ctx.to_config()));other=rt.ExecutionContext.from_config(saved)
        self.assertEqual(other.to_config(),saved);self.assertIs(ref(other).raw().nodes[0].values['AXES'].values[1],rt.UNINITIALIZED)

    def test_restored_queue_rebinds_to_new_explicit_buffer(self):
        _,ctx,_,_=execute(create('QUEUE_TYPE')+invoke(),routines=FILL);other=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertIsNone(ref(other).raw().buffer);v,_,p,_=execute(invoke('take'),context=other,routines=TAKE)
        self.assertEqual((v['N'],v['STATUS']),(7,0));self.assertIs(ref(other).raw().buffer,p._state.values['BUFFER'])

    def test_restored_created_path_can_append_without_recreating_type(self):
        _,ctx,_,_=execute(create('PATH')+invoke('grow'),routines=GROW);other=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        v,_,_,_=execute(invoke('grow'),context=other,routines=GROW);self.assertEqual(v['N'],2)

    def test_restored_queue_does_not_persist_original_buffer_reference(self):
        _,ctx,p,_=execute(create('QUEUE_TYPE')+invoke(),routines=FILL);saved=ctx.to_config();row=next(r for r in saved['variables'] if r['program']=='CACHE')
        self.assertEqual(set(row['value']),{'initialized','sequence','entries'});self.assertNotIn('buffer',json.dumps(row))

    def test_malformed_path_metadata_schema_rejected_before_value_decode(self):
        for spec in [('PATH',('CONFIG',),None),('PATH',None,('FILE',)),('PATH',None),('QUEUE_TYPE',1)]:
            ctx=rt.VariableStore()
            with self.subTest(spec=spec),self.assertRaises(ValueError),patch('karel2py.dynamic.runtime') as get:
                get.return_value=rt;restore_metadata(ctx,'CACHE','ITEM',dict(group=0,memory_pool=0),spec)
            self.assertFalse(ctx.metadata)

    def test_collection_payload_validation_is_not_weakened_by_creation(self):
        _,ctx,_,_=execute(create('QUEUE_TYPE'));saved=ctx.to_config();row=next(r for r in saved['variables'] if r['program']=='CACHE');row['value']['entries']=[[1,7]]
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(saved)

    def test_invalid_creation_policy_rejects_saved_resource_roots(self):
        _,ctx,_,_=execute(create('PATH'));original=ctx.to_config()
        for replacement in [{'group':True,'memory_pool':0},{'group':33,'memory_pool':0},{'group':0,'memory_pool':1}]:
            saved=deepcopy(original);next(r for r in saved['variables'] if r['program']=='CACHE')['creation']=replacement
            with self.subTest(replacement=replacement),self.assertRaises(ValueError):rt.ExecutionContext.from_config(saved)

    def test_queue_archive_roundtrip_preserves_creation_metadata(self):
        ctx=rt.ExecutionContext(variable_archives=rt.VariableArchives(),files=rt.MemoryFiles())
        execute(create('QUEUE_TYPE',pool=-1)+invoke()+" SAVE('CACHE','queue.VR',status)",context=ctx,routines=FILL)
        fresh=rt.ExecutionContext(variable_archives=rt.VariableArchives(),files=rt.MemoryFiles(ctx.files.snapshot()))
        v,_,_,_=execute("LOAD('queue.VR',0,status) "+invoke('take'),context=fresh,routines=TAKE)
        self.assertEqual((v['STATUS'],v['N'],fresh.variables.metadata['CACHE','ITEM']),(0,7,dict(group=0,memory_pool=-1)))

    def test_variable_archives_keep_path_roots_explicitly_excluded(self):
        ctx=rt.ExecutionContext(variable_archives=rt.VariableArchives(),files=rt.MemoryFiles());execute(create('PATH')+" SAVE('CACHE','path.VR',status)",context=ctx)
        saved=ctx.variable_archives.decode(ctx.files.snapshot()['PATH.VR']);self.assertIn('ITEM',saved['excluded']);self.assertEqual(saved['variables'],{})


class DynamicCollectionAllocationTests(unittest.TestCase):
    def test_descriptors_and_header_leaves_use_explicit_costs(self):
        node=('STRUCTURE','NODE_T',(('ID',('INTEGER',)),));head=('STRUCTURE','HEADER_T',(('A',('ARRAY',2,('INTEGER',))),))
        self.assertEqual([creation_cost(s) for s in [QUEUE,PATH,('PATH',node,None),('PATH',node,head)]],[1,1,1,3])

    def test_data_creation_costs_keep_existing_scalar_leaf_accounting(self):
        for spec,count in [(('INTEGER',),1),(('JOINTPOS',3),3),(('ARRAY',4,('SHORT',)),4)]:self.assertEqual(creation_cost(spec),count)

    def test_big_node_prototype_is_valid_without_allocating_nodes(self):
        prefix='TYPE node_t=STRUCTURE data:ARRAY[32767]OF INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        v,ctx,_,_=execute(create('route_t'),prefix=prefix);self.assertEqual((v['STATUS'],creation_cost(ref(ctx).spec),ref(ctx).raw().nodes),(0,1,[]))

    def test_header_limit_includes_descriptor_before_allocation(self):
        for count,status in [(32766,0),(32767,6)]:
            prefix=f'TYPE header_t=STRUCTURE data:ARRAY[{count}]OF INTEGER ENDSTRUCTURE route_t=PATH PATHHEADER=header_t'
            v,ctx,_,_=execute(create('route_t'),prefix=prefix);self.assertEqual(v['STATUS'],status)
            self.assertEqual(bool(ctx.variables.bindings),not status)

    def test_combined_budget_counts_existing_created_data_and_collections(self):
        v,ctx,_,_=execute(create('INTEGER',name='DATA',dims=(32766,0,0))+create('QUEUE_TYPE')+create('PATH',name='EXTRA'))
        self.assertEqual(v['STATUS'],6);self.assertEqual(set(ctx.variables.bindings),{('CACHE','DATA'),('CACHE','ITEM')})

    def test_header_reservation_remains_after_saved_restore(self):
        prefix='TYPE header_t=STRUCTURE data:ARRAY[32766]OF INTEGER ENDSTRUCTURE route_t=PATH PATHHEADER=header_t'
        _,ctx,_,_=execute(create('route_t'),prefix=prefix);other=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        v,_,_,_=execute(create('INTEGER',name='EXTRA'),context=other);self.assertEqual(v['STATUS'],6)

    def test_metadata_budget_rejects_before_decoding_new_payload(self):
        _,ctx,_,_=execute(create('INTEGER',name='DATA',dims=(32767,0,0)));saved=ctx.to_config();saved['variables'].append(dict(program='CACHE',path='EXTRA',type=['PATH',None,None],value={'deliberately':'invalid'},creation=dict(group=0,memory_pool=0)))
        with self.assertRaisesRegex(ValueError,'32767'):rt.ExecutionContext.from_config(saved)

    def test_nested_component_depth_is_bounded_before_allocation(self):
        node=('INTEGER',)
        for n in range(65):node=('STRUCTURE','S'+str(n),(('VALUE',node),))
        with self.assertRaisesRegex(ValueError,'64'):creation_cost(('PATH',node,None))

    def test_embedded_resource_components_and_array_roots_fail_closed(self):
        cases=[('PATH',('STRUCTURE','N',(('F',('FILE',)),)),None),('ARRAY',2,QUEUE),('ARRAY',1,PATH)]
        for spec in cases:
            with self.subTest(spec=spec),self.assertRaises(ValueError):creation_cost(spec)

    def test_budget_failure_retains_status_without_creating_collection(self):
        p,_=program('status=77 '+create('PATH'));original=p._state.tick
        def tick(line=None):
            if any(r['operation']=='CREATE_VAR' for r in p._state.service_requests):raise rt.KarelRuntimeError('authored budget failure')
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick),self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['STATUS'],p._state.execution.variables.bindings),(77,{}))

    def test_checkpoint_collision_preserves_the_other_writer(self):
        p,_=program(create('PATH'));ctx=p._state.execution;original=p._state.tick;fired=[]
        def tick(line=None):
            if not fired and any(r['operation']=='CREATE_VAR' for r in p._state.service_requests):fired.append(1);ctx.variables.define('CACHE','ITEM',('INTEGER',),99)
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick):v=p.run()
        self.assertEqual((v['STATUS'],ref(ctx).raw(),ref(ctx).spec),(3,99,('INTEGER',)))

    def test_checkpoint_capacity_change_is_rechecked_before_creation(self):
        p,_=program(create('QUEUE_TYPE'));ctx=p._state.execution;original=p._state.tick;fired=[]
        def tick(line=None):
            if not fired and any(r['operation']=='CREATE_VAR' for r in p._state.service_requests):
                fired.append(1);ctx.variables.define('SIDE','DATA',('ARRAY',32767,('INTEGER',)));ctx.variables.metadata['SIDE','DATA']=dict(group=0,memory_pool=0)
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick):v=p.run()
        self.assertEqual(v['STATUS'],6);self.assertNotIn(('CACHE','ITEM'),ctx.variables.bindings)

    def test_checkpoint_store_replacement_fails_without_publishing_to_old_bank(self):
        p,_=program('status=77 '+create('PATH'));ctx=p._state.execution;old=ctx.variables;original=p._state.tick;fired=[]
        def tick(line=None):
            if not fired and any(r['operation']=='CREATE_VAR' for r in p._state.service_requests):fired.append(1);ctx.variables=rt.VariableStore()
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick),self.assertRaisesRegex(rt.KarelRuntimeError,'store changed'):p.run()
        self.assertEqual((p.snapshot()['STATUS'],old.bindings,ctx.variables.bindings),(77,{},{}))


class DynamicCollectionBoundaryTests(unittest.TestCase):
    def test_narrow_partial_node_data_retains_unknown_and_missing_markers(self):
        prefix='TYPE node_t=STRUCTURE b:BYTE s:SHORT ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        routine='ROUTINE grow(p:route_t) BEGIN APPEND_NODE(p,status) p[1].s=4 END grow'
        _,ctx,_,_=execute(create('route_t')+invoke('grow'),prefix=prefix,routines=routine);restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        node=ref(restored).raw().nodes[0];self.assertIs(node.values['B'],rt.UNKNOWN_BYTE);self.assertEqual(node.values['S'],4)

    def test_byname_can_capture_dynamic_path_scalar_node_alias(self):
        routine=CUSTOM+' ROUTINE bump(value:INTEGER) BEGIN value=value+1 END bump'
        _,ctx,_,_=execute(create('route_t')+invoke('grow')+invoke('bump',path='ITEM[1].ID'),prefix=PREFIX,routines=routine)
        self.assertEqual(ref(ctx).raw().nodes[0].values['ID'],8)

    def test_custom_path_cannot_alias_default_path_formal(self):
        p,_=program(create('route_t')+' entry=77 '+invoke('wrong'),prefix=PREFIX,routines='ROUTINE wrong(p:PATH) BEGIN calls=99 END wrong')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type does not match'):p.run()
        self.assertEqual(p.snapshot()['ENTRY'],77);self.assertIs(p._state.values['CALLS'],rt.UNINITIALIZED)

    def test_queue_backing_buffer_identity_remains_enforced(self):
        routine=FILL+' ROUTINE wrong(q:QUEUE_TYPE) BEGIN GET_QUEUE(q,other,n,seen,status) END wrong'
        p,_=program(create('QUEUE_TYPE')+invoke()+invoke('wrong'),routines=routine,decl=DECL+' other:ARRAY[3]OF INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'original backing'):p.run()
        self.assertEqual(ref(p._state.execution).raw().entries,[(1,7),(2,9)])

    def test_rename_conflict_retains_both_resource_policies(self):
        body=create('PATH',pool=-1)+create('QUEUE_TYPE',name='OTHER')+" RENAME_VAR('CACHE','ITEM','OTHER',status)"
        v,ctx,_,_=execute(body);self.assertEqual(v['STATUS'],3);self.assertEqual(ref(ctx).spec,PATH);self.assertEqual(ref(ctx,'OTHER').spec,QUEUE);self.assertEqual(ctx.variables.metadata['CACHE','ITEM']['memory_pool'],-1)

    def test_renamed_header_keeps_reservation_in_saved_context(self):
        prefix='TYPE header_t=STRUCTURE data:ARRAY[32766]OF INTEGER ENDSTRUCTURE route_t=PATH PATHHEADER=header_t'
        _,ctx,_,_=execute(create('route_t')+" RENAME_VAR('CACHE','ITEM','KEPT',status)",prefix=prefix)
        ctx=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())));v,_,_,_=execute(create('QUEUE_TYPE'),context=ctx)
        self.assertEqual(v['STATUS'],6);self.assertIn(('CACHE','KEPT'),ctx.variables.metadata)

    def test_archive_clear_resets_queue_data_but_keeps_policy_and_identity(self):
        ctx=rt.ExecutionContext(variable_archives=rt.VariableArchives(),files=rt.MemoryFiles());execute(create('QUEUE_TYPE',pool=-1)+invoke(),context=ctx,routines=FILL);q=ref(ctx).raw()
        execute("CLEAR('CACHE.VR',status)",context=ctx)
        self.assertIs(ref(ctx).raw(),q);self.assertEqual((q.initialized,q.entries,q.buffer),(False,[],None));self.assertEqual(ctx.variables.metadata['CACHE','ITEM']['memory_pool'],-1)

    def test_saved_path_header_payload_cannot_omit_declared_fields(self):
        _,ctx,_,_=execute(create('route_t'),prefix=PREFIX);saved=ctx.to_config();row=next(r for r in saved['variables'] if r['program']=='CACHE');row['value']['data']={}
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(saved)

    def test_known_config_turns_remain_validated_inside_dynamic_path(self):
        prefix='TYPE node_t=STRUCTURE cfg:CONFIG ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        routine='ROUTINE grow(p:route_t) BEGIN APPEND_NODE(p,status) END grow'
        _,ctx,_,_=execute(create('route_t')+invoke('grow'),prefix=prefix,routines=routine);ref(ctx).raw().nodes[0].values['CFG'].values['CFG_TURN_NO1']=8
        with self.assertRaisesRegex(rt.KarelRuntimeError,'-8..7'):ctx.to_config()

    def test_cycle_shaped_malformed_component_fails_before_recursing(self):
        nested=[];node=('STRUCTURE','NODE_T',(('NEXT',nested),));nested.append(node)
        with self.assertRaises(ValueError):creation_cost(('PATH',node,None))

    def test_overwide_header_schema_is_unsupported_before_allocation(self):
        prefix='TYPE header_t=STRUCTURE a:ARRAY[32767]OF INTEGER b:INTEGER ENDSTRUCTURE route_t=PATH PATHHEADER=header_t'
        v,ctx,_,_=execute(create('route_t'),prefix=prefix);self.assertEqual((v['STATUS'],ctx.variables.bindings),(5,{}))

    def test_checkpoint_guard_also_preserves_existing_scalar_creation_contract(self):
        p,_=program(create('INTEGER'));ctx=p._state.execution;original=p._state.tick;fired=[]
        def tick(line=None):
            if not fired and any(r['operation']=='CREATE_VAR' for r in p._state.service_requests):fired.append(1);ctx.variables.define('CACHE','ITEM',('INTEGER',),42)
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick):v=p.run()
        self.assertEqual((v['STATUS'],ref(ctx).raw()),(3,42))

    def test_resource_group_metadata_does_not_discover_robot_context(self):
        v,ctx,_,_=execute(create('PATH',group=32));self.assertEqual(v['STATUS'],0);self.assertIsNone(ctx.robot);self.assertEqual(ctx.variables.metadata['CACHE','ITEM']['group'],32)


class DynamicCollectionTerminalTests(unittest.TestCase):
    def test_caught_terminal_abort_cannot_publish_after_checkpoint(self):
        for kind in ('PATH','QUEUE_TYPE','INTEGER'):
            p,_=program('status=77 '+create(kind));original=p._state.tick;fired=[]
            def tick(line=None):
                original(line)
                if not fired and any(r['operation']=='CREATE_VAR' for r in p._state.service_requests):
                    fired.append(1)
                    try:p._state.abort(7)
                    except rt.KarelAbort:pass
            with self.subTest(kind=kind),patch.object(p._state,'tick',side_effect=tick),self.assertRaises(rt.KarelAbort):p.run()
            self.assertEqual((p.snapshot()['STATUS'],p._state.execution.variables.bindings),(77,{}));self.assertEqual(p.abort_info['line'],7)

    def test_parent_abort_cannot_publish_from_child_after_checkpoint(self):
        ctx=rt.ExecutionContext();parent,_=program(context=ctx);p,_=program('status=77 '+create('PATH'),context=ctx);p._state._budget_parent=parent._state
        original=p._state.tick;fired=[]
        def tick(line=None):
            original(line)
            if not fired and any(r['operation']=='CREATE_VAR' for r in p._state.service_requests):
                fired.append(1)
                try:parent._state.abort(9)
                except rt.KarelAbort:pass
        with patch.object(p._state,'tick',side_effect=tick),self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual((p.snapshot()['STATUS'],ctx.variables.bindings),(77,{}));self.assertEqual(parent.abort_info['line'],9)

    def test_stopped_owner_cannot_publish_after_checkpoint(self):
        p,_=program('status=77 '+create('QUEUE_TYPE'));original=p._state.tick;fired=[]
        def tick(line=None):
            original(line)
            if not fired and any(r['operation']=='CREATE_VAR' for r in p._state.service_requests):fired.append(1);p._state.task_state='stopped'
        with patch.object(p._state,'tick',side_effect=tick),self.assertRaises(rt.KarelStop):p.run()
        self.assertEqual((p.snapshot()['STATUS'],p._state.execution.variables.bindings),(77,{}))


if __name__=='__main__':unittest.main()
