"""Authored original-cell FILE/PATH/QUEUE_TYPE row and plane borrowing."""
import json
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from karel2py.storage import collection_array_payload
from karel2py.dynamic import file_storage_payload
from tests.test_extended_services import compile_program
from tests.test_collection_arrays import TYPES,PATH
from tests.test_file_cancellation import serial
from tests.legacy_numeric_support import translate as legacy_translate

CALL="work(BYNAME('','ITEMS[2]',entry))"
WRITE="ROUTINE work(row:ARRAY OF FILE) BEGIN OPEN FILE row[1]('WO','out') WRITE row[1](17) CLOSE FILE row[1] END work"
GROW='ROUTINE work(row:ARRAY OF route_t) BEGIN APPEND_NODE(row[1],status) row[1].count=1 row[1][1].amount=17 n=row[1][1].amount END work'
QUEUE='ROUTINE work(row:ARRAY OF QUEUE_TYPE) BEGIN INIT_QUEUE(row[1]) APPEND_QUEUE(17,row[1],buffer,seq,status) END work'
DECL='entry,status,n,seq,visits:INTEGER buffer:ARRAY[3]OF INTEGER'


def build(kind='FILE',body=CALL,routines=None,*,shape='2,2',prefix=TYPES,decl='',context=None,**options):
    routines=(WRITE if kind=='FILE' else GROW if kind=='route_t' else QUEUE) if routines is None else routines
    context=rt.ExecutionContext(files=rt.MemoryFiles()) if context is None else context
    return compile_program(body,prefix=prefix,decl=f'items:ARRAY[{shape}]OF {kind} '+DECL+' '+decl,routines=routines,context=context,**options)

def run(*args,**options):return build(*args,**options)[0].run()
def cells(p):return p._state.values['ITEMS'].values


