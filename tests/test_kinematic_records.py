"""Authored model-backed record trees with preflight, ownership and exact boundaries."""
import copy
import json
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from karel2py.kinematics import pose as identity_pose
from tests.test_extended_services import compile_program
from tests.test_cartesian_interfaces import value as cartesian,snapshot_x
from tests.test_joint_interoperability import joint,model_context
from tests.test_kinematic_assignments import callback_context
from tests.test_kinematic_arrays import forward_adapter
from tests.legacy_numeric_support import translate as legacy_translate

U={'uninitialized':True}
POSES=('POSITION','XYZWPR','XYZWPREXT')


def types(first='JOINTPOS2',second='POSITION',counts=('INTEGER','REAL')):
    return f'TYPE in_t=STRUCTURE value:{first} count:{counts[0]} label:STRING[8] ENDSTRUCTURE out_t=STRUCTURE label:STRING[3] value:{second} count:{counts[1]} ENDSTRUCTURE'


def build(body='b=a',first='JOINTPOS2',second='POSITION',ctx=None,routines='',counts=('INTEGER','REAL'),**options):
    return compile_program(body,prefix=types(first,second,counts),decl='a:in_t b:out_t n,s,e,visits:INTEGER done:BOOLEAN',routines=routines,context=ctx if ctx is not None else model_context((0.,90.)),**options)


def geometry(kind):
    if kind.startswith('JOINTPOS'):
        width=int(kind[8:]) if kind[8:] else 9
        return joint(([0.,90.]+[0.]*9)[:width])
    return cartesian(kind,(100.,100.,0.),(0.,0.,90.),(0.,0.,0.))


def seed(p,kind='JOINTPOS2'):
    p._state.values['A'].values.update(VALUE=geometry(kind),COUNT=7,LABEL='abcdefgh');return p


def history(p,kind='ASSIGNMENT'):
    return [r for r in p.service_requests if r['operation']=='KINEMATIC_RECORD_'+kind]


def arrays(body='b=a',ctx=None,routines=''):
    prefix=types()+' out_row=ARRAY[2]OF out_t'
    p,r=compile_program(body,prefix=prefix,decl='a:ARRAY[1,2]OF in_t b:ARRAY[1]OF out_row n:INTEGER done:BOOLEAN',routines=routines,context=ctx if ctx is not None else model_context((0.,90.)))
    for i,item in enumerate(p._state.values['A'].values):item.values.update(VALUE=geometry('JOINTPOS2'),COUNT=i+1,LABEL='abcdefgh')
    return p,r


