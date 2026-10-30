"""Authored context-free STRUCTURE and record-ARRAY source conversions."""
import json
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_cartesian_interfaces import value as pose
from tests.test_joint_interoperability import joint
from tests.legacy_numeric_support import translate as legacy_translate

U={'uninitialized':True}
B={'unknown_byte':True}
TYPES='''TYPE in_child=STRUCTURE n:INTEGER note:STRING[8] ENDSTRUCTURE
out_child=STRUCTURE note:STRING[3] n:REAL ENDSTRUCTURE
out_row=ARRAY[2]OF REAL
in_t=STRUCTURE count:INTEGER label:STRING[8] child:in_child samples:ARRAY[2,2]OF INTEGER pose:XYZWPR joints:JOINTPOS2 flag:BOOLEAN ENDSTRUCTURE
out_t=STRUCTURE label:STRING[3] count:SHORT child:out_child samples:ARRAY[2]OF out_row pose:POSITION joints:JOINTPOS9 flag:BOOLEAN ENDSTRUCTURE'''
DECL='a:in_t b:out_t n,visits,s,e:INTEGER done:BOOLEAN'


def build(body='b=a',routines='',**options):
    return compile_program(body,prefix=TYPES,decl=DECL,routines=routines,**options)


def initialize(task):
    value=task._state.values['A'];value.values.update(COUNT=7,LABEL='abcdefgh',POSE=pose('XYZWPR',(1.,2.,3.),(0.,0.,90.)),JOINTS=joint([1.,2.]),FLAG=True)
    value.values['CHILD'].values.update(N=9,NOTE='nested');value.values['SAMPLES'].values[:]=[1,2,3,4]
    return task


def simple(body='b=a',first='INTEGER',second='REAL',routines='',**options):
    prefix=f'TYPE in_t=STRUCTURE value:{first} label:STRING[8] ENDSTRUCTURE out_t=STRUCTURE label:STRING[3] value:{second} ENDSTRUCTURE'
    return compile_program(body,prefix=prefix,decl='a:in_t b:out_t n,visits,e,s:INTEGER done:BOOLEAN',routines=routines,**options)


def seed(task,value=7,label='abcdef'):
    task._state.values['A'].values.update(VALUE=value,LABEL=label);return task


