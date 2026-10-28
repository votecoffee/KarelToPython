"""Authored supplied tray cells, queue receipts and bounded persistence checks."""
from copy import deepcopy
import json
import unittest

from karel2py import runtime as rt
from karel2py.vision import MAX_SEQUENCE
from tests.test_extended_services import compile_program,pose
from tests.test_vt_queues import context,execute,DECL,GET,PATH_DECL,SCHEMA,SETUP


PUT='VT_PUT_QUEUE(1,12,3,100,5,p,positions,measures,s) '
ZERO_PUT='VT_PUT_QUEUE(1,0,3,100,5,p,positions,measures,s) '


def tray_context(*,cells=None,sequenced=True,**options):
    return context(trays={'3':dict(cells=cells or [{'offset':pose()},{'offset':pose(10)}],sequenced=sequenced)},**options)


def parts(ctx):return ctx.vision.tracking.vt.lines[1]['parts']


class VTTrayExpansionTests(unittest.TestCase):
    def test_configured_tray_put_expands_cells_with_distinct_internal_ids(self):
        ctx=tray_context();values,_,_,_=execute(PUT,ctx)
        self.assertEqual(values['S'],0)
        self.assertEqual([(p['uid'],p['tray_instance'],p['tray_cell'],p['work_id'],p['tray']) for p in parts(ctx)],[(1,1,1,12,3),(2,1,2,12,3)])
        self.assertEqual([p['result']['offset'].values['X'] for p in parts(ctx)],[1.,11.])
        self.assertEqual(ctx.vision.tracking.vt.lines[1]['sequence'],2)

    def test_tray_without_a_cell_bank_retains_one_tagged_part(self):
        ctx=context();execute(PUT,ctx)
        self.assertEqual(len(parts(ctx)),1);self.assertNotIn('tray_cell',parts(ctx)[0])

    def test_zero_tray_ignores_configured_cells(self):
        ctx=tray_context();execute(PUT.replace(',3,100',',0,100'),ctx)
        self.assertEqual(len(parts(ctx)),1);self.assertNotIn('tray_cell',parts(ctx)[0])

    def test_local_cell_translation_uses_the_input_rotation(self):
        ctx=tray_context();execute('p.r=90 '+PUT,ctx)
        point=parts(ctx)[1]['result']['offset']
        self.assertAlmostEqual(point.values['X'],1.)
        self.assertAlmostEqual(point.values['Y'],12.)
        self.assertAlmostEqual(point.values['R'],90.)

    def test_supplied_cell_rotation_composes_with_the_input(self):
        rotated=pose();rotated.values['R']=45.
        ctx=tray_context(cells=[{'offset':rotated}]);execute('p.r=30 '+PUT,ctx)
        self.assertAlmostEqual(parts(ctx)[0]['result']['offset'].values['R'],75.)

    def test_existing_views_receive_cell_offsets_and_missing_views_stay_absent(self):
        ctx=tray_context();execute('positions[2]=p '+PUT,ctx)
        self.assertEqual(set(parts(ctx)[1]['result']['views']),{'2'})
        self.assertEqual(parts(ctx)[1]['result']['views']['2']['position'].values['X'],11.)
        self.assertEqual(parts(ctx)[0]['result']['views']['2']['position'].values['X'],1.)

    def test_missing_measurements_are_never_filled_with_zeroes(self):
        ctx=tray_context();execute('measures[2]=4.5 '+PUT,ctx)
        for part in parts(ctx):self.assertEqual(part['result']['measurements'],[None,4.5]+[None]*8)

    def test_cell_model_override_updates_its_views_only(self):
        ctx=tray_context(cells=[{'offset':pose()},{'offset':pose(10),'model':6}])
        execute('positions[1]=p '+PUT,ctx)
        self.assertEqual([p['result']['model'] for p in parts(ctx)],[5,6])
        self.assertEqual([p['result']['views']['1']['model'] for p in parts(ctx)],[5,6])

    def test_source_and_config_storage_are_detached_from_cell_results(self):
        offset=pose(10);ctx=tray_context(cells=[{'offset':offset}]);offset.values['X']=99.
        execute('positions[1]=p '+PUT+'p.x=77 positions[1].x=66',ctx)
        self.assertEqual(parts(ctx)[0]['result']['offset'].values['X'],11.)
        self.assertEqual(parts(ctx)[0]['result']['views']['1']['position'].values['X'],11.)

    def test_incomplete_source_view_rejects_entire_expansion(self):
        ctx=tray_context();values,_,_,_=execute('positions[1].x=1 '+PUT,ctx)
        self.assertEqual(values['S'],2);self.assertEqual(parts(ctx),[])
        self.assertEqual(ctx.vision.tracking.vt.lines[1]['sequence'],0)

    def test_capacity_preflight_includes_every_cell(self):
        ctx=tray_context(capacity=1);before=deepcopy(ctx.vision.tracking.vt.lines[1])
        values,_,_,_=execute(PUT,ctx)
        self.assertEqual(values['S'],4);self.assertEqual(ctx.vision.tracking.vt.lines[1],before)

    def test_allocated_cell_remains_counted_against_pool_capacity(self):
        ctx=tray_context(capacity=3);execute(PUT+GET,ctx)
        before=ctx.vision.to_config()
        values,_,_,_=execute(PUT.replace('1,12,3,100','1,13,3,101'),ctx)
        self.assertEqual(values['S'],4)
        self.assertEqual(ctx.vision.to_config()['tracking']['vt'],before['tracking']['vt'])

    def test_uid_exhaustion_checks_the_complete_batch(self):
        ctx=tray_context();ctx.vision.tracking.vt.lines[1]['sequence']=MAX_SEQUENCE-1
        with self.assertRaisesRegex(rt.KarelRuntimeError,'index exhausted'):execute(PUT,ctx)
        self.assertEqual(parts(ctx),[]);self.assertEqual(ctx.vision.tracking.vt.lines[1]['sequence'],MAX_SEQUENCE-1)

    def test_arrival_clock_failure_preserves_the_entire_batch(self):
        ctx=tray_context(travel=1);ctx.vision.tracking.vt.areas[1]['elapsed_ms']=MAX_SEQUENCE
        before=ctx.vision.to_config()['tracking']['vt']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'arrival clock exhausted'):execute(PUT,ctx)
        self.assertEqual(ctx.vision.to_config()['tracking']['vt'],before)

    def test_global_capacity_includes_other_lines(self):
        seed=context(capacity=4096);execute(PUT.replace(',3,100',',0,100').replace('1,12,','1,0,'),seed)
        config=seed.to_config();vt=config['vision']['tracking']['vt'];old=vt['lines']['1']['parts'][0]
        vt['lines']['2']={**deepcopy(vt['lines']['1']),'areas':[3], 'sequence':4095,
            'weights':{'0':{'pick':[1],'pass':0,'cursor':0}},'parts':[]}
        vt['areas']['3']={'line':2}
        for index in range(1,4096):
            row=deepcopy(old);row.update(uid=index,ready={'3':0},target=3)
            vt['lines']['2']['parts'].append(row)
        vt['lines']['1']['parts']=[];vt['lines']['1']['sequence']=0
        patterns=tray_context().to_config()['vision']['tracking']['vt']['trays'];vt['trays']=patterns
        ctx=rt.ExecutionContext.from_config(config)
        values,_,_,_=execute(PUT,ctx)
        self.assertEqual(values['S'],4);self.assertEqual(parts(ctx),[])
        self.assertEqual(ctx.vision.tracking.vt.lines[1]['sequence'],0)

    def test_budget_failure_raises_without_partial_cells_or_routing_changes(self):
        ctx=tray_context(cells=[{'offset':pose(i)} for i in range(8)],flags=1)
        program,_=compile_program(SETUP+PUT,decl=DECL,context=ctx)
        before=ctx.vision.to_config()['tracking']['vt']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):program.run(max_steps=6)
        self.assertEqual(ctx.vision.to_config()['tracking']['vt'],before)

    def test_composition_overflow_is_atomic_and_keeps_routing_cursor(self):
        offset=pose();offset.values['X']=1.7e308
        ctx=tray_context(cells=[{'offset':pose()},{'offset':offset}],flags=1)
        before=ctx.vision.to_config()['tracking']['vt']
        values,_,_,_=execute('p.x=1.7e308 '+PUT,ctx)
        self.assertEqual(values['S'],2);self.assertEqual(ctx.vision.to_config()['tracking']['vt'],before)

    def test_que2_still_rejects_trays_before_any_insertion(self):
        ctx=tray_context();values,_,_,_=execute('duplicate=TRUE VT_PUT_QUE2(1,12,3,100,5,p,positions,measures,duplicate,s)',ctx)
        self.assertEqual((values['S'],values['DUPLICATE']),(2,True));self.assertEqual(parts(ctx),[])