class ModelRecordValueTests(unittest.TestCase):
    def test_forward_all_cartesian_types(self):
        for kind in POSES:
            p,_=build(second=kind);seed(p);v=p.run()['B'];self.assertAlmostEqual(snapshot_x(v['VALUE'],kind),100.)
            self.assertEqual((v['LABEL'],v['COUNT']),('abc',7.));self.assertEqual(history(p)[0]['outcome'],'completed')

    def test_inverse_all_cartesian_types_native_and_padded(self):
        for kind in POSES:
            for width in (2,9):
                p,_=build(first=kind,second=f'JOINTPOS{width}');seed(p,kind)
                with self.subTest(kind=kind,width=width):self.assertEqual(p.run()['B']['VALUE']['axes'],[0.,90.]+[0.]*(width-2))

    def test_forward_model_nine_slot_input(self):
        p,_=build(first='JOINTPOS9');seed(p,'JOINTPOS9');self.assertAlmostEqual(p.run()['B']['VALUE']['LOCATION']['X'],100.)

    def test_custom_forward_accepts_each_explicit_width(self):
        for width in range(1,10):
            calls=[];p,_=build(first=f'JOINTPOS{width}',ctx=callback_context(forward=forward_adapter(calls)));seed(p,f'JOINTPOS{width}');p.run()
            self.assertEqual(len(calls),1);self.assertEqual(len(calls[0]),width)

    def test_custom_inverse_requires_exact_output_width(self):
        p,_=build(first='POSITION',second='JOINTPOS9',ctx=callback_context(inverse=lambda *args:joint([1.,2.])));seed(p,'POSITION');before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],before)

    def test_receiver_field_order_and_names_retained(self):
        p,_=build();seed(p);p.run();self.assertEqual(list(p._state.values['B'].values),['LABEL','VALUE','COUNT']);self.assertEqual(p._state.values['B'].spec[1],'OUT_T')

    def test_ordinary_missing_leaves_survive_model_conversion(self):
        p,_=build();seed(p);p._state.values['A'].values.update(COUNT=rt.UNINITIALIZED,LABEL=rt.UNINITIALIZED)
        result=p.run()['B'];self.assertEqual((result['COUNT'],result['LABEL']),(U,U));self.assertAlmostEqual(result['VALUE']['LOCATION']['X'],100.)

    def test_receiver_children_and_captured_references_stay_attached(self):
        p,_=build();seed(p);record=p._state.values['B'];point=record.values['VALUE'];location=point.values['LOCATION'];p.run()
        self.assertIs(p._state.values['B'],record);self.assertIs(record.values['VALUE'],point);self.assertIs(point.values['LOCATION'],location);self.assertAlmostEqual(location.values['X'],100.)

    def test_exact_partial_geometry_field_stays_partial(self):
        prefix='TYPE one=STRUCTURE input_pose:JOINTPOS2 keep:POSITION ENDSTRUCTURE two=STRUCTURE keep:POSITION input_pose:XYZWPR ENDSTRUCTURE'
        p,_=compile_program('b=a',prefix=prefix,decl='a:one b:two',context=model_context((0.,90.)));p._state.values['A'].values['INPUT_POSE']=geometry('JOINTPOS2')
        self.assertEqual(p.run()['B']['KEEP']['LOCATION']['X'],U)

    def test_selected_frame_and_tool_without_context_mutation(self):
        ctx=model_context((0.,0.));ctx.robot.frames[2]=identity_pose();ctx.robot.frames[2].values['LOCATION'].values['X']=10.
        ctx.robot.tools[3]=identity_pose();ctx.robot.tools[3].values['LOCATION'].values['Y']=20.;ctx.robot.active_frame=2;ctx.robot.active_tool=3
        p,_=build(ctx=ctx);seed(p);p._state.values['A'].values['VALUE'].values[:]=[0.,0.];before=copy.deepcopy(ctx.to_config()['robot']);v=p.run()['B']['VALUE']
        self.assertAlmostEqual(v['LOCATION']['X'],190.);self.assertAlmostEqual(v['LOCATION']['Y'],20.);self.assertEqual(ctx.to_config()['robot'],before)

    def test_forward_external_axes_retained_for_extended_receiver(self):
        calls=[];p,_=build(second='XYZWPREXT',ctx=callback_context(forward=forward_adapter(calls,external=[7.,8.,9.])));seed(p)
        v=p.run()['B']['VALUE'];self.assertEqual([v['EXT'+str(i)] for i in range(1,4)],[7.,8.,9.])

    def test_inverse_external_axes_and_detached_seed(self):
        seen=[]
        def inverse(seed,point,frame,tool,selector,config,axes):
            seen.append((seed.values[:],axes.values[:],selector));seed.values[0]=999.;return joint([1.,2.])
        ctx=callback_context(inverse=inverse,values=(3.,4.));p,_=build(first='XYZWPREXT',second='JOINTPOS2',ctx=ctx);seed(p,'XYZWPREXT');p._state.values['A'].values['VALUE'].values['EXT1']=7.
        self.assertEqual(p.run()['B']['VALUE']['axes'],[1.,2.]);self.assertEqual(seen,[([3.,4.],[7.,0.,0.],0)]);self.assertEqual(ctx.robot.current.joints.values,[3.,4.])