class RecordSchemaValueTests(unittest.TestCase):
    def test_fields_match_by_name_in_receiver_order(self):
        p,_=build();initialize(p);v=p.run()['B']
        self.assertEqual(list(p._state.values['B'].values),['LABEL','COUNT','CHILD','SAMPLES','POSE','JOINTS','FLAG'])
        self.assertEqual((v['LABEL'],v['COUNT'],v['CHILD']),('abc',7,{'NOTE':'nes','N':9.}))

    def test_nested_records_and_array_layouts_keep_receiver_names(self):
        p,_=build();initialize(p);v=p.run()['B']
        self.assertEqual(v['SAMPLES'],[[1.,2.],[3.,4.]])
        self.assertEqual(p._state.values['B'].spec,p._state.types['B'])
        self.assertEqual(p._state.values['B'].values['CHILD'].spec[1],'OUT_CHILD')
        self.assertEqual(p._state.values['B'].values['SAMPLES'].spec[2][3],'OUT_ROW')

    def test_all_integral_pairs_and_real_promotions(self):
        for first in ('INTEGER','BYTE','SHORT'):
            for second in ('INTEGER','BYTE','SHORT','REAL'):
                p,_=simple(first=first,second=second);seed(p,7);v=p.run()['B']['VALUE']
                self.assertEqual(v,7);self.assertIs(type(v),float if second=='REAL' else int)

    def test_strings_truncate_without_changing_source(self):
        p,_=simple();seed(p,label='abcdefgh');p.run()
        self.assertEqual((p.snapshot()['A']['LABEL'],p.snapshot()['B']['LABEL']),('abcdefgh','abc'))

    def test_missing_scalar_fields_stay_missing(self):
        p,_=simple();p.run();self.assertEqual(p.snapshot()['B'],{'LABEL':U,'VALUE':U})

    def test_partial_nested_leaves_remain_missing(self):
        p,_=build();initialize(p);p._state.values['A'].values['COUNT']=rt.UNINITIALIZED
        p._state.values['A'].values['CHILD'].values['NOTE']=rt.UNINITIALIZED;p._state.values['A'].values['SAMPLES'].values[-1]=rt.UNINITIALIZED
        v=p.run()['B'];self.assertEqual((v['COUNT'],v['CHILD']['NOTE'],v['SAMPLES'][1][1]),(U,U,U))

    def test_unknown_byte_is_preserved_for_same_type(self):
        p,_=simple(first='BYTE',second='BYTE');seed(p,rt.UNKNOWN_BYTE);self.assertEqual(p.run()['B']['VALUE'],B)

    def test_unknown_byte_cannot_become_a_number(self):
        p,_=simple(first='BYTE');seed(p,rt.UNKNOWN_BYTE);old=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'unknown'):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_short_sentinel_normalization_is_private(self):
        p,_=simple(first='SHORT');seed(p,32767);p.run()
        self.assertEqual(p.snapshot()['B']['VALUE'],U);self.assertEqual(p._state.values['A'].values['VALUE'],32767)

    def test_narrowing_to_short_retains_missing_sentinel(self):
        p,_=simple(second='SHORT');seed(p,32767);self.assertEqual(p.run()['B']['VALUE'],U)

    def test_late_overflow_preserves_whole_receiver(self):
        p,_=simple(second='BYTE');seed(p,256);old=p.snapshot()['B'];record=p._state.values['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],old);self.assertIs(p._state.values['B'],record)

    def test_source_domain_is_checked_before_promotion(self):
        for first,value in [('BYTE',256),('SHORT',-32769),('INTEGER',2147483647),('INTEGER',True),('INTEGER',1.)]:
            p,_=simple(first=first);seed(p,value)
            with self.subTest(first=first,value=value),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['B']['VALUE'],U)

    def test_oversized_source_string_is_not_hidden_by_truncation(self):
        p,_=simple();seed(p,label='too long for eight')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):p.run()
        self.assertEqual(p.snapshot()['B']['LABEL'],U)

    def test_non_ascii_source_rejects_without_publication(self):
        p,_=simple();seed(p,label='caf'+chr(233));old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_receiver_child_identities_survive(self):
        p,_=build();initialize(p);record=p._state.values['B'];child=record.values['CHILD'];row=record.values['SAMPLES'].values[0];location=record.values['POSE'].values['LOCATION'];p.run()
        self.assertIs(p._state.values['B'],record);self.assertIs(record.values['CHILD'],child)
        self.assertIs(record.values['SAMPLES'].values[0],row);self.assertIs(record.values['POSE'].values['LOCATION'],location)

    def test_pose_and_joint_fields_are_context_free(self):
        p,_=build();initialize(p);v=p.run()['B']
        self.assertEqual(v['POSE']['LOCATION'],{'X':1.,'Y':2.,'Z':3.});self.assertEqual(v['JOINTS']['axes'],[1.,2.]+[0.]*7)
        self.assertEqual(p.service_requests,())

    def test_missing_pose_cannot_change_representation(self):
        p,_=build();initialize(p);p._state.values['A'].values['POSE'].values['X']=rt.UNINITIALIZED;old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_same_type_partial_pose_is_copyable(self):
        prefix='TYPE in_t=STRUCTURE point:POSITION ENDSTRUCTURE out_t=STRUCTURE point:POSITION ENDSTRUCTURE'
        p,_=compile_program('b=a',prefix=prefix,decl='a:in_t b:out_t')
        self.assertEqual(p.run()['B']['POINT']['LOCATION']['X'],U);self.assertEqual(p.service_requests,())

    def test_position_orientation_remains_readonly(self):
        with self.assertRaises(TranslationError) as error:build('b=a b.pose.normal.x=9')
        self.assertEqual(error.exception.code,'E_POSITION_READ_ONLY')

    def test_nonzero_discarded_joint_axis_rejects(self):
        prefix='TYPE in_t=STRUCTURE j:JOINTPOS3 ENDSTRUCTURE out_t=STRUCTURE j:JOINTPOS2 ENDSTRUCTURE'
        p,_=compile_program('b=a',prefix=prefix,decl='a:in_t b:out_t');p._state.values['A'].values['J']=joint([1.,2.,3.])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B']['J']['axes'],[U,U])


