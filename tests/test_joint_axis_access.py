"""Authored Pythonic joint-axis access with schema, alias, I/O and geometry boundaries."""
import copy
import json
import struct
import unittest
from karel2py import runtime as rt,translate,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_joint_interoperability import joint,model_context
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_serial_waits import streams

U={'uninitialized':True}
DECL='j,k:JOINTPOS2 value,out:REAL n,e,s:INTEGER done:BOOLEAN f:FILE'


def build(body='out=j[1]',*,decl=DECL,seed=True,**options):
    p,r=compile_program(body,decl=decl,**options)
    if seed:
        if 'J' in p._state.values and p._state.types['J']==('JOINTPOS',2):p._state.values['J']=joint([10.,20.])
        p._state.values.update(N=0,E=99,S=77,VALUE=7.5,OUT=88.)
    return p,r


def close(p):
    f=p._state.values['F']
    if f.owner is not None:p._state.file_close(f)


class JointAxisScalarTests(unittest.TestCase):
    def test_all_declared_widths_use_one_based_real_axes(self):
        for width in range(1,10):
            body=' '.join(f'j[{i}]={i}.5' for i in range(1,width+1))
            p,_=build(body,decl=f'j:JOINTPOS{width}',seed=False);self.assertEqual(p.run()['J']['axes'],[i+.5 for i in range(1,width+1)])

    def test_unsuffixed_joint_keeps_nine_axes_without_context(self):
        p,_=build('j[9]=9 out=j[9]',decl='j:JOINTPOS out:REAL',seed=False,joint_axes=None);v=p.run();self.assertEqual((v['OUT'],v['J']['axes'][:8]),(9.,[U]*8))

    def test_partial_joint_reads_only_the_selected_initialized_axis(self):
        p,_=build('j[1]=3.5 out=j[1] flag=UNINIT(j[2])',seed=False,decl=DECL+' flag:BOOLEAN');v=p.run();self.assertEqual((v['OUT'],v['J']['axes'],v['FLAG']),(3.5,[3.5,U],True))

    def test_missing_selected_axis_does_not_invent_value(self):
        p,_=build(seed=False)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['J']['axes'],[U,U])

    def test_integer_assignment_promotes_to_real_axis(self):
        p,_=build('j[1]=7 out=j[1]');self.assertEqual(p.run()['OUT'],7.)

    def test_axis_bounds_use_declared_width(self):
        for axis in (0,-1,3):
            p,_=build(f'j[{axis}]=1')
            with self.subTest(axis=axis),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['J']['axes'],[10.,20.])

    def test_index_requires_integer_without_truthiness_or_rounding(self):
        for axis in ('TRUE','1.0',"'1'"):
            with self.subTest(axis=axis),self.assertRaises(TranslationError):build('out=j['+axis+']')

    def test_extra_joint_subscripts_do_not_add_dimensions(self):
        for expr in ('j[1,2]','j[1][2]'):
            with self.subTest(expr=expr),self.assertRaises(TranslationError):build('out='+expr)

    def test_axis_is_real_without_implicit_integer_narrowing(self):
        with self.assertRaises(TranslationError):build('n=j[1]')

    def test_joint_fields_and_python_attributes_remain_unavailable(self):
        for expr in ('j.j1','j.axes','j.values'):
            with self.subTest(expr=expr),self.assertRaises(TranslationError):build('out='+expr)

    def test_writes_retain_joint_container_and_other_axes(self):
        p,_=build('j[1]=7');old=p._state.values['J'];p.run();self.assertIs(p._state.values['J'],old);self.assertEqual(old.values,[7.,20.])

    def test_unselected_invalid_numeric_axis_is_not_a_geometry_read(self):
        p,_=build();p._state.values['J'].values[1]=float('nan');self.assertEqual(p.run()['OUT'],10.)


