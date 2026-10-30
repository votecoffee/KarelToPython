"""Authored explicit-model ARRAY conversions with atomic destination publication."""
import copy
import json
import math
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from karel2py.kinematics import pose as identity_pose
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_cartesian_interfaces import value as cartesian,snapshot_x
from tests.test_extended_services import compile_program
from tests.test_joint_interoperability import joint,model_context
from tests.test_kinematic_assignments import callback_context
from tests.test_project_scheduler import source
from tests.test_variable_transfers import transfer

U={'uninitialized':True}
KINDS=('POSITION','XYZWPR','XYZWPREXT')


def values(kind,count=2,shape=None):
    leaf=('JOINTPOS',kind)if type(kind)is int else(kind,)
    result=rt.Array(('ARRAY',shape if shape is not None else count,leaf))
    result.values[:]=[joint(([0.,90.]+[0.]*9)[:kind])if type(kind)is int else cartesian(kind,(100.,100.,0.),(0.,0.,90.),(0.,0.,0.))for _ in result.values]
    return result


def build(body='b=a',first='JOINTPOS2',second='POSITION',shape='2',ctx=None,routines='',**options):
    return compile_program(body,decl=f'a:ARRAY[{shape}]OF {first} b:ARRAY[{shape}]OF {second} n,e,s:INTEGER done:BOOLEAN',routines=routines,context=ctx if ctx is not None else model_context((0.,90.)),**options)


def initialized(task,kind=2,shape=None):task._state.values['A']=values(kind,shape=shape);return task


def history(task,kind='ASSIGNMENT'):return [row for row in task.service_requests if row['operation']=='KINEMATIC_ARRAY_'+kind]


def forward_adapter(calls,*,external=None):
    def forward(joints,frame,tool,selector):
        calls.append(joints.values[:]);point=identity_pose();point.values['LOCATION'].values['X']=float(len(calls))
        return point,point.values['CONFIG_DATA'],external or[0.,0.,0.]
    return forward


