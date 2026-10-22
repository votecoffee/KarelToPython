"""Authored task requests, scoped error severities and byte-accurate FILE reads."""
import json
from pathlib import Path
import tempfile
import unittest

from karel2py import translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


class TaskRequestTests(unittest.TestCase):
    def test_named_self_pause_obeys_handler_and_sets_status_first(self):
        tasks=rt.TaskRegistry();ctx=rt.ExecutionContext(tasks=tasks)
        p,_=compile_program("CONDITION[1]: WHEN PAUSE DO NOPAUSE,n=s ENDCONDITION ENABLE CONDITION[1] PAUSE_TASK('T',FALSE,FALSE,s)",context=ctx)
        tasks.bind('T',p)
        self.assertEqual(p.run(),{'N':0,'S':0})

    def test_named_self_abort_obeys_noabort(self):
        tasks=rt.TaskRegistry();ctx=rt.ExecutionContext(tasks=tasks)
        p,_=compile_program("CONDITION[1]: WHEN ABORT DO NOABORT,n=7 ENDCONDITION ENABLE CONDITION[1] ABORT_TASK('T',TRUE,FALSE,s)",context=ctx)
        tasks.bind('T',p);self.assertEqual(p.run(),{'N':7,'S':0});self.assertIsNone(p.abort_info)

    def test_named_self_abort_unwinds_and_is_sticky(self):
        tasks=rt.TaskRegistry();p,_=compile_program("work()",routines="ROUTINE work BEGIN ABORT_TASK('T',TRUE,FALSE,s) END work",context=rt.ExecutionContext(tasks=tasks))
        tasks.bind('T',p)
        with self.assertRaises(rt.KarelAbort): p.run()
        self.assertEqual((p.snapshot()['S'],p._state.call_depth),(0,0))
        with self.assertRaises(rt.KarelAbort): p.run()

    def test_standalone_remote_abort_runs_paused_handler(self):
        child,_=compile_program('n=0 CONDITION[1]: WHEN ABORT DO NOABORT,n=7 ENDCONDITION ENABLE CONDITION[1] PAUSE s=n')
        with self.assertRaises(rt.KarelPause): child.run()
        tasks=rt.TaskRegistry();tasks.bind('child',child)
        self.assertEqual(run("ABORT_TASK('child',FALSE,FALSE,s)",context=rt.ExecutionContext(tasks=tasks))['S'],0)
        self.assertTrue(child._state._abort_requested);self.assertEqual(child.resume()['S'],7)

    def test_scheduled_remote_abort_runs_paused_handler(self):
        instance=translate_project({'a':source('MAIN',"RUN_TASK('CHILD',0,FALSE,FALSE,0,s) DELAY 10 ABORT_TASK('CHILD',TRUE,FALSE,s) n=8"),
            'b':source('CHILD','CONDITION[1]: WHEN ABORT DO NOABORT,n=7 ENDCONDITION ENABLE CONDITION[1] PAUSE s=n')}).instantiate()
        result=instance.run('MAIN');self.assertEqual((result['CHILD']['state'],result['CHILD']['values']['S'],result['MAIN']['values']['N']),('completed',7,8))

    def test_numeric_remote_abort_uses_same_handler_path(self):
        instance=translate_project({'a':source('MAIN',"RUN_TASK('CHILD',0,FALSE,FALSE,0,s) DELAY 10 ABORT PROGRAM[2] n=8"),
            'b':source('CHILD','CONDITION[1]: WHEN ABORT DO NOABORT,n=7 ENDCONDITION ENABLE CONDITION[1] PAUSE s=n')}).instantiate()
        self.assertEqual(instance.run('MAIN')['CHILD']['values']['S'],7)

    def test_named_remote_pause_wakes_sleep_and_can_be_suppressed(self):
        instance=translate_project({'a':source('MAIN',"RUN_TASK('CHILD',0,FALSE,FALSE,0,s) DELAY 10 PAUSE_TASK('CHILD',FALSE,FALSE,s)"),
            'b':source('CHILD','n=0 CONDITION[1]: WHEN PAUSE DO NOPAUSE,n=7 ENDCONDITION ENABLE CONDITION[1] DELAY 100 s=n')}).instantiate()
        self.assertEqual(instance.run('MAIN')['CHILD']['values']['S'],7)

    def test_abort_releases_pending_semaphore(self):
        ctx=rt.ExecutionContext(semaphores=rt.SemaphoreBank(1))
        instance=translate_project({'a':source('MAIN',"RUN_TASK('CHILD',0,FALSE,FALSE,0,s) DELAY 20 ABORT_TASK('CHILD',TRUE,FALSE,s)"),
            'b':source('CHILD','PEND_SEMA(1,-1,timeout)',decl='timeout: BOOLEAN')}).instantiate(context=ctx)
        with self.assertRaises(rt.KarelAbort): instance.run('MAIN')
        self.assertEqual((ctx.semaphores.tickets,ctx.semaphores.value(1)),([],0))
        self.assertEqual(instance.programs['CHILD'].service_requests[-1]['outcome'],'failed')

    def test_inactive_abort_still_prevents_start(self):
        tasks=rt.TaskRegistry();child,_=compile_program('n=9',cooperative=True);tasks.bind('child',child)
        run("ABORT_TASK('child',TRUE,FALSE,s)",context=rt.ExecutionContext(tasks=tasks))
        with self.assertRaises(rt.KarelAbort): child.run()
        self.assertEqual(child.task_state,'aborted')

    def test_synchronous_child_termination_does_not_terminate_caller(self):
        for action in ('ABORT','STOP'):
            with self.subTest(action=action):
                tasks=rt.TaskRegistry();child,_=compile_program(action,cooperative=True);tasks.bind('child',child)
                state=run("RUN_TASK('child',0,FALSE,FALSE,0,s) n=7",context=rt.ExecutionContext(tasks=tasks))
                self.assertEqual((state['N'],state['S']),(7,0));self.assertEqual(child.task_state,'aborted' if action=='ABORT' else 'stopped')

    def test_synchronous_child_resume_abort_is_isolated(self):
        tasks=rt.TaskRegistry();child,_=compile_program('PAUSE ABORT');tasks.bind('child',child)
        state=run("RUN_TASK('child',0,FALSE,FALSE,0,s) CONT_TASK('child',s) n=7",context=rt.ExecutionContext(tasks=tasks))
        self.assertEqual((state['N'],state['S'],child.task_state),(7,0,'aborted'))

    def test_synchronous_child_runtime_failure_propagates(self):
        tasks=rt.TaskRegistry();child,_=compile_program('s=0 n=1 DIV s',cooperative=True);tasks.bind('child',child)
        p,_=compile_program("RUN_TASK('child',0,FALSE,FALSE,0,s) n=7",context=rt.ExecutionContext(tasks=tasks))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'zero'): p.run()
        self.assertEqual(child.task_state,'failed')

    def test_linked_named_self_control_uses_callers_task_identity(self):
        instance=translate_project({'a':source('LIB','',routines="ROUTINE halt BEGIN ABORT_TASK('MAIN',TRUE,FALSE,s) END halt"),
            'b':source('MAIN','CONDITION[1]: WHEN ABORT DO NOABORT,n=7 ENDCONDITION ENABLE CONDITION[1] halt() s=n',routines='ROUTINE halt FROM LIB')}).instantiate()
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['S'],7)

    def test_linked_numeric_self_control_uses_callers_task_identity(self):
        instance=translate_project({'a':source('LIB','',routines='ROUTINE halt BEGIN ABORT PROGRAM[2] END halt'),
            'b':source('MAIN','CONDITION[1]: WHEN ABORT DO NOABORT,n=7 ENDCONDITION ENABLE CONDITION[1] halt() s=n',routines='ROUTINE halt FROM LIB')}).instantiate()
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['S'],7)

    def test_linked_task_cannot_drive_itself_synchronously(self):
        instance=translate_project({'a':source('LIB','',routines="ROUTINE bad BEGIN CONT_TASK('MAIN',s) END bad"),
            'b':source('MAIN','bad()',routines='ROUTINE bad FROM LIB')}).instantiate()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'itself'): instance.run('MAIN')

    def test_final_continue_notifies_handlers(self):
        self.assertEqual(run('n=0 CONDITION[1]: WHEN CONTINUE DO n=7 ENDCONDITION ENABLE CONDITION[1] CONTINUE')['N'],7)

    def test_final_numeric_continue_notifies_self_and_linked_handlers(self):
        body='n=0 CONDITION[1]: WHEN CONTINUE DO n=7 ENDCONDITION ENABLE CONDITION[1] '
        tasks=rt.TaskRegistry();p,_=compile_program(body+'CONTINUE PROGRAM[1]',context=rt.ExecutionContext(tasks=tasks))
        tasks.bind('T',p);self.assertEqual(p.run()['N'],7)
        instance=translate_project({'a':source('LIB','',routines='ROUTINE notify BEGIN CONTINUE PROGRAM[2] END notify'),
            'b':source('MAIN',body+'notify()',routines='ROUTINE notify FROM LIB')}).instantiate()
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['N'],7)

    def test_unknown_task_sets_status_and_motion_request_preserves_child(self):
        self.assertEqual(run("ABORT_TASK('absent',TRUE,FALSE,s)")['S'],1)
        tasks=rt.TaskRegistry();child,_=compile_program('n=7',cooperative=True);tasks.bind('child',child)
        p,_=compile_program("s=9 ABORT_TASK('child',TRUE,TRUE,s)",context=rt.ExecutionContext(tasks=tasks))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Motion'): p.run()
        self.assertEqual((p.snapshot()['S'],child.task_state),(9,'ready'))


