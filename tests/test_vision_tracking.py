"""Authored legacy tracking waits, allocation, maps, lookup and outbox tests."""
from copy import deepcopy
import json
import unittest

from karel2py import translate,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_vision_results import found,batch
from tests.test_vision_io import image_record


def work(number=1,x=2):return dict(work_id=number,result=found(x))
def arrival(at=15,number=1):return dict(at_ms=at,part=work(number))
def area_map(x=1):return dict(frame=3,points=[[x,2,3]])
def context(*,queues=None,runs=None,registers=None,io=None,**tracking):
    tracking['queues']={'1':dict(capacity=3,parts=[work()]),'2':dict(capacity=3)} if queues is None else queues
    return rt.ExecutionContext(vision=rt.VisionServices(registers=registers,processes={'SCAN':dict(views=[1],runs=[] if runs is None else runs)},tracking=tracking,io=io))


def execute(body,ctx,decl='s,n:INTEGER',**options):
    p,result=compile_program(body,decl=decl,context=ctx,sleep=options.pop('sleep',lambda _:None),**options);return p.run(),p,result


class LegacyQueueTests(unittest.TestCase):
    def test_get_part_copies_value_and_records_encoder_receipt(self):
        ctx=context();values,_,_=execute('V_GET_QUEUE(1,1,0,s)',ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.registers[1]['offset'].values['X'],2.)
        self.assertEqual(ctx.vision.tracking.allocations,{1:{'queue':1,'work_id':1}});self.assertEqual(ctx.vision.tracking.triggers,{1:{'queue':1,'work_id':1,'encoder':-40}})
        self.assertEqual(ctx.vision.tracking.queues[1]['parts'],[])

    def test_reallocate_to_downstream_queue_once(self):
        ctx=context();values,_,_=execute('V_GET_QUEUE(1,1,0,s) V_RALC_QUEUE(2,1,s)',ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.tracking.queues[2]['parts'][0]['work_id'],1);self.assertEqual(ctx.vision.tracking.allocations,{})
        values,_,_=execute('V_RALC_QUEUE(2,1,s)',ctx);self.assertEqual(values['S'],6);self.assertEqual(len(ctx.vision.tracking.queues[2]['parts']),1)

    def test_adjusted_offset_can_be_reallocated_with_original_identity(self):
        ctx=context();execute('V_GET_QUEUE(1,1,0,s) V_ADJ_2D(1,3,0,s) V_RALC_QUEUE(2,1,s)',ctx)
        self.assertEqual(ctx.vision.tracking.queues[2]['parts'][0]['result']['offset'].values['X'],5.)

    def test_full_downstream_queue_preserves_receipt(self):
        ctx=context(queues={'1':dict(capacity=1,parts=[work()]),'2':dict(capacity=1,parts=[work(2)])})
        values,_,_=execute('V_GET_QUEUE(1,1,0,s) V_RALC_QUEUE(2,1,s)',ctx);self.assertEqual(values['S'],4);self.assertIn(1,ctx.vision.tracking.allocations)

    def test_duplicate_downstream_identity_preserves_receipt(self):
        ctx=context(queues={'1':dict(capacity=1,parts=[work()]),'2':dict(capacity=2,parts=[work()])})
        values,_,_=execute('V_GET_QUEUE(1,1,0,s) V_RALC_QUEUE(2,1,s)',ctx);self.assertEqual(values['S'],5);self.assertIn(1,ctx.vision.tracking.allocations)

    def test_invalid_queue_register_timeout_and_missing_receipt(self):
        for call,code in [('V_GET_QUEUE(3,1,0,s)',2),('V_GET_QUEUE(1,0,0,s)',2),('V_GET_QUEUE(1,1,86400001,s)',2),('V_RALC_QUEUE(2,1,s)',1)]:
            ctx=context();values,_,_=execute(call,ctx);self.assertEqual(values['S'],code);self.assertEqual(len(ctx.vision.tracking.queues[1]['parts']),1)

    def test_initialize_clears_stored_parts_and_receipts_but_keeps_external_plans(self):
        ctx=context(queues={'1':dict(capacity=3,parts=[work()],arrivals=[arrival(20,2)])})
        execute('V_GET_QUEUE(1,1,0,s) V_INIT_QUEUE(1,s)',ctx)
        queue=ctx.vision.tracking.queues[1];self.assertEqual(queue['parts'],[]);self.assertEqual(len(queue['arrivals']),1);self.assertEqual(ctx.vision.tracking.allocations,{})
        self.assertIn(1,ctx.vision.registers);values,_,_=execute('V_GET_QUEUE(1,2,20,s)',ctx);self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.tracking.allocations[2]['work_id'],2)

    def test_host_feed_is_checked_and_detached(self):
        ctx=context(queues={'1':dict(capacity=1)});row=found(7);self.assertEqual(ctx.vision.tracking.enqueue(1,1,row),0);row['offset'].values['X']=99
        self.assertEqual(ctx.vision.tracking.enqueue(1,1,found()),5);self.assertEqual(ctx.vision.tracking.enqueue(1,2,found()),4)
        execute('V_GET_QUEUE(1,1,0,s)',ctx);self.assertEqual(ctx.vision.registers[1]['offset'].values['X'],7.)

    def test_core_get_offset_invalidates_previous_queue_receipt(self):
        ctx=context(runs=[batch(found(8))]);execute("V_GET_QUEUE(1,1,0,s) V_RUN_FIND('SCAN',0,s) V_GET_OFFSET('SCAN',1,s)",ctx)
        self.assertEqual(ctx.vision.tracking.allocations,{});values,_,_=execute('V_RALC_QUEUE(2,1,s)',ctx);self.assertEqual(values['S'],6)

    def test_saved_allocation_can_be_reallocated_without_live_links(self):
        ctx=context();execute('V_GET_QUEUE(1,1,0,s)',ctx);restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        execute('V_RALC_QUEUE(2,1,s)',restored);self.assertEqual(restored.vision.tracking.queues[2]['parts'][0]['work_id'],1);self.assertIn(1,ctx.vision.tracking.allocations)


