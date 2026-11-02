"""Authored dynamic FILE ARRAY allocation, live aliases and task lifetimes."""
import json
import struct
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py.dynamic import creation_cost,concrete_type,reserved
from tests.test_extended_services import compile_program
from tests.test_dynamic_narrow import create
from tests.test_file_cancellation import serial
from tests.test_project_scheduler import source

DECL='status,entry,n,m,prior:INTEGER flag:BOOLEAN'
TYPES='TYPE fd_t=FILE row_t=ARRAY[2]OF FILE'
WRITE="ROUTINE work(a:ARRAY OF FILE) BEGIN OPEN FILE a[2]('WO','out') WRITE a[2](17) CLOSE FILE a[2] n=17 END work"


def build(body='',**options):return compile_program(body,decl=options.pop('decl',DECL),**options)
def run(body='',**options):
    p,r=build(body,**options);v=p.run();return v,p._state.execution,p,r

def ref(ctx,name='ITEM',owner='CACHE'):return ctx.variables.bindings[owner,name]
def invoke(path='ITEM',owner='CACHE'):return "work(BYNAME('"+owner+"','"+path+"',entry)) "
def allocation(kind='ARRAY OF FILE',dims=(2,0,0),**options):return create(kind,dims=dims,**options)


class DynamicFileArrayCreationTests(unittest.TestCase):
    def test_array_of_file_without_backend(self):
        v,ctx,_,_=run(allocation());a=ref(ctx).raw();self.assertEqual((v['STATUS'],ref(ctx).spec),(0,('ARRAY',2,('FILE',))));self.assertIsNot(a.values[0],a.values[1]);self.assertTrue(all(h.owner is None for h in a.values));self.assertIsNone(ctx.files)
    def test_file_with_dimensions_creates_array(self):self.assertEqual(ref(run(allocation('FILE'))[1]).spec,('ARRAY',2,('FILE',)))
    def test_file_alias_with_dimensions(self):self.assertEqual(ref(run(allocation('fd_t'),prefix=TYPES)[1]).spec,('ARRAY',2,('FILE',)))
    def test_array_of_transparent_file_alias(self):self.assertEqual(ref(run(allocation('ARRAY OF fd_t'),prefix=TYPES)[1]).spec,('ARRAY',2,('FILE',)))
    def test_named_array_without_extra_dimensions(self):self.assertEqual(ref(run(allocation('row_t',(0,0,0)),prefix=TYPES)[1]).spec,('ARRAY',2,('FILE',),'ROW_T'))
    def test_new_outer_dimensions_keep_named_row_identity(self):
        a=ref(run(allocation('row_t'),prefix=TYPES)[1]).raw();self.assertEqual(rt.array_dimensions(a.spec),(2,2));self.assertEqual(a.values[0].spec[-1],'ROW_T');self.assertIsNot(a.values[0],a.values[1])
    def test_alias_chain_preserves_named_component(self):
        a=ref(run(allocation('alias_t'),prefix=TYPES+' alias_t=row_t')[1]).raw();self.assertEqual(a.spec[2][-1],'ROW_T')
    def test_dimensions_are_inner_to_outer(self):self.assertEqual(rt.array_dimensions(ref(run(allocation(dims=(2,3,4)))[1]).spec),(4,3,2))
    def test_type_text_is_trimmed_and_casefolded(self):self.assertEqual(ref(run(allocation(' array  of  file '))[1]).spec,('ARRAY',2,('FILE',)))
    def test_blank_namespace_defaults_to_program(self):
        v,ctx,_,_=run(allocation(owner=''));self.assertEqual(v['STATUS'],0);self.assertIn(('T','ITEM'),ctx.variables.metadata)
    def test_group_and_pool_stay_metadata(self):
        _,ctx,_,_=run(allocation(group=32,pool=-1));self.assertEqual(ctx.variables.metadata['CACHE','ITEM'],dict(group=32,memory_pool=-1))
    def test_foreign_type_owner_supplies_named_array(self):
        project=translate_project({'main':source('MAIN',allocation('row_t',type_owner='LIB'),decl='status:INTEGER'),'lib':'PROGRAM LIB TYPE row_t=ARRAY[2]OF FILE BEGIN END LIB'}).instantiate();project.run('MAIN');self.assertEqual(ref(project.context).spec[2][-1],'ROW_T')
    def test_independent_created_roots(self):
        _,ctx,_,_=run(allocation()+allocation(name='OTHER'));self.assertIsNot(ref(ctx).raw().values[0],ref(ctx,'OTHER').raw().values[0])
    def test_every_descriptor_counts_toward_budget(self):
        _,ctx,_,_=run(allocation(dims=(2,3,0)));self.assertEqual(reserved(ctx.variables),6);self.assertEqual(creation_cost(ref(ctx).spec),6)
    def test_combined_budget_rejects_before_allocation(self):
        v,ctx,_,_=run(create('INTEGER',name='DATA',dims=(32766,0,0))+allocation());self.assertEqual(v['STATUS'],6);self.assertNotIn(('CACHE','ITEM'),ctx.variables.bindings)
    def test_exact_budget_boundary_accepts_all_descriptors(self):
        v,ctx,_,_=run(create('INTEGER',name='DATA',dims=(32765,0,0))+allocation());self.assertEqual(v['STATUS'],0);self.assertEqual(reserved(ctx.variables),32767)
    def test_overlarge_or_rank_four_schema_never_allocates(self):
        for kind,dims,prefix in [('FILE',(32767,2,0),''),('row_t',(2,2,2),TYPES)]:
            v,ctx,_,_=run(allocation(kind,dims),prefix=prefix);self.assertEqual((v['STATUS'],ctx.variables.bindings),(5,{}))
    def test_sparse_dimensions_remain_invalid(self):
        v,ctx,_,_=run(allocation(dims=(0,2,0)));self.assertEqual((v['STATUS'],ctx.variables.bindings),(5,{}))
    def test_array_of_file_requires_dimensions(self):
        v,ctx,_,_=run(allocation(dims=(0,0,0)));self.assertEqual((v['STATUS'],ctx.variables.bindings),(5,{}))
    def test_strict_runtime_does_not_gain_named_file_array_creation(self):
        p,_=build(prefix=TYPES)
        with rt._numeric_scope('strict'):
            for kind in ('FILE','ARRAY OF FILE','row_t'):self.assertIsNone(concrete_type(p._state.execution,p._state,'T',kind,0,(0,0,0),1))
    def test_collision_preserves_existing_array_identity(self):
        _,ctx,p,_=run(allocation());a=ref(ctx).raw();p,_=build(allocation(),context=ctx);self.assertEqual(p.run()['STATUS'],3);self.assertIs(ref(ctx).raw(),a)
    def test_declared_array_root_cannot_be_recreated(self):
        v,ctx,_,_=run(allocation(owner='',name='LOCAL'),decl=DECL+' local:ARRAY[2]OF FILE');self.assertEqual((v['STATUS'],ctx.variables.bindings),(3,{}))
    def test_report_describes_closed_allocation_intent(self):
        _,_,_,r=run(allocation());self.assertFalse(r.report['dynamic_file_array_policy']['controller_validated']);self.assertIn('32767',r.report['dynamic_file_array_policy']['allocation'])


