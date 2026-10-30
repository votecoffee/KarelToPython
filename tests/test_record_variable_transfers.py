"""Authored context-free record GET_VAR/SET_VAR conversions and prefix contracts."""
import copy
import json
import unittest
from karel2py import runtime as rt,translate_project
from karel2py import extended as ex
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_joint_interoperability import joint
from tests.test_cartesian_interfaces import value as pose
from tests.test_kinematic_assignments import callback_context

U={'uninitialized':True}
UNKNOWN={'unknown_byte':True}


def types(first='INTEGER',second='REAL'):
    return f'TYPE in_t=STRUCTURE count:{first} label:STRING[8] ENDSTRUCTURE out_t=STRUCTURE label:STRING[3] count:{second} ENDSTRUCTURE'


def call(action='GET_VAR',*,entry='e',status='s'):
    path,value=('A','b') if action=='GET_VAR' else ('B','a')
    return f"{action}({entry},'','{path}',{value},{status})"


def build(body=None,action='GET_VAR',first='INTEGER',second='REAL',routines='',decl='',**options):
    return compile_program(body or call(action),prefix=types(first,second),decl='a:in_t b:out_t e,s,old,n,visits:INTEGER done:BOOLEAN '+decl,routines=routines,**options)


def seed(p,count=7,label='abcdefgh'):
    p._state.values['A'].values.update(COUNT=count,LABEL=label);p._state.values['B'].values.update(COUNT=9,LABEL='old');return p


def arrays(body=None,action='GET_VAR',source=2,target=3,first='INTEGER',second='REAL',**options):
    prefix=types(first,second)+f' in_array=ARRAY[1,{source}]OF in_t out_row=ARRAY[{target}]OF out_t out_array=ARRAY[1]OF out_row'
    p,r=compile_program(body or call(action),prefix=prefix,decl='a:in_array b:out_array e,s,old,n:INTEGER done:BOOLEAN',**options)
    for i,item in enumerate(p._state.values['A'].values):item.values.update(COUNT=i+1,LABEL='abcdefgh')
    for item in p._state.values['B'].values[0].values:item.values.update(COUNT=99 if second!='REAL' else 99.,LABEL='old')
    return p,r


def geometry(first='XYZWPR',second='POSITION',action='GET_VAR',body=None,**options):
    prefix=f'TYPE in_t=STRUCTURE point:{first} count:INTEGER ENDSTRUCTURE out_t=STRUCTURE count:REAL point:{second} ENDSTRUCTURE'
    p,r=compile_program(body or call(action),prefix=prefix,decl='a:in_t b:out_t e,s,n:INTEGER done:BOOLEAN',**options)
    p._state.values['A'].values['COUNT']=7;return p,r


