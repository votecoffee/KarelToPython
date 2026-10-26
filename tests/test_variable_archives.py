"""Authored VR snapshots, guarded restoration and explicit DRAM save points."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from karel2py import runtime as rt,translate,translate_project
from karel2py.lexer import TranslationError
from karel2py.variable_archives import FORMAT
from tests.test_extended_services import compile_program,run,pose


def context(*,limit=16*1024*1024,program_limit=256,calls=None,files=None):
    ctx=rt.ExecutionContext(variable_archives=rt.VariableArchives(limit=limit,program_limit=program_limit,calls=calls),
        files=rt.MemoryFiles() if files is None else files)
    ctx.variables.define('CACHE','VALUE',('INTEGER',),17);return ctx


def execute(ctx,body,**options):return run(body,context=ctx,**options)


def envelope(program='CACHE',variables=None,calls=None):
    return dict(format=FORMAT,program=program,variables=variables if variables is not None else {'VALUE':{'type':['INTEGER'],'value':17}},excluded=[],calls=calls or [])


def install(ctx,row=None,path='FR:CACHE.VR'):
    ctx.files.files[path]=bytearray(ctx.variable_archives.encode(envelope() if row is None else row))


class VariableArchiveSourceTests(unittest.TestCase):
    def test_save_clear_load_and_option_ignored_for_vr(self):
        ctx=context();data=execute(ctx,"SAVE('CACHE','FR:CACHE.VR',s) CLEAR('CACHE.VR',s) LOAD('FR:CACHE.VR',99,s) GET_VAR(e,'CACHE','VALUE',n,s)",decl='e,n,s:INTEGER')
        self.assertEqual((data['S'],data['N']),(0,17));self.assertEqual(ctx.variables.bindings['CACHE','VALUE'].raw(),17)

    def test_load_into_fresh_namespace_uses_archive_internal_identity(self):
        ctx=context();execute(ctx,"SAVE('CACHE','FR:ALIAS.VR',s)");saved=ctx.files.snapshot()
        fresh=rt.ExecutionContext(variable_archives=rt.VariableArchives(),files=rt.MemoryFiles(saved))
        self.assertEqual(execute(fresh,"LOAD('FR:ALIAS.VR',0,s)")['S'],0)
        self.assertEqual(fresh.variables.bindings['CACHE','VALUE'].raw(),17);self.assertNotIn(('ALIAS','VALUE'),fresh.variables.bindings)

    def test_existing_values_overwrite_but_unlisted_roots_are_preserved(self):
        ctx=context();install(ctx);ctx.variables.define('CACHE','EXTRA',('INTEGER',),99);ctx.variables.bindings['CACHE','VALUE'].set(5)
        self.assertEqual(execute(ctx,"LOAD('FR:CACHE.VR',0,s)")['S'],0)
        self.assertEqual(ctx.variables.bindings['CACHE','EXTRA'].raw(),99);self.assertEqual(ctx.variables.bindings['CACHE','VALUE'].raw(),17)

    def test_save_refuses_existing_file_and_missing_namespace_returns_status(self):
        ctx=context();ctx.files.files['FR:CACHE.VR']=bytearray(b'original')
        self.assertEqual(execute(ctx,"SAVE('CACHE','FR:CACHE.VR',s)")['S'],3);self.assertEqual(ctx.files.files['FR:CACHE.VR'],b'original')
        self.assertEqual(execute(ctx,"SAVE('MISSING','FR:M.VR',s)")['S'],1)
        self.assertEqual(execute(ctx,"CLEAR('MISSING.VR',s)")['S'],1)

    def test_clear_resets_values_and_preserves_references_types_and_metadata(self):
        ctx=context();reference=ctx.variables.bindings['CACHE','VALUE']
        self.assertEqual(execute(ctx,"CLEAR('CACHE.VR',s)")['S'],0)
        self.assertIs(ctx.variables.bindings['CACHE','VALUE'],reference);self.assertIs(reference.raw(),rt.UNINITIALIZED)
        self.assertEqual(reference.spec,('INTEGER',))

    def test_own_globals_can_restore_with_routine_local_status(self):
        ctx=context();p,_=compile_program('n=7 transact',decl='n:INTEGER',context=ctx,
            routines="ROUTINE transact VAR s:INTEGER BEGIN SAVE('T','FR:T.VR',s) n=99 LOAD('FR:T.VR',0,s) END transact")
        self.assertEqual(p.run()['N'],7)

    def test_global_status_overlap_rejects_before_any_restoration(self):
        ctx=context();p,_=compile_program("n=7 s=0 SAVE('T','FR:T.VR',s) n=99 LOAD('FR:T.VR',0,s)",context=ctx)
        data=p.run();self.assertEqual((data['N'],data['S']),(99,4))

    def test_array_status_cell_overlap_rejects_before_data_changes(self):
        ctx=context();p,_=compile_program("a[1]=7 s=0 SAVE('T','FR:T.VR',s) a[1]=99 LOAD('FR:T.VR',0,a[1])",decl='a:ARRAY[2] OF INTEGER s:INTEGER',context=ctx)
        data=p.run();self.assertEqual(data['A'][0],4);self.assertEqual(data['S'],0)
        self.assertIs(p._state.values['A'].values[1],rt.UNINITIALIZED)

    def test_field_aliases_survive_whole_array_restore(self):
        ctx=context();p,_=compile_program('data[1]=7 data[2]=8 observed=0 stash data[1]=99 restore(data[1])',
            decl='data:series observed:INTEGER',prefix='TYPE series=ARRAY[2] OF INTEGER',context=ctx,
            routines="ROUTINE stash VAR s:INTEGER BEGIN SAVE('T','FR:T.VR',s) END stash ROUTINE restore(alias:INTEGER) VAR s:INTEGER BEGIN LOAD('FR:T.VR',0,s) observed=alias END restore")
        original=p._state.values['DATA'];data=p.run();self.assertEqual((data['DATA'],data['OBSERVED']),([7,8],7));self.assertIs(p._state.values['DATA'],original)

    def test_resources_are_excluded_and_remain_live_storage(self):
        ctx=context();p,_=compile_program('n=7 stash',decl='n:INTEGER f:FILE trail:PATH',context=ctx,
            routines="ROUTINE stash VAR s:INTEGER BEGIN SAVE('T','FR:T.VR',s) END stash")
        handle=p._state.values['F'];path=p._state.values['TRAIL'];p.run();row=json.loads(bytes(ctx.files.files['FR:T.VR']))
        self.assertEqual(row['excluded'],['F','TRAIL']);self.assertEqual(set(row['variables']),{'N'})
        self.assertIs(p._state.values['F'],handle);self.assertIs(p._state.values['TRAIL'],path)

    def test_imported_globals_are_excluded_from_the_importers_archive(self):
        ctx=context();project=translate_project({'main':'PROGRAM MAIN VAR shared FROM OWNER:INTEGER n:INTEGER ROUTINE stash VAR s:INTEGER BEGIN SAVE(\'MAIN\',\'FR:MAIN.VR\',s) END stash BEGIN n=7 stash END MAIN',
            'owner':'PROGRAM OWNER VAR shared:INTEGER BEGIN shared=99 END OWNER'}).instantiate(context=ctx)
        project.run('MAIN');row=json.loads(bytes(ctx.files.files['FR:MAIN.VR']))
        self.assertEqual(row['excluded'],['SHARED']);self.assertEqual(set(row['variables']),{'N'})

    def test_declared_and_dynamic_root_type_mismatch_is_atomic(self):
        ctx=context();row=envelope(variables={'VALUE':{'type':['REAL'],'value':1.5},'NEW':{'type':['INTEGER'],'value':8}});install(ctx,row)
        before=set(ctx.variables.bindings);self.assertEqual(execute(ctx,"LOAD('FR:CACHE.VR',0,s)")['S'],6)
        self.assertEqual(ctx.variables.bindings['CACHE','VALUE'].raw(),17);self.assertEqual(set(ctx.variables.bindings),before)

    def test_archive_cannot_replace_an_import_or_file_declaration(self):
        for variables in ({'F':{'type':['INTEGER'],'value':1}}, {'TRAIL':{'type':['INTEGER'],'value':1}}):
            ctx=context();install(ctx,envelope('T',variables),'FR:T.VR')
            p,_=compile_program("LOAD('FR:T.VR',0,s)",decl='s:INTEGER f:FILE trail:PATH',context=ctx)
            self.assertEqual(p.run()['S'],4)

    def test_sparse_and_overlapping_namespace_bindings_reject(self):
        ctx=context();ctx.variables.bind('CACHE','ALIAS',ctx.variables.bindings['CACHE','VALUE'])
        self.assertEqual(execute(ctx,"SAVE('CACHE','FR:CACHE.VR',s)")['S'],4);self.assertEqual(ctx.files.files,{})
        ctx=context();ctx.variables.bind('CACHE','ORPHAN[1]',rt.Reference(('INTEGER',),{'v':7},'v'))
        self.assertEqual(execute(ctx,"SAVE('CACHE','FR:CACHE.VR',s)")['S'],4)
        ctx=context();spec=('STRUCTURE','ITEM',(('FIELD',('INTEGER',)),));value=rt.initial_value(spec)
        ctx.variables.bind('CACHE','DATA',rt.Reference(spec,{'v':value},'v'))
        ctx.variables.bind('CACHE','DATA.FIELD',rt.Reference(('INTEGER',),{'v':99},'v'))
        self.assertEqual(execute(ctx,"SAVE('CACHE','FR:CACHE.VR',s)")['S'],4)

    def test_underscore_program_names_and_case_insensitive_identity(self):
        ctx=context();ctx.variables.define('_CACHE','VALUE',('INTEGER',),19)
        self.assertEqual(execute(ctx,"SAVE('_cache','FR:_CACHE.VR',s) CLEAR('_CACHE.VR',s) LOAD('FR:_CACHE.VR',0,s)")['S'],0)
        self.assertEqual(ctx.variables.bindings['_CACHE','VALUE'].raw(),19)

    def test_missing_services_do_not_fall_back_to_tp_or_host_files(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'variable_archives'):run("SAVE_DRAM('T',s)")
        with self.assertRaisesRegex(rt.KarelRuntimeError,'variable_archives'):run("LOAD('FR:A.VR',0,s)")
        ctx=rt.ExecutionContext(variable_archives=rt.VariableArchives());ctx.variables.define('CACHE','VALUE',('INTEGER',),7)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'files'):execute(ctx,"SAVE('CACHE','FR:A.VR',s)")


class VariableArchiveDataTests(unittest.TestCase):
    def test_partial_arrays_records_and_unknown_bytes_roundtrip(self):
        ctx=context();spec=('STRUCTURE','PACKET',(('BYTES',('ARRAY',3,('BYTE',))),('COUNT',('INTEGER',)),('LABEL',('STRING',8))))
        value=rt.initial_value(spec);value.values['BYTES'].values[0]=255;value.values['COUNT']=7
        reference=rt.Reference(spec,{'v':value},'v');ctx.variables.bind('CACHE','PACKET',reference)
        before=rt.snapshot_value(value);self.assertEqual(execute(ctx,"SAVE('CACHE','FR:CACHE.VR',s) CLEAR('CACHE.VR',s) LOAD('FR:CACHE.VR',0,s)")['S'],0)
        self.assertEqual(rt.snapshot_value(reference.raw()),before);self.assertIs(reference.raw(),value)

    def test_whole_missing_aggregate_restores_into_existing_field_alias_storage(self):
        ctx=context();spec=('ARRAY',2,('INTEGER',));array=rt.Array(spec);array.values[:]=[7,8]
        ctx.variables.bind('CACHE','DATA',rt.Reference(spec,{'v':array},'v'));alias=rt.Reference(('INTEGER',),array.values,0)
        row=envelope(variables={'DATA':{'type':['ARRAY',2,['INTEGER']],'value':{'uninitialized':True}}});install(ctx,row)
        self.assertEqual(execute(ctx,"LOAD('FR:CACHE.VR',0,s)")['S'],0)
        self.assertIs(ctx.variables.bindings['CACHE','DATA'].raw(),array);self.assertIs(alias.raw(),rt.UNINITIALIZED)

    def test_callback_backed_root_storage_is_not_mutated(self):
        class Storage(dict):
            def __setitem__(self,key,value):raise AssertionError('Unexpected callback')
        ctx=context();storage=Storage(value=99);ctx.variables.bind('CACHE','VALUE',rt.Reference(('INTEGER',),storage,'value'));install(ctx)
        self.assertEqual(execute(ctx,"LOAD('FR:CACHE.VR',0,s)")['S'],4);self.assertEqual(storage['value'],99)
        self.assertEqual(execute(ctx,"SAVE('CACHE','FR:OTHER.VR',s)")['S'],4);self.assertNotIn('FR:OTHER.VR',ctx.files.files)

    def test_partial_joint_axes_and_config_fields_roundtrip(self):
        ctx=context();joint=rt.JointPosition(('JOINTPOS',3));joint.values[0]=1.5
        ctx.variables.bind('CACHE','JOINT',rt.Reference(joint.spec,{'v':joint},'v'))
        config=rt.initial_value(('CONFIG',));ctx.variables.bind('CACHE','CONF',rt.Reference(('CONFIG',),{'v':config},'v'))
        before=rt.snapshot_value(joint);self.assertEqual(execute(ctx,"SAVE('CACHE','FR:CACHE.VR',s) CLEAR('CACHE.VR',s) LOAD('FR:CACHE.VR',0,s)")['S'],0)
        self.assertEqual(rt.snapshot_value(joint),before)

    def test_logical_queue_restores_identity_and_drops_runtime_buffer_binding(self):
        ctx=context();queue=rt.QueueValue();queue.initialized=True;queue.sequence=1;queue.entries=[(1,17)]
        queue.buffer=rt.Array(('ARRAY',3,('INTEGER',)));ctx.variables.bind('CACHE','QUEUE',rt.Reference(('QUEUE_TYPE',),{'v':queue},'v'))
        self.assertEqual(execute(ctx,"SAVE('CACHE','FR:CACHE.VR',s) CLEAR('CACHE.VR',s) LOAD('FR:CACHE.VR',0,s)")['S'],0)
        self.assertEqual(queue.entries,[(1,17)]);self.assertTrue(queue.initialized);self.assertIsNone(queue.buffer)
        self.assertIs(ctx.variables.bindings['CACHE','QUEUE'].raw(),queue)

    def test_dynamic_creation_metadata_is_reconstructed_for_new_roots(self):
        ctx=context();execute(ctx,"CREATE_VAR('CACHE','DATA','','INTEGER',0,0,0,0,s) SET_VAR(e,'CACHE','DATA',23,s) SAVE('CACHE','FR:CACHE.VR',s)",decl='e,s:INTEGER')
        fresh=rt.ExecutionContext(variable_archives=rt.VariableArchives(),files=rt.MemoryFiles(ctx.files.snapshot()))
        self.assertEqual(execute(fresh,"LOAD('FR:CACHE.VR',0,s)")['S'],0)
        self.assertEqual(fresh.variables.metadata['CACHE','DATA'],{'group':0,'memory_pool':0})
        self.assertEqual(fresh.variables.bindings['CACHE','DATA'].raw(),23)

    def test_invalid_schema_and_noncanonical_payloads_reject_before_allocation(self):
        variants=[{'VALUE':{'type':['INTEGER'],'value':{'uninitialized':1}}}, {'VALUE':{'type':['BYTE'],'value':{'unknown_byte':1}}},
            {'VALUE':{'type':['ARRAY',32768,['INTEGER']],'value':[]}},
            {'VALUE':{'type':['STRING',2],'value':'long'}},{'VALUE':{'type':['BYTE'],'value':{'unknown_byte':False}}},
            {'VALUE':{'type':['REAL'],'value':{'unknown_byte':True}}},{'VALUE':{'type':['FILE'],'value':{}}}]
        for variables in variants:
            ctx=context();install(ctx,envelope(variables=variables));self.assertEqual(execute(ctx,"LOAD('FR:CACHE.VR',0,s)")['S'],6)
            self.assertEqual(ctx.variables.bindings['CACHE','VALUE'].raw(),17)

    def test_invalid_json_duplicate_keys_and_native_vr_bytes_reject(self):
        for data in (b'native\0VR',b'{"program":"A","program":"B"}',b'NaN',b'['*33+b'0'+b']'*33,b'\xff'):
            ctx=context();ctx.files.files['FR:CACHE.VR']=bytearray(data)
            self.assertEqual(execute(ctx,"LOAD('FR:CACHE.VR',0,s)")['S'],6)
            self.assertEqual(ctx.variables.bindings['CACHE','VALUE'].raw(),17)

    def test_creation_policy_mismatch_rejects_without_changing_values(self):
        ctx=context();execute(ctx,"CREATE_VAR('CACHE','DATA','','INTEGER',0,0,0,0,s)")
        row=envelope(variables={'DATA':{'type':['INTEGER'],'value':5,'creation':{'group':0,'memory_pool':-1}}});install(ctx,row)
        self.assertEqual(execute(ctx,"LOAD('FR:CACHE.VR',0,s)")['S'],6);self.assertIs(ctx.variables.bindings['CACHE','DATA'].raw(),rt.UNINITIALIZED)


class VariableArchiveGuardTests(unittest.TestCase):
    def test_vr_writes_and_dynamic_filenames_cannot_modify_active_for_counters(self):
        for call in ("LOAD('FR:CACHE.VR',0,s)","CLEAR('CACHE.VR',s)","PROG_RESTORE('FR:CACHE.VR',s)","PROG_CLEAR('CACHE',PBR_VRTYPE,s)","LOAD(filename,0,s)"):
            with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO '+call+' ENDFOR',decl='n,s:INTEGER filename:STRING[40]')
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
        compile_program("FOR n=1 TO 2 DO LOAD('FR:A.TP',0,s) CLEAR('A.TP',s) PROG_CLEAR('A',PBR_ALLTYPE,s) ENDFOR")

    def test_transitive_restore_effects_guard_global_counters(self):
        with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO restore ENDFOR',routines="ROUTINE restore VAR status:INTEGER BEGIN LOAD('FR:T.VR',0,status) END restore")
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_condition_restore_action_cannot_indirectly_change_a_for_counter(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program("CONDITION[1]: WHEN TRUE DO LOAD('FR:T.VR',0,s) ENDCONDITION ENABLE CONDITION[1] FOR n=1 TO 2 DO ENDFOR",cooperative=True)
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_foreign_paused_task_and_its_aliases_are_protected(self):
        ctx=context();result=translate('PROGRAM TARGET VAR n:INTEGER BEGIN n=99 PAUSE END TARGET',cooperative=True)
        namespace={'__name__':'paused_target'};exec(result.python_source,namespace);target=namespace['Program'](context=ctx)
        with self.assertRaises(rt.KarelPause):target.run()
        install(ctx,envelope('TARGET',{'N':{'type':['INTEGER'],'value':17}}),'FR:TARGET.VR')
        self.assertEqual(execute(ctx,"LOAD('FR:TARGET.VR',0,s)")['S'],4);self.assertEqual(target.snapshot()['N'],99)
        ctx.variables.bind('CACHE','VALUE',target._state.reference('N'));install(ctx)
        self.assertEqual(execute(ctx,"LOAD('FR:CACHE.VR',0,s)")['S'],4);self.assertEqual(target.snapshot()['N'],99)

    def test_connected_timer_storage_cannot_be_restored(self):
        ctx=context();install(ctx,envelope('T',{'N':{'type':['INTEGER'],'value':17}}),'FR:T.VR')
        p,_=compile_program("n=99 CONNECT TIMER TO n LOAD('FR:T.VR',0,s)",context=ctx,clock_us=lambda:0)
        self.assertEqual(p.run()['S'],4);self.assertEqual(p.snapshot()['N'],99)

    def test_protected_metadata_blocks_writes_but_readonly_saving_works(self):
        ctx=context();ctx.program_attributes=rt.ProgramAttributes({'CACHE':{'loaded':True,'attributes':{'AT_PROTECT':2}}})
        self.assertEqual(execute(ctx,"SAVE('CACHE','FR:CACHE.VR',s)")['S'],0)
        self.assertEqual(execute(ctx,"CLEAR('CACHE.VR',s)")['S'],4);self.assertEqual(execute(ctx,"LOAD('FR:CACHE.VR',0,s)")['S'],4)

    def test_metadata_initialization_refreshes_without_fabricating_loaded_code(self):
        ctx=context();ctx.program_attributes=rt.ProgramAttributes({'CACHE':{'loaded':False,'initialized':True,'attributes':{'AT_OWNER':'owner'}}})
        execute(ctx,"SAVE('CACHE','FR:CACHE.VR',s) CLEAR('CACHE.VR',s)");self.assertFalse(ctx.program_attributes.record('CACHE')['initialized'])
        self.assertEqual(execute(ctx,"LOAD('FR:CACHE.VR',0,s)")['S'],0)
        row=ctx.program_attributes.record('CACHE');self.assertTrue(row['initialized']);self.assertFalse(row['loaded']);self.assertEqual(row['attributes'],{'AT_OWNER':'owner'})


class VariableArchiveBatchTests(unittest.TestCase):
    def test_recursive_vr_backup_clear_restore_uses_archived_dependency_graph(self):
        ctx=context(calls={'CACHE':['CHILD'],'CHILD':[]});ctx.variables.define('CHILD','TEXT',('STRING',8),'ready')
        self.assertEqual(execute(ctx,"PROG_BACKUP('FR:batch/CACHE',PBR_VRTYPE,0,TRUE,s) PROG_CLEAR('CACHE',PBR_VRTYPE,s)")['S'],0)
        ctx.variable_archives.calls={}
        self.assertEqual(execute(ctx,"PROG_RESTORE('FR:batch/CACHE.VR',s)")['S'],0)
        self.assertEqual(ctx.variables.bindings['CACHE','VALUE'].raw(),17);self.assertEqual(ctx.variables.bindings['CHILD','TEXT'].raw(),'ready')
        self.assertEqual(ctx.variable_archives.calls,{'CACHE':['CHILD'],'CHILD':[]})

    def test_pbr_pctype_is_variable_only_and_cycles_are_bounded(self):
        ctx=context(calls={'CACHE':['CHILD'],'CHILD':['CACHE']});ctx.variables.define('CHILD','VALUE',('INTEGER',),5)
        self.assertEqual(execute(ctx,"PROG_BACKUP('FR:CACHE',PBR_PCTYPE,0,TRUE,s) PROG_CLEAR('CACHE',PBR_PCTYPE,s) PROG_RESTORE('FR:CACHE.VR',s)")['S'],0)
        self.assertEqual(set(ctx.files.files),{'FR:CACHE.VR','FR:CHILD.VR'})

    def test_missing_restore_dependency_preserves_values_and_call_graph(self):
        ctx=context(calls={'CACHE':['MISSING']});install(ctx,envelope(calls=['MISSING']));before=ctx.variable_archives.to_config()
        self.assertEqual(execute(ctx,"PROG_RESTORE('FR:CACHE.VR',s)")['S'],1)
        self.assertEqual(ctx.variables.bindings['CACHE','VALUE'].raw(),17);self.assertEqual(ctx.variable_archives.to_config(),before)

    def test_late_type_failure_preserves_every_namespace(self):
        ctx=context(calls={'CACHE':['CHILD']});ctx.variables.define('CHILD','VALUE',('REAL',),1.5)
        install(ctx,envelope(calls=['CHILD']));install(ctx,envelope('CHILD',{'VALUE':{'type':['INTEGER'],'value':5}}),'FR:CHILD.VR')
        ctx.variables.bindings['CACHE','VALUE'].set(99)
        self.assertEqual(execute(ctx,"PROG_RESTORE('FR:CACHE.VR',s)")['S'],6)
        self.assertEqual(ctx.variables.bindings['CACHE','VALUE'].raw(),99);self.assertEqual(ctx.variables.bindings['CHILD','VALUE'].raw(),1.5)

    def test_protected_backup_filter_and_recursive_clear_skip(self):
        ctx=context(calls={'CACHE':['CHILD']});ctx.variables.define('CHILD','VALUE',('INTEGER',),5)
        ctx.program_attributes=rt.ProgramAttributes({'CHILD':{'loaded':True,'attributes':{'AT_PROTECT':2}}})
        self.assertEqual(execute(ctx,"PROG_BACKUP('FR:CACHE',PBR_VRTYPE,0,FALSE,s)")['S'],0);self.assertEqual(set(ctx.files.files),{'FR:CACHE.VR'})
        self.assertEqual(execute(ctx,"PROG_CLEAR('CACHE',PBR_VRTYPE,s)")['S'],0);self.assertEqual(ctx.variables.bindings['CHILD','VALUE'].raw(),5)

    def test_wildcard_save_preflights_all_existing_targets(self):
        ctx=context();ctx.files.files['FR:CACHE.VR']=bytearray(b'original')
        self.assertEqual(execute(ctx,"SAVE('*','FR:*.VR',s)")['S'],3);self.assertEqual(set(ctx.files.files),{'FR:CACHE.VR'})

    def test_virtual_device_aggregate_quota_and_garbage_accounting(self):
        files=rt.DeviceFiles({'FR:':{'capacity':100,'retain_deleted':True}});ctx=context(files=files)
        self.assertEqual(execute(ctx,"SAVE('CACHE','FR:CACHE.VR',s)")['S'],5);self.assertEqual(files.files,{})
        ctx=context(files=rt.DeviceFiles({'FR:':{'capacity':10000,'retain_deleted':True}}));body="PROG_BACKUP('FR:CACHE',PBR_VRTYPE,0,TRUE,s)"
        self.assertEqual(execute(ctx,body)['S'],0);size=len(ctx.files.files['FR:CACHE.VR']);ctx.variables.bindings['CACHE','VALUE'].set(99)
        self.assertEqual(execute(ctx,body)['S'],0);self.assertEqual(ctx.files._volumes['FR']['garbage'],size)

    def test_busy_and_readonly_archive_files_prevent_mutation(self):
        ctx=context();install(ctx);handle=rt.FileHandle();ctx.files.open(handle,'R','FR:CACHE.VR')
        self.assertEqual(execute(ctx,"LOAD('FR:CACHE.VR',0,s)")['S'],4);ctx.files.close(handle)
        ctx=context(files=rt.DeviceFiles({'FR:':{'capacity':10000,'read_only':True}}))
        self.assertEqual(execute(ctx,"SAVE('CACHE','FR:CACHE.VR',s)")['S'],4);self.assertEqual(ctx.files.files,{})

    def test_directory_files_are_rejected_without_host_writes(self):
        from karel2py.storage import DirectoryFiles
        with tempfile.TemporaryDirectory() as folder:
            ctx=context(files=DirectoryFiles(folder));self.assertEqual(execute(ctx,"SAVE('CACHE','A.VR',s)")['S'],4)
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_byte_leaf_count_and_graph_limits_are_preflighted(self):
        ctx=context(limit=16);self.assertEqual(execute(ctx,"SAVE('CACHE','FR:CACHE.VR',s)")['S'],5);self.assertEqual(ctx.files.files,{})
        ctx=context(program_limit=1);install(ctx,envelope('NEW'))
        self.assertEqual(execute(ctx,"LOAD('FR:CACHE.VR',0,s)")['S'],5);self.assertNotIn(('NEW','VALUE'),ctx.variables.bindings)
        ctx=context();row=envelope(variables={'A':{'type':['ARRAY',20000,['INTEGER']],'value':[]},'B':{'type':['ARRAY',20000,['INTEGER']],'value':[]}});install(ctx,row)
        self.assertEqual(execute(ctx,"LOAD('FR:CACHE.VR',0,s)")['S'],6)


class VariableDramTests(unittest.TestCase):
    def test_save_dram_and_explicit_host_restore_roundtrip(self):
        ctx=context();p,_=compile_program("SAVE_DRAM('CACHE',s)",context=ctx);self.assertEqual(p.run()['S'],0)
        ctx.variables.bindings['CACHE','VALUE'].set(99)
        self.assertEqual(ctx.variable_archives.restore_dram(p._state,'CACHE'),0);self.assertEqual(ctx.variables.bindings['CACHE','VALUE'].raw(),17)
        self.assertEqual(ctx.files.files,{})

    def test_host_dram_restore_uses_pythonic_real_and_cartesian_numeric_policy(self):
        ctx=context();ctx.program_attributes=rt.ProgramAttributes({'CACHE':{'loaded':False}})
        ctx.variables.define('CACHE','REAL',('REAL',),1.0e100)
        point=pose(1,2,3);point.values['X']=1.0e100;ctx.variables.define('CACHE','POSE',('XYZWPR',),point)
        p,_=compile_program("SAVE_DRAM('CACHE',s)",context=ctx);self.assertEqual(p.run()['S'],0)
        ctx.variables.bindings['CACHE','REAL'].storage['value']=99.0
        ctx.variables.bindings['CACHE','POSE'].raw().values['X']=99.0
        before=rt._numeric_mode.get();self.assertEqual(ctx.variable_archives.restore_dram(p._state,'CACHE'),0)
        self.assertEqual(rt._numeric_mode.get(),before)
        self.assertEqual(ctx.variables.bindings['CACHE','REAL'].raw(),1.0e100)
        self.assertEqual(ctx.variables.bindings['CACHE','POSE'].raw().values['X'],1.0e100)

    def test_dram_context_roundtrip_preserves_original_snapshots_and_values(self):
        ctx=context();p,_=compile_program("SAVE_DRAM('CACHE',s)",context=ctx);p.run();saved=json.loads(json.dumps(ctx.to_config()))
        restored=rt.ExecutionContext.from_config(saved);self.assertEqual(restored.to_config(),saved)
        restored.variables.bindings['CACHE','VALUE'].set(99);fresh,_=compile_program('n=0',context=restored)
        self.assertEqual(restored.variable_archives.restore_dram(fresh._state,'CACHE'),0)
        self.assertEqual(restored.variables.bindings['CACHE','VALUE'].raw(),17)

    def test_failed_save_dram_preserves_the_previous_snapshot(self):
        ctx=context();p,_=compile_program("SAVE_DRAM('CACHE',s)",context=ctx);p.run();before=deepcopy(ctx.variable_archives.flash)
        ctx.variable_archives.limit=1;self.assertEqual(execute(ctx,"SAVE_DRAM('CACHE',s)")['S'],5)
        self.assertEqual(ctx.variable_archives.flash,before)

    def test_missing_dram_snapshot_and_invalid_configuration_are_explicit(self):
        ctx=context();p,_=compile_program('n=0',context=ctx);self.assertEqual(ctx.variable_archives.restore_dram(p._state,'MISSING'),1)
        for config in ({'extra':1},{'limit':0},{'program_limit':True},{'calls':{'a':[],'A':[]}}, {'calls':{'A':['B','b']}}):
            with self.assertRaises(ValueError):rt.VariableArchives.from_config(config)
        with self.assertRaises(TypeError):rt.ExecutionContext(variable_archives={})

    def test_invalid_saved_flash_schemas_and_budgets_reject(self):
        for flash in ({'CACHE':envelope('OTHER')},{'cache':envelope('CACHE')},{'CACHE':{**envelope(),'extra':1}}):
            with self.assertRaises(ValueError):rt.VariableArchives.from_config({'flash':flash})
        with self.assertRaises(ValueError):rt.VariableArchives.from_config({'limit':10,'flash':{'CACHE':envelope()}})

    def test_saved_context_and_flash_export_are_detached(self):
        ctx=context();execute(ctx,"SAVE_DRAM('CACHE',s)");saved=ctx.variable_archives.to_config();saved['flash']['CACHE']['variables']['VALUE']['value']=99
        self.assertEqual(ctx.variable_archives.flash['CACHE']['variables']['VALUE']['value'],17)

    def test_source_user_override_and_output_counter_guards_remain(self):
        self.assertEqual(run('SAVE_DRAM(7)',routines='ROUTINE SAVE_DRAM(value:INTEGER) BEGIN n=value END SAVE_DRAM')['N'],7)
        with self.assertRaises(TranslationError) as caught:compile_program("FOR n=1 TO 2 DO SAVE_DRAM('T',n) ENDFOR")
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_report_identifies_vr_forms_dram_and_controller_boundary(self):
        _,result=compile_program("SAVE('CACHE','A.VR',s) LOAD('A.VR',0,s) CLEAR('CACHE.VR',s) PROG_BACKUP('A',PBR_VRTYPE,0,TRUE,s) PROG_CLEAR('A',PBR_VRTYPE,s) PROG_RESTORE('A.VR',s) SAVE_DRAM('CACHE',s)")
        policy=result.report['variable_archive_policy'];self.assertFalse(policy['controller_validated'])
        self.assertEqual(len(policy['procedures']),7);self.assertEqual(len(policy['calls']),7)

    def test_dram_save_does_not_install_an_automatic_powerup_hook(self):
        ctx=context();execute(ctx,"SAVE_DRAM('CACHE',s)");ctx.variables.bindings['CACHE','VALUE'].set(99)
        p,_=compile_program('PAUSE n=0',cooperative=True,context=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        p.powerup();self.assertEqual(ctx.variables.bindings['CACHE','VALUE'].raw(),99)


if __name__=='__main__':unittest.main()
