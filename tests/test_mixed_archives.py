"""Authored mixed TP/VR batches, cross-store preflight and compiler guards."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from karel2py import runtime as rt,translate
from karel2py.lexer import TranslationError
from karel2py.mixed_archives import FORMAT
from tests.test_extended_services import compile_program,run

BACKUP="PROG_BACKUP('FR:batch/ROOT',PBR_ALLTYPE,0,TRUE,s)"
CLEAR="PROG_CLEAR('ROOT',PBR_ALLTYPE,s)"
RESTORE="PROG_RESTORE('FR:batch/ROOT',s)"


def context(*,files=None,limit=100000,program_limit=256):
    ctx=rt.ExecutionContext(teach_programs=rt.TeachPrograms({'ROOT':{'instructions':['authored root']},'WORK':{'type':'JB','numeric_registers':{'1':7}}},calls={'ROOT':['WORK'],'WORK':[]},archive_limit=limit),variable_archives=rt.VariableArchives(limit=limit,program_limit=program_limit,calls={'ROOT':['DATA'],'DATA':['ROOT']}),files=rt.MemoryFiles() if files is None else files)
    ctx.variables.define('ROOT','VALUE',('INTEGER',),17);ctx.variables.define('DATA','VALUE',('INTEGER',),23)
    return ctx


def execute(ctx,body,**options):return run(body,context=ctx,**options)['S']


def state(ctx):return (ctx.teach_programs.to_config() if ctx.teach_programs is not None else None,{k:rt.snapshot_value(v.raw()) for k,v in ctx.variables.bindings.items() if k[0] in ('ROOT','DATA')},ctx.variable_archives.to_config())


def bundle(ctx):return json.loads(bytes(ctx.files.files['FR:batch/ROOT.PB']))


def replace_manifest(ctx,row):ctx.files.files['FR:batch/ROOT.PB']=bytearray((json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode())


class MixedBatchTests(unittest.TestCase):
    def test_cross_store_metadata_edges_survive_fresh_restore(self):
        ctx=context();ctx.teach_programs._calls['DATA']=['BRIDGE'];ctx.variables.define('BRIDGE','VALUE',('INTEGER',),31)
        self.assertEqual(execute(ctx,BACKUP),0)
        fresh=rt.ExecutionContext(teach_programs=rt.TeachPrograms(),variable_archives=rt.VariableArchives(),files=rt.MemoryFiles(ctx.files.snapshot()))
        self.assertEqual(execute(fresh,RESTORE),0);self.assertIn('BRIDGE',fresh.variable_archives.calls['DATA']);self.assertEqual(fresh.variables.bindings['BRIDGE','VALUE'].raw(),31)
        self.assertEqual(execute(fresh,BACKUP),0);self.assertIn('BRIDGE',{entry['name'] for entry in bundle(fresh)['entries']})

    def test_report_describes_actual_mixed_contract_and_boundaries(self):
        policy=translate('PROGRAM T BEGIN END T').report['mixed_archive_policy']
        self.assertFalse(policy['controller_validated']);self.assertEqual(len(policy['procedures']),3)
        self.assertIn('SHA-256',policy['files']);self.assertIn('FOR-counter',policy['guards']);self.assertIn('manifest',policy['boundary'])

    def test_combined_graph_creates_tp_vr_and_root_manifest(self):
        ctx=context();self.assertEqual(execute(ctx,BACKUP),0)
        self.assertEqual(set(ctx.files.files),{'FR:batch/ROOT.TP','FR:batch/WORK.TP','FR:batch/ROOT.VR','FR:batch/DATA.VR','FR:batch/ROOT.PB'})
        row=bundle(ctx);self.assertEqual(row['format'],FORMAT);self.assertEqual([v['name'] for v in row['entries']],['ROOT','WORK','DATA'])
        self.assertEqual(row['entries'][0]['calls'],['WORK','DATA'])
        for entry in row['entries']:
            for kind,digest in entry['files'].items():self.assertEqual(digest,hashlib.sha256(ctx.files.files['FR:batch/'+entry['name']+'.'+kind]).hexdigest())

    def test_clear_restore_roundtrip_preserves_both_banks(self):
        ctx=context();before=state(ctx);reference=ctx.variables.bindings['ROOT','VALUE']
        self.assertEqual(execute(ctx,BACKUP+' '+CLEAR),0);self.assertEqual(ctx.teach_programs.entries,());self.assertIs(reference.raw(),rt.UNINITIALIZED)
        self.assertEqual(execute(ctx,RESTORE),0);self.assertEqual(state(ctx),before);self.assertIs(ctx.variables.bindings['ROOT','VALUE'],reference)

    def test_existing_tp_is_retained_and_vr_overwritten(self):
        ctx=context();execute(ctx,BACKUP);ctx.teach_programs._programs['ROOT']['instructions']=['changed'];ctx.variables.bindings['ROOT','VALUE'].set(99)
        self.assertEqual(execute(ctx,RESTORE),0);self.assertEqual(ctx.teach_programs._programs['ROOT']['instructions'],['changed']);self.assertEqual(ctx.variables.bindings['ROOT','VALUE'].raw(),17)

    def test_restore_into_fresh_services_needs_no_original_graph(self):
        ctx=context();execute(ctx,BACKUP);fresh=rt.ExecutionContext(teach_programs=rt.TeachPrograms(),variable_archives=rt.VariableArchives(),files=rt.MemoryFiles(ctx.files.snapshot()))
        self.assertEqual(execute(fresh,RESTORE),0);self.assertEqual(fresh.teach_programs.entries,(('ROOT','TP'),('WORK','JB')));self.assertEqual(fresh.variables.bindings['DATA','VALUE'].raw(),23)

    def test_variable_only_alltype_roundtrip(self):
        ctx=context();ctx.teach_programs=None;before=state(ctx)
        self.assertEqual(execute(ctx,BACKUP+' '+CLEAR+' '+RESTORE),0);self.assertEqual(state(ctx),before)
        self.assertEqual(set(ctx.files.files),{'FR:batch/ROOT.PB','FR:batch/ROOT.VR','FR:batch/DATA.VR'})

    def test_tp_only_alltype_with_variable_service_has_no_fabricated_vr(self):
        ctx=context();ctx.variables=rt.VariableStore();ctx.variable_archives.calls={}
        self.assertEqual(execute(ctx,BACKUP+' '+CLEAR+' '+RESTORE),0);self.assertEqual(set(ctx.files.files),{'FR:batch/ROOT.TP','FR:batch/WORK.TP','FR:batch/ROOT.PB'})

    def test_no_variable_service_keeps_original_tp_archive_behavior(self):
        ctx=context();ctx.variable_archives=None;self.assertEqual(execute(ctx,BACKUP+' '+CLEAR+' '+RESTORE),0);self.assertNotIn('FR:batch/ROOT.PB',ctx.files.files)

    def test_no_manifest_falls_back_to_ordinary_tp_restore(self):
        ctx=context();self.assertEqual(execute(ctx,"PROG_BACKUP('FR:ROOT',PBR_NVRTYPE,0,TRUE,s) PROG_CLEAR('ROOT',PBR_NVRTYPE,s) PROG_RESTORE('FR:ROOT',s)"),0)
        self.assertEqual(ctx.variables.bindings['ROOT','VALUE'].raw(),17)

    def test_explicit_pb_requires_manifest(self):
        ctx=context();before=state(ctx);self.assertEqual(execute(ctx,"PROG_RESTORE('FR:ROOT.PB',s)"),1);self.assertEqual(state(ctx),before)

    def test_known_macros_are_excluded_even_from_variable_graph(self):
        ctx=context();ctx.teach_programs._programs['WORK']['type']='MR';ctx.variable_archives.calls['ROOT']=['WORK','DATA']
        self.assertEqual(execute(ctx,BACKUP),0);self.assertNotIn('WORK',{v['name'] for v in bundle(ctx)['entries']});self.assertNotIn('WORK',json.loads(ctx.files.files['FR:batch/ROOT.VR'])['calls'])

    def test_explicit_macro_root_can_be_backed_up(self):
        ctx=context();ctx.teach_programs._programs['ROOT']['type']='MR';self.assertEqual(execute(ctx,BACKUP),0);self.assertIn('FR:batch/ROOT.TP',ctx.files.files)

    def test_extension_ignored_for_mixed_backup_restore(self):
        ctx=context();self.assertEqual(execute(ctx,BACKUP.replace('ROOT\'',"ROOT.PC'")+' '+CLEAR+' '+RESTORE.replace("ROOT'","ROOT.TP'")),0)

    def test_clear_ignores_missing_child_but_backup_rejects_atomically(self):
        ctx=context();ctx.variable_archives.calls['DATA']=['MISSING'];self.assertEqual(execute(ctx,BACKUP),1);self.assertFalse(ctx.files.files)
        self.assertEqual(execute(ctx,CLEAR),0);self.assertFalse(ctx.teach_programs.entries)

    def test_missing_root_is_error_for_clear_and_backup(self):
        ctx=context()
        for call in (BACKUP,CLEAR):self.assertEqual(execute(ctx,call.replace('ROOT','ABSENT')),1)

    def test_saved_context_retains_manifest_values_and_graphs(self):
        ctx=context();execute(ctx,BACKUP);fresh=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertEqual(execute(fresh,CLEAR+' '+RESTORE),0);self.assertEqual(state(ctx),state(fresh))

    def test_partial_aggregate_and_alias_survive_combined_restore(self):
        ctx=context();spec=('ARRAY',2,('REAL',));array=rt.Array(spec);array.values[0]=1.5
        ctx.variables.bind('DATA','ARRAY',rt.Reference(spec,{'v':array},'v'));alias=rt.Reference(('REAL',),array.values,0)
        self.assertEqual(execute(ctx,BACKUP+' '+CLEAR+' '+RESTORE),0);self.assertIs(ctx.variables.bindings['DATA','ARRAY'].raw(),array);self.assertEqual(alias.raw(),1.5);self.assertIs(array.values[1],rt.UNINITIALIZED)


class MixedAtomicGuardsTests(unittest.TestCase):
    def test_selected_tp_dependency_prevents_all_clear_changes(self):
        ctx=context();ctx.teach_programs.select('WORK');before=state(ctx);self.assertEqual(execute(ctx,CLEAR),4);self.assertEqual(state(ctx),before)

    def test_bound_caller_prevents_all_clear_changes(self):
        ctx=context();ctx.teach_programs.bind_caller('OTHER','WORK');before=state(ctx);self.assertEqual(execute(ctx,CLEAR),4);self.assertEqual(state(ctx),before)

    def test_status_alias_in_variable_snapshot_preserves_tp_rows(self):
        ctx=context();p,_=compile_program('s=77 '+CLEAR,context=ctx);ctx.variables.bind('ROOT','ALIAS',p._state.reference('S'));before=ctx.teach_programs.to_config()
        self.assertEqual(p.run()['S'],4);self.assertEqual(ctx.teach_programs.to_config(),before);self.assertEqual(ctx.variables.bindings['ROOT','VALUE'].raw(),17)

    def test_foreign_active_variable_alias_prevents_tp_clear(self):
        ctx=context();ns={'__name__':'paused'};exec(translate('PROGRAM OTHER VAR n:INTEGER BEGIN n=99 PAUSE END OTHER',cooperative=True).python_source,ns);other=ns['Program'](context=ctx)
        with self.assertRaises(rt.KarelPause):other.run()
        ctx.variables.bind('ROOT','ALIAS',other._state.reference('N'));before=ctx.teach_programs.to_config();self.assertEqual(execute(ctx,CLEAR),4);self.assertEqual(ctx.teach_programs.to_config(),before);self.assertEqual(other.snapshot()['N'],99)

    def test_missing_restore_member_keeps_tp_and_vr_unchanged(self):
        ctx=context();execute(ctx,BACKUP+' '+CLEAR);del ctx.files.files['FR:batch/DATA.VR'];before=state(ctx);self.assertEqual(execute(ctx,RESTORE),1);self.assertEqual(state(ctx),before)

    def test_changed_member_hash_rejects_whole_restore(self):
        ctx=context();execute(ctx,BACKUP+' '+CLEAR);ctx.files.files['FR:batch/DATA.VR']+=b' ';before=state(ctx);self.assertEqual(execute(ctx,RESTORE),6);self.assertEqual(state(ctx),before)

    def test_schema_mismatch_preserves_earlier_tp_candidates(self):
        ctx=context();execute(ctx,BACKUP+' '+CLEAR);ctx.variables.bind('DATA','VALUE',rt.Reference(('REAL',),{'v':2.},'v'));before=state(ctx)
        self.assertEqual(execute(ctx,RESTORE),6);self.assertEqual(state(ctx),before)

    def test_protection_skips_both_halves_and_restore_reports_omission(self):
        ctx=context();ctx.teach_programs._programs['ROOT']['attributes']['AT_PROTECT']=2
        self.assertEqual(execute(ctx,BACKUP.replace('TRUE','FALSE')),0);self.assertEqual(bundle(ctx)['entries'][0]['files'],{});before=state(ctx)
        self.assertEqual(execute(ctx,RESTORE),1);self.assertEqual(state(ctx),before)
        self.assertEqual(execute(ctx,CLEAR),0);self.assertIn('ROOT',ctx.teach_programs._programs);self.assertEqual(ctx.variables.bindings['ROOT','VALUE'].raw(),17);self.assertIs(ctx.variables.bindings['DATA','VALUE'].raw(),rt.UNINITIALIZED)

    def test_explicit_protected_vr_blocks_restore_before_tp_commit(self):
        ctx=context();execute(ctx,BACKUP+' '+CLEAR);ctx.program_attributes=rt.ProgramAttributes({'DATA':{'loaded':False,'attributes':{'AT_PROTECT':2}}});before=state(ctx)
        self.assertEqual(execute(ctx,RESTORE),4);self.assertEqual(state(ctx),before)

    def test_invalid_manifest_structure_identity_graph_and_hashes(self):
        ctx=context();execute(ctx,BACKUP+' '+CLEAR);original=bundle(ctx);before=state(ctx)
        candidates=[]
        for field,value in [('root','OTHER'),('format','native'),('extra',1),('entries',[])]:row=deepcopy(original);row[field]=value;candidates.append(row)
        row=deepcopy(original);row['entries'][0]['files']['TP']='bad';candidates.append(row)
        row=deepcopy(original);row['entries'][0]['calls']=['UNKNOWN'];candidates.append(row)
        row=deepcopy(original);row['entries'].append(deepcopy(row['entries'][0]));candidates.append(row)
        row=deepcopy(original);row['entries'][0]['calls']=[];candidates.append(row)
        for row in candidates:
            replace_manifest(ctx,row)
            with self.subTest(row=row):self.assertEqual(execute(ctx,RESTORE),6);self.assertEqual(state(ctx),before)

    def test_duplicate_json_keys_are_not_accepted(self):
        ctx=context();execute(ctx,BACKUP+' '+CLEAR);ctx.files.files['FR:batch/ROOT.PB']=bytearray(b'{"root":"ROOT","root":"ROOT"}');before=state(ctx);self.assertEqual(execute(ctx,RESTORE),6);self.assertEqual(state(ctx),before)

    def test_tp_capacity_failure_preserves_all_vr_values(self):
        ctx=context();execute(ctx,BACKUP+' '+CLEAR);ctx.teach_programs.program_limit=1;before=state(ctx);self.assertEqual(execute(ctx,RESTORE),5);self.assertEqual(state(ctx),before)

    def test_variable_namespace_limit_prevents_writing_any_file(self):
        ctx=context();ctx.variable_archives=rt.VariableArchives(program_limit=1,calls={'ROOT':['DATA']});self.assertEqual(execute(ctx,BACKUP),5);self.assertFalse(ctx.files.files)

    def test_mixed_clear_keeps_resources_and_does_not_unload_source(self):
        ctx=context();ctx.variable_archives.calls={'ROOT':['T']};p,_=compile_program('n=7 work',decl='n:INTEGER f:FILE',context=ctx,routines="ROUTINE work VAR s:INTEGER BEGIN PROG_CLEAR('ROOT',PBR_ALLTYPE,s) END work")
        handle=p._state.values['F'];values=p.run();self.assertEqual(values['N'],{'uninitialized':True});self.assertIs(p._state.values['F'],handle);self.assertIs(ctx.variables.programs['T'],p._state)


class MixedFilesAndSourceTests(unittest.TestCase):
    def test_whole_batch_quota_includes_manifest_and_both_formats(self):
        ctx=context();execute(ctx,BACKUP);size=sum(map(len,ctx.files.files.values()));files=rt.DeviceFiles({'FR:':{'capacity':size-1}});ctx=context(files=files)
        self.assertEqual(execute(ctx,BACKUP),5);self.assertFalse(files.files)

    def test_busy_manifest_or_member_preserves_entire_backup(self):
        for filename in ('ROOT.PB','DATA.VR','WORK.TP'):
            ctx=context();execute(ctx,BACKUP);handle=rt.FileHandle();ctx.files.open(handle,'R','FR:batch/'+filename);before=ctx.files.snapshot();ctx.variables.bindings['ROOT','VALUE'].set(99)
            self.assertEqual(execute(ctx,BACKUP),4);self.assertEqual(ctx.files.snapshot(),before);ctx.files.close(handle)

    def test_busy_manifest_or_member_preserves_entire_restore(self):
        for filename in ('ROOT.PB','DATA.VR','WORK.TP'):
            ctx=context();execute(ctx,BACKUP+' '+CLEAR);handle=rt.FileHandle();ctx.files.open(handle,'R','FR:batch/'+filename);before=state(ctx)
            self.assertEqual(execute(ctx,RESTORE),4);self.assertEqual(state(ctx),before);ctx.files.close(handle)

    def test_identical_backup_has_no_garbage_changed_backup_updates_manifest(self):
        files=rt.DeviceFiles({'FR:':{'capacity':50000,'retain_deleted':True}});ctx=context(files=files);execute(ctx,BACKUP);old=files.snapshot()
        self.assertEqual(execute(ctx,BACKUP),0);self.assertEqual(files._volumes['FR']['garbage'],0)
        ctx.variables.bindings['ROOT','VALUE'].set(99);self.assertEqual(execute(ctx,BACKUP),0);self.assertEqual(files._volumes['FR']['garbage'],len(old['FR:batch/ROOT.VR'])+len(old['FR:batch/ROOT.PB']))

    def test_combined_graph_edge_bound_precedes_writes_or_clear(self):
        names=['P'+str(i) for i in range(184)];left={name:names[:92] for name in names};right={name:names[92:] for name in names}
        ctx=rt.ExecutionContext(teach_programs=rt.TeachPrograms({name:{} for name in names},calls=left),variable_archives=rt.VariableArchives(calls=right),files=rt.MemoryFiles())
        before=ctx.teach_programs.to_config()
        self.assertEqual(execute(ctx,BACKUP.replace('ROOT','P0')),5);self.assertFalse(ctx.files.files)
        self.assertEqual(execute(ctx,CLEAR.replace('ROOT','P0')),5);self.assertEqual(ctx.teach_programs.to_config(),before)

    def test_budgets_include_manifest_bytes(self):
        ctx=context();execute(ctx,BACKUP);size=sum(map(len,ctx.files.files.values()));ctx=context(limit=size-1);self.assertEqual(execute(ctx,BACKUP),5);self.assertFalse(ctx.files.files)

    def test_free_space_hint_and_invalid_values_preserve_files(self):
        ctx=context(files=rt.DeviceFiles({'FR:':{'capacity':50000}}))
        for hint,code in [(-1,2),(65537,2),(100,5)]:self.assertEqual(execute(ctx,BACKUP.replace(',0,TRUE',f',{hint},TRUE')),code);self.assertFalse(ctx.files.files)

    def test_directory_and_custom_backends_remain_unsupported(self):
        from karel2py.storage import DirectoryFiles
        class Custom(rt.MemoryFiles):pass
        with tempfile.TemporaryDirectory() as folder:
            for files in (DirectoryFiles(folder),Custom()):
                ctx=context(files=files);self.assertEqual(execute(ctx,BACKUP),4);self.assertEqual(execute(ctx,RESTORE),4)
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_missing_file_service_raises_explicitly(self):
        ctx=context();ctx.files=None
        with self.assertRaisesRegex(rt.KarelRuntimeError,'files'):execute(ctx,BACKUP)

    def test_clear_device_path_and_invalid_backup_path_reject(self):
        ctx=context();before=state(ctx);self.assertEqual(execute(ctx,CLEAR.replace("'ROOT'","'FR:ROOT'")),2);self.assertEqual(execute(ctx,BACKUP.replace('batch/ROOT','../ROOT')),2);self.assertEqual(state(ctx),before)

    def test_existing_tp_protection_also_blocks_associated_vr_restore(self):
        ctx=context();execute(ctx,BACKUP);ctx.teach_programs._programs['ROOT']['attributes']['AT_PROTECT']=2;ctx.variables.bindings['ROOT','VALUE'].set(99);before=state(ctx)
        self.assertEqual(execute(ctx,RESTORE),4);self.assertEqual(state(ctx),before)

    def test_missing_tp_service_for_manifest_preserves_variables(self):
        ctx=context();execute(ctx,BACKUP);ctx.teach_programs=None;before=state(ctx)
        self.assertEqual(execute(ctx,RESTORE),4);self.assertEqual(state(ctx),before)

    def test_old_manifest_does_not_silently_restore_replaced_member(self):
        ctx=context();execute(ctx,BACKUP);ctx.variables.bindings['ROOT','VALUE'].set(99)
        self.assertEqual(execute(ctx,"PROG_BACKUP('FR:batch/ROOT',PBR_VRTYPE,0,TRUE,s)"),0);before=state(ctx)
        self.assertEqual(execute(ctx,RESTORE),6);self.assertEqual(state(ctx),before)

    def test_restore_manifest_cannot_omit_member_dependencies(self):
        ctx=context();execute(ctx,BACKUP+' '+CLEAR);row=bundle(ctx)
        # ROOT still reaches DATA, which reaches ROOT, but DATA may not conceal
        # its own archived outgoing reference merely because it is reachable.
        next(entry for entry in row['entries'] if entry['name']=='DATA')['calls']=[];replace_manifest(ctx,row);before=state(ctx)
        self.assertEqual(execute(ctx,RESTORE),6);self.assertEqual(state(ctx),before)

    def test_unlisted_variable_roots_remain_on_restore(self):
        ctx=context();execute(ctx,BACKUP);ctx.variables.define('DATA','EXTRA',('INTEGER',),41)
        self.assertEqual(execute(ctx,RESTORE),0);self.assertEqual(ctx.variables.bindings['DATA','EXTRA'].raw(),41)

    def test_metadata_flags_refresh_without_losing_overlay_attributes(self):
        ctx=context();ctx.program_attributes=rt.ProgramAttributes({'ROOT':{'loaded':True,'initialized':True,'attributes':{'AT_OWNER':'author'}}})
        self.assertEqual(execute(ctx,BACKUP+' '+CLEAR+' '+RESTORE),0);record=ctx.program_attributes.record('ROOT')
        self.assertTrue(record['loaded']);self.assertTrue(record['initialized']);self.assertEqual(record['attributes'],{'AT_OWNER':'author'})

    def test_new_possible_variable_writes_guard_for_counters(self):
        for call in (CLEAR,RESTORE,RESTORE.replace("ROOT'","ROOT.TP'")):
            with self.subTest(call=call),self.assertRaises(TranslationError) as error:compile_program('FOR n=1 TO 2 DO '+call+' ENDFOR')
            self.assertEqual(error.exception.code,'E_FOR_COUNTER')
        compile_program("FOR n=1 TO 2 DO PROG_CLEAR('ROOT',PBR_NVRTYPE,s) LOAD('FR:R.TP',0,s) ENDFOR")

    def test_transitive_and_handler_mixed_writes_guard_for_counters(self):
        with self.assertRaises(TranslationError):compile_program('FOR n=1 TO 2 DO restore ENDFOR',routines="ROUTINE restore VAR code:INTEGER BEGIN PROG_RESTORE('FR:T',code) END restore")
        with self.assertRaises(TranslationError):compile_program("CONDITION[1]: WHEN TRUE DO PROG_CLEAR('T',PBR_ALLTYPE,s) ENDCONDITION ENABLE CONDITION[1] FOR n=1 TO 2 DO ENDFOR",cooperative=True)


if __name__=='__main__':unittest.main()
