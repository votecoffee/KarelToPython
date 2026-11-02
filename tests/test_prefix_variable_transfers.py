"""Authored selected row/plane variable data transfers and publication guards."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_array_prefix_values import build,U,B
from tests.test_kinematic_arrays import values,forward_adapter
from tests.test_kinematic_assignments import callback_context
from tests.test_joint_interoperability import model_context

DECL='m:ARRAY[2,3]OF INTEGER row:ARRAY[3]OF INTEGER e,s,n:INTEGER'


def program(body,*,decl=DECL,**options):return build(body,decl=decl,**options)
def execute(body,**options):return program(body,**options)[0].run()


class PrefixPathGetTests(unittest.TestCase):
    def test_get_selected_row(self):self.assertEqual(execute("m[2,1]=7 GET_VAR(e,'','M[2]',row,s)")['ROW'],[7,U,U])
    def test_get_selected_plane(self):
        v=execute("cube[2,1,2]=7 GET_VAR(e,'','CUBE[2]',plane,s)",decl='cube:ARRAY[2,2,2]OF INTEGER plane:ARRAY[2,2]OF INTEGER e,s:INTEGER');self.assertEqual(v['PLANE'],[[U,7],[U,U]])
    def test_get_cube_row_with_chained_path(self):
        v=execute("cube[2,1,2]=7 GET_VAR(e,'','CUBE[2][1]',row,s)",decl='cube:ARRAY[2,2,2]OF INTEGER row:ARRAY[2]OF INTEGER e,s:INTEGER');self.assertEqual(v['ROW'],[U,7])
    def test_get_named_flat_component_prefix(self):
        v=execute("m[2,1,2]=7 GET_VAR(e,'','M[2][1]',row,s)",types='TYPE plane_t=ARRAY[2,2]OF INTEGER',decl='m:ARRAY[2]OF plane_t row:ARRAY[2]OF INTEGER e,s:INTEGER');self.assertEqual(v['ROW'],[U,7])
    def test_get_nested_record_field_prefix(self):
        v=execute("box.data[1,1]=7 GET_VAR(e,'','BOX.DATA[1]',row,s)",types='TYPE box_t=STRUCTURE data:ARRAY[2,3]OF INTEGER ENDSTRUCTURE',decl='box:box_t row:ARRAY[3]OF INTEGER e,s:INTEGER');self.assertEqual(v['ROW'],[7,U,U])
    def test_chained_complete_element_keeps_scalar_result(self):self.assertEqual(execute("m[2,3]=7 GET_VAR(e,'','M[2][3]',n,s)")['N'],7)
    def test_complete_joint_axis_path_normalizes_all_index_groups(self):
        v=execute("m[2,1][2]=90 GET_VAR(e,'','M[2][1][2]',n,s)",decl='m:ARRAY[2,2]OF JOINTPOS2 n:REAL e,s:INTEGER');self.assertEqual((v['N'],v['S']),(90.,0))
    def test_case_equivalent_path_reuses_cache_id(self):
        p,_=program("m[2,1]=7 GET_VAR(e,'','m[2]',row,s) n=e GET_VAR(e,'','M[2]',row,s)");v=p.run();self.assertEqual((v['E'],v['N']),(1,1));self.assertEqual(len(p._state.execution.entries),1)
    def test_source_and_output_can_overlap_after_snapshot(self):
        v=execute("m[1,1]=7 m[1,2]=9 m[1,3]=11 GET_VAR(e,'','M[1]',m[1],s)");self.assertEqual((v['M'][0],v['S']),([7,9,11],0))


class PrefixPathSetTests(unittest.TestCase):
    def test_set_selected_row(self):self.assertEqual(execute("row[1]=7 SET_VAR(e,'','M[2]',row,s)")['M'][1],[7,U,U])
    def test_set_selected_plane(self):
        v=execute("plane[2,2]=7 SET_VAR(e,'','CUBE[2]',plane,s)",decl='cube:ARRAY[2,2,2]OF INTEGER plane:ARRAY[2,2]OF INTEGER e,s:INTEGER');self.assertEqual(v['CUBE'][1],[[U,U],[U,7]])
    def test_set_chained_cube_row(self):
        v=execute("row[1]=7 SET_VAR(e,'','CUBE[2][1]',row,s)",decl='cube:ARRAY[2,2,2]OF INTEGER row:ARRAY[2]OF INTEGER e,s:INTEGER');self.assertEqual(v['CUBE'][1][0],[7,U])
    def test_set_named_component_suffix_keeps_identity(self):
        p,_=program("row[1]=7 SET_VAR(e,'','M[1]',row,s)",types='TYPE row_t=ARRAY[3]OF INTEGER',decl='m:ARRAY[2]OF row_t row:ARRAY[3]OF INTEGER e,s:INTEGER');self.assertEqual(p.run()['M'][0],[7,U,U]);self.assertEqual(p._state.raw('M').values[0].spec[3],'ROW_T')
    def test_set_prefix_preserves_unselected_rows(self):
        v=execute("m[1,1]=42 row[1]=7 SET_VAR(e,'','M[2]',row,s)");self.assertEqual(v['M'],[[42,U,U],[7,U,U]])
    def test_set_prefix_preserves_receiver_tail(self):
        v=execute("m[2,3]=42 row[1]=7 row[2]=9 SET_VAR(e,'','M[2]',row,s)",decl='m:ARRAY[2,3]OF INTEGER row:ARRAY[2]OF INTEGER e,s:INTEGER');self.assertEqual(v['M'][1],[7,9,42])
    def test_chained_complete_element_set(self):self.assertEqual(execute("n=7 SET_VAR(e,'','M[2][3]',n,s)")['M'][1][2],7)
    def test_nested_record_alias_survives_named_prefix_set(self):
        types='TYPE item_t=STRUCTURE value:INTEGER ENDSTRUCTURE'
        routines="ROUTINE borrow(alias:INTEGER) BEGIN SET_VAR(e,'','M[1]',row,s) n=alias alias=42 END borrow"
        v=execute('m[1,1].value=99 row[1].value=7 borrow(m[1,1].value)',types=types,decl='m:ARRAY[2,2]OF item_t row:ARRAY[2]OF item_t e,s,n:INTEGER',routines=routines);self.assertEqual((v['N'],v['M'][0][0]['VALUE']),(7,42))


class PrefixSourceAndOutputTests(unittest.TestCase):
    def test_get_data_output_prefix(self):self.assertEqual(execute("row[1]=7 GET_VAR(e,'','ROW',m[2],s)")['M'][1],[7,U,U])
    def test_set_source_prefix(self):self.assertEqual(execute("m[2,1]=7 SET_VAR(e,'','ROW',m[2],s)")['ROW'],[7,U,U])
    def test_get_named_source_prefix_into_output_prefix(self):
        v=execute("m[1,1]=7 GET_VAR(e,'','M[1]',m[2],s)");self.assertEqual(v['M'],[[7,U,U],[7,U,U]])
    def test_set_source_prefix_into_named_prefix(self):
        v=execute("m[1,1]=7 SET_VAR(e,'','M[2]',m[1],s)");self.assertEqual(v['M'],[[7,U,U],[7,U,U]])
    def test_set_source_is_captured_before_status_selector(self):
        routines='ROUTINE pick:INTEGER BEGIN m[1,1]=99 RETURN 1 END pick'
        v=execute("m[1,1]=7 SET_VAR(e,'','ROW',m[1],statuses[pick()])",decl=DECL+' statuses:ARRAY[1]OF INTEGER',routines=routines);self.assertEqual((v['M'][0][0],v['ROW'][0]),(99,7))
    def test_get_source_is_captured_after_output_selector(self):
        routines='ROUTINE pick:INTEGER BEGIN row[1]=99 RETURN 2 END pick'
        v=execute("row[1]=7 GET_VAR(e,'','ROW',m[pick()],s)",routines=routines);self.assertEqual(v['M'][1][0],99)
    def test_get_prefix_destination_preserves_unused_tail(self):
        v=execute("m[2,3]=42 row[1]=7 row[2]=9 GET_VAR(e,'','ROW',m[2],s)",decl='m:ARRAY[2,3]OF INTEGER row:ARRAY[2]OF INTEGER e,s:INTEGER');self.assertEqual(v['M'][1],[7,9,42])
    def test_output_prefix_index_evaluates_once(self):
        v=execute("n=0 row[1]=7 GET_VAR(e,'','ROW',m[pick()],s)",routines='ROUTINE pick:INTEGER BEGIN n=n+1 RETURN 2 END pick');self.assertEqual((v['N'],v['M'][1][0]),(1,7))


class PrefixVariableConversionTests(unittest.TestCase):
    def test_numeric_promotion(self):
        v=execute("row[1]=7 GET_VAR(e,'','ROW',m[1],s)",decl='m:ARRAY[2,3]OF REAL row:ARRAY[3]OF INTEGER e,s:INTEGER');self.assertEqual(v['M'][0],[7.,U,U])
    def test_integral_narrowing(self):
        v=execute("row[1]=255 row[2]=0 row[3]=7 SET_VAR(e,'','M[1]',row,s)",decl='m:ARRAY[2,3]OF BYTE row:ARRAY[3]OF INTEGER e,s:INTEGER');self.assertEqual(v['M'][0],[255,0,7])
    def test_string_capacity_conversion(self):
        v=execute("row[1]='abcd' GET_VAR(e,'','ROW',m[1],s)",decl='m:ARRAY[2,2]OF STRING[2] row:ARRAY[2]OF STRING[4] e,s:INTEGER');self.assertEqual(v['M'][0],['ab',U])
    def test_record_schema_conversion(self):
        types='TYPE a_t=STRUCTURE value:INTEGER text:STRING[4] ENDSTRUCTURE b_t=STRUCTURE text:STRING[2] value:REAL ENDSTRUCTURE'
        v=execute("row[1].value=7 row[1].text='abcd' GET_VAR(e,'','ROW',m[1],s)",types=types,decl='m:ARRAY[2,2]OF b_t row:ARRAY[2]OF a_t e,s:INTEGER');self.assertEqual(v['M'][0][0],{'TEXT':'ab','VALUE':7.})
    def test_partial_scalar_transfer_reports_missing(self):
        v=execute("row[1]=7 SET_VAR(e,'','M[1]',row,s)");self.assertEqual((v['M'][0],v['S']),([7,U,U],12311))
    def test_unknown_byte_data_does_not_become_missing(self):
        v=execute("row[1]=7 SET_VAR(e,'','M[1]',row,s)",decl='m:ARRAY[2,3]OF BYTE row:ARRAY[3]OF BYTE e,s:INTEGER');self.assertEqual((v['M'][0],v['S']),([7,B,B],0))
    def test_joint_width_conversion(self):
        p,_=program("GET_VAR(e,'','ROW',m[1],s)",decl='m:ARRAY[2,2]OF JOINTPOS3 row:ARRAY[2]OF JOINTPOS2 e,s:INTEGER');p._state.values['ROW']=values(2);self.assertEqual(p.run()['M'][0][0]['axes'],[0.,90.,0.])
    def test_unsupported_rank_change_returns_status_without_data(self):
        p,_=program("e=77 GET_VAR(e,'','ROW',m[1],s)",decl='m:ARRAY[2,3]OF INTEGER row:ARRAY[1,3]OF INTEGER e,s:INTEGER');v=p.run();self.assertEqual((v['E'],v['S'],v['M'][0]),(77,3,[U,U,U]));self.assertEqual(p._state.execution.entries,{})


class PrefixVariableTransactionTests(unittest.TestCase):
    def test_get_prefix_overlap_with_entry_rejected(self):
        p,_=program("m[1,1]=42 s=88 GET_VAR(m[1,1],'','ROW',m[1],s)")
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['M'][0][0],p.snapshot()['S']),(42,88));self.assertEqual(p._state.execution.entries,{})
    def test_get_prefix_overlap_with_status_rejected(self):
        p,_=program("e=77 m[1,1]=42 GET_VAR(e,'','ROW',m[1],m[1,1])")
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['E'],p.snapshot()['M'][0][0]),(77,42))
    def test_named_set_prefix_overlap_rejected(self):
        p,_=program("m[2,1]=42 SET_VAR(m[2,1],'','M[2]',row,s)")
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['M'][1][0],42);self.assertEqual(p._state.execution.entries,{})
    def test_metadata_outside_selected_prefix_is_allowed(self):
        v=execute("row[1]=7 row[2]=9 row[3]=11 SET_VAR(m[1,1],'','M[2]',row,m[1,2])");self.assertEqual(v['M'],[[1,0,U],[7,9,11]])
    def test_bad_last_narrow_value_preserves_data_metadata_cache(self):
        p,_=program("e=77 s=88 m[1,1]=42 row[1]=7 row[2]=256 SET_VAR(e,'','M[1]',row,s)",decl='m:ARRAY[2,2]OF BYTE row:ARRAY[2]OF INTEGER e,s:INTEGER')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        v=p.snapshot();self.assertEqual((v['M'][0],v['E'],v['S']),([42,B],77,88));self.assertEqual(p._state.execution.entries,{})
    def test_missing_container_cannot_replace_shaped_prefix(self):
        ctx=rt.ExecutionContext();ctx.variables.bind('OTHER','SOURCE',rt.Reference(('ARRAY',3,rt.INTEGER),{'value':rt.UNINITIALIZED},'value'))
        p,_=program("e=77 s=88 m[1,1]=42 GET_VAR(e,'OTHER','SOURCE',m[1],s)",context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        v=p.snapshot();self.assertEqual((v['M'][0],v['E'],v['S']),([42,U,U],77,88));self.assertEqual(ctx.entries,{})
    def test_failed_output_index_skips_lookup_and_cache(self):
        p,_=program("e=77 s=88 GET_VAR(e,'','ROW',m[0],s)")
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['E'],p.snapshot()['S']),(77,88));self.assertEqual(p._state.execution.entries,{})
    def test_lookup_failure_changes_status_only(self):
        p,_=program("e=77 s=88 GET_VAR(e,'','M[0]',row,s)");v=p.run();self.assertEqual((v['E'],v['S'],v['ROW']),(77,1,[U,U,U]));self.assertEqual(p._state.execution.entries,{})


class PrefixVariableModelTests(unittest.TestCase):
    def make(self,body="GET_VAR(e,'','ROW',m[1],s)",*,context=None,first='JOINTPOS2',second='XYZWPR'):
        p,r=program(body,decl=f'm:ARRAY[2,2]OF {second} row:ARRAY[2]OF {first} e,s,n:INTEGER',context=context if context is not None else model_context((0.,90.)))
        p._state.values['ROW']=values(2 if first=='JOINTPOS2' else first);return p,r
    def test_forward_into_prefix_with_configured_model(self):
        p,_=self.make();self.assertAlmostEqual(p.run()['M'][0][0]['X'],100.,places=8)
    def test_inverse_into_named_prefix(self):
        p,_=self.make("SET_VAR(e,'','M[1]',row,s)",first='XYZWPR',second='JOINTPOS2');self.assertEqual(p.run()['M'][0][0]['axes'],[0.,90.])
    def test_named_prefix_source_uses_model_conversion(self):
        p,_=self.make("GET_VAR(e,'','M[1]',row,s)",first='XYZWPR',second='JOINTPOS2');p._state.raw('M').values[:2]=values(2).values;self.assertAlmostEqual(p.run()['ROW'][0]['X'],100.,places=8)
    def test_missing_model_retains_status_three(self):
        p,_=self.make(context=rt.ExecutionContext());v=p.run();self.assertEqual((v['S'],v['M'][0][0]['X']),(3,U));self.assertEqual(p._state.execution.entries,{})
    def test_late_adapter_failure_preserves_cache_and_prefix(self):
        calls=[]
        def forward(*args):
            result=forward_adapter(calls)(*args)
            if len(calls)==2:raise ValueError('authored late conversion failure')
            return result
        p,_=self.make("e=77 s=88 GET_VAR(e,'','ROW',m[1],s)",context=callback_context(forward=forward))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((len(calls),p.snapshot()['E'],p.snapshot()['S'],p.snapshot()['M'][0][0]['X']),(2,77,88,U));self.assertEqual(p._state.execution.entries,{})
    def test_adapter_root_replacement_keeps_captured_cells(self):
        calls=[];p=None
        def forward(*args):p._state.values['M']=rt.Array(p._state.types['M']);return forward_adapter(calls)(*args)
        p,_=self.make(context=callback_context(forward=forward));old=p._state.raw('M');v=p.run();self.assertEqual(v['M'][0][0]['X'],U);self.assertEqual(old.snapshot()[0][0]['X'],1.)
    def test_adapter_changed_receiver_tail_is_retained(self):
        calls=[];p=None
        def forward(*args):p._state.raw('M').values[2].values['X']=42.;return forward_adapter(calls)(*args)
        p,_=self.make(context=callback_context(forward=forward));v=p.run();self.assertEqual(v['M'][1][0]['X'],42.)
    def test_adapter_created_metadata_overlap_is_rechecked(self):
        calls=[];p=None
        def forward(*args):
            if not calls:p._state.raw('M').values[0]=p._state.raw('M').values[2]
            return forward_adapter(calls)(*args)
        types='TYPE a_t=STRUCTURE number:INTEGER point:JOINTPOS2 ENDSTRUCTURE b_t=STRUCTURE number:INTEGER point:XYZWPR ENDSTRUCTURE'
        p,_=program("m[2,1].number=77 s=88 GET_VAR(m[2,1].number,'','ROW',m[1],s)",types=types,decl='m:ARRAY[2,2]OF b_t row:ARRAY[2]OF a_t s:INTEGER',context=callback_context(forward=forward))
        for index,item in enumerate(p._state.raw('ROW').values):item.values.update(NUMBER=7,POINT=values(2).values[index])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual((p.snapshot()['M'][0][0]['NUMBER'],p.snapshot()['S']),(77,88));self.assertEqual(p._state.execution.entries,{})
    def test_adapter_invalidated_prefix_storage_allocates_no_cache(self):
        calls=[];p=None
        def forward(*args):
            if not calls:p._state.raw('M').values.pop()
            return forward_adapter(calls)(*args)
        p,_=self.make("e=77 s=88 GET_VAR(e,'','ROW',m[1],s)",context=callback_context(forward=forward))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p._state.values['E'],p._state.values['S']),(77,88));self.assertEqual(p._state.execution.entries,{})


class PrefixVariableScopeTests(unittest.TestCase):
    def test_explicit_root_binding_prefix(self):
        ctx=rt.ExecutionContext();a=rt.Array(('ARRAY',(2,3),rt.INTEGER));a.set((2,1),7);ctx.variables.define('OTHER','ROOT',a.spec,a)
        v=execute("GET_VAR(e,'OTHER','ROOT[2]',row,s)",context=ctx);self.assertEqual(v['ROW'],[7,U,U])
    def test_explicit_system_root_prefix(self):
        ctx=rt.ExecutionContext();a=rt.Array(('ARRAY',(2,3),rt.INTEGER));a.set((1,1),7);ctx.variables.define('SYSTEM','$GRID',a.spec,a)
        self.assertEqual(execute("GET_VAR(e,'SYSTEM','$GRID[1]',row,s)",context=ctx)['ROW'],[7,U,U])
    def test_exact_full_path_binding_keeps_precedence(self):
        ctx=rt.ExecutionContext();a=rt.Array(('ARRAY',3,rt.INTEGER));a.set(1,42);ctx.variables.define('OTHER','ROOT[1]',a.spec,a)
        self.assertEqual(execute("GET_VAR(e,'OTHER','ROOT[1]',row,s)",context=ctx)['ROW'],[42,U,U])
    def test_linked_routine_can_update_caller_prefix(self):
        main="PROGRAM MAIN VAR m:ARRAY[2,3]OF INTEGER row:ARRAY[3]OF INTEGER e,s:INTEGER ROUTINE fill FROM LIB BEGIN row[1]=7 fill END MAIN"
        lib="PROGRAM LIB VAR temp:ARRAY[3]OF INTEGER e,s:INTEGER ROUTINE fill BEGIN GET_VAR(e,'MAIN','ROW',temp,s) SET_VAR(e,'MAIN','M[2]',temp,s) END fill BEGIN END LIB"
        p=translate_project({'main':main,'lib':lib}).instantiate();p.run('MAIN');self.assertEqual(p.programs['MAIN'].snapshot()['M'][1],[7,U,U])
    def test_pause_in_output_index_does_not_replay(self):
        p,_=program("n=0 row[1]=7 GET_VAR(e,'','ROW',m[pick()],s)",cooperative=True,routines='ROUTINE pick:INTEGER BEGIN n=n+1 PAUSE RETURN 2 END pick')
        with self.assertRaises(rt.KarelPause):p.run()
        v=p.resume();self.assertEqual((v['N'],v['M'][1][0]),(1,7))
    def test_saved_context_has_data_without_prefix_bindings(self):
        p,_=program("row[1]=7 SET_VAR(e,'','M[1]',row,s)");p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertFalse(any('[' in row['path'] for row in saved.get('variables',[])));self.assertEqual(restored.to_config(),saved)
    def test_default_resolver_and_byname_remain_complete(self):
        p,_=program("e=77 work(BYNAME('','M[1]',e))",routines='ROUTINE work(p:ARRAY OF INTEGER) BEGIN END work')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['E'],77)
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):p._state.execution.resolve(p._state,'','M[1]')
    def test_cache_key_retains_original_bracket_spelling(self):
        p,_=program("m[1,1]=7 GET_VAR(e,'','M[1][1]',n,s) GET_VAR(e,'','M[1,1]',n,s)");p.run();self.assertEqual(len(p._state.execution.entries),2)


class PrefixVariableGuardTests(unittest.TestCase):
    def reject(self,body,code,**options):
        with self.assertRaises(TranslationError) as caught:program(body,**options)
        self.assertEqual(caught.exception.code,code,str(caught.exception))
    def test_other_service_outputs_remain_complete(self):self.reject("CNV_STR_INT('7',m[1])",'E_ARRAY_RANK')
    def test_get_prefix_output_cannot_write_active_counter_root(self):self.reject("FOR m[1,1]=1 TO 2 DO GET_VAR(e,'','ROW',m[2],s) ENDFOR",'E_FOR_COUNTER')
    def test_set_indirect_prefix_cannot_write_active_counter(self):self.reject("FOR n=1 TO 2 DO SET_VAR(e,'','M[1]',row,s) ENDFOR",'E_FOR_COUNTER')
    def test_partial_prefix_followed_by_field_is_not_a_record(self):
        v=execute("e=77 GET_VAR(e,'','M[1].VALUE',row,s)");self.assertEqual((v['E'],v['S']),(77,1))
    def test_too_many_chained_indexes_rejects_lookup(self):
        v=execute("e=77 GET_VAR(e,'','M[1][1][1]',row,s)");self.assertEqual((v['E'],v['S']),(77,1))
    def test_quoted_paths_do_not_evaluate_expressions(self):
        v=execute("n=0 GET_VAR(e,'','M[n+1]',row,s)");self.assertEqual((v['N'],v['S']),(0,1))
    def test_variable_store_rejects_live_prefix_bindings(self):
        p,_=program('');
        with rt._numeric_scope('pythonic'):
            target=rt.array_prefix_target(p._state.raw('M'),1,p._state.types['M'])
            with self.assertRaises(TypeError):p._state.execution.variables.bind('OTHER','ROW',target)
            from karel2py.extended import outputs_checked
            with self.assertRaises(rt.KarelRuntimeError):outputs_checked((('o','VARIABLE'),),[target])
    def test_report_records_specific_transfer_extension(self):
        _,r=program("GET_VAR(e,'','ROW',m[1],s)");self.assertFalse(r.report['prefix_variable_transfer_policy']['controller_validated']);self.assertTrue(r.report['array_prefix_targets']);json.dumps(r.report)