class ModelRecordPreflightTests(unittest.TestCase):
    def test_missing_robot_has_failed_observation_and_no_publication(self):
        p,_=build(ctx=rt.ExecutionContext());seed(p);before=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'robot'):p.run()
        self.assertEqual(p.snapshot()['B'],before);self.assertEqual(history(p)[0]['outcome'],'failed')

    def test_missing_model_operand_fails_before_any_adapter(self):
        calls=[];p,_=arrays(ctx=callback_context(forward=forward_adapter(calls)));p._state.values['A'].values[-1].values['VALUE'].values[-1]=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[])

    def test_invalid_late_position_matrix_precedes_all_adapters(self):
        calls=[]
        prefix='TYPE one=STRUCTURE first:JOINTPOS2 last:POSITION ENDSTRUCTURE two=STRUCTURE first:XYZWPR last:JOINTPOS2 ENDSTRUCTURE'
        p,_=compile_program('b=a',prefix=prefix,decl='a:one b:two',context=callback_context(forward=forward_adapter(calls),inverse=lambda *args:joint([0.,0.])))
        p._state.values['A'].values.update(FIRST=geometry('JOINTPOS2'),LAST=identity_pose());p._state.values['A'].values['LAST'].values['NORMAL'].values['X']=2.
        with self.assertRaisesRegex(rt.KarelRuntimeError,'orientation|rotation|orthonormal'):p.run()
        self.assertEqual(calls,[])

    def test_late_numeric_narrowing_failure_precedes_adapters(self):
        calls=[];p,_=build(counts=('INTEGER','BYTE'),ctx=callback_context(forward=forward_adapter(calls)));seed(p);p._state.values['A'].values['COUNT']=256
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[]);self.assertEqual(p.snapshot()['B']['COUNT'],{'unknown_byte':True})

    def test_original_string_capacity_is_validated_before_truncation(self):
        calls=[];p,_=build(ctx=callback_context(forward=forward_adapter(calls)));seed(p);p._state.values['A'].values['LABEL']='over capacity'
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[])

    def test_bad_known_leaf_in_late_record_precedes_adapters(self):
        calls=[];p,_=arrays(ctx=callback_context(forward=forward_adapter(calls)));p._state.values['A'].values[-1].values['COUNT']=True
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[])

    def test_source_schema_substitution_is_rejected(self):
        calls=[];p,_=build(ctx=callback_context(forward=forward_adapter(calls)));seed(p);a=p._state.values['A'];a.spec=('STRUCTURE','FOREIGN',a.spec[2]);before=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'declared schema'):p.run()
        self.assertEqual(calls,[]);self.assertEqual(p.snapshot()['B'],before)

    def test_malformed_source_storage_does_not_reach_adapter(self):
        for change in ('fields','types','values'):
            calls=[];p,_=build(ctx=callback_context(forward=forward_adapter(calls)));seed(p);a=p._state.values['A']
            if change=='fields':a.values.pop('COUNT')
            elif change=='types':a.types['COUNT']=('REAL',)
            else:a.values['VALUE'].values=[0.]
            with self.subTest(change=change),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(calls,[])

    def test_output_allocation_limit_precedes_model_calls(self):
        source=('STRUCTURE','ONE',(('VALUE',('JOINTPOS',1)),));target=('STRUCTURE','TWO',(('VALUE',('POSITION',)),))
        value=rt.Array(('ARRAY',4000,source))
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):rt.prepare_kinematic_record(('ARRAY',4000,target),value,17)

    def test_missing_frame_or_tool_has_no_adapter_call(self):
        for field in ('frames','tools'):
            calls=[];ctx=callback_context(forward=forward_adapter(calls));getattr(ctx.robot,field).clear();p,_=build(ctx=ctx);seed(p)
            with self.subTest(field=field),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(calls,[])

    def test_inverse_requires_current_seed_even_if_receiver_initialized(self):
        ctx=model_context();ctx.robot.current=None;p,_=build(first='POSITION',second='JOINTPOS2',ctx=ctx);seed(p,'POSITION');p._state.values['B'].values['VALUE']=joint([7.,7.]);before=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'current joints'):p.run()
        self.assertEqual(p.snapshot()['B'],before)

    def test_inverse_model_width_guard_is_retained(self):
        p,_=build(first='POSITION',second='JOINTPOS3');seed(p,'POSITION')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'model axes'):p.run()

    def test_model_solution_failure_keeps_destination(self):
        p,_=build(first='POSITION',second='JOINTPOS2');seed(p,'POSITION');p._state.values['A'].values['VALUE'].values['LOCATION'].values['X']=10000.;before=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'IK solution'):p.run()
        self.assertEqual(p.snapshot()['B'],before)


