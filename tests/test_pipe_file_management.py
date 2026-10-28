"""Authored closed-pipe management and finite cross-backend snapshot copies."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from tests.test_extended_services import compile_program,run


DECL='f:FILE names:ARRAY[3] OF STRING[80] n,s:INTEGER'


def pipe_bank(initial=None,*,sectors=1):
    bank=rt.FilePipes()
    for name,data in (initial or {'A.DAT':b'abc','B.DAT':b''}).items():
        assert bank.configure(name,True,sectors,8,'DICT',3)==0
        bank.feed(name,data)
    return bank


def context(initial=None,*,files=None):return rt.ExecutionContext(file_pipes=pipe_bank(initial),files=files)


def execute(body,ctx=None,**options):return run(body,decl=DECL,context=ctx or context(),**options)


def open_pipe(bank,name='A.DAT',mode='RW'):
    handle=rt.FileHandle();bank.open_for(None,handle,mode,name);return handle


class PipeFileManagementTests(unittest.TestCase):
    def test_pipe_to_pipe_copy_needs_no_ordinary_backend(self):
        ctx=context({'A.DAT':b'\xff\0abc','B.DAT':b'old'})
        values=execute("COPY_FILE('pip:/a.dat','PIP:b.dat',TRUE,FALSE,s)",ctx)
        self.assertEqual(values['S'],0)
        self.assertEqual(ctx.file_pipes.files['PIP:B.DAT'],b'\xff\0abc')
        self.assertEqual(ctx.file_pipes.files['PIP:A.DAT'],b'\xff\0abc')

    def test_snapshot_copy_preserves_destination_configuration(self):
        ctx=context();before=deepcopy(ctx.file_pipes.pipes['PIP:B.DAT'])
        execute("COPY_FILE('PIP:A.DAT','PIP:B.DAT',TRUE,TRUE,s)",ctx)
        self.assertEqual(ctx.file_pipes.pipes['PIP:B.DAT'],before)

    def test_configured_empty_destination_still_requires_overwrite_true(self):
        ctx=context();values=execute("COPY_FILE('PIP:A.DAT','PIP:B.DAT',FALSE,FALSE,s)",ctx)
        self.assertEqual(values['S'],2);self.assertEqual(ctx.file_pipes.files['PIP:B.DAT'],b'')

    def test_missing_destination_does_not_create_an_implicit_pipe(self):
        ctx=context();before=ctx.file_pipes.to_config()
        values=execute("COPY_FILE('PIP:A.DAT','PIP:NEW.DAT',TRUE,FALSE,s)",ctx)
        self.assertEqual(values['S'],1);self.assertEqual(ctx.file_pipes.to_config(),before)

    def test_missing_source_preserves_destination(self):
        ctx=context();before=ctx.file_pipes.to_config()
        values=execute("COPY_FILE('PIP:MISSING.DAT','PIP:B.DAT',TRUE,FALSE,s)",ctx)
        self.assertEqual(values['S'],1);self.assertEqual(ctx.file_pipes.to_config(),before)

    def test_source_and_destination_must_both_be_closed(self):
        for name in ('A.DAT','B.DAT'):
            ctx=context();handle=open_pipe(ctx.file_pipes,name);before=ctx.file_pipes.snapshot()
            values=execute("COPY_FILE('PIP:A.DAT','PIP:B.DAT',TRUE,FALSE,s)",ctx)
            self.assertEqual(values['S'],3);self.assertEqual(ctx.file_pipes.snapshot(),before)
            ctx.file_pipes.close(handle)

    def test_waiting_read_blocks_management_until_stopped_and_closed(self):
        ctx=context({'A.DAT':b'','B.DAT':b''})
        program,_=compile_program("SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','PIP:A.DAT') READ f(n,CR)",
            decl=DECL,context=ctx,sleep=lambda _:setattr(program._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):program.run()
        caller=rt.ExecutionContext(file_pipes=ctx.file_pipes)
        for statement in ("DELETE_FILE('PIP:A.DAT',FALSE,s)","RENAME_FILE('PIP:A.DAT','PIP:NEW',FALSE,s)",
                          "COPY_FILE('PIP:B.DAT','PIP:A.DAT',TRUE,FALSE,s)"):
            self.assertEqual(execute(statement,caller)['S'],3)
        program.stop();self.assertEqual(ctx.file_pipes._reads,{})
        ctx.file_pipes.close(program._state.values['F'])
        self.assertEqual(execute("DELETE_FILE('PIP:A.DAT',FALSE,s)",caller)['S'],0)

    def test_busy_destination_takes_precedence_over_missing_source(self):
        ctx=context();handle=open_pipe(ctx.file_pipes,'B.DAT')
        self.assertEqual(execute("COPY_FILE('PIP:MISSING','PIP:B.DAT',TRUE,FALSE,s)",ctx)['S'],3)
        ctx.file_pipes.close(handle)

    def test_same_pipe_copy_is_an_explicit_snapshot_replacement(self):
        ctx=context();before=ctx.file_pipes.to_config()
        self.assertEqual(execute("COPY_FILE('PIP:A.DAT','pip:/a.dat',TRUE,FALSE,s)",ctx)['S'],0)
        self.assertEqual(ctx.file_pipes.to_config(),before)

    def test_delete_removes_closed_pipe_configuration_and_bytes(self):
        ctx=context();values=execute("DELETE_FILE('pip:/a.dat',TRUE,s)",ctx)
        self.assertEqual(values['S'],0);self.assertNotIn('PIP:A.DAT',ctx.file_pipes.files)
        self.assertNotIn('PIP:A.DAT',ctx.file_pipes.pipes)
        self.assertEqual(execute("DELETE_FILE('PIP:A.DAT',FALSE,s)",ctx)['S'],1)

    def test_delete_releases_reserved_pipe_capacity(self):
        bank=rt.FilePipes(limit=2048);bank.configure('A',False,1,0,'',0);bank.configure('B',False,1,0,'',0)
        ctx=rt.ExecutionContext(file_pipes=bank)
        self.assertEqual(bank.configure('C',False,1,0,'',0),5)
        self.assertEqual(execute("DELETE_FILE('PIP:A',FALSE,s)",ctx)['S'],0)
        self.assertEqual(bank.configure('C',False,1,0,'',0),0)

    def test_open_delete_and_rename_preserve_bytes_metadata_and_cursor(self):
        for operation in ("DELETE_FILE('PIP:A.DAT',FALSE,s)","RENAME_FILE('PIP:A.DAT','PIP:NEW.DAT',FALSE,s)"):
            ctx=context();handle=open_pipe(ctx.file_pipes);handle.position=2
            before=deepcopy(ctx.file_pipes.pipes);values=execute(operation,ctx)
            self.assertEqual(values['S'],3);self.assertEqual(ctx.file_pipes.pipes,before)
            self.assertEqual(handle.position,2);self.assertEqual(ctx.file_pipes.files['PIP:A.DAT'],b'abc')
            ctx.file_pipes.close(handle)

    def test_rename_moves_configuration_without_reallocation(self):
        ctx=context();before=deepcopy(ctx.file_pipes.pipes['PIP:A.DAT'])
        values=execute("RENAME_FILE('pip:/a.dat','pip:/renamed.dat',TRUE,s)",ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.file_pipes.pipes['PIP:RENAMED.DAT'],before)
        self.assertEqual(ctx.file_pipes.files['PIP:RENAMED.DAT'],b'abc')
        self.assertNotIn('PIP:A.DAT',ctx.file_pipes.pipes);self.assertNotIn('PIP:A.DAT',ctx.file_pipes.files)

    def test_rename_refuses_existing_destination_or_missing_source(self):
        for operation,code in (("RENAME_FILE('PIP:A.DAT','PIP:B.DAT',FALSE,s)",2),
                               ("RENAME_FILE('PIP:A.DAT','pip:/a.dat',FALSE,s)",2),
                               ("RENAME_FILE('PIP:MISSING','PIP:NEW',FALSE,s)",1)):
            ctx=context();before=ctx.file_pipes.to_config()
            self.assertEqual(execute(operation,ctx)['S'],code);self.assertEqual(ctx.file_pipes.to_config(),before)

    def test_cross_bank_rename_is_rejected_without_creating_a_file(self):
        for operation in ("RENAME_FILE('PIP:A.DAT','ordinary',FALSE,s)","RENAME_FILE('ordinary','PIP:NEW',FALSE,s)"):
            ctx=context(files=rt.MemoryFiles({'ordinary':b'old'}));before=ctx.to_config()
            self.assertEqual(execute(operation,ctx)['S'],2)
            self.assertEqual(ctx.file_pipes.to_config(),before['file_pipes']);self.assertEqual(ctx.files.files['ordinary'],b'old')

    def test_direct_pipe_backend_methods_preserve_canonical_configuration(self):
        bank=pipe_bank();self.assertEqual(bank.copy('a.dat','b.dat',True),0)
        self.assertEqual(bank.read_named('pip:/B.dat'),(0,b'abc'))
        self.assertEqual(bank.rename('b.dat','new.dat'),0)
        self.assertEqual(bank.list_names('*.dat'),['PIP:A.DAT','PIP:NEW.DAT'])
        self.assertEqual(bank.delete('new.dat'),0);self.assertEqual(bank.read_named('new.dat'),(1,None))

    def test_rename_does_not_need_an_extra_pipe_slot(self):
        bank=rt.FilePipes(limit=32768)
        for index in range(32):self.assertEqual(bank.configure('P'+str(index),False,1,0,'',0),0)
        ctx=rt.ExecutionContext(file_pipes=bank)
        self.assertEqual(execute("RENAME_FILE('PIP:P0','PIP:NEW',FALSE,s)",ctx)['S'],0)
        self.assertEqual(len(bank.pipes),32)


class PipeCrossBackendCopyTests(unittest.TestCase):
    def test_memory_to_pipe_and_pipe_to_memory_copy_binary_bytes(self):
        ctx=context(files=rt.MemoryFiles({'source':b'\xff\0hello'}))
        values=execute("COPY_FILE('source','PIP:B.DAT',TRUE,FALSE,s) COPY_FILE('PIP:B.DAT','result',FALSE,TRUE,s)",ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.files.files['result'],b'\xff\0hello')
        self.assertEqual(ctx.files.files['source'],b'\xff\0hello')

    def test_snapshot_copy_uses_retained_history_after_circular_overflow(self):
        ctx=context(files=rt.MemoryFiles());ctx.file_pipes.feed('A.DAT',b'x'*1024+b'end')
        execute("COPY_FILE('PIP:A.DAT','result',FALSE,FALSE,s)",ctx)
        self.assertEqual(ctx.files.files['result'],b'x'*1021+b'end')

    def test_pipe_capacity_failure_preserves_all_destination_bytes(self):
        ctx=context(files=rt.MemoryFiles({'source':b'x'*1025}));before=ctx.file_pipes.to_config()
        self.assertEqual(execute("COPY_FILE('source','PIP:A.DAT',TRUE,FALSE,s)",ctx)['S'],4)
        self.assertEqual(ctx.file_pipes.to_config(),before)

    def test_exact_pipe_capacity_replaces_instead_of_appending(self):
        ctx=context(files=rt.MemoryFiles({'source':b'x'*1024}))
        self.assertEqual(execute("COPY_FILE('source','PIP:A.DAT',TRUE,FALSE,s)",ctx)['S'],0)
        self.assertEqual(ctx.file_pipes.files['PIP:A.DAT'],b'x'*1024)

    def test_memory_destination_overwrite_policy_and_limits(self):
        ctx=context(files=rt.MemoryFiles({'result':b'xy'},limit=2))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'file size limit'):
            execute("COPY_FILE('PIP:A.DAT','result',TRUE,FALSE,s)",ctx)
        self.assertEqual(ctx.files.files['result'],b'xy')

    def test_existing_ordinary_destination_requires_overwrite(self):
        ctx=context(files=rt.MemoryFiles({'result':b'old'}))
        self.assertEqual(execute("COPY_FILE('PIP:A.DAT','result',FALSE,FALSE,s)",ctx)['S'],2)
        self.assertEqual(ctx.files.files['result'],b'old')

    def test_empty_snapshot_truncates_an_explicitly_overwritten_destination(self):
        ctx=context({'EMPTY':b''},files=rt.MemoryFiles({'result':b'old'}))
        self.assertEqual(execute("COPY_FILE('PIP:EMPTY','result',TRUE,FALSE,s)",ctx)['S'],0)
        self.assertEqual(ctx.files.files['result'],b'')

    def test_closed_ordinary_source_is_required(self):
        files=rt.MemoryFiles({'source':b'data'});handle=rt.FileHandle();files.open(handle,'R','source')
        ctx=context(files=files);before=ctx.file_pipes.to_config()
        self.assertEqual(execute("COPY_FILE('source','PIP:A.DAT',TRUE,FALSE,s)",ctx)['S'],3)
        self.assertEqual(ctx.file_pipes.to_config(),before);files.close(handle)

    def test_closed_ordinary_destination_is_required(self):
        files=rt.MemoryFiles({'result':b'old'});handle=rt.FileHandle();files.open(handle,'RW','result')
        ctx=context(files=files)
        self.assertEqual(execute("COPY_FILE('PIP:A.DAT','result',TRUE,FALSE,s)",ctx)['S'],3)
        self.assertEqual(files.files['result'],b'old');files.close(handle)

    def test_directory_device_aliases_copy_in_both_directions(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'data').mkdir();(root/'data/source.bin').write_bytes(b'\xff\0disk')
            ctx=context(files=rt.DirectoryFiles(root,devices={'MD':'data'}))
            values=execute("COPY_FILE('MD:source.bin','PIP:A.DAT',TRUE,FALSE,s) COPY_FILE('PIP:A.DAT','MD:result.bin',FALSE,FALSE,s)",ctx)
            self.assertEqual(values['S'],0);self.assertEqual((root/'data/result.bin').read_bytes(),b'\xff\0disk')
            self.assertEqual(ctx.files.files['data/result.bin'],b'\xff\0disk')

    def test_directory_alias_of_an_open_destination_is_busy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'result').write_bytes(b'old')
            files=rt.DirectoryFiles(root,devices={'MD':''});handle=rt.FileHandle();files.open(handle,'RW','result')
            ctx=context(files=files)
            self.assertEqual(execute("COPY_FILE('PIP:A.DAT','MD:result',TRUE,FALSE,s)",ctx)['S'],3)
            self.assertEqual((root/'result').read_bytes(),b'old');files.close(handle)

    def test_directory_alias_of_an_open_source_is_busy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'source').write_bytes(b'data')
            files=rt.DirectoryFiles(root,devices={'MD':''});handle=rt.FileHandle();files.open(handle,'RW','source')
            ctx=context(files=files);before=ctx.file_pipes.to_config()
            self.assertEqual(execute("COPY_FILE('MD:source','PIP:A.DAT',TRUE,FALSE,s)",ctx)['S'],3)
            self.assertEqual(ctx.file_pipes.to_config(),before);files.close(handle)

    def test_directory_failed_publication_preserves_disk_and_buffer(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'result').write_bytes(b'old')
            files=rt.DirectoryFiles(root);handle=rt.FileHandle();files.open(handle,'R','result');files.close(handle)
            ctx=context(files=files)
            with patch('karel2py.storage.os.replace',side_effect=OSError('authored publication failure')):
                with self.assertRaisesRegex(rt.KarelRuntimeError,'publication failure'):
                    execute("COPY_FILE('PIP:A.DAT','result',TRUE,FALSE,s)",ctx)
            self.assertEqual((root/'result').read_bytes(),b'old');self.assertEqual(files.files['result'],b'old')
            self.assertEqual(sorted(p.name for p in root.iterdir()),['result'])

    def test_directory_parent_and_traversal_fail_before_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ctx=context(files=rt.DirectoryFiles(root))
            for target in ('../outside','/absolute','missing/result','C:/absolute'):
                with self.subTest(target=target),self.assertRaises(rt.KarelRuntimeError):
                    execute(f"COPY_FILE('PIP:A.DAT','{target}',TRUE,FALSE,s)",ctx)
                self.assertEqual(list(root.iterdir()),[])

    def test_directory_size_limit_preserves_pipe_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'source').write_bytes(b'large')
            ctx=context(files=rt.DirectoryFiles(root,limit=2));before=ctx.file_pipes.to_config()
            with self.assertRaisesRegex(rt.KarelRuntimeError,'size limit'):
                execute("COPY_FILE('source','PIP:A.DAT',TRUE,FALSE,s)",ctx)
            self.assertEqual(ctx.file_pipes.to_config(),before)

    def test_directory_destination_size_limit_preserves_disk_and_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'result').write_bytes(b'xy');files=rt.DirectoryFiles(root,limit=2)
            handle=rt.FileHandle();files.open(handle,'R','result');files.close(handle);ctx=context(files=files)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'size limit'):
                execute("COPY_FILE('PIP:A.DAT','result',TRUE,FALSE,s)",ctx)
            self.assertEqual((root/'result').read_bytes(),b'xy');self.assertEqual(files.files['result'],b'xy')

    def test_directory_symlink_paths_are_not_copy_endpoints(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'source').write_bytes(b'old')
            try:(root/'alias').symlink_to(root/'source')
            except (OSError,NotImplementedError):self.skipTest('Symlink creation is unavailable in this environment')
            ctx=context(files=rt.DirectoryFiles(root));before=ctx.file_pipes.to_config()
            for statement in ("COPY_FILE('alias','PIP:A.DAT',TRUE,FALSE,s)","COPY_FILE('PIP:A.DAT','alias',TRUE,FALSE,s)"):
                with self.assertRaisesRegex(rt.KarelRuntimeError,'Symlink'):execute(statement,ctx)
            self.assertEqual(ctx.file_pipes.to_config(),before);self.assertEqual((root/'source').read_bytes(),b'old')

    def test_device_source_and_destination_use_volume_names_and_accounting(self):
        files=rt.DeviceFiles({'RD:':{'capacity':100},'FR:':{'capacity':100}}, {'RD:source':b'device','FR:result':b'old'})
        ctx=context(files=files)
        values=execute("COPY_FILE('rd:source','PIP:A.DAT',TRUE,FALSE,s) COPY_FILE('PIP:A.DAT','fr:result',TRUE,FALSE,s)",ctx)
        self.assertEqual(values['S'],0);self.assertEqual(files.files['FR:result'],b'device')
        self.assertEqual(files._volumes['FR']['garbage'],3)

    def test_device_capacity_failure_preserves_destination_and_garbage(self):
        files=rt.DeviceFiles({'FR:':{'capacity':5}},{'FR:result':b'old'})
        ctx=context(files=files);before=files.to_config()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity exceeded'):
            execute("COPY_FILE('PIP:A.DAT','FR:result',TRUE,FALSE,s)",ctx)
        self.assertEqual(files.to_config(),before)

    def test_unmounted_or_readonly_device_destinations_remain_unchanged(self):
        for options in ({'mounted':False},{'read_only':True}):
            files=rt.DeviceFiles({'RD:':dict(capacity=100,**options)},{'RD:result':b'old'})
            ctx=context(files=files);before=files.to_config()
            with self.assertRaises(rt.KarelRuntimeError):execute("COPY_FILE('PIP:A.DAT','RD:result',TRUE,FALSE,s)",ctx)
            self.assertEqual(files.to_config(),before)

    def test_copy_budget_failure_keeps_complete_destination_snapshot(self):
        ctx=context({'A.DAT':b'x'*1024,'B.DAT':b'old'},files=rt.MemoryFiles())
        program,_=compile_program("s=99 COPY_FILE('PIP:A.DAT','PIP:B.DAT',TRUE,FALSE,s)",decl=DECL,context=ctx)
        before=ctx.file_pipes.to_config()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):program.run(max_steps=2)
        self.assertEqual(ctx.file_pipes.to_config(),before);self.assertEqual(program.snapshot()['S'],99)


class PipeListingAndScopeTests(unittest.TestCase):
    def test_listing_formats_zero_through_three_use_canonical_pipe_names(self):
        for form,expected in ((0,['PIP:A.DAT','PIP:B.DAT']),(1,['A','B']),(2,['DAT','DAT']),(3,['A.DAT','B.DAT'])):
            values=execute(f"FILE_LIST('pip:/*.dat',0,{form},names,n,s)")
            self.assertEqual((values['N'],values['S']),(2,0));self.assertEqual(values['NAMES'][:2],expected)

    def test_metadata_listing_uses_current_byte_size_and_blank_dates(self):
        values=execute("FILE_LIST('PIP:A.DAT',0,4,names,n,s)")
        text=values['NAMES'][0]
        self.assertEqual((len(text),text[:10],text[20:25],text[25:]),(40,'A       .D','3    ',' '*15))

    def test_listing_while_open_retains_cursors_and_includes_pending_bytes(self):
        ctx=context();handle=open_pipe(ctx.file_pipes);ctx.file_pipes.write(handle,b'xyz')
        handle.position=2
        values=execute("FILE_LIST('PIP:A.*',0,4,names,n,s)",ctx)
        self.assertEqual(values['S'],0);self.assertEqual(handle.position,2)
        self.assertEqual(values['NAMES'][0][20:25],'6    ')
        ctx.file_pipes.close(handle)

    def test_listing_pagination_and_question_wildcards_preserve_unused_slots(self):
        values=execute("names[2]='tail' FILE_LIST('PIP:?.DAT',1,3,names,n,s)")
        self.assertEqual((values['NAMES'][:2],values['N'],values['S']),(['B.DAT','tail'],1,0))

    def test_empty_listing_has_no_ordinary_backend_dependency(self):
        values=execute("FILE_LIST('PIP:NONE*',0,0,names,n,s)")
        self.assertEqual((values['N'],values['S']),(0,0))

    def test_listing_capacity_and_format_failures_preserve_outputs(self):
        ctx=context();program,_=compile_program("names[1]='old' n=99 FILE_LIST('PIP:*',0,0,names,n,s)",
            decl='names:ARRAY[2] OF STRING[3] n,s:INTEGER',context=ctx)
        values=program.run();self.assertEqual((values['NAMES'][0],values['N'],values['S']),('old',99,3))
        values=execute("names[1]='old' n=99 FILE_LIST('PIP:*',0,5,names,n,s)")
        self.assertEqual((values['NAMES'][0],values['N'],values['S']),('old',99,2))

    def test_listing_budget_failure_retains_the_whole_page(self):
        ctx=context();program,_=compile_program("names[1]='old' n=99 FILE_LIST('PIP:*',0,3,names,n,s)",decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):program.run(max_steps=4)
        self.assertEqual((program.snapshot()['NAMES'][0],program.snapshot()['N']),('old',99))

    def test_pipe_listing_rejects_path_and_character_class_patterns(self):
        for pattern in ('PIP:../*','PIP:dir/*','PIP:A[B].DAT','PIP:A:B','PIP:'):
            with self.subTest(pattern=pattern),self.assertRaises(rt.KarelRuntimeError):
                execute(f"FILE_LIST('{pattern}',0,0,names,n,s)")

    def test_invalid_pipe_names_never_fall_through_to_ordinary_files(self):
        for name in ('PIP:../A','PIP:folder/A','PIP:/../A','PIP:A:B','PIP:','PIP:\\A'):
            files=rt.MemoryFiles({name:b'shadow'});ctx=context(files=files)
            with self.subTest(name=name),self.assertRaises(rt.KarelRuntimeError):execute(f"DELETE_FILE('{name}',FALSE,s)",ctx)
            self.assertEqual(files.files[name],b'shadow')

    def test_explicit_pipe_namespace_wins_over_ordinary_shadow_names(self):
        ctx=context(files=rt.MemoryFiles({'PIP:A.DAT':b'shadow'}))
        execute("COPY_FILE('PIP:A.DAT','result',FALSE,FALSE,s)",ctx)
        self.assertEqual(ctx.files.files['result'],b'abc');self.assertEqual(ctx.files.files['PIP:A.DAT'],b'shadow')

    def test_socket_names_cannot_be_cross_copied_through_ordinary_shadow_files(self):
        ctx=context(files=rt.MemoryFiles({'S1:':b'shadow'}))
        for statement in ("COPY_FILE('S1:','PIP:A.DAT',TRUE,FALSE,s)","COPY_FILE('PIP:A.DAT','S1:',TRUE,FALSE,s)"):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'socket names'):execute(statement,ctx)
        self.assertEqual(ctx.files.files['S1:'],b'shadow');self.assertEqual(ctx.file_pipes.files['PIP:A.DAT'],b'abc')

    def test_daq_names_are_excluded_and_namespace_collisions_reject(self):
        acquisition=rt.Acquisition();acquisition.register(1,0,1,('INTEGER',),'daq.dat',0)
        ctx=rt.ExecutionContext(file_pipes=pipe_bank(),acquisition=acquisition)
        values=execute("FILE_LIST('PIP:*',0,3,names,n,s)",ctx)
        self.assertEqual(values['NAMES'][:2],['A.DAT','B.DAT'])
        for statement in ("DELETE_FILE('PIP:DAQ.DAT',FALSE,s)","RENAME_FILE('PIP:A.DAT','PIP:DAQ.DAT',FALSE,s)",
                          "COPY_FILE('PIP:DAQ.DAT','PIP:A.DAT',TRUE,FALSE,s)",
                          "COPY_FILE('PIP:A.DAT','PIP:DAQ.DAT',TRUE,FALSE,s)"):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'DAQ PIP'):execute(statement,ctx)
        ctx.file_pipes.configure('DAQ.DAT',False,1,0,'',0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'DAQ PIP'):execute("FILE_LIST('PIP:*',0,0,names,n,s)",ctx)

    def test_missing_required_services_fail_without_implicit_creation(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'file_pipes'):
            execute("DELETE_FILE('PIP:A.DAT',FALSE,s)",rt.ExecutionContext(files=rt.MemoryFiles()))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'files'):
            execute("COPY_FILE('PIP:A.DAT','ordinary',TRUE,FALSE,s)")

    def test_roundtrip_keeps_renamed_configuration_and_replaced_bytes(self):
        ctx=context(files=rt.MemoryFiles({'source':b'new'}))
        execute("COPY_FILE('source','PIP:A.DAT',TRUE,FALSE,s) RENAME_FILE('PIP:A.DAT','PIP:RENAMED',FALSE,s) DELETE_FILE('PIP:B.DAT',FALSE,s)",ctx)
        saved=ctx.to_config();restored=rt.ExecutionContext.from_config(json.loads(json.dumps(saved)))
        self.assertEqual(restored.to_config(),saved)
        self.assertEqual(execute("COPY_FILE('PIP:RENAMED','result',FALSE,FALSE,s)",restored)['S'],0)
        self.assertEqual(restored.files.files['result'],b'new')

    def test_non_pipe_operations_keep_the_ordinary_backend_behavior(self):
        files=rt.MemoryFiles({'a':b'ordinary'});ctx=context(files=files)
        values=execute("COPY_FILE('a','b',FALSE,FALSE,s) RENAME_FILE('b','c',FALSE,s) DELETE_FILE('a',FALSE,s)",ctx)
        self.assertEqual(values['S'],0);self.assertEqual(files.snapshot(),{'c':b'ordinary'})


if __name__=='__main__':unittest.main()
