"""Authored system-row model transfers and retained publication participants."""
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py.kinematics import pose
from tests.test_extended_services import compile_program
from tests.test_cartesian_interfaces import value as cartesian
from tests.test_joint_interoperability import joint
from tests.test_project_scheduler import source


def point():return cartesian('XYZWPREXT',(100.,0.,42.),(0.,0.,0.),(42.,0.,0.))


def context():
    model=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100},
        {'type':'prismatic','min':0,'max':100}],'external_axes':1,
        'current':{'joints':{'type':['JOINTPOS',2],'value':[0.,42.]}}}}).robot
    tables=rt.RobotContext(frames={7:point()},tools={8:point()},active_frame=7,active_tool=8)
    return rt.ExecutionContext(robot=rt.RobotContext(groups={1:tables,2:model},active_group=2))


def build(action='GET_VAR',path='$MNUFRAME[1,7]',*,ctx=None,width=2,body=None,**options):
    ctx=context() if ctx is None else ctx
    program,result=compile_program(body or f"{action}(e,'','{path}',j,s)",
        decl=options.pop('decl',f'j:JOINTPOS{width} e,s,n:INTEGER'),context=ctx,**options)
    program._state.values.update(J=joint([0.,42.]+[0.]*(width-2)),E=99,S=77,N=0)
    return program,result,ctx


def failed(test,program,ctx,pattern=None):
    before=(program.snapshot(),ctx.entries.copy())
    with test.assertRaises(rt.KarelRuntimeError) as caught:program.run()
    if pattern:test.assertIn(pattern,str(caught.exception))
    test.assertEqual((program.snapshot(),ctx.entries),before)


