"""Authored positional ARRAY changes, private interfaces and atomic typed prefixes."""
import copy
import json
import math
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_cartesian_interfaces import value as pose,snapshot_x
from tests.test_extended_services import compile_program
from tests.test_joint_interoperability import joint,model_context
from tests.test_project_scheduler import source
from tests.test_variable_transfers import transfer

KINDS=('POSITION','XYZWPR','XYZWPREXT')
PAIRS=tuple((a,b)for a in KINDS for b in KINDS if a!=b)
U={'uninitialized':True}


def data(kind,count=2,shape=None):
    spec=('JOINTPOS',kind)if type(kind)is int else(kind,)
    result=rt.Array(('ARRAY',shape if shape is not None else count,spec))
    result.values[:]=[joint([float(i+1)]+[0.]*(kind-1))if type(kind)is int else pose(kind,(float(i+1),2.,3.),(0.,0.,90.))for i in range(len(result.values))]
    return result


def build(body='b=a',first='XYZWPR',second='POSITION',*,shape='2',**options):
    return compile_program(body,decl=f'a:ARRAY[{shape}] OF {first} b:ARRAY[{shape}] OF {second} n,e,s:INTEGER done:BOOLEAN',**options)


def assign(task,first='XYZWPR',second='POSITION',shape=None):
    task._state.values['A']=data(first,shape=shape)
    return task