class ResourcePrefixFileTests(unittest.TestCase):
    def test_row_writes_through_original_descriptor(self):
        p,_=build();original=cells(p)[2];p.run();self.assertIs(cells(p)[2],original);self.assertEqual(p._state.execution.files.snapshot(),{'out':b' 17'});self.assertIsNone(cells(p)[0].name)
    def test_plane_uses_complete_coordinates(self):
        p,_=build(shape='2,2,2',routines=WRITE.replace('ARRAY OF FILE','ARRAY[*,*]OF FILE').replace('row[1]','row[2,1]'));p.run();self.assertEqual(cells(p)[6].name,'out');self.assertIsNone(cells(p)[4].name)
    def test_adjacent_static_brackets_capture_row(self):
        p,_=build(shape='2,2,2',body=CALL.replace('ITEMS[2]','ITEMS[2][1]'));p.run();self.assertEqual(cells(p)[4].name,'out')
    def test_optional_named_outer_array_loses_suffix_identity(self):
        p,_=compile_program(CALL,prefix='TYPE bank_t=ARRAY[2,2]OF FILE',decl='items:bank_t '+DECL,routines=WRITE,context=rt.ExecutionContext(files=rt.MemoryFiles()));p.run();self.assertEqual(cells(p)[2].name,'out')
    def test_named_child_components_keep_their_identity(self):
        p,_=build(kind='row_t',prefix='TYPE row_t=ARRAY[2]OF FILE',routines=WRITE.replace('ARRAY OF FILE','ARRAY OF row_t').replace('row[1]','row[1,2]'));p.run();self.assertEqual(cells(p)[2].values[1].name,'out')
    def test_live_row_forwards_as_ordinary_reference(self):
        p,_=build(routines=WRITE.replace('work','child')+' ROUTINE work(row:ARRAY OF FILE) BEGIN child(row) END work');p.run();self.assertEqual(cells(p)[2].name,'out')
    def test_individual_descriptor_forwards_without_copy(self):
        routines="ROUTINE child(f:FILE) BEGIN OPEN FILE f('WO','out') WRITE f(17) CLOSE FILE f END child ROUTINE work(row:ARRAY OF FILE) BEGIN child(row[1]) END work"
        p,_=build(routines=routines);p.run();self.assertEqual(cells(p)[2].name,'out')
    def test_two_captures_keep_same_descriptor(self):
        routines="ROUTINE work(left,right:ARRAY OF FILE) BEGIN OPEN FILE left[1]('WO','out') WRITE right[1](17) CLOSE FILE left[1] END work"
        p,_=build(body="work(BYNAME('','ITEMS[2]',entry),BYNAME('','ITEMS[2]',entry))",routines=routines);p.run();self.assertEqual(p._state.execution.files.snapshot()['out'],b' 17')
    def test_open_descriptor_can_be_borrowed_and_closed(self):
        p,_=build(body="OPEN FILE items[2,1]('WO','out') "+CALL,routines='ROUTINE work(row:ARRAY OF FILE) BEGIN WRITE row[1](17) CLOSE FILE row[1] END work');p.run();self.assertIsNone(cells(p)[2].owner);self.assertEqual(cells(p)[2].position,3)
    def test_capture_does_not_allocate_replacement_descriptors(self):
        p,_=build();a=p._state.values['ITEMS'];original=cells(p)[2]
        with rt._numeric_scope('pythonic'),patch.object(rt.Array,'__init__',side_effect=AssertionError('Unexpected ARRAY allocation')),patch.object(rt.FileHandle,'__init__',side_effect=AssertionError('Unexpected FILE allocation')):
            view=rt.resource_array_prefix_reference(a,2,a.spec).raw();self.assertIs(view.values[0],original)
    def test_attributes_and_binary_output_use_original_cell(self):
        routines="ROUTINE work(row:ARRAY OF FILE) BEGIN SET_FILE_ATR(row[1],ATR_REVERSE) OPEN FILE row[1]('WB','out') WRITE row[1](17) CLOSE FILE row[1] END work"
        p,_=build(routines=routines);p.run();self.assertTrue(cells(p)[2].reverse);self.assertEqual(p._state.execution.files.snapshot()['out'],b'\x00\x00\x00\x11')
    def test_pause_resume_retains_descriptor_and_window(self):
        p,_=build(cooperative=True,routines="ROUTINE work(row:ARRAY OF FILE) BEGIN OPEN FILE row[1]('WO','out') PAUSE WRITE row[1](17) CLOSE FILE row[1] END work")
        with self.assertRaises(rt.KarelPause):p.run()
        original=cells(p)[2];self.assertIsNotNone(original.owner);p.resume();self.assertIs(cells(p)[2],original);self.assertIsNone(original.owner)
    def test_stop_keeps_existing_explicit_close_contract(self):
        p,_=build(cooperative=True,routines="ROUTINE work(row:ARRAY OF FILE) BEGIN OPEN FILE row[1]('WO','out') PAUSE CLOSE FILE row[1] END work")
        with self.assertRaises(rt.KarelPause):p.run()
        handle=cells(p)[2];p.stop();self.assertIsNotNone(handle.owner);handle.owner.close(handle)
    def test_root_storage_replacement_does_not_retarget_captured_row(self):
        p,_=build(routines="ROUTINE change:INTEGER FROM HOST "+WRITE.replace('work(row:ARRAY OF FILE)','work(row:ARRAY OF FILE;ignored:INTEGER)'),body="work(BYNAME('','ITEMS[2]',entry),change())")
        old=list(cells(p));p._state.execution.externals[('HOST','CHANGE')]=lambda:(setattr(p._state.values['ITEMS'],'values',[rt.FileHandle() for _ in range(4)]) or 0);p.run();self.assertEqual(old[2].name,'out');self.assertIsNone(cells(p)[2].name)