class RecordTransferValueTests(unittest.TestCase):
    def test_get_and_set_map_receiver_fields_and_convert_domains(self):
        for action in ('GET_VAR','SET_VAR'):
            p,_=build(action=action);seed(p);v=p.run();self.assertEqual((v['B'],v['E'],v['S']),({'LABEL':'abc','COUNT':7.},1,0));self.assertEqual(v['A'],{'COUNT':7,'LABEL':'abcdefgh'})

    def test_every_integral_pair_and_real_promotion_in_both_directions(self):
        for first in ('INTEGER','BYTE','SHORT'):
            for second in ('INTEGER','BYTE','SHORT','REAL'):
                for action in ('GET_VAR','SET_VAR'):
                    p,_=build(first=first,second=second,action=action);seed(p);v=p.run()['B']['COUNT'];self.assertEqual(v,7);self.assertIs(type(v),float if second=='REAL' else int)

    def test_receiver_nominal_identity_and_field_order_retained(self):
        p,_=build();seed(p);p.run();self.assertEqual((p._state.values['B'].spec[1],list(p._state.values['B'].values)),('OUT_T',['LABEL','COUNT']))

    def test_strings_validate_source_then_truncate_or_widen(self):
        p,_=build();seed(p);p.run();self.assertEqual((p.snapshot()['A']['LABEL'],p.snapshot()['B']['LABEL']),('abcdefgh','abc'))
        prefix='TYPE in_t=STRUCTURE label:STRING[3] ENDSTRUCTURE out_t=STRUCTURE label:STRING[8] ENDSTRUCTURE'
        p,_=compile_program("a.label='abc' "+call(),prefix=prefix,decl='a:in_t b:out_t e,s:INTEGER');self.assertEqual(p.run()['B']['LABEL'],'abc')

    def test_nested_records_and_numeric_array_layouts(self):
        prefix='TYPE in_child=STRUCTURE n:INTEGER label:STRING[8] ENDSTRUCTURE out_child=STRUCTURE label:STRING[2] n:REAL ENDSTRUCTURE row_t=ARRAY[2]OF REAL in_t=STRUCTURE child:in_child data:ARRAY[1,2]OF INTEGER ENDSTRUCTURE out_t=STRUCTURE data:ARRAY[1]OF row_t child:out_child ENDSTRUCTURE'
        p,_=compile_program("a.child.n=7 a.child.label='abcdefgh' a.data[1,1]=1 a.data[1,2]=2 "+call(),prefix=prefix,decl='a:in_t b:out_t e,s:INTEGER')
        self.assertEqual(p.run()['B'],{'DATA':[[1.,2.]],'CHILD':{'LABEL':'ab','N':7.}})

    def test_late_narrowing_error_keeps_receiver_entry_status_and_cache(self):
        for action in ('GET_VAR','SET_VAR'):
            p,_=build('e=99 s=77 '+call(action),first='INTEGER',second='BYTE');seed(p,256);before=p.snapshot()['B']
            with self.subTest(action=action),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S'],p._state.execution.entries),(before,99,77,{}))

    def test_source_domain_is_checked_before_promotion(self):
        for first,value in [('BYTE',256),('SHORT',-32769),('INTEGER',2147483647),('INTEGER',True),('INTEGER',1.)]:
            p,_=build('e=99 s=77 '+call(),first=first);seed(p,value)
            with self.subTest(first=first,value=value),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['E'],p.snapshot()['S']),(99,77))

    def test_original_string_capacity_cannot_be_hidden(self):
        p,_=build('e=99 s=77 '+call());seed(p,label='longer than eight');before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),(before,99,77))

    def test_non_ascii_source_is_rejected(self):
        p,_=build('e=99 s=77 '+call());seed(p,label='caf'+chr(233));before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),(before,99,77))

    def test_non_finite_real_field_is_rejected(self):
        for bad in (float('nan'),float('inf')):
            p,_=build(first='REAL');seed(p,bad)
            with self.subTest(bad=bad),self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_receiver_and_known_child_aliases_stay_attached(self):
        p,_=geometry();p._state.values['A'].values['POINT']=pose('XYZWPR',(1.,2.,3.));b=p._state.values['B'];point=b.values['POINT'];location=point.values['LOCATION'];p.run()
        self.assertIs(p._state.values['B'],b);self.assertIs(b.values['POINT'],point);self.assertIs(point.values['LOCATION'],location);self.assertEqual(location.values['X'],1.)


