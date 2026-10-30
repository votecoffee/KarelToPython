"""Authored numeric ARRAY source conversions, ordering, domains and ownership."""
import json
import unittest
from karel2py import translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source

U={'uninitialized':True}
B={'unknown_byte':True}
INTEGRAL=('INTEGER','BYTE','SHORT')
PAIRS=tuple((a,b) for a in INTEGRAL for b in (*INTEGRAL,'REAL') if a!=b)


def build(body='b=a',first='INTEGER',second='REAL',*,shape='2',**options):
    return compile_program(body,decl=f'a:ARRAY[{shape}]OF {first} b:ARRAY[{shape}]OF {second} n,e,s,index_value,visits:INTEGER done:BOOLEAN',**options)


def initialize(program,values=(1,2)):
    program._state.values['A'].values[:]=values
    return program


class NumericArrayAssignmentTests(unittest.TestCase):
    def test_all_integral_domain_pairs_and_real_promotions(self):
        for first,second in PAIRS:
            with self.subTest(first=first,second=second):
                p,_=build(first=first,second=second);initialize(p,(0,127));values=p.run()['B']
                self.assertEqual(values,[0.,127.] if second=='REAL' else [0,127])
                self.assertTrue(all(type(v) is (float if second=='REAL' else int) for v in values))

    def test_missing_leaves_propagate_without_default_numbers(self):
        for first,second in PAIRS:
            with self.subTest(first=first,second=second):
                p,_=build(first=first,second=second);initialize(p,(7,rt.UNINITIALIZED))
                self.assertEqual(p.run()['B'],[7. if second=='REAL' else 7,U])

    def test_short_sentinel_narrowing_preserves_missing_semantics(self):
        p,_=build(second='SHORT');initialize(p,(32767,32766))
        self.assertEqual(p.run()['B'],[U,32766])

    def test_source_short_sentinel_normalizes_before_promotion(self):
        p,_=build(first='SHORT');initialize(p,(32767,7))
        self.assertEqual(p.run()['B'],[U,7.])

    def test_unknown_byte_cannot_become_a_numeric_value(self):
        for second in ('INTEGER','SHORT','REAL'):
            with self.subTest(second=second):
                p,_=build(first='BYTE',second=second);initialize(p,(7,rt.UNKNOWN_BYTE));old=p.snapshot()['B']
                with self.assertRaisesRegex(rt.KarelRuntimeError,'BYTE.*unknown'):p.run()
                self.assertEqual(p.snapshot()['B'],old)

    def test_known_source_domain_is_checked_before_target_conversion(self):
        for first,value in [('BYTE',256),('BYTE',-1),('SHORT',-32769),('INTEGER',2147483647),('INTEGER',True),('INTEGER',1.)]:
            with self.subTest(first=first,value=value):
                p,_=build(first=first);initialize(p,(1,value));old=p.snapshot()['B']
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertEqual(p.snapshot()['B'],old)

    def test_late_narrowing_overflow_preserves_entire_receiver(self):
        p,_=build(second='BYTE');initialize(p,(7,256));p._state.values['B'].values[:]=[88,99]
        with self.assertRaisesRegex(rt.KarelRuntimeError,'0..255'):p.run()
        self.assertEqual((p.snapshot()['A'],p.snapshot()['B']),([7,256],[88,99]))

    def test_negative_to_byte_fails_without_wrapping(self):
        p,_=build(first='SHORT',second='BYTE');initialize(p,(7,-1))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],[B,B])

    def test_rank_one_two_and_three_preserve_shape(self):
        for text in ('2','1,2','1,1,2'):
            with self.subTest(shape=text):
                p,_=build(shape=text);initialize(p);p.run()
                self.assertEqual(p._state.values['B'].shape,p._state.values['A'].shape)
                self.assertEqual(p._state.values['B'].values,[1.,2.])

    def test_receiver_array_and_element_reference_identities_survive(self):
        p,_=build();initialize(p);array=p._state.values['B'];values=array.values;ref=rt.index_reference(array,1)
        p.run();self.assertIs(p._state.values['B'],array);self.assertIs(array.values,values);self.assertEqual(ref.raw(),1.)

    def test_rhs_conversion_precedes_target_selector_effects(self):
        p,_=compile_program('items[pick()].points=a',prefix='TYPE box_t=STRUCTURE points:ARRAY[2]OF REAL ENDSTRUCTURE',decl='a:ARRAY[2]OF INTEGER items:ARRAY[1]OF box_t n:INTEGER',routines='ROUTINE pick:INTEGER BEGIN a[1]=99 RETURN 1 END pick')
        initialize(p);v=p.run();self.assertEqual((v['A'],v['ITEMS'][0]['POINTS']),([99,2],[1.,2.]))

    def test_failed_conversion_skips_target_selector(self):
        p,_=compile_program('n=0 items[pick()].points=a',prefix='TYPE box_t=STRUCTURE points:ARRAY[2]OF BYTE ENDSTRUCTURE',decl='a:ARRAY[2]OF INTEGER items:ARRAY[1]OF box_t n:INTEGER',routines='ROUTINE pick:INTEGER BEGIN n=n+1 RETURN 1 END pick')
        initialize(p,(7,256));old=p.snapshot()['ITEMS']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['ITEMS']),(0,old))

    def test_source_function_executes_once(self):
        p,_=build('n=0 b=make()',routines='ROUTINE make:ARRAY OF INTEGER BEGIN n=n+1 RETURN a END make');initialize(p)
        self.assertEqual((p.run()['B'],p.snapshot()['N']),([1.,2.],1))

    def test_anonymous_numeric_array_fields_convert_separately(self):
        p,_=compile_program('right.points=left.points',prefix='TYPE left_t=STRUCTURE points:ARRAY[2]OF SHORT ENDSTRUCTURE right_t=STRUCTURE points:ARRAY[2]OF REAL ENDSTRUCTURE',decl='left:left_t right:right_t')
        p._state.values['LEFT'].values['POINTS'].values[:]=[-2,7]
        self.assertEqual(p.run()['RIGHT']['POINTS'],[-2.,7.])

    def test_transparent_scalar_alias_elements_keep_numeric_domains(self):
        p,_=build(first='octet',prefix='TYPE octet=BYTE');initialize(p,(1,255))
        self.assertEqual(p.run()['B'],[1.,255.])

    def test_same_type_missing_and_unknown_byte_copies_are_unchanged(self):
        p,_=build(first='BYTE',second='BYTE');initialize(p,(1,rt.UNKNOWN_BYTE))
        self.assertEqual(p.run()['B'],[1,B])

    def test_known_shape_and_rank_mismatch_stay_rejected(self):
        for decl in ('a:ARRAY[2]OF INTEGER b:ARRAY[3]OF REAL','a:ARRAY[2]OF INTEGER b:ARRAY[1,2]OF REAL'):
            with self.subTest(decl=decl),self.assertRaises(TranslationError):compile_program('b=a',decl=decl)

    def test_named_source_and_receiver_keep_their_own_converted_schema(self):
        for prefix,decl in [('TYPE row_t=ARRAY[2]OF INTEGER','a:row_t b:ARRAY[2]OF REAL'),('TYPE row_t=ARRAY[2]OF REAL','a:ARRAY[2]OF INTEGER b:row_t')]:
            with self.subTest(decl=decl):
                p,_=compile_program('b=a',prefix=prefix,decl=decl);initialize(p);original=p._state.values['A'].spec
                self.assertEqual(p.run()['B'],[1.,2.]);self.assertEqual(p._state.values['A'].spec,original)
                self.assertEqual(p._state.values['B'].spec,p._state.types['B'])

    def test_real_to_integral_and_boolean_numeric_pairs_remain_rejected(self):
        for first,second in [('REAL','INTEGER'),('REAL','BYTE'),('REAL','SHORT'),('BOOLEAN','REAL'),('INTEGER','BOOLEAN'),('STRING[4]','REAL')]:
            with self.subTest(first=first,second=second),self.assertRaises(TranslationError):build(first=first,second=second)