class RecordSchemaInterfaceTests(unittest.TestCase):
    def test_bare_converted_actual_is_private(self):
        p,_=simple('work(a)',routines='ROUTINE work(v:out_t) BEGIN v.value=99 n=TRUNC(v.value) END work');seed(p);v=p.run()
        self.assertEqual((v['A']['VALUE'],v['N']),(7,99))

    def test_exact_actual_keeps_reference(self):
        p,_=simple('work(a)',routines='ROUTINE work(v:in_t) BEGIN v.value=99 END work');seed(p)
        self.assertEqual(p.run()['A']['VALUE'],99)

    def test_grouped_converted_actual_is_private(self):
        p,_=simple('work((a))',routines='ROUTINE work(v:out_t) BEGIN v.value=99 END work');seed(p)
        self.assertEqual(p.run()['A']['VALUE'],7)

    def test_forwarding_aliases_only_private_record(self):
        routines='ROUTINE inner(v:out_t) BEGIN v.value=99 END inner ROUTINE work(v:out_t) BEGIN inner(v) n=TRUNC(v.value) END work'
        p,_=simple('work(a)',routines=routines);seed(p);v=p.run();self.assertEqual((v['A']['VALUE'],v['N']),(7,99))

    def test_retained_handler_owns_private_record(self):
        routines='ROUTINE retain(v:out_t) BEGIN CONDITION[1]: WHEN EVENT[1] DO v.value=99 n=TRUNC(v.value) ENDCONDITION END retain'
        p,_=simple('retain(a) ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=routines);seed(p);v=p.run()
        self.assertEqual((v['A']['VALUE'],v['N']),(7,99))

    def test_pause_resume_has_no_copyback(self):
        p,_=simple('work(a)',routines='ROUTINE work(v:out_t) BEGIN v.value=77 PAUSE v.value=99 n=TRUNC(v.value) END work');seed(p)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['A']['VALUE'],7);p.resume();self.assertEqual((p.snapshot()['A']['VALUE'],p.snapshot()['N']),(7,99))

    def test_stop_and_abort_unwind_private_frames(self):
        for statement in ('PAUSE','ABORT'):
            p,_=simple('work(a)',routines=f'ROUTINE work(v:out_t) BEGIN v.value=99 {statement} END work');seed(p)
            with self.assertRaises(rt.KarelPause if statement=='PAUSE' else rt.KarelAbort):p.run()
            if statement=='PAUSE':p.stop()
            self.assertEqual((p.snapshot()['A']['VALUE'],p._state.local_frames),(7,[]))

    def test_failure_retains_global_effects_without_copyback(self):
        p,_=simple('work(a)',routines='ROUTINE work(v:out_t) BEGIN v.value=99 n=1 s=1 DIV 0 END work');seed(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['A']['VALUE'],p.snapshot()['N'],p._state.local_frames),(7,1,[]))

    def test_budget_failure_unwinds_record(self):
        p,_=simple('work(a)',routines='ROUTINE work(v:out_t) BEGIN WHILE TRUE DO v.value=99 ENDWHILE END work');seed(p)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):p.run(max_steps=20)
        self.assertEqual((p.snapshot()['A']['VALUE'],p._state.local_frames),(7,[]))

    def test_conversion_finishes_before_later_argument(self):
        routines='ROUTINE change:INTEGER BEGIN a.value=99 RETURN 0 END change ROUTINE work(v:out_t;ignored:INTEGER) BEGIN n=TRUNC(v.value) END work'
        p,_=simple('work(a,change())',routines=routines);seed(p);v=p.run();self.assertEqual((v['A']['VALUE'],v['N']),(99,7))

    def test_failed_conversion_skips_later_argument(self):
        routines='ROUTINE later:INTEGER BEGIN n=1 RETURN 0 END later ROUTINE work(v:out_t;ignored:INTEGER) BEGIN n=2 END work'
        p,_=simple('n=0 work(a,later())',second='BYTE',routines=routines);seed(p,256)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p._state.local_frames),(0,[]))

    def test_function_source_runs_once(self):
        p,_=simple('visits=0 b=make()',routines='ROUTINE make:in_t BEGIN visits=visits+1 RETURN a END make');seed(p)
        self.assertEqual((p.run()['VISITS'],p.snapshot()['B']['VALUE']),(1,7.))

    def test_rhs_capture_precedes_target_selector(self):
        prefix='TYPE in_t=STRUCTURE value:INTEGER ENDSTRUCTURE out_t=STRUCTURE value:REAL ENDSTRUCTURE box_t=STRUCTURE item:out_t ENDSTRUCTURE'
        p,_=compile_program('a.value=7 boxes[pick()].item=a',prefix=prefix,decl='a:in_t boxes:ARRAY[1]OF box_t',routines='ROUTINE pick:INTEGER BEGIN a.value=99 RETURN 1 END pick')
        v=p.run();self.assertEqual((v['A']['VALUE'],v['BOXES'][0]['ITEM']['VALUE']),(99,7.))

    def test_failed_conversion_skips_target_selector(self):
        prefix='TYPE in_t=STRUCTURE value:INTEGER ENDSTRUCTURE out_t=STRUCTURE value:BYTE ENDSTRUCTURE box_t=STRUCTURE item:out_t ENDSTRUCTURE'
        p,_=compile_program('visits=0 a.value=256 boxes[pick()].item=a',prefix=prefix,decl='a:in_t boxes:ARRAY[1]OF box_t visits:INTEGER',routines='ROUTINE pick:INTEGER BEGIN visits=1 RETURN 1 END pick')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)

    def test_return_captures_counter_before_cleanup(self):
        p,_=simple('b=make()',routines='ROUTINE make:out_t BEGIN FOR a.value=1 TO 2 DO RETURN a ENDFOR RETURN a END make');seed(p)
        self.assertEqual((p.run()['A']['VALUE'],p.snapshot()['B']['VALUE']),(U,1.))

    def test_converted_record_does_not_alias_counter(self):
        p,_=simple('n=0 FOR a.value=1 TO 2 DO work(a) n=n+a.value ENDFOR',routines='ROUTINE work(v:out_t) BEGIN v.value=99 END work');seed(p)
        self.assertEqual((p.run()['N'],p.snapshot()['A']['VALUE']),(3,U))

    def test_exact_record_alias_still_protects_counter(self):
        with self.assertRaises(TranslationError) as error:simple('FOR a.value=1 TO 2 DO work(a) ENDFOR',routines='ROUTINE work(v:in_t) BEGIN v.value=99 END work')
        self.assertEqual(error.exception.code,'E_FOR_COUNTER')

    def test_formal_timer_owns_only_private_record(self):
        p,_=simple('work(a)',second='INTEGER',routines='ROUTINE work(v:out_t) BEGIN CONNECT TIMER TO v.value v.value=99 END work',clock_us=lambda:0);seed(p)
        self.assertEqual((p.run()['A']['VALUE'],p._state.execution._timer_claims),(7,{}))

    def test_computed_using_owns_converted_fields(self):
        p,_=simple('USING make() DO value=99 n=TRUNC(value) ENDUSING',routines='ROUTINE make:out_t BEGIN RETURN a END make');seed(p)
        self.assertEqual((p.run()['A']['VALUE'],p.snapshot()['N']),(7,99))


