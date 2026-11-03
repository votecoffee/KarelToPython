"""Authored dynamic collection ARRAY allocation, aliases, quotas and replay."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate_project
from karel2py.dynamic import creation_cost,reserved
from tests.test_collection_arrays import TYPES,PATH
from tests.test_dynamic_narrow import create
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source

DECL='status,entry,n,seq,prior:INTEGER buffer:ARRAY[3]OF INTEGER'
PREFIX=TYPES+' TYPE queue_alias=QUEUE_TYPE row_t=ARRAY[2]OF route_t qrow_t=ARRAY[2]OF QUEUE_TYPE'
FILL='ROUTINE work(q:ARRAY OF QUEUE_TYPE) BEGIN INIT_QUEUE(q[2]) APPEND_QUEUE(9,q[2],buffer,seq,status) END work'
GROW='ROUTINE work(p:ARRAY OF route_t) BEGIN APPEND_NODE(p[2],status) p[2].count=1 p[2][1].amount=17 n=PATH_LEN(p[2]) END work'


def allocation(kind='ARRAY OF QUEUE_TYPE',dims=(2,0,0),**options):return create(kind,dims=dims,**options)

def invoke(path='ITEM',owner='CACHE'):return "work(BYNAME('"+owner+"','"+path+"',entry)) "

def build(body='',**options):return compile_program(body,decl=options.pop('decl',DECL),prefix=options.pop('prefix',PREFIX),**options)

def execute(body='',**options):
    p,r=build(body,**options);v=p.run();return v,p._state.execution,p,r

def ref(ctx,name='ITEM',owner='CACHE'):return ctx.variables.bindings[owner,name]


class DynamicCollectionArrayTests(unittest.TestCase):
    def test_direct_queue_array_allocation(self):
        v,ctx,_,_=execute(allocation());a=ref(ctx).raw();self.assertEqual(v['STATUS'],0);self.assertEqual(a.spec,('ARRAY',2,('QUEUE_TYPE',)));self.assertIsNot(a.values[0],a.values[1])
    def test_direct_path_array_allocation(self):
        v,ctx,_,_=execute(allocation('ARRAY OF PATH'));a=ref(ctx).raw();self.assertEqual(v['STATUS'],0);self.assertEqual(a.spec,('ARRAY',2,('PATH',None,None)));self.assertTrue(all(p.nodes==[] for p in a.values))
    def test_plain_collection_name_with_dimensions(self):
        for name in ('PATH','QUEUE_TYPE'):
            v,ctx,_,_=execute(allocation(name));self.assertEqual(v['STATUS'],0);self.assertEqual(ref(ctx).spec[0],'ARRAY')
    def test_transparent_collection_alias_with_dimensions(self):
        v,ctx,_,_=execute(allocation('route_t'));self.assertEqual(ref(ctx).spec,('ARRAY',2,PATH));self.assertEqual(v['STATUS'],0)
    def test_array_of_transparent_queue_alias(self):
        _,ctx,_,_=execute(allocation('ARRAY OF queue_alias'));self.assertEqual(ref(ctx).spec,('ARRAY',2,('QUEUE_TYPE',)))
    def test_named_array_without_extra_dimensions(self):
        v,ctx,_,_=execute(allocation('qrow_t',(0,0,0)));self.assertEqual(v['STATUS'],0);self.assertEqual(ref(ctx).spec[-1],'QROW_T')
    def test_new_outer_dimensions_preserve_named_components(self):
        _,ctx,_,_=execute(allocation('row_t'));a=ref(ctx).raw();self.assertEqual(rt.array_dimensions(a.spec),(2,2));self.assertEqual(a.values[0].spec[-1],'ROW_T');self.assertIsNot(a.values[0],a.values[1])
    def test_dimensions_remain_outer_to_inner_reversed(self):
        _,ctx,_,_=execute(allocation('QUEUE_TYPE',(2,3,1)));self.assertEqual(rt.array_dimensions(ref(ctx).spec),(1,3,2))
    def test_allocation_retains_group_and_pool_metadata(self):
        _,ctx,_,_=execute(allocation(group=32,pool=-1));self.assertEqual(ctx.variables.metadata['CACHE','ITEM'],{'group':32,'memory_pool':-1});self.assertIsNone(ctx.robot)
    def test_header_allocation_counts_reserved_units(self):
        _,ctx,_,_=execute(allocation('route_t'));self.assertEqual(creation_cost(ref(ctx).spec),4);self.assertEqual(reserved(ctx.variables),4)
    def test_new_queue_and_path_arrays_share_creation_budget(self):
        _,ctx,_,_=execute(allocation()+allocation('route_t',name='PATHS'));self.assertEqual(reserved(ctx.variables),6)
    def test_dynamic_queue_arrays_borrow_into_routines(self):
        v,ctx,_,_=execute(allocation()+invoke(),routines=FILL);self.assertEqual(v['STATUS'],0);self.assertEqual(ref(ctx).raw().values[1].entries,[(1,9)])
    def test_dynamic_path_arrays_borrow_into_routines(self):
        v,ctx,_,_=execute(allocation('route_t')+invoke(),routines=GROW);self.assertEqual(v['N'],1);self.assertEqual(ref(ctx).raw().values[1].nodes[0].values['AMOUNT'],17)
    def test_selected_dynamic_cell_is_borrowed(self):
        routines='ROUTINE work(q:QUEUE_TYPE) BEGIN INIT_QUEUE(q) END work'
        _,ctx,_,_=execute(allocation()+invoke('ITEM[2]'),routines=routines);self.assertTrue(ref(ctx).raw().values[1].initialized)
    def test_named_array_formal_keeps_identity(self):
        routine=FILL.replace('ARRAY OF QUEUE_TYPE','qrow_t')
        _,ctx,_,_=execute(allocation('qrow_t',(0,0,0))+invoke(),routines=routine);self.assertEqual(ref(ctx).spec[-1],'QROW_T')
    def test_foreign_source_type_owner(self):
        main='PROGRAM MAIN '+DECL.replace('status,','VAR status,')+' BEGIN '+allocation('row_t',(0,0,0),type_owner='LIB')+' END MAIN'
        lib='PROGRAM LIB '+PREFIX+' BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate();project.run('MAIN');self.assertEqual(ref(project.context).spec[-1],'ROW_T')
    def test_linked_routine_borrows_created_array(self):
        main=source('MAIN',allocation()+invoke(),decl=DECL,routines='ROUTINE work(q:ARRAY OF QUEUE_TYPE) FROM LIB')
        lib=source('LIB','',decl=DECL,routines=FILL)
        project=translate_project({'main':main,'lib':lib}).instantiate();project.run('MAIN');self.assertEqual(ref(project.context).raw().values[1].entries,[(1,9)])
    def test_root_rename_keeps_live_array_alias(self):
        routine=FILL.replace('INIT_QUEUE(q[2])',"RENAME_VAR('CACHE','ITEM','KEPT',status) INIT_QUEUE(q[2])")
        _,ctx,_,_=execute(allocation()+invoke(),routines=routine);self.assertEqual(ref(ctx,'KEPT').raw().values[1].entries,[(1,9)]);self.assertNotIn(('CACHE','ITEM'),ctx.variables.bindings)
    def test_namespace_rename_keeps_live_array_alias(self):
        routine=FILL.replace('INIT_QUEUE(q[2])',"RENAME_VARS('CACHE','MOVED',status) INIT_QUEUE(q[2])")
        _,ctx,_,_=execute(allocation()+invoke(),routines=routine);self.assertEqual(ref(ctx,owner='MOVED').raw().values[1].entries,[(1,9)]);self.assertIn(('MOVED','ITEM'),ctx.variables.metadata)
    def test_vr_clear_resets_created_collection_array_and_retains_metadata(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(),variable_archives=rt.VariableArchives())
        body=allocation()+invoke()+"SAVE('CACHE','CACHE.VR',status) CLEAR('CACHE.VR',status)"
        v,ctx,_,_=execute(body,routines=FILL,context=ctx);self.assertEqual(v['STATUS'],0);self.assertEqual(ref(ctx).raw().values[1].entries,[]);self.assertFalse(ref(ctx).raw().values[1].initialized)
        self.assertIn(('CACHE','ITEM'),ctx.variables.metadata)

    def test_pause_retains_once_created_cells(self):
        routine=FILL.replace('APPEND_QUEUE(9','PAUSE APPEND_QUEUE(9')
        p,_=build(allocation()+invoke(),routines=routine,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        held=ref(p._state.execution).raw();p.resume();self.assertIs(ref(p._state.execution).raw(),held);self.assertEqual(held.values[1].entries,[(1,9)])


class DynamicCollectionArrayGuardTests(unittest.TestCase):
    def test_dimension_hole_is_rejected_without_root(self):
        v,ctx,_,_=execute(allocation(dims=(0,2,0)));self.assertEqual(v['STATUS'],5);self.assertNotIn(('CACHE','ITEM'),ctx.variables.bindings)
    def test_header_budget_is_checked_before_factory(self):
        p,_=build(allocation('route_t',(20000,0,0)))
        with patch.object(rt.PathValue,'__init__',side_effect=AssertionError('Unexpected collection allocation')) as factory:v=p.run()
        self.assertEqual(v['STATUS'],5);factory.assert_not_called()
    def test_rank_four_named_component_is_rejected(self):
        v,ctx,_,_=execute(allocation('row_t',(2,2,2)));self.assertEqual(v['STATUS'],5);self.assertFalse(ctx.variables.bindings)
    def test_unknown_collection_type_is_not_discovered(self):
        v,ctx,_,_=execute(allocation('ARRAY OF MISSING'));self.assertEqual(v['STATUS'],5);self.assertFalse(ctx.variables.bindings)
    def test_nested_array_of_string_syntax_is_not_a_resource_parser(self):
        v,ctx,_,_=execute(allocation('ARRAY OF ARRAY OF PATH'));self.assertEqual(v['STATUS'],5);self.assertFalse(ctx.variables.bindings)
    def test_new_root_cannot_replace_existing_binding(self):
        v,ctx,_,_=execute(allocation()+allocation('PATH'));self.assertEqual(v['STATUS'],3);self.assertEqual(ref(ctx).spec[2],('QUEUE_TYPE',))
    def test_pool_validation_retains_old_status(self):
        v,ctx,_,_=execute(allocation(pool=1));self.assertEqual(v['STATUS'],2);self.assertFalse(ctx.variables.bindings)
    def test_resource_arrays_do_not_make_embedded_fields_data(self):
        bad=('STRUCTURE','BAD',(('JOBS',('ARRAY',2,('QUEUE_TYPE',))),))
        with self.assertRaises(ValueError):creation_cost(bad)
    def test_maximum_queue_descriptor_allocation_cost(self):self.assertEqual(creation_cost(('ARRAY',32767,('QUEUE_TYPE',))),32767)
    def test_header_limit_cannot_hide_in_named_components(self):
        with self.assertRaises(ValueError):creation_cost(('ARRAY',2,('ARRAY',10000,PATH,'ROW_T')))


class DynamicCollectionArrayRestoreTests(unittest.TestCase):
    def test_creation_tagged_queue_array_roundtrip(self):
        _,ctx,_,_=execute(allocation()+invoke(),routines=FILL);saved=json.loads(json.dumps(ctx.to_config(),allow_nan=False));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_creation_tagged_path_array_roundtrip(self):
        _,ctx,_,_=execute(allocation('route_t')+invoke(),routines=GROW);saved=json.loads(json.dumps(ctx.to_config(),allow_nan=False));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_restored_created_queues_use_fresh_objects_without_buffers(self):
        _,ctx,_,_=execute(allocation()+invoke(),routines=FILL);restored=rt.ExecutionContext.from_config(ctx.to_config())
        self.assertIsNot(ref(restored).raw(),ref(ctx).raw());self.assertTrue(all(q.buffer is None for q in ref(restored).raw().values))
    def test_restored_created_queue_can_bind_supplied_buffer(self):
        _,ctx,_,_=execute(allocation()+invoke(),routines=FILL);restored=rt.ExecutionContext.from_config(ctx.to_config())
        routine='ROUTINE work(q:ARRAY OF QUEUE_TYPE) BEGIN GET_QUEUE(q[2],buffer,n,seq,status) END work'
        v,_,_,_=execute(invoke(),context=restored,routines=routine);self.assertEqual(v['N'],9)
    def test_restore_validates_combined_creation_quota_before_array_factory(self):
        row=lambda name:dict(program='CACHE',path=name,type=['ARRAY',20000,['QUEUE_TYPE']],value=[dict(initialized=False,sequence=0,entries=[])]*20000,creation={'group':0,'memory_pool':0})
        # A small valid first row consumes the shared reservation; the next oversized
        # reservation must reject without creating that second root.
        payload={'variables':[dict(program='CACHE',path='FIRST',type=['ARRAY',20000,['INTEGER']],value=[0]*20000,creation={'group':0,'memory_pool':0}),row('SECOND')]}
        seen=[];original=rt.Array.__init__
        def track(instance,spec):seen.append(spec);original(instance,spec)
        with patch.object(rt.Array,'__init__',track),self.assertRaises(ValueError):rt.ExecutionContext.from_config(payload)
        self.assertTrue(seen);self.assertFalse(any(rt.collection_array_type(spec) for spec in seen))
    def test_restore_checks_invalid_creation_metadata(self):
        _,ctx,_,_=execute(allocation());saved=ctx.to_config();row=next(r for r in saved['variables'] if r['program']=='CACHE');row['creation']['group']=True
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(saved)
    def test_restore_rejects_closed_file_marker_as_collection_data(self):
        _,ctx,_,_=execute(allocation());saved=ctx.to_config();row=next(r for r in saved['variables'] if r['program']=='CACHE');row['value']={'closed':True}
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(saved)


class DynamicCollectionArrayCheckpointTests(unittest.TestCase):
    def inject(self,action):
        p,_=build('status=77 '+allocation());original=p._state.tick;fired=[]
        def tick(line=None):
            original(line)
            if not fired and any(r['operation']=='CREATE_VAR' for r in p._state.service_requests):fired.append(1);action(p)
        return p,patch.object(p._state,'tick',side_effect=tick)
    def test_collision_after_checkpoint_retains_callback_effect(self):
        p,guard=self.inject(lambda p:p._state.execution.variables.define('CACHE','ITEM',('INTEGER',),7))
        with guard:self.assertEqual(p.run()['STATUS'],3)
        self.assertEqual(ref(p._state.execution).raw(),7)
    def test_quota_after_checkpoint_prevents_resource_array_allocation(self):
        def fill(p):
            store=p._state.execution.variables;store.define('CACHE','DATA',('ARRAY',32766,('INTEGER',)));store.metadata['CACHE','DATA']=dict(group=0,memory_pool=0)
        p,guard=self.inject(fill)
        with guard:self.assertEqual(p.run()['STATUS'],6)
        self.assertNotIn(('CACHE','ITEM'),p._state.execution.variables.bindings)
    def test_replaced_variable_bank_fails_before_publication(self):
        p,guard=self.inject(lambda p:setattr(p._state.execution,'variables',rt.VariableStore()))
        with guard,self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['STATUS'],77)
    def test_terminal_abort_does_not_publish_array(self):
        def abort(p):
            try:p._state.abort(7)
            except rt.KarelAbort:pass
        p,guard=self.inject(abort)
        with guard,self.assertRaises(rt.KarelAbort):p.run()
        self.assertNotIn(('CACHE','ITEM'),p._state.execution.variables.bindings)
    def test_stopped_owner_does_not_publish_array(self):
        p,guard=self.inject(lambda p:setattr(p._state,'task_state','stopped'))
        with guard,self.assertRaises(rt.KarelStop):p.run()
        self.assertNotIn(('CACHE','ITEM'),p._state.execution.variables.bindings)


if __name__=='__main__':unittest.main()
