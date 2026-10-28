"""Authored Pythonic wildcard rename plans, ownership and publication bounds."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from tests.test_extended_services import compile_program
from tests.test_wildcard_file_operations import invoke


def rename(files,source='src/*.kl',target='dst/*.py',**options):
    return invoke(files,'RENAME_FILE',source,target,**options)


def memory(extra=None):
    return rt.MemoryFiles({'src/a.kl':b'\xff\0a','src/b.kl':b'b','src/other.txt':b'keep',**(extra or {})})


def pipes(values=None,*,limit=32768):
    bank=rt.FilePipes(limit=limit)
    for index,(name,data) in enumerate((values or {'A.DAT':b'a','B.DAT':b'\xff\0b'}).items()):
        assert bank.configure(name,index%2==0,1,index,'FMT',index)==0
        bank.feed(name,data)
    return bank


def pipe_rename(bank,source='PIP:*.DAT',target='PIP:*.NEW',**options):
    return rename(None,source,target,ctx=rt.ExecutionContext(file_pipes=bank),**options)


def directory(root,*,limit=1024):
    root=Path(root);(root/'src').mkdir();(root/'dst').mkdir();(root/'src/deep').mkdir()
    for name,data in {'src/b.kl':b'b','src/a.kl':b'\xff\0a','src/other.txt':b'keep','src/deep/c.kl':b'c'}.items():
        (root/name).write_bytes(data)
    return rt.DirectoryFiles(root,devices={'RD':'src','FR':'dst','ALIAS':'src'},limit=limit)


def disk(root):
    return {p.relative_to(root).as_posix():p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}


class WildcardRenameMemoryTests(unittest.TestCase):
    def test_complete_batch_preserves_dictionary_and_byte_object_identity(self):
        bank=memory();mapping=bank.files;a=bank.files['src/a.kl'];b=bank.files['src/b.kl']
        self.assertEqual(rename(bank),0)
        self.assertIs(bank.files,mapping);self.assertIs(bank.files['dst/a.py'],a);self.assertIs(bank.files['dst/b.py'],b)
        self.assertEqual(bank.snapshot(),{'dst/a.py':b'\xff\0a','dst/b.py':b'b','src/other.txt':b'keep'})

    def test_whole_stem_extension_templates_and_multiple_dots(self):
        bank=rt.MemoryFiles({'src/part.rev1.KL':b'a','src/partTwo.KL':b'b'})
        self.assertEqual(rename(bank,'src/part*.kl','dst/backup_*.copy*'),0)
        self.assertEqual(bank.snapshot(),{'dst/backup_part.rev1.copyKL':b'a','dst/backup_partTwo.copyKL':b'b'})

    def test_standalone_star_preserves_extensionless_names_and_literal_brackets(self):
        bank=rt.MemoryFiles({'src/LOG':b'a','src/a[1].kl':b'b'})
        self.assertEqual(rename(bank,'src/*','saved/*'),0)
        self.assertEqual(bank.snapshot(),{'saved/LOG':b'a','saved/a[1].kl':b'b'})

    def test_exact_source_with_star_target_uses_one_selected_file(self):
        bank=memory();self.assertEqual(rename(bank,'src/a.kl','dst/prefix_*.py'),0)
        self.assertEqual(bank.files['dst/prefix_a.py'],b'\xff\0a');self.assertIn('src/b.kl',bank.files)

    def test_no_match_is_status_one_without_mutation(self):
        bank=memory();before=bank.snapshot()
        self.assertEqual(rename(bank,'src/*.missing'),1);self.assertEqual(bank.snapshot(),before)

    def test_late_existing_target_blocks_every_source(self):
        bank=memory({'dst/B.PY':b'old'});before=bank.snapshot()
        self.assertEqual(rename(bank),2);self.assertEqual(bank.snapshot(),before)

    def test_case_aliased_sources_and_destinations_fail_closed(self):
        for extra in ({'src/A.KL':b'alias'},{'dst/a.py':b'x','dst/A.PY':b'y'}):
            with self.subTest(extra=extra):
                bank=memory(extra);before=bank.snapshot()
                self.assertEqual(rename(bank),2);self.assertEqual(bank.snapshot(),before)

    def test_duplicate_targets_and_source_overlap_are_rejected(self):
        for source,target in [('src/*.kl','dst/same.py'),('src/*.kl','src/*.*'),('src/*.*','src/*.kl')]:
            with self.subTest(source=source,target=target):
                bank=memory();before=bank.snapshot()
                self.assertEqual(rename(bank,source,target),2);self.assertEqual(bank.snapshot(),before)

    def test_extension_collapsing_and_ambiguous_templates_reject_entire_batch(self):
        for target in ('dst/*.py','dst/prefix_*','dst/**.py','dst/*.p*y*'):
            with self.subTest(target=target):
                bank=rt.MemoryFiles({'src/a.kl':b'a','src/a.txt':b'b'});before=bank.snapshot()
                self.assertEqual(rename(bank,'src/*.*',target),2);self.assertEqual(bank.snapshot(),before)

    def test_extensionless_substitution_requires_standalone_star(self):
        bank=rt.MemoryFiles({'src/LOG':b'a'});before=bank.snapshot()
        self.assertEqual(rename(bank,'src/*','dst/*.txt'),2);self.assertEqual(bank.snapshot(),before)

    def test_busy_later_source_and_case_aliased_target_are_status_three(self):
        for name in ('src/b.kl','dst/B.PY'):
            with self.subTest(name=name):
                bank=memory({name:b'old'}) if name.startswith('dst') else memory()
                handle=rt.FileHandle();bank.open(handle,'R',name);handle.position=1;before=bank.snapshot()
                self.assertEqual(rename(bank),3);self.assertEqual(bank.snapshot(),before);self.assertEqual(handle.position,1)
                bank.close(handle)

    def test_nowait_true_is_synchronous(self):
        bank=memory();self.assertEqual(rename(bank,nowait=True),0);self.assertIn('dst/b.py',bank.files)

    def test_budget_failure_preserves_sources_and_status_output(self):
        bank=memory();before=bank.snapshot()
        program,_=compile_program("s=91 RENAME_FILE('src/*.kl','dst/*.py',FALSE,s)",decl='s:INTEGER',context=rt.ExecutionContext(files=bank))
        with self.assertRaises(rt.KarelRuntimeError):program.run(max_steps=4)
        self.assertEqual(bank.snapshot(),before);self.assertEqual(program._state.reference('S').raw(),91)

    def test_rename_does_not_use_copy_snapshot_budget(self):
        bank=memory()
        with patch('karel2py.fileops.WILDCARD_COPY_BYTES',0):self.assertEqual(rename(bank),0)

    def test_budget_failure_while_fingerprinting_preserves_all_payloads(self):
        bank=rt.MemoryFiles({'src/a.kl':b'a'*40000,'src/b.kl':b'b'*40000});before=bank.snapshot();original=bank._check;observed=[]
        def check(name,data):
            original(name,data)
            if data:observed.append(name)
        with patch.object(bank,'_check',side_effect=check),self.assertRaises(rt.KarelRuntimeError):rename(bank,max_steps=20)
        self.assertTrue(observed);self.assertEqual(bank.snapshot(),before)

    def test_preflight_source_bytes_change_is_detected_and_fresh_data_preserved(self):
        bank=memory();original=bank._check
        def check(name,data):
            original(name,data)
            if name=='dst/b.py':bank.files['src/a.kl'].extend(b'fresh')
        with patch.object(bank,'_check',side_effect=check),self.assertRaisesRegex(rt.KarelRuntimeError,'bytes or metadata'):
            rename(bank)
        self.assertEqual(bank.files['src/a.kl'],b'\xff\0afresh');self.assertNotIn('dst/a.py',bank.files)

    def test_preflight_added_source_and_target_are_detected(self):
        for changed,reason in [('src/new.kl','sources changed'),('dst/new.py','destinations changed')]:
            with self.subTest(changed=changed):
                bank=memory();original=bank._check
                def check(name,data):
                    original(name,data)
                    if name=='src/b.kl':bank.files[changed]=bytearray(b'fresh')
                with patch.object(bank,'_check',side_effect=check),self.assertRaisesRegex(rt.KarelRuntimeError,reason):rename(bank)
                self.assertEqual(bank.files[changed],b'fresh');self.assertNotIn('dst/a.py',bank.files)

    def test_invalid_paths_generated_reserved_names_and_socket_routes_raise(self):
        for source,target in [('src/*/*.kl','dst/*.py'),('../*.kl','dst/*.py'),('src/?*.kl','dst/*.py'),
                ('src/*.kl','../*.py'),('src/*.kl','dst/CON.*'),('S1:*','dst/*'),('src/*.kl','C2:*')]:
            with self.subTest(source=source,target=target):
                bank=memory();before=bank.snapshot()
                with self.assertRaises(rt.KarelRuntimeError):rename(bank,source,target)
                self.assertEqual(bank.snapshot(),before)

    def test_scan_limit_fails_before_mutation(self):
        bank=memory();before=bank.snapshot()
        with patch('karel2py.fileops.WILDCARD_FILE_LIMIT',2),self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):rename(bank)
        self.assertEqual(bank.snapshot(),before)

    def test_exact_rename_retains_existing_extensionless_behavior(self):
        bank=rt.MemoryFiles({'plain':b'a'});self.assertEqual(rename(bank,'plain','new'),0)
        self.assertEqual(bank.snapshot(),{'new':b'a'})


class WildcardRenameDeviceTests(unittest.TestCase):
    def bank(self,**volume):
        return rt.DeviceFiles({'FR:':{'capacity':7,'garbage':3,'retain_deleted':True,**volume},'RD:':{'capacity':100}},
            {'FR:a.kl':b'aaa','FR:b.kl':b'b'})

    def test_at_capacity_rename_does_not_reserve_or_charge_garbage(self):
        bank=self.bank();mapping=bank.files;volumes=bank._volumes;row=volumes['FR'];data=bank.files['FR:a.kl']
        with patch.object(bank,'reserve',side_effect=AssertionError('rename must not reserve bytes')):
            self.assertEqual(rename(bank,'fr:*.KL','FR:saved/*.py'),0)
        self.assertIs(bank.files,mapping);self.assertIs(bank._volumes,volumes);self.assertIs(bank._volumes['FR'],row)
        self.assertIs(bank.files['FR:saved/a.py'],data);self.assertEqual((bank.used('FR'),row['garbage']),(7,3))

    def test_cross_volume_wildcard_rejected_but_exact_rename_preserved(self):
        bank=self.bank();before=deepcopy(bank.to_config())
        self.assertEqual(rename(bank,'FR:*.kl','RD:*.py'),2);self.assertEqual(bank.to_config(),before)
        self.assertEqual(rename(bank,'FR:a.kl','RD:a.py'),0);self.assertEqual(bank.files['RD:a.py'],b'aaa')

    def test_readonly_and_unmounted_source_are_errors_without_mutation(self):
        for option in ({'read_only':True},{'mounted':False}):
            with self.subTest(option=option):
                bank=self.bank(**option);before=deepcopy(bank.to_config())
                with self.assertRaises(rt.KarelRuntimeError):rename(bank,'FR:*.kl','FR:*.py')
                self.assertEqual(bank.to_config(),before)

    def test_roundtrip_preserves_renamed_files_and_volume_accounting(self):
        bank=self.bank();self.assertEqual(rename(bank,'FR:*.kl','FR:*.py'),0)
        clone=rt.DeviceFiles.from_config(bank.to_config());self.assertEqual(clone.to_config(),bank.to_config())


class WildcardRenamePipeTests(unittest.TestCase):
    def test_moves_configuration_and_bytes_without_extra_slots_or_capacity(self):
        bank=pipes({f'P{i}.DAT':bytes([i]) for i in range(32)});files=bank.files;configs=bank.pipes
        rows=dict(configs);data=dict(files)
        self.assertEqual(pipe_rename(bank),0);self.assertIs(bank.files,files);self.assertIs(bank.pipes,configs)
        for name,row in rows.items():
            target=name.replace('.DAT','.NEW');self.assertIs(bank.pipes[target],row);self.assertIs(bank.files[target],data[name])
        self.assertEqual(sum(row['sectors']*1024 for row in configs.values()),32768)

    def test_case_and_optional_root_slash_normalize(self):
        bank=pipes();self.assertEqual(pipe_rename(bank,'pip:/*.dat','pip:/saved_*.new'),0)
        self.assertEqual(set(bank.files),{'PIP:SAVED_A.NEW','PIP:SAVED_B.NEW'})

    def test_plain_star_preserves_extensionless_name_only_when_moving_scope_possible(self):
        bank=pipes({'LOG':b'a'});before=deepcopy(bank.to_config())
        # A pipe has one flat scope; preserving the complete name overlaps itself.
        self.assertEqual(pipe_rename(bank,'PIP:*','PIP:*'),2);self.assertEqual(bank.to_config(),before)

    def test_existing_pipe_target_prevents_all_configuration_moves(self):
        bank=pipes({'A.DAT':b'a','B.DAT':b'b','B.NEW':b'old'});before=deepcopy(bank.to_config())
        self.assertEqual(pipe_rename(bank),2);self.assertEqual(bank.to_config(),before)

    def test_busy_pipe_source_or_target_prevents_batch(self):
        for name in ('B.DAT','B.NEW'):
            with self.subTest(name=name):
                bank=pipes({'A.DAT':b'a','B.DAT':b'b','B.NEW':b'old'});handle=rt.FileHandle()
                bank.open_for(None,handle,'R',name);before=(deepcopy(bank.pipes),bank.snapshot())
                self.assertEqual(pipe_rename(bank),3);self.assertEqual((bank.pipes,bank.snapshot()),before);bank.close(handle)

    def test_cross_bank_rename_is_status_two_without_ordinary_bank_discovery(self):
        bank=pipes();before=deepcopy(bank.to_config())
        for source,target in [('PIP:*.DAT','ordinary/*.new'),('ordinary/*.DAT','PIP:*.NEW')]:
            with self.subTest(source=source,target=target):
                context=rt.ExecutionContext(files=rt.MemoryFiles({'ordinary/a.DAT':b'a'}),file_pipes=bank)
                self.assertEqual(rename(context.files,source,target,ctx=context),2);self.assertEqual(bank.to_config(),before)
        self.assertEqual(pipe_rename(bank,target='ordinary/*.new'),2)
        self.assertEqual(rename(None,'ordinary/*.DAT','PIP:*.NEW',ctx=rt.ExecutionContext(file_pipes=bank)),2)

    def test_configuration_identity_change_during_preflight_is_detected(self):
        bank=pipes();original=bank._check
        def check(name,data):
            original(name,data)
            if name=='PIP:B.DAT':bank.pipes['PIP:A.DAT']=dict(bank.pipes['PIP:A.DAT'])
        with patch.object(bank,'_check',side_effect=check),self.assertRaisesRegex(rt.KarelRuntimeError,'bytes or metadata'):pipe_rename(bank)
        self.assertIn('PIP:A.DAT',bank.pipes);self.assertNotIn('PIP:A.NEW',bank.pipes)

    def test_unresolved_pipe_read_registration_fails_closed(self):
        bank=pipes();before=deepcopy(bank.to_config());bank._reads[123]=object()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'READ identity'):pipe_rename(bank)
        bank._reads.clear();self.assertEqual(bank.to_config(),before)

    def test_pipe_roundtrip_retains_metadata_after_rename(self):
        bank=pipes();self.assertEqual(pipe_rename(bank),0)
        self.assertEqual(rt.FilePipes.from_config(bank.to_config()).to_config(),bank.to_config())

    def test_daq_source_pattern_and_generated_target_never_route_plain_bank(self):
        for daq in ('DAQ.DAT','A.NEW'):
            with self.subTest(daq=daq):
                bank=pipes();acquisition=rt.Acquisition();acquisition.register(1,0,1,('INTEGER',),daq,0)
                context=rt.ExecutionContext(file_pipes=bank,acquisition=acquisition);before=deepcopy(bank.to_config())
                with self.assertRaisesRegex(rt.KarelRuntimeError,'DAQ PIP'):
                    rename(None,'PIP:*.DAT','PIP:*.NEW',ctx=context)
                self.assertEqual(bank.to_config(),before)

    def test_unrelated_paused_pipe_read_survives_and_selected_pending_is_busy(self):
        bank=pipes({'WAIT.LOG':b'','A.DAT':b'a','B.DAT':b'b'});context=rt.ExecutionContext(file_pipes=bank)
        program,_=compile_program("SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','PIP:WAIT.LOG') READ f(x)",
            decl='f:FILE x:INTEGER',context=context,sleep=lambda _:setattr(program._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):program.run()
        handle=program._state.values['F'];pending=bank.files['PIP:WAIT.LOG'];requests=dict(bank._reads)
        self.assertEqual(rename(None,'PIP:*.DAT','PIP:*.NEW',ctx=context),0)
        self.assertIs(bank.files['PIP:WAIT.LOG'],pending);self.assertEqual(bank._reads,requests)
        self.assertEqual(rename(None,'PIP:WAIT.*','PIP:*.NEW',ctx=context),3)
        self.assertEqual(handle.position,0);program.stop();bank.close(handle);context.to_config()

    def test_invalid_retained_pipe_capacity_fails_before_any_move(self):
        bank=pipes();bank.files['PIP:B.DAT'].extend(b'x'*1024);before=bank.snapshot()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'retained capacity'):pipe_rename(bank)
        self.assertEqual(bank.snapshot(),before);self.assertNotIn('PIP:A.NEW',bank.pipes)


class WildcardRenameDirectoryTests(unittest.TestCase):
    def test_mapped_parent_paths_and_nonrecursive_selection(self):
        with tempfile.TemporaryDirectory() as root:
            bank=directory(root);mapping=bank.files
            self.assertEqual(rename(bank,'RD:*.KL','FR:backup_*.PY'),0)
            self.assertIs(bank.files,mapping)
            self.assertEqual(disk(root),{'dst/backup_a.PY':b'\xff\0a','dst/backup_b.PY':b'b','src/other.txt':b'keep','src/deep/c.kl':b'c'})

    def test_all_sources_preflight_before_sorted_per_file_publication(self):
        with tempfile.TemporaryDirectory() as root:
            bank=directory(root);original=bank.rename;observed=[]
            def move(source,target):
                observed.append((source,target));return original(source,target)
            with patch.object(bank,'rename',side_effect=move):self.assertEqual(rename(bank),0)
            self.assertEqual(observed,[('src/a.kl','dst/a.py'),('src/b.kl','dst/b.py')])

    def test_late_collision_or_missing_parent_prevents_any_rename(self):
        for target in ('dst/*.py','absent/*.py'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as root:
                bank=directory(root)
                if target.startswith('dst'):(Path(root)/'dst/b.py').write_bytes(b'old')
                before=disk(root)
                if target.startswith('dst'):self.assertEqual(rename(bank,target=target),2)
                else:
                    with self.assertRaisesRegex(rt.KarelRuntimeError,'parent directory'):rename(bank,target=target)
                self.assertEqual(disk(root),before)

    def test_rename_does_not_read_or_limit_already_existing_file_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            bank=directory(root,limit=1)
            with patch.object(bank,'read_named',side_effect=AssertionError('rename must not copy bytes')):
                self.assertEqual(rename(bank),0)
            self.assertEqual((Path(root)/'dst/a.py').read_bytes(),b'\xff\0a')

    def test_open_unflushed_source_and_destination_directory_block_preflight(self):
        with tempfile.TemporaryDirectory() as root:
            bank=directory(root);handle=rt.FileHandle();bank.open(handle,'W','src/new.kl');before=disk(root)
            self.assertEqual(rename(bank),3);self.assertEqual(disk(root),before);bank.close(handle)
            (Path(root)/'dst/b.py').mkdir();before=disk(root)
            self.assertEqual(rename(bank),2);self.assertEqual(disk(root),before);self.assertTrue((Path(root)/'dst/b.py').is_dir())

    def test_cached_payload_moves_without_stale_source_aliases(self):
        with tempfile.TemporaryDirectory() as root:
            bank=directory(root);handle=rt.FileHandle();bank.open(handle,'R','src/a.kl');bank.close(handle)
            data=bank.files['src/a.kl'];bank.files['SRC/A.KL']=bytearray(b'stale')
            self.assertEqual(rename(bank),0);self.assertIs(bank.files['dst/a.py'],data);self.assertNotIn('SRC/A.KL',bank.files)

    def test_hardlinked_source_aliases_and_open_aliases_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            bank=directory(root)
            try:os.link(Path(root)/'src/a.kl',Path(root)/'src/alias.kl')
            except OSError as exc:self.skipTest(str(exc))
            before=disk(root);self.assertEqual(rename(bank),2);self.assertEqual(disk(root),before)
            (Path(root)/'src/alias.kl').unlink();os.link(Path(root)/'src/b.kl',Path(root)/'elsewhere.txt')
            handle=rt.FileHandle();bank.open(handle,'R','elsewhere.txt');before=disk(root)
            self.assertEqual(rename(bank),3);self.assertEqual(disk(root),before);bank.close(handle)

    def test_destination_physical_alias_and_mapped_self_overlap_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            bank=directory(root);before=disk(root)
            self.assertEqual(rename(bank,'RD:*.kl','ALIAS:*.*'),2);self.assertEqual(disk(root),before)
            try:os.link(Path(root)/'src/b.kl',Path(root)/'dst/a.py')
            except OSError as exc:self.skipTest(str(exc))
            before=disk(root);self.assertEqual(rename(bank),2);self.assertEqual(disk(root),before)

    def test_late_host_failure_retains_earlier_atomic_rename(self):
        with tempfile.TemporaryDirectory() as root:
            bank=directory(root);original=bank.rename
            def move(source,target):
                if source=='src/b.kl':raise OSError('injected late host failure')
                return original(source,target)
            with patch.object(bank,'rename',side_effect=move),self.assertRaisesRegex(rt.KarelRuntimeError,'late host failure'):rename(bank)
            self.assertEqual((Path(root)/'dst/a.py').read_bytes(),b'\xff\0a')
            self.assertFalse((Path(root)/'src/a.kl').exists());self.assertTrue((Path(root)/'src/b.kl').exists())
            self.assertFalse((Path(root)/'dst/b.py').exists())

    def test_budget_failure_and_symlink_path_leave_host_data_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            bank=directory(root);before=disk(root)
            with self.assertRaises(rt.KarelRuntimeError):rename(bank,max_steps=4)
            self.assertEqual(disk(root),before)
            try:(Path(root)/'link').symlink_to(Path(root)/'dst',target_is_directory=True)
            except OSError as exc:self.skipTest(str(exc))
            with self.assertRaisesRegex(rt.KarelRuntimeError,'Symlink'):rename(bank,target='link/*.py')
            self.assertEqual(disk(root),before)


if __name__=='__main__':unittest.main()
