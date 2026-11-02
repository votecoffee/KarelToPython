"""Authored explicit offline frame/tool assignment and staged field updates."""
import unittest

from karel2py import runtime as rt,translate_project
from tests.test_extended_services import pose
from tests.test_cartesian_interfaces import value as cartesian_value
from tests.test_system_pose_values import program,context
from tests.test_project_scheduler import source


def execute(body,**options):
    p,r=program(body,**options);v=p.run();return v,p,r


def frame(p,number=2):return p._state.execution.robot.frames[number]
def config(p,number=2):return frame(p,number).values['CONFIG_DATA'].values


class SystemPoseWholeWriteTests(unittest.TestCase):
    def test_numbered_frame_accepts_xyzwpr(self):
        v,p,_=execute('a=$MNUFRAME[1,2] a.x=30 $MNUFRAME[1,2]=a p=$MNUFRAME[1,2]');self.assertEqual((v['P']['LOCATION']['X'],frame(p).values['X']),(30.,30.))
    def test_numbered_tool_accepts_position(self):
        v,p,_=execute('p=$MNUTOOL[1,3] p.location.x=40 $MNUTOOL[1,3]=p q=$MNUTOOL[1,3]');self.assertEqual(v['Q']['LOCATION']['X'],40.);self.assertEqual(p._state.execution.robot.tools[3].spec,('POSITION',))
    def test_active_frame_replaces_selected_row(self):
        v,p,_=execute('a=$MNUFRAME[1,2] a.x=30 $GROUP[1].$UFRAME=a p=$GROUP[1].$UFRAME');self.assertEqual(v['P']['LOCATION']['X'],30.);self.assertEqual(p._state.execution.robot.active_frame,2)
    def test_active_tool_replaces_selected_row(self):
        v,p,_=execute('a=$MNUTOOL[1,3] a.x=40 $GROUP[1].$UTOOL=a p=$GROUP[1].$UTOOL');self.assertEqual(v['P']['LOCATION']['X'],40.)
    def test_numbered_write_can_populate_explicit_row(self):
        v,p,_=execute('a=$MNUFRAME[1,2] $MNUFRAME[1,7]=a p=$MNUFRAME[1,7]');self.assertEqual(v['P']['LOCATION']['X'],12.);self.assertIn(7,p._state.execution.robot.frames)
    def test_whole_write_can_populate_empty_explicit_table(self):
        ctx=context();ctx.robot.tools.clear();_,p,_=execute('a=$MNUFRAME[1,2] $MNUTOOL[1,7]=a',context=ctx);self.assertEqual(p._state.execution.robot.tools[7].values['X'],12.)
    def test_whole_write_can_repair_malformed_previous_row(self):
        ctx=context();ctx.robot.tools[3]=7;_,p,_=execute('a=$MNUFRAME[1,2] $MNUTOOL[1,3]=a',context=ctx);self.assertEqual(p._state.execution.robot.tools[3].values['X'],12.)
    def test_whole_write_preserves_extended_source_axes(self):
        ctx=context();ctx.robot.frames[2]=cartesian_value('XYZWPREXT',(12.,0.,0.),(0.,0.,0.),(7.,8.,9.));_,p,_=execute('e=$MNUFRAME[1,2] e.ext1=7 e.ext2=8 e.ext3=9 $MNUTOOL[1,3]=e',context=ctx);h=p._state.execution.robot.tools[3];self.assertEqual((h.spec,h.values['EXT1'],h.values['EXT3']),(('XYZWPREXT',),7.,9.))
    def test_source_mutation_after_write_does_not_change_table(self):
        _,p,_=execute('a=$MNUFRAME[1,2] $MNUFRAME[1,7]=a a.x=99');self.assertEqual(frame(p,7).values['X'],12.)
    def test_old_read_snapshot_stays_independent(self):
        v,p,_=execute('p=$MNUFRAME[1,2] $MNUFRAME[1,2].location.x=99');self.assertEqual(v['P']['LOCATION']['X'],12.);self.assertEqual(frame(p).values['X'],99.)
    def test_existing_host_row_is_not_mutated_in_place(self):
        ctx=context();old=ctx.robot.frames[2];_,p,_=execute('$MNUFRAME[1,2].location.x=99',context=ctx);self.assertIsNot(frame(p),old);self.assertEqual(old.values['X'],12.)
    def test_row_zero_is_explicitly_writable(self):
        _,p,_=execute('a=$MNUFRAME[1,2] $MNUFRAME[1,0]=a');self.assertEqual(frame(p,0).values['X'],12.)
    def test_maximum_row_number_is_supported(self):
        _,p,_=execute('a=$MNUFRAME[1,2] $MNUFRAME[1,32767]=a');self.assertEqual(frame(p,32767).values['X'],12.)
    def test_grouped_context_changes_only_selected_group(self):
        one=context().robot;two=context().robot;ctx=rt.ExecutionContext(robot=rt.RobotContext(groups={1:one,2:two},active_group=1));execute('a=$MNUFRAME[1,2] a.x=40 $MNUFRAME[2,2]=a',context=ctx);self.assertEqual((one.frames[2].values['X'],two.frames[2].values['X']),(12.,40.))
    def test_handler_action_writes_configured_table(self):
        _,p,_=execute('CONDITION[1]: WHEN TRUE DO $MNUFRAME[1,2].location.x=30 ENDCONDITION ENABLE CONDITION[1] i=0');self.assertEqual(frame(p).values['X'],30.)
    def test_routine_writes_shared_explicit_context(self):
        _,p,_=execute('work',routines='ROUTINE work BEGIN $MNUFRAME[1,2].location.x=30 END work');self.assertEqual(frame(p).values['X'],30.)
    def test_linked_routine_writes_caller_context(self):
        files={'main':source('MAIN','work',routines='ROUTINE work FROM LIB'),'lib':source('LIB','',routines='ROUTINE work BEGIN $MNUFRAME[1,2].location.x=30 END work')};ctx=context();project=translate_project(files).instantiate(context=ctx);project.run('MAIN');self.assertEqual(ctx.robot.frames[2].values['X'],30.)
    def test_label_dispatch_writes_table(self):
        _,p,_=execute('start:: $MNUFRAME[1,2].location.x=30 GOTO done done::');self.assertEqual(frame(p).values['X'],30.)
    def test_cooperative_mode_writes_table(self):
        _,p,_=execute('$MNUFRAME[1,2].location.x=30',cooperative=True);self.assertEqual(frame(p).values['X'],30.)


