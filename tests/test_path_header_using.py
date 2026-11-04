"""Authored PATH-header lexical captures, private lifetimes, counters and timers."""
from copy import deepcopy
import unittest
from karel2py import runtime as rt,translate,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_private_using_counters import retained_root

PREFIX='TYPE node_t=STRUCTURE value:INTEGER ENDSTRUCTURE child_t=STRUCTURE value:INTEGER ENDSTRUCTURE header_t=STRUCTURE count:INTEGER elapsed:INTEGER label:STRING[4] child:child_t samples:ARRAY[2]OF INTEGER small:BYTE narrow:SHORT ENDSTRUCTURE route_t=PATH NODEDATA=node_t PATHHEADER=header_t'
DECL='source,other:route_t bank:ARRAY[2]OF route_t result,total,visits,status,index_value:INTEGER flag:BOOLEAN'
SEED="source.count=7 source.label='seed' source.child.value=5 source.samples[1]=11 source.samples[2]=13 source.small=1 source.narrow=2 visits=0 "
MAKE='ROUTINE make:route_t BEGIN visits=visits+1 RETURN source END make'
U={'uninitialized':True}

def build(body,*,seed=True,prefix=PREFIX,decl=DECL,routines=MAKE,**options):return compile_program((SEED if seed else '')+body,prefix=prefix,decl=decl,routines=routines,**options)
def raw(p,name='SOURCE'):return p._state.values[name]
def header(p,name='SOURCE'):return raw(p,name).data

