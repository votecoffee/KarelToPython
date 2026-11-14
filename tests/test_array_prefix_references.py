"""Authored explicit live data rows/planes; ordinary prefix values stay private."""
import json
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_array_prefix_values import build,U,B
from tests.legacy_numeric_support import translate as legacy_translate

DECL='m:ARRAY[2,2]OF INTEGER row:ARRAY[2]OF INTEGER e,s,n:INTEGER'
PUT='ROUTINE put(x:ARRAY OF INTEGER) BEGIN x[1]=7 x[2]=9 END put'
CALL="put(BYNAME('','M[1]',e))"


def program(body=CALL,*,routines=PUT,decl=DECL,**options):return build(body,routines=routines,decl=decl,**options)
def execute(body=CALL,**options):return program(body,**options)[0].run()


class LivePrefixSourceTests(unittest.TestCase):
    def test_row_writes_original(self):self.assertEqual(execute()['M'],[[7,9],[U,U]])
    def test_fixed_formal_spelling_borrows_matching_row(self):
        self.assertEqual(execute(routines=PUT.replace('ARRAY OF','ARRAY[2]OF'))['M'][0],[7,9])
    def test_generic_spelling(self):self.assertEqual(execute(routines=PUT.replace('ARRAY OF','ARRAY[*]OF'))['M'][0],[7,9])
    def test_selected_row_only(self):self.assertEqual(execute("m[1,1]=42 put(BYNAME('','M[2]',e))")['M'],[[42,U],[7,9]])
    def test_lowercase_path(self):self.assertEqual(execute("put(BYNAME('','m[1]',e))")['M'][0],[7,9])
    def test_explicit_program(self):self.assertEqual(execute("put(BYNAME('MAIN','M[1]',e))")['M'][0],[7,9])
    def test_plane(self):
        v=execute("put(BYNAME('','CUBE[2]',e))",decl='cube:ARRAY[2,2,3]OF INTEGER e:INTEGER',routines='ROUTINE put(x:ARRAY[*,*]OF INTEGER) BEGIN x[2,3]=7 END put');self.assertEqual(v['CUBE'][1],[[U,U,U],[U,U,7]])
    def test_cube_row_comma(self):self.assertEqual(execute("put(BYNAME('','M[2,1]',e))",decl=DECL.replace('[2,2]','[2,2,2]'))['M'][1][0],[7,9])
    def test_cube_row_chain(self):self.assertEqual(execute("put(BYNAME('','M[2][1]',e))",decl=DECL.replace('[2,2]','[2,2,2]'))['M'][1][0],[7,9])
    def test_complete_chain_scalar(self):self.assertEqual(execute("put(BYNAME('','M[2][1]',e))",routines='ROUTINE put(x:INTEGER) BEGIN x=7 END put')['M'][1][0],7)
    def test_named_flat_root_suffix_anonymous(self):self.assertEqual(execute(types='TYPE matrix_t=ARRAY[2,2]OF INTEGER',decl=DECL.replace('ARRAY[2,2]OF INTEGER','matrix_t'))['M'][0],[7,9])
    def test_named_inner_component(self):
        v=execute("put(BYNAME('','M[2][1]',e))",types='TYPE plane_t=ARRAY[2,2]OF INTEGER',decl=DECL.replace('ARRAY[2,2]OF INTEGER','ARRAY[2]OF plane_t'));self.assertEqual(v['M'][1][0],[7,9])
    def test_named_child_components_remain_named(self):
        v=execute(types='TYPE row_t=ARRAY[2]OF INTEGER',decl=DECL.replace('ARRAY[2,2]OF INTEGER','ARRAY[2,2]OF row_t'),routines='ROUTINE put(x:ARRAY OF row_t) BEGIN x[2,1]=7 END put');self.assertEqual(v['M'][0][1],[7,U])
    def test_record_field_prefix(self):
        v=execute("put(BYNAME('','BOX.DATA[1]',e))",types='TYPE box_t=STRUCTURE data:ARRAY[2,2]OF INTEGER ENDSTRUCTURE',decl='box:box_t e:INTEGER');self.assertEqual(v['BOX']['DATA'][0],[7,9])
    def test_record_cells(self):
        v=execute(types='TYPE item_t=STRUCTURE count:INTEGER ENDSTRUCTURE',decl=DECL.replace('OF INTEGER row','OF item_t row'),routines='ROUTINE put(x:ARRAY OF item_t) BEGIN x[1].count=7 END put');self.assertEqual(v['M'][0][0]['COUNT'],7)
    def test_whole_row_replacement(self):self.assertEqual(execute('row[1]=7 '+CALL,routines='ROUTINE put(x:ARRAY OF INTEGER) BEGIN x=row END put')['M'][0],[7,U])
    def test_generic_string_capacity(self):
        v=execute(decl='m:ARRAY[2,2]OF STRING[3] e:INTEGER',routines="ROUTINE put(x:ARRAY OF STRING) BEGIN x[1]='abcd' END put");self.assertEqual(v['M'][0][0],'abc')
    def test_byte_unknown_leaf_preserved(self):self.assertEqual(execute(decl=DECL.replace('m:ARRAY[2,2]OF INTEGER','m:ARRAY[2,2]OF BYTE'),routines='ROUTINE put(x:ARRAY OF BYTE) BEGIN x[1]=255 END put')['M'][0],[255,B])
    def test_short_sentinel(self):self.assertEqual(execute(decl=DECL.replace('m:ARRAY[2,2]OF INTEGER','m:ARRAY[2,2]OF SHORT'),routines='ROUTINE put(x:ARRAY OF SHORT) BEGIN x[1]=32767 END put')['M'][0],[U,U])
    def test_joint_axes(self):
        v=execute(decl=DECL.replace('m:ARRAY[2,2]OF INTEGER','m:ARRAY[2,2]OF JOINTPOS2'),routines='ROUTINE put(x:ARRAY OF JOINTPOS2) BEGIN x[1][2]=90 END put');self.assertEqual(v['M'][0][0]['axes'],[U,90.])
    def test_labelled_engine(self):self.assertEqual(execute(labelled=True)['M'][0],[7,9])
    def test_bare_prefix_stays_private(self):self.assertEqual(execute('put(m[1])')['M'][0],[U,U])
    def test_grouped_prefix_stays_private(self):self.assertEqual(execute('put((m[1]))')['M'][0],[U,U])
    def test_forwarded_bare_live_formal(self):
        self.assertEqual(execute(routines=PUT.replace('put','child')+' ROUTINE put(x:ARRAY OF INTEGER) BEGIN child(x) END put')['M'][0],[7,9])
    def test_forwarded_grouped_live_formal_is_private(self):
        self.assertEqual(execute(routines=PUT.replace('put','child')+' ROUTINE put(x:ARRAY OF INTEGER) BEGIN child((x)) END put')['M'][0],[U,U])
    def test_source_prefix_inside_live_plane_is_private(self):
        v=execute("put(BYNAME('','M[1]',e))",decl=DECL.replace('[2,2]','[2,2,2]'),routines=PUT.replace('put','child')+' ROUTINE put(x:ARRAY[*,*]OF INTEGER) BEGIN child(x[1]) END put');self.assertEqual(v['M'][0][0],[U,U])
    def test_prefix_assignment_inside_live_plane(self):
        v=execute(decl=DECL.replace('[2,2]','[2,2,2]'),routines='ROUTINE put(x:ARRAY[*,*]OF INTEGER) BEGIN row[1]=7 x[2]=row END put');self.assertEqual(v['M'][0][1],[7,U])
    def test_array_len(self):self.assertEqual(execute(routines='ROUTINE put(x:ARRAY OF INTEGER) BEGIN n=ARRAY_LEN(x) END put')['N'],2)
    def test_uninit(self):self.assertTrue(execute(decl=DECL+' missing:BOOLEAN',routines='ROUTINE put(x:ARRAY OF INTEGER) BEGIN missing=UNINIT(x[1]) END put')['MISSING'])
    def test_read_updates_live_row(self):self.assertEqual(execute(routines='ROUTINE put(x:ARRAY OF INTEGER) BEGIN READ(x) END put',read=lambda _: [7,9])['M'][0],[7,9])
    def test_read_failure_does_not_publish_prefix(self):
        p,_=program('m[1,1]=42 '+CALL,routines='ROUTINE put(x:ARRAY OF INTEGER) BEGIN READ(x) END put',read=lambda _: [7,'bad'])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['M'][0],[42,U])
    def test_write_reads_live_row(self):
        p,_=program('m[1,1]=7 m[1,2]=9 '+CALL,routines='ROUTINE put(x:ARRAY OF INTEGER) BEGIN WRITE(x) END put');p.run();self.assertEqual(p._state.write_requests[0]['text'],' 7 9')
    def test_set_var_from_live_row(self):
        v=execute(routines="ROUTINE put(x:ARRAY OF INTEGER) BEGIN x[1]=7 SET_VAR(e,'','ROW',x,s) END put");self.assertEqual((v['ROW'],v['S']),([7,U],12311))
    def test_get_var_into_live_row(self):
        v=execute('row[1]=7 '+CALL,routines="ROUTINE put(x:ARRAY OF INTEGER) BEGIN GET_VAR(e,'','ROW',x,s) END put");self.assertEqual((v['M'][0],v['S']),([7,U],12311))


