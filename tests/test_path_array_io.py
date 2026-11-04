"""Authored PATH-bank scalar I/O, capture, ownership and transport regressions."""
import json
import struct
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_path_io import TYPES,text
from tests.test_file_cancellation import serial
from tests.test_position_input import VALUES as POSE_VALUES,EXPECTED as POSE_EXPECTED

PREFIX=TYPES+' route_t=PATH NODEDATA=node_t PATHHEADER=header_t'
DECL='paths:ARRAY[2]OF route_t status,count,visits:INTEGER f:FILE done:BOOLEAN'
SEED="APPEND_NODE(paths[1],status) APPEND_NODE(paths[2],status) paths[1].total=1 paths[2].total=2 paths[1][1].amount=7 paths[2][1].amount=9 paths[1][1].label='abcd' paths[2][1].label='wxyz' "
VALUES=[3,17,'left',4,19,'rght']
EXPECTED=[dict(nodes=[dict(AMOUNT=17,LABEL='left')],data=dict(TOTAL=3)),dict(nodes=[dict(AMOUNT=19,LABEL='rght')],data=dict(TOTAL=4))]

def build(body='WRITE(paths)',*,seed=True,values=None,decl=DECL,prefix=PREFIX,**options):
    if values is not None:options['read']=lambda request:list(values)
    return compile_program((SEED if seed else '')+body,decl=decl,prefix=prefix,**options)
def raw(p):return p._state.values['PATHS']