class RecordTransferMissingTests(unittest.TestCase):
    def test_partial_scalar_fields_transfer_with_missing_status(self):
        for action in ('GET_VAR','SET_VAR'):
            p,_=build(action=action);seed(p,rt.UNINITIALIZED);v=p.run();self.assertEqual((v['B']['COUNT'],v['S']),(U,12311))

    def test_whole_missing_source_record_clears_compatible_receiver(self):
        p,_=build();seed(p);p._state.values['A']=rt.UNINITIALIZED;v=p.run();self.assertEqual((v['B'],v['E'],v['S']),(U,1,12311))

    def test_missing_receiver_record_materializes_declared_schema(self):
        p,_=build();seed(p);p._state.values['B']=rt.UNINITIALIZED;self.assertEqual(p.run()['B'],{'LABEL':'abc','COUNT':7.});self.assertEqual(p._state.values['B'].spec[1],'OUT_T')

    def test_missing_nested_record_container_stays_missing(self):
        prefix='TYPE one=STRUCTURE n:INTEGER ENDSTRUCTURE two=STRUCTURE n:REAL ENDSTRUCTURE in_t=STRUCTURE child:one label:STRING[8] ENDSTRUCTURE out_t=STRUCTURE label:STRING[3] child:two ENDSTRUCTURE'
        p,_=compile_program(call(),prefix=prefix,decl='a:in_t b:out_t e,s:INTEGER');p._state.values['A'].values.update(CHILD=rt.UNINITIALIZED,LABEL='abcdefgh')
        self.assertEqual((p.run()['B'],p.snapshot()['S']),({'LABEL':'abc','CHILD':U},12311))

    def test_missing_array_field_container_stays_missing(self):
        prefix='TYPE in_t=STRUCTURE data:ARRAY[2]OF INTEGER ENDSTRUCTURE out_t=STRUCTURE data:ARRAY[2]OF REAL ENDSTRUCTURE'
        p,_=compile_program(call(),prefix=prefix,decl='a:in_t b:out_t e,s:INTEGER');p._state.values['A'].values['DATA']=rt.UNINITIALIZED
        self.assertEqual((p.run()['B']['DATA'],p.snapshot()['S']),(U,12311))

    def test_changed_array_layout_expands_missing_component_to_leaves(self):
        prefix='TYPE row_t=ARRAY[2]OF INTEGER in_t=STRUCTURE data:ARRAY[2]OF row_t ENDSTRUCTURE out_t=STRUCTURE data:ARRAY[2,2]OF REAL ENDSTRUCTURE'
        p,_=compile_program('a.data[1,1]=7 a.data[1,2]=8 '+call(),prefix=prefix,decl='a:in_t b:out_t e,s:INTEGER');p._state.values['A'].values['DATA'].values[-1]=rt.UNINITIALIZED
        self.assertEqual((p.run()['B']['DATA'],p.snapshot()['S']),([[7.,8.],[U,U]],12311))

    def test_unknown_byte_same_type_is_distinct_from_missing(self):
        p,_=build(first='BYTE',second='BYTE');seed(p,rt.UNKNOWN_BYTE);self.assertEqual((p.run()['B']['COUNT'],p.snapshot()['S']),(UNKNOWN,0))

    def test_unknown_byte_promotion_is_atomic_error(self):
        p,_=build('e=99 s=77 '+call(),first='BYTE');seed(p,rt.UNKNOWN_BYTE);before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),(before,99,77))

    def test_source_short_sentinel_is_normalized_privately(self):
        p,_=build(first='SHORT');seed(p,32767);self.assertEqual((p.run()['B']['COUNT'],p.snapshot()['S']),(U,12311));self.assertEqual(p._state.values['A'].values['COUNT'],32767)

    def test_target_short_sentinel_produces_missing_status(self):
        p,_=build(second='SHORT');seed(p,32767);self.assertEqual((p.run()['B']['COUNT'],p.snapshot()['S']),(U,12311))

    def test_missing_type_incompatible_record_does_not_clear_receiver(self):
        p,_=build('e=99 '+call(),first='REAL',second='INTEGER');seed(p);p._state.values['A']=rt.UNINITIALIZED;before=p.snapshot()['B'];v=p.run();self.assertEqual((v['B'],v['E'],v['S']),(before,99,3))


