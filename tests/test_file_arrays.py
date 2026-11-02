"""Authored indexed FILE storage, borrowed interfaces and transport checks."""
import struct
import tempfile
import unittest
from pathlib import Path

from karel2py import runtime as rt, translate, translate_project
from tests.test_extended_services import compile_program
from tests.test_file_cancellation import serial
from tests.test_project_scheduler import source

DECL='streams:ARRAY[2] OF FILE n,m,s,entry:INTEGER before,during,after:BOOLEAN'
USE="ROUTINE use(v:ARRAY OF FILE) BEGIN OPEN FILE v[2]('WO','out') WRITE v[2](17) CLOSE FILE v[2] END use"


def build(body='',**options):
    return compile_program(body,decl=options.pop('decl',DECL),context=options.pop('context',rt.ExecutionContext(files=rt.MemoryFiles())),**options)


def handles(program):return program._state.raw('STREAMS').values


class FileArrayStorageTests(unittest.TestCase):
    def test_fresh_elements_are_distinct_closed_descriptors(self):
        p,_=build();a,b=handles(p);self.assertIsNot(a,b);self.assertIs(type(a),rt.FileHandle);self.assertIsNone(a.owner);self.assertIsNone(b.owner)
    def test_separate_roots_have_independent_descriptors(self):
        p,_=build(decl='streams,other:ARRAY[2] OF FILE');self.assertTrue(set(map(id,handles(p))).isdisjoint(map(id,p._state.raw('OTHER').values)))
    def test_program_instances_have_independent_descriptors(self):
        p,_=build();q=type(p)();self.assertIsNot(handles(p)[0],handles(q)[0])
    def test_two_open_streams_have_independent_contents(self):
        p,_=build("OPEN FILE streams[1]('WO','one') OPEN FILE streams[2]('WO','two') WRITE streams[1](7) WRITE streams[2](9) CLOSE FILE streams[2] CLOSE FILE streams[1]")
        p.run();self.assertEqual(p._state.execution.files.snapshot(),{'one':b' 7','two':b' 9'})
    def test_text_read_uses_selected_stream(self):
        p,_=build("OPEN FILE streams[2]('RO','in') READ streams[2](n,CR) CLOSE FILE streams[2]",context=rt.ExecutionContext(files=rt.MemoryFiles({'in':'17\n'})));self.assertEqual(p.run()['N'],17);self.assertIsNone(handles(p)[0].name)
    def test_binary_roundtrip(self):
        p,_=build("OPEN FILE streams[1]('WB','data') WRITE streams[1](17,-9) CLOSE FILE streams[1] OPEN FILE streams[2]('RB','data') READ streams[2](n,m) CLOSE FILE streams[2]")
        v=p.run();self.assertEqual((v['N'],v['M']),(17,-9));self.assertEqual(p._state.execution.files.snapshot()['data'],struct.pack('<ii',17,-9))
    def test_initialization_queries_follow_one_cell(self):
        p,_=build("before=UNINIT(streams[1]) OPEN FILE streams[1]('WO','out') during=UNINIT(streams[1]) after=UNINIT(streams[2])");v=p.run();self.assertEqual((v['BEFORE'],v['DURING'],v['AFTER']),(True,False,True))
    def test_closed_cell_becomes_uninitialized(self):
        p,_=build("OPEN FILE streams[2]('WO','out') CLOSE FILE streams[2] after=UNINIT(streams[2])");self.assertIs(p.run()['AFTER'],True)
    def test_failed_open_keeps_other_stream_live(self):
        p,_=build("OPEN FILE streams[1]('WO','out') OPEN FILE streams[2]('RO','missing')")
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIsNotNone(handles(p)[0].owner);self.assertIsNone(handles(p)[1].owner)
    def test_read_failure_preserves_selected_cursor_and_destinations(self):
        p,_=build("OPEN FILE streams[1]('RB','in') n=7 m=9 READ streams[1](n,m) s=IO_STATUS(streams[1])",context=rt.ExecutionContext(files=rt.MemoryFiles({'in':struct.pack('<i',17)})))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        v=p.snapshot();self.assertEqual((v['N'],v['M']),(7,9));self.assertEqual((handles(p)[0].position,handles(p)[0].status),(0,1))
    def test_indexed_cursor_queries_and_seek(self):
        p,_=build("OPEN FILE streams[2]('RB','in') READ streams[2](n) m=GET_FILE_POS(streams[2]) SET_FILE_POS(streams[2],0,s) CLOSE FILE streams[2]",context=rt.ExecutionContext(files=rt.MemoryFiles({'in':struct.pack('<i',17)})))
        v=p.run();self.assertEqual((v['N'],v['M'],v['S']),(17,4,0));self.assertEqual(handles(p)[1].position,0)
    def test_bytes_left_uses_selected_input_cursor(self):
        p,_=build("OPEN FILE streams[2]('RB','in') READ streams[2](n) m=BYTES_LEFT(streams[2]) CLOSE FILE streams[2]",context=rt.ExecutionContext(files=rt.MemoryFiles({'in':struct.pack('<ii',17,19)})));v=p.run();self.assertEqual((v['N'],v['M']),(17,4))
    def test_write_handle_precedes_value_effect(self):
        routines='ROUTINE pick:INTEGER BEGIN n=2 RETURN 17 END pick'
        p,_=build("n=1 OPEN FILE streams[1]('WO','out') WRITE streams[n](pick) CLOSE FILE streams[1]",routines=routines);p.run();self.assertEqual(p._state.execution.files.snapshot()['out'],b' 17');self.assertIsNone(handles(p)[1].name)
    def test_three_dimensional_storage(self):
        p,_=build("OPEN FILE streams[2,1,2]('WO','out') CLOSE FILE streams[2,1,2]",decl='streams:ARRAY[2,1,2] OF FILE');self.assertEqual(p.run()['STREAMS'][1][0][1]['file'],'out')
    def test_out_of_range_selector_has_no_open_effect(self):
        p,_=build("OPEN FILE streams[3]('WO','out')")
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.execution.files.snapshot(),{});self.assertTrue(all(h.owner is None for h in handles(p)))
    def test_indexed_file_attributes_remain_per_descriptor(self):
        p,_=build('SET_FILE_ATR(streams[2],ATR_REVERSE)');p.run();self.assertFalse(handles(p)[0].reverse);self.assertTrue(handles(p)[1].reverse)
    def test_rooted_filesystem_transport(self):
        with tempfile.TemporaryDirectory(prefix='karel-file-arrays-') as folder:
            p,_=build("OPEN FILE streams[2]('WO','out') WRITE streams[2]('ready',CR) CLOSE FILE streams[2]",context=rt.ExecutionContext(files=rt.DirectoryFiles(folder)));p.run();self.assertEqual((Path(folder)/'out').read_bytes(),b'ready\n')
    def test_named_file_alias(self):
        p,_=build('before=UNINIT(streams[1])',prefix='TYPE file_t=FILE',decl=DECL.replace('OF FILE','OF file_t'));self.assertIs(p.run()['BEFORE'],True)
    def test_named_array_type(self):
        p,_=build('before=UNINIT(streams[2])',prefix='TYPE streams_t=ARRAY[2] OF FILE',decl=DECL.replace('ARRAY[2] OF FILE','streams_t'));self.assertIs(p.run()['BEFORE'],True);self.assertEqual(p._state.types['STREAMS'][-1],'STREAMS_T')
    def test_multidimensional_storage(self):
        p,_=build("OPEN FILE streams[2,3]('WO','out') WRITE streams[2,3](7) CLOSE FILE streams[2,3]",decl='streams:ARRAY[2,3] OF FILE');v=p.run();self.assertEqual(v['STREAMS'][1][2]['position'],2);self.assertEqual(len({id(h) for h in handles(p)}),6)
    def test_chained_indexes_use_flat_storage(self):
        p,_=build("OPEN FILE streams[2][1]('WO','out') WRITE streams[2][1](7) CLOSE FILE streams[2][1]",decl='streams:ARRAY[2,2] OF FILE');self.assertEqual(p.run()['STREAMS'][1][0]['position'],2)
    def test_nested_named_components(self):
        p,_=build("OPEN FILE streams[2,1]('WO','out') CLOSE FILE streams[2][1]",prefix='TYPE row_t=ARRAY[2] OF FILE bank_t=ARRAY[2] OF row_t',decl='streams:bank_t');self.assertEqual(p.run()['STREAMS'][1][0]['file'],'out')
    def test_supplied_wildcard_storage(self):
        text="PROGRAM T VAR streams:ARRAY[*] OF FILE BEGIN OPEN FILE streams[3]('WO','out') CLOSE FILE streams[3] END T"
        r=translate(text,array_shapes={'streams':(3,)});ns={'__name__':'file_array_shape'};exec(r.python_source,ns);p=ns['Program'](context=rt.ExecutionContext(files=rt.MemoryFiles()));self.assertEqual(len(p.run()['STREAMS']),3)
    def test_open_selector_is_captured_once(self):
        routines='ROUTINE pick:INTEGER BEGIN n=n+1 RETURN 2 END pick'
        p,_=build("n=0 OPEN FILE streams[pick]('WO','out') CLOSE FILE streams[2]",routines=routines);self.assertEqual(p.run()['N'],1)
    def test_read_handle_is_captured_before_target_selector(self):
        routines='ROUTINE pick:INTEGER BEGIN n=2 RETURN 1 END pick'
        p,_=build("n=1 OPEN FILE streams[1]('RO','in') READ streams[n](data[pick],CR) CLOSE FILE streams[1]",decl=DECL+' data:ARRAY[1] OF INTEGER',routines=routines,context=rt.ExecutionContext(files=rt.MemoryFiles({'in':'17\n'})));v=p.run();self.assertEqual((v['N'],v['DATA']),(2,[17]));self.assertIsNone(handles(p)[1].name)
    def test_report_exposes_descriptor_policy(self):
        _,r=build();self.assertFalse(r.report['file_array_policy']['controller_validated']);self.assertEqual(r.report['file_array_policy']['guide'],'docs/file-arrays.md');self.assertIn('reference-only FILE ARRAY',r.report['features'])