class KinematicArrayAssignmentTests(unittest.TestCase):
    def test_forward_all_cartesian_representations_and_three_ranks(self):
        for kind in KINDS:
            for shape,text in [(2,'2'),((1,2),'1,2'),((1,1,2),'1,1,2')]:
                with self.subTest(kind=kind,shape=shape):
                    p,_=build(second=kind,shape=text);initialized(p,shape=shape);p.run()
                    for item in p._state.values['B'].values:
                        v=rt.snapshot_value(item);self.assertAlmostEqual(snapshot_x(v,kind),100.,places=8)
                        self.assertAlmostEqual(v['LOCATION']['Y']if kind=='POSITION'else v['Y'],100.,places=8)
                    self.assertEqual(history(p),[dict(operation='KINEMATIC_ARRAY_ASSIGNMENT',line=6,outcome='completed')])

    def test_inverse_all_cartesian_sources_to_native_and_padded_widths(self):
        for kind in KINDS:
            for width in(2,9):
                p,_=build(first=kind,second=f'JOINTPOS{width}');initialized(p,kind)
                with self.subTest(kind=kind,width=width):self.assertEqual(p.run()['B'][1]['axes'],[0.,90.]+[0.]*(width-2))

    def test_model_forward_native_and_nine_slot_inputs(self):
        for width in(2,9):
            p,_=build(first=f'JOINTPOS{width}');initialized(p,width);self.assertAlmostEqual(p.run()['B'][0]['LOCATION']['X'],100.)

    def test_missing_model_fails_without_destination_publication(self):
        p,_=build(ctx=rt.ExecutionContext());initialized(p);old=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'robot'):p.run()
        self.assertEqual(p.snapshot()['B'],old);self.assertEqual(history(p)[0]['outcome'],'failed')

    def test_inverse_requires_current_seed_not_receiver_contents(self):
        ctx=model_context();ctx.robot.current=None;p,_=build(first='POSITION',second='JOINTPOS2',ctx=ctx);initialized(p,'POSITION');p._state.values['B']=values(2);old=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'current joints'):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_selected_frame_and_tool_are_applied_without_robot_mutation(self):
        ctx=model_context((0.,0.));ctx.robot.frames[2]=identity_pose();ctx.robot.frames[2].values['LOCATION'].values['X']=10.
        ctx.robot.tools[3]=identity_pose();ctx.robot.tools[3].values['LOCATION'].values['Y']=20.;ctx.robot.active_frame=2;ctx.robot.active_tool=3
        p,_=build(ctx=ctx);initialized(p)
        for item in p._state.values['A'].values:item.values[:]=[0.,0.]
        before=copy.deepcopy(ctx.to_config()['robot']);v=p.run()['B'][0];self.assertAlmostEqual(v['LOCATION']['X'],190.);self.assertAlmostEqual(v['LOCATION']['Y'],20.);self.assertEqual(ctx.to_config()['robot'],before)

    def test_absent_selected_frame_fails_without_guessing(self):
        ctx=model_context();ctx.robot.active_frame=7;p,_=build(ctx=ctx);initialized(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'][0]['LOCATION']['X'],U)

    def test_bad_last_input_preflights_before_any_adapter(self):
        for bad in(rt.UNINITIALIZED,math.inf,True):
            calls=[];p,_=build(ctx=callback_context(forward=forward_adapter(calls)));initialized(p);p._state.values['A'].values[-1].values[0]=bad
            with self.subTest(bad=bad),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(calls,[]);self.assertEqual(history(p)[0]['outcome'],'failed')

    def test_improper_last_position_preflights_before_inverse_adapter(self):
        calls=[]
        def inverse(*args):calls.append(1);return joint([0.,90.])
        p,_=build(first='POSITION',second='JOINTPOS2',ctx=callback_context(inverse=inverse));initialized(p,'POSITION');p._state.values['A'].values[-1].values['NORMAL'].values['X']=7.
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[])

    def test_output_quota_fails_before_adapter(self):
        calls=[];p,_=compile_program('',context=callback_context(forward=forward_adapter(calls)));data=values(1,4000)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):p._state.kinematic_array(('ARRAY',4000,('POSITION',)),data,17)
        self.assertEqual(calls,[])

    def test_later_adapter_failure_retains_prior_effects_but_no_array_write(self):
        calls=[]
        def forward(joints,frame,tool,selector):
            calls.append(joints.values[:])
            if len(calls)==2:raise ValueError('scripted second failure')
            point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=build(ctx=callback_context(forward=forward));initialized(p);old=p.snapshot()['B']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'second failure'):p.run()
        self.assertEqual((len(calls),p.snapshot()['B']),(2,old));self.assertEqual(history(p)[0]['outcome'],'failed')

    def test_later_bad_adapter_output_rejects_entire_result(self):
        calls=[]
        def forward(*args):
            calls.append(1);point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,math.inf if len(calls)==2 else 0.]
        p,_=build(second='XYZWPREXT',ctx=callback_context(forward=forward));initialized(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'][0]['X'],U);self.assertEqual(len(calls),2)

    def test_destination_array_and_child_identities_survive_success(self):
        p,_=build();initialized(p);array=p._state.values['B'];item=array.values[0];location=item.values['LOCATION'];p.run()
        self.assertIs(p._state.values['B'],array);self.assertIs(array.values[0],item);self.assertIs(item.values['LOCATION'],location)

    def test_captured_source_survives_adapter_mutation_of_original(self):
        calls=[]
        def forward(joints,frame,tool,selector):
            calls.append(joints.values[:]);p._state.values['A'].values[-1].values[:]=[9.,9.];point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=build(ctx=callback_context(forward=forward));initialized(p);p.run();self.assertEqual(calls,[[0.,90.],[0.,90.]]);self.assertEqual(p.snapshot()['A'][-1]['axes'],[9.,9.])

    def test_forward_external_axes_survive_only_extended_receivers(self):
        for kind in KINDS:
            calls=[];p,_=build(second=kind,ctx=callback_context(forward=forward_adapter(calls,external=[7.,8.,9.])));initialized(p);v=p.run()['B'][0]
            if kind=='XYZWPREXT':self.assertEqual([v['EXT1'],v['EXT2'],v['EXT3']],[7.,8.,9.])
            else:self.assertNotIn('EXT1',v)

    def test_inverse_inputs_include_explicit_config_axes_and_detached_seed(self):
        seen=[]
        def inverse(seed,point,frame,tool,selector,config,axes):
            seen.append((seed.values[:],axes.values[:],selector));seed.values[0]=999.;return joint([10.,20.])
        ctx=callback_context(inverse=inverse,values=(1.,2.));p,_=build(first='XYZWPREXT',second='JOINTPOS2',ctx=ctx);initialized(p,'XYZWPREXT')
        p._state.values['A'].values[1].values['EXT1']=7.;self.assertEqual(p.run()['B'][1]['axes'],[10.,20.]);self.assertEqual(seen,[([1.,2.],[0.,0.,0.],0),([1.,2.],[7.,0.,0.],0)]);self.assertEqual(ctx.robot.current.joints.values,[1.,2.])

    def test_custom_forward_supports_every_explicit_joint_width(self):
        for width in range(1,10):
            calls=[];p,_=build(first=f'JOINTPOS{width}',ctx=callback_context(forward=forward_adapter(calls)));initialized(p,width);p.run();self.assertEqual(len(calls),2);self.assertEqual(len(calls[0]),width)

    def test_inverse_model_target_width_remains_checked(self):
        p,_=build(first='POSITION',second='JOINTPOS3');initialized(p,'POSITION')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'model axes'):p.run()