class JointAxisAggregateTests(unittest.TestCase):
    def test_array_joint_element_accepts_chained_and_comma_spelling(self):
        for expr in ('items[1][2]','items[1,2]'):
            p,_=build(expr+'=7 out='+expr,decl=DECL+' items:ARRAY[2]OF JOINTPOS2');self.assertEqual(p.run()['OUT'],7.)

    def test_two_dimensional_array_then_joint_axis(self):
        p,_=build('items[1,2][2]=7 out=items[1][2][2]',decl=DECL+' items:ARRAY[1,2]OF JOINTPOS2');self.assertEqual(p.run()['OUT'],7.)

    def test_three_dimensional_array_then_axis_is_not_four_dimensional_array(self):
        p,_=build('items[1][1][2][2]=7 out=items[1,1,2,2]',decl=DECL+' items:ARRAY[1,1,2]OF JOINTPOS2');self.assertEqual(p.run()['OUT'],7.)

    def test_named_array_component_boundaries_remain_complete(self):
        p,_=build('items[1][2][2]=7 out=items[1,2,2]',prefix='TYPE row_t=ARRAY[2]OF JOINTPOS2',decl=DECL+' items:ARRAY[1]OF row_t');self.assertEqual(p.run()['OUT'],7.)

    def test_nested_record_joint_axis(self):
        p,_=build('packet.pose[2]=7 out=packet.pose[2]',prefix='TYPE packet_t=STRUCTURE pose:JOINTPOS2 ENDSTRUCTURE',decl=DECL+' packet:packet_t');self.assertEqual(p.run()['OUT'],7.)

    def test_using_captured_record_selects_joint_axis(self):
        p,_=build('USING packet DO pose[1]=7 out=pose[1] ENDUSING',prefix='TYPE packet_t=STRUCTURE pose:JOINTPOS2 ENDSTRUCTURE',decl=DECL+' packet:packet_t');self.assertEqual(p.run()['OUT'],7.)

    def test_computed_using_changes_only_private_record_joint(self):
        p,_=build('packet.pose=j USING make() DO pose[1]=7 out=pose[1] ENDUSING',prefix='TYPE packet_t=STRUCTURE pose:JOINTPOS2 ENDSTRUCTURE',decl=DECL+' packet:packet_t',routines='ROUTINE make:packet_t BEGIN RETURN packet END make');v=p.run();self.assertEqual((v['OUT'],v['PACKET']['POSE']['axes']),(7.,[10.,20.]))

    def test_flat_array_still_requires_complete_array_prefix(self):
        with self.assertRaises(TranslationError):build('out=items[1]',decl=DECL+' items:ARRAY[2,2]OF JOINTPOS2')

    def test_generic_formal_uses_actual_joint_array_layout(self):
        p,_=build('work(items)',prefix='TYPE row_t=ARRAY[2]OF JOINTPOS2',decl=DECL+' items:ARRAY[1]OF row_t',routines='ROUTINE work(v:ARRAY[*,*]OF JOINTPOS2) BEGIN v[1,2,2]=7 out=v[1][2][2] END work');self.assertEqual(p.run()['OUT'],7.)

    def test_whole_joint_formal_keeps_axis_alias_storage(self):
        p,_=build('work(j)',routines='ROUTINE work(v:JOINTPOS2) BEGIN v[2]=7 END work');self.assertEqual(p.run()['J']['axes'],[10.,7.])

    def test_joint_function_result_axis_uses_private_result(self):
        p,_=build('out=make()[1]',routines='ROUTINE make:JOINTPOS2 BEGIN RETURN j END make');self.assertEqual(p.run()['OUT'],10.)

    def test_active_aggregate_counter_root_remains_protected(self):
        with self.assertRaises(TranslationError) as caught:build('FOR packet.count=1 TO 2 DO packet.pose[1]=7 ENDFOR',prefix='TYPE packet_t=STRUCTURE count:INTEGER pose:JOINTPOS2 ENDSTRUCTURE',decl=DECL+' packet:packet_t')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')