class FileArrayInterfaceTests(unittest.TestCase):
    def test_generic_array_formal_borrows_storage(self):
        p,_=build('use(streams)',routines=USE);original=handles(p)[1];p.run();self.assertIs(handles(p)[1],original);self.assertEqual(original.position,3)
    def test_generic_rank_two_formal(self):
        routines="ROUTINE use(v:ARRAY[*,*] OF FILE) BEGIN OPEN FILE v[2,1]('WO','out') CLOSE FILE v[2,1] END use"
        p,_=build('use(streams)',decl='streams:ARRAY[2,2] OF FILE',routines=routines);self.assertEqual(p.run()['STREAMS'][1][0]['file'],'out')
    def test_named_array_formal(self):
        p,_=build('use(streams)',prefix='TYPE streams_t=ARRAY[2] OF FILE',decl='streams:streams_t',routines=USE.replace('ARRAY OF FILE','streams_t'));self.assertEqual(p.run()['STREAMS'][1]['position'],3)
    def test_generic_rank_two_borrows_nested_named_storage(self):
        routines="ROUTINE use(v:ARRAY[*,*] OF FILE) BEGIN OPEN FILE v[2,1]('WO','out') CLOSE FILE v[2,1] END use"
        p,_=build('use(streams)',prefix='TYPE row_t=ARRAY[2] OF FILE',decl='streams:ARRAY[2] OF row_t',routines=routines);self.assertEqual(p.run()['STREAMS'][1][0]['file'],'out')
    def test_byname_mismatched_rank_fails_before_open(self):
        p,_=build("use(BYNAME('T','STREAMS',entry))",decl='streams:ARRAY[2,2] OF FILE entry:INTEGER',routines=USE)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.execution.files.snapshot(),{})
    def test_named_component_row_is_borrowed(self):
        p,_=build('use(streams[2])',prefix='TYPE row_t=ARRAY[2] OF FILE',decl='streams:ARRAY[2] OF row_t',routines=USE);self.assertEqual(p.run()['STREAMS'][1][1]['position'],3)
    def test_scalar_file_formal_borrows_array_cell(self):
        routines="ROUTINE use(v:FILE) BEGIN OPEN FILE v('WO','out') WRITE v(17) CLOSE FILE v END use"
        p,_=build('use(streams[1])',routines=routines);self.assertEqual(p.run()['STREAMS'][0]['position'],3)
    def test_repeated_formals_alias_original_stream(self):
        routines="ROUTINE use(a,b:ARRAY OF FILE) BEGIN OPEN FILE a[1]('WO','out') WRITE b[1](17) CLOSE FILE b[1] END use"
        p,_=build('use(streams,streams)',routines=routines);self.assertEqual(p.run()['STREAMS'][0]['position'],3)
    def test_byname_array_formal(self):
        p,_=build("use(BYNAME('T','STREAMS',entry))",routines=USE);self.assertEqual(p.run()['STREAMS'][1]['position'],3)
    def test_byname_scalar_cell_formal(self):
        routines="ROUTINE use(v:FILE) BEGIN OPEN FILE v('WO','out') CLOSE FILE v END use"
        p,_=build("use(BYNAME('T','STREAMS[2]',entry))",routines=routines);self.assertEqual(p.run()['STREAMS'][1]['file'],'out')
    def test_external_byname_binding_borrows_live_array(self):
        owner,_=build();value=owner._state.raw('STREAMS');ctx=rt.ExecutionContext(files=rt.MemoryFiles());ctx.variables.bind('CACHE','STREAMS',rt.Reference(value.spec,{'value':value},'value'))
        p,_=build("use(BYNAME('CACHE','STREAMS',entry))",routines=USE,context=ctx);p.run();self.assertIs(handles(owner)[1],value.values[1]);self.assertEqual(value.values[1].position,3)
    def test_fresh_local_arrays_on_each_call(self):
        routines="ROUTINE use VAR local_streams:ARRAY[2] OF FILE BEGIN before=UNINIT(local_streams[1]) OPEN FILE local_streams[1]('WO','out') CLOSE FILE local_streams[1] END use"
        p,_=build('use use',routines=routines);self.assertTrue(p.run()['BEFORE']);self.assertEqual(p._state.local_frames,[])
    def test_linked_routine_borrows_callers_array(self):
        files={'main':source('MAIN','use(streams)',decl='streams:ARRAY[2] OF FILE',routines='ROUTINE use(v:ARRAY OF FILE) FROM LIB'), 'lib':source('LIB','',routines=USE)}
        project=translate_project(files).instantiate(context=rt.ExecutionContext(files=rt.MemoryFiles()));project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['STREAMS'][1]['position'],3)
    def test_source_linked_import_retains_same_array(self):
        files={'owner':source('OWNER','',decl='streams:ARRAY[2] OF FILE'), 'main':source('MAIN',"OPEN FILE streams[2]('WO','out') WRITE streams[2](17) CLOSE FILE streams[2]",decl='streams FROM OWNER:ARRAY[2] OF FILE')}
        project=translate_project(files).instantiate(context=rt.ExecutionContext(files=rt.MemoryFiles()));project.run('MAIN');a=project.programs['MAIN']._state.raw('STREAMS');b=project.programs['OWNER']._state.raw('STREAMS');self.assertIs(a,b);self.assertEqual(b.values[1].position,3)