class DynamicFileArrayOperationsTests(unittest.TestCase):
    def test_generic_formal_writes_original_descriptor(self):
        v,ctx,_,_=run(allocation()+invoke(),routines=WRITE,context=rt.ExecutionContext(files=rt.MemoryFiles()));self.assertEqual((v['N'],ref(ctx).raw().values[1].position),(17,3));self.assertEqual(ctx.files.snapshot()['out'],b' 17')
    def test_scalar_file_byname_selects_one_array_cell(self):
        routine="ROUTINE work(h:FILE) BEGIN OPEN FILE h('WO','out') WRITE h(19) CLOSE FILE h END work"
        _,ctx,_,_=run(allocation()+invoke('ITEM[1]'),routines=routine,context=rt.ExecutionContext(files=rt.MemoryFiles()));self.assertEqual(ref(ctx).raw().values[0].position,3);self.assertIsNone(ref(ctx).raw().values[1].name)
    def test_named_component_row_can_be_borrowed(self):
        _,ctx,_,_=run(allocation('row_t')+invoke('ITEM[2]'),prefix=TYPES,routines=WRITE,context=rt.ExecutionContext(files=rt.MemoryFiles()));self.assertEqual(ref(ctx).raw().values[1].values[1].position,3)
    def test_binary_roundtrip_through_array_formal(self):
        routine="ROUTINE work(a:ARRAY OF FILE) BEGIN OPEN FILE a[1]('WB','out') WRITE a[1](17,-9) CLOSE FILE a[1] OPEN FILE a[2]('RB','out') READ a[2](n,m) CLOSE FILE a[2] END work"
        v,ctx,_,_=run(allocation()+invoke(),routines=routine,context=rt.ExecutionContext(files=rt.MemoryFiles()));self.assertEqual((v['N'],v['M']),(17,-9));self.assertEqual(ctx.files.snapshot()['out'],struct.pack('<ii',17,-9))
    def test_open_root_rename_retains_array_and_file(self):
        routine="ROUTINE work(a:ARRAY OF FILE) BEGIN OPEN FILE a[2]('WO','out') RENAME_VAR('CACHE','ITEM','KEPT',status) WRITE a[2](17) CLOSE FILE a[2] END work"
        _,ctx,_,_=run(allocation()+invoke(),routines=routine,context=rt.ExecutionContext(files=rt.MemoryFiles()));self.assertEqual(ref(ctx,'KEPT').raw().values[1].position,3);self.assertNotIn(('CACHE','ITEM'),ctx.variables.bindings)
    def test_namespace_rename_retains_array_and_metadata(self):
        routine="ROUTINE work(a:ARRAY OF FILE) BEGIN OPEN FILE a[2]('WO','out') RENAME_VARS('CACHE','MOVED',status) WRITE a[2](17) CLOSE FILE a[2] END work"
        _,ctx,_,_=run(allocation()+invoke(),routines=routine,context=rt.ExecutionContext(files=rt.MemoryFiles()));self.assertEqual(ref(ctx,owner='MOVED').raw().values[1].position,3);self.assertIn(('MOVED','ITEM'),ctx.variables.metadata)
    def test_linked_routine_borrows_created_array(self):
        files={'main':source('MAIN',allocation()+invoke(),decl=DECL,routines='ROUTINE work(a:ARRAY OF FILE) FROM LIB'),'lib':source('LIB','',routines=WRITE.replace(' n=17',''))}
        project=translate_project(files).instantiate(context=rt.ExecutionContext(files=rt.MemoryFiles()));project.run('MAIN');self.assertEqual(ref(project.context).raw().values[1].position,3)
    def test_named_array_formal_retains_exact_created_identity(self):
        routine=WRITE.replace('ARRAY OF FILE','row_t')
        _,ctx,_,_=run(allocation('row_t',(0,0,0))+invoke(),prefix=TYPES,routines=routine,context=rt.ExecutionContext(files=rt.MemoryFiles()));self.assertEqual(ref(ctx).spec[-1],'ROW_T');self.assertEqual(ref(ctx).raw().values[1].position,3)
    def test_inspection_reports_file_leaf_and_array_dimensions(self):
        body=allocation()+"VAR_INFO('CACHE','ITEM',flag,label,kind,dims,n,status)"
        v,_,_,_=run(body,decl=DECL+' label:STRING[12] kind:INTEGER dims:ARRAY[3]OF INTEGER');self.assertEqual((v['FLAG'],v['LABEL'],v['KIND'],v['DIMS']),(True,'FILE',29,[2,0,0]))
    def test_inspection_validates_open_and_closed_cells(self):
        routine="ROUTINE work(a:ARRAY OF FILE) BEGIN OPEN FILE a[1]('WO','one') OPEN FILE a[2]('WO','two') VAR_INFO('CACHE','ITEM',flag,label,kind,dims,n,status) CLOSE FILE a[1] CLOSE FILE a[2] END work"
        v,_,_,_=run(allocation()+invoke(),routines=routine,decl=DECL+' label:STRING[12] kind:INTEGER dims:ARRAY[3]OF INTEGER',context=rt.ExecutionContext(files=rt.MemoryFiles()));self.assertIs(v['FLAG'],False)
    def test_listing_file_filter_includes_array_root(self):
        body=allocation()+"VAR_LIST('CACHE','*',29,0,2,names,n,status)"
        v,_,_,_=run(body,decl=DECL+' names:ARRAY[2]OF STRING[36]');self.assertEqual((v['N'],v['NAMES']),(1,['ITEM','']))
    def test_vr_archive_excludes_created_descriptor_array(self):
        body=allocation()+"SAVE('CACHE','CACHE.VR',status)"
        v,ctx,_,_=run(body,context=rt.ExecutionContext(files=rt.MemoryFiles(),variable_archives=rt.VariableArchives()));self.assertEqual(v['STATUS'],0);r=json.loads(ctx.files.snapshot()['CACHE.VR']);self.assertEqual((r['variables'],r['excluded']),({},['ITEM']))
    def test_vr_clear_leaves_descriptor_array_allocation(self):
        body=allocation()+"SAVE('CACHE','CACHE.VR',status) CLEAR('CACHE.VR',status)"
        v,ctx,_,_=run(body,context=rt.ExecutionContext(files=rt.MemoryFiles(),variable_archives=rt.VariableArchives()));self.assertEqual(v['STATUS'],0);self.assertEqual(ref(ctx).spec,('ARRAY',2,('FILE',)))
    def test_missing_backend_does_not_discover_one(self):
        p,_=build(allocation()+invoke(),routines=WRITE)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIsNone(ref(p._state.execution).raw().values[1].owner)


