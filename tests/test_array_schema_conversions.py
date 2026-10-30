"""Authored source ARRAY schema, bounded STRING and logical-layout conversions."""
import copy
import json
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_named_array_conversions import cells,leaves,initialize,outputs
from tests.test_cartesian_interfaces import value as pose
from tests.test_joint_interoperability import joint,model_context
from tests.test_kinematic_assignments import callback_context
from karel2py.kinematics import pose as identity_pose
from tests.legacy_numeric_support import translate as legacy_translate

U={'uninitialized':True}
B={'unknown_byte':True}


def declaration(name,kind,layout):
    if layout=='flat':return f'{name}_t=ARRAY[2]OF {kind} '
    if layout=='matrix':return f'{name}_t=ARRAY[2,2]OF {kind} '
    if layout=='cube':return f'{name}_t=ARRAY[2,1,2]OF {kind} '
    if layout=='slab':return f'{name}_row=ARRAY[1,2]OF {kind} {name}_t=ARRAY[2]OF {name}_row '
    if layout=='deep':return f'{name}_row=ARRAY[2]OF {kind} {name}_plane=ARRAY[1]OF {name}_row {name}_t=ARRAY[2]OF {name}_plane '
    return f'{name}_row=ARRAY[2]OF {kind} {name}_t=ARRAY[2]OF {name}_row '


def build(body='b=a',first='INTEGER',second=None,source='rows',target=None,routines='',**options):
    target=target or source;second=second or first
    prefix='TYPE '+declaration('in',first,source)+declaration('out',second,target)
    return compile_program(body,prefix=prefix,decl='a:in_t b:out_t n,s,e,visits:INTEGER done:BOOLEAN',routines=routines,**options)


def strings(task,values=('abcdef','xy','','z')):
    for (storage,key),text in zip(cells(task._state.values['A']),values):storage[key]=text
    return task