class RecordArrayConversionTests(unittest.TestCase):
    TYPES='TYPE in_t=STRUCTURE value:INTEGER label:STRING[8] ENDSTRUCTURE out_t=STRUCTURE label:STRING[3] value:REAL ENDSTRUCTURE out_row=ARRAY[2]OF out_t'

    def build(self,body='b=a',routines='',**options):
        p,r=compile_program(body,prefix=self.TYPES,decl='a:ARRAY[1,2]OF in_t b:ARRAY[1]OF out_row n:INTEGER',routines=routines,**options)
        for i,item in enumerate(p._state.values['A'].values):item.values.update(VALUE=i+1,LABEL='abcdef')
        return p,r

    def test_arrays_use_receiver_fields_and_layout(self):
        p,_=self.build();self.assertEqual(p.run()['B'],[[{'LABEL':'abc','VALUE':1.},{'LABEL':'abc','VALUE':2.}]])
        self.assertEqual(p._state.values['B'].spec[2][3],'OUT_ROW')

    def test_partial_record_array_leaves_remain_missing(self):
        p,_=self.build();p._state.values['A'].values[-1].values['VALUE']=rt.UNINITIALIZED
        self.assertEqual(p.run()['B'][0][1]['VALUE'],U)

    def test_last_record_failure_preserves_whole_array(self):
        p,_=self.build();p._state.values['A'].values[-1].values['LABEL']='over capacity';old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_record_array_argument_is_private(self):
        p,_=self.build('work(a)',routines='ROUTINE work(v:ARRAY OF out_row) BEGIN v[1,1].value=99 n=TRUNC(v[1,1].value) END work')
        self.assertEqual((p.run()['A'][0][0]['VALUE'],p.snapshot()['N']),(1,99))

    def test_record_array_return_uses_declared_elements(self):
        p,_=self.build('b=make()',routines='ROUTINE make:ARRAY OF out_row BEGIN RETURN a END make')
        self.assertEqual(p.run()['B'][0][0]['VALUE'],1.)

    def test_generic_receiver_uses_actual_schema(self):
        p,_=self.build('work(b,a)',routines='ROUTINE work(dst:ARRAY[*,*]OF out_t;src:ARRAY[*,*]OF in_t) BEGIN dst=src END work')
        before=p._state.values['B'].spec;self.assertEqual(p.run()['B'][0][0]['VALUE'],1.);self.assertEqual(p._state.values['B'].spec,before)

    def test_known_shape_mismatch_remains_error(self):
        with self.assertRaises(TranslationError):compile_program('b=a',prefix=self.TYPES,decl='a:ARRAY[2,2]OF in_t b:ARRAY[1]OF out_row')

    def test_unknown_shape_mismatch_is_atomic(self):
        p,_=compile_program('work(b,a)',prefix=self.TYPES,decl='a:ARRAY[2,2]OF in_t b:ARRAY[1,4]OF out_t',routines='ROUTINE work(dst:ARRAY[*,*]OF out_t;src:ARRAY[*,*]OF in_t) BEGIN dst=src END work')
        old=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'logical dimensions'):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_receiver_record_children_keep_identity(self):
        p,_=self.build();array=p._state.values['B'];row=array.values[0];record=row.values[0];p.run()
        self.assertIs(p._state.values['B'],array);self.assertIs(array.values[0],row);self.assertIs(row.values[0],record)


