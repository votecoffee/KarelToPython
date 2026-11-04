"""Direct FILE prefix arguments borrow exact original descriptor cells."""
import json
import struct
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate,translate_project
from karel2py.lexer import TranslationError
from karel2py.storage import typed_value
from tests.test_resource_prefix_references import build as resource_build,cells,WRITE,DECL
from tests.test_file_cancellation import serial
from tests.test_extended_services import compile_program
from tests.test_collection_arrays import TYPES


def build(body='work(items[2])',routines=WRITE,**options):
    return resource_build(body=body,routines=routines,**options)


def run(*args,**options):return build(*args,**options)[0].run()


class DirectFileSelectionTests(unittest.TestCase):
    def test_row_keeps_original_descriptor(self):
        p,_=build();original=cells(p)[2];p.run();self.assertIs(cells(p)[2],original);self.assertEqual(original.name,'out');self.assertEqual(p._state.execution.files.snapshot()['out'],b' 17')
    def test_first_row_does_not_touch_second_row(self):
        p,_=build(body='work(items[1])');p.run();self.assertEqual(cells(p)[0].name,'out');self.assertIsNone(cells(p)[2].name)
    def test_plane_retains_both_remaining_dimensions(self):
        routine=WRITE.replace('ARRAY OF FILE','ARRAY[*,*]OF FILE').replace('row[1]','row[2,1]');p,_=build(shape='2,2,2',routines=routine);p.run();self.assertEqual(cells(p)[6].name,'out');self.assertIsNone(cells(p)[4].name)
    def test_row_from_cube_uses_comma_coordinates(self):
        p,_=build(shape='2,2,2',body='work(items[2,1])');p.run();self.assertEqual(cells(p)[4].name,'out')
    def test_row_from_cube_uses_adjacent_brackets(self):
        p,_=build(shape='2,2,2',body='work(items[2][1])');p.run();self.assertEqual(cells(p)[4].name,'out')
    def test_grouping_base_preserves_storage(self):
        p,_=build(body='work((items)[2])');p.run();self.assertEqual(cells(p)[2].name,'out')
    def test_named_outer_suffix_is_anonymous(self):
        p,r=compile_program('work(items[2])',prefix='TYPE bank_t=ARRAY[2,2]OF FILE',decl='items:bank_t '+DECL,routines=WRITE,context=rt.ExecutionContext(files=rt.MemoryFiles()));p.run();self.assertEqual(len(r.report['file_prefix_arguments'][0]['selected_type_spec']),3)
    def test_named_inner_components_keep_identity(self):
        routine=WRITE.replace('ARRAY OF FILE','ARRAY OF row_t').replace('row[1]','row[1,2]');p,_=build(kind='row_t',prefix='TYPE row_t=ARRAY[2]OF FILE',routines=routine);p.run();self.assertEqual(cells(p)[2].values[1].name,'out')
    def test_prefix_crosses_named_component_boundary(self):
        p,_=compile_program('work(items[2,1])',prefix='TYPE plane_t=ARRAY[2,2]OF FILE',decl='items:ARRAY[2]OF plane_t '+DECL,routines=WRITE,context=rt.ExecutionContext(files=rt.MemoryFiles()));p.run();self.assertEqual(cells(p)[1].values[0].name,'out')
    def test_scalar_file_type_alias_retains_resource_domain(self):
        p,_=build(kind='stream_t',prefix='TYPE stream_t=FILE');p.run();self.assertEqual(cells(p)[2].name,'out')
    def test_forward_type_chain_retains_file_cells(self):
        p,_=compile_program('work(items[2])',prefix='TYPE bank_t=ARRAY[2,2]OF file_t file_t=FILE',decl='items:bank_t '+DECL,routines=WRITE,context=rt.ExecutionContext(files=rt.MemoryFiles()));p.run();self.assertEqual(cells(p)[2].name,'out')
    def test_local_bank_can_be_borrowed(self):
        routine=WRITE+' ROUTINE launch VAR local:ARRAY[2,2]OF FILE BEGIN work(local[2]) END launch'
        p,_=build(body='launch',routines=routine);p.run();self.assertEqual(p._state.execution.files.snapshot()['out'],b' 17');self.assertEqual(p._state.local_frames,[])
    def test_runtime_global_wildcard_shape_is_explicit(self):
        result=translate('PROGRAM T VAR items:ARRAY[*,2]OF FILE '+WRITE+' BEGIN work(items[2]) END T',array_shapes={'ITEMS':[2,2]});ns={};exec(result.python_source,ns);p=ns['Program'](context=rt.ExecutionContext(files=rt.MemoryFiles()));p.run();self.assertEqual(cells(p)[2].name,'out')
    def test_capture_allocates_no_new_resources(self):
        p,_=build()
        with patch.object(rt.Array,'__init__',side_effect=AssertionError('Unexpected ARRAY allocation')),patch.object(rt.FileHandle,'__init__',side_effect=AssertionError('Unexpected FILE allocation')):p.run()
    def test_same_row_arguments_alias_same_handle(self):
        routine="ROUTINE work(left,right:ARRAY OF FILE) BEGIN OPEN FILE left[1]('WO','out') WRITE right[1](17) CLOSE FILE right[1] END work"
        p,_=build(body='work(items[2],items[2])',routines=routine);p.run();self.assertEqual(cells(p)[2].position,3)
    def test_different_rows_remain_distinct(self):
        routine="ROUTINE work(left,right:ARRAY OF FILE) BEGIN OPEN FILE left[1]('WO','one') OPEN FILE right[1]('WO','two') WRITE left[1](7) WRITE right[1](9) CLOSE FILE left[1] CLOSE FILE right[1] END work"
        p,_=build(body='work(items[1],items[2])',routines=routine);p.run();self.assertEqual(p._state.execution.files.snapshot(),{'one':b' 7','two':b' 9'})


