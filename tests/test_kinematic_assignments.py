"""Authored model-backed Cartesian/joint assignments and retained boundaries."""
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.kinematics import pose as identity_pose
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_joint_interoperability import joint,model_context
from tests.legacy_numeric_support import translate as legacy_translate


DECL='j,out: JOINTPOS p: POSITION e: XYZWPREXT a: XYZWPR s: INTEGER'
START='j=CURJPOS(0,0) '


def callback_context(*,forward=None,inverse=None,values=(10.,20.),**fields):
    return rt.ExecutionContext(robot=rt.RobotContext(forward=forward,inverse=inverse,
        current=rt.RobotState(joints=list(values)),frames={0:identity_pose()},tools={0:identity_pose()},**fields))


class AssignmentModelTests(unittest.TestCase):
    def test_joint_to_each_cartesian_representation(self):
        for target in ('p','a','e'):
            with self.subTest(target=target):
                state=run(START+f'{target}=j',decl=DECL,context=model_context((0.,90.)))
                actual=state[target.upper()];location=actual['LOCATION'] if target=='p' else actual
                self.assertAlmostEqual(location['X'],100.);self.assertAlmostEqual(location['Y'],100.)
                if target=='e': self.assertEqual([actual['EXT'+str(i)] for i in range(1,4)],[0.,0.,0.])

    def test_each_cartesian_representation_to_padded_joints(self):
        for target in ('p','a','e'):
            with self.subTest(target=target):
                state=run(START+f'{target}=j out={target}',decl=DECL,context=model_context((0.,90.)))
                self.assertEqual(state['OUT']['axes'],[0.,90.]+[0.]*7)

    def test_narrow_joint_input_and_output(self):
        ctx=model_context((0.,90.));p,_=compile_program('p=j out=p',decl=DECL.replace('j,out: JOINTPOS','j,out: JOINTPOS2'),context=ctx)
        p._state.values['J']=joint([0.,90.]);self.assertEqual(p.run()['OUT']['axes'],[0.,90.])

    def test_inverse_uses_current_seed_instead_of_destination_contents(self):
        ctx=model_context((0.,90.));p,_=compile_program(START+'p=j out=p',decl=DECL,context=ctx)
        p._state.values['OUT']=joint([100.,100.]+[0.]*7)
        self.assertEqual(p.run()['OUT']['axes'],[0.,90.]+[0.]*7)
        self.assertEqual(ctx.robot.current.joints.values,[0.,90.])

    def test_inverse_solves_new_target_within_tolerance(self):
        ctx=model_context((1.,89.));p,_=compile_program("CNV_STR_CONF('N',cfg,s) p=POS(100,100,0,0,0,90,cfg) out=p",decl=DECL+' cfg: CONFIG',context=ctx)
        result=p.run()['OUT']['axes'];point=ctx.robot.model.forward(joint(result),ctx.robot.frame(),ctx.robot.tool())[0]
        self.assertAlmostEqual(point.values['LOCATION'].values['X'],100.,delta=.02);self.assertAlmostEqual(point.values['LOCATION'].values['Y'],100.,delta=.02)

    def test_missing_robot_service_retains_destination(self):
        p,_=compile_program('p=j',decl=DECL);p._state.values['J']=joint([0.]*9)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'robot'): p.run()
        self.assertEqual(p.snapshot()['P']['LOCATION']['X'],{'uninitialized':True})

    def test_inverse_requires_current_joint_reference(self):
        ctx=model_context();ctx.robot.current=None;p,_=compile_program('out=p',decl=DECL,context=ctx)
        p._state.values['P']=identity_pose()
        p._state.values['OUT']=joint([7.]*9)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'current joints'): p.run()
        self.assertEqual(p.snapshot()['OUT']['axes'],[7.]*9)

    def test_limits_only_context_does_not_invent_a_model(self):
        ctx=rt.ExecutionContext(robot=rt.RobotContext(joint_limits=[(-180,180)],frames={0:identity_pose()},tools={0:identity_pose()}))
        p,_=compile_program('p=j',decl=DECL,context=ctx);p._state.values['J']=joint([0.]*9)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'adapter'): p.run()

    def test_invalid_or_partial_joint_input_is_rejected(self):
        for value in (joint([0.]*8+[1.]),joint([0.,rt.UNINITIALIZED]+[0.]*7),joint([0.,float('nan')]+[0.]*7),joint([0.]*3)):
            with self.subTest(value=value.values):
                p,_=compile_program('p=j',decl=DECL if len(value.values)==9 else DECL.replace('j,out: JOINTPOS','j,out: JOINTPOS3'),context=model_context());p._state.values['J']=value
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual(p.snapshot()['P']['LOCATION']['X'],{'uninitialized':True})

    def test_joint_limits_are_preserved(self):
        ctx=model_context((0.,90.));ctx.robot.model.limits[0]=(-5.,5.)
        p,_=compile_program('p=j',decl=DECL,context=ctx);p._state.values['J']=joint([90.,0.]+[0.]*7)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'limits'): p.run()

    def test_inverse_wrong_width_fails_without_model_callback(self):
        ctx=model_context();called=[];ctx.robot.inverse=lambda *args: called.append(args)
        p,_=compile_program('out=p',decl=DECL.replace('j,out: JOINTPOS','j: JOINTPOS out: JOINTPOS3'),context=ctx);p._state.values['P']=identity_pose()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'output'): p.run()
        self.assertEqual(called,[])

    def test_partial_pose_retains_joint_destination(self):
        p,_=compile_program('out=p',decl=DECL,context=model_context());p._state.values['OUT']=joint([7.]*9)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['OUT']['axes'],[7.]*9)

    def test_inverse_failure_does_not_change_destination(self):
        p,_=compile_program("CNV_STR_CONF('N',cfg,s) p=POS(10000,0,0,0,0,0,cfg) out=p",decl=DECL+' cfg: CONFIG',context=model_context())
        p._state.values['OUT']=joint([7.]*9)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'IK solution'): p.run()
        self.assertEqual(p.snapshot()['OUT']['axes'],[7.]*9)

    def test_selected_frame_and_tool_are_used(self):
        ctx=model_context((0.,0.));ctx.robot.frames[2]=identity_pose();ctx.robot.frames[2].values['LOCATION'].values['X']=10.
        ctx.robot.tools[3]=identity_pose();ctx.robot.tools[3].values['LOCATION'].values['Y']=20.;ctx.robot.active_frame=2;ctx.robot.active_tool=3
        state=run(START+'e=j out=e',decl=DECL,context=ctx)
        self.assertAlmostEqual(state['E']['X'],190.);self.assertAlmostEqual(state['E']['Y'],20.)
        self.assertEqual(state['OUT']['axes'],[0.]*9)

    def test_external_axes_survive_extended_roundtrip(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100},{'type':'prismatic','d':0}], 'external_axes':1,'current':{'joints':{'type':['JOINTPOS',2],'value':[0.,25.]}}}})
        state=run(START+'e=j out=e',decl=DECL,context=ctx)
        self.assertEqual([state['E'][key] for key in ('Z','EXT1','EXT2','EXT3')],[25.,25.,0.,0.]);self.assertEqual(state['OUT']['axes'],[0.,25.]+[0.]*7)

    def test_plain_pose_inverse_supplies_zero_external_axes(self):
        observed=[]
        def inverse(reference,point,frame,tool,selector,config,external): observed.append(list(external.values));return joint([0.,0.])
        ctx=callback_context(inverse=inverse);p,_=compile_program('out=p',decl=DECL.replace('j,out: JOINTPOS','j: JOINTPOS out: JOINTPOS2'),context=ctx)
        p._state.values['P']=identity_pose();p.run();self.assertEqual(observed,[[0.,0.,0.]])