class RecordSchemaBoundaryTests(unittest.TestCase):
    def test_missing_and_extra_fields_remain_rejected(self):
        for fields in ('value:REAL','value:REAL label:STRING[3] extra:INTEGER'):
            prefix='TYPE in_t=STRUCTURE value:INTEGER label:STRING[8] ENDSTRUCTURE out_t=STRUCTURE '+fields+' ENDSTRUCTURE'
            with self.assertRaises(TranslationError):compile_program('b=a',prefix=prefix,decl='a:in_t b:out_t')

    def test_field_renaming_is_not_inferred(self):
        prefix='TYPE in_t=STRUCTURE value:INTEGER ENDSTRUCTURE out_t=STRUCTURE renamed:REAL ENDSTRUCTURE'
        with self.assertRaises(TranslationError):compile_program('b=a',prefix=prefix,decl='a:in_t b:out_t')

    def test_boolean_and_real_to_integral_stay_rejected(self):
        for first,second in (('BOOLEAN','INTEGER'),('INTEGER','BOOLEAN'),('REAL','INTEGER')):
            with self.assertRaises(TranslationError):simple(first=first,second=second)

    def test_builtin_and_user_records_are_not_interchangeable(self):
        with self.assertRaises(TranslationError):compile_program('v=a',prefix='TYPE in_t=STRUCTURE x:REAL y:REAL z:REAL ENDSTRUCTURE',decl='a:in_t v:VECTOR')

    def test_model_fields_need_explicit_conversion(self):
        prefix='TYPE in_t=STRUCTURE value:JOINTPOS2 ENDSTRUCTURE out_t=STRUCTURE value:POSITION ENDSTRUCTURE'
        with self.assertRaises(TranslationError):compile_program('b=a',prefix=prefix,decl='a:in_t b:out_t')

    def test_resource_fields_remain_unavailable(self):
        for kind in ('FILE','PATH','QUEUE_TYPE'):
            with self.assertRaises(TranslationError):compile_program('b=a',prefix=f'TYPE in_t=STRUCTURE value:{kind} ENDSTRUCTURE',decl='a,b:in_t')

    def test_generic_runtime_helpers_remain_exact(self):
        p,_=simple();seed(p);target=p._state.types['B'];source=p._state.values['A']
        with rt._numeric_scope('pythonic'):
            for action in (lambda:rt.checked(target,source),lambda:rt.value_argument(target,source),lambda:rt.structure_value(target,source)):
                with self.assertRaises(rt.KarelRuntimeError):action()

    def test_byname_keeps_exact_record_schema(self):
        p,_=simple("e=77 work(BYNAME('','A',e))",routines='ROUTINE work(v:out_t) BEGIN END work');seed(p)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type does not match'):p.run()
        self.assertEqual(p.snapshot()['E'],77)

    def test_malformed_storage_rejects_before_destination(self):
        for change in ('fields','types','spec'):
            p,_=simple();seed(p);source=p._state.values['A'];old=p.snapshot()['B']
            if change=='fields':source.values.pop('LABEL')
            elif change=='types':source.types['VALUE']=('REAL',)
            else:source.spec=('STRUCTURE','FOREIGN',source.spec[2])
            with self.subTest(change=change),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['B'],old)

    def test_target_allocation_bound_precedes_copy(self):
        source_spec=('STRUCTURE','IN_T',(('J',('JOINTPOS',1)),));target_spec=('STRUCTURE','OUT_T',(('J',('JOINTPOS',9)),))
        source=rt.Array(('ARRAY',4000,source_spec))
        for item in source.values:item.values['J'].values[:]=[0.]
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):rt.convert_record_schema(('ARRAY',4000,target_spec),source,23)

    def test_schema_depth_guard_is_preserved(self):
        first=('INTEGER',);second=('REAL',)
        for i in range(64):
            first=('STRUCTURE','IN_'+str(i),(('VALUE',first),));second=('STRUCTURE','OUT_'+str(i),(('VALUE',second),))
        source=rt.Structure(first)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'64 levels'):rt.convert_record_schema(second,source,23)

    def test_malformed_target_is_source_located(self):
        p,_=simple();seed(p);target=('STRUCTURE','OUT_T',(('VALUE',('REAL',)),('VALUE',('REAL',))))
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'line 23'):rt.convert_record_schema(target,p._state.values['A'],23)

    def test_legacy_helper_and_source_guards_remain(self):
        p,_=simple();seed(p)
        with rt._numeric_scope('strict'),self.assertRaisesRegex(rt.KarelRuntimeError,'Pythonic'):rt.convert_record_schema(p._state.types['B'],p._state.values['A'])
        with self.assertRaises(TranslationError):legacy_translate('PROGRAM T TYPE one=STRUCTURE value:INTEGER ENDSTRUCTURE two=STRUCTURE value:INTEGER ENDSTRUCTURE VAR a:one b:two BEGIN b=a END T')

    def test_json_roundtrip_preserves_receiver_and_partial_values(self):
        body='IF UNINIT(done) THEN b=a done=TRUE ENDIF'
        p,_=simple(body);seed(p,rt.UNINITIALIZED);p.run();saved=json.loads(json.dumps(p._state.execution.to_config()))
        restored,_=simple(body,context=rt.ExecutionContext.from_config(saved));restored.run()
        self.assertEqual(restored.snapshot(),p.snapshot());self.assertEqual(restored._state.values['B'].spec,p._state.values['B'].spec)


