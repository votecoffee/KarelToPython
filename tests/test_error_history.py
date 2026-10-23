"""Authored ERR_DATA traversal, output protection and persisted presentation data."""
import ast
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import runtime as rt, translate
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program

ROOT=Path(__file__).resolve().parents[1]
DECL='seq,code,cause,stamp,severity: INTEGER message,reason: STRING[40] owner: STRING[12]'
CALL='ERR_DATA(seq,code,message,cause,reason,stamp,severity,owner)'
SEED="code=99 cause=98 stamp=97 severity=96 message='old' reason='prior' owner='previous'"


def context():
    history=rt.ErrorHistory()
    history.post(15018,'parameter',42,1,program='MAIN',error_string='first error',cause_string='first cause',time_int=rt._pack_time(datetime(2026,10,23,12,34,56)))
    history.post(15019,'second',0,2)
    return rt.ExecutionContext(errors=history)


def program(body,ctx=None,decl=DECL,**options):
    return compile_program(body,decl=decl,context=context() if ctx is None else ctx,**options)[0]


class ErrorDataTests(unittest.TestCase):
    def test_oldest_record_and_complete_fields(self):
        state=program('seq=0 '+CALL).run()
        self.assertEqual((state['SEQ'],state['CODE'],state['MESSAGE'],state['CAUSE'],state['REASON'],state['SEVERITY'],state['OWNER']),
                         (1,15018,'first error',42,'first cause',1,'MAIN'))
        self.assertEqual(rt._unpack_time(state['STAMP']),datetime(2026,10,23,12,34,56))

    def test_next_record_and_end_preserves_outputs(self):
        p=program('seq=1 '+CALL+' '+CALL)
        state=p.run()
        self.assertEqual((state['SEQ'],state['CODE'],state['MESSAGE'],state['CAUSE'],state['REASON'],state['STAMP'],state['SEVERITY'],state['OWNER']),
                         (0,15019,'second',0,'',0,2,''))

    def test_latest_constant_does_not_require_maxint_storage(self):
        state=program('seq=7 '+CALL.replace('seq,','MAXINT,')).run()
        self.assertEqual((state['SEQ'],state['CODE']),(7,15019))
        state=program(CALL.replace('seq,','(2147483647),')).run()
        self.assertEqual(state['CODE'],15019)

    def test_latest_named_constant(self):
        state=program(CALL.replace('seq,','last,'),prefix='CONST last=MAXINT').run()
        self.assertEqual(state['CODE'],15019)

    def test_maxint_storage_guard_is_retained(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'MAXINT'):
            program('seq=MAXINT '+CALL).run()

    def test_empty_or_missing_history_does_not_create_one(self):
        for history in (None,rt.ErrorHistory()):
            with self.subTest(history=history):
                ctx=rt.ExecutionContext(errors=history)
                state=program('seq=4 '+SEED+' '+CALL,ctx).run()
                self.assertEqual((state['SEQ'],state['CODE'],state['MESSAGE'],state['OWNER']),(0,99,'old','previous'))
                self.assertIs(ctx.errors,history)

    def test_empty_latest_preserves_all_outputs(self):
        state=program(SEED+' '+CALL.replace('seq,','MAXINT,'),rt.ExecutionContext()).run()
        self.assertEqual((state['CODE'],state['MESSAGE'],state['STAMP']),(99,'old',97))

    def test_cursor_past_end_preserves_fields(self):
        state=program('seq=100 '+SEED+' '+CALL).run()
        self.assertEqual((state['SEQ'],state['CODE'],state['CAUSE'],state['REASON']),(0,99,98,'prior'))

    def test_evicted_and_gapped_sequences(self):
        history=rt.ErrorHistory(limit=2)
        for n in range(4): history.post(n)
        ctx=rt.ExecutionContext(errors=history)
        self.assertEqual(program('seq=1 '+CALL,ctx).run()['SEQ'],3)
        rows=history.snapshot();rows[1]['sequence']=8
        ctx=rt.ExecutionContext(errors=rt.ErrorHistory(records=rows))
        self.assertEqual(program('seq=4 '+CALL,ctx).run()['SEQ'],8)

    def test_negative_and_uninitialized_cursor_preserve_outputs(self):
        for prefix in ('seq=-1 ',''):
            p=program(prefix+SEED+' '+CALL)
            with self.subTest(prefix=prefix),self.assertRaises(rt.KarelRuntimeError): p.run()
            self.assertEqual((p.snapshot()['CODE'],p.snapshot()['MESSAGE']),(99,'old'))

    def test_both_messages_require_minimum_capacity(self):
        for name in ('message','reason'):
            decl='seq,code,cause,stamp,severity: INTEGER owner: STRING[12] '+f'{name}: STRING[39] '+f'{"reason" if name=="message" else "message"}: STRING[40]'
            p=program('seq=0 '+SEED+' '+CALL,decl=decl)
            with self.subTest(name=name),self.assertRaisesRegex(rt.KarelRuntimeError,'40..254'): p.run()
            self.assertEqual((p.snapshot()['SEQ'],p.snapshot()['CODE']),(0,99))

    def test_messages_right_truncate_to_actual_capacity(self):
        history=rt.ErrorHistory();history.post(1,error_string='a'*254,cause_string='b'*254,program='VERYLONGPROGRAM')
        state=program('seq=0 '+CALL,rt.ExecutionContext(errors=history)).run()
        self.assertEqual((state['MESSAGE'],state['REASON'],state['OWNER']),('a'*40,'b'*40,'VERYLONGPROG'))

    def test_invalid_late_field_does_not_publish_earlier_outputs(self):
        history=rt.ErrorHistory();history.post(1,program='bad\u00fc')
        p=program('seq=0 '+SEED+' '+CALL,rt.ExecutionContext(errors=history))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['SEQ'],p.snapshot()['CODE'],p.snapshot()['MESSAGE']),(0,99,'old'))

    def test_overlapping_output_references_are_rejected(self):
        for call in (CALL.replace('seq,code,','seq,seq,'),CALL.replace(',owner)',',message)')):
            p=program('seq=0 '+SEED+' '+call)
            with self.subTest(call=call),self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): p.run()
            self.assertEqual(p.snapshot()['CODE'],99)

    def test_literal_and_wrong_type_outputs_are_rejected(self):
        for call in (CALL.replace('seq,','0,'),CALL.replace(',code,',',TRUE,'),CALL.replace(',code,',',owner,'),CALL.replace(',owner)',')')):
            with self.subTest(call=call),self.assertRaises(TranslationError): program('seq=0 '+call)

    def test_direct_and_transitive_for_counter_writes_are_rejected(self):
        for body,routines in (
            ('FOR seq=1 TO 2 DO '+CALL+' ENDFOR',''),
            ('FOR seq=1 TO 2 DO inspect ENDFOR','ROUTINE inspect BEGIN '+CALL+' END inspect')):
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught: program(body,routines=routines)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_lookup_does_not_consume_error_handler_notifications(self):
        body='CONDITION[1]: WHEN ERROR[*] DO '+CALL.replace('seq,','MAXINT,')+' ENDCONDITION CONDITION[2]: WHEN ERROR[*] DO seq=7 ENDCONDITION ENABLE CONDITION[1] ENABLE CONDITION[2] POST_ERR(12,\'posted\',0,0)'
        state=program(body,rt.ExecutionContext()).run()
        self.assertEqual((state['CODE'],state['SEQ']),(12,7))

    def test_lookup_from_posted_error_handler(self):
        body='CONDITION[1]: WHEN ERROR[*] DO '+CALL.replace('seq,','MAXINT,')+' ENDCONDITION ENABLE CONDITION[1] POST_ERR(12,\'handler text\',0,0)'
        state=program(body,rt.ExecutionContext()).run()
        self.assertEqual((state['CODE'],state['MESSAGE'],state['OWNER']),(12,'handler text',''))

    def test_posted_error_has_explicit_calendar_timestamp(self):
        ctx=rt.ExecutionContext(calendar=rt.CalendarClock(datetime(2026,10,23,12,34,56)))
        state=program("POST_ERR(12,'posted',0,0) "+CALL.replace('seq,','MAXINT,'),ctx).run()
        self.assertEqual(rt._unpack_time(state['STAMP']),datetime(2026,10,23,12,34,56))
        self.assertEqual(ctx.errors.snapshot()[0]['time_int'],state['STAMP'])

    def test_read_does_not_sample_calendar_or_change_history(self):
        ctx=context();before=ctx.errors.snapshot()
        class BrokenClock:
            def read(self,line=None): raise AssertionError('ERR_DATA sampled a clock')
        ctx.calendar=BrokenClock()
        program('seq=0 '+CALL,ctx).run()
        self.assertEqual(ctx.errors.snapshot(),before)

    def test_report_describes_portable_contract(self):
        result=translate('PROGRAM T VAR '+DECL+' BEGIN seq=0 '+CALL+' END T')
        policy=result.report['error_history_policy']
        self.assertFalse(policy['controller_validated'])
        self.assertIn('ERR_DATA',result.report['service_policy']['procedures'])