class ArrayIdentityCopyTests(unittest.TestCase):
    def test_scalar_terminals_retain_receiver_names_and_data(self):
        for kind,values in [('INTEGER',(1,2,3,4)),('REAL',(1.,2.,3.,4.)),('BOOLEAN',(True,False,True,False)),('BYTE',(0,127,254,255)),('SHORT',(-7,0,7,32766)),('STRING[8]',('ab','cd','','ef'))]:
            with self.subTest(kind=kind):
                p,_=build(first=kind);initialize(p,values);before=p._state.values['A'].spec;p.run()
                self.assertEqual(outputs(p),list(values));self.assertEqual(p._state.values['B'].spec,p._state.types['B']);self.assertEqual(p._state.values['A'].spec,before)

    def test_known_and_missing_leaves_remain_independent(self):
        p,_=build('b=a b[1,1]=9');initialize(p,(1,rt.UNINITIALIZED,3,rt.UNINITIALIZED));v=p.run()
        self.assertEqual((v['A'],v['B']),([[1,U],[3,U]],[[9,U],[3,U]]))

    def test_unknown_byte_is_preserved_without_numeric_conversion(self):
        p,_=build(first='BYTE');initialize(p,(1,rt.UNKNOWN_BYTE,3,rt.UNINITIALIZED));p.run()
        self.assertEqual(p.snapshot()['B'],[[1,B],[3,U]])

    def test_short_sentinel_normalizes_in_the_private_copy(self):
        p,_=build(first='SHORT');initialize(p,(1,32767,3,4));p.run()
        self.assertEqual(p.snapshot()['B'],[[1,U],[3,4]]);self.assertEqual(leaves(p._state.values['A'])[1],32767)

    def test_partial_record_elements_keep_nominal_record_identity(self):
        prefix='TYPE item_t=STRUCTURE n:INTEGER text:STRING[4] ENDSTRUCTURE in_t=ARRAY[2]OF item_t out_t=ARRAY[2]OF item_t'
        p,_=compile_program('b=a b[1].n=9',prefix=prefix,decl='a:in_t b:out_t');p._state.values['A'].values[0].values['N']=7
        self.assertEqual((p.run()['A'][0]['N'],p.snapshot()['B'][0]),(7,{'N':9,'TEXT':U}))

    def test_same_width_partial_joints_need_no_model(self):
        p,_=build(first='JOINTPOS2');initialize(p,[joint([1.,rt.UNINITIALIZED])for _ in range(4)]);p.run()
        self.assertEqual([rt.snapshot_value(v) for v in outputs(p)],[{'axes':[1.,U]}]*4);self.assertEqual(p.service_requests,())

    def test_same_representation_partial_poses_need_no_model(self):
        p,_=build(first='XYZWPR');before=p.snapshot()['B'];p.run()
        self.assertEqual(p.snapshot()['B'],before);self.assertEqual(p.service_requests,())

    def test_position_orientation_remains_protected_after_retyping(self):
        with self.assertRaises(TranslationError) as error:build('b=a b[1,1].normal.x=9',first='POSITION')
        self.assertEqual(error.exception.code,'E_POSITION_READ_ONLY')

    def test_assignment_retains_receiver_array_and_record_children(self):
        p,_=build(first='POSITION');initialize(p);array=p._state.values['B'];row=array.values[0];point=row.values[0];location=point.values['LOCATION'];p.run()
        self.assertIs(p._state.values['B'],array);self.assertIs(array.values[0],row);self.assertIs(row.values[0],point);self.assertIs(point.values['LOCATION'],location)

    def test_late_invalid_source_domain_preserves_receiver(self):
        p,_=build(first='BYTE');initialize(p,(1,2,3,256));old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_nominal_argument_is_private_even_when_actual_is_bare(self):
        p,_=build('work(a)',routines='ROUTINE work(v:out_t) BEGIN v[1,1]=99 n=v[1,1] END work');initialize(p);v=p.run()
        self.assertEqual((v['A'][0][0],v['N']),(1,99))

    def test_exact_named_argument_keeps_existing_borrow(self):
        p,_=build('work(a)',routines='ROUTINE work(v:in_t) BEGIN v[1,1]=99 END work');initialize(p)
        self.assertEqual(p.run()['A'][0][0],99)

    def test_compatible_flat_generic_formal_keeps_nested_actual_borrow(self):
        p,_=build('work(a)',routines='ROUTINE work(v:ARRAY[*,*]OF INTEGER) BEGIN v[1,1]=99 END work');initialize(p)
        self.assertEqual(p.run()['A'][0][0],99)

    def test_private_named_formal_can_be_forwarded_by_reference(self):
        routines='ROUTINE inner(v:out_t) BEGIN v[1,1]=99 END inner ROUTINE work(v:out_t) BEGIN inner(v) n=v[1,1] END work'
        p,_=build('work(a)',routines=routines);initialize(p);v=p.run();self.assertEqual((v['A'][0][0],v['N']),(1,99))

    def test_retained_handler_only_changes_private_nominal_value(self):
        routine='ROUTINE retain(v:out_t) BEGIN CONDITION[1]: WHEN EVENT[1] DO v[1,1]=99 n=v[1,1] ENDCONDITION END retain'
        p,_=build('retain(a) ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=routine);initialize(p);v=p.run()
        self.assertEqual((v['A'][0][0],v['N']),(1,99))

    def test_named_copy_does_not_alias_active_counter(self):
        p,_=build('n=0 FOR a[1,1]=1 TO 2 DO work(a) n=n+a[1,1] ENDFOR',routines='ROUTINE work(v:out_t) BEGIN v[1,1]=99 END work');initialize(p)
        self.assertEqual((p.run()['N'],p.snapshot()['A'][0][0]),(3,U))

    def test_compatible_generic_counter_alias_still_rejects_writes(self):
        with self.assertRaises(TranslationError) as error:build('FOR a[1,1]=1 TO 2 DO work(a) ENDFOR',routines='ROUTINE work(v:ARRAY[*,*]OF INTEGER) BEGIN v[1,1]=99 END work')
        self.assertEqual(error.exception.code,'E_FOR_COUNTER')

    def test_formal_timer_binds_only_the_private_copy(self):
        p,_=build('work(a)',routines='ROUTINE work(v:out_t) BEGIN CONNECT TIMER TO v[1,1] v[1,1]=99 END work',clock_us=lambda:0);initialize(p)
        self.assertEqual((p.run()['A'][0][0],p._state.execution._timer_claims),(1,{}))

    def test_pause_resume_and_stop_never_copy_back(self):
        for action in ('resume','stop'):
            p,_=build('work(a)',routines='ROUTINE work(v:out_t) BEGIN v[1,1]=77 PAUSE v[1,1]=99 END work');initialize(p)
            with self.assertRaises(rt.KarelPause):p.run()
            getattr(p,action)();self.assertEqual(p.snapshot()['A'][0][0],1);self.assertEqual(p._state.local_frames,[])

    def test_nominal_return_captures_active_counter_before_cleanup(self):
        p,_=build('b=make()',routines='ROUTINE make:out_t BEGIN FOR a[1,1]=1 TO 2 DO RETURN a ENDFOR RETURN a END make');initialize(p);v=p.run()
        self.assertEqual((v['A'][0][0],v['B'][0][0]),(U,1))


class ArrayStringCapacityTests(unittest.TestCase):
    def test_narrowing_truncates_each_known_string_to_receiver_capacity(self):
        p,_=build(first='STRING[8]',second='STRING[3]');strings(p);p.run()
        self.assertEqual(outputs(p),['abc','xy','','z']);self.assertEqual(leaves(p._state.values['A'])[0],'abcdef')

    def test_widening_retains_contents_and_receiver_capacity(self):
        p,_=build(first='STRING[3]',second='STRING[8]');strings(p,('abc','xy','','z'));p.run()
        self.assertEqual(outputs(p),['abc','xy','','z']);self.assertEqual(rt.array_leaf_spec(p._state.values['B'].spec),('STRING',8))

    def test_all_bounded_capacities_have_the_scalar_truncation_contract(self):
        source=rt.Array(('ARRAY',2,('STRING',254),'IN'));source.values[:]=['x'*254,'']
        with rt._numeric_scope('pythonic'):
            for capacity in range(1,255):
                result=rt.convert_array_schema(('ARRAY',2,('STRING',capacity),'OUT'),source,23)
                self.assertEqual(result.values,['x'*capacity,'']);self.assertEqual(result.spec[2],('STRING',capacity))
        self.assertEqual(len(source.values[0]),254)

    def test_missing_strings_stay_missing_during_narrowing(self):
        p,_=build(first='STRING[8]',second='STRING[2]');initialize(p,('abc',rt.UNINITIALIZED,'',rt.UNINITIALIZED));p.run()
        self.assertEqual(p.snapshot()['B'],[['ab',U],['',U]])

    def test_malformed_source_capacity_fails_before_truncation(self):
        p,_=build(first='STRING[3]',second='STRING[2]');strings(p,('abc','x','','abcd'));old=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_non_ascii_source_fails_before_publication(self):
        p,_=build(first='STRING[8]',second='STRING[2]');strings(p,('ab','x','','café'));old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_bounded_string_formal_is_private_and_writable(self):
        p,_=build('work(a)',first='STRING[8]',second='STRING[3]',routines="ROUTINE work(v:out_t) BEGIN v[1,1]='changed' n=STR_LEN(v[1,1]) END work");strings(p)
        self.assertEqual((p.run()['A'][0][0],p.snapshot()['N']),('abcdef',3))

    def test_capacity_conversion_completes_before_later_argument(self):
        routines="ROUTINE change:INTEGER BEGIN a[1,1]='later' RETURN 0 END change ROUTINE work(v:out_t;ignored:INTEGER) BEGIN n=STR_LEN(v[1,1]) END work"
        p,_=build('work(a,change())',first='STRING[8]',second='STRING[3]',routines=routines);strings(p)
        self.assertEqual((p.run()['N'],p.snapshot()['A'][0][0]),(3,'later'))

    def test_failed_capacity_argument_skips_later_argument_and_callee(self):
        routines='ROUTINE later:INTEGER BEGIN n=1 RETURN 0 END later ROUTINE work(v:out_t;ignored:INTEGER) BEGIN n=2 END work'
        p,_=build('n=0 work(a,later())',first='STRING[3]',second='STRING[2]',routines=routines);strings(p,('ab','x','','oversized'))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p._state.local_frames),(0,[]))

    def test_named_string_return_uses_declared_capacity(self):
        p,_=build('b=make()',first='STRING[8]',second='STRING[3]',routines='ROUTINE make:out_t BEGIN RETURN a END make');strings(p);p.run()
        self.assertEqual(outputs(p),['abc','xy','','z']);self.assertEqual(rt.array_leaf_spec(p._state.values['B'].spec),('STRING',3))

    def test_inherited_anonymous_result_can_capture_named_string_storage(self):
        prefix='TYPE words_t=ARRAY[2]OF STRING[3]'
        p,_=compile_program("a[1]='abc' b=make()",prefix=prefix,decl='a:words_t b:ARRAY[2]OF STRING[8]',routines='ROUTINE make:ARRAY OF STRING BEGIN RETURN a END make');p.run()
        self.assertEqual(p.snapshot()['B'],['abc',U]);self.assertEqual(p._state.values['B'].spec,('ARRAY',2,('STRING',8)))

    def test_retained_string_handler_has_no_copyback(self):
        routine="ROUTINE retain(v:out_t) BEGIN CONDITION[1]: WHEN EVENT[1] DO v[1,1]='xyz' n=STR_LEN(v[1,1]) ENDCONDITION END retain"
        p,_=build('retain(a) ENABLE CONDITION[1] SIGNAL EVENT[1]',first='STRING[8]',second='STRING[2]',routines=routine);strings(p)
        self.assertEqual((p.run()['A'][0][0],p.snapshot()['N']),('abcdef',2))


