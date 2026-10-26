"""Authored DAQ lifecycle, binary FILE, streaming and saved-context checks."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_program_calls import module
from tests.test_project_scheduler import source


DECL='value,s,flags,available,a,b:INTEGER f:FILE'
REG="DAQ_REGPIPE(1,DAQ_DRAM,3,'','value','authored.dat',0,s)"
START="DAQ_START(1,DAQ_STREAM,'',s)"


def context(*,files=None,limit=16*1024*1024):
    return rt.ExecutionContext(acquisition=rt.Acquisition(limit=limit),files=files)


def setup(*,capacity=3,stream=0,files=None,mode='DAQ_STREAM',limit=16*1024*1024):
    ctx=context(files=files,limit=limit)
    p,_=compile_program(f"DAQ_REGPIPE(1,DAQ_DRAM,{capacity},'','value','authored.dat',{stream},s) DAQ_START(1,{mode},'RD:',s)",decl=DECL,context=ctx)
    p.run();return ctx


def write(ctx,value):
    return run(f"value={value} DAQ_WRITE(1,'','value',s)",decl=DECL,context=ctx)['S']


class AcquisitionLifecycleTests(unittest.TestCase):
    def test_registration_start_stop_and_flags(self):
        ctx=context();data=run(REG+' DAQ_CHECKP(1,flags,available) a=flags '+START+' DAQ_CHECKP(1,flags,available) b=flags DAQ_STOP(1,FALSE,s) DAQ_CHECKP(1,flags,available)',decl=DECL,context=ctx)
        self.assertEqual((data['A'],data['B'],data['FLAGS'],data['AVAILABLE'],data['S']),(1,7,5,0,0))

    def test_start_reference_count_and_forced_stop(self):
        ctx=setup();data=run(START+' DAQ_STOP(1,FALSE,s) DAQ_CHECKP(1,flags,available) a=flags DAQ_STOP(1,TRUE,s) DAQ_CHECKP(1,flags,available)',decl=DECL,context=ctx)
        self.assertEqual((data['A'],data['FLAGS']),(7,5));self.assertEqual(ctx.acquisition.pipes[1]['starts'],0)

    def test_inactive_and_missing_writes_preserve_data(self):
        ctx=context();data=run(REG+" value=3 DAQ_WRITE(1,'','value',s)",decl=DECL,context=ctx)
        self.assertEqual(data['S'],6);self.assertEqual(ctx.acquisition.files['PIP:AUTHORED.DAT'],b'')
        self.assertEqual(run("value=3 DAQ_WRITE(2,'','value',s)",decl=DECL,context=ctx)['S'],1)

    def test_unregistered_check_is_zero_and_invalid_number_preserves_outputs(self):
        self.assertEqual(run('DAQ_CHECKP(1,flags,available)',decl=DECL,context=context())['FLAGS'],0)
        p,_=compile_program('flags=77 available=88 DAQ_CHECKP(6,flags,available)',decl=DECL,context=context())
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['FLAGS'],p.snapshot()['AVAILABLE']),(77,88))

    def test_registration_uses_uninitialized_type_and_preserves_duplicate(self):
        ctx=context();data=run(REG+' '+START+" value=7 DAQ_WRITE(1,'','value',s) "+REG,decl=DECL,context=ctx)
        self.assertEqual(data['S'],3);self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<i',7))

    def test_names_options_and_total_capacity_are_bounded(self):
        for name,memory,capacity,stream,code in [('bad',0,1,0,2),('../x.dat',0,1,0,2),('a.dat',1,1,0,2),('a.dat',0,0,0,2),('a.dat',0,1,2,2),('a.dat',0,3,0,5)]:
            ctx=context(limit=8)
            data=run(f"DAQ_REGPIPE(1,{memory},{capacity},'','value','{name}',{stream},s)",decl=DECL,context=ctx)
            self.assertEqual(data['S'],code);self.assertEqual(ctx.acquisition.pipes,{})
        ctx=context(limit=8)
        data=run("DAQ_REGPIPE(1,DAQ_DRAM,1,'','value','a.dat',0,s) DAQ_REGPIPE(2,DAQ_CMOS,2,'','value','b.dat',0,s)",decl=DECL,context=ctx)
        self.assertEqual(data['S'],5);self.assertEqual(set(ctx.acquisition.pipes),{1})

    def test_duplicate_names_and_resource_schemas_reject(self):
        ctx=context();self.assertEqual(run(REG+" DAQ_REGPIPE(2,DAQ_DRAM,1,'','value','AUTHORED.DAT',0,s)",decl=DECL,context=ctx)['S'],3)
        ctx=context();self.assertEqual(run("DAQ_REGPIPE(1,DAQ_DRAM,1,'','f','f.dat',0,s)",decl=DECL,context=ctx)['S'],4)
        self.assertEqual(ctx.acquisition.pipes,{})

    def test_unregister_guards_active_and_open_readers(self):
        ctx=setup();self.assertEqual(run('DAQ_UNREG(1,s)',context=ctx)['S'],3)
        p,_=compile_program("OPEN FILE f('RB','PIP:AUTHORED.DAT') DAQ_STOP(1,TRUE,s) DAQ_UNREG(1,s)",decl=DECL,context=ctx)
        self.assertEqual(p.run()['S'],3);p._state.file_close(p._state.values['F'])
        self.assertEqual(run('DAQ_UNREG(1,s) DAQ_CHECKP(1,flags,available)',decl=DECL,context=ctx)['FLAGS'],0)
        self.assertEqual(ctx.acquisition.files,{})

    def test_conflicting_modes_and_snapshot_auto_stream_reject(self):
        ctx=setup();self.assertEqual(run("DAQ_START(1,DAQ_SNAPSHT,'',s)",context=ctx)['S'],2)
        ctx=context(files=rt.MemoryFiles())
        self.assertEqual(run("DAQ_REGPIPE(1,DAQ_DRAM,2,'','value','a.dat',1,s) DAQ_START(1,DAQ_SNAPSHT,'RD:',s)",decl=DECL,context=ctx)['S'],2)
        self.assertEqual(ctx.acquisition.pipes[1]['starts'],0)

    def test_pipe_lifetime_is_shared_across_program_completion(self):
        ctx=setup();self.assertEqual(write(ctx,3),0)
        self.assertEqual(ctx.acquisition.pipes[1]['starts'],1)
        self.assertEqual(run('DAQ_STOP(1,TRUE,s)',context=ctx)['S'],0)


class AcquisitionDataTests(unittest.TestCase):
    def test_scalar_structure_and_fixed_string_layout(self):
        ctx=context()
        data=run("DAQ_REGPIPE(1,DAQ_DRAM,2,'','packet','data.bin',0,s) "+START+" packet.id=7 packet.measure=1.5 packet.ok=TRUE packet.label='x' DAQ_WRITE(1,'','packet',s)",decl='packet:record s:INTEGER',
            prefix='TYPE record=STRUCTURE id:INTEGER measure:REAL ok:BOOLEAN label:STRING[4] ENDSTRUCTURE',context=ctx)
        self.assertEqual(data['S'],0)
        self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<if?',7,1.5,True)+b'x\0\0\0')

    def test_multidimensional_array_and_narrow_leaves(self):
        ctx=context();data=run("DAQ_REGPIPE(1,DAQ_DRAM,1,'','values','a.dat',0,s) "+START+" values[1,1]=1 values[1,2]=2 values[2,1]=3 values[2,2]=4 DAQ_WRITE(1,'','values',s)",decl='values:ARRAY[2,2] OF SHORT s:INTEGER',context=ctx)
        self.assertEqual(data['S'],0);self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<hhhh',1,2,3,4))

    def test_type_identity_and_uninitialized_records_fail_before_mutation(self):
        ctx=context();data=run("DAQ_REGPIPE(1,DAQ_DRAM,2,'','a','a.dat',0,s) "+START+" b[1]=1 b[2]=2 DAQ_WRITE(1,'','b',s)",decl='a:first b:second s:INTEGER',
            prefix='TYPE first=ARRAY[2] OF INTEGER second=ARRAY[2] OF INTEGER',context=ctx)
        self.assertEqual(data['S'],4);self.assertEqual(ctx.acquisition.files['PIP:A.DAT'],b'')
        ctx=setup();self.assertEqual(run("DAQ_WRITE(1,'','value',s)",decl=DECL,context=ctx)['S'],4)

    def test_float32_overflow_is_rejected(self):
        ctx=context();data=run("DAQ_REGPIPE(1,DAQ_DRAM,1,'','x','a.dat',0,s) "+START+" x=1.0E100 DAQ_WRITE(1,'','x',s)",decl='x:REAL s:INTEGER',context=ctx)
        self.assertEqual(data['S'],4);self.assertEqual(ctx.acquisition.files['PIP:A.DAT'],b'')

    def test_foreign_dynamic_paths_use_explicit_store(self):
        ctx=context();ctx.variables.define('CACHE','VALUES',('ARRAY',2,('INTEGER',)))
        data=run("DAQ_REGPIPE(1,DAQ_DRAM,1,'CACHE','VALUES[2]','a.dat',0,s) "+START+" SET_VAR(e,'CACHE','VALUES[2]',17,s) DAQ_WRITE(1,'CACHE','VALUES[2]',s)",decl='e,s:INTEGER',context=ctx)
        self.assertEqual(data['S'],0);self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<i',17))

    def test_ring_overflow_retains_latest_complete_records(self):
        ctx=setup(capacity=2)
        for value in (1,2,3):self.assertEqual(write(ctx,value),0)
        self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<ii',2,3))

    def test_reader_overflow_flag_is_hidden_from_writer(self):
        ctx=setup(capacity=1);write(ctx,1)
        reader=module('READER','',context=ctx);handle=rt.FileHandle()
        ctx.acquisition.open_for(reader._state,handle,'RB','PIP:AUTHORED.DAT')
        writer,_=compile_program("value=2 DAQ_WRITE(1,'','value',s) DAQ_CHECKP(1,flags,available)",decl=DECL,context=ctx)
        self.assertFalse(writer.run()['FLAGS']&32)
        self.assertTrue(ctx.acquisition.check(reader._state,1)[0]&32)
        ctx.acquisition.close(handle)

    def test_snapshot_host_reads_retain_records(self):
        ctx=setup(mode='DAQ_SNAPSHT');write(ctx,8)
        self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<i',8))
        self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<i',8))


class AcquisitionFileTests(unittest.TestCase):
    def test_binary_file_read_consumes_complete_stream_records(self):
        ctx=setup();write(ctx,42)
        data=run("OPEN FILE f('RB','PIP:authored.dat') READ f(a) DAQ_CHECKP(1,flags,available) CLOSE FILE f",decl=DECL,context=ctx)
        self.assertEqual((data['A'],data['FLAGS'],data['AVAILABLE']),(42,23,0))
        self.assertEqual(ctx.acquisition.files['PIP:AUTHORED.DAT'],b'')

    def test_partial_record_read_retains_the_remaining_bytes(self):
        ctx=context();data=run("DAQ_REGPIPE(1,DAQ_DRAM,2,'','values','a.dat',0,s) "+START+" values[1]=7 values[2]=8 DAQ_WRITE(1,'','values',s) OPEN FILE f('RB','PIP:A.DAT') READ f(a) DAQ_CHECKP(1,flags,available) b=available READ f(a) DAQ_CHECKP(1,flags,available) CLOSE FILE f",decl=DECL+' values:ARRAY[2] OF INTEGER',context=ctx)
        self.assertEqual((data['A'],data['B'],data['AVAILABLE']),(8,4,0))

    def test_failed_batch_read_restores_outputs_cursor_and_pipe(self):
        ctx=setup();write(ctx,7)
        p,_=compile_program("a=77 b=88 OPEN FILE f('RB','PIP:AUTHORED.DAT') READ f(a,b)",decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['A'],p.snapshot()['B'],p.snapshot()['F']['position']),(77,88,0))
        self.assertFalse(ctx.acquisition.pipes[1]['first_read']);p._state.file_close(p._state.values['F'])
        self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<i',7))

    def test_multiple_readers_retain_data_until_all_consume(self):
        ctx=setup();write(ctx,7);bank=ctx.acquisition
        readers=[module(name,'',context=ctx) for name in ('FIRST','SECOND')];handles=[rt.FileHandle(),rt.FileHandle()]
        refs=[rt.Reference(('INTEGER',),{'value':rt.UNINITIALIZED},'value') for _ in handles]
        for reader,handle in zip(readers,handles):bank.open_for(reader._state,handle,'RB','PIP:AUTHORED.DAT')
        readers[0]._state.file_read(handles[0],[refs[0]])
        self.assertEqual(len(bank.files['PIP:AUTHORED.DAT']),4)
        readers[1]._state.file_read(handles[1],[refs[1]])
        self.assertEqual(bank.files['PIP:AUTHORED.DAT'],b'');self.assertEqual([ref.raw() for ref in refs],[7,7])
        for handle in handles:bank.close(handle)

    def test_snapshot_file_is_frozen_until_reopened(self):
        ctx=setup(mode='DAQ_SNAPSHT');write(ctx,1)
        p,_=compile_program("OPEN FILE f('RB','PIP:AUTHORED.DAT')",decl=DECL,context=ctx);p.run()
        self.assertEqual(p.snapshot()['F']['file'],'PIP:AUTHORED.DAT')
        handle=p._state.values['F'];write(ctx,2)
        self.assertEqual(ctx.acquisition.files[handle.name],struct.pack('<i',1))
        p._state.file_close(handle);ctx.acquisition.open_for(p._state,handle,'RB','PIP:AUTHORED.DAT')
        self.assertEqual(ctx.acquisition.files[handle.name],struct.pack('<ii',1,2));ctx.acquisition.close(handle)

    def test_file_access_requires_created_binary_read_only_pipe(self):
        ctx=setup()
        for mode in ('RO','WB','RWB'):
            p,_=compile_program(f"OPEN FILE f('{mode}','PIP:AUTHORED.DAT')",decl=DECL,context=ctx)
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(ctx.acquisition.readers,{})
        self.assertEqual(run("SET_FILE_ATR(f,ATR_UF) OPEN FILE f('RO','PIP:AUTHORED.DAT') CLOSE FILE f",decl=DECL,context=ctx)['F']['open'],False)

    def test_snapshot_views_have_a_combined_byte_limit(self):
        ctx=setup(capacity=1,mode='DAQ_SNAPSHT',limit=4);write(ctx,1)
        p=module('READER','',context=ctx);first=rt.FileHandle();second=rt.FileHandle()
        ctx.acquisition.open_for(p._state,first,'RB','PIP:AUTHORED.DAT')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'byte limit'):ctx.acquisition.open_for(p._state,second,'RB','PIP:AUTHORED.DAT')
        self.assertIsNone(second.owner);ctx.acquisition.close(first)

    def test_closing_lagging_reader_reclaims_consumed_records(self):
        ctx=setup();write(ctx,7);bank=ctx.acquisition
        owner=module('READER','',context=ctx);handles=[rt.FileHandle(),rt.FileHandle()]
        for handle in handles:bank.open_for(owner._state,handle,'RB','PIP:AUTHORED.DAT')
        target=rt.Reference(('INTEGER',),{'value':rt.UNINITIALIZED},'value')
        owner._state.file_read(handles[0],[target]);self.assertEqual(len(bank.files['PIP:AUTHORED.DAT']),4)
        bank.close(handles[1]);self.assertEqual(bank.files['PIP:AUTHORED.DAT'],b'')
        self.assertEqual(handles[0].position,0);bank.close(handles[0])


class AcquisitionStreamingTests(unittest.TestCase):
    def test_batch_threshold_and_final_stop_flush(self):
        files=rt.MemoryFiles({'RD:AUTHORED.DAT':b'prefix'});ctx=setup(stream=2,files=files)
        self.assertEqual(write(ctx,1),0);self.assertEqual(files.snapshot()['RD:AUTHORED.DAT'],b'prefix')
        self.assertEqual(write(ctx,2),0);self.assertEqual(files.snapshot()['RD:AUTHORED.DAT'],b'prefix'+struct.pack('<ii',1,2))
        write(ctx,3);run('DAQ_STOP(1,FALSE,s)',context=ctx)
        self.assertEqual(files.snapshot()['RD:AUTHORED.DAT'],b'prefix'+struct.pack('<iii',1,2,3))

    def test_busy_sink_preserves_pending_record_and_ring(self):
        files=rt.MemoryFiles({'RD:AUTHORED.DAT':b''});ctx=setup(stream=2,files=files);write(ctx,1)
        h=rt.FileHandle();files.open(h,'RB','RD:AUTHORED.DAT');before=ctx.acquisition.to_config()
        self.assertEqual(write(ctx,2),3);self.assertEqual(ctx.acquisition.to_config(),before);files.close(h)
        self.assertEqual(write(ctx,2),0);self.assertEqual(files.snapshot()['RD:AUTHORED.DAT'],struct.pack('<ii',1,2))

    def test_sink_limit_preserves_missing_file_and_existing_pipe(self):
        files=rt.MemoryFiles(limit=7);ctx=setup(stream=2,files=files);write(ctx,1);before=ctx.acquisition.to_config()
        self.assertEqual(write(ctx,2),5);self.assertEqual(files.snapshot(),{});self.assertEqual(ctx.acquisition.to_config(),before)

    def test_virtual_volume_capacity_and_permissions_are_respected(self):
        files=rt.DeviceFiles({'RD:':{'capacity':3}});ctx=setup(stream=1,files=files)
        before=ctx.acquisition.to_config();self.assertEqual(write(ctx,1),7)
        self.assertEqual(files.snapshot(),{});self.assertEqual(ctx.acquisition.to_config(),before)
        files=rt.DeviceFiles({'RD:':{'capacity':20,'read_only':True}});ctx=setup(stream=1,files=files)
        self.assertEqual(ctx.acquisition.pipes[1]['starts'],0)

    def test_directory_streaming_stays_under_explicit_root(self):
        with tempfile.TemporaryDirectory() as folder:
            files=rt.DirectoryFiles(folder,devices={'RD':''});ctx=setup(stream=1,files=files)
            self.assertEqual(write(ctx,17),0);self.assertEqual((Path(folder)/'AUTHORED.DAT').read_bytes(),struct.pack('<i',17))
            self.assertEqual(run("DAQ_STOP(1,TRUE,s) DAQ_START(1,DAQ_STREAM,'../',s)",context=ctx)['S'],7)

    def test_final_flush_failure_preserves_active_count_and_pending_data(self):
        files=rt.MemoryFiles({'RD:AUTHORED.DAT':b''});ctx=setup(stream=2,files=files);write(ctx,1)
        h=rt.FileHandle();files.open(h,'RB','RD:AUTHORED.DAT');before=ctx.acquisition.to_config()
        self.assertEqual(run('DAQ_STOP(1,TRUE,s)',context=ctx)['S'],3)
        self.assertEqual(ctx.acquisition.to_config(),before);files.close(h)

    def test_nonfinal_stop_does_not_flush_partial_batch(self):
        files=rt.MemoryFiles();ctx=setup(stream=2,files=files);write(ctx,1)
        self.assertEqual(run("DAQ_START(1,DAQ_STREAM,'RD:',s) DAQ_STOP(1,FALSE,s)",context=ctx)['S'],0)
        self.assertEqual(files.snapshot(),{});self.assertEqual(ctx.acquisition.pipes[1]['starts'],1)


class AcquisitionPersistenceAndScopeTests(unittest.TestCase):
    def test_json_roundtrip_preserves_active_partial_batch_and_data(self):
        ctx=setup(stream=2,files=rt.MemoryFiles());write(ctx,7)
        config=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(config)
        self.assertEqual(json.loads(json.dumps(restored.to_config())),config)
        self.assertEqual(write(restored,8),0);self.assertEqual(restored.files.snapshot()['RD:AUTHORED.DAT'],struct.pack('<ii',7,8))

    def test_live_reader_prevents_context_save(self):
        ctx=setup();p,_=compile_program("OPEN FILE f('RB','PIP:AUTHORED.DAT') PAUSE CLOSE FILE f",decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        with self.assertRaisesRegex(ValueError,'live DAQ'):ctx.to_config()
        p.resume();self.assertIn('acquisition',ctx.to_config())

    def test_invalid_lifecycle_hex_and_schema_are_rejected(self):
        ctx=setup();write(ctx,1);base=json.loads(json.dumps(ctx.acquisition.to_config()))
        for key,value in [('starts',True),('mode',0),('created',False),('data','00'),('data','zz'),('pending','00000000'),('stream_dev','x')]:
            data=deepcopy(base);data['pipes'][0][key]=value
            with self.assertRaises(ValueError):rt.Acquisition.from_config(data)
        data=deepcopy(base);data['pipes'][0]['schema']=['ARRAY',32767,['ARRAY',32767,['INTEGER']]]
        with self.assertRaises(ValueError):rt.Acquisition.from_config(data)

    def test_linked_routine_default_program_is_executing_module(self):
        ctx=context()
        lib=source('LIB','',decl='value,s:INTEGER',routines='ROUTINE capture BEGIN '+REG+' '+START+" value=42 DAQ_WRITE(1,'','value',s) DAQ_STOP(1,FALSE,s) END capture")
        p=translate_project({'lib':lib,'main':source('MAIN','capture',routines='ROUTINE capture FROM LIB')}).instantiate(context=ctx)
        p.run('MAIN');self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<i',42))

    def test_missing_service_alias_outputs_and_counter_guards(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'acquisition'):run('DAQ_CHECKP(1,n,s)')
        p,_=compile_program('flags=77 DAQ_CHECKP(1,flags,flags)',decl=DECL,context=context())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p.snapshot()['FLAGS'],77)
        for body in ('DAQ_CHECKP(1,n,s)','DAQ_STOP(1,TRUE,n)',"DAQ_WRITE(1,'','value',n)"):
            with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO '+body+' ENDFOR',decl='n,s,value:INTEGER')
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_explicit_user_override_remains_available(self):
        self.assertEqual(run('DAQ_WRITE(7)',routines='ROUTINE DAQ_WRITE(x:INTEGER) BEGIN n=x END DAQ_WRITE')['N'],7)

    def test_source_status_can_alias_value_after_snapshot_is_captured(self):
        ctx=setup();data=run("value=17 DAQ_WRITE(1,'','value',value)",decl=DECL,context=ctx)
        self.assertEqual(data['VALUE'],0);self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<i',17))


if __name__=='__main__':unittest.main()
