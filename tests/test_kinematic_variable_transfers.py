"""Authored explicit-model variable transfers: preflight, prefixes, aliases and lifecycle."""
import copy
import json
import unittest
from karel2py import runtime as rt,extended as ex,translate_project
from karel2py.kinematics import pose as identity_pose
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_joint_interoperability import joint,model_context
from tests.test_kinematic_assignments import callback_context
from tests.test_kinematic_arrays import forward_adapter
from tests.test_cartesian_interfaces import value as cartesian
from tests.test_record_variable_transfers import call

U={'uninitialized':True}
POSES=('POSITION','XYZWPR','XYZWPREXT')


def build(first='JOINTPOS2',second='POSITION',action='GET_VAR',body=None,ctx=None,**options):
    p,r=compile_program(body or call(action),decl=f'a:{first} b:{second} e,s,n:INTEGER done:BOOLEAN',context=ctx if ctx is not None else model_context((0.,90.)),**options)
    p._state.values.update(E=99,S=77,N=0)
    if first.startswith('JOINTPOS'):
        width=9 if first=='JOINTPOS' else int(first[8:]);p._state.values['A']=joint([0.,90.]+[0.]*(width-2))
    elif first in POSES:p._state.values['A']=cartesian(first)
    return p,r


def arrays(first='JOINTPOS2',second='POSITION',source='2',target='3',action='GET_VAR',ctx=None,body=None,routines=''):
    p,r=compile_program(body or call(action),decl=f'a:ARRAY[{source}]OF {first} b:ARRAY[{target}]OF {second} e,s,n:INTEGER done:BOOLEAN',routines=routines,context=ctx if ctx is not None else model_context((0.,90.)))
    p._state.values.update(E=99,S=77,N=0)
    leaf=rt.array_leaf_spec(p._state.types['A'])
    for storage,key in rt._array_conversion_cells(p._state.values['A']):storage[key]=joint([0.,90.]+[0.]*(leaf[1]-2)) if leaf[0]=='JOINTPOS' else cartesian(first)
    return p,r


def records(action='GET_VAR',ctx=None,first='JOINTPOS2',second='POSITION',body=None):
    prefix=f'TYPE one=STRUCTURE point:{first} count:INTEGER label:STRING[8] ENDSTRUCTURE two=STRUCTURE label:STRING[3] count:REAL point:{second} ENDSTRUCTURE'
    p,r=compile_program(body or call(action),prefix=prefix,decl='a:one b:two e,s,n:INTEGER done:BOOLEAN',context=ctx if ctx is not None else model_context((0.,90.)))
    p._state.values.update(E=99,S=77,N=0);p._state.values['A'].values.update(POINT=joint([0.,90.]) if first=='JOINTPOS2' else cartesian(first),COUNT=7,LABEL='abcdefgh')
    return p,r


def failed(test,p,pattern=None,exception=rt.KarelRuntimeError):
    before=(copy.deepcopy(p.snapshot()['B']),p.snapshot()['E'],p.snapshot()['S'],copy.deepcopy(p._state.execution.entries))
    with test.assertRaises(exception) as caught:p.run()
    if pattern:test.assertIn(pattern,str(caught.exception))
    test.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S'],p._state.execution.entries),before)
    return caught.exception


def x(value):return value['LOCATION']['X'] if 'LOCATION' in value else value['X']