class LivePrefixAliasTests(unittest.TestCase):
    def test_two_views_share_cells(self):
        v=execute("put(BYNAME('','M[1]',e),BYNAME('','M[1]',e))",routines='ROUTINE put(x,y:ARRAY OF INTEGER) BEGIN x[1]=7 n=y[1] y[2]=9 END put');self.assertEqual((v['M'][0],v['N']),([7,9],7))
    def test_scalar_alias_survives_whole_row_write(self):
        v=execute("m[1,1]=42 put(BYNAME('','M[1]',e),m[1,1])",routines='ROUTINE put(x:ARRAY OF INTEGER;y:INTEGER) BEGIN row[1]=7 x=row n=y y=9 END put');self.assertEqual((v['M'][0][0],v['N']),(9,7))
    def test_receiver_edits_after_capture_remain_live(self):
        v=execute("put(BYNAME('','M[1]',e),later)",routines='ROUTINE later:INTEGER BEGIN m[1,1]=7 RETURN 0 END later ROUTINE put(x:ARRAY OF INTEGER;y:INTEGER) BEGIN n=x[1] END put');self.assertEqual(v['N'],7)
    def test_entry_alias_overlap_rejected_before_publication(self):
        p,_=program("m[1,1]=42 put(BYNAME('','M[1]',m[1,1]))")
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['M'][0],p._state.execution.entries),([42,U],{}))
    def test_unselected_entry_allowed(self):self.assertEqual(execute("put(BYNAME('','M[1]',m[2,1]))")['M'],[[7,9],[1,U]])
    def test_repeat_path_reuses_entry(self):
        p,_=program(CALL+' n=e '+CALL);v=p.run();self.assertEqual((v['N'],v['E'],len(p._state.execution.entries)),(1,1,1))
    def test_pause_retains_live_alias(self):
        p,_=program(cooperative=True,routines='ROUTINE put(x:ARRAY OF INTEGER) BEGIN x[1]=7 PAUSE x[2]=9 END put')
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['M'][0],[7,U]);self.assertEqual(p.resume()['M'][0],[7,9])
    def test_connected_timer_claim_is_underlying_cell(self):
        p,_=program(routines='ROUTINE put(x:ARRAY OF INTEGER) BEGIN CONNECT TIMER TO x[1] n=m[1,1] DISCONNECT TIMER x[1] END put',clock_us=lambda:0);v=p.run();self.assertEqual((v['M'][0][0],v['N'],p._state.execution._timer_claims),(0,0,{}))
    def test_formal_counter_remains_rejected(self):
        with self.assertRaises(TranslationError) as caught:program(routines='ROUTINE put(x:ARRAY OF INTEGER) BEGIN FOR x[1]=1 TO 2 DO n=1 ENDFOR END put')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
    def test_queue_repeated_capture_keeps_same_backing_cells(self):
        v=execute('INIT_QUEUE(q) '+CALL+' '+CALL,decl=DECL+' q:QUEUE_TYPE seq:INTEGER',routines='ROUTINE put(x:ARRAY OF INTEGER) BEGIN APPEND_QUEUE(7,q,x,seq,s) END put');self.assertEqual((v['M'][0],v['S']),([7,7],0))
    def test_queue_different_row_rejected(self):
        p,_=program('INIT_QUEUE(q) '+CALL+" put(BYNAME('','M[2]',e))",decl=DECL+' q:QUEUE_TYPE seq:INTEGER',routines='ROUTINE put(x:ARRAY OF INTEGER) BEGIN APPEND_QUEUE(7,q,x,seq,s) END put')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['M'][1],[U,U])
    def test_dynamic_array_alias(self):
        v=execute("CREATE_VAR('CACHE','DATA','','ARRAY OF INTEGER',0,2,2,0,s) put(BYNAME('CACHE','DATA[1]',e)) GET_VAR(e,'CACHE','DATA[1]',row,s)");self.assertEqual(v['ROW'],[7,9])
    def test_dynamic_rename_preserves_borrowed_cells(self):
        v=execute("CREATE_VAR('CACHE','DATA','','ARRAY OF INTEGER',0,2,2,0,s) put(BYNAME('CACHE','DATA[1]',e)) GET_VAR(e,'CACHE','NEXT[1]',row,s)",routines="ROUTINE put(x:ARRAY OF INTEGER) BEGIN RENAME_VAR('CACHE','DATA','NEXT',s) x[1]=7 END put");self.assertEqual(v['ROW'],[7,U])
    def test_saved_json_contains_values_without_views(self):
        p,_=program();p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertFalse(any('[' in row['path'] for row in saved['variables']));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)


