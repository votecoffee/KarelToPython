"""Authored VT queue allocation, nullable snapshots, PATH editing and policy tests."""
from copy import deepcopy
import json
import unittest

from karel2py import translate,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,pose
from tests.test_vision_results import found,batch

SCHEMA='''TYPE
coord_t=STRUCTURE x:REAL y:REAL z:REAL w:REAL p:REAL r:REAL ENDSTRUCTURE
part_t=STRUCTURE work_id:INTEGER model_id:INTEGER tray_id:INTEGER enc_count:INTEGER offset:coord_t found_pos:coord_t meas_value:ARRAY[10] OF REAL ENDSTRUCTURE
header_t=STRUCTURE area_id:INTEGER num_parts:INTEGER ENDSTRUCTURE
queue_t=PATH NODEDATA=part_t,PATHHEADER=header_t'''
DECL='s,n,m,work_id,encoder:INTEGER cfg:CONFIG p,newp:XYZWPR positions:ARRAY[4] OF XYZWPR measures,updates:ARRAY[10] OF REAL duplicate:BOOLEAN'
SETUP="CNV_STR_CONF('N',cfg,s) p=POS(1,2,3,0,0,0,cfg) "
PUT='VT_PUT_QUEUE(1,12,0,100,5,p,positions,measures,s) '
GET='VT_GET_QUEUE(1,1,0,1,m,work_id,s) '
PATH_DECL=DECL+' q:queue_t'


def context(*,capacity=8,flags=0,travel=0,**options):
    vt=dict(lines={'1':dict(areas=[1,2],capacity=capacity,flags=flags,speed=100)},areas={'1':dict(line=1,span=1000,travel_ms=travel,frame=2),'2':dict(line=1,span=1000,frame=3)})
    for key,value in options.items():vt[key]=value
    return rt.ExecutionContext(vision=rt.VisionServices(processes={'SCAN':dict(views=[1],runs=[batch(found(9))])},tracking={'ids':{'areas':{'PICK':1,'NEXT':2},'lines':{'LINE':1},'trays':{'TRAY':3}},'vt':vt}))


def execute(body,ctx=None,*,decl=DECL,prefix='',setup=True,**options):
    ctx=ctx or context();p,result=compile_program((SETUP if setup else '')+body,decl=decl,prefix=prefix,context=ctx,sleep=options.pop('sleep',lambda _:None),**options)
    return p.run(),ctx,p,result