class DynamicFileArrayCheckpointTests(unittest.TestCase):
    def inject(self,action):
        p,_=build('status=77 '+allocation());original=p._state.tick;fired=[]
        def tick(line=None):
            original(line)
            if not fired and any(r['operation']=='CREATE_VAR' for r in p._state.service_requests):fired.append(1);action(p)
        return p,patch.object(p._state,'tick',side_effect=tick)
    def test_collision_after_checkpoint_retains_prior_effect(self):
        p,guard=self.inject(lambda p:p._state.execution.variables.define('CACHE','ITEM',('INTEGER',),7))
        with guard:self.assertEqual(p.run()['STATUS'],3)
        self.assertEqual(ref(p._state.execution).raw(),7)
    def test_quota_after_checkpoint_prevents_array_allocation(self):
        def fill(p):
            store=p._state.execution.variables;store.define('CACHE','DATA',('ARRAY',32766,('INTEGER',)));store.metadata['CACHE','DATA']=dict(group=0,memory_pool=0)
        p,guard=self.inject(fill)
        with guard:self.assertEqual(p.run()['STATUS'],6)
        self.assertNotIn(('CACHE','ITEM'),p._state.execution.variables.bindings)
    def test_replaced_variable_bank_fails_before_publication(self):
        p,guard=self.inject(lambda p:setattr(p._state.execution,'variables',rt.VariableStore()))
        with guard,self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['STATUS'],77);self.assertFalse(p._state.execution.variables.bindings)
    def test_terminal_abort_does_not_publish_descriptors(self):
        def abort(p):
            try:p._state.abort(7)
            except rt.KarelAbort:pass
        p,guard=self.inject(abort)
        with guard,self.assertRaises(rt.KarelAbort):p.run()
        self.assertFalse(p._state.execution.variables.bindings);self.assertEqual(p.snapshot()['STATUS'],77)