class LivePrefixGuardTests(unittest.TestCase):
    def fails(self,path='M[1]',**options):
        p,_=program("e=77 put(BYNAME('','"+path+"',e))",**options)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['E'],p._state.execution.entries),(77,{}))
    def test_rank_mismatch(self):self.fails(routines='ROUTINE put(x:ARRAY[*,*]OF INTEGER) BEGIN END put')
    def test_leaf_type_mismatch(self):self.fails(routines=PUT.replace('OF INTEGER','OF REAL'))
    def test_named_suffix_identity_not_invented(self):self.fails(types='TYPE row_t=ARRAY[2]OF INTEGER',routines=PUT.replace('ARRAY OF INTEGER','row_t'))
    def test_zero_index(self):self.fails('M[0]')
    def test_high_index(self):self.fails('M[3]')
    def test_excess_rank(self):self.fails('M[1,1,1]')
    def test_dynamic_path_expression_rejected(self):self.fails('M[n]')
    def test_system_path_rejected(self):self.fails('$MNUFRAME[1,1]')
    def test_resource_prefix_requires_exact_resource_leaf(self):
        self.fails(decl=DECL.replace('m:ARRAY[2,2]OF INTEGER','m:ARRAY[2,2]OF FILE'),routines='ROUTINE put(x:ARRAY OF PATH) BEGIN END put')
        values=execute(decl=DECL.replace('m:ARRAY[2,2]OF INTEGER','m:ARRAY[2,2]OF FILE'),routines='ROUTINE put(x:ARRAY OF FILE) BEGIN n=ARRAY_LEN(x) END put')
        self.assertEqual(values['N'],2)
    def test_active_counter_alias_still_rejected(self):
        with self.assertRaises(TranslationError) as caught:program('FOR n=1 TO 2 DO '+CALL+' ENDFOR')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
    def test_protected_position_orientation(self):
        with self.assertRaises(TranslationError):program(decl=DECL.replace('m:ARRAY[2,2]OF INTEGER','m:ARRAY[2,2]OF POSITION'),routines='ROUTINE put(x:ARRAY OF POSITION) BEGIN x[1].normal.x=7 END put')
    def test_legacy_byname_not_enabled(self):
        with self.assertRaises(TranslationError):program(translator=legacy_translate)


class LivePrefixRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.scope=rt._numeric_scope('pythonic');self.scope.__enter__();self.addCleanup(self.scope.__exit__,None,None,None)
        self.spec=('ARRAY',(2,2),('INTEGER',));self.array=rt.Array(self.spec)
        self.ref=rt.array_prefix_reference(rt.array_prefix_target(self.array,1,self.spec))
    def test_exact_array_carrier(self):self.assertIs(type(self.ref.raw()),rt.Array)
    def test_scalar_reference_normalizes_to_original_list(self):
        leaf=rt.index_reference(self.ref.raw(),1);self.assertIs(leaf.storage,self.array.values);self.assertEqual(leaf.key,0)
    def test_overlap_identity_includes_original_cells(self):self.assertTrue(rt._reference_cells(self.ref)&rt._reference_cells(rt.Reference(self.spec,self.__dict__,'array')))
    def test_copy_is_independent_plain_storage(self):
        copy=rt.checked(self.ref.spec,self.ref.raw());self.assertIs(type(copy.values),list);copy.set(1,7);self.assertIs(self.array.values[0],rt.UNINITIALIZED)
    def test_resized_original_rejected(self):
        self.array.values.append(0)
        with self.assertRaises(rt.KarelRuntimeError):self.ref.raw().set(1,7)
    def test_window_slice_cannot_resize(self):
        with self.assertRaises(rt.KarelRuntimeError):self.ref.raw().values[:]=[7]
        self.assertEqual(len(self.array.values),4)
    def test_replaced_receiver_does_not_retarget_capture(self):
        old=self.array.values;self.array.values=[0]*4;self.ref.raw().set(1,7);self.assertEqual((old[0],self.array.values[0]),(7,0))
    def test_nested_prefix_capture_maps_to_original_cells(self):
        cube=rt.Array(('ARRAY',(2,2,2),('INTEGER',)));plane=rt.array_prefix_reference(rt.array_prefix_target(cube,2,cube.spec));row=rt.array_prefix_reference(rt.array_prefix_target(plane.raw(),1,plane.spec));row.raw().set(1,7);self.assertEqual(cube.values[4],7)
    def test_malformed_unselected_leaf_rejected_at_capture(self):
        self.array.values[-1]='bad'
        with self.assertRaises(rt.KarelRuntimeError):rt.array_prefix_target(self.array,1,self.spec)
    def test_maximum_size_row_remains_independent_when_copied(self):
        array=rt.Array(('ARRAY',(1,32767),('INTEGER',)));borrowed=rt.array_prefix_reference(rt.array_prefix_target(array,1,array.spec));borrowed.raw().set(32767,7)
        copied=rt.checked(borrowed.spec,borrowed.raw());copied.set(32767,9);self.assertEqual((array.values[-1],copied.values[-1],len(copied.values)),(7,9,32767))
    def test_list_subclasses_still_rejected(self):
        class Other(list):pass
        self.array.values=Other(self.array.values)
        with self.assertRaises(rt.KarelRuntimeError):rt.array_prefix_target(self.array,1,self.spec)
    def test_strict_runtime_cannot_use_live_window(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):self.ref.raw().get(1)
    def test_window_serializes_as_ordinary_values(self):
        self.ref.raw().set(1,7);from karel2py.storage import typed_value,restore_value
        saved=typed_value(self.ref.raw());restored=restore_value(saved['type'],saved['value']);self.assertIs(type(restored.values),list);self.assertEqual(restored.snapshot(),[7,U])


