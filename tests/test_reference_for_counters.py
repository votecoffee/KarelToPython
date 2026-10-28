"""Authored captured INTEGER counter storage and conservative root write proofs."""
import json
import unittest

from karel2py import translate,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program


UNKNOWN={'uninitialized':True}
SCHEMA='''TYPE row_t=STRUCTURE count:INTEGER other:INTEGER ENDSTRUCTURE
nested_t=STRUCTURE row:row_t ENDSTRUCTURE'''
DECL='box,other_box:row_t nested:nested_t rows:ARRAY[2] OF row_t counters:ARRAY[3] OF INTEGER grid:ARRAY[2,2] OF INTEGER slot,n,total,calls,visits,result,status:INTEGER flag:BOOLEAN number:REAL'


def program(body,*,labelled=False,decl=DECL,prefix=SCHEMA,**options):
    return compile_program(('unused:: ' if labelled else '')+body,decl=decl,prefix=prefix,**options)


def execute(body,**options):return program(body,**options)[0].run()


class ReferenceForStorageTests(unittest.TestCase):
    def parity(self,body,**options):
        outcomes=[]
        for labelled in (False,True):
            p,_=program(body,labelled=labelled,**options);outcomes.append((p.run(),p._state.steps))
        self.assertEqual(outcomes[0],outcomes[1])
        return outcomes[0][0]

    def test_structure_field_initializes_and_clears_only_the_selected_leaf(self):
        values=self.parity('box.other=9 total=0 FOR box.count=1 TO 3 DO total=total+box.count ENDFOR')
        self.assertEqual((values['TOTAL'],values['BOX']),(6,{'COUNT':UNKNOWN,'OTHER':9}))

    def test_nested_record_field_counter_keeps_ordinary_storage(self):
        values=self.parity('total=0 FOR nested.row.count=1 TO 3 DO total=total+nested.row.count ENDFOR')
        self.assertEqual((values['TOTAL'],values['NESTED']['ROW']['COUNT']),(6,UNKNOWN))

    def test_array_element_counter_preserves_unrelated_elements(self):
        values=self.parity('counters[2]=99 total=0 FOR counters[1]=1 TO 3 DO total=total+counters[1] ENDFOR')
        self.assertEqual((values['TOTAL'],values['COUNTERS']),(6,[UNKNOWN,99,UNKNOWN]))

    def test_multidimensional_counter_uses_one_selected_cell(self):
        values=self.parity('grid[2,2]=99 total=0 FOR grid[1,2]=1 TO 3 DO total=total+grid[1,2] ENDFOR')
        self.assertEqual(values['TOTAL'],6);self.assertEqual(values['GRID'],[[UNKNOWN,UNKNOWN],[UNKNOWN,99]])

    def test_indexed_structure_field_is_a_scalar_counter(self):
        values=self.parity('rows[2].other=99 total=0 FOR rows[1].count=1 TO 3 DO total=total+rows[1].count ENDFOR')
        self.assertEqual((values['TOTAL'],values['ROWS'][0]['COUNT'],values['ROWS'][1]['OTHER']),(6,UNKNOWN,99))

    def test_array_index_changes_do_not_retarget_iteration_or_cleanup(self):
        values=self.parity('slot=1 counters[2]=99 total=0 FOR counters[slot]=1 TO 3 DO slot=2 total=total+counters[1] ENDFOR')
        self.assertEqual((values['TOTAL'],values['SLOT'],values['COUNTERS']),(6,2,[UNKNOWN,99,UNKNOWN]))

    def test_counter_selector_function_runs_once_per_loop_entry(self):
        routine='ROUTINE pick:INTEGER BEGIN calls=calls+1 RETURN slot END pick'
        values=self.parity('calls=0 slot=1 total=0 FOR counters[pick()]=1 TO 3 DO slot=2 total=total+counters[1] ENDFOR',routines=routine)
        self.assertEqual((values['CALLS'],values['TOTAL']),(1,6))

    def test_capture_happens_before_initial_expression_changes_the_index(self):
        routine='ROUTINE start_value:INTEGER BEGIN slot=2 RETURN 1 END start_value'
        values=self.parity('slot=1 counters[2]=99 total=0 FOR counters[slot]=start_value() TO 2 DO total=total+counters[1] ENDFOR',routines=routine)
        self.assertEqual((values['TOTAL'],values['COUNTERS']),(3,[UNKNOWN,99,UNKNOWN]))

    def test_final_expression_observes_the_initialized_captured_counter(self):
        routine='ROUTINE finish_value:INTEGER BEGIN result=counters[1] slot=2 RETURN 2 END finish_value'
        values=self.parity('slot=1 total=0 FOR counters[slot]=1 TO finish_value() DO total=total+counters[1] ENDFOR',routines=routine)
        self.assertEqual((values['TOTAL'],values['RESULT'],values['SLOT']),(3,1,2))

    def test_final_expression_can_update_captured_counter_before_start_capture(self):
        routine='ROUTINE finish_value:INTEGER BEGIN box.count=2 RETURN 3 END finish_value'
        values=self.parity('total=0 FOR box.count=1 TO finish_value() DO total=total+box.count ENDFOR',routines=routine)
        self.assertEqual(values['TOTAL'],5)

    def test_empty_range_clears_field_without_touching_sibling(self):
        values=self.parity('box.other=9 total=0 FOR box.count=3 TO 1 DO total=99 ENDFOR')
        self.assertEqual((values['TOTAL'],values['BOX']),(0,{'COUNT':UNKNOWN,'OTHER':9}))

    def test_descending_field_counter_is_inclusive(self):
        self.assertEqual(self.parity('total=0 FOR box.count=3 DOWNTO 1 DO total=total+box.count ENDFOR')['TOTAL'],6)

    def test_using_bare_field_keeps_global_same_named_variable_untouched(self):
        values=self.parity('count=99 total=0 USING box DO FOR count=1 TO 3 DO total=total+count ENDFOR ENDUSING',decl=DECL+' count:INTEGER')
        self.assertEqual((values['COUNT'],values['TOTAL'],values['BOX']['COUNT']),(99,6,UNKNOWN))

    def test_using_indexed_record_keeps_both_captures_when_indices_change(self):
        values=self.parity('slot=1 total=0 USING rows[slot] DO FOR count=1 TO 3 DO slot=2 total=total+count ENDFOR ENDUSING')
        self.assertEqual((values['TOTAL'],values['ROWS'][0]['COUNT'],values['ROWS'][1]['COUNT']),(6,UNKNOWN,UNKNOWN))

    def test_nested_using_counter_uses_innermost_selected_record(self):
        values=self.parity('total=0 USING box DO USING other_box DO FOR count=1 TO 2 DO total=total+count ENDFOR ENDUSING ENDUSING')
        self.assertEqual((values['TOTAL'],values['BOX']['COUNT'],values['OTHER_BOX']['COUNT']),(3,UNKNOWN,UNKNOWN))

    def test_independent_root_counters_can_nest(self):
        values=self.parity('total=0 FOR box.count=1 TO 2 DO FOR counters[1]=1 TO 2 DO total=total+box.count+counters[1] ENDFOR ENDFOR')
        self.assertEqual((values['TOTAL'],values['BOX']['COUNT'],values['COUNTERS'][0]),(12,UNKNOWN,UNKNOWN))

    def test_fresh_local_record_counter_in_parameterized_routine(self):
        routine='ROUTINE work(limit_value:INTEGER):INTEGER VAR local_box:row_t result_value:INTEGER BEGIN result_value=0 FOR local_box.count=1 TO limit_value DO result_value=result_value+local_box.count ENDFOR RETURN result_value END work'
        values=self.parity('result=work(3)',routines=routine)
        self.assertEqual(values['RESULT'],6)