class SystemModelValueTests(unittest.TestCase):
    def test_all_four_row_forms_get_and_set_in_both_execution_modes(self):
        for action in ('GET_VAR','SET_VAR'):
            for path,kind,number in (('$MNUFRAME[1,7]','frames',7),('$MNUTOOL[1,8]','tools',8),
                                     ('$GROUP[1].$UFRAME','frames',7),('$GROUP[1].$UTOOL','tools',8)):
                for cooperative in (False,True):
                    with self.subTest(action=action,path=path,cooperative=cooperative):
                        p,_,ctx=build(action,path,cooperative=cooperative);old=getattr(ctx.robot.groups[1],kind)[number]
                        data=p.run();self.assertEqual((data['E'],data['S']),(1,0))
                        if action=='GET_VAR':
                            self.assertEqual(data['J']['axes'],[0.,42.]);self.assertIs(getattr(ctx.robot.groups[1],kind)[number],old)
                        else:
                            value=getattr(ctx.robot.groups[1],kind)[number]
                            self.assertIsNot(value,old);self.assertEqual(value.spec,('XYZWPREXT',))
                            self.assertEqual([value.values[name] for name in ('X','Z','EXT1','EXT2','EXT3')],[100.,42.,42.,0.,0.])
                        self.assertEqual(ctx.robot.groups[2].current.joints.values,[0.,42.])

    def test_model_widths_and_zero_padding(self):
        for width in (2,3,9):
            for action in ('GET_VAR','SET_VAR'):
                with self.subTest(width=width,action=action):
                    p,_,ctx=build(action,width=width);data=p.run()
                    self.assertEqual(data['J']['axes'],[0.,42.]+[0.]*(width-2));self.assertEqual(data['S'],0)

    def test_get_accepts_all_cartesian_row_representations(self):
        for kind in ('POSITION','XYZWPR','XYZWPREXT'):
            with self.subTest(kind=kind):
                ctx=context();ctx.robot.groups[2]=rt.ExecutionContext.from_config({'robot':{
                    'dh':[{'a':100},{'type':'prismatic','min':0,'max':100}],
                    'current':{'joints':{'type':['JOINTPOS',2],'value':[0.,42.]}}}}).robot
                ctx.robot.groups[1].frames[7]=cartesian(kind,(100.,0.,42.),(0.,0.,0.))
                p,_,_=build(ctx=ctx);self.assertEqual(p.run()['J']['axes'],[0.,42.])

    def test_custom_forward_config_and_all_external_values_are_retained(self):
        ctx=context();value=pose();config=value.values['CONFIG_DATA'].clone();config.values['CFG_FLIP']=True
        ctx.robot.groups[2].forward=lambda *_:(value,config,[7.,8.,9.])
        p,_,_=build('SET_VAR',ctx=ctx);p.run();row=ctx.robot.groups[1].frames[7]
        self.assertEqual([row.values[name] for name in ('EXT1','EXT2','EXT3')],[7.,8.,9.])
        self.assertTrue(row.values['CONFIG_DATA'].values['CFG_FLIP'])

    def test_inverse_adapter_receives_independent_seed_and_source(self):
        ctx=context()
        def inverse(seed,target,*args):
            seed.values[0]=99.;target.values['X']=999.
            return joint([0.,42.])
        ctx.robot.groups[2].inverse=inverse
        p,_,_=build(ctx=ctx);p.run()
        self.assertEqual(ctx.robot.groups[1].frames[7].values['X'],100.)
        self.assertEqual(ctx.robot.groups[2].current.joints.values,[0.,42.])

    def test_named_write_can_populate_an_absent_row(self):
        p,_,ctx=build('SET_VAR','$MNUTOOL[1,9]');p.run()
        self.assertEqual(ctx.robot.groups[1].tools[9].values['EXT1'],42.)

    def test_get_model_uses_current_seed_not_destination_contents(self):
        seen=[];ctx=context()
        def inverse(seed,*args):seen.append(seed.values[:]);return joint([0.,42.])
        ctx.robot.groups[2].inverse=inverse
        p,_,_=build(ctx=ctx);p._state.values['J']=joint([7.,8.]);p.run()
        self.assertEqual(seen,[[0.,42.]])

    def test_partial_joint_output_is_replaced_and_keeps_its_storage(self):
        p,_,ctx=build();value=p._state.values['J'];value.values[:]=[rt.UNINITIALIZED,rt.UNINITIALIZED]
        data=p.run();self.assertEqual(data['J']['axes'],[0.,42.]);self.assertIs(p._state.values['J'],value)

    def test_set_keeps_captured_input_when_later_status_selector_changes_source(self):
        p,_,ctx=build('SET_VAR',decl='j:JOINTPOS2 e,n:INTEGER s:ARRAY[1]OF INTEGER',
            body="SET_VAR(e,'','$MNUFRAME[1,7]',j,s[change()])",
            routines='ROUTINE change:INTEGER BEGIN j[2]=10 RETURN 1 END change')
        array=rt.Array(('ARRAY',1,('INTEGER',)));array.values[:]=[77];p._state.values['S']=array
        data=p.run();self.assertEqual(data['J']['axes'],[0.,10.])
        self.assertEqual(ctx.robot.groups[1].frames[7].values['EXT1'],42.)

    def test_existing_explicit_full_path_binding_keeps_precedence(self):
        ctx=context();value=ctx.variables.define('','$MNUFRAME[1,7]',('JOINTPOS',2))
        value.raw().values[:]=[7.,8.]
        p,_,_=build(ctx=ctx);self.assertEqual(p.run()['J']['axes'],[7.,8.])
        self.assertEqual(ctx.robot.groups[1].frames[7].values['EXT1'],42.)

    def test_linked_model_transfer_uses_the_root_callers_group(self):
        ctx=context();ctx.robot.active_group=1
        files={'main':source('MAIN','work',decl='j:JOINTPOS2 IN GROUP[2]',routines='ROUTINE work FROM LIB'),
               'lib':source('LIB','',decl='j FROM MAIN:JOINTPOS2 e,s:INTEGER',
                    routines="ROUTINE work BEGIN GET_VAR(e,'','$MNUFRAME[1,7]',j,s) SET_VAR(e,'','$MNUTOOL[1,9]',j,s) END work")}
        instance=translate_project(files).instantiate(context=ctx);data=instance.run('MAIN')
        self.assertEqual(data['MAIN']['values']['J']['axes'],[0.,42.])
        self.assertEqual(ctx.robot.groups[1].tools[9].values['EXT1'],42.)

    def test_handlers_use_the_same_checked_transfer(self):
        p,_,ctx=build('SET_VAR',body="CONDITION[1]: WHEN TRUE DO SET_VAR(e,'','$MNUFRAME[1,7]',j,s) ENDCONDITION ENABLE CONDITION[1] n=1")
        self.assertEqual(p.run()['S'],0);self.assertEqual(ctx.robot.groups[1].frames[7].values['EXT1'],42.)

    def test_saved_model_rows_and_closed_data_replay(self):
        p,_,ctx=build('SET_VAR');data=p.run();saved=json.loads(json.dumps(ctx.to_config()))
        other=rt.ExecutionContext.from_config(saved);q,_,_=build('SET_VAR',ctx=other)
        self.assertEqual(q.run(),data);self.assertEqual(other.to_config(),saved)


