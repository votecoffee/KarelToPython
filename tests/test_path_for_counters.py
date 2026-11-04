"""Authored owned PATH/bank counters, retained aliases and stable node captures."""
from copy import deepcopy
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program

PREFIX='TYPE child_t=STRUCTURE value:INTEGER ENDSTRUCTURE data_t=STRUCTURE count:INTEGER other:INTEGER small:BYTE narrow:SHORT values:ARRAY[2]OF INTEGER child:child_t ENDSTRUCTURE route_t=PATH NODEDATA=data_t PATHHEADER=data_t'
DECL='source,other:route_t bank:ARRAY[2]OF route_t total,visits,slot,status,result,limit:INTEGER flag:BOOLEAN'
SEED='source.count=17 source.other=9 other.count=88 slot=1 visits=0 '
U={'uninitialized':True}
B={'unknown_byte':True}
def build(body,*,seed=True,labelled=False,decl=DECL,prefix=PREFIX,**options):return compile_program((SEED if seed else '')+('unused:: ' if labelled else '')+body,decl=decl,prefix=prefix,**options)
def raw(p,name='SOURCE'):return p._state.values[name]
def count(p):return raw(p).data.values['COUNT']
def node(p,index=0):return raw(p).nodes[index]
def reject(body,**options):
    with unittest.TestCase().assertRaises(TranslationError) as caught:build(body,**options)
    return caught.exception.code