class JointAxisCaptureTests(unittest.TestCase):
    def test_assignment_rhs_precedes_target_axis_selector_once(self):
        routines='ROUTINE rhs:REAL BEGIN n=n*10+1 RETURN 7.5 END rhs ROUTINE axis:INTEGER BEGIN n=n*10+2 RETURN 1 END axis'
        p,_=build('j[axis()]=rhs()',routines=routines);self.assertEqual((p.run()['N'],p.snapshot()['J']['axes'][0]),(12,7.5))

    def test_array_and_axis_calls_evaluate_once_left_to_right(self):
        routines='ROUTINE item:INTEGER BEGIN n=n*10+1 RETURN 1 END item ROUTINE axis:INTEGER BEGIN n=n*10+2 RETURN 2 END axis'
        p,_=build('items[item()][axis()]=7',decl=DECL+' items:ARRAY[2]OF JOINTPOS2',routines=routines);self.assertEqual(p.run()['N'],12)

    def test_all_indexes_run_before_combined_array_bounds_check(self):
        routines='ROUTINE item:INTEGER BEGIN n=n*10+1 RETURN 0 END item ROUTINE axis:INTEGER BEGIN n=n*10+2 RETURN 1 END axis'
        p,_=build('out=items[item()][axis()]',decl=DECL+' items:ARRAY[2]OF JOINTPOS2',routines=routines)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],12)

    def test_function_result_is_captured_before_axis_function_mutates_source(self):
        routines='ROUTINE make:JOINTPOS2 BEGIN n=n*10+1 RETURN j END make ROUTINE axis:INTEGER BEGIN n=n*10+2 j[1]=99 RETURN 1 END axis'
        p,_=build('out=make()[axis()]',routines=routines);v=p.run();self.assertEqual((v['N'],v['OUT'],v['J']['axes'][0]),(12,10.,99.))

    def test_bare_real_formal_alias_updates_selected_axis(self):
        p,_=build('work(j[2])',routines='ROUTINE work(v:REAL) BEGIN v=7.5 END work');self.assertEqual(p.run()['J']['axes'],[10.,7.5])

    def test_grouped_real_actual_is_private(self):
        p,_=build('work((j[2]))',routines='ROUTINE work(v:REAL) BEGIN v=7.5 END work');self.assertEqual(p.run()['J']['axes'],[10.,20.])

    def test_alias_capture_survives_whole_joint_replacement(self):
        p,_=build('k=j k[1]=7 work(j[2])',routines='ROUTINE work(v:REAL) BEGIN j=k v=99 END work');self.assertEqual(p.run()['J']['axes'],[7.,99.])

    def test_read_capture_precedes_format_call(self):
        routines='ROUTINE axis:INTEGER BEGIN n=n*10+1 RETURN 2 END axis ROUTINE width:INTEGER BEGIN n=n*10+2 RETURN 3 END width'
        p,_=build('READ(j[axis()]::width())',routines=routines,read=rt.TextInput('7.5'));self.assertEqual((p.run()['N'],p.snapshot()['J']['axes'][1]),(12,7.5))

    def test_pause_resume_retains_real_alias_without_repeating_selector(self):
        routines='ROUTINE axis:INTEGER BEGIN n=n+1 RETURN 2 END axis ROUTINE work(v:REAL) BEGIN PAUSE v=7.5 END work'
        p,_=build('work(j[axis()])',routines=routines)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['N'],1);v=p.resume();self.assertEqual((v['N'],v['J']['axes']),(1,[10.,7.5]))

    def test_scalar_conversion_output_can_write_real_axis(self):
        p,_=build("CNV_STR_REAL('7.5',j[2])");self.assertEqual((p.run()['J']['axes'][1],p.snapshot()['S']),(7.5,77))

    def test_real_axis_is_not_a_for_counter(self):
        with self.assertRaises(TranslationError):build('FOR j[1]=1 TO 2 DO ENDFOR')

    def test_builtin_integer_output_cannot_alias_real_axis(self):
        with self.assertRaises(TranslationError):build("GET_VAR(e,'','VALUE',value,j[1])")


