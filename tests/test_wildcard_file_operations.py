"""Authored bounded wildcard file batches across explicit offline backends."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from tests.test_extended_services import compile_program


DECL='f:FILE s:INTEGER'


def statement(operation,source,target=None,overwrite=False,nowait=False):
    flag=lambda value:str(value).upper()
    if operation=='COPY_FILE':return f"COPY_FILE('{source}','{target}',{flag(overwrite)},{flag(nowait)},s)"
    if operation=='DELETE_FILE':return f"DELETE_FILE('{source}',{flag(nowait)},s)"
    return f"RENAME_FILE('{source}','{target}',{flag(nowait)},s)"


def invoke(files,operation,source,target=None,*,overwrite=False,nowait=False,ctx=None,max_steps=100000):
    p,_=compile_program(statement(operation,source,target,overwrite,nowait),decl=DECL,context=ctx or rt.ExecutionContext(files=files))
    return p.run(max_steps=max_steps)['S']


def copy(files,source='src/*.kl',target='dst/*.py',**options):return invoke(files,'COPY_FILE',source,target,**options)
def delete(files,source='src/*.kl',**options):return invoke(files,'DELETE_FILE',source,**options)


def memory():return rt.MemoryFiles({'src/a.kl':b'a','src/b.kl':b'b','src/c.txt':b'c'})


def volumes(initial=None,*,capacity=100,retain=True,readonly=False):
    return rt.DeviceFiles({'RD:':{'capacity':1000},'FR:':{'capacity':capacity,'retain_deleted':retain,'read_only':readonly}},
        initial or {'RD:a.kl':b'aaa','RD:b.kl':b'bbb'})


def directory(root):
    root=Path(root);(root/'src').mkdir();(root/'dst').mkdir();(root/'src'/'deep').mkdir()
    for name,data in {'src/a.kl':b'a','src/b.kl':b'b','src/c.txt':b'c','src/deep/d.kl':b'd'}.items():(root/name).write_bytes(data)
    return rt.DirectoryFiles(root,devices={'RD':'src','FR':'dst','ALIAS':'src'})


class WildcardMemoryTests(unittest.TestCase):
    def test_copy_extension_template_and_binary_payloads(self):
        files=rt.MemoryFiles({'src/a.kl':b'\xff\0a','src/b.kl':b'b','src/c.txt':b'c'})
        self.assertEqual(copy(files),0)
        self.assertEqual(files.snapshot(),{'src/a.kl':b'\xff\0a','src/b.kl':b'b','src/c.txt':b'c','dst/a.py':b'\xff\0a','dst/b.py':b'b'})

    def test_star_substitutes_complete_source_stem_not_pattern_capture(self):
        files=rt.MemoryFiles({'src/partOne.KL':b'a','src/partTwo.KL':b'b'})
        self.assertEqual(copy(files,'src/part*.KL','dst/backup_*.PY'),0)
        self.assertEqual({key for key in files.files if key.startswith('dst/')},{'dst/backup_partOne.PY','dst/backup_partTwo.PY'})

    def test_extension_prefix_suffix_and_multiple_dot_stems(self):
        files=rt.MemoryFiles({'src/part.rev1.KL':b'a'})
        self.assertEqual(copy(files,'src/*.KL','dst/new_*.copy*'),0)
        self.assertEqual(files.snapshot()['dst/new_part.rev1.copyKL'],b'a')

    def test_standalone_destination_star_keeps_complete_filename(self):
        files=memory();self.assertEqual(copy(files,target='dst/*'),0)
        self.assertEqual(files.snapshot()['dst/a.kl'],b'a');self.assertEqual(files.snapshot()['dst/b.kl'],b'b')

    def test_wildcard_destination_with_exact_source(self):
        files=memory();self.assertEqual(copy(files,'src/a.kl','dst/saved_*.py'),0)
        self.assertEqual(files.snapshot()['dst/saved_a.py'],b'a')

    def test_case_insensitive_source_matching_preserves_actual_spelling(self):
        files=rt.MemoryFiles({'Src/Part.KL':b'a'})
        self.assertEqual(copy(files,'src/*.kl','dst/*.py'),0)
        self.assertEqual(files.snapshot()['dst/Part.py'],b'a')

    def test_default_scope_is_root_only(self):
        files=rt.MemoryFiles({'a.kl':b'a','sub/b.kl':b'b'})
        self.assertEqual(copy(files,'*.kl','saved_*.py'),0)
        self.assertEqual(files.snapshot(),{'a.kl':b'a','sub/b.kl':b'b','saved_a.py':b'a'})

    def test_explicit_device_prefix_and_nested_scope(self):
        files=rt.MemoryFiles({'rd:sub/a.kl':b'a','RD:sub/deep/b.kl':b'b','RD:top.kl':b't'})
        self.assertEqual(copy(files,'RD:sub/*.kl','FR:sub/*.py'),0)
        self.assertEqual(files.snapshot()['FR:sub/a.py'],b'a');self.assertNotIn('FR:sub/deep/b.py',files.files)

    def test_copy_and_delete_do_not_recurse(self):
        files=rt.MemoryFiles({'src/a.kl':b'a','src/deep/b.kl':b'b'})
        self.assertEqual(copy(files),0);self.assertNotIn('dst/deep/b.py',files.files)
        self.assertEqual(delete(files),0);self.assertEqual(files.snapshot()['src/deep/b.kl'],b'b')

    def test_delete_all_names_includes_extensionless_only_in_selected_parent(self):
        files=rt.MemoryFiles({'src/a':b'a','src/b.kl':b'b','src/deep/c':b'c','other.kl':b'o'})
        self.assertEqual(delete(files,'src/*'),0)
        self.assertEqual(files.snapshot(),{'src/deep/c':b'c','other.kl':b'o'})

    def test_no_match_returns_one_without_mutation(self):
        files=memory();before=files.snapshot()
        self.assertEqual(copy(files,'src/*.missing'),1);self.assertEqual(delete(files,'src/*.missing'),1)
        self.assertEqual(files.snapshot(),before)

    def test_selected_stored_brackets_are_literal_filename_characters(self):
        files=rt.MemoryFiles({'src/[part].KL':b'a'})
        self.assertEqual(copy(files),0);self.assertEqual(files.snapshot()['dst/[part].py'],b'a')
        self.assertEqual(delete(files),0);self.assertNotIn('src/[part].KL',files.files)

    def test_exact_operations_keep_existing_backend_semantics(self):
        files=rt.MemoryFiles({'a.kl':b'a'})
        self.assertEqual(copy(files,'a.kl','b.txt'),0)
        self.assertEqual(invoke(files,'RENAME_FILE','b.txt','c.txt'),0)
        self.assertEqual(delete(files,'a.kl'),0);self.assertEqual(files.snapshot(),{'c.txt':b'a'})

    def test_nowait_true_completes_synchronously(self):
        files=memory();self.assertEqual(copy(files,nowait=True),0)
        self.assertIn('dst/b.py',files.files);self.assertEqual(delete(files,nowait=True),0)
        self.assertNotIn('src/a.kl',files.files)

    def test_success_preserves_underlying_files_dictionary_identity(self):
        files=memory();identity=files.files
        self.assertEqual(copy(files),0);self.assertIs(files.files,identity)
        self.assertEqual(delete(files),0);self.assertIs(files.files,identity)


class WildcardPreflightTests(unittest.TestCase):
    def test_late_target_collision_blocks_all_earlier_copies(self):
        files=memory();files.files['dst/b.py']=bytearray(b'old');before=files.snapshot()
        self.assertEqual(copy(files),2);self.assertEqual(files.snapshot(),before)

    def test_overwrite_reuses_single_case_alias(self):
        files=memory();files.files['DST/A.PY']=bytearray(b'old')
        self.assertEqual(copy(files,overwrite=True),0)
        self.assertEqual(files.snapshot()['DST/A.PY'],b'a');self.assertNotIn('dst/a.py',files.files)

    def test_ambiguous_destination_case_aliases_block_overwrite(self):
        files=memory();files.files.update({'dst/a.py':bytearray(b'one'),'DST/A.PY':bytearray(b'two')});before=files.snapshot()
        self.assertEqual(copy(files,overwrite=True),2);self.assertEqual(files.snapshot(),before)

    def test_ambiguous_source_case_aliases_block_copy_and_delete(self):
        files=rt.MemoryFiles({'src/A.kl':b'a','SRC/a.KL':b'b'});before=files.snapshot()
        self.assertEqual(copy(files),2);self.assertEqual(delete(files),2);self.assertEqual(files.snapshot(),before)

    def test_constant_destination_many_sources_is_rejected(self):
        files=memory();before=files.snapshot()
        self.assertEqual(copy(files,target='dst/one.py'),2);self.assertEqual(files.snapshot(),before)

    def test_source_target_overlap_is_rejected_even_with_overwrite(self):
        files=memory();before=files.snapshot()
        self.assertEqual(copy(files,target='src/*.kl',overwrite=True),2);self.assertEqual(files.snapshot(),before)

    def test_busy_later_source_blocks_copy_and_delete(self):
        files=memory();handle=rt.FileHandle();files.open(handle,'R','src/b.kl');before=files.snapshot()
        self.assertEqual(copy(files),3);self.assertEqual(delete(files),3)
        self.assertEqual(files.snapshot(),before);self.assertIs(handle.owner,files);files.close(handle)

    def test_busy_case_alias_target_blocks_even_without_overwrite(self):
        files=memory();files.files['DST/A.PY']=bytearray(b'old');handle=rt.FileHandle();files.open(handle,'R','DST/A.PY');before=files.snapshot()
        self.assertEqual(copy(files),3);self.assertEqual(files.snapshot(),before);files.close(handle)

    def test_bad_destination_templates_return_two(self):
        for template in ('dst/a**.py','dst/prefix_*'):
            with self.subTest(template=template):
                files=memory();before=files.snapshot();self.assertEqual(copy(files,target=template),2);self.assertEqual(files.snapshot(),before)

    def test_source_copy_pattern_requires_name_and_type(self):
        files=memory();before=files.snapshot()
        self.assertEqual(copy(files,'src/*','dst/*'),2);self.assertEqual(files.snapshot(),before)

    def test_pattern_syntax_and_paths_fail_closed(self):
        for source,target in [('src/*/*.kl','dst/*.py'),('../*.kl','dst/*.py'),('src/[ab]*.kl','dst/*.py'),
            ('/src/*.kl','dst/*.py'),('src/*.kl','../*.py'),('src/*.kl','dst/*.'),('src/*.kl',r'dst\*.py')]:
            with self.subTest(source=source,target=target):
                files=memory();before=files.snapshot()
                with self.assertRaises(rt.KarelRuntimeError):copy(files,source,target)
                self.assertEqual(files.snapshot(),before)

    def test_reserved_generated_basename_is_rejected(self):
        files=rt.MemoryFiles({'src/a.kl':b'a'});before=files.snapshot()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Reserved'):copy(files,target='dst/CON.*')
        self.assertEqual(files.snapshot(),before)

    def test_wildcard_rename_moves_each_matching_source(self):
        files=memory()
        self.assertEqual(invoke(files,'RENAME_FILE','src/*.kl','dst/*.py'),0)
        self.assertEqual(files.snapshot(),{'dst/a.py':b'a','dst/b.py':b'b','src/c.txt':b'c'})
        self.assertEqual(invoke(files,'RENAME_FILE','dst/a.py','saved/*.txt'),0)
        self.assertEqual(files.snapshot(),{'saved/a.txt':b'a','dst/b.py':b'b','src/c.txt':b'c'})

    def test_copy_snapshot_limit_preflight(self):
        files=rt.MemoryFiles({'src/a.kl':b'aaa','src/b.kl':b'bbb'});before=files.snapshot()
        with patch('karel2py.fileops.WILDCARD_COPY_BYTES',5),self.assertRaisesRegex(rt.KarelRuntimeError,'64 MiB'):
            copy(files)
        self.assertEqual(files.snapshot(),before)

    def test_scan_count_limit_preflight(self):
        files=memory();before=files.snapshot()
        with patch('karel2py.fileops.WILDCARD_FILE_LIMIT',2),self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):
            copy(files)
        self.assertEqual(files.snapshot(),before)

    def test_budget_failure_before_publication_preserves_batch(self):
        for operation in ('COPY_FILE','DELETE_FILE'):
            with self.subTest(operation=operation):
                files=memory();before=files.snapshot()
                with self.assertRaises(rt.KarelRuntimeError):invoke(files,operation,'src/*.kl','dst/*.py',max_steps=4)
                self.assertEqual(files.snapshot(),before)

    def test_preflight_source_addition_is_detected_without_helper_writes(self):
        files=memory();original=files.read_named
        def read(name):
            answer=original(name)
            if name=='src/a.kl':files.files['src/new.kl']=bytearray(b'fresh')
            return answer
        with patch.object(files,'read_named',side_effect=read),self.assertRaisesRegex(rt.KarelRuntimeError,'sources changed'):
            copy(files)
        self.assertNotIn('dst/a.py',files.files);self.assertEqual(files.snapshot()['src/new.kl'],b'fresh')

    def test_source_bytes_changed_during_preflight_are_preserved(self):
        files=memory();original=files.read_named
        def read(name):
            answer=original(name)
            if name=='src/b.kl':files.files['src/a.kl']=bytearray(b'fresh')
            return answer
        with patch.object(files,'read_named',side_effect=read),self.assertRaisesRegex(rt.KarelRuntimeError,'bytes changed'):
            copy(files)
        self.assertEqual(files.snapshot()['src/a.kl'],b'fresh');self.assertNotIn('dst/a.py',files.files)

    def test_missing_pipe_service_and_socket_wildcards_fail_closed(self):
        for source,target,reason in [('PIP:*.DAT','dst/*.py','file_pipes'),('src/*.kl','PIP:*.DAT','file_pipes'),
            ('S1:*','dst/*.py','socket'),('src/*.kl','C2:*','socket')]:
            with self.subTest(source=source,target=target):
                files=memory();before=files.snapshot()
                with self.assertRaisesRegex(rt.KarelRuntimeError,reason):copy(files,source,target)
                self.assertEqual(files.snapshot(),before)


class WildcardDeviceTests(unittest.TestCase):
    def test_cross_volume_copies_and_deletes(self):
        files=volumes();self.assertEqual(copy(files,'rd:*.KL','FR:*.PY'),0)
        self.assertEqual(files.snapshot()['FR:a.PY'],b'aaa');self.assertEqual(files.snapshot()['FR:b.PY'],b'bbb')
        self.assertEqual(delete(files,'RD:*.kl'),0);self.assertEqual(set(files.files),{'FR:a.PY','FR:b.PY'})

    def test_whole_copy_quota_preflight_prevents_partial_targets(self):
        files=volumes(capacity=5);before=deepcopy(files.to_config())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'complete wildcard batch'):copy(files,'RD:*.kl','FR:*.py')
        self.assertEqual(files.to_config(),before)

    def test_retained_overwrite_garbage_is_included_in_batch_quota(self):
        files=volumes({'RD:a.kl':b'aaa','RD:b.kl':b'bbb','FR:a.py':b'xx'},capacity=6);before=deepcopy(files.to_config())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'complete wildcard batch'):copy(files,'RD:*.kl','FR:*.py',overwrite=True)
        self.assertEqual(files.to_config(),before)

    def test_retained_overwrite_and_delete_accounting_are_exact(self):
        files=volumes({'RD:a.kl':b'aaa','RD:b.kl':b'bbb','FR:a.py':b'xx'},capacity=8)
        self.assertEqual(copy(files,'RD:*.kl','FR:*.py',overwrite=True),0)
        self.assertEqual((files._volumes['FR']['garbage'],files.used('FR')),(2,8))
        self.assertEqual(delete(files,'FR:*.py'),0);self.assertEqual((files._volumes['FR']['garbage'],files.used('FR')),(8,8))

    def test_reclaiming_volume_overwrite_does_not_invent_garbage(self):
        files=volumes({'RD:a.kl':b'aaa','RD:b.kl':b'bbb','FR:a.py':b'xx'},capacity=6,retain=False)
        self.assertEqual(copy(files,'RD:*.kl','FR:*.py',overwrite=True),0)
        self.assertEqual((files._volumes['FR']['garbage'],files.used('FR')),(0,6))

    def test_readonly_destination_blocks_every_copy(self):
        files=volumes(readonly=True);before=deepcopy(files.to_config())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'read-only'):copy(files,'RD:*.kl','FR:*.py')
        self.assertEqual(files.to_config(),before)

    def test_readonly_source_blocks_delete_but_permits_copy(self):
        files=volumes();files._volumes['RD']['read_only']=True;before=deepcopy(files.to_config())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'read-only'):delete(files,'RD:*.kl')
        self.assertEqual(files.to_config(),before);self.assertEqual(copy(files,'RD:*.kl','FR:*.py'),0)

    def test_unmounted_source_or_destination_never_mutates(self):
        for volume in ('RD','FR'):
            with self.subTest(volume=volume):
                files=volumes();files._volumes[volume]['mounted']=False;before=deepcopy(files.to_config())
                with self.assertRaisesRegex(rt.KarelRuntimeError,'mounted'):copy(files,'RD:*.kl','FR:*.py')
                self.assertEqual(files.to_config(),before)

    def test_unknown_virtual_device_fails_closed(self):
        files=volumes();before=deepcopy(files.to_config())
        with self.assertRaises(rt.KarelRuntimeError):copy(files,'RD:*.kl','UNKNOWN:*.py')
        self.assertEqual(files.to_config(),before)

    def test_per_file_size_limit_is_checked_before_mutation(self):
        files=volumes();files.limit=2;before=deepcopy(files.to_config())
        with self.assertRaises(rt.KarelRuntimeError):copy(files,'RD:*.kl','FR:*.py')
        self.assertEqual(files.to_config(),before)

    def test_complete_file_count_preflight(self):
        initial={f'RD:unused/{n}.dat':b'' for n in range(32764)}
        initial.update({'RD:a.kl':b'a','RD:b.kl':b'b'})
        files=volumes(initial);before=set(files.files)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'file count'):copy(files,'RD:*.kl','FR:*.py',max_steps=150000)
        self.assertEqual(set(files.files),before)


class WildcardDirectoryTests(unittest.TestCase):
    def test_mapped_device_scope_and_literal_subdirectories(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root)
            self.assertEqual(copy(files,'RD:*.kl','FR:*.py'),0)
            self.assertEqual((Path(root)/'dst/a.py').read_bytes(),b'a');self.assertFalse((Path(root)/'dst/deep').exists())
            self.assertEqual(delete(files,'RD:*.kl'),0)
            self.assertTrue((Path(root)/'src/deep/d.kl').is_file());self.assertTrue((Path(root)/'src/c.txt').is_file())

    def test_complete_preflight_reads_all_sources_before_first_atomic_write(self):
        from karel2py.storage import atomic_bytes
        with tempfile.TemporaryDirectory() as root:
            files=directory(root);read=files.read_named;observed=[]
            def source(name):observed.append(name);return read(name)
            def publish(path,data):
                self.assertEqual(observed,['src/a.kl','src/b.kl']);return atomic_bytes(path,data)
            with patch.object(files,'read_named',side_effect=source),patch('karel2py.storage.atomic_bytes',side_effect=publish):
                self.assertEqual(copy(files),0)

    def test_late_collision_prevents_earlier_publication(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root);(Path(root)/'dst/b.py').write_bytes(b'old')
            self.assertEqual(copy(files),2);self.assertFalse((Path(root)/'dst/a.py').exists())
            self.assertEqual((Path(root)/'dst/b.py').read_bytes(),b'old')

    def test_destination_directory_is_not_replaced_as_a_file(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root);(Path(root)/'dst/b.py').mkdir()
            self.assertEqual(copy(files,overwrite=True),2);self.assertFalse((Path(root)/'dst/a.py').exists())
            self.assertTrue((Path(root)/'dst/b.py').is_dir())

    def test_missing_destination_parent_prevents_all_writes(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'parent directory'):copy(files,target='missing/*.py')
            self.assertEqual(list((Path(root)/'dst').iterdir()),[])

    def test_mapped_aliases_cannot_copy_sources_onto_themselves(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root)
            self.assertEqual(copy(files,'RD:*.kl','ALIAS:*.kl',overwrite=True),2)
            self.assertEqual((Path(root)/'src/a.kl').read_bytes(),b'a')

    def test_busy_unflushed_file_prevents_entire_batch(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root);handle=rt.FileHandle();files.open(handle,'W','src/new.kl')
            self.assertEqual(copy(files),3);self.assertEqual(delete(files),3)
            self.assertTrue((Path(root)/'src/a.kl').is_file());files.close(handle)

    def test_oversized_later_source_blocks_earlier_copy(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root);files.limit=1;(Path(root)/'src/b.kl').write_bytes(b'too long')
            with self.assertRaisesRegex(rt.KarelRuntimeError,'size limit'):copy(files)
            self.assertEqual(list((Path(root)/'dst').iterdir()),[])

    def test_closed_cache_aliases_are_updated_and_removed_with_physical_file(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root);(Path(root)/'dst/a.py').write_bytes(b'old')
            files.files['DST/A.PY']=bytearray(b'old cached alias')
            self.assertEqual(copy(files,overwrite=True),0)
            self.assertEqual(files.files['dst/a.py'],b'a');self.assertNotIn('DST/A.PY',files.files)
            files.files['SRC/A.KL']=bytearray(b'old source cached alias')
            self.assertEqual(delete(files),0);self.assertNotIn('SRC/A.KL',files.files)

    def test_case_alias_overwrite_keeps_actual_target_spelling(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root);(Path(root)/'dst/A.PY').write_bytes(b'old')
            self.assertEqual(copy(files,overwrite=True),0)
            self.assertEqual((Path(root)/'dst/A.PY').read_bytes(),b'a')

    def test_hardlink_source_aliases_fail_before_copy_or_delete(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root)
            try:os.link(Path(root)/'src/a.kl',Path(root)/'src/alias.kl')
            except OSError as error:self.skipTest(str(error))
            self.assertEqual(copy(files),2);self.assertEqual(delete(files),2)
            self.assertTrue((Path(root)/'src/a.kl').exists())

    def test_hardlink_target_source_overlap_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root)
            try:os.link(Path(root)/'src/a.kl',Path(root)/'dst/a.py')
            except OSError as error:self.skipTest(str(error))
            self.assertEqual(copy(files,overwrite=True),2)
            self.assertFalse((Path(root)/'dst/b.py').exists())

    def test_symlink_later_source_prevents_any_deletion(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root)
            try:(Path(root)/'src/z.kl').symlink_to(Path(root)/'src/a.kl')
            except OSError as error:self.skipTest(str(error))
            with self.assertRaisesRegex(rt.KarelRuntimeError,'Symlink'):delete(files)
            self.assertTrue((Path(root)/'src/a.kl').is_file())

    def test_target_change_during_preflight_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root);target=Path(root)/'dst/a.py';target.write_bytes(b'old');read=files.read_named
            def source(name):
                result=read(name)
                if name=='src/b.kl':target.write_bytes(b'fresh changed content')
                return result
            with patch.object(files,'read_named',side_effect=source),self.assertRaisesRegex(rt.KarelRuntimeError,'changed during preflight'):
                copy(files,overwrite=True)
            self.assertEqual(target.read_bytes(),b'fresh changed content');self.assertFalse((Path(root)/'dst/b.py').exists())

    def test_delete_does_not_read_or_reject_oversized_regular_files(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root);files.limit=1;(Path(root)/'src/b.kl').write_bytes(b'larger than the read limit')
            with patch.object(files,'read_named',side_effect=AssertionError('DELETE must not read bytes')):
                self.assertEqual(delete(files),0)
            self.assertFalse((Path(root)/'src/b.kl').exists());self.assertTrue((Path(root)/'src/deep/d.kl').exists())

    def test_host_unlink_failure_can_leave_ordered_partial_directory_deletion(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root);original=files.delete
            def remove(name):
                if name=='src/b.kl':raise OSError('authored unlink failure')
                return original(name)
            with patch.object(files,'delete',side_effect=remove),self.assertRaisesRegex(rt.KarelRuntimeError,'unlink failure'):
                delete(files)
            self.assertFalse((Path(root)/'src/a.kl').exists());self.assertTrue((Path(root)/'src/b.kl').exists())

    def test_host_io_failure_can_leave_earlier_per_file_atomic_copies(self):
        from karel2py.storage import atomic_bytes
        with tempfile.TemporaryDirectory() as root:
            files=directory(root)
            def publish(path,data):
                if path.name=='b.py':raise OSError('authored publication failure')
                return atomic_bytes(path,data)
            with patch('karel2py.storage.atomic_bytes',side_effect=publish),self.assertRaisesRegex(rt.KarelRuntimeError,'publication failure'):
                copy(files)
            self.assertEqual((Path(root)/'dst/a.py').read_bytes(),b'a');self.assertFalse((Path(root)/'dst/b.py').exists())
            self.assertEqual((Path(root)/'src/b.kl').read_bytes(),b'b')


if __name__=='__main__':unittest.main()