class PathForStorageTests(unittest.TestCase):
    def test_header_counter_cleans_only_selected_leaf(self):
        p,_=build('total=0 FOR source.count=1 TO 3 DO total=total+source.count ENDFOR');v=p.run();self.assertEqual((v['TOTAL'],v['SOURCE']['data']['COUNT'],v['SOURCE']['data']['OTHER']),(6,U,9))
    def test_node_counter_keeps_header_and_siblings(self):
        p,_=build('APPEND_NODE(source,status) source[1].other=9 total=0 FOR source[1].count=1 TO 3 DO total=total+source[1].count ENDFOR');v=p.run();self.assertEqual((v['TOTAL'],v['SOURCE']['data']['COUNT'],v['SOURCE']['nodes'][0]['COUNT']),(6,17,U));self.assertEqual(v['SOURCE']['nodes'][0]['OTHER'],9)
    def test_header_array_leaf_counter(self):
        p,_=build('source.values[2]=99 total=0 FOR source.values[1]=1 TO 3 DO total=total+source.values[1] ENDFOR');v=p.run();self.assertEqual((v['TOTAL'],v['SOURCE']['data']['VALUES']),(6,[U,99]))
    def test_nested_node_record_counter(self):
        p,_=build('APPEND_NODE(source,status) total=0 FOR source[1].child.value=1 TO 3 DO total=total+source[1].child.value ENDFOR');self.assertEqual(p.run()['TOTAL'],6)
    def test_path_bank_header_counter(self):
        p,_=build('bank[1].count=99 total=0 FOR bank[2].count=1 TO 3 DO total=total+bank[2].count ENDFOR');v=p.run();self.assertEqual((v['TOTAL'],[r['data']['COUNT'] for r in v['BANK']]),(6,[99,U]))
    def test_path_bank_node_counter(self):
        p,_=build('APPEND_NODE(bank[2],status) total=0 FOR bank[2][1].count=1 TO 3 DO total=total+bank[2][1].count ENDFOR');self.assertEqual(p.run()['TOTAL'],6)
    def test_combined_bank_node_indexes(self):
        p,_=build('APPEND_NODE(bank[2],status) total=0 FOR bank[2,1].count=1 TO 3 DO total=total+bank[2,1].count ENDFOR');self.assertEqual(p.run()['TOTAL'],6)
    def test_named_inner_bank_counter(self):
        p,_=build('total=0 FOR bank[2,2].count=1 TO 3 DO total=total+bank[2,2].count ENDFOR',prefix=PREFIX+' TYPE row_t=ARRAY[2]OF route_t',decl=DECL.replace('bank:ARRAY[2]OF route_t','bank:ARRAY[2]OF row_t'));self.assertEqual(p.run()['TOTAL'],6)
    def test_three_dimensional_bank_counter(self):
        p,_=build('total=0 FOR bank[2,2,2].count=1 TO 3 DO total=total+bank[2,2,2].count ENDFOR',decl=DECL.replace('bank:ARRAY[2]OF route_t','bank:ARRAY[2,2,2]OF route_t'));self.assertEqual(p.run()['TOTAL'],6)
    def test_header_using_counter(self):
        p,_=build('total=0 USING source DO FOR count=1 TO 3 DO total=total+count ENDFOR ENDUSING');self.assertEqual(p.run()['TOTAL'],6)
    def test_node_using_counter(self):
        p,_=build('APPEND_NODE(source,status) total=0 USING source[1] DO FOR count=1 TO 3 DO total=total+count ENDFOR ENDUSING');self.assertEqual(p.run()['TOTAL'],6)
    def test_fresh_local_path_in_parameterized_routine(self):
        p,_=build('result=work(3)',routines='ROUTINE work(last:INTEGER):INTEGER VAR local_path:route_t n:INTEGER BEGIN n=0 FOR local_path.count=1 TO last DO n=n+local_path.count ENDFOR RETURN n END work');self.assertEqual(p.run()['RESULT'],6)
    def test_fresh_local_bank_in_parameterized_routine(self):
        p,_=build('result=work(3)',routines='ROUTINE work(last:INTEGER):INTEGER VAR local_bank:ARRAY[2]OF route_t n:INTEGER BEGIN n=0 FOR local_bank[2].count=1 TO last DO n=n+local_bank[2].count ENDFOR RETURN n END work');self.assertEqual(p.run()['RESULT'],6)
    def test_independent_path_roots_can_nest(self):
        p,_=build('total=0 FOR source.count=1 TO 2 DO FOR other.count=1 TO 2 DO total=total+source.count+other.count ENDFOR ENDFOR');v=p.run();self.assertEqual((v['TOTAL'],v['SOURCE']['data']['COUNT'],v['OTHER']['data']['COUNT']),(12,U,U))
    def test_byte_header_endpoints_and_marker(self):
        p,_=build('total=0 FOR source.small=254 TO 255 DO total=total+source.small ENDFOR');v=p.run();self.assertEqual((v['TOTAL'],v['SOURCE']['data']['SMALL']),(509,B))
    def test_byte_node_descends_to_zero(self):
        p,_=build('APPEND_NODE(source,status) total=0 FOR source[1].small=1 DOWNTO 0 DO total=total+source[1].small ENDFOR');v=p.run();self.assertEqual((v['TOTAL'],v['SOURCE']['nodes'][0]['SMALL']),(1,B))
    def test_short_header_includes_upper_endpoint(self):
        p,_=build('total=0 FOR source.narrow=32766 TO 32766 DO total=total+source.narrow ENDFOR');v=p.run();self.assertEqual((v['TOTAL'],v['SOURCE']['data']['NARROW']),(32766,U))
    def test_short_node_includes_negative_endpoint(self):
        p,_=build('APPEND_NODE(source,status) total=0 FOR source[1].narrow=-32768 TO -32768 DO total=total+source[1].narrow ENDFOR');self.assertEqual(p.run()['TOTAL'],-32768)
    def test_zero_iteration_still_cleans_scalar(self):
        p,_=build('total=0 FOR source.count=3 TO 1 DO total=99 ENDFOR');v=p.run();self.assertEqual((v['TOTAL'],v['SOURCE']['data']['COUNT']),(0,U))
    def test_descending_integer_is_inclusive(self):
        p,_=build('total=0 FOR source.count=3 DOWNTO 1 DO total=total+source.count ENDFOR');self.assertEqual(p.run()['TOTAL'],6)
    def test_readonly_scalar_routine_can_observe_counter(self):
        p,_=build('total=0 FOR source.count=1 TO 3 DO observe(source.count) ENDFOR',routines='ROUTINE observe(v:INTEGER) BEGIN total=total+v END observe');self.assertEqual(p.run()['TOTAL'],6)
    def test_readonly_path_routine_can_observe_root(self):
        p,_=build('total=0 FOR source.count=1 TO 3 DO observe(source) ENDFOR',routines='ROUTINE observe(v:route_t) BEGIN total=total+v.count END observe');self.assertEqual(p.run()['TOTAL'],6)
    def test_grouped_path_argument_is_independent_during_loop(self):
        p,_=build('total=0 FOR source.count=1 TO 3 DO change((source)) total=total+source.count ENDFOR',routines='ROUTINE change(v:route_t) BEGIN v.count=99 END change');self.assertEqual(p.run()['TOTAL'],6)
    def test_narrow_promotion_passes_private_scalar_value(self):
        p,_=build('total=0 FOR source.small=1 TO 3 DO change(source.small) total=total+source.small ENDFOR',routines='ROUTINE change(v:INTEGER) BEGIN v=99 END change');self.assertEqual(p.run()['TOTAL'],6)
    def test_saved_context_roundtrip_contains_counter_missing_marker(self):
        p,_=build('FOR source.count=1 TO 2 DO ENDFOR');p.run();saved=p._state.execution.to_config();self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_report_marks_owned_path_root(self):
        _,r=build('FOR source.count=1 TO 2 DO ENDFOR');row=r.report['reference_for_counters'][0];self.assertTrue(row['path_counter']);self.assertEqual(row['root'],'SOURCE');self.assertEqual(row['root_type_spec'][0],'PATH')

