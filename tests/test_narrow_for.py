"""Authored checked BYTE/SHORT counters across capture, effects and cleanup."""
import json
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


U={'uninitialized':True}
B={'unknown_byte':True}
TYPES='TYPE row_t=STRUCTURE code:BYTE signed:SHORT other:INTEGER ENDSTRUCTURE box_t=STRUCTURE child:row_t ENDSTRUCTURE'
DECL='b:BYTE s:SHORT row,saved:row_t box:box_t bytes:ARRAY[2] OF BYTE shorts:ARRAY[2] OF SHORT i,index_value,total,result,calls,visits,missing_value,status:INTEGER flag:BOOLEAN number:REAL'


def build(body,*,labelled=False,decl=DECL,types=TYPES,routines='',cooperative=False,**options):
    r=translate('PROGRAM MAIN '+types+' VAR '+decl+' '+routines+' BEGIN '+('unused:: ' if labelled else '')+body+' END MAIN',cooperative=cooperative)
    ns={'__name__':'narrow_for_test'};exec(r.python_source,ns)
    return ns['Program'](**options),r


def execute(body,**options):return build(body,**options)[0].run()


class NarrowForStorageTests(unittest.TestCase):
    def parity(self,body,**options):
        states=[execute(body,labelled=labelled,**options) for labelled in (False,True)]
        self.assertEqual(states[0],states[1]);return states[0]

    def test_global_byte_counter_totals_and_clears_to_unknown(self):
        v=self.parity('total=0 FOR b=1 TO 3 DO total=total+b ENDFOR')
        self.assertEqual((v['TOTAL'],v['B']),(6,B))

    def test_global_short_counter_includes_negative_values(self):
        v=self.parity('total=0 FOR s=-2 TO 2 DO total=total+s ENDFOR flag=UNINIT(s)')
        self.assertEqual((v['TOTAL'],v['S'],v['FLAG']),(0,U,True))

    def test_byte_upper_boundary_does_not_write_256(self):
        v=self.parity('total=0 FOR b=254 TO 255 DO total=total+b ENDFOR')
        self.assertEqual((v['TOTAL'],v['B']),(509,B))

    def test_byte_lower_boundary_does_not_write_minus_one(self):
        v=self.parity('total=0 FOR b=1 DOWNTO 0 DO total=total+b ENDFOR')
        self.assertEqual((v['TOTAL'],v['B']),(1,B))

    def test_short_upper_boundary_does_not_store_sentinel(self):
        v=self.parity('total=0 FOR s=32765 TO 32766 DO total=total+s ENDFOR')
        self.assertEqual((v['TOTAL'],v['S']),(65531,U))

    def test_short_lower_boundary_does_not_write_below_domain(self):
        v=self.parity('total=0 FOR s=-32767 DOWNTO -32768 DO total=total+s ENDFOR')
        self.assertEqual((v['TOTAL'],v['S']),(-65535,U))

    def test_zero_iteration_loops_still_check_and_clear(self):
        v=self.parity('total=7 FOR b=3 TO 1 DO total=99 ENDFOR FOR s=1 DOWNTO 3 DO total=99 ENDFOR')
        self.assertEqual((v['TOTAL'],v['B'],v['S']),(7,B,U))

    def test_narrow_record_fields_preserve_unrelated_storage(self):
        v=self.parity('row.other=9 total=0 FOR row.code=1 TO 2 DO total=total+row.code ENDFOR FOR row.signed=-1 TO 1 DO total=total+row.signed ENDFOR')
        self.assertEqual((v['TOTAL'],v['ROW']),(3,{'CODE':B,'SIGNED':U,'OTHER':9}))

    def test_array_element_keeps_one_captured_index(self):
        v=self.parity('index_value=1 bytes[2]=99 total=0 FOR bytes[index_value]=1 TO 3 DO index_value=2 total=total+bytes[1] ENDFOR')
        self.assertEqual((v['TOTAL'],v['BYTES']),(6,[B,99]))

    def test_nested_alias_types_are_supported(self):
        v=self.parity('total=0 FOR narrow=1 TO 2 DO total=total+narrow ENDFOR',types='TYPE octet_t=BYTE alias_t=octet_t',decl='narrow:alias_t total:INTEGER')
        self.assertEqual((v['TOTAL'],v['NARROW']),(3,B))

    def test_named_using_fields_retain_original_storage(self):
        v=self.parity('total=0 USING row DO FOR code=1 TO 2 DO total=total+code ENDFOR ENDUSING')
        self.assertEqual((v['TOTAL'],v['ROW']['CODE']),(3,B))

    def test_private_using_counter_cleans_only_private_leaf(self):
        v=self.parity('box.child.code=99 total=0 USING make() DO FOR child.code=1 TO 3 DO total=total+child.code ENDFOR saved=child ENDUSING',
            routines='ROUTINE make:box_t BEGIN RETURN box END make')
        self.assertEqual((v['TOTAL'],v['SAVED']['CODE'],v['BOX']['CHILD']['CODE']),(6,B,99))

    def test_nested_private_reference_counter_shares_capture(self):
        v=self.parity('total=0 USING make() DO USING child DO FOR signed=-1 TO 1 DO total=total+signed ENDFOR ENDUSING saved=child ENDUSING',
            routines='ROUTINE make:box_t BEGIN RETURN box END make')
        self.assertEqual((v['TOTAL'],v['SAVED']['SIGNED']),(0,U))

    def test_independent_private_copies_can_nest_narrow_counters(self):
        routine='ROUTINE make:row_t BEGIN RETURN row END make'
        v=self.parity('total=0 USING make() DO FOR code=1 TO 2 DO USING make() DO FOR signed=1 TO 2 DO total=total+signed ENDFOR ENDUSING ENDFOR ENDUSING',routines=routine)
        self.assertEqual(v['TOTAL'],6)

    def test_parameterized_routine_can_use_fresh_local_narrow_root(self):
        routine='ROUTINE work(limit_value:INTEGER):INTEGER VAR counter:BYTE subtotal:INTEGER BEGIN subtotal=0 FOR counter=1 TO limit_value DO subtotal=subtotal+counter ENDFOR RETURN subtotal END work'
        self.assertEqual(self.parity('result=work(3)',routines=routine)['RESULT'],6)

    def test_parameterized_routine_can_use_private_narrow_capture(self):
        routines='ROUTINE make:row_t BEGIN RETURN row END make ROUTINE work(limit_value:INTEGER):INTEGER VAR subtotal:INTEGER BEGIN subtotal=0 USING make() DO FOR code=1 TO limit_value DO subtotal=subtotal+code ENDFOR ENDUSING RETURN subtotal END work'
        self.assertEqual(self.parity('result=work(3)',routines=routines)['RESULT'],6)

    def test_selector_function_runs_once_before_initial_expression(self):
        routines='ROUTINE pick:INTEGER BEGIN calls=calls*10+1 RETURN index_value END pick ROUTINE first:INTEGER BEGIN calls=calls*10+2 index_value=2 RETURN 1 END first'
        v=self.parity('calls=0 index_value=1 bytes[2]=99 FOR bytes[pick()]=first() TO 2 DO ENDFOR',routines=routines)
        self.assertEqual((v['CALLS'],v['BYTES']),(12,[B,99]))

    def test_final_expression_reads_initial_counter_once(self):
        v=self.parity('total=0 FOR b=2 TO b+2 DO total=total+b ENDFOR')
        self.assertEqual(v['TOTAL'],9)