class PathHeaderStorageTests(unittest.TestCase):
    def test_named_storage_fields_are_writable(self):
        p,_=build('USING source DO count=42 ENDUSING');self.assertEqual(p.run()['SOURCE']['data']['COUNT'],42)
    def test_grouping_retains_original_storage(self):
        p,_=build('USING ((source)) DO count=count+1 ENDUSING');self.assertEqual(p.run()['SOURCE']['data']['COUNT'],8)
    def test_unknown_fields_remain_uninitialized(self):
        p,_=build('USING source DO count=42 ENDUSING',seed=False);v=p.run();self.assertEqual(v['SOURCE']['data']['ELAPSED'],U);self.assertEqual(v['SOURCE']['nodes'],[])
    def test_string_capacity_is_retained(self):
        p,_=build("USING source DO label='longer' ENDUSING");self.assertEqual(p.run()['SOURCE']['data']['LABEL'],'long')
    def test_nested_record_selector_keeps_header_storage(self):
        p,_=build('USING source DO USING child DO value=42 ENDUSING ENDUSING');self.assertEqual(p.run()['SOURCE']['data']['CHILD']['VALUE'],42)
    def test_array_header_field_updates_original_cell(self):
        p,_=build('index_value=2 USING source DO samples[index_value]=42 ENDUSING');self.assertEqual(p.run()['SOURCE']['data']['SAMPLES'],[11,42])
    def test_indexed_path_captured_once(self):
        p,_=build('index_value=1 USING bank[index_value] DO count=42 index_value=2 count=count+1 ENDUSING');v=p.run();self.assertEqual([r['data']['COUNT'] for r in v['BANK']],[43,U])
    def test_index_function_is_evaluated_once(self):
        p,_=build('USING bank[pick()] DO count=42 result=count ENDUSING',routines=MAKE+' ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN 2 END pick');v=p.run();self.assertEqual((v['VISITS'],v['RESULT']),(1,42))
    def test_multi_index_effect_order_is_left_to_right(self):
        p,_=build('USING bank[row(),col()] DO count=42 ENDUSING',decl=DECL.replace('bank:ARRAY[2]','bank:ARRAY[2,2]'),routines=MAKE+' ROUTINE row:INTEGER BEGIN visits=visits*10+1 RETURN 1 END row ROUTINE col:INTEGER BEGIN visits=visits*10+2 RETURN 2 END col');self.assertEqual(p.run()['VISITS'],12)
    def test_rightmost_header_wins(self):
        p,_=build('other.count=9 USING source,other DO count=42 ENDUSING');v=p.run();self.assertEqual((v['SOURCE']['data']['COUNT'],v['OTHER']['data']['COUNT']),(7,42))
    def test_inner_header_wins_and_outer_binding_is_restored(self):
        p,_=build('USING source DO USING other DO count=42 ENDUSING count=8 ENDUSING');v=p.run();self.assertEqual((v['SOURCE']['data']['COUNT'],v['OTHER']['data']['COUNT']),(8,42))
    def test_record_and_path_selectors_share_lookup_rules(self):
        p,_=build('USING source,source.child DO value=42 count=8 ENDUSING');v=p.run();self.assertEqual((v['SOURCE']['data']['CHILD']['VALUE'],v['SOURCE']['data']['COUNT']),(42,8))
    def test_selector_list_uses_only_enclosing_aliases(self):
        p,_=build('index_value=2 source.count=1 USING source,bank[index_value] DO count=42 ENDUSING');self.assertEqual(p.run()['BANK'][1]['data']['COUNT'],42)
    def test_header_only_default_node_layout_is_supported(self):
        p,_=build('USING source DO count=42 ENDUSING',seed=False,prefix='TYPE h=STRUCTURE count:INTEGER ENDSTRUCTURE',decl='source:PATH PATHHEADER=h',routines='');self.assertEqual(p.run()['SOURCE']['data']['COUNT'],42)
    def test_pathdata_alias_is_supported(self):
        p,_=build('USING source DO count=42 ENDUSING',prefix=PREFIX.replace('PATHHEADER=header_t','PATHDATA=header_t'));self.assertEqual(p.run()['SOURCE']['data']['COUNT'],42)
    def test_whole_path_assignment_preserves_selected_header_alias(self):
        p,_=build('other.count=99 USING source DO source=other count=count+1 ENDUSING');self.assertEqual(p.run()['SOURCE']['data']['COUNT'],100)
    def test_host_cell_replacement_does_not_retarget_selected_header(self):
        seen=[]
        def read(_):seen.append(header(p));p._state.values['SOURCE']=rt.PathValue(raw(p).spec);return [42]
        p,_=build('USING source DO READ(count) result=count ENDUSING',read=read);v=p.run();self.assertEqual((seen[0].values['COUNT'],v['RESULT'],v['SOURCE']['data']['COUNT']),(42,42,U))
    def test_bare_formal_updates_caller_and_records_effect(self):
        p,r=build('work(source)',routines=MAKE+' ROUTINE work(v:route_t) BEGIN USING v DO count=42 ENDUSING END work');self.assertEqual(p.run()['SOURCE']['data']['COUNT'],42);self.assertEqual(r.report['routine_effects']['WORK']['potential_parameter_writes'],['V'])
    def test_private_formal_does_not_copy_back(self):
        p,_=build('work((source))',routines=MAKE+' ROUTINE work(v:route_t) BEGIN USING v DO count=42 result=count ENDUSING END work');v=p.run();self.assertEqual((v['SOURCE']['data']['COUNT'],v['RESULT']),(7,42))
    def test_created_byname_path_retains_live_header(self):
        p,_=build("CREATE_VAR('CACHE','PATH','T','route_t',0,0,0,0,status) work(BYNAME('CACHE','PATH',index_value))",routines=MAKE+' ROUTINE work(v:route_t) BEGIN USING v DO count=42 result=count ENDUSING END work');self.assertEqual(p.run()['RESULT'],42)
    def test_explicit_conversion_output_uses_header_field(self):
        p,_=build("USING source DO CNV_STR_INT('42',count) ENDUSING");self.assertEqual(p.run()['SOURCE']['data']['COUNT'],42)
    def test_header_read_uses_existing_scalar_transport(self):
        p,_=build('USING source DO READ(count,label) ENDUSING',read=lambda r:[42,'text']);v=p.run();self.assertEqual((v['SOURCE']['data']['COUNT'],v['SOURCE']['data']['LABEL']),(42,'text'))
    def test_report_retains_original_path_and_selected_header_schemas(self):
        _,r=build('USING source DO count=42 ENDUSING');row=r.report['using_scopes'][0]['selector_captures'][0];self.assertTrue(row['path_header']);self.assertEqual(row['path_type_spec'][0],'PATH');self.assertEqual(row['selected_type_spec'][0],'STRUCTURE');self.assertEqual(row['source_root'],'SOURCE')