class JointAxisInputTests(unittest.TestCase):
    def test_typed_callback_reads_into_partial_joint(self):
        p,_=build('READ(j[2])',seed=False,read=lambda request:[7.5]);self.assertEqual(p.run()['J']['axes'],[U,7.5])

    def test_late_invalid_callback_value_preserves_all_destinations(self):
        p,_=build('READ(j[1],j[2])',read=lambda request:[7.5,float('nan')])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['J']['axes'],[10.,20.])

    def test_repeated_axis_alias_keeps_order_after_complete_preflight(self):
        p,_=build('READ(j[1],j[1])',read=lambda request:[1.5,2.5]);self.assertEqual(p.run()['J']['axes'],[2.5,20.])

    def test_text_file_reads_real_axes(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'data':b'1.5 2.5\n'}));p,_=build("OPEN FILE f('RO','data') READ f(j[1],j[2],CR) CLOSE FILE f",context=ctx);self.assertEqual(p.run()['J']['axes'],[1.5,2.5])

    def test_binary_file_reads_real_axes(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'data':struct.pack('<ff',1.5,2.5)}));p,_=build("OPEN FILE f('RB','data') READ f(j[1],j[2]) CLOSE FILE f",context=ctx);self.assertEqual(p.run()['J']['axes'],[1.5,2.5])

    def test_invalid_binary_late_axis_keeps_outputs_and_cursor(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'data':struct.pack('<if',12,float('nan'))}));p,_=build("OPEN FILE f('RB','data') READ f(n,j[2])",context=ctx);p._state.values['N']=77
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        f=p._state.values['F'];self.assertEqual((p.snapshot()['N'],p.snapshot()['J']['axes'],f.position,f.status),(77,[10.,20.],0,1));close(p)

    def test_callback_whole_joint_replacement_retains_captured_axis(self):
        def read(request):rt.Reference(('JOINTPOS',2),p._state.values,'J').set(joint([1.,2.]));return [99.]
        p,_=build('READ(j[2])',read=read);self.assertEqual(p.run()['J']['axes'],[1.,99.])

    def test_waiting_serial_keeps_axis_capture_across_feed(self):
        bank,ctx=streams()
        def sleep(_):bank.feed(2,b'7.5\n')
        p,_=build("OPEN FILE f('RO','P2:') READ f(j[2],CR) CLOSE FILE f",context=ctx,sleep=sleep);self.assertEqual(p.run()['J']['axes'],[10.,7.5]);self.assertFalse(bank._pending)

    def test_cancel_waiting_serial_preserves_axis_values(self):
        bank,ctx=streams()
        def sleep(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=build("OPEN FILE f('RO','P2:') READ f(j[2],CR) s=IO_STATUS(f) CLOSE FILE f",context=ctx,sleep=sleep);v=p.run();self.assertEqual((v['J']['axes'],v['S']),( [10.,20.],6));self.assertFalse(bank._pending)

    def test_whole_joint_read_stays_rejected(self):
        with self.assertRaises(TranslationError):build('READ(j)')


class JointAxisVariablePathTests(unittest.TestCase):
    def test_get_var_reads_one_axis_without_robot_service(self):
        p,_=build("GET_VAR(e,'','J[2]',out,s)");v=p.run();self.assertEqual((v['OUT'],v['S'],v['E']),(20.,0,1))

    def test_set_var_writes_one_axis_without_replacing_joint(self):
        p,_=build("SET_VAR(e,'','J[2]',value,s)");before=p._state.values['J'];v=p.run();self.assertEqual((v['J']['axes'],v['S']),([10.,7.5],0));self.assertIs(p._state.values['J'],before)

    def test_byname_exact_real_alias_updates_axis(self):
        p,_=build("work(BYNAME('','J[2]',e))",routines='ROUTINE work(v:REAL) BEGIN v=99 END work');self.assertEqual(p.run()['J']['axes'],[10.,99.])

    def test_missing_selected_axis_preserves_transfer_missing_status(self):
        p,_=build("GET_VAR(e,'','J[2]',out,s)",seed=False);v=p.run();self.assertEqual((v['OUT'],v['S']),(U,12311))

    def test_invalid_axis_path_retains_lookup_failure_contract(self):
        p,_=build("GET_VAR(e,'','J[3]',out,s)");v=p.run();self.assertEqual((v['OUT'],v['E'],v['S']),(88.,99,1))

    def test_nested_joint_array_path_supports_combined_and_separate_axis(self):
        for path in ('ITEMS[1,2]','ITEMS[1][2]'):
            p,_=build("items[1][2]=7 GET_VAR(e,'','"+path+"',out,s)",decl=DECL+' items:ARRAY[2]OF JOINTPOS2');self.assertEqual(p.run()['OUT'],7.)

    def test_explicit_foreign_joint_binding_uses_declared_width(self):
        ctx=rt.ExecutionContext();ref=ctx.variables.define('OTHER','POSE',('JOINTPOS',2),joint([1.,2.]));p,_=build("SET_VAR(e,'OTHER','POSE[2]',value,s)",context=ctx);self.assertEqual(p.run()['S'],0);self.assertEqual(ref.raw().values,[1.,7.5])

    def test_substituted_binding_width_is_lookup_failure(self):
        ctx=rt.ExecutionContext();ref=ctx.variables.define('OTHER','POSE',('JOINTPOS',2),joint([1.,2.]));ref.storage[ref.key]=joint([1.,2.,3.]);p,_=build("GET_VAR(e,'OTHER','POSE[1]',out,s)",context=ctx);v=p.run();self.assertEqual((v['OUT'],v['E'],v['S']),(88.,99,1))


class JointAxisSchemaAndModelTests(unittest.TestCase):
    def test_substituted_source_joint_width_fails_before_read_callback(self):
        calls=[];p,_=build('READ(j[1])',read=lambda request:calls.append(request));p._state.values['J']=joint([1.,2.,3.])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((calls,p.read_requests),([],()))

    def test_malformed_axis_count_and_storage_types_are_rejected(self):
        for values in ([1.],(1.,2.)):
            p,_=build();p._state.values['J'].values=values
            with self.subTest(values=values),self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_substituted_array_schema_is_rejected_before_selected_write(self):
        p,_=build('items[1][1]=7',decl=DECL+' items:ARRAY[2]OF JOINTPOS2');p._state.values['ITEMS']=rt.Array(('ARRAY',3,('JOINTPOS',2)))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['ITEMS'][0]['axes'],[U,U])

    def test_malformed_selected_joint_element_is_rejected(self):
        p,_=build('items[1][1]=7',decl=DECL+' items:ARRAY[2]OF JOINTPOS2');p._state.values['ITEMS'].values[0]=joint([1.,2.,3.])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['ITEMS'][0]['axes'],[1.,2.,3.])

    def test_malformed_array_shape_is_rejected_before_bounds_checks(self):
        p,_=build('items[1][1]=7',decl=DECL+' items:ARRAY[2]OF JOINTPOS2');p._state.values['ITEMS'].shape=(3,)
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_nonfinite_axis_read_fails_with_source_line(self):
        p,_=build();p._state.values['J'].values[0]=float('nan')
        with self.assertRaises(rt.KarelRuntimeError) as caught:p.run()
        self.assertIsNotNone(caught.exception.line)

    def test_selected_axis_storage_is_not_a_joint_geometry_certificate(self):
        p,_=build('j[1]=0 out=j[1] p=j',decl=DECL+' p:POSITION',seed=False,context=model_context())
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['OUT'],0.)

    def test_axis_changes_flow_into_existing_explicit_forward_model(self):
        p,_=build('j[1]=0 j[2]=90 p=j',decl=DECL+' p:POSITION',context=model_context((0.,0.)));v=p.run();self.assertAlmostEqual(v['P']['LOCATION']['X'],100.);self.assertAlmostEqual(v['P']['LOCATION']['Y'],100.)

    def test_nonzero_discarded_axis_still_blocks_width_narrowing(self):
        p,_=build('j[3]=7 k=j',decl='j:JOINTPOS3 k:JOINTPOS2',seed=False);p._state.values['J']=joint([1.,2.,0.])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['K']['axes'],[U,U])

    def test_runtime_schema_classifier_is_bounded_for_malformed_types(self):
        cyclic=['ARRAY',1,None];cyclic[2]=cyclic
        for spec in (None,(),('JOINTPOS',True),('ARRAY',0,('JOINTPOS',2)),('ARRAY',1,cyclic)):
            with self.subTest(spec=repr(spec)):self.assertFalse(rt.joint_axis_access(spec,1))
        value=rt.Array(('ARRAY',1,('JOINTPOS',2)));value.spec=('ARRAY',1,cyclic)
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):
            rt.joint_index_reference(value,(1,1),('ARRAY',None,('JOINTPOS',2)),17)


