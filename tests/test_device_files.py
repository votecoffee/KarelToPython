"""Authored virtual media lifecycle, quota/reclamation and source integration."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run


DECL='f: FILE n,free,s,prior: INTEGER text: STRING[32]'


def files():
    return rt.DeviceFiles({'RD:':{'capacity':100},'FR:':{'capacity':100,'garbage':2},
        'UD1:':{'capacity':50,'label':'AUTHORED','info':{'DF_MANUFNAME':'Example','DF_SERIALNO':'SYNTHETIC'}},
        'FROM:':{'capacity':200}}, {'RD:a':b'ram','FR:b':b'flash','UD1:c':b'usb'})


class VirtualVolumeTests(unittest.TestCase):
    def test_source_volume_queries_and_total_only_outputs(self):
        bank=files();ctx=rt.ExecutionContext(files=bank)
        data=run("VOL_SPACE('rd:',n,free,text) prior=free free=77 text='saved' VOL_SPACE('FROM:',n,free,text)",decl=DECL,context=ctx)
        self.assertEqual((data['PRIOR'],data['N'],data['FREE'],data['TEXT']),(97,200,77,'saved'))
        data=run("VOL_SPACE('UD1:',n,free,text)",decl=DECL,context=ctx)
        self.assertEqual((data['N'],data['FREE'],data['TEXT']),(50,47,'AUTHORED'))

    def test_mount_and_dismount_retain_data_and_block_access(self):
        bank=files();ctx=rt.ExecutionContext(files=bank)
        self.assertEqual(run("DISMOUNT_DEV('RD:',s)",context=ctx)['S'],0)
        self.assertEqual(bank.snapshot()['RD:a'],b'ram');self.assertNotIn('RD:a',bank.list_names())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'mounted'):run("OPEN FILE f('RO','RD:a')",decl=DECL,context=ctx)
        self.assertEqual(run("MOUNT_DEV('rd:',s) OPEN FILE f('RO','rd:a') CLOSE FILE f",decl=DECL,context=ctx)['S'],0)

    def test_dismount_format_and_purge_are_busy_for_open_files(self):
        bank=files();ctx=rt.ExecutionContext(files=bank)
        data=run("OPEN FILE f('RO','FR:b') DISMOUNT_DEV('FR:',s) n=s FORMAT_DEV('FR:','new',FALSE,s) free=s PURGE_DEV('FR:',s) CLOSE FILE f",decl=DECL,context=ctx)
        self.assertEqual((data['N'],data['FREE'],data['S']),(4,4,4))
        self.assertEqual(bank.snapshot()['FR:b'],b'flash');self.assertEqual(bank.to_config()['volumes']['FR:']['garbage'],2)

    def test_format_clears_only_selected_virtual_volume_and_truncates_label(self):
        bank=files();ctx=rt.ExecutionContext(files=bank)
        data=run("FORMAT_DEV('FR:','abcdefghijklmnop',TRUE,s)",context=ctx)
        self.assertEqual(data['S'],0);self.assertEqual(bank.snapshot(),{'RD:a':b'ram','UD1:c':b'usb'})
        row=bank.to_config()['volumes']['FR:'];self.assertEqual((row['label'],row['garbage']),('abcdefghijk',0))

    def test_purge_reclaims_obsolete_bytes_without_deleting_live_files(self):
        bank=files();ctx=rt.ExecutionContext(files=bank);before=bank.snapshot()
        data=run("VOL_SPACE('FR:',n,free,text) prior=free PURGE_DEV('FR:',s) VOL_SPACE('FR:',n,free,text)",decl=DECL,context=ctx)
        self.assertEqual((data['PRIOR'],data['FREE'],data['S']),(93,95,0));self.assertEqual(bank.snapshot(),before)
        self.assertEqual(run("PURGE_DEV('FR:',s)",context=ctx)['S'],85023)

    def test_combined_purge_is_atomic_if_either_volume_is_unmounted_or_busy(self):
        for busy in (False,True):
            bank=files();ctx=rt.ExecutionContext(files=bank)
            if busy:
                h=rt.FileHandle();bank.open(h,'RO','RD:a')
            else:bank.mount('RD:',False)
            before=bank.to_config()
            self.assertEqual(run("PURGE_DEV('MF:',s)",context=ctx)['S'],4 if busy else 3)
            self.assertEqual(bank.to_config(),before)

    def test_combined_purge_clears_both_explicit_counters(self):
        bank=rt.DeviceFiles({'RD:':{'capacity':20,'garbage':2},'FR:':{'capacity':20,'garbage':3}})
        self.assertEqual(bank.purge('MF:'),0)
        self.assertEqual((bank.space('RD:')[1]['free'],bank.space('FR:')[1]['free']),(20,20))

    def test_readonly_and_memory_only_devices_reject_mutations(self):
        bank=rt.DeviceFiles({'UD1:':{'capacity':20,'read_only':True},'DRAM:':{'capacity':20}}, {'UD1:a':b'one'})
        self.assertEqual(bank.format('UD1:','new'),5);self.assertEqual(bank.purge('UD1:'),5)
        self.assertEqual(bank.format('DRAM:','new'),2);self.assertEqual(bank.purge('DRAM:'),2)
        with self.assertRaises(rt.KarelRuntimeError):bank.delete('UD1:a')
        with self.assertRaises(rt.KarelRuntimeError):bank.open(rt.FileHandle(),'RW','UD1:a')
        self.assertEqual(bank.snapshot(),{'UD1:a':b'one'})

    def test_unknown_devices_and_bad_labels_do_not_mutate(self):
        bank=files();before=bank.to_config()
        self.assertEqual(bank.mount('ZZ:'),2);self.assertEqual(bank.mount('RD'),2)
        self.assertEqual(bank.format('RD:','bad\nlabel'),2);self.assertEqual(bank.purge('ZZ:'),2)
        self.assertEqual(bank.to_config(),before)

    def test_unmounted_volume_query_preserves_every_output(self):
        bank=files();bank.mount('RD:',False)
        p,_=compile_program("n=7 free=8 text='old' VOL_SPACE('RD:',n,free,text)",decl=DECL,context=rt.ExecutionContext(files=bank))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['FREE'],p.snapshot()['TEXT']),(7,8,'old'))

    def test_small_volume_label_preserves_all_outputs(self):
        p,_=compile_program("n=7 free=8 text='old' VOL_SPACE('UD1:',n,free,text)",decl='n,free: INTEGER text: STRING[3]',context=rt.ExecutionContext(files=files()))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot(),{'N':7,'FREE':8,'TEXT':'old'})

    def test_host_and_directory_backends_are_never_management_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'keep.txt';path.write_bytes(b'preserve')
            for backend in (rt.MemoryFiles({'RD:a':'keep'}),rt.DirectoryFiles(temporary),None):
                for call in ("FORMAT_DEV('RD:','new',FALSE,s)","MOUNT_DEV('RD:',s)","PURGE_DEV('RD:',s)","VOL_SPACE('RD:',n,free,text)"):
                    p,_=compile_program('s=99 '+call,decl=DECL,context=rt.ExecutionContext(files=backend))
                    with self.subTest(call=call,backend=type(backend)),self.assertRaisesRegex(rt.KarelRuntimeError,'virtual DeviceFiles'):p.run()
                    self.assertEqual(p.snapshot()['S'],99)
            self.assertEqual(path.read_bytes(),b'preserve')

    def test_management_uses_no_host_file_operations(self):
        ctx=rt.ExecutionContext(files=files())
        p,_=compile_program("DISMOUNT_DEV('RD:',s) MOUNT_DEV('RD:',s) FORMAT_DEV('UD1:','new',FALSE,s) PURGE_DEV('FR:',s) VOL_SPACE('FR:',n,free,text)",decl=DECL,context=ctx)
        with patch('builtins.open',side_effect=AssertionError('unexpected host file access')):self.assertEqual(p.run()['S'],0)

    def test_format_preflight_budget_and_new_busy_handle_prevent_changes(self):
        bank=rt.DeviceFiles({'RD:':{'capacity':20}}, {'RD:a':b'one','RD:b':b'two'});before=bank.to_config()
        state=rt.State({},{});state.max_steps=1
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):bank.format('RD:','new',check=state.tick)
        self.assertEqual(bank.to_config(),before)
        handle=rt.FileHandle()
        def check():
            if handle.owner is None:bank.open(handle,'RO','RD:a')
        self.assertEqual(bank.format('RD:','new',check=check),4);self.assertEqual(bank.to_config(),before)


class VirtualCapacityTests(unittest.TestCase):
    def test_source_write_capacity_failure_keeps_bytes_cursor_and_accounting(self):
        bank=rt.DeviceFiles({'RD:':{'capacity':5}}, {'RD:a':b'abcd'})
        p,_=compile_program("OPEN FILE f('RW','rd:a') SET_FILE_POS(f,4,s) WRITE f('xy')",decl=DECL,context=rt.ExecutionContext(files=bank))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):p.run()
        self.assertEqual((bank.snapshot()['RD:a'],p.snapshot()['F']['position'],bank.space('RD:')[1]['free']),(b'abcd',4,1))

    def test_flash_overwrite_delete_and_purge_account_for_obsolete_bytes(self):
        bank=rt.DeviceFiles({'FR:':{'capacity':8,'garbage':2}}, {'FR:a':b'abc'})
        h=rt.FileHandle();bank.open(h,'RW','FR:a');bank.write(h,b'xy')
        self.assertEqual((bank.snapshot()['FR:a'],bank.space('FR:')[1]['free']),(b'xyc',1))
        before=bank.to_config();h.position=0
        with self.assertRaises(rt.KarelRuntimeError):bank.write(h,b'zzz')
        self.assertEqual(bank.to_config(),before);bank.close(h);bank.delete('FR:a')
        self.assertEqual(bank.space('FR:')[1]['free'],1);self.assertEqual(bank.purge('FR:'),0)
        self.assertEqual(bank.space('FR:')[1]['free'],8)

    def test_ram_delete_returns_space_immediately(self):
        bank=rt.DeviceFiles({'RD:':{'capacity':4}}, {'RD:a':b'data'});bank.delete('RD:a')
        self.assertEqual(bank.space('RD:')[1]['free'],4);self.assertEqual(bank.purge('RD:'),85023)

    def test_truncation_reserves_old_flash_bytes_as_garbage(self):
        bank=rt.DeviceFiles({'FR:':{'capacity':6}}, {'FR:a':b'data'});h=rt.FileHandle();bank.open(h,'WO','FR:a')
        self.assertEqual((bank.snapshot()['FR:a'],bank.space('FR:')[1]['free']),(b'',2))
        bank.write(h,b'xy');bank.close(h);self.assertEqual(bank.space('FR:')[1]['free'],0)

    def test_copy_overwrite_checks_live_plus_garbage_before_mutation(self):
        bank=rt.DeviceFiles({'RD:':{'capacity':10},'FR:':{'capacity':5}}, {'RD:s':b'new','FR:t':b'old'})
        before=bank.to_config()
        with self.assertRaises(rt.KarelRuntimeError):bank.copy('RD:s','FR:t',True)
        self.assertEqual(bank.to_config(),before)
        bank.delete('FR:t');bank.purge('FR:');self.assertEqual(bank.copy('RD:s','FR:t'),0)

    def test_same_volume_rename_at_capacity_needs_no_copy_space(self):
        bank=rt.DeviceFiles({'RD:':{'capacity':4}}, {'RD:a':b'data'})
        self.assertEqual(bank.rename('rd:a','RD:b'),0);self.assertEqual(bank.space('RD:')[1]['free'],0)

    def test_cross_volume_move_reserves_destination_and_retains_source_garbage(self):
        bank=rt.DeviceFiles({'RD:':{'capacity':2},'FR:':{'capacity':10}}, {'FR:a':b'data'})
        before=bank.to_config()
        with self.assertRaises(rt.KarelRuntimeError):bank.rename('FR:a','RD:a')
        self.assertEqual(bank.to_config(),before)
        bank=rt.DeviceFiles({'RD:':{'capacity':10},'FR:':{'capacity':10}}, {'FR:a':b'data'})
        self.assertEqual(bank.move('FR:*'),0);self.assertEqual(bank.snapshot(),{'RD:a':b'data'})
        self.assertEqual((bank.space('RD:')[1]['free'],bank.space('FR:')[1]['free']),(6,6))

    def test_batch_move_capacity_is_checked_before_the_first_move(self):
        bank=rt.DeviceFiles({'RD:':{'capacity':3},'FR:':{'capacity':20}}, {'FR:a':b'aa','FR:b':b'bb'})
        before=bank.to_config();ctx=rt.ExecutionContext(files=bank)
        p,_=compile_program("s=99 MOVE_FILE('FR:*',s)",context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'complete MOVE_FILE batch'):p.run()
        self.assertEqual((bank.to_config(),p.snapshot()['S']),(before,99))

    def test_device_names_fold_case_paths_preserve_case_and_reject_traversal(self):
        bank=rt.DeviceFiles({'RD:':{'capacity':10}}, {'rd:Dir/a':b'data'})
        self.assertEqual(bank.read_named('rD:Dir/a'),(0,b'data'))
        for name in ('RD:/a','RD:../a','RD:Dir/../a','RD:Dir\\a','RD:a:b','unknown:a','RD:'):
            with self.subTest(name=name),self.assertRaises(rt.KarelRuntimeError):bank.open(rt.FileHandle(),'RW',name)

    def test_xml_and_text_operations_share_the_same_virtual_mount(self):
        bank=rt.DeviceFiles({'RD:':{'capacity':100}}, {'RD:input.xml':b'<item/>'})
        data=run("SET_FILE_ATR(f,ATR_XML) OPEN FILE f('RO','RD:input.xml') XML_ADDTAG(f,'item',254,FALSE,7,s) XML_SCAN(f,text,n,free,s) DISMOUNT_DEV('RD:',s) CLOSE FILE f",decl=DECL,context=rt.ExecutionContext(files=bank))
        self.assertEqual((data['TEXT'],data['N'],data['S']),('item',7,4))


class DeviceMetadataAndPersistenceTests(unittest.TestCase):
    def test_all_five_device_information_fields_and_selected_outputs(self):
        info={name:str(i) for i,name in enumerate(rt.DEVICE_INFO,1)}
        bank=rt.DeviceFiles({'UD1:':{'capacity':100,'info':info}});ctx=rt.ExecutionContext(files=bank)
        for name in info:
            with self.subTest(name=name):
                data=run(f"DOSFILE_INF('ud1:',{name},text,s)",decl=DECL,context=ctx)
                self.assertEqual((data['TEXT'],data['S']),(info[name],0))

    def test_missing_invalid_unmounted_and_short_info_preserve_text(self):
        bank=files();ctx=rt.ExecutionContext(files=bank)
        for device,item,code in (('UD1:','DF_PRODNAME',1),('UD1:','999',2),('XX:','DF_MANUFNAME',2),('UD1:','DF_MANUFNAME',7)):
            with self.subTest(device=device,item=item):
                data=run(f"text='old' DOSFILE_INF('{device}',{item},text,s)",decl='s: INTEGER text: STRING[3]',context=ctx)
                self.assertEqual((data['TEXT'],data['S']),('old',code))
        bank.mount('UD1:',False)
        self.assertEqual(run("DOSFILE_INF('UD1:',DF_MANUFNAME,text,s)",decl=DECL,context=ctx)['S'],3)

    def test_json_roundtrip_preserves_unmounted_media_flags_and_garbage_without_handles(self):
        bank=files();bank.mount('FR:',False);ctx=rt.ExecutionContext(files=bank)
        h=rt.FileHandle();bank.open(h,'RO','RD:a')
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved);self.assertNotIn('files',saved)
        self.assertEqual(restored.files.handles,[]);self.assertEqual(restored.files.snapshot(),bank.snapshot())
        saved['device_files']['volumes']['RD:']['capacity']=50
        self.assertEqual(bank.space('RD:')[1]['total'],100)

    def test_malformed_configuration_rejected_without_allocating_resources(self):
        config=files().to_config();variants=[]
        for key,value in (('mounted',1),('read_only','yes'),('capacity',True),('capacity',0),('garbage',101),('label','x'*12),('info',{'UNKNOWN':'x'})):
            row=deepcopy(config);row['volumes']['RD:'][key]=value;variants.append(row)
        for key,value in (('unknown',1),('limit',0),('files',{'RD:a':{'hex':'z'}}),('files',{'RD:a':123})):
            row=deepcopy(config);row[key]=value;variants.append(row)
        row=deepcopy(config);row['volumes']['rd:']=deepcopy(row['volumes']['RD:']);variants.append(row)
        row=deepcopy(config);row['files']['rd:a']='alias';variants.append(row)
        for row in variants:
            with self.subTest(row=row),self.assertRaises((ValueError,rt.KarelRuntimeError)):rt.DeviceFiles.from_config(row)
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config({'files':{},'device_files':config})

    def test_total_capacity_limit_and_initial_usage_are_checked(self):
        with self.assertRaises(ValueError):rt.DeviceFiles({'RD:':{'capacity':64*1024*1024},'FR:':{'capacity':1}})
        with self.assertRaises(ValueError):rt.DeviceFiles({'FR:':{'capacity':4,'garbage':2}}, {'FR:a':b'abc'})
        with self.assertRaises(ValueError):rt.DeviceFiles({'MF:':{'capacity':10}})

    def test_outputs_counter_guards_types_and_user_routine_precedence(self):
        for body in ("FOR s=1 TO 2 DO MOUNT_DEV('RD:',s) ENDFOR","FOR n=1 TO 2 DO VOL_SPACE('RD:',n,free,text) ENDFOR"):
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught:compile_program(body,decl=DECL)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
        p,_=compile_program("n=99 VOL_SPACE('RD:',n,n,text)",decl=DECL,context=rt.ExecutionContext(files=files()))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p.snapshot()['N'],99)
        with self.assertRaises(TranslationError):compile_program("FORMAT_DEV('RD:','new',1,s)")
        self.assertEqual(run('MOUNT_DEV(7)',routines='ROUTINE MOUNT_DEV(n: INTEGER) BEGIN s=n END MOUNT_DEV')['S'],7)


if __name__=='__main__':unittest.main()