class ArrayLogicalLayoutTests(unittest.TestCase):
    def test_all_three_dimensional_partitions_keep_coordinates(self):
        for source in ('cube','slab','deep'):
            for target in ('cube','slab','deep'):
                p,_=build(source=source,target=target);initialize(p);p.run()
                self.assertEqual(p.snapshot()['B'],[[[1,2]],[[3,4]]]);self.assertEqual(p._state.values['B'].spec,p._state.types['B'])

    def test_flat_to_rows_and_rows_to_flat_preserve_logical_shape(self):
        for source,target in (('matrix','rows'),('rows','matrix')):
            p,_=build(source=source,target=target);initialize(p);p.run()
            self.assertEqual(p.snapshot()['B'],[[1,2],[3,4]]);self.assertEqual(rt.array_dimensions(p._state.values['B'].spec),(2,2))

    def test_numeric_conversion_can_change_storage_partition(self):
        p,_=build(first='INTEGER',second='REAL',source='rows',target='matrix');initialize(p);p.run()
        self.assertEqual(outputs(p),[1.,2.,3.,4.]);self.assertEqual(p._state.values['B'].shape,(2,2))

    def test_positional_conversion_can_change_storage_partition(self):
        p,_=build(first='XYZWPR',second='POSITION',source='matrix',target='rows');initialize(p);p.run()
        self.assertEqual([item.values['LOCATION'].values['X']for item in outputs(p)],[1.,2.,3.,4.])

    def test_joint_width_conversion_can_change_storage_partition(self):
        p,_=build(first='JOINTPOS2',second='JOINTPOS9',source='rows',target='matrix');initialize(p);p.run()
        self.assertEqual([item.values for item in outputs(p)],[[0.,90.]+[0.]*7]*4)

    def test_model_conversion_can_change_partition_without_context_inference(self):
        p,_=build(first='JOINTPOS2',second='POSITION',source='matrix',target='rows',context=model_context((0.,90.)));initialize(p);p.run()
        self.assertEqual([item.values['LOCATION'].values['X']for item in outputs(p)],[100.]*4)

    def test_same_element_count_does_not_allow_different_logical_dimensions(self):
        prefix='TYPE in_t=ARRAY[2,2]OF INTEGER out_t=ARRAY[1,4]OF INTEGER'
        with self.assertRaises(TranslationError):compile_program('b=a',prefix=prefix,decl='a:in_t b:out_t')

    def test_rank_change_does_not_become_reshape(self):
        prefix='TYPE in_t=ARRAY[4]OF INTEGER out_t=ARRAY[2,2]OF INTEGER'
        with self.assertRaises(TranslationError):compile_program('b=a',prefix=prefix,decl='a:in_t b:out_t')

    def test_model_preflight_checks_all_source_geometry_across_partitions(self):
        calls=[]
        def inverse(*args):calls.append(1);return joint([0.,0.])
        p,_=build(first='POSITION',second='JOINTPOS2',source='matrix',target='rows',context=callback_context(inverse=inverse));initialize(p)
        leaves(p._state.values['A'])[-1].values['NORMAL'].values['X']=7.
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[])

    def test_late_model_failure_keeps_repartitioned_receiver_unchanged(self):
        calls=[]
        def forward(*args):
            calls.append(1)
            if len(calls)==4:raise ValueError('authored late adapter failure')
            point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=build(first='JOINTPOS2',second='POSITION',source='matrix',target='rows',context=callback_context(forward=forward));initialize(p);old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['B'],len(calls)),(old,4))

    def test_complete_chained_access_uses_the_receiver_layout(self):
        p,_=build('b=a b[2][2]=99',source='matrix',target='rows');initialize(p);p.run()
        self.assertEqual((p.snapshot()['A'][1][1],p.snapshot()['B'][1][1]),(4,99))

    def test_missing_nested_leaf_survives_flat_receiver(self):
        p,_=build(source='rows',target='matrix');initialize(p,(1,rt.UNINITIALIZED,3,4));p.run()
        self.assertEqual(p.snapshot()['B'],[[1,U],[3,4]])