class DirectFileForwardingTests(unittest.TestCase):
    def test_borrowed_row_forwards_whole(self):
        p,_=build(routines=WRITE.replace('work','child')+' ROUTINE work(row:ARRAY OF FILE) BEGIN child(row) END work');p.run();self.assertEqual(cells(p)[2].name,'out')
    def test_borrowed_plane_forwards_row(self):
        routine=WRITE.replace('work','child')+' ROUTINE work(plane:ARRAY[*,*]OF FILE) BEGIN child(plane[2]) END work'
        p,_=build(shape='2,2,2',routines=routine);p.run();self.assertEqual(cells(p)[6].name,'out')
    def test_generic_whole_bank_forwards_prefix(self):
        routine=WRITE.replace('work','child')+' ROUTINE work(bank:ARRAY[*,*]OF FILE) BEGIN child(bank[2]) END work'
        p,_=build(body='work(items)',routines=routine);p.run();self.assertEqual(cells(p)[2].name,'out')
    def test_byname_plane_forwards_direct_row(self):
        routine=WRITE.replace('work','child')+' ROUTINE work(plane:ARRAY[*,*]OF FILE) BEGIN child(plane[2]) END work'
        p,_=build(shape='2,2,2',body="work(BYNAME('','ITEMS[2]',entry))",routines=routine);p.run();self.assertEqual(cells(p)[6].name,'out')
    def test_scalar_descriptor_forwards_from_prefix(self):
        routine="ROUTINE child(f:FILE) BEGIN OPEN FILE f('WO','out') WRITE f(17) CLOSE FILE f END child ROUTINE work(row:ARRAY OF FILE) BEGIN child(row[1]) END work"
        p,_=build(routines=routine);p.run();self.assertEqual(cells(p)[2].name,'out')
    def test_named_row_parameter_can_select_prefix(self):
        routine=WRITE.replace('work','child')+' ROUTINE work(bank:bank_t) BEGIN child(bank[2]) END work'
        p,_=compile_program('work(items)',prefix='TYPE bank_t=ARRAY[2,2]OF FILE',decl='items:bank_t '+DECL,routines=routine,context=rt.ExecutionContext(files=rt.MemoryFiles()));p.run();self.assertEqual(cells(p)[2].name,'out')
    def test_local_names_do_not_require_byname_discovery(self):
        routine=WRITE+' ROUTINE launch VAR hidden:ARRAY[2,2]OF FILE BEGIN work(hidden[2]) END launch'
        p,_=build(body='launch',routines=routine);p.run();self.assertNotIn(('T','HIDDEN'),p._state.execution.variables.bindings)
    def test_paused_callee_keeps_exact_open_descriptor(self):
        routine="ROUTINE work(row:ARRAY OF FILE) BEGIN OPEN FILE row[1]('WO','out') PAUSE WRITE row[1](17) CLOSE FILE row[1] END work"
        p,_=build(routines=routine,cooperative=True);h=cells(p)[2]
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertIsNotNone(h.owner);p.resume();self.assertIsNone(h.owner);self.assertEqual(h.position,3)
    def test_stop_does_not_implicitly_close_file(self):
        p,_=build(routines="ROUTINE work(row:ARRAY OF FILE) BEGIN OPEN FILE row[1]('WO','out') PAUSE END work",cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        h=cells(p)[2];p.stop();self.assertIsNotNone(h.owner);h.owner.close(h)
    def test_open_descriptor_is_shared_not_reopened(self):
        p,_=build(body="OPEN FILE items[2,1]('WO','out') work(items[2])",routines='ROUTINE work(row:ARRAY OF FILE) BEGIN WRITE row[1](17) CLOSE FILE row[1] END work');p.run();self.assertEqual(cells(p)[2].position,3)


class DirectFileCaptureTests(unittest.TestCase):
    def test_selector_call_runs_once(self):
        routine='ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN 2 END pick '+WRITE
        self.assertEqual(run(body='visits=0 work(items[pick()])',routines=routine)['VISITS'],1)
    def test_multiple_coordinates_run_left_to_right(self):
        routine='ROUTINE first:INTEGER BEGIN visits=visits*10+1 RETURN 2 END first ROUTINE second:INTEGER BEGIN visits=visits*10+2 RETURN 1 END second '+WRITE
        self.assertEqual(run(body='visits=0 work(items[first(),second()])',shape='2,2,2',routines=routine)['VISITS'],12)
    def test_reference_is_captured_before_later_argument_effects(self):
        routine='ROUTINE change:INTEGER FROM HOST '+WRITE.replace('work(row:ARRAY OF FILE)','work(row:ARRAY OF FILE;ignored:INTEGER)')
        p,_=build(body='work(items[2],change())',routines=routine);old=list(cells(p));p._state.execution.externals['HOST','CHANGE']=lambda:(setattr(p._state.values['ITEMS'],'values',[rt.FileHandle() for _ in range(4)]) or 0);p.run();self.assertEqual(old[2].name,'out');self.assertIsNone(cells(p)[2].name)
    def test_resize_of_captured_storage_fails_on_use(self):
        routine='ROUTINE change:INTEGER FROM HOST '+WRITE.replace('work(row:ARRAY OF FILE)','work(row:ARRAY OF FILE;ignored:INTEGER)')
        p,_=build(body='work(items[2],change())',routines=routine);p._state.execution.externals['HOST','CHANGE']=lambda:(cells(p).pop() and 0)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.execution.files.snapshot(),{})
    def test_unselected_malformed_descriptor_is_rejected(self):
        p,_=build();cells(p)[0]=7
        with self.assertRaisesRegex(rt.KarelRuntimeError,'exact FILE'):p.run()
        self.assertEqual(p._state.execution.files.snapshot(),{})
    def test_duplicate_descriptor_ownership_is_rejected(self):
        p,_=build();cells(p)[0]=cells(p)[1]
        with self.assertRaisesRegex(rt.KarelRuntimeError,'distinct resources'):p.run()
    def test_malformed_container_shape_is_rejected(self):
        p,_=build();p._state.values['ITEMS'].shape=(4,)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'malformed container'):p.run()
    def test_repeated_prefix_capture_does_not_change_original_list(self):
        p,_=build(body='work(items[2]) work(items[2])');original=cells(p);p.run();self.assertIs(cells(p),original);self.assertEqual(len(original),4)
    def test_bad_index_does_not_enter_callee(self):
        p,_=build(body='n=7 work(items[0])',routines='ROUTINE work(row:ARRAY OF FILE) BEGIN n=9 END work')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],7)
    def test_source_bank_quota_remains_bounded(self):
        with self.assertRaises(TranslationError):build(shape='2,16384')


