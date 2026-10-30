"""Authored lexical private-root FOR counters, aliases, scope exits and cleanup."""
import json
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


U={'uninitialized':True}
TYPES='''TYPE row_t=STRUCTURE count:INTEGER other:INTEGER ENDSTRUCTURE
box_t=STRUCTURE child:row_t sibling:row_t counts:ARRAY[2] OF INTEGER slot:INTEGER ENDSTRUCTURE'''
DECL='seed,saved:box_t i,index_value,calls,total,result,visits,missing_value,status,entry,public_value:INTEGER flag:BOOLEAN number:REAL'
MAKE='ROUTINE make:box_t BEGIN calls=calls+1 RETURN seed END make'


def build(body,*,labelled=False,routines=MAKE,types=TYPES,decl=DECL,cooperative=False,**options):
    r=translate('PROGRAM MAIN '+types+' VAR '+decl+' '+routines+' BEGIN calls=0 '+('unused:: ' if labelled else '')+body+' END MAIN',cooperative=cooperative)
    ns={'__name__':'private_counter_test'};exec(r.python_source,ns)
    return ns['Program'](**options),r


def execute(body,**options):return build(body,**options)[0].run()


def retained_root(program):
    # A deliberately readonly source handler retains its lexical record capture.
    # Inspect that retained data after unwinding, without inventing public globals.
    action=program._state._handlers[1]['clauses'][0][1]
    return action.__defaults__[0].raw()


READONLY_HANDLER='CONDITION[1]: WHEN EVENT[1] DO result=slot ENDCONDITION '


