"""Authored frame/tool-only contexts, explicit selections and exact JSON replay."""
from copy import deepcopy
import json
import unittest

from karel2py import runtime as rt
from karel2py.storage import typed_value
from tests.test_extended_services import pose
from tests.test_system_pose_values import run,context


def config():return dict(robot=dict(frames={'0':typed_value(pose(0)),'2':typed_value(pose(12))},tools={'3':typed_value(pose(23))},frame=2,tool=3))

def restore(data):return rt.ExecutionContext.from_config(json.loads(json.dumps(data)))


class FrameTableContextTests(unittest.TestCase):
    def test_table_only_context_needs_no_model(self):
        ctx=restore(config());v,_,_=run('p=$MNUFRAME[1,2] q=$GROUP[1].$UTOOL',context=ctx);self.assertEqual((v['P']['LOCATION']['X'],v['Q']['LOCATION']['X']),(12.,23.));self.assertIsNone(ctx.robot.model)
    def test_config_roundtrip_is_exact(self):
        data=config();ctx=restore(data);self.assertEqual(ctx.to_config()['robot'],data['robot']);self.assertEqual(restore(ctx.to_config()).to_config(),ctx.to_config())
    def test_host_tables_are_persisted(self):
        ctx=context();data=ctx.to_config();self.assertIn('frames',data['robot']);self.assertIsNone(restore(data).robot.model);self.assertEqual(restore(data).robot.frame(2).values['X'],12.)
    def test_explicit_identity_zero_is_retained(self):
        ctx=rt.ExecutionContext(robot=rt.RobotContext(frames={0:pose(0)}));data=ctx.to_config();self.assertIn('0',data['robot']['frames']);self.assertEqual(restore(data).robot.frame(0).values['X'],0.)
    def test_missing_identity_is_not_invented(self):
        data=dict(robot=dict(frames={'2':typed_value(pose(12))}));ctx=restore(data);self.assertEqual(set(ctx.robot.frames),{2});self.assertEqual(ctx.to_config()['robot'],data['robot']);self.assertFalse(ctx.robot.tools)
        v,_,_=run('p=$MNUFRAME[1,2]',context=ctx);self.assertEqual(v['P']['LOCATION']['X'],12.)
        with self.assertRaises(rt.KarelRuntimeError):ctx.robot.frame(0)
    def test_missing_tool_table_is_not_invented(self):
        ctx=restore(dict(robot=dict(frames={'0':typed_value(pose(0))})));self.assertNotIn('tools',ctx.to_config()['robot'])
        with self.assertRaises(rt.KarelRuntimeError):ctx.robot.tool(0)
    def test_empty_tables_alone_are_not_robot_context(self):
        with self.assertRaises(ValueError):restore(dict(robot=dict(frames={},tools={})))
    def test_limits_and_tables_can_coexist(self):
        data=config();data['robot']['joint_limits']=[[-5,5],[-10,10]];ctx=restore(data);self.assertEqual(ctx.robot.joint_limits,([-5,5],[-10,10]));self.assertEqual(ctx.to_config()['robot'],data['robot'])
    def test_current_state_and_tables_can_coexist(self):
        data=config();data['robot']['current']={'joints':typed_value(rt.RobotState(joints=[1,2]).joints)};ctx=restore(data);self.assertEqual(ctx.robot.current.joints.values,[1.,2.]);self.assertEqual(restore(ctx.to_config()).robot.frame(2).values['X'],12.)
    def test_grouped_table_only_context_roundtrip(self):
        raw=config()['robot'];data=dict(robot=dict(groups={'1':raw,'2':deepcopy(raw)},active_group=2));ctx=restore(data);self.assertEqual(ctx.to_config()['robot'],data['robot']);self.assertEqual(restore(ctx.to_config()).robot.for_group(2).tool(3).values['X'],23.)
    def test_changed_table_values_and_selection_survive(self):
        ctx=restore(config());ctx.robot.frames[2]=pose(42);ctx.robot.active_frame=0;again=restore(ctx.to_config());self.assertEqual((again.robot.frame(2).values['X'],again.robot.active_frame),(42.,0))
    def test_callbacks_are_not_invented_on_restore(self):
        ctx=context();ctx.robot.forward=lambda *args:None;again=restore(ctx.to_config());self.assertIsNone(again.robot.forward);self.assertIsNone(again.robot.inverse);self.assertIsNone(again.robot.reachable)
    def test_tables_require_objects(self):
        for rows in (None,[],1):
            data=config();data['robot']['frames']=rows
            with self.subTest(rows=rows),self.assertRaises(ValueError):restore(data)
    def test_table_keys_require_canonical_bounded_ids(self):
        for key in ('01','-1','32768','+1','1.0','100000','one'):
            with self.subTest(key=key),self.assertRaises(ValueError):restore(dict(robot=dict(frames={key:typed_value(pose(0))})))
    def test_explicit_selection_requires_supplied_row(self):
        for selected in (1,True,1.5,-1,32768):
            data=config();data['robot']['frame']=selected
            with self.subTest(selected=selected),self.assertRaises(ValueError):restore(data)
    def test_selection_without_table_is_rejected(self):
        with self.assertRaises(ValueError):restore(dict(robot=dict(current={'joints':typed_value(rt.RobotState(joints=[0,0]).joints)},frame=0)))
    def test_non_cartesian_table_data_is_rejected(self):
        for value in (rt.JointPosition(('JOINTPOS',2)),rt.Structure(('VECTOR',))):
            with self.subTest(kind=value.spec[0]),self.assertRaises(ValueError):restore(dict(robot=dict(frames={'0':typed_value(value)})))
    def test_partial_cartesian_table_data_is_rejected(self):
        value=pose(0);value.values['Y']=rt.UNINITIALIZED
        with self.assertRaises((ValueError,rt.KarelRuntimeError)):restore(dict(robot=dict(frames={'0':typed_value(value)})))
    def test_model_settings_without_dh_are_not_ignored(self):
        for key,value in (('iterations',20),('external_axes',1),('position_tolerance',.1)):
            data=config();data['robot'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):restore(data)