class ModelVariableScalarTests(unittest.TestCase):
    def test_forward_get_and_set_all_cartesian_types(self):
        for action in ('GET_VAR','SET_VAR'):
            for kind in POSES:
                p,_=build(second=kind,action=action);v=p.run();self.assertAlmostEqual(x(v['B']),100.);self.assertEqual((v['E'],v['S']),(1,0))

    def test_inverse_get_and_set_all_cartesian_types(self):
        for action in ('GET_VAR','SET_VAR'):
            for kind in POSES:
                p,_=build(first=kind,second='JOINTPOS2',action=action,ctx=callback_context(inverse=lambda *args:joint([3.,4.])));self.assertEqual(p.run()['B']['axes'],[3.,4.])

    def test_forward_nine_axis_padding(self):
        p,_=build(first='JOINTPOS');self.assertAlmostEqual(x(p.run()['B']),100.)

    def test_inverse_nine_axis_output(self):
        p,_=build(first='POSITION',second='JOINTPOS',ctx=model_context((0.,90.)));p._state.values['A']=p._state.execution.robot.model.forward(joint([0.,90.]),identity_pose(),identity_pose())[0];self.assertEqual(p.run()['B']['axes'],[0.,90.]+[0.]*7)

    def test_inverse_uses_current_seed_not_receiver(self):
        calls=[]
        def inverse(seed,*args):calls.append(seed.values[:]);return joint([3.,4.])
        p,_=build(first='POSITION',second='JOINTPOS2',ctx=callback_context(inverse=inverse,values=(1.,2.)));p._state.values['B']=joint([99.,99.]);p.run();self.assertEqual(calls,[[1.,2.]])

    def test_selected_frame_and_tool(self):
        seen=[]
        def forward(joints,frame,tool,selector):seen.append((frame.values['LOCATION'].values['X'],tool.values['LOCATION'].values['X']));v=identity_pose();return v,v.values['CONFIG_DATA'],[0.,0.,0.]
        ctx=callback_context(forward=forward);ctx.robot.frames[2]=identity_pose();ctx.robot.frames[2].values['LOCATION'].values['X']=10.;ctx.robot.tools[3]=identity_pose();ctx.robot.tools[3].values['LOCATION'].values['X']=20.;ctx.robot.active_frame=2;ctx.robot.active_tool=3
        p,_=build(ctx=ctx);p.run();self.assertEqual(seen,[(10.,20.)])

    def test_supplied_forward_external_metadata(self):
        p,_=build(second='XYZWPREXT',ctx=callback_context(forward=forward_adapter([],external=[7.,8.,9.])));v=p.run()['B'];self.assertEqual([v['EXT'+str(i)] for i in range(1,4)],[7.,8.,9.])

    def test_inverse_retains_supplied_external_slots(self):
        seen=[]
        def inverse(seed,point,frame,tool,selector,config,external):seen.append(external.values[:]);return joint([3.,4.])
        p,_=build(first='XYZWPREXT',second='JOINTPOS2',ctx=callback_context(inverse=inverse));p._state.values['A'].values.update(EXT1=10.,EXT2=20.,EXT3=30.);p.run();self.assertEqual(seen,[[10.,20.,30.]])

    def test_no_robot_service_retains_status_only_incompatibility(self):
        p,_=build(ctx=rt.ExecutionContext());v=p.run();self.assertEqual((v['E'],v['S']),(99,3));self.assertEqual(p._state.execution.entries,{})

    def test_limits_only_context_does_not_invent_adapter(self):
        ctx=callback_context();p,_=build(ctx=ctx);failed(self,p,'adapter')

    def test_missing_inverse_seed_fails_without_publication(self):
        ctx=callback_context(inverse=lambda *args:joint([0.,0.]));ctx.robot.current=None;p,_=build(first='POSITION',second='JOINTPOS2',ctx=ctx);failed(self,p,'current joints')

    def test_wrong_model_output_width_keeps_outputs(self):
        p,_=build(first='POSITION',second='JOINTPOS3');failed(self,p,'model axes')

    def test_invalid_forward_adapter_result_keeps_outputs(self):
        p,_=build(ctx=callback_context(forward=lambda *args:(identity_pose(),identity_pose().values['CONFIG_DATA'],[0.])));failed(self,p)

    def test_invalid_inverse_adapter_result_keeps_outputs(self):
        p,_=build(first='POSITION',second='JOINTPOS2',ctx=callback_context(inverse=lambda *args:joint([1.,2.,3.])));failed(self,p)