class ModelRecordOrderingTests(unittest.TestCase):
    def test_receiver_field_order_controls_adapter_calls(self):
        calls=[]
        prefix='TYPE one=STRUCTURE first:JOINTPOS2 second:JOINTPOS2 ENDSTRUCTURE two=STRUCTURE second:POSITION first:POSITION ENDSTRUCTURE'
        p,_=compile_program('b=a',prefix=prefix,decl='a:one b:two',context=callback_context(forward=forward_adapter(calls)))
        p._state.values['A'].values.update(FIRST=joint([1.,2.]),SECOND=joint([3.,4.]));v=p.run()['B']
        self.assertEqual(calls,[[3.,4.],[1.,2.]]);self.assertEqual((v['SECOND']['LOCATION']['X'],v['FIRST']['LOCATION']['X']),(1.,2.))

    def test_all_source_fields_captured_before_first_adapter(self):
        calls=[]
        def forward(joints,*args):
            calls.append(joints.values[:]);p._state.values['A'].values[-1].values['VALUE'].values[:]=[99.,99.]
            point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=arrays(ctx=callback_context(forward=forward));p.run();self.assertEqual(calls,[[0.,90.],[0.,90.]])

    def test_later_call_sees_explicit_context_changes(self):
        calls=[]
        def forward(joints,frame,tool,selector):
            calls.append(frame.values['LOCATION'].values['X']);ctx.robot.frames[0].values['LOCATION'].values['X']=7.
            point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        ctx=callback_context(forward=forward);p,_=arrays(ctx=ctx);p.run();self.assertEqual(calls,[0.,7.])

    def test_inverse_fields_do_not_chain_implicit_seeds(self):
        calls=[]
        def inverse(seed,*args):calls.append(seed.values[:]);return joint([99.,99.])
        prefix='TYPE one=STRUCTURE first:POSITION second:POSITION ENDSTRUCTURE two=STRUCTURE second:JOINTPOS2 first:JOINTPOS2 ENDSTRUCTURE'
        p,_=compile_program('b=a',prefix=prefix,decl='a:one b:two',context=callback_context(inverse=inverse,values=(1.,2.)));p._state.values['A'].values.update(FIRST=identity_pose(),SECOND=identity_pose());p.run()
        self.assertEqual(calls,[[1.,2.],[1.,2.]])

    def test_late_adapter_failure_preserves_receiver_and_prior_effects(self):
        calls=[]
        def forward(*args):
            calls.append(1)
            if len(calls)==2:raise ValueError('late failure')
            point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=arrays(ctx=callback_context(forward=forward));before=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'late failure'):p.run()
        self.assertEqual(calls,[1,1]);self.assertEqual(p.snapshot()['B'],before);self.assertEqual(history(p)[0]['outcome'],'failed')

    def test_invalid_adapter_output_keeps_destination(self):
        p,_=build(ctx=callback_context(forward=lambda *args:(identity_pose(),identity_pose().values['CONFIG_DATA'],[0.])));seed(p);before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],before)

    def test_rhs_conversion_precedes_target_selector(self):
        calls=[];prefix=types()+' box_t=STRUCTURE item:out_t ENDSTRUCTURE'
        p,_=compile_program('n=0 boxes[pick()].item=a',prefix=prefix,decl='a:in_t boxes:ARRAY[1]OF box_t n:INTEGER',routines='ROUTINE pick:INTEGER BEGIN n=1 RETURN 1 END pick',context=callback_context(forward=forward_adapter(calls)));seed(p)
        self.assertEqual((p.run()['N'],len(calls)),(1,1));self.assertEqual(p.snapshot()['BOXES'][0]['ITEM']['VALUE']['LOCATION']['X'],1.)

    def test_failed_conversion_skips_target_selector(self):
        prefix=types()+' box_t=STRUCTURE item:out_t ENDSTRUCTURE'
        p,_=compile_program('n=0 boxes[pick()].item=a',prefix=prefix,decl='a:in_t boxes:ARRAY[1]OF box_t n:INTEGER',routines='ROUTINE pick:INTEGER BEGIN n=1 RETURN 1 END pick',context=rt.ExecutionContext());seed(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],0)

    def test_function_source_is_evaluated_once(self):
        p,_=build('visits=0 b=make()',routines='ROUTINE make:in_t BEGIN visits=visits+1 RETURN a END make');seed(p);p.run();self.assertEqual((p.snapshot()['VISITS'],len(history(p))),(1,1))