class ReferenceForGuardTests(unittest.TestCase):
    def reject(self,body,code='E_FOR_COUNTER',**options):
        for labelled in (False,True):
            with self.subTest(labelled=labelled),self.assertRaises(TranslationError) as caught:program(body,labelled=labelled,**options)
            self.assertEqual(caught.exception.code,code,str(caught.exception))

    def test_writing_the_counter_leaf_is_blocked(self):self.reject('FOR box.count=1 TO 2 DO box.count=9 ENDFOR')

    def test_writing_a_sibling_field_is_conservatively_blocked(self):self.reject('FOR box.count=1 TO 2 DO box.other=9 ENDFOR')

    def test_writing_a_different_array_element_is_conservatively_blocked(self):self.reject('FOR counters[1]=1 TO 2 DO counters[2]=9 ENDFOR')

    def test_whole_root_replacement_is_blocked(self):self.reject('FOR box.count=1 TO 2 DO box=other_box ENDFOR')

    def test_same_root_nested_counters_are_blocked_even_when_disjoint(self):
        self.reject('FOR box.count=1 TO 2 DO FOR box.other=1 TO 2 DO ENDFOR ENDFOR')
        self.reject('FOR counters[1]=1 TO 2 DO FOR counters[2]=1 TO 2 DO ENDFOR ENDFOR')

    def test_direct_and_transitive_routine_global_writes_are_blocked(self):
        routines='ROUTINE change BEGIN box.other=9 END change\nROUTINE relay BEGIN change END relay'
        self.reject('FOR box.count=1 TO 2 DO relay ENDFOR',routines=routines)

    def test_routine_for_initialization_is_counted_as_a_root_write(self):
        self.reject('FOR box.count=1 TO 2 DO change ENDFOR',routines='ROUTINE change BEGIN FOR box.other=1 TO 2 DO ENDFOR END change')

    def test_writable_counter_and_sibling_formal_aliases_are_blocked(self):
        routine='ROUTINE change(value:INTEGER) BEGIN value=9 END change'
        self.reject('FOR box.count=1 TO 2 DO change(box.count) ENDFOR',routines=routine)
        self.reject('FOR box.count=1 TO 2 DO change(box.other) ENDFOR',routines=routine)

    def test_writable_root_record_argument_is_blocked(self):
        self.reject('FOR box.count=1 TO 2 DO change(box) ENDFOR',routines='ROUTINE change(value:row_t) BEGIN value.other=9 END change')

    def test_readonly_scalar_reference_is_usable(self):
        routine='ROUTINE observe(value:INTEGER) BEGIN total=total+value END observe'
        self.assertEqual(execute('total=0 FOR box.count=1 TO 2 DO observe(box.count) ENDFOR',routines=routine)['TOTAL'],3)

    def test_grouped_record_argument_is_an_independent_writable_copy(self):
        routine='ROUTINE change(value:row_t) BEGIN value.other=9 END change'
        values=execute('box.other=7 FOR box.count=1 TO 2 DO change((box)) ENDFOR',routines=routine)
        self.assertEqual(values['BOX'],{'COUNT':UNKNOWN,'OTHER':7})

    def test_read_output_to_sibling_field_is_blocked(self):self.reject('FOR box.count=1 TO 2 DO READ(box.other) ENDFOR')

    def test_ordinary_service_output_to_sibling_is_blocked(self):self.reject('FOR box.count=1 TO 2 DO GET_VAR(n,\'T\',\'VALUE\',box.other,status) ENDFOR')

    def test_conversion_output_through_using_alias_cannot_mutate_root(self):self.reject("USING box DO FOR count=1 TO 2 DO CNV_STR_INT('9',other) ENDFOR ENDUSING")

    def test_numeric_register_output_through_using_alias_cannot_mutate_root(self):self.reject('USING box DO FOR count=1 TO 2 DO GET_REG(1,flag,other,number,status) ENDFOR ENDUSING')

    def test_indirect_set_var_is_still_blocked_during_active_counter(self):self.reject("FOR box.count=1 TO 2 DO SET_VAR(n,'T','ANY',9,status) ENDFOR")

    def test_handler_direct_sibling_write_is_blocked(self):self.reject('CONDITION[1]: WHEN TRUE DO box.other=9 ENDCONDITION FOR box.count=1 TO 2 DO ENDFOR',cooperative=True)

    def test_handler_transitive_sibling_write_is_blocked(self):self.reject('CONDITION[1]: WHEN TRUE DO change ENDCONDITION FOR box.count=1 TO 2 DO ENDFOR',routines='ROUTINE change BEGIN box.other=9 END change',cooperative=True)

    def test_connected_timer_on_sibling_field_blocks_counter_root(self):self.reject('CONNECT TIMER TO box.other FOR box.count=1 TO 2 DO ENDFOR',cooperative=True)

    def test_selector_function_cannot_modify_an_outer_active_counter_root(self):
        self.reject('FOR box.count=1 TO 2 DO FOR counters[pick()]=1 TO 2 DO ENDFOR ENDFOR',routines='ROUTINE pick:INTEGER BEGIN box.other=9 RETURN 1 END pick')

    def test_unknown_external_global_write_effects_are_conservatively_blocked(self):
        self.reject('FOR box.count=1 TO 2 DO external_work ENDFOR',routines='ROUTINE external_work FROM LIB')
        self.reject('FOR box.count=1 TO 2 DO relay ENDFOR',routines='ROUTINE external_work FROM LIB\nROUTINE relay BEGIN external_work END relay')

    def test_handler_unknown_external_effects_are_blocked_for_aggregate_root(self):self.reject('CONDITION[1]: WHEN TRUE DO external_work ENDCONDITION FOR box.count=1 TO 2 DO ENDFOR',routines='ROUTINE external_work FROM LIB',cooperative=True)

    def test_fresh_local_aggregate_counter_is_isolated_from_no_argument_external(self):
        calls=[];context=rt.ExecutionContext(externals={('LIB','EXTERNAL_WORK'):lambda:calls.append(1)})
        routines='ROUTINE external_work FROM LIB\nROUTINE work VAR local_box:row_t BEGIN FOR local_box.count=1 TO 2 DO external_work ENDFOR END work'
        execute('work',routines=routines,context=context)
        self.assertEqual(calls,[1,1])

    def test_formal_and_nonlocal_parameterized_counter_roots_are_blocked(self):
        self.reject('work(box)',routines='ROUTINE work(value:row_t) BEGIN FOR value.count=1 TO 2 DO ENDFOR END work')
        self.reject('work(1)',routines='ROUTINE work(value:INTEGER) BEGIN FOR box.count=1 TO 2 DO ENDFOR END work')

    def test_nonintegral_counter_types_remain_rejected(self):
        for declaration in ('values:ARRAY[2] OF BOOLEAN','values:ARRAY[2] OF REAL'):
            self.reject('FOR values[1]=1 TO 2 DO ENDFOR',decl=declaration)

    def test_config_domain_fields_and_resource_root_fields_are_blocked(self):
        self.reject('FOR cfg.cfg_turn_no1=1 TO 2 DO ENDFOR',decl='cfg:CONFIG')
        self.reject('FOR track.count=1 TO 2 DO ENDFOR',decl='track:path_t',prefix='TYPE header_t=STRUCTURE count:INTEGER ENDSTRUCTURE path_t=PATH PATHHEADER=header_t')

    def test_position_orientation_descendants_remain_readonly(self):self.reject('FOR point.normal.x=1 TO 2 DO ENDFOR','E_POSITION_READ_ONLY',decl='point:POSITION')

    def test_port_resource_and_constant_counter_destinations_are_rejected(self):
        self.reject('FOR GOUT[1]=1 TO 2 DO ENDFOR')
        self.reject('FOR limit_value=1 TO 2 DO ENDFOR',prefix=SCHEMA+'\nCONST limit_value=2')

    def test_legacy_field_and_array_counter_syntax_remains_rejected(self):
        for selector in ('box.count','counters[1]'):
            with self.assertRaises(TranslationError):legacy_translate('PROGRAM T '+SCHEMA+' VAR '+DECL+' BEGIN FOR '+selector+'=1 TO 2 DO ENDFOR END T')