class PrivateUsingCounterStorageTests(unittest.TestCase):
    def parity(self,body,**options):
        states=[execute(body,labelled=labelled,**options) for labelled in (False,True)]
        self.assertEqual(states[0],states[1]);return states[0]

    def test_bare_integer_field_counts_and_clears_private_leaf(self):
        v=self.parity('total=0 seed.slot=99 USING make() DO FOR slot=1 TO 3 DO total=total+slot ENDFOR flag=UNINIT(slot) ENDUSING')
        self.assertEqual((v['TOTAL'],v['FLAG'],v['SEED']['SLOT'],v['CALLS']),(6,True,99,1))

    def test_dotted_private_record_counter_preserves_siblings(self):
        v=self.parity('total=0 USING make() DO child.other=9 FOR child.count=1 TO 3 DO total=total+child.count ENDFOR flag=UNINIT(child.count) result=child.other ENDUSING')
        self.assertEqual((v['TOTAL'],v['FLAG'],v['RESULT'],v['SEED']['CHILD']),(6,True,9,{'COUNT':U,'OTHER':U}))

    def test_private_array_leaf_uses_captured_index(self):
        v=self.parity('index_value=1 total=0 USING make() DO counts[2]=99 FOR counts[index_value]=1 TO 3 DO index_value=2 total=total+counts[1] ENDFOR result=counts[2] flag=UNINIT(counts[1]) ENDUSING')
        self.assertEqual((v['TOTAL'],v['RESULT'],v['FLAG']),(6,99,True))

    def test_nested_reference_capture_keeps_same_private_storage(self):
        v=self.parity('total=0 USING make() DO USING child DO FOR count=1 TO 3 DO total=total+count ENDFOR ENDUSING flag=UNINIT(child.count) ENDUSING')
        self.assertEqual((v['TOTAL'],v['FLAG']),(6,True))

    def test_downward_counter(self):
        v=self.parity('total=0 USING make() DO FOR slot=3 DOWNTO 1 DO total=total+slot ENDFOR flag=UNINIT(slot) ENDUSING')
        self.assertEqual((v['TOTAL'],v['FLAG']),(6,True))

    def test_zero_iteration_counter_still_clears_initialized_leaf(self):
        v=self.parity('total=7 USING make() DO slot=99 FOR slot=3 TO 1 DO total=0 ENDFOR flag=UNINIT(slot) ENDUSING')
        self.assertEqual((v['TOTAL'],v['FLAG']),(7,True))

    def test_independent_nested_computed_captures_have_independent_counters(self):
        v=self.parity('total=0 USING make() DO FOR slot=1 TO 2 DO USING make() DO FOR slot=1 TO 2 DO total=total+slot ENDFOR ENDUSING ENDFOR ENDUSING')
        self.assertEqual((v['TOTAL'],v['CALLS']),(6,3))

    def test_private_and_declared_counter_roots_can_nest(self):
        v=self.parity('total=0 USING make() DO FOR slot=1 TO 2 DO FOR i=1 TO 2 DO total=total+slot*i ENDFOR ENDFOR ENDUSING')
        self.assertEqual((v['TOTAL'],v['I']),(9,U))

    def test_original_source_writes_do_not_alias_private_counter(self):
        v=self.parity('total=0 USING make() DO FOR slot=1 TO 3 DO seed.slot=99 total=total+slot ENDFOR ENDUSING')
        self.assertEqual((v['TOTAL'],v['SEED']['SLOT']),(6,99))

    def test_each_fresh_entry_has_new_private_counter_storage(self):
        v=self.parity('total=0 FOR i=1 TO 2 DO USING make() DO FOR slot=1 TO i DO total=total+slot ENDFOR ENDUSING ENDFOR')
        self.assertEqual((v['TOTAL'],v['CALLS']),(4,2))

    def test_parameterized_routine_private_capture_is_fresh_storage(self):
        routines=MAKE+' ROUTINE work(limit_value:INTEGER):INTEGER VAR subtotal:INTEGER BEGIN subtotal=0 USING make() DO FOR slot=1 TO limit_value DO subtotal=subtotal+slot ENDFOR RETURN subtotal ENDUSING END work'
        v=self.parity('result=work(3)',routines=routines)
        self.assertEqual((v['RESULT'],v['SEED']['SLOT']),(6,U))

    def test_recursive_parameterized_invocations_have_private_frames(self):
        routines=MAKE+' ROUTINE work(depth:INTEGER):INTEGER VAR subtotal:INTEGER BEGIN IF depth=0 THEN RETURN 0 ENDIF subtotal=0 USING make() DO FOR slot=1 TO 2 DO subtotal=subtotal+slot+work(depth-1) ENDFOR ENDUSING RETURN subtotal END work'
        self.assertEqual(self.parity('result=work(2)',routines=routines)['RESULT'],9)

    def test_counter_selector_is_captured_before_initial_changes_index(self):
        routines=MAKE+' ROUTINE start_value:INTEGER BEGIN index_value=2 RETURN 1 END start_value'
        v=self.parity('index_value=1 USING make() DO counts[2]=99 FOR counts[index_value]=start_value() TO 2 DO ENDFOR result=counts[2] flag=UNINIT(counts[1]) ENDUSING',routines=routines)
        self.assertEqual((v['RESULT'],v['FLAG'],v['INDEX_VALUE']),(99,True,2))

    def test_counter_subscript_function_runs_once_per_entry(self):
        routines=MAKE+' ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN index_value END pick'
        v=self.parity('index_value=1 visits=0 total=0 USING make() DO FOR counts[pick()]=1 TO 3 DO index_value=2 total=total+counts[1] ENDFOR ENDUSING',routines=routines)
        self.assertEqual((v['VISITS'],v['TOTAL']),(1,6))

    def test_final_bound_reads_initialized_private_counter_once(self):
        v=self.parity('total=0 USING make() DO FOR slot=2 TO slot+2 DO total=total+slot ENDFOR ENDUSING')
        self.assertEqual(v['TOTAL'],9)

    def test_readonly_callee_can_observe_active_private_reference(self):
        routines=MAKE+' ROUTINE observe(p:INTEGER) BEGIN total=total+p END observe'
        v=self.parity('total=0 USING make() DO FOR slot=1 TO 3 DO observe(slot) ENDFOR ENDUSING',routines=routines)
        self.assertEqual(v['TOTAL'],6)

    def test_grouped_writable_actual_is_an_independent_value(self):
        routines=MAKE+' ROUTINE edit(p:INTEGER) BEGIN p=99 END edit'
        v=self.parity('total=0 USING make() DO FOR slot=1 TO 3 DO edit((slot)) total=total+slot ENDFOR ENDUSING',routines=routines)
        self.assertEqual(v['TOTAL'],6)

    def test_synchronous_write_before_loop_does_not_escape_alias(self):
        routines=MAKE+' ROUTINE edit(p:INTEGER) BEGIN p=99 END edit'
        v=self.parity('total=0 USING make() DO edit(slot) FOR slot=1 TO 3 DO total=total+slot ENDFOR ENDUSING',routines=routines)
        self.assertEqual(v['TOTAL'],6)

    def test_unknown_external_without_private_actual_cannot_name_capture(self):
        seen=[];context=rt.ExecutionContext(externals={('LIB','EXTERNAL_WORK'):lambda:seen.append(1)})
        v=execute('total=0 USING make() DO FOR slot=1 TO 2 DO external_work total=total+slot ENDFOR ENDUSING',
            routines=MAKE+' ROUTINE external_work FROM LIB',context=context)
        self.assertEqual((v['TOTAL'],seen),(3,[1,1]))

    def test_indirect_named_variable_write_cannot_resolve_private_root(self):
        v=self.parity("total=0 USING make() DO FOR slot=1 TO 2 DO SET_VAR(entry,'MAIN','PUBLIC_VALUE',9,status) total=total+slot ENDFOR ENDUSING")
        self.assertEqual((v['TOTAL'],v['PUBLIC_VALUE'],v['STATUS']),(3,9,0))


