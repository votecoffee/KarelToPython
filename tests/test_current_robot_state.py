"""Authored current-state queries, explicit model context and program identity."""
import json
from pathlib import Path
import tempfile
import unittest

from karel2py import translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run,pose
from tests.test_project_scheduler import source


def context(x=10,**options): return rt.ExecutionContext(robot=rt.RobotContext(current=rt.RobotState(position=pose(x),**options)))


class RobotSnapshotTests(unittest.TestCase):
    def test_pose_returns_extended_snapshot_and_masks(self):
        ctx=context(axis_limit_mask=3,overtravel_mask=4)
        state=run('p=CURPOS(n,s)',decl='p: XYZWPREXT n,s: INTEGER',context=ctx)
        self.assertEqual((state['P']['X'],state['P']['EXT1'],state['N'],state['S']),(10.,0.,3,4))

    def test_extended_pose_preserves_external_axes(self):
        value=rt.Structure(('XYZWPREXT',));value.values.update(pose(10).values);value.values.update(EXT1=42.,EXT2=7.,EXT3=3.)
        ctx=rt.ExecutionContext(robot=rt.RobotContext(current=rt.RobotState(position=value)))
        state=run('p=CURPOS(0,0)',decl='p: XYZWPREXT',context=ctx)
        self.assertEqual(tuple(state['P'][f'EXT{i}'] for i in (1,2,3)),(42.,7.,3.))

    def test_pose_assignment_can_narrow_to_position(self):
        state=run('p=CURPOS(0,0)',decl='p: POSITION',context=context())
        self.assertEqual(state['P']['LOCATION']['X'],10.)

    def test_literal_zero_discards_each_mask(self):
        state=run('p=CURPOS((0),s)',decl='p: XYZWPREXT s: INTEGER',context=context(overtravel_mask=7))
        self.assertEqual(state['S'],7)

    def test_joint_result_has_nine_slots_with_explicit_padding(self):
        ctx=rt.ExecutionContext(robot=rt.RobotContext(current=rt.RobotState(joints=[10,20],axis_limit_mask=1,overtravel_mask=2)))
        state=run('j=CURJPOS(n,s)',decl='j: JOINTPOS n,s: INTEGER',context=ctx)
        self.assertEqual((state['J']['axes'],state['N'],state['S']),([10.,20.]+[0.]*7,1,2))

    def test_full_nine_axis_snapshot_preserved(self):
        ctx=rt.ExecutionContext(robot=rt.RobotContext(current=rt.RobotState(joints=list(range(9)))))
        self.assertEqual(run('j=CURJPOS(0,0)',decl='j: JOINTPOS',context=ctx)['J']['axes'],list(map(float,range(9))))

    def test_model_derives_pose_from_current_joints(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100},{'a':100}],'current':{'joints':{'type':['JOINTPOS',2],'value':[0.,90.]}}}})
        state=run('p=CURPOS(n,s)',decl='p: XYZWPREXT n,s: INTEGER',context=ctx)
        self.assertAlmostEqual(state['P']['X'],100.);self.assertAlmostEqual(state['P']['Y'],100.)
        self.assertEqual((state['N'],state['S']),(0,0))

    def test_current_pose_math_can_observe_outside_limit_joints(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100,'min':-10,'max':10}],'current':{'joints':{'type':['JOINTPOS',1],'value':[90.]},'axis_limit_mask':1}}})
        state=run('p=CURPOS(n,s)',decl='p: XYZWPREXT n,s: INTEGER',context=ctx)
        self.assertAlmostEqual(state['P']['Y'],100.);self.assertEqual(state['N'],1)
        robot=ctx.robot
        with self.assertRaisesRegex(ValueError,'limits'): robot.model.forward(robot.current.joints,robot.frame(),robot.tool())
        with self.assertRaises(TypeError): robot.model.forward(robot.current.joints,robot.frame(),robot.tool(),check_limits=0)

    def test_model_frame_tool_and_base_are_applied(self):
        from karel2py.storage import typed_value
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100}],'base':typed_value(pose(20)),'frames':{'2':typed_value(pose(10))},'tools':{'3':typed_value(pose(5))},'frame':2,'tool':3,'current':{'joints':{'type':['JOINTPOS',1],'value':[0.]}}}})
        self.assertEqual(run('p=CURPOS(0,0)',decl='p: XYZWPREXT',context=ctx)['P']['X'],115.)

    def test_model_external_joints_are_preserved(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100},{'type':'prismatic','min':0,'max':100}],'external_axes':1,'current':{'joints':{'type':['JOINTPOS',2],'value':[0.,42.]}}}})
        value=run('p=CURPOS(0,0)',decl='p: XYZWPREXT',context=ctx)['P']
        self.assertEqual((value['Z'],value['EXT1']),(42.,42.))

    def test_explicit_pose_takes_precedence_over_model(self):
        from karel2py.storage import typed_value
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100}],'current':{'position':typed_value(pose(7)),'joints':{'type':['JOINTPOS',1],'value':[0.]}}}})
        self.assertEqual(run('p=CURPOS(0,0)',decl='p: XYZWPREXT',context=ctx)['P']['X'],7.)

    def test_missing_service_or_snapshot_preserves_masks(self):
        for ctx in (None,rt.ExecutionContext(robot=rt.RobotContext())):
            with self.subTest(context=ctx):
                p,_=compile_program('n=7 s=8 p=CURPOS(n,s)',decl='p: XYZWPREXT n,s: INTEGER',context=ctx)
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,8))

    def test_pose_without_current_joints_cannot_invent_joint_values(self):
        p,_=compile_program('n=7 s=8 j=CURJPOS(n,s)',decl='j: JOINTPOS n,s: INTEGER',context=context())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'current joints'): p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,8))

    def test_joints_without_model_cannot_invent_pose(self):
        ctx=rt.ExecutionContext(robot=rt.RobotContext(current=rt.RobotState(joints=[10.])))
        p,_=compile_program('n=7 s=8 p=CURPOS(n,s)',decl='p: XYZWPREXT n,s: INTEGER',context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'configured DH'): p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,8))

    def test_returned_pose_and_joint_values_are_detached(self):
        ctx=context(joints=[10.]);run('p=CURPOS(0,0) p.x=99 j=CURJPOS(0,0)',decl='p: XYZWPREXT j: JOINTPOS',context=ctx)
        self.assertEqual(ctx.robot.current.position.values['X'],10.)
        values=ctx.robot.current.joints;values.values[0]=99.;self.assertEqual(ctx.robot.current.joints.values[0],10.)

    def test_host_update_is_visible_to_subsequent_queries(self):
        ctx=context();p,_=compile_program("p=CURPOS(0,0) WRITE('update') q=CURPOS(0,0)",decl='p,q: XYZWPREXT',context=ctx,write=lambda text:ctx.robot.current.update(position=pose(20)))
        state=p.run();self.assertEqual((state['P']['X'],state['Q']['X']),(10.,20.))

    def test_host_state_constructor_copies_inputs(self):
        point=pose(10);joints=[10.,20.];current=rt.RobotState(position=point,joints=joints)
        point.values['X']=99.;joints[0]=99.;self.assertEqual(current.position.values['X'],10.);self.assertEqual(current.joints.values,[10.,20.])

    def test_invalid_update_is_atomic(self):
        current=rt.RobotState(position=pose(10),joints=[10.]);before=current.to_config()
        for changes in ({'position':pose(20),'joints':[True]},{'position':pose(20),'axis_limit_mask':512},{'joints':[float('nan')]},{'position':None,'joints':None}):
            with self.subTest(changes=changes),self.assertRaises((ValueError,rt.KarelRuntimeError)): current.update(**changes)
            self.assertEqual(current.to_config(),before)

    def test_invalid_or_partial_state_rejected(self):
        for values in ({},{'joints':[]},{'joints':[0.]*10},{'joints':rt.JointPosition(('JOINTPOS',2))},{'position':rt.Structure(('XYZWPR',))},{'joints':[0.],'axis_limit_mask':True},{'joints':[0.],'overtravel_mask':-1}):
            with self.subTest(values=values),self.assertRaises((ValueError,rt.KarelRuntimeError)): rt.RobotState(**values)

    def test_mask_alias_rejected_before_context_access(self):
        p,_=compile_program('n=7 p=CURPOS(n,n)',decl='p: XYZWPREXT n: INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): p.run()
        self.assertEqual(p.snapshot()['N'],7)

    def test_mask_types_literals_and_for_counter_guards(self):
        for body in ('p=CURPOS(1,0)','p=CURPOS(FALSE,0)','p=CURPOS(short,0)','FOR n=1 TO 2 DO p=CURPOS(n,0) ENDFOR'):
            with self.subTest(body=body),self.assertRaises(TranslationError): compile_program(body,decl='p: XYZWPREXT n: INTEGER short: SHORT')

    def test_transitive_mask_write_protects_for_counter(self):
        with self.assertRaises(TranslationError):
            compile_program('FOR n=1 TO 2 DO helper() ENDFOR',decl='n: INTEGER p: XYZWPREXT',routines='ROUTINE helper BEGIN p=CURPOS(n,0) END helper')


class CurrentGroupPersistenceTests(unittest.TestCase):
    def groups(self):
        return rt.ExecutionContext(robot=rt.RobotContext(groups={1:rt.RobotContext(current=rt.RobotState(position=pose(10),joints=[10.])),2:rt.RobotContext(current=rt.RobotState(position=pose(20),joints=[20.]))},active_group=2))

    def test_active_and_explicit_groups(self):
        state=run('p=CURPOS(0,0) q=CURPOS(0,0,1) j=CURJPOS(0,0,2)',decl='p,q: XYZWPREXT j: JOINTPOS',context=self.groups())
        self.assertEqual((state['P']['X'],state['Q']['X'],state['J']['axes'][0]),(20.,10.,20.))

    def test_source_group_selects_default_query(self):
        self.assertEqual(run('p=CURPOS(0,0)',decl='p: XYZWPREXT IN GROUP[1]',context=self.groups())['P']['X'],10.)

    def test_linked_queries_follow_callers_group(self):
        ctx=self.groups();instance=translate_project({'a':source('LIB','',routines='ROUTINE sample: XYZWPREXT BEGIN RETURN CURPOS(0,0) END sample'),
            'b':source('MAIN','p=sample()',decl='p: XYZWPREXT IN GROUP[1]',routines='ROUTINE sample: XYZWPREXT FROM LIB')}).instantiate(context=ctx)
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['P']['X'],10.)

    def test_flat_context_rejects_unconfigured_group(self):
        p,_=compile_program('p=CURPOS(0,0,2)',decl='p: XYZWPREXT',context=context())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'group'): p.run()

    def test_grouped_context_rejects_missing_or_nonpositive_group(self):
        for number in (0,3,-1):
            with self.subTest(number=number):
                p,_=compile_program(f'p=CURPOS(0,0,{number})',decl='p: XYZWPREXT',context=self.groups())
                with self.assertRaises(rt.KarelRuntimeError): p.run()

    def test_state_only_context_save_load(self):
        ctx=context(joints=[10.,20.],axis_limit_mask=1)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder,'state.json');ctx.save(path);restored=rt.ExecutionContext.load(path)
        self.assertEqual(restored.to_config(),ctx.to_config())
        self.assertEqual(run('p=CURPOS(n,s)',decl='p: XYZWPREXT n,s: INTEGER',context=restored)['P']['X'],10.)

    def test_grouped_state_updates_survive_persistence(self):
        ctx=self.groups();ctx.robot.groups[2].current.update(position=pose(42),overtravel_mask=3)
        config=ctx.to_config();restored=rt.ExecutionContext.from_config(json.loads(json.dumps(config)))
        self.assertEqual(restored.to_config(),config);self.assertEqual(restored.robot.for_group().current.position.values['X'],42.)

    def test_active_group_change_survives_persistence(self):
        ctx=self.groups();ctx.robot.active_group=1
        restored=rt.ExecutionContext.from_config(ctx.to_config());self.assertEqual(restored.robot.active_group,1)
        self.assertEqual(restored.robot.for_group().current.position.values['X'],10.)

    def test_model_state_updates_replace_initial_configuration(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100}],'current':{'joints':{'type':['JOINTPOS',1],'value':[0.]}}}})
        ctx.robot.current.update(joints=[90.]);restored=rt.ExecutionContext.from_config(ctx.to_config())
        self.assertAlmostEqual(run('p=CURPOS(0,0)',decl='p: XYZWPREXT',context=restored)['P']['Y'],100.)

    def test_legacy_model_config_without_state_stays_identical(self):
        config={'robot':{'groups':{'1':{'dh':[{'a':100}]},'2':{'dh':[{'a':200}]}},'active_group':2}}
        self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)

    def test_callback_only_context_is_not_serialized_as_an_empty_model(self):
        child=rt.RobotContext(forward=lambda *args:None,active_group=2)
        self.assertEqual(rt.ExecutionContext(robot=child).to_config(),{})
        self.assertEqual(rt.ExecutionContext(robot=rt.RobotContext(groups={2:child},active_group=2)).to_config(),{})
        mixed=rt.RobotContext(groups={1:child,2:rt.RobotContext(current=rt.RobotState(joints=[0.]))})
        with self.assertRaises(ValueError): rt.ExecutionContext(robot=mixed).to_config()

    def test_removing_current_state_does_not_restore_stale_snapshot(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100}],'current':{'joints':{'type':['JOINTPOS',1],'value':[0.]}}}})
        ctx.robot.current=None
        self.assertEqual(ctx.to_config(),{'robot':{'dh':[{'a':100}]}})
        ctx=rt.ExecutionContext.from_config({'robot':{'current':{'joints':{'type':['JOINTPOS',1],'value':[0.]}}}})
        ctx.robot.current=None;self.assertEqual(ctx.to_config(),{})

    def test_invalid_state_json_and_mixed_fields(self):
        for config in ({'current':{}},{'current':{'other':1}},{'current':{'joints':{'type':['REAL'],'value':1.}}},{'current':{'joints':{'type':['JOINTPOS',1],'value':[0.]}},'external_axes':1}):
            with self.subTest(config=config),self.assertRaises((ValueError,rt.KarelRuntimeError)): rt.RobotContext.from_config(config)