class RecordPrefixTransferTests(unittest.TestCase):
    def test_get_and_set_convert_prefix_keep_tail_and_names(self):
        for action in ('GET_VAR','SET_VAR'):
            p,_=arrays(action=action);v=p.run();self.assertEqual([r['COUNT'] for r in v['B'][0]],[1.,2.,99.]);self.assertEqual(v['S'],0);self.assertEqual((p._state.values['B'].spec[3],p._state.values['B'].spec[2][3]),('OUT_ARRAY','OUT_ROW'))

    def test_larger_source_ignores_missing_numeric_tail(self):
        p,_=arrays(source=3,target=2);p._state.values['A'].values[-1].values['COUNT']=rt.UNINITIALIZED;self.assertEqual((p.run()['B'][0][-1]['COUNT'],p.snapshot()['S']),(2.,0))

    def test_larger_source_ignores_bad_known_numeric_tail(self):
        p,_=arrays(source=3,target=2);p._state.values['A'].values[-1].values['COUNT']=True;self.assertEqual(p.run()['S'],0)

    def test_unknown_byte_outside_prefix_is_not_promoted(self):
        p,_=arrays(source=3,target=2,first='BYTE');p._state.values['A'].values[-1].values['COUNT']=rt.UNKNOWN_BYTE;self.assertEqual(p.run()['S'],0)

    def test_structural_corruption_outside_prefix_is_still_rejected(self):
        p,_=arrays(source=3,target=2);p._state.values['A'].values[-1].types['COUNT']=('BOOLEAN',)
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_late_record_failure_preserves_entire_prefix_and_cache(self):
        p,_=arrays('e=99 s=77 '+call(),second='BYTE');p._state.values['A'].values[-1].values['COUNT']=256;before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S'],p._state.execution.entries),(before,99,77,{}))

    def test_missing_record_prefix_does_not_count_missing_receiver_tail(self):
        p,_=arrays(source=1,target=2);p._state.values['B'].values[0].values[-1]=rt.UNINITIALIZED;self.assertEqual((p.run()['S'],p.snapshot()['B'][0][-1]),(0,U))

    def test_whole_missing_record_element_clears_only_its_cell(self):
        p,_=arrays();p._state.values['A'].values[-1]=rt.UNINITIALIZED;v=p.run();self.assertEqual((v['B'][0][1],v['B'][0][2]['COUNT'],v['S']),(U,99.,12311))

    def test_missing_whole_source_array_clears_compatible_receiver(self):
        p,_=arrays();p._state.values['A']=rt.UNINITIALIZED;self.assertEqual((p.run()['B'],p.snapshot()['S']),(U,12311))

    def test_missing_receiver_array_materializes_tail_as_missing(self):
        p,_=arrays();p._state.values['B']=rt.UNINITIALIZED;v=p.run();self.assertEqual((v['B'][0][0]['COUNT'],v['B'][0][-1]['COUNT'],v['S']),(1.,U,0))

    def test_three_dimensional_record_prefix(self):
        p,_=compile_program('a[1,1,1].count=7 '+call(),prefix=types(),decl='a:ARRAY[1,1,1]OF in_t b:ARRAY[1,1,2]OF out_t e,s:INTEGER')
        v=p.run();self.assertEqual((v['B'][0][0][0]['COUNT'],v['S']),(7.,12311))

    def test_rank_mismatch_is_status_only(self):
        p,_=compile_program('e=99 '+call(),prefix=types(),decl='a:ARRAY[2]OF in_t b:ARRAY[1,2]OF out_t e,s:INTEGER');self.assertEqual((p.run()['E'],p.snapshot()['S']),(99,3))

    def test_array_field_dimension_mismatch_is_status_only(self):
        prefix='TYPE in_t=STRUCTURE data:ARRAY[2]OF INTEGER ENDSTRUCTURE out_t=STRUCTURE data:ARRAY[3]OF REAL ENDSTRUCTURE'
        p,_=compile_program('e=99 '+call(),prefix=prefix,decl='a:in_t b:out_t e,s:INTEGER');self.assertEqual((p.run()['E'],p.snapshot()['S']),(99,3))


class RecordGeometryTransferTests(unittest.TestCase):
    def test_each_cartesian_pair_in_both_directions(self):
        for first in ('POSITION','XYZWPR','XYZWPREXT'):
            for second in ('POSITION','XYZWPR','XYZWPREXT'):
                for action in ('GET_VAR','SET_VAR'):
                    p,_=geometry(first,second,action);p._state.values['A'].values['POINT']=pose(first,(7.,8.,9.));v=p.run()['B']['POINT'];self.assertEqual((v['LOCATION']['X'] if second=='POSITION' else v['X']),7.)

    def test_joint_width_fields_in_both_directions(self):
        for first,second in ((2,9),(9,2),(1,4)):
            for action in ('GET_VAR','SET_VAR'):
                p,_=geometry(f'JOINTPOS{first}',f'JOINTPOS{second}',action);p._state.values['A'].values['POINT']=joint([7.]+[0.]*(first-1));self.assertEqual(p.run()['B']['POINT']['axes'],[7.]+[0.]*(second-1))

    def test_nonzero_discarded_axis_preserves_all_outputs(self):
        p,_=geometry('JOINTPOS3','JOINTPOS2',body='e=99 s=77 '+call());p._state.values['A'].values['POINT']=joint([1.,2.,3.]);before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),(before,99,77))

    def test_partial_changed_geometry_does_not_publish(self):
        p,_=geometry(body='e=99 s=77 '+call());before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),(before,99,77))

    def test_whole_missing_geometry_field_cannot_invent_representation(self):
        p,_=geometry(body='e=99 s=77 '+call());p._state.values['A'].values['POINT']=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['E'],p.snapshot()['S']),(99,77))

    def test_exact_partial_geometry_keeps_missing_status(self):
        p,_=geometry('POSITION','POSITION');self.assertEqual((p.run()['B']['POINT']['LOCATION']['X'],p.snapshot()['S']),(U,12311))

    def test_improper_source_position_is_rejected(self):
        p,_=geometry('POSITION','XYZWPR');p._state.values['A'].values['POINT']=pose('POSITION');p._state.values['A'].values['POINT'].values['NORMAL'].values['X']=2.
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_model_backed_fields_without_robot_service_remain_status_only(self):
        calls=[];p,_=geometry('JOINTPOS2','POSITION',body='e=99 '+call(),context=rt.ExecutionContext());p._state.values['A'].values['POINT']=joint([0.,0.]);before=p.snapshot()['B']
        v=p.run();self.assertEqual((v['B'],v['E'],v['S'],calls),(before,99,3,[]))