class NarrowForBoundsAndLifetimeTests(unittest.TestCase):
    def test_invalid_initial_bounds_preserve_previous_cell(self):
        for name,value in (('b',-1),('b',256),('s',-32769),('s',32767)):
            for labelled in (False,True):
                with self.subTest(name=name,value=value,labelled=labelled):
                    p,_=build(f'{name}=9 FOR {name}={value} TO 2 DO result=99 ENDFOR',labelled=labelled)
                    with self.assertRaises(rt.KarelRuntimeError):p.run()
                    self.assertEqual((p.snapshot()[name.upper()],p.snapshot()['RESULT']),(9,U))

    def test_invalid_final_bounds_clear_initialized_cell(self):
        for name,value,marker in (('b',-1,B),('b',256,B),('s',-32769,U),('s',32767,U)):
            for labelled in (False,True):
                with self.subTest(name=name,value=value,labelled=labelled):
                    p,_=build(f'{name}=9 FOR {name}=1 TO {value} DO result=99 ENDFOR',labelled=labelled)
                    with self.assertRaises(rt.KarelRuntimeError):p.run()
                    self.assertEqual((p.snapshot()[name.upper()],p.snapshot()['RESULT']),(marker,U))

    def test_outside_domain_final_rejects_even_when_loop_would_be_empty(self):
        p,_=build('b=9 FOR b=255 TO -1 DO ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],B)

    def test_initial_function_effects_remain_before_domain_rejection(self):
        p,_=build('calls=0 s=9 FOR s=first() TO 2 DO ENDFOR',routines='ROUTINE first:INTEGER BEGIN calls=calls+1 RETURN 32767 END first')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['CALLS'],p.snapshot()['S']),(1,9))

    def test_final_function_effects_remain_before_cleanup(self):
        p,_=build('calls=0 b=9 FOR b=1 TO last() DO ENDFOR',routines='ROUTINE last:INTEGER BEGIN calls=calls+1 RETURN 256 END last')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['CALLS'],p.snapshot()['B']),(1,B))

    def test_initial_uninitialized_expression_preserves_previous_cell(self):
        p,_=build('b=9 FOR b=missing_value TO 2 DO ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],9)

    def test_final_uninitialized_expression_clears_cell(self):
        p,_=build('s=9 FOR s=1 TO missing_value DO ENDFOR')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['S'],U)

    def test_same_loop_jump_retains_narrow_counter_and_bounds(self):
        v=execute('total=0 visits=0 FOR b=1 TO 2 DO again:: total=total+b visits=visits+1 IF visits=1 THEN GOTO again ENDIF ENDFOR')
        self.assertEqual((v['TOTAL'],v['VISITS'],v['B']),(4,3,B))

    def test_goto_exit_clears_nested_narrow_counters_inner_to_outer(self):
        v=execute('FOR b=1 TO 2 DO FOR s=1 TO 2 DO GOTO done ENDFOR ENDFOR done:: result=42')
        self.assertEqual((v['B'],v['S'],v['RESULT']),(B,U,42))

    def test_return_scalar_is_captured_before_cleanup(self):
        routine='ROUTINE work:BYTE BEGIN FOR b=1 TO 2 DO RETURN b ENDFOR RETURN 9 END work'
        v=execute('result=work()',routines=routine)
        self.assertEqual((v['RESULT'],v['B']),(1,B))

    def test_return_aggregate_snapshot_preserves_observed_counter(self):
        routine='ROUTINE work:row_t BEGIN FOR row.code=1 TO 2 DO RETURN row ENDFOR RETURN row END work'
        v=execute('saved=work()',routines=routine)
        self.assertEqual((v['SAVED']['CODE'],v['ROW']['CODE']),(1,B))

    def test_abort_and_body_error_clear_narrow_counters(self):
        for body,error in (('ABORT',rt.KarelAbort),('result=1 DIV 0',rt.KarelRuntimeError)):
            for labelled in (False,True):
                p,_=build('FOR b=1 TO 2 DO FOR s=1 TO 2 DO '+body+' ENDFOR ENDFOR',labelled=labelled)
                with self.assertRaises(error):p.run()
                self.assertEqual((p.snapshot()['B'],p.snapshot()['S']),(B,U))

    def test_budget_exhaustion_clears_byte_to_unknown(self):
        p,_=build('FOR b=1 TO 2 DO again:: GOTO again ENDFOR')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=12)
        self.assertEqual(p.snapshot()['B'],B)

    def test_pause_resume_keeps_selected_narrow_element(self):
        p,_=build('index_value=1 total=0 bytes[2]=99 FOR bytes[index_value]=1 TO 2 DO total=total+bytes[1] index_value=2 IF bytes[1]=1 THEN PAUSE ENDIF ENDFOR',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['BYTES'],[1,99])
        v=p.resume();self.assertEqual((v['TOTAL'],v['BYTES']),(3,[B,99]))

    def test_stop_clears_paused_narrow_counter_in_both_engines(self):
        for labelled in (False,True):
            p,_=build('FOR b=1 TO 2 DO FOR s=1 TO 2 DO PAUSE ENDFOR ENDFOR',labelled=labelled,cooperative=True)
            with self.assertRaises(rt.KarelPause):p.run()
            p.stop();self.assertEqual((p.snapshot()['B'],p.snapshot()['S'],p._state.call_depth),(B,U,0))

    def test_stop_during_initial_bound_keeps_previous_short(self):
        p,_=build('s=9 FOR s=first() TO 2 DO ENDFOR',cooperative=True,routines='ROUTINE first:INTEGER BEGIN PAUSE RETURN 1 END first')
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(p.snapshot()['S'],9)

    def test_stop_during_final_bound_clears_byte(self):
        p,_=build('b=9 FOR b=1 TO last() DO ENDFOR',cooperative=True,labelled=True,routines='ROUTINE last:INTEGER BEGIN PAUSE RETURN 2 END last')
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(p.snapshot()['B'],B)


