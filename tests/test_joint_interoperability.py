"""Authored padded-joint, frame/tool coherence and grouped-model checks."""
import json
from pathlib import Path
import tempfile
import unittest

from karel2py import translate_project,runtime as rt
from karel2py.kinematics import SerialRobotModel,pose as identity_pose
from karel2py.storage import typed_value
from tests.test_extended_services import compile_program,run,pose
from tests.test_project_scheduler import source


def joint(values):
    result=rt.JointPosition(('JOINTPOS',len(values)));result.values[:]=values;return result


def model_context(values=(30.,45.),**fields):
    return rt.ExecutionContext.from_config({'robot':dict(dh=[{'a':100},{'a':100}],current={'joints':typed_value(joint(list(values)))},**fields)})


FRAME="CNV_STR_CONF('N',c,s) f=POS(0,0,0,0,0,0,c) "
DECL='j,out: JOINTPOS f,p: POSITION c: CONFIG ext: ARRAY[3] OF REAL s: INTEGER'
FORWARD='j=CURJPOS(0,0) JOINT2POS(j,f,f,0,p,c,ext,s) '
INVERSE='POS2JOINT(j,p,f,f,0,c,ext,out,s)'


class PaddedJointTests(unittest.TestCase):
    def test_current_joint_value_runs_forward_and_inverse(self):
        ctx=model_context();state=run(FRAME+FORWARD+INVERSE,decl=DECL,context=ctx)
        self.assertEqual(state['S'],0)
        self.assertEqual(state['OUT']['axes'],[30.,45.]+[0.]*7)
        self.assertEqual(ctx.robot.current.joints.values,[30.,45.])

    def test_inverse_can_write_native_model_width(self):
        state=run(FRAME+FORWARD+INVERSE,decl=DECL.replace('j,out: JOINTPOS','j: JOINTPOS out: JOINTPOS2'),context=model_context())
        self.assertEqual(state['OUT']['axes'],[30.,45.])

    def test_inverse_can_use_native_reference_and_padded_output(self):
        p,_=compile_program(FRAME+'JOINT2POS(j,f,f,0,p,c,ext,s) '+INVERSE,decl=DECL.replace('j,out: JOINTPOS','j: JOINTPOS2 out: JOINTPOS'),context=model_context())
        p._state.values['J']=joint([30.,45.]);state=p.run()
        self.assertEqual(state['OUT']['axes'],[30.,45.]+[0.]*7)
        model=model_context().robot.model;cfg=identity_pose().values['CONFIG_DATA'];axes=rt.Array(('ARRAY',3,('REAL',)));axes.values[:]=[0.,0.,0.]
        point=model.forward(joint([30.,45.]),identity_pose(),identity_pose())[0]
        result=model.inverse(joint([30.,45.]),point,identity_pose(),identity_pose(),0,cfg,axes)
        self.assertEqual(result.spec,('JOINTPOS',2))

    def test_padded_values_reject_nonzero_unused_axes(self):
        value=joint([30.,45.,1.]+[0.]*6)
        model=model_context().robot.model
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Unused'): model.forward(value,identity_pose(),identity_pose())

    def test_other_width_is_not_treated_as_padding(self):
        model=model_context().robot.model
        with self.assertRaisesRegex(rt.KarelRuntimeError,'width'): model.forward(joint([0.,0.,0.]),identity_pose(),identity_pose())

    def test_model_width_nine_keeps_all_nine_values(self):
        model=SerialRobotModel([{'a':1}]*9);value=joint([0.]*8+[90.])
        self.assertEqual(rt.joint_values(value,9),[0.]*8+[90.])
        self.assertAlmostEqual(model.forward(value,identity_pose(),identity_pose())[0].values['LOCATION'].values['Y'],1.)

    def test_malformed_or_partial_joint_value_rejected(self):
        malformed=joint([0.]*9);malformed.values.pop()
        for value in (malformed,joint([0.]*8+[rt.UNINITIALIZED]),joint([0.]*8+[float('nan')]),joint([0.]*8+[True])):
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError): rt.joint_values(value,2)

    def test_helper_accepts_ordinary_pythonic_decimals_and_copies(self):
        value=joint([.1,.2]);padded=rt.padded_joints(value);padded.values[0]=9.
        self.assertEqual(value.values,[.1,.2]);self.assertEqual(rt.joint_values(rt.padded_joints(value),2),[.1,.2])

    def test_forward_failure_preserves_outputs_and_status(self):
        bank=rt.PositionRegisters(1,{1:joint([0.,0.,1.]+[0.]*6)})
        ctx=model_context();ctx.positions=bank
        p,_=compile_program(FRAME+"p=f ext[1]=7 ext[2]=8 ext[3]=9 s=99 j=GET_JPOS_REG(1,s) s=99 JOINT2POS(j,f,f,0,p,c,ext,s)",decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Unused'): p.run()
        self.assertEqual((p.snapshot()['EXT'],p.snapshot()['S']),([7.,8.,9.],99));self.assertEqual(p.snapshot()['P']['LOCATION']['X'],0.)

    def test_inverse_wrong_output_width_preserves_output(self):
        p,_=compile_program(FRAME+FORWARD+'s=99 '+INVERSE,decl=DECL.replace('j,out: JOINTPOS','j: JOINTPOS out: JOINTPOS3'),context=model_context())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'output'): p.run()
        self.assertEqual(p.snapshot()['S'],99);self.assertTrue(all(value=={'uninitialized':True} for value in p.snapshot()['OUT']['axes']))

    def test_position_register_getter_pads_all_narrow_widths(self):
        for width in range(1,10):
            with self.subTest(width=width):
                stored=joint([float(i) for i in range(width)]);bank=rt.PositionRegisters(1,{1:stored})
                state=run('j=GET_JPOS_REG(1,s)',decl='j: JOINTPOS s: INTEGER',context=rt.ExecutionContext(positions=bank))
                self.assertEqual(state['J']['axes'],stored.values+[0.]*(9-width));self.assertEqual(state['S'],0)
                self.assertEqual(bank.read(1)[1].spec,('JOINTPOS',width))

    def test_register_current_model_and_range_share_values(self):
        ctx=model_context();ctx.positions=rt.PositionRegisters(1,{1:joint([30.,45.])})
        state=run(FRAME+'j=GET_JPOS_REG(1,s) ready=J_IN_RANGE(j) JOINT2POS(j,f,f,0,p,c,ext,s)',decl=DECL+' ready: BOOLEAN',context=ctx)
        self.assertTrue(state['READY']);self.assertEqual(state['S'],0)

    def test_model_pose_can_use_padded_current_snapshot(self):
        ctx=model_context();ctx.robot.current.update(joints=rt.padded_joints(ctx.robot.current.joints))
        state=run('point=CURPOS(0,0)',decl='point: XYZWPREXT',context=ctx)
        expected=ctx.robot.model.chain([30.,45.]);self.assertAlmostEqual(state['POINT']['X'],expected[0][3])

    def test_external_joints_roundtrip_with_padded_reference(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100},{'type':'prismatic','min':0,'max':100}],'external_axes':1,'current':{'joints':typed_value(joint([0.,42.]))}}})
        state=run(FRAME+FORWARD+INVERSE,decl=DECL,context=ctx)
        self.assertEqual((state['OUT']['axes'],state['EXT']),([0.,42.]+[0.]*7,[42.,0.,0.]))

    def test_custom_inverse_adapter_keeps_exact_output_contract(self):
        calls=[]
        def inverse(*args): calls.append(1);return joint([0.,0.])
        ctx=rt.ExecutionContext(robot=rt.RobotContext(inverse=inverse))
        p,_=compile_program(FRAME+'j=j ext[1]=0 ext[2]=0 ext[3]=0 '+INVERSE,decl=DECL,context=ctx)
        # Supply a complete reference without making a model available.
        p._state.values['J']=joint([0.]*9);p._state.values['P']=identity_pose()
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(calls,[1])