class PathHeaderValueTests(unittest.TestCase):
    def test_computed_header_is_an_independent_copy(self):
        p,_=build('USING make() DO count=42 result=count ENDUSING');v=p.run();self.assertEqual((v['RESULT'],v['SOURCE']['data']['COUNT'],v['VISITS']),(42,7,1))
    def test_bare_function_name_is_resolved(self):
        p,_=build('USING make DO count=42 result=count ENDUSING');self.assertEqual(p.run()['VISITS'],1)
    def test_grouped_computed_value_remains_private(self):
        p,_=build('USING ((make())) DO count=42 ENDUSING');self.assertEqual(p.run()['SOURCE']['data']['COUNT'],7)
    def test_computed_bank_cell_is_private(self):
        p,_=build('bank[2]=source USING copies()[2] DO count=42 result=count ENDUSING',routines=MAKE+' ROUTINE copies:ARRAY OF route_t BEGIN RETURN bank END copies');v=p.run();self.assertEqual((v['RESULT'],v['BANK'][1]['data']['COUNT']),(42,7))
    def test_nested_header_reference_shares_private_copy(self):
        p,_=build('USING make() DO USING child DO value=42 ENDUSING result=child.value ENDUSING');v=p.run();self.assertEqual((v['RESULT'],v['SOURCE']['data']['CHILD']['VALUE']),(42,5))
    def test_partial_private_header_preserves_unknown_markers(self):
        p,_=build('USING make() DO flag=UNINIT(elapsed) count=42 ENDUSING');v=p.run();self.assertTrue(v['FLAG']);self.assertEqual(v['SOURCE']['data']['ELAPSED'],U)
    def test_each_entry_allocates_its_own_private_header(self):
        p,_=build('total=0 FOR index_value=1 TO 2 DO USING make() DO count=count+index_value total=total+count ENDUSING ENDFOR');v=p.run();self.assertEqual((v['TOTAL'],v['VISITS'],v['SOURCE']['data']['COUNT']),(17,2,7))
    def test_private_field_can_be_forwarded_by_reference(self):
        p,_=build('USING make() DO work(count) result=count ENDUSING',routines=MAKE+' ROUTINE work(n:INTEGER) BEGIN n=42 END work');v=p.run();self.assertEqual((v['RESULT'],v['SOURCE']['data']['COUNT']),(42,7))
    def test_empty_body_still_evaluates_selector(self):
        p,_=build('USING make() DO ENDUSING');self.assertEqual(p.run()['VISITS'],1)
    def test_later_failed_selector_preserves_earlier_effects(self):
        p,_=build('USING make(),bank[3] DO result=42 ENDUSING')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['VISITS'],p.snapshot()['RESULT']),(1,U))
    def test_function_selector_can_pause_before_header_capture(self):
        p,_=build('USING make() DO count=42 result=count ENDUSING',routines='ROUTINE make:route_t BEGIN PAUSE RETURN source END make')
        with self.assertRaises(rt.KarelPause):p.run()
        p.resume();self.assertEqual(p.snapshot()['RESULT'],42)
    def test_private_provenance_is_an_isolated_header_root(self):
        _,r=build('total=0 USING make() DO FOR count=1 TO 2 DO total=total+count ENDFOR ENDUSING');row=r.report['reference_for_counters'][0];self.assertIsNone(row['root']);self.assertEqual(row['provenance'],'private_temporary')