class RecordSchemaLinkageTests(unittest.TestCase):
    def test_linked_interface_gets_private_converted_data(self):
        types='TYPE in_t=STRUCTURE value:INTEGER ENDSTRUCTURE out_t=STRUCTURE value:REAL ENDSTRUCTURE '
        lib='PROGRAM LIB '+types+' VAR seen:REAL ROUTINE work(v:out_t) BEGIN v.value=99 seen=v.value END work BEGIN END LIB'
        main='PROGRAM MAIN '+types+' VAR a:in_t ROUTINE work(v:out_t) FROM LIB BEGIN a.value=7 work(a) END MAIN'
        project=translate_project({'main':main,'lib':lib}).instantiate();project.run('MAIN')
        self.assertEqual((project.programs['MAIN'].snapshot()['A']['VALUE'],project.programs['LIB'].snapshot()['SEEN']),(7,99.))

    def test_mismatched_linked_declarations_stay_rejected(self):
        types='TYPE in_t=STRUCTURE value:INTEGER ENDSTRUCTURE out_t=STRUCTURE value:REAL ENDSTRUCTURE '
        lib='PROGRAM LIB '+types+' VAR n:INTEGER ROUTINE work(v:in_t) BEGIN END work BEGIN END LIB'
        main='PROGRAM MAIN '+types+' VAR a:in_t ROUTINE work(v:out_t) FROM LIB BEGIN work(a) END MAIN'
        with self.assertRaises(ValueError):translate_project({'main':main,'lib':lib}).instantiate()

    def test_callback_receives_private_receiver_record(self):
        seen=[]
        def work(ref):seen.append(ref.spec);ref.raw().values['VALUE']=99.
        p,_=simple('work(a)',routines='ROUTINE work(v:out_t) FROM LIB',context=rt.ExecutionContext(externals={('LIB','WORK'):work}));seed(p);p.run()
        self.assertEqual((seen,p.snapshot()['A']['VALUE']),([p._state.types['B']],7))

    def test_raw_callback_result_must_match_declared_schema(self):
        p,_=simple();seed(p);source=p._state.values['A']
        task,_=simple('b=make()',routines='ROUTINE make:out_t FROM LIB',context=rt.ExecutionContext(externals={('LIB','MAKE'):lambda:source}))
        with self.assertRaises(rt.KarelRuntimeError):task.run()
        self.assertEqual(task.snapshot()['B']['VALUE'],U)