class DirectFileTransportTests(unittest.TestCase):
    def test_text_input_uses_original_stream(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'in':'17\n'}));routine="ROUTINE work(row:ARRAY OF FILE) BEGIN OPEN FILE row[1]('RO','in') READ row[1](n,CR) CLOSE FILE row[1] END work"
        p,_=build(routines=routine,context=ctx);self.assertEqual(p.run()['N'],17);self.assertEqual(cells(p)[2].position,3)
    def test_binary_output_keeps_attributes(self):
        routine="ROUTINE work(row:ARRAY OF FILE) BEGIN SET_FILE_ATR(row[1],ATR_REVERSE) OPEN FILE row[1]('WB','out') WRITE row[1](17) CLOSE FILE row[1] END work"
        p,_=build(routines=routine);p.run();self.assertEqual(p._state.execution.files.snapshot()['out'],struct.pack('>i',17));self.assertTrue(cells(p)[2].reverse)
    def test_scalar_file_uninit_queries_original_open_state(self):
        routine="ROUTINE work(row:ARRAY OF FILE) BEGIN before=UNINIT(row[1]) OPEN FILE row[1]('WO','out') during=UNINIT(row[1]) CLOSE FILE row[1] END work"
        v=run(routines=routine,decl='before,during:BOOLEAN');self.assertEqual((v['BEFORE'],v['DURING']),(True,False))
    def test_status_and_cursor_queries_use_same_cell(self):
        p,_=build(routines="ROUTINE work(row:ARRAY OF FILE) BEGIN OPEN FILE row[1]('WO','out') WRITE row[1](17) n=GET_FILE_POS(row[1]) status=IO_STATUS(row[1]) CLOSE FILE row[1] END work");v=p.run();self.assertEqual((v['N'],v['STATUS']),(3,0))
    def pending(self):
        bank,ctx=serial();text="PROGRAM MAIN VAR items:ARRAY[2,2]OF FILE n,status:INTEGER done:BOOLEAN ROUTINE work(row:ARRAY OF FILE) BEGIN OPEN FILE row[1]('RO','P2:') n=77 READ row[1](n,CR) status=IO_STATUS(row[1]) CLOSE FILE row[1] done=TRUE END work BEGIN work(items[2]) END MAIN"
        project=translate_project({'main':text}).instantiate(context=ctx);p=project.programs['MAIN'];project.scheduler.start('MAIN');h=cells(p)[2]
        for _ in range(80):
            project.scheduler.step()
            if h._read_operation is not None:return project,p,h,bank
        raise AssertionError('Direct FILE prefix READ did not become pending')
    def test_pending_read_completes_on_original_descriptor(self):
        project,p,h,bank=self.pending();bank.feed(2,b'17\n');project.scheduler.run();self.assertEqual(p.snapshot()['N'],17);self.assertIsNone(h.owner)
    def test_cancellation_preserves_unpublished_input(self):
        project,p,h,bank=self.pending();rt.cancel_file(p._state,h);project.scheduler.run();self.assertEqual((p.snapshot()['N'],p.snapshot()['STATUS']),(77,6));self.assertIsNone(h._read_operation)
    def test_pause_retains_pending_read(self):
        project,p,h,bank=self.pending();p.pause()
        for _ in range(40):
            project.scheduler.step()
            if p.task_state=='paused':break
        self.assertEqual(p.task_state,'paused');bank.feed(2,b'17\n');project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(p.snapshot()['N'],17)
    def test_stop_releases_pending_read_but_keeps_open_descriptor(self):
        project,p,h,bank=self.pending();project.scheduler.stop('MAIN');self.assertIsNone(h._read_operation);self.assertIs(h.owner,bank);bank.close(h)