class PositionalArrayAssignmentTests(unittest.TestCase):
    def test_all_cartesian_pairs_and_three_ranks(self):
        for first,second in PAIRS:
            for shape,text in [(2,'2'),((1,2),'1,2'),((1,1,2),'1,1,2')]:
                with self.subTest(first=first,second=second,shape=shape):
                    p,_=build(first=first,second=second,shape=text);assign(p,first,shape=shape);old=p.snapshot()['A'];values=p.run()
                    items=p._state.values['B'].values
                    self.assertEqual(p.snapshot()['A'],old);self.assertEqual([snapshot_x(rt.snapshot_value(v),second)for v in items],[1.,2.])
                    self.assertTrue(all(v.spec==(second,)for v in items));self.assertIsNone(p._state.execution.robot)
                    if second=='XYZWPREXT':self.assertTrue(all(v.values['EXT1']==0. for v in items))

    def test_matrix_columns_have_independent_expected_rotation(self):
        p,_=build();assign(p);v=p.run()['B'][0]
        self.assertAlmostEqual(v['NORMAL']['X'],0.,places=12);self.assertAlmostEqual(v['NORMAL']['Y'],1.,places=12)
        self.assertAlmostEqual(v['ORIENT']['X'],-1.,places=12);self.assertAlmostEqual(v['ORIENT']['Y'],0.,places=12)
        self.assertEqual(v['APPROACH'],{'X':0.,'Y':0.,'Z':1.})

    def test_assignment_preserves_receiver_array_element_and_child_identities(self):
        p,_=build();assign(p);a=p._state.values['B'];element=a.values[0];location=element.values['LOCATION'];p.run()
        self.assertIs(p._state.values['B'],a);self.assertIs(a.values[0],element);self.assertIs(element.values['LOCATION'],location)

    def test_same_type_partial_arrays_keep_existing_copy_contract(self):
        p,_=build(first='XYZWPR',second='XYZWPR');self.assertEqual(p.run()['B'][0]['X'],U)

    def test_all_joint_width_pairs_pad_or_remove_only_zeros(self):
        for first in range(1,10):
            for second in range(1,10):
                with self.subTest(first=first,second=second):
                    p,_=build(first=f'JOINTPOS{first}',second=f'JOINTPOS{second}');assign(p,first);values=p.run()
                    self.assertEqual(values['B'][0]['axes'],[1.]+[0.]*(second-1));self.assertEqual(values['B'][1]['axes'],[2.]+[0.]*(second-1))

    def test_nonzero_joint_narrowing_preserves_entire_receiver(self):
        p,_=build(first='JOINTPOS4',second='JOINTPOS2');assign(p,4);p._state.values['A'].values[1].values[3]=1.
        old=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'zero discarded'):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_failed_last_element_skips_target_selector_and_keeps_storage(self):
        p,_=compile_program('n=0 items[at()].points=a',prefix='TYPE box_t=STRUCTURE points:ARRAY[2] OF POSITION ENDSTRUCTURE',decl='a:ARRAY[2] OF XYZWPR items:ARRAY[1] OF box_t n:INTEGER',routines='ROUTINE at:INTEGER BEGIN n=n+1 RETURN 1 END at')
        assign(p);p._state.values['A'].values[1].values['X']=rt.UNINITIALIZED;old=p.snapshot()['ITEMS']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['ITEMS']),(0,old))

    def test_invalid_geometry_config_and_external_fields_reject_atomically(self):
        for kind,change in [('XYZWPR',lambda v:v.values.update(X=math.inf)),('XYZWPREXT',lambda v:v.values.update(EXT3=rt.UNINITIALIZED)),('POSITION',lambda v:v.values['NORMAL'].values.update(X=7.)),('XYZWPR',lambda v:v.values['CONFIG_DATA'].values.update(FLIP=rt.UNINITIALIZED))]:
            with self.subTest(kind=kind):
                second='XYZWPREXT'if kind!='XYZWPREXT'else'POSITION';p,_=build(first=kind,second=second);assign(p,kind);change(p._state.values['A'].values[-1]);old=p.snapshot()['B']
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertEqual(p.snapshot()['B'],old)

    def test_rhs_is_captured_before_target_selector_changes_source(self):
        p,_=compile_program('items[at()].points=a',prefix='TYPE box_t=STRUCTURE points:ARRAY[2] OF POSITION ENDSTRUCTURE',decl='a:ARRAY[2] OF XYZWPR items:ARRAY[1] OF box_t',routines='ROUTINE at:INTEGER BEGIN a[1].x=99 RETURN 1 END at')
        assign(p);v=p.run();self.assertEqual((v['A'][0]['X'],v['ITEMS'][0]['POINTS'][0]['LOCATION']['X']),(99,1.))

    def test_anonymous_array_fields_can_change_representation(self):
        p,_=compile_program('b.points=a.points',prefix='TYPE a_t=STRUCTURE points:ARRAY[2] OF XYZWPR ENDSTRUCTURE b_t=STRUCTURE points:ARRAY[2] OF POSITION ENDSTRUCTURE',decl='a:a_t b:b_t')
        p._state.values['A'].values['POINTS']=data('XYZWPR');self.assertEqual(p.run()['B']['POINTS'][1]['LOCATION']['X'],2.)

    def test_shape_and_rank_mismatch_do_not_flatten(self):
        for decl in ['a:ARRAY[2]OF XYZWPR b:ARRAY[3]OF POSITION','a:ARRAY[2]OF XYZWPR b:ARRAY[1,2]OF POSITION']:
            with self.subTest(decl=decl),self.assertRaises(TranslationError):compile_program('b=a',decl=decl)

    def test_named_source_and_target_arrays_keep_receiver_identity(self):
        for prefix,decl in [('TYPE row_t=ARRAY[2]OF XYZWPR','a:row_t b:ARRAY[2]OF POSITION'),('TYPE row_t=ARRAY[2]OF POSITION','a:ARRAY[2]OF XYZWPR b:row_t')]:
            with self.subTest(decl=decl):
                p,_=compile_program('b=a',prefix=prefix,decl=decl);p._state.values['A'].values[:]=data('XYZWPR').values;before=p._state.values['A'].spec
                self.assertEqual(p.run()['B'][1]['LOCATION']['X'],2.);self.assertEqual(p._state.values['A'].spec,before)
                self.assertEqual(p._state.values['B'].spec,p._state.types['B'])

    def test_model_does_not_enable_rank_changing_array_conversion(self):
        with self.assertRaises(TranslationError):compile_program('b=a',decl='a:ARRAY[2]OF JOINTPOS2 b:ARRAY[1,2]OF POSITION',context=model_context())

    def test_assignment_from_function_evaluates_body_once(self):
        p,_=build('n=0 b=make()',routines='ROUTINE make:ARRAY OF XYZWPR BEGIN n=n+1 RETURN a END make');assign(p)
        self.assertEqual(p.run()['N'],1)