class PathBankWriteTests(unittest.TestCase):
    def test_row_major_header_then_nodes(self):
        p,_=build();p.run();self.assertEqual(text(p),[' 1 7abcd 2 9wxyz'])
    def test_scalar_and_cr_share_one_request(self):
        p,_=build("WRITE('start',paths,CR,42)");p.run();self.assertEqual(text(p),['start 1 7abcd 2 9wxyz\n 42'])
    def test_grouped_bank_output(self):
        p,_=build('WRITE((paths))');p.run();self.assertEqual(text(p),[' 1 7abcd 2 9wxyz'])
    def test_computed_result_output(self):
        p,_=build('WRITE(copy())',routines='ROUTINE copy:ARRAY OF route_t BEGIN RETURN paths END copy');p.run();self.assertEqual(text(p),[' 1 7abcd 2 9wxyz'])
    def test_uniform_formats_apply_per_leaf(self):
        p,_=build('WRITE(paths::4::0)');p.run();self.assertEqual(text(p),['   1   7abcd   2   9wxyz'])
    def test_values_captured_before_format_effects(self):
        p,_=build('WRITE(paths::width()::0)',routines='ROUTINE width:INTEGER BEGIN paths[2][1].amount=99 RETURN 4 END width');p.run();self.assertEqual(text(p),['   1   7abcd   2   9wxyz']);self.assertEqual(raw(p).values[1].nodes[0].values['AMOUNT'],99)
    def test_format_deleting_later_node_cannot_change_output(self):
        p,_=build('WRITE(paths::width()::0)',routines='ROUTINE width:INTEGER BEGIN DELETE_NODE(paths[2],1,status) RETURN 4 END width');p.run();self.assertEqual(text(p),['   1   7abcd   2   9wxyz']);self.assertEqual(len(raw(p).values[1].nodes),0)
    def test_incomplete_data_skips_formats_and_output(self):
        p,_=build('visits=0 WRITE(paths::width())',routines='ROUTINE width:INTEGER BEGIN visits=1 RETURN 4 END width',seed=False)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['VISITS'],text(p)),(0,[]))
    def test_bare_formal_output(self):
        p,_=build('show(paths)',routines='ROUTINE show(v:ARRAY OF route_t) BEGIN WRITE(v) END show');p.run();self.assertEqual(text(p),[' 1 7abcd 2 9wxyz'])
    def test_private_formal_output(self):
        p,_=build('show((paths))',routines='ROUTINE show(v:ARRAY OF route_t) BEGIN v[1][1].amount=99 WRITE(v) END show');p.run();self.assertEqual(text(p),[' 1 99abcd 2 9wxyz']);self.assertEqual(p.snapshot()['PATHS'][0]['nodes'][0]['AMOUNT'],7)
    def test_all_empty_bank_produces_one_empty_item(self):
        p,_=build('WRITE(paths)',seed=False,prefix='',decl='paths:ARRAY[2]OF PATH');p.run();self.assertEqual(text(p),[''])
    def test_empty_bank_formatted_output_rejects(self):
        p,_=build('WRITE(paths::4)',seed=False,prefix='',decl='paths:ARRAY[2]OF PATH')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Empty PATH'):p.run()
        self.assertEqual(text(p),[])
    def test_empty_cells_are_skipped_in_formatted_mixed_bank(self):
        p,_=build('APPEND_NODE(paths[2],status) paths[2][1].amount=17 WRITE(paths::4)',seed=False,prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t',decl='paths:ARRAY[2]OF route_t status:INTEGER');p.run();self.assertEqual(text(p),['  17'])
    def test_report_records_path_bank_order(self):
        _,r=build();item=r.report['writes'][0]['items'][0];self.assertIn('ARRAY-row-major/PATH',item['scalar_order']);self.assertFalse(r.report['path_array_io_policy']['controller_validated'])

class PathBankReadTests(unittest.TestCase):
    def test_read_existing_headers_and_nodes(self):
        p,_=build('READ(paths)',values=VALUES);self.assertEqual(p.run()['PATHS'],EXPECTED)
    def test_root_cell_and_header_identities_remain(self):
        p,_=build('READ(paths)',values=VALUES);array=raw(p);cells=list(array.values);headers=[v.data for v in cells];p.run();self.assertIs(raw(p),array);self.assertTrue(all(a is b for a,b in zip(cells,array.values)));self.assertTrue(all(a is b.data for a,b in zip(headers,cells)))
    def test_missing_scalar_leaves_are_input_targets(self):
        p,_=build('APPEND_NODE(paths[1],status) APPEND_NODE(paths[2],status) READ(paths)',values=VALUES,seed=False);self.assertEqual(p.run()['PATHS'],EXPECTED)
    def test_input_does_not_resize_from_header_count(self):
        p,_=build('READ(paths)',values=[99,17,'left',88,19,'rght']);p.run();self.assertEqual([len(v.nodes) for v in raw(p).values],[1,1])
    def test_invalid_last_response_preserves_every_cell(self):
        p,_=build('READ(paths)',values=[3,17,'left',4,True,'rght'])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['PATHS'][0]['nodes'][0]['AMOUNT'],7);self.assertEqual(p.snapshot()['PATHS'][1]['data']['TOTAL'],2)
    def test_short_response_preserves_every_cell(self):
        p,_=build('READ(paths)',values=[3,17])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['PATHS'][0]['data']['TOTAL'],1)
    def test_cr_uses_expanded_scalar_offsets(self):
        p,_=build('READ(paths,CR,count)',values=VALUES+[42]);self.assertEqual(p.run()['COUNT'],42);self.assertEqual(p.read_requests[0]['line_breaks'],[6])
    def test_formats_evaluate_once(self):
        p,_=build('visits=0 READ(paths::width()::0)',values=VALUES,routines='ROUTINE width:INTEGER BEGIN visits=visits+1 RETURN 4 END width');self.assertEqual(p.run()['VISITS'],1);self.assertEqual(p.snapshot()['PATHS'],EXPECTED)
    def test_deleted_node_keeps_captured_original_leaf(self):
        held=[]
        def read(_):held.append(raw(p).values[1]);return VALUES
        p,_=build('READ(paths::width())',read=read,routines='ROUTINE width:INTEGER BEGIN DELETE_NODE(paths[1],1,status) RETURN 0 END width');v=p.run();self.assertEqual(v['PATHS'][0]['nodes'],[]);self.assertEqual(v['PATHS'][1],EXPECTED[1])
    def test_replaced_cell_cannot_retarget_captured_input(self):
        captured=[]
        def read(_):captured.append(raw(p).values[0].nodes[0]);raw(p).values[0]=rt.PathValue(raw(p).spec[2]);return VALUES
        p,_=build('READ(paths)',read=read);p.run();self.assertEqual(captured[0].values['AMOUNT'],17);self.assertEqual(raw(p).values[0].nodes,[])
    def test_bare_formal_updates_caller(self):
        p,_=build('fill(paths)',values=VALUES,routines='ROUTINE fill(v:ARRAY OF route_t) BEGIN READ(v) END fill');self.assertEqual(p.run()['PATHS'],EXPECTED)
    def test_private_formal_has_no_copyback(self):
        p,_=build('fill((paths))',values=VALUES,routines='ROUTINE fill(v:ARRAY OF route_t) BEGIN READ(v) WRITE(v) END fill');p.run();self.assertEqual(p.snapshot()['PATHS'][0]['nodes'][0]['AMOUNT'],7);self.assertEqual(text(p),[' 3 17left 4 19rght'])
    def test_header_only_bank_input(self):
        p,_=build('READ(paths)',seed=False,values=[3,4]);self.assertEqual([v['data']['TOTAL'] for v in p.run()['PATHS']],[3,4])
    def test_all_empty_input_rejects_before_adapter(self):
        seen=[];p,_=build('READ(paths)',seed=False,prefix='',decl='paths:ARRAY[2]OF PATH',read=lambda r:seen.append(r))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'existing header or node'):p.run()
        self.assertEqual(seen,[])
    def test_selected_nonempty_cell_skips_empty_cells(self):
        p,_=build('APPEND_NODE(paths[2],status) READ(paths)',seed=False,prefix='TYPE n=STRUCTURE amount:INTEGER ENDSTRUCTURE r=PATH NODEDATA=n',decl='paths:ARRAY[2]OF r status:INTEGER',values=[17]);self.assertEqual(p.run()['PATHS'][1]['nodes'][0]['AMOUNT'],17)
    def test_alias_leaf_after_bank_follows_source_input_order(self):
        p,_=build('READ(paths,paths[1][1].amount)',values=VALUES+[99]);self.assertEqual(p.run()['PATHS'][0]['nodes'][0]['AMOUNT'],99)
    def test_context_roundtrip_is_logical_data(self):
        p,_=build('READ(paths)',values=VALUES);p.run();config=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)