class SystemPoseFieldWriteTests(unittest.TestCase):
    def test_location_scalar_write(self):
        _,p,_=execute('$MNUFRAME[1,2].location.y=7');self.assertEqual((frame(p).values['X'],frame(p).values['Y']),(12.,7.))
    def test_location_vector_write(self):
        _,p,_=execute('p=$MNUTOOL[1,3] $MNUFRAME[1,2].location=p.location');self.assertEqual(frame(p).values['X'],23.)
    def test_location_vector_write_to_position_row(self):
        ctx=context();ctx.robot.frames[2]=cartesian_value('POSITION',(12.,0.,0.),(0.,0.,0.))
        _,p,_=execute('p=$MNUTOOL[1,3] $MNUFRAME[1,2].location=p.location',context=ctx);self.assertEqual(frame(p).values['LOCATION'].values['X'],23.);self.assertTrue(frame(p).values['NORMAL'].read_only)
    def test_config_whole_write(self):
        _,p,_=execute('p=$MNUFRAME[1,2] p.config_data.cfg_turn_no1=7 $MNUFRAME[1,2].config_data=p.config_data');self.assertEqual(config(p)['CFG_TURN_NO1'],7)
    def test_config_turn_scalar_write(self):
        _,p,_=execute('$MNUFRAME[1,2].config_data.cfg_turn_no2=-8');self.assertEqual(config(p)['CFG_TURN_NO2'],-8)
    def test_config_boolean_scalar_write(self):
        _,p,_=execute('$MNUTOOL[1,3].config_data.cfg_flip=TRUE');self.assertIs(p._state.execution.robot.tools[3].values['CONFIG_DATA'].values['CFG_FLIP'],True)
    def test_field_edit_preserves_extended_axes(self):
        ctx=context();ctx.robot.frames[2]=cartesian_value('XYZWPREXT',(12.,0.,0.),(10.,20.,30.),(7.,8.,9.));_,p,_=execute('$MNUFRAME[1,2].location.x=30',context=ctx);h=frame(p);self.assertEqual((h.values['EXT1'],h.values['EXT2'],h.values['EXT3'],h.values['W']),(7.,8.,9.,10.))
    def test_field_edit_preserves_position_basis(self):
        ctx=context();ctx.robot.frames[2]=cartesian_value('POSITION',(12.,0.,0.),(10.,20.,30.));before=rt.snapshot_value(ctx.robot.frames[2])
        _,p,_=execute('$MNUFRAME[1,2].location.x=30',context=ctx);after=rt.snapshot_value(frame(p));self.assertEqual([after[k] for k in ('NORMAL','ORIENT','APPROACH')],[before[k] for k in ('NORMAL','ORIENT','APPROACH')])
    def test_scalar_integral_value_promotes_to_real(self):
        _,p,_=execute('$GROUP[1].$UFRAME.location.x=7');self.assertIs(type(frame(p).values['X']),float)
    def test_loop_can_write_distinct_frame_rows(self):
        _,p,_=execute('a=$MNUFRAME[1,2] FOR i=4 TO 6 DO $MNUFRAME[1,i]=a ENDFOR');self.assertTrue(all(frame(p,n).values['X']==12. for n in (4,5,6)))


