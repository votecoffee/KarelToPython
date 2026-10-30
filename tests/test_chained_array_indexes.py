"""Authored complete ARRAY chains reuse comma indexing and capture contracts."""
import json
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


U={'uninitialized':True}
B={'unknown_byte':True}
TYPES='''TYPE row_t=ARRAY[3] OF INTEGER plane_t=ARRAY[2] OF row_t
leaf_t=STRUCTURE value:INTEGER label:STRING[4] ENDSTRUCTURE
box_t=STRUCTURE rows:ARRAY[2,2] OF leaf_t ENDSTRUCTURE'''
DECL='a,b:ARRAY[2,3] OF INTEGER cube:ARRAY[2,2,2] OF INTEGER named:plane_t row:row_t items:ARRAY[2,2] OF leaf_t box:box_t words:ARRAY[2,2] OF STRING[4] bytes:ARRAY[2,2] OF BYTE shorts:ARRAY[2,2] OF SHORT i,j,k,index_value,calls,total,result,visits,status:INTEGER flag:BOOLEAN text:STRING[16]'


def build(body,*,labelled=False,types=TYPES,decl=DECL,routines='',cooperative=False,shapes=None,**options):
    r=translate('PROGRAM MAIN '+types+' VAR '+decl+' '+routines+' BEGIN '+('unused:: ' if labelled else '')+body+' END MAIN',cooperative=cooperative,array_shapes=shapes)
    ns={'__name__':'chained_index_test'};exec(r.python_source,ns)
    return ns['Program'](**options),r


def execute(body,**options):return build(body,**options)[0].run()


class ChainedArrayStorageTests(unittest.TestCase):
    def parity(self,body,**options):
        states=[execute(body,labelled=labelled,**options) for labelled in (False,True)]
        self.assertEqual(states[0],states[1]);return states[0]

    def test_flat_matrix_read_and_write_match_comma_indexes(self):
        v=self.parity('a[1][2]=42 result=a[1,2] a[2,3]=7 total=a[2][3]')
        self.assertEqual((v['RESULT'],v['TOTAL']),(42,7))

    def test_three_dimension_complete_chain(self):self.assertEqual(self.parity('cube[2][1][2]=42 result=cube[2,1,2]')['RESULT'],42)

    def test_mixed_bracket_groups(self):
        v=self.parity('cube[1,2][2]=20 cube[2][1,2]=22 result=cube[1][2][2]+cube[2,1,2]')
        self.assertEqual(v['RESULT'],42)

    def test_grouped_intermediate_flat_indexes_do_not_create_row_views(self):
        v=self.parity('a[1][2]=42 result=((a[1]))[2] total=((a)[1])[2]')
        self.assertEqual(v['RESULT'],42)

    def test_named_components_share_existing_comma_path(self):self.assertEqual(self.parity('named[2][3]=42 result=named[2,3]')['RESULT'],42)

    def test_named_subarray_boundary_is_preserved(self):
        types='TYPE row_t=ARRAY[2] OF INTEGER plane_t=ARRAY[2] OF row_t cube_t=ARRAY[2] OF plane_t'
        v=self.parity('cube[1][2][1]=42 row=cube[1][2] row[2]=99 result=cube[1,2,1]',types=types,decl='cube:cube_t row:row_t result:INTEGER')
        self.assertEqual((v['ROW'],v['RESULT'],v['CUBE'][0][1]),([42,99],42,[42,U]))

    def test_mixed_outer_rank_and_named_terminal_array(self):
        types='TYPE row_t=ARRAY[2] OF INTEGER'
        v=self.parity('values[2][1,2]=42 result=values[2,1][2]',types=types,decl='values:ARRAY[2,2] OF row_t result:INTEGER')
        self.assertEqual(v['RESULT'],42)

    def test_named_outer_and_flat_named_inner_rank(self):
        types='TYPE plane_t=ARRAY[2,2] OF INTEGER'
        v=self.parity('values[2][1][2]=42 result=values[2][1,2]',types=types,decl='values:ARRAY[2] OF plane_t result:INTEGER')
        self.assertEqual(v['RESULT'],42)

    def test_record_fields_follow_complete_chain(self):
        v=self.parity("items[1][2].value=42 items[1][2].label='abcdef' result=items[1,2].value text=items[1][2].label")
        self.assertEqual((v['RESULT'],v['TEXT']),(42,'abcd'))

    def test_record_field_receivers_before_chain(self):self.assertEqual(self.parity('box.rows[2][1].value=42 result=box.rows[2,1].value')['RESULT'],42)

    def test_string_capacity_is_kept_on_chained_storage(self):self.assertEqual(self.parity("words[1][2]='abcdef' text=words[1][2]")['TEXT'],'abcd')

    def test_partial_byte_and_short_elements_keep_ordinary_markers(self):
        v=self.parity('bytes[1][1]=7 shorts[2][2]=32767 flag=UNINIT(shorts[2][2])')
        self.assertEqual((v['BYTES'][0],v['SHORTS'][1],v['FLAG']),([7,B],[U,U],True))

    def test_whole_array_copy_after_chained_writes_is_independent(self):
        v=self.parity('a[1][2]=7 b=a b[1][2]=42')
        self.assertEqual((v['A'][0][1],v['B'][0][1]),(7,42))

    def test_function_result_base_is_evaluated_once(self):
        routine='ROUTINE make:ARRAY[2,3] OF INTEGER BEGIN calls=calls+1 RETURN a END make'
        v=self.parity('calls=0 a[2,3]=42 result=make()[2][3]',routines=routine)
        self.assertEqual((v['RESULT'],v['CALLS']),(42,1))

    def test_grouped_function_result_chain(self):
        routine='ROUTINE make:ARRAY[2,3] OF INTEGER BEGIN RETURN a END make'
        self.assertEqual(self.parity('a[2,3]=42 result=((make())[2])[3]',routines=routine)['RESULT'],42)

    def test_returned_record_chain_and_nested_field(self):
        routine='ROUTINE make:box_t BEGIN RETURN box END make'
        self.assertEqual(self.parity('box.rows[1,2].value=42 result=make().rows[1][2].value',routines=routine)['RESULT'],42)

    def test_inherited_string_result_keeps_concrete_capacity(self):
        routine='ROUTINE make:ARRAY[2,2] OF STRING BEGIN RETURN words END make'
        v=self.parity("words[1][2]='abcdef' text=make()[1][2]",routines=routine)
        self.assertEqual(v['TEXT'],'abcd')

    def test_variable_global_shape_specialization_is_retained(self):
        v=self.parity('values[2][3]=42 result=values[2,3]',types='',decl='values:ARRAY[*,3] OF INTEGER result:INTEGER',shapes={'VALUES':[2,3]})
        self.assertEqual(v['RESULT'],42)