class ResourcePrefixPathTests(unittest.TestCase):
    def test_row_appends_into_original_path(self):
        p,_=build('route_t');value=cells(p)[2];v=p.run();self.assertIs(cells(p)[2],value);self.assertEqual(v['N'],17);self.assertEqual(v['ITEMS'][1][0]['nodes'],[{'AMOUNT':17}])
    def test_plane_node_chains_use_original_cells(self):
        routines=GROW.replace('ARRAY OF route_t','ARRAY[*,*]OF route_t').replace('row[1][1]','row[2,1][1]').replace('row[1]','row[2,1]')
        p,_=build('route_t',shape='2,2,2',routines=routines);self.assertEqual(p.run()['N'],17);self.assertEqual(len(cells(p)[6].nodes),1)
    def test_header_fields_use_original_path(self):
        p,_=build('route_t');p.run();self.assertEqual(cells(p)[2].data.values['COUNT'],1)
    def test_path_node_record_alias_survives_borrowed_call(self):
        routines='ROUTINE child(value:INTEGER) BEGIN value=99 END child '+GROW.replace('n=row[1][1].amount','child(row[1][1].amount) n=row[1][1].amount')
        p,_=build('route_t',routines=routines);self.assertEqual(p.run()['N'],99)
    def test_default_path_array_can_be_borrowed(self):
        p,_=build('PATH',routines='ROUTINE work(row:ARRAY OF PATH) BEGIN APPEND_NODE(row[1],status) n=PATH_LEN(row[1]) END work');self.assertEqual(p.run()['N'],1)
    def test_path_contents_are_preserved_at_capture(self):
        p,_=build('route_t',body='APPEND_NODE(items[2,1],status) items[2,1][1].amount=7 '+CALL,routines='ROUTINE work(row:ARRAY OF route_t) BEGIN n=row[1][1].amount END work');self.assertEqual(p.run()['N'],7)
    def test_partial_node_data_is_not_filled_or_copied(self):
        p,_=build('route_t',body='APPEND_NODE(items[2,1],status) '+CALL,routines='ROUTINE work(row:ARRAY OF route_t) BEGIN n=PATH_LEN(row[1]) END work');p.run();self.assertIs(cells(p)[2].nodes[0].values['AMOUNT'],rt.UNINITIALIZED)
    def test_copying_individual_path_retains_existing_copy_contract(self):
        p,_=build('route_t',decl='other:route_t',body='APPEND_NODE(other,status) other[1].amount=7 '+CALL,routines='ROUTINE work(row:ARRAY OF route_t) BEGIN row[1]=other row[1][1].amount=9 END work');self.assertEqual(p.run()['OTHER']['nodes'][0]['AMOUNT'],7);self.assertEqual(cells(p)[2].nodes[0].values['AMOUNT'],9)
    def test_path_context_json_preserves_original_root(self):
        p,_=build('route_t');p.run();data=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(data).to_config(),data)
    def test_path_live_view_is_not_a_generic_collection_codec_value(self):
        p,_=build('route_t',routines='ROUTINE work(row:ARRAY OF route_t) BEGIN inspect(row) END work ROUTINE inspect(row:ARRAY OF route_t) FROM HOST');views=[];p._state.execution.externals[('HOST','INSPECT')]=lambda ref:views.append(ref.raw());p.run()
        with self.assertRaises(ValueError):collection_array_payload(views[0].spec,views[0])


class ResourcePrefixQueueTests(unittest.TestCase):
    def test_queue_row_updates_original_cell_and_buffer(self):
        p,_=build('QUEUE_TYPE');q=cells(p)[2];v=p.run();self.assertIs(cells(p)[2],q);self.assertEqual(q.entries,[(1,17)]);self.assertIs(q.buffer,p._state.values['BUFFER']);self.assertEqual(v['BUFFER'],[17,0,0])
    def test_queue_plane_selects_exact_cell(self):
        p,_=build('QUEUE_TYPE',shape='2,2,2',routines=QUEUE.replace('ARRAY OF QUEUE_TYPE','ARRAY[*,*]OF QUEUE_TYPE').replace('row[1]','row[2,1]'));p.run();self.assertTrue(cells(p)[6].initialized);self.assertFalse(cells(p)[4].initialized)
    def test_repeat_capture_retains_backing_identity(self):
        routines='ROUTINE work(row:ARRAY OF QUEUE_TYPE) BEGIN APPEND_QUEUE(17,row[1],buffer,seq,status) END work'
        p,_=build('QUEUE_TYPE',body='INIT_QUEUE(items[2,1]) '+CALL+' '+CALL,routines=routines);p.run();self.assertEqual(cells(p)[2].entries,[(1,17),(2,17)])
    def test_initialization_of_other_row_stays_independent(self):
        p,_=build('QUEUE_TYPE');p.run();self.assertTrue(cells(p)[2].initialized);self.assertTrue(all(not q.initialized for q in cells(p) if q is not cells(p)[2]))
    def test_queue_forwards_with_original_buffer_link(self):
        routines=QUEUE.replace('work','child')+' ROUTINE work(row:ARRAY OF QUEUE_TYPE) BEGIN child(row) END work';p,_=build('QUEUE_TYPE',routines=routines);p.run();self.assertIs(cells(p)[2].buffer,p._state.values['BUFFER'])
    def test_existing_queue_entries_survive_capture(self):
        p,_=build('QUEUE_TYPE',body='INIT_QUEUE(items[2,1]) APPEND_QUEUE(7,items[2,1],buffer,seq,status) '+CALL,routines='ROUTINE work(row:ARRAY OF QUEUE_TYPE) BEGIN GET_QUEUE(row[1],buffer,n,seq,status) END work');self.assertEqual(p.run()['N'],7)
    def test_json_restores_values_without_live_buffer_link(self):
        p,_=build('QUEUE_TYPE');p.run();data=json.loads(json.dumps(p._state.execution.to_config()));c=rt.ExecutionContext.from_config(data);self.assertEqual(c.to_config(),data);self.assertIsNone(c.variables.bindings['T','ITEMS'].raw().values[2].buffer)
    def test_queue_window_is_not_a_serializable_alias(self):
        p,_=build('QUEUE_TYPE',routines='ROUTINE work(row:ARRAY OF QUEUE_TYPE) BEGIN inspect(row) END work ROUTINE inspect(row:ARRAY OF QUEUE_TYPE) FROM HOST');views=[];p._state.execution.externals[('HOST','INSPECT')]=lambda ref:views.append(ref.raw());p.run()
        with self.assertRaises(ValueError):collection_array_payload(views[0].spec,views[0])


