"""Authored bounded dynamic transfers, missing data and ordered capture cases."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


BASE='e,s,n: INTEGER'
MISSING={'uninitialized':True}
BYTE={'unknown_byte':True}


def transfer(action='GET_VAR',path='A',value='b',status='s'):
    return f"{action}(e,'','{path}',{value},{status})"


class BoundedArrayTransferTests(unittest.TestCase):
    def test_get_smaller_source_preserves_destination_tail(self):
        state=run('a[1]=10 a[2]=20 b[3]=30 '+transfer(),decl=BASE+' a: ARRAY[2] OF INTEGER b: ARRAY[3] OF INTEGER')
        self.assertEqual((state['B'],state['S']),([10,20,30],0))

    def test_set_smaller_source_preserves_destination_tail(self):
        state=run('a[1]=10 a[2]=20 b[3]=30 '+transfer('SET_VAR','B','a'),decl=BASE+' a: ARRAY[2] OF INTEGER b: ARRAY[3] OF INTEGER')
        self.assertEqual((state['B'],state['S']),([10,20,30],0))

    def test_larger_source_ignores_uninitialized_tail(self):
        for action in ('GET_VAR','SET_VAR'):
            call=transfer() if action=='GET_VAR' else transfer(action,'B','a')
            with self.subTest(action=action):
                state=run('a[1]=10 a[2]=20 '+call,decl=BASE+' a: ARRAY[4] OF INTEGER b: ARRAY[2] OF INTEGER')
                self.assertEqual((state['B'],state['S']),([10,20],0))

    def test_destination_unknown_tail_does_not_mark_transfer_missing(self):
        state=run('a[1]=10 '+transfer(),decl=BASE+' a: ARRAY[1] OF INTEGER b: ARRAY[3] OF INTEGER')
        self.assertEqual((state['B'],state['S']),([10,MISSING,MISSING],0))

    def test_selected_missing_elements_are_transferred(self):
        for action in ('GET_VAR','SET_VAR'):
            call=transfer() if action=='GET_VAR' else transfer(action,'B','a')
            with self.subTest(action=action):
                state=run('a[1]=10 b[2]=20 b[3]=30 '+call,decl=BASE+' a: ARRAY[2] OF INTEGER b: ARRAY[3] OF INTEGER')
                self.assertEqual((state['B'],state['S']),([10,MISSING,30],12311))

    def test_unknown_byte_markers_are_not_missing_flags(self):
        for action in ('GET_VAR','SET_VAR'):
            call=transfer() if action=='GET_VAR' else transfer(action,'B','a')
            with self.subTest(action=action):
                state=run('a[1]=7 b[3]=9 '+call,decl=BASE+' a: ARRAY[2] OF BYTE b: ARRAY[3] OF BYTE')
                self.assertEqual((state['B'],state['S']),([7,BYTE,9],0))

    def test_string_array_elements_truncate_to_receiver_capacity(self):
        state=run("a[1]='abcd' a[2]='xyz' b[3]='end' "+transfer(),decl=BASE+' a: ARRAY[2] OF STRING[8] b: ARRAY[3] OF STRING[3]')
        self.assertEqual((state['B'],state['S']),(['abc','xyz','end'],0))

    def test_named_outer_array_identities_do_not_block_prefix_copy(self):
        state=run('a[1]=7 a[2]=9 b[3]=11 '+transfer('SET_VAR','B','a'),decl=BASE+' a: small_t b: large_t',prefix='TYPE small_t=ARRAY[2] OF INTEGER large_t=ARRAY[3] OF INTEGER')
        self.assertEqual(state['B'],[7,9,11])

    def test_matrix_prefix_is_row_major(self):
        body='a[1,1]=1 a[1,2]=2 a[2,1]=3 a[2,2]=4 b[3,1]=5 b[3,2]=6 '+transfer()
        state=run(body,decl=BASE+' a: ARRAY[2,2] OF INTEGER b: ARRAY[3,2] OF INTEGER')
        self.assertEqual((state['B'],state['S']),([[1,2],[3,4],[5,6]],0))

    def test_three_dimensional_shapes_can_differ(self):
        state=run('a[1,1,1]=1 a[1,1,2]=2 a[1,2,1]=3 '+transfer(),decl=BASE+' a: ARRAY[2,2,2] OF INTEGER b: ARRAY[1,1,3] OF INTEGER')
        self.assertEqual((state['B'],state['S']),([[[1,2,3]]],0))

    def test_named_nested_array_matches_flat_matrix_rank(self):
        state=run('a[1,1]=1 a[1,2]=2 a[2,1]=3 a[2,2]=4 '+transfer(),decl=BASE+' a: ARRAY[2] OF row_t b: ARRAY[2,3] OF INTEGER',prefix='TYPE row_t=ARRAY[2] OF INTEGER')
        self.assertEqual((state['B'],state['S']),([[1,2,3],[4,MISSING,MISSING]],0))

    def test_missing_nested_array_expands_only_transferred_destination_prefix(self):
        program,_=compile_program('a[1,1]=7 '+transfer(),decl=BASE+' a: ARRAY[2] OF row_t b: ARRAY[3] OF row_t',prefix='TYPE row_t=ARRAY[2] OF INTEGER')
        program._state.values['A'].values[1]=rt.UNINITIALIZED
        program._state.values['B'].values[2]=rt.UNINITIALIZED
        state=program.run();self.assertEqual(state['B'],[[7,MISSING],[MISSING,MISSING],MISSING]);self.assertEqual(state['S'],12311)

    def test_array_rank_mismatch_is_status_only(self):
        state=run('e=9 b[1]=7 '+transfer(),decl=BASE+' a: ARRAY[1,2] OF INTEGER b: ARRAY[2] OF INTEGER')
        self.assertEqual((state['B'],state['E'],state['S']),([7,MISSING],9,3))

    def test_array_numeric_element_conversion_is_not_implicit(self):
        state=run('e=9 a[1]=7 b[1]=9 '+transfer('SET_VAR','B','a'),decl=BASE+' a: ARRAY[1] OF INTEGER b: ARRAY[1] OF REAL')
        self.assertEqual((state['B'],state['E'],state['S']),([9.],9,3))

    def test_nominal_record_leaf_types_remain_exact(self):
        state=run('e=9 b[1].id=7 '+transfer(),decl=BASE+' a: ARRAY[1] OF first_t b: ARRAY[2] OF second_t',prefix='TYPE first_t=STRUCTURE id: INTEGER ENDSTRUCTURE second_t=STRUCTURE id: INTEGER ENDSTRUCTURE')
        self.assertEqual((state['B'][0]['ID'],state['E'],state['S']),(7,9,3))

    def test_late_invalid_selected_value_preserves_all_outputs(self):
        program,_=compile_program('e=9 b[1]=99 b[2]=88 '+transfer(),decl=BASE+' a,b: ARRAY[2] OF REAL')
        program._state.values['A'].values[:]=[7.,float('nan')]
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['B'],program.snapshot()['E']),([99.,88.],9))

    def test_untransferred_nonfinite_numeric_tail_is_not_read(self):
        program,_=compile_program(transfer(),decl=BASE+' a: ARRAY[2] OF REAL b: ARRAY[1] OF REAL')
        program._state.values['A'].values[:]=[7.,float('nan')]
        self.assertEqual((program.run()['B'],program.snapshot()['S']),([7.],0))

    def test_malformed_destination_shape_is_guarded_before_copy(self):
        program,_=compile_program('a[1]=7 '+transfer(),decl=BASE+' a: ARRAY[1] OF INTEGER b: ARRAY[2] OF INTEGER')
        program._state.values['B'].values.pop()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'malformed ARRAY'): program.run()
        self.assertEqual(program._state.values['B'].values,[rt.UNINITIALIZED])

    def test_prefix_commit_preserves_captured_element_aliases(self):
        program,_=compile_program('a[1]=7 '+transfer(),decl=BASE+' a: ARRAY[1] OF INTEGER b: ARRAY[2] OF INTEGER')
        alias=rt.index_reference(program._state.values['B'],1);program.run()
        self.assertEqual(alias.raw(),7)

    def test_generic_array_source_formal_uses_actual_shape(self):
        routines="ROUTINE put(values: ARRAY OF INTEGER) BEGIN SET_VAR(e,'','B',values,s) END put"
        state=run('a[1]=7 a[2]=9 b[3]=11 put(a)',decl=BASE+' a: ARRAY[2] OF INTEGER b: ARRAY[3] OF INTEGER',routines=routines)
        self.assertEqual((state['B'],state['S']),([7,9,11],0))

    def test_generic_array_output_formal_uses_actual_shape(self):
        routines="ROUTINE take(values: ARRAY OF INTEGER) BEGIN GET_VAR(e,'','A',values,s) END take"
        state=run('a[1]=7 b[2]=9 take(b)',decl=BASE+' a: ARRAY[1] OF INTEGER b: ARRAY[2] OF INTEGER',routines=routines)
        self.assertEqual((state['B'],state['S']),([7,9],0))


class MissingVariableTransferTests(unittest.TestCase):
    def test_set_uninitialized_scalar_clears_target(self):
        state=run('b=9 '+transfer('SET_VAR','B','a'),decl=BASE+' a,b: INTEGER')
        self.assertEqual((state['B'],state['S']),(MISSING,12311));self.assertGreater(state['E'],0)

    def test_grouped_missing_source_is_captured_as_data(self):
        state=run('b=9 '+transfer('SET_VAR','B','((a))'),decl=BASE+' a,b: INTEGER')
        self.assertEqual((state['B'],state['S']),(MISSING,12311))

    def test_missing_source_field(self):
        state=run('n=9 '+transfer('SET_VAR','N','box.id'),decl=BASE+' box: box_t',prefix='TYPE box_t=STRUCTURE id: INTEGER ENDSTRUCTURE')
        self.assertEqual((state['N'],state['S']),(MISSING,12311))

    def test_computation_still_requires_initialized_values(self):
        program,_=compile_program('b=9 '+transfer('SET_VAR','B','a+1'),decl=BASE+' a,b: INTEGER')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['B'],9)

    def test_get_missing_source_type_mismatch_preserves_receiver(self):
        state=run('b=TRUE e=9 '+transfer(),decl=BASE+' a: INTEGER b: BOOLEAN')
        self.assertEqual((state['B'],state['E'],state['S']),(True,9,3))

    def test_set_missing_type_mismatch_is_status_only(self):
        state=run('b=TRUE e=9 '+transfer('SET_VAR','B','a'),decl=BASE+' a: INTEGER b: BOOLEAN')
        self.assertEqual((state['B'],state['E'],state['S']),(True,9,3))

    def test_compatible_numeric_missing_set(self):
        state=run('b=9 '+transfer('SET_VAR','B','a'),decl=BASE+' a: INTEGER b: REAL')
        self.assertEqual((state['B'],state['S']),(MISSING,12311))

    def test_whole_missing_array_clears_receiver_container(self):
        program,_=compile_program('b[1]=9 '+transfer('SET_VAR','B','a'),decl=BASE+' a: ARRAY[2] OF INTEGER b: ARRAY[3] OF INTEGER')
        program._state.values['A']=rt.UNINITIALIZED
        self.assertEqual((program.run()['B'],program.snapshot()['S']),(MISSING,12311))

    def test_missing_destination_array_materializes_for_prefix(self):
        program,_=compile_program('a[1]=7 '+transfer(),decl=BASE+' a: ARRAY[1] OF INTEGER b: ARRAY[3] OF INTEGER')
        program._state.values['B']=rt.UNINITIALIZED
        self.assertEqual((program.run()['B'],program.snapshot()['S']),([7,MISSING,MISSING],0))

    def test_partial_structure_retains_known_and_missing_fields(self):
        state=run('a.id=7 b.point.x=9 '+transfer(),decl=BASE+' a,b: box_t',prefix='TYPE box_t=STRUCTURE id: INTEGER point: VECTOR ENDSTRUCTURE')
        self.assertEqual((state['B']['ID'],state['B']['POINT']['X'],state['S']),(7,MISSING,12311))

    def test_partial_config_retains_known_turns_and_independent_storage(self):
        state=run('a.cfg_turn_no1=2 '+transfer('SET_VAR','B','a')+' a.cfg_turn_no1=3',decl=BASE+' a,b: CONFIG')
        self.assertEqual((state['B']['CFG_TURN_NO1'],state['B']['CFG_FLIP'],state['S']),(2,MISSING,12311))

    def test_invalid_known_config_field_preserves_target(self):
        program,_=compile_program('b.cfg_turn_no1=1 '+transfer('SET_VAR','B','a'),decl=BASE+' a,b: CONFIG')
        program._state.values['A'].values['CFG_TURN_NO1']=8
        with self.assertRaisesRegex(rt.KarelRuntimeError,'-8..7'): program.run()
        self.assertEqual(program.snapshot()['B']['CFG_TURN_NO1'],1)

    def test_partial_joint_axes_copy_without_inventing_values(self):
        program,_=compile_program(transfer(),decl=BASE+' a,b: JOINTPOS2')
        program._state.values['A'].values[0]=1.5
        self.assertEqual((program.run()['B'],program.snapshot()['S']),({'axes':[1.5,MISSING]},12311))

    def test_unknown_byte_scalar_remains_unknown(self):
        state=run('b[1]=7 '+transfer('SET_VAR','B[1]','a[1]'),decl=BASE+' a,b: ARRAY[1] OF BYTE')
        self.assertEqual((state['B'],state['S']),([BYTE],0))

    def test_unknown_byte_cannot_be_promoted_to_numeric_value(self):
        program,_=compile_program('n=9 '+transfer('SET_VAR','N','a[1]'),decl=BASE+' a: ARRAY[1] OF BYTE')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Unknown BYTE'): program.run()
        self.assertEqual(program.snapshot()['N'],9)

    def test_generic_string_formal_keeps_actual_capacity_and_missing_state(self):
        routines="ROUTINE put(value: STRING) BEGIN SET_VAR(e,'','B',value,s) END put"
        state=run('b=\'old\' put(a)',decl=BASE+' a: STRING[4] b: STRING[8]',routines=routines)
        self.assertEqual((state['B'],state['S']),(MISSING,12311))


class DynamicTransferOrderAndGuardTests(unittest.TestCase):
    def test_set_source_snapshot_precedes_status_selector(self):
        routines='ROUTINE at: INTEGER BEGIN a[1]=99 RETURN 1 END at'
        state=run('a[1]=7 '+transfer('SET_VAR','B','a','statuses[at()]'),decl=BASE+' a,b: ARRAY[1] OF INTEGER statuses: ARRAY[1] OF INTEGER',routines=routines)
        self.assertEqual((state['A'],state['B'],state['STATUSES']),([99],[7],[0]))

    def test_missing_snapshot_precedes_later_initialization(self):
        routines='ROUTINE at: INTEGER BEGIN a=99 RETURN 1 END at'
        state=run('b=7 '+transfer('SET_VAR','B','a','statuses[at()]'),decl=BASE+' a,b: INTEGER statuses: ARRAY[1] OF INTEGER',routines=routines)
        self.assertEqual((state['A'],state['B'],state['STATUSES']),(99,MISSING,[12311]))

    def test_source_index_and_status_selectors_run_once_in_order(self):
        routines='ROUTINE from_index: INTEGER BEGIN n=n*10+1 RETURN 1 END from_index ROUTINE status_index: INTEGER BEGIN n=n*10+2 RETURN 1 END status_index'
        state=run('n=0 a[1]=7 '+transfer('SET_VAR','B','a[from_index()]','statuses[status_index()]'),decl=BASE+' a: ARRAY[2] OF INTEGER b: INTEGER statuses: ARRAY[1] OF INTEGER',routines=routines)
        self.assertEqual((state['N'],state['B']),(12,7))

    def test_source_function_runs_once(self):
        routines='ROUTINE make: row_t BEGIN n=n+1 RETURN a END make'
        state=run('n=0 a[1]=7 a[2]=9 '+transfer('SET_VAR','B','make()'),decl=BASE+' a: row_t b: ARRAY[3] OF INTEGER',prefix='TYPE row_t=ARRAY[2] OF INTEGER',routines=routines)
        self.assertEqual((state['N'],state['B']),(1,[7,9,MISSING]))

    def test_get_resolves_source_after_output_selectors(self):
        routines='ROUTINE at: INTEGER BEGIN a[1]=99 RETURN 1 END at'
        state=run('a[1]=7 '+transfer('GET_VAR','A[1]','b[at()]'),decl=BASE+' a,b: ARRAY[1] OF INTEGER',routines=routines)
        self.assertEqual(state['B'],[99])

    def test_get_source_may_also_be_receiver(self):
        state=run('a[1]=7 '+transfer('GET_VAR','A','a'),decl=BASE+' a: ARRAY[2] OF INTEGER')
        self.assertEqual((state['A'],state['S']),([7,MISSING],12311))

    def test_set_target_overlap_with_entry_is_still_rejected(self):
        program,_=compile_program('a[1]=7 '+transfer('SET_VAR','E','a[1]'),decl=BASE+' a: ARRAY[1] OF INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): program.run()

    def test_get_output_overlap_is_rejected_before_lookup(self):
        program,_=compile_program("GET_VAR(b[1],'','A',b,s)",decl=BASE+' a,b: ARRAY[2] OF INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): program.run()

    def test_dynamic_config_scalar_target_remains_protected(self):
        program,_=compile_program(transfer('SET_VAR','A.CFG_TURN_NO1','7'),decl=BASE+' a: CONFIG')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Protected'): program.run()

    def test_readonly_position_source_can_be_copied_as_a_value(self):
        state=run("CNV_STR_CONF('N',cfg,s) point=POS(0,0,0,0,0,0,cfg) "+transfer('SET_VAR','B','point.normal'),decl=BASE+' cfg: CONFIG point: POSITION b: VECTOR')
        self.assertEqual(state['B'],{'X':1.,'Y':0.,'Z':0.})

    def test_set_scalar_numeric_conversion_and_string_truncation_remain(self):
        state=run(transfer('SET_VAR','VALUE','7')+' '+transfer('SET_VAR','TEXT',"'abcdef'"),decl=BASE+' value: REAL text: STRING[3]')
        self.assertEqual((state['VALUE'],state['TEXT']),(7.,'abc'))

    def test_missing_path_preserves_value_and_entry(self):
        state=run('b=7 e=9 '+transfer('SET_VAR','ABSENT','a'),decl=BASE+' a,b: INTEGER')
        self.assertEqual((state['B'],state['E'],state['S']),(7,9,1))

    def test_malformed_record_destination_fails_before_any_field_write(self):
        program,_=compile_program('a.x=7 a.y=8 a.z=9 b.x=99 '+transfer(),decl=BASE+' a,b: VECTOR')
        del program._state.values['B'].values['Z']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'malformed record'): program.run()
        self.assertEqual(program._state.values['B'].values['X'],99.)

    def test_source_config_field_is_read_without_writable_alias(self):
        state=run('cfg.cfg_turn_no1=2 '+transfer('SET_VAR','N','cfg.cfg_turn_no1'),decl=BASE+' cfg: CONFIG')
        self.assertEqual(state['N'],2)

    def test_active_for_counter_guard_remains(self):
        with self.assertRaises(TranslationError): compile_program('FOR n=1 TO 2 DO '+transfer('SET_VAR','A','7')+' ENDFOR',decl=BASE+' a: INTEGER')

    def test_whole_file_and_path_resources_remain_rejected(self):
        for kind in ('FILE','PATH'):
            with self.subTest(kind=kind),self.assertRaises(TranslationError): compile_program(transfer('SET_VAR','VALUE','value'),decl=BASE+' value: '+kind)


class VariableTransferIntegrationTests(unittest.TestCase):
    def test_multidimensional_transferred_state_roundtrips(self):
        program,result=compile_program('a[1,1]=7 b[2,2]=9 '+transfer(),decl=BASE+' a: ARRAY[1,2] OF INTEGER b: ARRAY[2,2] OF INTEGER')
        expected=program.run();ctx=rt.ExecutionContext.from_config(json.loads(json.dumps(program._state.execution.to_config())))
        namespace={'__name__':'matrix_transfer'};exec(result.python_source,namespace)
        self.assertEqual(namespace['Program'](context=ctx).snapshot(),expected)

    def test_three_dimensional_byte_state_roundtrips(self):
        from karel2py.storage import typed_value,decode_typed
        value=rt.Array(('ARRAY',(2,1,2),('BYTE',)));value.values[0]=7
        other=decode_typed(json.loads(json.dumps(typed_value(value))))[1]
        self.assertEqual(other.snapshot(),value.snapshot());self.assertIs(other.values[1],rt.UNKNOWN_BYTE)

    def test_named_components_in_matrix_state_keep_their_boundary(self):
        from karel2py.storage import typed_value,decode_typed
        row=('ARRAY',2,('INTEGER',),'ROW');value=rt.Array(('ARRAY',(2,1),row))
        value.values[0].values[0]=7;value.values[1]=rt.UNINITIALIZED
        other=decode_typed(json.loads(json.dumps(typed_value(value))))[1]
        self.assertEqual(other.snapshot(),value.snapshot());self.assertEqual(other.spec,value.spec)

    def test_legacy_flat_matrix_state_remains_readable(self):
        from karel2py.storage import decode_typed
        for shape,data in (((2,2),[1,2,3,4]),((2,1),[1,2])):
            with self.subTest(shape=shape):
                value=decode_typed({'type':('ARRAY',shape,('INTEGER',)),'value':data})[1]
                self.assertEqual(value.values,data)

    def test_legacy_flat_named_singleton_matrix_state_remains_readable(self):
        from karel2py.storage import decode_typed
        spec=('ARRAY',(2,1),('ARRAY',1,('INTEGER',),'ROW'))
        value=decode_typed({'type':spec,'value':[[7],[9]]})[1]
        self.assertEqual(value.snapshot(),[[[7]],[[9]]])

    def test_ragged_matrix_state_is_rejected(self):
        from karel2py.storage import decode_typed
        for data in ([[1,2],[3]],[[1,2,3],[4,5,6]],[1,2,3],[[1,2],3]):
            with self.subTest(data=data),self.assertRaises((ValueError,rt.KarelRuntimeError)):
                decode_typed({'type':('ARRAY',(2,2),('INTEGER',)),'value':data})

    def test_restored_position_keeps_protected_orientation_children(self):
        from karel2py.storage import typed_value,decode_typed
        value=rt.Structure(('POSITION',));value.values['NORMAL'].values['X']=1.
        other=decode_typed(json.loads(json.dumps(typed_value(value))))[1]
        self.assertTrue(other.values['NORMAL'].read_only)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'read.only|protected'):
            rt.field_reference(other.values['NORMAL'],'X').set(9.)
        self.assertEqual(other.values['NORMAL'].values['X'],1.)

    def test_missing_container_cannot_hide_resource_schema(self):
        for kind in ('FILE','PATH','QUEUE_TYPE'):
            spec=('STRUCTURE','RESOURCE_BOX',(('HANDLE',(kind,)),))
            with self.subTest(kind=kind),self.assertRaisesRegex(rt.KarelRuntimeError,'without resources'):
                rt.variable_value(spec,rt.UNINITIALIZED)

    def test_empty_string_literal_remains_supported(self):
        state=run("text='old' "+transfer('SET_VAR','TEXT',"''"),decl=BASE+' text: STRING[8]')
        self.assertEqual((state['TEXT'],state['S']),('',0))

    def test_bare_function_value_is_still_evaluated_once(self):
        routines='ROUTINE make: INTEGER BEGIN n=n+1 RETURN 7 END make'
        state=run('n=0 '+transfer('SET_VAR','B','make'),decl=BASE+' b: INTEGER',routines=routines)
        self.assertEqual((state['N'],state['B']),(1,7))

    def test_partial_record_array_element_counts_as_one_transfer_cell(self):
        state=run('a[1].id=7 b[2].id=9 '+transfer(),decl=BASE+' a: ARRAY[1] OF box_t b: ARRAY[2] OF box_t',prefix='TYPE box_t=STRUCTURE id: INTEGER label: STRING[4] ENDSTRUCTURE')
        self.assertEqual((state['B'],state['S']),([{'ID':7,'LABEL':MISSING},{'ID':9,'LABEL':MISSING}],12311))

    def test_foreign_root_and_path_nodes(self):
        ctx=rt.ExecutionContext();p,_=compile_program('APPEND_NODE(p,s) p[1].items[1]=7',decl='p: PATH NODEDATA=node_t s: INTEGER',prefix='TYPE node_t=STRUCTURE items: ARRAY[2] OF INTEGER ENDSTRUCTURE',context=ctx)
        p.run();ctx.variables.programs['LIB']=p._state
        state=run("GET_VAR(e,'LIB','P[1].ITEMS',b,s)",decl=BASE+' b: ARRAY[3] OF INTEGER',context=ctx)
        self.assertEqual((state['B'],state['S']),([7,MISSING,MISSING],12311))

    def test_linked_routine_generic_source(self):
        main=source('MAIN','a[1]=7 put(a)',decl='a: ARRAY[1] OF INTEGER',routines='ROUTINE put(values: ARRAY OF INTEGER) FROM LIB')
        lib=source('LIB','',decl=BASE+' b: ARRAY[2] OF INTEGER',routines="ROUTINE put(values: ARRAY OF INTEGER) BEGIN SET_VAR(e,'','B',values,s) END put")
        state=translate_project({'main':main,'lib':lib}).instantiate().run('MAIN')
        self.assertEqual(state['LIB']['values']['B'],[7,MISSING])

    def test_partial_results_survive_context_json(self):
        program,result=compile_program('a[1]=7 '+transfer('SET_VAR','B','a'),decl=BASE+' a: ARRAY[2] OF INTEGER b: ARRAY[3] OF INTEGER')
        expected=program.run();ctx=rt.ExecutionContext.from_config(json.loads(json.dumps(program._state.execution.to_config())))
        namespace={'__name__':'restored_transfer'};exec(result.python_source,namespace)
        self.assertEqual(namespace['Program'](context=ctx).snapshot(),expected)

    def test_records_and_policy_do_not_expose_values(self):
        program,result=compile_program(transfer('SET_VAR','B','a'),decl=BASE+' a,b: INTEGER');program.run()
        self.assertEqual(program.service_requests,({'operation':'SET_VAR','line':6,'outcome':'completed'},))
        self.assertFalse(result.report['variable_transfer_policy']['controller_validated'])

    def test_cache_entry_is_stable_across_successful_calls(self):
        state=run('a=7 '+transfer('GET_VAR','A','b')+' old=e '+transfer('SET_VAR','A','9'),decl=BASE+' a,b,old: INTEGER')
        self.assertEqual((state['E'],state['OLD'],state['A']),(1,1,9))

    def test_failed_type_check_does_not_publish_a_cache_entry(self):
        program,_=compile_program('e=9 '+transfer('GET_VAR','A','b'),decl=BASE+' a: INTEGER b: BOOLEAN');program.run()
        self.assertEqual((program.snapshot()['E'],program._state.execution.entries),(9,{}))


if __name__=='__main__': unittest.main()