class PathHeaderLifetimeTests(unittest.TestCase):
    def test_named_capture_survives_pause(self):
        p,_=build('USING source DO count=42 PAUSE result=count ENDUSING')
        with self.assertRaises(rt.KarelPause):p.run()
        p.resume();self.assertEqual(p.snapshot()['RESULT'],42)
    def test_private_capture_survives_pause_without_copyback(self):
        p,_=build('USING make() DO count=42 PAUSE result=count ENDUSING')
        with self.assertRaises(rt.KarelPause):p.run()
        p.resume();self.assertEqual((p.snapshot()['RESULT'],p.snapshot()['SOURCE']['data']['COUNT']),(42,7))
    def test_stop_discards_private_edits(self):
        p,_=build('USING make() DO count=42 PAUSE ENDUSING')
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(p.snapshot()['SOURCE']['data']['COUNT'],7)
    def test_retained_named_handler_keeps_original_header(self):
        p,_=build('USING source DO CONDITION[1]: WHEN EVENT[1] DO count=count+1 result=count ENDCONDITION ENDUSING ENABLE CONDITION[1] SIGNAL EVENT[1]');v=p.run();self.assertEqual((v['RESULT'],v['SOURCE']['data']['COUNT']),(8,8))
    def test_retained_private_handler_keeps_private_header(self):
        p,_=build('USING make() DO CONDITION[1]: WHEN EVENT[1] DO count=count+1 result=count ENDCONDITION ENDUSING ENABLE CONDITION[1] SIGNAL EVENT[1]');v=p.run();self.assertEqual((v['RESULT'],v['SOURCE']['data']['COUNT']),(8,7))
    def test_private_handler_captures_different_headers_on_reentry(self):
        p,_=build('total=0 FOR index_value=1 TO 2 DO USING make() DO count=index_value CONDITION[index_value]: WHEN EVENT[count] DO total=total+count ENDCONDITION ENDUSING ENDFOR ENABLE CONDITION[1] ENABLE CONDITION[2] SIGNAL EVENT[1] SIGNAL EVENT[2]');self.assertEqual(p.run()['TOTAL'],3)
    def test_jumps_inside_using_retain_the_capture(self):
        p,_=build('USING source DO count=40 GO TO after count=0 after:: count=count+2 ENDUSING');self.assertEqual(p.run()['SOURCE']['data']['COUNT'],42)
    def test_labelled_dispatcher_keeps_private_capture(self):
        p,_=build('start:: USING make() DO count=42 result=count ENDUSING');v=p.run();self.assertEqual((v['RESULT'],v['SOURCE']['data']['COUNT']),(42,7))
    def test_routine_return_captures_explicit_header_data(self):
        p,_=build('result=work()',routines=MAKE+' ROUTINE work:INTEGER BEGIN USING make() DO count=42 RETURN count ENDUSING END work');v=p.run();self.assertEqual(v['RESULT'],42);self.assertEqual(p._state.local_frames,[])
    def test_context_roundtrip_contains_only_logical_data(self):
        p,_=build('USING make() DO count=42 ENDUSING');p.run();saved=p._state.execution.to_config();self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

