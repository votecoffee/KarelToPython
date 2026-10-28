"""Partial storage copies must not relax complete robot/vision input contracts."""
import unittest

from karel2py import runtime as rt
from tests.test_extended_services import compile_program,pose
from tests.test_vision_results import found,batch,context
from tests.test_vt_trays import tray_context


DECL='c:CONFIG frame,p:POSITION j,out:JOINTPOS a:ARRAY[9] OF REAL axes:ARRAY[1] OF REAL i,s:INTEGER'
SETUP="CNV_STR_CONF('N',c,s) frame=POS(0,0,0,0,0,0,c) p=frame axes[1]=99 FOR i=1 TO 9 DO a[i]=1 ENDFOR CNV_REL_JPOS(a,j,s) s=77 "


class PartialServiceBoundaryTests(unittest.TestCase):
    def test_forward_adapter_partial_config_preserves_all_outputs(self):
        returned=pose(7,8,9);partial=rt.Structure(('CONFIG',))
        robot=rt.RobotContext(forward=lambda *args:(returned,partial,[0.]))
        p,_=compile_program(SETUP+'JOINT2POS(j,frame,frame,0,p,c,axes,s)',decl=DECL,
                            context=rt.ExecutionContext(robot=robot),joint_axes=9)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        values=p.snapshot()
        self.assertEqual(values['P']['LOCATION']['X'],0.)
        self.assertEqual(values['C'],rt.snapshot_value(returned.values['CONFIG_DATA']))
        self.assertEqual((values['AXES'],values['S']),([99.],77))

    def test_inverse_adapter_partial_joints_preserve_target_and_status(self):
        returned=rt.JointPosition(('JOINTPOS',9));returned.values[0]=2.
        robot=rt.RobotContext(inverse=lambda *args:returned)
        body=SETUP+'out=j POS2JOINT(j,p,frame,frame,0,c,axes,out,s)'
        p,_=compile_program(body,decl=DECL,context=rt.ExecutionContext(robot=robot),joint_axes=9)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        values=p.snapshot();self.assertEqual(values['OUT'],values['J'])
        self.assertEqual((values['AXES'],values['S']),([99.],77))

    def test_supplied_vision_offset_still_requires_complete_pose(self):
        row=found();partial=rt.Structure(('XYZWPR',));partial.values['X']=1.
        row['offset']=partial
        with self.assertRaisesRegex(ValueError,'complete XYZWPR'):context(batch(row))

    def test_supplied_vision_view_still_requires_complete_pose(self):
        row=found();partial=rt.Structure(('XYZWPR',));partial.values['Y']=1.
        row['views']['1']['position']=partial
        with self.assertRaisesRegex(ValueError,'complete XYZWPR'):context(batch(row))

    def test_supplied_tray_cell_still_requires_complete_transform(self):
        partial=rt.Structure(('XYZWPR',));partial.values['X']=1.
        with self.assertRaisesRegex(ValueError,'complete XYZWPR'):
            tray_context(cells=[{'offset':partial}])

    def test_tp_position_store_still_rejects_partial_joints(self):
        partial=rt.JointPosition(('JOINTPOS',3));partial.values[0]=1.
        with self.assertRaises(rt.KarelRuntimeError):
            rt.TeachPrograms({'DEMO':{'positions':[{'number':1,'group':1,'value':partial}]}})


if __name__=='__main__':unittest.main()