class PrivateUsingCounterProtectionTests(unittest.TestCase):
    def reject(self,body,code='E_FOR_COUNTER',**options):
        for labelled in (False,True):
            with self.subTest(labelled=labelled):
                with self.assertRaises(TranslationError) as caught:build(body,labelled=labelled,**options)
                self.assertEqual(caught.exception.code,code,str(caught.exception))

    def test_direct_counter_assignment_rejected(self):self.reject('USING make() DO FOR slot=1 TO 2 DO slot=99 ENDFOR ENDUSING')

    def test_sibling_field_assignment_protects_entire_private_root(self):self.reject('USING make() DO FOR slot=1 TO 2 DO child.other=99 ENDFOR ENDUSING')

    def test_distinct_private_array_elements_are_conservatively_same_root(self):self.reject('USING make() DO FOR counts[1]=1 TO 2 DO counts[2]=99 ENDFOR ENDUSING')

    def test_same_root_nested_counter_rejected(self):self.reject('USING make() DO FOR slot=1 TO 2 DO FOR child.count=1 TO 2 DO ENDFOR ENDFOR ENDUSING')

    def test_nested_reference_capture_does_not_create_a_new_protection_root(self):self.reject('USING make() DO FOR slot=1 TO 2 DO USING child DO FOR count=1 TO 2 DO ENDFOR ENDUSING ENDFOR ENDUSING')

    def test_nested_reference_alias_write_cannot_bypass_protection(self):self.reject('USING make() DO FOR slot=1 TO 2 DO USING child DO other=99 ENDUSING ENDFOR ENDUSING')

    def test_read_output_to_private_sibling_rejected(self):self.reject('USING make() DO FOR slot=1 TO 2 DO READ(child.other) ENDFOR ENDUSING')

    def test_scalar_conversion_output_to_private_sibling_rejected(self):self.reject("USING make() DO FOR slot=1 TO 2 DO CNV_STR_INT('9',child.other) ENDFOR ENDUSING")

    def test_service_output_to_private_sibling_rejected(self):self.reject("USING make() DO FOR slot=1 TO 2 DO GET_VAR(entry,'MAIN','PUBLIC_VALUE',child.other,status) ENDFOR ENDUSING")

    def test_register_output_to_private_sibling_rejected(self):self.reject('USING make() DO FOR slot=1 TO 2 DO GET_REG(1,flag,child.other,number,status) ENDFOR ENDUSING')

    def test_writable_reference_actual_rejected(self):self.reject('USING make() DO FOR slot=1 TO 2 DO edit(child.other) ENDFOR ENDUSING',routines=MAKE+' ROUTINE edit(p:INTEGER) BEGIN p=99 END edit')

    def test_transitive_writable_reference_actual_rejected(self):self.reject('USING make() DO FOR slot=1 TO 2 DO relay(child.other) ENDFOR ENDUSING',routines=MAKE+' ROUTINE edit(p:INTEGER) BEGIN p=99 END edit ROUTINE relay(p:INTEGER) BEGIN edit(p) END relay')

    def test_handler_direct_private_sibling_write_rejected(self):self.reject('USING make() DO CONDITION[1]: WHEN EVENT[1] DO child.other=99 ENDCONDITION FOR slot=1 TO 2 DO ENDFOR ENDUSING')

    def test_handler_conversion_private_sibling_write_rejected(self):self.reject("USING make() DO CONDITION[1]: WHEN EVENT[1] DO CNV_STR_INT('9',child.other) ENDCONDITION FOR slot=1 TO 2 DO ENDFOR ENDUSING")

    def test_handler_special_conversion_and_register_outputs_protect_private_root(self):
        for action in ("CNV_STR_TIME('2026/10/28 12:00:00',child.other)",
                       'GET_REG(1,flag,child.other,number,status)',
                       'SET_INT_REG(1,9,child.other)',
                       "CNV_STR_CONF('N',cfg,child.other)",
                       'CNV_JPOS_REL(joints,axes,child.other)'):
            with self.subTest(action=action):
                self.reject('USING make() DO CONDITION[1]: WHEN EVENT[1] DO '+action+' ENDCONDITION FOR slot=1 TO 2 DO ENDFOR ENDUSING',
                    decl=DECL+' cfg:CONFIG joints:JOINTPOS3 axes:ARRAY[3] OF REAL')

    def test_handler_transitive_reference_write_rejected(self):self.reject('USING make() DO CONDITION[1]: WHEN EVENT[1] DO edit(child.other) ENDCONDITION FOR slot=1 TO 2 DO ENDFOR ENDUSING',routines=MAKE+' ROUTINE edit(p:INTEGER) BEGIN p=99 END edit')

    def test_retained_scalar_parameter_alias_before_loop_rejected(self):
        routines=MAKE+' ROUTINE retain(p:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO p=99 ENDCONDITION END retain'
        self.reject('USING make() DO retain(child.other) FOR slot=1 TO 2 DO ENDFOR ENDUSING',routines=routines)

    def test_transitively_retained_parameter_alias_before_loop_rejected(self):
        routines=MAKE+' ROUTINE retain(p:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO p=99 ENDCONDITION END retain ROUTINE relay(p:INTEGER) BEGIN retain(p) END relay'
        self.reject('USING make() DO relay(child.other) FOR slot=1 TO 2 DO ENDFOR ENDUSING',routines=routines)

    def test_external_writable_alias_before_loop_is_a_possible_escape(self):self.reject('USING make() DO external_work(child.other) FOR slot=1 TO 2 DO ENDFOR ENDUSING',routines=MAKE+' ROUTINE external_work(p:INTEGER) FROM LIB')

    def test_detached_retained_argument_does_not_escape_private_root(self):
        routines=MAKE+' ROUTINE retain(p:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO p=99 ENDCONDITION END retain'
        v=execute('total=0 USING make() DO child.other=9 retain((child.other)) FOR slot=1 TO 2 DO total=total+slot ENDFOR result=child.other ENDUSING ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=routines)
        self.assertEqual((v['TOTAL'],v['RESULT']),(3,9))

    def test_readonly_retained_reference_is_safe(self):
        routines=MAKE+' ROUTINE retain(p:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO result=p ENDCONDITION END retain'
        v=execute('total=0 USING make() DO child.other=9 retain(child.other) FOR slot=1 TO 2 DO total=total+slot ENDFOR ENDUSING ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=routines)
        self.assertEqual((v['TOTAL'],v['RESULT']),(3,9))

    def test_original_source_handler_write_does_not_alias_private_root(self):
        v=execute('CONDITION[1]: WHEN EVENT[1] DO seed.slot=99 ENDCONDITION ENABLE CONDITION[1] total=0 USING make() DO FOR slot=1 TO 2 DO SIGNAL EVENT[1] total=total+slot ENDFOR ENDUSING')
        self.assertEqual((v['TOTAL'],v['SEED']['SLOT']),(3,99))

    def test_independent_private_handler_write_does_not_alias_counter(self):
        v=execute('USING make() DO CONDITION[1]: WHEN EVENT[1] DO slot=99 ENDCONDITION ENDUSING ENABLE CONDITION[1] total=0 USING make() DO FOR slot=1 TO 2 DO SIGNAL EVENT[1] total=total+slot ENDFOR ENDUSING')
        self.assertEqual(v['TOTAL'],3)

    def test_private_timer_keeps_counter_root_protected(self):self.reject('USING make() DO CONNECT TIMER TO child.count FOR slot=1 TO 2 DO ENDFOR ENDUSING','E_FOR_COUNTER')

    def test_private_config_domain_is_still_an_invalid_counter(self):self.reject('USING make_cfg() DO FOR cfg_turn_no1=1 TO 2 DO ENDFOR ENDUSING',routines='ROUTINE make_cfg:CONFIG BEGIN RETURN cfg END make_cfg',decl=DECL+' cfg:CONFIG')

    def test_exact_integer_domain_still_required(self):self.reject('USING VEC(1,2,3) DO FOR x=1 TO 2 DO ENDFOR ENDUSING')

    def test_parameterized_declared_global_and_formal_counter_rules_unchanged(self):
        self.reject('work(1)',routines=MAKE+' ROUTINE work(p:INTEGER) BEGIN FOR i=1 TO 2 DO ENDFOR END work')
        self.reject('work(1)',routines=MAKE+' ROUTINE work(p:INTEGER) BEGIN FOR p=1 TO 2 DO ENDFOR END work')


class PrivateUsingCounterLifetimeTests(unittest.TestCase):
    def test_initial_failure_preserves_private_leaf_and_prior_effects(self):
        for labelled in (False,True):
            p,_=build('USING make() DO slot=9 '+READONLY_HANDLER+'FOR slot=missing_value TO 2 DO ENDFOR ENDUSING',labelled=labelled)
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((retained_root(p).values['SLOT'],p.snapshot()['CALLS']),(9,1))

    def test_final_failure_clears_private_initialized_leaf(self):
        for labelled in (False,True):
            p,_=build('USING make() DO '+READONLY_HANDLER+'FOR slot=1 TO missing_value DO ENDFOR ENDUSING',labelled=labelled)
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertIs(retained_root(p).values['SLOT'],rt.UNINITIALIZED)

    def test_goto_exit_clears_private_leaf_before_target(self):
        v=execute('USING make() DO FOR slot=1 TO 3 DO GOTO done ENDFOR done:: flag=UNINIT(slot) ENDUSING')
        self.assertTrue(v['FLAG'])

    def test_same_loop_backward_jump_retains_private_reference_and_bound(self):
        v=execute('visits=0 total=0 USING make() DO FOR slot=1 TO 2 DO again:: total=total+slot visits=visits+1 IF visits=1 THEN GOTO again ENDIF ENDFOR ENDUSING')
        self.assertEqual((v['TOTAL'],v['VISITS'],v['CALLS']),(4,3,1))

    def test_nested_goto_exit_clears_both_private_counters(self):
        v=execute('USING make() DO FOR slot=1 TO 2 DO USING make() DO FOR slot=1 TO 2 DO GOTO outer_done ENDFOR ENDUSING ENDFOR outer_done:: flag=UNINIT(slot) ENDUSING')
        self.assertTrue(v['FLAG'])

    def test_return_scalar_captures_value_before_private_cleanup(self):
        routines=MAKE+' ROUTINE work:INTEGER BEGIN USING make() DO FOR slot=1 TO 3 DO RETURN slot ENDFOR ENDUSING RETURN 9 END work'
        p,_=build('result=work()',routines=routines);self.assertEqual(p.run()['RESULT'],1)
        self.assertEqual((p._state.call_depth,p._state.local_frames),(0,[]))

    def test_return_record_snapshot_retains_observed_counter_value(self):
        routines=MAKE+' ROUTINE work:row_t BEGIN USING make() DO FOR child.count=1 TO 3 DO RETURN child ENDFOR ENDUSING RETURN seed.child END work'
        v=execute('outcome=work()',decl=DECL+' outcome:row_t',routines=routines)
        self.assertEqual((v['OUTCOME']['COUNT'],v['SEED']['CHILD']['COUNT']),(1,U))

    def test_abort_body_error_and_budget_clear_retained_private_leaf(self):
        cases=(('ABORT',rt.KarelAbort,{}),('result=1 DIV 0',rt.KarelRuntimeError,{}),('again:: GOTO again',rt.KarelRuntimeError,{'max_steps':18}))
        for body,error,options in cases:
            with self.subTest(body=body):
                p,_=build('USING make() DO '+READONLY_HANDLER+'FOR slot=1 TO 2 DO '+body+' ENDFOR ENDUSING')
                with self.assertRaises(error):p.run(**options)
                self.assertIs(retained_root(p).values['SLOT'],rt.UNINITIALIZED)

    def test_pause_resume_retains_counter_and_same_capture(self):
        p,_=build('total=0 USING make() DO FOR slot=1 TO 2 DO total=total+slot IF slot=1 THEN PAUSE ENDIF ENDFOR flag=UNINIT(slot) ENDUSING',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        p._state.values['SEED'].values['SLOT']=99
        v=p.resume();self.assertEqual((v['TOTAL'],v['FLAG'],v['SEED']['SLOT'],v['CALLS']),(3,True,99,1))

    def test_stopping_paused_private_counter_clears_only_selected_leaf(self):
        for labelled in (False,True):
            p,_=build('USING make() DO child.other=9 '+READONLY_HANDLER+'FOR slot=1 TO 2 DO PAUSE ENDFOR ENDUSING',labelled=labelled,cooperative=True)
            with self.assertRaises(rt.KarelPause):p.run()
            root=retained_root(p);self.assertEqual(root.values['SLOT'],1)
            p.stop();self.assertIs(root.values['SLOT'],rt.UNINITIALIZED)
            self.assertEqual(root.values['CHILD'].values['OTHER'],9)
            self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))

    def test_stop_during_initial_expression_preserves_previous_leaf(self):
        routines=MAKE+' ROUTINE first:INTEGER BEGIN PAUSE RETURN 1 END first'
        p,_=build('USING make() DO slot=9 '+READONLY_HANDLER+'FOR slot=first() TO 2 DO ENDFOR ENDUSING',routines=routines,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        root=retained_root(p);p.stop();self.assertEqual(root.values['SLOT'],9)

    def test_stop_during_final_expression_clears_initialized_leaf(self):
        routines=MAKE+' ROUTINE last:INTEGER BEGIN PAUSE RETURN 2 END last'
        p,_=build('USING make() DO '+READONLY_HANDLER+'FOR slot=1 TO last() DO ENDFOR ENDUSING',routines=routines,cooperative=True,labelled=True)
        with self.assertRaises(rt.KarelPause):p.run()
        root=retained_root(p);p.stop();self.assertIs(root.values['SLOT'],rt.UNINITIALIZED)

    def test_jump_into_private_capture_or_for_scope_stays_rejected(self):
        for body,code in (('GOTO inside USING make() DO FOR slot=1 TO 2 DO inside:: ENDFOR ENDUSING','E_GOTO_FOR'),
            ('GOTO inside USING make() DO inside:: FOR slot=1 TO 2 DO ENDFOR ENDUSING','E_GOTO_ENTRY')):
            with self.assertRaises(TranslationError) as caught:build(body)
            self.assertEqual(caught.exception.code,code)


class PrivateUsingCounterReportAndProjectTests(unittest.TestCase):
    def test_reports_keep_private_public_root_null_and_separate_identity(self):
        _,r=build('USING make() DO FOR slot=1 TO 2 DO ENDFOR ENDUSING')
        report=json.loads(json.dumps(r.report));row=report['reference_for_counters'][0]
        self.assertIsNone(row['root']);self.assertEqual(row['provenance'],'private_temporary')
        self.assertTrue(row['protection_root'].startswith('_using_'))
        self.assertEqual(report['using_scopes'][0]['selector_captures'][0]['source_root'],None)
        self.assertFalse(report['private_using_counter_policy']['controller_validated'])

    def test_nested_references_share_identity_independent_copies_do_not(self):
        _,r=build('USING make() DO FOR slot=1 TO 2 DO ENDFOR USING child DO FOR count=1 TO 2 DO ENDFOR ENDUSING USING make() DO FOR slot=1 TO 2 DO ENDFOR ENDUSING ENDUSING')
        keys=[row['protection_root'] for row in r.report['reference_for_counters']]
        self.assertEqual(keys[0],keys[1]);self.assertNotEqual(keys[0],keys[2])

    def test_declared_counter_report_contract_is_unchanged(self):
        _,r=build('FOR i=1 TO 2 DO ENDFOR')
        row=r.report['reference_for_counters'][0]
        self.assertEqual(row['root'],'I');self.assertNotIn('protection_root',row);self.assertNotIn('provenance',row)

    def test_context_json_does_not_publish_private_counter_storage(self):
        p,_=build('USING make() DO FOR slot=1 TO 2 DO PAUSE ENDFOR ENDUSING',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        config=json.loads(json.dumps(p._state.execution.to_config()))
        self.assertTrue(all(not row['path'].startswith('_using_') for row in config.get('variables',[])))
        seed=next(row for row in config['variables'] if row['path']=='SEED')
        self.assertEqual(seed['value']['SLOT'],U);p.stop()

    def test_linked_parameterized_function_owns_private_counter(self):
        sources={'main':'PROGRAM MAIN VAR result:INTEGER ROUTINE work(limit_value:INTEGER):INTEGER FROM LIB BEGIN result=work(3) END MAIN',
            'lib':'PROGRAM LIB TYPE row_t=STRUCTURE count:INTEGER ENDSTRUCTURE VAR seed:row_t ROUTINE make:row_t BEGIN RETURN seed END make ROUTINE work(limit_value:INTEGER):INTEGER VAR subtotal:INTEGER BEGIN subtotal=0 USING make() DO FOR count=1 TO limit_value DO subtotal=subtotal+count ENDFOR ENDUSING RETURN subtotal END work BEGIN END LIB'}
        instance=translate_project(sources).instantiate();v=instance.run('MAIN')
        self.assertEqual((v['MAIN']['values']['RESULT'],v['LIB']['values']['SEED']['COUNT']),(6,U))

    def test_legacy_selector_and_counter_restrictions_preserved(self):
        source='PROGRAM MAIN '+TYPES+' VAR '+DECL+' '+MAKE+' BEGIN USING make() DO FOR slot=1 TO 2 DO ENDFOR ENDUSING END MAIN'
        with self.assertRaises(TranslationError) as caught:legacy_translate(source)
        self.assertEqual(caught.exception.code,'E_USING_TARGET')


if __name__=='__main__':unittest.main()
