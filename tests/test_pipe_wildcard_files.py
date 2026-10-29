"""Finite plain-PIP wildcard snapshots, preflight and cross-backend publication."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from tests.test_extended_services import compile_program
from tests.test_wildcard_file_operations import invoke


DECL='f:FILE x,s:INTEGER'


def bank(initial=None,*,sectors=1,limit=16*1024*1024):
    result=rt.FilePipes(limit=limit)
    for index,(name,data) in enumerate((initial or {'A.DAT':b'a','B.DAT':b'b','A.BAK':b'old-a','B.BAK':b'old-b'}).items(),1):
        assert result.configure(name,index%2==0,sectors,8,'FMT',index)==0
        result.feed(name,data)
    return result


def context(initial=None,*,files=None,**options):return rt.ExecutionContext(file_pipes=bank(initial,**options),files=files)


def copy(ctx,source='PIP:*.DAT',target='PIP:*.BAK',*,overwrite=True,**options):
    return invoke(ctx.files,'COPY_FILE',source,target,overwrite=overwrite,ctx=ctx,**options)


def delete(ctx,source='PIP:*.DAT',**options):return invoke(ctx.files,'DELETE_FILE',source,ctx=ctx,**options)


def frozen(ctx):return deepcopy(ctx.file_pipes.to_config())


def open_pipe(ctx,name='PIP:A.DAT'):
    handle=rt.FileHandle();ctx.file_pipes.open_for(None,handle,'RW',name);return handle


class PipeWildcardSnapshotTests(unittest.TestCase):
    def test_pipe_to_pipe_batch_needs_no_ordinary_files_service(self):
        ctx=context();before=deepcopy(ctx.file_pipes.pipes)
        self.assertEqual(copy(ctx),0)
        self.assertEqual(ctx.file_pipes.files['PIP:A.BAK'],b'a');self.assertEqual(ctx.file_pipes.files['PIP:B.BAK'],b'b')
        self.assertEqual(ctx.file_pipes.pipes,before)

    def test_snapshot_replacement_does_not_append_to_old_history(self):
        ctx=context();self.assertEqual(copy(ctx),0)
        self.assertEqual(ctx.file_pipes.files['PIP:A.BAK'],b'a')
        self.assertEqual(ctx.file_pipes.files['PIP:A.DAT'],b'a')

    def test_copy_and_delete_preserve_dictionary_identity(self):
        ctx=context();data=ctx.file_pipes.files;configuration=ctx.file_pipes.pipes
        self.assertEqual(copy(ctx),0);self.assertIs(ctx.file_pipes.files,data);self.assertIs(ctx.file_pipes.pipes,configuration)
        self.assertEqual(delete(ctx),0);self.assertIs(ctx.file_pipes.files,data);self.assertIs(ctx.file_pipes.pipes,configuration)

    def test_optional_pipe_root_slash_and_case_are_normalized(self):
        ctx=context();self.assertEqual(copy(ctx,'pip:/*.dat','pip:/*.bak'),0)
        self.assertEqual(ctx.file_pipes.files['PIP:A.BAK'],b'a')

    def test_whole_source_stem_substitution_is_not_a_glob_capture(self):
        ctx=context({'seedOne.DAT':b'a','work_seedOne.BAK':b'old'})
        self.assertEqual(copy(ctx,'PIP:SEED*.DAT','PIP:work_*.BAK'),0)
        self.assertEqual(ctx.file_pipes.files['PIP:WORK_SEEDONE.BAK'],b'a')

    def test_extensionless_pipe_names_can_preserve_complete_filename(self):
        ctx=context({'LOG':b'abc'},files=rt.MemoryFiles())
        self.assertEqual(copy(ctx,'PIP:*','saved/*'),0)
        self.assertEqual(ctx.files.files['saved/LOG'],b'abc')

    def test_extensionless_ordinary_source_can_fill_configured_pipe_star(self):
        ctx=context({'LOG':b'old'},files=rt.MemoryFiles({'log':b'abc'}))
        self.assertEqual(copy(ctx,'log','PIP:*'),0);self.assertEqual(ctx.file_pipes.files['PIP:LOG'],b'abc')

    def test_empty_source_truncates_overwritten_pipe(self):
        ctx=context({'A.DAT':b'','A.BAK':b'old'})
        self.assertEqual(copy(ctx),0);self.assertEqual(ctx.file_pipes.files['PIP:A.BAK'],b'')

    def test_binary_source_bytes_are_not_decoded(self):
        ctx=context({'A.DAT':b'\xff\0abc','A.BAK':b'old'})
        self.assertEqual(copy(ctx),0);self.assertEqual(ctx.file_pipes.files['PIP:A.BAK'],b'\xff\0abc')

    def test_configured_destination_requires_explicit_overwrite_even_when_empty(self):
        ctx=context({'A.DAT':b'a','A.BAK':b''});before=frozen(ctx)
        self.assertEqual(copy(ctx,overwrite=False),2);self.assertEqual(frozen(ctx),before)

    def test_missing_configured_destination_blocks_every_copy(self):
        ctx=context({'A.DAT':b'a','B.DAT':b'b','A.BAK':b'old'});before=frozen(ctx)
        self.assertEqual(copy(ctx),1);self.assertEqual(frozen(ctx),before);self.assertNotIn('PIP:B.BAK',ctx.file_pipes.pipes)

    def test_missing_source_pattern_returns_one(self):
        ctx=context();before=frozen(ctx);self.assertEqual(copy(ctx,'PIP:*.missing','PIP:*.BAK'),1)
        self.assertEqual(frozen(ctx),before)

    def test_capacity_failure_does_not_ring_truncate_or_publish_earlier_target(self):
        ctx=context({'A.DAT':b'a','B.DAT':b'b','A.BAK':b'old-a','B.BAK':b'old-b'},files=rt.MemoryFiles({'a.dat':b'a','b.dat':b'x'*1025}))
        before=frozen(ctx)
        self.assertEqual(copy(ctx,'*.dat','PIP:*.BAK'),4);self.assertEqual(frozen(ctx),before)

    def test_exact_pipe_capacity_replaces_complete_snapshot(self):
        ctx=context({'A.BAK':b'old'},files=rt.MemoryFiles({'a.dat':b'x'*1024}))
        self.assertEqual(copy(ctx,'*.dat','PIP:*.BAK'),0);self.assertEqual(ctx.file_pipes.files['PIP:A.BAK'],b'x'*1024)

    def test_source_snapshot_is_current_retained_circular_history(self):
        ctx=context({'A.DAT':b'','A.BAK':b''});ctx.file_pipes.feed('A.DAT',b'x'*1024+b'end')
        self.assertEqual(copy(ctx),0);self.assertEqual(ctx.file_pipes.files['PIP:A.BAK'],b'x'*1021+b'end')

    def test_snapshot_does_not_allocate_an_extra_pipe_slot(self):
        values={f'P{i}.DAT':b'x' for i in range(31)};values['P0.BAK']=b'old'
        ctx=context(values,limit=32768)
        self.assertEqual(copy(ctx,'PIP:P0.DAT','PIP:*.BAK'),0);self.assertEqual(len(ctx.file_pipes.pipes),32)
        self.assertEqual(ctx.file_pipes.pipes['PIP:P0.BAK']['sectors'],1)

    def test_nowait_remains_synchronous(self):
        ctx=context();self.assertEqual(copy(ctx,nowait=True),0)
        self.assertEqual(ctx.file_pipes.files['PIP:B.BAK'],b'b')


class PipeWildcardDeleteTests(unittest.TestCase):
    def test_delete_removes_only_matching_bytes_and_configuration(self):
        ctx=context();self.assertEqual(delete(ctx),0)
        self.assertEqual(set(ctx.file_pipes.files),{'PIP:A.BAK','PIP:B.BAK'})
        self.assertEqual(set(ctx.file_pipes.pipes),set(ctx.file_pipes.files))

    def test_delete_star_includes_extensionless_pipe_configurations(self):
        ctx=context({'LOG':b'a','A.DAT':b'b'});self.assertEqual(delete(ctx,'PIP:*'),0)
        self.assertEqual(ctx.file_pipes.files,{});self.assertEqual(ctx.file_pipes.pipes,{})

    def test_delete_no_matches_keeps_bank(self):
        ctx=context();before=frozen(ctx);self.assertEqual(delete(ctx,'PIP:*.missing'),1)
        self.assertEqual(frozen(ctx),before)

    def test_delete_frees_explicit_configuration_capacity(self):
        ctx=context({f'P{i}.DAT':b'x' for i in range(32)},limit=32768)
        self.assertEqual(delete(ctx,'PIP:P0.*'),0)
        self.assertEqual(ctx.file_pipes.configure('NEW.DAT',False,1,0,'',0),0)

    def test_busy_later_source_blocks_entire_delete(self):
        ctx=context();handle=open_pipe(ctx,'PIP:B.DAT');handle.position=1
        before=(deepcopy(ctx.file_pipes.pipes),ctx.file_pipes.snapshot())
        self.assertEqual(delete(ctx),3);self.assertEqual((ctx.file_pipes.pipes,ctx.file_pipes.snapshot()),before)
        self.assertEqual(handle.position,1);ctx.file_pipes.close(handle)

    def test_wildcard_rename_moves_plain_pipe_configuration_and_bytes(self):
        ctx=context();configuration=ctx.file_pipes.pipes['PIP:A.DAT']
        self.assertEqual(invoke(None,'RENAME_FILE','PIP:*.DAT','PIP:*.new',ctx=ctx),0)
        self.assertEqual(set(ctx.file_pipes.files),{'PIP:A.NEW','PIP:B.NEW','PIP:A.BAK','PIP:B.BAK'})
        self.assertIs(ctx.file_pipes.pipes['PIP:A.NEW'],configuration)
        self.assertEqual(ctx.file_pipes.files['PIP:A.NEW'],b'a')


class PipeWildcardCrossBackendTests(unittest.TestCase):
    def test_memory_to_pipe_and_pipe_to_memory_templates(self):
        files=rt.MemoryFiles({'seedA.DAT':b'a','seedB.DAT':b'b'})
        ctx=context({'work_seedA.BAK':b'old-a','work_seedB.BAK':b'old-b'},files=files)
        self.assertEqual(copy(ctx,'seed*.DAT','PIP:work_*.BAK'),0)
        self.assertEqual(copy(ctx,'PIP:WORK_*.BAK','saved_*.DAT',overwrite=False),0)
        self.assertEqual(files.files['saved_WORK_SEEDA.DAT'],b'a');self.assertEqual(files.files['saved_WORK_SEEDB.DAT'],b'b')
        self.assertEqual(delete(ctx,'PIP:WORK_*.BAK'),0)

    def test_memory_case_aliases_that_collapse_in_pipe_names_are_rejected(self):
        ctx=context({'A.BAK':b'old'},files=rt.MemoryFiles({'a.dat':b'a','A.DAT':b'b'}));before=frozen(ctx)
        self.assertEqual(copy(ctx,'*.dat','PIP:*.BAK'),2);self.assertEqual(frozen(ctx),before)

    def test_multiple_source_extensions_cannot_collapse_to_one_pipe(self):
        ctx=context({'A.BAK':b'old'},files=rt.MemoryFiles({'a.dat':b'a','a.txt':b'b'}));before=frozen(ctx)
        self.assertEqual(copy(ctx,'*.*','PIP:*.BAK'),2);self.assertEqual(frozen(ctx),before)

    def test_source_target_pipe_overlap_is_rejected(self):
        ctx=context();before=frozen(ctx)
        self.assertEqual(copy(ctx,'PIP:*.DAT','PIP:*.*'),2);self.assertEqual(frozen(ctx),before)

    def test_pipe_to_memory_late_collision_preserves_every_target(self):
        files=rt.MemoryFiles({'saved_B.py':b'old'});ctx=context(files=files);before=files.snapshot()
        self.assertEqual(copy(ctx,'PIP:*.DAT','saved_*.py',overwrite=False),2);self.assertEqual(files.snapshot(),before)

    def test_busy_ordinary_destination_and_source_block_whole_batch(self):
        files=rt.MemoryFiles({'a.dat':b'a','b.dat':b'b','saved_B.py':b'old'});ctx=context(files=files)
        for name,source,target in [('b.dat','*.dat','PIP:*.BAK'),('saved_B.py','PIP:*.DAT','saved_*.py')]:
            with self.subTest(name=name):
                handle=rt.FileHandle();files.open(handle,'R',name);before=(frozen(ctx),files.snapshot())
                self.assertEqual(copy(ctx,source,target),3);self.assertEqual((frozen(ctx),files.snapshot()),before);files.close(handle)

    def test_pipe_to_device_preflights_complete_volume_quota(self):
        files=rt.DeviceFiles({'RD:':{'capacity':1}});ctx=context(files=files);before=deepcopy(files.to_config())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'complete wildcard batch'):copy(ctx,'PIP:*.DAT','RD:*.py')
        self.assertEqual(files.to_config(),before)

    def test_device_to_pipe_and_retaining_device_overwrite_accounting(self):
        files=rt.DeviceFiles({'RD:':{'capacity':100},'FR:':{'capacity':100}},
            {'RD:a.dat':b'aa','RD:b.dat':b'bb','FR:A.py':b'old'})
        ctx=context(files=files)
        self.assertEqual(copy(ctx,'RD:*.dat','PIP:*.BAK'),0)
        self.assertEqual(copy(ctx,'PIP:*.BAK','FR:*.py'),0)
        self.assertEqual(files.files['FR:A.py'],b'aa');self.assertEqual(files._volumes['FR']['garbage'],3)

    def test_readonly_ordinary_source_can_be_exported_to_pipes(self):
        files=rt.DeviceFiles({'RD:':{'capacity':100,'read_only':True}},{'RD:a.dat':b'a','RD:b.dat':b'b'})
        ctx=context(files=files);self.assertEqual(copy(ctx,'RD:*.DAT','PIP:*.BAK'),0)
        self.assertTrue(files._volumes['RD']['read_only'])

    def test_pipe_to_directory_preflights_all_snapshots_before_publication(self):
        from karel2py.storage import atomic_bytes
        with tempfile.TemporaryDirectory() as root:
            (Path(root)/'saved').mkdir();files=rt.DirectoryFiles(root);ctx=context(files=files);read=ctx.file_pipes.read_named;observed=[]
            def source(name):observed.append(name);return read(name)
            def publish(path,data):self.assertEqual(observed,['PIP:A.DAT','PIP:B.DAT']);return atomic_bytes(path,data)
            with patch.object(ctx.file_pipes,'read_named',side_effect=source),patch('karel2py.storage.atomic_bytes',side_effect=publish):
                self.assertEqual(copy(ctx,'PIP:*.DAT','saved/*.py',overwrite=False),0)
            self.assertEqual((Path(root)/'saved/A.py').read_bytes(),b'a');self.assertEqual((Path(root)/'saved/B.py').read_bytes(),b'b')

    def test_directory_to_pipe_keeps_rooted_device_mapping(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root)/'data').mkdir();(Path(root)/'data/a.dat').write_bytes(b'a');(Path(root)/'data/b.dat').write_bytes(b'b')
            files=rt.DirectoryFiles(root,devices={'RD':'data'});ctx=context(files=files)
            self.assertEqual(copy(ctx,'RD:*.DAT','PIP:*.BAK'),0);self.assertEqual(ctx.file_pipes.files['PIP:B.BAK'],b'b')

    def test_missing_directory_parent_blocks_all_pipe_exports(self):
        with tempfile.TemporaryDirectory() as root:
            ctx=context(files=rt.DirectoryFiles(root));before=frozen(ctx)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'parent directory'):copy(ctx,'PIP:*.DAT','missing/*.py')
            self.assertEqual(list(Path(root).iterdir()),[]);self.assertEqual(frozen(ctx),before)

    def test_directory_publication_failure_preserves_pipe_sources(self):
        from karel2py.storage import atomic_bytes
        with tempfile.TemporaryDirectory() as root:
            ctx=context(files=rt.DirectoryFiles(root));before=frozen(ctx)
            def publish(path,data):
                if path.name=='B.py':raise OSError('authored pipe export failure')
                return atomic_bytes(path,data)
            with patch('karel2py.storage.atomic_bytes',side_effect=publish),self.assertRaisesRegex(rt.KarelRuntimeError,'pipe export failure'):
                copy(ctx,'PIP:*.DAT','*.py')
            self.assertEqual((Path(root)/'A.py').read_bytes(),b'a');self.assertFalse((Path(root)/'B.py').exists());self.assertEqual(frozen(ctx),before)


class PipeWildcardGuardTests(unittest.TestCase):
    def test_busy_pipe_source_or_target_preserves_bytes_configuration_and_cursor(self):
        for name in ('PIP:B.DAT','PIP:B.BAK'):
            with self.subTest(name=name):
                ctx=context();handle=open_pipe(ctx,name);handle.position=1;before=(deepcopy(ctx.file_pipes.pipes),ctx.file_pipes.snapshot())
                self.assertEqual(copy(ctx),3);self.assertEqual((ctx.file_pipes.pipes,ctx.file_pipes.snapshot()),before)
                self.assertEqual(handle.position,1);ctx.file_pipes.close(handle)

    def test_source_configuration_change_during_preflight_is_preserved(self):
        ctx=context();read=ctx.file_pipes.read_named
        def source(name):
            result=read(name)
            if name=='PIP:A.DAT':ctx.file_pipes.pipes[name]['form_ele']=99
            return result
        with patch.object(ctx.file_pipes,'read_named',side_effect=source),self.assertRaisesRegex(rt.KarelRuntimeError,'source changed'):
            copy(ctx)
        self.assertEqual(ctx.file_pipes.pipes['PIP:A.DAT']['form_ele'],99);self.assertEqual(ctx.file_pipes.files['PIP:A.BAK'],b'old-a')

    def test_destination_configuration_change_prevents_all_publication(self):
        ctx=context();read=ctx.file_pipes.read_named
        def source(name):
            result=read(name)
            if name=='PIP:B.DAT':ctx.file_pipes.pipes['PIP:A.BAK']['form_ele']=99
            return result
        with patch.object(ctx.file_pipes,'read_named',side_effect=source),self.assertRaisesRegex(rt.KarelRuntimeError,'changed during preflight'):
            copy(ctx)
        self.assertEqual(ctx.file_pipes.pipes['PIP:A.BAK']['form_ele'],99);self.assertEqual(ctx.file_pipes.files['PIP:A.BAK'],b'old-a')

    def test_destination_bytes_changed_during_preflight_are_preserved(self):
        ctx=context();read=ctx.file_pipes.read_named
        def source(name):
            result=read(name)
            if name=='PIP:B.DAT':ctx.file_pipes.files['PIP:A.BAK']=bytearray(b'fresh')
            return result
        with patch.object(ctx.file_pipes,'read_named',side_effect=source),self.assertRaisesRegex(rt.KarelRuntimeError,'bytes changed'):
            copy(ctx)
        self.assertEqual(ctx.file_pipes.files['PIP:A.BAK'],b'fresh');self.assertEqual(ctx.file_pipes.files['PIP:B.BAK'],b'old-b')

    def test_source_bytes_changed_during_preflight_are_preserved(self):
        ctx=context();read=ctx.file_pipes.read_named
        def source(name):
            result=read(name)
            if name=='PIP:B.DAT':ctx.file_pipes.files['PIP:A.DAT']=bytearray(b'fresh')
            return result
        with patch.object(ctx.file_pipes,'read_named',side_effect=source),self.assertRaisesRegex(rt.KarelRuntimeError,'bytes changed'):
            copy(ctx)
        self.assertEqual(ctx.file_pipes.files['PIP:A.DAT'],b'fresh');self.assertEqual(ctx.file_pipes.files['PIP:A.BAK'],b'old-a')

    def test_snapshot_byte_limit_and_execution_budget_fail_before_mutation(self):
        for byte_limit,budget in ((1,100000),(64*1024*1024,4)):
            with self.subTest(byte_limit=byte_limit,budget=budget):
                ctx=context();before=frozen(ctx)
                with patch('karel2py.fileops.WILDCARD_COPY_BYTES',byte_limit),self.assertRaises(rt.KarelRuntimeError):copy(ctx,max_steps=budget)
                self.assertEqual(frozen(ctx),before)

    def test_pipe_delete_budget_failure_keeps_every_configuration(self):
        ctx=context();before=frozen(ctx)
        with self.assertRaises(rt.KarelRuntimeError):delete(ctx,max_steps=4)
        self.assertEqual(frozen(ctx),before)

    def test_unconfigured_service_is_not_created_implicitly(self):
        files=rt.MemoryFiles({'a.dat':b'a'})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'file_pipes'):invoke(files,'COPY_FILE','*.dat','PIP:*.BAK')
        self.assertEqual(files.snapshot(),{'a.dat':b'a'})

    def test_plain_pipe_patterns_reject_paths_and_other_wildcards(self):
        for source in ('PIP:sub/*.DAT','PIP:../*.DAT','PIP:sub?/*.DAT','PIP:[AB]*.DAT'):
            with self.subTest(source=source):
                ctx=context();before=frozen(ctx)
                with self.assertRaises(rt.KarelRuntimeError):copy(ctx,source)
                self.assertEqual(frozen(ctx),before)

    def test_generated_pipe_name_limit_does_not_create_configuration(self):
        name='A'*68+'.DAT';ctx=context({'A.BAK':b'old'},files=rt.MemoryFiles({name:b'a'}));before=frozen(ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'plain ASCII name'):copy(ctx,'*.DAT','PIP:prefix_*.BAK')
        self.assertEqual(frozen(ctx),before)

    def test_corrupt_source_buffer_beyond_configured_capacity_fails_closed(self):
        ctx=context();ctx.file_pipes.files['PIP:A.DAT']=bytearray(b'x'*1025);before=ctx.file_pipes.snapshot()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'retained capacity'):copy(ctx)
        self.assertEqual(ctx.file_pipes.snapshot(),before)

    def test_socket_wildcards_never_fall_through_to_pipe_or_ordinary_files(self):
        ctx=context(files=rt.MemoryFiles({'S1:shadow':b'private'}));before=frozen(ctx)
        for source,target in [('S1:*','PIP:*.BAK'),('PIP:*.DAT','C1:*')]:
            with self.subTest(source=source),self.assertRaisesRegex(rt.KarelRuntimeError,'socket'):copy(ctx,source,target)
        self.assertEqual(frozen(ctx),before);self.assertEqual(ctx.files.files['S1:shadow'],b'private')

    def test_daq_source_pattern_rejects_entire_plain_batch(self):
        ctx=context();ctx.acquisition=rt.Acquisition();ctx.acquisition.register(1,0,1,('INTEGER',),'DAQ.DAT',0)
        before=frozen(ctx)
        for operation in (lambda:copy(ctx),lambda:delete(ctx)):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'DAQ PIP'):operation()
        self.assertEqual(frozen(ctx),before)

    def test_daq_only_source_match_is_rejected_without_becoming_plain_data(self):
        ctx=context();ctx.acquisition=rt.Acquisition();ctx.acquisition.register(1,0,1,('INTEGER',),'DAQ.DAT',0)
        before=frozen(ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'DAQ PIP'):copy(ctx,'PIP:DAQ*.DAT','PIP:*')
        self.assertEqual(frozen(ctx),before);self.assertNotIn('PIP:DAQ.DAT',ctx.file_pipes.files)

    def test_actual_daq_target_name_is_rejected_even_with_plain_config(self):
        ctx=context();ctx.acquisition=rt.Acquisition();ctx.acquisition.register(1,0,1,('INTEGER',),'A.BAK',0)
        before=frozen(ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'DAQ PIP'):copy(ctx)
        self.assertEqual(frozen(ctx),before)

    def test_unrelated_daq_target_template_match_is_not_implicitly_selected(self):
        ctx=context();ctx.acquisition=rt.Acquisition();ctx.acquisition.register(1,0,1,('INTEGER',),'OTHER.BAK',0)
        self.assertEqual(copy(ctx),0);self.assertIn('PIP:OTHER.BAK',ctx.acquisition.files)
        self.assertNotIn('PIP:OTHER.BAK',ctx.file_pipes.files)

    def test_daq_target_added_during_preflight_is_detected_before_publication(self):
        ctx=context();ctx.acquisition=rt.Acquisition();read=ctx.file_pipes.read_named
        def source(name):
            result=read(name)
            if name=='PIP:B.DAT':ctx.acquisition.register(1,0,1,('INTEGER',),'A.BAK',0)
            return result
        before=frozen(ctx)
        with patch.object(ctx.file_pipes,'read_named',side_effect=source),self.assertRaisesRegex(rt.KarelRuntimeError,'DAQ PIP'):copy(ctx)
        self.assertEqual(frozen(ctx),before)

    def test_saved_context_retains_replaced_buffers_and_removed_configuration(self):
        ctx=context();self.assertEqual(copy(ctx),0);self.assertEqual(delete(ctx),0)
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertEqual(restored.file_pipes.to_config(),ctx.file_pipes.to_config())


class PipeWildcardPendingTests(unittest.TestCase):
    def paused_reader(self,ctx,name='A.DAT'):
        body="SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','PIP:"+name+"') READ f(x) CLOSE FILE f"
        p,_=compile_program(body,decl=DECL,context=ctx,sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        return p

    def test_pending_selected_pipe_read_blocks_copy_and_delete_without_consumption(self):
        ctx=context({'A.DAT':b'','A.BAK':b'old'});p=self.paused_reader(ctx)
        handle=p._state.values['F'];before=ctx.file_pipes.snapshot();requests=dict(ctx.file_pipes._reads)
        self.assertEqual(copy(ctx),3);self.assertEqual(delete(ctx),3)
        self.assertEqual(ctx.file_pipes.snapshot(),before);self.assertEqual(ctx.file_pipes._reads,requests);self.assertEqual(handle.position,0)
        p.stop();ctx.file_pipes.close(handle);ctx.to_config()

    def test_unresolved_pending_read_identity_is_preserved_and_blocks_batch(self):
        ctx=context();unknown=object();ctx.file_pipes._reads[12345]=unknown
        before=ctx.file_pipes.snapshot()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Unresolved pending pipe READ identity'):copy(ctx)
        self.assertEqual(ctx.file_pipes.snapshot(),before);self.assertIs(ctx.file_pipes._reads[12345],unknown)
        ctx.file_pipes._reads.clear();ctx.to_config()

    def test_unrelated_pending_read_survives_prepared_bank_commit(self):
        ctx=context({'WAIT.DAT':b'','A.DAT':b'a','A.BAK':b'old'});p=self.paused_reader(ctx,'WAIT.DAT')
        handle=p._state.values['F'];pending=ctx.file_pipes.files['PIP:WAIT.DAT'];requests=dict(ctx.file_pipes._reads)
        self.assertEqual(copy(ctx,'PIP:A*.DAT','PIP:*.BAK'),0)
        self.assertIs(ctx.file_pipes.files['PIP:WAIT.DAT'],pending);self.assertEqual(ctx.file_pipes._reads,requests)
        p.stop();ctx.file_pipes.close(handle);ctx.to_config()


if __name__=='__main__':unittest.main()