class PositionalArrayInterfaceTests(unittest.TestCase):
    def test_converted_reference_actual_gets_private_writable_array(self):
        p,_=build('work(a)',routines='ROUTINE work(v:ARRAY OF POSITION) BEGIN v[1].location.x=99 n=ARRAY_LEN(v) END work');assign(p)
        self.assertEqual((p.run()['A'][0]['X'],p.snapshot()['N']),(1.,2))

    def test_exact_bare_actual_keeps_alias(self):
        p,_=build('work(a)',routines='ROUTINE work(v:ARRAY OF XYZWPR) BEGIN v[1].x=99 END work');assign(p)
        self.assertEqual(p.run()['A'][0]['X'],99.)

    def test_conversion_is_captured_before_later_argument_effects(self):
        p,_=build('work(a,change())',routines='ROUTINE change:INTEGER BEGIN a[1].x=99 RETURN 1 END change ROUTINE work(v:ARRAY OF POSITION;unused:INTEGER) BEGIN n=TRUNC(v[1].location.x) END work');assign(p)
        self.assertEqual((p.run()['A'][0]['X'],p.snapshot()['N']),(99,1))

    def test_bad_conversion_skips_later_arguments_and_callee_entry(self):
        p,_=build('n=0 work(a,change())',routines='ROUTINE change:INTEGER BEGIN n=1 RETURN 1 END change ROUTINE work(v:ARRAY OF POSITION;unused:INTEGER) BEGIN n=2 END work');assign(p);p._state.values['A'].values[-1].values['X']=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],0);self.assertEqual(p._state.local_frames,[])

    def test_return_changes_type_before_publishing_independent_result(self):
        p,_=build('b=make() a[1].x=99',routines='ROUTINE make:ARRAY OF POSITION BEGIN RETURN a END make');assign(p)
        self.assertEqual(p.run()['B'][0]['LOCATION']['X'],1.)

    def test_joint_arguments_and_results_are_private_converted_values(self):
        p,_=build('b=work(a)',first='JOINTPOS2',second='JOINTPOS9',routines='ROUTINE work(v:ARRAY OF JOINTPOS4):ARRAY OF JOINTPOS9 BEGIN RETURN v END work');assign(p,2)
        self.assertEqual(p.run()['B'][1]['axes'],[2.]+[0.]*8)

    def test_multidimensional_wildcard_return_inherits_concrete_shape(self):
        p,_=build('b=make()',shape='1,2',routines='ROUTINE make:ARRAY[*,*]OF POSITION BEGIN RETURN a END make');assign(p,shape=(1,2))
        self.assertEqual(p.run()['B'][0][1]['LOCATION']['X'],2.)

    def test_failed_return_cleans_counter_and_preserves_caller_target(self):
        p,_=build('b=make()',routines='ROUTINE make:ARRAY OF POSITION VAR i:INTEGER BEGIN FOR i=1 TO 2 DO RETURN a ENDFOR END make');assign(p);p._state.values['A'].values[-1].values['X']=rt.UNINITIALIZED;old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],old);self.assertEqual(p._state.local_frames,[]);self.assertEqual(p._state.call_depth,0)

    def test_pause_retains_private_converted_value_without_copyback(self):
        p,_=build('work(a) done=TRUE',routines='ROUTINE work(v:ARRAY OF POSITION) BEGIN v[1].location.x=99 PAUSE n=TRUNC(v[1].location.x) END work');assign(p)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['A'][0]['X'],1.);self.assertEqual(p.resume()['N'],99);self.assertEqual(p._state.local_frames,[])

    def test_linked_routines_accept_private_conversions(self):
        project=translate_project({'main':source('MAIN','b=work(a)',decl='a:ARRAY[2]OF XYZWPR b:ARRAY[2]OF XYZWPREXT',routines='ROUTINE work(v:ARRAY OF POSITION):ARRAY OF XYZWPREXT FROM LIB'),
            'lib':source('LIB','',routines='ROUTINE work(v:ARRAY OF POSITION):ARRAY OF XYZWPREXT BEGIN v[1].location.x=99 RETURN v END work')}).instantiate()
        project.programs['MAIN']._state.values['A']=data('XYZWPR');project.run('MAIN');v=project.programs['MAIN'].snapshot();self.assertEqual((v['A'][0]['X'],v['B'][0]['X']),(1.,99.))

    def test_callback_receives_declared_private_array(self):
        seen=[]
        def callback(ref):seen.append(ref.spec);ref.raw().values[0].values['LOCATION'].values['X']=99.
        ctx=rt.ExecutionContext(externals={('LIB','WORK'):callback});p,_=build('work(a)',routines='ROUTINE work(v:ARRAY OF POSITION) FROM LIB',context=ctx);assign(p)
        self.assertEqual(p.run()['A'][0]['X'],1.);self.assertEqual(seen,[('ARRAY',2,('POSITION',))])

    def test_callback_raw_array_result_remains_exact(self):
        ctx=rt.ExecutionContext(externals={('LIB','MAKE'):lambda:data('XYZWPR')});p,_=build('b=make()',routines='ROUTINE make:ARRAY OF POSITION FROM LIB',context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'exact element|matching'):p.run()

    def test_byname_keeps_exact_leaf_type_and_entry_output(self):
        p,_=build("e=77 work(BYNAME('','A',e))",routines='ROUTINE work(v:ARRAY OF POSITION) BEGIN END work');assign(p)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type does not match'):p.run()
        self.assertEqual(p.snapshot()['E'],77)

    def test_report_records_three_conversion_boundaries(self):
        p,result=build('b=make(a)',routines='ROUTINE make(v:ARRAY OF XYZWPREXT):ARRAY OF POSITION BEGIN RETURN v END make');assign(p);p.run()
        sites=json.loads(json.dumps(result.report))['positional_array_conversions'];self.assertEqual({r['operation']for r in sites},{'ARGUMENT','RETURN'})
        self.assertTrue(all(r['evaluated_once']and r['independent_value']for r in sites));self.assertTrue(result.report['array_value_arguments'][0]['converted'])