class PutAllocationTests(unittest.TestCase):
    def test_put_missing_views_and_measurements_allocates_offset(self):
        values,ctx,_,_=execute(PUT+GET)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.registers[1]['views'],{});self.assertEqual(ctx.vision.registers[1]['measurements'],[None]*10)
        self.assertEqual(ctx.vision.registers[1]['frame'],2);self.assertEqual(ctx.vision.tracking.vt.allocations[1]['part']['work_id'],12)

    def test_partial_measurements_and_populated_view_are_copied(self):
        values,ctx,_,_=execute('positions[2]=p measures[1]=1.5 measures[3]=3.5 '+PUT+GET)
        record=ctx.vision.registers[1];self.assertEqual(set(record['views']),{'2'});self.assertEqual(record['measurements'][:4],[1.5,None,3.5,None])
        values,_,_,_=execute('s=IRVU_VRGETMEAS(1,2,number)',ctx,decl=DECL+' number:REAL');self.assertEqual(values['S'],1)

    def test_duplicate_reports_true_without_new_index_or_part(self):
        values,ctx,_,_=execute('VT_PUT_QUE2(1,12,0,100,5,p,positions,measures,duplicate,s) VT_PUT_QUE2(1,13,0,100,5,p,positions,measures,duplicate,s)')
        self.assertEqual((values['S'],values['DUPLICATE']),(0,True));self.assertEqual(ctx.vision.tracking.vt.lines[1]['sequence'],1)

    def test_nonzero_caller_work_id_is_unique_even_when_geometry_changes(self):
        values,ctx,_,_=execute(PUT+'p.x=9 VT_PUT_QUE2(1,12,0,101,6,p,positions,measures,duplicate,s)')
        self.assertTrue(values['DUPLICATE']);self.assertEqual(len(ctx.vision.tracking.vt.lines[1]['parts']),1)

    def test_zero_caller_id_uses_distinct_internal_indexes(self):
        _,ctx,_,_=execute('VT_PUT_QUEUE(1,0,0,100,5,p,positions,measures,s) VT_PUT_QUEUE(1,0,0,101,5,p,positions,measures,s)')
        self.assertEqual([(v['uid'],v['work_id']) for v in ctx.vision.tracking.vt.lines[1]['parts']],[(1,0),(2,0)])

    def test_capacity_failure_preserves_duplication_output(self):
        ctx=context(capacity=1);values,_,_,_=execute(PUT+'duplicate=TRUE VT_PUT_QUE2(1,13,0,101,5,p,positions,measures,duplicate,s)',ctx)
        self.assertEqual((values['S'],values['DUPLICATE']),(4,True));self.assertEqual(ctx.vision.tracking.vt.lines[1]['sequence'],1)

    def test_partial_pose_view_is_rejected_atomically(self):
        values,ctx,_,_=execute('positions[1].x=1 '+PUT);self.assertEqual(values['S'],2);self.assertEqual(ctx.vision.tracking.vt.lines[1]['parts'],[])

    def test_model_and_work_selectors_capture_uninitialized_as_unspecified(self):
        values,ctx,_,_=execute(PUT+GET);self.assertEqual(values['S'],0);self.assertEqual(values['M'],{'uninitialized':True});self.assertEqual(values['WORK_ID'],{'uninitialized':True})

    def test_explicit_zero_selector_is_not_unspecified(self):
        values,ctx,_,_=execute(PUT+'m=0 '+GET);self.assertEqual(values['S'],117249);self.assertEqual(len(ctx.vision.tracking.vt.lines[1]['parts']),1)

    def test_specific_caller_id_uses_external_not_internal_index(self):
        values,_,_,_=execute(PUT+'work_id=12 '+GET);self.assertEqual(values['S'],0)
        values,ctx,_,_=execute(PUT+'work_id=1 '+GET);self.assertEqual(values['S'],117249);self.assertEqual(len(ctx.vision.tracking.vt.lines[1]['parts']),1)

    def test_ack_handled_and_failed_discard_once(self):
        for ack in (1,3):
            values,ctx,_,_=execute(PUT+GET+f'VT_ACK_QUEUE(1,1,{ack},s) VT_ACK_QUEUE(1,1,{ack},s)')
            self.assertEqual(values['S'],6);self.assertEqual(ctx.vision.tracking.vt.allocations,{});self.assertEqual(ctx.vision.tracking.vt.lines[1]['parts'],[])

    def test_ack_cancel_forwards_adjusted_result_downstream(self):
        values,ctx,_,_=execute(PUT+GET+'V_ADJ_2D(1,4,0,s) VT_ACK_QUEUE(1,1,2,s) VT_GET_QUEUE(2,1,0,1,m,work_id,s)')
        self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.registers[1]['offset'].values['X'],5.);self.assertEqual(ctx.vision.registers[1]['frame'],3)
        self.assertEqual(ctx.vision.tracking.vt.allocations[1]['part']['passed'],[1])

    def test_outstanding_allocation_blocks_reuse_and_core_overwrite(self):
        ctx=context();execute(PUT+GET,ctx)
        values,_,_,_=execute('VT_GET_QUEUE(2,1,0,1,m,work_id,s)',ctx);self.assertEqual(values['S'],3)
        values,_,_,_=execute("V_RUN_FIND('SCAN',0,s) V_GET_OFFSET('SCAN',1,s)",ctx);self.assertEqual(values['S'],3);self.assertEqual(ctx.vision.processes['SCAN']['cursor'],0)

    def test_invalid_ack_area_or_code_preserves_receipt(self):
        ctx=context();execute(PUT+GET,ctx)
        for call,expected in [('VT_ACK_QUEUE(2,1,1,s)',6),('VT_ACK_QUEUE(1,1,0,s)',2)]:
            values,_,_,_=execute(call,ctx);self.assertEqual(values['S'],expected);self.assertIn(1,ctx.vision.tracking.vt.allocations)

    def test_tray_tags_require_configuration_and_que2_rejects_trays(self):
        values,ctx,_,_=execute('VT_PUT_QUEUE(1,12,3,100,5,p,positions,measures,s)');self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.tracking.vt.lines[1]['parts'][0]['tray'],3)
        values,ctx,_,_=execute('VT_PUT_QUE2(1,12,3,100,5,p,positions,measures,duplicate,s)');self.assertEqual(values['S'],2);self.assertEqual(ctx.vision.tracking.vt.lines[1]['parts'],[])