class ModelVariablePrefixTests(unittest.TestCase):
    def test_forward_get_and_set_smaller_prefix_retains_tail(self):
        for action in ('GET_VAR','SET_VAR'):
            p,_=arrays(action=action);tail=p._state.values['B'].values[-1];tail.values['LOCATION'].values['X']=77.;v=p.run();self.assertEqual((x(v['B'][0]),x(v['B'][1]),x(v['B'][2]),v['S']),(100.,100.,77.,0));self.assertIs(p._state.values['B'].values[-1],tail)

    def test_inverse_array_get_and_set(self):
        for action in ('GET_VAR','SET_VAR'):
            p,_=arrays(first='POSITION',second='JOINTPOS2',action=action,ctx=callback_context(inverse=lambda *args:joint([3.,4.])));self.assertEqual(p.run()['B'][1]['axes'],[3.,4.])

    def test_two_and_three_dimensional_row_major_prefixes(self):
        for shape in ('1,2','1,1,2'):
            p,_=arrays(source=shape,target=shape.replace('2','3'));p.run();self.assertEqual(len([r for r in p.service_requests if r['operation']=='KINEMATIC_ASSIGNMENT']),2)

    def test_equal_count_different_rank_stays_incompatible(self):
        calls=[];p,_=arrays(source='2',target='1,2',ctx=callback_context(forward=forward_adapter(calls)));self.assertEqual(p.run()['S'],3);self.assertEqual(calls,[])

    def test_ignored_source_numeric_tail_is_not_converted(self):
        calls=[];p,_=arrays(source='3',target='2',ctx=callback_context(forward=forward_adapter(calls)));p._state.values['A'].values[-1].values[0]=float('nan');self.assertEqual(p.run()['S'],0);self.assertEqual(len(calls),2)

    def test_late_bad_selected_geometry_precedes_all_calls(self):
        calls=[];p,_=arrays(ctx=callback_context(forward=forward_adapter(calls)));p._state.values['A'].values[-1].values[0]=float('nan');failed(self,p);self.assertEqual(calls,[])

    def test_partial_selected_joint_precedes_all_calls(self):
        calls=[];p,_=arrays(ctx=callback_context(forward=forward_adapter(calls)));p._state.values['A'].values[-1].values[1]=rt.UNINITIALIZED;failed(self,p);self.assertEqual(calls,[])

    def test_missing_selected_pose_precedes_all_calls(self):
        calls=[];p,_=arrays(first='POSITION',second='JOINTPOS2',ctx=callback_context(inverse=lambda *args:calls.append(1)));p._state.values['A'].values[-1]=rt.UNINITIALIZED;failed(self,p);self.assertEqual(calls,[])

    def test_missing_whole_positional_array_is_rejected(self):
        p,_=arrays();p._state.values['A']=rt.UNINITIALIZED;failed(self,p)

    def test_late_adapter_failure_preserves_entire_prefix_and_cache(self):
        calls=[]
        def forward(*args):
            calls.append(1)
            if len(calls)==2:raise ValueError('late failure')
            v=identity_pose();return v,v.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=arrays(ctx=callback_context(forward=forward));failed(self,p,'late failure');self.assertEqual(calls,[1,1])

    def test_whole_source_is_captured_before_first_call(self):
        seen=[]
        def forward(joints,*args):
            seen.append(joints.values[:]);p._state.values['A'].values[-1].values[:]=[99.,99.];v=identity_pose();return v,v.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=arrays(ctx=callback_context(forward=forward));p.run();self.assertEqual(seen,[[0.,90.],[0.,90.]])

    def test_unselected_receiver_missing_tail_does_not_set_missing_status(self):
        p,_=arrays();v=p.run();self.assertEqual((v['B'][2]['LOCATION']['X'],v['S']),(U,0))

    def test_known_receiver_root_and_child_aliases_survive(self):
        p,_=arrays();array=p._state.values['B'];point=array.values[0];location=point.values['LOCATION'];ref=rt.field_reference(location,'X');p.run();self.assertIs(array,p._state.values['B']);self.assertIs(point,array.values[0]);self.assertIs(location,point.values['LOCATION']);self.assertEqual(ref.raw(),100.)