class ChainedArrayEffectsAndReferencesTests(unittest.TestCase):
    def test_indexes_evaluate_once_left_to_right(self):
        routines='ROUTINE first:INTEGER BEGIN calls=calls*10+1 RETURN 1 END first ROUTINE second:INTEGER BEGIN calls=calls*10+2 RETURN 2 END second'
        v=execute('calls=0 a[first()][second()]=42 result=calls',routines=routines)
        self.assertEqual(v['RESULT'],12)

    def test_function_base_precedes_all_index_effects(self):
        routines='ROUTINE make:ARRAY[2,3] OF INTEGER BEGIN calls=calls*10+1 RETURN a END make ROUTINE first:INTEGER BEGIN calls=calls*10+2 RETURN 1 END first ROUTINE second:INTEGER BEGIN calls=calls*10+3 RETURN 2 END second'
        v=execute('calls=0 a[1,2]=42 result=make()[first()][second()]',routines=routines)
        self.assertEqual((v['RESULT'],v['CALLS']),(42,123))

    def test_assignment_rhs_precedes_target_indexes(self):
        routines='ROUTINE rhs:INTEGER BEGIN calls=calls*10+3 RETURN 42 END rhs ROUTINE first:INTEGER BEGIN calls=calls*10+1 RETURN 1 END first ROUTINE second:INTEGER BEGIN calls=calls*10+2 RETURN 2 END second'
        v=execute('calls=0 a[first()][second()]=rhs()',routines=routines)
        self.assertEqual((v['CALLS'],v['A'][0][1]),(312,42))

    def test_returned_base_is_detached_before_index_function_mutates_source(self):
        routines='ROUTINE make:ARRAY[2,3] OF INTEGER BEGIN RETURN a END make ROUTINE pick:INTEGER BEGIN a[1,2]=99 RETURN 1 END pick'
        v=execute('a[1,2]=42 result=make()[pick()][2]',routines=routines)
        self.assertEqual((v['RESULT'],v['A'][0][1]),(42,99))

    def test_all_indexes_evaluate_before_combined_bounds_check_like_comma(self):
        p,_=build('calls=0 result=a[0][pick()]',routines='ROUTINE pick:INTEGER BEGIN calls=calls+1 RETURN 2 END pick')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['CALLS'],p.snapshot()['RESULT']),(1,U))

    def test_writable_scalar_formal_receives_selected_chain_reference(self):
        v=execute('edit(a[1][2])',routines='ROUTINE edit(p:INTEGER) BEGIN p=42 END edit')
        self.assertEqual(v['A'][0][1],42)

    def test_grouped_argument_is_detached_value(self):
        v=execute('a[1][2]=7 edit((a[1][2]))',routines='ROUTINE edit(p:INTEGER) BEGIN p=42 END edit')
        self.assertEqual(v['A'][0][1],7)

    def test_reference_into_function_result_changes_only_its_temporary(self):
        routines='ROUTINE make:ARRAY[2,3] OF INTEGER BEGIN RETURN a END make ROUTINE edit(p:INTEGER) BEGIN p=42 result=p END edit'
        v=execute('a[1][2]=7 edit(make()[1][2])',routines=routines)
        self.assertEqual((v['A'][0][1],v['RESULT']),(7,42))

    def test_named_subarray_actual_keeps_exact_reference_type(self):
        types='TYPE row_t=ARRAY[2] OF INTEGER plane_t=ARRAY[2] OF row_t cube_t=ARRAY[2] OF plane_t'
        v=execute('edit(cube[1][2])',types=types,decl='cube:cube_t',routines='ROUTINE edit(p:row_t) BEGIN p[2]=42 END edit')
        self.assertEqual(v['CUBE'][0][1][1],42)

    def test_read_targets_capture_chained_storage(self):
        self.assertEqual(execute('READ(a[1][2],a[2][3])',read=lambda request:[20,22])['A'],[[U,20,U],[U,U,22]])

    def test_conversion_output_uses_chained_leaf(self):self.assertEqual(execute("CNV_STR_INT('42',a[1][2])")['A'][0][1],42)

    def test_byname_entry_output_accepts_complete_chain(self):
        v=execute("edit(BYNAME('MAIN','A[1,2]',b[1][1]))",routines='ROUTINE edit(p:INTEGER) BEGIN p=42 END edit')
        self.assertEqual(v['A'][0][1],42)
        self.assertIsInstance(v['B'][0][0],int)

    def test_using_selector_captures_chained_record_once(self):
        v=execute('index_value=1 USING items[index_value][2] DO value=42 index_value=2 value=value+1 ENDUSING')
        self.assertEqual((v['ITEMS'][0][1]['VALUE'],v['ITEMS'][1][1]['VALUE']),(43,U))

    def test_computed_using_selector_chain_owns_private_record(self):
        routine='ROUTINE make:ARRAY[2,2] OF leaf_t BEGIN RETURN items END make'
        v=execute('items[1][2].value=7 USING make()[1][2] DO value=42 result=value ENDUSING',routines=routine)
        self.assertEqual((v['RESULT'],v['ITEMS'][0][1]['VALUE']),(42,7))

    def test_integer_counter_chain_keeps_original_leaf_when_index_changes(self):
        v=execute('index_value=1 total=0 a[2,2]=99 FOR a[index_value][2]=1 TO 3 DO index_value=2 total=total+a[1][2] ENDFOR')
        self.assertEqual((v['TOTAL'],v['A'][0][1],v['A'][1][1]),(6,U,99))

    def test_narrow_counter_chain_retains_type_specific_cleanup(self):
        v=execute('total=0 FOR bytes[1][2]=254 TO 255 DO total=total+bytes[1][2] ENDFOR')
        self.assertEqual((v['TOTAL'],v['BYTES'][0][1]),(509,B))

    def test_private_using_chain_counter_root_stays_protected(self):
        routine='ROUTINE make:box_t BEGIN RETURN box END make'
        v=execute('total=0 USING make() DO FOR rows[1][2].value=1 TO 3 DO total=total+rows[1][2].value ENDFOR flag=UNINIT(rows[1][2].value) ENDUSING',routines=routine)
        self.assertEqual((v['TOTAL'],v['FLAG'],v['BOX']['ROWS'][0][1]['VALUE']),(6,True,U))