class GenericArrayReceiverTests(unittest.TestCase):
    def test_generic_assignment_uses_actual_destination_nominal_schema(self):
        p,_=build('work(b,a)',routines='ROUTINE work(dst,src:ARRAY[*,*]OF INTEGER) BEGIN dst=src END work');initialize(p);p.run()
        self.assertEqual(p.snapshot()['B'],[[1,2],[3,4]]);self.assertEqual(p._state.values['B'].spec,p._state.types['B'])

    def test_generic_assignment_uses_actual_destination_partition(self):
        p,_=build('work(b,a)',source='matrix',target='rows',routines='ROUTINE work(dst,src:ARRAY[*,*]OF INTEGER) BEGIN dst=src END work');initialize(p);p.run()
        self.assertEqual(p._state.values['B'].spec,p._state.types['B']);self.assertIsInstance(p._state.values['B'].values[0],rt.Array)

    def test_generic_assignment_keeps_actual_string_capacity(self):
        p,_=build('work(b,a)',first='STRING[8]',second='STRING[2]',routines='ROUTINE work(dst,src:ARRAY[*,*]OF STRING) BEGIN dst=src END work');strings(p);p.run()
        self.assertEqual(outputs(p),['ab','xy','','z']);self.assertEqual(rt.array_leaf_spec(p._state.values['B'].spec),('STRING',2))

    def test_generic_numeric_assignment_keeps_actual_named_receiver(self):
        p,_=build('work(b,a)',first='INTEGER',second='REAL',routines='ROUTINE work(dst:ARRAY[*,*]OF REAL;src:ARRAY[*,*]OF INTEGER) BEGIN dst=src END work');initialize(p);p.run()
        self.assertEqual(outputs(p),[1.,2.,3.,4.]);self.assertEqual(p._state.values['B'].spec,p._state.types['B'])

    def test_generic_model_assignment_keeps_actual_named_receiver(self):
        p,_=build('work(b,a)',first='JOINTPOS2',second='POSITION',context=model_context((0.,90.)),routines='ROUTINE work(dst:ARRAY[*,*]OF POSITION;src:ARRAY[*,*]OF JOINTPOS2) BEGIN dst=src END work');initialize(p);p.run()
        self.assertEqual([item.values['LOCATION'].values['X']for item in outputs(p)],[100.]*4);self.assertEqual(p._state.values['B'].spec,p._state.types['B'])

    def test_generic_shape_mismatch_preserves_every_receiver_cell(self):
        p,_=compile_program('work(b,a)',decl='a:ARRAY[2,2]OF INTEGER b:ARRAY[1,4]OF INTEGER',routines='ROUTINE work(dst,src:ARRAY[*,*]OF INTEGER) BEGIN dst=src END work')
        initialize(p);old=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'logical dimensions'):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_generic_rhs_effects_finish_before_receiver_publication(self):
        routines='ROUTINE make:in_t BEGIN n=7 RETURN a END make ROUTINE work(dst:ARRAY[*,*]OF INTEGER) BEGIN dst=make() END work'
        p,_=build('work(b)',routines=routines);initialize(p);p.run();self.assertEqual((p.snapshot()['N'],outputs(p)),(7,[1,2,3,4]))

    def test_generic_receiver_uses_actual_record_schema(self):
        prefix='TYPE one=STRUCTURE n:INTEGER ENDSTRUCTURE two=STRUCTURE n:INTEGER ENDSTRUCTURE'
        p,_=compile_program('a[1].n=7 work(b,a) a[1].n=9',prefix=prefix,decl='a:ARRAY[2]OF one b:ARRAY[2]OF two',routines='ROUTINE work(dst:ARRAY OF two;src:ARRAY OF one) BEGIN dst=src END work')
        self.assertEqual(p.run()['B'],[{'N':7},{'N':U}]);self.assertEqual(p._state.values['B'].values[0].spec[1],'TWO')