class DirectFileLinkAndPersistenceTests(unittest.TestCase):
    def test_linked_source_routine_borrows_row(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles());main='PROGRAM MAIN VAR items:ARRAY[2,2]OF FILE ROUTINE work(row:ARRAY OF FILE) FROM LIB BEGIN work(items[2]) END MAIN'
        project=translate_project({'main':main,'lib':'PROGRAM LIB '+WRITE+' BEGIN END LIB'}).instantiate(context=ctx);p=project.programs['MAIN'];h=cells(p)[2];project.run('MAIN');self.assertIs(cells(p)[2],h);self.assertEqual(h.name,'out')
    def test_external_callback_receives_live_reference(self):
        p,_=build(routines='ROUTINE work(row:ARRAY OF FILE) FROM HOST');seen=[]
        def callback(reference):seen.append(reference.raw().values[0])
        p._state.execution.externals['HOST','WORK']=callback;p.run();self.assertIs(seen[0],cells(p)[2])
    def test_external_capture_stays_on_original_cells(self):
        p,_=build(routines='ROUTINE work(row:ARRAY OF FILE) FROM HOST');seen=[];p._state.execution.externals['HOST','WORK']=lambda ref:seen.append(ref)
        p.run();old=cells(p);p._state.values['ITEMS'].values=[rt.FileHandle() for _ in range(4)]
        with rt._numeric_scope('pythonic'):self.assertIs(seen[0].raw().values[0],old[2])
    def test_linked_signature_mismatch_remains_rejected(self):
        with self.assertRaisesRegex(ValueError,'type mismatch'):translate_project({'main':'PROGRAM MAIN ROUTINE work(row:ARRAY OF FILE) FROM LIB BEGIN END MAIN','lib':'PROGRAM LIB ROUTINE work(row:ARRAY OF QUEUE_TYPE) BEGIN END work BEGIN END LIB'}).instantiate()
    def test_static_file_bank_remains_omitted_from_saved_variables(self):
        p,_=build();p.run();self.assertFalse(any(r['path']=='ITEMS' for r in p._state.execution.to_config().get('variables',[])))
    def test_live_view_is_not_generic_typed_data(self):
        p,_=build(routines='ROUTINE work(row:ARRAY OF FILE) FROM HOST');seen=[];p._state.execution.externals['HOST','WORK']=lambda ref:seen.append(ref);p.run()
        with self.assertRaises(ValueError):typed_value(seen[0].raw(),seen[0].spec)