class PathBankPrefixTests(unittest.TestCase):
    def bank(self,body,**options):return build(body,seed=False,prefix='TYPE n=STRUCTURE amount:INTEGER ENDSTRUCTURE r=PATH NODEDATA=n',decl='paths:ARRAY[2,2]OF r status,count:INTEGER',**options)
    def test_write_row_uses_its_cells_only(self):
        p,_=self.bank('APPEND_NODE(paths[2,2],status) paths[2,2][1].amount=17 WRITE(paths[2])');p.run();self.assertEqual(text(p),[' 17'])
    def test_read_row_writes_original_cells(self):
        p,_=self.bank('APPEND_NODE(paths[1,1],status) APPEND_NODE(paths[2,2],status) READ(paths[2])',values=[17]);v=p.run();self.assertEqual(v['PATHS'][1][1]['nodes'][0]['AMOUNT'],17);self.assertEqual(v['PATHS'][0][0]['nodes'][0]['AMOUNT'],{'uninitialized':True})
    def test_prefix_selector_runs_once(self):
        p,_=self.bank('APPEND_NODE(paths[2,2],status) count=0 READ(paths[pick()])',values=[17],routines='ROUTINE pick:INTEGER BEGIN count=count+1 RETURN 2 END pick');self.assertEqual(p.run()['COUNT'],1)
    def test_prefix_capture_precedes_later_scalar_selector(self):
        p,_=self.bank('APPEND_NODE(paths[2,2],status) READ(paths[2],paths[pick(),2][1].amount)',values=[17,99],routines='ROUTINE pick:INTEGER BEGIN DELETE_NODE(paths[2,2],1,status) APPEND_NODE(paths[2,2],status) RETURN 2 END pick');self.assertEqual(p.run()['PATHS'][1][1]['nodes'][0]['AMOUNT'],99)
    def test_byname_prefix_reads_live_cells(self):
        p,_=self.bank("APPEND_NODE(paths[2,2],status) fill(BYNAME('','PATHS[2]',count))",values=[17],routines='ROUTINE fill(v:ARRAY OF r) BEGIN READ(v) END fill');self.assertEqual(p.run()['PATHS'][1][1]['nodes'][0]['AMOUNT'],17)
    def test_named_inner_bank_reads_in_place(self):
        p,_=build('APPEND_NODE(paths[2,2],status) READ(paths[2])',seed=False,prefix='TYPE n=STRUCTURE amount:INTEGER ENDSTRUCTURE r=PATH NODEDATA=n row_t=ARRAY[2]OF r',decl='paths:ARRAY[2]OF row_t status:INTEGER',values=[17]);self.assertEqual(p.run()['PATHS'][1][1]['nodes'][0]['AMOUNT'],17)
    def test_three_dimensional_plane_read(self):
        p,_=build('APPEND_NODE(paths[2,2,2],status) READ(paths[2])',seed=False,prefix='TYPE n=STRUCTURE amount:INTEGER ENDSTRUCTURE r=PATH NODEDATA=n',decl='paths:ARRAY[2,2,2]OF r status:INTEGER',values=[17]);self.assertEqual(p.run()['PATHS'][1][1][1]['nodes'][0]['AMOUNT'],17)
    def test_dynamic_created_bank(self):
        p,_=build("CREATE_VAR('CACHE','BANK','T','ARRAY OF route_t',0,2,0,0,status) fill(BYNAME('CACHE','BANK',count))",seed=False,values=VALUES,routines='ROUTINE fill(v:ARRAY OF route_t) BEGIN APPEND_NODE(v[1],status) APPEND_NODE(v[2],status) READ(v) WRITE(v) END fill');p.run();self.assertEqual(text(p),[' 3 17left 4 19rght'])