class NarrowForProtectionTests(unittest.TestCase):
    def reject(self,body,code='E_FOR_COUNTER',**options):
        for labelled in (False,True):
            with self.assertRaises(TranslationError) as caught:build(body,labelled=labelled,**options)
            self.assertEqual(caught.exception.code,code,str(caught.exception))

    def test_direct_active_counter_write_is_rejected(self):self.reject('FOR b=1 TO 2 DO b=99 ENDFOR')

    def test_whole_record_root_remains_protected(self):self.reject('FOR row.code=1 TO 2 DO row.other=99 ENDFOR')

    def test_array_root_rejects_writes_to_other_cells(self):self.reject('FOR bytes[1]=1 TO 2 DO bytes[2]=99 ENDFOR')

    def test_nested_same_root_narrow_counters_are_rejected(self):self.reject('FOR row.code=1 TO 2 DO FOR row.signed=1 TO 2 DO ENDFOR ENDFOR')

    def test_matching_writable_narrow_formal_is_rejected(self):self.reject('FOR b=1 TO 2 DO edit(b) ENDFOR',routines='ROUTINE edit(p:BYTE) BEGIN p=99 END edit')

    def test_matching_readonly_narrow_formal_observes_counter(self):
        v=execute('total=0 FOR b=1 TO 3 DO observe(b) ENDFOR',routines='ROUTINE observe(p:BYTE) BEGIN total=total+p END observe')
        self.assertEqual(v['TOTAL'],6)

    def test_integer_real_and_mismatched_narrow_formals_are_detached(self):
        for formal in ('INTEGER','REAL','SHORT'):
            with self.subTest(formal=formal):
                v=execute('total=0 FOR b=1 TO 3 DO edit(b) total=total+b ENDFOR',routines='ROUTINE edit(p:'+formal+') BEGIN p=99 END edit')
                self.assertEqual((v['TOTAL'],v['B']),(6,B))

    def test_transitive_matching_alias_write_is_rejected(self):self.reject('FOR s=1 TO 2 DO relay(s) ENDFOR',routines='ROUTINE edit(p:SHORT) BEGIN p=99 END edit ROUTINE relay(p:SHORT) BEGIN edit(p) END relay')

    def test_transitive_detached_narrow_promotion_is_safe(self):
        v=execute('total=0 FOR b=1 TO 3 DO relay(b) total=total+b ENDFOR',routines='ROUTINE edit(p:INTEGER) BEGIN p=99 END edit ROUTINE relay(p:BYTE) BEGIN edit(p) END relay')
        self.assertEqual(v['TOTAL'],6)

    def test_global_write_from_detached_callee_is_still_rejected(self):self.reject('FOR b=1 TO 2 DO edit(b) ENDFOR',routines='ROUTINE edit(p:INTEGER) BEGIN b=99 END edit')

    def test_narrow_global_is_scalar_for_unknown_no_argument_external(self):
        seen=[];context=rt.ExecutionContext(externals={('LIB','WORK'):lambda:seen.append(1)})
        v=execute('total=0 FOR b=1 TO 2 DO work total=total+b ENDFOR',routines='ROUTINE work FROM LIB',context=context)
        self.assertEqual((v['TOTAL'],seen),(3,[1,1]))

    def test_narrow_field_root_still_rejects_unknown_external(self):self.reject('FOR row.code=1 TO 2 DO work ENDFOR',routines='ROUTINE work FROM LIB')

    def test_handler_direct_and_conversion_writes_are_rejected(self):
        for action in ('b=99',"GET_VAR(i,'MAIN','RESULT',b,status)"):
            self.reject('CONDITION[1]: WHEN EVENT[1] DO '+action+' ENDCONDITION FOR b=1 TO 2 DO ENDFOR')

    def test_handler_matching_alias_write_is_rejected(self):self.reject('CONDITION[1]: WHEN EVENT[1] DO edit(s) ENDCONDITION FOR s=1 TO 2 DO ENDFOR',routines='ROUTINE edit(p:SHORT) BEGIN p=99 END edit')

    def test_private_retained_matching_narrow_alias_is_rejected(self):
        routines='ROUTINE make:row_t BEGIN RETURN row END make ROUTINE retain(p:BYTE) BEGIN CONDITION[1]: WHEN EVENT[1] DO p=99 ENDCONDITION END retain'
        self.reject('USING make() DO retain(code) FOR code=1 TO 2 DO ENDFOR ENDUSING',routines=routines)

    def test_parameterized_formal_and_global_roots_remain_rejected(self):
        self.reject('work(b)',routines='ROUTINE work(p:BYTE) BEGIN FOR p=1 TO 2 DO ENDFOR END work')
        self.reject('work(1)',routines='ROUTINE work(p:INTEGER) BEGIN FOR b=1 TO 2 DO ENDFOR END work')

    def test_real_boolean_counter_and_real_bound_remain_rejected(self):
        self.reject('FOR number=1 TO 2 DO ENDFOR')
        self.reject('FOR flag=1 TO 2 DO ENDFOR')
        self.reject('FOR b=1.0 TO 2 DO ENDFOR','E_TYPE')

    def test_byte_uninit_query_remains_prohibited_after_loop(self):self.reject('FOR b=1 TO 2 DO ENDFOR flag=UNINIT(b)','E_BYTE_UNINIT')

    def test_direct_entry_to_narrow_loop_remains_rejected(self):self.reject('GOTO inside FOR b=1 TO 2 DO inside:: ENDFOR','E_GOTO_FOR')