class RecordTransferOrderingTests(unittest.TestCase):
    def test_set_captures_record_before_later_status_selector(self):
        p,_=build("SET_VAR(e,'','B',a,statuses[pick()])",routines='ROUTINE pick:INTEGER BEGIN a.count=99 RETURN 1 END pick',decl='statuses:ARRAY[1]OF INTEGER');seed(p)
        v=p.run();self.assertEqual((v['A']['COUNT'],v['B']['COUNT'],v['STATUSES']),(99,7.,[0]))

    def test_get_captures_named_record_after_status_selector(self):
        p,_=build("GET_VAR(e,'','A',b,statuses[pick()])",routines='ROUTINE pick:INTEGER BEGIN a.count=99 RETURN 1 END pick',decl='statuses:ARRAY[1]OF INTEGER');seed(p)
        self.assertEqual((p.run()['B']['COUNT'],p.snapshot()['STATUSES']),(99.,[0]))

    def test_function_set_source_is_evaluated_once(self):
        p,_=build("visits=0 SET_VAR(e,'','B',make(),s)",routines='ROUTINE make:in_t BEGIN visits=visits+1 RETURN a END make');seed(p)
        self.assertEqual((p.run()['VISITS'],p.snapshot()['B']['COUNT']),(1,7.))

    def test_grouped_set_reference_keeps_capture_semantics(self):
        p,_=build("SET_VAR(e,'','B',(a),s)");seed(p);self.assertEqual(p.run()['B']['COUNT'],7.)

    def test_selector_effects_survive_late_value_validation_failure(self):
        p,_=build("e=99 statuses[1]=77 n=0 SET_VAR(e,'','B',a,statuses[pick()])",first='BYTE',routines='ROUTINE pick:INTEGER BEGIN n=1 RETURN 1 END pick',decl='statuses:ARRAY[1]OF INTEGER');seed(p,256);before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['E'],p.snapshot()['STATUSES'],p.snapshot()['B']),(1,99,[77],before))

    def test_cache_ids_reused_by_normalized_lookup(self):
        p,_=build("GET_VAR(e,'','a',b,s) old=e GET_VAR(e,'','A',b,s)");seed(p);v=p.run();self.assertEqual((v['E'],v['OLD'],len(p._state.execution.entries)),(1,1,1))

    def test_new_get_and_set_targets_get_distinct_cache_ids(self):
        p,_=build(call()+' old=e '+call('SET_VAR'));seed(p);v=p.run();self.assertEqual((v['OLD'],v['E'],len(p._state.execution.entries)),(1,2,2))

    def test_lookup_failure_keeps_data_entry_and_cache(self):
        p,_=build("e=99 GET_VAR(e,'','MISSING',b,s)");seed(p);before=p.snapshot()['B'];v=p.run();self.assertEqual((v['B'],v['E'],v['S'],p._state.execution.entries),(before,99,1,{}))

    def test_known_receiver_aliases_observe_changed_fields(self):
        p,_=build(call(),routines='');seed(p);b=p._state.values['B'];ref=rt.field_reference(b,'COUNT');p.run();self.assertEqual(ref.raw(),7.);ref.set(8.);self.assertEqual(p.snapshot()['B']['COUNT'],8.)

    def test_get_destination_may_not_overlap_status(self):
        p,_=build("GET_VAR(e,'','A',b,b.count)",second='INTEGER');seed(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        with self.assertRaises(TranslationError):build('FOR b.count=1 TO 2 DO '+call()+' ENDFOR',second='INTEGER')

    def test_set_named_target_may_not_overlap_entry(self):
        p,_=build("SET_VAR(b.count,'','B',a,s)",second='INTEGER');seed(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_handler_can_transfer_compatible_record(self):
        body='CONDITION[1]: WHEN EVENT[1] DO '+call()+' ENDCONDITION ENABLE CONDITION[1] SIGNAL EVENT[1]'
        p,_=build(body);seed(p);self.assertEqual(p.run()['B']['COUNT'],7.)


class RecordTransferBindingTests(unittest.TestCase):
    def test_explicit_system_binding_uses_receiver_schema(self):
        p,_=build("GET_VAR(e,'SYSTEM','$DATA',b,s)");seed(p);ref=p._state.execution.variables.define('SYSTEM','$DATA',p._state.types['A'],copy.deepcopy(p._state.values['A']));p.run();self.assertEqual(p.snapshot()['B']['COUNT'],7.);self.assertEqual(ref.raw().values['COUNT'],7)

    def test_foreign_binding_is_updated_by_set_without_source_aliasing(self):
        p,_=build("SET_VAR(e,'OTHER','DATA',a,s)");seed(p);ref=p._state.execution.variables.define('OTHER','DATA',p._state.types['B'],copy.deepcopy(p._state.values['B']));p.run();self.assertEqual(ref.raw().values['COUNT'],7.);ref.raw().values['COUNT']=99.;self.assertEqual(p.snapshot()['A']['COUNT'],7)

    def test_static_nested_field_lookup(self):
        prefix=types()+' box_t=STRUCTURE item:in_t ENDSTRUCTURE'
        p,_=compile_program("box.item.count=7 box.item.label='abcdefgh' GET_VAR(e,'','BOX.ITEM',b,s)",prefix=prefix,decl='box:box_t b:out_t e,s:INTEGER');self.assertEqual(p.run()['B'],{'LABEL':'abc','COUNT':7.})

    def test_static_record_element_lookup(self):
        p,_=compile_program("items[1].count=7 items[1].label='abcdefgh' GET_VAR(e,'','ITEMS[1]',b,s)",prefix=types(),decl='items:ARRAY[1]OF in_t b:out_t e,s:INTEGER');self.assertEqual(p.run()['B']['COUNT'],7.)

    def test_routine_get_uses_module_globals_instead_of_shadowing_local(self):
        p,_=build('work()',routines='ROUTINE work VAR a:in_t BEGIN a.count=99 '+call()+' END work');seed(p);self.assertEqual(p.run()['B']['COUNT'],7.)

    def test_generic_formals_keep_actual_record_array_shapes(self):
        p,_=arrays('work(b,a)',routines="ROUTINE work(dst:ARRAY[*,*]OF out_t;src:ARRAY[*,*]OF in_t) BEGIN SET_VAR(e,'','B',src,s) END work");self.assertEqual([r['COUNT'] for r in p.run()['B'][0]],[1.,2.,99.])

    def test_linked_get_converts_owner_record_into_caller_schema(self):
        prefix=types();main='PROGRAM MAIN '+prefix+" VAR b:out_t e,s:INTEGER BEGIN GET_VAR(e,'LIB','A',b,s) END MAIN";lib='PROGRAM LIB '+prefix+' VAR a:in_t BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate();project.programs['LIB']._state.values['A'].values.update(COUNT=7,LABEL='abcdefgh');project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['B']['COUNT'],7.)

    def test_linked_set_converts_caller_record_into_owner_schema(self):
        prefix=types();main='PROGRAM MAIN '+prefix+" VAR a:in_t e,s:INTEGER BEGIN SET_VAR(e,'LIB','B',a,s) END MAIN";lib='PROGRAM LIB '+prefix+' VAR b:out_t BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate();seeded=project.programs['MAIN']._state.values['A'];seeded.values.update(COUNT=7,LABEL='abcdefgh');project.run('MAIN');self.assertEqual(project.programs['LIB'].snapshot()['B']['COUNT'],7.)

    def test_json_replay_retains_record_schemas_and_rebuilds_cache(self):
        p,_=build();seed(p);state=p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));q,_=build(context=rt.ExecutionContext.from_config(saved));self.assertEqual(q.run(),state);self.assertEqual(q._state.values['B'].spec,p._state.values['B'].spec);self.assertEqual(len(q._state.execution.entries),1)

    def test_path_node_record_can_be_converted_as_selected_data(self):
        prefix=types();p,_=compile_program("APPEND_NODE(route,s) route[1].count=7 route[1].label='abcdefgh' GET_VAR(e,'','ROUTE[1]',b,s)",prefix=prefix,decl='route:PATH NODEDATA=in_t b:out_t e,s:INTEGER');self.assertEqual(p.run()['B']['COUNT'],7.)
        p,_=compile_program("APPEND_NODE(route,s) a.count=7 a.label='abcdefgh' SET_VAR(e,'','ROUTE[1]',a,s)",prefix=prefix,decl='a:in_t route:PATH NODEDATA=out_t e,s:INTEGER');p.run();self.assertEqual(p._state.values['ROUTE'].nodes[0].values,{'LABEL':'abc','COUNT':7.})