class ModelVariableRecordTests(unittest.TestCase):
    def test_records_get_and_set_map_fields_and_convert_ordinary_data(self):
        for action in ('GET_VAR','SET_VAR'):
            p,_=records(action=action);v=p.run();self.assertEqual((v['B']['LABEL'],v['B']['COUNT'],x(v['B']['POINT']),v['S']),('abc',7.,100.,0))

    def test_inverse_record_field(self):
        p,_=records(first='POSITION',second='JOINTPOS2',ctx=callback_context(inverse=lambda *args:joint([3.,4.])));self.assertEqual(p.run()['B']['POINT']['axes'],[3.,4.])

    def test_receiver_field_order_drives_model_calls(self):
        seen=[];prefix='TYPE one=STRUCTURE first:JOINTPOS2 second:JOINTPOS2 ENDSTRUCTURE two=STRUCTURE second:POSITION first:POSITION ENDSTRUCTURE'
        p,_=compile_program(call(),prefix=prefix,decl='a:one b:two e,s:INTEGER',context=callback_context(forward=forward_adapter(seen)));p._state.values['A'].values.update(FIRST=joint([1.,2.]),SECOND=joint([3.,4.]));p.run();self.assertEqual(seen,[[3.,4.],[1.,2.]])

    def test_nested_records_and_inner_array_layouts(self):
        prefix='TYPE one=STRUCTURE points:ARRAY[1,2]OF JOINTPOS2 ENDSTRUCTURE row=ARRAY[2]OF POSITION two=STRUCTURE points:ARRAY[1]OF row ENDSTRUCTURE'
        p,_=compile_program(call(),prefix=prefix,decl='a:one b:two e,s:INTEGER',context=model_context((0.,90.)))
        p._state.values['A'].values['POINTS'].values[:]=[joint([0.,90.]),joint([0.,90.])];v=p.run();self.assertEqual(x(v['B']['POINTS'][0][1]),100.)

    def test_mixed_forward_and_inverse_record_fields(self):
        prefix='TYPE one=STRUCTURE fwd:JOINTPOS2 inv:POSITION ENDSTRUCTURE two=STRUCTURE inv:JOINTPOS2 fwd:POSITION ENDSTRUCTURE';seen=[]
        p,_=compile_program(call(),prefix=prefix,decl='a:one b:two e,s:INTEGER',context=callback_context(forward=forward_adapter(seen),inverse=lambda *args:joint([3.,4.])));p._state.values['A'].values.update(FWD=joint([0.,90.]),INV=identity_pose());v=p.run();self.assertEqual((v['B']['INV']['axes'],len(seen)),([3.,4.],1))

    def test_missing_whole_record_clears_without_model_calls(self):
        calls=[];p,_=records(ctx=callback_context(forward=forward_adapter(calls)));p._state.values['A']=rt.UNINITIALIZED;v=p.run();self.assertEqual((v['B'],v['S'],calls),(U,12311,[]))

    def test_missing_ordinary_field_retains_missing_status(self):
        p,_=records();p._state.values['A'].values['COUNT']=rt.UNINITIALIZED;v=p.run();self.assertEqual((v['B']['COUNT'],v['S']),(U,12311))

    def test_missing_model_field_fails_before_any_adapter(self):
        calls=[];p,_=records(ctx=callback_context(forward=forward_adapter(calls)));p._state.values['A'].values['POINT']=rt.UNINITIALIZED;failed(self,p);self.assertEqual(calls,[])

    def test_late_numeric_domain_error_precedes_adapter(self):
        calls=[];p,_=records(ctx=callback_context(forward=forward_adapter(calls)));p._state.values['A'].values['COUNT']=True;failed(self,p);self.assertEqual(calls,[])

    def test_original_string_capacity_error_precedes_adapter(self):
        calls=[];p,_=records(ctx=callback_context(forward=forward_adapter(calls)));p._state.values['A'].values['LABEL']='over capacity';failed(self,p);self.assertEqual(calls,[])

    def test_substituted_record_schema_is_rejected(self):
        calls=[];p,_=records(ctx=callback_context(forward=forward_adapter(calls)));p._state.values['A'].spec=('STRUCTURE','OTHER',p._state.types['A'][2]);failed(self,p);self.assertEqual(calls,[])

    def test_record_prefix_stages_late_numeric_errors_before_models(self):
        from tests.test_record_variable_transfers import arrays as record_arrays
        calls=[];p,_=record_arrays(first='JOINTPOS2',second='POSITION',context=callback_context(forward=forward_adapter(calls)))
        for item in p._state.values['A'].values:item.values['COUNT']=joint([0.,90.])
        for item in p._state.values['B'].values[0].values:item.values['COUNT']=identity_pose()
        p._state.values.update(E=99,S=77);p._state.values['A'].values[-1].values['COUNT'].values[0]=float('nan');failed(self,p);self.assertEqual(calls,[])

    def test_record_prefix_missing_container_contributes_status(self):
        from tests.test_record_variable_transfers import arrays as record_arrays
        calls=[];p,_=record_arrays(first='JOINTPOS2',second='POSITION',context=callback_context(forward=forward_adapter(calls)))
        for item in p._state.values['B'].values[0].values:item.values['COUNT']=identity_pose()
        p._state.values['A'].values[0].values['COUNT']=joint([0.,90.]);p._state.values['A'].values[1]=rt.UNINITIALIZED;v=p.run();self.assertEqual((v['B'][0][1],v['S'],len(calls)),(U,12311,1))