class ResourcePrefixLookupTests(unittest.TestCase):
    def test_dynamic_file_allocation_supports_row_borrowing(self):
        p,_=compile_program("CREATE_VAR('CACHE','ITEMS','','ARRAY OF FILE',0,2,2,0,status) work(BYNAME('CACHE','ITEMS[2]',entry))",decl=DECL,routines=WRITE,context=rt.ExecutionContext(files=rt.MemoryFiles()));p.run();self.assertEqual(p._state.execution.variables.bindings['CACHE','ITEMS'].raw().values[2].name,'out')
    def test_dynamic_path_allocation_supports_row_borrowing(self):
        p,_=compile_program("CREATE_VAR('CACHE','ITEMS','','ARRAY OF route_t',0,2,2,0,status) work(BYNAME('CACHE','ITEMS[2]',entry))",prefix=TYPES,decl=DECL,routines=GROW);self.assertEqual(p.run()['N'],17)
    def test_dynamic_queue_allocation_supports_row_borrowing(self):
        p,_=compile_program("CREATE_VAR('CACHE','ITEMS','','ARRAY OF QUEUE_TYPE',0,2,2,0,status) work(BYNAME('CACHE','ITEMS[2]',entry))",decl=DECL,routines=QUEUE);p.run();self.assertTrue(p._state.execution.variables.bindings['CACHE','ITEMS'].raw().values[2].initialized)
    def test_namespace_rename_does_not_retarget_capture(self):
        body="CREATE_VAR('CACHE','ITEMS','','ARRAY OF FILE',0,2,2,0,status) work(BYNAME('CACHE','ITEMS[2]',entry),later)"
        routines="ROUTINE later:INTEGER BEGIN RENAME_VAR('CACHE','ITEMS','KEPT',status) RETURN(0) END later "+WRITE.replace('work(row:ARRAY OF FILE)','work(row:ARRAY OF FILE;ignored:INTEGER)')
        p,_=compile_program(body,decl=DECL,routines=routines,context=rt.ExecutionContext(files=rt.MemoryFiles()));p.run();bindings=p._state.execution.variables.bindings;self.assertNotIn(('CACHE','ITEMS'),bindings);self.assertEqual(bindings['CACHE','KEPT'].raw().values[2].name,'out')
    def test_explicit_external_root_binding_is_used(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles())
        with rt._numeric_scope('pythonic'):a=rt.Array(('ARRAY',(2,2),('FILE',)))
        ctx.variables.bind('CACHE','HANDLES',rt.Reference(a.spec,{'value':a},'value'));p,_=build(body="work(BYNAME('CACHE','HANDLES[2]',entry))",context=ctx);p.run();self.assertEqual(a.values[2].name,'out')
    def test_blank_program_name_uses_calling_root(self):
        p,_=build();self.assertGreater(p.run()['ENTRY'],0)
    def test_repeated_path_reuses_entry_cache(self):
        p,_=build(body=CALL+' visits=entry '+CALL,routines='ROUTINE work(row:ARRAY OF FILE) BEGIN n=ARRAY_LEN(row) END work');v=p.run();self.assertEqual(v['VISITS'],v['ENTRY']);self.assertEqual(len(p._state.execution.entries),1)
    def test_default_context_resolution_does_not_gain_prefix_references(self):
        p,_=build()
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):p._state.execution.resolve(p._state,'T','ITEMS[2]')