class RecordTransferBoundaryTests(unittest.TestCase):
    def test_field_name_set_mismatch_is_status_only(self):
        for target in ('count:REAL','count:REAL label:STRING[3] extra:INTEGER','other:REAL label:STRING[3]'):
            prefix='TYPE in_t=STRUCTURE count:INTEGER label:STRING[8] ENDSTRUCTURE out_t=STRUCTURE '+target+' ENDSTRUCTURE'
            p,_=compile_program('e=99 '+call(),prefix=prefix,decl='a:in_t b:out_t e,s:INTEGER');self.assertEqual((p.run()['E'],p.snapshot()['S']),(99,3))

    def test_boolean_and_real_to_integral_fields_are_status_only(self):
        for first,second in (('BOOLEAN','INTEGER'),('INTEGER','BOOLEAN'),('REAL','INTEGER')):
            p,_=build('e=99 '+call(),first=first,second=second);v=p.run();self.assertEqual((v['E'],v['S']),(99,3))

    def test_generic_transfer_helper_requires_explicit_record_opt_in(self):
        p,_=build();seed(p);target=p._state.reference('B');source=ex.variable_reference(p._state.reference('A'))
        with rt._numeric_scope('pythonic'):
            self.assertIsNone(ex.variable_transfer(target,source,numeric=True,representations=True));prepared=ex.variable_transfer(target,source,numeric=True,representations=True,records=True);self.assertEqual(prepared[0].values['COUNT'],7.)
        self.assertEqual(p.snapshot()['B']['COUNT'],9)

    def test_generic_checked_helpers_remain_nominal(self):
        p,_=build();seed(p)
        with rt._numeric_scope('pythonic'):
            for fn in (rt.checked,rt.value_argument,rt.structure_value):
                with self.assertRaises(rt.KarelRuntimeError):fn(p._state.types['B'],p._state.values['A'])

    def test_strict_helper_does_not_gain_record_coercion(self):
        p,_=build();seed(p);target=p._state.reference('B');source=ex.variable_reference(p._state.reference('A'))
        with rt._numeric_scope('strict'):self.assertIsNone(ex.variable_transfer(target,source,records=True))

    def test_malformed_record_schema_storage_is_rejected(self):
        for change in ('fields','types','spec'):
            p,_=build('e=99 s=77 '+call());seed(p);a=p._state.values['A'];before=p.snapshot()['B']
            if change=='fields':a.values.pop('COUNT')
            elif change=='types':a.types['COUNT']=('REAL',)
            else:a.spec=('STRUCTURE','FOREIGN',a.spec[2])
            with self.subTest(change=change),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),(before,99,77))

    def test_report_describes_dynamic_record_and_prefix_boundaries(self):
        _,result=build();policy=result.report['record_variable_transfer_policy'];self.assertFalse(policy['controller_validated']);self.assertEqual(policy['guide'],'docs/record-variable-transfers.md')
        for text in ('GET_VAR','SET_VAR'):self.assertIn(text,policy['procedures'])
        self.assertIn('model-backed',policy['boundary']);self.assertIn('cache',policy['status']);self.assertIn('smaller',policy['arrays']);json.dumps(result.report)


if __name__=='__main__':unittest.main()