class VTTrayDuplicateAndAllocationTests(unittest.TestCase):
    def test_zero_work_id_duplicate_matches_origin_when_no_cell_is_at_origin(self):
        ctx=tray_context(cells=[{'offset':pose(10)},{'offset':pose(20)}]);execute(ZERO_PUT,ctx)
        before=ctx.vision.to_config()['tracking']['vt'];values,_,_,_=execute(ZERO_PUT,ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.to_config()['tracking']['vt'],before)

    def test_duplicate_detection_includes_fully_allocated_trays(self):
        ctx=tray_context(cells=[{'offset':pose(10)},{'offset':pose(20)}])
        execute(ZERO_PUT+GET+'VT_GET_QUEUE(1,2,0,1,m,work_id,s)',ctx)
        self.assertEqual(parts(ctx),[])
        values,_,_,_=execute(ZERO_PUT,ctx)
        self.assertEqual(values['S'],0);self.assertEqual(parts(ctx),[])
        self.assertEqual(ctx.vision.tracking.vt.lines[1]['sequence'],2)

    def test_shared_caller_id_selects_successive_sibling_cells(self):
        ctx=tray_context();execute(PUT+'work_id=12 '+GET,ctx)
        self.assertEqual(ctx.vision.tracking.vt.allocations[1]['part']['tray_cell'],1)
        execute('VT_ACK_QUEUE(1,1,1,s) work_id=12 '+GET,ctx)
        self.assertEqual(ctx.vision.tracking.vt.allocations[1]['part']['tray_cell'],2)

    def test_handled_and_failed_ack_discard_only_the_allocated_cell(self):
        for ack in (1,3):
            ctx=tray_context();execute(PUT+GET+f'VT_ACK_QUEUE(1,1,{ack},s)',ctx)
            self.assertEqual([p['tray_cell'] for p in parts(ctx)],[2])
            self.assertEqual(ctx.vision.tracking.vt.allocations,{})

    def test_ack_two_forwards_one_adjusted_cell_with_instance_identity(self):
        ctx=tray_context();execute(PUT+GET+'V_ADJ_2D(1,4,0,s) VT_ACK_QUEUE(1,1,2,s)',ctx)
        self.assertEqual([(p['tray_cell'],p['target']) for p in parts(ctx)],[(2,1),(1,2)])
        forwarded=parts(ctx)[1]
        self.assertEqual((forwarded['tray_instance'],forwarded['passed']),(1,[1]))
        self.assertEqual(forwarded['result']['offset'].values['X'],5.)
        execute('VT_GET_QUEUE(2,1,0,1,m,work_id,s)',ctx)
        self.assertEqual(ctx.vision.tracking.vt.allocations[1]['part']['tray_cell'],1)

    def test_clear_drops_allocations_without_dropping_downstream_siblings(self):
        ctx=tray_context();execute(PUT+GET+'VT_CLR_QUEUE(1,s)',ctx)
        self.assertEqual(ctx.vision.tracking.vt.allocations,{})
        self.assertEqual([(p['tray_cell'],p['target'],p['passed']) for p in parts(ctx)],[(2,2,[1])])

    def test_distinct_insertions_get_distinct_instance_and_internal_ids(self):
        ctx=tray_context();execute(PUT+PUT.replace('1,12,3,100','1,13,3,101'),ctx)
        self.assertEqual([(p['uid'],p['tray_instance'],p['tray_cell']) for p in parts(ctx)],[(1,1,1),(2,1,2),(3,3,1),(4,3,2)])

    def test_wait_pause_resume_and_stop_release_pending_cell_request(self):
        ctx=tray_context(travel=25);execute(PUT,ctx)
        program,_=compile_program('s=99 '+GET.replace(',0,1,',',30,1,'),decl=DECL,context=ctx,
            sleep=lambda _:setattr(program._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):program.run()
        self.assertEqual(program.task_state,'paused')
        self.assertTrue(ctx.vision.tracking.vt.pending)
        with self.assertRaisesRegex(ValueError,'pending VT'):ctx.to_config()
        program.stop();self.assertEqual(ctx.vision.tracking.vt.pending,{})
        self.assertEqual(len(parts(ctx)),2);self.assertEqual(ctx.vision.tracking.vt.allocations,{})

    def test_wait_can_resume_then_allocate_after_arrival(self):
        ctx=tray_context(travel=25);execute(PUT,ctx)
        program,_=compile_program(GET.replace(',0,1,',',30,1,'),decl=DECL,context=ctx,
            sleep=lambda _:setattr(program._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):program.run()
        program._state._sleep=lambda _:None;program.resume()
        self.assertEqual(program.snapshot()['S'],0)
        self.assertEqual(ctx.vision.tracking.vt.allocations[1]['part']['tray_cell'],1)


class VTTrayOrderingAndPersistenceTests(unittest.TestCase):
    def test_sequence_overrides_y_sort_within_the_same_tray(self):
        cells=[{'offset':pose(0,10)},{'offset':pose()}]
        for sequenced,expected in ((True,1),(False,2)):
            ctx=tray_context(cells=cells,sequenced=sequenced);ctx.vision.tracking.vt.areas[1]['flags']=2
            execute(PUT+GET,ctx)
            self.assertEqual(ctx.vision.tracking.vt.allocations[1]['part']['tray_cell'],expected)

    def test_model_filter_can_select_a_later_cell(self):
        ctx=tray_context(cells=[{'offset':pose()},{'offset':pose(10),'model':6}]);execute(PUT+'m=6 '+GET,ctx)
        self.assertEqual(ctx.vision.tracking.vt.allocations[1]['part']['tray_cell'],2)

    def test_weighted_routing_advances_once_per_cell_and_ack_does_not_reassign_siblings(self):
        ctx=tray_context(flags=1);execute(PUT,ctx)
        self.assertEqual([p['target'] for p in parts(ctx)],[1,2])
        execute(GET+'VT_ACK_QUEUE(1,1,1,s)',ctx)
        self.assertEqual([(p['tray_cell'],p['target']) for p in parts(ctx)],[(2,2)])

    def test_cell_model_override_selects_its_own_weight_profile(self):
        ctx=tray_context(cells=[{'offset':pose()},{'offset':pose(10),'model':6}],flags=1)
        line=ctx.vision.tracking.vt.lines[1]
        line['weights']['0']={'pick':[1,0],'pass':0,'cursor':0}
        line['weights']['6']={'pick':[0,1],'pass':0,'cursor':0}
        execute(PUT,ctx)
        self.assertEqual([p['target'] for p in parts(ctx)],[1,2])

    def test_unsequenced_path_retains_encoder_order_after_cell_edit(self):
        ctx=tray_context(sequenced=False);ctx.vision.tracking.vt.lines[1]['tray_edit']=True
        values,_,_,_=execute(PUT+'encoder=1 VT_WRITE_PQ(1,2,m,encoder,newp,newp,updates,s) APPEND_NODE(q,s) APPEND_NODE(q,s) VT_READ_PQ(1,q,s)',ctx,decl=PATH_DECL,prefix=SCHEMA)
        self.assertEqual(values['S'],0);self.assertEqual([p['WORK_ID'] for p in values['Q']['nodes']],[2,1])

    def test_flow_rate_counts_expanded_cells_as_workpieces(self):
        ctx=tray_context();values,_,_,_=execute(PUT+'VT_GET_PFRT(1,1,1,m,n,s)',ctx)
        self.assertEqual((values['N'],values['S']),(12,0))

    def test_bypass_still_reserves_distinct_internal_ids_for_all_cells(self):
        ctx=tray_context(flags=1)
        ctx.vision.tracking.vt.lines[1]['weights']['0']={'pick':[1,0],'pass':1,'cursor':0}
        execute(PUT,ctx)
        self.assertEqual([p['tray_cell'] for p in parts(ctx)],[1])
        self.assertEqual(ctx.vision.tracking.vt.lines[1]['sequence'],2)

    def test_path_read_exposes_cell_ids_and_requires_explicit_tray_edit(self):
        ctx=tray_context();body=PUT+'APPEND_NODE(q,s) APPEND_NODE(q,s) VT_READ_PQ(1,q,s)'
        values,_,_,_=execute(body,ctx,decl=PATH_DECL,prefix=SCHEMA);self.assertEqual(values['S'],7)
        ctx.vision.tracking.vt.lines[1]['tray_edit']=True
        values,_,_,_=execute('VT_READ_PQ(1,q,s)',ctx,decl=PATH_DECL,prefix=SCHEMA)
        # This separate invocation has a new local PATH, so no nodes are invented.
        self.assertEqual(values['Q']['data']['NUM_PARTS'],0)
        values,_,_,_=execute('APPEND_NODE(q,s) APPEND_NODE(q,s) VT_READ_PQ(1,q,s)',ctx,decl=PATH_DECL,prefix=SCHEMA)
        self.assertEqual([p['WORK_ID'] for p in values['Q']['nodes']],[1,2])
        self.assertEqual([p['TRAY_ID'] for p in values['Q']['nodes']],[3,3])

    def test_path_write_preserves_instance_and_explicit_sequence(self):
        ctx=tray_context();ctx.vision.tracking.vt.lines[1]['tray_edit']=True
        values,_,_,_=execute(PUT+'encoder=1 VT_WRITE_PQ(1,2,m,encoder,newp,newp,updates,s) APPEND_NODE(q,s) APPEND_NODE(q,s) VT_READ_PQ(1,q,s)',ctx,decl=PATH_DECL,prefix=SCHEMA)
        self.assertEqual(values['S'],0);self.assertEqual([p['WORK_ID'] for p in values['Q']['nodes']],[1,2])
        self.assertEqual(parts(ctx)[1]['tray_instance'],1)

    def test_path_delete_targets_one_cell_and_keeps_other_metadata(self):
        ctx=tray_context();ctx.vision.tracking.vt.lines[1]['tray_edit']=True
        execute(PUT+'VT_DELETE_PQ(1,1,s)',ctx)
        self.assertEqual([(p['tray_cell'],p['target']) for p in parts(ctx)],[(1,2),(2,1)])

    def test_roundtrip_keeps_patterns_cells_receipts_and_partial_values(self):
        ctx=tray_context();execute('measures[3]=4.5 '+PUT+GET,ctx)
        config=ctx.to_config();restored=rt.ExecutionContext.from_config(json.loads(json.dumps(config)))
        self.assertEqual(restored.to_config(),config)
        execute('VT_ACK_QUEUE(1,1,2,s)',restored)
        self.assertIn(1,ctx.vision.tracking.vt.allocations)
        self.assertEqual(restored.vision.tracking.vt.allocations,{})
        self.assertEqual(parts(restored)[1]['tray_cell'],1)

    def test_saved_group_metadata_cannot_forge_other_instance_ownership(self):
        ctx=tray_context();execute(PUT,ctx);original=ctx.to_config()
        mutations=(('tray_instance',2),('tray_cell',1),('tray_instance',True),('tray_origin',[100,6,1,2,3,0,0,0]),('work_id',13),('tray',0))
        for field,value in mutations:
            config=deepcopy(original);config['vision']['tracking']['vt']['lines']['1']['parts'][1][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)

    def test_partial_metadata_and_missing_patterns_reject_saved_cells(self):
        ctx=tray_context();execute(PUT,ctx);original=ctx.to_config()
        for field in ('tray_origin','tray_cell','tray_instance'):
            config=deepcopy(original);del config['vision']['tracking']['vt']['lines']['1']['parts'][0][field]
            with self.subTest(field=field),self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)
        config=deepcopy(original);del config['vision']['tracking']['vt']['trays']
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)

    def test_bad_origin_shapes_and_scalar_types_reject_saved_cells(self):
        ctx=tray_context();execute(PUT,ctx);original=ctx.to_config()
        for origin in (None,[],[100,5,1,2,3,0,0],[True,5,1,2,3,0,0,0],[100,-1,1,2,3,0,0,0],
                       [100,5,1,2,3,0,0,float('inf')]):
            config=deepcopy(original);config['vision']['tracking']['vt']['lines']['1']['parts'][0]['tray_origin']=origin
            with self.subTest(origin=origin),self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)

    def test_shortened_pattern_cannot_restore_other_cell_ordinals(self):
        ctx=tray_context();execute(PUT,ctx);config=ctx.to_config()
        config['vision']['tracking']['vt']['trays']['3']['cells'].pop()
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)

    def test_duplicate_ids_are_rejected_across_distinct_tray_instances(self):
        ctx=tray_context();execute(PUT+PUT.replace('1,12,3,100','1,13,3,101'),ctx)
        config=ctx.to_config();rows=config['vision']['tracking']['vt']['lines']['1']['parts']
        rows[2]['work_id']=rows[3]['work_id']=12
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)

    def test_invalid_tray_configuration_fails_before_any_source_runs(self):
        cell={'offset':pose()}
        cases=({'3':{'cells':[]}},{'3':{'cells':[cell]*257}},{'3':{'cells':[cell],'sequenced':1}},
               {'3':{'cells':[{'offset':pose(),'model':-1}]}},{'3':{'cells':[{'offset':pose(),'extra':1}]}},
               {'3':{'cells':[{}]}},{'03':{'cells':[cell]}},{'4':{'cells':[cell]}},[],{'3':{'cells':[cell],'extra':1}})
        for trays in cases:
            with self.subTest(trays=trays),self.assertRaises(ValueError):context(trays=trays)

    def test_unknown_partial_and_wrong_type_cell_offsets_reject(self):
        unknown=rt.Structure(('XYZWPR',));partial=rt.Structure(('XYZWPR',));partial.values['X']=1.
        for value in (unknown,partial,None,{'uninitialized':True},rt.Structure(('VECTOR',))):
            with self.subTest(value=repr(value)),self.assertRaises(ValueError):context(trays={'3':{'cells':[{'offset':value}]}})

    def test_pattern_total_cell_limit_is_checked(self):
        config=context().to_config();tracking=config['vision']['tracking'];cell=tray_context().to_config()['vision']['tracking']['vt']['trays']['3']['cells'][0]
        tracking['ids']['trays']={f'TRAY{i}':i for i in range(1,18)}
        tracking['vt']['trays']={str(i):{'cells':[deepcopy(cell) for _ in range(256)]} for i in range(1,18)}
        with self.assertRaisesRegex(ValueError,'4096'):rt.ExecutionContext.from_config(config)


if __name__=='__main__':unittest.main()