class ModelRecordInterfaceTests(unittest.TestCase):
    def test_bare_and_grouped_arguments_are_private(self):
        for actual in ('a','(a)'):
            p,_=build(f'work({actual})',routines='ROUTINE work(v:out_t) BEGIN v.value.location.x=77 v.count=99 n=TRUNC(v.value.location.x) END work');seed(p);before=p.snapshot()['A'];self.assertEqual(p.run()['N'],77);self.assertEqual(p.snapshot()['A'],before);self.assertEqual(len(history(p,'ARGUMENT')),1)

    def test_same_schema_argument_remains_borrowed(self):
        p,_=build('work(a)',routines='ROUTINE work(v:in_t) BEGIN v.count=99 END work');seed(p);self.assertEqual(p.run()['A']['COUNT'],99);self.assertEqual(history(p,'ARGUMENT'),[])

    def test_forwarded_exact_formal_aliases_only_private_record(self):
        routines='ROUTINE inner(v:out_t) BEGIN v.value.location.x=77 END inner ROUTINE work(v:out_t) BEGIN inner(v) n=TRUNC(v.value.location.x) END work'
        p,_=build('work(a)',routines=routines);seed(p);before=p.snapshot()['A'];self.assertEqual(p.run()['N'],77);self.assertEqual(p.snapshot()['A'],before)

    def test_retained_handler_can_own_converted_record(self):
        routines='ROUTINE work(v:out_t) BEGIN CONDITION[1]: WHEN EVENT[1] DO v.count=99 n=TRUNC(v.count) ENDCONDITION END work'
        p,_=build('work(a) ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=routines);seed(p);self.assertEqual((p.run()['N'],p.snapshot()['A']['COUNT']),(99,7))

    def test_pause_resume_does_not_replay_conversion(self):
        calls=[];p,_=build('work(a)',ctx=callback_context(forward=forward_adapter(calls)),routines='ROUTINE work(v:out_t) BEGIN PAUSE v.value.location.x=77 n=TRUNC(v.value.location.x) END work');seed(p)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(len(calls),1);p.resume();self.assertEqual((len(calls),p.snapshot()['N'],p._state.local_frames),(1,77,[]))

    def test_stop_or_abort_never_copies_private_record_back(self):
        for stop in ('PAUSE','ABORT'):
            p,_=build('work(a)',routines=f'ROUTINE work(v:out_t) BEGIN v.count=99 {stop} END work');seed(p);before=p.snapshot()['A']
            with self.assertRaises(rt.KarelPause if stop=='PAUSE' else rt.KarelAbort):p.run()
            if stop=='PAUSE':p.stop()
            self.assertEqual((p.snapshot()['A'],p._state.local_frames),(before,[]))

    def test_failure_retains_earlier_global_effects_without_copyback(self):
        p,_=build('work(a)',routines='ROUTINE work(v:out_t) BEGIN n=1 v.count=99 s=1 DIV 0 END work');seed(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['A']['COUNT'],p._state.local_frames),(1,7,[]))

    def test_capture_finishes_before_later_argument(self):
        routines='ROUTINE later:INTEGER BEGIN a.count=99 RETURN 0 END later ROUTINE work(v:out_t;x:INTEGER) BEGIN n=TRUNC(v.count) END work'
        p,_=build('work(a,later())',routines=routines);seed(p);self.assertEqual((p.run()['N'],p.snapshot()['A']['COUNT']),(7,99))

    def test_failed_argument_skips_later_argument_and_entry(self):
        routines='ROUTINE later:INTEGER BEGIN n=1 RETURN 0 END later ROUTINE work(v:out_t;x:INTEGER) BEGIN n=2 END work'
        p,_=build('n=0 work(a,later())',ctx=rt.ExecutionContext(),routines=routines);seed(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p._state.local_frames),(0,[]))

    def test_return_owns_declared_schema(self):
        p,_=build('b=make()',routines='ROUTINE make:out_t BEGIN RETURN a END make');seed(p);p.run();self.assertEqual(len(history(p,'RETURN')),1);self.assertEqual(p._state.values['B'].spec[1],'OUT_T')

    def test_opposite_argument_and_return_conversions(self):
        p,_=build('a=work(a)',counts=('INTEGER','INTEGER'),routines='ROUTINE work(v:out_t):in_t BEGIN RETURN v END work');seed(p);self.assertEqual(p.run()['A']['VALUE']['axes'],[0.,90.]);self.assertEqual((len(history(p,'ARGUMENT')),len(history(p,'RETURN'))),(1,1))

    def test_return_captures_fresh_counter_before_cleanup(self):
        routine="ROUTINE make:out_t VAR local:in_t BEGIN local.value=a.value local.label='abc' FOR local.count=1 TO 2 DO RETURN local ENDFOR RETURN local END make"
        p,_=build('b=make()',routines=routine);seed(p);self.assertEqual(p.run()['B']['COUNT'],1.);self.assertEqual(p._state.local_frames,[])

    def test_timer_on_private_converted_count_is_released(self):
        p,_=build('work(a)',counts=('INTEGER','INTEGER'),routines='ROUTINE work(v:out_t) BEGIN CONNECT TIMER TO v.count v.count=99 END work',clock_us=lambda:0);seed(p);self.assertEqual((p.run()['A']['COUNT'],p._state.execution._timer_claims),(7,{}))

    def test_computed_using_owns_converted_result(self):
        p,_=build('USING make() DO value.location.x=77 n=TRUNC(value.location.x) ENDUSING',routines='ROUTINE make:out_t BEGIN RETURN a END make');seed(p);before=p.snapshot()['A'];self.assertEqual(p.run()['N'],77);self.assertEqual(p.snapshot()['A'],before)