class PaddedRangeTests(unittest.TestCase):
    def test_current_snapshot_range_uses_explicit_active_axes(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'joint_limits':[[-5,5],[-5,5]],'current':{'joints':typed_value(joint([0.,4.]))}}})
        self.assertTrue(run('ready=J_IN_RANGE(CURJPOS(0,0))',decl='ready: BOOLEAN',context=ctx)['READY'])
        ctx.robot.current.update(joints=[0.,8.]);self.assertFalse(run('ready=J_IN_RANGE(CURJPOS(0,0))',decl='ready: BOOLEAN',context=ctx)['READY'])

    def test_limits_only_context_can_roundtrip_without_state(self):
        config={'robot':{'joint_limits':[[-5,5],[-10,10]]}}
        ctx=rt.ExecutionContext.from_config(config);self.assertEqual(ctx.to_config(),config)
        ctx.positions=rt.PositionRegisters(1,{1:joint([0.,4.])})
        self.assertTrue(run('j=GET_JPOS_REG(1,s) ready=J_IN_RANGE(j)',decl='j: JOINTPOS ready: BOOLEAN s: INTEGER',context=ctx)['READY'])

    def test_nonzero_padding_is_an_error_rather_than_a_range_result(self):
        ctx=rt.ExecutionContext(robot=rt.RobotContext(joint_limits=[(-5,5)]));ctx.positions=rt.PositionRegisters(1,{1:joint([0.,1.]+[0.]*7)})
        p,_=compile_program('ready=TRUE j=GET_JPOS_REG(1,s) ready=J_IN_RANGE(j)',decl='j: JOINTPOS ready: BOOLEAN s: INTEGER',context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Unused'): p.run()
        self.assertTrue(p.snapshot()['READY'])

    def test_invalid_limits_and_conflicting_model_fields(self):
        for limits in ([],[(0,1)]*10,[(1,0)],[(True,1)],[(0,float('nan'))]):
            with self.subTest(limits=limits),self.assertRaises((ValueError,TypeError)): rt.RobotContext(joint_limits=limits)
        with self.assertRaises(ValueError): rt.RobotContext.from_config({'dh':[{'a':1}],'joint_limits':[[0,1]]})
        for limits in (None,True,{}):
            with self.subTest(limits=limits),self.assertRaises(ValueError): rt.RobotContext.from_config({'joint_limits':limits})

    def test_range_context_persistence_retains_current_and_limits(self):
        ctx=rt.ExecutionContext(robot=rt.RobotContext(joint_limits=[(-5,5)],current=rt.RobotState(joints=[4.])))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder,'state.json');ctx.save(path);restored=rt.ExecutionContext.load(path)
        self.assertEqual(restored.to_config(),ctx.to_config());self.assertEqual(restored.robot.joint_limits,([-5,5],))