class ModelVariableOrderingTests(unittest.TestCase):
    def test_set_source_capture_precedes_status_selector(self):
        p,_=compile_program("SET_VAR(e,'','B',a,codes[change()])",decl='a:JOINTPOS2 b:POSITION e:INTEGER codes:ARRAY[1]OF INTEGER',routines='ROUTINE change:INTEGER BEGIN a=CURJPOS(0,0) RETURN 1 END change',context=model_context((0.,90.)));p._state.values['A']=joint([0.,0.]);self.assertAlmostEqual(x(p.run()['B']),200.)

    def test_get_named_capture_follows_status_selector(self):
        p,_=compile_program("GET_VAR(e,'','A',b,codes[change()])",decl='a:JOINTPOS2 b:POSITION e:INTEGER codes:ARRAY[1]OF INTEGER',routines='ROUTINE change:INTEGER BEGIN a=CURJPOS(0,0) RETURN 1 END change',context=model_context((0.,90.)));p._state.values['A']=joint([0.,0.]);self.assertAlmostEqual(x(p.run()['B']),100.)

    def test_later_adapter_observes_explicit_frame_updates(self):
        seen=[]
        def forward(joints,frame,*args):
            seen.append(frame.values['LOCATION'].values['X']);ctx.robot.frames[0].values['LOCATION'].values['X']=7.;v=identity_pose();return v,v.values['CONFIG_DATA'],[0.,0.,0.]
        ctx=callback_context(forward=forward);p,_=arrays(ctx=ctx);p.run();self.assertEqual(seen,[0.,7.])

    def test_inverse_calls_do_not_chain_hidden_seed_updates(self):
        seen=[]
        def inverse(seed,*args):seen.append(seed.values[:]);return joint([99.,99.])
        p,_=arrays(first='POSITION',second='JOINTPOS2',ctx=callback_context(inverse=inverse,values=(1.,2.)));p.run();self.assertEqual(seen,[[1.,2.],[1.,2.]])

    def test_no_destination_is_published_during_adapter_calls(self):
        seen=[]
        def forward(*args):
            seen.append(p.snapshot()['B']);v=identity_pose();return v,v.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=arrays(ctx=callback_context(forward=forward));before=p.snapshot()['B'];p.run();self.assertEqual(seen,[before,before])

    def test_adapter_mutations_are_private_inputs(self):
        def forward(joints,frame,tool,*args):
            joints.values[0]=99.;frame.values['LOCATION'].values['X']=88.;tool.values['LOCATION'].values['X']=77.;v=identity_pose();return v,v.values['CONFIG_DATA'],[0.,0.,0.]
        ctx=callback_context(forward=forward);p,_=build(ctx=ctx);p.run();self.assertEqual((p.snapshot()['A']['axes'],ctx.robot.frames[0].values['LOCATION'].values['X']),([0.,90.],0.))

    def test_sticky_abort_stops_later_calls_and_cache_publication(self):
        seen=[]
        def forward(*args):
            seen.append(1)
            try:p._state.abort(33)
            except rt.KarelAbort:pass
            v=identity_pose();return v,v.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=arrays(ctx=callback_context(forward=forward));failed(self,p,exception=rt.KarelAbort);self.assertEqual(seen,[1])

    def test_abort_wins_over_adapter_exception(self):
        def forward(*args):
            try:p._state.abort(33)
            except rt.KarelAbort:pass
            raise ValueError('later error')
        p,_=build(ctx=callback_context(forward=forward));failed(self,p,exception=rt.KarelAbort)

    def test_repeated_success_reuses_context_cache(self):
        p,_=build(body=call()+' '+call());v=p.run();self.assertEqual((v['E'],len(p._state.execution.entries)),(1,1))

    def test_failure_retains_existing_unrelated_cache_entries(self):
        p,_=build(ctx=callback_context(forward=lambda *args:None));p._state.execution.entries[('OTHER','X')]=1;failed(self,p)