class AssignmentAdapterTests(unittest.TestCase):
    def test_forward_callback_config_and_external_outputs_are_used(self):
        point=identity_pose();config=point.values['CONFIG_DATA'].clone();config.values['CFG_FLIP']=True
        state=run(START+'e=j',decl=DECL,context=callback_context(forward=lambda *args:(point,config,[1.,2.,3.])))
        self.assertTrue(state['E']['CONFIG_DATA']['CFG_FLIP']);self.assertEqual([state['E']['EXT'+str(i)] for i in range(1,4)],[1.,2.,3.])
        self.assertFalse(point.values['CONFIG_DATA'].values['CFG_FLIP'])

    def test_callback_inputs_are_detached_and_destination_is_independent(self):
        value=identity_pose();seen=[]
        def forward(joints,frame,tool,selector): joints.values[0]=999.;frame.values['LOCATION'].values['X']=999.;seen.append(selector);return value,value.values['CONFIG_DATA'],[0.,0.,0.]
        ctx=callback_context(forward=forward);p,_=compile_program(START+'e=j e.x=5',decl=DECL,context=ctx);p.run()
        self.assertEqual(p.snapshot()['J']['axes'][:2],[10.,20.]);self.assertEqual(ctx.robot.frames[0].values['LOCATION'].values['X'],0.);self.assertEqual(value.values['LOCATION'].values['X'],0.);self.assertEqual(seen,[0])

    def test_callback_errors_retain_destination_and_source_line(self):
        def forward(*args): raise ValueError('authored adapter failure')
        p,_=compile_program('p=j',decl=DECL,context=callback_context(forward=forward));p._state.values['J']=joint([0.]*9)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'authored adapter failure') as caught: p.run()
        self.assertIsNotNone(caught.exception.line);self.assertEqual(p.service_requests[-1]['outcome'],'failed')

    def test_malformed_forward_results_do_not_commit(self):
        point=identity_pose()
        broken=point.values['CONFIG_DATA'].clone();broken.values['UNKNOWN']=True
        for result in (None,(point,point.values['CONFIG_DATA'],[0.]),(point,point.values['CONFIG_DATA'],[0.,True,0.]),(point,broken,[0.,0.,0.]),(point,point.values['CONFIG_DATA'],None)):
            with self.subTest(result=result):
                p,_=compile_program('p=j',decl=DECL,context=callback_context(forward=lambda *args:result));p._state.values['J']=joint([0.]*9)
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual(p.snapshot()['P']['LOCATION']['X'],{'uninitialized':True})

    def test_inverse_callback_requires_exact_output_width(self):
        p,_=compile_program('out=p',decl=DECL,context=callback_context(inverse=lambda *args:joint([0.,0.])));p._state.values['P']=identity_pose()
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertTrue(all(row=={'uninitialized':True} for row in p.snapshot()['OUT']['axes']))

    def test_callback_requires_explicit_frame_tool_maps(self):
        ctx=callback_context(forward=lambda *args:None);ctx.robot.frames.clear()
        p,_=compile_program('p=j',decl=DECL,context=ctx);p._state.values['J']=joint([0.]*9)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'frame'): p.run()

    def test_swallowed_abort_cannot_commit_conversion(self):
        p=None
        def forward(*args):
            try: p._state.abort(99)
            except rt.KarelAbort: pass
            point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=compile_program('p=j',decl=DECL,context=callback_context(forward=forward));p._state.values['J']=joint([0.]*9)
        with self.assertRaises(rt.KarelAbort): p.run()
        self.assertEqual(p.snapshot()['P']['LOCATION']['X'],{'uninitialized':True})
        with self.assertRaises(rt.KarelAbort): p.run()

    def test_abort_remains_authoritative_over_a_later_adapter_error(self):
        p=None
        def forward(*args):
            try: p._state.abort(99)
            except rt.KarelAbort: pass
            raise ValueError('after abort')
        p,_=compile_program('p=j',decl=DECL,context=callback_context(forward=forward));p._state.values['J']=joint([0.]*9)
        with self.assertRaises(rt.KarelAbort): p.run()
        self.assertEqual(p.snapshot()['P']['LOCATION']['X'],{'uninitialized':True})