class ResourcePrefixGuardTests(unittest.TestCase):
    def reject(self,*,path='ITEMS[2]',kind='FILE',routines=WRITE,change=None):
        p,_=build(kind,body="entry=77 work(BYNAME('','"+path+"',entry))",routines=routines)
        if change:change(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['ENTRY'],77);self.assertEqual(p._state.execution.entries,{})
    def test_zero_index_preserves_entry_and_cache(self):self.reject(path='ITEMS[0]')
    def test_high_index_preserves_entry_and_cache(self):self.reject(path='ITEMS[3]')
    def test_leaf_type_mismatch_preserves_entry_and_cache(self):self.reject(routines=GROW)
    def test_named_suffix_identity_is_not_invented(self):
        p,_=build(prefix='TYPE row_t=ARRAY[2]OF FILE',routines=WRITE.replace('ARRAY OF FILE','row_t'),body="entry=77 "+CALL)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['ENTRY'],77);self.assertEqual(p._state.execution.entries,{})
    def test_ordinary_file_prefix_argument_remains_rejected(self):
        for kind,routines in (('FILE',WRITE),):
            with self.subTest(kind=kind),self.assertRaises(TranslationError):build(kind,body='work(items[2])',routines=routines)
    def test_grouped_resource_view_remains_rejected(self):
        with self.assertRaises(TranslationError):build(routines=WRITE.replace('work','child')+' ROUTINE work(row:ARRAY OF FILE) BEGIN child((row)) END work')
    def test_whole_resource_array_assignment_remains_rejected(self):
        with self.assertRaises(TranslationError):build(routines='ROUTINE work(row:ARRAY OF FILE) BEGIN row=items END work')
    def test_resource_array_return_remains_rejected(self):
        with self.assertRaises(TranslationError):build(prefix='TYPE row_t=ARRAY[2]OF FILE',routines='ROUTINE work(row:ARRAY OF FILE):row_t BEGIN RETURN(row) END work')
    def test_resource_prefix_read_remains_rejected(self):
        with self.assertRaises(TranslationError):build(routines='ROUTINE work(row:ARRAY OF FILE) BEGIN READ(row) END work')
    def test_resource_prefix_write_remains_rejected(self):
        with self.assertRaises(TranslationError):build(routines='ROUTINE work(row:ARRAY OF FILE) BEGIN WRITE(row) END work')
    def test_resource_for_counter_remains_rejected(self):
        with self.assertRaises(TranslationError):build(routines='ROUTINE work(row:ARRAY OF FILE) BEGIN FOR row[1]=1 TO 2 DO n=1 ENDFOR END work')
    def test_context_get_var_does_not_copy_resource_prefix(self):
        with self.assertRaises(TranslationError):build(body="entry=77 GET_VAR(entry,'','ITEMS[2]',other,status)",decl='other:ARRAY[2]OF FILE',routines='')
    def test_malformed_unselected_descriptor_rejects_before_entry(self):self.reject(change=lambda p:cells(p).__setitem__(0,7))
    def test_duplicate_descriptor_ownership_is_rejected(self):self.reject(change=lambda p:cells(p).__setitem__(1,cells(p)[0]))
    def test_wrong_container_shape_is_rejected(self):self.reject(change=lambda p:setattr(p._state.values['ITEMS'],'shape',(4,)))
    def test_wrong_container_storage_type_is_rejected(self):self.reject(change=lambda p:setattr(p._state.values['ITEMS'],'values',tuple(cells(p))))
    def test_wrong_container_length_is_rejected(self):self.reject(change=lambda p:cells(p).pop())
    def test_wrong_path_cell_type_is_rejected(self):self.reject(kind='route_t',routines=GROW,change=lambda p:cells(p).__setitem__(0,7))
    def test_malformed_unselected_path_nodes_are_rejected(self):self.reject(kind='route_t',routines=GROW,change=lambda p:setattr(cells(p)[0],'nodes',[7]))
    def test_malformed_queue_state_is_rejected(self):self.reject(kind='QUEUE_TYPE',routines=QUEUE,change=lambda p:setattr(cells(p)[0],'sequence',-1))
    def test_strict_runtime_does_not_gain_views(self):
        with rt._numeric_scope('pythonic'):a=rt.Array(('ARRAY',(2,2),('FILE',)))
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.resource_array_prefix_reference(a,1,a.spec)
    def test_data_capture_helper_remains_data_only(self):
        with rt._numeric_scope('pythonic'):
            a=rt.Array(('ARRAY',(2,2),('FILE',)))
            with self.assertRaises(rt.KarelRuntimeError):rt.array_prefix_target(a,1,a.spec)
    def test_created_file_codec_does_not_accept_live_window(self):
        p,_=build(routines='ROUTINE work(row:ARRAY OF FILE) BEGIN inspect(row) END work ROUTINE inspect(row:ARRAY OF FILE) FROM HOST');views=[];p._state.execution.externals[('HOST','INSPECT')]=lambda ref:views.append(ref.raw());p.run()
        with self.assertRaises(ValueError):file_storage_payload(views[0].spec,views[0])