class ModelVariableBindingTests(unittest.TestCase):
    def test_explicit_foreign_binding_get(self):
        p,_=build(body="GET_VAR(e,'OTHER','POINT',b,s)");ref=p._state.execution.variables.define('OTHER','POINT',('JOINTPOS',2),joint([0.,90.]));self.assertAlmostEqual(x(p.run()['B']),100.);self.assertEqual(ref.raw().values,[0.,90.])

    def test_explicit_foreign_binding_set(self):
        p,_=build(body="SET_VAR(e,'OTHER','POINT',a,s)");ref=p._state.execution.variables.define('OTHER','POINT',('POSITION',),identity_pose());p.run();self.assertAlmostEqual(ref.raw().values['LOCATION'].values['X'],100.)

    def test_static_array_element_lookup(self):
        p,_=compile_program("GET_VAR(e,'','ITEMS[1]',b,s)",decl='items:ARRAY[1]OF JOINTPOS2 b:POSITION e,s:INTEGER',context=model_context((0.,90.)));p._state.values['ITEMS'].values[0]=joint([0.,90.]);self.assertEqual(x(p.run()['B']),100.)

    def test_static_record_field_lookup(self):
        p,_=records(body="GET_VAR(e,'','A.POINT',b.point,s)");self.assertEqual(x(p.run()['B']['POINT']),100.)

    def test_linked_callee_uses_root_caller_group(self):
        ctx=rt.ExecutionContext(robot=rt.RobotContext(groups={1:callback_context(forward=forward_adapter([])).robot,2:model_context((0.,90.)).robot},active_group=1))
        main="PROGRAM MAIN\n%DEFGROUP=2\nVAR a:JOINTPOS2 b:POSITION ROUTINE work FROM LIB BEGIN a=CURJPOS(0,0) work END MAIN"
        lib="PROGRAM LIB\n%DEFGROUP=1\nVAR a FROM MAIN:JOINTPOS2 b FROM MAIN:POSITION e,s:INTEGER ROUTINE work BEGIN GET_VAR(e,'MAIN','A',b,s) END work BEGIN END LIB"
        project=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);project.run('MAIN');self.assertEqual(x(project.programs['MAIN'].snapshot()['B']),100.)

    def test_missing_lookup_does_not_call_model_or_allocate_cache(self):
        seen=[];p,_=build(body="GET_VAR(e,'','MISSING',b,s)",ctx=callback_context(forward=forward_adapter(seen)));self.assertEqual((p.run()['S'],seen,p._state.execution.entries),(1,[],{}))

    def test_serializable_model_json_replay_retains_schemas(self):
        p,_=records();state=p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));q,_=records(ctx=rt.ExecutionContext.from_config(saved));self.assertEqual(q.run(),state);self.assertEqual(len(q._state.execution.entries),1)

    def test_generic_helper_does_not_infer_model_context(self):
        p,_=records();source=ex.variable_value(p._state.types['A'],p._state.values['A']);target=rt.Reference(p._state.types['B'],p._state.values,'B')
        with rt._numeric_scope('pythonic'):self.assertIsNone(ex.variable_transfer(target,source,numeric=True,representations=True,records=True))

    def test_config_status_alias_remains_blocked(self):
        with self.assertRaises(TranslationError):compile_program("GET_VAR(e,'','A',b,c.cfg_turn_no1)",decl='a:JOINTPOS2 b:POSITION c:CONFIG e:INTEGER')

    def test_report_exposes_explicit_model_policy(self):
        _,r=build();policy=r.report['kinematic_variable_transfer_policy'];self.assertFalse(policy['controller_validated']);self.assertIn('prefix',policy['arrays']);self.assertIn('root-caller',policy['context']);json.dumps(r.report)