class PathBankTransportTests(unittest.TestCase):
    def test_fixed_width_text_roundtrip(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles());p,_=build("OPEN FILE f('WO','out') WRITE f(paths::4::0) CLOSE FILE f OPEN FILE f('RO','out') READ f(paths::4::0) CLOSE FILE f",context=ctx);p.run();self.assertEqual(bytes(ctx.files.files['out']),b'   1   7abcd   2   9wxyz')
    def test_binary_roundtrip_preserves_scalar_layout(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles());p,_=build("OPEN FILE f('WB','out') WRITE f(paths) CLOSE FILE f OPEN FILE f('RB','out') READ f(paths) CLOSE FILE f",context=ctx);p.run();self.assertEqual(bytes(ctx.files.files['out']),struct.pack('<ii4sii4s',1,7,b'abcd',2,9,b'wxyz'))
    def test_reverse_binary_byte_order(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles());p,_=build("SET_FILE_ATR(f,ATR_REVERSE,1) OPEN FILE f('WB','out') WRITE f(paths) CLOSE FILE f OPEN FILE f('RB','out') READ f(paths) CLOSE FILE f",context=ctx);p.run();self.assertEqual(bytes(ctx.files.files['out']),struct.pack('>ii4sii4s',1,7,b'abcd',2,9,b'wxyz'))
    def test_truncated_input_rolls_back_cursor_and_data(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'in':struct.pack('<ii',3,17)}));p,_=build("OPEN FILE f('RB','in') READ f(paths)",context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.values['F'].position,0);self.assertEqual(p.snapshot()['PATHS'][0]['data']['TOTAL'],1)
    def test_default_text_input_formats(self):
        p,_=build('READ(paths::4::0)',read=rt.TextInput('   3  17left   4  19rght'));self.assertEqual(p.run()['PATHS'],EXPECTED)
    def test_empty_closed_file_still_rejects(self):
        p,_=build('WRITE f(paths)',seed=False,prefix='',decl='paths:ARRAY[2]OF PATH f:FILE',context=rt.ExecutionContext(files=rt.MemoryFiles()))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not open'):p.run()
    def test_cooperative_binary_cancel_rolls_back_bank(self):
        bank,ctx=serial(struct.pack('<ii',3,17))
        def sleeper(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=build("OPEN FILE f('RB','P2:') READ f(paths) count=IO_STATUS(f) CLOSE FILE f",context=ctx,sleep=sleeper);v=p.run();self.assertEqual(v['COUNT'],6);self.assertEqual(v['PATHS'][0]['data']['TOTAL'],1);self.assertEqual(bank.snapshot()[2]['input'],struct.pack('<ii',3,17))
    def pending(self):
        bank,ctx=serial();decl='f:FILE paths:ARRAY[2]OF PATH NODEDATA=node_t s:INTEGER done:BOOLEAN';body="APPEND_NODE(paths[2],s) OPEN FILE f('RO','P2:') READ f(paths,CR) CLOSE FILE f done=TRUE"
        sources={'main':"PROGRAM MAIN TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE VAR "+decl+' BEGIN '+body+' END MAIN'}
        project=translate_project(sources).instantiate(context=ctx);task=project.programs['MAIN'];project.scheduler.start('MAIN')
        for _ in range(80):
            project.scheduler.step()
            if task._state.values['F']._read_operation is not None:return bank,project,task,task._state.values['F']
        self.fail('READ did not become pending')
    def test_pause_resume_retains_captured_input(self):
        bank,project,task,handle=self.pending();task.pause()
        for _ in range(40):
            project.scheduler.step()
            if task.task_state=='paused':break
        self.assertEqual(task.task_state,'paused');bank.feed(2,b'17\n');project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(task.snapshot()['PATHS'][1]['nodes'][0]['AMOUNT'],17);self.assertIsNone(handle._read_operation)
    def test_stop_clears_pending_input_without_publication(self):
        bank,project,task,handle=self.pending();project.scheduler.stop('MAIN');self.assertEqual(task.task_state,'stopped');self.assertEqual(task.snapshot()['PATHS'][1]['nodes'][0]['AMOUNT'],{'uninitialized':True});self.assertIsNone(handle._read_operation);bank.close(handle)
    def test_linked_read_and_write_share_exact_bank(self):
        types='TYPE n=STRUCTURE amount:INTEGER ENDSTRUCTURE r=PATH NODEDATA=n'
        sources={'main':f'PROGRAM MAIN {types} VAR paths:ARRAY[2]OF r s:INTEGER ROUTINE fill(v:ARRAY OF r) FROM LIB BEGIN APPEND_NODE(paths[2],s) fill(paths) END MAIN','lib':f'PROGRAM LIB {types} ROUTINE fill(v:ARRAY OF r) BEGIN READ(v) WRITE(v) END fill BEGIN END LIB'}
        project=translate_project(sources).instantiate(options=dict(read=lambda r:[17]));state=project.run('MAIN');self.assertEqual(state['MAIN']['values']['PATHS'][1]['nodes'][0]['AMOUNT'],17)

class PathBankGuardTests(unittest.TestCase):
    def test_shared_path_cells_reject_before_transport(self):
        seen=[];p,_=build('READ(paths)',seed=False,read=lambda r:seen.append(r));raw(p).values[1]=raw(p).values[0]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(seen,[])
    def test_shared_headers_reject_before_output(self):
        p,_=build();a,b=raw(p).values;b.data=a.data
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(text(p),[])
    def test_shared_nodes_reject_before_input(self):
        p,_=build('READ(paths)',values=VALUES,seed=False);a,b=raw(p).values;a.append();b.nodes=a.nodes
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_malformed_runtime_schema_is_source_located(self):
        p,_=build('WRITE(paths)',seed=False);value=raw(p);declared=value.spec;value.spec=None
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.path_array_io_values(declared,value,7)
    def test_malformed_bank_shape_rejects(self):
        p,_=build(seed=False);raw(p).shape=(1,2)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_malformed_bank_length_rejects(self):
        p,_=build(seed=False);raw(p).values.pop()
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_malformed_node_value_prevents_formats(self):
        p,_=build('visits=0 WRITE(paths::width())',routines='ROUTINE width:INTEGER BEGIN visits=1 RETURN 4 END width',seed=False);raw(p).values[1].append();raw(p).values[1].nodes[0].values['AMOUNT']=True
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)
    def test_missing_container_cannot_be_invented(self):
        p,_=build('READ(paths)',seed=False,values=[3,4]);raw(p).values[1].data=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_combined_bank_field_bound_precedes_formats(self):
        p,_=build('visits=0 WRITE(paths::width())',prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t',decl='paths:ARRAY[2]OF route_t visits:INTEGER',seed=False,routines='ROUTINE width:INTEGER BEGIN visits=1 RETURN 4 END width')
        for cell in raw(p).values:
            for _ in range(513):cell.append();cell.nodes[-1].values['AMOUNT']=7
        with self.assertRaisesRegex(rt.KarelRuntimeError,'1024'):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)
    def test_exactly_1024_fields_can_be_read(self):
        p,_=build('READ(paths)',prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t',decl='paths:ARRAY[2]OF route_t',seed=False,values=list(range(1024)))
        for cell in raw(p).values:
            for _ in range(512):cell.append()
        self.assertEqual(p.run()['PATHS'][1]['nodes'][-1]['AMOUNT'],1023)
    def test_cr_counts_toward_operation_bound(self):
        p,_=build('READ(paths,CR)',prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t',decl='paths:ARRAY[2]OF route_t',seed=False,values=list(range(1024)))
        for cell in raw(p).values:
            for _ in range(512):cell.append()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'1024'):p.run()
    def test_whole_position_cohorts_retain_geometry_checks(self):
        p,_=build('APPEND_NODE(paths[2],status) READ(paths)',seed=False,prefix='TYPE node_t=STRUCTURE pose:POSITION ENDSTRUCTURE route_t=PATH NODEDATA=node_t',decl='paths:ARRAY[2]OF route_t status:INTEGER',values=POSE_VALUES);self.assertEqual(p.run()['PATHS'][1]['nodes'][0]['POSE'],POSE_EXPECTED)
    def test_bad_position_geometry_has_no_partial_bank_publication(self):
        values=list(POSE_VALUES);values[0]=2.
        p,_=build('APPEND_NODE(paths[2],status) READ(paths)',seed=False,prefix='TYPE node_t=STRUCTURE pose:POSITION ENDSTRUCTURE route_t=PATH NODEDATA=node_t',decl='paths:ARRAY[2]OF route_t status:INTEGER',values=values)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['PATHS'][1]['nodes'][0]['POSE']['LOCATION']['X'],{'uninitialized':True})
    def test_queue_banks_remain_excluded(self):
        for operation in ('READ','WRITE'):
            with self.subTest(operation=operation),self.assertRaises(TranslationError):build(operation+'(paths)',seed=False,prefix='',decl='paths:ARRAY[2]OF QUEUE_TYPE')
    def test_file_banks_remain_excluded(self):
        for operation in ('READ','WRITE'):
            with self.subTest(operation=operation),self.assertRaises(TranslationError):build(operation+'(paths)',seed=False,prefix='',decl='paths:ARRAY[2]OF FILE')
    def test_resource_fields_remain_excluded(self):
        bad=('STRUCTURE','NESTED',(('VALUE',('ARRAY',2,('PATH',None,None))),));self.assertFalse(rt.aggregate_write_type(bad));self.assertFalse(rt.aggregate_read_type(bad))
    def test_direct_orientation_input_remains_excluded(self):
        with self.assertRaises(TranslationError):build('READ(paths[1][1].pose.normal)',seed=False,prefix='TYPE n=STRUCTURE pose:POSITION ENDSTRUCTURE r=PATH NODEDATA=n',decl='paths:ARRAY[2]OF r')
    def test_generic_collection_checked_copy_stays_closed(self):
        p,_=build(seed=False)
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.checked(raw(p).spec,raw(p))
    def test_readonly_root_reference_rejects(self):
        p,_=build(seed=False);value=raw(p);ref=rt.ReadOnlyFieldReference(value.spec,{'value':value},'value')
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.capture_aggregate_read_target(ref,[])
    def test_legacy_runtime_scope_remains_closed(self):
        p,_=build(seed=False)
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.path_array_io_values(raw(p).spec,raw(p))
    def test_policy_records_bounds_and_persistence(self):
        _,r=build();policy=r.report['path_array_io_policy'];self.assertIn('1024',policy['bounds']);self.assertIn('JSON',policy['persistence']);self.assertEqual(policy['guide'],'docs/path-array-io.md')

if __name__=='__main__':unittest.main()