class PositionalArrayVariableTests(unittest.TestCase):
    def test_get_and_set_cartesian_prefixes_preserve_tail_and_identity(self):
        for first,second in PAIRS:
            for action in ('GET_VAR','SET_VAR'):
                p,_=compile_program(transfer(action,'A','b')if action=='GET_VAR'else transfer(action,'B','a'),decl=f'a:ARRAY[2]OF {first} b:ARRAY[3]OF {second} e,s:INTEGER')
                p._state.values['A']=data(first);p._state.values['B']=data(second,3);target=p._state.values['B'];child=target.values[0];tail=rt.snapshot_value(target.values[2])
                with self.subTest(first=first,second=second,action=action):
                    self.assertEqual(p.run()['S'],0);self.assertIs(p._state.values['B'],target);self.assertIs(target.values[0],child);self.assertEqual(rt.snapshot_value(target.values[2]),tail)
                    self.assertEqual(snapshot_x(rt.snapshot_value(target.values[1]),second),2.)

    def test_joint_variable_prefixes_pad_and_preserve_tail(self):
        for action in ('GET_VAR','SET_VAR'):
            p,_=compile_program(transfer(action,'A','b')if action=='GET_VAR'else transfer(action,'B','a'),decl='a:ARRAY[2]OF JOINTPOS2 b:ARRAY[3]OF JOINTPOS9 e,s:INTEGER')
            p._state.values['A']=data(2);p._state.values['B']=data(9,3);self.assertEqual(p.run()['B'][2]['axes'],[3.]+[0.]*8);self.assertEqual(p.snapshot()['S'],0)

    def test_invalid_last_prefix_element_preserves_data_entry_and_status(self):
        p,_=build('e=99 s=77 '+transfer());assign(p);p._state.values['A'].values[-1].values['X']=rt.UNINITIALIZED;old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),(old,99,77));self.assertEqual(p._state.execution.entries,{})

    def test_nonzero_joint_narrowing_is_atomic_for_whole_prefix(self):
        p,_=build('e=99 s=77 '+transfer(),first='JOINTPOS4',second='JOINTPOS2');assign(p,4);p._state.values['A'].values[-1].values[3]=7.;old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),(old,99,77));self.assertEqual(p._state.execution.entries,{})

    def test_missing_uncopied_source_tail_does_not_invalidate_selected_prefix(self):
        p,_=compile_program(transfer(),decl='a:ARRAY[3]OF XYZWPR b:ARRAY[2]OF POSITION e,s:INTEGER');p._state.values['A']=data('XYZWPR',3);p._state.values['A'].values[-1]=rt.UNINITIALIZED
        self.assertEqual(p.run()['S'],0);self.assertEqual(p.snapshot()['B'][1]['LOCATION']['X'],2.)

    def test_named_component_arrays_keep_receiver_schema_and_row_major_prefix(self):
        prefix='TYPE row_a=ARRAY[2]OF XYZWPR row_b=ARRAY[3]OF POSITION'
        p,_=compile_program(transfer(),prefix=prefix,decl='a:ARRAY[2]OF row_a b:ARRAY[2]OF row_b e,s:INTEGER')
        for row in p._state.values['A'].values:row.values[:]=data('XYZWPR').values
        target=p._state.values['B'];identity=target.values[0].spec
        self.assertEqual(p.run()['S'],0);self.assertEqual(target.values[0].spec,identity);self.assertEqual(p.snapshot()['B'][1][0]['LOCATION']['X'],2.)

    def test_rank_mismatch_retains_status_three(self):
        p,_=compile_program('e=99 '+transfer(),decl='a:ARRAY[2]OF XYZWPR b:ARRAY[1,2]OF POSITION e,s:INTEGER');assign(p)
        self.assertEqual((p.run()['S'],p.snapshot()['E']),(3,99))

    def test_wholly_missing_conversion_rejects_instead_of_clearing_receiver(self):
        p,_=build('e=99 s=77 '+transfer());p._state.values['A']=rt.UNINITIALIZED;old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),(old,99,77));self.assertEqual(p._state.execution.entries,{})

    def test_exact_partial_transfer_keeps_status_12311(self):
        p,_=build(transfer(),first='XYZWPR',second='XYZWPR');self.assertEqual(p.run()['S'],12311)

    def test_set_captures_all_values_before_status_selector_effects(self):
        p,_=compile_program("SET_VAR(e,'','B',a,codes[change()])",decl='a:ARRAY[2]OF XYZWPR b:ARRAY[2]OF POSITION codes:ARRAY[1]OF INTEGER e:INTEGER',routines='ROUTINE change:INTEGER BEGIN a[1].x=99 RETURN 1 END change');assign(p)
        self.assertEqual((p.run()['B'][0]['LOCATION']['X'],p.snapshot()['A'][0]['X']),(1.,99))

    def test_get_resolves_source_after_output_selectors(self):
        p,_=compile_program("GET_VAR(e,'','A',b,codes[change()])",decl='a:ARRAY[2]OF XYZWPR b:ARRAY[2]OF POSITION codes:ARRAY[1]OF INTEGER e:INTEGER',routines='ROUTINE change:INTEGER BEGIN a[1].x=99 RETURN 1 END change');assign(p)
        self.assertEqual(p.run()['B'][0]['LOCATION']['X'],99.)

    def test_concrete_converted_arrays_round_trip_context_without_robot(self):
        ctx=rt.ExecutionContext();p,_=build(transfer(),context=ctx);assign(p);p.run();config=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(config)
        self.assertEqual(restored.to_config(),config);self.assertIsNone(restored.robot)