class ModelVariableAdditionalGuards(unittest.TestCase):
    def test_malformed_receiver_precedes_all_model_calls(self):
        seen=[];p,_=arrays(ctx=callback_context(forward=forward_adapter(seen)));p._state.values['B'].values[-1].types['LOCATION']=('INTEGER',)
        failed(self,p);self.assertEqual(seen,[])

    def test_improper_inverse_orientation_precedes_all_model_calls(self):
        seen=[];p,_=arrays(first='POSITION',second='JOINTPOS2',ctx=callback_context(inverse=lambda *args:seen.append(1)));p._state.values['A'].values[-1].values['NORMAL'].values['X']=2.
        failed(self,p);self.assertEqual(seen,[])

    def test_whole_missing_record_array_clears_without_calls(self):
        from tests.test_record_variable_transfers import arrays as record_arrays
        seen=[];p,_=record_arrays(first='JOINTPOS2',second='POSITION',context=callback_context(forward=forward_adapter(seen)))
        for item in p._state.values['B'].values[0].values:item.values['COUNT']=identity_pose()
        p._state.values['A']=rt.UNINITIALIZED;v=p.run();self.assertEqual((v['B'],v['S'],seen),(U,12311,[]))

    def test_original_ignored_record_tail_string_shape_is_validated(self):
        from tests.test_record_variable_transfers import arrays as record_arrays
        seen=[];p,_=record_arrays(source=3,target=2,first='JOINTPOS2',second='POSITION',context=callback_context(forward=forward_adapter(seen)))
        for item in p._state.values['A'].values:item.values['COUNT']=joint([0.,90.])
        for item in p._state.values['B'].values[0].values:item.values['COUNT']=identity_pose()
        p._state.values.update(E=99,S=77);p._state.values['A'].values[-1].values['LABEL']='over capacity';failed(self,p);self.assertEqual(seen,[])

    def test_nested_missing_record_container_remains_missing(self):
        prefix='TYPE child_in=STRUCTURE point:JOINTPOS2 ENDSTRUCTURE child_out=STRUCTURE point:POSITION ENDSTRUCTURE one=STRUCTURE item:child_in other:JOINTPOS2 ENDSTRUCTURE two=STRUCTURE item:child_out other:POSITION ENDSTRUCTURE'
        seen=[];p,_=compile_program(call(),prefix=prefix,decl='a:one b:two e,s:INTEGER',context=callback_context(forward=forward_adapter(seen)));p._state.values['A'].values.update(ITEM=rt.UNINITIALIZED,OTHER=joint([0.,90.]));v=p.run();self.assertEqual((v['B']['ITEM'],v['S'],len(seen)),(U,12311,1))

    def test_inner_record_array_dimension_change_stays_incompatible(self):
        prefix='TYPE one=STRUCTURE points:ARRAY[2]OF JOINTPOS2 ENDSTRUCTURE two=STRUCTURE points:ARRAY[3]OF POSITION ENDSTRUCTURE'
        seen=[];p,_=compile_program(call(),prefix=prefix,decl='a:one b:two e,s:INTEGER',context=callback_context(forward=forward_adapter(seen)));v=p.run();self.assertEqual((v['S'],seen,p._state.execution.entries),(3,[],{}))

    def test_changed_field_set_stays_incompatible_before_models(self):
        prefix='TYPE one=STRUCTURE point:JOINTPOS2 ENDSTRUCTURE two=STRUCTURE renamed:POSITION ENDSTRUCTURE'
        seen=[];p,_=compile_program(call(),prefix=prefix,decl='a:one b:two e,s:INTEGER',context=callback_context(forward=forward_adapter(seen)));v=p.run();self.assertEqual((v['S'],seen),(3,[]))

    def test_context_updates_inverse_seed_only_when_explicit(self):
        seen=[]
        def inverse(seed,*args):seen.append(seed.values[:]);ctx.robot.current=rt.RobotState(joints=[7.,8.]);return joint([99.,99.])
        ctx=callback_context(inverse=inverse,values=(1.,2.));p,_=arrays(first='POSITION',second='JOINTPOS2',ctx=ctx);p.run();self.assertEqual(seen,[[1.,2.],[7.,8.]])

    def test_model_failure_marks_service_history_failed(self):
        p,_=build(ctx=callback_context(forward=lambda *args:None));failed(self,p);self.assertEqual([(r['operation'],r['outcome']) for r in p.service_requests],[('GET_VAR','failed'),('KINEMATIC_ASSIGNMENT','failed')])

    def test_same_schema_partial_geometry_uses_ordinary_copy(self):
        p,_=build(first='JOINTPOS2',second='JOINTPOS2');p._state.values['A'].values[0]=rt.UNINITIALIZED;v=p.run();self.assertEqual((v['B']['axes'][0],v['S']),(U,12311));self.assertFalse(any(r['operation']=='KINEMATIC_ASSIGNMENT' for r in p.service_requests))

    def test_explicit_helper_is_not_available_in_legacy_scope(self):
        from karel2py.variable_kinematics import transfer
        p,_=build();source=ex.variable_value(p._state.types['A'],p._state.values['A']);target=rt.Reference(p._state.types['B'],p._state.values,'B')
        with rt._numeric_scope('strict'):self.assertIsNone(transfer(p._state,target,source,17))

    def test_live_callbacks_are_not_persisted_in_context_json(self):
        p,_=build(ctx=callback_context(forward=forward_adapter([])));p.run()
        saved=json.loads(json.dumps(p._state.execution.to_config()));restored=rt.ExecutionContext.from_config(saved);self.assertIsNone(restored.robot.forward);self.assertIsNone(restored.robot.inverse)