class ArraySchemaBoundaryTests(unittest.TestCase):
    def test_generic_runtime_helpers_remain_exact(self):
        p,_=build();initialize(p);source=p._state.values['A'];target=p._state.types['B']
        with rt._numeric_scope('pythonic'):
            for action in (lambda:rt.checked(target,source),lambda:rt.value_argument(target,source),lambda:rt.array_result(target,source)):
                with self.assertRaises(rt.KarelRuntimeError):action()
        self.assertFalse(rt.parameter_accepts(target,source.spec))

    def test_byname_stays_exact_without_private_retyping(self):
        p,_=build("e=77 work(BYNAME('','A',e))",routines='ROUTINE work(v:out_t) BEGIN END work');initialize(p)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type does not match'):p.run()
        self.assertEqual(p.snapshot()['E'],77)

    def test_compatible_record_terminals_retain_receiver_names(self):
        prefix='TYPE one=STRUCTURE n:INTEGER ENDSTRUCTURE two=STRUCTURE n:INTEGER ENDSTRUCTURE in_t=ARRAY[2]OF one out_t=ARRAY[2]OF two'
        p,_=compile_program('a[1].n=7 b=a a[1].n=9',prefix=prefix,decl='a:in_t b:out_t')
        self.assertEqual(p.run()['B'],[{'N':7},{'N':U}]);self.assertEqual(p._state.values['B'].spec[3],'OUT_T')
        self.assertEqual(p._state.values['B'].values[0].spec[1],'TWO')

    def test_boolean_and_numeric_terminals_remain_separate(self):
        for first,second in (('BOOLEAN','INTEGER'),('INTEGER','BOOLEAN'),('REAL','INTEGER')):
            with self.assertRaises(TranslationError):build(first=first,second=second)

    def test_unknown_byte_query_is_not_enabled_by_retyping(self):
        with self.assertRaises(TranslationError) as error:build('b=a n=UNINIT(b[1,1])',first='BYTE')
        self.assertEqual(error.exception.code,'E_BYTE_UNINIT')

    def test_malformed_nested_storage_fails_before_receiver_publication(self):
        p,_=build();initialize(p);p._state.values['A'].values[0].shape=(3,);old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_invalid_string_schema_capacities_do_not_classify(self):
        for cap in (0,255,True,'4'):
            self.assertFalse(rt.array_schema_compatible(('ARRAY',2,('STRING',cap)),('ARRAY',2,('STRING',4))))

    def test_named_unknown_string_capacity_is_not_inferred(self):
        self.assertFalse(rt.array_schema_compatible(('ARRAY',2,('STRING',None),'OUT'),('ARRAY',2,('STRING',4),'IN')))

    def test_runtime_schema_helper_keeps_legacy_mode_guard(self):
        source=rt.Array(('ARRAY',2,('INTEGER',),'IN'))
        with rt._numeric_scope('strict'),self.assertRaisesRegex(rt.KarelRuntimeError,'Pythonic'):rt.convert_array_schema(('ARRAY',2,('INTEGER',),'OUT'),source)

    def test_public_strict_mode_remains_future_work(self):
        from karel2py import translate
        with self.assertRaises(TranslationError) as error:translate('PROGRAM T BEGIN END T',mode='strict')
        self.assertEqual(error.exception.code,'E_MODE')

    def test_legacy_source_nominal_copy_guard_is_preserved(self):
        with self.assertRaises(TranslationError):legacy_translate('PROGRAM T TYPE one=ARRAY[2]OF INTEGER two=ARRAY[2]OF INTEGER VAR a:one b:two BEGIN b=a END T')

    def test_json_preserves_repartitioned_receiver_names_and_missing_values(self):
        body='IF UNINIT(done) THEN b=a done=TRUE ENDIF'
        p,_=build(body,source='matrix',target='rows');initialize(p,(1,rt.UNINITIALIZED,3,4));p.run();saved=json.loads(json.dumps(p._state.execution.to_config()))
        restored,_=build(body,source='matrix',target='rows',context=rt.ExecutionContext.from_config(saved));restored.run()
        self.assertEqual(restored.snapshot(),p.snapshot());self.assertEqual(restored._state.values['B'].spec,p._state.values['B'].spec)


