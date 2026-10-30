"""Authored computed record captures, provenance, effects and lifetime boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate, translate_project, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


ROOT=Path(__file__).resolve().parents[1]
U={'uninitialized':True}
B={'unknown_byte':True}
TYPES='''TYPE row_t=STRUCTURE value:INTEGER label:STRING[4] ENDSTRUCTURE
box_t=STRUCTURE child:row_t rows:ARRAY[2] OF row_t slot:INTEGER ENDSTRUCTURE'''
DECL='source,other:row_t box:box_t rows:ARRAY[2] OF row_t i,slot,calls,result,total,status:INTEGER flag:BOOLEAN number:REAL text:STRING[8]'
MAKE='ROUTINE make:row_t BEGIN calls=calls+1 RETURN source END make'


def build(body,*,types=TYPES,decl=DECL,routines=MAKE,cooperative=False,translator=translate,**options):
    result=translator(f'PROGRAM MAIN {types} VAR {decl} {routines} BEGIN {body} END MAIN',**({'cooperative':cooperative} if translator is translate else {}))
    namespace={'__name__':'computed_using_test'};exec(result.python_source,namespace)
    return namespace['Program'](**options),result


def execute(body,**options):return build(body,**options)[0].run()


class ComputedUsingValueTests(unittest.TestCase):
    def test_constructor_exposes_independent_mutable_fields(self):
        values=execute('USING VEC(1,2,3) DO x=x+41 number=x+y+z ENDUSING')
        self.assertEqual(values['NUMBER'],47.)
        self.assertFalse(any(name.startswith('_USING') for name in values))

    def test_function_result_never_copies_back_to_global_source(self):
        values=execute('calls=0 source.value=7 USING make() DO value=42 result=value ENDUSING')
        self.assertEqual((values['CALLS'],values['RESULT'],values['SOURCE']),(1,42,{'VALUE':7,'LABEL':U}))

    def test_function_parameter_result_stays_detached(self):
        routine='ROUTINE copy(p:row_t):row_t BEGIN RETURN p END copy'
        values=execute('source.value=7 USING copy(source) DO value=42 result=value ENDUSING',routines=routine)
        self.assertEqual((values['SOURCE']['VALUE'],values['RESULT']),(7,42))

    def test_bare_zero_parameter_function_selector(self):
        p,r=build('calls=0 USING make DO value=42 result=value ENDUSING')
        self.assertEqual((p.run()['RESULT'],p.snapshot()['CALLS']),(42,1))
        self.assertEqual([row['name'] for row in r.report['bare_function_calls']],['MAKE'])

    def test_grouped_function_selector_remains_a_value_copy(self):
        values=execute('calls=0 source.value=7 USING ((make)) DO value=42 ENDUSING')
        self.assertEqual((values['SOURCE']['VALUE'],values['CALLS']),(7,1))

    def test_nested_record_field_of_function_result(self):
        routine='ROUTINE make_box:box_t BEGIN RETURN box END make_box'
        values=execute('box.child.value=7 USING make_box().child DO value=42 result=value ENDUSING',routines=routine)
        self.assertEqual((values['BOX']['CHILD']['VALUE'],values['RESULT']),(7,42))

    def test_record_element_of_array_function_result(self):
        routine='ROUTINE make_rows:ARRAY OF row_t BEGIN RETURN rows END make_rows'
        values=execute('rows[2].value=7 USING make_rows()[2] DO value=42 result=value ENDUSING',routines=routine)
        self.assertEqual((values['ROWS'][1]['VALUE'],values['RESULT']),(7,42))

    def test_nested_indexed_record_selection_of_function_result(self):
        routine='ROUTINE make_box:box_t BEGIN RETURN box END make_box'
        values=execute('box.rows[2].value=7 USING (make_box().rows)[2] DO value=42 result=value ENDUSING',routines=routine)
        self.assertEqual((values['BOX']['ROWS'][1]['VALUE'],values['RESULT']),(7,42))

    def test_vector_operator_result_can_be_a_selector(self):
        values=execute('USING (VEC(1,2,3)+VEC(4,5,6))*2 DO number=x+y+z x=99 ENDUSING')
        self.assertEqual(values['NUMBER'],42.)

    def test_unary_vector_and_inverse_results(self):
        values=execute('USING -INV(VEC(1,2,3)) DO number=x+y+z ENDUSING')
        self.assertEqual(values['NUMBER'],6.)

    def test_composed_geometry_result_remains_independent(self):
        values=execute("CNV_STR_CONF('N',cfg,status) pose=POS(1,2,3,0,0,0,cfg) USING VEC(10,20,30):pose DO x=99 number=y+z ENDUSING",
            decl=DECL+' cfg:CONFIG pose:XYZWPR')
        self.assertEqual((values['POSE']['X'],values['NUMBER']),(1.,55.))

    def test_constructor_nested_config_selector(self):
        values=execute("CNV_STR_CONF('N',cfg,status) USING POS(1,2,3,0,0,0,cfg).config_data DO cfg_turn_no1=7 result=cfg_turn_no1 ENDUSING",
            decl=DECL+' cfg:CONFIG')
        self.assertEqual((values['RESULT'],values['CFG']['CFG_TURN_NO1']),(7,0))

    def test_partial_structure_retains_missing_fields_until_written(self):
        values=execute("calls=0 source.value=7 USING make() DO flag=UNINIT(label) label='abcdef' text=label value=value+1 result=value ENDUSING")
        self.assertEqual((values['FLAG'],values['TEXT'],values['RESULT'],values['SOURCE']),(True,'abcd',8,{'VALUE':7,'LABEL':U}))

    def test_partial_vector_function_result_accepts_known_component(self):
        routine='ROUTINE make_vector:VECTOR BEGIN RETURN vec END make_vector'
        values=execute('vec.x=7 USING make_vector() DO flag=UNINIT(y) y=2 number=x+y ENDUSING',routines=routine,decl=DECL+' vec:VECTOR')
        self.assertEqual((values['FLAG'],values['NUMBER'],values['VEC']),(True,9.,{'X':7.,'Y':U,'Z':U}))

    def test_nested_byte_and_short_missing_markers_survive(self):
        types='TYPE data_t=STRUCTURE bytes:ARRAY[2] OF BYTE shorts:ARRAY[2] OF SHORT ENDSTRUCTURE'
        routine='ROUTINE make_data:data_t BEGIN RETURN data END make_data'
        values=execute('data.bytes[1]=7 data.shorts[1]=32767 USING make_data() DO flag=UNINIT(shorts[1]) bytes[2]=42 shorts[1]=9 result=bytes[2]+shorts[1] ENDUSING',
            types=types,decl='data:data_t flag:BOOLEAN result:INTEGER',routines=routine)
        self.assertEqual((values['RESULT'],values['FLAG'],values['DATA']),(51,True,{'BYTES':[7,B],'SHORTS':[U,U]}))

    def test_grouped_declared_storage_keeps_live_no_copy_semantics(self):
        self.assertEqual(execute('USING ((source)) DO value=42 ENDUSING')['SOURCE']['VALUE'],42)

    def test_nested_private_alias_uses_same_temporary_storage(self):
        routine='ROUTINE make_box:box_t BEGIN RETURN box END make_box'
        values=execute('USING make_box() DO USING child DO value=42 ENDUSING result=child.value ENDUSING',routines=routine)
        self.assertEqual((values['RESULT'],values['BOX']['CHILD']['VALUE']),(42,U))

    def test_repeat_calls_do_not_share_captured_mutations(self):
        values=execute('calls=0 source.value=7 USING make() DO value=42 ENDUSING USING make() DO result=value ENDUSING')
        self.assertEqual((values['RESULT'],values['CALLS'],values['SOURCE']['VALUE']),(7,2,7))


class ComputedUsingValidationAndEffectsTests(unittest.TestCase):
    def reject(self,body,code='E_FOR_COUNTER',**options):
        with self.assertRaises(TranslationError) as caught:build(body,**options)
        self.assertEqual(caught.exception.code,code,str(caught.exception))

    def test_selectors_evaluate_once_left_to_right_before_body(self):
        routines='ROUTINE first:VECTOR BEGIN calls=calls*10+1 RETURN VEC(1,0,0) END first ROUTINE second:VECTOR BEGIN calls=calls*10+2 RETURN VEC(2,0,0) END second'
        values=execute('calls=0 USING first(),second() DO number=x ENDUSING',routines=routines)
        self.assertEqual((values['CALLS'],values['NUMBER']),(12,2.))

    def test_empty_body_still_evaluates_selector(self):
        self.assertEqual(execute('calls=0 USING make() DO ENDUSING')['CALLS'],1)

    def test_later_invalid_selector_preserves_prior_effects(self):
        p,_=build('calls=0 USING make(),rows[0] DO result=99 ENDUSING')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['CALLS'],p.snapshot()['RESULT']),(1,U))

    def test_later_source_mutation_does_not_change_earlier_capture(self):
        routines=MAKE+' ROUTINE change:VECTOR BEGIN source.value=99 RETURN VEC(1,2,3) END change'
        values=execute('calls=0 source.value=7 USING make(),change() DO result=value ENDUSING',routines=routines)
        self.assertEqual((values['RESULT'],values['SOURCE']['VALUE']),(7,99))

    def test_computed_element_indexes_run_once_after_source_call(self):
        routines='ROUTINE make_rows:ARRAY OF row_t BEGIN calls=calls*10+1 RETURN rows END make_rows ROUTINE pick:INTEGER BEGIN calls=calls*10+2 RETURN 2 END pick'
        values=execute('calls=0 USING make_rows()[pick()] DO value=42 result=value ENDUSING',routines=routines)
        self.assertEqual((values['CALLS'],values['RESULT'],values['ROWS'][1]['VALUE']),(12,42,U))

    def test_selector_list_does_not_expose_earlier_fields_to_later_selector(self):
        routines='ROUTINE make_box:box_t BEGIN RETURN box END make_box'
        values=execute('slot=2 box.slot=1 USING make_box(),rows[slot] DO value=42 ENDUSING',routines=routines)
        self.assertEqual((values['ROWS'][0]['VALUE'],values['ROWS'][1]['VALUE']),(U,42))

    def test_nested_selector_uses_outer_private_field_as_index(self):
        routines='ROUTINE make_box:box_t BEGIN RETURN box END make_box'
        values=execute('box.slot=2 USING make_box() DO USING rows[slot] DO value=42 result=value ENDUSING ENDUSING',routines=routines)
        self.assertEqual((values['RESULT'],values['BOX']['ROWS'][1]['VALUE'],values['ROWS'][1]['VALUE']),(42,U,U))

    def test_compile_only_never_evaluates_selector_body(self):
        p,_=build('USING make() DO ENDUSING',routines='ROUTINE make:row_t BEGIN ABORT END make')
        self.assertEqual(p.snapshot()['SOURCE']['VALUE'],U)
        with self.assertRaises(rt.KarelAbort):p.run()

    def test_computed_scalar_array_joint_and_resource_top_levels_reject(self):
        for spec in ('INTEGER','ARRAY[2] OF INTEGER','JOINTPOS6','FILE','PATH','QUEUE_TYPE'):
            with self.subTest(spec=spec):self.reject('USING item DO ENDUSING','E_USING_TYPE',types='',decl='item:'+spec,routines='')
        self.reject('USING VEC(1,2,3).x DO ENDUSING','E_USING_TYPE')

    def test_constructor_arity_is_checked_even_in_empty_scope(self):self.reject('USING VEC(1,2) DO ENDUSING','E_ARGUMENTS')

    def test_mutating_function_selector_cannot_write_active_counter(self):
        self.reject('FOR i=1 TO 2 DO USING make() DO ENDUSING ENDFOR',routines='ROUTINE make:row_t BEGIN i=99 RETURN source END make')

    def test_transitive_selector_function_counter_write_is_rejected(self):
        routines='ROUTINE change BEGIN i=99 END change ROUTINE make:row_t BEGIN change RETURN source END make'
        self.reject('FOR i=1 TO 2 DO USING make() DO ENDUSING ENDFOR',routines=routines)

    def test_selector_reference_argument_cannot_modify_active_counter(self):
        routines='ROUTINE make(p:INTEGER):row_t BEGIN p=99 RETURN source END make'
        self.reject('FOR i=1 TO 2 DO USING make(i) DO ENDUSING ENDFOR',routines=routines)

    def test_computed_subscript_effect_cannot_write_active_counter(self):
        routines='ROUTINE make_rows:ARRAY OF row_t BEGIN RETURN rows END make_rows ROUTINE pick:INTEGER BEGIN i=99 RETURN 1 END pick'
        self.reject('FOR i=1 TO 2 DO USING make_rows()[pick()] DO ENDUSING ENDFOR',routines=routines)

    def test_aggregate_counter_root_guard_covers_selector_global_writes(self):
        routines='ROUTINE make:row_t BEGIN source.label=\'x\' RETURN other END make'
        self.reject('FOR source.value=1 TO 2 DO USING make() DO ENDUSING ENDFOR',routines=routines)

    def test_safe_counter_reads_and_private_field_writes_are_allowed(self):
        routines='ROUTINE make:row_t BEGIN RETURN source END make'
        values=execute('total=0 FOR source.value=1 TO 3 DO USING make() DO total=total+value value=99 ENDUSING ENDFOR',routines=routines)
        self.assertEqual((values['TOTAL'],values['SOURCE']['VALUE']),(6,U))

    def test_named_alias_counter_root_protection_is_retained(self):self.reject('USING source DO FOR value=1 TO 2 DO source.label=\'x\' ENDFOR ENDUSING')

    def test_private_temporary_field_for_counter_uses_isolated_storage(self):
        values=execute('calls=0 total=0 USING make() DO FOR value=1 TO 3 DO total=total+value ENDFOR flag=UNINIT(value) ENDUSING')
        self.assertEqual((values['TOTAL'],values['FLAG'],values['SOURCE']['VALUE']),(6,True,U))

    def test_nested_private_alias_counter_cannot_reuse_active_root(self):
        self.reject('USING make_box() DO FOR slot=1 TO 2 DO USING child DO FOR value=1 TO 2 DO ENDFOR ENDUSING ENDFOR ENDUSING',routines='ROUTINE make_box:box_t BEGIN RETURN box END make_box')

    def test_private_connected_timer_is_accepted(self):
        p,r=build('calls=0 USING make() DO CONNECT TIMER TO value DISCONNECT TIMER value ENDUSING',cooperative=True)
        p.run();self.assertEqual(r.report['connected_timers'][0]['provenance'],'private_temporary')

    def test_readonly_position_columns_remain_readonly_in_computed_selector(self):
        for selector in ('make_pose().normal','(make_pose().orient)','make_pose().approach'):
            with self.subTest(selector=selector):self.reject('USING '+selector+' DO x=1 ENDUSING','E_POSITION_READ_ONLY',
                decl=DECL+' pose:POSITION',routines='ROUTINE make_pose:POSITION BEGIN RETURN pose END make_pose')

    def test_nested_computed_position_column_cannot_escape_as_writable_formal(self):
        routines='ROUTINE make_pose:POSITION BEGIN RETURN pose END make_pose ROUTINE edit(p:REAL) BEGIN p=99 END edit'
        self.reject('USING make_pose() DO USING normal DO edit(x) ENDUSING ENDUSING','E_POSITION_READ_ONLY_ARG',decl=DECL+' pose:POSITION',routines=routines)

    def test_config_turn_bounds_remain_checked_in_private_capture(self):
        p,_=build('USING make_cfg() DO cfg_turn_no1=1 cfg_turn_no1=8 ENDUSING',decl=DECL+' cfg:CONFIG',routines='ROUTINE make_cfg:CONFIG BEGIN RETURN cfg END make_cfg')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'-8'):p.run()
        self.assertEqual(p.snapshot()['CFG']['CFG_TURN_NO1'],U)

    def test_config_subfield_conversion_outputs_remain_blocked(self):
        self.reject("USING make_cfg() DO CNV_STR_INT('8',cfg_turn_no1) ENDUSING",'E_CONFIG_OUTPUT',decl=DECL+' cfg:CONFIG',routines='ROUTINE make_cfg:CONFIG BEGIN RETURN cfg END make_cfg')

    def test_runtime_checked_capture_rejects_forged_schema_and_known_values(self):
        # Synthetic host stubs deliberately bypass generated RETURN validation;
        # the USING boundary must still validate and copy what it receives.
        for damage in ('field','schema','type','capacity','unknown'):
            with self.subTest(damage=damage):
                p,_=build('USING make() DO result=42 ENDUSING')
                item=p._state.values['SOURCE'].clone()
                if damage=='field':item.values['EXTRA']=1
                if damage=='schema':item.types['VALUE']=rt.REAL
                if damage=='type':item.values['VALUE']=True
                if damage=='capacity':item.values['LABEL']='excess'
                if damage=='unknown':item.values['VALUE']=rt.UNKNOWN_BYTE
                p._routine_MAKE=lambda:item
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertEqual(p.snapshot()['RESULT'],U)

    def test_mutating_private_fields_does_not_claim_a_global_storage_write(self):
        routines='ROUTINE work:INTEGER BEGIN USING VEC(1,2,3) DO x=42 RETURN 7 ENDUSING END work'
        p,r=build('result=work()',routines=routines)
        self.assertEqual(p.run()['RESULT'],7)
        effects=r.report['routine_effects']['WORK']
        self.assertEqual(effects['potential_global_writes'],[])
        self.assertFalse(effects['potential_external_writes'])


class ComputedUsingFlowAndLifetimeTests(unittest.TestCase):
    def test_internal_backward_jump_retains_one_capture(self):
        values=execute('calls=0 source.value=0 USING make() DO again:: value=value+1 IF value<3 THEN GOTO again ENDIF result=value ENDUSING')
        self.assertEqual((values['RESULT'],values['CALLS'],values['SOURCE']['VALUE']),(3,1,0))

    def test_exit_restores_outer_and_global_alias_resolution(self):
        values=execute('calls=0 source.value=7 other.value=8 USING source DO USING make() DO value=99 GOTO done ENDUSING done:: result=value ENDUSING total=source.value')
        self.assertEqual((values['RESULT'],values['TOTAL']),(7,7))

    def test_reentry_allocates_fresh_temporary_on_each_loop(self):
        values=execute('calls=0 source.value=7 total=0 FOR i=1 TO 2 DO USING make() DO value=value+i total=total+value ENDUSING ENDFOR')
        self.assertEqual((values['TOTAL'],values['CALLS'],values['SOURCE']['VALUE']),(17,2,7))

    def test_declared_counter_can_run_inside_computed_scope(self):
        values=execute('calls=0 USING make() DO value=0 FOR i=1 TO 3 DO value=value+i ENDFOR result=value ENDUSING')
        self.assertEqual((values['RESULT'],values['I']),(6,U))

    def test_entry_and_sibling_jumps_do_not_skip_computed_capture(self):
        bodies=('GOTO inside USING make() DO inside:: value=42 ENDUSING',
            'USING make() DO GOTO inside ENDUSING USING make() DO inside:: value=42 ENDUSING')
        for body in bodies:
            with self.subTest(body=body):
                with self.assertRaises(TranslationError) as caught:build(body)
                self.assertEqual(caught.exception.code,'E_GOTO_ENTRY')

    def test_pause_resume_retains_private_capture_after_source_changes(self):
        p,_=build('calls=0 source.value=7 USING make() DO value=20 PAUSE value=value+22 result=value ENDUSING',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        p._state.values['SOURCE'].values['VALUE']=99
        p.resume()
        self.assertEqual((p.snapshot()['RESULT'],p.snapshot()['SOURCE']['VALUE'],p.snapshot()['CALLS']),(42,99,1))

    def test_stop_closes_frames_without_copyback(self):
        p,_=build('calls=0 source.value=7 work',routines=MAKE+' ROUTINE work BEGIN USING make() DO value=99 PAUSE result=value ENDUSING END work',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop()
        self.assertEqual((p.snapshot()['SOURCE']['VALUE'],p.snapshot()['RESULT'],p._state.local_frames,p._state.call_depth),(7,U,[],0))

    def test_return_value_survives_scope_and_cleans_routine_frame(self):
        p,_=build('result=work()',routines='ROUTINE work:INTEGER BEGIN USING VEC(1,2,3) DO RETURN 42 ENDUSING END work')
        self.assertEqual(p.run()['RESULT'],42)
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))

    def test_runtime_error_keeps_prior_external_effects_without_copyback(self):
        p,_=build('calls=0 source.value=7 USING make() DO value=99 result=value total=rows[0].value ENDUSING')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['CALLS'],p.snapshot()['SOURCE']['VALUE'],p.snapshot()['RESULT']),(1,7,99))

    def test_step_budget_limits_private_label_loop(self):
        p,_=build('calls=0 source.value=0 USING make() DO again:: value=value+1 GOTO again ENDUSING')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=20)
        self.assertEqual((p.snapshot()['CALLS'],p.snapshot()['SOURCE']['VALUE']),(1,0))

    def test_handler_retains_and_mutates_private_capture_after_scope_exit(self):
        values=execute('calls=0 source.value=7 USING make() DO value=20 CONDITION[1]: WHEN EVENT[1] DO value=value+22 result=value ENDCONDITION ENDUSING ENABLE CONDITION[1] SIGNAL EVENT[1]')
        self.assertEqual((values['RESULT'],values['SOURCE']['VALUE'],values['CALLS']),(42,7,1))

    def test_handlers_retain_distinct_temporaries_across_entries(self):
        values=execute('calls=0 FOR i=1 TO 2 DO USING make() DO value=i IF i=1 THEN CONDITION[1]: WHEN EVENT[1] DO value=value+10 result=value ENDCONDITION ELSE CONDITION[2]: WHEN EVENT[2] DO value=value+20 total=value ENDCONDITION ENDIF ENDUSING ENDFOR ENABLE CONDITION[1] ENABLE CONDITION[2] SIGNAL EVENT[2] SIGNAL EVENT[1]')
        self.assertEqual((values['RESULT'],values['TOTAL'],values['CALLS']),(11,22,2))

    def test_handler_action_can_create_a_fresh_inner_computed_capture(self):
        values=execute('calls=0 USING make() DO value=7 CONDITION[1]: WHEN EVENT[1] DO USING VEC(1,2,3) DO number=x+y+z ENDUSING result=value ENDCONDITION ENDUSING ENABLE CONDITION[1] SIGNAL EVENT[1]')
        self.assertEqual((values['RESULT'],values['NUMBER']),(7,6.))

    def test_deferred_predicate_reads_retained_private_value(self):
        values=execute('calls=0 USING make() DO value=42 CONDITION[1]: WHEN value=42 DO result=7 DISABLE CONDITION[1] ENDCONDITION ENDUSING source.value=0 ENABLE CONDITION[1] total=1')
        self.assertEqual((values['RESULT'],values['SOURCE']['VALUE']),(7,0))

    def test_selector_function_can_pause_before_capture_finishes(self):
        p,_=build('source.value=7 USING make() DO value=42 result=value ENDUSING',routines='ROUTINE make:row_t BEGIN PAUSE RETURN source END make',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['RESULT'],U)
        p.resume()
        self.assertEqual((p.snapshot()['RESULT'],p.snapshot()['SOURCE']['VALUE'],p._state.call_depth),(42,7,0))


class ComputedUsingReportAndIntegrationTests(unittest.TestCase):
    def test_json_report_distinguishes_named_storage_and_independent_values(self):
        _,r=build('USING source,make(),VEC(1,2,3) DO ENDUSING')
        report=json.loads(json.dumps(r.report));captures=report['using_scopes'][0]['selector_captures']
        self.assertEqual([row['source_kind'] for row in captures],['storage_reference','computed_value','computed_value'])
        self.assertEqual([row['source_root'] for row in captures],['SOURCE',None,None])
        self.assertEqual([row['provenance'] for row in captures],['declared_storage','private_temporary','private_temporary'])
        self.assertEqual([row['independent_copy'] for row in captures],[False,True,True])
        self.assertTrue(all(row['copy_back'] is False for row in captures))
        self.assertFalse(report['computed_using_policy']['controller_validated'])
        self.assertNotIn('function-result/computed selectors remain blocked',' '.join(report['limitations']))

    def test_nested_private_reference_provenance_is_preserved(self):
        _,r=build('USING make_box() DO USING child DO value=42 ENDUSING ENDUSING',routines='ROUTINE make_box:box_t BEGIN RETURN box END make_box')
        captures=r.report['using_scopes'][1]['selector_captures']
        self.assertEqual(captures[0],dict(source_kind='storage_reference',provenance='private_temporary',source_root=None,
            expression_kind='field',independent_copy=False,copy_back=False))

    def test_include_source_map_retains_computed_selector_origin(self):
        r=translate('PROGRAM MAIN VAR result:REAL BEGIN\n%INCLUDE body\nEND MAIN',includes={'body.kl':'USING VEC(1,2,3) DO result=x+y+z ENDUSING'})
        namespace={'__name__':'computed_include'};exec(r.python_source,namespace)
        self.assertEqual(namespace['Program']().run()['RESULT'],6.)
        self.assertTrue(any(row.get('source_file')=='body.kl' for row in r.report['source_map']))

    def test_linked_external_function_result_can_be_captured(self):
        sources={'main':'PROGRAM MAIN VAR result:REAL ROUTINE make_vector:VECTOR FROM LIB BEGIN USING make_vector() DO x=42 result=x ENDUSING END MAIN',
            'lib':'PROGRAM LIB VAR original:VECTOR ROUTINE make_vector:VECTOR BEGIN original=VEC(1,2,3) RETURN original END make_vector BEGIN END LIB'}
        instance=translate_project(sources).instantiate();values=instance.run('MAIN')
        self.assertEqual((values['MAIN']['values']['RESULT'],values['LIB']['values']['ORIGINAL']['X']),(42.,1.))

    def test_cli_translation_and_driver_state_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'input.kl';target=Path(folder)/'output.py';state=Path(folder)/'state.json'
            source.write_bytes(b'PROGRAM MAIN VAR result:REAL BEGIN USING VEC(1,2,3) DO x=42 result=x+y+z ENDUSING END MAIN')
            process=subprocess.run([sys.executable,'-X','utf8','-m','karel2py',str(source),'-o',str(target)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            process=subprocess.run([sys.executable,'-X','utf8',str(target),'--state-out',str(state)],cwd=ROOT,capture_output=True,text=True,
                env=dict(os.environ,PYTHONPATH=str(ROOT)))
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertEqual(json.loads(state.read_text(encoding='utf-8'))['variables'],[dict(program='MAIN',path='RESULT',type=['REAL'],value=47.)])

    def test_legacy_translator_retains_function_and_constructor_rejections(self):
        for selector in ('make()','VEC(1,2,3)'):
            with self.subTest(selector=selector):
                with self.assertRaises(TranslationError) as caught:build('USING '+selector+' DO ENDUSING',translator=legacy_translate)
                self.assertEqual(caught.exception.code,'E_USING_TARGET')


if __name__=='__main__':unittest.main()