class QueueWaitTests(unittest.TestCase):
    def test_wait_uses_bounded_steps_and_inclusive_arrival_deadline(self):
        ctx=context(queues={'1':dict(capacity=1,arrivals=[arrival(25)])});delays=[]
        values,_,_=execute('V_GET_QUEUE(1,1,25,s)',ctx,sleep=delays.append)
        self.assertEqual(values['S'],0);self.assertEqual(delays,[.01,.01,.005]);self.assertEqual(ctx.vision.tracking.queues[1]['elapsed_ms'],25)

    def test_timeout_preserves_future_arrival_for_later_read(self):
        ctx=context(queues={'1':dict(capacity=1,arrivals=[arrival(21)])});values,_,_=execute('V_GET_QUEUE(1,1,20,s)',ctx)
        self.assertEqual(values['S'],117249);self.assertEqual(len(ctx.vision.tracking.queues[1]['arrivals']),1);self.assertNotIn(1,ctx.vision.registers)
        values,_,_=execute('V_GET_QUEUE(1,1,1,s)',ctx);self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.tracking.queues[1]['elapsed_ms'],21)

    def test_zero_timeout_materializes_due_arrival_without_sleep(self):
        ctx=context(queues={'1':dict(capacity=1,arrivals=[arrival(0)])});delays=[];values,_,_=execute('V_GET_QUEUE(1,1,0,s)',ctx,sleep=delays.append)
        self.assertEqual((values['S'],delays),(0,[]))

    def test_negative_timeout_can_wait_for_supplied_arrival(self):
        ctx=context(queues={'1':dict(capacity=1,arrivals=[arrival(12)])});values,_,_=execute('V_GET_QUEUE(1,1,-1,s)',ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.tracking.queues[1]['elapsed_ms'],12)

    def test_wait_does_not_create_pause_notification(self):
        ctx=context(queues={'1':dict(capacity=1,arrivals=[arrival(12)])})
        values,_,_=execute('n=0 CONDITION[1]: WHEN PAUSE DO n=n+1 ENDCONDITION ENABLE CONDITION[1] V_GET_QUEUE(1,1,20,s)',ctx)
        self.assertEqual((values['N'],values['S']),(0,0))

    def test_pause_resume_keeps_original_request_and_remainder(self):
        ctx=context(queues={'1':dict(capacity=1,arrivals=[arrival(25)])});p,_=compile_program('s=99 V_GET_QUEUE(1,1,50,s)',context=ctx,sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['S'],99);self.assertEqual(ctx.vision.tracking.queues[1]['elapsed_ms'],10)
        with self.assertRaisesRegex(ValueError,'pending tracking'):ctx.to_config()
        p._state._sleep=lambda _:None;p.resume();self.assertEqual(p.snapshot()['S'],0);self.assertEqual(ctx.vision.sequence,1);self.assertEqual(ctx.vision.tracking.pending,{})

    def test_stop_at_exhausted_sequence_releases_wait_without_replaying(self):
        ctx=context(queues={'1':dict(capacity=1,arrivals=[arrival(25)])});p,_=compile_program('s=99 V_GET_QUEUE(1,1,50,s)',context=ctx,sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        ctx.vision.sequence=2147483646;p.stop()
        self.assertEqual(ctx.vision.tracking.pending,{});self.assertEqual(ctx.vision.history[-1]['status'],8);self.assertEqual(p.snapshot()['S'],99)
        self.assertEqual(len(ctx.vision.tracking.queues[1]['arrivals']),1);ctx.to_config()

    def test_budget_failure_releases_indefinite_wait(self):
        ctx=context(queues={'1':dict(capacity=1)});p,_=compile_program('s=99 V_GET_QUEUE(1,1,-1,s)',context=ctx,sleep=lambda _:None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=8)
        self.assertEqual(ctx.vision.tracking.pending,{});self.assertEqual(ctx.vision.history[-1]['status'],9);self.assertEqual(p.snapshot()['S'],99);ctx.to_config()

    def test_pending_queue_and_register_are_exclusive(self):
        ctx=context(queues={'1':dict(capacity=1,arrivals=[arrival(25)]),'2':dict(capacity=1,parts=[work(2)])})
        p,_=compile_program('V_GET_QUEUE(1,1,50,s)',context=ctx,sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        for call in ('V_GET_QUEUE(1,2,0,s)','V_GET_QUEUE(2,1,0,s)','V_INIT_QUEUE(1,s)'):
            values,_,_=execute(call,ctx);self.assertEqual(values['S'],3)
        self.assertEqual(len(ctx.vision.tracking.queues[2]['parts']),1);p.stop()

    def test_pending_register_blocks_core_overwrite_adjust_and_reallocation(self):
        ctx=context(queues={'1':dict(capacity=1,parts=[work()]),'2':dict(capacity=1,arrivals=[arrival(25,2)])},runs=[batch(found(8))])
        execute('V_GET_QUEUE(1,1,0,s)',ctx);p,_=compile_program('V_GET_QUEUE(2,1,50,s)',context=ctx,sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        execute("V_RUN_FIND('SCAN',0,s)",ctx)
        for call in ("V_GET_OFFSET('SCAN',1,s)",'V_ADJ_2D(1,3,0,s)','V_RALC_QUEUE(1,1,s)'):
            values,_,_=execute(call,ctx);self.assertEqual(values['S'],3)
        self.assertEqual(ctx.vision.processes['SCAN']['cursor'],0);self.assertEqual(ctx.vision.registers[1]['offset'].values['X'],2.);p.stop()

    def test_host_can_feed_a_finite_pending_read(self):
        ctx=context(queues={'1':dict(capacity=1)})
        def feed(_):self.assertEqual(ctx.vision.tracking.enqueue(1,1,found(7)),0)
        values,_,_=execute('V_GET_QUEUE(1,1,20,s)',ctx,sleep=feed)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.registers[1]['offset'].values['X'],7.)

    def test_clock_exhaustion_does_not_start_or_consume_request(self):
        ctx=context(queues={'1':dict(capacity=1,elapsed_ms=2147483646)})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'clock exhausted'):execute('V_GET_QUEUE(1,1,1,s)',ctx)
        self.assertEqual(ctx.vision.sequence,0);self.assertEqual(ctx.vision.tracking.pending,{})


class TrackingResultTests(unittest.TestCase):
    def test_vt_result_outputs_share_core_cursor_and_preserve_unknown_tails(self):
        ctx=rt.ExecutionContext(vision=rt.VisionServices(processes={'SCAN':dict(views=[1],runs=[batch(found(3),found(9))])}))
        values,_,_=execute("V_RUN_FIND('SCAN',0,s) VT_GET_FOUND('SCAN',model_no,encoder,p,points,measures,s) V_GET_OFFSET('SCAN',1,s)",ctx,'s,model_no,encoder:INTEGER p:XYZWPR points:ARRAY[4] OF XYZWPR measures:ARRAY[10] OF REAL')
        self.assertEqual((values['MODEL_NO'],values['ENCODER'],values['P']['X']),(21,-40,3.));self.assertEqual(values['POINTS'][1]['X'],{'uninitialized':True});self.assertEqual(ctx.vision.registers[1]['offset'].values['X'],9.)
        self.assertEqual(ctx.vision.history[1]['operation'],'VT_GET_FOUND')

    def test_fixed_array_shapes_and_writable_outputs_remain_checked(self):
        for decl in ('s,n:INTEGER p:XYZWPR points:ARRAY[3] OF XYZWPR measures:ARRAY[10] OF REAL','s,n:INTEGER p:XYZWPR points:ARRAY[4] OF XYZWPR measures:ARRAY[9] OF REAL'):
            with self.assertRaises(TranslationError):compile_program("VT_GET_FOUND('SCAN',n,s,p,points,measures,s)",decl=decl)

    def test_get_found_alias_failure_does_not_consume_result(self):
        ctx=context(runs=[batch(found())]);execute("V_RUN_FIND('SCAN',0,s)",ctx)
        p,_=compile_program("VT_GET_FOUND('SCAN',n,n,p,points,measures,s)",decl='s,n:INTEGER p:XYZWPR points:ARRAY[4] OF XYZWPR measures:ARRAY[10] OF REAL',context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(ctx.vision.processes['SCAN']['cursor'],0)

    def test_empty_failed_or_missing_vt_results_preserve_outputs(self):
        for runs,body,code in [([batch()],"V_RUN_FIND('SCAN',0,s) ",117151),([batch(status=91)],"V_RUN_FIND('SCAN',0,s) ",91),([],"",1)]:
            ctx=context(runs=runs);values,_,_=execute(body+"n=99 VT_GET_FOUND('SCAN',n,encoder,p,points,measures,s)",ctx,'s,n,encoder:INTEGER p:XYZWPR points:ARRAY[4] OF XYZWPR measures:ARRAY[10] OF REAL')
            self.assertEqual((values['S'],values['N']),(code,99))

    def test_lookup_uses_explicit_case_insensitive_distinct_banks(self):
        ctx=context(ids={'areas':{'pick':2},'lines':{'line':3},'trays':{'tray':4}});values,_,_=execute("area=VT_GET_AREID('PICK') line_no=VT_GET_LINID('line') tray=VT_GET_TRYID('tray')",ctx,'area,line_no,tray:INTEGER')
        self.assertEqual(values,{'AREA':2,'LINE_NO':3,'TRAY':4})

    def test_unknown_name_is_explicit_error_without_fabricating_id(self):
        ctx=context();p,_=compile_program("n=99 n=VT_GET_AREID('missing')",context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not configured'):p.run()
        self.assertEqual(p.snapshot()['N'],99);self.assertEqual(ctx.vision.history[-1]['status'],2)

    def test_only_documented_irvu_wrappers_get_native_library_lowering(self):
        p,_=compile_program("n=VT_GET_AREID('PICK')",routines='ROUTINE VT_GET_AREID(area_name:STRING):INTEGER FROM IRVUTILVR',context=context())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicitly linked'):p.run()


class SensorAndProcessTests(unittest.TestCase):
    def test_start_stop_flags_are_explicit_and_do_not_generate_data(self):
        ctx=context(processes={'SCAN':{'running':False}});execute("V_START_VTRK('SCAN',s) V_START_VTRK('SCAN',s)",ctx);self.assertTrue(ctx.vision.tracking.processes['SCAN']['running'])
        self.assertEqual(ctx.vision.processes['SCAN']['runs'],[]);execute("V_STOP_VTRK('SCAN',s) V_STOP_VTRK('SCAN',s)",ctx);self.assertFalse(ctx.vision.tracking.processes['SCAN']['running'])

    def test_unconfigured_tracking_process_is_rejected(self):
        values,_,_=execute("V_START_VTRK('SCAN',s)",context());self.assertEqual(values['S'],2)

    def test_successful_map_replaces_and_failure_keeps_last_map(self):
        ctx=context(sensors={'DEPTH':{'responses':[{'status':0,'map':area_map(7)},{'status':95}],'map':area_map(2)}})
        execute("V_ACQ_VAMAP('depth',FALSE,VEC(0,0,0),s)",ctx);self.assertEqual(ctx.vision.tracking.sensors['DEPTH']['map']['points'][0][0],7.)
        values,_,_=execute("V_ACQ_VAMAP('depth',FALSE,VEC(0,0,0),s)",ctx);self.assertEqual(values['S'],95);self.assertEqual(ctx.vision.tracking.sensors['DEPTH']['map']['points'][0][0],7.)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'area-map response'):execute("V_ACQ_VAMAP('depth',FALSE,VEC(0,0,0),s)",ctx)

    def test_internal_map_parameters_reject_nonzero_or_partial_without_consuming(self):
        for call in ("V_ACQ_VAMAP('DEPTH',TRUE,VEC(0,0,0),s)","V_ACQ_VAMAP('DEPTH',FALSE,VEC(1,0,0),s)"):
            ctx=context(sensors={'DEPTH':{'responses':[{'status':0,'map':area_map()}]}});values,_,_=execute(call,ctx)
            self.assertEqual(values['S'],2);self.assertEqual(len(ctx.vision.tracking.sensors['DEPTH']['responses']),1)

    def test_clear_map_is_idempotent_and_keeps_future_replies(self):
        ctx=context(sensors={'DEPTH':{'responses':[{'status':0,'map':area_map()}],'map':area_map(5)}});execute("V_CLR_VAMAP('DEPTH',s) V_CLR_VAMAP('DEPTH',s)",ctx)
        self.assertIsNone(ctx.vision.tracking.sensors['DEPTH']['map']);self.assertEqual(len(ctx.vision.tracking.sensors['DEPTH']['responses']),1)

    def test_supplied_map_and_saved_configuration_are_detached(self):
        value=area_map();ctx=context(sensors={'DEPTH':{'responses':[{'status':0,'map':value}]}});value['points'][0][0]=99
        execute("V_ACQ_VAMAP('DEPTH',FALSE,VEC(0,0,0),s)",ctx);config=ctx.to_config();restored=rt.ExecutionContext.from_config(config);config['vision']['tracking']['sensors']['DEPTH']['map']['points'][0][0]=99
        self.assertEqual(restored.vision.tracking.sensors['DEPTH']['map']['points'][0][0],1.)


class VisionOutboxTests(unittest.TestCase):
    def test_latest_completion_is_staged_without_delivery_or_cursor_consumption(self):
        ctx=context(runs=[batch(found(7))]);values,_,_=execute("V_RUN_FIND('SCAN',0,s) V_IRCONNECT('part found',2,0,s)",ctx)
        self.assertEqual(values['S'],0);packet=ctx.vision.tracking.outbox[0];self.assertEqual((packet['description'],packet['priority'],packet['process']),('part found',2,'SCAN'))
        self.assertEqual(packet['result']['results'][0]['offset']['value']['X'],7.);self.assertEqual(packet['images'],{});self.assertEqual(ctx.vision.processes['SCAN']['cursor'],0)
        ctx.vision.processes['SCAN']['active']['results'][0]['offset'].values['X']=99;self.assertEqual(packet['result']['results'][0]['offset']['value']['X'],7.)

    def test_latest_failure_replaces_previous_success_for_notifications(self):
        ctx=context(runs=[batch(found()),batch(status=96)]);execute("V_RUN_FIND('SCAN',0,s) V_RUN_FIND('SCAN',0,s) V_IRCONNECT('failed',3,0,s)",ctx)
        self.assertEqual(ctx.vision.tracking.outbox[0]['result']['status'],96);self.assertEqual(ctx.vision.tracking.outbox[0]['result']['results'],[])

    def test_invalid_priority_register_and_missing_latest_preserve_outbox(self):
        for call,code in [("V_IRCONNECT('x',4,0,s)",2),("V_IRCONNECT('x',0,1,s)",2),("V_IRCONNECT('x',0,0,s)",1)]:
            ctx=context();values,_,_=execute(call,ctx);self.assertEqual(values['S'],code);self.assertEqual(ctx.vision.tracking.outbox,[])

    def test_outbox_capacity_never_discards_uncollected_packets(self):
        ctx=context(runs=[batch(found())],outbox_limit=1);values,_,_=execute("V_RUN_FIND('SCAN',0,s) V_IRCONNECT('first',0,0,s) V_IRCONNECT('second',0,0,s)",ctx)
        self.assertEqual(values['S'],4);self.assertEqual([v['description'] for v in ctx.vision.tracking.outbox],['first'])

    def test_payload_limit_rejects_without_consuming_result(self):
        ctx=context(runs=[batch(found())],payload_limit=100);values,_,_=execute("V_RUN_FIND('SCAN',0,s) V_IRCONNECT('too large',0,0,s)",ctx)
        self.assertEqual(values['S'],4);self.assertEqual(ctx.vision.tracking.outbox,[]);self.assertEqual(ctx.vision.processes['SCAN']['cursor'],0)

    def test_optional_images_are_supplied_data_and_roundtrip(self):
        ctx=context(runs=[dict(batch(found(),view=1),image_reg=1)],io={'image_count':1,'images':{'1':image_record()}},include_images=True)
        execute("V_FIND_VIEW('SCAN',1,1,s) V_IRCONNECT('image',1,0,s)",ctx);packet=ctx.vision.tracking.outbox[0]
        self.assertEqual(packet['images']['1']['image']['pixels'],image_record()['image']['pixels'])
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())));self.assertEqual(restored.vision.tracking.outbox,ctx.vision.tracking.outbox)

    def test_packet_restore_checks_schema_ids_and_image_ownership(self):
        ctx=context(runs=[batch(found())],io={'image_count':1,'images':{'1':image_record()}},include_images=True);execute("V_RUN_FIND('SCAN',0,s) V_IRCONNECT('image',1,0,s)",ctx);original=ctx.to_config()
        for field,value in [('sequence',0),('priority',True),('process','OTHER'),('callback','untrusted')]:
            config=deepcopy(original);config['vision']['tracking']['outbox'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)


