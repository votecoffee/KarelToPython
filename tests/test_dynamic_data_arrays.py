"""Authored dynamic typed ARRAY layouts, aliases, quotas and portable lifetimes."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py.dynamic import concrete_type,creation_cost,reserved
from tests.test_extended_services import compile_program
from tests.test_dynamic_narrow import create
from tests.test_project_scheduler import source

U={'uninitialized':True}
B={'unknown_byte':True}
TYPES='TYPE row_t=ARRAY[3]OF INTEGER plane_t=ARRAY[2]OF row_t'
DECL='entry,status,n,prior,calls:INTEGER flag:BOOLEAN row:ARRAY[3]OF INTEGER'
META={'group':0,'memory_pool':0}


def program(body='',*,kind='ROW_T',dims=(2,0,0),prefix=TYPES,decl=DECL,routines='',labelled=False,**options):
    return compile_program(('unused:: ' if labelled else '')+create(kind,dims=dims)+body,decl=decl,prefix=prefix,routines=routines,**options)

def run(body='',**options):
    p,r=program(body,**options);v=p.run();return v,p._state.execution,p,r

def ref(context):return context.variables.bindings['CACHE','ITEM']

def alias(routine='edit'):return routine+"(BYNAME('CACHE','ITEM',entry)) "


class DynamicArrayCreationTests(unittest.TestCase):
    def test_array_of_data_scalars(self):
        for kind in ('INTEGER','REAL','BOOLEAN','BYTE','SHORT','VECTOR','CONFIG'):
            with self.subTest(kind=kind):
                v,ctx,_,_=run(kind='ARRAY OF '+kind);self.assertEqual((v['STATUS'],ref(ctx).spec),(0,('ARRAY',2,(kind,))))
    def test_array_of_bounded_string(self):
        v,ctx,_,_=run(kind='ARRAY OF STRING[4]');self.assertEqual((v['STATUS'],ref(ctx).spec),(0,('ARRAY',2,('STRING',4))))
    def test_array_of_default_string_capacity(self):self.assertEqual(ref(run(kind='ARRAY OF STRING')[1]).spec[2],('STRING',12))
    def test_new_outer_dimensions_preserve_named_row(self):
        v,ctx,_,_=run();self.assertEqual((v['STATUS'],ref(ctx).spec),(0,('ARRAY',2,('ARRAY',3,rt.INTEGER,'ROW_T'))))
    def test_array_of_named_row_type(self):self.assertEqual(ref(run(kind='ARRAY OF ROW_T')[1]).spec,ref(run()[1]).spec)
    def test_two_new_outer_dimensions_keep_inner_to_outer_order(self):
        v,ctx,_,_=run(dims=(2,4,0));self.assertEqual((v['STATUS'],rt.array_dimensions(ref(ctx).spec)),(0,(4,2,3)))
    def test_named_flat_matrix_gains_one_outer_dimension(self):
        v,ctx,_,_=run(kind='MATRIX_T',prefix='TYPE matrix_t=ARRAY[2,3]OF INTEGER');self.assertEqual((v['STATUS'],rt.array_dimensions(ref(ctx).spec)),(0,(2,2,3)))
    def test_foreign_attached_array_type_uses_supplied_owner(self):
        p=translate_project({'lib':'PROGRAM LIB TYPE row_t=ARRAY[4]OF INTEGER BEGIN END LIB','main':source('MAIN',create('ARRAY OF ROW_T',type_owner='LIB',dims=(2,0,0)),decl='status:INTEGER')}).instantiate();p.run('MAIN');self.assertEqual(rt.array_dimensions(ref(p.context).spec),(2,4))


class DynamicArrayDataTests(unittest.TestCase):
    def test_each_named_child_owns_distinct_storage(self):
        _,ctx,_,_=run();a=ref(ctx).raw();self.assertIsNot(a.values[0],a.values[1]);a.set((1,1),7);self.assertEqual(a.snapshot(),[[7,U,U],[U,U,U]])
    def test_named_children_keep_their_identity(self):
        _,ctx,_,_=run();self.assertTrue(all(child.spec[3]=='ROW_T' for child in ref(ctx).raw().values))
    def test_alias_chain_preserves_resolved_array_identity(self):
        _,ctx,_,_=run(kind='ARRAY OF ALIAS_T',prefix=TYPES+' alias_t=row_t');self.assertEqual(ref(ctx).spec[2][3],'ROW_T')
    def test_byte_array_defaults_remain_unknown(self):
        _,ctx,_,_=run(kind='ARRAY OF BYTE');self.assertEqual(ref(ctx).raw().snapshot(),[B,B])
    def test_short_array_defaults_remain_missing(self):
        _,ctx,_,_=run(kind='ARRAY OF SHORT');self.assertEqual(ref(ctx).raw().snapshot(),[U,U])
    def test_string_array_leaf_truncation_uses_declared_capacity(self):
        v,ctx,_,_=run("SET_VAR(entry,'CACHE','ITEM[1]','abcdef',status)",kind='ARRAY OF STRING[4]');self.assertEqual((v['STATUS'],ref(ctx).raw().snapshot()),(0,['abcd',U]))
    def test_record_arrays_retain_nested_array_fields(self):
        types='TYPE item_t=STRUCTURE values:ARRAY[2]OF INTEGER text:STRING[3] ENDSTRUCTURE'
        _,ctx,_,_=run("SET_VAR(entry,'CACHE','ITEM[1].VALUES[2]',7,status)",kind='ARRAY OF ITEM_T',prefix=types);self.assertEqual(ref(ctx).raw().snapshot()[0],{'VALUES':[U,7],'TEXT':U})
    def test_direct_positional_array_group_policy(self):
        for kind in ('JOINTPOS2','POSITION','XYZWPR','XYZWPREXT'):
            p,_=compile_program(create('ARRAY OF '+kind,dims=(2,0,0),group=1),decl=DECL);self.assertEqual(p.run()['STATUS'],0);self.assertEqual(ref(p._state.execution).spec[2],rt.joint_spec(kind) if kind=='JOINTPOS2' else (kind,))


class DynamicArrayOperationTests(unittest.TestCase):
    def test_byname_borrows_named_children(self):
        routines='ROUTINE edit(p:ARRAY OF row_t) BEGIN p[2,3]=7 n=p[2,3] END edit'
        v,ctx,_,_=run(alias(),routines=routines);self.assertEqual((v['N'],ref(ctx).raw().snapshot()[1][2]),(7,7))
    def test_named_matrix_formal_remains_exact(self):
        v,ctx,_,_=run(alias(),kind='PLANE_T',dims=(0,0,0),routines='ROUTINE edit(p:plane_t) BEGIN p[2,3]=7 n=p[2,3] END edit');self.assertEqual((v['N'],ref(ctx).spec[3]),(7,'PLANE_T'))
    def test_flat_get_set_transfers_use_existing_layout_rules(self):
        v,ctx,_,_=run("row[1]=7 row[2]=9 row[3]=11 SET_VAR(entry,'CACHE','ITEM[2]',row,status) GET_VAR(entry,'CACHE','ITEM[2]',row,status)");self.assertEqual((v['ROW'],ref(ctx).raw().snapshot()[1]),([7,9,11],[7,9,11]))
    def test_prefix_source_and_get_output_work_on_created_storage(self):
        routines="ROUTINE edit(p:ARRAY OF row_t) BEGIN p[1,1]=7 p[1,2]=9 p[1,3]=11 GET_VAR(entry,'CACHE','ITEM[1]',p[2],status) END edit"
        v,ctx,_,_=run(alias(),routines=routines);self.assertEqual((v['STATUS'],ref(ctx).raw().snapshot()),(0,[[7,9,11],[7,9,11]]))
    def test_aggregate_read_populates_created_named_layout(self):
        _,ctx,_,_=run(alias(),routines='ROUTINE edit(p:ARRAY OF row_t) BEGIN READ(p) END edit',read=lambda request:[1,2,3,4,5,6]);self.assertEqual(ref(ctx).raw().snapshot(),[[1,2,3],[4,5,6]])
    def test_aggregate_write_uses_created_typed_data(self):
        _,_,p,_=run(alias(),routines='ROUTINE edit(p:ARRAY OF row_t) BEGIN READ(p) WRITE(p::2) END edit',read=lambda request:[1,2,3,4,5,6]);self.assertEqual([row['text'] for row in p.write_requests],[' 1 2 3 4 5 6'])
    def test_variable_info_reports_combined_logical_shape(self):
        v,_,_,_=run("VAR_INFO('CACHE','ITEM',flag,label,code,dims,length,status)",decl=DECL+' label:STRING[32] code,length:INTEGER dims:ARRAY[3]OF INTEGER');self.assertEqual((v['STATUS'],v['DIMS']),(0,[2,3,0]))
    def test_complete_chained_source_access_borrows_created_cells(self):
        v,ctx,_,_=run(alias(),routines='ROUTINE edit(p:ARRAY OF row_t) BEGIN p[2][3]=7 n=p[2,3] END edit');self.assertEqual((v['N'],ref(ctx).raw().snapshot()[1][2]),(7,7))


class DynamicArrayLifetimeTests(unittest.TestCase):
    def test_alias_survives_root_rename(self):
        routines="ROUTINE edit(p:ARRAY OF row_t) BEGIN RENAME_VAR('CACHE','ITEM','RENAMED',status) p[2,3]=7 END edit"
        v,ctx,_,_=run(alias(),routines=routines);self.assertEqual((v['STATUS'],ctx.variables.bindings['CACHE','RENAMED'].raw().snapshot()[1][2]),(0,7));self.assertNotIn(('CACHE','ITEM'),ctx.variables.bindings)
    def test_alias_survives_namespace_rename(self):
        routines="ROUTINE edit(p:ARRAY OF row_t) BEGIN RENAME_VARS('CACHE','SAVED',status) p[2,3]=7 END edit"
        _,ctx,_,_=run(alias(),routines=routines);self.assertEqual(ctx.variables.bindings['SAVED','ITEM'].raw().snapshot()[1][2],7)
    def test_pause_retains_borrowed_created_array(self):
        p,_=program(alias(),routines='ROUTINE edit(p:ARRAY OF row_t) BEGIN p[1,1]=7 PAUSE p[2,3]=9 END edit',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        root=ref(p._state.execution).raw();p.resume();self.assertIs(root,ref(p._state.execution).raw());self.assertEqual(root.snapshot(),[[7,U,U],[U,U,9]])
    def test_error_retains_completed_data_edits(self):
        p,_=program(alias(),routines='ROUTINE edit(p:ARRAY OF row_t) BEGIN p[1,1]=7 n=1 DIV 0 END edit')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ref(p._state.execution).raw().snapshot()[0][0],7);self.assertEqual(p._state.local_frames,[])
    def test_abort_retains_created_root_and_prior_edits(self):
        p,_=program(alias(),routines='ROUTINE edit(p:ARRAY OF row_t) BEGIN p[1,1]=7 ABORT END edit')
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(ref(p._state.execution).raw().snapshot()[0][0],7)
    def test_checkpoint_collision_preserves_competing_root(self):
        p,_=program();ctx=p._state.execution;original=p._state.tick;fired=[]
        def tick(line=None):
            if not fired and any(r['operation']=='CREATE_VAR' for r in p.service_requests):fired.append(1);ctx.variables.define('CACHE','ITEM',rt.INTEGER,99)
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick):v=p.run()
        self.assertEqual((v['STATUS'],ref(ctx).raw()),(3,99));self.assertEqual(ctx.variables.metadata,{})
    def test_checkpoint_rechecks_total_reserved_units(self):
        p,_=program();ctx=p._state.execution;original=p._state.tick;fired=[]
        def tick(line=None):
            if not fired and any(r['operation']=='CREATE_VAR' for r in p.service_requests):
                fired.append(1);ctx.variables.define('SIDE','DATA',('ARRAY',32767,rt.INTEGER));ctx.variables.metadata['SIDE','DATA']=META.copy()
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick):v=p.run()
        self.assertEqual(v['STATUS'],6);self.assertNotIn(('CACHE','ITEM'),ctx.variables.bindings)
    def test_checkpoint_type_mapping_change_does_not_retarget_captured_schema(self):
        p,_=program();original=p._state.tick;fired=[]
        def tick(line=None):
            if not fired and any(r['operation']=='CREATE_VAR' for r in p.service_requests):fired.append(1);p.variable_types['ROW_T']=('ARRAY',4,rt.INTEGER,'ROW_T')
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick):v=p.run()
        self.assertEqual((v['STATUS'],rt.array_dimensions(ref(p._state.execution).spec)),(0,(2,3)))
    def test_checkpoint_bank_replacement_prevents_publication(self):
        p,_=program();ctx=p._state.execution;old=ctx.variables;original=p._state.tick;fired=[]
        def tick(line=None):
            if not fired and any(r['operation']=='CREATE_VAR' for r in p.service_requests):fired.append(1);ctx.variables=rt.VariableStore()
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick),self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((old.bindings,ctx.variables.bindings),({},{}))


class DynamicArrayPersistenceTests(unittest.TestCase):
    def test_context_json_retains_outer_and_child_schemas(self):
        _,ctx,_,_=run("SET_VAR(entry,'CACHE','ITEM[2,3]',7,status)");saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual((ref(restored).spec,ref(restored).raw().snapshot()),(ref(ctx).spec,[[U,U,U],[U,U,7]]));self.assertEqual(restored.to_config(),saved)
    def test_unknown_byte_markers_survive_context_replay(self):
        _,ctx,_,_=run(kind='ARRAY OF BYTE');restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())));self.assertEqual(ref(restored).raw().snapshot(),[B,B])
    def test_restored_metadata_reserves_combined_leaf_count(self):
        _,ctx,_,_=run();restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())));self.assertEqual(reserved(restored.variables),6)
    def test_vr_archive_roundtrip_preserves_named_layout_and_policy(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({}),variable_archives=rt.VariableArchives())
        body="SET_VAR(entry,'CACHE','ITEM[2,3]',7,status) SAVE('CACHE','FR:ROWS.VR',status) CLEAR('CACHE.VR',status) LOAD('FR:ROWS.VR',0,status) GET_VAR(entry,'CACHE','ITEM[2,3]',n,status)"
        v,_,_,_=run(body,context=ctx);self.assertEqual((v['N'],v['STATUS'],ref(ctx).spec[2][3]),(7,0,'ROW_T'));self.assertEqual(ctx.variables.metadata['CACHE','ITEM'],META)
    def test_dram_restore_preserves_existing_child_aliases(self):
        ctx=rt.ExecutionContext(variable_archives=rt.VariableArchives());v,_,p,_=run("SET_VAR(entry,'CACHE','ITEM[1,2]',7,status) SAVE_DRAM('CACHE',status)",context=ctx)
        old=ref(ctx).raw().values[0];old.set(2,99);self.assertEqual(ctx.variable_archives.restore_dram(p._state,'CACHE'),0);self.assertIs(old,ref(ctx).raw().values[0]);self.assertEqual(old.snapshot()[1],7)
    def test_restore_budget_fails_before_decoding_overflow_row(self):
        _,ctx,_,_=run();row=deepcopy(ctx.to_config()['variables'][0]);large=dict(program='SIDE',path='DATA',type=['ARRAY',32762,['INTEGER']],value=U,creation=META.copy())
        from karel2py import storage
        original=storage.decode_typed;decoded=[]
        def decode(value):decoded.append(storage.tuple_spec(value['type']));return original(value)
        with patch.object(storage,'decode_typed',side_effect=decode),self.assertRaises(ValueError):rt.ExecutionContext.from_config({'variables':[large,row]})
        self.assertEqual(decoded,[('ARRAY',32762,rt.INTEGER)])
    def test_restore_rejects_anonymous_inner_components(self):
        _,ctx,_,_=run();saved=ctx.to_config();saved['variables'][0]['type'][2]=['ARRAY',3,['INTEGER']]
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(saved)
    def test_new_type_owner_definition_does_not_retype_restored_values(self):
        _,ctx,_,_=run();restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        p,_=program(kind='ROW_T',prefix='TYPE row_t=ARRAY[4]OF INTEGER',context=restored);v=p.run();self.assertEqual((v['STATUS'],rt.array_dimensions(ref(restored).spec)),(3,(2,3)))


class DynamicArrayBoundsTests(unittest.TestCase):
    def test_combined_rank_above_three_is_rejected(self):
        v,ctx,_,_=run(dims=(2,2,2));self.assertEqual((v['STATUS'],ctx.variables.bindings),(5,{}))
    def test_anonymous_host_array_cannot_be_nested(self):
        p,_=program(kind='BAD');p.variable_types['BAD']=('ARRAY',3,rt.INTEGER);self.assertEqual(p.run()['STATUS'],5)
    def test_inline_nested_array_grammar_is_not_parsed(self):
        v,ctx,_,_=run(kind='ARRAY OF ARRAY OF INTEGER');self.assertEqual((v['STATUS'],ctx.variables.bindings),(5,{}))
    def test_collection_array_forms_have_reference_only_storage(self):
        for kind in ('PATH','QUEUE_TYPE'):
            with self.subTest(kind=kind):
                v,ctx,_,_=run(kind='ARRAY OF '+kind);self.assertEqual(v['STATUS'],0)
                self.assertTrue(rt.collection_array_type(ctx.variables.bindings['CACHE','ITEM'].spec))
    def test_positional_element_requires_explicit_group(self):
        v,ctx,_,_=run(kind='ARRAY OF JOINTPOS2');self.assertEqual((v['STATUS'],ctx.variables.bindings),(5,{}))
    def test_per_root_leaf_limit_counts_named_components(self):
        v,ctx,_,_=run(dims=(200,0,0),prefix='TYPE row_t=ARRAY[200]OF INTEGER');self.assertEqual((v['STATUS'],ctx.variables.bindings),(5,{}))
    def test_total_reserved_quota_includes_new_outer_storage(self):
        body=create('INTEGER',name='FIRST',dims=(32762,0,0))+create('ROW_T',dims=(2,0,0))
        p,_=compile_program(body,prefix=TYPES,decl=DECL);self.assertEqual(p.run()['STATUS'],6);self.assertNotIn(('CACHE','ITEM'),p._state.execution.variables.bindings)
    def test_exact_schema_depth_boundary_is_accepted(self):
        spec=rt.INTEGER
        for index in range(63):spec=('STRUCTURE','LEVEL_'+str(index),(('VALUE',spec),))
        self.assertEqual(creation_cost(spec),1)
    def test_outer_array_pushes_deep_named_schema_over_limit_without_allocation(self):
        leaf=rt.INTEGER
        for index in range(62):leaf=('STRUCTURE','LEVEL_'+str(index),(('VALUE',leaf),))
        p,_=program();p.variable_types['ROW_T']=('ARRAY',1,leaf,'ROW_T')
        with patch.object(rt,'initial_value',side_effect=AssertionError('must not allocate')):v=p.run()
        self.assertEqual((v['STATUS'],p._state.execution.variables.bindings),(5,{}))
    def test_empty_data_record_cannot_bypass_reserved_unit_accounting(self):
        with self.assertRaises(ValueError):creation_cost(('STRUCTURE','EMPTY',()))
    def test_schema_depth_is_bounded_before_recursive_collection_walk(self):
        spec=rt.INTEGER
        for index in range(65):spec=('STRUCTURE','LEVEL_'+str(index),(('VALUE',spec),))
        with self.assertRaises(ValueError):creation_cost(spec)


class DynamicArrayPreflightTests(unittest.TestCase):
    def test_array_of_requires_positive_inner_dimension(self):
        v,ctx,_,_=run(kind='ARRAY OF INTEGER',dims=(0,0,0));self.assertEqual((v['STATUS'],ctx.variables.bindings),(5,{}))
    def test_invalid_dimensions_return_without_allocation(self):
        for dims in ((0,1,0),(1,0,1),(-1,0,0),(32768,0,0)):
            p,_=program(dims=dims)
            with self.subTest(dims=dims),patch.object(rt,'initial_value',side_effect=AssertionError('must not allocate')):v=p.run()
            self.assertEqual((v['STATUS'],p._state.execution.variables.bindings),(5,{}))
    def test_memory_pool_intent_survives_json(self):
        p,_=compile_program(create('ARRAY OF ROW_T',dims=(2,0,0),pool=-1),prefix=TYPES,decl=DECL);p.run();ctx=p._state.execution;restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())));self.assertEqual(restored.variables.metadata['CACHE','ITEM'],{'group':0,'memory_pool':-1})
    def test_unknown_type_owner_cannot_discover_layout(self):
        p,_=compile_program(create('ARRAY OF ROW_T',type_owner='ABSENT',dims=(2,0,0)),prefix=TYPES,decl=DECL);self.assertEqual(p.run()['STATUS'],5)
    def test_case_and_spaces_are_normalized_without_type_evaluation(self):
        v,ctx,_,_=run(kind=' array   of   row_t ');self.assertEqual((v['STATUS'],ref(ctx).spec[2][3]),(0,'ROW_T'))
    def test_zero_extra_dimensions_keep_original_named_array(self):
        v,ctx,_,_=run(dims=(0,0,0));self.assertEqual((v['STATUS'],ref(ctx).spec),(0,('ARRAY',3,rt.INTEGER,'ROW_T')))
    def test_internal_strict_helper_keeps_prior_array_guard(self):
        p,_=program()
        with rt._numeric_scope('strict'):
            self.assertIsNone(concrete_type(p._state.execution,p._state,'T','ROW_T',0,(2,0,0),None));self.assertIsNone(concrete_type(p._state.execution,p._state,'T','ARRAY OF INTEGER',0,(2,0,0),None))
    def test_report_states_data_only_dynamic_layout_contract(self):
        _,r=program();self.assertFalse(r.report['dynamic_array_creation_policy']['controller_validated']);self.assertIn('64',r.report['dynamic_array_creation_policy']['validation']);json.dumps(r.report)