class ModelVariableReceiverRecheckTests(unittest.TestCase):
    def test_adapter_corrupted_receiver_is_rejected_before_cache_or_data_write(self):
        calls=[]
        def forward(*args):
            calls.append(1);p._state.values['B'].values[0].values.pop('CONFIG_DATA',None)
            v=identity_pose();return v,v.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=arrays(ctx=callback_context(forward=forward))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'malformed record'):p.run()
        self.assertEqual((p.snapshot()['E'],p.snapshot()['S'],p._state.execution.entries),(99,77,{}))
        self.assertEqual(calls,[1,1]);self.assertEqual(p.snapshot()['B'][0]['LOCATION']['X'],U)
        self.assertNotIn('CONFIG_DATA',p.snapshot()['B'][0])

    def test_adapter_replaced_receiver_schema_is_rejected_before_publication(self):
        def forward(*args):
            p._state.values['B']=rt.Structure(('VECTOR',))
            v=identity_pose();return v,v.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=build(ctx=callback_context(forward=forward))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'malformed record'):p.run()
        self.assertEqual((p.snapshot()['E'],p.snapshot()['S'],p._state.execution.entries),(99,77,{}))
        self.assertEqual(p.snapshot()['B'],dict(X=U,Y=U,Z=U))


class ModelVariableTailPublicationTests(unittest.TestCase):
    def test_adapter_updates_to_unselected_receiver_tail_are_retained(self):
        def forward(*args):
            p._state.values['B'].values[-1].values['LOCATION'].values['X']=88.
            v=identity_pose();return v,v.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=arrays(ctx=callback_context(forward=forward));tail=p._state.values['B'].values[-1];tail.values['LOCATION'].values['X']=77.
        values=p.run();self.assertEqual([x(value) for value in values['B']],[0.,0.,88.]);self.assertIs(p._state.values['B'].values[-1],tail);self.assertEqual(values['S'],0)


if __name__=='__main__':unittest.main()
