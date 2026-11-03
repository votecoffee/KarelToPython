"""Authored cross-bank moves, reserved pipe endpoints and prepared publication."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate_project
from karel2py import fileops
from tests.test_extended_services import compile_program
from tests.test_wildcard_file_operations import statement

SEED={'src/a.kl':b'aaa','src/b.kl':b'\0b','keep.dat':b'keep'}


def pipes(values=None,*,limit=32768,sectors=1):
    bank=rt.FilePipes(limit=limit)
    for index,(name,data) in enumerate(({'A.NEW':b'','B.NEW':b''} if values is None else values).items()):
        assert bank.configure(name,bool(index%2),sectors,index,'DICT',index)==0
        if data:bank.feed(name,data)
    return bank

def context(files=None,bank=None):return rt.ExecutionContext(files=files if files is not None else rt.MemoryFiles(SEED),file_pipes=bank if bank is not None else pipes())
def build(ctx,source='src/*.kl',target='PIP:*.NEW',*,nowait=False,**options):return compile_program('s=77 '+statement('RENAME_FILE',source,target,nowait=nowait),decl='s:INTEGER f:FILE',context=ctx,**options)[0]
def move(ctx,source='src/*.kl',target='PIP:*.NEW',**options):return build(ctx,source,target,**options).run()['S']
def snapshots(ctx):return deepcopy((ctx.files.snapshot(),getattr(ctx.files,'_volumes',None),ctx.file_pipes.snapshot(),ctx.file_pipes.pipes))
def exported():return context(rt.MemoryFiles({'keep.dat':b'keep'}),pipes({'A.NEW':b'aaa','B.NEW':b'\0b'}))
def device(*,capacity=32,garbage=2,retain=True,initial=None,**flags):
    return rt.DeviceFiles({'FR:':dict(capacity=capacity,garbage=garbage,retain_deleted=retain,**flags),'RD:':dict(capacity=64,retain_deleted=False)},SEED_DEVICE if initial is None else initial)
SEED_DEVICE={'FR:src/a.kl':b'aaa','FR:src/b.kl':b'\0b','FR:keep.dat':b'keep'}


def directory(root,*,initial=None,limit=32768):
    root=Path(root);(root/'src').mkdir();(root/'dst').mkdir()
    for name,data in (SEED if initial is None else initial).items():(root/name).write_bytes(data)
    return rt.DirectoryFiles(root,devices={'RD':'src','FR':'dst'},limit=limit)
def disk(root):return {p.relative_to(root).as_posix():p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}


class CrossBankMemoryTests(unittest.TestCase):
    def test_moves_complete_batch_into_reserved_pipes(self):
        ctx=context();self.assertEqual(move(ctx),0);self.assertEqual(ctx.files.snapshot(),{'keep.dat':b'keep'});self.assertEqual(ctx.file_pipes.snapshot(),{'PIP:A.NEW':b'aaa','PIP:B.NEW':b'\0b'})
    def test_exports_complete_pipe_batch(self):
        ctx=exported();self.assertEqual(move(ctx,'PIP:*.NEW','dst/*.dat'),0);self.assertEqual(ctx.files.snapshot(),{'keep.dat':b'keep','dst/A.dat':b'aaa','dst/B.dat':b'\0b'});self.assertEqual(ctx.file_pipes.pipes,{})
    def test_exact_inbound(self):
        ctx=context();self.assertEqual(move(ctx,'src/a.kl','PIP:A.NEW'),0);self.assertNotIn('src/a.kl',ctx.files.files)
    def test_exact_outbound(self):
        ctx=exported();self.assertEqual(move(ctx,'PIP:A.NEW','dst/exact.dat'),0);self.assertEqual(ctx.files.files['dst/exact.dat'],b'aaa')
    def test_exact_extensionless_names(self):
        ctx=context(rt.MemoryFiles({'raw':b'abc'}),pipes({'TARGET':b''}));self.assertEqual(move(ctx,'raw','PIP:TARGET'),0);self.assertEqual(move(ctx,'PIP:TARGET','restored'),0);self.assertEqual(ctx.files.files['restored'],b'abc')
    def test_exact_extensionless_ordinary_source_to_dotted_pipe(self):
        ctx=context(rt.MemoryFiles({'source':b'7'}),pipes({'A.NEW':b''}));buffer=ctx.files.files['source']
        self.assertEqual(move(ctx,'source','PIP:A.NEW'),0);self.assertIs(ctx.file_pipes.files['PIP:A.NEW'],buffer);self.assertNotIn('source',ctx.files.files)
    def test_exact_extensionless_pipe_source_to_dotted_file(self):
        ctx=context(rt.MemoryFiles({'keep':b'k'}),pipes({'BRIDGE':b'7'}));buffer=ctx.file_pipes.files['PIP:BRIDGE']
        self.assertEqual(move(ctx,'PIP:BRIDGE','result.dat'),0);self.assertIs(ctx.files.files['result.dat'],buffer);self.assertFalse(ctx.file_pipes.pipes)
    def test_standalone_star_preserves_extensionless_source(self):
        ctx=context(rt.MemoryFiles({'raw':b'abc'}),pipes({'RAW':b''}));self.assertEqual(move(ctx,'r*','PIP:*'),0);self.assertEqual(ctx.file_pipes.snapshot(),{'PIP:RAW':b'abc'})
    def test_question_source_matchers(self):
        ctx=context();self.assertEqual(move(ctx,'src/?.kl','PIP:*.NEW'),0)
    def test_pipe_case_and_optional_slash(self):
        ctx=context();self.assertEqual(move(ctx,'src/a.kl','pip:/a.new'),0);self.assertEqual(ctx.file_pipes.files['PIP:A.NEW'],b'aaa')
    def test_nowait_true_remains_synchronous(self):
        ctx=context();self.assertEqual(move(ctx,nowait=True),0);self.assertEqual(ctx.file_pipes.files['PIP:B.NEW'],b'\0b')
    def test_full_stem_template(self):
        ctx=context(rt.MemoryFiles({'src/part.one.kl':b'x'}),pipes({'SAVED_PART.ONE.DAT':b''}));self.assertEqual(move(ctx,'src/part*.kl','PIP:saved_*.DAT'),0)
    def test_mapping_identity_is_preserved(self):
        ctx=context();first=ctx.files.files;second=ctx.file_pipes.files;records=ctx.file_pipes.pipes;move(ctx);self.assertIs(ctx.files.files,first);self.assertIs(ctx.file_pipes.files,second);self.assertIs(ctx.file_pipes.pipes,records)
    def test_inbound_mutable_payload_identity_is_preserved(self):
        ctx=context();a=ctx.files.files['src/a.kl'];move(ctx);self.assertIs(ctx.file_pipes.files['PIP:A.NEW'],a)
    def test_outbound_mutable_payload_identity_is_preserved(self):
        ctx=exported();a=ctx.file_pipes.files['PIP:A.NEW'];move(ctx,'PIP:*','dst/*');self.assertIs(ctx.files.files['dst/A.NEW'],a)
    def test_immutable_source_becomes_mutable_pipe_storage(self):
        ctx=context();ctx.files.files['src/a.kl']=b'aaa';move(ctx);self.assertIs(type(ctx.file_pipes.files['PIP:A.NEW']),bytearray);ctx.file_pipes.feed('A.NEW',b'x');self.assertEqual(ctx.file_pipes.files['PIP:A.NEW'],b'aaax')
    def test_destination_configuration_identity_and_fields_retained(self):
        ctx=context();records=dict(ctx.file_pipes.pipes);saved=deepcopy(records);move(ctx)
        for name,row in records.items():self.assertIs(ctx.file_pipes.pipes[name],row);self.assertEqual(row,saved[name])
    def test_export_releases_source_configuration_without_mutating_record(self):
        ctx=exported();record=ctx.file_pipes.pipes['PIP:A.NEW'];saved=dict(record);move(ctx,'PIP:A.NEW','a.dat');self.assertNotIn('PIP:A.NEW',ctx.file_pipes.pipes);self.assertEqual(record,saved)
    def test_unselected_records_and_bytes_retained(self):
        ctx=context(bank=pipes({'A.NEW':b'','B.NEW':b'','OTHER':b'keep'}));other=ctx.file_pipes.files['PIP:OTHER'];move(ctx);self.assertIs(ctx.file_pipes.files['PIP:OTHER'],other)
    def test_empty_payload_moves(self):
        ctx=context(rt.MemoryFiles({'empty.dat':b''}),pipes({'EMPTY.NEW':b''}));self.assertEqual(move(ctx,'*.dat','PIP:*.NEW'),0);self.assertEqual(ctx.files.files,{})
    def test_pipe_can_be_read_after_move(self):
        ctx=context(rt.MemoryFiles({'number':b'7'}),pipes({'NUMBER':b''}));p,_=compile_program("RENAME_FILE('number','PIP:NUMBER',FALSE,s) OPEN FILE f('RO','PIP:NUMBER') READ f(n) CLOSE FILE f",decl='s,n:INTEGER f:FILE',context=ctx);self.assertEqual(p.run()['N'],7)
    def test_outbound_then_inbound_keeps_bytes(self):
        ctx=exported();self.assertEqual(move(ctx,'PIP:A.NEW','saved'),0);ctx.file_pipes.configure('RESTORED',False,1,0,'',0);self.assertEqual(move(ctx,'saved','PIP:RESTORED'),0);self.assertEqual(ctx.file_pipes.files['PIP:RESTORED'],b'aaa')


class CrossBankDeviceTests(unittest.TestCase):
    def test_deleting_retained_device_sources_creates_garbage(self):
        ctx=context(device());self.assertEqual(move(ctx,'FR:src/*.kl','PIP:*.NEW'),0);self.assertEqual((ctx.files._volumes['FR']['garbage'],ctx.files.used('FR')),(7,11))
    def test_nonretaining_device_reclaims_source_bytes(self):
        ctx=context(device(retain=False));self.assertEqual(move(ctx,'FR:src/*.kl','PIP:*.NEW'),0);self.assertEqual((ctx.files._volumes['FR']['garbage'],ctx.files.used('FR')),(2,6))
    def test_exported_pipe_bytes_count_at_destination(self):
        ctx=context(device(initial={'FR:keep.dat':b'keep'}),pipes({'A.NEW':b'aaa','B.NEW':b'\0b'}));self.assertEqual(move(ctx,'PIP:*','FR:dst/*'),0);self.assertEqual((ctx.files._volumes['FR']['garbage'],ctx.files.used('FR')),(2,11))
    def test_exact_capacity_fit(self):
        ctx=context(device(capacity=11,initial={'FR:keep.dat':b'keep'}),pipes({'A.NEW':b'aaa','B.NEW':b'\0b'}));self.assertEqual(move(ctx,'PIP:*','FR:dst/*'),0)
    def test_whole_batch_capacity_failure_changes_neither_bank(self):
        ctx=context(device(capacity=10,initial={'FR:keep.dat':b'keep'}),pipes({'A.NEW':b'aaa','B.NEW':b'\0b'}));before=snapshots(ctx);p=build(ctx,'PIP:*','FR:dst/*')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'complete cross-bank rename batch'):p.run()
        self.assertEqual(snapshots(ctx),before);self.assertEqual(p.snapshot()['S'],77)
    def test_source_at_capacity_needs_no_extra_bytes(self):
        ctx=context(device(capacity=11));self.assertEqual(move(ctx,'FR:src/*.kl','PIP:*.NEW'),0);self.assertEqual(ctx.files.used('FR'),11)
    def test_readonly_source_rejected_without_changes(self):
        ctx=context(device(read_only=True));before=snapshots(ctx)
        with self.assertRaises(rt.KarelRuntimeError):move(ctx,'FR:src/*.kl','PIP:*.NEW')
        self.assertEqual(snapshots(ctx),before)
    def test_readonly_destination_rejected_without_changes(self):
        ctx=context(device(read_only=True,initial={}),pipes({'A.NEW':b'a'}));before=snapshots(ctx)
        with self.assertRaises(rt.KarelRuntimeError):move(ctx,'PIP:*','FR:dst/*')
        self.assertEqual(snapshots(ctx),before)
    def test_unmounted_source_rejected(self):
        ctx=context(device(mounted=False));before=snapshots(ctx)
        with self.assertRaises(rt.KarelRuntimeError):move(ctx,'FR:src/*.kl','PIP:*.NEW')
        self.assertEqual(snapshots(ctx),before)
    def test_unmounted_destination_rejected(self):
        ctx=context(device(mounted=False,initial={}),pipes({'A.NEW':b'a'}));before=snapshots(ctx)
        with self.assertRaises(rt.KarelRuntimeError):move(ctx,'PIP:*','FR:dst/*')
        self.assertEqual(snapshots(ctx),before)
    def test_volume_row_identities_and_unrelated_objects_retained(self):
        ctx=context(device());volumes=ctx.files._volumes;rows=dict(volumes);keep=ctx.files.files['FR:keep.dat'];move(ctx,'FR:src/*.kl','PIP:*.NEW');self.assertIs(ctx.files._volumes,volumes);self.assertIs(ctx.files.files['FR:keep.dat'],keep)
        for name,row in rows.items():self.assertIs(ctx.files._volumes[name],row)
    def test_global_file_count_limit_is_atomic(self):
        ctx=context(device(initial={'FR:one.dat':b'x','RD:two.dat':b'x'}),pipes({'A.NEW':b'a'}));before=snapshots(ctx)
        with patch.object(fileops,'WILDCARD_FILE_LIMIT',2),self.assertRaises(rt.KarelRuntimeError):move(ctx,'PIP:*','FR:dst/*')
        self.assertEqual(snapshots(ctx),before)
    def test_device_json_retains_garbage_and_released_pipe_slots(self):
        ctx=context(device());move(ctx,'FR:src/*.kl','PIP:*.NEW');saved=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_device_file_names_are_canonicalized(self):
        ctx=context(device());self.assertEqual(move(ctx,'fr:src/a.kl','pip:a.new'),0);self.assertNotIn('FR:src/a.kl',ctx.files.files)


class CrossBankDirectoryTests(unittest.TestCase):
    def test_imports_rooted_directory_batch(self):
        with tempfile.TemporaryDirectory() as root:
            ctx=context(directory(root));self.assertEqual(move(ctx),0);self.assertEqual(disk(root),{'keep.dat':b'keep'});self.assertEqual(ctx.file_pipes.files['PIP:A.NEW'],b'aaa')
    def test_exports_rooted_directory_batch(self):
        with tempfile.TemporaryDirectory() as root:
            ctx=context(directory(root,initial={}),pipes({'A.NEW':b'aaa','B.NEW':b'\0b'}));self.assertEqual(move(ctx,'PIP:*','dst/*'),0);self.assertEqual(disk(root),{'dst/A.NEW':b'aaa','dst/B.NEW':b'\0b'})
    def test_explicit_directory_device_mapping(self):
        with tempfile.TemporaryDirectory() as root:
            ctx=context(directory(root));self.assertEqual(move(ctx,'RD:*.kl','PIP:*.NEW'),0)
    def test_existing_later_destination_preserves_all_sources(self):
        with tempfile.TemporaryDirectory() as root:
            files=directory(root,initial={'dst/B.NEW':b'old'});ctx=context(files,pipes({'A.NEW':b'aaa','B.NEW':b'\0b'}));before=disk(root);pipe_before=deepcopy(ctx.file_pipes.to_config());self.assertEqual(move(ctx,'PIP:*','dst/*'),2);self.assertEqual(disk(root),before);self.assertEqual(ctx.file_pipes.to_config(),pipe_before)
    def test_missing_target_parent_rejected_before_pipe_removal(self):
        with tempfile.TemporaryDirectory() as root:
            ctx=context(directory(root,initial={}),pipes({'A.NEW':b'a'}));before=deepcopy(ctx.file_pipes.to_config())
            with self.assertRaises(rt.KarelRuntimeError):move(ctx,'PIP:*','missing/*')
            self.assertEqual(ctx.file_pipes.to_config(),before)
    def test_destination_size_limit_is_preflighted(self):
        with tempfile.TemporaryDirectory() as root:
            ctx=context(directory(root,initial={},limit=2),pipes({'A.NEW':b'a','B.NEW':b'bbb'}));before=deepcopy(ctx.file_pipes.to_config())
            with self.assertRaises(rt.KarelRuntimeError):move(ctx,'PIP:*','dst/*')
            self.assertEqual(disk(root),{});self.assertEqual(ctx.file_pipes.to_config(),before)
    def test_late_host_write_failure_retains_current_source(self):
        from karel2py.storage import atomic_bytes as original
        with tempfile.TemporaryDirectory() as root:
            ctx=context(directory(root,initial={}),pipes({'A.NEW':b'aaa','B.NEW':b'bbb'}));p=build(ctx,'PIP:*','dst/*')
            def write(path,data):
                if path.name=='B.NEW':raise OSError('Authored late write failure')
                return original(path,data)
            with patch('karel2py.storage.atomic_bytes',side_effect=write),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(disk(root),{'dst/A.NEW':b'aaa'});self.assertEqual(ctx.file_pipes.snapshot(),{'PIP:B.NEW':b'bbb'});self.assertEqual(p.snapshot()['S'],77)
    def test_late_host_delete_failure_retains_current_source_and_reservation(self):
        with tempfile.TemporaryDirectory() as root:
            ctx=context(directory(root));original=ctx.files.delete;p=build(ctx)
            def delete(name):
                if name.endswith('b.kl'):raise PermissionError('Authored late delete failure')
                return original(name)
            with patch.object(ctx.files,'delete',side_effect=delete),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(disk(root),{'src/b.kl':b'\0b','keep.dat':b'keep'});self.assertEqual(ctx.file_pipes.snapshot(),{'PIP:A.NEW':b'aaa','PIP:B.NEW':b''});self.assertEqual(p.snapshot()['S'],77)
    def test_open_source_preserves_complete_batch(self):
        with tempfile.TemporaryDirectory() as root:
            ctx=context(directory(root));handle=rt.FileHandle();ctx.files.open(handle,'RO','src/b.kl');before=disk(root)
            try:self.assertEqual(move(ctx),3);self.assertEqual(disk(root),before);self.assertEqual(ctx.file_pipes.snapshot(),{'PIP:A.NEW':b'','PIP:B.NEW':b''})
            finally:ctx.files.close(handle)
    def test_unflushed_target_handle_is_busy(self):
        with tempfile.TemporaryDirectory() as root:
            ctx=context(directory(root,initial={}),pipes({'A.NEW':b'a'}));handle=rt.FileHandle();ctx.files.open(handle,'WO','dst/A.NEW')
            try:self.assertEqual(move(ctx,'PIP:*','dst/*'),3);self.assertIn('PIP:A.NEW',ctx.file_pipes.pipes)
            finally:ctx.files.close(handle)
    def test_source_change_during_preflight_is_retained_without_move(self):
        with tempfile.TemporaryDirectory() as root:
            ctx=context(directory(root));original=ctx.file_pipes._check;changed=[]
            def check(name,data):
                result=original(name,data)
                if name=='PIP:B.NEW' and not changed:changed.append(True);(Path(root)/'src/a.kl').write_bytes(b'changed')
                return result
            with patch.object(ctx.file_pipes,'_check',side_effect=check),self.assertRaises(rt.KarelRuntimeError):move(ctx)
            self.assertEqual(disk(root)['src/a.kl'],b'changed');self.assertEqual(ctx.file_pipes.files['PIP:A.NEW'],b'')
    def test_directory_count_limit_is_checked_before_writing(self):
        with tempfile.TemporaryDirectory() as root:
            ctx=context(directory(root,initial={'dst/one':b'x','dst/two':b'x'}),pipes({'A.NEW':b'a'}));before=disk(root)
            with patch.object(fileops,'WILDCARD_FILE_LIMIT',2),self.assertRaises(rt.KarelRuntimeError):move(ctx,'PIP:*','dst/*')
            self.assertEqual(disk(root),before);self.assertIn('PIP:A.NEW',ctx.file_pipes.pipes)
    def test_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            ctx=context(directory(root),pipes({'A.NEW':b'a'}));before=disk(root)
            with self.assertRaises(rt.KarelRuntimeError):move(ctx,'PIP:*','../escape/*')
            self.assertEqual(disk(root),before)
    def test_caches_do_not_keep_moved_source(self):
        with tempfile.TemporaryDirectory() as root:
            ctx=context(directory(root));ctx.files.files['src/a.kl']=bytearray(b'stale');self.assertEqual(move(ctx),0);self.assertNotIn('src/a.kl',ctx.files.files)


class CrossBankPreflightTests(unittest.TestCase):
    def target_effect(self,effect):
        ctx=context();original=ctx.file_pipes._check;triggered=[]
        def check(name,data):
            result=original(name,data)
            if name=='PIP:B.NEW' and not triggered:triggered.append(True);effect(ctx)
            return result
        p=build(ctx)
        with patch.object(ctx.file_pipes,'_check',side_effect=check),self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['S'],77);return ctx
    def test_source_bytes_change_is_not_rolled_back_or_moved(self):
        ctx=self.target_effect(lambda ctx:ctx.files.files['src/a.kl'].extend(b'changed'));self.assertEqual(ctx.files.files['src/a.kl'],b'aaachanged');self.assertEqual(ctx.file_pipes.files['PIP:A.NEW'],b'')
    def test_equal_source_replacement_identity_is_detected(self):
        ctx=self.target_effect(lambda ctx:ctx.files.files.__setitem__('src/a.kl',bytearray(b'aaa')));self.assertEqual(ctx.files.files['src/a.kl'],b'aaa')
    def test_source_set_change_is_detected(self):
        ctx=self.target_effect(lambda ctx:ctx.files.files.__setitem__('src/c.kl',bytearray(b'new')));self.assertIn('src/c.kl',ctx.files.files)
    def test_target_empty_buffer_replacement_is_detected(self):
        ctx=self.target_effect(lambda ctx:ctx.file_pipes.files.__setitem__('PIP:A.NEW',bytearray()));self.assertIn('src/a.kl',ctx.files.files)
    def test_target_data_arrival_is_retained(self):
        ctx=self.target_effect(lambda ctx:ctx.file_pipes.feed('A.NEW',b'arrived'));self.assertEqual(ctx.file_pipes.files['PIP:A.NEW'],b'arrived')
    def test_configuration_value_change_is_detected(self):
        ctx=self.target_effect(lambda ctx:ctx.file_pipes.pipes['PIP:A.NEW'].__setitem__('form_ele',9));self.assertEqual(ctx.file_pipes.pipes['PIP:A.NEW']['form_ele'],9)
    def test_equal_configuration_replacement_is_detected(self):
        ctx=self.target_effect(lambda ctx:ctx.file_pipes.pipes.__setitem__('PIP:A.NEW',dict(ctx.file_pipes.pipes['PIP:A.NEW'])));self.assertIn('src/a.kl',ctx.files.files)
    def test_configuration_map_replacement_is_detected(self):
        ctx=self.target_effect(lambda ctx:setattr(ctx.file_pipes,'pipes',dict(ctx.file_pipes.pipes)));self.assertEqual(ctx.file_pipes.files['PIP:A.NEW'],b'')
    def test_source_map_replacement_is_detected(self):
        ctx=self.target_effect(lambda ctx:setattr(ctx.files,'files',dict(ctx.files.files)));self.assertIn('src/a.kl',ctx.files.files)
    def test_target_map_replacement_is_detected(self):
        ctx=self.target_effect(lambda ctx:setattr(ctx.file_pipes,'files',dict(ctx.file_pipes.files)));self.assertEqual(ctx.file_pipes.files['PIP:A.NEW'],b'')
    def test_new_pipe_during_preflight_is_retained(self):
        ctx=self.target_effect(lambda ctx:ctx.file_pipes.configure('EXTRA',False,1,0,'',0));self.assertIn('PIP:EXTRA',ctx.file_pipes.pipes)
    def test_budget_failure_changes_neither_bank(self):
        ctx=context();before=snapshots(ctx);p=build(ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):p.run(max_steps=3)
        self.assertEqual(snapshots(ctx),before);self.assertEqual(p.snapshot()['S'],77)
    def test_late_open_destination_is_busy(self):
        ctx=context();handle=rt.FileHandle();original=ctx.file_pipes._check;triggered=[]
        def check(name,data):
            result=original(name,data)
            if name=='PIP:B.NEW' and not triggered:triggered.append(True);ctx.file_pipes.open(handle,'RO','PIP:A.NEW')
            return result
        try:
            with patch.object(ctx.file_pipes,'_check',side_effect=check):self.assertEqual(move(ctx),3)
            self.assertIn('src/a.kl',ctx.files.files)
        finally:ctx.file_pipes.close(handle)
    def test_unrelated_open_file_retains_buffer_and_cursor(self):
        ctx=context();handle=rt.FileHandle();ctx.files.open(handle,'RO','keep.dat');ctx.files.read_bytes(handle,2);buffer=ctx.files.files[handle.name];position=handle.position
        try:self.assertEqual(move(ctx),0);self.assertIs(ctx.files.files[handle.name],buffer);self.assertEqual(handle.position,position);self.assertIs(handle.owner,ctx.files)
        finally:ctx.files.close(handle)
    def test_unrelated_open_pipe_is_not_rebound(self):
        ctx=context(bank=pipes({'A.NEW':b'','B.NEW':b'','OTHER':b'keep'}));handle=rt.FileHandle();ctx.file_pipes.open(handle,'RO','PIP:OTHER');buffer=ctx.file_pipes.files[handle.name]
        try:self.assertEqual(move(ctx),0);self.assertIs(ctx.file_pipes.files[handle.name],buffer);self.assertIs(handle.owner,ctx.file_pipes)
        finally:ctx.file_pipes.close(handle)


class CrossBankGuardTests(unittest.TestCase):
    def test_missing_source_returns_one(self):self.assertEqual(move(context(),'missing/*.kl','PIP:*.NEW'),1)
    def test_missing_destination_pipe_returns_one(self):
        ctx=context(bank=pipes({'A.NEW':b''}));before=snapshots(ctx);self.assertEqual(move(ctx),1);self.assertEqual(snapshots(ctx),before)
    def test_nonempty_destination_pipe_is_collision(self):
        ctx=context(bank=pipes({'A.NEW':b'old','B.NEW':b''}));before=snapshots(ctx);self.assertEqual(move(ctx),2);self.assertEqual(snapshots(ctx),before)
    def test_nonempty_later_pipe_preserves_earlier_target(self):
        ctx=context(bank=pipes({'A.NEW':b'','B.NEW':b'old'}));before=snapshots(ctx);self.assertEqual(move(ctx),2);self.assertEqual(snapshots(ctx),before)
    def test_existing_ordinary_target_is_collision(self):
        ctx=exported();ctx.files.files['dst/A.NEW']=bytearray();before=snapshots(ctx);self.assertEqual(move(ctx,'PIP:*','dst/*'),2);self.assertEqual(snapshots(ctx),before)
    def test_later_ordinary_collision_preserves_earlier_pipe(self):
        ctx=exported();ctx.files.files['dst/B.NEW']=bytearray(b'old');before=snapshots(ctx);self.assertEqual(move(ctx,'PIP:*','dst/*'),2);self.assertEqual(snapshots(ctx),before)
    def test_duplicate_target_mapping_is_rejected(self):
        ctx=context(bank=pipes({'FIXED':b''}));before=snapshots(ctx);self.assertEqual(move(ctx,target='PIP:FIXED'),2);self.assertEqual(snapshots(ctx),before)
    def test_case_ambiguous_sources_are_rejected(self):
        ctx=context(rt.MemoryFiles({'src/a.kl':b'a','src/A.KL':b'b'}));before=snapshots(ctx);self.assertEqual(move(ctx),2);self.assertEqual(snapshots(ctx),before)
    def test_pipe_capacity_status_four_is_atomic(self):
        ctx=context(rt.MemoryFiles({'src/a.kl':b'a','src/b.kl':b'x'*1025}));before=snapshots(ctx);self.assertEqual(move(ctx),4);self.assertEqual(snapshots(ctx),before)
    def test_exact_pipe_capacity_fit(self):
        ctx=context(rt.MemoryFiles({'src/a.kl':b'x'*1024}));self.assertEqual(move(ctx),0);self.assertEqual(len(ctx.file_pipes.files['PIP:A.NEW']),1024)
    def test_missing_ordinary_backend_is_not_discovered(self):
        ctx=rt.ExecutionContext(file_pipes=pipes({'A.NEW':b'a'}))
        with self.assertRaises(rt.KarelRuntimeError):move(ctx,'PIP:*','dst/*')
    def test_missing_pipe_backend_is_not_created(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(SEED))
        with self.assertRaises(rt.KarelRuntimeError):move(ctx)
    def test_source_pipe_over_capacity_is_invalid(self):
        ctx=exported();ctx.file_pipes.files['PIP:A.NEW']=bytearray(b'x'*1025);before=snapshots(ctx)
        with self.assertRaises(rt.KarelRuntimeError):move(ctx,'PIP:*','dst/*')
        self.assertEqual(snapshots(ctx),before)
    def test_malformed_pipe_record_is_rejected(self):
        ctx=context();ctx.file_pipes.pipes['PIP:A.NEW']['sectors']=True
        with self.assertRaises(rt.KarelRuntimeError):move(ctx)
        self.assertIn('src/a.kl',ctx.files.files)
    def test_mismatched_configuration_and_bytes_are_rejected(self):
        ctx=context();ctx.file_pipes.files.pop('PIP:A.NEW')
        with self.assertRaises(rt.KarelRuntimeError):move(ctx)
    def test_oversubscribed_pipe_reservations_are_rejected(self):
        ctx=context();ctx.file_pipes.pipes['PIP:A.NEW']['sectors']=33
        with self.assertRaises(rt.KarelRuntimeError):move(ctx)
    def test_memory_file_count_limit_is_atomic(self):
        ctx=context(rt.MemoryFiles({'one':b'x','two':b'x'}),pipes({'A.NEW':b'a'}));before=snapshots(ctx)
        with patch.object(fileops,'WILDCARD_FILE_LIMIT',2),self.assertRaises(rt.KarelRuntimeError):move(ctx,'PIP:*','dst/*')
        self.assertEqual(snapshots(ctx),before)
    def test_memory_file_count_exact_fit(self):
        ctx=context(rt.MemoryFiles({'one':b'x'}),pipes({'A.NEW':b'a'}))
        with patch.object(fileops,'WILDCARD_FILE_LIMIT',2):self.assertEqual(move(ctx,'PIP:*','dst/*'),0)
    def test_batch_retained_payload_budget_is_atomic(self):
        ctx=context();before=snapshots(ctx)
        with patch.object(fileops,'WILDCARD_COPY_BYTES',4),self.assertRaises(rt.KarelRuntimeError):move(ctx)
        self.assertEqual(snapshots(ctx),before)
    def test_destination_question_template_is_rejected(self):
        ctx=context();before=snapshots(ctx);self.assertEqual(move(ctx,target='PIP:?.NEW'),2);self.assertEqual(snapshots(ctx),before)
    def test_recursive_source_parent_is_rejected(self):
        ctx=context()
        with self.assertRaises(rt.KarelRuntimeError):move(ctx,'src/**/*.kl','PIP:*.NEW')
    def test_reserved_generated_destination_is_rejected(self):
        ctx=exported()
        with self.assertRaises(rt.KarelRuntimeError):move(ctx,'PIP:A.NEW','CON')
    def test_socket_endpoint_is_rejected(self):
        ctx=exported()
        with self.assertRaises(rt.KarelRuntimeError):move(ctx,'PIP:*','S2:peer')
    def test_daq_target_is_not_a_plain_pipe(self):
        ctx=context();ctx.acquisition=rt.Acquisition();ctx.acquisition.register(1,0,1,('INTEGER',),'DAQ.DAT',0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'DAQ PIP'):move(ctx,'src/a.kl','PIP:DAQ.DAT')


class CrossBankIntegrationTests(unittest.TestCase):
    def test_context_json_round_trip(self):
        ctx=context();move(ctx);saved=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_exact_result_can_be_reopened(self):
        ctx=exported();p,_=compile_program("RENAME_FILE('PIP:A.NEW','number',FALSE,s) OPEN FILE f('RO','number') READ f(n) CLOSE FILE f",decl='s,n:INTEGER f:FILE',context=ctx);ctx.file_pipes.files['PIP:A.NEW']=bytearray(b'7');self.assertEqual(p.run()['N'],7)
    def test_linked_routine_uses_shared_explicit_banks(self):
        ctx=context();p=translate_project({'main':"PROGRAM MAIN VAR status:INTEGER ROUTINE work(value:INTEGER) FROM LIB BEGIN work(status) END MAIN",'lib':"PROGRAM LIB ROUTINE work(value:INTEGER) BEGIN RENAME_FILE('src/*.kl','PIP:*.NEW',FALSE,value) END work BEGIN END LIB"}).instantiate(context=ctx);p.run('MAIN');self.assertEqual(p.programs['MAIN'].snapshot()['STATUS'],0);self.assertEqual(ctx.file_pipes.files['PIP:B.NEW'],b'\0b')
    def test_cooperative_execution_has_one_completed_operation(self):
        ctx=context();p=build(ctx,cooperative=True);self.assertEqual(p.run()['S'],0);self.assertEqual([row['outcome'] for row in p._state.service_requests if row['operation']=='RENAME_FILE'],['completed'])


class CrossBankReportTests(unittest.TestCase):
    def test_report_describes_exact_and_wildcard_explicit_services(self):
        _,report=compile_program("RENAME_FILE('src/a.kl','PIP:A.NEW',FALSE,s)",decl='s:INTEGER',context=context())
        policy=report.report['cross_bank_rename_policy'];self.assertEqual(policy['guide'],'docs/cross-bank-rename.md');self.assertFalse(policy['controller_validated'])
        self.assertIn('Exact names',policy['forms']);self.assertIn('empty and closed',policy['destination']);self.assertEqual(len(policy['calls']),1)
    def test_report_retains_host_failure_and_bounded_payload_contracts(self):
        _,report=compile_program("RENAME_FILE('src/*.kl','PIP:*.NEW',TRUE,s)",decl='s:INTEGER',context=context())
        policy=report.report['cross_bank_rename_policy'];self.assertIn('late host errors',policy['publication']);self.assertIn('64 MiB',policy['limits']);self.assertIn('synchronously',policy['limits']);self.assertIn('native/controller',policy['boundary'])
    def test_shared_report_does_not_claim_all_cross_bank_renames_are_blocked(self):
        _,report=compile_program('s=0',decl='s:INTEGER')
        self.assertEqual(report.report['wildcard_file_policy']['cross_bank_guide'],'docs/cross-bank-rename.md')
        self.assertNotIn('cross-backend rename,',report.report['pipe_file_management_policy']['boundaries'])


if __name__=='__main__':unittest.main()