class ResourcePrefixOwnershipTests(unittest.TestCase):
    def test_selected_queue_buffer_cannot_receive_byname_entry(self):
        body="INIT_QUEUE(items[2,1]) APPEND_QUEUE(7,items[2,1],buffer,seq,status) work(BYNAME('','ITEMS[2]',buffer[1]))"
        p,_=build('QUEUE_TYPE',body=body,routines='ROUTINE work(row:ARRAY OF QUEUE_TYPE) BEGIN END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps entry'):p.run()
        self.assertEqual(p.snapshot()['BUFFER'],[7,0,0]);self.assertEqual(cells(p)[2].entries,[(1,7)]);self.assertEqual(p._state.execution.entries,{})
    def test_unselected_queue_buffer_can_receive_byname_entry(self):
        body="INIT_QUEUE(items[1,1]) APPEND_QUEUE(7,items[1,1],other,seq,status) INIT_QUEUE(items[2,1]) APPEND_QUEUE(17,items[2,1],buffer,seq,status) work(BYNAME('','ITEMS[2]',other[1]))"
        p,_=build('QUEUE_TYPE',decl='other:ARRAY[3]OF INTEGER',body=body,routines='ROUTINE work(row:ARRAY OF QUEUE_TYPE) BEGIN END work');p.run();self.assertEqual(p.snapshot()['BUFFER'],[17,0,0]);self.assertEqual(p.snapshot()['OTHER'][0],1)
    def test_path_header_entry_overlap_is_rejected(self):
        p,_=build('route_t',body="items[2,1].count=77 work(BYNAME('','ITEMS[2]',items[2,1].count))",routines='ROUTINE work(row:ARRAY OF route_t) BEGIN END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps entry'):p.run()
        self.assertEqual(cells(p)[2].data.values['COUNT'],77);self.assertEqual(p._state.execution.entries,{})
    def test_path_node_entry_overlap_is_rejected(self):
        p,_=build('route_t',body="APPEND_NODE(items[2,1],status) items[2,1][1].amount=77 work(BYNAME('','ITEMS[2]',items[2,1][1].amount))",routines='ROUTINE work(row:ARRAY OF route_t) BEGIN END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps entry'):p.run()
        self.assertEqual(cells(p)[2].nodes[0].values['AMOUNT'],77)
    def test_late_list_resize_fails_before_file_open(self):
        p,_=build(body="work(BYNAME('','ITEMS[2]',entry),later())",routines='ROUTINE later:INTEGER FROM HOST '+WRITE.replace('work(row:ARRAY OF FILE)','work(row:ARRAY OF FILE;ignored:INTEGER)'));p._state.execution.externals[('HOST','LATER')]=lambda:(cells(p).pop() and 0)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.execution.files.snapshot(),{})
    def test_absent_file_backend_is_not_created_by_borrowing(self):
        ctx=rt.ExecutionContext();p,_=build(context=ctx,routines='ROUTINE work(row:ARRAY OF FILE) BEGIN n=ARRAY_LEN(row) END work');self.assertEqual(p.run()['N'],2);self.assertIsNone(ctx.files)
    def test_live_file_prefix_omitted_from_saved_static_variables(self):
        p,_=build();p.run();data=p._state.execution.to_config();self.assertFalse(any(row['path']=='ITEMS' for row in data['variables']))
    def test_dynamic_file_prefix_retains_closed_creation_marker(self):
        p,_=compile_program("CREATE_VAR('CACHE','ITEMS','','ARRAY OF FILE',0,2,2,0,status) work(BYNAME('CACHE','ITEMS[2]',entry))",decl=DECL,routines=WRITE,context=rt.ExecutionContext(files=rt.MemoryFiles()));p.run();data=p._state.execution.to_config();row=next(r for r in data['variables'] if r['program']=='CACHE');self.assertEqual(row['value'],{'closed':True});self.assertEqual(row['creation'],{'group':0,'memory_pool':0})
    def test_dynamic_borrowing_does_not_reserve_more_descriptors(self):
        from karel2py.dynamic import reserved
        p,_=compile_program("CREATE_VAR('CACHE','ITEMS','','ARRAY OF FILE',0,2,2,0,status) work(BYNAME('CACHE','ITEMS[2]',entry))",decl=DECL,routines=WRITE,context=rt.ExecutionContext(files=rt.MemoryFiles()));p.run();self.assertEqual(reserved(p._state.execution.variables),4)
    def test_combined_path_contents_are_bounded_before_entry(self):
        p,_=build('route_t',body='entry=77 '+CALL,routines='ROUTINE work(row:ARRAY OF route_t) BEGIN END work');path=cells(p)[0];node=rt.Structure(path.node_spec);path.nodes=[node]*32767
        with self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):p.run()
        self.assertEqual(p.snapshot()['ENTRY'],77);self.assertEqual(p._state.execution.entries,{})
    def test_resource_carrier_is_exact_array_with_original_window(self):
        p,_=build();a=p._state.values['ITEMS']
        with rt._numeric_scope('pythonic'):
            view=rt.resource_array_prefix_reference(a,2,a.spec);self.assertIs(type(view),rt.Reference);self.assertIs(type(view.raw()),rt.Array);self.assertIs(type(view.raw().values),rt._ArrayWindow);self.assertIs(rt.index_reference(view.raw(),1).storage,cells(p))