class CurrentProgramTests(unittest.TestCase):
    def test_bare_and_explicit_forms(self):
        state=run('a=CURR_PROG b=CURR_PROG()',decl='a,b: STRING[12]');self.assertEqual(state,{'A':'T','B':'T'})

    def test_linked_call_reports_executing_library(self):
        instance=translate_project({'a':source('LIB','',routines='ROUTINE module_name: STRING[12] BEGIN RETURN CURR_PROG END module_name'),
            'b':source('MAIN','text=module_name()',decl='text: STRING[12]',routines='ROUTINE module_name: STRING[12] FROM LIB')}).instantiate()
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['TEXT'],'LIB')

    def test_program_result_truncates_to_native_result_capacity(self):
        instance=translate_project({'a':source('LONG_PROGRAM_NAME','text=CURR_PROG',decl='text: STRING[20]')}).instantiate()
        self.assertEqual(instance.run('LONG_PROGRAM_NAME')['LONG_PROGRAM_NAME']['values']['TEXT'],'LONG_PROGRAM')

    def test_global_and_local_storage_retain_precedence(self):
        self.assertEqual(run('CURR_PROG=7 n=CURR_PROG',decl='CURR_PROG,n: INTEGER')['N'],7)
        self.assertEqual(run('n=read_local()',routines='ROUTINE read_local: INTEGER CONST CURR_PROG=7 BEGIN RETURN CURR_PROG END read_local')['N'],7)

    def test_internal_function_retains_precedence(self):
        self.assertEqual(run('n=CURR_PROG',routines='ROUTINE CURR_PROG: INTEGER BEGIN RETURN 7 END CURR_PROG')['N'],7)

    def test_argument_count_rejected(self):
        with self.assertRaises(TranslationError): compile_program('text=CURR_PROG(1)',decl='text: STRING[12]')


if __name__=='__main__': unittest.main()
