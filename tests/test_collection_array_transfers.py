"""Authored logical collection bank transfers and original-cell prefix captures."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate,translate_project
from karel2py import extended as ex
from karel2py.lexer import TranslationError
from karel2py.storage import typed_value
from tests.test_extended_services import compile_program
from tests.test_collection_array_archives import PATH,PREFIX

DECL='source,target:ARRAY[2]OF route_t entry,status,visits:INTEGER'
GET="GET_VAR(entry,'','SOURCE',target,status)";SET="SET_VAR(entry,'','TARGET',source,status)"
ROW_DECL='source,target:ARRAY[2,2]OF route_t entry,status,visits:INTEGER'
ROW_GET="GET_VAR(entry,'','SOURCE[2]',target[2],status)";ROW_SET="SET_VAR(entry,'','TARGET[2]',source[2],status)"
QDECL='source,target:ARRAY[2]OF QUEUE_TYPE buffers:ARRAY[2,3]OF INTEGER entry,status,seq:INTEGER'
U={'uninitialized':True}


def collections(value):
    for item in value.values:
        if type(item) is rt.Array:yield from collections(item)
        else:yield item


def prepare(body=GET,*,decl=DECL,prefix=PREFIX,seed=True,**options):
    p,result=compile_program(body,decl=decl,prefix=prefix,**options)
    if seed:
        for name in ('SOURCE','TARGET'):
            for item in collections(p._state.values[name]):
                if type(item) is rt.PathValue and item.data is not None:item.data.values['COUNT']=0
                if type(item) is rt.QueueValue:item.initialized=True
        source=list(collections(p._state.values['SOURCE']))[-1]
        if type(source) is rt.PathValue:source.append();source.nodes[0].values['VALUE']=17;source.data.values['COUNT']=1
        else:source.sequence=2;source.entries=[(2,17)]
    return p,result


def row(body=ROW_GET,*,decl=ROW_DECL,**options):return prepare(body,decl=decl,**options)
def queues(body=GET,**options):return prepare(body,decl=QDECL,prefix='',**options)
def raw(p,name='TARGET'):return p._state.values[name]
def snapshot(value):return rt.snapshot_value(value)


class CollectionTransferWholeTests(unittest.TestCase):
    def test_get_copies_whole_path_bank(self):
        p,_=prepare();v=p.run();self.assertEqual(v['STATUS'],0);self.assertEqual(v['TARGET'],v['SOURCE']);self.assertEqual(v['ENTRY'],1)
    def test_set_copies_whole_path_bank(self):
        p,_=prepare(SET);v=p.run();self.assertEqual(v['STATUS'],0);self.assertEqual(v['TARGET'],v['SOURCE'])
    def test_get_copies_whole_queue_bank(self):
        p,_=queues();v=p.run();self.assertEqual(v['STATUS'],0);self.assertEqual(v['TARGET'],v['SOURCE']);self.assertEqual(raw(p).values[1].sequence,2)
    def test_set_copies_whole_queue_bank(self):
        p,_=queues(SET);v=p.run();self.assertEqual(v['STATUS'],0);self.assertEqual(v['TARGET'],v['SOURCE'])
    def test_source_and_receiver_collections_stay_independent(self):
        p,_=prepare();p.run();raw(p,'SOURCE').values[1].nodes[0].values['VALUE']=99;self.assertEqual(raw(p).values[1].nodes[0].values['VALUE'],17)
    def test_preserves_destination_array_and_path_objects(self):
        p,_=prepare();target=raw(p);storage=target.values;cells=list(storage);p.run();self.assertIs(raw(p),target);self.assertIs(target.values,storage);self.assertTrue(all(a is b for a,b in zip(cells,target.values)))
    def test_preserves_headers_and_detaches_old_node_storage(self):
        p,_=prepare();cell=raw(p).values[1];cell.append();cell.nodes[0].values['VALUE']=88;old=cell.nodes;header=cell.data;alias=rt.field_reference(old[0],'VALUE');p.run();self.assertIs(cell.data,header);self.assertIsNot(cell.nodes,old);self.assertEqual(alias.raw(),88)
    def test_queue_buffers_are_not_copied_or_retargeted(self):
        p,_=queues();source=raw(p,'SOURCE').values[1];target=raw(p).values[1];buffer=rt.Array(('ARRAY',3,('INTEGER',)));source.buffer=buffer;target.buffer=buffer;p.run();self.assertIsNone(target.buffer);self.assertIs(source.buffer,buffer)
    def test_self_copy_detaches_paths_without_replacing_cells(self):
        p,_=prepare("GET_VAR(entry,'','SOURCE',source,status)");cell=raw(p,'SOURCE').values[1];nodes=cell.nodes;p.run();self.assertIs(raw(p,'SOURCE').values[1],cell);self.assertIsNot(cell.nodes,nodes);self.assertEqual(cell.nodes[0].values['VALUE'],17)
    def test_self_queue_copy_drops_runtime_buffer_link(self):
        p,_=queues("GET_VAR(entry,'','SOURCE',source,status)");q=raw(p,'SOURCE').values[1];q.buffer=rt.Array(('ARRAY',3,('INTEGER',)));p.run();self.assertIsNone(q.buffer)
    def test_named_bank_type_keeps_declared_identity(self):
        p,_=prepare(decl='source,target:bank_t entry,status,visits:INTEGER',prefix=PREFIX+' bank_t=ARRAY[2]OF route_t');p.run();self.assertEqual(raw(p).spec[-1],'BANK_T')
    def test_named_nested_components_keep_existing_containers(self):
        p,_=prepare(decl='source,target:ARRAY[2]OF row_t entry,status,visits:INTEGER',prefix=PREFIX+' row_t=ARRAY[2]OF route_t');inner=raw(p).values[1];p.run();self.assertIs(raw(p).values[1],inner);self.assertEqual(inner.values[1].nodes[0].values['VALUE'],17)
    def test_grouped_set_source_is_a_private_transfer_snapshot(self):
        p,_=prepare(SET.replace(',source,',',(source),'));self.assertEqual(p.run()['STATUS'],0)
    def test_repeated_calls_reuse_named_entry_cache_id(self):
        p,_=prepare(GET+' '+GET);self.assertEqual(p.run()['ENTRY'],1);self.assertEqual(p._state.execution.entries,{('T','SOURCE'):1})


class CollectionTransferPrefixTests(unittest.TestCase):
    def test_get_writes_selected_original_row(self):
        p,_=row();v=p.run();self.assertEqual(v['STATUS'],0);self.assertEqual(v['TARGET'][1],v['SOURCE'][1]);self.assertEqual(v['TARGET'][0][1]['nodes'],[])
    def test_set_writes_quoted_selected_row(self):
        p,_=row(ROW_SET);v=p.run();self.assertEqual(v['STATUS'],0);self.assertEqual(v['TARGET'][1],v['SOURCE'][1])
    def test_grouped_set_prefix_retains_snapshot_semantics(self):
        p,_=row(ROW_SET.replace(',source[2],',',(source[2]),'));self.assertEqual(p.run()['STATUS'],0)
    def test_get_whole_bank_into_an_equal_suffix_row(self):
        p,_=prepare("GET_VAR(entry,'','SOURCE',target[2],status)",decl='source:ARRAY[2]OF route_t target:ARRAY[2,2]OF route_t entry,status,visits:INTEGER');v=p.run();self.assertEqual(v['SOURCE'],v['TARGET'][1])
    def test_set_prefix_into_whole_bank(self):
        p,_=prepare("SET_VAR(entry,'','TARGET',source[2],status)",decl='source:ARRAY[2,2]OF route_t target:ARRAY[2]OF route_t entry,status,visits:INTEGER');v=p.run();self.assertEqual(v['SOURCE'][1],v['TARGET'])
    def test_plane_copy_retains_unselected_plane(self):
        p,_=prepare(ROW_GET,decl='source,target:ARRAY[2,2,2]OF route_t entry,status,visits:INTEGER');v=p.run();self.assertEqual(v['SOURCE'][1],v['TARGET'][1]);self.assertEqual(v['TARGET'][0][1][1]['nodes'],[])
    def test_chained_source_and_named_path_indexes_normalize(self):
        p,_=prepare("SET_VAR(entry,'','TARGET[2][1]',source[2][1],status)",decl='source,target:ARRAY[2,2,2]OF route_t entry,status,visits:INTEGER');list(collections(raw(p,'SOURCE')))[5].append();list(collections(raw(p,'SOURCE')))[5].nodes[0].values['VALUE']=33;v=p.run();self.assertEqual(v['TARGET'][1][0][1]['nodes'][0]['VALUE'],33)
    def test_nested_named_component_row(self):
        p,_=prepare("GET_VAR(entry,'','SOURCE[2,2]',target[2,2],status)",decl='source,target:ARRAY[2]OF row_t entry,status,visits:INTEGER',prefix=PREFIX+' row_t=ARRAY[2,2]OF route_t');v=p.run();self.assertEqual(v['TARGET'][1][1],v['SOURCE'][1][1])
    def test_queue_row_copy_leaves_other_row_buffer_links_live(self):
        p,_=prepare(ROW_GET,decl='source,target:ARRAY[2,2]OF QUEUE_TYPE entry,status,visits:INTEGER',prefix='');buffer=rt.Array(('ARRAY',3,('INTEGER',)));raw(p).values[0].buffer=buffer;raw(p).values[2].buffer=buffer;p.run();self.assertIs(raw(p).values[0].buffer,buffer);self.assertIsNone(raw(p).values[2].buffer)
    def test_old_byname_view_observes_original_target_cells(self):
        p,_=row();target=raw(p)
        with rt._numeric_scope('pythonic'):view=rt.resource_array_prefix_reference(target,2,target.spec).raw()
        p.run()
        with rt._numeric_scope('pythonic'):self.assertIs(view.values[1],target.values[3]);self.assertEqual(view.values[1].nodes[0].values['VALUE'],17)
    def test_output_row_selector_runs_once(self):
        body="visits=0 GET_VAR(entry,'','SOURCE[2]',target[pick()],status)";p,_=row(body,routines='ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN(2) END pick');self.assertEqual(p.run()['VISITS'],1)
    def test_source_row_selector_runs_once(self):
        body="visits=0 SET_VAR(entry,'','TARGET[2]',source[pick()],status)";p,_=row(body,routines='ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN(2) END pick');self.assertEqual(p.run()['VISITS'],1)


class CollectionTransferOrderingTests(unittest.TestCase):
    def test_set_source_budget_precedes_payload_and_status_selector(self):
        body=SET.replace(',status)',',statuses[later()])')
        p,_=prepare(body,decl=QDECL+' visits:INTEGER statuses:ARRAY[1]OF INTEGER',
                    prefix='',routines='ROUTINE later:INTEGER BEGIN visits=visits+1 RETURN(1) END later')
        source=raw(p,'SOURCE').values[1]
        source.sequence=12
        source.entries=[(number,number) for number in range(1,13)]
        p._state.values.update(ENTRY=77,VISITS=0)
        p._state.values['STATUSES'].set(1,88)
        target=raw(p);before=snapshot(target)
        with patch('karel2py.storage.collection_payload',side_effect=AssertionError('Source was encoded before charging')):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=8)
        result=p.snapshot()
        self.assertEqual((result['ENTRY'],result['STATUSES'],result['VISITS']),(77,[88],0))
        self.assertEqual(snapshot(target),before)
        self.assertEqual(p._state.execution.entries,{})

    def test_get_row_receiver_budget_preserves_cells_and_outputs(self):
        p,_=row()
        target=raw(p);cell=target.values[3];nodes=cell.nodes;header=cell.data
        for value in range(12):
            cell.append()
            cell.nodes[-1].values['VALUE']=value
        cell.data.values['COUNT']=12
        before=snapshot(target)
        p._state.values.update(ENTRY=77,STATUS=88)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=8)
        self.assertIs(raw(p),target)
        self.assertIs(target.values[3],cell)
        self.assertIs(cell.nodes,nodes)
        self.assertIs(cell.data,header)
        self.assertEqual(snapshot(target),before)
        result=p.snapshot()
        self.assertEqual((result['ENTRY'],result['STATUS']),(77,88))
        self.assertEqual(p._state.execution.entries,{})

    def test_set_snapshot_precedes_later_status_effects(self):
        p,_=row("SET_VAR(entry,'','TARGET[2]',source[2],statuses[later()])",decl='source,target:ARRAY[2,2]OF route_t entry,status,visits:INTEGER statuses:ARRAY[1]OF INTEGER',routines='ROUTINE later:INTEGER FROM HOST');ctx=p._state.execution;ctx.externals['HOST','LATER']=lambda:(raw(p,'SOURCE').values[3].nodes[0].values.update(VALUE=99) or 1);p.run();self.assertEqual(raw(p).values[3].nodes[0].values['VALUE'],17)
    def test_get_named_snapshot_follows_output_selector_effects(self):
        p,_=row("GET_VAR(entry,'','SOURCE[2]',target[2],statuses[later()])",decl='source,target:ARRAY[2,2]OF route_t entry,status,visits:INTEGER statuses:ARRAY[1]OF INTEGER',routines='ROUTINE later:INTEGER FROM HOST');p._state.execution.externals['HOST','LATER']=lambda:(raw(p,'SOURCE').values[3].nodes[0].values.update(VALUE=99) or 1);p.run();self.assertEqual(raw(p).values[3].nodes[0].values['VALUE'],99)
    def test_get_output_capture_ignores_later_root_list_replacement(self):
        p,_=row("GET_VAR(entry,'','SOURCE[2]',target[2],statuses[later()])",decl='source,target:ARRAY[2,2]OF route_t entry,status,visits:INTEGER statuses:ARRAY[1]OF INTEGER',routines='ROUTINE later:INTEGER FROM HOST');old=raw(p).values;p._state.execution.externals['HOST','LATER']=lambda:(setattr(raw(p),'values',list(raw(p,'SOURCE').values)) or 1);p.run();self.assertEqual(old[3].nodes[0].values['VALUE'],17);self.assertIsNot(old,raw(p).values)
    def test_malformed_source_prefix_fails_before_later_status_selector(self):
        p,_=row("visits=0 SET_VAR(entry,'','TARGET[2]',source[2],statuses[later()])",decl='source,target:ARRAY[2,2]OF route_t entry,status,visits:INTEGER statuses:ARRAY[1]OF INTEGER',routines='ROUTINE later:INTEGER BEGIN visits=visits+1 RETURN(1) END later');raw(p,'SOURCE').values[0].data.values['COUNT']=True
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)
    def test_source_snapshot_owns_no_queue_buffer_links(self):
        p,_=queues(SET);source=raw(p,'SOURCE');buffer=rt.Array(('ARRAY',3,('INTEGER',)));source.values[1].buffer=buffer
        with rt._numeric_scope('pythonic'):captured=ex.variable_reference(rt.Reference(source.spec,{'v':source},'v'))
        self.assertIsNone(captured.value.values[1].buffer);self.assertIs(source.values[1].buffer,buffer)
    def test_pause_resume_continues_with_saved_private_source_snapshot(self):
        p,_=row(ROW_SET.replace(',status)',',statuses[later()])'),decl='source,target:ARRAY[2,2]OF route_t entry,status,visits:INTEGER statuses:ARRAY[1]OF INTEGER',routines='ROUTINE later:INTEGER BEGIN PAUSE RETURN(1) END later',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        raw(p,'SOURCE').values[3].nodes[0].values['VALUE']=99;p.resume();self.assertEqual(raw(p).values[3].nodes[0].values['VALUE'],17)


class CollectionTransferGuardTests(unittest.TestCase):
    def test_get_entry_cannot_overlap_receiver_header(self):
        p,_=prepare("GET_VAR(target[1].count,'','SOURCE',target,status)");before=snapshot(raw(p))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(snapshot(raw(p)),before);self.assertEqual(p._state.execution.entries,{})
    def test_get_status_cannot_overlap_receiver_node(self):
        p,_=prepare("GET_VAR(entry,'','SOURCE',target,target[2][1].value)");cell=raw(p).values[1];cell.append();cell.nodes[0].values['VALUE']=88
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(cell.nodes[0].values['VALUE'],88)
    def test_set_named_receiver_cannot_overlap_status(self):
        p,_=prepare(SET.replace(',status)',',target[1].count)'));before=snapshot(raw(p))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(snapshot(raw(p)),before)
    def test_selected_row_and_entry_overlap_is_detected(self):
        p,_=row(ROW_GET.replace('entry,','target[2,1].count,'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
    def test_disjoint_row_can_hold_entry_output(self):
        p,_=row(ROW_GET.replace('entry,','target[1,1].count,'));self.assertEqual(p.run()['TARGET'][0][0]['data']['COUNT'],1)
    def test_malformed_unselected_output_row_fails_capture(self):
        p,_=row();raw(p).values[0].data.values['COUNT']=True
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.execution.entries,{})
    def test_missing_output_storage_list_has_source_located_runtime_error(self):
        p,_=prepare('entry=77 status=88 '+GET);raw(p).values=None
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Collection ARRAY output storage'):p.run()
        self.assertEqual((p._state.values['ENTRY'],p._state.values['STATUS']),(77,88));self.assertEqual(p._state.execution.entries,{})
    def test_invalid_output_node_list_has_source_located_runtime_error(self):
        p,_=prepare('entry=77 status=88 '+GET);raw(p).values[1].nodes=None
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Collection ARRAY output storage'):p.run()
        self.assertEqual((p._state.values['ENTRY'],p._state.values['STATUS']),(77,88))
    def test_shared_receiver_headers_are_rejected(self):
        p,_=prepare();target=raw(p);target.values[1].data=target.values[0].data
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
    def test_shared_receiver_queue_cells_are_rejected(self):
        p,_=queues();raw(p).values[1]=raw(p).values[0]
        with self.assertRaisesRegex(rt.KarelRuntimeError,'distinct|overlap'):p.run()
    def test_shared_source_cells_are_rejected_before_status_publication(self):
        p,_=prepare('entry=77 status=88 '+SET);raw(p,'SOURCE').values[1]=raw(p,'SOURCE').values[0]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['ENTRY'],p.snapshot()['STATUS']),(77,88))
    def test_changed_retained_prefix_list_size_fails(self):
        p,_=row("GET_VAR(entry,'','SOURCE[2]',target[2],statuses[later()])",decl='source,target:ARRAY[2,2]OF route_t entry,status,visits:INTEGER statuses:ARRAY[1]OF INTEGER',routines='ROUTINE later:INTEGER FROM HOST');p._state.execution.externals['HOST','LATER']=lambda:(raw(p).values.pop(),1)[1]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.execution.entries,{})
    def test_missing_source_root_preserves_receiver_entry_and_cache(self):
        p,_=prepare('entry=77 '+GET.replace("'SOURCE'","'ABSENT'"));before=snapshot(raw(p));v=p.run();self.assertEqual((v['ENTRY'],v['STATUS']),(77,1));self.assertEqual(snapshot(raw(p)),before);self.assertEqual(p._state.execution.entries,{})
    def test_wrong_array_dimensions_return_type_status_without_publication(self):
        p,_=prepare('entry=77 '+GET,decl='source:ARRAY[2]OF route_t target:ARRAY[3]OF route_t entry,status,visits:INTEGER');before=snapshot(raw(p));v=p.run();self.assertEqual((v['ENTRY'],v['STATUS']),(77,3));self.assertEqual(snapshot(raw(p)),before)
    def test_named_bank_identities_remain_exact(self):
        p,_=prepare(GET,decl='source:a_t target:b_t entry,status,visits:INTEGER',prefix=PREFIX+' a_t=ARRAY[2]OF route_t b_t=ARRAY[2]OF route_t');self.assertEqual(p.run()['STATUS'],3)
    def test_data_and_resource_array_kinds_do_not_convert(self):
        p,_=prepare(GET,decl='source:ARRAY[2]OF route_t target:ARRAY[2]OF INTEGER entry,status,visits:INTEGER',seed=False);self.assertEqual(p.run()['STATUS'],3)
    def test_file_prefix_lookup_retains_unsupported_status(self):
        p,_=compile_program("GET_VAR(entry,'','FILES[2]',target,status)",decl='files:ARRAY[2,2]OF FILE target:ARRAY[2]OF INTEGER entry,status:INTEGER');self.assertEqual(p.run()['STATUS'],1)
    def test_grouped_get_output_stays_rejected(self):
        with self.assertRaises(TranslationError):prepare(GET.replace(',target,',',(target),'))
    def test_collection_source_type_mismatch_stays_rejected(self):
        with self.assertRaises(TranslationError):prepare('other=source',decl=DECL+' other:ARRAY[2]OF QUEUE_TYPE')
    def test_grouped_collection_argument_type_mismatch_stays_rejected(self):
        with self.assertRaises(TranslationError):prepare('work((source))',routines='ROUTINE work(items:ARRAY OF QUEUE_TYPE) BEGIN END work')
    def test_collection_prefix_argument_type_mismatch_stays_rejected(self):
        with self.assertRaises(TranslationError):row('work(source[2])',routines='ROUTINE work(items:ARRAY OF QUEUE_TYPE) BEGIN END work')
    def test_active_counter_protection_remains(self):
        with self.assertRaises(TranslationError):compile_program(SET.replace('SET_VAR','FOR visits=1 TO 2 DO SET_VAR')+' ENDFOR',decl=DECL,prefix=PREFIX)


class CollectionTransferPartialAndLimitTests(unittest.TestCase):
    def test_missing_path_leaf_copies_with_partial_status(self):
        p,_=prepare();raw(p,'SOURCE').values[1].nodes[0].values['VALUE']=rt.UNINITIALIZED;v=p.run();self.assertEqual(v['STATUS'],12311);self.assertEqual(v['TARGET'][1]['nodes'][0]['VALUE'],U)
    def test_missing_node_container_copies_with_partial_status(self):
        p,_=prepare();raw(p,'SOURCE').values[1].nodes[0]=rt.UNINITIALIZED;self.assertEqual(p.run()['STATUS'],12311)
    def test_uninitialized_queue_cell_copies_with_partial_status(self):
        p,_=queues();raw(p,'SOURCE').values[0].initialized=False;self.assertEqual(p.run()['STATUS'],12311);self.assertFalse(raw(p).values[0].initialized)
    def test_unknown_byte_marker_alone_has_success_status(self):
        prefix='TYPE node_t=STRUCTURE value:BYTE ENDSTRUCTURE route_t=PATH NODEDATA=node_t';p,_=prepare(prefix=prefix,seed=False);raw(p,'SOURCE').values[0].append();v=p.run();self.assertEqual(v['STATUS'],0);self.assertEqual(v['TARGET'][0]['nodes'][0]['VALUE'],{'unknown_byte':True})
    def test_whole_missing_resource_array_is_not_an_empty_bank(self):
        p,_=prepare();p._state.values['SOURCE']=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_malformed_known_source_scalar_is_rejected(self):
        p,_=prepare();raw(p,'SOURCE').values[1].nodes[0].values['VALUE']=True
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_oversized_combined_path_contents_reject_before_decode(self):
        p,_=prepare();raw(p,'SOURCE').values[1].nodes=[rt.UNINITIALIZED]*32765
        with patch('karel2py.storage.restore_collection_array',side_effect=AssertionError('premature allocation')),self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_oversized_queue_entry_contents_reject_before_decode(self):
        p,_=queues();q=raw(p,'SOURCE').values[1];q.sequence=17000;q.entries=[(n,n) for n in range(1,17001)]
        with patch('karel2py.storage.restore_collection_array',side_effect=AssertionError('premature allocation')),self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_malformed_receiver_is_validated_before_publication(self):
        p,_=prepare('entry=77 status=88 '+GET);raw(p).values.pop()
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['ENTRY'],p.snapshot()['STATUS']),(77,88));self.assertEqual(p._state.execution.entries,{})
    def test_generic_formal_inherits_actual_collection_schema(self):
        p,_=prepare("work(source,target)",routines="ROUTINE work(first:ARRAY OF route_t;second:ARRAY OF route_t) BEGIN SET_VAR(entry,'','TARGET',first,status) END work");self.assertEqual(p.run()['STATUS'],0)


class CollectionTransferIntegrationTests(unittest.TestCase):
    def test_explicit_dynamic_namespace_bank(self):
        from tests.test_collection_array_archives import context as stored,raw as stored_raw
        ctx=stored();p,_=prepare("GET_VAR(entry,'CACHE','ITEM',target,status)",context=ctx);self.assertEqual(p.run()['STATUS'],0);self.assertEqual(snapshot(raw(p)),snapshot(stored_raw(ctx)))
    def test_explicit_model_context_does_not_convert_collection_data(self):
        from tests.test_joint_interoperability import model_context
        p,_=prepare(context=model_context());self.assertEqual(p.run()['STATUS'],0)
    def test_variable_transfers_create_no_new_root_bindings(self):
        p,_=row();before=dict(p._state.execution.variables.bindings);p.run();self.assertEqual(p._state.execution.variables.bindings,before)
    def test_copied_banks_save_as_ordinary_json_values(self):
        p,_=queues();p.run();data=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(data).to_config(),data)
    def test_copied_bank_can_use_vr_archive_and_restore(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(),variable_archives=rt.VariableArchives());p,_=prepare(GET+" SAVE_DRAM('T',status)",context=ctx);v=p.run();self.assertEqual(v['STATUS'],0);self.assertIn('TARGET',ctx.variable_archives.flash['T']['variables'])
    def test_linked_source_owner_is_resolved_exactly(self):
        sources={'main':'PROGRAM MAIN '+PREFIX+" VAR target:ARRAY[2]OF route_t entry,status:INTEGER ROUTINE seed FROM LIB BEGIN seed GET_VAR(entry,'LIB','SOURCE',target,status) END MAIN",'lib':'PROGRAM LIB '+PREFIX+' VAR source:ARRAY[2]OF route_t s:INTEGER ROUTINE seed BEGIN source[1].count=0 source[2].count=1 APPEND_NODE(source[2],s) source[2][1].value=42 END seed BEGIN END LIB'}
        project=translate_project(sources).instantiate();project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['TARGET'][1]['nodes'][0]['VALUE'],42)
    def test_linked_row_formals_retain_target_original_cells(self):
        sources={'main':'PROGRAM MAIN '+PREFIX+' VAR source,target:ARRAY[2,2]OF route_t ROUTINE work(first:ARRAY[*,*]OF route_t;second:ARRAY[*,*]OF route_t) FROM LIB BEGIN source[2,2].count=1 work(source,target) END MAIN','lib':'PROGRAM LIB '+PREFIX+" VAR entry,status:INTEGER ROUTINE work(first:ARRAY[*,*]OF route_t;second:ARRAY[*,*]OF route_t) BEGIN GET_VAR(entry,'MAIN','SOURCE[2]',second[2],status) END work BEGIN END LIB"}
        project=translate_project(sources).instantiate();project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['TARGET'][1][1]['data']['COUNT'],1)


class CollectionTransferDynamicAndSchemaTests(unittest.TestCase):
    def test_create_set_get_logical_queue_bank(self):
        from tests.test_dynamic_collection_arrays import allocation
        p,_=queues(allocation()+"SET_VAR(entry,'CACHE','ITEM',source,status) GET_VAR(entry,'CACHE','ITEM',target,status)");v=p.run();self.assertEqual(v['STATUS'],0);self.assertEqual(v['SOURCE'],v['TARGET']);self.assertEqual(p._state.execution.variables.metadata['CACHE','ITEM'],{'group':0,'memory_pool':0})
    def test_created_matrix_row_transfers_without_touching_other_row(self):
        from tests.test_dynamic_collection_arrays import allocation
        p,_=queues(allocation(dims=(2,2,0))+"SET_VAR(entry,'CACHE','ITEM[2]',source,status) GET_VAR(entry,'CACHE','ITEM[2]',target,status)");v=p.run();bank=p._state.execution.variables.bindings['CACHE','ITEM'].raw();self.assertEqual(v['STATUS'],0);self.assertFalse(bank.values[0].initialized);self.assertEqual(bank.values[3].entries,[(2,17)])
    def test_created_bank_survives_namespace_rename(self):
        from tests.test_dynamic_collection_arrays import allocation
        p,_=queues(allocation()+"SET_VAR(entry,'CACHE','ITEM',source,status) RENAME_VARS('CACHE','MOVED',status) GET_VAR(entry,'MOVED','ITEM',target,status)");v=p.run();self.assertEqual(v['STATUS'],0);self.assertEqual(v['SOURCE'],v['TARGET'])
    def test_out_of_range_named_row_is_lookup_failure(self):
        p,_=row(ROW_GET.replace('SOURCE[2]','SOURCE[3]'));before=snapshot(raw(p));self.assertEqual(p.run()['STATUS'],1);self.assertEqual(snapshot(raw(p)),before)
    def test_nominal_path_components_are_not_coerced(self):
        prefix=PREFIX+' other_node=STRUCTURE value:INTEGER ENDSTRUCTURE other_route=PATH NODEDATA=other_node PATHHEADER=header_t';p,_=prepare(decl='source:ARRAY[2]OF route_t target:ARRAY[2]OF other_route entry,status,visits:INTEGER',prefix=prefix);self.assertEqual(p.run()['STATUS'],3)
    def test_selected_row_path_headers_do_not_share_source_storage(self):
        p,_=row();p.run();first=raw(p,'SOURCE').values[3].data;second=raw(p).values[3].data;self.assertIsNot(first,second);first.values['COUNT']=99;self.assertEqual(second.values['COUNT'],1)
    def test_generic_formal_inherits_actual_path_schema(self):
        p,_=prepare('work(source)',routines="ROUTINE work(items:ARRAY OF route_t) BEGIN SET_VAR(entry,'','TARGET',items,status) END work");self.assertEqual(p.run()['STATUS'],0)
    def test_raw_generic_resource_codec_still_rejects_live_windows(self):
        p,_=row();root=raw(p,'SOURCE')
        with rt._numeric_scope('pythonic'):
            ref=rt.resource_array_prefix_reference(root,2,root.spec)
            with self.assertRaises(ValueError):typed_value(ref.raw(),ref.spec)
    def test_aliases_inside_source_bank_do_not_escape_in_copied_context(self):
        p,_=row();p.run();state=json.loads(json.dumps(p._state.execution.to_config()));restored=rt.ExecutionContext.from_config(state);source=restored.variables.bindings['T','SOURCE'].raw();target=restored.variables.bindings['T','TARGET'].raw();self.assertIsNot(source.values[3],target.values[3]);self.assertIsNot(source.values[3].nodes,target.values[3].nodes)
    def test_receiver_empty_headerless_paths_are_valid(self):
        prefix='TYPE node_t=STRUCTURE value:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t';p,_=prepare(prefix=prefix,seed=False);self.assertEqual(p.run()['STATUS'],0)


class CollectionTransferPolicyTests(unittest.TestCase):
    def policy(self):return prepare()[1].report['collection_array_transfer_policy']
    def test_report_covers_exact_logical_transfers_and_statuses(self):
        policy=self.policy();self.assertEqual(policy['procedures'],['GET_VAR','SET_VAR']);self.assertIn('Exact concrete selected ARRAY',policy['schema']);self.assertIn('12311',policy['status']);self.assertIn('3 incompatible',policy['status'])
    def test_report_records_capture_identity_and_lifetime(self):
        policy=self.policy();self.assertIn('before later status selectors',policy['capture']);self.assertIn('unselected rows',policy['identity']);self.assertIn('32767',policy['bounds']);self.assertIn('no aliases',policy['persistence'])
    def test_report_links_guide_and_retains_offline_scope(self):
        policy=self.policy();self.assertEqual(policy['guide'],'docs/collection-array-transfers.md');self.assertFalse(policy['controller_validated']);self.assertIn('ordinary resource-copy guards',policy['protection'])


if __name__=='__main__':unittest.main()