class ModelRecordArrayTests(unittest.TestCase):
    def test_record_array_layout_and_receiver_components(self):
        p,_=arrays();v=p.run()['B'];self.assertEqual([r['COUNT'] for r in v[0]],[1.,2.]);self.assertEqual(p._state.values['B'].spec[2][3],'OUT_ROW');self.assertAlmostEqual(v[0][1]['VALUE']['LOCATION']['X'],100.)

    def test_record_array_argument_is_private(self):
        p,_=arrays('work(a)',routines='ROUTINE work(v:ARRAY OF out_row) BEGIN v[1,1].count=99 n=TRUNC(v[1,1].count) END work');self.assertEqual((p.run()['N'],p.snapshot()['A'][0][0]['COUNT']),(99,1))

    def test_record_array_return_uses_target_schema(self):
        p,_=arrays('b=make()',routines='ROUTINE make:ARRAY OF out_row BEGIN RETURN a END make');p.run();self.assertEqual(len(history(p,'RETURN')),1)

    def test_generic_record_array_receiver_uses_actual_layout(self):
        p,r=arrays('work(b,a)',routines='ROUTINE work(dst:ARRAY[*,*]OF out_t;src:ARRAY[*,*]OF in_t) BEGIN dst=src END work');before=p._state.values['B'].spec;p.run();self.assertEqual(p._state.values['B'].spec,before);self.assertTrue(r.report['kinematic_record_conversions'][0]['actual_receiver_schema'])

    def test_nested_array_field_converts_every_model_leaf(self):
        prefix='TYPE in_child=STRUCTURE n:INTEGER value:JOINTPOS2 ENDSTRUCTURE out_child=STRUCTURE value:POSITION n:REAL ENDSTRUCTURE row_t=ARRAY[2]OF out_child in_t=STRUCTURE data:ARRAY[1,2]OF in_child ENDSTRUCTURE out_t=STRUCTURE data:ARRAY[1]OF row_t ENDSTRUCTURE'
        calls=[];p,_=compile_program('b=a',prefix=prefix,decl='a:in_t b:out_t',context=callback_context(forward=forward_adapter(calls)))
        for i,item in enumerate(p._state.values['A'].values['DATA'].values):item.values.update(N=i,VALUE=geometry('JOINTPOS2'))
        result=p.run()['B']['DATA'];self.assertEqual(len(calls),2);self.assertEqual((result[0][0]['N'],result[0][1]['N']),(0.,1.))

    def test_unknown_logical_shape_failure_skips_adapters(self):
        prefix=types();calls=[];p,_=compile_program('work(b,a)',prefix=prefix,decl='a:ARRAY[2,2]OF in_t b:ARRAY[1,4]OF out_t',routines='ROUTINE work(dst:ARRAY[*,*]OF out_t;src:ARRAY[*,*]OF in_t) BEGIN dst=src END work',context=callback_context(forward=forward_adapter(calls)))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[])

    def test_known_logical_shape_mismatch_is_rejected(self):
        with self.assertRaises(TranslationError):compile_program('b=a',prefix=types(),decl='a:ARRAY[2,2]OF in_t b:ARRAY[1,4]OF out_t')


