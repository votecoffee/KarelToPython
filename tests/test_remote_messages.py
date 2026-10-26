"""Authored message publication, deferred attachment and persistence regressions."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


DECL='paths:ARRAY[2] OF STRING[40] s,n:INTEGER'
XML=b'<message><value>7</value></message>'


def context(initial=None,**options):
    return rt.ExecutionContext(remote_messages=rt.RemoteMessages(**options),files=rt.MemoryFiles(initial or {'TD:note.xml':XML}))


def send(ctx,body="paths[1]='' paths[2]='' RMCN_SEND('TD:note.xml',paths,1,s)",**options):
    return run(body,decl=DECL,context=ctx,**options)


def selected(bank,paths=('TD:data.bin','MD:latest.dg')):
    if bank.queue_attach('ALARM_MSG_P',paths,1):raise AssertionError('Could not select attachments')
    if bank.publish('ALARM_MSG_P',b'event'):raise AssertionError('Could not publish message')


class RemoteMessageSourceTests(unittest.TestCase):
    def test_alert_explicit_defaults_and_custom_values(self):
        ctx=context(defaults={'address':'recipient@example.invalid','url':'offline://alerts'})
        data=run("RMCN_ALERT('','','','',s) RMCN_ALERT('local','subject','body','link',n)",context=ctx)
        self.assertEqual((data['S'],data['N']),(0,0))
        self.assertEqual(ctx.remote_messages.snapshot(),[
            dict(sequence=1,kind='alert',address='recipient@example.invalid',subject='iRConnect Alert',message='',url='offline://alerts'),
            dict(sequence=2,kind='alert',address='local',subject='subject',message='body',url='link')])

    def test_missing_native_defaults_remain_empty_offline_data(self):
        ctx=context();run("RMCN_ALERT('','','','',s)",context=ctx)
        self.assertEqual(ctx.remote_messages.snapshot()[0]['address'],'')
        self.assertEqual(ctx.remote_messages.snapshot()[0]['url'],'')

    def test_xml_queued_and_deleted_with_deferred_attachment_names(self):
        ctx=context();data=send(ctx,"paths[1]='TD:later.bin' paths[2]='MD:latest.dg' RMCN_SEND('TD:note.xml',paths,1,s)")
        self.assertEqual(data['S'],0);self.assertNotIn('TD:note.xml',ctx.files.files)
        self.assertEqual(ctx.remote_messages.snapshot(),[dict(sequence=1,kind='xml',xml_file='TD:note.xml',data=XML.hex(),
            attachments=['TD:later.bin','MD:latest.dg'],priority=1)])

    def test_empty_attachment_sentinel_does_not_require_an_attachment_file(self):
        ctx=context();self.assertEqual(send(ctx)['S'],0)
        code,row=ctx.remote_messages.collect(1)
        self.assertEqual(code,0);self.assertEqual(row['attachments'],[])
        self.assertEqual(ctx.remote_messages.messages,[])

    def test_queue_attach_only_selects_explicit_type_without_reading_or_sending(self):
        ctx=context(message_types=['ALARM_MSG_P']);data=send(ctx,"paths[1]='TD:later' paths[2]='' QUEUE_ATTACH('alarm_msg_p',paths,1,s)")
        self.assertEqual(data['S'],0);self.assertEqual(ctx.remote_messages.sequence,0)
        self.assertEqual(ctx.remote_messages.pending,{'ALARM_MSG_P':{'attachments':['TD:later'],'priority':1}})
        self.assertIn('TD:note.xml',ctx.files.files)

    def test_queue_attach_replaces_selection_but_retains_previously_published_row(self):
        bank=rt.RemoteMessages(message_types=['A']);bank.queue_attach('A',['TD:first'],0);bank.publish('A',b'1')
        bank.queue_attach('A',['TD:second'],1);bank.publish('a',b'2')
        self.assertEqual([row['attachments'] for row in bank.messages],[['TD:first'],['TD:second']])
        self.assertEqual([row['priority'] for row in bank.messages],[0,1])

    def test_unknown_type_and_bad_priority_leave_bank_unchanged(self):
        ctx=context(message_types=['A']);before=ctx.remote_messages.to_config()
        for call,expected in [("QUEUE_ATTACH('missing',paths,1,s)",1),("QUEUE_ATTACH('A',paths,2,s)",2),
                ("RMCN_SEND('TD:note.xml',paths,-1,s)",2)]:
            self.assertEqual(send(ctx,"paths[1]='' paths[2]='' "+call)['S'],expected)
            self.assertEqual(ctx.remote_messages.to_config(),before);self.assertIn('TD:note.xml',ctx.files.files)

    def test_invalid_attachment_names_duplicates_and_xml_self_reference_reject(self):
        for paths in [('TD:../escape',''),('PIP:LOG',''),('S1:',''),('TD:a','td:a'),('TD:note.xml',''),('/absolute','')]:
            ctx=context();body=f"paths[1]='{paths[0]}' paths[2]='{paths[1]}' RMCN_SEND('TD:note.xml',paths,0,s)"
            self.assertEqual(send(ctx,body)['S'],2,paths)
            self.assertEqual(ctx.remote_messages.messages,[]);self.assertIn('TD:note.xml',ctx.files.files)

    def test_missing_and_busy_xml_return_status_without_publication(self):
        ctx=context();ctx.files.delete('TD:note.xml');self.assertEqual(send(ctx)['S'],1)
        ctx=context();handle=rt.FileHandle();ctx.files.open(handle,'R','TD:note.xml')
        self.assertEqual(send(ctx)['S'],3);self.assertEqual(ctx.remote_messages.sequence,0);ctx.files.close(handle)

    def test_invalid_xml_and_dtd_entities_are_rejected_before_deletion(self):
        invalid=[b'',b'<unclosed>',b'not XML',b'<a/><b/>',b'<!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>',
            b'<a>\xff</a>',b'<a>'*65+b'</a>'*65,b'<a>'+b'<b/>'*4096+b'</a>']
        for data in invalid:
            ctx=context({'TD:note.xml':data});self.assertEqual(send(ctx)['S'],4)
            self.assertEqual(ctx.files.files['TD:note.xml'],data);self.assertEqual(ctx.remote_messages.messages,[])

    def test_utf8_xml_and_byte_order_mark_are_preserved_as_bytes(self):
        data=b'\xef\xbb\xbf<message>caf\xc3\xa9</message>';ctx=context({'TD:note.xml':data})
        self.assertEqual(send(ctx)['S'],0);self.assertEqual(ctx.remote_messages.messages[0]['data'],data.hex())

    def test_full_queue_byte_budget_and_sequence_exhaustion_preserve_xml(self):
        for options in ({'capacity':1},{'limit':10},{}):
            ctx=context(**options)
            if 'capacity' in options:ctx.remote_messages.alert('a','b','c','d')
            if not options:ctx.remote_messages.sequence=2147483646
            before=ctx.remote_messages.to_config();self.assertEqual(send(ctx)['S'],5)
            self.assertEqual(ctx.remote_messages.to_config(),before);self.assertIn('TD:note.xml',ctx.files.files)

    def test_arrays_are_input_snapshots_before_output_selector_effects(self):
        ctx=context();routines="ROUTINE slot:INTEGER BEGIN paths[1]='TD:after' n=n+1 RETURN 1 END slot"
        p,_=compile_program("n=0 paths[1]='TD:before' paths[2]='' RMCN_SEND('TD:note.xml',paths,0,results[slot])",
            decl=DECL+' results:ARRAY[1] OF INTEGER',routines=routines,context=ctx)
        data=p.run();self.assertEqual(data['N'],1);self.assertEqual(data['PATHS'][0],'TD:after')
        self.assertEqual(ctx.remote_messages.messages[0]['attachments'],['TD:before'])

    def test_generic_named_arrays_and_nested_routines_are_accepted(self):
        ctx=context();p,_=compile_program("paths[1]='' enqueue(paths)",decl='paths:names s:INTEGER',prefix='TYPE names=ARRAY[1] OF STRING[40]',
            routines="ROUTINE enqueue(a:ARRAY OF STRING) BEGIN RMCN_SEND('TD:note.xml',a,0,s) END enqueue",context=ctx)
        self.assertEqual(p.run()['S'],0)

    def test_uninitialized_attachment_leaf_returns_status_without_deleting_xml(self):
        ctx=context();p,_=compile_program("paths[1]='' RMCN_SEND('TD:note.xml',paths,0,s)",decl=DECL,context=ctx)
        self.assertEqual(p.run()['S'],2)
        self.assertIn('TD:note.xml',ctx.files.files);self.assertEqual(ctx.remote_messages.sequence,0)

    def test_wrong_source_shapes_types_and_status_values_fail_closed(self):
        for decl in ('paths:ARRAY[2,2] OF STRING[4] s:INTEGER','paths:ARRAY[2] OF INTEGER s:INTEGER','paths:STRING[4] s:INTEGER'):
            with self.assertRaises(TranslationError):compile_program("RMCN_SEND('a',paths,0,s)",decl=decl)
        with self.assertRaises(TranslationError):compile_program("RMCN_ALERT('a','b','c','d',1)")

    def test_source_array_count_limit_is_runtime_checked(self):
        ctx=context();p,_=compile_program("FOR n=1 TO 33 DO paths[n]='' ENDFOR RMCN_SEND('TD:note.xml',paths,0,s)",
            decl='paths:ARRAY[33] OF STRING[4] n,s:INTEGER',context=ctx)
        self.assertEqual(p.run()['S'],2);self.assertIn('TD:note.xml',ctx.files.files)

    def test_missing_service_or_files_does_not_fall_back_to_host(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'remote_messages'):run("RMCN_ALERT('','','','',s)")
        ctx=rt.ExecutionContext(remote_messages=rt.RemoteMessages())
        self.assertEqual(run("RMCN_ALERT('','','','',s)",context=ctx)['S'],0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'files'):send(ctx)

    def test_status_for_counter_guards_and_user_override_remain(self):
        for call in ("RMCN_ALERT('','','','',n)","RMCN_SEND('a',paths,0,n)","QUEUE_ATTACH('A',paths,0,n)"):
            with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO '+call+' ENDFOR',decl=DECL)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
        self.assertEqual(run('RMCN_SEND(7)',routines='ROUTINE RMCN_SEND(x:INTEGER) BEGIN n=x END RMCN_SEND')['N'],7)

    def test_linked_calls_share_one_explicit_outbox(self):
        ctx=context();project=translate_project({'main':source('MAIN',"RMCN_ALERT('a','b','c','d',s) CALL_PROG('CHILD',s)"),
            'child':source('CHILD',"RMCN_ALERT('e','f','g','h',s)")}).instantiate(context=ctx)
        project.run('MAIN');self.assertEqual([row['sequence'] for row in ctx.remote_messages.messages],[1,2])


class DeferredAttachmentTests(unittest.TestCase):
    def test_collect_reads_latest_contents_deletes_td_and_retains_md(self):
        bank=rt.RemoteMessages(message_types=['ALARM_MSG_P']);selected(bank)
        files=rt.MemoryFiles({'TD:data.bin':b'\0\xff','MD:latest.dg':'latest'})
        code,row=bank.collect(1,files);self.assertEqual(code,0)
        self.assertEqual(row['attachments'],[dict(name='TD:data.bin',data='00ff',retained=False),
            dict(name='MD:latest.dg',data=b'latest'.hex(),retained=True)])
        self.assertNotIn('TD:data.bin',files.files);self.assertEqual(files.files['MD:latest.dg'],b'latest')
        self.assertEqual(bank.messages,[]);self.assertEqual(bank.sequence,1)

    def test_all_attachments_are_preflighted_before_any_deletion(self):
        bank=rt.RemoteMessages(message_types=['ALARM_MSG_P']);selected(bank)
        files=rt.MemoryFiles({'TD:data.bin':'retained'});before=bank.to_config()
        self.assertEqual(bank.collect(1,files),(1,None));self.assertEqual(files.files['TD:data.bin'],b'retained')
        self.assertEqual(bank.to_config(),before)

    def test_open_attachment_prevents_collection_without_queue_changes(self):
        bank=rt.RemoteMessages(message_types=['ALARM_MSG_P']);selected(bank,['TD:data.bin'])
        files=rt.MemoryFiles({'TD:data.bin':'data'});handle=rt.FileHandle();files.open(handle,'R','TD:data.bin')
        self.assertEqual(bank.collect(1,files),(3,None));self.assertEqual(bank.sequence,1)
        files.close(handle);self.assertEqual(bank.collect(1,files)[0],0)

    def test_device_deletions_account_for_garbage_and_md_can_be_read_only(self):
        bank=rt.RemoteMessages(message_types=['ALARM_MSG_P']);selected(bank)
        files=rt.DeviceFiles({'TD:':{'capacity':100,'retain_deleted':True},'MD:':{'capacity':100,'read_only':True}},
            {'TD:data.bin':b'abc','MD:latest.dg':b'new'})
        self.assertEqual(bank.collect(1,files)[0],0);self.assertEqual(files._volumes['TD']['garbage'],3)
        self.assertEqual(files.files['MD:latest.dg'],b'new')

    def test_read_only_or_unmounted_non_md_attachment_preserves_all(self):
        for flags in ({'read_only':True},{'mounted':False}):
            bank=rt.RemoteMessages(message_types=['ALARM_MSG_P']);selected(bank,['TD:data.bin'])
            files=rt.DeviceFiles({'TD:':{'capacity':100,**flags}},{'TD:data.bin':'data'})
            self.assertEqual(bank.collect(1,files),(4,None));self.assertIn('TD:data.bin',files.files)
            self.assertEqual(len(bank.messages),1)

    def test_xml_on_md_is_deleted_but_read_only_xml_is_preserved(self):
        ctx=context();ctx.files=rt.DeviceFiles({'MD:':{'capacity':200}},{'MD:note.xml':XML})
        self.assertEqual(send(ctx,"paths[1]='' paths[2]='' RMCN_SEND('MD:note.xml',paths,0,s)")['S'],0)
        self.assertNotIn('MD:note.xml',ctx.files.files)
        ctx=context();ctx.files=rt.DeviceFiles({'TD:':{'capacity':200,'read_only':True}},{'TD:note.xml':XML})
        self.assertEqual(send(ctx)['S'],4);self.assertIn('TD:note.xml',ctx.files.files)

    def test_collection_payload_budget_prevents_partial_deletion(self):
        bank=rt.RemoteMessages(limit=400,message_types=['ALARM_MSG_P']);selected(bank,['TD:a','TD:b'])
        files=rt.MemoryFiles({'TD:a':'a'*30,'TD:b':'b'*200});before=bank.to_config()
        self.assertEqual(bank.collect(1,files),(5,None));self.assertEqual(bank.to_config(),before)
        self.assertEqual(set(files.files),{'TD:a','TD:b'})

    def test_directory_and_custom_backends_are_rejected_without_io(self):
        from karel2py.storage import DirectoryFiles
        class Custom(rt.MemoryFiles):
            def delete(self,name):raise AssertionError('Unexpected callback')
        for files in (Custom({'TD:note.xml':XML}),):
            bank=rt.RemoteMessages();self.assertEqual(bank.send(files,'TD:note.xml',[''],0),4)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'note.xml';path.write_bytes(XML);files=DirectoryFiles(folder)
            bank=rt.RemoteMessages();self.assertEqual(bank.send(files,'note.xml',[''],0),4)
            self.assertEqual(path.read_bytes(),XML)

    def test_collection_can_choose_a_row_without_reordering_other_messages(self):
        bank=rt.RemoteMessages();bank.alert('a','1','','');bank.alert('a','2','','');bank.alert('a','3','','')
        self.assertEqual(bank.collect(2)[1]['subject'],'2')
        self.assertEqual([row['sequence'] for row in bank.messages],[1,3]);bank.alert('a','4','','')
        self.assertEqual(bank.messages[-1]['sequence'],4)

    def test_invalid_collection_and_detached_snapshots_preserve_bank(self):
        bank=rt.RemoteMessages();bank.alert('a','b','','');before=bank.to_config()
        for value in (0,True,-1,'1'):self.assertEqual(bank.collect(value),(2,None))
        self.assertEqual(bank.collect(99),(1,None));snapshot=bank.snapshot();snapshot[0]['subject']='mutated'
        self.assertEqual(bank.to_config(),before)

    def test_pending_byte_budget_replacement_and_clear_selection(self):
        bank=rt.RemoteMessages(message_types=['A'],limit=90)
        self.assertEqual(bank.queue_attach('A',['TD:a'],0),0);before=bank.to_config()
        self.assertEqual(bank.queue_attach('A',['TD:'+'a'*80],0),5);self.assertEqual(bank.to_config(),before)
        self.assertEqual(bank.queue_attach('A',[''],1),0);self.assertEqual(bank.pending['A'],dict(attachments=[],priority=1))

    def test_publish_without_selection_and_bad_data_do_not_infer_schema(self):
        bank=rt.RemoteMessages(message_types=['A']);self.assertEqual(bank.publish('a',b'\0\xff'),0)
        self.assertEqual(bank.messages[0]['attachments'],[]);self.assertEqual(bank.messages[0]['data'],'00ff')
        self.assertEqual(bank.publish('missing'),1);self.assertEqual(bank.publish('A',{}),4)
        self.assertEqual(bank.publish('A',b'x'*(bank.limit//2+1)),5)


class RemoteMessagePersistenceTests(unittest.TestCase):
    def test_all_message_kinds_and_pending_selection_roundtrip_in_context(self):
        ctx=context(message_types=['ALARM_MSG_P']);send(ctx);ctx.remote_messages.alert('a','b','c','d');selected(ctx.remote_messages)
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved);self.assertEqual(restored.remote_messages.sequence,3)

    def test_queued_xml_replay_uses_saved_bytes_after_file_deletion(self):
        ctx=context();send(ctx);restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertNotIn('TD:note.xml',restored.files.files)
        self.assertEqual(restored.remote_messages.collect(1)[1]['data'],XML.hex())

    def test_invalid_constructor_and_context_service_types_reject(self):
        for options in ({'capacity':True},{'capacity':0},{'limit':0},{'limit':67108865},{'message_types':['A','a']},
                {'message_types':['bad type']},{'message_types':['A']*33},{'defaults':{'bad':'x'}},{'defaults':{'address':'\u00e9'}}):
            with self.assertRaises(ValueError):rt.RemoteMessages(**options)
        with self.assertRaises(TypeError):rt.ExecutionContext(remote_messages={})
        with self.assertRaises(ValueError):rt.RemoteMessages.from_config({'extra':1})

    def test_saved_sequence_order_bounds_and_capacity_are_checked(self):
        bank=rt.RemoteMessages();bank.alert('a','b','','');bank.alert('a','c','','');base=bank.to_config()
        for change in ({'sequence':True},{'sequence':0},{'sequence':2147483647},{'capacity':1},
                {'messages':[base['messages'][1],base['messages'][0]]},{'messages':[base['messages'][0]]*2}):
            with self.assertRaises(ValueError):rt.RemoteMessages.from_config({**base,**change})

    def test_saved_row_fields_payloads_xml_and_types_are_checked(self):
        ctx=context();send(ctx);base=ctx.remote_messages.to_config();original=base['messages'][0]
        for change in ({'extra':1},{'kind':'unknown'},{'data':'0'},{'data':'zz'},{'data':b'invalid'.hex()},
                {'attachments':['']},{'attachments':['TD:note.xml']},{'priority':True},{'xml_file':'../bad'}):
            saved=deepcopy(base);saved['messages']=[{**original,**change}]
            with self.assertRaises(ValueError):rt.RemoteMessages.from_config(saved)
        bank=rt.RemoteMessages(message_types=['A']);bank.publish('A');saved=bank.to_config();saved['messages'][0]['message_type']='B'
        with self.assertRaises(ValueError):rt.RemoteMessages.from_config(saved)

    def test_saved_pending_selections_and_aggregate_bytes_are_checked(self):
        bank=rt.RemoteMessages(message_types=['A']);bank.queue_attach('A',['TD:a'],0);base=bank.to_config()
        for pending in ({'B':base['pending']['A']},{'A':{'attachments':['TD:a'],'priority':2}},
                {'A':{'attachments':['TD:a'],'priority':0,'extra':1}},{'A':base['pending']['A'],'a':base['pending']['A']}):
            with self.assertRaises(ValueError):rt.RemoteMessages.from_config({**base,'pending':pending})
        bank.alert('a','b','','');saved=bank.to_config();saved['limit']=bank.used()-1
        with self.assertRaises(ValueError):rt.RemoteMessages.from_config(saved)

    def test_saved_state_and_collected_results_are_independent(self):
        bank=rt.RemoteMessages(message_types=['A']);bank.queue_attach('A',['TD:a'],1);bank.publish('A')
        saved=bank.to_config();restored=rt.RemoteMessages.from_config(saved)
        saved['messages'][0]['attachments'][0]='TD:changed';saved['pending']['A']['attachments'][0]='TD:changed'
        self.assertEqual(restored.messages[0]['attachments'],['TD:a']);self.assertEqual(restored.pending['A']['attachments'],['TD:a'])
        files=rt.MemoryFiles({'TD:a':'old'});row=restored.collect(1,files)[1];row['attachments'].clear()
        self.assertEqual(restored.pending['A']['attachments'],['TD:a'])

    def test_reports_record_offline_boundary_and_actual_source_calls(self):
        _,result=compile_program("paths[1]='' paths[2]='' QUEUE_ATTACH('A',paths,0,s) RMCN_ALERT('','','','',s) RMCN_SEND('a',paths,0,s)",decl=DECL)
        policy=result.report['remote_message_policy'];self.assertFalse(policy['controller_validated'])
        self.assertEqual([row['operation'] for row in policy['calls']],['QUEUE_ATTACH','RMCN_ALERT','RMCN_SEND'])


if __name__=='__main__':unittest.main()
