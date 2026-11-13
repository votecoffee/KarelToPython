"""Fixed CREATE_VAR type text normalizes before checked allocation and publication."""
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py.dynamic import concrete_type,creation_cost,reserved
from tests.test_dynamic_narrow import create
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source


U={'uninitialized':True}
DECL='status,entry,n,seq:INTEGER buffer:ARRAY[2]OF INTEGER'
TYPES='TYPE row_t=ARRAY[3]OF INTEGER node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t'


def build(body='',kind='ARRAY[2]OF ARRAY[3]OF INTEGER',dims=(0,0,0),prefix=TYPES,decl=DECL,routines='',group=0,pool=None,**options):
    return compile_program(create(kind,dims=dims,group=group,pool=pool)+body,
                           prefix=prefix,decl=decl,routines=routines,**options)


def run(*args,**kwargs):
    p,result=build(*args,**kwargs)
    return p.run(),p._state.execution,p,result.report


def ref(ctx,name='ITEM',owner='CACHE'):return ctx.variables.bindings[owner,name]


class FixedArrayTypeTextTests(unittest.TestCase):
    def test_fixed_flat_and_inline_spellings_share_one_schema(self):
        for kind in ('ARRAY[2,3]OF INTEGER','ARRAY[2]OF ARRAY[3]OF INTEGER',' array [ 2 ] of array [ 3 ] of integer '):
            with self.subTest(kind=kind):
                v,ctx,_,_=run(kind=kind)
                self.assertEqual((v['STATUS'],ref(ctx).spec),(0,('ARRAY',(2,3),rt.INTEGER)))
                self.assertEqual(ref(ctx).raw().snapshot(),[[U,U,U],[U,U,U]])
                self.assertEqual(reserved(ctx.variables),6)

    def test_explicit_dimensions_are_outer_to_inner(self):
        _,ctx,_,_=run(kind='ARRAY[2]OF ARRAY[1,3]OF INTEGER')
        self.assertEqual(rt.array_dimensions(ref(ctx).spec),(2,1,3))

    def test_dimension_slots_add_outer_dimensions_in_legacy_order(self):
        _,ctx,_,_=run(kind='ARRAY[3]OF INTEGER',dims=(2,4,0))
        self.assertEqual(ref(ctx).spec,('ARRAY',(4,2,3),rt.INTEGER))

    def test_optional_bare_array_prefix_still_requires_dimension_slots(self):
        _,ctx,_,_=run(kind='ARRAY OF ARRAY[3]OF INTEGER',dims=(2,0,0))
        self.assertEqual(ref(ctx).spec,('ARRAY',(2,3),rt.INTEGER))
        v,ctx,_,_=run(kind='ARRAY OF ARRAY[3]OF INTEGER')
        self.assertEqual((v['STATUS'],ctx.variables.bindings),(5,{}))

    def test_named_inner_arrays_keep_identity_and_independent_children(self):
        _,ctx,_,_=run(kind='ARRAY[2]OF ROW_T')
        value=ref(ctx).raw()
        self.assertEqual(value.spec,('ARRAY',2,('ARRAY',3,rt.INTEGER,'ROW_T')))
        self.assertIsNot(value.values[0],value.values[1])
        value.set((2,3),7);self.assertEqual(value.snapshot(),[[U,U,U],[U,U,7]])

    def test_type_alias_named_array_can_gain_fixed_and_slot_dimensions(self):
        _,ctx,_,_=run(kind='ARRAY[1]OF ROW_ALIAS',dims=(2,0,0),prefix=TYPES+' row_alias=row_t')
        self.assertEqual(ref(ctx).spec,('ARRAY',(2,1),('ARRAY',3,rt.INTEGER,'ROW_T')))

    def test_terminal_type_name_starting_with_array_is_not_parsed_as_a_layer(self):
        _,ctx,_,_=run(kind='ARRAY[2]OF ARRAY_T',prefix=TYPES+' array_t=row_t')
        self.assertEqual(rt.array_dimensions(ref(ctx).spec),(2,3))

    def test_scalar_domains_and_string_defaults_are_preserved(self):
        for kind,leaf in [('INTEGER',rt.INTEGER),('REAL',rt.REAL),('BOOLEAN',rt.BOOLEAN),
                          ('BYTE',rt.BYTE),('SHORT',rt.SHORT),('STRING',('STRING',12)),
                          ('STRING[4]',('STRING',4)),('VECTOR',('VECTOR',)),('CONFIG',('CONFIG',))]:
            with self.subTest(kind=kind):
                v,ctx,_,_=run(kind='ARRAY[2]OF '+kind)
                self.assertEqual((v['STATUS'],ref(ctx).spec),(0,('ARRAY',2,leaf)))

    def test_record_terminals_preserve_fields_and_named_arrays(self):
        prefix=TYPES+' item_t=STRUCTURE cells:row_t text:STRING[4] ENDSTRUCTURE'
        v,ctx,_,_=run("SET_VAR(entry,'CACHE','ITEM[2,3].CELLS[2]',7,status)",kind='ARRAY[2]OF ARRAY[3]OF item_t',prefix=prefix)
        self.assertEqual(v['STATUS'],0)
        self.assertEqual(ref(ctx).raw().snapshot()[1][2],{'CELLS':[U,7,U],'TEXT':U})

    def test_positional_terminals_retain_explicit_group_metadata(self):
        for kind in ('POSITION','XYZWPR','XYZWPREXT','JOINTPOS2'):
            with self.subTest(kind=kind):
                v,ctx,_,_=run(kind='ARRAY[2]OF '+kind,group=3,pool=-1)
                self.assertEqual(v['STATUS'],0)
                self.assertEqual(ctx.variables.metadata['CACHE','ITEM'],{'group':3,'memory_pool':-1})
                self.assertIsNone(ctx.robot)
                self.assertEqual(run(kind='ARRAY[2]OF '+kind)[0]['STATUS'],5)

    def test_foreign_type_owner_supplies_terminal_without_discovery(self):
        main=source('MAIN',create('ARRAY[2]OF row_t',type_owner='LIB'),decl='status:INTEGER')
        lib='PROGRAM LIB TYPE row_t=ARRAY[4]OF INTEGER BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate();project.run('MAIN')
        self.assertEqual(rt.array_dimensions(ref(project.context).spec),(2,4))