class FileArrayCancellationTests(unittest.TestCase):
    def pending(self):
        bank,ctx=serial(b'17 ')
        body="OPEN FILE streams[2]('RO','P2:') n=7 READ streams[2](n,CR) s=IO_STATUS(streams[2]) CLOSE FILE streams[2]"
        project=translate_project({'main':source('MAIN',body,decl=DECL)}).instantiate(context=ctx)
        task=project.programs['MAIN'];project.scheduler.start('MAIN')
        for _ in range(80):
            project.scheduler.step()
            if handles(task)[1]._read_operation is not None:return project,task,bank
        raise AssertionError('indexed READ did not become pending')
    def test_pause_resume_retains_original_descriptor(self):
        project,task,bank=self.pending();handle=handles(task)[1];task.pause()
        for _ in range(80):
            project.scheduler.step()
            if task.task_state=='paused':break
        self.assertEqual(task.task_state,'paused');self.assertIs(handles(task)[1],handle);bank.feed(2,b'\n');project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(task.snapshot()['N'],17);self.assertIsNone(handle._read_operation)
    def test_stop_unwinds_pending_read_without_publication(self):
        project,task,bank=self.pending();handle=handles(task)[1];project.scheduler.stop('MAIN');self.assertEqual(task.task_state,'stopped');self.assertEqual(task.snapshot()['N'],7);self.assertEqual(bank.snapshot()[2]['input'],b'17 ');self.assertIsNone(handle._read_operation);bank.close(handle)
    def test_cancel_captures_index_once(self):
        routines='ROUTINE pick:INTEGER BEGIN m=m+1 RETURN 2 END pick'
        p,_=build("m=0 OPEN FILE streams[2]('WO','out') CANCEL FILE streams[pick] CLOSE FILE streams[2]",routines=routines);self.assertEqual(p.run()['M'],1)
    def test_serial_cancel_preserves_array_descriptor_and_input(self):
        bank,ctx=serial(b'17 ')
        def sleeper(_):rt.cancel_file(p._state,handles(p)[1])
        p,_=build("OPEN FILE streams[2]('RO','P2:') n=7 READ streams[2](n,CR) s=IO_STATUS(streams[2]) CLOSE FILE streams[2]",context=ctx,sleep=sleeper)
        v=p.run();self.assertEqual((v['N'],v['S']),(7,6));self.assertEqual(bank.snapshot()[2]['input'],b'17 ');self.assertIsNone(handles(p)[1]._read_operation)
    def test_handler_cancels_indexed_stream(self):
        bank,ctx=serial(b'17 ')
        def sleeper(_):p._state.set('BEFORE',True)
        body="before=FALSE CONDITION[1]: WHEN before DO CANCEL FILE streams[2] ENDCONDITION ENABLE CONDITION[1] OPEN FILE streams[2]('RO','P2:') n=7 READ streams[2](n,CR) s=IO_STATUS(streams[2]) CLOSE FILE streams[2]"
        p,_=build(body,context=ctx,sleep=sleeper);v=p.run();self.assertEqual((v['N'],v['S']),(7,6));self.assertEqual(bank._pending,{})
    def test_idle_cancel_retains_other_stream(self):
        p,_=build("OPEN FILE streams[1]('WO','one') OPEN FILE streams[2]('WO','two') CANCEL FILE streams[2] WRITE streams[1](7) CLOSE FILE streams[1] CLOSE FILE streams[2]");p.run();self.assertEqual(p._state.execution.files.snapshot()['one'],b' 7')