class FrameToolCoherenceTests(unittest.TestCase):
    def context(self):
        return rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100,'min':0,'max':0}],'current':{'joints':typed_value(joint([0.]))}}})

    def test_frame_change_updates_current_pose_and_reachability(self):
        ctx=self.context();ctx.robot.frames[2]=pose(50);ctx.robot.active_frame=2
        state=run('p=CURPOS(0,0) ready=IN_RANGE(p)',decl='p: XYZWPREXT ready: BOOLEAN',context=ctx)
        self.assertEqual(state['P']['X'],50.);self.assertTrue(state['READY'])

    def test_tool_change_updates_current_pose_and_reachability(self):
        ctx=self.context();ctx.robot.tools[3]=pose(20);ctx.robot.active_tool=3
        state=run('p=CURPOS(0,0) ready=IN_RANGE(p)',decl='p: XYZWPREXT ready: BOOLEAN',context=ctx)
        self.assertEqual(state['P']['X'],120.);self.assertTrue(state['READY'])

    def test_replacing_existing_frame_updates_reachability(self):
        ctx=self.context();ctx.robot.frames[0]=pose(50)
        self.assertTrue(run('p=CURPOS(0,0) ready=IN_RANGE(p)',decl='p: XYZWPREXT ready: BOOLEAN',context=ctx)['READY'])

    def test_updated_frames_tools_and_selection_persist(self):
        ctx=self.context();ctx.robot.frames[2]=pose(50);ctx.robot.tools[3]=pose(20);ctx.robot.active_frame=2;ctx.robot.active_tool=3
        config=ctx.to_config();restored=rt.ExecutionContext.from_config(json.loads(json.dumps(config)))
        self.assertEqual(restored.to_config(),config)
        state=run('p=CURPOS(0,0) ready=IN_RANGE(p)',decl='p: XYZWPREXT ready: BOOLEAN',context=restored)
        self.assertEqual(state['P']['X'],70.);self.assertTrue(state['READY'])

    def test_legacy_omitted_identity_entries_remain_omitted(self):
        config={'robot':{'dh':[{'a':100}]}}
        self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)

    def test_legacy_explicit_typed_entries_keep_input_representation(self):
        value=typed_value(pose(50));config={'robot':{'dh':[{'a':100}],'frames':{'2':value},'frame':2}}
        self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)

    def test_removed_frame_is_not_resurrected(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100}],'frames':{'2':typed_value(pose(50))},'frame':2}})
        ctx.robot.active_frame=0;del ctx.robot.frames[2]
        restored=rt.ExecutionContext.from_config(ctx.to_config());self.assertNotIn(2,restored.robot.frames)

    def test_invalid_selection_fails_queries_without_overwriting_target(self):
        ctx=self.context();ctx.robot.active_frame=True
        p,_=compile_program('ready=TRUE ready=IN_RANGE(CURPOS(0,0))',decl='ready: BOOLEAN',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertTrue(p.snapshot()['READY'])

    def test_invalid_frame_cannot_replace_saved_file(self):
        ctx=self.context();ctx.robot.frames[2]=rt.Structure(('POSITION',));ctx.robot.active_frame=2
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder,'state.json');path.write_text('before',encoding='utf-8')
            with self.assertRaises(rt.KarelRuntimeError): ctx.save(path)
            self.assertEqual(path.read_text(),'before')

    def test_invalid_inactive_frame_identifiers_rejected_on_load(self):
        for key in ('-1','32768'):
            with self.subTest(key=key),self.assertRaises(rt.KarelRuntimeError):
                rt.RobotContext.from_config({'dh':[{'a':100}],'frames':{key:typed_value(pose())}})