class PathHeaderCounterTimerTests(unittest.TestCase):
    def test_private_integer_counter_counts_and_cleans_leaf(self):
        p,_=build('total=0 USING make() DO FOR count=1 TO 3 DO total=total+count ENDFOR flag=UNINIT(count) ENDUSING');v=p.run();self.assertEqual((v['TOTAL'],v['FLAG'],v['SOURCE']['data']['COUNT']),(6,True,7))
    def test_private_byte_counter_preserves_source(self):
        p,_=build('total=0 USING make() DO FOR small=1 TO 3 DO total=total+small ENDFOR ENDUSING');v=p.run();self.assertEqual((v['TOTAL'],v['SOURCE']['data']['SMALL']),(6,1))
    def test_private_short_counter_preserves_source(self):
        p,_=build('total=0 USING make() DO FOR narrow=-1 TO 1 DO total=total+narrow ENDFOR ENDUSING');v=p.run();self.assertEqual((v['TOTAL'],v['SOURCE']['data']['NARROW']),(0,2))
    def test_nested_private_counter_uses_same_header_root(self):
        p,_=build('total=0 USING make() DO USING child DO FOR value=1 TO 3 DO total=total+value ENDFOR ENDUSING ENDUSING');self.assertEqual(p.run()['TOTAL'],6)
    def test_retained_readonly_counter_alias_observes_cleanup(self):
        p,_=build('USING make() DO CONDITION[1]: WHEN EVENT[1] DO result=count ENDCONDITION FOR count=1 TO 2 DO ENDFOR ENDUSING');p.run();self.assertIs(retained_root(p).values['COUNT'],rt.UNINITIALIZED)
    def test_private_timer_initializes_only_private_elapsed(self):
        p,_=build('USING make() DO CONNECT TIMER TO elapsed result=elapsed DISCONNECT TIMER elapsed ENDUSING',clock_us=lambda:0);v=p.run();self.assertEqual((v['RESULT'],v['SOURCE']['data']['ELAPSED']),(0,U))
    def test_named_timer_updates_existing_header(self):
        p,_=build('USING source DO CONNECT TIMER TO elapsed DISCONNECT TIMER elapsed ENDUSING',clock_us=lambda:0);self.assertEqual(p.run()['SOURCE']['data']['ELAPSED'],0)
    def test_retained_private_timer_can_be_disconnected_by_handler(self):
        p,_=build('USING make() DO CONNECT TIMER TO elapsed CONDITION[1]: WHEN EVENT[1] DO result=elapsed DISCONNECT TIMER elapsed ENDCONDITION ENDUSING ENABLE CONDITION[1] SIGNAL EVENT[1]',clock_us=lambda:0);v=p.run();self.assertEqual((v['RESULT'],v['SOURCE']['data']['ELAPSED']),(0,U));self.assertEqual(p._state._timers,{})
    def test_borrowed_formal_timer_uses_routine_frame_cleanup(self):
        p,_=build('work(source)',routines=MAKE+' ROUTINE work(v:route_t) BEGIN USING v DO CONNECT TIMER TO elapsed result=elapsed ENDUSING END work',clock_us=lambda:0);self.assertEqual(p.run()['RESULT'],0);self.assertEqual(p._state._timers,{})
    def test_duplicate_header_timer_alias_rejects(self):
        p,_=build('USING source DO CONNECT TIMER TO elapsed ENDUSING USING source DO CONNECT TIMER TO elapsed ENDUSING',clock_us=lambda:0)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_private_timer_survives_pause(self):
        p,_=build('USING make() DO CONNECT TIMER TO elapsed PAUSE result=elapsed DISCONNECT TIMER elapsed ENDUSING',clock_us=lambda:0)
        with self.assertRaises(rt.KarelPause):p.run()
        p.resume();self.assertEqual(p.snapshot()['RESULT'],0)
    def test_timer_root_cannot_be_used_as_counter(self):
        with self.assertRaises(TranslationError):build('USING make() DO CONNECT TIMER TO elapsed FOR count=1 TO 2 DO ENDFOR ENDUSING',cooperative=True)
    def test_named_path_counter_remains_rejected(self):
        with self.assertRaises(TranslationError):build('USING source DO FOR count=1 TO 2 DO ENDFOR ENDUSING')
    def test_whole_root_write_inside_private_counter_remains_rejected(self):
        with self.assertRaises(TranslationError):build('USING make() DO FOR count=1 TO 2 DO child.value=42 ENDFOR ENDUSING')
    def test_writable_alias_escape_keeps_counter_guard(self):
        with self.assertRaises(TranslationError):build('USING make() DO work(count) FOR count=1 TO 2 DO ENDFOR ENDUSING',routines=MAKE+' ROUTINE work(n:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO n=42 ENDCONDITION END work')