class NarrowForRuntimeAndIntegrationTests(unittest.TestCase):
    def test_wrapper_checked_short_write_preserves_prior_cell_on_sentinel(self):
        with rt._numeric_scope('pythonic'):
            storage={'value':9};counter=rt.NarrowForCounter(rt.Reference(rt.SHORT,storage,'value'))
            with self.assertRaises(rt.KarelRuntimeError):counter.set(32767,42)
            self.assertEqual(storage['value'],9);counter.clear();self.assertIs(storage['value'],rt.UNINITIALIZED)

    def test_wrapper_byte_cleanup_is_local_and_generic_clear_unchanged(self):
        with rt._numeric_scope('pythonic'):
            storage={'one':9,'two':7};reference=rt.Reference(rt.BYTE,storage,'one');counter=rt.NarrowForCounter(reference)
            counter.clear();self.assertIs(storage['one'],rt.UNKNOWN_BYTE);self.assertEqual(storage['two'],7)
            reference.clear();self.assertIs(storage['one'],rt.UNINITIALIZED)

    def test_wrapper_rejects_legacy_and_nonordinary_references(self):
        reference=rt.Reference(rt.BYTE,{'value':9},'value')
        with self.assertRaises(rt.KarelRuntimeError):rt.NarrowForCounter(reference)
        with rt._numeric_scope('pythonic'):
            for reference in (None,rt.Reference(rt.REAL,{'value':1.},'value'),rt.ReadOnlyFieldReference(rt.BYTE,{'value':9},'value')):
                with self.assertRaises(rt.KarelRuntimeError):rt.NarrowForCounter(reference)

    def test_bound_helper_rejects_wrong_types_and_short_marker(self):
        for spec,value in ((rt.BYTE,-1),(rt.BYTE,256),(rt.SHORT,32767),(rt.SHORT,-32769),(rt.BYTE,True),(rt.SHORT,1.0),(rt.BYTE,rt.UNKNOWN_BYTE)):
            with self.assertRaises(rt.KarelRuntimeError):rt.for_bound(spec,value,42)
        self.assertEqual(rt.for_bound(rt.BYTE,255),255)

    def test_counter_report_records_domain_and_cleanup_without_changing_integer_rows(self):
        _,r=build('FOR b=1 TO 2 DO ENDFOR FOR s=1 TO 2 DO ENDFOR FOR i=1 TO 2 DO ENDFOR')
        rows=json.loads(json.dumps(r.report))['reference_for_counters']
        self.assertEqual([row.get('cleanup_marker') for row in rows],['unknown_byte','uninitialized',None])
        self.assertEqual(rows[0]['bound_domain'],[0,255]);self.assertEqual(rows[1]['counter_type'],['SHORT'])

    def test_context_roundtrip_keeps_unknown_byte_and_short_markers(self):
        p,_=build('FOR b=1 TO 2 DO ENDFOR FOR s=1 TO 2 DO ENDFOR');p.run()
        context=rt.ExecutionContext.from_config(json.loads(json.dumps(p._state.execution.to_config())))
        q,_=build('result=42',context=context)
        v=q.run();self.assertEqual((v['B'],v['S'],v['RESULT']),(B,U,42))

    def test_linked_parameterized_routine_uses_fresh_byte_counter(self):
        sources={'main':'PROGRAM MAIN VAR result:INTEGER ROUTINE work(limit_value:INTEGER):INTEGER FROM LIB BEGIN result=work(3) END MAIN',
            'lib':'PROGRAM LIB ROUTINE work(limit_value:INTEGER):INTEGER VAR count:BYTE total:INTEGER BEGIN total=0 FOR count=1 TO limit_value DO total=total+count ENDFOR RETURN total END work BEGIN END LIB'}
        instance=translate_project(sources).instantiate();self.assertEqual(instance.run('MAIN')['MAIN']['values']['RESULT'],6)

    def test_legacy_narrow_field_counter_remains_rejected(self):
        with self.assertRaises(TranslationError):legacy_translate('PROGRAM MAIN '+TYPES+' VAR row:row_t BEGIN FOR row.code=1 TO 2 DO ENDFOR END MAIN')


if __name__=='__main__':unittest.main()