class ModelRecordAbortAndLinkTests(unittest.TestCase):
    def test_sticky_abort_stops_later_fields_and_publication(self):
        calls=[]
        def forward(*args):
            calls.append(1)
            try:p._state.abort(33)
            except rt.KarelAbort:pass
            point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=arrays(ctx=callback_context(forward=forward));before=p.snapshot()['B']
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(calls,[1]);self.assertEqual(p.snapshot()['B'],before);self.assertEqual(history(p)[0]['outcome'],'failed')

    def test_abort_wins_over_adapter_exception(self):
        def forward(*args):
            try:p._state.abort(33)
            except rt.KarelAbort:pass
            raise ValueError('later failure')
        p,_=build(ctx=callback_context(forward=forward));seed(p)
        with self.assertRaises(rt.KarelAbort):p.run()

    def test_linked_roundtrip_uses_root_caller_group(self):
        ctx=rt.ExecutionContext(robot=rt.RobotContext(groups={1:callback_context(inverse=lambda *args:joint([-7.,-7.]),values=(0.,0.)).robot,2:model_context((0.,90.)).robot},active_group=1))
        prefix=types(counts=('INTEGER','INTEGER'))
        main='PROGRAM MAIN\n%DEFGROUP=2\n'+prefix+' VAR a:in_t b:in_t ROUTINE work(v:out_t):in_t FROM LIB BEGIN b=work(a) END MAIN'
        lib='PROGRAM LIB\n%DEFGROUP=1\n'+prefix+' ROUTINE work(v:out_t):in_t BEGIN RETURN v END work BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);seed(project.programs['MAIN']);project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['B']['VALUE']['axes'],[0.,90.])

    def test_callback_receives_private_declared_record(self):
        seen=[]
        def work(ref):seen.append(ref.spec[1]);ref.raw().values['COUNT']=99.
        ctx=model_context((0.,90.));ctx.externals[('LIB','WORK')]=work;p,_=build('work(a)',ctx=ctx,routines='ROUTINE work(v:out_t) FROM LIB');seed(p);self.assertEqual((p.run()['A']['COUNT'],seen),(7,['OUT_T']))

    def test_raw_callback_result_keeps_exact_nominal_contract(self):
        ctx=model_context();p,_=build('b=make()',ctx=ctx,routines='ROUTINE make:out_t FROM LIB');seed(p);ctx.externals[('LIB','MAKE')]=lambda:p._state.values['A']
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_mismatched_linked_signatures_remain_rejected(self):
        prefix=types();main='PROGRAM MAIN '+prefix+' VAR a:in_t ROUTINE work(v:out_t) FROM LIB BEGIN work(a) END MAIN';lib='PROGRAM LIB '+prefix+' ROUTINE work(v:in_t) BEGIN END work BEGIN END LIB'
        with self.assertRaisesRegex(ValueError,'type mismatch'):translate_project({'main':main,'lib':lib}).instantiate()