class PathHeaderGuardTests(unittest.TestCase):
    def test_headerless_path_is_rejected(self):
        with self.assertRaises(TranslationError):build('USING p DO ENDUSING',seed=False,prefix='',decl='p:PATH',routines='')
    def test_other_nonrecord_selectors_remain_rejected(self):
        for spec in ('FILE','QUEUE_TYPE','JOINTPOS2','ARRAY[2]OF PATH'):
            with self.subTest(spec=spec),self.assertRaises(TranslationError):build('USING p DO ENDUSING',seed=False,prefix='',decl='p:'+spec,routines='')
    def test_missing_header_container_cannot_be_allocated(self):
        p,_=build('USING source DO result=42 ENDUSING',seed=False);raw(p).data=rt.UNINITIALIZED
        with self.assertRaisesRegex(rt.KarelRuntimeError,'existing shaped header'):p.run()
        self.assertEqual(p.snapshot()['RESULT'],U)
    def test_malformed_node_data_prevents_body(self):
        p,_=build('USING source DO result=42 ENDUSING',seed=False);raw(p).append();raw(p).nodes[0].values['VALUE']='bad'
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['RESULT'],U)
    def test_shared_owned_nodes_are_rejected(self):
        p,_=build('USING source DO ENDUSING',seed=False);raw(p).append();raw(p).nodes*=2
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps'):p.run()
    def test_schema_relabelling_is_rejected(self):
        p,_=build('USING source DO ENDUSING',seed=False);raw(p).spec=('PATH',None,None)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_header_shape_is_checked_for_empty_body(self):
        p,_=build('USING source DO ENDUSING',seed=False);header(p).values.pop('COUNT')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_path_scalar_leaf_budget_is_retained(self):
        p,_=build('USING source DO ENDUSING',seed=False);raw(p).append();raw(p).nodes=[deepcopy(raw(p).nodes[0]) for _ in range(32767)]
        with self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):p.run()
    def test_direct_readonly_reference_does_not_become_writable(self):
        p,_=build('',seed=False);value=raw(p);ref=rt.ReadOnlyFieldReference(value.spec,{'value':value},'value')
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.using_path_header(value.spec,ref,reference=True)
    def test_legacy_runtime_scope_is_closed(self):
        p,_=build('',seed=False)
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.using_path_header(raw(p).spec,raw(p))
    def test_selector_effects_cannot_mutate_active_outer_counter(self):
        with self.assertRaises(TranslationError):build('FOR index_value=1 TO 2 DO USING make() DO ENDUSING ENDFOR',routines='ROUTINE make:route_t BEGIN index_value=99 RETURN source END make')
    def test_uncaptured_using_scope_entry_remains_rejected(self):
        with self.assertRaises(TranslationError):build('GO TO inside USING source DO inside:: count=42 ENDUSING')
    def test_config_domains_inside_header_stay_checked(self):
        p,_=build('USING source DO cfg.cfg_turn_no1=8 ENDUSING',seed=False,prefix='TYPE h=STRUCTURE cfg:CONFIG ENDSTRUCTURE r=PATH PATHHEADER=h',decl='source:r',routines='')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_position_orientation_inside_header_stays_readonly(self):
        with self.assertRaises(TranslationError):build('USING source DO pose.normal.x=1 ENDUSING',seed=False,prefix='TYPE h=STRUCTURE pose:POSITION ENDSTRUCTURE r=PATH PATHHEADER=h',decl='source:r',routines='')
    def test_policy_records_bounds_and_lifetime(self):
        _,r=build('USING source DO ENDUSING');policy=r.report['path_header_using_policy'];self.assertIn('32767',policy['bounds']);self.assertIn('Retained handlers',policy['lifetime']);self.assertFalse(policy['controller_validated'])

class PathHeaderLinkedTests(unittest.TestCase):
    def test_linked_bare_selector_updates_caller_header(self):
        sources={'main':f'PROGRAM MAIN {PREFIX} VAR source:route_t ROUTINE work(v:route_t) FROM LIB BEGIN work(source) END MAIN','lib':f'PROGRAM LIB {PREFIX} ROUTINE work(v:route_t) BEGIN USING v DO count=42 ENDUSING END work BEGIN END LIB'}
        project=translate_project(sources).instantiate();self.assertEqual(project.run('MAIN')['MAIN']['values']['SOURCE']['data']['COUNT'],42)
    def test_linked_computed_result_has_private_header(self):
        sources={'main':f'PROGRAM MAIN {PREFIX} VAR source:route_t result:INTEGER ROUTINE copy(v:route_t):route_t FROM LIB BEGIN source.count=7 USING copy(source) DO count=42 result=count ENDUSING END MAIN','lib':f'PROGRAM LIB {PREFIX} ROUTINE copy(v:route_t):route_t BEGIN RETURN v END copy BEGIN END LIB'}
        project=translate_project(sources).instantiate();v=project.run('MAIN')['MAIN']['values'];self.assertEqual((v['RESULT'],v['SOURCE']['data']['COUNT']),(42,7))
    def test_linked_declaration_mismatch_remains_rejected(self):
        sources={'main':f'PROGRAM MAIN {PREFIX} VAR source:route_t ROUTINE work(v:route_t) FROM LIB BEGIN work(source) END MAIN','lib':'PROGRAM LIB ROUTINE work(v:PATH) BEGIN END work BEGIN END LIB'}
        with self.assertRaisesRegex(ValueError,'External routine type mismatch'):translate_project(sources).instantiate()

if __name__=='__main__':unittest.main()