class ReferenceForLifetimeTests(unittest.TestCase):
    def test_bad_selector_does_not_initialize_or_clear_any_cell(self):
        p,_=program('counters[1]=9 slot=4 FOR counters[slot]=1 TO 2 DO ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['COUNTERS'],[9,UNKNOWN,UNKNOWN])

    def test_initial_failure_preserves_captured_leaf_and_sibling(self):
        for labelled in (False,True):
            p,_=program('box.count=9 box.other=7 FOR box.count=n TO 2 DO ENDFOR',labelled=labelled)
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['BOX'],{'COUNT':9,'OTHER':7})

    def test_final_failure_clears_only_initialized_captured_leaf(self):
        for labelled in (False,True):
            p,_=program('box.other=7 FOR box.count=1 TO n DO ENDFOR',labelled=labelled)
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['BOX'],{'COUNT':UNKNOWN,'OTHER':7})

    def test_goto_exit_clears_original_element_after_index_changes(self):
        values=execute('slot=1 counters[2]=99 FOR counters[slot]=1 TO 3 DO slot=2 GOTO done ENDFOR done:: flag=UNINIT(counters[1])')
        self.assertEqual((values['FLAG'],values['COUNTERS']),(True,[UNKNOWN,99,UNKNOWN]))

    def test_same_loop_goto_retains_one_capture_and_current_leaf(self):
        routine='ROUTINE pick:INTEGER BEGIN calls=calls+1 RETURN slot END pick'
        values=execute('calls=0 slot=1 total=0 visits=0 FOR counters[pick()]=1 TO 2 DO again:: total=total+counters[1] slot=2 visits=visits+1 IF visits=1 THEN GOTO again ENDIF ENDFOR',routines=routine)
        self.assertEqual((values['CALLS'],values['TOTAL'],values['VISITS']),(1,4,3))

    def test_nested_exit_clears_inner_leaf_and_preserves_outer_record_counter(self):
        values=execute('total=0 FOR box.count=1 TO 2 DO FOR counters[1]=1 TO 2 DO total=total+box.count GOTO after_inner ENDFOR after_inner:: flag=UNINIT(counters[1]) ENDFOR')
        self.assertEqual((values['TOTAL'],values['FLAG'],values['BOX']['COUNT']),(3,True,UNKNOWN))

    def test_return_of_scalar_captures_value_before_leaf_cleanup(self):
        routines='ROUTINE work:INTEGER BEGIN FOR box.count=1 TO 2 DO RETURN box.count ENDFOR RETURN 9 END work'
        values=execute('result=work()',routines=routines)
        self.assertEqual((values['RESULT'],values['BOX']['COUNT']),(1,UNKNOWN))

    def test_returned_record_snapshot_retains_value_after_local_counter_cleanup(self):
        routine='ROUTINE make:row_t VAR local_box:row_t BEGIN local_box.other=9 FOR local_box.count=1 TO 2 DO suffix:: RETURN local_box ENDFOR RETURN local_box END make'
        values=execute('other_box=make()',routines=routine)
        self.assertEqual(values['OTHER_BOX'],{'COUNT':1,'OTHER':9})

    def test_abort_clears_leaf_and_preserves_sibling_effects(self):
        p,_=program('box.other=9 FOR box.count=1 TO 2 DO suffix:: ABORT ENDFOR')
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(p.snapshot()['BOX'],{'COUNT':UNKNOWN,'OTHER':9})

    def test_body_error_and_callback_failure_clear_selected_leaf(self):
        for body,options in (('n=1 DIV 0',{}),('WRITE(box.count)',{'write':lambda request:(_ for _ in ()).throw(RuntimeError('authored failure'))})):
            p,_=program('box.other=9 FOR box.count=1 TO 2 DO suffix:: '+body+' ENDFOR',**options)
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['BOX'],{'COUNT':UNKNOWN,'OTHER':9})

    def test_budget_failure_clears_captured_leaf(self):
        p,_=program('box.other=9 FOR box.count=1 TO 2 DO suffix:: GOTO suffix ENDFOR')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=12)
        self.assertEqual(p.snapshot()['BOX'],{'COUNT':UNKNOWN,'OTHER':9})

    def test_pause_resume_preserves_reference_when_index_has_changed(self):
        p,_=program('slot=1 counters[2]=99 total=0 FOR counters[slot]=1 TO 2 DO total=total+counters[1] slot=2 IF counters[1]=1 THEN PAUSE ENDIF ENDFOR',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['COUNTERS'],[1,99,UNKNOWN])
        values=p.resume();self.assertEqual((values['TOTAL'],values['COUNTERS']),(3,[UNKNOWN,99,UNKNOWN]))

    def test_stopping_paused_dispatcher_clears_original_element(self):
        p,_=program('slot=1 counters[2]=99 FOR counters[slot]=1 TO 2 DO suffix:: slot=2 PAUSE ENDFOR',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(p.snapshot()['COUNTERS'],[UNKNOWN,99,UNKNOWN])

    def test_stop_during_initial_bound_preserves_previous_leaf(self):
        routine='ROUTINE start_value:INTEGER BEGIN PAUSE RETURN 1 END start_value'
        p,_=program('box.count=9 FOR box.count=start_value() TO 2 DO suffix:: ENDFOR',routines=routine,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(p.snapshot()['BOX']['COUNT'],9)

    def test_stop_during_final_bound_clears_initialized_leaf(self):
        routine='ROUTINE finish_value:INTEGER BEGIN PAUSE RETURN 2 END finish_value'
        p,_=program('box.other=9 FOR box.count=1 TO finish_value() DO suffix:: ENDFOR',routines=routine,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(p.snapshot()['BOX'],{'COUNT':UNKNOWN,'OTHER':9})

    def test_values_can_be_serialized_without_captured_reference_or_iterator(self):
        p,_=program('box.other=9 FOR box.count=1 TO 2 DO PAUSE ENDFOR',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        config=json.loads(json.dumps(p._state.execution.to_config()))
        self.assertTrue(any(row['path']=='BOX' and row['value']['COUNT']==1 for row in config['variables']))
        self.assertNotIn('iterator',json.dumps(config).lower());p.stop()


class ReferenceForReportsTests(unittest.TestCase):
    def test_selector_report_records_root_capture_and_cleanup(self):
        _,translation=program('slot=1 FOR counters[slot]=1 TO 2 DO ENDFOR')
        rows=translation.report['reference_for_counters'];self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['selector'],rows[0]['root'],rows[0]['kind']),('COUNTERS[SLOT]','COUNTERS','index'))
        self.assertTrue(rows[0]['captured_once']);self.assertEqual(rows[0]['cleanup'],'selected_scalar')

    def test_dispatcher_report_keeps_complete_counter_selector(self):
        _,translation=program('FOR rows[1].count=1 TO 2 DO suffix:: ENDFOR')
        graph=translation.report['control_flow']['program']
        self.assertEqual(graph['for_scopes'][0]['counter'],'ROWS[1].COUNT')

    def test_using_report_names_original_root_and_counter_field(self):
        _,translation=program('USING rows[1] DO FOR count=1 TO 2 DO ENDFOR ENDUSING')
        row=translation.report['reference_for_counters'][0]
        self.assertEqual((row['root'],row['selector']),('ROWS','ROWS[1].COUNT'))

    def test_selector_call_is_not_duplicated_by_report_type_inference(self):
        _,translation=program('FOR counters[pick()]=1 TO 2 DO ENDFOR',routines='ROUTINE pick:INTEGER BEGIN RETURN 1 END pick')
        self.assertEqual(translation.python_source.count('self._routine_PICK('),1)
        self.assertEqual(len(translation.report['reference_for_counters']),1)


if __name__=='__main__':unittest.main()
