"""Authored logical PATH archive ownership, preflight and replay checks."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate,translate_project
from karel2py import variable_archives as vr
from karel2py.storage import typed_value
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_variable_archives import execute,envelope,install

NODE=('STRUCTURE','NODE_T',(('VALUE',('INTEGER',)),))
HEADER=('STRUCTURE','HEADER_T',(('COUNT',('INTEGER',)),))
SPEC=('PATH',NODE,HEADER)
PREFIX='TYPE node_t=STRUCTURE value:INTEGER ENDSTRUCTURE header_t=STRUCTURE count:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t PATHHEADER=header_t'


def path(spec=SPEC,values=(7,9)):
    value=rt.PathValue(spec)
    for number in values:value.append();value.nodes[-1].values['VALUE']=number
    if value.data is not None:value.data.values['COUNT']=len(values)
    return value


def bind(ctx,value=None,*,program='CACHE',name='ROUTE'):
    value=path() if value is None else value
    ref=rt.Reference(value.spec,{'value':value},'value');ctx.variables.bind(program,name,ref);return ref


def context(*,value=None,**options):
    ctx=rt.ExecutionContext(variable_archives=rt.VariableArchives(**options),files=rt.MemoryFiles());bind(ctx,value);return ctx


def raw(ctx,program='CACHE',name='ROUTE'):return ctx.variables.bindings[program,name].raw()
def snapshot(value):return rt.snapshot_value(value)
def save(ctx):return execute(ctx,"SAVE('CACHE','CACHE.VR',s)")['S']
def load(ctx):return execute(ctx,"LOAD('CACHE.VR',0,s)")['S']
def row(ctx):return json.loads(bytes(ctx.files.files['CACHE.VR']))
def record(value=None):
    with rt._numeric_scope('pythonic'):return typed_value(path() if value is None else value)


class PathArchiveValueTests(unittest.TestCase):
    def test_save_includes_schema_nodes_header_and_no_excluded_path(self):
        ctx=context();self.assertEqual(save(ctx),0);saved=row(ctx)
        self.assertEqual(saved['excluded'],[]);self.assertEqual(saved['variables']['ROUTE'],record())

    def test_clear_then_load_restores_complete_logical_path(self):
        ctx=context();before=snapshot(raw(ctx));self.assertEqual(save(ctx),0)
        self.assertEqual(execute(ctx,"CLEAR('CACHE.VR',s)")['S'],0);self.assertEqual(raw(ctx).nodes,[])
        self.assertIs(raw(ctx).data.values['COUNT'],rt.UNINITIALIZED);self.assertEqual(load(ctx),0);self.assertEqual(snapshot(raw(ctx)),before)

    def test_load_preserves_existing_root_and_header_identity(self):
        ctx=context();root=raw(ctx);header=root.data;save(ctx);root.nodes[0].values['VALUE']=99
        self.assertEqual(load(ctx),0);self.assertIs(raw(ctx),root);self.assertIs(root.data,header);self.assertEqual(root.nodes[0].values['VALUE'],7)

    def test_captured_node_alias_stays_on_detached_preload_storage(self):
        ctx=context();save(ctx);root=raw(ctx);nodes=root.nodes;field=rt.field_reference(nodes[0],'VALUE');field.set(99)
        self.assertEqual(load(ctx),0);self.assertIsNot(root.nodes,nodes);self.assertEqual(field.raw(),99)

    def test_captured_header_alias_observes_restored_value(self):
        ctx=context();save(ctx);field=rt.field_reference(raw(ctx).data,'COUNT');field.set(99)
        self.assertEqual(load(ctx),0);self.assertEqual(field.raw(),2)

    def test_clear_preserves_root_header_but_detaches_old_nodes(self):
        ctx=context();root=raw(ctx);header=root.data;nodes=root.nodes
        self.assertEqual(execute(ctx,"CLEAR('CACHE.VR',s)")['S'],0);self.assertIs(raw(ctx),root);self.assertIs(root.data,header)
        self.assertEqual(nodes[0].values['VALUE'],7);self.assertIsNot(root.nodes,nodes)

    def test_partial_scalar_and_whole_missing_nodes_survive_replay(self):
        ctx=context();root=raw(ctx);root.nodes[0].values['VALUE']=rt.UNINITIALIZED;root.nodes[1]=rt.UNINITIALIZED;save(ctx)
        self.assertEqual(load(ctx),0);self.assertIs(root.nodes[0].values['VALUE'],rt.UNINITIALIZED);self.assertIs(root.nodes[1],rt.UNINITIALIZED)

    def test_missing_header_is_preserved_and_later_clear_materializes_it(self):
        ctx=context();raw(ctx).data=rt.UNINITIALIZED;self.assertEqual(save(ctx),0);self.assertEqual(load(ctx),0);self.assertIs(raw(ctx).data,rt.UNINITIALIZED)
        self.assertEqual(execute(ctx,"CLEAR('CACHE.VR',s)")['S'],0);self.assertIs(raw(ctx).data.values['COUNT'],rt.UNINITIALIZED)

    def test_empty_default_path_roundtrips_without_inventing_nodes(self):
        ctx=context(value=rt.PathValue(('PATH',None,None)));self.assertEqual(save(ctx),0);self.assertEqual(load(ctx),0);self.assertEqual(snapshot(raw(ctx)),dict(nodes=[],data=None))

    def test_partial_default_node_pose_and_config_roundtrip(self):
        value=rt.PathValue(('PATH',None,None));value.append();value.nodes[0].values['NODE_POS'].values['LOCATION'].values['X']=2.5
        ctx=context(value=value);self.assertEqual(save(ctx),0);self.assertEqual(load(ctx),0);self.assertEqual(raw(ctx).nodes[0].values['NODE_POS'].values['LOCATION'].values['X'],2.5)

    def test_unknown_byte_short_and_partial_joint_axes_keep_markers(self):
        node=('STRUCTURE','NODE_T',(('B',('BYTE',)),('S',('SHORT',)),('J',('JOINTPOS',2))))
        value=rt.PathValue(('PATH',node,None));value.append();value.nodes[0].values['J'].values[0]=2.5;ctx=context(value=value)
        self.assertEqual(save(ctx),0);self.assertEqual(load(ctx),0);n=raw(ctx).nodes[0]
        self.assertIs(n.values['B'],rt.UNKNOWN_BYTE);self.assertIs(n.values['S'],rt.UNINITIALIZED);self.assertEqual(n.values['J'].values[0],2.5)

    def test_save_and_load_do_not_share_live_or_serialized_nodes(self):
        ctx=context();save(ctx);saved=row(ctx);raw(ctx).nodes[0].values['VALUE']=99;self.assertEqual(saved['variables']['ROUTE']['value']['nodes'][0]['VALUE'],7)
        load(ctx);saved['variables']['ROUTE']['value']['nodes'][0]['VALUE']=88;self.assertEqual(raw(ctx).nodes[0].values['VALUE'],7)

    def test_fresh_namespace_load_uses_record_identity_and_exact_layout(self):
        ctx=context();save(ctx);fresh=rt.ExecutionContext(variable_archives=rt.VariableArchives(),files=rt.MemoryFiles(ctx.files.snapshot()))
        self.assertEqual(load(fresh),0);self.assertEqual(raw(fresh).spec,SPEC);self.assertEqual(snapshot(raw(fresh)),snapshot(raw(ctx)))

    def test_legacy_excluded_path_record_leaves_existing_path_untouched(self):
        ctx=context();old=envelope(variables={});old['excluded']=['ROUTE'];install(ctx,old,'CACHE.VR');root=raw(ctx);nodes=root.nodes
        self.assertEqual(load(ctx),0);self.assertIs(raw(ctx),root);self.assertIs(root.nodes,nodes)

    def test_nested_header_array_alias_is_preserved(self):
        header=('STRUCTURE','HEADER_T',(('DATA',('ARRAY',2,('INTEGER',))),));value=rt.PathValue(('PATH',NODE,header));value.data.values['DATA'].values[:]=[3,4]
        ctx=context(value=value);save(ctx);array=value.data.values['DATA'];array.values[0]=99
        self.assertEqual(load(ctx),0);self.assertIs(value.data.values['DATA'],array);self.assertEqual(array.values,[3,4])


class PathArchiveValidationTests(unittest.TestCase):
    def test_inexact_node_name_fails_without_changing_other_roots(self):
        ctx=context();saved=record();saved['type'][1][1]='OTHER_NODE';install(ctx,envelope(variables={'OTHER':{'type':['INTEGER'],'value':42},'ROUTE':saved}),'CACHE.VR')
        self.assertEqual(load(ctx),6);self.assertNotIn(('CACHE','OTHER'),ctx.variables.bindings);self.assertEqual(raw(ctx).nodes[0].values['VALUE'],7)

    def test_inexact_header_name_is_rejected(self):
        ctx=context();saved=record();saved['type'][2][1]='OTHER_HEADER';install(ctx,envelope(variables={'ROUTE':saved}),'CACHE.VR');self.assertEqual(load(ctx),6)

    def test_whole_missing_path_payload_is_not_an_empty_path(self):
        ctx=context();saved=record();saved['value']={'uninitialized':True};install(ctx,envelope(variables={'ROUTE':saved}),'CACHE.VR');self.assertEqual(load(ctx),6)

    def test_missing_source_root_cannot_be_saved(self):
        ctx=context();ref=ctx.variables.bindings['CACHE','ROUTE'];ref.storage[ref.key]=rt.UNINITIALIZED
        self.assertEqual(save(ctx),6);self.assertEqual(ctx.files.files,{})

    def test_malformed_existing_receiver_is_not_silently_overwritten(self):
        ctx=context();save(ctx);root=raw(ctx);root.nodes[0].values['VALUE']=True;nodes=root.nodes
        self.assertEqual(load(ctx),6);self.assertIs(root.nodes,nodes);self.assertIs(root.nodes[0].values['VALUE'],True)

    def test_missing_existing_receiver_root_is_rejected(self):
        ctx=context();save(ctx);ref=ctx.variables.bindings['CACHE','ROUTE'];ref.storage[ref.key]=rt.UNINITIALIZED;self.assertEqual(load(ctx),6)

    def test_nonfinite_known_source_leaf_rejects_before_file_creation(self):
        node=('STRUCTURE','NODE_T',(('X',('REAL',)),));value=rt.PathValue(('PATH',node,None));value.append();value.nodes[0].values['X']=float('nan');ctx=context(value=value)
        self.assertEqual(save(ctx),6);self.assertEqual(ctx.files.files,{})

    def test_bad_known_payload_field_and_marker_reject(self):
        for bad in (True,{'uninitialized':1},{'unknown_byte':True}):
            ctx=context();saved=record();saved['value']['nodes'][0]['VALUE']=bad;install(ctx,envelope(variables={'ROUTE':saved}),'CACHE.VR')
            with self.subTest(bad=bad):self.assertEqual(load(ctx),6)

    def test_extra_or_missing_node_fields_reject(self):
        for node in ({},{'VALUE':7,'EXTRA':8}):
            ctx=context();saved=record();saved['value']['nodes'][0]=node;install(ctx,envelope(variables={'ROUTE':saved}),'CACHE.VR');self.assertEqual(load(ctx),6)

    def test_headerless_schema_cannot_restore_header_data(self):
        ctx=context(value=rt.PathValue(('PATH',None,None)));saved=record(raw(ctx));saved['value']['data']=42;install(ctx,envelope(variables={'ROUTE':saved}),'CACHE.VR');self.assertEqual(load(ctx),6)

    def test_resource_fields_and_path_arrays_stay_excluded(self):
        for spec in (('ARRAY',1,('PATH',None,None)),('PATH',('STRUCTURE','N',(('F',('FILE',)),)),None)):
            ctx=context();install(ctx,envelope(variables={'ROUTE':{'type':json.loads(json.dumps(spec)),'value':{}}}),'CACHE.VR');self.assertEqual(load(ctx),6)

    def test_file_records_remain_excluded(self):
        ctx=context();install(ctx,envelope(variables={'FD':{'type':['FILE'],'value':{'closed':True}}}),'CACHE.VR');self.assertEqual(load(ctx),6);self.assertNotIn(('CACHE','FD'),ctx.variables.bindings)

    def test_creation_metadata_checks_precede_any_typed_decode(self):
        saved=record();saved['creation']={'group':True,'memory_pool':0}
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('must validate policy first')),self.assertRaises(ValueError):vr.validate(envelope(variables={'ROUTE':saved}))

    def test_schemas_and_leaf_totals_precede_any_typed_decode(self):
        saved=record();saved['value']['nodes']=[{'uninitialized':True}]*32767
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('must bound first')),self.assertRaises(ValueError):vr.validate(envelope(variables={'ROUTE':saved}))

    def test_descriptor_and_header_count_toward_namespace_leaf_limit(self):
        spec=('PATH',NODE,None);value=rt.PathValue(spec);value.nodes=[rt.UNINITIALIZED]*32766
        self.assertEqual(vr.schema(spec,value),32767);value.nodes.append(rt.UNINITIALIZED)
        with self.assertRaises(ValueError):vr.schema(spec,value)

    def test_total_across_path_and_scalar_roots_is_bounded(self):
        saved=record(rt.PathValue(('PATH',NODE,None)));saved['value']['nodes']=[{'uninitialized':True}]*32765
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('must total first')),self.assertRaises(ValueError):vr.validate(envelope(variables={'ROUTE':saved,'A':{'type':['INTEGER'],'value':1},'B':{'type':['INTEGER'],'value':2}}))

    def test_malformed_node_container_is_bounded_before_decode(self):
        for nodes in (None,{},'nodes'):
            saved=record();saved['value']['nodes']=nodes
            with patch('karel2py.storage.decode_typed',side_effect=AssertionError('must check container first')),self.assertRaises(ValueError):vr.validate(envelope(variables={'ROUTE':saved}))

    def test_nested_component_schema_depth_is_bounded(self):
        node=('INTEGER',)
        for i in range(65):node=('STRUCTURE','N'+str(i),(('VALUE',node),))
        with self.assertRaises((ValueError,rt.KarelRuntimeError)):vr.schema(('PATH',node,None),{'nodes':[],'data':None})

    def test_partial_config_turns_still_require_known_range(self):
        node=('STRUCTURE','N',(('CFG',('CONFIG',)),));value=rt.PathValue(('PATH',node,None));value.append();value.nodes[0].values['CFG'].values['CFG_TURN_NO1']=8
        ctx=context(value=value);self.assertEqual(save(ctx),6)


class PathArchiveOwnershipTests(unittest.TestCase):
    def test_same_empty_path_under_two_root_bindings_is_an_overlap(self):
        value=rt.PathValue(('PATH',None,None));ctx=context(value=value);bind(ctx,value,name='OTHER');self.assertEqual(save(ctx),4)

    def test_shared_empty_node_list_between_distinct_paths_is_an_overlap(self):
        value=rt.PathValue(('PATH',None,None));ctx=context(value=value);other=rt.PathValue(value.spec);other.nodes=value.nodes;bind(ctx,other,name='OTHER');self.assertEqual(save(ctx),4)

    def test_sparse_node_field_binding_must_match_root_storage(self):
        ctx=context();field=rt.field_reference(raw(ctx).nodes[0],'VALUE');ctx.variables.bind('CACHE','ROUTE[1].VALUE',field);self.assertEqual(save(ctx),0)
        ctx.variables.bind('CACHE','ROUTE[1].VALUE',rt.Reference(('INTEGER',),{'value':7},'value'));self.assertEqual(save(ctx),4)

    def test_sparse_whole_node_binding_must_match_actual_list_cell(self):
        ctx=context();root=raw(ctx);ctx.variables.bind('CACHE','ROUTE[1]',rt.Reference(NODE,root.nodes,0));self.assertEqual(save(ctx),0)

    def test_status_alias_inside_header_rejects_before_nodes_are_replaced(self):
        ctx=context();save(ctx);root=raw(ctx);root.nodes[0].values['VALUE']=99;nodes=root.nodes
        p,_=compile_program("work(BYNAME('CACHE','ROUTE',e))",prefix=PREFIX,decl='e:INTEGER',context=ctx,routines="ROUTINE work(route:route_t) BEGIN LOAD('CACHE.VR',0,route.count) END work")
        p.run();self.assertEqual(root.data.values['COUNT'],4);self.assertEqual(root.nodes[0].values['VALUE'],99);self.assertIs(root.nodes,nodes)

    def test_connected_header_timer_blocks_clear_without_removing_connection(self):
        ctx=context();p,_=compile_program("work(BYNAME('CACHE','ROUTE',e))",prefix=PREFIX,decl='e,s:INTEGER',context=ctx,cooperative=True,clock_us=lambda:0,routines="ROUTINE work(route:route_t) BEGIN CONNECT TIMER TO route.count CLEAR('CACHE.VR',s) PAUSE END work")
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['S'],4);self.assertEqual(raw(ctx).nodes[0].values['VALUE'],7);self.assertTrue(ctx._timer_claims)
        p.stop();self.assertEqual(ctx._timer_claims,{})

    def test_active_foreign_alias_to_path_blocks_replacement(self):
        ctx=context();save(ctx);namespace={'__name__':'paused_path_owner'}
        exec(translate('PROGRAM OTHER '+PREFIX+' VAR other:route_t BEGIN PAUSE END OTHER',cooperative=True).python_source,namespace)
        p=namespace['Program'](context=ctx);p._state.values['OTHER']=raw(ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(load(ctx),4);p.stop()

    def test_nested_header_joint_shared_with_active_foreign_root_is_protected(self):
        header=('STRUCTURE','H',(('J',('JOINTPOS',2)),));value=rt.PathValue(('PATH',NODE,header));ctx=context(value=value);save(ctx)
        namespace={'__name__':'paused_joint_owner'};exec(translate('PROGRAM OTHER VAR axes:JOINTPOS2 BEGIN PAUSE END OTHER',cooperative=True).python_source,namespace)
        p=namespace['Program'](context=ctx);p._state.values['AXES']=value.data.values['J']
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(load(ctx),4);p.stop()

    def test_indirect_for_counter_guards_still_reject_restore_and_clear(self):
        for operation in ("LOAD('CACHE.VR',0,s)","CLEAR('CACHE.VR',s)","PROG_RESTORE('CACHE.VR',s)"):
            with self.assertRaises(TranslationError):compile_program('FOR n=1 TO 2 DO '+operation+' ENDFOR',decl='n,s:INTEGER')


class PathArchiveBatchTests(unittest.TestCase):
    def test_recursive_backup_clear_restore_covers_parent_and_child_paths(self):
        ctx=context(calls={'CACHE':['CHILD'],'CHILD':[]});bind(ctx,path(values=(42,)),program='CHILD');self.assertEqual(execute(ctx,"PROG_BACKUP('CACHE',PBR_VRTYPE,0,TRUE,s) PROG_CLEAR('CACHE',PBR_VRTYPE,s) PROG_RESTORE('CACHE.VR',s)")['S'],0)
        self.assertEqual((raw(ctx).nodes[0].values['VALUE'],raw(ctx,'CHILD').nodes[0].values['VALUE']),(7,42))

    def test_late_child_type_failure_preserves_parent_path_and_graph(self):
        ctx=context(calls={'CACHE':['CHILD']});bind(ctx,path(values=(42,)),program='CHILD');execute(ctx,"PROG_BACKUP('CACHE',PBR_VRTYPE,0,TRUE,s)");raw(ctx).nodes[0].values['VALUE']=99
        child=json.loads(bytes(ctx.files.files['CHILD.VR']));child['variables']['ROUTE']['type'][1][1]='OTHER';install(ctx,child,'CHILD.VR');before=deepcopy(ctx.variable_archives.calls)
        self.assertEqual(execute(ctx,"PROG_RESTORE('CACHE.VR',s)")['S'],6);self.assertEqual(raw(ctx).nodes[0].values['VALUE'],99);self.assertEqual(ctx.variable_archives.calls,before)

    def test_pbr_pctype_roundtrip_uses_variable_branch(self):
        ctx=context();self.assertEqual(execute(ctx,"PROG_BACKUP('CACHE',PBR_PCTYPE,0,TRUE,s) PROG_CLEAR('CACHE',PBR_PCTYPE,s) PROG_RESTORE('CACHE.VR',s)")['S'],0);self.assertEqual(raw(ctx).nodes[0].values['VALUE'],7)

    def test_wildcard_save_captures_multiple_path_namespaces(self):
        ctx=context();bind(ctx,path(values=(42,)),program='CHILD');self.assertEqual(execute(ctx,"SAVE('*','*.VR',s)")['S'],0)
        self.assertIn('ROUTE',json.loads(bytes(ctx.files.files['CHILD.VR']))['variables']);self.assertIn('CACHE.VR',ctx.files.files)

    def test_readonly_and_device_quota_fail_without_archives(self):
        for options,code in ((dict(capacity=64),5),(dict(capacity=10000,read_only=True),4)):
            ctx=context();ctx.files=rt.DeviceFiles({'FR:':options});self.assertEqual(execute(ctx,"SAVE('CACHE','FR:CACHE.VR',s)")['S'],code);self.assertEqual(ctx.files.files,{})

    def test_flash_save_restore_and_context_replay_keep_logical_paths(self):
        ctx=context();p,_=compile_program("SAVE_DRAM('CACHE',s)",context=ctx);self.assertEqual(p.run()['S'],0);raw(ctx).nodes[0].values['VALUE']=99
        self.assertEqual(ctx.variable_archives.restore_dram(p._state,'CACHE'),0);self.assertEqual(raw(ctx).nodes[0].values['VALUE'],7)
        saved=json.loads(json.dumps(ctx.to_config()));other=rt.ExecutionContext.from_config(saved);self.assertEqual(other.to_config(),saved)

    def test_failed_flash_save_retains_previous_snapshot(self):
        ctx=context();execute(ctx,"SAVE_DRAM('CACHE',s)");before=deepcopy(ctx.variable_archives.flash);raw(ctx).nodes[0].values['VALUE']=True
        self.assertEqual(execute(ctx,"SAVE_DRAM('CACHE',s)")['S'],6);self.assertEqual(ctx.variable_archives.flash,before)

    def test_restored_dynamic_path_keeps_creation_metadata(self):
        ctx=rt.ExecutionContext(variable_archives=rt.VariableArchives(),files=rt.MemoryFiles());execute(ctx,"CREATE_VAR('CACHE','ROUTE','','PATH',0,0,0,0,s,-1) SAVE('CACHE','CACHE.VR',s)")
        fresh=rt.ExecutionContext(variable_archives=rt.VariableArchives(),files=rt.MemoryFiles(ctx.files.snapshot()));self.assertEqual(load(fresh),0)
        self.assertEqual(fresh.variables.metadata['CACHE','ROUTE'],dict(group=0,memory_pool=-1));self.assertEqual(raw(fresh).nodes,[])

    def test_creation_policy_conflict_preserves_existing_path(self):
        ctx=context();saved=record();saved['creation']=dict(group=0,memory_pool=-1);install(ctx,envelope(variables={'ROUTE':saved}),'CACHE.VR');ctx.variables.metadata['CACHE','ROUTE']=dict(group=0,memory_pool=0)
        root=raw(ctx);self.assertEqual(load(ctx),6);self.assertIs(raw(ctx),root)

    def test_mixed_alltype_backup_clear_and_manifest_restore_include_paths(self):
        from tests.test_mixed_archives import context as mixed_context
        ctx=mixed_context();bind(ctx,path(),program='ROOT');self.assertEqual(execute(ctx,"PROG_BACKUP('ROOT',PBR_ALLTYPE,0,TRUE,s) PROG_CLEAR('ROOT',PBR_ALLTYPE,s) PROG_RESTORE('ROOT.TP',s)")['S'],0)
        self.assertEqual(raw(ctx,'ROOT').nodes[0].values['VALUE'],7)

    def test_linked_source_path_is_restored_with_local_status(self):
        ctx=rt.ExecutionContext(variable_archives=rt.VariableArchives(),files=rt.MemoryFiles())
        main='PROGRAM MAIN ROUTINE work FROM LIB BEGIN work END MAIN'
        lib='PROGRAM LIB '+PREFIX+" VAR route:route_t ROUTINE work VAR s:INTEGER BEGIN APPEND_NODE(route,s) route[1].value=42 route.count=1 SAVE('LIB','LIB.VR',s) route[1].value=99 LOAD('LIB.VR',0,s) END work BEGIN END LIB"
        p=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);self.assertEqual(p.run('MAIN')['LIB']['values']['ROUTE']['nodes'][0]['VALUE'],42)


class PathArchiveAdditionalIntegrationTests(unittest.TestCase):
    def test_missing_node_cell_shared_with_another_root_still_overlaps(self):
        value=path();value.nodes[0]=rt.UNINITIALIZED;ctx=context(value=value)
        ctx.variables.bind('CACHE','ALIAS',rt.Reference(NODE,value.nodes,0));self.assertEqual(save(ctx),4)

    def test_flash_restore_retains_root_header_and_detaches_prior_nodes(self):
        ctx=context();p,_=compile_program("SAVE_DRAM('CACHE',s)",context=ctx);p.run();root=raw(ctx);header=root.data;nodes=root.nodes;nodes[0].values['VALUE']=99
        self.assertEqual(ctx.variable_archives.restore_dram(p._state,'CACHE'),0);self.assertIs(raw(ctx),root);self.assertIs(root.data,header);self.assertIsNot(root.nodes,nodes);self.assertEqual(nodes[0].values['VALUE'],99)

    def test_failed_flash_restore_preserves_snapshot_and_receiver(self):
        ctx=context();p,_=compile_program("SAVE_DRAM('CACHE',s)",context=ctx);p.run();before=deepcopy(ctx.variable_archives.flash);root=raw(ctx);root.nodes[0].values['VALUE']=True
        self.assertEqual(ctx.variable_archives.restore_dram(p._state,'CACHE'),6);self.assertEqual(ctx.variable_archives.flash,before);self.assertIs(root.nodes[0].values['VALUE'],True)

    def test_program_initialization_refreshes_from_path_content_only(self):
        ctx=context();ctx.program_attributes=rt.ProgramAttributes({'CACHE':dict(loaded=False,initialized=False)})
        save(ctx);self.assertEqual(load(ctx),0);self.assertTrue(ctx.program_attributes.record('CACHE')['initialized']);self.assertFalse(ctx.program_attributes.record('CACHE')['loaded'])
        execute(ctx,"CLEAR('CACHE.VR',s)");self.assertFalse(ctx.program_attributes.record('CACHE')['initialized'])

    def test_fresh_path_restore_does_not_allocate_a_throwaway_path_root(self):
        ctx=rt.ExecutionContext(variable_archives=rt.VariableArchives());p,_=compile_program('',context=ctx);saved=envelope(variables={'ROUTE':record()});original=rt.initial_value
        def initial(spec):
            if spec[0]=='PATH':raise AssertionError('Fresh PATH root must publish decoded storage directly')
            return original(spec)
        with patch('karel2py.runtime.initial_value',side_effect=initial),rt._numeric_scope('pythonic'):
            prepared=vr.prepare(ctx,p._state,ctx.variable_archives,[saved]);vr.commit(ctx,ctx.variable_archives,prepared)
        self.assertEqual(raw(ctx).nodes[0].values['VALUE'],7)

    def test_dynamic_metadata_total_is_checked_before_any_decode(self):
        header=('STRUCTURE','H',(('DATA',('ARRAY',20000,('INTEGER',))),));saved=record(rt.PathValue(('PATH',NODE,header)));saved['creation']=dict(group=0,memory_pool=0)
        # Snapshot data itself is already over the namespace cap; neither record
        # may allocate during the first schema/policy accounting pass.
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('must account first')),self.assertRaises(ValueError):vr.validate(envelope(variables={'A':saved,'B':deepcopy(saved)}))

    def test_cooperative_pause_between_save_and_load_keeps_completed_save(self):
        ctx=context();p,_=compile_program("SAVE('CACHE','CACHE.VR',s) PAUSE LOAD('CACHE.VR',0,s)",context=ctx,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        root=raw(ctx);root.nodes[0].values['VALUE']=99;self.assertIn('CACHE.VR',ctx.files.files)
        self.assertEqual(p.resume()['S'],0);self.assertEqual(root.nodes[0].values['VALUE'],7)

    def test_source_header_formal_alias_observes_load(self):
        ctx=context();save(ctx);raw(ctx).data.values['COUNT']=99
        p,_=compile_program("work(BYNAME('CACHE','ROUTE',e))",prefix=PREFIX,decl='e,n:INTEGER',context=ctx,routines="ROUTINE work(route:route_t) VAR s:INTEGER BEGIN LOAD('CACHE.VR',0,s) n=route.count END work")
        self.assertEqual(p.run()['N'],2)

    def test_mixed_late_path_type_failure_preserves_tp_and_all_values(self):
        from tests.test_mixed_archives import context as mixed_context
        import hashlib
        ctx=mixed_context();bind(ctx,path(),program='ROOT');execute(ctx,"PROG_BACKUP('ROOT',PBR_ALLTYPE,0,TRUE,s)")
        saved=json.loads(bytes(ctx.files.files['ROOT.VR']));saved['variables']['ROUTE']['type'][1][1]='OTHER';data=ctx.variable_archives.encode(saved);ctx.files.files['ROOT.VR']=bytearray(data)
        manifest=json.loads(bytes(ctx.files.files['ROOT.PB']));next(entry for entry in manifest['entries'] if entry['name']=='ROOT')['files']['VR']=hashlib.sha256(data).hexdigest();ctx.files.files['ROOT.PB']=bytearray((json.dumps(manifest)+'\n').encode())
        before=deepcopy(ctx.teach_programs.to_config());root=raw(ctx,'ROOT');root.nodes[0].values['VALUE']=99
        self.assertEqual(execute(ctx,"PROG_RESTORE('ROOT.TP',s)")['S'],6);self.assertEqual(ctx.teach_programs.to_config(),before);self.assertEqual(root.nodes[0].values['VALUE'],99)

    def test_report_names_path_archive_policy_and_native_boundary(self):
        _,result=compile_program("SAVE_DRAM('CACHE',s)");policy=result.report['path_archive_policy']
        self.assertFalse(policy['controller_validated']);self.assertIn('descriptor',policy['limits']);self.assertIn('detached',policy['identity'])


if __name__=='__main__':unittest.main()