class NumericArrayInterfaceTests(unittest.TestCase):
    def test_bare_converted_argument_is_private_and_writable(self):
        p,_=build('work(a)',routines='ROUTINE work(v:ARRAY OF REAL) BEGIN v[1]=99 n=TRUNC(v[2]) END work');initialize(p)
        self.assertEqual((p.run()['A'],p.snapshot()['N']),([1,2],2))

    def test_exact_bare_argument_retains_reference_semantics(self):
        p,_=build('work(a)',routines='ROUTINE work(v:ARRAY OF INTEGER) BEGIN v[1]=99 END work');initialize(p)
        self.assertEqual(p.run()['A'],[99,2])

    def test_grouped_converted_argument_is_private(self):
        p,_=build('work((a))',routines='ROUTINE work(v:ARRAY OF BYTE) BEGIN v[1]=99 END work');initialize(p)
        self.assertEqual(p.run()['A'],[1,2])

    def test_conversion_finishes_before_later_argument_effects(self):
        routines='ROUTINE change:INTEGER BEGIN a[1]=99 RETURN 0 END change ROUTINE work(v:ARRAY OF REAL;ignored:INTEGER) BEGIN n=TRUNC(v[1]) END work'
        p,_=build('work(a,change())',routines=routines);initialize(p)
        self.assertEqual((p.run()['A'],p.snapshot()['N']),([99,2],1))

    def test_failed_argument_skips_later_argument_and_callee(self):
        routines='ROUTINE later:INTEGER BEGIN n=1 RETURN 0 END later ROUTINE work(v:ARRAY OF BYTE;ignored:INTEGER) BEGIN n=2 END work'
        p,_=build('n=0 work(a,later())',routines=routines);initialize(p,(1,256))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p._state.local_frames),(0,[]))

    def test_forwarded_private_array_aliases_only_that_copy(self):
        routines='ROUTINE inner(v:ARRAY OF REAL) BEGIN v[1]=99 END inner ROUTINE work(v:ARRAY OF REAL) BEGIN inner(v) n=TRUNC(v[1]) END work'
        p,_=build('work(a)',routines=routines);initialize(p)
        self.assertEqual((p.run()['A'],p.snapshot()['N']),([1,2],99))

    def test_partial_argument_can_be_initialized_privately(self):
        p,_=build('work(a)',routines='ROUTINE work(v:ARRAY OF REAL) BEGIN IF UNINIT(v[2]) THEN v[2]=9 ENDIF n=TRUNC(v[2]) END work');initialize(p,(1,rt.UNINITIALIZED))
        self.assertEqual((p.run()['A'],p.snapshot()['N']),([1,U],9))

    def test_retained_handler_mutates_only_converted_argument(self):
        routines='ROUTINE retain(v:ARRAY OF REAL) BEGIN CONDITION[1]: WHEN EVENT[1] DO v[1]=99 n=TRUNC(v[1]) ENDCONDITION END retain'
        p,_=build('retain(a) ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=routines);initialize(p)
        self.assertEqual((p.run()['A'],p.snapshot()['N']),([1,2],99))

    def test_callee_failure_preserves_earlier_effects_without_copyback(self):
        p,_=build('work(a)',routines='ROUTINE work(v:ARRAY OF REAL) BEGIN v[1]=99 n=77 s=1 DIV 0 END work');initialize(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['A'],p.snapshot()['N'],p._state.local_frames),([1,2],77,[]))

    def test_retained_converted_argument_does_not_escape_private_counter_root(self):
        prefix='TYPE box_t=STRUCTURE points:ARRAY[2]OF INTEGER count:INTEGER ENDSTRUCTURE'
        routines='ROUTINE make:box_t BEGIN RETURN seed END make ROUTINE retain(v:ARRAY OF REAL) BEGIN CONDITION[1]: WHEN EVENT[1] DO v[1]=99 s=TRUNC(v[1]) ENDCONDITION END retain'
        body='seed.points[1]=7 seed.points[2]=8 n=0 USING make() DO retain(points) FOR count=1 TO 2 DO n=n+count ENDFOR ENDUSING ENABLE CONDITION[1] SIGNAL EVENT[1]'
        p,_=compile_program(body,prefix=prefix,decl='seed:box_t n,s:INTEGER',routines=routines)
        self.assertEqual((p.run()['SEED']['POINTS'],p.snapshot()['N'],p.snapshot()['S']),([7,8],3,99))

    def test_unknown_byte_argument_fails_before_entry(self):
        p,_=build('n=0 work(a)',first='BYTE',routines='ROUTINE work(v:ARRAY OF REAL) BEGIN n=1 END work')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],0)

    def test_converted_argument_survives_pause_without_copyback(self):
        p,_=build('work(a) done=TRUE',routines='ROUTINE work(v:ARRAY OF REAL) BEGIN v[1]=99 PAUSE n=TRUNC(v[1]) END work');initialize(p)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['A'],[1,2]);self.assertEqual(p.resume()['N'],99);self.assertEqual(p._state.local_frames,[])

    def test_stop_does_not_copy_private_mutation_back(self):
        p,_=build('work(a)',routines='ROUTINE work(v:ARRAY OF BYTE) BEGIN v[1]=99 PAUSE END work');initialize(p)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual((p.snapshot()['A'],p._state.local_frames),([1,2],[]))

    def test_return_promotes_to_independent_concrete_result(self):
        p,_=build('b=make() a[1]=99',routines='ROUTINE make:ARRAY OF REAL BEGIN RETURN a END make');initialize(p)
        self.assertEqual((p.run()['B'],p.snapshot()['A']),([1.,2.],[99,2]))

    def test_composed_narrow_argument_and_promoted_return(self):
        p,_=build('b=work(a)',routines='ROUTINE work(v:ARRAY OF SHORT):ARRAY OF REAL BEGIN v[1]=-7 RETURN v END work');initialize(p)
        self.assertEqual((p.run()['B'],p.snapshot()['A']),([-7.,2.],[1,2]))

    def test_wildcard_matrix_result_inherits_concrete_dimensions(self):
        p,_=build('b=make()',shape='1,2',routines='ROUTINE make:ARRAY[*,*]OF REAL BEGIN RETURN a END make');initialize(p)
        self.assertEqual(p.run()['B'],[[1.,2.]])

    def test_return_capture_precedes_active_counter_cleanup(self):
        routines='ROUTINE make:ARRAY OF REAL BEGIN FOR a[1]=1 TO 2 DO RETURN a ENDFOR END make'
        p,_=build('b=make()',routines=routines);initialize(p)
        self.assertEqual((p.run()['B'],p.snapshot()['A']),([1.,2.],[U,2]))

    def test_failed_return_cleans_counter_and_keeps_destination(self):
        p,_=build('b=make()',second='BYTE',routines='ROUTINE make:ARRAY OF BYTE BEGIN FOR a[1]=1 TO 2 DO RETURN a ENDFOR END make');initialize(p,(7,256));old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['B'],p.snapshot()['A'],p._state.local_frames),(old,[U,256],[]))

    def test_dynamic_receiver_length_check_remains_atomic(self):
        p,_=compile_program('work(b)',decl='a:ARRAY[3]OF INTEGER b:ARRAY[2]OF REAL',routines='ROUTINE work(v:ARRAY OF REAL) BEGIN v=a END work')
        initialize(p,(1,2,3));old=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'matching logical dimensions'):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_writable_converted_argument_does_not_alias_active_counter_root(self):
        routines='ROUTINE edit(v:ARRAY OF REAL) BEGIN v[1]=99 END edit'
        p,_=build('n=0 FOR a[1]=1 TO 2 DO edit(a) n=n+a[1] ENDFOR',routines=routines);initialize(p)
        self.assertEqual((p.run()['N'],p.snapshot()['A']),(3,[U,2]))

    def test_converted_argument_still_obeys_explicit_global_write_guard(self):
        with self.assertRaises(TranslationError) as error:
            build('FOR a[1]=1 TO 2 DO edit(a) ENDFOR',routines='ROUTINE edit(v:ARRAY OF REAL) BEGIN a[2]=99 END edit')
        self.assertEqual(error.exception.code,'E_FOR_COUNTER')

    def test_named_source_generic_numeric_conversion_is_private(self):
        p,_=compile_program('work(a)',decl='a:row_t',prefix='TYPE row_t=ARRAY[2]OF INTEGER',routines='ROUTINE work(v:ARRAY OF REAL) BEGIN v[1]=99 END work');initialize(p)
        self.assertEqual(p.run()['A'],[1,2]);self.assertEqual(rt.array_identity(p._state.values['A'].spec),'ROW_T')

    def test_byname_retains_exact_declared_type(self):
        p,_=build("e=77 work(BYNAME('','A',e))",routines='ROUTINE work(v:ARRAY OF REAL) BEGIN END work');initialize(p)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type does not match'):p.run()
        self.assertEqual(p.snapshot()['E'],77)

    def test_callback_argument_receives_private_declared_numeric_array(self):
        seen=[]
        def callback(ref):seen.append(ref.spec);ref.raw().set(1,99.)
        p,_=build('work(a)',routines='ROUTINE work(v:ARRAY OF REAL) FROM LIB',context=rt.ExecutionContext(externals={('LIB','WORK'):callback}));initialize(p)
        self.assertEqual(p.run()['A'],[1,2]);self.assertEqual(seen,[('ARRAY',2,('REAL',))])

    def test_raw_callback_return_does_not_gain_implicit_conversion(self):
        raw=rt.Array(('ARRAY',2,('INTEGER',)));raw.values[:]=[1,2]
        p,_=build('b=make()',routines='ROUTINE make:ARRAY OF REAL FROM LIB',context=rt.ExecutionContext(externals={('LIB','MAKE'):lambda:raw}))
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_linked_routine_converts_actual_and_return_without_copyback(self):
        project=translate_project({'main':source('MAIN','b=work(a)',decl='a:ARRAY[2]OF INTEGER b:ARRAY[2]OF REAL',routines='ROUTINE work(v:ARRAY OF SHORT):ARRAY OF REAL FROM LIB'),
            'lib':source('LIB','',routines='ROUTINE work(v:ARRAY OF SHORT):ARRAY OF REAL BEGIN v[1]=-7 RETURN v END work')}).instantiate()
        initialize(project.programs['MAIN']);project.run('MAIN');v=project.programs['MAIN'].snapshot()
        self.assertEqual((v['A'],v['B']),([1,2],[-7.,2.]))

    def test_linked_signature_identity_stays_exact(self):
        with self.assertRaisesRegex(ValueError,'type mismatch'):
            translate_project({'main':source('MAIN','',routines='ROUTINE work(v:ARRAY OF REAL) FROM LIB'),
                'lib':source('LIB','',routines='ROUTINE work(v:ARRAY OF INTEGER) BEGIN END work')}).instantiate()

    def test_report_tracks_all_three_conversion_boundaries(self):
        _,r=build('b=work(a)',routines='ROUTINE work(v:ARRAY OF SHORT):ARRAY OF REAL BEGIN RETURN v END work')
        self.assertEqual({row['operation'] for row in r.report['numeric_array_conversions']},{'ARGUMENT','RETURN'})
        _,r=build();self.assertEqual(r.report['numeric_array_conversions'][0]['operation'],'ASSIGNMENT')
        self.assertFalse(r.report['numeric_array_policy']['controller_validated']);json.dumps(r.report,allow_nan=False)


