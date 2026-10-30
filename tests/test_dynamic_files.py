"""Authored created FILE roots, explicit I/O, closed descriptors and lifetimes."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate_project
from karel2py.dynamic import creation_cost,concrete_type,file_descriptor_payload,restore_file_descriptor
from karel2py.storage import typed_value,decode_typed,collection_data_spec
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_dynamic_narrow import create
from tests.test_file_cancellation import serial
from tests.test_keyboard import context as keyboard_context

DECL='entry,status,n,m,prior,seen:INTEGER text:STRING[254] flag,done:BOOLEAN'
FILE=('FILE',)
READ="ROUTINE work(h:FILE) BEGIN OPEN FILE h('RO','data.txt') READ h(n,CR) status=IO_STATUS(h) CLOSE FILE h END work"
WAIT="ROUTINE work(h:FILE) BEGIN OPEN FILE h('RO','P2:') n=77 READ h(n,CR) status=IO_STATUS(h) CLOSE FILE h END work"


def context():return rt.ExecutionContext(files=rt.MemoryFiles({'data.txt':b'42\n'}))
def program(body='',**options):return compile_program(body,decl=options.pop('decl',DECL),**options)
def execute(body='',**options):
    p,r=program(body,**options);return p.run(),p._state.execution,p,r

def ref(ctx,name='ITEM',owner='CACHE'):return ctx.variables.bindings[owner,name]
def invoke(name='work',path='ITEM',owner='CACHE'):return name+"(BYNAME('"+owner+"','"+path+"',entry)) "
def row(ctx):return next(r for r in ctx.to_config()['variables'] if r['program']=='CACHE' and r['path']=='ITEM')
def pending(ctx):
    source='PROGRAM MAIN VAR '+DECL+' '+WAIT+' BEGIN '+create('FILE')+invoke()+'done=TRUE END MAIN'
    project=translate_project({'main':source}).instantiate(context=ctx);task=project.programs['MAIN'];project.scheduler.start('MAIN')
    for _ in range(80):
        project.scheduler.step();target=ctx.variables.bindings.get(('CACHE','ITEM'))
        if target is not None and target.raw()._read_operation is not None:return project,task,target.raw()
    raise AssertionError('Created FILE read did not wait')


class DynamicFileCreationTests(unittest.TestCase):
    def test_direct_file_creates_exact_closed_storage_without_backend(self):
        v,ctx,_,_=execute(create('FILE'));h=ref(ctx).raw();self.assertEqual(v['STATUS'],0);self.assertIs(type(h),rt.FileHandle);self.assertIsNone(h.owner);self.assertIsNone(ctx.files);self.assertEqual((h.name,h.position,h.status,h.mode),(None,0,0,''))

    def test_casefolded_and_trimmed_file_type(self):
        v,ctx,_,_=execute(create(' file '));self.assertEqual((v['STATUS'],ref(ctx).spec),(0,FILE))

    def test_supplied_transparent_alias_uses_file_contract(self):
        v,ctx,_,_=execute(create('fd_t'),prefix='TYPE fd_t=FILE');self.assertEqual((v['STATUS'],ref(ctx).spec),(0,FILE))

    def test_foreign_alias_uses_attached_type_owner(self):
        main='PROGRAM MAIN VAR status:INTEGER BEGIN '+create('fd_t',type_owner='LIB')+' END MAIN'
        p=translate_project({'main':main,'lib':'PROGRAM LIB TYPE fd_t=FILE BEGIN END LIB'}).instantiate();p.run('MAIN');self.assertEqual(ref(p.context).spec,FILE)

    def test_blank_namespace_defaults_to_current_source_program(self):
        v,ctx,_,_=execute(create('FILE',owner=''));self.assertEqual(v['STATUS'],0);self.assertIn(('T','ITEM'),ctx.variables.metadata)

    def test_group_and_pool_are_metadata_with_no_device_discovery(self):
        v,ctx,_,_=execute(create('FILE',group=32,pool=-1));self.assertEqual(v['STATUS'],0);self.assertEqual(ctx.variables.metadata['CACHE','ITEM'],dict(group=32,memory_pool=-1));self.assertIsNone(ctx.files)

    def test_additional_dimensions_are_rejected_for_file_and_alias(self):
        for kind in ('FILE','fd_t'):
            for dims in ((1,0,0),(2,3,0),(1,1,1)):
                v,ctx,_,_=execute(create(kind,dims=dims),prefix='TYPE fd_t=FILE');self.assertEqual((v['STATUS'],ctx.variables.bindings),(5,{}))

    def test_preserved_runtime_does_not_gain_file_creation(self):
        p,_=program(prefix='TYPE fd_t=FILE')
        with rt._numeric_scope('strict'):
            for kind in ('FILE','fd_t'):self.assertIsNone(concrete_type(p._state.execution,p._state,'T',kind,0,(0,0,0),1))

    def test_independent_roots_start_with_independent_handles(self):
        _,ctx,_,_=execute(create('FILE')+create('FILE',name='OTHER'));self.assertIsNot(ref(ctx).raw(),ref(ctx,'OTHER').raw())

    def test_duplicate_creation_preserves_open_handle_identity(self):
        ctx=context();routine="ROUTINE work(h:FILE) BEGIN OPEN FILE h('RO','data.txt') END work"
        v,_,_,_=execute(create('FILE')+invoke()+create('FILE'),context=ctx,routines=routine);h=ref(ctx).raw()
        self.assertEqual(v['STATUS'],3);self.assertIs(h.owner,ctx.files);ctx.files.close(h)

    def test_declared_global_and_descendant_binding_prevent_creation(self):
        v,ctx,_,_=execute(create('FILE',owner='',name='LOCAL'),decl=DECL+' local:FILE');self.assertEqual((v['STATUS'],ctx.variables.bindings),(3,{}))
        ctx=rt.ExecutionContext();ctx.variables.define('CACHE','ITEM.X',('INTEGER',),7);v,_,_,_=execute(create('FILE'),context=ctx)
        self.assertEqual(v['STATUS'],3);self.assertEqual(ref(ctx,'ITEM.X').raw(),7)

    def test_file_reservation_is_one_unit_with_existing_collection_budget(self):
        self.assertEqual(creation_cost(FILE),1)
        v,ctx,_,_=execute(create('INTEGER',name='DATA',dims=(32766,0,0))+create('FILE')+create('PATH',name='EXTRA'))
        self.assertEqual(v['STATUS'],6);self.assertEqual(set(ctx.variables.bindings),{('CACHE','DATA'),('CACHE','ITEM')})

    def test_malformed_file_schema_and_embedded_file_are_rejected(self):
        for spec in [('FILE',1),('ARRAY',1,FILE),('STRUCTURE','BAD_T',(('F',FILE),))]:
            with self.subTest(spec=spec),self.assertRaises(ValueError):creation_cost(spec)

    def test_invalid_name_group_pool_never_allocate(self):
        for call,code in [(create('FILE',name='BAD.NAME'),2),(create('FILE',group=33),5),(create('FILE',pool=1),2)]:
            v,ctx,_,_=execute(call);self.assertEqual((v['STATUS'],ctx.variables.bindings),(code,{}))

    def test_checkpoint_abort_retains_status_and_no_descriptor(self):
        p,_=program('status=77 '+create('FILE'));original=p._state.tick;fired=[]
        def tick(line=None):
            original(line)
            if not fired and any(r['operation']=='CREATE_VAR' for r in p._state.service_requests):
                fired.append(1)
                try:p._state.abort(7)
                except rt.KarelAbort:pass
        with patch.object(p._state,'tick',side_effect=tick),self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual((p.snapshot()['STATUS'],p._state.execution.variables.bindings),(77,{}))


class DynamicFileOperationTests(unittest.TestCase):
    def test_byname_file_formal_reads_explicit_memory_file(self):
        v,ctx,p,_=execute(create('FILE')+invoke(),context=context(),routines=READ);self.assertEqual((v['N'],v['STATUS']),(42,0));self.assertIsNone(ref(ctx).raw().owner);self.assertEqual(p._state.local_frames,[])

    def test_text_write_and_reopen_use_same_handle(self):
        routine="ROUTINE work(h:FILE) BEGIN OPEN FILE h('WO','out.txt') WRITE h('hello',CR) CLOSE FILE h OPEN FILE h('RO','out.txt') READ h(text,CR) CLOSE FILE h END work"
        v,ctx,_,_=execute(create('FILE')+invoke(),context=context(),routines=routine);self.assertEqual(v['TEXT'],'hello');self.assertEqual(ctx.files.snapshot()['out.txt'],b'hello\n')

    def test_binary_integer_real_and_string_fields_roundtrip(self):
        routine="ROUTINE work(h:FILE) BEGIN OPEN FILE h('WB','out.bin') WRITE h(42,2.5,'xy'::2) CLOSE FILE h OPEN FILE h('RB','out.bin') READ h(n,value,text::2) CLOSE FILE h END work"
        v,ctx,_,_=execute(create('FILE')+invoke(),context=context(),routines=routine,decl=DECL+' value:REAL')
        self.assertEqual((v['N'],v['VALUE'],v['TEXT']),(42,2.5,'xy'));self.assertEqual(ctx.files.snapshot()['out.bin'],struct.pack('<if',42,2.5)+b'xy')

    def test_source_root_rename_while_open_keeps_file_cursor_and_alias(self):
        routine="ROUTINE work(h:FILE) BEGIN OPEN FILE h('RO','data.txt') RENAME_VAR('CACHE','ITEM','KEPT',status) READ h(n,CR) CLOSE FILE h END work"
        v,ctx,_,_=execute(create('FILE')+invoke(),context=context(),routines=routine);self.assertEqual(v['N'],42);self.assertIsNone(ref(ctx,'KEPT').raw().owner);self.assertNotIn(('CACHE','ITEM'),ctx.variables.bindings)

    def test_namespace_move_while_open_keeps_resource_registration(self):
        routine="ROUTINE work(h:FILE) BEGIN OPEN FILE h('RO','data.txt') RENAME_VARS('CACHE','MOVED',status) READ h(n,CR) CLOSE FILE h END work"
        v,ctx,_,_=execute(create('FILE')+invoke(),context=context(),routines=routine);self.assertEqual(v['N'],42);self.assertIsNone(ref(ctx,owner='MOVED').raw().owner);self.assertIn(('MOVED','ITEM'),ctx.variables.metadata)

    def test_rename_retains_byname_lookup_entry_hint(self):
        v,ctx,_,_=execute(create('FILE')+invoke()+" prior=entry RENAME_VAR('CACHE','ITEM','KEPT',status) "+invoke(path='KEPT'),context=context(),routines=READ)
        self.assertEqual((v['ENTRY'],v['N']),(v['PRIOR'],42))

    def test_var_info_reports_file_type_and_closed_state(self):
        body=create('FILE')+" VAR_INFO('CACHE','ITEM',flag,label,seen,dims,n,status)"
        v,_,_,_=execute(body,decl=DECL+' label:STRING[12] dims:ARRAY[3]OF INTEGER')
        self.assertEqual((v['STATUS'],v['LABEL'],v['SEEN'],v['FLAG']),(0,'FILE',29,True))

    def test_var_info_open_state_remains_initialized(self):
        routine="ROUTINE work(h:FILE) BEGIN OPEN FILE h('RO','data.txt') VAR_INFO('CACHE','ITEM',flag,label,seen,dims,n,status) CLOSE FILE h END work"
        v,_,_,_=execute(create('FILE')+invoke(),context=context(),routines=routine,decl=DECL+' label:STRING[12] dims:ARRAY[3]OF INTEGER');self.assertEqual((v['FLAG'],v['SEEN']),(False,29))

    def test_var_list_file_filter_keeps_other_resource_types_separate(self):
        body=create('FILE')+create('QUEUE_TYPE',name='QUEUE')+" VAR_LIST('CACHE','*',29,0,2,names,n,status)"
        v,_,_,_=execute(body,decl=DECL+' names:ARRAY[2]OF STRING[36]');self.assertEqual((v['N'],v['NAMES']),(1,['ITEM','']))

    def test_file_formal_type_mismatch_preserves_entry(self):
        p,_=program(create('FILE')+' entry=77 '+invoke(),routines='ROUTINE work(v:INTEGER) BEGIN n=99 END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type does not match'):p.run()
        self.assertEqual(p.snapshot()['ENTRY'],77);self.assertIs(p._state.values['N'],rt.UNINITIALIZED)

    def test_whole_file_get_var_remains_excluded(self):
        with self.assertRaises(TranslationError):program(create('FILE')+" GET_VAR(entry,'CACHE','ITEM',local,status)",decl=DECL+' local:FILE')

    def test_file_fields_do_not_become_source_data_members(self):
        with self.assertRaises(TranslationError):program('n=local.position',decl=DECL+' local:FILE')

    def test_missing_files_backend_fails_without_implicit_connection(self):
        p,_=program(create('FILE')+invoke(),routines=READ)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIsNone(ref(p._state.execution).raw().owner)

    def test_directory_backend_remains_explicitly_rooted(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'data.txt').write_bytes(b'42\n');ctx=rt.ExecutionContext(files=rt.DirectoryFiles(folder))
            v,_,_,_=execute(create('FILE')+invoke(),context=ctx,routines=READ);self.assertEqual(v['N'],42);self.assertIsNone(ref(ctx).raw().owner)

    def test_device_backend_uses_explicit_volume_without_group_inference(self):
        ctx=rt.ExecutionContext(files=rt.DeviceFiles({'RD:':{'capacity':1000}},{'RD:data.txt':b'42\n'}))
        v,_,_,_=execute(create('FILE',group=32)+invoke(),context=ctx,routines=READ.replace('data.txt','RD:data.txt'));self.assertEqual(v['N'],42);self.assertIsNone(ctx.robot)

    def test_readonly_file_write_failure_preserves_bytes_and_live_handle(self):
        routine="ROUTINE work(h:FILE) BEGIN OPEN FILE h('RO','data.txt') WRITE h('bad') END work"
        ctx=context();p,_=program(create('FILE')+invoke(),context=ctx,routines=routine)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.files.snapshot()['data.txt'],b'42\n');ctx.files.close(ref(ctx).raw())

    def test_linked_routine_reads_and_closes_dynamic_file(self):
        main='PROGRAM MAIN VAR entry,status,value:INTEGER ROUTINE work(h:FILE):INTEGER FROM LIB BEGIN '+create('FILE')+' value='+invoke()+' END MAIN'
        lib="PROGRAM LIB VAR n:INTEGER ROUTINE work(h:FILE):INTEGER BEGIN OPEN FILE h('RO','data.txt') READ h(n,CR) CLOSE FILE h RETURN n END work BEGIN END LIB"
        p=translate_project({'main':main,'lib':lib}).instantiate(context=context());v=p.run('MAIN');self.assertEqual(v['MAIN']['values']['VALUE'],42);self.assertIsNone(ref(p.context).raw().owner)

    def test_pause_resume_retains_open_handle_and_captured_alias(self):
        routine="ROUTINE work(h:FILE) BEGIN OPEN FILE h('RO','data.txt') PAUSE READ h(n,CR) CLOSE FILE h END work"
        ctx=context();p,_=program(create('FILE')+invoke(),context=ctx,routines=routine,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        h=ref(ctx).raw();self.assertIs(h.owner,ctx.files)
        with self.assertRaises(ValueError):ctx.to_config()
        self.assertEqual(p.resume()['N'],42);self.assertIs(ref(ctx).raw(),h);self.assertIsNone(h.owner)

    def test_abort_keeps_live_handle_until_explicit_close(self):
        routine="ROUTINE work(h:FILE) BEGIN OPEN FILE h('RO','data.txt') ABORT END work";ctx=context();p,_=program(create('FILE')+invoke(),context=ctx,routines=routine,cooperative=True)
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(p._state.local_frames,[])
        with self.assertRaises(ValueError):ctx.to_config()
        ctx.files.close(ref(ctx).raw());self.assertEqual(row(ctx)['value'],{'closed':True})

    def test_transitive_for_counter_write_guard_remains_active(self):
        with self.assertRaises(TranslationError):program(create('FILE')+' FOR n=1 TO 2 DO '+invoke()+' ENDFOR',context=context(),routines=READ)


class DynamicFileDescriptorTests(unittest.TestCase):
    def test_created_closed_file_has_minimal_explicit_json_row(self):
        _,ctx,_,_=execute(create('FILE',pool=-1));self.assertEqual(row(ctx),dict(program='CACHE',path='ITEM',type=['FILE'],value={'closed':True},creation=dict(group=0,memory_pool=-1)))

    def test_roundtrip_allocates_fresh_closed_file(self):
        _,ctx,_,_=execute(create('FILE'));h=ref(ctx).raw();saved=json.loads(json.dumps(ctx.to_config()));other=rt.ExecutionContext.from_config(saved)
        self.assertIsNot(ref(other).raw(),h);self.assertIsNone(ref(other).raw().owner);self.assertEqual(other.to_config(),saved)

    def test_closed_filename_cursor_status_and_attributes_reset_on_restore(self):
        _,ctx,_,_=execute(create('FILE'));h=ref(ctx).raw();h.name='old';h.logical_name='old';h.position=19;h.status=6;h.mode='RB';h.binary=True;h.field=True;h.eol=13;h.passall=True;h.noecho=True
        other=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())));fresh=ref(other).raw();self.assertEqual(vars(fresh),vars(rt.FileHandle()));self.assertEqual(h.position,19)

    def test_restored_descriptor_can_be_opened_again(self):
        _,ctx,_,_=execute(create('FILE'),context=context());other=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        v,_,_,_=execute(invoke(),context=other,routines=READ);self.assertEqual((v['N'],v['STATUS']),(42,0))

    def test_type_string_spelling_normalizes_to_canonical_file_type(self):
        saved=dict(variables=[dict(program='CACHE',path='ITEM',type='FILE',value={'closed':True},creation=dict(group=0,memory_pool=0))])
        other=rt.ExecutionContext.from_config(saved);self.assertEqual(ref(other).spec,FILE);self.assertEqual(row(other)['type'],['FILE'])

    def test_generic_typed_file_encoding_and_decoding_stay_excluded(self):
        with self.assertRaises(ValueError):typed_value(rt.FileHandle(),FILE)
        with self.assertRaises(ValueError):decode_typed(dict(type=['FILE'],value={'closed':True}))

    def test_file_row_without_creation_policy_is_rejected(self):
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(dict(variables=[dict(program='CACHE',path='ITEM',type=['FILE'],value={'closed':True})]))

    def test_descriptor_payload_requires_exact_closed_true_object(self):
        for payload in (None,True,[],{},1,{'closed':False},{'closed':1},{'closed':'true'},{'closed':True,'position':0},{'closed':True,'owner':None}):
            with self.subTest(payload=payload),self.assertRaises(ValueError):restore_file_descriptor(payload)

    def test_invalid_saved_payload_does_not_change_input_configuration(self):
        saved=dict(variables=[dict(program='CACHE',path='ITEM',type=['FILE'],value={'closed':False},creation=dict(group=0,memory_pool=0))]);before=deepcopy(saved)
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(saved)
        self.assertEqual(saved,before)

    def test_open_memory_file_cannot_be_encoded_as_descriptor(self):
        _,ctx,_,_=execute(create('FILE'),context=context());h=ref(ctx).raw();ctx.files.open(h,'R','data.txt')
        with self.assertRaises(ValueError):ctx.to_config()
        ctx.files.close(h)

    def test_foreign_backend_ownership_still_prevents_descriptor_save(self):
        _,ctx,_,_=execute(create('FILE'));bank=rt.MemoryFiles({'x':'data'});h=ref(ctx).raw();bank.open(h,'R','x')
        with self.assertRaisesRegex(ValueError,'closed'):ctx.to_config()
        bank.close(h)

    def test_closed_handle_with_pending_operation_marker_is_rejected(self):
        _,ctx,_,_=execute(create('FILE'));ref(ctx).raw()._read_operation={'cancelled':True}
        with self.assertRaisesRegex(ValueError,'pending I/O'):ctx.to_config()

    def test_nonfile_value_or_subclass_cannot_claim_descriptor_contract(self):
        class Derived(rt.FileHandle):pass
        for value in (42,{},Derived()):
            with self.subTest(value=value),self.assertRaises(ValueError):file_descriptor_payload(value)

    def test_created_file_metadata_is_checked_before_handle_allocation(self):
        saved=dict(variables=[dict(program='CACHE',path='ITEM',type=['FILE'],value={'closed':True},creation=dict(group=33,memory_pool=0))])
        with patch('karel2py.dynamic.restore_file_descriptor',side_effect=AssertionError('must not allocate')),self.assertRaises(ValueError):rt.ExecutionContext.from_config(saved)

    def test_reserved_quota_is_checked_before_descriptor_payload(self):
        _,ctx,_,_=execute(create('INTEGER',dims=(32767,0,0)));saved=ctx.to_config();saved['variables'].append(dict(program='CACHE',path='EXTRA',type=['FILE'],value={'invalid':True},creation=dict(group=0,memory_pool=0)))
        with patch('karel2py.dynamic.restore_file_descriptor',side_effect=AssertionError('must not allocate')),self.assertRaisesRegex(ValueError,'32767'):rt.ExecutionContext.from_config(saved)

    def test_duplicate_saved_created_roots_are_rejected(self):
        _,ctx,_,_=execute(create('FILE'));saved=ctx.to_config();saved['variables'].append(deepcopy(next(r for r in saved['variables'] if r['program']=='CACHE')))
        with self.assertRaisesRegex(ValueError,'Duplicate'):rt.ExecutionContext.from_config(saved)

    def test_existing_state_file_is_preserved_when_live_descriptor_blocks_save(self):
        _,ctx,_,_=execute(create('FILE'),context=context());h=ref(ctx).raw();ctx.files.open(h,'R','data.txt')
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'state.json';target.write_bytes(b'keep')
            with self.assertRaises(ValueError):ctx.save(target)
            self.assertEqual(target.read_bytes(),b'keep')
        ctx.files.close(h)

    def test_closed_descriptors_do_not_restore_alias_relationships(self):
        _,ctx,_,_=execute(create('FILE')+create('FILE',name='OTHER'));ref(ctx,'OTHER').storage['value']=ref(ctx).raw()
        other=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())));self.assertIsNot(ref(other).raw(),ref(other,'OTHER').raw());self.assertIs(ref(ctx).raw(),ref(ctx,'OTHER').raw())

    def test_file_roots_remain_excluded_from_portable_variable_archives(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(),variable_archives=rt.VariableArchives());execute(create('FILE')+" SAVE('CACHE','file.VR',status)",context=ctx)
        saved=ctx.variable_archives.decode(ctx.files.snapshot()['FILE.VR']);self.assertEqual((saved['excluded'],saved['variables']),(['ITEM'],{}))

    def test_collection_data_schema_still_rejects_file_members(self):
        with self.assertRaises(ValueError):collection_data_spec(FILE)
        with self.assertRaises(ValueError):collection_data_spec(('STRUCTURE','BAD_T',(('HANDLE',FILE),)))

    def test_descriptor_shape_contains_no_live_or_filename_metadata(self):
        _,ctx,_,_=execute(create('FILE')+invoke(),context=context(),routines=READ);payload=row(ctx)['value'];self.assertEqual(set(payload),{'closed'});self.assertNotIn('data.txt',json.dumps(payload))

    def test_report_records_reset_and_live_handle_boundaries(self):
        _,_,_,r=execute(create('FILE'));p=r.report['dynamic_file_policy'];self.assertIn('fresh',p['reset']);self.assertIn('Generic typed FILE',p['guards']);self.assertFalse(p['controller_validated'])


class DynamicFileCancellationTests(unittest.TestCase):
    def test_serial_read_cancels_through_created_formal(self):
        bank,ctx=serial(b'17 ');holder={}
        def sleeper(_):rt.cancel_file(holder['p']._state,ref(ctx).raw())
        p,_=program(create('FILE')+invoke(),context=ctx,routines=WAIT,sleep=sleeper);holder['p']=p
        v=p.run();self.assertEqual((v['N'],v['STATUS']),(77,6));self.assertEqual(bank.snapshot()[2]['input'],b'17 ');self.assertIsNone(ref(ctx).raw().owner)

    def test_source_condition_can_cancel_retained_file_formal(self):
        bank,ctx=serial(b'17');holder={}
        def sleeper(_):holder['p']._state.set('FLAG',True)
        routine="ROUTINE work(h:FILE) BEGIN flag=FALSE CONDITION[1]: WHEN flag DO CANCEL FILE h ENDCONDITION ENABLE CONDITION[1] OPEN FILE h('RO','P2:') n=77 READ h(n,CR) DISABLE CONDITION[1] status=IO_STATUS(h) CLOSE FILE h END work"
        p,_=program(create('FILE')+invoke(),context=ctx,routines=routine,sleep=sleeper);holder['p']=p
        v=p.run();self.assertEqual((v['N'],v['STATUS']),(77,6));self.assertEqual(p._state.local_frames,[])

    def test_pending_read_rename_preserves_live_registration(self):
        bank,ctx=serial();project,task,h=pending(ctx);token=h._read_operation
        execute("RENAME_VAR('CACHE','ITEM','KEPT',status)",context=ctx);self.assertIs(ref(ctx,'KEPT').raw(),h);self.assertIs(h._read_operation,token)
        bank.feed(2,b'42\n');project.scheduler.run();self.assertEqual(task.snapshot()['N'],42);self.assertIsNone(h.owner)

    def test_pending_cancel_unwinds_before_descriptor_can_be_saved(self):
        bank,ctx=serial();project,task,h=pending(ctx);rt.cancel_file(task._state,h)
        with self.assertRaises(ValueError):ctx.to_config()
        project.scheduler.run();self.assertEqual(task.snapshot()['STATUS'],6);self.assertEqual(row(ctx)['value'],{'closed':True})

    def test_stopping_pending_reader_retires_read_but_requires_explicit_close(self):
        bank,ctx=serial();project,task,h=pending(ctx);project.scheduler.stop('MAIN')
        self.assertIsNone(h._read_operation);self.assertEqual(task.task_state,'stopped')
        with self.assertRaises(ValueError):ctx.to_config()
        bank.close(h);self.assertEqual(row(ctx)['value'],{'closed':True})

    def test_completed_serial_read_can_save_closed_descriptor_and_stream_data(self):
        bank,ctx=serial(b'42\n');v,_,_,_=execute(create('FILE')+invoke(),context=ctx,routines=WAIT)
        self.assertEqual((v['N'],v['STATUS']),(42,0));saved=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_read_kb_cancellation_keeps_outputs_and_closes_created_file(self):
        ctx=keyboard_context(events=[dict(key='a'),dict(key='ENTER',at_ms=100)]);holder={}
        def sleeper(_):rt.cancel_file(holder['p']._state,ref(ctx).raw())
        routine="ROUTINE work(h:FILE) BEGIN OPEN FILE h('RW','KB:TPKB') text='old' n=77 seen=88 READ_KB(h,text,254,KC_DISPLAY,KC_ENTER_KEY,200,'',n,seen,status) CLOSE FILE h END work"
        p,_=program(create('FILE')+invoke(),context=ctx,routines=routine,sleep=sleeper);holder['p']=p;v=p.run()
        self.assertEqual((v['TEXT'],v['N'],v['SEEN'],v['STATUS']),('old',77,88,6));self.assertIsNone(ref(ctx).raw().owner)

    def test_direct_cancel_byname_expression_remains_invalid_source(self):
        with self.assertRaises(TranslationError):program(create('FILE')+" CANCEL FILE BYNAME('CACHE','ITEM',entry)")


class DynamicFileTransportTests(unittest.TestCase):
    def test_source_file_assignment_keeps_live_alias_until_close(self):
        routine="ROUTINE share(a:FILE;b:FILE) BEGIN OPEN FILE b('RO','data.txt') a=b READ a(n,CR) CLOSE FILE b END share"
        body=create('FILE')+create('FILE',name='OTHER')+"share(BYNAME('CACHE','ITEM',entry),BYNAME('CACHE','OTHER',seen))"
        v,ctx,_,_=execute(body,context=context(),routines=routine);self.assertEqual(v['N'],42);self.assertIs(ref(ctx).raw(),ref(ctx,'OTHER').raw());self.assertIsNone(ref(ctx).raw().owner)

    def test_file_attributes_and_custom_record_endings_use_existing_policy(self):
        routine="ROUTINE work(h:FILE) BEGIN SET_FILE_ATR(h,ATR_EOL,13) OPEN FILE h('WO','out.txt') WRITE h('hello',CR) CLOSE FILE h OPEN FILE h('RO','out.txt') READ h(text,CR) CLOSE FILE h END work"
        v,ctx,_,_=execute(create('FILE')+invoke(),context=context(),routines=routine);self.assertEqual((v['TEXT'],ctx.files.snapshot()['out.txt']),('hello',b'hello\r'))

    def test_readonly_device_write_failure_never_opens_handle(self):
        ctx=rt.ExecutionContext(files=rt.DeviceFiles({'RD:':{'capacity':1000,'read_only':True}},{'RD:data.txt':b'42\n'}))
        p,_=program(create('FILE')+invoke(),context=ctx,routines="ROUTINE work(h:FILE) BEGIN OPEN FILE h('WO','RD:data.txt') END work")
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIsNone(ref(ctx).raw().owner);self.assertEqual(ctx.files.snapshot()['RD:data.txt'],b'42\n')

    def test_closed_directory_file_restores_into_snapshot_bank_without_host_root(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'data.txt').write_bytes(b'42\n');ctx=rt.ExecutionContext(files=rt.DirectoryFiles(folder));execute(create('FILE')+invoke(),context=ctx,routines=READ)
            other=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())));self.assertIs(type(other.files),rt.MemoryFiles);self.assertIsNone(ref(other).raw().owner)
            v,_,_,_=execute(invoke(),context=other,routines=READ);self.assertEqual(v['N'],42)

    def test_canceled_serial_prefix_can_be_replayed_after_saved_restore(self):
        bank,ctx=serial(b'17');holder={}
        def sleeper(_):rt.cancel_file(holder['p']._state,ref(ctx).raw())
        p,_=program(create('FILE')+invoke(),context=ctx,routines=WAIT,sleep=sleeper);holder['p']=p;self.assertEqual(p.run()['STATUS'],6)
        other=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())));other.serial_streams.feed(2,b'\n')
        v,_,_,_=execute(invoke(),context=other,routines=WAIT);self.assertEqual((v['N'],v['STATUS']),(17,0))

    def test_renamed_file_reservation_and_policy_survive_saved_restore(self):
        body=create('INTEGER',name='DATA',dims=(32766,0,0))+create('FILE',pool=-1)+" RENAME_VAR('CACHE','ITEM','KEPT',status)"
        _,ctx,_,_=execute(body);other=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())));v,_,_,_=execute(create('FILE'),context=other)
        self.assertEqual(v['STATUS'],6);self.assertEqual(other.variables.metadata['CACHE','KEPT'],dict(group=0,memory_pool=-1))

    def test_partial_binary_read_retains_all_outputs_and_original_cursor(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'data.bin':struct.pack('<i',42)}))
        routine="ROUTINE work(h:FILE) BEGIN OPEN FILE h('RB','data.bin') n=77 m=88 READ h(n,m) CLOSE FILE h END work"
        p,_=program(create('FILE')+invoke(),context=ctx,routines=routine)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['M'],ref(ctx).raw().position),(77,88,0));ctx.files.close(ref(ctx).raw())

    def test_failed_rw_write_keeps_existing_bytes_and_cursor(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'out.txt':b'xy'},limit=2))
        routine="ROUTINE work(h:FILE) BEGIN OPEN FILE h('RW','out.txt') WRITE h('too long') END work"
        p,_=program(create('FILE')+invoke(),context=ctx,routines=routine)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((ctx.files.snapshot()['out.txt'],ref(ctx).raw().position),(b'xy',0));ctx.files.close(ref(ctx).raw())

    def test_malformed_file_schema_is_rejected_before_descriptor_allocation(self):
        saved=dict(variables=[dict(program='CACHE',path='ITEM',type=['FILE',1],value={'closed':True},creation=dict(group=0,memory_pool=0))])
        with patch('karel2py.dynamic.restore_file_descriptor',side_effect=AssertionError('must not allocate')),self.assertRaises(ValueError):rt.ExecutionContext.from_config(saved)

    def test_restored_descriptor_does_not_implicitly_supply_file_service(self):
        _,ctx,_,_=execute(create('FILE'));other=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertIsNone(other.files);p,_=program(invoke(),context=other,routines=READ)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIsNone(ref(other).raw().owner)


if __name__=='__main__':unittest.main()