class DynamicFileArrayWaitingTests(unittest.TestCase):
    def pending(self):
        bank,ctx=serial(b'17 ')
        routine="ROUTINE work(a:ARRAY OF FILE) BEGIN OPEN FILE a[2]('RO','P2:') n=77 READ a[2](n,CR) status=IO_STATUS(a[2]) CLOSE FILE a[2] END work"
        project=translate_project({'main':source('MAIN',allocation()+invoke(),decl=DECL,routines=routine)}).instantiate(context=ctx);p=project.programs['MAIN'];project.scheduler.start('MAIN')
        for _ in range(100):
            project.scheduler.step();value=ctx.variables.bindings.get(('CACHE','ITEM'))
            if value is not None and value.raw().values[1]._read_operation is not None:return project,p,ctx,bank,value.raw().values[1]
        raise AssertionError('Created FILE ARRAY read did not wait')
    def test_cancel_preserves_prefix_and_allocation_intent_after_close(self):
        project,p,ctx,bank,h=self.pending();rt.cancel_file(p._state,h);project.scheduler.run();self.assertEqual((p.snapshot()['N'],p.snapshot()['STATUS']),(77,6));self.assertEqual(bank.snapshot()[2]['input'],b'17 ');self.assertEqual(next(row for row in ctx.to_config()['variables'] if row['program']=='CACHE')['value'],{'closed':True})
    def test_pause_resume_retains_original_array_descriptor(self):
        project,p,ctx,bank,h=self.pending();p.pause()
        for _ in range(100):
            project.scheduler.step()
            if p.task_state=='paused':break
        self.assertEqual(p.task_state,'paused');self.assertIs(ref(ctx).raw().values[1],h);bank.feed(2,b'\n');project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(p.snapshot()['N'],17)
    def test_stop_unwinds_read_but_requires_close_before_save(self):
        project,p,ctx,bank,h=self.pending();project.scheduler.stop('MAIN');self.assertIsNone(h._read_operation)
        with self.assertRaises(ValueError):ctx.to_config()
        bank.close(h);self.assertEqual(next(r for r in ctx.to_config()['variables'] if r['program']=='CACHE')['value'],{'closed':True})
    def test_pending_rename_retains_captured_file_and_schema(self):
        project,p,ctx,bank,h=self.pending();run("RENAME_VAR('CACHE','ITEM','KEPT',status)",context=ctx);self.assertIs(ref(ctx,'KEPT').raw().values[1],h);bank.feed(2,b'\n');project.scheduler.run();self.assertEqual(p.snapshot()['N'],17)