class KinematicArrayInterfaceTests(unittest.TestCase):
    def test_forward_argument_is_private_writable_and_source_unchanged(self):
        p,_=build('work(a)',routines='ROUTINE work(v:ARRAY OF POSITION) BEGIN v[1].location.x=77 n=TRUNC(v[1].location.x) END work');initialized(p);old=p.snapshot()['A'];self.assertEqual(p.run()['N'],77);self.assertEqual(p.snapshot()['A'],old);self.assertEqual(history(p,'ARGUMENT')[0]['outcome'],'completed')

    def test_inverse_argument_is_private_and_not_copied_back(self):
        p,_=build('work(a)',first='POSITION',second='JOINTPOS2',routines='ROUTINE work(v:ARRAY OF JOINTPOS2) BEGIN v[1]=v[2] n=ARRAY_LEN(v) END work');initialized(p,'POSITION');old=p.snapshot()['A'];self.assertEqual(p.run()['N'],2);self.assertEqual(p.snapshot()['A'],old)

    def test_converted_return_is_independent(self):
        p,_=build('b=make()',routines='ROUTINE make:ARRAY OF POSITION BEGIN RETURN a END make');initialized(p);self.assertAlmostEqual(p.run()['B'][0]['LOCATION']['X'],100.);self.assertEqual(len(history(p,'RETURN')),1)

    def test_inverse_return_uses_supplied_seed(self):
        p,_=build('b=make()',first='POSITION',second='JOINTPOS9',routines='ROUTINE make:ARRAY OF JOINTPOS9 BEGIN RETURN a END make');initialized(p,'POSITION');self.assertEqual(p.run()['B'][0]['axes'],[0.,90.]+[0.]*7)

    def test_two_dimensional_wildcard_result_keeps_shape(self):
        p,_=build('b=make()',shape='1,2',routines='ROUTINE make:ARRAY[*,*]OF POSITION BEGIN RETURN a END make');initialized(p,shape=(1,2));self.assertAlmostEqual(p.run()['B'][0][1]['LOCATION']['X'],100.)

    def test_argument_capture_precedes_later_source_mutation(self):
        p,_=build('work(a,later())',routines='ROUTINE later:INTEGER BEGIN a[1]=a[2] n=7 RETURN 0 END later ROUTINE work(v:ARRAY OF POSITION;x:INTEGER) BEGIN s=TRUNC(v[1].location.x) END work');initialized(p);p.run();self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,100))

    def test_failed_array_argument_skips_later_effects_and_callee(self):
        p,_=build('n=0 work(a,later())',routines='ROUTINE later:INTEGER BEGIN n=7 RETURN 0 END later ROUTINE work(v:ARRAY OF POSITION;x:INTEGER) BEGIN n=8 END work');initialized(p);p._state.values['A'].values[-1].values[0]=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],0);self.assertEqual(p._state.local_frames,[])

    def test_failed_return_skips_target_selector_and_unwinds_frames(self):
        p,_=compile_program('n=0 items[at()].points=make()',prefix='TYPE box_t=STRUCTURE points:ARRAY[2]OF POSITION ENDSTRUCTURE',decl='a:ARRAY[2]OF JOINTPOS2 items:ARRAY[1]OF box_t n:INTEGER',routines='ROUTINE at:INTEGER BEGIN n=7 RETURN 1 END at ROUTINE make:ARRAY OF POSITION BEGIN RETURN a END make',context=model_context());initialized(p);p._state.values['A'].values[-1].values[0]=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],0);self.assertEqual(p._state.local_frames,[])

    def test_paused_callee_keeps_converted_values_without_repeating_adapter(self):
        calls=[];p,_=build('work(a) done=TRUE',ctx=callback_context(forward=forward_adapter(calls)),routines='ROUTINE work(v:ARRAY OF POSITION) BEGIN v[1].location.x=77 PAUSE n=TRUNC(v[1].location.x) END work');initialized(p)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(len(calls),2);self.assertEqual(p.resume()['N'],77);self.assertEqual(len(calls),2);self.assertEqual(p._state.local_frames,[])

    def test_stop_releases_converted_frames_and_keeps_caller_input(self):
        p,_=build('work(a)',routines='ROUTINE work(v:ARRAY OF POSITION) BEGIN v[1].location.x=77 PAUSE n=1 END work');initialized(p);old=p.snapshot()['A']
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(p.snapshot()['A'],old);self.assertEqual(p._state.local_frames,[]);self.assertEqual(p.task_state,'stopped')

    def test_sticky_abort_after_first_adapter_stops_remaining_elements(self):
        calls=[]
        def forward(*args):
            calls.append(1)
            try:p._state.abort(33)
            except rt.KarelAbort:pass
            point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=build(ctx=callback_context(forward=forward));initialized(p)
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(calls,[1]);self.assertEqual(p.snapshot()['B'][0]['LOCATION']['X'],U);self.assertEqual(history(p)[0]['outcome'],'failed')

    def test_prior_abort_wins_over_later_adapter_exception(self):
        def forward(*args):
            try:p._state.abort(33)
            except rt.KarelAbort:pass
            raise ValueError('later failure')
        p,_=build(ctx=callback_context(forward=forward));initialized(p)
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(p.snapshot()['B'][0]['LOCATION']['X'],U)

    def test_linked_calls_use_caller_group(self):
        ctx=rt.ExecutionContext(robot=rt.RobotContext(groups={1:callback_context(inverse=lambda *args:joint([-7.,-7.]),values=(0.,0.)).robot,2:model_context((0.,90.)).robot},active_group=1))
        main='PROGRAM MAIN\n%DEFGROUP=2\nVAR a:ARRAY[2]OF JOINTPOS2 b:ARRAY[2]OF JOINTPOS2 ROUTINE work(v:ARRAY OF POSITION):ARRAY OF JOINTPOS2 FROM LIB BEGIN b=work(a) END MAIN'
        lib='PROGRAM LIB\n%DEFGROUP=1\nROUTINE work(v:ARRAY OF POSITION):ARRAY OF JOINTPOS2 BEGIN RETURN v END work BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);project.programs['MAIN']._state.values['A']=values(2);project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['B'][0]['axes'],[0.,90.])

    def test_callback_receives_private_declared_array(self):
        seen=[]
        def work(ref):seen.append(ref.spec);ref.raw().values[0].values['LOCATION'].values['X']=77.
        ctx=model_context();ctx.externals[('LIB','WORK')]=work;p,_=build('work(a)',ctx=ctx,routines='ROUTINE work(v:ARRAY OF POSITION) FROM LIB');initialized(p);old=p.snapshot()['A'];p.run();self.assertEqual(seen,[('ARRAY',2,('POSITION',))]);self.assertEqual(p.snapshot()['A'],old)

    def test_raw_callback_result_does_not_gain_automatic_model_conversion(self):
        ctx=model_context();ctx.externals[('LIB','MAKE')]=lambda:values(2);p,_=build('b=make()',ctx=ctx,routines='ROUTINE make:ARRAY OF POSITION FROM LIB')
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_reports_expose_assignment_argument_return_and_no_values(self):
        p,result=build('b=a work(a) b=make()',routines='ROUTINE work(v:ARRAY OF POSITION) BEGIN END work ROUTINE make:ARRAY OF POSITION BEGIN RETURN a END make');initialized(p);p.run()
        sites=json.loads(json.dumps(result.report))['kinematic_array_conversions'];self.assertEqual({s['operation']for s in sites},{'ASSIGNMENT','ARGUMENT','RETURN'});self.assertTrue(all(s['evaluated_once']and s['independent_value']for s in sites))
        rows=[r for r in p.service_requests if r['operation'].startswith('KINEMATIC_ARRAY_')];self.assertEqual(len(rows),3);self.assertTrue(all(set(row)=={'operation','line','outcome'}for row in rows))