class DirectFileBoundaryTests(unittest.TestCase):
    def reject(self,body='work(items[2])',**options):
        with self.assertRaises(TranslationError) as e:build(body=body,**options)
        return e.exception
    def test_grouped_prefix_still_cannot_copy_files(self):self.reject('work((items[2]))')
    def test_grouped_whole_bank_still_cannot_copy_files(self):self.reject('work((items))')
    def test_scalar_file_formal_cannot_accept_a_row(self):self.assertEqual(self.reject(routines='ROUTINE work(f:FILE) BEGIN END work').code,'E_TYPE')
    def test_wrong_formal_rank_is_rejected(self):self.assertEqual(self.reject(routines='ROUTINE work(row:ARRAY[*,*]OF FILE) BEGIN END work').code,'E_TYPE')
    def test_named_suffix_identity_is_not_invented(self):self.assertEqual(self.reject(prefix='TYPE row_t=ARRAY[2]OF FILE',routines='ROUTINE work(row:row_t) BEGIN END work').code,'E_TYPE')
    def test_wrong_named_inner_component_is_rejected(self):
        self.reject(kind='first_t',prefix='TYPE first_t=ARRAY[2]OF FILE second_t=ARRAY[2]OF FILE',routines='ROUTINE work(row:ARRAY OF second_t) BEGIN END work')
    def test_file_prefix_is_not_integer_data(self):self.assertEqual(self.reject(routines='ROUTINE work(row:ARRAY OF INTEGER) BEGIN END work').code,'E_TYPE')
    def test_whole_assignment_stays_rejected(self):self.reject('items[1]=items[2]')
    def test_file_bank_write_stays_rejected(self):self.reject('WRITE(items[2])')
    def test_file_bank_read_stays_rejected(self):self.reject('READ(items[2])')
    def test_file_bank_uninit_stays_rejected(self):self.reject('flag=UNINIT(items[2])',decl='flag:BOOLEAN')
    def test_prefix_cannot_feed_any_scalar_service(self):self.reject('status=FILE_COUNT(items[2])')
    def test_boolean_index_stays_rejected(self):self.assertEqual(self.reject('work(items[TRUE])').code,'E_TYPE')
    def test_real_index_stays_rejected(self):self.assertEqual(self.reject('work(items[1.0])').code,'E_TYPE')
    def test_path_prefix_retains_private_value_copy(self):
        routine='ROUTINE work(row:ARRAY OF route_t) BEGIN APPEND_NODE(row[1],status) END work'
        p,_=resource_build('route_t',body='work(items[2])',routines=routine);p.run();self.assertEqual(cells(p)[2].nodes,[])
    def test_queue_prefix_retains_private_value_copy(self):
        routine='ROUTINE work(row:ARRAY OF QUEUE_TYPE) BEGIN INIT_QUEUE(row[1]) END work'
        p,_=resource_build('QUEUE_TYPE',body='work(items[2])',routines=routine);p.run();self.assertFalse(cells(p)[2].initialized)