class NumericArrayRuntimeTests(unittest.TestCase):
    def array(self,kind='INTEGER',values=(1,2)):
        a=rt.Array(('ARRAY',len(values),(kind,)));a.values[:]=values;return a

    def convert(self,target,values,line=23):
        with rt._numeric_scope('pythonic'):return rt.convert_numeric_array(target,values,line)

    def test_conversion_helper_returns_detached_concrete_storage(self):
        a=self.array();b=self.convert(('ARRAY',None,('REAL',)),a)
        self.assertEqual((b.spec,b.values),(('ARRAY',2,('REAL',)),[1.,2.]))
        b.values[0]=99.;self.assertEqual(a.values,[1,2])

    def test_generic_checked_argument_and_result_helpers_stay_exact(self):
        a=self.array()
        with rt._numeric_scope('pythonic'):
            for operation in (lambda:rt.checked(('ARRAY',2,('REAL',)),a),lambda:rt.value_argument(('ARRAY',None,('REAL',)),a),lambda:rt.array_result(('ARRAY',None,('REAL',)),a)):
                with self.subTest(operation=operation),self.assertRaises(rt.KarelRuntimeError):operation()

    def test_malformed_shape_and_storage_are_rejected_with_source_line(self):
        for modify in (lambda a:setattr(a,'shape',(1,2)),lambda a:a.values.append(3),lambda a:setattr(a,'values',(1,2))):
            a=self.array();modify(a)
            with self.subTest(modify=modify),self.assertRaisesRegex(rt.KarelRuntimeError,'line 23'):self.convert(('ARRAY',2,('REAL',)),a)

    def test_allocations_over_leaf_bound_fail_before_copy(self):
        a=object.__new__(rt.Array);a.spec=('ARRAY',(128,256),('INTEGER',));a.shape=(128,256);a.values=[0]*32768
        with self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):self.convert(('ARRAY',(128,256),('REAL',)),a)

    def test_named_array_specs_classify_only_supported_numeric_changes(self):
        for target,source_spec in [(('ARRAY',2,('REAL',)),('ARRAY',2,('INTEGER',),'ROW')), (('ARRAY',2,('REAL',),'ROW'),('ARRAY',2,('INTEGER',)))]:
            self.assertEqual(rt.numeric_array_kind(target,source_spec),'promote_real')
        for target,source_spec in [(('ARRAY',2,('INTEGER',)),('ARRAY',2,('REAL',))), (('ARRAY',2,('REAL',)),('ARRAY',2,('BOOLEAN',)))]:
            with self.subTest(target=target,source=source_spec):self.assertIsNone(rt.numeric_array_kind(target,source_spec))

    def test_legacy_conversion_helper_remains_unavailable(self):
        with rt._numeric_scope('strict'),self.assertRaisesRegex(rt.KarelRuntimeError,'Pythonic'):rt.convert_numeric_array(('ARRAY',2,('REAL',)),self.array())

    def test_legacy_source_numeric_array_guards_are_preserved(self):
        for body,routine in [('b=a',''),('work(a)','ROUTINE work(v:ARRAY OF REAL) BEGIN END work'),('','ROUTINE make:ARRAY OF REAL BEGIN RETURN a END make')]:
            with self.subTest(body=body),self.assertRaises(TranslationError):legacy_translate('PROGRAM T VAR a:ARRAY[2]OF INTEGER b:ARRAY[2]OF REAL '+routine+' BEGIN '+body+' END T')


if __name__=='__main__':unittest.main()