class KinematicArrayBoundaryTests(unittest.TestCase):
    def test_named_source_arrays_keep_independent_converted_interfaces(self):
        for prefix,decl in [('TYPE joint_array=ARRAY[2]OF JOINTPOS2','a:joint_array b:ARRAY[2]OF POSITION'),('TYPE pose_array=ARRAY[2]OF POSITION','a:ARRAY[2]OF JOINTPOS2 b:pose_array')]:
            with self.subTest(decl=decl):
                p,_=compile_program('b=a',prefix=prefix,decl=decl,context=model_context((0.,90.)));p._state.values['A'].values[:]=values(2).values
                before=p._state.values['A'].spec;self.assertAlmostEqual(p.run()['B'][1]['LOCATION']['X'],100.)
                self.assertEqual(p._state.values['A'].spec,before);self.assertEqual(p._state.values['B'].spec,p._state.types['B'])

    def test_rank_and_concrete_shape_changes_stay_rejected(self):
        for decl in('a:ARRAY[2]OF JOINTPOS2 b:ARRAY[1,2]OF POSITION','a:ARRAY[2]OF JOINTPOS2 b:ARRAY[3]OF POSITION'):
            with self.subTest(decl=decl),self.assertRaises(TranslationError):compile_program('b=a',decl=decl)

    def test_byname_keeps_exact_terminal_types_and_entry_output(self):
        p,_=build("e=77 work(BYNAME('','A',e))",routines='ROUTINE work(v:ARRAY OF POSITION) BEGIN END work');initialized(p)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type does not match'):p.run()
        self.assertEqual(p.snapshot()['E'],77)

    def test_variable_transfers_without_robot_service_stay_incompatible(self):
        for action in('GET_VAR','SET_VAR'):
            p,_=build('e=77 '+(transfer(action,'A','b')if action=='GET_VAR'else transfer(action,'B','a')),ctx=rt.ExecutionContext());initialized(p);self.assertEqual((p.run()['S'],p.snapshot()['E']),(3,77));self.assertEqual(history(p),[])

    def test_legacy_source_and_runtime_guards_remain(self):
        for body,routines in[('b=a',''),('work(a)','ROUTINE work(v:ARRAY OF POSITION) BEGIN END work'),('','ROUTINE make:ARRAY OF POSITION BEGIN RETURN a END make')]:
            with self.subTest(body=body),self.assertRaises(TranslationError):legacy_translate('PROGRAM T VAR a:ARRAY[2]OF JOINTPOS2 b:ARRAY[2]OF POSITION '+routines+' BEGIN '+body+' END T')
        p,_=build();initialized(p)
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):p._state.kinematic_array(('ARRAY',2,('POSITION',)),values(2))

    def test_generic_checked_argument_and_result_helpers_remain_exact(self):
        with rt._numeric_scope('pythonic'):
            for fn in(lambda:rt.checked(('ARRAY',2,('POSITION',)),values(2)),lambda:rt.value_argument(('ARRAY',None,('POSITION',)),values(2)),lambda:rt.array_result(('ARRAY',None,('POSITION',)),values(2))):
                with self.subTest(fn=fn),self.assertRaises(rt.KarelRuntimeError):fn()

    def test_invalid_runtime_schemas_and_phase_are_source_located(self):
        p,_=build()
        with rt._numeric_scope('pythonic'):
            for target in(None,(),('ARRAY',True,('POSITION',)),('ARRAY',2,('JOINTPOS',0)),('ARRAY',2,('REAL',))):
                with self.subTest(target=target),self.assertRaises(rt.KarelRuntimeError)as err:p._state.kinematic_array(target,values(2),17)
                self.assertEqual(err.exception.line,17)
            with self.assertRaises(rt.KarelRuntimeError):p._state.kinematic_array(('ARRAY',2,('POSITION',)),values(2),17,kind=True)

    def test_missing_whole_array_and_malformed_last_element_fail(self):
        for bad in(rt.UNINITIALIZED,rt.UNKNOWN_BYTE):
            p,_=build();p._state.values['A']=bad
            with self.subTest(bad=bad),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['B'][0]['LOCATION']['X'],U)

    def test_saved_model_and_concrete_results_round_trip(self):
        ctx=model_context();p,_=build(ctx=ctx);initialized(p);p.run();saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved);self.assertEqual(restored.to_config(),saved)

    def test_context_free_array_conversion_still_needs_no_model(self):
        p,_=build(first='XYZWPR',second='POSITION',ctx=rt.ExecutionContext());initialized(p,'XYZWPR');self.assertAlmostEqual(p.run()['B'][0]['LOCATION']['X'],100.);self.assertEqual(history(p),[])

    def test_context_free_joint_width_conversion_uses_no_model(self):
        p,_=build(first='JOINTPOS2',second='JOINTPOS9',ctx=rt.ExecutionContext());initialized(p);self.assertEqual(p.run()['B'][0]['axes'],[0.,90.]+[0.]*7);self.assertEqual(history(p),[])