class PathForCaptureLifetimeTests(unittest.TestCase):
    def test_bank_selector_evaluates_once(self):
        p,_=build('total=0 FOR bank[pick()].count=1 TO 3 DO slot=2 total=total+bank[1].count ENDFOR',routines='ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN slot END pick');v=p.run();self.assertEqual((v['TOTAL'],v['VISITS']),(6,1))
    def test_node_selector_evaluates_once(self):
        p,_=build('APPEND_NODE(source,status) APPEND_NODE(source,status) total=0 FOR source[pick()].count=1 TO 3 DO slot=2 total=total+source[1].count ENDFOR',routines='ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN slot END pick');v=p.run();self.assertEqual((v['TOTAL'],v['VISITS']),(6,1))
    def test_initial_effect_cannot_retarget_capture(self):
        p,_=build('total=0 FOR bank[slot].count=start_value() TO 3 DO total=total+bank[1].count ENDFOR',routines='ROUTINE start_value:INTEGER BEGIN slot=2 RETURN 1 END start_value');self.assertEqual(p.run()['TOTAL'],6)
    def test_final_effect_observes_initialized_counter(self):
        p,_=build('total=0 FOR source.count=1 TO finish() DO total=total+source.count ENDFOR',routines='ROUTINE finish:INTEGER BEGIN result=source.count RETURN 3 END finish');v=p.run();self.assertEqual((v['TOTAL'],v['RESULT']),(6,1))
    def test_final_effect_can_change_start_before_range_capture(self):
        p,_=build('total=0 FOR source.count=1 TO finish() DO total=total+source.count ENDFOR',routines='ROUTINE finish:INTEGER BEGIN source.count=2 RETURN 3 END finish');self.assertEqual(p.run()['TOTAL'],5)
    def test_final_node_deletion_retains_counter_and_using_capture(self):
        p,_=build('APPEND_NODE(source,status) total=0 USING source[1] DO FOR count=1 TO finish() DO total=total+count ENDFOR ENDUSING',routines='ROUTINE finish:INTEGER BEGIN DELETE_NODE(source,1,status) RETURN 3 END finish');v=p.run();self.assertEqual((v['TOTAL'],v['SOURCE']['nodes']),(6,[]))
    def test_initial_failure_keeps_previous_counter(self):
        p,_=build('FOR source.count=limit TO 3 DO ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(count(p),17)
    def test_final_failure_cleans_initialized_counter(self):
        p,_=build('FOR source.count=1 TO limit DO ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(count(p),rt.UNINITIALIZED)
    def test_bad_narrow_initial_keeps_previous_value(self):
        p,_=build('source.small=7 FOR source.small=256 TO 255 DO ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(raw(p).data.values['SMALL'],7)
    def test_bad_narrow_final_cleans_selected_leaf(self):
        p,_=build('FOR source.small=1 TO 256 DO ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(raw(p).data.values['SMALL'],rt.UNKNOWN_BYTE)
    def test_pause_resume_keeps_iteration_and_reference(self):
        p,_=build('total=0 FOR source.count=1 TO 3 DO total=total+source.count IF source.count=1 THEN PAUSE ENDIF ENDFOR')
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(count(p),1);p.resume();self.assertEqual(p.snapshot()['TOTAL'],6);self.assertIs(count(p),rt.UNINITIALIZED)
    def test_stop_cleans_active_counter(self):
        p,_=build('FOR source.count=1 TO 3 DO PAUSE ENDFOR')
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertIs(count(p),rt.UNINITIALIZED);self.assertEqual(raw(p).data.values['OTHER'],9)
    def test_abort_cleans_counter(self):
        p,_=build('FOR source.count=1 TO 3 DO ABORT ENDFOR')
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertIs(count(p),rt.UNINITIALIZED)
    def test_body_failure_cleans_counter(self):
        p,_=build('FOR source.count=1 TO 3 DO result=1/0 ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(count(p),rt.UNINITIALIZED)
    def test_routine_return_cleans_fresh_local_counter(self):
        p,_=build('result=work()',routines='ROUTINE work:INTEGER VAR local_path:route_t BEGIN FOR local_path.count=1 TO 3 DO RETURN local_path.count ENDFOR RETURN 0 END work');self.assertEqual(p.run()['RESULT'],1);self.assertEqual(p._state.local_frames,[])
    def test_jump_out_cleans_counter(self):
        p,_=build('FOR source.count=1 TO 3 DO GO TO after ENDFOR after:: flag=UNINIT(source.count)');self.assertTrue(p.run()['FLAG'])
    def test_same_loop_jumps_do_not_repeat_bounds(self):
        p,_=build('total=0 FOR source.count=1 TO finish() DO total=total+source.count GO TO tail unused_body:: result=99 tail:: visits=visits+1 ENDFOR',routines='ROUTINE finish:INTEGER BEGIN visits=visits+10 RETURN 3 END finish');v=p.run();self.assertEqual((v['TOTAL'],v['VISITS'],v['RESULT']),(6,13,U))
    def test_labelled_and_structured_parity(self):
        values=[build('total=0 FOR source.count=1 TO 3 DO total=total+source.count ENDFOR',labelled=labelled)[0].run() for labelled in (False,True)];self.assertEqual(values[0],values[1])

class PathForProofTests(unittest.TestCase):
    def test_direct_counter_write_rejects(self):self.assertEqual(reject('FOR source.count=1 TO 2 DO source.count=9 ENDFOR'),'E_FOR_COUNTER')
    def test_sibling_header_write_rejects(self):self.assertEqual(reject('FOR source.count=1 TO 2 DO source.other=9 ENDFOR'),'E_FOR_COUNTER')
    def test_node_mutation_rejects_for_header_counter(self):self.assertEqual(reject('FOR source.count=1 TO 2 DO APPEND_NODE(source,status) ENDFOR'),'E_FOR_COUNTER')
    def test_node_deletion_rejects_for_node_counter(self):self.assertEqual(reject('FOR source[1].count=1 TO 2 DO DELETE_NODE(source,1,status) ENDFOR'),'E_FOR_COUNTER')
    def test_bank_other_cell_write_rejects(self):self.assertEqual(reject('FOR bank[1].count=1 TO 2 DO bank[2].other=9 ENDFOR'),'E_FOR_COUNTER')
    def test_whole_path_assignment_rejects(self):self.assertEqual(reject('FOR source.count=1 TO 2 DO source=other ENDFOR'),'E_FOR_COUNTER')
    def test_whole_bank_assignment_rejects(self):self.assertEqual(reject('FOR bank[1].count=1 TO 2 DO bank=bank ENDFOR'),'E_FOR_COUNTER')
    def test_same_root_nested_counter_rejects(self):self.assertEqual(reject('FOR source.count=1 TO 2 DO FOR source.other=1 TO 2 DO ENDFOR ENDFOR'),'E_FOR_COUNTER')
    def test_read_into_sibling_rejects(self):self.assertEqual(reject('FOR source.count=1 TO 2 DO READ(source.other) ENDFOR'),'E_FOR_COUNTER')
    def test_scalar_conversion_output_rejects(self):self.assertEqual(reject("FOR source.count=1 TO 2 DO CNV_STR_INT('9',source.other) ENDFOR"),'E_FOR_COUNTER')
    def test_indirect_variable_write_rejects(self):self.assertEqual(reject("FOR source.count=1 TO 2 DO SET_VAR(result,'','SOURCE.OTHER',9,status) ENDFOR"),'E_FOR_COUNTER')
    def test_mutable_scalar_argument_rejects(self):self.assertEqual(reject('FOR source.count=1 TO 2 DO change(source.other) ENDFOR',routines='ROUTINE change(v:INTEGER) BEGIN v=9 END change'),'E_FOR_COUNTER')
    def test_mutable_path_argument_rejects(self):self.assertEqual(reject('FOR source.count=1 TO 2 DO change(source) ENDFOR',routines='ROUTINE change(v:route_t) BEGIN v.other=9 END change'),'E_FOR_COUNTER')
    def test_transitive_global_root_write_rejects(self):self.assertEqual(reject('FOR source.count=1 TO 2 DO relay ENDFOR',routines='ROUTINE change BEGIN source.other=9 END change ROUTINE relay BEGIN change END relay'),'E_FOR_COUNTER')
    def test_unknown_external_effects_reject_for_global_path(self):self.assertEqual(reject('FOR source.count=1 TO 2 DO opaque ENDFOR',routines='ROUTINE opaque FROM LIB'),'E_FOR_COUNTER')
    def test_parameterized_nonlocal_root_rejects(self):self.assertEqual(reject('work(2)',routines='ROUTINE work(v:INTEGER) BEGIN FOR source.count=1 TO v DO ENDFOR END work'),'E_FOR_COUNTER')
    def test_borrowed_formal_root_rejects(self):self.assertEqual(reject('work(source)',routines='ROUTINE work(v:route_t) BEGIN FOR v.count=1 TO 2 DO ENDFOR END work'),'E_FOR_COUNTER')
    def test_imported_root_rejects(self):
        source=f'PROGRAM MAIN {PREFIX} VAR alias FROM LIB:route_t BEGIN FOR alias.count=1 TO 2 DO ENDFOR END MAIN'
        from karel2py import translate
        with self.assertRaises(TranslationError) as caught:translate(source)
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
    def test_direct_computed_root_rejects(self):self.assertEqual(reject('FOR make().count=1 TO 2 DO ENDFOR',routines='ROUTINE make:route_t BEGIN RETURN source END make'),'E_SYNTAX')
    def test_real_counter_rejects(self):self.assertEqual(reject('FOR source.value=1 TO 2 DO ENDFOR',prefix='TYPE h=STRUCTURE value:REAL ENDSTRUCTURE route_t=PATH PATHHEADER=h',seed=False),'E_FOR_COUNTER')
    def test_config_domain_counter_rejects(self):self.assertEqual(reject('FOR source.cfg.cfg_turn_no1=1 TO 2 DO ENDFOR',prefix='TYPE h=STRUCTURE cfg:CONFIG ENDSTRUCTURE route_t=PATH PATHHEADER=h',seed=False),'E_FOR_COUNTER')
    def test_connected_timer_root_rejects(self):self.assertEqual(reject('CONNECT TIMER TO source.other FOR source.count=1 TO 2 DO ENDFOR',cooperative=True),'E_FOR_COUNTER')
    def test_direct_handler_root_write_rejects(self):self.assertEqual(reject('CONDITION[1]: WHEN EVENT[1] DO source.other=9 ENDCONDITION FOR source.count=1 TO 2 DO ENDFOR',cooperative=True),'E_FOR_COUNTER')
    def test_named_using_header_root_is_protected(self):self.assertEqual(reject('USING source DO FOR count=1 TO 2 DO other=9 ENDFOR ENDUSING'),'E_FOR_COUNTER')

class PathForRetainedAliasTests(unittest.TestCase):
    RETAIN='ROUTINE retain(v:route_t) BEGIN CONDITION[1]: WHEN EVENT[1] DO v.other=42 ENDCONDITION END retain'
    def test_retained_writable_root_alias_rejects(self):self.assertEqual(reject('retain(source) FOR source.count=1 TO 2 DO ENDFOR',routines=self.RETAIN),'E_FOR_COUNTER')
    def test_retained_writable_scalar_alias_rejects(self):self.assertEqual(reject('retain(source.other) FOR source.count=1 TO 2 DO ENDFOR',routines='ROUTINE retain(v:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO v=42 ENDCONDITION END retain'),'E_FOR_COUNTER')
    def test_transitive_retained_alias_rejects(self):self.assertEqual(reject('relay(source) FOR source.count=1 TO 2 DO ENDFOR',routines=self.RETAIN+' ROUTINE relay(v:route_t) BEGIN retain(v) END relay'),'E_FOR_COUNTER')
    def test_unknown_retained_byname_alias_rejects(self):self.assertEqual(reject("retain(BYNAME('','SOURCE',status)) FOR source.count=1 TO 2 DO ENDFOR",routines=self.RETAIN),'E_FOR_COUNTER')
    def test_retained_writable_formal_rejects_fresh_local_root(self):self.assertEqual(reject('work',routines=self.RETAIN+' ROUTINE work VAR local_path:route_t BEGIN retain(local_path) FOR local_path.count=1 TO 2 DO ENDFOR END work'),'E_FOR_COUNTER')
    def test_readonly_retained_scalar_alias_is_allowed(self):
        routine='ROUTINE retain(v:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO result=v ENDCONDITION END retain'
        p,_=build('retain(source.other) total=0 FOR source.count=1 TO 2 DO total=total+source.count ENDFOR ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=routine);v=p.run();self.assertEqual((v['TOTAL'],v['RESULT']),(3,9))
    def test_readonly_retained_path_alias_is_allowed(self):
        routine='ROUTINE retain(v:route_t) BEGIN CONDITION[1]: WHEN EVENT[1] DO result=v.other ENDCONDITION END retain'
        p,_=build('retain(source) total=0 FOR source.count=1 TO 2 DO total=total+source.count ENDFOR ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=routine);v=p.run();self.assertEqual((v['TOTAL'],v['RESULT']),(3,9))
    def test_grouped_retained_path_is_private(self):
        p,_=build('retain((source)) total=0 FOR source.count=1 TO 2 DO total=total+source.count ENDFOR ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=self.RETAIN);v=p.run();self.assertEqual((v['TOTAL'],v['SOURCE']['data']['OTHER']),(3,9))
    def test_promoted_retained_scalar_is_private(self):
        routine='ROUTINE retain(v:REAL) BEGIN CONDITION[1]: WHEN EVENT[1] DO v=42 ENDCONDITION END retain'
        p,_=build('source.small=1 retain(source.small) total=0 FOR source.count=1 TO 2 DO total=total+source.count ENDFOR ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=routine);v=p.run();self.assertEqual((v['TOTAL'],v['SOURCE']['data']['SMALL']),(3,1))
    def test_frame_scoped_timer_does_not_leave_a_retained_alias(self):
        routine='ROUTINE work(v:route_t) BEGIN CONNECT TIMER TO v.other END work'
        p,_=build('work(source) total=0 FOR source.count=1 TO 2 DO total=total+source.count ENDFOR',routines=routine,clock_us=lambda:0);self.assertEqual(p.run()['TOTAL'],3);self.assertEqual(p._state._timers,{})
    def test_unknown_byname_does_not_claim_fresh_local_storage(self):
        routine=self.RETAIN+' ROUTINE work VAR local_path:route_t BEGIN total=0 FOR local_path.count=1 TO 2 DO total=total+local_path.count ENDFOR END work'
        p,_=build("retain(BYNAME('','SOURCE',status)) work",routines=routine);self.assertEqual(p.run()['TOTAL'],3)

class PathForValidationTests(unittest.TestCase):
    def test_bad_root_data_rejects_before_initial_effect(self):
        p,_=build('FOR source.count=start_value() TO 2 DO ENDFOR',seed=False,routines='ROUTINE start_value:INTEGER BEGIN visits=1 RETURN 1 END start_value');raw(p).data.values['COUNT']=17;raw(p).data.values['OTHER']='bad';p._state.values['VISITS']=0
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((count(p),p.snapshot()['VISITS']),(17,0))
    def test_shared_owned_node_cells_reject(self):
        p,_=build('FOR source.count=1 TO 2 DO ENDFOR',seed=False);raw(p).append();raw(p).nodes*=2
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_shared_bank_path_cells_reject(self):
        p,_=build('FOR bank[1].count=1 TO 2 DO ENDFOR',seed=False);raw(p,'BANK').values[1]=raw(p,'BANK').values[0]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_snapshot_budget_is_retained(self):
        p,_=build('FOR source.count=1 TO 2 DO ENDFOR',seed=False);raw(p).append();raw(p).nodes=[deepcopy(node(p)) for _ in range(5000)]
        with self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):p.run()
    def test_root_schema_substitution_rejects(self):
        p,_=build('FOR source.count=1 TO 2 DO ENDFOR',seed=False);raw(p).spec=('PATH',None,None)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_helper_rejects_unrelated_scalar(self):
        p,_=build('',seed=False);root=p._state.reference('SOURCE');target=p._state.reference('TOTAL')
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.path_for_reference(root,root.spec,target)
    def test_helper_rejects_forged_leaf_domain(self):
        p,_=build('',seed=False);root=p._state.reference('SOURCE');target=rt.Reference(('BYTE',),raw(p).data.values,'COUNT')
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.path_for_reference(root,root.spec,target)
    def test_helper_does_not_treat_descriptor_as_scalar(self):
        p,_=build('',seed=False);root=p._state.reference('SOURCE');target=rt.Reference(('INTEGER',),p._state.values,'SOURCE')
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.path_for_reference(root,root.spec,target)
    def test_readonly_scalar_reference_rejects(self):
        p,_=build('',seed=False);root=p._state.reference('SOURCE');target=rt.ReadOnlyFieldReference(('INTEGER',),raw(p).data.values,'COUNT')
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.path_for_reference(root,root.spec,target)
    def test_legacy_runtime_scope_rejects(self):
        p,_=build('',seed=False);root=p._state.reference('SOURCE');target=rt.Reference(('INTEGER',),raw(p).data.values,'COUNT')
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.path_for_reference(root,root.spec,target)
    def test_policy_records_alias_and_bound_guards(self):
        _,r=build('FOR source.count=1 TO 2 DO ENDFOR');policy=r.report['path_for_policy'];self.assertIn('retained writable',policy['proof']);self.assertIn('32767',policy['bounds']);self.assertFalse(policy['controller_validated'])

class StablePathNodeUsingTests(unittest.TestCase):
    def test_delete_selected_node_does_not_retarget_using(self):
        p,_=build('APPEND_NODE(source,status) APPEND_NODE(source,status) source[1].count=11 source[2].count=22 USING source[1] DO DELETE_NODE(source,1,status) count=42 result=count ENDUSING');v=p.run();self.assertEqual((v['RESULT'],v['SOURCE']['nodes'][0]['COUNT']),(42,22))
    def test_deleting_an_earlier_node_keeps_selected_node(self):
        p,_=build('APPEND_NODE(source,status) APPEND_NODE(source,status) source[2].count=22 USING source[2] DO DELETE_NODE(source,1,status) result=count ENDUSING');self.assertEqual(p.run()['RESULT'],22)
    def test_whole_path_copy_detaches_old_selected_node(self):
        p,_=build('APPEND_NODE(source,status) APPEND_NODE(other,status) source[1].count=11 other[1].count=22 USING source[1] DO source=copy_other() result=count ENDUSING',routines='ROUTINE copy_other:route_t BEGIN RETURN other END copy_other');v=p.run();self.assertEqual((v['RESULT'],v['SOURCE']['nodes'][0]['COUNT']),(11,22))
    def test_bank_combined_node_selector_is_stable(self):
        p,_=build('APPEND_NODE(bank[2],status) bank[2][1].count=17 USING bank[2,1] DO DELETE_NODE(bank[2],1,status) result=count ENDUSING');self.assertEqual(p.run()['RESULT'],17)
    def test_retained_handler_keeps_deleted_node(self):
        p,_=build('APPEND_NODE(source,status) source[1].count=17 USING source[1] DO CONDITION[1]: WHEN EVENT[1] DO count=42 result=count ENDCONDITION ENDUSING DELETE_NODE(source,1,status) ENABLE CONDITION[1] SIGNAL EVENT[1]');v=p.run();self.assertEqual((v['RESULT'],v['SOURCE']['nodes']),(42,[]))
    def test_pause_keeps_old_node_after_host_removal(self):
        p,_=build('APPEND_NODE(source,status) source[1].count=17 USING source[1] DO PAUSE result=count ENDUSING')
        with self.assertRaises(rt.KarelPause):p.run()
        raw(p).nodes.clear();p.resume();self.assertEqual(p.snapshot()['RESULT'],17)
    def test_detached_counter_at_entry_cannot_claim_current_root(self):
        p,_=build('APPEND_NODE(source,status) USING source[1] DO DELETE_NODE(source,1,status) FOR count=1 TO 2 DO ENDFOR ENDUSING')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'current owned root'):p.run()
    def test_node_capture_metadata_is_explicit(self):
        _,r=build('APPEND_NODE(source,status) USING source[1] DO count=17 ENDUSING');self.assertTrue(r.report['using_scopes'][0]['selector_captures'][0]['path_node'])

class PathForLinkedTests(unittest.TestCase):
    def test_linked_routine_can_count_owned_global_path(self):
        sources={'main':'PROGRAM MAIN VAR result:INTEGER ROUTINE work:INTEGER FROM LIB BEGIN result=work() END MAIN','lib':f'PROGRAM LIB {PREFIX} VAR source:route_t total:INTEGER ROUTINE work:INTEGER BEGIN total=0 FOR source.count=1 TO 3 DO total=total+source.count ENDFOR RETURN total END work BEGIN END LIB'}
        project=translate_project(sources).instantiate();self.assertEqual(project.run('MAIN')['MAIN']['values']['RESULT'],6)
    def test_linked_routine_can_count_fresh_local_path_with_parameter(self):
        sources={'main':'PROGRAM MAIN VAR result:INTEGER ROUTINE work(last:INTEGER):INTEGER FROM LIB BEGIN result=work(3) END MAIN','lib':f'PROGRAM LIB {PREFIX} ROUTINE work(last:INTEGER):INTEGER VAR source:route_t total:INTEGER BEGIN total=0 FOR source.count=1 TO last DO total=total+source.count ENDFOR RETURN total END work BEGIN END LIB'}
        project=translate_project(sources).instantiate();self.assertEqual(project.run('MAIN')['MAIN']['values']['RESULT'],6)
    def test_local_counter_isolated_from_unreferenced_external_globals(self):
        calls=[];context=rt.ExecutionContext(externals={('LIB','OPAQUE'):lambda:calls.append(1)})
        p,_=build('work',context=context,routines='ROUTINE opaque FROM LIB ROUTINE work VAR source:route_t BEGIN FOR source.count=1 TO 2 DO opaque ENDFOR END work');p.run();self.assertEqual(calls,[1,1])

if __name__=='__main__':unittest.main()
