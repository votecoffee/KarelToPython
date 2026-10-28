"""Captured USING storage across records, effects, handlers and control flow."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate,load_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_pythonic_using import compile_program as base_program

ROOT=Path(__file__).resolve().parents[1]
ENTRY='TYPE entry_t=STRUCTURE value:INTEGER label:STRING[5] ENDSTRUCTURE'
DECL='items:ARRAY[2] OF entry_t index_value,calls,result,total:INTEGER'


def program(body,*,types=ENTRY,declarations=DECL,cooperative=False,**options):
    def translator(source,**kwargs):return translate(source,cooperative=cooperative,**kwargs)
    return base_program(body,types=types,declarations=declarations,translator=translator,**options)


def execute(body,**kwargs):return program(body,**kwargs)[0].run()


class CapturedUsingStorageTests(unittest.TestCase):
    def test_index_is_captured_before_body_changes_it(self):
        values=execute('index_value=1 USING items[index_value] DO value=20 index_value=2 value=value+22 ENDUSING')
        self.assertEqual(values['ITEMS'][0]['VALUE'],42)
        self.assertEqual(values['ITEMS'][1]['VALUE'],{'uninitialized':True})

    def test_index_function_runs_once_even_with_many_field_uses(self):
        values=execute("calls=0 USING items[next_slot()] DO value=20 label='abcdef' value=value+22 ENDUSING",
            routines='ROUTINE next_slot:INTEGER BEGIN calls=calls+1 RETURN calls END next_slot')
        self.assertEqual((values['CALLS'],values['ITEMS'][0]),(1,{'VALUE':42,'LABEL':'abcde'}))

    def test_empty_body_still_evaluates_and_checks_selector(self):
        values=execute('calls=0 USING items[next_slot()] DO ENDUSING',
            routines='ROUTINE next_slot:INTEGER BEGIN calls=calls+1 RETURN 1 END next_slot')
        self.assertEqual(values['CALLS'],1)

    def test_selector_list_evaluates_left_to_right_before_body(self):
        values=execute('calls=0 USING items[next_slot()],items[next_slot()] DO value=42 ENDUSING',
            routines='ROUTINE next_slot:INTEGER BEGIN calls=calls+1 RETURN calls END next_slot')
        self.assertEqual(values['CALLS'],2)
        self.assertEqual(values['ITEMS'][0]['VALUE'],{'uninitialized':True})
        self.assertEqual(values['ITEMS'][1]['VALUE'],42)

    def test_multi_dimension_subscripts_evaluate_once_in_order(self):
        values=execute('calls=0 USING items[row_index(),col_index()] DO value=42 ENDUSING',
            declarations=DECL.replace('ARRAY[2]','ARRAY[2,2]'),
            routines='ROUTINE row_index:INTEGER BEGIN calls=calls*10+1 RETURN 1 END row_index ROUTINE col_index:INTEGER BEGIN calls=calls*10+2 RETURN 2 END col_index')
        self.assertEqual((values['CALLS'],values['ITEMS'][0][1]['VALUE']),(12,42))

    def test_selector_list_does_not_introduce_names_for_later_indexes(self):
        types=ENTRY+' TYPE box_t=STRUCTURE index_value:INTEGER ENDSTRUCTURE'
        values=execute('index_value=2 box.index_value=1 USING box,items[index_value] DO value=42 ENDUSING',
            types=types,declarations=DECL+' box:box_t')
        self.assertEqual(values['ITEMS'][1]['VALUE'],42)

    def test_nested_selector_index_uses_enclosing_field(self):
        types=ENTRY+' TYPE box_t=STRUCTURE slot:INTEGER ENDSTRUCTURE'
        values=execute('box.slot=2 USING box DO USING items[slot] DO value=42 ENDUSING ENDUSING',
            types=types,declarations=DECL+' box:box_t')
        self.assertEqual(values['ITEMS'][1]['VALUE'],42)

    def test_grouping_and_qualified_index_storage(self):
        types=ENTRY+' TYPE box_t=STRUCTURE rows:ARRAY[2] OF entry_t ENDSTRUCTURE'
        values=execute('index_value=1 USING ((box.rows)[index_value]) DO value=42 ENDUSING',
            types=types,declarations=DECL+' box:box_t')
        self.assertEqual(values['BOX']['ROWS'][0]['VALUE'],42)

    def test_whole_array_replacement_preserves_captured_element_storage(self):
        values=execute("other[1].value=7 other[1].label='first' other[2].value=8 other[2].label='next' USING items[1] DO value=1 items=other value=value+1 ENDUSING",
            declarations=DECL+' other:ARRAY[2] OF entry_t')
        self.assertEqual(values['ITEMS'][0],{'VALUE':8,'LABEL':'first'})
        self.assertEqual(values['OTHER'][0]['VALUE'],7)

    def test_each_loop_entry_selects_fresh_storage(self):
        values=execute('index_value=1 WHILE index_value<=2 DO USING items[index_value] DO value=index_value*21 ENDUSING index_value=index_value+1 ENDWHILE')
        self.assertEqual([row['VALUE'] for row in values['ITEMS']],[21,42])

    def test_formal_array_and_effect_report_keep_original_root(self):
        p,result=program('edit(items)',routines='ROUTINE edit(rows:ARRAY[*] OF entry_t) BEGIN USING rows[2] DO value=42 ENDUSING END edit')
        self.assertEqual(p.run()['ITEMS'][1]['VALUE'],42)
        self.assertEqual(result.report['routine_effects']['EDIT']['potential_parameter_writes'],['ROWS'])

    def test_value_parameter_stays_detached(self):
        values=execute("items[1].value=1 items[1].label='first' items[2].value=2 items[2].label='next' edit((items))",
            routines='ROUTINE edit(rows:ARRAY[*] OF entry_t) BEGIN USING rows[2] DO value=42 ENDUSING END edit')
        self.assertEqual(values['ITEMS'][1]['VALUE'],2)

    def test_nested_rightmost_priority_and_outer_restoration(self):
        values=execute('USING items[1] DO value=1 USING items[2] DO value=2 ENDUSING value=value+3 ENDUSING')
        self.assertEqual([row['VALUE'] for row in values['ITEMS']],[4,2])

    def test_callee_has_its_own_lexical_scope(self):
        values=execute('USING items[1] DO value=1 edit ENDUSING',declarations=DECL+' value:INTEGER',
            routines='ROUTINE edit BEGIN value=42 END edit')
        self.assertEqual((values['ITEMS'][0]['VALUE'],values['VALUE']),(1,42))

    def test_invalid_index_fails_on_entry_even_for_empty_body(self):
        p,_=program('USING items[0] DO ENDUSING')
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_prior_selector_effects_remain_when_later_selector_fails(self):
        p,_=program('calls=0 USING items[next_slot()],items[0] DO result=99 ENDUSING',
            routines='ROUTINE next_slot:INTEGER BEGIN calls=calls+1 RETURN 1 END next_slot')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['CALLS'],1)
        self.assertEqual(p.snapshot()['RESULT'],{'uninitialized':True})

    def test_scalar_array_resource_and_joint_selectors_rejected(self):
        for spec in ('INTEGER','ARRAY[2] OF INTEGER','FILE','PATH','QUEUE_TYPE','JOINTPOS6'):
            with self.subTest(spec=spec):
                with self.assertRaises(TranslationError) as caught:program('USING item DO ENDUSING',types='',declarations='item:'+spec)
                self.assertEqual(caught.exception.code,'E_USING_TYPE')

    def test_function_results_and_computed_selectors_rejected(self):
        for selector in ('make()','(make())','(left+right)','left.value()'):
            with self.subTest(selector=selector):
                with self.assertRaises(TranslationError) as caught:program('USING '+selector+' DO ENDUSING')
                self.assertEqual(caught.exception.code,'E_USING_TARGET')

    def test_non_integer_subscript_rejected(self):
        with self.assertRaises(TranslationError) as caught:program('USING items[TRUE] DO ENDUSING')
        self.assertEqual(caught.exception.code,'E_TYPE')

    def test_path_node_structure_is_existing_storage(self):
        values=execute('APPEND_NODE(track,status) USING track[1] DO value=42 ENDUSING',
            declarations='track:PATH NODEDATA=entry_t status:INTEGER')
        self.assertEqual(values['TRACK']['nodes'][0]['VALUE'],42)


class BuiltinUsingRecordTests(unittest.TestCase):
    def test_vector_fields_can_initialize_existing_storage(self):
        values=execute('USING item DO x=20 y=22 z=x+y ENDUSING',types='',declarations='item:VECTOR')
        self.assertEqual(values['ITEM'],{'X':20.0,'Y':22.0,'Z':42.0})

    def test_builtin_record_array_elements_and_aliases(self):
        values=execute('index_value=2 USING items[index_value] DO x=42 y=0 z=0 ENDUSING',
            types='TYPE vector_t=VECTOR',declarations='items:ARRAY[2] OF vector_t index_value:INTEGER')
        self.assertEqual(values['ITEMS'][1],{'X':42.0,'Y':0.0,'Z':0.0})

    def test_xyz_expression_and_nested_config_fields(self):
        values=execute("USING pose DO x=42 y=0 z=0 w=0 p=0 r=0 USING config_data DO cfg_turn_no1=0 cfg_turn_no2=0 cfg_turn_no3=0 cfg_flip=OFF cfg_left=OFF cfg_up=OFF cfg_front=OFF ENDUSING ENDUSING",
            types='',declarations='pose:XYZWPR')
        self.assertEqual(values['POSE']['X'],42.0)
        self.assertFalse(values['POSE']['CONFIG_DATA']['CFG_FLIP'])

    def test_external_axes_are_exposed(self):
        values=execute('USING pose DO ext1=1 ext2=2 ext3=ext1+ext2 ENDUSING',types='',declarations='pose:XYZWPREXT')
        self.assertEqual([values['POSE'][name] for name in ('EXT1','EXT2','EXT3')],[1.0,2.0,3.0])

    def test_position_location_is_writable(self):
        values=execute('USING pose DO USING location DO x=42 y=0 z=0 ENDUSING ENDUSING',types='',declarations='pose:POSITION')
        self.assertEqual(values['POSE']['LOCATION'],{'X':42.0,'Y':0.0,'Z':0.0})

    def test_position_orientation_protection_survives_capture_and_grouping(self):
        for field in ('normal','orient','approach'):
            for body in (f'USING (pose.{field}) DO x=1 ENDUSING',f'USING pose DO USING {field} DO x=1 ENDUSING ENDUSING'):
                with self.subTest(body=body):
                    with self.assertRaises(TranslationError) as caught:program(body,types='',declarations='pose:POSITION')
                    self.assertEqual(caught.exception.code,'E_POSITION_READ_ONLY')

    def test_protected_component_cannot_escape_as_writable_argument(self):
        with self.assertRaises(TranslationError) as caught:
            program('USING (pose.normal) DO change(x) ENDUSING',types='',declarations='pose:POSITION',
                routines='ROUTINE change(p:REAL) BEGIN p=1 END change')
        self.assertEqual(caught.exception.code,'E_POSITION_READ_ONLY_ARG')

    def test_grouped_protected_field_argument_is_still_a_private_value(self):
        p,_=program('USING (pose.normal) DO change((x)) ENDUSING',types='',declarations='pose:POSITION',
            routines='ROUTINE change(value:REAL) BEGIN value=42 END change')
        # Synthetic host seed only: grouped values copy initialized protected data.
        p._state.values['POSE'].values['NORMAL'].values['X']=7.0
        self.assertEqual(p.run()['POSE']['NORMAL']['X'],7.0)

    def test_config_bounds_still_reject_without_storing(self):
        p,_=program('USING cfg DO cfg_turn_no1=1 cfg_turn_no1=8 ENDUSING',types='',declarations='cfg:CONFIG')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'-8'):p.run()
        self.assertEqual(p.snapshot()['CFG']['CFG_TURN_NO1'],1)

    def test_config_fields_cannot_be_unbounded_conversion_outputs(self):
        with self.assertRaises(TranslationError) as caught:
            program("USING cfg DO CNV_STR_INT('8',cfg_turn_no1) ENDUSING",types='',declarations='cfg:CONFIG status:INTEGER')
        self.assertEqual(caught.exception.code,'E_CONFIG_OUTPUT')

    def test_captured_record_survives_whole_copy(self):
        values=execute('other=VEC(1,2,3) USING item DO x=0 item=other x=x+41 ENDUSING',types='',declarations='item,other:VECTOR')
        self.assertEqual(values['ITEM'],{'X':42.0,'Y':2.0,'Z':3.0})


class UsingIntegrationTests(unittest.TestCase):
    def test_numeric_register_outputs_use_captured_fields(self):
        types='TYPE entry_t=STRUCTURE flag:BOOLEAN value:INTEGER real_value:REAL status:INTEGER ENDSTRUCTURE'
        values=execute('USING items[1] DO GET_REG(1,flag,value,real_value,status) ENDUSING',types=types,
            declarations='items:ARRAY[1] OF entry_t',registers=rt.NumericRegisters(1,{1:42}))
        self.assertEqual(values['ITEMS'][0],{'FLAG':False,'VALUE':42,'REAL_VALUE':{'uninitialized':True},'STATUS':0})

    def test_string_conversion_outputs_use_captured_fields(self):
        values=execute("USING items[2] DO CNV_STR_INT('42',value) ENDUSING",declarations=DECL+' status:INTEGER')
        self.assertEqual(values['ITEMS'][1]['VALUE'],42)

    def test_config_conversion_output_uses_captured_field(self):
        types='TYPE entry_t=STRUCTURE cfg:CONFIG status:INTEGER ENDSTRUCTURE'
        values=execute("USING items[1] DO CNV_STR_CONF('N',cfg,status) ENDUSING",types=types,declarations='items:ARRAY[1] OF entry_t')
        self.assertEqual(values['ITEMS'][0]['STATUS'],0)
        self.assertFalse(values['ITEMS'][0]['CFG']['CFG_FLIP'])

    def test_read_targets_use_captured_fields(self):
        values=execute('USING items[2] DO READ(value) ENDUSING',read=lambda request:[42])
        self.assertEqual(values['ITEMS'][1]['VALUE'],42)

    def test_index_function_effects_cannot_write_active_counter(self):
        with self.assertRaises(TranslationError) as caught:
            program('FOR index_value=1 TO 2 DO USING items[next_slot()] DO value=42 ENDUSING ENDFOR',
                routines='ROUTINE next_slot:INTEGER BEGIN index_value=2 RETURN 1 END next_slot')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_integer_field_for_counter_uses_captured_selector(self):
        values=execute('index_value=1 USING items[index_value] DO FOR value=1 TO 2 DO index_value=2 ENDFOR ENDUSING')
        self.assertEqual(values['ITEMS'][0]['VALUE'],{'uninitialized':True})
        self.assertEqual(values['INDEX_VALUE'],2)

    def test_handlers_freeze_each_entry_reference(self):
        body='index_value=1 WHILE index_value<=2 DO USING items[index_value] DO value=0 IF index_value=1 THEN CONDITION[1]: WHEN EVENT[1] DO value=42 ENDCONDITION ELSE CONDITION[2]: WHEN EVENT[2] DO value=42 ENDCONDITION ENDIF ENDUSING index_value=index_value+1 ENDWHILE ENABLE CONDITION[1] ENABLE CONDITION[2] SIGNAL EVENT[1] result=items[1].value total=items[2].value SIGNAL EVENT[2]'
        values=execute(body)
        self.assertEqual((values['RESULT'],values['TOTAL']),(42,0))
        self.assertEqual([row['VALUE'] for row in values['ITEMS']],[42,42])

    def test_handler_nested_using_does_not_capture_undefined_inner_reference(self):
        values=execute('USING items[1] DO value=1 CONDITION[1]: WHEN EVENT[1] DO USING items[2] DO value=42 ENDUSING ENDCONDITION ENDUSING ENABLE CONDITION[1] SIGNAL EVENT[1]')
        self.assertEqual([row['VALUE'] for row in values['ITEMS']],[1,42])

    def test_handler_inner_selector_keeps_enclosing_capture(self):
        types=ENTRY+' TYPE box_t=STRUCTURE child:entry_t ENDSTRUCTURE'
        values=execute('index_value=1 USING boxes[index_value] DO CONDITION[1]: WHEN EVENT[1] DO USING child DO value=42 ENDUSING ENDCONDITION ENDUSING index_value=2 ENABLE CONDITION[1] SIGNAL EVENT[1]',
            types=types,declarations=DECL+' boxes:ARRAY[2] OF box_t')
        self.assertEqual(values['BOXES'][0]['CHILD']['VALUE'],42)
        self.assertEqual(values['BOXES'][1]['CHILD']['VALUE'],{'uninitialized':True})

    def test_deferred_predicate_retains_selected_record(self):
        values=execute('index_value=1 USING items[index_value] DO value=0 CONDITION[1]: WHEN value=42 DO total=7 ENDCONDITION ENDUSING ENABLE CONDITION[1] index_value=2 items[1].value=42 result=1')
        self.assertEqual(values['TOTAL'],7)


class UsingControlFlowAndReportTests(unittest.TestCase):
    def test_label_dispatcher_captures_once_before_body_label(self):
        values=execute('calls=0 USING items[next_slot()] DO value=0 again:: value=value+1 IF value<3 THEN GOTO again ENDIF ENDUSING',
            routines='ROUTINE next_slot:INTEGER BEGIN calls=calls+1 RETURN 1 END next_slot')
        self.assertEqual((values['CALLS'],values['ITEMS'][0]['VALUE']),(1,3))

    def test_label_dispatcher_reenters_using(self):
        values=execute('index_value=1 again:: USING items[index_value] DO value=index_value ENDUSING index_value=index_value+1 IF index_value<=2 THEN GOTO again ENDIF')
        self.assertEqual([row['VALUE'] for row in values['ITEMS']],[1,2])

    def test_jump_out_restores_outer_alias(self):
        values=execute('USING items[1] DO value=1 USING items[2] DO value=2 GOTO done ENDUSING done:: value=value+3 ENDUSING')
        self.assertEqual([row['VALUE'] for row in values['ITEMS']],[4,2])

    def test_jump_into_capture_scope_remains_blocked(self):
        with self.assertRaises(TranslationError) as caught:program('GOTO inside USING items[1] DO inside:: value=42 ENDUSING')
        self.assertEqual(caught.exception.code,'E_GOTO_ENTRY')

    def test_return_releases_routine_frame_and_keeps_prior_writes(self):
        p,_=program('result=edit()',routines='ROUTINE edit:INTEGER BEGIN USING items[1] DO value=42 RETURN value ENDUSING RETURN 0 END edit')
        self.assertEqual(p.run()['RESULT'],42)
        self.assertEqual((p._state.call_depth,p._state.local_frames),(0,[]))

    def test_abort_keeps_prior_writes_and_unwinds(self):
        p,_=program('edit',routines='ROUTINE edit BEGIN USING items[1] DO value=42 ABORT ENDUSING END edit')
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(p.snapshot()['ITEMS'][0]['VALUE'],42)
        self.assertEqual((p._state.call_depth,p._state.local_frames),(0,[]))

    def test_pause_and_resume_keep_the_selected_element(self):
        p,_=program('index_value=1 USING items[index_value] DO value=20 PAUSE value=value+22 ENDUSING',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.task_state,'paused')
        p._state.reference('INDEX_VALUE').set(2)
        p.resume()
        self.assertEqual(p.snapshot()['ITEMS'][0]['VALUE'],42)
        self.assertEqual(p.snapshot()['ITEMS'][1]['VALUE'],{'uninitialized':True})

    def test_record_report_is_serializable_and_describes_capture(self):
        _,result=program('USING (items[index_value]) DO value=42 ENDUSING')
        row=json.loads(json.dumps(result.report))['using_scopes'][0]
        self.assertEqual(row['source_selectors'],['(ITEMS[INDEX_VALUE])'])
        self.assertTrue(row['capture_once'])
        self.assertEqual(row['selector_types'][0][0],'STRUCTURE')

    def test_included_selector_has_source_mapping(self):
        result=translate('PROGRAM T TYPE entry_t=STRUCTURE value:INTEGER ENDSTRUCTURE VAR items:ARRAY[2] OF entry_t BEGIN\n%INCLUDE body\nEND T',
            includes={'body.kl':'USING items[1] DO value=42 ENDUSING'})
        self.assertTrue(any(row.get('source_file')=='body.kl' for row in result.report['source_map']))

    def test_cli_can_translate_indexed_using(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'input.kl';target=Path(folder)/'output.py'
            source.write_text('PROGRAM T TYPE entry_t=STRUCTURE value:INTEGER ENDSTRUCTURE VAR items:ARRAY[2] OF entry_t BEGIN USING items[2] DO value=42 ENDUSING END T')
            result=subprocess.run([sys.executable,'-X','utf8','-m','karel2py',str(source),'-o',str(target)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            namespace={'__name__':'cli_test'};exec(target.read_text(),namespace)
            self.assertEqual(namespace['Program']().run()['ITEMS'][1]['VALUE'],42)
