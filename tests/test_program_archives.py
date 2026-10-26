"""Authored portable TP archive and recursive dependency regressions."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from karel2py import runtime as rt
from karel2py.archives import encode,FORMAT
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run


def context(programs=None,*,calls=None,files=None,**options):
    return rt.ExecutionContext(teach_programs=rt.TeachPrograms(programs if programs is not None else {
        'A':{'instructions':['opaque instruction'],'numeric_registers':{'1':7},'string_registers':{'1':'part'}}},calls=calls,**options),
        files=rt.MemoryFiles() if files is None else files)


def execute(ctx,body,**options):return run(body,context=ctx,**options)['S']


def chain(**options):
    return context({'A':{'instructions':['not parsed']},'B':{'type':'JB'},'C':{'type':'PR'}},calls={'A':['B'],'B':['C'],'C':[]},**options)


class ProgramArchiveSourceTests(unittest.TestCase):
    def test_save_clear_load_retains_positions_headers_and_all_register_banks(self):
        joints=rt.JointPosition(('JOINTPOS',3));joints.values[:]=[1.,2.,3.]
        ctx=context({'A':{'instructions':['opaque'], 'attributes':{'AT_COMMENT':'authored'},'numeric_registers':{'1':1.5},
            'string_registers':{'1':'part'},'positions':[{'group':1,'number':1,'value':joints,'uframe':2,'utool':3}],
            'comments':{'1':'pick'},'position_registers':[{'group':1,'number':2,'value':joints,'uframe':4,'utool':5}]}},calls={'A':[]})
        before=ctx.teach_programs.to_config()
        self.assertEqual(execute(ctx,"SAVE('A','FR:A.TP',s) CLEAR('A.TP',s) LOAD('FR:A.TP',0,s)"),0)
        self.assertEqual(ctx.teach_programs.to_config(),before)
        self.assertEqual(json.loads(bytes(ctx.files.files['FR:A.TP']))['format'],FORMAT)

    def test_save_refuses_existing_target_without_modifying_file(self):
        ctx=context(files=rt.MemoryFiles({'FR:A.TP':b'original'}))
        self.assertEqual(execute(ctx,"SAVE('A','FR:A.TP',s)"),3);self.assertEqual(ctx.files.files['FR:A.TP'],b'original')

    def test_load_overwrite_option_one_and_other_values_refuse_existing_record(self):
        ctx=context();execute(ctx,"SAVE('A','FR:A.TP',s)");ctx.teach_programs._programs['A']['instructions']=['changed']
        for option in (0,2,-1):self.assertEqual(execute(ctx,f"LOAD('FR:A.TP',{option},s)"),3)
        self.assertEqual(execute(ctx,"LOAD('FR:A.TP',1,s)"),0)
        self.assertEqual(ctx.teach_programs._programs['A']['instructions'],['opaque instruction'])

    def test_filename_alias_preserves_internal_program_identity(self):
        ctx=context();self.assertEqual(execute(ctx,"SAVE('A','FR:alias.TP',s) CLEAR('A',s) LOAD('FR:alias.TP',0,s)"),0)
        self.assertEqual(ctx.teach_programs.entries,(('A','TP'),));self.assertIn('FR:ALIAS.TP',ctx.files.files)

    def test_wildcard_save_creates_individual_program_files(self):
        ctx=chain();self.assertEqual(execute(ctx,"SAVE('*','FR:batch/*.TP',s)"),0)
        self.assertEqual(set(ctx.files.files),{'FR:batch/A.TP','FR:batch/B.TP','FR:batch/C.TP'})

    def test_unsupported_native_types_do_not_mutate_logical_programs(self):
        for suffix in ('PC','VR','IO'):
            for body in (f"SAVE('A','FR:A.{suffix}',s)",f"LOAD('FR:A.{suffix}',0,s)",f"CLEAR('A.{suffix}',s)"):
                ctx=context();before=ctx.teach_programs.to_config();self.assertEqual(execute(ctx,body),4)
                self.assertEqual(ctx.teach_programs.to_config(),before);self.assertEqual(ctx.files.files,{})

    def test_invalid_paths_and_clear_device_paths_reject(self):
        for path in ('../A.TP','FR:../A.TP','/A.TP','PIP:A.TP','S1:A.TP','FR:a//A.TP'):
            ctx=context();self.assertEqual(execute(ctx,f"SAVE('A','{path}',s)"),2,path);self.assertEqual(ctx.files.files,{})
        ctx=context();self.assertEqual(execute(ctx,"CLEAR('FR:A.TP',s)"),2)

    def test_missing_services_and_programs_fail_without_fallback(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'teach_programs'):run("CLEAR('A.TP',s)")
        ctx=rt.ExecutionContext(teach_programs=rt.TeachPrograms({'A':{}}))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'files'):execute(ctx,"SAVE('A','FR:A.TP',s)")
        ctx=context();self.assertEqual(execute(ctx,"SAVE('missing','FR:M.TP',s)"),1)
        self.assertEqual(execute(ctx,"LOAD('FR:M.TP',0,s)"),1);self.assertEqual(execute(ctx,"CLEAR('missing',s)"),1)

    def test_status_for_counter_guards_and_user_override_remain(self):
        calls=["SAVE('A','A.TP',n)","LOAD('A.TP',0,n)","CLEAR('A',n)","PROG_BACKUP('A',PBR_ALLTYPE,0,TRUE,n)",
            "PROG_RESTORE('A',n)","PROG_CLEAR('A',PBR_NVRTYPE,n)"]
        for call in calls:
            with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO '+call+' ENDFOR')
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
        self.assertEqual(run('LOAD(7)',routines='ROUTINE LOAD(x:INTEGER) BEGIN n=x END LOAD')['N'],7)

    def test_value_arguments_capture_before_later_status_selector_effects(self):
        ctx=context();p,_=compile_program("n=0 filename='FR:A.TP' SAVE('A',filename,results[slot])",context=ctx,
            decl='filename:STRING[40] results:ARRAY[1] OF INTEGER n,s:INTEGER',
            routines="ROUTINE slot:INTEGER BEGIN n=n+1 filename='FR:B.TP' RETURN 1 END slot")
        self.assertEqual(p.run()['N'],1);self.assertIn('FR:A.TP',ctx.files.files);self.assertNotIn('FR:B.TP',ctx.files.files)

    def test_load_status_tracks_real_logical_store_after_clear_and_load(self):
        ctx=context();data=run("SAVE('A','A.TP',s) CLEAR('A',s) LOAD_STATUS('A',before,initialized) LOAD('A.TP',0,s) LOAD_STATUS('A',after,initialized)",
            decl='s:INTEGER before,after,initialized:BOOLEAN',context=ctx)
        self.assertEqual((data['BEFORE'],data['AFTER'],data['INITIALIZED']),(False,True,True))

    def test_selected_and_open_targets_guard_clear_and_overwrite_but_save_is_readable(self):
        for mode in ('selected','open'):
            ctx=context();execute(ctx,"SAVE('A','A.TP',s)")
            if mode=='selected':ctx.teach_programs.select('A')
            else:ctx.teach_programs.open('A',1)
            before=ctx.teach_programs.to_config()
            self.assertEqual(execute(ctx,"CLEAR('A',s)"),4);self.assertEqual(execute(ctx,"LOAD('A.TP',1,s)"),4)
            self.assertEqual(ctx.teach_programs.to_config(),before)
        ctx=context();ctx.teach_programs.select('A');self.assertEqual(execute(ctx,"SAVE('A','A.TP',s)"),0)

    def test_attached_karel_identity_and_explicit_active_metadata_guard_operations(self):
        ctx=context({'T':{}});self.assertEqual(execute(ctx,"CLEAR('T',s)"),4)
        self.assertEqual(execute(ctx,"SAVE('T','T.TP',s)"),4)
        ctx=context();ctx.program_attributes=rt.ProgramAttributes({'A':{'loaded':True,'active':True}})
        self.assertEqual(execute(ctx,"CLEAR('A',s)"),4)

    def test_protected_clear_and_overwrite_refuse_but_read_save_succeeds(self):
        ctx=context({'A':{'attributes':{'AT_PROTECT':2}}});self.assertEqual(execute(ctx,"SAVE('A','A.TP',s)"),0)
        self.assertEqual(execute(ctx,"CLEAR('A',s)"),4);self.assertEqual(execute(ctx,"LOAD('A.TP',1,s)"),4)

    def test_explicit_metadata_load_flags_refresh_and_overlay_attributes_survive(self):
        ctx=context();ctx.program_attributes=rt.ProgramAttributes({'A':{'loaded':True,'initialized':True,'attributes':{'AT_OWNER':'owner'}}})
        execute(ctx,"SAVE('A','A.TP',s) CLEAR('A',s)")
        self.assertFalse(ctx.program_attributes.record('A')['loaded'])
        self.assertFalse(ctx.program_attributes.record('A')['initialized'])
        self.assertEqual(execute(ctx,"LOAD('A.TP',0,s)"),0)
        self.assertTrue(ctx.program_attributes.record('A')['loaded'])
        self.assertTrue(ctx.program_attributes.record('A')['initialized'])
        self.assertEqual(ctx.program_attributes.record('A')['attributes'],{'AT_OWNER':'owner'})

    def test_host_protection_metadata_remains_read_only_in_source_and_copy_guarded(self):
        ctx=context({'A':{'attributes':{'AT_PROTECT':2}},'B':{}})
        self.assertEqual(execute(ctx,"SET_ATTR_PRG('A',AT_PROTECT,1,'',s)"),2)
        self.assertEqual(ctx.teach_programs.copy('B','A',True),4)

    def test_copy_tpe_retains_detached_dependency_metadata(self):
        ctx=chain();self.assertEqual(ctx.teach_programs.copy('A','D'),0)
        self.assertEqual(ctx.teach_programs._calls['D'],['B']);ctx.teach_programs._calls['D'].clear()
        self.assertEqual(ctx.teach_programs._calls['A'],['B'])


class RecursiveProgramArchiveTests(unittest.TestCase):
    def test_recursive_backup_clear_restore_roundtrip(self):
        ctx=chain();before=ctx.teach_programs.to_config()
        self.assertEqual(execute(ctx,"PROG_BACKUP('FR:batch/A.PC',PBR_ALLTYPE,0,TRUE,s) PROG_CLEAR('A.TP',PBR_NVRTYPE,s) PROG_RESTORE('FR:batch/A',s)"),0)
        self.assertEqual(ctx.teach_programs.to_config(),before)
        self.assertEqual(set(ctx.files.files),{'FR:batch/A.TP','FR:batch/B.TP','FR:batch/C.TP'})

    def test_cycles_and_shared_dependencies_are_processed_once(self):
        ctx=context({'A':{},'B':{},'C':{}},calls={'A':['B','C'],'B':['C'],'C':['A']})
        self.assertEqual(execute(ctx,"PROG_BACKUP('FR:A',PBR_ALLTYPE,0,TRUE,s) PROG_CLEAR('A',PBR_ALLTYPE,s) PROG_RESTORE('FR:A',s)"),0)
        self.assertEqual(len(ctx.teach_programs.entries),3);self.assertEqual(len(ctx.files.files),3)

    def test_known_macro_references_are_excluded_from_recursive_archives(self):
        ctx=context({'A':{},'M':{'type':'MR'}},calls={'A':['M']})
        self.assertEqual(execute(ctx,"PROG_BACKUP('FR:A',PBR_ALLTYPE,0,TRUE,s)"),0)
        self.assertEqual(set(ctx.files.files),{'FR:A.TP'});self.assertEqual(json.loads(bytes(ctx.files.files['FR:A.TP']))['calls'],[])
        self.assertEqual(execute(ctx,"PROG_CLEAR('A',PBR_ALLTYPE,s) PROG_RESTORE('FR:A',s)"),0)
        self.assertEqual(ctx.teach_programs.entries,(('A','TP'),('M','MR')))

    def test_explicit_macro_root_can_be_backed_up_and_restored(self):
        ctx=context({'M':{'type':'MR'}})
        self.assertEqual(execute(ctx,"PROG_BACKUP('FR:M',PBR_MRTYPE,0,TRUE,s) PROG_CLEAR('M',PBR_MRTYPE,s) PROG_RESTORE('FR:M',s)"),0)
        self.assertEqual(ctx.teach_programs.entries,(('M','MR'),))

    def test_type_filters_traverse_through_other_kinds(self):
        ctx=chain();self.assertEqual(execute(ctx,"PROG_BACKUP('FR:A',PBR_JBTYPE,0,TRUE,s)"),0)
        self.assertEqual(set(ctx.files.files),{'FR:B.TP'})
        self.assertEqual(execute(ctx,"PROG_CLEAR('A',PBR_PRTYPE,s)"),0);self.assertEqual(ctx.teach_programs.entries,(('A','TP'),('B','JB')))

    def test_backup_protected_inclusion_flag_and_recursive_clear_skip(self):
        ctx=context({'A':{},'B':{'attributes':{'AT_PROTECT':2}}},calls={'A':['B']})
        self.assertEqual(execute(ctx,"PROG_BACKUP('FR:A',PBR_NVRTYPE,0,FALSE,s)"),0);self.assertEqual(set(ctx.files.files),{'FR:A.TP'})
        self.assertEqual(execute(ctx,"PROG_BACKUP('FR:A',PBR_NVRTYPE,0,TRUE,s)"),0);self.assertIn('FR:B.TP',ctx.files.files)
        self.assertEqual(execute(ctx,"PROG_CLEAR('A',PBR_ALLTYPE,s)"),0);self.assertEqual(ctx.teach_programs.entries,(('B','TP'),))

    def test_missing_dependency_preserves_complete_backup_and_clear_ignores_missing(self):
        ctx=context(calls={'A':['MISSING']});self.assertEqual(execute(ctx,"PROG_BACKUP('FR:A',PBR_ALLTYPE,0,TRUE,s)"),1)
        self.assertEqual(ctx.files.files,{});self.assertEqual(execute(ctx,"PROG_CLEAR('A',PBR_ALLTYPE,s)"),0)
        self.assertEqual(ctx.teach_programs.entries,())

    def test_missing_restore_dependency_preserves_entire_store(self):
        ctx=chain();execute(ctx,"PROG_BACKUP('FR:A',PBR_ALLTYPE,0,TRUE,s) PROG_CLEAR('A',PBR_ALLTYPE,s)")
        ctx.files.delete('FR:C.TP');before=ctx.teach_programs.to_config()
        self.assertEqual(execute(ctx,"PROG_RESTORE('FR:A',s)"),1);self.assertEqual(ctx.teach_programs.to_config(),before)

    def test_restore_keeps_existing_programs_and_traverses_their_current_graph(self):
        ctx=chain();execute(ctx,"PROG_BACKUP('FR:A',PBR_ALLTYPE,0,TRUE,s) PROG_CLEAR('A',PBR_ALLTYPE,s)")
        ctx.teach_programs.create('A');ctx.teach_programs._programs['A']['instructions']=['live']
        ctx.teach_programs._calls['A']=['C'];ctx.files.delete('FR:A.TP');ctx.files.delete('FR:B.TP')
        self.assertEqual(execute(ctx,"PROG_RESTORE('FR:A',s)"),0)
        self.assertEqual(ctx.teach_programs._programs['A']['instructions'],['live']);self.assertEqual(set(ctx.teach_programs._programs),{'A','C'})

    def test_restore_program_count_and_shared_byte_budget_preflight(self):
        ctx=chain();execute(ctx,"PROG_BACKUP('FR:A',PBR_ALLTYPE,0,TRUE,s) PROG_CLEAR('A',PBR_ALLTYPE,s)")
        ctx.teach_programs.program_limit=2
        self.assertEqual(execute(ctx,"PROG_RESTORE('FR:A',s)"),5);self.assertEqual(ctx.teach_programs.entries,())
        ctx.teach_programs.program_limit=256;ctx.teach_programs.archive_limit=len(ctx.files.files['FR:A.TP'])+1
        self.assertEqual(execute(ctx,"PROG_RESTORE('FR:A',s)"),5);self.assertEqual(ctx.teach_programs.entries,())

    def test_clear_batch_is_atomic_when_a_dependency_is_selected_or_bound(self):
        for mode in ('selected','bound'):
            ctx=chain()
            if mode=='selected':ctx.teach_programs.select('C')
            else:ctx.teach_programs.bind_caller('OTHER','C')
            before=ctx.teach_programs.to_config();self.assertEqual(execute(ctx,"PROG_CLEAR('A',PBR_ALLTYPE,s)"),4)
            self.assertEqual(ctx.teach_programs.to_config(),before)

    def test_vr_pc_only_and_unknown_filters_are_explicitly_unsupported(self):
        for selector in ('PBR_VRTYPE','PBR_PCTYPE','99'):
            ctx=chain();before=ctx.teach_programs.to_config()
            self.assertEqual(execute(ctx,f"PROG_BACKUP('FR:A',{selector},0,TRUE,s)"),4)
            self.assertEqual(execute(ctx,f"PROG_CLEAR('A',{selector},s)"),4);self.assertEqual(ctx.teach_programs.to_config(),before)


class ProgramArchiveFileTests(unittest.TestCase):
    def test_busy_archive_target_and_source_preserve_files_and_store(self):
        ctx=context();execute(ctx,"SAVE('A','FR:A.TP',s)");handle=rt.FileHandle();ctx.files.open(handle,'R','FR:A.TP')
        before=ctx.teach_programs.to_config();data=bytes(ctx.files.files['FR:A.TP'])
        self.assertEqual(execute(ctx,"PROG_BACKUP('FR:A',PBR_ALLTYPE,0,TRUE,s)"),4)
        self.assertEqual(execute(ctx,"LOAD('FR:A.TP',1,s)"),4)
        self.assertEqual(ctx.teach_programs.to_config(),before);self.assertEqual(ctx.files.files['FR:A.TP'],data);ctx.files.close(handle)

    def test_aggregate_device_quota_failure_preserves_all_targets(self):
        files=rt.DeviceFiles({'FR:':{'capacity':400}});ctx=chain(files=files)
        self.assertLess(len(encode(ctx.teach_programs,'A')),400)
        self.assertEqual(execute(ctx,"PROG_BACKUP('FR:A',PBR_ALLTYPE,0,TRUE,s)"),5);self.assertEqual(files.files,{})

    def test_changed_backup_accounts_for_retained_garbage_and_identical_skips(self):
        files=rt.DeviceFiles({'FR:':{'capacity':10000,'retain_deleted':True}});ctx=context(files=files)
        body="PROG_BACKUP('FR:A',PBR_ALLTYPE,0,TRUE,s)";self.assertEqual(execute(ctx,body),0)
        first=bytes(files.files['FR:A.TP']);self.assertEqual(execute(ctx,body),0);self.assertEqual(files._volumes['FR']['garbage'],0)
        ctx.teach_programs._programs['A']['instructions']=['new'];self.assertEqual(execute(ctx,body),0)
        self.assertEqual(files._volumes['FR']['garbage'],len(first));self.assertNotEqual(files.files['FR:A.TP'],first)

    def test_read_only_and_unmounted_devices_reject_backup_without_changes(self):
        for flags in ({'read_only':True},{'mounted':False}):
            files=rt.DeviceFiles({'FR:':{'capacity':10000,**flags}});ctx=context(files=files)
            self.assertEqual(execute(ctx,"PROG_BACKUP('FR:A',PBR_ALLTYPE,0,TRUE,s)"),4);self.assertEqual(files.files,{})

    def test_max_size_is_free_space_hint_and_not_output_size_cap(self):
        ctx=context(files=rt.DeviceFiles({'FR:':{'capacity':10000}}))
        self.assertEqual(execute(ctx,"PROG_BACKUP('FR:A',PBR_ALLTYPE,20,TRUE,s)"),5);self.assertEqual(ctx.files.files,{})
        self.assertEqual(execute(ctx,"PROG_BACKUP('FR:A',PBR_ALLTYPE,0,TRUE,s)"),0)
        for size in (-1,65537):self.assertEqual(execute(ctx,f"PROG_BACKUP('FR:A',PBR_ALLTYPE,{size},TRUE,s)"),2)

    def test_directory_and_custom_file_backends_cannot_write_host_archives(self):
        from karel2py.storage import DirectoryFiles
        class Custom(rt.MemoryFiles):pass
        with tempfile.TemporaryDirectory() as folder:
            for files in (DirectoryFiles(folder),Custom()):
                ctx=context(files=files);self.assertEqual(execute(ctx,"SAVE('A','A.TP',s)"),4)
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_invalid_json_duplicate_keys_deep_nesting_and_native_bytes_reject(self):
        payloads=[b'native\0TP',b'{',b'{"format":1,"format":2}',b'['*33+b'0'+b']'*33,b'NaN',b'\xff']
        for data in payloads:
            ctx=context(files=rt.MemoryFiles({'FR:A.TP':data}));before=ctx.teach_programs.to_config()
            self.assertEqual(execute(ctx,"LOAD('FR:A.TP',1,s)"),6);self.assertEqual(ctx.teach_programs.to_config(),before)

    def test_archive_schema_identity_position_type_and_register_limits_reject(self):
        ctx=context();base=json.loads(encode(ctx.teach_programs,'A'))
        variants=[{**base,'extra':1},{**base,'format':'native'},{**base,'name':'lower'},
            {**base,'program':{'type':'PC'}},{**base,'program':{'string_registers':{'32768':'x'}}},
            {**base,'program':{'positions':[{'group':1,'number':1,'value':{'type':'INTEGER','value':1}}]}}]
        for row in variants:
            target=context(files=rt.MemoryFiles({'FR:A.TP':json.dumps(row).encode()}));before=target.teach_programs.to_config()
            self.assertEqual(execute(target,"LOAD('FR:A.TP',1,s)"),6);self.assertEqual(target.teach_programs.to_config(),before)
        target=context({},files=rt.MemoryFiles({'FR:B.TP':encode(ctx.teach_programs,'A')}))
        self.assertEqual(execute(target,"PROG_RESTORE('FR:B',s)"),6);self.assertEqual(target.teach_programs.entries,())

    def test_byte_limits_refuse_save_and_load_before_mutations(self):
        ctx=context(archive_limit=10);self.assertEqual(execute(ctx,"SAVE('A','A.TP',s)"),5);self.assertEqual(ctx.files.files,{})
        ctx=context(files=rt.MemoryFiles(limit=10));self.assertEqual(execute(ctx,"SAVE('A','A.TP',s)"),5)
        ctx=context();data=encode(ctx.teach_programs,'A');ctx.files.files['A.TP']=bytearray(data);ctx.teach_programs.archive_limit=10
        self.assertEqual(execute(ctx,"LOAD('A.TP',1,s)"),5)


class ProgramArchivePersistenceTests(unittest.TestCase):
    def test_context_roundtrip_retains_graph_limits_and_file_bytes(self):
        ctx=chain(archive_limit=8192);execute(ctx,"PROG_BACKUP('FR:A',PBR_ALLTYPE,0,TRUE,s)")
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved);self.assertEqual(execute(restored,"PROG_CLEAR('A',PBR_ALLTYPE,s) PROG_RESTORE('FR:A',s)"),0)

    def test_graph_normalization_detaches_inputs_and_rejects_duplicates(self):
        calls={'a':['b']};bank=rt.TeachPrograms(calls=calls);calls['a'].clear()
        self.assertEqual(bank.to_config()['calls'],{'A':['B']})
        for graph in ({'A':['b','B']},{'A':[],'a':[]},{'bad name':[]},{'A':'B'},{'A':[1]}):
            with self.assertRaises(ValueError):rt.TeachPrograms(calls=graph)
        for limit in (0,True,67108865):
            with self.assertRaises(ValueError):rt.TeachPrograms(archive_limit=limit)

    def test_graph_node_edge_and_copy_growth_limits_preflight(self):
        with self.assertRaises(ValueError):rt.TeachPrograms(program_limit=1,calls={'A':[],'B':[]})
        with self.assertRaises(ValueError):rt.TeachPrograms(program_limit=1,calls={'A':['B','C']})
        targets=['P'+str(n) for n in range(4096)]
        with self.assertRaises(ValueError):rt.TeachPrograms(program_limit=4096,calls={'N'+str(n):targets for n in range(8)})
        bank=rt.TeachPrograms({'A':{},'B':{}},program_limit=2,calls={'A':['B'],'UNLOADED':[]});before=bank.to_config()
        self.assertEqual(bank.copy('A','B',True),6);self.assertEqual(bank.to_config(),before)

    def test_legacy_context_has_no_new_default_fields_and_snapshots_are_detached(self):
        bank=rt.TeachPrograms();self.assertEqual(set(bank.to_config()),{'groups','position_limit','program_limit','programs'})
        bank=rt.TeachPrograms({'A':{}},calls={'A':['B']});saved=bank.to_config();saved['calls']['A'].clear();saved['programs']['A']['instructions'].append('changed')
        self.assertEqual(bank._calls['A'],['B']);self.assertEqual(bank._programs['A']['instructions'],[])

    def test_report_lists_actual_calls_constants_and_offline_boundary(self):
        _,result=compile_program("SAVE('A','A.TP',s) LOAD('A.TP',1,s) CLEAR('A',s) PROG_BACKUP('A',PBR_ALLTYPE,0,TRUE,s) PROG_CLEAR('A',PBR_ALLTYPE,s) PROG_RESTORE('A',s)")
        policy=result.report['program_archive_policy'];self.assertFalse(policy['controller_validated'])
        self.assertEqual(len(policy['calls']),6);self.assertEqual(len(policy['constants']),9)


if __name__=='__main__':unittest.main()
