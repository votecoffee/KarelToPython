"""Authored component/globstar FILE batches over explicit offline backends."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import os
from types import SimpleNamespace
from unittest.mock import patch
from karel2py import runtime as rt,translate_project
from karel2py import fileops
from tests.test_extended_services import compile_program
from tests.test_wildcard_file_operations import invoke,statement
from tests.test_cross_bank_rename import pipes

DATA={'src/root.kl':b'r','src/cell1/a.kl':b'a','src/cell2/b.KL':b'b','src/cell1/deep/c.kl':b'c','src/cell1/a.txt':b't','else/other.kl':b'o'}
MATCHES={'dst/a.py':b'a','dst/b.py':b'b','dst/c.py':b'c','dst/root.py':b'r'}
PATTERN='src/**/*.kl'


def memory(data=None):return rt.MemoryFiles(DATA if data is None else data)
def copy(bank,source=PATTERN,target='dst/*.py',**options):return invoke(bank,'COPY_FILE',source,target,**options)
def delete(bank,source=PATTERN,**options):return invoke(bank,'DELETE_FILE',source,**options)
def rename(bank,source=PATTERN,target='dst/*.py',**options):return invoke(bank,'RENAME_FILE',source,target,**options)
def selected(bank):return {n:v for n,v in bank.snapshot().items() if n.startswith('dst/')}
def disk(root):return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}


@contextmanager
def directory(data=None,**options):
    with tempfile.TemporaryDirectory(prefix='karel_directory_glob_') as folder:
        root=Path(folder).resolve();assert root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        (root/'dst').mkdir()
        for name,value in (DATA if data is None else data).items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
        yield root,rt.DirectoryFiles(root,**options)


def devices(*,capacity=1000,retain=False,initial=None,**flags):
    return rt.DeviceFiles({'RD:':{'capacity':1000},'FR:':dict(capacity=capacity,retain_deleted=retain,**flags)},initial or {'RD:'+n:v for n,v in DATA.items()})


class DirectoryGlobMemoryTests(unittest.TestCase):
    def test_globstar_copies_zero_and_multiple_directory_levels(self):
        bank=memory();self.assertEqual(copy(bank),0);self.assertEqual(selected(bank),MATCHES)
    def test_single_star_directory_selects_exactly_one_level(self):
        bank=memory();self.assertEqual(copy(bank,'src/*/*.kl'),0);self.assertEqual(selected(bank),{'dst/a.py':b'a','dst/b.py':b'b'})
    def test_question_directory_matches_exactly_one_character(self):
        bank=memory();self.assertEqual(copy(bank,'src/cell?/*.kl'),0);self.assertEqual(selected(bank),{'dst/a.py':b'a','dst/b.py':b'b'})
    def test_literal_suffix_after_globstar(self):
        bank=memory();self.assertEqual(copy(bank,'src/**/deep/*.kl'),0);self.assertEqual(selected(bank),{'dst/c.py':b'c'})
    def test_multiple_globstars_do_not_duplicate_source_files(self):
        bank=memory();self.assertEqual(copy(bank,'src/**/**/a.kl'),0);self.assertEqual(selected(bank),{'dst/a.py':b'a'})
    def test_exact_final_name_with_directory_matcher(self):
        bank=memory();self.assertEqual(copy(bank,'src/*/a.kl'),0);self.assertEqual(selected(bank),{'dst/a.py':b'a'})
    def test_case_insensitive_component_matching(self):
        bank=memory();self.assertEqual(copy(bank,'SRC/CELL?/*.KL'),0);self.assertEqual(selected(bank),{'dst/a.py':b'a','dst/b.py':b'b'})
    def test_literal_parent_pattern_keeps_old_nonrecursive_scope(self):
        bank=memory();self.assertEqual(copy(bank,'src/*.kl'),0);self.assertEqual(selected(bank),{'dst/root.py':b'r'})
    def test_star_component_never_consumes_slash(self):
        bank=memory();self.assertEqual(copy(bank,'src/cell*/*.kl'),0);self.assertNotIn('dst/c.py',bank.files)
    def test_double_star_final_filename_is_not_a_recursive_directory(self):
        bank=memory();self.assertEqual(delete(bank,'src/*/**'),0);self.assertIn('src/cell1/deep/c.kl',bank.files);self.assertIn('src/root.kl',bank.files);self.assertNotIn('src/cell1/a.kl',bank.files)
    def test_recursive_delete_leaves_nonmatches_and_other_roots(self):
        bank=memory();self.assertEqual(delete(bank),0);self.assertEqual(bank.snapshot(),{'src/cell1/a.txt':b't','else/other.kl':b'o'})
    def test_recursive_delete_accepts_extensionless_files(self):
        bank=memory({'src/a/plain':b'p','src/a/deep/other':b'o'});self.assertEqual(delete(bank,'src/**/plain'),0);self.assertEqual(bank.snapshot(),{'src/a/deep/other':b'o'})
    def test_recursive_rename_moves_selected_names(self):
        bank=memory();self.assertEqual(rename(bank),0);self.assertEqual(selected(bank),MATCHES);self.assertNotIn('src/root.kl',bank.files)
    def test_rename_retains_payload_identity(self):
        bank=memory();old=bank.files['src/cell1/a.kl'];rename(bank);self.assertIs(bank.files['dst/a.py'],old)
    def test_copy_retains_source_bytes_and_dictionary_identity(self):
        bank=memory();mapping=bank.files;old=bank.files['src/cell1/a.kl'];copy(bank);self.assertIs(bank.files,mapping);self.assertIs(bank.files['src/cell1/a.kl'],old)
    def test_source_no_match_preserves_bank(self):
        bank=memory();before=bank.snapshot();self.assertEqual(copy(bank,'src/*/missing*.kl'),1);self.assertEqual(bank.snapshot(),before)
    def test_standalone_destination_star_keeps_source_names(self):
        bank=memory();self.assertEqual(copy(bank,target='dst/*'),0);self.assertIn('dst/b.KL',bank.files);other=memory();self.assertEqual(rename(other,target='dst/*'),0);self.assertIn('dst/b.KL',other.files)
    def test_full_stem_destination_template(self):
        bank=memory({'src/cell1/part.rev.KL':b'p'});self.assertEqual(copy(bank,target='dst/new_*.bak'),0);self.assertEqual(selected(bank),{'dst/new_part.rev.bak':b'p'})
    def test_basenames_with_literal_brackets_remain_data(self):
        bank=memory({'src/cell1/a[1].kl':b'p'});self.assertEqual(copy(bank),0);self.assertIn('dst/a[1].py',bank.files)
    def test_unqualified_root_glob_does_not_discover_logical_devices(self):
        bank=memory({'a.kl':b'a','sub/b.kl':b'b','RD:sub/c.kl':b'c'});self.assertEqual(copy(bank,'**/*.kl'),0);self.assertEqual(selected(bank),{'dst/a.py':b'a','dst/b.py':b'b'})
    def test_fixed_device_scope_is_retained(self):
        bank=memory({'RD:src/a.kl':b'a','RD:src/deep/b.kl':b'b','FR:src/c.kl':b'c'});self.assertEqual(copy(bank,'rd:src/**/*.KL'),0);self.assertEqual(selected(bank),{'dst/a.py':b'a','dst/b.py':b'b'})
    def test_first_component_glob_after_device_prefix(self):
        bank=memory({'RD:cell1/a.kl':b'a','RD:cell2/b.kl':b'b','FR:cell3/c.kl':b'c'});self.assertEqual(copy(bank,'RD:*/*.kl'),0);self.assertEqual(selected(bank),{'dst/a.py':b'a','dst/b.py':b'b'})


class DirectoryGlobPreflightTests(unittest.TestCase):
    def test_flattened_duplicate_basenames_block_complete_copy(self):
        bank=memory({'src/one/a.kl':b'1','src/two/a.kl':b'2'});before=bank.snapshot();self.assertEqual(copy(bank),2);self.assertEqual(bank.snapshot(),before)
    def test_flattened_duplicate_basenames_block_complete_rename(self):
        bank=memory({'src/one/a.kl':b'1','src/two/a.kl':b'2'});before=bank.snapshot();self.assertEqual(rename(bank),2);self.assertEqual(bank.snapshot(),before)
    def test_late_existing_destination_blocks_earlier_copies(self):
        bank=memory();bank.files['dst/root.py']=bytearray(b'old');before=bank.snapshot();self.assertEqual(copy(bank),2);self.assertEqual(bank.snapshot(),before)
    def test_overwrite_reuses_existing_spelling(self):
        bank=memory();bank.files['DST/A.PY']=bytearray(b'old');self.assertEqual(copy(bank,overwrite=True),0);self.assertEqual(bank.files['DST/A.PY'],b'a');self.assertNotIn('dst/a.py',bank.files)
    def test_ambiguous_case_sources_block_delete(self):
        bank=memory({'src/a/one.kl':b'a','SRC/A/ONE.KL':b'b'});before=bank.snapshot();self.assertEqual(delete(bank),2);self.assertEqual(bank.snapshot(),before)
    def test_ambiguous_destination_aliases_block_overwrite(self):
        bank=memory();bank.files.update({'dst/a.py':bytearray(b'1'),'DST/A.PY':bytearray(b'2')});before=bank.snapshot();self.assertEqual(copy(bank,overwrite=True),2);self.assertEqual(bank.snapshot(),before)
    def test_constant_destination_many_matches_is_rejected(self):
        bank=memory();before=bank.snapshot();self.assertEqual(copy(bank,target='dst/one.py'),2);self.assertEqual(bank.snapshot(),before)
    def test_open_deep_source_prevents_complete_copy(self):
        bank=memory();handle=rt.FileHandle();bank.open(handle,'RO','src/cell1/deep/c.kl');before=bank.snapshot();self.assertEqual(copy(bank),3);self.assertEqual(bank.snapshot(),before);bank.close(handle)
    def test_open_destination_prevents_complete_rename(self):
        bank=memory();handle=rt.FileHandle();bank.open(handle,'WO','dst/root.py');before=bank.snapshot();self.assertEqual(rename(bank),3);self.assertEqual(bank.snapshot(),before);bank.close(handle)
    def test_scan_limit_prevents_any_publication(self):
        bank=memory();before=bank.snapshot()
        with patch.object(fileops,'WILDCARD_FILE_LIMIT',3),self.assertRaises(rt.KarelRuntimeError):copy(bank)
        self.assertEqual(bank.snapshot(),before)
    def test_copy_byte_limit_prevents_any_publication(self):
        bank=memory();before=bank.snapshot()
        with patch.object(fileops,'WILDCARD_COPY_BYTES',2),self.assertRaises(rt.KarelRuntimeError):copy(bank)
        self.assertEqual(bank.snapshot(),before)
    def test_budget_failure_prevents_any_publication(self):
        bank=memory();before=bank.snapshot()
        with self.assertRaises(rt.KarelRuntimeError):copy(bank,max_steps=2)
        self.assertEqual(bank.snapshot(),before)
    def test_new_deep_source_during_preflight_is_retained_without_publication(self):
        bank=memory();original=bank._check;fired=[]
        def check(name,data):
            if name.startswith('dst/') and not fired:fired.append(1);bank.files['src/new/fresh.kl']=bytearray(b'fresh')
            return original(name,data)
        with patch.object(bank,'_check',side_effect=check),self.assertRaisesRegex(rt.KarelRuntimeError,'changed'):copy(bank)
        self.assertEqual(bank.files['src/new/fresh.kl'],b'fresh');self.assertEqual(selected(bank),{})
    def test_traversal_remains_invalid_after_globstar(self):
        bank=memory()
        with self.assertRaises(rt.KarelRuntimeError):copy(bank,'src/**/../*.kl')
    def test_bracket_directory_pattern_remains_invalid(self):
        bank=memory()
        with self.assertRaises(rt.KarelRuntimeError):copy(bank,'src/[ab]/*.kl')
    def test_directory_destination_pattern_remains_invalid(self):
        bank=memory()
        with self.assertRaises(rt.KarelRuntimeError):copy(bank,target='dst/*/*.py')
    def test_absolute_path_remains_invalid(self):
        bank=memory()
        with self.assertRaises(rt.KarelRuntimeError):delete(bank,'/src/**/*.kl')
    def test_socket_and_daq_endpoints_are_not_discovered(self):
        bank=memory()
        with self.assertRaises(rt.KarelRuntimeError):copy(bank,'S1:**/*.kl')


class DirectoryGlobDeviceTests(unittest.TestCase):
    def test_device_recursive_copy(self):
        bank=devices();self.assertEqual(copy(bank,'RD:src/**/*.kl','FR:dst/*.py'),0);self.assertEqual({k:v for k,v in bank.snapshot().items() if k.startswith('FR:')},{'FR:'+k:v for k,v in MATCHES.items()})
    def test_cross_volume_recursive_rename(self):
        bank=devices();self.assertEqual(rename(bank,'RD:src/**/*.kl','FR:dst/*.py'),0);self.assertNotIn('RD:src/root.kl',bank.files);self.assertIn('FR:dst/root.py',bank.files)
    def test_retaining_delete_accounts_for_selected_payloads(self):
        bank=devices(initial={'FR:'+n:v for n,v in DATA.items()},retain=True);self.assertEqual(delete(bank,'FR:src/**/*.kl'),0);self.assertEqual(bank._volumes['FR']['garbage'],4)
    def test_destination_complete_capacity_failure_is_atomic(self):
        bank=devices(capacity=2);before=deepcopy(bank.to_config())
        with self.assertRaises(rt.KarelRuntimeError):copy(bank,'RD:src/**/*.kl','FR:dst/*.py')
        self.assertEqual(bank.to_config(),before)
    def test_readonly_destination_blocks_recursive_copy(self):
        bank=devices(read_only=True);before=deepcopy(bank.to_config())
        with self.assertRaises(rt.KarelRuntimeError):copy(bank,'RD:src/**/*.kl','FR:dst/*.py')
        self.assertEqual(bank.to_config(),before)
    def test_unmounted_source_is_rejected(self):
        bank=devices();bank._volumes['RD']['mounted']=False
        with self.assertRaises(rt.KarelRuntimeError):copy(bank,'RD:src/**/*.kl','FR:dst/*.py')
    def test_root_glob_does_not_cross_volume_boundaries(self):
        bank=devices(initial={'RD:a.kl':b'a','RD:x/b.kl':b'b','FR:c.kl':b'c'});self.assertEqual(copy(bank,'RD:**/*.kl','FR:dst/*.py'),0);self.assertIn('FR:c.kl',bank.files);self.assertNotIn('FR:dst/c.py',bank.files)


class DirectoryGlobRootedTests(unittest.TestCase):
    def test_rooted_recursive_copy(self):
        with directory() as (root,bank):self.assertEqual(copy(bank),0);self.assertEqual({k:v for k,v in disk(root).items() if k.startswith('dst/')},MATCHES)

    def test_rooted_scan_stops_consuming_directory_at_limit(self):
        data={f'src/ignored{index}.txt':b'data' for index in range(8)}
        for pattern in ('src/*.kl',PATTERN):
            with self.subTest(pattern=pattern),directory(data) as (root,bank):
                original=os.scandir
                visited=[]
                @contextmanager
                def scan(folder):
                    with original(folder) as entries:
                        def track():
                            for entry in entries:
                                visited.append(entry.name)
                                yield entry
                        yield track()
                with patch.object(os,'scandir',scan),patch.object(fileops,'WILDCARD_FILE_LIMIT',2):
                    with self.assertRaisesRegex(rt.KarelRuntimeError,'scan exceeds'):
                        copy(bank,pattern)
                self.assertEqual(len(visited),3)
                self.assertEqual(disk(root),data)

    def test_rooted_single_level_matching_excludes_deeper_file(self):
        with directory() as (root,bank):self.assertEqual(copy(bank,'src/*/*.kl'),0);self.assertEqual({k:v for k,v in disk(root).items() if k.startswith('dst/')},{'dst/a.py':b'a','dst/b.py':b'b'})
    def test_rooted_delete_keeps_directories(self):
        with directory() as (root,bank):self.assertEqual(delete(bank),0);self.assertTrue((root/'src/cell1/deep').is_dir());self.assertEqual(disk(root),{'src/cell1/a.txt':b't','else/other.kl':b'o'})
    def test_rooted_recursive_rename(self):
        with directory() as (root,bank):self.assertEqual(rename(bank),0);self.assertEqual({k:v for k,v in disk(root).items() if k.startswith('dst/')},MATCHES);self.assertFalse((root/'src/root.kl').exists())
    def test_rooted_device_mapping_uses_literal_mount_root(self):
        with directory(devices={'RD':'src','FR':'dst'}) as (root,bank):self.assertEqual(copy(bank,'RD:**/*.kl','FR:*.py'),0);self.assertTrue((root/'dst/c.py').is_file())
    def test_rooted_missing_destination_parent_is_not_created(self):
        with directory() as (root,bank):
            before=disk(root)
            with self.assertRaises(rt.KarelRuntimeError):copy(bank,target='missing/*.py')
            self.assertEqual(disk(root),before);self.assertFalse((root/'missing').exists())
    def test_rooted_source_no_match_has_no_effect(self):
        with directory() as (root,bank):before=disk(root);self.assertEqual(copy(bank,'missing/**/*.kl'),1);self.assertEqual(disk(root),before)
    def test_rooted_complete_collision_check(self):
        with directory() as (root,bank):
            (root/'dst/root.py').write_bytes(b'old');before=disk(root);self.assertEqual(copy(bank),2);self.assertEqual(disk(root),before)
    def test_rooted_open_deep_file_blocks_delete(self):
        with directory() as (root,bank):
            handle=rt.FileHandle();bank.open(handle,'RO','src/cell1/deep/c.kl');before=disk(root);self.assertEqual(delete(bank),3);self.assertEqual(disk(root),before);bank.close(handle)
    def test_encountered_link_fails_before_publication(self):
        with directory() as (root,bank):
            (root/'src/link').mkdir();before=disk(root);original=Path.is_symlink
            with patch.object(Path,'is_symlink',lambda p:p.name=='link' or original(p)),self.assertRaises(rt.KarelRuntimeError):copy(bank)
            self.assertEqual(disk(root),before)
    def test_encountered_junction_fails_before_publication(self):
        with directory() as (root,bank):
            (root/'src/junction').mkdir();before=disk(root)
            with patch.object(Path,'is_junction',lambda p:p.name=='junction',create=True),self.assertRaises(rt.KarelRuntimeError):copy(bank)
            self.assertEqual(disk(root),before)
    def test_links_outside_literal_source_root_are_not_scanned(self):
        with directory() as (root,bank):
            original=Path.is_symlink
            with patch.object(Path,'is_symlink',lambda p:p.name=='else' or original(p)):self.assertEqual(copy(bank),0)
            self.assertTrue((root/'else/other.kl').is_file())
    def test_rooted_scan_limit_counts_directories_and_files(self):
        with directory() as (root,bank):
            before=disk(root)
            with patch.object(fileops,'WILDCARD_FILE_LIMIT',4),self.assertRaises(rt.KarelRuntimeError):copy(bank)
            self.assertEqual(disk(root),before)
    def test_new_deep_file_during_preflight_prevents_publication(self):
        with directory() as (root,bank):
            original=bank.read_named;fired=[]
            def read(name):
                result=original(name)
                if not fired:fired.append(1);(root/'src/cell1/deep/fresh.kl').write_bytes(b'fresh')
                return result
            with patch.object(bank,'read_named',side_effect=read),self.assertRaisesRegex(rt.KarelRuntimeError,'changed'):copy(bank)
            self.assertFalse((root/'dst/a.py').exists());self.assertEqual((root/'src/cell1/deep/fresh.kl').read_bytes(),b'fresh')
    def test_stale_cached_deep_file_is_not_selected(self):
        with directory() as (root,bank):bank.files['src/deep/ghost.kl']=bytearray(b'cached');self.assertEqual(copy(bank),0);self.assertFalse((root/'dst/ghost.py').exists())


class DirectoryGlobPipeAndLinkTests(unittest.TestCase):
    def test_recursive_copy_into_preconfigured_pipe_targets(self):
        ctx=rt.ExecutionContext(files=memory(),file_pipes=pipes({'A.NEW':b'','B.NEW':b'','C.NEW':b'','ROOT.NEW':b''}));self.assertEqual(copy(ctx.files,target='PIP:*.NEW',ctx=ctx,overwrite=True),0);self.assertEqual(ctx.file_pipes.snapshot()['PIP:C.NEW'],b'c')
    def test_recursive_rename_into_preconfigured_pipe_targets(self):
        ctx=rt.ExecutionContext(files=memory(),file_pipes=pipes({'A.NEW':b'','B.NEW':b'','C.NEW':b'','ROOT.NEW':b''}));self.assertEqual(rename(ctx.files,target='PIP:*.NEW',ctx=ctx),0);self.assertNotIn('src/cell1/deep/c.kl',ctx.files.files);self.assertEqual(ctx.file_pipes.snapshot()['PIP:C.NEW'],b'c')
    def test_missing_reserved_pipe_target_blocks_entire_batch(self):
        ctx=rt.ExecutionContext(files=memory(),file_pipes=pipes({'A.NEW':b''}));before=ctx.files.snapshot();self.assertEqual(rename(ctx.files,target='PIP:*.NEW',ctx=ctx),1);self.assertEqual(ctx.files.snapshot(),before)
    def test_pipe_sources_do_not_gain_directory_syntax(self):
        ctx=rt.ExecutionContext(files=memory(),file_pipes=pipes())
        with self.assertRaises(rt.KarelRuntimeError):copy(ctx.files,'PIP:**/*.NEW',ctx=ctx)
    def test_linked_calls_use_shared_explicit_file_bank(self):
        project=translate_project({'main':'PROGRAM MAIN ROUTINE work FROM LIB BEGIN work END MAIN','lib':"PROGRAM LIB VAR s:INTEGER ROUTINE work BEGIN COPY_FILE('src/**/*.kl','dst/*.py',FALSE,FALSE,s) END work BEGIN END LIB"}).instantiate(context=rt.ExecutionContext(files=memory()));project.run('MAIN');self.assertEqual(selected(project.context.files),MATCHES)
    def test_saved_backend_values_replay_without_glob_objects(self):
        ctx=rt.ExecutionContext(files=memory());self.assertEqual(copy(ctx.files,ctx=ctx),0);config=ctx.to_config();self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)


class DirectoryGlobAdditionalTests(unittest.TestCase):
    def test_copy_into_existing_empty_pipes_still_needs_overwrite(self):
        ctx=rt.ExecutionContext(files=memory(),file_pipes=pipes({'A.NEW':b'','B.NEW':b'','C.NEW':b'','ROOT.NEW':b''}));before=ctx.file_pipes.snapshot();self.assertEqual(copy(ctx.files,target='PIP:*.NEW',ctx=ctx),2);self.assertEqual(ctx.file_pipes.snapshot(),before)
    def test_globstar_zero_levels_with_fixed_directory_suffix(self):
        bank=memory({'src/deep/a.kl':b'a','src/cell/deep/b.kl':b'b','src/deep/sub/c.kl':b'c'});self.assertEqual(copy(bank,'src/**/deep/*.kl'),0);self.assertEqual(selected(bank),{'dst/a.py':b'a','dst/b.py':b'b'})
    def test_star_directory_and_question_basename_compose(self):
        bank=memory({'src/cell1/a1.kl':b'a','src/cell1/a12.kl':b'b','src/cell1/deep/a2.kl':b'c'});self.assertEqual(copy(bank,'src/*/a?.kl'),0);self.assertEqual(selected(bank),{'dst/a1.py':b'a'})
    def test_delete_byte_limit_does_not_read_matched_payloads(self):
        bank=memory()
        with patch.object(bank,'read_named',side_effect=AssertionError('delete read bytes')),patch.object(fileops,'WILDCARD_COPY_BYTES',0):self.assertEqual(delete(bank),0)
    def test_directory_glob_does_not_create_a_literal_star_folder(self):
        with directory() as (root,bank):self.assertEqual(copy(bank),0);self.assertFalse((root/'src/**').exists());self.assertFalse((root/'dst/*').exists())
    def test_nested_target_directory_must_be_supplied(self):
        with directory() as (root,bank):
            (root/'dst/stage').mkdir();self.assertEqual(copy(bank,target='dst/stage/*.py'),0);self.assertEqual((root/'dst/stage/c.py').read_bytes(),b'c')
    def test_readonly_source_volume_still_permits_snapshot_copy(self):
        bank=devices();bank._volumes['RD']['read_only']=True;self.assertEqual(copy(bank,'RD:src/**/*.kl','FR:dst/*.py'),0)
    def test_matching_component_work_charges_the_execution_budget(self):
        bank=memory({'src/a/b/c.kl':b'c'});before=bank.snapshot()
        with self.assertRaises(rt.KarelRuntimeError):copy(bank,'src/**/**/**/c.kl',max_steps=4)
        self.assertEqual(bank.snapshot(),before)
    def test_literal_brackets_in_directory_names_are_data(self):
        bank=memory({'src/cell[1]/a.kl':b'a'});self.assertEqual(copy(bank,'src/*/*.kl'),0);self.assertEqual(selected(bank),{'dst/a.py':b'a'})
    def test_binary_payload_is_copied_without_text_decoding(self):
        bank=memory({'src/one/deep/a.kl':b'\x00\xff\x80'});self.assertEqual(copy(bank),0);self.assertEqual(selected(bank),{'dst/a.py':b'\x00\xff\x80'})
    def test_selected_paths_remain_bounded(self):
        bank=memory();bank.files['src/'+('deep/'*50)+'a.kl']=bytearray(b'a');before=bank.snapshot()
        with self.assertRaises(rt.KarelRuntimeError):copy(bank)
        self.assertEqual(bank.snapshot(),before)
    def test_repeated_globstar_matching_is_bounded_by_components(self):
        pattern='src/'+'**/'*40+'a.kl';bank=memory({'src/one/two/three/a.kl':b'a'});self.assertEqual(copy(bank,pattern),0);self.assertEqual(selected(bank),{'dst/a.py':b'a'})


class DirectoryGlobPolicyTests(unittest.TestCase):
    def policy(self):return compile_program("COPY_FILE('src/**/*.kl','dst/*.py',FALSE,FALSE,s)")[1].report['directory_glob_policy']
    def test_report_covers_procedures_matching_and_scope(self):
        policy=self.policy();self.assertEqual(policy['procedures'],['COPY_FILE','DELETE_FILE','RENAME_FILE']);self.assertIn('zero or more components',policy['matching']);self.assertIn('literal prefix fixes root/device',policy['source'])
    def test_report_retains_limits_and_publication_boundary(self):
        policy=self.policy();self.assertIn('32767',policy['bounds']);self.assertIn('matching components',policy['bounds']);self.assertIn('no host filesystem transaction',policy['publication']);self.assertIn('Plain PIP sources stay flat',policy['pipes'])
    def test_report_links_guide_and_explicit_offline_scope(self):
        policy=self.policy();self.assertEqual(policy['guide'],'docs/directory-globs.md');self.assertFalse(policy['controller_validated']);self.assertIn('MOVE_FILE and FILE_LIST',policy['boundary'])


class DirectoryGlobHardlinkTests(unittest.TestCase):
    def test_older_pathlib_reparse_attribute_fallback_rejects_junction(self):
        path=SimpleNamespace(is_symlink=lambda:False,lstat=lambda:SimpleNamespace(st_file_attributes=0x400))
        self.assertTrue(fileops._wildcard_link(path))
    def test_older_pathlib_fallback_accepts_ordinary_files(self):
        for attributes in (SimpleNamespace(st_file_attributes=0),SimpleNamespace()):
            with self.subTest(attributes=attributes):self.assertFalse(fileops._wildcard_link(SimpleNamespace(is_symlink=lambda:False,lstat=lambda:attributes)))
    def test_deep_hardlinked_source_aliases_reject_complete_batch(self):
        with directory() as (root,bank):
            os.link(root/'src/cell1/a.kl',root/'src/cell2/alias.kl');before=disk(root);self.assertEqual(copy(bank),2);self.assertEqual(delete(bank),2);self.assertEqual(disk(root),before)


if __name__=='__main__':unittest.main()