class ChainedArrayRejectionTests(unittest.TestCase):
    def reject(self,body,code='E_ARRAY_RANK',**options):
        for labelled in (False,True):
            with self.assertRaises(TranslationError) as caught:build(body,labelled=labelled,**options)
            self.assertEqual(caught.exception.code,code,str(caught.exception))

    def test_incomplete_flat_chain_is_not_a_row_view(self):
        for expression in ('a[1]','(a[1])','cube[1][2]','((cube[1]))[2]'):
            self.reject('result='+expression)

    def test_incomplete_flat_named_inner_is_not_a_row_view(self):self.reject('result=values[1][2]',types='TYPE plane_t=ARRAY[2,2] OF INTEGER',decl='values:ARRAY[2] OF plane_t result:INTEGER')

    def test_excess_subscripts_are_rejected_after_flattening(self):
        for expression in ('a[1][2][3]','a[1,2][1]','cube[1][1][1][1]'):
            self.reject('result='+expression)

    def test_nonarray_receiver_and_record_reindex_are_rejected(self):
        self.reject('result=items[1][2][1].value')
        self.reject('result=result[1][2]','E_TYPE')

    def test_wrong_index_types_stay_rejected(self):
        for expression in ('a[TRUE][1]','a[1][1.0]',"a[1]['2']"):
            self.reject('result='+expression,'E_TYPE')

    def test_named_subarray_copy_retains_receiver_identity(self):
        types='TYPE row_t=ARRAY[2]OF INTEGER plane_t=ARRAY[2]OF row_t cube_t=ARRAY[2]OF plane_t alien_t=ARRAY[2]OF INTEGER'
        p,_=build('cube[1,2,1]=7 alien=cube[1][2]',types=types,decl='cube:cube_t alien:alien_t')
        self.assertEqual(p.run()['ALIEN'],[7,U]);self.assertEqual(p._state.raw('ALIEN').spec[3],'ALIEN_T')

    def test_counter_root_writes_cannot_hide_behind_chain(self):self.reject('FOR a[1][2]=1 TO 2 DO a[2][3]=99 ENDFOR','E_FOR_COUNTER')

    def test_counter_index_effect_still_checks_transitive_writes(self):self.reject('FOR i=1 TO 2 DO result=a[pick()][2] ENDFOR','E_FOR_COUNTER',routines='ROUTINE pick:INTEGER BEGIN i=99 RETURN 1 END pick')

    def test_writable_reference_to_active_root_is_rejected(self):self.reject('FOR a[1][2]=1 TO 2 DO edit(a[2][3]) ENDFOR','E_FOR_COUNTER',routines='ROUTINE edit(p:INTEGER) BEGIN p=99 END edit')

    def test_handler_write_to_chained_counter_root_is_rejected(self):self.reject('CONDITION[1]: WHEN EVENT[1] DO a[2][3]=99 ENDCONDITION FOR a[1][2]=1 TO 2 DO ENDFOR','E_FOR_COUNTER')

    def test_position_orientation_readonly_guard_survives_chain(self):
        self.reject('poses[1][2].normal.x=1','E_POSITION_READ_ONLY',decl=DECL+' poses:ARRAY[2,2] OF POSITION')
        self.reject('READ(poses[1][2].normal.x)','E_POSITION_READ_ONLY',decl=DECL+' poses:ARRAY[2,2] OF POSITION')

    def test_config_subfield_output_guard_survives_chain(self):self.reject("CNV_STR_INT('8',cfgs[1][2].cfg_turn_no1)",'E_CONFIG_OUTPUT',decl=DECL+' cfgs:ARRAY[2,2] OF CONFIG')

    def test_runtime_bad_index_preserves_destination(self):
        for expression in ('a[0][2]','a[1][4]','a[-1][2]'):
            p,_=build('result=7 result='+expression)
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['RESULT'],7)

    def test_runtime_unknown_leaf_is_still_a_read_error(self):
        p,_=build('result=a[1][2]')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'):p.run()

    def test_legacy_chain_restriction_is_unchanged(self):
        for body in ('result=a[1][2]','a[1][2]=42'):
            with self.assertRaises(TranslationError):legacy_translate('PROGRAM MAIN VAR a:ARRAY[2,3] OF INTEGER result:INTEGER BEGIN '+body+' END MAIN')