class WaitingAndSnapshotTests(unittest.TestCase):
    def test_bounded_wait_and_time_estimate(self):
        ctx=context(travel=25);execute(PUT,ctx);delays=[]
        values,_,_,_=execute('VT_GET_TIME(1,1,m,work_id,n,s) VT_GET_QUEUE(1,1,25,1,m,work_id,s)',ctx,sleep=delays.append)
        self.assertEqual((values['N'],values['S']),(25,0));self.assertEqual(delays,[.01,.01,.005])

    def test_ready_time_is_negative_and_lookup_does_not_consume(self):
        values,ctx,_,_=execute(PUT+'VT_GET_TIME(1,1,m,work_id,n,s)');self.assertEqual(values['N'],-1);self.assertEqual(len(ctx.vision.tracking.vt.lines[1]['parts']),1)

    def test_timeout_retains_part_and_later_read_completes(self):
        ctx=context(travel=21);execute(PUT,ctx);values,_,_,_=execute('VT_GET_QUEUE(1,1,20,1,m,work_id,s)',ctx);self.assertEqual(values['S'],117249)
        values,_,_,_=execute('VT_GET_QUEUE(1,1,1,1,m,work_id,s)',ctx);self.assertEqual(values['S'],0)

    def test_pause_resume_preserves_one_request_and_blocks_save(self):
        ctx=context(travel=25);execute(PUT,ctx);p,_=compile_program('s=99 VT_GET_QUEUE(1,1,30,1,m,work_id,s)',decl=DECL,context=ctx,sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        with self.assertRaisesRegex(ValueError,'pending VT'):ctx.to_config()
        p._state._sleep=lambda _:None;p.resume();self.assertEqual(p.snapshot()['S'],0);self.assertEqual(ctx.vision.sequence,2);self.assertEqual(ctx.vision.tracking.vt.pending,{})

    def test_stop_after_sequence_exhaustion_releases_reservation(self):
        ctx=context(travel=25);execute(PUT,ctx);p,_=compile_program('s=99 VT_GET_QUEUE(1,1,30,1,m,work_id,s)',decl=DECL,context=ctx,sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        ctx.vision.sequence=2147483646;p.stop();self.assertEqual(ctx.vision.history[-1]['status'],8);self.assertEqual(p.snapshot()['S'],99)
        self.assertEqual(len(ctx.vision.tracking.vt.lines[1]['parts']),1);ctx.to_config()

    def test_indefinite_wait_budget_failure_cleans_up(self):
        ctx=context();p,_=compile_program('s=99 VT_GET_QUEUE(1,1,-1,1,m,work_id,s)',decl=DECL,context=ctx,sleep=lambda _:None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=8)
        self.assertEqual(ctx.vision.history[-1]['status'],9);self.assertEqual(ctx.vision.tracking.vt.pending,{});ctx.to_config()

    def test_pending_area_and_register_reject_competing_reads(self):
        ctx=context(travel=25);execute(PUT,ctx);p,_=compile_program('VT_GET_QUEUE(1,1,30,1,m,work_id,s)',decl=DECL,context=ctx,sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        for call in ('VT_GET_QUEUE(1,2,0,1,m,work_id,s)','VT_GET_QUEUE(2,1,0,1,m,work_id,s)','VT_CLR_QUEUE(1,s)'):
            values,_,_,_=execute(call,ctx);self.assertEqual(values['S'],3)
        p.stop()

    def test_nullable_input_is_captured_before_output_selector_side_effect(self):
        ctx=context();values,_,_,_=execute(PUT+'m=5 VT_GET_QUEUE(1,1,0,1,m,work_id,codes[idx()])',ctx,decl=DECL+' codes:ARRAY[1] OF INTEGER',routines='ROUTINE idx:INTEGER BEGIN m=9 RETURN 1 END idx')
        self.assertEqual((values['M'],values['CODES'][0]),(9,0))

    def test_readonly_nullable_formal_can_receive_for_counter(self):
        routines='ROUTINE query(model_no:INTEGER; code:INTEGER) VAR unknown:INTEGER BEGIN VT_GET_TIME(1,1,model_no,unknown,estimate,code) END query'
        values,_,_,_=execute('estimate=99 FOR n=1 TO 1 DO query(n,s) ENDFOR',decl=DECL+' estimate:INTEGER',routines=routines)
        self.assertEqual((values['S'],values['ESTIMATE']),(1,99))

    def test_other_calls_keep_uninitialized_read_guards(self):
        ctx=context();p,_=compile_program('V_GET_QUEUE(m,1,0,s)',decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'):p.run()
        self.assertEqual(ctx.vision.sequence,0)


class PathEditingTests(unittest.TestCase):
    def test_preallocated_path_copies_prefix_and_internal_id(self):
        values,_,_,_=execute(PUT+'APPEND_NODE(q,s) APPEND_NODE(q,s) q[2].model_id=99 VT_READ_PQ(1,q,s)',decl=PATH_DECL,prefix=SCHEMA)
        q=values['Q'];self.assertEqual(q['data'],{'AREA_ID':1,'NUM_PARTS':1});self.assertEqual(q['nodes'][0]['WORK_ID'],1);self.assertEqual(q['nodes'][1]['MODEL_ID'],99)
        self.assertEqual(q['nodes'][0]['TRAY_ID'],{'uninitialized':True});self.assertEqual(q['nodes'][0]['FOUND_POS']['X'],{'uninitialized':True})

    def test_empty_path_has_zero_copied_count_without_appending(self):
        values,ctx,_,_=execute(PUT+'VT_READ_PQ(1,q,s)',decl=PATH_DECL,prefix=SCHEMA)
        self.assertEqual(values['Q']['data']['NUM_PARTS'],0);self.assertEqual(values['Q']['nodes'],[]);self.assertEqual(len(ctx.vision.tracking.vt.lines[1]['parts']),1)

    def test_path_capacity_truncation_and_encoder_order(self):
        values,_,_,_=execute(PUT+'VT_PUT_QUEUE(1,13,0,90,6,p,positions,measures,s) APPEND_NODE(q,s) VT_READ_PQ(1,q,s)',decl=PATH_DECL,prefix=SCHEMA)
        self.assertEqual(values['Q']['data']['NUM_PARTS'],1);self.assertEqual(values['Q']['nodes'][0]['WORK_ID'],2);self.assertEqual(values['Q']['nodes'][0]['ENC_COUNT'],90)

    def test_partial_update_retains_unspecified_values_and_updates_holes(self):
        values,ctx,_,_=execute('measures[1]=1.5 measures[3]=3.5 '+PUT+'m=8 updates[2]=2.5 VT_WRITE_PQ(1,1,m,encoder,newp,newp,updates,s) APPEND_NODE(q,s) VT_READ_PQ(1,q,s)',decl=PATH_DECL,prefix=SCHEMA)
        node=values['Q']['nodes'][0];self.assertEqual((node['MODEL_ID'],node['ENC_COUNT'],node['OFFSET']['X']),(8,100,1.));self.assertEqual(node['MEAS_VALUE'][:4],[1.5,2.5,3.5,{'uninitialized':True}])

    def test_partial_pose_update_failure_is_atomic(self):
        values,ctx,_,_=execute(PUT+'m=8 newp.x=5 VT_WRITE_PQ(1,1,m,encoder,newp,newp,updates,s)')
        self.assertEqual(values['S'],2);self.assertEqual(ctx.vision.tracking.vt.lines[1]['parts'][0]['result']['model'],5)

    def test_write_uses_documented_model_then_encoder_order(self):
        _,ctx,_,_=execute(PUT+'m=8 encoder=44 VT_WRITE_PQ(1,1,m,encoder,newp,newp,updates,s)')
        value=ctx.vision.tracking.vt.lines[1]['parts'][0]['result'];self.assertEqual((value['model'],value['encoder']),(8,44))

    def test_delete_is_local_to_area_and_can_forward_to_next(self):
        values,ctx,_,_=execute(PUT+'VT_DELETE_PQ(1,1,s) APPEND_NODE(q,s) VT_READ_PQ(1,q,s)',decl=PATH_DECL,prefix=SCHEMA)
        self.assertEqual(values['Q']['data']['NUM_PARTS'],0);self.assertEqual(ctx.vision.tracking.vt.lines[1]['parts'][0]['target'],2)
        values,_,_,_=execute('VT_GET_QUEUE(2,1,0,1,m,work_id,s)',ctx);self.assertEqual(values['S'],0)

    def test_allocated_part_cannot_be_edited_or_deleted(self):
        ctx=context();execute(PUT+GET,ctx)
        for call in ('VT_DELETE_PQ(1,1,s)','VT_WRITE_PQ(1,1,m,encoder,newp,newp,updates,s)'):
            values,_,_,_=execute(call,ctx);self.assertEqual(values['S'],3)

    def test_clear_current_area_preserves_other_area_access(self):
        values,ctx,_,_=execute(PUT+'VT_CLR_QUEUE(1,s) VT_GET_QUEUE(2,1,0,1,m,work_id,s)');self.assertEqual(values['S'],0)
        execute('VT_CLR_QUEUE(2,s)',ctx);self.assertEqual(ctx.vision.tracking.vt.allocations,{})

    def test_read_status_alias_guard_and_wrong_schema_preserve_queue(self):
        ctx=context();execute(PUT,ctx);p,_=compile_program('VT_READ_PQ(1,q,q.num_parts)',decl=PATH_DECL,prefix=SCHEMA,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        with self.assertRaises(TranslationError):compile_program('VT_READ_PQ(1,q,s)',decl='q:PATH s:INTEGER')
        self.assertEqual(len(ctx.vision.tracking.vt.lines[1]['parts']),1)

    def test_path_staging_budget_failure_preserves_old_header(self):
        ctx=context();execute(PUT,ctx);p,_=compile_program('APPEND_NODE(q,s) q.num_parts=99 VT_READ_PQ(1,q,s)',decl=PATH_DECL,prefix=SCHEMA,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=3)
        self.assertEqual(len(ctx.vision.tracking.vt.lines[1]['parts']),1)


FLAGS_SETUP='FOR i=1 TO 32 DO enflags[i]=0 disflags[i]=0 rates[i]=0 ENDFOR '
FLAGS_DECL=DECL+' i:INTEGER enflags,disflags,rates:ARRAY[32] OF INTEGER'


class FlagsBalanceAndEstimateTests(unittest.TestCase):
    def test_weighted_round_robin_assigns_target_areas_and_bypass(self):
        body=FLAGS_SETUP+'rates[1]=1 rates[2]=1 VT_SET_LDBAL(1,0,rates,1,s) VT_SET_FLAG(1,1,0,enflags,disflags,s) '
        body+='VT_PUT_QUEUE(1,12,0,100,5,p,positions,measures,s) VT_PUT_QUEUE(1,13,0,101,5,p,positions,measures,s) VT_PUT_QUEUE(1,14,0,102,5,p,positions,measures,s)'
        values,ctx,_,_=execute(body,decl=FLAGS_DECL);self.assertEqual(values['S'],0);self.assertEqual([v['target'] for v in ctx.vision.tracking.vt.lines[1]['parts']],[1,2]);self.assertEqual(ctx.vision.tracking.vt.lines[1]['sequence'],3)

    def test_consecutive_override_can_ignore_balance_target(self):
        ctx=context(flags=1);execute(FLAGS_SETUP+'rates[2]=1 VT_SET_LDBAL(1,0,rates,0,s) '+PUT,ctx,decl=FLAGS_DECL)
        values,_,_,_=execute(GET,ctx);self.assertEqual(values['S'],117249)
        values,_,_,_=execute('VT_GET_QUEUE(1,1,0,2,m,work_id,s)',ctx);self.assertEqual(values['S'],0)

    def test_downstream_first_flag_changes_weight_cycle_order(self):
        ctx=context(flags=3);execute(PUT,ctx);self.assertEqual(ctx.vision.tracking.vt.lines[1]['parts'][0]['target'],2)

    def test_flags_apply_by_area_order_and_skip_retargets_existing_part(self):
        values,ctx,_,_=execute(PUT+FLAGS_SETUP+'enflags[1]=1 VT_SET_FLAG(1,0,0,enflags,disflags,s)',decl=FLAGS_DECL)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.tracking.vt.areas[1]['flags'],1);self.assertEqual(ctx.vision.tracking.vt.lines[1]['parts'][0]['target'],2)

    def test_invalid_conflicting_masks_and_unused_slots_are_atomic(self):
        for modification in ('enflags[1]=1 disflags[1]=2','enflags[3]=1','enflags[1]=32'):
            values,ctx,_,_=execute(FLAGS_SETUP+modification+' VT_SET_FLAG(1,0,0,enflags,disflags,s)',decl=FLAGS_DECL)
            self.assertEqual(values['S'],2);self.assertEqual(ctx.vision.tracking.vt.areas[1]['flags'],0)
        values,ctx,_,_=execute(FLAGS_SETUP+'VT_SET_FLAG(1,1,2,enflags,disflags,s)',decl=FLAGS_DECL);self.assertEqual(values['S'],2);self.assertEqual(ctx.vision.tracking.vt.lines[1]['flags'],0)

    def test_y_sort_and_descending_flags_select_offset_y(self):
        ctx=context();execute(PUT+'p.y=8 VT_PUT_QUEUE(1,13,0,101,5,p,positions,measures,s) '+FLAGS_SETUP+'enflags[1]=6 VT_SET_FLAG(1,0,0,enflags,disflags,s)',ctx,decl=FLAGS_DECL)
        execute(GET,ctx);self.assertEqual(ctx.vision.registers[1]['offset'].values['Y'],8.)

    def test_read_write_delete_blocked_when_load_balance_enabled(self):
        ctx=context(flags=1);execute(PUT,ctx)
        for call in ('VT_READ_PQ(1,q,s)','VT_DELETE_PQ(1,1,s)','VT_WRITE_PQ(1,1,m,encoder,newp,newp,updates,s)'):
            values,_,_,_=execute(call,ctx,decl=PATH_DECL,prefix=SCHEMA);self.assertEqual(values['S'],7)

    def test_flow_rate_uses_supplied_speed_span_and_matching_count(self):
        values,_,_,_=execute(PUT+'VT_PUT_QUEUE(1,13,0,101,6,p,positions,measures,s) VT_GET_PFRT(1,1,1,m,n,s)')
        self.assertEqual((values['N'],values['S']),(12,0))
        values,_,_,_=execute(PUT+'m=6 VT_GET_PFRT(1,1,1,m,n,s)');self.assertEqual(values['N'],0)

    def test_missing_flow_geometry_preserves_output(self):
        ctx=context();ctx.vision.tracking.vt.areas[1]['span']=None
        values,_,_,_=execute(PUT+'n=99 VT_GET_PFRT(1,1,1,m,n,s)',ctx);self.assertEqual((values['N'],values['S']),(99,1))

    def test_invalid_rate_profile_and_array_shapes_are_rejected(self):
        values,_,_,_=execute(FLAGS_SETUP+'VT_SET_LDBAL(1,0,rates,0,s)',decl=FLAGS_DECL);self.assertEqual(values['S'],2)
        with self.assertRaises(TranslationError):compile_program('VT_SET_LDBAL(1,0,rates,0,s)',decl='rates:ARRAY[31] OF INTEGER s:INTEGER')


class PersistenceAndConfigurationTests(unittest.TestCase):
    def test_report_records_calls_optional_inputs_and_offline_choices(self):
        policy=translate('PROGRAM T BEGIN END T').report['vt_queue_policy']
        self.assertEqual(len(policy['calls']),12);self.assertFalse(policy['controller_validated'])
        self.assertIn('model_id then enc_count',policy['discrepancy']);self.assertIn('unspecified',policy['selectors'])

    def test_core_opaque_results_count_and_sparse_measurement_roundtrip(self):
        value=dict(found(),views={},measurements=[1.,None,3.])
        ctx=rt.ExecutionContext(vision=rt.VisionServices(processes={'SCAN':dict(views=[1],runs=[batch(value)])}),numeric=rt.NumericRegisters(1))
        values,_,_,_=execute("V_RUN_FIND('SCAN',0,s) V_GET_VPARAM('SCAN',0,-1,1,s) VT_GET_FOUND('SCAN',n,encoder,p,positions,measures,s)",ctx)
        self.assertEqual(ctx.numeric.read(1),(0,1.));self.assertEqual(values['MEASURES'][:3],[1.,{'uninitialized':True},3.]);self.assertEqual(values['POSITIONS'][0]['X'],{'uninitialized':True})
        self.assertEqual(rt.ExecutionContext.from_config(ctx.to_config()).vision.to_config(),ctx.vision.to_config())

    def test_indexed_unspecified_selector_is_evaluated_once(self):
        values,_,_,_=execute(PUT+'calls=0 VT_GET_QUEUE(1,1,0,1,selectors[idx()],work_id,s)',decl=DECL+' calls:INTEGER selectors:ARRAY[1] OF INTEGER',routines='ROUTINE idx:INTEGER BEGIN calls=calls+1 RETURN 1 END idx')
        self.assertEqual((values['S'],values['CALLS']),(0,1))

    def test_legacy_get_cannot_overwrite_outstanding_vt_allocation(self):
        ctx=context();config=ctx.to_config();config['vision']['tracking']['queues']={'1':{'capacity':1,'parts':[{'work_id':100,'result':found()}]}}
        ctx=rt.ExecutionContext.from_config(config);values,_,_,_=execute(PUT+GET+'V_GET_QUEUE(1,1,0,s)',ctx)
        self.assertEqual(values['S'],3);self.assertEqual(len(ctx.vision.tracking.queues[1]['parts']),1);self.assertIn(1,ctx.vision.tracking.vt.allocations)

    def test_tagged_tray_edit_requires_explicit_permission(self):
        ctx=context();body='VT_PUT_QUEUE(1,12,3,100,5,p,positions,measures,s) APPEND_NODE(q,s) VT_READ_PQ(1,q,s)'
        values,_,_,_=execute(body,ctx,decl=PATH_DECL,prefix=SCHEMA);self.assertEqual(values['S'],7)
        ctx=context();ctx.vision.tracking.vt.lines[1]['tray_edit']=True;values,_,_,_=execute(body,ctx,decl=PATH_DECL,prefix=SCHEMA)
        self.assertEqual(values['S'],0);self.assertEqual(values['Q']['nodes'][0]['TRAY_ID'],3)

    def test_model_specific_weights_leave_default_profile_independent(self):
        body=FLAGS_SETUP+'rates[2]=1 VT_SET_LDBAL(1,5,rates,0,s) VT_SET_FLAG(1,1,0,enflags,disflags,s) '+PUT+'VT_PUT_QUEUE(1,13,0,101,6,p,positions,measures,s)'
        _,ctx,_,_=execute(body,decl=FLAGS_DECL);self.assertEqual([v['target'] for v in ctx.vision.tracking.vt.lines[1]['parts']],[2,1])

    def test_flow_overflow_keeps_output_unchanged(self):
        ctx=context();ctx.vision.tracking.vt.lines[1]['speed']=1.7e308
        values,_,_,_=execute(PUT+'n=99 VT_GET_PFRT(1,1,1,m,n,s)',ctx);self.assertEqual((values['S'],values['N']),(2,99))

    def test_roundtrip_keeps_allocations_clock_ids_and_nullable_result_data(self):
        _,ctx,_,_=execute(PUT+GET);saved=ctx.to_config();restored=rt.ExecutionContext.from_config(json.loads(json.dumps(saved)))
        self.assertEqual(restored.vision.to_config(),ctx.vision.to_config());execute('VT_ACK_QUEUE(1,1,2,s)',restored)
        self.assertIn(1,ctx.vision.tracking.vt.allocations);self.assertEqual(restored.vision.tracking.vt.lines[1]['parts'][0]['target'],2)

    def test_unknown_config_keys_and_invalid_topology(self):
        original=context().to_config()
        for field,value in [('callback','bad'),('lines',{'01':{}}),('areas',{}),('allocations',{'1':{}})]:
            config=deepcopy(original);config['vision']['tracking']['vt'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)

    def test_bad_weights_clocks_and_area_flags_are_rejected(self):
        original=context().to_config()
        for location,field,value in [('line','flags',4),('line','direction',0),('line','weights',{'0':{'pick':[0,0],'pass':0}}),('area','elapsed_ms',True),('area','span',0),('area','flags',32)]:
            config=deepcopy(original);row=config['vision']['tracking']['vt']['lines' if location=='line' else 'areas']['1'];row[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)

    def test_duplicate_uid_and_external_ids_in_saved_queue_are_rejected(self):
        _,ctx,_,_=execute(PUT);config=ctx.to_config();vt=config['vision']['tracking']['vt'];vt['lines']['1']['parts'].append(deepcopy(vt['lines']['1']['parts'][0]))
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)

    def test_source_output_and_active_for_guards_still_apply(self):
        for body in ('VT_ACK_QUEUE(1,1,1,TRUE)','FOR n=1 TO 2 DO VT_GET_QUEUE(1,1,0,1,m,work_id,n) ENDFOR'):
            with self.assertRaises(TranslationError):compile_program(body,decl=DECL)

    def test_missing_vt_service_fails_explicitly(self):
        ctx=rt.ExecutionContext(vision=rt.VisionServices(tracking={}))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'tracking vt'):execute('VT_CLR_QUEUE(1,s)',ctx)

    def test_request_and_index_exhaustion_preserve_inputs(self):
        ctx=context();ctx.vision.sequence=2147483646;before=ctx.vision.to_config()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'sequence exhausted'):execute(PUT,ctx)
        self.assertEqual(ctx.vision.to_config(),before)
        ctx=context();ctx.vision.tracking.vt.lines[1]['sequence']=2147483646
        with self.assertRaisesRegex(rt.KarelRuntimeError,'index exhausted'):execute(PUT,ctx)
        self.assertEqual(ctx.vision.tracking.vt.lines[1]['parts'],[])


if __name__=='__main__':unittest.main()