class AssignmentOwnershipTests(unittest.TestCase):
    def test_routine_conversions_use_explicit_model_with_legacy_guards(self):
        routines='ROUTINE take(value: POSITION) BEGIN value.location.x=99 END take ROUTINE produce: POSITION BEGIN RETURN j END produce'
        program,_=compile_program(START+'take(j) p=produce()',decl=DECL,routines=routines,context=model_context((0.,90.)))
        state=program.run()
        self.assertEqual(state['J']['axes'],[0.,90.]+[0.]*7)
        self.assertAlmostEqual(state['P']['LOCATION']['X'],100.)
        for body,routines in (('take(j)','ROUTINE take(value: POSITION) BEGIN END take'),('p=produce()','ROUTINE produce: POSITION BEGIN RETURN j END produce')):
            with self.subTest(body=body),self.assertRaises(TranslationError): legacy_translate(f'PROGRAM T VAR {DECL} {routines} BEGIN {body} END T')

    def test_whole_arrays_do_not_gain_element_conversion(self):
        with self.assertRaises(TranslationError): compile_program('poses=joints',decl='poses: ARRAY[2] OF POSITION joints: ARRAY[2] OF JOINTPOS')

    def test_conversion_of_function_result_precedes_target_selector(self):
        trace=[]
        def forward(*args): trace.append('convert');point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        routines="ROUTINE value: JOINTPOS BEGIN order=order+'V' RETURN j END value ROUTINE at: INTEGER BEGIN order=order+'I' RETURN 1 END at"
        state=run(START+"order='' points[at()]=value()",decl=DECL+' order: STRING[8] points: ARRAY[1] OF POSITION',routines=routines,context=callback_context(forward=forward))
        self.assertEqual(state['ORDER'],'VI');self.assertEqual(trace,['convert'])

    def test_failure_does_not_evaluate_target_selector(self):
        routines='ROUTINE at: INTEGER BEGIN n=n+1 RETURN 1 END at'
        p,_=compile_program(START+'n=0 points[at()]=j',decl=DECL+' n: INTEGER points: ARRAY[1] OF POSITION',routines=routines,context=model_context())
        p._state.execution.robot.forward=lambda *args:None
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['N'],0)

    def test_structured_fields_and_array_elements_convert_individually(self):
        prefix='TYPE packet = STRUCTURE j: JOINTPOS2 p: POSITION ENDSTRUCTURE'
        p,_=compile_program('items[1].p=items[1].j items[1].j=items[1].p',decl='items: ARRAY[1] OF packet',prefix=prefix,context=model_context((0.,90.)))
        p._state.values['ITEMS'].values[0].values['J']=joint([0.,90.]);state=p.run()
        self.assertEqual(state['ITEMS'][0]['J']['axes'],[0.,90.])

    def test_readonly_position_fields_remain_blocked(self):
        with self.assertRaises(TranslationError): compile_program('p.normal=j',decl=DECL)

    def test_handler_conversion_and_cooperative_execution(self):
        body=START+'CONDITION[1]: WHEN TRUE DO p=j ENDCONDITION ENABLE CONDITION[1] s=1'
        p,_=compile_program(body,decl=DECL,context=model_context((0.,90.)),cooperative=True);state=p.run()
        self.assertAlmostEqual(state['P']['LOCATION']['Y'],100.)

    def test_linked_conversion_uses_calling_root_group(self):
        sources={'main.kl':'PROGRAM MAIN\nVAR x: REAL dummy: XYZWPREXT IN GROUP[2]\nROUTINE point: REAL FROM LIB\nBEGIN x=point() END MAIN',
                 'lib.kl':'PROGRAM LIB\nVAR dummy: XYZWPREXT IN GROUP[1]\nROUTINE point: REAL VAR j: JOINTPOS p: POSITION BEGIN j=CURJPOS(0,0) p=j RETURN p.location.x END point\nBEGIN END LIB'}
        first=model_context((0.,0.)).robot;second=model_context((0.,90.)).robot
        ctx=rt.ExecutionContext(robot=rt.RobotContext(groups={1:first,2:second},active_group=1))
        instance=translate_project(sources).instantiate(context=ctx);self.assertAlmostEqual(instance.run('MAIN')['MAIN']['values']['X'],100.)

    def test_report_records_source_types_locations_and_value_free_requests(self):
        p,result=compile_program(START+'e=j out=e',decl=DECL,context=model_context());p.run()
        rows=result.report['kinematic_assignments'];self.assertEqual(len(rows),2);self.assertEqual(rows[0]['source_type'],('JOINTPOS',9))
        self.assertEqual(rows[1]['target_type'],('JOINTPOS',9));self.assertTrue(all(row['independent_value'] and row['evaluated_once'] for row in rows))
        self.assertTrue(all(set(row)=={'operation','line','outcome'} for row in p.service_requests))

    def test_strict_runtime_cannot_invoke_kinematic_assignment(self):
        p,_=compile_program('',decl=DECL,context=model_context())
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): p._state.kinematic_assignment(('POSITION',),joint([0.]*9),99)

    def test_ordinary_joint_copy_does_not_require_robot_context(self):
        p,_=compile_program('out=j',decl=DECL);p._state.values['J']=joint([1.]*9)
        self.assertEqual(p.run()['OUT']['axes'],[1.]*9);self.assertEqual(p.service_requests,())

    def test_explicit_source_group_must_be_configured(self):
        p,_=compile_program('p=j',decl=DECL+' unused: XYZWPREXT IN GROUP[2]',context=model_context());p._state.values['J']=joint([0.]*9)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'group'): p.run()

    def test_inverse_rejects_current_pose_without_joint_seed(self):
        ctx=model_context();ctx.robot.current=rt.RobotState(position=identity_pose())
        p,_=compile_program('out=p',decl=DECL,context=ctx);p._state.values['P']=identity_pose()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'current joints'): p.run()


if __name__=='__main__': unittest.main()