class LivePrefixIntegrationTests(unittest.TestCase):
    def test_report_exposes_explicit_ownership_and_boundaries(self):
        _,result=program();policy=result.report['array_prefix_reference_policy'];self.assertFalse(policy['controller_validated']);self.assertEqual(policy['guide'],'docs/array-prefix-references.md');self.assertIn('32767',policy['limits'])
    def test_malformed_unselected_source_fails_before_entry_cache(self):
        p,_=program('e=77 '+CALL);p._state.raw('M').values[-1]='bad'
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['E'],p._state.execution.entries),(77,{}))
    def test_linked_borrow(self):
        project=translate_project({'main':"PROGRAM MAIN VAR m:ARRAY[2,2]OF INTEGER e:INTEGER ROUTINE put(x:ARRAY OF INTEGER) FROM LIB BEGIN put(BYNAME('','M[2]',e)) END MAIN",'lib':'PROGRAM LIB '+PUT+' BEGIN END LIB'}).instantiate()
        project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['M'][1],[7,9])
    def test_attached_global_prefix(self):
        project=translate_project({'main':"PROGRAM MAIN VAR e:INTEGER ROUTINE put(x:ARRAY OF INTEGER) FROM LIB BEGIN put(BYNAME('LIB','M[2]',e)) END MAIN",'lib':'PROGRAM LIB VAR m:ARRAY[2,2]OF INTEGER '+PUT+' BEGIN END LIB'}).instantiate()
        project.run('MAIN');self.assertEqual(project.programs['LIB'].snapshot()['M'][1],[7,9])
    def test_linked_blank_program_keeps_calling_root(self):
        project=translate_project({'main':"PROGRAM MAIN VAR m:ARRAY[2,2]OF INTEGER ROUTINE probe FROM LIB BEGIN probe END MAIN",'lib':"PROGRAM LIB VAR e:INTEGER "+PUT+" ROUTINE probe BEGIN put(BYNAME('','M[1]',e)) END probe BEGIN END LIB"}).instantiate()
        project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['M'][0],[7,9])
    def test_linked_routine_pause(self):
        sources={'main':"PROGRAM MAIN VAR m:ARRAY[2,2]OF INTEGER e:INTEGER ROUTINE put(x:ARRAY OF INTEGER) FROM LIB BEGIN put(BYNAME('','M[1]',e)) END MAIN",'lib':'PROGRAM LIB '+PUT.replace('x[2]=9','PAUSE x[2]=9')+' BEGIN END LIB'}
        project=translate_project(sources).instantiate()
        self.assertEqual(project.run('MAIN')['MAIN']['state'],'paused')
        self.assertEqual(project.programs['MAIN'].snapshot()['M'][0],[7,U]);project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(project.programs['MAIN'].snapshot()['M'][0],[7,9])
    def test_dynamic_namespace_rename(self):
        v=execute("CREATE_VAR('CACHE','DATA','','ARRAY OF INTEGER',0,2,2,0,s) put(BYNAME('CACHE','DATA[1]',e)) GET_VAR(e,'SAVED','DATA[1]',row,s)",routines="ROUTINE put(x:ARRAY OF INTEGER) BEGIN RENAME_VARS('CACHE','SAVED',s) x[1]=7 END put");self.assertEqual(v['ROW'],[7,U])
    def test_binary_file_read(self):
        import struct
        context=rt.ExecutionContext(files=rt.MemoryFiles({'input':struct.pack('>ii',7,9)}))
        v=execute(decl=DECL+' f:FILE',context=context,routines="ROUTINE put(x:ARRAY OF INTEGER) BEGIN SET_FILE_ATR(f,ATR_REVERSE) OPEN FILE f('RB','input') READ f(x) CLOSE FILE f END put");self.assertEqual(v['M'][0],[7,9])
    def test_text_file_read(self):
        context=rt.ExecutionContext(files=rt.MemoryFiles({'input':b'7 9'}))
        v=execute(decl=DECL+' f:FILE',context=context,routines="ROUTINE put(x:ARRAY OF INTEGER) BEGIN OPEN FILE f('RO','input') READ f(x) CLOSE FILE f END put");self.assertEqual(v['M'][0],[7,9])
    def test_counter_analysis_through_forwarded_formal(self):
        with self.assertRaises(TranslationError) as caught:program('FOR n=1 TO 2 DO '+CALL+' ENDFOR',routines=PUT)
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
    def test_invalid_config_batch_preserves_live_row(self):
        p,_=program(decl='m:ARRAY[2,1]OF CONFIG e:INTEGER',routines='ROUTINE put(x:ARRAY OF CONFIG) BEGIN READ(x) END put',read=lambda _: [8,0,0,False,False,False])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['M'][0][0]['CFG_TURN_NO1'],U)
    def test_prefix_read_inside_live_plane(self):
        v=execute(decl=DECL.replace('[2,2]','[2,2,2]'),routines='ROUTINE put(x:ARRAY[*,*]OF INTEGER) BEGIN READ(x[2]) END put',read=lambda _: [7,9]);self.assertEqual(v['M'][0],[[U,U],[7,9]])
    def test_independent_return_from_live_formal(self):
        v=execute("row=copy(BYNAME('','M[1]',e)) row[1]=42",routines='ROUTINE copy(x:ARRAY OF INTEGER):ARRAY[2]OF INTEGER BEGIN x[1]=7 RETURN x END copy');self.assertEqual((v['M'][0],v['ROW']),([7,U],[42,U]))
    def test_entry_selector_captured_once(self):
        v=execute("n=0 put(BYNAME('','M[1]',cache[pick()]))",decl=DECL+' cache:ARRAY[1]OF INTEGER',routines='ROUTINE pick:INTEGER BEGIN n=n+1 RETURN 1 END pick '+PUT);self.assertEqual((v['N'],v['CACHE']),(1,[1]))
    def test_read_input_limit_retained(self):
        seen=[];p,_=program(decl='m:ARRAY[2,1025]OF INTEGER e:INTEGER',routines='ROUTINE put(x:ARRAY OF INTEGER) BEGIN READ(x) END put',read=lambda request:seen.append(request) or [])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(seen,[])
    def test_same_cells_do_not_equate_independent_arrays(self):
        with rt._numeric_scope('pythonic'):
            a=rt.Array(('ARRAY',2,('INTEGER',)));b=rt.Array(a.spec);self.assertFalse(rt.same_array_storage(a,b))


if __name__=='__main__':unittest.main()