if __name__=='__main__':unittest.main()


class RecordSchemaReportTests(unittest.TestCase):
    def test_sites_identify_assignment_argument_and_return(self):
        p,result=simple('b=work(a)',second='INTEGER',routines='ROUTINE work(v:out_t):in_t BEGIN RETURN v END work');seed(p)
        rows=result.report['record_schema_conversions'];self.assertEqual([row['operation'] for row in rows],['RETURN','ARGUMENT','ASSIGNMENT'])
        for row in rows:
            self.assertTrue(row['evaluated_once']);self.assertTrue(row['independent_value']);self.assertGreater(row['line'],0)
            self.assertEqual(row['conversion_kind'],'structure')
        self.assertTrue(rows[0]['before_cleanup']);json.dumps(result.report)

    def test_policy_is_explicit_about_context_and_exact_helpers(self):
        _,result=simple();policy=result.report['record_schema_policy']
        self.assertFalse(policy['controller_validated']);self.assertEqual(policy['guide'],'docs/record-schema-conversions.md')
        for word in ('BYNAME','callback','linked'):self.assertIn(word,policy['exact'])
        self.assertIn('model-backed',policy['limits']);self.assertIn('declared source schema',policy['capture'])

    def test_generic_receiver_site_reports_dynamic_schema(self):
        types='TYPE one=STRUCTURE n:INTEGER ENDSTRUCTURE two=STRUCTURE n:REAL ENDSTRUCTURE'
        _,result=compile_program('work(b,a)',prefix=types,decl='a:ARRAY[2]OF one b:ARRAY[2]OF two',routines='ROUTINE work(dst:ARRAY OF two;src:ARRAY OF one) BEGIN dst=src END work')
        row=result.report['record_schema_conversions'][0]
        self.assertTrue(row['actual_receiver_schema']);self.assertEqual((row['operation'],row['conversion_kind']),('ASSIGNMENT','record_array'))