class ModelRecordBoundaryTests(unittest.TestCase):
    def test_context_free_helper_never_infers_model_conversion(self):
        p,_=build();seed(p)
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.convert_record_schema(p._state.types['B'],p._state.values['A'])

    def test_generic_helpers_and_byname_remain_exact(self):
        p,_=build("e=77 work(BYNAME('','A',e))",routines='ROUTINE work(v:out_t) BEGIN END work');seed(p)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type does not match'):p.run()
        self.assertEqual(p.snapshot()['E'],77)
        with rt._numeric_scope('pythonic'):
            for fn in (rt.checked,rt.value_argument,rt.structure_value):
                with self.subTest(helper=fn.__name__),self.assertRaises(rt.KarelRuntimeError):fn(p._state.types['B'],p._state.values['A'])

    def test_legacy_runtime_and_source_guards_remain(self):
        p,_=build();seed(p)
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):p._state.kinematic_record(p._state.types['B'],p._state.values['A'])
        with self.assertRaises(TranslationError):legacy_translate('PROGRAM T '+types()+' VAR a:in_t b:out_t BEGIN b=a END T')

    def test_runtime_phase_and_invalid_schemas_are_source_located(self):
        p,_=build();seed(p)
        with rt._numeric_scope('pythonic'):
            for target in (None,(),('INTEGER',),('STRUCTURE','BAD',())):
                with self.subTest(target=target),self.assertRaises(rt.KarelRuntimeError) as caught:p._state.kinematic_record(target,p._state.values['A'],17)
                self.assertEqual(caught.exception.line,17)
            with self.assertRaises(rt.KarelRuntimeError):p._state.kinematic_record(p._state.types['B'],p._state.values['A'],17,kind=True)

    def test_context_free_records_still_need_no_robot(self):
        p,_=build(first='XYZWPR',second='POSITION',ctx=rt.ExecutionContext());seed(p,'XYZWPR');p.run();self.assertEqual(history(p),[])

    def test_json_preserves_model_data_and_record_schemas_only(self):
        ctx=model_context((0.,90.));p,_=build('IF UNINIT(done) THEN b=a done=TRUE ENDIF',ctx=ctx);seed(p);p.run();saved=json.loads(json.dumps(ctx.to_config()))
        replay,_=build('IF UNINIT(done) THEN b=a done=TRUE ENDIF',ctx=rt.ExecutionContext.from_config(saved));self.assertEqual(replay.run(),p.snapshot());self.assertEqual(replay._state.values['B'].spec,p._state.values['B'].spec);self.assertEqual(history(replay),[])

    def test_report_sites_and_model_policy_are_explicit(self):
        p,r=build('b=work(a)',counts=('INTEGER','INTEGER'),routines='ROUTINE work(v:out_t):in_t BEGIN RETURN v END work');seed(p);p.run();rows=r.report['kinematic_record_conversions']
        self.assertEqual([row['operation'] for row in rows],['RETURN','ARGUMENT','ASSIGNMENT'])
        for row in rows:self.assertTrue(row['geometry_preflight']);self.assertTrue(row['evaluated_once']);self.assertTrue(row['independent_value']);self.assertGreater(row['line'],0)
        self.assertTrue(rows[0]['before_cleanup']);policy=r.report['kinematic_record_policy'];self.assertFalse(policy['controller_validated']);self.assertIn('root-caller',policy['context']);self.assertEqual(policy['guide'],'docs/kinematic-records.md');json.dumps(r.report)


class ModelRecordMixedGuards(unittest.TestCase):
    def test_mixed_forward_inverse_fields_share_explicit_context(self):
        calls=[]
        def forward(*args):
            calls.append('forward');point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        def inverse(*args):calls.append('inverse');return joint([8.,9.])
        prefix='TYPE one=STRUCTURE first:JOINTPOS2 second:POSITION ENDSTRUCTURE two=STRUCTURE first:XYZWPR second:JOINTPOS2 ENDSTRUCTURE'
        p,_=compile_program('b=a',prefix=prefix,decl='a:one b:two',context=callback_context(forward=forward,inverse=inverse));p._state.values['A'].values.update(FIRST=geometry('JOINTPOS2'),SECOND=identity_pose())
        self.assertEqual(p.run()['B']['SECOND']['axes'],[8.,9.]);self.assertEqual(calls,['forward','inverse'])

    def test_forward_inputs_are_detached_from_source_and_context(self):
        def forward(joints,frame,tool,selector):
            joints.values[0]=99.;frame.values['LOCATION'].values['X']=99.;tool.values['LOCATION'].values['X']=99.
            point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        ctx=callback_context(forward=forward);p,_=build(ctx=ctx);seed(p);p.run()
        self.assertEqual(p.snapshot()['A']['VALUE']['axes'],[0.,90.]);self.assertEqual((ctx.robot.frames[0].values['LOCATION'].values['X'],ctx.robot.tools[0].values['LOCATION'].values['X']),(0.,0.))

    def test_late_context_free_geometry_failure_precedes_adapters(self):
        calls=[];prefix='TYPE one=STRUCTURE first:JOINTPOS2 last:JOINTPOS3 ENDSTRUCTURE two=STRUCTURE first:POSITION last:JOINTPOS2 ENDSTRUCTURE'
        p,_=compile_program('b=a',prefix=prefix,decl='a:one b:two',context=callback_context(forward=forward_adapter(calls)));p._state.values['A'].values.update(FIRST=geometry('JOINTPOS2'),LAST=joint([1.,2.,3.]))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[])

    def test_position_orientation_is_still_read_only(self):
        with self.assertRaises(TranslationError) as error:build('b=a b.value.normal.x=7')
        self.assertEqual(error.exception.code,'E_POSITION_READ_ONLY')


if __name__=='__main__':unittest.main()