class PositionalArrayBoundaryTests(unittest.TestCase):
    def test_preserved_legacy_source_and_runtime_guards(self):
        for body,routines in [('b=a',''),('work(a)','ROUTINE work(v:ARRAY OF POSITION) BEGIN END work'),('','ROUTINE make:ARRAY OF POSITION BEGIN RETURN a END make')]:
            with self.subTest(body=body),self.assertRaises(TranslationError):legacy_translate('PROGRAM T VAR a:ARRAY[2]OF XYZWPR b:ARRAY[2]OF POSITION '+routines+' BEGIN '+body+' END T')
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.convert_positional_array(('ARRAY',2,('POSITION',)),data('XYZWPR'))

    def test_raw_checked_value_argument_and_array_result_stay_exact(self):
        target=('ARRAY',None,('POSITION',));value=data('XYZWPR')
        with rt._numeric_scope('pythonic'):
            for operation in (lambda:rt.checked(('ARRAY',2,('POSITION',)),value),lambda:rt.value_argument(target,value),lambda:rt.array_result(target,value)):
                with self.subTest(operation=operation),self.assertRaises(rt.KarelRuntimeError):operation()

    def test_malformed_storage_and_schemas_fail_with_source_line(self):
        with rt._numeric_scope('pythonic'):
            for target in (None,(),('ARRAY',True,('POSITION',)),('ARRAY',0,('POSITION',)),('ARRAY',2,('REAL',)),('ARRAY',2,('JOINTPOS',0))):
                with self.subTest(target=target),self.assertRaises(rt.KarelRuntimeError)as err:rt.convert_positional_array(target,data('XYZWPR'),17)
                self.assertEqual(err.exception.line,17)
            value=data('XYZWPR');value.values.pop()
            with self.assertRaises(rt.KarelRuntimeError):rt.convert_positional_array(('ARRAY',2,('POSITION',)),value,17)

    def test_output_allocation_limit_is_checked_before_conversion(self):
        value=data(1,4000)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):rt.convert_positional_array(('ARRAY',4000,('JOINTPOS',9)),value,17)


if __name__=='__main__':unittest.main()