class ScopedErrorTests(unittest.TestCase):
    def test_all_named_severities_and_effects(self):
        for name,(_,effect,local) in rt.ERROR_SEVERITIES.items():
            with self.subTest(name=name):
                p,result=compile_program(f"n=1 POST_ERR_L(12,'part',3,{name}) n=7")
                if effect:
                    with self.assertRaises(rt.KarelPause if effect==1 else rt.KarelAbort): p.run()
                    self.assertEqual(p.snapshot()['N'],1)
                    if effect==1: self.assertEqual(p.resume()['N'],7)
                else: self.assertEqual(p.run()['N'],7)
                record=p._state.execution.errors.snapshot()[0]
                self.assertEqual((record['operation'],record['severity_name'],record['severity'],record['program'],record['source_program']),('POST_ERR_L',name,effect,'T' if local else '','T'))
                self.assertTrue(result.report['cooperative_execution'])

    def test_local_and_global_delivery_are_distinct(self):
        for name,(_,effect,local) in rt.ERROR_SEVERITIES.items():
            with self.subTest(name=name):
                handlers='n=0 CONDITION[1]: WHEN ERROR[*] DO NOPAUSE,NOABORT,n=7 ENDCONDITION ENABLE CONDITION[1] '
                instance=translate_project({'a':source('MAIN',handlers+f"RUN_TASK('CHILD',0,FALSE,FALSE,0,s) DELAY 20 POST_ERR_L(12,'',0,{name}) s=n"),
                    'b':source('CHILD',handlers+'DELAY 100 s=n')}).instantiate()
                result=instance.run('MAIN');self.assertEqual(result['MAIN']['values']['S'],7)
                self.assertEqual(result['CHILD']['values']['S'],0 if local else 7)

    def test_linked_local_error_scopes_to_callers_task(self):
        instance=translate_project({'a':source('LIB','',routines="ROUTINE report BEGIN POST_ERR_L(12,'',0,ERSEV_PAUSEL) END report"),
            'b':source('MAIN','CONDITION[1]: WHEN ERROR[12] DO NOPAUSE,n=7 ENDCONDITION ENABLE CONDITION[1] report() s=n',routines='ROUTINE report FROM LIB')}).instantiate()
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['S'],7)
        record=instance.context.errors.snapshot()[0];self.assertEqual((record['program'],record['source_program']),('MAIN','LIB'))

    def test_local_metadata_persists_and_copies(self):
        p,_=compile_program("POST_ERR_L(12,'part',0,ERSEV_WARN)");p.run();ctx=p._state.execution
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertEqual(restored.errors.snapshot(),ctx.errors.snapshot())
        copy=restored.errors.snapshot();copy[0]['severity_name']='bad';self.assertEqual(restored.errors.snapshot()[0]['severity_name'],'ERSEV_WARN')

    def test_invalid_portable_severity_does_not_post(self):
        for value in (-1,11,999):
            with self.subTest(value=value):
                p,_=compile_program(f"POST_ERR_L(12,'',0,{value})")
                with self.assertRaisesRegex(rt.KarelRuntimeError,'ERSEV'): p.run()
                self.assertFalse(any(row['origin']=='posted' for row in p._state.execution.errors.snapshot()))

    def test_incomplete_or_inconsistent_local_metadata_rejected(self):
        p,_=compile_program("POST_ERR_L(12,'',0,ERSEV_WARN)");p.run();record=p._state.execution.errors.snapshot()[0]
        for changes in ({'severity_name':'bad'},{'severity':2},{'program':'T'},{'operation':'bad'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError): rt.ErrorHistory(records=[dict(record,**changes)])
        del record['source_program']
        with self.assertRaises(ValueError): rt.ErrorHistory(records=[record])

    def test_predefined_severity_names_are_case_insensitive(self):
        self.assertEqual(run('n=ersev_abortl s=ERSEV_SYSTEM'),{'N':9,'S':10})
        with self.assertRaises(TranslationError): compile_program('n=1',decl='ersev_abort: INTEGER n: INTEGER')

    def test_nomessage_handler_suppresses_local_error(self):
        p,_=compile_program("CONDITION[1]: WHEN ERROR[*] DO NOMESSAGE,NOPAUSE ENDCONDITION ENABLE CONDITION[1] POST_ERR_L(12,'',0,ERSEV_STOPL) n=7")
        self.assertEqual(p.run()['N'],7);self.assertTrue(p._state.execution.errors.snapshot()[0]['suppressed'])


class FileFieldTests(unittest.TestCase):
    def file_program(self,data,body,decl='a,b: STRING[3] n,s: INTEGER',attributes='SET_FILE_ATR(f,ATR_FIELD)',backend=None):
        files=backend if backend is not None else rt.MemoryFiles({'data':data})
        p,result=compile_program(f"{attributes} OPEN FILE f ('R','data') {body}",decl='f: FILE '+decl,context=rt.ExecutionContext(files=files))
        return p,files

    def test_field_default_string_capacity_and_sequential_reads(self):
        p,_=self.file_program('abcdef','READ f (a) n=GET_FILE_POS(f) READ f (b) s=GET_FILE_POS(f)')
        state=p.run();self.assertEqual((state['A'],state['B'],state['N'],state['S']),('abc','def',3,6))

    def test_field_explicit_width_overrides_capacity(self):
        p,_=self.file_program('abcdef','READ f (a::2,b::4) n=GET_FILE_POS(f)')
        state=p.run();self.assertEqual((state['A'],state['B'],state['N']),('ab','cde',6))

    def test_field_zero_width_uses_capacity(self):
        p,_=self.file_program('abcdef','READ f (a::0,b)');self.assertEqual((p.run()['A'],p.snapshot()['B']),('abc','def'))

    def test_short_field_preserves_all_targets_and_byte_cursor(self):
        p,_=self.file_program('abcde',"a='old' b='old' READ f (a,b)")
        with self.assertRaisesRegex(rt.KarelRuntimeError,'incomplete'): p.run()
        state=p.snapshot();self.assertEqual((state['A'],state['B'],state['F']['position']),('old','old',0))
        self.assertEqual(p._state.values['F'].status,1)

    def test_field_numbers_keep_token_defaults(self):
        p,_=self.file_program('123 4.25 ON','READ f (n,x,flag)',decl='n: INTEGER x: REAL flag: BOOLEAN')
        state=p.run();self.assertEqual((state['N'],state['X'],state['FLAG']),(123,4.25,True))

    def test_field_quoted_string_uses_declared_field_width(self):
        p,_=self.file_program("'a'xyz",'READ f (a::0::2,b)')
        state=p.run();self.assertEqual((state['A'],state['B']),('a','xyz'))

    def test_default_string_without_field_reads_record(self):
        p,_=self.file_program('abcdef\r\n','READ f (a,CR) n=GET_FILE_POS(f)',attributes='')
        state=p.run();self.assertEqual((state['A'],state['N']),('abc',8))

    def test_custom_eol_sequential_records(self):
        p,_=self.file_program('abc;def;',"READ f (a,CR) n=GET_FILE_POS(f) READ f (b,CR) s=GET_FILE_POS(f)",attributes='SET_FILE_ATR(f,ATR_EOL,59)')
        state=p.run();self.assertEqual((state['A'],state['B'],state['N'],state['S']),('abc','def',4,8))

    def test_custom_eol_treats_newlines_as_string_data(self):
        p,_=self.file_program('a\r\nb;','READ f (a,CR) n=GET_FILE_POS(f)',decl='a: STRING[8] n: INTEGER',attributes='SET_FILE_ATR(f,ATR_EOL,59)')
        state=p.run();self.assertEqual((state['A'],state['N']),('a\r\nb',5))

    def test_crlf_cursor_counts_both_bytes(self):
        p,_=self.file_program('abc\r\ndef\nghi\r','READ f (a,CR) n=GET_FILE_POS(f) READ f (b,CR) s=GET_FILE_POS(f)')
        state=p.run();self.assertEqual((state['N'],state['S']),(5,9))

    def test_nul_terminator(self):
        p,_=self.file_program(b'abc\0def\0','READ f (a,CR,b,CR) n=GET_FILE_POS(f)',attributes='SET_FILE_ATR(f,ATR_EOL,0)')
        state=p.run();self.assertEqual((state['A'],state['B'],state['N']),('abc','def',8))

    def test_record_read_failure_preserves_cursor(self):
        p,_=self.file_program('12;bad;',"n=9 s=9 READ f (n,CR,s,CR)",decl='n,s: INTEGER',attributes='SET_FILE_ATR(f,ATR_EOL,59)')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        state=p.snapshot();self.assertEqual((state['N'],state['S'],state['F']['position']),(9,9,0))

    def test_directory_backend_uses_same_field_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'data').write_bytes(b'abcdef;')
            p,files=self.file_program(None,'READ f (a,b,CR) n=GET_FILE_POS(f)',attributes='SET_FILE_ATR(f,ATR_FIELD) SET_FILE_ATR(f,ATR_EOL,59)',backend=rt.DirectoryFiles(folder))
            state=p.run();self.assertEqual((state['A'],state['B'],state['N']),('abc','def',7));self.assertEqual(Path(folder,'data').read_bytes(),b'abcdef;')

    def test_custom_eol_write_read_roundtrip(self):
        files=rt.MemoryFiles();state=run("SET_FILE_ATR(f,ATR_EOL,59) OPEN FILE f ('RW','data') WRITE f ('abc',CR,'def',CR) SET_FILE_POS(f,0,s) READ f (a,CR,b,CR) n=GET_FILE_POS(f)",decl='f: FILE a,b: STRING[3] n,s: INTEGER',context=rt.ExecutionContext(files=files))
        self.assertEqual((state['A'],state['B'],state['N'],files.snapshot()['data']),('abc','def',8,b'abc;def;'))

    def test_field_attribute_does_not_change_text_writes(self):
        files=rt.MemoryFiles();run("SET_FILE_ATR(f,ATR_FIELD) OPEN FILE f ('W','data') WRITE f ('a','b')",decl='f: FILE',context=rt.ExecutionContext(files=files))
        self.assertEqual(files.snapshot()['data'],b'ab')

    def test_binary_ignores_text_eol_and_field_flag(self):
        p,_=self.file_program(b'abc;','READ f (a::3,n::1)',decl='a: STRING[3] n: INTEGER',attributes='SET_FILE_ATR(f,ATR_UF) SET_FILE_ATR(f,ATR_FIELD) SET_FILE_ATR(f,ATR_EOL,59)')
        state=p.run();self.assertEqual((state['A'],state['N']),('abc',59))

    def test_text_input_exact_offsets_and_validation(self):
        reader=rt.TextInput('ab\r\ncd\r',field_mode=True)
        request={'targets':[{'type':'STRING','type_spec':['STRING',2]}],'line_breaks':[1]}
        self.assertEqual(reader(request),['ab']);self.assertEqual(reader.offset,4)
        self.assertEqual(reader(request),['cd']);self.assertEqual(reader.offset,7)
        self.assertTrue(reader.position['eof'])
        for options in ({'terminator':True},{'terminator':128},{'terminator':'x'},{'field_mode':1}):
            with self.subTest(options=options),self.assertRaises(ValueError): rt.TextInput('',**options)


if __name__=='__main__': unittest.main()
