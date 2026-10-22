"""Authored file comparison, bounded printing and backend integration checks."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run


DECL='f: FILE n,s: INTEGER'
COMPARE="COMPARE_FILE('a','b',f,TRUE,n,s)"


def compare(left=b'one\nold\n',right=b'one\nnew\n',*,ascii_flag=True,initial=None,**options):
    files=rt.MemoryFiles(dict({'a':left,'b':right},**(initial or {})))
    state=run("OPEN FILE f ('W','report') "+COMPARE.replace('TRUE','TRUE' if ascii_flag else 'FALSE')+' CLOSE FILE f',decl=DECL,context=rt.ExecutionContext(files=files),**options)
    return state,files,[json.loads(line) for line in files.snapshot()['report'].splitlines()]


class FileComparisonTests(unittest.TestCase):
    def test_ascii_report_counts_replaced_and_missing_records(self):
        state,files,report=compare(b'one\r\nold\r\n',b'one\nnew\nextra\n')
        self.assertEqual((state['N'],state['S']),(2,0))
        self.assertEqual(report,[{'mode':'ascii','left':'a','right':'b','different_lines':2},{'line':2,'left':'old','right':'new'},{'line':3,'left':None,'right':'extra'}])
        self.assertEqual(files.snapshot()['a'],b'one\r\nold\r\n')

    def test_normalizes_record_terminators_and_final_terminator_presence(self):
        for a,b in ((b'a\r\nb\r',b'a\nb'),(b'a\n',b'a'),(b'',b'')):
            with self.subTest(a=a,b=b):
                state,_,report=compare(a,b);self.assertEqual(state['N'],0);self.assertEqual(len(report),1)

    def test_blank_record_differs_from_empty_file(self):
        state,_,report=compare(b'\n',b'')
        self.assertEqual(state['N'],1);self.assertEqual(report[1],{'line':1,'left':'','right':None})

    def test_records_are_compared_by_number_without_alignment(self):
        state,_,report=compare(b'a\nb\n',b'x\na\nb\n')
        self.assertEqual(state['N'],3);self.assertEqual([row['line'] for row in report[1:]],[1,2,3])

    def test_json_escapes_controls_and_quotes(self):
        _,files,report=compare(b'a\t"\x00\x0b\x0c\n',b'different\n')
        self.assertEqual(report[1]['left'],'a\t"\x00\x0b\x0c')
        self.assertNotIn(b'\x00',files.snapshot()['report']);self.assertIn(b'\\u0000',files.snapshot()['report'])

    def test_binary_first_difference_is_one_based(self):
        state,_,report=compare(b'\x00\xff\x03',b'\x00\xfe\x03',ascii_flag=False)
        self.assertEqual((state['N'],state['S']),(2,0));self.assertEqual(report,[{'mode':'binary','left':'a','right':'b','first_difference':2,'left_byte':255,'right_byte':254}])

    def test_binary_prefix_end_and_equal_inputs(self):
        for a,b,expected in ((b'ab',b'abc',3),(b'abc',b'ab',3),(b'',b'x',1),(b'',b'',0),(b'abc',b'abc',0)):
            with self.subTest(a=a,b=b):
                state,_,report=compare(a,b,ascii_flag=False);self.assertEqual(state['N'],expected)
                if not expected: self.assertIsNone(report[0]['left_byte']);self.assertIsNone(report[0]['right_byte'])

    def test_binary_boundary_across_work_blocks(self):
        state,_,report=compare(b'a'*4096+b'x',b'a'*4096+b'y',ascii_flag=False)
        self.assertEqual(state['N'],4097);self.assertEqual(report[0]['left_byte'],ord('x'))

    def test_append_and_custom_report_terminator(self):
        files=rt.MemoryFiles({'a':'x','b':'y','report':'prefix\n'})
        state=run("SET_FILE_ATR(f,ATR_EOL,124) OPEN FILE f ('A','report') "+COMPARE+' CLOSE FILE f',decl=DECL,context=rt.ExecutionContext(files=files))
        data=files.snapshot()['report'];self.assertTrue(data.startswith(b'prefix\n'));self.assertTrue(data.endswith(b'|'))
        records=[json.loads(row) for row in data[len(b'prefix\n'):].split(b'|') if row]
        self.assertEqual((state['N'],len(records)),(1,2))

    def test_report_overwrites_at_existing_cursor(self):
        files=rt.MemoryFiles({'a':'x','b':'y','report':'prefix'})
        run("OPEN FILE f ('RW','report') SET_FILE_POS(f,-1,s) "+COMPARE+' CLOSE FILE f',decl=DECL,context=rt.ExecutionContext(files=files))
        self.assertTrue(files.snapshot()['report'].startswith(b'prefix{"mode":"ascii"'))

    def test_file_handle_alias_uses_shared_cursor(self):
        files=rt.MemoryFiles({'a':'x','b':'x'})
        state=run("OPEN FILE f ('W','report') other=f COMPARE_FILE('a','b',other,TRUE,n,s) cursor=GET_FILE_POS(f) CLOSE FILE f",decl=DECL+' other: FILE cursor: INTEGER',context=rt.ExecutionContext(files=files))
        self.assertEqual(state['CURSOR'],len(files.snapshot()['report']));self.assertEqual(state['N'],0)

    def test_missing_inputs_preserve_count_and_report(self):
        for missing in ('a','b'):
            with self.subTest(missing=missing):
                files=rt.MemoryFiles({name:'x' for name in ('a','b') if name!=missing})
                state=run("n=7 OPEN FILE f ('W','report') "+COMPARE,decl=DECL,context=rt.ExecutionContext(files=files))
                self.assertEqual((state['N'],state['S']),(7,1));self.assertEqual(files.snapshot()['report'],b'')

    def test_busy_input_and_output_alias_return_status_three(self):
        for target in ('a','report'):
            with self.subTest(target=target):
                files=rt.MemoryFiles({'a':'x','b':'y'})
                body=f"n=7 OPEN FILE f ('RW','{target}') "+("OPEN FILE other ('R','a') " if target=='report' else '')+COMPARE
                state=run(body,decl=DECL+' other: FILE',context=rt.ExecutionContext(files=files))
                self.assertEqual((state['N'],state['S']),(7,3));self.assertEqual(files.snapshot()['a'],b'x')

    def test_invalid_ascii_and_small_report_capacity_preserve_outputs(self):
        for files in (rt.MemoryFiles({'a':b'\xff','b':b'x'}),rt.MemoryFiles({'a':'x','b':'y'},limit=16)):
            with self.subTest(files=files):
                p,_=compile_program("n=7 s=8 OPEN FILE f ('W','report') "+COMPARE,decl=DECL,context=rt.ExecutionContext(files=files))
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,8));self.assertEqual(files.snapshot()['report'],b'')
                self.assertEqual(p._state.values['F'].position,0)

    def test_closed_and_read_only_results_fail_before_input_access(self):
        for body in (COMPARE,"OPEN FILE f ('R','report') "+COMPARE):
            with self.subTest(body=body):
                p,_=compile_program('n=7 s=8 '+body,decl=DECL,context=rt.ExecutionContext(files=rt.MemoryFiles({'report':'retained'})))
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,8))

    def test_foreign_result_backend_is_rejected(self):
        files=rt.MemoryFiles({'a':'x','b':'y'});other=rt.MemoryFiles();handle=rt.FileHandle();other.open(handle,'W','report')
        p,_=compile_program('n=7 s=8 '+COMPARE,decl=DECL,context=rt.ExecutionContext(files=files));p._state.values['F']=handle
        with self.assertRaisesRegex(rt.KarelRuntimeError,'input backend'): p.run()
        self.assertEqual(other.snapshot()['report'],b'');self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,8))

    def test_comparison_budget_failure_does_not_commit_report(self):
        files=rt.MemoryFiles({'a':'x\nx\n','b':'y\ny\n'})
        p,_=compile_program("n=7 s=8 OPEN FILE f ('W','report') "+COMPARE,decl=DECL,context=rt.ExecutionContext(files=files))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'): p.run(max_steps=4)
        self.assertEqual(files.snapshot()['report'],b'');self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,8))


class FilePrintingTests(unittest.TestCase):
    def test_original_ascii_bytes_are_recorded_without_added_newline(self):
        files=rt.MemoryFiles({'message':b'ready\r\nnext\nend'})
        p,_=compile_program("PRINT_FILE('message',FALSE,s)",context=rt.ExecutionContext(files=files));state=p.run()
        self.assertEqual(state['S'],0);self.assertEqual([row['text'] for row in p.write_requests],['ready\r\nnext\nend'])
        self.assertEqual(files.snapshot()['message'],b'ready\r\nnext\nend')

    def test_both_nowait_values_use_synchronous_callback_chunks(self):
        text='x'*254+'y'*47
        for flag in ('TRUE','FALSE'):
            with self.subTest(flag=flag):
                output=[];p,_=compile_program(f"PRINT_FILE('message',{flag},s)",context=rt.ExecutionContext(files=rt.MemoryFiles({'message':text})),write=output.append)
                self.assertEqual(p.run()['S'],0);self.assertEqual(output,['x'*254,'y'*47])

    def test_empty_file_succeeds_without_output_request(self):
        p,_=compile_program("PRINT_FILE('message',FALSE,s)",context=rt.ExecutionContext(files=rt.MemoryFiles({'message':''})))
        self.assertEqual(p.run()['S'],0);self.assertEqual(p.write_requests,())

    def test_missing_and_busy_inputs_produce_no_output(self):
        for body,expected in (("PRINT_FILE('message',FALSE,s)",1),("OPEN FILE f ('R','message') PRINT_FILE('message',FALSE,s)",3)):
            with self.subTest(body=body):
                p,_=compile_program(body,decl=DECL,context=rt.ExecutionContext(files=rt.MemoryFiles({'message':'text'} if expected==3 else {})))
                self.assertEqual(p.run()['S'],expected);self.assertEqual(p.write_requests,())

    def test_entire_ascii_input_is_validated_before_output(self):
        p,_=compile_program("s=7 PRINT_FILE('message',FALSE,s)",context=rt.ExecutionContext(files=rt.MemoryFiles({'message':b'x'*300+b'\xff'})))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['S'],7);self.assertEqual(p.write_requests,())

    def test_callback_failure_preserves_status_and_earlier_output_effect(self):
        output=[]
        def sink(text):
            if output: raise OSError('authored sink failure')
            output.append(text)
        p,_=compile_program("s=7 PRINT_FILE('message',FALSE,s)",context=rt.ExecutionContext(files=rt.MemoryFiles({'message':'x'*300})),write=sink)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'sink failure'): p.run()
        self.assertEqual((p.snapshot()['S'],len(output)),(7,1));self.assertEqual([row['adapter_outcome'] for row in p.write_requests],['callback_completed','callback_failed'])

    def test_print_budget_retains_only_completed_chunks(self):
        p,_=compile_program("s=7 PRINT_FILE('message',FALSE,s)",context=rt.ExecutionContext(files=rt.MemoryFiles({'message':'x'*300})))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'): p.run(max_steps=3)
        self.assertEqual([row['text'] for row in p.write_requests],['x'*254]);self.assertEqual(p.snapshot()['S'],7)

    def test_sticky_abort_stops_printing_without_writing_success_status(self):
        p=None;output=[]
        def sink(text): output.append(text);p._state.abort(99)
        p,_=compile_program("s=7 PRINT_FILE('message',FALSE,s)",context=rt.ExecutionContext(files=rt.MemoryFiles({'message':'x'*300})),write=sink)
        with self.assertRaises(rt.KarelAbort): p.run()
        self.assertEqual((len(output),p.snapshot()['S']),(1,7))
        with self.assertRaises(rt.KarelAbort): p.run()


class DirectoryComparisonTests(unittest.TestCase):
    def test_directory_inputs_are_read_fresh_and_report_is_buffered_until_close(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'a').write_bytes(b'old');(root/'b').write_bytes(b'new')
            files=rt.DirectoryFiles(root);files.files['a']=bytearray(b'stale')
            p,_=compile_program("OPEN FILE f ('W','report') "+COMPARE,decl=DECL,context=rt.ExecutionContext(files=files));state=p.run()
            self.assertEqual(state['N'],1);self.assertFalse((root/'report').exists())
            self.assertEqual(json.loads(files.snapshot()['report'].splitlines()[1])['left'],'old')
            files.close(p._state.values['F']);self.assertTrue((root/'report').is_file())
            self.assertEqual((root/'a').read_bytes(),b'old')

    def test_mapped_devices_work_for_compare_and_print(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'a').write_bytes(b'x');(root/'b').write_bytes(b'y')
            files=rt.DirectoryFiles(root,devices={'MD':''});ctx=rt.ExecutionContext(files=files);output=[]
            state=run("OPEN FILE f ('W','MD:report') COMPARE_FILE('MD:a','MD:b',f,FALSE,n,s) CLOSE FILE f PRINT_FILE('MD:a',FALSE,s)",decl=DECL,context=ctx,write=output.append)
            self.assertEqual((state['N'],state['S'],output),(1,0,['x']))

    def test_invalid_paths_fail_without_comparison_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'b').write_bytes(b'y');files=rt.DirectoryFiles(root)
            for name in ('../outside','X:b','/outside'):
                with self.subTest(name=name):
                    p,_=compile_program(f"n=7 s=8 OPEN FILE f ('W','report') COMPARE_FILE('{name}','b',f,TRUE,n,s)",decl=DECL,context=rt.ExecutionContext(files=files))
                    with self.assertRaises(rt.KarelRuntimeError): p.run()
                    self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,8));self.assertEqual(files.snapshot()['report'],b'')
                    files.close(p._state.values['F'])

    def test_oversized_named_read_is_bounded_and_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'a').write_bytes(b'x'*9);files=rt.DirectoryFiles(root,limit=8)
            with self.assertRaises(ValueError): files.read_named('a')

    def test_interactive_flush_failure_preserves_buffer_cursor_and_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'a').write_bytes(b'x');(root/'b').write_bytes(b'y');(root/'report').write_bytes(b'prefix')
            files=rt.DirectoryFiles(root);p,_=compile_program("n=7 s=8 SET_FILE_ATR(f,ATR_IA) OPEN FILE f ('RW','report') SET_FILE_POS(f,-1,s) s=8 "+COMPARE,decl=DECL,context=rt.ExecutionContext(files=files))
            with patch.object(files,'flush',side_effect=rt.KarelRuntimeError('authored flush failure')):
                with self.assertRaisesRegex(rt.KarelRuntimeError,'flush failure'): p.run()
            self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,8));self.assertEqual(files.snapshot()['report'],b'prefix')
            self.assertEqual(p._state.values['F'].position,6);self.assertEqual((root/'report').read_bytes(),b'prefix')

    @unittest.skipUnless(os.name=='nt','Windows path aliases')
    def test_case_alias_of_open_input_is_busy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'a.txt').write_bytes(b'x');files=rt.DirectoryFiles(root);handle=rt.FileHandle();files.open(handle,'R','a.txt')
            self.assertEqual(files.read_named('A.TXT'),(3,None));files.close(handle)


class FileOperationOwnershipTests(unittest.TestCase):
    def test_source_arity_types_and_output_guards(self):
        for body in ("COMPARE_FILE('a','b',f,TRUE,n)","COMPARE_FILE('a','b','report',TRUE,n,s)","COMPARE_FILE('a','b',f,1,n,s)","COMPARE_FILE('a','b',f,TRUE,x,s)","PRINT_FILE('a',1,s)","PRINT_FILE('a',FALSE,0)"):
            with self.subTest(body=body),self.assertRaises(TranslationError): compile_program(body,decl=DECL+' x: REAL')

    def test_output_alias_fails_before_backend_access(self):
        p,_=compile_program("n=7 COMPARE_FILE('a','b',f,TRUE,n,n)",decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): p.run()
        self.assertEqual(p.snapshot()['N'],7)

    def test_missing_service_preserves_outputs(self):
        for body in (COMPARE,"PRINT_FILE('a',FALSE,s)"):
            with self.subTest(body=body):
                p,_=compile_program('n=7 s=8 '+body,decl=DECL)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'files'): p.run()
                self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,8))

    def test_direct_transitive_and_handler_for_counter_guards(self):
        for body,routines in ((f'FOR n=1 TO 2 DO {COMPARE} ENDFOR',''),('FOR n=1 TO 2 DO helper() ENDFOR',f'ROUTINE helper BEGIN {COMPARE} END helper'),("FOR s=1 TO 2 DO PRINT_FILE('a',FALSE,s) ENDFOR",''),(f'CONDITION[1]: WHEN TRUE DO {COMPARE} ENDCONDITION FOR n=1 TO 2 DO ENDFOR','')):
            with self.subTest(body=body),self.assertRaises(TranslationError): compile_program(body,decl=DECL,routines=routines)

    def test_argument_functions_evaluate_once_before_comparison(self):
        files=rt.MemoryFiles({'a':'x','b':'x'});ctx=rt.ExecutionContext(files=files)
        routines="ROUTINE first: STRING[1] BEGIN trace=trace+'A' RETURN 'a' END first ROUTINE second: STRING[1] BEGIN trace=trace+'B' RETURN 'b' END second"
        state=run("trace='' OPEN FILE f ('W','report') COMPARE_FILE(first(),second(),f,TRUE,n,s)",decl=DECL+' trace: STRING[4]',routines=routines,context=ctx)
        self.assertEqual((state['TRACE'],state['N'],state['S']),('AB',0,0))

    def test_user_procedures_keep_precedence(self):
        for name in ('COMPARE_FILE','PRINT_FILE'):
            with self.subTest(name=name): self.assertEqual(run(f'{name}(7)',routines=f'ROUTINE {name}(value: INTEGER) BEGIN n=value END {name}')['N'],7)

    def test_report_policy_and_value_free_service_records(self):
        p,result=compile_program("PRINT_FILE('a',FALSE,s)",context=rt.ExecutionContext(files=rt.MemoryFiles({'a':'text'})));p.run()
        self.assertFalse(result.report['file_comparison_policy']['controller_validated'])
        self.assertTrue(all(set(row)=={'operation','line','outcome'} for row in p.service_requests))

    def test_print_effect_propagates_through_routines(self):
        routines="ROUTINE emit BEGIN PRINT_FILE('a',FALSE,s) END emit ROUTINE relay BEGIN emit() END relay"
        output=[];p,result=compile_program('relay()',routines=routines,context=rt.ExecutionContext(files=rt.MemoryFiles({'a':'text'})),write=output.append)
        p.run();self.assertEqual(output,['text'])
        for name in ('EMIT','RELAY'): self.assertTrue(result.report['routine_effects'][name]['potential_output_requests'])

    def test_named_memory_reads_are_detached(self):
        files=rt.MemoryFiles({'a':'text'});code,data=files.read_named('a');files.files['a'][0]=ord('n')
        self.assertEqual((code,data),(0,b'text'));self.assertEqual(files.read_named('missing'),(1,None))


if __name__=='__main__': unittest.main()