class ResourcePrefixCooperativeTests(unittest.TestCase):
    def pending(self):
        bank,ctx=serial()
        source="PROGRAM MAIN VAR items:ARRAY[2,2]OF FILE entry,n,status:INTEGER done:BOOLEAN ROUTINE work(row:ARRAY OF FILE) BEGIN OPEN FILE row[1]('RO','P2:') n=77 READ row[1](n,CR) status=IO_STATUS(row[1]) CLOSE FILE row[1] done=TRUE END work BEGIN work(BYNAME('','ITEMS[2]',entry)) END MAIN"
        project=translate_project({'main':source}).instantiate(context=ctx);p=project.programs['MAIN'];project.scheduler.start('MAIN');h=p._state.values['ITEMS'].values[2]
        for _ in range(80):
            project.scheduler.step()
            if h._read_operation is not None:return project,p,h,bank
        raise AssertionError('Borrowed FILE READ did not become active')
    def test_pending_read_completes_on_original_descriptor(self):
        project,p,h,bank=self.pending();bank.feed(2,b'17\n');project.scheduler.run();self.assertEqual(p.snapshot()['N'],17);self.assertIsNone(h.owner);self.assertIsNone(h._read_operation)
    def test_pending_read_cancellation_preserves_output_and_input(self):
        project,p,h,bank=self.pending();rt.cancel_file(p._state,h);project.scheduler.run();self.assertEqual((p.snapshot()['N'],p.snapshot()['STATUS']),(77,6));self.assertEqual(bank._pending,{})
    def test_pause_resume_retains_pending_borrowed_handle(self):
        project,p,h,bank=self.pending();p.pause()
        for _ in range(40):
            project.scheduler.step()
            if p.task_state=='paused':break
        self.assertEqual(p.task_state,'paused');bank.feed(2,b'17\n');self.assertIsNotNone(h._read_operation);project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(p.snapshot()['N'],17)
    def test_stop_releases_read_without_implicit_close(self):
        project,p,h,bank=self.pending();project.scheduler.stop('MAIN');self.assertIsNone(h._read_operation);self.assertEqual(bank._pending,{});self.assertIs(h.owner,bank);bank.close(h)


class ResourcePrefixLinkedTests(unittest.TestCase):
    def test_linked_file_formal_keeps_descriptor_identity(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles());project=translate_project({'main':"PROGRAM MAIN VAR items:ARRAY[2,2]OF FILE entry:INTEGER ROUTINE work(row:ARRAY OF FILE) FROM LIB BEGIN work(BYNAME('','ITEMS[2]',entry)) END MAIN",'lib':'PROGRAM LIB '+WRITE+' BEGIN END LIB'}).instantiate(context=ctx);h=project.programs['MAIN']._state.values['ITEMS'].values[2];project.run('MAIN');self.assertEqual(h.position,3);self.assertIsNone(h.owner);self.assertEqual(ctx.files.snapshot()['out'],b' 17')
    def test_linked_blank_program_uses_calling_root_prefix(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles());project=translate_project({'main':"PROGRAM MAIN VAR items:ARRAY[2,2]OF FILE ROUTINE work FROM LIB BEGIN work END MAIN",'lib':"PROGRAM LIB VAR entry:INTEGER "+WRITE.replace('work','fill')+" ROUTINE work BEGIN fill(BYNAME('','ITEMS[2]',entry)) END work BEGIN END LIB"}).instantiate(context=ctx);project.run('MAIN');self.assertEqual(ctx.files.snapshot()['out'],b' 17')
    def test_linked_path_formal_mutates_calling_root(self):
        main='PROGRAM MAIN '+TYPES+" VAR items:ARRAY[2,2]OF route_t entry,status,n:INTEGER ROUTINE work(row:ARRAY OF route_t) FROM LIB BEGIN work(BYNAME('','ITEMS[2]',entry)) END MAIN"
        lib='PROGRAM LIB '+TYPES+' VAR status,n:INTEGER '+GROW+' BEGIN END LIB';project=translate_project({'main':main,'lib':lib}).instantiate();project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['ITEMS'][1][0]['nodes'],[{'AMOUNT':17}])
    def test_linked_declared_resource_schemas_remain_exact(self):
        with self.assertRaisesRegex(ValueError,'type mismatch'):translate_project({'main':'PROGRAM MAIN ROUTINE work(row:ARRAY OF FILE) FROM LIB BEGIN END MAIN','lib':'PROGRAM LIB ROUTINE work(row:ARRAY OF QUEUE_TYPE) BEGIN END work BEGIN END LIB'}).instantiate()