class ErrorHistoryPersistenceTests(unittest.TestCase):
    def test_presentation_roundtrip_and_legacy_records(self):
        ctx=context();saved=json.loads(json.dumps(ctx.to_config()))
        restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.errors.snapshot(),ctx.errors.snapshot())
        self.assertEqual(program('seq=0 '+CALL,restored).run()['REASON'],'first cause')
        self.assertNotIn('time_int',restored.errors.snapshot()[1])

    def test_read_returns_defensive_copy(self):
        history=context().errors;record=history.read_after(0);record['code']=77
        self.assertEqual(history.read_after(0)['code'],15018)

    def test_invalid_presentation_preserves_history_and_sequence(self):
        for metadata in ({'error_string':'\u00fc'},{'cause_string':'x'*255},{'time_int':True},{'time_int':1}):
            history=rt.ErrorHistory()
            with self.subTest(metadata=metadata),self.assertRaises(rt.KarelRuntimeError): history.post(1,**metadata)
            self.assertEqual((history.records,history.sequence),([],0))

    def test_invalid_persisted_presentation_is_rejected(self):
        row=context().errors.snapshot()[0]
        for update in ({'error_string':None},{'cause_string':4},{'time_int':1},{'extra':0},{'sequence':2147483647}):
            with self.subTest(update=update),self.assertRaises((ValueError,rt.KarelRuntimeError)):
                rt.ErrorHistory(records=[dict(row,**update)])

    def test_sequence_exhaustion_does_not_append_or_wrap(self):
        row=context().errors.snapshot()[0];row['sequence']=2147483646
        history=rt.ErrorHistory(records=[row]);before=history.snapshot()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'sequence exhausted'): history.post(9)
        self.assertEqual(history.snapshot(),before)


class ErrorHistoryCliTests(unittest.TestCase):
    def test_fresh_cli_translation_execution_and_saved_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);output=root/'history.py';report=root/'report.json';saved=root/'state.json'
            result=subprocess.run([sys.executable,'-X','utf8','-m','karel2py',str(ROOT/'examples/error_history.kl'),'-o',str(output),'--report',str(report)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('error_history_policy',json.loads(report.read_text(encoding='utf-8')))
            result=subprocess.run([sys.executable,'-X','utf8',str(output),'--context',str(ROOT/'examples/error_history.services.initial.json'),'--state-out',str(saved)],cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(ast.literal_eval(result.stdout),json.loads((ROOT/'examples/error_history.expected.json').read_text(encoding='utf-8')))
            rows=json.loads(saved.read_text(encoding='utf-8'))['errors']['records']
            self.assertEqual([row['code'] for row in rows],[15018,15019])
            self.assertTrue(all(row['time_int']==ast.literal_eval(result.stdout)['STAMP'] for row in rows))


if __name__=='__main__': unittest.main()