class KinematicArrayOrderingTests(unittest.TestCase):
    def test_later_adapter_failure_skips_assignment_target_selector(self):
        calls=[]
        def forward(*args):
            calls.append(1)
            if len(calls)==2:raise ValueError('second element')
            point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=compile_program('n=0 items[at()].points=a',prefix='TYPE box_t=STRUCTURE points:ARRAY[2]OF POSITION ENDSTRUCTURE',decl='a:ARRAY[2]OF JOINTPOS2 items:ARRAY[1]OF box_t n:INTEGER',routines='ROUTINE at:INTEGER BEGIN n=7 RETURN 1 END at',context=callback_context(forward=forward));initialized(p);old=p.snapshot()['ITEMS']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'second element'):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['ITEMS']),(0,old))

    def test_rhs_function_runs_once_and_observations_are_per_array(self):
        calls=[];p,_=build('n=0 b=make()',ctx=callback_context(forward=forward_adapter(calls)),routines='ROUTINE make:ARRAY OF JOINTPOS2 BEGIN n=n+1 RETURN a END make');initialized(p)
        self.assertEqual(p.run()['N'],1);self.assertEqual(len(calls),2);self.assertEqual(len(history(p)),1)

    def test_return_conversion_precedes_local_for_counter_and_frame_cleanup(self):
        seen=[]
        def forward(*args):
            seen.append(p._state.get('I'));point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=build('b=make()',ctx=callback_context(forward=forward),routines='ROUTINE make:ARRAY OF POSITION VAR i:INTEGER BEGIN FOR i=1 TO 1 DO RETURN a ENDFOR END make');initialized(p);p.run()
        self.assertEqual(seen,[1,1]);self.assertEqual(p._state.local_frames,[]);self.assertEqual(p._state.call_depth,0)

    def test_explicit_adapter_context_changes_apply_to_later_elements(self):
        seen=[]
        def inverse(seed,point,frame,tool,selector,config,axes):
            seen.append(seed.values[:]);ctx.robot.current=rt.RobotState(joints=[99.,4.]);return joint([1.,2.])
        ctx=callback_context(inverse=inverse,values=(3.,4.));p,_=build(first='POSITION',second='JOINTPOS2',ctx=ctx);initialized(p,'POSITION');p.run()
        self.assertEqual(seen,[[3.,4.],[99.,4.]]);self.assertEqual(ctx.robot.current.joints.values,[99.,4.])


if __name__=='__main__':unittest.main()