class SystemModelPublicationTests(unittest.TestCase):
    def change_during_adapter(self,change,*,action='SET_VAR',path='$MNUFRAME[1,7]'):
        ctx=context();holder={}
        def forward(*args):change(ctx,holder['p']);value=pose();return value,value.values['CONFIG_DATA'],[0.,0.,0.]
        def inverse(*args):change(ctx,holder['p']);return joint([0.,42.])
        ctx.robot.groups[2].forward=forward;ctx.robot.groups[2].inverse=inverse
        p,_,_=build(action,path,ctx=ctx);holder['p']=p
        return p,ctx

    def test_row_changes_during_adapter_preserve_callback_edits_and_metadata(self):
        changes=(lambda c,p:c.robot.groups[1].frames.__setitem__(7,point()),
                 lambda c,p:c.robot.groups[1].frames[7].values.__setitem__('X',999.),
                 lambda c,p:c.robot.groups[1].frames[7].values.__setitem__('CONFIG_DATA',point().values['CONFIG_DATA']),
                 lambda c,p:c.robot.groups[1].frames.pop(7))
        for action in ('GET_VAR','SET_VAR'):
            for change in changes:
                with self.subTest(action=action,change=change):
                    p,ctx=self.change_during_adapter(change,action=action)
                    with self.assertRaises(rt.KarelRuntimeError):p.run()
                    self.assertEqual((p.snapshot()['E'],p.snapshot()['S']),(99,77));self.assertEqual(ctx.entries,{})

    def test_active_selection_change_does_not_redirect_a_write(self):
        p,ctx=self.change_during_adapter(lambda c,p:setattr(c.robot.groups[1],'active_frame',9),path='$GROUP[1].$UFRAME')
        old=ctx.robot.groups[1].frames[7]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.robot.groups[1].active_frame,9);self.assertIs(ctx.robot.groups[1].frames[7],old)
        self.assertEqual((p.snapshot()['E'],p.snapshot()['S'],ctx.entries),(99,77,{}))

    def test_context_banks_and_new_full_path_binding_are_retained(self):
        changes=(lambda c,p:setattr(c,'entries',{}),
                 lambda c,p:setattr(c.robot.groups[1],'frames',dict(c.robot.groups[1].frames)),
                 lambda c,p:c.robot.groups.__setitem__(1,context().robot.groups[1]),
                 lambda c,p:c.variables.define('','$MNUFRAME[1,7]',('INTEGER',),9))
        for change in changes:
            with self.subTest(change=change):
                p,ctx=self.change_during_adapter(change);old=ctx.robot.groups[1].frames[7]
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertEqual((p.snapshot()['E'],p.snapshot()['S'],ctx.entries),(99,77,{}))
                self.assertEqual(old.values['X'],100.)

    def test_newly_populated_destination_is_not_overwritten(self):
        p,ctx=self.change_during_adapter(lambda c,p:c.robot.groups[1].tools.__setitem__(9,point()),path='$MNUTOOL[1,9]')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.robot.groups[1].tools[9].values['X'],100.);self.assertEqual(ctx.entries,{})

    def test_output_binding_and_joint_list_changes_reject_publication(self):
        changes=(lambda c,p:setattr(p._state.values['J'],'values',[0.,42.]),
                 lambda c,p:p._state.values['J'].values.__setitem__(0,7.),
                 lambda c,p:p._state.values.__setitem__('E',123))
        for change in changes:
            with self.subTest(change=change):
                p,ctx=self.change_during_adapter(change,action='GET_VAR')
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertEqual(p.snapshot()['S'],77);self.assertEqual(ctx.entries,{})

    def test_metadata_reference_storage_is_retained(self):
        holder={};other={'code':77}
        def change(c,p):holder['ref'].storage=other
        p,ctx=self.change_during_adapter(change);storage={'code':77}
        ref=rt.Reference(('INTEGER',),storage,'code');holder['ref']=ref;p._state.values['S']=ref
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((storage['code'],other['code'],ctx.entries),(77,77,{}))

    def test_unrelated_adapter_effects_are_retained_on_success(self):
        p,ctx=self.change_during_adapter(lambda c,p:p._state.values.__setitem__('N',7))
        data=p.run();self.assertEqual((data['N'],data['S']),(7,0))

    def test_abort_even_if_caught_by_adapter_prevents_publication(self):
        def change(c,p):
            try:p._state.abort(17)
            except rt.KarelAbort:pass
        p,ctx=self.change_during_adapter(change);old=ctx.robot.groups[1].frames[7]
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertIs(ctx.robot.groups[1].frames[7],old)
        self.assertEqual((p.snapshot()['E'],p.snapshot()['S'],ctx.entries),(99,77,{}))