class FixedArrayOperationsTests(unittest.TestCase):
    def test_exact_byname_and_variable_transfers_use_normalized_coordinates(self):
        routines='ROUTINE work(p:ARRAY OF ARRAY OF INTEGER) BEGIN p[2,3]=7 END work'
        v,ctx,_,_=run("work(BYNAME('CACHE','ITEM',entry)) GET_VAR(entry,'CACHE','ITEM[2,3]',n,status)",routines=routines)
        self.assertEqual((v['STATUS'],v['N']),(0,7))
        self.assertEqual(ref(ctx).raw().snapshot()[1],[U,U,7])

    def test_variable_inspection_reports_the_normalized_shape(self):
        v,_,_,_=run("VAR_INFO('CACHE','ITEM',flag,label,code,dims,length,status)",
            decl=DECL+' flag:BOOLEAN label:STRING[32] code,length:INTEGER dims:ARRAY[3]OF INTEGER')
        self.assertEqual((v['STATUS'],v['DIMS']),(0,[2,3,0]))

    def test_path_headers_count_all_immediately_reserved_units(self):
        prefix='TYPE head_t=STRUCTURE cells:ARRAY[2]OF INTEGER ENDSTRUCTURE route_t=PATH PATHHEADER=head_t'
        _,ctx,_,_=run(kind='ARRAY[2]OF ARRAY[3]OF route_t',prefix=prefix)
        self.assertEqual((creation_cost(ref(ctx).spec),reserved(ctx.variables)),(18,18))

    def test_read_write_and_source_copy_use_ordinary_data_contract(self):
        routines='ROUTINE work(p:ARRAY[*,*]OF INTEGER) BEGIN READ(p) WRITE(p::2) END work'
        v,ctx,p,_=run("work(BYNAME('CACHE','ITEM',entry)) GET_VAR(entry,'CACHE','ITEM',copy,status)",
            decl=DECL+' copy:ARRAY[2,3]OF INTEGER',routines=routines,read=lambda request:[1,2,3,4,5,6])
        self.assertEqual((v['STATUS'],v['COPY']),(0,[[1,2,3],[4,5,6]]))
        self.assertEqual([row['text'] for row in p.write_requests],[' 1 2 3 4 5 6'])
        self.assertIsNot(ref(ctx).raw(),p._state.raw('COPY'))

    def test_source_linked_routine_borrows_created_matrix(self):
        main=source('MAIN',create('ARRAY[2]OF ARRAY[3]OF INTEGER')+"work(BYNAME('CACHE','ITEM',entry))",
                    decl=DECL,routines='ROUTINE work(p:ARRAY OF ARRAY OF INTEGER) FROM LIB')
        lib=source('LIB','',routines='ROUTINE work(p:ARRAY[*,*]OF INTEGER) BEGIN p[2,3]=7 END work')
        project=translate_project({'main':main,'lib':lib}).instantiate();project.run('MAIN')
        self.assertEqual(ref(project.context).raw().snapshot()[1][2],7)

    def test_pause_and_root_rename_retain_the_captured_array(self):
        routine="ROUTINE work(p:ARRAY OF ARRAY OF INTEGER) BEGIN p[1,1]=7 PAUSE RENAME_VAR('CACHE','ITEM','KEPT',status) p[2,3]=9 END work"
        p,_=build("work(BYNAME('CACHE','ITEM',entry))",routines=routine,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        original=ref(p._state.execution).raw();p.resume()
        self.assertIs(ref(p._state.execution,'KEPT').raw(),original)
        self.assertEqual(original.snapshot(),[[7,U,U],[U,U,9]])

    def test_file_matrix_uses_original_descriptors_and_closed_allocation_markers(self):
        files=rt.MemoryFiles();ctx=rt.ExecutionContext(files=files)
        routines="ROUTINE work(p:ARRAY OF ARRAY OF FILE) BEGIN OPEN FILE p[2,3]('WB','out') WRITE p[2,3](17) CLOSE FILE p[2,3] END work"
        v,ctx,_,_=run("work(BYNAME('CACHE','ITEM',entry))",kind='ARRAY[2]OF ARRAY[3]OF FILE',routines=routines,context=ctx)
        self.assertEqual(v['STATUS'],0);self.assertEqual(files.snapshot(),{'out':b'\x11\x00\x00\x00'})
        saved=json.loads(json.dumps(ctx.to_config()))
        self.assertEqual(saved['variables'][0]['value'],{'closed':True})
        restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(ref(restored).spec,('ARRAY',(2,3),('FILE',)))
        self.assertTrue(all(h.owner is None for h in ref(restored).raw().values))
        self.assertIsNot(ref(restored).raw().values[0],ref(restored).raw().values[1])

    def test_custom_path_matrix_owns_nodes_and_preserves_archive_layout(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(),variable_archives=rt.VariableArchives())
        routines='ROUTINE work(p:ARRAY OF ARRAY OF route_t) BEGIN APPEND_NODE(p[2,3],status) p[2,3][1].amount=17 END work'
        body="work(BYNAME('CACHE','ITEM',entry)) SAVE('CACHE','FR:DATA.VR',status) CLEAR('CACHE.VR',status) LOAD('FR:DATA.VR',0,status)"
        v,ctx,_,_=run(body,kind='ARRAY[2]OF ARRAY[3]OF route_t',routines=routines,context=ctx)
        self.assertEqual((v['STATUS'],ref(ctx).raw().snapshot()[1][2]['nodes']),(0,[{'AMOUNT':17}]))
        self.assertEqual(ref(ctx).raw().snapshot()[0][0]['nodes'],[])

    def test_queue_matrix_persistence_detaches_buffer_links(self):
        routine='ROUTINE work(p:ARRAY OF ARRAY OF QUEUE_TYPE) BEGIN INIT_QUEUE(p[2,3]) APPEND_QUEUE(7,p[2,3],buffer,seq,status) END work'
        v,ctx,_,_=run("work(BYNAME('CACHE','ITEM',entry))",kind='ARRAY[2,3]OF QUEUE_TYPE',routines=routine)
        self.assertEqual(v['STATUS'],0)
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(ref(restored).raw().snapshot()[1][2]['entries'],[[1,7]])
        self.assertFalse(ref(restored).raw().snapshot()[0][0]['initialized'])
        self.assertIsNone(ref(restored).raw().values[5].buffer)

    def test_data_context_roundtrip_keeps_flat_schema_and_creation_policy(self):
        _,ctx,_,_=run("SET_VAR(entry,'CACHE','ITEM[2,3]',7,status)",pool=-1)
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(ref(restored).spec,('ARRAY',(2,3),rt.INTEGER))
        self.assertEqual(ref(restored).raw().snapshot(),[[U,U,U],[U,U,7]])
        self.assertEqual(restored.to_config(),saved)
        self.assertEqual(reserved(restored.variables),6)


class FixedArrayPreflightTests(unittest.TestCase):
    def invalid(self,kind,**options):
        p,_=build(kind=kind,**options);ctx=p._state.execution
        with patch.object(rt,'initial_value',side_effect=AssertionError('must not allocate')):v=p.run()
        self.assertEqual((v['STATUS'],ctx.variables.bindings,ctx.variables.metadata),(5,{},{}))

    def test_malformed_or_executable_dimension_text_is_rejected_without_allocation(self):
        for kind in ('ARRAY[]OF INTEGER','ARRAY[0]OF INTEGER','ARRAY[-1]OF INTEGER','ARRAY[+1]OF INTEGER',
                     'ARRAY[2.0]OF INTEGER','ARRAY[1+1]OF INTEGER','ARRAY[*]OF INTEGER',
                     'ARRAY[2,]OF INTEGER','ARRAY[2,,3]OF INTEGER','ARRAY[32768]OF INTEGER',
                     'ARRAY[999999]OF INTEGER','ARRAY[1,2,3,4]OF INTEGER','ARRAY[2]OF ARRAY OF INTEGER',
                     'ARRAY[2]OF UNKNOWN','ARRAY[2]OF INTEGER trailing','ARRAY[2]INTEGER',
                     'ARRAY[2]OF STRING[0]','ARRAY[2]OF STRING[255]'):
            with self.subTest(kind=kind):self.invalid(kind)

    def test_repeated_literal_layers_are_bounded_before_allocation(self):
        self.invalid('ARRAY[1]OF '*20+'INTEGER')

    def test_complete_logical_rank_counts_slots_fixed_layers_and_named_components(self):
        for kind,dims in [('ARRAY[1,1]OF ARRAY[1,1]OF INTEGER',(0,0,0)),
                          ('ARRAY[1,1]OF INTEGER',(1,1,0)),('ARRAY[1]OF ROW_T',(1,1,0))]:
            with self.subTest(kind=kind,dims=dims):self.invalid(kind,dims=dims)

    def test_schema_and_sparse_slot_limits_precede_allocation(self):
        self.invalid('ARRAY[200]OF ARRAY[200]OF INTEGER')
        self.invalid('ARRAY[2]OF INTEGER',dims=(0,2,0))
        self.invalid('ARRAY[2]OF INTEGER',dims=(1,0,2))

    def test_unknown_owner_and_group_still_reject(self):
        p,_=compile_program(create('ARRAY[2]OF ROW_T',type_owner='ABSENT'),prefix=TYPES,decl=DECL)
        self.assertEqual(p.run()['STATUS'],5)
        self.invalid('ARRAY[2]OF INTEGER',group=33)

    def test_anonymous_host_component_is_not_relabelled_as_named(self):
        p,_=build(kind='ARRAY[2]OF BAD');p.variable_types['BAD']=('ARRAY',3,rt.INTEGER)
        self.assertEqual(p.run()['STATUS'],5)

    def test_repeated_bare_layers_remain_ambiguous_and_rejected(self):
        self.invalid('ARRAY OF ARRAY OF INTEGER',dims=(2,3,0))

    def test_shared_quota_failure_preserves_prior_created_root(self):
        body=create('INTEGER',name='FIRST',dims=(32762,0,0))+create('ARRAY[2,3]OF INTEGER')
        p,_=compile_program(body,decl=DECL);v=p.run();ctx=p._state.execution
        self.assertEqual(v['STATUS'],6)
        self.assertEqual(set(ctx.variables.bindings),{('CACHE','FIRST')})

    def test_exact_reservation_boundary_accepts_fixed_shape(self):
        body=create('INTEGER',name='FIRST',dims=(32761,0,0))+create('ARRAY[2,3]OF INTEGER')
        p,_=compile_program(body,decl=DECL);self.assertEqual(p.run()['STATUS'],0)
        self.assertEqual(reserved(p._state.execution.variables),32767)

    def test_checkpoint_collision_retains_competing_value(self):
        p,_=build();ctx=p._state.execution;original=p._state.tick;fired=[]
        def tick(line=None):
            if not fired and any(r['operation']=='CREATE_VAR' for r in p.service_requests):
                fired.append(1);ctx.variables.define('CACHE','ITEM',rt.INTEGER,99)
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick):v=p.run()
        self.assertEqual((v['STATUS'],ref(ctx).raw(),ctx.variables.metadata),(3,99,{}))

    def test_checkpoint_bank_replacement_leaves_both_stores_unmodified(self):
        p,_=build();ctx=p._state.execution;old=ctx.variables;original=p._state.tick;fired=[]
        def tick(line=None):
            if not fired and any(r['operation']=='CREATE_VAR' for r in p.service_requests):
                fired.append(1);ctx.variables=rt.VariableStore()
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick),self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((old.bindings,ctx.variables.bindings),({},{}))

    def test_checkpoint_type_change_cannot_retarget_captured_named_component(self):
        p,_=build(kind='ARRAY[2]OF ROW_T');ctx=p._state.execution;original=p._state.tick;fired=[]
        def tick(line=None):
            if not fired and any(r['operation']=='CREATE_VAR' for r in p.service_requests):
                fired.append(1);p.variable_types['ROW_T']=('ARRAY',4,rt.INTEGER,'ROW_T')
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick):v=p.run()
        self.assertEqual((v['STATUS'],rt.array_dimensions(ref(ctx).spec)),(0,(2,3)))

    def test_budget_failure_preserves_status_and_unpublished_root(self):
        p,_=build();ctx=p._state.execution;original=p._state.tick;fired=[]
        p._state.values['STATUS']=23
        def tick(line=None):
            if any(row['operation']=='CREATE_VAR' for row in p.service_requests):
                fired.append(1);raise rt.KarelRuntimeError('Execution step limit')
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'step limit'):p.run()
        self.assertEqual(fired,[1])
        self.assertEqual((ctx.variables.bindings,ctx.variables.metadata),({},{}))
        self.assertEqual(p.snapshot()['STATUS'],23)

    def test_strict_runtime_does_not_accept_fixed_type_text(self):
        p,_=build()
        with rt._numeric_scope('strict'):
            for kind in ('ARRAY[2]OF INTEGER','ARRAY[2]OF ARRAY[3]OF FILE','ARRAY[2]OF QUEUE_TYPE'):
                self.assertIsNone(concrete_type(p._state.execution,p._state,'T',kind,0,(0,0,0),1))

    def test_report_exposes_fixed_literal_policy_and_retained_boundaries(self):
        _,_,_,report=run()
        policy=report['dynamic_fixed_array_policy']
        self.assertFalse(policy['controller_validated'])
        self.assertEqual(policy['guide'],'docs/dynamic-fixed-arrays.md')
        self.assertIn('without source evaluation',policy['validation'])
        self.assertIn('repeated bare ARRAY',report['dynamic_array_creation_policy']['boundaries'])
        self.assertNotIn('inline nested type grammar',report['dynamic_array_creation_policy']['boundaries'])


if __name__=='__main__':unittest.main()
