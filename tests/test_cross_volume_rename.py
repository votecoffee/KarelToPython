"""Whole-batch virtual cross-volume rename quotas and retention accounting."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from tests.test_extended_services import compile_program
from tests.test_wildcard_rename import rename


DEFAULT_FILES={'FR:src/a.kl':b'aaa','FR:src/b.kl':b'\0b',
    'FR:elsewhere.txt':b'keep','RD:outside/pre.dat':b'x'}


def bank(initial=None,*,fr=None,rd=None):
    return rt.DeviceFiles({'FR:':{'capacity':16,'garbage':3,'retain_deleted':True,**(fr or {})},
        'RD:':{'capacity':16,'garbage':2,'retain_deleted':False,**(rd or {})},
        'BK:':{'capacity':1000,'garbage':0,'retain_deleted':True}},
        DEFAULT_FILES if initial is None else initial)


def move(files,source='FR:src/*.kl',target='RD:dst/*.py',**options):
    return rename(files,source,target,**options)


class CrossVolumeRenameAccountingTests(unittest.TestCase):
    def test_moves_original_objects_and_publishes_exact_garbage(self):
        files=bank();mapping=files.files;volumes=files._volumes;rows=dict(volumes);payloads=dict(mapping)
        self.assertEqual(move(files),0)
        self.assertIs(files.files,mapping);self.assertIs(files._volumes,volumes)
        for volume,row in rows.items():self.assertIs(files._volumes[volume],row)
        self.assertIs(files.files['RD:dst/a.py'],payloads['FR:src/a.kl'])
        self.assertIs(files.files['RD:dst/b.py'],payloads['FR:src/b.kl'])
        self.assertIs(files.files['FR:elsewhere.txt'],payloads['FR:elsewhere.txt'])
        self.assertEqual(files.snapshot(),{'RD:dst/a.py':b'aaa','RD:dst/b.py':b'\0b',
            'FR:elsewhere.txt':b'keep','RD:outside/pre.dat':b'x'})
        self.assertEqual((files._volumes['FR']['garbage'],files.used('FR')),(8,12))
        self.assertEqual((files._volumes['RD']['garbage'],files.used('RD')),(2,8))

    def test_destination_exact_capacity_fit_accepts_whole_batch(self):
        files=bank(rd={'capacity':8});self.assertEqual(move(files),0)
        self.assertEqual(files.used('RD'),8);self.assertEqual(files.space('RD:')[1]['free'],0)

    def test_later_source_would_overfill_destination_so_no_files_or_garbage_move(self):
        files=bank(rd={'capacity':7});before=deepcopy(files.to_config())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'complete wildcard rename batch'):move(files)
        self.assertEqual(files.to_config(),before)

    def test_destination_garbage_and_unrelated_parent_files_count_against_capacity(self):
        initial={**DEFAULT_FILES,'RD:another/large.dat':b'1234'}
        files=bank(initial,rd={'capacity':11});before=deepcopy(files.to_config())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):move(files)
        self.assertEqual(files.to_config(),before)

    def test_unrelated_volume_free_bytes_cannot_subsidize_target(self):
        files=bank(rd={'capacity':7});self.assertEqual(files.space('BK:')[1]['free'],1000)
        before=deepcopy(files.to_config())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):move(files)
        self.assertEqual(files.to_config(),before)

    def test_retaining_source_at_capacity_does_not_need_extra_source_space(self):
        files=bank(fr={'capacity':12},rd={'capacity':8})
        self.assertEqual(files.space('FR:')[1]['free'],0);self.assertEqual(move(files),0)
        self.assertEqual((files.used('FR'),files._volumes['FR']['garbage']),(12,8))

    def test_nonretaining_source_reclaims_live_bytes_without_new_garbage(self):
        files=bank(fr={'retain_deleted':False});self.assertEqual(move(files),0)
        self.assertEqual((files.used('FR'),files._volumes['FR']['garbage']),(7,3))

    def test_destination_retention_does_not_charge_old_or_new_bytes_as_garbage(self):
        files=bank(rd={'retain_deleted':True});self.assertEqual(move(files),0)
        self.assertEqual((files.used('RD'),files._volumes['RD']['garbage']),(8,2))

    def test_reverse_direction_uses_actual_source_retention_policy(self):
        files=bank();self.assertEqual(move(files,'rd:outside/*.DAT','FR:saved/*.new'),0)
        self.assertEqual(files.files['FR:saved/pre.new'],b'x')
        self.assertEqual((files.used('RD'),files._volumes['RD']['garbage']),(2,2))
        self.assertEqual((files.used('FR'),files._volumes['FR']['garbage']),(13,3))

    def test_zero_length_files_move_without_inventing_garbage(self):
        files=bank({'FR:src/a.kl':b'','FR:src/b.kl':b''},fr={'capacity':3},rd={'capacity':2})
        self.assertEqual(move(files),0);self.assertEqual(files.snapshot(),{'RD:dst/a.py':b'','RD:dst/b.py':b''})
        self.assertEqual((files.used('FR'),files.used('RD')),(3,2))

    def test_rename_requires_no_per_file_reservation_or_copy_quota(self):
        files=bank()
        with patch.object(files,'reserve',side_effect=AssertionError('no transient reserve')),patch.object(files,'rename',side_effect=AssertionError('no incremental backend rename')),patch('karel2py.fileops.WILDCARD_COPY_BYTES',0):
            self.assertEqual(move(files),0)

    def test_full_global_file_count_needs_no_temporary_slot(self):
        initial={f'BK:unused/{index}.dat':b'' for index in range(32765)}
        initial.update({'FR:src/a.kl':b'a','FR:src/b.kl':b'b'})
        files=bank(initial,rd={'capacity':4});self.assertEqual(len(files.files),32767)
        self.assertEqual(move(files,max_steps=150000),0);self.assertEqual(len(files.files),32767)
        self.assertEqual((files._volumes['FR']['garbage'],files.used('RD')),(5,4))

    def test_same_volume_full_capacity_still_avoids_garbage_and_growth(self):
        files=bank(fr={'capacity':12});before=deepcopy(files._volumes);count=len(files.files)
        self.assertEqual(move(files,target='fr:saved/*.py'),0)
        self.assertEqual(files._volumes,before);self.assertEqual(files.used('FR'),12);self.assertEqual(len(files.files),count)

    def test_exact_cross_volume_retention_semantics_remain_consistent(self):
        batch=bank();exact=bank()
        self.assertEqual(move(batch),0)
        self.assertEqual(move(exact,'FR:src/a.kl','RD:dst/a.py'),0)
        self.assertEqual(move(exact,'FR:src/b.kl','RD:dst/b.py'),0)
        self.assertEqual(batch.to_config(),exact.to_config())


class CrossVolumeRenameGuardTests(unittest.TestCase):
    def test_source_and_target_must_be_mounted_and_writable(self):
        for volume in ('FR','RD'):
            for field in ('mounted','read_only'):
                with self.subTest(volume=volume,field=field):
                    options={field:field=='read_only'};files=bank(**{volume.lower():options});before=deepcopy(files.to_config())
                    with self.assertRaisesRegex(rt.KarelRuntimeError,'mounted|read-only'):move(files)
                    self.assertEqual(files.to_config(),before)

    def test_unknown_volume_and_invalid_paths_fail_before_any_publication(self):
        for source,target in [('FR:src/*.kl','UNKNOWN:dst/*.py'),('UNKNOWN:*.kl','RD:dst/*.py'),
                ('FR:src/*.kl','RD:../*.py'),('FR:src/*/*.kl','RD:dst/*.py'),('FR:src/*.kl','RD:dst/CON.*')]:
            with self.subTest(source=source,target=target):
                files=bank();before=deepcopy(files.to_config())
                with self.assertRaises(rt.KarelRuntimeError):move(files,source,target)
                self.assertEqual(files.to_config(),before)

    def test_existing_later_destination_or_case_alias_blocks_every_move(self):
        files=bank({**DEFAULT_FILES,'RD:dst/B.PY':b'old'});before=deepcopy(files.to_config())
        self.assertEqual(move(files),2);self.assertEqual(files.to_config(),before)

    def test_case_aliased_sources_or_targets_are_status_two(self):
        for extra in ({'FR:src/A.KL':b'x'},{'RD:dst/a.py':b'x','RD:dst/A.PY':b'y'}):
            with self.subTest(extra=extra):
                files=bank({**DEFAULT_FILES,**extra});before=deepcopy(files.to_config())
                self.assertEqual(move(files),2);self.assertEqual(files.to_config(),before)

    def test_duplicate_generated_targets_preserve_source_garbage_and_bytes(self):
        files=bank();before=deepcopy(files.to_config())
        self.assertEqual(move(files,target='RD:dst/one.py'),2);self.assertEqual(files.to_config(),before)

    def test_busy_source_and_target_are_status_three_with_unchanged_cursor(self):
        for name in ('FR:src/b.kl','RD:dst/B.PY'):
            with self.subTest(name=name):
                initial={**DEFAULT_FILES,**({name:b'old'} if name.startswith('RD') else {})}
                files=bank(initial);handle=rt.FileHandle();files.open(handle,'R',name);handle.position=1
                before=deepcopy(files.to_config());self.assertEqual(move(files),3)
                self.assertEqual(files.to_config(),before);self.assertEqual(handle.position,1);self.assertIs(handle.owner,files)
                files.close(handle)

    def test_unrelated_open_handle_survives_dictionary_publication(self):
        files=bank();handle=rt.FileHandle();files.open(handle,'R','FR:elsewhere.txt');handle.position=2
        data=files.files[handle.name];self.assertEqual(move(files),0)
        self.assertIs(files.files[handle.name],data);self.assertIs(handle.owner,files);self.assertEqual(handle.position,2)
        self.assertEqual(files.read_bytes(handle,2),b'ep');files.close(handle)

    def test_missing_source_returns_one_and_nowait_true_finishes_synchronously(self):
        files=bank();before=deepcopy(files.to_config())
        self.assertEqual(move(files,'FR:src/*.missing'),1);self.assertEqual(files.to_config(),before)
        self.assertEqual(move(files,nowait=True),0);self.assertIn('RD:dst/b.py',files.files)

    def test_cross_volume_case_and_whole_component_templates(self):
        files=bank({'FR:src/part.rev1.KL':b'a','FR:src/partTwo.KL':b'b'})
        self.assertEqual(move(files,'fr:src/part*.kl','rd:dst/backup_*.copy*'),0)
        self.assertEqual(files.snapshot(),{'RD:dst/backup_part.rev1.copyKL':b'a','RD:dst/backup_partTwo.copyKL':b'b'})

    def test_standalone_star_preserves_extensionless_source_name(self):
        files=bank({'FR:src/LOG':b'abc'})
        self.assertEqual(move(files,'fr:src/*','rd:dst/*'),0);self.assertEqual(files.files['RD:dst/LOG'],b'abc')

    def test_budget_failure_during_preflight_preserves_status_files_and_garbage(self):
        files=bank({'FR:src/a.kl':b'a'*40000,'FR:src/b.kl':b'b'*40000},
            fr={'capacity':100000,'garbage':0},rd={'capacity':100000,'garbage':0})
        before=deepcopy(files.to_config());observed=[];original=files._check
        def check(name,data):
            original(name,data)
            if data:observed.append(name)
        program,_=compile_program("s=91 RENAME_FILE('FR:src/*.kl','RD:dst/*.py',FALSE,s)",decl='s:INTEGER',context=rt.ExecutionContext(files=files))
        with patch.object(files,'_check',side_effect=check),self.assertRaises(rt.KarelRuntimeError):program.run(max_steps=20)
        self.assertTrue(observed);self.assertEqual(files.to_config(),before);self.assertEqual(program._state.reference('S').raw(),91)

    def test_final_target_write_guard_detects_policy_change_without_helper_writes(self):
        files=bank();original=files._check;payloads=files.snapshot();garbage={key:row['garbage'] for key,row in files._volumes.items()}
        def check(name,data):
            original(name,data)
            if name=='FR:src/b.kl' and data:files._volumes['RD']['read_only']=True
        with patch.object(files,'_check',side_effect=check),self.assertRaisesRegex(rt.KarelRuntimeError,'read-only'):move(files)
        self.assertEqual(files.snapshot(),payloads);self.assertEqual({key:row['garbage'] for key,row in files._volumes.items()},garbage)
        self.assertTrue(files._volumes['RD']['read_only'])

    def test_current_destination_garbage_is_charged_before_commit(self):
        files=bank(rd={'capacity':8});original=files._check;payloads=files.snapshot()
        def check(name,data):
            original(name,data)
            if name=='FR:src/b.kl' and data:files._volumes['RD']['garbage']=3
        with patch.object(files,'_check',side_effect=check),self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):move(files)
        self.assertEqual(files.snapshot(),payloads);self.assertEqual(files._volumes['FR']['garbage'],3)
        self.assertEqual(files._volumes['RD']['garbage'],3)

    def test_source_byte_change_is_detected_before_garbage_publication(self):
        files=bank();original=files._check
        def check(name,data):
            original(name,data)
            if name=='RD:dst/b.py':files.files['FR:src/a.kl'].extend(b'fresh')
        with patch.object(files,'_check',side_effect=check),self.assertRaisesRegex(rt.KarelRuntimeError,'bytes or metadata'):move(files)
        self.assertEqual(files.files['FR:src/a.kl'],b'aaafresh');self.assertEqual(files._volumes['FR']['garbage'],3)
        self.assertNotIn('RD:dst/a.py',files.files)

    def test_pipe_to_device_and_device_to_pipe_remain_cross_bank_rejections(self):
        files=bank();pipes=rt.FilePipes();pipes.configure('A.KL',False,1,0,'',0);pipes.feed('A.KL',b'a')
        context=rt.ExecutionContext(files=files,file_pipes=pipes);before=deepcopy(files.to_config());pipe_before=deepcopy(pipes.to_config())
        for source,target in [('PIP:*.KL','RD:dst/*.py'),('FR:src/*.kl','PIP:*.PY')]:
            with self.subTest(source=source,target=target):self.assertEqual(move(files,source,target,ctx=context),2)
        self.assertEqual(files.to_config(),before);self.assertEqual(pipes.to_config(),pipe_before)

    def test_closed_bank_json_roundtrip_preserves_names_bytes_and_accounting(self):
        files=bank();context=rt.ExecutionContext(files=files);self.assertEqual(move(files,ctx=context),0)
        saved=json.loads(json.dumps(context.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved);self.assertEqual(restored.files.to_config(),files.to_config())
        self.assertEqual((restored.files.used('FR'),restored.files.used('RD')),(12,8))


if __name__=='__main__':unittest.main()