class LinkedModelGroupTests(unittest.TestCase):
    def context(self):
        return rt.ExecutionContext.from_config({'robot':{'groups':{'1':{'dh':[{'a':100,'min':0,'max':0}],'current':{'joints':typed_value(joint([0.]))}},'2':{'dh':[{'a':200,'min':90,'max':90}],'current':{'joints':typed_value(joint([90.]))}}},'active_group':2}})

    def test_linked_joint_conversion_and_current_query_use_one_group(self):
        routine='ROUTINE sample: REAL VAR j: JOINTPOS f,p: POSITION c: CONFIG ext: ARRAY[3] OF REAL s: INTEGER BEGIN '+FRAME+FORWARD+' RETURN p.location.x END sample'
        instance=translate_project({'a':source('LIB','',routines=routine),'b':source('MAIN','x=sample()',decl='x: REAL p: XYZWPREXT IN GROUP[1]',routines='ROUTINE sample: REAL FROM LIB')}).instantiate(context=self.context())
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['X'],100.)

    def test_linked_joint_range_uses_callers_limits(self):
        routine='ROUTINE ready: BOOLEAN BEGIN RETURN J_IN_RANGE(CURJPOS(0,0)) END ready'
        instance=translate_project({'a':source('LIB','',routines=routine),'b':source('MAIN','ok=ready()',decl='ok: BOOLEAN p: XYZWPREXT IN GROUP[1]',routines='ROUTINE ready: BOOLEAN FROM LIB')}).instantiate(context=self.context())
        self.assertTrue(instance.run('MAIN')['MAIN']['values']['OK'])

    def test_linked_cartesian_range_uses_callers_model(self):
        routine='ROUTINE ready: BOOLEAN BEGIN RETURN IN_RANGE(CURPOS(0,0)) END ready'
        instance=translate_project({'a':source('LIB','',routines=routine),'b':source('MAIN','ok=ready()',decl='ok: BOOLEAN p: XYZWPREXT IN GROUP[1]',routines='ROUTINE ready: BOOLEAN FROM LIB')}).instantiate(context=self.context())
        self.assertTrue(instance.run('MAIN')['MAIN']['values']['OK'])


if __name__=='__main__': unittest.main()