class ResourcePrefixAdditionalGuards(unittest.TestCase):
    def test_path_header_integer_cannot_act_as_for_counter(self):
        with self.assertRaises(TranslationError):build('route_t',routines='ROUTINE work(row:ARRAY OF route_t) BEGIN FOR row[1].count=1 TO 2 DO n=1 ENDFOR END work')
    def test_named_inner_array_identity_mismatch_is_rejected(self):
        p,_=build(kind='first_t',prefix='TYPE first_t=ARRAY[2]OF FILE second_t=ARRAY[2]OF FILE',routines='ROUTINE work(row:ARRAY OF second_t) BEGIN END work')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_wrong_path_schema_is_rejected_before_entry(self):
        prefix=TYPES+' TYPE other_node=STRUCTURE amount:REAL ENDSTRUCTURE other_path=PATH NODEDATA=other_node'
        p,_=build('route_t',prefix=prefix,routines='ROUTINE work(row:ARRAY OF other_path) BEGIN END work',body='entry=77 '+CALL)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['ENTRY'],77)
    def test_resource_source_prefix_cannot_be_used_as_get_var_data_value(self):
        with self.assertRaises(TranslationError):build(routines="ROUTINE work(row:ARRAY OF FILE) BEGIN SET_VAR(entry,'','ITEMS',row,status) END work")
    def test_queue_byname_whole_reference_protects_backing_buffer(self):
        p,_=compile_program("INIT_QUEUE(q) APPEND_QUEUE(7,q,buffer,seq,status) work(BYNAME('','Q',buffer[1]))",decl='q:QUEUE_TYPE buffer:ARRAY[3]OF INTEGER n,seq,status:INTEGER',routines='ROUTINE work(value:QUEUE_TYPE) BEGIN END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps entry'):p.run()
        self.assertEqual(p.snapshot()['BUFFER'],[7,0,0])


class ResourcePrefixReportTests(unittest.TestCase):
    def test_report_describes_three_resource_kinds_and_original_cells(self):
        _,r=build();policy=r.report['resource_prefix_reference_policy'];self.assertIn('FILE/PATH/QUEUE_TYPE',policy['syntax']);self.assertIn('without allocating',policy['capture']);self.assertEqual(policy['guide'],'docs/resource-prefix-references.md');self.assertFalse(policy['controller_validated'])
    def test_report_preserves_copy_codec_and_lifetime_boundaries(self):
        _,r=build();policy=r.report['resource_prefix_reference_policy'];self.assertIn('queue backing',policy['protection']);self.assertIn('grouped copies',policy['boundary']);self.assertIn('not serialized',policy['persistence'])
    def test_data_reference_policy_points_to_resource_contract(self):
        _,r=build();self.assertIn('resource_prefix_reference_policy',r.report['array_prefix_reference_policy']['limits'])


class ResourcePrefixSchemaGuards(unittest.TestCase):
    def test_malformed_expected_schema_is_source_located(self):
        p,_=build();a=p._state.values['ITEMS']
        with rt._numeric_scope('pythonic'):
            for spec in (None,(),('ARRAY',),('ARRAY',(2,2),None)):
                with self.subTest(spec=spec),self.assertRaisesRegex(rt.KarelRuntimeError,'line 23'):rt.resource_array_prefix_reference(a,2,spec,23)
    def test_cyclic_expected_array_metadata_is_bounded(self):
        p,_=build();cycle=['ARRAY',2,None];cycle[2]=cycle;spec=('ARRAY',2,cycle)
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.resource_array_prefix_reference(p._state.values['ITEMS'],2,spec)
    def test_malformed_actual_schema_is_rejected_before_shape_use(self):
        p,_=build();a=p._state.values['ITEMS'];expected=a.spec;a.spec=('ARRAY',)
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.resource_array_prefix_reference(a,2,expected)
    def test_noncanonical_named_file_component_is_rejected(self):
        p,_=build();a=p._state.values['ITEMS'];a.spec=(*a.spec,'lower_case')
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'canonical'):rt.resource_array_prefix_reference(a,2,a.spec)


if __name__=='__main__':unittest.main()