class JointAxisPersistenceAndBoundaryTests(unittest.TestCase):
    def test_serializable_context_keeps_axes_and_missing_markers(self):
        p,_=build('j[1]=7',seed=False);p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));q,_=build('out=j[1]',seed=False,context=rt.ExecutionContext.from_config(saved));self.assertEqual(q.run()['OUT'],7.);self.assertEqual(q.snapshot()['J']['axes'][1],U)

    def test_linked_real_formal_preserves_selected_axis_alias(self):
        main='PROGRAM MAIN VAR j:JOINTPOS2 ROUTINE work(v:REAL) FROM LIB BEGIN j[1]=1 j[2]=2 work(j[2]) END MAIN'
        lib='PROGRAM LIB ROUTINE work(v:REAL) BEGIN v=7.5 END work BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate();project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['J']['axes'],[1.,7.5])

    def test_legacy_source_and_helpers_remain_array_only(self):
        with self.assertRaises(TranslationError):legacy_translate('PROGRAM T VAR j:JOINTPOS2 x:REAL BEGIN x=j[1] END T')
        with rt._numeric_scope('strict'):
            for access in (lambda:rt.index_reference(joint([1.,2.]),1),lambda:rt.raw_index(joint([1.,2.]),1),lambda:rt.joint_index_reference(joint([1.,2.]),1,('JOINTPOS',2))):
                with self.assertRaises(rt.KarelRuntimeError):access()

    def test_generic_array_type_helper_does_not_gain_joint_index_coercion(self):
        with self.assertRaises(rt.KarelRuntimeError):rt.indexed_type(('JOINTPOS',2),1)

    def test_report_records_declared_width_and_source_locations(self):
        _,r=build('j[2]=7 out=j[2]');rows=r.report['joint_axis_accesses'];self.assertEqual(len(rows),2);self.assertTrue(all(row['joint_type_spec']==('JOINTPOS',2) and row['evaluated_once'] and row['declared_schema_checked'] for row in rows));self.assertFalse(r.report['joint_axis_policy']['controller_validated']);json.dumps(r.report)

    def test_native_joint_field_syntax_remains_separate(self):
        self.assertIn('no direct joint field syntax',build()[1].report['joint_policy']['representation'])


class JointAxisAdditionalBoundaries(unittest.TestCase):
    def test_runtime_index_helpers_use_same_checked_real_cells(self):
        value=joint([1.,2.])
        with rt._numeric_scope('pythonic'):
            rt.store_index(value,2,7.5,19);self.assertEqual(rt.load_index(value,2,19),7.5)
            self.assertEqual(rt.index_reference(value,2,19).spec,('REAL',))
            with self.assertRaises(rt.KarelRuntimeError):rt.store_index(value,2,float('nan'),19)
        self.assertEqual(value.values,[1.,7.5])

    def test_whole_missing_joint_fails_before_read_callback(self):
        calls=[];p,_=build('READ(j[1])',read=lambda request:calls.append(request));p._state.values['J']=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((calls,p.read_requests,p.snapshot()['OUT']),([],(),88.))


if __name__=='__main__':unittest.main()