class DirectFileReportTests(unittest.TestCase):
    def test_policy_is_discoverable(self):self.assertEqual(build()[1].report['file_prefix_call_policy']['guide'],'docs/direct-file-prefixes.md')
    def test_source_capture_records_argument_and_suffix(self):
        row=build()[1].report['file_prefix_arguments'][0];self.assertEqual((row['routine'],row['parameter'],row['supplied_subscripts']),('WORK','ROW',1));self.assertEqual(row['selected_type_spec'],('ARRAY',2,('FILE',)));self.assertTrue(row['original_cells'])
    def test_include_origin_retains_physical_location(self):
        source='PROGRAM T VAR items:ARRAY[2,2]OF FILE '+WRITE+' BEGIN\n%INCLUDE calls\nEND T'
        row=translate(source,filename='main.kl',includes={'calls':'work(items[2])'}).report['file_prefix_arguments'][0];self.assertEqual((row['source_file'],row['source_line']),('calls',1))
    def test_offline_and_value_boundaries_remain_explicit(self):
        policy=build()[1].report['file_prefix_call_policy'];self.assertFalse(policy['controller_validated']);self.assertIn('strict',policy['boundary']);self.assertIn('PATH/QUEUE',policy['source'])

    def test_dynamic_bank_forwarding_keeps_reservations_and_closed_marker(self):
        from karel2py.dynamic import reserved
        routine=WRITE+' ROUTINE parent(bank:ARRAY[*,*]OF FILE) BEGIN work(bank[2]) END parent'
        body="CREATE_VAR('CACHE','BANK','','ARRAY OF FILE',0,2,2,0,status) parent(BYNAME('CACHE','BANK',entry))"
        p,_=compile_program(body,decl=DECL,routines=routine,context=rt.ExecutionContext(files=rt.MemoryFiles()));p.run();ctx=p._state.execution;self.assertEqual(reserved(ctx.variables),4)
        row=next(row for row in ctx.to_config()['variables'] if row['program']=='CACHE');self.assertEqual(row['value'],{'closed':True})
    def test_caller_descriptor_alias_can_cancel_prefix_read(self):
        bank,ctx=serial();routine="ROUTINE work(row:ARRAY OF FILE) BEGIN OPEN FILE row[1]('RO','P2:') n=77 READ row[1](n,CR) status=IO_STATUS(row[1]) CLOSE FILE row[1] END work"
        body='flag=FALSE CONDITION[1]: WHEN flag DO CANCEL FILE items[2,1] ENDCONDITION ENABLE CONDITION[1] work(items[2])'
        p,_=build(body=body,routines=routine,context=ctx,decl='flag:BOOLEAN',sleep=lambda _:p._state.set('FLAG',True));v=p.run();self.assertEqual((v['N'],v['STATUS']),(77,6));self.assertEqual(bank._pending,{})
    def test_disjoint_global_for_counter_can_call_borrowed_prefix(self):
        routine='ROUTINE work(row:ARRAY OF FILE) BEGIN n=n+1 END work'
        self.assertEqual(run(body='n=0 FOR visits=1 TO 2 DO work(items[visits]) ENDFOR',routines=routine)['N'],2)
    def test_index_call_cannot_mutate_active_counter(self):
        routine='ROUTINE pick:INTEGER BEGIN visits=2 RETURN 1 END pick ROUTINE work(row:ARRAY OF FILE) BEGIN END work'
        with self.assertRaises(TranslationError) as e:build(body='FOR visits=1 TO 2 DO work(items[pick()]) ENDFOR',routines=routine)
        self.assertEqual(e.exception.code,'E_FOR_COUNTER')
    def test_narrow_integral_index_uses_existing_checked_promotion(self):
        p,_=build(body='selected=2 work(items[selected])',decl='selected:BYTE');p.run();self.assertEqual(cells(p)[2].name,'out')
    def test_data_prefix_still_uses_private_value(self):
        routine='ROUTINE work(row:ARRAY OF INTEGER) BEGIN row[1]=99 END work'
        v=run(body='data[2,1]=7 work(data[2]) n=data[2,1]',decl='data:ARRAY[2,2]OF INTEGER',routines=routine);self.assertEqual(v['N'],7)