class ArraySchemaReportTests(unittest.TestCase):
    def test_nominal_sites_cover_assignment_argument_and_return(self):
        p,result=build('b=work(a)',routines='ROUTINE work(v:out_t):in_t BEGIN RETURN v END work');initialize(p);p.run()
        rows=result.report['array_schema_conversions'];self.assertEqual({row['operation']for row in rows},{'ARGUMENT','RETURN','ASSIGNMENT'})
        self.assertTrue(all(row['independent_value'] for row in rows));self.assertTrue(any(row.get('before_cleanup') for row in rows))

    def test_dynamic_receiver_report_requires_actual_receiver_schema(self):
        p,result=build('work(b,a)',routines='ROUTINE work(dst,src:ARRAY[*,*]OF INTEGER) BEGIN dst=src END work');initialize(p);p.run()
        rows=result.report['array_schema_conversions'];self.assertTrue(any(row.get('actual_receiver_schema') and row['schema_change_kind']=='dynamic_receiver' for row in rows))

    def test_string_report_retains_source_and_target_capacity(self):
        p,result=build(first='STRING[8]',second='STRING[2]');strings(p);p.run()
        row=result.report['array_schema_conversions'][0];self.assertEqual(row['schema_change_kind'],'string_capacity')
        self.assertEqual((rt.array_leaf_spec(row['source_type_spec']),rt.array_leaf_spec(row['target_type_spec'])),(('STRING',8),('STRING',2)))

    def test_schema_policy_and_named_provenance_are_explicit_offline_evidence(self):
        p,result=build();initialize(p);p.run();report=result.report
        self.assertFalse(report['array_schema_policy']['controller_validated']);self.assertEqual(report['array_schema_policy']['guide'],'docs/array-schema-conversions.md')
        self.assertTrue(any(row['conversion_kind']=='array_schema' for row in report['named_array_conversions']))


