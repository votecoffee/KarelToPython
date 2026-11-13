"""Authored joint-to-system-pose writes, context, capture and failure guards."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.kinematics import pose
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_joint_interoperability import joint
from tests.test_project_scheduler import source


def context():
    return rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100},{'a':100}]}})


def callback_context(callback):
    return rt.ExecutionContext(robot=rt.RobotContext(forward=callback,
        frames={0:pose()},tools={0:pose()}))


def program(body,*,ctx=None,decl='j:JOINTPOS2 n:INTEGER trace:STRING[32]',**options):
    value,result=compile_program(body,decl=decl,context=ctx if ctx is not None else context(),**options)
    if 'J' in value._state.values:value._state.values['J']=joint([0.,0.])
    value._state.values.update(N=0,TRACE='')
    return value,result


def row(ctx,kind='frame',number=7):return (ctx.robot.frames if kind=='frame' else ctx.robot.tools)[number]


class SystemJointValueTests(unittest.TestCase):
    def test_all_four_forms_in_both_execution_modes(self):
        cases=(('$MNUFRAME[1,7]','frame',7),('$MNUTOOL[1,8]','tool',8),
               ('$GROUP[1].$UFRAME','frame',0),('$GROUP[1].$UTOOL','tool',0))
        for target,kind,number in cases:
            for cooperative in (False,True):
                with self.subTest(target=target,cooperative=cooperative):
                    ctx=context();p,_=program(target+'=j',ctx=ctx,cooperative=cooperative)
                    old=(ctx.robot.frames if kind=='frame' else ctx.robot.tools).get(number)
                    p.run();value=row(ctx,kind,number)
                    self.assertEqual(value.spec,('XYZWPREXT',))
                    self.assertEqual([value.values[name] for name in ('X','Y','Z','EXT1','EXT2','EXT3')],
                                     [200.,0.,0.,0.,0.,0.])
                    self.assertIsNot(value,old)
                    self.assertEqual((ctx.robot.active_frame,ctx.robot.active_tool),(0,0))
                    self.assertIsNone(ctx.robot.current)

    def test_configured_frames_and_tools_are_used_for_conversion(self):
        ctx=context();ctx.robot.frames[2]=pose();ctx.robot.frames[2].values['LOCATION'].values['X']=10.
        ctx.robot.tools[3]=pose();ctx.robot.tools[3].values['LOCATION'].values['X']=5.
        ctx.robot.active_frame=2;ctx.robot.active_tool=3
        p,_=program('$MNUFRAME[1,7]=j',ctx=ctx);p.run()
        self.assertEqual(row(ctx).values['X'],195.)
        self.assertEqual((ctx.robot.active_frame,ctx.robot.active_tool),(2,3))

    def test_external_axes_and_config_from_the_adapter_are_retained(self):
        point=pose();point.values['LOCATION'].values['X']=42.;config=point.values['CONFIG_DATA'].clone()
        config.values['CFG_FLIP']=True
        ctx=callback_context(lambda *_:(point,config,[7.,8.,9.]))
        p,_=program('$MNUTOOL[1,7]=j j[1]=90',ctx=ctx);p.run()
        value=row(ctx,'tool')
        self.assertEqual([value.values[name] for name in ('X','EXT1','EXT2','EXT3')],[42.,7.,8.,9.])
        self.assertTrue(value.values['CONFIG_DATA'].values['CFG_FLIP'])
        point.values['LOCATION'].values['X']=99.;config.values['CFG_FLIP']=False
        self.assertEqual(value.values['X'],42.)
        self.assertTrue(value.values['CONFIG_DATA'].values['CFG_FLIP'])

    def test_mapped_external_joint_metadata_survives_source_write(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'type':'prismatic'},
            {'a':100},{'type':'prismatic'}],'external_axis_indices':[3,1]}})
        p,_=program('$MNUFRAME[1,7]=j',ctx=ctx,decl='j:JOINTPOS3')
        p._state.values['J']=joint([17.,0.,31.]);p.run()
        self.assertEqual([row(ctx).values[name] for name in ('X','Z','EXT1','EXT2','EXT3')],
                         [100.,48.,31.,17.,0.])

    def test_padded_joint_values_and_array_elements_work(self):
        for width in (2,9):
            with self.subTest(width=width):
                p,_=program('$MNUFRAME[1,7]=bank[1]',decl=f'bank:ARRAY[1]OF JOINTPOS{width}')
                p._state.values['BANK'].values[0]=joint([0.]*width);p.run()
                self.assertEqual(row(p._state.execution).values['X'],200.)

    def test_caller_group_controls_conversion_not_destination_group(self):
        one=context().robot;two=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':30},{'a':40}]}}).robot
        ctx=rt.ExecutionContext(robot=rt.RobotContext(groups={1:one,2:two},active_group=1))
        p,_=program('$MNUFRAME[1,7]=j',ctx=ctx,decl='j:JOINTPOS2 IN GROUP[2]')
        p.run();self.assertEqual(one.frames[7].values['X'],70.)
        self.assertEqual((ctx.robot.active_group,p._state.robot_group),(1,2))
        self.assertNotIn(7,two.frames)

    def test_linked_routine_uses_the_calling_root_group(self):
        one=context().robot;two=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':30},{'a':40}]}}).robot
        ctx=rt.ExecutionContext(robot=rt.RobotContext(groups={1:one,2:two},active_group=1))
        files={'main':source('MAIN','j[1]=0 j[2]=0 store(j)',decl='j:JOINTPOS2 IN GROUP[2]',
                            routines='ROUTINE store(j:JOINTPOS2) FROM LIB'),
               'lib':source('LIB','',routines='ROUTINE store(j:JOINTPOS2) BEGIN $MNUTOOL[1,7]=j END store')}
        project=translate_project(files).instantiate(context=ctx);project.run('MAIN')
        self.assertEqual(one.tools[7].values['X'],70.)
        self.assertNotIn(7,two.tools)

    def test_handler_and_label_dispatch_use_the_same_conversion(self):
        bodies=('CONDITION[1]: WHEN TRUE DO $MNUFRAME[1,7]=j ENDCONDITION ENABLE CONDITION[1] n=1',
                'GOTO store n=99 store:: $MNUFRAME[1,7]=j')
        for body in bodies:
            with self.subTest(body=body):
                p,_=program(body);p.run();self.assertEqual(row(p._state.execution).values['X'],200.)

    def test_saved_model_rows_roundtrip_and_remain_independent(self):
        ctx=context();p,_=program('$MNUFRAME[1,7]=j',ctx=ctx);p.run()
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved)
        restored.robot.frames[7].values['X']=9.
        self.assertEqual(row(ctx).values['X'],200.)

    def test_later_conversion_uses_the_updated_active_frame(self):
        ctx=context();p,_=program('$GROUP[1].$UFRAME=j $MNUFRAME[1,7]=j',ctx=ctx);p.run()
        self.assertEqual(ctx.robot.frames[0].values['X'],200.)
        self.assertEqual(row(ctx).values['X'],0.)

    def test_numbered_joint_write_can_repair_a_malformed_old_row(self):
        ctx=context();ctx.robot.frames[7]=9
        p,_=program('$MNUFRAME[1,7]=j',ctx=ctx);p.run()
        self.assertEqual(row(ctx).values['X'],200.)

    def test_reports_keep_source_and_stored_types_and_value_free_events(self):
        p,result=program('$MNUFRAME[1,7]=j');p.run()
        item=result.report['system_pose_writes'][0]
        self.assertEqual((item['source_type'],item['stored_type']),(('JOINTPOS',2),('XYZWPREXT',)))
        self.assertTrue(item['kinematic_conversion']);self.assertTrue(item['rhs_before_selectors'])
        self.assertEqual(result.report['kinematic_assignments'][0]['target_kind'],'system_pose')
        self.assertEqual([(value['operation'],value['outcome']) for value in p.service_requests],
                         [('KINEMATIC_ASSIGNMENT','completed'),('SYSTEM_POSE_WRITE','completed')])
        self.assertTrue(all(set(value)=={'operation','line','outcome'} for value in p.service_requests))


class SystemJointCaptureTests(unittest.TestCase):
    def test_rhs_conversion_then_selectors_once_with_independent_inputs_and_result(self):
        point=pose();point.values['LOCATION'].values['X']=42.;holder={}
        def forward(joints,frame,tool,selector):
            owner=holder['p']._state.values;owner['TRACE']+='F';joints.values[0]=99.
            return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        ctx=callback_context(forward)
        routines="ROUTINE value:JOINTPOS2 BEGIN trace=trace+'R' RETURN j END value "
        routines+="ROUTINE grp:INTEGER BEGIN trace=trace+'G' j[1]=90 RETURN 1 END grp "
        routines+="ROUTINE row:INTEGER BEGIN trace=trace+'N' change RETURN 7 END row ROUTINE change FROM HOST"
        ctx.externals['HOST','CHANGE']=lambda:point.values['LOCATION'].values.__setitem__('X',999.)
        p,_=program('$MNUFRAME[grp,row]=value',ctx=ctx,routines=routines);holder['p']=p
        data=p.run();self.assertEqual(data['TRACE'],'RFGN')
        self.assertEqual(data['J']['axes'],[90.,0.]);self.assertEqual(row(ctx).values['X'],42.)

    def test_conversion_failure_prevents_all_selector_effects(self):
        def forward(*args):raise ValueError('authored failure')
        ctx=callback_context(forward);old=ctx.robot.frames[0]
        p,_=program('$MNUFRAME[grp,7]=j',ctx=ctx,routines='ROUTINE grp:INTEGER BEGIN n=1 RETURN 1 END grp')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'authored failure'):p.run()
        self.assertEqual(p.snapshot()['N'],0);self.assertIs(ctx.robot.frames[0],old);self.assertNotIn(7,ctx.robot.frames)
        self.assertEqual([(value['operation'],value['outcome']) for value in p.service_requests],
                         [('KINEMATIC_ASSIGNMENT','failed')])

    def test_failed_selector_keeps_completed_callback_effects_and_old_table(self):
        calls=[];point=pose()
        def forward(*args):calls.append(1);return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        ctx=callback_context(forward);old=ctx.robot.frames[0]
        p,_=program('$MNUFRAME[grp,-1]=j',ctx=ctx,routines='ROUTINE grp:INTEGER BEGIN n=1 RETURN 1 END grp')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((calls,p.snapshot()['N']),([1],1));self.assertIs(ctx.robot.frames[0],old)

    def test_callback_selection_effect_precedes_active_target_lookup(self):
        holder={};point=pose();point.values['LOCATION'].values['X']=42.
        def forward(*args):
            holder['ctx'].robot.active_frame=7
            return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        ctx=callback_context(forward);ctx.robot.frames[7]=pose();holder['ctx']=ctx;old=ctx.robot.frames[0]
        p,_=program('$GROUP[1].$UFRAME=j',ctx=ctx);p.run()
        self.assertIs(ctx.robot.frames[0],old);self.assertEqual(row(ctx).values['X'],42.)

    def test_sticky_abort_prevents_selectors_and_table_publication(self):
        holder={};point=pose()
        def forward(*args):
            try:holder['p']._state.abort(17)
            except rt.KarelAbort:pass
            return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        ctx=callback_context(forward);old=ctx.robot.frames[0]
        p,_=program('$MNUFRAME[grp,7]=j',ctx=ctx,routines='ROUTINE grp:INTEGER BEGIN n=1 RETURN 1 END grp');holder['p']=p
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(p.snapshot()['N'],0);self.assertIs(ctx.robot.frames[0],old);self.assertNotIn(7,ctx.robot.frames)


class SystemJointGuardTests(unittest.TestCase):
    def test_bad_joint_inputs_preserve_the_target(self):
        for values in ([0.],[0.,0.,1.],[rt.UNINITIALIZED,0.],[float('nan'),0.],[True,0.],[181.,0.]):
            with self.subTest(values=values):
                ctx=context();old=ctx.robot.frames[0]
                p,_=program('$MNUFRAME[1,0]=j',ctx=ctx,decl=f'j:JOINTPOS{len(values)}')
                p._state.values['J']=joint(values)
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertIs(ctx.robot.frames[0],old)

    def test_joint_values_cannot_replace_a_pose_field(self):
        for field in ('location','location.x','config_data','ext1'):
            with self.subTest(field=field),self.assertRaises(TranslationError):program('$MNUFRAME[1,7].'+field+'=j')

    def test_active_target_still_requires_a_configured_row(self):
        ctx=context();ctx.robot.frames[7]=pose();ctx.robot.active_frame=7
        # Conversion requires the selected frame. Remove the destination tool instead.
        del ctx.robot.tools[0]
        p,_=program('$GROUP[1].$UTOOL=j',ctx=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertNotIn(0,ctx.robot.tools)

    def test_context_host_write_still_requires_a_cartesian_value(self):
        ctx=context()
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):
            ctx.system_pose_write('FRAME',1,7,joint([0.,0.]))
        self.assertNotIn(7,ctx.robot.frames)


if __name__=='__main__':unittest.main()