class TrackingGuardTests(unittest.TestCase):
    def test_public_metadata_records_twelve_offline_legacy_calls(self):
        policy=translate('PROGRAM T BEGIN END T').report['vision_tracking_policy']
        self.assertEqual(len(policy['calls']),12);self.assertFalse(policy['controller_validated']);self.assertIn('no delivery',policy['outbox'])

    def test_missing_service_fails_without_inventing_tracking_state(self):
        ctx=rt.ExecutionContext(vision=rt.VisionServices())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'vision tracking'):execute('V_INIT_QUEUE(1,s)',ctx)

    def test_sequence_exhaustion_precedes_queue_map_and_outbox_mutations(self):
        for call in ('V_GET_QUEUE(1,1,0,s)','V_INIT_QUEUE(1,s)',"V_ACQ_VAMAP('DEPTH',FALSE,VEC(0,0,0),s)","V_IRCONNECT('x',0,0,s)"):
            ctx=context(sensors={'DEPTH':{'responses':[{'status':0,'map':area_map()}]}});ctx.vision.sequence=2147483646;before=ctx.vision.to_config()
            with self.subTest(call=call),self.assertRaisesRegex(rt.KarelRuntimeError,'sequence exhausted'):execute(call,ctx)
            self.assertEqual(ctx.vision.to_config(),before)

    def test_outputs_and_active_for_guards_remain_checked(self):
        for body in ('V_GET_QUEUE(1,1,0,TRUE)','FOR n=1 TO 2 DO V_INIT_QUEUE(1,n) ENDFOR'):
            with self.subTest(body=body),self.assertRaises(TranslationError):compile_program(body)