class ChainedArrayLifetimeAndIntegrationTests(unittest.TestCase):
    def test_pause_resume_keeps_captured_chain_counter(self):
        p,_=build('index_value=1 total=0 FOR a[index_value][2]=1 TO 2 DO total=total+a[1][2] index_value=2 IF a[1][2]=1 THEN PAUSE ENDIF ENDFOR',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        v=p.resume();self.assertEqual((v['TOTAL'],v['A'][0][1]),(3,U))

    def test_stop_clears_selected_chain_leaf(self):
        p,_=build('FOR bytes[1][2]=1 TO 2 DO PAUSE ENDFOR',cooperative=True,labelled=True)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(p.snapshot()['BYTES'][0][1],B)

    def test_goto_exit_clears_chained_counter(self):
        v=execute('FOR a[1][2]=1 TO 2 DO GOTO done ENDFOR done:: flag=UNINIT(a[1][2])')
        self.assertTrue(v['FLAG'])

    def test_pausing_index_function_is_not_replayed(self):
        routine='ROUTINE pick:INTEGER BEGIN calls=calls+1 PAUSE RETURN 1 END pick'
        p,_=build('calls=0 a[1,2]=42 result=a[pick()][2]',cooperative=True,routines=routine)
        with self.assertRaises(rt.KarelPause):p.run()
        v=p.resume();self.assertEqual((v['CALLS'],v['RESULT']),(1,42))

    def test_read_callback_failure_does_not_publish_chained_target(self):
        def fail(request):raise ValueError('authored input failure')
        p,_=build('a[1][2]=7 READ(a[1][2])',read=fail)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['A'][0][1],7)

    def test_report_records_source_and_normalized_chain_without_duplicate_calls(self):
        p,r=build('calls=0 a[pick()][2]=42',routines='ROUTINE pick:INTEGER BEGIN calls=calls+1 RETURN 1 END pick')
        self.assertEqual(p.run()['CALLS'],1)
        rows=json.loads(json.dumps(r.report))['array_index_chains']
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['source_selector'],rows[0]['normalized_selector'],rows[0]['segment_lengths']),('A[PICK()][2]','A[PICK(),2]',[1,1]))

    def test_included_chain_uses_physical_source_map(self):
        r=translate('PROGRAM MAIN VAR a:ARRAY[2,2] OF INTEGER BEGIN\n%INCLUDE body\nEND MAIN',includes={'body.kl':'a[1][2]=42'})
        self.assertTrue(any(row.get('source_file')=='body.kl' for row in r.report['source_map']))
        self.assertEqual(len(r.report['array_index_chains']),1)

    def test_linked_generic_function_and_formal_chain(self):
        sources={'main':'PROGRAM MAIN VAR a:ARRAY[2,2] OF INTEGER result:INTEGER ROUTINE edit(p:ARRAY[*,*] OF INTEGER) FROM LIB BEGIN edit(a) result=a[1][2] END MAIN',
            'lib':'PROGRAM LIB ROUTINE edit(p:ARRAY[*,*] OF INTEGER) BEGIN p[1][2]=42 END edit BEGIN END LIB'}
        instance=translate_project(sources).instantiate();self.assertEqual(instance.run('MAIN')['MAIN']['values']['RESULT'],42)

    def test_context_json_preserves_concrete_shape_and_partial_values(self):
        p,_=build('a[1][2]=42');p.run()
        context=rt.ExecutionContext.from_config(json.loads(json.dumps(p._state.execution.to_config())))
        q,_=build('result=a[1][2]',context=context)
        v=q.run();self.assertEqual((v['RESULT'],v['A'][0]),(42,[U,42,U]))


if __name__=='__main__':unittest.main()