class SystemModelFailureTests(unittest.TestCase):
    def test_source_capture_checkpoint_conflict_precedes_inverse_adapter(self):
        p,_,ctx=build();calls=[];counter=[0];tick=p._state.tick
        ctx.robot.groups[2].inverse=lambda *_:calls.append(1)
        def change(line=None):
            tick(line);counter[0]+=1
            if counter[0]==2:ctx.robot.groups[1].frames[7].values['X']=999.
        with patch.object(p._state,'tick',side_effect=change),self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((calls,p.snapshot()['E'],p.snapshot()['S'],ctx.entries),([],99,77,{}))
        self.assertEqual(ctx.robot.groups[1].frames[7].values['X'],999.)

    def test_budget_exhaustion_prevents_data_and_cache_publication(self):
        for action in ('GET_VAR','SET_VAR'):
            with self.subTest(action=action):
                p,_,ctx=build(action);old=ctx.robot.groups[1].frames[7];before=p.snapshot()
                with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=2)
                self.assertEqual(p.snapshot(),before);self.assertIs(ctx.robot.groups[1].frames[7],old);self.assertEqual(ctx.entries,{})

    def test_bad_source_joint_data_and_unreachable_pose_preserve_outputs(self):
        p,_,ctx=build('SET_VAR');p._state.values['J'].values[1]=rt.UNINITIALIZED;failed(self,p,ctx)
        p,_,ctx=build();ctx.robot.groups[1].frames[7].values['X']=20000.;failed(self,p,ctx,'IK solution')

    def test_modeled_write_requires_a_valid_existing_row(self):
        p,_,ctx=build('SET_VAR');ctx.robot.groups[1].frames[7].values['CONFIG_DATA'].values['CFG_TURN_NO1']=8
        old=ctx.robot.groups[1].frames[7];failed(self,p,ctx);self.assertIs(ctx.robot.groups[1].frames[7],old)

    def test_field_and_selection_paths_do_not_gain_joint_conversion(self):
        for action in ('GET_VAR','SET_VAR'):
            for path in ('$MNUFRAME[1,7].LOCATION','$MNUFRAME[1,7].CONFIG_DATA','$MNUFRAMENUM[1]'):
                with self.subTest(action=action,path=path):
                    p,_,ctx=build(action,path);data=p.run();self.assertEqual((data['E'],data['S'],ctx.entries),(99,3,{}))

    def test_report_exposes_explicit_models_and_retained_participants(self):
        _,result,_=build();policy=result.report['system_variable_transfer_policy']
        self.assertFalse(policy['controller_validated']);self.assertIn('calling root group',policy['models'])
        self.assertIn('output locations/data/containers',policy['models'])


if __name__=='__main__':unittest.main()