class SystemPoseWriteCaptureTests(unittest.TestCase):
    def test_rhs_then_group_then_row_once(self):
        routines="ROUTINE value:XYZWPR BEGIN trace=trace+'R' RETURN $MNUFRAME[1,2] END value ROUTINE grp:INTEGER BEGIN trace=trace+'G' RETURN 1 END grp ROUTINE row:INTEGER BEGIN trace=trace+'N' RETURN 7 END row"
        v,p,_=execute("trace='' $MNUFRAME[grp,row]=value",routines=routines);self.assertEqual(v['TRACE'],'RGN');self.assertEqual(frame(p,7).values['X'],12.)
    def test_rhs_snapshot_precedes_selector_mutation(self):
        routines='ROUTINE row:INTEGER BEGIN a.x=99 RETURN 7 END row'
        v,p,_=execute('a=$MNUFRAME[1,2] $MNUFRAME[1,row]=a',routines=routines);self.assertEqual((v['A']['X'],frame(p,7).values['X']),(99.,12.))
    def test_selector_effects_remain_when_last_selector_fails(self):
        routines='ROUTINE grp:INTEGER BEGIN n=7 RETURN 1 END grp'
        p,_=program('a=$MNUFRAME[1,2] $MNUFRAME[grp,-1]=a',routines=routines)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],7.);self.assertEqual(frame(p).values['X'],12.)
    def test_rhs_failure_prevents_selector_effects(self):
        routines='ROUTINE grp:INTEGER BEGIN n=7 RETURN 1 END grp'
        p,_=program('$MNUFRAME[grp,7].location.x=n',routines=routines)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(p._state.raw('N'),rt.UNINITIALIZED);self.assertNotIn(7,p._state.execution.robot.frames)
    def test_active_row_is_selected_after_group_effects(self):
        ctx=context();ctx.robot.frames[7]=pose(40)
        routines='ROUTINE grp:INTEGER BEGIN switch RETURN 1 END grp ROUTINE switch FROM HOST'
        # An explicit callback models a supplied selection effect without new source aliases.
        ctx.externals['HOST','SWITCH']=lambda:setattr(ctx.robot,'active_frame',7)
        _,p,_=execute('$GROUP[grp].$UFRAME.location.x=30',routines=routines,context=ctx);self.assertEqual((frame(p).values['X'],frame(p,7).values['X']),(12.,30.))
    def test_observations_contain_no_pose_payload(self):
        _,p,_=execute('$MNUFRAME[1,2].location.x=30');row=p.service_requests[-1];self.assertEqual(row['operation'],'SYSTEM_POSE_WRITE');self.assertEqual(set(row),{'operation','line','outcome'});self.assertEqual(row['outcome'],'completed')
    def test_report_records_path_and_capture_policy(self):
        _,_,r=execute('$MNUFRAME[1,2].location.x=30');row=r.report['system_pose_writes'][0];self.assertEqual(row['path'],('LOCATION','X'));self.assertTrue(row['rhs_before_selectors']);self.assertTrue(row['atomic_table_publication']);self.assertFalse(r.report['system_pose_write_policy']['controller_validated'])