class ArraySchemaLinkageTests(unittest.TestCase):
    def test_matching_named_link_receives_private_nominal_copy(self):
        types='TYPE in_t=ARRAY[2]OF INTEGER out_t=ARRAY[2]OF INTEGER '
        lib='PROGRAM LIB '+types+' VAR seen:INTEGER ROUTINE work(v:out_t) BEGIN v[1]=99 seen=v[1] END work BEGIN END LIB'
        main='PROGRAM MAIN '+types+' VAR a:in_t ROUTINE work(v:out_t) FROM LIB BEGIN a[1]=7 work(a) END MAIN'
        project=translate_project({'main':main,'lib':lib}).instantiate();project.run('MAIN')
        self.assertEqual((project.programs['MAIN'].snapshot()['A'][0],project.programs['LIB'].snapshot()['SEEN']),(7,99))

    def test_mismatched_linked_declarations_are_not_coerced(self):
        types='TYPE in_t=ARRAY[2]OF INTEGER out_t=ARRAY[2]OF INTEGER '
        lib='PROGRAM LIB '+types+' VAR n:INTEGER ROUTINE work(v:in_t) BEGIN END work BEGIN END LIB'
        main='PROGRAM MAIN '+types+' VAR a:in_t ROUTINE work(v:out_t) FROM LIB BEGIN work(a) END MAIN'
        with self.assertRaises(ValueError):translate_project({'main':main,'lib':lib}).instantiate()

    def test_callback_receives_private_receiver_named_schema(self):
        seen=[]
        def work(ref):seen.append(ref.spec);ref.raw().values[0].values[0]=99
        p,_=build('work(a)',routines='ROUTINE work(v:out_t) FROM LIB',context=rt.ExecutionContext(externals={('LIB','WORK'):work}));initialize(p);p.run()
        self.assertEqual(seen,[p._state.types['B']]);self.assertEqual(leaves(p._state.values['A'])[0],1)

    def test_raw_callback_result_must_match_declared_named_schema(self):
        actual=rt.Array(('ARRAY',2,('INTEGER',),'IN_T'));actual.values[:]=[1,2]
        p,_=build('b=make()',source='flat',routines='ROUTINE make:out_t FROM LIB',context=rt.ExecutionContext(externals={('LIB','MAKE'):lambda:actual}))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(outputs(p)[0],rt.UNINITIALIZED)


if __name__=='__main__':unittest.main()