class RecordSchemaDeclaredSourceTests(unittest.TestCase):
    def test_declared_source_checked_for_arguments_and_generic_assignments(self):
        p,_=simple('n=0 work(a)',routines='ROUTINE work(v:out_t) BEGIN n=1 END work');seed(p)
        a=p._state.values['A'];a.spec=('STRUCTURE','FOREIGN',a.spec[2])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'declared schema'):p.run()
        self.assertEqual((p.snapshot()['N'],p._state.local_frames),(0,[]))
        for target in ('INTEGER','REAL'):
            types=f'TYPE one=STRUCTURE n:INTEGER ENDSTRUCTURE two=STRUCTURE n:{target} ENDSTRUCTURE'
            p,_=compile_program('work(b,a)',prefix=types,decl='a:ARRAY[2]OF one b:ARRAY[2]OF two',routines='ROUTINE work(dst:ARRAY OF two;src:ARRAY OF one) BEGIN dst=src END work')
            foreign=rt.Array(p._state.types['B']);foreign.values[0].values['N']=7 if target=='INTEGER' else 7.
            p._state.values['A']=foreign;before=p.snapshot()['B']
            with self.subTest(target=target),self.assertRaisesRegex(rt.KarelRuntimeError,'declared schema'):p.run()
            self.assertEqual(p.snapshot()['B'],before)
        for schema in ((),('ARRAY',0,('INTEGER',)),('ARRAY',2,('STRUCTURE','BAD',()))):
            p,_=compile_program('work(b,a)',prefix=types,decl='a:ARRAY[2]OF one b:ARRAY[2]OF two',routines='ROUTINE work(dst:ARRAY OF two;src:ARRAY OF one) BEGIN dst=src END work')
            before=p.snapshot()['B'];p._state.values['A'].spec=schema
            with self.subTest(malformed=schema),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['B'],before)

    def test_return_checks_declared_source_before_publication(self):
        p,_=simple('b=make()',routines='ROUTINE make:out_t BEGIN RETURN a END make');seed(p)
        a=p._state.values['A'];a.spec=('STRUCTURE','FOREIGN',a.spec[2]);before=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'declared schema'):p.run()
        self.assertEqual((p.snapshot()['B'],p._state.local_frames),(before,[]))

    def test_nested_array_model_fields_are_not_implicitly_converted(self):
        types='TYPE in_t=STRUCTURE values:ARRAY[2]OF JOINTPOS2 ENDSTRUCTURE out_t=STRUCTURE values:ARRAY[2]OF POSITION ENDSTRUCTURE'
        with self.assertRaises(TranslationError):compile_program('b=a',prefix=types,decl='a:in_t b:out_t')