class TrackingConfigurationTests(unittest.TestCase):
    def test_bad_queue_keys_fields_capacity_and_duplicates(self):
        for queues in ({'01':{'capacity':1}},{'0':{'capacity':1}},{'1':{'capacity':True}},{'1':{'capacity':1,'callback':1}},
            {'1':{'capacity':1,'parts':[work(),work(2)]}},{'1':{'capacity':3,'parts':[work(),work()]}},
            {'1':{'capacity':1,'arrivals':[arrival(20),arrival(10,2)]}}):
            with self.subTest(queues=queues),self.assertRaises(ValueError):context(queues=queues)

    def test_invalid_process_ids_map_and_tracking_options(self):
        for options in ({'processes':{'ABSENT':{'running':True}}},{'processes':{'SCAN':{'running':1}}},{'ids':{'unknown':{}}},{'ids':{'areas':{'A':1,'B':1}}},
            {'ids':{'lines':{'A':True}}},{'latest':'SCAN'},{'include_images':1},{'outbox_limit':0},{'payload_limit':0},
            {'sensors':{'DEPTH':{'responses':[{'status':0}]}}},{'sensors':{'DEPTH':{'responses':[{'status':3,'map':area_map()}]}}},
            {'sensors':{'DEPTH':{'responses':[{'status':0,'map':{'frame':1,'points':[[float('inf'),0,0]]}}]}}}):
            with self.subTest(options=options),self.assertRaises(ValueError):context(**options)

    def test_bad_receipts_triggers_and_duplicate_work_identity(self):
        ctx=context();execute('V_GET_QUEUE(1,1,0,s)',ctx);original=ctx.to_config()
        for update in ('missing_trigger','wrong_encoder','missing_register','duplicate_part'):
            config=deepcopy(original)
            if update=='missing_trigger':config['vision']['tracking']['triggers']={}
            elif update=='wrong_encoder':config['vision']['tracking']['triggers']['1']['encoder']=8
            elif update=='missing_register':config['vision']['registers']={}
            else:config['vision']['tracking']['queues']['1']['parts']=[dict(work_id=1,result=config['vision']['registers']['1'])]
            with self.subTest(update=update),self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)

    def test_cumulative_map_point_limit_includes_current_maps(self):
        sensors={str(i):{'responses':[],'map':{'frame':0,'points':[[1,2,3]]*4096}} for i in range(8)}
        with self.assertRaisesRegex(ValueError,'32767'):context(sensors=sensors)

    def test_cumulative_workpiece_and_map_reply_limits_are_enforced(self):
        value=found()
        with self.assertRaises(ValueError):context(queues={'1':dict(capacity=4096,parts=[dict(work_id=i,result=value) for i in range(1,4097)],arrivals=[dict(at_ms=5,part=dict(work_id=4097,result=value))])})
        with self.assertRaises(ValueError):context(sensors={'DEPTH':{'responses':[{'status':1}]*4097}})


if __name__=='__main__':unittest.main()
